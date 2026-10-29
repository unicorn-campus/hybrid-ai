"""RAG 인덱싱 예제 main: 원천 문서를 로드 → 정제 → 가명처리 → 청킹 → 임베딩 → 벡터DB 적재 → BM25 색인 순서로 처리함.

핵심 단계(정제, 청킹, 임베딩, 적재, BM25 색인)의 알맹이는 core_indexing.py의 함수가 맡고,
이 파일은 설정값, 로더, 단계별 출력과 점검을 맡음.
"""

import argparse
import json
import os
import re
import shutil
import sys
import time
from datetime import datetime
from importlib.metadata import version as package_version
from pathlib import Path

import cohere
import pymupdf
from dotenv import load_dotenv
from langchain_chroma import Chroma
from langchain_cohere import CohereEmbeddings
from langchain_core.documents import Document


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


if use_student_code("my_indexing"):
    import my_indexing as indexing  # 교육생 코드(--mine)
else:
    import core_indexing as indexing  # 강사 코드(기본)

sys.stdout.reconfigure(encoding="utf-8")  # Windows 콘솔에서 한글이 깨지지 않게 함

# ---------------------------------------------------------------------------
# 설정값(상수). 교육생이 값을 바꿔 보며 결과 차이를 볼 수 있도록 한곳에 모음
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent  # 이 파일이 있는 indexing 폴더
ROOT_DIR = BASE_DIR.parents[3]  # indexing → rag → solutions → hands-on → 저장소 루트
DOCS_DIR = ROOT_DIR / "docs"  # 원천 문서 폴더
DATA_DIR = BASE_DIR / "data"  # 전체 실행 결과 폴더(검색기가 읽음)
DATA_LIMIT_DIR = BASE_DIR / "data-limit"  # --limit 실행 결과 폴더. 전체 결과를 부분 결과로 덮어쓰지 않기 위해 분리함
CHROMA_DIR_NAME = "chroma"  # 결과 폴더 안의 Chroma 저장 폴더 이름(본문, 메타데이터, 벡터)
BM25_DIR_NAME = "bm25"  # 결과 폴더 안의 BM25 색인 폴더 이름(bm25s 점수표, chunk_ids.json, dictionary.json, aliases_review.json, manifest.json)
STALE_FILES = ["chunks.json"]  # 예전 버전이 만들던 파일. 남아 있으면 지움(검색기는 본문을 Chroma에서 읽음)
ALIASES_APPROVED_PATH = BASE_DIR / "aliases_approved.json"  # 사람 검수를 통과한 별칭(강사 제공). {정식명: [별칭, ...]}
SECRETS_PATH = ROOT_DIR / "secrets" / ".env"  # API 키가 든 파일. 키 값은 코드·주석·README에 절대 적지 않음
COHERE_API_KEY_NAME = "COHERE_API_KEY"  # secrets/.env 안의 변수 이름(검색기의 리랭커와 같은 키)

COLLECTION_NAME = "card_docs"  # Chroma collection 이름(검색기와 약속한 값)
EMBEDDING_MODEL = "embed-v5.0-fast"  # Cohere 임베딩 모델(API). 검색기도 같은 모델로 질문을 임베딩해야 함
EMBED_DIMENSION = 2048  # 벡터 길이. 단계 5 출력이 이 값인지 확인함
EMBED_BATCH_SIZE = 96  # Cohere 한 요청에 넣을 수 있는 최대 건수. 260청크면 호출 3회
CHUNK_SIZE = 800  # 청크 토큰 상한(Cohere 토크나이저 기준)
CHUNK_OVERLAP = 200  # 앞뒤 청크가 겹치는 토큰 수
CARD_HEADER_TOKEN_BUDGET = 40  # D2 청크 앞에 붙일 "[카드: ...]" 머리말 몫. 미리 빼 두어야 800을 넘지 않음
LOAD_BATCH_SIZE = 100  # Chroma에 한 번에 넣는 건수

# BM25 색인 설정(교재 130쪽 "우리 코드의 설정값"). 검색기는 저장된 색인을 그대로 읽으므로 여기만 바꾸면 됨
BM25_K1 = 1.5  # 한 청크 안에서 같은 단어가 반복될 때 점수가 더 오르는 정도
BM25_B = 0.75  # 긴 청크의 점수를 깎는 정도
# 단계 7 출력용. 교재 130쪽 예시 문장이 색인 단어가 되는 과정을 보여 줌
TRACE_SENTENCE = "한빛 가족돌봄 카드로 30,000원 이상 결제하면 KB-PAY 할인을 받습니다."
# 단계 7 자가 테스트. 네 가지 표기가 모두 같은 정식명 토큰으로 모이는지 확인함(교재 131쪽 "✓ 일치")
SELF_TEST_QUESTIONS = ["모아생활 연회비 안 내려면?", "모아생활카드 연회비", "한빛모아생활 연회비", "한빛 모아생활 카드 연회비"]
SELF_TEST_EXPECTED = "한빛모아생활"

# Chroma collection 설정. 거리 방식과 HNSW(근사 최근접 이웃 그래프) 값을 적음(교재 127 ~ 128쪽)
# 검색기가 같은 값으로 collection을 열므로 바꾸면 검색기 상수도 함께 바꿈
COLLECTION_METADATA = {
    "hnsw:space": "cosine",  # 코사인 거리. 검색기의 "1 - 거리" 점수 계산과 맞춤
    "hnsw:M": 16,  # 청크 하나당 최대 연결 수. 교재 128쪽 권장 값
    "hnsw:construction_ef": 200,  # 색인을 만들 때 후보 폭. 클수록 그래프 품질이 오르고 시간이 늘어남
    "hnsw:search_ef": 100,  # 검색할 때 후보 폭. top_k보다 크게 두어야 재현율이 안정됨
}

