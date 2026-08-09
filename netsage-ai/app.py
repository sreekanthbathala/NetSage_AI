"""
app.py
-------
NetSage AI — Main Streamlit Application

3 tabs:
  1. 🔍 Troubleshoot  — Select a case, run rule checker + AI diagnosis in parallel
  2. 📝 Human Review  — Accept / Edit / Reject AI diagnoses, view review history
  3. 📊 Dashboard     — Case metrics, agreement rates, responsible AI log

Architecture notes:
  - This file NEVER imports a provider-specific SDK (no `import anthropic`, etc.)
  - All AI calls go through ai/diagnose.py -> ai/providers/provider_factory.py
  - Rule checker (checker/rules.py) runs independently of any AI provider
  - On AI failure: a red error banner is shown; rule checker results are unaffected
"""

import json
import os
import sys
import pandas as pd
import streamlit as st
from pathlib import Path
from dotenv import load_dotenv

# Load .env file if present
load_dotenv()

# Ensure project root is on the path for imports
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from checker.rules import run_all_checks, get_triggered_checks
from ai.diagnose import get_diagnosis_for_case
from ai.providers.base import ProviderConfigError, ProviderCallError
from review.review_store import (
    load_reviews,
    save_review,
    load_responsible_ai_log,
    get_review_for_case,
    get_agreement_stats,
)
from dashboard.charts import render_dashboard

# ─────────────────────────────────────────────────────────────────────────────
# Page configuration
# ─────────────────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="NetSage AI — Network Troubleshooting Assistant",
    page_icon="🌐",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────────────────────────────────────
# Custom CSS
# ─────────────────────────────────────────────────────────────────────────────

