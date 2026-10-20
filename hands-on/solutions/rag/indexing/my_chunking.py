"""교육생용 뼈대: core_chunking.py와 같은 이름·같은 인자의 함수 5개를 본인 코드로 채우는 파일임."""

# 사용법: 아래 함수를 채운 뒤 index_docs.py의 import 한 줄을 "import my_chunking as chunking"으로 바꿈
# 정규식과 상수는 학습 목표가 아니므로 완성본을 그대로 줌. 교육생은 이 값을 "쓰는" 코드만 작성함

import hashlib
import re

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


def split_into_chunks(
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
