"""결과 확인 도구(읽기만): 질문 하나로 「검색엔진 → 청크 → 그래프 엔티티 → 커뮤니티 보고서 → 리랭크」를 차례로 보여 줌.

인덱싱이 끝난 뒤 교육생이 "그래서 무엇이 만들어졌나"를 눈으로 확인하는 용도임(교재 30쪽 「검색 때 그래프로 건너감」).
답을 만드는 LLM 호출은 없음. 검색기(답변 생성)는 다음 실습에서 만듦.

실행(이 폴더에서):
  ../.venv/Scripts/python.exe check_graph.py "할부로 산 상품의 철회는 며칠 안에 요청해야 하나요?"
  ../.venv/Scripts/python.exe check_graph.py --qid Q02            평가셋 질문으로 실행하고 적중 여부와 이유까지 판정
  ../.venv/Scripts/python.exe check_graph.py --qid Q09 --rerank   마지막에 Cohere 리랭크로 청크 순위를 다시 매김
  ../.venv/Scripts/python.exe check_graph.py --drop gen-lab-...   실패한 세대의 노드와 인덱스만 지움(활성 세대는 거부)
"""

import argparse
import json
import re
import sys

import cohere
from langchain_cohere import CohereEmbeddings

import index_graph as main  # 설정값과 접속 함수를 main과 같은 것으로 씀(값이 어긋나지 않게)
import kr_tokenizer

sys.stdout.reconfigure(encoding="utf-8")

EVAL_SET_PATH = main.ROOT_DIR / "hands-on" / "solutions" / "eval-set.json"  # 평가셋(질문, 정답, 근거 위치)
RERANK_MODEL = "rerank-v4.0-fast"  # Cohere 리랭커(RAG 실습과 같음)
RRF_K = 60  # RRF(순위 융합) 상수. 순위 차이를 완만하게 만듦
SNIPPET = 70  # 본문 미리보기 글자 수
WIDE_TOP = 50  # 근거 청크가 상위 N개 밖일 때 몇 위인지 알아보려고 넓게 다시 찾는 개수


def short(text: str, width: int = SNIPPET) -> str:
    """한 줄 미리보기: 줄바꿈을 공백으로 바꾸고 width 글자에서 자름."""
    flat = " ".join(str(text).split())
    return flat if len(flat) <= width else flat[:width] + "…"


def load_question(args) -> tuple[str, dict | None]:
    """명령줄 질문 또는 평가셋 질문(--qid)을 돌려줌. 평가셋이면 적중 판정용 항목도 함께."""
    if args.qid:
        for item in main.load_json(EVAL_SET_PATH)["questions"]:
            if item["id"] == args.qid:
                return item["question"], item
        raise SystemExit(f"평가셋에 {args.qid}가 없음: {EVAL_SET_PATH}")
    if not args.question:
        raise SystemExit("질문을 주거나 --qid Q02 처럼 평가셋 번호를 줌")
    return args.question, None


# ---------------------------------------------------------------------------
# 검색엔진: BM25 + kNN → RRF
# ---------------------------------------------------------------------------
def search_engine(os_client, index: str, question: str, top: int) -> tuple[list[dict], list[str]]:
    """BM25(text_tokens)와 kNN(embedding)을 각각 돌리고 RRF로 합쳐 상위 top개 청크를 돌려줌. 질문 토큰도 함께 돌려줌."""
    meta = os_client.indices.get_mapping(index=index)[index]["mappings"]["_meta"]["tokenizer"]
    lexicon = kr_tokenizer.lexicon_from_meta(meta)  # 색인 때 기록한 사전으로 같은 토크나이저를 만듦
    tokens = lexicon.tokenize(question)
    embedder = CohereEmbeddings(model=main.EMBEDDING_MODEL, cohere_api_key=main.read_secret("COHERE_API_KEY"))
    vector = embedder.embed_query(question)  # 질문은 input_type search_query(색인은 search_document)

    bm25 = os_client.search(index=index, body={
        "size": top * 3, "_source": ["chunk_id", "chroma_id", "doc_type", "text", "card_name", "record_id"],
        "query": {"match": {"text_tokens": " ".join(tokens)}}})["hits"]["hits"]
    knn = os_client.search(index=index, body={
        "size": top * 3, "_source": ["chunk_id", "chroma_id", "doc_type", "text", "card_name", "record_id"],
        "query": {"knn": {"embedding": {"vector": vector, "k": top * 3}}}})["hits"]["hits"]

    fused: dict[str, dict] = {}
    for name, hits in (("bm25", bm25), ("knn", knn)):
        for rank, hit in enumerate(hits, start=1):
            row = fused.setdefault(hit["_id"], {"chunk_id": hit["_id"], "source": hit["_source"], "rrf": 0.0, "ranks": {}})
            row["rrf"] += 1.0 / (RRF_K + rank)  # RRF 점수 = 1 / (상수 + 순위)를 두 검색에서 더함
            row["ranks"][name] = rank
    ordered = sorted(fused.values(), key=lambda r: -r["rrf"])[:top]
    return ordered, tokens


