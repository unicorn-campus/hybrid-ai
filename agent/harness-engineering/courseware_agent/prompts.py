"""역할별 시스템 프롬프트와 출력 스키마."""
from __future__ import annotations

import json

from .config import Settings
from .pptx_builder import PATTERNS


def _obj(props: dict, required: list[str] | None = None) -> dict:
    return {
        "type": "object",
        "properties": props,
        "required": required if required is not None else list(props),
        "additionalProperties": False,
    }


STR = {"type": "string"}
STR_LIST = {"type": "array", "items": STR}

# ---------------------------------------------------------------- 리서치

RESEARCH_SCHEMA = _obj({
    "overview_md": STR,
    "key_concepts": {"type": "array", "items": _obj({"term": STR, "definition": STR})},
    "sources": {"type": "array", "items": _obj({
        "title": STR, "url": STR, "publisher": STR, "date": STR, "key_points": STR_LIST,
    })},
    "practices": STR_LIST,
    "case_studies": STR_LIST,
    "open_questions": STR_LIST,
})


def topic_brief(s: Settings) -> str:
    lines = [f"주제: {s.topic}", f"대상 학습자: {s.audience}"]
    if s.scope:
        lines.append(f"주제 범위(반드시 지킬 것): {s.scope}")
    return "\n".join(lines)


def scope_rule(s: Settings) -> str:
    if not s.scope:
        return ""
    return (f"\n\n주제 범위: {s.scope}\n"
            "이 범위를 벗어난 내용은 짧게 줄이거나 빼고, 범위의 핵심은 빠짐없이 깊게 다룬다.")


def research_system(s: Settings) -> str:
    return f"""너는 기술 교육 과정의 리서처다. 주제 '{s.topic}'에 대한 교재를 만들기 전에
웹 검색(WebSearch)과 페이지 읽기(WebFetch)로 최신·정확한 자료를 조사한다.

원칙
- 1차 자료(공식 블로그, 문서, 논문, 저자 본인의 글)를 우선한다. 최소 8개 이상의 서로 다른 출처를 확인한다.
- 실제로 열어 본 페이지의 URL만 sources에 넣는다. URL을 지어내지 않는다.
- 용어의 정의가 출처마다 다르면 그 차이를 overview_md에 적는다.
- 원문을 길게 베끼지 말고 요점을 자신의 말로 요약한다.
- 결과는 {s.language}로 작성한다(고유명사·코드·URL은 원문 유지).{scope_rule(s)}"""


def research_prompt(s: Settings) -> str:
    return f"""{topic_brief(s)}

다음을 조사해 구조화해 줘.
1. 이 주제의 정의, 등장 배경, 왜 지금 중요한지 (overview_md, 마크다운 1500자 이상)
2. 핵심 개념과 용어 정의 (key_concepts, 12개 이상)
3. 참고 출처 (sources, 8개 이상, 각 출처의 핵심 요점 포함)
4. 실무 적용 방법·모범 사례 (practices)
5. 실제 사례 (case_studies)
6. 아직 논쟁 중이거나 열려 있는 질문 (open_questions)"""


# ---------------------------------------------------------------- 기획

PLAN_SCHEMA = _obj({
    "title": STR,
    "subtitle": STR,
    "audience": STR,
    "prerequisites": STR_LIST,
    "course_outcomes": STR_LIST,
    "chapters": {"type": "array", "items": _obj({
        "id": STR,
        "title": STR,
        "summary": STR,
        "objectives": STR_LIST,
        "key_topics": STR_LIST,
        "hands_on": STR,
        "slide_count": {"type": "integer"},
    })},
})


def planner_system(s: Settings) -> str:
    return f"""너는 교육과정 설계자(instructional designer)다. 리서치 결과를 바탕으로
'{s.topic}' 교재의 전체 커리큘럼을 설계한다.

설계 원칙
- 기초 개념 → 구성 요소 → 설계·구현 → 운영·평가 → 종합 실습 순으로 난이도가 자연스럽게 올라가게 한다.
- 장 수는 {s.min_chapters}~{s.max_chapters}개. 각 장은 혼자 읽어도 이해되지만 앞 장의 개념을 이어받는다.
- 학습 목표는 '~할 수 있다' 형태의 관찰 가능한 행동으로 쓴다(장마다 3~5개).
- 모든 장에 직접 해 볼 수 있는 실습(hands_on)을 넣는다.
- id는 'ch01', 'ch02'처럼 두 자리 번호를 쓴다.
- slide_count는 10~16 사이로 정한다.
- {s.language}로 작성한다.{scope_rule(s)}"""


