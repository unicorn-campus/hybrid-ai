"""8단계 [단계 ④]: 채우기 시험. 시험용 표본을 스키마 초안으로 추출하고, 기대 답과 견주고, 경로와 검사 규칙을 셈.

- extract {문서 종류}: 시험용 단위마다 머리줄(version 2)을 붙여 LLMEntityRelationExtractor(schema=스키마 초안)로 추출하고
  GraphPruning으로 초안 밖 노드와 속성을 지움. 형식 오류는 같은 입력으로 2번까지 다시 함 → output/fill_calls.jsonl
- score: 역량 질문마다 지표(답이 있는 표본에서 뽑음, 답이 없는 표본에서 잘못 뽑음, 값이 기대 답과 같음)를 세고,
  세 문서 종류의 결과를 한 그래프로 합쳐 건너가는 경로와 검사 규칙(온톨로지 원본의 shapes/checks.ttl)을 셈 → output/fill_report.md
- 온톨로지는 Turtle에서 읽음: 초안 폴더(draft-ttl/)가 있으면 초안, 없으면 승인본(ttl/). 스키마 초안은 초안 Turtle에서
  만들어 낸 output/schema_draft.json을 씀(ttl/tools/build_from_ttl.py --draft)
온톨로지 적용: 검사 규칙의 위반 수(허용 값, 허용 수, 참조 무결성)와 원천을 건너가는 경로가 이어지는지를 함께 셈
실행: python tools/fill_test.py extract regulation | score
"""

from __future__ import annotations

import asyncio
import collections
import copy
import json
import re
import sys
import time

from common import BASE_DIR, DOC_TYPES, load_chunks, read_json, write_json

import ttl_write  # ttl/tools(common이 경로를 넣어 줌). 온톨로지 원본(Turtle) 읽기

turtle = ttl_write.turtle

DOC_NAMES = {"regulation": "약관", "benefit_guide": "카드 혜택 안내", "consult_log": "상담 기록"}
CONCURRENCY = 3


def tagged_template():
    """추출 프롬프트 틀: 라이브러리 기본 틀에서 입력 글만 <input_text> 태그로 감쌈.

    까닭(2026-11-18 실측): 기본 틀의 끝 「Input text: {text}」 뒤에 짧은 한국어 조항이 오면 모델이 「입력 글이 비어 있다」고 보고
    빈 그래프를 냄(약관 5단위 × 2회에서 빈 응답 6 ~ 7번). 태그로 감싸면 0번. 인덱싱도 같은 틀을 써야 함
    """
    from neo4j_graphrag.generation.prompts import ERExtractionTemplate
    base = ERExtractionTemplate.DEFAULT_TEMPLATE
    tagged = base.replace("Input text:\n\n{text}", "Input text (between <input_text> tags):\n<input_text>\n{text}\n</input_text>")
    assert tagged != base, "라이브러리 기본 틀이 바뀌어 태그를 넣지 못함"
    return ERExtractionTemplate(template=tagged)
HUB_SHARE = 0.30  # 노드 하나가 그 문서 종류 단위의 이만큼 이상과 이어지면 허브 경고


def tidy_graph_json(content: str) -> str:
    """LLM 응답을 추출기가 기대하는 그래프 꼴로 다듬음: 정해진 칸 밖 키 제거, id는 글자, 빈 속성 제거."""
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return content

    def plain(value):
        if value is None or value == "" or value == []:
            return None
        if isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, list) and all(isinstance(x, (str, int, float, bool)) for x in value):
            return value
        return json.dumps(value, ensure_ascii=False)

    def props(obj: dict) -> dict:
        return {k: plain(v) for k, v in (obj.get("properties") or {}).items() if plain(v) is not None}

    nodes = [{"id": str(n.get("id")), "label": str(n.get("label")), "properties": props(n)}
             for n in data.get("nodes", []) if isinstance(n, dict)]
    rels = [{"type": str(r.get("type")), "start_node_id": str(r.get("start_node_id")), "end_node_id": str(r.get("end_node_id")),
             "properties": props(r)} for r in data.get("relationships", []) if isinstance(r, dict)]
    return json.dumps({"nodes": nodes, "relationships": rels}, ensure_ascii=False)


