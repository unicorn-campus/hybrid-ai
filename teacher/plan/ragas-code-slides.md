# RAGAS 평가 교재 코드 장표 스크립트(W01 ~ W04 「품질 평가 및 튜닝 실습」 간지 뒤)

- 대상: 『신한카드 하이브리드AI_W01 ~ W04』. 「코드로 보기」 장표 3장(옛 189 ~ 191쪽)을 지우고,  
  간지 「품질 평가 및 튜닝 실습」 바로 뒤에 새 장표 13장(워크플로우 구성안 1장 + 코드 장표 12장)을 넣음
- 덱 파일: `teacher/plan/ragas-code.pptx`(13장)
- 발췌: `python teacher/plan/build/extract-ragas-code.py` → `teacher/plan/build/ragas-code-slides.json`
- 빌드: `NODE_PATH="C:\Users\hiond\.npm-global\node_modules" node teacher/plan/build/build-ragas-code.js`
- 교재 반영: `python teacher/plan/build/fix_ph.py teacher/plan/ragas-code.pptx` →  
  `python teacher/plan/build/merge-ragas-code.py {교재}.pptx`(「코드로 보기」 3장 삭제, 간지 뒤에 13장 삽입. 다시 돌리면 같은 제목을 바꿈)
- 코드 규칙: 실제 소스(`hands-on/solutions/ragas/`)에서 발췌기가 자동으로 꺼냄. docstring과 주석은 빼고 나머지 글자는 소스 그대로임.  
  「코드 빼기」에 적은 글이 든 줄(과 그 아래 더 들여 쓴 줄)은 「...」 한 줄로 줄임. 코드를 고치면 발췌와 빌드를 다시 돌림
- 일련번호: 단계 번호 ① ~ ⑤와 헷갈리지 않게 ❶, ❷, ❸ …
- 번호 줄 꼴: `❶ | 코드 줄에서 찾을 글 | 설명 제목 | 설명 본문`. 번호는 앞 번호 줄 다음부터 찾음
- 1장(구성안)은 「코드」 줄이 없는 그림 장표임. 빌더가 이 스크립트의 입력, 단계, 출력, 분기, 표를 읽어 그림

## 슬라이드 1. 평가 워크플로우 구성안
- 넣을 자리: 품질 평가 및 튜닝 실습
- 제목: 평가 워크플로우: 버전 비교 평가 구성안
- 리드문: 하이퍼 파라미터 하나를 바꾼 버전마다 같은 평가셋으로 검색기를 돌리고, 코드 4지표와 LLM 5지표를 같은 잣대로 채점해 기준선과 비교함
- 입력: 평가셋 + 값 범위|10문항, top_k 3 5 10
- 단계 1: ① 버전 만들기|값 하나당 버전 1개, 기준선 ★
- 단계 2: ② 검색기 실행|버전 × 문항, 결과 정보 4칸
- 단계 3: ③ 코드 평가|정답 단서 글자 대조, 4지표
- 단계 4: ④ LLM 평가|평가자 LLM이 5지표(ragas)
- 단계 5: ⑤ 버전 비교|평균, 기준선 대비 ▲ ▼, 원인
- 출력: 결과 파일|버전마다 1개(.md)
- 분기 2: 근거 0개(근거 부족, 되묻기)면 ③ 0점, ④ 채점 안 함|답 없는 문항(Q20, Q21)은 「확인 필요」로 끝났는지만 봄
- 분기 4: 지표마다 읽는 칸이 다름(질문, 모범 답안, 검색 결과, 답변)|채점 실패는 nan으로 두고 평균에서 뺌
- 분기 5: 흔들림 폭보다 큰 차이만 ▲, ▼(교재 177쪽)|떨어진 지표 조합으로 고칠 곳 후보(교재 187쪽)
- 표 열 너비: [1.5, 6.9, 2.3, 4.2]

| 단계 | 하는 일 | 판단 방식 | 핵심 코드 |
|---|---|---|---|
| ① 버전 만들기 | 값 목록으로 v01, v02, …를 만들고 나머지 설정은 기준선 값으로 고정함 | 코드 규칙 | build_versions |
| ② 검색기 실행 | 문항마다 run_workflow를 불러 질문, 모범 답안, 검색 결과, 답변을 한 행에 모음 | 검색기(LLM 포함) | make_result_row, clean_for_ragas |
| ③ 코드 평가 | 적중 청크를 판정하고 하(Hit), 빠(Recall), 빨(MRR), 앞(nDCG)을 계산함 | 코드 계산(LLM 없음) | find_hits, retrieval_metrics, ndcg_at_k |
| ④ LLM 평가 | 위, 정, 출, 관, 답 5지표를 평가자 LLM이 문항마다 판정함 | 평가자 LLM + 임베딩 | build_metrics, score_row, @experiment |
| ⑤ 버전 비교 | 버전별 매크로 평균, 기준선 대비 변화, 원인 후보를 내고 결과 파일을 씀 | 코드 규칙 | summarize_versions, diagnose |

