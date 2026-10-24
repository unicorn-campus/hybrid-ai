"""KG 구축 서브 워크플로우.

준비 prepare(): K1 추출 단위 나누기 → K2 추출(LLM) → K3 가지치기. 결과는 파일로 보관만 하고 Neo4j에는 쓰지 않음
반영 apply():   K4 적재(Neo4j에 새 청크 넣기) → K5 병합(관련 엔티티만) → K6 노드 설명 임베딩
정리 cleanup(): K7 청크 정리(옛 청크 노드와 고아 엔티티 지우기)

추출 단위(약관 조항)는 LLM에 넣을 글을 정하는 데만 씀. 그래프의 Chunk 노드는 검색엔진 청크와 1대1이고
노드의 chunk_id가 검색엔진 chunk_id와 같음. 검색 결과에서 그래프로 들어갈 때 ID 일치 하나로 찾게 하려는 것임.

활성 세대 파일은 바꾸지 않음(게시는 오케스트레이터가 함).
"""

from __future__ import annotations

import asyncio
import re

from neo4j_graphrag.components.entity_relation_extractor import LLMEntityRelationExtractor, OnError
from neo4j_graphrag.components.graph_pruning import GraphPruning
from neo4j_graphrag.components.kg_writer import Neo4jWriter
from neo4j_graphrag.components.schema import GraphSchema
from neo4j_graphrag.components.types import Neo4jGraph, Neo4jNode, Neo4jRelationship, TextChunk, TextChunks

import config
from common import doc_id_of, embed, load_json, log, make_llm, sha256_file, sha256_text

SYSTEM_PROPS = {"generation", "run_id", "embedding"}  # 엔티티 설명을 만들 때 빼는 관리용 속성


# ---------------------------------------------------------------- 스키마 읽기

def load_schemas() -> dict[str, dict]:
    """문서 유형마다 승인 기록이 있는 graph_schema.json, 추출 단위 규칙, 머리줄 칸을 읽음."""

    out = {}
    for doc_type in config.DOC_TYPES:
        folder = config.SCHEMA_DIR / doc_type
        path = folder / "graph_schema.json"
        if not path.exists():
            continue
        approval = load_json(folder / "approval.json")
        out[doc_type] = {
            "schema": GraphSchema.from_file(str(path)),
            "unit_rule": approval.get("extraction_unit_rule"),  # 없으면 청크를 그대로 추출 단위로 씀
            "header": load_json(folder / "schema_spec.json").get("metadata_header", []),
            "signature": sha256_file(path),  # 스키마가 바뀌면 보관한 추출 결과를 다시 쓰지 않음
            "below_criteria": approval.get("below_criteria"),
        }
    return out


# ---------------------------------------------------------------- K1 추출 단위 나누기

def _split_by_heading(chunk: dict, rule: dict) -> list[dict]:
    """제목 줄(예: 「제16조(할부 거래)」) 다음 줄이 ①로 시작할 때만 단위를 시작함. 차례 줄은 단위가 되지 않음."""

    heading = re.compile(rule["heading"])
    drop = re.compile(rule["drop_lines"]) if rule.get("drop_lines") else None
    lines = chunk["text"].split("\n")
    nxt = lambda i: next((l.strip() for l in lines[i + 1:] if l.strip()), "")
    starts = [i for i, l in enumerate(lines)
              if heading.match(l.strip()) and nxt(i).startswith(rule["body_start"])]
    units = []
    for k, i in enumerate(starts):
        end = starts[k + 1] if k + 1 < len(starts) else len(lines)
        body = [l for l in lines[i:end] if not (drop and drop.match(l.strip()))]
        no = heading.match(lines[i].strip()).group(1)
        units.append({"text": "\n".join(body).strip(), "key": no, "section_label": lines[i].strip()})
    return units


