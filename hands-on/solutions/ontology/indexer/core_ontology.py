"""온톨로지 결합 인덱싱 함수 모음. 스키마 설계(`schema/doc-ontology`)가 확정한 결과를 그대로 따름.

스키마 설계 프롬프트(`prompts/design-kg-schema-doc-ontology.md`) 9단계가 남긴 추출 단위 글 규칙(unit_text_rules.json)대로
인덱싱에서도 같은 글로 추출하려고, 추출 단위와 머리줄과 머리줄 값 보정은 스키마 설계 도구(`schema/doc-ontology/tools`)의
함수를 불러 씀. 파일에 적힌 규칙과 그 함수의 규칙이 같은지는 check_unit_text_rules가 시작할 때 확인함.

  K1      split_units          추출 단위(약관은 조항, 혜택 안내는 혜택 항목, 상담 기록은 청크 그대로)와 머리줄(version 2)
  K2 뒤   postprocess_graph    머리줄 값 보정(header_fill_rule)과 주제 맞추기 표(대표 이름으로 바꿈)
  K5 뒤   load_concept_layer   공통 개념 층(Class, 관계, 검사 규칙)을 그래프에 실음. 정형 DB의 행은 싣지 않음
          load_view_layer      정형 조회용 뷰 설명(schema/rdb/app_views.json)을 DB 카탈로그와 대조한 뒤 DbView, DbColumn,
                               SqlExample로 실음. 키 컬럼은 OntoConcept -[:KEY_IN]-> DbColumn(검색기의 정형 조회 툴이 읽음)
          link_categories      업종 맞추기 표의 approved 행만 Benefit -[:IN_CATEGORY]-> Category로 이음
          check_rules          검사 규칙 K01 ~ K09의 위반 수와 건너가는 지점(P1 ~ P6)의 이어짐을 셈

정형 데이터(회원, 카드, 거래)는 PostgreSQL에 그대로 둠. 문서 노드에는 키 속성(product_id, member_pseudo_id)만 있음.
"""

import json
import re
import sys
from pathlib import Path

import core_turtle as turtle  # 온톨로지 원본(Turtle) 읽기와 SHACL 검사

SCHEMA_DIR = Path(__file__).resolve().parents[1] / "schema" / "doc-ontology"  # 스키마 설계 결과 폴더. 읽기만 함
sys.path.insert(0, str(SCHEMA_DIR / "tools"))  # 스키마 설계 도구(units.py, fill_test.py)를 불러 쓰기 위함

import units as schema_units  # noqa: E402  추출 단위, 머리줄, 머리줄 값
from fill_test import apply_header, tagged_template, tidy_graph_json  # noqa: E402  시험과 같은 보정, 추출 틀, 응답 다듬기

CONCEPT_LABELS = ("OntoConcept",)  # 공통 개념 층 노드. 세대와 상관없이 한 벌만 둠


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def squash(text) -> str:
    return re.sub(r"\s+", "", str(text or ""))


# ---------------------------------------------------------------------------
# K1 추출 단위
# ---------------------------------------------------------------------------
def check_unit_text_rules(doc_type: str, rules: dict) -> None:
    """unit_text_rules.json에 적힌 규칙이 지금 실행할 코드(units.py)의 규칙과 같은지 확인함. 다르면 멈춤.

    목적: 스키마 설계가 시험해 통과시킨 추출 단위와 머리줄을 인덱싱이 그대로 쓰는지 보장함.
          설계 뒤에 units.py만 고치면 시험과 다른 글로 추출하게 되므로, 그때는 9단계를 다시 실행해야 함.
    """
    problems = []
    if rules.get("extraction_unit_rule") != schema_units.RULES[doc_type]:
        problems.append("나누는 규칙(extraction_unit_rule)")
    if rules.get("metadata_header") != schema_units.HEADER_FIELDS[doc_type]:
        problems.append("머리줄 칸(metadata_header)")
    if problems:
        raise SystemExit(f"{doc_type}: unit_text_rules.json의 {', '.join(problems)}이 schema/doc-ontology/tools/units.py와 다름\n"
                         "스키마 설계 9단계(tools/finalize.py)를 다시 실행해 두 곳을 맞출 것")


