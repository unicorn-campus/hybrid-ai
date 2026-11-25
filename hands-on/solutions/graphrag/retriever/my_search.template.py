"""교육생용 뼈대: core_search.py와 같은 이름, 같은 인자의 실습 함수 13개를 본인 코드로 채우는 파일임.

채우는 순서(워크플로우 순서). "직접"은 NotImplementedError 자리에 본인 코드를 쓰고, "빈칸"은 거의 완성된 코드의 빈칸만 채움
  [교시 2]
   1 jev_route                (직접)       W2 질문 분석: Jev에 판정 요청
   2 build_agent              (직접)       W3 검색 에이전트: create_agent로 ReAct 루프
   3 ToolWrapperMiddleware    (직접)       W4 래퍼와 W5 채점: 툴 호출 감싸기(wrap_tool_call)
   4 run_tool                 (직접)       W4 툴 실행: 래퍼
  [교시 3]
   5 read_chunk_texts         (직접)       W4 원문 글 읽기
   6 search_engine            (빈칸 2곳)    W4 O 검색엔진 검색: O1 벡터, O2 BM25, O3, O4
   7 rrf_merge                (직접)       W4 O 검색엔진 검색: RRF
   8 local_search             (빈칸 2곳)    W4 L Local 검색: L1 두 갈래, L2, L3, L4
   9 narrow_entities          (직접)       W4 L Local 검색: L1 갈래 A 엔티티 축소
  10 global_search            (빈칸 3곳)    W4 G Global 검색: G1, G2, G3
  [교시 4]
  11 jev_judge_passages       (직접)       W5 채점: Jev 청크 판정
  12 rerank                   (직접)       W6 리랭킹(O4 포함): Cohere 리랭커
  13 generate_answer          (직접)       W8 답변 생성: LCEL 체인 + 구조화 출력
  제공(완성본, 읽기만): 상수, 프롬프트와 스키마, 도구, 제공 함수는 core_search에서 그대로 가져옴(아래 import)

사용법(이 파일은 강사 뼈대(템플릿)임. 직접 고치지 않고 복사본 my_search.py를 고침. my_search.py는 Git이 무시해 pull 충돌이 없음)
  1) "python search_graph.py --mine --qid Q01"처럼 --mine을 붙여 실행함. my_search.py가 없으면 이 파일을 복사해 만듦
  2) 채울 함수 이름을 이 파일 맨 아래 USE_TEACHER_CODE 목록에서 지움(지우지 않은 함수는 강사 코드가 대신 돎)
  3) 함수를 채우고 같은 명령(예: --qid Q01)으로 실행해 강사 결과와 비교함. 막히면 이름을 목록에 다시 넣고 다음 함수로 넘어감
"""

import traceback
from concurrent.futures import ThreadPoolExecutor

from langchain.agents import create_agent
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import ToolMessage
from typesafe_sdk import Choice, Noul

# 제공 상수, 프롬프트와 스키마, 도구, 제공 함수: 강사 코드(core_search.py)의 것을 그대로 씀(읽고 이해만 함)
#   main(search_graph.py)이 core.이름으로 부르는 제공 함수도 여기서 가져와 둬야 --mine 실행이 됨
from core_search import (  # noqa: F401
    # 상수와 설정값
    CLAUSE_PATTERN, END_STATES, MEMBER_ID_PATTERN, NUMBER_PATTERN, PSEUDO_ID_PATTERN, ROLES, TREND_WORDS,
    G_FALLBACK_REPORTS, G_MAX_REPORTS, G_MAX_TOPICS, G_REPORT_TOKENS, L_ENTITIES, L_NEIGHBORS, L_REPORTS,
    L2_WEIGHT_ENGINE, O_CANDIDATES, O_KEEP, PASSAGE_QUESTIONS, PASSAGE_THRESHOLDS, REPORT_RELEVANCE_MIN, RERANK_MODEL,
    LABEL_OF, PROPS_OF, SIMILARITY_OF,
    # 프롬프트와 스키마
    G1_PROMPT, G2_PROMPT, AnswerSentence, GroundedAnswer, PickedReports, Topic, TopicPlan,
    # 도구
    PRINT_LOCK, record_outcome, say, short,
    # 제공 함수
    allowed_chunk_ids, apply_passage_judgments, block_calls, candidate_pairs, check_ready, check_tool_input,
    core_terms, cosine, count_cooccur, coverage, decide_collection, decide_question_route, diagnose_signals,
    embed_query, entity_allowed_clause, force_stop_reason, keep_linked_entities, make_end_state, member_pseudonym,
    merge_entity_lists, neighbors_and_reports, recheck_question, replace_identifiers, select_final_chunks,
    split_sentences, spread, strip_identifiers, verify_answer, wrap_chunks,
)


