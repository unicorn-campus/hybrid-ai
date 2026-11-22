"""온톨로지 원본(Turtle) 읽기 모듈. 스키마 설계 도구, 인덱서가 함께 씀.

이 실습은 Class, 관계, 규칙을 `../ttl` 폴더의 Turtle 파일에 적고, 세 단계가 모두 그 파일을 읽음.
  ttl/card.ttl                Class와 뜻, 관계와 역관계, 같은 개체 키, 값 목록            (OWL, RDFS, SKOS)
  ttl/shapes/{문서 종류}.ttl  문서 종류별 허용 목록: 노드 타입 속성과 허용 패턴          (SHACL)
  ttl/shapes/checks.ttl       검사 규칙 K01 ~ K09                                        (SHACL)
  ttl/maps/topic.ttl          주제 맞추기 표: 대표 이름과 다른 이름                      (SKOS)
  ttl/maps/category.ttl       업종 맞추기 표: 혜택마다 확정한 업종

함수
  load_concepts       card.ttl과 셰이프에서 공통 개념 층(Class, 관계, 검사 규칙 목록)을 읽음
  graph_schema        card.ttl + shapes/{문서 종류}.ttl → neo4j-graphrag가 읽는 graph_schema.json 내용
  load_topic_map      주제 이름 → 대표 이름(확정한 것), 아직 확정하지 않은 이름
  load_category_map   혜택 → 업종 행 목록(확정, 잇지 않음)
  run_checks          검사 규칙을 SHACL 검사기(pyshacl)로 돌려 규칙마다 어긴 개체를 돌려줌
표준에 없어 우리가 지은 낱말은 `card:` 주소 아래에 두고 CUSTOM_TERMS에 목록으로 적음.
"""

import hashlib
import json
from pathlib import Path
from urllib.parse import quote

from pyshacl import validate
from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.collection import Collection
from rdflib.compare import to_isomorphic
from rdflib.namespace import OWL, RDF, RDFS, SKOS, XSD

TTL_DIR = Path(__file__).resolve().parents[1] / "ttl"  # 온톨로지 원본 폴더
CARD = Namespace("https://hanbit-card.example/ontology#")  # 이 실습의 낱말 주소(가상 회사)
SH = Namespace("http://www.w3.org/ns/shacl#")
DOC_TYPES = ("regulation", "benefit_guide", "consult_log")
TYPE_NAMES = {XSD.string: "STRING", XSD.boolean: "BOOLEAN", XSD.integer: "INTEGER", XSD.double: "FLOAT", XSD.date: "DATE"}
SCHEMA_FLAGS = ("additional_node_types", "additional_relationship_types", "additional_patterns")

# 표준(OWL, RDFS, SKOS, SHACL)에 없어 우리가 지은 낱말과 그 뜻
CUSTOM_TERMS = {
    "CommonConcept": "공통 개념 층에 드는 Class들의 상위 Class. rdfs:subClassOf card:CommonConcept로 표시함",
    "order": "목록에서의 순서(Class, 관계, 제약). graph_schema.json을 똑같이 만들려는 것",
    "keyOrder": "고유 키 제약의 순서",
    "valueList": "분류 Class의 허용 값 목록",
    "identityRule": "키 비교가 아닌 동일 개체 규칙의 설명(between, rule, detail)",
    "sourceKey": "정형 DB 쪽 라벨과 키(source, label, keyProperty)",
    "inverseReason": "역관계를 둔 까닭",
    "docType": "관계나 인덱서가 더하는 노드 타입이 쓰이는 문서 종류",
    "addedBy": "LLM 추출이 아니라 인덱서가 더하는 노드 타입이나 관계(문서 셰이프에는 적지 않음)",
    "additionalProperties": "관계에 목록 밖 속성을 허용하는지",
    "additional_node_types / additional_relationship_types / additional_patterns": "스키마 전체에서 목록 밖을 허용하는지",
    "PendingMapping, name, proposed, status": "맞추기 표에서 아직 확정하지 않은 행",
    "fill, fillNote": "채우는 방법(LLM 추출, 머리줄 값, 맞추기 표)과 그 설명. 노드 타입은 셰이프에, 키만 두는 속성은 그 속성에 적음",
    "CrossingPath, question, path, rule": "건너가는 경로: 역량 질문 번호, 그래프에서 따라갈 경로 글, 쓰는 규칙",
}


