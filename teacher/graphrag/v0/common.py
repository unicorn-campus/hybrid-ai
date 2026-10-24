"""여러 파일이 함께 쓰는 작은 도구: JSON 읽고 쓰기, 해시, 문서 키, 임베더, LLM."""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import os
import threading
import time
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any, Optional

from neo4j_graphrag.llm import LLMInterface, LLMResponse

import config


def load_json(path: Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def save_json(path: Path, data: Any) -> None:
    """임시 파일에 다 쓴 뒤 바꿔 끼움. 쓰다가 멈춰도 반쯤 쓴 파일이 남지 않게 함."""

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, path)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def doc_id_of(chunk_id: str) -> str:
    """chunk_id = {문서 키}_{본문 해시 16}_{같은 본문 반복 번호 4}. 뒤 두 칸을 떼면 문서 키."""

    return str(chunk_id).rsplit("_", 2)[0]


def index_text_of(chunk: dict) -> str:
    """임베딩과 키워드 분석에 쓰는 색인용 본문(머리말이 있으면 머리말 포함)."""

    return str(chunk.get("index_text") or chunk["text"])


def log(message: str) -> None:
    print(time.strftime("%H:%M:%S"), message, flush=True)


# ---------------------------------------------------------------- 임베더(S1, K6가 함께 씀)

_embedder = None
_embedder_lock = threading.Lock()


def _load_embedder():
    """KURE-v2를 고정 revision으로 Hugging Face 캐시에서만 읽어 올림(내려받지 않음). 출력 차원이 설정과 다르면 멈춤.

    출처: hybrid-ai-lab indexer/vector-bm25의 HuggingFaceEmbedder(2026-10-24)에서 v0가 쓰던 설정만 옮김.
    """

    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(config.EMBED_MODEL, revision=config.EMBED_REVISION, local_files_only=True,
                                device="cpu")
    model.max_seq_length = config.EMBED_MAX_SEQ_LENGTH
    getter = getattr(model, "get_embedding_dimension", None) or model.get_sentence_embedding_dimension
    if getter() != config.EMBED_DIMENSION:
        raise SystemExit(f"임베딩 차원이 설정과 다름: {getter()} != {config.EMBED_DIMENSION}")
    return model


def embed(texts: list[str]) -> list[list[float]]:
    """KURE-v2로 임베딩함. 모델은 처음 부를 때 한 번만 올림(두 서브 워크플로우가 함께 씀).

    KURE-v2의 단일 벡터 변환은 normalize_embeddings=True여도 길이가 약 0.997 ~ 1.003이라 float로 다시 정규화함.
    """

    global _embedder
    if not texts:
        return []
    with _embedder_lock:
        if _embedder is None:
            _embedder = _load_embedder()
        rows = _embedder.encode(texts, batch_size=8, normalize_embeddings=True, show_progress_bar=False).tolist()
    out = []
    for row in rows:
        norm = math.sqrt(sum(v * v for v in row))
        if not math.isfinite(norm) or norm <= 0:
            raise ValueError("임베딩 벡터 길이가 0이거나 숫자가 아님")
        out.append([v / norm for v in row])
    return out


# ---------------------------------------------------------------- LLM(K2)

def read_secret(name: str) -> str:
    for line in config.SECRET_FILE.read_text(encoding="utf-8").splitlines():
        if line.strip().startswith(f"{name}="):
            value = line.split("=", 1)[1].strip().strip('"').strip("'")
            if value:
                return value
    raise SystemExit(f"비밀값 파일에 {name} 값이 없음")