- 화면 출처: hands-on/solutions/ragas/evaluate_rag.py, core_eval.py, teacher/plan/ragas-개발계획서.md 4장, 교재 177, 188쪽
- 발표자 노트:
  - 교재 177쪽 「버전 비교 평가」를 실습 예제의 단계 번호로 다시 그린 그림입니다. 검색기(150쪽 ① ~ ⑥)는 ②에서 통째로 부릅니다
  - 교재 178쪽은 실험 함수 안에서 검색과 채점을 함께 하지만, 실습은 ② 실행을 먼저 끝내고 그 결과 정보로 ③, ④를 채점합니다(188쪽 구조)
  - 남색 상자 5개가 모두 실습 예제에 코드가 있습니다. 이어지는 장표는 단계 순서대로 실제 코드를 봅니다
  - 실행 옵션 --until로 ①, ②, ③까지만 돌릴 수 있고, --selftest는 API 없이 ③과 ⑤의 계산 함수만 점검합니다

## 슬라이드 2. ① 버전 만들기
- 넣을 자리: 평가 워크플로우: 버전 비교 평가 구성안
- 제목: 평가 워크플로우: ① 버전 만들기 – 실제 코드
- 리드문: 하이퍼 파라미터 하나의 값 목록을 버전 목록으로 바꿈. 기준선이 값 목록에 없으면 비교할 잣대가 없으므로 멈춤
- 코드: core_eval.py build_versions
- 코드 빼기
  - seen = []
  - if value in seen:
  - seen.append(value)
- 번호
  - ❶ | if param not in supported: | 지원 목록 검사 | 재색인이 필요한 값(청크 크기, 임베딩 모델)은 지원 목록에 없으므로 여기서 멈춤
  - ❷ | if baseline is None: | 기준선 기본값 | --baseline을 안 주면 검색기의 현재 값(top_k 5)이 기준선임
  - ❸ | if baseline not in values: | 기준선도 돌려야 함 | 같은 실행에서 기준선을 함께 채점해야 같은 잣대로 비교할 수 있음(교재 177쪽)
  - ❹ | "name": f"v{number:02d}", | 버전 이름 | v01, v02, …. 결과 파일 이름의 vNN이 됨. 같은 값은 한 번만 버전으로 만듦(...)
  - ❺ | "is_baseline": value == baseline, | 기준선 표시 | 비교표에서 ★로 보이고, 흔들림 폭 반복 채점(--repeat)도 이 버전만 함
- 굵게
  - param not in supported
  - baseline not in values
  - value == baseline
- 상세 보기 링크: https://github.com/unicorn-campus/hybrid-ai/blob/main/hands-on/solutions/ragas/core_eval.py
- 발표자 노트:
  - 교육생 실습 함수 build_versions(직접 작성)의 정답임
  - 한 번에 하나만 바꾸는 규칙은 main의 apply_version이 지킵니다. 버전이 끝날 때마다 검색기 설정을 원래 값으로 되돌립니다
  - 확인: --param top_k --values 3 5 10 --until versions → v01 3, v02 5 ★, v03 10. --values 3 10이면 기준선 없음 오류

## 슬라이드 3. ② 결과 정보
- 넣을 자리: 평가 워크플로우: ① 버전 만들기 – 실제 코드
- 제목: 평가 워크플로우: ② 검색기 실행 – 결과 정보 실제 코드
- 리드문: 문항 1건 = 결과 정보 4칸(교재 188쪽). 질문과 모범 답안은 평가셋이, 검색 결과와 답변은 검색기가 채움. ragas에 넘기기 전에 회원번호와 인용 표시를 지움
- 코드: core_eval.py make_result_row; evaluate_rag.py clean_for_ragas
- 코드 빼기
  - "answerable": item["answerable"],
  - "status": result["status"],
  - "question": item["question"],
  - "answer": result["answer"],
  - "chunk_ids": chunk_ids,
  - "relevance": item["relevance"],
  - chunk_ids = []
  - chunk_ids.append
