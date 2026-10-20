"""외부 모델에 보낼 질문과 결과에서 식별자를 제거합니다."""
import re
from collections.abc import Mapping
from datetime import date, datetime
from decimal import Decimal

PRIVATE_KEYS = {"member_id", "card_id", "counselor_id", "consultation_id", "requester_id",
                "회원id", "카드id", "상담사id", "상담id"}


def redact_text(text: str, identifiers=()) -> str:
    # 문자열 길이가 큰 순으로 정렬하고, 각 식별자(identifier)를 제거함 
    """ 
    identifiers = ["M-123", "M-12345"]
    text = "회원 M-12345의 정보를 조회합니다."
    
    위의 예에서 M-123을 제거하면 '45'가 일부 남는 문제를 방지하기 위함
    """
    for identifier in sorted(set(str(value) for value in identifiers if value), key=len, reverse=True):
        text = text.replace(identifier, "[식별자 제거]")
    
    # 식별자 포맷을 찾아 제거      
    text = re.sub(r"(?i)\b(?:M|C|CS|CONSULT|COUNSELOR|AGENT)[-_][A-Z0-9_-]+\b", "[식별자 제거]", text)
    
    # 대체 카드번호 제거: 논리 view에는 실제 카드번호를 'CARD-{일련번호}'형식으로 대체함 
    text = re.sub(r"(?i)\bCARD-[A-Z0-9_-]+\b", "[식별자 제거]", text)
    
    text = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "[이메일 제거]", text)
    text = re.sub(r"\b\d{6}[- ]?[1-4]\d{6}\b", "[주민번호 앞 7자리 제거]", text)
    text = re.sub(r"\b01[016789][- ]?\d{3,4}[- ]?\d{4}\b", "[전화번호 제거]", text)
    text = re.sub(r"\b\d{4}[- ]\d{4}[- ]\d{4}[- ]\d{4}\b", "[카드번호 제거]", text)
    text = re.sub(r"\b\d{16}\b", "[카드번호 제거]", text)
    return text


def safe_context(value, identifiers=()):
    """ID 필드와 그 값이 다른 문자열에 등장하는 경우를 모두 제거합니다."""
    known = set(identifiers)

    def collect(item):
        if isinstance(item, Mapping):
            for key, child in item.items():
                if str(key).lower() in PRIVATE_KEYS and isinstance(child, str):
                    known.add(child)
                collect(child)
        elif isinstance(item, (list, tuple)):
            for child in item:
                collect(child)

    def clean(item):
        if isinstance(item, Mapping):
            return {str(key): clean(child) for key, child in item.items()
                    if str(key).lower() not in PRIVATE_KEYS}
        if isinstance(item, (list, tuple)):
            return [clean(child) for child in item]
        if isinstance(item, str):
            return redact_text(item, known)
        if isinstance(item, (date, datetime)):
            return item.isoformat()
        if isinstance(item, Decimal):
            return str(item)
        return item

    collect(value)
    return clean(value)
