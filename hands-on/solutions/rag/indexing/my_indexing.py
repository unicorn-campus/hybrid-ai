"""교육생용 뼈대: core_indexing.py와 같은 이름·같은 인자의 핵심 함수 8개를 본인 코드로 채우는 파일임.

채우는 순서(쉬운 것부터). "직접"은 NotImplementedError 자리에 본인 코드를 쓰고, "빈칸"은 거의 완성된 코드의 빈칸만 채움
  [벡터 색인: 정제 → 청킹 → 임베딩 → 적재]
  1 chunk_document      (핵심, 직접) 분할기 만들기
  2 clean_document      (핵심, 직접) 제공된 보조 함수(clean_page_text, mask_private_info)를 순서대로 부르기
  3 embed_chunks        (핵심, 빈칸 2곳) 배치 슬라이싱, 벡터 이어 붙이기
  4 store_chunks        (핵심, 빈칸 2곳) 배치 슬라이싱, collection.add 인자
  [BM25 색인: 사전 → 토큰화 → 점수표]
  5 build_tokenizer     (핵심, 직접) 카드 사용자 사전. Kiwi에 정식명과 별칭을 고유명사로 등록
  6 apply_aliases       (핵심, 직접) 별칭 사전 치환. 별칭 → 정식명, 같은 정식명은 1개만
  7 tokenize_korean     (핵심, 직접) Kiwi 토큰화. 표기 통일 → 코드 추출 → 내용어 선택 → 별칭 치환
  8 build_bm25_index    (핵심, 빈칸 3곳) BM25(k1, b, method), index(), save()
  제공(완성본, 읽기만): 보조 함수 4개(find_repeated_lines, clean_page_text, mask_private_info, member_pseudonym)와
                       별칭 규칙 함수(canonical_card_name, make_alias_table, build_alias_lookup), load_bm25_index
"""

# 사용법: 아래 함수를 채운 뒤 index_docs.py의 import 한 줄을 "import my_indexing as indexing"으로 바꿈.
#         검색기(retriever/search_docs.py)도 같은 모듈로 질문을 토큰화해야 하므로 그쪽 import도 my_indexing으로 바꿈
# 정규식, 상수, 보조 함수는 학습 목표가 아니므로 완성본을 그대로 줌. 교육생은 이것들을 "쓰는" 핵심 함수만 작성함
# 임베딩(3)은 API를 부르므로 먼저 "--limit 8"로 실행해 호출 횟수가 적을 때 맞는지 확인한 뒤 전체를 돌림

import hashlib
import json
import re
from pathlib import Path

import bm25s
import chromadb
from kiwipiepy import Kiwi
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

# BM25 색인 상수(교재 130 ~ 131쪽)
CONTENT_TAGS = {"NNG", "NNP", "NR", "SN", "SL", "VV", "VA"}  # 색인에 남길 품사. 조사·어미·기호는 뺌
CODE_PATTERN = re.compile(r"[A-Za-z]+\d*-[A-Za-z]*\d+(?:-[A-Za-z]*\d+)*")  # D2-C001, M-1042 같은 코드를 통째로 잡음
NUMBER_COMMA_PATTERN = re.compile(r"(?<=\d),(?=\d)")  # "3,000,000" 안의 쉼표
CARD_NAME_PREFIX = "한빛 "  # 카드명 앞의 회사명
CARD_WORD = "카드"  # 별칭에 붙이는 말
ALIAS_MIN_LENGTH = 3  # 두 글자 이하 별칭은 걸러냄
BM25_METHOD = "lucene"  # bm25s 점수 공식
CHUNK_IDS_FILE = "chunk_ids.json"  # 색인 폴더 안의 청크 ID 순서 파일


# ---------------------------------------------------------------------------
# 벡터 색인 보조 함수 4개(완성본 제공, 읽기만): 정제와 가명처리의 부품. 핵심 함수가 안에서 부름
# ---------------------------------------------------------------------------
def find_repeated_lines(pages: list[str], min_pages: int = 2) -> set[str]:
    """여러 쪽에 반복되는 머리말·꼬리말 줄을 찾음.

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

    방법: PRIVATE_PATTERNS를 적힌 순서대로 정규식 치환하고, 마지막에 "만 35세"를 "30대"로 바꿈.
    반환값: 치환된 본문. 예: "제 이름은 가상고객0001입니다" → "제 이름은 [고객]입니다"
    """
    masked_text = text
    for pattern, replacement in PRIVATE_PATTERNS:
        masked_text = pattern.sub(replacement, masked_text)
    masked_text = AGE_PATTERN.sub(_age_to_decade, masked_text)
    return masked_text


