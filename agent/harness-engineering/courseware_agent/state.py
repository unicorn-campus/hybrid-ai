"""재시작 가능한 작업 상태(state.json)."""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

import anyio


class State:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.lock = anyio.Lock()
        self.data: dict[str, Any] = {
            "topic": None,
            "research": None,      # {"brief_path", "sources": [...]}
            "plan": None,          # 커리큘럼 JSON
            "chapters": {},        # id -> 진행 상태
            "course_reviews": [],
            "events": [],
        }
        if path.exists():
            self.data.update(json.loads(path.read_text(encoding="utf-8")))

    @property
    def chapters(self) -> dict[str, dict]:
        return self.data["chapters"]

    def chapter(self, cid: str) -> dict:
        return self.chapters.setdefault(cid, {
            "text_status": "pending",    # pending → drafted → approved
            "slide_status": "pending",   # pending → drafted → approved → rendered
            "text_reviews": [],
            "slide_reviews": [],
        })

    def event(self, message: str) -> None:
        self.data["events"].append({"at": datetime.now().isoformat(timespec="seconds"), "msg": message})

    def save(self) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, self.path)
