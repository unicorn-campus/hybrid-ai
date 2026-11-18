"""주제 맞추기 표(라운드 1 판정 F4): LLM이 지은 주제 이름을 대표 주제로 묶는 후보를 LLM이 내고, 사람이 확정함.

- 입력: 채우기 시험(또는 인덱싱) 결과의 Topic 이름. 문서 종류마다 나온 건수와 그 주제를 단 단위의 제목을 함께 넘김
- 출력: common/output/topic_candidates.json(대표 주제, 묶인 이름, 까닭, 미정)
- 확정: common/topic_map_approved.json. 사람이 확정한 행만 approved, 나머지는 needs_review. 인덱싱은 approved 행만 대표 이름으로 합침
- 대표 주제 목록은 AI가 혼자 확정하지 않음(공통 개념의 값이 되기 때문)
실행: python common/tools/draft_topic_map.py draft [--from {인덱서 세대 폴더}/new_map_items.json]
      python common/tools/draft_topic_map.py approve {결정 파일}
"""

from __future__ import annotations

import collections
import json
import re
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE / "tools"))

from common import DOC_TYPES, read_json, write_json  # noqa: E402

CANDIDATES = BASE / "common/output/topic_candidates.json"
APPROVED = BASE / "common/topic_map_approved.json"
DOC_NAMES = {"regulation": "약관", "benefit_guide": "카드 혜택 안내", "consult_log": "상담 기록"}

PROMPT = """너는 여러 문서(약관, 카드 혜택 안내, 상담 기록)에서 LLM이 뽑은 「주제」 이름을 대표 주제로 묶는 도우미다.
목적: 서로 다른 문서에서 같은 업무 대상을 가리키는 이름을 같은 대표 주제로 묶어, 상담의 불만과 관련 약관 조항, 카드 혜택이 이어지게 한다.
규칙
- 대표 주제는 업무 대상을 2 ~ 8글자 명사로 쓴다(예: 연회비, 본인 확인, 통지 방법, 혜택 신청, 이의신청)
- 뜻이 같거나 한쪽이 다른 쪽의 일부인 이름은 같은 대표 주제로 묶는다. 특히 다른 문서 종류의 이름끼리 묶을 수 있는지 먼저 본다
  (예: 상담의 「광고 수신」과 약관의 「통지 방법」은 회원이 고른 수단으로 알리는 일이라 같은 대표 주제가 될 수 있다)
- 묶을 짝이 없는 이름은 그 이름 하나로 대표 주제를 만든다
- 「혜택」, 「할인」, 「안내」, 「계산」처럼 너무 넓어 무엇이든 이어 버리는 이름은 「미정」으로 한다
- 목록에 없는 이름을 키로 넣지 않는다
JSON 하나로만 답한다. map에는 목록의 모든 이름을 키로 넣고 값은 대표 주제 또는 "미정"으로 쓴다.
reasons에는 둘 이상의 이름을 묶은 대표 주제마다 까닭 한 문장을 쓴다:
{{"map": {{"이름": "대표 주제", "...": "미정"}}, "reasons": {{"대표 주제": "한 문장"}}}}

주제 이름 목록(이름 | 나온 문서 종류와 건수 | 그 주제를 단 단위 제목 예):
{names}
"""


