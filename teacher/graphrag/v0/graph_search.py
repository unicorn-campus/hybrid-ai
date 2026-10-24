"""Neo4j 그래프 검색: 질문 판단 → 거시 검색(커뮤니티 보고서) 또는 하이브리드 검색(엔티티 + 연결된 커뮤니티 보고서) → 답.

흐름
- 질문 판단(classify): LLM이 질문을 global(여러 문서를 모아야 답하는 거시 질문)과 hybrid(특정 대상의 사실을 묻는 질문)로 나눔
- 거시 검색(global_search): 질문 벡터로 커뮤니티 보고서 벡터 인덱스(kg_community_embedding)에서 가까운 보고서를 찾음
- 하이브리드 검색: 시작점을 두 갈래로 찾고 둘 다 커뮤니티 보고서까지 따라감
  - 청크 갈래(chunk_search, chunk_graph): OpenSearch에서 BM25와 벡터(kNN)를 순위 융합(RRF)해 청크를 찾고, Neo4j에서
    그 청크에서 나온 엔티티(FROM_CHUNK 역방향)와 그 엔티티가 속한 커뮤니티 보고서(IN_COMMUNITY)를 가져옴
  - 엔티티 갈래(hybrid_search): 질문 벡터로 엔티티 벡터 인덱스(kg_entity_embedding)에서 엔티티를 찾고, 같은 Cypher 안에서
    이웃 엔티티와 관계, 그 엔티티가 나온 청크 원문(FROM_CHUNK), 커뮤니티 보고서(IN_COMMUNITY)를 함께 가져옴
  엔티티 벡터만으로는 「한빛 가족돌봄 카드」, 「연회비 면제」처럼 이름과 낱말이 중요한 사실 질문의 시작점을 놓쳐서
  (2026-10-24 검증에서 Q01, Q09가 「근거에 없음」), 청크 갈래를 함께 둠
- 답하기(answer): 거시는 보고서만 근거로, 하이브리드는 원문과 엔티티(사실)에 보고서(맥락)를 더해 LLM이 답함
두 검색 모두 neo4j-graphrag의 VectorCypherRetriever를 씀(벡터로 노드를 찾은 뒤 retrieval_query로 그래프를 더 따라감).
활성 세대만 보도록 filters로 generation을 거름. DB에는 아무것도 쓰지 않음.

실행: python graph_search.py "질문"            (질문 판단 후 알맞은 검색)
      python graph_search.py --qid Q23 Q01      (hands-on/solutions/eval-set.json의 질문 id)
      --mode global|hybrid|local 로 판단을 건너뛰고 검색 방식을 고정함(local: 하이브리드에서 커뮤니티 보고서를 뺀 비교용)
      --show-context 로 LLM에 넘긴 근거 글을 함께 출력함
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from typing import Any

from neo4j_graphrag.embeddings.base import Embedder
from neo4j_graphrag.retrievers import VectorCypherRetriever

import config
import search_index
from common import embed, load_json, make_llm
from orchestrator import neo4j_driver

EVAL_SET = config.REPO / "hands-on" / "solutions" / "eval-set.json"
SYSTEM_PROPS = ("embedding", "generation", "run_id")  # 근거 글에 넣지 않는 관리용 속성
GLOBAL_TOP_K = 5  # 거시 검색에서 가져올 커뮤니티 보고서 수
HYBRID_TOP_K = 8  # 하이브리드 검색에서 찾을 엔티티 수
MAX_NEIGHBORS = 6  # 엔티티 하나에 붙이는 이웃 수(1-hop 이웃 중 질문과 비슷한 순)
MAX_CHUNKS = 5  # 근거로 넣는 청크 원문 수
MAX_REPORTS = 3  # 하이브리드 검색에서 근거로 넣는 커뮤니티 보고서 수(찾은 엔티티가 많이 속한 순)
CHUNK_CHARS = 700  # 청크 원문 하나의 글자 상한
CHUNK_TOP_K = 4  # 청크 갈래에서 고르는 청크 수(BM25와 kNN을 순위 융합한 뒤)
CHUNK_POOL = 10  # BM25와 kNN에서 각각 먼저 뽑는 수
RRF_K = 60  # 순위 융합 상수: 점수 = Σ 1 / (RRF_K + 순위)
MAX_CHUNK_ENTITIES = 8  # 청크 하나에서 근거로 넣는 엔티티 수
MAX_PROMPT_ENTITIES = 30  # 프롬프트에 넣는 엔티티 수 상한(두 갈래 합)
logging.getLogger("neo4j.notifications").setLevel(logging.ERROR)  # 벡터 검색 프로시저 사용 중단 예고 알림을 숨김

# 거시 검색: 찾은 Community 노드에서 보고서 칸만 꺼냄
GLOBAL_QUERY = """
RETURN node.community_id AS community_id, node.title AS title, node.summary AS summary,
       node.findings AS findings, node.size AS size, score
