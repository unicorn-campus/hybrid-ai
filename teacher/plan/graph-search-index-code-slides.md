# 그래프 교재 검색엔진 인덱싱(S1 ~ S3) 코드 예시 장표 스크립트

- 덱 파일: `teacher/plan/graph-search-index-code.pptx`(4장)
- 발췌: `python teacher/plan/build/extract-graph-k8-code.py teacher/plan/graph-search-index-code-slides.md teacher/plan/build/graph-search-index-code-slides.json`
- 빌드: `NODE_PATH="C:\Users\hiond\node_modules" node teacher/plan/build/build-graph-k8-community.js`  
  `teacher/plan/graph-search-index-code-slides.md teacher/plan/build/graph-search-index-code-slides.json teacher/plan/graph-search-index-code.pptx`
- 교재 넣기: `python teacher/plan/build/merge-graph-search-index-code.py {교재}.pptx`  
  (「넣을 자리」 제목으로 시작하는 마지막 장표 바로 뒤에 넣음. 다시 돌리면 전에 넣은 코드 장표를 지우고 새로 넣음)
- 대상 소스: `hands-on/solutions/graphrag/indexer/`의 `core_graph.py`, `kr_tokenizer.py`
- 코드 규칙: 발췌기가 실제 소스에서 꺼냄. docstring, 주석, 빈 줄은 빠지고 나머지 글자는 소스 그대로임.  
  「코드 빼기」에 적은 줄은 「...」 한 줄로 줄임
- 모양: 교재의 다른 「실제 코드」 장표와 같음(왼쪽 실제 코드, 오른쪽 ❶ ~ ❻ 설명)

## 슬라이드 1. S1 임베딩 코드

- 종류: 코드
- 넣을 자리: 검색엔진 인덱싱 – S1.
- 제목: 검색엔진 인덱싱 – S1 임베딩 실제 코드
- 리드문: 본문 해시가 옛 벡터 목록에 없는 글만 새로 임베딩하고, 나머지는 옛 벡터를 원래 순서대로 다시 씀
- 코드: core_graph.py embed_with_reuse
- 코드 빼기
  - todo_positions = []
  - todo_texts = []
- 번호
  - ❶ | if text_hash not in old_vectors: | 새로 만들 글 고르기 | 본문 해시가 옛 벡터 목록에 없는 글만 고름. 자리(position)도 함께 적어 둠
  - ❷ | new_vectors = embed_texts(todo_texts) | 한 번에 임베딩 | 고른 글만 Cohere에 보냄. 고른 글이 없으면 API를 부르지 않음
  - ❸ | fresh[position] = vector | 자리와 짝짓기 | 새 벡터를 원래 자리 번호에 맞춰 적어 둠
  - ❹ | if position in fresh: | 원래 순서대로 합치기 | 청크 순서대로 돌면서 새로 만든 자리는 새 벡터를 씀
  - ❺ | vectors.append(old_vectors[text_hash]) | 옛 벡터 재사용 | 나머지 자리는 본문 해시로 옛 벡터를 꺼내 씀. chunk_id가 달라도 본문이 같으면 됨
  - ❻ | return vectors, len(todo_texts) | 돌려주기 | 청크 순서대로의 벡터 목록과 새로 임베딩한 수. 수는 실행 로그에 남음
- 굵게
  - text_hash not in old_vectors
  - old_vectors[text_hash]
- 상세 보기 링크: https://github.com/unicorn-campus/hybrid-ai/blob/main/hands-on/solutions/graphrag/indexer/core_graph.py
- 발표자 노트
  - 교육생 실습 함수 embed_with_reuse(직접 작성)의 정답임
  - old_vectors는 index_graph.py의 read_old_vectors가 활성 세대 인덱스에서 읽은 {본문 해시: 벡터}임. 활성 세대가 없거나
    임베딩 모델, 차원이 지금 설정과 다르면(can_reuse_vectors) 빈 dict를 넘겨 모든 글을 새로 임베딩함
  - 첫 「...」는 새로 임베딩할 글의 자리 목록과 글 목록을 비워 두는 두 줄임
  - 96건씩 나눠 부르는 일과 차원 검사는 embed_texts가 함(K8.5 코드 장표)

