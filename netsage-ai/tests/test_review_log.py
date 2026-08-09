"""
tests/test_review_log.py
-------------------------
Tests for review/review_store.py.

Validates:
  - All 3 review statuses are supported
  - human_root_cause is NEVER blank (regardless of status)
  - agreement is computed from root cause comparison, NEVER assumed from status
  - An Accepted review with a different human_root_cause computes agreement=False
  - An Edited review with matching text computes agreement=True
  - reviewer_notes required for Edited and Rejected
  - One row per case_id (re-review overwrites)
"""

import sys
import os
import pytest
import pandas as pd
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from review.review_store import (
    compute_agreement,
    normalize,
    validate_review_input,
    save_review,
    load_reviews,
    get_review_for_case,
    get_agreement_stats,
)


class TestNormalizeAndAgreement:
    """Unit tests for the normalize() and compute_agreement() functions."""

    def test_normalize_lowercases(self):
        assert normalize("VLAN") == "vlan"
        assert normalize("Gateway") == "gateway"

    def test_normalize_strips_whitespace(self):
        assert normalize("  DHCP  ") == "dhcp"
        assert normalize("\tRouting\n") == "routing"

    def test_agreement_same_value(self):
        assert compute_agreement("VLAN", "VLAN") is True

    def test_agreement_case_insensitive(self):
        assert compute_agreement("VLAN", "vlan") is True
        assert compute_agreement("Gateway", "GATEWAY") is True

    def test_agreement_with_whitespace(self):
        assert compute_agreement("  NAT  ", "nat") is True

    def test_disagreement_different_values(self):
        assert compute_agreement("VLAN", "Routing") is False

    # ── Critical: status must NEVER determine agreement ──────────────────────

    def test_accepted_with_different_human_rc_is_false(self):
        """
        An Accepted review where reviewer changed the human_root_cause
        must still compute agreement=False. Status does NOT determine agreement.
        """
        agreement = compute_agreement(
            ai_root_cause="VLAN",
            human_root_cause="Routing"   # reviewer changed it
        )
        assert agreement is False, (
            "Accepted status does not guarantee agreement=True. "
            "Agreement must come from root cause comparison."
        )

    def test_edited_with_matching_rc_is_true(self):
        """
        An Edited review where reviewer typed the same root cause
        must compute agreement=True. Edited status does NOT guarantee disagreement.
        """
        agreement = compute_agreement(
            ai_root_cause="Gateway",
            human_root_cause="Gateway"   # same despite 'Edited' status
        )
        assert agreement is True, (
            "Edited status does not guarantee agreement=False. "
            "Agreement must come from root cause comparison."
        )

    def test_rejected_with_undetermined_is_false(self):
        """Rejected case with 'Undetermined' human_root_cause computes False correctly."""
        agreement = compute_agreement(
            ai_root_cause="DHCP",
            human_root_cause="Undetermined — AI diagnosis rejected without a confirmed alternative"
        )
        assert agreement is False


class TestValidateReviewInput:
    def test_valid_accepted(self):
        ok, err = validate_review_input("Accepted", "VLAN", "")
        assert ok is True
        assert err is None

    def test_valid_edited_with_notes(self):
        ok, err = validate_review_input("Edited", "Gateway", "The AI missed the subnet mask error.")
        assert ok is True

    def test_valid_rejected_with_notes(self):
        ok, err = validate_review_input(
            "Rejected",
            "Undetermined — AI diagnosis rejected without a confirmed alternative",
            "The AI diagnosis was completely wrong."
        )
        assert ok is True

    def test_blank_human_rc_fails_always(self):
        """Blank human_root_cause must fail for ALL statuses."""
        for status in ["Accepted", "Edited", "Rejected"]:
            ok, err = validate_review_input(status, "", "some notes")
            assert ok is False, f"Blank human_rc should fail for status={status}"
            assert err is not None

    def test_whitespace_only_human_rc_fails(self):
        ok, err = validate_review_input("Accepted", "   ", "")
        assert ok is False

    def test_edited_without_notes_fails(self):
        ok, err = validate_review_input("Edited", "Gateway", "")
        assert ok is False
        assert "reviewer_notes" in err.lower() or "required" in err.lower()

    def test_rejected_without_notes_fails(self):
        ok, err = validate_review_input("Rejected", "VLAN", "")
        assert ok is False

    def test_invalid_status_fails(self):
        ok, err = validate_review_input("Maybe", "VLAN", "notes")
        assert ok is False
        assert "Invalid" in err

    def test_accepted_notes_optional(self):
        """reviewer_notes is optional for Accepted reviews."""
        ok, err = validate_review_input("Accepted", "VLAN", "")
        assert ok is True


