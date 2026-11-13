"""실행 결과 보고서(RESULT.md): 자동으로 채운 입력값, 단계별 결정, 문서 종류별 시험 지표와 Mermaid 그림을 한 파일로 모음."""

from __future__ import annotations

from pathlib import Path

from common import BASE, decisions, load_json

LAB = "C:/Users/hiond/class/design-agentic-ai/"
KO = {"regulation": "약관", "benefit_guide": "혜택 안내", "consult_log": "상담 기록"}


def rel(p: str) -> str:
    return p.replace(LAB, "")


def main() -> None:
    d = decisions()
    i = d["input"]
    plan = load_json("sample_plan.json")
    L = ["# 문서 스키마 설계 프롬프트 실행 결과", "",
         "> 프롬프트: `hybrid-ai-lab/prompts/design-kg-schema-doc.md`  ",
         "> 실행 방식: 입력값은 AI가 프로젝트에서 찾아 채움. `[승인]` 단계는 사용자 지시로 모두 자동 승인함  ",
         "> 자동 승인이므로 사람 검토를 거친 확정본이 아님. 실제 사용 전에 사람이 다시 승인해야 함", "",
         "## 1. 자동으로 채운 입력값", "", "| 입력 | 값 | 찾은 근거 |", "|---|---|---|",
         f"| 출력 기준 폴더 | `{rel(i['base_dir'])}` | 승인이 자동이라 인덱서가 아닌 verify 아래에 둠 |",
         f"| 청크 위치 파일 | `{rel(i['chunk_source'])}` | 인덱서의 활성 세대 기록 |",
         f"| 찾은 청크 파일 | `{rel(i['chunk_file'])}` | " + "; ".join(d["steps"][0]["content"]["chunk_file_reasons"][1:]) + " |",
         f"| 본문 칸 | `{i['text_field']}` | 정제 본문. `index_text`는 검색용 별칭을 덧붙인 칸이라 뺌 |",
         f"| 문서 종류 칸 | `metadata.{i['doc_type_field']}` | 값 3종: "
         + ", ".join(f"{k} {v}건" for k, v in d["steps"][0]["content"]["doc_types"].items()) + " |",
         "| 사용자 질문 출처 | " + "<br/>".join(f"`{rel(p)}`" for p in i["question_sources"])
         + " | 평가용 질문셋 2개(Q01 ~ Q22, E01 ~ E20)와 사용자 스토리 |",
         f"| 정형 데이터 그래프 스키마 | `{rel(i['structured_schema'])}` | RDB에서 만든 GraphSchema(Product, Card, Member 등) |",
         "| 기존 정답표 | " + "<br/>".join(f"`{rel(p)}`" for p in i["answer_tables"]["consult_log"])
         + " | 상담 기록만 있음. 약관과 혜택은 LLM이 기대 답 초안을 씀 |",
         f"| LLM | {i['llm_provider']} `{i['llm_model']}` | 프로젝트 공용 모델 |",
         f"| 비밀값 | `{rel(i['secret_file'])}`의 `{i['secret_key_name']}` | 값이 있는지만 확인함(값은 보지 않음) |",
         f"| 도구 판 | neo4j-graphrag {i['neo4j_graphrag_version']} | 검증 가상환경 |",
         f"| Neo4j 판 | {i['neo4j_edition']} | 컨테이너 이미지 이름 |", "",
         "- 개인정보 점검(정규식): " + ", ".join(f"{k} {v}건" for k, v in d["steps"][0]["content"]["pii_scan"].items()), "",
         "## 2. 묶음과 표본", "", "| 문서 종류 | 묶음 기준 | 묶음(청크 수) | 발견용 상한 | 시험용 |", "|---|---|---|---:|---:|"]
    for doc, p in plan["docs"].items():
        gs = p["groups"]
        L.append(f"| {KO[doc]} | {p['group_basis']} | " + ", ".join(f"{g.replace('_상담이력_합성.txt', '')}({v['chunks']})"
                                                           for g, v in gs.items())
                 + f" | {sum(v['discovery_cap'] for v in gs.values())} | {sum(len(v['test']) for v in gs.values())} |")
    L += ["", "- " + "  \n- ".join(f"{KO[k]}: {p['note']}" for k, p in plan["docs"].items()), "",
          "## 3. 문서 종류별 결과", ""]
    for doc in i["doc_types"]:
        spec = load_json(f"{doc}/schema_spec.json")
        m = load_json(f"{doc}/output/fill_metrics.json")
        summ = (BASE / doc / "output/candidates_summary.md").read_text(encoding="utf-8").splitlines()[3]
        L += [f"### 3.{i['doc_types'].index(doc) + 1} {KO[doc]}({doc})", "",
              f"- 후보: {summ.lstrip('- ')}", "", "추천표(자동 승인)", "", "| 구분 | 추천 | 근거 질문 |", "|---|---|---|"]
        L += [f"| {r['kind']} | {r['item']} | {', '.join(r['cq']) or '없음'} |" for r in spec["recommend"]]
        L += ["", "```mermaid", (BASE / doc / "output/schema.mmd").read_text(encoding="utf-8").rstrip(), "```", "",
              f"채우기 시험(마지막 라운드 {m['round']})", "",
              "| 질문 | 뽑음 | 잘못 뽑음 | 값 같음 | 판정 |", "|---|---:|---:|---:|---|"]
        pct = lambda x: "해당 없음" if x is None else f"{x * 100:.0f}%"
        for q, v in m["metrics"].items():
            L.append(f"| {q} | {v['hit']} / {v['pos']}({pct(v['recall'])}) | {v['fp']} / {v['neg']}({pct(v['fp_rate'])}) | "
                     f"{v['same']} / {v['hit']}({pct(v['match'])}) | {'통과' if v['pass'] else '미달'} |")
        final = BASE / doc / "graph_schema.json"
        L += ["", f"- 최종 파일: " + (f"`{doc}/graph_schema.json`, `{doc}/approval.json`" if final.exists()
                                     else "만들지 않음(합격 기준 미달)"), ""]
    L += ["## 4. 주의와 남은 쟁점", "",
          "- 자동 승인: 역량 질문, 묶음, 스키마 초안, 제약, 기대 답, 합격 기준, 시험 통과를 사람이 보지 않고 AI가 정함",
          "- 기대 답: 약관과 혜택은 정답표가 없어 시험에 쓰는 모델과 같은 모델이 초안을 씀. 채점이 후하게 나올 수 있음",
          "- 표본 부족: 약관 시험용 5건, 상담 18건으로 목표 30 ~ 50건보다 적음(청크 수 자체가 적음)",
          "- 상담 C1: 라운드 4는 잘못 뽑음 2 / 6으로 미달, 같은 설명의 라운드 5는 1 / 6으로 통과. 기준(20%)에 붙어 있어 "
          "다시 돌리면 바뀔 수 있음. 잘못 뽑은 문장은 고객의 실제 불편 진술이라 정답표 범위를 다시 볼 필요가 있음",
          "- 혜택 B5(카드 기본 이용 조건): 기대 답 16건이 모두 연회비나 가족카드 규칙이라 정형 스키마가 답하는 질문으로 옮김",
          "- 약관(청크 단위, 1차): 청크 하나가 조항 7 ~ 30개를 묶고 2건은 차례(목차)로 시작해 추출이 조항 목록에 쏠림. "
          "라운드 2에서 5건 모두 조항과 문서 노드만 나와 중단함. 기록은 `output/regulation-chunk-run/`",
          "- 약관(조항 단위, 2차): 표본으로 뽑힌 청크만 조항으로 나눔(검색 청크는 그대로). 시험용 30건, 발견용 17건. "
          "조건, 기한, 처리 노드가 실제로 뽑히기 시작했으나 라운드 3에서도 R2 ~ R5 미달로 중단함",
          "  - R2: 답 있는 표본이 6건뿐이라 설명을 좁히면 뽑음이, 넓히면 잘못 뽑음이 흔들림",
          "  - R4: 잘못 뽑음 16 / 21 중 다수가 '~경우 ~안내합니다' 꼴의 실제 상황별 처리 문장이라 기대 답 초안이 좁아 보임",
          "  - R5: 30건 모두 판, 시행일, 이전 판을 정확히 뽑았으나 기대 답에 'version:' 같은 이름표가 붙어 채점에서 떨어짐",
          "  - 다음 단계: 사람이 시험용 30건의 기대 답(R2 ~ R5)을 검토한 뒤 다시 시험해야 판정이 의미 있음",
          "- 도구 발견: neo4j-graphrag 1.22.0은 required 속성을 EXISTENCE 제약으로 바꿈. Community 판이 지원하지 않아 "
          "required를 모두 false로 두고 다시 시험함", "",
          "## 5. 단계별 결정 기록", "", "| 단계 | 판 | 판정자 | 일시 |", "|---|---:|---|---|"]
    L += [f"| {s['step']} | {s['rev']} | {s['judge']} | {s['date']} |" for s in d["steps"]]
    (BASE / "RESULT.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("RESULT.md 저장")


if __name__ == "__main__":
    main()
