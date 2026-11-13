"""--until 옵션이 쓰는 단계별 결과 보기(제공: 읽지 않아도 됨).

목적: 학생이 --until {단계}로 특정 단계에서 멈추면, 그 단계가 한 일과 실제 결과를 화면에 보여 주고,
      결과 일부를 파일로 저장하고, 저장소(Neo4j, OpenSearch)에서 직접 확인할 명령을 붙여 넣을 수 있게 출력함.
방법: index_graph.py의 색인 흐름은 바꾸지 않음. 단계가 끝날 때 이 모듈의 *_view 함수로 결과를 모으고,
      StageReporter가 파일 저장, 화면 출력, 멈춤 여부 판단을 맡음. 미리보기를 만들다 실패해도 색인은 멈추지 않음.
멈출 수 있는 곳(트랙마다 따로 돌아감):
  KG 구축          K1, K3(=K2+K3), K5(=K4+K5), K6, K8     (K7은 증분 색인용이라 이 실습에서 하지 않음)
  검색엔진 인덱싱   S1, S2, S3
"""

import json
import math
import os
import time
from pathlib import Path

SYSTEM_PROPS = {"generation", "run_id", "embedding"}  # 엔티티를 보여 줄 때 빼는 관리용 속성
NEO4J_BROWSER = "http://localhost:7474"  # Neo4j Browser 주소(compose의 NEO4J_HTTP_PORT 기본값)
CURL = "curl.exe -s"  # Windows PowerShell의 curl 별칭을 피하려고 curl.exe로 적음

# 멈출 수 있는 단계. what은 "이 단계가 한 일", next는 같은 트랙의 다음 멈춤 지점
STOPS = {
    "K1": {"track": "kg", "title": "K1 추출 청크 나누기", "next": "K3",
           "what": "청크를 LLM에 한 번에 넣을 글 조각(추출 청크)으로 나눔. 약관은 조항마다 따로 자르고, 혜택 안내와 상담은 "
                   "청크 하나가 추출 청크 하나임. 아직 LLM도 DB도 쓰지 않았음"},
    "K3": {"track": "kg", "title": "K2 추출 + K3 가지치기", "next": "K5",
           "what": "추출 청크마다 LLM에 그래프 스키마(허용된 노드와 관계)를 주고 노드와 관계를 뽑고(K2), "
                   "스키마 밖 노드, 관계, 속성은 바로 지움(K3). 결과는 아직 파일에만 있고 Neo4j에는 쓰지 않았음"},
    "K5": {"track": "kg", "title": "K4 적재 + K5 병합", "next": "K6",
           "what": "뽑은 노드와 관계를 Neo4j에 한 번에 씀(K4). 엔티티마다 자기가 나온 청크 노드로 FROM_CHUNK 관계를 이음. "
                   "그다음 스키마 고유 속성 값이 같은 엔티티를 하나로 합침(K5)"},
    "K6": {"track": "kg", "title": "K6 엔티티 설명 임베딩", "next": "K8",
           "what": "합치고 남은 엔티티마다 「라벨: 속성=값」 설명 글을 만들어 임베딩하고, Neo4j에 저장한 뒤 벡터 인덱스를 만듦. "
                   "이제 질문과 뜻이 가까운 엔티티를 바로 찾을 수 있음"},
    "K8": {"track": "kg", "title": "K8 커뮤니티 요약", "next": None,
           "what": "서로 촘촘히 이어진 엔티티를 묶고(Leiden), 묶음마다 LLM이 요약 보고서를 쓰고, 보고서를 임베딩해 "
                   "Community 노드로 저장함. 「전체적으로 어떤 주제가 있나」 같은 넓은 질문에 쓰임"},
    "S1": {"track": "search", "title": "S1 청크 임베딩", "next": "S2",
           "what": "청크 본문을 임베딩 모델로 숫자 벡터로 바꿈. 앞 세대에 같은 본문(해시)이 있으면 벡터를 다시 쓰고, "
                   "없는 본문만 API로 임베딩함. 아직 검색엔진에는 넣지 않았음"},
    "S2": {"track": "search", "title": "S2 키워드 분석", "next": "S3",
           "what": "청크 본문을 한국어 형태소 분석기(카드명 사전과 별칭 포함)로 낱말로 잘라 text_tokens를 만들고, "
                   "벡터와 메타데이터를 붙여 검색엔진 문서 한 건으로 만듦. 아직 검색엔진에는 넣지 않았음"},
    "S3": {"track": "search", "title": "S3 검색엔진 적재", "next": None,
           "what": "문서를 인덱스에 넣음(같은 청크의 옛 문서는 지우고 넣음). 한 인덱스에서 키워드(BM25)와 벡터(kNN) "
                   "검색이 모두 가능해짐"},
}
ALIASES = {"K2": "K3", "K4": "K5"}  # 한 묶음으로 도는 단계는 묶음 끝까지 수행함
TRACK_NAME = {"kg": "KG 구축", "search": "검색엔진 인덱싱"}


def parse_until(raw: str | None) -> dict | None:
    """--until 값을 읽어 {"step", "track", "note"}로 돌려줌. 값이 없으면 None(끝까지 수행). 잘못된 값이면 안내하고 종료."""
    if not raw:
        return None
    step = raw.strip().upper()
    if step == "K7":
        raise SystemExit("K7(청크 정리)은 증분 색인에서 쓰는 단계라 이 실습에서는 하지 않음(교재 31, 50쪽).\n"
                         "  → 멈출 수 있는 곳: " + ", ".join(STOPS))
    note = ""
    if step in ALIASES:
        note = f"{step}는 {ALIASES[step]}와 한 묶음으로 수행하므로 {ALIASES[step]}까지 수행함"
        step = ALIASES[step]
    if step not in STOPS:
        raise SystemExit(f"--until 값을 알 수 없음: {raw}\n  → 멈출 수 있는 곳: " + ", ".join(STOPS)
                         + " (K2는 K3, K4는 K5와 같은 묶음)")
    return {"step": step, "track": STOPS[step]["track"], "note": note}


