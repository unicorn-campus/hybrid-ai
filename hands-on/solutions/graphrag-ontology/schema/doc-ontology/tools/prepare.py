"""1단계: 벡터DB(Chroma)에서 청크를 읽어 사본을 저장하고, 입력 자료(원천 목록 표, 값 목록, 키 값 목록)를 만듦.

벡터DB는 읽기만 함(add, upsert, update, delete, collection 만들기와 지우기를 하지 않음).
실행: python tools/prepare.py  (저장소 루트의 graphrag 가상환경에서)
만드는 파일: chunks_snapshot.json, sources.json, inputs/value_lists.json, inputs/key_values.json, output/input_scan.json
"""

from __future__ import annotations

import collections
import importlib.metadata
import re

import chromadb

from common import BASE_DIR, REPO_ROOT, SNAPSHOT_PATH, rel, sha256_of, write_json

CHROMA_DIR = REPO_ROOT / "hands-on/solutions/rag/indexing/data/chroma"
COLLECTION = "card_docs"
PAGE = 100  # 한 번에 읽는 청크 수(건수가 많아도 나눠 읽게 함)
RDB_SCHEMA = REPO_ROOT / "hands-on/solutions/graphrag-ontology/schema/rdb/graph_schema.json"
RDB_STRUCTURE = REPO_ROOT / "hands-on/solutions/graphrag-ontology/schema/rdb/output/structure.json"
RDB_DDL = REPO_ROOT / "backing-services/rdb/init/01_schema.sql"
RDB_SEED = REPO_ROOT / "backing-services/rdb/init/02_seed.sql"

# 개인정보 꼴(정규식). 날짜처럼 모양만 같은 것도 걸리므로 아래에서 앞뒤 글을 보고 다시 가림
PII_PATTERNS = {
    "전화번호": r"0\d{1,2}[-.\s]?\d{3,4}[-.\s]?\d{4}",
    "이메일": r"[\w.+-]+@[\w-]+\.[\w.-]+",
    "카드 번호(16자리)": r"\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b",
    "계좌 번호 꼴": r"\b\d{2,6}-\d{2,6}-\d{2,8}\b",
    "주민번호": r"\b\d{6}[-\s]?[1-4]\d{6}\b",
    "생년월일(숫자 표기)": r"\b(?:19|20)\d{2}[-./]\s?\d{1,2}[-./]\s?\d{1,2}\b",
    "생년월일(한글 표기)": r"(?:19|20)\d{2}년\s*\d{1,2}월\s*\d{1,2}일",
    "회원 원래 번호": r"\bM-\d{4}\b",
}
BIRTH_WORDS = re.compile("생년|생일|출생|태어")


def read_chunks() -> tuple[list[dict], dict]:
    """collection을 나눠 읽고 건수, ID 겹침, 빈 값을 확인함."""
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    names = {c.name: c.count() for c in client.list_collections()}
    collection = client.get_collection(COLLECTION)  # 없으면 오류가 남(get_or_create는 새로 만들므로 쓰지 않음)
    count = collection.count()
    chunks = []
    for offset in range(0, count, PAGE):
        got = collection.get(include=["documents", "metadatas"], limit=PAGE, offset=offset)
        for chunk_id, text, meta in zip(got["ids"], got["documents"], got["metadatas"]):
            chunks.append({"id": chunk_id, "text": text, "metadata": meta})
    chunks.sort(key=lambda c: c["id"])  # 꺼내는 순서는 정해져 있지 않으므로 ID 순으로 맞춤
    ids = [c["id"] for c in chunks]
    check = {
        "collections": names,
        "collection": COLLECTION,
        "count": count,
        "read": len(chunks),
        "duplicate_ids": len(ids) - len(set(ids)),
        "empty_text": sum(1 for c in chunks if not (c["text"] or "").strip()),
        "empty_metadata": sum(1 for c in chunks if not c["metadata"]),
    }
    check["passed"] = (check["read"] == count and check["duplicate_ids"] == 0
                       and check["empty_text"] == 0 and check["empty_metadata"] == 0)
    return chunks, check


def scan_pii(chunks: list[dict]) -> dict:
    """개인정보 꼴을 세고, 실제 개인정보로 보이는 것의 위치를 값은 가린 채 적음."""
    result = {}
    for name, pattern in PII_PATTERNS.items():
        hits, real = 0, []
        for chunk in chunks:
            for found in re.finditer(pattern, chunk["text"]):
                hits += 1
                around = chunk["text"][max(0, found.start() - 15):found.end() + 5]
                is_date = bool(re.fullmatch(r"(?:19|20)\d{2}\D+\d{1,2}\D+\d{1,2}\D?", found.group(0)))
                if is_date and not BIRTH_WORDS.search(around):
                    continue  # 상담일, 시행일 같은 날짜는 개인정보가 아님
                real.append({"chunk_id": chunk["id"], "doc_type": chunk["metadata"]["doc_type"],
                             "where": "생일 낱말 곁의 날짜" if is_date else "본문"})
        result[name] = {"hits": hits, "real": len(real), "locations": real}
    return result


