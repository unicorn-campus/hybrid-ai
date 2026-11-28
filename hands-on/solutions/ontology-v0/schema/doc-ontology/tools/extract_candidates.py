"""4단계 [단계 ②]: 발견용 표본을 1건씩 LLM에 넣어 스키마 후보를 넓게 뽑음.

- 온톨로지 적용: 하지 않음. examples에는 그 문서 종류의 역량 질문만 넣고, 앞서 나온 이름이나 공통 개념의 이름을 넘기지 않음
- 멈춤: 묶음의 시작 수를 본 뒤 새 타입이 3건 연속 없으면 그 묶음을 멈춤. 상한에 닿아도 멈춤
- 새 타입: 대소문자, 띄어쓰기, 밑줄 차이를 없앤 이름이 두 번째로 나온 때(한 번만 나온 이름은 잡음으로 보고 세지 않음)
실행: python tools/extract_candidates.py {문서 종류}
만드는 파일: {문서 종류}/output/candidates_calls.jsonl, {문서 종류}/output/candidates_summary.md
"""

from __future__ import annotations

import asyncio
import collections
import json
import re
import sys
import time

from neo4j_graphrag.components.schema import SchemaFromTextExtractor

from common import BASE_DIR, load_chunks, read_json
from llm import make_llm
from units import header_of, split_chunk

QUIET_LIMIT = 3  # 새 타입이 연속으로 이만큼 없으면 묶음을 멈춤


def norm(name: str) -> str:
    return re.sub(r"[\s_]+", "", name).lower()


def load_units(doc_type: str) -> dict[str, dict]:
    """발견용 단위를 읽음. 추출 단위를 쓰는 문서 종류는 units.json에서, 아니면 사본의 청크를 그대로 씀."""
    path = BASE_DIR / doc_type / "units.json"
    if path.exists():
        return {u["unit_id"]: u for u in read_json(path)["units"]}
    return {u["unit_id"]: u for c in load_chunks(doc_type) for u in split_chunk(doc_type, c)[0]}


def examples_for(doc_type: str) -> str:
    questions = [q["question"] for q in read_json(BASE_DIR / "competency_questions.json")["questions"]
                 if doc_type in q["doc_types"]]
    return "이 스키마로 만든 지식 그래프가 답해야 하는 질문:\n" + "\n".join(f"- {q}" for q in questions)


async def run(doc_type: str) -> None:
    plan = read_json(BASE_DIR / "sample_plan.json")["doc_types"][doc_type]
    units = load_units(doc_type)
    llm = make_llm()
    extractor = SchemaFromTextExtractor(llm=llm)
    examples = examples_for(doc_type)
    out_dir = BASE_DIR / doc_type / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    seen = collections.Counter()  # 다듬은 이름 → 나온 건수(문서 종류 전체에서 셈)
    first_form = {}  # 다듬은 이름 → 처음 나온 표기
    calls, stops = [], {}
    started = time.time()
    with open(out_dir / "candidates_calls.jsonl", "w", encoding="utf-8", newline="\n") as log:
        for bundle, unit_ids in plan["discover"].items():
            start = plan["bundles"][bundle]["discover_start"]
            quiet = 0
            for position, unit_id in enumerate(unit_ids, 1):
                unit = units[unit_id]
                record = {"doc_type": doc_type, "bundle": bundle, "position": position, "unit_id": unit_id,
                          "node_types": [], "relationship_types": [], "patterns": [], "new_types": [], "error": None}
                try:
                    schema = await extractor.run(text=header_of(doc_type, unit, version=1) + "\n" + unit["text"], examples=examples)
                    data = schema.model_dump()
                    record["node_types"] = [{"label": n["label"], "properties": [p["name"] for p in n.get("properties") or []]}
                                            for n in data["node_types"]]
                    record["relationship_types"] = [r["label"] for r in data["relationship_types"]]
                    record["patterns"] = [[p["source"], p["relationship"], p["target"]] for p in data["patterns"] or []]
                    record["constraints_ignored"] = len(data.get("constraints") or [])  # 후보 단계의 제약은 쓰지 않음
                    names = {n["label"] for n in record["node_types"]} | set(record["relationship_types"])
                    for name in names:
                        key = norm(name)
                        first_form.setdefault(key, name)
                        seen[key] += 1
                        if seen[key] == 2:  # 두 번째로 나온 때를 새 타입으로 셈
                            record["new_types"].append(first_form[key])
                except Exception as error:  # 스키마 검증 실패나 형식 오류는 사유를 적고 넘어감
                    record["error"] = f"{type(error).__name__}: {str(error)[:300]}"
                log.write(json.dumps(record, ensure_ascii=False) + "\n")
                log.flush()
                calls.append(record)
                print(f"[{doc_type}] {bundle} {position}/{len(unit_ids)} {unit_id}: 노드 {len(record['node_types'])}, "
                      f"관계 {len(record['relationship_types'])}, 새 타입 {len(record['new_types'])}"
                      + (f", 실패 {record['error'][:80]}" if record["error"] else ""), flush=True)
                quiet = 0 if record["new_types"] else quiet + 1
                if position >= start and quiet >= QUIET_LIMIT:
                    stops[bundle] = f"{position}건에서 멈춤(새 타입이 {QUIET_LIMIT}건 연속 없음)"
                    break
            else:
                stops[bundle] = f"{len(unit_ids)}건 모두 봄(상한)"
    write_summary(doc_type, calls, stops, llm.usage, time.time() - started)


