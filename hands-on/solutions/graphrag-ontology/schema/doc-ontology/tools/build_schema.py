"""5단계 [단계 ③]: 문서 종류별 스키마 초안과 그림을 만듦.

- 뜻 한 줄은 공통 개념 층(common/output/concepts_draft.json)에만 있음. Class에 대응하는 노드 타입의 description은
  「공통 개념 층의 뜻 + 이 파일의 추출 기준(해당과 비해당)」으로 스크립트가 만듦(손으로 두 번 쓰지 않음)
- 공통 노드 타입(Topic)은 SHARED 한 곳에 적고 세 문서 종류에 같은 라벨, description, 속성, 키로 넣음
- additional_node_types, additional_relationship_types, additional_patterns는 모두 false
- required는 쓰지 않음(검증 중에 EXISTENCE 제약으로 바뀌는데 Community 판은 EXISTENCE를 지원하지 않음)
실행: python tools/build_schema.py
만드는 파일: {문서 종류}/output/schema_draft.json, schema.mmd, schema_preview.html, common/output/schema_all.mmd,
            common/output/schema_preview.html
"""

from __future__ import annotations

import html
import json

from common import BASE_DIR, DOC_TYPES, read_json, write_json

CONCEPTS = BASE_DIR / "common/output/concepts_draft.json"
DOC_NAMES = {"regulation": "약관", "benefit_guide": "카드 혜택 안내", "consult_log": "상담 기록"}


def prop(name: str, description: str, type_: str = "STRING") -> dict:
    return {"name": name, "type": type_, "description": description, "required": False}


# 공통 노드 타입: 모든 문서 종류에 같은 모양으로 넣음
SHARED = {
    "Topic": {
        "class": "주제",
        "korean": "주제",
        "criteria": "해당: 그 단위가 다루는 업무 대상을 2 ~ 8글자의 명사로 씀(예: 연회비, 본인 확인, 광고 수신, 혜택 신청, "
                    "이의신청, 결제일, 해외 결제, 카드 해지). 혜택 항목이면 그 혜택이 쓰이는 곳이나 대상을 씀(예: 외식, 대중교통, "
                    "디지털 구독, 해외 결제, 전기차 충전, 통합 한도). 단위 하나에 가장 중심 대상부터 1 ~ 3개, 많아야 3개. "
                    "비해당: 불편, 불만, 문의, 안내, 계산 같은 말, 혜택, 할인, 적립, 캐시백, 보너스처럼 너무 넓은 말, "
                    "카드 이름, 가맹점 이름, 금액, 날짜, 사람.",
        "properties": [prop("name", "주제의 대표 이름. 띄어쓰기는 낱말 사이에 한 칸. 예: 연회비, 본인 확인")],
        "key": ["name"],
    },
}

