"""K8 커뮤니티 요약(선택 단계). 엔티티 그래프를 묶음(커뮤니티)으로 나누고 묶음마다 요약 보고서를 만듦.

흐름: ① 엔티티 그래프 읽기 → ② Leiden으로 묶기 → ③ 묶음마다 LLM 보고서 → ④ 요약 임베딩 → ⑤ Neo4j에 쓰기
- 묶는 대상은 엔티티와 엔티티 사이 관계뿐임. 청크 노드와 FROM_CHUNK는 넣지 않음.
  넣으면 같은 청크에서 나온 엔티티끼리 묶여 "문서 요약"과 다를 바가 없어지기 때문임
- 보고서는 구성원 지문(member_hash)이 같으면 기록 파일에서 그대로 다시 씀. 그래프가 그대로인 묶음에 LLM을 다시 부르지 않음
- Community 노드에는 __Entity__ 라벨을 붙이지 않음. K6 엔티티 벡터 인덱스와 K7 고아 정리에 섞이지 않게 함
- 매 실행 그 세대의 Community 노드를 모두 지우고 다시 씀. 묶음 경계가 바뀌면 일부만 고치기가 어렵기 때문임

묶음 계산은 Neo4j GDS의 Leiden(gds.leiden.stream)을 씀. 그래프가 이미 Neo4j에 있어 밖으로 꺼내지 않아도 되고,
Neo4j GraphRAG 실무에서 가장 흔한 방법이기 때문임. 그래서 파이썬 쪽 추가 라이브러리(igraph, leidenalg)는 쓰지 않음.
"""

from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor

import config
from common import embed, log, make_llm, sha256_text

SYSTEM_PROPS = {"generation", "run_id", "embedding"}  # 엔티티를 알아보는 키와 보고서 입력에서 빼는 관리용 속성
VALUE_LIMIT = 200  # 보고서 입력에 넣는 속성 값 한 개의 글자 상한
# 보고서 판. 프롬프트나 보고서 꼴을 바꾸면 올림. 지문에 들어가 옛 판 보고서를 재사용하지 않게 함
REPORT_VERSION = "v2"
# 입력용 엔티티 번호(e3, e1~e7 등)가 본문에 남으면 지움. 상담사에게는 뜻 없는 기호라서임
ENTITY_REF = re.compile(r"\s*\(?\be\d+(?:\s*(?:~|-|,|와|및)\s*e?\d+)*\)?")

PROMPT_SYSTEM = (
    "너는 카드사 상담 지원용 지식 그래프의 묶음(커뮤니티)을 요약하는 분석가다. 주어진 엔티티와 관계만 근거로 쓰고, "
    "없는 사실을 지어내지 않는다. 반드시 JSON 하나로만 답한다.")
PROMPT_USER = """아래는 지식 그래프에서 서로 촘촘히 이어진 엔티티 묶음이다.
이 묶음이 무엇에 관한 것인지 상담사가 한눈에 알 수 있게 요약 보고서를 써라.

출력 형식(JSON):
{{"title": "묶음의 주제를 한 줄로(40자 이내)",
  "summary": "묶음 전체를 3 ~ 5문장으로 요약",
  "findings": [{{"text": "핵심 사실 한 문장", "entities": ["근거 엔티티 번호, 예: e3"]}}]}}
findings는 3 ~ 6개. 각 사실의 entities에는 근거가 된 엔티티 번호를 1개 이상 넣는다.
title, summary, findings의 text에는 e1 같은 엔티티 번호를 쓰지 말고 내용으로 풀어 쓴다. 번호는 entities 칸에만 쓴다.

엔티티:
{entities}

관계:
{relations}"""


# ---------------------------------------------------------------- ① 엔티티 그래프 읽기

def entity_key(label: str, props: dict) -> str:
    """세대와 실행이 바뀌어도 같은 엔티티면 같은 키. Neo4j 내부 ID는 실행마다 바뀌어 묶음 지문에 쓸 수 없음."""

    clean = {k: v for k, v in props.items() if k not in SYSTEM_PROPS}
    return label + "|" + json.dumps(clean, ensure_ascii=False, sort_keys=True, default=str)


