"""
tests/test_e2e.py
------------------
End-to-end test: single case through rule checker → mocked AI → review → responsible AI filter.

This test simulates the full pipeline without any real AI provider or API key:
  1. Load a case from cases.csv
  2. Run rule checker (deterministic)
  3. Run AI diagnosis via a MOCKED provider
  4. Save a review (Edited status with different root cause = disagreement)
  5. Verify responsible AI log is populated correctly
"""

import sys
import os
import json
import pytest
import pandas as pd
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

PROJECT_ROOT = Path(__file__).parent.parent
CASES_PATH = PROJECT_ROOT / "data" / "cases.csv"


@pytest.fixture(scope="module")
def cases_df():
    assert CASES_PATH.exists(), "cases.csv must exist for e2e test"
    return pd.read_csv(CASES_PATH, dtype=str)


@pytest.fixture(autouse=True)
def temp_review_files(tmp_path, monkeypatch):
    """Redirect all file paths to temp directory for isolation."""
    review_dir = tmp_path / "review"
    review_dir.mkdir()
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    results_dir = tmp_path / "results"
    results_dir.mkdir()

    monkeypatch.setattr("review.review_store.REVIEWS_FILE", review_dir / "reviews.csv")
    monkeypatch.setattr("review.review_store.RESPONSIBLE_AI_LOG", logs_dir / "responsible_ai_log.csv")

    return tmp_path


class TestEndToEndPipeline:
    def test_full_pipeline_ns014(self, cases_df, tmp_path):
        """
        Full E2E for NS-014 (the demo inter-VLAN routing case):
        rule checker → mocked AI → review (Edited, disagreement) → responsible AI log
        """
        # ── Step 1: Load the demo case ────────────────────────────────────────
        case_row = cases_df[cases_df["case_id"] == "NS-014"].iloc[0].to_dict()
        assert case_row["case_id"] == "NS-014"

        # ── Step 2: Rule checker (no mocking needed — deterministic) ──────────
        from checker.rules import run_all_checks, get_triggered_checks

        results = run_all_checks(case_row["show_command_output"])
        assert len(results) == 6
        # NS-014 has an interface with unassigned IP — rule checker should detect something
        # (exact rules depend on output; we just verify it runs cleanly)
        for r in results:
            assert "triggered" in r
            assert "rule" in r

        # ── Step 3: AI diagnosis via mocked provider ──────────────────────────
        from ai.diagnose import diagnose_case

        # Mock AI response — valid JSON matching the schema
        mock_diagnosis = {
            "case_id": "NS-014",
            "root_cause": "Routing",
            "osi_layer": "Layer 3",
            "confidence": "High",
            "evidence": [
                "GigabitEthernet0/0.30  unassigned      YES unset  up                    up",
                "interface GigabitEthernet0/0.30 configured with no ip address"
            ],
            "next_command": "show running-config interface gi0/0.30",
            "fix_steps": [
                "interface GigabitEthernet0/0.30",
                "encapsulation dot1Q 30",
                "ip address 192.168.30.1 255.255.255.0"
            ]
        }
        mock_provider = MagicMock()
        mock_provider.diagnose.return_value = json.dumps(mock_diagnosis)

        with patch("ai.diagnose.get_provider", return_value=mock_provider):
            ai_result = diagnose_case(case_row)

        assert ai_result["ai_error"] is False
        assert ai_result["root_cause"] == "Routing"
        assert ai_result["confidence"] == "High"

        # ── Step 4: Human review — Edited with different root cause ───────────
        from review.review_store import save_review, load_reviews, load_responsible_ai_log

        # Reviewer corrects the root cause (AI said Routing, reviewer says DNS — disagreement)
        ok, msg = save_review(
            case_id="NS-014",
            ai_root_cause=ai_result["root_cause"],
            ai_confidence=ai_result["confidence"],
            review_status="Edited",
            human_root_cause="DNS",  # Different from AI's "Routing"
            reviewer_notes="The AI identified a routing symptom but the actual fault is a DNS configuration issue.",
        )
        assert ok is True

        # ── Step 5: Verify review is stored correctly ─────────────────────────
        reviews_df = load_reviews()
        assert len(reviews_df) == 1
        row = reviews_df.iloc[0]
        assert row["case_id"] == "NS-014"
        assert row["review_status"] == "Edited"
        assert row["human_root_cause"] == "DNS"
        assert row["ai_root_cause"] == "Routing"
        # Agreement must be False (Routing != DNS)
        assert row["agreement"].lower() == "false"

        # ── Step 6: Verify responsible AI log populated ───────────────────────
        log_df = load_responsible_ai_log()
        assert len(log_df) == 1
        log_row = log_df.iloc[0]
        assert log_row["case_id"] == "NS-014"
        assert log_row["review_status"] == "Edited"
        assert log_row["ai_root_cause"] == "Routing"
        assert log_row["human_root_cause"] == "DNS"

    def test_rule_checker_unaffected_by_missing_ai_provider(self, cases_df):
        """
        Even with no AI provider configured, rule checker must work perfectly.
        """
        env_no_ai = {k: v for k, v in os.environ.items()
                     if k not in ("AI_PROVIDER", "ANTHROPIC_API_KEY",
                                  "GEMINI_API_KEY", "OPENROUTER_API_KEY")}

        with patch.dict(os.environ, env_no_ai, clear=True):
            from checker.rules import run_all_checks

            case = cases_df.iloc[0]
            results = run_all_checks(case["show_command_output"])
            assert len(results) == 6
            assert all("triggered" in r for r in results)

    def test_accepted_review_does_not_pollute_responsible_ai_log(self, cases_df):
        """
        An Accepted review (agreement=True) must NOT appear in the responsible AI log.
        """
        from review.review_store import save_review, load_responsible_ai_log

        ok, _ = save_review(
            case_id="NS-001",
            ai_root_cause="VLAN",
            ai_confidence="High",
            review_status="Accepted",
            human_root_cause="VLAN",
            reviewer_notes="",
        )
        assert ok is True

        log_df = load_responsible_ai_log()
        assert len(log_df) == 0, \
            "Accepted reviews with agreement=True must not appear in responsible AI log"

    def test_ai_error_does_not_crash_rule_checker(self, cases_df):
        """
        When AI provider returns an error, rule checker results must still be available.
        """
        from ai.providers.base import ProviderConfigError
        from ai.diagnose import diagnose_case
        from checker.rules import run_all_checks

        case = cases_df[cases_df["case_id"] == "NS-007"].iloc[0].to_dict()

        # Simulate AI provider being unavailable
        with patch("ai.diagnose.get_provider",
                   side_effect=ProviderConfigError("No API key configured")):
            ai_result = diagnose_case(case)

        # AI should error gracefully
        assert ai_result["ai_error"] is True
        assert "No API key" in ai_result["ai_error_message"]
        assert ai_result["root_cause"] == ""  # Nothing fabricated

        # Rule checker must still work
        rule_results = run_all_checks(case["show_command_output"])
        assert len(rule_results) == 6
        # NS-007 has admin-down interface
        triggered_rules = {r["rule"] for r in rule_results if r["triggered"]}
        assert "check_interface_down" in triggered_rules
