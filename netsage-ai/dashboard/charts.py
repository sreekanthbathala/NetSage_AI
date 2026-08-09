"""
dashboard/charts.py
--------------------
Streamlit chart functions for the NetSage AI Dashboard tab.

Reads from:
  - data/cases.csv        (case metadata)
  - review/reviews.csv    (human review results, including the explicit `agreement` column)
  - logs/responsible_ai_log.csv  (cases where human disagreed with AI)

IMPORTANT: All agreement statistics read directly from the `agreement` column in reviews.csv.
           We NEVER infer agreement from review_status. The column is the ground truth.
"""

import streamlit as st
import pandas as pd
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
CASES_FILE = BASE_DIR / "data" / "cases.csv"
REVIEWS_FILE = BASE_DIR / "review" / "reviews.csv"
RESPONSIBLE_AI_LOG = BASE_DIR / "logs" / "responsible_ai_log.csv"

# Minimum required responsible AI corrections for project completion
MIN_REQUIRED_CORRECTIONS = 5


def _load_cases() -> pd.DataFrame:
    """Load cases.csv."""
    if CASES_FILE.exists():
        return pd.read_csv(CASES_FILE, dtype=str)
    return pd.DataFrame()


def _load_reviews() -> pd.DataFrame:
    """Load reviews.csv with correct dtypes."""
    if REVIEWS_FILE.exists() and REVIEWS_FILE.stat().st_size > 0:
        try:
            return pd.read_csv(REVIEWS_FILE, dtype=str)
        except Exception:
            pass
    return pd.DataFrame(columns=["case_id", "ai_root_cause", "ai_confidence",
                                  "review_status", "human_root_cause", "agreement",
                                  "reviewer_notes", "timestamp"])


def _load_responsible_ai_log() -> pd.DataFrame:
    """Load responsible_ai_log.csv."""
    if RESPONSIBLE_AI_LOG.exists() and RESPONSIBLE_AI_LOG.stat().st_size > 0:
        try:
            return pd.read_csv(RESPONSIBLE_AI_LOG, dtype=str)
        except Exception:
            pass
    return pd.DataFrame(columns=["case_id", "ai_root_cause", "human_root_cause",
                                  "review_status", "reviewer_notes", "timestamp"])


def render_dashboard():
    """Render the full Dashboard tab with all 3 sections + responsible AI panel."""

    st.header("📊 NetSage AI Dashboard")
    st.caption("Live metrics from the case dataset and human review log.")

    cases_df = _load_cases()
    reviews_df = _load_reviews()
    log_df = _load_responsible_ai_log()

    # ─────────────────────────────────────────────────
    # Section A: Case Count by Fault Category
    # ─────────────────────────────────────────────────
    st.subheader("A — Cases by Fault Category")

    if cases_df.empty:
        st.warning("No cases loaded. Ensure data/cases.csv exists.")
    else:
        category_counts = cases_df["expected_fault"].value_counts().reset_index()
        category_counts.columns = ["Fault Category", "Case Count"]

        col1, col2 = st.columns([2, 1])
        with col1:
            st.bar_chart(category_counts.set_index("Fault Category"))
        with col2:
            st.dataframe(category_counts, hide_index=True, use_container_width=True)

        st.caption(f"Total cases: **{len(cases_df)}** across **{cases_df['expected_fault'].nunique()}** fault categories")

    st.divider()

    # ─────────────────────────────────────────────────
    # Section B: Case Count by Severity
    # ─────────────────────────────────────────────────
    st.subheader("B — Cases by Severity")

    if cases_df.empty:
        st.warning("No cases loaded.")
    else:
        severity_order = ["Critical", "High", "Medium", "Low"]
        severity_counts = (
            cases_df["severity"]
            .value_counts()
            .reindex(severity_order, fill_value=0)
            .reset_index()
        )
        severity_counts.columns = ["Severity", "Case Count"]

        col1, col2 = st.columns([2, 1])
        with col1:
            st.bar_chart(severity_counts.set_index("Severity"))
        with col2:
            for _, row in severity_counts.iterrows():
                sev = row["Severity"]
                count = row["Case Count"]
                color = {"Critical": "🔴", "High": "🟠", "Medium": "🟡", "Low": "🟢"}.get(sev, "⚪")
                st.metric(f"{color} {sev}", count)

    st.divider()

    # ─────────────────────────────────────────────────
    # Section C: AI vs Human Agreement
    # (reads the explicit `agreement` column — NEVER inferred from status)
    # ─────────────────────────────────────────────────
    st.subheader("C — AI vs Human Agreement")

    if reviews_df.empty:
        st.info("No reviews yet. Use the **Human Review** tab to review AI diagnoses.")
    else:
        # Read agreement directly from the agreement column — never from review_status
        agreement_col = reviews_df["agreement"].str.strip().str.lower()
        total_reviewed = len(reviews_df)
        agreement_count = int((agreement_col == "true").sum())
        disagreement_count = int(total_reviewed - agreement_count)
        agreement_pct = round((agreement_count / total_reviewed) * 100, 1) if total_reviewed > 0 else 0.0

        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Total Reviewed", total_reviewed)
        with col2:
            st.metric("✅ Agreement", f"{agreement_count} ({agreement_pct}%)")
        with col3:
            st.metric("❌ Disagreement", disagreement_count)

        # Pie-like bar
        if total_reviewed > 0:
            agree_df = pd.DataFrame({
                "Result": ["Agreement", "Disagreement"],
                "Count": [agreement_count, disagreement_count]
            })
            st.bar_chart(agree_df.set_index("Result"))

        # Status breakdown table (informational — NOT used to determine agreement)
        st.caption("**Review Status Breakdown** (for reference — agreement is computed from root cause comparison, not from status)")
        status_counts = reviews_df["review_status"].value_counts().reset_index()
        status_counts.columns = ["Review Status", "Count"]
        st.dataframe(status_counts, hide_index=True)

    st.divider()

    # ─────────────────────────────────────────────────
    # Responsible AI Panel
    # ─────────────────────────────────────────────────
    st.subheader("🛡️ Responsible AI Log")

    correction_count = len(log_df)

    if correction_count < MIN_REQUIRED_CORRECTIONS:
        st.warning(
            f"⚠ Only **{correction_count}** of **{MIN_REQUIRED_CORRECTIONS}** required corrections logged. "
            f"Review more cases in the **Human Review** tab and mark at least "
            f"{MIN_REQUIRED_CORRECTIONS - correction_count} more as Edited or Rejected "
            f"(with genuine reviewer_notes explaining what was wrong)."
        )
    else:
        st.success(
            f"✅ Responsible AI requirement met: **{correction_count}** genuine corrections logged "
            f"(minimum {MIN_REQUIRED_CORRECTIONS} required)."
        )

    st.metric("Genuine AI Corrections (agreement=False)", correction_count)

    if not log_df.empty:
        st.caption("Cases where human reviewer's judgment diverged from AI diagnosis:")
        st.dataframe(
            log_df[["case_id", "ai_root_cause", "human_root_cause", "review_status", "reviewer_notes", "timestamp"]],
            hide_index=True,
            use_container_width=True,
        )
    else:
        st.caption(
            "No corrections logged yet. This log is populated automatically when you submit "
            "reviews where your root cause differs from the AI's root cause."
        )