def split_units(chunks: list[dict], skip_chroma_ids: set[str]) -> tuple[list[dict], list[str], list[str]]:
    """청크를 추출 단위로 나눔. 스키마 설계 3단계에서 승인한 규칙(units.split_chunk)을 그대로 씀.

    인자: chunks는 index_graph의 청크(chunk_id, doc_id, doc_type, text, metadata). skip_chroma_ids는 LLM에 보내지 않을 청크
          (1단계 개인정보 점검에서 남은 것).
    반환값: (단위 목록, 단위가 하나도 안 나온 청크 ID, 개인정보 때문에 건너뛴 청크 ID).
            단위는 unit_id, doc_type, doc_id, metadata, text, chunk_ids, text_hash, bundle, keys,
            header_text(머리줄 version 2), header_values(머리줄 값. None이면 답이 없어야 하는 단위라 LLM에 보내지 않음).
    """
    import hashlib
    units: dict[str, dict] = {}
    empty, skipped = [], []
    for chunk in chunks:
        if chunk["metadata"].get("chroma_id") in skip_chroma_ids:
            skipped.append(chunk["chunk_id"])
            continue
        doc_type = chunk["doc_type"]
        # units.split_chunk는 1단계 사본의 청크 꼴(id, text, metadata)을 받음. id는 인덱서의 chunk_id를 넘겨 FROM_CHUNK에 씀
        pieces, _why = schema_units.split_chunk(doc_type, {"id": chunk["chunk_id"], "text": chunk["text"],
                                                           "metadata": chunk["metadata"]})
        if not pieces:
            empty.append(chunk["chunk_id"])
        for piece in pieces:
            unit_id = piece["unit_id"]
            if doc_type != "consult_log" and unit_id == chunk["chunk_id"]:
                unit_id = f"{chunk['doc_id']}#{chunk['metadata'].get('chroma_id')}"  # 조항, 항목이 아닌 청크(표지 등)
            unit = units.get(unit_id)
            if unit is None:
                header_values = schema_units.header_values(doc_type, piece)
                units[unit_id] = {
                    "unit_id": unit_id, "doc_type": doc_type, "doc_id": chunk["doc_id"],
                    "metadata": dict(chunk["metadata"]), "text": piece["text"], "chunk_ids": [chunk["chunk_id"]],
                    "bundle": piece["bundle"], "keys": piece["keys"],
                    "header_text": schema_units.header_of(doc_type, piece) + "\n",
                    "header_values": header_values,
                }
            elif chunk["chunk_id"] not in unit["chunk_ids"]:  # 두 청크에 걸친 단위: 긴 글을 남기고 청크 ID를 모두 모음
                if len(piece["text"]) > len(unit["text"]):
                    unit["text"] = piece["text"]
                unit["chunk_ids"].append(chunk["chunk_id"])
    for unit in units.values():
        unit["text_hash"] = hashlib.sha256(unit["text"].encode("utf-8")).hexdigest()
    return list(units.values()), empty, skipped


# ---------------------------------------------------------------------------
# K2 뒤: 머리줄 값 보정과 주제 맞추기 표
# ---------------------------------------------------------------------------
def load_topic_map(table: dict) -> dict[str, str]:
    """주제 맞추기 표(core_turtle.load_topic_map의 결과)에서 확정한 이름만: 띄어쓰기를 없앤 이름 → 대표 이름."""
    return {squash(name).lower(): representative for name, representative in table["approved"].items()}


def postprocess_graph(unit: dict, topic_map: dict[str, str]) -> dict:
    """추출 결과(가지치기 뒤 model_dump 꼴)에 머리줄 값을 넣고, 주제 이름을 대표 이름으로 바꿈.

    머리줄 값 보정은 스키마 설계의 apply_header를 그대로 씀(관계 꼴만 start, end로 바꿔 넘기고 되돌림).
    반환값: {"fixes": 머리줄 보정 내용, "topics_mapped": 대표 이름으로 바꾼 주제 수}
    """
    graph = unit["graph"]
    simple = {"nodes": [{"id": n["id"], "label": n["label"], "properties": dict(n.get("properties") or {})}
                        for n in graph["nodes"]],
              "relationships": [{"type": r["type"], "start": r["start_node_id"], "end": r["end_node_id"]}
                                for r in graph["relationships"]]}
    simple = apply_header(simple, unit["header_values"], unit["unit_id"])
    mapped = 0
    for node in simple["nodes"]:
        if node["label"] == "Topic" and node["properties"].get("name"):
            name = " ".join(str(node["properties"]["name"]).split())  # 맞추기 표에 없으면 띄어쓰기만 맞춤
            rep = topic_map.get(squash(name).lower())
            if rep and rep != name:
                mapped += 1
            node["properties"]["name"] = rep or name
    unit["graph"] = {
        "nodes": [{"id": n["id"], "label": n["label"], "properties": n["properties"], "embedding_properties": {}}
                  for n in simple["nodes"]],
        "relationships": [{"type": r["type"], "start_node_id": r["start"], "end_node_id": r["end"], "properties": {},
                           "embedding_properties": {}} for r in simple["relationships"]],
    }
    return {"fixes": simple.get("header_fix", []), "topics_mapped": mapped}


