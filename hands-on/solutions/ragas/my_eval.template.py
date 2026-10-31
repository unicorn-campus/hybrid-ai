"""교육생용 뼈대: core_eval.py와 같은 이름, 같은 인자의 실습 함수 9개를 본인 코드로 채우는 파일임.

채우는 순서(워크플로우 순서). "직접"은 NotImplementedError 자리에 본인 코드를 쓰고, "빈칸"은 거의 완성된 코드의 빈칸만 채움
  [교시 2: ①, ②, ③]
   1 build_versions       (직접)      ① 하이퍼 파라미터 값 목록 → 버전 목록(기준선 표시)
   2 make_result_row      (빈칸 2곳)  ② 평가셋 문항 + 검색기 결과 → 결과 정보 4칸
   3 find_hits            (직접)      ③ 정답 단서를 글자 대조해 적중 청크와 찾은 정답 근거 판정
   4 retrieval_metrics    (직접)      ③ 하(Hit@k), 빠(Recall@k), 빨(MRR)
   5 ndcg_at_k            (빈칸 2곳)  ③ 앞(nDCG@k) = DCG ÷ IDCG
  [교시 3: ⑤, ④]
   6 summarize_versions   (직접)      ⑤ 버전별 평균(매크로 평균)과 기준선 대비 변화(▲, ▼, 변화 없음)
   7 diagnose             (빈칸 3곳)  ⑤ 떨어진 지표 조합으로 고칠 곳 후보(교재 187쪽)
   8 build_metrics        (빈칸 2곳)  ④ ragas 지표 객체 5개
   9 score_row            (빈칸 5곳)  ④ 지표마다 읽는 칸을 맞춰 ascore
  제공(완성본, 읽기만): 지표 이름 상수, compact_text, rank_weight, count_relevant_chunks, mean_of, format_delta, ascore_or_nan은
  core_eval에서 그대로 가져옴(아래 import)

함수 설명(docstring)과 주석은 core_eval.py의 같은 함수와 같음. 빈칸 자리만 「# 빈칸 n: ...」 안내와 NotImplementedError로 바꿨음

사용법(이 파일은 강사 뼈대(템플릿)임. 직접 고치지 않고 복사본 my_eval.py를 고침. my_eval.py는 Git이 무시해 pull 충돌이 없음)
  1) "python evaluate_rag.py --mine --selftest"처럼 --mine을 붙여 실행함. my_eval.py가 없으면 이 파일을 복사해 만듦
  2) 채울 함수 이름을 이 파일 맨 아래 USE_TEACHER_CODE 목록에서 지움(지우지 않은 함수는 강사 코드가 대신 돎)
  3) 함수를 채우고 README 6장의 확인 명령으로 실행해 강사 결과와 비교함. 막히면 이름을 목록에 다시 넣고 다음 함수로 넘어감
  4) 코드 평가 함수(3, 4, 5)와 비교 함수(1, 6, 7)는 --selftest로 API 없이 확인할 수 있음
"""

from ragas.metrics.collections import (  # noqa: F401  (8 build_metrics에서 씀)
    AnswerRelevancy,
    ContextPrecisionWithReference,
    ContextRecall,
    FactualCorrectness,
    Faithfulness,
)

# 제공 상수와 함수는 강사 코드에서 그대로 가져옴(evaluate_rag.py가 core.이름 으로 부르므로 이 파일에도 있어야 함)
from core_eval import (  # noqa: F401
    CODE_METRICS,
    LLM_METRICS,
    ascore_or_nan,
    compact_text,
    count_relevant_chunks,
    format_delta,
    mean_of,
    rank_weight,
)


