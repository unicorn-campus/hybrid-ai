"""인덱싱 핵심 모듈: 정제 → 청킹 → 임베딩 → 적재 4단계 함수와 보조 함수 4개(교육생 클론 코딩 대상)임.

핵심 함수 4개(단계 이름 그대로)
- clean_document  : 정제. PDF 쪽의 머리말·꼬리말·쪽번호 삭제, 상담 건의 개인정보 가명처리
- chunk_document  : 청킹. 구분자 우선순위와 토큰 상한으로 본문을 청크로 나눔
- embed_chunks    : 임베딩. 청크 본문을 배치로 나눠 임베딩 API에 보내고 벡터를 모음
- store_chunks    : 적재. 벡터와 메타데이터를 Chroma에 넣고 chunks.json을 씀

보조 함수 4개(핵심 함수가 안에서 부름)
- find_repeated_lines, clean_page_text : 정제가 씀
- mask_private_info, member_pseudonym  : 가명처리가 씀(member_pseudonym은 main이 메타데이터를 만들 때 직접 부름)

로드(PDF 읽기, 상담 파일 나누기)는 라이브러리 호출뿐이라 main(index_docs.py)에 둠.
"""

import hashlib
import json
import re
from pathlib import Path

import chromadb
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


# ---------------------------------------------------------------------------
# 보조 함수: 정제와 가명처리의 부품
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# 핵심 함수 1. 정제
# ---------------------------------------------------------------------------
def clean_document(text: str, repeated_lines: set[str] | None = None, mask_private: bool = False) -> str:
    """문서 한 단위(PDF 한 쪽 또는 상담 한 건)의 본문을 정제함.

    목적: 청킹 전에 검색에 쓸모없는 줄을 걷어내고, 개인정보는 색인에 남기지 않기 위함.
    방법: PDF 쪽이면 repeated_lines를 넘겨 머리말·꼬리말·쪽번호를 지움(clean_page_text).
          상담 건이면 mask_private=True로 개인정보를 유형 토큰으로 바꿈(mask_private_info).
          둘 다 켜면 순서대로 둘 다 적용함.
    인자: repeated_lines는 find_repeated_lines가 돌려준 집합. None이면 쪽 정제를 건너뜀.
          mask_private가 True면 가명처리를 함.
    반환값: 정제된 본문. 모든 줄이 지워지면 빈 문자열임.
    """
    cleaned_text = text
    if repeated_lines is not None:
        cleaned_text = clean_page_text(cleaned_text, repeated_lines)
    if mask_private:
        cleaned_text = mask_private_info(cleaned_text)
    return cleaned_text


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


# ---------------------------------------------------------------------------
# 핵심 함수 3. 임베딩
# ---------------------------------------------------------------------------
def embed_chunks(texts: list[str], embeddings, batch_size: int) -> tuple[list[list[float]], int]:
    """청크 본문 목록을 배치로 나눠 임베딩 API에 보내고, 입력 순서 그대로 벡터 목록을 만듦.

    목적: API는 한 요청에 넣을 수 있는 건수에 상한이 있고, 한 번에 다 보내면 실패 시 전부 잃으므로 나눠 보냄.
    방법: start를 0, batch_size, 2*batch_size ... 로 옮기며 texts[start : start + batch_size]를 잘라
          embeddings.embed_documents(배치)로 벡터를 받고 vectors 뒤에 이어 붙임.
    인자: embeddings는 embed_documents(list[str]) -> list[list[float]] 메서드를 가진 객체(main이 만듦).
          batch_size는 한 요청에 넣을 최대 건수임(Cohere는 96).
    반환값: (벡터 목록, API 호출 횟수). 벡터 목록의 i번째는 texts의 i번째 본문의 벡터임.
    예외: API 오류(호출 한도 초과 등)는 여기서 잡지 않고 main이 잡아 안내함.
    """
    vectors = []
    api_calls = 0
    for start in range(0, len(texts), batch_size):
        batch_texts = texts[start : start + batch_size]
        batch_vectors = embeddings.embed_documents(batch_texts)
        vectors.extend(batch_vectors)
        api_calls = api_calls + 1
    return vectors, api_calls


# ---------------------------------------------------------------------------
# 핵심 함수 4. 적재
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

    목적: 검색기가 벡터 검색(Chroma)과 BM25·본문 표시(chunks.json) 두 가지를 읽을 수 있게 저장함.
    방법: ① PersistentClient로 chroma_dir을 열고 collection을 만듦(거리 방식과 HNSW 값은 collection_metadata).
          ② chunks와 vectors를 같은 자리끼리 batch_size개씩 묶어 collection.add(ids, documents, embeddings, metadatas).
             벡터를 이미 계산했으므로 chromadb 클라이언트로 직접 넣음(langchain의 add_documents는 다시 임베딩함).
          ③ chunks 목록을 그대로 JSON으로 씀(ensure_ascii=False라 한글이 그대로 보임).
    인자: chunks는 {"chunk_id", "text", "metadata"} dict 목록. vectors는 chunks와 길이·순서가 같아야 함.
    반환값: collection에 저장된 건수. chunks 수와 같아야 정상임.
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
        batch_vectors = vectors[start : start + batch_size]
        collection.add(ids=ids, documents=documents, embeddings=batch_vectors, metadatas=metadatas)

    with open(chunks_json_path, "w", encoding="utf-8") as file:
        json.dump(chunks, file, ensure_ascii=False, indent=2)

    return collection.count()