# ===========================================================================
# 1. W2 질문 분석: Jev에 판정 요청 — 직접 작성
# ===========================================================================
def jev_route(res, question: str, ctx: dict) -> dict | None:
    """W2 질문 분석: Jev에 잡담, 모호, 첫 툴을 묻고 확률만 받아 옴. 결정은 decide_question_route가 함.

    목적: 검색할 필요가 없거나(잡담) 무엇을 묻는지 모르는(모호) 질문을 걸러 내고, 첫 툴 후보를 얻음.
    인자: res.jev는 TypeSafe 클라이언트, question은 식별자를 지운 질문, ctx는 이 요청의 작업 기록.
    방법: (1) 보기 3개(criteria: 툴 이름 → 그 툴을 고를 질문 유형, 영어)와 순서를 뒤집은 사본(swapped)을 만듦
          (2) 요청 1: res.jev.system_one(state={"question": question}, questions={잡담 Noul, 모호 Noul, 첫 툴 Choice})
          (3) 요청 2: 뒤집은 보기로 첫 툴 Choice만 다시 물음(첫 보기 쏠림 대비). 요청마다 ctx["calls"]["jev"]를 셈
          (4) 실패하면 ctx["warnings"]에 남기고 None
    질문 문장은 영어로 씀(Jev는 영어가 가장 정확). 자료(state)는 식별자를 지운 한국어 질문 그대로 보냄.
    반환값: {"is_smalltalk": 확률, "needs_clarification": 확률, "first_tool": (답, 확신), "first_tool_swapped": (답, 확신)}
    """
    raise NotImplementedError("여기에 본인 코드를 작성함")


# ===========================================================================
# 2. W3 검색 에이전트: create_agent로 ReAct 루프 — 직접 작성
# ===========================================================================
def build_agent(model, tools: list, system_prompt: str, middleware: list, first_message: str, context: dict,
                recursion_limit: int) -> dict:
    """LangChain create_agent로 「생각 → 툴 호출 → 관찰」 루프를 만들고 돌려서 마지막 상태를 돌려줌.

    목적: 툴 고르기는 에이전트 모델(Groq)이 하고, 막는 일(상한, 강제 종료, 필터, 채점)은 미들웨어 코드가 하게 묶음.
    방법: 모델, 툴 5개, 시스템 프롬프트, 미들웨어 목록을 create_agent에 넘겨 에이전트를 만들고,
          첫 메시지(W2의 결과)와 이 요청의 작업 기록(context)을 주어 한 번 돌림. 메시지는 덧붙이기만 됨.
    반환값: 에이전트의 마지막 상태(dict). "messages"에 모든 대화(생각, 툴 호출, 관찰)가 순서대로 있음.
    """
    raise NotImplementedError("여기에 본인 코드를 작성함")


