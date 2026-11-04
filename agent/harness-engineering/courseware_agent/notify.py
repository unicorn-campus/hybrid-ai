"""작업 변경 요약 메일.

백그라운드 데몬에서 작업이 생길 때마다(장 완성, 하네스 버전 변화, 리프레시, 사이클 종료, 오류) 이벤트를 모으고,
저장소의 email_sender.py(.env 의 SMTP_SERVER, SMTP_PORT, SMTP_USER, SMTP_PASSWORD 사용)로 RECIPIENTS 에게 보낸다.
- 짧은 시간에 이벤트가 몰리면 min_interval_minutes 간격으로 묶어서 한 통으로 보낸다(사이클 종료와 오류는 즉시)
- 보낸 메일은 harness/outbox/ 에 마크다운으로도 남긴다
- 발송에 실패하면 이벤트를 버리지 않고 다음 발송 때 다시 보낸다
"""
from __future__ import annotations

import html
import json
import logging
import sys
import threading
from datetime import datetime, timedelta
from pathlib import Path

log = logging.getLogger("courseware")

REPO_ROOT = Path(__file__).resolve().parents[3]   # newsletter/ (email_sender.py, .env)
DEFAULT_NOTIFY = {"enabled": True, "min_interval_minutes": 10, "sender_name": "교재 제작 에이전트",
                  "subject_prefix": "[교재 RSI]"}
MAX_PENDING = 200


class Notifier:
    def __init__(self, harness_root: Path, cfg: dict | None = None, status_fn=None) -> None:
        self.root = harness_root
        self.cfg = {**DEFAULT_NOTIFY, **(cfg or {})}
        self.status_fn = status_fn          # 메일 끝에 붙일 현재 상태(마크다운 줄 목록)를 돌려주는 함수
        self.pending: list[dict] = []
        self.last_sent: datetime | None = None
        self.lock = threading.Lock()
        (harness_root / "outbox").mkdir(parents=True, exist_ok=True)

    @property
    def enabled(self) -> bool:
        return bool(self.cfg.get("enabled"))

    def event(self, topic: str, kind: str, message: str, urgent: bool = False) -> None:
        if not self.enabled:
            return
        with self.lock:
            self.pending.append({"at": datetime.now().strftime("%m-%d %H:%M"), "topic": topic, "kind": kind,
                                 "message": message, "urgent": urgent})
            del self.pending[:-MAX_PENDING]

    def due(self) -> bool:
        if not self.pending:
            return False
        if any(e["urgent"] for e in self.pending) or self.last_sent is None:
            return True
        return datetime.now() - self.last_sent >= timedelta(minutes=self.cfg["min_interval_minutes"])

    def flush(self, force: bool = False) -> bool:
        """보낼 때가 됐으면(또는 force) 모인 이벤트를 메일 한 통으로 보낸다. 보냈으면 True."""
        if not self.enabled:
            return False
        with self.lock:
            if not self.pending or not (force or self.due()):
                return False
            events = list(self.pending)
        subject, text, body_html = self.compose(events)
        sent_to = self._send(subject, text, body_html)
        self._archive(subject, text, sent_to)
        if sent_to:
            with self.lock:
                self.pending = [e for e in self.pending if e not in events]
                self.last_sent = datetime.now()
            log.info("메일 발송: %d명, 이벤트 %d건 — %s", len(sent_to), len(events), subject)
            return True
        log.warning("메일 발송 실패 — 이벤트 %d건을 다음 발송 때 다시 보냄", len(events))
        return False

    # ------------------------------------------------------------ 본문

    def compose(self, events: list[dict]) -> tuple[str, str, str]:
        topics = sorted({e["topic"] for e in events if e["topic"]})
        headline = events[-1]["message"] if len(events) == 1 else f"{len(events)}건의 작업 변경"
        subject = f"{self.cfg['subject_prefix']} {', '.join(topics) or '데몬'} — {headline}"[:180]
        status = self.status_fn() if self.status_fn else []

        lines = [f"교재 제작 에이전트 작업 변경 요약 ({datetime.now():%Y-%m-%d %H:%M})", "", "■ 변경 내역"]
        lines += [f"- {e['at']} [{e['kind']}] {e['topic'] + ': ' if e['topic'] else ''}{e['message']}" for e in events]
        if status:
            lines += ["", "■ 현재 상태"] + status
        lines += ["", f"자세한 기록: {self.root / 'RSI_REPORT.md'}", f"실행 로그: {self.root / 'logs' / 'rsi.log'}"]
        text = "\n".join(lines)

        rows = "".join(
            f"<tr><td style='padding:4px 8px;color:#7C8598;white-space:nowrap'>{html.escape(e['at'])}</td>"
            f"<td style='padding:4px 8px'><span style='background:{'#FDECEC' if e['urgent'] else '#EEF3FA'};"
            f"color:#1E2A5C;border-radius:10px;padding:1px 8px;font-size:12px'>{html.escape(e['kind'])}</span></td>"
            f"<td style='padding:4px 8px'>{html.escape(e['topic'])}</td>"
            f"<td style='padding:4px 8px'>{html.escape(e['message'])}</td></tr>" for e in events)
        status_html = "".join(f"<li>{html.escape(s.lstrip('- '))}</li>" for s in status)
        body_html = f"""<div style="font-family:Pretendard,'Malgun Gothic',sans-serif;color:#2B3242;max-width:820px">
<h2 style="color:#1E2A5C;margin:0 0 4px">작업 변경 요약</h2>
<div style="color:#7C8598;font-size:13px;margin-bottom:12px">{datetime.now():%Y-%m-%d %H:%M} · 교재 제작 에이전트(RSI 데몬)</div>
<table style="border-collapse:collapse;font-size:14px;width:100%">{rows}</table>
{f'<h3 style="color:#1E2A5C">현재 상태</h3><ul style="font-size:14px">{status_html}</ul>' if status_html else ''}
<div style="color:#7C8598;font-size:12px;margin-top:16px">자세한 기록: {html.escape(str(self.root / 'RSI_REPORT.md'))}</div>
</div>"""
        return subject, text, body_html

    # ------------------------------------------------------------ 발송, 보관

    def _send(self, subject: str, text: str, body_html: str) -> list[str]:
        try:
            if str(REPO_ROOT) not in sys.path:
                sys.path.insert(0, str(REPO_ROOT))
            import email_sender   # .env 를 읽어 SMTP 설정과 수신자를 준비한다
        except Exception as err:
            log.warning("email_sender 를 불러오지 못함: %s", err)
            return []
        recipients = email_sender.get_recipients()
        if not recipients:
            log.warning(".env 의 RECIPIENTS 가 비어 있어 메일을 보내지 않음")
            return []
        sent = []
        for to in recipients:
            if email_sender.send_email(to, subject, text, body_html, sender_name=self.cfg["sender_name"]):
                sent.append(to)
        return sent

    def _archive(self, subject: str, text: str, sent_to: list[str]) -> None:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        result = f"발송: {len(sent_to)}명" if sent_to else "발송 실패(다음에 다시 보냄)"
        (self.root / "outbox" / f"{stamp}.md").write_text(
            f"# {subject}\n\n- {result}\n\n```\n{text}\n```\n", encoding="utf-8")


def load_notify_config(harness_root: Path) -> dict:
    path = harness_root / "daemon.json"
    cfg = json.loads(path.read_text(encoding="utf-8")).get("notify", {}) if path.exists() else {}
    return {**DEFAULT_NOTIFY, **cfg}
