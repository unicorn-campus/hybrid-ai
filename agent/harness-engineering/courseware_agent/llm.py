"""Claude Agent SDK 호출 래퍼.

Claude Code CLI의 로그인 정보를 그대로 쓰므로 별도 API 키가 필요 없다.
모든 호출은 사용자/프로젝트 설정(CLAUDE.md 등)을 읽지 않는 격리 모드로 실행한다.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import Any

import anyio
from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKError,
    ResultMessage,
    ToolUseBlock,
    query,
)

from .config import Settings

log = logging.getLogger("courseware")


class LLMError(RuntimeError):
    pass


@dataclass
class LLMResult:
    text: str
    data: Any
    cost_usd: float
    turns: int
    seconds: float


class Ledger:
    """호출 횟수·비용 누계."""

    def __init__(self) -> None:
        self.calls = 0
        self.cost_usd = 0.0

    def add(self, cost: float | None) -> None:
        self.calls += 1
        self.cost_usd += cost or 0.0


ledger = Ledger()


async def ask(
    settings: Settings,
    prompt: str,
    *,
    system: str,
    schema: dict | None = None,
    tools: list[str] | None = None,
    max_turns: int = 8,
    label: str = "llm",
    retries: int = 3,
) -> LLMResult:
    """프롬프트를 보내고 결과(텍스트 또는 schema에 맞는 dict)를 돌려준다."""
    tools = tools or []
    options = ClaudeAgentOptions(
        model=settings.model,
        effort=settings.effort,
        system_prompt=system,
        tools=tools,
        allowed_tools=tools,
        setting_sources=[],
        max_turns=max_turns,
        cwd=str(settings.out_dir),
        output_format={"type": "json_schema", "schema": schema} if schema else None,
    )

    last_err: Exception | None = None
    for attempt in range(1, retries + 1):
        started = time.monotonic()
        try:
            result: ResultMessage | None = None
            tool_calls = 0
            with anyio.fail_after(settings.call_timeout_s):
                async for message in query(prompt=prompt, options=options):
                    if isinstance(message, AssistantMessage):
                        tool_calls += sum(isinstance(b, ToolUseBlock) for b in message.content)
                    elif isinstance(message, ResultMessage):
                        result = message
            if result is None:
                raise LLMError("ResultMessage를 받지 못함")
            if result.is_error:
                raise LLMError(f"{result.subtype}: {result.errors or result.result}")

            data = result.structured_output
            if schema is not None:
                if data is None and result.result:
                    data = _parse_json(result.result)
                if not isinstance(data, dict):
                    raise LLMError("구조화 출력이 비어 있음")
                _check_required(schema, data)

            elapsed = time.monotonic() - started
            ledger.add(result.total_cost_usd)
            log.info(
                "[%s] ok turns=%s tools=%s cost=$%.3f %.0fs",
                label, result.num_turns, tool_calls, result.total_cost_usd or 0.0, elapsed,
            )
            return LLMResult(result.result or "", data, result.total_cost_usd or 0.0, result.num_turns, elapsed)
        except (ClaudeSDKError, LLMError, TimeoutError, json.JSONDecodeError) as err:
            last_err = err
            log.warning("[%s] attempt %d/%d failed: %s", label, attempt, retries, str(err)[:300])
            if attempt < retries:
                await anyio.sleep(10 * attempt)
    raise LLMError(f"[{label}] {retries}회 시도 모두 실패: {last_err}")


def _parse_json(text: str) -> Any:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0]
    return json.loads(text)


def _check_required(schema: dict, data: dict) -> None:
    missing = [k for k in schema.get("required", []) if k not in data]
    if missing:
        raise LLMError(f"필수 필드 누락: {missing}")