# 문서 유형별 설정. separators는 정규식이며 앞이 우선임
# "(?=...)"(전방탐색)은 그 글자 앞에서 자르되 글자는 지우지 않고 다음 청크 맨 앞에 남김. 예: "제3조("가 다음 청크 첫머리가 됨
# 문장 끝 구분자 "(?<=[.!?。])\s+"는 "마침표 뒤 공백"에서 자르고, 마지막 ""는 글자 단위로 자른다는 뜻임
DOC_SETTINGS = {
    "D1": {
        "file_pattern": "D1_*.pdf",
        "doc_type": "regulation",  # 약관
        "access_level": "public",
        "separators": [r"(?=제\s*\d+조(?:의\d+)?\s*\()", r"\n\n", r"\n", r"(?<=[.!?。])\s+", r" ", r""],
    },
    "D2": {
        "file_pattern": "D2_*.pdf",
        "doc_type": "benefit_guide",  # 카드 혜택 안내
        "access_level": "public",
        "separators": [r"(?=D2-C\d{3}(?:-B\d+)?)", r"\n\n", r"\n", r"(?<=[.!?。])\s+", r" ", r""],
    },
    "D3": {
        "file_pattern": "D3_S*.txt",
        "doc_type": "consult_log",  # 상담 이력
        "access_level": "restricted",  # 감사 권한만 봄
        "separators": [r"(?=(?:고객|상담사)\s*[:：])", r"\n\n", r"\n", r" ", r""],
    },
}

# D2 「카드 찾아보기」 표가 있는 쪽 범위(1부터). 원본문서의 3~6페이지에 카드 목록표가 있음. 
# 이 목록표를 이용하여 {카드ID: 카드명} 리스트를 만듦
D2_CARD_INDEX_FIRST_PAGE = 3
D2_CARD_INDEX_LAST_PAGE = 6
CARD_CODE_PATTERN = re.compile(r"D2-C\d{3}")  # 청크 본문에서 카드 코드를 찾는 정규식

# D3 상담 파일 구조
D3_RECORD_SEPARATOR = "========================================"  # 상담 건 사이의 구분 줄
D3_HEADER_PATTERN = re.compile(
    r"^\[상담ID\]\s*(?P<record_id>C-\d{8}-\d{3})\s*\|\s*(?P<consult_date>\d{4}-\d{2}-\d{2})"
    r"\s*\|\s*채널:\s*(?P<channel>[^|]+?)\s*\|\s*회원번호:\s*(?P<member_id>M-\d+)"
)
D3_DROP_LINE_PREFIXES = ("[접수정보]", "[본인확인]", "[기록정보]")  # 개인정보·기록 관리 줄. 본문에서 삭제

# 토큰 세기용 Cohere 클라이언트. 모듈을 읽는 시점에는 키가 없으므로 main이 키 검사 뒤에 만들어 넣음
cohere_client = None


# ---------------------------------------------------------------------------
# 화면 출력 도우미
# ---------------------------------------------------------------------------
def print_step(step_number: int, title: str) -> None:
    """단계 머리말을 통일된 꼴로 출력함."""
    print("=" * 60)
    print(f"[단계 {step_number}] {title}")


def print_lines(label: str, lines: list[str], max_lines: int) -> None:
    """앞 max_lines줄만 들여쓰기해서 보여 줌. 교육생이 처리 전후를 눈으로 비교하기 위한 용도임."""
    print(f"  {label}")
    for line in lines[:max_lines]:
        print(f"    | {line}")


# ---------------------------------------------------------------------------
# 실행 전 점검: 원천 폴더 확인, 지난 결과 삭제
# ---------------------------------------------------------------------------
def check_docs_dir() -> None:
    """원천 문서 폴더가 없으면 안내하고 종료함. 폴더 위치를 저장소 구조에서 계산하므로 폴더를 옮기면 못 찾음."""
    if DOCS_DIR.is_dir():
        return
    print(f"원천 문서 폴더가 없음: {DOCS_DIR}")
    print("저장소를 통째로 clone하고 indexing 폴더를 다른 곳으로 옮기지 말 것")
    sys.exit(1)


def check_secrets() -> None:
    """secrets/.env 파일과 그 안의 COHERE_API_KEY를 확인함. 없으면 경로와 변수 이름만 안내하고 종료함(값은 출력하지 않음)."""
    if not SECRETS_PATH.is_file():
        print(f"비밀값 파일이 없음: {SECRETS_PATH}")
        print(f"그 파일을 만들고 {COHERE_API_KEY_NAME}=발급받은키 한 줄을 적을 것")
        sys.exit(1)
    load_dotenv(SECRETS_PATH)  # 파일의 변수를 환경변수로 올림. CohereEmbeddings가 환경변수에서 키를 읽음
    if os.environ.get(COHERE_API_KEY_NAME, "") == "":
        print(f"{SECRETS_PATH} 안에 {COHERE_API_KEY_NAME} 가 없음")
        print(f"{COHERE_API_KEY_NAME}=발급받은키 한 줄을 추가할 것")
        sys.exit(1)