## 슬라이드 2. S2 토큰화 코드 (1/2)

- 종류: 코드
- 넣을 자리: 검색엔진 인덱싱 – S2.
- 제목: 검색엔진 인덱싱 – S2 BM25 토큰화 실제 코드 (1/2)
- 리드문: 표기를 통일하고, 코드는 통째로 넣고, Kiwi가 자른 낱말 중 내용어만 남긴 뒤 별칭을 정식 카드명으로 바꿈
- 코드: kr_tokenizer.py CONTENT_TAGS; kr_tokenizer.py tokenize_korean; kr_tokenizer.py apply_aliases
- 코드 빼기
  - if canonical in seen_names:
  - seen_names.add(canonical)
- 번호
  - ❶ | CONTENT_TAGS = | 남길 품사 | 명사, 숫자, 영문, 동사와 형용사 줄기만 남김. 조사, 어미, 기호는 여기 없어 빠짐
  - ❷ | normalized = NUMBER_COMMA_PATTERN.sub("", text).lower() | 표기 통일 | 숫자 사이 쉼표를 지우고 영문을 소문자로 바꿈. 30,000은 30000, KB는 kb가 됨
  - ❸ | tokens = list(CODE_PATTERN.findall(normalized)) | 코드는 통째로 | D2-C021 같은 코드를 먼저 통째로 넣음. Kiwi가 쪼개도 코드로 찾을 수 있음
  - ❹ | if token.tag.split("-")[0] in CONTENT_TAGS: | 내용어만 남김 | Kiwi가 붙인 품사가 ❶에 있을 때만 낱말을 넣음
  - ❺ | return apply_aliases(tokens, alias_to_name) | 별칭 바꾸기 | 줄여 부른 카드 이름을 정식 카드명 한 낱말로 바꿈
  - ❻ | canonical = alias_to_name[token] | 정식 카드명 찾기 | 가족돌봄, 가족돌봄 카드 모두 한빛가족돌봄이 됨
- 굵게
  - CONTENT_TAGS
  - apply_aliases(tokens, alias_to_name)
- 상세 보기 링크: https://github.com/unicorn-campus/hybrid-ai/blob/main/hands-on/solutions/graphrag/indexer/kr_tokenizer.py
- 발표자 노트
  - 강사 제공 코드임(kr_tokenizer.py). RAG 실습의 토크나이저와 같은 규칙이라 색인 쪽과 질문 쪽이 같은 낱말을 만듦
  - 품사 이름: NNG 일반 명사, NNP 고유 명사, NR 수사, SN 숫자, SL 영문, VV 동사, VA 형용사
  - 카드명과 별칭은 Kiwi에 고유 명사로 미리 등록해 두어 한 낱말로 잘림(build_tokenizer)
  - apply_aliases의 「...」는 같은 정식 카드명이 한 글 안에서 두 번 들어가지 않게 막는 자리임

## 슬라이드 3. S2 토큰화 코드 (2/2)

- 종류: 코드
- 넣을 자리: 검색엔진 인덱싱 – S2.
- 제목: 검색엔진 인덱싱 – S2 BM25 토큰화 실제 코드 (2/2)
- 리드문: 청크마다 낱말, 벡터, 메타데이터를 한 건에 담아 검색엔진에 넣을 문서를 만듦
- 코드: core_graph.py build_search_docs
- 번호
  - ❶ | tokens = tokenizer.tokenize(chunk["text"]) | 낱말로 자르기 | 앞 장표의 토크나이저로 청크 본문을 낱말 목록으로 바꿈
  - ❷ | "doc_id": chunk["doc_id"], | 문서 ID | S3에서 이 값이 같은 옛 청크를 한꺼번에 지움
  - ❸ | "text_hash": text_hash, | 본문 해시 | 다음 실행의 S1이 이 값으로 벡터를 다시 쓸지 정함
  - ❹ | "text_tokens": " ".join(tokens), | 낱말을 공백으로 이음 | 검색엔진은 공백으로만 잘라 역색인을 만듦(whitespace 분석기)
  - ❺ | "embedding": vector, | 벡터 | S1에서 만든 벡터를 같은 한 건에 담음
  - ❻ | doc[field] = str(value) | 메타데이터 | 값이 있는 것만 글자로 넣음. 카드 번호 같은 필터와 출처 표시에 씀
