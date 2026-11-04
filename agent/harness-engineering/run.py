"""교재 제작 에이전트 실행기.

    python run.py "하네스엔지니어링"              # 한 번 끝까지 제작(중간부터 이어하기 가능)
    python run.py "하네스엔지니어링" --fresh      # 처음부터 다시
    python run.py "하네스엔지니어링" --render-only  # LLM 없이 슬라이드 빌드와 목차만 다시
    python run.py --daemon                         # 이 PC에서 백그라운드로 계속 도는 RSI 데몬
    python run.py --add-topic "주제" --audience "대상" [--slug english-name]  # 데몬 주제 추가(실행 중에도 반영)
    python run.py --remove-topic "주제"            # 데몬 주제 비활성화
    python run.py --status                         # 데몬 상태, 주제별 진행, RSI 보고서 보기
"""
from __future__ import annotations

import argparse
import json
import logging
import shutil
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from courseware_agent import CoursewareAgent, Settings
from courseware_agent.daemon import add_topic, load_daemon_config, remove_topic, run_daemon, status_text
from courseware_agent.harness import Harness
from courseware_agent.pptx_builder import build_deck, check_paste

HERE = Path(__file__).resolve().parent
HARNESS_DIR = HERE / "harness"


def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    ap = argparse.ArgumentParser(description="주제 기반 교재·슬라이드 자동 제작 에이전트 (RSI)")
    ap.add_argument("topic", nargs="?", help="교재 주제 (예: 하네스엔지니어링)")
    ap.add_argument("--out", type=Path, help="출력 폴더 (기본: ./output/<영문 슬러그>)")
    ap.add_argument("--slug", help="출력 디렉토리 영문 이름 (기본: Claude가 주제를 영문으로 지음)")
    ap.add_argument("--audience", help="대상 학습자")
    ap.add_argument("--scope", help="주제 범위(무엇을 다루고 무엇을 빼는지 한두 문장)")
    ap.add_argument("--model", help="Claude 모델 ID")
    ap.add_argument("--effort", choices=["low", "medium", "high", "xhigh", "max"])
    ap.add_argument("--concurrency", type=int)
    ap.add_argument("--min-chapters", type=int)
    ap.add_argument("--max-chapters", type=int)
    ap.add_argument("--pass-score", type=float)
    ap.add_argument("--max-revisions", type=int)
    ap.add_argument("--fresh", action="store_true", help="기존 진행 상태를 지우고 처음부터 시작")
    ap.add_argument("--render-only", action="store_true", help="LLM 호출 없이 슬라이드 빌드와 발행만 다시 수행")
    ap.add_argument("--text-only", action="store_true", help="본문만 만들고 슬라이드와 과정 검토는 건너뜀")
    ap.add_argument("--no-improve", action="store_true", help="자기 개선(RSI) 끄기")
    ap.add_argument("--daemon", action="store_true", help="이 PC에서 백그라운드로 계속 도는 RSI 데몬")
    ap.add_argument("--add-topic", metavar="주제", help="데몬 주제 대기열에 추가 (--audience 와 함께 쓸 수 있음)")
    ap.add_argument("--remove-topic", metavar="주제", help="데몬 주제 비활성화")
    ap.add_argument("--status", action="store_true", help="데몬 상태와 RSI 보고서 출력")
    args = ap.parse_args()

    HARNESS_DIR.mkdir(exist_ok=True)
    if args.status:
        print(status_text(HERE, HARNESS_DIR))
        return
    if args.add_topic:
        print(add_topic(HARNESS_DIR, args.add_topic.strip(), args.audience or "", args.slug or "",
                        scope=args.scope or ""))
        return
    if args.remove_topic:
        print(remove_topic(HARNESS_DIR, args.remove_topic.strip()))
        return

    overrides = {name: getattr(args, name) for name in
                 ("audience", "model", "effort", "concurrency", "min_chapters", "max_chapters", "pass_score", "max_revisions")
                 if getattr(args, name) is not None}
    if args.no_improve:
        overrides["self_improve"] = False

    if args.daemon:
        _setup_logging([HARNESS_DIR / "logs" / "rsi.log"])
        if args.topic:
            print(add_topic(HARNESS_DIR, args.topic, args.audience or "", args.slug or "", scope=args.scope or ""))
        run_daemon(HERE, HARNESS_DIR, {k: v for k, v in overrides.items() if k != "audience"})
        return

    if not args.topic:
        ap.error("주제를 주거나 --daemon / --status 를 쓰세요")
    # 주제 → 영문 디렉토리 이름은 harness/daemon.json 한 곳에서 관리한다(수동 실행 주제는 비활성으로 등록)
    queued = {t["topic"]: t for t in load_daemon_config(HARNESS_DIR)["topics"]}
    if args.topic not in queued:
        print(add_topic(HARNESS_DIR, args.topic, args.audience or "", args.slug or "", enabled=False,
                        scope=args.scope or ""))
        queued = {t["topic"]: t for t in load_daemon_config(HARNESS_DIR)["topics"]}
    entry = queued[args.topic]
    out = (args.out or HERE / "output" / entry["slug"]).resolve()
    if args.fresh and out.exists():
        shutil.rmtree(out)

    settings = Settings(topic=args.topic, out_dir=out)
    if entry["audience"]:
        settings.audience = entry["audience"]   # 데몬과 같은 대상 학습자와 범위로 이어서 만든다
    settings.scope = args.scope or entry.get("scope", "")
    settings.ensure_dirs()
    settings.text_only = args.text_only
    _setup_logging([settings.logs_dir / "agent.log", HARNESS_DIR / "logs" / "rsi.log"])
    agent = CoursewareAgent(settings, Harness(HARNESS_DIR))
    for key, value in overrides.items():   # 명령줄 값이 하네스 설정보다 우선
        setattr(settings, key, value)

    if args.render_only:
        _render_only(agent)
        return
    import anyio
    anyio.run(agent.run)


def _render_only(agent: CoursewareAgent) -> None:
    log = logging.getLogger("courseware")
    for ch in agent.state.data["plan"]["chapters"]:
        paths = agent._paths(ch)
        if not paths["spec"].exists():
            continue
        spec = json.loads(paths["spec"].read_text(encoding="utf-8"))
        agent._write_spec(ch, paths, spec)
        result = build_deck(spec, agent._deck_title(ch), paths["pptx"], paths["preview"])
        agent.state.chapter(ch["id"])["slide_count"] = len(spec["slides"])
        log.info("%s 빌드: 레이아웃 오류 %d, 붙여넣기 %s, 미리보기 %d장", ch["id"], len(result.layout_errors),
                 check_paste(paths["pptx"]) or "OK", len(result.previews))
    agent.publish()


def _setup_logging(paths: list[Path]) -> None:
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%Y-%m-%d %H:%M:%S")
    root = logging.getLogger("courseware")
    root.setLevel(logging.INFO)
    handlers: list[logging.Handler] = []
    if sys.stdout is not None:
        handlers.append(logging.StreamHandler(sys.stdout))
    for path in paths:
        path.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(RotatingFileHandler(path, maxBytes=5_000_000, backupCount=5, encoding="utf-8"))
    for handler in handlers:
        handler.setFormatter(fmt)
        root.addHandler(handler)


if __name__ == "__main__":
    main()
