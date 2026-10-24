"""GraphRAG 인덱싱 핵심 모듈: 워크플로우 단계마다 하나씩 둔 실습 함수 16개(교육생 클론 코딩 대상)와 제공 함수 몇 개임.

이 파일의 함수는 main(index_graph.py)이 순서대로 부름. 단계와 함수의 대응은 아래와 같음(교재 30 ~ 62쪽).
  ① 세대 ID 발급      issue_generation          (직접 작성)
  ② 공통 단계         prepare_chunks            (빈칸 2곳)   doc_id와 chunk_id 규칙
  K1 추출 단위 나누기  split_by_heading          (직접 작성)  조항 제목 줄로 자르기
                      k1_split_units            (빈칸 2곳)   단위 ID, 겹친 조항 합치기
  K2 추출, K3 가지치기 extract_one               (빈칸 2곳)   추출기 호출, 가지치기 호출
  K4 적재             build_graph_rows          (빈칸 2곳)   청크 노드, FROM_CHUNK
  K5 병합             k5_merge                  (빈칸 2곳)   같은 값 노드 모으기, mergeNodes
  K6 설명 임베딩       entity_description        (직접 작성)  「라벨: 속성=값」
                      k6_embed_descriptions     (빈칸 2곳)   벡터 저장, 벡터 인덱스
  K8 커뮤니티 요약     detect_communities        (빈칸 2곳)   GDS 투영, Leiden
                      build_community_rows      (빈칸 2곳)   3개 이상 묶음, 구성원 ID
  S1 임베딩           embed_with_reuse          (직접 작성)  본문 해시로 벡터 재사용
  S2 키워드 분석       build_search_docs         (빈칸 2곳)   토큰화, 엔진 문서 한 건
  S3 적재             apply_search              (빈칸 3곳)   문서 단위 지우기, bulk, refresh
  ④ 검증              verify_chunk_ids          (직접 작성)  세 목록 비교
  ⑤ 게시              publish_active            (직접 작성)  활성 세대 파일 교체
  제공(읽기만): sha256_text, next_nonblank_line, head_line, group_assignments, k8_write_communities

교육생은 my_graph.py(뼈대)에 같은 이름, 같은 인자로 함수를 채운 뒤 main의 import 한 줄을 my_graph로 바꿔 실행함.
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
    """메타데이터를 「칸: 값 | 칸: 값」 한 줄로 만들어 추출 단위 앞에 붙임(교재 35쪽 ②).

    값이 없는 칸은 뺌. 상담 번호나 날짜처럼 본문에 없는 키 속성을 LLM이 채우게 하려는 것임.
    """
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
# ① 세대 ID 발급 (교재 31쪽) — 직접 작성
# ---------------------------------------------------------------------------
def issue_generation(run: str, active: dict | None, input_sha256: str, config_signature: str,
                     full_reindex: bool, tag: str) -> dict:
    """실행 이름으로 세대 ID를 만들고, 할 일이 있는지 사전 검사함.

    목적: 같은 실행 이름이면 같은 세대 ID가 나와, 중단돼도 같은 세대로 이어서 만들 수 있게 함(교재 31쪽).
    방법: 세대 ID = "gen-{tag}-{실행 이름(안전한 글자만)}-{실행 이름 해시 앞 8자리}".
          사전 검사는 활성 세대가 있고, 입력 지문과 설정 지문이 모두 같으면 "할 일 없음"(skip=True).
          full_reindex가 True면 사전 검사를 건너뜀(무조건 새로 만듦).
    인자: active는 활성 세대 파일 내용(없으면 None). input_sha256은 청크 전체의 지문, config_signature는 설정 지문.
    반환값: {"generation": 세대 ID, "skip": 할 일 없음 여부}.
    """
    # 실행 이름에서 영문, 숫자, "_", ".", "-" 만 남기고 나머지는 "-"로 바꿈(인덱스 이름에 쓸 수 있는 글자만)
    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "-", run)
    safe_name = safe_name.strip("-")  # 앞뒤에 남은 "-" 제거
    if safe_name == "":  # 전부 바뀌어 비면 기본 이름
        safe_name = "run"

    # 실행 이름 전체의 해시 앞 8자리. 이름이 같으면 해시도 같아 세대 ID가 같음
    short_hash = sha256_text(run)[:8]
    generation = f"gen-{tag}-{safe_name}-{short_hash}"

    # 사전 검사: 세 조건이 모두 맞을 때만 할 일 없음
    skip = False
    if active is not None and not full_reindex:  # 활성 세대가 있고, 강제 재색인이 아닐 때만 비교함
        same_input = active.get("input_sha256") == input_sha256  # 원천(청크) 지문이 같음
        same_config = active.get("config_signature") == config_signature  # 스키마, 모델, 토큰화 설정이 같음
        if same_input and same_config:
            skip = True
    return {"generation": generation, "skip": skip}


# ---------------------------------------------------------------------------
# ② 공통 단계: 청크 한 건 만들기 (교재 31쪽) — 빈칸 2곳
# ---------------------------------------------------------------------------
def prepare_chunks(rows: list[dict]) -> list[dict]:
    """Chroma에서 읽은 행을 인덱싱 입력 청크로 바꿈. doc_id와 chunk_id를 여기서 정함.

    목적: 두 저장소(검색엔진, 그래프)가 같은 열쇠(chunk_id)를 쓰고, 문서 단위 교체(S3)에 쓸 doc_id를 갖게 함.
    방법: doc_id = 문서 키(D1, D2, D3) + "_" + 문서 구분값. 약관과 혜택은 원천 파일 이름의 해시 16자리,
          상담은 상담 번호(record_id)라 상담 1건이 문서 1개임.
          chunk_id = doc_id + "_" + 본문 해시 16자리 + "_" + 같은 본문 반복 번호 4자리(교재 31쪽 그림).
    인자: rows는 [{"chroma_id": "D1-0001", "text": 본문, "metadata": {...}}, ...]. chroma_id 순서가 문서 안 순서임.
    반환값: [{"chunk_id", "doc_id", "doc_type", "text", "text_hash", "metadata"}, ...]. 메타데이터에
            doc_key, chunk_index(문서 안 순서), chroma_id, chunk_id, product_id(혜택 안내)를 더함.
    """
    repeat_counter: dict[tuple[str, str], int] = {}  # (doc_id, 본문 해시) → 지금까지 나온 횟수
    next_index: dict[str, int] = {}  # doc_id → 다음 청크의 문서 안 순서
    chunks = []
    for row in rows:
        metadata = dict(row["metadata"])  # 원본을 바꾸지 않으려고 복사함
        text = row["text"]
        doc_key = str(metadata["source"])[:2]  # 원천 파일 이름 앞 두 글자: D1, D2, D3

        # 빈칸 1: doc_id 규칙. 상담(D3)은 상담 번호, 나머지는 원천 파일 이름 해시 앞 16자리
        if doc_key == "D3":
            doc_part = str(metadata["record_id"])
        else:
            doc_part = sha256_text(str(metadata["source"]))[:16]
        doc_id = doc_key + "_" + doc_part

        text_hash = sha256_text(text)
        repeat = repeat_counter.get((doc_id, text_hash), 0)  # 같은 문서에 같은 본문이 또 나오면 1, 2, ...
        repeat_counter[(doc_id, text_hash)] = repeat + 1

        # 빈칸 2: chunk_id 규칙. 예) D1_27223010abe31291_112f1e4abea05436_0000
        chunk_id = f"{doc_id}_{text_hash[:16]}_{repeat:04d}"

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
# K1 추출 단위 나누기 (교재 32, 34쪽)
# ---------------------------------------------------------------------------
def split_by_heading(text: str, rule: dict) -> list[dict]:
    """청크 본문을 조항 제목 줄 기준으로 잘라 추출 단위 조각 목록을 돌려줌. — 직접 작성

    목적: 약관 청크 하나에 조항이 여러 개 섞여 있으면 LLM이 조항 안의 조건과 기한을 놓치므로, 조항마다 따로 넣으려는 것임.
    방법: ① 제목 줄(예: 「제16조(할부 거래)」)이면서 ② 다음 줄이 본문 시작 표시(①)로 시작하는 줄만 시작점으로 잡음
          (차례에 있는 제목 줄은 다음 줄이 또 제목이라 제외됨). ③ 다음 시작점 전까지가 한 조각. ④ 장 제목 줄은 버림.
    인자: rule은 스키마 승인 기록의 추출 단위 규칙 {"heading": 제목 줄 정규식(그룹 1이 조항 번호), "body_start": "①",
          "drop_lines": 버릴 줄 정규식(없을 수 있음)}.
    반환값: [{"key": "제16조의2", "section_label": "제16조의2(할부 거래의 철회 요청)", "text": 조각 본문}, ...].
            제목 줄이 하나도 없으면 빈 목록.
    """
    heading = re.compile(rule["heading"])  # 제목 줄 정규식
    drop = None
    if rule.get("drop_lines"):  # 버릴 줄 규칙이 있을 때만 정규식을 만듦
        drop = re.compile(rule["drop_lines"])
    lines = text.split("\n")

    # 시작점 찾기: 제목 줄이면서 다음 줄이 본문 시작 표시로 시작하는 줄의 번호
    starts = []
    for index, line in enumerate(lines):
        if not heading.match(line.strip()):  # 제목 줄이 아니면 넘어감
            continue
        if not next_nonblank_line(lines, index).startswith(rule["body_start"]):  # 다음 줄이 ①이 아니면 차례임
            continue
        starts.append(index)

    # 시작점마다 다음 시작점 전까지를 한 조각으로 만듦
    pieces = []
    for order, start in enumerate(starts):
        if order + 1 < len(starts):  # 다음 시작점이 있으면 거기까지
            end = starts[order + 1]
        else:  # 마지막 조각은 끝까지
            end = len(lines)
        body_lines = []
        for line in lines[start:end]:
            if drop is not None and drop.match(line.strip()):  # 장 제목(제2장 ...) 같은 줄은 버림
                continue
            body_lines.append(line)
        title_line = lines[start].strip()
        clause_no = heading.match(title_line).group(1)  # 정규식 그룹 1 = 조항 번호(제16조의2)
        pieces.append({
            "key": clause_no,
            "section_label": title_line,
            "text": "\n".join(body_lines).strip(),
        })
    return pieces


def k1_split_units(chunks: list[dict], schemas: dict) -> tuple[list[dict], list[str]]:
    """청크 목록을 추출 단위 목록으로 바꿈. 규칙이 있는 문서 유형(약관)만 나누고 나머지는 청크 하나가 단위 하나. — 빈칸 2곳

    목적: LLM에 한 번에 넣을 글 조각(추출 단위)을 정함. 단위는 LLM 입력에만 쓰고 그래프 노드가 되지 않음(교재 32쪽).
    방법: 문서 유형의 unit_rule이 없으면 청크 그대로. 있으면 split_by_heading으로 나누고,
          단위 ID = 문서 ID + "#" + 조항 번호. 같은 단위 ID가 다른 청크에서 또 나오면(겹침) 긴 글을 남기고 청크 ID를 모두 모음.
    인자: schemas는 {문서 유형: {"schema", "unit_rule", "header", "signature"}}.
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
            # 빈칸 1: 단위 ID = 문서 ID + "#" + 조항 번호. 예) D1_27223010abe31291#제16조의2
            unit_id = chunk["doc_id"] + "#" + piece["key"]

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
                # 빈칸 2: 겹친 조항. 두 청크에 걸친 조항은 더 긴 글을 남기고(길이가 같으면 먼저 나온 글), 청크 ID를 모두 모음
                if len(piece["text"]) > len(old["text"]):
                    old["text"] = piece["text"]
                old["chunk_ids"] = old["chunk_ids"] + [chunk["chunk_id"]]

    for unit in units.values():
        unit["text_hash"] = sha256_text(unit["text"])  # K2 재사용 판정(같은 본문은 다시 묻지 않음)에 씀
    return list(units.values()), empty_chunks