# ---------------------------------------------------------------------------
# 그래프: 청크 → 엔티티, 엔티티 벡터 검색, 커뮤니티 보고서
# ---------------------------------------------------------------------------
def entities_of_chunks(driver, generation: str, chunk_ids: list[str], limit: int) -> dict[str, list[dict]]:
    """검색이 찾은 chunk_id와 같은 청크 노드에서 FROM_CHUNK로 이어진 엔티티를 가져옴(교재 33쪽 「검색엔진과 KG 연결」)."""
    records, _, _ = driver.execute_query(
        "UNWIND $ids AS cid MATCH (c:Chunk {generation: $g, chunk_id: cid}) "
        "MATCH (e)-[:FROM_CHUNK]->(c) "
        "RETURN cid, [l IN labels(e) WHERE NOT l STARTS WITH '__'][0] AS label, properties(e) AS props, elementId(e) AS id",
        ids=chunk_ids, g=generation)
    result: dict[str, list[dict]] = {cid: [] for cid in chunk_ids}
    for record in records:
        result[record["cid"]].append({"id": record["id"], "label": record["label"], "props": dict(record["props"])})
    for cid in result:
        result[cid] = result[cid][:limit]
    return result


def entity_vector_search(driver, generation: str, vector: list[float], top: int) -> list[dict]:
    """K6 벡터 인덱스로 질문과 뜻이 가까운 엔티티를 찾음(엔티티 직접 검색, 교재 46, 47쪽). 지금 세대만 남김."""
    records, _, _ = driver.execute_query(
        "CALL db.index.vector.queryNodes($index, $k, $vec) YIELD node, score "
        "WHERE node.generation = $g "
        "RETURN elementId(node) AS id, [l IN labels(node) WHERE NOT l STARTS WITH '__'][0] AS label, "
        "properties(node) AS props, score ORDER BY score DESC LIMIT $top",
        index=main.ENTITY_INDEX, k=top * 10, vec=vector, g=generation, top=top)
    return [{"id": r["id"], "label": r["label"], "props": dict(r["props"]), "score": r["score"]} for r in records]


def neighbors_of(driver, entity_id: str, limit: int) -> list[str]:
    """엔티티의 1-hop 이웃을 「-[관계]-> 라벨(첫 속성)」 꼴로 돌려줌."""
    records, _, _ = driver.execute_query(
        "MATCH (e)-[r]-(n:__Entity__) WHERE elementId(e) = $id "
        "RETURN type(r) AS t, startNode(r) = e AS out, [l IN labels(n) WHERE NOT l STARTS WITH '__'][0] AS label, "
        "properties(n) AS props LIMIT $limit", id=entity_id, limit=limit)
    lines = []
    for record in records:
        arrow = f"-[{record['t']}]->" if record["out"] else f"<-[{record['t']}]-"
        lines.append(f"{arrow} {main.short_name({'label': record['label'], 'props': dict(record['props'])})}")
    return lines


def communities_of(driver, entity_ids: list[str], top: int) -> list[dict]:
    """엔티티들이 속한 커뮤니티 보고서를 많이 걸린 순으로 돌려줌(교재 56쪽 ③ IN_COMMUNITY)."""
    if not entity_ids:
        return []
    records, _, _ = driver.execute_query(
        "UNWIND $ids AS eid MATCH (e)-[:IN_COMMUNITY]->(c:Community) WHERE elementId(e) = eid "
        "RETURN c.title AS title, c.summary AS summary, c.size AS size, count(*) AS hits ORDER BY hits DESC LIMIT $top",
        ids=entity_ids, top=top)
    return [dict(r) for r in records]


# ---------------------------------------------------------------------------
# 리랭크와 적중 판정
# ---------------------------------------------------------------------------
def rerank_chunks(question: str, chunks: list[dict]) -> list[tuple[dict, float]]:
    """Cohere 리랭커로 청크 본문을 다시 채점해 점수 내림차순으로 돌려줌(API 1회)."""
    client = cohere.ClientV2(api_key=main.read_secret("COHERE_API_KEY"))
    response = client.rerank(model=RERANK_MODEL, query=question, documents=[c["source"]["text"] for c in chunks],
                             top_n=len(chunks))
    return [(chunks[r.index], r.relevance_score) for r in response.results]


