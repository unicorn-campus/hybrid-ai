# 넓은 의미의 RAG 최신 트렌드 조사 (2026년 10월)

- 작성: hybrid-ai 교육팀 (총괄 클로니, 조사 지식니)  
- 작성일: 2026-10-21  
- 범위: "정보 검색으로 LLM 답변 품질을 높이는 모든 방법"을 넓은 의미의 RAG로 보고,  
  벡터 검색, BM25, 하이브리드, 그래프 검색, 온톨로지, NL2SQL, 에이전틱 검색, 평가까지 다룸  
- 조사 방법: 세 갈래로 나눠 WebSearch 68회(영어 50회, 한국어 16회, 보강 2회) 수행, 공식 원문 15건은  
  `curl`로 `.temp/`에 저장해 수치와 날짜를 직접 확인함  
- 독자: 하이브리드 AI 아키텍처를 배우는 개발자(중급). 용어는 처음 나올 때 괄호로 풀어 씀  
- 표기 원칙: 수치는 출처가 있는 것만 적음. 벤더 자체 발표는 "벤더 발표", 블로그 경유는 "2차 자료",  
  원문에서 확인하지 못한 것은 "출처 미확인"으로 구분함. 출처는 `[출처: URL]` 형식으로 표기함  
- 짝 자료: 요약 슬라이드 `rag-trends-2026.pptx` (각 슬라이드가 이 문서의 해당 섹션으로 연결됨)

---

## 1. 한눈에 보기

2026년의 RAG는 "문서를 잘라 임베딩하고 비슷한 조각을 찾는 기술"에서 벗어나,  
**질문에 맞는 지식 경로(벡터, 키워드, SQL, 그래프)를 고르고, LLM이 검색을 도구로 반복 호출하며,  
결과를 평가셋과 실행 추적으로 관리하는 체계**로 넓어졌음.

