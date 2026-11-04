"""슬라이드 명세(JSON) → pptxgenjs 빌드 스크립트 → .pptx.

references/pptx-guide.md 를 따른다.
- 16″×9″, 콘텐츠 레이아웃 이름 `내용_단쪽`, 제목은 제목 개체 틀, 쪽 번호는 레이아웃 slideNumber
- 팔레트 상수 C.*, 글꼴 Pretendard 직접 지정, fontSize 는 fsMin()(최소 14pt) 경유
- 슬라이드 함수는 async function createSlideXX(pptx), main().catch(...)
- 빌드 뒤 개체 틀 번호 정리(6-14) → 붙여넣기 호환 점검(6-13) → LibreOffice 미리보기

LLM은 명세만 쓰고, 좌표 계산과 코드 생성은 여기서 결정적으로 한다.
분량이 넘치면 글자를 14pt 밑으로 줄이지 않고 오류로 돌려보내 명세를 고치게 한다.
"""
from __future__ import annotations

import json
import math
import re
import shutil
import subprocess
import sys
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

AGENT_DIR = Path(__file__).resolve().parents[1]
RENDER_SCRIPT = AGENT_DIR.parents[1] / "scripts" / "render-pptx.py"

X0, CW = 0.557, 14.9
BODY_BOTTOM = 7.95
GAP = 0.2
MIN_FONT = 14
PATTERNS = ("objectives", "agenda", "cards", "two_column", "steps", "table", "code", "why_how_what", "summary")
MIDDLE_DOT = "·"


@dataclass
class BuiltSlide:
    no: int
    func: str
    errors: list[str] = field(default_factory=list)
    bottom: float = 0.0


# ================================================================ 글자 크기 추정

def _units(text: str) -> float:
    """글자 폭(em 단위) 추정: 한글·전각 1.0, 공백 0.3, 그 밖 0.55."""
    total = 0.0
    for ch in text:
        if ord(ch) >= 0x2E80:
            total += 1.0
        elif ch == " ":
            total += 0.3
        else:
            total += 0.58
    return total


def _lines(text: str, fs: float, width_in: float) -> int:
    per_line = max(1.0, (width_in * 72) / fs)
    return sum(max(1, math.ceil(_units(seg) / per_line)) for seg in text.split("\n"))


def _height(text: str, fs: float, width_in: float, spacing: float = 1.3) -> float:
    return _lines(text, fs, width_in) * fs * spacing / 72


def _plain(text: str) -> str:
    return re.sub(r"\*\*(.+?)\*\*", r"\1", text)


def _column_widths(rows: list[list], total: float, fs: float = 16) -> list[float]:
    """표 열 너비. 글이 많은 열에 더 주되, 각 열은 가장 긴 낱말(파일명, 식별자)이 끊기지 않을 만큼은 보장한다."""
    columns = list(zip(*rows))
    weights = [max(2.0, max(_units(_plain(str(c))) for c in col)) ** 0.8 for col in columns]
    floors = [max(_units(tok) for c in col for tok in (_plain(str(c)).split() or [""])) * fs / 72 + 0.3
              for col in columns]
    if sum(floors) >= total:   # 다 지킬 수 없으면 낱말 길이 비율로 나눈다
        return [total * f / sum(floors) for f in floors]
    fixed: dict[int, float] = {}   # 최소 너비로 고정한 열(한 번 고정하면 유지)
    while True:
        free = [i for i in range(len(columns)) if i not in fixed]
        rest = total - sum(fixed.values())
        free_weight = sum(weights[i] for i in free) or 1
        widths = [fixed.get(i, rest * weights[i] / free_weight) for i in range(len(columns))]
        short = [i for i in free if widths[i] < floors[i]]
        if not short:
            return widths
        for i in short:
            fixed[i] = floors[i]


def _pick(sizes: list[int], fits) -> int | None:
    for fs in sizes:
        if fits(fs):
            return fs
    return None


# ================================================================ 텍스트 런

def _parts(text: str, color: str = "ink", bold: bool = False, bullet: bool = False) -> list[dict]:
    """'**굵게**'를 굵은 런으로 나눈 파트 목록. 마지막 파트에 줄바꿈을 붙인다."""
    parts = []
    for seg in re.split(r"(\*\*.+?\*\*)", text):
        if not seg:
            continue
        if seg.startswith("**") and seg.endswith("**"):
            parts.append({"t": seg[2:-2], "b": True, "c": "navy" if color in ("ink", "body") else color})
        else:
            parts.append({"t": seg, "b": bold, "c": color})
    if parts:
        parts[0]["bullet"] = bullet
        parts[-1]["br"] = True
    return parts


def _body_parts(text: str, color: str = "body") -> list[dict]:
    """여러 줄 본문: '- '로 시작하는 줄은 불릿."""
    out = []
    for line in text.split("\n"):
        line = line.rstrip()
        if not line.strip():
            continue
        bullet = bool(re.match(r"^\s*[-*•]\s+", line))
        out += _parts(re.sub(r"^\s*[-*•]\s+", "", line), color, bullet=bullet)
    return out


def _js(value) -> str:
    return json.dumps(value, ensure_ascii=False)


NUMBERING_RE = re.compile(r"^\s*(?:\d{1,2}\s*[.)]|\(\d{1,2}\)|[①-⑳])\s*")