def planner_prompt(s: Settings, brief: str, feedback: str = "") -> str:
    extra = f"\n\n이전 기획안의 문제점(반드시 고칠 것):\n{feedback}" if feedback else ""
    return f"""{topic_brief(s)}

리서치 결과:
{brief}{extra}

위 자료로 교재 커리큘럼을 설계해 줘."""


EXTEND_SCHEMA = _obj({"chapters": PLAN_SCHEMA["properties"]["chapters"]})


def extend_prompt(plan: dict, missing: list[str], next_index: int, room: int) -> str:
    return f"""현재 커리큘럼:
{json.dumps(_plan_outline(plan), ensure_ascii=False, indent=2)}

과정 검토에서 다음 주제가 빠졌다고 지적됐다:
{_bullets(missing)}

빠진 주제를 다룰 장을 최대 {room}개 설계해 줘. 기존 장과 내용이 겹치지 않게 하고,
id는 ch{next_index:02d}부터 순서대로 붙인다. 기존 장으로 충분히 다뤄지는 주제는 장을 만들지 않는다."""


# ---------------------------------------------------------------- 집필

CHAPTER_SCHEMA = _obj({"markdown": STR, "change_log": STR})

REQUIRED_SECTIONS = ["학습 목표", "실습", "핵심 정리", "확인 문제", "참고 자료"]


def writer_system(s: Settings) -> str:
    return f"""너는 '{s.topic}' 교재의 집필자다. 대상 학습자는 {s.audience}이다.{scope_rule(s)}

문체와 형식
- {s.language}, 설명문 존댓말('~합니다'). 어려운 용어는 처음 나올 때 쉬운 말로 풀어 준다.
- 추상적인 설명 뒤에는 반드시 구체적인 예시(설정 파일, 코드, 프롬프트, 표, 다이어그램)를 붙인다.
- 다이어그램은 ```mermaid 코드 블록으로 그린다. 코드 예시는 실제로 실행·적용 가능한 수준으로 쓴다.
- 장의 첫 줄은 '# N장. 제목' 형식의 H1 하나뿐이다. 그 아래는 ##, ### 만 쓴다.

반드시 들어갈 절(## 제목에 아래 단어를 그대로 포함)
1. 학습 목표 — 기획안의 학습 목표를 그대로 옮긴다
2. (본문 절 여러 개) — 도입 사례로 '왜 필요한가'를 보여 준 뒤 개념 → 구조 → 적용 순으로 설명
3. 실습 — 준비물, 단계별 절차, 기대 결과, 확인 방법
4. 핵심 정리 — 5~8개의 요점
5. 확인 문제 — 4~6문항, 각 정답과 해설은 <details><summary>정답</summary>...</details> 안에
6. 참고 자료 — 리서치 출처 목록에 있는 URL만 쓴다. 목록에 없는 URL은 절대 만들지 않는다

분량은 본문 기준 8,000~14,000자. 사실이 불확실한 내용은 단정하지 말고 출처의 표현을 따른다.
markdown 필드에는 장 전체 마크다운만 넣는다."""


def writer_prompt(plan: dict, chapter: dict, brief: str, chapter_no: int) -> str:
    return f"""교재 전체 구성:
{json.dumps(_plan_outline(plan), ensure_ascii=False, indent=2)}

이번에 쓸 장 ({chapter_no}장):
{json.dumps(chapter, ensure_ascii=False, indent=2)}

리서치 자료(사실 근거와 참고 자료 URL은 여기서만 가져온다):
{brief}

{chapter_no}장 전체를 집필해 줘. 앞뒤 장과 겹치는 내용은 짧게 언급만 하고 해당 장을 가리킨다.
change_log에는 '초안 작성'이라고 적는다."""


