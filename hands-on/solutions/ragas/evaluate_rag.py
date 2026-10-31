"""RAG 검색기를 하이퍼 파라미터 버전마다 실행하고 코드 평가 4지표와 RAGAS 5지표로 채점해 비교하는 실행 파일(main)."""

import argparse
import asyncio
import contextlib
import io
import json
import re
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path


def use_student_code(student_module: str) -> bool:
    """--mine 옵션이 있으면 교육생 파일(my_*.py)로 돌림. 파일이 없으면 강사 뼈대(my_*.template.py)를 복사해 만듦.

    교육생 파일은 Git이 무시하므로(.gitignore) 강사가 뼈대를 고쳐도 pull 충돌이 나지 않음.
    이 파일의 import 줄은 고치지 않고 옵션으로만 바꿈.
    """
    if "--mine" not in sys.argv:
        return False
    folder = Path(__file__).resolve().parent
    student_path = folder / f"{student_module}.py"
    if not student_path.exists():
        shutil.copyfile(folder / f"{student_module}.template.py", student_path)
        print(f"[--mine] {student_path.name} 이 없어 {student_module}.template.py 를 복사해 만듦")
    return True


sys.stdout.reconfigure(encoding="utf-8")  # Windows 콘솔에서 한글이 깨지지 않게 함
sys.stderr.reconfigure(encoding="utf-8")  # 오류 메시지(NotImplementedError의 한글 안내)도 깨지지 않게 함

if use_student_code("my_eval"):
    import my_eval as core  # 교육생 코드(--mine)
else:
    import core_eval as core  # 강사 코드(기본)

# ---------------------------------------------------------------------------
# 평가 대상 RAG 검색기를 불러옴. 검색기는 언제나 강사 코드(core_search.py)로 돎(강사 지시 2026-10-31).
# 검색기도 명령행에 --mine이 있으면 교육생 검색기(my_search.py)로 바뀌므로, 불러오는 동안만 --mine을 빼 둠
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent  # 이 파일이 있는 ragas 폴더
RETRIEVER_DIR = BASE_DIR.parent / "rag" / "retriever"  # 평가 대상 검색기 폴더
sys.path.insert(0, str(RETRIEVER_DIR))
saved_argv = sys.argv
sys.argv = []
for argument in saved_argv:
    if argument != "--mine":
        sys.argv.append(argument)
import search_docs as retriever  # noqa: E402  (명령행을 정리한 뒤에 불러와야 해서 맨 위에 두지 않음)
sys.argv = saved_argv

from dotenv import dotenv_values  # noqa: E402
from openai import AsyncOpenAI  # noqa: E402
from ragas import Dataset, experiment  # noqa: E402
from ragas.embeddings import OpenAIEmbeddings  # noqa: E402
from ragas.llms import llm_factory  # noqa: E402

# ---------------------------------------------------------------------------
# 설정값(맨 위 상수)
# ---------------------------------------------------------------------------
ROOT_DIR = BASE_DIR.parents[2]  # ragas → solutions → hands-on → 저장소 루트
SECRETS_ENV_PATH = ROOT_DIR / "secrets" / ".env"  # GROQ_API_KEY, COHERE_API_KEY(값은 화면과 파일에 찍지 않음)
EVAL_SET_PATH = ROOT_DIR / "hands-on" / "solutions" / "eval-set.json"  # 평가셋(검색기와 같은 파일)
RESULTS_DIR = BASE_DIR / "results"  # 결과 파일: results/{하이퍼 파라미터명}/evaluate_{YYMMDDHHMM}_{vNN}.md

# 평가자(채점관) LLM. 답변 LLM(openai/gpt-oss-120b)과 다른 모델이라 자기 답을 자기가 채점하지 않음(교재 176쪽)
JUDGE_MODEL = "qwen/qwen3.8-27b"
GROQ_BASE_URL = "https://api.groq.com/openai/v1"  # Groq의 OpenAI 호환 주소. openai 패키지로 그대로 부름
JUDGE_MAX_TOKENS = 4096  # 평가자 답(판정 JSON) 길이 상한. 기본 1024는 근거가 길면 잘릴 수 있음
JUDGE_TIMEOUT_SECONDS = 60  # 평가자 호출 한 번의 제한 시간
JUDGE_MAX_RETRIES = 3  # 429(호출 제한), 5xx 때 openai 클라이언트가 스스로 다시 부르는 횟수
# AnswerRelevancy용 임베딩. 인덱서와 같은 Cohere 모델을 Cohere의 OpenAI 호환 주소로 부름(교재 184쪽 실행과 같음)
EMBEDDING_MODEL = "embed-v5.0-fast"
COHERE_COMPAT_URL = "https://api.cohere.ai/compatibility/v1"
MAX_CONCURRENT_ROWS = 2  # 동시에 채점하는 행 수. arun은 모든 행을 한꺼번에 돌리므로 429를 피하려고 직접 제한함

# 흔들림 폭: 다시 채점만 해도 생기는 점수 차이. 이보다 작은 차이는 「변화 없음」(교재 177쪽).
# 0.03은 교재 그림 예시값임. --repeat 3으로 기준선을 반복 채점하면 LLM 지표는 실측값으로 바꿔 씀
NOISE = 0.03
MIN_DETECTABLE = 0.125  # 답 있는 8문항 중 6문항이 정답 근거 1개 → 한 문항이 바뀌면 Recall 평균이 1 ÷ 8 = 0.125 움직임

ROLE = "auditor"  # 검색기 역할. 약관, 혜택, 상담 이력을 모두 봄(회원 문항은 그 회원 상담만)
SNIPPET_LENGTH = 60  # 화면과 결과 파일에 보여 줄 본문 앞 글자 수
CITATION_PATTERN = re.compile(r"\s*\[[A-Za-z0-9]+-[A-Za-z0-9-]+\]")  # 답변 끝 인용 표시(예: [D3-0019])

# 지원하는 하이퍼 파라미터(재색인 없이 바꿀 수 있는 것)와 값의 형. 현재 값은 검색기 상수에서 읽음(기준선 기본값)
SUPPORTED = {
    "top_k": retriever.DEFAULT_TOP_K,
    "fusion": "weighted",
    "vector_weight": retriever.VECTOR_WEIGHT,
    "rerank_model": retriever.RERANK_MODEL,
    "llm_model": retriever.LLM_MODEL,
}
VALUE_TYPES = {"top_k": int, "fusion": str, "vector_weight": float, "rerank_model": str, "llm_model": str}
FUSION_CHOICES = ["weighted", "rrf"]

