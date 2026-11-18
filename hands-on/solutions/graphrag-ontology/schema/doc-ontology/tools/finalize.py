"""9단계 [단계 ⑤]: 8단계에서 통과를 승인한 문서 종류의 스키마와 공통 개념 층을 함께 저장함.

- 스키마: GraphSchema.save()로 {문서 종류}/graph_schema.json을 쓰고, GraphSchema.from_file()로 다시 읽어
  노드 타입, 관계, 패턴, 제약 수가 검증된 초안과 같은지 비교함. 제약은 Community 판이 지원하는 UNIQUENESS만이어야 함
- 공통 개념 층: concepts_draft.json에서 통과한 문서 종류와 관련된 내용을 common/concepts.json에 보탬.
  저장 전에 기존 층의 판 번호와 SHA-256 값이 1단계 기록과 같은지 비교함(다르면 저장하지 않음)
- 추출 단위 글 규칙: {문서 종류}/unit_text_rules.json(청크를 추출 단위로 나누는 규칙, 단위 앞에 붙일 머리줄 칸).
  인덱싱이 스키마 설계와 같은 글로 추출하도록 따로 남김. 인덱서는 graph_schema.json과 이 파일만 읽음
- 승인 기록: {문서 종류}/approval.json(승인자, 일시, 청크 출처, 입력 파일 SHA-256, 공통 개념 층 판, 마지막 시험 지표,
  추출 절차). 사람이 확인하는 기록이라 인덱서는 읽지 않음
실행: python tools/finalize.py regulation benefit_guide consult_log
"""

from __future__ import annotations

import copy
import json
import sys
from datetime import datetime

from neo4j_graphrag.components.schema import GraphSchema

from common import BASE_DIR, DECISIONS_PATH, SNAPSHOT_PATH, load_chunks, load_decisions, read_json, rel, sha256_of, write_json
from units import HEADER_FIELDS, header_of, header_values, split_chunk

CONCEPTS = BASE_DIR / "common/concepts.json"
DRAFT = BASE_DIR / "common/output/concepts_draft.json"
APPROVER = "hiondal(사용자)"
UNIT_CODE = "tools/units.py(split_chunk, header_of version 2, header_values)"


def counts(schema: GraphSchema) -> dict:
    return {"node_types": len(schema.node_types), "relationship_types": len(schema.relationship_types),
            "patterns": len(schema.patterns), "constraints": len(schema.constraints)}


def save_schema(doc_type: str) -> dict:
    draft = read_json(BASE_DIR / doc_type / "output/schema_draft.json")
    validated = GraphSchema.model_validate(copy.deepcopy(draft))
    path = BASE_DIR / doc_type / "graph_schema.json"
    validated.save(str(path))
    reloaded = GraphSchema.from_file(str(path))
    kinds = sorted({str(getattr(c.type, "value", c.type)) for c in reloaded.constraints})
    result = {"path": rel(path), "validated": counts(validated), "reloaded": counts(reloaded),
              "same": counts(validated) == counts(reloaded), "constraint_types": kinds,
              "community_ok": set(kinds) <= {"UNIQUENESS"}, "sha256": sha256_of(path)}
    print(doc_type, result)
    if not (result["same"] and result["community_ok"]):
        raise SystemExit(f"{doc_type}: 저장 뒤 다시 읽은 스키마가 초안과 다르거나 지원하지 않는 제약이 있음")
    return result


def save_concepts(doc_types: list[str]) -> dict:
    existing = load_decisions()["input"]["existing_concept_layer"]
    if CONCEPTS.exists():
        now = read_json(CONCEPTS)
        if existing.get("sha256") is None or sha256_of(CONCEPTS) != existing["sha256"]:
            raise SystemExit("공통 개념 층이 1단계 기록과 다름(그 사이 다른 설계가 고친 것). 저장하지 않음")
        old_classes = {c["name"]: c for c in now["classes"]}
    else:
        now, old_classes = None, {}
    draft = read_json(DRAFT)
    keep = set(doc_types)
    classes = []
    for cls in draft["classes"]:
        cls = copy.deepcopy(cls)
        cls["doc_labels"] = [d for d in cls.get("doc_labels", []) if d["doc_type"] in keep]
        if cls["doc_labels"] or cls.get("source_labels"):
            classes.append(cls)
    names = {c["name"] for c in classes}
    relations = [r for r in draft["relations"] if set(r.get("doc_types", [])) & keep]
    layer = {
        "version": "1",
        "status": "approved",
        "approved": {"by": APPROVER, "at": datetime.now().isoformat(timespec="seconds"),
                     "how": "8단계에서 스키마와 함께 통과를 승인함(review/step8.md 라운드 3, 4)"},
        "purpose": draft["purpose"],
        "sources": draft["sources"], "value_list_file": draft["value_list_file"],
        "header_fill_rule": draft.get("header_fill_rule"),
        "doc_types": sorted(keep),
        "classes": classes,
        "relations": relations,
        "checks": draft["checks"],
        "indexer_adds": draft["indexer_adds"],
        "paths": draft["paths"],
        "value_maps": {
            "업종": {"file": "common/category_map_approved.json", "sha256": sha256_of(BASE_DIR / "common/category_map_approved.json")},
            "주제": {"file": "common/topic_map_approved.json", "sha256": sha256_of(BASE_DIR / "common/topic_map_approved.json")},
        },
        "change_log": [{"version": "1", "date": datetime.now().date().isoformat(),
                        "added_classes": sorted(names - set(old_classes)), "changed_classes": [],
                        "affected_doc_types": sorted(keep), "note": "처음 설계라 기존 층 없음. 모두 새로 등록함"}],
    }
    write_json(CONCEPTS, layer)
    print("공통 개념 층 저장:", rel(CONCEPTS), "Class", len(classes), "관계", len(relations))
    return {"path": rel(CONCEPTS), "version": layer["version"], "sha256": sha256_of(CONCEPTS),
            "classes": len(classes), "relations": len(relations)}