# ===========================================================================
# 1. ① 버전 만들기 (교재 177, 192, 196쪽) — 직접 작성
# ===========================================================================
def build_versions(param: str, values: list, baseline, supported: dict) -> list[dict]:
    """실습(직접). 하이퍼 파라미터 하나의 값 목록으로 버전 목록을 만듦.

    목적: 버전 = 하이퍼 파라미터 값 한 묶음(교재 177쪽). 한 번에 하나만 바꾸고 나머지는 기준선 값으로 고정해야
          점수 변화를 그 값 탓으로 볼 수 있음.
    인자: param은 하이퍼 파라미터 이름(예: "top_k"), values는 형 변환을 마친 값 목록(예: [3, 5, 10]),
          baseline은 기준선 값(None이면 supported에 적힌 현재 값), supported는 {지원 이름: 현재 값}.
    반환값: 버전 dict 목록. 키 name(v01, v02, …), param, value, is_baseline(기준선이면 True).
    예외: 지원하지 않는 이름이거나 기준선 값이 값 목록에 없으면 ValueError(같은 잣대로 비교하려면 기준선도 돌려야 함).

    순서: ① param이 supported에 없으면 ValueError  ② baseline이 None이면 supported[param]을 기준선으로
          ③ baseline이 values에 없으면 ValueError  ④ values를 돌며(같은 값은 한 번만) 번호를 1부터 매겨
             {"name": f"v{번호:02d}", "param": param, "value": 값, "is_baseline": 값 == baseline}을 목록에 더함
    """
    raise NotImplementedError("여기에 본인 코드를 작성함")


# ===========================================================================
# 2. ② 결과 정보 만들기 (교재 188쪽) — 빈칸 2곳
# ===========================================================================
def make_result_row(item: dict, result: dict, question_for_ragas: str, answer_for_ragas: str) -> dict:
    """실습(빈칸). 평가셋 문항 하나와 검색기 결과 하나로 결과 정보 한 행을 만듦.

    목적: 교재 188쪽 「문항 1건 = 결과 정보 4칸」. 평가셋이 채우는 칸(질문, 모범 답안)과 검색기가 채우는 칸(검색 결과, 답변)을
          한 행에 모아야 지표들이 필요한 칸만 골라 읽음.
    인자: item은 eval-set.json의 문항, result는 검색기 run_workflow의 반환값(evidence = ⑤ 답변 생성에 넘긴 근거, 리랭크 순서),
          question_for_ragas는 회원번호를 지운 질문, answer_for_ragas는 인용 표시를 뺀 답변(main이 정리해서 넘김).
    반환값: dict. ragas 4칸(user_input, reference, retrieved_contexts, response)과
            코드 평가와 결과 파일용 칸(id, answerable, status, question, answer, chunk_ids, relevance).
    """
    retrieved_contexts = []  # 검색 결과 청크 본문 목록(순위 순서 그대로)
    chunk_ids = []  # 같은 순서의 청크ID 목록(결과 파일에 순위별로 적음)
    for hit in result["evidence"]:  # 근거 0개로 끝난 문항(근거 부족, 되묻기)은 빈 목록이라 반복하지 않음
        # 빈칸 1: 청크 본문(hit["text"])을 retrieved_contexts에 더함
        raise NotImplementedError("빈칸 1을 채울 것")
        chunk_ids.append(hit["chunk_id"])

    row = {
        "id": item["id"],  # 평가셋 문항 번호(Q01 …)
        "answerable": item["answerable"],  # 문서에서 답을 찾을 수 있는 문항인가(False면 「확인 필요」가 정답)
        "status": result["status"],  # 검색기 종료 상태(답변 완료, 근거 부족, 되묻기 …)
        "question": item["question"],  # 원 질문(결과 파일에만 씀)
        "answer": result["answer"],  # 원 답변(인용 표시 포함. 결과 파일에만 씀)
        "chunk_ids": chunk_ids,
        "relevance": item["relevance"],  # 정답 근거 목록(코드 평가가 정답 단서를 꺼내 씀)
    }
    # 빈칸 2: ragas 4칸을 row에 넣음(교재 188쪽). 질문과 모범 답안은 평가셋이, 검색 결과와 답변은 검색기가 채움
    #         row["user_input"] = 회원번호를 지운 질문, row["reference"] = 모범 답안(item["ground_truth"]),
    #         row["retrieved_contexts"] = 검색 결과 본문 목록, row["response"] = 인용 표시를 뺀 답변
    raise NotImplementedError("빈칸 2를 채울 것")
    return row


