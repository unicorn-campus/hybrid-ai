"""3단계: 승인된 묶음 기준으로 청크를 나누고 발견용 표본과 시험용 표본을 겹치지 않게 뽑음 → sample_plan.json.

순서: 시험용 표본을 먼저 떼어 둔 뒤 남은 청크에서 발견용 순서를 정함. 작은 묶음에서 발견용이 청크를 다 가져가
시험용이 비는 일을 막기 위함. 같은 시드면 다시 돌려도 같은 표본과 순서가 나옴.
실행: python tools/plan_samples.py [문서종류 ...] → 적은 문서 종류만 다시 짜고 나머지는 기존 sample_plan.json을 유지함.
추출 단위 규칙이 있는 문서 종류는 표본으로 뽑힌 청크만 단위(예: 조항)로 나눠 {doc}/units.json에 저장함.
"""

from __future__ import annotations

import random
import re
import sys
from collections import defaultdict

from common import BASE, decisions, load_chunks, load_json, record, save_json, split_chunks

SEED = 20261018
# 문서 종류마다 묶음 기준(규칙)과 근거. AI 제안을 자동 승인한 내용
RULES = {
    "regulation": {
        "basis": "묶음 하나(조항 단위 전체)",
        "why": "추출 단위를 조항으로 바꿈(조항 51개). 값이 2 ~ 10개인 메타데이터 필드가 없고 장(章) 정보도 조항 단위에 없어 "
               "묶음을 나누지 않음. 조항마다 답이 있는 질문이 달라 답이 없어야 하는 단위가 자연히 섞임",
        "fn": lambda md: "약관 조항 전체",
    },
    "benefit_guide": {
        "basis": "section_label 값의 모양",
        "why": "값이 2 ~ 10개인 필드가 없어 절 제목 꼴로 나눔. 혜택 상세(D2-C000-B00)에는 B1 ~ B4 답이, "
               "카드 개요(D2-C000)에는 B5 답이 몰리고, 공통 안내와 참고 카드(타사)는 답이 없어야 하는 문서가 될 수 있음",
        "fn": lambda md: ("혜택 상세" if re.match(r"D2-C\d+-B\d+", md.get("section_label") or "")
                          else "참고 카드" if "참고 카드" in (md.get("section_label") or "")
                          else "카드 개요" if re.match(r"D2-C\d+", md.get("section_label") or "")
                          else "공통 안내"),
    },
    "consult_log": {
        "basis": "source(상담 시나리오 파일)",
        "why": "값 6개, 묶음마다 8건으로 고름. 시나리오마다 불만 주제와 제안 반응(수용, 거절, 보류)이 달라 "
               "C1 ~ C4 답이 나오는 무리가 갈림. channel(3개)은 질문 답과 관계가 적음",
        "fn": lambda md: md.get("source"),
    },
}
# 문서 종류마다 시험용 목표 건수와 발견용 기본값(시작, 상한)
TEST_TARGET = {"regulation": 30, "benefit_guide": 40, "consult_log": 18}
START, CAP = 10, 30


def split_even(groups: dict[str, list], total: int) -> dict[str, int]:
    """시험용 건수를 묶음별로 고르게 나눔. 묶음마다 최소 1건은 발견용으로 남김."""

    n = {g: 0 for g in groups}
    while sum(n.values()) < total:
        open_ = [g for g in groups if n[g] < len(groups[g]) - 1]
        if not open_:
            break
        g = min(open_, key=lambda x: (n[x] / len(groups[x]), -len(groups[x])))
        n[g] += 1
    return n