def revise_prompt(kind: str, current: str, issues: list[dict], lint_errors: list[str], extra: str = "") -> str:
    issue_lines = [f"- [{i.get('severity')}] {i.get('location')}: {i.get('problem')} → {i.get('fix')}" for i in issues]
    issue_lines += [f"- [lint] {e}" for e in lint_errors]
    return f"""아래 {kind}를 검토 의견에 맞춰 고쳐 줘. 지적되지 않은 좋은 부분은 유지하고,
지적된 문제는 빠짐없이 해결한다. 결과는 고친 {kind} 전체다.
{extra}
검토 의견:
{chr(10).join(issue_lines) or '- (없음)'}

현재 {kind}:
{current}

change_log에는 무엇을 고쳤는지 3~6줄로 적는다."""


# ---------------------------------------------------------------- 검토

REVIEW_SCHEMA = _obj({
    "scores": _obj({
        "accuracy": {"type": "number"},
        "clarity": {"type": "number"},
        "structure": {"type": "number"},
        "practicality": {"type": "number"},
        "objective_coverage": {"type": "number"},
    }),
    "overall": {"type": "number"},
    "strengths": STR_LIST,
    "issues": {"type": "array", "items": _obj({
        "severity": {"type": "string", "enum": ["major", "minor"]},
        "location": STR,
        "problem": STR,
        "fix": STR,
    })},
})


def reviewer_system(s: Settings) -> str:
    return f"""너는 '{s.topic}' 교재의 엄격한 검토자(기술 감수 + 교육 설계 감수)다.
대상 학습자는 {s.audience}이다.{scope_rule(s)}
범위를 벗어난 내용이 많거나 범위의 핵심을 빠뜨리면 objective_coverage를 깎는다.

채점 기준(각 1~10점, 8점 = 바로 출간 가능한 수준)
- accuracy: 기술적 사실이 정확하고 리서치 자료와 일치하는가. 근거 없는 단정·지어낸 수치·지어낸 URL은 major
- clarity: 대상 학습자가 막힘없이 읽을 수 있는가. 용어 풀이, 예시, 문장 흐름
- structure: 절의 순서와 분량 배분, 필수 절(학습 목표/실습/핵심 정리/확인 문제/참고 자료)이 갖춰졌는가
- practicality: 예시와 실습이 실제로 따라 할 수 있는가. 코드·설정이 동작할 만한가
- objective_coverage: 기획안의 학습 목표와 핵심 주제를 모두 충분히 다루는가

issues에는 고쳐야 할 점을 구체적인 위치와 수정 방법과 함께 적는다. 출간을 막을 문제는 major,
다듬으면 좋아지는 점은 minor. overall은 다섯 점수를 종합한 점수다. 점수를 후하게 주지 않는다."""


def review_prompt(chapter: dict, markdown: str, source_urls: list[str], lint_errors: list[str]) -> str:
    return f"""기획안의 이 장 정보:
{json.dumps(chapter, ensure_ascii=False, indent=2)}

리서치에서 확인된 출처 URL(이 밖의 URL은 지어낸 것으로 간주):
{_bullets(source_urls)}

자동 점검(lint) 결과:
{_bullets(lint_errors) or '- 문제 없음'}

검토할 원고:
{markdown}"""


# ---------------------------------------------------------------- 슬라이드 (references/pptx-guide.md)

SLIDE_SPEC = _obj({
    "pattern": {"type": "string", "enum": list(PATTERNS)},
    "title": STR,
    "lead": STR,
    "items": {"type": "array", "items": _obj({"heading": STR, "text": STR})},
    "left": _obj({"header": STR, "points": STR_LIST}),
    "right": _obj({"header": STR, "points": STR_LIST}),
    "table": _obj({"label": STR, "columns": STR_LIST, "rows": {"type": "array", "items": STR_LIST}}),
    "code": _obj({"language": STR, "text": STR}),
    "side_points": STR_LIST,
    "message": STR,
    "source": STR,
    "notes": STR,
})
SLIDES_SCHEMA = _obj({"slides": {"type": "array", "items": SLIDE_SPEC}, "change_log": STR})

