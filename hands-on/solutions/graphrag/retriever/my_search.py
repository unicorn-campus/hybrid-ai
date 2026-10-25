"""교육생용 뼈대: core_search.py와 같은 이름, 같은 인자의 실습 함수 13개(+ 선택 1개)를 본인 코드로 채우는 파일임.

채우는 순서(워크플로우 순서). "직접"은 NotImplementedError 자리에 본인 코드를 쓰고, "빈칸"은 거의 완성된 코드의 빈칸만 채움
  [교시 2: ① ~ ④ 래퍼]
   1 check_ready             (직접)      ① 권한, 같은 세대, 보고서 유무
   2 decide_question_route   (직접)      ② Jev 확률 → 코드의 결정
   3 build_agent             (빈칸 2곳)  ③ create_agent로 ReAct 고리 만들고 돌리기
   4 run_tool                (빈칸 2곳)  ④ 래퍼: 질의 속 식별자 지우기, 필터 강제
  [교시 3: ④ O, L과 ⑤]
   5 rrf_merge               (직접)      ④ O3 RRF로 두 순위 합치기
   6 narrow_entities         (직접)      ④ L2 엔티티 16개로 줄이기
   7 diagnose_signals        (빈칸 3곳)  ⑤ 진단 신호 규칙
   8 force_stop_reason       (직접)      ⑤ 강제 종료 조건
   + normalize_entity_key    (선택, 직접) ④ E1 레이블마다 키를 같은 꼴로
  [교시 4: ⑥ ~ ⑩]
   9 select_final_chunks     (직접)      ⑥ 주제마다 1자리 먼저, 8자리
  10 recheck_question        (빈칸 2곳)  ⑦ 원 질문 재확인 조건 ①, ②
  11 generate_answer         (빈칸 2곳)  ⑧ LCEL 체인 + 구조화 출력
  12 verify_answer           (직접)      ⑨ 인용, 숫자, 보고서 인용 검사
  13 make_end_state          (빈칸 1곳)  ⑩ 종료 상태 이름과 돌려줄 것
  제공(완성본, 읽기만): 상수, 스키마(GroundedAnswer), 제공 함수는 core_search에서 그대로 가져옴(아래 import)

사용법
  1) search_graph.py의 import 한 줄을 "import my_search as core"로 바꿈
  2) 채울 함수 이름을 이 파일 맨 아래 USE_TEACHER_CODE 목록에서 지움(지우지 않은 함수는 강사 코드가 대신 돎)
  3) 함수를 채우고 같은 명령(예: --qid Q01)으로 실행해 강사 결과와 비교함. 막히면 이름을 목록에 다시 넣고 다음 함수로 넘어감
"""

import re

from langchain.agents import create_agent

# 제공 상수, 스키마, 제공 함수: 강사 코드(core_search.py)의 것을 그대로 씀(읽고 이해만 함)
from core_search import (  # noqa: F401
    CLAUSE_PATTERN, END_STATES, MEMBER_ID_PATTERN, NUMBER_PATTERN, PSEUDO_ID_PATTERN, ROLES, TREND_WORDS,
    AnswerSentence, GroundedAnswer,
    allowed_chunk_ids, apply_passage_judgments, block_calls, candidate_pairs, check_tool_input, core_terms,
    count_cooccur, coverage,
    decide_collection, keep_linked_entities, member_pseudonym, replace_identifiers, split_sentences, strip_identifiers,
    wrap_chunks,
)


