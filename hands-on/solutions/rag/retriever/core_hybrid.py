"""검색 핵심 모듈: 한국어 토크나이저, BM25 검색, 점수 융합 2종, Cohere 리랭크, 회원 가명 함수 7개(교육생 클론 코딩 대상)임."""

import hashlib
import re

from kiwipiepy import Kiwi

# BM25 색인에 남길 품사(Kiwi 태그). 조사·어미·기호는 어느 청크에나 있어 점수를 흐리므로 뺌
# NNG 일반명사, NNP 고유명사, NR 수사, SN 숫자, SL 알파벳, VV 동사 어간, VA 형용사 어간
CONTENT_TAGS = {"NNG", "NNP", "NR", "SN", "SL", "VV", "VA"}

# "D2-C001", "D2-C001-B01", "M-1042", "C-20260302-001" 같은 코드. Kiwi는 이런 코드를 "D", "2", "-", "C", "001"로
# 쪼개므로 코드 전체를 한 토큰으로 따로 뽑음. 색인과 질문에 같은 규칙을 쓰므로 양쪽 토큰이 같아짐
CODE_PATTERN = re.compile(r"[A-Za-z]+\d*-[A-Za-z]*\d+(?:-[A-Za-z]*\d+)*")
NUMBER_COMMA_PATTERN = re.compile(r"(?<=\d),(?=\d)")  # "3,000,000" 안의 쉼표. 질문은 "300만"처럼 쓰기도 해 숫자만 남김
CARD_NAME_PREFIX = "한빛 "  # 카드명 앞의 회사명. 교육생이 "모아생활 카드"처럼 회사명 없이 묻는 경우가 많음
RERANK_MODEL = "rerank-v4.0-fast"  # Cohere 리랭커 기본 모델명. main이 같은 이름의 상수를 넘겨 줌


def build_tokenizer(card_names: list[str]) -> Kiwi:
    """Kiwi 형태소 분석기를 만들고 카드명을 고유명사로 등록함.

    목적: "모아생활"을 등록하지 않으면 Kiwi가 "모으/VV + 어 + 생활"로 쪼개 BM25가 카드명을 못 맞춤(실측).
    방법: 카드명 그대로("한빛 모아생활")와 회사명을 뗀 이름("모아생활") 둘 다 NNP(고유명사)로 add_user_word 함.
          띄어 쓴 이름도 등록하면 Kiwi가 한 토큰으로 잡음(실측).
    인자: card_names는 chunks.json 메타데이터 card_name 값의 집합(중복 없는 목록)임.
    반환값: 사용자 단어가 등록된 Kiwi 객체. 색인과 질문 양쪽에 같은 객체를 씀.
    """
    kiwi = Kiwi()
    for card_name in card_names:
        kiwi.add_user_word(card_name, "NNP")
        if card_name.startswith(CARD_NAME_PREFIX):
            short_name = card_name[len(CARD_NAME_PREFIX):]
            kiwi.add_user_word(short_name, "NNP")
    return kiwi


def tokenize_korean(kiwi: Kiwi, text: str) -> list[str]:
    """본문이나 질문을 BM25용 토큰 목록으로 바꿈.

    목적: BM25는 "질문 토큰과 색인 토큰이 문자열로 같을 때만" 점수를 주므로 양쪽을 같은 규칙으로 잘라야 함.
    방법: ① 숫자 쉼표 제거·소문자화 ② 코드(D2-C001 꼴)를 통째로 토큰에 추가 ③ Kiwi 형태소 분석 뒤 내용어만 남김.
    반환값: 토큰 문자열 목록. 내용어가 하나도 없으면 빈 목록임.
    예시: "한빛 모아생활 카드의 포인트" → ["한빛 모아생활", "카드", "포인트"]
    """
    normalized = NUMBER_COMMA_PATTERN.sub("", text).lower()

    tokens = []
    for code in CODE_PATTERN.findall(normalized):
        tokens.append(code)

    for token in kiwi.tokenize(normalized):
        if token.tag in CONTENT_TAGS:
            tokens.append(token.form)
    return tokens


