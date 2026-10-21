# PPT 스크립트: Contextual Retrieval (1장)

- 덱 파일: `research/rag/contextual-retrieval.pptx`  
- 빌드 코드: `research/rag/build/build-one-slide.js contextual-retrieval` (pptxgenjs). `references/pptx-guide.md`를 따름  
- 상세 문서: `research/rag/contextual-retrieval.md` (지식니 심층 조사, 2026-10-22)  
- 총 1장. 16″ × 9″, `내용_단쪽` 레이아웃. 표지와 간지 없음  
- 글꼴은 모든 텍스트에 Pretendard를 직접 지정. 제목 32pt, 리드문 18pt, 본문과 표는 최소 14pt  
- 시각 배치: 3열 구성. 좌측(왜 필요한가, 실습 적용) / 중앙(처리 절차 번호 목록) / 우측(효과 표, 한계와 비용)  
  아래에 콜아웃 한 줄, 오른쪽 아래 「상세 보기」 필 라벨(상세 문서 링크), 출처 한 줄  
- 아래의 「화면」 항목만 슬라이드에 표시함. 「발표자 노트」는 노트에 넣음

---

## 슬라이드 1. Contextual Retrieval

- 제목: Contextual Retrieval: 청크에 문맥을 붙여 색인하기
- 리드문: LLM이 청크마다 짧은 문맥 설명을 써서 앞에 붙인 뒤, 임베딩과 BM25 양쪽에 같이 색인합니다.
- 좌상 배지: 왜 필요한가
- 좌상 카드:
  - 질문: ACME 2023년 2분기 매출 성장률은?
  - 청크: "매출이 전 분기보다 3% 늘었다"
  - 회사와 기간이 빠져 벡터와 BM25 모두 빗나감
  - 보강: "ACME 2023년 2분기 공시 일부" + 청크
- 좌하 배지: 실습 적용(Chroma + bm25s)
- 좌하 카드:
  - 청킹 뒤 Haiku가 청크마다 문맥 생성
  - 문맥 + 청크를 임베딩과 bm25s에 함께 색인
  - 평가셋으로 기준선과 비교 후 채택
- 중앙 배지: 처리 절차
- 처리 절차:
  1. 문서를 청크로 나눔(실습 4단계와 같음)
  2. 문서 전체와 청크를 LLM에 주고 50 ~ 100토큰 문맥 생성
  3. "문맥 + 청크"를 임베딩과 BM25 양쪽에 색인
  4. 두 검색 결과를 순위 융합해 150개를 뽑고, 리랭킹해 상위 20개를 전달
- 우상 배지: 효과(상위 20개 검색 실패율)
- 표 열 너비: [2.2, 1.5, 1.5]

| 구성 | 실패율 | 감소 |
|---|---|---|
| 기본 임베딩 | 5.7% | 기준 |
| 문맥 임베딩 | 3.7% | 35% |
| 문맥 BM25 결합 | 2.9% | 49% |
| 리랭킹 추가 | 1.9% | 67% |

- 우하 배지: 한계와 비용
- 우하 카드:
  - 청크마다 LLM 호출. 색인 1회에 문서 100만 토큰당 약 1달러(캐싱 전제)
  - Anthropic 자체 실험 수치. 내 데이터로 다시 측정
- 콜아웃: 지식베이스가 20만 토큰(약 500쪽) 미만이면 RAG 없이 통째로 넣는 편이 낫다고 Anthropic이 안내합니다.
- 상세 보기 링크: https://github.com/unicorn-campus/hybrid-ai/blob/main/research/rag/contextual-retrieval.md
- 화면 출처: Anthropic, Introducing Contextual Retrieval (2024-09-19). Anthropic 쿡북 contextual-embeddings 노트북
- 발표자 노트:
  - 핵심 한 줄: 청크를 자르면 "무엇에 대한 말인지"가 청크 밖에 남습니다. LLM이 그 빠진 문맥을 50에서 100토큰으로 써서 청크 앞에 붙이는 전처리입니다.
  - 원문 예시: SEC 공시 모음에서 "ACME Corp의 2023년 2분기 매출 성장률은?"을 물으면 정답 청크는 "The company's revenue grew by 3% over the previous quarter."뿐입니다. 변환 결과는 "This chunk is from an SEC filing on ACME corp's performance in Q2 2023; the previous quarter's revenue was $314 million."을 청크 앞에 붙인 것입니다.
  - 프롬프트 원문: <document>{{WHOLE_DOCUMENT}}</document> Here is the chunk we want to situate within the whole document <chunk>{{CHUNK_CONTENT}}</chunk> Please give a short succinct context to situate this chunk within the overall document for the purposes of improving search retrieval of the chunk. Answer only with the succinct context and nothing else.
  - 효과 표 조건: 코드베이스, 소설, ArXiv, 과학 논문 평균이고 임베딩은 최고 성능이던 Gemini Text 004입니다. 지표는 정답이 상위 20개에 못 든 비율(1 - recall@20)입니다. 쿡북 노트북(코드베이스 9개, 질의 248개, voyage-2)에서는 기본 9.9%, 문맥 임베딩 5.7%, BM25 결합 4.8%, 리랭킹 2.6%로 절대값은 다르지만 방향은 같습니다.
  - 비용 가정: 청크 800토큰, 문서 8k토큰, 문맥 100토큰, 프롬프트 캐싱 사용. 100만 토큰당 1.02달러는 원문 값입니다. 지식니가 현재 단가로 다시 계산하면 Claude Haiku 4.5는 약 3.94달러, Haiku 5.5는 약 0.39달러입니다(재계산). 캐시는 5분 유지라 문서 하나의 청크를 연달아 호출해야 하고, Haiku 4.5는 4,096토큰 미만 프롬프트는 캐시되지 않습니다.
  - 한계: 독립 연구(arXiv 2504.19754, 질의 50개, 문서 약 300개)에서는 NDCG@10이 기본 0.291, 문맥만 0.295, 문맥 + 융합 + 리랭킹 0.308로 이득이 작았습니다. 문서가 바뀌면 그 문서의 청크 문맥을 모두 다시 만들어야 하고, 생성된 문맥은 샘플 검수가 필요합니다. 한국어 공개 수치는 없습니다.
  - 실습 적용 포인트: 인덱싱 7단계 중 4단계(청킹)와 5단계(임베딩) 사이에 "문맥 생성"을 끼웁니다. Chroma에는 documents에 원래 청크, embeddings에 문맥 포함 벡터, metadata에 context를 저장하고, bm25s에는 문맥 + 청크를 Kiwi로 토큰화해 넣습니다. 질문에는 문맥을 붙이지 않습니다. 상세 문서 9절에 Python 예시가 있습니다.
  - Late Chunking과의 차이: Late Chunking은 LLM 없이 임베딩 모델 안에서 문맥을 반영하므로 싸지만 글을 바꾸지 않아 BM25는 좋아지지 않고, 토큰별 벡터를 주는 모델이 필요합니다. Contextual Retrieval은 글 자체에 문맥을 써 넣어 임베딩과 BM25가 함께 좋아지고 임베딩 모델 제약이 없지만 LLM 호출 비용이 듭니다.
