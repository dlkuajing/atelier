"""Smoke tests for app.core.llm_relay — config wiring + role mapping.

Network calls to the actual relay are NOT exercised here (covered by manual
probes during setup). These tests guard the in-process invariants only.
"""

import pytest

from app.core.llm_relay import (
    FALLBACK_CHAT,
    KNOWN_UNAVAILABLE,
    PRIMARY_CHAT,
    PRIMARY_IMAGE,
    PRIMARY_LONG_CONTEXT,
    is_available,
    model_for_role,
)

# ---------------------------------------------------------------------------
# Role mapping
# ---------------------------------------------------------------------------


def test_wizard_main_maps_to_primary_chat():
    assert model_for_role("wizard.main") == PRIMARY_CHAT


def test_wizard_params_uses_same_primary_chat_for_consistency():
    """Wizard main + params share the same model so prompt style stays uniform."""
    assert model_for_role("wizard.params") == model_for_role("wizard.main")


def test_report_long_uses_long_context_model():
    assert model_for_role("report.long") == PRIMARY_LONG_CONTEXT


def test_image_cover_uses_image_model():
    assert model_for_role("image.cover") == PRIMARY_IMAGE


def test_fallback_chat_differs_from_primary():
    """Fallback must NOT be the primary itself — that would defeat the point."""
    assert FALLBACK_CHAT != PRIMARY_CHAT


def test_unknown_role_raises_with_helpful_message():
    with pytest.raises(ValueError, match="Unknown role"):
        model_for_role("nonexistent.role")


# ---------------------------------------------------------------------------
# Availability heuristic
# ---------------------------------------------------------------------------


def test_is_available_for_primary_model():
    assert is_available(PRIMARY_CHAT)
    assert is_available(PRIMARY_LONG_CONTEXT)
    assert is_available(PRIMARY_IMAGE)


def test_is_available_for_recovered_claude_channels():
    """Anthropic channels were restored on 2026-05-21 afternoon; if relay
    state regresses we update KNOWN_UNAVAILABLE and this test flips."""
    assert is_available("claude-opus-4-7")
    assert is_available("claude-sonnet-4-6")


def test_primary_chat_is_not_in_unavailable_set():
    """Sanity: we never select a model the relay can't serve."""
    assert PRIMARY_CHAT not in KNOWN_UNAVAILABLE
    assert PRIMARY_LONG_CONTEXT not in KNOWN_UNAVAILABLE
    assert PRIMARY_IMAGE not in KNOWN_UNAVAILABLE


def test_unavailable_set_is_currently_empty():
    """Sanity: no relay-blocked models tracked right now."""
    assert frozenset() == KNOWN_UNAVAILABLE
