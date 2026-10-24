"""8단계: 시험용 표본을 스키마 초안으로 실제 추출해 역량 질문마다 채워지는지 기대 답과 맞춰 봄.

추출: LLMEntityRelationExtractor(schema = 스키마 초안) → GraphPruning(초안 밖 노드와 관계를 지움)
청크 앞에 메타데이터 머리줄(schema_spec.json의 metadata_header 칸)을 붙여 키 속성이 채워지게 함.
채점(질문마다): 답이 있는 표본에서 뽑음, 답이 없는 표본에서 잘못 뽑음, 값이 기대 답과 같음(글자 두 개씩 겹침 비율).
실행: python tools/fill_test.py {doc} [--round=N] → {doc}/output/fill_calls.jsonl, fill_report.md, fill_metrics.json
"""

from __future__ import annotations

import asyncio
import copy
import json
import re
import sys
import time
from collections import Counter

from neo4j_graphrag.components.entity_relation_extractor import LLMEntityRelationExtractor, OnError
from neo4j_graphrag.components.graph_pruning import GraphPruning
from neo4j_graphrag.components.schema import GraphSchema
from neo4j_graphrag.components.types import TextChunk, TextChunks

from common import BASE, decisions, load_units, load_json, make_llm, save_json

CONCURRENCY = 4
MATCH = 0.4  # 기대 답의 글자 두 개 묶음 중 이만큼이 뽑은 값에 있으면 "같음"


def bigrams(s: str) -> set[str]:
    s = re.sub(r"[\s\W_]+", "", str(s).lower())
    return {s[i:i + 2] for i in range(len(s) - 1)} or ({s} if s else set())


def overlap(expected: str, got: str) -> float:
    e = bigrams(expected)
    return len(e & bigrams(got)) / len(e) if e else 0.0


def head_line(md: dict, fields: list[str]) -> str:
    return " | ".join(f"{f}: {md[f]}" for f in fields if md.get(f) not in (None, "")) + "\n"


async def extract_one(sem, extractor, pruner, schema, cid, text) -> dict:
    async with sem:
        rec, t0 = {"chunk_id": cid}, time.time()
        try:
            for attempt in range(3):  # 형식 오류는 같은 입력으로 2번까지 다시 함
                try:
                    graph = await extractor.run(chunks=TextChunks(chunks=[TextChunk(text=text, index=0, uid=cid)]),
                                                schema=schema)
                    break
                except Exception:
                    if attempt == 2:
                        raise
                    rec["retries"] = attempt + 1
            pruned = (await pruner.run(graph, schema)).graph
            rec.update(raw_nodes=[n.label for n in graph.nodes], raw_rels=[r.type for r in graph.relationships],
                       nodes=[{"id": n.id, "label": n.label, "properties": n.properties} for n in pruned.nodes],
                       rels=[{"type": r.type, "start": r.start_node_id, "end": r.end_node_id,
                              "properties": r.properties} for r in pruned.relationships])
        except Exception as e:  # 한 건 실패는 기록하고 계속함
            rec["error"] = f"{type(e).__name__}: {str(e)[:300]}"
        rec["seconds"] = round(time.time() - t0, 1)
        return rec


def answer_of(rec: dict, targets: list[dict]) -> tuple[bool, str]:
    """질문에 대응한 노드 타입(속성)이나 관계가 뽑혔는지와, 비교에 쓸 값 글을 돌려줌."""

    found, values = False, []
    by_id = {n["id"]: n for n in rec.get("nodes", [])}
    for t in targets:
        if "rel" in t:
            for r in rec.get("rels", []):
                if r["type"] == t["rel"]:
                    found = True
                    end = by_id.get(r["end"], {})
                    values += [str(v) for v in end.get("properties", {}).values()] + [str(r["end"])]
        else:
            for n in rec.get("nodes", []):
                if n["label"] != t["label"]:
                    continue
                if "property" in t:
                    v = n["properties"].get(t["property"])
                    if v not in (None, "", []):
                        found = True
                        values.append(str(v))
                else:
                    found = True
                    values += [str(v) for v in n["properties"].values()]
    return found, " ".join(values)


def score(doc: str, results: list[dict], expected: dict, cq_map: dict, criteria: dict) -> dict:
    metrics, examples = {}, []
    for q, targets in cq_map.items():
        pos = neg = hit = fp = same = 0
        for rec in results:
            if "error" in rec:
                continue
            exp = expected[rec["chunk_id"]][q]["answer"]
            found, got = answer_of(rec, targets)
            if exp != "없음":
                pos += 1
                hit += found
                ok = found and overlap(exp, got) >= MATCH
                same += ok
                if not found:
                    examples.append((q, "못 뽑음", rec["chunk_id"], exp, got))
                elif not ok:
                    examples.append((q, "값 다름", rec["chunk_id"], exp, got))
            else:
                neg += 1
                fp += found
                if found:
                    examples.append((q, "잘못 뽑음", rec["chunk_id"], exp, got))
        recall = hit / pos if pos else None
        fpr = fp / neg if neg else None
        match = same / hit if hit else None
        passed = ((recall is None or recall >= criteria["recall_min"]) and (fpr is None or fpr <= criteria["fp_max"])
                  and (match is None or match >= criteria["match_min"]) and pos > 0)
        metrics[q] = {"pos": pos, "hit": hit, "neg": neg, "fp": fp, "same": same, "recall": recall, "fp_rate": fpr,
                      "match": match, "pass": passed}
    return {"metrics": metrics, "examples": examples}


