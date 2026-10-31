"""평가셋 22문항을 search_docs.py의 검색·답변 함수로 일괄 실행해 RAGAS가 읽는 logs/results.json을 만듦."""

import argparse
import json
import sys
import time
import unicodedata
from datetime import datetime
from pathlib import Path

import search_docs  # 검색·답변 코드는 복사하지 않고 main 파일의 함수를 그대로 재사용함

sys.stdout.reconfigure(encoding="utf-8")  # Windows 콘솔에서 한글이 깨지지 않게 함

# ---------------------------------------------------------------------------
# 설정값(상수)
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
EVAL_SET_PATH = BASE_DIR.parents[1] / "eval-set.json"  # 평가셋(hands-on/solutions/eval-set.json, RAG와 GraphRAG가 함께 씀)
RESULTS_PATH = BASE_DIR / "logs" / "results.json"  # 결과 로그. ragas/evaluate_ragas.py가 이 경로를 읽음
DEFAULT_MODE = "hybrid_rerank"
DEFAULT_TOP_K = 5
DEFAULT_FUSION = "weighted"
NO_ANSWER_PREFIX = "확인 필요:"  # 답 없는 문항의 정답 꼴
ERROR_PREFIX = "오류:"  # 문항 실행이 실패했을 때 answer에 적는 머리말
SLEEP_BETWEEN_QUESTIONS = 1.0  # 문항 사이 쉬는 시간(초). Groq·Cohere 분당 호출 제한(429)을 피하기 위함


def normalize_for_match(text: str) -> str:
    """문장 대조용 정규화: 유니코드 NFKC로 통일하고 공백을 모두 지움.

    목적: PDF에서 뽑은 본문은 줄바꿈·띄어쓰기가 원문과 달라, 글자만 비교해야 "같은 문장"을 알아봄.
    """
    normalized = unicodedata.normalize("NFKC", text)
    return "".join(normalized.split())


def is_hit(relevance: list[dict], contexts: list[str]) -> bool:
    """정답 단서가 검색된 근거 안에 글자 그대로 있는지 봄(코드 채점 Hit@5, 교재 167쪽).

    방법: relevance의 clues(정답 단서) 중 하나라도 contexts 중 하나에 들어 있으면 True.
    반환값: relevance가 비어 있으면(답 없는 문항) False.
    """
    normalized_contexts = []
    for context in contexts:
        normalized_contexts.append(normalize_for_match(context))

    for item in relevance:
        for clue in item["clues"]:
            needle = normalize_for_match(clue)
            for context in normalized_contexts:
                if needle in context:
                    return True
    return False


def find_member_id(filters: list[dict]) -> str | None:
    """문항 filters에서 member_id를 찾음. 없으면 None(agent 역할로 검색)."""
    for item in filters:
        if "member_id" in item:
            return item["member_id"]
    return None


def run_one_question(resources: dict, item: dict, args) -> dict:
    """문항 하나를 검색·답변하고 결과 행(results.json의 rows 한 줄)을 만듦.

    방법: filters에 member_id가 있으면 auditor + 그 회원, 없으면 agent로 검색함. 오류가 나면 answer에
          "오류: ..."를 적고 근거는 빈 목록으로 두어 다음 문항으로 넘어갈 수 있게 함.
    반환값: 키 id, question, reference, answerable, answer, context_ids, contexts, hit인 dict임.
    """
    member_id = find_member_id(item["filters"])
    role = "agent"
    role_label = "(agent)"
    if member_id is not None:
        role = "auditor"  # 회원 상담 이력을 묻는 문항은 감사자 권한으로 실행함
        role_label = f"(auditor, 회원 {member_id})"
    print(f"  {role_label} {item['question']}")

    context_ids = []
    contexts = []
    try:
        result = search_docs.run_search(
            resources,
            item["question"],
            args.top_k,
            args.mode,
            role,
            member_id,
            args.fusion,
            show=False,
        )
        for hit in result["final_hits"]:
            context_ids.append(hit["chunk_id"])
            contexts.append(hit["text"])
        answer = search_docs.generate_answer(resources["llm"], item["question"], result["final_hits"])
    except Exception as error:  # 한 문항의 API 오류로 전체가 멈추지 않게 함. 오류 내용은 answer에 남김
        answer = f"{ERROR_PREFIX} {search_docs.explain_error(error)}"

    hit = is_hit(item["relevance"], contexts)
    print(f"  근거: {context_ids}  hit={hit}")
    print(f"  답변: {answer[:120]}")
    return {
        "id": item["id"],
        "question": item["question"],
        "reference": item["ground_truth"],
        "answerable": item["answerable"],
        "answer": answer,
        "context_ids": context_ids,
        "contexts": contexts,
        "hit": hit,
    }


