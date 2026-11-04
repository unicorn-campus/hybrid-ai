"""에이전트 실행 설정."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path


SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

_INITIALS = ["g", "kk", "n", "d", "tt", "r", "m", "b", "pp", "s", "ss", "", "j", "jj", "ch", "k", "t", "p", "h"]
_MEDIALS = ["a", "ae", "ya", "yae", "eo", "e", "yeo", "ye", "o", "wa", "wae", "oe", "yo", "u", "wo", "we", "wi",
            "yu", "eu", "ui", "i"]
_FINALS = ["", "k", "k", "k", "n", "n", "n", "t", "l", "k", "m", "l", "l", "l", "p", "l", "m", "p", "p", "t", "t",
           "ng", "t", "t", "k", "t", "p", "t"]


def romanize(text: str) -> str:
    """한글 음절을 로마자로 옮긴다(국어의 로마자 표기법을 단순화). 그 밖의 글자는 그대로 둔다."""
    out = []
    for ch in text:
        code = ord(ch) - 0xAC00
        if 0 <= code < 11172:
            out.append(_INITIALS[code // 588] + _MEDIALS[(code % 588) // 28] + _FINALS[code % 28])
        else:
            out.append(ch)
    return "".join(out)


def slugify(text: str) -> str:
    """디렉토리 이름에 쓰는 영문 kebab-case 슬러그. 한글은 로마자로 바꾼다(영문 번역 슬러그가 없을 때의 대안)."""
    slug = re.sub(r"[^a-z0-9]+", "-", romanize(text).lower()).strip("-")
    return slug[:48].strip("-") or "topic"


@dataclass
class Settings:
    topic: str
    out_dir: Path
    audience: str = "이 주제를 처음 체계적으로 배우려는 실무자(개발자, 기획자, 관리자)"
    scope: str = ""                  # 주제 범위(무엇을 다루고 무엇을 다루지 않는지)
    language: str = "한국어"
    model: str = field(default_factory=lambda: os.environ.get("COURSEWARE_MODEL", "claude-opus-5-5"))
    effort: str = "high"
    min_chapters: int = 6
    max_chapters: int = 12
    pass_score: float = 8.0          # LLM 리뷰 통과 기준(10점 만점)
    max_revisions: int = 3           # 장/슬라이드별 최대 수정 횟수
    max_course_reviews: int = 2      # 과정 전체 검토(누락 주제 보강) 반복 횟수
    concurrency: int = 3             # 동시에 작업할 장 수
    min_chapter_chars: int = 6000    # 장 본문 최소 글자 수(공백 포함)
    call_timeout_s: int = 1500       # LLM 호출 1회 제한 시간
    text_only: bool = False          # 본문만 만들고 슬라이드와 과정 검토는 건너뜀
    self_improve: bool = True        # RSI: 실행 기록으로 자기 하네스를 고침
    improve_every: int = 3           # 검토 루프 몇 번마다 자기 개선을 시도할지

    @property
    def research_dir(self) -> Path:
        return self.out_dir / "research"

    @property
    def textbook_dir(self) -> Path:
        return self.out_dir / "textbook"

    @property
    def slides_dir(self) -> Path:
        return self.out_dir / "slides"

    @property
    def reviews_dir(self) -> Path:
        return self.out_dir / "reviews"

    @property
    def logs_dir(self) -> Path:
        return self.out_dir / "logs"

    @property
    def state_path(self) -> Path:
        return self.out_dir / "state.json"

    def ensure_dirs(self) -> None:
        for d in (self.research_dir, self.textbook_dir, self.slides_dir, self.reviews_dir, self.logs_dir):
            d.mkdir(parents=True, exist_ok=True)
