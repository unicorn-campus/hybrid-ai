"""개선 2: 업종 매핑표 초안 만들기. 혜택마다 가맹점 업종 8개 중 하나를 LLM이 후보로 내고, 사람이 확정함.

거래 쪽 업종은 DB의 값 8개이고 혜택 쪽은 안내서의 문장이라, 둘을 같은 업종 개념으로 맞추는 표가 필요함.
LLM은 후보와 까닭만 냄. 분명하지 않으면 「미정」으로 두게 해서 사람이 정할 목록으로 남김.

실행(schema/common 폴더에서, graphrag-ontology 가상환경을 활성화한 뒤):
  python tools/draft_category_map.py                  후보만 만듦 → output/category_candidates.json
  python tools/draft_category_map.py --auto-approve   후보를 그대로 승인본으로 저장함(실습용. 미정은 needs_review로 남김)
입력: 인덱서 활성 세대의 prepared-chunks.json(혜택 안내 청크). --chunks로 다른 파일을 줄 수 있음
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Literal

from dotenv import dotenv_values
from langchain_core.prompts import ChatPromptTemplate
from langchain_groq import ChatGroq
from pydantic import BaseModel, Field

sys.stdout.reconfigure(encoding="utf-8")
BASE = Path(__file__).resolve().parent.parent  # schema/common
ROOT_DIR = BASE.parents[4]  # common → schema → graphrag-ontology → solutions → hands-on → 저장소 루트
INDEXER_DATA = BASE.parents[1] / "indexer" / "data"
SECRETS_PATH = ROOT_DIR / "secrets" / ".env"
LLM_MODEL = "openai/gpt-oss-120b"
AUTO = "자동 승인(실습용. 강사 검토 전, 2026-11-13)"

BENEFIT_HEADER = re.compile(r"^(D\d-C\d{3}-B\d{2}) \| (.+)$")  # 예: D2-C021-B04 | 교육 할인
TARGET_LABELS = ("대상·채널", "사용처")  # 이 줄 다음 줄이 혜택의 대상(원문 표기 그대로)

Category = Literal["식비", "쇼핑", "교통", "주유", "여행", "해외", "생활", "교육", "미정"]


class Candidate(BaseModel):
    benefit_id: str = Field(description="혜택 ID. 입력에 있는 값 그대로")
    category: Category = Field(description="업종 8개 중 하나. 분명하지 않으면 미정")
    closest: list[str] = Field(description="미정일 때 가까운 업종 후보(0 ~ 2개). 미정이 아니면 빈 목록")
    reason: str = Field(description="고른 까닭 한 줄")


class CandidateList(BaseModel):
    items: list[Candidate]


PROMPT = ChatPromptTemplate.from_messages([
    ("system", "너는 카드 혜택을 가맹점 업종에 맞추는 분석가다. 업종은 주어진 8개뿐이다. "
               "혜택의 대상이 한 업종에 분명히 들어갈 때만 그 업종을 고른다. 8개에 딱 맞는 것이 없거나 둘 이상에 걸치면 "
               "「미정」으로 두고 가까운 후보를 적는다. 지어내지 않는다."),
    ("human", "업종 정의\n{definition}\n\n혜택 목록(혜택 ID | 이름 | 대상)\n{benefits}\n\n혜택마다 업종을 하나씩 정한다."),
])


def parse_benefits(chunks: list[dict]) -> list[dict]:
    """혜택 안내 청크의 본문에서 혜택 ID, 이름, 대상 줄을 꺼냄. 같은 혜택이 여러 청크에 걸쳐도 한 번만 남김."""
    found = {}
    for chunk in chunks:
        if chunk["doc_type"] != "benefit_guide":
            continue
        lines = chunk["text"].splitlines()
        current = None
        for index, line in enumerate(lines):
            header = BENEFIT_HEADER.match(line.strip())
            if header:
                current = found.setdefault(header.group(1), {"benefit_id": header.group(1), "name": header.group(2),
                                                             "target": ""})
            elif current is not None and line.strip() in TARGET_LABELS and index + 1 < len(lines):
                current["target"] = current["target"] or lines[index + 1].strip()
    return sorted(found.values(), key=lambda b: b["benefit_id"])


def main() -> None:
    parser = argparse.ArgumentParser(description="업종 매핑표 초안(LLM 후보)")
    parser.add_argument("--chunks", default=None, help="prepared-chunks.json 경로. 없으면 인덱서 활성 세대의 파일")
    parser.add_argument("--auto-approve", action="store_true", help="후보를 승인본으로 저장함(실습용)")
    args = parser.parse_args()

    concepts = json.loads((BASE / "concepts.json").read_text(encoding="utf-8"))
    category = next(c for c in concepts["concepts"] if c["name"] == "업종")
    if args.chunks:
        chunk_path = Path(args.chunks)
    else:
        active = json.loads((INDEXER_DATA / "active_generation.json").read_text(encoding="utf-8"))
        chunk_path = INDEXER_DATA / "generations" / active["generation"] / "prepared-chunks.json"
    benefits = parse_benefits(json.loads(chunk_path.read_text(encoding="utf-8")))
    print(f"혜택 {len(benefits)}개를 읽음: {chunk_path}")

    key = (dotenv_values(SECRETS_PATH).get("GROQ_API_KEY") or "").strip()
    if not key:
        raise SystemExit(f"{SECRETS_PATH}에 GROQ_API_KEY=... 줄이 필요함")
    llm = ChatGroq(model=LLM_MODEL, api_key=key, temperature=0, max_retries=2, reasoning_effort="medium")
    chain = PROMPT | llm.with_structured_output(CandidateList, method="json_schema", strict=True)
    known = {b["benefit_id"] for b in benefits}
    candidates = {}
    for start in range(0, len(benefits), 30):  # 한 번에 30개씩 물음
        batch = benefits[start:start + 30]
        listing = "\n".join(f"{b['benefit_id']} | {b['name']} | {b['target']}" for b in batch)
        result = chain.invoke({"definition": f"{category['definition']} 값: {', '.join(category['values'])}",
                               "benefits": listing})
        for item in result.items:
            if item.benefit_id in known:  # 입력에 없는 ID를 지어내면 버림
                candidates[item.benefit_id] = item.model_dump()
    missing = sorted(known - set(candidates))
    for benefit in benefits:
        candidates.setdefault(benefit["benefit_id"], {"benefit_id": benefit["benefit_id"], "category": "미정",
                                                      "closest": [], "reason": "LLM이 답하지 않음"})
        candidates[benefit["benefit_id"]].update(name=benefit["name"], target=benefit["target"])

    out = BASE / "output" / "category_candidates.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"model": LLM_MODEL, "source": str(chunk_path.name), "candidates": candidates},
                              ensure_ascii=False, indent=2), encoding="utf-8")
    undecided = [c for c in candidates.values() if c["category"] == "미정"]
    print(f"후보 저장: {out} (업종을 고른 혜택 {len(candidates) - len(undecided)}개, 미정 {len(undecided)}개, "
          f"LLM이 빠뜨린 혜택 {len(missing)}개)")
    for c in undecided:
        print(f"  미정: {c['benefit_id']} {c['name']} / 가까운 후보 {c['closest']} / {c['reason']}")

    if not args.auto_approve:
        print("다음: 후보를 사람이 검토해 category_map_approved.json으로 확정함(같은 꼴, status는 approved 또는 needs_review)")
        return
    approved = {"version": "1", "approved_by": AUTO, "categories": category["values"], "benefits": {}}
    for benefit_id, c in sorted(candidates.items()):
        decided = c["category"] != "미정"
        approved["benefits"][benefit_id] = {
            "name": c["name"], "target": c["target"], "category": c["category"] if decided else None,
            "status": "approved" if decided else "needs_review", "closest": c["closest"], "reason": c["reason"]}
    path = BASE / "category_map_approved.json"
    path.write_text(json.dumps(approved, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"승인본 저장: {path} ({AUTO})")


if __name__ == "__main__":
    main()