# ===========================================================================
# 3. ③ 적중 청크 판정 (교재 180쪽) — 직접 작성
# ===========================================================================
def find_hits(chunk_texts: list[str], relevance: list[dict]) -> dict:
    """실습(직접). 검색 결과 청크마다 정답 단서가 들어 있는지 보고 적중 순위와 찾은 정답 근거를 돌려줌.

    목적: 적중 청크 = 정답 단서를 하나라도 담은 검색 결과 청크(교재 179쪽 용어표). 코드 평가 4지표가 모두 이 판정을 씀.
    방법: 순위마다 청크 본문과 정답 단서를 compact_text로 공백을 지우고 글자 대조함.
          정답 근거 하나에 정답 단서가 여러 개면 그중 하나만 있어도 그 정답 근거를 찾은 것으로 봄.
          같은 정답 근거가 여러 청크에 나와도 찾은 정답 근거는 한 번만 셈(집합 set에 넣음, 교재 181쪽 4위의 ①).
    인자: chunk_texts는 상위 k개 청크 본문(1위부터), relevance는 정답 근거 목록(원소마다 clues = 정답 단서 목록).
    반환값: dict. hit_ranks(적중 청크 순위 목록, 1부터 오름차순), found_evidence(찾은 정답 근거 번호 집합, 1부터),
            evidence_by_rank(순위마다 그 청크에 담긴 정답 근거 번호 목록), evidence_count(전체 정답 근거 수).
    예시: 181쪽 예(정답 근거 ①②③) → 2위 청크에 ①②, 4위 청크에 ① → hit_ranks [2, 4], found_evidence {1, 2}.

    순서: chunk_texts를 enumerate(..., start=1)로 돌며(rank, chunk_text)
            body = compact_text(chunk_text), 이 청크에 담긴 정답 근거 번호 목록 numbers_in_chunk = []
            relevance를 enumerate(..., start=1)로 돌며(number, evidence)
              evidence["clues"]의 단서마다 compact_text(단서)가 body에 있으면 numbers_in_chunk에 number를 더하고
              found_evidence에 number를 add한 뒤 break(같은 근거의 다른 단서는 볼 필요 없음)
            evidence_by_rank에 numbers_in_chunk를 더하고, 비어 있지 않으면 hit_ranks에 rank를 더함
          evidence_count는 len(relevance)
    """
    raise NotImplementedError("여기에 본인 코드를 작성함")


# ===========================================================================
# 4. ③ 코드 평가: 하(Hit@k), 빠(Recall@k), 빨(MRR) (교재 180, 181쪽) — 직접 작성
# ===========================================================================
def retrieval_metrics(hits: dict, k: int) -> dict:
    """실습(직접). 적중 판정으로 Hit@k, Recall@k, MRR을 계산함.

    목적: 같은 검색 결과를 서로 다른 질문으로 읽음(교재 180쪽). Hit: 답할 재료를 하나라도 건졌나,
          Recall: 정답 근거를 빠짐없이 찾았나, MRR: 첫 적중 청크를 얼마나 빨리 보여 줬나.
    방법: Hit = 적중 청크가 1개 이상이면 1, 없으면 0. Recall = 찾은 정답 근거 수 ÷ 전체 정답 근거 수(세는 단위는 정답 근거).
          MRR = 1 ÷ 첫 적중 청크 순위(이 문항 하나의 값. 여러 문항의 평균은 summarize_versions가 냄).
    인자: hits는 find_hits의 반환값, k는 상위 몇 개까지 볼지(이 버전의 top_k).
    반환값: dict. 키 hit, recall, mrr. 정답 근거가 0개인 문항(답 없음)은 분모가 0이라 모두 None(교재 181쪽).

    순서: ① hits["evidence_count"]가 0이면 {"hit": None, "recall": None, "mrr": None}
          ② hits["hit_ranks"] 중 k 이하인 순위만 ranks_in_k에 모음
          ③ hit = ranks_in_k가 비어 있지 않으면 1, 아니면 0
          ④ recall = len(hits["found_evidence"]) / hits["evidence_count"]
          ⑤ mrr = ranks_in_k가 있으면 1 / ranks_in_k[0], 없으면 0.0
    """
    raise NotImplementedError("여기에 본인 코드를 작성함")