def member_pseudonym(member_id: str) -> str:
    """회원번호를 되돌릴 수 없는 가명 ID로 바꿈.

    방법: SHA-256 해시의 16진수 앞 16자리에 "m_"을 붙임. 검색기·평가셋과 같은 식이어야 회원 필터가 맞음.
    반환값: "m_" + 16자리 문자열. 예: "M-1042" → "m_59853c3d8e1e3c25"
    """
    digest = hashlib.sha256(member_id.encode("utf-8")).hexdigest()
    return "m_" + digest[:16]


# ---------------------------------------------------------------------------
# 벡터 색인 핵심 함수 1. 정제
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
# 벡터 색인 핵심 함수 2. 청킹
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
    # 할 일 3: splitter.create_documents(texts=[text], metadatas=[metadata])의 결과를 그대로 돌려줌
    raise NotImplementedError("여기에 본인 코드를 작성함")


# ---------------------------------------------------------------------------
# 벡터 색인 핵심 함수 3. 임베딩 (빈칸 채우기)
# ---------------------------------------------------------------------------
def embed_chunks(texts: list[str], embeddings, batch_size: int) -> tuple[list[list[float]], int]:
    """청크 본문 목록을 배치로 나눠 임베딩 API에 보내고, 입력 순서 그대로 벡터 목록을 만듦.

    인자: embeddings는 embed_documents(list[str]) -> list[list[float]] 메서드를 가진 객체(main이 만듦).
    반환값: (벡터 목록, API 호출 횟수). 벡터 목록의 i번째는 texts의 i번째 본문의 벡터임.
    """
    vectors = []
    api_calls = 0
    for start in range(0, len(texts), batch_size):  # range(시작, 끝, 간격)
        batch_texts = None  # 빈칸 1: texts에서 start부터 batch_size개를 슬라이싱해 넣음
        if batch_texts is None:
            raise NotImplementedError("빈칸 1을 채울 것")
        batch_vectors = embeddings.embed_documents(batch_texts)
        # 빈칸 2: batch_vectors를 vectors 뒤에 이어 붙임(append가 아니라 목록을 통째로 잇는 메서드)
        raise NotImplementedError("빈칸 2를 채우고 이 줄을 지울 것")
        api_calls = api_calls + 1
    return vectors, api_calls


