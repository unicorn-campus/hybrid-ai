"""정형 조회(NL2SQL) 함수 모음: 그래프의 스키마 설명 읽기, SQL 검사, 읽기 전용 실행, 건너갈 키 고르기.

온톨로지 결합 개선 6번(검색기에 정형 조회 툴 추가)에서 씀. search_graph.py의 query_customer_data 툴이 순서대로 부름.
  ① read_schema_graph   Neo4j에 실어 둔 스키마 설명(뷰, 컬럼, 업무 개념, 예시 쿼리)을 읽음
  ② schema_text         읽은 설명을 LLM 프롬프트에 넣을 글로 만듦
  ③ check_sql           LLM이 만든 SQL을 실행 전에 검사함(SELECT만, 허용한 뷰만, 행 수 상한)
  ④ run_sql             읽기 전용 트랜잭션에서 실행함. 회원 범위는 세션 값으로만 넘김
  ⑤ bridge_keys         결과에서 문서 그래프로 건너갈 키 값(업종, 카드상품 ID)을 고름

행 데이터는 PostgreSQL에 그대로 두고, Neo4j에는 스키마와 뜻만 둠(개선 3번이 실어 둠).
회원 격리는 이 코드가 아니라 DB가 맡음: 검색기 계정은 app 논리 뷰만 읽고, 뷰는 세션 값 app.member_id의 회원 행만 돌려줌.
"""

import re
from datetime import date
from decimal import Decimal

import psycopg
from psycopg.rows import dict_row

# SELECT 한 문장만 받음. 바꾸는 말, 여러 문장, 주석, 시스템 함수가 보이면 실행하지 않음
SQL_FORBIDDEN = re.compile(
    r"\b(insert|update|delete|merge|drop|alter|create|grant|revoke|truncate|copy|call|do|set|show|begin|commit|"
    r"rollback|vacuum|explain|listen|notify|lock|pg_\w+|information_schema)\b|;|--|/\*", re.IGNORECASE)
VIEW_REFERENCE = re.compile(r"\b(?:from|join)\s+([A-Za-z_][\w.]*)", re.IGNORECASE)  # FROM, JOIN 뒤의 이름
HAS_LIMIT = re.compile(r"\blimit\s+\d+\s*$", re.IGNORECASE)

SCOPE_SETTINGS = ("app.member_id", "app.base_date", "app.coverage_start")  # 논리 뷰가 읽는 세션 값(rdb/init/04_views_rls.sql)


def read_schema_graph(run) -> dict:
    """① Neo4j에서 스키마 설명을 읽음. run은 Cypher를 실행해 레코드 목록을 돌려주는 함수(Resources.run).

    반환값: views({뷰 이름: {meaning, columns[{name, type, meaning, concept}]}}), concepts, examples,
            key_columns({컬럼 이름: 업무 개념 이름}. 이 컬럼의 값이 문서 그래프로 건너가는 키임)
    """
    views, key_columns = {}, {}
    for r in run("MATCH (v:DbView)-[:HAS_COLUMN]->(c:DbColumn) OPTIONAL MATCH (k:OntoConcept)-[:KEY_IN]->(c) "
                 "RETURN v.name AS view, v.meaning AS meaning, c.name AS col, c.data_type AS type, "
                 "c.meaning AS col_meaning, k.name AS concept ORDER BY v.name, c.position"):
        view = views.setdefault(r["view"], {"meaning": r["meaning"], "columns": []})
        view["columns"].append({"name": r["col"], "type": r["type"], "meaning": r["col_meaning"], "concept": r["concept"]})
        if r["concept"]:
            key_columns[r["col"]] = r["concept"]
    concepts = [dict(r) for r in run("MATCH (k:OntoConcept) RETURN k.name AS name, k.definition AS definition, "
                                     "k.values AS values ORDER BY k.position")]
    examples = [dict(r) for r in run("MATCH (e:SqlExample) RETURN e.question AS question, e.sql AS sql "
                                     "ORDER BY e.position")]
    return {"views": views, "concepts": concepts, "examples": examples, "key_columns": key_columns}


def schema_text(schema: dict) -> str:
    """② 스키마 설명을 프롬프트에 넣을 글로 만듦. 뷰와 컬럼의 뜻, 업무 개념의 정의와 허용 값, 예시 쿼리 순서."""
    lines = []
    for name, view in schema["views"].items():
        lines.append(f"뷰 {name}: {view['meaning']}")
        for col in view["columns"]:
            key = f" [{col['concept']}의 키]" if col["concept"] else ""
            lines.append(f"  - {col['name']} ({col['type']}): {col['meaning']}{key}")
    lines.append("업무 개념")
    for concept in schema["concepts"]:
        values = f" 값: {', '.join(concept['values'])}" if concept["values"] else ""
        lines.append(f"  - {concept['name']}: {concept['definition']}.{values}")
    lines.append("예시")
    for example in schema["examples"]:
        lines.append(f"  질문: {example['question']}\n  SQL: {example['sql']}")
    return "\n".join(lines)


