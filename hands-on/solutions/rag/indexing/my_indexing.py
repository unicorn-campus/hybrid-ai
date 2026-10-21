"""교육생용 뼈대: core_indexing.py와 같은 이름·같은 인자의 함수 8개를 본인 코드로 채우는 파일임.

채우는 순서(쉬운 것부터). 앞의 6개는 직접 쓰고, 뒤의 2개는 거의 완성된 코드의 빈칸만 채움
  1 member_pseudonym   (보조) 가명 ID 2줄
  2 chunk_document     (핵심) 분할기 만들기
  3 clean_page_text    (보조) 줄 걸러내기
  4 find_repeated_lines(보조) 반복 줄 세기
  5 mask_private_info  (보조) 정규식 치환
  6 clean_document     (핵심) 위 보조 함수를 순서대로 부르기
  7 embed_chunks       (핵심) 빈칸 2곳: 배치 슬라이싱, 벡터 이어 붙이기
  8 store_chunks       (핵심) 빈칸 3곳: 배치 슬라이싱, collection.add 인자, JSON 쓰기
"""

# 사용법: 아래 함수를 채운 뒤 index_docs.py의 import 한 줄을 "import my_indexing as indexing"으로 바꿈
# 정규식과 상수는 학습 목표가 아니므로 완성본을 그대로 줌. 교육생은 이 값을 "쓰는" 코드만 작성함
# 임베딩(7)은 API를 부르므로 먼저 "--limit 8"로 실행해 호출 횟수가 적을 때 맞는지 확인한 뒤 전체를 돌림

import hashlib
import json
import re
from pathlib import Path

import chromadb
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

# --- 완성본 상수(그대로 씀) -------------------------------------------------
MARGIN_TOP_LINES = 4  # 쪽 위쪽에서 머리말 후보로 보는 줄 수
MARGIN_BOTTOM_LINES = 2  # 쪽 아래쪽에서 꼬리말 후보로 보는 줄 수

PAGE_NUMBER_PATTERN = re.compile(r"^-\s*\d+\s*-$")  # "- 3 -" 꼴 쪽번호 줄
DIGITS_ONLY_PATTERN = re.compile(r"^\d+$")  # "17" 처럼 숫자만 있는 줄(D2 쪽번호)

