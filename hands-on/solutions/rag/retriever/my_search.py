"""교육생용 뼈대: core_search.py와 같은 이름, 같은 인자의 실습 함수 12개를 본인 코드로 채우는 파일임.

채우는 순서(워크플로우 순서). "직접"은 NotImplementedError 자리에 본인 코드를 쓰고, "빈칸"은 거의 완성된 코드의 빈칸만 채움
  [교시 2: ①, ②, ③ 벡터]
   1 build_chroma_filter    (빈칸 2곳)  ① 역할과 회원으로 Chroma 메타데이터 필터
   2 classify_question      (직접)      ② 질문유형 판정 LLM을 불러 유형과 하위 질문 제안받기
   3 apply_plan_rules       (빈칸 3곳)  ② LLM 제안을 규칙 5개로 확정
   4 search_vector          (빈칸 2곳)  ③ Chroma 근사 검색과 점수 방향 통일
  [교시 3: ③ BM25, 융합, 리랭크]
   5 search_bm25            (직접)      ③ 저장된 BM25 점수표로 순위
   6 fuse_weighted          (직접)      ③ 정규화한 두 점수를 6 : 4로
   7 rerank                 (빈칸 2곳)  ③ Cohere 리랭커로 다시 채점
  [교시 4: ④, ⑤, ⑥]
   8 grade                  (직접)      ④ 신호로 정확, 불확실, 부정확 판정
   9 transform_query        (빈칸 3곳)  ④ 질문 변환 LLM을 불러 질의를 고칠 방법 제안받기
  10 apply_transform_rules  (빈칸 3곳)  ④ 질문 변환 금지 규칙
  11 generate_answer        (빈칸 2곳)  ⑤ LCEL 체인 + 구조화 출력
  12 verify_answer          (직접)      ⑥ 인용문을 근거 본문과 글자 대조
  제공(완성본, 읽기만): 상수, 스키마, 제공 함수는 core_search에서 그대로 가져옴(아래 import)

함수 설명(docstring)과 주석은 core_search.py의 같은 함수와 같음. 빈칸 자리만 「# 빈칸 n: ...」 안내와 NotImplementedError로 바꿨음

사용법
  1) search_docs.py의 import 한 줄을 "import my_search as core"로 바꿈
  2) 채울 함수 이름을 이 파일 맨 아래 USE_TEACHER_CODE 목록에서 지움(지우지 않은 함수는 강사 코드가 대신 돎)
  3) 함수를 채우고 같은 명령(예: --qid Q01)으로 실행해 강사 결과와 비교함. 막히면 이름을 목록에 다시 넣고 다음 함수로 넘어감
"""

from langchain_core.prompts import ChatPromptTemplate  # noqa: F401  (② classify_question, ④ transform_query, ⑤ generate_answer에서 씀)

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
    PLAN_HUMAN_PROMPT,
    PLAN_SYSTEM_PROMPT,
    QTYPE_CHITCHAT,
    QTYPE_COMPLEX,
    QTYPE_SIMPLE,
    RERANK_MODEL,
    ROLE_ACCESS_LEVELS,
    TECHNIQUE_GUIDE,
    TECHNIQUES,
    TRANSFORM_HUMAN_PROMPT,
    TRANSFORM_SYSTEM_PROMPT,
    AnswerSentence,
    GroundedAnswer,
    QueryTransform,
    QuestionPlan,
    _build_fused_list,
    _get_fused_score,
    _merge_lists,
    _normalize_scores,
    answer_to_text,
    build_signals,
    build_weight_mask,
    card_label,
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
    """실습(빈칸 2곳). 역할과 회원 가명 ID로 벡터 검색용 Chroma 메타데이터 필터를 만듦.

    방법: agent는 public만 봄. auditor가 회원을 지정하면 그 회원의 상담 이력(restricted)만 봄.
          auditor가 회원을 지정하지 않으면 조건이 없음(None = 전부).
    인자: member_pseudo_id는 auditor일 때만 값이 있음(agent면 main이 None으로 넘김).
    반환값: Chroma filter dict 또는 None.
    예시: agent → {"access_level": {"$eq": "public"}}
    """
    if role == "agent":  # 상담사는 약관과 혜택 안내만 봄
        # 빈칸 1: access_level이 "public"과 같은($eq) 청크만 남기는 필터 dict를 return함
        #         ($eq: 메타데이터 값이 이 값과 "같은" 청크만 남김)
        raise NotImplementedError("빈칸 1을 채울 것")
    if member_pseudo_id is None:  # 감사자인데 회원을 지정하지 않음 → 거르지 않음
        return None
    # $and: 목록 안의 조건을 "모두" 만족하는 청크만 남김
    # 빈칸 2: "$and" 목록에 조건 두 개를 넣은 dict를 return함
    #         (access_level이 "restricted"와 같고, member_pseudo_id가 member_pseudo_id와 같은 청크)
    raise NotImplementedError("빈칸 2를 채울 것")