def save_results(rows: list[dict], mode: str, top_k: int) -> None:
    """지금까지의 결과 행을 results.json에 씀. 문항마다 불러 중간에 실패해도 앞 결과가 남게 함."""
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    results = {
        "created_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "mode": mode,
        "top_k": top_k,
        "rows": rows,
    }
    with open(RESULTS_PATH, "w", encoding="utf-8") as file:
        json.dump(results, file, ensure_ascii=False, indent=2)


def print_summary(rows: list[dict], top_k: int) -> None:
    """답 있는 문항의 Hit@k 비율, 답 없는 문항의 "확인 필요:" 비율, 오류 문항 수를 표로 보여 줌."""
    answerable_total = 0
    answerable_hit = 0
    unanswerable_total = 0
    unanswerable_refused = 0
    error_count = 0
    for row in rows:
        if row["answer"].startswith(ERROR_PREFIX):
            error_count = error_count + 1
        if row["answerable"]:
            answerable_total = answerable_total + 1
            if row["hit"]:
                answerable_hit = answerable_hit + 1
        else:
            unanswerable_total = unanswerable_total + 1
            if row["answer"].startswith(NO_ANSWER_PREFIX):
                unanswerable_refused = unanswerable_refused + 1

    print("=" * 60)
    print("[요약]")
    print(f"  {'구분':<22} {'문항':>4} {'성공':>4} {'비율':>7}")
    if answerable_total > 0:
        ratio = answerable_hit / answerable_total * 100
        print(f"  {'답 있는 문항 Hit@' + str(top_k):<22} {answerable_total:>4} {answerable_hit:>4} {ratio:>6.1f}%")
    if unanswerable_total > 0:
        ratio = unanswerable_refused / unanswerable_total * 100
        print(f"  {'답 없는 문항 확인 필요':<22} {unanswerable_total:>4} {unanswerable_refused:>4} {ratio:>6.1f}%")
    if error_count > 0:
        print(f"  오류로 끝난 문항: {error_count}개 (answer가 '{ERROR_PREFIX}'로 시작). --start N 으로 그 문항부터 다시 실행함")
    print(f"  결과 파일: {RESULTS_PATH}")


def main() -> None:
    """평가셋을 읽어 문항마다 검색·답변을 실행하고 results.json과 요약 표를 만듦."""
    parser = argparse.ArgumentParser(description="평가셋 일괄 실행 → logs/results.json")
    parser.add_argument("--limit", type=int, default=None, help="앞 N문항만 실행(빠른 확인)")
    parser.add_argument("--start", type=int, default=1, help="N번째 문항부터 실행(1부터 셈). 중간에 끊겼을 때 이어서 돌림")
    parser.add_argument("--mode", choices=search_docs.MODES, default=DEFAULT_MODE, help=f"검색 모드(기본 {DEFAULT_MODE})")
    parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K, help=f"근거 수(기본 {DEFAULT_TOP_K})")
    parser.add_argument("--fusion", choices=search_docs.FUSIONS, default=DEFAULT_FUSION, help="융합 방식(기본 weighted)")
    args = parser.parse_args()

    with open(EVAL_SET_PATH, "r", encoding="utf-8") as file:
        eval_set = json.load(file)
    questions = eval_set["questions"]
    if args.limit is not None:
        questions = questions[: args.limit]
    questions = questions[args.start - 1 :]  # --start 3 이면 3번째 문항부터

    print("=" * 60)
    print(f"[준비] 평가셋 {len(questions)}문항 (시작 {args.start}번째), 모드 {args.mode}, top_k {args.top_k}")
    resources = search_docs.load_resources(args.mode, True)

    rows = []
    for number, item in enumerate(questions, start=args.start):
        print("=" * 60)
        print(f"[{number}/{args.start + len(questions) - 1}] {item['id']}")
        row = run_one_question(resources, item, args)
        rows.append(row)
        save_results(rows, args.mode, args.top_k)  # 문항마다 저장해 중간 실패에도 앞 결과를 보존함
        time.sleep(SLEEP_BETWEEN_QUESTIONS)  # 호출 제한(429)을 피하려고 문항 사이에 잠깐 쉼

    print_summary(rows, args.top_k)
    print("=" * 60)
    print("완료")


if __name__ == "__main__":
    main()