def search_bm25(bm25, chunks: list[dict], query_tokens: list[str], top_n: int) -> list[dict]:
    """BM25 점수가 높은 청크를 top_n개까지 돌려줌.

    목적: 조항 번호·카드 코드·고유명사처럼 "낱말이 그대로 있어야 찾는" 질문을 맡음(교재: Sparse 검색).
    방법: bm25.get_scores가 청크마다 점수 1개씩 돌려주므로(순서는 chunks와 같음) 점수 내림차순으로 정렬함.
    인자: bm25는 chunks를 같은 순서로 토큰화해 만든 BM25Okapi 객체임. 둘의 순서가 다르면 점수가 엉뚱한 청크에 붙음.
    반환값: {"chunk_id", "text", "metadata", "score", "rank"} 목록. 점수 0(질문 토큰이 하나도 없는 청크)은 뺌.
    """
    scores = bm25.get_scores(query_tokens)

    scored = []  # (점수, 청크 순번) 쌍
    for index in range(len(chunks)):
        score = float(scores[index])
        if score > 0:
            scored.append((score, index))
    scored.sort(reverse=True)  # (점수, 순번) 쌍은 점수부터 비교됨. reverse=True라 점수가 큰 것이 앞으로 옴

    hits = []
    for rank, (score, index) in enumerate(scored[:top_n], start=1):  # (score, index)는 쌍을 두 변수로 푸는 문법
        chunk = chunks[index]
        hits.append(
            {
                "chunk_id": chunk["chunk_id"],
                "text": chunk["text"],
                "metadata": chunk["metadata"],
                "score": score,
                "rank": rank,
            }
        )
    return hits


def _normalize_scores(hits: list[dict]) -> dict:
    """검색 결과의 점수를 최소-최대 정규화로 0 ~ 1 사이에 다시 펴서 {chunk_id: 정규화 점수}로 돌려줌.

    목적: 코사인 점수(0 ~ 1)와 BM25 점수(0 ~ 수십)는 범위가 달라 그대로 더하면 BM25가 결과를 좌우함(교재 154쪽).
    방법: (점수 - 최소) / (최대 - 최소). 모든 점수가 같으면(후보 1개 포함) 0으로 나눌 수 없어 전부 1.0으로 둠.
    """
    if len(hits) == 0:
        return {}

    scores = []
    for hit in hits:
        scores.append(hit["score"])
    lowest = min(scores)
    highest = max(scores)

    normalized = {}
    for hit in hits:
        if highest == lowest:
            normalized[hit["chunk_id"]] = 1.0
        else:
            normalized[hit["chunk_id"]] = (hit["score"] - lowest) / (highest - lowest)
    return normalized


def _merge_hits(vector_hits: list[dict], bm25_hits: list[dict]) -> dict:
    """두 검색 결과를 chunk_id로 묶어 {chunk_id: {"chunk": 청크, "found_in": [...]}} 표를 만듦."""
    merged = {}
    for hit in vector_hits:
        merged[hit["chunk_id"]] = {"chunk": hit, "found_in": ["vector"]}
    for hit in bm25_hits:
        if hit["chunk_id"] in merged:
            merged[hit["chunk_id"]]["found_in"].append("bm25")
        else:
            merged[hit["chunk_id"]] = {"chunk": hit, "found_in": ["bm25"]}
    return merged


def _build_fused_list(merged: dict, fused_scores: dict) -> list[dict]:
    """묶음 표와 융합 점수로 최종 목록을 만들고 fused_score 내림차순으로 순위(rank)를 매김."""
    fused = []
    for chunk_id, entry in merged.items():
        chunk = entry["chunk"]
        fused.append(
            {
                "chunk_id": chunk_id,
                "text": chunk["text"],
                "metadata": chunk["metadata"],
                "fused_score": fused_scores[chunk_id],
                "found_in": entry["found_in"],
            }
        )

    fused.sort(key=_get_fused_score, reverse=True)
    for rank, item in enumerate(fused, start=1):
        item["rank"] = rank
    return fused


def _get_fused_score(item: dict) -> float:
    """정렬 기준으로 쓸 융합 점수를 꺼냄(람다 대신 이름 있는 함수를 씀)."""
    return item["fused_score"]


def fuse_weighted(
    vector_hits: list[dict],
    bm25_hits: list[dict],
    vector_weight: float = 0.6,
    bm25_weight: float = 0.4,
) -> list[dict]:
    """벡터·BM25 점수를 각각 0 ~ 1로 정규화한 뒤 가중합으로 합침(교재 154쪽 "정규화 가중합").

    목적: 순위만 보는 RRF와 달리 점수 차이의 크기까지 반영함. 벡터 0.6 : BM25 0.4는 커리큘럼 4-2의 기본 비중임.
    방법: 한쪽 검색에만 있는 청크는 없는 쪽 점수를 0으로 봄. fused_score = 0.6 × 벡터 정규화 + 0.4 × BM25 정규화.
    반환값: {"chunk_id", "text", "metadata", "fused_score", "found_in", "rank"} 목록(점수 내림차순).
    """
    vector_normalized = _normalize_scores(vector_hits)
    bm25_normalized = _normalize_scores(bm25_hits)
    merged = _merge_hits(vector_hits, bm25_hits)

    fused_scores = {}
    for chunk_id in merged:
        vector_part = 0.0
        if chunk_id in vector_normalized:
            vector_part = vector_normalized[chunk_id]
        bm25_part = 0.0
        if chunk_id in bm25_normalized:
            bm25_part = bm25_normalized[chunk_id]
        fused_scores[chunk_id] = vector_weight * vector_part + bm25_weight * bm25_part

    return _build_fused_list(merged, fused_scores)