def read_entity_graph(driver, generation: str) -> tuple[list[dict], list[tuple[int, int, str]]]:
    """세대의 엔티티와 엔티티 사이 관계를 읽음.

    반환: (엔티티 목록, 관계 목록). 엔티티는 키 순으로 정렬해 번호를 매김(같은 그래프면 같은 번호, 묶음 결정성의 전제).
    관계는 (시작 번호, 끝 번호, 관계 이름). 청크 노드로 가는 FROM_CHUNK와 K8이 만든 IN_COMMUNITY는 읽지 않음.
    """

    records, _, _ = driver.execute_query(
        "MATCH (n:__Entity__ {generation: $g}) "
        "RETURN elementId(n) AS id, [l IN labels(n) WHERE NOT l STARTS WITH '__'][0] AS label, "
        "properties(n) AS props", g=generation)
    entities = [{"id": r["id"], "label": r["label"], "props": dict(r["props"])} for r in records]
    for e in entities:
        e["key"] = entity_key(e["label"], e["props"])
    entities.sort(key=lambda e: e["key"])
    index = {e["id"]: i for i, e in enumerate(entities)}
    records, _, _ = driver.execute_query(
        "MATCH (a:__Entity__ {generation: $g})-[r]->(b:__Entity__ {generation: $g}) "
        "RETURN elementId(a) AS a, elementId(b) AS b, type(r) AS t", g=generation)
    relations = sorted({(index[r["a"]], index[r["b"]], r["t"]) for r in records if r["a"] in index and r["b"] in index})
    return entities, relations


# ---------------------------------------------------------------- ② GDS Leiden으로 묶기

def group(assign: dict[int, int]) -> list[list[int]]:
    """「엔티티 번호 → 묶음 번호」를 묶음 목록으로 바꿈. 묶음 안은 번호 순, 묶음끼리는 가장 작은 번호 순.

    GDS가 매기는 묶음 번호 자체는 뜻이 없어서, 구성원으로만 순서를 정해 같은 묶음이면 같은 출력이 나오게 함.
    """

    out: dict[int, list[int]] = {}
    for i, c in assign.items():
        out.setdefault(c, []).append(i)
    return sorted((sorted(v) for v in out.values()), key=lambda v: v[0])


def detect(driver, generation: str, run_id: str, entities: list[dict],
           relations: list[tuple[int, int, str]]) -> list[list[int]]:
    """GDS Leiden(모듈성, 씨앗 고정, 병렬 1, 한 단계)으로 엔티티를 묶음. 방향은 묶음에 상관없어 무방향으로 투영함.

    결정성: 노드를 엔티티 키 순서로 먼저 모두 투영하고 관계는 번호 순으로 넣음(GDS 내부 번호가 실행마다 같아짐).
    씨앗과 병렬 1을 함께 둬야 같은 그래프에서 같은 묶음이 나옴.
    반환: group()과 같은 꼴. 부수효과: 이름이 겹치지 않는 투영 그래프를 만들고 끝나면 반드시 지움.
    """

    if not entities:
        return []
    name = "k8-" + sha256_text(generation + "|" + run_id)[:12]
    ids = [e["id"] for e in entities]
    edges = sorted({(min(a, b), max(a, b)) for a, b, _ in relations if a != b})
    rows = [{"s": i, "t": None} for i in range(len(ids))] + [{"s": a, "t": b} for a, b in edges]
    try:
        driver.execute_query(
            "UNWIND $rows AS row MATCH (s) WHERE elementId(s) = $ids[row.s] "
            "OPTIONAL MATCH (t) WHERE row.t IS NOT NULL AND elementId(t) = $ids[row.t] "
            "WITH gds.graph.project($name, s, t, {}, {undirectedRelationshipTypes: ['*']}) AS g "
            "RETURN g.nodeCount AS n", rows=rows, ids=ids, name=name)
        records, _, _ = driver.execute_query(
            "CALL gds.leiden.stream($name, {randomSeed: $seed, concurrency: 1}) YIELD nodeId, communityId "
            "RETURN elementId(gds.util.asNode(nodeId)) AS id, communityId AS c",
            name=name, seed=config.COMMUNITY_SEED)
    finally:
        driver.execute_query("CALL gds.graph.drop($name, false) YIELD graphName RETURN graphName", name=name)
    index = {e: i for i, e in enumerate(ids)}
    return group({index[r["id"]]: r["c"] for r in records})


