"""5단계와 6단계: 추천 내용(`{doc}/schema_spec.json`)으로 스키마 초안, Mermaid 그림, 미리보기 HTML을 만들고 기계 검증함.

schema_spec.json 꼴:
  recommend: [{"kind": "병합|제거|추가", "item": "...", "cq": ["C1"]}]
  node_types: [{"label", "ko", "description", "properties": [{"name", "type", "description", "required"?}]}]
  relationship_types: [{"label", "ko", "description", "properties"?: [...]}]
  patterns: [["Source", "REL", "Target"]]
  constraints: [{"type": "UNIQUENESS", "node_type", "property_name"}]
  cq_map: {"C1": [{"label": "...", "property"?: "..."} | {"rel": "..."}]}   # 8단계 채점에 씀
실행: python tools/build_schema.py {doc} → {doc}/output/schema_draft.json, schema.mmd, schema_preview.html, validate.log
"""

from __future__ import annotations

import copy
import json
import re
import sys
from collections import Counter

from neo4j_graphrag.components.schema import GraphSchema

from common import BASE, decisions, load_json

NODE_RE, REL_RE = re.compile(r"^[A-Z][A-Za-z0-9]*$"), re.compile(r"^[A-Z][A-Z0-9_]*$")
MERMAID = "https://cdn.jsdelivr.net/npm/mermaid@11.4.1/dist/mermaid.min.js"


def to_graph_schema(spec: dict) -> dict:
    """사람이 읽는 추천 내용을 neo4j-graphrag GraphSchema 꼴로 바꿈(한글 이름은 description 앞에 붙임)."""

    # required=true는 EXISTENCE 제약이 되는데 Community 판은 지원하지 않아, 그 판에서는 모두 false로 둠
    community = "Community" in decisions()["input"]["neo4j_edition"]

    def props(ps):
        return [{"name": p["name"], "type": p.get("type", "STRING"), "description": p["description"],
                 "required": bool(p.get("required", False)) and not community} for p in ps or []]

    return {
        "node_types": [{"label": n["label"], "description": f"({n['ko']}) {n['description']}",
                        "properties": props(n["properties"]), "additional_properties": False}
                       for n in spec["node_types"]],
        "relationship_types": [{"label": r["label"], "description": f"({r['ko']}) {r['description']}",
                                "properties": props(r.get("properties")), "additional_properties": False}
                               for r in spec["relationship_types"]],
        "patterns": [list(p) for p in spec["patterns"]],
        "constraints": spec.get("constraints", []),
        "additional_node_types": False,
        "additional_relationship_types": False,
        "additional_patterns": False,
    }


def mermaid(spec: dict) -> str:
    lines = ["flowchart LR"]
    for n in spec["node_types"]:
        ps = "<br/>".join(f"{p['name']}" for p in n["properties"])
        lines.append(f'    {n["label"]}["<b>:{n["label"]}</b><br/>({n["ko"]})<br/>{ps}"]')
    for s, r, t in spec["patterns"]:
        lines.append(f"    {s} -->|{r}| {t}")
    return "\n".join(lines) + "\n"


def validate(spec: dict, draft: dict) -> list[str]:
    log, ok = [], True
    dup = [k for k, v in Counter(n["label"] for n in spec["node_types"]).items() if v > 1]
    log.append(f"노드 타입 라벨 중복: {dup or '없음'}")
    ok &= not dup
    bad_n = [n["label"] for n in spec["node_types"] if not NODE_RE.match(n["label"])]
    bad_r = [r["label"] for r in spec["relationship_types"] if not REL_RE.match(r["label"])]
    log.append(f"이름 규칙 위반: 노드 타입 {bad_n or '없음'}, 관계 {bad_r or '없음'}")
    ok &= not bad_n and not bad_r
    no_desc = [x["label"] for x in spec["node_types"] + spec["relationship_types"] if not x.get("description")]
    no_desc += [f"{x['label']}.{p['name']}" for x in spec["node_types"] for p in x["properties"] if not p.get("description")]
    log.append(f"description 없음: {no_desc or '없음'}")
    ok &= not no_desc
    labels = {n["label"] for n in spec["node_types"]}
    rels = {r["label"] for r in spec["relationship_types"]}
    bad_p = [p for p in spec["patterns"] if p[0] not in labels or p[2] not in labels or p[1] not in rels]
    log.append(f"패턴의 이름이 목록에 없음: {bad_p or '없음'}")
    ok &= not bad_p
    try:
        s = GraphSchema.model_validate(copy.deepcopy(draft))  # 원본을 넘기면 dict 안의 패턴이 바뀔 수 있어 사본으로 검증
        log.append("GraphSchema.model_validate: 통과")
        # required 속성은 검증 중에 EXISTENCE 제약으로 바뀜(1.22.0 실측). Community 판은 UNIQUENESS만 지원
        allowed = {"UNIQUENESS"} if "Community" in decisions()["input"]["neo4j_edition"] else None
        bad_c = [f"{c.type}:{c.node_type}.{c.property_name}" for c in s.constraints
                 if allowed and str(getattr(c.type, "value", c.type)) not in allowed]
        log.append(f"쓰는 Neo4j 판이 지원하지 않는 제약: {bad_c or '없음'}")
        ok &= not bad_c
    except Exception as e:
        ok = False
        log.append(f"GraphSchema.model_validate: 실패 {type(e).__name__}: {str(e)[:300]}")
    log.append("결과: " + ("통과" if ok else "실패"))
    return log


def main() -> None:
    doc = sys.argv[1]
    spec = load_json(f"{doc}/schema_spec.json")
    out = BASE / doc / "output"
    out.mkdir(parents=True, exist_ok=True)
    draft = to_graph_schema(spec)
    (out / "schema_draft.json").write_text(json.dumps(draft, ensure_ascii=False, indent=2), encoding="utf-8")
    mmd = mermaid(spec)
    (out / "schema.mmd").write_text(mmd, encoding="utf-8")
    html = f"""<!doctype html><html lang="ko"><head><meta charset="utf-8"><title>{doc} 스키마 초안</title>
<style>body{{font-family:sans-serif;margin:16px;background:#fff}}</style></head><body>
<h3>{doc} 스키마 초안</h3><pre class="mermaid">
{mmd}</pre><div id="status">rendering</div>
<script src="{MERMAID}"></script>
<script>mermaid.initialize({{startOnLoad:false, securityLevel:'loose'}});
mermaid.run().then(()=>{{document.getElementById('status').textContent='rendered '+document.querySelectorAll('svg').length}})
.catch(e=>{{document.getElementById('status').textContent='error '+e}});</script></body></html>"""
    (out / "schema_preview.html").write_text(html, encoding="utf-8")
    log = validate(spec, draft)
    (out / "validate.log").write_text("\n".join(log) + "\n", encoding="utf-8")
    print("\n".join(log))


if __name__ == "__main__":
    main()