# 화면과 결과 파일의 열 이름(교재 약칭 병기)
METRIC_LABELS = {
    "hit": "하 Hit@k",
    "recall": "빠 Recall@k",
    "mrr": "빨 MRR",
    "ndcg": "앞 nDCG@k",
    "context_precision": "위 ContextPrecision",
    "context_recall": "정 ContextRecall",
    "faithfulness": "출 Faithfulness",
    "answer_relevancy": "관 AnswerRelevancy",
    "factual_correctness": "답 FactualCorrectness",
}
ALL_METRICS = core.CODE_METRICS + core.LLM_METRICS


# ---------------------------------------------------------------------------
# 화면 출력 도움 함수
# ---------------------------------------------------------------------------
def print_step(title: str) -> None:
    """단계 구분선과 제목을 같은 꼴로 찍음."""
    print("=" * 70)
    print(title)


def snippet(text: str) -> str:
    """본문 앞부분을 한 줄로 줄여 보여 줌."""
    one_line = " ".join(text.split())
    return one_line[:SNIPPET_LENGTH]


def fmt(value) -> str:
    """점수를 표에 쓸 글로 바꿈. None은 「-」(계산 안 함), nan은 「실패」(채점 실패)."""
    if value is None:
        return "-"
    if isinstance(value, float) and value != value:  # nan은 자기 자신과 같지 않음
        return "실패"
    if isinstance(value, int):
        return str(value)
    return f"{value:.2f}"


# ---------------------------------------------------------------------------
# 준비: 명령행 값 변환, 평가셋, 시작 검사
# ---------------------------------------------------------------------------
def parse_value(param: str, raw: str):
    """명령행 글자를 하이퍼 파라미터 형(int, float, str)으로 바꿈. 잘못된 값이면 안내 뒤 종료함."""
    value_type = VALUE_TYPES[param]
    try:
        value = value_type(raw)
    except ValueError:
        print(f"  오류: {param} 값 {raw} 을(를) {value_type.__name__}(으)로 바꿀 수 없음")
        sys.exit(1)
    if param == "top_k" and value < 1:
        print("  오류: top_k는 1 이상")
        sys.exit(1)
    if param == "vector_weight" and (value < 0 or value > 1):
        print("  오류: vector_weight는 0 ~ 1(BM25 비중은 1 - 값)")
        sys.exit(1)
    if param == "fusion" and value not in FUSION_CHOICES:
        print(f"  오류: fusion은 {FUSION_CHOICES} 중 하나")
        sys.exit(1)
    return value


def load_eval_items(qids: list[str] | None) -> list[dict]:
    """평가셋을 읽고 --qid로 고른 문항만 돌려줌. 없는 번호면 안내 뒤 종료함."""
    with open(EVAL_SET_PATH, "r", encoding="utf-8") as file:
        eval_set = json.load(file)
    items = eval_set["questions"]
    if qids is None:
        return items
    selected = []
    for qid in qids:
        found = None
        for item in items:
            if item["id"] == qid:
                found = item
        if found is None:
            all_ids = []
            for item in items:
                all_ids.append(item["id"])
            print(f"  오류: 평가셋에 {qid} 가 없음 → {all_ids} 중에서 고름")
            sys.exit(1)
        selected.append(found)
    return selected


def check_judge_secrets() -> dict:
    """평가자와 임베딩에 쓸 키 2개를 읽음. 검색기와 같은 키라 따로 늘지 않음(값은 찍지 않음)."""
    values = dotenv_values(SECRETS_ENV_PATH)
    secrets = {}
    for key_name in ["GROQ_API_KEY", "COHERE_API_KEY"]:
        value = values.get(key_name, "")
        if not value:
            print(f"  오류: {SECRETS_ENV_PATH} 에 {key_name} 가 없거나 비어 있음")
            sys.exit(1)
        secrets[key_name] = value
    return secrets


def count_relevant_by_question(resources: dict, items: list[dict]) -> dict:
    """문항마다 관련 청크 수를 세고, 어느 청크에도 없는 정답 단서가 있으면 안내 뒤 종료함(시작 검사).

    목적: 정답 단서가 청크 경계에 걸려 어느 청크에도 통째로 없으면 관련 청크가 0이 되어 Hit와 nDCG가 늘 0이 됨.
          평가셋이나 청킹을 고쳐야 하는 문제이므로 채점을 시작하지 않음.
    """
    all_texts = []
    for chunk in resources["chunks"]:
        all_texts.append(chunk["text"])

    missing = []
    relevant_counts = {}
    for item in items:
        for evidence in item["relevance"]:
            for clue in evidence["clues"]:
                found = False
                for text in all_texts:
                    if core.compact_text(clue) in core.compact_text(text):
                        found = True
                        break
                if not found:
                    missing.append(f"{item['id']} {evidence['location']}: {clue[:40]}")
        relevant_counts[item["id"]] = core.count_relevant_chunks(all_texts, item["relevance"])

    if len(missing) > 0:
        print("  오류: 색인 어느 청크에도 없는 정답 단서가 있음(청크 경계에 걸렸거나 원문과 다름)")
        for line in missing:
            print(f"    - {line}")
        print("  → 평가셋의 정답 단서를 원문 그대로 고치거나, 청크 크기와 오버랩을 바꿔 다시 색인함")
        sys.exit(1)
    return relevant_counts


# ---------------------------------------------------------------------------
# ② 검색기 실행: 버전 설정 바꾸기, 문항마다 run_workflow, ragas용 정리
# ---------------------------------------------------------------------------
def remember_settings(resources: dict) -> dict:
    """검색기 모듈 상수와 LLM 객체의 원래 값을 기억함(버전이 끝나면 되돌리기 위함)."""
    return {
        "VECTOR_WEIGHT": retriever.VECTOR_WEIGHT,
        "BM25_WEIGHT": retriever.BM25_WEIGHT,
        "RERANK_MODEL": retriever.RERANK_MODEL,
        "LLM_MODEL": retriever.LLM_MODEL,
        "llm": resources["llm"],
    }


def restore_settings(resources: dict, originals: dict) -> None:
    """검색기 설정을 원래 값으로 되돌림. 다음 버전이 기준선 설정에서 출발하게 함."""
    retriever.VECTOR_WEIGHT = originals["VECTOR_WEIGHT"]
    retriever.BM25_WEIGHT = originals["BM25_WEIGHT"]
    retriever.RERANK_MODEL = originals["RERANK_MODEL"]
    retriever.LLM_MODEL = originals["LLM_MODEL"]
    resources["llm"] = originals["llm"]


