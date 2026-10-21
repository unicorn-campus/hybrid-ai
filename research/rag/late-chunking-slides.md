# PPT 스크립트: Late Chunking (1장)

- 덱 파일: `research/rag/late-chunking.pptx`  
- 빌드 코드: `research/rag/build/build-one-slide.js late-chunking` (pptxgenjs). `references/pptx-guide.md`를 따름  
- 상세 문서: `research/rag/late-chunking.md` (지식니 심층 조사, 2026-10-22)  
- 총 1장. 16″ × 9″, `내용_단쪽` 레이아웃. 표지와 간지 없음  
- 글꼴은 모든 텍스트에 Pretendard를 직접 지정. 제목 32pt, 리드문 18pt, 본문과 표는 최소 14pt  
- 시각 배치: 3열 구성. 좌측(왜 필요한가, 실습 적용) / 중앙(처리 절차 번호 목록) / 우측(효과 표, 한계)  
  아래에 콜아웃 한 줄, 오른쪽 아래 「상세 보기」 필 라벨(상세 문서 링크), 출처 한 줄  
- 아래의 「화면」 항목만 슬라이드에 표시함. 「발표자 노트」는 노트에 넣음

---

## 슬라이드 1. Late Chunking

- 제목: Late Chunking: 문서 전체를 먼저 임베딩하고 나중에 자르기
- 리드문: 긴 문맥 임베딩 모델에 문서 전체를 한 번 통과시킨 뒤, 토큰 벡터를 청크 구간별로 평균 내어 문맥을 보존합니다.
- 좌상 배지: 왜 필요한가
- 좌상 카드:
  - 질문: 베를린의 인구는?
  - 청크: "Its more than 3.85 million inhabitants..."
  - "Its"가 무엇인지 몰라 Berlin 질문에 안 걸림
  - Late 적용 뒤 Berlin과 유사도 0.71 → 0.82
- 좌하 배지: 실습 적용(Chroma + Cohere)
- 좌하 카드:
  - Cohere API는 토큰 벡터를 안 줘 적용 불가
  - 대안: Jina API late_chunking 또는 jina-v3 로컬
  - 질문도 같은 모델로 임베딩, Chroma에는 벡터만
- 중앙 배지: 처리 절차
- 처리 절차:
  1. 기존 splitter로 청크 경계를 정함(경계는 여전히 필요)
  2. 문서 전체를 토큰화하고 글자 경계를 토큰 구간으로 바꿈
  3. 모델을 한 번 통과시켜 토큰 벡터를 얻음(모든 토큰이 문서 전체를 봄)
  4. 청크 구간별로 토큰 벡터를 평균 내어 청크 벡터를 만듦
- 우상 배지: 효과(nDCG@10, jina-embeddings-v3)
- 표 열 너비: [2.0, 1.6, 1.6]

| 데이터셋 | 기존 청킹 | Late |
|---|---|---|
| SciFact | 71.8 | 73.2 |
| NFCorpus | 35.6 | 36.7 |
| FiQA | 46.3 | 47.6 |
| TRECCOVID | 73.0 | 77.2 |

- 우하 배지: 한계
- 우하 카드:
  - 토큰 벡터를 주고 문서를 통째로 담는 긴 문맥 평균 풀링 모델 필요
  - 글은 그대로라 BM25 효과 없음. 짧은 문서는 이득 작음