def _strip_numbering(spec: dict) -> dict:
    """번호 배지가 붙는 자리의 글에서 손으로 단 번호('1.', '2)', '①')를 뗀다(배지와 숫자가 겹치지 않게)."""
    s = json.loads(json.dumps(spec))
    s["items"] = [dict(it, heading=NUMBERING_RE.sub("", it.get("heading", "")),
                       text=it.get("text", "") if it.get("heading", "").strip() else NUMBERING_RE.sub("", it.get("text", "")))
                  for it in s.get("items", [])]
    s["side_points"] = [NUMBERING_RE.sub("", p) for p in s.get("side_points", [])]
    for side in ("left", "right"):
        if s.get(side):
            s[side] = dict(s[side], points=[NUMBERING_RE.sub("", p) for p in s[side].get("points", [])])
    return s


# ================================================================ 패턴별 레이아웃

class SlideWriter:
    """한 장의 슬라이드 함수 본문(JS 문)을 만든다."""

    def __init__(self, no: int, spec: dict) -> None:
        self.no, self.spec = no, _strip_numbering(spec)
        self.stmts: list[str] = []
        self.errors: list[str] = []
        self.bottom = 0.0
        lead = spec.get("lead", "").strip()
        self.top = 1.90 if lead else 1.45
        self.limit = BODY_BOTTOM
        if spec.get("message", "").strip():
            self.limit = BODY_BOTTOM - 0.95

    @property
    def H(self) -> float:
        return self.limit - self.top

    def err(self, msg: str) -> None:
        self.errors.append(f"{self.no}번 슬라이드: {msg}")

    def emit(self, stmt: str) -> None:
        self.stmts.append(stmt)

    def mark(self, y_bottom: float) -> None:
        self.bottom = max(self.bottom, y_bottom)

    # ---------------------------------------------------------- 공통 부품

    def box(self, x, y, w, h, fill="tint"):
        self.emit(f"box(slide, {{ x: {x:.3f}, y: {y:.3f}, w: {w:.3f}, h: {h:.3f}, fill: C.{fill} }});")
        self.mark(y + h)

    def text(self, parts, x, y, w, h, fs, valign="top", align="left"):
        self.emit(
            f"slide.addText(rich({_js(parts)}, {fs}), {{ x: {x:.3f}, y: {y:.3f}, w: {w:.3f}, h: {h:.3f}, "
            f"fontFace: FONT, valign: \"{valign}\", align: \"{align}\", margin: 0.12, paraSpaceAfter: 4 }});")

    def badge(self, x, y, n, size=0.5, color="blue"):
        self.emit(f"numBadge(slide, {{ x: {x:.3f}, y: {y:.3f}, n: {_js(str(n))}, color: C.{color}, size: {size} }});")

    def numbered_rows(self, items: list[dict], x, y, w, h, fill="altRow", sizes=(21, 20, 18, 16, 14),
                      slots: int | None = None, start: int = 1):
        """번호 배지 + 굵은 소제목 + 설명으로 된 행 목록으로 영역을 채운다.
        slots 를 주면 그 개수 기준으로 행 높이를 정해 옆 열과 높이를 맞춘다."""
        n = len(items)
        if not n:
            return
        slots = max(slots or n, n)
        row_h = (h - GAP * (slots - 1)) / slots
        text_w = w - 0.95

        def text_fs(it, fs):
            return max(MIN_FONT, fs - 2) if it.get("heading") else fs

        def fits(fs):
            return all(
                _height(_plain(it.get("heading", "")), fs, text_w) * (1 if it.get("heading") else 0)
                + _height(_plain(it.get("text", "")), text_fs(it, fs), text_w) * (1 if it.get("text") else 0)
                + 0.2 <= row_h
                for it in items)

        fs = _pick(list(sizes), fits)
        if fs is None:
            self.err(f"항목 {n}개가 영역에 다 들어가지 않음(14pt 기준) — 항목 수나 글자 수를 줄이거나 슬라이드를 나눌 것")
            fs = MIN_FONT
        for k, it in enumerate(items):
            ry = y + k * (row_h + GAP)
            self.box(x, ry, w, row_h, fill)
            self.badge(x + 0.2, ry + (row_h - 0.5) / 2, k + start)
            parts = []
            if it.get("heading"):
                parts += _parts(it["heading"], "navy", bold=True)
            if it.get("text"):
                parts += [dict(p, fs=text_fs(it, fs)) for p in _body_parts(it["text"])]
            self.text(parts, x + 0.85, ry, text_w, row_h, fs, valign="middle")

    def card_grid(self, items: list[dict], cols: int, x, y, w, h, numbered=False):
        n = len(items)
        rows = math.ceil(n / cols)
        cw = (w - GAP * (cols - 1)) / cols
        ch = (h - GAP * (rows - 1)) / rows
        inner_w = cw - 0.3

        def fits(fs):
            for it in items:
                need = 0.25 + _height(_plain(it.get("heading", "")), fs + 2, inner_w - (0.6 if numbered else 0))
                need += _height(_plain(it.get("text", "")), fs, inner_w)
                if need > ch:
                    return False
            return True

        fs = _pick([20, 18, 16, 14], fits)
        if fs is None:
            self.err("카드 내용이 카드 높이를 넘음(14pt 기준) — 카드 글을 줄이거나 슬라이드를 나눌 것")
            fs = MIN_FONT
        last_row = rows - 1
        last_count = n - cols * last_row
        for k, it in enumerate(items):
            row = k // cols
            # 마지막 줄이 덜 찼으면(예: 5개를 3열에) 그 줄 카드를 넓혀 빈 칸이 생기지 않게 한다
            row_w = (w - GAP * (last_count - 1)) / last_count if row == last_row and last_count < cols else cw
            cx = x + (k % cols) * (row_w + GAP)
            cy = y + row * (ch + GAP)
            cw_k = row_w
            self.box(cx, cy, cw_k, ch, "tint")
            head_x = cx + 0.15
            if numbered:
                self.badge(cx + 0.2, cy + 0.2, k + 1, size=0.45)
                head_x = cx + 0.75
            head_h = _height(_plain(it.get("heading", "")), fs + 2, cx + cw_k - 0.15 - head_x) + 0.15
            self.text(_parts(it.get("heading", ""), "navy", bold=True), head_x, cy + 0.12,
                      cx + cw_k - 0.15 - head_x, max(head_h, 0.55), fs + 2, valign="middle")
            body_y = cy + 0.12 + max(head_h, 0.55)
            self.text(_body_parts(it.get("text", ""), "slate"), cx + 0.15, body_y, cw_k - 0.3,
                      cy + ch - body_y - 0.1, fs)

    def header_bar(self, x, y, w, text, accent=False):
        self.emit(f"headerBar(slide, {{ x: {x:.3f}, y: {y:.3f}, w: {w:.3f}, text: {_js(text)}, accent: {str(accent).lower()} }});")
        self.mark(y + 0.5)

    def points_box(self, points: list[str], x, y, w, h, fill="tint"):
        self.box(x, y, w, h, fill)
        text = "\n".join(f"- {p}" for p in points)

        def fits(fs):
            return _height(_plain(text), fs, w - 0.5, 1.45) + 0.3 <= h

        fs = _pick([20, 18, 16, 14], fits)
        if fs is None:
            self.err("요약 박스 글이 넘침(14pt 기준) — 항목을 줄일 것")
            fs = MIN_FONT
        self.text(_body_parts(text), x + 0.15, y + 0.1, w - 0.3, h - 0.2, fs)

    # ---------------------------------------------------------- 패턴

    def build(self) -> None:
        s = self.spec
        pattern = s.get("pattern")
        items = [i for i in s.get("items", []) if i.get("heading") or i.get("text")]
        x, y, w, h = X0, self.top, CW, self.H

        if pattern in ("objectives", "steps"):
            if not 1 <= len(items) <= 6:
                self.err(f"{pattern} 항목은 1~6개 (현재 {len(items)}개)")
            self.numbered_rows(items[:6], x, y, w, h)
        elif pattern in ("agenda", "cards"):
            if not 2 <= len(items) <= 6:
                self.err(f"{pattern} 카드는 2~6개 (현재 {len(items)}개)")
            items = items[:6]
            cols = {1: 1, 2: 2, 3: 3, 4: 2}.get(len(items), 3)
            self.card_grid(items, cols, x, y, w, h, numbered=pattern == "agenda")
        elif pattern == "two_column":
            left, right = s.get("left", {}), s.get("right", {})
            if not left.get("points") or not right.get("points"):
                self.err("two_column 은 left.points 와 right.points 가 모두 있어야 함")
            lw = CW * 0.42
            rx, rw = X0 + lw + 0.3, CW - lw - 0.3
            self.header_bar(x, y, lw, left.get("header") or "개요")
            self.header_bar(rx, y, rw, right.get("header") or "방법", accent=True)
            by, bh = y + 0.65, h - 0.65
            self.points_box(left.get("points", []), x, by, lw, bh)
            self.numbered_rows([{"text": p} for p in right.get("points", [])[:6]], rx, by, rw, bh,
                               sizes=(20, 18, 16, 14))
        elif pattern == "table":
            self.table_pattern(s, x, y, w, h)
        elif pattern == "code":
            self.code_pattern(s, x, y, w, h)
        elif pattern == "why_how_what":
            if len(items) != 3:
                self.err(f"why_how_what 항목은 정확히 3개 (현재 {len(items)}개)")
            self.why_how_what(items[:3], x, y, w, h)
        elif pattern == "summary":
            if not 3 <= len(items) <= 8:
                self.err(f"summary 항목은 3~8개 (현재 {len(items)}개)")
            items = items[:8]
            if len(items) <= 4:
                self.numbered_rows(items, x, y, w, h)
            else:
                half = math.ceil(len(items) / 2)
                cw = (w - 0.3) / 2
                self.numbered_rows(items[:half], x, y, cw, h, sizes=(20, 18, 16, 14), slots=half)
                self.numbered_rows(items[half:], x + cw + 0.3, y, cw, h, sizes=(20, 18, 16, 14),
                                   slots=half, start=half + 1)
        else:
            self.err(f"알 수 없는 패턴 '{pattern}' (허용: {', '.join(PATTERNS)})")

        if s.get("message", "").strip():
            cy = BODY_BOTTOM - 0.8
            self.emit(f"callout(slide, {{ x: {X0}, y: {cy:.3f}, w: {CW}, h: 0.8, text: {_js(s['message'].strip())} }});")
            if _units(s["message"]) * 18 / 72 > CW - 0.4:
                self.err("핵심 메시지(message)가 한 줄을 넘음 — 50자 안쪽으로 줄일 것")
            self.mark(BODY_BOTTOM)

    def table_pattern(self, s, x, y, w, h):
        t = s.get("table", {})
        cols, rows = t.get("columns", []), t.get("rows", [])
        if not cols or not rows:
            self.err("table 패턴에 columns 와 rows 가 없음")
            return
        if len(rows) > 7:
            self.err(f"표 행 {len(rows)}개 (최대 7개) — 표를 나눌 것")
        rows = [r + [""] * (len(cols) - len(r)) for r in rows[:7]]
        side = s.get("side_points", [])
        tw = CW * 0.62 if side else CW
        label = t.get("label", "").strip()
        ty = y
        if label:
            lw = min(tw, 0.5 + _units(label) * 18 / 72)
            self.emit(f"darkBadge(slide, {{ x: {x:.3f}, y: {y:.3f}, w: {lw:.3f}, h: 0.45, text: {_js(label)} }});")
            ty = y + 0.6
        avail = self.limit - ty
        col_w = _column_widths([cols] + rows, tw)

        def table_h(fs):
            total = 0.0
            for row in [cols] + rows:
                lines = max(_lines(_plain(str(c)), fs, cw - 0.2) for c, cw in zip(row, col_w))
                total += max(0.5, lines * fs * 1.25 / 72 + 0.18)
            return total

        fs = _pick([20, 18, 16, 14], lambda f: table_h(f) <= avail)
        if fs is None:
            self.err("표가 영역을 넘음(14pt 기준) — 행이나 셀 글을 줄일 것")
            fs = MIN_FONT
        base_h = table_h(fs)
        row_h = max(0.5, min(1.0, avail / (len(rows) + 1))) if base_h < avail else None
        data = [[{"text": _plain(str(c)), "options": {"fill": {"color": "@tableHead"}, "color": "@navy", "bold": True}}
                 for c in cols]]
        for k, row in enumerate(rows):
            fill = "@altRow" if k % 2 else "@white"
            data.append([{"text": _plain(str(c)), "options": {"fill": {"color": fill}, "color": "@ink"}} for c in row])
        rows_js = re.sub(r'"@(\w+)"', r"C.\1", _js(data))
        row_h_js = f"rowH: {row_h:.3f}, " if row_h else ""
        self.emit(
            f"slide.addTable({rows_js}, {{ x: {x:.3f}, y: {ty:.3f}, w: {tw:.3f}, colW: {_js([round(c, 3) for c in col_w])}, "
            f"{row_h_js}fontSize: fsMin({fs}), fontFace: FONT, valign: \"middle\", margin: 0.08, "
            f"border: {{ type: \"solid\", color: C.line, pt: 1 }} }});")
        used = (row_h * (len(rows) + 1)) if row_h and row_h * (len(rows) + 1) >= base_h else base_h
        self.mark(ty + used)
        if side:
            sx = x + tw + 0.3
            self.numbered_rows([{"text": p} for p in side[:5]], sx, y, CW - tw - 0.3, h, sizes=(18, 16, 14))

    def code_pattern(self, s, x, y, w, h):
        code = s.get("code", {}).get("text", "").rstrip("\n")
        if not code.strip():
            self.err("code 패턴에 code.text 가 없음")
            return
        lines = code.split("\n")
        if len(lines) > 14:
            self.err(f"코드 {len(lines)}줄 (최대 14줄) — 핵심 부분만 남길 것")
        side = s.get("side_points", [])
        cw = CW * 0.58 if side else CW
        longest = max(_units(ln) for ln in lines)
        fs = _pick([18, 16, 14], lambda f: len(lines) * f * 1.25 / 72 + 0.4 <= h and longest * f / 72 <= cw - 0.4)
        if fs is None:
            self.err("코드가 상자에 다 들어가지 않음(14pt 기준) — 줄 수나 줄 길이를 줄일 것")
            fs = MIN_FONT
        self.box(x, y, cw, h, "altRow")
        lang = s.get("code", {}).get("language", "")
        if lang:
            self.emit(f"pill(slide, {{ x: {x + cw - 1.75:.3f}, y: {y + 0.15:.3f}, w: 1.6, h: 0.4, text: {_js(lang)} }});")
        parts = [{"t": ln if ln.strip() else " ", "c": "ink", "br": True} for ln in lines]
        self.text(parts, x + 0.2, y + 0.2, cw - 0.4, h - 0.4, fs)
        if side:
            sx = x + cw + 0.3
            self.numbered_rows([{"text": p} for p in side[:5]], sx, y, CW - cw - 0.3, h, sizes=(18, 16, 14))

    def why_how_what(self, items, x, y, w, h):
        labels = [("WHY", "navy"), ("HOW", "blue"), ("WHAT", "dark")]
        row_h = (h - GAP * 2) / 3
        lw = 2.6
        tw = w - lw - 0.15

        def fits(fs):
            return all(_height(_plain(it.get("text", "")), fs, tw - 0.3) + 0.25 <= row_h for it in items)

        fs = _pick([20, 18, 16, 14], fits)
        if fs is None:
            self.err("WHY/HOW/WHAT 설명이 행 높이를 넘음 — 글을 줄일 것")
            fs = MIN_FONT
        for k, it in enumerate(items):
            ry = y + k * (row_h + GAP)
            label, color = labels[k]
            self.emit(f"labelCell(slide, {{ x: {x:.3f}, y: {ry:.3f}, w: {lw}, h: {row_h:.3f}, color: C.{color}, "
                      f"label: {_js(label)}, sub: {_js(it.get('heading', ''))} }});")
            self.box(x + lw + 0.15, ry, tw, row_h, "altRow")
            self.text(_body_parts(it.get("text", "")), x + lw + 0.3, ry, tw - 0.3, row_h, fs, valign="middle")

    def function(self) -> str:
        s = self.spec
        lines = [f"async function createSlide{self.no:02d}(pptx) {{",
                 "  const slide = pptx.addSlide({ masterName: LAYOUT });",
                 f"  pageHeader(slide, {{ title: {_js(s.get('title', ''))}, lead: {_js(s.get('lead', '').strip())} }});"]
        lines += [f"  {st}" for st in self.stmts]
        if s.get("source", "").strip():
            lines.append(f"  sourceLine(slide, {_js(s['source'].strip())});")
        if s.get("notes", "").strip():
            lines.append(f"  slide.addNotes({_js(s['notes'].strip())});")
        lines += ["  return slide;", "}"]
        return "\n".join(lines)


