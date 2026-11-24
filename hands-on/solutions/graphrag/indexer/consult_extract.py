"""K2 상담 기록 추출(consult_log 전용): 상담 원문 하나를 스키마(schema/doc/consult_log/graph_schema.json) 모양의 그래프로 뽑음.

다른 문서 유형은 core.extract_one(LLM이 글 전체를 읽고 노드와 관계를 자유롭게 뽑음)을 그대로 씀. 상담은 그 방식이
확인 질문까지 제안으로 잡아 제안 결정 일치가 22/48에 그쳐서, 「코드가 찾고 LLM은 분류만, 인용은 원문 대조」로 바꿈
(실험: research/global-search-experiment-20261124, 검색 README 7.8).

- 코드가 읽음: 머리줄 칸(record_id, consult_date, channel, member_pseudo_id), [상담주제] 줄(topic),
  다른 상담 ID 언급(FOLLOWS), 제안 후보(물음표가 있는 상담사 말 + 바로 뒤 고객 답)
- LLM이 채움(구조화 출력): 상담 요약·후속 안내 방식·불만 여부와 인용, 후보마다 「제안인가·결정·이유」,
  보류면 이어진 고객 말에서 재검토 조건
- 코드가 검증: 인용은 원문에 글자 그대로 있어야 씀(공백 무시). 불만 인용이 어긋나면 가장 비슷한 고객 줄을 그대로 씀
결과는 core.extract_one과 같은 꼴({"graph", "raw_nodes", "kept_nodes"})이라 K3 ~ K8은 그대로 돎.
"""

import asyncio
import re
from difflib import SequenceMatcher
from typing import Literal

from langchain_core.prompts import ChatPromptTemplate
from langchain_groq import ChatGroq
from neo4j_graphrag.components.graph_pruning import GraphPruning
from neo4j_graphrag.components.types import Neo4jGraph, Neo4jNode, Neo4jRelationship
from pydantic import BaseModel, Field

EXTRACTOR_VERSION = "consult-v1"  # 방법이나 프롬프트를 바꾸면 올려야 앞 세대 추출을 다시 쓰지 않음
RECORD_ID = re.compile(r"C-\d{8}-\d{3}")


class RecordFields(BaseModel):
    # 칸 이름, 설명, 순서와 프롬프트는 실험에서 불만 여부 47/48이 나온 것과 같게 둠
    # (고객 줄에 번호를 붙이거나 불만 정의를 늘리면 40 ~ 44/48로 떨어졌음, 2026-11-24 실측)
    is_complaint: bool = Field(description="고객이 불만·불편을 말했으면 true, 일반 문의면 false")
    complaint_quote: str = Field(description="불만 원인을 나타내는 고객 발화 원문 그대로(없으면 빈 글)")
    complaint_summary: str = Field(description="불만 요약(없으면 빈 글)")
    topic_summary: str = Field(description="상담 내용 한 줄 요약")
    contact_preference: str = Field(description="고객이 원한 후속 안내 방식(예: 오전 전화, 이메일 요약)")


class PairJudge(BaseModel):
    pair_no: int = Field(description="쌍 번호")
    is_proposal: bool = Field(description="상담사가 고객에게 무언가를 해 보라고 권하거나 해 주겠다고 제안한 것이면 true, "
                                          "단순히 상황을 묻는 질문이면 false")
    decision: Literal["수용", "거절", "보류", "해당없음"] = Field(description="고객 답으로 정한 반응. 제안이 아니면 해당없음")
    reason_quote: str = Field(description="고객 답에서 이유를 밝힌 부분 원문 그대로(없으면 빈 글)")


class PairsOut(BaseModel):
    pairs: list[PairJudge] = Field(description="쌍마다 하나")


class HoldCondition(BaseModel):
    condition_quote: str = Field(description="다시 검토하겠다는 조건이 담긴 고객 말 원문 그대로(없으면 빈 글)")


