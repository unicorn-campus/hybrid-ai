"""프롬프트 문서를 읽어 게이트웨이가 함께 쓰는 대화 프롬프트로 만듭니다."""

from functools import lru_cache
from pathlib import Path

from langchain_core.messages import SystemMessage
from langchain_core.prompts import ChatPromptTemplate

PROMPTS = Path(__file__).resolve().parents[1] / "prompts"

PLAN_HUMAN_TEMPLATE = "<request>{request}</request>"
EXPLAIN_HUMAN_TEMPLATE = "<input>{payload}</input>"


@lru_cache(maxsize=None)
def load_system_prompt(name: str) -> str:
    """app/prompts/{name}.md 내용을 한 번만 읽고 재사용합니다."""
    return (PROMPTS / f"{name}.md").read_text(encoding="utf-8")


@lru_cache(maxsize=None)
def build_chat_prompt(name: str, human_template: str) -> ChatPromptTemplate:
    """시스템 문서는 치환하지 않는 고정 메시지로, 사람 메시지만 템플릿으로 구성합니다."""
    return ChatPromptTemplate.from_messages([
        SystemMessage(content=load_system_prompt(name)),
        ("human", human_template),
    ])


def plan_prompt() -> ChatPromptTemplate:
    """검색 계획 생성용 프롬프트입니다. 사람 메시지 변수는 request입니다."""
    return build_chat_prompt("search_plan", PLAN_HUMAN_TEMPLATE)


def explain_prompt() -> ChatPromptTemplate:
    """결과 설명용 프롬프트입니다. 사람 메시지 변수는 payload입니다."""
    return build_chat_prompt("explain_result", EXPLAIN_HUMAN_TEMPLATE)
