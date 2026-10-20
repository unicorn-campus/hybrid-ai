"""검색기 결과 로그(results.json)를 RAGAS 핵심 4지표로 채점하는 실행 파일(main)."""

import argparse
import asyncio
import json
import math
import os
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path

# Windows 콘솔에서 한글이 깨지지 않도록 출력 인코딩을 먼저 고정함
sys.stdout.reconfigure(encoding="utf-8")

from dotenv import load_dotenv
from openai import AsyncOpenAI
from ragas import Dataset, experiment
from ragas.embeddings import LiteLLMEmbeddings
from ragas.llms import llm_factory
from ragas.metrics.collections import AnswerRelevancy, ContextPrecisionWithReference, ContextRecall, Faithfulness

import core_scoring as scoring  # 교육생: 본인 코드로 바꾸려면 "import my_scoring as scoring"

# ---------- 설정값(맨 위 상수) ----------
HERE = Path(__file__).resolve().parent  # 이 파일이 있는 ragas 폴더. 어디서 실행해도 경로가 어긋나지 않게 기준으로 삼음
ROOT = HERE.parents[3]  # 저장소 루트(hybrid-ai). ragas → rag → solutions → hands-on → hybrid-ai 순으로 올라감
ENV_PATH = ROOT / "secrets" / ".env"  # GROQ_API_KEY, COHERE_API_KEY가 있는 파일. 키 값은 어디에도 적지 않음
DEFAULT_RESULTS_PATH = HERE.parent / "retriever" / "logs" / "results.json"  # 검색기 run_eval.py가 만드는 결과 로그
LOG_DIR = HERE / "logs"  # 채점 결과 json을 저장하는 폴더

JUDGE_MODEL = "openai/gpt-oss-120b"  # 평가자(채점) LLM. Groq 제공사 사정으로 바뀔 수 있음, 교육 전날 확인
JUDGE_MAX_TOKENS = 4096  # 평가자 답변(판정 JSON) 길이 상한. 기본 1024는 긴 근거에서 잘림
GROQ_BASE_URL = "https://api.groq.com/openai/v1"  # Groq의 OpenAI 호환 주소. openai 패키지로 그대로 부름
# AnswerRelevancy가 쓰는 임베딩. 인덱싱과 같은 Cohere 모델(API, 2048차원)을 LiteLLM "제공사/모델" 꼴 이름으로 적음
EMBEDDING_MODEL = "cohere/embed-v5.0-fast"
EMBEDDING_LABEL = "Cohere embed-v5.0-fast (API, 2048차원)"  # 단계 2 화면 표시용
MAX_CONCURRENT_ROWS = 2  # 동시에 채점하는 행 수. Groq 분당 호출 제한(429)을 피하려고 작게 둠
API_MAX_RETRIES = 5  # 429(호출 제한) 등 일시 오류 때 openai 클라이언트가 스스로 다시 부르는 횟수

# 표의 열 머리말(지표 이름 → 화면 표시 이름). 순서는 교재 168쪽 「위, 정, 출, 관」 순임
METRIC_LABELS = {
    "context_precision": "ContextPrecision",
    "context_recall": "ContextRecall",
    "faithfulness": "Faithfulness",
    "answer_relevancy": "AnswerRelevancy",
}


def parse_args() -> argparse.Namespace:
    """명령행 옵션을 읽음. 모두 선택 사항이며 기본값은 맨 위 상수를 따름."""
    parser = argparse.ArgumentParser(description="검색기 결과 로그를 RAGAS 핵심 4지표로 채점함")
    parser.add_argument("--results", default=str(DEFAULT_RESULTS_PATH), help="결과 로그 json 경로")
    parser.add_argument("--limit", type=int, default=0, help="앞 N행만 채점(0이면 전체). 빠른 확인용")
    parser.add_argument("--repeat", type=int, default=1, help="같은 행을 N번 채점해 평균과 표준편차를 냄(기본 1)")
    parser.add_argument("--show-reason", action="store_true", help="지표별 판정 이유를 문항마다 출력")
    return parser.parse_args()


def print_header(step_no: int, title: str) -> None:
    """단계 구분선과 머리말을 같은 꼴로 찍음(세 프로그램 공통 형식)."""
    print("=" * 60)
    print(f"[단계 {step_no}] {title}")


