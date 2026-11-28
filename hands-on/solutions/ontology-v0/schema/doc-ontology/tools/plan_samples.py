"""3단계: 추출 단위를 제안하고, 묶음마다 발견용 표본과 시험용 표본을 고름.

- 제안 근거: 문서 종류마다 고정 시드로 고른 표본 청크(최대 30건)의 제목 줄 수를 셈
- 나누기: 고정 시드로 청크 순서를 정하고, 청크를 하나씩 나눠 시험용을 먼저 채운 뒤 발견용을 채움.
  둘 다 차면 남은 청크는 나누지 않음
실행: python tools/plan_samples.py
만드는 파일: sample_plan.json, {문서 종류}/units.json(추출 단위를 쓰는 문서 종류만)
"""

from __future__ import annotations

import collections
import random

from common import BASE_DIR, DOC_TYPES, SEED, load_chunks, load_decisions, write_json
from units import RULES, benefit_kind, count_headings, split_chunk, BENEFIT

LOOK = 30  # 제안 근거로 보는 표본 청크 수의 상한
# 묶음별 건수: test는 시험용, start와 cap은 발견용의 시작 수와 상한
QUOTA = {
    "regulation": {"조항": {"test": 27, "start": 10, "cap": 30}, "조항 아님": {"test": 3, "start": 0, "cap": 0}},
    "benefit_guide": {**{k: {"test": 8, "start": 10, "cap": 30} for k in ("할인", "적립", "캐시백", "이용 기준", "그 밖")},
                      "항목 아님": {"test": 5, "start": 0, "cap": 0}},
    "consult_log": {"*": {"test": 4, "start": 10, "cap": 30}},
}
BUNDLE_BASIS = {
    "regulation": {"basis": "제목 줄이 있는지(조항, 조항 아님)",
                   "reason": "메타데이터가 page뿐이라 묶을 필드가 없음. 장(7개)으로 나누면 묶음마다 조항이 4 ~ 10개뿐이라 "
                             "표본을 시험용과 발견용으로 가를 수 없음. 표지와 각주는 역량 질문의 답이 없어야 하는 단위라 따로 묶어 시험용에만 씀"},
    "benefit_guide": {"basis": "혜택 제목의 낱말(할인, 적립, 캐시백, 이용 기준, 그 밖)과 제목 줄이 없는 청크(항목 아님)",
                      "reason": "메타데이터 card_id와 card_name은 값이 64종이라 묶음으로 쓰기에 너무 많음. 혜택 종류에 따라 B1(얼마를 주는가)의 "
                                "답 모양이 비율, 금액, 횟수로 갈리고 B5(이용 제한)의 답은 「이용 기준」 항목에만 있어, 제목 낱말로 나눠야 "
                                "드문 종류가 표본에서 빠지지 않음"},
    "consult_log": {"basis": "원본 파일 이름의 고객군(6개)",
                    "reason": "A1(고객군마다 어떤 주제의 불만이 나왔는가)이 고객군으로 무리를 나눔. 고객군마다 상담이 8건씩이라 고르게 뽑을 수 있음. "
                              "channel(3개)은 어느 역량 질문에도 쓰이지 않아 기준으로 삼지 않음"},
}
METADATA_NODE_CANDIDATES = [
    {"doc_type": "consult_log", "field": "source(파일 이름의 고객군)", "values": 6, "use": "A1이 고객군으로 무리를 나눔. 값 목록의 고객군 6개와 같은 분류"},
    {"doc_type": "consult_log", "field": "member_pseudo_id", "values": 12, "use": "X2와 건너가는 지점 P5(회원). 같은 회원의 상담을 이음"},
    {"doc_type": "consult_log", "field": "record_id", "values": 48, "use": "상담 한 건을 가려내는 키. C5(앞선 상담과 이어짐)"},
    {"doc_type": "consult_log", "field": "consult_date", "values": 34, "use": "첫 상담과 가장 최근 상담을 가리는 날짜. 묶는 값이 아니라 속성 후보"},
    {"doc_type": "benefit_guide", "field": "card_id, card_name", "values": 64, "use": "건너가는 지점 P3, P6(카드 상품). 정형 DB의 Product.product_id와 범위가 같음"},
    {"doc_type": "benefit_guide", "field": "혜택 제목 줄의 혜택 ID", "values": 270, "use": "혜택 한 건을 가려내는 키. 메타데이터가 아니라 제목 줄에서 읽음"},
    {"doc_type": "regulation", "field": "조 제목 줄의 조 번호와 제목", "values": 52, "use": "조항 하나를 가려내는 키. R4(다른 조항을 가리킴)와 M1. 제목 줄에서 읽음"},
]


def look_at_sample(doc_type: str, chunks: list[dict]) -> dict:
    """제안 근거: 표본 청크마다 제목 줄 수와 나온 단위 수를 셈."""
    rng = random.Random(SEED)
    sample = sorted(rng.sample(chunks, min(LOOK, len(chunks))), key=lambda c: c["id"])
    heading_counts, produced, empty = collections.Counter(), 0, []
    for chunk in sample:
        heading_counts[count_headings(doc_type, chunk["text"])] += 1
        units, why = split_chunk(doc_type, chunk)
        produced += len(units)
        if not units:
            empty.append({"chunk_id": chunk["id"], "reason": why})
    return {"chunks_seen": len(sample), "heading_count_distribution": dict(sorted(heading_counts.items())),
            "units_produced": produced, "chunks_without_units": empty}


