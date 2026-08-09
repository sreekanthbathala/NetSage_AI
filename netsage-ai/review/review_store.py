"""
review/review_store.py
-----------------------
Manages the reviews.csv file — reading, writing, and computing agreement.

Schema of reviews.csv:
  case_id, ai_root_cause, ai_confidence, review_status, human_root_cause,
  agreement, reviewer_notes, timestamp

Key design rules:
  - human_root_cause is ALWAYS required (non-blank), regardless of review_status
  - agreement is ALWAYS computed by comparing ai_root_cause and human_root_cause
    (normalized: lowercase + stripped) — NEVER assumed from review_status
  - reviewer_notes is required (non-blank) when review_status != 'Accepted'
  - One row per case_id — re-review overwrites the previous entry
  - No fabricated/auto-generated review rows — only written from real UI submissions
"""

import datetime
import os
import pandas as pd
from pathlib import Path
from typing import Optional, Tuple

BASE_DIR = Path(__file__).parent.parent
REVIEWS_FILE = BASE_DIR / "review" / "reviews.csv"
RESPONSIBLE_AI_LOG = BASE_DIR / "logs" / "responsible_ai_log.csv"

REVIEW_COLUMNS = [
    "case_id",
    "ai_root_cause",
    "ai_confidence",
    "review_status",
    "human_root_cause",
    "agreement",
    "reviewer_notes",
    "timestamp",
]

RESPONSIBLE_AI_COLUMNS = [
    "case_id",
    "ai_root_cause",
    "human_root_cause",
    "review_status",
    "reviewer_notes",
    "timestamp",
]

VALID_STATUSES = {"Accepted", "Edited", "Rejected"}


def normalize(root_cause: str) -> str:
    """
    Normalize a root cause string for agreement comparison.
    Lowercases and strips whitespace.
    """
    return root_cause.strip().lower()


def compute_agreement(ai_root_cause: str, human_root_cause: str) -> bool:
    """
    Compute agreement by comparing normalized ai_root_cause and human_root_cause.

    This is ALWAYS computed from the two strings — never assumed from review_status.
    An 'Accepted' review with a divergent human_root_cause computes agreement=False.
    An 'Edited' review with matching root causes computes agreement=True.
    """
    return normalize(ai_root_cause) == normalize(human_root_cause)


def validate_review_input(
    review_status: str,
    human_root_cause: str,
    reviewer_notes: str,
) -> Tuple[bool, Optional[str]]:
    """
    Validate review form inputs before saving.

    Returns:
        (is_valid, error_message) — error_message is None if valid.
    """
    if review_status not in VALID_STATUSES:
        return False, f"Invalid review_status: '{review_status}'. Must be Accepted, Edited, or Rejected."

    if not human_root_cause or not human_root_cause.strip():
        return False, (
            "human_root_cause is required and must not be blank, regardless of review status. "
            "For Rejected cases where the cause is unknown, enter: "
            "'Undetermined — AI diagnosis rejected without a confirmed alternative'"
        )

    if review_status != "Accepted" and (not reviewer_notes or not reviewer_notes.strip()):
        return False, (
            f"reviewer_notes is required (non-blank) when review_status is '{review_status}'. "
            "Please explain what was wrong with the AI's diagnosis."
        )

    return True, None


def load_reviews() -> pd.DataFrame:
    """
    Load reviews.csv into a DataFrame.
    Returns an empty DataFrame with the correct schema if the file doesn't exist.
    """
    if REVIEWS_FILE.exists() and REVIEWS_FILE.stat().st_size > 0:
        try:
            df = pd.read_csv(REVIEWS_FILE, dtype=str)
            # Ensure all expected columns exist
            for col in REVIEW_COLUMNS:
                if col not in df.columns:
                    df[col] = ""
            return df[REVIEW_COLUMNS]
        except Exception:
            pass

    return pd.DataFrame(columns=REVIEW_COLUMNS)


