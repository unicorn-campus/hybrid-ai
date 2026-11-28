"""온톨로지 원본(Turtle)에서 그래프 스키마 파일과 그림을 만들어 냄.

neo4j-graphrag는 Turtle을 읽지 못하고 그래프 스키마 JSON만 읽음. 그래서 사람이 승인하는 원본은 Turtle에 두고,
이 도구가 card.ttl + shapes/{문서 종류}.ttl에서 JSON을 만듦. JSON은 생성물이므로 손으로 고치지 않음.

실행(ttl 폴더에서, 가상환경을 활성화한 뒤):
  python tools/build_from_ttl.py           승인본 → schema/doc-ontology/{문서 종류}/graph_schema.json. 같으면 건드리지 않음
  python tools/build_from_ttl.py --check   저장하지 않고, 지금 파일이 Turtle에서 만든 것과 같은지만 봄(다르면 종료 코드 1)
  python tools/build_from_ttl.py --draft   초안 → {문서 종류}/output/schema_draft.json과 그림(schema.mmd, schema_preview.html,
                                           common/output/schema_all.mmd). 스키마 설계 5단계와 8단계(채우기 시험)가 씀
"""
import argparse
import copy
import html
import json
import sys
from pathlib import Path

from neo4j_graphrag.components.schema import GraphSchema
from rdflib.namespace import OWL, RDF, RDFS, SKOS

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent))
import ttl_write as w  # noqa: E402
from ttl_write import BASE_DIR, CARD, DRAFT_DIR, TTL_DIR, turtle  # noqa: E402
from core_turtle import local  # noqa: E402

DOC_NAMES = {"regulation": "약관", "benefit_guide": "카드 혜택 안내", "consult_log": "상담 기록"}


def korean_names(ttl_dir: Path) -> dict:
    """라벨 → 한글 이름. Class는 rdfs:label, 문서 전용 노드 타입은 뜻의 첫 낱말(예: 「이용 기준.」)을 씀."""
    card = turtle.read(ttl_dir / "card.ttl")
    names = {}
    for cls in card.subjects(RDF.type, OWL.Class):
        label, definition = card.value(cls, RDFS.label), card.value(cls, SKOS.definition)
        if label is not None or definition is not None:
            names[local(cls)] = str(label) if label is not None else str(definition).split(".")[0]
    return names


def indexer_adds(ttl_dir: Path) -> tuple[dict, list]:
    """인덱싱이 맞추기 표로 더하는 노드 타입과 관계(card:addedBy). 그림에 점선으로 그림."""
    card = turtle.read(ttl_dir / "card.ttl")
    nodes = {local(c): [str(d) for d in card.objects(c, CARD.docType)]
             for c in card.subjects(RDF.type, OWL.Class) if card.value(c, CARD.addedBy) is not None}
    edges = [(local(card.value(p, RDFS.domain)), local(p), local(card.value(p, RDFS.range)), [str(d) for d in card.objects(p, CARD.docType)])
             for p in card.subjects(RDF.type, OWL.ObjectProperty) if card.value(p, CARD.addedBy) is not None]
    return nodes, edges


def mermaid(groups: dict, names: dict, adds: tuple[dict, list], shared: set) -> str:
    """flowchart LR. 상자에 :영문 라벨, (한글 이름), 속성. 화살표에 관계 이름. 여러 문서 종류에 나오는 노드(shared)는 공통으로 그림."""
    lines, properties = ["flowchart LR"], {}
    for doc_type, schema in groups.items():
        lines.append(f'  subgraph {doc_type}["{DOC_NAMES.get(doc_type, doc_type)}"]')
        for node in schema["node_types"]:
            properties[node["label"]] = "<br/>".join(p["name"] for p in node["properties"])
            if node["label"] not in shared:
                lines.append(f'    {node["label"]}[":{node["label"]}<br/>({names.get(node["label"], "")})<br/>---<br/>{properties[node["label"]]}"]')
        lines.append("  end")
    drawn_shared = sorted(label for label in shared if label in properties)
    for label in drawn_shared:
        lines.append(f'  {label}{{{{":{label}<br/>({names.get(label, "")}, 공통)<br/>---<br/>{properties[label]}"}}}}')
    add_nodes, add_edges = adds
    for label, docs in sorted(add_nodes.items()):
        if set(docs) & set(groups):
            lines.append(f'  {label}[/":{label}<br/>({names.get(label, "")}, 인덱싱이 더함)<br/>---<br/>name"/]')
    edges = {(p["source"], p["relationship"], p["target"], "-->") for s in groups.values() for p in s["patterns"]}
    edges |= {(s, r, t, "-.->") for s, r, t, docs in add_edges if set(docs) & set(groups)}
    lines += [f"  {s} {arrow}|{r}| {t}" for s, r, t, arrow in sorted(edges)]
    if drawn_shared:
        lines += ["  classDef shared fill:#fff3d6,stroke:#c98a00", "  class " + ",".join(drawn_shared) + " shared"]
    return "\n".join(lines) + "\n"