def write_summary(doc_type: str, calls: list[dict], stops: dict, usage: dict, seconds: float) -> None:
    node_hits, rel_hits, prop_hits, pattern_hits = (collections.Counter() for _ in range(4))
    form = {}
    for call in calls:
        for node in call["node_types"]:
            key = norm(node["label"])
            form.setdefault(key, node["label"])
            node_hits[key] += 1
            for prop in node["properties"]:
                prop_hits[(key, prop)] += 1
        for rel in call["relationship_types"]:
            form.setdefault(norm(rel), rel)
            rel_hits[norm(rel)] += 1
        for source, rel, target in call["patterns"]:
            pattern_hits[(source, rel, target)] += 1
    ok = [c for c in calls if not c["error"]]
    lines = [f"# 스키마 후보 요약: {doc_type}", "",
             f"- 호출 {len(calls)}건(성공 {len(ok)}, 실패 {len(calls) - len(ok)}), 토큰 {usage['total_tokens']:,}, 걸린 시간 {seconds:.0f}초  ",
             f"- 노드 타입 이름 {len(node_hits)}개(두 번 이상 나온 것 {sum(1 for v in node_hits.values() if v > 1)}개), "
             f"관계 이름 {len(rel_hits)}개(두 번 이상 나온 것 {sum(1 for v in rel_hits.values() if v > 1)}개)  ",
             "- 이름은 대소문자, 띄어쓰기, 밑줄 차이를 없애고 셈. 한 번만 나온 이름도 빼지 않고 적음  ", "",
             "## 묶음별 멈춘 곳", "", "| 묶음 | 본 건수 | 멈춘 까닭 |", "|---|---|---|"]
    for bundle, why in stops.items():
        lines.append(f"| {bundle} | {sum(1 for c in calls if c['bundle'] == bundle)} | {why} |")
    lines += ["", "## 노드 타입 후보(나온 건수 순)", "", "| 이름 | 나온 건수 | 속성(나온 건수) |", "|---|---|---|"]
    for key, hits in node_hits.most_common():
        props = sorted(((p, n) for (k, p), n in prop_hits.items() if k == key), key=lambda x: -x[1])
        lines.append(f"| {form[key]} | {hits} | " + ", ".join(f"{p}({n})" for p, n in props[:12]) + " |")
    lines += ["", "## 관계 후보(나온 건수 순)", "", "| 이름 | 나온 건수 |", "|---|---|"]
    lines += [f"| {form[key]} | {hits} |" for key, hits in rel_hits.most_common()]
    lines += ["", "## 패턴 후보(두 번 이상 나온 것)", "", "| 출발 | 관계 | 도착 | 나온 건수 |", "|---|---|---|---|"]
    lines += [f"| {s} | {r} | {t} | {n} |" for (s, r, t), n in pattern_hits.most_common() if n > 1]
    failed = [c for c in calls if c["error"]]
    if failed:
        lines += ["", "## 실패한 호출", "", "| 단위 | 사유 |", "|---|---|"]
        lines += [f"| {c['unit_id']} | {c['error'][:160]} |" for c in failed]
    (BASE_DIR / doc_type / "output" / "candidates_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print(f"[{doc_type}] 끝: 호출 {len(calls)}, 실패 {len(failed)}, 노드 이름 {len(node_hits)}, 관계 이름 {len(rel_hits)}, 멈춤 {stops}")


if __name__ == "__main__":
    asyncio.run(run(sys.argv[1]))
