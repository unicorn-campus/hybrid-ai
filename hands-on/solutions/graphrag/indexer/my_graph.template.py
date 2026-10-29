"""교육생용 뼈대: core_graph.py와 같은 이름, 같은 인자의 실습 함수 16개를 본인 코드로 채우는 파일임.

채우는 순서(워크플로우 순서). "직접"은 NotImplementedError 자리에 본인 코드를 쓰고, "빈칸"은 거의 완성된 코드의 빈칸만 채움
  [교시 A: 세대와 청크, 추출 단위, 추출]
   1 issue_generation        (직접)      ① 세대 ID 규칙과 사전 검사
   2 prepare_chunks          (빈칸 2곳)  ② doc_id 규칙, chunk_id 규칙
   3 split_by_heading        (직접)      K1 조항 제목 줄로 자르기
   4 k1_split_units          (빈칸 2곳)  K1 단위 ID, 겹친 조항 합치기
   5 extract_one             (빈칸 2곳)  K2 추출기 호출, K3 가지치기 호출
  [교시 B: 그래프 적재, 병합, 임베딩, 커뮤니티]
   6 build_graph_rows        (빈칸 2곳)  K4 청크 노드, FROM_CHUNK
   7 k5_merge                (빈칸 2곳)  K5 같은 값 노드 모으기, mergeNodes
   8 entity_description      (직접)      K6 「라벨: 속성=값」
   9 k6_embed_descriptions   (빈칸 2곳)  K6 벡터 저장, 벡터 인덱스
  10 detect_communities      (빈칸 2곳)  K8 GDS 투영, Leiden
  11 build_community_rows    (빈칸 2곳)  K8 3개 이상 묶음, 구성원 ID
  [교시 C: 검색엔진, 검증, 게시]
  12 embed_with_reuse        (직접)      S1 본문 해시로 벡터 재사용
  13 build_search_docs       (빈칸 2곳)  S2 토큰화, 엔진 문서 한 건
  14 apply_search            (빈칸 3곳)  S3 문서 단위 지우기, bulk, refresh
  15 verify_chunk_ids        (직접)      ④ 세 목록 비교
  16 publish_active          (직접)      ⑤ 활성 세대 파일 교체
  제공(완성본, 읽기만): sha256_text, next_nonblank_line, head_line, group_assignments, k8_write_communities

사용법(이 파일은 강사 뼈대(템플릿)임. 직접 고치지 않고 복사본 my_graph.py를 고침. my_graph.py는 Git이 무시해 pull 충돌이 없음)
  1) index_graph.py를 --mine을 붙여 실행함. my_graph.py가 없으면 이 파일을 복사해 만듦
  2) 채울 함수 이름을 이 파일 맨 아래 USE_TEACHER_CODE 목록에서 지움(지우지 않은 함수는 강사 코드가 대신 돎)
  3) 함수를 채우고 같은 명령으로 실행해 강사 결과와 비교함. 막히면 이름을 목록에 다시 넣고 다음 함수로 넘어감
"""

import asyncio
import hashlib
import json
import os
import re
from pathlib import Path

from neo4j_graphrag.components.entity_relation_extractor import LLMEntityRelationExtractor, OnError
from neo4j_graphrag.components.graph_pruning import GraphPruning
from neo4j_graphrag.components.types import Neo4jGraph, Neo4jNode, Neo4jRelationship, TextChunk, TextChunks
from opensearchpy import helpers

SYSTEM_PROPS = {"generation", "run_id", "embedding"}  # 엔티티 설명 글을 만들 때 빼는 관리용 속성(교재 43쪽 ②)


