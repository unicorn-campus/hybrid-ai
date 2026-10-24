"""3단계 추출 단위 제안 근거: 표본 청크(고정 시드로 고른 최대 30건)에 제목 꼴 단위가 몇 개 들었는지 셈.

문서 전체를 나누지 않고 표본 청크만 봄(원본이 많아도 비용이 늘지 않게). 규칙은 decisions.json의
input.extraction_units.{doc}(heading, body_start, drop_lines)에 적은 후보 규칙을 씀.
실행: python tools/analyze_units.py {doc} [표본 수] → output/units_{doc}.json
"""

from __future__ import annotations

import json
import random
import sys
from collections import Counter

from common import BASE, _split_by_heading, decisions, load_chunks, split_chunks

SEED = 20261018


def main() -> None:
    doc = sys.argv[1]
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 30
    rule = decisions()["input"].get("extraction_units", {}).get(doc)
    chunks = [c for c in load_chunks() if c["doc_type"] == doc]
    if not rule:
        print(f"{doc}: 추출 단위 규칙 없음 → 청크를 그대로 단위로 씀")
        return
    sample = sorted(chunks, key=lambda c: c["id"])
    random.Random(f"{SEED}:analyze:{doc}").shuffle(sample)
    sample = sample[:n]
    per_chunk = [{"chunk_id": c["id"], "section_label": c["metadata"].get("section_label"),
                  "units": len(_split_by_heading(c, rule))} for c in sample]
    units = split_chunks(sample, rule)
    sizes = sorted(len(u["text"]) for u in units) or [0]
    out = {"doc": doc, "rule": rule, "chunks_total": len(chunks), "chunks_sampled": len(sample),
           "per_chunk": per_chunk, "units_before_dedupe": sum(p["units"] for p in per_chunk), "units": len(units),
           "chunks_without_unit": [p["chunk_id"] for p in per_chunk if p["units"] == 0],
           "chunks_with_many_units": sum(1 for p in per_chunk if p["units"] >= 2),
           "unit_chars": {"min": sizes[0], "median": sizes[len(sizes) // 2], "max": sizes[-1]},
           "units_in_two_chunks": sum(1 for u in units if len(u["parent_chunk_ids"]) > 1)}
    (BASE / "output").mkdir(exist_ok=True)
    (BASE / f"output/units_{doc}.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in out.items() if k != "per_chunk"}, ensure_ascii=False, indent=1))
    print("청크별 단위 수:", Counter(p["units"] for p in per_chunk))


if __name__ == "__main__":
    main()