def member_hash(entities: list[dict], members: list[int], relations: list[tuple[int, int, str]]) -> str:
    """묶음 지문: 보고서 판, 구성원 키, 묶음 안 관계로 만듦. 하나라도 바뀌면 보고서를 다시 씀."""

    inside = set(members)
    rels = sorted(f"{entities[a]['key']}->{t}->{entities[b]['key']}" for a, b, t in relations
                  if a in inside and b in inside)
    return sha256_text("\n".join([REPORT_VERSION] + [entities[i]["key"] for i in members] + rels))


# ---------------------------------------------------------------- ③ 보고서

def _entity_line(no: int, e: dict) -> str:
    props = ", ".join(f"{k}={str(v)[:VALUE_LIMIT]}" for k, v in sorted(e["props"].items()) if k not in SYSTEM_PROPS)
    return f"e{no}. {e['label']}: {props}"


def _report_prompt(entities: list[dict], members: list[int], relations: list[tuple[int, int, str]]) -> tuple[str, dict]:
    """보고서 입력 글과 「번호 → 엔티티」 표. 큰 묶음은 관계가 많은 엔티티부터 상한까지만 넣음."""

    inside = set(members)
    degree = {i: 0 for i in members}
    for a, b, _ in relations:
        if a in inside and b in inside:
            degree[a] += 1
            degree[b] += 1
    shown = sorted(sorted(members, key=lambda i: (-degree[i], i))[:config.COMMUNITY_MAX_ENTITIES])
    refs = {f"e{k}": i for k, i in enumerate(shown, 1)}
    back = {i: ref for ref, i in refs.items()}
    lines = [_entity_line(k, entities[i]) for k, i in enumerate(shown, 1)]
    rels = [f"{back[a]} -[{t}]-> {back[b]}" for a, b, t in relations if a in back and b in back]
    return PROMPT_USER.format(entities="\n".join(lines), relations="\n".join(rels) or "(없음)"), refs


def _short(e: dict) -> str:
    """보고서 근거 표시용 짧은 이름: 라벨과 첫 속성 값."""

    vals = [str(v) for k, v in sorted(e["props"].items()) if k not in SYSTEM_PROPS]
    return f"{e['label']}({(vals[0] if vals else '')[:40]})"


def _plain(text) -> str:
    """본문에 남은 입력용 엔티티 번호를 지우고 공백을 정리함."""

    return re.sub(r"\s{2,}", " ", ENTITY_REF.sub("", str(text))).strip()


def _summarize(llm, entities, members, relations) -> dict:
    prompt, refs = _report_prompt(entities, members, relations)
    for attempt in range(config.LLM_RETRIES + 1):  # 형식 오류는 같은 입력으로 다시 물음
        try:
            d = json.loads(llm.chat_json(prompt, PROMPT_SYSTEM))
            findings = []
            for f in d.get("findings") or []:
                names = [_short(entities[refs[r]]) for r in f.get("entities") or [] if r in refs]
                findings.append(f"{_plain(f.get('text', ''))} [근거: {', '.join(names) or '없음'}]")
            if not d.get("title") or not d.get("summary"):
                raise ValueError("title 또는 summary가 비어 있음")
            return {"title": _plain(d["title"]), "summary": _plain(d["summary"]), "findings": findings}
        except (json.JSONDecodeError, ValueError, KeyError, TypeError):
            if attempt == config.LLM_RETRIES:
                raise
    raise RuntimeError("도달하지 않음")


# ---------------------------------------------------------------- K8 전체