def report(doc, rnd, results, sc, criteria, chunks, usage) -> str:
    qs = {q["id"]: q for q in load_json("competency_questions.json")[doc]}
    pct = lambda x: "해당 없음" if x is None else f"{x * 100:.0f}%"
    errors = [r for r in results if "error" in r]
    pruned = Counter()
    for r in results:
        if "error" not in r:
            kept = Counter(n["label"] for n in r["nodes"])
            pruned.update((Counter(r["raw_nodes"]) - kept).elements())
    lines = [f"# 채우기 시험 보고서: {doc}(라운드 {rnd})", "",
             f"- 시험용 표본 {len(results)}건(추출 실패 {len(errors)}건), 모델 {decisions()['input']['llm_model']}",
             f"- 합격 기준: 답이 있는 표본에서 뽑음 {criteria['recall_min'] * 100:.0f}% 이상, 답이 없는 표본에서 잘못 뽑음 "
             f"{criteria['fp_max'] * 100:.0f}% 이하, 뽑은 값이 기대 답과 같음 {criteria['match_min'] * 100:.0f}% 이상",
             f"- 값이 같음 판정: 기대 답 글자의 두 글자 묶음 중 {MATCH * 100:.0f}% 이상이 뽑은 값에 있음", "",
             "| 질문 | 답 있는 표본 | 뽑음 | 답 없는 표본 | 잘못 뽑음 | 값 같음(뽑은 것 중) | 판정 |",
             "|---|---:|---:|---:|---:|---:|---|"]
    for q, m in sc["metrics"].items():
        lines.append(f"| {q} {qs[q]['type']} | {m['pos']} | {m['hit']}({pct(m['recall'])}) | {m['neg']} | "
                     f"{m['fp']}({pct(m['fp_rate'])}) | {m['same']}({pct(m['match'])}) | "
                     f"{'통과' if m['pass'] else '미달'} |")
    lines += ["", f"- 가지치기(초안 밖 노드를 지움)로 지운 노드 {sum(pruned.values())}개: "
              + (", ".join(f"{k}({v})" for k, v in pruned.most_common()) or "없음"),
              f"- 토큰 합계: {usage.get('total_tokens')}", "", "## 잘못 뽑은 예", ""]
    order = {"잘못 뽑음": 0, "못 뽑음": 1, "값 다름": 2}
    for q, kind, cid, exp, got in sorted(sc["examples"], key=lambda x: (order[x[1]], x[0]))[:12]:
        lines += [f"- {q} {kind} `{cid}`", f"  - 기대 답: {exp[:160]}", f"  - 뽑은 값: {got[:160] or '(없음)'}"]
    for r in errors:
        lines.append(f"- 추출 실패 `{r['chunk_id']}`: {r['error'][:160]}")
    return "\n".join(lines) + "\n"


async def main() -> None:
    doc = sys.argv[1]
    rnd = int(next((a.split("=", 1)[1] for a in sys.argv[2:] if a.startswith("--round=")), "1"))
    spec = load_json(f"{doc}/schema_spec.json")
    draft = load_json(f"{doc}/output/schema_draft.json")
    schema = GraphSchema.model_validate(copy.deepcopy(draft))
    criteria = load_json("pass_criteria.json")
    expected = load_json(f"{doc}/expected_answers.json")["answers"]
    chunks = {c["id"]: c for c in load_units()}
    llm = make_llm(graph_safe=True)
    extractor = LLMEntityRelationExtractor(llm=llm, create_lexical_graph=False, on_error=OnError.RAISE)
    pruner, sem = GraphPruning(), asyncio.Semaphore(CONCURRENCY)
    ids = list(expected)
    tasks = [extract_one(sem, extractor, pruner, schema, cid,
                         head_line(chunks[cid]["metadata"], spec.get("metadata_header", [])) + chunks[cid]["text"])
             for cid in ids]
    results = await asyncio.gather(*tasks)
    out = BASE / doc / "output"
    with (out / "fill_calls.jsonl").open("w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    sc = score(doc, results, expected, spec["cq_map"], criteria)
    text = report(doc, rnd, results, sc, criteria, chunks, dict(llm.usage))
    (out / "fill_report.md").write_text(text, encoding="utf-8")
    (out / f"fill_report_round{rnd}.md").write_text(text, encoding="utf-8")
    save_json(f"{doc}/output/fill_metrics.json", {"round": rnd, "metrics": sc["metrics"],
                                                  "all_pass": all(m["pass"] for m in sc["metrics"].values())})
    print(text)


if __name__ == "__main__":
    asyncio.run(main())