def apply_version(resources: dict, version: dict, originals: dict, retriever_secrets: dict) -> dict:
    """버전의 하이퍼 파라미터 값을 검색기에 적용하고 run_workflow에 넘길 인자(top_k, fusion)를 돌려줌.

    방법: 바꾸는 방법이 하이퍼 파라미터마다 셋으로 나뉨(계획서 4.2).
          ① 인자: top_k, fusion은 run_workflow 인자로 넘김
          ② 모듈 상수: vector_weight(VECTOR_WEIGHT와 BM25_WEIGHT를 함께), rerank_model은 호출 때 상수를 읽으므로 바꿔 두면 됨
          ③ 자원 다시 만들기: llm_model은 LLM 객체가 색인을 열 때 이미 만들어져 있어 새 ChatGroq를 만들어 끼움
    부수효과: 검색기 모듈 상수와 resources["llm"]을 바꿈. 끝나면 restore_settings로 되돌림.
    """
    restore_settings(resources, originals)  # 늘 기준선 설정에서 출발(한 번에 하나만 바꿈)
    run_args = {"top_k": retriever.DEFAULT_TOP_K, "fusion": "weighted"}
    param = version["param"]
    value = version["value"]
    if param == "top_k":
        run_args["top_k"] = value
    elif param == "fusion":
        run_args["fusion"] = value
    elif param == "vector_weight":
        # BM25_WEIGHT는 따로 선언된 상수라 벡터 비중만 바꾸면 두 비중의 합이 1이 아니게 됨
        retriever.VECTOR_WEIGHT = value
        retriever.BM25_WEIGHT = round(1 - value, 4)
    elif param == "rerank_model":
        retriever.RERANK_MODEL = value
    elif param == "llm_model":
        retriever.LLM_MODEL = value
        resources["llm"] = retriever.ChatGroq(
            model=value,
            temperature=retriever.LLM_TEMPERATURE,
            api_key=retriever_secrets["GROQ_API_KEY"],
            timeout=retriever.LLM_TIMEOUT_SECONDS,
            max_retries=retriever.LLM_MAX_RETRIES,
        )
    return run_args


def clean_for_ragas(question: str, answer: str) -> tuple[str, str]:
    """ragas에 넘길 질문과 답변을 정리함.

    목적: 평가자 LLM은 답변을 주장으로 쪼갤 때 질문의 회원번호(M-3001)와 답변의 인용 표시([D3-0019])까지 주장에 넣음.
          색인 본문에는 둘 다 없어 「근거에 없음」으로 판정되어 Faithfulness가 0이 됨(2026-10-31 실측, 계획서 9.1).
    방법: 질문은 검색기가 ⑤ 답변 생성에 넘긴 것과 같은 규칙으로 회원번호를 지우고, 답변은 인용 표시를 지움.
          모든 버전에 같게 적용하므로 버전 비교는 공정함.
    """
    question_clean = " ".join(retriever.MEMBER_ID_PATTERN.sub(" ", question).split())
    answer_clean = CITATION_PATTERN.sub("", answer).strip()
    return question_clean, answer_clean


def member_of(item: dict) -> str | None:
    """평가셋 문항의 filters에 회원번호가 있으면 돌려줌(그 회원의 상담 이력만 검색하게)."""
    for condition in item["filters"]:
        if "member_id" in condition:
            return condition["member_id"]
    return None


def is_confirm_needed_answer(status: str, answer: str) -> bool:
    """답 없는 문항의 「확인 필요」 판정: 근거 부족, 검증 실패로 끝났거나 답이 「확인 필요」로 시작하면 맞음."""
    if status in ["근거 부족", "검증 실패"]:
        return True
    if answer.strip().startswith("확인 필요"):
        return True
    return False  # 답변 완료, 되묻기, 잡담, 오류는 틀림


def run_retriever(resources: dict, items: list[dict], version: dict, originals: dict,
                  retriever_secrets: dict) -> list[dict]:
    """② 한 버전으로 문항마다 검색기를 실행해 결과 정보 행 목록을 돌려줌.

    방법: 검색기의 화면 출력은 문항별로 모아(log) 결과 파일 상세에 붙이고, 화면에는 한 줄 요약만 찍음.
          검색기 예외는 그 문항을 「오류」로 남기고 다음 문항으로 넘어감(한 문항 때문에 버전 전체를 버리지 않음).
    """
    run_args = apply_version(resources, version, originals, retriever_secrets)
    rows = []
    for item in items:
        started_at = time.time()
        log_buffer = io.StringIO()
        try:
            with contextlib.redirect_stdout(log_buffer):  # 검색기의 print를 화면 대신 log_buffer로 보냄
                result = retriever.run_workflow(
                    resources, item["question"], ROLE, member_of(item), run_args["top_k"], run_args["fusion"], False
                )
        except Exception as error:  # 외부 API가 끝내 실패한 경우 등
            result = {"status": "오류", "answer": f"{type(error).__name__}: {error}", "evidence": [], "queries": []}

        question_clean, answer_clean = clean_for_ragas(item["question"], result["answer"])
        row = core.make_result_row(item, result, question_clean, answer_clean)  # 실습 함수

        # 결과 파일과 이후 단계에 쓸 칸을 덧붙임
        row["version"] = version["name"]
        row["k"] = run_args["top_k"]
        row["log"] = log_buffer.getvalue()
        row["seconds"] = time.time() - started_at
        row["query_count"] = len(result.get("queries", []))
        rerank_ids = []  # 근거 0개 문항의 참고용: 리랭크 상위 청크ID
        for query in result.get("queries", []):
            for chunk_id in query["final_ids"]:
                rerank_ids.append(chunk_id)
        row["rerank_ids"] = rerank_ids
        rows.append(row)

        print(f"  {row['id']} {row['status']:<6} 근거 {len(row['chunk_ids'])}개 {row['chunk_ids']} {row['seconds']:.1f}초")
    restore_settings(resources, originals)
    return rows


def print_result_info(rows: list[dict]) -> None:
    """--until run: 결과 정보 4칸을 문항마다 보여 줌(교재 188쪽)."""
    for row in rows:
        print(f"  [{row['id']}] 종료 상태: {row['status']}")
        print(f"    user_input(질문)          : {row['user_input']}")
        print(f"    reference(모범 답안)      : {snippet(row['reference'])}")
        print(f"    retrieved_contexts(검색 결과): {len(row['retrieved_contexts'])}개")
        for rank, text in enumerate(row["retrieved_contexts"], start=1):
            print(f"      {rank}위 {row['chunk_ids'][rank - 1]:<10} {snippet(text)}")
        print(f"    response(답변)            : {snippet(row['response'])}")


