# 그래프 교재 K8 커뮤니티 리포트 만들기 장표 스크립트

- 덱 파일: `teacher/plan/graph-k8-community.pptx`(16장)
- 넣을 자리: 교재의 「KG 구축 – K8. 커뮤니티마다 보고서 쓰기 (원리와 코드)」 장표 바로 뒤
- 대상 소스: `hands-on/solutions/graphrag/indexer/index_graph.py`, `hands-on/solutions/graphrag/indexer/core_graph.py`
- 코드 규칙: 실제 소스에서 발췌기(`teacher/plan/build/code_excerpt.py`)가 꺼냄. docstring, 줄 전체 주석, 줄 끝 주석, 빈 줄은 빠지고
  나머지 글자는 소스 그대로임. 「코드 빼기」에 적은 줄은 「...」 한 줄로 줄임
- 「코드」 칸 꼴: `파일 함수`를 「;」로 이어 적음. `k8_summarize#N`은 `k8_summarize` 안의 `# --- N.` 주석 줄부터
  다음 `# --- ` 주석 줄 전까지 구간을 뜻함
- 「코드 끝: 글」 = 「코드」 칸 첫 함수에서 그 글이 든 문장까지만 보여 주고 뒤는 「...」 한 줄
- 「코드 시작: 글」 = 「코드」 칸 첫 함수에서 그 글이 든 줄부터 보여 줌. 앞은 def 줄까지 버리고 들여쓰기를 다시 맞춤
- 일련번호: 단계 번호와 헷갈리지 않게 ❶, ❷, ❸ …
- 번호 줄 꼴: `❶ | 코드 줄에서 찾을 글 | 설명 제목 | 설명 본문`. 번호는 앞 번호 줄 다음 줄부터 찾음
- 도식 줄 꼴: `상자 A | 상자 제목 | 줄1 / 줄2 / 줄3`, `화살표 A → B | 화살표 글`,
  `그림 A | 상자 제목 | 그림 종류 | 줄1 / 줄2`(그림 종류: directed, undirected, communities, in_community.
  이어 쓰는 예시의 엔티티 7개를 점과 선으로 그림)
- 용어 약속: 「커뮤니티」(묶음이라 쓰지 않음), 「리포트」(보고서라 쓰지 않음), 「선(edge)」,
  「지문」(처음 나올 때 「지문(해시)」), 「엔티티 번호」(entities 목록 안의 위치, 0부터)
- 이어 쓰는 예시: 실습 세대 `gen-lab-v3-e0d2747b`에서 뽑은 엔티티 7개(소스 docstring의 값 그대로)
- 코드 글자 안의 「묶음」, 「보고서」는 소스 원문이라 고치지 않음. 화면 설명 글에서만 「커뮤니티」, 「리포트」를 씀

## 슬라이드 1. 수행 단계

- 종류: 수행단계
- 제목: KG 구축 – K8. 커뮤니티 리포트 만들기 수행 단계
- 리드문: 함수 하나(k8_summarize)가 엔티티 읽기부터 KG 적재까지 여섯 단계를 차례로 부름
- 단계
  - K8.1 | 엔티티, 관계, 선(edge) 생성 | 이 세대 엔티티에 번호를 매기고 관계를 방향 없는 선으로 바꿈 | read_entity_graph, entity_key | generation → entities, relations, edges
  - K8.2 | 커뮤니티 구성 | Leiden으로 커뮤니티를 나누고 커뮤니티마다 지문(해시)을 만듦 | core.detect_communities, member_hash | entities, edges → groups, hashes, targets
  - K8.3 | 리포트 생성 대상 커뮤니티 선별 | 앞 세대 리포트(cache)에 지문이 없는 커뮤니티만 고름 | k8_summarize 본문 | targets, cache → todo
  - K8.4 | 커뮤니티 리포트 생성 | todo만 LLM에 묻고, 지문이 같은 리포트는 cache에서 가져와 합침 | summarize_community | todo, cache → reports
  - K8.5 | 커뮤니티 리포트 임베딩 | 벡터가 없는 리포트만 글 하나로 이어 임베딩함 | embed_texts | reports → reports[지문]["embedding"]
  - K8.6 | 커뮤니티를 KG 적재 | 리포트를 행으로 만들어 Community 노드와 IN_COMMUNITY 관계로 씀 | core.build_community_rows, core.k8_write_communities | reports → Community 노드, 벡터 인덱스
- 실측: 실습 세대 gen-lab-v3-e0d2747b 기준 엔티티 73개, 관계 69개 → 커뮤니티 11개, 리포트 11개(모두 2048차원 벡터)
- 발표자 노트
  - 이 여섯 단계는 코드 안에 그대로 적혀 있습니다. index_graph.py의 k8_summarize를 열면 `# --- 1.`부터 `# --- 6.`까지
    주석이 단계를 나누고 있고, 오늘 보는 열여섯 장은 그 주석 하나마다 설명 한 장과 코드 한 장 이상을 붙인 것입니다.
    가장 복잡한 K8.4는 코드가 세 장, K8.6은 두 장입니다.
  - 단계 이름 옆의 「부르는 함수」를 눈여겨봐 주세요. k8_summarize 자체는 짧고, 무거운 일은 전부 다른 함수에 맡깁니다.
    Leiden으로 커뮤니티를 나누는 일과 Neo4j에 쓰는 일은 core_graph.py에 있고, LLM에 묻는 일은 summarize_community에 있습니다.
  - 「입력 → 출력」의 변수 이름이 다음 단계의 입력으로 그대로 이어집니다. entities와 relations가 edges를 만들고,
    edges가 groups를 만들고, groups가 지문을 만들고, 지문이 리포트를 부를지 재사용할지를 정합니다.
  - 실측 줄을 보면 엔티티 73개가 커뮤니티 11개로 줄었습니다. 11개가 모두 엔티티 3개 이상이라 리포트도 11개입니다.
    이 세대는 앞 세대 리포트를 전부 재사용해서 LLM 호출이 0번이었습니다. 이 「재사용」이 K8.3의 주제입니다.

## 슬라이드 2. K8.1 설명