def k8_summarize(driver, generation: str, run_id: str, cache: dict) -> tuple[dict, dict]:
    """K8. 세대의 엔티티 그래프를 묶고 보고서를 만들어 Neo4j에 씀.

    인자: cache는 이전 기록 파일의 {member_hash: 보고서}(없으면 빈 dict). 같은 지문의 보고서는 LLM을 부르지 않고 다시 씀.
    반환: (실행 결과 요약, 이번 세대의 {member_hash: 보고서}). 호출한 쪽이 기록 파일로 저장함.
    부수효과: 세대의 옛 Community 노드를 지우고 새로 씀, 벡터 인덱스 kg_community_embedding을 없으면 만듦.
    예외: 보고서 형식 오류가 재시도 뒤에도 이어지면 그 예외를 그대로 올림(일부만 쓰인 묶음이 게시되지 않게 함).
    """

    entities, relations = read_entity_graph(driver, generation)
    groups = detect(driver, generation, run_id, entities, relations)
    sizes = sorted((len(g) for g in groups), reverse=True)
    targets = [g for g in groups if len(g) >= config.COMMUNITY_MIN_SIZE]
    hashes = [member_hash(entities, g, relations) for g in targets]
    todo = [(h, g) for h, g in zip(hashes, targets) if h not in cache]
    llm = make_llm()
    with ThreadPoolExecutor(max_workers=config.LLM_CONCURRENCY) as pool:
        made = dict(zip([h for h, _ in todo], pool.map(lambda x: _summarize(llm, entities, x[1], relations), todo)))
    need_vec = [h for h in hashes if "embedding" not in (cache.get(h) or {})]
    reports = {}
    texts = []
    for h in hashes:
        r = dict(cache.get(h) or made[h])
        reports[h] = r
        if h in need_vec:
            texts.append(r["title"] + "\n" + r["summary"] + "\n" + "\n".join(r["findings"]))
    for h, v in zip(need_vec, embed(texts)):
        reports[h]["embedding"] = v

    # ⑤ 쓰기: 옛 묶음을 지우고 새로 씀(엔티티는 그대로 두고 IN_COMMUNITY와 Community만 바뀜)
    driver.execute_query("MATCH (c:Community {generation: $g}) DETACH DELETE c", g=generation)
    rows = []
    for h, g in zip(hashes, targets):
        r = reports[h]
        rows.append({"community_id": f"comm-{h[:12]}", "title": r["title"], "summary": r["summary"],
                     "findings": r["findings"], "member_hash": h, "size": len(g), "vec": r["embedding"],
                     "members": [entities[i]["id"] for i in g]})
    driver.execute_query(
        "UNWIND $rows AS row "
        "CREATE (c:Community {community_id: row.community_id, title: row.title, summary: row.summary, "
        "findings: row.findings, member_hash: row.member_hash, size: row.size, generation: $g, run_id: $run}) "
        "WITH c, row CALL db.create.setNodeVectorProperty(c, 'embedding', row.vec) "
        "WITH c, row UNWIND row.members AS mid MATCH (e) WHERE elementId(e) = mid "
        "CREATE (e)-[:IN_COMMUNITY]->(c)", rows=rows, g=generation, run=run_id)
    driver.execute_query(
        "CREATE VECTOR INDEX kg_community_embedding IF NOT EXISTS FOR (c:Community) ON c.embedding "
        "OPTIONS {indexConfig: {`vector.dimensions`: $d, `vector.similarity_function`: 'cosine'}}",
        d=config.EMBED_DIMENSION)
    result = {"entities": len(entities), "relations": len(relations), "groups": len(groups),
              "group_sizes": sizes, "summarized": len(targets), "llm_calls": len(todo),
              "reused": len(targets) - len(todo), "llm_usage": dict(llm.usage)}
    log(f"[KG K8] 커뮤니티 요약: 묶음 {len(groups)}개 중 {len(targets)}개 요약(엔티티 {config.COMMUNITY_MIN_SIZE}개 이상), "
        f"LLM {len(todo)}번, 재사용 {len(targets) - len(todo)}개")
    return result, reports


def verify(driver, generation: str) -> dict:
    """④ 검증 추가 항목(K8을 켰을 때만): 요약과 임베딩이 빠진 Community, 현재 세대 엔티티가 아닌 구성원, 빈 묶음을 셈."""

    rec, _, _ = driver.execute_query(
        "MATCH (c:Community {generation: $g}) "
        "OPTIONAL MATCH (e)-[:IN_COMMUNITY]->(c) "
        "WITH c, collect(e) AS ms "
        "RETURN count(c) AS communities, "
        "sum(CASE WHEN c.summary IS NULL OR c.summary = '' OR c.embedding IS NULL THEN 1 ELSE 0 END) AS incomplete, "
        "sum(CASE WHEN size(ms) = 0 THEN 1 ELSE 0 END) AS empty, "
        "sum(size([m IN ms WHERE NOT m:__Entity__ OR m.generation <> $g])) AS foreign_members", g=generation)
    r = dict(rec[0])
    r["ok"] = r["communities"] > 0 and r["incomplete"] == 0 and r["empty"] == 0 and r["foreign_members"] == 0
    return r
