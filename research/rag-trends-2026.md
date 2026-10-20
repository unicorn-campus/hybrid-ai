# 넓은 의미의 RAG 최신 트렌드 조사 (2026년 10월)

- 작성: hybrid-ai 교육팀 (총괄 클로니, 조사 지식니)  
- 작성일: 2026-10-21  
- 범위: "정보 검색으로 LLM 답변 품질을 높이는 모든 방법"을 넓은 의미의 RAG로 보고,  
  벡터 검색, BM25, 하이브리드, 그래프 검색, 온톨로지, NL2SQL, 에이전틱 검색, 평가까지 다룸  
- 최초 조사 기록: 세 갈래로 나눠 WebSearch 68회(영어 50회, 한국어 16회, 보강 2회) 수행, 공식 원문 15건은  
  `curl`로 `.temp/`에 저장해 수치와 날짜를 직접 확인함  
- 추가 검토: 2026-10-21, GPT-6 Astra(`gpt-6-astra`)로 전체 내용을 검토하고 핵심 공식 자료를 재확인했습니다.  
  최초 조사 횟수와 수행자는 위 기록을 유지합니다. 이번 검토는 제품 선정, 버전, 비교 조건과 해석을 보완했습니다.  
- 독자: 하이브리드 AI 아키텍처를 배우는 개발자(중급). 용어는 처음 나올 때 괄호로 풀어 씀  
- 표기 원칙: 수치는 출처가 있는 것만 적음. 벤더 자체 발표는 "벤더 발표", 블로그 경유는 "2차 자료",  
  원문에서 확인하지 못한 것은 "출처 미확인"으로 구분함. 출처는 `[출처: URL]` 형식으로 표기함  
- 짝 자료: 요약 슬라이드 `rag-trends-2026.pptx`와 스크립트 `rag-trends-2026-slides.md`에도 이번 검토 내용을 반영했습니다.

---

## 1. 한눈에 보기

사내 문서를 찾는 질문, 매출을 집계하는 질문, 여러 조직의 관계를 묻는 질문은 필요한 근거가 다릅니다.  
그래서 이 보고서는 RAG를 문서 벡터 검색에 한정하지 않고, **질문에 맞는 검색 경로를 선택해  
검증 가능한 근거를 답변에 전달하는 설계**로 넓게 다룹니다. 이는 이 보고서의 범위 정의이며,  
모든 NL2SQL이나 에이전트 시스템을 학계에서 RAG로 분류한다는 뜻은 아닙니다.

2024년부터 2026년 10월까지의 공개 자료에서는 검색 품질뿐 아니라 비용, 지연, 데이터 갱신과  
평가를 함께 다루는 흐름이 확인됩니다. 아래 결론은 시장 점유율이나 보편적인 우승 순위를 뜻하지 않습니다.