def remove_old_outputs(data_dir: Path) -> None:
    """지난 실행의 결과(Chroma 폴더, BM25 색인 폴더, 예전 버전 파일)를 지움. 실패하면 안내하고 종료함.

    목적: 실행마다 전체 재색인하므로 지난 청크가 섞이지 않게 함.
    방법: Chroma 폴더, BM25 색인 폴더, 예전 버전 파일을 지움.
          Windows는 검색기가 폴더를 열고 있으면 PermissionError로 삭제가 막히므로 안내 후 종료함.
    """
    try:
        for dir_name in [CHROMA_DIR_NAME, BM25_DIR_NAME]:
            if (data_dir / dir_name).exists():
                shutil.rmtree(data_dir / dir_name)
        for file_name in STALE_FILES:
            if (data_dir / file_name).exists():
                (data_dir / file_name).unlink()
    except PermissionError:
        print(f"지난 결과 폴더를 지울 수 없음: {data_dir}")
        print("검색 프로그램(search_docs.py, run_eval.py) 창을 모두 닫고 다시 실행할 것")
        sys.exit(1)


# ---------------------------------------------------------------------------
# 로더: 파일에서 텍스트를 꺼내는 함수
# ---------------------------------------------------------------------------
def load_pdf_pages(pdf_path: Path, limit: int | None) -> list[str]:
    """PDF를 쪽 단위 텍스트 목록으로 읽음. limit가 있으면 앞 limit쪽만 읽음."""
    page_texts = []
    with pymupdf.open(pdf_path) as pdf:
        for page in pdf:
            page_texts.append(page.get_text())
            if limit is not None and len(page_texts) >= limit:
                break
    return page_texts


def load_consult_records(txt_path: Path, limit: int | None) -> list[dict]:
    """상담 파일을 상담 건 단위로 나눠 읽음.

    방법: "====" 구분 줄로 블록을 나누고, "[상담ID] ... | 채널: ... | 회원번호: ..." 머리말 형식에 맞는 줄이 있는 블록만 상담 건으로 봄(파일 머리 설명은 버림).
    반환값: 상담 건마다 {"raw_lines": 원문 줄 목록, "header": 상담ID 줄에서 읽은 값 dict}인 목록임.
    예시: "[상담ID] C-20260314-001 | 2026-03-14 | 채널: 앱 채팅 | 회원번호: M-1001" 줄의 header는
          {"record_id": "C-20260314-001", "consult_date": "2026-03-14", "channel": "앱 채팅", "member_id": "M-1001"}
    """
    text = txt_path.read_text(encoding="utf-8")
    records = []
    for block in text.split(D3_RECORD_SEPARATOR):
        raw_lines = []
        for line in block.strip().splitlines():
            raw_lines.append(line.strip())

        header = None
        for line in raw_lines:
            match = D3_HEADER_PATTERN.match(line)
            if match is not None:
                header = match.groupdict()
                break
        if header is None:
            continue  # "[상담ID]" 줄이 없는 블록은 파일 설명이므로 건너뜀

        records.append({"raw_lines": raw_lines, "header": header})
        if limit is not None and len(records) >= limit:
            break
    return records


def build_consult_body(record: dict) -> str:
    """상담 건에서 개인정보 줄을 지우고 가명처리한 본문을 만듦.

    방법: [접수정보]·[본인확인]·[기록정보] 줄은 통째로 지움. [상담ID] 줄은 회원번호를 뗀 채 남겨
          상담ID·날짜·채널로도 BM25가 찾게 함. 그 뒤 발화 안의 개인정보를 mask_private_info로 바꿈.
    """
    header = record["header"]
    body_lines = []
    for line in record["raw_lines"]:
        if line.startswith(D3_DROP_LINE_PREFIXES):  # 튜플이면 그중 하나로 시작하는지 봄
            continue
        if line.startswith("[상담ID]"):
            body_lines.append(
                f"[상담ID] {header['record_id']} | {header['consult_date']} | 채널: {header['channel']}"
            )
            continue
        body_lines.append(line)
    body_text = "\n".join(body_lines)
    return indexing.clean_document(body_text, mask_private=True)  # 정제(가명처리)


def build_card_name_table(cleaned_pages: list[str]) -> dict:
    """D2 「카드 찾아보기」 표에서 {카드ID: 카드명} 표를 만듦.

    방법: 표가 있는 쪽에서 "D2-C001" 줄 바로 다음 줄("한빛 모아생활")을 카드명으로 읽음.
          PyMuPDF가 표를 한 칸 한 줄로 풀어 주기 때문에 이 규칙이 성립함.
    반환값: 카드 코드 → 카드명 dict. 표 쪽이 없으면(--limit로 앞쪽만 읽은 경우) 빈 dict임.
    """
    card_names = {}
    for page_number, page_text in enumerate(cleaned_pages, start=1):
        if page_number < D2_CARD_INDEX_FIRST_PAGE or page_number > D2_CARD_INDEX_LAST_PAGE:
            continue
        lines = page_text.splitlines()
        for index, line in enumerate(lines):
            if CARD_CODE_PATTERN.fullmatch(line) and index + 1 < len(lines):
                card_names[line] = lines[index + 1]
    return card_names


def count_tokens(text: str) -> int:
    """본문의 토큰 수를 Cohere 토크나이저로 셈. 분할기의 length_function으로 넘겨 청크 크기의 기준이 됨.

    방법: offline=True라 실행할 때마다 처음 한 번만 토크나이저 파일(tokenizer.json. 글자 조각을 토큰 번호로
          바꾸는 사전과 규칙)을 받아 메모리에 캐시하고, 이후에는 API 호출 없이 로컬에서 셈.
          청크 통계와 머리말 몫 계산에도 같은 함수를 써야 상한 검증 기준이 맞음.
    """
    if text == "":
        return 0  # 분할기가 빈 조각의 길이도 물어봄. 빈 글은 토크나이저에 보내지 않음

    # 입력 text를 토큰(자주 쓰는 글자 조각)으로 쪼개고, 조각마다 tokenizer.json 사전의 번호로 바꿈
    response = cohere_client.tokenize(text=text, model=EMBEDDING_MODEL, offline=True)

    # response.tokens는 글자 조각이 아니라 사전 번호 목록임. 개수만 필요하므로 길이를 셈
    return len(response.tokens)