# ---------------------------------------------------------------------------
# 작은 도구
# ---------------------------------------------------------------------------
def _short(text, limit: int = 40) -> str:
    """줄바꿈과 겹친 공백을 한 칸으로 줄이고 limit자까지만 보여 줌."""
    flat = " ".join(str(text).split())
    return flat if len(flat) <= limit else flat[:limit] + "…"


def _props_text(props: dict, limit: int = 2, width: int = 24) -> str:
    """엔티티 속성 앞 limit개를 「이름=값」으로 이음(관리용 속성은 뺌)."""
    items = [(k, v) for k, v in sorted(props.items()) if k not in SYSTEM_PROPS and v not in (None, "")]
    return ", ".join(f"{k}={_short(v, width)}" for k, v in items[:limit])


def _node_text(label: str, props: dict) -> str:
    return f"{label}({_props_text(props)})"


def _unit_label(unit: dict) -> str:
    """추출 청크 이름표: 약관은 조항 번호(#뒤), 나머지는 청크 하나가 곧 추출 청크라 「청크 전체」."""
    unit_id = unit["unit_id"]
    return unit_id.split("#", 1)[1] if "#" in unit_id else "청크 전체"


def _query(driver, cypher: str, **params) -> list[dict]:
    records, _, _ = driver.execute_query(cypher, **params)
    return [record.data() for record in records]


def _try_query(driver, notes: list, what: str, cypher: str, **params) -> list[dict]:
    """질의 하나가 실패해도 나머지 예시는 보여 주려고, 실패하면 notes에 이유를 남기고 빈 목록을 돌려줌."""
    try:
        return _query(driver, cypher, **params)
    except Exception as error:
        notes.append(f"{what}을(를) 만들지 못함: {type(error).__name__}: {str(error)[:160]}")
        return []


def _vector_index(driver, label: str, wanted: str) -> tuple[str, int | None]:
    """label의 embedding 속성에 걸린 벡터 인덱스의 (이름, 차원). 같은 라벨과 속성에 다른 이름의 인덱스가 먼저 있으면
    CREATE VECTOR INDEX ... IF NOT EXISTS가 새로 만들지 않으므로, 실제 이름을 찾아 씀(없으면 (wanted, None))."""
    try:
        rows = _query(driver, "SHOW VECTOR INDEXES YIELD name, labelsOrTypes, properties, options "
                              "RETURN name, labelsOrTypes, properties, options.indexConfig['vector.dimensions'] AS dim")
    except Exception:
        return wanted, None
    found = [r for r in rows if label in (r["labelsOrTypes"] or []) and "embedding" in (r["properties"] or [])]
    if not found:
        return wanted, None
    pick = next((r for r in found if r["name"] == wanted), found[0])
    return pick["name"], pick["dim"]