def describe(chunks: list[dict]) -> dict:
    """문서 종류마다 청크 수, 본문 길이, 메타데이터 칸별 값 종류 수를 셈."""
    out = {}
    by_type = collections.defaultdict(list)
    for chunk in chunks:
        by_type[chunk["metadata"]["doc_type"]].append(chunk)
    for doc_type, rows in by_type.items():
        lengths = sorted(len(c["text"]) for c in rows)
        fields = collections.defaultdict(set)
        filled = collections.Counter()
        for c in rows:
            for key, value in c["metadata"].items():
                fields[key].add(value)
                filled[key] += 1
        out[doc_type] = {
            "chunks": len(rows),
            "text_length": {"min": lengths[0], "median": lengths[len(lengths) // 2], "max": lengths[-1]},
            "metadata": {k: {"filled": filled[k], "distinct": len(v)} for k, v in sorted(fields.items())},
        }
    return out


def build_sources() -> dict:
    """다른 원천의 구조 명세에서 라벨, 한글 이름, 키 속성을 읽어 원천 목록 표를 만듦."""
    import json
    schema = json.loads(RDB_SCHEMA.read_text(encoding="utf-8"))
    keys = {c["node_type"]: c["property_names"] for c in schema["constraints"] if c["type"] == "UNIQUENESS"}
    labels = [{"label": n["label"], "korean_name": n.get("description", ""),
               "key_properties": keys.get(n["label"], []),
               "properties": [p["name"] for p in n.get("properties", [])]} for n in schema["node_types"]]
    return {"sources": [{
        "name": "정형 DB(cardlab)",
        "kind": "정형 DB(PostgreSQL)",
        "spec_files": [rel(RDB_SCHEMA), rel(RDB_STRUCTURE)],
        "spec_sha256": {rel(RDB_SCHEMA): sha256_of(RDB_SCHEMA), rel(RDB_STRUCTURE): sha256_of(RDB_STRUCTURE)},
        "labels": labels,
        "relationships": [r["label"] for r in schema["relationship_types"]],
        "not_in_spec": ["값 목록(Merchant.category, Member.segment_id의 뜻)"],
    }]}


def copy_block(seed: str, table: str) -> tuple[list[str], list[list[str]]]:
    """초기 데이터 파일의 `COPY 표 (...) FROM stdin;` 구간을 열 이름과 행으로 읽음."""
    found = re.search(r"COPY " + table + r" \(([^)]*)\) FROM stdin;\n(.*?)\n\\\.", seed, re.S)
    return found.group(1).split(", "), [line.split("\t") for line in found.group(2).split("\n")]


def build_value_files() -> tuple[dict, dict]:
    """값 목록과 키 값 목록을 원본 파일에서 옮겨 적음(기억으로 적지 않음)."""
    seed = RDB_SEED.read_text(encoding="utf-8")
    ddl = RDB_DDL.read_text(encoding="utf-8")
    cols, rows = copy_block(seed, "merchant")
    categories = list(dict.fromkeys(r[cols.index("category")] for r in rows))  # 처음 나온 순서대로, 겹침 없이
    comment = re.search(r"COMMENT ON COLUMN member\.segment_id IS '([^']*)'", ddl).group(1)
    segments = [{"code": int(part.split(" ", 1)[0]), "name": part.split(" ", 1)[1].strip()}
                for part in comment.split(" / ")]
    cols, rows = copy_block(seed, "product")
    product_ids = sorted(r[cols.index("product_id")] for r in rows)
    value_lists = {
        "note": "분류 Class의 허용 값. 아래 원본 파일에서 스크립트로 옮겨 적음",
        "lists": {
            "업종": {"values": categories, "source": rel(RDB_SEED) + "의 merchant 초기 데이터(category 열)",
                     "source_label": "Merchant", "source_property": "category", "hierarchy": "원본에 상하위 정보 없음"},
            "고객군": {"values": segments, "source": rel(RDB_DDL) + "의 member.segment_id 컬럼 설명",
                       "source_label": "Member", "source_property": "segment_id", "hierarchy": "원본에 상하위 정보 없음"},
        },
    }
    key_values = {
        "note": "다른 원천에 실제로 있는 키 값. 8단계 참조 무결성 검사에서만 씀",
        "keys": {"Product.product_id": {"values": product_ids, "count": len(product_ids),
                                        "source": rel(RDB_SEED) + "의 product 초기 데이터"}},
    }
    return value_lists, key_values


def main() -> None:
    chunks, check = read_chunks()
    print("읽기 확인:", check)
    if not check["passed"]:
        raise SystemExit("읽기 확인 실패. 사본을 저장하지 않음")
    write_json(SNAPSHOT_PATH, {"collection": COLLECTION, "chroma_dir": rel(CHROMA_DIR),
                               "count": len(chunks), "text_field": "documents", "chunks": chunks})
    value_lists, key_values = build_value_files()
    write_json(BASE_DIR / "sources.json", build_sources())
    write_json(BASE_DIR / "inputs/value_lists.json", value_lists)
    write_json(BASE_DIR / "inputs/key_values.json", key_values)
    scan = {
        "read_check": check,
        "snapshot": {"path": rel(SNAPSHOT_PATH), "sha256": sha256_of(SNAPSHOT_PATH)},
        "doc_types": describe(chunks),
        "pii": scan_pii(chunks),
        "tool_versions": {name: importlib.metadata.version(name) for name in ("chromadb", "neo4j-graphrag")},
    }
    write_json(BASE_DIR / "output/input_scan.json", scan)
    print("사본:", scan["snapshot"])
    print("문서 종류:", {k: v["chunks"] for k, v in scan["doc_types"].items()})
    print("개인정보:", {k: (v["hits"], v["real"]) for k, v in scan["pii"].items()})
    print("실제 개인정보 위치:", [loc for v in scan["pii"].values() for loc in v["locations"]])
    print("값 목록:", {k: len(v["values"]) for k, v in value_lists["lists"].items()},
          "| 키 값:", {k: v["count"] for k, v in key_values["keys"].items()})
    print("도구 판:", scan["tool_versions"])


if __name__ == "__main__":
    main()