def k1_split_units(chunks: list[dict], schemas: dict) -> tuple[list[dict], list[str]]:
    """청크를 추출 단위로 나눔. 규칙이 있는 문서 유형(약관)만 나누고 나머지는 청크 하나가 단위 하나.

    반환: (추출 단위 목록, 단위가 하나도 안 나온 청크 ID 목록). 단위의 chunk_ids는 이 단위가 나온 검색용 청크 ID.
    chunk_ids는 준비 결과 파일에만 두는 기록임. K4가 이 목록으로 엔티티를 청크 노드에 잇고, 그래프에는 쓰지 않음.
    """

    units: dict[str, dict] = {}
    empty: list[str] = []
    for c in chunks:
        doc_type = c["metadata"].get("doc_type")
        if doc_type not in schemas:
            continue
        base = {"doc_type": doc_type, "doc_id": doc_id_of(c["chunk_id"]), "metadata": dict(c["metadata"])}
        rule = schemas[doc_type]["unit_rule"]
        if not rule:
            units[c["chunk_id"]] = {**base, "unit_id": c["chunk_id"], "text": c["text"],
                                    "chunk_ids": [c["chunk_id"]]}
            continue
        parts = _split_by_heading(c, rule)
        if not parts:
            empty.append(c["chunk_id"])
        for p in parts:
            uid = f"{base['doc_id']}#{p['key']}"  # 예) D1_27223010abe31291#제16조의2
            md = {**base["metadata"], "section_label": p["section_label"]}
            old = units.get(uid)
            if old is None:
                units[uid] = {**base, "metadata": md, "unit_id": uid, "text": p["text"],
                              "chunk_ids": [c["chunk_id"]]}
            elif c["chunk_id"] not in old["chunk_ids"]:  # 겹침으로 같은 조항이 또 나오면 긴 글을 남기고 청크 ID는 모두 모음
                keep = max(old["text"], p["text"], key=len)  # 길이가 같으면 먼저 나온 글을 남김
                old.update(text=keep, chunk_ids=old["chunk_ids"] + [c["chunk_id"]])
    for u in units.values():
        u["text_hash"] = sha256_text(u["text"])
    return list(units.values()), empty


# ---------------------------------------------------------------- K2 추출, K3 가지치기

def _head_line(md: dict, fields: list[str]) -> str:
    """메타데이터를 한 줄로 단위 앞에 붙임. 상담 번호나 날짜 같은 키 속성이 채워지게 함."""

    return " | ".join(f"{f}: {md[f]}" for f in fields if md.get(f) not in (None, "")) + "\n"


async def _k2_k3_one(sem, extractor, pruner, unit: dict, spec: dict) -> dict:
    async with sem:
        text = _head_line(unit["metadata"], spec["header"]) + unit["text"]
        for attempt in range(config.LLM_RETRIES + 1):
            try:
                # K2: uid에 단위 ID를 주면 라이브러리가 노드 ID 앞에 붙여 단위끼리 ID가 겹치지 않음
                graph = await extractor.run(chunks=TextChunks(chunks=[TextChunk(text=text, index=0,
                                                                               uid=unit["unit_id"])]),
                                            schema=spec["schema"])
                break
            except Exception as e:  # 형식 오류는 같은 입력으로 다시 물음
                if attempt == config.LLM_RETRIES:
                    return {"error": f"{type(e).__name__}: {str(e)[:200]}"}
        pruned = (await pruner.run(graph, spec["schema"])).graph  # K3: 스키마 밖 노드와 관계를 지움
        return {"graph": pruned.model_dump(), "raw_nodes": len(graph.nodes), "kept_nodes": len(pruned.nodes)}


def prepare(chunks: list[dict], previous: dict | None = None) -> dict:
    """K1 ~ K3. 아무 데도 쓰지 않고 추출 결과만 만들어 돌려줌(오케스트레이터가 파일로 보관).

    previous: 앞 세대의 준비 결과. 본문 해시와 스키마가 같은 단위는 LLM을 다시 부르지 않고 그 결과를 씀.
    """

    schemas = load_schemas()
    units, empty = k1_split_units(chunks, schemas)
    log(f"[KG K1] 청크 {len(chunks)}개 → 추출 단위 {len(units)}개 (단위가 없는 청크 {len(empty)}개)")
    cache = {}
    for u in (previous or {}).get("units", []):
        if "graph" in u:
            cache[(u["doc_type"], u["text_hash"], u["schema_signature"])] = u
    todo = []
    for u in units:
        u["schema_signature"] = schemas[u["doc_type"]]["signature"]
        hit = cache.get((u["doc_type"], u["text_hash"], u["schema_signature"]))
        if hit:
            u.update(graph=hit["graph"], reused=True)
        else:
            todo.append(u)
    log(f"[KG K2] LLM 추출 {len(todo)}개, 앞 세대 결과 재사용 {len(units) - len(todo)}개")

    async def run_all():
        llm = make_llm()
        extractor = LLMEntityRelationExtractor(llm=llm, create_lexical_graph=False, on_error=OnError.RAISE)
        pruner, sem = GraphPruning(), asyncio.Semaphore(config.LLM_CONCURRENCY)
        results = await asyncio.gather(*[_k2_k3_one(sem, extractor, pruner, u, schemas[u["doc_type"]])
                                         for u in todo])
        return results, dict(llm.usage)

    results, usage = asyncio.run(run_all()) if todo else ([], {})
    for u, r in zip(todo, results):
        u.update(r)
    failed = [u["unit_id"] for u in units if "error" in u]
    log(f"[KG K3] 가지치기 뒤 노드 {sum(len(u.get('graph', {}).get('nodes', [])) for u in units)}개, "
        f"추출 실패 단위 {len(failed)}개, 토큰 {usage.get('total_tokens', 0)}")
    # 청크 노드는 단위가 없거나 추출에 실패한 청크도 만듦. 검색엔진과 청크 집합이 늘 같아야 ④가 같음 비교 하나로 끝남
    chunk_rows = [{"chunk_id": c["chunk_id"], "doc_id": doc_id_of(c["chunk_id"]),
                   "doc_type": c["metadata"].get("doc_type"), "text": c["text"]} for c in chunks]
    return {"chunks": chunk_rows, "units": units, "no_unit_chunks": empty, "failed_units": failed,
            "llm_usage": usage}


