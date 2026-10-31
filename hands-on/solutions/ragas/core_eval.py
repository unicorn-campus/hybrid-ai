"""RAGAS 평가 핵심 모듈: 버전 만들기, 결과 정보, 코드 평가 4지표, LLM 평가 5지표, 버전 비교(교육생 클론 코딩 대상)."""

import math

from ragas.metrics.collections import (
    AnswerRelevancy,
    ContextPrecisionWithReference,
    ContextRecall,
    FactualCorrectness,
    Faithfulness,
)

# ---------------------------------------------------------------------------
# 지표 이름(결과 dict의 키, 결과 파일의 열 이름으로 그대로 씀)
# ---------------------------------------------------------------------------
# 코드 평가 4지표(교재 180쪽 「하, 빠, 빨, 앞」): LLM 없이 정답 단서를 글자로 대조해 계산함
CODE_METRICS = ["hit", "recall", "mrr", "ndcg"]
# LLM 평가 5지표(교재 182쪽 「위, 정, 출, 관, 답」): 평가자 LLM이 뜻으로 판정함
LLM_METRICS = ["context_precision", "context_recall", "faithfulness", "answer_relevancy", "factual_correctness"]


# ===========================================================================
# 제공 함수(읽고 이해. 클론 대상 아님)
# ===========================================================================
def compact_text(text: str) -> str:
    """제공. 띄어쓰기와 줄바꿈을 모두 지운 글을 돌려줌.

    목적: PDF 본문은 문장 중간에서 줄이 바뀌어 정답 단서와 띄어쓰기가 다름. 둘 다 지운 뒤 비교해야 같은 문장을 찾음.
    """
    return "".join(text.split())  # split()은 공백, 탭, 줄바꿈 기준으로 자르므로 이어 붙이면 공백이 모두 사라짐


def rank_weight(rank: int) -> float:
    """제공. 순위 가중치 1 ÷ log₂(순위 + 1)을 돌려줌(교재 180쪽). 1위 1.00, 2위 0.63, 3위 0.50, 4위 0.43, 5위 0.39."""
    return 1 / math.log2(rank + 1)


def count_relevant_chunks(all_chunk_texts: list[str], relevance: list[dict]) -> int:
    """제공. 색인된 청크 중 관련 청크(정답 단서를 하나라도 담은 청크)의 수를 셈(교재 179쪽 용어표).

    목적: nDCG의 IDCG(이상적인 순서의 점수)는 관련 청크를 1위부터 채웠을 때의 합이라 관련 청크 수가 필요함.
    방법: 청크마다 정답 근거의 정답 단서를 하나씩 글자 대조함. 한 청크에 단서가 여러 개 있어도 청크 1개로 셈.
    반환값: 관련 청크 수. 답 없는 문항(정답 근거 0개)은 0.
    """
    count = 0
    for chunk_text in all_chunk_texts:
        body = compact_text(chunk_text)
        is_relevant = False
        for evidence in relevance:
            for clue in evidence["clues"]:
                if compact_text(clue) in body:
                    is_relevant = True
        if is_relevant:
            count = count + 1
    return count


def mean_of(values: list) -> float | None:
    """제공. None(계산 안 함)과 nan(채점 실패)을 뺀 평균. 남는 값이 없으면 None."""
    total = 0.0
    count = 0
    for value in values:
        if value is None:
            continue
        if isinstance(value, float) and math.isnan(value):  # nan은 더하면 합 전체가 nan이 되므로 뺌
            continue
        total = total + value
        count = count + 1
    if count == 0:
        return None
    return total / count


def format_delta(delta: float | None, change: str) -> str:
    """제공. 기준선 대비 변화를 「▲ +0.120」처럼 화면과 결과 파일용 글로 바꿈."""
    if change == "-":
        return "-"  # 기준선 자신
    if delta is None:
        return change  # 비교 불가
    return f"{change} {delta:+.3f}"  # +는 양수에도 부호를 붙이라는 뜻