- 콜아웃: LLM 호출 없이 문맥을 얻지만, 독립 비교(NFCorpus nDCG@10)에서는 Contextual 0.308 대 Late 0.294로 뒤졌습니다.
- 상세 보기 링크: https://github.com/unicorn-campus/hybrid-ai/blob/main/research/rag/late-chunking.md
- 화면 출처: Günther 외, Late Chunking (arXiv 2409.04701 v3). Jina AI 블로그 1편(2024-08-22)과 2편(2024-10-03)
- 발표자 노트:
  - 핵심 한 줄: 기존 방식은 "자르고 나서 임베딩"이라 청크끼리 서로 못 봅니다. Late Chunking은 "임베딩하고 나서 자르기"라서 토큰 벡터 하나하나에 문서 전체 정보가 섞인 뒤에 청크 구간별로 평균을 냅니다. 추가 학습도 LLM 호출도 없습니다.
  - 블로그 예시: 베를린 위키 문서를 문장 단위로 자르면 "Its more than 3.85 million inhabitants make it the European Union's most populous city..." 문장에 Berlin이라는 단어가 없습니다. 논문 표 1(jina-embeddings-v2-small)에서 이 문장과 "Berlin"의 코사인 유사도는 기존 0.7084, Late 0.8249입니다. 다른 두 문장도 0.75에서 0.85, 0.85에서 0.85로 같거나 올랐습니다.
  - 처리 절차 보충: 경계 단서는 여전히 필요하고, 쓰는 시점만 모델 통과 뒤로 밀립니다. 코드는 tokenizer의 offset mapping으로 글자 위치를 토큰 번호 구간으로 바꾸고, 구간의 토큰 벡터를 더해 개수로 나눕니다(공식 저장소 chunked_pooling). 블로그 1편은 "앞 청크에 조건화"라고 썼지만 2편이 "양방향"으로 바로잡았습니다.
  - 긴 문서: 모델 한도 8192토큰을 넘으면 long late chunking(논문 v3 3.1절)을 씁니다. 큰 창으로 나눠 각각 통과시키되 창끼리 512토큰을 겹쳐 문맥을 보충하고, 겹친 앞부분 출력은 버리고 이어 붙입니다.
  - 효과 표 조건: 고정 256토큰 청크, 겹침 없음, BEIR 4개 데이터셋, nDCG@10(상위 10개 순서 점수, 높을수록 좋음). 3개 모델 평균 상대 향상은 고정 크기 +3.46%, 문장 경계 +3.63%, 의미 경계 +2.70%입니다. 문서가 길수록 이득이 크고(NFCorpus 평균 1,589자 +6.5점, Quora 62자 변화 없음), 청크가 작을수록 이득이 큽니다.
  - 지원 모델: Jina API는 요청에 late_chunking: true를 주면 되고, 2026년 10월 OpenAPI 명세 기준 jina-embeddings-v3와 v4에만 있습니다(v2, v5 없음). 로컬 실행은 jina-embeddings-v3(572M, 약 2.1GB, trust_remote_code 필요)이며 라이선스가 CC BY-NC 4.0이라 상업 이용은 문의가 필요합니다. 일반 조건은 토큰 벡터 접근 가능, 8192 이상 긴 문맥, 평균 풀링 모델입니다. CLS나 max 풀링 모델은 부적합합니다.
  - 한계와 독립 비교: 1차 출처가 모두 Jina 측 자료입니다. 독립 비교(arXiv 2504.19754, NFCorpus 20% 부분집합, jina-v3, 512토큰 청크)에서 nDCG@10은 Late 0.294, Contextual Retrieval 0.308이었습니다. 다만 Contextual 쪽에 BM25 결합과 리랭커가 포함되어 순수 비교는 아닙니다. 같은 연구에서 BGE-M3는 NFCorpus 0.225에서 0.067로 크게 떨어져, 모델을 가려 써야 합니다.
  - 실습 적용 포인트: Cohere embed API는 텍스트마다 최종 벡터 하나만 주므로 구간 평균을 낼 토큰 벡터가 없습니다. 적용하려면 임베딩 모델을 Jina로 바꿔야 하고, 질문 벡터도 같은 모델로 만들어야 하며 기존 Cohere 인덱스와 섞을 수 없습니다. BM25 색인과 청크 문장은 그대로 씁니다. Chroma에는 미리 계산한 벡터를 upsert의 embeddings 인자로 넣습니다. 상세 문서 9절에 Jina API 방식과 로컬 방식 Python 예시가 있습니다.
  - Contextual Retrieval과의 차이: Contextual은 글 자체에 문맥을 써 넣어 임베딩과 BM25가 함께 좋아지지만 청크마다 LLM 비용이 듭니다. Late Chunking은 비용이 거의 없지만 글이 바뀌지 않아 BM25에는 영향이 없고 모델 제약이 큽니다.
