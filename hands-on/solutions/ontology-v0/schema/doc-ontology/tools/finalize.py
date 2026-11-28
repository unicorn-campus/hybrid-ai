"""9단계 [단계 ⑤]: 8단계에서 통과를 승인한 온톨로지 초안(Turtle)을 승인본으로 올리고, 그래프 스키마와 승인 기록을 남김.

- 온톨로지: 초안 폴더(draft-ttl/)를 승인본(ttl/)으로 올림(ttl/tools/draft.py의 promote). 올리기 전에 승인본이 초안을 시작한 뒤
  바뀌지 않았는지와 초안이 기계 검사를 통과하는지 보고, 올린 뒤 승인본을 다시 검사함. 초안이 없으면 올리지 않고 기록만 다시 씀
- 스키마: {문서 종류}/graph_schema.json은 승인본 Turtle에서 만들어 냄(손으로 쓰지 않음). 한글 그대로 UTF-8로 쓰고,
  다시 읽어 GraphSchema로 검증함. 제약은 Community 판이 지원하는 UNIQUENESS만이어야 함
- 추출 단위 글 규칙: {문서 종류}/unit_text_rules.json(청크를 추출 단위로 나누는 규칙, 단위 앞에 붙일 머리줄 칸).
  인덱싱이 스키마 설계와 같은 글로 추출하도록 따로 남김. 인덱서는 graph_schema.json과 이 파일과 Turtle 승인본을 읽음
- 승인 기록: {문서 종류}/approval.json(승인자, 일시, 청크 출처, 입력 파일 SHA-256, 온톨로지 판과 지문, 마지막 시험 지표,
  추출 절차). 사람이 확인하는 기록이라 인덱서는 읽지 않음
실행: python tools/finalize.py regulation benefit_guide consult_log
"""

from __future__ import annotations

import copy
import sys
from datetime import datetime

from neo4j_graphrag.components.schema import GraphSchema

from common import BASE_DIR, DECISIONS_PATH, SNAPSHOT_PATH, load_chunks, load_decisions, read_json, rel, sha256_of, write_json
from units import HEADER_FIELDS, header_of, header_values, split_chunk

import draft as draft_tool  # ttl/tools(common이 경로를 넣어 줌)
import ttl_write

turtle = ttl_write.turtle
APPROVER = "hiondal(사용자)"
UNIT_CODE = "tools/units.py(split_chunk, header_of version 2, header_values)"


def schema_record(doc_type: str) -> dict:
    """승인본 Turtle에서 만들어진 graph_schema.json을 다시 읽어 검증하고 기록할 값을 돌려줌."""
    path = BASE_DIR / doc_type / "graph_schema.json"
    stored = read_json(path)
    schema = GraphSchema.model_validate(copy.deepcopy(stored))
    kinds = sorted({str(getattr(c.type, "value", c.type)) for c in schema.constraints})
    result = {"path": rel(path), "node_types": len(schema.node_types), "relationship_types": len(schema.relationship_types),
              "patterns": len(schema.patterns), "constraints": len(schema.constraints), "constraint_types": kinds,
              "community_ok": set(kinds) <= {"UNIQUENESS"}, "same_as_turtle": stored == turtle.graph_schema(doc_type, ttl_write.TTL_DIR),
              "sha256": sha256_of(path)}
    print(doc_type, result)
    if not (result["community_ok"] and result["same_as_turtle"]):
        raise SystemExit(f"{doc_type}: graph_schema.json이 승인본 Turtle과 다르거나 지원하지 않는 제약이 있음")
    return result


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
    promoted = None
    if ttl_write.DRAFT_DIR.exists():
        promoted = draft_tool.promote()  # 검사 → 승인본으로 복사 → graph_schema.json 만들기 → 승인본 다시 검사
    else:
        print("초안 폴더가 없음: 승인본은 그대로 두고 기록만 다시 씀")
    schemas = {d: schema_record(d) for d in doc_types}
    concepts = turtle.load_concepts(ttl_write.TTL_DIR)
    ontology = {"dir": rel(ttl_write.TTL_DIR), "version": concepts["version"], "signature": turtle.signature(ttl_write.TTL_DIR),
                "classes": len(concepts["classes"]), "relations": len(concepts["relations"]), "checks": len(concepts["checks"]),
                "changed_files": [c["file"] for c in promoted["changed"]] if promoted else []}
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
            "ontology": ontology,  # 온톨로지 원본(Turtle 승인본)의 판 번호와 내용 지문
            "last_test": last_metrics(d),
            "unit_text_rules": {"path": rel(rules_path), "sha256": sha256_of(rules_path)},  # 나누는 규칙과 머리줄 칸은 이 파일에 있음
            "extraction": {
                "header_fill": "추출 뒤 tools/fill_test.py의 apply_header로 머리줄 값을 넣음(채우는 방법이 「머리줄 값」인 속성과 연결)",
                "prompt_template": "라이브러리 기본 ERExtractionTemplate에서 입력 글만 <input_text> 태그로 감쌈(tools/fill_test.py의 tagged_template)",
                "llm": {"provider": "groq", "model": load_decisions()["input"]["llm_model"], "json_mode": False, "max_tokens": 16000,
                        "reasoning_effort": "medium", "temperature": 0},
                "retries": "형식 오류와 내용이 있는 단위의 빈 그래프는 같은 입력으로 2번까지 다시 물음",
                "pruning": "GraphPruning(schema=graph_schema.json)",
                "value_maps": "업종과 주제는 확정한 행만 씀(ttl/maps/category.ttl, ttl/maps/topic.ttl)",
            },
        }
        write_json(BASE_DIR / d / "approval.json", approval)
        print(d, "추출 단위 글 규칙과 승인 기록 저장")
    decisions = load_decisions()
    decisions["steps"].append({"step": "9", "title": "[단계 ⑤] 스키마와 온톨로지 확정(Turtle 원본)", "date": datetime.now().date().isoformat(),
                               "content": {"doc_types": doc_types, "schemas": schemas, "ontology": ontology}})
    write_json(DECISIONS_PATH, decisions)


if __name__ == "__main__":
    main(sys.argv[1:])
