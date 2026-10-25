# 그래프 검색 교재 코드 예시 장표 스크립트(W05 ~ W07 64 ~ 79쪽 단계별 설명 뒤)

- 덱 파일: `teacher/plan/graph-search-code.pptx`(14장)
- 발췌: `python teacher/plan/build/extract-graph-search-code.py` → `teacher/plan/build/graph-search-code-slides.json`
- 빌드: `NODE_PATH="C:\Users\hiond\.npm-global\node_modules" node teacher/plan/build/build-graph-search-code.js`
- 교재 넣기: `python teacher/plan/build/merge-graph-search-code.py {교재}.pptx`(「넣을 자리」 제목의 장표 바로 뒤에 넣음. 다시 돌리면 옛 코드 장표를 지우고 새로 넣음)
- 레이아웃: 본 덱 `내용_단쪽`. 교재 48, 61쪽 코드 장표와 같은 모양(왼쪽 실제 코드, 오른쪽 번호별 설명)
- 코드 규칙: 실제 소스(`hands-on/solutions/graphrag/retriever/`)에서 발췌기가 자동으로 꺼냄. docstring, 줄 전체 주석, 줄 끝 주석은 빼고  
  나머지 글자는 소스 그대로임. 「코드 빼기」에 적은 줄은 「...」 한 줄로 줄임. 코드를 고치면 발췌와 빌드를 다시 돌림
- 일련번호: 단계 번호 ① ~ ⑩과 헷갈리지 않게 ❶, ❷, ❸ …(강사 결정 D7)
- 번호 줄 꼴: `❶ | 코드 줄에서 찾을 글 | 설명 제목 | 설명 본문`(찾을 글 안에 「 | 」가 있어도 됨. 뒤의 두 칸이 제목과 본문)  
- 번호는 앞 번호 줄 다음부터 찾음. 「코드 번호 마지막 줄 찾기」에 적은 번호는 맨 마지막으로 나온 줄에 붙임

## 슬라이드 1. ② 질문 분석
- 넣을 자리: 3. 검색: ① 요청 접수, ② 질문 분석
- 제목: 3. 검색: ② 질문 분석 – 실제 코드
- 리드문: Jev가 낸 확률을 코드가 기준값과 비교해 「끝낼지, 첫 툴 후보는 무엇인지」를 정함. 결정은 늘 코드가 함
- 코드: core_search.py decide_question_route
- 번호
  - ❶ | if answers is None: | Jev가 실패하면 | 끝내지도 후보를 주지도 않고 검색으로 감. 잘못 끝내는 쪽이 손해가 더 큼
  - ❷ | answers["is_smalltalk"] >= | 잡담이면 끝냄 | Noul 확률이 기준값 0.7 이상일 때만 「검색 불필요」
  - ❸ | answers["needs_clarification"] >= | 모호하면 끝냄 | 0.7 이상일 때만 「확인 필요」. 0.3 ~ 0.7은 애매하므로 검색으로 감
  - ❹ | tool_swapped, confidence_swapped = | 보기 순서를 바꾼 답 | main이 Choice 보기 순서를 뒤집어 한 번 더 물은 답(첫 보기 쏠림 대비)
  - ❺ | if tool == tool_swapped and | 첫 툴 후보 | 두 답이 같고 두 확신이 모두 0.5 이상일 때만 후보로 씀. 후보는 권고일 뿐임
- 굵게
  - thresholds["end_noul"]
  - tool == tool_swapped
  - thresholds["choice_confidence"]
- 상세 보기 링크: https://github.com/unicorn-campus/hybrid-ai/blob/main/hands-on/solutions/graphrag/retriever/core_search.py
- 발표자 노트
  - 교육생 실습 함수 decide_question_route(직접 작성)의 정답임
  - Jev 호출은 main의 jev_route가 함. 잡담, 모호 Noul 2개와 첫 툴 Choice를 한 요청으로, 보기 순서를 뒤집은 Choice를 한 번 더 물음
  - 「모호함」 질문 문장은 실측으로 고름. 「어느 카드인지 안 밝힘」으로 물었더니 일반 약관 질문까지 0.9로 막았음