def check_sql(sql: str, allowed_views: set, limit: int = 50) -> str:
    """③ LLM이 만든 SQL을 실행 전에 검사함. 통과하면 행 수 상한을 붙인 SQL을 돌려주고, 아니면 ValueError.

    규칙: SELECT로 시작하는 한 문장만, 바꾸는 말과 주석과 시스템 이름 금지, FROM과 JOIN은 허용한 뷰만.
    여기서 놓쳐도 DB가 한 번 더 막음(읽기 전용 트랜잭션, app 뷰만 읽는 계정, 회원별 행 수준 보안).
    예시: "SELECT * FROM public.member" → ValueError(허용하지 않은 뷰: public.member)
    """
    text = sql.strip().rstrip(";").strip()
    if not re.match(r"select\b", text, re.IGNORECASE):
        raise ValueError("SELECT 문만 실행함")
    found = SQL_FORBIDDEN.search(text)
    if found:
        raise ValueError(f"쓸 수 없는 말: {found.group(0)}")
    used = VIEW_REFERENCE.findall(text)
    unknown = [name for name in used if name.lower().removeprefix("app.") not in allowed_views]
    if not used or unknown:
        raise ValueError(f"허용하지 않은 뷰: {', '.join(unknown) or '뷰 없음'}")
    return text if HAS_LIMIT.search(text) else f"{text} LIMIT {limit}"


def read_scope(dsn: str, password: str) -> dict:
    """데이터 기준일과 조회 시작일을 DB의 lab_metadata에서 읽음. 논리 뷰가 이 값으로 최근 6개월을 정함."""
    with psycopg.connect(dsn, password=password, connect_timeout=10) as conn:
        meta = dict(conn.execute("SELECT key, value FROM public.lab_metadata").fetchall())
    return {"base_date": meta["base_date"], "coverage_start": meta["txn_period"].split("~")[0].strip() + "-01"}


def run_sql(dsn: str, password: str, sql: str, member_id: str, scope: dict, timeout_ms: int = 5000) -> list[dict]:
    """④ 검사를 통과한 SQL을 읽기 전용 트랜잭션에서 실행함.

    회원번호는 SQL 글에 넣지 않고 세션 값(app.member_id)으로만 넘김. 뷰가 이 회원의 행만 돌려줌.
    """
    values = (member_id, scope["base_date"], scope["coverage_start"])
    with psycopg.connect(dsn, password=password, row_factory=dict_row, connect_timeout=10) as conn:
        with conn.transaction():
            conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")  # 쓰기를 DB가 거부함
            conn.execute("SET LOCAL search_path TO pg_catalog, app")  # 이름만 쓰면 app 논리 뷰로 감
            conn.execute("SELECT set_config('statement_timeout', %s, true)", (str(timeout_ms),))
            for name, value in zip(SCOPE_SETTINGS, values):
                conn.execute("SELECT set_config(%s, %s, true)", (name, value))  # 값 바인딩. 이 트랜잭션에서만 유효
            rows = conn.execute(sql).fetchall()
    return [{k: plain(v) for k, v in row.items()} for row in rows]


def plain(value):
    """DB 값을 기록과 화면에 쓰기 쉬운 꼴로 바꿈(Decimal은 정수나 실수, 날짜는 글자)."""
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, date):
        return value.isoformat()
    return value


def bridge_keys(rows: list[dict], key_columns: dict, top: int = 3) -> dict:
    """⑤ 조회 결과에서 문서 그래프로 건너갈 키 값을 고름. 결과 순서대로 서로 다른 값 top개까지.

    예시: rows의 category가 식비, 교육, 식비이고 key_columns가 {"category": "업종"} → {"업종": ["식비", "교육"]}
    """
    keys = {}
    for row in rows:
        for column, concept in key_columns.items():
            value = row.get(column)
            found = keys.setdefault(concept, [])
            if value is not None and str(value) not in found and len(found) < top:
                found.append(str(value))
    return {concept: values for concept, values in keys.items() if values}


def rows_text(rows: list[dict], limit: int = 20) -> str:
    """조회 결과를 근거 글로 만듦. 한 줄에 한 행, 「컬럼=값」을 쉼표로 이음."""
    return "\n".join(", ".join(f"{k}={v}" for k, v in row.items()) for row in rows[:limit])