def fuse_rrf(vector_hits: list[dict], bm25_hits: list[dict], k: int = 60) -> list[dict]:
    """벡터·BM25 결과를 RRF(순위의 역수 합)로 합침(교재 154쪽 "RRF").

    목적: 점수 단위가 다른 두 검색을 "몇 점인지"는 버리고 "몇 등인지"만으로 공정하게 합침.
    방법: 청크마다 각 검색의 순위 r에 대해 1 / (k + r)을 더함. 한쪽에만 있으면 그쪽 값만 더해짐.
    인자: k=60은 RRF 논문 권장 상수. 클수록 1등과 2등의 점수 차이가 완만해짐.
    반환값: fuse_weighted와 같은 꼴. fused_score는 보통 0.03 안팎의 작은 값임.
    """
    merged = _merge_hits(vector_hits, bm25_hits)

    fused_scores = {}
    for chunk_id in merged:
        fused_scores[chunk_id] = 0.0
    for hit in vector_hits:
        fused_scores[hit["chunk_id"]] = fused_scores[hit["chunk_id"]] + 1.0 / (k + hit["rank"])
    for hit in bm25_hits:
        fused_scores[hit["chunk_id"]] = fused_scores[hit["chunk_id"]] + 1.0 / (k + hit["rank"])

    return _build_fused_list(merged, fused_scores)


def rerank(
    question: str,
    candidates: list[dict],
    cohere_client,
    top_k: int,
    model_name: str = RERANK_MODEL,
) -> list[dict]:
    """Cohere 리랭커로 후보를 다시 채점해 상위 top_k개를 돌려줌(교재 155쪽 "재정렬").

    목적: 1차 검색은 질문과 청크를 따로 벡터로 만들어 비교하지만, 리랭커는 질문과 청크를 한 쌍으로 읽어
          관련성을 더 정확히 매김. 후보가 많을수록 느리므로 융합 상위 몇 개에만 씀.
    방법: 후보 본문 목록을 API에 보내고, 응답의 index(입력 순번)와 relevance_score(0 ~ 1)로 후보를 다시 고름.
    인자: candidates는 fuse_* 결과처럼 "text" 키를 가진 목록. cohere_client는 cohere.ClientV2 객체임.
          model_name은 main의 RERANK_MODEL 상수를 넘겨받음(기본값은 같은 이름).
    반환값: 후보 항목에 "rerank_score"·"fused_rank"(리랭크 전 순위)·"rank"를 더한 목록. 점수 내림차순 top_k개.
    부수효과: Cohere API를 1번 호출함(네트워크·과금).
    """
    if len(candidates) == 0:
        return []

    documents = []
    for candidate in candidates:
        documents.append(candidate["text"])

    response = cohere_client.rerank(
        model=model_name,
        query=question,
        documents=documents,
        top_n=top_k,
    )

    reranked = []
    for rank, result in enumerate(response.results, start=1):
        candidate = dict(candidates[result.index])  # 원본을 바꾸지 않도록 복사함
        candidate["fused_rank"] = candidate["rank"]
        candidate["rerank_score"] = float(result.relevance_score)
        candidate["rank"] = rank
        reranked.append(candidate)
    return reranked


def member_pseudonym(member_id: str) -> str:
    """회원번호를 되돌릴 수 없는 가명 ID로 바꿈(인덱서 core_indexing.member_pseudonym과 같은 식).

    목적: 색인에는 회원번호가 없고 가명 ID만 있으므로, 검색기도 같은 식으로 가명 ID를 만들어 필터에 씀.
    반환값: "m_" + SHA-256 16진수 앞 16자리. 예: "M-1042" → "m_59853c3d8e1e3c25"
    """
    digest = hashlib.sha256(member_id.encode("utf-8")).hexdigest()
    return "m_" + digest[:16]