# ---------------------------------------------------------------------------
# K5 뒤: 공통 개념 층 싣기, 업종 잇기, 검사 규칙
# ---------------------------------------------------------------------------
def read_view_catalog(dsn: str, password: str, schema: str = "app") -> dict:
    """DB 카탈로그에서 논리 뷰의 컬럼과 자료형을 읽음. 반환값: {뷰 이름: {컬럼 이름: 자료형}}"""
    import psycopg
    catalog = {}
    with psycopg.connect(dsn, password=password, connect_timeout=10) as conn:
        rows = conn.execute("SELECT table_name, column_name, data_type FROM information_schema.columns "
                            "WHERE table_schema = %s ORDER BY table_name, ordinal_position", (schema,)).fetchall()
    for view, column, data_type in rows:
        catalog.setdefault(view, {})[column] = data_type
    return catalog


def load_concept_layer(driver, concepts: dict) -> dict:
    """공통 개념 층(concepts.json)의 Class를 OntoConcept 노드로 실음. 옛 설명 노드는 지우고 다시 만듦(수십 노드라 통째로).

    노드 속성: name, definition, kind(개체, 분류), values(허용 값), doc_labels(문서 쪽 라벨과 키), source_labels(정형 DB 라벨과 키),
              identity(동일 규칙), relations(이 Class가 출발인 관계와 반대 이름). 검색기가 질문의 낱말을 Class와 키로 바꿀 때 씀.
    """
    rows = []
    for position, cls in enumerate(concepts["classes"]):
        out = [r for r in concepts["relations"]
               if cls["name"] in (r["source_class"] if isinstance(r["source_class"], list) else [r["source_class"]])]
        rows.append({
            "name": cls["name"], "class_id": cls["id"], "definition": cls["definition"], "kind": cls["kind"],
            "position": position, "values": (cls.get("allowed_values") or {}).get("values") or [],
            "doc_labels": json.dumps(cls.get("doc_labels", []), ensure_ascii=False),
            "source_labels": json.dumps(cls.get("source_labels", []), ensure_ascii=False),
            "identity": json.dumps(cls.get("identity", []), ensure_ascii=False),
            "relations": json.dumps([{"label": r["label"], "target_class": r["target_class"], "inverse": r.get("inverse")}
                                     for r in out], ensure_ascii=False),
        })
    driver.execute_query("MATCH (n) WHERE any(label IN labels(n) WHERE label IN $labels) DETACH DELETE n",
                         labels=list(CONCEPT_LABELS) + ["DbView", "DbColumn", "SqlExample"])  # 옛 설명 노드도 지움
    driver.execute_query(
        "UNWIND $rows AS k MERGE (oc:OntoConcept {name: k.name}) "
        "SET oc += k", rows=rows)
    driver.execute_query(  # Class 사이 관계(개념 규칙): 출발 Class → 도착 Class, 이름과 반대 이름을 속성으로
        "UNWIND $rels AS r UNWIND r.sources AS s "
        "MATCH (a:OntoConcept {name: s}), (b:OntoConcept {name: r.target}) "
        "MERGE (a)-[x:CONCEPT_REL {label: r.label}]->(b) SET x.inverse = r.inverse",
        rels=[{"label": r["label"], "target": r["target_class"], "inverse": r.get("inverse"),
               "sources": r["source_class"] if isinstance(r["source_class"], list) else [r["source_class"]]}
              for r in concepts["relations"]])
    records, _, _ = driver.execute_query("MATCH (:OntoConcept)-[r:CONCEPT_REL]->(:OntoConcept) RETURN count(r) AS n")
    return {"concepts": len(rows), "concept_relations": records[0]["n"], "version": concepts.get("version")}


