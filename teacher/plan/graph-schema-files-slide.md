# 그래프 교재 「인덱싱이 읽는 스키마 파일 2개」 장표 스크립트

- 덱 파일: `teacher/plan/graph-schema-files.pptx`(1장)  
- 넣을 자리: 교재(W06 ~ W08)의 「1-b 분리형(검색 엔진)의 인덱싱 파이프라인」 장표 바로 뒤  
- 빌드: `teacher/plan/build/build-graph-schema-files.js` → `fix_ph.py` → `check_paste.py`  
  → `merge-graph-schema-files.py {교재}.pptx`  
- 근거 소스(2026-11-19 확인)  
  - 파일: `hands-on/solutions/graphrag/schema/doc/{regulation,benefit_guide,consult_log}/`의  
    `graph_schema.json`, `unit_text_rules.json`  
  - 만드는 곳: `schema/doc/tools/finalize.py`(GraphSchema 검증 뒤 저장)  
  - 읽는 곳: `indexer/index_graph.py`의 `load_schemas()`, `config_signature()`, K2 재사용 판정  
  - 쓰는 곳: `indexer/core_graph.py`의 `k1_split_units()`, `split_by_heading()`, `head_line()`,  
    `extract_one()`(K2 추출, K3 가지치기), `build_graph_rows()`(K4), `k5_merge()`(K5)  
- 예시 약속: 약관(regulation) 값을 씀. 고유 키 예시만 혜택 안내(ProductGuide의 product_id)를 씀  
  (약관의 고유 키 version은 다른 약관이 같은 판 번호를 쓰면 합쳐지는 문제가 있어 예시로 쓰지 않음)

## 슬라이드 1. 인덱싱이 읽는 스키마 파일 2개

- 제목: 인덱싱이 읽는 스키마 파일 2개
- 리드문: graph_schema.json은 무엇을 뽑을지, unit_text_rules.json은 어떤 글을 LLM에 넣을지 정함. 인덱서는 둘 다 읽기만 함
- 왼쪽 헤더 바(네이비): graph_schema.json (스키마 본체)
- 왼쪽 표(키 | 담긴 것 | 약관 예시)
  - node_types | 노드 라벨, 설명(해당, 비해당), 속성 | Clause {clause_no, title} 등 5개
  - relationship_types | 관계 이름과 설명 | HAS_CLAUSE 등 4개
  - patterns | 허용하는 (시작 노드, 관계, 끝 노드) | (TermsDocument, HAS_CLAUSE, Clause)
  - constraints | 고유 키(같은 대상인지 가리는 속성) | ProductGuide의 product_id(혜택 안내 예)
  - additional_* | 스키마 밖 라벨, 관계, 패턴 허용 여부 | false(모두 막음)
- 오른쪽 헤더 바(블루): unit_text_rules.json (추출 청크 글 규칙)
- 오른쪽 표(키 | 담긴 것 | 약관 예시)
  - doc | 문서 유형 | regulation
  - extraction_unit_rule | 청크를 추출 청크로 나누는 규칙. null이면 청크 그대로(혜택 안내, 상담 기록) |
    heading: 「제N조(제목)」 줄 / body_start: ① / drop_lines: 「제N장」 줄
  - metadata_header | 추출 청크 앞에 붙일 머리줄 칸 | source, version, effective_date, supersedes, section_label
- 오른쪽 아래 예시 상자: LLM에 들어가는 글(약관 제2조)
  - 머리줄: `source: D1_개인회원표준약관_합성.pdf | version: 1.2 | effective_date: 2027-01-15 | supersedes: 1.1 | section_label: 제2조(용어의 정의)`
  - 본문: `제2조(용어의 정의)` / `① '본인회원'은 자신의 이름으로 카드를 신청하여 …`
- 아래 흐름(인덱싱에서 쓰는 곳). 상자 위 꼬리표는 쓰는 파일(스키마 = graph_schema.json, 글 규칙 = unit_text_rules.json)
  - 읽기 | 스키마, 글 규칙 | 문서 유형마다 두 파일을 읽음 / 글 규칙 파일이 없으면 멈춤
  - K1 추출 청크 나누기 | 글 규칙 | 약관만 조항마다 자름 / 혜택, 상담은 청크 그대로
  - K2 추출 | 스키마, 글 규칙 | 머리줄 + 본문을 LLM에 넣고 스키마 모양대로 받음
  - K3 가지치기 | 스키마 | 스키마 밖 노드, 관계, 속성을 지움
  - K4 적재, K5 병합 | 스키마 | constraints 값이 같은 노드를 하나로 합침
- 맨 아래 한 줄: ※ 두 파일의 지문(SHA-256)이 설정 지문에 들어감. 하나라도 바뀌면 새로 만들고,
  graph_schema.json 지문과 본문, 머리줄이 모두 같은 추출 청크는 앞 세대 추출 결과를 다시 씀
- 발표자 노트
  - 앞 장 파이프라인 맨 위에 「GraphSchema 파일, 인덱싱은 읽기만 함」 상자가 있었습니다. 이 장은 그 상자를 열어 본 것입니다.
    스키마 설계가 끝나면 문서 유형 폴더마다 파일 세 개가 남는데, 인덱서가 읽는 것은 graph_schema.json과
    unit_text_rules.json 두 개뿐이고 승인 기록(approval.json)은 읽지 않습니다.
  - graph_schema.json은 「무엇을 뽑을지」입니다. 노드 라벨과 속성, 관계, 허용하는 연결 모양(패턴), 고유 키(제약)가 들어 있고,
    additional로 시작하는 세 키가 모두 false라서 스키마에 없는 라벨이나 관계는 받지 않습니다.
    고유 키는 「같은 대상인지」를 가리는 속성입니다. 혜택 안내의 product_id처럼 대상마다 값이 달라야 쓸모가 있습니다.
  - unit_text_rules.json은 「어떤 글을 LLM에 넣을지」입니다. 약관은 청크 하나에 조항이 여러 개 섞여 있어서
    조항 제목 줄을 기준으로 다시 자르고, 혜택 안내와 상담 기록은 규칙이 null이라 청크를 그대로 씁니다.
    metadata_header는 추출 청크 앞에 붙일 머리줄 칸 목록입니다. 본문에 없는 판 번호나 상담 번호를 LLM이 볼 수 있게 해 줍니다.
  - 아래 흐름을 보면 두 파일이 단계마다 나뉘어 쓰입니다. K1은 글 규칙만, K3과 K5는 스키마만 쓰고,
    K2는 둘 다 씁니다. 머리줄을 붙인 글을 스키마와 함께 LLM에 넣기 때문입니다.
  - 두 파일은 설정 지문에도 들어갑니다. 스키마를 고치면 인덱서가 알아서 새로 만들고, 스키마와 글이 그대로인
    추출 청크는 LLM을 다시 부르지 않고 앞 세대 결과를 씁니다.
