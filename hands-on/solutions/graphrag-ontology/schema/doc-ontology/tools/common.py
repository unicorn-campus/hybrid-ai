"""KG 스키마 설계(온톨로지 판) 도구들이 함께 쓰는 경로와 기록 함수.

프롬프트 `prompts/design-kg-schema-doc-ontology.md`의 1 ~ 9단계 스크립트가 이 파일을 불러 씀.
- 경로: 저장소 루트와 출력 기준 폴더(base_dir)
- 파일: JSON 읽기와 쓰기, SHA-256 값 계산
- 기록: decisions.json에 승인 기록을 덧붙임
- 비밀값: 비밀값 파일에서 키를 읽음(값은 화면이나 파일에 남기지 않음)
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import date
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent  # 출력 기준 폴더(schema/doc-ontology)
REPO_ROOT = BASE_DIR.parents[4]  # 저장소 루트(hybrid-ai)
DECISIONS_PATH = BASE_DIR / "decisions.json"
SNAPSHOT_PATH = BASE_DIR / "chunks_snapshot.json"
DOC_TYPES = ["regulation", "benefit_guide", "consult_log"]
SEED = 20261118  # 표본을 고를 때 쓰는 고정 시드(다시 돌려도 같은 표본이 나오게 함)

if hasattr(sys.stdout, "reconfigure"):  # Windows 콘솔에서 한글이 깨지지 않게 함
    sys.stdout.reconfigure(encoding="utf-8")


def rel(path: Path | str) -> str:
    """저장소 루트 기준 상대 경로 글자를 돌려줌(기록에 절대 경로를 남기지 않기 위함)."""
    return Path(path).resolve().relative_to(REPO_ROOT).as_posix()


def read_json(path: Path | str):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path: Path | str, data) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def sha256_of(path: Path | str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_decisions() -> dict:
    if DECISIONS_PATH.exists():
        return read_json(DECISIONS_PATH)
    return {"prompt": "prompts/design-kg-schema-doc-ontology.md", "input": {}, "steps": []}


def record_step(step: str, title: str, content: dict, review: str | None = None,
                user_answer: str | None = None, judge: str = "hiondal(사용자)") -> None:
    """decisions.json의 steps에 기록 하나를 덧붙임.

    review가 있으면 승인 기록으로 보고 검토 파일 경로와 SHA-256 값, 사용자 답 원문을 함께 남김.
    """
    decisions = load_decisions()
    entry = {"step": step, "title": title, "date": date.today().isoformat(), "content": content}
    if review:
        review_path = BASE_DIR / review
        entry["approval"] = {
            "judge": judge,
            "review_file": rel(review_path),
            "review_sha256": sha256_of(review_path),
            "user_answer": user_answer,
        }
    decisions["steps"].append(entry)
    write_json(DECISIONS_PATH, decisions)


def read_secret(env_path: Path | str, key_name: str) -> str:
    """비밀값 파일에서 키 하나를 읽음. 없거나 비어 있으면 오류를 냄(값은 출력하지 않음)."""
    for line in Path(env_path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        if name.strip() == key_name:
            value = value.strip().strip("\"'")
            if value:
                return value
    raise RuntimeError(f"비밀값 파일에 {key_name} 값이 없음: {env_path}")


def load_chunks(doc_type: str | None = None) -> list[dict]:
    """1단계에서 저장한 사본에서 청크를 읽음. 2 ~ 9단계는 벡터DB를 다시 열지 않고 이 함수만 씀."""
    chunks = read_json(SNAPSHOT_PATH)["chunks"]
    if doc_type:
        chunks = [c for c in chunks if c["metadata"].get("doc_type") == doc_type]
    return chunks
