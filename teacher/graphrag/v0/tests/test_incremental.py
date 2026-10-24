"""증분 색인에서 ④ 검증이 실패했을 때의 기록 처리 시험. Neo4j, 검색엔진, LLM 없이 반영 함수를 가짜로 바꿔 봄.

실패하면 청킹 결과(prepared-chunks.json)와 활성 세대 파일의 입력 지문을 갱신하지 않아야,
원인을 고친 뒤 같은 입력으로 다시 돌렸을 때 같은 문서를 다시 반영함.
"""

from __future__ import annotations

import contextlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import orchestrator  # noqa: E402
from common import load_json, save_json  # noqa: E402

GEN = "gen-hai-test-001"


def _chunk(doc, h, text):
    return {"chunk_id": f"{doc}_{h * 16}_0000", "text": text, "metadata": {"doc_type": "regulation"}}


OLD = [_chunk("docA", "a", "가"), _chunk("docB", "b", "나")]
NEW = [_chunk("docA", "a", "가"), _chunk("docB", "c", "나 고침")]  # docB만 바뀜


@pytest.fixture
def env(tmp_path, monkeypatch):
    gens, active_file = tmp_path / "generations", tmp_path / "active_generation.json"
    monkeypatch.setattr(orchestrator.config, "GENERATIONS", gens)
    monkeypatch.setattr(orchestrator.config, "ACTIVE_FILE", active_file)
    monkeypatch.setattr(orchestrator.config, "GENERATION_TAG", "hai")
    save_json(gens / GEN / "prepared-chunks.json", OLD)
    save_json(gens / GEN / "kg_prepared.json", {"chunks": [], "units": [], "no_unit_chunks": [], "failed_units": []})
    save_json(active_file, {"generation": GEN, "search_index": f"card_chunks-{GEN}", "input_sha256": "old",
                            "chunk_count": 2, "runs": ["r0"]})
    new_path = tmp_path / "new-chunks.json"
    new_path.write_text(json.dumps(NEW, ensure_ascii=False), encoding="utf-8")

    applied = []  # 반영 단계(K4 ~ K6)에 넘어온 청크
    empty_kg = {"chunks": [], "units": [], "no_unit_chunks": [], "failed_units": [], "llm_usage": {}}
    monkeypatch.setattr(orchestrator.kg_build, "prepare", lambda target, old: dict(empty_kg, chunks=[
        {"chunk_id": c["chunk_id"], "doc_id": orchestrator.doc_id_of(c["chunk_id"])} for c in target]))
    monkeypatch.setattr(orchestrator.search_index, "tokenizer_meta_of", lambda index: {})
    monkeypatch.setattr(orchestrator.search_index, "prepare", lambda target, index, meta: {"docs": target})
    monkeypatch.setattr(orchestrator.kg_build, "apply", lambda d, prep, g, r: applied.append(prep["chunks"]) or {})
    monkeypatch.setattr(orchestrator.search_index, "apply", lambda index, prep, delete_doc_ids=None: {})
    monkeypatch.setattr(orchestrator.kg_build, "cleanup", lambda d, g, r, docs: {})
    monkeypatch.setattr(orchestrator, "neo4j_driver", lambda: contextlib.nullcontext())
    return {"gen_dir": gens / GEN, "active_file": active_file, "new_path": new_path, "applied": applied}


def _verify(ok):
    report = {"ok": ok, "search_missing": [] if ok else ["docB_cccccccccccccccc_0000"], "search_extra": [],
              "kg_missing": [], "kg_extra": [], "kg_duplicate_chunk_nodes": [], "failed_units": []}
    return lambda *a, **k: report


def test_failed_verify_keeps_records_so_next_run_reapplies(env, monkeypatch):
    # 1회차: 검증 실패 → 멈추고, 청킹 결과와 입력 지문은 그대로, 보고서는 남음
    monkeypatch.setattr(orchestrator, "step4_verify", _verify(False))
    with pytest.raises(SystemExit, match="다시 실행"):
        orchestrator.run_incremental("inc-1", env["new_path"])
    assert load_json(env["gen_dir"] / "prepared-chunks.json") == OLD
    active = load_json(env["active_file"])
    assert active["input_sha256"] == "old" and active["runs"] == ["r0"]
    assert not load_json(env["gen_dir"] / "incremental_report-inc-1.json")["verify"]["ok"]
    assert [c["chunk_id"] for c in env["applied"][0]] == [NEW[1]["chunk_id"]]

    # 2회차: 원인을 고친 뒤 같은 입력 → 같은 문서(docB)를 다시 반영하고, 이번에는 기록을 갱신함
    monkeypatch.setattr(orchestrator, "step4_verify", _verify(True))
    orchestrator.run_incremental("inc-2", env["new_path"])
    assert len(env["applied"]) == 2 and env["applied"][1] == env["applied"][0]
    assert load_json(env["gen_dir"] / "prepared-chunks.json") == NEW
    active = load_json(env["active_file"])
    assert active["input_sha256"] != "old" and active["chunk_count"] == 2 and active["runs"][0] == "r0"

    # 3회차: 같은 입력 → 바뀐 문서가 없어 반영하지 않음
    orchestrator.run_incremental("inc-3", env["new_path"])
    assert len(env["applied"]) == 2