def squash(text: str) -> str:
    """공백과 줄바꿈을 모두 지움. 원문은 줄이 띄어쓰기 자리나 낱말 중간에서 끊겨 있어(예: 「7일\\n이내에」, 「시점\\n에」)
    글자 그대로 비교하면 정답이 있어도 어긋나므로, 비교할 때만 양쪽에서 지움(화면에 보이는 글은 그대로)."""
    return re.sub(r"\s+", "", text)


def match_clue(phrase: str, chunks: list[dict], entities: list[dict]) -> dict:
    """정답 단서 하나가 어느 청크 본문과 엔티티 설명에 들어 있는지 위치(번호)를 돌려줌. 공백과 줄바꿈은 무시함."""
    needle = squash(phrase)
    return {
        "chunks": [i for i, c in enumerate(chunks) if needle in squash(c["source"]["text"])],
        "entities": [i for i, e in enumerate(entities)
                     if needle in squash(main.core.entity_description(e["label"], e["props"]))],
    }


def hit_check(item: dict, chunks: list[dict], entities: list[dict]) -> list[str]:
    """평가셋 relevance.clues(정답 단서)가 상위 청크 본문이나 엔티티 설명에 있으면 적중으로 봄. 공백과 줄바꿈은 무시함."""
    results = []
    for rel in item.get("relevance", []):
        for phrase in rel.get("clues", []):
            found = match_clue(phrase, chunks, entities)
            where = (["청크"] if found["chunks"] else []) + (["엔티티"] if found["entities"] else [])
            results.append(f"{'적중' if where else '빗나감'}({', '.join(where) or '-'}): {short(phrase, 50)}")
    return results


def clue_chunks_in_index(os_client, index: str, phrase: str) -> list[dict]:
    """이 세대 검색엔진 인덱스 전체에서 단서가 본문에 든 청크를 찾음(근거 청크가 인덱스에 있는지 알아보려는 것)."""
    needle = squash(phrase)
    found = []
    for hit in main.helpers.scan(os_client, index=index, query={"_source": ["chunk_id", "chroma_id", "doc_type", "text"]}):
        if needle in squash(hit["_source"]["text"]):
            found.append({**hit["_source"], "chunk_id": hit["_id"]})
    return found


def clue_chunks_in_source(phrase: str) -> tuple[list[str], int] | None:
    """입력 원본(RAG 실습 Chroma) 전체에서 단서가 든 청크의 chroma_id와 전체 청크 수. Chroma가 없으면 None."""
    try:
        rows = main.read_chroma_rows(False)
    except (SystemExit, Exception):
        return None
    needle = squash(phrase)
    return [r["chroma_id"] for r in rows if needle in squash(r["text"])], len(rows)