# ===========================================================================
# 1. ① 요청 접수: 준비 확인 (교재 65쪽) — 직접 작성
# ===========================================================================
def check_ready(role: str, active: dict | None, index_exists: bool, graph_chunk_count: int, report_count: int) -> dict:
    """검색을 시작해도 되는지 세 조건(권한, 같은 세대, 보고서 유무)으로 판정함.

    방법: ① role이 ROLES에 없으면 ok False(「권한 없음」) ② active가 None이거나 index_exists가 False이거나
          graph_chunk_count가 active["chunk_count"]와 다르면 ok False(세대 문제) ③ 그 밖은 ok True이고,
          allow_global은 report_count가 0보다 클 때만 True(보고서가 없으면 global_search만 막음)
    반환값: {"ok": bool, "reason": 한 줄, "allow_global": bool}
    """
    raise NotImplementedError("여기에 본인 코드를 작성함")


# ===========================================================================
# 2. ② 질문 분석: Jev 확률 → 코드의 결정 (교재 65, 66쪽) — 직접 작성
# ===========================================================================
def decide_question_route(answers: dict | None, thresholds: dict) -> dict:
    """Jev가 낸 확률을 기준값과 비교해 「끝낼지, 첫 툴 후보는 무엇인지」를 정함.

    인자: answers는 {"is_smalltalk": 확률, "needs_clarification": 확률, "first_tool": (답, 확신),
          "first_tool_swapped": (답, 확신)} 또는 None(Jev 실패). thresholds는 {"end_noul": 0.7, "choice_confidence": 0.5}
    방법: ① answers가 None → end None, first_tool None(규칙만으로 검색)
          ② is_smalltalk ≥ end_noul → end "no_search" ③ needs_clarification ≥ end_noul → end "need_clarification"
          ④ 두 번의 첫 툴 답이 같고 두 확신이 모두 choice_confidence 이상 → first_tool에 그 답, 아니면 None
    반환값: {"end": None 또는 "no_search" 또는 "need_clarification", "first_tool": 툴 이름 또는 None, "reason": 한 줄}
    """
    raise NotImplementedError("여기에 본인 코드를 작성함")


# ===========================================================================
# 3. ③ 검색 에이전트: create_agent로 ReAct 고리 (교재 68쪽) — 빈칸 2곳
# ===========================================================================
def build_agent(model, tools: list, system_prompt: str, middleware: list, first_message: str, context: dict,
                recursion_limit: int) -> dict:
    """LangChain create_agent로 「생각 → 툴 호출 → 관찰」 고리를 만들고 돌려서 마지막 상태를 돌려줌.

    반환값: 에이전트의 마지막 상태(dict). "messages"에 모든 대화가 순서대로 있음.
    """
    # 빈칸 1: create_agent에 model, tools, system_prompt, middleware를 이름 붙여 넘겨 에이전트를 만들고 agent에 받음
    raise NotImplementedError("빈칸 1을 채울 것")

    # 빈칸 2: agent.invoke(입력, context=..., config=...)로 고리를 끝까지 돌려 state에 받음
    #         입력은 {"messages": [{"role": "user", "content": first_message}]},
    #         config는 {"recursion_limit": recursion_limit}
    raise NotImplementedError("빈칸 2를 채우고 이 줄을 지울 것")
    return state


# ===========================================================================
# 4. ④ 툴 실행: 래퍼 (교재 69쪽) — 빈칸 2곳
# ===========================================================================
def run_tool(name: str, args: dict, ctx: dict, tool_functions: dict) -> dict:
    """에이전트의 툴 호출 하나를 실행하는 래퍼. 입력 검사, 질의 속 식별자 지우기, 필터 강제를 함.

    반환값: {"text": 관찰 글, "result": 서브 워크플로우 결과, "error": 입력 오류면 True}
    """
    problem = check_tool_input(name, args, set(ctx["topics"]), ctx["allow_global"])
    if problem:
        return {"text": f"입력 오류: {problem}", "result": None, "error": True}
    args = dict(args)
    # 빈칸 1: args에 "query"가 있으면 strip_identifiers로 회원번호와 가명 id를 지운 글로 바꿈
    raise NotImplementedError("빈칸 1을 채울 것")

    # 빈칸 2: filters = ctx["filters"]로 필터를 꺼내고, tool_functions[name]을 (args, filters, ctx)로 불러 result에 받음
    raise NotImplementedError("빈칸 2를 채우고 이 줄을 지울 것")
    text = result["observation"]
    return {"text": text, "result": result, "error": False}


