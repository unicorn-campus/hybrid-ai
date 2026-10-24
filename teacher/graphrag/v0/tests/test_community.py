"""K8 커뮤니티 요약의 단위 시험. Neo4j와 LLM 없이 묶음 결정성, 보고서 재사용, 옵션을 껐을 때 무변화를 봄."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import community  # noqa: E402
import orchestrator  # noqa: E402


def _entities(n: int) -> list[dict]:
    es = [{"id": f"x{i}", "label": "Clause", "props": {"clause_no": f"제{i}조", "generation": "g1", "run_id": "r1"}}
          for i in range(n)]
    for e in es:
        e["key"] = community.entity_key(e["label"], e["props"])
    return sorted(es, key=lambda e: e["key"])


def test_entity_key_ignores_management_props():
    # 세대와 실행이 바뀌어도 같은 엔티티면 같은 키여야 보고서를 다시 쓸 수 있음
    a = community.entity_key("Clause", {"clause_no": "제1조", "generation": "g1", "run_id": "r1", "embedding": [1.0]})
    b = community.entity_key("Clause", {"clause_no": "제1조", "generation": "g2", "run_id": "r9"})
    assert a == b


def test_group_orders_by_members_not_by_gds_ids():
    # GDS 묶음 번호가 달라도 구성원이 같으면 같은 출력이어야 함
    assert community.group({0: 7, 1: 7, 2: 3, 3: 3}) == community.group({0: 1, 1: 1, 2: 9, 3: 9}) == [[0, 1], [2, 3]]


def test_detect_with_gds_is_deterministic_and_splits_two_cliques():
    # 실제 Neo4j GDS로 시험함. 시험용 세대의 엔티티 6개를 만들고 끝나면 지움(다른 세대는 건드리지 않음)
    import neo4j
    import pytest

    try:
        drv = neo4j.GraphDatabase.driver(orchestrator.config.NEO4J_URI,
                                         auth=(orchestrator.config.NEO4J_USER, orchestrator.neo4j_password()))
        drv.verify_connectivity()
    except Exception as e:  # Neo4j가 꺼져 있으면 이 시험만 건너뜀
        pytest.skip(f"Neo4j 접속 안 됨: {type(e).__name__}")
    g = "test-k8-unit"
    with drv:
        drv.execute_query("MATCH (n {generation: $g}) DETACH DELETE n", g=g)
        rec, _, _ = drv.execute_query(
            "UNWIND range(0, 5) AS i CREATE (n:__Entity__:Clause {generation: $g, clause_no: '제' + i + '조'}) "
            "RETURN elementId(n) AS id ORDER BY n.clause_no", g=g)
        es = [{"id": r["id"], "label": "Clause", "props": {}, "key": str(k)} for k, r in enumerate(rec)]
        rel = [(0, 1, "R"), (1, 2, "R"), (0, 2, "R"), (3, 4, "R"), (4, 5, "R"), (3, 5, "R"), (2, 3, "R")]
        try:
            first = community.detect(drv, g, "r1", es, rel)
            again = community.detect(drv, g, "r2", es, list(reversed(rel)))  # 관계 순서가 달라도 같은 묶음
        finally:
            drv.execute_query("MATCH (n {generation: $g}) DETACH DELETE n", g=g)
    assert first == again == [[0, 1, 2], [3, 4, 5]]


def test_member_hash_changes_only_when_members_or_inner_relations_change():
    es = _entities(4)
    rel = [(0, 1, "R"), (1, 2, "R")]
    h = community.member_hash(es, [0, 1, 2], rel)
    assert h == community.member_hash(es, [0, 1, 2], list(rel))
    assert h != community.member_hash(es, [0, 1, 2], [(0, 1, "R")])  # 묶음 안 관계가 바뀜
    assert h == community.member_hash(es, [0, 1, 2], rel + [(2, 3, "R")])  # 묶음 밖으로 가는 관계는 상관없음


def test_load_reports_prefers_current_generation(tmp_path):
    cur, prev = tmp_path / "cur", tmp_path / "prev"
    cur.mkdir(), prev.mkdir()
    (prev / orchestrator.REPORTS_FILE).write_text(json.dumps({"h1": {"title": "옛"}, "h2": {"title": "둘"}}), "utf-8")
    (cur / orchestrator.REPORTS_FILE).write_text(json.dumps({"h1": {"title": "새"}}), "utf-8")
    got = orchestrator.load_reports(cur, prev)
    assert got["h1"]["title"] == "새" and got["h2"]["title"] == "둘"
    assert orchestrator.load_reports(tmp_path / "없음", None) == {}


def test_k8_reuses_cached_reports_without_llm(monkeypatch):
    # 지문이 기록에 있으면 LLM과 임베딩을 부르지 않고 그대로 씀
    es = _entities(3)
    rel = [(0, 1, "R"), (1, 2, "R"), (0, 2, "R")]
    h = community.member_hash(es, [0, 1, 2], rel)
    cache = {h: {"title": "t", "summary": "s", "findings": ["f"], "embedding": [0.0] * 768}}
    monkeypatch.setattr(community, "read_entity_graph", lambda d, g: (es, rel))
    monkeypatch.setattr(community, "detect", lambda d, g, r, e, rl: [[0, 1, 2]])

    class NoLLM:
        usage = {}

        def chat_json(self, *a, **k):
            raise AssertionError("LLM을 부르면 안 됨")

    monkeypatch.setattr(community, "make_llm", lambda: NoLLM())
    monkeypatch.setattr(community, "embed", lambda texts: [] if not texts else (_ for _ in ()).throw(AssertionError()))

    class FakeDriver:
        def __init__(self):
            self.queries = []

        def execute_query(self, q, **kw):
            self.queries.append((q, kw))
            return [], None, None

    drv = FakeDriver()
    result, reports = community.k8_summarize(drv, "g1", "r1", cache)
    assert result["llm_calls"] == 0 and result["reused"] == 1 and reports[h]["title"] == "t"
    assert any("CREATE (c:Community" in q for q, _ in drv.queries)


def test_option_off_never_calls_k8(monkeypatch):
    # 옵션을 끄면 K8을 부르지 않고 검증 보고서에도 communities 칸이 생기지 않아야 함
    called = []
    monkeypatch.setattr(orchestrator.community, "k8_summarize", lambda *a, **k: called.append(1))
    monkeypatch.setattr(orchestrator.community, "verify", lambda *a, **k: called.append(2))
    monkeypatch.setattr(orchestrator.search_index, "chunk_ids", lambda index: {"c1"})
    monkeypatch.setattr(orchestrator.kg_build, "chunk_node_ids", lambda driver, g: ["c1"])
    report = orchestrator.step4_verify([{"chunk_id": "c1"}], "g1", "idx", {"failed_units": []}, None)
    assert report["ok"] and "communities" not in report and called == []


def test_plain_removes_entity_refs_only():
    # 입력용 엔티티 번호는 지우고, 낱말 안의 e나 다른 글은 그대로 둠
    assert community._plain("조항(e1~e7)을 포함한다(e13).") == "조항을 포함한다."
    assert community._plain("e-mail 안내") == "e-mail 안내"