def load_results(results_path: Path) -> dict:
    """검색기 결과 로그 json을 읽어 dict로 돌려줌. 파일이 없으면 안내 후 종료함."""
    if not results_path.exists():
        print(f"결과 로그가 없음: {results_path}")
        print("먼저 retriever 폴더에서 run_eval.py를 실행하거나 --results 로 다른 파일을 지정함")
        sys.exit(1)
    with open(results_path, "r", encoding="utf-8") as file:
        results = json.load(file)
    # 평가셋(eval-set.json)은 "questions" 키라 "rows"가 없음. 다른 파일을 잘못 넘긴 경우를 바로 알려 줌
    if "rows" not in results:
        print(f"'rows' 키가 없음: {results_path}")
        print("run_eval.py가 만든 results.json인지 확인(eval-set.json이 아님)")
        sys.exit(1)
    return results


def build_metrics() -> dict:
    """평가자 LLM과 임베딩을 만들고 RAGAS 4지표 객체를 지표 이름 → 객체 dict로 돌려줌.

    방법: ragas 0.4의 collections 지표는 llm_factory가 만든 LLM만 받음(LangChain 래퍼는 받지 않음).
          Groq는 OpenAI 호환 주소를 제공하므로 openai 패키지의 AsyncOpenAI에 base_url만 바꿔 넘김.
          임베딩은 ragas에 Cohere 직접 지원이 없어 LiteLLM(여러 제공사 API를 한 꼴로 부르는 패키지)을 거침.
    예외: GROQ_API_KEY 또는 COHERE_API_KEY가 없으면 안내 후 종료함.
    """
    load_dotenv(ENV_PATH)
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        print(f"GROQ_API_KEY가 없음. {ENV_PATH} 에 키를 넣어야 함")
        sys.exit(1)
    cohere_key = os.getenv("COHERE_API_KEY")
    if not cohere_key:
        print(f"COHERE_API_KEY가 없음. {ENV_PATH} 에 키를 넣어야 함")
        sys.exit(1)

    client = AsyncOpenAI(api_key=api_key, base_url=GROQ_BASE_URL, max_retries=API_MAX_RETRIES)
    # temperature 0: 같은 입력에 되도록 같은 판정이 나오게 함(채점 흔들림을 줄임)
    # max_tokens: ragas 기본값(1024)은 한국어 근거가 긴 문항(카드 혜택 Q08)에서 판정 JSON이 잘려 채점이 실패함(실측)
    judge_llm = llm_factory(JUDGE_MODEL, client=client, temperature=0, max_tokens=JUDGE_MAX_TOKENS)
    print(f"  평가자 LLM: {JUDGE_MODEL} (Groq, OpenAI 호환 주소)")

    # ragas에 Cohere 직접 지원이 없어 LiteLLM을 거침. AnswerRelevancy는 역질문과 원 질문을 같은 종류(search_query)로
    # 임베딩해 비교하므로 input_type을 search_query 하나로 둠
    embeddings = LiteLLMEmbeddings(model=EMBEDDING_MODEL, api_key=cohere_key, input_type="search_query")
    print(f"  임베딩 모델: {EMBEDDING_LABEL}")

    metrics = {
        "context_precision": ContextPrecisionWithReference(llm=judge_llm),  # 정답(reference)이 있는 평가셋이라 WithReference
        "context_recall": ContextRecall(llm=judge_llm),
        "faithfulness": Faithfulness(llm=judge_llm),
        "answer_relevancy": AnswerRelevancy(llm=judge_llm, embeddings=embeddings),  # 역질문 비교에 임베딩이 필요함
    }
    return metrics


@experiment()  # 데코레이터: 아래 함수를 감싸 arun 기능(행마다 실행해 표로 모으기)을 붙이는 표식
async def score_experiment(row: dict, metrics: dict, semaphore: asyncio.Semaphore, show_reason: bool) -> dict:
    """실험 함수: 한 행을 채점해 행 내용 + 4지표 점수를 돌려줌(교재 174쪽 ragas_eval과 같은 역할).

    방법: arun이 모든 행을 한꺼번에 태스크로 만들기 때문에 세마포어(동시에 들어갈 수 있는 수를 세는 자물쇠)로
          동시 채점 행 수를 MAX_CONCURRENT_ROWS로 제한함. 채점이 끝나면 행마다 한 줄을 찍음.
    반환값: id, 4지표 점수, reasons, elapsed_seconds를 담은 dict임. arun이 이것을 모아 실험 결과 표를 만듦.
    """
    async with semaphore:
        started_at = time.time()
        scores = await scoring.score_row(row, metrics)
        elapsed_seconds = time.time() - started_at

    line = f"  {row['id']:<4}"
    for metric_name in scoring.METRIC_NAMES:
        line = line + f"  {METRIC_LABELS[metric_name]} {scores[metric_name]:.3f}"
    print(line + f"  ({elapsed_seconds:.1f}초)")
    if show_reason:
        print_reasons(scores["reasons"])

    result = {"id": row["id"], "elapsed_seconds": elapsed_seconds}
    for metric_name in scoring.METRIC_NAMES:
        result[metric_name] = scores[metric_name]
    result["reasons"] = scores["reasons"]
    return result


