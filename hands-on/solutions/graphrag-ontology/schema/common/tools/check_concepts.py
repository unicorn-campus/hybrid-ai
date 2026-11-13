"""개선 1: 공통 개념 층(concepts.json)이 실제 스키마와 맞는지 검사함. LLM을 쓰지 않음.

공통 개념 층은 사람이 확정하는 파일이라, 적은 라벨과 컬럼이 실제로 있는지 기계로 한 번 더 확인함.
  검사 ①: 문서 쪽 라벨과 키 속성이 문서 그래프 스키마(schema/doc/*/graph_schema.json)에 있는가
  검사 ②: DB 쪽 뷰와 컬럼이 PostgreSQL의 app 논리 뷰에 있는가
  검사 ③: 예시 쿼리가 SQL 검사(check_sql)를 통과하고 DB에서 실행 계획이 서는가(EXPLAIN. 행은 읽지 않음)

실행(schema/common 폴더에서): python tools/check_concepts.py
결과: output/check_concepts.json. 어긋난 것이 하나라도 있으면 종료 코드 1
"""

import json
import os
import sys
from pathlib import Path

import psycopg
from dotenv import dotenv_values

sys.stdout.reconfigure(encoding="utf-8")
BASE = Path(__file__).resolve().parent.parent  # schema/common
PROJECT = BASE.parents[1]  # graphrag-ontology
ROOT_DIR = BASE.parents[4]
SECRETS_PATH = ROOT_DIR / "secrets" / ".env"
sys.path.insert(0, str(PROJECT / "retriever"))
import core_sql  # noqa: E402  검색기가 쓰는 SQL 검사 규칙을 그대로 씀

RDB_DSN_DEFAULT = "host=localhost port=5432 dbname=cardlab user=sql_retriever_user"


def doc_labels() -> dict:
    """문서 그래프 스키마 3종에서 {라벨: 속성 이름 집합}을 모음."""
    labels = {}
    for path in sorted((PROJECT / "schema" / "doc").glob("*/graph_schema.json")):
        for node in json.loads(path.read_text(encoding="utf-8"))["node_types"]:
            labels.setdefault(node["label"], set()).update(p["name"] for p in node.get("properties", []))
    return labels


def main() -> None:
    concepts = json.loads((BASE / "concepts.json").read_text(encoding="utf-8"))
    values = dotenv_values(SECRETS_PATH) if SECRETS_PATH.exists() else {}
    dsn = os.environ.get("SQL_RETRIEVER_DB_DSN") or values.get("SQL_RETRIEVER_DB_DSN") or RDB_DSN_DEFAULT
    password = os.environ.get("SQL_RETRIEVER_DB_PASSWORD") or values.get("SQL_RETRIEVER_DB_PASSWORD") or ""
    problems = []

    # 검사 ①: 문서 쪽 라벨과 키
    labels = doc_labels()
    for concept in concepts["concepts"]:
        doc = concept["doc"]
        if doc.get("created_by") == "indexer":  # 인덱서가 만드는 라벨(업종)은 문서 스키마에 없는 것이 정상
            continue
        if doc["label"] not in labels:
            problems.append(f"{concept['name']}: 문서 스키마에 없는 라벨 {doc['label']}")
        elif doc["key"] not in labels[doc["label"]]:
            problems.append(f"{concept['name']}: {doc['label']}에 없는 속성 {doc['key']}")

    # 검사 ②: DB 쪽 뷰와 컬럼
    with psycopg.connect(dsn, password=password, connect_timeout=10) as conn:
        catalog = {}
        for view, column in conn.execute("SELECT table_name, column_name FROM information_schema.columns "
                                         "WHERE table_schema = 'app'").fetchall():
            catalog.setdefault(view, set()).add(column)
        described = {view["name"]: {c["name"] for c in view["columns"]} for view in concepts["views"]}
        for view, columns in described.items():
            if view not in catalog:
                problems.append(f"DB에 없는 뷰 {view}")
            else:
                problems += [f"DB에 없는 컬럼 {view}.{c}" for c in sorted(columns - catalog[view])]
        for concept in concepts["concepts"]:
            for ref in concept["db"]:
                if ref["column"] not in described.get(ref["view"], set()):
                    problems.append(f"{concept['name']}: 설명이 없는 키 컬럼 {ref['view']}.{ref['column']}")

        # 검사 ③: 예시 쿼리. 검색기와 같은 규칙으로 검사한 뒤 실행 계획만 세워 봄
        for example in concepts.get("examples", []):
            try:
                sql = core_sql.check_sql(example["sql"], set(described))
                with conn.transaction():
                    conn.execute("SET TRANSACTION READ ONLY")
                    conn.execute("SET LOCAL search_path TO pg_catalog, app")
                    conn.execute("EXPLAIN " + sql)
            except (ValueError, psycopg.Error) as error:
                problems.append(f"예시 쿼리 「{example['question']}」: {str(error).splitlines()[0]}")

    report = {"ok": not problems, "concepts": len(concepts["concepts"]), "views": len(concepts["views"]),
              "examples": len(concepts.get("examples", [])), "problems": problems}
    out = BASE / "output" / "check_concepts.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"공통 개념 층 검사: {'통과' if report['ok'] else '실패'} (업무 개념 {report['concepts']}개, 뷰 {report['views']}개, "
          f"예시 쿼리 {report['examples']}개)")
    for problem in problems:
        print("  어긋남:", problem)
    if problems:
        sys.exit(1)


if __name__ == "__main__":
    main()
