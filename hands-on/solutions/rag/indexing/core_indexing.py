"""인덱싱 핵심 모듈: 정제 → 청킹 → 임베딩 → 적재 → BM25 색인 함수와 보조 함수(교육생 클론 코딩 대상)임.

벡터 색인 핵심 함수 4개(단계 이름 그대로)
- clean_document  : 정제. PDF 쪽의 머리말·꼬리말·쪽번호 삭제, 상담 건의 개인정보 가명처리
- chunk_document  : 청킹. 구분자 우선순위와 토큰 상한으로 본문을 청크로 나눔
- embed_chunks    : 임베딩. 청크 본문을 배치로 나눠 임베딩 API에 보내고 벡터를 모음
- store_chunks    : 적재. 벡터와 본문과 메타데이터를 Chroma에 넣음(검색기는 본문도 Chroma에서 읽음)

벡터 색인 보조 함수 4개(핵심 함수가 안에서 부름)
- find_repeated_lines, clean_page_text : 정제가 씀
- mask_private_info, member_pseudonym  : 가명처리가 씀(member_pseudonym은 main이 메타데이터를 만들 때 직접 부름)

BM25 색인 핵심 함수 3개(직접 작성)와 1개(빈칸 채우기). 교재 130 ~ 131쪽
- build_tokenizer : 카드 사용자 사전. Kiwi에 카드 정식명과 별칭을 고유명사로 등록해 쪼개지지 않게 함
- apply_aliases   : 별칭 사전 치환. 별칭 토큰을 정식명 토큰으로 바꿔 BM25가 같은 단어로 세게 함
- tokenize_korean : Kiwi 토큰화. 표기 통일 → 코드 추출 → 내용어 선택 → 별칭 치환. 문서와 질문에 같은 규칙
- build_bm25_index: bm25s 점수표를 미리 계산해 폴더에 저장(빈칸 채우기)

BM25 색인 제공 함수(읽기만)
- canonical_card_name, make_alias_table, build_alias_lookup : 별칭 후보 생성과 걸러내기(문자열 규칙)
- load_bm25_index : 저장한 색인과 chunk_id 순서를 다시 읽음(검색기가 씀)

로드(PDF 읽기, 상담 파일 나누기)는 라이브러리 호출뿐이라 main(index_docs.py)에 둠.
"""

import hashlib
import json
import re
from pathlib import Path

import bm25s
import chromadb
from kiwipiepy import Kiwi
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
    documents = splitter.create_documents(texts=[text], metadatas=[metadata])
    return documents