# ---------------------------------------------------------------------------
# ③ 코드 평가
# ---------------------------------------------------------------------------
def evaluate_code(rows: list[dict], relevant_counts: dict) -> None:
    """③ 문항마다 적중 판정과 코드 평가 4지표를 계산해 행에 담고 화면에 찍음.

    부수효과: 행마다 hits, relevant_count, code(4지표), confirm_ok(답 없는 문항만) 칸을 채움.
    """
    for row in rows:
        k = row["k"]
        top_texts = row["retrieved_contexts"][:k]  # 상위 k개만 봄
        hits = core.find_hits(top_texts, row["relevance"])  # 실습 함수
        code = core.retrieval_metrics(hits, k)  # 실습 함수: hit, recall, mrr
        code["ndcg"] = core.ndcg_at_k(hits["hit_ranks"], relevant_counts[row["id"]], k)  # 실습 함수
        row["hits"] = hits
        row["relevant_count"] = relevant_counts[row["id"]]
        row["code"] = code
        row["confirm_ok"] = None
        if not row["answerable"]:
            row["confirm_ok"] = is_confirm_needed_answer(row["status"], row["answer"])

        if not row["answerable"]:
            verdict = "맞음" if row["confirm_ok"] else "틀림"
            print(f"  {row['id']} 답 없음 → 코드 지표 계산 안 함 | 「확인 필요」 판정 {verdict}({row['status']})")
            continue
        marks = []  # 순위별 담긴 정답 근거(예: 1위 ③, 2위 -)
        for rank, numbers in enumerate(hits["evidence_by_rank"], start=1):
            if len(numbers) == 0:
                marks.append(f"{rank}위 -")
            else:
                marks.append(f"{rank}위 " + ",".join(str(number) for number in numbers))
        found = f"{len(hits['found_evidence'])}/{hits['evidence_count']}"
        rank_text = " ".join(marks) if marks else "근거 0개"
        print(f"  {row['id']} 관련 청크 {row['relevant_count']}개, 정답 근거 {found} | {rank_text}")
        print(f"      Hit {fmt(code['hit'])}  Recall {fmt(code['recall'])}  MRR {fmt(code['mrr'])}  "
              f"nDCG {fmt(code['ndcg'])}")


# ---------------------------------------------------------------------------
# ④ LLM 평가(RAGAS)
# ---------------------------------------------------------------------------
def build_judge(secrets: dict):
    """평가자 LLM(Groq Qwen)과 임베딩(Cohere)을 만듦(교재 201쪽).

    방법: 둘 다 OpenAI 호환 주소라 openai 패키지의 AsyncOpenAI 클라이언트로 부름. llm_factory는 ragas 0.4 방식이고
          LangChain 래퍼(LangchainLLMWrapper)는 0.4에서 deprecated라 쓰지 않음(교재 201쪽).
    """
    judge_client = AsyncOpenAI(
        api_key=secrets["GROQ_API_KEY"],
        base_url=GROQ_BASE_URL,
        timeout=JUDGE_TIMEOUT_SECONDS,
        max_retries=JUDGE_MAX_RETRIES,
    )
    llm = llm_factory(JUDGE_MODEL, client=judge_client, max_tokens=JUDGE_MAX_TOKENS)
    embedding_client = AsyncOpenAI(api_key=secrets["COHERE_API_KEY"], base_url=COHERE_COMPAT_URL)
    embeddings = OpenAIEmbeddings(client=embedding_client, model=EMBEDDING_MODEL)
    return llm, embeddings


def can_score_with_llm(row: dict) -> tuple[bool, str]:
    """이 행을 LLM 평가로 채점할지 정함. 채점하지 않으면 그 이유를 함께 돌려줌(계획서 4.3)."""
    if not row["answerable"]:
        return False, "답 없는 문항"
    if row["status"] == "오류":
        return False, "검색기 오류"
    if len(row["retrieved_contexts"]) == 0:  # 근거 부족, 되묻기, 잡담: 빈 검색 결과는 ragas가 예외를 냄
        return False, "근거 0개"
    return True, ""


async def run_llm_evaluation(rows: list[dict], metrics: dict, experiment_name: str) -> dict:
    """④ 채점할 행을 ragas Dataset에 담고 @experiment 실험 함수를 arun으로 돌려 {문항: 점수 dict}를 돌려줌.

    방법: 교재 178쪽과 같은 모양(204쪽이 이 코드). 한 행 = 한 문항, 실험 함수가 행마다 score_row(지표 5개)를 부르고 arun이 표로 모음.
          arun은 모든 행을 한꺼번에 돌리므로 세마포어(동시에 들어갈 수 있는 수를 세는 문지기)로 동시 채점 수를 제한함.
    """
    dataset = Dataset(name=experiment_name.replace("/", "_"), backend="inmemory")  # 메모리에만 담음(파일 안 만듦)
    for row in rows:
        dataset.append({
            "id": row["id"],
            "user_input": row["user_input"],
            "reference": row["reference"],
            "retrieved_contexts": row["retrieved_contexts"],
            "response": row["response"],
        })

    semaphore = asyncio.Semaphore(MAX_CONCURRENT_ROWS)

    @experiment()
    async def ragas_eval(row):
        # 한 행(문항)을 지표 5개로 채점해 점수 행을 돌려줌. arun이 행마다 이 함수를 부름
        async with semaphore:  # 자리가 날 때까지 기다렸다가 들어감
            scores = await core.score_row(row, metrics)  # 실습 함수
        return {"id": row["id"], **scores}

    experiment_result = await ragas_eval.arun(dataset, name=experiment_name)
    scores_by_id = {}
    for record in experiment_result:  # 실패한 행은 arun이 경고만 남기고 빼므로 여기 없음
        scores_by_id[record["id"]] = record
    return scores_by_id


