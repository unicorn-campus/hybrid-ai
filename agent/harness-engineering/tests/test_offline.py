"""LLM 없이 돌아가는 부분 테스트: 슬라이드 빌더(pptx-guide 준수), 하네스 자기 개선, 데몬 주제 대기열."""
import json
import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from courseware_agent import daemon
from courseware_agent.harness import Harness
from courseware_agent.lint import lint_chapter
from courseware_agent.orchestrator import _clean_md, _digest
from courseware_agent.pptx_builder import build_deck, check_paste, generate_js, lint_spec, spec_to_markdown

HERE = Path(__file__).resolve().parent
SPEC = json.loads((HERE / "sample_spec.json").read_text(encoding="utf-8"))

CHAPTER = """# 1장. 하네스란 무엇인가

## 학습 목표
- 설명할 수 있다

## 본문
내용 https://example.com/a 입니다.

## 실습
단계

## 핵심 정리
- 요점 하나

## 확인 문제
<details><summary>정답</summary>답</details>

## 참고 자료
- https://example.com/a
- https://made-up.example.org/x
"""


# ---------------------------------------------------------------- 교재 lint

def test_lint_chapter_flags_unknown_url_and_length():
    errors = lint_chapter(CHAPTER, ["https://www.example.com/a/"], min_chars=10)
    assert errors == ["리서치 출처에 없는 URL: https://made-up.example.org/x"]
    errors = lint_chapter(CHAPTER.replace("## 실습", "## 연습"), [], min_chars=99999)
    assert any("'## 실습'" in e for e in errors)
    assert any("분량 부족" in e for e in errors)


def test_clean_md_and_digest():
    assert _clean_md("```markdown\n# 제목\n본문\n```") == "# 제목\n본문\n"
    digest = _digest({"id": "ch01", "title": "t"}, CHAPTER)
    assert "## 핵심 정리" in digest and "요점 하나" in digest


# ---------------------------------------------------------------- 슬라이드 명세와 빌더

def test_lint_spec_clean_sample():
    assert lint_spec(SPEC, 8) == []


def test_lint_spec_catches_guide_violations():
    bad = json.loads(json.dumps(SPEC))
    bad["slides"][0]["pattern"] = "cards"
    bad["slides"][1]["lead"] = "노드 타입·관계"
    bad["slides"][2]["notes"] = ""
    errors = lint_spec(bad, 8)
    assert any("첫 슬라이드는 학습 목표" in e for e in errors)
    assert any("가운뎃점" in e for e in errors)
    assert any("발표자 노트" in e for e in errors)


def test_generate_js_follows_guide():
    js, errors, built = generate_js(SPEC, "1장. 테스트", "out.pptx")
    assert errors == []
    assert 'const LAYOUT = "내용_단쪽"' in js
    assert "pptx.defineLayout({ name: \"CUSTOM\", width: 16, height: 9 })" in js
    assert js.count("pptx.addSlide({ masterName: LAYOUT })") == len(SPEC["slides"])
    assert "async function createSlide01(pptx)" in js and "main().catch(" in js
    assert "schemeClr" not in js and "SchemeColor" not in js and "Calibri" not in js
    # 숫자 fontSize 직접 지정은 레이아웃 실측값(12/16/32pt)과 출처 예외뿐
    import re
    bare = re.findall(r"fontSize: (\d+)", js)
    assert set(bare) <= {"12", "16", "32"}


def test_overflow_is_reported_not_shrunk():
    spec = {"slides": [{"pattern": "objectives", "title": "학습 목표", "lead": "", "message": "", "source": "",
                        "notes": "노트", "items": [{"heading": "아주 긴 목표 " * 40, "text": "설명 " * 80}] * 6}]}
    _, errors, _ = generate_js(spec, "t", "o.pptx")
    assert any("들어가지 않음" in e for e in errors)