"""

# 하이브리드 검색: 찾은 엔티티(node)에서 이웃, 원문, 커뮤니티 보고서까지 한 번에 따라감.
# 이웃은 관계 1개로 이어진(1-hop) 엔티티이고, 질문 벡터($query_vector, 검색기가 넘김)와 코사인 유사도가 높은 순으로
# max_neighbors개를 고름. 1-hop 이웃은 그래프 거리가 모두 1이라 질문과의 의미 거리로 순서를 정함
HYBRID_QUERY = """
WITH node AS e, score
OPTIONAL MATCH (e)-[r]-(n:__Entity__ {generation: e.generation})
WITH e, score, r, n, coalesce(vector.similarity.cosine(n.embedding, $query_vector), -1.0) AS sim
ORDER BY sim DESC
WITH e, score, collect(DISTINCT {type: type(r), outgoing: startNode(r) = e, sim: sim,
     label: [l IN labels(n) WHERE NOT l STARTS WITH '__'][0], props: properties(n)})[..$max_neighbors] AS neighbors
OPTIONAL MATCH (e)-[:FROM_CHUNK]->(k:Chunk)
WITH e, score, neighbors, collect(DISTINCT {chunk_id: k.chunk_id, doc_type: k.doc_type, text: k.text}) AS chunks
OPTIONAL MATCH (e)-[:IN_COMMUNITY]->(c:Community)
RETURN elementId(e) AS id, [l IN labels(e) WHERE NOT l STARTS WITH '__'][0] AS label, properties(e) AS props,
       score, neighbors, chunks,
       CASE WHEN c IS NULL THEN null ELSE {community_id: c.community_id, title: c.title, summary: c.summary,
            findings: c.findings, size: c.size} END AS community
"""

# 청크 갈래: 검색엔진이 찾은 청크(순위대로)에서 엔티티와 커뮤니티 보고서까지 따라감
CHUNK_QUERY = """
UNWIND range(0, size($ids) - 1) AS i
MATCH (k:Chunk {chunk_id: $ids[i], generation: $g})
OPTIONAL MATCH (e:__Entity__)-[:FROM_CHUNK]->(k)
OPTIONAL MATCH (e)-[:IN_COMMUNITY]->(c:Community)
WITH i, k, e, c
RETURN i AS rank, k.chunk_id AS chunk_id, k.doc_type AS doc_type, k.text AS text,
       collect(DISTINCT CASE WHEN e IS NULL THEN null ELSE {label: [l IN labels(e) WHERE NOT l STARTS WITH '__'][0],
               props: properties(e)} END)[..$max_entities] AS entities,
       collect(DISTINCT CASE WHEN c IS NULL THEN null ELSE {community_id: c.community_id, title: c.title,
               summary: c.summary, findings: c.findings, size: c.size} END) AS communities
