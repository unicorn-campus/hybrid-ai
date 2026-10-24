"""오케스트레이터 워크플로우(교육용 v0).

① 세대 ID 발급 → ② 공통 단계 → ③ 인덱스 구축 → ④ 검증 → ⑤ 게시(활성 세대 파일 교체)

- 전체 재색인(full): 새 세대에 쓰므로 순서가 필요 없음. KG 구축과 검색엔진 인덱싱을 처음부터 끝까지 병렬로 돌림
- 증분 색인(incremental): 지금 쓰는 세대에 바로 써서 쓰는 순간 보임. 준비만 병렬, 반영은
  K4 ~ K6(KG에 새 청크 넣기) → S3(검색엔진 문서 교체) → K7(KG 옛 청크 지우기) → 기록 갱신 순서
- 서브 워크플로우(kg_build, search_index)는 인덱스 구축만 하고 활성 세대 파일은 바꾸지 않음
- K8 커뮤니티 요약(선택, --communities): 전체 재색인은 K4 ~ K6 뒤, 증분 색인은 K7 뒤(그래프가 완성된 뒤)에 함.
  옵션이 없으면 K8을 부르지 않고 출력도 그대로임

실행:
  python orchestrator.py full --run sample-001 --chunks data/sample-chunks.json
  python orchestrator.py incremental --run sample-002 --chunks data/sample-chunks-v2.json
  python orchestrator.py full --run sample-007 --chunks data/sample-chunks.json --full-reindex --communities
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

import neo4j

import community
import config
import kg_build
import search_index
from common import doc_id_of, load_json, log, save_json, sha256_file, sha256_text


def neo4j_password() -> str:
    """환경변수 NEO4J_PASSWORD를 먼저 쓰고, 없으면 Neo4j compose 옆 .env에서 읽음(값은 출력하지 않음)."""

    password = os.environ.get("NEO4J_PASSWORD")
    if not password and config.NEO4J_ENV_FILE.exists():
        for line in config.NEO4J_ENV_FILE.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("NEO4J_PASSWORD="):
                password = line.split("=", 1)[1].strip().strip('"').strip("'")
    if not password:
        raise SystemExit("Neo4j 비밀번호가 없음: 환경변수 NEO4J_PASSWORD나 backing-services/neo4j/.env 필요")
    return password


def neo4j_driver():
    password = neo4j_password()
    return neo4j.GraphDatabase.driver(config.NEO4J_URI, auth=(config.NEO4J_USER, password))


def own_generation(generation: str) -> bool:
    """이 저장소가 만든 세대인지 봄(gen-{GENERATION_TAG}-로 시작). 같은 DB에 다른 세대가 섞여도 v0 세대만 다루게 함."""

    return generation.startswith(f"gen-{config.GENERATION_TAG}-")


def read_active() -> dict | None:
    return load_json(config.ACTIVE_FILE) if config.ACTIVE_FILE.exists() else None


def config_signature() -> str:
    """처리 설정 지문: 스키마 파일, LLM, 임베딩, BM25 값, 토큰화 규칙과 승인 별칭이 하나라도 바뀌면 사전 검사가 생략하지 않음."""

    parts = [sha256_file(config.SCHEMA_DIR / d / "graph_schema.json") for d in config.DOC_TYPES
             if (config.SCHEMA_DIR / d / "graph_schema.json").exists()]
    parts += [config.LLM_MODEL, config.EMBED_MODEL, config.EMBED_REVISION, str(config.BM25_K1), str(config.BM25_B)]
    parts += [config.LEXICAL_RULES] + ([sha256_file(config.ALIASES_APPROVED)] if config.ALIASES_APPROVED.exists() else [])
    return sha256_text("|".join(parts))


# ---------------------------------------------------------------- K8 기록 파일

REPORTS_FILE = "community_reports.json"  # 세대 폴더의 K8 보고서 기록. {member_hash: 보고서와 임베딩}


def load_reports(*gen_dirs) -> dict:
    """앞에 준 세대 폴더부터 K8 보고서 기록을 찾아 합침. 같은 지문은 앞 폴더 것을 씀(이번 세대 > 이전 활성 세대)."""

    out: dict = {}
    for d in reversed([d for d in gen_dirs if d is not None]):
        if (d / REPORTS_FILE).exists():
            out.update(load_json(d / REPORTS_FILE))
    return out


def step3_k8(driver, generation, gen_dir, run_id, previous_dir) -> dict:
    """K8을 돌리고 이번 세대의 보고서 기록을 세대 폴더에 저장함(다음 실행이 지문이 같은 보고서를 다시 씀)."""

    result, reports = community.k8_summarize(driver, generation, run_id, load_reports(gen_dir, previous_dir))
    save_json(gen_dir / REPORTS_FILE, reports)
    return result


# ---------------------------------------------------------------- ① ~ ⑤

def step1_issue_generation(run: str, chunks_path, active: dict | None, full_reindex: bool) -> dict:
    """① 세대 ID 발급과 사전 검사. 같은 실행 이름이면 같은 세대 ID(중단돼도 같은 세대로 이어서 만듦).
    앞머리 gen-{GENERATION_TAG}-는 같은 DB에 있을 수 있는 다른 세대와 ID가 겹치지 않게 함."""

    safe = re.sub(r"[^A-Za-z0-9_.-]+", "-", run).strip("-") or "run"
    generation = f"gen-{config.GENERATION_TAG}-{safe}-{sha256_text(run)[:8]}"
    input_sha, signature = sha256_file(chunks_path), config_signature()
    skip = bool(active and not full_reindex and active["input_sha256"] == input_sha
                and active["config_signature"] == signature)
    log(f"① 세대 ID {generation}" + (" → 사전 검사: 입력과 설정이 활성 세대와 같아 할 일 없음" if skip else ""))
    return {"generation": generation, "input_sha256": input_sha, "config_signature": signature, "skip": skip}


def step2_common(chunks_path, gen_dir) -> list[dict]:
    """② 공통 단계. v0는 RAG 인덱싱 예제가 로드, 정제와 가명처리, 청킹까지 끝낸 청킹 결과 파일을 받아 이 세대에 고정함.
    (청킹 결과를 새로 만들려면 RAG 인덱싱 예제를 다시 돌린 뒤 tools/export_chroma_chunks.py를 돌림)"""

    gen_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(chunks_path, gen_dir / "prepared-chunks.json")
    chunks = load_json(gen_dir / "prepared-chunks.json")
    log(f"② 공통 단계: 청킹 결과 {len(chunks)}개를 세대 폴더에 고정")
    return chunks


def step3_build_full(chunks, generation, gen_dir, run_id, active, driver, communities: bool = False) -> dict:
    """③ 인덱스 구축(전체 재색인). 둘 다 새 세대에 쓰므로 KG 구축과 검색엔진 인덱싱을 통째로 병렬로 돌림."""

    previous_kg = None
    if active and (config.GENERATIONS / active["generation"] / "kg_prepared.json").exists():
        previous_kg = load_json(config.GENERATIONS / active["generation"] / "kg_prepared.json")
    previous_index = active["search_index"] if active else None
    index = search_index.index_name(generation)

    def kg_side():
        prepared = kg_build.prepare(chunks, previous_kg)  # K1 ~ K3
        save_json(gen_dir / "kg_prepared.json", prepared)  # 준비 결과 보관: 반영에서 실패해도 계산을 다시 하지 않음
        applied = kg_build.apply(driver, prepared, generation, run_id)  # K4 ~ K6
        if communities:  # K8: 새 세대라 K7이 없음. K6까지 끝나면 그래프가 완성됨
            previous_dir = config.GENERATIONS / active["generation"] if active else None
            applied["k8"] = step3_k8(driver, generation, gen_dir, run_id, previous_dir)
        return prepared, applied

    def search_side():
        prepared = search_index.prepare(chunks, previous_index)  # S1 ~ S2
        return prepared, search_index.apply(index, prepared)  # S3

    log("③ 인덱스 구축: KG 구축과 검색엔진 인덱싱을 병렬로 실행")
    with ThreadPoolExecutor(max_workers=2) as pool:
        kg_future, search_future = pool.submit(kg_side), pool.submit(search_side)
        kg_prepared, kg_result = kg_future.result()
        search_prepared, search_result = search_future.result()
    return {"index": index, "kg_prepared": kg_prepared, "kg": kg_result, "search": search_result,
            "tokenizer": search_prepared["tokenizer"]}


def step4_verify(chunks, generation, index, kg_prepared, driver, communities: bool = False) -> dict:
    """④ 검증. 검색엔진 chunk_id 집합 = 전체 청크 = KG 청크 노드 chunk_id 집합인지, 청크 하나에 노드가 하나인지 봄.
    추출 단위가 없거나 추출에 실패한 청크도 청크 노드는 있으므로 예외 목록이 필요 없음(엔티티만 없음)."""

    all_ids = {c["chunk_id"] for c in chunks}
    search_ids = search_index.chunk_ids(index)
    kg_list = kg_build.chunk_node_ids(driver, generation)
    kg_ids = set(kg_list)
    report = {
        "search_equal": search_ids == all_ids, "kg_equal": kg_ids == all_ids,
        "search_missing": sorted(all_ids - search_ids), "search_extra": sorted(search_ids - all_ids),
        "kg_missing": sorted(all_ids - kg_ids), "kg_extra": sorted(kg_ids - all_ids),
        "kg_duplicate_chunk_nodes": sorted({c for c in kg_list if kg_list.count(c) > 1}),
        "failed_units": kg_prepared["failed_units"]}  # 게시 조건은 아님. 엔티티가 빠진 청크를 알리는 기록
    report["ok"] = report["search_equal"] and report["kg_equal"] and not report["kg_duplicate_chunk_nodes"]
    log(f"④ 검증: {'통과' if report['ok'] else '실패'} (검색엔진 {len(search_ids)}/{len(all_ids)}, "
        f"KG 청크 노드 {len(kg_list)}개 = 고유 {len(kg_ids)}/{len(all_ids)}, 추출 실패 단위 {len(report['failed_units'])}개)")
    if communities:  # K8을 켠 실행만 커뮤니티를 확인함(끈 실행의 보고서 꼴과 로그는 그대로 둠)
        c = report["communities"] = community.verify(driver, generation)
        report["ok"] = report["ok"] and c["ok"]
        log(f"④ 검증(K8): {'통과' if c['ok'] else '실패'} (커뮤니티 {c['communities']}개, 요약 빠짐 {c['incomplete']}, "
            f"빈 묶음 {c['empty']}, 세대 밖 구성원 {c['foreign_members']})")
    return report


def step5_publish(record: dict) -> None:
    """⑤ 게시. 활성 세대 파일 하나만 바꿈(임시 파일에 쓴 뒤 바꿔 끼워 반쯤 쓴 파일이 보이지 않음)."""

    save_json(config.ACTIVE_FILE, record)
    log(f"⑤ 게시: 활성 세대 파일 → {record['generation']}")


# ---------------------------------------------------------------- 전체 재색인

def run_full(run: str, chunks_path, full_reindex: bool, communities: bool = False) -> None:
    active = read_active()
    gen = step1_issue_generation(run, chunks_path, active, full_reindex)
    if gen["skip"]:
        return
    if active and gen["generation"] == active["generation"]:  # 같은 실행 이름이면 지금 쓰는 세대에 덮어써 검색이 섞임
        raise SystemExit(f"세대 {gen['generation']}는 지금 활성 세대임: 전체 재색인은 새 실행 이름(--run)으로 해야 함")
    generation, gen_dir = gen["generation"], config.GENERATIONS / gen["generation"]
    run_id = f"{run}@{time.strftime('%Y%m%d%H%M%S')}"
    chunks = step2_common(chunks_path, gen_dir)
    with neo4j_driver() as driver:
        built = step3_build_full(chunks, generation, gen_dir, run_id, active, driver, communities)
        report = step4_verify(chunks, generation, built["index"], built["kg_prepared"], driver, communities)
    save_json(gen_dir / "build_report.json", {"run_id": run_id, "kg": built["kg"], "search": built["search"],
                                              "verify": report, "llm_usage": built["kg_prepared"]["llm_usage"]})
    if not report["ok"]:
        raise SystemExit("④ 검증 실패: 게시하지 않음(활성 세대는 그대로)")
    step5_publish({
        "generation": generation, "search_index": built["index"], "neo4j_generation": generation,
        "chunk_count": len(chunks), "input_sha256": gen["input_sha256"], "config_signature": gen["config_signature"],
        "published_at": time.strftime("%Y-%m-%d %H:%M:%S"), "runs": [run_id]})


# ---------------------------------------------------------------- 증분 색인

def _by_doc(chunks: list[dict]) -> dict[str, set[str]]:
    out = defaultdict(set)
    for c in chunks:
        out[doc_id_of(c["chunk_id"])].add(c["chunk_id"])
    return out


def run_incremental(run: str, chunks_path, communities: bool = False) -> None:
    """지금 쓰는 세대에 바뀐 문서만 반영함. 준비는 병렬, 반영은 K4 ~ K6 → S3 → K7 → 기록 갱신 순서."""

    active = read_active()
    if not active:
        raise SystemExit("활성 세대가 없음: 먼저 full을 실행")
    if not own_generation(active["generation"]):  # 증분 색인은 활성 세대에 바로 쓰므로 남의 세대면 멈춤
        raise SystemExit(f"활성 세대 {active['generation']}는 이 저장소가 만든 세대가 아님"
                         f"(gen-{config.GENERATION_TAG}-로 시작하지 않음): 먼저 full을 실행")
    generation, index = active["generation"], active["search_index"]
    gen_dir = config.GENERATIONS / generation
    run_id = f"{run}@{time.strftime('%Y%m%d%H%M%S')}"
    old_chunks, new_chunks = load_json(gen_dir / "prepared-chunks.json"), load_json(chunks_path)
    old_docs, new_docs = _by_doc(old_chunks), _by_doc(new_chunks)
    changed = sorted(d for d in new_docs if new_docs[d] != old_docs.get(d))
    removed = sorted(set(old_docs) - set(new_docs))
    log(f"증분 색인({generation}): 바뀌거나 새로 생긴 문서 {len(changed)}개, 사라진 문서 {len(removed)}개")
    if not changed and not removed:
        log("바뀐 문서가 없어 할 일 없음")
        return
    target = [c for c in new_chunks if doc_id_of(c["chunk_id"]) in set(changed)]
    old_kg = load_json(gen_dir / "kg_prepared.json")

    # 준비(병렬): 아무 데도 쓰지 않음
    with ThreadPoolExecutor(max_workers=2) as pool:
        kg_future = pool.submit(kg_build.prepare, target, old_kg)
        search_future = pool.submit(search_index.prepare, target, index, search_index.tokenizer_meta_of(index))
        kg_prepared, search_prepared = kg_future.result(), search_future.result()

    # 반영(순서): 그래프는 먼저 넣고 나중에 지움 → 바뀌는 동안에도 검색이 찾은 chunk_id가 그래프에 있음
    with neo4j_driver() as driver:
        kg_result = kg_build.apply(driver, kg_prepared, generation, run_id)  # K4 ~ K6
        search_result = search_index.apply(index, search_prepared, delete_doc_ids=removed)  # S3
        cleanup = kg_build.cleanup(driver, generation, run_id, changed + removed)  # K7
        if communities:  # K8: K7이 옛 청크와 고아 엔티티를 지운 뒤라야 묶음에 지워질 엔티티가 섞이지 않음
            kg_result["k8"] = step3_k8(driver, generation, gen_dir, run_id, None)

        # 기록 갱신: 이 세대의 청킹 결과와 준비 결과, 활성 세대 파일의 입력 지문
        touched = set(changed) | set(removed)
        merged_kg = {"chunks": [c for c in old_kg.get("chunks", []) if c["doc_id"] not in touched]
                     + kg_prepared["chunks"],
                     "units": [u for u in old_kg["units"] if u["doc_id"] not in touched] + kg_prepared["units"],
                     "no_unit_chunks": [c for c in old_kg["no_unit_chunks"] if doc_id_of(c) not in touched]
                     + kg_prepared["no_unit_chunks"],
                     "failed_units": [u["unit_id"] for u in old_kg["units"]
                                      if "error" in u and u["doc_id"] not in touched]
                     + kg_prepared["failed_units"], "llm_usage": kg_prepared["llm_usage"]}
        save_json(gen_dir / "kg_prepared.json", merged_kg)
        shutil.copyfile(chunks_path, gen_dir / "prepared-chunks.json")
        report = step4_verify(new_chunks, generation, index, merged_kg, driver, communities)  # 확인용(게시 조건 아님)
    save_json(gen_dir / f"incremental_report-{run}.json", {"run_id": run_id, "changed_docs": changed,
                                                           "removed_docs": removed, "kg": kg_result,
                                                           "search": search_result, "cleanup": cleanup,
                                                           "verify": report})
    active.update(input_sha256=sha256_file(chunks_path), chunk_count=len(new_chunks),
                  updated_at=time.strftime("%Y-%m-%d %H:%M:%S"), runs=active.get("runs", []) + [run_id])
    save_json(config.ACTIVE_FILE, active)
    log("기록 갱신: 활성 세대 파일의 입력 지문과 청크 수를 바꿈(세대는 그대로)")


def main() -> None:
    p = argparse.ArgumentParser(description="KG 구축과 검색엔진 인덱싱 오케스트레이터(교육용 v0)")
    p.add_argument("mode", choices=["full", "incremental"])
    p.add_argument("--run", required=True, help="실행 이름. 같은 이름이면 같은 세대 ID")
    p.add_argument("--chunks", default=str(config.DEFAULT_CHUNKS), help="청킹 결과 파일(prepared-chunks.json)")
    p.add_argument("--full-reindex", action="store_true", help="사전 검사를 건너뛰고 새 세대를 만듦")
    p.add_argument("--communities", action="store_true", help="K8 커뮤니티 요약을 켬(선택 단계)")
    a = p.parse_args()
    if a.mode == "full":
        run_full(a.run, a.chunks, a.full_reindex, a.communities)
    else:
        run_incremental(a.run, a.chunks, a.communities)


if __name__ == "__main__":
    main()
