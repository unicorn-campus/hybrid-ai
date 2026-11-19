"""9단계: 8단계 통과가 승인된 문서 종류만 GraphSchema 파일, 승인 기록, 추출 청크 글 규칙을 만듦.

스키마를 한글 그대로(UTF-8) 저장한 뒤 다시 읽어 노드 타입, 관계, 패턴, 제약 수가 초안과 같은지 비교함.
GraphSchema.save()는 한글을 \\uXXXX로 바꿔 쓰고, from_file()은 Windows 기본 인코딩(cp949)으로 읽어 한글 파일을
못 읽음. 그래서 같은 일(model_dump로 쓰고 model_validate로 읽기)을 UTF-8로 직접 함.
인덱서는 graph_schema.json과 unit_text_rules.json만 읽음. schema_spec.json은 설계 단계의 중간 파일임.
실행: python tools/finalize.py {doc} → {doc}/graph_schema.json, {doc}/approval.json, {doc}/unit_text_rules.json
"""

from __future__ import annotations

import copy
import hashlib
import sys
import time

from neo4j_graphrag.components.schema import GraphSchema

from common import AUTO, BASE, load_json, save_json


def sha256(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def counts(s: GraphSchema) -> dict:
    return {"node_types": len(s.node_types), "relationship_types": len(s.relationship_types),
            "patterns": len(s.patterns), "constraints": len(s.constraints)}


def main() -> None:
    doc = sys.argv[1]
    # 미달인데도 확정하려면 사유를 반드시 적게 함. 사유와 미달 질문은 승인 기록에 남아 나중에 다시 볼 수 있음
    accept_below = next((a.split("=", 1)[1] for a in sys.argv[2:] if a.startswith("--accept-below=")), None)
    metrics = load_json(f"{doc}/output/fill_metrics.json")
    if not metrics["all_pass"] and not accept_below:
        raise SystemExit(f"{doc}: 8단계 합격 기준 미달이라 9단계를 진행하지 않음 (확정하려면 --accept-below=사유)")
    draft = load_json(f"{doc}/output/schema_draft.json")
    schema = GraphSchema.model_validate(copy.deepcopy(draft))
    save_json(f"{doc}/graph_schema.json", schema.model_dump(mode="json"))  # 한글 그대로 UTF-8로 씀
    reread = GraphSchema.model_validate(load_json(f"{doc}/graph_schema.json"))  # UTF-8로 읽어 다시 검증
    want = counts(schema)  # 검증을 거친 초안 기준(required 속성이 제약으로 바뀌는 판이 있어 원본 dict 수와 다를 수 있음)
    got = counts(reread)
    same = want == got
    inputs = ["competency_questions.md", "sample_plan.json", "decisions.json", f"{doc}/expected_answers.json"]
    approver = AUTO if metrics["all_pass"] else f"사용자 지시: 합격 기준 미달 상태로 확정({accept_below})"
    approval = {"doc": doc, "approver": approver, "approved_at": time.strftime("%Y-%m-%d %H:%M"),
                "input_sha256": {f: sha256(BASE / f) for f in inputs},
                "last_metrics": metrics, "draft_counts": want, "reread_counts": got, "reread_same": same}
    if not metrics["all_pass"]:
        approval["below_criteria"] = {"failed": [q for q, m in metrics["metrics"].items() if not m["pass"]],
                                      "reason": accept_below}
    save_json(f"{doc}/approval.json", approval)
    # 인덱싱이 스키마 설계와 같은 글로 추출하도록, 추출 청크(unit)의 글을 만드는 규칙 두 가지를 따로 남김
    save_json(f"{doc}/unit_text_rules.json", {
        "doc": doc,
        # 청크를 추출 청크로 다시 나누는 규칙. 없으면(null) 청크를 그대로 추출 청크로 씀
        "extraction_unit_rule": load_json("decisions.json")["input"].get("extraction_units", {}).get(doc),
        # 추출 청크 앞에 머리줄로 붙일 메타데이터 칸(키 속성이 채워지게 함)
        "metadata_header": load_json(f"{doc}/schema_spec.json").get("metadata_header", []),
    })
    print(f"{doc}: 초안 {want} / 다시 읽음 {got} → {'같음' if same else '다름'}")


if __name__ == "__main__":
    main()