# ---------------------------------------------------------------------------
# 머리줄 값 보정(공통 개념 층 header_fill_rule, 라운드 1 판정 F1)
# ---------------------------------------------------------------------------
def apply_header(graph: dict, values: dict | None, unit_id: str) -> dict:
    """추출 결과의 주 노드에 머리줄 값을 넣음. 주 노드가 없으면 만듦. 상담이면 고객군 노드와 IN_SEGMENT를 하나로 맞춤.

    graph: {"nodes": [...], "relationships": [{"type", "start", "end"}]}. 고친 그래프와 함께 고친 내용을 graph["header_fix"]에 적음
    """
    if values is None:
        return graph
    nodes, rels = graph["nodes"], graph["relationships"]
    fix = []
    label, props = values["label"], values["props"]
    key = next(iter(props))  # 첫 속성이 식별 키(article_no, benefit_id, item_id, record_id)
    same = [n for n in nodes if n["label"] == label and squash(n["properties"].get(key)) == squash(props[key])]
    targets = {r["end"] for r in rels}  # 다른 노드가 가리키는 노드(이어받은 상담, 가리킨 조항)는 주 노드 후보에서 뺌
    loose = [n for n in nodes if n["label"] == label and not n["properties"].get(key) and n["id"] not in targets]
    main = (same or loose or [None])[0]
    if main is None:
        main = {"id": f"{unit_id}:main", "label": label, "properties": {}}
        nodes.append(main)
        fix.append("주 노드 만듦")
    for k, v in props.items():
        if main["properties"].get(k) != v:
            fix.append(f"{k}: {main['properties'].get(k)!r} → {v!r}")
            main["properties"][k] = v
    if values["segment"]:
        seg_ids = {n["id"] for n in nodes if n["label"] == "CustomerSegment"}
        kept = next((n for n in nodes if n["label"] == "CustomerSegment" and n["properties"].get("name") == values["segment"]), None)
        if kept is None:
            kept = {"id": f"{unit_id}:segment", "label": "CustomerSegment", "properties": {"name": values["segment"]}}
            nodes.append(kept)
            fix.append(f"고객군 노드 만듦: {values['segment']}")
        drop = seg_ids - {kept["id"]}
        if drop:
            fix.append(f"다른 고객군 노드 {len(drop)}개 지움")
        graph["nodes"] = [n for n in nodes if n["id"] not in drop]
        rels = [r for r in rels if not (r["type"] == "IN_SEGMENT" and r["start"] == main["id"]) and r["end"] not in drop and r["start"] not in drop]
        rels.append({"type": "IN_SEGMENT", "start": main["id"], "end": kept["id"]})
        graph["relationships"] = rels
    graph["header_fix"] = fix
    return graph


# ---------------------------------------------------------------------------
# 추출
# ---------------------------------------------------------------------------
async def extract(doc_type: str) -> None:
    from neo4j_graphrag.components.entity_relation_extractor import LLMEntityRelationExtractor, OnError
    from neo4j_graphrag.components.graph_pruning import GraphPruning
    from neo4j_graphrag.components.schema import GraphSchema
    from neo4j_graphrag.components.types import TextChunk, TextChunks

    from llm import make_llm

    draft = read_json(BASE_DIR / doc_type / "output/schema_draft.json")
    schema = GraphSchema.model_validate(copy.deepcopy(draft))
    # F6: Groq JSON 모드는 닫는 괄호 하나만 빠져도 응답을 버림. 라이브러리가 고침.
    # 출력 한도: JSON 모드를 끄면 들여쓴 JSON이 나와 길어지므로 기본 3,072토큰에서 관계 목록이 잘림(라운드 3 첫 실행). 16,000으로 넓힘
    llm = make_llm(tidy=tidy_graph_json, json_mode=False, max_tokens=16000)
    extractor = LLMEntityRelationExtractor(llm=llm, prompt_template=tagged_template(), create_lexical_graph=False,
                                           on_error=OnError.RAISE)
    pruning = GraphPruning()
    from expected_answers import test_units
    from units import header_values
    units = read_json(BASE_DIR / doc_type / "output/test_units.json")
    values_of = {u["unit_id"]: header_values(doc_type, u) for u in test_units(doc_type)}
    gate = asyncio.Semaphore(CONCURRENCY)
    started = time.time()

    async def one(unit: dict) -> dict:
        record = {"unit_id": unit["unit_id"], "bundle": unit["bundle"], "attempts": 0, "error": None,
                  "raw_nodes": 0, "kept_nodes": 0, "pruning": None, "graph": {"nodes": [], "relationships": []}}
        async with gate:
            for attempt in range(3):  # 처음 1번 + 형식 오류면 2번까지 다시
                record["attempts"] = attempt + 1
                try:
                    chunks = TextChunks(chunks=[TextChunk(text=unit["header"] + "\n" + unit["text"], index=0)])
                    graph = await extractor.run(chunks=chunks, schema=schema)
                    result = await pruning.run(graph=graph, schema=schema)
                    record["raw_nodes"] = len(graph.nodes)
                    record["kept_nodes"] = len(result.graph.nodes)
                    record["pruning"] = json.loads(result.pruning_stats.model_dump_json()) if result.pruning_stats else None
                    record["graph"] = {
                        "nodes": [{"id": n.id, "label": n.label, "properties": n.properties} for n in result.graph.nodes],
                        "relationships": [{"type": r.type, "start": r.start_node_id, "end": r.end_node_id}
                                          for r in result.graph.relationships]}
                    record["error"] = None
                    if not graph.nodes and values_of[unit["unit_id"]] is not None and attempt < 2:
                        record["empty_retries"] = record.get("empty_retries", 0) + 1  # F5: 내용이 있는 단위의 빈 그래프는 다시 물음
                        continue
                    break
                except Exception as error:
                    record["error"] = f"{type(error).__name__}: {str(error)[:300]}"
            record["graph"] = apply_header(record["graph"], values_of[unit["unit_id"]], unit["unit_id"])  # F1
        print(f"[{doc_type}] {unit['unit_id']}: 노드 {record['raw_nodes']} → 가지치기 뒤 {record['kept_nodes']}, "
              f"시도 {record['attempts']}" + (f", 실패 {record['error'][:80]}" if record["error"] else ""), flush=True)
        return record

    records = await asyncio.gather(*(one(u) for u in units))
    out = BASE_DIR / doc_type / "output/fill_calls.jsonl"
    out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records), encoding="utf-8", newline="\n")
    print(f"[{doc_type}] 끝: 단위 {len(records)}, 실패 {sum(1 for r in records if r['error'])}, "
          f"토큰 {llm.usage['total_tokens']:,}, {time.time() - started:.0f}초")