def print_reasons(reasons: dict) -> None:
    """지표별 판정 이유를 찍음. ragas 0.4.3 collections 지표는 reason을 주지 않아 대부분 「없음」이 찍힘."""
    for metric_name in scoring.METRIC_NAMES:
        reason = reasons[metric_name]
        if reason is None:
            reason = "(없음 — ragas 0.4.3 collections 지표는 점수만 돌려줌)"
        print(f"      - {METRIC_LABELS[metric_name]} 이유: {reason}")


async def run_all_rounds(rows: list[dict], metrics: dict, repeat: int, show_reason: bool) -> dict:
    """행 전체를 repeat번 채점해 문항 id → 회차별 점수 리스트의 dict로 모음.

    방법: 교재 173 ~ 174쪽처럼 Dataset(inmemory)에 행을 담고 @experiment 함수의 arun으로 돌림.
          arun은 실패한 행을 경고만 찍고 건너뛰므로, 회차마다 빠진 id를 찾아 화면에 알림.
    반환값: {"Q01": [1회차 결과 dict, 2회차 결과 dict, ...], ...} 꼴임. 실패한 회차는 리스트에 들어가지 않음.
    """
    dataset = Dataset(name="rag-eval", backend="inmemory")  # inmemory: 파일을 만들지 않고 메모리에만 담음
    for row in rows:
        dataset.append(row)

    semaphore = asyncio.Semaphore(MAX_CONCURRENT_ROWS)
    rounds_by_id = {}
    for row in rows:
        rounds_by_id[row["id"]] = []

    for round_no in range(1, repeat + 1):
        if repeat > 1:
            print(f"  --- {round_no}회차 ---")
        experiment_result = await score_experiment.arun(
            dataset, name=f"round-{round_no}", metrics=metrics, semaphore=semaphore, show_reason=show_reason
        )
        scored_ids = []
        for item in experiment_result:
            rounds_by_id[item["id"]].append(item)
            scored_ids.append(item["id"])
        failed_count = 0
        for row in rows:
            if row["id"] not in scored_ids:
                print(f"  {row['id']}  채점 실패 — 이번 회차 결과에서 제외함(위 Warning 참고)")
                failed_count = failed_count + 1
        # 한 회차에서 여러 행이 한꺼번에 실패하면 모델 문제보다 Groq 분당 호출 제한(429)일 가능성이 큼
        if failed_count >= 2:
            print(f"  실패 행 {failed_count}개: 호출 제한(429) 의심 — 2분 뒤 --limit 를 줄여 재실행")
    return rounds_by_id


def merge_rounds(rows: list[dict], rounds_by_id: dict) -> list[dict]:
    """회차별 결과를 문항 하나당 한 행으로 합침(점수는 회차 평균, 표준편차는 회차가 2개 이상일 때만).

    반환값: id, question, 4지표 평균 점수, stdev(지표별 표준편차 또는 None), reasons(마지막 회차), rounds(회차별 점수)를
            담은 행의 리스트임. 모든 회차가 실패한 문항은 빠짐.
    """
    merged_rows = []
    for row in rows:
        round_results = rounds_by_id[row["id"]]
        if len(round_results) == 0:
            continue
        merged = {"id": row["id"], "question": row["user_input"], "stdev": {}, "rounds": []}
        for metric_name in scoring.METRIC_NAMES:
            values = []
            for round_result in round_results:
                value = round_result[metric_name]
                if not math.isnan(value):
                    values.append(value)
            if len(values) == 0:
                merged[metric_name] = float("nan")
                merged["stdev"][metric_name] = None
            else:
                merged[metric_name] = statistics.mean(values)
                if len(values) >= 2:
                    merged["stdev"][metric_name] = statistics.pstdev(values)  # 모집단 표준편차: 회차 간 흔들림의 크기
                else:
                    merged["stdev"][metric_name] = None
        merged["reasons"] = round_results[-1]["reasons"]
        for round_result in round_results:
            round_scores = {}
            for metric_name in scoring.METRIC_NAMES:
                round_scores[metric_name] = round_result[metric_name]
            merged["rounds"].append(round_scores)
        merged_rows.append(merged)
    return merged_rows


def format_score(value: float | None) -> str:
    """점수를 소수 3자리 문자열로. None이나 nan은 「-」로 보여 줌."""
    if value is None or math.isnan(value):
        return "-"
    return f"{value:.3f}"