SPECS = {
    "regulation": {
        "nodes": {
            "Article": {
                "class": "조항", "korean": "조항",
                "criteria": "해당: 머리줄의 article_no 하나에 조항 노드 하나. 조항 노드에는 article_no와 title 말고도 condition과 action을 "
                            "원문 문장 그대로 반드시 채움(이 조의 내용이 그래프에 남는 곳임). 본문이 가리키는 다른 조(예: 「제10조에 따릅니다」)도 "
                            "article_no만 채운 조항 노드로 만듦. 비해당: 표지, 문서 정보, 차례, 각주, 조 안의 항(①, ②)을 따로 나눈 것.",
                "properties": [
                    prop("article_no", "조 번호. 머리줄의 article_no 값을 그대로 씀. 예: 제10조, 제16조의2"),
                    prop("title", "조 제목. 머리줄의 title 값. 예: 연회비 면제 및 계약 해지에 따른 반환"),
                    prop("condition", "반드시 채움. 이 조가 적용되는 경우나 조건을 원문 문장 그대로 옮김. "
                                      "예: 본인회원의 직전 12개월 이용금액이 3,000,000원 이상이고 다음 연회비 청구일까지 연체가 없으면. "
                                      "조건 없이 늘 적용되는 조이면 그 조가 다루는 대상을 쓴 첫 문장을 옮김"),
                    prop("action", "반드시 채움. 카드사나 회원이 하는 일과 절차를 원문 문장 그대로 1 ~ 3문장 옮김. "
                                   "예: 다음 연도의 기본 연회비를 전액 면제합니다. 결과를 알리는 방법도 여기에 씀"),
                    prop("deadline", "원문에 기한이나 알림 시점(일, 영업일, 개월, 전, 이내)이 있으면 반드시 그대로 옮김. "
                                     "예: 명세서가 게시된 날부터 45일 이내. 없으면 비움"),
                    prop("amount", "원문에 기준 금액, 비율, 횟수가 있으면 반드시 그대로 옮김. 예: 3,000,000원 이상. 없으면 비움"),
                ],
                "key": ["article_no"],
            },
            "Topic": SHARED["Topic"],
        },
        "relationships": {
            "REFERS_TO": "조항이 본문에서 따르라고 가리키는 다른 조항. 해당: 「제N조에 따릅니다」, 「제N조의 기준을 적용합니다」. 비해당: 자기 자신.",
            "ABOUT": "단위가 다루는 주제. 조항, 혜택, 불만마다 주제를 1 ~ 3개 반드시 잇는다(주제 없는 조항, 혜택, 불만을 만들지 않음). 해당: 그 단위의 중심 대상. 비해당: 지나가듯 한 번 나온 낱말.",
        },
        "patterns": [("Article", "REFERS_TO", "Article"), ("Article", "ABOUT", "Topic")],
    },
    "benefit_guide": {
        "nodes": {
            "Benefit": {
                "class": "혜택", "korean": "혜택",
                "criteria": "해당: 머리줄의 항목 ID 하나에 혜택 노드 하나. 항목 제목이 할인, 적립, 캐시백, 바우처, 보너스, 무이자 할부, 쿠폰, "
                            "제휴 서비스이면 혜택임. 비해당: 항목 제목이 이용 기준, 통합 한도, 결제 이용 한도, 포인트 운영 기준처럼 "
                            "혜택을 주지 않고 규칙만 적은 항목(UsageRule로 씀). 머리줄이 「혜택 항목 아님」이면 아무 노드도 만들지 않음.",
                "properties": [
                    prop("benefit_id", "머리줄의 항목 ID 값. 예: D2-C035-B02"),
                    prop("name", "머리줄의 항목 제목. 예: 주말 외식 적립"),
                    prop("product_id", "머리줄의 product_id 값(카드상품 키). 예: D2-C035. 본문에서 찾지 않음"),
                    prop("card_name", "머리줄의 card_name 값. 예: 한빛 일상포인트"),
                    prop("kind", "혜택 종류 한 낱말: 할인, 적립, 캐시백, 바우처, 보너스, 무이자 할부, 쿠폰, 서비스 중 하나"),
                    prop("amount", "주는 양을 원문 표현으로(비율, 금액, 횟수). 예: 대상 결제액의 1.2%를 적립함"),
                    prop("target", "혜택을 받는 가맹점, 업종, 결제 방식을 원문 표현으로. 예: 일반 음식점 업종의 매장 직접 결제. 업종 맞추기 표의 입력이 됨"),
                    prop("condition", "받으려면 채울 조건(전월 실적, 등록, 신청)을 원문 표현으로. 예: 전월 국내외 일시불, 유이자 할부 이용액 350,000원 이상"),
                    prop("limit", "이 혜택의 한도를 원문 표현으로. 예: 월 8,000원 상당까지"),
                    prop("validity", "사용 기한이나 유효기간을 원문 표현으로. 예: 발급일부터 180일. 없으면 비움"),
                    prop("payout", "지급하거나 차감하는 시점을 원문 표현으로. 예: 다음 달 18일 일반 포인트로 지급함"),
                    prop("exclusion", "혜택에서 빠지는 거래를 원문 표현으로. 예: 상품권, 선불 충전, 현금서비스, 취소 거래"),
                ],
                "key": ["benefit_id"],
            },
            "UsageRule": {
                "class": None, "korean": "이용 기준",
                "criteria": "카드상품에 걸린 이용 규칙 항목 하나(통합 한도, 결제 한도, 실적 산정, 정산 기준). 해당: 항목 제목이 이용 기준, "
                            "통합 한도, 결제 이용 한도, 포인트 운영 기준, 한도 변경인 항목. 비해당: 할인이나 적립을 주는 혜택 항목(Benefit으로 씀).",
                "properties": [
                    prop("item_id", "머리줄의 항목 ID 값. 예: D2-C055-B04"),
                    prop("title", "머리줄의 항목 제목. 예: 결제 이용 한도"),
                    prop("product_id", "머리줄의 product_id 값(카드상품 키). 본문에서 찾지 않음"),
                    prop("card_name", "머리줄의 card_name 값"),
                    prop("limit", "한도를 원문 표현으로. 예: 건별 25,000원, 월 150,000원을 기본 상한으로 함"),
                    prop("restriction", "막는 업종이나 거래, 계정 조건을 원문 표현으로. 예: 주류, 사행성 업종과 현금성 거래는 제한함"),
                ],
                "key": ["item_id"],
            },
            "Topic": SHARED["Topic"],
        },
        "relationships": {
            "ABOUT": "단위가 다루는 주제. 조항, 혜택, 불만마다 주제를 1 ~ 3개 반드시 잇는다(주제 없는 조항, 혜택, 불만을 만들지 않음). 해당: 그 단위의 중심 대상. 비해당: 지나가듯 한 번 나온 낱말.",
        },
        "patterns": [("Benefit", "ABOUT", "Topic")],
    },
    "consult_log": {
        "nodes": {
            "Consultation": {
                "class": "상담", "korean": "상담",
                "criteria": "해당: 머리줄의 record_id 하나에 상담 노드 하나. 본문이 이어진다고 말한 앞선 상담(예: 「C-20260310-018과 이어지는 기록」)도 "
                            "record_id만 채운 상담 노드로 만듦. 비해당: 상담사, 채널, 카드, 고객을 따로 만든 노드.",
                "properties": [
                    prop("record_id", "머리줄의 record_id 값. 예: C-20260314-001"),
                    prop("consult_date", "머리줄의 consult_date 값(YYYY-MM-DD)"),
                    prop("channel", "머리줄의 channel 값. 예: 앱 채팅"),
                    prop("member_pseudo_id", "머리줄의 member_pseudo_id 값(회원 가명 키). 본문의 이름이나 번호로 바꾸지 않음"),
                    prop("product_id", "머리줄의 product_id 값(카드상품 키). 「없음」이면 비움"),
                    prop("card_name", "머리줄의 card_name 값"),
                    prop("subject", "본문 [상담주제] 줄의 값. 예: 앱 인증 불편 완화"),
                    prop("progress", "고객의 일(해지, 전환, 신고, 신청, 취소, 변경)이 이 상담 끝에 어디까지 왔는지 원문 문장 그대로 옮김. "
                                     "해지, 전환, 신고, 신청, 취소, 변경, 조회처럼 고객이 하려는 일에 관한 줄만 봄. 고객이나 상담사가 그 일의 진행 단계를 "
                                     "말한 줄(예: 「아직 바꿨다고 기록하지는 마세요」, 「아직 접수하지는 않았어요」)과 상담사가 그 일의 다음 단계를 밝힌 줄"
                                     "(예: 「확인한 뒤 결과를 안내드리겠습니다」, 「~ 화면으로 안내드리겠습니다」)을 씀. 그런 줄 가운데 가장 마지막 것을 씀. "
                                     "비해당: 상담 내용을 기록에 남기는 줄(「~ 상담 기록에 정리하겠습니다」, 「앞선 기록과 연결하고」, "
                                     "「후속 안내는 ~ 남겼습니다」, 「~ 따로 기록해 주세요」). 고객의 일에 관한 줄이 없으면 비움"),
                    prop("follow_up_method", "반드시 채움. 본문 끝의 「후속 안내는 요청하신 방식(…)을 기준으로 남겼습니다」 줄의 괄호 안 값을 "
                                             "그대로 씀. 예: 오전 전화, 영업점 안내, 이메일 요약"),
                ],
                "key": ["record_id"],
            },
            "CustomerSegment": {
                "class": "고객군", "korean": "고객군",
                "criteria": "해당: 머리줄의 고객군 값 하나에 노드 하나. 값은 신규 가입, 장기 보유, VIP, 휴면 직전, 다중 카드, 연회비 부담 중 하나. "
                            "비해당: 본문에서 짐작한 고객 성향.",
                "properties": [prop("name", "머리줄의 고객군 값을 그대로 씀. 예: 신규 가입")],
                "key": ["name"],
            },
            "Complaint": {
                "class": "불만", "korean": "불만",
                "criteria": "해당: 「불편해요」, 「지쳤어요」, 「혜택이 없어요」처럼 고객이 불만이나 불편을 분명히 말한 것. 상담 하나에 0 ~ 2개. "
                            "불만마다 그 불만이 다루는 주제를 하나 이상 ABOUT로 잇는다. "
                            "비해당: 단순한 질문이나 요청, 상담사의 말, 고객이 걱정만 한 것.",
                "properties": [prop("content", "고객이 말한 불만을 한 문장으로, 원문 표현을 살려 씀. 예: 본인 확인을 끝내려 해도 같은 요청 화면으로 계속 되돌아감")],
                "key": [],
            },
            "Request": {
                "class": None, "korean": "요청",
                "criteria": "고객이 상담에서 해 달라고 한 것 하나(비교 기준, 원하는 조건, 기록 요청). 해당: 「비교해 주세요」, 「~이면 옮기겠어요」. "
                            "비해당: 불만(Complaint로 씀), 상담사의 제안.",
                "properties": [prop("content", "요청 내용을 한 문장으로, 원문 표현을 살려 씀")],
                "key": [],
            },
            "Proposal": {
                "class": None, "korean": "제안",
                "criteria": "상담사가 고객에게 권한 방법이나 대안 하나와 고객의 반응. 해당: 「~하시는 건 어떠세요?」, 「~를 안내드릴게요」. "
                            "비해당: 고객의 요청, 상담사가 사실만 알려 준 것.",
                "properties": [
                    prop("content", "상담사가 권한 말을 원문 문장 그대로 옮김"),
                    prop("accepted", "반드시 채움. 제안 바로 뒤 고객의 말로 판단함. 받아들이면 true(예: 「그렇게 해 주세요」, 「받아 볼게요」, "
                                     "「그렇게 할게요」), 거절하면 false(예: 「괜찮아요」, 「안 할래요」, 「원하지 않아요」). "
                                     "「나중에 정할게요」처럼 미룬 때만 비움", "BOOLEAN"),
                    prop("reason", "고객이 받아들이거나 거절한 까닭을 원문 표현으로. 예: 연회비 하나 때문에 생활비 관리 방식을 바꾸고 싶지 않음"),
                ],
                "key": [],
            },
            "Topic": SHARED["Topic"],
        },
        "relationships": {
            "FOLLOWS": "이 상담이 이어받은 앞선 상담. 해당: 본문이 앞선 상담 ID를 말하며 이어진다고 한 것. 비해당: 같은 회원의 다른 상담이라는 것만으로 잇지 않음.",
            "IN_SEGMENT": "상담한 회원의 고객군. 상담 하나에 정확히 하나.",
            "HAS_COMPLAINT": "상담에서 고객이 말한 불만.",
            "HAS_REQUEST": "상담에서 고객이 한 요청.",
            "HAS_PROPOSAL": "상담에서 상담사가 한 제안.",
            "ABOUT": "단위가 다루는 주제. 조항, 혜택, 불만마다 주제를 1 ~ 3개 반드시 잇는다(주제 없는 조항, 혜택, 불만을 만들지 않음). 해당: 그 단위의 중심 대상. 비해당: 지나가듯 한 번 나온 낱말.",
        },
        "patterns": [("Consultation", "FOLLOWS", "Consultation"), ("Consultation", "IN_SEGMENT", "CustomerSegment"),
                     ("Consultation", "HAS_COMPLAINT", "Complaint"), ("Consultation", "HAS_REQUEST", "Request"),
                     ("Consultation", "HAS_PROPOSAL", "Proposal"), ("Complaint", "ABOUT", "Topic")],
    },
}