# ================================================================ JS 템플릿

JS_HEADER = r"""// 자동 생성 파일 — courseware_agent/pptx_builder.py (references/pptx-guide.md 준수)
const pptxgen = require("pptxgenjs");

const FONT = "Pretendard";
const LAYOUT = "내용_단쪽";              // 본 덱 레이아웃 이름과 글자 하나까지 같아야 함
const X0 = 0.557, CW = 14.9;            // 콘텐츠 왼쪽 끝과 폭 (제목 개체 틀과 같은 선)
const BODY_TOP = 1.90, BODY_BOTTOM = 7.95;

const C = {
  title:  "2C2926",  lead:   "000000",
  navy:   "1E2A5C",  blue:   "2E74C6",  ink:    "2B3242",
  slate:  "4A5364",  sub:    "7C8598",  body:   "3B4557",
  tint:   "EEF3FA",  altRow: "F5F8FC",  tableHead: "E2EEF9",
  dark:   "404155",  border: "D9E0EC",  line:   "EDF0F6",
  titleLine: "E2E8F0", footLine: "E9ECF3", pageNum: "6B6B7B",
  pillLine: "C3CEE0", white: "FFFFFF",
};

const MIN_FONT = 14;
const fsMin = (size) => {
  if (size < MIN_FONT) throw new Error(`fontSize ${size} < ${MIN_FONT}pt 금지! 슬라이드를 분리할 것`);
  return size;
};

let pptx;   // 헬퍼(headerBar, sourceLine 등)가 pptx.shapes를 쓰므로 모듈 범위에 둠

// 6-5 — 본 덱 `내용_단쪽` 실측값
function defineContentLayout(pptx) {
  pptx.defineSlideMaster({
    title: LAYOUT,
    background: { color: "FFFFFF" },
    objects: [
      { line: { x: 0.556, y: 0.95, w: 14.888, h: 0, line: { color: C.titleLine, width: 1.5 } } },
      { text: { text: "무단전재 및 배포 금지",
          options: { x: 0.4875, y: 8.517, w: 1.675, h: 0.27,
                     fontFace: FONT, fontSize: 12, color: "A6A6A6", margin: 0 } } },
      { placeholder: { options: { name: "title", type: "title", x: X0, y: 0.109, w: 15.025, h: 0.906,
          fontFace: FONT, fontSize: 32, bold: true, color: C.title, margin: 0, align: "left", valign: "middle" },
          text: "" } },
    ],
    slideNumber: { x: 11.913, y: 8.517, w: 3.6, h: 0.25,
                   fontFace: FONT, fontSize: 16, color: C.pageNum, align: "right" },
  });
}

// 장 제목(제목 개체 틀) + 리드문(선택)
function pageHeader(slide, { title, lead }) {
  slide.addText(title, { placeholder: "title" });
  if (lead) {
    slide.addText(lead, { x: X0, y: 1.259, w: CW, h: 0.42, margin: 0, isTextBox: true,
      fontFace: "Pretendard SemiBold", fontSize: fsMin(18), color: C.lead });
  }
}

// 출처 줄 — 140자 초과는 12pt (출처에만 허용하는 예외)
function sourceLine(slide, text) {
  slide.addShape(pptx.shapes.LINE, { x: X0, y: 8.08, w: CW, h: 0, line: { color: C.footLine, width: 1 } });
  slide.addText(text, { x: X0, y: 8.14, w: CW, h: 0.42, margin: 0, valign: "top", isTextBox: true,
    fontFace: FONT, fontSize: text.length > 140 ? 12 : 14, color: C.sub });
}

// 6-3 — 단색 헤더 바
function headerBar(slide, { x, y, w, text, accent = false }) {
  slide.addShape(pptx.shapes.ROUNDED_RECTANGLE, {
    x, y, w, h: 0.5, rectRadius: 0.06,
    fill: { color: accent ? C.blue : C.navy },
    line: { type: "none" },
  });
  slide.addText(text, { x, y, w, h: 0.5, align: "center", valign: "middle", color: C.white,
    bold: true, fontSize: fsMin(24), fontFace: FONT, margin: 0 });
}

// 6-4 — 넘버 배지
function numBadge(slide, { x, y, n, color = C.blue, size = 0.4 }) {
  slide.addShape(pptx.shapes.ROUNDED_RECTANGLE, {
    x, y, w: size, h: size, rectRadius: 0.05, fill: { color }, line: { type: "none" },
  });
  slide.addText(String(n), { x, y, w: size, h: size, align: "center", valign: "middle",
    color: C.white, bold: true, fontSize: fsMin(18), fontFace: FONT, margin: 0 });
}

// 틴트 정보 박스 / 카드 (테두리 #D9E0EC)
function box(slide, { x, y, w, h, fill = C.tint }) {
  slide.addShape(pptx.shapes.ROUNDED_RECTANGLE, {
    x, y, w, h, rectRadius: 0.1, fill: { color: fill }, line: { color: C.border, width: 1 },
  });
}

// 다크 배지 (표 섹션 라벨)
function darkBadge(slide, { x, y, w, h, text }) {
  slide.addShape(pptx.shapes.ROUNDED_RECTANGLE, {
    x, y, w, h, rectRadius: 0.05, fill: { color: C.dark }, line: { type: "none" },
  });
  slide.addText(text, { x, y, w, h, align: "center", valign: "middle", color: C.white,
    bold: true, fontSize: fsMin(18), fontFace: FONT, margin: 0 });
}

// 필 라벨
function pill(slide, { x, y, w, h, text }) {
  slide.addShape(pptx.shapes.ROUNDED_RECTANGLE, {
    x, y, w, h, rectRadius: h / 2, fill: { color: C.tint }, line: { color: C.pillLine, width: 1 },
  });
  slide.addText(text, { x, y, w, h, align: "center", valign: "middle", color: C.navy,
    bold: true, fontSize: fsMin(14), fontFace: FONT, margin: 0 });
}

// WHY / HOW / WHAT 라벨 셀 (영문 대문자 + 한글 부제)
function labelCell(slide, { x, y, w, h, color, label, sub }) {
  slide.addShape(pptx.shapes.ROUNDED_RECTANGLE, {
    x, y, w, h, rectRadius: 0.08, fill: { color }, line: { type: "none" },
  });
  slide.addText([
    { text: label, options: { bold: true, fontSize: fsMin(24), color: C.white, fontFace: FONT, breakLine: true } },
    { text: sub, options: { fontSize: fsMin(16), color: C.white, fontFace: FONT } },
  ], { x, y, w, h, align: "center", valign: "middle", margin: 0.1 });
}

// 인용 콜아웃 — 좌측 블루 바 + 굵은 기울임 네이비 글
function callout(slide, { x, y, w, h, text }) {
  slide.addShape(pptx.shapes.RECTANGLE, { x, y, w: 0.07, h, fill: { color: C.blue }, line: { type: "none" } });
  slide.addText(text, { x: x + 0.25, y, w: w - 0.25, h, valign: "middle", margin: 0,
    color: C.navy, bold: true, italic: true, fontSize: fsMin(18), fontFace: FONT });
}

// 파트 목록 → 텍스트 런 (모든 글자에 fontFace 와 fsMin 경유 fontSize)
function rich(parts, fs) {
  return parts.map((p) => ({
    text: p.t,
    options: {
      bold: !!p.b, color: C[p.c || "ink"], fontFace: FONT, fontSize: fsMin(p.fs || fs),
      breakLine: !!p.br, bullet: p.bullet ? { indent: 18 } : false,
    },
  }));
}
"""