# ---------------------------------------------------------------------------
# 채점 도우미
# ---------------------------------------------------------------------------
def squash(text) -> str:
    return re.sub(r"\s+", "", str(text or ""))


def bigram_recall(expected: str, got: str) -> float:
    e, g = squash(expected), squash(got)
    if not e:
        return 0.0
    if e in g or (g and g in e and len(g) >= 0.6 * len(e)):
        return 1.0
    grams = [e[i:i + 2] for i in range(len(e) - 1)] or [e]
    return sum(1 for x in grams if x in g) / len(grams)


TOPIC_REP: dict[str, str] = {}  # 주제 맞추기 표(F4): 띄어쓰기를 없앤 이름 → 대표 이름. score()가 채움


def topic_key(name: str) -> str:
    key = squash(name).lower()
    return TOPIC_REP.get(key, key)


def load_topic_map() -> str:
    """확정한 주제 맞추기 표가 있으면 approved 행만, 없으면 후보(미정 제외)를 임시로 씀. 쓴 기준을 돌려줌."""
    import os
    approved_rows = [r for r in ttl_write.topic_rows(ttl_write.work_dir()) if r["status"] == "approved"]  # maps/topic.ttl
    candidates = BASE_DIR / "common/output/topic_candidates.json"
    TOPIC_REP.clear()
    if os.environ.get("FILL_TOPIC_MAP") == "proposal":  # 사람 확정 전에 수정안으로 견줘 볼 때만 씀(확정 표 위에 수정안을 얹음)
        base_rows = approved_rows
        for r in base_rows + read_json(BASE_DIR / "common/output/topic_map_proposal.json")["rows"]:
            if r["status"] == "approved":
                TOPIC_REP[squash(r["name"]).lower()] = squash(r["representative"]).lower()
        return f"확정 전 수정안 기준(임시) {len(TOPIC_REP)}개 이름"
    if os.environ.get("FILL_TOPIC_MAP") == "none":
        return "맞추기 표 없음(이름 맞추기)"
    if approved_rows:
        for r in approved_rows:
            TOPIC_REP[squash(r["name"]).lower()] = squash(r["representative"]).lower()
        return f"확정 표 기준 {len(TOPIC_REP)}개 이름"
    if candidates.exists():
        for g in read_json(candidates)["groups"]:
            for m in g["members"]:
                TOPIC_REP[squash(m).lower()] = squash(g["representative"]).lower()
        return f"확정 전이라 후보 기준(임시) {len(TOPIC_REP)}개 이름"
    return "맞추기 표 없음(이름 맞추기)"


