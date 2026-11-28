"""7단계 [단계 ④ 준비]: 시험용 표본의 기대 답 뼈대를 만들고, 채운 초안을 검사함.

- skeleton: 시험용 단위마다 역량 질문별 칸을 만듦. 머리줄 값이나 본문 규칙으로 정해지는 답(키, 고객군, 가리키는 조항과 상담)은
  스크립트가 채우고(by=규칙), 글로 답하는 칸은 비워 둠(by=AI 초안, answer=null). 같이 볼 단위 글을 output/test_units.json에 씀
- check: 채운 초안을 검사함. 원문 답은 원문에 그대로 있는지(공백과 줄바꿈을 없애고 비교), 업종은 허용 값 안인지,
  빈칸이 남았는지, 규칙 답을 바꾸지 않았는지 셈
실행: python tools/expected_answers.py skeleton | check
만드는 파일: {문서 종류}/expected_answers.json, {문서 종류}/output/test_units.json, output/expected_check.json
"""

from __future__ import annotations

import re
import sys

from common import BASE_DIR, DOC_TYPES, load_chunks, read_json, write_json
from units import consult_card, header_of, segment_canonical, split_chunk

# 문서 종류별 칸: (역량 질문 번호, 답의 꼴, 채우는 쪽)
# 답의 꼴: quote(원문 조각 하나), quotes(원문 조각 목록), names(주제 이름 목록), proposals(제안 목록),
#          ids(규칙으로 찾은 번호 목록), value(규칙으로 정한 값 하나), category(업종 값 하나)
FIELDS = {
    "regulation": [("R1", "quotes", "AI"), ("R2", "quotes", "AI"), ("R3", "quotes", "AI"), ("R4", "ids", "규칙"), ("M1", "names", "AI")],
    "benefit_guide": [("B1", "quote", "AI"), ("B2", "quotes", "AI"), ("B3", "quotes", "AI"), ("B4", "quote", "AI"),
                      ("B5", "quotes", "AI"), ("M2", "names", "AI"), ("X1", "category", "AI"), ("M3,X3", "value", "규칙")],
    "consult_log": [("C1", "quotes", "AI"), ("C2", "quotes", "AI"), ("C3", "proposals", "AI"), ("C4", "quote", "AI"),
                    ("C5", "ids", "규칙"), ("C6", "quote", "AI"), ("A1", "value", "규칙"), ("M1,M2", "names", "AI"),
                    ("M3", "value", "규칙"), ("X2", "value", "규칙")],
}
ARTICLE_REF = re.compile(r"제\d+조(?:의\d+)?")
RECORD_REF = re.compile(r"C-\d{8}-\d{3}")


def test_units(doc_type: str) -> list[dict]:
    plan = read_json(BASE_DIR / "sample_plan.json")["doc_types"][doc_type]
    ids = [u for bundle in plan["test"].values() for u in bundle]
    path = BASE_DIR / doc_type / "units.json"
    if path.exists():
        pool = {u["unit_id"]: u for u in read_json(path)["units"]}
    else:
        pool = {u["unit_id"]: u for c in load_chunks(doc_type) for u in split_chunk(doc_type, c)[0]}
    return [pool[i] for i in ids]


def rule_answer(doc_type: str, field: str, unit: dict):
    keys, text = unit["keys"], unit["text"]
    if field == "R4":
        if not keys:
            return "없음"
        refs = sorted({r for r in ARTICLE_REF.findall(text) if r != keys["article_no"]}, key=lambda r: [int(x) for x in re.findall(r"\d+", r)])
        return refs or "없음"
    if field == "M3,X3":
        return keys.get("card_id") if keys.get("benefit_id") else "없음"
    if field == "C5":
        return sorted({r for r in RECORD_REF.findall(text) if r != keys["record_id"]}) or "없음"
    if field == "A1":
        return segment_canonical(keys["segment_name"])
    if field == "M3":
        return consult_card(text)[1] or "없음"
    if field == "X2":
        return keys["member_pseudo_id"]
    raise KeyError(field)