| 분야 | 한 줄 결론 | 상세 |
|------|-----------|------|
| 벡터 검색 | LLM 기반 대형 임베딩이 상위권, 인프라는 PostgreSQL 안(pgvector)과 서버리스(LanceDB) 두 갈래 | [3절](#3-벡터-검색과-임베딩) |
| BM25 | 정확 일치 문서에서 여전히 강함. 한국어는 형태소 분석기가 곧 품질 | [4절](#4-bm25와-희소-검색) |
| 하이브리드와 리랭킹 | "BM25 + 벡터 + RRF + 리랭커"가 사실상 기본값 | [5절](#5-하이브리드-검색과-리랭킹) |
| 청킹과 쿼리 변환 | "자르고 나서 문맥을 되살리는" 기법(Contextual Retrieval, late chunking)이 표준 옵션 | [6절](#6-청킹-인덱싱-쿼리-변환) |
| 그래프 검색 | 전부 대신 보완. 비용을 줄인 LazyGraphRAG, HippoRAG 2, EffiRAG 계열로 이동 | [7절](#7-그래프-검색-graphrag) |
| 온톨로지 | 무거운 OWL 대신 "가벼운 스키마 + 시맨틱 레이어"로 돌아옴 | [8절](#8-온톨로지와-지식그래프) |
| NL2SQL | 벤치마크는 사람 대비 약 10점 차. 실무 정확도는 모델보다 메트릭 정의가 올림 | [9절](#9-nl2sql과-시맨틱-레이어) |
| 에이전틱 RAG | 검색이 "파이프라인 단계"에서 "루프 안의 도구"로 바뀜. 딥 리서치가 대표 사례 | [10절](#10-에이전틱-rag와-딥-리서치) |
| 컨텍스트 엔지니어링 | 긴 문맥은 RAG의 대체가 아니라 라우팅 대상. 문맥은 유한 자원 | [11절](#11-컨텍스트-엔지니어링과-긴-문맥-논쟁) |
| 평가와 관측 | 자사 평가셋과 실행 추적 없이는 에이전트형 검색을 관리할 수 없음 | [12절](#12-rag-평가와-관측) |
| 라우팅 | 벡터, 키워드, SQL, 그래프를 질문 유형별로 고르는 라우터가 아키텍처의 앞단이 됨 | [13절](#13-멀티-소스-라우팅-아키텍처) |

---

## 2. 큰 흐름 7가지

1. **하이브리드 + 리랭킹이 기본 구성이 됨.** Anthropic 실험(임베딩 + BM25 > 임베딩 단독, 리랭킹 효과 누적),  
   SemEval-2026 참가 시스템, 주요 벡터DB의 네이티브 하이브리드 지원이 같은 방향을 가리킴  
   [출처: https://www.anthropic.com/news/contextual-retrieval] [출처: https://arxiv.org/pdf/2606.28352]
2. **검색이 "단계"에서 "도구"로 바뀜.** NL2SQL의 탐색-실행-수정 루프, 에이전틱 RAG, 딥 리서치, Anthropic의 적시 검색이  
   모두 LLM이 검색을 반복 호출하는 구조임  
   [출처: https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents]
3. **모델보다 "정의된 지식"이 정확도를 올림.** 시맨틱 레이어, 메트릭 정의, 지식그래프, 잘 쓴 메타데이터가  
   NL2SQL과 검색 벤치마크에서 가장 큰 이득을 냄  
   [출처: https://docs.getdbt.com/blog/semantic-layer-vs-text-to-sql-2026?version=2]
4. **그래프와 긴 문맥은 대체가 아니라 보완임.** 단순 사실형은 벡터 RAG, 전체 요약과 다중 홉은 그래프,  
   문서 간 종합은 긴 문맥으로 보내는 라우팅이 권고됨  
   [출처: https://arxiv.org/abs/2506.05690] [출처: https://proceedings.mlr.press/v267/li25dv.html]
5. **비용이 설계 기준이 됨.** 인덱싱 때 LLM 호출을 줄이는 지연 구축(LazyGraphRAG), 소형 리랭커 미세조정,  
   멀티벡터 압축, MCP 도구 정의의 점진 공개가 같은 동기에서 나옴  
   [출처: https://www.microsoft.com/en-us/research/blog/lazygraphrag/] [출처: https://arxiv.org/pdf/2608.09650]
6. **"자르고 나서 문맥을 되살리는" 색인이 표준 옵션이 됨.** Contextual Retrieval, late chunking,  
   구조 보존 파싱(Docling)이 서로 보완함  
   [출처: https://jina.ai/news/late-chunking-in-long-context-embedding-models/]
7. **벤더 수치는 독립 재현이 필요함.** 그래프 메모리 독립 평가에서 RAG보다 20%p 이상 낮게 나온 사례처럼,  
   자사 데이터와 공개 벤치마크로 다시 재야 함 [출처: https://arxiv.org/abs/2601.07978]

---

## 3. 벡터 검색과 임베딩

### 핵심 개념
- 임베딩(embedding)은 문장을 숫자 벡터로 바꾸는 기술임. 뜻이 비슷하면 벡터 거리도 가까움  
- 벡터 검색은 질문 벡터와 가장 가까운 문서 벡터를 찾는 일이며, 전부 비교하면 느리므로 ANN(근사 최근접 탐색) 색인을 씀  
- HNSW(그래프형 색인)는 메모리에 올려 빠르고, DiskANN은 SSD에 두고도 빠르게 찾도록 설계됨

### 왜 지금 주목받는가
- 2025년 이후 주류가 "작은 BERT 계열 인코더"에서 "LLM을 기반으로 학습한 대형 임베딩"으로 이동함.  
  Qwen3-Embedding-8B는 논문 자체 표 기준 MTEB(eng, v2) 평균 75.22점을 보고함 [출처: https://arxiv.org/pdf/2506.05176]  
- Google이 2026-03-10 Gemini Embedding 2를 공개함. 텍스트, 이미지, 영상, 오디오, PDF를 하나의 벡터 공간에 넣는  
  네이티브 멀티모달 임베딩임 [출처: https://blog.google/innovation-and-ai/models-and-research/gemini-models/gemini-embedding-2/]  
- MTEB 리더보드가 영어 v2와 다국어(MMTEB)로 재편되어 과거 점수와 직접 비교가 어려워짐 (2차 자료)  
  [출처: https://app.ailog.fr/en/blog/news/rag-benchmark-mteb-2026]

### 대표 기법과 도구
| 기법 또는 모델 | 발표 주체, 시기 | 요점 |
|---|---|---|
| Qwen3-Embedding (0.6B, 4B, 8B) | Alibaba Qwen, 2025-06 | LLM 기반, Apache 2.0, 리랭커도 함께 공개 [출처: https://arxiv.org/pdf/2506.05176] |
| Gemini Embedding 2 | Google, 2026-03 | 네이티브 멀티모달, 텍스트 8192 토큰 입력 |
| Matryoshka 임베딩(MRL) | 여러 벤더 | 벡터 앞부분만 잘라 써도 성능이 유지되게 학습. 저장 비용 절감 (2차 자료) [출처: https://www.premai.io/blog/best-embedding-models-for-rag-2026-ranked-by-mteb-score-cost-and-self-hosting/] |
| jina-embeddings-v3, v4 | Jina AI, 2024 ~ 2025 | 8192 토큰 긴 문맥, late chunking 옵션 [출처: https://jina.ai/news/late-chunking-in-long-context-embedding-models/] |
| KURE-v1, v2 | 고려대 NLP&AI Lab | 한국어 검색 특화. bge-m3를 한국어 약 200만 쌍으로 미세조정 [출처: https://github.com/nlpai-lab/KURE] |
| pgvector 0.8.0 | 2024-10 | 필터가 걸린 ANN 질의가 너무 적게 반환되는 문제를 반복 색인 스캔으로 해결 [출처: https://www.thenile.dev/blog/pgvector-080] |
| pgvectorscale | Timescale | DiskANN 기반 StreamingDiskANN 색인과 통계적 이진 양자화를 pgvector 위에 추가 (2차 자료) [출처: https://rivestack.io/blog/pgvector-vs-pgvectorscale] |
| LanceDB | LanceDB | Lance 컬럼 포맷으로 오브젝트 스토리지 위에서 서버 없이 동작 (2차 자료) [출처: https://www.firecrawl.dev/blog/best-vector-databases] |

### 한국어 관점
- KURE 저장소 리더보드(자체 공개)에서 MTEB-ko-retrieval 평균 nDCG@10은 KURE-v2 0.8160, Qwen3-Embedding-8B 0.7826,  
  bge-m3 0.7509로 보고됨. 독립 검증 수치는 아님 [출처: https://github.com/nlpai-lab/KURE]  
- 한국어 공공문서 시각 검색 벤치마크(SDS KoPub VDR)가 2025-11 공개됨 [출처: https://arxiv.org/pdf/2511.04910]

### 실무 적용 팁과 한계
- 팁: 리더보드 점수보다 "내 도메인 평가셋"이 우선임. 한국어 검색이 핵심이면 KURE 계열, 다국어와 긴 문맥이면 Qwen3,  
  dense와 sparse를 한 모델로 뽑고 싶으면 bge-m3를 후보로 두고 직접 비교함  
- 팁: 수천만 벡터 이하이고 이미 PostgreSQL을 쓰면 pgvector(필요 시 pgvectorscale)로 시작하는 흐름이 일반적임 (2차 자료)  
  [출처: https://www.actian.com/blog/developer/state-of-vector-databases-q2-2026/]  
- 팁: 양자화(int8, binary)는 저장 공간을 크게 줄이는 대신 재현율이 떨어지므로 리랭킹 단계를 함께 둠  
  [출처: https://aws.amazon.com/blogs/database/scale-pgvector-with-binary-quantization-on-amazon-aurora-postgresql/]  
- 한계: 8B급 임베딩은 추론 비용이 큼. "LLM 임베딩이 더 좋지만 비용이 얼마인가"를 다룬 논문이 2026년에 나옴  
  [출처: https://arxiv.org/pdf/2608.12875]  
- 한계: 벤더 벤치마크는 하드웨어와 양자화 조건이 달라 그대로 믿기 어려움. 자체 데이터로 재현율과 p95 지연을 재야 함

---

## 4. BM25와 희소 검색

### 핵심 개념
- BM25는 단어가 문서에 얼마나 자주 나오고(TF) 전체에서 얼마나 드문지(IDF)로 점수를 매기는 고전 검색 방식임  
- 희소 검색(sparse retrieval)은 "단어 ID → 가중치"처럼 대부분이 0인 벡터로 문서를 표현함.  
  SPLADE 같은 학습형 희소 검색은 신경망이 단어 가중치와 확장 단어를 학습함

### 왜 2026년에도 BM25가 중요한가
- 금융 텍스트와 표 문서 벤치마크(2026)에서 BM25가 text-embedding-3-large를 Recall@20을 제외한 모든 지표에서 앞섬  
  [출처: https://arxiv.org/html/2604.01733v1]  
- 임베딩만 쓰면 고유명사, 코드, 제품번호 같은 정확 일치 질의에 약함. Anthropic 실험에서도 "임베딩 + BM25"가  
  임베딩 단독보다 낫다는 결론이 명시됨 [출처: https://www.anthropic.com/news/contextual-retrieval]  
- 희소 검색은 어휘 정확성, 설명 가능성, 운영 효율을 함께 가짐  
  [출처: https://huggingface.co/blog/yjoonjang/the-past-and-present-of-sparse-retrieval]

### 대표 기법과 도구
| 기법 | 주체, 시기 | 요점 |
|---|---|---|
| BM25S | Xing Han Lù(McGill, Mila), 2024-07 | 색인 시점에 점수를 미리 계산해 희소 행렬로 저장. 기존 파이썬 BM25 대비 최대 500배 빠르다고 보고 [출처: https://arxiv.org/abs/2407.03618v1] |
| SPLADE 계열 | Naver Labs Europe 외 | BEIR 대부분에서 BM25를 앞서지만 GPU 추론이 필요하고 사전 밖 토큰(제품 코드)에 약함 (2차 자료) [출처: https://suhasbhairav.com/blog/splade-vs-bm25-learned-sparse-retrieval-vs-traditional-keyword-scoring] |
| PROSPER | 2025 | LLM 기반 희소 검색기. 상품 검색에서 BM25 대비 재현율 10.2% 개선 보고 [출처: https://staff.fnwi.uva.nl/m.derijke/wp-content/papercite-data/pdf/song-2025-llms-arxiv.pdf] |
| OpenSearch | OpenSearch | BM25, Nori 형태소 분석기, kNN, RRF 융합을 엔진 기능으로 제공 [출처: https://github.com/mindexxo/rag-agent/issues/139] |

### 한국어 형태소와 BM25
- 한국어는 조사와 어미가 붙어 공백 분리만으로는 "검색이", "검색을"이 다른 단어가 됨. Kiwi 같은 형태소 분석기로  
  어간을 뽑아 BM25에 넣으면 재현율이 올라감 [출처: https://wikidocs.net/251980]  
- 소규모 실측(문서 16개, 질의 20개)에서 공백 BM25는 Top3 정답 11/15, Kiwi BM25는 15/15였음. 다만 dense와 결합한  
  하이브리드는 Kiwi 여부와 무관하게 15/15라 "하이브리드가 토크나이저 차이를 흡수"하는 경향이 보임  
  [출처: https://github.com/AI-HealthCare-05/AH_05_06/pull/341]

### 실무 적용 팁과 한계
- 팁: BM25로 시작하고, 말바꿈(paraphrase) 불일치가 심한 코퍼스에서만 SPLADE나 dense를 더함  
- 팁: 한국어 BM25는 토크나이저가 곧 품질임. 형태소 분석기 버전을 고정하고, 바꿀 때 재색인함  
- 한계: BM25, SPLADE, BM25S를 여러 RAG 벤치마크에서 중립적으로 비교한 2025년 대규모 연구는 찾지 못함

---

## 5. 하이브리드 검색과 리랭킹

### 핵심 개념
- 하이브리드 검색은 BM25(단어 일치)와 벡터 검색(뜻 유사)을 함께 돌려 결과를 합치는 방식임  
- RRF(Reciprocal Rank Fusion, 역순위 융합)는 각 검색기의 "순위"만 보고 1/(k + 순위)를 더해 합침.  
  점수 단위가 달라도 정규화가 필요 없음 [출처: https://redis.io/blog/reciprocal-rank-fusion/]  
- 리랭킹(reranking)은 1차 검색이 뽑은 후보 수십 ~ 수백 개를 더 정밀한 모델로 다시 줄 세우는 단계임.  
  크로스 인코더는 질문과 문서를 한 번에 입력해 관련도를 내고, LLM 리랭커는 LLM에 후보 목록을 주고 순서를 매기게 함

### 왜 지금 주목받는가
- Anthropic 실험: Contextual Embedding + Contextual BM25에 리랭킹을 더하면 상위 20개 검색 실패율이  
  5.7%에서 1.9%로 67% 줄었음 [출처: https://www.anthropic.com/news/contextual-retrieval]  
- 주요 벡터DB(Weaviate, Milvus, Qdrant, LanceDB, Pinecone)가 하이브리드를 네이티브로 내장함 (2차 자료)  
  [출처: https://www.firecrawl.dev/blog/best-vector-databases]  
- SemEval-2026 Task 8(다중 턴 RAG) 참가 시스템도 하이브리드 검색 + RRF + 크로스 인코더 리랭커 구성을 사용함  
  [출처: https://arxiv.org/pdf/2606.28352]

### 융합 전략 비교
| 전략 | 장점 | 단점 |
|---|---|---|
| RRF (k=60이 관례) | 설정 없이 동작, 점수 정규화 불필요 | 1위 점수가 0.99인지 0.51인지 구분 못 함 [출처: https://blog.serghei.pl/posts/reciprocal-rank-fusion-explained/] |
| 가중 합성(정규화 점수 + alpha) | 레이블 질의가 있으면 RRF보다 나을 수 있음 | min-max 정규화가 짧은 목록에 불안정 [출처: https://bigdataboutique.com/blog/hybrid-search-fusion-methods-compared] |
| 학습형 융합 | 대규모에서 개선 주장 (수치 출처 미확인) | 학습 데이터 필요 |

- Weaviate는 v1.24부터 기본 융합을 RRF에서 상대 점수 융합(relativeScoreFusion)으로 바꿈  
  [출처: https://weaviate.io/developers/weaviate/concepts/search/hybrid-search]  
- "Top-K는 하이브리드의 예산이 아니다"라는 2026년 논문은 검색기별 후보 수 배분을 다시 봐야 한다고 주장함  
  [출처: https://arxiv.org/pdf/2609.15143]

### 리랭커 동향
- Qwen3-Reranker(2025-06)처럼 임베딩과 리랭커를 한 가족으로 공개하는 흐름이 생김 [출처: https://arxiv.org/pdf/2506.05176]  
- BEIR 일부 데이터셋 3자 측정(2차 자료): Jina reranker-v3.5 0.492, Cohere rerank-v3.5 0.486, Qwen3-Reranker-0.6B 0.478,  
  BGE reranker v2-m3 0.471 (평균 nDCG@10). Cohere가 p50 지연 192ms로 가장 빨랐음 [출처: https://hevmind.com/writing/jev-as-a-reranker/]  
- 크로스 인코더 vs LLM 리랭커 실측(2차 자료): bge-v2-m3로 상위 100개 리랭킹 시 p50 약 140ms, gpt-4o-mini로 상위 50개 시  
  약 700ms. nDCG@10은 0.71 대 0.72로 차이가 작았음  
  [출처: https://dev.to/gabrielanhaia/rerankers-and-the-latency-budget-when-cross-encoders-are-worth-it-3efc]  
- 의료 시술 리랭킹 연구(2026): 미세조정한 109M 크로스 인코더가 프롬프트 최적화한 4B Qwen3 리랭커를 앞섰고 CPU에서 동작함  
  [출처: https://arxiv.org/pdf/2608.09650]  
- FIRST: listwise LLM 리랭킹에서 첫 토큰 로짓만 써서 속도를 올리는 기법 [출처: https://arxiv.org/pdf/2406.15657]

### 실무 적용 팁과 한계
- 팁: 기본은 RRF(k 약 60) + 리랭커로 시작하고, 레이블 질의 50개 이상이 모이면 가중 합성을 측정해 교체함 (2차 자료)  
  [출처: https://dev.to/gabrielanhaia/hybrid-retrieval-fusion-rrf-vs-weighted-vs-learned-when-each-wins-26i1]  
- 팁: 융합 방식 차이보다 리랭커 유무가 결과에 더 큰 영향을 주는 경우가 많음  
  [출처: https://bigdataboutique.com/blog/hybrid-search-fusion-methods-compared]  
- 팁: 자체 호스팅 기본값은 bge-reranker-v2-m3, 오픈 가중치 최고 성능 후보는 Qwen3-Reranker, 관리형은 Cohere 또는 Voyage (2차 자료)  
  [출처: https://futureagi.com/blog/best-rerankers-for-rag-2026/]  
- 팁: listwise LLM 리랭커는 가장 정확하지만 가장 느리고 비싸므로 어려운 질의에만 3단계로 둠 (2차 자료)  
  [출처: https://dataaspirant.com/blog/reranking/]  
- 한계: 크로스 인코더 비용은 후보 수에 비례함. Anthropic도 "더 많이 리랭킹하면 품질, 적게 하면 지연과 비용"의  
  트레이드오프를 명시하고 실험으로 균형점을 찾으라고 권함 [출처: https://www.anthropic.com/news/contextual-retrieval]  
- 한계: 모델 라이선스가 자료마다 다르게 적혀 있으므로 모델 카드로 직접 확인해야 함 (출처 미확인)

---

## 6. 청킹, 인덱싱, 쿼리 변환

### 핵심 개념
- 청킹(chunking)은 긴 문서를 검색 단위로 자르는 일임. 잘못 자르면 "이 매출이 어느 회사 것인지" 같은 문맥이 사라짐  
- 쿼리 변환은 사용자의 짧은 질문과 문서의 긴 설명 사이 어휘 차이를 줄이려고 검색 전에 질문을 고쳐 쓰는 기법임  
- 후기 상호작용(late interaction)은 토큰(또는 이미지 패치)마다 벡터를 남겨 두고 질의 토큰별 최대 유사도를 더함(MaxSim)

### 왜 지금 주목받는가
- Anthropic Contextual Retrieval(2024-09): 각 청크 앞에 LLM이 만든 짧은 문맥 설명을 붙인 뒤 임베딩과 BM25 색인을 만듦.  
  Contextual Embedding 단독으로 검색 실패율 35% 감소(5.7% → 3.7%), Contextual BM25까지 합치면 49% 감소(→ 2.9%),  
  리랭킹까지 더하면 67% 감소(→ 1.9%). 문맥 생성 비용은 프롬프트 캐싱 기준 문서 100만 토큰당 약 1.02달러  
  [출처: https://www.anthropic.com/news/contextual-retrieval]  
- 2025 ~ 2026년에 청킹 전략을 체계 비교하는 논문이 여럿 나와 "청킹이 검색 품질의 독립 변수"로 자리 잡음  
  [출처: https://arxiv.org/pdf/2504.19754] [출처: https://arxiv.org/pdf/2603.25333]  
- ColPali(ICLR 2025)는 PDF를 OCR 없이 페이지 이미지째 다중 벡터로 임베딩해 기존 문서 검색 파이프라인을 크게 앞섬  
  [출처: https://proceedings.iclr.cc/paper_files/paper/2025/file/99e9e141aafc314f76b0ca3dd66898b3-Paper-Conference.pdf]

### 청킹과 인덱싱 기법
| 기법 | 주체, 시기 | 요점 |
|---|---|---|
| Contextual Retrieval | Anthropic, 2024-09 | 청크별 문맥 문장 생성 후 임베딩과 BM25 |
| Late chunking | Jina AI, 2024-09 | 문서 전체를 먼저 토큰 임베딩하고 "그 뒤에" 청크 단위로 풀링. 추가 학습 불필요 [출처: https://arxiv.org/html/2409.04701v1] |
| RAPTOR | 2024 | 청크를 재귀 군집화하고 요약해 트리를 만들어 긴 문서와 섹션 간 추론에 유리 [출처: https://atlan.com/know/advanced-rag-techniques/] |
| Docling HybridChunker | IBM | 문서 구조(제목, 표, 절) 기반 계층 청킹. 표와 바운딩 박스 메타데이터를 보존해 인용에 유리 [출처: https://docling.org/] |
| 적응형 청킹 | 2026 | 문서 특성에 따라 청킹 방법을 자동 선택 [출처: https://arxiv.org/pdf/2603.25333] |

- Late chunking과 Contextual Retrieval 비교(2025): Contextual Retrieval은 의미 일관성이 높지만 계산 비용이 크고,  
  late chunking은 효율이 높지만 관련성과 완전성이 떨어지는 경향 [출처: https://arxiv.org/pdf/2504.19754]

### 멀티벡터와 멀티모달 검색
| 기법 | 주체, 시기 | 요점 |
|---|---|---|
| ColBERTv2 | Stanford | 토큰 임베딩을 센트로이드로 군집화하고 잔차를 양자화하는 압축 [출처: https://huggingface.co/colbert-ir/colbertv2.0] |
| ColPali, ColQwen | ICLR 2025 이후 | 문서 이미지를 그대로 다중 벡터로 검색. ColQwen3-4B가 ViDoRe 최고 성능 보고 (2차 자료) [출처: https://www.emergentmind.com/topics/light-colpali-colqwen2] |
| PyLate | LightOn, 2025-08 | Sentence Transformers 위에서 멀티벡터 모델 학습과 검색 지원 [출처: https://arxiv.org/pdf/2508.03555] |
| GTE-ModernColBERT | LightOn, 2025-04 | 8000 토큰 문서 지원. Qdrant, LanceDB, Weaviate, Vespa 연동 [출처: https://lighton.ai/lighton-blogs/lighton-releases-gte-moderncolbert-first-state-of-the-art-late-interaction-model-trained-on-pylate] |

- 저장 공간이 큼. 같은 문단 집합에 대해 dense 색인 15.0MB 대 멀티벡터 311.5MB, 압축 시 92MB로 보고됨  
  [출처: https://huggingface.co/blog/multi-vector-encoder]. 압축 연구(MarginMerge, AnchorFold)가 2026년에 이어짐  
  [출처: https://arxiv.org/pdf/2608.02969] [출처: https://arxiv.org/pdf/2608.08732]

### 쿼리 변환 기법
| 기법 | 동작 | 적합한 질문 |
|---|---|---|
| HyDE | 가상의 답을 생성해 그 답을 임베딩으로 검색 | 용어 격차가 큰 문서 [출처: https://fareedkhan-dev.github.io/rag-cookbook-2026/theory/query-transformation/] |
| Multi-query | N개 바꿔 쓰기 → 각각 검색 → RRF 융합 | 표현이 여러 가지인 질문 |
| Step-back | 더 추상적인 질문을 함께 검색 | 분석형, 다단계 추론 질문 |
| Decomposition | 하위 질문으로 나눠 순차 또는 병렬 검색 | 다중 홉. 양방향 분해가 세 데이터셋에서 유효 [출처: https://arxiv.org/pdf/2609.06065] |

### 실무 적용 팁과 한계
- 팁: PDF가 많으면 Docling으로 구조 보존 파싱 후 HybridChunker, 그 위에 Contextual Retrieval을 얹는 조합이 자연스러움  
- 팁: 표, 차트, 스캔 PDF처럼 "텍스트 추출이 깨지는 문서"에 ColPali 계열이 특히 유효함  
- 팁: 쿼리 변환은 LLM 호출을 1회 이상 추가하므로, 라우팅과 바꿔 쓰기와 융합을 겹치기 전에 각각의 비용과 이득을 잼  
- 한계: Contextual Retrieval은 청크마다 LLM 호출이 필요해 캐싱 없이는 색인 비용이 빠르게 늚  
- 한계: HyDE는 가짜 답이 틀리면 오히려 엉뚱한 문서를 끌어옴

---

## 7. 그래프 검색 GraphRAG

### 핵심 개념
- 문서에서 사람, 조직, 사건 같은 노드(점)와 그 사이 관계(선)를 뽑아 그래프로 만들고, 질문에 맞는 부분 그래프를 찾아 답함  
- 벡터 RAG가 약한 "여러 문서를 가로지르는 질문"과 "이 데이터셋의 주요 주제는?" 같은 전체 조망 질문을 겨냥함  
  [출처: https://microsoft.github.io/graphrag//query/overview/]

### 왜 지금 주목받는가
- Microsoft GraphRAG 1.0(2024-12)이 커뮤니티 요약으로 전체 조망 질문을 풀면서 관심이 커졌으나,  
  전체 그래프 인덱싱 비용이 너무 커서 2025년 이후 흐름은 "품질은 지키고 비용을 줄이는" 변형으로 이동함  
  [출처: https://www.microsoft.com/en-us/research/blog/lazygraphrag/]  
- 여러 연구가 "GraphRAG가 실제 과제 다수에서 바닐라 RAG보다 못하다"고 보고하면서 "언제 쓸까"가 핵심 질문이 됨  
  [출처: https://arxiv.org/abs/2506.05690]

### 대표 기법과 도구
| 기법 | 주체, 시기 | 요점 |
|---|---|---|
| Microsoft GraphRAG 글로벌, 로컬, DRIFT 검색 | Microsoft, 2024 | 글로벌은 커뮤니티 요약 맵리듀스, 로컬은 엔터티 이웃, DRIFT는 둘을 결합 [출처: https://www.microsoft.com/en-us/research/blog/introducing-drift-search-combining-global-and-local-search-methods-to-improve-quality-and-efficiency] |
| LazyGraphRAG | Microsoft, 2024-11 | 인덱싱 때 요약을 안 만들고 질의 때 LLM을 씀. 인덱싱 비용이 전체 GraphRAG의 0.1%, 글로벌 질의 비용 700배 이상 절감(벤더 발표) [출처: https://www.microsoft.com/en-us/research/blog/lazygraphrag/] |
| LightRAG | HKU, EMNLP 2025 | 엔터티 수준과 주제 수준 이중 검색, 증분 갱신 지원 [출처: https://arxiv.org/html/2410.05779v3] |
| HippoRAG 2 | Ohio State, ICML 2025 | Personalized PageRank로 그래프를 타되 원문 구절을 깊이 결합. 연상 기억 과제에서 7% 개선(저자 발표) [출처: https://arxiv.org/abs/2502.14802] |
| EffiRAG | 2026-09 | "그래프로 위치를 찾고 답은 원문에서" 설계. LightRAG 대비 93승 7패 20무, 총비용 57% 절감 [출처: https://arxiv.org/abs/2609.18099] |

### 그래프 구축 자동화
- 2025-10 서베이는 LLM 기반 구축을 스키마 유도(구조, 일관성 중시)와 자유 추출(유연성, 열린 발견 중시)로 정리하고,  
  둘이 경쟁이 아니라 보완 관계라고 결론 냄. 초기 추출 오류가 뒤 단계로 전파되므로 사람 검토는 필수임  
  [출처: https://arxiv.org/abs/2510.20345]  
- Neo4j GraphRAG Python 패키지 v1.8.0은 텍스트에서 스키마를 자동 추론하고 강제 수준을 조절하는 옵션을 더함  
  [출처: https://neo4j.com/blog/developer/unleashing-the-power-of-schema/]  
- 구축 비용 사례: LightRAG는 한 벤치마크에서 그래프 구축에 8,680만 토큰, HippoRAG 2도 1,447만 토큰을 씀  
  [출처: https://arxiv.org/pdf/2607.20506]. 해법은 지연 구축, 증분 구축(iText2KG), LLM 없는 필터(EffiRAG)임  
  [출처: https://arxiv.org/abs/2409.03284]

### 지식그래프 질의와 그래프DB
- Text-to-Cypher는 Text-to-SQL보다 연구가 적음. CypherBench(2024-12)에서 GPT-4o 실행 정확도 60.18%,  
  10B 미만 모델은 20%도 못 넘김 [출처: https://arxiv.org/pdf/2412.18702]. CypherSmith(ACL 2026)가 12배 큰 튜닝 데이터를 공개함  
  [출처: https://preview.aclanthology.org/ingest-acl/2026.acl-long.1601/]  
- 그래프DB가 벡터 검색을 내장하면서 "벡터로 진입점을 찾고 그래프로 확장"하는 하이브리드가 한 엔진에서 가능해짐.  
  Neo4j(생태계 기본값), Kuzu(임베디드), FalkorDB(그래프와 벡터 통합), Memgraph(인메모리)  
  [출처: https://till-freitag.com/en/blog/neo4j-kuzu-memgraph-comparison-en]

### 언제 쓰지 말아야 하는가
- 단순 사실 검색: 그래프가 불필요한 정보를 끌어와 답을 흐림. Natural Questions에서 GraphRAG가 바닐라 RAG보다 13.4% 낮음  
  [출처: https://arxiv.org/abs/2506.05690]  
- 시간 민감 질문: 그래프가 "언제"를 잘 담지 못해 오답 증가  
- 그래프 품질이 낮을 때: 추출 오류가 그대로 답에 전파됨 [출처: https://arxiv.org/pdf/2502.11371]  
- 인덱싱 예산이 벡터 RAG의 수십 배를 감당하지 못할 때, 또는 벡터 RAG에 리랭킹만 붙여도 목표 품질에 닿을 때  
- GraphRAG-Bench(ICLR 2026)는 사실 검색, 복합 추론, 문맥 요약, 창의 생성 4난이도로 이 경계를 측정함  
  [출처: https://arxiv.org/abs/2506.05690]

### 그래프 기반 에이전트 메모리
- Zep Graphiti(2025-01): 이중 시간(bi-temporal) 모델로 사건 발생 시각과 수집 시각을 함께 기록하고, 충돌하는 사실은  
  지우지 않고 무효화 시각을 찍음 [출처: https://arxiv.org/abs/2501.13956v1]  
- Mem0(2025-04): 대화에서 핵심 정보를 추출, 통합, 검색. 그래프 변형은 시간 질문에서만 근소 우세(벤더 발표)  
  [출처: https://mem0.ai/blog/ai-agent-memory-benchmark]  
- 경고: 2026-01 독립 테스트베드(LoCoMo)에서 mem0, RAG, 전체 컨텍스트는 77 ~ 81% 정확도인데 Graphiti와 cognee는  
  55 ~ 56%에 머뭄. 원인은 "검색 불완전". RAG 기준선이 총소유비용 8.4배 저렴하면서 같은 정확도를 냄  
  [출처: https://arxiv.org/abs/2601.07978]

### 실무 적용 팁
- 전체 인덱싱 전에 자사 질문 로그를 4유형(사실, 추론, 요약, 생성)으로 분류해 그래프가 이기는 비율을 먼저 잼  
- 비용을 걱정하면 LazyGraphRAG 또는 HippoRAG 2처럼 인덱싱 때 LLM 호출을 줄이는 계열부터 검토함  
- 생성된 Cypher는 실행 전 문법 검증과 읽기 전용 권한을 걸고, 실패 시 재시도 루프 상한을 둠  
- 실무 요약 기사도 "전부 그래프화하지 말 것"을 권함  
  [출처: https://venturebeat.com/orchestration/stop-graphing-everything-when-graphrag-actually-beats-vector-rag]

---

## 8. 온톨로지와 지식그래프

### 핵심 개념
- 온톨로지(ontology)는 "이 분야에서 쓰는 개념과 그 관계를 약속한 사전"임. 지식그래프의 타입과 스키마 층에 해당함  
- 시맨틱 레이어(semantic layer)는 "매출", "활성 고객" 같은 업무 용어를 DB 컬럼과 계산식에 한 번만 매핑해 두는 층임  
- Competency Question(CQ)은 "이 온톨로지가 답할 수 있어야 하는 질문 목록"으로, 설계 요구사항 역할을 함

### 왜 지금 주목받는가
- LLM이 학습 데이터에 적게 등장한 도메인일수록 온톨로지로 묶어 주는 효과가 크다는 분석이 나옴  
  [출처: https://arxiv.org/html/2604.00555v2]  
- Snowflake, Microsoft Fabric, Palantir 등 주요 플랫폼이 "에이전트용 거버넌스된 시맨틱 레이어"로 수렴함  
  [출처: https://atlan.com/know/best-semantic-layer-tools/]  
- 국내에서도 "온톨로지는 죽는 게 아니라 보완되는 쪽"이라는 해설이 나옴 [출처: https://brunch.co.kr/@uxn00b/572]

### 대표 기법과 도구
| 기법 | 주체, 시기 | 요점 |
|---|---|---|
| OG-RAG | Microsoft, EMNLP 2025 | 문서를 온톨로지에 맞춘 사실 블록과 하이퍼엣지로 바꿔 검색. 2차 요약의 +55%, +40% 수치는 원문 미확인 [출처: https://aclanthology.org/2025.emnlp-main.1674.pdf] |
| Snowflake Cortex Agents 온톨로지 실험 | Snowflake, 2026-05 | 생의학 데이터로 시맨틱 뷰 기준선과 지식그래프, GraphRAG 비교 [출처: https://www.snowflake.com/en/blog/engineering/ontology-grounded-cortex-agents/] |
| Semantic View Autopilot | Snowflake, 2026-02 GA | 쿼리 로그에서 지표 정의를 자동 제안 [출처: https://futurumgroup.com/?p=90786] |
| 금융 분석용 온톨로지 프레임 | 2026-08 | 벡터 RAG는 관계 문맥이 없고 Text-to-SQL은 의미 문맥이 없다는 문제를 온톨로지로 메움 [출처: https://arxiv.org/pdf/2608.20661] |
| Bench4KE | 2025 | 실제 온톨로지 프로젝트 17개의 CQ 골드셋으로 LLM CQ 생성기를 비교하는 벤치마크 [출처: https://arxiv.org/abs/2505.24554v3] |
| Large Ontology Models | 2026-02 | 기업 지식관리용 "구축, 정렬, 추론" 프레임 [출처: https://arxiv.org/pdf/2602.00029] |

### OWL과 RDF를 LLM과 결합하는 방법
- 실무 시스템 다수는 전체 OWL(웹 온톨로지 언어) 대신 가벼운 타입 스키마만 씀. GraphRAG는 OWL을 전제하지 않음  
  [출처: https://aiexpjourney.substack.com/p/why-ontology-is-making-a-comeback]  
- RDF 그래프는 스키마가 커서 Text-to-SPARQL 제로샷이 어렵고, 프로퍼티 그래프 쪽 연구가 더 활발함  
  [출처: https://arxiv.org/pdf/2412.18702]  
- LLM은 온톨로지를 "완전 자동 생성"하기보다 "코파일럿"으로 쓰는 것이 적합하다는 평가가 반복됨  
  [출처: https://www.semanticarts.com/wp-content/uploads/2025/06/Building-an-Ontology-with-LLMs.pdf]

### 국내 동향
- 삼성SDS(2025-11-19 보도): 협업 SW 브리티웍스에 온톨로지를 적용하고 "퍼스널라이즈드 컨텍스트 그래프" 방법론 연구 착수  
  [출처: https://www.thelec.kr/news/articleView.html?idxno=44150]  
- CIO Korea(2025-02): 지식그래프를 기업 데이터와 LLM을 잇는 층으로 쓰는 사례. 구축과 유지에 전문 인력이 필요하다는 한계 지적  
  [출처: https://www.cio.com/article/3816012/]  
- 네이버, KT, LG CNS와 공공기관의 공개 구축 사례는 이번 조사에서 확인하지 못함 (출처 미확인)

### 실무 적용 팁과 한계
- 설계 순서는 CQ 작성 → 최소 스키마 → 자유 추출로 보강 → CQ로 회귀 검증이 안전함  
  (본 저장소 `references/how-to-competency-question.md` 참고)  
- 에이전트가 원시 스키마를 직접 보면 거버넌스를 우회하므로, 인증된 시맨틱 뷰만 통하게 강제해야 함  
  [출처: https://pub.towardsai.net/i-built-four-cortex-agents-on-a-semantic-layer-heres-where-the-governance-actually-lives-03a2c6dba478]  
- 웨어하우스 내장 시맨틱 레이어는 빠르지만 한 벤더에 잠김. 혼합 환경이면 dbt, Cube, AtScale 같은 독립 레이어 검토

---

## 9. NL2SQL과 시맨틱 레이어

### 핵심 개념
- NL2SQL(자연어를 SQL로 변환)은 "지난달 매출 상위 5개 지점"처럼 말로 한 질문을 DB가 실행할 SQL로 바꾸는 기술임.  
  벤치마크는 생성한 SQL을 실제로 실행해 정답 결과와 같은지로 채점함(실행 정확도, EX)  
- 큰 스키마에서 관련 테이블만 고르고(스키마 링킹), 여러 후보 SQL을 만들어 실행해 보며 고치는(자기 교정) 흐름이 표준임

### 벤치마크 현황 (2026-10-21 공식 페이지 열람 기준)
| 벤치마크 | 구성 | 현재 1위 | 참고 |
|---|---|---|---|
| Spider 2.0-Snow | 547문제, Snowflake 단일 방언 | Genloop Sentinel Agent v2 Pro 96.70 | 발표 당시(2024-11) GPT-4o 10.1%, o1-preview 17.1% [출처: https://spider2-sql.github.io/] |
| Spider 2.0-Lite | 547문제, BigQuery, Snowflake, SQLite 혼합 | Tianqiong Data Agent + GLM 5.2(Tencent) 76.23 | 스키마를 미리 주지 않고 모델이 탐색하는 설정 |
| Spider 2.0-DBT | 68문제, dbt 프로젝트 수준 코드 과제 | SignalPilot Agent 65.6 | |
| BIRD | 대규모 DB + 외부 지식 힌트 | GrainSQL(Purdue) 테스트 82.95% | 사람 92.96%, 격차 약 10점 [출처: https://bird-bench.github.io/] |

- 주의: 상위권은 대부분 기업 제출 에이전트이고 정답 SQL 일부만 공개되어 외부 재현이 제한됨 [출처: https://spider2-sql.github.io/]  
- 실무에서 점수가 안 나오는 이유: 수천 컬럼 스키마와 방언 혼합 [출처: https://arxiv.org/abs/2411.07763], 벤치마크 정답 자체의 오류  
  [출처: https://arxiv.org/pdf/2604.16493], 사람이 써 준 힌트 의존, 모호한 질문과 이기종 소스  
  [출처: https://promethium.ai/guides/text-to-sql-evaluation-benchmarks-metrics/]

### 대표 기법
| 기법 | 주체, 시기 | 요점 |
|---|---|---|
| RSL-SQL | 2024-11 | 양방향 스키마 링킹 후 전체 스키마 결과와 축소 결과를 투표. 실행 결과를 보고 다회전 수정 [출처: https://arxiv.org/abs/2411.00073] |
| CHASE-SQL | Google Cloud | 여러 전략으로 후보 SQL을 만들고 선택 모델이 고름. BIRD 76.02%(2025-04) [출처: https://bird-bench.github.io/] |
| 실행 기반 강화학습 | 2025-06 | 실행기를 학습 루프에 넣어 보상을 주면 새 스키마로 일반화가 좋아짐 [출처: https://arxiv.org/html/2506.06093v1] |
| AutoLink | 2025-11 | 에이전트가 스키마를 스스로 탐색하며 링킹. 대규모 스키마 대응 [출처: https://arxiv.org/pdf/2511.17190] |
| APEX-SQL | 2026-02 | 실제 데이터를 프로파일링해 컬럼 역할을 확인하는 가설-검증 루프. Spider 2.0-Snow 73.13 [출처: https://arxiv.org/abs/2602.16720v1] |
| FlexSQL | 2026-05 | 어느 단계에서든 스키마와 데이터 값을 보고 검증 질의를 실행 [출처: https://www.emergentmind.com/papers/2605.02815] |

- "스키마 링킹의 죽음" 논쟁: 추론 능력이 좋은 모델은 전체 스키마를 줘도 잘 고른다는 주장이 있으나,  
  수천 컬럼 규모에서는 컨텍스트 한계 때문에 여전히 축소가 필요함  
  [출처: https://www.promptlayer.com/research-papers/the-death-of-schema-linking-text-to-sql-in-the-age-of-well-reasoned-language-models]

### 시맨틱 레이어와 메트릭 정의
- dbt Semantic Layer 벤치마크(2026-04): 보험 스키마 질문에서 claude-sonnet-4-6이 원시 Text-to-SQL 90.0% → 시맨틱 레이어 98.2%,  
  gpt-5.3-codex 84.1% → 100.0%. "모델 교체보다 메트릭 정의가 정확도를 더 올림"  
  [출처: https://docs.getdbt.com/blog/semantic-layer-vs-text-to-sql-2026?version=2]  
- 3자 재현(Bodo.ai)은 질문 11개 규모이며 원시 스키마 직접 생성은 64.5%로 보고해, 설정 차이로 직접 비교는 어려움  
  [출처: https://www.bodo.ai/blog/how-pydough-reached-100-accuracy-on-dbts-semantic-layer-benchmark]  
- Snowflake Cortex Analyst: 시맨틱 모델을 붙였을 때 BIRD 일부 DB에서 57% → 78%(2025-03, 2차 자료 경유)  
  [출처: https://atlan.com/know/snowflake/cortex-analyst-vs-text-to-sql/]  
- 지식그래프 + SQL: AT&T CDO와 RelationalAI의 관계 지식그래프 기반 방식이 Spider 2.0-Snow 86.28을 기록함  
  [출처: https://spider2-sql.github.io/]  
- dbt는 시맨틱 레이어를 MCP 서버로 노출해 LLM이 메트릭 질의를 도구로 부르게 함

### 실무 적용 팁과 한계
- 팁: 자사 데이터로 작은 평가셋(질문 50 ~ 100개, 정답 결과 포함)을 먼저 만들고, 공개 벤치마크 점수는 모델 비교용으로만 씀  
- 팁: (1) 메트릭 정의 → (2) 용어집(동의어 포함) → (3) 검증된 질문-SQL 쌍을 few-shot 예시로 저장 → (4) 예시는 벡터 검색으로  
  질문과 비슷한 것만 골라 프롬프트에 넣음  
- 팁: 탐색 루프는 DB 호출 횟수와 지연을 늘리므로 루프 상한, 읽기 전용 계정, 실행 시간 제한을 반드시 둠  
- 한계: 시맨틱 레이어에 없는 질문(새 지표, 임시 분석)은 여전히 원시 SQL 생성으로 떨어지므로 두 경로를 함께 운영해야 함  
  [출처: https://atlan.com/know/ai-agent/data-for-ai/text-to-sql-for-enterprise/]

---

## 10. 에이전틱 RAG와 딥 리서치

### 핵심 개념
- 기존 RAG는 "검색 한 번 → 생성"의 고정 파이프라인이었음. 에이전틱 RAG는 LLM이 검색을 도구처럼 불러 쓰며  
  "검색할지, 무엇을 검색할지, 다시 검색할지"를 스스로 판단함  
- 딥 리서치(Deep Research)는 질문 하나에 수십 번의 검색과 읽기를 반복해 긴 보고서를 만드는 에이전트임.  
  "계획 → 병렬 검색 → 종합 → 인용"의 다단계 구조가 공통임

### 왜 지금 주목받는가
- Anthropic은 에이전트를 "도구를 루프 안에서 자율적으로 쓰는 LLM"으로 정의했고, 검색도 그 도구 중 하나가 됨  
  [출처: https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents]  
- OpenAI가 2025-02에 Deep Research를 내놓은 뒤 Google, Anthropic, Perplexity가 비슷한 기능을 출시했고 오픈소스가 구조를 따라 잡음  
  [출처: https://openai.com/index/introducing-deep-research/]

### 대표 기법과 도구
| 기법 | 주체, 시기 | 요점 |
|---|---|---|
| Self-RAG | 2023-10 | 모델이 "반성 토큰"으로 검색 필요 여부와 근거 충족 여부를 스스로 판단 [출처: https://arxiv.org/abs/2310.11511] |
| CRAG (Corrective RAG) | 2024 | 평가기가 검색 문서를 "정확, 모호, 부정확"으로 등급 매기고 부정확이면 웹 검색 등으로 넘어감 [출처: https://arxiv.org/abs/2401.15884] |
| LangGraph Adaptive RAG | LangChain | 라우터 + 문서 등급 + 질의 재작성 + 환각 검사 루프를 그래프로 구현한 표준 예제 [출처: https://docs.mistral.ai/resources/cookbooks/third_party-langchain-adaptive_rag_mistral] |
| Azure AI Search agentic retrieval | Microsoft, 2025-05 | LLM이 복합 질문을 하위 질의로 쪼개 키워드, 벡터, 하이브리드를 병렬 실행 후 시맨틱 리랭킹. 복합 질문 관련성 최대 40% 향상(벤더 발표) [출처: https://learn.microsoft.com/en-us/Azure/search/agentic-retrieval-overview] |
| Search-R1 | UIUC와 Google, COLM 2025 | 추론 중 검색 질의를 여러 번 만들도록 강화학습. Qwen2.5-7B 기준 RAG 대비 +24% [출처: https://arxiv.org/abs/2503.09516] |
| DeepRetrieval | 2025 | 질의 생성 자체를 강화학습으로 최적화 [출처: https://arxiv.org/pdf/2506.10408] |

- 에이전틱 RAG 서베이(2025-01)는 단일 에이전트, 멀티 에이전트, 계층형, 교정형, 적응형, 그래프 기반으로 분류함  
  [출처: https://arxiv.org/abs/2501.09136]

### 딥 리서치 구조
- Anthropic Research(2025-06 공개 글): 오케스트레이터-워커 구조. 리드 에이전트가 질문을 쪼개 서브에이전트들을 병렬로 띄우고  
  결과를 종합한 뒤 인용 에이전트에 넘김. 내부 평가에서 단일 모델 대비 90.2% 향상. 토큰 사용량이 성능 분산의 80%를 설명하며,  
  멀티 에이전트는 일반 채팅 대비 약 15배 토큰을 씀 [출처: https://www.anthropic.com/engineering/multi-agent-research-system]  
- 같은 글의 교훈: 서브에이전트에게 목표, 출력 형식, 도구 안내, 작업 범위를 명확히 주지 않으면 중복 작업이 생김.  
  에이전트끼리 맥락을 많이 공유해야 하는 작업(예: 코딩)에는 멀티 에이전트가 맞지 않음  
- OpenAI Deep Research는 찾기 어려운 정보를 끈질기게 탐색하는 BrowseComp 벤치마크(1,266문항)에서 문제의 약 절반을 풂.  
  브라우징을 켠 GPT-4o는 1.9%에 그침 [출처: https://openai.com/index/browsecomp/]  
- 오픈소스: LangChain Open Deep Research(범위 정하기 → 조사 → 쓰기 3단계) [출처: https://github.com/langchain-ai/open_deep_research],  
  GPT Researcher(플래너와 크롤러 에이전트 병렬 수집)

### 실무 적용 팁과 한계
- 팁: 15배 토큰은 "답의 가치가 큰 작업"에만 맞음. 질문당 예산 상한과 검색 횟수 상한을 둠  
- 팁: 하위 질의 수가 늘수록 느려지므로 "추론 노력 수준(low, medium)"처럼 단계를 두는 설계가 유용함  
  [출처: https://docs.azure.cn/en-us/search/agentic-retrieval-how-to-set-retrieval-reasoning-effort]  
- 한계: 평가와 자기 비판을 위한 LLM 호출이 늘어 지연과 비용이 오르고, 생산성 없는 검색 루프에 갇히는 문제가 열린 과제임  
  [출처: https://arxiv.org/pdf/2506.10408]

---

## 11. 컨텍스트 엔지니어링과 긴 문맥 논쟁

### 핵심 개념
- 컨텍스트 엔지니어링은 "프롬프트 문구"가 아니라 "모델에 넣을 토큰 전체(시스템 지시, 도구, MCP, 외부 데이터, 대화 이력)를  
  매 턴 어떻게 고를지"를 설계하는 일임 [출처: https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents]  
- 1M 토큰 문맥 모델이 나오면서 "RAG가 필요 없다"는 주장이 나왔지만, 문맥이 길수록 회상력이 떨어지는  
  "컨텍스트 부패(context rot)"가 관찰되어 문맥을 유한 자원으로 다루게 됨

### Anthropic 가이드(2025-09)의 핵심
- 주의 예산(attention budget): 토큰이 늘수록 집중력이 분산되므로 토큰마다 예산을 소모한다고 봄  
- 적시(just-in-time) 검색: 모든 데이터를 미리 넣는 대신 파일 경로, 저장된 질의, 링크 같은 가벼운 식별자만 두고 필요할 때 도구로 불러옴  
- 하이브리드 권고: 속도를 위해 일부는 미리 검색하고 나머지는 에이전트가 탐색. 긴 작업은 압축, 구조화된 메모, 서브에이전트 분리  
- RAG 공동 저자 Douwe Kiela는 "사람들이 이를 MCP와 RAG를 포함하는 컨텍스트 엔지니어링으로 다시 이름 붙였다"고 말함  
  [출처: https://thenewstack.io/rag-isnt-dead-but-context-engineering-is-the-new-hotness/]

### 긴 문맥 vs RAG
- LaRA(ICML 2025, Alibaba-NLP): 2,326개 사례, 11개 LLM으로 비교. 결론은 "만능 해법 없음". RAG는 단일 위치 질문과 환각 탐지에 강하고,  
  긴 문맥은 추론과 비교 과제에 강함. 약한 모델일수록 RAG 이득이 큼 [출처: https://proceedings.mlr.press/v267/li25dv.html]  
- 실무 결론: 단순 조회는 RAG, 문서 간 종합은 긴 문맥으로 보내는 라우팅(Self-Route 계열)이 권고됨  
  [출처: https://www.dataiku.com/blog/is-rag-obsolete]  
- 비용: 프롬프트 캐싱은 같은 앞부분을 다시 보낼 때 캐시 적중 요금만 냄. Claude 요금표(2026-10-21 열람) 기준 Sonnet 5.5는  
  기본 입력 $2/MTok, 캐시 적중 $0.10/MTok [출처: https://docs.claude.com/en/docs/build-with-claude/prompt-caching].  
  같은 문서 묶음을 반복해 쓰면 "긴 문맥 + 캐싱"이 경제적일 수 있으나, 문서가 자주 바뀌거나 사용자마다 다르면 RAG가 유리함

### MCP로 검색 도구를 노출하는 흐름
- Anthropic "Code execution with MCP"(2025-11): 도구 정의를 전부 프롬프트에 싣는 대신 파일시스템처럼 두고 필요한 것만 읽게 하면  
  150,000 토큰 → 2,000 토큰으로 98.7% 절감 [출처: https://www.anthropic.com/engineering/code-execution-with-mcp]  
- 도구가 많아지면 도구 선택 자체가 라우팅 문제가 되므로 "점진적 공개(progressive disclosure)"가 필요함

---

## 12. RAG 평가와 관측

### 핵심 개념
- RAG 평가는 검색(맞는 문서를 가져왔나)과 생성(가져온 문서에 근거해 답했나)을 나눠 봄.  
  정답 라벨이 없을 때는 LLM을 심사자로 써서 점수를 매김(LLM-as-a-judge)  
- 에이전틱 RAG는 검색 횟수와 경로가 매번 달라져, 지표만이 아니라 실행 추적(tracing)이 있어야 원인을 찾을 수 있음

### 지표와 도구
| 항목 | 내용 |
|---|---|
| 대표 지표 | faithfulness(답이 검색 문맥에 근거), answer relevancy(답이 질문에 맞음), context precision(가져온 청크 중 관련 비율), context recall(필요한 근거를 빠짐없이) [출처: https://dev.to/dublecc/rag-evaluation-metrics-guide-2026-faithfulness-context-precision-and-how-to-score-a-pipeline-46gi] |
| RAGAS 테스트셋 생성 | 문서를 노드로 올려 지식 그래프를 만들고 그래프를 걸어 다니며 단일 홉과 다중 홉 질문을 생성. 페르소나로 말투 다양화 [출처: https://docs.ragas.io/en/latest/concepts/test_data_generation/rag/] |
| RAGAS 버전 | 0.4.x 계열이 현재이며 옛 `ragas.metrics` 클래스명은 1.0에서 제거 예정 (2차 자료) [출처: https://blog.premai.io/rag-evaluation-metrics-frameworks-testing-2026] |
| LangSmith | LangChain과 LangGraph 스택에 가장 잘 맞음. SaaS 중심 [출처: https://signoz.io/comparisons/llm-observability-tools/] |
| Langfuse | 프레임워크 독립. 2025-06에 LLM 심사, 주석 큐 등 상용 모듈을 MIT로 공개 |
| Arize Phoenix | OpenTelemetry 기반. RAG 검색 관련성 평가에 자주 인용됨 |

### LLM-as-a-judge 한계
- 심사 모델을 바꾸면 점수가 흔들림. 완화책은 심사 모델 고정, 사람이 라벨한 소규모 부분집합으로 보정, 절대값 대신 추세 추적  
  [출처: https://letsdatascience.com/blog/llm-evaluation-ragas-llm-as-judge-and-production-evals]  
- 집계 점수는 "존재하지 않는 정책을 자신 있게 인용"하는 식의 개별 실패를 가릴 수 있으므로 실패 사례 열람이 필요함  
- Anthropic은 LLM 심사자에 루브릭(사실 정확성, 인용 정확성, 완전성, 출처 품질, 도구 효율)을 주고 사람 검수를 병행함  
  [출처: https://www.anthropic.com/engineering/multi-agent-research-system]

### 실무 적용 팁
- 운영 로그에서 실패한 질문을 모아 평가셋에 추가하는 "실패 → 테스트 변환" 루프를 두면 평가셋이 실제 분포를 따라감  
- OpenTelemetry로 계측해 두면 백엔드(Langfuse, Phoenix 등)를 나중에 바꿀 수 있음 [출처: https://roadmap.sh/ai-engineer/observability-tools]  
- NL2SQL 평가셋도 같은 원칙임. "질문, 정답 SQL, 실행 결과" 3종을 갖추고 실행 결과 일치로 채점함  
- 본 저장소 실습(`hands-on/solutions/rag`)의 RAGAS 평가와 연결됨

---

## 13. 멀티 소스 라우팅 아키텍처

### 핵심 개념
- 질문을 보고 벡터 검색(의미 유사), 키워드 검색(정확한 식별자), SQL(집계와 수치), 그래프(관계와 다중 홉) 중  
  어디로 보낼지 정하는 라우터를 앞단에 둠. 결과는 RRF와 리랭커로 합침  
- 임베딩만 쓰는 검색은 SKU, 오류 코드 같은 정확한 식별자를 놓치고, 집계 질문은 벡터로 답할 수 없다는 한계가 널리 인식됨  
  [출처: https://mer.vin/2026/07/vectorless-rag-explained-when-to-skip-embeddings-and-route-hybrid-retrieval-in-2026/]

### 질문 유형별 지식 경로
| 질문 유형 | 예시 | 권장 경로 | 근거 |
|---|---|---|---|
| 정확 식별자 조회 | "오류 코드 E-4021 원인" | BM25 우선 + 벡터 보조 | 4절 |
| 의미 유사 조회 | "카드 분실 시 어떻게 하나" | 벡터 + BM25 하이브리드 + 리랭커 | 5절 |
| 집계와 수치 | "지난달 지점별 매출 상위 5개" | NL2SQL + 시맨틱 레이어 | 9절 |
| 관계와 다중 홉 | "A 임원이 관여한 계열사의 소송" | 그래프 검색 또는 Text-to-Cypher | 7절 |
| 전체 조망 요약 | "이 문서 묶음의 주요 쟁점은" | GraphRAG 글로벌 또는 긴 문맥 | 7절, 11절 |
| 시간 변화 | "지난달에 뭐라고 했지" | 시간 인지 메모리 + 벡터 병행 | 7절 |

### 라우터 설계
- 라우터 유형: 정규식과 소형 의도 분류기, 또는 LLM 라우터. 질문이 특정 개체를 지목하는지, 다중 홉인지, 집계를 요구하는지로 분류  
  [출처: https://delos.so/blog/graphrag-vs-vector-search-enterprise-knowledge-retrieval]  
- LangGraph Adaptive RAG는 구조화 출력(`RouteQuery.datasource`)으로 라우팅을 코드로 고정함  
- 상용 통합: Azure agentic retrieval은 "지식 소스 선택"을 LLM 계획 단계에 포함해 여러 인덱스 중 어디를 볼지 정함  
- 저장소 분리 설계: 서사형 내용은 벡터, 사실은 그래프, 원문은 문서 저장소로 나눔  
  [출처: https://karbouch.substack.com/p/post-1-foundations-how-ai-actually]

### 한계
- 라우팅 정확도를 독립적으로 비교한 벤치마크는 찾지 못함. 튜토리얼의 라우터는 대부분 단순 분류기이므로  
  자사 질문 로그로 라우팅 정확도를 따로 측정해야 함

---

## 14. 교육팀 적용 제안

| 단계 | 내용 | 관련 실습 |
|---|---|---|
| 1. 기본기 | BM25(Kiwi 형태소) + 벡터 + RRF + 리랭커를 "기본 구성"으로 가르침 | `hands-on/solutions/rag` 인덱싱과 검색 |
| 2. 색인 품질 | Contextual Retrieval과 Docling 구조 보존 파싱을 선택 과제로 추가 | 청킹 비교 실습 |
| 3. 구조화 질의 | 시맨틱 레이어(메트릭 정의, 용어집, few-shot 예시)를 NL2SQL 앞에 두는 설계를 실습 | `hands-on/solutions/sql-retriever` |
| 4. 그래프 | "쓰지 말아야 할 경우" 체크리스트부터 가르치고, LazyGraphRAG 계열의 저비용 설계를 소개 | 그래프 스키마 도출 장표 |
| 5. 라우팅 | 질문 유형 6종을 분류하는 라우터를 LangGraph로 구현 | 하이브리드 지식 경로 설계 |
| 6. 평가 | RAGAS 테스트셋 생성 + 실패 사례 수집 루프 + Langfuse 추적 | RAGAS 평가 실습 |

- 교육 자료에서는 해외 벤치마크로 기법을 설명하고, 국내 사례는 동향 수준으로만 인용함  
- 수치를 인용할 때 "벤더 발표", "2차 자료" 표기를 유지함

---

## 15. 조사 한계와 미확인 항목

- 벤치마크 수치 상당수가 벤더 또는 블로그 2차 자료임  
- 출처 미확인으로 남긴 항목: Cohere Rerank 4와 voyage-4 공식 문서, Weaviate alpha 기본값, OG-RAG 원문 수치,  
  Google Gemini-SQL2의 BIRD 80.04%, Databricks Genie와 Cube의 정확도 수치, Gemini와 Perplexity 딥 리서치 내부 구조  
- 찾지 못한 것: BM25와 SPLADE의 중립 대규모 비교(2025 이후), 쿼리 변환 기법 간 정면 비교, 라우팅 정확도 벤치마크,  
  네이버와 KT와 LG CNS와 공공기관의 GraphRAG 또는 온톨로지 공개 사례  
- 저장한 원문(`.temp/`): Anthropic Contextual Retrieval, Jina late chunking, LazyGraphRAG 블로그, EffiRAG와 GraphRAG-Bench 초록,  
  삼성SDS 기사, Spider 2.0과 BIRD 리더보드, Anthropic 컨텍스트 엔지니어링과 멀티 에이전트 글, MCP 코드 실행 글, 프롬프트 캐싱 요금표

---

## 16. 주요 출처

### 공식 원문과 논문
- Anthropic Contextual Retrieval: https://www.anthropic.com/news/contextual-retrieval  
- Anthropic 컨텍스트 엔지니어링: https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents  
- Anthropic 멀티 에이전트 리서치: https://www.anthropic.com/engineering/multi-agent-research-system  
- Anthropic Code execution with MCP: https://www.anthropic.com/engineering/code-execution-with-mcp  
- Qwen3-Embedding: https://arxiv.org/pdf/2506.05176  
- Gemini Embedding 2: https://blog.google/innovation-and-ai/models-and-research/gemini-models/gemini-embedding-2/  
- BM25S: https://arxiv.org/abs/2407.03618v1  
- Late chunking: https://arxiv.org/html/2409.04701v1  
- ColPali: https://proceedings.iclr.cc/paper_files/paper/2025/file/99e9e141aafc314f76b0ca3dd66898b3-Paper-Conference.pdf  
- PyLate: https://arxiv.org/pdf/2508.03555  
- LazyGraphRAG: https://www.microsoft.com/en-us/research/blog/lazygraphrag/  
- LightRAG: https://arxiv.org/html/2410.05779v3  
- HippoRAG 2: https://arxiv.org/abs/2502.14802  
- EffiRAG: https://arxiv.org/abs/2609.18099  
- GraphRAG-Bench: https://arxiv.org/abs/2506.05690  
- LLM 기반 지식그래프 구축 서베이: https://arxiv.org/abs/2510.20345  
- CypherBench: https://arxiv.org/pdf/2412.18702  
- OG-RAG: https://aclanthology.org/2025.emnlp-main.1674.pdf  
- Zep Graphiti: https://arxiv.org/abs/2501.13956v1  
- Mem0: https://arxiv.org/abs/2504.19413  
- 에이전트 메모리 독립 평가: https://arxiv.org/abs/2601.07978  
- Spider 2.0: https://spider2-sql.github.io/ , https://arxiv.org/abs/2411.07763  
- BIRD: https://bird-bench.github.io/  
- RSL-SQL: https://arxiv.org/abs/2411.00073  
- APEX-SQL: https://arxiv.org/abs/2602.16720v1  
- dbt Semantic Layer 벤치마크: https://docs.getdbt.com/blog/semantic-layer-vs-text-to-sql-2026?version=2  
- 에이전틱 RAG 서베이: https://arxiv.org/abs/2501.09136  
- Self-RAG: https://arxiv.org/abs/2310.11511  
- CRAG: https://arxiv.org/abs/2401.15884  
- Search-R1: https://arxiv.org/abs/2503.09516  
- LaRA(긴 문맥 vs RAG): https://proceedings.mlr.press/v267/li25dv.html  
- OpenAI BrowseComp: https://openai.com/index/browsecomp/  
- RAGAS 테스트셋 생성: https://docs.ragas.io/en/latest/concepts/test_data_generation/rag/

### 2차 자료(블로그, 비교 글)
- 하이브리드 융합 비교: https://bigdataboutique.com/blog/hybrid-search-fusion-methods-compared  
- 리랭커 지연 예산: https://dev.to/gabrielanhaia/rerankers-and-the-latency-budget-when-cross-encoders-are-worth-it-3efc  
- 벡터DB 동향: https://www.firecrawl.dev/blog/best-vector-databases  
- 그래프DB 비교: https://till-freitag.com/en/blog/neo4j-kuzu-memgraph-comparison-en  
- 시맨틱 레이어 도구: https://atlan.com/know/best-semantic-layer-tools/  
- LLM 관측 도구 비교: https://signoz.io/comparisons/llm-observability-tools/  
- 삼성SDS 온톨로지 기사: https://www.thelec.kr/news/articleView.html?idxno=44150