# ===========================================================================
# 3. W4 래퍼와 W5 채점: 툴 호출 감싸기(wrap_tool_call) — 직접 작성
# ===========================================================================
class ToolWrapperMiddleware(AgentMiddleware):
    """W4 래퍼와 W5 채점: 막힌 호출은 실행하지 않고 오류 표시로 돌려주고, 실행한 결과에는 Jev 판정과 진단 신호를 붙임.

    score_result: W5 채점 함수(main의 score_result). 만들 때 넘겨받아 실행한 툴 결과마다 부름.
    """

    def __init__(self, score_result):
        super().__init__()
        self.score_result = score_result

    def wrap_tool_call(self, request, handler):
        """툴 호출 하나를 감쌈: 막힌 호출은 오류 표시로 돌려주고, 실행한 결과에는 W5 채점 글을 덧붙임.

        인자: request.tool_call은 {"id", "name", "args"}, request.runtime.context는 작업 기록(ctx),
              handler(request)는 툴을 실제로 실행해 ToolMessage를 돌려줌.
        방법: (1) ctx["blocked"]에 있는 호출은 실행하지 않고 record_outcome(실패)을 적은 뒤
                  status="error"인 ToolMessage(「더 부를 수 없음. 지금 근거로 finish할 것(이유)」)를 돌려줌
              (2) handler(request)로 실행함
              (3) finish면 채점하지 않고 그대로 돌려줌
              (4) ctx["call_results"][호출 id]에 error가 있으면 status를 "error"로 하고 record_outcome(실패)
              (5) 그 밖은 self.score_result(ctx, call, 결과)가 만든 채점 글을 관찰 끝에 덧붙임.
                  채점 중 예외가 나면 traceback을 ctx["fatal"]에 적음
        반환값: ToolMessage(에이전트가 받는 관찰)
        """
        raise NotImplementedError("여기에 본인 코드를 작성함")


# ===========================================================================
# 4. W4 툴 실행: 래퍼 — 직접 작성
# ===========================================================================
def run_tool(name: str, args: dict, ctx: dict, tool_functions: dict) -> dict:
    """에이전트의 툴 호출 하나를 실행하는 래퍼. 입력 검사, 질의 속 식별자 지우기, 필터 강제, 태그 감싸기를 함.

    목적: 에이전트가 무엇을 고르든 세대와 식별자 필터를 벗어나지 못하게 함(툴 입력에는 필터 칸이 없음).
    인자: ctx는 이 요청의 작업 기록(필터 값, 주제 목록 등), tool_functions는 {툴 이름: 서브 워크플로우 함수}.
    반환값: text(에이전트에게 돌려줄 관찰 글), result(서브 워크플로우 결과), error(입력 오류면 True)
    """
    raise NotImplementedError("여기에 본인 코드를 작성함")


# ===========================================================================
# 5. W4 원문 글 읽기 — 직접 작성
# ===========================================================================
def read_chunk_texts(res, ctx: dict, chunk_ids: list[str]) -> dict:
    """청크 id로 원문 글을 검색엔진에서 읽음(mget 한 번). 이 요청 안에서 한 번 읽은 글은 다시 읽지 않음.

    목적: 그래프의 Chunk 노드에는 글이 없음(ID와 최소 속성만). 글은 검색엔진(벡터 저장소)에만 있어
          툴이 청크 id를 얻은 뒤 필요한 청크만 그때그때 읽음.
    쓰는 곳: 관찰 글, W5 채점, W6 리랭킹, W7 수집 종료 판정(재확인), W8 답변 생성(근거 묶음)
    반환값: {chunk_id: 글}. 못 읽은 청크는 빈 글("")로 돌려주고 경고를 남김(다음에 다시 읽어 봄).
    """
    raise NotImplementedError("여기에 본인 코드를 작성함")