@pytest.mark.skipif(shutil.which("node") is None, reason="node 필요")
def test_build_deck_passes_paste_check(tmp_path):
    result = build_deck(SPEC, "1장. 테스트", tmp_path / "deck.pptx", preview_dir=None)
    assert result.pptx.stat().st_size > 0
    assert result.paste_errors == [] and check_paste(result.pptx) == []
    from pptx import Presentation
    prs = Presentation(str(result.pptx))
    assert len(prs.slides) == len(SPEC["slides"])
    assert prs.slides[0].shapes.title.text == "학습 목표"
    assert prs.slides[0].notes_slide.notes_text_frame.text.startswith("학습 목표를")


def test_spec_markdown_marks_section_divider():
    md = spec_to_markdown(SPEC, "1장. 테스트")
    assert "<!-- 간지: 1장. 테스트 -->" in md and "## 1. 학습 목표" in md


# ---------------------------------------------------------------- 하네스 자기 개선(RSI)

def _metric(h, version, score, revisions=1, lint=0, kind="text"):
    h.record(topic="t", chapter="ch01", kind=kind, version=version, first_score=score, final_score=score,
             revisions=revisions, first_lint=lint, passed=True, forced=False)


def test_harness_propose_validates_and_creates_trial(tmp_path):
    h = Harness(tmp_path / "h")
    corpus = {"text": ["가 나 다", "라 마 바", "사 아 자"], "slides": []}
    rec = h.propose("반복 지적", [
        {"action": "add_prompt_rule", "role": "writer", "text": "실습 절마다 기대 결과를 표로 제시한다."},
        {"action": "add_lint_rule", "lint": {"target": "text", "mode": "forbid", "pattern": "[", "message": "x"}},
        {"action": "add_lint_rule", "lint": {"target": "text", "mode": "forbid", "pattern": " ", "message": "공백"}},
        {"action": "set_config", "config_key": "pass_score", "config_value": 5.0},
        {"action": "set_config", "config_key": "max_revisions", "config_value": 2},
    ], corpus)
    assert [p["action"] for p in rec["accepted"]] == ["add_prompt_rule", "set_config"]
    reasons = " ".join(r["reason"] for r in rec["rejected"])
    assert "정규식 오류" in reasons and "과잉 탐지" in reasons and "허용 범위" in reasons
    assert h.version == 2 and h.status == "trial"
    assert "실습 절마다" in h.system("writer", "BASE") and h.system("reviewer", "BASE") == "BASE"
    assert (tmp_path / "h" / "versions" / "v002.json").exists()
    assert "시험 버전 생성" in (tmp_path / "h" / "CHANGELOG.md").read_text(encoding="utf-8")


def test_harness_trial_rollback_and_adopt(tmp_path):
    h = Harness(tmp_path / "h")
    for _ in range(3):
        _metric(h, 1, 8.5)
    h.propose("d", [{"action": "add_prompt_rule", "role": "slides", "text": "슬라이드 제목은 질문형으로 쓴다."}], {})
    assert h.evaluate_trial() is None            # 표본 부족
    for _ in range(3):
        _metric(h, 2, 6.0, revisions=3)
    verdict = h.evaluate_trial()
    assert verdict["verdict"] == "rolled_back" and h.version == 1 and h.status == "stable"
    assert h.system("slides", "B") == "B"

    h.propose("d2", [{"action": "add_prompt_rule", "role": "slides", "text": "각 슬라이드 노트에 질문 하나를 넣는다."}], {})
    assert h.version == 3                        # 롤백된 v2 번호는 다시 쓰지 않는다
    for _ in range(3):
        _metric(h, 3, 9.0, revisions=0)
    assert h.evaluate_trial()["verdict"] == "adopted" and h.status == "stable"
    assert "질문 하나" in h.system("slides", "B")
    track = h.track_record()
    assert "rolled_back" in track and "adopted" in track
    report = h.write_report(cycles=[{"start": "s", "end": "e", "topic": "t", "action": "a", "result": "r"}])
    assert "버전별 품질" in report.read_text(encoding="utf-8")