# ---------------------------------------------------------------------------
# 핵심 함수 3. 임베딩
# ---------------------------------------------------------------------------
def embed_chunks(texts: list[str], embeddings, batch_size: int) -> tuple[list[list[float]], int]:
    """청크 본문 목록을 배치로 나눠 임베딩 API에 보내고, 입력 순서 그대로 벡터 목록을 만듦.

    목적: API는 한 요청에 넣을 수 있는 건수에 상한이 있고, 한 번에 다 보내면 실패 시 전부 잃으므로 나눠 보냄.
    방법: 청크 본문을 앞에서부터 batch_size개씩 묶음(96개면 0 ~ 95번, 96 ~ 191번, ...). 마지막 묶음은 남은 만큼만 담김.
          묶음마다 embed_documents로 한 번씩 API를 불러 벡터를 받고, 받은 순서대로 vectors 뒤에 이어 붙임.
    인자: embeddings는 embed_documents(list[str]) -> list[list[float]] 메서드를 가진 객체(main이 만듦).
          batch_size는 한 요청에 넣을 최대 건수임(Cohere는 96).
    반환값: (벡터 목록, API 호출 횟수). 벡터 목록의 i번째는 texts의 i번째 본문의 벡터임.
    예외: API 오류(호출 한도 초과 등)는 여기서 잡지 않고 main이 잡아 안내함.
    """
    vectors = []
    api_calls = 0
    for start in range(0, len(texts), batch_size):      #range(시작, 끝, 간격)
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
    collection_name: str,
    collection_metadata: dict,
    batch_size: int,
) -> int:
    """청크의 본문, 메타데이터, 벡터를 Chroma collection에 넣음.

    목적: 검색기가 벡터 검색과 본문 표시를 모두 Chroma 한 곳에서 읽게 함(본문과 메타데이터의 단일 출처).
    방법: ① PersistentClient로 chroma_dir을 열고 collection을 만듦(거리 방식과 HNSW 값은 collection_metadata).
          ② chunks와 vectors를 같은 자리끼리 batch_size개씩 묶어 collection.add(ids, documents, embeddings, metadatas).
             벡터를 이미 계산했으므로 chromadb 클라이언트로 직접 넣음(langchain의 add_documents는 다시 임베딩함).
    인자: chunks는 {"chunk_id", "text", "metadata"} dict 목록. vectors는 chunks와 길이·순서가 같아야 함.
    반환값: collection에 저장된 건수. chunks 수와 같아야 정상임.
    """
    client = chromadb.PersistentClient(path=str(chroma_dir))
    collection = client.get_or_create_collection(name=collection_name, metadata=collection_metadata)
    for start in range(0, len(chunks), batch_size): #range(시작, 끝, 간격)
        ids = []
        documents = []
        metadatas = []
        for chunk in chunks[start : start + batch_size]:
            ids.append(chunk["chunk_id"])
            documents.append(chunk["text"])
            metadatas.append(chunk["metadata"])
        batch_vectors = vectors[start : start + batch_size]
        collection.add(ids=ids, documents=documents, embeddings=batch_vectors, metadatas=metadatas)

    return collection.count()


# ---------------------------------------------------------------------------
# BM25 색인(단계 7) 상수. 교재 130 ~ 131쪽
# ---------------------------------------------------------------------------
# BM25 색인에 남길 품사(Kiwi 태그). 조사·어미·기호는 어느 청크에나 있어 점수를 흐리므로 뺌
# NNG 일반명사, NNP 고유명사, NR 수사, SN 숫자, SL 알파벳, VV 동사 어간, VA 형용사 어간
CONTENT_TAGS = {"NNG", "NNP", "NR", "SN", "SL", "VV", "VA"}

# "D2-C001", "D2-C001-B01", "M-1042", "C-20260302-001" 같은 코드. Kiwi는 이런 코드를 "D", "2", "-", "C", "001"로
# 쪼개므로 코드 전체를 한 토큰으로 따로 뽑음. 색인과 질문에 같은 규칙을 쓰므로 양쪽 토큰이 같아짐
CODE_PATTERN = re.compile(r"[A-Za-z]+\d*-[A-Za-z]*\d+(?:-[A-Za-z]*\d+)*")
NUMBER_COMMA_PATTERN = re.compile(r"(?<=\d),(?=\d)")  # "3,000,000" 안의 쉼표. 질문은 "300만"처럼 쓰기도 해 숫자만 남김

CARD_NAME_PREFIX = "한빛 "  # 카드명 앞의 회사명. 질문에서는 "모아생활 카드"처럼 회사명 없이 묻는 경우가 많음
CARD_WORD = "카드"  # 별칭에 붙이는 말. "모아생활카드"처럼 붙여 묻는 질문을 받기 위함
ALIAS_MIN_LENGTH = 3  # 두 글자 이하 별칭은 걸러냄(교재 131쪽 걸러내기 ③)
BM25_METHOD = "lucene"  # bm25s 점수 공식(교재 130쪽 "bm25s · Lucene 방식")
CHUNK_IDS_FILE = "chunk_ids.json"  # 색인 폴더 안에 두는 청크 ID 순서 파일. 색인의 i번째 문서 = i번째 chunk_id


