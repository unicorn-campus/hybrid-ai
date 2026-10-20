from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage

from app.infrastructure import prompt_loader
from app.infrastructure.prompt_loader import (
    build_chat_prompt,
    explain_prompt,
    load_system_prompt,
    plan_prompt,
)


PROMPTS = Path(__file__).resolve().parents[1] / "app" / "prompts"


def test_plan_prompt_puts_document_in_system_message_and_binds_request():
    messages = plan_prompt().invoke({"request": "<질문>"}).to_messages()

    assert isinstance(messages[0], SystemMessage)
    assert messages[0].content == (PROMPTS / "search_plan.md").read_text(encoding="utf-8")
    assert isinstance(messages[1], HumanMessage)
    assert messages[1].content == "<request><질문></request>"


def test_explain_prompt_puts_document_in_system_message_and_binds_payload():
    messages = explain_prompt().invoke({"payload": "{}"}).to_messages()

    assert isinstance(messages[0], SystemMessage)
    assert messages[0].content == (PROMPTS / "explain_result.md").read_text(encoding="utf-8")
    assert messages[1].content == "<input>{}</input>"


def test_system_document_braces_are_not_treated_as_template_variables(tmp_path, monkeypatch):
    monkeypatch.setattr(prompt_loader, "PROMPTS", tmp_path)
    load_system_prompt.cache_clear()
    build_chat_prompt.cache_clear()
    document = '예시 {"query_mode": "fixed"} 를 반환함.'
    (tmp_path / "brace_sample.md").write_text(document, encoding="utf-8")

    prompt = build_chat_prompt("brace_sample", "<request>{request}</request>")
    messages = prompt.invoke({"request": "질문"}).to_messages()

    assert prompt.input_variables == ["request"]
    assert messages[0].content == document

    load_system_prompt.cache_clear()
    build_chat_prompt.cache_clear()


def test_documents_are_read_once_and_prompts_are_reused():
    load_system_prompt.cache_clear()
    build_chat_prompt.cache_clear()

    assert plan_prompt() is plan_prompt()
    assert load_system_prompt.cache_info().misses == 1