def squash(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


def collect_from(source: str) -> dict[str, dict]:
    """인덱서가 남긴 new_map_items.json의 주제 이름(문서 종류별 건수)을 collect와 같은 꼴로 바꿈."""
    names = {}
    for item in read_json(source)["topics"]:
        names[squash(item["name"])] = {"name": item["name"], "docs": collections.Counter(item["docs"]), "examples": []}
    return names


def collect() -> dict[str, dict]:
    """세 문서 종류의 시험 결과에서 주제 이름을 모음(띄어쓰기 차이는 하나로)."""
    names = {}
    for doc_type in DOC_TYPES:
        titles = {u["unit_id"]: u.get("header", "") for u in read_json(BASE / doc_type / "output/test_units.json")}
        for line in (BASE / doc_type / "output/fill_calls.jsonl").read_text(encoding="utf-8").splitlines():
            record = json.loads(line)
            for node in record["graph"]["nodes"]:
                if node["label"] != "Topic" or not node["properties"].get("name"):
                    continue
                name = node["properties"]["name"].strip()
                entry = names.setdefault(squash(name), {"name": name, "docs": collections.Counter(), "examples": []})
                entry["docs"][doc_type] += 1
                header = titles.get(record["unit_id"], "")
                title = (re.search(r"(?:title|항목 제목): ([^|\]]+)", header) or [None, record["unit_id"]])[1]
                if len(entry["examples"]) < 2:
                    entry["examples"].append(title.strip())
    return names


def draft(source: str | None = None) -> None:
    """확정 표(topic_map_approved.json)에 이미 있는 이름은 다시 묻지 않고, 새 이름만 LLM에 넘김.
    새 이름은 확정 표의 대표 주제로 넣을 수도 있게 그 목록을 함께 줌(라운드 3부터)."""
    from llm import make_llm
    names = collect_from(source) if source else collect()  # source: 인덱서의 new_map_items.json
    settled, reps = {}, []
    if APPROVED.exists():
        for r in read_json(APPROVED)["rows"]:
            settled[squash(r["name"])] = r
        reps = sorted({r["representative"] for r in settled.values() if r["representative"]})
    all_names = names
    names = {k: e for k, e in names.items() if k not in settled}
    listing = "\n".join(f"- {e['name']} | " + ", ".join(f"{DOC_NAMES[d]} {n}" for d, n in e["docs"].items())
                        + f" | {', '.join(e['examples'])}" for e in sorted(names.values(), key=lambda e: e["name"]))
    if not names:
        print("새 주제 이름 없음. 확정 표 그대로 씀")
        write_json(CANDIDATES, {"names": 0, "names_total": len(all_names), "already_settled": len(all_names),
                                "groups": [], "undecided": [], "missing_from_llm": [], "llm_calls": 0, "retries": []})
        return
    llm = make_llm(effort="low", max_tokens=16000)  # 이름 107개를 한 번에 묶으므로 출력 한도를 넓힘(기본 3,072토큰에서 잘림)
    prompt = PROMPT.format(names=listing)
    if reps:  # 라운드 3부터: 새 이름을 이미 확정한 대표 주제에 넣을 수 있게 그 목록을 줌
        prompt += ("\n이미 사람이 확정한 대표 주제(새 이름이 이 가운데 하나와 같은 뜻이면 그 대표 주제를 그대로 씀):\n"
                   + ", ".join(reps) + "\n")
    answer, errors = None, []
    for attempt in range(3):  # 형식 오류(JSON 검증 실패)는 같은 입력으로 2번까지 다시 물음
        try:
            answer = json.loads(llm.chat_json(prompt))
            break
        except Exception as error:
            errors.append(f"{type(error).__name__}: {str(error)[:120]}")
    if answer is None:
        raise SystemExit(f"맞추기 표 초안 실패: {errors}")
    known = {squash(e["name"]): e["name"] for e in names.values()}
    by_rep = collections.defaultdict(list)
    undecided, seen = [], set()
    for raw, rep in answer.get("map", {}).items():
        key = squash(raw)
        if key not in known or key in seen:
            continue
        seen.add(key)
        if not rep or squash(rep) == "미정":
            undecided.append(known[key])
        else:
            by_rep[rep.strip()].append(known[key])
    groups = []
    for rep, members in by_rep.items():
        docs = sorted({d for m in members for d in names[squash(m)]["docs"]})
        groups.append({"representative": rep, "members": members, "reason": answer.get("reasons", {}).get(rep, ""),
                       "doc_types": docs, "cross_doc": len(docs) > 1})
    missing = [e["name"] for k, e in names.items() if k not in seen]  # LLM이 빠뜨린 이름은 미정으로 둠
    write_json(CANDIDATES, {"names": len(names), "names_total": len(all_names), "already_settled": len(all_names) - len(names),
                            "groups": groups, "undecided": undecided + missing,
                            "missing_from_llm": missing, "llm_calls": llm.usage["calls"], "retries": errors})
    print(f"이름 {len(names)}개 → 대표 주제 {len(groups)}개(문서 종류를 넘는 것 {sum(g['cross_doc'] for g in groups)}개), "
          f"미정 {len(undecided) + len(missing)}개(LLM이 빠뜨림 {len(missing)})")


def approve(decision_file: str, out: Path = APPROVED) -> None:
    """결정 파일: {"decided_by", "date", "approve_groups": [대표 주제...] | "all", "rename": {옛 대표: 새 대표},
    "move": {이름: 대표 주제}, "not_linked": [이름...]}. 적지 않은 미정 이름은 needs_review."""
    decision = read_json(decision_file)
    cand = read_json(CANDIDATES)
    rows = []
    approve_all = decision.get("approve_groups") == "all"
    for g in cand["groups"]:
        rep = decision.get("rename", {}).get(g["representative"], g["representative"])
        ok = approve_all or g["representative"] in decision.get("approve_groups", [])
        for m in g["members"]:
            if m in decision.get("move", {}) or m in decision.get("not_linked", []):
                continue
            rows.append({"name": m, "representative": rep, "status": "approved" if ok else "needs_review"})
    for name, rep in decision.get("move", {}).items():
        rows.append({"name": name, "representative": rep, "status": "approved"})
    for name in decision.get("not_linked", []):
        rows.append({"name": name, "representative": None, "status": "not_linked"})
    done = {squash(r["name"]) for r in rows}
    rows += [{"name": n, "representative": None, "status": "needs_review"} for n in cand["undecided"] if squash(n) not in done]
    if out == APPROVED and APPROVED.exists():  # 앞서 확정한 행은 지우지 않고 그대로 둠(이번에 새로 정한 이름만 보탬)
        new_keys = {squash(r["name"]) for r in rows}
        rows = [r for r in read_json(APPROVED)["rows"] if squash(r["name"]) not in new_keys] + rows
    write_json(out, {"decided_by": decision["decided_by"], "date": decision["date"], "status": decision.get("status", "approved"), "rows": rows})
    print({s: sum(1 for r in rows if r["status"] == s) for s in ("approved", "not_linked", "needs_review")})


if __name__ == "__main__":
    if sys.argv[1] == "draft":
        draft(sys.argv[3] if len(sys.argv) > 3 and sys.argv[2] == "--from" else None)
    elif sys.argv[1] == "propose":  # 사람 확정 전 제안: 확정 파일이 아니라 output/topic_map_proposal.json에 씀
        approve(sys.argv[2], BASE / "common/output/topic_map_proposal.json")
    else:
        approve(sys.argv[2])