# ---------------------------------------------------------------------------
# 제공 함수(읽기만): 여러 단계가 함께 쓰는 작은 도구
# ---------------------------------------------------------------------------
def sha256_text(text: str) -> str:
    """글의 SHA-256 해시(16진수 64자). 세대 ID, chunk_id, 본문 해시에 씀."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def next_nonblank_line(lines: list[str], index: int) -> str:
    """index 다음 줄부터 처음 나오는 빈 줄이 아닌 줄을 앞뒤 공백을 떼고 돌려줌. 없으면 빈 문자열."""
    for line in lines[index + 1:]:
        if line.strip() != "":
            return line.strip()
    return ""


def head_line(metadata: dict, fields: list[str]) -> str:
    """메타데이터를 「칸: 값 | 칸: 값」 한 줄로 만들어 추출 단위 앞에 붙임(교재 35쪽 ②). 값이 없는 칸은 뺌."""
    parts = []
    for field in fields:
        value = metadata.get(field)
        if value is None or value == "":
            continue
        parts.append(f"{field}: {value}")
    if not parts:
        return ""
    return " | ".join(parts) + "\n"


# ---------------------------------------------------------------------------
# 1. ① 세대 ID 발급 (교재 31쪽) — 직접 작성
# ---------------------------------------------------------------------------
def issue_generation(run: str, active: dict | None, input_sha256: str, config_signature: str,
                     full_reindex: bool, tag: str) -> dict:
    """실행 이름으로 세대 ID를 만들고, 할 일이 있는지 사전 검사함.

    목적: 같은 실행 이름이면 같은 세대 ID가 나와, 중단돼도 같은 세대로 이어서 만들 수 있게 함(교재 31쪽).
    방법: 세대 ID = "gen-{tag}-{실행 이름(안전한 글자만)}-{실행 이름 해시 앞 8자리}".
          사전 검사는 활성 세대가 있고, 입력 지문과 설정 지문이 모두 같으면 "할 일 없음"(skip=True).
          full_reindex가 True면 사전 검사를 건너뜀(무조건 새로 만듦).
    반환값: {"generation": 세대 ID, "skip": 할 일 없음 여부}.
    힌트: 안전한 글자만 남기기 → re.sub(r"[^A-Za-z0-9_.-]+", "-", run).strip("-"), 비면 "run".
          해시 → sha256_text(run)[:8]. active의 키는 "input_sha256", "config_signature".
    """
    raise NotImplementedError("여기에 본인 코드를 작성함")


# ---------------------------------------------------------------------------
# 2. ② 공통 단계: 청크 한 건 만들기 (교재 31쪽) — 빈칸 2곳
# ---------------------------------------------------------------------------
def prepare_chunks(rows: list[dict]) -> list[dict]:
    """Chroma에서 읽은 행을 인덱싱 입력 청크로 바꿈. doc_id와 chunk_id를 여기서 정함.

    방법: doc_id = 문서 키(D1, D2, D3) + "_" + 문서 구분값. 약관과 혜택은 원천 파일 이름의 해시 16자리,
          상담은 상담 번호(record_id)라 상담 1건이 문서 1개임.
          chunk_id = doc_id + "_" + 본문 해시 16자리 + "_" + 같은 본문 반복 번호 4자리(교재 31쪽 그림).
    반환값: [{"chunk_id", "doc_id", "doc_type", "text", "text_hash", "metadata"}, ...].
    """
    repeat_counter: dict[tuple[str, str], int] = {}  # (doc_id, 본문 해시) → 지금까지 나온 횟수
    next_index: dict[str, int] = {}  # doc_id → 다음 청크의 문서 안 순서
    chunks = []
    for row in rows:
        metadata = dict(row["metadata"])  # 원본을 바꾸지 않으려고 복사함
        text = row["text"]
        doc_key = str(metadata["source"])[:2]  # 원천 파일 이름 앞 두 글자: D1, D2, D3

        # 빈칸 1: doc_id 규칙. 상담(D3)은 metadata["record_id"], 나머지는 sha256_text(원천 파일 이름)[:16].
        #         doc_id는 doc_key와 "_"와 doc_part를 이은 글임
        raise NotImplementedError("빈칸 1을 채울 것")

        text_hash = sha256_text(text)
        repeat = repeat_counter.get((doc_id, text_hash), 0)  # 같은 문서에 같은 본문이 또 나오면 1, 2, ...
        repeat_counter[(doc_id, text_hash)] = repeat + 1

        # 빈칸 2: chunk_id 규칙. 예) D1_27223010abe31291_112f1e4abea05436_0000 (반복 번호는 4자리, 빈자리는 0)
        raise NotImplementedError("빈칸 2를 채우고 이 줄을 지울 것")

        # 혜택 안내는 스키마 머리줄 칸 product_id를 card_id와 같은 값으로 채움(정형 Product와 잇는 키)
        if metadata.get("doc_type") == "benefit_guide" and metadata.get("card_id"):
            metadata.setdefault("product_id", metadata["card_id"])
        metadata["doc_key"] = doc_key
        metadata["chunk_index"] = next_index.get(doc_id, 0)
        next_index[doc_id] = metadata["chunk_index"] + 1
        metadata["chroma_id"] = row["chroma_id"]  # RAG 실습 결과(D2-0067 등)와 대조할 수 있게 남김
        metadata["chunk_id"] = chunk_id

        chunks.append({
            "chunk_id": chunk_id,
            "doc_id": doc_id,
            "doc_type": metadata.get("doc_type"),
            "text": text,
            "text_hash": text_hash,
            "metadata": metadata,
        })
    return chunks


# ---------------------------------------------------------------------------
# 3. K1 추출 단위 나누기 (교재 32, 34쪽) — 직접 작성
# ---------------------------------------------------------------------------
def split_by_heading(text: str, rule: dict) -> list[dict]:
    """청크 본문을 조항 제목 줄 기준으로 잘라 추출 단위 조각 목록을 돌려줌.

    방법: ① 제목 줄(rule["heading"] 정규식에 맞는 줄)이면서 ② 다음 줄(next_nonblank_line)이 rule["body_start"]로
          시작하는 줄만 시작점으로 잡음(차례에 있는 제목 줄은 다음 줄이 또 제목이라 제외됨).
          ③ 다음 시작점 전까지가 한 조각. ④ rule["drop_lines"]에 맞는 줄(장 제목)은 버림.
    반환값: [{"key": 조항 번호(정규식 그룹 1), "section_label": 제목 줄, "text": 조각 본문}, ...]. 제목 줄이 없으면 빈 목록.
    힌트: heading = re.compile(rule["heading"]), lines = text.split("\\n"), 시작점 번호 목록 starts를 먼저 만들고
          enumerate(starts)로 돌며 end를 정함. 조항 번호는 heading.match(제목 줄).group(1).
    """
    raise NotImplementedError("여기에 본인 코드를 작성함")


# ---------------------------------------------------------------------------
# 4. K1 단위 목록 만들기 — 빈칸 2곳
# ---------------------------------------------------------------------------
def k1_split_units(chunks: list[dict], schemas: dict) -> tuple[list[dict], list[str]]:
    """청크 목록을 추출 단위 목록으로 바꿈. 규칙이 있는 문서 유형(약관)만 나누고 나머지는 청크 하나가 단위 하나.

    반환값: (단위 목록, 단위가 하나도 안 나온 청크 ID 목록). 단위는 {"unit_id", "doc_type", "doc_id", "metadata",
            "text", "chunk_ids", "text_hash"}. chunk_ids는 이 단위가 나온 검색용 청크 ID(K4가 FROM_CHUNK를 이을 때 씀).
    """
    units: dict[str, dict] = {}  # 단위 ID → 단위. 겹침을 찾으려고 dict로 모음
    empty_chunks: list[str] = []  # 조항이 하나도 안 나온 청크(표지, 차례 쪽 등)
    for chunk in chunks:
        doc_type = chunk["doc_type"]
        if doc_type not in schemas:  # 스키마가 없는 문서 유형은 그래프를 만들지 않음
            continue
        rule = schemas[doc_type]["unit_rule"]
        if not rule:  # 규칙이 없는 유형(혜택 안내, 상담 기록): 청크 하나가 단위 하나
            units[chunk["chunk_id"]] = {
                "unit_id": chunk["chunk_id"],
                "doc_type": doc_type,
                "doc_id": chunk["doc_id"],
                "metadata": dict(chunk["metadata"]),
                "text": chunk["text"],
                "chunk_ids": [chunk["chunk_id"]],
            }
            continue

        pieces = split_by_heading(chunk["text"], rule)
        if not pieces:
            empty_chunks.append(chunk["chunk_id"])
        for piece in pieces:
            # 빈칸 1: 단위 ID = 문서 ID + "#" + 조항 번호(piece["key"]). 예) D1_27223010abe31291#제16조의2
            raise NotImplementedError("빈칸 1을 채울 것")

            metadata = dict(chunk["metadata"])
            metadata["section_label"] = piece["section_label"]  # 머리줄에 조항 제목을 넣으려고 보탬
            old = units.get(unit_id)
            if old is None:  # 처음 나온 조항
                units[unit_id] = {
                    "unit_id": unit_id,
                    "doc_type": doc_type,
                    "doc_id": chunk["doc_id"],
                    "metadata": metadata,
                    "text": piece["text"],
                    "chunk_ids": [chunk["chunk_id"]],
                }
            elif chunk["chunk_id"] not in old["chunk_ids"]:
                # 빈칸 2: 겹친 조항. 더 긴 글을 old["text"]에 남기고(길이가 같으면 먼저 나온 글),
                #         old["chunk_ids"]에 이 청크 ID를 더함
                raise NotImplementedError("빈칸 2를 채우고 이 줄을 지울 것")

    for unit in units.values():
        unit["text_hash"] = sha256_text(unit["text"])  # K2 재사용 판정(같은 본문은 다시 묻지 않음)에 씀
    return list(units.values()), empty_chunks


# ---------------------------------------------------------------------------
# 5. K2 추출, K3 가지치기 (교재 35, 36쪽) — 빈칸 2곳
# ---------------------------------------------------------------------------
def extract_one(unit: dict, spec: dict, llm, retries: int) -> dict:
    """추출 단위 하나를 LLM에 넣어 노드와 관계를 뽑고(K2), 스키마 밖은 바로 지움(K3).

    인자: spec은 schemas[문서 유형]({"schema": GraphSchema, "header": 머리줄 칸, ...}). llm은 main이 만든 LLMInterface.
    반환값: 성공이면 {"graph": 가지치기 뒤 그래프(dict), "raw_nodes": 가지치기 전 노드 수, "kept_nodes": 뒤 노드 수},
            실패면 {"error": 오류 한 줄}.
    """
    extractor = LLMEntityRelationExtractor(llm=llm, create_lexical_graph=False, on_error=OnError.RAISE)
    pruner = GraphPruning()
    text = head_line(unit["metadata"], spec["header"]) + unit["text"]  # 머리줄(메타데이터) + 단위 본문

    graph = None
    last_error = ""
    for attempt in range(retries + 1):
        try:
            # 빈칸 1: 추출기 호출. TextChunk(text=text, index=0, uid=unit["unit_id"])를 TextChunks(chunks=[...])에 담아
            #         asyncio.run(extractor.run(chunks=..., schema=spec["schema"])) 결과를 graph에 받음
            raise NotImplementedError("빈칸 1을 채울 것")
            break
        except Exception as error:  # LLM 형식 오류, 호출 실패 등. 같은 입력으로 다시 물음
            last_error = f"{type(error).__name__}: {str(error)[:200]}"
            print(f"      [K2 시도 {attempt + 1}/{retries + 1} 실패] {unit['unit_id']}: {last_error[:80]}")
    if graph is None:
        return {"error": last_error}

    # 빈칸 2: 가지치기(K3). asyncio.run(pruner.run(graph, spec["schema"])).graph 를 pruned에 받음
    raise NotImplementedError("빈칸 2를 채우고 이 줄을 지울 것")

    return {"graph": pruned.model_dump(), "raw_nodes": len(graph.nodes), "kept_nodes": len(pruned.nodes)}


# ---------------------------------------------------------------------------
# 6. K4 적재: 그래프 행 만들기 (교재 37, 38쪽) — 빈칸 2곳
# ---------------------------------------------------------------------------
def build_graph_rows(chunks: list[dict], units: list[dict], schemas: dict, generation: str,
                     run_id: str) -> tuple[list, list, set]:
    """Neo4j에 한 번에 쓸 노드 목록, 관계 목록, K5에서 합칠 값을 만듦.

    방법: ① 청크 노드(라벨 Chunk)를 청크마다 만듦 ② 추출 성공 단위의 노드마다 세대와 실행 표시를 붙이고
          그 단위가 나온 청크마다 FROM_CHUNK 관계를 만듦(겹친 조항이면 청크 2개) ③ 스키마 고유 속성(UNIQUENESS)의
          라벨과 같은 노드면 (라벨, 속성, 값)을 모아 K5에 넘김 ④ LLM이 뽑은 관계를 그대로 더함.
    반환값: (노드 목록, 관계 목록, 병합 키 집합). 노드와 관계는 neo4j-graphrag의 Neo4jNode, Neo4jRelationship.
    """
    nodes = []
    relationships = []
    merge_keys: set[tuple[str, str, str]] = set()

    def chunk_node_id(chunk_id: str) -> str:
        """청크 노드의 임시 ID. 이 실행 안에서 관계 양 끝을 찾는 데만 쓰고 저장 뒤에는 라이브러리가 지움."""
        return f"{generation}|{chunk_id}|{run_id}"

    # 빈칸 1: 청크 노드. 청크마다 Neo4jNode(id=chunk_node_id(chunk_id), label="Chunk", properties={...})를 nodes에 더함.
    #         properties에는 generation, run_id, chunk_id, doc_id, doc_type, text를 넣음
    raise NotImplementedError("빈칸 1을 채울 것")

    for unit in units:
        if "graph" not in unit:  # 추출에 실패한 단위는 건너뜀(청크 노드는 위에서 이미 만들었음)
            continue
        graph = Neo4jGraph.model_validate(unit["graph"])  # dict로 보관한 그래프를 라이브러리 객체로 되돌림
        constraints = schemas[unit["doc_type"]]["schema"].constraints  # 이 문서 유형의 고유 속성 제약
        for node in graph.nodes:
            # 모든 엔티티에 세대와 실행 표시. 세대끼리 섞이지 않게 함(교재 37쪽 ②)
            node.properties = {**(node.properties or {}), "generation": generation, "run_id": run_id}
            nodes.append(node)

            # 빈칸 2: FROM_CHUNK. unit["chunk_ids"]의 청크마다(중복 제거: dict.fromkeys)
            #         Neo4jRelationship(type="FROM_CHUNK", start_node_id=node.id, end_node_id=chunk_node_id(청크 ID))를 더함
            raise NotImplementedError("빈칸 2를 채우고 이 줄을 지울 것")

            # K5에서 합칠 값 모으기: 제약의 라벨과 노드 라벨이 같고 값이 있을 때만(교재 39쪽 ③)
            for constraint in constraints:
                value = node.properties.get(constraint.property_name)
                if constraint.node_type == node.label and value not in (None, ""):
                    merge_keys.add((node.label, constraint.property_name, str(value)))

        relationships.extend(graph.relationships)  # LLM이 뽑은 관계(HAS_CLAUSE 등)를 그대로 더함
    return nodes, relationships, merge_keys


# ---------------------------------------------------------------------------
# 7. K5 병합 (교재 39 ~ 41쪽) — 빈칸 2곳
# ---------------------------------------------------------------------------
def k5_merge(driver, generation: str, merge_keys: set) -> int:
    """같은 세대에서 스키마 고유 속성 값이 같은 노드를 하나로 합침.

    방법: (라벨, 속성, 값)마다 같은 세대에서 값이 같은 노드를 모아 2개 이상이면 APOC mergeNodes로 합침.
          속성이 다르면 목록 첫 노드 값을 남기고(discard), 관계는 모두 합친 노드로 옮김(mergeRels).
    반환값: 합쳐진 묶음 수.
    """
    groups = 0
    keys = sorted(merge_keys)  # 순서를 고정해 실행마다 같은 순서로 합침
    for number, (label, prop, value) in enumerate(keys, start=1):
        # 빈칸 1: 같은 세대에서 라벨과 속성 값이 같은 노드를 모음(MATCH ... WHERE toString(n.`{prop}`) = $v,
        #         WITH collect(n) AS ns WHERE size(ns) > 1)
        # 빈칸 2: CALL apoc.refactor.mergeNodes(ns, {properties: 'discard', mergeRels: true}) YIELD node
        #         RETURN count(node) AS merged
        #         → driver.execute_query(질의, g=generation, v=value) 결과의 merged를 groups에 더함
        raise NotImplementedError("빈칸 1과 2를 채우고 이 줄을 지울 것")
        if number % 50 == 0:  # 값이 많을 때 멈춘 것처럼 보이지 않게 진행을 알림
            print(f"      [K5] {number}/{len(keys)}개 값 검사, 지금까지 {groups}묶음 합침")
    return groups


# ---------------------------------------------------------------------------
# 8. K6 엔티티 설명 글 (교재 43쪽) — 직접 작성
# ---------------------------------------------------------------------------
def entity_description(label: str, props: dict) -> str:
    """엔티티 하나를 「라벨: 속성=값, 속성=값」 설명 글로 바꿈.

    방법: 관리용 속성(SYSTEM_PROPS)은 빼고, 속성 이름순으로 "이름=값"을 ", "로 이음.
    예시: ("Proposal", {"content": "주문 내역 화면 대조", "decision": "수용", "generation": "gen-..."})
          → "Proposal: content=주문 내역 화면 대조, decision=수용"
    """
    raise NotImplementedError("여기에 본인 코드를 작성함")


# ---------------------------------------------------------------------------
# 9. K6 설명 임베딩과 벡터 인덱스 (교재 44쪽) — 빈칸 2곳
# ---------------------------------------------------------------------------
def k6_embed_descriptions(driver, generation: str, embed_texts, dimension: int, index_name: str) -> int:
    """임베딩이 없는 엔티티의 설명 글을 임베딩해 저장하고 벡터 인덱스를 만듦.

    인자: embed_texts는 글 목록을 받아 벡터 목록을 돌려주는 함수(main 제공, 96건씩 나눠 부름).
    반환값: 임베딩한 엔티티 수.
    """
    records, _, _ = driver.execute_query(
        "MATCH (n:__Entity__ {generation: $g}) WHERE n.embedding IS NULL "
        "RETURN elementId(n) AS id, [l IN labels(n) WHERE NOT l STARTS WITH '__'][0] AS label, "
        "properties(n) AS props", g=generation)
    rows = []
    for record in records:
        rows.append(dict(record))
    if not rows:
        return 0

    texts = []
    for row in rows:
        texts.append(entity_description(row["label"], row["props"]))
    vectors = embed_texts(texts)  # 96건씩 나눠 API를 부르는 일은 main이 맡음

    # 빈칸 1: 벡터 저장. [{"id": elementId, "vec": 벡터}, ...]를 만들어 아래 질의에 rows로 넘김
    #         "UNWIND $rows AS row MATCH (n) WHERE elementId(n) = row.id
    #          CALL db.create.setNodeVectorProperty(n, 'embedding', row.vec)"
    raise NotImplementedError("빈칸 1을 채울 것")

    # 빈칸 2: 벡터 인덱스. CREATE VECTOR INDEX {index_name} IF NOT EXISTS FOR (n:__Entity__) ON n.embedding
    #         OPTIONS {indexConfig: {`vector.dimensions`: $d, `vector.similarity_function`: 'cosine'}}  (d=dimension)
    raise NotImplementedError("빈칸 2를 채우고 이 줄을 지울 것")
    return len(rows)


# ---------------------------------------------------------------------------
# 10. K8 커뮤니티 찾기 (교재 48쪽) — 빈칸 2곳
# ---------------------------------------------------------------------------
def group_assignments(assignments: dict[int, int]) -> list[list[int]]:
    """제공 함수. 「엔티티 번호 → 묶음 번호」를 묶음 목록으로 바꿈. 묶음 안은 번호순, 묶음끼리는 가장 작은 번호순."""
    by_community: dict[int, list[int]] = {}
    for entity_no, community_no in assignments.items():
        by_community.setdefault(community_no, []).append(entity_no)
    groups = []
    for members in by_community.values():
        groups.append(sorted(members))
    groups.sort(key=lambda members: members[0])
    return groups


def detect_communities(driver, graph_name: str, entity_ids: list[str], edges: list[tuple[int, int]],
                       seed: int) -> list[list[int]]:
    """GDS Leiden으로 엔티티를 묶음(커뮤니티)으로 나눔.

    방법: ① 엔티티와 엔티티 사이 줄만 GDS 메모리에 투영함(무방향) ② Leiden을 씨앗 고정, 병렬 1로 한 번 불러
          묶음 번호를 받음 ③ finally로 투영 그래프를 반드시 지움 ④ 묶음 번호를 구성원 목록으로 바꿈.
    반환값: [[엔티티 번호, ...], ...] 묶음 목록.
    """
    if not entity_ids:
        return []
    # 줄이 없는 엔티티도 들어가게 노드 행(t 없음)을 먼저 두고, 그 뒤에 줄 행을 둠
    rows = []
    for number in range(len(entity_ids)):
        rows.append({"s": number, "t": None})
    for a, b in edges:
        rows.append({"s": a, "t": b})
    try:
        # 빈칸 1: 투영. "UNWIND $rows AS row MATCH (s) WHERE elementId(s) = $ids[row.s]
        #         OPTIONAL MATCH (t) WHERE row.t IS NOT NULL AND elementId(t) = $ids[row.t]
        #         WITH gds.graph.project($name, s, t, {}, {undirectedRelationshipTypes: ['*']}) AS g
        #         RETURN g.nodeCount AS n"
        #         (rows=rows, ids=entity_ids, name=graph_name)
        raise NotImplementedError("빈칸 1을 채울 것")
        # 빈칸 2: Leiden. "CALL gds.leiden.stream($name, {randomSeed: $seed, concurrency: 1}) YIELD nodeId, communityId
        #         RETURN elementId(gds.util.asNode(nodeId)) AS id, communityId AS c"  → records에 받음
        raise NotImplementedError("빈칸 2를 채우고 이 줄을 지울 것")
    finally:
        # 성공해도 오류가 나도 투영 그래프를 지움. 안 지우면 메모리를 계속 차지함
        driver.execute_query("CALL gds.graph.drop($name, false) YIELD graphName RETURN graphName", name=graph_name)

    position = {}  # elementId → 엔티티 번호
    for number, entity_id in enumerate(entity_ids):
        position[entity_id] = number
    assignments = {}
    for record in records:
        assignments[position[record["id"]]] = record["c"]
    return group_assignments(assignments)


# ---------------------------------------------------------------------------
# 11. K8 커뮤니티 행 만들기 (교재 49쪽) — 빈칸 2곳
# ---------------------------------------------------------------------------
def build_community_rows(groups: list[list[int]], group_hashes: list[str], entities: list[dict],
                         reports: dict, min_size: int) -> list[dict]:
    """보고서가 있는 묶음을 Neo4j에 쓸 행으로 만듦.

    방법: 묶음마다 ① 크기가 min_size보다 작으면 건너뜀 ② 지문(group_hashes)으로 보고서를 찾음 ③ 구성원 번호를 엔티티 ID로 바꿈.
    인자: reports는 {묶음 지문: {"title", "summary", "findings", "embedding"}}(main이 LLM과 임베딩으로 채움).
    """
    rows = []
    for members, member_hash in zip(groups, group_hashes):
        # 빈칸 1: 엔티티가 min_size개보다 적은 묶음은 보고서를 쓰지 않음 → continue
        raise NotImplementedError("빈칸 1을 채울 것")
        report = reports[member_hash]

        # 빈칸 2: 묶음 안 번호(members의 각 번호)를 entities[번호]["id"]로 바꿔 member_ids 목록을 만듦
        raise NotImplementedError("빈칸 2를 채우고 이 줄을 지울 것")

        rows.append({
            "community_id": "comm-" + member_hash[:12],
            "title": report["title"],
            "summary": report["summary"],
            "findings": report["findings"],
            "member_hash": member_hash,
            "size": len(members),
            "vec": report["embedding"],
            "members": member_ids,
        })
    return rows


def k8_write_communities(driver, generation: str, run_id: str, rows: list[dict], dimension: int,
                         index_name: str) -> None:
    """제공 함수. 이 세대의 옛 Community를 지우고 새 Community 노드와 IN_COMMUNITY 관계를 쓰고 벡터 인덱스를 만듦."""
    driver.execute_query("MATCH (c:Community {generation: $g}) DETACH DELETE c", g=generation)
    if rows:
        driver.execute_query(
            "UNWIND $rows AS row "
            "CREATE (c:Community {community_id: row.community_id, title: row.title, summary: row.summary, "
            "findings: row.findings, member_hash: row.member_hash, size: row.size, generation: $g, run_id: $run}) "
            "WITH c, row CALL db.create.setNodeVectorProperty(c, 'embedding', row.vec) "
            "WITH c, row UNWIND row.members AS member_id MATCH (e) WHERE elementId(e) = member_id "
            "CREATE (e)-[:IN_COMMUNITY]->(c)", rows=rows, g=generation, run=run_id)
    driver.execute_query(
        f"CREATE VECTOR INDEX {index_name} IF NOT EXISTS FOR (c:Community) ON c.embedding "
        "OPTIONS {indexConfig: {`vector.dimensions`: $d, `vector.similarity_function`: 'cosine'}}", d=dimension)


# ---------------------------------------------------------------------------
# 12. S1 임베딩: 벡터 재사용 (교재 54, 55쪽) — 직접 작성
# ---------------------------------------------------------------------------
def embed_with_reuse(texts: list[str], hashes: list[str], old_vectors: dict[str, list[float]],
                     embed_texts) -> tuple[list[list[float]], int]:
    """본문 해시가 활성 세대에 있으면 그 벡터를 다시 쓰고, 없는 본문만 새로 임베딩함.

    방법: ① 해시가 old_vectors에 없는 글만 골라 ② 한 번에 embed_texts로 임베딩하고(없으면 부르지 않음)
          ③ 원래 순서대로 재사용 벡터와 합침.
    인자: texts와 hashes는 같은 길이. old_vectors는 {본문 해시: 벡터}(없으면 빈 dict).
    반환값: (청크 순서대로의 벡터 목록, 새로 임베딩한 수).
    """
    raise NotImplementedError("여기에 본인 코드를 작성함")


# ---------------------------------------------------------------------------
# 13. S2 키워드 분석: 엔진 문서 한 건 만들기 (교재 53, 56 ~ 58쪽) — 빈칸 2곳
# ---------------------------------------------------------------------------
def build_search_docs(chunks: list[dict], hashes: list[str], vectors: list[list[float]], lexicon,
                      meta_fields: tuple) -> list[dict]:
    """청크마다 검색엔진에 넣을 문서 한 건(벡터 + 낱말 + 메타데이터)을 만듦.

    인자: lexicon은 kr_tokenizer.Lexicon(tokenize(글) → 낱말 목록). meta_fields는 검색엔진 필드로 남길 메타데이터 키.
    반환값: [{"chunk_id", "doc_id", "text_hash", "text", "text_tokens", "embedding", 메타데이터...}, ...].
    """
    docs = []
    for chunk, text_hash, vector in zip(chunks, hashes, vectors):
        # 빈칸 1: 키워드 분석. lexicon.tokenize(chunk["text"]) → tokens
        raise NotImplementedError("빈칸 1을 채울 것")

        # 빈칸 2: 엔진 문서 한 건 doc = {"chunk_id", "doc_id", "text_hash", "text", "text_tokens", "embedding"}.
        #         text_tokens는 낱말을 " "로 이은 글임
        raise NotImplementedError("빈칸 2를 채우고 이 줄을 지울 것")
        for field in meta_fields:  # 값이 있는 메타데이터만 문자열로 넣음(필터와 출처 표시에 씀)
            value = chunk["metadata"].get(field)
            if value is not None and value != "":
                doc[field] = str(value)
        docs.append(doc)
    return docs


# ---------------------------------------------------------------------------
# 14. S3 적재: 검색엔진에 쓰기 (교재 58, 59쪽) — 빈칸 3곳
# ---------------------------------------------------------------------------
def apply_search(os_client, index: str, docs: list[dict], mapping: dict) -> dict:
    """문서(doc_id)마다 옛 청크를 지우고 새 청크를 한꺼번에 넣은 뒤 바로 검색되게 함.

    방법: ① 인덱스가 없으면 매핑으로 만듦 ② 넣을 문서의 doc_id를 모음 ③ doc_id마다 delete_by_query로 옛 청크를 지움
          ④ bulk로 한꺼번에 넣음(_id = chunk_id) ⑤ refresh로 바로 보이게 함.
    반환값: {"deleted": 지운 수, "indexed": 넣은 수, "documents": 문서 수}.
    """
    if not os_client.indices.exists(index=index):  # ① 이번 세대 인덱스가 없으면 만듦
        os_client.indices.create(index=index, body=mapping)

    doc_ids = set()  # ② 지울 문서 고르기
    for doc in docs:
        doc_ids.add(doc["doc_id"])

    deleted = 0
    for doc_id in sorted(doc_ids):
        # 빈칸 1: 옛 청크 지우기. os_client.delete_by_query(index=index, body={"query": {"term": {"doc_id": doc_id}}},
        #         refresh=True, conflicts="proceed") 결과의 "deleted"를 deleted에 더함
        raise NotImplementedError("빈칸 1을 채울 것")

    # 빈칸 2: 한꺼번에 넣기. [{"_index": index, "_id": doc["chunk_id"], "_source": doc}, ...]를 만들어
    #         helpers.bulk(os_client, 그 목록, max_retries=3)
    raise NotImplementedError("빈칸 2를 채우고 이 줄을 지울 것")

    # 빈칸 3: 반영. os_client.indices.refresh(index=index)
    raise NotImplementedError("빈칸 3을 채우고 이 줄을 지울 것")

    return {"deleted": deleted, "indexed": len(docs), "documents": len(doc_ids)}


# ---------------------------------------------------------------------------
# 15. ④ 검증: chunk_id 목록 비교 (교재 60, 61쪽) — 직접 작성
# ---------------------------------------------------------------------------
def verify_chunk_ids(all_ids: set[str], search_ids: set[str], kg_list: list[str]) -> dict:
    """입력 청크, 검색엔진, 그래프 청크 노드의 chunk_id가 모두 같은지 검사함.

    방법: 검사 1 검색엔진 = 입력(집합 비교), 검사 2 그래프 = 입력(집합 비교), 검사 3 청크 하나에 노드 하나
          (kg_list를 그대로 세어 두 번 이상 나온 chunk_id를 찾음. 집합으로 바꾸면 사라져 못 잡음).
    반환값: {"ok", "search_equal", "kg_equal", "search_missing", "search_extra", "kg_missing", "kg_extra",
            "kg_duplicate_chunk_nodes"}. 목록 값은 정렬된 list. ok는 셋 다 맞을 때만 True.
    힌트: 빠진 것 = sorted(all_ids - search_ids), 남는 것 = sorted(search_ids - all_ids).
    """
    raise NotImplementedError("여기에 본인 코드를 작성함")


# ---------------------------------------------------------------------------
# 16. ⑤ 게시: 활성 세대 파일 교체 (교재 30, 62쪽) — 직접 작성
# ---------------------------------------------------------------------------
def publish_active(record: dict, active_file: Path) -> None:
    """활성 세대 파일 하나만 새 세대 기록으로 바꿔 끼움.

    방법: 폴더가 없으면 만들고, 임시 파일(같은 폴더, 뒤에 .tmp)에 json.dumps(record, ensure_ascii=False, indent=1)를
          다 쓴 뒤 os.replace(임시 파일, active_file)로 이름을 바꿈. 쓰다가 멈춰도 반쯤 쓴 파일이 활성 세대로 보이지 않음.
    """
    raise NotImplementedError("여기에 본인 코드를 작성함")


# ---------------------------------------------------------------------------
# 아직 채우지 않은 함수는 강사 코드(core_graph)로 대신 돌게 함.
# 함수를 채울 때마다 그 이름을 아래 목록에서 지움. 목록이 비면 이 파일의 코드만으로 전체가 돎.
# 막히면 이름을 다시 넣어 뒤 단계를 계속함(실습이 멈추지 않음)
# ---------------------------------------------------------------------------
import core_graph as _teacher  # noqa: E402

USE_TEACHER_CODE = [
    "issue_generation", "prepare_chunks", "split_by_heading", "k1_split_units", "extract_one",
    "build_graph_rows", "k5_merge", "entity_description", "k6_embed_descriptions",
    "detect_communities", "build_community_rows",
    "embed_with_reuse", "build_search_docs", "apply_search", "verify_chunk_ids", "publish_active",
]
for _name in USE_TEACHER_CODE:
    globals()[_name] = getattr(_teacher, _name)  # 이 파일의 빈 함수 대신 강사 함수를 같은 이름으로 둠
