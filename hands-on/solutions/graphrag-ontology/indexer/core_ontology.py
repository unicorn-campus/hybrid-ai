"""온톨로지 결합 인덱싱 함수 모음(개선 3 ~ 5). index_graph.py가 K5 병합 뒤에 순서대로 부름.

  개선 3  load_schema_graph   정형 스키마 설명과 공통 개념 층을 Neo4j에 실음(행 데이터는 싣지 않음)
  개선 4  link_categories     승인된 업종 매핑표로 혜택 노드를 업종 노드에 이음
  개선 5  check_bridge        문서 그래프와 정형 DB가 키로 이어지는지 검사함

전제: 정형 데이터(회원, 카드, 거래)는 PostgreSQL에 그대로 둠. 그래프에는 뷰와 컬럼의 뜻, 업무 개념, 예시 쿼리만 들어감.
검색기는 이 설명을 읽어 SQL을 만들고(개선 6), 조회 결과의 키 값으로 문서 그래프에 건너감(개선 7).
"""

import re

import psycopg

VIEW_REFERENCE = re.compile(r"\b(?:from|join)\s+([A-Za-z_][\w.]*)", re.IGNORECASE)  # 예시 쿼리가 쓰는 뷰 이름
SCHEMA_LABELS = ("OntoConcept", "DbView", "DbColumn", "SqlExample")  # 스키마 설명 노드. 세대와 상관없이 한 벌만 둠


def read_view_catalog(dsn: str, password: str, schema: str = "app") -> dict:
    """DB 카탈로그에서 논리 뷰의 컬럼과 자료형을 읽음. 반환값: {뷰 이름: {컬럼 이름: 자료형}}"""
    catalog = {}
    with psycopg.connect(dsn, password=password, connect_timeout=10) as conn:
        rows = conn.execute("SELECT table_name, column_name, data_type FROM information_schema.columns "
                            "WHERE table_schema = %s ORDER BY table_name, ordinal_position", (schema,)).fetchall()
    for view, column, data_type in rows:
        catalog.setdefault(view, {})[column] = data_type
    return catalog


def load_schema_graph(driver, concepts: dict, catalog: dict) -> dict:
    """개선 3: 공통 개념 층(concepts.json)과 DB 카탈로그로 스키마 설명 노드를 다시 만듦.

    노드: OntoConcept(업무 개념), DbView(논리 뷰), DbColumn(컬럼), SqlExample(예시 쿼리)
    관계: (DbView)-[:HAS_COLUMN]->(DbColumn), (OntoConcept)-[:KEY_IN]->(DbColumn), (SqlExample)-[:USES]->(DbView)
    KEY_IN은 「이 컬럼의 값이 이 업무 개념의 키」라는 뜻임. 검색기가 조회 결과에서 건너갈 키를 고를 때 씀.
    설명에 적은 뷰나 컬럼이 DB에 없으면 싣지 않고 ValueError를 냄(설명과 실제가 어긋난 채로 두지 않음).
    """
    views = []
    for view in concepts["views"]:
        columns = catalog.get(view["name"])
        if columns is None:
            raise ValueError(f"DB에 없는 뷰: {view['name']}")
        rows = []
        for position, column in enumerate(view["columns"]):
            if column["name"] not in columns:
                raise ValueError(f"DB에 없는 컬럼: {view['name']}.{column['name']}")
            rows.append({"name": column["name"], "meaning": column["meaning"], "position": position,
                         "data_type": columns[column["name"]]})  # 자료형은 손으로 적지 않고 DB에서 읽음
        views.append({"name": view["name"], "meaning": view["meaning"], "columns": rows})
    concept_rows = [{"name": c["name"], "definition": c["definition"], "values": c.get("values") or [],
                     "doc_label": c["doc"]["label"], "doc_key": c["doc"]["key"], "position": position,
                     "bridge_rule": (c.get("bridge") or {}).get("rule"), "db": c["db"]}
                    for position, c in enumerate(concepts["concepts"])]
    examples = [{"question": e["question"], "sql": e["sql"], "position": position,
                 "views": sorted({name.removeprefix("app.") for name in VIEW_REFERENCE.findall(e["sql"])})}
                for position, e in enumerate(concepts.get("examples", []))]

    # 옛 설명을 지우고 다시 만듦. 스키마 설명은 작아서(수십 노드) 통째로 바꾸는 편이 안전함
    driver.execute_query("MATCH (n) WHERE any(label IN labels(n) WHERE label IN $labels) DETACH DELETE n",
                         labels=list(SCHEMA_LABELS))
    driver.execute_query(
        "UNWIND $views AS v MERGE (dv:DbView {name: v.name}) SET dv.meaning = v.meaning "
        "WITH dv, v UNWIND v.columns AS c "
        "MERGE (dc:DbColumn {id: v.name + '.' + c.name}) "
        "SET dc.name = c.name, dc.data_type = c.data_type, dc.meaning = c.meaning, dc.position = c.position "
        "MERGE (dv)-[:HAS_COLUMN]->(dc)", views=views)
    driver.execute_query(
        "UNWIND $concepts AS k MERGE (oc:OntoConcept {name: k.name}) "
        "SET oc.definition = k.definition, oc.values = k.values, oc.doc_label = k.doc_label, oc.doc_key = k.doc_key, "
        "    oc.bridge_rule = k.bridge_rule, oc.position = k.position "
        "WITH oc, k UNWIND k.db AS d "
        "MATCH (dc:DbColumn {id: d.view + '.' + d.column}) MERGE (oc)-[:KEY_IN]->(dc)", concepts=concept_rows)
    driver.execute_query(
        "UNWIND $examples AS e CREATE (ex:SqlExample {question: e.question, sql: e.sql, position: e.position}) "
        "WITH ex, e UNWIND e.views AS name MATCH (dv:DbView {name: name}) MERGE (ex)-[:USES]->(dv)", examples=examples)
    records, _, _ = driver.execute_query("MATCH (:OntoConcept)-[r:KEY_IN]->(:DbColumn) RETURN count(r) AS n")
    return {"concepts": len(concept_rows), "views": len(views), "columns": sum(len(v["columns"]) for v in views),
            "examples": len(examples), "key_links": records[0]["n"]}