| 분야 | 검토 결과 | 상세 |
|---|---|---|
| 임베딩 | Cohere, OpenAI, Voyage, Google API와 공개 가중치 모델을 용도별로 비교 | [3절](#3-벡터-검색과-임베딩) |
| BM25 | 식별자와 고유명사 검색 기준선. 한국어 분석기 효과는 평가 필요 | [4절](#4-bm25와-희소-검색) |
| 하이브리드 | 벡터와 키워드 결합, 융합과 리랭킹을 단계별로 검증 | [5절](#5-하이브리드-검색과-리랭킹) |
| 청킹 | 문서 구조와 청크 문맥을 보존하는 여러 선택지가 공존 | [6절](#6-청킹-인덱싱-쿼리-변환) |
| 그래프 | 연구 기법과 Neo4j 같은 구현 기반을 구분해 검토 | [7절](#7-그래프-검색-graphrag) |
| 온톨로지 | 개념, 관계와 업무 지표의 의미를 명시 | [8절](#8-온톨로지와-지식그래프) |
| NL2SQL | 공개 점수와 자사 업무 정확도를 구분. 지표 정의와 권한이 중요 | [9절](#9-nl2sql과-시맨틱-레이어) |
| 에이전틱 검색 | 필요한 경우 검색을 반복하되 종료 조건과 예산을 설정 | [10절](#10-에이전틱-rag와-딥-리서치) |
| 긴 문맥 | 검색과 함께 비교할 선택지. 캐싱까지 포함해 비용 평가 | [11절](#11-컨텍스트-엔지니어링과-긴-문맥-논쟁) |
| 평가 | 검색, 답변 근거, 지연과 비용을 함께 측정 | [12절](#12-rag-평가와-관측) |
| 라우팅 | 질문 유형에 맞는 경로를 선택하고 실패 사례를 추적 | [13절](#13-멀티-소스-라우팅-아키텍처) |

---

## 2. 큰 흐름 7가지

1. **벡터 검색과 키워드 검색을 함께 평가합니다.** Anthropic의 Contextual Retrieval 실험은  
   청크 문맥 보강, BM25 결합과 리랭킹의 누적 효과를 보여 줍니다. 다만 이 결과가 모든 데이터에서  
   같은 조합이 최선이라는 증거는 아닙니다. [출처: https://www.anthropic.com/news/contextual-retrieval]
2. **임베딩 선택지가 대형 모델 하나로 수렴하지 않습니다.** Cohere Embed 5와 Voyage 4는 같은 제품군 안에서  
   문서 색인용과 질의용 모델을 조합할 수 있습니다. Jina v5-text는 작은 모델의 효율을 다룹니다.  
   품질뿐 아니라 질의 지연과 배포 조건으로 후보를 나눠야 합니다.  
   [출처: https://docs.cohere.com/v1/changelog/embed-v5]  
   [출처: https://blog.voyageai.com/2026/01/15/voyage-4/] [출처: https://arxiv.org/abs/2602.15547]
3. **검색을 반복 호출하는 구조가 확장됩니다.** 에이전트는 검색 결과를 보고 다음 질의를 바꿀 수 있습니다.  
   단순 조회까지 모두 에이전트로 바꾸기보다, 반복 탐색이 필요한 질문에서 이득을 확인합니다.  
   [출처: https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents]
4. **업무 의미를 명시하는 작업이 중요합니다.** dbt의 보험 데이터 실험에서는 시맨틱 레이어가  
   정확도를 높였습니다. 이는 11개 질문을 반복 실행한 벤더 실험이므로 전체 기업 업무로 일반화하지 않습니다.  
   [출처: https://docs.getdbt.com/blog/semantic-layer-vs-text-to-sql-2026?version=2]
5. **그래프는 질문 유형에 맞춰 사용합니다.** Microsoft GraphRAG의 전체 조망 검색,  
   Neo4j의 관계 탐색과 Text-to-Cypher는 서로 다른 구현 선택지입니다.  
   그래프DB를 사용한다고 Microsoft GraphRAG의 커뮤니티 요약 방식이 자동 적용되지는 않습니다.  
   [출처: https://neo4j.com/docs/neo4j-graphrag-python/current/user_guide_rag.html]
6. **구축 비용도 품질과 함께 비교합니다.** LazyGraphRAG는 LLM 사용을 질의 시점으로 미루고,  
   EffiRAG는 그래프로 찾은 원문을 답변 근거로 사용합니다. 논문별 절감률은 해당 실험 조건에 한정됩니다.  
   [출처: https://www.microsoft.com/en-us/research/blog/lazygraphrag/] [출처: https://arxiv.org/abs/2609.18099]
7. **자사 평가셋으로 선택을 검증합니다.** 공개 순위와 고객 사례는 후보 선정 근거입니다.  
   한국어 질문, 접근 권한, 갱신 주기와 실제 비용까지 맞춘 자체 평가를 대신하지는 않습니다.  
   이 항목은 교육팀의 설계 제안입니다.

---

## 3. 벡터 검색과 임베딩

### 먼저 모델, 검색 방식과 저장소를 구분합니다

임베딩 모델은 문서와 질문을 숫자 벡터로 바꿉니다. 검색 엔진은 그 벡터를 저장하고 가까운 후보를 찾습니다.  
따라서 Cohere Embed와 pgvector를 같은 종류의 제품으로 비교하면 선택 기준이 흐려집니다.  
아래에서는 모델, 표현 방식과 저장소를 나누어 설명합니다.

단일 벡터 검색은 문서 또는 청크를 한 벡터로 요약합니다. 후기 상호작용(late interaction)은  
토큰별 벡터를 남겨 더 세밀하게 비교하지만 색인 크기와 검색 계산이 달라집니다. HNSW와 DiskANN은  
모델 이름이 아니라 근사 최근접 검색(ANN)을 효율적으로 수행하기 위한 색인 기법입니다.

### 실무 임베딩 후보와 선정 기준

후보는 **관리형 API, 자체 배포, 한국어, 멀티모달, 기존 시스템 비교 기준**을 고르게 다루도록 골랐습니다.  
공식 문서 또는 모델 카드로 기능을 확인할 수 있는 제품군의 예시이며, 점유율 순위나 전체 목록은 아닙니다.  
표의 공개 시점은 신제품 여부를 설명하는 정보이고, 오래된 모델도 비교 기준으로 유효할 수 있습니다.

| 후보 | 구분과 공개 시점 | 비교할 이유 |
|---|---|---|
| Cohere Embed 5 Pro/Fast | 관리형, 2026-09-30 | 다국어와 문서 이미지. 같은 벡터 공간에서 색인과 질의 모델 조합 |
| Cohere Embed 4 | 관리형, 2025 | 기존 Cohere 시스템의 비교 기준. 텍스트와 이미지 혼합 입력 |
| OpenAI text-embedding-3-small/large | 관리형, 2024 | 텍스트 검색 비교 기준. 크기와 출력 차원 선택 |
| Voyage 4 large/기본/lite/nano | API와 공개 가중치, 2026-01-15 | 제품군 내부 벡터 호환으로 품질과 질의 비용 조절 |
| Gemini Embedding 2 | 관리형, 2026-03-10 공개 | 텍스트, 이미지, 영상, 오디오와 PDF 검색 |
| Qwen3-Embedding 0.6B/4B/8B | 공개 가중치, 2025-06 | 자체 배포와 모델 크기별 비용 비교 |
| BGE-M3 | 공개 가중치, 2024 | 다국어 dense, sparse와 multi-vector 방식을 비교 |
| Jina v5-text / v5-omni | 공개 모델, 2026-02 / 05 논문 | 소형 텍스트 모델과 멀티모달 확장 비교 |
| KURE-v1 / v3 | 한국어 dense, 2024 / 2026 | 한국어 단일 벡터 검색 후보 |
| KURE-v2 | 한국어 late-interaction, 2026-08 | 한국어 다중 벡터 검색 후보. 별도 비용 비교 필요 |

제품별 공식 근거는 다음과 같습니다.

- **Cohere:** Embed 5 공식 출시 기록과 모델 목록을 함께 확인했습니다. Embed 5는 128k 입력과  
  256, 512, 768, 1024, 1536, 2048 차원을 제공합니다. Pro로 문서를 색인하고 Fast로 질문을 변환하는  
  조합을 공식 지원합니다. 이 호환성을 Embed 4나 다른 벤더 모델로 확대 해석해서는 안 됩니다.  
  [출처: https://docs.cohere.com/v1/changelog/embed-v5] [출처: https://docs.cohere.com/v2/docs/cohere-embed]
- **OpenAI:** text-embedding-3-small과 large의 기본 차원은 각각 1536과 3072이며,  
  `dimensions`로 출력 크기를 줄일 수 있습니다. [출처: https://platform.openai.com/docs/guides/embeddings]
- **Voyage:** 2026-01-15 발표한 Voyage 4 제품군은 벡터 공간을 공유합니다.  
  nano는 공개 가중치이고, large/기본/lite는 API 후보입니다.  
  [출처: https://blog.voyageai.com/2026/01/15/voyage-4/]
- **Google:** Gemini Embedding 2는 최초 공개 당시 공개 미리보기였고, 텍스트 8192 토큰과  
  여러 입력 유형을 지원한다고 발표했습니다. 도입 시 현재 API의 가용 상태와 입력 제한을 다시 확인합니다.  
  [출처: https://blog.google/innovation-and-ai/models-and-research/gemini-models/gemini-embedding-2/]
- **공개 모델:** Qwen3는 크기별 선택과 Apache 2.0 라이선스를 제공하고, BGE-M3는 여러 검색 표현을 지원합니다.  
  Jina v5-text 논문은 최대 32k 텍스트와 소형 모델을, v5-omni 논문은 이미지, 오디오와 영상 확장을 다룹니다.  
  공개 가중치라는 이유만으로 상업 이용 조건이 같다고 보지 말고 모델별 라이선스를 확인합니다.  
  [출처: https://github.com/QwenLM/Qwen3-Embedding] [출처: https://huggingface.co/BAAI/bge-m3]  
  [출처: https://arxiv.org/abs/2602.15547] [출처: https://arxiv.org/abs/2605.08384]

### 한국어 후보는 검색 방식까지 맞춰 비교합니다

KURE 공식 저장소는 v1을 BGE-M3 기반 dense 모델, v2를 late-interaction 모델로 구분합니다.  
2026-10-20 공개한 v3는 Nemotron-3-Embed-1B 기반 dense 모델입니다. 기존 보고서처럼 v1과 v2를  
모두 BGE-M3 미세조정 모델로 묶으면 서로 다른 검색 구조를 놓치게 됩니다.  
[출처: https://github.com/nlpai-lab/KURE]

같은 저장소의 MTEB-ko-retrieval 자체 평가에는 KURE-v2 0.8160, KURE-v3 0.8027,  
Qwen3-Embedding-8B 0.7826의 평균 nDCG@10이 실려 있습니다. 이는 독립 검증 결과가 아니며,  
v2의 다중 벡터 색인 비용까지 포함한 우열을 뜻하지 않습니다. 사내 약어, 한영 혼합 질문과  
문서 길이가 다른 평가셋에서 재현율, p95 지연과 색인 크기를 함께 측정합니다.  
[출처: https://github.com/nlpai-lab/KURE]

### 표현 방식과 저장소 선택

Matryoshka 표현 학습(MRL)은 벡터 앞부분만 사용해도 정보가 남도록 학습하는 방식입니다.  
Cohere, Voyage 등 지원 모델에서 출력 차원을 줄일 수 있지만, 줄인 차원에서 품질을 다시 재야 합니다.  
int8 또는 binary 양자화도 저장량을 줄이는 선택지이며 재현율 손실을 자동으로 복구해 주지는 않습니다.  
[출처: https://docs.cohere.com/v2/docs/cohere-embed]

| 저장소 또는 도구 | 검토할 상황 | 주의점 |
|---|---|---|
| pgvector | PostgreSQL 데이터와 벡터를 함께 관리 | 필터 선택도, ANN 재현율과 SQL 실행 계획 확인 |
| pgvectorscale | PostgreSQL에서 다른 색인 구현 비교 | StreamingDiskANN과 압축 설정을 실제 부하로 평가 |
| LanceDB | 임베디드 검색과 멀티모달 데이터 관리 | OSS 라이브러리와 Enterprise 서비스 운영 방식 구분 |
| OpenSearch, Weaviate 등 | 키워드와 벡터 검색을 한 엔진에서 운영 | 엔진별 융합, 필터와 확장 방식 확인 |
| Neo4j | 벡터 후보에서 관계를 따라 근거 확장 | 그래프 모델링과 관계 유지 비용을 함께 고려 |

pgvector 0.8.0부터 제공하는 반복 색인 스캔은 필터 적용 뒤 후보가 부족할 때 탐색을 이어 가는 기능입니다.  
이 버전을 현재 최신 버전으로 소개하는 것은 아닙니다. 저장소 선택에는 벡터 수뿐 아니라  
갱신량, 동시 질의, 필터 선택도와 운영 인력이 영향을 줍니다. 특정 벡터 수를 보편적인 경계로 삼지 않습니다.  
[출처: https://github.com/pgvector/pgvector] [출처: https://github.com/timescale/pgvectorscale]  
[출처: https://github.com/lancedb/lancedb]  
[출처: https://docs.opensearch.org/latest/vector-search/ai-search/hybrid-search/index/]  
[출처: https://docs.weaviate.io/weaviate/concepts/search/hybrid-search]  
[출처: https://neo4j.com/docs/neo4j-graphrag-python/current/user_guide_rag.html]

### 비교할 때 고정할 조건

MTEB 점수는 벤치마크 이름, 버전, 언어와 과제 구성이 같을 때 비교합니다. 전체 평균에는 검색 외 과제가  
포함될 수 있으므로 RAG 검색 성능과 같다고 보지 않습니다. Qwen3-Embedding-8B의 75.22는  
개발팀 공개 표의 MTEB English v2 평균이며, 현재 모든 모델의 검색 순위를 뜻하지 않습니다.  
[출처: https://github.com/QwenLM/Qwen3-Embedding] [출처: https://github.com/embeddings-benchmark/mteb]

실무에서는 동일한 문서, 청크, 질문과 정답 근거를 고정한 뒤 모델을 비교합니다. 모델을 교체할 때는  
벡터 차원이 같더라도 공간이 호환된다고 가정하지 않습니다. 공식적으로 호환을 보장하는 조합을 제외하면  
재색인과 회귀 평가를 계획합니다.

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
| SPLADE 계열 | Naver Labs Europe 외 | 학습한 단어 가중치와 확장으로 희소 검색 수행. 품질과 추론 비용을 BM25와 비교 [출처: https://github.com/naver/splade] |
| PROSPER | 2025 | LLM 기반 희소 검색기. 상품 검색에서 BM25 대비 재현율 10.2% 개선 보고 [출처: https://staff.fnwi.uva.nl/m.derijke/wp-content/papercite-data/pdf/song-2025-llms-arxiv.pdf] |
| OpenSearch | OpenSearch | 키워드와 벡터 검색을 결합하는 하이브리드 검색 제공 [출처: https://docs.opensearch.org/latest/vector-search/ai-search/hybrid-search/index/] |

### 한국어 형태소와 BM25

- 한국어는 조사와 어미가 붙어 공백 분리만으로는 "검색이", "검색을"이 다른 단어가 됨. Kiwi 같은 형태소 분석기로  
  어간을 뽑아 BM25에 넣으면 재현율이 올라감 [출처: https://wikidocs.net/251980]  
- 한국어 분석기는 조사와 어미 처리에 도움이 될 수 있지만, 약어와 제품 코드에서는 다른 결과를 낼 수 있습니다.  
  공백 분리, 형태소 분석과 하이브리드 구성을 같은 질문 집합으로 비교하는 것이 교육팀의 권장 실험입니다.

### 실무 적용 팁과 한계

- 팁: BM25로 시작하고, 말바꿈(paraphrase) 불일치가 심한 코퍼스에서만 SPLADE나 dense를 더함  
- 팁: 한국어 BM25는 토크나이저가 품질에 영향을 줍니다. 형태소 분석기 버전을 고정하고, 바꿀 때 재색인함  
- 한계: BM25, SPLADE, BM25S를 여러 RAG 벤치마크에서 중립적으로 비교한 2025년 대규모 연구는 찾지 못함

---

## 5. 하이브리드 검색과 리랭킹

### 서로 다른 검색기의 강점을 결합합니다

하이브리드 검색은 키워드 검색과 벡터 검색 등 서로 다른 검색 결과를 합치는 방식입니다.  
문서 후보를 넓게 모은 뒤, 리랭커가 질문과 후보를 함께 보고 관련도 순서를 다시 정할 수 있습니다.  
이 두 단계는 별개이므로 각각 추가했을 때의 품질과 비용을 측정합니다.

Anthropic의 2024년 실험에서는 기본 임베딩 검색의 상위 20개 검색 실패율 5.7%가  
Contextual Embedding과 Contextual BM25 적용 뒤 2.9%, 리랭킹까지 적용하면 1.9%가 됐습니다.  
67% 감소는 **기본 임베딩 검색 대비 전체 조합의 상대 감소율**이며, 리랭커만의 효과가 아닙니다.  
이 수치는 해당 평가셋과 설정의 벤더 발표입니다.  
[출처: https://www.anthropic.com/news/contextual-retrieval]

### 융합 방식은 검색 엔진과 평가셋에 맞춥니다

| 방식 | 계산과 장점 | 확인할 한계 |
|---|---|---|
| RRF | 검색기별 순위에 `1/(k + 순위)`를 적용해 합산 | 관련도 점수의 차이는 직접 반영하지 않음 |
| 정규화 점수 융합 | 점수 범위를 맞춘 뒤 가중합 | 정규화 방식과 가중치에 민감 |
| 학습형 융합 | 정답 레이블로 결합 방식 학습 | 학습과 운영 데이터가 다르면 성능 저하 가능 |

RRF의 `k=60`은 흔히 쓰는 설정 예시이며 필수값은 아닙니다. Weaviate는 v1.24부터  
기본값을 상대 점수 융합(`relativeScoreFusion`)으로 바꾸었습니다. 따라서 모든 제품이  
BM25, 벡터, RRF, 리랭커를 동일하게 제공한다고 설명하면 부정확합니다.  
[출처: https://docs.weaviate.io/weaviate/concepts/search/hybrid-search]

### 리랭커 후보

| 후보 | 비교할 이유 | 공식 근거 |
|---|---|---|
| Cohere Rerank 4 Pro/Fast | 품질과 지연에 따라 관리형 모델 선택 | [Cohere 출시 기록][cohere-rerank4] |
| Qwen3-Reranker 0.6B/4B/8B | 자체 배포와 크기별 비용 비교 | [Qwen 공식 저장소][qwen3] |
| BGE reranker 계열 | 공개 모델을 이용한 크로스 인코더 비교 | [FlagEmbedding][flagembedding] |
| Jina, Voyage 리랭커 | 기존 검색 서비스와 통합할 추가 후보 | 도입 시 해당 모델 카드와 API 문서 확인 |

Cohere Rerank 4는 2025-12-11 공개됐으며 다국어, JSON 형태의 문서와 32k 문맥을 지원합니다.  
Embed는 검색용 벡터를 만들고 Rerank는 이미 찾은 후보를 정렬합니다. 두 제품의 역할을 구분해야 합니다.  
[출처: https://docs.cohere.com/changelog/rerank-v4.0]

이전 보고서의 서로 다른 블로그에서 가져온 nDCG와 밀리초 순위는 삭제했습니다. 하드웨어,  
후보 수, 문서 길이와 요청 방식이 다르면 같은 표에 놓아도 공정한 비교가 되지 않기 때문입니다.  
LLM listwise 방식이 항상 가장 정확하다는 일반화도 하지 않습니다.

### 적용 순서

1. BM25와 벡터 검색을 각각 측정해 어떤 질문에서 근거를 놓치는지 봅니다.
2. 두 결과를 합쳐 재현율이 개선되는지 확인합니다. 검색기별 후보 수와 융합값을 기록합니다.
3. 리랭커를 추가해 상위 근거의 품질과 최종 답변이 개선되는지 측정합니다.
4. 질문당 비용과 p95 지연이 예산을 넘으면 후보 수, 모델 크기 또는 적용할 질문 유형을 조정합니다.

이 순서는 교육팀의 실험 제안입니다. 리랭커는 후보 목록에 들어오지 않은 문서를 복구할 수 없으므로,  
1차 검색에서 근거를 놓쳤다면 청킹, 질의와 검색 범위를 먼저 점검합니다.

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
- ColPali(ICLR 2025)는 PDF 페이지 이미지를 다중 벡터로 표현해 검색합니다. 검색 경로에서 OCR 의존을 줄이는 접근입니다  
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
| ColPali, ColQwen | ICLR 2025 이후 | 문서 이미지를 다중 벡터로 검색. 세대별 모델과 평가셋을 구분해 비교 [출처: https://huggingface.co/vidore] |
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

### 관계를 따라가야 답할 수 있는 질문에서 출발합니다

“이 계약에 연결된 공급사와 그 공급사의 모회사에 어떤 위험이 있나요?”라는 질문은 여러 문서의  
이름을 연결해야 합니다. 그래프를 이용하면 회사, 계약과 사건을 노드로 두고 관계를 따라 근거를 찾을 수 있습니다.  
반면 한 문단에 답이 있는 질문에는 관계 확장이 추가 비용만 만들 수도 있습니다.

GraphRAG라는 말은 그래프를 검색에 활용하는 넓은 방법군과 Microsoft의 특정 프로젝트 이름으로  
함께 쓰입니다. **방법론, 그래프DB와 개발 SDK를 구분해야 구현 선택을 정확히 비교할 수 있습니다.**

| 구분 | 예시 | 맡는 일 |
|---|---|---|
| 검색 방법 또는 연구 구현 | Microsoft GraphRAG, LightRAG, HippoRAG 2 | 그래프 구축과 검색 전략 정의 |
| 그래프 데이터베이스 | Neo4j | 노드와 관계 저장, Cypher 질의와 색인 실행 |
| 개발 라이브러리 | Neo4j GraphRAG Python | 검색기, 그래프 구축과 LLM 답변 생성을 코드로 연결 |

### 대표 연구 기법

| 기법 | 공개 시기 | 핵심 선택 |
|---|---|---|
| Microsoft GraphRAG | 2024 | 커뮤니티 요약의 글로벌 검색, 개체 중심 로컬 검색과 DRIFT |
| LazyGraphRAG | 2024-11 | 미리 만드는 LLM 요약을 줄이고 질의 시점에 추론 |
| LightRAG | 2024 공개, EMNLP 2025 | 개체와 관계 기반 검색, 증분 갱신 |
| HippoRAG 2 | 2025, ICML | 원문 구절과 Personalized PageRank 기반 탐색 결합 |
| EffiRAG | 2026-09 논문 | 그래프로 원문 위치를 찾고 원문으로 답변 생성 |

Microsoft GraphRAG의 글로벌, 로컬과 DRIFT는 서로 다른 질문을 겨냥합니다.  
Neo4j를 사용하는 모든 시스템이 이 커뮤니티 요약 파이프라인을 구현하는 것은 아닙니다.  
[출처: https://microsoft.github.io/graphrag/query/overview/]  
[출처: https://arxiv.org/html/2410.05779v3] [출처: https://arxiv.org/abs/2502.14802]

LazyGraphRAG의 “색인 비용 0.1%, 글로벌 질의 비용 700배 이상 절감”은 Microsoft가 비교한  
전체 GraphRAG 설정 대비 결과입니다. 모든 GraphRAG 제품에 적용되는 비용 비율은 아닙니다.  
EffiRAG의 비용 57% 절감과 93승, 7패, 20무 역시 UltraDomain의 4개 분야, 120개 질문에서  
LightRAG-hybrid와 비교한 저자 실험입니다. [출처: https://www.microsoft.com/en-us/research/blog/lazygraphrag/]  
[출처: https://arxiv.org/abs/2609.18099]

### Neo4j를 이용한 실무 구현

Neo4j는 관계 질의와 벡터 검색, 전문 검색을 함께 사용할 수 있는 구현 기반입니다. 공식  
GraphRAG Python 라이브러리는 아래 검색기를 제공합니다. 그래프 탐색 깊이와 반환할 근거는  
업무 질문에 맞게 설계해야 합니다. [출처: https://neo4j.com/docs/neo4j-graphrag-python/current/user_guide_rag.html]

| 검색기 | 실제로 하는 일 | 사용할 상황 |
|---|---|---|
| `VectorRetriever` | 벡터 유사도로 후보 검색 | 문서 의미 검색 기준선 |
| `HybridRetriever` | 벡터와 전문 검색 결과 결합 | 이름이나 식별자와 의미를 함께 검색 |
| `VectorCypherRetriever` | 벡터로 찾은 노드에서 정해 둔 Cypher 실행 | 관련 회사, 계약과 원문으로 확장 |
| `HybridCypherRetriever` | 하이브리드 후보에서 Cypher 실행 | 키워드와 관계 탐색 결합 |
| `Text2CypherRetriever` | 자연어와 스키마로 Cypher 생성 후 실행 | 관계 조건이나 집계 질의 |

앞의 네 검색기와 Text2Cypher는 제어 방식이 다릅니다. `VectorCypherRetriever`의 후속 질의는  
개발자가 정할 수 있지만, Text2Cypher는 모델이 질의를 생성합니다. 후자에는 읽기 전용 계정,  
허용 범위, 실행 시간 제한과 결과 검증을 별도로 설계해야 합니다.

실무 사례로 Neo4j가 공개한 **Klarna의 사내 지식 도우미 Kiki**가 있습니다. 이 사례는  
지식그래프로 사내 정보를 연결하고 직원 질문에 답하는 용도를 보여 줍니다. Neo4j의 고객 사례에  
등장하는 도입률과 처리 건수는 고객 및 벤더 발표이며, 독립적으로 재현한 정확도 비교가 아닙니다.  
이 사례는 실제 도입의 근거로 사용하고 시장 점유율이나 모든 그래프 검색의 효과를 증명하는 데 쓰지 않습니다.  
[출처: https://neo4j.com/customer-stories/klarna/]

그래프 구축에는 추출 모델 선택뿐 아니라 같은 개체의 이름 통합, 관계 타입, 원문 위치와 갱신 이력이 필요합니다.  
Neo4j의 스키마 기능도 이 구조를 명시하는 수단입니다. 자동 추출 결과를 그대로 사실로 취급하지 말고  
업무 질문과 원문 대조로 확인합니다. [출처: https://neo4j.com/blog/developer/unleashing-the-power-of-schema/]

### 어떤 조건에서 이득이 있는지 검증합니다

GraphRAG-Bench는 사실 검색, 복합 추론, 문맥 요약과 창의 생성으로 과제를 나눕니다.  
논문에서 특정 GraphRAG 구현이 낮은 성능을 보였다고 해서 Neo4j 기반의 모든 검색이 낮다고  
해석할 수는 없습니다. 비교한 그래프 구축기, 검색기와 질문 유형을 함께 읽어야 합니다.  
이전 보고서의 Natural Questions “13.4% 낮음”은 본 검토에서 본문 표와 계산 기준을 확인하지 못해 제외했습니다.  
[출처: https://arxiv.org/abs/2506.05690]

| 조건 | 먼저 확인할 것 |
|---|---|
| 단순 사실 조회 | 벡터 또는 키워드 검색만으로 근거가 충분한지 |
| 관계를 따라가는 질문 | 개체 통합과 관계 방향이 정확한지 |
| 전체 문서의 쟁점 요약 | 커뮤니티 요약이나 긴 문맥이 유리한지 |
| 시간에 따라 바뀌는 사실 | 유효 시점과 수집 시점을 구분해 저장하는지 |
| 잦은 데이터 변경 | 변경과 삭제가 관계와 요약에 전파되는지 |

### 그래프 기반 에이전트 메모리

Graphiti는 사건 발생 시점과 시스템이 알게 된 시점을 구분하는 이중 시간 모델을 사용합니다.  
따라서 “그래프는 시간 질문에 약하다”는 일반화보다 어떤 시간 모델과 검색 조건을 썼는지 봐야 합니다.  
[출처: https://github.com/getzep/graphiti]

LoCoMo를 사용한 독립 테스트베드는 특정 설정에서 mem0, RAG와 전체 문맥이 77 ~ 81%,  
Graphiti와 cognee가 55 ~ 56% 정확도를 보였다고 보고했습니다. RAG의 총소유비용이  
8.4배 낮았다는 비교 대상은 **mem0**입니다. 이는 해당 버전과 실험 환경의 결과이며  
그래프 메모리 전체의 고정된 성능 순위가 아닙니다. [출처: https://arxiv.org/abs/2601.07978]

### 실무 적용 제안

기존 Neo4j 그래프가 있다면 질문에 필요한 관계를 Cypher로 찾아 원문과 함께 전달하는 작은 실험부터  
시작할 수 있습니다. 문서에서 새 그래프를 만든다면 추출, 정합성 검사와 갱신 비용을 먼저 측정합니다.  
HippoRAG 2는 검색과 기억 성능을 개선하는 연구이므로, 별도 비용 측정 없이 저비용 구축 기법으로 묶지 않습니다.

평가에서는 벡터 검색 기준선과 그래프 확장 결과를 같은 질문으로 비교합니다. 답변 품질뿐 아니라  
원문 추적률, 관계 오류, 검색 지연, 구축 비용과 갱신 비용을 기록합니다.

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
| OG-RAG | Microsoft, EMNLP 2025 | 문서를 온톨로지에 맞춘 사실 블록과 하이퍼엣지로 바꿔 검색. 정량 개선 수치는 본 검토에서 원문 표를 재확인하지 않아 제외 [출처: https://aclanthology.org/2025.emnlp-main.1674.pdf] |
| Snowflake Cortex Agents 온톨로지 실험 | Snowflake, 2026-05 | 생의학 데이터로 시맨틱 뷰 기준선과 지식그래프, GraphRAG 비교 [출처: https://www.snowflake.com/en/blog/engineering/ontology-grounded-cortex-agents/] |
| Semantic View Autopilot | Snowflake, 2026-02 GA | 쿼리 로그에서 지표 정의를 자동 제안 [출처: https://futurumgroup.com/?p=90786] |
| 금융 분석용 온톨로지 프레임 | 2026-08 | 벡터 RAG는 관계 문맥이 없고 Text-to-SQL은 의미 문맥이 없다는 문제를 온톨로지로 메움 [출처: https://arxiv.org/pdf/2608.20661] |
| Bench4KE | 2025 | 실제 온톨로지 프로젝트 17개의 CQ 골드셋으로 LLM CQ 생성기를 비교하는 벤치마크 [출처: https://arxiv.org/abs/2505.24554v3] |
| Large Ontology Models | 2026-02 | 기업 지식관리용 "구축, 정렬, 추론" 프레임 [출처: https://arxiv.org/pdf/2602.00029] |

### OWL과 RDF를 LLM과 결합하는 방법

- GraphRAG 구현에 반드시 OWL(웹 온톨로지 언어)이 필요한 것은 아닙니다. 타입과 관계 스키마부터 시작할 수 있습니다  
  [출처: https://aiexpjourney.substack.com/p/why-ontology-is-making-a-comeback]  
- RDF는 SPARQL, 프로퍼티 그래프는 Cypher 같은 질의 언어를 사용합니다. 질의 생성에는 스키마와 예시가 중요합니다  
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
- 에이전트가 데이터를 조회할 때도 사용자 권한이 유지되도록 접근 가능한 테이블과 뷰를 제한합니다.  
  시맨틱 레이어가 있다는 이유만으로 접근 권한이 자동 보장되는 것은 아닙니다. 교육팀의 설계 제안입니다.  
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
| Spider 2.0-Lite | 547문제, BigQuery, Snowflake, SQLite 혼합 | Tianqiong + GLM 5.2 76.23 | 메타데이터와 문서 제공 |
| Spider 2.0-DBT | 68문제, dbt 프로젝트 수준 코드 과제 | SignalPilot Agent 65.6 | |
| BIRD | 대규모 DB + 외부 지식 힌트 | GrainSQL(Purdue) 테스트 82.95% | 사람 92.96%, 해당 평가 내 격차 10.01%p [출처: https://bird-bench.github.io/] |

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

- 큰 스키마에서는 관련 테이블과 컬럼을 고르는 작업이 중요합니다. Spider 2.0처럼 문서와  
  여러 SQL 방언을 함께 다루는 과제에서는 탐색 방법까지 평가해야 합니다.  
  [출처: https://spider2-sql.github.io/]

### 시맨틱 레이어와 메트릭 정의

- dbt Semantic Layer 벤치마크(벤더 발표): 보험 데이터의 11개 질문을 각각 20회 실행했습니다.  
  claude-sonnet-4-6이 Text-to-SQL 90.0% → 시맨틱 레이어 98.2%,  
  gpt-5.3-codex 84.1% → 100.0%. 이 범위에서 시맨틱 모델링의 효과를 보여 주지만, 다른 업무에서도 같은 개선폭을 보장하지는 않습니다  
  [출처: https://docs.getdbt.com/blog/semantic-layer-vs-text-to-sql-2026?version=2]  
- Bodo.ai의 별도 구현 실험도 같은 11개 질문을 사용하며 원시 스키마 직접 생성은 64.5%로 보고해, 설정 차이로 직접 비교는 어려움  
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
  해당 멀티 에이전트 시스템은 일반 채팅 대비 약 15배 토큰을 사용했다고 보고함 [출처: https://www.anthropic.com/engineering/multi-agent-research-system]  
- 같은 글의 교훈: 서브에이전트에게 목표, 출력 형식, 도구 안내, 작업 범위를 명확히 주지 않으면 중복 작업이 생김.  
  에이전트끼리 맥락을 많이 공유하거나 의존 관계가 강한 작업에서는 병렬화 이득이 줄어들 수 있습니다  
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
- 비용: 프롬프트 캐싱은 같은 앞부분을 다시 보낼 때 캐시 적중 부분에는 읽기 요금이 적용됩니다. 최초 캐시 쓰기, 만료와  
  출력 토큰 비용도 계산해야 합니다. Claude 요금표(2026-10-21 열람) 기준 Sonnet 5.5는  
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
| RAGAS 버전 | 설치 버전의 공식 문서와 API를 고정해 평가 코드를 재현합니다. 특정 최신 버전 단정은 제외합니다 |
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
  어디로 보낼지 정하는 라우터를 앞단에 둠. 문서 후보는 융합하거나 리랭킹할 수 있습니다. SQL 집계값은 단위와 기준 시점을 확인해 답변에 결합합니다.  
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
| 1. 기본기 | BM25와 벡터 기준선을 측정한 뒤 융합과 리랭킹의 효과 비교 | `hands-on/solutions/rag` 인덱싱과 검색 |
| 2. 색인 품질 | Contextual Retrieval과 Docling 구조 보존 파싱을 선택 과제로 추가 | 청킹 비교 실습 |
| 3. 구조화 질의 | 시맨틱 레이어(메트릭 정의, 용어집, few-shot 예시)를 NL2SQL 앞에 두는 설계를 실습 | `hands-on/solutions/sql-retriever` |
| 4. 그래프 | Neo4j 관계 확장과 벡터 기준선 비교. 연구 기법의 구축 비용도 구분 | 그래프 스키마 도출 장표 |
| 5. 라우팅 | 질문 유형 6종을 분류하는 라우터를 LangGraph로 구현 | 하이브리드 지식 경로 설계 |
| 6. 평가 | RAGAS 테스트셋 생성 + 실패 사례 수집 루프 + Langfuse 추적 | RAGAS 평가 실습 |

- 교육 자료에서는 해외 벤치마크로 기법을 설명하고, 국내 사례는 동향 수준으로만 인용함  
- 수치를 인용할 때 "벤더 발표", "2차 자료" 표기를 유지함

---

## 15. 조사 한계와 추가 검토 기록

### 이번 Astra 검토에서 바로잡은 내용

2026-10-21에 GPT-6 Astra(`gpt-6-astra`)로 문서 전체를 읽고, 핵심 주장의 공식 원문을 다시 확인했습니다.  
이번 작업은 문헌 검토이며 모델 성능을 직접 측정한 실험은 아닙니다.

| 검토 항목 | 반영한 수정 |
|---|---|
| 대표 제품 누락 | Cohere Embed, OpenAI, Voyage와 BGE-M3를 임베딩 후보에 추가 |
| 최신 버전 | Cohere Embed 5, Rerank 4, Voyage 4, Jina v5와 KURE-v3 공개 근거 확인 |
| KURE 분류 오류 | v1/v3의 dense와 v2의 late-interaction 구분 |
| Neo4j 설명 부족 | 방법론, DB와 SDK 구분. 공식 검색기와 Klarna 고객 사례 추가 |
| GraphRAG 과잉 일반화 | 논문별 설정과 비용 기준 명시. 특정 결과를 모든 구현에 적용하지 않음 |
| 하이브리드 효과 | Anthropic의 67%가 전체 조합의 상대 감소율임을 명확히 설명 |
| SQL 벤치마크 | Spider 2.0-Lite의 메타데이터 제공 조건 수정. dbt의 11개 질문 규모 명시 |
| 비교 조건 누락 | 조건이 다른 블로그의 리랭커 순위와 지연 수치 삭제 |
| 운영 비용 | 캐시 쓰기와 읽기 비용 구분. 모델 교체 시 벡터 호환과 재색인 확인 추가 |

### 남아 있는 한계

- 최초 조사의 모든 링크와 모든 논문 본문을 이번에 다시 검증한 것은 아닙니다. 재확인은  
  제품 선정과 버전, Neo4j 기능과 사례, 주요 수치 및 핵심 결론에 집중했습니다.
- 본문에 남은 “2차 자료”는 공식 근거를 다시 확인하기 전까지 설계 판단의 보조 자료로만 사용합니다.  
  출처가 있다는 사실만으로 독립 재현이나 현재 운영 성능이 확인되는 것은 아닙니다.
- 공식 리더보드 숫자는 2026-10-21 열람 시점의 제출 결과입니다. 제출 날짜가 없는 항목은  
  그 이전의 특정 시점 순위를 복원할 수 없고, 실제 업무 정확도와 동일하지 않습니다.
- 모델 API, 라이선스와 관리형 서비스 제공 지역은 도입 시 다시 확인해야 합니다.  
  이 문서는 한국어 기업 데이터에서의 비용, 지연과 품질 실측을 수행하지 않았습니다.
- 최신 모델을 모두 망라하지 않았습니다. 후보는 배포 방식, 한국어, 멀티모달과 기존 시스템 비교를 위한 예시입니다.
- GraphRAG-Bench의 Natural Questions 13.4% 차이는 본문 표와 계산 기준을 재확인하지 못해 삭제했습니다.  
  OG-RAG 개선율과 Gemini-SQL2 정확도 등 기존 미확인 수치도 설계 결론의 근거로 사용하지 않습니다.
- 요약 슬라이드 14장과 PPT 스크립트에 이번 검토 내용을 반영했습니다. 자세한 비교 조건과 원문 링크는 발표자 노트에 담았습니다.

이번 확인에 사용한 원문은 `.temp/astra-*.html`과 읽기용 `.txt`에 저장했습니다.  
Neo4j 검색기, Klarna 사례와 Cohere 모델 목록은 기존 `.temp/` 원문도 함께 확인했습니다.  
원문 저장 여부는 검증의 보조 기록이며, 본문에서 확인하지 않은 주장까지 검증했다는 뜻은 아닙니다.

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
- ColPali:  
  https://proceedings.iclr.cc/paper_files/paper/2025/file/99e9e141aafc314f76b0ca3dd66898b3-Paper-Conference.pdf
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


### Astra 검토에서 추가한 공식 자료

- [Cohere Embed 모델 목록](https://docs.cohere.com/v2/docs/cohere-embed)
- [Cohere Embed 5 출시 기록](https://docs.cohere.com/v1/changelog/embed-v5)
- [Cohere Rerank 4 출시 기록](https://docs.cohere.com/changelog/rerank-v4.0)
- [Voyage 4 출시 기록](https://blog.voyageai.com/2026/01/15/voyage-4/)
- [OpenAI 임베딩 가이드](https://platform.openai.com/docs/guides/embeddings)
- [Neo4j GraphRAG Python 검색기](https://neo4j.com/docs/neo4j-graphrag-python/current/user_guide_rag.html)
- [Neo4j의 Klarna 고객 사례](https://neo4j.com/customer-stories/klarna/)
- [KURE 공식 저장소](https://github.com/nlpai-lab/KURE)
- [Jina v5-text 논문](https://arxiv.org/abs/2602.15547)
- [Jina v5-omni 논문](https://arxiv.org/abs/2605.08384)

[cohere-rerank4]: https://docs.cohere.com/changelog/rerank-v4.0
[qwen3]: https://github.com/QwenLM/Qwen3-Embedding
[flagembedding]: https://github.com/FlagOpen/FlagEmbedding