# ===========================================================================
# 2. ② 질문유형 판정: LLM 호출 (교재 152 ~ 155쪽) — 직접 작성
# ===========================================================================
def classify_question(resources: dict, question: str) -> QuestionPlan:
    """실습(직접). ② 질문유형 판정 LLM을 불러 질문 유형과 하위 질문을 「제안」받음(LCEL 체인 + 구조화 출력).

    방법: 프롬프트 | 구조화 모델 체인을 invoke함. LLM은 제안만 하고, 받아들일지는 apply_plan_rules가 정함.
    인자: resources는 main이 만든 dict. resources["llm"]은 Groq LLM, resources["calls"]["llm"]은 LLM 호출 횟수 카운터임.
    반환값: QuestionPlan(question_type, sub_questions, chitchat_reply).
    부수효과: Groq API를 1번 부르고, resources["calls"]["llm"]을 1 올림.

    할 일 1: ChatPromptTemplate.from_messages로 프롬프트를 만듦. 메시지는 ("system", PLAN_SYSTEM_PROMPT), ("human", PLAN_HUMAN_PROMPT)
    할 일 2: resources["llm"].with_structured_output(...)에 QuestionPlan, method="json_schema", strict=True를 넘겨
             구조화 모델을 만듦(strict=True가 없으면 gpt-oss-120b가 스키마를 되돌림)
    할 일 3: prompt와 구조화 모델을 | 로 이어 chain을 만듦(LCEL)
    할 일 4: resources["calls"]["llm"]을 1 올림(LLM 호출 횟수 기록)
    할 일 5: chain.invoke({"question": question})의 결과(QuestionPlan)를 return함
    """
    raise NotImplementedError("여기에 본인 코드를 작성함")