def build(doc_type: str, concepts: dict) -> dict:
    definitions = {c["name"]: c["definition"] for c in concepts["classes"]}
    spec = SPECS[doc_type]
    node_types, constraints = [], []
    for label, node in spec["nodes"].items():
        prefix = definitions[node["class"]] + " " if node["class"] else ""  # 뜻은 공통 개념 층에서 가져옴
        node_types.append({"label": label, "description": f"{node['korean']}. {prefix}{node['criteria']}" if not prefix
                           else f"{prefix}{node['criteria']}", "properties": node["properties"], "additional_properties": False})
        if node["key"]:
            constraints.append({"type": "UNIQUENESS", "node_type": label, "property_names": node["key"]})
    return {
        "node_types": node_types,
        "relationship_types": [{"label": l, "description": d, "properties": [], "additional_properties": False}
                               for l, d in spec["relationships"].items()],
        "patterns": [{"source": s, "relationship": r, "target": t} for s, r, t in spec["patterns"]],
        "constraints": constraints,
        "additional_node_types": False, "additional_relationship_types": False, "additional_patterns": False,
    }


def mermaid(groups: dict[str, dict], extra_edges: list[tuple] = (), extra_nodes: dict | None = None) -> str:
    """flowchart LR. 상자에 :영문 라벨, (한글 이름), 속성. 화살표에 관계 이름."""
    lines = ["flowchart LR"]
    korean = {}
    for doc_type, schema in groups.items():
        for n in schema["node_types"]:
            korean[n["label"]] = SPECS[doc_type]["nodes"][n["label"]]["korean"]
    drawn = set()
    for doc_type, schema in groups.items():
        lines.append(f'  subgraph {doc_type}["{DOC_NAMES[doc_type]}"]')
        for n in schema["node_types"]:
            node_id = n["label"] if n["label"] not in SHARED else None
            if node_id and node_id not in drawn:
                props = "<br/>".join(p["name"] for p in n["properties"])
                lines.append(f'    {node_id}[":{n["label"]}<br/>({korean[n["label"]]})<br/>---<br/>{props}"]')
                drawn.add(node_id)
        lines.append("  end")
    for label in SHARED:
        if any(label in [n["label"] for n in s["node_types"]] for s in groups.values()):
            props = "<br/>".join(p["name"] for p in SHARED[label]["properties"])
            lines.append(f'  {label}{{{{":{label}<br/>({SHARED[label]["korean"]}, 공통)<br/>---<br/>{props}"}}}}')
    for label, (k, props) in (extra_nodes or {}).items():
        lines.append(f'  {label}[/":{label}<br/>({k}, 인덱싱이 더함)<br/>---<br/>{props}"/]')
    edges = set()
    for schema in groups.values():
        for p in schema["patterns"]:
            edges.add((p["source"], p["relationship"], p["target"], "-->"))
    for s, r, t in extra_edges:
        edges.add((s, r, t, "-.->"))
    for s, r, t, arrow in sorted(edges):
        lines.append(f"  {s} {arrow}|{r}| {t}")
    lines.append("  classDef shared fill:#fff3d6,stroke:#c98a00")
    lines.append("  class " + ",".join(SHARED) + " shared")
    return "\n".join(lines) + "\n"