# ---------------------------------------------------------------------------
# K2 추출, K3 가지치기 (교재 35, 36쪽) — 빈칸 2곳
# ---------------------------------------------------------------------------
def extract_one(unit: dict, spec: dict, llm, retries: int) -> dict:
    """추출 단위 하나를 LLM에 넣어 노드와 관계를 뽑고(K2), 스키마 밖은 바로 지움(K3).

    목적: 단위마다 「머리줄 + 본문」과 문서 유형의 그래프 스키마를 추출기에 주어 스키마 모양대로 JSON 그래프를 받음.
    방법: neo4j-graphrag의 LLMEntityRelationExtractor(추출 프롬프트는 라이브러리 것 그대로)와 GraphPruning을 씀.
          형식 오류는 같은 입력으로 retries번까지 다시 묻고, 그래도 실패하면 오류를 기록해 돌려줌(나머지 단위는 계속 진행).
          라이브러리가 비동기(async)라 asyncio.run으로 한 번씩 돌림(스레드마다 자기 이벤트 루프를 씀).
    인자: spec은 schemas[문서 유형]. llm은 main이 만든 LLMInterface(Groq). retries는 다시 묻는 횟수.
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
            # 빈칸 1: 추출기 호출. uid에 단위 ID를 주면 라이브러리가 노드 ID 앞에 붙여 단위끼리 ID가 겹치지 않음
            text_chunk = TextChunk(text=text, index=0, uid=unit["unit_id"])
            graph = asyncio.run(extractor.run(chunks=TextChunks(chunks=[text_chunk]), schema=spec["schema"]))
            break
        except Exception as error:  # LLM 형식 오류, 호출 실패 등. 같은 입력으로 다시 물음
            last_error = f"{type(error).__name__}: {str(error)[:200]}"
            print(f"      [K2 시도 {attempt + 1}/{retries + 1} 실패] {unit['unit_id']}: {last_error[:80]}")
    if graph is None:
        return {"error": last_error}

    # 빈칸 2: 가지치기(K3). 추출 직후 바로 스키마 밖 노드, 관계, 속성을 지움
    pruned = asyncio.run(pruner.run(graph, spec["schema"])).graph

    return {"graph": pruned.model_dump(), "raw_nodes": len(graph.nodes), "kept_nodes": len(pruned.nodes)}


# ---------------------------------------------------------------------------
# K4 적재: 그래프 행 만들기 (교재 37, 38쪽) — 빈칸 2곳
# ---------------------------------------------------------------------------
def build_graph_rows(chunks: list[dict], units: list[dict], schemas: dict, generation: str,
                     run_id: str) -> tuple[list, list, set]:
    """Neo4j에 한 번에 쓸 노드 목록, 관계 목록, K5에서 합칠 값을 만듦.

    목적: 검색용 청크마다 청크 노드를 하나 만들고(검색엔진과 chunk_id가 같음), 엔티티를 자기가 나온 청크에 FROM_CHUNK로 이음.
    방법: ① 청크 노드(라벨 Chunk)를 청크마다 만듦 ② 추출 성공 단위의 노드마다 세대와 실행 표시를 붙이고
          그 단위가 나온 청크마다 FROM_CHUNK 관계를 만듦(겹친 조항이면 청크 2개) ③ 스키마 고유 속성(UNIQUENESS)의
          라벨과 같은 노드면 (라벨, 속성, 값)을 모아 K5에 넘김 ④ LLM이 뽑은 관계를 그대로 더함.
    인자: chunks는 ② 결과, units는 K1 ~ K3 결과(graph가 있는 단위만 씀).
    반환값: (노드 목록, 관계 목록, 병합 키 집합). 노드와 관계는 neo4j-graphrag의 Neo4jNode, Neo4jRelationship.
    """
    nodes = []
    relationships = []
    merge_keys: set[tuple[str, str, str]] = set()

    def chunk_node_id(chunk_id: str) -> str:
        """청크 노드의 임시 ID. 이 실행 안에서 관계 양 끝을 찾는 데만 쓰고 저장 뒤에는 라이브러리가 지움."""
        return f"{generation}|{chunk_id}|{run_id}"

    # 빈칸 1: 청크 노드. 검색용 청크마다 하나. chunk_id가 검색엔진 문서의 chunk_id와 같아야 검색 결과에서 그래프로 건너감
    for chunk in chunks:
        nodes.append(Neo4jNode(id=chunk_node_id(chunk["chunk_id"]), label="Chunk", properties={
            "generation": generation,
            "run_id": run_id,
            "chunk_id": chunk["chunk_id"],
            "doc_id": chunk["doc_id"],
            "doc_type": chunk["doc_type"],
            "text": chunk["text"],
        }))

    for unit in units:
        if "graph" not in unit:  # 추출에 실패한 단위는 건너뜀(청크 노드는 위에서 이미 만들었음)
            continue
        graph = Neo4jGraph.model_validate(unit["graph"])  # dict로 보관한 그래프를 라이브러리 객체로 되돌림
        constraints = schemas[unit["doc_type"]]["schema"].constraints  # 이 문서 유형의 고유 속성 제약
        for node in graph.nodes:
            # 모든 엔티티에 세대와 실행 표시. 세대끼리 섞이지 않게 함(교재 37쪽 ②)
            node.properties = {**(node.properties or {}), "generation": generation, "run_id": run_id}
            nodes.append(node)

            # 빈칸 2: FROM_CHUNK. 엔티티 → 이 단위가 나온 청크 노드. 겹친 조항은 청크 2개에 모두 이음
            for chunk_id in dict.fromkeys(unit["chunk_ids"]):  # dict.fromkeys는 순서를 지키며 중복을 없앰
                relationships.append(Neo4jRelationship(
                    type="FROM_CHUNK", start_node_id=node.id, end_node_id=chunk_node_id(chunk_id)))

            # K5에서 합칠 값 모으기: 제약의 라벨과 노드 라벨이 같고 값이 있을 때만(교재 39쪽 ③)
            for constraint in constraints:
                value = node.properties.get(constraint.property_name)
                if constraint.node_type == node.label and value not in (None, ""):
                    merge_keys.add((node.label, constraint.property_name, str(value)))

        relationships.extend(graph.relationships)  # LLM이 뽑은 관계(HAS_CLAUSE 등)를 그대로 더함
    return nodes, relationships, merge_keys


# ---------------------------------------------------------------------------
# K5 병합 (교재 39 ~ 41쪽) — 빈칸 2곳
# ---------------------------------------------------------------------------
def k5_merge(driver, generation: str, merge_keys: set) -> int:
    """같은 세대에서 스키마 고유 속성 값이 같은 노드를 하나로 합침.

    목적: 여러 추출 단위에 흩어진 같은 대상(예: 상품 안내 노드 ProductGuide D2-C021이 청크 4개에서 각각 뽑힘)을 한 노드로 모음.
    방법: (라벨, 속성, 값)마다 같은 세대에서 값이 같은 노드를 모아 2개 이상이면 APOC mergeNodes로 합침.
          속성이 다르면 목록 첫 노드 값을 남기고(discard), 관계는 모두 합친 노드로 옮김(mergeRels).
    인자: merge_keys는 K4가 모은 {(라벨, 속성 이름, 값)}. 이번에 들어온 값만 검사함(교재 40쪽 ①).
    반환값: 합쳐진 묶음 수.
    """
    groups = 0
    keys = sorted(merge_keys)  # 순서를 고정해 실행마다 같은 순서로 합침
    for number, (label, prop, value) in enumerate(keys, start=1):
        # 빈칸 1: 같은 세대에서 라벨과 속성 값이 같은 노드를 모음. 2개 이상일 때만 다음으로 넘김
        # 빈칸 2: apoc.refactor.mergeNodes로 하나로 합침(속성은 첫 노드 것, 관계는 모두 옮김)
        records, _, _ = driver.execute_query(
            f"MATCH (n:`{label}` {{generation: $g}}) WHERE toString(n.`{prop}`) = $v "
            "WITH collect(n) AS ns WHERE size(ns) > 1 "
            "CALL apoc.refactor.mergeNodes(ns, {properties: 'discard', mergeRels: true}) YIELD node "
            "RETURN count(node) AS merged",
            g=generation, v=value)
        for record in records:
            groups += record["merged"]
        if number % 50 == 0:  # 값이 많을 때 멈춘 것처럼 보이지 않게 진행을 알림
            print(f"      [K5] {number}/{len(keys)}개 값 검사, 지금까지 {groups}묶음 합침")
    return groups


# ---------------------------------------------------------------------------
# K6 엔티티 설명 임베딩 (교재 42 ~ 44쪽)
# ---------------------------------------------------------------------------
def entity_description(label: str, props: dict) -> str:
    """엔티티 하나를 「라벨: 속성=값, 속성=값」 설명 글로 바꿈. — 직접 작성

    목적: 이 글을 임베딩해 질문과 뜻이 가까운 엔티티를 바로 찾게 함(엔티티 직접 검색, 교재 42쪽).
    방법: 관리용 속성(generation, run_id, embedding)은 빼고, 속성 이름순으로 "이름=값"을 쉼표로 이음.
    예시: ("Proposal", {"content": "주문 내역 화면 대조", "decision": "수용", "generation": "gen-..."})
          → "Proposal: content=주문 내역 화면 대조, decision=수용"
    """
    parts = []
    for name in sorted(props):  # 속성 이름순. 같은 엔티티면 늘 같은 글이 나오게 함
        if name in SYSTEM_PROPS:  # 관리용 속성은 뜻이 없어 뺌
            continue
        parts.append(f"{name}={props[name]}")
    return f"{label}: " + ", ".join(parts)


def k6_embed_descriptions(driver, generation: str, embed_texts, dimension: int, index_name: str) -> int:
    """임베딩이 없는 엔티티의 설명 글을 임베딩해 저장하고 벡터 인덱스를 만듦. — 빈칸 2곳

    목적: K5 병합 뒤 남은 엔티티만 임베딩하고(합쳐져 사라질 노드는 임베딩하지 않음), 벡터 검색이 가능하게 인덱스를 둠.
    방법: 이 세대의 __Entity__ 중 embedding이 비어 있는 노드를 읽어 설명 글을 만들고, main의 embed_texts(96건씩 나눠 부름)로
          벡터를 받아 setNodeVectorProperty로 저장함. 인덱스는 없을 때만 만듦(차원과 코사인 지정).
    인자: embed_texts는 글 목록을 받아 벡터 목록을 돌려주는 함수(main 제공). dimension은 임베딩 차원.
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

    # 빈칸 1: 벡터 저장. elementId로 노드를 찾아 embedding 속성에 벡터를 넣음(db.create.setNodeVectorProperty)
    save_rows = []
    for row, vector in zip(rows, vectors):
        save_rows.append({"id": row["id"], "vec": vector})
    driver.execute_query(
        "UNWIND $rows AS row MATCH (n) WHERE elementId(n) = row.id "
        "CALL db.create.setNodeVectorProperty(n, 'embedding', row.vec)", rows=save_rows)

    # 빈칸 2: 벡터 인덱스. __Entity__ 라벨의 embedding 속성, 차원과 코사인 유사도를 적음. 있으면 그대로 둠
    driver.execute_query(
        f"CREATE VECTOR INDEX {index_name} IF NOT EXISTS FOR (n:__Entity__) ON n.embedding "
        "OPTIONS {indexConfig: {`vector.dimensions`: $d, `vector.similarity_function`: 'cosine'}}", d=dimension)
    return len(rows)