# ===========================================================================
# 3. ② 질문유형 판정: 규칙 확정 (교재 152 ~ 155쪽) — 빈칸 3곳
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
    """실습(빈칸 3곳). LLM이 제안한 질문 유형과 하위 질문을 규칙 5개로 검사해 검색할 질의를 확정함.

    목적: LLM은 제안만 하고, 받아들일지는 코드 규칙이 정함(교재 152쪽). 애매하면 단순 질문으로 처리함.
    인자: condition_terms_of, domain_terms_of는 "문장을 넣으면 낱말 집합을 돌려주는 함수"임(main이 토크나이저를 묶어 넘김).
    반환값: {"type": 유형, "queries": 검색할 질의 목록, "reply": 잡담 답, "warnings": 규칙이 결과를 바꾼 이유}.
            단순이면 queries = [원 질문], 복합이면 queries = 하위 질문 2 ~ 3개, 잡담이면 queries = [].
    """
    # 규칙 1: 약속하지 않은 유형이 오면 단순 질문으로 처리함
    if question_type not in [QTYPE_CHITCHAT, QTYPE_SIMPLE, QTYPE_COMPLEX]:
        return fallback_simple(question, f"알 수 없는 질문 유형 → 단순 처리: {question_type}")

    # 규칙 2: 잡담 판정이어도 업무 낱말이 있으면 단순 질문으로 처리함(업무 질문을 검색 없이 끝내는 쪽이 더 위험함)
    if question_type == QTYPE_CHITCHAT:
        business_words = sorted(domain_terms_of(question))  # 질문 속 업무 낱말(카드명, 숫자, 업무 어휘)
        # 빈칸 1: business_words가 하나라도 있으면(잡담이 아님)
        #         fallback_simple(question, f"잡담 판정이지만 업무 낱말 {business_words[:5]}이 있어 단순 질문으로 처리")를 return함
        raise NotImplementedError("빈칸 1을 채울 것")
        if chitchat_reply.strip() == "":  # 인사 답이 비었으면 검색해 보는 쪽이 안전함
            return fallback_simple(question, "잡담 답이 비어 단순 질문으로 처리")
        return {"type": QTYPE_CHITCHAT, "queries": [], "reply": chitchat_reply.strip(), "warnings": []}

    if question_type == QTYPE_SIMPLE:  # 단순 질문은 원 질문 그대로 1개
        return {"type": QTYPE_SIMPLE, "queries": [question], "reply": "", "warnings": []}

    # 여기부터 복합 질문. 하위 질문의 공백을 정리하고 빈 질문과 중복을 뺌
    texts = []
    for text in sub_questions:
        cleaned = " ".join(text.split())  # 여러 칸 공백, 줄바꿈을 한 칸으로
        if cleaned != "" and cleaned not in texts:
            texts.append(cleaned)

    warnings = []
    # 규칙 4: 하위 질문은 앞에서부터 최대 max_sub_questions개만 씀
    if len(texts) > max_sub_questions:
        warnings.append(f"하위 질문 {len(texts)}개 중 앞 {max_sub_questions}개만 사용")
        # 빈칸 2: texts를 앞 max_sub_questions개만 남긴 목록으로 바꿈(목록 자르기 문법)
        raise NotImplementedError("빈칸 2를 채울 것")

    # 규칙 3: 하위 질문이 1개 이하면 분해가 아니므로 원 질문으로 검색함
    if len(texts) <= 1:
        return fallback_simple(question, "복합 판정인데 하위 질문이 1개 이하라 단순 질문으로 처리")

    # 규칙 5: 하위 질문들이 원 질문의 조건 낱말을 빠뜨리거나(lost) 없던 조건을 만들면(invented) 단순 질문으로 되돌림
    original_terms = condition_terms_of(question)  # 원 질문의 조건 낱말 집합
    union_terms = set()  # 하위 질문들의 조건 낱말을 모두 모은 집합
    for text in texts:
        union_terms = union_terms | condition_terms_of(text)  # | 는 두 집합을 합침
    # 빈칸 3: 집합 빼기(-)로 두 집합을 구함
    #         lost = 원 질문에는 있는데 하위 질문 어디에도 없는 조건, invented = 하위 질문에만 있는 새 조건
    raise NotImplementedError("빈칸 3을 채울 것")
    if len(lost) > 0 or len(invented) > 0:  # noqa: F821
        return fallback_simple(question, f"하위 질문 조건 검사 실패: 빠진 조건 {sorted(lost)}, 새 조건 {sorted(invented)}")  # noqa: F821

    # 모두 통과: 복합 질문으로 확정하고 하위 질문마다 검색함
    return {"type": QTYPE_COMPLEX, "queries": texts, "reply": "", "warnings": warnings}


