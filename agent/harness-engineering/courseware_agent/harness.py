"""자기 개선(RSI)되는 하네스 저장소.

에이전트의 '하네스'(역할별 추가 프롬프트 규칙, 결정적 lint 규칙, 설정값)를 버전으로 관리한다.
- 개선자(improver)가 실행 기록을 보고 다음 버전을 제안한다 → 정적 검증 → '시험(trial)' 버전으로 적용
- 시험 버전으로 만든 결과의 지표를 부모 버전과 비교해 채택하거나 자동으로 되돌린다
- 개선자 자신의 규칙(role=improver)도 하네스에 들어 있어서, 개선 방식 자체가 개선된다(재귀)

코드(파이썬)는 바꾸지 않고 데이터만 바꾼다. 코드에 박힌 기본 규칙(가이드 준수, 지어낸 URL 금지 등)은
하네스가 지울 수 없다. 모든 변경은 versions/, CHANGELOG.md, proposals.jsonl 에 남는다.
"""
from __future__ import annotations

import copy
import json
import logging
import re
from datetime import datetime
from pathlib import Path
from statistics import mean

log = logging.getLogger("courseware")

ROLES = ("planner", "writer", "reviewer", "slides", "slide_reviewer", "improver")

# set_config 로 바꿀 수 있는 설정과 허용 범위(코드가 소유, 개선자는 범위 밖으로 못 나감)
CONFIG_BOUNDS: dict[str, tuple[float, float]] = {
    "pass_score": (7.5, 9.0),
    "max_revisions": (1, 4),
    "min_chapter_chars": (4000, 12000),
    "concurrency": (1, 4),
}
INT_KEYS = {"max_revisions", "min_chapter_chars", "concurrency"}

MAX_RULES_PER_ROLE = 8
MAX_LINT_RULES = 12
MAX_ACCEPTED = 4
TRIAL_MIN_SAMPLES = 3
ROLLBACK_MARGIN = 0.25


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _strip_code(text: str) -> str:
    return re.sub(r"```.*?```", "", text, flags=re.S)


