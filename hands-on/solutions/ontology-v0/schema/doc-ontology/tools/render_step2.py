"""2단계: 역량 질문(JSON)과 건너가는 지점(JSON)을 사람이 읽는 문서로 옮김.

competency_questions.json과 crossing_points.json이 원본이고, 이 스크립트가
competency_questions.md와 review/step2.md를 만듦(같은 내용을 손으로 두 번 쓰지 않기 위함).
실행: python tools/render_step2.py
"""

from __future__ import annotations

from common import BASE_DIR, read_json

DOC_NAMES = {"regulation": "약관", "benefit_guide": "카드 혜택 안내", "consult_log": "상담 기록"}


def table(header: list[str], rows: list[list[str]]) -> str:
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(str(c) for c in row) + " |" for row in rows]
    return "\n".join(lines)


def question_rows(cq: dict) -> list[list[str]]:
    types = {t["id"]: t["pattern"] for t in cq["question_types"]}
    return [[q["id"], q["scope"], ", ".join(DOC_NAMES[d] for d in q["doc_types"]), types[q["type"]],
             q["question"], ", ".join(q["basis"])] for q in cq["questions"]]


def crossing_rows(cp: dict) -> list[list[str]]:
    rows = []
    for point in cp["crossing_points"]:
        for c in point["crossings"]:
            key = c["other_source_key"]
            key_text = f"{key['label']}.{key['property']}" if key else "없음"
            if c.get("value_list"):
                key_text += "(값 목록: " + c["value_list"] + ")"
            if c.get("key_values"):
                key_text += "(키 값 목록: " + c["key_values"] + ")"
            rows.append([point["id"], point["question"], " → ".join(point["path"]),
                         f"{c['link_kind']}({c['linked_by']})", c["doc_side"], key_text, c["note"]])
    return rows