# ===========================================================================
# 5. ③ 코드 평가: 앞(nDCG@k) (교재 180, 181쪽) — 빈칸 2곳
# ===========================================================================
def ndcg_at_k(hit_ranks: list[int], relevant_chunk_count: int, k: int) -> float | None:
    """실습(빈칸). nDCG@k = DCG ÷ IDCG를 계산함.

    목적: 필요한 청크들을 얼마나 앞에 모아 검색했나(교재 180쪽 「앞」). 적중 청크가 위에 있을수록 점수가 큼.
    방법: DCG = 상위 k개 중 적중 청크 칸의 순위 가중치 합(적중하지 않은 칸은 0).
          IDCG = 관련 청크를 1위부터 min(관련 청크 수, k)개 채웠을 때의 순위 가중치 합(이상적인 순서).
          관련 청크 기준이라 적중 청크 수가 IDCG의 칸 수를 넘지 않아 nDCG가 1을 넘지 않음.
    인자: hit_ranks는 적중 순위 목록, relevant_chunk_count는 색인 전체의 관련 청크 수(count_relevant_chunks), k는 top_k.
    반환값: 0 ~ 1 실수. 관련 청크가 0개면(답 없는 문항) None.
    예시: 181쪽 예 → 적중 2위, 4위, 관련 청크 4개, k 5 → (0.63 + 0.43) ÷ (1.00 + 0.63 + 0.50 + 0.43) = 0.41.
    """
    if relevant_chunk_count == 0:  # IDCG가 0이 되어 나눌 수 없음
        return None

    dcg = 0.0
    for rank in hit_ranks:
        if rank <= k:  # 상위 k개 안의 적중 칸만 더함
            # 빈칸 1: dcg에 그 순위의 가중치 rank_weight(rank)를 더함
            raise NotImplementedError("빈칸 1을 채울 것")

    ideal_count = min(relevant_chunk_count, k)  # 이상적이면 관련 청크가 1위부터 몇 칸을 채우나(k칸이 최대)
    idcg = 0.0
    for rank in range(1, ideal_count + 1):  # 1위부터 ideal_count위까지
        # 빈칸 2: idcg에 그 순위의 가중치를 더함
        raise NotImplementedError("빈칸 2를 채울 것")

    return dcg / idcg


# ===========================================================================
# 6. ⑤ 버전 비교 (교재 177, 178, 181쪽) — 직접 작성
# ===========================================================================
def summarize_versions(rows_by_version: dict, metric_names: list[str], baseline_name: str, noise: dict) -> dict:
    """실습(직접). 버전마다 지표별 평균을 내고 기준선과 비교함.

    목적: 점수 0.8 같은 고정 합격선보다 기준선 대비 변화로 채택 여부를 정함(교재 187쪽).
    방법: 지표마다 문항 점수의 평균(매크로 평균, 교재 181쪽)을 mean_of로 냄(None과 nan은 뺌).
          기준선이 아닌 버전은 평균 - 기준선 평균을 delta로 두고, 흔들림 폭(noise)보다 크면 ▲, 작으면 ▼, 그 사이면 「변화 없음」.
    인자: rows_by_version은 {버전 이름: [문항 점수 dict, …]}(dict 키 = 지표 이름), metric_names는 비교할 지표 이름 목록,
          baseline_name은 기준선 버전 이름(예: "v02"), noise는 {지표 이름: 흔들림 폭}.
    반환값: {버전 이름: {"mean": {지표: 평균}, "delta": {지표: 차이}, "change": {지표: "▲", "▼", "변화 없음", "-", "비교 불가"}}}.

    순서: ① 버전마다, 지표마다 문항 점수(row.get(지표))를 모아 mean_of로 평균 → summary[버전]["mean"][지표]
          ② 기준선 평균 baseline_means = summary[baseline_name]["mean"]
          ③ 버전마다, 지표마다: 기준선 자신이면 delta None, change "-"
             평균이나 기준선 평균이 None이면 delta None, change "비교 불가"
             아니면 delta = 평균 - 기준선 평균. delta > noise[지표]면 "▲", delta < -noise[지표]면 "▼", 그 사이면 "변화 없음"
    """
    raise NotImplementedError("여기에 본인 코드를 작성함")