## 슬라이드 2. ③ 검색 에이전트
- 넣을 자리: 3. 검색: ③ 검색 에이전트
- 제목: 3. 검색: ③ 검색 에이전트 – 실제 코드
- 리드문: LangChain create_agent로 ReAct 고리를 만들고 한 번 돌림. 막는 일은 함께 넘긴 미들웨어가 맡음
- 코드: core_search.py build_agent
- 번호
  - ❶ | agent = create_agent( | 에이전트 만들기 | 「모델 → 툴 → 모델」 고리를 LangGraph 그래프로 만들어 줌
  - ❷ | model=model, | Groq gpt-oss-120b | 다음 툴과 질의를 고름. G1, G2, ⑧과 같은 모델, reasoning_effort medium
  - ❸ | tools=tools, | 툴 6개 | 검색 툴 5개 + finish. 입력에 필터 칸이 없음
  - ❹ | middleware=middleware, | 미들웨어 | 상한과 강제 종료(GuardMiddleware), 래퍼와 채점(ToolWrapperMiddleware)
  - ❺ | context=context, | 작업 기록 | 툴과 미들웨어가 함께 보는 이 요청의 기록(필터, 모은 근거, 회차)
  - ❻ | config={"recursion_limit": | 안전 상한 | 프레임워크 쪽 상한. 코드 상한(6회차)보다 넉넉히 둠
- 굵게
  - create_agent(
  - agent.invoke(
- 상세 보기 링크: https://github.com/unicorn-campus/hybrid-ai/blob/main/hands-on/solutions/graphrag/retriever/core_search.py
- 발표자 노트
  - 교육생 실습 함수 build_agent(빈칸 2곳)의 정답임. 빈칸은 create_agent 호출과 invoke 호출
  - 메시지는 덧붙이기만 됨(append-only). 앞부분이 같은 입력은 Groq가 자동으로 캐시해 회차가 늘어도 입력 비용이 작음
  - 에이전트 모델은 처음 설계의 Claude Opus 5.5에서 Groq로 바꿈(강사 결정 2026-10-25). 비교 실험에서 품질은 거의 같고 더 빠르고 쌌음

## 슬라이드 3. ④ 툴 실행 래퍼
- 넣을 자리: 3. 검색: ④ 툴 실행 – 검색 툴 5개
- 제목: 3. 검색: ④ 툴 실행 – 래퍼 실제 코드
- 리드문: 에이전트의 툴 호출 하나를 감싸 입력을 검사하고, 질의 속 식별자를 지우고, 필터를 강제로 붙여 서브 워크플로우를 부름
- 코드: core_search.py run_tool
- 번호
  - ❶ | problem = check_tool_input( | 입력 검사 | 명세 밖 입력(모르는 키, 없는 topic_id, 비어 있는 질의)은 실행하지 않음
  - ❷ | return {"text": f"입력 오류 | 오류 표시 | 입력 오류는 오류 표시로 돌려줌(교재 75쪽 툴 오류의 꼴)
  - ❸ | args["query"] = strip_identifiers( | 식별자 지우기 | 에이전트가 질의에 회원번호를 넣어도 검색에는 쓰이지 않음
  - ❹ | filters = ctx["filters"] | 필터 꺼내기 | ②가 만든 세대, 볼 수 있는 청크 표, 회원, 카드 필터
  - ❺ | result = tool_functions[name](args, filters, ctx) | 필터를 붙여 부름 | 툴 입력에는 필터 칸이 없고 래퍼가 강제로 붙임
- 굵게
  - strip_identifiers(
  - tool_functions[name](args, filters, ctx)
- 상세 보기 링크: https://github.com/unicorn-campus/hybrid-ai/blob/main/hands-on/solutions/graphrag/retriever/core_search.py
- 발표자 노트
  - 교육생 실습 함수 run_tool(빈칸 2곳)의 정답임. 빈칸은 식별자 지우기와 필터를 붙인 호출
  - 서브 워크플로우가 돌려준 관찰 글은 원문을 <chunk id=…> 태그로 감싼 것임(프롬프트 인젝션 방지)
  - 결과에 붙는 ⑤ 신호와 Jev 판정은 ToolWrapperMiddleware의 wrap_tool_call이 덧붙임

## 슬라이드 4. ④ O 검색엔진 검색
- 넣을 자리: 3. 검색: ④ 툴 실행 – O.
- 제목: 3. 검색: ④ 툴 실행 – O3 RRF 실제 코드
- 리드문: 벡터 검색과 BM25 검색의 두 순위를 점수 대신 순위로만 합쳐, 두 검색 모두에서 앞에 나온 청크를 위로 올림
- 코드: core_search.py rrf_merge
- 번호
  - ❶ | for source, hits in | 두 검색을 차례로 | 벡터 결과와 BM25 결과를 같은 방식으로 훑음. 한쪽이 비어도 됨
  - ❷ | enumerate(hits, start=1) | 순위는 1부터 | 순위만 쓰므로 점수 단위가 달라도 합칠 수 있음
  - ❸ | if chunk_id not in merged: | 중복 제거 | 처음 본 청크만 새 줄을 만듦. 두 번째부터는 같은 줄에 더함
  - ❹ | += 1.0 / (k + rank) | RRF 점수 | Σ 1 / (60 + 순위). 예: 벡터 1위, BM25 3위면 1/61 + 1/63
  - ❺ | ordered = sorted( | 상위 25개 | 점수 큰 순으로 줄 세워 상위 top개. 다음 O4 리랭커가 6개로 줄임
- 굵게
  - 1.0 / (k + rank)
- 상세 보기 링크: https://github.com/unicorn-campus/hybrid-ai/blob/main/hands-on/solutions/graphrag/retriever/core_search.py
- 발표자 노트
  - 교육생 실습 함수 rrf_merge(직접 작성)의 정답임
  - RRF를 코드에서 계산하는 까닭: 한쪽 검색이 죽어도 남은 순위로 결과를 낼 수 있음(교재 70쪽)
  - O1, O2는 main이 OpenSearch에 같은 필터(볼 수 있는 청크 표)를 걸어 두 번 부름

## 슬라이드 5. ④ L Local 검색
- 넣을 자리: 3. 검색: ④ 툴 실행 – L.
- 제목: 3. 검색: ④ 툴 실행 – L2 엔티티 축소 실제 코드
- 리드문: 청크에서 나온 엔티티 후보를 고정 엔티티, 청크마다 1개, 유사도 순으로 채워 16개만 남김
- 코드: core_search.py narrow_entities
- 코드 빼기
  - for row in candidates:
- 번호
  - ❶ | def add(row: dict) -> None: | 한 번만 넣기 | 같은 엔티티는 한 번만, 합계 limit(16)개까지
  - ❷ | by_score = sorted( | 유사도 순 | 질문 벡터와 노드 설명 임베딩(K6)의 코사인 유사도가 큰 순
  - ❸ | if row["id"] in (pinned_ids | 고정 먼저 | 상담 질문은 그 회원의 첫 상담과 가장 최근 상담을 먼저 넣음
  - ❹ | for chunk_id in seen_chunks: | 청크마다 1개 | 청크마다 가장 가까운 엔티티 1개. 엔티티와 원문의 연결이 끊기지 않음
  - ❺ | for row in by_score: | 남은 자리 | 남은 자리는 전체 유사도 순으로 채움
- 굵게
  - pinned_ids
  - seen_chunks
- 코드 번호 마지막 줄 찾기: ❺
- 상세 보기 링크: https://github.com/unicorn-campus/hybrid-ai/blob/main/hands-on/solutions/graphrag/retriever/core_search.py
- 발표자 노트
  - 교육생 실습 함수 narrow_entities(직접 작성)의 정답임
  - 후보와 유사도는 main의 Cypher가 구함. 엔티티가 나온 청크가 모두 볼 수 있는 청크일 때만 후보가 됨(권한 필터)
  - 교재 71쪽은 L2 ~ L4를 Cypher 한 번으로 그렸지만, 실습 예제는 이 축소를 파이썬 함수로 꺼내려고 두 번 부름

## 슬라이드 6. ④ G Global 검색
- 넣을 자리: 3. 검색: ④ 툴 실행 – G.
- 제목: 3. 검색: ④ 툴 실행 – G Global 검색 실제 코드
- 리드문: 보고서 고르기(G1)와 주제 나누기(G2)는 LCEL 체인과 구조화 출력으로 Groq를 부르고, 주제마다 Local 검색(G3)을 병렬로 돌림
- 코드: search_graph.py global_search
- 코드 빼기
  - vector = embed_query(
  - relevance = {}
  - for rid, report in reports.items():
  - short_ids = {f"r{i}"
  - titles = "
".join(
  - ctx["calls"]["groq"] += 1
  - picked.sort(
  - back = {rid: sid
  - report_lines = "
".join(
  - for topic in plan.topics
  - picked = [short_ids[s]
  - picked = []
  - topics = []
  - locals_ = [future.result()
  - except Exception as error:
  - if not picked:
  - while picked and sum(
  - if not topics:
  - return {"topics": topics
- 번호
  - ❶ | reports = {rid: r for rid | 볼 수 있는 보고서 | 회원 한 명의 상담으로 된 보고서는 그 권한이 없으면 고르지 못함
  - ❷ | chain = G1_PROMPT | G1 보고서 고르기 | 「프롬프트 → 구조화 모델」 LCEL 체인. 답은 PickedReports(보고서 id 목록)
  - ❸ | chain = G2_PROMPT | G2 주제와 Follow-up | 주제 1 ~ 5개와 주제마다 사실 확인 질문 하나(TopicPlan)
  - ❹ | topic["topic_id"] = | 주제 id | T1, T2 … 에이전트는 이 번호로만 local_search(topic_id)를 부를 수 있음
  - ❺ | pool.submit(local_search | G3 주제별 Local | 원 질문이 아니라 주제의 Follow-up 질문으로 병렬 검색
- 굵게
  - with_structured_output(PickedReports
  - with_structured_output(TopicPlan
  - pool.submit(local_search
- 상세 보기 링크: https://github.com/unicorn-campus/hybrid-ai/blob/main/hands-on/solutions/graphrag/retriever/search_graph.py
- 발표자 노트
  - 이 함수는 main에 있고 실습 함수가 아님(읽기). 「...」 줄은 보고서 관련도 계산, 실패 대체, 본문 토큰 몫 자르기임
  - method="json_schema", strict=True: gpt-oss-120b는 strict가 없으면 스키마를 되돌려 파싱이 실패함(RAG 실습 실측)
  - Microsoft GraphRAG의 Global Search(map-reduce)와 다른 자체 구성임(교재 72쪽)

## 슬라이드 7. ④ E, R 엔티티 직접 검색
- 넣을 자리: 3. 검색: ④ 툴 실행 – 엔티티 직접 검색
- 제목: 3. 검색: ④ 툴 실행 – R 원문 붙이기 실제 코드
- 리드문: 엔티티에서 FROM_CHUNK로 원문을 가져오고(R1), 볼 수 있는 청크 표로 다시 걸러(R2) 다른 회원 원문으로 가는 우회를 막음
- 코드: search_graph.py get_source_chunks
- 번호
  - ❶ | "UNWIND $ids AS eid MATCH (n)-[:FROM_CHUNK] | R1 원문 찾기 | 엔티티가 나온 청크를 같은 세대에서만 찾음
  - ❷ | kept = [cid for cid in all_ids if cid in | R2 필터 다시 걸기 | 엔티티 id만으로 다른 회원 청크에 닿지 못하게 다시 거름
  - ❸ | if with_reports: | 보고서도 | with_reports면 소속 커뮤니티 보고서를 함께. 볼 수 있는 보고서만
  - ❹ | "removed": len(all_ids) - len(kept) | 뺀 수 | 권한 밖이라 뺀 원문 수를 관찰에 알려 줌
- 굵게
  - filters["allowed_ids"]
  - filters["allowed_reports"]
- 상세 보기 링크: https://github.com/unicorn-campus/hybrid-ai/blob/main/hands-on/solutions/graphrag/retriever/search_graph.py
- 발표자 노트
  - 이 함수는 main에 있음(읽기). find_entities의 E1 정규화는 선택 과제 normalize_entity_key임
  - 그래프의 Chunk 노드에는 권한 속성이 없어서, ①에서 검색엔진 메타데이터로 만든 「볼 수 있는 청크 표」로 거름
  - 가져온 원문은 툴 안에서 관련성으로 거르지 않고 ⑤로 넘김. 질의가 없는 툴이라 ⑤가 원 질문으로 채점함

## 슬라이드 8. ⑤ 채점
- 넣을 자리: 3. 검색: ⑤ 채점
- 제목: 3. 검색: ⑤ 채점 – 진단 신호 실제 코드
- 리드문: 툴 결과 하나의 통계(원문 수, 포함률, 공존 문장 수 등)로 신호를 매겨 「왜 부족한가」를 에이전트에게 알려 줌
- 코드: core_search.py diagnose_signals
- 번호
  - ❶ | if stats["n_chunks"] == 0: | NO_SEED | 검색 결과 0건. 질의를 다시 써서 검색하라는 신호
  - ❷ | stats["cooccur"] == 0: | NO_COOCCUR | 핵심 낱말 두 개가 한 문장에 함께 나온 근거 0건(함정 질문의 단서)
  - ❸ | if (stats["coverage"] >= | PASS | 포함률 0.6 이상, 원문 2개 이상, NO_COOCCUR 없음
  - ❹ | signals.append("LOW_COVERAGE") | 나머지 신호 | LOW_COVERAGE, SCATTERED, NO_REPORTS, NO_NEW는 완성본으로 제공
- 굵게
  - "NO_SEED"
  - "NO_COOCCUR"
  - "PASS"
- 상세 보기 링크: https://github.com/unicorn-campus/hybrid-ai/blob/main/hands-on/solutions/graphrag/retriever/core_search.py
- 발표자 노트
  - 교육생 실습 함수 diagnose_signals(빈칸 3곳)의 정답임. 빈칸은 NO_SEED, NO_COOCCUR, PASS 세 규칙
  - 세는 일(포함률, 공존 문장 수)은 제공 함수가 하고, Jev는 원문마다 관련, 답 근거, 전제 충돌, 지시 끼워 넣기 확률만 냄
  - 신호와 기준값은 이 설계의 가정값이고 평가셋으로 조정함

## 슬라이드 9. ⑤ 상한 판정
- 넣을 자리: 3. 검색: ⑤ 상한 판정
- 제목: 3. 검색: ⑤ 상한 판정 – 미들웨어 실제 코드
- 리드문: 모델을 부르기 전에 코드가 강제 종료 조건을 보고, 걸리면 모델을 다시 부르지 않고 고리를 끝냄(jump_to end)
- 코드: search_graph.py before_model
- 번호
  - ❶ | @hook_config(can_jump_to=["end"]) | 끝낼 수 있는 훅 | before_model 훅이 고리를 끝(end)으로 보낼 수 있다고 알림
  - ❷ | if ctx.get("finish"): | finish 뒤 | 에이전트가 finish를 불렀으면 다음 모델 호출 없이 끝냄
  - ❸ | reason = core.force_stop_reason( | 강제 종료 조건 | 실습 함수: 회차 6, NO_NEW 2회 연속, 같은 호출 2회 연속, 전량 실패 2회
  - ❹ | if reason is None and ctx["rounds"] >= | 하드 상한 | 실습 함수를 잘못 채워도 6회차와 180초에서 고리를 끊음
  - ❺ | return {"jump_to": "end"} | 모델을 부르지 않음 | 종료 상태는 ⑦ 기준으로 코드가 정함. 툴 목록은 건드리지 않음
- 굵게
  - {"jump_to": "end"}
  - core.force_stop_reason(
- 코드 번호 마지막 줄 찾기: ❺
- 상세 보기 링크: https://github.com/unicorn-campus/hybrid-ai/blob/main/hands-on/solutions/graphrag/retriever/search_graph.py
- 발표자 노트
  - GuardMiddleware의 before_model 훅임(main, 읽기). 교육생 실습 함수 force_stop_reason을 여기서 부름
  - 병렬 5개, global_search 1회, 질의 8개는 after_model 훅이 모델이 고른 호출을 보고 막음(block_calls)
  - 툴 목록을 비워 한 번 더 부르는 방법은 쓰지 않음. finish까지 사라지고 캐시도 깨짐(교재 75쪽)

## 슬라이드 10. ⑥ 리랭킹
- 넣을 자리: 3. 검색: ⑥ 리랭킹
- 제목: 3. 검색: ⑥ 리랭킹 – 8자리 고르기 실제 코드
- 리드문: 리랭커 점수가 붙은 원문에서 8자리를 고르되, Global 검색 주제마다 1자리를 먼저 맡겨 주제가 통째로 잘리지 않게 함
- 코드: core_search.py select_final_chunks
- 번호
  - ❶ | by_score = sorted( | 점수 순 | 원 질문 기준 리랭커 점수가 큰 순
  - ❷ | topics = sorted( | 주제 목록 | 원문에 붙은 주제 id(T1, T2 …)를 이름순으로
  - ❸ | for topic in topics: | 주제마다 1자리 | 그 주제의 최고 점수 원문을 먼저 넣음
  - ❹ | for row in by_score: | 남은 자리 | 남은 자리는 점수 순으로 채움
  - ❺ | return sorted(chosen | 점수 순으로 | 고른 원문을 점수 내림차순으로 돌려줌
- 굵게
  - for topic in topics:
- 코드 번호 마지막 줄 찾기: ❹
- 상세 보기 링크: https://github.com/unicorn-campus/hybrid-ai/blob/main/hands-on/solutions/graphrag/retriever/core_search.py
- 발표자 노트
  - 교육생 실습 함수 select_final_chunks(직접 작성)의 정답임
  - 리랭커로 다시 채점하는 것은 원문 청크뿐임. 엔티티는 남은 원문과 이어진 것만, 보고서는 걸린 횟수와 관련도 순(main)
  - 회차가 1회이고 원문이 8개 이하면 main이 리랭킹을 건너뜀

## 슬라이드 11. ⑦ 수집 종료 판정
- 넣을 자리: 3. 검색: ⑦ 수집 종료 판정
- 제목: 3. 검색: ⑦ 수집 종료 판정 – 코드 재확인 실제 코드
- 리드문: 원 질문의 핵심 낱말 두 개로 모은 원문을 다시 확인함. 한 문장에 함께 있거나 관계 하나로 이어져야 통과
- 코드: core_search.py recheck_question
- 번호
  - ❶ | if len(terms) < 2: | 짧은 질문 | 핵심 낱말이 1개 이하면 그 낱말이 원문에 있는지만 봄
  - ❷ | together = count_cooccur( | 조건 ① | 두 낱말이 한 문장에 함께 나온 문장 수. 1개 이상이면 통과
  - ❸ | for entity_a, entity_b, where in candidate_pairs( | 조건 ② 후보 | a를 가진 엔티티와 b를 가진 엔티티의 쌍(서로 다른 두 원문, 또는 두 엔티티의 속성)
  - ❹ | in links: | 관계 하나 | 두 엔티티가 관계 하나로 이어지면 통과. IN_COMMUNITY는 관계로 치지 않음
  - ❺ | return {"passed": False | 불통과 | 둘 다 아니면 불통과 → ⑩ 확인할 수 없음. Jev가 살리지 않음
- 굵게
  - count_cooccur(
  - frozenset((entity_a, entity_b)) in links
- 상세 보기 링크: https://github.com/unicorn-campus/hybrid-ai/blob/main/hands-on/solutions/graphrag/retriever/core_search.py
- 발표자 노트
  - 교육생 실습 함수 recheck_question(빈칸 2곳)의 정답임. 빈칸은 조건 ①의 공존 문장 수와 조건 ②의 관계 확인
  - 통과한 뒤에는 제공 함수 decide_collection이 Jev 판정을 봄. 답 근거 원문이 0개면 불통과, 전제 충돌은 통과 + 표시
  - 함정 5문항 × 3회 실측(에이전트 Groq): 15번 모두 「확인할 수 없음」이고 모두 ⑦이 막음. 대가로 낱말이 다른 질문(Q14 「해지」와 「정리」)은 오거절됨

## 슬라이드 12. ⑧ 답변 생성
- 넣을 자리: 3. 검색: ⑧ 답변 생성, ⑨ 근거 검증
- 제목: 3. 검색: ⑧ 답변 생성 – LCEL 체인과 구조화 출력 실제 코드
- 리드문: 근거만으로 답하게 하고, 답은 문장마다 인용 id를 단 구조화 객체(GroundedAnswer)로 받음
- 코드: core_search.py AnswerSentence; core_search.py GroundedAnswer; core_search.py generate_answer
- 번호
  - ❶ | citation_ids: list[str] = Field( | 문장마다 인용 id | 「c1」 같은 근거 id 목록. ⑨가 이 칸으로 검증함
  - ❷ | sentences: list[AnswerSentence] | 답의 문장들 | 근거로 답할 수 없으면 빈 목록
  - ❸ | structured = llm.with_structured_output( | 구조화 출력 | LLM이 스키마의 칸을 채운 객체로 답함(문자열 파싱 없음)
  - ❹ | chain = prompt | structured | LCEL 체인 | 프롬프트와 구조화 모델을 이어(파이프 기호) 한 번 부름
  - ❺ | "feedback": feedback or | 재작성 피드백 | ⑨가 찾은 실패 사유를 넣어 다시 씀(최대 2회)
- 굵게
  - with_structured_output(
  - prompt | structured
- 상세 보기 링크: https://github.com/unicorn-campus/hybrid-ai/blob/main/hands-on/solutions/graphrag/retriever/core_search.py
- 발표자 노트
  - 교육생 실습 함수 generate_answer(빈칸 2곳)의 정답임. 빈칸은 with_structured_output과 LCEL 체인
  - 모델은 Groq gpt-oss-120b. method="json_schema", strict=True가 있어야 스키마를 지킴(RAG 실습 실측)
  - 프롬프트(main의 ANSWER_PROMPT)는 보고서(r로 시작하는 id)는 경향 문장에만 인용하라고 함

## 슬라이드 13. ⑨ 근거 검증
- 넣을 자리: 3. 검색: ⑧ 답변 생성, ⑨ 근거 검증
- 제목: 3. 검색: ⑨ 근거 검증 – 실제 코드
- 리드문: LLM이 아니라 규칙으로 답을 근거와 대조함. 실패 사유가 하나라도 있으면 ⑧이 그 사유를 받아 다시 씀
- 코드: core_search.py verify_answer
- 번호
  - ❶ | if not cited: | 인용 없음 | 문장마다 인용 id가 있어야 함(검사 ①)
  - ❷ | missing = [cid for cid in cited if | 없는 id | 근거 목록에 없는 id를 인용하면 실패(검사 ①)
  - ❸ | values = CLAUSE_PATTERN.findall( | 숫자와 조항 번호 | 답의 숫자와 조항 번호를 뽑음(검사 ②)
  - ❹ | if flat not in cited_text and digits not in | 원문에 그대로 있나 | 인용한 원문에 없으면 「c2에 7일 없음」 같은 사유
  - ❺ | if any(evidence[cid]["kind"] == "report" | 보고서 인용 | 보고서를 인용한 문장은 경향 낱말이 있어야 함(검사 ③)
- 굵게
  - CLAUSE_PATTERN.findall(
  - NUMBER_PATTERN.findall(
  - TREND_WORDS
- 상세 보기 링크: https://github.com/unicorn-campus/hybrid-ai/blob/main/hands-on/solutions/graphrag/retriever/core_search.py
- 발표자 노트
  - 교육생 실습 함수 verify_answer(직접 작성)의 정답임
  - 공백과 쉼표를 지우고 비교함. 「3,000,000원」과 「3000000원」을 같은 값으로 봄
  - 재작성 2회 뒤에도 실패하면 ⑩ 「확인 필요(2회 소진)」로 답과 경고를 함께 돌려줌

## 슬라이드 14. ⑩ 종료 상태
- 넣을 자리: 3. 검색: ⑩ 종료 상태
- 제목: 3. 검색: ⑩ 종료 상태 – 실제 코드
- 리드문: 어디서 끝나든 종료 상태 이름과 끝난 이유를 함께 돌려줌. 「확인할 수 없음」도 정상 종료임
- 코드: core_search.py END_STATES; core_search.py make_end_state
- 번호
  - ❶ | END_STATES = { | 종료 상태 표 | 코드 → (이름, 뜻). 교재 79쪽 표와 같은 7가지(+ 생성 실패)
  - ❷ | "unverifiable": | 확인할 수 없음 | 근거가 없어 지어내지 않고 멈춤. 실패가 아니라 정상 종료
  - ❸ | name, meaning = END_STATES[end_code] | 이름과 뜻 꺼내기 | 끝난 자리에서 넘긴 코드로 표를 찾음
  - ❹ | return {"status": name | 돌려줄 것 | 이름, 뜻, 이유, 답, 근거 목록, 경고. main이 에이전트 비용을 덧붙여 화면에 찍음
- 굵게
  - END_STATES[end_code]
- 상세 보기 링크: https://github.com/unicorn-campus/hybrid-ai/blob/main/hands-on/solutions/graphrag/retriever/core_search.py
- 발표자 노트
  - 교육생 실습 함수 make_end_state(빈칸 1곳)의 정답임
  - 화면 맨 끝에는 ③ 에이전트(Groq) 실제 비용(응답의 토큰 사용량 × 단가)과 호출 수, 툴 경로가 찍힘
  - 평가셋 25문항 마지막 실행(에이전트 Groq): 답 있는 20문항 중 답변 완료 16, 함정 5/5 확인할 수 없음, 에이전트 비용 합계 $0.0415
