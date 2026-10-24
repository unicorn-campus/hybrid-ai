"""PostgreSQL 카탈로그(pg_catalog)에서 테이블 구조를 읽어 output/structure.json으로 저장함.

읽는 것: 지정 스키마의 일반 테이블(뷰 제외), 열(이름, 타입, PK 포함 여부, FK 포함 여부), PK, FK 제약.
FK는 제약 단위로 읽음. pg_constraint의 conkey(내 열 번호)와 confkey(상대 열 번호)를 같은 순서끼리 짝지음.
information_schema를 단순 조인하면 열 2개짜리 FK의 짝이 엇갈려 곱해지기 때문임.

비밀번호는 secrets/.env의 RDB_PASSWORD를 실행할 때마다 읽음(코드, 로그, 출력에 남기지 않음).
DB는 읽기 전용 세션으로만 조회함.

실행 예:
  .venv/Scripts/python tools/read_catalog.py --host localhost --port 5432 --dbname cardlab --schema public --user cardlab
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import psycopg

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_ENV = BASE_DIR.parents[3] / "secrets" / ".env"  # schema → graphrag → indexer → hybrid-ai-lab → 저장소 루트

# 일반 테이블만 셈(r: 일반, p: 파티션 부모). 뷰(v), 구체화 뷰(m), 외부 테이블(f)은 뺌
TABLE_KINDS = ("r", "p")

SQL_TABLES = """
SELECT c.oid, c.relname
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = %(schema)s AND c.relkind = ANY(%(kinds)s) AND NOT c.relispartition
ORDER BY c.relname
"""

SQL_COLUMNS = """
SELECT a.attrelid, a.attnum, a.attname, t.typname, format_type(a.atttypid, a.atttypmod), a.attnotnull
FROM pg_attribute a JOIN pg_type t ON t.oid = a.atttypid
WHERE a.attrelid = ANY(%(oids)s) AND a.attnum > 0 AND NOT a.attisdropped
ORDER BY a.attrelid, a.attnum
"""

# unnest ... WITH ORDINALITY: conkey와 confkey의 같은 순번끼리 짝지어 열 짝이 엇갈리지 않게 함
SQL_CONSTRAINTS = """
SELECT con.conrelid, con.conname, con.contype, ft.relname AS ref_table,
       k.ord, a.attname AS col, fa.attname AS ref_col
