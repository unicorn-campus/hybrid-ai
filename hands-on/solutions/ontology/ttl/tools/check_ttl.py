"""온톨로지 원본(Turtle)을 기계로 검사함. LLM을 쓰지 않음. 하나라도 어긋나면 종료 코드 1.

스키마 설계 6단계(기계 검증)와 9단계(확정 뒤 다시 검사)가 이 도구를 씀. 승인본과 초안 어느 쪽이든 검사함.

  검사 ①: 모든 Turtle 파일이 문법에 맞게 읽히고, 셰이프 파일이 SHACL 규격에 맞는가
  검사 ②: 검사 규칙의 허용 값(sh:in)이 card.ttl의 값 목록과 같은가(값이 두 곳에 적혀 있어 어긋날 수 있음)
  검사 ③: 셰이프가 겨냥하거나 가리키는 Class가 card.ttl에 뜻과 함께 있는가, 키 속성이 그 Class의 셰이프에 있는가,
          공통 개념(rdfs:subClassOf card:CommonConcept)인 노드 타입마다 채우는 방법(card:fill)이 적혀 있는가
  검사 ④: Turtle에서 만든 그래프 스키마가 쓸 수 있는 꼴인가(GraphSchema 검증, 이름 규칙, 설명 유무, 목록 밖 허용 꺼짐,
          Community 판이 지원하는 제약만), 저장된 파일과 같은가(생성물을 손으로 고쳤는지 잡음)
  검사 ⑤: 설계 입력과 맞는가. 원천별 라벨과 키가 원천 목록 표(sources.json)에, 허용 값이 값 목록 파일에 있는가,
          관계의 출발과 도착이 등록된 Class인가, 반대 이름과 인덱싱이 더하는 이름이 다른 이름과 겹치지 않는가,
          건너가는 지점(crossing_points.json)마다 경로가 적혀 있는가
  검사 ⑥: 맞추기 표가 맞는가. 확정한 업종이 값 목록 안에 있는가, 같은 주제 이름이 두 대표 이름에 걸치지 않는가

실행(ttl 폴더에서):
  python tools/check_ttl.py            승인본(ttl/)을 검사하고 저장된 graph_schema.json과 대조함 → output/check_ttl.json
  python tools/check_ttl.py --draft    초안(schema/doc-ontology/draft-ttl/)을 검사하고 schema_draft.json과 대조함
  python tools/check_ttl.py --draft --schema none   초안만 검사함(스키마 초안 파일을 아직 만들지 않았을 때)
"""
import argparse
import copy
import json
import re
import sys
from pathlib import Path

from pyshacl import validate
from rdflib import Graph
from rdflib.collection import Collection
from rdflib.namespace import OWL, RDF, RDFS, SKOS

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent))
import ttl_write as w  # noqa: E402
from ttl_write import BASE_DIR, CARD, DRAFT_DIR, SH, TTL_DIR, turtle  # noqa: E402
from core_turtle import local  # noqa: E402

