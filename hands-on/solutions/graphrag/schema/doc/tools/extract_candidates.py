"""4단계: 발견용 표본을 1건씩 SchemaFromTextExtractor에 넣어 스키마 후보를 넓게 뽑음.

examples에는 그 문서 종류의 역량 질문만 넣음(앞서 나온 이름을 다시 쓰라는 안내는 넣지 않음).
새 타입: 이름(대소문자, 띄어쓰기, 밑줄 차이를 없앤 꼴)이 문서 종류 안에서 두 번째 청크에 나올 때 셈.
멈춤: 묶음 시작 수를 본 뒤 새 타입이 연속 3건 없으면 그 묶음을 멈춤. 상한에 닿으면 멈춤.
실행: python tools/extract_candidates.py [문서종류 ...] → {doc}/output/candidates_calls.jsonl, candidates_summary.md
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from collections import Counter, defaultdict

from neo4j_graphrag.components.schema import SchemaFromTextExtractor

from common import BASE, cq_text, decisions, key, load_units, load_json, make_llm

RUN_LENGTH = 3


async def run_doc(extractor, doc: str, plan: dict, chunks: dict) -> list[dict]:
    out = BASE / doc / "output"
    out.mkdir(parents=True, exist_ok=True)
    seen = Counter()  # 이름별로 나온 청크 수(노드 타입과 관계를 따로 셈)
    calls = []
    with (out / "candidates_calls.jsonl").open("w", encoding="utf-8") as log:
        for group, g in plan["groups"].items():
            zero_run, stop = 0, "모두 봄"
            for i, cid in enumerate(g["discovery_order"]):
                if i >= g["discovery_cap"]:
                    stop = f"상한 {g['discovery_cap']}건"
                    break
                if i >= g["discovery_start"] and zero_run >= RUN_LENGTH:
                    stop = f"시작 수 뒤 연속 {RUN_LENGTH}건 새 타입 없음"
                    break
                rec = {"doc": doc, "group": group, "order": i + 1, "chunk_id": cid}
                t0 = time.time()
                try:
                    s = await extractor.run(text=chunks[cid]["text"], examples=cq_text(doc))
                    rec.update(
                        nodes=[n.label for n in s.node_types],
                        node_descriptions={n.label: n.description for n in s.node_types},
                        node_props={n.label: [p.name for p in n.properties] for n in s.node_types},
                        relationships=[r.label for r in s.relationship_types],
                        patterns=[[p.source, p.relationship, p.target] for p in s.patterns])
                    names = {("N", key(n)) for n in rec["nodes"]} | {("R", key(r)) for r in rec["relationships"]}
                    new = sorted(f"{t}:{n}" for t, n in names if seen[(t, n)] == 1)  # 이번이 두 번째 등장
                    seen.update(names)
                    rec["new_types"] = new
                    zero_run = 0 if new else zero_run + 1
                except Exception as e:  # 검증 실패 등은 사유만 남기고 넘어감. 실패 건은 새 타입 없음으로 세지 않음
                    rec["error"] = f"{type(e).__name__}: {str(e)[:300]}"
                rec["seconds"] = round(time.time() - t0, 1)
                log.write(json.dumps(rec, ensure_ascii=False) + "\n")
                log.flush()
                calls.append(rec)
                print(f"[{doc}/{group}] {i + 1}: 새 타입 {len(rec.get('new_types', []))}"
                      f"{' 오류' if 'error' in rec else ''}", flush=True)
            used = sum(1 for c in calls if c.get("group") == group and not c.get("summary"))
            calls.append({"doc": doc, "group": group, "summary": True, "used": used, "stop": stop})
    return calls


async def map_to_cq(llm, doc: str, names: list[dict]) -> dict:
    """이름 목록을 역량 질문에 비춰 '이 질문에 답할 수 있어 보이는 이름'으로 나눔(드문 이름도 포함)."""

    qs = load_json("competency_questions.json")[doc]
    prompt = ("아래 역량 질문마다, 후보 이름 목록에서 그 질문의 답을 담을 수 있어 보이는 이름을 모두 고르세요. "
              "나온 횟수가 적어도 빼지 마세요. JSON으로만 답하세요: {\"<질문 id>\": [\"이름\", ...]}\n\n<questions>\n"
              + "\n".join(f"{q['id']}: {q['question']}" for q in qs) + "\n</questions>\n\n<names>\n"
              + "\n".join(f"{n['kind']} {n['name']} (청크 {n['count']}건) 속성: {', '.join(n['props'][:12])}"
                          for n in names) + "\n</names>")
    res = await llm.ainvoke(prompt)
    return json.loads(res.content)


def summarize(doc: str, calls: list[dict], cq_map: dict) -> str:
    ok = [c for c in calls if "nodes" in c]
    node_n = Counter(n for c in ok for n in set(c["nodes"]))
    rel_n = Counter(r for c in ok for r in set(c["relationships"]))
    props = defaultdict(Counter)
    for c in ok:
        for label, ps in c["node_props"].items():
            props[label].update(ps)
    pat_n = Counter(tuple(p) for c in ok for p in {tuple(x) for x in c["patterns"]})
    lines = [f"# 스키마 후보 요약: {doc}", "",
             f"- 모델: {decisions()['input']['llm_model']}, 추출기: neo4j-graphrag `SchemaFromTextExtractor`, "
             "examples = 역량 질문만", f"- 호출 {len(ok) + sum('error' in c for c in calls)}건(성공 {len(ok)}, "
             f"실패 {sum('error' in c for c in calls)}), 노드 타입 이름 {len(node_n)}개, 관계 이름 {len(rel_n)}개", "",
             "## 묶음별 멈춤", "", "| 묶음 | 본 건수 | 멈춘 이유 |", "|---|---:|---|"]
    lines += [f"| {c['group']} | {c['used']} | {c['stop']} |" for c in calls if c.get("summary")]
    lines += ["", "## 역량 질문별로 답할 수 있어 보이는 이름(LLM 분류, 드문 이름 포함)", "",
              "| 질문 | 이름 |", "|---|---|"]
    lines += [f"| {q} | {', '.join(v)} |" for q, v in cq_map.items()]
    lines += ["", "## 노드 타입 이름별 나온 청크 수와 자주 나온 속성", "", "| 노드 타입 | 청크 수 | 속성(나온 수) |",
              "|---|---:|---|"]
    lines += [f"| {n} | {k} | {', '.join(f'{p}({c})' for p, c in props[n].most_common(8))} |"
              for n, k in node_n.most_common()]
    lines += ["", "## 관계 이름별 나온 청크 수", "", "| 관계 | 청크 수 |", "|---|---:|"]
    lines += [f"| {r} | {k} |" for r, k in rel_n.most_common()]
    lines += ["", "## 자주 나온 패턴(2건 이상)", "", "| 패턴 | 청크 수 |", "|---|---:|"]
    lines += [f"| ({s})-[{r}]->({t}) | {k} |" for (s, r, t), k in pat_n.most_common() if k >= 2]
    errs = [c for c in calls if "error" in c]
    if errs:
        lines += ["", "## 실패한 호출", ""] + [f"- {c['group']} {c['order']}번 `{c['chunk_id']}`: {c['error'][:160]}"
                                            for c in errs]
    return "\n".join(lines) + "\n"


async def main() -> None:
    plan = load_json("sample_plan.json")
    docs = sys.argv[1:] or decisions()["input"]["doc_types"]
    chunks = {c["id"]: c for c in load_units()}
    llm = make_llm()
    extractor = SchemaFromTextExtractor(llm=llm)
    for doc in docs:
        calls = await run_doc(extractor, doc, plan["docs"][doc], chunks)
        ok = [c for c in calls if "nodes" in c]
        names = []
        for kind, field in (("노드 타입", "nodes"), ("관계", "relationships")):
            n = Counter(x for c in ok for x in set(c[field]))
            for name, k in n.most_common():
                ps = Counter(p for c in ok for p in c["node_props"].get(name, [])) if field == "nodes" else Counter()
                names.append({"kind": kind, "name": name, "count": k, "props": [p for p, _ in ps.most_common()]})
        cq_map = await map_to_cq(llm, doc, names)
        (BASE / doc / "output" / "candidates_summary.md").write_text(summarize(doc, calls, cq_map), encoding="utf-8")
        print(f"[{doc}] 요약 저장, 토큰 누적 {dict(llm.usage).get('total_tokens')}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