SLIDE_REVIEW_SCHEMA = _obj({
    "scores": _obj({
        "alignment": {"type": "number"},
        "density": {"type": "number"},
        "flow": {"type": "number"},
        "visual_clarity": {"type": "number"},
    }),
    "overall": {"type": "number"},
    "issues": REVIEW_SCHEMA["properties"]["issues"],
})

PATTERN_GUIDE = """패턴 카탈로그 (pattern 값 → 쓰는 필드와 분량)
- objectives : 학습 목표. 첫 슬라이드 고정. items 3~5개(heading=목표 문장, text=한 줄 부연 또는 빈 값)
- agenda     : 목차와 흐름(패턴 E). items 3~6개(heading=소주제, text=1~2줄)
- cards      : 개념 카드 그리드(패턴 C). items 2~6개(heading=8자 안팎, text='- ' 불릿 2~4줄, 줄당 30자 이내)
- two_column : 목적과 추진 전략(패턴 A). left.header/right.header 6자 이내, left.points 2~4개(요약),
               right.points 2~5개(번호 항목, 각 45자 이내)
- steps      : 절차와 단계. items 3~6개(heading=단계 이름, text=1~2줄)
- table      : 데이터 표(패턴 D). table.label=표 이름, columns 2~4개, rows 2~7개, 셀 25자 이내.
               side_points 0~4개(표 해석, 규칙)
- code       : 코드와 설정 예시. code.language, code.text 14줄 이내(줄당 60자 이내), side_points 2~4개(해설)
- why_how_what : 목표, 방안, 결과(패턴 B). items 정확히 3개(heading=한글 부제 예: 목표/수행 방안/핵심 결과, text=설명 1~3줄)
- summary    : 핵심 정리. items 3~8개(heading=요점 한 문장, text=빈 값 또는 한 줄)"""


def slides_system(s: Settings) -> str:
    return f"""너는 기술 강의 슬라이드의 시각 명세 작성자(pptx-spec-writer)다. 교재 한 장을 강의 슬라이드 명세(JSON)로 바꾼다.
명세는 빌더가 pptxgenjs 코드로 바꿔 16″×9″, 레이아웃 '내용_단쪽'의 PPTX를 만든다. 좌표와 디자인은 빌더가 정하니
너는 슬라이드마다 알맞은 패턴을 고르고 글을 다듬는 데 집중한다.

{PATTERN_GUIDE}

공통 규칙
- 표지와 섹션 간지는 만들지 않는다(본 덱에서 추가함). 첫 슬라이드는 objectives(제목 '학습 목표').
- 마지막 두 슬라이드는 summary(제목 '핵심 정리')와 steps(제목 '실습 안내').
- title 22자 이내 한 줄. lead는 제목 아래 한 문장 요약(45자 이내) 또는 빈 값.
- message는 슬라이드 하단 핵심 메시지 콜아웃(45자 이내) 또는 빈 값. source는 근거 출처 한 줄('출처: ...', 140자 이내) 또는 빈 값.
- notes(발표자 노트)는 모든 슬라이드에 2~4문장.
- 슬라이드 글자는 최소 14pt로 렌더링된다. 내용이 많으면 슬라이드를 나누고, 너무 적어 하단이 비지 않게 한다.
- 가운뎃점(U+00B7)을 쓰지 않는다. 뜻하는 말을 쓴다: 둘 다는 '와/과' 또는 '및', 셋 이상 나열은 쉼표,
  둘 중 하나는 '또는', 덧붙임 설명은 괄호. (코드, 파일명, 고유명사 원문은 예외)
- 교재에 코드나 설정 예시가 있으면 핵심 코드는 code 패턴 슬라이드로 옮긴다(코드 중심 장이면 2장 이상).
- 번호 배지가 붙는 항목(items, side_points, right.points)에는 '1.' 같은 번호를 직접 쓰지 않는다.
- 강조는 **굵게** 표기만 쓴다. 마크다운 제목, 이미지, mermaid, HTML은 쓰지 않는다(다이어그램은 steps, cards, table로 바꾼다).
- 패턴이 쓰지 않는 필드는 빈 문자열, 빈 배열, 빈 값 객체로 둔다.
- {s.language}로 쓰고, 교재에 없는 사실을 새로 만들지 않는다."""


