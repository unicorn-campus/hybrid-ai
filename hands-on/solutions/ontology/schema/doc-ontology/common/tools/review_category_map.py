"""8단계 값 맞추기 표: 사람이 확정할 업종 후보의 검토 파일과 결정 파일 틀을 만듦. LLM을 부르지 않음.

- 입력: common/output/category_candidates.json(draft_category_map.py draft가 만든 후보), 온톨로지 원본의 업종 맞추기 표
  (초안 폴더가 있으면 초안, 없으면 승인본의 maps/category.ttl)
- 대상: 아직 사람이 정하지 않은 혜택만(확정했거나 잇지 않기로 한 것은 빼고 수만 적음)
- 출력: review/step8-category.md(검토 파일), output/category_decision_draft.json(결정 파일 틀. 후보가 분명한 항목은 후보 값으로
  미리 채워 둠. 사람이 고쳐서 확정하면 draft_category_map.py approve가 이 파일을 읽음)
실행: python common/tools/review_category_map.py
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE / "tools"))

from common import read_json, write_json  # noqa: E402

import ttl_write  # noqa: E402  ttl/tools(common이 경로를 넣어 줌)

CANDIDATES = BASE / "common/output/category_candidates.json"
REVIEW = BASE / "review/step8-category.md"
DECISION = BASE / "output/category_decision_draft.json"


def cell(text) -> str:
    return str(text or "").replace("|", "/").replace("\n", " ") or "없음"


def main() -> None:
    ttl_dir = ttl_write.work_dir()
    settled = {r["benefit_id"]: r for r in ttl_write.category_rows(ttl_dir) if r["status"] in ("approved", "not_linked")}
    candidates = read_json(CANDIDATES)
    values = candidates["values"]
    rows = [r for r in candidates["rows"] if r["benefit_id"] not in settled]
    clear = [r for r in rows if not r["undecided"]]
    undecided = [r for r in rows if r["undecided"]]
    no_target = [r for r in undecided if not r.get("target")]
    lines = ["# 8단계 검토 파일: 업종 맞추기 표(혜택 → 업종)", "",
             "- 승인하는 것: 아래 혜택마다 이어 줄 업종 값. 후보는 LLM이 냈고, 확정은 사람이 함  ",
             "- 승인하면 일어나는 일: 확정한 행만 온톨로지 초안의 업종 맞추기 표(`maps/category.ttl`)에 적고, 기계 검사를 거쳐 승인본으로 올린 뒤 "
             "인덱싱이 그 혜택을 업종 노드에 이음(IN_CATEGORY). 확정하지 않은 행은 잇지 않음  ",
             f"- 읽은 곳: `common/output/category_candidates.json`, `{ttl_dir.relative_to(ttl_write.PROJECT).as_posix()}/maps/category.ttl`  ", "",
             "## 1. 한눈에 보기", "",
             "업종은 가맹점을 나눈 정해진 갈래 8개임(값 목록 파일에서 읽음). 혜택의 대상 문장은 글이라서 그대로는 업종과 이어지지 않으므로, "
             "혜택마다 업종 하나를 맞춰 주는 표가 필요함. 이 표가 있어야 「많이 쓰는 업종에 혜택을 주는 카드」 같은 질문에 답할 수 있음.", "",
             "| 구분 | 건수 |", "|---|---|",
             f"| 앞서 사람이 정한 혜택(이번 검토에서 뺌) | {len(settled)} |",
             f"| 이번에 검토할 혜택 | {len(rows)} |",
             f"| 그 가운데 LLM 후보가 분명한 것 | {len(clear)} |",
             f"| 그 가운데 미정(둘 이상에 걸치거나 어디에도 들지 않음) | {len(undecided) - len(no_target)} |",
             f"| 그 가운데 대상 문장이 추출되지 않아 묻지 못한 것 | {len(no_target)} |", "",
             "| 후보 업종 | 건수 |", "|---|---|"]
    lines += [f"| {v} | {sum(1 for r in clear if r['category'] == v)} |" for v in values]
    lines += ["", "열 뜻  ", "- 구분: 혜택이 지금 어느 상태인지  ", "- 후보 업종: LLM이 고른 업종 값. 값 목록의 8개 가운데 하나  ",
              "- 건수: 그 줄에 해당하는 혜택 수  ", ""]
    number = 2
    for value in values:
        group = sorted((r for r in clear if r["category"] == value), key=lambda r: r["benefit_id"])
        if not group:
            continue
        lines += [f"## {number}. 후보 업종 「{value}」 {len(group)}건", "",
                  f"LLM이 「{value}」로 고른 혜택임. 대상 문장을 보고 맞지 않는 것만 골라 주면 됨.", "",
                  "| 혜택 ID | 혜택 이름 | 대상 문장 | 까닭 |", "|---|---|---|---|"]
        lines += [f"| {r['benefit_id']} | {cell(r['name'])} | {cell(r['target'])} | {cell(r['reason'])} |" for r in group]
        lines += ["", "열 뜻  ", "- 혜택 ID: 카드 혜택 안내의 항목 번호. 앞의 D2-C001이 카드상품 키임  ",
                  "- 혜택 이름, 대상 문장: 인덱싱이 원문에서 뽑은 값. 대상 문장이 업종을 정하는 근거임  ",
                  "- 까닭: LLM이 그 업종을 고른 까닭 한 문장  ", ""]
        number += 1
    lines += [f"## {number}. 미정 {len(undecided)}건", "",
              "LLM이 하나로 정하지 못한 혜택임. 사람이 업종 값을 정하거나 「잇지 않음」으로 두어야 함. "
              "아무것도 정하지 않으면 확정 전 상태로 남고 그래프에 잇지 않음.", "",
              "| 혜택 ID | 혜택 이름 | 대상 문장 | 가까운 후보 | 까닭 |", "|---|---|---|---|---|"]
    lines += [f"| {r['benefit_id']} | {cell(r['name'])} | {cell(r['target'])} | {cell(', '.join(r.get('near') or []))} | {cell(r['reason'])} |"
              for r in sorted(undecided, key=lambda r: r["benefit_id"])]
    lines += ["", "열 뜻  ", "- 가까운 후보: LLM이 가깝다고 본 업종(최대 2개). 없으면 어느 업종에도 분명히 들지 않는다고 본 것  ",
              "- 까닭: 정하지 못한 까닭. 「대상 문장이 추출되지 않음」은 인덱싱에서 대상 문장이 비어 LLM에 묻지 않은 것  ", "",
              "## 함께 볼 파일", "",
              "- 결정 파일 틀: `output/category_decision_draft.json`(후보가 분명한 항목은 후보 값으로 채워 둠. 고칠 곳만 고치면 됨)  ",
              "- 후보 원본: `common/output/category_candidates.json`  ",
              "- 업종 값 목록: `inputs/value_lists.json`  ", ""]
    REVIEW.parent.mkdir(parents=True, exist_ok=True)
    REVIEW.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    write_json(DECISION, {"decided_by": "(확정한 사람)", "date": date.today().isoformat(),
                          "note": "값은 업종 8개 중 하나 또는 「잇지 않음」. 줄을 지우면 확정 전(needs_review)으로 남음",
                          "decisions": {r["benefit_id"]: r["category"] for r in sorted(clear, key=lambda r: r["benefit_id"])}})
    print(f"검토 파일 {REVIEW.relative_to(ttl_write.PROJECT).as_posix()}: 검토할 혜택 {len(rows)}건(후보 분명 {len(clear)}, 미정 {len(undecided)}, "
          f"그중 대상 문장 없음 {len(no_target)}), 앞서 정한 {len(settled)}건은 뺌")
    print("후보 업종별:", {v: sum(1 for r in clear if r["category"] == v) for v in values})


if __name__ == "__main__":
    main()
