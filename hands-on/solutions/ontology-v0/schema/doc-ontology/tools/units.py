"""추출 단위: 청크를 LLM에 한 번에 넣을 글 조각(단위)으로 나누는 규칙.

후보 추출(4단계), 채우기 시험(8단계), 인덱싱이 모두 이 파일의 split_chunk를 불러 같은 단위를 씀.
- regulation(약관): 조 제목 줄을 경계로 나눔. 한 청크에 조항이 4 ~ 6개 들어 있기 때문임
- benefit_guide(카드 혜택 안내): 혜택 제목 줄을 경계로 나눔. 한 청크에 혜택 항목이 1 ~ 2개 들어 있음
- consult_log(상담 기록): 청크 하나가 상담 한 건이라 그대로 씀
"""

from __future__ import annotations

import re

ARTICLE = re.compile(r"^(제\d+조(?:의\d+)?)\(([^)]*)\)\s*$")  # 예: 제10조(연회비 면제 및 계약 해지에 따른 반환)
CHAPTER = re.compile(r"^제\d+장\s")  # 예: 제3장 카드 이용과 승인 (버릴 줄)
BENEFIT = re.compile(r"^(D2-C\d{3}-B\d{2}) \| (.+)$")  # 예: D2-C035-B02 | 주말 외식 적립
CARD_HEADER = re.compile(r"^\[카드: .+\]$")  # 인덱서가 청크 첫 줄에 붙인 머리줄(버리고 메타데이터로 다시 붙임)
SEGMENT = re.compile(r"D3_S(\d{2})_([^_]+)_")  # 예: D3_S01_신규가입_상담이력_합성.txt

RULES = {
    "regulation": {
        "unit": "조항 하나",
        "heading": ARTICLE.pattern,
        "body_start": "제목 줄 바로 다음 줄부터. 본문 줄이 하나도 없는 제목(차례)은 단위로 만들지 않음",
        "drop_lines": CHAPTER.pattern,
        "no_heading_chunk": "제목 줄이 없는 청크(표지, 문서 정보, 각주)는 청크째로 한 단위",
    },
    "benefit_guide": {
        "unit": "혜택 항목 하나",
        "heading": BENEFIT.pattern,
        "body_start": "제목 줄 바로 다음 줄부터",
        "drop_lines": CARD_HEADER.pattern + " 과 첫 혜택 제목 앞의 연회비 표(범위 밖으로 승인됨)",
        "no_heading_chunk": "제목 줄이 없는 청크(표지, 적용 기준, 카드 찾아보기, 참고 자료)는 청크째로 한 단위",
    },
    "consult_log": {
        "unit": "청크 그대로(상담 한 건)",
        "heading": None,
        "body_start": None,
        "drop_lines": None,
        "no_heading_chunk": "해당 없음",
    },
}

# 머리줄 칸(version 2): header_of가 단위 앞 머리줄에 「칸: 값」으로 적는 이름.
# 9단계(finalize.py)가 실제 단위의 머리줄에 이 칸이 모두 있는지 확인한 뒤 unit_text_rules.json에 적음
HEADER_FIELDS = {
    "regulation": ["article_no", "title"],
    "benefit_guide": ["항목 ID", "항목 제목", "product_id", "card_name"],
    "consult_log": ["record_id", "consult_date", "channel", "member_pseudo_id", "product_id", "card_name", "고객군"],
}


def benefit_kind(title: str) -> str:
    """혜택 제목의 낱말로 묶음을 정함(메타데이터에 묶을 만한 필드가 없어 제목 모양으로 나눔)."""
    for word in ("할인", "적립", "캐시백"):
        if word in title:
            return word
    if "기준" in title or "한도" in title:
        return "이용 기준"
    return "그 밖"


def segment_of(source: str) -> tuple[int, str]:
    """상담 이력 파일 이름에서 고객군 번호와 이름을 읽음. 예: (1, "신규가입")"""
    found = SEGMENT.search(source)
    return int(found.group(1)), found.group(2)


def count_headings(doc_type: str, text: str) -> int:
    pattern = {"regulation": ARTICLE, "benefit_guide": BENEFIT}.get(doc_type)
    return sum(1 for line in text.split("\n") if pattern and pattern.match(line))


