"""교육생용 뼈대: core_search.py와 같은 이름, 같은 인자의 실습 함수 10개를 본인 코드로 채우는 파일임.

채우는 순서(워크플로우 순서). "직접"은 NotImplementedError 자리에 본인 코드를 쓰고, "빈칸"은 거의 완성된 코드의 빈칸만 채움
  [교시 2: ①, ②, ③ 벡터]
   1 build_chroma_filter    (빈칸 2곳)  ① 역할과 회원으로 Chroma 메타데이터 필터
   2 apply_plan_rules       (빈칸 3곳)  ② LLM 제안을 규칙 5개로 확정
   3 search_vector          (빈칸 2곳)  ③ Chroma 근사 검색과 점수 방향 통일
  [교시 3: ③ BM25, 융합, 리랭크]
   4 search_bm25            (직접)      ③ 저장된 BM25 점수표로 순위
   5 fuse_weighted          (직접)      ③ 정규화한 두 점수를 6 : 4로
   6 rerank                 (빈칸 2곳)  ③ Cohere 리랭커로 다시 채점
  [교시 4: ④, ⑤, ⑥]
   7 grade                  (직접)      ④ 신호로 정확, 불확실, 부정확 판정
   8 apply_transform_rules  (빈칸 3곳)  ④ 질문 변환 금지 규칙
   9 generate_answer        (빈칸 2곳)  ⑤ LCEL 체인 + 구조화 출력
  10 verify_answer          (직접)      ⑥ 인용문을 근거 본문과 글자 대조
  제공(완성본, 읽기만): 상수, 스키마, 제공 함수는 core_search에서 그대로 가져옴(아래 import)

사용법
  1) search_docs.py의 import 한 줄을 "import my_search as core"로 바꿈
  2) 채울 함수 이름을 이 파일 맨 아래 USE_TEACHER_CODE 목록에서 지움(지우지 않은 함수는 강사 코드가 대신 돎)
  3) 함수를 채우고 같은 명령(예: --qid Q01)으로 실행해 강사 결과와 비교함. 막히면 이름을 목록에 다시 넣고 다음 함수로 넘어감
"""

from langchain_core.prompts import ChatPromptTemplate  # noqa: F401  (⑤ generate_answer에서 씀)

# 제공 상수, 스키마, 함수는 강사 코드에서 그대로 가져옴(search_docs.py가 core.이름 으로 부르므로 이 파일에도 있어야 함)
from core_search import (  # noqa: F401
    ALLOWED_TECHNIQUES,
    ANSWER_HUMAN_PROMPT,
    ANSWER_SYSTEM_PROMPT,
    BUSINESS_WORDS,
    CLARIFY,
    GRADE_CORRECT,
    GRADE_INCORRECT,
    GRADE_UNCERTAIN,
    KEEP,
    MAX_TRANSFORM_QUERIES,
    ORIGINAL_REQUIRED,
    QTYPE_CHITCHAT,
    QTYPE_COMPLEX,
    QTYPE_SIMPLE,
    RERANK_MODEL,
    ROLE_ACCESS_LEVELS,
    TECHNIQUES,
    AnswerSentence,
    GroundedAnswer,
    _build_fused_list,
    _get_fused_score,
    _merge_lists,
    _normalize_scores,
    answer_to_text,
    build_signals,
    build_weight_mask,
    card_token,
    compact_text,
    condition_terms,
    describe_source,
    domain_terms,
    fallback_simple,
    format_evidence,
    fuse_rrf,
    hit_card_token,
    is_chunk_allowed,
    member_pseudonym,
    merge_query_results,
    mixed_target_clarify,
    normalize_query,
    select_evidence,
    target_key,
)


