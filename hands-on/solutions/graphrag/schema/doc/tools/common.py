"""design-kg-schema-doc.md 실행용 공통 코드: 설정 읽기, 청크 읽기, LLM 호출, 응답 다듬기, 이름 정규화.

모든 스크립트는 `{base_dir}/decisions.json`(1단계 결정)을 읽어 같은 입력으로 돌아감.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any, Optional

from neo4j_graphrag.llm import LLMInterface, LLMResponse

BASE = Path(__file__).resolve().parent.parent


def load_json(name: str) -> Any:
    return json.loads((BASE / name).read_text(encoding="utf-8"))


def save_json(name: str, data: Any) -> None:
    path = BASE / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def decisions() -> dict:
    return load_json("decisions.json")


AUTO = "자동 승인(사용자 지시: 승인은 자동 승인 처리, 2026-10-18)"


def record(step: str, content: Any, judge: str = AUTO) -> None:
    """decisions.json의 steps에 결정 하나를 덧붙임(같은 단계를 다시 돌리면 판 번호를 올려 남김)."""

    d = decisions()
    steps = d.setdefault("steps", [])
    rev = sum(1 for s in steps if s["step"] == step) + 1
    steps.append({"step": step, "rev": rev, "judge": judge, "date": time.strftime("%Y-%m-%d %H:%M"),
                  "content": content})
    save_json("decisions.json", d)


def load_chunks() -> list[dict]:
    """1단계에서 승인된 청크 파일과 본문 칸으로 청크를 읽음."""

    d = decisions()["input"]
    data = json.loads(Path(d["chunk_file"]).read_text(encoding="utf-8"))
    rows = data if isinstance(data, list) else next(v for v in data.values() if isinstance(v, list))
    out = []
    for r in rows:
        md = r.get("metadata", {})
        out.append({"id": r.get("chunk_id"), "text": r[d["text_field"]], "metadata": md,
                    "doc_type": md.get(d["doc_type_field"])})
    return out


def _split_by_heading(chunk: dict, rule: dict) -> list[dict]:
    """청크 본문을 제목 줄(예: '제16조(할부 거래)') 경계로 나눔.

    제목 줄 바로 다음 줄이 본문 시작 표시(예: '①')로 시작할 때만 단위의 시작으로 봄. 차례(목차)처럼 제목만 이어지는 줄은
    단위가 되지 않음. 첫 제목 앞의 글(앞 청크에서 이어진 조각)은 버림. 겹침 구간에서 같은 단위가 다시 나오면 load_units가 합침.
    """

    heading, drop = re.compile(rule["heading"]), re.compile(rule["drop_lines"]) if rule.get("drop_lines") else None
    lines = chunk["text"].split("\n")
    nxt = lambda i: next((l.strip() for l in lines[i + 1:] if l.strip()), "")
    starts = [i for i, l in enumerate(lines) if heading.match(l.strip()) and nxt(i).startswith(rule["body_start"])]
    units = []
    for k, i in enumerate(starts):
        end = starts[k + 1] if k + 1 < len(starts) else len(lines)
        body = [l for l in lines[i:end] if not (drop and drop.match(l.strip()))]
        m = heading.match(lines[i].strip())
        md = {**chunk["metadata"], "unit_no": m.group(1), "unit_title": m.group(2), "section_label": lines[i].strip()}
        units.append({"id": f"{chunk['doc_type']}:{m.group(1)}", "text": "\n".join(body).strip(), "metadata": md,
                      "doc_type": chunk["doc_type"], "parent_chunk_ids": [chunk["id"]]})
    return units


def split_chunks(chunks: list[dict], rule: dict) -> list[dict]:
    """주어진 청크만 단위로 나눔. 겹침 구간 때문에 같은 단위가 두 청크에 나오면 글이 가장 긴 것 하나만 남기고
    원래 청크 ID는 모두 parent_chunk_ids에 모음(인덱싱 때 검색 청크와 잇는 데 씀)."""

    merged: dict[str, dict] = {}
    for c in chunks:
        for u in _split_by_heading(c, rule):
            old = merged.get(u["id"])
            if old is None:
                merged[u["id"]] = u
            else:
                parents = old["parent_chunk_ids"] + u["parent_chunk_ids"]
                merged[u["id"]] = {**(u if len(u["text"]) > len(old["text"]) else old), "parent_chunk_ids": parents}
    return list(merged.values())


def load_units() -> list[dict]:
    """4 ~ 8단계가 쓰는 표본 단위. 규칙이 없는 문서 종류는 청크 그대로, 규칙이 있는 문서 종류는 3단계가 표본 청크만
    나눠 저장한 `{doc}/units.json`을 읽음(문서 전체를 나누지 않음)."""

    rules = decisions()["input"].get("extraction_units", {})
    out = [c for c in load_chunks() if c["doc_type"] not in rules]
    for doc in rules:
        path = BASE / doc / "units.json"
        if path.exists():
            out += json.loads(path.read_text(encoding="utf-8"))
    return out


def read_secret(path: str, name: str) -> str:
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip().startswith(f"{name}="):
            value = line.split("=", 1)[1].strip().strip('"').strip("'")
            if value:
                return value
    raise SystemExit(f"비밀값 파일에 {name} 값이 없음")


def key(label: str) -> str:
    """대소문자, 띄어쓰기, 밑줄 차이를 없앤 이름(같은 이름 판정용)."""

    return re.sub(r"[^0-9a-z가-힣]", "", str(label).lower())


class ChatLLM(LLMInterface):
    """OpenAI 호환 채팅 API(Groq 등)를 표준 라이브러리로 부르는 LLM. JSON 모드, 429와 5xx 재시도, 호출 전체 마감."""

    URLS = {"groq": "https://api.groq.com/openai/v1/chat/completions"}

    def __init__(self, provider: str, model_name: str, api_key: str, deadline: float = 240.0) -> None:
        super().__init__(model_name=model_name)
        self._url, self._key, self._deadline = self.URLS[provider], api_key, deadline
        self.usage = Counter()

    def _post(self, body: bytes) -> dict:
        req = urllib.request.Request(self._url, data=body, headers={
            "Authorization": f"Bearer {self._key}", "Content-Type": "application/json; charset=utf-8",
            "User-Agent": "kg-schema-doc/1.0"})
        with urllib.request.urlopen(req, timeout=90) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def invoke(self, input: str, message_history: Optional[Any] = None,
               system_instruction: Optional[str] = None) -> LLMResponse:
        messages = ([{"role": "system", "content": system_instruction}] if system_instruction else [])
        messages.append({"role": "user", "content": input})
        body = {"model": self.model_name, "messages": messages, "response_format": {"type": "json_object"},
                "temperature": 0}
        if "gpt-oss" in self.model_name:  # 추론 글은 받지 않음(응답 칸만 JSON으로)
            body.update(include_reasoning=False, reasoning_effort="medium")
        raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
        for attempt in range(6):
            try:
                payload = self._post(raw)
                for k, v in (payload.get("usage") or {}).items():
                    if isinstance(v, (int, float)):
                        self.usage[k] += v
                return LLMResponse(content=payload["choices"][0]["message"]["content"])
            except urllib.error.HTTPError as e:
                detail = e.read()[:300]
                if e.code == 400 and b"json_validate_failed" in detail and attempt < 2:
                    continue  # JSON 모드에서 모델이 가끔 빈 글을 내 400이 남. 같은 입력을 다시 부르면 대개 풀림
                if e.code != 429 and e.code < 500:
                    raise RuntimeError(f"HTTP {e.code}: {detail!r}") from e
                time.sleep(min(float(e.headers.get("retry-after") or 0) or 5 * 2 ** attempt, 90))
        raise RuntimeError("LLM 재시도 6회 모두 실패")

    async def ainvoke(self, input: str, message_history: Optional[Any] = None,
                      system_instruction: Optional[str] = None) -> LLMResponse:
        return await asyncio.wait_for(asyncio.to_thread(self.invoke, input, message_history, system_instruction),
                                      timeout=self._deadline)


class GraphSafeLLM(ChatLLM):
    """추출 응답을 그래프 꼴(nodes, relationships)에 맞게 다듬음: 정해진 칸 밖 키 제거, id는 글자, 빈 속성 제거."""

    @staticmethod
    def _value(v):
        if v is None:
            return None
        if isinstance(v, (str, int, float, bool)):
            return v
        if isinstance(v, list) and all(isinstance(x, (str, int, float, bool)) for x in v):
            return v
        return json.dumps(v, ensure_ascii=False)

    def _clean(self, content: str) -> str:
        try:
            d = json.loads(content)
        except json.JSONDecodeError:
            return content
        props = lambda o: {k: self._value(v) for k, v in (o.get("properties") or {}).items() if self._value(v) is not None}
        nodes = [{"id": str(n.get("id")), "label": str(n.get("label")), "properties": props(n)}
                 for n in d.get("nodes", []) if isinstance(n, dict)]
        rels = [{"type": str(r.get("type")), "start_node_id": str(r.get("start_node_id")),
                 "end_node_id": str(r.get("end_node_id")), "properties": props(r)}
                for r in d.get("relationships", []) if isinstance(r, dict)]
        return json.dumps({"nodes": nodes, "relationships": rels}, ensure_ascii=False)

    async def ainvoke(self, input, message_history=None, system_instruction=None):
        res = await super().ainvoke(input, message_history, system_instruction)
        res.content = self._clean(res.content)
        return res


def make_llm(graph_safe: bool = False) -> ChatLLM:
    d = decisions()["input"]
    cls = GraphSafeLLM if graph_safe else ChatLLM
    return cls(d["llm_provider"], d["llm_model"], read_secret(d["secret_file"], d["secret_key_name"]))


def cq_text(doc: str) -> str:
    qs = load_json("competency_questions.json")[doc]
    return ("Competency questions: design node types, relationship types and properties so that a graph built with "
            "this schema can answer the following questions about documents like the input text.\n"
            + "\n".join(f"{q['id']}. {q['question']}" for q in qs))
