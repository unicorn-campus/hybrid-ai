"""graph_search(질문 판단, 거시 검색, 하이브리드 검색)의 시험.

LLM과 Neo4j 없이: 질문 판단의 답 해석, 근거 묶음 정리(중복 제거, 보고서 순서, 상한), 프롬프트 꼴.
Neo4j가 있으면: 활성 세대에서 하이브리드 검색과 거시 검색이 실제로 돌고, 다른 세대가 섞이지 않는지.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import graph_search as gs  # noqa: E402


class FakeLLM:
    """정해 둔 답을 차례로 돌려주는 LLM."""

    def __init__(self, replies: list[str]) -> None:
        self.replies, self.calls, self.usage = list(replies), 0, Counter()

    def chat_json(self, input: str, system_instruction: str | None = None) -> str:
        self.calls += 1
        return self.replies.pop(0)


def test_classify_reads_route_and_reason():
    llm = FakeLLM([json.dumps({"route": "Global", "reason": "여러 상담을 모아야 함"})])
    assert gs.classify(llm, "고객군별 불만 주제는?") == {"route": "global", "reason": "여러 상담을 모아야 함"}


def test_classify_retries_then_falls_back_to_hybrid():
    # 꼴이 틀린 답만 오면 정해진 횟수만큼 다시 묻고 hybrid로 둠(하이브리드도 보고서를 함께 넣어 맥락이 남음)
    llm = FakeLLM(["아님", json.dumps({"route": "other"}), "{}"])
    res = gs.classify(llm, "질문")
    assert res["route"] == "hybrid" and llm.calls == 3


def _row(eid, score, chunk_ids, community=None, neighbors=None):
    return {"id": eid, "label": "Clause", "score": score,
            "props": {"clause_no": eid, "generation": "g1", "run_id": "r1", "embedding": [0.1]},
            "neighbors": neighbors if neighbors is not None else [
                {"type": None, "outgoing": None, "label": None, "props": None}],
            "chunks": [{"chunk_id": c, "doc_type": "regulation", "text": "가" * 1000} for c in chunk_ids],
            "community": community}


def _comm(cid):
    return {"community_id": cid, "title": f"보고서 {cid}", "summary": "요약", "findings": ["사실 [근거: e1]"], "size": 4}


def test_hybrid_context_dedupes_and_ranks_reports_by_hits():
    rows = [_row("제1조", 0.90, ["k1", "k2"], _comm("A")),
            _row("제2조", 0.89, ["k2", "k3"], _comm("B")),
            _row("제3조", 0.88, ["k4"], _comm("B")),
            _row("제4조", 0.95, ["k5", "k6", "k7"], _comm("C"))]
    ctx = gs.hybrid_context(rows)
    assert [k["chunk_id"] for k in ctx["chunks"]] == ["k1", "k2", "k3", "k4", "k5"]  # 중복 없이 상한 5개
    assert all(len(k["text"]) == gs.CHUNK_CHARS for k in ctx["chunks"])  # 원문은 글자 상한으로 자름
    # 두 번 걸린 B가 먼저, 한 번씩 걸린 A와 C는 먼저 걸린 A가 먼저
    assert [c["community_id"] for c in ctx["reports"]] == ["B", "A", "C"]
    assert ctx["reports"][0]["hits"] == 2
    # 관리용 속성(embedding, generation, run_id)과 빈 이웃은 근거에 넣지 않음
    assert ctx["entities"][0]["props"] == {"clause_no": "제1조"} and ctx["entities"][0]["neighbors"] == []


def _chunk_row(cid, entities, comms):
    return {"rank": 0, "chunk_id": cid, "doc_type": "benefit_guide", "text": "원문 " + cid,
            "entities": [{"label": "Benefit", "props": {"name": n, "generation": "g1"}} for n in entities],
            "communities": comms}


def test_chunk_branch_comes_first_and_shares_report_counts():
    chunk_rows = [_chunk_row("c1", ["바우처"], [_comm("X")]), _chunk_row("c2", ["바우처", "할인"], [_comm("X"), _comm("Y")])]
    rows = [_row("제1조", 0.9, ["k1", "c1"], _comm("Y")), _row("제2조", 0.8, ["k2"], _comm("Z"))]
    ctx = gs.hybrid_context(rows, chunk_rows)
    assert [k["chunk_id"] for k in ctx["chunks"]] == ["c1", "c2", "k1", "k2"]  # 검색엔진 순위가 먼저, c1은 한 번만
    names = [e["props"].get("name") or e["props"].get("clause_no") for e in ctx["entities"]]
    assert names == ["바우처", "할인", "제1조", "제2조"]  # 같은 엔티티는 한 번만
    assert ctx["entities"][0]["from"] == "청크 c1" and ctx["entities"][2]["from"] == "엔티티 벡터"
    # X: 청크 두 개에서 2번, Y: 청크와 엔티티 갈래에서 2번(X가 먼저 걸림), Z: 1번
    assert [(c["community_id"], c["hits"]) for c in ctx["reports"]] == [("X", 2), ("Y", 2), ("Z", 1)]


def test_rrf_merges_rankings():
    # 두 목록 모두 위쪽에 있는 b가 1위, 한쪽에만 1위인 a와 d는 그다음(같으면 먼저 나온 a)
    assert gs.rrf(["a", "b", "c"], ["d", "b", "c"]) == ["b", "c", "a", "d"]


def test_local_mode_drops_reports():
    ctx = gs.hybrid_context([_row("제1조", 0.9, ["k1"], _comm("A"))], [_chunk_row("c1", ["x"], [_comm("B")])],
                            with_reports=False)
    assert ctx["reports"] == [] and len(ctx["chunks"]) == 2


def test_prompts_keep_facts_and_context_apart():
    ctx = gs.hybrid_context([_row("제1조", 0.9, ["k1"], _comm("A"), neighbors=[
        {"type": "SETS_DEADLINE", "outgoing": True, "label": "Deadline", "props": {"description": "7일", "run_id": "r"}}])])
    p = gs.hybrid_prompt("철회 기한은?", ctx)
    assert "사실 근거 1." in p and "사실 근거 2." in p and "맥락 근거." in p
    assert "→SETS_DEADLINE Deadline" in p and "run_id" not in p
    assert "[원문 k1]" in p and "[보고서] 보고서 A" in p
    assert "(찾은 보고서 없음)" in gs.global_prompt("질문", [])


def test_queries_follow_chunks_and_communities():
    assert "FROM_CHUNK" in gs.HYBRID_QUERY and "IN_COMMUNITY" in gs.HYBRID_QUERY
    assert "$max_neighbors" in gs.HYBRID_QUERY and "node.summary" in gs.GLOBAL_QUERY
    # 1-hop 이웃은 질문 벡터와 비슷한 순으로 정렬한 뒤 잘라야 함(정렬 없이 자르면 아무 6개가 남음)
    assert "vector.similarity.cosine(n.embedding, $query_vector)" in gs.HYBRID_QUERY
    assert gs.HYBRID_QUERY.index("ORDER BY sim DESC") < gs.HYBRID_QUERY.index("[..$max_neighbors]")
    assert "(e:__Entity__)-[:FROM_CHUNK]->(k)" in gs.CHUNK_QUERY and "IN_COMMUNITY" in gs.CHUNK_QUERY


def test_search_on_active_generation():
    # 실제 Neo4j에서 활성 세대로 돎(LLM은 부르지 않음). Neo4j나 활성 세대가 없으면 건너뜀
    import pytest

    import config
    from common import embed, load_json
    from orchestrator import neo4j_driver

    if not config.ACTIVE_FILE.exists():
        pytest.skip("활성 세대 없음")
    g = load_json(config.ACTIVE_FILE)["generation"]
    try:
        driver = neo4j_driver()
        driver.verify_connectivity()
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"Neo4j에 접속할 수 없음: {e}")
    q = "고객이 광고 알림 때문에 불편하다고 한 상담"
    vec = embed([q])[0]
    with driver:
        rows = gs.hybrid_search(driver, g, vec)
        reports = gs.global_search(driver, g, vec)
        ids = gs.chunk_search(load_json(config.ACTIVE_FILE)["search_index"], q, vec)
        chunk_rows = gs.chunk_graph(driver, g, ids)
        gens = {r["generation"] for r in driver.execute_query(
            "UNWIND $ids AS i MATCH (e) WHERE elementId(e) = i RETURN e.generation AS generation",
            ids=[r["id"] for r in rows]).records}
    assert len(rows) == gs.HYBRID_TOP_K and gens == {g}  # 활성 세대 엔티티만
    assert any(r["community"] for r in rows)  # 찾은 엔티티 가운데 커뮤니티 보고서와 이어진 것이 있음
    for r in rows:  # 이웃은 질문과 비슷한 순(유사도 내림차순)이고 상한을 넘지 않음
        sims = [n["sim"] for n in r["neighbors"] if n.get("type")]
        assert sims == sorted(sims, reverse=True) and len(r["neighbors"]) <= gs.MAX_NEIGHBORS
    assert len(reports) == gs.GLOBAL_TOP_K and all(r["summary"] for r in reports)
    # 청크 갈래: 검색엔진이 찾은 청크가 순위대로 그래프에 있고, 그 청크의 엔티티를 거쳐 보고서까지 이어짐
    assert [r["chunk_id"] for r in chunk_rows] == ids and len(ids) == gs.CHUNK_TOP_K
    assert any(r["entities"] for r in chunk_rows) and any(r["communities"] for r in chunk_rows)