RECORD_PROMPT = ChatPromptTemplate.from_messages([
    ("system", "너는 상담 기록을 구조화하는 분석가다. 원문에 있는 것만 채우고, *_quote 칸은 원문을 글자 그대로 옮긴다. "
               "불만은 고객이 겪는 불편·불만의 원인을 말한 것이고, 단순 문의나 요청은 불만이 아니다."),
    ("human", "{doc}"),
])
PAIR_PROMPT = ChatPromptTemplate.from_messages([
    ("system", "너는 상담 기록의 「상담사 질문 → 고객 답」 쌍을 분류한다. 상담사가 고객에게 어떤 행동, 서비스, 설정을 권하거나 "
               "해 주겠다고 한 것만 제안이다(예: 「~해 보시는 건 어떠세요?」, 「~해 드릴까요?」). 상황을 묻는 질문은 제안이 아니다. "
               "결정은 고객 답으로만 정한다: 받아들이면 수용, 싫다거나 안 하겠다면 거절, 지금 정하지 않고 나중에 정하겠다면 보류. "
               "주의: 한국어 「~은 괜찮아요」, 「~은 됐어요」, 「~까지는 안 할게요」는 제안을 사양하는 말이라 거절이다. "
               "고객 답이 그 제안에 대한 대답이 아니라 다른 요청이나 이야기만 하면 결정은 해당없음이다. "
               "*_quote는 고객 답의 글자를 그대로 옮긴다."),
    ("human", "{pairs}"),
])
HOLD_PROMPT = ChatPromptTemplate.from_messages([
    ("system", "고객이 상담사 제안을 보류했다. 고객 말 중 「언제, 무엇을 보고 다시 정하겠다」는 재검토 조건을 글자 그대로 옮긴다. "
               "없으면 빈 글."),
    ("human", "제안: {proposal}\n고객 말:\n{lines}"),
])

_chains = None


def chains(api_key: str):
    """구조화 출력 체인 3개를 한 번만 만듦(K2 스레드들이 함께 씀). 모델은 인덱서의 다른 LLM 호출과 같음."""
    global _chains
    if _chains is None:
        llm = ChatGroq(model="openai/gpt-oss-120b", api_key=api_key, temperature=0, max_retries=6, request_timeout=90,
                       reasoning_effort="medium")

        def so(schema):
            return llm.with_structured_output(schema, method="json_schema", strict=True)

        _chains = (RECORD_PROMPT | so(RecordFields), PAIR_PROMPT | so(PairsOut), HOLD_PROMPT | so(HoldCondition))
    return _chains


