"""고객 정형 조회에서 공유하는 식별자와 기준시점 규칙."""

from calendar import monthrange
from datetime import date, timedelta
import re


MEMBER_ID_PATTERN = re.compile(r"^M-[0-9]{1,20}$")
USAGE_MONTHS = 6


def validate_member_id(member_id: str) -> str:
    """저장소를 직접 호출해도 회원 범위가 넓어지지 않게 형식을 확인함."""

    if not isinstance(member_id, str) or not MEMBER_ID_PATTERN.fullmatch(member_id):
        raise ValueError("회원ID 형식이 올바르지 않습니다.")
    return member_id


def validate_requested_date(
    base_date: date,
    data_base_date: date,
    join_date: date,
    coverage_start: date | None = None,
) -> date:
    """데이터 기준일 이후 및 가입 전 조회를 명시적으로 거부함."""

    if type(base_date) is not date:
        raise ValueError("기준일은 날짜여야 합니다.")
    if base_date > data_base_date:
        raise ValueError("데이터 기준일 이후의 고객 현황은 조회할 수 없습니다.")
    if coverage_start is not None and base_date < coverage_start:
        raise ValueError("거래 데이터 제공 기간 이전의 고객 현황은 조회할 수 없습니다.")
    if base_date < join_date:
        raise ValueError("가입일 전 고객 현황은 조회할 수 없습니다.")
    return base_date


def month_end(value: date) -> date:
    """주어진 날짜가 속한 달의 마지막 날짜를 반환함."""

    return value.replace(day=monthrange(value.year, value.month)[1])


def latest_completed_month_end(base_date: date) -> date:
    """월중 조회에서 아직 끝나지 않은 월의 연체 지표 사용을 막음."""

    if base_date == month_end(base_date):
        return base_date
    return base_date.replace(day=1) - timedelta(days=1)


def shift_month(value: date, months: int) -> date:
    """일자를 1일로 정규화한 뒤 달 단위로 이동함."""

    index = value.year * 12 + value.month - 1 + months
    return date(index // 12, index % 12 + 1, 1)


def usage_window(base_date: date, months: int = USAGE_MONTHS) -> tuple[date, date]:
    """기준일이 속한 월을 포함한 최근 N개월의 안전한 조회 범위를 반환함."""

    if months < 1:
        raise ValueError("이용액 조회 개월 수는 1 이상이어야 합니다.")
    return shift_month(base_date.replace(day=1), -(months - 1)), base_date


def card_reference(position: int) -> str:
    """외부 LLM과 논리 SQL에서 사용할 요청 내부 카드 식별자를 생성함."""

    if position < 1 or position > 999:
        raise ValueError("카드 대체 식별자 순번은 1~999 범위여야 합니다.")
    return f"CARD_{position:03d}"


def snapshot_warnings(base_date: date, product_future: bool) -> list[str]:
    """스키마가 보존하지 않는 과거 상태와 부분 월의 한계를 명시함."""

    warnings = [
        "카드 상태는 데이터의 현재 스냅샷이며 기준일 당시의 상태 이력은 아닙니다.",
    ]
    if base_date != month_end(base_date):
        warnings.append("기준일이 월중이므로 해당 월 승인 이용액은 기준일까지의 부분 집계입니다.")
    if product_future:
        warnings.append(
            "기준일 이후 시행 상품 정보가 포함되어 상품명과 연회비를 기준일 당시 정책으로 단정할 수 없습니다."
        )
    return warnings