# ===========================================================================
# 1. ① 권한 필터 (교재 151쪽) — 빈칸 2곳
# ===========================================================================
def build_chroma_filter(role: str, member_pseudo_id: str | None) -> dict | None:
    """역할과 회원 가명 ID로 벡터 검색용 Chroma 메타데이터 필터를 만듦.

    agent → {"access_level": {"$eq": "public"}}
    auditor + 회원 없음 → None(거르지 않음)
    auditor + 회원 → access_level이 "restricted"이고 member_pseudo_id가 그 회원인 청크만($and)
    """
    if role == "agent":
        # 빈칸 1: access_level이 "public"과 같은($eq) 청크만 남기는 필터 dict를 return함
        raise NotImplementedError("빈칸 1을 채울 것")
    if member_pseudo_id is None:
        return None
    # 빈칸 2: "$and" 목록에 조건 두 개(access_level이 "restricted", member_pseudo_id가 member_pseudo_id)를 넣은 dict를 return함
    raise NotImplementedError("빈칸 2를 채울 것")


# ===========================================================================
# 2. ② Adaptive 분류 (교재 152 ~ 155쪽) — 빈칸 3곳
# ===========================================================================
def apply_plan_rules(
    question: str,
    question_type: str,
    sub_questions: list[str],
    chitchat_reply: str,
    condition_terms_of,
    domain_terms_of,
    max_sub_questions: int = 3,
) -> dict:
    """LLM이 제안한 질문 유형과 하위 질문을 규칙 5개로 검사해 검색할 질의를 확정함.

    반환값: {"type", "queries", "reply", "warnings"}. 규칙에 걸리면 fallback_simple(question, 이유)를 돌려줌.
    """
    # 규칙 1: 약속하지 않은 유형 → 단순
    if question_type not in [QTYPE_CHITCHAT, QTYPE_SIMPLE, QTYPE_COMPLEX]:
        return fallback_simple(question, f"알 수 없는 질문 유형 → 단순 처리: {question_type}")

    # 규칙 2: 업무 낱말이 있는 잡담 → 단순
    if question_type == QTYPE_CHITCHAT:
        business_words = sorted(domain_terms_of(question))
        # 빈칸 1: business_words가 하나라도 있으면
        #         fallback_simple(question, f"잡담 판정이지만 업무 낱말 {business_words[:5]}이 있어 단순 질문으로 처리")를 return함
        raise NotImplementedError("빈칸 1을 채울 것")
        if chitchat_reply.strip() == "":
            return fallback_simple(question, "잡담 답이 비어 단순 질문으로 처리")
        return {"type": QTYPE_CHITCHAT, "queries": [], "reply": chitchat_reply.strip(), "warnings": []}

    if question_type == QTYPE_SIMPLE:
        return {"type": QTYPE_SIMPLE, "queries": [question], "reply": "", "warnings": []}

    texts = []
    for text in sub_questions:
        cleaned = " ".join(text.split())
        if cleaned != "" and cleaned not in texts:
            texts.append(cleaned)

    warnings = []
    # 규칙 4: 하위 질문은 앞에서부터 최대 max_sub_questions개
    if len(texts) > max_sub_questions:
        warnings.append(f"하위 질문 {len(texts)}개 중 앞 {max_sub_questions}개만 사용")
        # 빈칸 2: texts를 앞 max_sub_questions개만 남긴 목록으로 바꿈(목록 자르기 문법)
        raise NotImplementedError("빈칸 2를 채울 것")

    # 규칙 3: 하위 질문 1개 이하 → 단순
    if len(texts) <= 1:
        return fallback_simple(question, "복합 판정인데 하위 질문이 1개 이하라 단순 질문으로 처리")

    # 규칙 5: 조건 낱말 보존 검사
    original_terms = condition_terms_of(question)
    union_terms = set()
    for text in texts:
        union_terms = union_terms | condition_terms_of(text)
    # 빈칸 3: lost(원 질문에만 있는 조건)와 invented(하위 질문에만 있는 조건)를 집합 빼기(-)로 구함
    raise NotImplementedError("빈칸 3을 채울 것")
    if len(lost) > 0 or len(invented) > 0:  # noqa: F821
        return fallback_simple(question, f"하위 질문 조건 검사 실패: 빠진 조건 {sorted(lost)}, 새 조건 {sorted(invented)}")  # noqa: F821
    return {"type": QTYPE_COMPLEX, "queries": texts, "reply": "", "warnings": warnings}