def local(term) -> str:
    """주소에서 이름만 꺼냄. 예: https://...ontology#Article → Article"""
    return str(term).split("#")[-1]


def read(*paths: Path) -> Graph:
    """Turtle 파일 여러 개를 한 그래프로 읽음."""
    graph = Graph()
    for path in paths:
        graph.parse(path, format="turtle")
    return graph


def signature(ttl_dir: Path = TTL_DIR) -> str:
    """Turtle 파일 전체의 지문. 글자가 아니라 내용(문장 집합)으로 만듦.

    주석, 줄바꿈, 문장 순서, 이름 없는 노드의 번호가 달라도 내용이 같으면 같은 지문이 나옴.
    그래서 파일을 다시 저장하거나 읽기 좋게 고쳐 쓴 것만으로는 다시 인덱싱하지 않음.
    """
    digest = hashlib.sha256()
    for path in sorted(ttl_dir.rglob("*.ttl")):
        digest.update(path.relative_to(ttl_dir).as_posix().encode("utf-8"))
        digest.update(str(to_isomorphic(read(path)).graph_digest()).encode("utf-8"))
    return digest.hexdigest()


def ordered(graph: Graph, subjects, predicate=None) -> list:
    """순서 값(card:order 또는 준 낱말)으로 정렬함."""
    predicate = predicate or CARD.order
    return sorted(subjects, key=lambda s: int(graph.value(s, predicate)))


def common_concepts(card: Graph) -> list:
    """공통 개념 층에 드는 Class(rdfs:subClassOf card:CommonConcept). 문서 전용 노드 타입은 들지 않음."""
    return [cls for cls in card.subjects(RDFS.subClassOf, CARD.CommonConcept) if (cls, RDF.type, OWL.Class) in card]


def key_names(graph: Graph, cls) -> list[str]:
    keys = graph.value(cls, OWL.hasKey)
    return [local(k) for k in Collection(graph, keys)] if keys is not None else []