async def evaluate_llm(rows: list[dict], metrics: dict, experiment_name: str, repeat: int) -> dict:
    """④ 한 버전의 행들을 LLM 평가로 채점해 행에 담음. repeat가 2 이상이면 지표별 흔들림 폭(실측)을 돌려줌.

    방법: repeat번 채점해 문항별 점수는 평균을 쓰고, 지표마다 「회차 평균의 최댓값 - 최솟값」을 흔들림 폭으로 봄.
    부수효과: 행마다 llm(지표 5개 점수 또는 None), llm_note(채점 안 함 이유), llm_errors 칸을 채움.
    """
    targets = []
    for row in rows:
        allowed, note = can_score_with_llm(row)
        row["llm"] = None
        row["llm_note"] = note
        row["llm_errors"] = {}
        if allowed:
            targets.append(row)
    if len(targets) == 0:
        print("  채점할 행 없음(모두 답 없음 또는 근거 0개)")
        return {}

    runs = []  # 회차마다 {문항: 점수 dict}
    for run_number in range(1, repeat + 1):
        started_at = time.time()
        scores_by_id = await run_llm_evaluation(targets, metrics, f"{experiment_name}/{run_number}")
        runs.append(scores_by_id)
        print(f"  채점 {run_number}/{repeat}회: {len(scores_by_id)}/{len(targets)}행, {time.time() - started_at:.1f}초")

    for row in targets:
        averaged = {}
        for metric in core.LLM_METRICS:
            values = []
            for scores_by_id in runs:
                if row["id"] in scores_by_id:
                    values.append(scores_by_id[row["id"]][metric])
            if len(values) == 0:
                averaged[metric] = float("nan")  # 모든 회차에서 행 채점이 실패함
            else:
                mean = core.mean_of(values)
                averaged[metric] = float("nan") if mean is None else mean
        row["llm"] = averaged
        for scores_by_id in runs:
            if row["id"] in scores_by_id:
                row["llm_errors"].update(scores_by_id[row["id"]]["errors"])
            else:
                row["llm_errors"]["행 전체"] = "arun에서 행 채점 실패(경고 참고)"
        parts = []
        for metric in core.LLM_METRICS:
            parts.append(f"{METRIC_LABELS[metric].split()[1]} {fmt(averaged[metric])}")
        print(f"  {row['id']} " + "  ".join(parts))
        for metric_name, message in row["llm_errors"].items():
            print(f"      채점 실패 {metric_name}: {message}")

    widths = {}
    if repeat >= 2:
        for metric in core.LLM_METRICS:
            run_means = []
            for scores_by_id in runs:
                values = []
                for record in scores_by_id.values():
                    values.append(record[metric])
                run_mean = core.mean_of(values)
                if run_mean is not None:
                    run_means.append(run_mean)
            if len(run_means) >= 2:
                widths[metric] = max(run_means) - min(run_means)
        print("  흔들림 폭(실측, 회차 평균의 최대 - 최소): "
              + ", ".join(f"{METRIC_LABELS[m].split()[1]} {widths[m]:.3f}" for m in widths))
    return widths


async def evaluate_all_versions(versions: list[dict], rows_by_version: dict, metrics: dict, repeat: int) -> dict:
    """④ 모든 버전을 차례로 LLM 평가함. 기준선만 repeat번 반복해 흔들림 폭(실측)을 돌려줌."""
    widths = {}
    for version in versions:
        version_repeat = 1
        if version["is_baseline"]:
            version_repeat = max(1, repeat)  # 흔들림 폭은 기준선만 반복해서 잼
        title = f"[④ LLM 평가] {version['name']} {version['param']}={version['value']}"
        if version_repeat > 1:
            title = title + f" — 기준선 {version_repeat}회 반복"
        print_step(title)
        experiment_name = f"{version['param']}/{version['name']}"
        version_widths = await evaluate_llm(rows_by_version[version["name"]], metrics, experiment_name, version_repeat)
        if len(version_widths) > 0:
            widths = version_widths
    return widths


# ---------------------------------------------------------------------------
# ⑤ 버전 비교
# ---------------------------------------------------------------------------
def question_scores(row: dict) -> dict:
    """한 행의 지표 9개 점수를 한 dict로 모음. 채점하지 않은 칸은 None."""
    scores = {}
    for metric in core.CODE_METRICS:
        scores[metric] = row["code"][metric]
    for metric in core.LLM_METRICS:
        if row.get("llm") is None:
            scores[metric] = None
        else:
            scores[metric] = row["llm"][metric]
    return scores


def print_comparison(versions: list[dict], summary: dict, metric_names: list[str]) -> None:
    """⑤ 버전별 평균과 기준선 대비 변화를 표로 찍음."""
    header = f"  {'버전':<22}"
    for metric in metric_names:
        header = header + f"{METRIC_LABELS[metric].split()[1]:>22}"
    print(header)
    for version in versions:
        label = f"{version['name']} {version['param']}={version['value']}" + (" ★" if version["is_baseline"] else "")
        line = f"  {label:<22}"
        version_summary = summary[version["name"]]
        for metric in metric_names:
            mean = fmt(version_summary["mean"][metric])
            change = core.format_delta(version_summary["delta"][metric], version_summary["change"][metric])
            line = line + f"{mean + ' (' + change + ')':>22}"
        print(line)


# ---------------------------------------------------------------------------
# 결과 파일 쓰기
# ---------------------------------------------------------------------------
def md_cell(text: str) -> str:
    """마크다운 표 칸 안에 넣을 수 있게 줄바꿈과 세로줄을 바꿈."""
    return " ".join(str(text).split()).replace("|", "/")


def comparison_table_md(versions: list[dict], summary: dict, metric_names: list[str]) -> list[str]:
    """버전 비교표를 마크다운 줄 목록으로 만듦(모든 버전 파일에 같은 표를 넣음)."""
    lines = []
    header = "| 버전 |"
    divider = "|---|"
    for metric in metric_names:
        header = header + f" {METRIC_LABELS[metric]} |"
        divider = divider + "---|"
    lines.append(header)
    lines.append(divider)
    for version in versions:
        label = f"{version['name']} {version['param']}={version['value']}" + (" ★" if version["is_baseline"] else "")
        line = f"| {label} |"
        version_summary = summary[version["name"]]
        for metric in metric_names:
            change = core.format_delta(version_summary["delta"][metric], version_summary["change"][metric])
            line = line + f" {fmt(version_summary['mean'][metric])} ({change}) |"
        lines.append(line)
    return lines


