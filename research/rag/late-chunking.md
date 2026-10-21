# Late Chunking 심층 조사

작성: 지식니(지식과 데이터 엔지니어), 확인 일자 2026-10-22  
용도: 수강생 설명용 PPT 1장의 근거 문서

## 1. 한눈에 보기
- 정의: 문서 전체를 먼저 모델에 통과시켜 토큰 벡터를 얻고, 그 뒤 청크 구간별로 평균을 냄 (Jina AI, 블로그 2024.8, 논문 2024.9)
- 조건: 추가 학습 없음, 평균 풀링 방식의 긴 문맥(8192토큰) 임베딩 모델 필요
- 효과: BEIR 4개 데이터셋 평균 상대 +2.70 % 에서 +3.63 %. 문서가 길수록 이득이 큼
- 한계: 토큰 벡터를 주지 않는 API(Cohere 등)에는 적용 불가. 독립 비교 연구에서는 Contextual Retrieval이 더 높음
- 실습 적용: Jina API의 `late_chunking` 옵션 또는 jina-embeddings-v3 로컬 실행 (9절)

## 2. 문제: 청크가 문맥을 잃는 이유
- 청크를 따로 임베딩(글을 숫자 목록으로 바꾸는 일)하면 앞뒤 문장을 못 봐서 "its", "그 도시"가 무엇인지 모름
- 블로그 예시: 베를린 문서를 문장 단위로 자르면 "Its more than 3.85 million inhabitants..." 문장에 "Berlin"이 없어
  "What is the population of Berlin?" 질문에 잘 안 걸림
- 논문 표 1 ("Berlin"과의 코사인 유사도, 높을수록 가까움, jina-embeddings-v2-small)

| 청크 | 기존(naive) | Late |
|------|------------|------|
| Berlin is the capital and largest city... | 0.8486 | 0.8495 |
| Its more than 3.85 million inhabitants... | 0.7084 | 0.8249 |
| The city is also one of the states... | 0.7535 | 0.8498 |

## 3. 원리와 처리 절차
```
기존:  문서 -> 청크로 자름 -> 청크마다 모델 통과 -> 청크마다 평균 -> 벡터 N개   (청크끼리 서로 못 봄)
Late:  문서 전체 -> 모델 1회 통과 -> 토큰 벡터 m개 -> 청크 구간별 평균 -> 벡터 N개 (토큰이 문서 전체를 봄)
```
1. 기존 splitter로 청크 경계를 정함 (경계 단서는 여전히 필요, 쓰는 시점만 뒤로 밀림)
2. 문서 전체를 토큰화(모델이 글을 자르는 최소 단위)하고 토큰별 글자 위치(offset)를 기록
3. 글자 경계를 토큰 구간(시작, 끝)으로 변환 (논문 알고리즘 1, 5행에서 13행)
4. 모델을 한 번 통과시켜 토큰 벡터를 얻음
5. 구간별 평균 풀링(여러 벡터를 평균 내 하나로 합침) (알고리즘 1, 14행에서 16행)

- 문맥이 보존되는 이유: 임베딩 모델은 모든 토큰이 서로를 보는 구조라 각 토큰 벡터에 문서 전체 정보가 섞임.
  블로그 1편은 "앞 청크에 조건화"라 썼으나 2편이 "양방향"으로 바로잡음

## 4. 코드 핵심(경계 매핑과 풀링)
- 경계 매핑: `chunking.py`가 `tokenizer.encode_plus(text, return_offsets_mapping=True, add_special_tokens=False)`로
  토큰별 글자 위치를 얻어 청크를 토큰 번호 구간 `(start, end)`로 만듦. 의미 분할은 `bisect`로 글자 위치를 토큰 번호로 바꿈
- 풀링: `chunked_pooling()` (`chunked_pooling/__init__.py`) 핵심 발췌

```python
token_embeddings = model_output[0]                          # 문서 전체 토큰 벡터
pooled = embeddings[start:end].sum(dim=0) / (end - start)   # 청크 구간 평균
```

- 모델 최대 길이를 넘는 구간은 `max_length` 인자로 버림. 논문은 [CLS], [SEP], 지시문 토큰을 첫 청크와 마지막 청크 평균에 포함

## 5. 긴 문서 처리(long late chunking)
- 논문 v3(2025.7)에 long late chunking(3.1절, 알고리즘 2)과 학습 보강(span pooling, 3.2절)이 있음. v1과 v2 내용은 확인 못 함
- 문서가 모델 한도(8192)를 넘을 때: 큰 창(l_max 토큰)으로 나눠 각각 모델에 통과시키되 창끼리 일부 토큰을 겹쳐 문맥을 보충.
  겹친 앞부분 출력은 버리고 이어 붙인 뒤 같은 방식으로 풀링
- 공식 코드 `_embed_with_overlap`(`mteb_chunked_eval.py`): 창 이동 폭 = 창 크기 - 겹침(기본 겹침 512)
- 8192토큰 넘는 독서 이해 데이터셋 3개에서 naive보다 우수 (그림만 있어 수치는 미확인)