FROM pg_constraint con
CROSS JOIN LATERAL unnest(con.conkey, con.confkey) WITH ORDINALITY AS k(attnum, fattnum, ord)
JOIN pg_attribute a ON a.attrelid = con.conrelid AND a.attnum = k.attnum
LEFT JOIN pg_class ft ON ft.oid = con.confrelid
LEFT JOIN pg_attribute fa ON fa.attrelid = con.confrelid AND fa.attnum = k.fattnum
WHERE con.conrelid = ANY(%(oids)s) AND con.contype IN ('p', 'f')
ORDER BY con.conrelid, con.contype, con.conname, k.ord
"""


def read_password(env_file: Path) -> str:
    """.env에서 RDB_PASSWORD 값만 꺼냄. 없거나 비어 있으면 값 없이 이유만 알리고 끝냄."""

    if not env_file.is_file():
        raise SystemExit(f"{env_file} 파일이 없음. RDB_PASSWORD={{비밀번호}} 한 줄을 직접 등록해 주세요.")
    for line in env_file.read_text(encoding="utf-8").splitlines():
        key, sep, value = line.strip().partition("=")
        if sep and key.strip() == "RDB_PASSWORD":
            value = value.strip().strip('"').strip("'")
            if value:
                return value
    raise SystemExit(f"{env_file}에 RDB_PASSWORD가 없거나 값이 비어 있음. 직접 등록해 주세요.")


def read_catalog(conn: psycopg.Connection, schema: str) -> dict:
    with conn.cursor() as cur:
        cur.execute("SELECT 1")
        cur.execute(SQL_TABLES, {"schema": schema, "kinds": list(TABLE_KINDS)})
        tables = cur.fetchall()
        oids = [oid for oid, _ in tables]
        cur.execute(SQL_COLUMNS, {"oids": oids})
        columns = cur.fetchall()
        cur.execute(SQL_CONSTRAINTS, {"oids": oids})
        constraints = cur.fetchall()

    pk_cols: dict[int, list[str]] = {}
    fks: dict[int, dict[str, dict]] = {}
    for relid, conname, contype, ref_table, _ord, col, ref_col in constraints:
        if contype == "p":
            pk_cols.setdefault(relid, []).append(col)
        else:
            fk = fks.setdefault(relid, {}).setdefault(conname, {"name": conname, "ref_table": ref_table, "pairs": []})
            fk["pairs"].append({"column": col, "ref_column": ref_col})

    out = []
    for oid, name in tables:
        pk = pk_cols.get(oid, [])
        fk_list = list(fks.get(oid, {}).values())
        fk_cols = {p["column"] for fk in fk_list for p in fk["pairs"]}
        cols = [
            {"name": col, "type": typname, "full_type": full_type, "not_null": not_null,
             "in_pk": col in pk, "in_fk": col in fk_cols}
            for relid, _num, col, typname, full_type, not_null in columns if relid == oid
        ]
        out.append({"name": name, "columns": cols, "primary_key": pk, "foreign_keys": fk_list})
    return {"tables": out}


def count_tables(conn: psycopg.Connection, schema: str) -> int:
    """완료조건 대조용: 카탈로그에서 일반 테이블 수를 따로 셈."""

    with conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = %s AND c.relkind = ANY(%s) AND NOT c.relispartition",
            (schema, list(TABLE_KINDS)),
        )
        return cur.fetchone()[0]


def main() -> None:
    ap = argparse.ArgumentParser(description="PostgreSQL 카탈로그 → structure.json")
    ap.add_argument("--host", required=True)
    ap.add_argument("--port", type=int, required=True)
    ap.add_argument("--dbname", required=True)
    ap.add_argument("--schema", required=True)
    ap.add_argument("--user", required=True)
    ap.add_argument("--env-file", type=Path, default=DEFAULT_ENV)
    ap.add_argument("--out", type=Path, default=BASE_DIR / "output" / "structure.json")
    args = ap.parse_args()

    try:
        conn = psycopg.connect(host=args.host, port=args.port, dbname=args.dbname, user=args.user,
                               password=read_password(args.env_file), connect_timeout=10, autocommit=True)
    except psycopg.OperationalError as e:
        # 오류 문구에 비밀번호는 들어가지 않음(psycopg는 접속 문자열을 감춤)
        print(f"접속 실패: {e}", file=sys.stderr)
        raise SystemExit(2)

    with conn:
        conn.execute("SET default_transaction_read_only = on")
        read_only = conn.execute("SHOW default_transaction_read_only").fetchone()[0]
        data = read_catalog(conn, args.schema)
        catalog_count = count_tables(conn, args.schema)

    # 실행 시각은 넣지 않음: 다시 돌려도 같은 파일(같은 SHA-256)이 나오게 하기 위함
    result = {
        "source": {"db_type": "PostgreSQL", "host": args.host, "port": args.port, "database": args.dbname,
                   "schema": args.schema, "user": args.user},
        "table_count": len(data["tables"]),
        **data,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    fk_total = sum(len(t["foreign_keys"]) for t in data["tables"])
    print(f"접속 확인: SELECT 1 성공, default_transaction_read_only = {read_only}")
    print(f"일반 테이블: structure.json {result['table_count']}개 / 카탈로그 집계 {catalog_count}개 "
          f"→ {'일치' if result['table_count'] == catalog_count else '불일치'}")
    print(f"FK 제약 {fk_total}개 저장: {args.out}")
    if result["table_count"] != catalog_count:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