# ---------------------------------------------------------------- K4 적재, K5 병합, K6 노드 설명 임베딩

def apply(driver, prepared: dict, generation: str, run_id: str) -> dict:
    """K4 ~ K6. 준비 결과를 Neo4j의 해당 세대에 씀. 모든 노드에 generation을 붙여 세대끼리 섞이지 않게 함."""

    nodes, rels, merge_keys = [], [], set()
    schemas = load_schemas()
    # 청크 노드(라벨 Chunk): 검색엔진 청크 하나에 하나. 임시 ID는 이 실행 안에서 관계 양 끝을 찾는 데만 씀
    chunk_node = lambda cid: f"{generation}|{cid}|{run_id}"
    for c in prepared["chunks"]:
        nodes.append(Neo4jNode(id=chunk_node(c["chunk_id"]), label="Chunk", properties={
            "generation": generation, "run_id": run_id, "chunk_id": c["chunk_id"], "doc_id": c["doc_id"],
            "doc_type": c["doc_type"], "text": c["text"]}))
    for u in prepared["units"]:
        if "graph" not in u:
            continue
        graph = Neo4jGraph.model_validate(u["graph"])
        for n in graph.nodes:
            n.properties = {**(n.properties or {}), "generation": generation, "run_id": run_id}
            nodes.append(n)
            # 겹친 조항은 두 청크에 모두 이음. 어느 청크로 검색돼도 그 조항의 엔티티가 후보가 되게 하려는 것임
            for cid in dict.fromkeys(u["chunk_ids"]):
                rels.append(Neo4jRelationship(type="FROM_CHUNK", start_node_id=n.id, end_node_id=chunk_node(cid)))
            for c in schemas[u["doc_type"]]["schema"].constraints:  # K5에서 합칠 값(이번에 들어온 것만)
                if c.node_type == n.label and n.properties.get(c.property_name) not in (None, ""):
                    merge_keys.add((n.label, c.property_name, str(n.properties[c.property_name])))
        rels.extend(graph.relationships)

    # K4: 노드는 CREATE로 새로 만들고, 단위 ID가 붙은 임시 ID로 관계 양 끝을 찾은 뒤 임시 ID는 지움(라이브러리 동작)
    asyncio.run(Neo4jWriter(driver).run(Neo4jGraph(nodes=nodes, relationships=rels)))
    log(f"[KG K4] 적재: 노드 {len(nodes)}개(청크 노드 {len(prepared['chunks'])}개 포함), 관계 {len(rels)}개")

    merged = k5_merge(driver, generation, merge_keys)
    dedup_from_chunk(driver, generation)
    embedded = k6_embed_descriptions(driver, generation)
    return {"written_nodes": len(nodes), "written_rels": len(rels), "merged_groups": merged, "embedded": embedded}


def k5_merge(driver, generation: str, keys: set[tuple[str, str, str]]) -> int:
    """같은 세대에서 스키마의 고유 속성(UNIQUENESS 제약) 값이 같은 노드를 하나로 합침.

    예) 상담 노드 C-20260302-002가 그 상담 본문 추출과 다음 상담의 앞 상담 참조(FOLLOWS)로 두 번 생기면 하나로 합침.
    이번에 들어온 값만 대상으로 하여 관련 엔티티만 건드림.
    """

    groups = 0
    for label, prop, value in sorted(keys):
        records, _, _ = driver.execute_query(
            f"MATCH (n:`{label}` {{generation: $g}}) WHERE toString(n.`{prop}`) = $v "
            "WITH collect(n) AS ns WHERE size(ns) > 1 "
            "CALL apoc.refactor.mergeNodes(ns, {properties: 'discard', mergeRels: true}) YIELD node "
            "RETURN count(node) AS c", g=generation, v=value)
        groups += sum(r["c"] for r in records)
    log(f"[KG K5] 병합: 같은 고유 속성 값 묶음 {groups}개를 합침 (검사한 값 {len(keys)}개)")
    return groups