def link_categories(driver, generation: str, category_map: dict, categories: list[str]) -> dict:
    """개선 4: 업종 노드 8개를 만들고, 승인된 매핑표대로 혜택을 업종에 이음.

    업종 노드(Category)는 DB에서 복사한 데이터가 아님. 혜택 문서 쪽 매핑에서 생기며, 두 저장소가 만나는 자리임.
    매핑표에서 status가 approved이고 category가 8개 값 안에 있는 혜택만 이음(확정하지 않은 혜택은 잇지 않음).
    Category에는 __Entity__ 라벨을 붙이지 않음: 엔티티 임베딩(K6)과 커뮤니티(K8)에 섞이지 않게 함.
    """
    rows = [{"benefit_id": benefit_id, "category": item["category"]}
            for benefit_id, item in category_map["benefits"].items()
            if item.get("status") == "approved" and item.get("category") in categories]
    driver.execute_query("UNWIND $names AS name MERGE (:Category {generation: $g, name: name})",
                         names=categories, g=generation)
    records, _, _ = driver.execute_query(
        "UNWIND $rows AS row "
        "MATCH (b:Benefit {generation: $g, benefit_id: row.benefit_id}) "
        "MATCH (c:Category {generation: $g, name: row.category}) "
        "MERGE (b)-[:FOR_CATEGORY]->(c) RETURN count(*) AS linked", rows=rows, g=generation)
    return {"categories": len(categories), "approved_rows": len(rows), "linked": records[0]["linked"]}


def read_db_reference(dsn: str, password: str) -> dict:
    """DB 원본에서 대조할 기준값을 읽음(상품 ID 전체, 가맹점 업종 값). 원본 테이블을 읽으므로 관리 계정으로만 됨."""
    with psycopg.connect(dsn, password=password, connect_timeout=10) as conn:
        products = {row[0] for row in conn.execute("SELECT product_id FROM public.product").fetchall()}
        categories = {row[0] for row in conn.execute("SELECT DISTINCT category FROM public.merchant").fetchall()}
    return {"product_ids": products, "categories": categories}


def check_bridge(driver, generation: str, categories: list[str], db_reference: dict | None) -> dict:
    """개선 5: 문서 그래프와 정형 DB가 키로 이어지는지 검사함. 데이터를 고치지 않고 어긋난 것만 보고함.

    검사 ①: 문서의 상품 ID(ProductGuide.product_id)가 DB 상품에 있는가 → 없으면 orphan_products(오류)
    검사 ②: 공통 개념 층의 업종 8개가 DB의 가맹점 업종 값과 같은가 → 다르면 category_mismatch(오류)
    검사 ③: 업종에 이어지지 않은 혜택 → unmapped_benefits(경고. 담당자가 매핑표를 확정할 목록)
    db_reference가 None이면(관리 계정 정보 없음) ①, ②를 건너뛰고 skipped에 적음.
    """
    records, _, _ = driver.execute_query(
        "MATCH (p:ProductGuide {generation: $g}) RETURN collect(DISTINCT p.product_id) AS ids", g=generation)
    graph_products = {pid for pid in records[0]["ids"] if pid}
    records, _, _ = driver.execute_query(
        "MATCH (b:Benefit {generation: $g}) WHERE NOT (b)-[:FOR_CATEGORY]->(:Category) "
        "RETURN b.benefit_id AS benefit_id, b.name AS name ORDER BY benefit_id", g=generation)
    unmapped = [dict(record) for record in records]
    report = {"graph_products": len(graph_products), "unmapped_benefits": unmapped, "skipped": []}
    if db_reference is None:
        report["skipped"] = ["orphan_products", "category_mismatch"]
        report["ok"] = True
        return report
    report["orphan_products"] = sorted(graph_products - db_reference["product_ids"])
    report["category_mismatch"] = sorted(set(categories) ^ db_reference["categories"])
    report["ok"] = not report["orphan_products"] and not report["category_mismatch"]
    return report