def slides_prompt(chapter: dict, markdown: str) -> str:
    return f"""장 정보:
{json.dumps(chapter, ensure_ascii=False, indent=2)}

목표 슬라이드 수: {chapter.get('slide_count', 12)}장(±2)

교재 원고:
{markdown}

이 장의 강의 슬라이드 명세를 만들어 줘. change_log에는 '초안 작성'이라고 적는다."""


def slide_reviewer_system(s: Settings) -> str:
    return f"""너는 기술 강의 슬라이드 검토자다. 대상 학습자는 {s.audience}이다.
슬라이드는 명세(JSON)로 쓰였고 빌더가 PPTX로 렌더링했다. 미리보기 PNG가 있으면 Read 도구로 모든 장을 직접 열어 본다.

채점 기준(각 1~10점, 8점 = 바로 강의에 쓸 수 있는 수준)
- alignment: 교재 원고의 핵심과 학습 목표를 빠짐없이, 사실 그대로 담았는가
- density: 슬라이드 한 장의 정보량이 적절한가(빽빽하거나 텅 비지 않았는가, 하단 여백 1인치 이상은 문제)
- flow: 슬라이드 순서가 강의 흐름으로 자연스러운가, 패턴 선택이 내용에 맞는가
- visual_clarity: 미리보기에서 글이 상자 밖으로 넘치거나 겹치지 않는가, 푸터 영역(쪽 번호, 무단전재 문구)을 침범하지 않는가,
  한눈에 읽히는가, 발표자 노트가 쓸모 있는가

issues의 location에는 'N번 슬라이드'를 적고, fix에는 명세의 어느 필드를 어떻게 고칠지 적는다."""


def slide_review_prompt(chapter: dict, markdown: str, spec: dict, lint_errors: list[str], previews: list[str]) -> str:
    preview_lines = "\n".join(f"- {p}" for p in previews) or "- (미리보기 없음)"
    return f"""장 정보:
{json.dumps(chapter, ensure_ascii=False, indent=2)}

자동 점검(lint, 빌드, 붙여넣기 호환) 결과:
{_bullets(lint_errors) or '- 문제 없음'}

렌더링 미리보기 PNG(작업 폴더 기준 경로, 모두 열어 볼 것):
{preview_lines}

교재 원고:
{markdown}

검토할 슬라이드 명세:
{json.dumps(spec, ensure_ascii=False, indent=2)}"""


def revise_slides_prompt(spec: dict, issues: list[dict], lint_errors: list[str]) -> str:
    return revise_prompt("슬라이드 명세(JSON)", json.dumps(spec, ensure_ascii=False, indent=2), issues, lint_errors)


# ---------------------------------------------------------------- 과정 전체 검토

COURSE_REVIEW_SCHEMA = _obj({
    "overall": {"type": "number"},
    "summary": STR,
    "missing_topics": STR_LIST,
    "chapter_issues": {"type": "array", "items": _obj({
        "chapter_id": STR, "severity": {"type": "string", "enum": ["major", "minor"]},
        "problem": STR, "fix": STR,
    })},
})


def course_reviewer_system(s: Settings) -> str:
    return f"""너는 '{s.topic}' 교재 전체를 보는 편집장이다. 대상 학습자는 {s.audience}이다.{scope_rule(s)}
각 장의 품질은 이미 따로 검토됐다. 너는 교재 전체 차원의 문제만 본다.
- 주제를 배우는 데 꼭 필요한데 어느 장에서도 다루지 않은 주제(missing_topics). 사소한 것은 넣지 않는다
- 장 사이의 중복, 용어 불일치, 앞뒤 순서가 맞지 않는 설명(chapter_issues)
overall은 교재 전체의 완성도(1~10)다."""


def course_review_prompt(plan: dict, digests: list[str], brief_concepts: list[str]) -> str:
    return f"""커리큘럼:
{json.dumps(_plan_outline(plan), ensure_ascii=False, indent=2)}

리서치에서 정리한 핵심 개념:
{_bullets(brief_concepts)}

각 장의 요약(절 제목과 핵심 정리):
{chr(10).join(digests)}"""