# ---------------------------------------------------------------------------
# BM25 색인 제공 함수(읽기만). 별칭 후보 생성과 걸러내기는 문자열 규칙이라 BM25 이해와 무관함
# ---------------------------------------------------------------------------
def canonical_card_name(card_name: str) -> str:
    """카드명을 정식명 토큰으로 바꿈. 소문자로 통일하고, 끝의 "카드"를 떼고, 띄어쓰기를 없앰.

    예시: "한빛 모아생활" → "한빛모아생활", "한빛 통신할부 A" → "한빛통신할부a"
    """
    name = card_name.strip().lower()
    if name.endswith(CARD_WORD):
        name = name[: -len(CARD_WORD)]
    return name.replace(" ", "")


def _is_common_noun(base_kiwi: Kiwi, alias: str) -> bool:
    """별칭이 Kiwi 기본 사전에 일반명사로 통째로 있는지 봄(교재 131쪽 걸러내기 ① "일반 명사와 겹침").

    방법: 끝의 "카드"와 띄어쓰기를 뗀 뒤 사용자 사전이 없는 기본 분석기로 분석해, 형태소 1개짜리 일반명사(NNG)면 겹침으로 봄.
          예: "대중교통"은 사전에 있는 일반명사라 "대중교통 할인 카드?" 같은 질문을 특정 카드로 몰아가면 안 됨.
    """
    core = alias.replace(" ", "")
    if core.endswith(CARD_WORD):
        core = core[: -len(CARD_WORD)]
    tokens = list(base_kiwi.tokenize(core))
    return len(tokens) == 1 and tokens[0].tag == "NNG"