- 종류: 설명
- 제목: KG 구축 – K8.1 엔티티, 관계, 선(edge) 생성
- 리드문: Neo4j에서 읽은 엔티티에 번호를 매기고, 방향과 이름이 있는 관계를 방향 없는 선으로 바꿈
- 도식
  - 그림 A | Neo4j (이 세대의 엔티티와 관계) | directed | __Entity__ 노드만 읽음 / 청크 노드와 FROM_CHUNK는 안 읽음
  - 화살표 A → B | entity_key로 키를 만들어 키순으로 정렬
  - 상자 B | entities (번호 = 목록 안 위치) | 0 BenefitCondition / 1 BenefitExclusion / 2 BenefitLimit / 3 Benefit / 4 Clause / 5 ProductGuide / 6 TermsDocument
  - 화살표 B → C | 엔티티 사이 관계를 번호로 바꿔 읽음
  - 상자 C | relations (방향과 이름이 있음) | (3, 0, "REQUIRES") / (3, 1, "EXCLUDES") / (3, 2, "LIMITED_BY") / (5, 3, "OFFERS_BENEFIT") / (6, 4, "HAS_CLAUSE")
  - 화살표 C → D | 방향과 이름을 버리고 작은 번호를 앞에
  - 그림 D | edges (방향 없는 선) | undirected | (0, 3) (1, 3) (2, 3) / (3, 5) (4, 6)
- 핵심
  - 왜 번호로 말하나 | Neo4j 내부 ID는 실행마다 바뀜. 키순으로 정렬해 매긴 번호는 같은 엔티티면 늘 같은 자리에 옴
  - 왜 방향을 버리나 | 커뮤니티 나누기는 「이어져 있는가」만 봄. 3 → 0과 0 → 3이 같은 선 (0, 3)이 됨
  - 선은 한 번만 | set으로 모아서 두 엔티티 사이에 관계가 여러 개여도 선은 1개가 됨
- 발표자 노트
  - 엔티티 번호는 데이터베이스가 준 번호가 아니라 우리가 매긴 번호입니다. 키는 「라벨|속성 JSON」이고,
    이 키를 글자 순서로 줄 세운 다음 앞에서부터 0, 1, 2를 붙입니다. 그래서 라벨이 Benefit로 시작하는 엔티티가 앞쪽에 옵니다.
  - 예시의 7개는 실제 실습 세대에서 뽑은 것입니다. 3번 Benefit(병원·약국 할인)에 조건, 제외, 한도가 모두 붙어 있고,
    5번 상품안내가 그 혜택을 가리킵니다. 4번 조항과 6번 약관 문서는 따로 떨어진 짝입니다.
  - 관계를 선으로 바꾸면 정보가 줄어듭니다. 방향도 사라지고 이름도 사라집니다. 아깝지만 커뮤니티를 나눌 때는
    그 정보가 필요 없고, 리포트를 쓸 때는 relations를 다시 꺼내 쓰기 때문에 잃어버리는 것이 아닙니다.
  - 자기 자신을 가리키는 관계는 선에서 뺍니다. 혼자 이어진 선은 누구와 가까운지를 알려 주지 않기 때문입니다.

## 슬라이드 3. K8.1 코드