## 6. 실험 결과와 조건
- 조건: nDCG@10(상위 10개 결과의 순서 점수, 높을수록 좋음), 고정 256토큰 청크, 겹침 없음, BEIR(검색 평가 모음) 4개
- 논문 표 2, naive에서 late로 (%)

| 데이터셋 | jina-v2-small | jina-v3 | nomic-v1 |
|----------|---------------|---------|----------|
| SciFact | 64.2 에서 66.1 | 71.8 에서 73.2 | 70.7 에서 70.6 |
| NFCorpus | 23.5 에서 30.0 | 35.6 에서 36.7 | 35.3 에서 35.3 |
| FiQA | 33.3 에서 33.8 | 46.3 에서 47.6 | 37.0 에서 38.3 |
| TRECCOVID | 63.4 에서 64.7 | 73.0 에서 77.2 | 72.9 에서 75.0 |

- 3개 모델 평균 상대 향상: 고정 크기 +3.46 %, 문장 경계 +3.63 %, 의미 경계 +2.70 %
- 문서 길이와 이득(블로그 1편, jina-v2-small): 평균 1589자 NFCorpus +6.5점, 1498자 SciFact +1.9점, 767자 FiQA +0.6점,
  62자 Quora 변화 없음. 청크가 작을수록 이득이 크고, 겹쳐 자르기(16토큰)는 차이 없음 (부록 A.2)

## 7. 지원 모델과 API
- Jina API: 요청에 `late_chunking: true`. OpenAPI 명세(2026.10.13판)상 jina-embeddings-v3와 v4에만 있고 v2와 v5에는 없음.
  설명: "모든 입력을 이어 붙여 한 시퀀스로 처리한 뒤 나눔". v4는 텍스트만 가능
- 논문 실험 모델: jina-embeddings-v2-small(8192), v3, nomic-embed-text-v1
- 일반 조건(블로그 2편): 토큰 벡터 접근 가능, 8192 이상 긴 문맥, 기본 풀링이 평균. CLS나 max 풀링 모델은 부적합
- 로컬 실행: jina-embeddings-v3는 `trust_remote_code=True`, 최대 8192토큰, 라이선스 CC BY-NC 4.0(상업 이용은 문의).
  572M 파라미터, 약 2.13GB (독립 연구 표 1)

## 8. 한계와 독립 비교 결과
- 모델 문맥 길이와 메모리: 문서를 통째로 통과시키므로 길면 long late chunking 필요
- 효과가 작은 경우: 짧은 문서, 큰 청크, 필요 정보가 주변 글과 무관한 경우(논문의 Needle, Passkey 데이터셋)
- 1차 출처가 모두 Jina 측 자료임
- 독립 비교(arXiv 2504.19754, 볼로냐대, 2025.4): NFCorpus 20 % 부분집합, jina-v3, 고정 512토큰, 소형 LLM(Phi-3.5-mini 4비트)
  - Late 0.294 대 Contextual 0.308 (nDCG@10). 저자 결론: Contextual은 일관성이 좋으나 비용이 큼, Late는 효율적이나 관련성이 낮음
  - Contextual 쪽에 BM25 결합과 리랭커가 포함되어 순수 비교는 아님
  - 모델별 하락: BGE-M3 NFCorpus 0.225 에서 0.067, Stella-V5 MS MARCO 0.632 에서 0.505. 원인은 논문에서 확인 못 함

## 9. 실습 코드 적용 방법
- Cohere 불가 이유: embed API는 텍스트마다 최종 벡터 하나만 줌(블로그 2편의 "Single Output" 기준). 토큰 벡터가 없어 구간 평균을 못 냄
- 주의: 질문 벡터도 같은 모델로 만들어야 하고 기존 Cohere 인덱스와 섞을 수 없음. BM25와 청크 문장은 그대로 사용

방법 A, Jina API (한 호출에 한 문서의 청크만 넣음. "이어 붙여 처리"라는 명세 설명에서 나온 추정)

```python
import os, requests
def late_chunk_api(chunk_texts):   # 한 문서를 자른 청크 문자열 목록
    r = requests.post("https://api.jina.ai/v1/embeddings",
        headers={"Authorization": f"Bearer {os.environ['JINA_API_KEY']}"},
        json={"model": "jina-embeddings-v3", "task": "retrieval.passage",
              "late_chunking": True, "input": chunk_texts}, timeout=60)
    r.raise_for_status()
    return [d["embedding"] for d in r.json()["data"]]   # 청크 순서대로
```

방법 B, 로컬 jina-embeddings-v3 (공식 저장소 wrapper 방식, 모델 호출은 미실행)