# ===========================================================================
# 6. W4 O 검색엔진 검색: O1 벡터, O2 BM25, O3, O4 — 빈칸 2곳(O1, O2)
# ===========================================================================
def search_engine(res, query: str, filters: dict, ctx: dict) -> dict:
    """O 검색엔진 검색: O1 벡터 검색 + O2 BM25 검색(같은 필터) → O3 RRF → O4 리랭킹(최대 6).

    필터(볼 수 있는 청크 표)를 두 검색에 똑같이 걸고, 필터 뒤 후보가 6개 이하면 O4를 건너뜀.
    한쪽 검색이 실패해도 남은 순위로 결과를 냄(RRF를 코드에서 계산하는 까닭).
    """
    # 준비: 두 검색에 똑같이 걸 필터(볼 수 있는 청크 표)와 질의 임베딩
    index = filters["index"]
    allowed = sorted(filters["allowed_ids"])
    id_filter = {"ids": {"values": allowed}}
    vector_hits, bm25_hits = [], []
    vector = embed_query(res, query, ctx)

    # --- O1 벡터 검색: 질의 임베딩으로 kNN 25개(lucene 엔진은 필터를 검색 안에서 걺). 실패해도 경고만 남기고 계속
    # 빈칸 1(O1 벡터 검색): vector가 None이 아니면 kNN 질의로 O_CANDIDATES개를 찾아 vector_hits에
    #   [{"chunk_id": h["_id"]}, …]로 받음. 질의 body는
    #   {"size": O_CANDIDATES, "_source": False,
    #    "query": {"knn": {"embedding": {"vector": vector, "k": O_CANDIDATES, "filter": id_filter}}}}
    #   검색은 res.os.search(index=index, body=body)["hits"]["hits"]. 실패하면 ctx["warnings"]에 남기고 계속
    raise NotImplementedError("빈칸 1(O1 벡터 검색)을 채울 것")

    # --- O2 BM25 검색: 색인과 같은 토크나이저로 질의를 낱말로 나눠 25개. 실패해도 경고만 남기고 계속
    # 빈칸 2(O2 BM25 검색): res.ready_data["tokenizer"].tokenize(query)로 질의를 낱말로 나눠 공백으로 잇고,
    #   {"bool": {"must": {"match": {"text_tokens": 낱말들}}, "filter": id_filter}} 질의로 O_CANDIDATES개를
    #   찾아 bm25_hits에 [{"chunk_id": h["_id"]}, …]로 받음. 실패하면 ctx["warnings"]에 남기고 계속
    raise NotImplementedError("빈칸 2(O2 BM25 검색)를 채우고 이 줄을 지울 것")

    # --- O3 RRF 병합: 두 순위를 점수 대신 순위로만 합쳐 25개(실습 함수 rrf_merge)
    fused = rrf_merge(vector_hits, bm25_hits, k=60, top=O_CANDIDATES)

    # --- 글 읽기: 검색은 id만 받았으므로 리랭크 전에 청크 글을 읽어 한 줄씩 만듦(점수는 우선 RRF 점수)
    texts = read_chunk_texts(res, ctx, [row["chunk_id"] for row in fused])
    rows = []
    for row in fused:
        meta = res.ready_data["chunk_meta"][row["chunk_id"]]
        rows.append({"chunk_id": row["chunk_id"], "short_id": meta["short_id"], "text": texts[row["chunk_id"]],
                     "ranks": row["ranks"], "score": row["rrf"]})

    # --- O4 리랭킹: 후보가 6개보다 많을 때만 Cohere 리랭커로 다시 채점해 줄 세움(실패하면 RRF 순위 그대로)
    if len(rows) > O_KEEP:
        scores = rerank(res, query, [r["text"] for r in rows], ctx)
        if scores is not None:
            for row, score in zip(rows, scores):
                row["score"] = score
            rows.sort(key=lambda r: r["score"], reverse=True)

    # 리턴: 상위 6개 청크와 두 검색의 후보 수(관찰 글에 보임)
    return {"chunks": rows[:O_KEEP], "n_vector": len(vector_hits), "n_bm25": len(bm25_hits)}


# ===========================================================================
# 7. W4 O 검색엔진 검색: RRF — 직접 작성
# ===========================================================================
def rrf_merge(vector_hits: list[dict], bm25_hits: list[dict], k: int = 60, top: int = 25) -> list[dict]:
    """벡터 검색과 BM25 검색의 두 순위를 RRF(점수 대신 순위만 쓰는 합치기)로 합침.

    방법: 청크마다 RRF 점수 = Σ 1 / (k + 순위). 두 검색에 모두 나오면 두 값을 더하고, 한쪽에만 있으면 한 값만.
          점수 내림차순으로 줄 세워 상위 top개.
    인자: vector_hits, bm25_hits는 순위 순서의 [{"chunk_id": ...}] 목록. 한쪽이 빈 목록이어도 됨(부분결과).
    반환값: [{"chunk_id", "rrf", "ranks": {"vector": 순위, "bm25": 순위}}]
    예시: A가 벡터 1위, BM25 3위 → 1/61 + 1/63 ≈ 0.0323 / B가 벡터 2위만 → 1/62 ≈ 0.0161
    """
    raise NotImplementedError("여기에 본인 코드를 작성함")