def count_bundles(doc_type: str, chunks: list[dict]) -> dict:
    """묶음별 단위 수를 셈(제목 줄만 세고 단위 파일은 만들지 않음)."""
    counts = collections.Counter()
    for chunk in chunks:
        if doc_type == "benefit_guide":
            titles = [BENEFIT.match(l).group(2) for l in chunk["text"].split("\n") if BENEFIT.match(l)]
            for title in titles:
                counts[benefit_kind(title)] += 1
            if not titles:
                counts["항목 아님"] += 1
        else:
            for unit in split_chunk(doc_type, chunk)[0]:
                counts[unit["bundle"]] += 1
    return dict(counts)


def assign(doc_type: str, chunks: list[dict], seed: int) -> dict:
    """청크를 시드 순서로 하나씩 나눠 시험용을 먼저, 그다음 발견용을 채움."""
    order = chunks[:]
    random.Random(seed).shuffle(order)
    quota = QUOTA[doc_type]
    test, discover, used_units, split_ids, seen = collections.defaultdict(list), collections.defaultdict(list), {}, [], set()

    def room(bundle: str) -> dict:
        return quota.get(bundle) or quota["*"]

    def full() -> bool:
        if "*" in quota:
            return False  # 묶음 이름을 미리 모르므로 청크를 모두 봄(상담 기록은 46건뿐)
        return all(len(test[b]) >= q["test"] and len(discover[b]) >= q["cap"] for b, q in quota.items())

    for chunk in order:
        if full():
            break
        units, _ = split_chunk(doc_type, chunk)
        split_ids.append(chunk["id"])
        for unit in units:
            if unit["unit_id"] in seen:  # 겹친 청크 때문에 같은 단위가 두 번 나오면 하나만 남김
                used_units[unit["unit_id"]]["chunk_ids"].append(chunk["id"])
                continue
            seen.add(unit["unit_id"])
            q = room(unit["bundle"])
            if len(test[unit["bundle"]]) < q["test"]:
                test[unit["bundle"]].append(unit["unit_id"])
            elif len(discover[unit["bundle"]]) < q["cap"]:
                discover[unit["bundle"]].append(unit["unit_id"])
            else:
                continue  # 나눴지만 표본에 쓰지 않는 단위
            used_units[unit["unit_id"]] = unit
    return {"test": dict(test), "discover": dict(discover), "units": used_units, "split_chunk_ids": sorted(split_ids),
            "chunks_not_split": len(chunks) - len(split_ids)}


def main() -> None:
    excluded = [p["chunk_id"] for p in load_decisions()["input"]["pii_remaining"]]
    plan = {"seed": SEED, "excluded_chunks": {"ids": excluded, "reason": "생일이 가려지지 않아 표본에서 뺌(1단계 승인)"},
            "metadata_node_candidates": METADATA_NODE_CANDIDATES, "doc_types": {}}
    for index, doc_type in enumerate(DOC_TYPES):
        chunks = [c for c in load_chunks(doc_type) if c["id"] not in excluded]
        result = assign(doc_type, chunks, SEED + index)
        bundles = count_bundles(doc_type, chunks)
        rows = {}
        for bundle in sorted(bundles):
            q = QUOTA[doc_type].get(bundle) or QUOTA[doc_type]["*"]
            n_disc = len(result["discover"].get(bundle, []))
            rows[bundle] = {"units": bundles[bundle], "test": len(result["test"].get(bundle, [])),
                            "discover_start": min(q["start"], n_disc), "discover_cap": n_disc}
        plan["doc_types"][doc_type] = {
            "chunks": len(chunks), "extraction_unit": RULES[doc_type], "sample_look": look_at_sample(doc_type, chunks),
            "bundle_basis": BUNDLE_BASIS[doc_type], "bundles": rows,
            "units_total": sum(bundles.values()),
            "test_total": sum(r["test"] for r in rows.values()), "discover_total": sum(r["discover_cap"] for r in rows.values()),
            "test": result["test"], "discover": result["discover"],
            "split_chunk_ids": result["split_chunk_ids"], "chunks_not_split": result["chunks_not_split"],
            "seed": SEED + index,
        }
        if doc_type != "consult_log":
            write_json(BASE_DIR / doc_type / "units.json", {"doc_type": doc_type, "rule": RULES[doc_type],
                                                            "units": list(result["units"].values())})
        d = plan["doc_types"][doc_type]
        print(f"\n== {doc_type}: 청크 {d['chunks']}, 단위 {d['units_total']}, 시험용 {d['test_total']}, 발견용 {d['discover_total']}, "
              f"나눈 청크 {len(d['split_chunk_ids'])}, 안 나눈 청크 {d['chunks_not_split']}")
        print("   표본 청크:", d["sample_look"])
        for bundle, row in rows.items():
            print("   ", bundle, row)
        overlap = {u for v in result["test"].values() for u in v} & {u for v in result["discover"].values() for u in v}
        print("   시험용과 발견용 겹침:", len(overlap))
    write_json(BASE_DIR / "sample_plan.json", plan)


if __name__ == "__main__":
    main()
