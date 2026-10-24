"""Neo4j 세대별 노드 수와 Community 수, OpenSearch card_chunks-* 인덱스와 별칭을 JSON으로 남김(읽기만 함).

지우기 전과 뒤를 비교하려고 씀. 실행: python tools/snapshot_stores.py {저장할 파일}
"""

from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config  # noqa: E402
import search_index  # noqa: E402
from common import save_json  # noqa: E402
from orchestrator import neo4j_driver  # noqa: E402

logging.getLogger("neo4j.notifications").setLevel(logging.ERROR)  # 빈 DB의 「없는 라벨, 속성」 알림을 숨김


def snapshot() -> dict:
    with neo4j_driver() as d:
        q = lambda cypher: [dict(r) for r in d.execute_query(cypher)[0]]
        nodes = {r["g"]: r["n"] for r in q("MATCH (n) RETURN n.generation AS g, count(*) AS n ORDER BY g")}
        communities = {r["g"]: r["n"] for r in q("MATCH (c:Community) RETURN c.generation AS g, count(*) AS n ORDER BY g")}
        total = q("MATCH (n) RETURN count(n) AS n")[0]["n"]
    client = search_index.client()
    pattern = f"{config.INDEX_PREFIX}-*"
    indices = {r["index"]: int(r["docs.count"]) for r in client.cat.indices(index=pattern, format="json")}
    aliases = [{"alias": r["alias"], "index": r["index"]} for r in client.cat.aliases(name="*", format="json")
               if r["index"].startswith(f"{config.INDEX_PREFIX}-")]
    return {"taken_at": time.strftime("%Y-%m-%d %H:%M:%S"), "neo4j_total_nodes": total,
            "neo4j_nodes_by_generation": {str(k): v for k, v in nodes.items()},
            "neo4j_communities_by_generation": {str(k): v for k, v in communities.items()},
            "opensearch_indices": dict(sorted(indices.items())), "opensearch_aliases": aliases}


def main() -> None:
    out = Path(sys.argv[1])
    data = snapshot()
    save_json(out, data)
    print(f"기록 → {out}")
    for k in ("neo4j_total_nodes", "neo4j_nodes_by_generation", "neo4j_communities_by_generation",
              "opensearch_indices", "opensearch_aliases"):
        print(f"{k}: {data[k]}")


if __name__ == "__main__":
    main()