def check_view_catalog(views: dict, catalog: dict) -> list[str]:
    """뷰 설명 파일(schema/rdb/app_views.json)을 DB 카탈로그와 대조함. 어긋난 곳을 글 목록으로 돌려줌(없으면 빈 목록).

    예시: 파일에 merchant_usage.category가 있는데 DB 뷰에 그 컬럼이 없으면 「merchant_usage.category: DB에 없음」
    """
    problems = []
    for view in views["views"]:
        db_columns = catalog.get(view["name"])
        if db_columns is None:
            problems.append(f"{view['name']}: DB의 {views.get('schema', 'app')} 스키마에 없거나 읽을 권한 없음")
            continue
        described = {c["name"] for c in view["columns"]}
        problems += [f"{view['name']}.{c}: DB에 없음" for c in sorted(described - set(db_columns))]
        problems += [f"{view['name']}.{c}: 설명 없음" for c in db_columns if c not in described]
    return problems


def load_view_layer(driver, views: dict, catalog: dict) -> dict:
    """정형 조회용 뷰 설명을 실음: DbView -HAS_COLUMN-> DbColumn, 키 컬럼은 OntoConcept -KEY_IN-> DbColumn, 예시는 SqlExample.

    행 데이터는 싣지 않고 뜻만 실음(공통 개념 층과 같이 세대와 상관없이 한 벌). 자료형은 DB 카탈로그 값을 씀.
    load_concept_layer가 옛 설명 노드를 지운 뒤에 불러야 함(KEY_IN이 OntoConcept에 이어짐).
    """
    rows, keys = [], []
    for view in views["views"]:
        for position, col in enumerate(view["columns"]):
            rows.append({"view": view["name"], "view_meaning": view["meaning"], "name": col["name"],
                         "meaning": col["meaning"], "position": position,
                         "data_type": catalog.get(view["name"], {}).get(col["name"])})
            if col.get("concept"):
                keys.append({"view": view["name"], "name": col["name"], "concept": col["concept"]})
    driver.execute_query(
        "UNWIND $rows AS r MERGE (v:DbView {name: r.view}) SET v.meaning = r.view_meaning "
        "MERGE (v)-[:HAS_COLUMN]->(c:DbColumn {view: r.view, name: r.name}) "
        "SET c.meaning = r.meaning, c.position = r.position, c.data_type = r.data_type", rows=rows)
    records, _, _ = driver.execute_query(
        "UNWIND $keys AS k MATCH (oc:OntoConcept {name: k.concept}) MATCH (c:DbColumn {view: k.view, name: k.name}) "
        "MERGE (oc)-[:KEY_IN]->(c) RETURN count(*) AS n", keys=keys)
    driver.execute_query(
        "UNWIND $rows AS e CREATE (:SqlExample {question: e.question, sql: e.sql, position: e.position})",
        rows=[{**e, "position": i} for i, e in enumerate(views["examples"])])
    return {"views": len(views["views"]), "columns": len(rows), "key_columns": records[0]["n"],
            "key_expected": len(keys), "examples": len(views["examples"])}


def link_categories(driver, generation: str, category_map: dict, categories: list[str]) -> dict:
    """업종 노드를 만들고, 업종 맞추기 표의 approved 행만 Benefit -[:IN_CATEGORY]-> Category로 이음.

    공통 개념 층의 「인덱싱이 더하는 라벨과 관계」(indexer_adds)에 적힌 것만 만듦. Category에는 __Entity__를 붙이지 않음
    (엔티티 임베딩 K6과 커뮤니티 K8에 섞이지 않게 함).
    """
    rows = [{"benefit_id": r["benefit_id"], "category": r["category"]} for r in category_map["rows"]
            if r["status"] == "approved" and r.get("category") in categories]
    driver.execute_query("UNWIND $names AS name MERGE (:Category {generation: $g, name: name})",
                         names=categories, g=generation)
    records, _, _ = driver.execute_query(
        "UNWIND $rows AS row "
        "MATCH (b:Benefit {generation: $g, benefit_id: row.benefit_id}) "
        "MATCH (c:Category {generation: $g, name: row.category}) "
        "MERGE (b)-[:IN_CATEGORY]->(c) RETURN count(*) AS linked", rows=rows, g=generation)
    return {"categories": len(categories), "approved_rows": len(rows), "linked": records[0]["linked"]}