# ===========================================================================
# 4. ③ 검색: 벡터 (교재 159 ~ 160쪽) — 빈칸 2곳
# ===========================================================================
def search_vector(store, query: str, top_n: int, chroma_filter: dict | None) -> list[dict]:
    """실습(빈칸 2곳). 질의를 임베딩해 Chroma HNSW 근사 검색으로 가까운 청크 top_n개를 찾음(교재 159쪽).

    방법: similarity_search_with_score 한 번이 ① 질의 임베딩(Cohere API) ② 필터를 건 근사 검색을 모두 함.
          돌려받는 거리는 작을수록 가까우므로 점수 = 1 - 거리로 바꿔 "클수록 좋은" 점수로 통일함(BM25, 리랭크와 같은 방향).
    인자: store는 langchain_chroma.Chroma 객체(임베딩 함수가 붙어 있음). chroma_filter는 ①의 결과.
    반환값: {"chunk_id", "text", "metadata", "score", "rank"} 목록(가까운 순서).
    부수효과: Cohere 임베딩 API를 1번 부름.
    """
    # (Document, 거리) 쌍의 목록을 받음. filter에 ①의 권한 필터를 그대로 넘겨 검색 "전에" 거름
    # 빈칸 1: store.similarity_search_with_score(...)에 query, k=top_n, filter=chroma_filter를 넘겨 results에 받음
    raise NotImplementedError("빈칸 1을 채울 것")

    hits = []
    for rank, (document, distance) in enumerate(results, start=1):  # noqa: F821  쌍을 두 변수로 푸는 문법. 순위는 1부터
        # 빈칸 2: 코사인 거리(작을수록 가까움)를 유사도(클수록 가까움)로 바꿔 score에 받음(distance를 float로 바꿀 것)
        raise NotImplementedError("빈칸 2를 채울 것")
        hits.append(
            {
                "chunk_id": document.id,  # 인덱서가 chunk_id를 Chroma id로 저장했으므로 BM25 결과와 같은 키가 됨
                "text": document.page_content,  # 청크 본문
                "metadata": document.metadata,  # 출처, 카드, 권한 등급 등
                "score": score,  # noqa: F821  코사인 거리 → 유사도(클수록 가까움)
                "rank": rank,
            }
        )
    return hits


# ===========================================================================
# 5. ③ 검색: BM25 (교재 157 ~ 158쪽) — 직접 작성
# ===========================================================================
def search_bm25(bm25, chunks: list[dict], query_tokens: list[str], top_n: int, weight_mask=None) -> list[dict]:
    """실습(직접). 저장된 BM25 점수표로 점수가 높은 청크를 top_n개까지 돌려줌(교재 157쪽).

    방법: bm25.get_scores가 청크마다 점수 1개씩 돌려줌(순서는 chunks와 같음). weight_mask(1 또는 0)를 곱해
          권한 밖 청크는 0점이 됨. 0점은 빼고 점수 내림차순으로 정렬함.
    반환값: {"chunk_id", "text", "metadata", "score", "rank"} 목록. 벡터 결과와 같은 꼴이라 융합에서 합칠 수 있음.

    할 일 1: bm25.get_scores(query_tokens, weight_mask=weight_mask)로 청크마다 점수를 받음(numpy 배열, 순서는 chunks와 같음)
    할 일 2: 청크 순번(index)마다 점수를 float(...)로 바꾸고, 0보다 큰 것만 (점수, 순번) 쌍으로 목록에 모음
             (0점 = 질문 토큰이 하나도 없거나 권한 밖인 청크)
    할 일 3: 목록.sort(reverse=True)로 점수 내림차순 정렬((점수, 순번) 쌍은 점수부터 비교됨)
    할 일 4: 앞 top_n개를 enumerate(..., start=1)로 돌며 chunks[순번]에서
             {"chunk_id", "text", "metadata", "score", "rank"} dict를 만들어 목록으로 return함
    """
    raise NotImplementedError("여기에 본인 코드를 작성함")


# ===========================================================================
# 6. ③ 검색: 융합 (교재 161 ~ 162쪽) — 직접 작성
# ===========================================================================
def fuse_weighted(
    vector_hits: list[dict],
    bm25_hits: list[dict],
    vector_weight: float = 0.6,
    bm25_weight: float = 0.4,
) -> list[dict]:
    """실습(직접). 벡터와 BM25 점수를 각각 0 ~ 1로 정규화한 뒤 가중합으로 합침(교재 161쪽 「정규화 가중합」).

    방법: 한쪽 검색에만 있는 청크는 없는 쪽 점수를 0으로 봄. fused_score = 0.6 × 벡터 정규화 + 0.4 × BM25 정규화.
    반환값: {"chunk_id", "text", "metadata", "fused_score", "found_in", "rank"} 목록(점수 내림차순).

    할 일 1: _normalize_scores로 두 결과를 각각 {chunk_id: 0 ~ 1} dict로 만듦
             (vector_normalized_scores, bm25_normalized_scores)
    할 일 2: _merge_lists([vector_hits, bm25_hits], ["vector", "bm25"])로 chunk_id 묶음 표(merged)를 만듦
    할 일 3: merged의 chunk_id마다 vector_weight × 벡터 정규화 + bm25_weight × BM25 정규화를 계산해
             fused_scores[chunk_id]에 넣음(한쪽 검색에 없으면 그쪽은 0점)
    할 일 4: _build_fused_list(merged, fused_scores)를 return함
    """
    raise NotImplementedError("여기에 본인 코드를 작성함")