class GroqLLM(LLMInterface):
    """Groq(OpenAI 호환 채팅 API)를 표준 라이브러리로 부르는 LLM. JSON 모드, 429와 5xx 재시도, 호출 전체 마감 시간."""

    URL = "https://api.groq.com/openai/v1/chat/completions"

    def __init__(self, model_name: str, api_key: str, deadline: float = 240.0) -> None:
        super().__init__(model_name=model_name)
        self._key, self._deadline = api_key, deadline
        self.usage: Counter = Counter()

    def _post(self, body: bytes) -> dict:
        req = urllib.request.Request(self.URL, data=body, headers={
            "Authorization": f"Bearer {self._key}", "Content-Type": "application/json; charset=utf-8",
            "User-Agent": "graphrag-v0/1.0"})
        with urllib.request.urlopen(req, timeout=90) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def invoke(self, input: str, message_history: Optional[Any] = None,
               system_instruction: Optional[str] = None) -> LLMResponse:
        return LLMResponse(content=self._clean(self.chat_json(input, system_instruction)))

    def chat_json(self, input: str, system_instruction: Optional[str] = None) -> str:
        """JSON 모드로 한 번 묻고 응답 글을 그대로 돌려줌(그래프 꼴로 다듬지 않음).

        K2 추출은 invoke가 이 글을 그래프 꼴로 다듬어 쓰고, K8 커뮤니티 요약은 보고서 JSON을 그대로 씀.
        예외: 4xx(429 제외)는 바로 RuntimeError, 429와 5xx는 6번까지 기다렸다 다시 부른 뒤 RuntimeError.
        부수효과: 응답의 토큰 사용량을 self.usage에 더함.
        """

        messages = ([{"role": "system", "content": system_instruction}] if system_instruction else [])
        messages.append({"role": "user", "content": input})
        body = {"model": self.model_name, "messages": messages, "response_format": {"type": "json_object"},
                "temperature": 0}
        if "gpt-oss" in self.model_name:  # 추론 글은 받지 않고 답 칸만 JSON으로 받음
            body.update(include_reasoning=False, reasoning_effort="medium")
        raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
        for attempt in range(6):
            try:
                payload = self._post(raw)
                for k, v in (payload.get("usage") or {}).items():
                    if isinstance(v, (int, float)):
                        self.usage[k] += v
                return payload["choices"][0]["message"]["content"]
            except urllib.error.HTTPError as e:
                detail = e.read()[:300]
                if e.code == 400 and b"json_validate_failed" in detail and attempt < 2:
                    continue  # JSON 모드에서 가끔 빈 글이 나와 400이 남. 같은 입력으로 다시 부르면 대개 풀림
                if e.code != 429 and e.code < 500:
                    raise RuntimeError(f"HTTP {e.code}: {detail!r}") from e
                time.sleep(min(float(e.headers.get("retry-after") or 0) or 5 * 2 ** attempt, 90))
        raise RuntimeError("LLM 재시도 6회 모두 실패")

    async def ainvoke(self, input: str, message_history: Optional[Any] = None,
                      system_instruction: Optional[str] = None) -> LLMResponse:
        return await asyncio.wait_for(asyncio.to_thread(self.invoke, input, message_history, system_instruction),
                                      timeout=self._deadline)

    @staticmethod
    def _clean(content: str) -> str:
        """응답을 그래프 꼴로 다듬음: 정해진 칸 밖 키 제거, id는 글자, 빈 속성 제거. 사소한 형식 차이로 버려지지 않게 함."""

        try:
            d = json.loads(content)
        except json.JSONDecodeError:
            return content

        def value(v):
            if v is None or isinstance(v, (str, int, float, bool)):
                return v
            if isinstance(v, list) and all(isinstance(x, (str, int, float, bool)) for x in v):
                return v
            return json.dumps(v, ensure_ascii=False)

        props = lambda o: {k: value(v) for k, v in (o.get("properties") or {}).items() if value(v) is not None}
        nodes = [{"id": str(n.get("id")), "label": str(n.get("label")), "properties": props(n)}
                 for n in d.get("nodes", []) if isinstance(n, dict)]
        rels = [{"type": str(r.get("type")), "start_node_id": str(r.get("start_node_id")),
                 "end_node_id": str(r.get("end_node_id")), "properties": props(r)}
                for r in d.get("relationships", []) if isinstance(r, dict)]
        return json.dumps({"nodes": nodes, "relationships": rels}, ensure_ascii=False)


def make_llm() -> GroqLLM:
    return GroqLLM(config.LLM_MODEL, read_secret("GROQ_API_KEY"))