def dedup_from_chunk(driver, generation: str) -> int:
    """같은 엔티티와 같은 청크 사이의 FROM_CHUNK를 하나만 남김.

    K5가 한 청크의 여러 조항에서 뽑힌 같은 노드(예: 약관 문서 노드)를 합치면 그 청크로 가는 관계가 여러 개 생길 수 있음.
    표본(2026-10-23)에서는 mergeNodes의 mergeRels가 이미 합쳐 0건이었음. APOC 동작에 기대지 않으려고 둔 안전장치임.
    """

    records, _, _ = driver.execute_query(
        "MATCH (e:__Entity__ {generation: $g})-[r:FROM_CHUNK]->(c:Chunk {generation: $g}) "
        "WITH e, c, collect(r) AS rs WHERE size(rs) > 1 "
        "FOREACH (x IN tail(rs) | DELETE x) RETURN sum(size(rs) - 1) AS n", g=generation)
    removed = records[0]["n"] or 0
    log(f"[KG K5] FROM_CHUNK 중복 {removed}개 지움")
    return removed


def k6_embed_descriptions(driver, generation: str) -> int:
    """임베딩이 없는 엔티티마다 「라벨: 속성=값, …」 설명을 만들어 KURE-v2로 임베딩하고 벡터 인덱스를 만듦."""

    records, _, _ = driver.execute_query(
        "MATCH (n:__Entity__ {generation: $g}) WHERE n.embedding IS NULL "
        "RETURN elementId(n) AS id, [l IN labels(n) WHERE NOT l STARTS WITH '__'][0] AS label, "
        "properties(n) AS props", g=generation)
    rows = [dict(r) for r in records]
    texts = [f"{r['label']}: " + ", ".join(f"{k}={v}" for k, v in sorted(r["props"].items())
                                          if k not in SYSTEM_PROPS) for r in rows]
    vectors = embed(texts)
    driver.execute_query(
        "UNWIND $rows AS row MATCH (n) WHERE elementId(n) = row.id "
        "CALL db.create.setNodeVectorProperty(n, 'embedding', row.vec)",
        rows=[{"id": r["id"], "vec": v} for r, v in zip(rows, vectors)])
    driver.execute_query(
        "CREATE VECTOR INDEX kg_entity_embedding IF NOT EXISTS FOR (n:__Entity__) ON n.embedding "
        "OPTIONS {indexConfig: {`vector.dimensions`: $d, `vector.similarity_function`: 'cosine'}}",
        d=config.EMBED_DIMENSION)
    log(f"[KG K6] 노드 설명 임베딩 {len(rows)}개")
    return len(rows)


# ---------------------------------------------------------------- K7 청크 정리

def cleanup(driver, generation: str, run_id: str, doc_ids: list[str]) -> dict:
    """K7. 바뀌거나 사라진 문서의 옛 청크 노드(이번 실행에서 만들지 않은 것)를 지우고,
    근거 청크를 하나도 잃은 엔티티(고아)를 지움. 증분 색인에서 검색엔진 교체(S3) 뒤에 부름.
    바뀐 문서는 K4에서 청크 노드를 새로 만들었으므로 지우는 동안에도 같은 chunk_id 노드가 그래프에 하나 이상 있음."""

    records, _, _ = driver.execute_query(
        "MATCH (c:Chunk {generation: $g}) WHERE c.doc_id IN $docs AND c.run_id <> $run "
        "DETACH DELETE c RETURN count(*) AS n", g=generation, docs=doc_ids, run=run_id)
    chunks = records[0]["n"]
    records, _, _ = driver.execute_query(
        "MATCH (e:__Entity__ {generation: $g}) WHERE NOT (e)-[:FROM_CHUNK]->(:Chunk) "
        "DETACH DELETE e RETURN count(*) AS n", g=generation)
    orphans = records[0]["n"]
    log(f"[KG K7] 청크 정리: 옛 청크 노드 {chunks}개, 고아 엔티티 {orphans}개 지움")
    return {"deleted_chunk_nodes": chunks, "deleted_orphans": orphans}


def chunk_node_ids(driver, generation: str) -> list[str]:
    """④ 검증용: 이 세대 청크 노드의 chunk_id 전체. 중복을 그대로 돌려줘 청크 하나에 노드가 둘인 경우도 잡게 함."""

    records, _, _ = driver.execute_query(
        "MATCH (c:Chunk {generation: $g}) RETURN collect(c.chunk_id) AS ids", g=generation)
    return list(records[0]["ids"])
