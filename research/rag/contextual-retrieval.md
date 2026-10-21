# Contextual Retrieval 심층 조사

작성 2026-10-22, 지식니. 1차와 2차 출처를 구분하고 확인 못 한 것은 "(미확인)"으로 표시함.

## 1. 한눈에 보기
- Anthropic이 2024-09-19에 공개한 검색 전처리 기법. 청크마다 LLM이 쓴 짧은 설명(문맥)을 앞에 붙여 임베딩과 BM25 양쪽에 색인함
- 상위 20개 검색 실패율: 5.7%(기본) → 3.7%(문맥 임베딩만) → 2.9%(문맥 BM25 결합) → 1.9%(리랭킹 추가)
- 비용은 프롬프트 캐싱 전제로 문서 100만 토큰당 1.02달러(원문 가정)
- 지식베이스가 20만 토큰 미만이면 RAG 없이 통째로 프롬프트에 넣으라고 원문이 안내함
- 수치는 Anthropic 자체 실험이고, 독립 연구는 소규모이며 이득이 작게 나옴

## 2. 문제: 청크가 문맥을 잃는 이유
문서를 수백 토큰 청크로 자르면 "무엇에 대한 말인지"가 청크 밖에 남음.  
원문 예시: SEC 공시 모음에서 "ACME Corp의 2023년 2분기 매출 성장률은?"이라고 물음.  
정답 청크는 "The company's revenue grew by 3% over the previous quarter."뿐이라 회사와 기간이 없음.  
임베딩(뜻이 비슷한 글을 벡터로 찾는 방식)도 BM25(같은 단어가 든 글을 찾는 방식)도 이 청크를 ACME와 잇기 어려움.  
원문의 변환 결과: "This chunk is from an SEC filing on ACME corp's performance in Q2 2023; the previous quarter's  
revenue was $314 million." 뒤에 원래 청크를 붙임.

## 3. 원리와 처리 절차
1. 문서를 평소처럼 청크로 나눔
2. 청크마다 (문서 전체 + 그 청크)를 LLM에 주고 문맥 문장을 생성함(원문은 Claude 3 Haiku, 보통 50에서 100토큰)
3. "문맥 + 청크"로 임베딩을 만들고(문맥 임베딩), 같은 글로 BM25 색인도 만듦(문맥 BM25)
4. 질문 때 두 검색 결과를 순위 융합으로 합침. 질문에는 문맥을 붙이지 않음(노트북 코드 기준)
5. 선택: 후보 150개를 리랭커(후보를 다시 줄 세우는 모델)로 정렬해 상위 20개 사용

```text
문서 ─ 청크 나누기 ─ 청크 i
(문서 전체 + 청크 i) → Claude Haiku → 문맥 i (50-100토큰)
"문맥 i + 청크 i" ─┬→ 임베딩 → 벡터DB
                   └→ BM25 색인
질문 → 벡터 검색 + BM25 검색 → 순위 융합 → (리랭킹) → 상위 20개 → 답변 LLM
```

## 4. 프롬프트 원문과 번역
블로그 원문(Claude 3 Haiku용)임.

```text
<document>
{{WHOLE_DOCUMENT}}
</document>
Here is the chunk we want to situate within the whole document
<chunk>
{{CHUNK_CONTENT}}
</chunk>
Please give a short succinct context to situate this chunk within the overall document for the purposes of
improving search retrieval of the chunk. Answer only with the succinct context and nothing else.
```

번역: 이 청크가 문서 전체에서 어디에 해당하는지, 청크 검색 개선용으로 짧고 간결한 문맥을 주시오.  
문맥만 답하고 다른 말은 하지 마시오.  
쿡북은 같은 문구에 `claude-haiku-4-5`, temperature 0을 쓰고 문서 블록에만 `cache_control`을 붙임.

## 5. 실험 결과와 조건
원문(블로그): 코드베이스, 소설, ArXiv, 과학 논문 평균. 임베딩은 최고 성능이던 Gemini Text 004.  
지표는 1 - recall@20(정답이 상위 20개에 못 든 비율)임.

| 조건 | 상위 20개 실패율 | 기본 대비 감소 |
|---|---|---|
| 기본(문맥 없는 임베딩) | 5.7% | 기준 |
| 문맥 임베딩만 | 3.7% | 35% |
| 문맥 임베딩 + 문맥 BM25 결합 | 2.9% | 49% |
| 위 조합 + 리랭킹 추가(Cohere) | 1.9% | 67% |