class UnitGraph:
    """단위 하나의 추출 결과를 라벨과 관계로 찾기 쉽게 감싼 것."""

    def __init__(self, record: dict):
        self.nodes = {n["id"]: n for n in record["graph"]["nodes"]}
        self.rels = record["graph"]["relationships"]

    def label(self, label: str) -> list[dict]:
        return [n for n in self.nodes.values() if n["label"] == label]

    def out(self, node: dict | None, rel: str, label: str | None = None) -> list[dict]:
        if not node:
            return []
        ends = [self.nodes.get(r["end"]) for r in self.rels if r["start"] == node["id"] and r["type"] == rel]
        return [e for e in ends if e and (label is None or e["label"] == label)]

    def prop(self, node: dict | None, *names: str) -> str:
        if not node:
            return ""
        return " ".join(str(node["properties"].get(n, "")) for n in names if node["properties"].get(n) not in (None, ""))


def main_node(g: UnitGraph, doc_type: str, unit_id: str) -> dict | None:
    if doc_type == "regulation":
        no = unit_id.split(":", 1)[1] if ":" in unit_id else None
        found = [n for n in g.label("Article") if squash(n["properties"].get("article_no")) == squash(no)]
        return (found or g.label("Article") or [None])[0]
    if doc_type == "benefit_guide":
        return (g.label("Benefit") or [None])[0]
    found = [n for n in g.label("Consultation") if n["properties"].get("record_id") == unit_id_record(unit_id)]
    return (found or g.label("Consultation") or [None])[0]


_RECORDS = {}


def unit_id_record(unit_id: str) -> str | None:
    if not _RECORDS:
        for c in load_chunks("consult_log"):
            _RECORDS[c["id"]] = c["metadata"]["record_id"]
    return _RECORDS.get(unit_id)


def extracted(doc_type: str, field: str, g: UnitGraph, unit_id: str, category_map: dict):
    """역량 질문 칸마다 추출 결과에서 답에 해당하는 값을 꺼냄. 빈 값이면 None."""
    m = main_node(g, doc_type, unit_id)
    if doc_type == "regulation":
        value = {"R1": lambda: g.prop(m, "condition", "action"), "R2": lambda: g.prop(m, "deadline", "amount"),
                 "R3": lambda: g.prop(m, "action", "deadline"),
                 "R4": lambda: sorted({squash(t["properties"].get("article_no")) for t in g.out(m, "REFERS_TO", "Article")} - {""}),
                 "M1": lambda: sorted({t["properties"].get("name", "") for t in g.out(m, "ABOUT", "Topic")} - {""})}[field]()
    elif doc_type == "benefit_guide":
        rule = (g.label("UsageRule") or [None])[0]
        value = {"B1": lambda: g.prop(m, "amount"), "B2": lambda: g.prop(m, "condition", "target"),
                 "B3": lambda: g.prop(m, "limit", "validity", "payout"), "B4": lambda: g.prop(m, "exclusion"),
                 "B5": lambda: g.prop(rule, "limit", "restriction"),
                 "M2": lambda: sorted({t["properties"].get("name", "") for t in g.out(m, "ABOUT", "Topic")} - {""}),
                 "X1": lambda: (category_map.get(m["properties"].get("benefit_id")) if m else None),
                 "M3,X3": lambda: (m or rule or {"properties": {}})["properties"].get("product_id")}[field]()
    else:
        complaints = g.out(m, "HAS_COMPLAINT", "Complaint") or g.label("Complaint")
        proposals = g.out(m, "HAS_PROPOSAL", "Proposal") or g.label("Proposal")
        value = {"C1": lambda: " ".join(c["properties"].get("content", "") for c in complaints),
                 "C2": lambda: " ".join(r["properties"].get("content", "") for r in (g.out(m, "HAS_REQUEST", "Request") or g.label("Request"))),
                 "C3": lambda: [{"content": p["properties"].get("content", ""), "accepted": p["properties"].get("accepted")} for p in proposals],
                 "C4": lambda: g.prop(m, "progress"),
                 "C5": lambda: sorted({t["properties"].get("record_id") for t in g.out(m, "FOLLOWS", "Consultation")} - {None, ""}),
                 "C6": lambda: g.prop(m, "follow_up_method"),
                 "A1": lambda: next((s["properties"].get("name") for s in g.out(m, "IN_SEGMENT", "CustomerSegment")), None),
                 "M1,M2": lambda: sorted({t["properties"].get("name", "") for c in complaints for t in g.out(c, "ABOUT", "Topic")} - {""}),
                 "M3": lambda: (m or {"properties": {}})["properties"].get("product_id"),
                 "X2": lambda: (m or {"properties": {}})["properties"].get("member_pseudo_id")}[field]()
    if value in ("", [], None) or (isinstance(value, str) and not value.strip()):
        return None
    return value