- 굵게
  - " ".join(tokens)
- 상세 보기 링크: https://github.com/unicorn-campus/hybrid-ai/blob/main/hands-on/solutions/graphrag/indexer/core_graph.py
- 발표자 노트
  - 교육생 실습 함수 build_search_docs(빈칸 2곳)의 정답임. 빈칸은 tokenizer.tokenize 호출과 엔진 문서 한 건 만들기
  - 벡터와 낱말이 같은 한 건에 들어 있어 벡터 색인과 키워드 색인이 어긋날 수 없음
  - text는 보여 주기용이라 색인하지 않고, text_tokens만 키워드 검색에 씀. 필드 종류는 index_graph.py의 index_mapping이 정함
  - BM25의 k1 1.5, b 0.75도 index_mapping이 인덱스 설정에 적음

## 슬라이드 4. S3 쓰기 코드

- 종류: 코드
- 넣을 자리: 검색엔진 인덱싱 – S3.
- 제목: 검색엔진 인덱싱 – S3 검색 엔진에 쓰기 실제 코드
- 리드문: 넣을 문서의 doc_id를 모으고, 문서마다 옛 청크를 지우고, 새 청크를 한꺼번에 넣은 뒤 바로 보이게 함
- 코드: core_graph.py apply_search
- 번호
  - ❶ | if not os_client.indices.exists(index=index): | 인덱스 만들기 | 이번 세대 인덱스가 없으면 매핑으로 만듦. 벡터 필드와 낱말 필드가 이때 정해짐
  - ❷ | doc_ids.add(doc["doc_id"]) | 지울 문서 고르기 | 이번에 넣을 청크의 doc_id를 겹치지 않게 모음
  - ❸ | result = os_client.delete_by_query( | 옛 청크 지우기 | doc_id가 같은 청크를 모두 지움. refresh=True라 바로 반영됨
  - ❹ | actions.append({"_index": index, "_id": doc["chunk_id"], "_source": doc}) | _id는 chunk_id | 같은 입력을 두 번 넣어도 덮어써서 건수가 그대로임
  - ❺ | helpers.bulk(os_client, actions, max_retries=3) | 한꺼번에 넣기 | 요청 한 번으로 모두 넣음. 일부가 실패하면 오류(BulkIndexError)가 남
  - ❻ | os_client.indices.refresh(index=index) | 반영 | 넣은 청크가 다음 검색부터 보임
- 굵게
  - delete_by_query
  - "_id": doc["chunk_id"]
- 상세 보기 링크: https://github.com/unicorn-campus/hybrid-ai/blob/main/hands-on/solutions/graphrag/indexer/core_graph.py
- 발표자 노트
  - 교육생 실습 함수 apply_search(빈칸 3곳)의 정답임. 빈칸은 옛 청크 지우기, 한꺼번에 넣기, 반영
  - conflicts="proceed"는 지우는 도중 다른 쓰기와 부딪혀도 멈추지 않고 계속하라는 뜻임
  - 실습은 실행마다 새 세대 인덱스에 쓰므로 지울 옛 청크가 없어 지운 수가 0으로 나옴. 같은 세대에 다시 쓸 때 이 지우기가 일함
  - 돌려주는 값(지운 수, 넣은 수, 문서 수)은 실행 로그 [S3] 줄에 찍힘