def write_result_files(context: dict) -> list[Path]:
    """버전마다 결과 마크다운 파일을 씀(계획서 6장). 쓴 파일 경로 목록을 돌려줌."""
    versions = context["versions"]
    summary = context["summary"]
    metric_names = context["metric_names"]
    param = versions[0]["param"]
    out_dir = RESULTS_DIR / param
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []

    for version in versions:
        rows = context["rows_by_version"][version["name"]]
        version_summary = summary[version["name"]]
        star = " ★기준선" if version["is_baseline"] else ""
        lines = []
        lines.append(f"# {param} 평가 — {version['name']} {param}={version['value']}{star}")
        lines.append("")
        lines.append("## 읽는 순서")
        lines.append("")
        lines.append("1. 요약에서 기준선 대비 ▲(좋아짐), ▼(나빠짐)를 봄  ")
        lines.append("2. 원인 후보에서 고칠 곳을 고름  ")
        lines.append("3. 0점이거나 「채점 안 함」인 문항은 문항별 상세에서 검색 결과와 답변을 확인함")
        lines.append("")
        lines.append("범례: ▲ 기준선보다 흔들림 폭 넘게 오름, ▼ 내림, 변화 없음 = 흔들림 폭 안, - = 기준선 자신 또는 계산 안 함,  ")
        lines.append("실패 = 평가자 채점 실패, 채점 안 함 = 답 없는 문항이거나 근거 0개")
        lines.append("")
        lines.append("## 실행 정보")
        lines.append("")
        lines.append("| 항목 | 값 |")
        lines.append("|---|---|")
        lines.append(f"| 실행 시각 | {context['started']} |")
        lines.append(f"| 하이퍼 파라미터 | {param} = {version['value']}{star} |")
        lines.append(f"| 고정한 나머지 설정 | {md_cell(context['fixed_settings'])} |")
        lines.append(f"| 평가셋 | {EVAL_SET_PATH.name} {len(rows)}문항(답 있음 {context['answerable_count']}) |")
        lines.append(f"| 검색기 | rag/retriever core_search(강사 코드), 역할 {ROLE} |")
        lines.append(f"| 평가자 LLM, 임베딩 | Groq {JUDGE_MODEL}, Cohere {EMBEDDING_MODEL} |")
        lines.append(f"| 흔들림 폭 | {md_cell(context['noise_text'])} |")
        lines.append(f"| 실행 옵션 | {md_cell(context['command'])} |")
        lines.append("")
        lines.append("## 요약")
        lines.append("")
        lines.append("| 지표 | 평균 | 기준선 대비 |")
        lines.append("|---|---|---|")
        for metric in metric_names:
            change = core.format_delta(version_summary["delta"][metric], version_summary["change"][metric])
            lines.append(f"| {METRIC_LABELS[metric]} | {fmt(version_summary['mean'][metric])} | {change} |")
        confirm_total = 0
        confirm_ok = 0
        for row in rows:
            if not row["answerable"]:
                confirm_total = confirm_total + 1
                if row["confirm_ok"]:
                    confirm_ok = confirm_ok + 1
        lines.append("")
        lines.append(f"- 답 없는 문항 「확인 필요」 판정: {confirm_ok}/{confirm_total} 맞음  ")
        lines.append(f"- 최소 식별 변화: 답 있는 문항 대부분이 정답 근거 1개라 한 문항이 바뀌면 Recall 평균이 약 "
                     f"{MIN_DETECTABLE} 움직임. 통계적 유의성은 주장하지 않음  ")
        lines.append("- 평균은 매크로 평균(문항 점수의 평균). 「-」와 「실패」 칸은 평균에서 뺌")
        lines.append("")
        lines.append("## 버전 비교표")
        lines.append("")
        lines.extend(comparison_table_md(versions, summary, metric_names))
        lines.append("")
        lines.append("## 원인 후보(교재 187쪽)")
        lines.append("")
        if version["is_baseline"]:
            lines.append("- 기준선")
        else:
            for reason in context["diagnoses"][version["name"]]:
                lines.append(f"- {reason}")
        if param == "top_k":
            lines.append("- 참고: k가 커지면 Hit와 Recall은 기계적으로 오르므로 ContextPrecision과 짝지어 읽음")
        lines.append("")
        lines.append("## 문항별 검색 표")
        lines.append("")
        lines.append("| 문항 | 종료 상태 | 관련 청크 | 적중 순위 | 찾은 정답 근거 | 하 Hit | 빠 Recall | 빨 MRR | 앞 nDCG "
                     "| 위 Precision | 정 Recall |")
        lines.append("|---|---|---|---|---|---|---|---|---|---|---|")
        for row in rows:
            scores = question_scores(row)
            hits = row["hits"]
            found = f"{len(hits['found_evidence'])}/{hits['evidence_count']}" if row["answerable"] else "-"
            ranks = ",".join(str(rank) for rank in hits["hit_ranks"]) if hits["hit_ranks"] else "-"
            lines.append(
                f"| {row['id']} | {row['status']} | {row['relevant_count']} | {ranks} | {found} | "
                f"{fmt(scores['hit'])} | {fmt(scores['recall'])} | {fmt(scores['mrr'])} | {fmt(scores['ndcg'])} | "
                f"{fmt(scores['context_precision'])} | {fmt(scores['context_recall'])} |"
            )
        lines.append("")
        lines.append("## 문항별 답변 표")
        lines.append("")
        lines.append("| 문항 | 종료 상태 | 출 Faithfulness | 관 AnswerRelevancy | 답 FactualCorrectness | 「확인 필요」 판정 | 비고 |")
        lines.append("|---|---|---|---|---|---|---|")
        for row in rows:
            scores = question_scores(row)
            confirm = "-"
            if row["confirm_ok"] is not None:
                confirm = "맞음" if row["confirm_ok"] else "틀림"
            note = row.get("llm_note", "LLM 평가 실행 안 함")
            if note:
                note = f"채점 안 함: {note}"
            if row.get("llm_errors"):
                note = (note + " " if note else "") + "채점 실패: " + ", ".join(row["llm_errors"].keys())
            lines.append(
                f"| {row['id']} | {row['status']} | {fmt(scores['faithfulness'])} | "
                f"{fmt(scores['answer_relevancy'])} | {fmt(scores['factual_correctness'])} | {confirm} | "
                f"{md_cell(note)} |"
            )
        lines.append("")
        lines.append("## 문항별 상세")
        for row in rows:
            lines.append("")
            lines.append(f"### {row['id']} — {row['status']}(질의 {row['query_count']}개, {row['seconds']:.1f}초)")
            lines.append("")
            lines.append(f"- 원 질문: {md_cell(row['question'])}  ")
            lines.append(f"- ragas에 넘긴 질문: {md_cell(row['user_input'])}  ")
            lines.append(f"- 모범 답안: {md_cell(row['reference'])}  ")
            lines.append(f"- 원 답변: {md_cell(row['answer'])}  ")
            lines.append(f"- ragas에 넘긴 답변: {md_cell(row['response'])}")
            lines.append("")
            if len(row["chunk_ids"]) == 0:
                lines.append(f"검색 결과 0개. 참고: 리랭크 상위 청크ID {row['rerank_ids'] if row['rerank_ids'] else '없음'}")
            else:
                lines.append("| 순위 | 청크ID | 담긴 정답 근거 | 본문 앞부분 |")
                lines.append("|---|---|---|---|")
                for rank, chunk_id in enumerate(row["chunk_ids"], start=1):
                    numbers = []
                    if rank <= len(row["hits"]["evidence_by_rank"]):
                        numbers = row["hits"]["evidence_by_rank"][rank - 1]
                    mark = ",".join(str(number) for number in numbers) if numbers else "-"
                    body = md_cell(snippet(row["retrieved_contexts"][rank - 1]))
                    lines.append(f"| {rank} | {chunk_id} | {mark} | {body} |")
            for metric_name, message in row.get("llm_errors", {}).items():
                lines.append(f"- 채점 실패 {metric_name}: {md_cell(message)}")
            lines.append("")
            lines.append("<details><summary>검색기 실행 기록</summary>")
            lines.append("")
            lines.append("```text")
            lines.append(row["log"].rstrip())
            lines.append("```")
            lines.append("")
            lines.append("</details>")

        path = out_dir / f"evaluate_{context['stamp']}_{version['name']}.md"
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        written.append(path)
    return written