def _whole(chunk: dict, bundle: str, why: str) -> dict:
    return {"unit_id": chunk["id"], "chunk_ids": [chunk["id"]], "title": why, "bundle": bundle,
            "text": chunk["text"], "keys": {}}


def split_chunk(doc_type: str, chunk: dict) -> tuple[list[dict], str | None]:
    """청크 하나를 단위 목록으로 나눔. 반환값: (단위 목록, 단위가 하나도 없을 때의 이유)."""
    meta = chunk["metadata"]
    lines = chunk["text"].split("\n")
    if doc_type == "consult_log":
        number, name = segment_of(meta["source"])
        unit = _whole(chunk, f"S{number:02d} {name}", "상담 한 건")
        unit["keys"] = {"record_id": meta["record_id"], "member_pseudo_id": meta["member_pseudo_id"],
                        "consult_date": meta["consult_date"], "channel": meta["channel"],
                        "segment_code": number, "segment_name": name}
        return [unit], None

    pattern = ARTICLE if doc_type == "regulation" else BENEFIT
    starts = [i for i, line in enumerate(lines) if pattern.match(line)]
    if not starts:
        bundle = "조항 아님" if doc_type == "regulation" else "항목 아님"
        unit = _whole(chunk, lines[1] if CARD_HEADER.match(lines[0]) and len(lines) > 1 else lines[0], bundle)
        unit["bundle"], unit["title"] = bundle, unit["title"][:40]
        if doc_type == "benefit_guide" and meta.get("card_id"):
            unit["keys"] = {"card_id": meta["card_id"], "card_name": meta["card_name"]}
        return [unit], None

    units = []
    for n, start in enumerate(starts):
        end = starts[n + 1] if n + 1 < len(starts) else len(lines)
        body = [line for line in lines[start + 1:end] if not CHAPTER.match(line)]
        if not any(line.strip() for line in body):
            continue  # 제목만 이어진 차례는 본문이 없어 단위로 만들지 않음
        found = pattern.match(lines[start])
        if doc_type == "regulation":
            unit_id, title = "D1:" + found.group(1), found.group(2)
            keys, bundle = {"article_no": found.group(1), "article_title": found.group(2)}, "조항"
        else:
            unit_id, title = found.group(1), found.group(2)
            keys = {"benefit_id": found.group(1), "benefit_title": found.group(2),
                    "card_id": meta.get("card_id"), "card_name": meta.get("card_name")}
            bundle = benefit_kind(title)
        units.append({"unit_id": unit_id, "chunk_ids": [chunk["id"]], "title": title, "bundle": bundle,
                      "text": "\n".join([lines[start]] + body), "keys": keys})
    if not units:
        return [], "제목 줄만 있고 본문이 없음(차례)"
    return units, None


def header_of(doc_type: str, unit: dict, version: int = 2) -> str:
    """단위 앞에 붙이는 메타데이터 머리줄. 키 속성이 본문에 없어도 채워지게 함.

    version 1: 4단계(후보 추출)에서 쓴 머리줄
    version 2: 5단계에서 정한 머리줄. 키 속성 이름을 함께 적고, 상담 기록에는 카드상품 키와 값 목록의 고객군 이름을 더함.
               8단계 채우기 시험과 인덱싱이 씀
    """
    keys = unit["keys"]
    if version == 1:
        if doc_type == "regulation":
            return f"[문서: 개인회원 이용약관 | 조항: {keys['article_no']} {keys['article_title']}]" if keys else "[문서: 개인회원 이용약관]"
        if doc_type == "benefit_guide":
            if keys.get("benefit_id"):
                return (f"[문서: 카드 혜택 안내 | 카드 ID: {keys['card_id']} | 카드 이름: {keys['card_name']} | "
                        f"혜택 ID: {keys['benefit_id']}]")
            return "[문서: 카드 혜택 안내]"
        return (f"[문서: 상담 기록 | 상담 ID: {keys['record_id']} | 상담일: {keys['consult_date']} | "
                f"채널: {keys['channel']} | 회원 가명 ID: {keys['member_pseudo_id']} | 고객군: {keys['segment_name']}]")
    if doc_type == "regulation":
        if not keys:
            return "[문서: 개인회원 이용약관 | 조항 아님]"
        return f"[문서: 개인회원 이용약관 | article_no: {keys['article_no']} | title: {keys['article_title']}]"
    if doc_type == "benefit_guide":
        if not keys.get("benefit_id"):
            return "[문서: 카드 혜택 안내 | 혜택 항목 아님]"
        return (f"[문서: 카드 혜택 안내 | 항목 ID: {keys['benefit_id']} | 항목 제목: {keys['benefit_title']} | "
                f"product_id: {keys['card_id']} | card_name: {keys['card_name']}]")
    card_name, product_id = consult_card(unit["text"])
    return (f"[문서: 상담 기록 | record_id: {keys['record_id']} | consult_date: {keys['consult_date']} | "
            f"channel: {keys['channel']} | member_pseudo_id: {keys['member_pseudo_id']} | "
            f"product_id: {product_id or '없음'} | card_name: {card_name or '없음'} | "
            f"고객군: {segment_canonical(keys['segment_name'])}]")