# ===========================================================================
# 7. ③ 검색: 리랭크 (교재 163 ~ 166쪽) — 빈칸 2곳
# ===========================================================================
def rerank(
    question: str,
    candidates: list[dict],
    cohere_client,
    top_k: int,
    model_name: str = RERANK_MODEL,
) -> list[dict]:
    """실습(빈칸 2곳). Cohere 리랭커로 후보를 다시 채점해 상위 top_k개를 돌려줌(교재 164쪽).

    목적: 1차 검색은 질문과 청크를 따로 벡터로 만들어 비교하지만, 리랭커는 질문과 청크를 한 쌍으로 읽어 관련성을 더 정확히 매김.
    방법: 후보 본문 목록을 API에 한 번 보내고, 응답의 index(보낸 목록의 순번)와 relevance_score(0 ~ 1)로 후보를 다시 고름.
    인자: question은 변환 질의가 아니라 원 질의(하위 질문)임. cohere_client는 cohere.ClientV2 객체.
    반환값: 후보 항목에 "rerank_score", "fused_rank"(리랭크 전 순위), 새 "rank"를 더한 목록(점수 내림차순 top_k개).
    부수효과: Cohere 리랭크 API를 1번 부름.
    """
    if len(candidates) == 0:  # 후보가 없으면 API를 부르지 않음
        return []

    documents = []  # 리랭커에 보낼 본문 목록. 순서가 곧 응답 index의 기준임
    for candidate in candidates:
        documents.append(candidate["text"])

    # 질문과 본문 목록을 한 번에 보냄
    # 빈칸 1: cohere_client.rerank(...)에 model=model_name, query=question, documents=documents,
    #         top_n=top_k(점수가 높은 top_k개만 돌려받음)를 넘겨 response에 받음
    raise NotImplementedError("빈칸 1을 채울 것")

    reranked = []
    for rank, result in enumerate(response.results, start=1):  # noqa: F821  results는 relevance_score 내림차순
        # 빈칸 2: result.index로 candidates에서 원래 후보를 찾고, 원본을 바꾸지 않도록 dict(...)로 복사해 candidate에 받음
        raise NotImplementedError("빈칸 2를 채울 것")
        candidate["fused_rank"] = candidate["rank"]  # noqa: F821  리랭크 전(융합) 순위를 남겨 순위 변화를 보여 줌
        candidate["rerank_score"] = float(result.relevance_score)  # noqa: F821  관련성 점수(0 ~ 1)
        candidate["rank"] = rank  # noqa: F821  새 순위
        reranked.append(candidate)  # noqa: F821
    return reranked


# ===========================================================================
# 8. ④ 검색결과 검증 (교재 149, 171쪽) — 직접 작성
# ===========================================================================
def grade(signals: dict, thresholds: dict) -> str:
    """실습(직접). 판정 근거로 정확, 불확실, 부정확 중 하나를 돌려줌(교재 149쪽 「판정 규칙」).

    방법: ① 부정확(하나라도): 결과 0건, 1위 점수 < 하한
          ② 정확(모두): 리랭크 성공, 1위 ≥ 상한, 핵심어 포함, 대상 일치, 격차 ≥ 최소 격차,
             검색기 겹침 ≥ 최소 겹침(1위가 면제 기준 이상이면 겹침 조건 면제)
          ③ 나머지는 불확실
    인자:
    - signals: core_search.build_signals의 docstring 반환값 참조
    - thresholds는 main의 THRESHOLDS(upper, lower, min_gap, min_overlap, overlap_waiver).

    할 일 1: signals["result_count"]가 0이면 GRADE_INCORRECT를 return함
    할 일 2: signals["main_score"]가 None이 아니고 thresholds["lower"] 미만이면 GRADE_INCORRECT를 return함
    할 일 3: 겹침 조건 overlap_ok를 구함. signals["overlap"] ≥ thresholds["min_overlap"]이면 True,
             main_score가 None이 아니고 thresholds["overlap_waiver"] 이상이어도 True
    할 일 4: 아래를 모두 만족하면 GRADE_CORRECT를 return함(signals["reranked"]를 맨 앞에 두어야 main_score가 None일 때 비교하지 않음)
             signals["reranked"], main_score ≥ thresholds["upper"], signals["keyword_match"], signals["target_match"],
             signals["gap"] ≥ thresholds["min_gap"], overlap_ok
    할 일 5: 나머지는 GRADE_UNCERTAIN을 return함(main이 질문을 바꿔 한 번 더 검색함)
    """
    raise NotImplementedError("여기에 본인 코드를 작성함")