쿡북 노트북(코드베이스 9개, 질의 248개, voyage-2)의 실행 출력임. 실패율은 100에서 Pass@20을 뺀 내 계산임.

| 조건 | Pass@20 | 실패율 |
|---|---|---|
| 기본 | 90.06% | 9.9% |
| 문맥 임베딩만 | 94.29% | 5.7% |
| 문맥 임베딩 + 문맥 BM25 결합 | 95.23% | 4.8% |
| 문맥 임베딩 + 리랭킹(BM25 없음, rerank-english-v3.0) | 97.45% | 2.6% |

노트북 요약표의 BM25 결합 값(94.99%)은 실행 출력과 달라 출력값을 썼음.

## 6. 비용 산식과 가정
원문 가정: 청크 800토큰, 문서 8k토큰, 지시문 50토큰, 문맥 100토큰, 캐싱. 문서 100만 토큰 = 문서 125개 = 청크 1,250개.  
식: 125 × (8,000 × 캐시쓰기 + 10 × 8,000 × 캐시읽기 + 10 × 850 × 입력 + 10 × 100 × 출력) (단가는 100만 토큰당)  
원문은 단가를 안 밝혀 내가 재계산함.

| 모델 | 입력 / 출력 / 캐시쓰기 / 캐시읽기 | 문서 100만 토큰당 |
|---|---|---|
| Claude 3 Haiku(단가 기억 기반, 미확인) | 0.25 / 1.25 / 0.30 / 0.03 | 1.02달러(원문과 일치) |
| Claude Haiku 4.5(프롬프트 캐싱 문서) | 1 / 5 / 1.25 / 0.10 | 약 3.94달러 |
| Claude Haiku 5.5(같은 문서) | 0.10 / 0.50 / 0.125 / 0.01 | 약 0.39달러 |

- 캐시 없이 문서를 매번 입력하면 Haiku 4.5는 약 11.7달러로 3배가량 늘어남
- 쿡북 실측: 청크 737개, 입력 토큰의 61.83%가 캐시 읽기, 입력비 9.20달러에서 2.85달러로 감소
- 캐시 유지 5분이므로 문서 하나의 청크를 연달아 호출해야 함. Haiku 4.5는 4,096토큰 미만이면 캐시되지 않음(오류 없음)

## 7. 구현 시 고려사항
- 청크 경계: 크기, 경계, 중첩이 성능에 영향을 줌(원문)
- 임베딩 모델: 원문은 Gemini와 Voyage가 효과적이라 함. 노트북은 입력 한도가 작으면 문맥 붙은 청크가 잘려 나빠질 수 있다고 경고함
- 문맥 프롬프트: 도메인 용어집을 넣으면 좋다고 원문이 제안함
- 청크 수: 5, 10, 20개 중 20개가 최고(원문). 항상 직접 평가하라고 원문이 권함
- 융합 가중치: 노트북은 벡터 0.8, BM25 0.2에 각 150개 후보를 씀(조정 가능). 2차 논문은 1 대 0.25를 썼다고 함
- 리랭킹: 지연과 질의당 비용이 늘어남(원문). 노트북의 100에서 200ms 수치는 근거 불명(미확인)

## 8. 한계와 비판
- 원문 수치는 도메인 평균이며 최고 임베딩 조건임. 평가 데이터 공개 링크가 없고 한국어 수치도 없음
- 독립 연구(arXiv 2504.19754): Phi-3.5-mini, NFCorpus 20%(질의 50개, 문서 약 300개). NDCG@10은 문맥 없는 기본 0.291,  
  문맥만 0.295, 문맥 + 융합 + 리랭킹 0.308로 이득이 작음. 긴 문서는 GPU 메모리 약 20GB를 쓰고 답변 품질 차이는 미미함  
- ConTEB(arXiv 2505.24782, 초록만 확인): 최신 임베딩이 문서 전체 문맥이 필요한 검색에 약하다고 보고함
- Medium 비판 글은 접근 차단(403)으로 읽지 못함. 검색 요약상 "67%가 과장일 수 있다"는 취지(미확인)
- 의견: 색인 비용이 청크 수에 비례하고, 문서가 바뀌면 그 문서 청크를 모두 다시 만들며, 문맥 오류는 샘플 검수가 필요함

