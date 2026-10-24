"""활성 세대 색인이 질문에 맞는 근거를 찾는지 눈으로 확인하는 도구(읽기만 함). v0에는 검색기가 없어 저장소를 직접 부름.

질문마다 네 갈래 상위 결과를 보여 줌:
  ① OpenSearch BM25(text_tokens, 질문은 인덱스 _meta의 사전으로 다시 만든 토크나이저로 자름)
  ② OpenSearch 벡터(kNN, 질문을 KURE-v2로 임베딩)
  ③ Neo4j 엔티티 벡터(kg_entity_embedding) → 그 엔티티가 나온 청크(FROM_CHUNK)
  ④ Neo4j 커뮤니티 벡터(kg_community_embedding, K8을 켠 세대만)
벡터 인덱스는 세대가 섞여 있어 넉넉히 뽑은 뒤 활성 세대만 남김.

실행: python tools/search_check.py Q01 Q09 Q24   (질문은 hands-on/solutions/eval-set.json의 id)
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config  # noqa: E402
import search_index  # noqa: E402
from common import embed, load_json  # noqa: E402
from orchestrator import neo4j_driver  # noqa: E402

EVAL_SET = config.REPO / "hands-on" / "solutions" / "eval-set.json"
TOP = 3
logging.getLogger("neo4j.notifications").setLevel(logging.ERROR)  # db.index.vector.queryNodes 사용 중단 예고 알림을 숨김
VECTOR_POOL = 200  # 세대가 섞인 Neo4j 벡터 인덱스에서 먼저 뽑는 수


def _where(src: dict) -> str:
    keys = ("source", "card_name", "record_id", "topic")
    return ", ".join(f"{k}={src[k]}" for k in keys if src.get(k))


def _snippet(text: str, n: int = 70) -> str:
    return " ".join(str(text).split())[:n]


def main() -> None:
    ids = sys.argv[1:] or ["Q01", "Q09", "Q24"]
    questions = {q["id"]: q for q in load_json(EVAL_SET)["questions"]}
    active = load_json(config.ACTIVE_FILE)
    g, index = active["generation"], active["search_index"]
    os_client = search_index.client()
    lex = search_index.tokenizer_from_meta(search_index.tokenizer_meta_of(index))
    print(f"활성 세대 {g}, 인덱스 {index}")
    with neo4j_driver() as d:
        for qid in ids:
            q = questions[qid]
            vec = embed([q["question"]])[0]
            print(f"\n=== {qid} {q['question']}")
            print(f"  기대 근거: {_snippet(q.get('relevance', ''), 160)}")

            tokens = lex.tokenize_many([q["question"]])[0]
            hits = os_client.search(index=index, body={"size": TOP, "query": {"match": {"text_tokens": " ".join(tokens)}},
                                                       "_source": {"excludes": ["embedding", "text_tokens"]}})
            print(f"  ① BM25 (질문 토큰 {tokens})")
            for h in hits["hits"]["hits"]:
                print(f"     {h['_score']:.2f} {_where(h['_source'])} | {_snippet(h['_source']['text'])}")

            hits = os_client.search(index=index, body={"size": TOP, "query": {"knn": {"embedding": {"vector": vec, "k": TOP}}},
                                                       "_source": {"excludes": ["embedding", "text_tokens"]}})
            print("  ② 벡터(kNN)")
            for h in hits["hits"]["hits"]:
                print(f"     {h['_score']:.3f} {_where(h['_source'])} | {_snippet(h['_source']['text'])}")

            rows, _, _ = d.execute_query(
                "CALL db.index.vector.queryNodes('kg_entity_embedding', $pool, $v) YIELD node, score "
                "WHERE node.generation = $g WITH node, score ORDER BY score DESC LIMIT $top "
                "OPTIONAL MATCH (node)-[:FROM_CHUNK]->(c:Chunk) "
                "RETURN [l IN labels(node) WHERE NOT l STARTS WITH '__'][0] AS label, properties(node) AS props, "
                "score, collect(DISTINCT c.doc_type) AS doc_types, count(DISTINCT c) AS chunks",
                pool=VECTOR_POOL, v=vec, g=g, top=TOP)
            print("  ③ 엔티티 벡터 → 청크")
            for r in rows:
                props = {k: v for k, v in r["props"].items() if k not in ("embedding", "generation", "run_id")}
                print(f"     {r['score']:.3f} {r['label']} {_snippet(props, 90)} | 청크 {r['chunks']}개 {r['doc_types']}")

            rows, _, _ = d.execute_query(
                "CALL db.index.vector.queryNodes('kg_community_embedding', $pool, $v) YIELD node, score "
                "WHERE node.generation = $g RETURN node.title AS title, node.summary AS summary, score "
                "ORDER BY score DESC LIMIT $top", pool=VECTOR_POOL, v=vec, g=g, top=TOP)
            print("  ④ 커뮤니티 벡터")
            for r in rows:
                print(f"     {r['score']:.3f} {r['title']} | {_snippet(r['summary'], 90)}")


if __name__ == "__main__":
    main()
