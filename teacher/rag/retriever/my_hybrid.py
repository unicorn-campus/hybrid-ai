"""교육생용 뼈대: core_hybrid.py와 같은 이름·같은 인자의 함수 5개를 본인 코드로 채우는 파일임."""

# 사용법: 아래 함수를 채운 뒤 search_docs.py의 import 한 줄을 "import my_hybrid as hybrid"로 바꿈
#
# 클론 코딩 범위(교시 분량 기준)
#   직접 작성(핵심 2개): search_bm25, fuse_weighted
#   읽고 복사(3개): fuse_rrf, rerank, member_pseudonym — core_hybrid.py를 읽고 이해한 뒤 그대로 옮김
#   완성본 제공: 맨 위 상수와 fuse_weighted의 보조 함수 4개(_normalize_scores, _merge_hits, _build_fused_list,
#   _get_fused_score)는 아래에 완성된 채로 있으므로 그대로 씀
#   한국어 토크나이저(사용자 사전, 별칭 사전, Kiwi 토큰화)는 W3 인덱싱 뼈대(../indexing/my_indexing.py)에서 작성함.
#   검색기는 인덱서 모듈의 함수로 질문을 토큰화하므로 여기에는 없음
#
# 함수 하나를 채울 때마다 모드를 좁혀 확인함: --mode bm25 --no-answer → --mode hybrid --no-answer → 기본 모드

import hashlib

# ---------------------------------------------------------------------------
# 완성본 상수(core_hybrid.py와 같음)
# ---------------------------------------------------------------------------
RERANK_MODEL = "rerank-v4.0-fast"  # Cohere 리랭커 기본 모델명. main이 같은 이름의 상수를 넘겨 줌


# ---------------------------------------------------------------------------
# 직접 작성(핵심 1): search_bm25
# ---------------------------------------------------------------------------
def search_bm25(bm25, chunks: list[dict], query_tokens: list[str], top_n: int, weight_mask=None) -> list[dict]:
    """BM25 점수가 높은 청크를 top_n개까지 돌려줌.

    인자: bm25는 인덱서가 chunks와 같은 순서로 저장한 bm25s 색인. weight_mask는 청크마다 1 또는 0인 권한 마스크(없으면 None).
    반환값: {"chunk_id", "text", "metadata", "score", "rank"} 목록(점수 내림차순). 점수 0인 청크는 뺌.
    """
    # 할 일 1: bm25.get_scores(query_tokens, weight_mask=weight_mask)로 청크마다 점수를 받음(순서는 chunks와 같음)
    # 할 일 2: (점수, 순번) 쌍을 목록에 모으되 점수 0은 버림(질문 토큰이 없거나 권한 밖인 청크)
    # 할 일 3: 목록.sort(reverse=True) — (점수, 순번) 쌍은 점수부터 비교되므로 점수 내림차순이 됨
    # 할 일 4: 앞 top_n개를 for rank, (score, index) in enumerate(..., start=1) 꼴로 돌며(쌍을 두 변수로 푸는 문법)
    #          {"chunk_id", "text", "metadata", "score", "rank"} dict로 만들어 목록에 담음. 점수는 float(...)로 바꿈
    raise NotImplementedError("여기에 본인 코드를 작성함")


# ---------------------------------------------------------------------------
# 완성본 제공: fuse_weighted의 보조 함수 4개(core_hybrid.py와 같음)
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# 직접 작성(핵심 2): fuse_weighted — 합산 루프만 쓰면 됨
# ---------------------------------------------------------------------------
def fuse_weighted(
    vector_hits: list[dict],
    bm25_hits: list[dict],
    vector_weight: float = 0.6,
    bm25_weight: float = 0.4,
) -> list[dict]:
    """벡터·BM25 점수를 각각 0 ~ 1로 정규화한 뒤 가중합으로 합침.

    반환값: {"chunk_id", "text", "metadata", "fused_score", "found_in", "rank"} 목록(점수 내림차순).
    """
    # 할 일 1: vector_normalized = _normalize_scores(vector_hits), bm25_normalized = _normalize_scores(bm25_hits)
    # 할 일 2: merged = _merge_hits(vector_hits, bm25_hits)
    # 할 일 3: merged의 chunk_id마다 fused_scores[chunk_id] = vector_weight × 벡터 정규화 점수 + bm25_weight × BM25 정규화 점수
    #          (한쪽 목록에 없는 chunk_id는 그쪽 점수를 0으로 봄)
    # 할 일 4: return _build_fused_list(merged, fused_scores)
    raise NotImplementedError("여기에 본인 코드를 작성함")


# ---------------------------------------------------------------------------
# 읽고 복사: fuse_rrf, rerank, member_pseudonym
# ---------------------------------------------------------------------------
def fuse_rrf(vector_hits: list[dict], bm25_hits: list[dict], k: int = 60) -> list[dict]:
    """벡터·BM25 결과를 RRF(순위의 역수 합)로 합침.

    반환값: fuse_weighted와 같은 꼴. fused_score = Σ 1 / (k + 순위).
    """
    # 할 일 1: merged = _merge_hits(vector_hits, bm25_hits), fused_scores는 chunk_id마다 0.0으로 시작
    # 할 일 2: vector_hits의 항목마다 fused_scores[chunk_id]에 1 / (k + hit["rank"])를 더함. bm25_hits도 같게
    # 할 일 3: return _build_fused_list(merged, fused_scores)
    raise NotImplementedError("여기에 본인 코드를 작성함")


def rerank(
    question: str,
    candidates: list[dict],
    cohere_client,
    top_k: int,
    model_name: str = RERANK_MODEL,
) -> list[dict]:
    """Cohere 리랭커로 후보를 다시 채점해 상위 top_k개를 돌려줌.

    인자: candidates는 fuse_* 결과처럼 "text"·"rank" 키를 가진 목록. cohere_client는 cohere.ClientV2 객체임.
    반환값: 후보 항목에 "rerank_score"·"fused_rank"(리랭크 전 순위)·"rank"를 더한 목록. 점수 내림차순 top_k개.
    """
    # 할 일 1: 후보가 비어 있으면 빈 목록을 돌려줌(API를 부르지 않음)
    # 할 일 2: 후보의 "text"만 모아 cohere_client.rerank(model=model_name, query=question, documents=..., top_n=top_k) 호출
    # 할 일 3: 응답 response.results의 각 항목에서 index(입력 순번)와 relevance_score를 읽음
    # 할 일 4: dict(candidates[index])로 복사해 fused_rank(원래 rank), rerank_score, 새 rank(1부터)를 넣어 목록에 담음
    raise NotImplementedError("여기에 본인 코드를 작성함")


def member_pseudonym(member_id: str) -> str:
    """회원번호를 되돌릴 수 없는 가명 ID로 바꿈(인덱서와 같은 식).

    반환값: "m_" + 16자리 문자열. 예: "M-1042" → "m_59853c3d8e1e3c25"
    """
    # 할 일 1: hashlib.sha256(member_id.encode("utf-8")).hexdigest()의 앞 16자리를 구함
    # 할 일 2: 앞에 "m_"를 붙여 돌려줌. 인덱서·평가셋이 같은 식을 쓰므로 식을 바꾸면 회원 필터가 어긋남
    raise NotImplementedError("여기에 본인 코드를 작성함")
