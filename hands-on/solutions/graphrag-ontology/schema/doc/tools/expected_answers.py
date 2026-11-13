"""7단계: 시험용 표본마다 역량 질문별 기대 답을 준비함 → {doc}/expected_answers.json.

기존 정답표가 있으면 그것을 쓰고(상담: 대조표의 칸을 질문에 대응), 없는 문서 종류나 빠진 질문만 LLM이 초안을 씀.
초안 규칙: 답은 원문 문장을 그대로 옮기고, 원문 위치(몇 번째 줄이나 표 항목)를 적고, 답이 없으면 "없음".
실행: python tools/expected_answers.py [문서종류 ...]
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from common import BASE, decisions, load_units, load_json, make_llm, save_json

# 상담 정답표 칸 → 역량 질문(정답표가 가진 칸만 대응함)
CONSULT_MAP = {"C1": ["complaint_cause"], "C2": ["proposal"], "C3": ["proposal_decision", "proposal_reason"],
               "C4": ["hold_condition"], "C5": ["previous_record_id"]}


def from_answer_table(doc: str, test_ids: list[str], chunks: dict) -> dict:
    files = decisions()["input"]["answer_tables"].get(doc, [])
    table = {}
    for f in files:
        p = Path(f)
        rows = ([json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]
                if p.suffix == ".jsonl" else json.loads(p.read_text(encoding="utf-8")))
        for r in rows:
            table.setdefault(r["record_id"], {}).update(r)
    out = {}
    for cid in test_ids:
        rid = chunks[cid]["metadata"].get("record_id")
        row = table.get(rid)
        if row is None:
            continue
        ans = {}
        for q, cols in CONSULT_MAP.items():
            vals = [str(row[c]) for c in cols if row.get(c)]
            ans[q] = {"answer": " / ".join(vals) if vals else "없음", "location": "정답표 " + ", ".join(cols),
                      "source": "기존 정답표"}
        out[cid] = ans
    return out


async def draft(llm, doc: str, cid: str, text: str) -> dict:
    qs = load_json("competency_questions.json")[doc]
    prompt = ("아래 문서 청크만 보고 질문마다 기대 답을 쓰세요. 규칙: 답은 청크의 원문 문장이나 표 칸을 그대로 옮김(요약하거나 "
              "바꿔 쓰지 않음). 답이 여럿이면 가장 대표적인 것 1 ~ 3개를 ' / '로 이음. 청크에 답이 없으면 answer를 \"없음\"으로 "
              "씀. location에는 원문 위치(예: 표의 항목 이름, 조항 번호)를 씀. JSON으로만 답함: "
              "{\"<질문 id>\": {\"answer\": \"...\", \"location\": \"...\"}}\n\n<questions>\n"
              + "\n".join(f"{q['id']}: {q['question']}" for q in qs) + f"\n</questions>\n\n<chunk>\n{text}\n</chunk>")
    res = await llm.ainvoke(prompt)
    d = json.loads(res.content)
    return {q["id"]: {**d.get(q["id"], {"answer": "없음", "location": ""}), "source": "LLM 초안"} for q in qs}


async def main() -> None:
    plan = load_json("sample_plan.json")
    chunks = {c["id"]: c for c in load_units()}
    llm = make_llm()
    for doc in sys.argv[1:] or decisions()["input"]["doc_types"]:
        test_ids = [cid for g in plan["docs"][doc]["groups"].values() for cid in g["test"]]
        out = from_answer_table(doc, test_ids, chunks)
        # 8단계 추출과 같은 입력(메타데이터 머리줄 + 본문)을 보고 초안을 써야 머리줄에서 채우는 답도 공정하게 셈
        fields = load_json(f"{doc}/schema_spec.json").get("metadata_header", [])
        for cid in test_ids:
            if cid not in out:
                md = chunks[cid]["metadata"]
                head = " | ".join(f"{f}: {md[f]}" for f in fields if md.get(f) not in (None, ""))
                out[cid] = await draft(llm, doc, cid, (head + "\n" if head else "") + chunks[cid]["text"])
                print(f"[{doc}] {cid} 초안", flush=True)
        save_json(f"{doc}/expected_answers.json", {"doc": doc, "answers": out})
        has = {q: sum(1 for a in out.values() if a[q]["answer"] != "없음") for q in next(iter(out.values()))}
        print(f"[{doc}] 시험용 {len(out)}건, 질문별 답 있음 {has}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