# ---------------------------------------------------------------------------
# 공통 개념 층: Class, 관계, 검사 규칙 목록
# ---------------------------------------------------------------------------
def load_concepts(ttl_dir: Path = TTL_DIR) -> dict:
    """card.ttl과 셰이프를 읽어 공통 개념 층을 돌려줌. 인덱서가 그래프에 싣고 검사할 때 쓰는 꼴임.

    classes: name(한글 이름), id, kind, definition, synonyms, allowed_values(values), doc_labels, source_labels, identity
    공통 개념은 rdfs:subClassOf card:CommonConcept인 Class임. kind는 따로 적지 않고 값 목록(card:valueList)이 있으면 「분류」,
    없으면 「개체」로 계산함.
    relations: label, source_class(목록), target_class, inverse
    checks: id, kind, rule (shapes/checks.ttl의 노드 셰이프)
    doc_labels는 따로 적지 않고 셰이프에서 알아냄: 그 Class를 겨냥한 노드 셰이프가 있으면 「노드」,
    노드 타입이 아닌 Class는 그 키 속성을 가진 다른 노드 셰이프를 「키 참조」로 봄.
    """
    card = read(ttl_dir / "card.ttl")
    shapes = {doc: read(ttl_dir / "shapes" / f"{doc}.ttl") for doc in DOC_TYPES}
    concept_classes = ordered(card, common_concepts(card))
    name_of = {cls: str(card.value(cls, RDFS.label)) for cls in concept_classes}
    node_classes = {cls for g in shapes.values() for cls in g.objects(None, SH.targetClass)}
    classes = []
    for cls in concept_classes:
        keys = key_names(card, cls)
        doc_labels = [{"doc_type": str(doc), "label": local(cls), "role": "노드", "key_properties": keys, **fill_of(card, cls)}
                      for doc in card.objects(cls, CARD.docType)]  # 인덱서가 더하는 노드 타입(card:addedBy)
        for doc, g in ({} if card.value(cls, CARD.addedBy) is not None else shapes).items():
            for shape in g.subjects(RDF.type, SH.NodeShape):
                target = g.value(shape, SH.targetClass)
                rows = {local(g.value(row, SH.path)): row for row in g.objects(shape, SH.property)}
                if target == cls:  # 채우는 방법은 노드 타입이면 셰이프에, 키만 두는 것이면 그 키 속성에 적혀 있음
                    doc_labels.append({"doc_type": doc, "label": local(target), "role": "노드", "key_properties": keys,
                                       **fill_of(g, shape)})
                elif cls not in node_classes and keys and set(keys) <= set(rows):
                    doc_labels.append({"doc_type": doc, "label": local(target), "role": "키 참조", "key_properties": keys,
                                       **fill_of(g, rows[keys[0]])})
        values_list = card.value(cls, CARD.valueList)
        values = []
        if values_list is not None:
            values = [str(card.value(item, SKOS.prefLabel)) for item in Collection(card, card.value(values_list, SKOS.memberList))]
        classes.append({
            "name": name_of[cls], "id": local(cls), "kind": "분류" if card.value(cls, CARD.valueList) is not None else "개체",
            "definition": str(card.value(cls, SKOS.definition)),
            "synonyms": sorted(str(o) for o in card.objects(cls, SKOS.altLabel)),
            "allowed_values": {"values": values} if values else None,
            "doc_labels": sorted(doc_labels, key=lambda r: (r["doc_type"], r["label"])),
            "source_labels": [{"source": str(card.value(row, CARD.source)), "label": str(card.value(row, CARD.label)),
                               "key_properties": [str(o) for o in card.objects(row, CARD.keyProperty)]}
                              for row in card.objects(cls, CARD.sourceKey)],
            "identity": [{field: str(card.value(row, CARD[field])) for field in ("between", "rule", "detail")}
                         for row in card.objects(cls, CARD.identityRule)],
        })
    relations = []
    for prop in ordered(card, [p for p in card.subjects(RDF.type, OWL.ObjectProperty) if card.value(p, CARD.order) is not None]):
        domain = card.value(prop, RDFS.domain)
        union = card.value(domain, OWL.unionOf)
        sources = [name_of[m] for m in Collection(card, union)] if union is not None else [name_of[domain]]
        inverse = card.value(prop, OWL.inverseOf)
        relations.append({"label": local(prop), "source_class": sources, "target_class": name_of[card.value(prop, RDFS.range)],
                          "inverse": local(inverse) if inverse is not None else None,
                          "doc_types": sorted(str(o) for o in card.objects(prop, CARD.docType))})
    checks_graph = read(ttl_dir / "shapes" / "checks.ttl")
    checks = [{"id": local(shape), "kind": str(checks_graph.value(shape, RDFS.label)),
               "target": ", ".join(sorted(local(t) for t in checks_graph.objects(shape, SH.targetClass))),
               "rule": str(checks_graph.value(shape, RDFS.comment))}
              for shape in sorted(checks_graph.subjects(RDF.type, SH.NodeShape), key=local)
              if checks_graph.value(shape, RDFS.label) is not None]
    return {"version": str(card.value(CARD.ontology, OWL.versionInfo)), "classes": classes, "relations": relations,
            "checks": checks}


def fill_of(graph: Graph, subject) -> dict:
    """채우는 방법(card:fill: LLM 추출, 머리줄 값, 맞추기 표)과 그 설명(card:fillNote). 적지 않았으면 None."""
    fill, note = graph.value(subject, CARD.fill), graph.value(subject, CARD.fillNote)
    return {"fill": str(fill) if fill is not None else None, "detail": str(note) if note is not None else None}