class TestSaveAndLoadReview:
    """Integration tests for save_review and load_reviews using a temp directory."""

    @pytest.fixture(autouse=True)
    def use_temp_dir(self, tmp_path, monkeypatch):
        """Redirect REVIEWS_FILE and RESPONSIBLE_AI_LOG to a temp directory."""
        review_dir = tmp_path / "review"
        review_dir.mkdir()
        logs_dir = tmp_path / "logs"
        logs_dir.mkdir()

        monkeypatch.setattr("review.review_store.REVIEWS_FILE", review_dir / "reviews.csv")
        monkeypatch.setattr("review.review_store.RESPONSIBLE_AI_LOG", logs_dir / "responsible_ai_log.csv")

    def test_save_accepted_review(self):
        ok, msg = save_review(
            case_id="NS-001",
            ai_root_cause="VLAN",
            ai_confidence="High",
            review_status="Accepted",
            human_root_cause="VLAN",
            reviewer_notes="",
        )
        assert ok is True
        df = load_reviews()
        assert len(df) == 1
        row = df.iloc[0]
        assert row["agreement"].lower() == "true"
        assert row["human_root_cause"] == "VLAN"

    def test_save_accepted_with_divergent_rc_computes_false(self):
        """Accepted + different human_root_cause must compute agreement=False."""
        ok, msg = save_review(
            case_id="NS-002",
            ai_root_cause="VLAN",
            ai_confidence="High",
            review_status="Accepted",
            human_root_cause="Routing",  # reviewer changed it
            reviewer_notes="",
        )
        assert ok is True
        df = load_reviews()
        row = df[df["case_id"] == "NS-002"].iloc[0]
        assert row["agreement"].lower() == "false", \
            "Accepted + different human_root_cause must be agreement=False"

    def test_save_edited_with_same_rc_computes_true(self):
        """Edited + same human_root_cause must compute agreement=True."""
        ok, msg = save_review(
            case_id="NS-003",
            ai_root_cause="Gateway",
            ai_confidence="Medium",
            review_status="Edited",
            human_root_cause="Gateway",  # same value
            reviewer_notes="I only corrected the fix steps, not the root cause.",
        )
        assert ok is True
        df = load_reviews()
        row = df[df["case_id"] == "NS-003"].iloc[0]
        assert row["agreement"].lower() == "true", \
            "Edited + same human_root_cause must be agreement=True"

    def test_save_rejected_with_undetermined(self):
        ok, msg = save_review(
            case_id="NS-004",
            ai_root_cause="DHCP",
            ai_confidence="Low",
            review_status="Rejected",
            human_root_cause="Undetermined — AI diagnosis rejected without a confirmed alternative",
            reviewer_notes="The AI had no basis for this diagnosis.",
        )
        assert ok is True
        df = load_reviews()
        row = df[df["case_id"] == "NS-004"].iloc[0]
        assert row["agreement"].lower() == "false"

    def test_re_review_overwrites_not_duplicates(self):
        """Reviewing the same case twice must produce ONE row, not two."""
        save_review("NS-005", "VLAN", "High", "Accepted", "VLAN", "")
        save_review("NS-005", "VLAN", "High", "Edited", "Routing",
                    "Changed root cause after deeper analysis.")
        df = load_reviews()
        ns005_rows = df[df["case_id"] == "NS-005"]
        assert len(ns005_rows) == 1, "Re-review must overwrite, not duplicate"
        assert ns005_rows.iloc[0]["review_status"] == "Edited"

    def test_human_rc_never_blank_enforced(self):
        """save_review must reject blank human_root_cause."""
        ok, msg = save_review("NS-006", "NAT", "High", "Accepted", "", "")
        assert ok is False

    def test_agreement_stats(self):
        save_review("NS-007", "VLAN", "High", "Accepted", "VLAN", "")   # agree=True
        save_review("NS-008", "DHCP", "High", "Edited", "Routing",
                    "Different fault.")  # agree=False
        stats = get_agreement_stats()
        assert stats["total_reviewed"] == 2
        assert stats["agreement_count"] == 1
        assert stats["disagreement_count"] == 1
        assert stats["agreement_pct"] == 50.0

    def test_get_review_for_case_returns_none_if_not_reviewed(self):
        result = get_review_for_case("NS-999")
        assert result is None

    def test_get_review_for_case_returns_dict_after_save(self):
        save_review("NS-010", "ACL", "Medium", "Accepted", "ACL", "")
        result = get_review_for_case("NS-010")
        assert result is not None
        assert result["case_id"] == "NS-010"
        assert result["review_status"] == "Accepted"