- 번호
  - ❶ | for hit in result["evidence"]: | 검색 결과 | 검색기가 ⑤ 답변 생성에 넘긴 근거(리랭크 순서)의 본문만 모음. 근거 0개로 끝난 문항은 빈 목록
  - ❷ | row["user_input"] = question_for_ragas | 질문 | 회원번호를 지운 질문. 검색기가 답변 생성에 넘긴 것과 같은 문장
  - ❸ | row["reference"] = item["ground_truth"] | 모범 답안 | 평가셋 ground_truth. 위, 정, 답 지표가 읽음
  - ❹ | row["response"] = answer_for_ragas | 답변 | 인용 표시를 뺀 글. 출, 관, 답 지표가 읽음
  - ❺ | MEMBER_ID_PATTERN.sub | 정리 이유 | 평가자는 답변을 주장으로 쪼갤 때 「M-3001」과 「[D3-0019]」까지 주장에 넣는데 색인 본문에 없어 Faithfulness가 0이 됨(실측). 모든 버전에 같게 적용함
- 굵게
  - user_input
  - reference
  - retrieved_contexts
  - response
- 상세 보기 링크: https://github.com/unicorn-campus/hybrid-ai/blob/main/hands-on/solutions/ragas/core_eval.py
- 발표자 노트:
  - 교육생 실습 함수 make_result_row(빈칸 2곳: ❶의 본문 더하기, ❷ ~ ❹의 4칸)의 정답임. clean_for_ragas는 main의 제공 함수임
  - 장표에서는 결과 파일용 칸(answerable, status, 원 질문, 원 답변, chunk_ids, relevance)을 ...로 줄였습니다
  - 확인: --until run --qid Q17 → user_input이 「회원과 상담할 때 …」로 시작하고 response에 [D3-…]이 없음

## 슬라이드 4. ③ 적중 청크 판정
- 넣을 자리: 평가 워크플로우: ② 검색기 실행 – 결과 정보 실제 코드
- 제목: 평가 워크플로우: ③ 코드 평가 – 적중 청크 판정 실제 코드
- 리드문: 검색 결과 청크마다 정답 단서가 글자 그대로 있는지 봄. 적중 청크 순위와 찾은 정답 근거를 돌려주고, 같은 정답 근거는 한 번만 셈
- 코드: core_eval.py find_hits
- 코드 빼기
  - evidence_by_rank
  - "evidence_count": len(relevance),
- 번호
  - ❶ | for rank, chunk_text in enumerate(chunk_texts, start=1): | 순위마다 | 상위 k개 청크를 1위부터 봄. compact_text로 띄어쓰기와 줄바꿈을 지운 본문과 비교함(PDF 줄바꿈 차이)
  - ❷ | for number, evidence in enumerate(relevance, start=1): | 정답 근거마다 | 정답 근거 번호(①이 1). 정답 근거 하나에 정답 단서(clues)가 여러 개일 수 있음
  - ❸ | if compact_text(clue) in body: | 글자 대조 | 단서도 공백을 지우고 본문에 그대로 있는지 봄. LLM 없이 같은 입력이면 같은 결과
  - ❹ | found_evidence.add(number) | 한 번만 셈 | 집합(set)이라 같은 정답 근거가 2위와 4위에 모두 있어도 하나로 셈(교재 181쪽 4위의 ①). break로 같은 근거의 다른 단서는 보지 않음
  - ❺ | hit_ranks.append(rank) | 적중 청크 | 정답 근거를 하나라도 담은 청크의 순위 목록. 4지표가 모두 이 목록을 씀
- 굵게
  - compact_text(clue) in body
  - found_evidence.add(number)
- 상세 보기 링크: https://github.com/unicorn-campus/hybrid-ai/blob/main/hands-on/solutions/ragas/core_eval.py
- 발표자 노트:
  - 교육생 실습 함수 find_hits(직접 작성)의 정답임
  - 장표에서는 결과 파일 표시용 evidence_by_rank(순위마다 담긴 정답 근거 번호)를 ...로 줄였습니다
  - 확인: --selftest에서 적중 순위 [2, 4]. 181쪽 예의 2위 청크에 줄바꿈이 있어도 찾아야 합니다

