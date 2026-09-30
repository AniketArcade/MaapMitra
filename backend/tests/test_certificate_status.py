"""Spec 13: pure unit coverage for app/core/certificate_status.py.

effective_status() predates this spec (step 9) and already had indirect coverage through
tests/test_public_verify.py and tests/test_expiry_job.py; this file pins its exact REVOKED-wins/
EXPIRED contract directly, as the regression check that step 13's additive is_expiring_soon()
sibling didn't disturb it. Both functions are pure (no DB), so no fixtures are needed beyond a
frozen `today`.
"""

from datetime import date, timedelta

from app.core.certificate_status import effective_status, is_expiring_soon
from app.core.config import get_settings
from app.models.certificate import CertificateStatus

TODAY = date(2026, 6, 15)
S = CertificateStatus


# --- effective_status(): existing contract, unchanged by step 13 ---------------------------


def test_effective_status_valid_far_out() -> None:
    assert effective_status(S.VALID, TODAY + timedelta(days=400), today=TODAY) == S.VALID


def test_effective_status_valid_on_the_due_date_is_not_yet_expired() -> None:
    # valid_until == today: the existing rule is strictly "<", not "<=".
    assert effective_status(S.VALID, TODAY, today=TODAY) == S.VALID


def test_effective_status_valid_past_due_becomes_expired() -> None:
    assert effective_status(S.VALID, TODAY - timedelta(days=1), today=TODAY) == S.EXPIRED


def test_effective_status_already_expired_stays_expired() -> None:
    assert effective_status(S.EXPIRED, TODAY - timedelta(days=1), today=TODAY) == S.EXPIRED


def test_effective_status_revoked_wins_even_when_not_past_due() -> None:
    assert effective_status(S.REVOKED, TODAY + timedelta(days=400), today=TODAY) == S.REVOKED


def test_effective_status_revoked_wins_even_when_also_past_due() -> None:
    # The precise "REVOKED always wins" guarantee spec 09 §4 documents: never displayed as merely
    # EXPIRED even though valid_until has also passed.
    assert effective_status(S.REVOKED, TODAY - timedelta(days=1), today=TODAY) == S.REVOKED


def test_effective_status_superseded_not_special_cased() -> None:
    # Step 13 deliberately does NOT add a SUPERSEDED-wins branch (see the function's own
    # docstring): a superseded certificate still falls through the same date rule as any other
    # non-REVOKED status.
    assert effective_status(S.SUPERSEDED, TODAY + timedelta(days=400), today=TODAY) == S.SUPERSEDED
    assert effective_status(S.SUPERSEDED, TODAY - timedelta(days=1), today=TODAY) == S.EXPIRED


# --- is_expiring_soon(): new in step 13, strictly additive ----------------------------------


def test_is_expiring_soon_false_when_far_out() -> None:
    horizon = get_settings().EXPIRY_REMINDER_30D_DAYS
    assert not is_expiring_soon(S.VALID, TODAY + timedelta(days=horizon + 1), today=TODAY)


def test_is_expiring_soon_true_at_exact_boundary() -> None:
    horizon = get_settings().EXPIRY_REMINDER_30D_DAYS
    assert is_expiring_soon(S.VALID, TODAY + timedelta(days=horizon), today=TODAY)


def test_is_expiring_soon_true_one_day_inside_boundary() -> None:
    horizon = get_settings().EXPIRY_REMINDER_30D_DAYS
    assert is_expiring_soon(S.VALID, TODAY + timedelta(days=horizon - 1), today=TODAY)


def test_is_expiring_soon_false_one_day_outside_boundary() -> None:
    horizon = get_settings().EXPIRY_REMINDER_30D_DAYS
    assert not is_expiring_soon(S.VALID, TODAY + timedelta(days=horizon + 1), today=TODAY)


def test_is_expiring_soon_false_for_expired_even_inside_window() -> None:
    # valid_until is technically inside the window, but effective_status() would already call
    # this EXPIRED (it's past due), never VALID -> is_expiring_soon must be False.
    assert not is_expiring_soon(S.EXPIRED, TODAY - timedelta(days=1), today=TODAY)
    assert not is_expiring_soon(S.VALID, TODAY - timedelta(days=1), today=TODAY)


def test_is_expiring_soon_false_for_revoked_even_inside_window() -> None:
    horizon = get_settings().EXPIRY_REMINDER_30D_DAYS
    assert not is_expiring_soon(S.REVOKED, TODAY + timedelta(days=horizon - 1), today=TODAY)


def test_is_expiring_soon_false_for_superseded_even_inside_window() -> None:
    horizon = get_settings().EXPIRY_REMINDER_30D_DAYS
    assert not is_expiring_soon(S.SUPERSEDED, TODAY + timedelta(days=horizon - 1), today=TODAY)