# ===========================================================================
# 7. ⑤ 지표 조합으로 원인 찾기 (교재 187쪽) — 빈칸 3곳
# ===========================================================================
def diagnose(change: dict) -> list[str]:
    """실습(빈칸). 기준선보다 떨어진(▼) 지표의 조합으로 고칠 곳 후보를 고름(교재 187쪽 표).

    목적: 지표 하나만 보면 놓침(교재 185쪽 Q17). 검색 지표와 답변 지표를 함께 봐야 검색, 순위, 생성 중 어디서 새는지 보임.
    인자: change는 summarize_versions가 만든 한 버전의 {지표 이름: 변화}. LLM 평가를 돌리지 않았으면 LLM 지표는 「비교 불가」.
    반환값: 원인 후보 문장 목록. 떨어진 지표가 없으면 그렇다는 문장 하나.
    """
    reasons = []

    # 코드 평가(LLM 없이도 나옴): 정답 근거를 놓쳤나, 뒤로 밀렸나
    if change.get("recall") == "▼":
        reasons.append("Recall@k ↓ (코드): 정답 근거를 놓침 → 청킹, 임베딩, Top-k를 봄")
    if change.get("ndcg") == "▼":
        reasons.append("nDCG@k ↓ (코드): 정답 근거가 뒤로 밀림 → 리랭커, 하이브리드 비중을 봄")

    # LLM 평가(교재 187쪽 표). change.get(이름)은 그 지표가 없으면(LLM 평가를 안 돌림) None이라 조건이 거짓이 됨
    # 빈칸 1: change.get("context_recall")이 "▼"와 같은지(True/False)를 context_recall_dropped에 받음
    raise NotImplementedError("빈칸 1을 채울 것")
    if context_recall_dropped:  # noqa: F821
        reasons.append("Context Recall ↓: 검색 정답률이 떨어짐 → 청킹, 임베딩, Top-k를 봄")
    # 빈칸 2: 같은 방법으로 Context Precision이 떨어졌는지를 context_precision_dropped에 받음
    raise NotImplementedError("빈칸 2를 채울 것")
    if context_precision_dropped:  # noqa: F821
        reasons.append("Context Precision ↓: 검색 상위에 답이 많이 없음 → 리랭커, 하이브리드 비중을 봄")
    if change.get("faithfulness") == "▼":
        reasons.append("Faithfulness ↓: 답변이 검색 결과에 없는 말을 함 → 답변 프롬프트를 고침")
    if change.get("answer_relevancy") == "▼":
        reasons.append("Answer Relevancy ↓: 답변이 질문과 어긋남 → 질문 변환, 답변 프롬프트를 고침")
    if change.get("factual_correctness") == "▼":
        # 빈칸 3: Context Recall도 떨어졌으면(context_recall_dropped) 검색이 근거를 못 가져온 것,
        #         아니면 검색은 됐는데 답변이 근거 일부만 담은 것(교재 185쪽 Q17). 조건에 맞는 문장 하나를 reasons에 더함
        #         "Factual Correctness ↓ + Context Recall ↓: 근거를 못 가져옴 → 청킹, 임베딩, Top-k를 봄"
        #         "Factual Correctness ↓, Context Recall 정상: 답변이 근거 일부만 담음 → 답변 프롬프트를 고침"
        raise NotImplementedError("빈칸 3을 채울 것")

    if len(reasons) == 0:
        reasons.append("기준선보다 떨어진 지표 없음")
    return reasons


# ===========================================================================
# 8. ④ LLM 평가 지표 만들기 (교재 188, 201쪽) — 빈칸 2곳
# ===========================================================================
def build_metrics(llm, embeddings) -> dict:
    """실습(빈칸). ragas 0.4.3 collections의 지표 객체 5개를 만듦.

    목적: 지표마다 평가자 LLM이 하는 일이 다름(교재 188쪽). 모두 평가자 LLM이 필요하고, AnswerRelevancy만 임베딩도 필요함
          (답변으로 만든 역질문과 원래 질문의 코사인 유사도를 잼).
    인자: llm은 llm_factory로 만든 평가자 LLM, embeddings는 ragas 임베딩 객체(main이 만들어 넘김).
    반환값: {지표 이름: 지표 객체} 5개. 키는 LLM_METRICS와 같음.
    """
    metrics = {
        "context_recall": ContextRecall(llm=llm),  # 정: 모범 답안의 주장이 검색 결과에 있나
        "faithfulness": Faithfulness(llm=llm),  # 출: 답변의 주장이 검색 결과에서 나왔나(환각 탐지)
        "factual_correctness": FactualCorrectness(llm=llm),  # 답: 답변과 모범 답안의 주장이 서로 맞나(기본 F1)
    }
    # 빈칸 1: metrics["context_precision"]에 위(ContextPrecision) 지표를 넣음.
    #         평가셋에 모범 답안이 있으므로 모범 답안과 비교하는 WithReference 클래스를 llm=llm으로 만듦
    raise NotImplementedError("빈칸 1을 채울 것")
    # 빈칸 2: metrics["answer_relevancy"]에 관(AnswerRelevancy) 지표를 넣음.
    #         역질문과 원래 질문을 임베딩으로 비교하므로 llm과 embeddings를 둘 다 넘김
    raise NotImplementedError("빈칸 2를 채울 것")
    return metrics