def unit_text_rules(doc_type: str, plan: dict) -> dict:
    """추출 단위 글 규칙: 3단계에서 승인한 나누는 규칙과 5단계에서 정한 머리줄 칸(version 2).

    머리줄 칸은 실제 단위 하나의 머리줄에 모두 있는지 확인한 뒤 적음(코드와 기록이 어긋나면 저장하지 않음).
    """
    fields = HEADER_FIELDS[doc_type]
    for chunk in load_chunks(doc_type):
        for unit in split_chunk(doc_type, chunk)[0]:
            if header_values(doc_type, unit) is None:  # 표지, 차례처럼 답이 없어야 하는 단위는 머리줄이 「아님」뿐임
                continue
            header = header_of(doc_type, unit)
            missing = [f for f in fields if f"{f}: " not in header]
            if missing:
                raise SystemExit(f"{doc_type}: 머리줄에 없는 칸 {missing}. units.py의 HEADER_FIELDS와 header_of를 맞출 것")
            return {
                "doc": doc_type,
                # 청크를 추출 단위로 다시 나누는 규칙. heading이 없으면(null) 청크를 그대로 단위로 씀
                "extraction_unit_rule": plan["doc_types"][doc_type]["extraction_unit"],
                # 단위 앞에 머리줄로 붙일 칸(키 속성이 본문에 없어도 채워지게 함)
                "metadata_header": fields,
                "header_version": 2,
                "rule_code": UNIT_CODE,  # 규칙을 실제로 실행하는 코드. 후보 추출, 시험, 인덱싱이 같은 함수를 부름
            }
    raise SystemExit(f"{doc_type}: 머리줄을 확인할 단위가 하나도 없음")


def last_metrics(doc_type: str) -> dict:
    scores = read_json(BASE_DIR / "output/fill_scores.json")
    m = scores["scores"][doc_type]["metrics"]
    return {"round": scores["round"], "topic_basis": scores.get("topic_basis"),
            "questions": {f: {"recall": v["recall"], "same_rate": v["same_rate"], "false_rate": v["false_rate"]} for f, v in m.items()},
            "rules": {k: r["violations"] for k, r in scores["checks"]["rules"].items()},
            "paths": {"P1_linked_complaint_units": scores["checks"]["complaints_linked"], "keys": scores["checks"]["keys"]}}


def main(doc_types: list[str]) -> None:
    schemas = {d: save_schema(d) for d in doc_types}
    layer = save_concepts(doc_types)
    plan = read_json(BASE_DIR / "sample_plan.json")
    snapshot = read_json(SNAPSHOT_PATH)
    inputs = ["chunks_snapshot.json", "competency_questions.md", "crossing_points.json", "sample_plan.json", "decisions.json"]
    for d in doc_types:
        rules_path = BASE_DIR / d / "unit_text_rules.json"
        write_json(rules_path, unit_text_rules(d, plan))
        approval = {
            "doc_type": d,
            "approved_by": APPROVER,
            "approved_at": datetime.now().isoformat(timespec="seconds"),
            "chunk_source": {"chroma_dir": snapshot["chroma_dir"], "collection": snapshot["collection"], "count": snapshot["count"]},
            "input_sha256": {**{f: sha256_of(BASE_DIR / f) for f in inputs},
                             f"{d}/expected_answers.json": sha256_of(BASE_DIR / d / "expected_answers.json")},
            "graph_schema": schemas[d],
            "concept_layer": layer,
            "last_test": last_metrics(d),
            "unit_text_rules": {"path": rel(rules_path), "sha256": sha256_of(rules_path)},  # 나누는 규칙과 머리줄 칸은 이 파일에 있음
            "extraction": {
                "header_fill": "추출 뒤 tools/fill_test.py의 apply_header로 머리줄 값을 넣음(공통 개념 층 header_fill_rule)",
                "prompt_template": "라이브러리 기본 ERExtractionTemplate에서 입력 글만 <input_text> 태그로 감쌈(tools/fill_test.py의 tagged_template)",
                "llm": {"provider": "groq", "model": load_decisions()["input"]["llm_model"], "json_mode": False, "max_tokens": 16000,
                        "reasoning_effort": "medium", "temperature": 0},
                "retries": "형식 오류와 내용이 있는 단위의 빈 그래프는 같은 입력으로 2번까지 다시 물음",
                "pruning": "GraphPruning(schema=graph_schema.json)",
                "value_maps": "업종과 주제는 approved 행만 씀(common/category_map_approved.json, common/topic_map_approved.json)",
            },
        }
        write_json(BASE_DIR / d / "approval.json", approval)
        print(d, "추출 단위 글 규칙과 승인 기록 저장")
    decisions = load_decisions()
    decisions["steps"].append({"step": "9", "title": "[단계 ⑤] 스키마와 공통 개념 층 확정", "date": datetime.now().date().isoformat(),
                               "content": {"doc_types": doc_types, "schemas": schemas, "concept_layer": layer}})
    write_json(DECISIONS_PATH, decisions)


if __name__ == "__main__":
    main(sys.argv[1:])