def header_values(doc_type: str, unit: dict) -> dict | None:
    """머리줄 값으로 채우는 속성(공통 개념 층의 header_fill_rule). 답이 없어야 하는 단위면 None.

    반환값: {"label": 주 노드 라벨, "props": {속성: 값}, "segment": 고객군 이름 또는 None}
    """
    keys = unit["keys"]
    if doc_type == "regulation":
        if not keys:
            return None
        return {"label": "Article", "props": {"article_no": keys["article_no"], "title": keys["article_title"]}, "segment": None}
    if doc_type == "benefit_guide":
        if not keys.get("benefit_id"):
            return None
        if unit["bundle"] == "이용 기준":
            return {"label": "UsageRule", "segment": None,
                    "props": {"item_id": keys["benefit_id"], "title": keys["benefit_title"],
                              "product_id": keys["card_id"], "card_name": keys["card_name"]}}
        return {"label": "Benefit", "segment": None,
                "props": {"benefit_id": keys["benefit_id"], "name": keys["benefit_title"],
                          "product_id": keys["card_id"], "card_name": keys["card_name"]}}
    card_name, product_id = consult_card(unit["text"])
    props = {"record_id": keys["record_id"], "consult_date": keys["consult_date"], "channel": keys["channel"],
             "member_pseudo_id": keys["member_pseudo_id"]}
    if product_id:
        props.update({"product_id": product_id, "card_name": card_name})
    return {"label": "Consultation", "props": props, "segment": segment_canonical(keys["segment_name"])}


_NAME_TABLE: dict[str, str] | None = None
RECORD_SENTENCE = re.compile(r"([^\n]*?) 카드 상담(?:으로| 기록)")  # 예: ‘…’ 내용을 한빛 가족돌봄 카드 상담으로 기록하겠습니다


def card_name_table() -> dict[str, str]:
    """카드 혜택 안내 메타데이터의 카드 이름 → 카드 ID 표(64쌍). 1단계 사본에서만 읽음."""
    global _NAME_TABLE
    if _NAME_TABLE is None:
        from common import load_chunks
        _NAME_TABLE = {c["metadata"]["card_name"]: c["metadata"]["card_id"]
                       for c in load_chunks("benefit_guide") if c["metadata"].get("card_name")}
    return _NAME_TABLE


def consult_card(text: str) -> tuple[str | None, str | None]:
    """상담 본문의 기록 문장(「~ 카드 상담으로 기록」)에서 카드 이름을 찾아 상품 ID로 바꿈(동일 규칙: 바꾸는 규칙).

    기록 문장 앞부분이 끝나는 카드 이름 가운데 가장 긴 것을 고름(예: 「한빛 모아생활 플러스」가 「한빛 모아생활」보다 먼저).
    찾지 못하면 (None, None).
    """
    found = RECORD_SENTENCE.search(text)
    if not found:
        return None, None
    names = [n for n in card_name_table() if found.group(1).endswith(n)]
    if not names:
        return None, None
    name = max(names, key=len)
    return name, card_name_table()[name]


def segment_canonical(file_form: str) -> str:
    """파일 이름의 고객군(예: 신규가입)을 값 목록의 이름(예: 신규 가입)으로 바꿈(띄어쓰기만 다름)."""
    from common import BASE_DIR, read_json
    for value in read_json(BASE_DIR / "inputs/value_lists.json")["lists"]["고객군"]["values"]:
        if value["name"].replace(" ", "") == file_form.replace(" ", ""):
            return value["name"]
    return file_form