NODE_NAME, REL_NAME = re.compile(r"^[A-Z][A-Za-z0-9]*$"), re.compile(r"^[A-Z][A-Z0-9_]*$")
SUPPORTED_CONSTRAINTS = {"UNIQUENESS"}  # Neo4j Community 판이 지원하는 제약
SCHEMA_FILES = {"saved": "graph_schema.json", "draft": "output/schema_draft.json"}


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def run(ttl_dir: Path, schema_mode: str = "saved") -> dict:
    """검사를 돌리고 보고(dict)를 돌려줌. 저장하거나 종료하지 않음. schema_mode: saved, draft, none."""
    problems = []
    files = sorted(ttl_dir.rglob("*.ttl"))
    report = {"ttl_dir": ttl_dir.relative_to(w.PROJECT).as_posix(), "schema_mode": schema_mode, "files": len(files)}

    # 검사 ①
    graphs = {}
    for path in files:
        try:
            graphs[path.relative_to(ttl_dir).as_posix()] = Graph().parse(path, format="turtle")
        except Exception as error:
            problems.append(f"① {path.name}: 문법 오류 {str(error).splitlines()[0][:160]}")
    missing = [name for name in w.FILES if name not in graphs and not any(p.startswith(f"① {Path(name).name}") for p in problems)]
    problems += [f"① {name}: 파일이 없음" for name in missing]
    for name, graph in graphs.items():
        if name.startswith("shapes/"):
            ok, _, text = validate(Graph(), shacl_graph=graph, meta_shacl=True)
            if not ok:
                problems.append(f"① {name}: SHACL 규격에 맞지 않음 {text[:200]}")
    if problems:  # 읽히지 않으면 뒤 검사를 할 수 없음
        return {**report, "ok": False, "problems": problems}
    card, checks = graphs["card.ttl"], graphs["shapes/checks.ttl"]
    concepts = turtle.load_concepts(ttl_dir)

    # 검사 ②
    values = {c["id"]: c["allowed_values"]["values"] for c in concepts["classes"] if c["allowed_values"]}
    for shape in checks.subjects(RDF.type, SH.NodeShape):
        target = checks.value(shape, SH.targetClass)
        for row in checks.objects(shape, SH.property):
            in_list = checks.value(row, SH["in"])
            if in_list is not None and local(target) in values:
                listed = [str(v) for v in Collection(checks, in_list)]
                if listed != values[local(target)]:
                    problems.append(f"② {local(shape)}: 허용 값 {listed}이 card.ttl의 값 목록 {values[local(target)]}과 다름")

    # 검사 ③
    defined = {cls for cls in card.subjects(RDF.type, OWL.Class) if card.value(cls, SKOS.definition) is not None}
    common = set(turtle.common_concepts(card))
    for doc_type in turtle.DOC_TYPES:
        graph = graphs[f"shapes/{doc_type}.ttl"]
        for shape in graph.subjects(RDF.type, SH.NodeShape):
            target = graph.value(shape, SH.targetClass)
            paths = {local(graph.value(row, SH.path)) for row in graph.objects(shape, SH.property)}
            if target not in defined:
                problems.append(f"③ {doc_type}: {local(target)}의 뜻이 card.ttl에 없음")
            lost = [k for k in turtle.key_names(card, target) if k not in paths]
            if lost:
                problems.append(f"③ {doc_type}: {local(target)}의 키 속성 {lost}이 셰이프에 없음")
            if target in common and graph.value(shape, CARD.fill) is None:
                problems.append(f"③ {doc_type}: {local(target)}의 채우는 방법(card:fill)이 없음")
            for row in graph.objects(shape, SH.property):
                pointed = graph.value(row, SH["class"])
                if pointed is not None and pointed not in defined:
                    problems.append(f"③ {doc_type}: 패턴이 가리키는 {local(pointed)}의 뜻이 card.ttl에 없음")

    # 검사 ④
    from neo4j_graphrag.components.schema import GraphSchema
    schemas = {}
    for doc_type in turtle.DOC_TYPES:
        try:
            schema = schemas[doc_type] = turtle.graph_schema(doc_type, ttl_dir)
        except Exception as error:
            problems.append(f"④ {doc_type}: 그래프 스키마를 만들지 못함 {type(error).__name__}: {str(error)[:120]}")
            continue
        labels = [n["label"] for n in schema["node_types"]]
        bad = sorted({l for l in labels if labels.count(l) > 1}) + [l for l in labels if not NODE_NAME.match(l)]
        bad += [r["label"] for r in schema["relationship_types"] if not REL_NAME.match(r["label"])]
        if bad:
            problems.append(f"④ {doc_type}: 라벨이 겹치거나 이름 규칙에 맞지 않음 {bad}")
        empty = [t["label"] for t in schema["node_types"] + schema["relationship_types"] if not (t.get("description") or "").strip()]
        empty += [f"{n['label']}.{p['name']}" for n in schema["node_types"] for p in n["properties"] if not (p.get("description") or "").strip()]
        if empty:
            problems.append(f"④ {doc_type}: 설명이 없음 {empty}")
        if any(schema.get(flag) for flag in turtle.SCHEMA_FLAGS):
            problems.append(f"④ {doc_type}: 목록 밖 허용(additional_*)이 켜져 있음")
        try:
            validated = GraphSchema.model_validate(copy.deepcopy(schema))  # 원본을 넘기면 dict 안의 패턴이 바뀔 수 있음
            kinds = {str(getattr(c.type, "value", c.type)) for c in validated.constraints}
            if not kinds <= SUPPORTED_CONSTRAINTS:
                problems.append(f"④ {doc_type}: 지원하지 않는 제약 {sorted(kinds - SUPPORTED_CONSTRAINTS)}(필수 속성을 쓰면 생김)")
        except Exception as error:
            problems.append(f"④ {doc_type}: GraphSchema 검증 실패 {str(error)[:200]}")
        if schema_mode in SCHEMA_FILES:
            stored = BASE_DIR / doc_type / SCHEMA_FILES[schema_mode]
            if not stored.exists() or load_json(stored) != schema:
                problems.append(f"④ {doc_type}: {SCHEMA_FILES[schema_mode]}이 Turtle에서 만든 것과 다름(tools/build_from_ttl.py로 다시 만듦)")

    # 검사 ⑤
    sources = {(s["name"], l["label"]): l for s in load_json(BASE_DIR / "sources.json")["sources"] for l in s["labels"]}
    value_lists = load_json(BASE_DIR / "inputs" / "value_lists.json")["lists"]
    class_names = {c["name"] for c in concepts["classes"]}
    for cls in concepts["classes"]:
        for row in cls["source_labels"]:
            label = sources.get((row["source"], row["label"]))
            if label is None or any(k not in label["properties"] for k in row["key_properties"]):
                problems.append(f"⑤ Class {cls['name']}: {row['source']}의 {row['label']}과 키 {row['key_properties']}가 원천 목록 표에 없음")
        if cls["allowed_values"]:
            listed = [v["name"] if isinstance(v, dict) else v for v in value_lists.get(cls["name"], {}).get("values", [])]
            if cls["allowed_values"]["values"] != listed:
                problems.append(f"⑤ Class {cls['name']}: 허용 값이 값 목록 파일과 다름")
    node_names = {n["label"] for s in schemas.values() for n in s["node_types"]}
    relation_names = {r["label"] for s in schemas.values() for r in s["relationship_types"]}
    added_relations = {local(p) for p in card.subjects(RDF.type, OWL.ObjectProperty) if card.value(p, CARD.addedBy) is not None}
    added_classes = {local(c) for c in card.subjects(RDF.type, OWL.Class) if card.value(c, CARD.addedBy) is not None}
    clash = sorted((added_classes & node_names) | (added_relations & relation_names))
    if clash:
        problems.append(f"⑤ 인덱싱이 더하는 이름이 문서 스키마의 이름과 겹침 {clash}")
    inverses = [r["inverse"] for r in concepts["relations"] if r["inverse"]]
    for relation in concepts["relations"]:
        unknown = [c for c in relation["source_class"] + [relation["target_class"]] if c not in class_names]
        if unknown:
            problems.append(f"⑤ 관계 {relation['label']}: 출발이나 도착이 등록된 Class가 아님 {unknown}")
        if relation["label"] not in relation_names | added_relations:
            problems.append(f"⑤ 관계 {relation['label']}: 어느 문서 스키마에도, 인덱싱이 더하는 관계에도 없음")
        inverse = relation["inverse"]
        if inverse and (inverse in relation_names | added_relations or inverses.count(inverse) > 1):
            problems.append(f"⑤ 관계 {relation['label']}: 반대 이름 {inverse}이 다른 이름과 겹침")
    paths = {p["crossing_point"] for p in turtle.crossing_paths(ttl_dir)}
    for point in load_json(BASE_DIR / "crossing_points.json")["crossing_points"]:
        if point["id"] not in paths:
            problems.append(f"⑤ 건너가는 지점 {point['id']}({point['question']})을 지나는 경로가 card.ttl에 없음")

    # 검사 ⑥
    topic, category = turtle.load_topic_map(ttl_dir), turtle.load_category_map(ttl_dir)["rows"]
    categories = next((c["allowed_values"]["values"] for c in concepts["classes"] if c["id"] == "Category"), [])
    outside = sorted({r["category"] for r in category if r["status"] == "approved"} - set(categories))
    if outside:
        problems.append(f"⑥ 업종 맞추기 표: 값 목록 밖의 업종 {outside}")
    seen = {}
    for g in [graphs["maps/topic.ttl"]]:
        for node in g.subjects(RDF.type, SKOS.Concept):
            for name in [g.value(node, SKOS.prefLabel), *g.objects(node, SKOS.altLabel)]:
                seen.setdefault(re.sub(r"\s+", "", str(name)).lower(), set()).add(str(g.value(node, SKOS.prefLabel)))
    twice = sorted(name for name, reps in seen.items() if len(reps) > 1)
    if twice:
        problems.append(f"⑥ 주제 맞추기 표: 한 이름이 대표 이름 둘에 걸침 {twice}")
    both = sorted(set(topic["pending"]) & set(topic["approved"]))
    if both:
        problems.append(f"⑥ 주제 맞추기 표: 확정한 이름이 확정 전 목록에도 있음 {both}")

    return {**report, "ok": not problems, "problems": problems, "signature": turtle.signature(ttl_dir),
            "classes": len(concepts["classes"]), "relations": len(concepts["relations"]), "checks": len(concepts["checks"]),
            "paths": len(paths), "topic_approved": len(topic["approved"]), "topic_pending": len(topic["pending"]),
            "category_approved": sum(1 for r in category if r["status"] == "approved"), "category_rows": len(category)}