JS_MAIN = """
async function main() {
  pptx = new pptxgen();
  pptx.defineLayout({ name: "CUSTOM", width: 16, height: 9 });
  pptx.layout = "CUSTOM";
  pptx.title = %(title)s;
  defineContentLayout(pptx);   // 6-5 — 레이아웃 이름 "내용_단쪽"

  for (const fn of [%(funcs)s]) {
    await fn(pptx);
  }

  await pptx.writeFile({ fileName: %(out)s });
  console.log("✅ PPT 생성 완료");
}

main().catch((e) => { console.error("❌ PPT 생성 실패:", e); process.exit(1); });
"""


# ================================================================ 명세 점검

def lint_spec(spec: dict, target_count: int) -> list[str]:
    errors = []
    slides = spec.get("slides", [])
    if abs(len(slides) - target_count) > 3:
        errors.append(f"슬라이드 수 {len(slides)}장 (목표 {target_count}장 ±3)")
    if slides and slides[0].get("pattern") != "objectives":
        errors.append("첫 슬라이드는 학습 목표(objectives)여야 함 — 표지와 간지는 새 덱에서 만들지 않음")
    for no, s in enumerate(slides, 1):
        title = s.get("title", "")
        if not title.strip():
            errors.append(f"{no}번 슬라이드 제목 없음")
        if _units(title) * 32 / 72 > 15.0:
            errors.append(f"{no}번 슬라이드 제목이 한 줄(32pt)을 넘음: '{title}'")
        lead = s.get("lead", "")
        if _units(lead) * 18 / 72 > CW:
            errors.append(f"{no}번 슬라이드 리드문이 한 줄(18pt)을 넘음")
        source = s.get("source", "").strip()
        source_fs = 12 if len(source) > 140 else 14   # 가이드: 140자 초과는 12pt 전폭 허용, 단 한 줄
        if source and _units(source) * source_fs / 72 > CW:
            errors.append(f"{no}번 슬라이드 출처 문구가 한 줄({source_fs}pt)을 넘음 — 「무단전재」 문구와 겹치므로 줄일 것")
        if not s.get("notes", "").strip():
            errors.append(f"{no}번 슬라이드 발표자 노트 없음")
        dots = [f for f, v in _text_fields(s) if MIDDLE_DOT in v]
        if dots:
            errors.append(f"{no}번 슬라이드 가운뎃점(·) 사용: {', '.join(dots)} — 뜻하는 말(와/과, 쉼표, 또는, 괄호)로 바꿀 것")
    return errors