# ===========================================================================
# 9. ④ 질문 변환: LLM 호출 (교재 169쪽) — 빈칸 3곳
# ===========================================================================
def transform_query(
    resources: dict, query: str, reasons: list[str], final_hits: list[dict], previous: list[str]
) -> QueryTransform:
    """실습(빈칸 3곳). ④ 질문 변환 LLM을 불러 질의를 어떻게 고칠지 「제안」받음(교재 169쪽). LCEL 체인 + 구조화 출력.

    방법: 판정 근거(reasons), 검색 결과, 이전에 검색한 질의를 프롬프트에 함께 주고 QueryTransform 칸을 채우게 함.
          LLM은 기법과 질의를 제안만 하고, 받아들일지는 apply_transform_rules가 정함.
    인자: reasons는 main이 describe_signals로 만든 판정 근거 문장 목록, final_hits는 리랭크 뒤 근거,
          previous는 이미 검색한 질의 목록.
    반환값: QueryTransform(technique, queries, clarify_question, reason).
    부수효과: Groq API를 1번 부르고, resources["calls"]["llm"]을 1 올림.
    """
    result_lines = []  # 프롬프트에 넣을 검색 결과 줄 목록(청크ID, 카드, 리랭크 점수, 본문 앞 150자)
    for hit in final_hits:
        # 빈칸 1: hit에서 "rerank_score"를 꺼내 score에 받음. 리랭크가 실패해 이 키가 없으면 0.0을 씀(dict.get의 두 번째 인자)
        raise NotImplementedError("빈칸 1을 채울 것")
        result_lines.append(f"[{hit['chunk_id']} | {card_label(hit)} | 리랭크 {score:.2f}] {hit['text'][:150]}")  # noqa: F821
    prompt = ChatPromptTemplate.from_messages([("system", TRANSFORM_SYSTEM_PROMPT), ("human", TRANSFORM_HUMAN_PROMPT)])
    # 구조화 모델: LLM이 QueryTransform 칸을 채운 JSON으로 답하게 함. strict=True가 없으면 gpt-oss-120b가 스키마를 되돌림(실측)
    # 빈칸 2: resources["llm"].with_structured_output(...)에 QueryTransform, method="json_schema", strict=True를 넘겨
    #         structured_llm에 받음
    raise NotImplementedError("빈칸 2를 채울 것")
    # 빈칸 3: prompt와 structured_llm을 | 로 이어 chain을 만듦(LCEL: 프롬프트를 채운 결과가 구조화 모델로 흘러감)
    raise NotImplementedError("빈칸 3을 채울 것")
    resources["calls"]["llm"] = resources["calls"]["llm"] + 1
    return chain.invoke(  # noqa: F821
        {
            "guide": TECHNIQUE_GUIDE,
            "query": query,
            "reasons": "\n".join(reasons),
            "results": "\n".join(result_lines),
            "previous": "\n".join(previous),
        }
    )


