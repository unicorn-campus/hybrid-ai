"""6단계 [단계 ③ 검증]: 문서 종류별 스키마 초안과 공통 개념 층 초안을 기계로 검사함.

검사 항목(프롬프트 6단계)
- 스키마: 노드 타입 라벨 중복, 이름 규칙, description 유무, GraphSchema.model_validate 통과(사본으로),
  쓰는 Neo4j 판이 지원하지 않는 제약(Community 판은 UNIQUENESS만)
- 공통 노드 타입: 쓰이는 모든 문서 종류 초안에서 라벨, description, 키 속성이 같은지
- 공통 개념 층
  - 문서 쪽: 적은 라벨과 키 속성이 스키마 초안에 있는지, 인덱싱이 더하는 라벨과 관계가 스키마 이름과 겹치지 않는지
  - 뜻: Class에 대응하는 노드 타입의 description 첫머리가 공통 개념 층의 뜻과 같은지
  - 다른 원천: 원천별 라벨과 키 속성이 원천 목록 표(sources.json)에 있는지
  - 허용 값: 값 목록이 값 목록 파일과 같은지, 상위와 하위에 쓴 값이 허용 값 안에 있는지
  - 관계: 출발 Class와 도착 Class가 등록된 Class인지, 반대 이름이 다른 관계 이름과 겹치지 않는지
  - 경로: 2단계의 건너가는 지점마다 경로가 있는지
실행: python common/tools/check_concepts.py [--saved]
  --saved: 9단계에서 저장한 graph_schema.json과 concepts.json을 기준으로 다시 검사함
만드는 파일: common/output/check_concepts.json
"""

from __future__ import annotations

import copy
import json
import re
import sys
from pathlib import Path

from neo4j_graphrag.components.schema import GraphSchema