- 종류: 코드
- 제목: KG 구축 – K8.1 엔티티, 관계, 선(edge) 생성 실제 코드
- 리드문: read_entity_graph가 번호를 매겨 돌려주고, k8_summarize가 그 관계를 방향 없는 선으로 바꿈
- 코드: index_graph.py read_entity_graph; index_graph.py k8_summarize#1
- 코드 빼기
  - driver.execute_query(
  - for record in records:
  - if a == b:
- 번호
  - ❶ | entities.sort(key=lambda e: e["key"]) | 키순으로 줄 세움 | 「라벨|속성 JSON」 키로 정렬함. 세대가 달라도 같은 엔티티면 같은 자리에 옴
  - ❷ | position = {entity["id"]: number | 번호 매김 | 줄 세운 자리(0부터)가 엔티티 번호가 됨. 뒤 단계는 이 번호로만 말함
  - ❸ | return entities, sorted(relations) | 두 가지를 돌려줌 | 번호 매긴 엔티티 목록과 (출발 번호, 도착 번호, 관계 이름) 목록
  - ❹ | edge_set = set() | 같은 선은 한 번만 | 두 엔티티 사이에 관계가 여러 개여도 선은 1개로 남음
  - ❺ | edge = (min(a, b), max(a, b)) | 방향 없애기 | 작은 번호를 앞에 둬서 3 → 0과 0 → 3을 같은 선 (0, 3)으로 만듦
  - ❻ | edges = sorted(edge_set) | 순서 고정 | 선 순서가 늘 같아야 Leiden이 같은 커뮤니티를 내놓음
- 굵게
  - entities.sort(key=lambda e: e["key"])
  - min(a, b), max(a, b)
- 상세 보기 링크: https://github.com/unicorn-campus/hybrid-ai/blob/main/hands-on/solutions/graphrag/indexer/index_graph.py
- 발표자 노트
  - read_entity_graph의 Cypher 두 개는 「...」로 줄임. 첫째는 이 세대 __Entity__ 노드 읽기, 둘째는 엔티티 사이 관계 읽기
  - 엔티티 키를 만드는 함수 entity_key는 K8.3 코드 장표(슬라이드 7)에서 자세히 봄
  - `_relation_type`의 밑줄은 「값을 받되 쓰지 않음」이라는 파이썬 관례
  - 선 만들기는 k8_summarize 안에 그대로 있음. 짧아서 함수로 빼지 않았음

## 슬라이드 4. K8.2 설명

- 종류: 설명
- 제목: KG 구축 – K8.2 커뮤니티 구성
- 리드문: 선만 보고 촘촘히 이어진 엔티티를 커뮤니티로 나눈 뒤, 커뮤니티마다 지문(해시)을 찍음
- 도식
  - 그림 A | 입력: 엔티티 7개와 선 5개 | undirected | edges 5개 / 씨앗 COMMUNITY_SEED = 42
  - 화살표 A → B | GDS 메모리에 복사해 Leiden을 돌림
  - 상자 B | Leiden이 준 커뮤니티 번호 | 엔티티 3, 0, 1, 2, 5 → 17번 / 엔티티 4, 6 → 42번 / 번호 자체는 뜻이 없음
  - 화살표 B → C | 번호를 구성원 목록으로 바꾸고 두 번 정렬
  - 그림 C | groups | communities | [[0, 1, 2, 3, 5], [4, 6]] / 안은 번호순, 커뮤니티끼리는 가장 작은 번호순
  - 화살표 C → D | member_hash로 지문을 만들고 3개 이상만 남김
  - 상자 D | hashes와 targets | 지문 재료: 리포트 판 / + 구성원 키 / + 커뮤니티 안 관계 / [0, 1, 2, 3, 5] 5개: 대상 / [4, 6] 2개: 빠짐
- 핵심
  - 씨앗을 고정하는 이유 | randomSeed 42와 concurrency 1을 함께 둬야 같은 그래프에서 같은 커뮤니티가 나옴. 그래야 리포트를 재사용함
  - 지문이 하는 일 | 커뮤니티 내용이 하나도 안 바뀌면 지문이 같음. 지문이 같으면 리포트를 다시 쓸 필요가 없음
  - 작은 커뮤니티는 건너뜀 | 엔티티가 COMMUNITY_MIN_SIZE(3)개보다 적으면 엔티티 설명만으로 충분해 리포트를 쓰지 않음
- 발표자 노트
  - Leiden이 무엇을 보고 나누는지는 앞 장표 「K8. Leiden으로 커뮤니티 찾기 (원리)」에서 다뤘습니다. 여기서는
    그 결과를 코드가 어떻게 받아 쓰는지만 봅니다.
  - Leiden이 주는 커뮤니티 번호는 17번, 42번처럼 뜻이 없습니다. 실행할 때마다 달라질 수 있어서 그대로 쓰면 안 됩니다.
    그래서 구성원 목록으로 바꾸고, 커뮤니티 안은 번호순으로, 커뮤니티끼리는 가장 작은 번호순으로 줄 세웁니다.
  - 선이 하나도 없는 엔티티도 혼자 있는 커뮤니티가 됩니다. 투영할 때 선 없는 노드도 함께 넣기 때문입니다.
    이런 커뮤니티는 엔티티가 1개라 다음 걸러내기에서 자연스럽게 빠집니다.
  - 지문에는 세 가지가 들어갑니다. 리포트 판(REPORT_VERSION), 구성원의 키, 커뮤니티 안 관계입니다.
    프롬프트를 고쳐 판을 올리면 지문이 전부 바뀌어 리포트를 다시 쓰게 됩니다.

## 슬라이드 5. K8.2 코드

- 종류: 코드
- 제목: KG 구축 – K8.2 커뮤니티 구성 실제 코드
- 리드문: k8_summarize가 detect_communities를 부르고, 그 안에서 투영, Leiden, 정렬이 차례로 일어남
- 코드: index_graph.py k8_summarize#2; core_graph.py detect_communities
- 코드 빼기
  - if not entity_ids:
  - rows = []
  - for number in range(len(entity_ids)):
  - for a, b in edges:
  - "UNWIND $rows AS row MATCH (s)
  - "OPTIONAL MATCH (t)
  - "RETURN g.nodeCount AS n"
  - "RETURN elementId(gds.util.asNode(nodeId))
  - finally:
  - position = {}
  - for number, entity_id in enumerate(entity_ids):
  - by_community: dict
  - for record in records:
  - groups = []
  - for members in by_community.values():
- 번호
  - ❶ | groups = core.detect_communities( | 커뮤니티 나누기 호출 | 엔티티 elementId 목록, 선 목록, 씨앗 42를 넘기면 커뮤니티별 엔티티 번호 목록이 옴
  - ❷ | hashes = [member_hash(entities, g, relations) for g in groups] | 커뮤니티마다 지문 | 커뮤니티 하나가 지문 하나를 가짐. groups와 순서가 같음
  - ❸ | if len(g) >= COMMUNITY_MIN_SIZE | 3개 이상만 남김 | 엔티티가 3개보다 적은 커뮤니티는 리포트를 쓰지 않고 뺌
  - ❹ | "WITH gds.graph.project( | 메모리에 복사 | 엔티티와 선만 GDS 메모리에 옮김. 모든 관계를 무방향으로 봄
  - ❺ | "CALL gds.leiden.stream($name, {randomSeed: $seed, concurrency: 1} | Leiden 돌리기 | 씨앗과 병렬 1을 함께 둬야 같은 그래프에서 늘 같은 커뮤니티가 나옴
  - ❻ | groups.sort(key=lambda members: members[0]) | 커뮤니티 줄 세우기 | GDS 번호는 뜻이 없어 버리고, 가장 작은 엔티티 번호로 커뮤니티 순서를 정함
- 굵게
  - COMMUNITY_SEED
  - COMMUNITY_MIN_SIZE
  - randomSeed: $seed, concurrency: 1
- 상세 보기 링크: https://github.com/unicorn-campus/hybrid-ai/blob/main/hands-on/solutions/graphrag/indexer/core_graph.py
- 발표자 노트
  - detect_communities는 교육생 실습 함수임(빈칸 2곳). 빈칸은 투영(gds.graph.project)과 Leiden 호출(gds.leiden.stream)
  - 첫 「...」는 투영에 넘길 행을 만드는 자리임. 선이 없는 엔티티도 노드 행으로 먼저 넣어 혼자 있는 커뮤니티가 되게 함
  - 마지막 「...」 안에는 try의 finally가 있음. 성공하든 실패하든 투영 그래프를 지워 메모리를 돌려줌.
    그 뒤에서 「엔티티 번호 → 커뮤니티 번호」를 커뮤니티별 구성원 목록으로 뒤집고 커뮤니티 안을 번호순으로 정렬함
  - graph_name은 세대와 실행으로 만들어 서로 다른 실행이 같은 투영 그래프를 건드리지 않게 함

## 슬라이드 6. K8.3 설명

- 종류: 설명
- 제목: KG 구축 – K8.3 리포트 생성 대상 커뮤니티 선별
- 리드문: 앞 세대가 남긴 리포트 파일과 지문을 맞춰 보고, 없는 것만 LLM에 물을 목록(todo)으로 만듦
- 도식
  - 상자 A | targets (예: 커뮤니티 3개) | 지문 a1f… / 지문 7c2… / 지문 e90… / 실습 세대에서는 11개
  - 상자 B | cache = 앞 세대 community_reports.json | a1f…: 리포트와 벡터 / e90…: 리포트와 벡터 / run()이 활성 세대 폴더나 --reuse 폴더에서 읽음
  - 화살표 A → C | 지문이 cache에 없는 것만
  - 화살표 B → C | 지문이 cache에 있으면 재사용
  - 상자 C | todo (LLM에 물을 것) | 7c2…만 todo에 들어감 / a1f…와 e90…는 재사용 / 실습 세대 실측: todo 0개, 재사용 11개
  - 화살표 C → D | 로그 한 줄로 바로 확인
  - 상자 D | 실행 중 로그 (실습 세대) | [K8] 엔티티 73개, 관계 69개 → 묶음 11개, / 엔티티 3개 이상 11개, / 보고서 LLM 0번, 재사용 11개
- 핵심
  - 지문이 달라지는 경우 세 가지 | 리포트 판을 올렸을 때, 구성원이 바뀌었을 때, 커뮤니티 안 관계가 바뀌었을 때
  - 가장 비싼 일을 건너뜀 | K8에서 돈과 시간이 가장 많이 드는 것이 LLM 호출임. 안 바뀐 커뮤니티는 아예 묻지 않음
  - 글자 하나도 안 바뀜 | 재사용한 리포트는 제목, 요약, 핵심 사실, 벡터까지 앞 세대 그대로임
- 발표자 노트
  - cache는 어디서 올까요. 실행을 시작할 때 run()이 앞 세대 폴더의 community_reports.json을 읽어 두었다가
    k8_summarize에 넘깁니다. 처음 돌리면 그 파일이 없어서 cache는 빈 사전이고, 모든 커뮤니티가 todo가 됩니다.
  - 강사 배포본을 --reuse로 지정하면 남의 세대가 만든 리포트도 그대로 쓸 수 있습니다. 지문만 같으면 되기 때문입니다.
  - 실습 세대 실측에서 LLM 호출은 0번이었습니다. 그래프가 그대로였고 리포트 판도 그대로여서 지문이 전부 같았기 때문입니다.
    프롬프트를 고치고 REPORT_VERSION을 v2로 올리면 11개가 모두 todo가 됩니다.
  - 화면의 로그 글자에 「묶음」, 「보고서」라고 나오는 것은 소스에 적힌 말 그대로입니다. 설명에서는 커뮤니티와 리포트로 부릅니다.

## 슬라이드 7. K8.3 코드

- 종류: 코드
- 제목: KG 구축 – K8.3 리포트 생성 대상 커뮤니티 선별 실제 코드
- 리드문: 걸러내기는 한 줄임. 그 한 줄이 통하는 이유는 지문과 엔티티 키가 늘 같은 값으로 나오기 때문임
- 코드: index_graph.py k8_summarize#3; index_graph.py member_hash; index_graph.py entity_key
- 번호
  - ❶ | todo = [(g, h) for g, h in targets if h not in cache] | 없는 것만 고름 | 지문이 cache에 없는 커뮤니티만 LLM을 부를 대상이 됨
  - ❷ | 보고서 LLM {len(todo)}번, 재사용 | 숫자를 바로 보여 줌 | 몇 개를 새로 쓰고 몇 개를 재사용하는지 실행 중에 로그로 보임
  - ❸ | inner = sorted(f"{entities[a]['key']}->{t}->{entities[b]['key']}" | 안쪽 관계도 재료 | 구성원이 같아도 커뮤니티 안 관계가 달라지면 지문이 달라짐
  - ❹ | core.sha256_text("\n".join([REPORT_VERSION] | 세 가지를 이어 붙임 | 리포트 판, 구성원 키, 안쪽 관계를 한 글로 이어 짧은 지문으로 줄임
  - ❺ | clean = {k: v for k, v in props.items() if k not in core.SYSTEM_PROPS} | 관리용 속성 뺌 | generation, run_id, embedding을 빼서 세대가 달라도 키가 같아짐
  - ❻ | sort_keys=True | 이름순으로 고정 | Neo4j가 주는 속성 순서가 실행마다 달라도 같은 키가 나옴
- 굵게
  - h not in cache
  - REPORT_VERSION
  - sort_keys=True
- 상세 보기 링크: https://github.com/unicorn-campus/hybrid-ai/blob/main/hands-on/solutions/graphrag/indexer/index_graph.py
- 발표자 노트
  - cache는 k8_summarize의 네 번째 인자임. 부른 쪽(run)이 앞 세대 community_reports.json을 읽어 넘김
  - member_hash의 inside는 구성원 번호 집합임. 양 끝이 모두 이 커뮤니티 안인 관계만 지문 재료로 씀
  - entity_key는 K8.1에서 엔티티에 번호를 매길 때도 쓰임. 같은 키가 정렬 기준이자 지문 재료가 됨
  - `default=str`은 날짜처럼 JSON이 모르는 값을 글자로 바꾸라는 뜻임. 속성 값이 한 글자만 바뀌어도 지문이 바뀜

## 슬라이드 8. K8.4 설명

- 종류: 설명
- 제목: KG 구축 – K8.4 커뮤니티 리포트 생성
- 리드문: 커뮤니티 하나를 LLM이 읽을 글로 바꿔 묻고, 돌아온 답의 번호를 엔티티 이름으로 되돌림
- 도식
  - 상자 A | 커뮤니티 하나(todo 한 건) | 구성원 [0, 1, 2, 3, 5] / 안쪽 관계 4개 / 동시에 LLM_CONCURRENCY(2)건씩 처리
  - 화살표 A → B | 안쪽 관계가 많은 엔티티부터 120개까지 고름
  - 상자 B | 고른 엔티티와 이름표 | shown = [0, 1, 2, 3, 5] / refs = {"e1": 0, "e2": 1, "e3": 2, "e4": 3, "e5": 5} / back은 그 반대 표
  - 화살표 B → C | 엔티티 한 줄씩, 관계 한 줄씩 글로 만듦
  - 상자 C | LLM에 보내는 글 | e1. BenefitCondition: description=가상 일반 병원·약국 업종의 본인 결제; … / e4. Benefit: amount=대상 결제액의 4%를 할인함., …, name=병원·약국 할인 / e4 -[REQUIRES]-> e1 / e5 -[OFFERS_BENEFIT]-> e4
  - 화살표 C → D | REPORT_USER 틀에 끼워 Groq에 물음(JSON 하나로만 답하게 함)
  - 상자 D | LLM이 준 JSON | {"title": …, "summary": …, / "findings": [{"text": …, / "entities": ["e4", "e1"]}]}
  - 화살표 D → E | e번호를 엔티티 이름으로 바꾸고, 없는 번호는 버림
  - 상자 E | reports[지문] | title 한빛 가족돌봄 카드의 병원·약국·쇼핑 할인 혜택 / summary 3 ~ 5문장 / findings 「… [근거: Benefit(대상 결제액의 4%를 할인함.)]」
- 핵심
  - 왜 e1, e2를 붙이나 | 엔티티 번호는 0, 1, 2, 3, 5처럼 빠진 번호가 있어 읽기 어려움. 고른 순서대로 e1부터 다시 붙임
  - 근거를 이름으로 되돌림 | LLM이 댄 e4를 엔티티 이름으로 바꿔 「본문 [근거: …]」로 적음. 지어낸 번호(e9)는 버림
  - 틀리면 다시 물음 | JSON이 깨지거나 제목이나 요약이 비면 같은 입력으로 처음 1번에 더해 3번까지 다시 부름
- 발표자 노트
  - LLM에 통째로 넣을 수 없는 큰 커뮤니티가 있습니다. 그래서 커뮤니티 안에서 관계가 많은 엔티티,
    즉 그 커뮤니티의 중심에 가까운 엔티티부터 120개까지만 고릅니다. 작은 커뮤니티는 전부 들어갑니다.
  - 이름표를 두 벌 만듭니다. refs는 「e4 → 엔티티 3」이고 back은 「엔티티 3 → e4」입니다.
    back은 관계 글을 만들 때 쓰고, refs는 LLM 답에 적힌 e4를 다시 엔티티로 되돌릴 때 씁니다.
  - 프롬프트에서 「번호는 entities 칸에만 쓰라」고 시켰지만 LLM이 본문에 e1을 남기기도 합니다.
    그래서 본문에서 e번호 꼴을 지우는 처리를 한 번 더 겁니다.
  - 동시에 2건만 부르는 이유는 조별로 키 하나를 여럿이 나눠 쓰기 때문입니다. 더 많이 부르면 호출 제한에 걸립니다.
  - 마지막으로 cache에 있던 리포트를 같은 reports 사전에 합칩니다. 새로 쓴 것과 재사용한 것이 여기서 한 덩어리가 됩니다.
  - 이어지는 코드 장표는 세 장입니다. 부르는 쪽, 묻기 전 준비, 답 처리 차례로 봅니다.

## 슬라이드 9. K8.4 코드 (1/3)

- 종류: 코드
- 제목: KG 구축 – K8.4 커뮤니티 리포트 생성 실제 코드 (1/3)
- 리드문: 부르는 쪽 코드임. todo만 동시에 2건씩 LLM에 묻고, 재사용 리포트를 같은 사전에 합침
- 코드: index_graph.py k8_summarize#4
- 번호
  - ❶ | reports = {} | 리포트 모을 곳 | 새로 쓴 것과 재사용한 것을 {지문: 리포트} 꼴로 한 사전에 모음
  - ❷ | if todo: | 없으면 건너뜀 | 새로 쓸 커뮤니티가 하나도 없으면 LLM 준비조차 하지 않음
  - ❸ | with ThreadPoolExecutor(max_workers=LLM_CONCURRENCY) as pool: | 동시에 2건 | 일꾼 2명이 커뮤니티를 하나씩 집어 감. 조별 키 하나를 나눠 쓰므로 낮게 둠
  - ❹ | made = list(pool.map( | 순서대로 받음 | 먼저 끝난 순이 아니라 todo 순서대로 결과를 돌려줌. 그래야 지문과 짝지을 수 있음
  - ❺ | for (_, h), report in zip(todo, made): | 지문에 붙임 | todo의 지문과 결과를 순서대로 짝지어 reports에 넣음
  - ❻ | if h in cache: | 재사용 합치기 | 앞 세대 리포트를 그대로 복사해 같은 사전에 넣음. 벡터까지 함께 따라옴
- 굵게
  - LLM_CONCURRENCY
  - dict(cache[h])
- 상세 보기 링크: https://github.com/unicorn-campus/hybrid-ai/blob/main/hands-on/solutions/graphrag/indexer/index_graph.py
- 발표자 노트
  - `pool.map`에 넘긴 이름 없는 함수(lambda)가 커뮤니티 한 건을 summarize_community에 넘김. item[0]이 구성원 목록임
  - usage는 LLM이 몇 번 불렸고 토큰을 얼마나 썼는지를 담음. 실행 끝의 결과 요약에 들어감
  - `dict(cache[h])`로 복사하는 이유는 cache 쪽 값을 실수로 고치지 않기 위함임
  - 이 뒤로 reports에는 이번에 쓴 리포트와 재사용 리포트가 섞여 있음. 다음 단계가 벡터 유무로 구분함

## 슬라이드 10. K8.4 코드 (2/3)

- 종류: 코드
- 제목: KG 구축 – K8.4 커뮤니티 리포트 생성 실제 코드 (2/3)
- 리드문: 묻기 전 준비임. 보낼 엔티티를 고르고 짧은 이름표를 붙여 엔티티 줄과 관계 줄을 만듦
- 코드: index_graph.py summarize_community
- 코드 끝: prompt = REPORT_USER.format(
- 코드 빼기
  - inside = set(members)
  - degree = {i: 0
  - for a, b, _ in relations:
  - if a not in back or b not in back:
- 번호
  - ❶ | key=lambda i: (-degree[i], i), | 중심부터 고름 | 커뮤니티 안 관계 수가 많은 엔티티를 앞으로. 수가 같으면 번호가 작은 순
  - ❷ | top = by_importance[:COMMUNITY_MAX_ENTITIES] | 120개까지만 | 커뮤니티가 커도 LLM 입력 한도를 넘지 않게 앞에서부터 잘라 씀
  - ❸ | refs = {f"e{k}": i for k, i in enumerate(shown, 1)} | 짧은 이름표 | e1은 엔티티 0, e4는 엔티티 3처럼 짝지음. LLM 답을 되돌릴 때 씀
  - ❹ | lines = [entity_line(k, entities[i]) | 엔티티 한 줄씩 | 「e1. 라벨: 속성=값, …」 꼴로 만듦. 한 줄이 300자를 넘으면 잘라 냄
  - ❺ | rels.append(f"{back[a]} -[{relation_type}]-> {back[b]}") | 관계 한 줄씩 | 「e4 -[REQUIRES]-> e1」 꼴. 양 끝이 모두 고른 엔티티일 때만 넣음
  - ❻ | prompt = REPORT_USER.format( | 프롬프트 완성 | 엔티티 줄과 관계 줄을 틀에 끼움. 관계가 하나도 없으면 「(없음)」을 넣음
- 굵게
  - COMMUNITY_MAX_ENTITIES
  - shown = sorted(top)
- 상세 보기 링크: https://github.com/unicorn-campus/hybrid-ai/blob/main/hands-on/solutions/graphrag/indexer/index_graph.py
- 발표자 노트
  - 첫 「...」는 중요도 점수(degree) 세기임. 커뮤니티 안 관계에 나올 때마다 양쪽 엔티티 점수를 1씩 올림
  - `shown = sorted(top)`은 고른 엔티티를 다시 번호순으로 되돌림. e1, e2 이름이 늘 같은 순서로 붙게 함
  - `back`은 refs를 뒤집은 표임(엔티티 번호 → e이름). 관계 줄을 만들 때 씀
  - 마지막 「...」 뒤는 LLM에 묻고 답을 처리하는 부분임. 다음 장표에서 이어서 봄

## 슬라이드 11. K8.4 코드 (3/3)

- 종류: 코드
- 제목: KG 구축 – K8.4 커뮤니티 리포트 생성 실제 코드 (3/3)
- 리드문: 답 처리임. LLM이 준 JSON을 읽어 근거 번호를 엔티티 이름으로 바꾸고, 꼴이 틀리면 다시 물음
- 코드: index_graph.py summarize_community
- 코드 시작: for attempt in range(LLM_RETRIES + 1):
- 코드 빼기
  - findings = []
  - raw_findings = data.get
  - if ref not in refs:
  - entity_no = refs[ref]
  - "title": plain(data["title"]),
  - "summary": plain(data["summary"]),
  - "findings": findings,
  - if attempt == LLM_RETRIES:
  - log(f"[K8 재시도
- 번호
  - ❶ | answer_text = llm.chat_json(prompt, REPORT_SYSTEM) | LLM에 묻기 | 앞 장표에서 만든 프롬프트를 보냄. JSON 하나로만 답하게 해 둠
  - ❷ | data = json.loads(answer_text) | 글자를 값으로 | JSON 글자를 파이썬 사전으로 바꿈. 꼴이 깨졌으면 여기서 오류가 남
  - ❸ | names.append(short_name(entities[entity_no])) | 번호를 이름으로 | LLM이 댄 e4를 「Benefit(대상 결제액의 4%를 할인함.)」 같은 이름으로 바꿈
  - ❹ | findings.append(f"{text} [근거: {evidence}]") | 근거를 붙인 한 문장 | 본문 뒤에 근거 이름을 묶어 적음. 근거가 없으면 「없음」이 들어감
  - ❺ | if not data.get("title") or not data.get("summary"): | 빈 리포트 막기 | 제목이나 요약이 비면 쓸모가 없어 일부러 오류를 내고 다시 물음
  - ❻ | except (json.JSONDecodeError | 꼴 오류만 다시 | 꼴이 틀린 오류만 잡아 다시 묻고, 통신 오류 같은 것은 그대로 멈춤
- 굵게
  - short_name(entities[entity_no])
  - [근거: {evidence}]
- 상세 보기 링크: https://github.com/unicorn-campus/hybrid-ai/blob/main/hands-on/solutions/graphrag/indexer/index_graph.py
- 발표자 노트
  - 첫 「...」는 findings를 담을 빈 목록과 LLM 답의 findings 칸을 꺼내는 자리임. 칸이 없으면 빈 목록으로 봄
  - `names` 위 「...」에서 LLM이 지어낸 이름(e9 등)을 버리고, 쓸 수 있는 이름만 엔티티 번호로 되돌림
  - `plain`은 본문에 남은 「(e1)」 같은 번호를 지우고 공백을 정리하는 작은 함수임(앞 장표의 「...」 안에 있음)
  - 마지막 「...」는 마지막 시도였으면 오류를 그대로 올리고, 아니면 재시도 로그를 남기는 자리임
  - 처음 1번에 더해 LLM_RETRIES(3)번까지 같은 입력으로 다시 물음

## 슬라이드 12. K8.5 설명

- 종류: 설명
- 제목: KG 구축 – K8.5 커뮤니티 리포트 임베딩
- 리드문: 리포트 하나를 글 하나로 이어 붙여 벡터로 바꿈. 벡터가 이미 있는 리포트는 건너뜀
- 도식
  - 상자 A | reports | 새로 쓴 리포트: embedding 없음 / 재사용 리포트: embedding 있음(앞 세대 벡터) / 둘이 한 사전에 섞여 있음
  - 화살표 A → B | "embedding" not in reports[h] 인 것만 고름
  - 상자 B | need_vector | 벡터가 없는 지문만 모음 / 실습 세대 실측은 0개(11개 모두 재사용)
  - 화살표 B → C | 제목, 요약, 핵심 사실을 줄바꿈으로 이음
  - 상자 C | 임베딩할 글 | 한빛 가족돌봄 카드의 병원·약국·쇼핑 할인 혜택 / 한빛 가족돌봄 카드는 병원·약국 결제와 쇼핑 멤버십 이용 시 각각 결제액의 4%를 … / … 전월 이용액이 350,000원 이상이어야 한다 [근거: Benefit(…)]
  - 화살표 C → D | embed_texts로 Cohere에 보냄(96건씩 나눠 부름)
  - 상자 D | reports[지문]["embedding"] | 숫자 2048개 / 리포트마다 하나 / K8.6에서 Community 노드에 저장됨
- 핵심
  - 왜 셋을 다 넣나 | 질문과 뜻이 가까운 커뮤니티를 찾으려면 제목만이 아니라 요약과 핵심 사실까지 벡터에 담겨야 함
  - 왜 96건씩 나누나 | Cohere 한 요청에 넣을 수 있는 최대 건수가 EMBED_BATCH_SIZE(96)임
  - 차원이 다르면 멈춤 | 돌아온 벡터 길이가 EMBED_DIMENSION(2048)과 다르면 그 자리에서 실행을 멈춰 잘못된 색인을 막음
- 발표자 노트
  - 이 벡터는 나중에 「고객군별로 고객 불만을 주제별로 나눠 주세요」 같은 거시 질문에 쓰입니다.
    청크 하나하나를 찾는 대신 커뮤니티 리포트를 찾아 답하는 길이 열립니다.
  - 재사용한 리포트에는 벡터까지 들어 있습니다. community_reports.json에 embedding 칸을 함께 저장해 두기 때문입니다.
    그래서 실습 세대처럼 전부 재사용이면 Cohere 호출도 0번입니다.
  - 벡터를 붙이는 방법은 지문과 벡터를 순서대로 짝짓는 것입니다. need_vector 순서로 글을 만들었기 때문에
    돌아온 벡터 순서도 같습니다. 순서가 어긋나면 엉뚱한 리포트에 붙으니 이 짝이 중요합니다.
  - 엔티티 설명 임베딩(K6)과 같은 모델, 같은 차원을 씁니다. 모델을 바꾸면 두 인덱스를 함께 다시 만들어야 합니다.

## 슬라이드 13. K8.5 코드

- 종류: 코드
- 제목: KG 구축 – K8.5 커뮤니티 리포트 임베딩 실제 코드
- 리드문: 벡터가 없는 리포트만 골라 글로 이어 붙이고, embed_texts가 96건씩 나눠 Cohere를 부름
- 코드: index_graph.py k8_summarize#5; index_graph.py embed_texts
- 코드 빼기
  - global _embedder
  - if not texts:
  - if _embedder is None:
- 번호
  - ❶ | need_vector = [h for _, h in targets if "embedding" not in reports[h]] | 없는 것만 고름 | 새로 쓴 리포트만 남음. 재사용 리포트는 벡터까지 있어 건너뜀
  - ❷ | reports[h]["title"] + "\n" + reports[h]["summary"] | 글 하나로 이음 | 제목, 요약, 핵심 사실을 줄바꿈으로 이어 리포트 하나를 글 하나로 만듦
  - ❸ | for h, vector in zip(need_vector, embed_texts(texts)): | 짝지어 붙임 | 지문과 돌아온 벡터를 순서대로 짝지어 reports에 넣음
  - ❹ | for start in range(0, len(texts), EMBED_BATCH_SIZE): | 96건씩 나눠 부름 | 한 요청에 넣을 수 있는 최대 건수가 96이라 잘라서 여러 번 부름
  - ❺ | if vectors and len(vectors[0]) != EMBED_DIMENSION: | 차원 검사 | 설정값 2048과 다르면 그 자리에서 멈춤. 벡터 인덱스와 어긋나는 사고를 막음
- 굵게
  - EMBED_BATCH_SIZE
  - EMBED_DIMENSION
- 상세 보기 링크: https://github.com/unicorn-campus/hybrid-ai/blob/main/hands-on/solutions/graphrag/indexer/index_graph.py
- 발표자 노트
  - 「...」 안은 임베딩 도구를 처음 한 번만 만드는 자리임(Cohere 키 읽기 포함). 글이 하나도 없으면 바로 빈 목록을 돌려줌
  - embed_texts는 K8 전용이 아님. 청크 임베딩(S1)과 엔티티 설명 임베딩(K6)도 같은 함수를 씀
  - `"\n".join(reports[h]["findings"])`는 핵심 사실 여러 줄을 줄바꿈으로 이어 붙이는 뜻임
  - 벡터는 reports 사전 안에 들어가고, 같은 사전이 그대로 community_reports.json으로 저장됨

## 슬라이드 14. K8.6 설명

- 종류: 설명
- 제목: KG 구축 – K8.6 커뮤니티를 KG 적재
- 리드문: 리포트를 Neo4j에 쓸 행으로 바꾸고, 이 세대의 옛 Community를 지운 뒤 새로 씀
- 도식
  - 상자 A | 입력 | groups (커뮤니티별 엔티티 번호) / hashes (지문) / reports (리포트와 벡터)
  - 화살표 A → B | 엔티티 3개 이상만 골라 번호를 elementId로 바꿈
  - 상자 B | rows 한 줄 | community_id "comm-c2b3c9fbed46" / title, summary, findings / member_hash, size 5 / vec (숫자 2048개) / members (엔티티 elementId 5개)
  - 화살표 B → C | 이 세대의 옛 Community를 지우고 새로 씀
  - 그림 C | Neo4j | in_community | Community 노드 1개와 IN_COMMUNITY 5개 / 벡터 인덱스 kg_community_embedding
  - 화살표 C → D | k8_summarize가 reports를 돌려줌
  - 상자 D | community_reports.json | {지문: 리포트} 파일로 저장 / 다음 실행의 cache가 됨
- 핵심
  - 왜 지우고 다시 쓰나 | 커뮤니티 경계가 조금만 바뀌어도 일부만 고치기 어려움. 엔티티는 그대로 두고 Community만 다시 씀
  - Community에는 __Entity__를 안 붙임 | K6 엔티티 벡터 인덱스와 섞이지 않게 함. 커뮤니티 벡터는 따로 kg_community_embedding에 들어감
  - 다음 세대로 이어짐 | 돌려준 리포트를 파일로 남겨 두면 다음 실행에서 K8.3의 cache가 됨
- 발표자 노트
  - community_id는 지문 앞 12자에 「comm-」을 붙인 것입니다. 실습 세대의 예가 comm-c2b3c9fbed46입니다.
    지문이 안 바뀌면 id도 그대로라, 다시 돌려도 같은 이름이 나옵니다.
  - 관계 방향은 엔티티에서 커뮤니티로 갑니다. 「이 엔티티는 이 커뮤니티에 속함」이라고 읽으면 됩니다.
  - 벡터는 보통 속성처럼 넣지 않고 setNodeVectorProperty로 넣습니다. 벡터 인덱스가 읽을 수 있는 꼴로 저장하기 위해서입니다.
  - 인덱스는 없을 때만 만듭니다. 다만 같은 이름 인덱스가 다른 차원으로 이미 있으면 새 벡터가 색인되지 않으니,
    차원을 바꿨다면 인덱스를 지우고 다시 만들어야 합니다.
  - 코드 장표는 두 장입니다. 행 만들기와 Neo4j에 쓰기를 나눠 봅니다.

## 슬라이드 15. K8.6 코드 (1/2)

- 종류: 코드
- 제목: KG 구축 – K8.6 커뮤니티를 KG 적재 실제 코드 (1/2)
- 리드문: 행 만들기임. 엔티티 3개 이상 커뮤니티만 고르고 번호를 elementId로 바꿔 한 행에 담음
- 코드: index_graph.py k8_summarize#6; core_graph.py build_community_rows
- 코드 빼기
  - for row in rows[:3]:
  - result = {"entities"
  - return result, reports
  - "community_id": "comm-" + member_hash[:12],
  - "title": report["title"],
  - "summary": report["summary"],
  - "findings": report["findings"],
  - "member_hash": member_hash,
  - "size": len(members),
  - "vec": report["embedding"],
  - "members": member_ids,
- 번호
  - ❶ | rows = core.build_community_rows( | 쓸 행 만들기 | 커뮤니티 목록, 지문, 엔티티, 리포트를 넘겨 Neo4j에 쓸 행 목록을 받음
  - ❷ | core.k8_write_communities(driver, generation, run_id, rows | KG에 쓰기 | 행 목록과 벡터 차원, 인덱스 이름을 넘김. 쓰는 일은 다음 장표에서 봄
  - ❸ | if len(members) < min_size: | 작은 것 건너뜀 | 엔티티가 3개보다 적은 커뮤니티는 행을 만들지 않음. Community 노드도 생기지 않음
  - ❹ | report = reports[member_hash] | 지문으로 찾기 | 커뮤니티 지문을 열쇠로 그 커뮤니티의 리포트를 꺼냄
  - ❺ | member_ids.append(entities[number]["id"]) | 번호를 id로 | 엔티티 번호를 Neo4j가 아는 elementId로 바꿈. IN_COMMUNITY의 출발 노드가 됨
  - ❻ | rows.append({ | 한 행에 담기 | community_id, 제목, 요약, 핵심 사실, 지문, 크기, 벡터, 구성원 id를 한 행으로 묶음
- 굵게
  - min_size
  - entities[number]["id"]
- 상세 보기 링크: https://github.com/unicorn-campus/hybrid-ai/blob/main/hands-on/solutions/graphrag/indexer/core_graph.py
- 발표자 노트
  - build_community_rows는 교육생 실습 함수임(빈칸 2곳). 빈칸은 작은 커뮤니티 건너뛰기와 번호를 elementId로 바꾸기
  - 「...」 안의 칸은 community_id, title, summary, findings, member_hash, size, vec, members 여덟 개임
  - community_id는 「comm-」에 지문 앞 12자를 붙인 것임. 예: comm-c2b3c9fbed46
  - k8_summarize는 끝에서 (실행 결과 요약, reports)를 돌려줌. 부른 쪽이 community_reports.json으로 저장해 다음 cache로 씀

## 슬라이드 16. K8.6 코드 (2/2)

- 종류: 코드
- 제목: KG 구축 – K8.6 커뮤니티를 KG 적재 실제 코드 (2/2)
- 리드문: 쓰기임. 이 세대의 옛 Community를 지우고 노드, 벡터, 구성원 관계, 벡터 인덱스를 차례로 만듦
- 코드: core_graph.py k8_write_communities
- 코드 빼기
  - "findings: row.findings
  - "OPTIONS {indexConfig
- 번호
  - ❶ | DETACH DELETE c | 옛것 먼저 지움 | 이 세대의 Community만 관계까지 통째로 지움. 엔티티는 건드리지 않음
  - ❷ | "CREATE (c:Community {community_id | 노드 만들기 | 행 하나가 Community 노드 하나가 됨. __Entity__ 라벨은 붙이지 않음
  - ❸ | db.create.setNodeVectorProperty(c, 'embedding', row.vec) | 벡터 저장 | 리포트 벡터를 Community 노드의 embedding 속성에 넣음
  - ❹ | UNWIND row.members AS member_id | 구성원 펼치기 | 행에 담아 둔 elementId 목록을 한 줄씩 펼쳐 엔티티를 찾음
  - ❺ | CREATE (e)-[:IN_COMMUNITY]->(c) | 구성원 잇기 | 구성원 엔티티마다 커뮤니티로 가는 관계를 만듦
  - ❻ | CREATE VECTOR INDEX {index_name} | 벡터 인덱스 | 없을 때만 만듦. 이름은 kg_community_embedding, 코사인 유사도로 찾음
- 굵게
  - DETACH DELETE c
  - CREATE (e)-[:IN_COMMUNITY]->(c)
- 상세 보기 링크: https://github.com/unicorn-campus/hybrid-ai/blob/main/hands-on/solutions/graphrag/indexer/core_graph.py
- 발표자 노트
  - k8_write_communities는 강사 제공 함수임(빈칸 없음). 커뮤니티 경계가 바뀌면 일부만 고치기 어려워 매번 다시 씀
  - Cypher 한 줄씩 읽으면 됨. 행 펼치기 → 노드 만들기 → 벡터 넣기 → 구성원 펼치기 → 관계 만들기 순서임
  - 「...」는 노드 속성 뒷부분(findings, member_hash, size, generation, run_id)과 인덱스 설정값임
  - 인덱스 설정값은 차원(2048)과 코사인 유사도임. K6 엔티티 인덱스와 이름이 달라 서로 섞이지 않음