def matches(shape: str, expected, got) -> bool:
    if shape in ("quote", "quotes"):
        quotes = [expected] if isinstance(expected, str) else expected
        text = got if isinstance(got, str) else json.dumps(got, ensure_ascii=False)
        return sum(1 for q in quotes if bigram_recall(q, text) >= 0.6) >= max(1, len(quotes) / 2)
    if shape == "names":
        e, g = {topic_key(x) for x in expected}, {topic_key(x) for x in got}
        return any(a == b or a in b or b in a for a in e for b in g)
    if shape == "ids":
        return {squash(x) for x in expected} == {squash(x) for x in got}
    if shape == "proposals":
        hit = 0
        for p in expected:
            best = max(got, key=lambda x: bigram_recall(p["content"], x["content"]), default=None)
            if best and bigram_recall(p["content"], best["content"]) >= 0.5 and (p.get("accepted") is None or best.get("accepted") == p["accepted"]):
                hit += 1
        return hit >= max(1, len(expected) / 2)
    return squash(expected) == squash(got)  # value, category


# ---------------------------------------------------------------------------
# 채점과 보고
# ---------------------------------------------------------------------------
def load_records(doc_type: str) -> dict[str, dict]:
    path = BASE_DIR / doc_type / "output/fill_calls.jsonl"
    return {json.loads(l)["unit_id"]: json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()}


def score_doc(doc_type: str, category_map: dict) -> dict:
    expected = read_json(BASE_DIR / doc_type / "expected_answers.json")
    records = load_records(doc_type)
    texts = {u["unit_id"]: u for u in read_json(BASE_DIR / doc_type / "output/test_units.json")}
    metrics, wrong = {}, []
    for field, meta in expected["fields"].items():
        if field == "X1" and not category_map:
            continue  # 업종은 맞추기 표가 있어야 셈
        has = got = false_pos = none = same = 0
        for row in expected["units"]:
            exp = row["answers"][field]["answer"]
            value = extracted(doc_type, field, UnitGraph(records[row["unit_id"]]), row["unit_id"], category_map)
            if exp in ("없음", [], None):
                none += 1
                if value is not None:
                    false_pos += 1
                    wrong.append({"unit_id": row["unit_id"], "field": field, "kind": "답이 없는데 뽑음", "expected": exp, "got": value})
                continue
            has += 1
            if value is not None:
                got += 1
                if matches(meta["shape"], exp, value):
                    same += 1
                else:
                    wrong.append({"unit_id": row["unit_id"], "field": field, "kind": "값이 다름", "expected": exp, "got": value})
            else:
                wrong.append({"unit_id": row["unit_id"], "field": field, "kind": "답이 있는데 못 뽑음", "expected": exp, "got": None})
        metrics[field] = {"has": has, "got": got, "recall": round(got / has, 3) if has else None,
                          "none": none, "false": false_pos, "false_rate": round(false_pos / none, 3) if none else None,
                          "same": same, "same_rate": round(same / has, 3) if has else None}
    pruned = sum(r["raw_nodes"] - r["kept_nodes"] for r in records.values())
    for w in wrong:
        w["text"] = texts[w["unit_id"]]["text"][:300]
    return {"metrics": metrics, "wrong": wrong, "pruned_nodes": pruned, "raw_nodes": sum(r["raw_nodes"] for r in records.values()),
            "failed_calls": [r["unit_id"] for r in records.values() if r["error"]], "units": len(records)}