def make_alias_table(card_names: list[str], approved: dict | None = None) -> tuple[dict, list[dict]]:
    """정식명 목록에서 별칭 후보를 규칙으로 만들고 위험한 후보를 걸러 별칭 사전을 만듦(교재 131쪽 ①).

    방법: 카드명마다 후보 = {원래 이름, 접두어 뗀 이름, 띄어쓰기 없앤 이름} × {그대로, "카드" 붙임, " 카드" 붙임}.
          걸러내기 ① 일반 명사와 겹침 ② 정식명 여러 개를 가리킴 ③ 두 글자 이하 → 걸러진 후보는 review 목록에 이유와 함께 둠.
          approved(사람 검수 승인분, {정식명: [별칭, ...]})는 걸러내기와 무관하게 추가함.
    인자: card_names는 메타데이터 card_name 값의 집합(중복 없는 목록). approved는 없으면 None.
    반환값: (별칭 사전 {정식명: [별칭, ...]}, 검수 목록 [{"alias", "canonical", "reason"}, ...]) 쌍.
    """
    base_kiwi = Kiwi()  # 사용자 사전이 없는 기본 분석기. 걸러내기 ①에만 씀
    candidates = {}  # 별칭 → 그 별칭이 가리키는 정식명 집합
    # 아래 주석의 예시는 card_name = "한빛 통신할부 A" 한 건을 따라감
    for card_name in card_names:
        canonical = canonical_card_name(card_name)  # 예: "한빛통신할부a" (소문자, 띄어쓰기 없음)
        full_name = card_name.strip().lower()  # 예: "한빛 통신할부 a" (소문자만)
        short_name = full_name  # 예: 접두어가 없을 때를 대비해 일단 "한빛 통신할부 a"로 둠
        if full_name.startswith(CARD_NAME_PREFIX):  # 예: "한빛 "으로 시작하므로 참
            short_name = full_name[len(CARD_NAME_PREFIX):]  # 예: 앞 3글자 "한빛 "을 떼어 "통신할부 a"
        # 예: {"한빛 통신할부 a", "통신할부 a", "통신할부a"}. 이름이 같아지면 set이라 하나만 남음
        base_forms = {full_name, short_name, short_name.replace(" ", "")}
        forms = set()
        for form in base_forms:  # 예: form = "통신할부a"일 때
            forms.add(form)  # 예: "통신할부a"
            forms.add(form + CARD_WORD)  # 예: "통신할부a카드"
            forms.add(form + " " + CARD_WORD)  # 예: "통신할부a 카드"
        # 여기까지 후보 3 × 3 = 9개
        forms.discard(canonical)  # 정식명 자체는 별칭이 아님. 예: "한빛통신할부a"는 후보에 없으므로 그대로 9개
        for alias in forms:  # 예: alias = "통신할부a카드"일 때
            if alias not in candidates:  # 예: 처음 나온 별칭이면
                candidates[alias] = set()  # 예: candidates["통신할부a카드"] = set()
            candidates[alias].add(canonical)  # 예: candidates["통신할부a카드"] = {"한빛통신할부a"}
            # 다른 카드도 같은 별칭을 만들면 집합에 정식명이 2개가 되어 아래 걸러내기 ②에 걸림

    aliases = {}
    review = []
    # 아래 주석의 예시는 통과하는 "가게모음카드"와 걸러지는 "대중교통카드"를 따라감
    for alias in sorted(candidates):  # 가나다순으로 돌아 실행할 때마다 결과 순서가 같게 함
        canonicals = candidates[alias]  # 예: "가게모음카드" → {"한빛가게모음"}, "대중교통카드" → {"한빛대중교통"}
        reason = None  # 걸러진 이유. 끝까지 None이면 통과
        if len(canonicals) > 1:  # ② 카드 두 개 이상이 같은 별칭을 만든 경우
            reason = "정식명 여러 개를 가리킴"  # 가정 예: {"한빛가게모음", "가게모음"} → 어느 카드인지 모름
        elif len(alias.replace(" ", "")) < ALIAS_MIN_LENGTH:  # ③ 띄어쓰기를 뺀 길이가 3글자 미만
            reason = "두 글자 이하"  # 가정 예: "한빛 S" 카드의 별칭 "s" → 다른 낱말에 너무 쉽게 걸림
        elif _is_common_noun(base_kiwi, alias):  # ① 기본 사전에 일반명사로 있음
            reason = "일반 명사와 겹침"  # 예: "대중교통카드" → "대중교통"이 일반명사라 걸러짐
        if reason is not None:  # 걸러진 후보는 버리지 않고 사람이 검수할 목록에 이유와 함께 남김
            # 예: {"alias": "대중교통카드", "canonical": "한빛대중교통", "reason": "일반 명사와 겹침"}
            review.append({"alias": alias, "canonical": sorted(canonicals)[0], "reason": reason})
            continue
        canonical = sorted(canonicals)[0]  # 통과했으면 정식명이 1개뿐임. 예: "한빛가게모음"
        if canonical not in aliases:  # 예: 이 정식명의 첫 별칭이면 빈 목록부터 만듦
            aliases[canonical] = []
        aliases[canonical].append(alias)  # 예: aliases["한빛가게모음"] = [..., "가게모음카드"]
        # 모두 돌고 나면 예: aliases["한빛가게모음"] = ["가게모음", "가게모음 카드", "가게모음카드", "한빛 가게모음", "한빛 가게모음 카드", "한빛 가게모음카드"]

    # 사람 검수 승인분 추가. 위 걸러내기에 걸렸어도 사람이 "카드 고유 이름이 맞다"고 승인한 별칭은 되살림
    # 아래 주석의 예시는 aliases_approved.json의 "한빛수소길": ["수소길", "수소길카드", "수소길 카드"]를 따라감
    if approved is not None:  # 인자를 안 넘기면 None이라 건너뜀(파일이 없을 때 index_docs는 빈 dict를 넘겨 반복 0회)
        for canonical, extra_aliases in approved.items():  # 예: canonical = "한빛수소길", extra_aliases = ["수소길", ...]
            # 예: "한빛수소길"은 "한빛 수소길" 등 3개가 이미 통과해 칸이 있음. 후보가 모두 걸린 카드면 여기서 빈 칸을 만듦
            if canonical not in aliases:
                aliases[canonical] = []
            for alias in extra_aliases:  # 예: alias = "수소길카드"일 때
                alias = alias.strip().lower()  # 사람이 적은 값이라 앞뒤 공백과 대소문자를 위 규칙과 맞춤
                if alias not in aliases[canonical]:  # 이미 있는 별칭은 두 번 넣지 않음
                    aliases[canonical].append(alias)  # 예: aliases["한빛수소길"] = [..., "수소길카드"]
    return aliases, review