def _text_fields(s: dict):
    """코드를 뺀 모든 글 필드 (이름, 값)."""
    for key in ("title", "lead", "message", "source", "notes"):
        yield key, s.get(key, "")
    for k, it in enumerate(s.get("items", []), 1):
        yield f"items[{k}]", f"{it.get('heading', '')} {it.get('text', '')}"
    for side in ("left", "right"):
        part = s.get(side) or {}
        yield side, " ".join([part.get("header", "")] + part.get("points", []))
    yield "side_points", " ".join(s.get("side_points", []))
    table = s.get("table") or {}
    yield "table", " ".join([table.get("label", "")] + table.get("columns", []) + [" ".join(r) for r in table.get("rows", [])])


# ================================================================ 빌드

def generate_js(spec: dict, deck_title: str, out_name: str) -> tuple[str, list[str], list[BuiltSlide]]:
    built, errors, funcs = [], [], []
    for no, s in enumerate(spec.get("slides", []), 1):
        writer = SlideWriter(no, s)
        writer.build()
        if writer.bottom and BODY_BOTTOM - writer.bottom > 1.0:
            writer.err(f"하단 여백 {BODY_BOTTOM - writer.bottom:.1f}인치 — 내용을 보강하거나 다른 패턴을 쓸 것")
        errors += writer.errors
        built.append(BuiltSlide(no, writer.function(), writer.errors, writer.bottom))
        funcs.append(f"createSlide{no:02d}")
    js = JS_HEADER + "\n" + "\n\n".join(b.func for b in built) + "\n" + JS_MAIN % {
        "title": _js(deck_title), "funcs": ", ".join(funcs), "out": _js(out_name)}
    return js, errors, built