## 슬라이드 5. ③ 하, 빠, 빨
- 넣을 자리: 평가 워크플로우: ③ 코드 평가 – 적중 청크 판정 실제 코드
- 제목: 평가 워크플로우: ③ 코드 평가 – 하, 빠, 빨 실제 코드
- 리드문: 같은 적중 판정을 세 가지 질문으로 읽음. 하(Hit)는 답할 재료를 하나라도 건졌나, 빠(Recall)는 정답 근거를 빠짐없이 찾았나, 빨(MRR)은 첫 적중이 몇 위인가
- 코드: core_eval.py retrieval_metrics
- 번호
  - ❶ | if hits["evidence_count"] == 0: | 답 없는 문항 | 정답 근거 0개면 Recall 분모가 0이라 계산하지 않고 None(교재 181쪽). 평균에서 뺌
  - ❷ | if rank <= k: | 상위 k개만 | 적중 순위 중 k 이하만 남김. k 밖의 적중은 이 지표에 들어가지 않음
  - ❸ | hit = 1 | 하 Hit@k | 상위 k개 안 적중 청크가 하나라도 있으면 1. 몇 개인지, 몇 위인지는 안 봄
  - ❹ | recall = len(hits["found_evidence"]) / hits["evidence_count"] | 빠 Recall@k | 찾은 정답 근거 수 ÷ 전체 정답 근거 수. 세는 단위는 청크가 아니라 정답 근거(교재 180쪽)
  - ❺ | mrr = 1 / first_rank | 빨 MRR | 첫 적중 청크 순위의 역수. 2위면 0.50. 적중이 없으면 0. 여러 문항의 평균이 MRR(교재 181쪽)
- 굵게
  - len(hits["found_evidence"]) / hits["evidence_count"]
  - 1 / first_rank
- 상세 보기 링크: https://github.com/unicorn-campus/hybrid-ai/blob/main/hands-on/solutions/ragas/core_eval.py
- 발표자 노트:
  - 교육생 실습 함수 retrieval_metrics(직접 작성)의 정답임
  - 확인: --selftest에서 181쪽 예 Hit 1, Recall 0.67, MRR 0.50. 4위 청크의 정답 근거 ①을 두 번 세면 Recall이 1.00으로 틀립니다
  - Hit과 MRR은 첫 적중 청크만 보고, Recall은 정답 근거 전부를 봅니다(180쪽 노트 「짝으로 봄」)

## 슬라이드 6. ③ 앞(nDCG)
- 넣을 자리: 평가 워크플로우: ③ 코드 평가 – 하, 빠, 빨 실제 코드
- 제목: 평가 워크플로우: ③ 코드 평가 – 앞(nDCG) 실제 코드
- 리드문: 앞(nDCG@k) = DCG ÷ IDCG. 적중 청크가 위에 있을수록 점수가 크고, 이상적인 순서(관련 청크를 1위부터 채움)와 견줘 0 ~ 1로 맞춤
- 코드: core_eval.py ndcg_at_k
- 번호
  - ❶ | if relevant_chunk_count == 0: | 관련 청크 0개 | IDCG가 0이 되어 나눌 수 없음(답 없는 문항) → None
  - ❷ | dcg = dcg + rank_weight(rank) | DCG | 상위 k개 안 적중 칸의 순위 가중치 1 ÷ log₂(순위 + 1)을 더함. 1위 1.00, 2위 0.63, 3위 0.50, 4위 0.43, 5위 0.39
  - ❸ | ideal_count = min(relevant_chunk_count, k) | 이상적인 칸 수 | 관련 청크(색인 전체에서 정답 단서를 담은 청크)가 1위부터 몇 칸을 채우나. k칸이 최대
  - ❹ | idcg = idcg + rank_weight(rank) | IDCG | 1위부터 ideal_count위까지의 가중치 합. 관련 청크 수 기준이라 nDCG가 1을 넘지 않음(181쪽 노트의 걱정이 사라짐)
  - ❺ | return dcg / idcg | nDCG | 181쪽 예: (0.63 + 0.43) ÷ (1.00 + 0.63 + 0.50 + 0.43) = 0.41. Q17 기준선 0.97(185쪽)
- 굵게
  - rank_weight(rank)
  - min(relevant_chunk_count, k)
  - dcg / idcg
- 상세 보기 링크: https://github.com/unicorn-campus/hybrid-ai/blob/main/hands-on/solutions/ragas/core_eval.py
- 발표자 노트:
  - 교육생 실습 함수 ndcg_at_k(빈칸 2곳: ❷, ❹의 더하기)의 정답임. rank_weight는 제공 함수임
  - 관련 청크 수는 main이 시작할 때 색인 260청크에서 정답 단서를 대조해 문항마다 한 번 셉니다. 어느 청크에도 없는 정답 단서가 있으면 멈춥니다
  - Q07처럼 관련 청크가 많은 문항(38개)은 k가 커질수록 nDCG가 내려갑니다(README 7.3)