def graph_checks(category_map: dict) -> dict:
    """세 문서 종류의 시험 결과를 한 그래프로 합쳐(주제는 이름 맞추기로 합침) 경로와 검사 규칙을 셈."""
    concepts = turtle.load_concepts(ttl_write.work_dir())  # Class와 값 목록, 검사 규칙 목록
    segments = concepts["classes"][[c["name"] for c in concepts["classes"]].index("고객군")]["allowed_values"]["values"]
    categories = concepts["classes"][[c["name"] for c in concepts["classes"]].index("업종")]["allowed_values"]["values"]
    product_ids = set(read_json(BASE_DIR / "inputs/key_values.json")["keys"]["Product.product_id"]["values"])
    record_ids = {c["metadata"]["record_id"] for c in load_chunks("consult_log")}
    article_nos = {u["keys"]["article_no"] for u in read_json(BASE_DIR / "regulation/units.json")["units"] if u["keys"]}
    graphs = {d: {uid: UnitGraph(r) for uid, r in load_records(d).items()} for d in DOC_TYPES}

    topics = {d: collections.defaultdict(set) for d in DOC_TYPES}  # 문서 종류 → 주제 키 → 이어진 단위
    no_topic = collections.Counter()
    owner_count = collections.Counter()
    for d, units in graphs.items():
        for uid, g in units.items():
            owners = {"regulation": g.label("Article"), "benefit_guide": g.label("Benefit"), "consult_log": g.label("Complaint")}[d]
            if not owners:
                continue
            owner_count[d] += 1
            names = {topic_key(t["properties"].get("name", "")) for o in owners for t in g.out(o, "ABOUT", "Topic")} - {""}
            if not names:
                no_topic[d] += 1
            for name in names:
                topics[d][name].add(uid)
    consult_topics = set(topics["consult_log"])
    paths = {
        "P1": {"what": "상담 불만의 주제 가운데 약관 조항의 주제와 같은 것",
               "shared": sorted(consult_topics & set(topics["regulation"])), "base": len(consult_topics)},
        "P2": {"what": "상담 불만의 주제 가운데 혜택의 주제와 같은 것",
               "shared": sorted(consult_topics & set(topics["benefit_guide"])), "base": len(consult_topics)},
    }
    for p in paths.values():
        p["rate"] = round(len(p["shared"]) / p["base"], 3) if p["base"] else None
    complaints_linked = {"P1": 0, "P2": 0, "complaint_units": 0}
    for uid, g in graphs["consult_log"].items():
        names = {topic_key(t["properties"].get("name", "")) for c in g.label("Complaint") for t in g.out(c, "ABOUT", "Topic")} - {""}
        if g.label("Complaint"):
            complaints_linked["complaint_units"] += 1
            complaints_linked["P1"] += bool(names & set(topics["regulation"]))
            complaints_linked["P2"] += bool(names & set(topics["benefit_guide"]))

    def filled(doc: str, label: str, key: str) -> tuple[int, int]:
        """그 단위의 주 노드에서 키가 채워진 수 / 주 노드를 세야 할 단위 수(답이 없어야 하는 단위는 뺌).

        상담은 이어받은 앞선 상담(record_id만 채운 노드)을 세지 않음. 주 노드가 아예 없는 단위는 채우지 못한 것으로 셈
        """
        hit = base = 0
        for uid, g in graphs[doc].items():
            if doc == "benefit_guide":
                kind = "UsageRule" if uid in usage_units else "Benefit"
                if kind != label or uid in no_item_units:
                    continue
                nodes = g.label(label)
            else:
                nodes = [n for n in g.label(label) if n["properties"].get("record_id") == unit_id_record(uid)]
            base += 1
            hit += any(n["properties"].get(key) for n in nodes)
        return hit, base

    plan = read_json(BASE_DIR / "sample_plan.json")["doc_types"]["benefit_guide"]["test"]
    usage_units = set(plan.get("이용 기준", []))
    no_item_units = set(plan.get("항목 아님", []))

    keys = {"P3 상담 product_id": filled("consult_log", "Consultation", "product_id"),
            "P5 상담 member_pseudo_id": filled("consult_log", "Consultation", "member_pseudo_id"),
            "P6 혜택 product_id": filled("benefit_guide", "Benefit", "product_id"),
            "P6 이용 기준 product_id": filled("benefit_guide", "UsageRule", "product_id")}
    benefits = [n for g in graphs["benefit_guide"].values() for n in g.label("Benefit")]
    keys["P4 혜택 업종(맞추기 표 approved)"] = (sum(1 for n in benefits if category_map.get(n["properties"].get("benefit_id"))), len(benefits))
    consult_pids = {n["properties"].get("product_id") for g in graphs["consult_log"].values() for n in g.label("Consultation")} - {None}
    benefit_pids = {n["properties"].get("product_id") for n in benefits} - {None}

    hubs = []
    for d in DOC_TYPES:
        for name, uids in topics[d].items():
            if owner_count[d] and len(uids) / owner_count[d] >= HUB_SHARE:
                hubs.append({"doc_type": d, "topic": name, "units": len(uids), "of": owner_count[d]})

    # 검사 규칙: 시험 결과를 노드와 관계 목록으로 펴서 온톨로지 원본의 규칙(shapes/checks.ttl)으로 검사함(SHACL).
    # 인덱싱이 쓰는 것과 같은 규칙 파일이라, 시험에서 통과한 규칙이 인덱싱에서도 같은 뜻으로 적용됨
    nodes, relationships = [], []
    for units in graphs.values():
        for uid, g in units.items():
            for n in g.nodes.values():
                props = {k: (x if isinstance(x, (str, int, float, bool)) else json.dumps(x, ensure_ascii=False))
                         for k, x in n["properties"].items() if x is not None}
                nodes.append({"id": f"{uid}#{n['id']}", "label": n["label"], "props": props})
            relationships += [{"source": f"{uid}#{r['start']}", "type": r["type"], "target": f"{uid}#{r['end']}"}
                              for r in g.rels if r["start"] in g.nodes and r["end"] in g.nodes]
    nodes += [{"id": f"category#{value}", "label": "Category", "props": {"name": value}} for value in sorted(set(category_map.values()))]
    v = collections.defaultdict(list, turtle.run_checks(nodes, relationships, product_ids, record_ids, article_nos,
                                                        ttl_write.work_dir()))
    rules = {c["id"]: {"kind": c["kind"], "target": c["target"], "rule": c["rule"], "violations": len(v[c["id"]]),
                       "examples": v[c["id"]][:5]} for c in concepts["checks"] if c["id"].startswith("K")}
    rules["K07"]["note"] = "정형 DB의 키 값 목록(inputs/key_values.json, 상품 ID 64개)과 대조함"
    return {"paths": paths, "complaints_linked": complaints_linked, "keys": {k: {"filled": a, "of": b} for k, (a, b) in keys.items()},
            "consult_benefit_product_overlap": len(consult_pids & benefit_pids), "consult_products": len(consult_pids),
            "no_topic": {d: {"units": no_topic[d], "of": owner_count[d]} for d in DOC_TYPES}, "hubs": hubs, "rules": rules,
            "topics": {d: len(topics[d]) for d in DOC_TYPES}}