# ===========================================================================
# 3. ③ 검색: 벡터 (교재 159 ~ 160쪽) — 빈칸 2곳
# ===========================================================================
def search_vector(store, query: str, top_n: int, chroma_filter: dict | None) -> list[dict]:
    """질의를 임베딩해 Chroma HNSW 근사 검색으로 가까운 청크 top_n개를 찾음.

    반환값: {"chunk_id", "text", "metadata", "score", "rank"} 목록. score = 1 - 코사인 거리.
    """
    # 빈칸 1: store.similarity_search_with_score(...)에 질의, k=top_n, filter=chroma_filter를 넘겨 results에 받음
    raise NotImplementedError("빈칸 1을 채울 것")
    hits = []
    for rank, (document, distance) in enumerate(results, start=1):  # noqa: F821
        # 빈칸 2: 거리(작을수록 가까움)를 "클수록 좋은" 점수로 바꿔 score에 받음(float로 바꿀 것)
        raise NotImplementedError("빈칸 2를 채울 것")
        hits.append(
            {
                "chunk_id": document.id,
                "text": document.page_content,
                "metadata": document.metadata,
                "score": score,  # noqa: F821
                "rank": rank,
            }
        )
    return hits


# ===========================================================================
# 4. ③ 검색: BM25 (교재 157 ~ 158쪽) — 직접 작성
# ===========================================================================
def search_bm25(bm25, chunks: list[dict], query_tokens: list[str], top_n: int, weight_mask=None) -> list[dict]:
    """BM25 점수가 높은 청크를 top_n개까지 돌려줌.

    할 일 1: bm25.get_scores(query_tokens, weight_mask=weight_mask)로 청크마다 점수를 받음(순서는 chunks와 같음)
    할 일 2: (점수, 순번) 쌍을 목록에 모으되 점수 0은 버림. 점수는 float(...)로 바꿈
    할 일 3: 목록.sort(reverse=True)로 점수 내림차순 정렬
    할 일 4: 앞 top_n개를 enumerate(..., start=1)로 돌며 {"chunk_id", "text", "metadata", "score", "rank"} dict를 만듦
    """
    raise NotImplementedError("여기에 본인 코드를 작성함")


# ===========================================================================
# 5. ③ 검색: 융합 (교재 161 ~ 162쪽) — 직접 작성
# ===========================================================================
def fuse_weighted(
    vector_hits: list[dict],
    bm25_hits: list[dict],
    vector_weight: float = 0.6,
    bm25_weight: float = 0.4,
) -> list[dict]:
    """벡터와 BM25 점수를 각각 0 ~ 1로 정규화한 뒤 가중합으로 합침.

    할 일 1: _normalize_scores로 두 결과를 각각 {chunk_id: 0 ~ 1} dict로 만듦
    할 일 2: _merge_lists([vector_hits, bm25_hits], ["vector", "bm25"])로 chunk_id 묶음 표를 만듦
    할 일 3: 묶음 표의 chunk_id마다 vector_weight × 벡터 정규화 + bm25_weight × BM25 정규화를 계산(없는 쪽은 0점)
    할 일 4: _build_fused_list(묶음 표, {chunk_id: 융합 점수})를 return함
    """
    raise NotImplementedError("여기에 본인 코드를 작성함")


