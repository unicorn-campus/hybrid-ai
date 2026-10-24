"""검색엔진 인덱싱 서브 워크플로우.

준비 prepare(): S1 임베딩(바뀐 것만) → S2 키워드 분석(카드명 사전과 별칭). 결과는 돌려주기만 하고 검색엔진에는 쓰지 않음
반영 apply():   S3 적재(검색엔진에 문서 단위로 지우고 넣기)
정리: 없음(문서 단위로 지우고 넣어서 옛 청크가 남지 않음)

검색엔진 인덱스는 세대마다 하나(card_chunks-{세대 ID})이고 별칭은 쓰지 않음. 검색기는 활성 세대 파일을 읽고 인덱스를 고름.
"""

from __future__ import annotations

from opensearchpy import OpenSearch, helpers

import config
import lexical  # 이 저장소 RAG 인덱싱 예제와 같은 토큰화 규칙, 카드명 사전과 별칭 규칙(색인 쪽과 질문 쪽이 같아야 함)
from common import doc_id_of, embed, index_text_of, log, sha256_text

META_FIELDS = ("doc_key", "doc_type", "access_level", "source", "card_id", "card_name", "product_id",
               "benefit_id", "record_id", "channel", "topic", "member_pseudo_id")


def client() -> OpenSearch:
    return OpenSearch(hosts=[config.OPENSEARCH_URL], timeout=60, max_retries=3, retry_on_timeout=True)


def index_name(generation: str) -> str:
    return f"{config.INDEX_PREFIX}-{generation}"


# ---------------------------------------------------------------- S2에 쓰는 토크나이저

def build_tokenizer(chunks: list[dict]) -> tuple[lexical.Lexicon, dict]:
    """혜택 안내 청크의 카드명으로 카드명 사전과 별칭 사전을 만들고 토크나이저를 만듦(RAG 인덱싱 예제와 같은 규칙).

    반환: (토크나이저, 검색 쪽이 같은 토크나이저를 다시 만들 수 있는 사전 기록)
    """

    lex = lexical.lexicon_from_chunks(chunks, lexical.load_approved_aliases(config.ALIASES_APPROVED))
    return lex, lex.meta()


def tokenizer_from_meta(meta: dict) -> lexical.Lexicon:
    """기록된 사전으로 같은 토크나이저를 다시 만듦(증분 색인이나 검색 쪽에서 씀)."""

    return lexical.lexicon_from_meta(meta)


# ---------------------------------------------------------------- 준비: S1, S2

def _old_vectors(os_client: OpenSearch, index: str | None) -> dict[str, list[float]]:
    """앞 세대 인덱스에서 {본문 해시: 벡터}를 읽음. 본문이 같으면 다시 임베딩하지 않으려고 씀(v0는 통째로 읽음)."""

    if not index or not os_client.indices.exists(index=index):
        return {}
    out = {}
    for hit in helpers.scan(os_client, index=index, query={"_source": ["text_hash", "embedding"]}):
        out.setdefault(hit["_source"]["text_hash"], hit["_source"]["embedding"])
    return out


def prepare(chunks: list[dict], previous_index: str | None = None, tokenizer_meta: dict | None = None) -> dict:
    """S1 ~ S2. 검색엔진에 넣을 문서(청크 하나 = 한 건)를 만들어 돌려줌. 검색엔진에는 쓰지 않음.

    tokenizer_meta: 증분 색인처럼 활성 세대의 사전을 그대로 써야 할 때 넘김. 없으면 이번 청크로 사전을 만듦.
    """

    os_client = client()
    old = _old_vectors(os_client, previous_index)
    hashes = [sha256_text(index_text_of(c)) for c in chunks]
    todo = [i for i, h in enumerate(hashes) if h not in old]
    fresh = embed([index_text_of(chunks[i]) for i in todo])  # S1: 바뀐 청크만 임베딩
    vectors = {hashes[i]: v for i, v in zip(todo, fresh)}
    log(f"[S1] 임베딩 {len(todo)}개, 앞 세대 벡터 재사용 {len(chunks) - len(todo)}개")

    if tokenizer_meta:
        tokenizer, meta = tokenizer_from_meta(tokenizer_meta), tokenizer_meta
    else:
        tokenizer, meta = build_tokenizer(chunks)
    tokens = tokenizer.tokenize_many([index_text_of(c) for c in chunks])  # S2: 키워드 분석
    log(f"[S2] 키워드 분석 {len(chunks)}개 (카드명 사전 {len(meta['card_names'])}개, 별칭 {sum(len(v) for v in meta['aliases'].values())}개)")

    docs = []
    for c, h, toks in zip(chunks, hashes, tokens):
        doc = {"chunk_id": c["chunk_id"], "doc_id": doc_id_of(c["chunk_id"]), "text_hash": h, "text": c["text"],
               "text_tokens": " ".join(toks), "embedding": vectors.get(h) or old[h]}
        doc.update({k: str(c["metadata"][k]) for k in META_FIELDS if c["metadata"].get(k) not in (None, "")})
        docs.append(doc)
    return {"docs": docs, "tokenizer": meta}