# ---------------------------------------------------------------- 자기 개선(RSI)

ROLES = ["planner", "writer", "reviewer", "slides", "slide_reviewer", "improver"]

IMPROVE_SCHEMA = _obj({
    "diagnosis": STR,
    "proposals": {"type": "array", "items": _obj({
        "action": {"type": "string", "enum": ["add_prompt_rule", "remove_prompt_rule", "add_lint_rule",
                                              "remove_lint_rule", "set_config"]},
        "role": {"type": "string", "enum": ROLES + [""]},
        "rule_id": STR,
        "text": STR,
        "lint": _obj({
            "target": {"type": "string", "enum": ["text", "slides", ""]},
            "mode": {"type": "string", "enum": ["forbid", "require", ""]},
            "pattern": STR,
            "message": STR,
        }),
        "config_key": STR,
        "config_value": {"type": "number"},
        "rationale": STR,
        "expected_effect": STR,
    })},
})


def improver_system() -> str:
    return """너는 교재 제작 에이전트의 '하네스 엔지니어'다. 이 에이전트가 쓰는 자기 하네스(역할별 프롬프트 규칙,
결정적 lint 규칙, 설정값)를 실행 기록을 근거로 고쳐서 다음 작업의 품질을 올린다. 이것이 재귀적 자기 개선 루프다.

원칙
- 근거 우선: 검토에서 반복된 지적, 자주 걸린 lint, 수정 횟수가 많은 단계에서 원인을 찾는다. 한 번만 나온 문제로 규칙을 만들지 않는다.
- 예방 위치: 생성 역할(writer, slides, planner)의 규칙으로 실수를 미리 막는 것을 우선한다. 기계적으로 판별 가능한
  문제(금지 표현, 필수 문구)는 lint 규칙(정규식)으로 만든다. 판단이 필요한 기준은 검토 역할 규칙으로 만든다.
- 작게: 한 번에 1~4개만 제안한다. 규칙은 300자 이내, 구체적이고 검증 가능한 문장으로 쓴다.
- 정리: 효과가 없었거나(시험 후 롤백) 서로 충돌하는 규칙은 remove_*로 지운다.
- 재귀: 과거 제안의 채택/롤백 이력을 보고, 너 자신(role=improver)의 제안 방식도 고칠 수 있다.
- 설정 변경(set_config)은 허용 범위 안에서만, 비용과 품질의 근거가 분명할 때만 한다.
- 일반화: 하네스는 여러 주제의 교재 제작에 함께 쓰인다. 특정 주제의 용어나 사실을 규칙에 넣지 말고,
  어떤 주제에도 적용되는 작성, 검토 방식으로 일반화해서 쓴다. 한 주제에서만 나온 문제면 근거로 약하다.
- 개선할 근거가 없으면 proposals를 비운다. 그것도 좋은 결과다.

필드 사용법: 쓰지 않는 필드는 빈 문자열, config_value는 0으로 둔다.
- add_prompt_rule: role, text
- remove_prompt_rule / remove_lint_rule: rule_id
- add_lint_rule: lint.target(text=교재 본문, slides=슬라이드 글), lint.mode(forbid=패턴이 나오면 오류, require=없으면 오류),
  lint.pattern(파이썬 정규식), lint.message(작성자가 고칠 수 있게 쓴 오류 문구)
- set_config: config_key, config_value"""


def improve_prompt(harness_view: str, telemetry: str, track_record: str, config_bounds: str) -> str:
    return f"""현재 하네스:
{harness_view}

설정 허용 범위:
{config_bounds}

실행 기록 요약:
{telemetry}

과거 제안과 결과(채택/롤백):
{track_record or '- 없음'}

이 기록을 근거로 하네스 개선안을 제안해 줘."""


# ---------------------------------------------------------------- helpers

def _plan_outline(plan: dict) -> dict:
    return {
        "title": plan.get("title"),
        "chapters": [{"id": c["id"], "title": c["title"], "summary": c["summary"]} for c in plan.get("chapters", [])],
    }


def _bullets(items: list[str]) -> str:
    return "\n".join(f"- {i}" for i in items)