class Harness:
    def __init__(self, root: Path) -> None:
        self.root = root
        (root / "versions").mkdir(parents=True, exist_ok=True)
        (root / "logs").mkdir(exist_ok=True)
        self.current_path = root / "current.json"
        self.metrics_path = root / "metrics.jsonl"
        self.proposals_path = root / "proposals.jsonl"
        self.changelog_path = root / "CHANGELOG.md"
        if self.current_path.exists():
            self.data = json.loads(self.current_path.read_text(encoding="utf-8"))
        else:
            self.data = {
                "version": 1, "parent": None, "status": "stable", "created_at": _now(),
                "prompt_rules": {r: [] for r in ROLES}, "lint_rules": [], "config": {}, "next_id": 1,
            }
            self._snapshot()
            self._changelog(1, "초기 하네스", ["코드에 들어 있는 기본 규칙만 사용"])
            self.save()

    # ------------------------------------------------------------ 기본

    @property
    def version(self) -> int:
        return self.data["version"]

    @property
    def status(self) -> str:
        return self.data["status"]

    def save(self) -> None:
        tmp = self.current_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.current_path)

    def _snapshot(self) -> None:
        (self.root / "versions" / f"v{self.version:03d}.json").write_text(
            json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")

    def _load_version(self, version: int) -> dict:
        return json.loads((self.root / "versions" / f"v{version:03d}.json").read_text(encoding="utf-8"))

    def _changelog(self, version: int, title: str, lines: list[str]) -> None:
        if not self.changelog_path.exists():
            self.changelog_path.write_text("# 하네스 변경 이력\n\n자기 개선 루프가 만든 버전과 그 근거를 시간순으로 남깁니다.\n\n",
                                           encoding="utf-8")
        with self.changelog_path.open("a", encoding="utf-8") as f:
            f.write(f"## v{version} — {title} ({_now()})\n\n" + "\n".join(f"- {ln}" for ln in lines) + "\n\n")

    # ------------------------------------------------------------ 적용

    def system(self, role: str, base: str) -> str:
        """역할 시스템 프롬프트에 하네스가 학습한 규칙을 덧붙인다."""
        rules = self.data["prompt_rules"].get(role, [])
        if not rules:
            return base
        lines = "\n".join(f"- {r['text']}" for r in rules)
        return f"{base}\n\n추가 규칙(하네스 v{self.version}, 이전 실행 기록에서 학습함)\n{lines}"

    def apply_config(self, settings) -> None:
        for key, value in self.data["config"].items():
            if key in CONFIG_BOUNDS:
                setattr(settings, key, int(value) if key in INT_KEYS else float(value))

    def extra_lint(self, target: str, text: str) -> list[str]:
        """하네스 lint 규칙 적용. 교재 본문은 코드 블록을 빼고 검사한다."""
        body = _strip_code(text) if target == "text" else text
        errors = []
        for rule in self.data["lint_rules"]:
            if rule["target"] != target:
                continue
            try:
                found = re.findall(rule["pattern"], body, flags=re.M)
            except re.error:
                continue
            if rule["mode"] == "forbid" and found:
                errors.append(f"[하네스 {rule['id']}] {rule['message']} ({len(found)}곳)")
            elif rule["mode"] == "require" and not found:
                errors.append(f"[하네스 {rule['id']}] {rule['message']}")
        return errors

    # ------------------------------------------------------------ 지표

    def record(self, **metric) -> None:
        metric = {"at": _now(), "version": self.version, **metric}
        with self.metrics_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(metric, ensure_ascii=False) + "\n")

    def metrics(self) -> list[dict]:
        if not self.metrics_path.exists():
            return []
        return [json.loads(ln) for ln in self.metrics_path.read_text(encoding="utf-8").splitlines() if ln.strip()]

    @staticmethod
    def quality(rows: list[dict]) -> float:
        """첫 검토 점수가 높고, 수정 횟수와 첫 lint 오류가 적을수록 높다."""
        return mean(r["first_score"] - 0.3 * r["revisions"] - 0.1 * min(r["first_lint"], 10) for r in rows)

    def evaluate_trial(self) -> dict | None:
        """시험 버전의 표본이 충분하면 부모와 비교해 채택하거나 되돌린다. 판정했으면 결과를 돌려준다."""
        if self.status != "trial":
            return None
        rows = self.metrics()
        trial = [r for r in rows if r["version"] == self.version]
        if len(trial) < TRIAL_MIN_SAMPLES:
            return None
        parent = self.data["parent"]
        # 같은 종류(text/slides)끼리 비교, 부모 표본이 없으면 그 이전 전체를 기준선으로 쓴다
        deltas, weights = [], []
        for kind in {r["kind"] for r in trial}:
            t = [r for r in trial if r["kind"] == kind]
            base = [r for r in rows if r["version"] == parent and r["kind"] == kind] or \
                   [r for r in rows if r["version"] < self.version and r["kind"] == kind]
            if base:
                deltas.append(self.quality(t) - self.quality(base))
                weights.append(len(t))
        delta = sum(d * w for d, w in zip(deltas, weights)) / sum(weights) if weights else 0.0
        verdict = "rolled_back" if delta < -ROLLBACK_MARGIN else "adopted"
        result = {"version": self.version, "parent": parent, "delta": round(delta, 3),
                  "samples": len(trial), "verdict": verdict}
        self._set_outcome(self.version, verdict, result)
        if verdict == "adopted":
            self.data["status"] = "stable"
            self._snapshot()
            self._changelog(self.version, "시험 통과 → 채택", [f"품질 변화 {delta:+.2f} (표본 {len(trial)}개)"])
        else:
            failed = self.version
            restored = self._load_version(parent)
            restored["status"] = "stable"
            restored["created_at"] = _now()   # 롤백 뒤 새 표본이 쌓일 때까지 다음 제안을 미룬다
            restored["next_id"] = max(restored["next_id"], self.data["next_id"])
            self.data = restored
            self._changelog(failed, f"시험 실패 → v{parent}로 되돌림", [f"품질 변화 {delta:+.2f} (표본 {len(trial)}개)"])
        self.save()
        return result

    # ------------------------------------------------------------ 제안

    def view(self) -> str:
        lines = [f"버전 v{self.version} ({self.status})"]
        for role in ROLES:
            for r in self.data["prompt_rules"].get(role, []):
                lines.append(f"- [{r['id']}] prompt/{role}: {r['text']}")
        for r in self.data["lint_rules"]:
            lines.append(f"- [{r['id']}] lint/{r['target']}/{r['mode']}: /{r['pattern']}/ → {r['message']}")
        lines.append(f"- 설정: {json.dumps(self.data['config'], ensure_ascii=False) or '{}'}")
        return "\n".join(lines)

    def track_record(self, limit: int = 10) -> str:
        if not self.proposals_path.exists():
            return ""
        rows = [json.loads(ln) for ln in self.proposals_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        out = []
        for row in rows[-limit:]:
            accepted = "; ".join(f"{p['action']}({p.get('role') or p.get('rule_id') or p.get('config_key')}): "
                                 f"{(p.get('text') or p.get('lint', {}).get('message') or '')[:80]}" for p in row["accepted"])
            rejected = "; ".join(f"{x['reason']}" for x in row["rejected"])
            out.append(f"- v{row.get('created_version')}: 결과={row['outcome']} {row.get('eval') or ''}\n"
                       f"  채택 제안: {accepted or '없음'}\n  거부된 제안: {rejected or '없음'}")
        return "\n".join(out)

    def samples_since_last_proposal(self) -> int:
        last = self.data["created_at"]
        return sum(1 for r in self.metrics() if r["at"] >= last)

    def propose(self, diagnosis: str, proposals: list[dict], corpus: dict[str, list[str]]) -> dict:
        """정적 검증을 통과한 제안으로 새 시험 버전을 만든다. corpus 는 lint 규칙 과잉 탐지 점검용 기존 결과물."""
        candidate = copy.deepcopy(self.data)
        accepted, rejected = [], []
        for p in proposals:
            if len(accepted) >= MAX_ACCEPTED:
                rejected.append({"proposal": p, "reason": "한 번에 최대 4개"})
                continue
            reason = self._apply(candidate, p, corpus)
            (rejected.append({"proposal": p, "reason": reason}) if reason else accepted.append(p))

        record = {"at": _now(), "from_version": self.version, "diagnosis": diagnosis,
                  "accepted": accepted, "rejected": rejected, "outcome": "no_change", "eval": None}
        if accepted:
            candidate.update({"version": self._next_version(), "parent": self.version,
                              "status": "trial", "created_at": _now()})
            self.data = candidate
            self._snapshot()
            self.save()
            record["created_version"] = self.version
            record["outcome"] = "pending"
            self._changelog(self.version, f"시험 버전 생성 (부모 v{candidate['parent']})",
                            [f"진단: {diagnosis[:300]}"] + [_describe(p) for p in accepted] +
                            [f"거부: {x['reason']}" for x in rejected])
        with self.proposals_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        return record

    def _next_version(self) -> int:
        existing = [int(p.stem[1:]) for p in (self.root / "versions").glob("v*.json")]
        return max(existing + [self.version]) + 1

    def _new_id(self, cand: dict, prefix: str) -> str:
        rid = f"{prefix}{cand['next_id']}"
        cand["next_id"] += 1
        return rid

    def _apply(self, cand: dict, p: dict, corpus: dict[str, list[str]]) -> str | None:
        """제안 하나를 후보에 적용한다. 거부하면 이유 문자열."""
        action = p.get("action")
        if action == "add_prompt_rule":
            role, text = p.get("role"), (p.get("text") or "").strip()
            if role not in ROLES:
                return f"알 수 없는 역할 '{role}'"
            if not 10 <= len(text) <= 300:
                return "규칙 길이는 10~300자"
            rules = cand["prompt_rules"].setdefault(role, [])
            if any(r["text"] == text for r in rules):
                return "이미 있는 규칙"
            if len(rules) >= MAX_RULES_PER_ROLE:
                return f"{role} 규칙이 이미 {MAX_RULES_PER_ROLE}개 — 먼저 정리할 것"
            rules.append({"id": self._new_id(cand, "r"), "text": text, "since": self._next_version()})
            return None
        if action == "remove_prompt_rule":
            for role, rules in cand["prompt_rules"].items():
                for r in rules:
                    if r["id"] == p.get("rule_id"):
                        rules.remove(r)
                        return None
            return f"규칙 id '{p.get('rule_id')}' 없음"
        if action == "add_lint_rule":
            lint = p.get("lint") or {}
            target, mode, pattern, message = lint.get("target"), lint.get("mode"), lint.get("pattern", ""), lint.get("message", "")
            if target not in ("text", "slides") or mode not in ("forbid", "require"):
                return "lint target/mode 값이 잘못됨"
            if not pattern or len(pattern) > 200 or not message.strip():
                return "lint pattern 또는 message 가 비었거나 너무 김"
            try:
                rx = re.compile(pattern, re.M)
            except re.error as err:
                return f"정규식 오류: {err}"
            if len(cand["lint_rules"]) >= MAX_LINT_RULES:
                return f"lint 규칙이 이미 {MAX_LINT_RULES}개"
            docs = corpus.get(target, [])
            if len(docs) >= 3:
                hits = sum(bool(rx.search(_strip_code(d) if target == "text" else d)) for d in docs)
                if mode == "forbid" and hits == len(docs):
                    return f"과잉 탐지: 기존 결과물 {len(docs)}개 모두에서 걸림"
                if mode == "require" and hits == 0:
                    return f"과잉 탐지: 기존 결과물 {len(docs)}개 모두 요구 조건 불만족"
            cand["lint_rules"].append({"id": self._new_id(cand, "l"), "target": target, "mode": mode,
                                       "pattern": pattern, "message": message.strip(), "since": self._next_version()})
            return None
        if action == "remove_lint_rule":
            for r in cand["lint_rules"]:
                if r["id"] == p.get("rule_id"):
                    cand["lint_rules"].remove(r)
                    return None
            return f"lint 규칙 id '{p.get('rule_id')}' 없음"
        if action == "set_config":
            key, value = p.get("config_key"), p.get("config_value")
            if key not in CONFIG_BOUNDS:
                return f"바꿀 수 없는 설정 '{key}'"
            lo, hi = CONFIG_BOUNDS[key]
            if not isinstance(value, (int, float)) or not lo <= value <= hi:
                return f"{key} 값 {value} 은 허용 범위 {lo}~{hi} 밖"
            cand["config"][key] = int(value) if key in INT_KEYS else float(value)
            return None
        return f"알 수 없는 action '{action}'"

    def _set_outcome(self, version: int, outcome: str, result: dict) -> None:
        if not self.proposals_path.exists():
            return
        rows = [json.loads(ln) for ln in self.proposals_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        for row in rows:
            if row.get("created_version") == version:
                row["outcome"], row["eval"] = outcome, result
        self.proposals_path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")

    # ------------------------------------------------------------ 사람이 보는 보고서

    def write_report(self, cycles: list[dict] | None = None, extra: str = "") -> Path:
        rows = self.metrics()
        lines = ["# RSI 보고서 — 교재 제작 에이전트의 자기 개선 기록", "",
                 f"갱신: {_now()}", "",
                 "이 파일은 데몬이 사이클마다 다시 씁니다. 버전별 상세 근거는 [CHANGELOG.md](CHANGELOG.md),",
                 "실행 로그는 [logs/rsi.log](logs/rsi.log)에 있습니다.", "",
                 "## 현재 하네스", "", "```", self.view(), "```", "",
                 "## 버전별 품질", "",
                 "품질 = 첫 검토 점수 − 0.3×수정 횟수 − 0.1×첫 lint 오류 수 (높을수록 좋음)", "",
                 "| 버전 | 표본 | 첫 검토 평균 | 평균 수정 | 품질 |", "|---|---|---|---|---|"]
        for v in sorted({r["version"] for r in rows}):
            vr = [r for r in rows if r["version"] == v]
            lines.append(f"| v{v} | {len(vr)} | {mean(r['first_score'] for r in vr):.2f} | "
                         f"{mean(r['revisions'] for r in vr):.2f} | {self.quality(vr):.2f} |")
        lines += ["", "## 개선 제안과 결과", ""]
        track = self.track_record(limit=15)
        lines.append(track or "- 아직 없음")
        if cycles:
            lines += ["", "## 최근 사이클", "", "| 시작 | 끝 | 주제 | 한 일 | 결과 |", "|---|---|---|---|---|"]
            for c in cycles[-20:]:
                lines.append(f"| {c.get('start', '')} | {c.get('end', '')} | {c.get('topic', '')} | "
                             f"{c.get('action', '')} | {c.get('result', '')} |")
        if extra:
            lines += ["", extra]
        path = self.root / "RSI_REPORT.md"
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return path


def _describe(p: dict) -> str:
    action = p["action"]
    if action == "add_prompt_rule":
        return f"규칙 추가 [{p['role']}]: {p['text']} — 근거: {p.get('rationale', '')}"
    if action == "add_lint_rule":
        lint = p["lint"]
        return f"lint 추가 [{lint['target']}/{lint['mode']}] /{lint['pattern']}/: {lint['message']} — 근거: {p.get('rationale', '')}"
    if action == "set_config":
        return f"설정 변경 {p['config_key']}={p['config_value']} — 근거: {p.get('rationale', '')}"
    return f"{action} {p.get('rule_id', '')} — 근거: {p.get('rationale', '')}"