def save_review(
    case_id: str,
    ai_root_cause: str,
    ai_confidence: str,
    review_status: str,
    human_root_cause: str,
    reviewer_notes: str,
) -> Tuple[bool, str]:
    """
    Validate and save a single review row to reviews.csv.

    Computes agreement from the two root cause strings (never assumed from status).
    Overwrites any existing row for this case_id (one row per case).

    Args:
        case_id: The case being reviewed.
        ai_root_cause: The AI's root cause diagnosis (verbatim from results).
        ai_confidence: The AI's confidence (verbatim).
        review_status: 'Accepted', 'Edited', or 'Rejected'.
        human_root_cause: The reviewer's root cause (always required).
        reviewer_notes: Required when status != Accepted.

    Returns:
        (success, message) tuple.
    """
    # Validate inputs
    is_valid, error = validate_review_input(review_status, human_root_cause, reviewer_notes)
    if not is_valid:
        return False, error

    # Compute agreement from data, not from status
    agreement = compute_agreement(ai_root_cause, human_root_cause)

    # Build the new row
    new_row = {
        "case_id": str(case_id).strip(),
        "ai_root_cause": str(ai_root_cause).strip(),
        "ai_confidence": str(ai_confidence).strip(),
        "review_status": review_status,
        "human_root_cause": str(human_root_cause).strip(),
        "agreement": str(agreement),
        "reviewer_notes": str(reviewer_notes).strip(),
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }

    # Load existing reviews, remove any existing row for this case_id, append new row
    df = load_reviews()
    df = df[df["case_id"] != str(case_id).strip()]
    new_df = pd.DataFrame([new_row], columns=REVIEW_COLUMNS)
    df = pd.concat([df, new_df], ignore_index=True)

    # Save to file
    REVIEWS_FILE.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(REVIEWS_FILE, index=False)

    # Regenerate responsible AI log after any review change
    _regenerate_responsible_ai_log(df)

    status_display = "agreement" if agreement else "disagreement"
    return True, (
        f"Review saved for {case_id}: {review_status} | "
        f"Agreement computed: {agreement} ({status_display})"
    )


def _regenerate_responsible_ai_log(reviews_df: pd.DataFrame) -> None:
    """
    Regenerate logs/responsible_ai_log.csv from reviews where agreement == False.

    This is the ONLY code path that may write to responsible_ai_log.csv.
    No seed scripts, no demo data — only real reviews.

    The log captures cases where the reviewer's genuine judgment diverged from the AI's output.
    """
    # Filter for rows where agreement is False (as string)
    disagreements = reviews_df[
        reviews_df["agreement"].str.strip().str.lower() == "false"
    ].copy()

    log_df = disagreements[
        ["case_id", "ai_root_cause", "human_root_cause", "review_status", "reviewer_notes", "timestamp"]
    ]

    RESPONSIBLE_AI_LOG.parent.mkdir(parents=True, exist_ok=True)
    log_df.to_csv(RESPONSIBLE_AI_LOG, index=False)


def load_responsible_ai_log() -> pd.DataFrame:
    """
    Load the responsible AI log from file.
    Returns empty DataFrame with correct schema if file doesn't exist.
    """
    if RESPONSIBLE_AI_LOG.exists() and RESPONSIBLE_AI_LOG.stat().st_size > 0:
        try:
            return pd.read_csv(RESPONSIBLE_AI_LOG, dtype=str)
        except Exception:
            pass
    return pd.DataFrame(columns=RESPONSIBLE_AI_COLUMNS)


def get_review_for_case(case_id: str) -> Optional[dict]:
    """
    Return the most recent review for a given case_id, or None if not reviewed.
    """
    df = load_reviews()
    matching = df[df["case_id"] == str(case_id).strip()]
    if matching.empty:
        return None
    row = matching.iloc[0].to_dict()
    return row


def get_agreement_stats() -> dict:
    """
    Compute agreement statistics from reviews.csv for the Dashboard.

    Returns:
        dict with keys: total_reviewed, agreement_count, disagreement_count, agreement_pct
    """
    df = load_reviews()
    if df.empty:
        return {
            "total_reviewed": 0,
            "agreement_count": 0,
            "disagreement_count": 0,
            "agreement_pct": 0.0,
        }

    agreement_col = df["agreement"].str.strip().str.lower()
    agreement_count = (agreement_col == "true").sum()
    total = len(df)
    return {
        "total_reviewed": total,
        "agreement_count": int(agreement_count),
        "disagreement_count": int(total - agreement_count),
        "agreement_pct": round((agreement_count / total) * 100, 1) if total > 0 else 0.0,
    }