def main() -> None:
    cq = read_json(BASE_DIR / "competency_questions.json")
    cp = read_json(BASE_DIR / "crossing_points.json")
    q_header = ["번호", "범위", "관련 문서 종류", "질문 유형", "역량 질문", "근거가 된 사용자 질문"]
    c_header = ["번호", "질문", "거치는 원천", "이어지는 것", "문서 쪽 단서", "다른 원천의 키 후보", "메모"]
    basic = table(["기본 질문", "답(초안)"], [[k, v] for k, v in cq["basic_questions"].items()])
    types = table(["유형", "질문 틀", "묶인 사용자 질문"],
                  [[t["id"], t["pattern"], ", ".join(t["user_questions"])] for t in cq["question_types"]])
    scopes = table(["범위", "뜻", "역량 질문 수"],
                   [[k, v, sum(1 for q in cq["questions"] if q["scope"] == k)] for k, v in cq["scopes"].items()])
    out_scope = table(["범위 밖으로 둔 질문", "까닭"], [[o["question"], o["reason"]] for o in cq["out_of_scope"]])
    checklist = table(["점검 항목", "결과"], [[c["item"], c["result"]] for c in cq["checklist"]])
    questions = table(q_header, question_rows(cq))
    crossings = table(c_header, crossing_rows(cp))
    remarks = "\n".join(f"- {r['about']}: {r['note']}  " for r in cp["remarks"])
    state = "확정" if cq["status"] == "approved" else "초안(승인 전)"

    (BASE_DIR / "competency_questions.md").write_text(f"""# 역량 질문과 답할 범위

- 상태: {state}
- 역량 질문: 지식 그래프가 답할 수 있어야 하는 질문 목록. 이 목록과 범위가 온톨로지의 「답할 범위」임
- 원본: `competency_questions.json`(이 문서는 `tools/render_step2.py`가 만듦)

## 기본 질문 4가지

{basic}

## 질문 유형

{types}

## 범위

{scopes}

## 역량 질문

{questions}

## 범위 밖으로 둔 질문

{out_scope}

## 건너가는 지점

{crossings}

{remarks}
""", encoding="utf-8", newline="\n")

    (BASE_DIR / "review/step2.md").write_text(f"""# 2단계 검토: 역량 질문과 건너가는 지점 `[단계 ①]`

- 승인하는 것: 기본 질문 4가지의 답, 역량 질문 {len(cq['questions'])}개와 그 범위, 범위 밖으로 둔 질문 {len(cq['out_of_scope'])}개,
  건너가는 지점 {len(cp['crossing_points'])}곳
- 승인하면 다음에 일어나는 일: 이 목록을 「답할 범위」로 확정하고, 3단계(추출 단위와 표본 계획)로 넘어감.
  4단계에서 LLM에게 넘기는 예시 질문과 8단계 시험의 채점 기준이 이 목록에서 나옴
- 온톨로지 적용(요소: 답할 범위): 여러 원천을 거치는 질문을 함께 정하고, 원천이 바뀌는 자리(건너가는 지점)를 적음.
  기존 스키마 설계의 ① 단계는 문서 종류마다 질문만 정했음. 이번에는 4절과 5절이 더해짐

## 1. 기본 질문 4가지

### 개념 설명
역량 질문을 쓰기 전에 「무엇을, 어디에 쓰려고, 누가 쓰는가」를 먼저 정함(Ontology 101의 Step 1).
용도와 쓰는 사람이 달라지면 담을 정보가 달라지기 때문임. 아래는 AI가 쓴 초안이며 틀린 곳이 있으면 고쳐 주시면 됨.

{basic}

열 뜻
- 기본 질문: 역량 질문 가이드 2절이 먼저 답하라고 한 4가지
- 답(초안): 프로젝트 자료(평가 질문, 실습 README)를 보고 AI가 쓴 답

## 2. 질문 유형

### 개념 설명
질문 유형은 사용자 질문에서 사람 이름, 카드 이름, 날짜, 금액 같은 값을 빈칸으로 바꾼 뒤 틀이 같은 것끼리 묶은 것임.
질문 유형마다 역량 질문을 1개 이상 써야 사용자가 실제로 묻는 것이 빠지지 않음.
사용자 질문은 평가 질문 25개(Q01 ~ Q25)와 실습 README의 검색 예시 1개임.

{types}

열 뜻
- 유형: 질문 유형의 번호
- 질문 틀: 값을 `{{빈칸}}`으로 바꾼 질문의 틀
- 묶인 사용자 질문: 이 틀에 해당하는 사용자 질문의 번호. Q18 ~ Q22는 문서에 답이 없는 질문임(답이 없어야 하는 시험에 씀)

## 3. 범위

### 개념 설명
범위는 그 질문에 답하려면 어디까지 봐야 하는지를 나눈 것임.
문서 하나 안에서 답하는 질문만 보고 설계하면, 여러 문서를 잇거나 다른 원천과 함께 봐야 하는 질문에 필요한 연결이 빠짐.
그래서 질문마다 범위를 적고, 뒤의 세 범위가 필요한지 사용자가 확인함.

{scopes}

열 뜻
- 범위: 답하려면 봐야 하는 넓이
- 역량 질문 수: 그 범위로 적은 역량 질문의 수
- 단위: LLM에 한 번에 넣는 글 조각(3단계에서 정함). 원천: 데이터가 나온 곳(문서 3종과 정형 DB)

## 4. 역량 질문

### 개념 설명
역량 질문은 지식 그래프가 답할 수 있어야 하는 질문임. 그래프에 무엇을 담고 무엇을 뺄지를 이 질문으로 정함.
답이 될 노드 타입(그래프의 점 종류)이나 관계(점을 잇는 선) 이름은 일부러 쓰지 않았음.
이름을 미리 쓰면 LLM이 그 이름만 따라 써서 다른 후보가 나오지 않기 때문임.

{questions}

열 뜻
- 번호: R은 약관, B는 카드 혜택 안내, C는 상담 기록의 문서 하나 범위. A는 전체 모음, M은 여러 문서 종류, X는 문서와 다른 원천
- 관련 문서 종류: 답하려면 봐야 하는 문서 종류. 4단계에서는 그 문서 종류의 질문만 LLM에 예시로 넘김
- 질문 유형: 2절의 질문 틀
- 근거가 된 사용자 질문: 이 역량 질문이 나온 사용자 질문. 「AI 제안」은 사용자 질문에 없지만 문서를 보고 AI가 보탠 것임
- 고객군: 회원을 나눈 무리(신규 가입, 장기 보유, VIP, 휴면 직전, 다중 카드, 연회비 부담)

AI 제안 3개(R4, M3, X3)는 빼도 됨. 넣은 까닭은 「근거」 칸에 적었음.

### 범위 밖으로 둔 질문

{out_scope}

열 뜻
- 범위 밖으로 둔 질문: 관련은 있지만 이번 그래프가 답하지 않기로 한 질문
- 까닭: 뺀 이유. 승인하면 이 내용은 그래프에 담지 않음

## 5. 건너가는 지점

### 개념 설명
건너가는 지점은 질문에 답하는 길에서 원천이 바뀌는 자리임. 예를 들어 「회원이 많이 쓰는 업종에 혜택을 주는 카드」는
정형 DB에서 업종을 알아낸 뒤 카드 혜택 안내로 넘어가야 답할 수 있음.
이 자리마다 두 원천이 **무엇으로** 이어지는지를 적어 둬야, 5단계에서 그 자리를 잇는 공통 개념과 규칙을 빠뜨리지 않음.
여기서는 개념 이름과 규칙을 정하지 않고 「어디서 무엇으로 이어져야 하는가」만 적음.

{crossings}

열 뜻
- 질문: 4절의 역량 질문 번호
- 거치는 원천: 답을 찾는 순서대로 적은 원천
- 이어지는 것: 같은 대상(두 원천이 같은 개체를 가리킴. 키 값으로 이음), 같은 분류 값(두 원천이 같은 분류의 값을 가짐.
  값 목록으로 이음), 같은 주제(두 문서가 같은 주제를 말함. 키도 값 목록도 없음) 가운데 하나와 괄호 안의 이어 주는 것
- 문서 쪽 단서: 문서에서 그 대상이나 값이 나타나는 곳. 괄호의 숫자는 1단계 사본에서 센 것임
- 다른 원천의 키 후보: 원천 목록 표(sources.json)에서 찾은 라벨과 속성. 키는 대상 하나를 가려내는 값임
- 메모: 5단계에서 풀어야 할 점

{remarks}

읽는 법 예시(P4): 정형 DB에서 회원의 업종별 사용액을 구함 → 「업종」 값으로 카드 혜택 안내에 건너감.
정형 DB의 업종은 정해진 8개 값이고 혜택 안내는 문장이라, 둘을 맞추는 표가 있어야 건너갈 수 있음.

## 6. 점검 체크리스트(가이드 6절)

### 개념 설명
역량 질문 가이드가 정한 7가지 점검 항목으로 초안을 스스로 점검한 결과임.
아래 두 항목은 뒤 단계(7, 8단계)에서 하는 일이라 지금은 「아직 안 함」으로 적었음.

{checklist}

열 뜻
- 점검 항목: `references/how-to-competency-question.md` 6절의 항목
- 결과: 이번 초안이 그 항목을 지켰는지와 근거

## 7. 정해 주실 것

| 번호 | 정할 것 | 추천 |
|---|---|---|
| 가 | 기본 질문 4가지의 답 | 초안 그대로 |
| 나 | 역량 질문 {len(cq['questions'])}개(AI 제안 3개를 넣을지 포함) | 모두 넣음 |
| 다 | 범위 밖으로 둔 질문 {len(cq['out_of_scope'])}개 | 그대로 뺌 |
| 라 | 건너가는 지점 {len(cp['crossing_points'])}곳 | 그대로 |
| 마 | 「여러 문서 종류」, 「전체 모음」, 「문서와 다른 원천」 범위가 이 용도에 모두 필요한지 | 모두 필요함(사용자 질문에 세 범위가 모두 있음) |

함께 볼 원본 파일
- 역량 질문: `competency_questions.md`, `competency_questions.json`
- 건너가는 지점: `crossing_points.json`
- 사용자 질문: `hands-on/solutions/eval-set-full.json`, `hands-on/solutions/ontology/README.md`
- 원천 목록 표: `sources.json`. 값 목록: `inputs/value_lists.json`, `inputs/key_values.json`
- 작성 가이드: `references/how-to-competency-question.md`
""", encoding="utf-8", newline="\n")
    print("역량 질문", len(cq["questions"]), "개, 건너가는 지점", len(cp["crossing_points"]), "곳, 상태", state)


if __name__ == "__main__":
    main()