```python
import torch
from transformers import AutoModel, AutoTokenizer
tok = AutoTokenizer.from_pretrained("jinaai/jina-embeddings-v3")
model = AutoModel.from_pretrained("jinaai/jina-embeddings-v3", trust_remote_code=True).eval()

def pool_spans(hidden, offsets, spans):      # spans: 청크별 (글자 시작, 글자 끝)
    out = []
    for cs, ce in spans:
        idx = [i for i, (s, e) in enumerate(offsets) if e > s and cs <= s < ce]  # 특수 토큰 제외
        v = hidden[idx[0]:idx[-1] + 1].mean(dim=0)
        out.append(torch.nn.functional.normalize(v, dim=0).numpy())
    return out

enc = tok(text, return_offsets_mapping=True, truncation=True, max_length=8192, return_tensors="pt")
offsets = enc.pop("offset_mapping")[0].tolist()
mask = torch.full((1,), model._adaptation_map["retrieval.passage"], dtype=torch.int32)
with torch.no_grad():
    hidden = model(**enc, adapter_mask=mask)[0][0]   # (토큰 수, 1024)
# spans는 RecursiveCharacterTextSplitter(add_start_index=True)의 start_index와 길이로 계산
```

Chroma 적재와 검색 (실습 코드의 `upsert` 그대로, 벡터 출처만 교체)

```python
col = client.get_or_create_collection("docs-late", metadata={"hnsw:space": "cosine"})
col.upsert(ids=ids, documents=texts, embeddings=[v.tolist() for v in vectors], metadatas=metas)
q = model.encode(["질문"], task="retrieval.query")   # 질문도 같은 모델
hits = col.query(query_embeddings=q.tolist(), n_results=5)
```

## 10. Contextual Retrieval과의 차이
- Contextual Retrieval(Anthropic, 2024.9)은 LLM이 청크마다 설명 문장을 써서 청크 앞에 붙인 뒤 임베딩함.
  실패율 49 % 감소, 리랭킹 병행 67 % 감소, 비용 문서 100만 토큰당 약 $1.02(프롬프트 캐싱 전제)로 발표
- Late Chunking은 LLM 호출과 추가 저장이 없음. 대신 토큰 벡터를 주는 긴 문맥 모델이 필요하고, 글자는 안 바뀌어 BM25에는 영향 없음(추정)

## 11. 2026년 확장 연구 (초록만 확인)
- Visual Late Chunking(arXiv 2604.10167): 이미지 문서의 패치 벡터를 군집으로 묶는 ColChunk. 저장량 90 % 이상 감소,
  nDCG@5 평균 +9점이라고 초록이 주장
- Graph-Aware Late Chunking(arXiv 2603.22633): 생의학 논문용 GraLC-RAG. late chunking에 구조 인식 경계와 지식그래프를 결합.
  구조 인식 방식은 최대 15.6배 많은 섹션에서 근거를 가져오나 MRR 최고는 내용 유사도 방식(0.517)

## 12. 출처 목록 (확인 일자 2026-10-22)

| 구분 | 출처 | URL |
|------|------|-----|
| 1차 | 논문 v3 (PDF 본문) | https://arxiv.org/abs/2409.04701 |
| 1차 | Jina 블로그 1편 (2024.8.22) | https://jina.ai/news/late-chunking-in-long-context-embedding-models/ |
| 1차 | Jina 블로그 2편 (2024.10.3) | https://jina.ai/news/what-late-chunking-really-is-and-what-its-not-part-ii/ |
| 1차 | GitHub 코드 | https://github.com/jina-ai/late-chunking |
| 1차 | Jina API OpenAPI 명세 | https://api.jina.ai/openapi.json |
| 1차 | jina-embeddings-v3 모델 카드 | https://huggingface.co/jinaai/jina-embeddings-v3 |
| 1차 | Anthropic Contextual Retrieval | https://www.anthropic.com/news/contextual-retrieval |
| 2차 | 독립 비교 연구 (본문) | https://arxiv.org/abs/2504.19754 |
| 2차 | Visual Late Chunking (초록) | https://arxiv.org/abs/2604.10167 |
| 2차 | Graph-Aware Late Chunking (초록) | https://arxiv.org/abs/2603.22633 |
| 2차 | Weaviate 블로그 (2024.9.5, 일부) | https://weaviate.io/blog/late-chunking |
| 2차 | voyage-context-3 문서 (Voyage AI, 2025.7) | https://docs.voyageai.com/docs/contextualized-chunk-embeddings |
| 2차 | voyage-context-4 발표 글 (Voyage AI, MongoDB, 2026.6) | https://mongodb.com/company/blog/product-release-announcements/voyage-context-4-stop-worrying-about-chunking-with-our-best-performing-model |

- Chroma `add` 인자와 sentence-transformers `output_value` 시그니처는 context7 문서 조회로 확인

## 13. 확인하지 못한 항목
- Jina 블로그 3편: 존재 확인 못 함 (1편과 2편의 읽기 순서 안내에 3편 없음)
- Jina API 웹 문서 페이지, late_chunking 사용 시 입력 총 토큰 한도 (명세만 확인)
- jina-embeddings-v4와 v5의 로컬 late chunking 가능 여부, v3의 지시문 접두어 처리, sentence-transformers 경로의 v3 동작
- 논문 그림 3과 4의 수치, Cohere 공식 문서 (전달받은 사실과 블로그 기준으로 서술)
- 코드 검증 범위: `pool_spans`와 Chroma 적재는 가짜 데이터로 로컬 실행해 확인. 실제 jina-v3 모델과 Jina API 호출은 미실행