# ===========================================================================
# 5. ④ O 검색엔진 검색: RRF (교재 70쪽) — 직접 작성
# ===========================================================================
def rrf_merge(vector_hits: list[dict], bm25_hits: list[dict], k: int = 60, top: int = 25) -> list[dict]:
    """벡터 검색과 BM25 검색의 두 순위를 RRF로 합침.

    방법: 청크마다 RRF 점수 = Σ 1 / (k + 순위)(순위는 1부터). 두 검색에 모두 나오면 더함. 점수 내림차순 상위 top개.
    반환값: [{"chunk_id", "rrf", "ranks": {"vector": 순위, "bm25": 순위}}] (한쪽에만 있으면 ranks에 그쪽만)
    예시: A가 벡터 1위, BM25 3위 → 1/61 + 1/63 ≈ 0.0323
    """
    raise NotImplementedError("여기에 본인 코드를 작성함")


# ===========================================================================
# 6. ④ L Local 검색: 엔티티 축소 (교재 71쪽) — 직접 작성
# ===========================================================================
def narrow_entities(candidates: list[dict], limit: int = 16, pinned_ids: list[str] | None = None) -> list[dict]:
    """청크에서 나온 엔티티 후보를 질문과의 유사도로 줄여 limit개만 남김.

    방법: ① pinned_ids의 엔티티를 먼저 ② 청크마다(처음 나온 청크 순서) 유사도가 가장 높은 엔티티 1개
          ③ 남은 자리를 전체 유사도 순으로. 같은 id는 한 번만, 합계 limit개까지.
    인자: candidates는 [{"id", "chunk_id", "score", ...}]
    """
    raise NotImplementedError("여기에 본인 코드를 작성함")


# ===========================================================================
# 선택 과제. ④ E 엔티티 찾기: 키 정규화 (교재 73쪽) — 직접 작성
# ===========================================================================
def normalize_entity_key(label: str, text: str) -> str:
    """찾을 대상의 글을 레이블별 키 속성과 같은 꼴로 맞춤(E1 정규화).

    규칙: ProductGuide는 「한빛」과 끝의 「카드」를 떼고 공백을 지움. Clause는 「제N조」(「의M」은 남기고 항 번호는 뗌).
          Benefit은 공백과 괄호를 지움. 그 밖은 앞뒤 공백만 지움.
    예시: ("Clause", "16조의2 1항") → "제16조의2" / ("ProductGuide", "한빛 모아생활 카드") → "모아생활"
    """
    raise NotImplementedError("여기에 본인 코드를 작성함")


# ===========================================================================
# 7. ⑤ 채점: 진단 신호 (교재 74쪽) — 빈칸 3곳
# ===========================================================================
def diagnose_signals(stats: dict, thresholds: dict) -> list[str]:
    """툴 결과 하나의 통계로 진단 신호를 매김.

    인자: stats의 키는 tool, n_chunks, coverage, cooccur(낱말이 2개 미만이면 None), n_doc_types, has_member_filter,
          n_reports, n_new_relevant. thresholds는 {"coverage": 0.6, "min_chunks": 2}
    """
    signals = []
    # 빈칸 1: n_chunks가 0이면 "NO_SEED"를 넣음
    raise NotImplementedError("빈칸 1을 채울 것")

    # 빈칸 2: n_chunks가 0보다 크고 cooccur가 0이면 "NO_COOCCUR"를 넣음(cooccur가 None이면 넣지 않음)
    raise NotImplementedError("빈칸 2를 채우고 이 줄을 지울 것")

    # 빈칸 3: coverage ≥ thresholds["coverage"], n_chunks ≥ thresholds["min_chunks"], NO_COOCCUR 없음이면 "PASS"
    raise NotImplementedError("빈칸 3을 채우고 이 줄을 지울 것")

    # 아래 4개는 완성본
    if stats["n_chunks"] > 0 and stats["coverage"] < thresholds["coverage"]:
        signals.append("LOW_COVERAGE")
    if stats["n_doc_types"] >= 3 and not stats["has_member_filter"] and stats["coverage"] < thresholds["coverage"]:
        signals.append("SCATTERED")
    if stats["tool"] == "global_search" and stats["n_reports"] == 0:
        signals.append("NO_REPORTS")
    if stats["n_chunks"] > 0 and stats["n_new_relevant"] == 0:
        signals.append("NO_NEW")
    return signals