def show(report: dict) -> None:
    line = f"온톨로지 원본 검사({report['ttl_dir']}): {'통과' if report['ok'] else '실패'} (Turtle 파일 {report['files']}개"
    if "classes" in report:
        line += (f", Class {report['classes']}개, 관계 {report['relations']}개, 검사 규칙 {report['checks']}개, "
                 f"건너가는 경로 {report['paths']}개, 주제 확정 이름 {report['topic_approved']}개와 확정 전 {report['topic_pending']}개, "
                 f"업종 확정 {report['category_approved']}/{report['category_rows']}행")
    print(line + ")")
    for problem in report["problems"]:
        print("  어긋남:", problem)


def main() -> None:
    parser = argparse.ArgumentParser(description="온톨로지 원본(Turtle) 검사")
    parser.add_argument("--draft", action="store_true", help="승인본 대신 초안 폴더를 검사함")
    parser.add_argument("--schema", choices=["saved", "draft", "none"], help="대조할 스키마 파일(기본: 승인본은 saved, 초안은 draft)")
    args = parser.parse_args()
    ttl_dir = DRAFT_DIR if args.draft else TTL_DIR
    if not ttl_dir.exists():
        raise SystemExit(f"폴더가 없음: {ttl_dir}. 초안은 tools/draft.py start로 만듦")
    report = run(ttl_dir, args.schema or ("draft" if args.draft else "saved"))
    out = ttl_dir / "output" / "check_ttl.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    show(report)
    sys.exit(0 if report["ok"] else 1)


if __name__ == "__main__":
    main()