def print_table(merged_rows: list[dict], summary: dict, repeat: int) -> None:
    """문항 × 4지표 표, 평균 행, 검색/생성 평균을 찍음. repeat가 2 이상이면 표준편차(±)도 같이 찍음."""
    column_width = 18
    header = f"{'문항':<6}"
    for metric_name in scoring.METRIC_NAMES:
        header = header + f"{METRIC_LABELS[metric_name]:<{column_width}}"
    print(header)

    for row in merged_rows:
        line = f"{row['id']:<6}"
        for metric_name in scoring.METRIC_NAMES:
            cell = format_score(row[metric_name])
            if repeat > 1 and row["stdev"][metric_name] is not None:
                cell = cell + f"±{row['stdev'][metric_name]:.3f}"
            line = line + f"{cell:<{column_width}}"
        print(line)

    mean_line = f"{'평균':<5}"  # 한글 2자는 콘솔에서 4칸을 차지해 1칸 적게 맞춤
    for metric_name in scoring.METRIC_NAMES:
        mean_line = mean_line + f"{format_score(summary['mean'][metric_name]):<{column_width}}"
    print(mean_line)
    retrieval_mean = format_score(summary["retrieval_mean"])
    generation_mean = format_score(summary["generation_mean"])
    print(f"검색 평균(Precision, Recall) {retrieval_mean} | 생성 평균(Faithfulness, Relevancy) {generation_mean}")


def save_log(results_path: Path, merged_rows: list[dict], summary: dict, counts: dict, repeat: int) -> Path:
    """채점 결과를 logs/ragas-{YYYYMMDD-HHMMSS}.json 에 저장하고 그 경로를 돌려줌. nan은 json에 null로 적음."""
    LOG_DIR.mkdir(exist_ok=True)
    log_path = LOG_DIR / f"ragas-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"

    rows_for_json = []
    for row in merged_rows:
        row_for_json = {"id": row["id"], "question": row["question"], "scores": {}, "stdev": row["stdev"]}
        for metric_name in scoring.METRIC_NAMES:
            if math.isnan(row[metric_name]):
                row_for_json["scores"][metric_name] = None
            else:
                row_for_json["scores"][metric_name] = row[metric_name]
        row_for_json["reasons"] = row["reasons"]
        row_for_json["rounds"] = row["rounds"]
        rows_for_json.append(row_for_json)

    log = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "results_path": str(results_path),
        "judge_model": JUDGE_MODEL,
        "embedding_model": EMBEDDING_MODEL,
        "repeat": repeat,
        "counts": counts,
        "rows": rows_for_json,
        "summary": summary,
    }
    with open(log_path, "w", encoding="utf-8") as file:
        json.dump(log, file, ensure_ascii=False, indent=2)
    return log_path


def main() -> None:
    """[단계 1] 로그 읽기 → [단계 2] 평가자 준비 → [단계 3] 채점 → [단계 4] 표 출력과 저장."""
    args = parse_args()
    results_path = Path(args.results)

    print_header(1, "결과 로그 읽기")
    results = load_results(results_path)
    all_rows = results["rows"]
    rows = scoring.select_rows(results)
    skipped_count = len(all_rows) - len(rows)
    if args.limit > 0:
        rows = rows[: args.limit]
    print(f"  파일: {results_path}")
    print(f"  전체 행 수: {len(all_rows)} | 채점 대상: {len(rows)} | 제외(답 없음 또는 근거 없음): {skipped_count}")
    if len(rows) == 0:
        print("  채점할 행이 없어 끝냄")
        return
    counts = {"total_rows": len(all_rows), "scored_rows": len(rows), "skipped_rows": skipped_count}

    print_header(2, "평가자 준비")
    metrics = build_metrics()

    print_header(3, f"채점 진행 (동시 {MAX_CONCURRENT_ROWS}행, 반복 {args.repeat}회)")
    # asyncio.run: ragas의 ascore가 비동기(async) 함수라 이렇게 한 번 감싸서 실행함
    rounds_by_id = asyncio.run(run_all_rounds(rows, metrics, args.repeat, args.show_reason))
    merged_rows = merge_rounds(rows, rounds_by_id)
    if len(merged_rows) == 0:
        print("  채점에 성공한 행이 없어 끝냄")
        return

    print_header(4, f"채점 결과 (평가자: {JUDGE_MODEL}, 반복 {args.repeat}회)")
    summary = scoring.summarize(merged_rows)
    print_table(merged_rows, summary, args.repeat)
    print("  읽는 법: Recall이 낮으면 검색(청킹, 임베딩, Top-k) 쪽, Faithfulness가 낮으면 답변(프롬프트) 쪽을 봄(교재 176쪽)")
    log_path = save_log(results_path, merged_rows, summary, counts, args.repeat)
    print(f"  결과 저장: {log_path}")


if __name__ == "__main__":
    main()