# ===========================================================================
# 8. ⑤ 상한 판정: 강제 종료 (교재 75쪽) — 직접 작성
# ===========================================================================
def force_stop_reason(counts: dict, max_rounds: int) -> str | None:
    """더 찾아도 소용없거나 상한을 다 쓰면 강제 종료 이유 한 줄을, 아니면 None을 돌려줌.

    조건(위에서부터 먼저 걸린 것): ① counts["rounds"] ≥ max_rounds ② counts["no_new_streak"] ≥ 2
          ③ counts["same_call_streak"] ≥ 2 ④ counts["failed_rounds"] ≥ 2
    """
    raise NotImplementedError("여기에 본인 코드를 작성함")


# ===========================================================================
# 9. ⑥ 리랭킹: 8자리 고르기 (교재 76쪽) — 직접 작성
# ===========================================================================
def select_final_chunks(scored: list[dict], limit: int = 8) -> list[dict]:
    """리랭커 점수가 붙은 원문에서 limit자리를 고름. Global 검색 주제마다 1자리를 먼저 맡김.

    방법: ① 주제 id 이름순으로 그 주제의 최고 점수 원문을 1자리씩 ② 남은 자리를 점수 순으로 ③ 점수 내림차순으로 돌려줌
    인자: scored는 [{"chunk_id", "score", "topic_ids": [...]}]
    """
    raise NotImplementedError("여기에 본인 코드를 작성함")


# ===========================================================================
# 10. ⑦ 수집 종료 판정: 코드 재확인 (교재 77쪽) — 빈칸 2곳
# ===========================================================================
def recheck_question(terms: list[str], chunks: list[dict], chunk_entities: dict, entity_texts: dict,
                     links: set) -> dict:
    """원 질문의 핵심 낱말 두 개로 모은 원문을 다시 확인함. 조건 ① 또는 ②면 통과.

    반환값: {"passed": bool, "rule": 「조건 ①」 등, "detail": 한 줄}
    """
    texts = [chunk["text"] for chunk in chunks]
    if len(terms) < 2:
        found = bool(terms) and any(terms[0].replace(" ", "") in t.replace(" ", "") for t in texts)
        return {"passed": found, "rule": "낱말 1개", "detail": f"「{terms[0] if terms else '-'}」 {'있음' if found else '없음'}"}
    a, b = terms[0], terms[1]
    # 빈칸 1: count_cooccur(a, b, texts)로 두 낱말이 함께 나온 문장 수를 together에 받음
    raise NotImplementedError("빈칸 1을 채울 것")
    if together > 0:
        return {"passed": True, "rule": "조건 ①", "detail": f"「{a}」와 「{b}」가 한 문장에 함께({together}문장)"}
    for entity_a, entity_b, where in candidate_pairs(a, b, chunks, chunk_entities, entity_texts):
        # 빈칸 2: entity_a와 entity_b가 서로 다르고 frozenset((entity_a, entity_b))가 links에 있으면
        #         {"passed": True, "rule": "조건 ②", "detail": f"「{a}」와 「{b}」가 관계 하나로 이어짐({where})"}를 돌려줌
        raise NotImplementedError("빈칸 2를 채우고 이 줄을 지울 것")
    return {"passed": False, "rule": "-", "detail": f"「{a}」와 「{b}」를 잇는 근거 없음"}