def explain_hits(item: dict, chunks: list[dict], entities: list[dict], os_client, index: str, question: str,
                 active: dict, top: int) -> list[str]:
    """[6] 적중 판정을 줄 목록으로 만듦. 판정 방법, 정답 근거 위치, 단서마다 결과와 맞추거나 빗나간 이유를 적음."""
    ids = ", ".join(c["source"]["chroma_id"] for c in chunks) or "없음"
    lines = [f"판정 방법: 정답 단서 문구가 ① 검색된 상위 {len(chunks)}개 청크 본문 ② 찾은 엔티티 {len(entities)}개의 설명 중",
             "          하나에 들어 있으면 적중(공백과 줄바꿈은 무시). 청크 ID를 비교하는 것이 아님",
             f"검색된 청크: {ids}"]
    relevance = item.get("relevance", [])
    for rel in relevance:
        where = " ".join(x for x in (rel.get("source"), rel.get("location")) if x)
        if where:
            lines.append(f"평가셋의 정답 근거: {where}")
    clues = [phrase for rel in relevance for phrase in rel.get("clues", [])]
    if not clues:
        return lines + ["평가셋에 정답 단서(clues)가 없어 판정하지 않음"]
    for number, phrase in enumerate(clues, start=1):
        found = match_clue(phrase, chunks, entities)
        hit = bool(found["chunks"] or found["entities"])
        lines += ["", f"단서 {number}/{len(clues)}: {short(phrase, 70)}", f"  판정: {'적중' if hit else '빗나감'}"]
        if found["chunks"]:
            lines.append("  ① 검색된 청크 본문: 단서 있음 → " + ", ".join(chunks[i]["source"]["chroma_id"] for i in found["chunks"]))
        else:
            lines.append("  ① 검색된 청크 본문: 단서 없음")
        lines.append(f"  ② 찾은 엔티티 설명: {'단서 있음' if found['entities'] else '단서 없음'}")
        if hit:
            for i in found["chunks"]:
                row = chunks[i]
                lines.append(f"  이유: 근거 청크 {row['source']['chroma_id']}이(가) 검색 {i + 1}위(bm25 {row['ranks'].get('bm25', '-')} / "
                             f"knn {row['ranks'].get('knn', '-')})에 있고 본문에 단서가 있음")
            shown = []  # 같은 설명이 여러 번 나오면(병합 전 중복 등) 한 번만 보여 줌
            for i in found["entities"]:
                e = entities[i]
                text = short(main.core.entity_description(e["label"], e["props"]), 70)
                if text not in shown and len(shown) < 2:
                    shown.append(text)
                    lines.append(f"  이유: {e['label']} 엔티티 설명에 단서가 있음: {text}")
            continue
        # 빗나감: 원인을 나눠 설명함
        in_index = clue_chunks_in_index(os_client, index, phrase)
        if in_index:
            wide, _ = search_engine(os_client, index, question, min(WIDE_TOP, max(top, active["chunk_count"])))
            notes = []
            for row in in_index:
                position = next((n for n, c in enumerate(wide, start=1) if c["chunk_id"] == row["chunk_id"]), None)
                notes.append(f"{row['chroma_id']}은(는) 검색 {position}위" if position
                             else f"{row['chroma_id']}은(는) 검색 상위 {len(wide)}개 안에도 없음")
            lines += [f"  이유: 근거 청크는 이 세대 인덱스에 있지만 검색 상위 {len(chunks)}개에 들지 못함",
                      f"        {', '.join(notes)}",
                      f"        → 검색 순위 문제임. --top 을 늘리면 청크 쪽이 맞음(예: --top {max(top + 1, 10)})"]
            continue
        source = clue_chunks_in_source(phrase)
        lines.append("  이유: 이 세대의 검색엔진 인덱스에 단서가 든 청크가 없음")
        if source is None:
            lines.append("        원본(Chroma)을 읽을 수 없어 단서가 든 청크를 찾지 못함")
        elif source[0]:
            lines += [f"        단서가 든 청크: {', '.join(source[0])} (원본 Chroma 전체 {source[1]}개 기준)",
                      f"        이 세대에는 청크 {active['chunk_count']}개만 들어 있고 그 청크는 빠져 있음"]
            if active["chunk_count"] < source[1]:
                lines.append("        → 표본(--sample)으로 만든 세대임. --sample 없이 전체 인덱싱한 세대에서 확인함")
        else:
            lines.append("        원본(Chroma) 전체에서도 단서 문구가 없음 → 평가셋의 단서 문구나 원문 표기를 확인함")
    return lines


# ---------------------------------------------------------------------------
# 세대 지우기(--drop)
# ---------------------------------------------------------------------------
def drop_generation(driver, os_client, generation: str, active: dict | None) -> None:
    """실패한 세대의 노드(Community 포함)와 검색엔진 인덱스만 지움. 활성 세대는 거부함."""
    if not generation.startswith(f"gen-{main.GENERATION_TAG}-"):
        raise SystemExit(f"이 도구는 gen-{main.GENERATION_TAG}- 세대만 지움: {generation}")
    if active and active["generation"] == generation:
        raise SystemExit("활성 세대는 지우지 않음(다른 세대를 게시한 뒤 지움)")
    records, _, _ = driver.execute_query("MATCH (n {generation: $g}) DETACH DELETE n RETURN count(*) AS n", g=generation)
    index = main.index_name(generation)
    had_index = os_client.indices.exists(index=index)
    if had_index:
        os_client.indices.delete(index=index)
    print(f"세대 {generation}: 노드 {records[0]['n']}개 지움, 검색엔진 인덱스 {'지움' if had_index else '없음'}")