# ===========================================================================
# 10. ④ 질문 변환: 금지 규칙 (교재 169, 172쪽) — 빈칸 3곳
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
    """실습(빈칸 3곳). LLM이 고른 질문 변환에 금지 규칙을 적용해 최종 결정을 만듦(교재 169쪽 「금지 규칙」).

    방법: ① 대상명 없음 + 대상 섞임이면 LLM 답과 상관없이 clarify ② 허용 선택지 밖 기법은 keep
          ③ keep, clarify 처리 ④ 원 질의나 이전 질의와 같은 질의는 버리고, 남은 질의가 없으면 keep
          ⑤ HyDE, Step-Back은 원 질의도 함께 검색함
    인자: target_query는 불확실 판정을 받은 원 질의, forced_clarify는 mixed_target_clarify의 결과(없으면 None).
    반환값: {"technique", "queries", "include_original", "clarify_question", "reason", "warnings"}.
            queries는 재검색할 질의(최대 3개), include_original이 True면 원 질의도 함께 검색함.
    """
    decision = {"technique": KEEP, "queries": [], "include_original": False,
                "clarify_question": "", "reason": reason, "warnings": []}

    # 규칙 ①: 대상명 없음 + 대상 섞임 → 코드가 만든 확인 질문으로 되물음
    if forced_clarify is not None:
        # 빈칸 1: decision의 "technique"를 CLARIFY로, "clarify_question"을 forced_clarify로 바꾸고
        #         "warnings"에 "대상명 없음 + 대상 섞임 → clarify"를 더한 뒤 decision을 return함
        raise NotImplementedError("빈칸 1을 채울 것")

    # 규칙 ②: 허용 선택지(기법 4가지 + keep + clarify) 밖이면 keep
    if technique not in ALLOWED_TECHNIQUES:
        decision["warnings"].append(f"허용 선택지 밖 기법 거부: {technique}")
        return decision

    # 규칙 ③: keep은 그대로, clarify는 확인 질문이 있어야 받아들임
    if technique == KEEP:
        return decision
    if technique == CLARIFY:
        if clarify_question.strip() == "":
            decision["warnings"].append("확인 질문이 비어 clarify 거부 → keep")
            return decision
        decision["technique"] = CLARIFY
        decision["clarify_question"] = clarify_question.strip()
        return decision

    # 규칙 ④: 원 질의, 이전 질의와 같은 질의(공백과 대소문자만 다른 것 포함)는 버림
    seen = [normalize_query(target_query)]  # 이미 검색한 질의 목록(비교용 꼴)
    for previous in previous_queries:
        seen.append(normalize_query(previous))
    kept = []
    for query in queries:
        key = normalize_query(query)
        if key == "":
            continue  # 빈 질의는 버림
        # 빈칸 2: key가 seen에 있으면(이미 검색한 질의와 같음 → 같은 결과가 나오므로 버림)
        #         decision["warnings"]에 f"같은 질의 반복 제외: {query[:40]}"를 더하고 다음 질의로 넘어감(continue)
        raise NotImplementedError("빈칸 2를 채울 것")
        seen.append(key)  # 변환 질의끼리도 중복되지 않게 기록
        kept.append(query.strip())
        if len(kept) == MAX_TRANSFORM_QUERIES:
            break
    if len(kept) == 0:  # 쓸 질의가 없으면 재검색하지 않음
        decision["warnings"].append("쓸 수 있는 변환 질의 없음 → keep")
        return decision

    # 규칙 ⑤: HyDE와 Step-Back은 질문을 크게 바꾸므로 원 질의도 함께 검색함
    decision["technique"] = technique
    decision["queries"] = kept
    # 빈칸 3: technique가 ORIGINAL_REQUIRED에 있으면 True, 아니면 False를 decision["include_original"]에 넣음
    raise NotImplementedError("빈칸 3을 채울 것")
    return decision


