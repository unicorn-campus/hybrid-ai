"""RAGAS 채점 핵심 모듈 — 채점할 행 고르기, 한 행 채점, 평균 내기(교육생 클론 코딩 대상)."""

import math

# RAGAS 핵심 4지표의 이름. 결과 dict의 키와 결과 파일의 키로 그대로 씀
METRIC_NAMES = ["context_precision", "context_recall", "faithfulness", "answer_relevancy"]

# 교재 168쪽 「위, 정, 출, 관」: 왼쪽 2개는 검색 품질, 오른쪽 2개는 생성(답변) 품질을 잼
RETRIEVAL_METRICS = ["context_precision", "context_recall"]  # 위(상위에 깔렸나), 정(정답이 빠짐없이 검색됐나)
GENERATION_METRICS = ["faithfulness", "answer_relevancy"]  # 출(출처에서 나온 답인가), 관(질문과 관련 있나)


def select_rows(results: dict) -> list[dict]:
    """결과 로그에서 RAGAS로 채점할 행만 골라 ragas 4칸 이름으로 바꿔 돌려줌.

    목적: 답이 없는 문항(answerable가 false)은 「확인 필요」로 끝나야 정답이라 RAGAS 4지표의 대상이 아님.
          근거(contexts)가 비어 있으면 지표가 ValueError를 내므로 함께 제외함.
    방법: 행마다 answerable와 contexts를 보고 거른 뒤, 검색기 로그의 키 이름을 ragas가 쓰는 이름으로 옮김.
          question → user_input, contexts → retrieved_contexts, answer → response, reference → reference.
    반환값: 채점 대상 행의 리스트. 각 행은 id와 ragas 4칸을 가진 dict임. 대상이 없으면 빈 리스트임.
    """
    selected_rows = []
    for row in results["rows"]:
        # 답 없음 문항은 건너뜀. True가 아닌 값(False, None)은 모두 제외함
        if row["answerable"] is not True:
            continue
        # 근거가 하나도 없으면 ContextRecall 등이 예외를 내므로 건너뜀
        if len(row["contexts"]) == 0:
            continue
        ragas_row = {
            "id": row["id"],  # 표와 결과 파일에서 문항을 알아보기 위해 유지함
            "user_input": row["question"],  # 질문
            "retrieved_contexts": row["contexts"],  # 검색 근거(청크 본문 리스트)
            "response": row["answer"],  # 검색기가 만든 답변
            "reference": row["reference"],  # 평가셋의 정답
        }
        selected_rows.append(ragas_row)
    return selected_rows


async def score_row(row: dict, metrics: dict) -> dict:
    """한 행(문항)을 RAGAS 4지표로 채점해 점수 dict를 돌려줌.

    목적: 교재 174쪽의 실험 함수처럼 문항 하나에 지표 4개의 ascore를 차례로 호출함.
    방법: 지표마다 필요한 칸만 넘김(교재 173쪽 표). ascore는 평가자 LLM을 부르는 비동기 함수라 await로 기다림.
          4개를 순서대로 부르는 이유는 Groq 분당 호출 제한 안에서 동시 호출 수를 예측하기 쉽게 하기 위함임.
    인자: metrics는 지표 이름(METRIC_NAMES) → 지표 객체의 dict임. row는 select_rows가 만든 한 행임.
    반환값: 4지표 점수(0 ~ 1 실수)와 reasons(지표별 판정 이유, 없으면 None)를 담은 dict임.
            ragas 0.4.3 collections 지표는 reason을 채우지 않아 보통 None임(설치본 소스 확인).
    예외: 평가자 호출이 끝내 실패하면 openai 예외가 그대로 올라옴. 호출자가 행 단위로 처리함.
    """
    question = row["user_input"]
    contexts = row["retrieved_contexts"]
    answer = row["response"]
    reference = row["reference"]

    # 위(ContextPrecision): 근거 조각마다 정답에 쓸모 있나 1/0 판정 → 순위대로 평균 정밀도
    precision_result = await metrics["context_precision"].ascore(
        user_input=question, reference=reference, retrieved_contexts=contexts
    )
    # 정(ContextRecall): 정답을 문장으로 쪼개 근거에 있는 비율
    recall_result = await metrics["context_recall"].ascore(
        user_input=question, retrieved_contexts=contexts, reference=reference
    )
    # 출(Faithfulness): 답변을 주장으로 쪼개 근거로 뒷받침되는 비율(환각 탐지)
    faithfulness_result = await metrics["faithfulness"].ascore(
        user_input=question, response=answer, retrieved_contexts=contexts
    )
    # 관(AnswerRelevancy): 답변으로 역질문을 만들어 원래 질문과 임베딩 유사도 → 평균
    relevancy_result = await metrics["answer_relevancy"].ascore(user_input=question, response=answer)

    scores = {
        "context_precision": float(precision_result.value),
        "context_recall": float(recall_result.value),
        "faithfulness": float(faithfulness_result.value),
        "answer_relevancy": float(relevancy_result.value),
        "reasons": {
            "context_precision": precision_result.reason,
            "context_recall": recall_result.reason,
            "faithfulness": faithfulness_result.reason,
            "answer_relevancy": relevancy_result.reason,
        },
    }
    return scores


def summarize(rows: list[dict]) -> dict:
    """채점된 행들의 지표별 평균과 검색 평균, 생성 평균을 냄.

    목적: 교재 174쪽 결과 표의 「평균」 행과 「검색 평균, 생성 평균」을 만듦.
    방법: 지표마다 숫자인 점수만 더해 평균을 냄. nan(ragas가 주장을 하나도 못 뽑았을 때 주는 값)은 빼고 셈.
          검색 평균은 precision과 recall의 평균, 생성 평균은 faithfulness와 relevancy의 평균임.
    인자: rows의 각 행은 METRIC_NAMES 4키에 점수가 들어 있어야 함(다른 키는 무시함).
    반환값: count(행 수), mean(지표별 평균), retrieval_mean, generation_mean을 담은 dict임.
            점수가 하나도 없는 지표의 평균은 None임.
    """
    mean_by_metric = {}
    for metric_name in METRIC_NAMES:
        total = 0.0
        count = 0
        for row in rows:
            score = row[metric_name]
            # nan은 더하면 전체가 nan이 되므로 건너뜀
            if math.isnan(score):
                continue
            total = total + score
            count = count + 1
        if count == 0:
            mean_by_metric[metric_name] = None
        else:
            mean_by_metric[metric_name] = total / count

    summary = {
        "count": len(rows),
        "mean": mean_by_metric,
        "retrieval_mean": mean_of_metrics(mean_by_metric, RETRIEVAL_METRICS),
        "generation_mean": mean_of_metrics(mean_by_metric, GENERATION_METRICS),
    }
    return summary


def mean_of_metrics(mean_by_metric: dict, metric_names: list[str]) -> float | None:
    """지표별 평균 dict에서 주어진 지표들의 평균을 냄. 값이 없는 지표는 빼고 셈. 하나도 없으면 None임."""
    total = 0.0
    count = 0
    for metric_name in metric_names:
        value = mean_by_metric[metric_name]
        if value is None:
            continue
        total = total + value
        count = count + 1
    if count == 0:
        return None
    return total / count