def build_alias_lookup(aliases: dict) -> dict:
    """별칭 사전을 뒤집어 역방향 대응표 {별칭: 정식명}을 만듦. 정식명 자신도 넣어 치환 뒤 중복 정리가 한 규칙으로 됨."""
    alias_to_name = {}
    for canonical, alias_list in aliases.items():
        alias_to_name[canonical] = canonical
        for alias in alias_list:
            alias_to_name[alias] = canonical
    return alias_to_name


def load_bm25_index(index_dir: Path) -> tuple:
    """build_bm25_index가 저장한 색인과 chunk_id 순서를 다시 읽음. 검색기와 색인 검증이 씀.

    반환값: (bm25s.BM25 객체, chunk_id 목록) 쌍. 색인의 i번째 문서 점수가 chunk_id 목록의 i번째 청크 점수임.
    """
    retriever = bm25s.BM25.load(str(index_dir), load_corpus=False, show_progress=False)
    with open(index_dir / CHUNK_IDS_FILE, "r", encoding="utf-8") as file:
        chunk_ids = json.load(file)
    return retriever, chunk_ids


# ---------------------------------------------------------------------------
# BM25 색인 핵심 함수 1. 카드 사용자 사전
# ---------------------------------------------------------------------------
def build_tokenizer(card_names: list[str], aliases: dict) -> Kiwi:
    """Kiwi 형태소 분석기를 만들고 카드 정식명과 별칭을 고유명사(NNP)로 등록함(교재 130쪽 "카드명 사용자 사전").

    목적: "모아생활"을 등록하지 않으면 Kiwi가 "모으/VV + 어 + 생활"로 쪼개 BM25가 카드명을 못 맞춤(실측).
    방법: 카드명 원문(소문자), 정식명(canonical_card_name), 별칭 사전의 모든 별칭을 add_user_word로 등록함.
          띄어 쓴 이름("한빛 모아생활")도 등록하면 Kiwi가 한 토큰으로 잡음(실측).
    인자: card_names는 메타데이터 card_name 값의 집합. aliases는 make_alias_table이 돌려준 {정식명: [별칭, ...]}.
    반환값: 사용자 단어가 등록된 Kiwi 객체. 색인과 질문 양쪽에 같은 객체를 씀.
    """
    kiwi = Kiwi()
    for card_name in card_names:
        kiwi.add_user_word(card_name.strip().lower(), "NNP")
        kiwi.add_user_word(canonical_card_name(card_name), "NNP")
    for alias_list in aliases.values():
        for alias in alias_list:
            kiwi.add_user_word(alias, "NNP")
    return kiwi


# ---------------------------------------------------------------------------
# BM25 색인 핵심 함수 2. 별칭 사전 치환
# ---------------------------------------------------------------------------
def apply_aliases(tokens: list[str], alias_to_name: dict) -> list[str]:
    """토큰 목록에서 별칭을 정식명으로 바꾸고, 같은 정식명이 여러 번 나오면 1개만 남김(교재 131쪽 ②, ③).

    목적: 문서의 "한빛 모아생활"과 질문의 "모아생활"이 같은 토큰 "한빛모아생활"이 되어야 BM25가 같은 단어로 셈.
    방법: 토큰마다 대응표에 있으면 정식명으로 바꿈. 정식명이 이미 나왔으면 건너뜀(한 문장에서 이름이 두 번 잡히는 경우).
          대응표에 없는 토큰은 그대로 둠(일반 단어의 반복 횟수는 BM25 점수에 그대로 반영됨).
    반환값: 치환과 중복 정리가 끝난 토큰 목록(순서 유지).
    예시: ["모아생활", "카드", "연회비"] → ["한빛모아생활", "카드", "연회비"]
    """
    result = []
    seen_names = set()
    for token in tokens:
        if token not in alias_to_name:
            result.append(token)
            continue
        canonical = alias_to_name[token]
        if canonical in seen_names:
            continue
        seen_names.add(canonical)
        result.append(canonical)
    return result