def _write_json(path: Path, data) -> None:
    """임시 파일에 다 쓴 뒤 바꿔 끼움(쓰다가 멈춰도 반쯤 쓴 파일이 남지 않게 함)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(temp, path)


def _view(step: str, numbers: list, examples: list, file_name: str, file_data: dict,
          cypher: list | None = None, curl: list | None = None, notes: list | None = None) -> dict:
    """단계 결과 보기 하나. numbers는 [(이름, 값)], examples는 [{"title", "lines"}], cypher와 curl은 [(설명, 명령)]."""
    return {"step": step, "numbers": numbers, "examples": examples, "file_name": file_name, "file_data": file_data,
            "cypher": cypher or [], "curl": curl or [], "notes": notes or []}


# ---------------------------------------------------------------------------
# KG 구축 단계 결과 보기
# ---------------------------------------------------------------------------
def k1_view(chunks: list[dict], units: list[dict], empty_chunk_ids: list[str]) -> dict:
    """K1 결과: 청크가 추출 청크로 어떻게 나뉘었는지(약관 청크 하나가 조항 여러 개로), 안 나뉜 경우, 비는 청크."""
    chunk_by_id = {c["chunk_id"]: c for c in chunks}
    units_of: dict[str, list[dict]] = {}
    for unit in units:
        for chunk_id in unit["chunk_ids"]:
            units_of.setdefault(chunk_id, []).append(unit)
    by_type: dict[str, int] = {}
    for unit in units:
        by_type[unit["doc_type"]] = by_type.get(unit["doc_type"], 0) + 1
    multi = [u for u in units if len(u["chunk_ids"]) > 1]

    def describe(chunk_id: str, text_limit: int) -> dict:
        chunk = chunk_by_id[chunk_id]
        return {"chunk_id": chunk_id, "doc_type": chunk["doc_type"], "chunk_text_length": len(chunk["text"]),
                "chunk_text_head": chunk["text"][:text_limit],
                "units": [{"unit_id": u["unit_id"], "text_length": len(u["text"]), "text": u["text"][:text_limit]}
                          for u in units_of.get(chunk_id, [])]}

    picks = []  # (제목, 청크 ID)
    split_ids = [cid for cid, us in units_of.items() if len(us) > 1 and cid in chunk_by_id]
    if split_ids:
        best = max(split_ids, key=lambda cid: len(units_of[cid]))
        picks.append(("청크 하나가 조항 여러 개로 나뉨", best))
    whole = next((c["chunk_id"] for c in chunks if len(units_of.get(c["chunk_id"], [])) == 1
                  and units_of[c["chunk_id"]][0]["unit_id"] == c["chunk_id"]), None)
    if whole:
        picks.append(("나누지 않음: 청크 하나가 추출 청크 하나", whole))
    if empty_chunk_ids and empty_chunk_ids[0] in chunk_by_id:
        picks.append(("추출 청크가 안 나오는 청크(표지나 차례 쪽)", empty_chunk_ids[0]))

    examples, file_examples = [], []
    for title, chunk_id in picks:
        chunk = chunk_by_id[chunk_id]
        mine = units_of.get(chunk_id, [])
        lines = [f"청크 {chunk_id[:30]}…  (본문 {len(chunk['text'])}자)  →  추출 청크 {len(mine)}개"]
        for unit in mine[:6]:
            lines.append(f"  {_unit_label(unit):<14} {len(unit['text']):>4}자  {_short(unit['text'], 34)}")
        if len(mine) > 6:
            lines.append(f"  … 외 {len(mine) - 6}개")
        if not mine:
            lines.append(f"  본문 앞부분: {_short(chunk['text'], 50)}")
        examples.append({"title": title, "lines": lines})
        file_examples.append({"title": title, **describe(chunk_id, 400)})
    if multi:
        unit = multi[0]
        examples.append({"title": "두 청크에 걸쳐 나온 같은 조항(겹침)",
                         "lines": [f"{unit['unit_id'][:40]}…", f"  나온 청크 {len(unit['chunk_ids'])}개: "
                                   + ", ".join(c[:24] for c in unit["chunk_ids"])]})
    numbers = [("청크", f"{len(chunks)}개"), ("추출 청크", f"{len(units)}개 {by_type}"),
               ("청크 2개 이상에 걸친 추출 청크", f"{len(multi)}개"),
               ("추출 청크가 안 나온 청크", f"{len(empty_chunk_ids)}개")]
    data = {"단계": "K1 추출 청크 나누기", "요약": dict(numbers), "예시": file_examples}
    return _view("K1", numbers, examples, "K1_units.json", data,
                 notes=["이 단계의 결과는 아직 DB에 없고 메모리에만 있었음. 위 파일이 일부를 저장한 것임"])


def k3_view(units: list[dict], k2: dict, failed: list[dict], fill_rates: dict, kg_prepared_path: str) -> dict:
    """K3 결과: LLM 호출 수, 가지치기로 지운 노드 수, 추출 청크 몇 개의 노드와 관계."""
    fresh = [u for u in units if "raw_nodes" in u]  # 이번에 LLM을 부른 단위(재사용분은 가지치기 전 수를 모름)
    raw = sum(u["raw_nodes"] for u in fresh)
    kept = sum(u["kept_nodes"] for u in fresh)
    total_nodes = sum(len(u.get("graph", {}).get("nodes", [])) for u in units)
    numbers = [("LLM으로 추출", f"{k2['llm_units']}개 (재사용 {k2['reused']}개, 실패 {len(failed)}개)"),
               ("토큰", f"{k2['usage'].get('total_tokens', 0):,}")]
    if fresh:
        numbers.append(("가지치기(K3)", f"새로 뽑은 노드 {raw}개 중 스키마 밖 {raw - kept}개를 지워 {kept}개 남김"))
    else:
        numbers.append(("가지치기(K3)", "모두 재사용이라 이번에 새로 뽑은 노드가 없음"))
    numbers += [("남은 노드(재사용 포함)", f"{total_nodes}개"), ("머리줄 채움률(%)", str(fill_rates))]

    def graph_lines(unit: dict) -> list[str]:
        graph = unit["graph"]
        by_id = {n["id"]: n for n in graph["nodes"]}
        lines = []
        for node in graph["nodes"][:5]:
            lines.append("  노드  " + _node_text(node["label"], node.get("properties") or {}))
        if len(graph["nodes"]) > 5:
            lines.append(f"        … 외 {len(graph['nodes']) - 5}개")
        kinds: dict[str, int] = {}  # 같은 꼴의 관계는 한 줄로 묶어 개수를 붙임
        for rel in graph["relationships"]:
            a, b = by_id.get(rel["start_node_id"]), by_id.get(rel["end_node_id"])
            if a and b:
                text = f"{a['label']} -[{rel['type']}]-> {b['label']}"
                kinds[text] = kinds.get(text, 0) + 1
        for text, count in list(kinds.items())[:4]:
            lines.append(f"  관계  {text}" + (f"  ×{count}" if count > 1 else ""))
        return lines

    picked, seen_types = [], set()
    for unit in units:  # 문서 유형마다 노드가 있는 첫 추출 청크
        if unit["doc_type"] not in seen_types and unit.get("graph", {}).get("nodes"):
            seen_types.add(unit["doc_type"])
            picked.append(unit)
    examples, file_examples = [], []
    for unit in picked:
        graph = unit["graph"]
        raw_text = f"가지치기 전 {unit['raw_nodes']}개 → 후 {unit['kept_nodes']}개" if "raw_nodes" in unit else "재사용"
        examples.append({"title": f"{unit['doc_type']} · {unit['unit_id'][:34]}… ({raw_text})",
                         "lines": [f"  입력 글: {_short(unit['text'], 56)}"] + graph_lines(unit)})
        file_examples.append({"unit_id": unit["unit_id"], "doc_type": unit["doc_type"], "입력_글": unit["text"][:600],
                              "가지치기": raw_text, "노드": graph["nodes"], "관계": graph["relationships"]})
    data = {"단계": "K2 추출 + K3 가지치기", "요약": dict(numbers), "예시": file_examples,
            "실패한_추출_청크": [{"unit_id": u["unit_id"], "error": u["error"]} for u in failed[:5]],
            "전체_결과": kg_prepared_path}
    return _view("K3", numbers, examples, "K3_extract.json", data,
                 notes=[f"전체 결과(모든 추출 청크의 노드와 관계)는 {kg_prepared_path} 에 있음"])


def count_entities(driver, generation: str) -> int:
    """이 세대의 엔티티 수(K5 병합 전후 비교용)."""
    return _query(driver, "MATCH (n:__Entity__ {generation: $g}) RETURN count(n) AS n", g=generation)[0]["n"]


def k5_view(driver, generation: str, chunks: list[dict], nodes_total: int, rels_total: int, from_chunk: int,
            entities_before: int, merge_value_count: int, merged: int, removed_dup: int) -> dict:
    """K5 결과: 적재한 노드와 관계 수, 병합 전후 엔티티 수, 합쳐진 엔티티, 청크 하나에 붙은 엔티티."""
    notes: list[str] = []
    entities_after = count_entities(driver, generation)
    labels = _try_query(driver, notes, "라벨별 수", "MATCH (n:__Entity__ {generation: $g}) "
                            "WITH [l IN labels(n) WHERE NOT l STARTS WITH '__'][0] AS label "
                            "RETURN label, count(*) AS c ORDER BY c DESC", g=generation)
    merged_rows = _try_query(
        driver, notes, "합쳐진 엔티티 예시",
        "MATCH (e:__Entity__ {generation: $g})-[:FROM_CHUNK]->(c:Chunk {generation: $g}) "
        "WITH e, collect(DISTINCT c.chunk_id) AS cs WHERE size(cs) > 1 "
        "RETURN [l IN labels(e) WHERE NOT l STARTS WITH '__'][0] AS label, "
        "apoc.map.removeKey(properties(e), 'embedding') AS props, cs ORDER BY size(cs) DESC LIMIT 3", g=generation)
    chunk_rows = _try_query(
        driver, notes, "청크 하나의 엔티티 예시",
        "MATCH (c:Chunk {generation: $g})<-[:FROM_CHUNK]-(e:__Entity__) WITH c, collect(e) AS es "
        "ORDER BY size(es) DESC LIMIT 1 "
        "RETURN c.chunk_id AS chunk_id, size(es) AS n, [e IN es[0..6] | {label: [l IN labels(e) WHERE NOT l STARTS WITH '__'][0], "
        "props: apoc.map.removeKey(properties(e), 'embedding')}] AS shown", g=generation)
    numbers = [("K4 적재", f"노드 {nodes_total}개(청크 노드 {len(chunks)}개 + 엔티티 {nodes_total - len(chunks)}개), "
                         f"관계 {rels_total}개(FROM_CHUNK {from_chunk}개 + 추출 관계 {rels_total - from_chunk}개)"),
               ("K5 병합 전 → 후", f"엔티티 {entities_before}개 → {entities_after}개 ({entities_before - entities_after}개가 합쳐져 사라짐)"),
               ("K5 병합", f"검사한 값 {merge_value_count}개 중 {merged}묶음을 합침, FROM_CHUNK 중복 {removed_dup}개 지움"),
               ("엔티티 라벨별", {r["label"]: r["c"] for r in labels})]
    examples = []
    if merged_rows:
        lines = []
        for row in merged_rows:
            lines.append(f"  {_node_text(row['label'], row['props'])}  ← 청크 {len(row['cs'])}개에서 나온 같은 대상")
        examples.append({"title": "합쳐진 엔티티(여러 청크에서 나온 같은 대상이 노드 하나로)", "lines": lines})
    else:
        examples.append({"title": "합쳐진 엔티티", "lines": ["  이번 데이터에는 합쳐진 엔티티가 없음"]})
    if chunk_rows:
        row = chunk_rows[0]
        lines = [f"  청크 {row['chunk_id'][:30]}…  에서 엔티티 {row['n']}개가 나옴(FROM_CHUNK)"]
        lines += [f"    {_node_text(x['label'], x['props'])}" for x in row["shown"]]
        if row["n"] > 6:
            lines.append(f"    … 외 {row['n'] - 6}개")
        examples.append({"title": "청크 하나에 붙은 엔티티", "lines": lines})
    g = generation
    cypher = [
        ("라벨별 노드 수", f"MATCH (n {{generation: '{g}'}}) RETURN labels(n) AS 라벨, count(*) AS 개수 ORDER BY 개수 DESC"),
        ("그림으로 보기: 청크와 그 청크에서 나온 엔티티 (결과 창에서 Graph 보기)",
         f"MATCH (c:Chunk {{generation: '{g}'}})<-[r:FROM_CHUNK]-(e:__Entity__) RETURN c, r, e LIMIT 30"),
        ("K5가 합친 엔티티: 청크 2개 이상에서 나온 엔티티",
         f"MATCH (e:__Entity__ {{generation: '{g}'}})-[:FROM_CHUNK]->(c:Chunk) WITH e, count(c) AS 청크수 WHERE 청크수 > 1 "
         "RETURN labels(e) AS 라벨, properties(e) AS 속성, 청크수 ORDER BY 청크수 DESC LIMIT 10"),
    ]
    data = {"단계": "K4 적재 + K5 병합", "요약": dict(numbers),
            "합쳐진_엔티티_예": [{"label": r["label"], "속성": r["props"], "나온_청크": r["cs"]} for r in merged_rows],
            "청크_하나의_엔티티_예": chunk_rows}
    return _view("K5", numbers, examples, "K5_graph.json", data, cypher=cypher, notes=notes)


def k6_view(driver, generation: str, embedded: int, dimension: int, index_name: str, model: str, describe) -> dict:
    """K6 결과: 임베딩한 엔티티 수, 엔티티 설명 글과 벡터 앞부분, 설명 글이 가까운 엔티티(벡터 검색)."""
    try:
        driver.execute_query("CALL db.awaitIndexes(60)")  # 방금 만든 벡터 인덱스가 켜질 때까지 기다림
    except Exception:  # 못 기다려도 아래 조회는 시도함(실패하면 그 예시만 빠짐)
        pass
    notes: list[str] = []
    actual_index, actual_dim = _vector_index(driver, "__Entity__", index_name)
    usable = actual_dim in (None, dimension)  # 차원이 다른 인덱스에는 이 실습의 벡터로 검색할 수 없음
    if actual_index != index_name:
        notes.append(f"이 Neo4j에는 같은 라벨과 속성에 {actual_index} 인덱스가 먼저 있어 {index_name}은 새로 만들어지지 않았음"
                     f"(CREATE VECTOR INDEX ... IF NOT EXISTS)")
    if not usable:
        notes.append(f"{actual_index} 인덱스는 {actual_dim}차원이고 이 실습의 벡터는 {dimension}차원이라 벡터 검색을 보여 줄 수 없음. "
                     f"다른 실습이 남긴 인덱스이므로 Neo4j Browser에서 DROP INDEX {actual_index} 를 실행한 뒤 K6을 다시 돌림")
    rows = _try_query(
        driver, notes, "엔티티 설명 글과 벡터 예시",
        "MATCH (n:__Entity__ {generation: $g}) WHERE n.embedding IS NOT NULL "
        "RETURN [l IN labels(n) WHERE NOT l STARTS WITH '__'][0] AS label, "
        "apoc.map.removeKey(properties(n), 'embedding') AS props, size(n.embedding) AS dim, n.embedding[0..4] AS head "
        "LIMIT 3", g=generation)
    near = [] if not usable else _try_query(
        driver, notes, "가까운 엔티티 예시(벡터 검색)",
        "MATCH (a:__Entity__ {generation: $g}) WHERE a.embedding IS NOT NULL WITH a LIMIT 1 "
        "CALL db.index.vector.queryNodes($index, 6, a.embedding) YIELD node, score "
        "WHERE node.generation = $g AND elementId(node) <> elementId(a) "
        "RETURN [l IN labels(a) WHERE NOT l STARTS WITH '__'][0] AS base_label, "
        "apoc.map.removeKey(properties(a), 'embedding') AS base_props, "
        "[l IN labels(node) WHERE NOT l STARTS WITH '__'][0] AS label, "
        "apoc.map.removeKey(properties(node), 'embedding') AS props, score ORDER BY score DESC LIMIT 3",
        g=generation, index=actual_index)
    numbers = [("임베딩한 엔티티", f"{embedded}개 ({model}, {dimension}차원)"),
               ("벡터 인덱스", actual_index + ("" if usable else f" ({actual_dim}차원: 이 실습과 맞지 않음)"))]
    examples = []
    lines = []
    for row in rows:
        lines.append(f"  글: {_short(describe(row['label'], row['props']), 70)}")
        lines.append(f"  벡터({row['dim']}차원) 앞 4개: {[round(v, 4) for v in row['head']]}")
    examples.append({"title": "엔티티 설명 글과 벡터(앞부분만)", "lines": lines or ["  임베딩된 엔티티가 없음"]})
    if near:
        base = near[0]
        lines = [f"  기준: {_short(describe(base['base_label'], base['base_props']), 70)}"]
        lines += [f"  {r['score']:.3f}  {_short(describe(r['label'], r['props']), 64)}" for r in near]
        examples.append({"title": "벡터가 가까운 엔티티(코사인 유사도): 설명 글의 뜻이 가까움", "lines": lines})
    g = generation
    cypher = [
        ("임베딩이 들어간 엔티티 수", f"MATCH (n:__Entity__ {{generation: '{g}'}}) WHERE n.embedding IS NOT NULL RETURN count(n) AS 개수"),
        ("벡터 앞 5개와 차원",
         f"MATCH (n:__Entity__ {{generation: '{g}'}}) RETURN labels(n) AS 라벨, n.embedding[0..5] AS 벡터_앞5개, "
         "size(n.embedding) AS 차원 LIMIT 3"),
    ]
    if usable:
        cypher.append(("벡터 검색: 엔티티 하나와 뜻이 가까운 엔티티 3개",
                       f"MATCH (a:__Entity__ {{generation: '{g}'}}) WITH a LIMIT 1 "
                       f"CALL db.index.vector.queryNodes('{actual_index}', 6, a.embedding) YIELD node, score "
                       f"WHERE node.generation = '{g}' AND elementId(node) <> elementId(a) "
                       "RETURN score, labels(node) AS 라벨, apoc.map.removeKey(properties(node), 'embedding') AS 속성 "
                       "ORDER BY score DESC LIMIT 3"))
    data = {"단계": "K6 엔티티 설명 임베딩", "요약": dict(numbers),
            "엔티티_예": [{"label": r["label"], "속성": r["props"], "설명_글": describe(r["label"], r["props"]),
                         "벡터_차원": r["dim"], "벡터_앞4개": r["head"]} for r in rows],
            "가까운_엔티티_예": [{"기준": near[0]["base_props"]}] + [{"label": r["label"], "속성": r["props"], "유사도": r["score"]}
                                                          for r in near] if near else []}
    return _view("K6", numbers, examples, "K6_embedding.json", data, cypher=cypher, notes=notes)


def k8_view(driver, generation: str, k8_result: dict) -> dict:
    """K8 결과: 묶음 수, 요약한 묶음 수, 큰 묶음의 보고서(제목, 요약, 핵심 사실)."""
    notes: list[str] = []
    rows = _try_query(driver, notes, "커뮤니티 보고서 예시",
                      "MATCH (c:Community {generation: $g}) "
                      "RETURN c.title AS title, c.size AS size, c.summary AS summary, c.findings AS findings "
                      "ORDER BY c.size DESC LIMIT 3", g=generation)
    numbers = [("엔티티와 관계", f"엔티티 {k8_result['entities']}개, 관계 {k8_result['relations']}개"),
               ("Leiden 묶음", f"{k8_result['groups']}개 중 요약 대상 {k8_result['summarized']}개"),
               ("보고서 LLM", f"{k8_result['llm_calls']}번 호출, 재사용 {k8_result['reused']}개, "
                            f"토큰 {k8_result['usage'].get('total_tokens', 0):,}")]
    examples = []
    for row in rows:
        lines = [f"  요약: {_short(row['summary'], 90)}"]
        if row["findings"]:
            lines.append(f"  핵심 사실 1: {_short(row['findings'][0], 90)}")
            lines.append(f"  (핵심 사실 {len(row['findings'])}개)")
        examples.append({"title": f"「{row['title']}」 (엔티티 {row['size']}개)", "lines": lines})
    if not rows:
        examples.append({"title": "커뮤니티 보고서", "lines": ["  요약 대상 묶음이 없음(엔티티 3개 이상인 묶음이 없었음)"]})
    g = generation
    cypher = [
        ("커뮤니티 목록(큰 순서)",
         f"MATCH (c:Community {{generation: '{g}'}}) RETURN c.title AS 제목, c.size AS 크기, c.summary AS 요약 ORDER BY 크기 DESC"),
        ("그림으로 보기: 커뮤니티와 구성원 엔티티 (결과 창에서 Graph 보기)",
         f"MATCH p = (e:__Entity__)-[:IN_COMMUNITY]->(c:Community {{generation: '{g}'}}) RETURN p LIMIT 40"),
        ("보고서 핵심 사실 전체", f"MATCH (c:Community {{generation: '{g}'}}) RETURN c.title AS 제목, c.findings AS 핵심_사실 LIMIT 3"),
    ]
    data = {"단계": "K8 커뮤니티 요약", "요약": dict(numbers),
            "보고서_예": [{"title": r["title"], "size": r["size"], "summary": r["summary"], "findings": r["findings"]}
                       for r in rows]}
    return _view("K8", numbers, examples, "K8_communities.json", data, cypher=cypher, notes=notes)


# ---------------------------------------------------------------------------
# 검색엔진 인덱싱 단계 결과 보기
# ---------------------------------------------------------------------------
def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / norm if norm else 0.0


def s1_view(chunks: list[dict], vectors: list[list[float]], new_count: int, model: str, dimension: int) -> dict:
    """S1 결과: 새로 임베딩한 수와 재사용한 수, 벡터 앞부분, 한 청크와 벡터가 가까운 청크."""
    numbers = [("임베딩", f"새로 {new_count}개, 재사용 {len(chunks) - new_count}개 ({model}, {dimension}차원)")]
    base = next((i for i, c in enumerate(chunks) if c["doc_type"] == "regulation"), 0)
    scores = sorted(((_cosine(vectors[base], v), i) for i, v in enumerate(vectors) if i != base), reverse=True)[:3]
    examples = [{"title": "청크 본문 → 벡터(앞부분만)",
                 "lines": [f"  {c['chunk_id'][:26]}…  {_short(c['text'], 30)}\n      벡터({len(v)}차원) 앞 5개: {[round(x, 4) for x in v[:5]]}"
                           for c, v in list(zip(chunks, vectors))[:2]]}]
    if scores:
        lines = [f"  기준: {_short(chunks[base]['text'], 56)}"]
        lines += [f"  {score:.3f}  {_short(chunks[i]['text'], 56)}" for score, i in scores]
        examples.append({"title": "벡터가 가까운 청크(코사인 유사도): 글의 뜻이 가까움", "lines": lines})
    if new_count == 0:
        notes = ["모두 활성 세대의 벡터를 재사용했음(본문 해시가 같아서). API를 부르지 않아 시간과 비용이 들지 않았음"]
    else:
        notes = ["아직 검색엔진에 넣기 전이라 검색엔진에서 확인할 것은 없음. S3 뒤에 확인함"]
    data = {"단계": "S1 청크 임베딩", "요약": dict(numbers),
            "청크_예": [{"chunk_id": c["chunk_id"], "본문_앞": c["text"][:200], "벡터_차원": len(v), "벡터_앞8개": v[:8]}
                      for c, v in list(zip(chunks, vectors))[:3]],
            "가까운_청크": [{"기준": chunks[base]["chunk_id"]}] + [{"chunk_id": chunks[i]["chunk_id"], "유사도": s}
                                                          for s, i in scores]}
    return _view("S1", numbers, examples, "S1_embedding.json", data, notes=notes)


def s2_view(docs: list[dict], tokenizer) -> dict:
    """S2 결과: 청크 본문이 낱말로 어떻게 잘렸는지(text_tokens), 검색엔진 문서 한 건의 필드."""
    alias_count = sum(len(v) for v in tokenizer.aliases.values())
    numbers = [("검색엔진 문서", f"{len(docs)}개"), ("카드명 사전", f"{len(tokenizer.card_names)}개, 별칭 {alias_count}개")]
    picked, seen = [], set()
    for doc in docs:  # 문서 유형이 다른 문서를 하나씩
        key = doc.get("doc_type", "")
        if key not in seen:
            seen.add(key)
            picked.append(doc)
    examples = []
    for doc in picked[:3]:
        tokens = doc["text_tokens"].split()
        examples.append({"title": f"{doc.get('doc_type', '')} · {doc['chunk_id'][:26]}…",
                         "lines": [f"  원문: {_short(doc['text'], 60)}", f"  낱말 {len(tokens)}개: {' | '.join(tokens[:14])}"
                                   + (" …" if len(tokens) > 14 else "")]})
    if docs:
        fields = [k for k in docs[0] if k not in ("text", "embedding", "text_tokens")]
        examples.append({"title": "검색엔진 문서 한 건의 필드",
                         "lines": ["  text(원문), text_tokens(낱말), embedding(벡터), " + ", ".join(fields)]})
    data = {"단계": "S2 키워드 분석", "요약": dict(numbers),
            "문서_예": [{k: (f"<벡터 {len(v)}차원>" if k == "embedding" else v) for k, v in doc.items()} for doc in picked[:3]]}
    return _view("S2", numbers, examples, "S2_keywords.json", data,
                 notes=["아직 검색엔진에 넣기 전이라 검색엔진에서 확인할 것은 없음. S3 뒤에 확인함"])


def s3_view(os_client, index: str, s3: dict, docs: list[dict], open_search_url: str) -> dict:
    """S3 결과: 인덱스 문서 수, 저장된 문서 한 건, 첫 문서의 낱말로 BM25 검색한 결과."""
    notes: list[str] = []
    os_client.indices.refresh(index=index)
    count = os_client.count(index=index)["count"]
    sample, hits = [], []
    try:
        sample = os_client.search(index=index, body={"size": 1, "_source": {"excludes": ["embedding"]}})["hits"]["hits"]
    except Exception as error:  # 예시 하나가 실패해도 나머지는 보여 줌
        notes.append(f"저장된 문서 예시를 만들지 못함: {type(error).__name__}: {str(error)[:120]}")
    words = []
    for token in sorted(set(docs[0]["text_tokens"].split()), key=lambda t: (-len(t), t)) if docs else []:  # 길이순, 같으면 가나다순(실행마다 같게)
        if len(token) >= 2:
            words.append(token)
        if len(words) == 3:
            break
    if words:
        try:
            hits = os_client.search(index=index, body={"size": 3, "_source": ["chunk_id", "text"],
                                                       "query": {"match": {"text_tokens": " ".join(words)}}})["hits"]["hits"]
        except Exception as error:
            notes.append(f"검색 예시를 만들지 못함: {type(error).__name__}: {str(error)[:120]}")
    numbers = [("인덱스", index), ("문서 수", f"{count}개"),
               ("이번 적재", f"옛 청크 {s3['deleted']}건 지우고 {s3['indexed']}건 넣음")]
    examples = []
    if sample:
        source = sample[0]["_source"]
        examples.append({"title": "저장된 문서 한 건(벡터는 뺌)",
                         "lines": [f"  chunk_id: {source.get('chunk_id', '')[:34]}…", f"  doc_type: {source.get('doc_type', '')}",
                                   f"  text_tokens: {_short(source.get('text_tokens', ''), 60)}"]})
    if hits:
        lines = [f"  검색어(첫 문서의 낱말): {' '.join(words)}"]
        lines += [f"  {h['_score']:.2f}  {h['_source']['chunk_id'][:24]}…  {_short(h['_source']['text'], 40)}" for h in hits]
        examples.append({"title": "키워드(BM25) 검색 결과: 점수가 높은 순", "lines": lines})
    base = f"{open_search_url}/{index}"
    curl = [
        ("문서 수", f'{CURL} "{base}/_count?pretty"'),
        ("문서 한 건 보기(벡터는 뺌)", f'{CURL} "{base}/_search?size=1&_source_excludes=embedding&pretty"'),
        ("약관 청크만 골라 보기(메타데이터 필터)", f'{CURL} "{base}/_search?q=doc_type:regulation&size=3&_source_includes=chunk_id,doc_type&pretty"'),
        ("인덱스 설정(키워드 BM25 필드, 벡터 kNN 필드)", f'{CURL} "{base}/_mapping?pretty"'),
    ]
    data = {"단계": "S3 검색엔진 적재", "요약": dict(numbers),
            "문서_예": [h["_source"] for h in sample],
            "검색_예": {"검색어": " ".join(words), "결과": [{"점수": h["_score"], "chunk_id": h["_source"]["chunk_id"]} for h in hits]}}
    return _view("S3", numbers, examples, "S3_index.json", data, curl=curl, notes=notes)


# ---------------------------------------------------------------------------
# 파일 저장, 화면 출력, 멈춤 판단
# ---------------------------------------------------------------------------
class StageReporter:
    """--until 실행 동안 단계 결과를 저장하고, 멈출 단계에서 안내를 출력함. until이 None이면 아무것도 하지 않음."""

    def __init__(self, until: dict | None, generation: str, gen_dir: Path, base_dir: Path, args, log) -> None:
        self.until = until
        self.generation = generation
        self.gen_dir = Path(gen_dir)
        self.base_dir = Path(base_dir)
        self.args = args
        self.log = log

    @property
    def active(self) -> bool:
        return self.until is not None

    def _rel(self, path: Path) -> str:
        return Path(path).resolve().relative_to(self.base_dir.resolve()).as_posix()

    def done(self, step: str, make_view) -> bool:
        """단계가 끝날 때 부름. 결과 일부를 파일로 저장하고, 여기가 멈출 단계면 안내를 출력하고 True를 돌려줌.

        make_view는 인자 없는 함수(결과 보기를 만듦). until이 없으면 부르지도 않음. 보기를 만들다 실패해도 색인은 계속함.
        """
        if not self.active:
            return False
        stop = step == self.until["step"]
        view = None
        try:
            view = make_view()
        except Exception as error:  # 보기 실패가 색인을 막으면 안 됨
            self.log(f"      ({step} 결과 보기를 만들지 못함: {type(error).__name__}: {str(error)[:120]})")
        if view is not None:
            path = self.gen_dir / "stages" / view["file_name"]
            view["file_path"] = self._rel(path)
            if view["cypher"] or view["curl"]:  # 화면에 나오는 확인 명령을 파일에도 남김
                view["file_data"]["확인_명령"] = {"Neo4j Browser에 붙여 넣기": [{"설명": t, "질의": q} for t, q in view["cypher"]],
                                              "터미널에 붙여 넣기": [{"설명": t, "명령": c} for t, c in view["curl"]]}
            try:
                _write_json(path, view["file_data"])
                if not stop:
                    self.log(f"      {step} 결과 일부를 파일로 저장: {view['file_path']}")
            except Exception as error:
                view["file_path"] = f"(저장하지 못함: {type(error).__name__})"
                self.log(f"      ({step} 결과 파일을 저장하지 못함: {type(error).__name__}: {str(error)[:120]})")
        if stop:
            self._print_guide(step, view)
        return stop

    # -- 화면 출력 ----------------------------------------------------------
    def _command(self, next_step: str, with_reuse: bool) -> str:
        """다음 단계로 이어서 돌리는 명령(지금 옵션을 그대로 이어받음)."""
        args = self.args
        parts = ["../.venv/Scripts/python.exe", "index_graph.py", "--run", args.run]
        if args.sample:
            parts.append("--sample")
        if getattr(args, "mine", False):
            parts.append("--mine")
        if args.chunks:
            parts += ["--chunks", args.chunks]
        reuse = args.reuse or (self._rel(self.gen_dir) if with_reuse else None)
        if reuse:
            parts += ["--reuse", reuse]
        parts += ["--until", next_step.lower()]
        return " ".join(parts)

    def _next_step(self, step: str) -> str | None:
        nxt = STOPS[step]["next"]
        if nxt == "K8" and self.args.skip_communities:
            return None
        return nxt

    def _print_guide(self, step: str, view: dict | None) -> None:
        info = STOPS[step]
        bar = "=" * 74
        out = ["", bar, f" {info['title']} 까지 수행하고 멈춤   (--until {self.until['step'].lower()}, {TRACK_NAME[info['track']]} 트랙)", bar]
        if self.until["note"]:
            out.append(f" 참고: {self.until['note']}")
        out += ["", "■ 이 단계가 한 일", f"  {info['what']}"]
        if view:
            out += ["", "■ 실제 결과"]
            out += [f"  - {name}: {value}" for name, value in view["numbers"]]
            for number, example in enumerate(view["examples"], 1):
                out += ["", f"  예 {number}) {example['title']}"]
                out += [f"    {line}".replace("\n", "\n    ") for line in example["lines"]]
            out += ["", "■ 결과 파일(일부만 저장)", f"  {view['file_path']}",
                    f"  보기: ../.venv/Scripts/python.exe -X utf8 -m json.tool --no-ensure-ascii {view['file_path']}"]
            out += [f"  ※ {note}" for note in view["notes"]]
            if view["cypher"]:
                out += ["", f"■ Neo4j에서 직접 확인: {NEO4J_BROWSER} 의 입력창에 한 개씩 붙여 넣고 실행(Ctrl+Enter)"]
                for no, (title, query) in enumerate(view["cypher"], 1):
                    out += [f"  [{no}] {title}", f"      {query}"]
            if view["curl"]:
                out += ["", "■ OpenSearch에서 직접 확인: 터미널에 한 줄씩 붙여 넣음"]
                for no, (title, command) in enumerate(view["curl"], 1):
                    out += [f"  [{no}] {title}", f"      {command}"]
        else:
            out += ["", "■ 결과 보기를 만들지 못했음(위 로그 참고). 색인은 이 단계까지 수행했음"]
        out += ["", "■ 게시하지 않음", "  ④ 검증과 ⑤ 게시는 건너뜀. 활성 세대 파일은 그대로이므로 검색과 check_graph.py는 이전과 똑같이 동작함",
                f"  이 세대 {self.generation} 는 데이터만 남아 있음. 지울 때: "
                f"../.venv/Scripts/python.exe check_graph.py --drop {self.generation}"]
        nxt = self._next_step(step)
        out += ["", "■ 이어서 보기"]
        if nxt:
            out += [f"  다음 단계 {STOPS[nxt]['title']}", f"  {self._command(nxt, with_reuse=False)}"]
            if info["track"] == "kg" and step in ("K3", "K5", "K6") and not self.args.reuse:
                out += ["  같은 --run으로 다시 돌리면 이 트랙을 처음부터 다시 만들고 LLM도 다시 부름. LLM을 건너뛰려면 끝에 아래를 붙임",
                        f"  --reuse {self._rel(self.gen_dir)}   (K2, K3 코드를 고쳐 다시 보는 중이면 붙이지 않음)"]
        else:
            other = "search" if info["track"] == "kg" else "kg"
            first = "S1" if other == "search" else "K1"
            out += [f"  {TRACK_NAME[info['track']]} 트랙은 여기가 끝임. 다른 트랙({TRACK_NAME[other]})을 보려면",
                    f"  {self._command(first, with_reuse=False)}",
                    "  두 트랙을 모두 돌리고 ④ 검증과 ⑤ 게시까지 하려면 --until 없이 실행함"]
        out.append(bar)
        print("\n".join(out), flush=True)