## 9. 실습 코드 적용 방법(Chroma + bm25s + Cohere)
현재 `hands-on/solutions/rag/indexing/`은 7단계임. 4단계(청킹)와 5단계(임베딩) 사이에 "문맥 생성"을 끼워 넣음.  
1. 입력은 3단계 가명처리를 거친 문서와 청크를 씀(개인정보 유출 방지, 의견)
2. 문서 단위로 청크마다 Haiku를 호출해 한국어 문맥을 얻음
3. 임베딩 입력은 `문맥 + 청크`. embed-v5.0-fast는 128k 토큰이라 잘릴 걱정이 없음(Cohere 문서)
4. Chroma `upsert`는 documents에 원래 청크, embeddings에 문맥 포함 벡터, metadata에 `context`를 저장함
5. BM25는 `문맥 + 청크`를 `tokenize_korean`(Kiwi)에 넣어 bm25s로 색인함. 질문은 그대로 검색함
6. 문맥 없는 색인과 있는 색인을 같은 질문 세트로 비교함(recall@5, @20). `usage`로 캐시 적중도 확인함

```python
import anthropic
client = anthropic.Anthropic()  # ANTHROPIC_API_KEY 환경변수

CHUNK_PROMPT = """Here is the chunk we want to situate within the whole document
<chunk>
{chunk}
</chunk>
Please give a short succinct context to situate this chunk within the overall document for the purposes of
improving search retrieval of the chunk. Answer only with the succinct context and nothing else.
한국어로 답하고 문서명, 조항 번호, 카드명을 포함할 것."""  # 마지막 줄은 실습용으로 덧붙인 지시

def situate(doc: str, chunk: str):
    r = client.messages.create(
        model="claude-haiku-4-5", max_tokens=200, temperature=0.0,
        messages=[{"role": "user", "content": [
            {"type": "text", "text": f"<document>\n{doc}\n</document>",
             "cache_control": {"type": "ephemeral"}},   # 문서 블록만 캐시
            {"type": "text", "text": CHUNK_PROMPT.format(chunk=chunk)}]}])
    return r.content[0].text.strip(), r.usage  # usage.cache_read_input_tokens로 캐시 확인

for doc in docs:                      # 문서 단위로 연달아 호출해야 캐시 적중
    for ch in doc.chunks:
        ch.context, _ = situate(doc.masked_text, ch.text)
        ch.embed_text = f"{ch.context}\n\n{ch.text}"   # 임베딩과 BM25 입력
```

D2 청크 앞의 `[카드: 이름 (코드)]` 머리말은 사람이 만든 문맥 붙이기와 같은 발상임.

## 10. Late Chunking과의 차이
Late Chunking(arXiv 2409.04701)은 LLM 없이, 긴 문서 전체를 긴 입력용 임베딩 모델에 한 번 통과시켜 토큰별 벡터를 얻은 뒤  
청크 경계로 나눠 평균을 내서 청크 벡터에 문서 문맥을 담음. 비용이 싸지만 토큰별 벡터를 내주는 모델이 필요함(Cohere API는  
입력당 벡터 하나라 어려움, 의견). 글을 안 바꿔 BM25는 개선되지 않음. Contextual Retrieval은 글에 문맥을 써  
넣어 임베딩과 BM25 둘 다 좋아지고 모델 제약이 없지만 LLM 호출 비용이 듦. 독립 비교에서 같은 조건 NDCG@10은 Contextual 0.308,  
Late 0.294로 Contextual이 높았고 계산 비용도 더 컸음(소규모).

## 11. 출처 목록(확인 일자 2026-10-22)
1차(직접 읽음)  
- Anthropic 블로그: https://www.anthropic.com/news/contextual-retrieval
- Anthropic 쿡북 노트북(옛 경로 skills/contextual-embeddings에서 이동됨):  
  https://github.com/anthropics/claude-cookbooks/blob/main/capabilities/contextual-embeddings/guide.ipynb  
- 프롬프트 캐싱 문서: https://platform.claude.com/docs/en/build-with-claude/prompt-caching
- Cohere 임베딩 문서: https://docs.cohere.com/docs/cohere-embed

2차(직접 읽음)  
- Merola와 Singh 논문: https://arxiv.org/abs/2504.19754
- Late Chunking 논문(초록): https://arxiv.org/abs/2409.04701
- ConTEB 논문(초록): https://arxiv.org/abs/2505.24782

## 12. 확인하지 못한 항목
- 블로그 부록(이미지): 도메인별, 임베딩별 수치와 예시 질문
- Medium 비판 글 본문(403), LlamaIndex 구현 노트북(검색 결과에서만 확인)
- Claude 3 Haiku 단가(기억 기반), 블로그가 쓴 리랭커의 정확한 모델명
- 한국어 문서와 embed-v5.0-fast 조합의 효과 수치
- 9절 코드는 실행하지 않음(쿡북과 Anthropic SDK 문서 기준으로 작성)