# ---------------------------------------------------------------------------
# 전체 흐름
# ---------------------------------------------------------------------------
def run(args) -> None:
    """활성 세대에서 질문 하나로 [1] ~ [6]을 차례로 출력함. --drop이면 세대만 지움."""
    active = main.read_active()
    driver = main.neo4j_driver()
    os_client = main.opensearch_client()
    if args.drop:
        drop_generation(driver, os_client, args.drop, active)
        return
    if not active:
        raise SystemExit("활성 세대가 없음: 먼저 index_graph.py 를 실행함")
    generation, index = active["generation"], active["search_index"]
    question, item = load_question(args)
    print(f"활성 세대 {generation} (청크 {active['chunk_count']}개, 게시 {active['published_at']})")
    print(f"질문: {question}")

    # 1) 검색엔진
    chunks, tokens = search_engine(os_client, index, question, args.top)
    print(f"\n[1] 검색엔진: 질문 토큰 {tokens}")
    print(f"    BM25와 kNN을 RRF로 합친 상위 {len(chunks)}개 (bm25 순위 / knn 순위)")
    for rank, row in enumerate(chunks, start=1):
        src = row["source"]
        tag = src.get("card_name") or src.get("record_id") or ""
        print(f"    {rank}. {src['chroma_id']:<8} {src['doc_type']:<13} {tag:<14} "
              f"bm25 {row['ranks'].get('bm25', '-'):>2} / knn {row['ranks'].get('knn', '-'):>2}  {short(src['text'])}")

    # 2) 청크 → 엔티티(FROM_CHUNK)
    by_chunk = entities_of_chunks(driver, generation, [c["chunk_id"] for c in chunks], args.entities)
    print(f"\n[2] 청크의 엔티티(FROM_CHUNK, 청크마다 최대 {args.entities}개)")
    found_entities = []
    for row in chunks:
        ents = by_chunk[row["chunk_id"]]
        found_entities.extend(ents)
        print(f"    {row['source']['chroma_id']}: {len(ents)}개")
        for ent in ents:
            print(f"       - {short(main.core.entity_description(ent['label'], ent['props']), 90)}")

    # 3) 엔티티 직접 검색(K6 벡터)
    embedder = CohereEmbeddings(model=main.EMBEDDING_MODEL, cohere_api_key=main.read_secret("COHERE_API_KEY"))
    direct = entity_vector_search(driver, generation, embedder.embed_query(question), args.entities)
    print(f"\n[3] 엔티티 직접 검색(벡터 인덱스 {main.ENTITY_INDEX}, 상위 {len(direct)}개)와 이웃")
    for ent in direct:
        print(f"    {ent['score']:.3f}  {short(main.core.entity_description(ent['label'], ent['props']), 90)}")
        for line in neighbors_of(driver, ent["id"], 3):
            print(f"           {line}")

    # 4) 커뮤니티 보고서
    reports = communities_of(driver, [e["id"] for e in found_entities + direct], 3)
    print(f"\n[4] 엔티티가 속한 커뮤니티 보고서(많이 걸린 순, 최대 3개)")
    if not reports:
        print("    없음(K8을 건너뛴 세대이거나 묶음이 작음)")
    for report in reports:
        print(f"    - 「{report['title']}」 (엔티티 {report['size']}개, 걸린 엔티티 {report['hits']}개)")
        print(f"      {short(report['summary'], 110)}")

    # 5) 리랭크(선택)
    if args.rerank:
        print(f"\n[5] Cohere 리랭크({RERANK_MODEL}): 청크 본문을 질문으로 다시 채점")
        for new_rank, (row, score) in enumerate(rerank_chunks(question, chunks), start=1):
            old_rank = chunks.index(row) + 1
            print(f"    {new_rank}. (융합 {old_rank}위 → ) {score:.3f}  {row['source']['chroma_id']}  {short(row['source']['text'], 60)}")

    # 6) 적중 판정(평가셋 질문일 때)
    if item:
        print(f"\n[6] 적중 판정(평가셋 {item['id']})")
        for line in explain_hits(item, chunks, found_entities + direct, os_client, index, question, active, args.top):
            print(f"    {line}" if line else "")
        print(f"\n    참고(평가셋 정답 문장, 판정과는 무관): {short(item.get('ground_truth', ''), 100)}")
    driver.close()


def main_cli() -> None:
    """명령줄 인자를 읽어 run을 부름."""
    parser = argparse.ArgumentParser(description="GraphRAG 인덱싱 결과 확인 도구(읽기만)")
    parser.add_argument("question", nargs="?", help="질문. --qid를 주면 생략")
    parser.add_argument("--qid", help="평가셋 질문 번호(예: Q02)")
    parser.add_argument("--top", type=int, default=4, help="검색엔진 상위 청크 수(기본 4)")
    parser.add_argument("--entities", type=int, default=5, help="청크마다 보여 줄 엔티티 수와 직접 검색 수(기본 5)")
    parser.add_argument("--rerank", action="store_true", help="마지막에 Cohere 리랭크 실행")
    parser.add_argument("--drop", help="이 세대의 노드와 검색엔진 인덱스를 지움(활성 세대는 거부)")
    run(parser.parse_args())


if __name__ == "__main__":
    main_cli()