async def ascore_or_nan(metric, metric_name: str, errors: dict, **inputs) -> float:
    """제공. ragas 지표 하나를 채점해 점수를 돌려줌. 실패하면 사유를 errors에 적고 nan을 돌려줌.

    목적: 평가자 LLM 호출이 한 번 실패했다고 그 문항의 다른 지표까지 버리지 않게 함.
    방법: metric.ascore(**inputs)를 기다려(await) MetricResult를 받고, 점수인 .value를 실수로 바꿈.
          ragas 0.4.3 collections 지표는 판정 이유(.reason)를 채우지 않아(2026-10-31 실측) 점수만 씀.
    부수효과: 실패하면 errors[metric_name]에 「예외 이름: 메시지」를 적음.
    """
    try:
        result = await metric.ascore(**inputs)
        return float(result.value)
    except Exception as error:  # 평가자 호출 실패, 응답 형식 오류 등. 행 전체를 버리지 않으려고 지표 단위로 잡음
        errors[metric_name] = f"{type(error).__name__}: {str(error)[:200]}"
        return float("nan")


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
    """
    if param not in supported:  # 재색인이 필요한 값(청크 크기 등)은 지원 목록에 없음
        raise ValueError(f"지원하지 않는 하이퍼 파라미터: {param} → 지원 목록: {list(supported.keys())}")

    if baseline is None:  # 기준선을 주지 않으면 검색기의 현재 값이 기준선임
        baseline = supported[param]

    if baseline not in values:  # 기준선을 돌리지 않으면 다른 버전과 비교할 잣대가 없음
        raise ValueError(f"기준선 값 {baseline} 이(가) 값 목록 {values} 에 없음 → --values에 기준선 값을 넣을 것")

    versions = []
    seen = []  # 이미 버전으로 만든 값(같은 값을 두 번 돌리지 않게)
    for value in values:
        if value in seen:
            continue
        seen.append(value)
        number = len(versions) + 1  # 버전 번호는 1부터
        version = {
            "name": f"v{number:02d}",  # 02d = 두 자리로 맞춤(v01, v02, …). 결과 파일 이름의 vNN이 됨
            "param": param,
            "value": value,
            "is_baseline": value == baseline,
        }
        versions.append(version)
    return versions


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
        retrieved_contexts.append(hit["text"])  # 빈칸 1: 청크 본문(hit["text"])을 검색 결과 목록에 더함
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
    # 빈칸 2: ragas 4칸. 질문과 모범 답안은 평가셋이, 검색 결과와 답변은 검색기가 채움(교재 188쪽)
    row["user_input"] = question_for_ragas  # 질문(회원번호를 지운 질문)
    row["reference"] = item["ground_truth"]  # 모범 답안(eval-set.json의 ground_truth)
    row["retrieved_contexts"] = retrieved_contexts  # 검색 결과(청크 본문 목록)
    row["response"] = answer_for_ragas  # 답변(인용 표시를 뺀 글)
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
    """
    hit_ranks = []  # 적중 청크의 순위
    found_evidence = set()  # 찾은 정답 근거 번호. set은 같은 값을 두 번 넣어도 하나만 남음
    evidence_by_rank = []  # 순위별로 담긴 정답 근거 번호(결과 파일 표시용)

    for rank, chunk_text in enumerate(chunk_texts, start=1):  # rank: 검색 순위(1위부터)
        body = compact_text(chunk_text)  # 청크 본문의 공백과 줄바꿈을 지움
        numbers_in_chunk = []  # 이 청크에 담긴 정답 근거 번호

        for number, evidence in enumerate(relevance, start=1):  # number: 정답 근거 번호(①이 1)
            for clue in evidence["clues"]:  # 정답 근거 하나의 정답 단서들
                if compact_text(clue) in body:  # 단서도 공백을 지우고 본문에 그대로 있는지 봄
                    numbers_in_chunk.append(number)  # 이 청크는 이 정답 근거를 담음
                    found_evidence.add(number)  # 찾은 정답 근거로 셈(이미 있으면 그대로)
                    break  # 단서 하나만 맞아도 이 정답 근거는 찾음. 같은 근거의 다른 단서는 볼 필요 없음

        evidence_by_rank.append(numbers_in_chunk)
        if len(numbers_in_chunk) > 0:  # 정답 근거를 하나라도 담았으면 적중 청크
            hit_ranks.append(rank)

    return {
        "hit_ranks": hit_ranks,
        "found_evidence": found_evidence,
        "evidence_by_rank": evidence_by_rank,
        "evidence_count": len(relevance),
    }


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
    """
    if hits["evidence_count"] == 0:  # 답 없는 문항: Recall 분모가 0이라 계산하지 않음
        return {"hit": None, "recall": None, "mrr": None}

    ranks_in_k = []  # 상위 k개 안의 적중 순위만 남김(k 밖의 청크는 이 지표에 들어가지 않음)
    for rank in hits["hit_ranks"]:
        if rank <= k:
            ranks_in_k.append(rank)

    # 하(Hit@k): 적중 청크가 하나라도 있으면 1. 몇 개인지, 몇 위인지는 보지 않음
    if len(ranks_in_k) > 0:
        hit = 1
    else:
        hit = 0

    # 빠(Recall@k): 찾은 정답 근거 수 ÷ 전체 정답 근거 수. 같은 근거를 담은 청크가 여럿이어도 한 번만 셈
    recall = len(hits["found_evidence"]) / hits["evidence_count"]

    # 빨(MRR): 첫 적중 청크 순위의 역수. 적중이 없으면 0
    if len(ranks_in_k) > 0:
        first_rank = ranks_in_k[0]  # hit_ranks는 1위부터 차례로 담았으므로 맨 앞이 첫 적중
        mrr = 1 / first_rank
    else:
        mrr = 0.0

    return {"hit": hit, "recall": recall, "mrr": mrr}


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
            dcg = dcg + rank_weight(rank)  # 빈칸 1: 그 순위의 가중치 rank_weight(rank)를 더함

    ideal_count = min(relevant_chunk_count, k)  # 이상적이면 관련 청크가 1위부터 몇 칸을 채우나(k칸이 최대)
    idcg = 0.0
    for rank in range(1, ideal_count + 1):  # 1위부터 ideal_count위까지
        idcg = idcg + rank_weight(rank)  # 빈칸 2: 1위부터 채운 칸의 가중치를 더함

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
    """
    summary = {}
    for version_name, rows in rows_by_version.items():  # 버전마다
        means = {}
        for metric in metric_names:  # 지표마다
            values = []
            for row in rows:  # 문항마다 그 지표 점수를 모음
                values.append(row.get(metric))  # 점수가 없는 칸(채점 안 함)은 None
            means[metric] = mean_of(values)  # 문항 점수의 평균(매크로 평균)
        summary[version_name] = {"mean": means, "delta": {}, "change": {}}

    baseline_means = summary[baseline_name]["mean"]
    for version_name, version_summary in summary.items():
        for metric in metric_names:
            mean = version_summary["mean"][metric]
            base = baseline_means[metric]
            if version_name == baseline_name:  # 기준선 자신은 비교하지 않음
                version_summary["delta"][metric] = None
                version_summary["change"][metric] = "-"
                continue
            if mean is None or base is None:  # 어느 한쪽이 채점되지 않았으면 비교할 수 없음
                version_summary["delta"][metric] = None
                version_summary["change"][metric] = "비교 불가"
                continue
            delta = mean - base  # 기준선 대비 차이(+면 나아짐)
            version_summary["delta"][metric] = delta
            if delta > noise[metric]:  # 다시 채점만 해도 생기는 흔들림보다 크게 올랐을 때만 개선
                version_summary["change"][metric] = "▲"
            elif delta < -noise[metric]:
                version_summary["change"][metric] = "▼"
            else:
                version_summary["change"][metric] = "변화 없음"
    return summary


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
    context_recall_dropped = change.get("context_recall") == "▼"  # 빈칸 1: Context Recall이 떨어졌나(True/False)
    if context_recall_dropped:
        reasons.append("Context Recall ↓: 검색 정답률이 떨어짐 → 청킹, 임베딩, Top-k를 봄")
    context_precision_dropped = change.get("context_precision") == "▼"  # 빈칸 2: Context Precision이 떨어졌나
    if context_precision_dropped:
        reasons.append("Context Precision ↓: 검색 상위에 답이 많이 없음 → 리랭커, 하이브리드 비중을 봄")
    if change.get("faithfulness") == "▼":
        reasons.append("Faithfulness ↓: 답변이 검색 결과에 없는 말을 함 → 답변 프롬프트를 고침")
    if change.get("answer_relevancy") == "▼":
        reasons.append("Answer Relevancy ↓: 답변이 질문과 어긋남 → 질문 변환, 답변 프롬프트를 고침")
    if change.get("factual_correctness") == "▼":
        # 빈칸 3: Context Recall도 떨어졌으면(context_recall_dropped) 검색이 근거를 못 가져온 것,
        #         아니면 검색은 됐는데 답변이 근거 일부만 담은 것(교재 185쪽 Q17)
        if context_recall_dropped:
            reasons.append("Factual Correctness ↓ + Context Recall ↓: 근거를 못 가져옴 → 청킹, 임베딩, Top-k를 봄")
        else:
            reasons.append("Factual Correctness ↓, Context Recall 정상: 답변이 근거 일부만 담음 → 답변 프롬프트를 고침")

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
    # 빈칸 1: 위(ContextPrecision). 평가셋에 모범 답안이 있으므로 모범 답안과 비교하는 WithReference 클래스를 씀
    metrics["context_precision"] = ContextPrecisionWithReference(llm=llm)
    # 빈칸 2: 관(AnswerRelevancy). 역질문과 원래 질문을 임베딩으로 비교하므로 llm과 embeddings를 둘 다 넘김
    metrics["answer_relevancy"] = AnswerRelevancy(llm=llm, embeddings=embeddings)
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
    """
    question = row["user_input"]  # 질문
    reference = row["reference"]  # 모범 답안
    contexts = row["retrieved_contexts"]  # 검색 결과(청크 본문 목록)
    answer = row["response"]  # 답변
    errors = {}  # 실패한 지표와 사유

    scores = {}
    # 빈칸 1: 위(ContextPrecision)는 질문, 모범 답안, 검색 결과를 읽음
    scores["context_precision"] = await ascore_or_nan(
        metrics["context_precision"], "context_precision", errors,
        user_input=question, reference=reference, retrieved_contexts=contexts)
    # 빈칸 2: 정(ContextRecall)은 질문, 검색 결과, 모범 답안을 읽음
    scores["context_recall"] = await ascore_or_nan(
        metrics["context_recall"], "context_recall", errors,
        user_input=question, retrieved_contexts=contexts, reference=reference)
    # 빈칸 3: 출(Faithfulness)은 질문, 답변, 검색 결과를 읽음(모범 답안은 안 읽음)
    scores["faithfulness"] = await ascore_or_nan(
        metrics["faithfulness"], "faithfulness", errors,
        user_input=question, response=answer, retrieved_contexts=contexts)
    # 빈칸 4: 관(AnswerRelevancy)은 질문과 답변만 읽음
    scores["answer_relevancy"] = await ascore_or_nan(
        metrics["answer_relevancy"], "answer_relevancy", errors,
        user_input=question, response=answer)
    # 빈칸 5: 답(FactualCorrectness)은 답변과 모범 답안만 읽음(검색 결과는 안 읽음)
    scores["factual_correctness"] = await ascore_or_nan(
        metrics["factual_correctness"], "factual_correctness", errors,
        response=answer, reference=reference)

    scores["errors"] = errors
    return scores
