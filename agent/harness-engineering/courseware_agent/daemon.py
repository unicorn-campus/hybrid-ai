"""이 PC에서만 백그라운드로 계속 도는 RSI 데몬 (여러 주제).

사이클마다 주제 하나를 골라
1) 교재가 아직 완성되지 않은 주제(새로 추가한 주제 포함)는 이어서 만들고
2) 모두 완성됐으면 가장 오래 손대지 않은 주제에서 가장 약한 장(본문 또는 슬라이드)을
   현재 하네스로 다시 만든다(나아질 때만 교체)
3) 그 지표로 하네스 시험 버전을 판정하고 새 개선안을 만든다(재귀적 자기 개선).
   하네스는 모든 주제가 함께 쓰므로 한 주제에서 배운 규칙이 다른 주제에도 쓰인다
4) 사람이 읽는 기록을 남긴다: harness/RSI_REPORT.md, harness/CHANGELOG.md, harness/logs/rsi.log, harness/cycles.jsonl

주제 목록은 harness/daemon.json 의 topics 이고, 사이클마다 다시 읽으므로 실행 중에 추가해도 된다.
    python run.py --add-topic "쿠버네티스 운영" --audience "운영 담당 개발자" [--slug k8s-operations]
결과물은 output/<영문 슬러그>/ 에 쌓인다. 슬러그를 주지 않으면 Claude가 짓고, 실패하면 로마자 표기를 쓴다.
    python run.py --remove-topic "쿠버네티스 운영"

안전장치
- 이 PC 고정: 처음 실행한 PC의 식별값(호스트 이름, 하드웨어 노드 ID)을 harness/machine.json 에 기록하고
  다른 PC에서는 실행을 거부한다
- 한 PC에 한 개만: harness/daemon.lock 파일 잠금
- 하루 비용, 사이클 상한(harness/daemon.json), 연속 실패 시 대기 시간을 늘림
- harness/STOP 파일을 만들면 현재 작업을 마친 뒤 종료한다
"""
from __future__ import annotations

import getpass
import json
import logging
import os
import re
import socket
import sys
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path

import anyio

from .config import SLUG_RE, Settings, slugify
from .harness import Harness
from .llm import ask, ledger
from .notify import DEFAULT_NOTIFY, Notifier
from .orchestrator import CoursewareAgent

log = logging.getLogger("courseware")

DEFAULT_DAEMON_CONFIG = {
    "topics": [
        {"topic": "파이썬 AI 프로그램 하네스 엔지니어링", "slug": "python-ai-harness-engineering",
         "audience": "파이썬으로 LLM 기반 AI 프로그램(에이전트, RAG, 업무 자동화)을 개발하는 개발자",
         "scope": "파이썬으로 개발하는 AI 프로그램에 하네스(에이전트 루프, 도구, 컨텍스트, 구조화 출력과 검증, "
                  "가드레일, 재시도, 상태 저장, 평가, 관측, 비용 관리, 자기 개선 루프)를 설계하고 파이썬 코드로 "
                  "구현하는 실습 중심. 코딩 에이전트 사용법(AGENTS.md 등)은 배경으로만 짧게 다룬다.",
         "enabled": True},
    ],
    "interval_minutes": 20,
    "daily_budget_usd": 40.0,
    "max_cycles_per_day": 48,
    "notify": DEFAULT_NOTIFY,   # 작업 변경 요약 메일(.env 의 SMTP 설정, RECIPIENTS)
}


# ================================================================ 이 PC 고정, 단일 실행

def machine_identity() -> dict:
    return {"hostname": socket.gethostname(), "node": uuid.getnode(), "user": getpass.getuser()}


def ensure_this_machine(root: Path) -> dict:
    """처음이면 이 PC를 등록하고, 다른 PC면 종료한다."""
    path = root / "machine.json"
    me = machine_identity()
    if not path.exists():
        path.write_text(json.dumps({**me, "registered_at": datetime.now().isoformat(timespec="seconds")},
                                   ensure_ascii=False, indent=2), encoding="utf-8")
        return me
    saved = json.loads(path.read_text(encoding="utf-8"))
    if (saved["hostname"], saved["node"]) != (me["hostname"], me["node"]):
        raise SystemExit(f"RSI 데몬은 등록된 PC({saved['hostname']})에서만 실행됩니다. 현재 PC: {me['hostname']}")
    return me


