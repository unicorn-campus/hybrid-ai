"""structure.json(DB 구조)과 decisions.json(사람의 결정)으로 그래프 스키마를 판정, 초안 작성, 검증, 그림, 저장함.

하위 명령:
  judge     structure.json → output/judgment_table.md (규칙 ②③④ 자동 판정, 규칙 ① 후보 표시)
  draft     + decisions.json → output/schema_draft.json, 기계 검증, output/schema.mmd, output/schema_preview.html
  finalize  후보 표시가 하나도 없을 때만 → graph_schema.json(GraphSchema.save), approval.json

판정 기준(위에서부터 먼저 맞는 것을 적용, FK 개수는 열 수가 아니라 제약 수):
  다른 테이블의 FK가 가리킴 → 노드 타입(관계는 FK가 가리킬 수 없음)
  FK 0개 또는 1개 → 노드 타입
  FK 3개 이상 → 중간 노드 타입(규칙 ④)
  FK 2개이고 업무 열 없음 → 관계(규칙 ②)
  FK 2개이고 업무 열 있음 → 규칙 ① 후보(사람이 노드 타입 또는 관계 + 관계 속성(규칙 ③)으로 정함)
업무 열: PK에도 FK에도 들어가지 않는 열.

실행 예(base_dir에서): .venv/Scripts/python tools/draft_schema.py judge
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import html
import json
import re
from collections import Counter
from datetime import datetime, timezone, timedelta
from pathlib import Path

from neo4j_graphrag.components.schema import GraphSchema

BASE_DIR = Path(__file__).resolve().parent.parent
OUT = BASE_DIR / "output"
STRUCTURE = OUT / "structure.json"
DECISIONS = BASE_DIR / "decisions.json"
DRAFT = OUT / "schema_draft.json"
FINAL = BASE_DIR / "graph_schema.json"
APPROVAL = BASE_DIR / "approval.json"
KST = timezone(timedelta(hours=9))

# RDB 타입 → GraphSchema 속성 타입. 표에 없는 타입은 추측하지 않고 멈춤(사람이 표를 늘려야 함)
TYPE_MAP = {
    "text": "STRING", "varchar": "STRING", "bpchar": "STRING", "uuid": "STRING",
    "int2": "INTEGER", "int4": "INTEGER", "int8": "INTEGER",
    "numeric": "FLOAT", "float4": "FLOAT", "float8": "FLOAT",
    "bool": "BOOLEAN", "date": "DATE",
}
NODE_LABEL_RE = re.compile(r"^[A-Z][A-Za-z0-9]*$")
REL_LABEL_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
HANGUL_RE = re.compile(r"[가-힣]")

KIND_KO = {"node": "노드 타입", "middle_node": "중간 노드 타입", "relationship": "관계", "rule1": "규칙 ① 후보"}


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def business_columns(table: dict) -> list[dict]:
    return [c for c in table["columns"] if not c["in_pk"] and not c["in_fk"]]


def judge(tables: list[dict]) -> dict[str, dict]:
    """테이블마다 판정(kind)과 적용 규칙(rule)을 돌려줌. 제외 테이블도 판정은 함(판정표에 다 보이게)."""

    referenced = {fk["ref_table"] for t in tables for fk in t["foreign_keys"] if fk["ref_table"] != t["name"]}
    result = {}
    for t in tables:
        n_fk, n_biz = len(t["foreign_keys"]), len(business_columns(t))
        if t["name"] in referenced:
            kind, rule = "node", "다른 테이블이 가리킴"
        elif n_fk <= 1:
            kind, rule = "node", "FK 0개 또는 1개"
        elif n_fk >= 3:
            kind, rule = "middle_node", "규칙 ④ (FK 3개 이상)"
        elif n_biz == 0:
            kind, rule = "relationship", "규칙 ② (FK 2개, 업무 열 없음)"
        else:
            kind, rule = "rule1", "규칙 ① (FK 2개, 업무 열 있음)"
        result[t["name"]] = {"fk": n_fk, "biz": n_biz, "kind": kind, "rule": rule}
    return result


def judgment_markdown(tables: list[dict], j: dict[str, dict], dec: dict | None) -> str:
    excluded = set(dec.get("exclude_tables", [])) if dec else set()
    rule1 = dec.get("rule1", {}) if dec else {}
    lines = ["# 테이블 판정표", "",
             "- FK 제약 수: 열 수가 아니라 FK 규칙(제약) 수. 열 2개로 된 FK 1개는 1개로 셈  ",
             "- 업무 열 수: PK에도 FK에도 들어가지 않는 열의 수  ",
             "- 판정은 위에서부터 먼저 맞는 규칙을 적용함(다른 테이블이 가리킴 → FK 0개 또는 1개 → FK 3개 이상 → "
             "FK 2개)", "",
             "| 테이블 | FK 제약 수 | 업무 열 수 | 판정 | 적용 규칙 |",
             "|--------|-----------|-----------|------|-----------|"]
    for t in tables:
        r = j[t["name"]]
        verdict = KIND_KO[r["kind"]]
        if r["kind"] == "rule1" and t["name"] in rule1:
            chosen = "노드 타입" if rule1[t["name"]]["decision"] == "node" else "관계 + 관계 속성(규칙 ③)"
            verdict += f" → 사용자가 {chosen}으로 정함"
        if t["name"] in excluded:
            verdict += " → 사용자가 그래프에서 뺌"
        lines.append(f"| {t['name']} | {r['fk']} | {r['biz']} | {verdict} | {r['rule']} |")
    lines += ["", "## FK 제약 목록", "", "| 제약 이름 | 테이블 | 가리키는 테이블 | 열 짝 |", "|---|---|---|---|"]
    for t in tables:
        for fk in t["foreign_keys"]:
            pairs = ", ".join(f"{t['name']}.{p['column']} → {fk['ref_table']}.{p['ref_column']}" for p in fk["pairs"])
            lines.append(f"| {fk['name']} | {t['name']} | {fk['ref_table']} | {pairs} |")
    return "\n".join(lines) + "\n"


def prop(col: dict) -> dict:
    if col["type"] not in TYPE_MAP:
        raise SystemExit(f"타입 변환 표에 없는 RDB 타입: {col['name']} {col['type']} — TYPE_MAP에 직접 추가 필요")
    return {"name": col["name"], "type": TYPE_MAP[col["type"]]}


def build_draft(structure: dict, dec: dict) -> tuple[dict, dict]:
    """GraphSchema 입력 dict와 그림용 부가정보(한글 이름, 키, 관계 속성)를 만듦."""

    tables = [t for t in structure["tables"] if t["name"] not in dec["exclude_tables"]]
    by_name = {t["name"]: t for t in tables}
    j = judge(structure["tables"])
    node_names, rels = dec["node_types"], dec["relationships"]

    kinds = {}
    for t in tables:
        k = j[t["name"]]["kind"]
        if k == "rule1":
            if t["name"] not in dec["rule1"]:
                raise SystemExit(f"decisions.json rule1에 판정이 없는 테이블: {t['name']}")
            k = "node" if dec["rule1"][t["name"]]["decision"] == "node" else "rel_props"
        kinds[t["name"]] = "node" if k == "middle_node" else k

    nodes, constraints, rel_types, patterns = [], [], [], []
    info = {"name_ko": {}, "keys": {}, "rel_props": {}, "candidates": []}
    for t in tables:
        if kinds[t["name"]] != "node":
            continue
        nn = node_names[t["name"]]
        # FK 열은 관계로 바뀌므로 지움. PK에 든 FK 열은 노드 하나하나를 구별하는 데 필요해 남김
        keep = [c for c in t["columns"] if c["in_pk"] or not c["in_fk"]]
        nodes.append({"label": nn["label"], "description": nn["name_ko"],
                      "properties": [prop(c) for c in keep], "additional_properties": False})
        constraints.append({"type": "UNIQUENESS", "node_type": nn["label"], "property_names": t["primary_key"]})
        info["name_ko"][nn["label"]] = nn["name_ko"]
        info["keys"][nn["label"]] = t["primary_key"]
        if nn.get("_후보"):
            info["candidates"].append(f"노드 타입 {t['name']} → {nn['label']}({nn['name_ko']})")

    def add_rel(key: str, props: list[dict]) -> None:
        r = rels[key]
        for end in (r["from"], r["to"]):
            if end not in by_name or kinds[end] != "node":
                raise SystemExit(f"관계 {key}의 끝 {end}가 노드 타입이 아님(제외되었거나 관계로 판정됨)")
        if r["label"] not in {x["label"] for x in rel_types}:
            rel_types.append({"label": r["label"], "description": r["name_ko"], "properties": props,
                              "additional_properties": False})
        src, dst = node_names[r["from"]]["label"], node_names[r["to"]]["label"]
        patterns.append({"source": src, "relationship": r["label"], "target": dst})
        info["name_ko"][r["label"]] = r["name_ko"]
        info["rel_props"][r["label"]] = [p["name"] for p in props]
        if r.get("_후보"):
            info["candidates"].append(f"관계 {key} → {src} -[{r['label']}({r['name_ko']})]-> {dst}")

    for t in tables:  # FK에서 나온 관계(노드 타입 테이블의 FK)
        if kinds[t["name"]] == "node":
            for fk in t["foreign_keys"]:
                if fk["ref_table"] in by_name:
                    add_rel(fk["name"], [])
    for t in tables:  # 테이블에서 나온 관계: 규칙 ②는 속성 없음, 규칙 ③은 업무 열이 관계 속성
        k = kinds[t["name"]]
        if k in ("relationship", "rel_props"):
            add_rel(t["name"], [prop(c) for c in business_columns(t)] if k == "rel_props" else [])

    schema = {"node_types": nodes, "relationship_types": rel_types, "patterns": patterns, "constraints": constraints,
              "additional_node_types": False, "additional_relationship_types": False, "additional_patterns": False}
    return schema, info


def check(schema: dict) -> list[str]:
    """기계 검증. 실패 사유 목록을 돌려줌(빈 목록이면 통과)."""

    errors = []
    for kind, items in (("노드 타입", schema["node_types"]), ("관계", schema["relationship_types"])):
        dup = [k for k, n in Counter(x["label"] for x in items).items() if n > 1]
        if dup:
            errors.append(f"{kind} 라벨 중복: {dup}")
    print(f"[검사] 노드 타입 라벨 중복: {'없음' if not any('노드 타입 라벨 중복' in e for e in errors) else '있음'}")

    name_err = []
    for n in schema["node_types"]:
        if not NODE_LABEL_RE.match(n["label"]):
            name_err.append(f"노드 타입 라벨 규칙 위반: {n['label']}")
        if not HANGUL_RE.search(n["description"]):
            name_err.append(f"노드 타입 {n['label']}의 description에 한글 이름 없음")
    for r in schema["relationship_types"]:
        if not REL_LABEL_RE.match(r["label"]):
            name_err.append(f"관계 라벨 규칙 위반: {r['label']}")
        if not HANGUL_RE.search(r["description"]):
            name_err.append(f"관계 {r['label']}의 description에 한글 이름 없음")
    print(f"[검사] 이름 규칙(노드 타입 {NODE_LABEL_RE.pattern}, 관계 {REL_LABEL_RE.pattern}, 한글 이름): "
          f"{'통과' if not name_err else '실패'}")
    errors += name_err

    try:
        # 사본을 넘기는 이유: model_validate가 받은 dict의 patterns를 Pattern 객체로 바꿔 놓아 JSON 저장이 깨짐
        GraphSchema.model_validate(copy.deepcopy(schema))
        print("[검사] GraphSchema.model_validate(): 통과")
    except Exception as e:  # pydantic ValidationError 외에 스키마 내부 검사 오류도 함께 받음
        print("[검사] GraphSchema.model_validate(): 실패")
        errors.append(f"GraphSchema 검증 실패: {e}")
    return errors


def mermaid(schema: dict, info: dict) -> str:
    ids = {n["label"]: f"N{i}" for i, n in enumerate(schema["node_types"])}
    lines = ["flowchart LR"]
    for n in schema["node_types"]:
        keys = info["keys"][n["label"]]
        props = "".join(f"<br/>{p['name']}{' (키)' if p['name'] in keys else ''}" for p in n["properties"])
        lines.append(f'    {ids[n["label"]]}["<b>:{n["label"]}</b><br/>({n["description"]}){props}"]')
    for p in schema["patterns"]:
        rel = p["relationship"]
        extra = "".join(f"<br/>{x}" for x in info["rel_props"].get(rel, []))
        lines.append(f'    {ids[p["source"]]} -->|"{rel}<br/>({info["name_ko"][rel]}){extra}"| {ids[p["target"]]}')
    lines.append("    classDef nt fill:#EEF3FA,stroke:#1E2A5C,stroke-width:2px,color:#2B3242")
    lines.append("    class " + ",".join(ids.values()) + " nt")
    return "\n".join(lines) + "\n"


def preview_html(mmd: str) -> str:
    return ("<!doctype html><html lang='ko'><head><meta charset='utf-8'><title>그래프 스키마 미리보기</title>"
            "<script src='https://cdn.jsdelivr.net/npm/mermaid@11.4.1/dist/mermaid.min.js'></script>"
            "<style>body{background:#fff;font-family:sans-serif;margin:16px}#status{color:#666}</style></head><body>"
            f"<pre class='mermaid'>{html.escape(mmd)}</pre><div id='status'>RENDERING</div><script>"
            "mermaid.initialize({startOnLoad:false, securityLevel:'loose', flowchart:{htmlLabels:true}});"
            "mermaid.run().then(()=>{document.getElementById('status').textContent='RENDER_OK'})"
            ".catch(e=>{document.getElementById('status').textContent='RENDER_FAIL '+e});</script></body></html>\n")


def counts(s: dict) -> dict:
    return {k: len(s[k]) for k in ("node_types", "relationship_types", "patterns", "constraints")}


def cmd_judge(_: argparse.Namespace) -> None:
    structure = load(STRUCTURE)
    dec = load(DECISIONS) if DECISIONS.exists() else None
    j = judge(structure["tables"])
    (OUT / "judgment_table.md").write_text(judgment_markdown(structure["tables"], j, dec), encoding="utf-8")
    for name, r in j.items():
        print(f"{name}: FK {r['fk']}, 업무 열 {r['biz']} → {KIND_KO[r['kind']]} ({r['rule']})")


def cmd_draft(_: argparse.Namespace) -> None:
    structure, dec = load(STRUCTURE), load(DECISIONS)
    (OUT / "judgment_table.md").write_text(
        judgment_markdown(structure["tables"], judge(structure["tables"]), dec), encoding="utf-8")
    schema, info = build_draft(structure, dec)
    write_json(DRAFT, schema)
    print(f"초안: {counts(schema)}")
    errors = check(schema)
    if errors:
        print("기계 검증 실패:\n  " + "\n  ".join(errors))
        raise SystemExit(1)
    mmd = mermaid(schema, info)
    (OUT / "schema.mmd").write_text(mmd, encoding="utf-8")
    (OUT / "schema_preview.html").write_text(preview_html(mmd), encoding="utf-8")
    print(f"후보 표시 남은 항목 {len(info['candidates'])}개")
    for c in info["candidates"]:
        print(f"  - {c}")


def cmd_finalize(args: argparse.Namespace) -> None:
    structure, dec = load(STRUCTURE), load(DECISIONS)
    schema, info = build_draft(structure, dec)
    if info["candidates"]:
        raise SystemExit(f"후보 표시가 남아 있어 만들지 않음: {info['candidates']}")
    if check(schema):
        raise SystemExit("기계 검증 실패")
    write_json(DRAFT, schema)  # 승인된 decisions.json 기준으로 초안도 맞춰 둠
    GraphSchema.model_validate(copy.deepcopy(schema)).save(FINAL, overwrite=True)
    reloaded = GraphSchema.from_file(FINAL)
    got = {"node_types": len(reloaded.node_types), "relationship_types": len(reloaded.relationship_types),
           "patterns": len(reloaded.patterns), "constraints": len(reloaded.constraints)}
    want = counts(schema)
    print(f"[대조] 초안 {want} / 다시 읽은 파일 {got} → {'일치' if got == want else '불일치'}")
    if got != want:
        raise SystemExit(1)
    approval = {
        "approved_by": args.approver,
        "approved_at": datetime.now(KST).isoformat(timespec="seconds"),
        "graph_schema": FINAL.name,
        "inputs_sha256": {
            "output/structure.json": hashlib.sha256(STRUCTURE.read_bytes()).hexdigest(),
            "decisions.json": hashlib.sha256(DECISIONS.read_bytes()).hexdigest(),
        },
        "graph_schema_sha256": hashlib.sha256(FINAL.read_bytes()).hexdigest(),
        "counts": got,
    }
    write_json(APPROVAL, approval)
    print(f"저장: {FINAL}, {APPROVAL}")


def main() -> None:
    ap = argparse.ArgumentParser(description="RDB 구조 → 그래프 스키마 판정, 초안, 확정")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("judge").set_defaults(func=cmd_judge)
    sub.add_parser("draft").set_defaults(func=cmd_draft)
    fin = sub.add_parser("finalize")
    fin.add_argument("--approver", required=True)
    fin.set_defaults(func=cmd_finalize)
    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
