"""사람이 승인할 검토 파일을 온톨로지 초안(Turtle)에서 만들어 냄. 사람은 Turtle을 직접 읽지 않고 이 표로 검토함.

스키마 설계 5단계(초안 추천과 확정)의 검토 파일임. 표는 모두 Turtle에서 읽어 만들므로 손으로 다시 적지 않음.
섹션마다 개념 설명, 표, 열 뜻을 차례로 씀(그래프DB를 처음 접하는 사람이 읽는다고 봄).

실행(ttl 폴더에서): python tools/render_review.py [--out review/step5-ttl.md] [--note "이번에 바꾼 까닭 한 줄"]
  초안 폴더가 있으면 초안을, 없으면 승인본을 읽음. 초안이면 승인본과 달라진 곳 표가 맨 앞에 붙음
"""
import argparse
import sys
from pathlib import Path

from rdflib.namespace import RDF

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_from_ttl  # noqa: E402
import draft as draft_tool  # noqa: E402
import ttl_write as w  # noqa: E402
from ttl_write import BASE_DIR, DRAFT_DIR, SH, turtle  # noqa: E402
from core_turtle import local  # noqa: E402

DOC_NAMES = build_from_ttl.DOC_NAMES


def cell(value) -> str:
    """표 칸에 넣을 글: 목록은 쉼표로, 빈 값은 「없음」, 세로줄은 표가 깨지지 않게 바꿈."""
    if isinstance(value, (list, tuple, set)):
        value = ", ".join(str(v) for v in value)
    return str(value).replace("|", "/").replace("\n", " ") if value not in (None, "", []) else "없음"


def table(headers: list[str], rows: list[list]) -> list[str]:
    lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    return lines + ["| " + " | ".join(cell(v) for v in row) + " |" for row in rows]


def section(title: str, concept: str, headers: list[str], rows: list[list], meanings: list[str]) -> list[str]:
    return [f"## {title}", "", concept, ""] + table(headers, rows) + ["", "열 뜻  "] + [f"- {m}  " for m in meanings] + [""]