def make_chunk_id(doc_id: str, sequence: int) -> str:
    """청크 ID를 "D1-0001" 꼴로 만듦. 4자리 순번이라 정렬했을 때 순서가 유지됨."""
    return f"{doc_id}-{sequence:04d}"


# ---------------------------------------------------------------------------
# 단계 1. 로드
# ---------------------------------------------------------------------------
def step_load(limit: int | None) -> tuple[dict, dict]:
    """원천 문서를 읽음. PDF는 쪽 단위, 상담 파일은 상담 건 단위로 꺼냄.

    반환값: (파일 경로 → 쪽 텍스트 목록, 파일 경로 → 상담 건 목록) 두 dict임.
    """
    print_step(1, "로드 — 원천 문서에서 텍스트를 꺼냄")
    pdf_pages_by_file = {}  # D1, D2
    consult_records_by_file = {}  # D3
    for doc_id, setting in DOC_SETTINGS.items():
        for file_path in sorted(DOCS_DIR.glob(setting["file_pattern"])):
            if file_path.suffix == ".pdf":
                page_texts = load_pdf_pages(file_path, limit)
                pdf_pages_by_file[file_path] = page_texts
                total_chars = 0
                for page_text in page_texts:
                    total_chars = total_chars + len(page_text)
                print(f"  {file_path.name}: {len(page_texts)}쪽, {total_chars:,}자")
            else:
                records = load_consult_records(file_path, limit)
                consult_records_by_file[file_path] = records
                total_chars = 0
                for record in records:
                    total_chars = total_chars + len("\n".join(record["raw_lines"]))
                print(f"  {file_path.name}: {len(records)}건, {total_chars:,}자")
    return pdf_pages_by_file, consult_records_by_file


# ---------------------------------------------------------------------------
# 단계 2. 정제(PDF)
# ---------------------------------------------------------------------------
def step_clean(pdf_pages_by_file: dict) -> tuple[dict, dict]:
    """PDF 쪽마다 머리말·꼬리말·쪽번호를 지우고 쪽 단위 Document를 만듦.

    반환값: (문서ID → 쪽 단위 Document 목록, D2 카드ID → 카드명 표)임.
    """
    print_step(2, "정제 — 머리말·꼬리말·쪽번호를 지움")
    page_documents = {"D1": [], "D2": []}
    card_names = {}
    for file_path, page_texts in pdf_pages_by_file.items():
        doc_id = file_path.name[:2]  # 파일명 앞 두 글자("D1", "D2")가 문서 ID임
        setting = DOC_SETTINGS[doc_id]
        repeated_lines = indexing.find_repeated_lines(page_texts, min_pages=2)
        print(f"  {file_path.name}: 반복 줄 {len(repeated_lines)}개 → {sorted(repeated_lines)}")

        cleaned_pages = []
        for page_number, page_text in enumerate(page_texts, start=1):
            cleaned_text = indexing.clean_document(page_text, repeated_lines)  # 정제(쪽)
            cleaned_pages.append(cleaned_text)
            if cleaned_text == "":
                continue  # 표지처럼 내용이 다 지워진 쪽은 청크를 만들지 않음
            metadata = {
                "source": file_path.name,
                "doc_type": setting["doc_type"],
                "access_level": setting["access_level"],
                "page": page_number,
            }
            page_documents[doc_id].append(Document(page_content=cleaned_text, metadata=metadata))

        if doc_id == "D1":
            print_lines("D1 첫 쪽 정제 전 5줄:", page_texts[0].splitlines(), 5)
            print_lines("D1 첫 쪽 정제 후 5줄:", cleaned_pages[0].splitlines(), 5)
        if doc_id == "D2":
            card_names = build_card_name_table(cleaned_pages)
            print(f"  D2 카드명 표: {len(card_names)}개 (예: {list(card_names.items())[:2]})")
    return page_documents, card_names


# ---------------------------------------------------------------------------
# 단계 3. 가명처리(D3)
# ---------------------------------------------------------------------------
def print_mask_sample(record: dict, body_text: str, pseudo_id: str) -> None:
    """상담 1건의 처리 전 3줄과 처리 후 3줄을 나란히 보여 줌."""
    header = record["header"]
    raw_lines = record["raw_lines"]
    # 줄 순서가 [상담ID], [기록정보], [접수정보], [본인확인], [상담주제], 첫 발화로 고정이라 고정 인덱스가 가능함
    before_lines = [raw_lines[0], raw_lines[2], raw_lines[5]]  # 상담ID 줄, 접수정보 줄, 첫 고객 발화
    body_lines = body_text.splitlines()
    after_lines = [body_lines[0], "(접수정보 줄 삭제됨)", body_lines[2]]  # 같은 자리의 처리 후 줄
    print_lines(f"{header['record_id']} 처리 전 3줄:", before_lines, 3)
    print_lines(f"{header['record_id']} 처리 후 3줄:", after_lines, 3)
    print(f"  회원번호 {header['member_id']} → member_pseudo_id {pseudo_id}")


