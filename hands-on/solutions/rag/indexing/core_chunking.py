"""인덱싱 핵심 모듈: PDF 쪽 정제, 상담 가명처리, 토큰 기준 청킹 함수 5개(교육생 클론 코딩 대상)임."""

import hashlib
import re

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

# 머리말·꼬리말 후보로 보는 영역. PyMuPDF의 get_text()는 글자 좌표를 주지 않으므로
# "쪽 위쪽 몇 줄, 아래쪽 몇 줄"을 머리말·꼬리말 영역으로 봄(교육용 단순화)
# 쪽 전체 줄로 반복을 세면 D2 표의 "항목"·"혜택" 같은 본문 머리글까지 지워지므로 영역을 제한함
MARGIN_TOP_LINES = 4  # 쪽 위쪽에서 머리말 후보로 보는 줄 수
MARGIN_BOTTOM_LINES = 2  # 쪽 아래쪽에서 꼬리말 후보로 보는 줄 수

PAGE_NUMBER_PATTERN = re.compile(r"^-\s*\d+\s*-$")  # "- 3 -" 꼴 쪽번호 줄
DIGITS_ONLY_PATTERN = re.compile(r"^\d+$")  # "17" 처럼 숫자만 있는 줄(D2 쪽번호)

# 가명처리 규칙: (찾을 정규식, 바꿀 말). 적힌 순서대로 적용함
# 카드번호를 전화번호보다 먼저 바꿈. 숫자 묶음이 긴 카드번호 안에서 전화번호 꼴이 먼저 잡히는 일을 막기 위함
PRIVATE_PATTERNS = [
    (re.compile(r"가상고객\d+"), "[고객]"),
    (re.compile(r"가상상담사\d+"), "[상담사]"),
    (re.compile(r"\d{4}-\d{4}-\d{4}-\d{4}"), "[카드번호]"),  # 0000-0000-0001-0017
    (re.compile(r"(?<!\d)\d{16}(?!\d)"), "[카드번호]"),  # 하이픈 없는 16자리
    (re.compile(r"(끝\s*(?:네|4)\s*자리는?\s*)\d{4}"), r"\1[카드번호]"),  # "끝 네 자리는 0017"
    (re.compile(r"010[-\s]?\d{4}[-\s]?\d{4}"), "[전화번호]"),  # 010-0000-0001, 010 0000 0001
    (re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"), "[이메일]"),
    # 생년월일은 19xx년만 봄. 상담일(2026-03-14)과 이용월(2026-02) 같은 업무 날짜는 남겨야 하기 때문임
    (re.compile(r"19\d{2}년\s*\d{1,2}월\s*\d{1,2}일"), "[생년월일]"),
    (re.compile(r"19\d{2}-\d{2}-\d{2}"), "[생년월일]"),
]
AGE_PATTERN = re.compile(r"만\s*(\d{1,3})세")  # "만 35세" → 연령대로 바꿀 대상


def find_repeated_lines(pages: list[str], min_pages: int = 2) -> set[str]:
    """여러 쪽에 반복되는 머리말·꼬리말 줄을 찾음.

    목적: "한빛카드 개인회원 이용약관", "SYNTHETIC DATA" 같은 줄은 본문이 아니므로 청크에서 빼기 위함.
    방법: 쪽마다 위쪽 MARGIN_TOP_LINES줄과 아래쪽 MARGIN_BOTTOM_LINES줄만 후보로 모아 몇 쪽에 나오는지 셈.
    인자: pages는 쪽 단위 원문 텍스트 목록. min_pages는 "이 쪽수 이상 나오면 반복"으로 보는 기준임.
    반환값: 반복 줄의 집합(앞뒤 공백을 뗀 문자열). 한 쪽짜리 문서면 빈 집합임.
    """
    count_by_line = {}  # 줄 → 그 줄이 머리말·꼬리말 영역에 나온 쪽 수

    for page_text in pages:
        lines = []
        for raw_line in page_text.splitlines():
            line = raw_line.strip()
            if line != "":
                lines.append(line)

        # 같은 쪽 안에서 두 번 나와도 한 쪽으로 세야 하므로 set으로 묶음
        margin_lines = set(lines[:MARGIN_TOP_LINES] + lines[-MARGIN_BOTTOM_LINES:])
        for line in margin_lines:
            if line in count_by_line:
                count_by_line[line] = count_by_line[line] + 1
            else:
                count_by_line[line] = 1

    repeated_lines = set()
    for line, page_count in count_by_line.items():
        if page_count >= min_pages:
            repeated_lines.add(line)
    return repeated_lines


def clean_page_text(page_text: str, repeated_lines: set[str]) -> str:
    """PDF 한 쪽의 텍스트에서 머리말·꼬리말, 쪽번호, 숫자만 있는 줄을 지우고 빈 줄을 정리함.

    목적: 검색에 쓸모없는 줄이 청크에 섞이면 벡터와 BM25 점수가 흐려지므로 청킹 전에 걷어냄.
    방법: 줄마다 ① 반복 줄 ② "- 3 -" 꼴 쪽번호 ③ 숫자만 있는 줄이면 버리고, 연속 빈 줄은 1개로 줄임.
    인자: repeated_lines는 find_repeated_lines가 돌려준 집합임.
    반환값: 정제된 쪽 텍스트. 모든 줄이 지워지면 빈 문자열임.
    """
    kept_lines = []
    for raw_line in page_text.splitlines():
        line = raw_line.strip()
        if line in repeated_lines:
            continue
        if PAGE_NUMBER_PATTERN.match(line):
            continue
        if DIGITS_ONLY_PATTERN.match(line):
            continue
        kept_lines.append(line)

    # 연속 빈 줄을 1개로 줄임. 빈 줄이 많으면 "\n\n" 구분자가 의미 없는 자리에서 자르게 됨
    result_lines = []
    for line in kept_lines:
        if line == "" and len(result_lines) > 0 and result_lines[-1] == "":
            continue
        result_lines.append(line)

    return "\n".join(result_lines).strip()


def _age_to_decade(match: re.Match) -> str:
    """정규식이 잡은 "만 35세"를 "30대"로 바꿈. 정확한 나이는 개인 식별에 쓰일 수 있어 범위로 넓힘."""
    age = int(match.group(1))
    decade = (age // 10) * 10
    return str(decade) + "대"


def mask_private_info(text: str) -> str:
    """상담 본문 안의 개인정보를 유형 토큰으로 바꾸거나 범위로 넓힘.

    목적: 고객명·전화·이메일·카드번호·생년월일은 답변에 필요 없고 유출 위험만 있으므로 색인 전에 없앰.
    방법: PRIVATE_PATTERNS를 적힌 순서대로 정규식 치환하고, 마지막에 "만 35세"를 "30대"로 바꿈.
    반환값: 치환된 본문. 개인정보가 없으면 입력과 같음.
    예시: "제 이름은 가상고객0001입니다" → "제 이름은 [고객]입니다"
    """
    masked_text = text
    for pattern, replacement in PRIVATE_PATTERNS:
        masked_text = pattern.sub(replacement, masked_text)
    masked_text = AGE_PATTERN.sub(_age_to_decade, masked_text)
    return masked_text


def member_pseudonym(member_id: str) -> str:
    """회원번호를 되돌릴 수 없는 가명 ID로 바꿈.

    목적: 같은 회원의 상담을 묶어 검색하되 원래 회원번호는 저장하지 않기 위함.
    방법: SHA-256 해시의 16진수 앞 16자리에 "m_"을 붙임. 검색기·평가셋과 같은 식이어야 필터가 맞음.
    반환값: "m_" + 16자리 문자열. 예: "M-1042" → "m_59853c3d8e1e3c25"
    """
    digest = hashlib.sha256(member_id.encode("utf-8")).hexdigest()
    return "m_" + digest[:16]


def split_into_chunks(
    text: str,
    metadata: dict,
    separators: list[str],
    count_tokens,
    chunk_size: int,
    chunk_overlap: int,
) -> list[Document]:
    """본문 하나를 토큰 상한 안의 청크 여러 개로 나누고, 같은 메타데이터를 청크마다 복사함.

    목적: 임베딩 모델 입력 상한 안에서 조항·카드 코드·발화 같은 의미 경계를 지키며 나누기 위함.
    방법: RecursiveCharacterTextSplitter가 separators를 앞에서부터 시도함. 첫 구분자로 잘라도 길면
          다음 구분자로 더 나눔. 길이는 글자 수가 아니라 count_tokens가 돌려주는 토큰 수로 셈.
    인자: count_tokens는 문자열을 받아 토큰 수(int)를 돌려주는 함수(main이 Cohere 토크나이저로 만듦).
          separators는 정규식 문자열 목록(앞이 우선). chunk_size·chunk_overlap 단위는 토큰임.
    반환값: Document 목록. 각 Document의 page_content가 청크 본문, metadata는 입력 metadata의 복사본임.
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        length_function=count_tokens,  # 기본값은 글자 수(len). 토큰 수로 재려고 함수를 바꿔 끼움
        separators=separators,
        is_separator_regex=True,
        keep_separator="start",  # "제3조(" 같은 경계 문구가 다음 청크의 맨 앞에 남게 함
    )
    documents = splitter.create_documents([text], metadatas=[metadata])
    return documents