def test_harness_extra_lint_skips_code(tmp_path):
    h = Harness(tmp_path / "h")
    h.propose("d", [{"action": "add_lint_rule",
                     "lint": {"target": "text", "mode": "forbid", "pattern": "TODO", "message": "TODO 남김"}}], {})
    assert h.extra_lint("text", "본문 TODO") and not h.extra_lint("text", "```\nTODO\n```")
    assert h.extra_lint("slides", "TODO") == []


# ---------------------------------------------------------------- 데몬

def test_daemon_machine_binding(tmp_path):
    daemon.ensure_this_machine(tmp_path)
    data = json.loads((tmp_path / "machine.json").read_text(encoding="utf-8"))
    data["hostname"] = "other-pc"
    (tmp_path / "machine.json").write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(SystemExit):
        daemon.ensure_this_machine(tmp_path)


def test_daemon_single_instance(tmp_path):
    with daemon.SingleInstance(tmp_path / "daemon.lock"):
        assert (tmp_path / "daemon.pid").exists()
        with pytest.raises(SystemExit):
            with daemon.SingleInstance(tmp_path / "daemon.lock"):
                pass
    assert not (tmp_path / "daemon.pid").exists()


def test_daemon_topic_queue_and_pick(tmp_path):
    root, agent_dir = tmp_path / "harness", tmp_path
    root.mkdir()
    cfg = daemon.load_daemon_config(root)
    assert cfg["topics"][0]["topic"] == "파이썬 AI 프로그램 하네스 엔지니어링"
    assert "output/kubernetes-operations" in daemon.add_topic(root, "쿠버네티스 운영", "운영 담당자", "kubernetes-operations")
    with pytest.raises(SystemExit):
        daemon.add_topic(root, "다른 주제", slug="Bad Slug")
    cfg = daemon.load_daemon_config(root)
    assert [t["topic"] for t in cfg["topics"]] == ["파이썬 AI 프로그램 하네스 엔지니어링", "쿠버네티스 운영"]
    # 둘 다 미완성이면 목록 순서대로
    assert daemon.pick_topic(agent_dir, cfg, [], {})["topic"] == "파이썬 AI 프로그램 하네스 엔지니어링"
    # 첫 주제가 완성이면 다음 미완성 주제
    out = agent_dir / "output" / "python-ai-harness-engineering"
    out.mkdir(parents=True)
    (out / "state.json").write_text(json.dumps({
        "plan": {"chapters": [{"id": "ch01"}]}, "chapters": {"ch01": {"slide_status": "rendered"}},
        "course_reviews": [{}], "research": {}}), encoding="utf-8")
    assert daemon.pick_topic(agent_dir, cfg, [], {})["topic"] == "쿠버네티스 운영"
    daemon.remove_topic(root, "쿠버네티스 운영")
    cfg = daemon.load_daemon_config(root)
    # 모두 완성(또는 비활성)이면 가장 오래 손대지 않은 활성 주제
    assert daemon.pick_topic(agent_dir, cfg, [{"topic": "파이썬 AI 프로그램 하네스 엔지니어링", "start": "2026-11-01"}], {})["topic"] == "파이썬 AI 프로그램 하네스 엔지니어링"
    settings = daemon.topic_settings(agent_dir, cfg["topics"][1], {})
    assert settings.audience == "운영 담당자"
    assert settings.out_dir == agent_dir / "output" / "kubernetes-operations"


def test_slugify_is_ascii():
    from courseware_agent.config import SLUG_RE, slugify
    for text in ["파이썬 AI 프로그램 하네스 엔지니어링", "Kubernetes 운영 101", "!!!"]:
        assert SLUG_RE.match(slugify(text)), slugify(text)
    assert slugify("Kubernetes 운영 101") == "kubernetes-unyeong-101"


# ---------------------------------------------------------------- 작업 변경 요약 메일