# ---------------------------------------------------------------- 반영: S3

def _mapping(tokenizer_meta: dict) -> dict:
    """벡터(kNN)와 키워드(BM25, k1 1.5)를 한 인덱스에 둠. 사전 기록은 _meta에 남겨 검색 쪽이 같은 토크나이저를 만들게 함."""

    keyword = {name: {"type": "keyword"} for name in META_FIELDS}
    return {
        "settings": {"index": {"knn": True, "number_of_shards": 1, "number_of_replicas": 0,
                               "similarity": {"bm25_v0": {"type": "BM25", "k1": config.BM25_K1, "b": config.BM25_B}}}},
        "mappings": {
            "_meta": {"tokenizer": tokenizer_meta},
            "properties": {
                "chunk_id": {"type": "keyword"}, "doc_id": {"type": "keyword"}, "text_hash": {"type": "keyword"},
                "text": {"type": "text", "index": False},
                "text_tokens": {"type": "text", "analyzer": "whitespace", "similarity": "bm25_v0"},
                "embedding": {"type": "knn_vector", "dimension": config.EMBED_DIMENSION,
                              "method": {"name": "hnsw", "engine": "lucene", "space_type": "cosinesimil"}},
                **keyword}}}


def apply(index: str, prepared: dict, delete_doc_ids: list[str] | None = None) -> dict:
    """S3. 문서(doc_id)마다 옛 청크를 지우고 새 청크를 한꺼번에 넣음. 청크 수가 줄어도 고아 청크가 남지 않음.

    delete_doc_ids: 새 입력에 아예 없는 문서(사라진 문서)의 청크도 지울 때 넘김.
    """

    os_client = client()
    if not os_client.indices.exists(index=index):
        os_client.indices.create(index=index, body=_mapping(prepared["tokenizer"]))
    docs = prepared["docs"]
    doc_ids = sorted({d["doc_id"] for d in docs} | set(delete_doc_ids or []))
    deleted = 0
    for doc_id in doc_ids:
        r = os_client.delete_by_query(index=index, body={"query": {"term": {"doc_id": doc_id}}},
                                      refresh=True, conflicts="proceed")
        deleted += int(r.get("deleted", 0))
    helpers.bulk(os_client, [{"_index": index, "_id": d["chunk_id"], "_source": d} for d in docs], max_retries=3)
    os_client.indices.refresh(index=index)
    log(f"[S3] 적재: 문서 {len(doc_ids)}개, 옛 청크 {deleted}건 지우고 {len(docs)}건 넣음")
    return {"deleted": deleted, "indexed": len(docs), "documents": len(doc_ids)}


def chunk_ids(index: str) -> set[str]:
    """④ 검증용: 인덱스에 들어 있는 청크 ID 전체."""

    os_client = client()
    if not os_client.indices.exists(index=index):
        return set()
    return {h["_source"]["chunk_id"] for h in helpers.scan(os_client, index=index, query={"_source": ["chunk_id"]})}


def tokenizer_meta_of(index: str) -> dict:
    """활성 세대 인덱스에 기록된 사전(증분 색인에서 같은 토크나이저를 쓰려고 읽음)."""

    m = client().indices.get_mapping(index=index)[index]["mappings"]
    return m["_meta"]["tokenizer"]