# ===========================================================================
# 8. W4 L Local 검색: L1 두 갈래, L2, L3, L4 — 빈칸 2곳(L1 갈래 A 후보, L1 갈래 B)
# ===========================================================================
def local_search(res, query: str, topic_id: str | None, filters: dict, ctx: dict) -> dict:
    """L Local 검색: L1 두 갈래 검색 → L2 엔티티 합치기(16) → L3 이웃(각 4) → L4 보고서(3).

    갈래 A: 검색엔진 검색(O, 청크 6) → 청크에서 나온 엔티티를 질문 유사도로 16개로 축소(실습 함수 narrow_entities).
    갈래 B: 이번 세대 엔티티 전체와 질문을 비교해 설명(K6 임베딩)이 가까운 16개.
    두 갈래 모두 엔티티라 같은 단위로 가중합(검색엔진 0.7, 엔티티 설명 코사인 0.3)해 16개로 합침.
    G3 주제별 Local 검색은 원 질문 대신 주제의 Follow-up 질문을 query로, 주제 번호를 topic_id로 넘겨 부름.
    """
    # --- L1 갈래 A 시작: 검색엔진 검색(O)으로 청크 6개. 같은 필터가 걸림
    found = search_engine(res, query, filters, ctx)
    chunks = found["chunks"]
    vector = embed_query(res, query, ctx)  # 질문 벡터(Cohere). 갈래 A의 유사도와 갈래 B, L3에 씀. 실패하면 None

    # --- L1 갈래 A 후보: 청크 6개에서 FROM_CHUNK를 거꾸로 따라가 엔티티를 찾고, 질문 유사도를 score로 붙임
    # 빈칸 1(L1 갈래 A 후보): chunks가 있으면 청크 id마다 FROM_CHUNK를 거꾸로 따라가 엔티티를 찾는 Cypher를
    #   res.run으로 부르고 [dict(r) for r in records]를 candidates에 받음(chunks가 없으면 빈 목록)
    #   MATCH (c:Chunk {generation: $g, chunk_id: cid})<-[:FROM_CHUNK]-(n:__Entity__), WHERE는 entity_allowed_clause("n")
    #   RETURN 칸: chunk_id, id(elementId(n)), label(LABEL_OF), props(PROPS_OF),
    #             chunk_ids([(n)-[:FROM_CHUNK]->(s:Chunk) | s.chunk_id]), score(SIMILARITY_OF)
    #   매개변수: cids, g=filters["generation"], allowed=sorted(filters["allowed_ids"]), qv=vector
    raise NotImplementedError("빈칸 1(L1 갈래 A 후보)을 채울 것")

    # --- L1 갈래 A 축소: 청크마다 1개를 보장하고 남은 자리는 유사도 순으로 16개(실습 함수 narrow_entities)
    list_a = narrow_entities(candidates, limit=L_ENTITIES)

    # --- L1 갈래 B: 이번 세대 엔티티 전체와 코사인을 직접 비교해 상위 16개(벡터 인덱스를 쓰지 않음)
    #     인덱스 kg_entity_embedding은 모든 세대가 한 인덱스에 섞여 있어 「상위 k → 세대 거르기」로는 많이 놓침
    #     (평가셋 10문항 실측 37/80). 직접 비교는 빠짐없이 찾고, 이번 세대 엔티티 약 1,650개라 0.1초 안팎임
    # 빈칸 2(L1 갈래 B): vector가 있으면 이번 세대 엔티티(n:__Entity__ {generation: $g}) 중 n.embedding이 있고
    #   entity_allowed_clause("n")을 지키는 것과 질문 벡터의 코사인(vector.similarity.cosine(n.embedding, $qv))을
    #   직접 비교해 상위 L_ENTITIES개를 list_b에 받음(vector가 없으면 빈 목록). RETURN 칸은 갈래 A와 같음(chunk_id 빼고)
    raise NotImplementedError("빈칸 2(L1 갈래 B)를 채우고 이 줄을 지울 것")

    # --- L2 두 갈래 합치기: 0.7 × 검색엔진(청크) 점수 + 0.3 × 엔티티 설명 코사인으로 16개
    chunk_scores = {c["chunk_id"]: c["score"] for c in chunks}
    entities = merge_entity_lists(list_a, list_b, chunk_scores, L_ENTITIES)

    # --- L3 이웃 탐색(엔티티마다 4개)과 L4 커뮤니티 보고서(3개)
    graph = neighbors_and_reports(res, [e["id"] for e in entities], vector, filters)

    # 리턴: 청크, 엔티티, 이웃, 보고서와 두 갈래 개수(관찰 글에 보임). topic_id는 G3가 주제를 알아보게 그대로 돌려줌
    ids_a, ids_b = {e["id"] for e in list_a}, {e["id"] for e in list_b}
    return {"chunks": chunks, "entities": entities, "neighbors": graph["neighbors"], "reports": graph["reports"],
            "n_candidates": len(candidates), "n_a": len(list_a), "n_b": len(list_b),
            "n_both": len(ids_a & ids_b), "topic_id": topic_id}


