from datetime import date

import pytest

from app.domain.customer import (
    card_reference,
    latest_completed_month_end,
    snapshot_warnings,
    usage_window,
    validate_member_id,
    validate_requested_date,
)


def test_monthly_delinquency_uses_only_completed_month():
    assert latest_completed_month_end(date(2026, 8, 15)) == date(2026, 7, 31)
    assert latest_completed_month_end(date(2026, 8, 31)) == date(2026, 8, 31)


def test_usage_window_includes_base_month_and_previous_five_months():
    assert usage_window(date(2026, 8, 15)) == (date(2026, 3, 1), date(2026, 8, 15))
    assert usage_window(date(2026, 1, 5)) == (date(2025, 8, 1), date(2026, 1, 5))


def test_requested_date_rejects_future_and_pre_join_dates():
    with pytest.raises(ValueError, match="데이터 기준일 이후"):
        validate_requested_date(date(2026, 9, 1), date(2026, 8, 31), date(2020, 1, 1))
    with pytest.raises(ValueError, match="가입일 전"):
        validate_requested_date(date(2020, 1, 1), date(2026, 8, 31), date(2020, 1, 2))
    with pytest.raises(ValueError, match="거래 데이터 제공 기간 이전"):
        validate_requested_date(
            date(2025, 7, 31),
            date(2026, 8, 31),
            date(2020, 1, 1),
            date(2025, 8, 1),
        )


def test_member_and_card_references_are_bounded():
    assert validate_member_id("M-1042") == "M-1042"
    assert card_reference(1) == "CARD_001"
    with pytest.raises(ValueError):
        validate_member_id("1042 OR 1=1")
    with pytest.raises(ValueError):
        card_reference(1000)


def test_partial_month_and_future_product_warnings_are_explicit():
    warnings = snapshot_warnings(date(2026, 8, 15), product_future=True)
    assert any("부분 집계" in warning for warning in warnings)
    assert any("기준일 이후 시행" in warning for warning in warnings)