def step_mask(consult_records_by_file: dict) -> list[Document]:
    """상담 건마다 개인정보 줄을 지우고 본문을 가명처리한 뒤 Document를 만듦. 회원번호는 가명 ID로 메타데이터에 둠."""
    print_step(3, "가명처리 — 상담 본문의 개인정보를 토큰으로 바꿈")
    setting = DOC_SETTINGS["D3"]
    consult_documents = []
    for file_path, records in consult_records_by_file.items():
        for record in records:
            header = record["header"]
            body_text = build_consult_body(record)
            metadata = {
                "source": file_path.name,
                "doc_type": setting["doc_type"],
                "access_level": setting["access_level"],
                "record_id": header["record_id"],
                "consult_date": header["consult_date"],
                "channel": header["channel"],
                "member_pseudo_id": indexing.member_pseudonym(header["member_id"]),
            }
            consult_documents.append(Document(page_content=body_text, metadata=metadata))
            if len(consult_documents) == 1:
                print_mask_sample(record, body_text, metadata["member_pseudo_id"])
    print(f"  상담 {len(consult_documents)}건 처리 완료")
    return consult_documents


# ---------------------------------------------------------------------------
# 단계 4. 청킹
# ---------------------------------------------------------------------------
def attach_card_header(text: str, metadata: dict, card_names: dict) -> str:
    """D2 청크 본문의 첫 카드 코드로 card_id·card_name 메타데이터를 넣고 "[카드: ...]" 머리말을 앞에 붙임.

    목적: 카드의 첫 청크를 뺀 나머지 청크 본문에는 카드명이 없어 카드명으로 검색이 안 됨(교재 "본문에 메타데이터 삽입").
    반환값: 머리말이 붙은 본문. 카드 코드가 없거나 표에 없는 코드면 원래 본문 그대로임.
    """
    
    # 본문에서 카드ID를 찾음   
    match = CARD_CODE_PATTERN.search(text)
    
    if match is None or match.group(0) not in card_names:
        return text
    
    card_id = match.group(0)
    
    # metadata에 카드ID와 카드명을 넣음
    metadata["card_id"] = card_id
    metadata["card_name"] = card_names[card_id]
    
    # 본문 앞에 "[카드: 카드명 (카드ID)]" 머리말을 붙임
    return f"[카드: {card_names[card_id]} ({card_id})]\n" + text


def print_chunk_stats(chunks: list[dict]) -> None:
    """문서 유형별 청크 수와 토큰 길이(최소·평균·최대), 상한 초과 개수를 보여 줌."""
    token_counts_by_doc_type = {}
    over_limit = 0
    for chunk in chunks:
        doc_type = chunk["metadata"]["doc_type"]
        token_count = count_tokens(chunk["text"])
        if doc_type not in token_counts_by_doc_type:
            token_counts_by_doc_type[doc_type] = []
        token_counts_by_doc_type[doc_type].append(token_count)
        if token_count > CHUNK_SIZE:
            over_limit = over_limit + 1
    for doc_type, token_counts in token_counts_by_doc_type.items():
        average = sum(token_counts) / len(token_counts)
        print(
            f"  {doc_type:<13}: {len(token_counts)}개 "
            f"(최소 {min(token_counts)} / 평균 {average:.0f} / 최대 {max(token_counts)} 토큰)"
        )
    print(f"  전체 {len(chunks)}개, {CHUNK_SIZE}토큰 초과 {over_limit}개")


def print_chunk_samples(chunks: list[dict]) -> None:
    """샘플 2개를 보여 줌: 카드 머리말이 붙은 D2 본문 청크(목차 쪽 제외)와 D3 청크. 없으면 첫 청크."""
    sample_chunks = []
    for chunk in chunks:
        is_card_chunk = chunk["chunk_id"].startswith("D2") and "card_id" in chunk["metadata"]
        if is_card_chunk and chunk["metadata"]["page"] > D2_CARD_INDEX_LAST_PAGE:
            sample_chunks.append(chunk)
            break
    for chunk in chunks:
        if chunk["chunk_id"].startswith("D3"):
            sample_chunks.append(chunk)
            break
    if len(sample_chunks) < 2 and len(chunks) > 0:
        sample_chunks.append(chunks[0])
    for chunk in sample_chunks:
        print(f"  샘플 {chunk['chunk_id']} | metadata={chunk['metadata']}")
        for line in chunk["text"][:120].splitlines():
            print(f"    {line}")


def step_chunk(page_documents: dict, consult_documents: list[Document], card_names: dict) -> list[dict]:
    """문서 유형별 구분자로 청크를 만들고 chunk_id를 붙임. 핵심 함수 chunk_document가 나누고 길이는 count_tokens로 셈.

    반환값: {"chunk_id", "text", "metadata"} dict의 목록. 적재(Chroma)와 BM25 색인이 같은 목록을 같은 순서로 씀.
    """
    print_step(4, f"청킹 — {CHUNK_SIZE}토큰, 중첩 {CHUNK_OVERLAP}토큰")
    documents_by_doc_id = {"D1": page_documents["D1"], "D2": page_documents["D2"], "D3": consult_documents}
    chunks = []
    for doc_id, documents in documents_by_doc_id.items():
        setting = DOC_SETTINGS[doc_id]
        chunk_size = CHUNK_SIZE
        if doc_id == "D2":
            chunk_size = CHUNK_SIZE - CARD_HEADER_TOKEN_BUDGET  # 머리말을 붙여도 800을 넘지 않게 미리 뺌

        sequence = 0
        for document in documents:
            pieces = indexing.chunk_document(
                document.page_content, document.metadata, setting["separators"], count_tokens, chunk_size, CHUNK_OVERLAP
            )
            for piece in pieces:
                text = piece.page_content
                metadata = piece.metadata
                
                # D2 카드 청크는 "[카드: ...]" 머리말을 붙이고 card_id·card_name 메타데이터를 넣음
                if doc_id == "D2":
                    text = attach_card_header(text, metadata, card_names)
                
                sequence = sequence + 1
                chunks.append({"chunk_id": make_chunk_id(doc_id, sequence), "text": text, "metadata": metadata})

    print_chunk_stats(chunks)
    print_chunk_samples(chunks)
    return chunks