# ---------------------------------------------------------------------------
# --selftest: API 없이 실습 함수 점검(교재 181쪽 가상 예)
# ---------------------------------------------------------------------------
def check(label: str, actual, expected, tolerance: float = 0.005) -> bool:
    """값 하나를 기대값과 비교해 맞음/틀림을 찍음. 실수는 tolerance 안이면 맞음."""
    if isinstance(expected, float):
        ok = actual is not None and abs(actual - expected) <= tolerance
    else:
        ok = actual == expected
    print(f"  {'맞음' if ok else '틀림'}  {label}: 내 값 {actual}, 기대값 {expected}")
    return ok


def run_selftest() -> None:
    """교재 181쪽 가상 예와 작은 비교 예로 실습 함수를 API 없이 점검함."""
    print_step("[자체 점검] 교재 181쪽 예: 관련 청크 4개, 정답 근거 3개(①②③), 상위 k = 5")
    relevance = [
        {"clues": ["정산 기한: 복귀 후 7일 이내"]},  # ①
        {"clues": ["증빙 서류: 영수증 원본 첨부"]},  # ②
        {"clues": ["승인 절차: 팀장 결재 후 재무팀 확인"]},  # ③(7위라 상위 5 밖)
    ]
    chunk_texts = [
        "출장 신청 방법 안내",
        "출장비 정산 규정. 정산 기한: 복귀 후\n7일 이내. 증빙 서류: 영수증 원본 첨부",  # 2위: ①② (줄바꿈이 있어도 찾아야 함)
        "해외 출장 수당표",
        "정산 자주 묻는 질문. 정산 기한: 복귀 후 7일 이내",  # 4위: ① 한 번 더(한 번만 셈)
        "법인카드 사용 안내",
    ]
    results = []
    hits = core.find_hits(chunk_texts, relevance)
    results.append(check("적중 순위", hits["hit_ranks"], [2, 4]))
    metrics = core.retrieval_metrics(hits, 5)
    results.append(check("하 Hit@5", metrics["hit"], 1))
    results.append(check("빠 Recall@5", metrics["recall"], 2 / 3))
    results.append(check("빨 MRR", metrics["mrr"], 0.5))
    results.append(check("앞 nDCG@5", core.ndcg_at_k(hits["hit_ranks"], 4, 5), 0.4144))
    results.append(check("답 없는 문항 Recall", core.retrieval_metrics(core.find_hits(chunk_texts, []), 5)["recall"], None))

    print_step("[자체 점검] 버전 만들기, 버전 비교, 원인 찾기")
    versions = core.build_versions("top_k", [3, 5, 10], 5, SUPPORTED)
    names = []
    for version in versions:
        names.append(f"{version['name']}={version['value']}{'★' if version['is_baseline'] else ''}")
    results.append(check("버전 목록", names, ["v01=3", "v02=5★", "v03=10"]))
    rows_by_version = {
        "v01": [{"recall": 0.5, "context_recall": 0.6}, {"recall": 0.5, "context_recall": None}],
        "v02": [{"recall": 1.0, "context_recall": 0.9}, {"recall": 1.0, "context_recall": 0.8}],
    }
    noise = {"recall": 0.03, "context_recall": 0.03}
    summary = core.summarize_versions(rows_by_version, ["recall", "context_recall"], "v02", noise)
    results.append(check("v01 Recall 평균", summary["v01"]["mean"]["recall"], 0.5))
    results.append(check("v01 ContextRecall 평균(None 뺌)", summary["v01"]["mean"]["context_recall"], 0.6))
    results.append(check("v01 Recall 변화", summary["v01"]["change"]["recall"], "▼"))
    results.append(check("기준선 변화", summary["v02"]["change"]["recall"], "-"))
    reasons = core.diagnose(summary["v01"]["change"])
    results.append(check("원인 후보 수", len(reasons), 2))

    correct = 0
    for ok in results:
        if ok:
            correct = correct + 1
    print_step(f"[자체 점검 끝] 맞음 {correct}/{len(results)}")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def parse_args() -> argparse.Namespace:
    """명령행 옵션을 읽음."""
    parser = argparse.ArgumentParser(description="RAG 검색기를 하이퍼 파라미터 버전마다 코드 평가 4지표 + RAGAS 5지표로 채점함")
    parser.add_argument("--param", choices=list(SUPPORTED.keys()), help="실험할 하이퍼 파라미터 이름")
    parser.add_argument("--values", nargs="+", help="값 범위(띄어 써서 여러 개. 예: 3 5 10)")
    parser.add_argument("--baseline", default=None, help="기준선 값(생략하면 검색기의 현재 값)")
    parser.add_argument("--until", choices=["versions", "run", "code", "all"], default="all",
                        help="어느 단계까지 실행할지(versions ①, run ②, code ③과 ⑤, all 전부. 기본 all)")
    parser.add_argument("--qid", nargs="+", default=None, help="일부 문항만(예: Q01 Q17 Q20)")
    parser.add_argument("--repeat", type=int, default=1, help="기준선 LLM 평가를 N번 반복해 흔들림 폭을 실측(기본 1)")
    parser.add_argument("--mine", action="store_true", help="평가 실습 함수를 교육생 코드(my_eval.py)로 실행")
    parser.add_argument("--selftest", action="store_true", help="API 없이 실습 함수만 점검(교재 181쪽 예)")
    return parser.parse_args()