def new_map_items(driver, generation: str, category_map: dict, topic_table: dict) -> dict:
    """맞추기 표에 아직 없는 항목을 모음. 사람이 확정할 새 항목이며, 인덱서는 확정하지 않음.

    benefits: 업종 맞추기 표에 행이 없는 혜택(benefit_id, name, target). draft_category_map.py draft --from 의 입력
    topics: 주제 맞추기 표에 행이 없는 주제 이름과 문서 종류별 건수. draft_topic_map.py draft --from 의 입력
    """
    known_benefits = {r["benefit_id"] for r in category_map["rows"]}
    records, _, _ = driver.execute_query(
        "MATCH (b:Benefit {generation: $g}) RETURN b.benefit_id AS benefit_id, b.name AS name, b.target AS target "
        "ORDER BY benefit_id", g=generation)
    benefits = [dict(r) for r in records if r["benefit_id"] not in known_benefits]
    known_topics = {squash(name).lower() for name in list(topic_table["approved"]) + topic_table["pending"]}
    records, _, _ = driver.execute_query(
        "MATCH (t:Topic {generation: $g}) "
        "RETURN t.name AS name, [(t)<-[:ABOUT]-(a:Article) | 'regulation'] + [(t)<-[:ABOUT]-(b:Benefit) | 'benefit_guide'] "
        "+ [(t)<-[:ABOUT]-(c:Complaint) | 'consult_log'] AS docs ORDER BY name", g=generation)
    topics = []
    for r in records:
        if squash(r["name"]).lower() in known_topics or not r["docs"]:
            continue
        counts = {}
        for doc in r["docs"]:
            counts[doc] = counts.get(doc, 0) + 1
        topics.append({"name": r["name"], "docs": counts})
    return {"generation": generation, "benefits": benefits, "topics": topics}


CHECK_LABELS = ("CustomerSegment", "Category", "Consultation", "Benefit", "UsageRule", "Complaint", "Article", "Topic")
CHECK_PROPS = ("name", "record_id", "channel", "member_pseudo_id", "product_id", "benefit_id", "item_id", "article_no",
               "title", "content")
CHECK_RELS = ("IN_SEGMENT", "ABOUT", "FOLLOWS", "REFERS_TO", "IN_CATEGORY", "HAS_COMPLAINT")


def export_for_checks(driver, generation: str) -> tuple[list[dict], list[dict]]:
    """검사에 필요한 노드와 관계만 그래프에서 꺼냄(읽기만 함). SHACL 검사기는 Neo4j를 직접 읽지 못해 이 꼴로 넘김.

    반환값: nodes [{id, label, props}], relationships [{source, type, target}]
    """
    records, _, _ = driver.execute_query(
        "MATCH (n {generation: $g}) WHERE any(l IN labels(n) WHERE l IN $labels) "
        "RETURN elementId(n) AS id, [l IN labels(n) WHERE l IN $labels][0] AS label, properties(n) AS props",
        g=generation, labels=list(CHECK_LABELS))
    nodes = [{"id": r["id"], "label": r["label"], "props": {k: r["props"][k] for k in CHECK_PROPS if k in r["props"]}}
             for r in records]
    records, _, _ = driver.execute_query(
        "MATCH (a {generation: $g})-[r]->(b {generation: $g}) WHERE type(r) IN $rels "
        "RETURN elementId(a) AS source, type(r) AS type, elementId(b) AS target", g=generation, rels=list(CHECK_RELS))
    return nodes, [dict(r) for r in records]