def fix_placeholders(pptx_path: Path) -> None:
    """6-14 — pptxgenjs 개체 틀 번호를 본 덱 `내용_단쪽`과 같게 맞춘다."""
    tmp = pptx_path.with_suffix(".tmp")
    with zipfile.ZipFile(pptx_path) as zin, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if re.match(r"ppt/(slides|slideLayouts)/slide(Layout)?\d+\.xml$", item.filename):
                x = data.decode("utf8")
                x = re.sub(r'<p:ph\s+idx="\d+"\s+type="title"[^>]*/>', '<p:ph type="title"/>', x)
                x = re.sub(r'<p:ph type="sldNum" sz="quarter" idx="\d+"/>', '<p:ph type="sldNum" idx="4"/>', x)
                data = x.encode("utf8")
            zout.writestr(item, data)
    shutil.move(str(tmp), str(pptx_path))


def check_paste(pptx_path: Path) -> list[str]:
    """6-13 — 본 덱 붙여넣기 호환 점검. 문제 없으면 빈 목록."""
    from pptx import Presentation

    p = Presentation(str(pptx_path))
    err = []
    if (p.slide_width, p.slide_height) != (14630400, 8229600):
        err.append("슬라이드 크기가 16x9인치가 아님")
    for i, s in enumerate(p.slides, 1):
        if s.slide_layout.name != "내용_단쪽":
            err.append(f"{i}쪽 레이아웃 이름: {s.slide_layout.name}")
        if s.shapes.title is None or not s.shapes.title.text.strip():
            err.append(f"{i}쪽 제목 개체 틀 비었음")
        for sh in s.shapes:
            if sh.has_text_frame and " / " in sh.text_frame.text and sh.top > 7_500_000 and len(sh.text_frame.text) < 10:
                err.append(f"{i}쪽 글자 쪽 표시 의심: {sh.text_frame.text}")
    xml = "".join(s._element.xml for s in p.slides)
    if "schemeClr" in xml:
        err.append("테마 색(schemeClr) 사용")
    fonts = set(re.findall(r'typeface="([^"]+)"', xml))
    banned = fonts & {"Calibri", "Arial", "맑은 고딕", "Malgun Gothic"}
    if banned:
        err.append(f"금지 글꼴 사용: {sorted(banned)}")
    return err