# 가명처리 규칙: (찾을 정규식, 바꿀 말). 적힌 순서대로 적용함. 카드번호를 전화번호보다 먼저 바꿈
PRIVATE_PATTERNS = [
    (re.compile(r"가상고객\d+"), "[고객]"),
    (re.compile(r"가상상담사\d+"), "[상담사]"),
    (re.compile(r"\d{4}-\d{4}-\d{4}-\d{4}"), "[카드번호]"),  # 0000-0000-0001-0017
    (re.compile(r"(?<!\d)\d{16}(?!\d)"), "[카드번호]"),  # 하이픈 없는 16자리
    (re.compile(r"(끝\s*(?:네|4)\s*자리는?\s*)\d{4}"), r"\1[카드번호]"),  # "끝 네 자리는 0017"
    (re.compile(r"010[-\s]?\d{4}[-\s]?\d{4}"), "[전화번호]"),  # 010-0000-0001, 010 0000 0001
    (re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"), "[이메일]"),
    (re.compile(r"19\d{2}년\s*\d{1,2}월\s*\d{1,2}일"), "[생년월일]"),  # 상담일(2026-...)은 남기려고 19xx만 봄
    (re.compile(r"19\d{2}-\d{2}-\d{2}"), "[생년월일]"),
]
AGE_PATTERN = re.compile(r"만\s*(\d{1,3})세")  # "만 35세" → 연령대로 바꿀 대상. group(1)이 나이 숫자임


# ---------------------------------------------------------------------------
# 보조 함수 4개: 정제와 가명처리의 부품
# ---------------------------------------------------------------------------
def find_repeated_lines(pages: list[str], min_pages: int = 2) -> set[str]:
    """여러 쪽에 반복되는 머리말·꼬리말 줄을 찾음.

    인자: pages는 쪽 단위 원문 텍스트 목록. min_pages는 "이 쪽수 이상 나오면 반복"으로 보는 기준임.
    반환값: 반복 줄의 집합(앞뒤 공백을 뗀 문자열).
    """
    # 할 일 1: 쪽마다 줄을 나누고(splitlines) 앞뒤 공백을 뗀 뒤 빈 줄은 버림
    # 할 일 2: 쪽 위쪽 MARGIN_TOP_LINES줄과 아래쪽 MARGIN_BOTTOM_LINES줄만 후보로 삼아 set으로 묶음
    # 할 일 3: 후보 줄이 몇 쪽에 나오는지 dict로 셈(같은 쪽 안에서 두 번 나와도 1쪽으로 셈)
    # 할 일 4: 쪽 수가 min_pages 이상인 줄만 set에 담아 돌려줌
    raise NotImplementedError("여기에 본인 코드를 작성함")


def clean_page_text(page_text: str, repeated_lines: set[str]) -> str:
    """PDF 한 쪽의 텍스트에서 머리말·꼬리말, 쪽번호, 숫자만 있는 줄을 지우고 빈 줄을 정리함.

    인자: repeated_lines는 find_repeated_lines가 돌려준 집합임.
    반환값: 정제된 쪽 텍스트. 모든 줄이 지워지면 빈 문자열임.
    """
    # 할 일 1: 줄마다 앞뒤 공백을 떼고 repeated_lines에 있으면 버림
    # 할 일 2: PAGE_NUMBER_PATTERN.match(줄) 또는 DIGITS_ONLY_PATTERN.match(줄)에 걸리는 줄도 버림
    # 할 일 3: 남은 줄을 이을 때 연속 빈 줄은 1개로 줄임(바로 앞에 넣은 줄이 빈 줄이면 건너뜀)
    # 할 일 4: "\n"으로 이어 붙이고 앞뒤 공백을 뗀 문자열을 돌려줌
    raise NotImplementedError("여기에 본인 코드를 작성함")


def mask_private_info(text: str) -> str:
    """상담 본문 안의 개인정보를 유형 토큰으로 바꾸거나 범위로 넓힘.

    반환값: 치환된 본문. 예: "제 이름은 가상고객0001입니다" → "제 이름은 [고객]입니다"
    """
    # 할 일 1: PRIVATE_PATTERNS를 for로 돌며 pattern.sub(replacement, text)로 차례로 바꿈
    # 할 일 2: 나이를 연령대로 바꾸는 작은 함수를 만듦. 예: match.group(1)이 "35"면 (35 // 10) * 10 → "30대"
    # 할 일 3: AGE_PATTERN.sub(그 함수, text)처럼 sub에 함수를 넘기면 찾은 자리마다 함수 결과로 바뀜
    # 할 일 4: 다 바꾼 문자열을 돌려줌
    raise NotImplementedError("여기에 본인 코드를 작성함")


def member_pseudonym(member_id: str) -> str:
    """회원번호를 되돌릴 수 없는 가명 ID로 바꿈.

    반환값: "m_" + 16자리 문자열. 예: "M-1042" → "m_59853c3d8e1e3c25"
    """
    # 할 일 1: hashlib.sha256(member_id.encode("utf-8")).hexdigest()의 앞 16자리를 구함
    # 할 일 2: 앞에 "m_"를 붙여 돌려줌. 검색기·평가셋이 같은 식을 쓰므로 식을 바꾸면 회원 필터가 어긋남
    raise NotImplementedError("여기에 본인 코드를 작성함")


# ---------------------------------------------------------------------------
# 핵심 함수 1. 정제
# ---------------------------------------------------------------------------
def clean_document(text: str, repeated_lines: set[str] | None = None, mask_private: bool = False) -> str:
    """문서 한 단위(PDF 한 쪽 또는 상담 한 건)의 본문을 정제함.

    인자: repeated_lines가 None이 아니면 쪽 정제(clean_page_text)를 함. mask_private가 True면 가명처리를 함.
    반환값: 정제된 본문. main은 PDF 쪽에는 repeated_lines를, 상담 건에는 mask_private=True를 넘김.
    """
    # 할 일 1: repeated_lines가 None이 아니면 clean_page_text(text, repeated_lines)로 바꿈
    # 할 일 2: mask_private가 True면 mask_private_info(...)로 한 번 더 바꿈
    # 할 일 3: 결과를 돌려줌(둘 다 해당 없으면 입력 그대로)
    raise NotImplementedError("여기에 본인 코드를 작성함")


# ---------------------------------------------------------------------------
# 핵심 함수 2. 청킹
# ---------------------------------------------------------------------------
def chunk_document(
    text: str,
    metadata: dict,
    separators: list[str],
    count_tokens,
    chunk_size: int,
    chunk_overlap: int,
) -> list[Document]:
    """본문 하나를 토큰 상한 안의 청크 여러 개로 나누고, 같은 메타데이터를 청크마다 복사함.

    인자: count_tokens는 문자열을 받아 토큰 수를 돌려주는 함수(main이 넘겨 줌). separators는 정규식 목록(앞이 우선).
          chunk_size·chunk_overlap 단위는 토큰임.
    반환값: Document 목록. page_content가 청크 본문, metadata는 입력 metadata의 복사본임.
    """
    # 할 일 1: RecursiveCharacterTextSplitter(...)로 분할기를 만듦. length_function=count_tokens 로 길이 기준을 토큰 수로 바꿈
    # 할 일 2: chunk_size, chunk_overlap, separators, is_separator_regex=True, keep_separator="start"도 함께 넘김
    # 할 일 3: splitter.create_documents([text], metadatas=[metadata])의 결과를 그대로 돌려줌
    raise NotImplementedError("여기에 본인 코드를 작성함")


# ---------------------------------------------------------------------------
# 핵심 함수 3. 임베딩 (빈칸 채우기)
# ---------------------------------------------------------------------------
def embed_chunks(texts: list[str], embeddings, batch_size: int) -> tuple[list[list[float]], int]:
    """청크 본문 목록을 배치로 나눠 임베딩 API에 보내고, 입력 순서 그대로 벡터 목록을 만듦.

    인자: embeddings는 embed_documents(list[str]) -> list[list[float]] 메서드를 가진 객체(main이 만듦).
    반환값: (벡터 목록, API 호출 횟수). 벡터 목록의 i번째는 texts의 i번째 본문의 벡터임.
    """
    vectors = []
    api_calls = 0
    for start in range(0, len(texts), batch_size):
        batch_texts = None  # 빈칸 1: texts에서 start부터 batch_size개를 슬라이싱해 넣음
        if batch_texts is None:
            raise NotImplementedError("빈칸 1을 채울 것")
        batch_vectors = embeddings.embed_documents(batch_texts)
        # 빈칸 2: batch_vectors를 vectors 뒤에 이어 붙임(append가 아니라 목록을 통째로 잇는 메서드)
        raise NotImplementedError("빈칸 2를 채우고 이 줄을 지울 것")
        api_calls = api_calls + 1
    return vectors, api_calls


# ---------------------------------------------------------------------------
# 핵심 함수 4. 적재 (빈칸 채우기)
# ---------------------------------------------------------------------------
def store_chunks(
    chunks: list[dict],
    vectors: list[list[float]],
    chroma_dir: Path,
    chunks_json_path: Path,
    collection_name: str,
    collection_metadata: dict,
    batch_size: int,
) -> int:
    """청크와 벡터를 Chroma collection에 넣고, 청크 목록을 chunks.json으로 씀.

    인자: chunks는 {"chunk_id", "text", "metadata"} dict 목록. vectors는 chunks와 길이·순서가 같아야 함.
    반환값: collection에 저장된 건수.
    """
    client = chromadb.PersistentClient(path=str(chroma_dir))
    collection = client.get_or_create_collection(name=collection_name, metadata=collection_metadata)
    for start in range(0, len(chunks), batch_size):
        ids = []
        documents = []
        metadatas = []
        for chunk in chunks[start : start + batch_size]:
            ids.append(chunk["chunk_id"])
            documents.append(chunk["text"])
            metadatas.append(chunk["metadata"])
        batch_vectors = None  # 빈칸 1: vectors에서 같은 자리(start부터 batch_size개)를 슬라이싱해 넣음
        if batch_vectors is None:
            raise NotImplementedError("빈칸 1을 채울 것")
        # 빈칸 2: collection.add(ids=..., documents=..., embeddings=..., metadatas=...)를 위 네 목록으로 부름
        raise NotImplementedError("빈칸 2를 채우고 이 줄을 지울 것")

    with open(chunks_json_path, "w", encoding="utf-8") as file:
        # 빈칸 3: json.dump(...)로 chunks를 file에 씀. 한글이 그대로 보이게 ensure_ascii=False, 보기 좋게 indent=2
        raise NotImplementedError("빈칸 3을 채우고 이 줄을 지울 것")

    return collection.count()