def render(ttl_dir: Path, note: str) -> str:
    is_draft = ttl_dir == DRAFT_DIR
    concepts = turtle.load_concepts(ttl_dir)
    lines = ["# 5단계 검토 파일: 스키마 초안과 온톨로지(Turtle 원본)", "",
             "- 승인하는 것: 아래 표에 적은 Class, 관계, 검사 규칙, 건너가는 경로, 문서 종류별 노드 타입과 속성  ",
             "- 승인하면 일어나는 일: 이 초안으로 기계 검증(6단계)과 채우기 시험(8단계)을 돌림. 승인본은 아직 바뀌지 않음  ",
             f"- 읽은 곳: `{ttl_dir.relative_to(w.PROJECT).as_posix()}`(표는 모두 이 Turtle에서 만들어 냄)  "]
    if note:
        lines.append(f"- 이번에 바꾼 까닭: {note}  ")
    lines.append("")
    if is_draft:
        rows = [[r["file"], r["added"], r["removed"], r["subjects"]] for r in draft_tool.diff()]
        lines += section("1. 승인본과 달라진 곳",
                         "초안은 승인본을 복사해 고친 것임. 어느 파일의 어느 대상이 달라졌는지를 먼저 봄. "
                         "표가 비어 있으면 초안이 승인본과 같음.",
                         ["파일", "더한 문장", "뺀 문장", "달라진 대상"], rows or [["없음", 0, 0, "없음"]],
                         ["파일: 온톨로지 원본 파일. card.ttl은 Class와 관계, shapes는 문서 종류별 속성과 검사 규칙, maps는 맞추기 표",
                          "더한 문장, 뺀 문장: Turtle의 문장(주어, 서술어, 목적어 한 줄) 수. 값을 고치면 뺀 문장 1개와 더한 문장 1개로 셈",
                          "달라진 대상: 문장이 달라진 Class, 관계, 셰이프(노드 타입 한 개의 속성 묶음), 맞추기 표 행의 이름"])
    rows = []
    for c in concepts["classes"]:
        fills = sorted({f"{DOC_NAMES.get(d['doc_type'], d['doc_type'])} {d['label']}({d['role']}, {d['fill'] or '적지 않음'})"
                        for d in c["doc_labels"]})
        rows.append([c["name"], c["id"], c["kind"], c["definition"], c["synonyms"],
                     sorted({k for d in c["doc_labels"] for k in d["key_properties"]}),
                     (c["allowed_values"] or {}).get("values"), [f"{s['source']} {s['label']}" for s in c["source_labels"]],
                     [f"{i['between']}: {i['rule']}" for i in c["identity"]], fills])
    lines += section("2. Class(공통 개념)",
                     "Class는 같은 뜻의 개체를 묶은 업무 개념임. 여러 문서 종류와 정형 DB가 같은 Class를 가리키면 그 Class로 서로 이어짐. "
                     "뜻 한 줄은 여기에만 적고, 스키마의 설명 첫머리는 이 뜻에서 만들어짐.",
                     ["이름", "라벨", "종류", "뜻", "같은 말", "키 속성", "허용 값", "다른 원천의 라벨", "같은 개체로 보는 규칙", "문서 쪽 노드 타입과 채우는 방법"],
                     rows,
                     ["이름, 라벨: 한글 이름과 그래프에 쓰는 영문 이름", "종류: 개체(하나하나 세는 것) 또는 분류(정해진 값 가운데 하나)",
                      "같은 말: 후보를 합칠 때 이 Class로 모은 다른 이름(동의어)", "키 속성: 값이 같으면 같은 개체로 보는 속성",
                      "허용 값: 분류 Class가 가질 수 있는 값 목록. 값 목록 파일에서 읽은 것만 씀",
                      "다른 원천의 라벨: 정형 DB처럼 다른 원천에서 같은 개념을 나타내는 라벨",
                      "같은 개체로 보는 규칙: 값 같음, 바꾸는 규칙, 맞추기 표 가운데 무엇으로 같은 개체를 알아보는지",
                      "문서 쪽 노드 타입과 채우는 방법: 노드(그 Class의 노드를 만듦) 또는 키 참조(다른 노드에 키 속성만 둠), "
                      "그리고 LLM 추출, 머리줄 값(청크 메타데이터), 맞추기 표 가운데 무엇으로 채우는지"])
    rows = [[r["label"], r["source_class"], r["target_class"], r["inverse"], [DOC_NAMES.get(d, d) for d in r["doc_types"]]]
            for r in concepts["relations"]]
    lines += section("3. 관계(개념 규칙과 역관 규칙)",
                     "관계마다 출발 Class와 도착 Class를 적어 두면 연결을 같은 뜻으로 읽을 수 있음. 반대 이름은 같은 사실을 반대 방향에서 "
                     "묻는 질문을 위한 것이고, 그래프에는 한 방향만 저장함.",
                     ["관계", "출발 Class", "도착 Class", "반대 이름", "쓰는 문서 종류"], rows,
                     ["관계: 그래프에 저장하는 관계 이름", "출발 Class, 도착 Class: 이 관계가 잇는 두 Class",
                      "반대 이름: 반대 방향에서 부르는 이름. 저장하지 않고 검색이 뒤집어 따라감", "쓰는 문서 종류: 이 관계가 나오는 문서 종류"])
    rows = [[c["id"], c["kind"], c["target"], c["rule"]] for c in concepts["checks"]]
    lines += section("4. 검사 규칙",
                     "검사 규칙은 그래프에 들어간 데이터가 지켜야 할 조건임. 데이터를 고치지 않고 어긴 것만 알려 줌. "
                     "채우기 시험과 인덱싱이 같은 규칙 파일(shapes/checks.ttl)로 검사함.",
                     ["번호", "종류", "대상", "조건"], rows,
                     ["번호: 규칙 이름(K01 등)", "종류: 허용 값(값이 목록 안에 있음), 허용 수(개수가 범위 안임), 참조 무결성(가리키는 대상이 실제로 있음)",
                      "대상: 규칙을 적용하는 노드 타입", "조건: 지켜야 할 내용"])
    rows = [[p["crossing_point"], p["question"], p["path"], p["rules"]] for p in turtle.crossing_paths(ttl_dir)]
    lines += section("5. 건너가는 경로",
                     "건너가는 지점은 질문 하나가 한 원천에서 다른 원천으로 넘어가는 자리임. 지점마다 그래프에서 따라갈 경로가 "
                     "하나 이상 있어야 그 질문에 답할 수 있음.",
                     ["지점", "역량 질문", "경로", "쓰는 규칙"], rows,
                     ["지점: 2단계에서 정한 건너가는 지점 번호", "역량 질문: 이 지점을 지나는 질문 번호",
                      "경로: 노드 타입과 관계로 적은 길. 화살표는 관계의 방향", "쓰는 규칙: 이 경로가 기대는 온톨로지 규칙(동일, 분류, 개념, 역관)"])
    number = 6
    for doc_type in turtle.DOC_TYPES:
        schema = turtle.graph_schema(doc_type, ttl_dir)
        shapes = turtle.read(ttl_dir / "shapes" / f"{doc_type}.ttl")
        keys = {c["node_type"]: c["property_names"] for c in schema["constraints"]}
        rows = []
        for node in schema["node_types"]:
            shape = next(s for s in shapes.subjects(RDF.type, SH.NodeShape) if local(shapes.value(s, SH.targetClass)) == node["label"])
            fill = turtle.fill_of(shapes, shape)["fill"]
            for i, prop in enumerate(node["properties"]):
                rows.append([node["label"] if i == 0 else "", node["description"] if i == 0 else "", (fill or "적지 않음") if i == 0 else "",
                             prop["name"] + (" (키)" if prop["name"] in keys.get(node["label"], []) else ""), prop["type"], prop["description"]])
        lines += section(f"{number}. 문서 종류 {DOC_NAMES[doc_type]}({doc_type})의 노드 타입과 속성",
                         "노드 타입은 이 문서에서 LLM이 뽑을 수 있는 대상의 목록임. 설명에 해당하는 것과 해당하지 않는 것을 함께 적어야 "
                         "LLM이 엉뚱한 것을 뽑지 않음. 목록에 없는 것은 가지치기로 지워짐.",
                         ["노드 타입", "설명(뜻과 해당, 비해당)", "채우는 방법", "속성", "자료형", "속성 설명"], rows,
                         ["노드 타입: 그래프에 쓰는 영문 라벨", "설명: 뜻 한 줄과 추출 기준. 추출 품질을 가장 크게 좌우함",
                          "채우는 방법: LLM 추출 또는 머리줄 값. 문서 전용 노드 타입은 적지 않음", "속성: 노드에 붙는 값의 이름. (키)는 고유 키",
                          "자료형: STRING(글), BOOLEAN(참 또는 거짓) 등", "속성 설명: LLM에 주는 채우는 기준"])
        number += 1
        rows = [[p["source"], p["relationship"], p["target"],
                 next(r["description"] for r in schema["relationship_types"] if r["label"] == p["relationship"])] for p in schema["patterns"]]
        lines += section(f"{number}. 문서 종류 {DOC_NAMES[doc_type]}의 허용 패턴",
                         "허용 패턴은 「어느 노드 타입이 어떤 관계로 어느 노드 타입을 가리킬 수 있는지」의 목록임. 목록 밖 연결은 지워짐.",
                         ["출발", "관계", "도착", "관계 설명"], rows,
                         ["출발, 도착: 관계의 양 끝 노드 타입", "관계: 관계 이름", "관계 설명: LLM에 주는 연결 기준"])
        number += 1
    lines += ["## 함께 볼 파일", "",
              f"- 온톨로지 원본: `{ttl_dir.relative_to(w.PROJECT).as_posix()}/card.ttl`, `shapes/`, `maps/`  ",
              "- 그림: `schema/doc-ontology/common/output/schema_preview.html`(브라우저로 엶), 문서 종류마다 `output/schema.mmd`  ",
              "- 역량 질문과 건너가는 지점: `schema/doc-ontology/competency_questions.md`, `crossing_points.json`  ", ""]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Turtle → 검토 파일")
    parser.add_argument("--out", default="review/step5-ttl.md", help="출력 기준 폴더(schema/doc-ontology) 아래의 경로")
    parser.add_argument("--note", default="", help="이번에 바꾼 까닭 한 줄")
    args = parser.parse_args()
    ttl_dir = w.work_dir()
    out = BASE_DIR / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(ttl_dir, args.note), encoding="utf-8", newline="\n")
    print(f"검토 파일: {out.relative_to(w.PROJECT).as_posix()} ({'초안' if ttl_dir == DRAFT_DIR else '승인본'}에서 만듦)")


if __name__ == "__main__":
    main()
