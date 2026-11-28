"""8단계 값 맞추기 표: 혜택의 대상(target) 문장을 업종 8개 중 하나로 맞추는 후보를 LLM이 냄. 사람이 확정함.

- 입력: 채우기 시험(또는 인덱싱) 결과의 Benefit 노드(benefit_id, name, target). 업종 허용 값은 값 목록 파일에서만 읽음
- 출력: common/output/category_candidates.json(후보 값, 까닭, 미정 여부, 가까운 후보)
- 이미 후보가 있는 항목은 다시 묻지 않음(인덱싱 뒤 항목이 늘면 다시 돌려 새 항목만 사람이 확정하기 위함)
- approve: 사람이 확정한 결정 파일을 받아 온톨로지 원본의 업종 맞추기 표(maps/category.ttl)를 씀. 확정한 항목만 approved,
  나머지는 needs_review. 앞서 확정한 행은 지우지 않음. 초안 폴더(draft-ttl/)가 있으면 초안에, 없으면 승인본(ttl/)에 씀
실행: python common/tools/draft_category_map.py draft [--from {인덱서 세대 폴더}/new_map_items.json]
      python common/tools/draft_category_map.py approve {결정 파일}
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE / "tools"))

from common import DOC_TYPES, read_json, write_json  # noqa: E402

import ttl_write  # noqa: E402  ttl/tools(common이 경로를 넣어 줌). 온톨로지 원본(Turtle) 읽기와 쓰기

CANDIDATES = BASE / "common/output/category_candidates.json"

PROMPT = """너는 카드 혜택의 대상 문장을 가맹점 업종으로 나누는 도우미다.
업종 값은 다음 {n}개뿐이다: {values}
아래 혜택의 대상 문장을 보고 가장 맞는 업종 하나를 고른다.
- 둘 이상의 업종에 고르게 걸치거나, {n}개 어디에도 분명히 들지 않으면 category를 "미정"으로 하고 near에 가까운 후보를 최대 2개 적는다
- 문장에 없는 가맹점을 짐작하지 않는다
JSON 하나로만 답한다: {{"category": "...", "reason": "한 문장", "near": ["..."]}}

혜택 이름: {name}
대상 문장: {target}
"""


def benefits_from_fill() -> list[dict]:
    rows = {}
    path = BASE / "benefit_guide/output/fill_calls.jsonl"
    for line in path.read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        for node in record["graph"]["nodes"]:
            if node["label"] == "Benefit" and node["properties"].get("benefit_id"):
                p = node["properties"]
                rows[p["benefit_id"]] = {"benefit_id": p["benefit_id"], "name": p.get("name", ""), "target": p.get("target", "")}
    return list(rows.values())


def draft(source: str | None = None) -> None:
    """source: 인덱서가 남긴 new_map_items.json(인덱싱 뒤 늘어난 혜택). 없으면 채우기 시험 결과에서 모음."""
    from llm import make_llm
    values = read_json(BASE / "inputs/value_lists.json")["lists"]["업종"]["values"]
    old = {r["benefit_id"]: r for r in (read_json(CANDIDATES)["rows"] if CANDIDATES.exists() else [])}
    llm = make_llm()
    rows = list(old.values()) if source else []  # 인덱서 입력이면 시험 결과 후보를 지우지 않고 보탬
    items = read_json(source)["benefits"] if source else benefits_from_fill()
    for item in items:
        if source and item["benefit_id"] in old:
            continue
        if item["benefit_id"] in old:
            rows.append(old[item["benefit_id"]])
            continue
        if not item["target"]:
            rows.append({**item, "category": "미정", "reason": "대상 문장이 추출되지 않음", "near": [], "undecided": True})
            continue
        answer = json.loads(llm.chat_json(PROMPT.format(n=len(values), values=", ".join(values), name=item["name"], target=item["target"])))
        category = answer.get("category") if answer.get("category") in values else "미정"
        rows.append({**item, "category": category, "reason": answer.get("reason", ""), "near": answer.get("near", []),
                     "undecided": category == "미정"})
        print(item["benefit_id"], category, answer.get("reason", "")[:60], flush=True)
    write_json(CANDIDATES, {"values": values, "rows": rows, "llm_calls": llm.usage["calls"]})
    print(f"후보 {len(rows)}건, 미정 {sum(r['undecided'] for r in rows)}건, 새로 물은 것 {llm.usage['calls']}건")


def approve(decision_file: str) -> None:
    """결정 파일: {"decided_by": ..., "date": ..., "decisions": {benefit_id: 업종 값 | "잇지 않음"}}. 적지 않은 항목은 needs_review."""
    values = read_json(BASE / "inputs/value_lists.json")["lists"]["업종"]["values"]
    decision = read_json(decision_file)
    ttl_dir = ttl_write.work_dir()
    settled = {r["benefit_id"]: r for r in ttl_write.category_rows(ttl_dir)}  # 앞서 적은 행
    rows = {}
    for r in read_json(CANDIDATES)["rows"]:
        chosen = decision["decisions"].get(r["benefit_id"])
        if chosen in values:
            rows[r["benefit_id"]] = {**r, "category": chosen, "status": "approved"}
        elif chosen == "잇지 않음":
            rows[r["benefit_id"]] = {**r, "category": None, "status": "not_linked"}
        elif settled.get(r["benefit_id"], {}).get("status") in ("approved", "not_linked"):
            rows[r["benefit_id"]] = settled[r["benefit_id"]]  # 앞서 사람이 정한 것은 그대로 둠
        else:
            rows[r["benefit_id"]] = {**r, "category": None, "status": "needs_review"}
    rows = [rows.get(key) or settled[key] for key in sorted(set(rows) | set(settled))]
    ttl_write.write_category_rows(rows, decision["decided_by"], decision["date"], ttl_dir)
    print({s: sum(1 for r in rows if r["status"] == s) for s in ("approved", "not_linked", "needs_review")})


if __name__ == "__main__":
    if sys.argv[1] == "draft":
        draft(sys.argv[3] if len(sys.argv) > 3 and sys.argv[2] == "--from" else None)
    else:
        approve(sys.argv[2])