def crossing_paths(ttl_dir: Path = TTL_DIR) -> list[dict]:
    """건너가는 경로(card:CrossingPath): 역량 질문이 원천을 건너가는 자리마다 그래프에서 따라갈 경로와 쓰는 규칙.

    반환값: [{crossing_point(P1 등), question(역량 질문 번호), path(경로 글), rules(쓰는 규칙 목록)}]
    """
    card = read(ttl_dir / "card.ttl")
    return [{"crossing_point": local(p), "question": str(card.value(p, CARD.question)), "path": str(card.value(p, CARD.path)),
             "rules": sorted(str(o) for o in card.objects(p, CARD.rule))}
            for p in sorted(card.subjects(RDF.type, CARD.CrossingPath), key=local)]


def entity_keys(ttl_dir: Path = TTL_DIR) -> dict:
    """검색기의 엔티티 찾기가 쓰는 키 표를 card.ttl의 키(owl:hasKey)와 셰이프에서 만듦.

    nodes: 그래프에 노드로 있는 Class의 키. [{label, name(한글 이름. 없으면 None), prop}]
    refs:  노드가 없는 Class(카드상품, 회원)의 키를 속성으로 가진 노드 타입. [{name, prop, labels}]
    키 속성이 둘 이상인 Class는 값 하나로 찾을 수 없어 싣지 않음(지금은 없음).
    예시: nodes에 {"label": "Article", "name": "조항", "prop": "article_no"},
          refs에 {"name": "카드상품", "prop": "product_id", "labels": ["Benefit", "Consultation", "UsageRule"]}
    """
    card = read(ttl_dir / "card.ttl")
    shapes = [read(ttl_dir / "shapes" / f"{doc}.ttl") for doc in DOC_TYPES]
    node_classes = {cls for g in shapes for cls in g.objects(None, SH.targetClass)}
    common = set(common_concepts(card))
    nodes, refs = [], []
    for cls in sorted((c for c in card.subjects(RDF.type, OWL.Class) if isinstance(c, URIRef)), key=local):
        keys = key_names(card, cls)
        if len(keys) != 1:
            continue
        name = card.value(cls, RDFS.label) if cls in common else None
        if cls in node_classes:
            nodes.append({"label": local(cls), "name": str(name) if name is not None else None, "prop": keys[0]})
        elif card.value(cls, CARD.addedBy) is None:  # 인덱서가 더하는 업종은 엔티티 찾기의 대상이 아님(혜택으로 건너감)
            labels = sorted({local(g.value(shape, SH.targetClass)) for g in shapes for shape in g.subjects(RDF.type, SH.NodeShape)
                             if keys[0] in {local(g.value(row, SH.path)) for row in g.objects(shape, SH.property)}})
            refs.append({"name": str(name), "prop": keys[0], "labels": labels})
    return {"nodes": nodes, "refs": refs}