ORDER BY rank
"""

ROUTE_SYSTEM = (
    "너는 카드사 상담 지원 검색기의 질문 분류기다. 질문을 보고 검색 방식을 하나 고른다. 반드시 JSON 하나로만 답한다.")
ROUTE_USER = """검색 방식
- global: 여러 상담이나 문서를 모아 공통점, 주제, 경향, 집단별 차이를 물음. 답이 특정 대상 하나로 끝나지 않음
  예: "고객군별로 불만을 주제별로 나눠 주세요", "고객이 받아들인 제안에는 어떤 공통점이 있나요?"
- hybrid: 특정 카드, 조항, 상담, 금액, 기한, 조건 같은 사실을 물음. 답이 정해진 대상에서 나옴
  예: "할부로 산 물건은 며칠 안에 철회하나요?", "가족돌봄 카드의 돌봄 바우처 한도는?"

출력 형식(JSON): {{"route": "global 또는 hybrid", "reason": "고른 까닭 한 문장"}}

질문: {question}"""

ANSWER_SYSTEM = (
    "너는 카드사 상담 지원 도우미다. 아래 근거만 써서 질문에 한국어로 답한다. 근거에 없는 내용은 지어내지 말고 "
    "'근거에 없음'이라고 쓴다. 답 끝에 쓴 근거(보고서 제목, 청크 id)를 적는다. JSON {\"answer\": \"...\"} 하나로만 답한다.")


class KureEmbedder(Embedder):
    """neo4j-graphrag 검색기가 질문을 임베딩할 때 쓰는 KURE-v2(색인과 같은 임베더)."""

    def embed_query(self, text: str) -> list[float]:
        return embed([text])[0]


# ---------------------------------------------------------------- 질문 판단

def classify(llm, question: str) -> dict:
    """질문을 global 또는 hybrid로 나눔. 답 꼴이 틀리면 같은 입력으로 다시 묻고, 끝내 틀리면 hybrid로 둠.

    hybrid를 기본값으로 두는 까닭: 하이브리드 검색도 커뮤니티 보고서를 함께 넣으므로 거시 질문을 잘못 보내도 맥락이 남음.
    """

    for _ in range(config.LLM_RETRIES + 1):
        try:
            d = json.loads(llm.chat_json(ROUTE_USER.format(question=question), ROUTE_SYSTEM))
            route = str(d.get("route", "")).strip().lower()
            if route in ("global", "hybrid"):
                return {"route": route, "reason": str(d.get("reason", "")).strip()}
        except (json.JSONDecodeError, AttributeError):
            pass
    return {"route": "hybrid", "reason": "분류 답의 꼴이 맞지 않아 기본값(hybrid)으로 둠"}


# ---------------------------------------------------------------- 검색

def _clean(props: dict) -> dict:
    return {k: v for k, v in (props or {}).items() if k not in SYSTEM_PROPS and v not in (None, "", [])}


def _retriever(driver, index_name: str, retrieval_query: str) -> VectorCypherRetriever:
    """VectorCypherRetriever를 만듦.

    neo4j-graphrag 1.22.0 결함 우회: 인덱스 정보는 _embedding_node_property에 읽어 두면서, filters로 거를 때는
    _node_embedding_property를 봄. 그대로 두면 세대 필터를 줄 때 「node_label, embedding_node_property 필요」 예외가 나므로
    읽어 둔 값을 같은 이름으로 옮겨 둠. 우리 인덱스는 generation을 필터 속성으로 선언하지 않아, 라벨 전체를 정확히 견주는
    방식(brute force)으로 거름. 노드가 수천 개라 충분히 빠름.
    """

    retriever = VectorCypherRetriever(driver, index_name, retrieval_query)
    if getattr(retriever, "_node_embedding_property", None) is None:
        retriever._node_embedding_property = getattr(retriever, "_embedding_node_property", None)
    return retriever


def global_search(driver, generation: str, vector: list[float], top_k: int = GLOBAL_TOP_K) -> list[dict]:
    """질문 벡터와 가까운 커뮤니티 보고서 top_k개(활성 세대만)."""

    retriever = _retriever(driver, "kg_community_embedding", GLOBAL_QUERY)
    raw = retriever.get_search_results(query_vector=vector, top_k=top_k, filters={"generation": generation})
    return [dict(r) for r in raw.records]


def hybrid_search(driver, generation: str, vector: list[float], top_k: int = HYBRID_TOP_K) -> list[dict]:
    """질문 벡터와 가까운 엔티티 top_k개(활성 세대만)와 그 이웃, 원문, 커뮤니티 보고서."""

    retriever = _retriever(driver, "kg_entity_embedding", HYBRID_QUERY)
    raw = retriever.get_search_results(query_vector=vector, top_k=top_k, filters={"generation": generation},
                                       query_params={"max_neighbors": MAX_NEIGHBORS})
    return [dict(r) for r in raw.records]


def rrf(*rankings: list[str], k: int = RRF_K) -> list[str]:
    """여러 순위 목록을 순위 융합(Reciprocal Rank Fusion)으로 합침. 점수 = Σ 1 / (k + 순위). 같으면 먼저 나온 순."""

    score: dict[str, float] = {}
    for ranking in rankings:
        for rank, key in enumerate(ranking, 1):
            score[key] = score.get(key, 0.0) + 1.0 / (k + rank)
    return sorted(score, key=lambda key: -score[key])


_lexicons: dict[str, Any] = {}


def chunk_search(index: str, question: str, vector: list[float], top_k: int = CHUNK_TOP_K) -> list[str]:
    """OpenSearch에서 BM25(질문 토큰)와 kNN(질문 벡터)으로 각각 CHUNK_POOL개를 찾아 순위 융합한 청크 id top_k개."""

    os_client = search_index.client()
    if index not in _lexicons:  # 색인할 때 쓴 사전으로 같은 토크나이저를 만듦(인덱스마다 한 번)
        _lexicons[index] = search_index.tokenizer_from_meta(search_index.tokenizer_meta_of(index))
    tokens = _lexicons[index].tokenize_many([question])[0]
    src = {"includes": ["chunk_id"]}
    bm25 = os_client.search(index=index, body={"size": CHUNK_POOL, "_source": src,
                                               "query": {"match": {"text_tokens": " ".join(tokens)}}})
    knn = os_client.search(index=index, body={"size": CHUNK_POOL, "_source": src,
                                              "query": {"knn": {"embedding": {"vector": vector, "k": CHUNK_POOL}}}})
    ids = lambda res: [h["_source"]["chunk_id"] for h in res["hits"]["hits"]]
    return rrf(ids(bm25), ids(knn))[:top_k]


def chunk_graph(driver, generation: str, chunk_ids: list[str]) -> list[dict]:
    """검색엔진이 찾은 청크(순위대로)마다 원문, 그 청크에서 나온 엔티티, 그 엔티티가 속한 커뮤니티 보고서."""

    if not chunk_ids:
        return []
    rows, _, _ = driver.execute_query(CHUNK_QUERY, ids=chunk_ids, g=generation, max_entities=MAX_CHUNK_ENTITIES)
    return [dict(r) for r in rows]


def hybrid_context(rows: list[dict], chunk_rows: list[dict] | None = None, with_reports: bool = True) -> dict:
    """두 갈래 검색 결과를 근거 묶음으로 정리함. 같은 청크, 엔티티, 보고서는 한 번만 넣음.

    청크: 청크 갈래(검색엔진 순위)를 먼저, 이어서 엔티티 갈래 엔티티가 나온 청크를 MAX_CHUNKS개까지.
    엔티티: 청크 갈래 청크에서 나온 엔티티를 먼저, 이어서 엔티티 갈래 엔티티(이웃 포함).
    보고서: 두 갈래에서 걸린 횟수가 많은 순(같으면 먼저 걸린 순)으로 MAX_REPORTS개까지.
    """

    entities, seen, chunks, reports = [], set(), {}, {}

    def add_chunk(k: dict) -> None:
        if k.get("chunk_id") and k["chunk_id"] not in chunks and len(chunks) < MAX_CHUNKS:
            chunks[k["chunk_id"]] = {"chunk_id": k["chunk_id"], "doc_type": k.get("doc_type"),
                                     "text": str(k.get("text") or "")[:CHUNK_CHARS]}

    def add_report(c: dict | None, order: int) -> None:
        if with_reports and c:
            rep = reports.setdefault(c["community_id"], {**c, "hits": 0, "first": order})
            rep["hits"] += 1

    def add_entity(label: str, props: dict, extra: dict) -> None:
        key = json.dumps([label, _clean(props)], ensure_ascii=False, sort_keys=True)
        if key not in seen:
            seen.add(key)
            entities.append({"label": label, "props": _clean(props), **extra})

    order = 0
    for r in chunk_rows or []:
        add_chunk(r)
        for e in r["entities"]:
            if e and e.get("label"):
                add_entity(e["label"], e["props"], {"from": f"청크 {r['chunk_id']}", "neighbors": []})
        for c in r["communities"]:
            order += 1
            add_report(c, order)
    for r in rows:
        add_entity(r["label"], r["props"], {"score": round(r["score"], 3), "from": "엔티티 벡터",
                                             "neighbors": [{"type": n["type"], "outgoing": n["outgoing"],
                                                            "label": n["label"], "props": _clean(n["props"])}
                                                           for n in r["neighbors"] if n.get("type")]})
        for k in r["chunks"]:
            add_chunk(k)
        order += 1
        add_report(r.get("community"), order)
    ranked = sorted(reports.values(), key=lambda c: (-c["hits"], c["first"]))[:MAX_REPORTS]
    return {"entities": entities, "chunks": list(chunks.values()), "reports": ranked}


# ---------------------------------------------------------------- 답하기

def _report_text(c: dict) -> str:
    findings = "\n".join(f"  - {f}" for f in (c.get("findings") or []))
    return f"[보고서] {c['title']}\n{c['summary']}\n{findings}".rstrip()


def global_prompt(question: str, reports: list[dict]) -> str:
    body = "\n\n".join(_report_text(c) for c in reports) or "(찾은 보고서 없음)"
    return f"질문: {question}\n\n커뮤니티 보고서(여러 문서를 묶어 요약한 글):\n{body}"


def hybrid_prompt(question: str, ctx: dict) -> str:
    ents = []
    for e in ctx["entities"][:MAX_PROMPT_ENTITIES]:
        near = "; ".join(f"{'→' if n['outgoing'] else '←'}{n['type']} {n['label']} {json.dumps(n['props'], ensure_ascii=False)}"
                         for n in e["neighbors"])
        ents.append(f"- {e['label']} {json.dumps(e['props'], ensure_ascii=False)}" + (f" | 이웃: {near}" if near else ""))
    chunks = "\n\n".join(f"[원문 {k['chunk_id']}] ({k['doc_type']})\n{k['text']}" for k in ctx["chunks"]) or "(없음)"
    reports = "\n\n".join(_report_text(c) for c in ctx["reports"]) or "(없음)"
    return (f"질문: {question}\n\n사실 근거 1. 찾은 엔티티와 이웃:\n" + ("\n".join(ents) or "(없음)")
            + f"\n\n사실 근거 2. 엔티티가 나온 원문:\n{chunks}"
            + f"\n\n맥락 근거. 찾은 엔티티가 속한 커뮤니티 보고서(사실은 원문을 우선하고, 보고서는 전체 흐름을 보탤 때만 씀):\n{reports}")


def answer(llm, prompt: str) -> str:
    raw = llm.chat_json(prompt, ANSWER_SYSTEM)
    try:
        return str(json.loads(raw).get("answer", raw))
    except json.JSONDecodeError:
        return raw


# ---------------------------------------------------------------- 묶어서 부르기

def search(question: str, mode: str = "auto", driver=None, llm=None) -> dict:
    """질문 하나를 끝까지 처리함. mode: auto(질문 판단), global, hybrid, local(하이브리드에서 보고서를 뺀 비교용)."""

    llm = llm or make_llm()
    route = classify(llm, question) if mode == "auto" else {"route": mode, "reason": "검색 방식을 고정함"}
    active = load_json(config.ACTIVE_FILE)
    generation = active["generation"]
    vector = embed([question])[0]
    own = driver is None
    driver = driver or neo4j_driver()
    try:
        if route["route"] == "global":
            reports = global_search(driver, generation, vector)
            ctx = {"reports": reports}
            prompt = global_prompt(question, reports)
        else:
            chunk_rows = chunk_graph(driver, generation, chunk_search(active["search_index"], question, vector))
            ctx = hybrid_context(hybrid_search(driver, generation, vector), chunk_rows,
                                 with_reports=route["route"] != "local")
            prompt = hybrid_prompt(question, ctx)
    finally:
        if own:
            driver.close()
    return {"question": question, "generation": generation, **route, "context": ctx, "prompt": prompt,
            "answer": answer(llm, prompt), "llm_usage": dict(llm.usage)}


def _summary(res: dict) -> str:
    ctx = res["context"]
    lines = [f"검색 방식: {res['route']} ({res['reason']})"]
    if "entities" in ctx:
        from_chunks = [e["label"] for e in ctx["entities"] if e["from"].startswith("청크")]
        from_vec = [f"{e['label']}({e['score']})" for e in ctx["entities"] if e["from"] == "엔티티 벡터"]
        lines.append(f"청크 갈래 엔티티 {len(from_chunks)}개: " + ", ".join(from_chunks))
        lines.append(f"엔티티 갈래 엔티티 {len(from_vec)}개: " + ", ".join(from_vec))
        lines.append("원문: " + ", ".join(k["chunk_id"] for k in ctx["chunks"]))
    lines.append("커뮤니티 보고서: " + (" / ".join(c["title"] for c in ctx.get("reports", [])) or "없음"))
    lines.append(f"답: {res['answer']}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="Neo4j 그래프 검색(질문 판단, 거시 검색, 하이브리드 검색)")
    p.add_argument("question", nargs="*", help="질문 글(여러 낱말이면 이어 붙임)")
    p.add_argument("--qid", nargs="*", default=[], help="eval-set.json 질문 id(예: Q23 Q01)")
    p.add_argument("--mode", choices=["auto", "global", "hybrid", "local"], default="auto")
    p.add_argument("--show-context", action="store_true", help="LLM에 넘긴 근거 글도 출력")
    p.add_argument("--json", help="결과를 이 JSON 파일로 저장")
    a = p.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    evalset = {x["id"]: x["question"] for x in load_json(EVAL_SET)["questions"]}
    questions = [(qid, evalset[qid]) for qid in a.qid]
    if a.question:
        questions.append(("-", " ".join(a.question)))
    llm, out = make_llm(), []
    with neo4j_driver() as d:
        for qid, q in questions:
            res = search(q, a.mode, driver=d, llm=llm)
            res["qid"] = qid
            out.append(res)
            print(f"\n=== {qid} {q}\n{_summary(res)}")
            if a.show_context:
                print("--- 근거 글\n" + res["prompt"])
    print(f"\nLLM 사용량(누적): {dict(llm.usage)}")
    if a.json:
        from common import save_json
        save_json(a.json, [{k: v for k, v in r.items() if k != "llm_usage"} for r in out] + [{"llm_usage": dict(llm.usage)}])


if __name__ == "__main__":
    main()
