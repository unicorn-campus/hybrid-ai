"""LLM 연결: Groq 모델을 neo4j-graphrag의 추출기가 부르는 LLMInterface 모양으로 감쌈.

모델과 비밀값 파일 경로는 decisions.json의 input에서 읽음(1단계에서 승인된 값). 키 값은 화면이나 파일에 남기지 않음.
"""

from __future__ import annotations

import asyncio
import threading

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_groq import ChatGroq
from neo4j_graphrag.llm import LLMInterface, LLMResponse

from common import REPO_ROOT, load_decisions, read_secret

LLM_TIMEOUT = 120  # 호출 한 번의 제한 시간(초)


class GroqLLM(LLMInterface):
    """추출기는 invoke(프롬프트) → LLMResponse(content=JSON 글)만 필요로 함. 호출 제한(429)과 5xx는 ChatGroq가 다시 부름."""

    def __init__(self, model_name: str, api_key: str, tidy=None, effort: str = "medium", max_tokens: int | None = None,
                 json_mode: bool = True) -> None:
        super().__init__(model_name=model_name)
        # max_tokens: Groq gpt-oss의 기본 출력 한도는 3,072토큰이라 추론이 길면 본문이 비고 「JSON 검증 실패」가 남(2026-11-18 실측)
        self.chat = ChatGroq(model=model_name, api_key=api_key, temperature=0, max_retries=6,
                             request_timeout=LLM_TIMEOUT, reasoning_effort=effort, max_tokens=max_tokens,
                             model_kwargs={"response_format": {"type": "json_object"}} if json_mode else {})
        self.tidy = tidy  # 응답 글을 다듬는 함수(채우기 시험에서 그래프 꼴로 맞출 때 씀)
        self.usage = {"calls": 0, "total_tokens": 0}
        self._lock = threading.Lock()

    def chat_json(self, prompt: str, system: str | None = None) -> str:
        messages = ([SystemMessage(content=system)] if system else []) + [HumanMessage(content=prompt)]
        response = self.chat.invoke(messages)
        content = response.content
        if isinstance(content, list):  # 일부 모델은 조각 목록으로 줌
            content = "".join(part if isinstance(part, str) else part.get("text", "") for part in content)
        with self._lock:
            self.usage["calls"] += 1
            self.usage["total_tokens"] += int((response.usage_metadata or {}).get("total_tokens", 0))
        return content

    def invoke(self, input: str, message_history=None, system_instruction=None) -> LLMResponse:
        content = self.chat_json(input, system_instruction)
        return LLMResponse(content=self.tidy(content) if self.tidy else content)

    async def ainvoke(self, input: str, message_history=None, system_instruction=None) -> LLMResponse:
        return await asyncio.to_thread(self.invoke, input, message_history, system_instruction)


def make_llm(tidy=None, effort: str = "medium", max_tokens: int | None = None, json_mode: bool = True) -> GroqLLM:
    conf = load_decisions()["input"]
    key = read_secret(REPO_ROOT / conf["secret_file"], conf["secret_key_name"])
    return GroqLLM(conf["llm_model"], key, tidy, effort, max_tokens, json_mode)