def skeleton() -> None:
    for doc_type in DOC_TYPES:
        units = test_units(doc_type)
        no_answer = lambda u: doc_type != "consult_log" and not u["keys"].get("article_no") and not u["keys"].get("benefit_id")
        rows = []
        for unit in units:
            answers = {}
            for field, shape, by in FIELDS[doc_type]:
                if no_answer(unit):  # 표지, 차례, 참고 자료처럼 답이 없어야 하는 단위
                    answers[field] = {"answer": "없음", "location": None, "by": "규칙"}
                elif by == "규칙":
                    answers[field] = {"answer": rule_answer(doc_type, field, unit), "location": "머리줄 또는 본문 규칙", "by": "규칙"}
                else:
                    answers[field] = {"answer": None, "location": None, "by": "AI 초안"}
            rows.append({"unit_id": unit["unit_id"], "bundle": unit["bundle"], "title": unit["title"], "answers": answers})
        write_json(BASE_DIR / doc_type / "expected_answers.json",
                   {"doc_type": doc_type, "status": "draft", "fields": {f: {"shape": s, "by": b} for f, s, b in FIELDS[doc_type]},
                    "units": rows})
        write_json(BASE_DIR / doc_type / "output/test_units.json",
                   [{"unit_id": u["unit_id"], "bundle": u["bundle"], "header": header_of(doc_type, u), "text": u["text"]} for u in units])
        print(doc_type, "시험용 단위", len(rows))


def squash(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


def check() -> None:
    allowed = read_json(BASE_DIR / "inputs/value_lists.json")["lists"]["업종"]["values"]
    report, ok_all = {}, True
    for doc_type in DOC_TYPES:
        data = read_json(BASE_DIR / doc_type / "expected_answers.json")
        texts = {u["unit_id"]: squash(u["text"]) for u in read_json(BASE_DIR / doc_type / "output/test_units.json")}
        units = {u["unit_id"]: u for u in test_units(doc_type)}
        problems, counts = [], {"empty": 0, "not_in_text": 0, "bad_category": 0, "rule_changed": 0, "answered": 0, "none": 0}
        for row in data["units"]:
            text = texts[row["unit_id"]]
            for field, cell in row["answers"].items():
                shape, by = data["fields"][field]["shape"], data["fields"][field]["by"]
                answer = cell["answer"]
                if answer is None:
                    counts["empty"] += 1
                    problems.append(f"{row['unit_id']} {field}: 빈칸")
                    continue
                if answer == "없음" or answer == []:
                    counts["none"] += 1
                    continue
                counts["answered"] += 1
                if by == "규칙" and cell.get("by") == "규칙" and shape in ("ids", "value"):
                    expected = rule_answer(doc_type, field, units[row["unit_id"]]) if units[row["unit_id"]]["keys"] else "없음"
                    if answer != expected:
                        counts["rule_changed"] += 1
                        problems.append(f"{row['unit_id']} {field}: 규칙 답이 바뀜")
                quotes = []
                if shape == "quote":
                    quotes = [answer]
                elif shape == "quotes":
                    quotes = answer
                elif shape == "proposals":
                    quotes = [p["content"] for p in answer] + [p["reason"] for p in answer if p.get("reason")]
                elif shape == "category" and answer not in allowed + ["미정"]:
                    counts["bad_category"] += 1
                    problems.append(f"{row['unit_id']} {field}: 업종 허용 값 밖 {answer}")
                for q in quotes:
                    if squash(q) not in text:
                        counts["not_in_text"] += 1
                        problems.append(f"{row['unit_id']} {field}: 원문에 없음 「{q[:40]}」")
        passed = not any(counts[k] for k in ("empty", "not_in_text", "bad_category", "rule_changed"))
        ok_all &= passed
        report[doc_type] = {"passed": passed, "units": len(data["units"]), **counts, "problems": problems}
        print(doc_type, "통과" if passed else "실패", counts)
        for p in problems[:15]:
            print("   ", p)
    write_json(BASE_DIR / "output/expected_check.json", report)
    sys.exit(0 if ok_all else 1)


if __name__ == "__main__":
    {"skeleton": skeleton, "check": check}[sys.argv[1]]()