def check_rules(driver, generation: str, concepts: dict, product_ids: set[str], record_ids: set[str],
                article_nos: set[str]) -> dict:
    """공통 개념 층의 검사 규칙(K01 ~ K09) 위반 수와 건너가는 지점의 이어짐을 셈. 데이터는 고치지 않음.

    참조 무결성은 받은 자료 안에서만 대조함: 상품 키는 inputs/key_values.json(정형 DB의 상품 ID 64개),
    상담 ID와 조 번호는 스키마 설계 1단계 사본의 전체 목록(일부 청크만 인덱싱해도 그 밖을 가리킬 수 있어 전체로 대조).
    판정(ok): 허용 값, 참조 무결성, 머리줄로 채우는 허용 수(K03 ~ K05)는 0건이어야 하고, K06은 대상의 10% 이하.
    """
    def q(cypher: str, **params):
        records, _, _ = driver.execute_query(cypher, g=generation, **params)
        return [dict(r) for r in records]

    # 검사 규칙 K01 ~ K09: 그래프 노드를 꺼내 온톨로지 원본의 규칙(ttl/shapes/checks.ttl)으로 검사함(SHACL)
    nodes, relationships = export_for_checks(driver, generation)
    bad = turtle.run_checks(nodes, relationships, product_ids, record_ids, article_nos)
    v = {rule: [{"bad": item} for item in items] for rule, items in bad.items()}
    k6_base = q("MATCH (n {generation: $g}) WHERE n:Complaint OR (n:Article AND n.title IS NOT NULL) OR n:Benefit "
                "RETURN count(n) AS n")[0]["n"]
    rules = {c["id"]: {"kind": c["kind"], "rule": c["rule"], "violations": len(v.get(c["id"], [])),
                       "examples": v.get(c["id"], [])[:5]} for c in concepts["checks"] if c["id"] in v}

    # 건너가는 지점의 이어짐(경로 검사)
    paths = {}
    paths["P1"] = q("MATCH (c:Consultation {generation: $g})-[:HAS_COMPLAINT]->(:Complaint)-[:ABOUT]->(t:Topic) "
                    "OPTIONAL MATCH (t)<-[:ABOUT]-(a:Article) "
                    "RETURN count(DISTINCT c) AS complaint_consults, count(DISTINCT CASE WHEN a IS NOT NULL THEN c END) AS linked")[0]
    paths["P2"] = q("MATCH (c:Consultation {generation: $g})-[:HAS_COMPLAINT]->(:Complaint)-[:ABOUT]->(t:Topic) "
                    "OPTIONAL MATCH (t)<-[:ABOUT]-(b:Benefit) "
                    "RETURN count(DISTINCT c) AS complaint_consults, count(DISTINCT CASE WHEN b IS NOT NULL THEN c END) AS linked")[0]
    paths["P3_P5"] = q("MATCH (c:Consultation {generation: $g}) WHERE c.channel IS NOT NULL "
                       "RETURN count(c) AS consults, count(c.product_id) AS product_id, count(c.member_pseudo_id) AS member_pseudo_id")[0]
    paths["P3_shared_products"] = q("MATCH (c:Consultation {generation: $g}), (b:Benefit {generation: $g}) "
                                    "WHERE c.product_id = b.product_id RETURN count(DISTINCT c.product_id) AS n")[0]["n"]
    paths["P4"] = q("MATCH (b:Benefit {generation: $g}) OPTIONAL MATCH (b)-[:IN_CATEGORY]->(k:Category) "
                    "RETURN count(DISTINCT b) AS benefits, count(DISTINCT CASE WHEN k IS NOT NULL THEN b END) AS with_category")[0]
    paths["P6"] = q("MATCH (b {generation: $g}) WHERE b:Benefit OR b:UsageRule "
                    "RETURN count(b) AS items, count(b.product_id) AS product_id")[0]
    paths["shared_topics"] = q("MATCH (t:Topic {generation: $g}) "
                               "WITH t, [x IN [(t)<-[:ABOUT]-(a:Article) | 'regulation'] + [(t)<-[:ABOUT]-(b:Benefit) | 'benefit_guide'] "
                               "+ [(t)<-[:ABOUT]-(c:Complaint) | 'consult_log'] | x] AS docs "
                               "WITH t, apoc.coll.toSet(docs) AS kinds WHERE size(kinds) > 1 "
                               "RETURN t.name AS topic, kinds ORDER BY topic")
    strict = ["K01", "K02", "K03", "K04", "K05", "K07", "K08", "K09"]
    k6_rate = rules["K06"]["violations"] / k6_base if k6_base else 0.0
    ok = all(rules[k]["violations"] == 0 for k in strict if k in rules) and k6_rate <= 0.1
    return {"ok": ok, "rules": rules, "k06_base": k6_base, "k06_rate": round(k6_rate, 3), "paths": paths}
