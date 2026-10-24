"""이 저장소 RAG 인덱싱 예제의 Chroma(collection card_docs) 청크를 v0 입력 꼴(prepared-chunks.json)로 바꿔 저장함.

- Chroma 폴더(hands-on/solutions/rag/indexing/data/chroma)는 읽기만 함. chromadb로 열면 sqlite 파일에 기록이 남을 수 있어
  chroma.sqlite3를 읽기 전용(mode=ro)으로 열고 본문(chroma:document)과 메타데이터만 꺼냄
- 벡터는 꺼내지 않음. Chroma는 Cohere embed-v5.0-fast(2048차원)이고 v0는 KURE-v2(768차원)라 그대로 쓸 수 없음
- chunk_id는 v0 규칙 {문서 키}_{본문 해시 16}_{같은 본문 반복 번호 4}로 새로 만들고 Chroma ID는 메타데이터 chroma_id에 남김.
  문서 키: 약관(D1)과 혜택 안내(D2)는 원천 파일마다 하나, 상담 기록(D3)은 상담 건(record_id)마다 하나
- 메타데이터에 v0가 쓰는 doc_key(D1, D2, D3)와 문서 안 순서 chunk_index를 더함.
  혜택 안내는 스키마 머리줄 칸 product_id를 card_id와 같은 값으로 채움(hybrid-ai-lab 1-a 청크와 같은 규칙)

실행: python tools/export_chroma_chunks.py   (결과: data/chroma-chunks.json)
"""

from __future__ import annotations

import json
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config  # noqa: E402
from common import save_json, sha256_text  # noqa: E402

QUERY = """
SELECT e.embedding_id, m.key, m.string_value, m.int_value, m.float_value, m.bool_value
FROM embeddings e
JOIN segments s ON s.id = e.segment_id
JOIN collections c ON c.id = s.collection
JOIN embedding_metadata m ON m.id = e.id
WHERE c.name = ?
"""


def read_chroma(chroma_dir: Path, collection: str) -> dict[str, dict]:
    """{Chroma ID: {"text": 본문, "metadata": {...}}}. 읽기 전용으로 열어 원본 폴더에 아무것도 쓰지 않음."""

    uri = (chroma_dir / "chroma.sqlite3").resolve().as_uri() + "?mode=ro"
    rows: dict[str, dict] = defaultdict(lambda: {"text": None, "metadata": {}})
    with sqlite3.connect(uri, uri=True) as conn:
        for cid, key, s, i, f, b in conn.execute(QUERY, (collection,)):
            value = next((v for v in (s, i, f) if v is not None), None)
            if value is None and b is not None:
                value = bool(b)
            if key == "chroma:document":
                rows[cid]["text"] = value
            else:
                rows[cid]["metadata"][key] = value
    if not rows:
        raise SystemExit(f"Chroma collection {collection}에 청크가 없음: {chroma_dir}")
    return dict(rows)


def to_prepared(rows: dict[str, dict]) -> list[dict]:
    chunks, seen, order = [], Counter(), Counter()
    for chroma_id in sorted(rows):  # D1-0001, D1-0002, … 순서가 문서 안 순서임
        text, md = rows[chroma_id]["text"], dict(rows[chroma_id]["metadata"])
        doc_key = str(md["source"])[:2]  # D1, D2, D3
        doc_part = md["record_id"] if doc_key == "D3" else sha256_text(md["source"])[:16]
        doc_id = f"{doc_key}_{doc_part}"
        text_hash = sha256_text(text)
        rep = seen[(doc_id, text_hash)]
        seen[(doc_id, text_hash)] += 1
        chunk_id = f"{doc_id}_{text_hash[:16]}_{rep:04d}"
        if md.get("doc_type") == "benefit_guide" and md.get("card_id"):
            md.setdefault("product_id", md["card_id"])
        md.update(doc_key=doc_key, chunk_index=order[doc_id], chroma_id=chroma_id, chunk_id=chunk_id)
        order[doc_id] += 1
        chunks.append({"chunk_id": chunk_id, "text": text, "index_text": "", "metadata": md, "text_hash": text_hash,
                       "metadata_hash": sha256_text(json.dumps(md, ensure_ascii=False, sort_keys=True))})
    return chunks


def main() -> None:
    chunks = to_prepared(read_chroma(config.CHROMA_DIR, config.CHROMA_COLLECTION))
    save_json(config.DEFAULT_CHUNKS, chunks)
    by_type = Counter(c["metadata"].get("doc_type") for c in chunks)
    docs = len({c["chunk_id"].rsplit("_", 2)[0] for c in chunks})
    print(f"Chroma {config.CHROMA_COLLECTION} 청크 {len(chunks)}개(문서 {docs}개, {dict(by_type)}) → "
          f"{config.DEFAULT_CHUNKS.relative_to(config.V0).as_posix()}")


if __name__ == "__main__":
    main()