# ===========================================================================
# 11. ⑧ 답변 생성: LCEL 체인 + 구조화 출력 (교재 78쪽) — 빈칸 2곳
# ===========================================================================
def generate_answer(llm, prompt, question: str, evidence_text: str, feedback: str, premise_note: str) -> GroundedAnswer:
    """근거만으로 답을 만듦. 답은 문장마다 인용 id를 단 구조화 객체(GroundedAnswer)로 받음."""
    # 빈칸 1: llm.with_structured_output(GroundedAnswer, method="json_schema", strict=True)를 structured에 받음
    raise NotImplementedError("빈칸 1을 채울 것")

    # 빈칸 2: prompt와 structured를 | 로 이어 chain을 만듦(LCEL 체인)
    raise NotImplementedError("빈칸 2를 채우고 이 줄을 지울 것")
    return chain.invoke({"question": question, "evidence": evidence_text, "feedback": feedback or "없음",
                         "premise_note": premise_note or "없음"})


# ===========================================================================
# 12. ⑨ 근거 검증 (교재 78쪽) — 직접 작성
# ===========================================================================
def verify_answer(answer: GroundedAnswer, evidence: dict) -> list[str]:
    """답을 근거와 대조해 실패 사유 목록을 돌려줌. 빈 목록이면 통과.

    검사 ①: 문장마다 citation_ids가 비어 있지 않고 모두 evidence에 있음
    검사 ②: 문장의 조항 번호(CLAUSE_PATTERN)와 숫자(NUMBER_PATTERN)가 인용한 원문에 그대로 있음
            (공백과 쉼표를 지우고 비교. 단위를 뗀 숫자만으로도 한 번 더 봄)
    검사 ③: evidence[id]["kind"]가 "report"인 근거를 인용한 문장에는 TREND_WORDS 중 하나가 있어야 함
    예시 실패 사유: 「문장 1: c2에 7일 없음」
    """
    raise NotImplementedError("여기에 본인 코드를 작성함")


# ===========================================================================
# 13. ⑩ 종료 상태 (교재 79쪽) — 빈칸 1곳
# ===========================================================================
def make_end_state(end_code: str, reason: str, answer_text: str, evidence: list[dict], warnings: list[str]) -> dict:
    """어디서 끝나든 종료 상태 이름과 끝난 이유를 함께 돌려줌."""
    # 빈칸 1: END_STATES[end_code]에서 (이름, 뜻)을 꺼내 name, meaning에 받음
    raise NotImplementedError("빈칸 1을 채울 것")
    return {"status": name, "code": end_code, "meaning": meaning, "reason": reason, "answer": answer_text or "",
            "evidence": evidence, "warnings": warnings}


# ---------------------------------------------------------------------------
# 아직 채우지 않은 함수는 강사 코드(core_search)로 대신 돌게 함.
# 함수를 채울 때마다 그 이름을 아래 목록에서 지움. 목록이 비면 이 파일의 코드만으로 전체가 돎.
# 막히면 이름을 다시 넣어 뒤 단계를 계속함(실습이 멈추지 않음)
# ---------------------------------------------------------------------------
import core_search as _teacher  # noqa: E402

USE_TEACHER_CODE = [
    "check_ready", "decide_question_route", "build_agent", "run_tool",
    "rrf_merge", "narrow_entities", "diagnose_signals", "force_stop_reason", "normalize_entity_key",
    "select_final_chunks", "recheck_question", "generate_answer", "verify_answer", "make_end_state",
]
for _name in USE_TEACHER_CODE:
    globals()[_name] = getattr(_teacher, _name)  # 이 파일의 빈 함수 대신 강사 함수를 같은 이름으로 둠