# ===========================================================================
# 6. ③ 검색: 리랭크 (교재 163 ~ 166쪽) — 빈칸 2곳
# ===========================================================================
def rerank(
    question: str,
    candidates: list[dict],
    cohere_client,
    top_k: int,
    model_name: str = RERANK_MODEL,
) -> list[dict]:
    """Cohere 리랭커로 후보를 다시 채점해 상위 top_k개를 돌려줌."""
    if len(candidates) == 0:
        return []
    documents = []
    for candidate in candidates:
        documents.append(candidate["text"])

    # 빈칸 1: cohere_client.rerank(...)에 model=model_name, query=question, documents=documents, top_n=top_k를
    #         넘겨 response에 받음
    raise NotImplementedError("빈칸 1을 채울 것")

    reranked = []
    for rank, result in enumerate(response.results, start=1):  # noqa: F821
        # 빈칸 2: result.index(보낸 목록의 순번)로 candidates에서 원래 후보를 찾아 dict(...)로 복사해 candidate에 받음
        raise NotImplementedError("빈칸 2를 채울 것")
        candidate["fused_rank"] = candidate["rank"]  # noqa: F821
        candidate["rerank_score"] = float(result.relevance_score)  # noqa: F821
        candidate["rank"] = rank  # noqa: F821
        reranked.append(candidate)  # noqa: F821
    return reranked


# ===========================================================================
# 7. ④ CRAG 채점 (교재 149, 171쪽) — 직접 작성
# ===========================================================================
def grade(signals: dict, thresholds: dict) -> str:
    """판정 근거로 GRADE_CORRECT, GRADE_UNCERTAIN, GRADE_INCORRECT 중 하나를 돌려줌.

    ① 부정확(하나라도): signals["result_count"] == 0, 또는 main_score가 None이 아니고 thresholds["lower"] 미만
    ② 정확(모두): signals["reranked"], main_score ≥ thresholds["upper"], signals["keyword_match"], signals["target_match"],
       gap ≥ thresholds["min_gap"],
       겹침 만족(overlap ≥ thresholds["min_overlap"] 또는 main_score ≥ thresholds["overlap_waiver"])
    ③ 나머지는 불확실
    """
    raise NotImplementedError("여기에 본인 코드를 작성함")


# ===========================================================================
# 8. ④ 질문 변환 금지 규칙 (교재 169, 172쪽) — 빈칸 3곳
# ===========================================================================
def apply_transform_rules(
    technique: str,
    queries: list[str],
    clarify_question: str,
    reason: str,
    target_query: str,
    previous_queries: list[str],
    forced_clarify: str | None,
) -> dict:
    """LLM이 고른 질문 변환에 금지 규칙을 적용해 최종 결정을 만듦."""
    decision = {"technique": KEEP, "queries": [], "include_original": False,
                "clarify_question": "", "reason": reason, "warnings": []}

    # 규칙 ①: 대상명 없음 + 대상 섞임 → clarify
    if forced_clarify is not None:
        # 빈칸 1: decision의 technique를 CLARIFY로, clarify_question을 forced_clarify로 바꾸고
        #         warnings에 "대상명 없음 + 대상 섞임 → clarify"를 더한 뒤 decision을 return함
        raise NotImplementedError("빈칸 1을 채울 것")

    # 규칙 ②: 허용 선택지 밖 → keep
    if technique not in ALLOWED_TECHNIQUES:
        decision["warnings"].append(f"허용 선택지 밖 기법 거부: {technique}")
        return decision

    # 규칙 ③: keep, clarify
    if technique == KEEP:
        return decision
    if technique == CLARIFY:
        if clarify_question.strip() == "":
            decision["warnings"].append("확인 질문이 비어 clarify 거부 → keep")
            return decision
        decision["technique"] = CLARIFY
        decision["clarify_question"] = clarify_question.strip()
        return decision

    # 규칙 ④: 같은 질의 반복 금지
    seen = [normalize_query(target_query)]
    for previous in previous_queries:
        seen.append(normalize_query(previous))
    kept = []
    for query in queries:
        key = normalize_query(query)
        if key == "":
            continue
        # 빈칸 2: key가 seen에 있으면 warnings에 f"같은 질의 반복 제외: {query[:40]}"를 더하고 다음 질의로 넘어감(continue)
        raise NotImplementedError("빈칸 2를 채울 것")
        seen.append(key)
        kept.append(query.strip())
        if len(kept) == MAX_TRANSFORM_QUERIES:
            break
    if len(kept) == 0:
        decision["warnings"].append("쓸 수 있는 변환 질의 없음 → keep")
        return decision

    # 규칙 ⑤: HyDE, Step-Back은 원 질의도 함께 검색
    decision["technique"] = technique
    decision["queries"] = kept
    # 빈칸 3: technique가 ORIGINAL_REQUIRED에 있으면 True, 아니면 False를 decision["include_original"]에 넣음
    raise NotImplementedError("빈칸 3을 채울 것")
    return decision