# ===========================================================================
# 9. W4 L Local 검색: L1 갈래 A 엔티티 축소 — 직접 작성
# ===========================================================================
def narrow_entities(candidates: list[dict], limit: int = 16) -> list[dict]:
    """청크에서 나온 엔티티 후보를 질문과의 유사도로 줄여 limit개만 남김(L1 갈래 A).

    방법: ① 청크마다 유사도가 가장 높은 엔티티 1개를 넣음 ② 남은 자리를 전체 유사도 순으로 채움.
          같은 엔티티는 한 번만 넣음.
    인자: candidates는 [{"id", "chunk_id", "score"(질문과의 코사인 유사도), ...}]. 한 엔티티가 여러 청크에서 나오면 여러 줄.
    반환값: 고른 엔티티 목록(넣은 순서). 엔티티가 0개인 청크는 건너뜀.
    """
    raise NotImplementedError("여기에 본인 코드를 작성함")


# ===========================================================================
# 10. W4 G Global 검색: G1, G2, G3 — 빈칸 3곳(G1, G2, G3)
# ===========================================================================
def global_search(res, query: str, filters: dict, ctx: dict) -> dict:
    """G Global 검색: G1 보고서 고르기(Groq) → G2 주제와 Follow-up 질문(Groq) → G3 주제별 Local 검색(병렬)

    이 구성은 Microsoft GraphRAG의 Global Search(map-reduce)와 다른 자체 구성임.
    찾기만 하고, 결과(found)를 작업 기록과 툴 결과로 바꾸는 일은 run_global이 함.
    """
    # --- G1 준비: 볼 수 있는 보고서만 남기고, 보고서마다 관련도(질문 벡터와 보고서 요약 임베딩의 코사인)를 셈
    #     관련도는 G1 실패 대체, 분량 맞추기, 관련 보고서 수(NO_REPORTS 판정)에 씀
    reports = {rid: r for rid, r in res.ready_data["reports"].items() if rid in filters["allowed_reports"]}
    vector = embed_query(res, query, ctx)
    relevance = {}
    for rid, report in reports.items():
        relevance[rid] = cosine(vector, report["embedding"]) if vector and report["embedding"] else 0.0

    # --- G1 제목 목록: 보고서 id를 정렬해 r1, r2 …를 붙이고 「r1: 제목」 줄로 이음(긴 id보다 토큰을 아낌)
    #     short_ids는 LLM 답을 원래 id로 되돌리는 표가 됨
    short_ids = {f"r{i}": rid for i, rid in enumerate(sorted(reports), start=1)}
    titles = "\n".join(f"{sid}: {reports[rid]['title']}" for sid, rid in short_ids.items())

    # --- G1 보고서 고르기: LCEL 체인(G1_PROMPT | 구조화 모델)으로 최대 12개. 표에 없는 id는 버림
    # 빈칸 1(G1 보고서 고르기): G1_PROMPT와 res.groq.with_structured_output(PickedReports, method="json_schema",
    #   strict=True)를 |로 이은 체인에 {"question": query, "titles": titles, "limit": G_MAX_REPORTS}를 넣어 부르고,
    #   답의 report_ids 중 short_ids에 있는 것만 원래 id로 바꿔 picked에 받음(최대 G_MAX_REPORTS개)
    #   부르기 전에 ctx["calls"]["groq"] += 1. 실패하면 ctx["warnings"]에 남기고 picked는 빈 목록
    raise NotImplementedError("빈칸 1(G1 보고서 고르기)을 채울 것")

    # --- G1 실패 대체: 고른 것이 없으면 관련도 상위 5개로 대신함
    if not picked:
        picked = sorted(reports, key=lambda rid: relevance[rid], reverse=True)[:G_FALLBACK_REPORTS]

    # --- G1 분량 맞추기: 관련도 순으로 세운 뒤, (요약 + 핵심 발견) 글자 수 / 2가 12,000 토큰을 넘으면 뒤에서 하나씩 뺌
    picked.sort(key=lambda rid: relevance[rid], reverse=True)
    while picked and sum(len(reports[r]["summary"] or "") + len(" ".join(reports[r]["findings"])) for r in picked) / 2 \
            > G_REPORT_TOKENS:
        picked.pop()

    # --- G2 보고서 목록: 고른 보고서를 다시 r1, r2 …로 바꾸고 「r1: 제목 - 요약 앞 300자」 줄을 만듦
    back = {rid: sid for sid, rid in short_ids.items()}
    report_lines = "\n".join(f"{back[r]}: {reports[r]['title']} - {short(reports[r]['summary'], 300)}" for r in picked)

    # --- G2 주제와 Follow-up 질문: 고른 보고서를 주제 1 ~ 5개로 묶고 주제마다 사실 확인 질문 하나(TopicPlan)
    # 빈칸 2(G2 주제와 Follow-up 질문): G2_PROMPT | 구조화 모델(TopicPlan) 체인에
    #   {"question": query, "reports": report_lines, "limit": G_MAX_TOPICS}를 넣어 부르고, plan.topics 앞
    #   G_MAX_TOPICS개를 {"title", "report_ids"(short_ids로 원래 id로 바꿈), "follow_up"} dict로 topics에 담음
    #   부르기 전에 ctx["calls"]["groq"] += 1. 실패하면 ctx["warnings"]에 남기고 topics는 빈 목록
    raise NotImplementedError("빈칸 2(G2 주제와 Follow-up 질문)를 채우고 이 줄을 지울 것")

    # --- G2 실패 대체: 주제가 하나도 없으면 상위 보고서마다 주제 1개, 질문은 제목 + 요약 첫 문장
    if not topics:
        for rid in picked[:G_MAX_TOPICS]:
            first = split_sentences(reports[rid]["summary"] or "")[:1]
            topics.append({"title": reports[rid]["title"], "report_ids": [rid],
                           "follow_up": reports[rid]["title"] + " " + (first[0] if first else "")})

    # --- G2 주제 id 붙이기: T1, T2 … 에이전트는 이 번호로만 local_search(topic_id)를 부를 수 있음
    for number, topic in enumerate(topics, start=1):
        topic["topic_id"] = f"T{number}"

    # --- G3 주제별 Local 검색(병렬): 원 질문이 아니라 그 주제의 Follow-up 질문으로 찾음
    #     future.result()는 넣은 순서대로 모으므로 locals_[0]이 topics[0](T1)의 결과임
    # 빈칸 3(G3 주제별 Local 검색): ThreadPoolExecutor(max_workers=G_MAX_TOPICS)로 주제마다
    #   local_search(res, 주제의 follow_up, 주제의 topic_id, filters, ctx)를 병렬로 부르고,
    #   넣은 순서대로 결과를 locals_에 받음(locals_[0]이 topics[0]의 결과)
    raise NotImplementedError("빈칸 3(G3 주제별 Local 검색)을 채우고 이 줄을 지울 것")

    # 리턴(found): 주제와 주제별 Local 결과(같은 순서의 짝), 고른 보고서와 관련도, 관련도 0.25 이상 보고서 수
    return {"topics": topics, "locals": locals_,
            "reports": [{"id": rid, "hits": 0, "relevance": relevance[rid]} for rid in picked],
            "n_relevant_reports": sum(1 for rid in picked if relevance[rid] >= REPORT_RELEVANCE_MIN)}