class SingleInstance:
    """파일 잠금으로 데몬이 한 개만 돌게 한다. 프로세스가 죽으면 OS가 잠금을 풀어 준다."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.fh = None

    def __enter__(self):
        self.fh = open(self.path, "a+")
        try:
            if os.name == "nt":
                import msvcrt
                self.fh.seek(0)
                msvcrt.locking(self.fh.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.fh.close()
            raise SystemExit("RSI 데몬이 이미 실행 중입니다 (harness/daemon.lock)")
        (self.path.parent / "daemon.pid").write_text(str(os.getpid()), encoding="utf-8")
        return self

    def __exit__(self, *exc):
        try:
            (self.path.parent / "daemon.pid").unlink(missing_ok=True)
            self.fh.close()
        except OSError:
            pass


# ================================================================ 주제 대기열

def _normalize_topic(entry) -> dict:
    if isinstance(entry, str):
        entry = {"topic": entry}
    topic = entry["topic"].strip()
    return {"topic": topic, "slug": entry.get("slug") or slugify(topic), "audience": entry.get("audience", ""),
            "scope": entry.get("scope", ""), "enabled": entry.get("enabled", True)}


def load_daemon_config(root: Path) -> dict:
    path = root / "daemon.json"
    cfg = json.loads(json.dumps(DEFAULT_DAEMON_CONFIG))
    saved = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    cfg.update(saved)
    cfg["notify"] = {**DEFAULT_NOTIFY, **saved.get("notify", {})}
    cfg["topics"] = [_normalize_topic(t) for t in cfg["topics"]]
    if not path.exists() or "notify" not in saved:
        save_daemon_config(root, cfg)
    return cfg


def save_daemon_config(root: Path, cfg: dict) -> None:
    (root / "daemon.json").write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


SLUG_SCHEMA = {"type": "object", "properties": {"slug": {"type": "string"}},
               "required": ["slug"], "additionalProperties": False}


async def _ask_slug(settings: Settings) -> str:
    res = await ask(
        settings,
        f"교재 주제 '{settings.topic}'의 출력 디렉토리 이름으로 쓸 짧은 영문 슬러그를 지어 줘. "
        "소문자 영어 단어 2~4개를 하이픈으로 이은 kebab-case(예: harness-engineering, kubernetes-operations).",
        system="너는 한국어 주제를 뜻이 통하는 짧은 영문 kebab-case 슬러그로 옮긴다. 로마자 음역이 아니라 영어 번역을 쓴다.",
        schema=SLUG_SCHEMA, label="slug", retries=1)
    return res.data["slug"].strip().lower()


def english_slug(root: Path, topic: str, taken: set[str]) -> str:
    """주제의 영문 디렉토리 이름. 영문 주제는 그대로, 한글 주제는 Claude가 번역하고 실패하면 로마자 표기."""
    slug = ""
    if not re.search(r"[^\x00-\x7f]", topic):
        slug = slugify(topic)
    else:
        settings = Settings(topic=topic, out_dir=root)
        settings.effort, settings.call_timeout_s = "low", 180
        try:
            candidate = anyio.run(_ask_slug, settings)
            if SLUG_RE.match(candidate) and len(candidate) <= 48:
                slug = candidate
        except Exception as err:
            log.warning("영문 슬러그 생성 실패, 로마자 표기 사용: %s", err)
    slug = slug or slugify(topic)
    base, n = slug, 2
    while slug in taken:
        slug, n = f"{base}-{n}", n + 1
    return slug


def add_topic(root: Path, topic: str, audience: str = "", slug: str = "", enabled: bool = True,
              scope: str = "") -> str:
    cfg = load_daemon_config(root)
    for t in cfg["topics"]:
        if t["topic"] == topic:
            t["enabled"] = t["enabled"] or enabled
            if audience:
                t["audience"] = audience
            if scope:
                t["scope"] = scope
            save_daemon_config(root, cfg)
            return f"주제 '{topic}' 다시 활성화 (output/{t['slug']})"
    taken = {t["slug"] for t in cfg["topics"]}
    if slug and (not SLUG_RE.match(slug) or slug in taken):
        raise SystemExit(f"슬러그 '{slug}'는 영문 소문자, 숫자, 하이픈만 쓰고 다른 주제와 겹치지 않아야 합니다")
    slug = slug or english_slug(root, topic, taken)
    cfg["topics"].append({"topic": topic, "slug": slug, "audience": audience, "scope": scope, "enabled": enabled})
    save_daemon_config(root, cfg)
    if not enabled:
        return f"주제 '{topic}' 등록 (output/{slug}, 데몬 대상 아님 — 데몬에 맡기려면 --add-topic)"
    return f"주제 '{topic}' 추가 (output/{slug}) — 데몬이 다음 사이클에서 제작을 시작합니다"


def remove_topic(root: Path, topic: str) -> str:
    cfg = load_daemon_config(root)
    for t in cfg["topics"]:
        if t["topic"] == topic:
            t["enabled"] = False
            save_daemon_config(root, cfg)
            return f"주제 '{topic}' 비활성화(결과물은 그대로 둠)"
    return f"주제 '{topic}' 없음"


def topic_settings(agent_dir: Path, entry: dict, overrides: dict) -> Settings:
    settings = Settings(topic=entry["topic"], out_dir=agent_dir / "output" / entry["slug"])
    if entry.get("audience"):
        settings.audience = entry["audience"]
    settings.scope = entry.get("scope", "")
    for key, value in overrides.items():
        setattr(settings, key, value)
    return settings


def topic_progress(settings: Settings) -> dict:
    """state.json 만 읽어 진행 상황을 요약한다(LLM 호출 없음)."""
    path = settings.state_path
    if not path.exists():
        return {"complete": False, "stage": "시작 전", "chapters": 0, "done": 0}
    data = json.loads(path.read_text(encoding="utf-8"))
    plan = data.get("plan")
    if not plan:
        return {"complete": False, "stage": "리서치" if not data.get("research") else "기획", "chapters": 0, "done": 0}
    chapters = plan["chapters"]
    done = sum(1 for c in chapters if data["chapters"].get(c["id"], {}).get("slide_status") == "rendered")
    complete = done == len(chapters) and bool(data.get("course_reviews"))
    return {"complete": complete, "stage": "완성" if complete else "제작", "chapters": len(chapters), "done": done}


def pick_topic(agent_dir: Path, cfg: dict, cycles: list[dict], overrides: dict) -> dict | None:
    """미완성 주제를 목록 순서대로 먼저, 모두 완성이면 가장 오래 손대지 않은 주제를 고른다."""
    active = [t for t in cfg["topics"] if t["enabled"]]
    if not active:
        return None
    for entry in active:
        if not topic_progress(topic_settings(agent_dir, entry, overrides))["complete"]:
            return entry
    last = {c["topic"]: c["start"] for c in cycles}
    return min(active, key=lambda t: last.get(t["topic"], ""))


# ================================================================ 사용량, 기록

class Usage:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}

    @property
    def today(self) -> dict:
        return self.data.setdefault(date.today().isoformat(), {"calls": 0, "cost_usd": 0.0, "cycles": 0})

    def add(self, calls: int, cost: float) -> None:
        t = self.today
        t["calls"] += calls
        t["cost_usd"] = round(t["cost_usd"] + cost, 4)
        t["cycles"] += 1
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")


def read_cycles(root: Path) -> list[dict]:
    path = root / "cycles.jsonl"
    if not path.exists():
        return []
    return [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


async def _sleep_unless_stopped(seconds: float, stop_file: Path) -> None:
    end = datetime.now() + timedelta(seconds=seconds)
    while datetime.now() < end and not stop_file.exists():
        await anyio.sleep(min(10, (end - datetime.now()).total_seconds() + 0.1))


# ================================================================ 데몬 루프

async def run_cycle(agent_dir: Path, harness: Harness, entry: dict, overrides: dict,
                    notifier: Notifier | None = None) -> dict:
    """주제 하나에 대해 사이클 한 번(제작 이어하기 또는 리프레시 + 자기 개선)."""
    settings = topic_settings(agent_dir, entry, overrides)
    agent = CoursewareAgent(settings, harness, notifier)
    calls0, cost0 = ledger.calls, ledger.cost_usd
    cycle = {"start": datetime.now().isoformat(timespec="seconds"), "topic": entry["topic"],
             "harness_before": harness.version, "failed": False}
    try:
        if not agent.is_complete():
            cycle["action"] = "교재 제작(이어하기)"
            await agent.run()
            cycle["result"] = "교재 완성" if agent.is_complete() else "진행됨"
        else:
            r = await agent.refresh_cycle()
            cycle.update(action=r["action"], result=r["result"])
            rec = await agent.improve("데몬 사이클")
            if rec and rec.get("accepted"):
                cycle["result"] += f"; 하네스 시험 v{harness.version} 생성"
    except Exception as err:   # 데몬은 죽지 않고 기록한 뒤 다음 사이클로
        log.exception("사이클 오류 (%s)", entry["topic"])
        cycle.update(result=f"오류: {str(err)[:200]}", failed=True)
        cycle.setdefault("action", "-")
    cycle.update(end=datetime.now().isoformat(timespec="seconds"), harness_after=harness.version,
                 calls=ledger.calls - calls0, cost_usd=round(ledger.cost_usd - cost0, 4))
    return cycle


async def daemon_loop(agent_dir: Path, harness_root: Path, overrides: dict) -> None:
    harness = Harness(harness_root)
    usage = Usage(harness_root / "usage.json")
    stop_file = harness_root / "STOP"
    failures = 0
    cfg = load_daemon_config(harness_root)
    notifier = Notifier(harness_root, cfg["notify"],
                        status_fn=lambda: _status_lines(harness, agent_dir, load_daemon_config(harness_root), usage, overrides))
    notifier.event("", "데몬", f"RSI 데몬 시작(PC {socket.gethostname()}, 하네스 v{harness.version})")
    await anyio.to_thread.run_sync(notifier.flush, True)
    log.info("RSI 데몬 시작: pid=%s, 주제=%s, 하네스 v%d", os.getpid(),
             [t["topic"] for t in cfg["topics"] if t["enabled"]], harness.version)

    while not stop_file.exists():
        cfg = load_daemon_config(harness_root)        # 실행 중 추가한 주제와 메일 설정도 반영
        notifier.cfg.update(cfg["notify"])
        today = usage.today
        if today["cost_usd"] >= cfg["daily_budget_usd"] or today["cycles"] >= cfg["max_cycles_per_day"]:
            log.info("오늘 예산 또는 사이클 상한 도달(비용 $%.2f, 사이클 %d) — 1시간 뒤 다시 확인",
                     today["cost_usd"], today["cycles"])
            _report(harness, harness_root, agent_dir, cfg, usage, overrides, "예산 대기 중")
            await _sleep_unless_stopped(3600, stop_file)
            continue

        entry = pick_topic(agent_dir, cfg, read_cycles(harness_root), overrides)
        if entry is None:
            log.info("활성 주제가 없음 — harness/daemon.json 에 주제를 추가하세요")
            _report(harness, harness_root, agent_dir, cfg, usage, overrides, "주제 없음")
            await _sleep_unless_stopped(cfg["interval_minutes"] * 60, stop_file)
            continue

        log.info("사이클 시작: 주제 '%s'", entry["topic"])
        cycle = await run_cycle(agent_dir, harness, entry, overrides, notifier)
        usage.add(cycle["calls"], cycle["cost_usd"])
        with (harness_root / "cycles.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(cycle, ensure_ascii=False) + "\n")
        log.info("사이클 끝: %s | %s | %s | 호출 %d회 $%.2f | 하네스 v%d→v%d", entry["topic"], cycle.get("action"),
                 cycle.get("result"), cycle["calls"], cycle["cost_usd"], cycle["harness_before"], cycle["harness_after"])

        notifier.event(entry["topic"], "오류" if cycle["failed"] else "사이클",
                       f"{cycle.get('action')} → {cycle.get('result')} (LLM 호출 {cycle['calls']}회, "
                       f"하네스 v{cycle['harness_before']}→v{cycle['harness_after']})", urgent=cycle["failed"])
        await anyio.to_thread.run_sync(notifier.flush, True)
        failures = failures + 1 if cycle["failed"] else 0
        wait = cfg["interval_minutes"] * 60 * (2 ** min(failures, 4))
        next_at = datetime.now() + timedelta(seconds=wait)
        _report(harness, harness_root, agent_dir, cfg, usage, overrides, f"다음 사이클 {next_at:%m-%d %H:%M}"
                + (f" (연속 실패 {failures}회로 대기 늘림)" if failures else ""))
        await _sleep_unless_stopped(wait, stop_file)

    log.info("STOP 파일 확인 — 데몬 종료")
    stop_file.unlink(missing_ok=True)
    notifier.event("", "데몬", "RSI 데몬 정지(STOP 파일)")
    await anyio.to_thread.run_sync(notifier.flush, True)
    _report(harness, harness_root, agent_dir, load_daemon_config(harness_root), usage, overrides, "정지됨")


def _topics_table(agent_dir: Path, cfg: dict, overrides: dict) -> list[str]:
    lines = ["| 주제 | 상태 | 진행 | 결과물 |", "|---|---|---|---|"]
    for t in cfg["topics"]:
        settings = topic_settings(agent_dir, t, overrides)
        prog = topic_progress(settings)
        rel = os.path.relpath(settings.out_dir, agent_dir / "harness").replace("\\", "/")
        state = prog["stage"] if t["enabled"] else "비활성"
        lines.append(f"| {t['topic']} | {state} | {prog['done']}/{prog['chapters']}장 | [{rel}]({rel}/README.md) |")
    return lines


def _status_lines(harness: Harness, agent_dir: Path, cfg: dict, usage: Usage, overrides: dict) -> list[str]:
    """메일 끝에 붙는 현재 상태."""
    t = usage.today
    lines = [f"- 하네스 v{harness.version} ({'시험 중' if harness.status == 'trial' else '안정'}), "
             f"학습한 규칙 {sum(len(v) for v in harness.data['prompt_rules'].values())}개, "
             f"lint 규칙 {len(harness.data['lint_rules'])}개",
             f"- 오늘 사용: 사이클 {t['cycles']}회, LLM 호출 {t['calls']}회"]
    for entry in cfg["topics"]:
        if entry["enabled"]:
            prog = topic_progress(topic_settings(agent_dir, entry, overrides))
            lines.append(f"- {entry['topic']}: {prog['stage']} {prog['done']}/{prog['chapters']}장 (output/{entry['slug']})")
    return lines


def _report(harness: Harness, root: Path, agent_dir: Path, cfg: dict, usage: Usage, overrides: dict, status: str) -> None:
    t = usage.today
    pid_file = root / "daemon.pid"
    extra = "\n".join([
        "## 데몬 상태", "",
        f"- 상태: {status}",
        f"- PID: {pid_file.read_text(encoding='utf-8') if pid_file.exists() else '-'} · PC: {socket.gethostname()}",
        f"- 간격 {cfg['interval_minutes']}분 · 오늘 사용: 사이클 {t['cycles']}/{cfg['max_cycles_per_day']}, "
        f"호출 {t['calls']}회, 보고 비용 ${t['cost_usd']:.2f}/${cfg['daily_budget_usd']}",
        "- 주제 추가: `python run.py --add-topic \"주제\" --audience \"대상\"` · 멈추기: `stop_daemon.ps1` 또는 `harness/STOP` 파일",
        "", "## 주제", "", *_topics_table(agent_dir, cfg, overrides),
    ])
    harness.write_report(cycles=read_cycles(root), extra=extra)


def status_text(agent_dir: Path, harness_root: Path) -> str:
    pid_file = harness_root / "daemon.pid"
    running = "실행 중 (pid " + pid_file.read_text(encoding="utf-8") + ")" if pid_file.exists() else "멈춤"
    cfg = load_daemon_config(harness_root)
    lines = [f"RSI 데몬: {running}", "", *_topics_table(agent_dir, cfg, {}), ""]
    report = harness_root / "RSI_REPORT.md"
    if report.exists():
        lines.append(report.read_text(encoding="utf-8"))
    return "\n".join(lines)


def run_daemon(agent_dir: Path, harness_root: Path, overrides: dict) -> None:
    ensure_this_machine(harness_root)
    with SingleInstance(harness_root / "daemon.lock"):
        anyio.run(daemon_loop, agent_dir, harness_root, overrides)
    sys.exit(0)
