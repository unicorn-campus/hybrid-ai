"""LLM 리뷰 전에 돌리는 결정적(deterministic) 점검."""
from __future__ import annotations

import re

from .prompts import REQUIRED_SECTIONS

URL_RE = re.compile(r"https?://[^\s)\]>\"'`]+")


def normalize_url(url: str) -> str:
    return url.rstrip(".,;:").rstrip("/").lower().replace("://www.", "://")


def lint_chapter(markdown: str, source_urls: list[str], min_chars: int) -> list[str]:
    errors: list[str] = []
    lines = markdown.strip().splitlines()
    if not lines or not re.match(r"^# \S", lines[0]):
        errors.append("첫 줄이 '# N장. 제목' 형식의 H1이 아님")
    if sum(1 for ln in _outside_code(lines) if ln.startswith("# ")) > 1:
        errors.append("H1(# 제목)이 두 개 이상임")

    headings = [ln for ln in _outside_code(lines) if ln.startswith("## ")]
    for name in REQUIRED_SECTIONS:
        if not any(name in h for h in headings):
            errors.append(f"필수 절 '## {name}'이 없음")

    if len(markdown) < min_chars:
        errors.append(f"분량 부족: {len(markdown)}자 (최소 {min_chars}자)")
    if markdown.count("```") % 2:
        errors.append("코드 블록(```)이 닫히지 않음")
    if "<details>" in markdown and markdown.count("<details>") != markdown.count("</details>"):
        errors.append("<details> 태그 짝이 맞지 않음")

    known = {normalize_url(u) for u in source_urls}
    unknown = sorted({u for u in URL_RE.findall(markdown) if normalize_url(u) not in known})
    if unknown:
        errors.append("리서치 출처에 없는 URL: " + ", ".join(unknown[:8]))
    return errors


def _outside_code(lines: list[str]):
    in_code = False
    for ln in lines:
        if ln.lstrip().startswith("```"):
            in_code = not in_code
            continue
        if not in_code:
            yield ln