# ---------------------------------------------------------------------------
# 단계 5. 임베딩
# ---------------------------------------------------------------------------
def step_embed(chunks: list[dict]) -> tuple[CohereEmbeddings, list[list[float]]]:
    """Cohere API로 모든 청크 본문을 벡터로 바꿈. 핵심 함수 embed_chunks가 96건씩 나눠 보냄.

    반환값: (임베딩 객체, 청크 순서와 같은 벡터 목록). 임베딩 객체는 적재 뒤 검색기 방식의 읽기 확인에 다시 씀.
    예외: 호출 한도 초과(429)나 그 밖의 API 오류면 안내를 출력하고 종료함.
    """
    print_step(5, f"임베딩 — Cohere {EMBEDDING_MODEL} (API)")
    # 키는 check_secrets가 올린 환경변수 COHERE_API_KEY에서 자동으로 읽음. 문서용 input_type도 자동으로 보냄
    embeddings = CohereEmbeddings(model=EMBEDDING_MODEL)

    texts = []
    for chunk in chunks:
        texts.append(chunk["text"])
    started_at = time.time()
    try:
        vectors, api_calls = indexing.embed_chunks(texts, embeddings, EMBED_BATCH_SIZE)  # 임베딩
    except cohere.TooManyRequestsError:
        print("  Cohere 호출 한도 초과(429). 잠시 뒤 다시 실행할 것")
        sys.exit(1)
    except cohere.ApiError as error:
        print(f"  Cohere 호출 실패(HTTP {error.status_code}). 키와 네트워크를 확인하고 잠시 뒤 다시 실행할 것")
        sys.exit(1)
    elapsed = time.time() - started_at
    print(f"  청크 {len(vectors)}개 임베딩 {elapsed:.1f}초, API 호출 {api_calls}회")

    first_values = []
    for value in vectors[0][:5]:
        first_values.append(round(value, 4))
    print(f"  차원 수: {len(vectors[0])} (기대값 {EMBED_DIMENSION}), 첫 청크 벡터 앞 5개: {first_values}")
    return embeddings, vectors


# ---------------------------------------------------------------------------
# 단계 6. 적재
# ---------------------------------------------------------------------------
def step_store(chunks: list[dict], vectors: list, embeddings: CohereEmbeddings, data_dir: Path) -> None:
    """본문, 메타데이터, 벡터를 Chroma에 넣음. 핵심 함수 store_chunks가 맡고, 여기서는 건수를 확인함.

    부수효과: data_dir 아래 chroma/ 를 만듦.
    """
    print_step(6, "적재 — Chroma 저장(본문, 메타데이터, 벡터)")
    chroma_dir = data_dir / CHROMA_DIR_NAME
    data_dir.mkdir(parents=True, exist_ok=True)

    stored_count = indexing.store_chunks(  # 적재
        chunks, vectors, chroma_dir, COLLECTION_NAME, COLLECTION_METADATA, LOAD_BATCH_SIZE
    )
    print(f"  Chroma 저장 건수: {stored_count} / 청크 {len(chunks)}개 (collection={COLLECTION_NAME}, {chroma_dir})")

    # 검색기가 쓰는 방식(langchain_chroma)으로 다시 열어 같은 건수가 읽히는지 확인함
    store = Chroma(
        collection_name=COLLECTION_NAME,
        embedding_function=embeddings,
        persist_directory=str(chroma_dir),
        collection_metadata=COLLECTION_METADATA,
    )
    stored_ids = store.get()["ids"]
    print(f"  langchain_chroma로 다시 읽은 건수: {len(stored_ids)}")


# ---------------------------------------------------------------------------
# 단계 7. BM25 색인
# ---------------------------------------------------------------------------
def collect_card_names(chunks: list[dict]) -> list[str]:
    """청크 메타데이터의 card_name 값을 중복 없이 모음. 사용자 사전과 별칭 사전의 정식명 목록이 됨."""
    names = set()
    for chunk in chunks:
        if "card_name" in chunk["metadata"]:
            names.add(chunk["metadata"]["card_name"])
    return sorted(names)


def load_approved_aliases() -> dict:
    """사람 검수를 통과한 별칭 파일(강사 제공)을 읽음. 없으면 빈 dict임."""
    if not ALIASES_APPROVED_PATH.is_file():
        return {}
    with open(ALIASES_APPROVED_PATH, "r", encoding="utf-8") as file:
        approved = json.load(file)
    result = {}
    for canonical, alias_list in approved.items():
        if not canonical.startswith("_"):  # "_설명" 같은 설명 키는 건너뜀
            result[canonical] = alias_list
    return result