BASE = Path(__file__).resolve().parents[2]  # schema/doc-ontology
DOC_TYPES = ["regulation", "benefit_guide", "consult_log"]
NODE_NAME = re.compile(r"^[A-Z][A-Za-z0-9]*$")
REL_NAME = re.compile(r"^[A-Z][A-Z0-9_]*$")
SUPPORTED_CONSTRAINTS = {"UNIQUENESS"}  # Neo4j Community 판

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    saved = "--saved" in sys.argv
    schemas = {}
    for doc in DOC_TYPES:
        path = BASE / doc / ("graph_schema.json" if saved else "output/schema_draft.json")
        if path.exists():
            schemas[doc] = read(path)
    concepts = read(BASE / "common" / ("concepts.json" if saved else "output/concepts_draft.json"))
    sources = read(BASE / "sources.json")["sources"]
    value_lists = read(BASE / "inputs/value_lists.json")["lists"]
    crossing = read(BASE / "crossing_points.json")["crossing_points"]
    results = []

    def check(group: str, name: str, ok: bool, detail: str = "") -> None:
        results.append({"group": group, "check": name, "passed": bool(ok), "detail": detail})
        print(("통과" if ok else "실패"), f"[{group}] {name}", ("- " + detail) if detail else "")

    # 1. 문서 종류별 스키마
    for doc, schema in schemas.items():
        labels = [n["label"] for n in schema["node_types"]]
        dup = sorted({l for l in labels if labels.count(l) > 1})
        check(doc, "노드 타입 라벨 중복 없음", not dup, ", ".join(dup))
        bad_nodes = [l for l in labels if not NODE_NAME.match(l)]
        bad_rels = [r["label"] for r in schema["relationship_types"] if not REL_NAME.match(r["label"])]
        check(doc, "이름 규칙", not bad_nodes and not bad_rels, ", ".join(bad_nodes + bad_rels))
        no_desc = [t["label"] for t in schema["node_types"] + schema["relationship_types"] if not (t.get("description") or "").strip()]
        no_desc += [f"{n['label']}.{p['name']}" for n in schema["node_types"] for p in n.get("properties", [])
                    if not (p.get("description") or "").strip()]
        check(doc, "모든 타입과 속성에 description 있음", not no_desc, ", ".join(no_desc))
        try:
            validated = GraphSchema.model_validate(copy.deepcopy(schema))  # 원본을 넘기면 dict 안의 패턴이 바뀔 수 있음
            check(doc, "GraphSchema.model_validate 통과", True,
                  f"노드 {len(validated.node_types)}, 관계 {len(validated.relationship_types)}, "
                  f"패턴 {len(validated.patterns)}, 제약 {len(validated.constraints)}")
            kinds = sorted({str(getattr(c.type, 'value', c.type)) for c in validated.constraints})
            check(doc, "제약은 Community 판이 지원하는 것만", set(kinds) <= SUPPORTED_CONSTRAINTS, ", ".join(kinds))
        except Exception as error:
            check(doc, "GraphSchema.model_validate 통과", False, str(error)[:300])
        flags = [k for k in ("additional_node_types", "additional_relationship_types", "additional_patterns") if schema.get(k)]
        check(doc, "additional_* 모두 false", not flags, ", ".join(flags))

    # 2. 공통 노드 타입이 모든 문서 종류에서 같은지
    for cls in concepts["classes"]:
        shared = [d for d in cls.get("doc_labels", []) if d.get("shared")]
        if not shared:
            continue
        seen = {}
        for d in shared:
            node = next((n for n in schemas.get(d["doc_type"], {}).get("node_types", []) if n["label"] == d["label"]), None)
            if node:
                keys = sorted(c["property_names"][0] if len(c["property_names"]) == 1 else "+".join(c["property_names"])
                              for c in schemas[d["doc_type"]].get("constraints", []) if c.get("node_type") == d["label"])
                seen[d["doc_type"]] = (node["label"], node.get("description"),
                                       json.dumps(node.get("properties"), ensure_ascii=False), tuple(keys))
        same = len(set(seen.values())) <= 1
        check("공통 노드", f"{cls['name']}: 라벨, description, 속성, 키가 모든 문서 종류에서 같음", same and len(seen) == len(shared),
              ", ".join(seen))

    # 3. 공통 개념 층: 문서 쪽 라벨과 키, 뜻
    schema_rel_names = {r["label"] for s in schemas.values() for r in s["relationship_types"]}
    schema_node_names = {n["label"] for s in schemas.values() for n in s["node_types"]}
    for cls in concepts["classes"]:
        for d in cls.get("doc_labels", []):
            if d["fill"] == "맞추기 표":
                continue  # 인덱싱이 더하는 라벨은 아래에서 따로 봄
            schema = schemas.get(d["doc_type"])
            node = next((n for n in (schema or {}).get("node_types", []) if n["label"] == d["label"]), None)
            props = {p["name"] for p in (node or {}).get("properties", [])}
            missing = [k for k in d.get("key_properties", []) if k not in props]
            check("개념 층 문서 쪽", f"{cls['name']}: {d['doc_type']}.{d['label']}과 키 속성이 스키마에 있음",
                  node is not None and not missing, ", ".join(missing))
            if node is not None and d.get("role") == "노드":  # 키만 가리키는 노드(키 참조)는 다른 Class의 노드라 뜻 검사에서 뺌
                check("개념 층 뜻", f"{cls['name']}: {d['doc_type']}.{d['label']}의 description 첫머리가 뜻과 같음",
                      (node.get("description") or "").startswith(cls["definition"]))
    adds = concepts.get("indexer_adds", {})
    for cls in concepts["classes"]:  # 맞추기 표로 채우는 라벨은 인덱싱이 더하는 라벨에 적혀 있어야 함
        for d in cls.get("doc_labels", []):
            if d["fill"] == "맞추기 표":
                check("개념 층 문서 쪽", f"{cls['name']}: 맞추기 표로 채우는 {d['label']}이 「인덱싱이 더하는 라벨」에 있음",
                      d["label"] in {l["label"] for l in adds.get("labels", [])})
    clash = [l for l in adds.get("labels", []) if l["label"] in schema_node_names]
    clash += [r for r in adds.get("relationships", []) if r["label"] in schema_rel_names]
    check("개념 층 문서 쪽", "인덱싱이 더하는 라벨과 관계가 스키마 이름과 겹치지 않음", not clash,
          ", ".join(x["label"] for x in clash))

    # 4. 다른 원천
    source_index = {(s["name"], l["label"]): l for s in sources for l in s["labels"]}
    for cls in concepts["classes"]:
        for s in cls.get("source_labels", []):
            label = source_index.get((s["source"], s["label"]))
            missing = [k for k in s.get("key_properties", []) if not label or k not in label["properties"]]
            check("개념 층 다른 원천", f"{cls['name']}: {s['source']}의 {s['label']}과 키 속성이 원천 목록 표에 있음",
                  label is not None and not missing, ", ".join(missing))

    # 5. 허용 값과 상하위
    for cls in concepts["classes"]:
        allowed = cls.get("allowed_values")
        if not allowed:
            continue
        source_values = value_lists[allowed["list"]]["values"]
        source_values = [v["name"] if isinstance(v, dict) else v for v in source_values]
        check("허용 값", f"{cls['name']}: 값 목록이 값 목록 파일과 같음", allowed["values"] == source_values,
              f"개념 층 {len(allowed['values'])}개, 파일 {len(source_values)}개")
        hierarchy = allowed.get("hierarchy")
        if isinstance(hierarchy, list):
            outside = [v for h in hierarchy for v in [h["parent"], *h["children"]] if v not in allowed["values"]]
            check("허용 값", f"{cls['name']}: 상위와 하위 값이 모두 허용 값 안에 있음", not outside, ", ".join(outside))

    # 6. 관계: 출발과 도착 Class, 반대 이름
    class_names = {c["name"] for c in concepts["classes"]}
    all_rel_names = schema_rel_names | {r["label"] for r in adds.get("relationships", [])}
    inverses = [r["inverse"] for r in concepts["relations"] if r.get("inverse")]
    for rel in concepts["relations"]:
        ends = (rel["source_class"] if isinstance(rel["source_class"], list) else [rel["source_class"]]) + [rel["target_class"]]
        unknown = [c for c in ends if c not in class_names]
        check("관계", f"{rel['label']}: 출발과 도착 Class가 등록된 Class임", not unknown, ", ".join(unknown))
        check("관계", f"{rel['label']}: 스키마나 인덱싱이 더하는 관계에 있음", rel["label"] in all_rel_names)
        if rel.get("inverse"):
            check("관계", f"{rel['label']}: 반대 이름 {rel['inverse']}이 다른 관계 이름과 겹치지 않음",
                  rel["inverse"] not in all_rel_names and inverses.count(rel["inverse"]) == 1)

    # 7. 경로: 건너가는 지점마다 경로가 있는지
    paths = {p["crossing_point"] for p in concepts.get("paths", [])}
    for point in crossing:
        check("경로", f"{point['id']}({point['question']}): 지나는 경로가 있음", point["id"] in paths)

    passed = all(r["passed"] for r in results)
    out = BASE / "common" / "output" / "check_concepts.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"mode": "saved" if saved else "draft", "passed": passed,
                               "total": len(results), "failed": sum(not r["passed"] for r in results),
                               "results": results}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"\n판정: {'통과' if passed else '실패'} ({len(results)}개 검사 중 실패 {sum(not r['passed'] for r in results)}개)")
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
