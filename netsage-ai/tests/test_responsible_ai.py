"""
tests/test_responsible_ai.py
-----------------------------
Tests for the Responsible AI log (logs/responsible_ai_log.csv).

IMPORTANT: The test `test_at_least_5_corrections` is EXPECTED TO FAIL until
the student has performed at least 5 genuine Edited/Rejected reviews through
the app with real AI outputs. This is INTENTIONAL and CORRECT behavior.

Do NOT "fix" this test by generating fake review data. The failure is the
honest signal that the student's manual review work is not yet complete.

Tests:
  1. Log is derived ONLY from reviews.csv (no other write path)
  2. Every row in the log corresponds to an agreement=False row in reviews.csv
  3. Log has >= 5 rows (EXPECTED TO FAIL until student completes 5 real reviews)
  4. Log contains the correct columns
"""

import sys
import os
import pytest
import pandas as pd
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

BASE_DIR = Path(__file__).parent.parent
REVIEWS_FILE = BASE_DIR / "review" / "reviews.csv"
RESPONSIBLE_AI_LOG = BASE_DIR / "logs" / "responsible_ai_log.csv"

EXPECTED_LOG_COLUMNS = [
    "case_id", "ai_root_cause", "human_root_cause",
    "review_status", "reviewer_notes", "timestamp"
]

MIN_REQUIRED_CORRECTIONS = 5


class TestResponsibleAILogDerivation:
    """
    Tests that the responsible AI log is derived correctly from reviews.csv.
    These tests use the REAL files (not mocks) — they reflect live project state.
    """

    def test_log_file_can_be_loaded_or_is_empty(self):
        """Log file exists or is empty — never an error condition by itself."""
        if RESPONSIBLE_AI_LOG.exists() and RESPONSIBLE_AI_LOG.stat().st_size > 0:
            df = pd.read_csv(RESPONSIBLE_AI_LOG, dtype=str)
            assert isinstance(df, pd.DataFrame)
        else:
            # No reviews yet — this is expected at project start
            pytest.skip("Responsible AI log not yet populated (no reviews completed)")

    def test_log_has_correct_columns(self):
        """If the log exists, it must have the expected columns."""
        if not RESPONSIBLE_AI_LOG.exists() or RESPONSIBLE_AI_LOG.stat().st_size == 0:
            pytest.skip("Log not yet populated")

        df = pd.read_csv(RESPONSIBLE_AI_LOG, dtype=str)
        for col in EXPECTED_LOG_COLUMNS:
            assert col in df.columns, f"Missing column in responsible_ai_log: {col}"

    def test_every_log_row_traces_to_real_disagreement_in_reviews(self):
        """
        Every row in responsible_ai_log.csv must correspond to a row
        in reviews.csv where agreement == False.
        This verifies the log is NOT fabricated.
        """
        if not RESPONSIBLE_AI_LOG.exists() or RESPONSIBLE_AI_LOG.stat().st_size == 0:
            pytest.skip("Log not yet populated")
        if not REVIEWS_FILE.exists() or REVIEWS_FILE.stat().st_size == 0:
            pytest.skip("reviews.csv not yet populated")

        log_df = pd.read_csv(RESPONSIBLE_AI_LOG, dtype=str)
        reviews_df = pd.read_csv(REVIEWS_FILE, dtype=str)

        # Reviews where agreement is False
        real_disagreements = set(
            reviews_df[reviews_df["agreement"].str.strip().str.lower() == "false"]["case_id"]
        )

        for _, row in log_df.iterrows():
            assert row["case_id"] in real_disagreements, (
                f"Log row for case {row['case_id']} has no corresponding "
                f"agreement=False entry in reviews.csv. "
                f"Log must only contain rows derived from real disagreements."
            )

    def test_no_log_row_has_agreement_true(self):
        """The log should only contain cases where AI was genuinely corrected."""
        if not RESPONSIBLE_AI_LOG.exists() or RESPONSIBLE_AI_LOG.stat().st_size == 0:
            pytest.skip("Log not yet populated")
        if not REVIEWS_FILE.exists() or REVIEWS_FILE.stat().st_size == 0:
            pytest.skip("reviews.csv not yet populated")

        log_df = pd.read_csv(RESPONSIBLE_AI_LOG, dtype=str)
        reviews_df = pd.read_csv(REVIEWS_FILE, dtype=str)

        # For each log row, check the corresponding reviews.csv row has agreement=False
        for _, log_row in log_df.iterrows():
            matching = reviews_df[reviews_df["case_id"] == log_row["case_id"]]
            if not matching.empty:
                agreement = matching.iloc[0]["agreement"].strip().lower()
                assert agreement == "false", (
                    f"Log contains case {log_row['case_id']} but reviews.csv shows "
                    f"agreement={agreement}. Log must only derive from agreement=False rows."
                )