## 슬라이드 7. ④ 평가자와 지표
- 넣을 자리: 평가 워크플로우: ③ 코드 평가 – 앞(nDCG) 실제 코드
- 제목: 평가 워크플로우: ④ LLM 평가 – 평가자와 지표 실제 코드
- 리드문: 평가자 LLM(Groq Qwen)과 임베딩(Cohere)을 OpenAI 호환 주소로 만들고, ragas 0.4.3 collections 지표 5개를 만듦. 모범 답안이 있으므로 Precision은 WithReference
- 코드: evaluate_rag.py build_judge; core_eval.py build_metrics
- 코드 빼기
  - timeout=JUDGE_TIMEOUT_SECONDS,
  - max_retries=JUDGE_MAX_RETRIES,
- 번호
  - ❶ | judge_client = AsyncOpenAI( | 평가자 클라이언트 | Groq의 OpenAI 호환 주소를 openai 패키지로 부름. 답변 LLM과 다른 모델(Qwen)이라 자기 채점이 아님
  - ❷ | llm = llm_factory( | ragas 0.4 방식 | LangChain 래퍼는 0.4에서 deprecated라 llm_factory에 클라이언트를 직접 넘김
  - ❸ | embeddings = OpenAIEmbeddings( | 임베딩 | 인덱서와 같은 Cohere 모델을 OpenAI 호환 주소로. AnswerRelevancy만 씀
  - ❹ | "context_recall": ContextRecall(llm=llm), | 정, 출, 답 | 평가자 LLM만 있으면 되는 지표 3개. 답은 기본 F1
  - ❺ | metrics["context_precision"] = ContextPrecisionWithReference(llm=llm) | 위 | 모범 답안이 있으므로 WithReference. 없으면 WithoutReference(답변 기준)
  - ❻ | metrics["answer_relevancy"] = AnswerRelevancy(llm=llm, embeddings=embeddings) | 관 | 역질문과 원래 질문을 임베딩으로 비교하므로 embeddings도 넘김
- 굵게
  - llm_factory
  - ContextPrecisionWithReference
  - embeddings=embeddings
- 상세 보기 링크: https://github.com/unicorn-campus/hybrid-ai/blob/main/hands-on/solutions/ragas/core_eval.py
- 발표자 노트:
  - 교육생 실습 함수 build_metrics(빈칸 2곳: ❺, ❻)의 정답임. build_judge는 main의 제공 함수임
  - 평가자가 다르면 점수도 다릅니다. 184 ~ 185쪽 실제 예(Claude Haiku 5.5)와 값을 직접 비교하지 않습니다(README 9장)
  - ragas 0.4.3 collections 지표는 판정 이유(reason)를 채우지 않습니다(실측). 점수(value)만 씁니다

## 슬라이드 8. ④ 한 행 채점: 검색 지표
- 넣을 자리: 평가 워크플로우: ④ LLM 평가 – 평가자와 지표 실제 코드
- 제목: 평가 워크플로우: ④ LLM 평가 – 한 행 채점(위, 정) 실제 코드
- 리드문: 결과 정보 한 행을 지표 5개로 채점함. 지표마다 읽는 칸이 다르므로(교재 188쪽) 맞는 칸을 맞는 이름으로 넘김. 먼저 검색 지표 둘
- 코드: core_eval.py score_row
- 코드 빼기
  - errors = {}
  - scores["errors"] = errors
  - scores["faithfulness"] = await ascore_or_nan(
  - scores["answer_relevancy"] = await ascore_or_nan(
  - scores["factual_correctness"] = await ascore_or_nan(
- 번호
  - ❶ | question = row["user_input"] | 읽는 칸 4개 | 질문, 모범 답안, 검색 결과(청크 본문 목록), 답변. 188쪽 결과 정보 4칸 그대로
  - ❷ | scores["context_precision"] = await ascore_or_nan( | 위 ContextPrecision | 질문, 모범 답안, 검색 결과를 읽음. 청크마다 모범 답안에 쓸모 있나 1/0 → 순위대로 평균 정밀도
  - ❸ | user_input=question, reference=reference, retrieved_contexts=contexts) | 칸 이름 | ragas가 정한 영어 이름을 그대로 씀. await는 평가자 호출이 끝날 때까지 기다림(비동기)
  - ❹ | scores["context_recall"] = await ascore_or_nan( | 정 ContextRecall | 질문, 검색 결과, 모범 답안을 읽음. 모범 답안을 주장으로 쪼개 검색 결과에 있나
  - ❺ | ... | 나머지 3개 | 출, 관, 답은 다음 장. 실패한 지표는 ascore_or_nan이 사유를 적고 nan을 돌려줘 다음 지표로 감
- 굵게
  - user_input=question, reference=reference, retrieved_contexts=contexts)
  - user_input=question, retrieved_contexts=contexts, reference=reference)
- 상세 보기 링크: https://github.com/unicorn-campus/hybrid-ai/blob/main/hands-on/solutions/ragas/core_eval.py
- 발표자 노트:
  - 교육생 실습 함수 score_row(빈칸 5곳)의 정답 앞부분임(빈칸 1, 2). 뒷부분은 다음 장
  - ascore_or_nan은 제공 함수로, metric.ascore(**칸)를 기다려 MetricResult.value를 실수로 돌려주고 예외면 사유를 적고 nan을 돌려줍니다
  - 칸 이름을 틀리면 TypeError가 「채점 실패」로 결과 파일에 남습니다

## 슬라이드 9. ④ 한 행 채점: 답변 지표
- 넣을 자리: 평가 워크플로우: ④ LLM 평가 – 한 행 채점(위, 정) 실제 코드
- 제목: 평가 워크플로우: ④ LLM 평가 – 한 행 채점(출, 관, 답) 실제 코드
- 리드문: 답변 지표 셋. 출(Faithfulness)은 검색 결과 기준, 답(FactualCorrectness)은 모범 답안 기준이라 대조 대상이 다름(교재 185쪽)
- 코드: core_eval.py score_row
- 코드 빼기
  - errors = {}
  - scores["context_precision"] = await ascore_or_nan(
  - scores["context_recall"] = await ascore_or_nan(
- 번호
  - ❶ | ... | 앞 장 | 위, 정 채점(검색 지표)
  - ❷ | scores["faithfulness"] = await ascore_or_nan( | 출 Faithfulness | 질문, 답변, 검색 결과. 모범 답안은 읽지 않음(근거 기준 환각 탐지)
  - ❸ | scores["answer_relevancy"] = await ascore_or_nan( | 관 AnswerRelevancy | 질문과 답변만. 답변으로 역질문을 만들어 원래 질문과 임베딩 유사도
  - ❹ | scores["factual_correctness"] = await ascore_or_nan( | 답 FactualCorrectness | 답변과 모범 답안만. 검색 결과는 읽지 않음(모범 답안 기준 사실 정확도, 기본 F1)
  - ❺ | scores["errors"] = errors | 실패 사유 | 지표별 실패 사유 dict를 점수와 함께 돌려줌. 결과 파일의 「채점 실패」 칸이 됨
- 굵게
  - user_input=question, response=answer, retrieved_contexts=contexts)
  - user_input=question, response=answer)
  - response=answer, reference=reference)
- 상세 보기 링크: https://github.com/unicorn-campus/hybrid-ai/blob/main/hands-on/solutions/ragas/core_eval.py
- 발표자 노트:
  - 교육생 실습 함수 score_row(빈칸 5곳)의 정답 뒷부분임(빈칸 3 ~ 5)
  - 5개를 차례로(await) 부르는 이유는 Groq 호출 제한 안에서 동시 호출 수를 예측하기 위함입니다. 행끼리는 동시에 돕니다(다음 장)
  - 실측(README 7.4): 답 FactualCorrectness는 답변 주장 하나에 모범 답안에 없는 낱말(「할부」)이 있으면 0점이 됩니다. 출 Faithfulness와 함께 읽습니다

## 슬라이드 10. ④ 실험 실행
- 넣을 자리: 평가 워크플로우: ④ LLM 평가 – 한 행 채점(출, 관, 답) 실제 코드
- 제목: 평가 워크플로우: ④ LLM 평가 – 실험 실행 실제 코드
- 리드문: 채점할 행을 ragas Dataset에 담고 @experiment 실험 함수를 arun으로 돌림(교재 178쪽). 모든 행을 한꺼번에 돌리므로 동시 채점 수를 세마포어로 제한함
- 코드: evaluate_rag.py run_llm_evaluation
- 코드 빼기
  - dataset.append({
- 번호
  - ❶ | dataset = Dataset( | 평가셋 담기 | 한 문항 = 한 행(4칸 + id. 장표에서는 ...로 줄임). 메모리(inmemory)에만 두고 파일은 만들지 않음
  - ❷ | semaphore = asyncio.Semaphore(MAX_CONCURRENT_ROWS) | 동시 채점 제한 | 세마포어 = 동시에 들어갈 수 있는 수를 세는 문지기. 2행씩 채점해 Groq 429(호출 제한)를 피함
  - ❸ | @experiment() | 실험 함수 | 데코레이터가 함수에 arun을 붙여 줌. 한 행(dict)을 받아 점수 행을 돌려줌
  - ❹ | scores = await core.score_row(row, metrics) | 한 행 채점 | 앞 장의 score_row. 자리가 날 때까지 기다렸다가(async with) 들어감
  - ❺ | experiment_result = await ragas_eval.arun(dataset, name=experiment_name) | 문항 × 지표 표 | arun이 모든 행을 동시에 돌리고 표로 모음. 실패한 행은 경고만 남기고 뺌
- 굵게
  - @experiment()
  - arun(dataset, name=experiment_name)
- 상세 보기 링크: https://github.com/unicorn-campus/hybrid-ai/blob/main/hands-on/solutions/ragas/evaluate_rag.py
- 발표자 노트:
  - main의 읽기 구간입니다(실습 함수 아님). 교재 178쪽 코드와 같은 모양이며, 교재 178쪽의 local/csv 저장 대신 메모리에만 둡니다
  - 버전 전체를 이벤트 루프 하나(asyncio.run 한 번)에서 돌립니다. 버전마다 루프를 새로 만들면 같은 API 클라이언트가 닫힌 루프를 쓰다 오류가 납니다
  - --repeat 3이면 기준선만 3번 돌려 지표별 흔들림 폭(회차 평균의 최대 - 최소)을 잽니다(교재 177쪽)

## 슬라이드 11. ⑤ 버전별 평균
- 넣을 자리: 평가 워크플로우: ④ LLM 평가 – 실험 실행 실제 코드
- 제목: 평가 워크플로우: ⑤ 버전 비교 – 버전별 평균 실제 코드
- 리드문: 버전마다 지표별 평균을 냄. 문항마다 점수를 먼저 내고 그 평균을 내는 매크로 평균(교재 181쪽)이라 정답 근거가 많은 문항에 무게가 쏠리지 않음
- 코드: core_eval.py summarize_versions
- 코드 빼기
  - baseline_means = summary[baseline_name]["mean"]
  - for version_name, version_summary in summary.items():
  - return summary
- 번호
  - ❶ | for version_name, rows in rows_by_version.items(): | 버전마다 | rows는 그 버전의 문항 점수 dict 목록(키 = 지표 이름)
  - ❷ | values.append(row.get(metric)) | 문항 점수 모으기 | 채점하지 않은 칸(답 없음, 근거 0개)은 None, 채점 실패는 nan
  - ❸ | means[metric] = mean_of(values) | 매크로 평균 | 제공 함수 mean_of가 None과 nan을 빼고 평균함. 남는 값이 없으면 None
  - ❹ | summary[version_name] = {"mean": means, "delta": {}, "change": {}} | 버전 요약 | delta(기준선과의 차이)와 change(▲, ▼, 변화 없음)는 다음 장에서 채움
- 굵게
  - mean_of(values)
- 상세 보기 링크: https://github.com/unicorn-campus/hybrid-ai/blob/main/hands-on/solutions/ragas/core_eval.py
- 발표자 노트:
  - 교육생 실습 함수 summarize_versions(직접 작성)의 정답 앞부분임. 뒷부분(기준선 대비 변화)은 다음 장
  - 답 있는 8문항 중 6문항이 정답 근거 1개라 한 문항이 바뀌면 Recall 평균이 0.125 움직입니다. 통계적 유의성은 주장하지 않습니다(README 5.2)

## 슬라이드 12. ⑤ 기준선 대비 변화
- 넣을 자리: 평가 워크플로우: ⑤ 버전 비교 – 버전별 평균 실제 코드
- 제목: 평가 워크플로우: ⑤ 버전 비교 – 기준선 대비 변화 실제 코드
- 리드문: 기준선과의 차이를 흔들림 폭과 견줌. 점수 0.8 같은 고정 합격선 대신 기준선 대비 변화로 채택 여부를 정함(교재 187쪽)
- 코드: core_eval.py summarize_versions
- 코드 빼기
  - summary = {}
  - for version_name, rows in rows_by_version.items():
  - if version_name == baseline_name:
  - if mean is None or base is None:
- 번호
  - ❶ | baseline_means = summary[baseline_name]["mean"] | 기준선 평균 | 앞 장에서 낸 버전별 평균 중 기준선(★) 것
  - ❷ | ... | 비교하지 않는 경우 | 기준선 자신은 「-」, 어느 한쪽이 None이면 「비교 불가」(장표에서 ...로 줄임)
  - ❸ | delta = mean - base | 기준선 대비 차이 | +면 나아짐. 결과 파일의 「▲ +0.125」 같은 숫자
  - ❹ | if delta > noise[metric]: | 흔들림 폭과 견줌 | 다시 채점만 해도 생기는 폭보다 크게 올랐을 때만 ▲, 크게 내렸을 때만 ▼, 그 사이는 「변화 없음」(교재 177쪽)
- 굵게
  - mean - base
  - delta > noise[metric]
  - delta < -noise[metric]
- 상세 보기 링크: https://github.com/unicorn-campus/hybrid-ai/blob/main/hands-on/solutions/ragas/core_eval.py
- 발표자 노트:
  - 교육생 실습 함수 summarize_versions(직접 작성)의 정답 뒷부분임
  - 흔들림 폭은 상수 0.03(교재 177쪽 예시값)에서 출발하고, --repeat 3이면 기준선 반복 채점 실측값으로 바꿉니다. 실측에서는 평가자가 temperature 0.01이라 대부분 0.000이었고 Faithfulness만 한 번 0.125였습니다
  - 1회차 실측에서 코드 지표 ▲ +0.125는 기준선 Q17이 되묻기로 끝난 검색기 흔들림이었습니다(README 7.3). 평균만 보지 말고 문항별 표를 함께 봅니다

## 슬라이드 13. ⑤ 원인 찾기
- 넣을 자리: 평가 워크플로우: ⑤ 버전 비교 – 기준선 대비 변화 실제 코드
- 제목: 평가 워크플로우: ⑤ 원인 찾기 – 실제 코드
- 리드문: 기준선보다 떨어진(▼) 지표의 조합으로 검색, 순위, 생성 중 어디를 고칠지 고름(교재 187쪽 표). 지표 하나만 보면 놓침
- 코드: core_eval.py diagnose
- 코드 빼기
  - if change.get("ndcg") == "▼":
  - if change.get("faithfulness") == "▼":
  - if change.get("answer_relevancy") == "▼":
  - if len(reasons) == 0:
- 번호
  - ❶ | if change.get("recall") == "▼": | 코드 지표 | LLM 평가를 안 돌려도 나옴. Recall ↓는 정답 근거를 놓친 것 → 청킹, 임베딩, Top-k
  - ❷ | context_recall_dropped = change.get("context_recall") == "▼" | 정 ↓ | 검색 정답률 → 청킹, 임베딩, Top-k. change.get은 지표가 없으면 None이라 조건이 거짓
  - ❸ | context_precision_dropped = change.get("context_precision") == "▼" | 위 ↓ | 상위에 답이 적음 → 리랭커, 하이브리드 비중
  - ❹ | if change.get("factual_correctness") == "▼": | 답 ↓ | 정 ↓와 함께면 검색이 근거를 못 가져온 것, 정이 정상이면 답변이 근거 일부만 담은 것(교재 185쪽 Q17) → 답변 프롬프트
- 굵게
  - context_recall_dropped
  - context_precision_dropped
- 상세 보기 링크: https://github.com/unicorn-campus/hybrid-ai/blob/main/hands-on/solutions/ragas/core_eval.py
- 발표자 노트:
  - 교육생 실습 함수 diagnose(빈칸 3곳: ❷, ❸, ❹의 갈림)의 정답임
  - 장표에서는 nDCG ↓, Faithfulness ↓(답변 프롬프트), Answer Relevancy ↓(질문 변환, 답변 프롬프트), 떨어진 지표 없음 문장을 ...로 줄였습니다
  - 실측(README 7장)에서 1회차는 기준선 Q17이 되묻기로 끝나 코드 지표가 ▲ +0.125로 보였는데, 이는 검색기 흔들림이지 top_k 효과가 아니었습니다. 원인 후보를 읽기 전에 문항별 표를 먼저 봐야 하는 이유입니다