# ===========================================================================
# 11. ⑤ 답변 생성 (교재 173쪽) — 빈칸 2곳
# ===========================================================================
def generate_answer(llm, question: str, hits: list[dict], failures: list[str] | None = None) -> GroundedAnswer:
    """실습(빈칸 2곳). 근거 청크만으로 문장별 인용이 달린 답을 만듦(LCEL 체인 + 구조화 출력).

    방법: 프롬프트 | 구조화 모델 체인을 invoke함. 재작성 때는 ⑥의 실패 사유(failures)를 프롬프트에 함께 넣음.
    반환값: GroundedAnswer(sentences, missing). 근거가 0건이면 LLM을 부르지 않고 missing만 채워 돌려줌.
    부수효과: Groq API를 1번 부름.
    """
    if len(hits) == 0:  # 근거가 없으면 LLM을 부르지 않음(지어낼 재료가 없음)
        return GroundedAnswer(sentences=[], missing="권한 범위 안에서 검색된 근거가 없음")

    feedback = "없음"  # 첫 시도
    if failures:  # 재작성: 무엇이 틀렸는지 알려 줘야 같은 실수를 되풀이하지 않음
        feedback = "\n".join(failures)

    prompt = ChatPromptTemplate.from_messages([("system", ANSWER_SYSTEM_PROMPT), ("human", ANSWER_HUMAN_PROMPT)])
    # 구조화 모델: LLM이 GroundedAnswer 칸을 채운 JSON으로 답하게 함. strict=True가 없으면 gpt-oss-120b가 스키마를 되돌림(실측)
    # 빈칸 1: llm.with_structured_output(...)에 GroundedAnswer, method="json_schema", strict=True를 넘겨 structured_llm에 받음
    raise NotImplementedError("빈칸 1을 채울 것")
    # 빈칸 2: prompt와 structured_llm을 | 로 이어 chain을 만듦(LCEL: 프롬프트를 채운 결과가 구조화 모델로 흘러감)
    raise NotImplementedError("빈칸 2를 채울 것")
    answer = chain.invoke({"question": question, "evidence": format_evidence(hits), "feedback": feedback})  # noqa: F821
    return answer


# ===========================================================================
# 12. ⑥ 답변 검증 (교재 174쪽) — 직접 작성
# ===========================================================================
def verify_answer(answer: GroundedAnswer, evidence_texts: dict) -> list[str]:
    """실습(직접). 답의 인용을 근거 본문과 대조해 실패 사유 목록을 돌려줌. 빈 목록이면 통과.

    방법: 문장마다 ① 청크ID가 비었는지 ② 청크ID가 근거 묶음(evidence_texts)에 있는지
          ③ 인용문이 그 청크 본문에 글자 그대로 있는지(compact_text로 공백을 지우고 비교) 봄.
    인자: evidence_texts는 이번에 ⑤에 넘긴 근거의 {청크ID: 본문}.
    반환값: 실패 사유 문자열 목록. 사유는 ⑤ 재작성 프롬프트로 그대로 넘기므로 문장 번호를 1부터 적음.

    answer.sentences를 enumerate(..., start=1)로 돌며 문장마다(number는 문장 번호, sentence는 문장):
      검사 ①: sentence.chunk_id.strip()이 비었으면
              f"{number}번 문장에 근거 청크ID가 없음: {sentence.text[:40]}"를 더하고 다음 문장으로(continue)
      검사 ②: sentence.chunk_id가 evidence_texts에 없으면(지어낸 인용으로 봄)
              f"{number}번 문장이 근거에 없는 청크ID를 인용함: {sentence.chunk_id}"를 더하고 다음 문장으로(continue)
      검사 ③: compact_text(인용문 sentence.quote)가 비었거나 compact_text(그 청크 본문) 안에 없으면
              f"{number}번 문장의 인용문이 {sentence.chunk_id} 본문과 글자 그대로 맞지 않음: \"{sentence.quote[:40]}\""를 더함
    """
    raise NotImplementedError("여기에 본인 코드를 작성함")


# ---------------------------------------------------------------------------
# 아직 채우지 않은 함수는 강사 코드(core_search)로 대신 돌게 함.
# 함수를 채울 때마다 그 이름을 아래 목록에서 지움. 목록이 비면 이 파일의 코드만으로 전체가 돎.
# 막히면 이름을 다시 넣어 뒤 단계를 계속함(실습이 멈추지 않음)
# ---------------------------------------------------------------------------
import core_search as _teacher  # noqa: E402

USE_TEACHER_CODE = [
    "build_chroma_filter", "classify_question", "apply_plan_rules", "search_vector",
    "search_bm25", "fuse_weighted", "rerank",
    "grade", "transform_query", "apply_transform_rules", "generate_answer", "verify_answer",
]
for _name in USE_TEACHER_CODE:
    globals()[_name] = getattr(_teacher, _name)  # 이 파일의 빈 함수 대신 강사 함수를 같은 이름으로 둠