# ===========================================================================
# 9. ④ 한 행을 지표 5개로 채점 (교재 188, 202 ~ 203쪽) — 빈칸 5곳
# ===========================================================================
async def score_row(row: dict, metrics: dict) -> dict:
    """실습(빈칸). 결과 정보 한 행을 LLM 평가 5지표로 채점함.

    목적: 지표마다 읽는 칸이 다름(교재 188쪽 표). 맞는 칸을 맞는 이름으로 넘겨야 함.
    방법: 지표마다 ascore_or_nan(지표, 이름, errors, 칸=값, …)을 await로 기다림. 평가자 LLM을 부르는 비동기 함수라
          기다리는 동안 다른 행의 채점이 돌 수 있음. 5개는 차례로 불러 동시 호출 수를 예측하기 쉽게 함(Groq 호출 제한).
    인자: row는 make_result_row가 만든 한 행, metrics는 build_metrics의 반환값.
    반환값: {지표 이름: 점수(0 ~ 1)} 5개 + "errors": {지표 이름: 실패 사유}. 실패한 지표의 점수는 nan.

    부르는 꼴(칸 이름은 ragas가 정한 영어 이름을 그대로 씀):
      scores["지표 이름"] = await ascore_or_nan(metrics["지표 이름"], "지표 이름", errors, user_input=..., reference=..., ...)
    """
    question = row["user_input"]  # 질문
    reference = row["reference"]  # 모범 답안
    contexts = row["retrieved_contexts"]  # 검색 결과(청크 본문 목록)
    answer = row["response"]  # 답변
    errors = {}  # 실패한 지표와 사유

    scores = {}
    # 빈칸 1: 위(context_precision)는 user_input=질문, reference=모범 답안, retrieved_contexts=검색 결과를 읽음
    raise NotImplementedError("빈칸 1을 채울 것")
    # 빈칸 2: 정(context_recall)은 user_input=질문, retrieved_contexts=검색 결과, reference=모범 답안을 읽음
    raise NotImplementedError("빈칸 2를 채울 것")
    # 빈칸 3: 출(faithfulness)은 user_input=질문, response=답변, retrieved_contexts=검색 결과를 읽음(모범 답안은 안 읽음)
    raise NotImplementedError("빈칸 3을 채울 것")
    # 빈칸 4: 관(answer_relevancy)은 user_input=질문, response=답변만 읽음
    raise NotImplementedError("빈칸 4를 채울 것")
    # 빈칸 5: 답(factual_correctness)은 response=답변, reference=모범 답안만 읽음(검색 결과는 안 읽음)
    raise NotImplementedError("빈칸 5를 채울 것")

    scores["errors"] = errors
    return scores


# ---------------------------------------------------------------------------
# 아직 채우지 않은 함수는 강사 코드(core_eval)로 대신 돌게 함.
# 함수를 채울 때마다 그 이름을 아래 목록에서 지움. 목록이 비면 이 파일의 코드만으로 전체가 돎.
# 막히면 이름을 다시 넣어 뒤 단계를 계속함(실습이 멈추지 않음)
# ---------------------------------------------------------------------------
import core_eval as _teacher  # noqa: E402

USE_TEACHER_CODE = [
    "build_versions", "make_result_row", "find_hits", "retrieval_metrics", "ndcg_at_k",
    "summarize_versions", "diagnose", "build_metrics", "score_row",
]
for _name in USE_TEACHER_CODE:
    globals()[_name] = getattr(_teacher, _name)  # 이 파일의 빈 함수 대신 강사 함수를 같은 이름으로 둠