# ---------------------------------------------------------------------------
# 벡터 색인 핵심 함수 4. 적재 (빈칸 채우기)
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

    인자: chunks는 {"chunk_id", "text", "metadata"} dict 목록. vectors는 chunks와 길이·순서가 같아야 함.
    반환값: collection에 저장된 건수.
    """
    client = chromadb.PersistentClient(path=str(chroma_dir))
    collection = client.get_or_create_collection(name=collection_name, metadata=collection_metadata)
    for start in range(0, len(chunks), batch_size):  # range(시작, 끝, 간격)
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

    return collection.count()


# ---------------------------------------------------------------------------
# BM25 색인 제공 함수(읽기만). 별칭 후보 생성과 걸러내기는 문자열 규칙이라 BM25 이해와 무관함
# ---------------------------------------------------------------------------
def canonical_card_name(card_name: str) -> str:
    """카드명을 정식명 토큰으로 바꿈. 소문자로 통일하고, 끝의 "카드"를 떼고, 띄어쓰기를 없앰. "한빛 모아생활" → "한빛모아생활"."""
    name = card_name.strip().lower()
    if name.endswith(CARD_WORD):
        name = name[: -len(CARD_WORD)]
    return name.replace(" ", "")


def _is_common_noun(base_kiwi: Kiwi, alias: str) -> bool:
    """별칭이 Kiwi 기본 사전에 일반명사로 통째로 있는지 봄(걸러내기 ① "일반 명사와 겹침")."""
    core = alias.replace(" ", "")
    if core.endswith(CARD_WORD):
        core = core[: -len(CARD_WORD)]
    tokens = list(base_kiwi.tokenize(core))
    return len(tokens) == 1 and tokens[0].tag == "NNG"


def make_alias_table(card_names: list[str], approved: dict | None = None) -> tuple[dict, list[dict]]:
    """정식명 목록에서 별칭 후보를 규칙으로 만들고 위험한 후보를 걸러 별칭 사전을 만듦(교재 131쪽 ①).

    방법: 후보 = {원래 이름, 접두어 뗀 이름, 띄어쓰기 없앤 이름} × {그대로, "카드" 붙임, " 카드" 붙임}.
          걸러내기 ① 일반 명사와 겹침 ② 정식명 여러 개를 가리킴 ③ 두 글자 이하. approved(사람 검수 승인분)는 그대로 추가함.
    반환값: (별칭 사전 {정식명: [별칭, ...]}, 검수 목록 [{"alias", "canonical", "reason"}, ...]) 쌍.
    """
    base_kiwi = Kiwi()  # 사용자 사전이 없는 기본 분석기. 걸러내기 ①에만 씀
    candidates = {}  # 별칭 → 그 별칭이 가리키는 정식명 집합
    for card_name in card_names:
        canonical = canonical_card_name(card_name)
        full_name = card_name.strip().lower()
        short_name = full_name
        if full_name.startswith(CARD_NAME_PREFIX):
            short_name = full_name[len(CARD_NAME_PREFIX):]
        base_forms = {full_name, short_name, short_name.replace(" ", "")}
        forms = set()
        for form in base_forms:
            forms.add(form)
            forms.add(form + CARD_WORD)
            forms.add(form + " " + CARD_WORD)
        forms.discard(canonical)  # 정식명 자체는 별칭이 아님
        for alias in forms:
            if alias not in candidates:
                candidates[alias] = set()
            candidates[alias].add(canonical)

    aliases = {}
    review = []
    for alias in sorted(candidates):
        canonicals = candidates[alias]
        reason = None
        if len(canonicals) > 1:
            reason = "정식명 여러 개를 가리킴"
        elif len(alias.replace(" ", "")) < ALIAS_MIN_LENGTH:
            reason = "두 글자 이하"
        elif _is_common_noun(base_kiwi, alias):
            reason = "일반 명사와 겹침"
        if reason is not None:
            review.append({"alias": alias, "canonical": sorted(canonicals)[0], "reason": reason})
            continue
        canonical = sorted(canonicals)[0]
        if canonical not in aliases:
            aliases[canonical] = []
        aliases[canonical].append(alias)

    if approved is not None:
        for canonical, extra_aliases in approved.items():
            if canonical not in aliases:
                aliases[canonical] = []
            for alias in extra_aliases:
                alias = alias.strip().lower()
                if alias not in aliases[canonical]:
                    aliases[canonical].append(alias)
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
    """build_bm25_index가 저장한 색인과 chunk_id 순서를 다시 읽음. (bm25s.BM25 객체, chunk_id 목록) 쌍을 돌려줌."""
    retriever = bm25s.BM25.load(str(index_dir), load_corpus=False, show_progress=False)
    with open(index_dir / CHUNK_IDS_FILE, "r", encoding="utf-8") as file:
        chunk_ids = json.load(file)
    return retriever, chunk_ids


# ---------------------------------------------------------------------------
# BM25 색인 핵심 함수 1. 카드 사용자 사전 (직접 작성)
# ---------------------------------------------------------------------------
def build_tokenizer(card_names: list[str], aliases: dict) -> Kiwi:
    """Kiwi 형태소 분석기를 만들고 카드 정식명과 별칭을 고유명사(NNP)로 등록함(교재 130쪽 "카드명 사용자 사전").

    인자: card_names는 카드명 목록("한빛 모아생활" 꼴). aliases는 make_alias_table이 돌려준 {정식명: [별칭, ...]}.
    반환값: 사용자 단어가 등록된 Kiwi 객체. 색인과 질문 양쪽에 같은 객체를 씀.
    """
    # 할 일 1: Kiwi() 객체를 만듦
    # 할 일 2: 카드명마다 소문자 원문(card_name.strip().lower())과 정식명(canonical_card_name)을 add_user_word(단어, "NNP")로 등록
    # 할 일 3: aliases.values()의 모든 별칭도 같은 방법으로 등록
    # 할 일 4: Kiwi 객체를 돌려줌
    raise NotImplementedError("여기에 본인 코드를 작성함")


# ---------------------------------------------------------------------------
# BM25 색인 핵심 함수 2. 별칭 사전 치환 (직접 작성)
# ---------------------------------------------------------------------------
def apply_aliases(tokens: list[str], alias_to_name: dict) -> list[str]:
    """토큰 목록에서 별칭을 정식명으로 바꾸고, 같은 정식명이 여러 번 나오면 1개만 남김(교재 131쪽 ②, ③).

    인자: alias_to_name은 build_alias_lookup이 만든 {별칭: 정식명} 대응표(정식명 자신도 들어 있음).
    반환값: 치환과 중복 정리가 끝난 토큰 목록(순서 유지). 예: ["모아생활", "카드"] → ["한빛모아생활", "카드"]
    """
    # 할 일 1: 결과 목록과 "이미 나온 정식명" 집합을 빈 상태로 만듦
    # 할 일 2: 토큰마다 대응표에 없으면 그대로 결과에 넣음
    # 할 일 3: 대응표에 있으면 정식명으로 바꾸되, 이미 나온 정식명이면 건너뛰고 아니면 집합에 넣고 결과에 넣음
    # 할 일 4: 결과 목록을 돌려줌
    raise NotImplementedError("여기에 본인 코드를 작성함")


# ---------------------------------------------------------------------------
# BM25 색인 핵심 함수 3. Kiwi 토큰화 (직접 작성)
# ---------------------------------------------------------------------------
def tokenize_korean(kiwi: Kiwi, text: str, alias_to_name: dict) -> list[str]:
    """본문이나 질문을 BM25용 토큰 목록으로 바꿈(교재 130쪽 "한 문장이 색인 단어가 되기까지").

    반환값: 토큰 문자열 목록. 예: "모아생활 카드의 포인트" → ["한빛모아생활", "카드", "포인트"]
    """
    # 할 일 1: 표기 통일 — NUMBER_COMMA_PATTERN.sub("", text)로 숫자 쉼표를 지우고 .lower()로 소문자화
    # 할 일 2: CODE_PATTERN.findall(통일한 글)로 찾은 코드를 토큰 목록에 먼저 넣음
    # 할 일 3: kiwi.tokenize(통일한 글)의 토큰 중 token.tag가 CONTENT_TAGS에 있는 것만 token.form을 넣음
    # 할 일 4: apply_aliases(토큰 목록, alias_to_name)의 결과를 돌려줌
    raise NotImplementedError("여기에 본인 코드를 작성함")


# ---------------------------------------------------------------------------
# BM25 색인 핵심 함수 4. bm25s 점수표 생성과 저장 (빈칸 채우기)
# ---------------------------------------------------------------------------
def build_bm25_index(chunk_tokens: list[list[str]], chunk_ids: list[str], index_dir: Path, k1: float, b: float) -> int:
    """청크 토큰 목록으로 bm25s 점수표를 미리 계산해 폴더에 저장하고, 청크 ID 순서를 함께 둠(교재 130쪽 ③, ④).

    인자: k1은 한 청크 안에서 같은 단어가 반복될 때 점수가 더 오르는 정도, b는 긴 청크의 점수를 깎는 정도.
    반환값: 색인에 들어간 문서(청크) 수.
    """
    retriever = None  # 빈칸 1: bm25s.BM25(k1=..., b=..., method=BM25_METHOD)로 색인 객체를 만듦
    if retriever is None:
        raise NotImplementedError("빈칸 1을 채울 것")
    # 빈칸 2: retriever.index(...)에 chunk_tokens를 넘겨 점수표를 계산함(show_progress=False를 함께 넘기면 조용함)
    raise NotImplementedError("빈칸 2를 채우고 이 줄을 지울 것")
    index_dir.mkdir(parents=True, exist_ok=True)
    # 빈칸 3: retriever.save(...)로 index_dir에 저장함(경로는 str(index_dir)로 넘김)
    raise NotImplementedError("빈칸 3을 채우고 이 줄을 지울 것")
    with open(index_dir / CHUNK_IDS_FILE, "w", encoding="utf-8") as file:
        json.dump(chunk_ids, file, ensure_ascii=False, indent=2)
    return retriever.scores["num_docs"]