# ---------------------------------------------------------------------------
# 그래프 스키마: Turtle → graph_schema.json
# ---------------------------------------------------------------------------
def graph_schema(doc_type: str, ttl_dir: Path = TTL_DIR) -> dict:
    """card.ttl과 shapes/{문서 종류}.ttl을 읽어 graph_schema.json의 내용을 만듦.

    노드 타입 설명은 card.ttl의 뜻(skos:definition)에 해당과 비해당(skos:scopeNote)을 이어 만듦.
    순서는 sh:order(노드 타입, 속성, 패턴)와 card:order(관계), card:keyOrder(제약)를 따름.
    """
    card = read(ttl_dir / "card.ttl")
    g = read(ttl_dir / "shapes" / f"{doc_type}.ttl")
    schema = {"node_types": [], "relationship_types": [], "patterns": [], "constraints": []}
    patterns, constraints = [], []
    for shape in ordered(g, g.subjects(RDF.type, SH.NodeShape), SH.order):
        cls = g.value(shape, SH.targetClass)
        note = card.value(cls, SKOS.scopeNote)
        description = str(card.value(cls, SKOS.definition)) + (" " + str(note) if note is not None else "")
        properties = []
        for row in g.objects(shape, SH.property):
            position = int(g.value(row, SH.order))
            if g.value(row, SH.datatype) is not None:  # 값 속성
                properties.append((position, {"name": local(g.value(row, SH.path)), "type": TYPE_NAMES[g.value(row, SH.datatype)],
                                              "description": str(g.value(row, SH.description)),
                                              "required": g.value(row, SH.minCount) is not None}))
            else:  # 허용 패턴: 이 노드가 이 관계로 가리킬 수 있는 Class
                patterns.append((position, {"source": local(cls), "relationship": local(g.value(row, SH.path)),
                                            "target": local(g.value(row, SH["class"]))}))
        schema["node_types"].append({"label": local(cls), "description": description,
                                     "properties": [p for _, p in sorted(properties, key=lambda x: x[0])],
                                     "additional_properties": not bool(g.value(shape, SH.closed).toPython())})
        key_order = g.value(shape, CARD.keyOrder)
        if key_order is not None:  # 이 문서 종류에서 고유 키 제약으로 거는 Class
            names = key_names(card, cls)
            constraints.append((int(key_order), {"type": "UNIQUENESS", "property_name": names[0], "property_names": names,
                                                 "node_type": local(cls), "relationship_type": None}))
    for prop in ordered(g, g.subjects(RDF.type, OWL.ObjectProperty)):
        schema["relationship_types"].append({"label": local(prop), "description": str(g.value(prop, SKOS.definition)),
                                             "properties": [],
                                             "additional_properties": bool(g.value(prop, CARD.additionalProperties).toPython())})
    schema["patterns"] = [p for _, p in sorted(patterns, key=lambda x: x[0])]
    schema["constraints"] = [c for _, c in sorted(constraints, key=lambda x: x[0])]
    for flag in SCHEMA_FLAGS:
        schema[flag] = bool(g.value(CARD[f"profile_{doc_type}"], CARD[flag]).toPython())
    return schema