# ===========================================================================
# 11. W5 채점: Jev 청크 판정 — 직접 작성
# ===========================================================================
def jev_judge_passages(res, question: str, chunk_ids: list[str], ctx: dict) -> dict:
    """W5, W7 원문마다 Jev Noul 4개를 묻고 표시를 붙임. 판정은 (판정 질문, 청크 id)로 캐시해 두 번 묻지 않음.

    인자: question은 판정 질문(원 질문 또는 주제의 Follow-up 질문), chunk_ids는 판정할 청크 id 목록.
    방법: (1) ctx["jev_cache"]에 「질문|청크 id」 열쇠가 있으면 그 표시를 쓰고, 없는 청크만 모음
          (2) 모은 청크의 글을 read_chunk_texts로 한 번에 읽음
          (3) 청크마다 res.jev.system_one(state={"query": question, "passage": {"id": 짧은 id, "text": 글}},
              questions=PASSAGE_QUESTIONS)로 Noul 4개의 확률을 받음. 6개씩 동시에(ThreadPoolExecutor)
          (4) apply_passage_judgments(확률, PASSAGE_THRESHOLDS)로 표시를 만들어 캐시와 결과에 넣음
              (ctx["calls"]["jev"]는 PRINT_LOCK 안에서 셈). 실패한 청크는 경고만 남기고 결과에서 뺌
    짧은 id는 res.ready_data["chunk_meta"][청크 id]["short_id"](예: D1-0007).
    반환값: {chunk_id: 표시 dict}. Jev가 실패한 원문은 결과에 없음(호출한 쪽이 「모두 관련」으로 셈).
    """
    raise NotImplementedError("여기에 본인 코드를 작성함")