# ---------------------------------------------------------------------------
# K8 커뮤니티 요약 (교재 46 ~ 49쪽)
# ---------------------------------------------------------------------------
def group_assignments(assignments: dict[int, int]) -> list[list[int]]:
    """제공 함수. 「엔티티 번호 → 묶음 번호」를 묶음 목록으로 바꿈. 묶음 안은 번호순, 묶음끼리는 가장 작은 번호순.

    GDS가 매기는 묶음 번호 자체는 뜻이 없어서, 구성원으로만 순서를 정해 같은 묶음이면 같은 출력이 나오게 함.
    """
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
    """GDS Leiden으로 엔티티를 묶음(커뮤니티)으로 나눔. — 빈칸 2곳

    목적: 서로 촘촘히 이어진 엔티티를 묶어, 묶음마다 보고서를 써 두면 거시 질문에 답할 재료가 됨(교재 46쪽).
    방법: ① 엔티티와 엔티티 사이 줄만 GDS 메모리에 투영함(무방향. 청크 노드는 넣지 않음) ② Leiden을 씨앗 고정, 병렬 1로
          한 번 불러 묶음 번호를 받음 ③ finally로 투영 그래프를 반드시 지움 ④ 묶음 번호를 구성원 목록으로 바꿈.
    인자: entity_ids는 엔티티 키순으로 정렬된 elementId 목록(같은 순서로 넣어야 같은 결과). edges는 (번호, 번호) 무방향 줄.
    반환값: [[엔티티 번호, ...], ...] 묶음 목록(group_assignments와 같은 꼴).
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
        # 빈칸 1: 투영. gds.graph.project로 엔티티와 줄을 메모리에 복사함. 모든 관계를 무방향으로 봄
        driver.execute_query(
            "UNWIND $rows AS row MATCH (s) WHERE elementId(s) = $ids[row.s] "
            "OPTIONAL MATCH (t) WHERE row.t IS NOT NULL AND elementId(t) = $ids[row.t] "
            "WITH gds.graph.project($name, s, t, {}, {undirectedRelationshipTypes: ['*']}) AS g "
            "RETURN g.nodeCount AS n", rows=rows, ids=entity_ids, name=graph_name)
        # 빈칸 2: Leiden. 씨앗(randomSeed)과 병렬 1(concurrency)을 함께 둬야 같은 그래프에서 같은 묶음이 나옴
        records, _, _ = driver.execute_query(
            "CALL gds.leiden.stream($name, {randomSeed: $seed, concurrency: 1}) YIELD nodeId, communityId "
            "RETURN elementId(gds.util.asNode(nodeId)) AS id, communityId AS c", name=graph_name, seed=seed)
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


def build_community_rows(groups: list[list[int]], group_hashes: list[str], entities: list[dict],
                         reports: dict, min_size: int) -> list[dict]:
    """보고서가 있는 묶음을 Neo4j에 쓸 행으로 만듦. — 빈칸 2곳

    목적: 엔티티 min_size개 이상인 묶음만 Community 노드가 되고, 구성원 엔티티는 IN_COMMUNITY로 이어짐(교재 49쪽 ①, ⑤).
    방법: 묶음마다 ① 크기가 작으면 건너뜀 ② 지문(group_hashes)으로 보고서를 찾음 ③ 구성원 번호를 엔티티 elementId로 바꿈.
    인자: reports는 {묶음 지문: {"title", "summary", "findings", "embedding"}}(main이 LLM과 임베딩으로 채움).
    반환값: [{"community_id", "title", "summary", "findings", "member_hash", "size", "vec", "members"}, ...].
    """
    rows = []
    for members, member_hash in zip(groups, group_hashes):
        # 빈칸 1: 엔티티가 min_size개보다 적은 묶음은 보고서를 쓰지 않음(한두 개짜리는 엔티티 설명으로 충분함)
        if len(members) < min_size:
            continue
        report = reports[member_hash]

        # 빈칸 2: 묶음 안 번호(0, 1, 2, ...)를 엔티티의 elementId로 바꿈. IN_COMMUNITY의 시작 노드가 됨
        member_ids = []
        for number in members:
            member_ids.append(entities[number]["id"])

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
    """제공 함수. 이 세대의 옛 Community를 지우고 새 Community 노드와 IN_COMMUNITY 관계를 쓰고 벡터 인덱스를 만듦.

    묶음 경계가 조금만 바뀌어도 일부만 고치기 어려워 매번 그 세대의 Community를 모두 다시 씀(엔티티는 그대로 둠).
    Community에는 __Entity__ 라벨을 붙이지 않아 K6 벡터 인덱스와 섞이지 않음.
    """
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
# S1 임베딩: 벡터 재사용 (교재 54, 55쪽) — 직접 작성
# ---------------------------------------------------------------------------
def embed_with_reuse(texts: list[str], hashes: list[str], old_vectors: dict[str, list[float]],
                     embed_texts) -> tuple[list[list[float]], int]:
    """본문 해시가 활성 세대에 있으면 그 벡터를 다시 쓰고, 없는 본문만 새로 임베딩함.

    목적: 모델과 설정이 같고 본문도 같으면 벡터가 같으므로 API 호출을 줄임(교재 55쪽 「같은 정제 본문이 있나요?」).
    방법: ① 해시가 old_vectors에 없는 글만 골라 ② 한 번에 embed_texts로 임베딩하고 ③ 원래 순서대로 재사용 벡터와 합침.
    인자: texts와 hashes는 같은 길이(i번째 글의 해시가 hashes[i]). old_vectors는 {본문 해시: 벡터}(없으면 빈 dict).
    반환값: (청크 순서대로의 벡터 목록, 새로 임베딩한 수).
    """
    # ① 새로 임베딩할 글 고르기: 해시가 옛 벡터에 없는 것만
    todo_positions = []
    todo_texts = []
    for position, text_hash in enumerate(hashes):
        if text_hash not in old_vectors:
            todo_positions.append(position)
            todo_texts.append(texts[position])

    # ② 새 글만 한 번에 임베딩(96건씩 나누는 일은 embed_texts가 함). 없으면 API를 부르지 않음
    if todo_texts:
        new_vectors = embed_texts(todo_texts)
    else:
        new_vectors = []
    fresh = {}  # 위치 → 새 벡터
    for position, vector in zip(todo_positions, new_vectors):
        fresh[position] = vector

    # ③ 원래 순서대로 합치기: 새로 만든 것은 fresh에서, 나머지는 옛 벡터에서
    vectors = []
    for position, text_hash in enumerate(hashes):
        if position in fresh:
            vectors.append(fresh[position])
        else:
            vectors.append(old_vectors[text_hash])
    return vectors, len(todo_texts)


# ---------------------------------------------------------------------------
# S2 키워드 분석: 엔진 문서 한 건 만들기 (교재 53, 56 ~ 58쪽) — 빈칸 2곳
# ---------------------------------------------------------------------------
def build_search_docs(chunks: list[dict], hashes: list[str], vectors: list[list[float]], lexicon,
                      meta_fields: tuple) -> list[dict]:
    """청크마다 검색엔진에 넣을 문서 한 건(벡터 + 낱말 + 메타데이터)을 만듦.

    목적: 검색엔진 인덱스 하나가 벡터 검색과 키워드 검색을 모두 맡도록 한 건에 두 가지를 함께 담음(교재 53쪽).
    방법: 색인용 본문을 Kiwi 토크나이저(카드명 사전과 별칭 포함)로 낱말로 잘라 공백으로 이어 text_tokens에 넣고,
          임베딩 벡터는 embedding에, 필터용 메타데이터는 문자열로 넣음.
    인자: lexicon은 kr_tokenizer.Lexicon(tokenize(글) → 낱말 목록). meta_fields는 검색엔진 필드로 남길 메타데이터 키.
    반환값: [{"chunk_id", "doc_id", "text_hash", "text", "text_tokens", "embedding", 메타데이터...}, ...].
    """
    docs = []
    for chunk, text_hash, vector in zip(chunks, hashes, vectors):
        # 빈칸 1: 키워드 분석. 색인 때와 검색 때 같은 토크나이저를 써야 하므로 lexicon.tokenize 하나만 씀
        tokens = lexicon.tokenize(chunk["text"])

        # 빈칸 2: 엔진 문서 한 건. text_tokens는 낱말을 공백으로 이어 whitespace 분석기가 그대로 자르게 함
        doc = {
            "chunk_id": chunk["chunk_id"],
            "doc_id": chunk["doc_id"],
            "text_hash": text_hash,
            "text": chunk["text"],
            "text_tokens": " ".join(tokens),
            "embedding": vector,
        }
        for field in meta_fields:  # 값이 있는 메타데이터만 문자열로 넣음(필터와 출처 표시에 씀)
            value = chunk["metadata"].get(field)
            if value is not None and value != "":
                doc[field] = str(value)
        docs.append(doc)
    return docs


# ---------------------------------------------------------------------------
# S3 적재: 검색엔진에 쓰기 (교재 58, 59쪽) — 빈칸 3곳
# ---------------------------------------------------------------------------
def apply_search(os_client, index: str, docs: list[dict], mapping: dict) -> dict:
    """문서(doc_id)마다 옛 청크를 지우고 새 청크를 한꺼번에 넣은 뒤 바로 검색되게 함.

    목적: 고친 문서의 옛 청크가 남지 않게 청크 단위가 아니라 문서 단위로 바꿈(교재 58쪽 그림).
    방법: ① 인덱스가 없으면 매핑으로 만듦 ② 넣을 문서의 doc_id를 모음 ③ doc_id마다 delete_by_query로 옛 청크를 지움
          ④ bulk로 한꺼번에 넣음(_id = chunk_id라 같은 입력을 두 번 넣어도 건수가 그대로) ⑤ refresh로 바로 보이게 함.
    반환값: {"deleted": 지운 수, "indexed": 넣은 수, "documents": 문서 수}.
    """
    if not os_client.indices.exists(index=index):  # ① 이번 세대 인덱스가 없으면 만듦(벡터 필드와 낱말 필드가 이때 정해짐)
        os_client.indices.create(index=index, body=mapping)

    doc_ids = set()  # ② 지울 문서 고르기
    for doc in docs:
        doc_ids.add(doc["doc_id"])

    deleted = 0
    for doc_id in sorted(doc_ids):
        # 빈칸 1: 옛 청크 지우기. term doc_id로 그 문서의 청크를 모두 지움. refresh=True라 바로 반영되고,
        #         conflicts="proceed"는 충돌이 나도 멈추지 않음
        result = os_client.delete_by_query(index=index, body={"query": {"term": {"doc_id": doc_id}}},
                                           refresh=True, conflicts="proceed")
        deleted += int(result.get("deleted", 0))

    # 빈칸 2: 한꺼번에 넣기. _id를 chunk_id로 고정함. 일부가 실패하면 BulkIndexError가 남
    actions = []
    for doc in docs:
        actions.append({"_index": index, "_id": doc["chunk_id"], "_source": doc})
    helpers.bulk(os_client, actions, max_retries=3)

    # 빈칸 3: 반영. refresh로 넣은 청크가 다음 검색부터 보임
    os_client.indices.refresh(index=index)

    return {"deleted": deleted, "indexed": len(docs), "documents": len(doc_ids)}


# ---------------------------------------------------------------------------
# ④ 검증: chunk_id 목록 비교 (교재 60, 61쪽) — 직접 작성
# ---------------------------------------------------------------------------
def verify_chunk_ids(all_ids: set[str], search_ids: set[str], kg_list: list[str]) -> dict:
    """입력 청크, 검색엔진, 그래프 청크 노드의 chunk_id가 모두 같은지 검사함.

    목적: 세 곳이 어긋나면 검색 결과의 chunk_id가 그래프에 없어 건너가지 못하므로, 다 맞을 때만 ⑤ 게시로 넘어감.
    방법: 검사 1 검색엔진 = 입력(집합 비교), 검사 2 그래프 = 입력(집합 비교), 검사 3 청크 하나에 노드 하나
          (목록 그대로 세어 두 번 이상 나온 chunk_id를 찾음. 집합으로 바꾸면 사라져 못 잡음).
    인자: all_ids는 이번에 색인하려던 청크 ID 집합, search_ids는 검색엔진에서 읽은 집합, kg_list는 그래프 청크 노드의
          chunk_id 목록(중복을 지우지 않은 그대로).
    반환값: {"ok", "search_equal", "kg_equal", "search_missing", "search_extra", "kg_missing", "kg_extra",
            "kg_duplicate_chunk_nodes"}. 목록 값은 정렬된 list.
    """
    kg_ids = set(kg_list)  # 비교용 집합은 따로 만듦(원래 목록은 중복 검사에 씀)

    # 검사 1, 2: 집합이 같은지 보고, 차집합으로 빠진 것과 남는 것을 적음
    report = {
        "search_equal": search_ids == all_ids,
        "kg_equal": kg_ids == all_ids,
        "search_missing": sorted(all_ids - search_ids),  # 입력에는 있는데 검색엔진에 없음
        "search_extra": sorted(search_ids - all_ids),  # 검색엔진에만 있음
        "kg_missing": sorted(all_ids - kg_ids),
        "kg_extra": sorted(kg_ids - all_ids),
    }

    # 검사 3: 목록에서 두 번 이상 나온 chunk_id
    seen_count: dict[str, int] = {}
    for chunk_id in kg_list:
        seen_count[chunk_id] = seen_count.get(chunk_id, 0) + 1
    duplicates = []
    for chunk_id, count in seen_count.items():
        if count > 1:
            duplicates.append(chunk_id)
    report["kg_duplicate_chunk_nodes"] = sorted(duplicates)

    # 통과 조건: 셋 다 맞아야 함
    report["ok"] = report["search_equal"] and report["kg_equal"] and len(duplicates) == 0
    return report


# ---------------------------------------------------------------------------
# ⑤ 게시: 활성 세대 파일 교체 (교재 30, 62쪽) — 직접 작성
# ---------------------------------------------------------------------------
def publish_active(record: dict, active_file: Path) -> None:
    """활성 세대 파일 하나만 새 세대 기록으로 바꿔 끼움.

    목적: 검색기는 요청마다 이 파일을 한 번 읽어 같은 세대로 두 저장소를 조회함. 파일 하나만 바꾸면 전환이 끝남.
    방법: 임시 파일에 다 쓴 뒤 os.replace로 이름을 바꿈. 쓰다가 멈춰도 반쯤 쓴 파일이 활성 세대로 보이지 않음.
    인자: record는 세대 ID, 검색엔진 인덱스 이름, 청크 수, 입력 지문, 설정 지문, 게시 시각을 담은 dict.
    부수효과: active_file을 덮어씀(폴더가 없으면 만듦).
    """
    active_file = Path(active_file)
    active_file.parent.mkdir(parents=True, exist_ok=True)
    temp_file = active_file.with_suffix(active_file.suffix + ".tmp")  # 같은 폴더의 임시 파일
    temp_file.write_text(json.dumps(record, ensure_ascii=False, indent=1), encoding="utf-8")  # 먼저 다 씀
    os.replace(temp_file, active_file)  # 그다음 한 번에 바꿔 끼움