def schema_text(schema: dict) -> str:
    """graph_schema.json 파일에 쓸 글. 스키마 설계 도구(GraphSchema.save)와 같은 꼴(들여쓰기 2칸, 한글 그대로)."""
    return json.dumps(schema, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# 맞추기 표
# ---------------------------------------------------------------------------
def load_topic_map(ttl_dir: Path = TTL_DIR) -> dict:
    """주제 맞추기 표. approved: {이름: 대표 이름}(확정한 것), pending: 아직 확정하지 않은 이름 목록."""
    g = read(ttl_dir / "maps" / "topic.ttl")
    approved = {}
    for topic in g.subjects(RDF.type, SKOS.Concept):
        representative = str(g.value(topic, SKOS.prefLabel))
        approved[representative] = representative
        for alt in g.objects(topic, SKOS.altLabel):
            approved[str(alt)] = representative
    pending = sorted(str(g.value(row, CARD.name)) for row in g.subjects(RDF.type, CARD.PendingMapping))
    return {"approved": approved, "pending": pending}


def load_category_map(ttl_dir: Path = TTL_DIR) -> dict:
    """업종 맞추기 표. rows: benefit_id, category(확정한 업종 또는 None), status(approved 또는 not_linked)."""
    g = read(ttl_dir / "maps" / "category.ttl", ttl_dir / "card.ttl")
    rows = []
    for benefit, category in g.subject_objects(CARD.IN_CATEGORY):
        if g.value(benefit, CARD.benefit_id) is not None:
            rows.append({"benefit_id": str(g.value(benefit, CARD.benefit_id)),
                         "category": str(g.value(category, SKOS.prefLabel)), "status": "approved"})
    for row in g.subjects(RDF.type, CARD.PendingMapping):
        rows.append({"benefit_id": str(g.value(row, CARD.benefit_id)), "category": None, "status": str(g.value(row, CARD.status))})
    return {"rows": sorted(rows, key=lambda r: r["benefit_id"])}


# ---------------------------------------------------------------------------
# 검사 규칙: SHACL
# ---------------------------------------------------------------------------
def node_iri(node: dict) -> URIRef:
    """그래프 노드에 붙일 주소. 상담과 조항은 다른 노드가 가리킬 수 있어 키 값으로 주소를 만듦."""
    props = node["props"]
    if node["label"] == "Consultation" and props.get("record_id"):
        return CARD[f"consultation/{quote(props['record_id'])}"]
    if node["label"] == "Article" and props.get("article_no"):
        return CARD[f"article/{quote(props['article_no'])}"]
    return CARD[f"node/{quote(node['id'])}"]


def describe(node: dict) -> str:
    """보고서에 쓸 개체 이름: 라벨과 키 값(없으면 내용의 앞부분)."""
    props = node["props"]
    key = next((props[k] for k in ("benefit_id", "item_id", "record_id", "article_no", "name") if props.get(k)), None)
    return f"{node['label']} {key or str(props.get('content') or node['id'])[:30]}"


def data_graph(nodes: list[dict], relationships: list[dict], product_ids, record_ids, article_nos) -> Graph:
    """Neo4j에서 꺼낸 노드와 관계를 검사기가 읽는 꼴(RDF)로 바꿈. 라벨은 Class, 속성은 값, 관계는 관계로.

    nodes: [{id, label, props}], relationships: [{source, type, target}].
    참조 무결성 대조용으로 실제로 있는 상품 ID, 상담 ID, 조 번호도 함께 넣음.
    """
    g = Graph()
    iri = {node["id"]: node_iri(node) for node in nodes}
    for node in nodes:
        me = iri[node["id"]]
        g.add((me, RDF.type, CARD[node["label"]]))
        for key, value in node["props"].items():
            if value is not None:
                g.add((me, CARD[key], Literal(value)))
        if node["props"].get("product_id"):  # 상품 키는 가리키는 대상으로도 적음(참조 검사 K07)
            g.add((me, CARD.ofProduct, CARD[f"product/{quote(str(node['props']['product_id']))}"]))
    for rel in relationships:
        g.add((iri[rel["source"]], CARD[rel["type"]], iri[rel["target"]]))
    for pid in product_ids:
        g.add((CARD[f"product/{quote(pid)}"], RDF.type, CARD.CardProduct))
    for rid in record_ids:
        g.add((CARD[f"consultation/{quote(rid)}"], RDF.type, CARD.KnownConsultation))
    for no in article_nos:
        g.add((CARD[f"article/{quote(no)}"], RDF.type, CARD.KnownArticle))
    return g


def run_checks(nodes: list[dict], relationships: list[dict], product_ids, record_ids, article_nos,
               ttl_dir: Path = TTL_DIR) -> dict:
    """검사 규칙(shapes/checks.ttl)을 SHACL 검사기로 돌림. 데이터는 고치지 않고 어긴 개체만 모음.

    반환값: {규칙 ID: [어긴 개체(라벨과 키 값)]}. 한 규칙이 셰이프 둘로 나뉜 것(K06, K06_Article)은 앞 이름으로 모음.
    """
    shapes = read(ttl_dir / "shapes" / "checks.ttl")
    owner = {}
    for shape in shapes.subjects(RDF.type, SH.NodeShape):
        owner[shape] = shape
        for prop in shapes.objects(shape, SH.property):
            owner[prop] = shape
    data = data_graph(nodes, relationships, product_ids, record_ids, article_nos)
    readable = {str(node_iri(node)).split("#")[-1]: describe(node) for node in nodes}
    _, report, _ = validate(data, shacl_graph=shapes, inference="none", advanced=False)
    found = {local(shape).split("_")[0]: set() for shape in owner.values()}
    for result in report.subjects(RDF.type, SH.ValidationResult):
        rule = local(owner[report.value(result, SH.sourceShape)]).split("_")[0]
        focus = str(report.value(result, SH.focusNode)).split("#")[-1]
        found[rule].add(readable.get(focus, focus))
    return {rule: sorted(bad) for rule, bad in sorted(found.items())}