def preview(title: str, diagrams: list[tuple[str, str]]) -> str:
    blocks = "\n".join(f"<h2>{html.escape(name)}</h2>\n<pre class=\"mermaid\">\n{html.escape(code)}</pre>" for name, code in diagrams)
    return f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><title>{html.escape(title)}</title>
<style>body{{font-family:Pretendard,system-ui,sans-serif;margin:24px;background:#fff;color:#222}} h2{{margin-top:32px}}
#status{{padding:8px;background:#eef;}}</style></head>
<body><h1>{html.escape(title)}</h1><div id="status">그리는 중</div>
{blocks}
<script type="module">
import mermaid from "https://cdn.jsdelivr.net/npm/mermaid@10.9.1/dist/mermaid.esm.min.mjs";
mermaid.initialize({{startOnLoad:false, flowchart:{{htmlLabels:true}}}});
try {{ await mermaid.run({{querySelector:".mermaid"}}); document.getElementById("status").textContent="그림 " + document.querySelectorAll(".mermaid svg").length + "장 그림, 오류 없음"; }}
catch (e) {{ document.getElementById("status").textContent="오류: " + e.message; }}
</script></body></html>
"""


def main() -> None:
    concepts = read_json(CONCEPTS)
    schemas = {}
    for doc_type in DOC_TYPES:
        schema = build(doc_type, concepts)
        schemas[doc_type] = schema
        out = BASE_DIR / doc_type / "output"
        write_json(out / "schema_draft.json", schema)
        extra_nodes, extra_edges = {}, []
        if doc_type == "benefit_guide":  # 인덱싱이 맞추기 표로 더하는 라벨과 관계(공통 개념 층에 적은 것)
            extra_nodes = {a["label"]: ("업종", "name") for a in concepts["indexer_adds"]["labels"]}
            extra_edges = [(r["source"], r["label"], r["target"]) for r in concepts["indexer_adds"]["relationships"]]
        code = mermaid({doc_type: schema}, extra_edges, extra_nodes)
        (out / "schema.mmd").write_text(code, encoding="utf-8", newline="\n")
        (out / "schema_preview.html").write_text(preview(f"스키마 초안: {DOC_NAMES[doc_type]}", [(DOC_NAMES[doc_type], code)]),
                                                 encoding="utf-8", newline="\n")
        print(f"{doc_type}: 노드 {len(schema['node_types'])}, 관계 {len(schema['relationship_types'])}, "
              f"패턴 {len(schema['patterns'])}, 제약 {len(schema['constraints'])}")
    adds_nodes = {a["label"]: ("업종", "name") for a in concepts["indexer_adds"]["labels"]}
    adds_edges = [(r["source"], r["label"], r["target"]) for r in concepts["indexer_adds"]["relationships"]]
    whole = mermaid(schemas, adds_edges, adds_nodes)
    common_out = BASE_DIR / "common/output"
    (common_out / "schema_all.mmd").write_text(whole, encoding="utf-8", newline="\n")
    (common_out / "schema_preview.html").write_text(
        preview("스키마 초안: 전체(공통 노드와 문서 종류별 노드)",
                [("전체", whole)] + [(DOC_NAMES[d], (BASE_DIR / d / "output/schema.mmd").read_text(encoding="utf-8")) for d in DOC_TYPES]),
        encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