def norm(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


def invoke_retry(chain, args: dict, retries: int):
    last = None
    for _ in range(retries + 1):
        try:
            return chain.invoke(args)
        except Exception as error:  # 구조화 출력 검증 실패(400)나 호출 실패는 같은 입력으로 다시 물음
            last = error
    raise last


def dialogue(text: str) -> list[tuple[str, str]]:
    """대화 줄만 [(화자, 말)]로. 화자는 「고객」 또는 「상담사」."""
    out = []
    for line in text.splitlines():
        line = line.strip()
        for who in ("고객", "상담사"):
            if line.startswith(who + ":"):
                out.append((who, line[len(who) + 1:].strip()))
    return out


def proposal_candidates(lines: list[tuple[str, str]]) -> list[dict]:
    """물음표가 있는 상담사 말 + 바로 뒤 고객 답 + 그 뒤 고객 말 두 줄(보류 조건용)."""
    out = []
    for i, (who, said) in enumerate(lines):
        if who == "상담사" and "?" in said and i + 1 < len(lines) and lines[i + 1][0] == "고객":
            later = [s for w, s in lines[i + 2:i + 6] if w == "고객"][:2]
            out.append({"q": said, "a": lines[i + 1][1], "later": later})
    return out


def extract_consult(unit: dict, spec: dict, header: str, api_key: str, retries: int) -> dict:
    """상담 원문 하나 → 스키마 모양 그래프(가지치기까지). 실패하면 {"error": 한 줄}. core.extract_one과 같은 반환 꼴."""
    record_chain, pair_chain, hold_chain = chains(api_key)
    text = unit["text"]
    meta = unit["metadata"]
    lines = dialogue(text)
    customer = [s for w, s in lines if w == "고객"]
    try:
        fields = invoke_retry(record_chain, {"doc": header + text}, retries)
        cands = proposal_candidates(lines)
        judged = []
        if cands:
            body = "\n".join(f"{n}. 상담사: {c['q']}\n   고객: {c['a']}" for n, c in enumerate(cands, start=1))
            judged = invoke_retry(pair_chain, {"pairs": body}, retries).pairs
    except Exception as error:
        return {"error": f"{type(error).__name__}: {str(error)[:200]}"}

    uid = unit["unit_id"]
    nodes, rels = [], []

    def add(label: str, props: dict) -> str:
        node_id = f"{uid}:{len(nodes)}"
        nodes.append(Neo4jNode(id=node_id, label=label, properties={k: v for k, v in props.items() if v not in (None, "")}))
        return node_id

    topic = re.search(r"\[상담주제\]\s*(.+)", text)
    consult = add("Consultation", {
        "record_id": meta.get("record_id"), "consult_date": meta.get("consult_date"), "channel": meta.get("channel"),
        "member_pseudo_id": meta.get("member_pseudo_id"), "topic": topic.group(1).strip() if topic else None,
        "summary": fields.topic_summary, "contact_preference": fields.contact_preference})
    for other in dict.fromkeys(RECORD_ID.findall(text)):  # 본문이 앞 상담 ID를 말하면 그 상담에 이어짐
        if other != meta.get("record_id"):
            rels.append(Neo4jRelationship(type="FOLLOWS", start_node_id=consult,
                                          end_node_id=add("Consultation", {"record_id": other})))
    if fields.is_complaint:
        quote = fields.complaint_quote if norm(fields.complaint_quote) and norm(fields.complaint_quote) in norm(text) else ""
        if not quote and customer:  # 인용이 원문과 어긋나면 가장 비슷한 고객 줄을 그대로 씀(원문 그대로)
            best = max(customer, key=lambda line: SequenceMatcher(None, norm(fields.complaint_quote), norm(line)).ratio())
            if SequenceMatcher(None, norm(fields.complaint_quote), norm(best)).ratio() >= 0.5:
                quote = best
        if quote:
            rels.append(Neo4jRelationship(type="HAS_COMPLAINT", start_node_id=consult, end_node_id=add(
                "Complaint", {"cause": quote, "summary": fields.complaint_summary})))
    for pj in judged:
        if not (1 <= pj.pair_no <= len(cands)) or not pj.is_proposal or pj.decision == "해당없음":
            continue
        c = cands[pj.pair_no - 1]
        reason = pj.reason_quote if norm(pj.reason_quote) and norm(pj.reason_quote) in norm(c["a"]) else ""
        proposal = add("Proposal", {"content": c["q"], "decision": pj.decision, "reason": reason, "reply": c["a"]})
        rels.append(Neo4jRelationship(type="HAS_PROPOSAL", start_node_id=consult, end_node_id=proposal))
        if pj.decision == "보류":  # 재검토 조건은 바로 뒤 답이나 이어진 고객 말에 있음
            said = [c["a"]] + c["later"]
            try:
                cond = invoke_retry(hold_chain, {"proposal": c["q"], "lines": "\n".join(said)}, retries).condition_quote
            except Exception:
                cond = ""
            if norm(cond) and norm(cond) in norm(" ".join(said)):
                rels.append(Neo4jRelationship(type="RECONSIDER_WHEN", start_node_id=proposal,
                                              end_node_id=add("ReconsiderCondition", {"condition": cond})))
    graph = Neo4jGraph(nodes=nodes, relationships=rels)
    pruned = asyncio.run(GraphPruning().run(graph, spec["schema"])).graph  # K3: 스키마 밖은 지움(안전장치)
    return {"graph": pruned.model_dump(), "raw_nodes": len(nodes), "kept_nodes": len(pruned.nodes)}