def render_preview(pptx_path: Path, out_dir: Path, timeout: int = 300) -> list[Path]:
    """LibreOffice 미리보기(scripts/render-pptx.py). 도구가 없으면 빈 목록."""
    if not RENDER_SCRIPT.exists():
        return []
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("*"):   # 이미지 뷰어 등이 잡고 있는 파일은 건너뛰고 덮어쓴다
        try:
            old.unlink()
        except OSError:
            pass
    result = subprocess.run(
        [sys.executable, str(RENDER_SCRIPT), str(pptx_path), "--out", str(out_dir), "--width", "1280"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
    if result.returncode != 0:
        raise RuntimeError(f"미리보기 실패: {result.stdout[-500:]} {result.stderr[-500:]}")
    return sorted(out_dir.glob("slide-*.png"), key=lambda p: int(re.search(r"(\d+)", p.stem).group(1)))


@dataclass
class BuildResult:
    pptx: Path
    js: Path
    layout_errors: list[str]
    paste_errors: list[str]
    previews: list[Path]
    pdf: Path | None


def build_deck(spec: dict, deck_title: str, pptx_path: Path, preview_dir: Path | None = None) -> BuildResult:
    """명세로 build.js 를 만들고 node 로 실행해 .pptx 를 만든 뒤 정리, 점검, 미리보기까지 한다."""
    build_dir = pptx_path.parent / "build"
    build_dir.mkdir(exist_ok=True)
    js_path = build_dir / f"{pptx_path.stem}.build.js"
    js, layout_errors, _ = generate_js(spec, deck_title, pptx_path.name)
    js_path.write_text(js, encoding="utf-8")

    node = shutil.which("node")
    if not node:
        raise RuntimeError("node 를 찾을 수 없음 (node ≥ 18 필요)")
    tmp_out = build_dir / pptx_path.name
    result = subprocess.run([node, js_path.name], cwd=build_dir, capture_output=True, text=True,
                            encoding="utf-8", errors="replace", timeout=180,
                            env={**_env(), "NODE_PATH": str(AGENT_DIR / "node_modules")})
    if result.returncode != 0 or not tmp_out.exists() or tmp_out.stat().st_size == 0:
        raise RuntimeError(f"PPT 빌드 실패 (exit={result.returncode}): {result.stderr[-800:]}")

    # 정리, 점검, 미리보기는 build/ 사본에서 한다. 사람이 slides/ 의 덱을 열어 둬도 빌드가 멈추지 않게 하기 위함
    fix_placeholders(tmp_out)
    paste_errors = check_paste(tmp_out)
    previews, pdf = [], None
    if preview_dir is not None:
        previews = render_preview(tmp_out, preview_dir)
        pdf_src = preview_dir / f"{pptx_path.stem}.pdf"
        if pdf_src.exists():
            pdf = _publish(pdf_src, pptx_path.with_suffix(".pdf"), copy=True)
    final = _publish(tmp_out, pptx_path)
    return BuildResult(final, js_path, layout_errors, paste_errors, previews, pdf)


def _publish(src: Path, dst: Path, copy: bool = False, attempts: int = 3) -> Path:
    """src 를 dst 자리에 놓는다. dst 가 PowerPoint 등에 열려 잠겨 있으면 잠시 기다렸다가,
    끝내 안 되면 dst.latest 이름으로 저장하고 그 경로를 돌려준다(다음 성공 때 정리)."""
    import logging
    import os
    import time
    alt = dst.with_name(f"{dst.stem}.latest{dst.suffix}")
    for attempt in range(attempts):
        try:
            if copy:
                shutil.copyfile(src, dst)
            else:
                os.replace(src, dst)
            alt.unlink(missing_ok=True)
            return dst
        except PermissionError:
            time.sleep(2 * (attempt + 1))
    if copy:
        shutil.copyfile(src, alt)
    else:
        os.replace(src, alt)
    logging.getLogger("courseware").warning("%s 이(가) 열려 있어 새 버전을 %s 에 저장함 (닫으면 다음 빌드에서 교체)",
                                            dst.name, alt.name)
    return alt


def _env() -> dict:
    import os
    return dict(os.environ)


# ================================================================ 명세 → 읽기용 마크다운

def spec_to_markdown(spec: dict, deck_title: str) -> str:
    """사람이 읽는 슬라이드 스크립트(시각 명세 .md)."""
    out = [f"# {deck_title} — 슬라이드 명세", "",
           "> 레이아웃 `내용_단쪽`, 16″×9″. 표지와 간지는 본 덱에서 추가한다.", "",
           f"<!-- 간지: {deck_title} -->", ""]
    for no, s in enumerate(spec.get("slides", []), 1):
        out += [f"## {no}. {s.get('title', '')}", "", f"- 패턴: `{s.get('pattern')}`"]
        if s.get("lead"):
            out.append(f"- 리드문: {s['lead']}")
        for k, it in enumerate(s.get("items", []), 1):
            text = it.get("text", "").replace("\n", " / ")
            out.append(f"- {k}. **{it.get('heading', '')}** {text}".rstrip())
        for side in ("left", "right"):
            part = s.get(side) or {}
            if part.get("points"):
                out.append(f"- {side} [{part.get('header', '')}]: " + "; ".join(part["points"]))
        table = s.get("table") or {}
        if table.get("columns"):
            out += ["", f"표: {table.get('label', '')}", "",
                    "| " + " | ".join(table["columns"]) + " |",
                    "|" + "---|" * len(table["columns"])]
            out += ["| " + " | ".join(r) + " |" for r in table.get("rows", [])]
            out.append("")
        code = s.get("code") or {}
        if code.get("text"):
            out += ["", f"```{code.get('language', '')}", code["text"].rstrip("\n"), "```", ""]
        if s.get("side_points"):
            out.append("- 보조 설명: " + "; ".join(s["side_points"]))
        if s.get("message"):
            out.append(f"- 핵심 메시지: {s['message']}")
        if s.get("source"):
            out.append(f"- 출처: {s['source']}")
        out += ["", f"<!-- 노트: {s.get('notes', '')} -->", ""]
    return "\n".join(out)
