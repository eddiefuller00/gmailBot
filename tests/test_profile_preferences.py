from __future__ import annotations

from app.profile_preferences import (
    expand_deprioritize_categories,
    expand_priority_categories,
    normalize_important_sender_preferences,
)


def test_expand_priority_categories_handles_synonyms_and_odd_phrasing() -> None:
    expanded = expand_priority_categories(
        [
            "job opportunities",
            "academic deadlines",
            "billing reminders",
            "calendar invites",
        ]
    )
    assert expanded == {"job", "school", "bill", "event"}


def test_expand_deprioritize_categories_handles_marketing_aliases() -> None:
    expanded = expand_deprioritize_categories(
        ["ads and discounts", "weekly digests"]
    )
    assert expanded == {"promotion", "newsletter"}


def test_normalize_important_sender_preferences_supports_aliases_and_custom_values() -> None:
    expanded = normalize_important_sender_preferences(
        ["Talent Team", "Faculty", "Employers", "stripe.com"]
    )
    assert "recruiters" in expanded
    assert "professors" in expanded
    assert "companies" in expanded
    assert "stripe.com" in expanded