def preview(title: str, diagrams: list[tuple[str, str]]) -> str:
    blocks = "\n".join(f"<h2>{html.escape(name)}</h2>\n<pre class=\"mermaid\">\n{html.escape(code)}</pre>" for name, code in diagrams)
    return f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><title>{html.escape(title)}</title>
<style>body{{font-family:Pretendard,system-ui,sans-serif;margin:24px;background:#fff;color:#222}} h2{{margin-top:32px}}
#status{{padding:8px;background:#eef;}}</style></head>
<body><h1>{html.escape(title)}</h1><div id="status">그리는 중</div>
{blocks}
<script type="module">
import mermaid from "https://cdn.jsdelivr.net/npm/mermaid@10.9.1/dist/mermaid.esm.min.mjs";
mermaid.initialize({{startOnLoad:false, flowchart:{{htmlLabels:true}}}});
try {{ await mermaid.run({{querySelector:".mermaid"}}); document.getElementById("status").textContent="그림 " + document.querySelectorAll(".mermaid svg").length + "장 그림, 오류 없음"; }}
catch (e) {{ document.getElementById("status").textContent="오류: " + e.message; }}
</script></body></html>
"""


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def build(ttl_dir: Path, mode: str, check_only: bool = False) -> list[str]:
    """mode: saved(graph_schema.json) 또는 draft(output/schema_draft.json과 그림). 달라서 쓴(또는 다른) 문서 종류를 돌려줌."""
    target = "graph_schema.json" if mode == "saved" else "output/schema_draft.json"
    different, schemas = [], {}
    for doc_type in turtle.DOC_TYPES:
        schema = schemas[doc_type] = turtle.graph_schema(doc_type, ttl_dir)
        GraphSchema.model_validate(copy.deepcopy(schema))  # neo4j-graphrag가 받는 꼴인지 확인(틀리면 여기서 멈춤)
        path = BASE_DIR / doc_type / target
        current = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
        counts = (f"노드 타입 {len(schema['node_types'])}, 관계 {len(schema['relationship_types'])}, "
                  f"패턴 {len(schema['patterns'])}, 제약 {len(schema['constraints'])}")
        if current == schema:  # 칸의 값과 목록 순서까지 같은지
            print(f"{doc_type}: {counts} → 지금 파일과 같음")
            continue
        different.append(doc_type)
        if check_only:
            keys = [k for k in schema if current is None or current.get(k) != schema[k]]
            print(f"{doc_type}: {counts} → 지금 파일과 다름(다른 칸: {keys})")
        else:
            write_text(path, turtle.schema_text(schema))
            print(f"{doc_type}: {counts} → 저장함 {path.relative_to(w.PROJECT).as_posix()}")
    if mode == "draft" and not check_only:  # 그림: 문서 종류마다 1장, 전체 1장
        names, adds = korean_names(ttl_dir), indexer_adds(ttl_dir)
        labels = [n["label"] for s in schemas.values() for n in s["node_types"]]
        shared = {label for label in labels if labels.count(label) > 1}  # 여러 문서 종류에 나오는 노드 타입
        codes = {}
        for doc_type, schema in schemas.items():
            codes[doc_type] = mermaid({doc_type: schema}, names, adds, shared)
            write_text(BASE_DIR / doc_type / "output" / "schema.mmd", codes[doc_type])
            write_text(BASE_DIR / doc_type / "output" / "schema_preview.html",
                       preview(f"스키마 초안: {DOC_NAMES[doc_type]}", [(DOC_NAMES[doc_type], codes[doc_type])]))
        whole = mermaid(schemas, names, adds, shared)
        write_text(BASE_DIR / "common" / "output" / "schema_all.mmd", whole)
        write_text(BASE_DIR / "common" / "output" / "schema_preview.html",
                   preview("스키마 초안: 전체(공통 노드와 문서 종류별 노드)",
                           [("전체", whole)] + [(DOC_NAMES[d], codes[d]) for d in turtle.DOC_TYPES]))
        print("그림: 문서 종류마다 output/schema.mmd와 schema_preview.html, 전체는 common/output/schema_all.mmd")
    return different


def main() -> None:
    parser = argparse.ArgumentParser(description="Turtle → 그래프 스키마 JSON")
    parser.add_argument("--check", action="store_true", help="저장하지 않고 지금 파일과 같은지만 봄")
    parser.add_argument("--draft", action="store_true", help="초안 폴더에서 스키마 초안과 그림을 만듦")
    args = parser.parse_args()
    ttl_dir = DRAFT_DIR if args.draft else TTL_DIR
    if not ttl_dir.exists():
        raise SystemExit(f"폴더가 없음: {ttl_dir}. 초안은 tools/draft.py start로 만듦")
    different = build(ttl_dir, "draft" if args.draft else "saved", args.check)
    if args.check and different:
        raise SystemExit(f"스키마 파일이 Turtle과 다름: {different}. Turtle을 고쳤으면 --check 없이 다시 돌림")


if __name__ == "__main__":
    main()