class TestMinimumCorrectionsRequirement:
    """
    *** THIS TEST IS EXPECTED TO FAIL until the student has performed ***
    *** at least 5 genuine Edited/Rejected reviews through the app.   ***
    ***                                                                ***
    *** DO NOT fix this by generating fake review data.               ***
    *** The failure is intentional and correct.                       ***
    """

    def test_at_least_5_corrections_logged(self):
        """
        The responsible AI log must contain at least 5 entries.

        EXPECTED TO FAIL until the student has:
          1. Run the app with a real AI provider
          2. Gone through the Human Review tab
          3. Marked at least 5 cases as Edited or Rejected
          4. Provided genuine reviewer_notes for each

        This test will remain red (failing) until those steps are completed.
        That failing state is correct and honest — it accurately reflects that
        the student's manual review work is not yet done.
        """
        if not RESPONSIBLE_AI_LOG.exists() or RESPONSIBLE_AI_LOG.stat().st_size == 0:
            log_count = 0
        else:
            try:
                log_df = pd.read_csv(RESPONSIBLE_AI_LOG, dtype=str)
                log_count = len(log_df)
            except Exception:
                log_count = 0

        assert log_count >= MIN_REQUIRED_CORRECTIONS, (
            f"\n"
            f"RESPONSIBLE AI REQUIREMENT NOT YET MET\n"
            f"{'='*50}\n"
            f"Current corrections logged: {log_count}\n"
            f"Required: {MIN_REQUIRED_CORRECTIONS}\n"
            f"\n"
            f"To satisfy this requirement, you (the student) must:\n"
            f"  1. Run the app: streamlit run app.py\n"
            f"  2. Ensure an AI provider is configured (e.g. Ollama)\n"
            f"  3. Go to the Troubleshoot tab and run AI diagnosis for cases\n"
            f"  4. Go to the Human Review tab\n"
            f"  5. For at least 5 cases, select 'Edited' or 'Rejected'\n"
            f"  6. Enter your genuine human_root_cause and reviewer_notes\n"
            f"     explaining what was wrong with the AI diagnosis\n"
            f"  7. Click Save Review\n"
            f"\n"
            f"This CANNOT be done by a script or AI agent.\n"
            f"It requires YOUR judgment of whether the AI was correct.\n"
        )


class TestResponsibleAIWritePath:
    """
    Tests using temp directories to verify there is only ONE write path
    to the responsible AI log: the filter-on-agreement=False function.
    """

    def test_log_populated_only_from_disagreements(self, tmp_path, monkeypatch):
        """
        After saving reviews with mixed agreement values,
        the log must contain ONLY the agreement=False rows.
        """
        review_dir = tmp_path / "review"
        review_dir.mkdir()
        logs_dir = tmp_path / "logs"
        logs_dir.mkdir()

        monkeypatch.setattr("review.review_store.REVIEWS_FILE", review_dir / "reviews.csv")
        monkeypatch.setattr("review.review_store.RESPONSIBLE_AI_LOG", logs_dir / "responsible_ai_log.csv")

        from review.review_store import save_review, load_responsible_ai_log

        # Save 3 reviews: 2 agreements, 1 disagreement
        save_review("NS-A", "VLAN", "High", "Accepted", "VLAN", "")          # agree=True
        save_review("NS-B", "DHCP", "Medium", "Accepted", "DHCP", "")        # agree=True
        save_review("NS-C", "Routing", "High", "Edited", "ACL",               # agree=False
                    "The fault was an ACL, not a routing issue.")

        log_df = load_responsible_ai_log()
        assert len(log_df) == 1, f"Expected 1 disagreement in log, got {len(log_df)}"
        assert log_df.iloc[0]["case_id"] == "NS-C"

    def test_log_updated_when_re_review_changes_agreement(self, tmp_path, monkeypatch):
        """
        If a case is re-reviewed and agreement changes, the log must update accordingly.
        """
        review_dir = tmp_path / "review"
        review_dir.mkdir()
        logs_dir = tmp_path / "logs"
        logs_dir.mkdir()

        monkeypatch.setattr("review.review_store.REVIEWS_FILE", review_dir / "reviews.csv")
        monkeypatch.setattr("review.review_store.RESPONSIBLE_AI_LOG", logs_dir / "responsible_ai_log.csv")

        from review.review_store import save_review, load_responsible_ai_log

        # First review: disagreement
        save_review("NS-X", "NAT", "High", "Edited", "VLAN",
                    "Changed from NAT to VLAN after investigation.")
        log_df = load_responsible_ai_log()
        assert len(log_df) == 1

        # Re-review: now agreement
        save_review("NS-X", "NAT", "High", "Accepted", "NAT", "")
        log_df = load_responsible_ai_log()
        assert len(log_df) == 0, \
            "Log must update when re-review changes agreement to True"
