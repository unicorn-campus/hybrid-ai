"""이 저장소 v0가 만든 시험 데이터를 지움: Neo4j의 v0 세대 노드(Community 포함), 검색엔진의 card_chunks-gen-hai-* 인덱스.
data 폴더의 세대 기록과 활성 세대 파일은 지우지 않고 data/_old/{시각}/으로 옮김(입력 청크 파일은 그대로 둠).

대상은 이 저장소 앞머리(gen-{GENERATION_TAG}-)로 시작하는 세대뿐임. 세대는 세 곳에서 모음: data/generations 폴더,
Neo4j의 generation 값, OpenSearch 인덱스 이름. 다른 앞머리 세대(예: 분리 전 볼륨에 있던 hybrid-ai-lab의 gen-full-001,
gen-sample-*)는 지우지 않음.
지금 활성 세대는 --all을 줄 때만 지움(검색이 쓰는 세대를 실수로 지우지 않게 함).
실행: python tools/reset.py              (지울 대상만 셈, 아무것도 지우지 않음)
      python tools/reset.py --yes        (활성 세대 말고 지움)
      python tools/reset.py --yes --all  (활성 세대까지 지움)
"""

from __future__ import annotations

import argparse
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config  # noqa: E402
import search_index  # noqa: E402
from common import load_json  # noqa: E402
from orchestrator import neo4j_driver, own_generation  # noqa: E402


def main() -> None:
    p = argparse.ArgumentParser(description="이 저장소 v0 세대(gen-hai-*)만 지움")
    p.add_argument("--yes", action="store_true", help="실제로 지움. 없으면 대상만 셈")
    p.add_argument("--all", action="store_true", help="지금 활성 세대까지 지움")
    a = p.parse_args()
    yes = a.yes
    active = load_json(config.ACTIVE_FILE)["generation"] if config.ACTIVE_FILE.exists() else None
    keep = {active} if active and not a.all else set()
    if keep:
        print(f"활성 세대 {active}는 남김(지우려면 --all)")

    prefix = f"gen-{config.GENERATION_TAG}-"
    found = config.GENERATIONS.glob(f"{prefix}*") if config.GENERATIONS.exists() else []
    folders = sorted(f.name for f in found if f.name not in keep)
    client = search_index.client()
    indices = sorted(r["index"] for r in client.cat.indices(index=f"{search_index.index_name(prefix)}*", format="json")
                     if r["index"] not in {search_index.index_name(g) for g in keep})
    with neo4j_driver() as d:
        in_graph = [r["g"] for r in d.execute_query(
            "MATCH (n) WHERE n.generation STARTS WITH $p RETURN DISTINCT n.generation AS g", p=prefix)[0]]
        generations = sorted((set(folders) | set(in_graph) | {i[len(search_index.index_name("")):] for i in indices})
                             - keep)
        assert all(own_generation(g) for g in generations)
        if not generations:
            print("지울 v0 세대가 없음")
        for g in generations:
            c = d.execute_query("MATCH (c:Community {generation: $g}) RETURN count(c) AS n", g=g)[0][0]["n"]
            if yes:
                n = d.execute_query("MATCH (n {generation: $g}) DETACH DELETE n RETURN count(*) AS n", g=g)[0][0]["n"]
                print(f"Neo4j 세대 {g}: 노드 {n}개 지움(Community {c}개 포함)")
            else:
                n = d.execute_query("MATCH (n {generation: $g}) RETURN count(n) AS n", g=g)[0][0]["n"]
                print(f"Neo4j 세대 {g}: 노드 {n}개(Community {c}개 포함) 지울 대상")
    for index in indices:
        aliases = sorted(client.indices.get_alias(index=index)[index].get("aliases", {}))
        if yes:
            client.indices.delete(index=index)  # 인덱스를 지우면 그 인덱스의 별칭도 함께 사라짐
        print(f"검색엔진 인덱스 {index}{' 지움' if yes else ' 지울 대상'}(별칭 {aliases or '없음'})")
    if not yes:
        print("대상만 셈. 실제로 지우려면 --yes")
        return

    moved = []
    old = config.DATA / "_old" / time.strftime("%Y%m%d-%H%M%S")
    for g in folders:
        (old / "generations").mkdir(parents=True, exist_ok=True)
        shutil.move(str(config.GENERATIONS / g), str(old / "generations" / g))
        moved.append(g)
    if active and not keep and own_generation(active):
        old.mkdir(parents=True, exist_ok=True)
        shutil.move(str(config.ACTIVE_FILE), str(old / config.ACTIVE_FILE.name))
        moved.append(config.ACTIVE_FILE.name)
    if moved:
        print(f"data 기록 {len(moved)}개를 {old.relative_to(config.V0).as_posix()}로 옮김: {moved}")


if __name__ == "__main__":
    main()