def print_tokenize_trace(kiwi, alias_to_name: dict, sentence: str) -> None:
    """교재 130쪽 표처럼 한 문장이 색인 단어가 되는 과정을 단계별로 보여 줌."""
    normalized = indexing.NUMBER_COMMA_PATTERN.sub("", sentence).lower()
    kept = []
    dropped = []
    for token in kiwi.tokenize(normalized):
        if token.tag.split("-")[0] in indexing.CONTENT_TAGS:
            kept.append(token.form)
        else:
            dropped.append(f"{token.form}/{token.tag}")
    codes = indexing.CODE_PATTERN.findall(normalized)
    final_tokens = indexing.tokenize_korean(kiwi, sentence, alias_to_name)
    print(f"  원문        | {sentence}")
    print(f"  ① 표기 통일 | {normalized}")
    print(f"  ② 코드 추가 | {codes} (코드 꼴이 없으면 빈 목록. 목록 맨 앞에 들어감)")
    print(f"  ③ 남긴 단어 | {kept}")
    print(f"     버린 조각 | {dropped} (참고: 조사, 어미, 기호)")
    print(f"  ④ 별칭 치환 | {final_tokens}  → {len(final_tokens)}개 단어를 bm25s가 점수 계산")


def run_alias_self_test(kiwi, alias_to_name: dict) -> None:
    """네 가지 표기의 질문이 모두 같은 정식명 토큰으로 모이는지 확인함(교재 131쪽 "✓ 일치")."""
    all_passed = True
    for question in SELF_TEST_QUESTIONS:
        tokens = indexing.tokenize_korean(kiwi, question, alias_to_name)
        passed = SELF_TEST_EXPECTED in tokens
        all_passed = all_passed and passed
        print(f"  {'✓' if passed else '✗'} {question!r} → {tokens}")
    print(f"  자가 테스트 {'통과' if all_passed else '실패'}: 모든 질문에 {SELF_TEST_EXPECTED!r} 토큰이 {'있음' if all_passed else '없음'}")


