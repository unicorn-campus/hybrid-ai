"""온톨로지 초안 폴더를 다룸: 시작, 승인본과의 차이, 승인본으로 올리기, 버리기.

스키마 설계는 승인본(ttl/)을 바로 고치지 않음. 승인본을 초안 폴더(schema/doc-ontology/draft-ttl/)로 복사해 초안을 고치고,
기계 검사와 채우기 시험과 사람 승인을 거친 뒤에만 승인본으로 올림. 초안이 있는 동안 설계 도구는 초안을 읽음.

실행(ttl 폴더에서):
  python tools/draft.py start      승인본을 초안 폴더로 복사함. 이때의 승인본 지문을 적어 둠
  python tools/draft.py diff       초안이 승인본과 달라진 곳을 파일과 대상별로 보여 줌 → draft-ttl/output/diff.json
  python tools/draft.py promote    검사를 통과한 초안을 승인본으로 올리고 graph_schema.json을 다시 만듦. 초안 폴더는 지움
  python tools/draft.py discard    초안 폴더를 지움(승인본은 그대로)
"""
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

from rdflib import BNode
from rdflib.compare import to_canonical_graph

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_from_ttl  # noqa: E402
import check_ttl  # noqa: E402
import ttl_write as w  # noqa: E402
from ttl_write import DRAFT_DIR, FILES, TTL_DIR, turtle  # noqa: E402
from core_turtle import local  # noqa: E402

BASE_FILE = DRAFT_DIR / "BASE.json"  # 초안을 시작할 때의 승인본 지문. 그 사이 승인본이 바뀌었는지 올리기 전에 봄


def version_of(ttl_dir: Path) -> str:
    """card.ttl의 판 번호(owl:versionInfo)만 읽음. 공통 개념을 읽는 규칙이 바뀌어도 옛 승인본과 견줄 수 있게 따로 읽음."""
    from rdflib.namespace import OWL
    from core_turtle import CARD
    return str(turtle.read(ttl_dir / "card.ttl").value(CARD.ontology, OWL.versionInfo))


def start() -> None:
    if DRAFT_DIR.exists():
        raise SystemExit(f"초안이 이미 있음: {DRAFT_DIR}. 이어서 고치거나 discard로 지운 뒤 다시 시작함")
    for name in FILES:
        (DRAFT_DIR / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(TTL_DIR / name, DRAFT_DIR / name)
    BASE_FILE.write_text(json.dumps({"approved_signature": turtle.signature(TTL_DIR),
                                     "started_at": datetime.now().isoformat(timespec="seconds")}, indent=2), encoding="utf-8")
    print(f"초안 시작: 승인본 파일 {len(FILES)}개를 {DRAFT_DIR.relative_to(w.PROJECT).as_posix()}로 복사함")


def owner(graph, node) -> str:
    """이름 없는 노드가 딸린 이름 있는 대상을 찾아 올라감(예: 셰이프의 속성 줄 → 그 셰이프)."""
    seen = set()
    while isinstance(node, BNode) and node not in seen:
        seen.add(node)
        parent = next(graph.subjects(None, node), None)
        if parent is None:
            return "(이름 없는 노드)"
        node = parent
    return local(node)


def diff() -> list[dict]:
    """파일마다 더한 문장 수, 뺀 문장 수, 달라진 대상(Class, 관계, 셰이프, 맞추기 표 행)을 돌려줌."""
    if not DRAFT_DIR.exists():
        raise SystemExit("초안이 없음. tools/draft.py start로 시작함")
    rows = []
    for name in FILES:
        # 이름 없는 노드의 번호를 내용 기준으로 다시 매긴 그래프끼리 견줌(같은 그래프에서 딸린 대상을 찾아야 이름이 나옴)
        old, new = to_canonical_graph(turtle.read(TTL_DIR / name)), to_canonical_graph(turtle.read(DRAFT_DIR / name))
        removed, added = old - new, new - old
        if len(removed) or len(added):
            subjects = sorted({owner(old, s) for s in removed.subjects()} | {owner(new, s) for s in added.subjects()})
            rows.append({"file": name, "added": len(added), "removed": len(removed), "subjects": subjects})
    return rows


def show_diff() -> None:
    rows = diff()
    out = DRAFT_DIR / "output" / "diff.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    if not rows:
        print("초안이 승인본과 같음(달라진 문장 없음)")
    for row in rows:
        print(f"{row['file']}: 더한 문장 {row['added']}개, 뺀 문장 {row['removed']}개, 달라진 대상 {', '.join(row['subjects'])}")


def promote() -> dict:
    """초안을 승인본으로 올림. 올리기 전에 승인본이 그 사이 바뀌지 않았는지, 초안이 검사를 통과하는지 봄."""
    if not DRAFT_DIR.exists():
        raise SystemExit("초안이 없음")
    base = json.loads(BASE_FILE.read_text(encoding="utf-8"))
    if turtle.signature(TTL_DIR) != base["approved_signature"]:
        raise SystemExit("승인본이 초안을 시작한 뒤에 바뀌었음(다른 설계가 고친 것). 올리지 않음. 바뀐 내용을 초안에 반영한 뒤 다시 함")
    changed = diff()
    meaning_changed = [c["file"] for c in changed if not c["file"].startswith("maps/")]  # 맞추기 표만 바뀐 것은 판을 올리지 않음
    if meaning_changed and version_of(DRAFT_DIR) == version_of(TTL_DIR):
        raise SystemExit(f"Class, 관계, 셰이프, 검사 규칙이 바뀌었는데({meaning_changed}) 판 번호가 그대로임. "
                         "초안 card.ttl의 card:ontology owl:versionInfo를 올린 뒤 다시 함")
    report = check_ttl.run(DRAFT_DIR, "draft")
    if not report["ok"]:
        check_ttl.show(report)
        raise SystemExit("초안이 검사를 통과하지 못해 올리지 않음")
    for name in FILES:
        shutil.copyfile(DRAFT_DIR / name, TTL_DIR / name)
    build_from_ttl.build(TTL_DIR, "saved")
    after = check_ttl.run(TTL_DIR, "saved")
    result = {"promoted_at": datetime.now().isoformat(timespec="seconds"), "changed": changed, "signature": after["signature"],
              "check_ok": after["ok"], "problems": after["problems"]}
    out = TTL_DIR / "output" / "last_promote.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    if not after["ok"]:
        check_ttl.show(after)
        raise SystemExit("올린 뒤 승인본 검사가 실패함. 초안 폴더를 남겨 둠")
    shutil.rmtree(DRAFT_DIR)
    print(f"승인본으로 올림: 달라진 파일 {len(changed)}개, 지문 {after['signature'][:16]}. 초안 폴더는 지움")
    return result


def discard() -> None:
    if DRAFT_DIR.exists():
        shutil.rmtree(DRAFT_DIR)
    print("초안 폴더를 지움")


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    actions = {"start": start, "diff": show_diff, "promote": promote, "discard": discard}
    if command not in actions:
        raise SystemExit(__doc__)
    actions[command]()
