"""시험용 표본 청킹 결과 두 개를 만듦(LLM 호출을 줄이려고 전체 218개 대신 일부만 씀).

- data/sample-chunks.json: 약관 청크 2개(조항이 겹치는 이웃 청크), 혜택 안내 청크 4개(한빛 가족돌봄), 상담 기록 청크 4개
- data/sample-chunks-v2.json: 증분 색인 시험용. 상담 기록 1건의 본문을 고치고(chunk_id가 바뀜) 혜택 안내 청크 1개를 뺌

실행: python tools/make_sample.py
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config  # noqa: E402
from common import load_json, save_json, sha256_text  # noqa: E402

FOLLOW_PAIR = ("C-20260501-003", "C-20260302-002")  # 앞 상담을 FOLLOWS로 가리키는 상담과 그 앞 상담(K5 병합 확인용)
EDIT_RECORD = "C-20260501-003"


def main() -> None:
    chunks = load_json(config.DEFAULT_CHUNKS)
    order = lambda c: c["metadata"].get("chunk_index", 0)
    d1 = sorted([c for c in chunks if c["metadata"].get("doc_key") == "D1"], key=order)
    # 혜택 안내는 카드명이 있는 청크를 골라야 카드명 사전과 별칭(S2)이 실제로 만들어짐
    d2 = sorted([c for c in chunks if c["metadata"].get("card_name") == "한빛 가족돌봄"], key=order)
    d3 = [c for c in chunks if c["metadata"].get("doc_key") == "D3"]
    pick_d3 = [c for c in d3 if c["metadata"].get("record_id") in FOLLOW_PAIR]
    pick_d3 += [c for c in d3 if c not in pick_d3][: 4 - len(pick_d3)]
    sample = d1[4:6] + d2[:4] + pick_d3
    save_json(config.DATA / "sample-chunks.json", sample)

    v2 = []
    for c in sample:
        if c is d2[3]:
            continue  # 혜택 안내 청크 하나를 뺌(문서 D2가 바뀜)
        c = copy.deepcopy(c)
        if c["metadata"].get("record_id") == EDIT_RECORD:  # 상담 본문을 고치면 chunk_id 규칙대로 chunk_id도 바뀜
            c["text"] += "\n상담사: 다음 명세서가 나오면 지역 표시를 다시 함께 확인해 드리겠습니다."
            c["index_text"] = ""
            c["text_hash"] = sha256_text(c["text"])
            key, _old, no = c["chunk_id"].rsplit("_", 2)
            c["chunk_id"] = f"{key}_{c['text_hash'][:16]}_{no}"
            c["metadata"] = {**c["metadata"], "chunk_id": c["chunk_id"]}
        v2.append(c)
    save_json(config.DATA / "sample-chunks-v2.json", v2)
    print(f"표본 {len(sample)}개(약관 2, 혜택 4, 상담 {len(pick_d3)}) → data/sample-chunks.json")
    print(f"증분용 {len(v2)}개(상담 {EDIT_RECORD} 본문 수정, 혜택 청크 1개 뺌) → data/sample-chunks-v2.json")


if __name__ == "__main__":
    main()