def main() -> None:
    """명령행대로 ① ~ ⑤를 실행하고 결과 파일을 씀."""
    args = parse_args()
    print(f"[실습 함수] {core.__name__}  [검색기] core_search(강사 코드)")
    if args.selftest:
        run_selftest()
        return
    if args.param is None or args.values is None:
        print("  오류: --param과 --values가 필요함. 예: python evaluate_rag.py --param top_k --values 3 5 10")
        sys.exit(1)

    started = datetime.now()
    command = "python evaluate_rag.py " + " ".join(sys.argv[1:])

    # ① 버전 만들기
    print_step("[① 버전 만들기] 하이퍼 파라미터 하나만 바꾸고 나머지는 기준선 값으로 고정함(교재 177쪽)")
    values = []
    for raw in args.values:
        values.append(parse_value(args.param, raw))
    baseline = None
    if args.baseline is not None:
        baseline = parse_value(args.param, args.baseline)
    try:
        versions = core.build_versions(args.param, values, baseline, SUPPORTED)  # 실습 함수
    except ValueError as error:
        print(f"  오류: {error}")
        sys.exit(1)
    baseline_name = None
    for version in versions:
        star = " ★기준선" if version["is_baseline"] else ""
        print(f"  {version['name']}  {version['param']} = {version['value']}{star}")
        if version["is_baseline"]:
            baseline_name = version["name"]
    if args.until == "versions":
        return

    # 준비: 평가셋, 색인, 시작 검사
    print_step("[준비] 평가셋 읽기, 색인 열기, 정답 단서 검사")
    items = load_eval_items(args.qid)
    answerable_count = 0
    for item in items:
        if item["answerable"]:
            answerable_count = answerable_count + 1
    print(f"  평가셋 {EVAL_SET_PATH.name}: {len(items)}문항(답 있음 {answerable_count}, 답 없음 {len(items) - answerable_count})")
    resources = retriever.load_resources()  # 검색기가 비밀값과 색인 파일을 검사한 뒤 색인을 엶
    retriever_secrets = check_judge_secrets()  # llm_model 버전에서 LLM을 다시 만들 때 씀(검색기와 같은 키)
    relevant_counts = count_relevant_by_question(resources, items)
    print("  정답 단서 검사: 모든 정답 단서가 색인 청크에 있음")
    originals = remember_settings(resources)
    fixed = []
    for name, current in SUPPORTED.items():
        if name != args.param:
            fixed.append(f"{name}={current}")
    fixed_settings = ", ".join(fixed)

    # ② 검색기 실행 → 결과 정보
    rows_by_version = {}
    for version in versions:
        print_step(f"[② 검색기 실행] {version['name']} {version['param']}={version['value']} — 문항마다 run_workflow")
        rows_by_version[version["name"]] = run_retriever(resources, items, version, originals, retriever_secrets)
    calls = resources["calls"]
    print(f"  검색기 호출 합계: LLM {calls['llm']}회, 임베딩 {calls['embed']}회, 리랭크 {calls['rerank']}회")
    if args.until == "run":
        for version in versions:
            print_step(f"[② 결과 정보 4칸] {version['name']} {version['param']}={version['value']}(교재 188쪽)")
            print_result_info(rows_by_version[version["name"]])
        return

    # ③ 코드 평가
    for version in versions:
        print_step(f"[③ 코드 평가] {version['name']} {version['param']}={version['value']} — 적중 청크와 4지표(교재 180쪽)")
        evaluate_code(rows_by_version[version["name"]], relevant_counts)

    # ④ LLM 평가(RAGAS)
    noise = {}
    for metric in ALL_METRICS:
        noise[metric] = NOISE
    noise_text = f"모든 지표 {NOISE}(교재 177쪽 예시값)"
    metric_names = core.CODE_METRICS
    if args.until == "all":
        metric_names = ALL_METRICS
        llm, embeddings = build_judge(check_judge_secrets())
        metrics = core.build_metrics(llm, embeddings)  # 실습 함수
        print_step(f"[④ LLM 평가] 평가자 Groq {JUDGE_MODEL}, 임베딩 Cohere {EMBEDDING_MODEL}, 지표 {list(metrics.keys())}")
        # 버전 전체를 이벤트 루프 하나에서 채점함. 루프를 여러 번 만들면 같은 API 클라이언트가 닫힌 루프를 쓰다 오류가 남
        widths = asyncio.run(evaluate_all_versions(versions, rows_by_version, metrics, args.repeat))
        if len(widths) > 0:
            parts = []
            for metric, width in widths.items():
                noise[metric] = max(width, 0.01)  # 실측 폭이 0이어도 0.01 미만 차이는 변화로 보지 않음
                parts.append(f"{metric} {noise[metric]:.3f}")
            noise_text = f"LLM 지표는 기준선 {args.repeat}회 실측({', '.join(parts)}), 코드 지표는 {NOISE}"
    else:
        for version in versions:
            for row in rows_by_version[version["name"]]:
                row["llm"] = None
                row["llm_note"] = "LLM 평가 실행 안 함(--until code)"
                row["llm_errors"] = {}

    # ⑤ 버전 비교
    print_step("[⑤ 버전 비교] 버전별 평균(매크로 평균)과 기준선 대비 변화(교재 178, 187쪽)")
    scores_by_version = {}
    for version in versions:
        scores = []
        for row in rows_by_version[version["name"]]:
            scores.append(question_scores(row))
        scores_by_version[version["name"]] = scores
    summary = core.summarize_versions(scores_by_version, metric_names, baseline_name, noise)  # 실습 함수
    print_comparison(versions, summary, metric_names)
    diagnoses = {}
    for version in versions:
        if version["is_baseline"]:
            continue
        diagnoses[version["name"]] = core.diagnose(summary[version["name"]]["change"])  # 실습 함수
        print(f"  원인 후보 {version['name']}: " + " / ".join(diagnoses[version["name"]]))

    written = write_result_files({
        "versions": versions,
        "summary": summary,
        "metric_names": metric_names,
        "rows_by_version": rows_by_version,
        "diagnoses": diagnoses,
        "started": started.strftime("%Y-%m-%d %H:%M"),
        "stamp": started.strftime("%y%m%d%H%M"),
        "fixed_settings": fixed_settings,
        "answerable_count": answerable_count,
        "noise_text": noise_text,
        "command": command,
    })
    print_step("[결과 파일]")
    for path in written:
        print(f"  {path.relative_to(BASE_DIR)}")
    print(f"  걸린 시간 {(datetime.now() - started).total_seconds():.0f}초")


if __name__ == "__main__":
    main()