def write_bm25_sidecars(index_dir: Path, card_names: list[str], aliases: dict, review: list[dict], chunk_count: int) -> None:
    """색인 폴더에 사전(dictionary.json), 검수 목록(aliases_review.json), 요약(manifest.json)을 씀.

    목적: 검색기가 색인과 "같은 사전"으로 질문을 토큰화하게 하고, 사람이 색인 내용을 검토할 수 있게 함.
    """
    with open(index_dir / "dictionary.json", "w", encoding="utf-8") as file:
        json.dump({"card_names": card_names, "aliases": aliases}, file, ensure_ascii=False, indent=2)
    with open(index_dir / "aliases_review.json", "w", encoding="utf-8") as file:
        json.dump(review, file, ensure_ascii=False, indent=2)
    manifest = {
        "chunk_count": chunk_count,
        "k1": BM25_K1,
        "b": BM25_B,
        "method": indexing.BM25_METHOD,
        "tokenizer_module": indexing.__name__,  # 검색기가 같은 모듈로 질문을 토큰화해야 함(core_indexing 또는 my_indexing)
        "kiwipiepy": package_version("kiwipiepy"),
        "bm25s": package_version("bm25s"),
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    with open(index_dir / "manifest.json", "w", encoding="utf-8") as file:
        json.dump(manifest, file, ensure_ascii=False, indent=2)


def step_bm25_index(chunks: list[dict], data_dir: Path) -> None:
    """청크 본문을 Kiwi로 토큰화해 bm25s 색인을 만들고 저장함. 핵심 함수 build_tokenizer, tokenize_korean(안에서 apply_aliases), build_bm25_index와 제공 함수 make_alias_table, build_alias_lookup이 맡음.

    방법: 카드명 → 별칭 사전(규칙 생성 + 걸러내기 + 승인분) → 사용자 사전(Kiwi) → 청크 토큰화 → bm25s 점수표 저장
          → 다시 읽어 문서 수가 청크 수와 같은지 검증(교재 130쪽 ④ "저장·검증").
    부수효과: data_dir 아래 bm25/ 를 만듦.
    """
    print_step(7, f"BM25 색인 — Kiwi 토큰화 + bm25s (k1={BM25_K1}, b={BM25_B}, {indexing.BM25_METHOD})")
    index_dir = data_dir / BM25_DIR_NAME

    # ===== 사용자 사전, 별칭 사전을 만들고 Kiwi 형태소 분석기에 고유명사로 등록 ====
    # 사전자 사전 만들기: 청크에서 카드명만 모아 정식명 목록을 만듦
    card_names = collect_card_names(chunks)
    
    # 별칭 사전 만들기: 정식명을 키로 별칭을 값으로 하는 dict
    aliases, review = indexing.make_alias_table(card_names, load_approved_aliases())
    
    # 별칭 사전을 뒤집어 역방향 대응표 {별칭: 정식명}을 만듦.
    alias_to_name = indexing.build_alias_lookup(aliases)
    
    # Kiwi 형태소 분석기를 만들고 사용자 사전과 별칭사전을 고유명사(NNP)로 등록함
    kiwi = indexing.build_tokenizer(card_names, aliases)
    # ============================================================================
    
    alias_count = 0
    for alias_list in aliases.values():
        alias_count = alias_count + len(alias_list)
    print(f"  카드명 {len(card_names)}개 → 별칭 {alias_count}개 등록, 검수 대상(미승인) {len(review)}개 (예: {review[:2]})")

    print("  예시: 한 문장이 색인 단어가 되기까지")
    print_tokenize_trace(kiwi, alias_to_name, TRACE_SENTENCE)
    print("  자가 테스트: 네 가지 표기의 질문")
    run_alias_self_test(kiwi, alias_to_name)

    
    # ============= 청크 본문을 Kiwi로 토큰화하고 bm25s 색인을 만듦 =============
    # 청크 토큰화하면서 별칭 사전의 역방향 대응표(alias_to_name)를 적용함. 청크 ID도 함께 모음
    started_at = time.time()
    chunk_tokens = []
    chunk_ids = []
    for chunk in chunks:
        chunk_tokens.append(indexing.tokenize_korean(kiwi, chunk["text"], alias_to_name))  # Kiwi 토큰화
        chunk_ids.append(chunk["chunk_id"])
        
    token_total = 0
    for tokens in chunk_tokens:
        token_total = token_total + len(tokens)
    print(f"  청크 {len(chunks)}개 토큰화 {time.time() - started_at:.1f}초, 청크당 평균 {token_total / len(chunks):.0f} 토큰")
    
    # BM25 색인 만들기(점수화 포함) 후 저장    
    doc_count = indexing.build_bm25_index(chunk_tokens, chunk_ids, index_dir, BM25_K1, BM25_B)  # bm25s 색인
    # ===========================================================================
    
    # ============== 검색을 위한 중요 정보 저장 및 색인 검증 ==============
    # 색인 폴더에 사전(dictionary.json), 검수 목록(aliases_review.json), 요약(manifest.json) 저장 : 검색 시 필요한 정보라 저장함   
    write_bm25_sidecars(index_dir, card_names, aliases, review, len(chunks))

    # 검증: 저장한 색인을 다시 읽어 문서 수와 ID 수가 청크 수와 같은지 봄
    bm25, loaded_ids = indexing.load_bm25_index(index_dir)
    print(f"  색인 문서 수: {doc_count}, 다시 읽은 문서 수: {bm25.scores['num_docs']}, chunk_id 수: {len(loaded_ids)} (청크 {len(chunks)}개)")
    if bm25.scores["num_docs"] != len(chunks) or len(loaded_ids) != len(chunks):
        print("  오류: 색인 문서 수가 청크 수와 다름 → 색인을 다시 만들어야 함")
        sys.exit(1)
    print(f"  저장 위치: {index_dir} (bm25s 점수표, chunk_ids.json, dictionary.json, aliases_review.json, manifest.json)")
    #==========================================================================

# ---------------------------------------------------------------------------
# main: 점검 뒤 7단계를 순서대로 실행함
# ---------------------------------------------------------------------------
def main() -> None:
    """명령행 옵션을 읽고 인덱싱 7단계를 실행함. 전체 실행은 data/, --limit 실행은 data-limit/ 에 씀."""
    parser = argparse.ArgumentParser(description="RAG 인덱싱 예제: 로드 → 정제 → 가명처리 → 청킹 → 임베딩 → 적재 → BM25 색인")
    parser.add_argument("--limit", type=int, default=None, help="문서마다 앞 N쪽(또는 N건)만 처리해 빨리 확인함")
    parser.add_argument("--mine", action="store_true", help="강사 코드 대신 교육생 코드(my_indexing.py)로 실행함")
    args = parser.parse_args()
    limit = args.limit

    check_docs_dir()
    check_secrets()
    global cohere_client  # 모듈 맨 위 변수에 넣어 count_tokens가 인자 없이 쓰게 함
    cohere_client = cohere.ClientV2(api_key=os.environ[COHERE_API_KEY_NAME])

    data_dir = DATA_DIR
    if limit is not None:
        data_dir = DATA_LIMIT_DIR  # 부분 결과가 검색기가 읽는 전체 결과를 덮어쓰지 않게 함
        print(f"--limit {limit}: 결과는 {data_dir} 에 씀(검색기는 data/ 를 읽으므로 영향 없음)")
        if limit < D2_CARD_INDEX_LAST_PAGE:
            print(f"--limit 가 {D2_CARD_INDEX_LAST_PAGE} 미만이면 카드명 표(3 ~ 6쪽)를 다 읽지 못해 일부 카드 머리말이 안 붙음(단계 7 자가 테스트도 실패로 표시될 수 있음)")

    remove_old_outputs(data_dir)  # 지난 실행 결과를 지움. 실패하면 안내하고 종료함

    # 1 로드: PDF(D1, D2)는 쪽 단위로, 상담 파일(D3)은 상담 건 단위로 원문 텍스트를 꺼냄
    pdf_pages_by_file, consult_records_by_file = step_load(limit)
    
    # 2 정제: 검색에 쓸모없는 머리말, 꼬리말, 쪽번호를 지우고 D2 카드명 표를 만듦
    page_documents, card_names = step_clean(pdf_pages_by_file)
    
    # 3 가명처리: 상담 본문의 개인정보 줄을 지우고 이름, 전화번호 등을 토큰으로 바꿔 색인에 남기지 않음
    consult_documents = step_mask(consult_records_by_file)
    
    # 4 청킹: 검색 단위가 되도록 문서 유형별 구분자로 잘게 나누고, D2 청크에는 카드명 머리말을 붙임
    chunks = step_chunk(page_documents, consult_documents, card_names)
    
    # 5 임베딩: 의미가 비슷한 글을 찾을 수 있도록 청크 본문을 Cohere API로 벡터(숫자 목록)로 바꿈
    embeddings, vectors = step_embed(chunks)
    
    # 6 적재: 검색기가 읽도록 본문, 메타데이터, 벡터를 Chroma에 저장함
    step_store(chunks, vectors, embeddings, data_dir)

    # 7 BM25 색인: 카드 사용자 사전과 별칭 사전으로 청크를 Kiwi 토큰화하고 bm25s 점수표를 미리 계산해 저장함
    step_bm25_index(chunks, data_dir)

    print("=" * 60)
    print("완료")


if __name__ == "__main__":
    main()