def test_notifier_batches_and_retries(tmp_path, monkeypatch):
    from courseware_agent.notify import Notifier
    sent = []
    n = Notifier(tmp_path, {"min_interval_minutes": 10}, status_fn=lambda: ["- 하네스 v1"])
    monkeypatch.setattr(n, "_send", lambda subject, text, body_html: sent.append((subject, text)) or ["a@b.c"])

    n.event("주제A", "장 완성", "ch01 완성")
    assert n.flush() and len(sent) == 1           # 첫 이벤트는 바로 보냄
    n.event("주제A", "장 완성", "ch02 완성")
    assert not n.flush()                          # 10분 안의 이벤트는 모아 둠
    n.event("주제A", "하네스 개선", "v2 시험")
    assert n.flush(force=True) and len(sent) == 2  # 사이클 끝(force)이면 묶어서 한 통
    assert "2건의 작업 변경" in sent[1][0] and "ch02 완성" in sent[1][1] and "v2 시험" in sent[1][1]
    assert "하네스 v1" in sent[1][1]

    n.event("주제A", "오류", "빌드 실패", urgent=True)
    monkeypatch.setattr(n, "_send", lambda *a: [])  # SMTP 실패
    assert not n.flush()
    assert len(n.pending) == 1                    # 실패한 이벤트는 다음에 다시 보냄
    assert len(list((tmp_path / "outbox").glob("*.md"))) == 3


def test_notifier_disabled(tmp_path):
    from courseware_agent.notify import Notifier
    n = Notifier(tmp_path, {"enabled": False})
    n.event("t", "k", "m")
    assert not n.pending and not n.flush(force=True)


def test_builder_layout_fixes():
    from courseware_agent.pptx_builder import _column_widths, _strip_numbering, _units, SlideWriter
    # 열 너비: 긴 낱말(파일명)이 들어갈 최소 너비 보장, 합계 유지
    rows = [["파일", "설명"], ["AGENTS.md(CLAUDE.md) 갱신", "아주 긴 설명 " * 12]]
    widths = _column_widths(rows, 9.0)
    assert abs(sum(widths) - 9.0) < 1e-6
    assert widths[0] >= _units("AGENTS.md(CLAUDE.md)") * 16 / 72 + 0.3 - 1e-6
    # 손으로 단 번호 제거
    s = _strip_numbering({"items": [{"heading": "1. 준비", "text": ""}, {"heading": "", "text": "② 실행"}],
                          "side_points": ["3) 확인"], "right": {"header": "h", "points": ["(4) 끝"]}})
    assert [i["heading"] for i in s["items"]] == ["준비", ""] and s["items"][1]["text"] == "실행"
    assert s["side_points"] == ["확인"] and s["right"]["points"] == ["끝"]
    # 카드 5개: 마지막 줄 2장이 전체 폭을 채움
    spec = {"pattern": "cards", "title": "t", "lead": "", "message": "", "source": "", "notes": "n",
            "items": [{"heading": f"카드{i}", "text": "- 내용"} for i in range(5)]}
    w = SlideWriter(1, spec)
    w.build()
    boxes = [st for st in w.stmts if st.startswith("box(")]
    import re
    xs = [(float(re.search(r"x: ([\d.]+)", b).group(1)), float(re.search(r"w: ([\d.]+)", b).group(1))) for b in boxes]
    last_two = xs[3:]
    assert abs(last_two[1][0] + last_two[1][1] - (0.557 + 14.9)) < 0.01


@pytest.mark.skipif(shutil.which("node") is None or sys.platform != "win32", reason="Windows 파일 잠금 동작")
def test_build_survives_open_deck(tmp_path):
    target = tmp_path / "deck.pptx"
    build_deck(SPEC, "t", target)
    with open(target, "rb"):                       # PowerPoint 처럼 덱을 열어 둔 상태
        result = build_deck(SPEC, "t", target)
    assert result.pptx.name == "deck.latest.pptx" and result.pptx.exists() and result.paste_errors == []
    result = build_deck(SPEC, "t", target)          # 닫은 뒤 빌드는 원래 이름으로, .latest 는 정리
    assert result.pptx == target and not (tmp_path / "deck.latest.pptx").exists()