def judge(metric: dict, criteria: dict, field: str = "", ignore_false: dict | None = None) -> str:
    ok = True
    if metric["recall"] is not None:
        ok &= metric["recall"] >= criteria["recall_min"]
        ok &= metric["same_rate"] >= criteria["same_min"]
    if metric["false_rate"] is not None and field not in (ignore_false or {}):  # 조정 1: 판정에서 뺀 잘못 뽑음
        ok &= metric["false_rate"] <= criteria["false_max"]
    return "통과" if ok else "미달"


def write_reports(scores: dict, checks: dict, criteria: dict, round_no: int, ignore_false: dict | None = None) -> None:
    ignore_false = ignore_false or {}
    cq = {q["id"]: q["question"] for q in read_json(BASE_DIR / "competency_questions.json")["questions"]}
    common = ["## 경로 검사(세 문서 종류를 합친 그래프)", "",
              "| 지점 | 무엇을 셈 | 결과 |", "|---|---|---|"]
    for pid, p in checks["paths"].items():
        common.append(f"| {pid} | {p['what']} | {len(p['shared'])} / {p['base']}"
                      + (f" ({p['rate']:.0%})" if p["rate"] is not None else "") + f": {', '.join(p['shared'][:8])} |")
    cl = checks["complaints_linked"]
    common.append(f"| P1 | 불만이 있는 상담 가운데 약관 주제와 이어진 상담 | {cl['P1']} / {cl['complaint_units']} |")
    common.append(f"| P2 | 불만이 있는 상담 가운데 혜택 주제와 이어진 상담 | {cl['P2']} / {cl['complaint_units']} |")
    for key, k in checks["keys"].items():
        common.append(f"| {key.split()[0]} | {key[3:]} 채워진 비율 | {k['filled']} / {k['of']} |")
    common.append(f"| P3 | 상담이 가리킨 상품 가운데 시험용 혜택 표본에도 있는 상품 | {checks['consult_benefit_product_overlap']} / {checks['consult_products']} |")
    common += ["", "공통 노드(주제)에 하나도 잇지 못한 단위", "", "| 문서 종류 | 단위 | 비율 |", "|---|---|---|"]
    for d, n in checks["no_topic"].items():
        common.append(f"| {DOC_NAMES[d]} | {n['units']} / {n['of']} | {n['units'] / n['of']:.0%} |" if n["of"] else f"| {DOC_NAMES[d]} | 0 / 0 | - |")
    common += ["", f"- 허브 경고(한 주제가 그 문서 종류 단위의 {HUB_SHARE:.0%} 이상과 이어짐): "
               + (", ".join(f"{h['topic']}({DOC_NAMES[h['doc_type']]} {h['units']}/{h['of']})" for h in checks["hubs"]) or "없음") + "  ",
               f"- 문서 종류별 주제 수(이름 맞추기 뒤): " + ", ".join(f"{DOC_NAMES[d]} {n}" for d, n in checks["topics"].items()) + "  ",
               "", "## 규칙 검사(공통 개념 층의 검사 규칙)", "", "| 번호 | 종류 | 대상 | 조건 | 위반 수 | 예 |", "|---|---|---|---|---|---|"]
    for rid, r in checks["rules"].items():
        common.append(f"| {rid} | {r['kind']} | {r['target']} | {r['rule']} | {r['violations']} | {'; '.join(r['examples'][:3])} |")
    for doc_type, s in scores.items():
        lines = [f"# 채우기 시험 보고서: {DOC_NAMES[doc_type]}(라운드 {round_no})", "",
                 f"- 시험용 단위 {s['units']}개, 추출 실패 {len(s['failed_calls'])}개, 가지치기로 지운 노드 {s['pruned_nodes']} / {s['raw_nodes']}  ",
                 f"- 합격 기준: 뽑음 {criteria['recall_min']:.0%} 이상, 값 일치 {criteria['same_min']:.0%} 이상, 잘못 뽑음 {criteria['false_max']:.0%} 이하  ",
                 "", "## 질문별 지표", "",
                 "| 질문 | 내용 | 답이 있는 표본에서 뽑음 | 값이 기대 답과 같음 | 답이 없는 표본에서 잘못 뽑음 | 판정 |", "|---|---|---|---|---|---|"]
        for field, m in s["metrics"].items():
            first = field.split(",")[0]
            rec = f"{m['got']}/{m['has']} ({m['recall']:.0%})" if m["has"] else "-"
            same = f"{m['same']}/{m['has']} ({m['same_rate']:.0%})" if m["has"] else "-"
            fp = f"{m['false']}/{m['none']} ({m['false_rate']:.0%})" if m["none"] else "-"
            fp += " (판정 제외)" if field in ignore_false else ""
            lines.append(f"| {field} | {cq.get(first, '')} | {rec} | {same} | {fp} | {judge(m, criteria, field, ignore_false)} |")
        lines += ["", "## 잘못 뽑은 예(최대 6건)", ""]
        for w in s["wrong"][:6]:
            lines.append(f"- {w['unit_id']} {w['field']} {w['kind']}: 기대 {json.dumps(w['expected'], ensure_ascii=False)[:160]} / "
                         f"추출 {json.dumps(w['got'], ensure_ascii=False)[:160]}  ")
        lines += [""] + common
        (BASE_DIR / doc_type / "output/fill_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def score() -> None:
    criteria = read_json(BASE_DIR / "pass_criteria.json")
    candidates_path = BASE_DIR / "common/output/category_candidates.json"
    category_map = {r["benefit_id"]: r["category"] for r in ttl_write.category_rows(ttl_write.work_dir()) if r["status"] == "approved"}
    if category_map:  # 사람이 확정한 표(maps/category.ttl)가 있으면 확정한 행만 씀
        print("업종: 확정 표 기준", len(category_map), "건")
    elif candidates_path.exists():  # 확정 전에는 LLM 후보(미정 제외)로 임시로 셈
        category_map = {r["benefit_id"]: r["category"] for r in read_json(candidates_path)["rows"] if not r["undecided"]}
        print("업종: 확정 전이라 후보 기준(임시)", len(category_map), "건")
    topic_basis = load_topic_map()
    print("주제:", topic_basis)
    scores = {d: score_doc(d, category_map) for d in DOC_TYPES}
    checks = graph_checks(category_map)
    round_no = criteria.get("round", 1)
    write_reports(scores, checks, criteria["questions"], round_no, criteria.get("ignore_false"))
    write_json(BASE_DIR / "output/fill_scores.json", {"round": round_no, "topic_basis": topic_basis, "scores": scores, "checks": checks})
    for d, s in scores.items():
        print(d, {f: (m["recall"], m["same_rate"], m["false_rate"]) for f, m in s["metrics"].items()})
    print("경로:", {k: (len(p["shared"]), p["base"]) for k, p in checks["paths"].items()}, checks["complaints_linked"])
    print("키:", checks["keys"])
    print("규칙 위반:", {k: r["violations"] for k, r in checks["rules"].items()})
    print("허브:", checks["hubs"])


if __name__ == "__main__":
    if sys.argv[1] == "extract":
        asyncio.run(extract(sys.argv[2]))
    else:
        score()