# ---------------------------------------------------------------------------
# BM25 색인 핵심 함수 3. Kiwi 토큰화
# ---------------------------------------------------------------------------
def tokenize_korean(kiwi: Kiwi, text: str, alias_to_name: dict) -> list[str]:
    """본문이나 질문을 BM25용 토큰 목록으로 바꿈(교재 130쪽 "한 문장이 색인 단어가 되기까지").

    목적: BM25는 "질문 토큰과 색인 토큰이 문자열로 같을 때만" 점수를 주므로 양쪽을 같은 규칙으로 잘라야 함.
    방법: ① 표기 통일(숫자 쉼표 제거, 소문자화) ② 코드(D2-C001 꼴)를 통째로 토큰에 추가
          ③ Kiwi 형태소 분석 뒤 내용어(CONTENT_TAGS)만 남김 ④ 별칭을 정식명으로 치환(apply_aliases).
    반환값: 토큰 문자열 목록. 내용어가 하나도 없으면 빈 목록임.
    예시: "모아생활 카드의 포인트" → ["한빛모아생활", "카드", "포인트"]
    """
    normalized = NUMBER_COMMA_PATTERN.sub("", text).lower()

    tokens = []
    for code in CODE_PATTERN.findall(normalized):
        tokens.append(code)
    for token in kiwi.tokenize(normalized):
        if token.tag in CONTENT_TAGS:
            tokens.append(token.form)
    return apply_aliases(tokens, alias_to_name)


# ---------------------------------------------------------------------------
# BM25 색인 핵심 함수 4. bm25s 점수표 생성과 저장(빈칸 채우기)
# ---------------------------------------------------------------------------
def build_bm25_index(chunk_tokens: list[list[str]], chunk_ids: list[str], index_dir: Path, k1: float, b: float) -> int:
    """청크 토큰 목록으로 bm25s 점수표를 미리 계산해 폴더에 저장하고, 청크 ID 순서를 함께 둠(교재 130쪽 ③, ④).

    목적: 낱말마다 "청크 안 빈도 × 전체 청크 중 희소성 × 청크 길이 보정"을 검색 전에 계산해 두면 질문 때는 더하기만 함.
    방법: BM25(k1, b, method="lucene")를 만들고 index(chunk_tokens)로 점수표를 계산한 뒤 save(index_dir)로 저장함.
          색인은 청크를 번호(0, 1, 2 ...)로만 알므로 chunk_ids를 같은 순서로 chunk_ids.json에 적어 둠.
    인자: k1은 한 청크 안에서 같은 단어가 반복될 때 점수가 더 오르는 정도, b는 긴 청크의 점수를 깎는 정도(교재 130쪽).
    반환값: 색인에 들어간 문서(청크) 수. chunk_ids 길이와 같아야 정상임.
    """
    retriever = bm25s.BM25(k1=k1, b=b, method=BM25_METHOD)
    
    # BM25 색인: 점수 포함
    # bm25s 색인 예시: "연회비" → [(청크 3, 2.1), (청크 17, 0.8), (청크 42, 1.5)] 
    retriever.index(chunk_tokens, show_progress=False)
    
    # BM25 색인 저장: 점수표와 chunk_id 순서를 index_dir에 둠
    index_dir.mkdir(parents=True, exist_ok=True)
    retriever.save(str(index_dir))
    with open(index_dir / CHUNK_IDS_FILE, "w", encoding="utf-8") as file:
        json.dump(chunk_ids, file, ensure_ascii=False, indent=2)
    return retriever.scores["num_docs"]