def plan_split_doc(doc: str, groups: dict[str, list], chunks: dict, unit_rule: dict, rng) -> tuple[dict, list]:
    """추출 단위 규칙이 있는 문서 종류: 청크 순서를 먼저 정하고, 그 순서대로 필요한 단위 수가 찰 때까지만 청크를 나눔.

    시험용 단위를 먼저 채우고 발견용은 그 뒤 청크에서 채움. 청크가 겹쳐 같은 단위가 양쪽에 나올 수 있어
    시험용에 이미 있는 단위 번호는 발견용에서 뺌. 쓰지 않은 청크는 나누지 않음.
    """

    # 목표는 단위 수라 청크 수로 자르지 않음. 묶음별 몫은 청크 수에 비례해 나눔
    total = sum(len(v) for v in groups.values())
    test_n = {g: TEST_TARGET[doc] * len(ids) // total for g, ids in groups.items()}
    for g in sorted(groups, key=lambda x: -len(groups[x]))[: TEST_TARGET[doc] - sum(test_n.values())]:
        test_n[g] += 1
    doc_groups, units, split_ids = {}, {}, []
    for g, ids in groups.items():
        order = ids[:]
        rng.shuffle(order)
        test, disc, pos = [], [], 0
        while len(test) < test_n[g] and pos < len(order):
            split_ids.append(order[pos])
            for u in split_chunks([chunks[order[pos]]], unit_rule):
                if u["id"] not in units and len(test) < test_n[g]:
                    units[u["id"]] = u
                    test.append(u["id"])
            pos += 1
        while len(disc) < CAP and pos < len(order):
            split_ids.append(order[pos])
            for u in split_chunks([chunks[order[pos]]], unit_rule):
                if u["id"] not in units and len(disc) < CAP:
                    units[u["id"]] = u
                    disc.append(u["id"])
            pos += 1
        rng.shuffle(disc)  # 같은 청크에서 나온 단위가 잇달아 들어가지 않게 섞음
        doc_groups[g] = {"chunks": len(ids), "chunks_split": order[:pos], "test": test, "discovery_order": disc,
                         "discovery_start": min(START, len(disc)), "discovery_cap": min(CAP, len(disc))}
    total_split = len(split_ids)
    total_chunks = sum(len(v) for v in groups.values())
    test_total = sum(len(v["test"]) for v in doc_groups.values())
    note = (f"청크 {total_chunks}건 중 {total_split}건만 나눔 → 단위 시험용 {test_total}건, "
            f"발견용 {sum(len(v['discovery_order']) for v in doc_groups.values())}건(목표 시험용 30 ~ 50건)"
            + (" 모자람: 청크를 모두 나눠도 단위가 모자람" if test_total < 30 else ""))
    return {"groups": doc_groups, "note": note, "unit_rule": unit_rule}, list(units.values())


def main() -> None:
    unit_rules = decisions()["input"].get("extraction_units", {})
    chunks = load_chunks()
    by_id = {c["id"]: c for c in chunks}
    docs = sys.argv[1:] or decisions()["input"]["doc_types"]
    plan = (load_json("sample_plan.json") if sys.argv[1:] and (BASE / "sample_plan.json").exists()
            else {"seed": SEED, "start_default": f"min({START}, 남은 수)", "cap_default": CAP, "docs": {}})
    rng = random.Random(SEED)
    for doc in docs:
        if sys.argv[1:]:
            rng = random.Random(f"{SEED}:{doc}")  # 한 문서 종류만 다시 짤 때는 그 문서 종류 이름을 붙인 시드로 시작함
        rule = RULES[doc]
        groups = defaultdict(list)
        for c in chunks:
            if c["doc_type"] == doc:
                groups[rule["fn"](c["metadata"])].append(c["id"])  # 묶음은 청크 메타데이터로 나눔
        groups = {g: sorted(ids) for g, ids in sorted(groups.items())}
        doc_plan = {"group_basis": rule["basis"], "why": rule["why"], "groups": {}}
        if doc in unit_rules:
            part, units = plan_split_doc(doc, groups, by_id, unit_rules[doc], rng)
            doc_plan.update(part)
            save_json(f"{doc}/units.json", units)
        else:
            test_n = split_even(groups, TEST_TARGET[doc])
            for g, ids in groups.items():
                order = ids[:]
                rng.shuffle(order)
                test, rest = order[: test_n[g]], order[test_n[g]:]
                doc_plan["groups"][g] = {"chunks": len(ids), "test": test, "discovery_order": rest,
                                         "discovery_start": min(START, len(rest)), "discovery_cap": min(CAP, len(rest))}
            total = sum(len(v) for v in groups.values())
            doc_plan["note"] = (f"청크 {total}건 → 시험용 {sum(test_n.values())}건(목표 30 ~ 50건)"
                                + (" 모자람: 청크가 적어 시험용을 줄임" if sum(test_n.values()) < 30 else ""))
        plan["docs"][doc] = doc_plan
    save_json("sample_plan.json", plan)
    table = []
    for doc, p in ((d, plan["docs"][d]) for d in docs):
        for g, v in p["groups"].items():
            table.append({"doc": doc, "group": g, "chunks": v["chunks"], "chunks_split": len(v.get("chunks_split", [])),
                          "discovery_start": v["discovery_start"], "discovery_cap": v["discovery_cap"],
                          "test": len(v["test"])})
    record("3. 묶음 기준과 표본 계획" + (f"({', '.join(docs)})" if sys.argv[1:] else ""),
           {"seed": SEED if not sys.argv[1:] else {d: f"{SEED}:{d}" for d in docs}, "table": table,
            "notes": {d: plan["docs"][d]["note"] for d in docs},
            "units": {d: unit_rules.get(d, "청크 그대로") for d in docs}})
    for row in table:
        print(row)


if __name__ == "__main__":
    main()