# ===========================================================================
# 9. ⑤ 답변 생성 (교재 173쪽) — 빈칸 2곳
# ===========================================================================
def generate_answer(llm, question: str, hits: list[dict], failures: list[str] | None = None) -> GroundedAnswer:
    """근거 청크만으로 문장별 인용이 달린 답을 만듦(LCEL 체인 + 구조화 출력)."""
    if len(hits) == 0:
        return GroundedAnswer(sentences=[], missing="권한 범위 안에서 검색된 근거가 없음")
    feedback = "없음"
    if failures:
        feedback = "\n".join(failures)
    prompt = ChatPromptTemplate.from_messages([("system", ANSWER_SYSTEM_PROMPT), ("human", ANSWER_HUMAN_PROMPT)])
    # 빈칸 1: llm.with_structured_output(...)에 GroundedAnswer, method="json_schema", strict=True를 넘겨 structured_llm에 받음
    raise NotImplementedError("빈칸 1을 채울 것")
    # 빈칸 2: prompt와 structured_llm을 | 로 이어 chain을 만듦(LCEL)
    raise NotImplementedError("빈칸 2를 채울 것")
    answer = chain.invoke({"question": question, "evidence": format_evidence(hits), "feedback": feedback})  # noqa: F821
    return answer


# ===========================================================================
# 10. ⑥ Self-RAG 근거 검증 (교재 174쪽) — 직접 작성
# ===========================================================================
def verify_answer(answer: GroundedAnswer, evidence_texts: dict) -> list[str]:
    """답의 인용을 근거 본문과 대조해 실패 사유 목록을 돌려줌. 빈 목록이면 통과.

    answer.sentences의 문장마다(번호는 1부터):
      검사 ①: sentence.chunk_id가 비었으면 f"{번호}번 문장에 근거 청크ID가 없음: ..." 를 더하고 다음 문장으로
      검사 ②: chunk_id가 evidence_texts에 없으면 f"{번호}번 문장이 근거에 없는 청크ID를 인용함: ..." 를 더하고 다음 문장으로
      검사 ③: compact_text(인용문)이 비었거나 compact_text(본문) 안에 없으면 f"{번호}번 문장의 인용문이 ... 맞지 않음: ..." 를 더함
    """
    raise NotImplementedError("여기에 본인 코드를 작성함")


# ---------------------------------------------------------------------------
# 아직 채우지 않은 함수는 강사 코드(core_search)로 대신 돌게 함.
# 함수를 채울 때마다 그 이름을 아래 목록에서 지움. 목록이 비면 이 파일의 코드만으로 전체가 돎.
# 막히면 이름을 다시 넣어 뒤 단계를 계속함(실습이 멈추지 않음)
# ---------------------------------------------------------------------------
import core_search as _teacher  # noqa: E402

USE_TEACHER_CODE = [
    "build_chroma_filter", "apply_plan_rules", "search_vector",
    "search_bm25", "fuse_weighted", "rerank",
    "grade", "apply_transform_rules", "generate_answer", "verify_answer",
]
for _name in USE_TEACHER_CODE:
    globals()[_name] = getattr(_teacher, _name)  # 이 파일의 빈 함수 대신 강사 함수를 같은 이름으로 둠
