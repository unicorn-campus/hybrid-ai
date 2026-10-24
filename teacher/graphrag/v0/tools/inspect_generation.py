"""활성 세대의 Neo4j 그래프와 검색엔진 인덱스를 요약해 보여 줌(읽기만 함).

실행: python tools/inspect_generation.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config  # noqa: E402
import search_index  # noqa: E402
from common import load_json  # noqa: E402
from orchestrator import neo4j_driver  # noqa: E402


def main() -> None:
    active = load_json(config.ACTIVE_FILE)
    g = active["generation"]
    print(f"활성 세대 {g}, 검색엔진 인덱스 {active['search_index']}, 청크 {active['chunk_count']}개")
    with neo4j_driver() as d:
        q = lambda cypher: [dict(r) for r in d.execute_query(cypher, g=g)[0]]
        print("노드:", {r["label"]: r["n"] for r in q(
            "MATCH (n {generation: $g}) RETURN [l IN labels(n) WHERE NOT l STARTS WITH '__'][0] AS label, "
            "count(*) AS n ORDER BY label")})
        print("관계:", {r["t"]: r["n"] for r in q(
            "MATCH (a {generation: $g})-[r]->(b {generation: $g}) RETURN type(r) AS t, count(*) AS n ORDER BY t")})
        print("두 청크에 이어진 조항:", [r["u"] for r in q(
            "MATCH (k:Clause {generation: $g})-[:FROM_CHUNK]->(c:Chunk) WITH k, count(c) AS n WHERE n > 1 "
            "RETURN k.clause_no AS u ORDER BY u")])
        print("청크 노드:", q("MATCH (c:Chunk {generation: $g}) RETURN count(*) AS n, "
                            "count(DISTINCT c.chunk_id) AS ids")[0])
        print("상담 노드:", q("MATCH (c:Consultation {generation: $g}) OPTIONAL MATCH (c)-[:FOLLOWS]->(p) "
                             "RETURN c.record_id AS record, c.topic AS topic, p.record_id AS follows ORDER BY record"))
        print("임베딩 없는 엔티티:", q("MATCH (n:__Entity__ {generation: $g}) WHERE n.embedding IS NULL "
                                   "RETURN count(*) AS n")[0]["n"])
    print("검색엔진 청크 수:", len(search_index.chunk_ids(active["search_index"])))


if __name__ == "__main__":
    main()
