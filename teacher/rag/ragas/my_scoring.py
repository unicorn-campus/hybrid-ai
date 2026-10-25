"""RAGAS 채점 핵심 모듈 뼈대 — 교육생이 core_scoring.py를 보고 직접 채워 넣는 파일."""

# 사용법: 아래 함수 3개를 완성한 뒤 evaluate_ragas.py의 import 한 줄을
#   import core_scoring as scoring  →  import my_scoring as scoring
# 으로 바꾸면 본인 코드로 채점이 돌아감. 함수 이름과 인자는 바꾸지 않음(main이 그대로 부름).

import math

# RAGAS 핵심 4지표의 이름. main이 이 이름으로 결과 dict를 읽음(바꾸지 않음)
METRIC_NAMES = ["context_precision", "context_recall", "faithfulness", "answer_relevancy"]
RETRIEVAL_METRICS = ["context_precision", "context_recall"]
GENERATION_METRICS = ["faithfulness", "answer_relevancy"]


def select_rows(results: dict) -> list[dict]:
    """결과 로그에서 RAGAS로 채점할 행만 골라 ragas 4칸 이름으로 바꿔 돌려줌.

    인자: results는 results.json을 json.load한 dict임. results["rows"]가 문항 리스트임.
    반환값: 각 행이 id, user_input, retrieved_contexts, response, reference 키를 가진 리스트임.
    """
    # 할 일 1: results["rows"]를 for로 돌면서
    #   1) row["answerable"]가 True가 아니면 건너뜀(답 없음 문항은 RAGAS 대상이 아님)
    #   2) row["contexts"]가 비어 있으면 건너뜀(지표가 ValueError를 냄)
    #   3) 남은 행을 아래 이름으로 옮긴 새 dict를 만들어 리스트에 넣음
    #      id ← row["id"], user_input ← row["question"], retrieved_contexts ← row["contexts"],
    #      response ← row["answer"], reference ← row["reference"]
    raise NotImplementedError("여기에 본인 코드를 작성함")


async def score_row(row: dict, metrics: dict) -> dict:
    """한 행(문항)을 RAGAS 4지표로 채점해 점수 dict를 돌려줌.

    인자: metrics는 지표 이름 → 지표 객체의 dict임. 키는 METRIC_NAMES와 같음.
    반환값: METRIC_NAMES 4키에 0 ~ 1 실수 점수, "reasons" 키에 지표별 판정 이유(없으면 None)를 담은 dict임.
    """
    # 할 일 2: 지표마다 ascore를 await로 호출함. 넘기는 칸은 지표마다 다름(교재 173쪽 표)
    #   context_precision: user_input, reference, retrieved_contexts
    #   context_recall:    user_input, retrieved_contexts, reference
    #   faithfulness:      user_input, response, retrieved_contexts
    #   answer_relevancy:  user_input, response
    #   예: result = await metrics["faithfulness"].ascore(user_input=..., response=..., retrieved_contexts=...)
    #       점수는 float(result.value), 이유는 result.reason
    raise NotImplementedError("여기에 본인 코드를 작성함")


def summarize(rows: list[dict]) -> dict:
    """채점된 행들의 지표별 평균과 검색 평균, 생성 평균을 냄.

    인자: rows의 각 행은 METRIC_NAMES 4키에 점수가 들어 있음.
    반환값: count, mean(지표 이름 → 평균), retrieval_mean, generation_mean 키를 가진 dict임.
            점수가 하나도 없는 지표의 평균은 None임.
    """
    # 할 일 3:
    #   1) 지표마다 rows를 돌며 점수를 더해 평균을 냄. math.isnan(score)인 값은 건너뜀
    #   2) retrieval_mean = precision 평균과 recall 평균의 평균
    #      generation_mean = faithfulness 평균과 relevancy 평균의 평균
    #   3) {"count": 행 수, "mean": {...}, "retrieval_mean": ..., "generation_mean": ...} 꼴로 돌려줌
    raise NotImplementedError("여기에 본인 코드를 작성함")