# ===========================================================================
# 12. W6 리랭킹(O4 포함): Cohere 리랭커 — 직접 작성
# ===========================================================================
def rerank(res, query: str, texts: list[str], ctx: dict) -> list[float] | None:
    """Cohere 리랭커로 글마다 질의 관련도 점수를 매김(입력 순서대로 점수 목록). 실패하면 None.

    쓰는 곳: O4(검색엔진 검색 후보 줄 세우기), W6 리랭킹(모든 회차에서 모은 청크 다시 채점).
    방법: 글이 없으면 빈 목록. res.cohere.rerank(model=RERANK_MODEL, query=query, documents=texts, top_n=len(texts))를
          부르고(ctx["calls"]["cohere"]를 셈), 답의 results마다 item.index 자리에 item.relevance_score를 넣음.
          실패하면 ctx["warnings"]에 남기고 None
    반환값: texts와 같은 순서의 점수 목록(0 ~ 1)
    """
    raise NotImplementedError("여기에 본인 코드를 작성함")


# ===========================================================================
# 13. W8 답변 생성: LCEL 체인 + 구조화 출력 — 직접 작성
# ===========================================================================
def generate_answer(llm, prompt, question: str, evidence_text: str, feedback: str, premise_note: str) -> GroundedAnswer:
    """근거만으로 답을 만듦. 답은 문장마다 인용 id를 단 구조화 객체(GroundedAnswer)로 받음.

    방법: LCEL 체인 「프롬프트 | 구조화 모델」을 만들어 한 번 부름. 재작성이면 feedback(무엇이 틀렸는지)을 함께 넣음.
    인자: llm은 Groq ChatGroq, prompt는 main의 ChatPromptTemplate(변수 question, evidence, feedback, premise_note).
    반환값: GroundedAnswer. 예외(호출 실패, 파싱 실패)는 그대로 올려 main이 W10 생성 실패로 처리함.
    """
    raise NotImplementedError("여기에 본인 코드를 작성함")


# ---------------------------------------------------------------------------
# 아직 채우지 않은 함수는 강사 코드(core_search)로 대신 돌게 함.
# 함수를 채울 때마다 그 이름을 아래 목록에서 지움. 목록이 비면 이 파일의 코드만으로 전체가 돎.
# 막히면 이름을 다시 넣어 뒤 단계를 계속함(실습이 멈추지 않음)
# ---------------------------------------------------------------------------
import core_search as _teacher  # noqa: E402

USE_TEACHER_CODE = [
    "jev_route", "build_agent", "ToolWrapperMiddleware", "run_tool",
    "read_chunk_texts", "search_engine", "rrf_merge", "local_search", "narrow_entities", "global_search",
    "jev_judge_passages", "rerank", "generate_answer",
]
for _name in USE_TEACHER_CODE:
    globals()[_name] = getattr(_teacher, _name)  # 이 파일의 빈 함수 대신 강사 함수를 같은 이름으로 둠