st.markdown("""
<style>
/* Global font */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
}

/* Header */
.main-header {
    background: linear-gradient(135deg, #0f2027, #203a43, #2c5364);
    padding: 1.5rem 2rem;
    border-radius: 12px;
    margin-bottom: 1.5rem;
    color: white;
}
.main-header h1 {
    font-size: 2rem;
    font-weight: 700;
    margin: 0;
    letter-spacing: -0.5px;
}
.main-header p {
    color: #a0aec0;
    margin: 0.25rem 0 0 0;
    font-size: 0.95rem;
}

/* Provider badge */
.provider-badge {
    display: inline-block;
    padding: 4px 12px;
    border-radius: 999px;
    font-size: 0.75rem;
    font-weight: 600;
    background: rgba(99, 179, 237, 0.15);
    color: #63b3ed;
    border: 1px solid rgba(99, 179, 237, 0.3);
    margin-top: 0.5rem;
}

/* Rule checker result cards */
.rule-card-triggered {
    background: rgba(245, 101, 101, 0.1);
    border-left: 4px solid #fc8181;
    border-radius: 8px;
    padding: 0.75rem 1rem;
    margin: 0.4rem 0;
}
.rule-card-clean {
    background: rgba(72, 187, 120, 0.1);
    border-left: 4px solid #68d391;
    border-radius: 8px;
    padding: 0.75rem 1rem;
    margin: 0.4rem 0;
}

/* Show command output */
.show-output {
    background: #0d1117;
    color: #58a6ff;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.78rem;
    padding: 1rem;
    border-radius: 8px;
    border: 1px solid #21262d;
    white-space: pre-wrap;
    word-break: break-all;
    max-height: 300px;
    overflow-y: auto;
}

/* AI diagnosis card */
.ai-result-card {
    background: rgba(66, 153, 225, 0.05);
    border: 1px solid rgba(66, 153, 225, 0.2);
    border-radius: 12px;
    padding: 1.2rem 1.5rem;
    margin-top: 1rem;
}

/* Error banner */
.error-banner {
    background: rgba(245, 101, 101, 0.1);
    border: 1px solid rgba(245, 101, 101, 0.4);
    border-radius: 8px;
    padding: 1rem 1.25rem;
    color: #fc8181;
    font-size: 0.9rem;
}

/* Review status badges */
.badge-accepted { color: #68d391; font-weight: 600; }
.badge-edited   { color: #f6ad55; font-weight: 600; }
.badge-rejected { color: #fc8181; font-weight: 600; }
.badge-agree    { color: #68d391; }
.badge-disagree { color: #fc8181; }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# Load dataset
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_data
def load_cases() -> pd.DataFrame:
    cases_path = PROJECT_ROOT / "data" / "cases.csv"
    if not cases_path.exists():
        return pd.DataFrame()
    return pd.read_csv(cases_path, dtype=str)


# ─────────────────────────────────────────────────────────────────────────────
# Header
# ─────────────────────────────────────────────────────────────────────────────

provider_name = os.environ.get("AI_PROVIDER", "ollama").upper()
st.markdown(f"""
<div class="main-header">
  <h1>🌐 NetSage AI</h1>
  <p>AI-Assisted Cisco Network Troubleshooting · Human-in-the-Loop · Responsible AI</p>
  <span class="provider-badge">AI Provider: {provider_name}</span>
</div>
""", unsafe_allow_html=True)

cases_df = load_cases()

# ─────────────────────────────────────────────────────────────────────────────
# Main tabs
# ─────────────────────────────────────────────────────────────────────────────

tab_troubleshoot, tab_review, tab_dashboard = st.tabs([
    "🔍 Troubleshoot",
    "📝 Human Review",
    "📊 Dashboard",
])

# =============================================================================
# TAB 1: TROUBLESHOOT
# =============================================================================

with tab_troubleshoot:
    st.header("🔍 Troubleshoot a Network Case")

    if cases_df.empty:
        st.error("Cannot load cases. Ensure `data/cases.csv` exists.")
        st.stop()

    # Sidebar-style case selector
    col_select, col_info = st.columns([1, 2])

    with col_select:
        st.subheader("Select Case")

        # Filter by category
        categories = ["All"] + sorted(cases_df["expected_fault"].unique().tolist())
        selected_category = st.selectbox(
            "Filter by Fault Category",
            categories,
            key="ts_category_filter",
        )

        filtered_df = cases_df if selected_category == "All" else \
            cases_df[cases_df["expected_fault"] == selected_category]

        case_options = [
            f"{row['case_id']} — {row['title']}"
            for _, row in filtered_df.iterrows()
        ]
        selected_option = st.selectbox(
            "Case",
            case_options,
            key="ts_case_select",
        )

        selected_case_id = selected_option.split(" — ")[0]
        case_row = cases_df[cases_df["case_id"] == selected_case_id].iloc[0].to_dict()

    with col_info:
        st.subheader(f"Case: {case_row['case_id']}")
        st.write(f"**{case_row['title']}**")

        sev_colors = {"Critical": "🔴", "High": "🟠", "Medium": "🟡", "Low": "🟢"}
        sev_icon = sev_colors.get(case_row.get("severity", ""), "⚪")
        st.write(
            f"**Category:** {case_row.get('expected_fault', '—')} &nbsp;|&nbsp; "
            f"**Severity:** {sev_icon} {case_row.get('severity', '—')} &nbsp;|&nbsp; "
            f"**OSI Layer:** {case_row.get('osi_layer', '—')}"
        )
        st.write(f"**Symptom:** {case_row.get('symptom', '—')}")
        st.write(f"**Topology:** {case_row.get('topology_note', '—')}")

    # Show command output
    st.subheader("📟 Show Command Output (Evidence)")
    st.markdown(
        f'<div class="show-output">{case_row.get("show_command_output", "")}</div>',
        unsafe_allow_html=True,
    )

    st.divider()

    # ── Run Analysis ──────────────────────────────────────────────────────────
    col_rule, col_ai = st.columns(2)

    with col_rule:
        st.subheader("🔧 Rule Checker")
        st.caption("Deterministic checks — runs regardless of AI availability")

        rule_results = run_all_checks(case_row.get("show_command_output", ""))
        triggered = [r for r in rule_results if r["triggered"]]

        if triggered:
            st.warning(f"**{len(triggered)} rule(s) triggered:**")
            for r in triggered:
                st.markdown(
                    f'<div class="rule-card-triggered">'
                    f'<strong>⚠ {r["rule"].replace("_", " ").title()}</strong><br>'
                    f'{r["message"]}'
                    f'{"<br><em>Evidence: " + r["evidence"][:200] + "</em>" if r["evidence"] else ""}'
                    f'</div>',
                    unsafe_allow_html=True,
                )
        else:
            st.success("✅ All rule checks passed — no deterministic faults detected.")

        # Show all checks summary
        with st.expander("All 6 checks detail"):
            for r in rule_results:
                icon = "⚠️" if r["triggered"] else "✅"
                st.write(f"{icon} **{r['rule']}**: {r['message']}")
                if r["evidence"]:
                    st.caption(f"Evidence: {r['evidence'][:300]}")

    with col_ai:
        st.subheader("🤖 AI Diagnosis")
        ai_provider = os.environ.get("AI_PROVIDER", "ollama")
        st.caption(f"Provider: `{ai_provider}` | Click button to run")

        if st.button("▶ Run AI Diagnosis", key="btn_run_ai", type="primary"):
            with st.spinner(f"Calling {ai_provider} provider…"):
                result = get_diagnosis_for_case(case_row)
                st.session_state["ai_result"] = result
                st.session_state["ai_case_id"] = selected_case_id

        # Display AI result from session state
        ai_result = st.session_state.get("ai_result")
        ai_case = st.session_state.get("ai_case_id")

        if ai_result and ai_case == selected_case_id:
            if ai_result.get("ai_error"):
                st.markdown(
                    f'<div class="error-banner">'
                    f'🚫 <strong>AI diagnosis unavailable</strong> — '
                    f'{ai_result.get("ai_error_message", "Unknown error")}.<br>'
                    f'<em>Rule-checker results above are unaffected.</em>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
            else:
                conf_color = {"High": "🟢", "Medium": "🟡", "Low": "🔴"}.get(
                    ai_result.get("confidence", ""), "⚪"
                )
                st.markdown(
                    f'<div class="ai-result-card">'
                    f'<strong>Root Cause:</strong> {ai_result.get("root_cause", "—")}<br>'
                    f'<strong>OSI Layer:</strong> {ai_result.get("osi_layer", "—")}<br>'
                    f'<strong>Confidence:</strong> {conf_color} {ai_result.get("confidence", "—")}'
                    f'</div>',
                    unsafe_allow_html=True,
                )

                # Evidence
                evidence_raw = ai_result.get("evidence", "[]")
                try:
                    evidence_list = json.loads(evidence_raw) if isinstance(evidence_raw, str) else evidence_raw
                except Exception:
                    evidence_list = [str(evidence_raw)]

                if evidence_list:
                    with st.expander("🔍 Evidence cited by AI"):
                        for ev in evidence_list:
                            st.write(f"• {ev}")

                # Fix steps
                fix_raw = ai_result.get("fix_steps", "[]")
                try:
                    fix_list = json.loads(fix_raw) if isinstance(fix_raw, str) else fix_raw
                except Exception:
                    fix_list = [str(fix_raw)]

                if fix_list:
                    with st.expander("🛠 Recommended Fix Steps"):
                        for i, step in enumerate(fix_list, 1):
                            st.write(f"{i}. {step}")

                st.info(
                    f"**Suggested next command:** `{ai_result.get('next_command', '—')}`",
                    icon="💡",
                )

                # Quick-jump to review
                st.success(
                    "✅ AI diagnosis complete. Go to the **📝 Human Review** tab to "
                    "Accept, Edit, or Reject this diagnosis.",
                    icon="➡️",
                )

# =============================================================================
# TAB 2: HUMAN REVIEW
# =============================================================================

with tab_review:
    st.header("📝 Human Review")
    st.caption(
        "Review AI diagnoses. Every case requires an explicit human_root_cause. "
        "Agreement is computed from the two root causes — never assumed from the status button you click."
    )

    if cases_df.empty:
        st.error("Cannot load cases. Ensure `data/cases.csv` exists.")
        st.stop()

    # ── Case selector ─────────────────────────────────────────────────────────
    reviews_df = load_reviews()
    reviewed_ids = set(reviews_df["case_id"].tolist()) if not reviews_df.empty else set()

    col_a, col_b = st.columns([1, 2])

    with col_a:
        st.subheader("Select Case to Review")

        review_options = [
            f"{'✅ ' if row['case_id'] in reviewed_ids else ''}{row['case_id']} — {row['title']}"
            for _, row in cases_df.iterrows()
        ]
        selected_review_opt = st.selectbox(
            "Case",
            review_options,
            key="rv_case_select",
        )

        # Strip the ✅ prefix if present
        rv_case_raw = selected_review_opt.lstrip("✅ ").split(" — ")[0].strip()
        rv_case_row = cases_df[cases_df["case_id"] == rv_case_raw].iloc[0].to_dict()

        # Progress indicator
        st.metric("Reviewed", f"{len(reviewed_ids)} / {len(cases_df)}")
        if len(reviewed_ids) >= len(cases_df):
            st.success("🎉 All cases reviewed!")

    with col_b:
        st.subheader(f"Reviewing: {rv_case_row['case_id']}")
        st.write(f"**{rv_case_row['title']}**")
        st.write(f"**Symptom:** {rv_case_row.get('symptom', '—')}")

        with st.expander("Show Command Output"):
            st.code(rv_case_row.get("show_command_output", ""), language=None)

    st.divider()

    # ── Load existing AI result from ai_results.csv ───────────────────────────
    ai_results_path = PROJECT_ROOT / "results" / "ai_results.csv"
    ai_case_result = {}
    if ai_results_path.exists():
        try:
            ai_df = pd.read_csv(ai_results_path, dtype=str)
            matched = ai_df[ai_df["case_id"] == rv_case_raw]
            if not matched.empty:
                ai_case_result = matched.iloc[0].to_dict()
        except Exception:
            pass

    # Also check session state for a freshly-run AI result
    session_ai = st.session_state.get("ai_result", {})
    if st.session_state.get("ai_case_id") == rv_case_raw and not session_ai.get("ai_error"):
        ai_case_result = session_ai

    ai_root_cause = str(ai_case_result.get("root_cause", "")).strip()
    ai_confidence = str(ai_case_result.get("confidence", "")).strip()
    ai_error = str(ai_case_result.get("ai_error", "False")).strip().lower() == "true"

    col_rv1, col_rv2 = st.columns(2)

    with col_rv1:
        st.subheader("AI Diagnosis")
        if ai_error or not ai_root_cause:
            st.error(
                "No valid AI diagnosis available for this case. "
                "Run the AI diagnosis in the **Troubleshoot** tab first, "
                "or run all cases via the batch runner."
            )
            if ai_case_result.get("ai_error_message"):
                st.caption(f"Error: {ai_case_result['ai_error_message']}")
            ai_root_cause_display = "N/A"
        else:
            st.write(f"**Root Cause:** {ai_root_cause}")
            st.write(f"**Confidence:** {ai_confidence}")

            fix_raw = ai_case_result.get("fix_steps", "[]")
            try:
                fix_list = json.loads(fix_raw) if isinstance(fix_raw, str) else fix_raw
            except Exception:
                fix_list = []
            if fix_list:
                with st.expander("AI Fix Steps"):
                    for step in fix_list:
                        st.write(f"• {step}")

            ai_root_cause_display = ai_root_cause

    with col_rv2:
        st.subheader("Your Review")

        # Load existing review if any
        existing = get_review_for_case(rv_case_raw)

        review_status = st.radio(
            "Review Status",
            ["Accepted", "Edited", "Rejected"],
            index=["Accepted", "Edited", "Rejected"].index(
                existing.get("review_status", "Accepted")
            ) if existing else 0,
            key="rv_status",
            horizontal=True,
        )

        # human_root_cause pre-fill logic
        if review_status == "Accepted":
            default_hrc = existing.get("human_root_cause", ai_root_cause_display) \
                if existing else ai_root_cause_display
            hrc_help = "Pre-filled from AI diagnosis (editable). Agreement is computed from both values."
        elif review_status == "Edited":
            default_hrc = existing.get("human_root_cause", ai_root_cause_display) \
                if existing else ai_root_cause_display
            hrc_help = "Edit this to reflect your corrected diagnosis. Agreement computed from comparison."
        else:  # Rejected
            default_hrc = existing.get(
                "human_root_cause",
                "Undetermined — AI diagnosis rejected without a confirmed alternative"
            ) if existing else "Undetermined — AI diagnosis rejected without a confirmed alternative"
            hrc_help = (
                "Enter your diagnosis, or leave as 'Undetermined — AI diagnosis rejected without "
                "a confirmed alternative' if you cannot confirm the cause."
            )

        human_root_cause = st.text_input(
            "Your Root Cause Diagnosis (required)",
            value=default_hrc,
            key="rv_human_rc",
            help=hrc_help,
        )

        reviewer_notes = st.text_area(
            f"Reviewer Notes {'(required for Edited/Rejected)' if review_status != 'Accepted' else '(optional)'}",
            value=existing.get("reviewer_notes", "") if existing else "",
            key="rv_notes",
            height=100,
            placeholder="Explain what was correct or incorrect about the AI diagnosis…",
        )

        # Preview computed agreement
        if ai_root_cause_display and human_root_cause:
            preview_agree = ai_root_cause_display.strip().lower() == human_root_cause.strip().lower()
            agree_icon = "✅ True" if preview_agree else "❌ False"
            st.caption(
                f"**Agreement preview:** `normalize('{ai_root_cause_display}') == "
                f"normalize('{human_root_cause}')` → **{agree_icon}**"
            )

        # Save button
        if st.button("💾 Save Review", key="btn_save_review", type="primary"):
            rc_to_save = ai_root_cause_display if ai_error else ai_root_cause_display
            success, message = save_review(
                case_id=rv_case_raw,
                ai_root_cause=rc_to_save,
                ai_confidence=ai_confidence,
                review_status=review_status,
                human_root_cause=human_root_cause,
                reviewer_notes=reviewer_notes,
            )
            if success:
                st.success(f"✅ {message}")
                # Refresh reviewed_ids
                st.rerun()
            else:
                st.error(f"❌ {message}")

    st.divider()

    # ── Review History ────────────────────────────────────────────────────────
    st.subheader("📋 Review History")
    reviews_df = load_reviews()

    if reviews_df.empty:
        st.info("No reviews yet.")
    else:
        stats = get_agreement_stats()
        c1, c2, c3 = st.columns(3)
        c1.metric("Total Reviewed", stats["total_reviewed"])
        c2.metric("Agreement", f"{stats['agreement_count']} ({stats['agreement_pct']}%)")
        c3.metric("Disagreement", stats["disagreement_count"])

        # Color the agreement column
        def style_agreement(val):
            if str(val).strip().lower() == "true":
                return "color: #68d391"
            return "color: #fc8181"

        styled = reviews_df.style.applymap(style_agreement, subset=["agreement"])
        st.dataframe(styled, hide_index=True, use_container_width=True)

# =============================================================================
# TAB 3: DASHBOARD
# =============================================================================

with tab_dashboard:
    render_dashboard()
