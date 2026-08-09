"""
ai/diagnose.py
---------------
Orchestrates the AI diagnosis for a single case.

Responsibilities:
  1. Load the system prompt (with few-shot examples) from prompts/
  2. Build a user prompt for the specific case
  3. Call the selected provider via provider_factory.get_provider()
  4. Validate the response via schema_validator
  5. Retry once on schema validation failure
  6. On ProviderConfigError / ProviderCallError: return an error object (never fabricate)
  7. Save results to results/ai_results.csv

This module NEVER imports a provider-specific SDK — it only talks to the Provider interface.
"""

import os
import json
import datetime
import pandas as pd
from pathlib import Path

from ai.providers.base import ProviderConfigError, ProviderCallError
from ai.providers.provider_factory import get_provider
from ai.schema_validator import validate_diagnosis

# Paths
BASE_DIR = Path(__file__).parent.parent
PROMPTS_DIR = BASE_DIR / "prompts"
RESULTS_FILE = BASE_DIR / "results" / "ai_results.csv"

# AI results CSV columns
RESULTS_COLUMNS = [
    "case_id",
    "provider_used",
    "root_cause",
    "osi_layer",
    "confidence",
    "evidence",
    "next_command",
    "fix_steps",
    "matches_expected",
    "ai_error",
    "ai_error_message",
    "timestamp",
]


def _load_prompt_file(filename: str) -> str:
    """Load a prompt file from the prompts directory."""
    path = PROMPTS_DIR / filename
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return f"[Prompt file not found: {filename}]"


def _build_system_prompt() -> str:
    """Combine the system prompt with the few-shot examples."""
    system = _load_prompt_file("system_prompt.md")
    examples = _load_prompt_file("examples.md")
    return f"{system}\n\n---\n\n## Few-Shot Examples\n\n{examples}"


def _build_user_prompt(case: dict) -> str:
    """Build the user prompt for a single case, substituting case field values."""
    template = _load_prompt_file("diagnose_prompt.md")
    # Replace template placeholders
    prompt = template
    for key, value in case.items():
        prompt = prompt.replace(f"{{{key}}}", str(value) if value is not None else "")
    return prompt


def _make_error_result(case_id: str, provider_name: str, error_message: str) -> dict:
    """Create a structured error result — never a fabricated diagnosis."""
    return {
        "case_id": case_id,
        "provider_used": provider_name,
        "root_cause": "",
        "osi_layer": "",
        "confidence": "",
        "evidence": [],
        "next_command": "",
        "fix_steps": [],
        "matches_expected": False,
        "ai_error": True,
        "ai_error_message": error_message,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }


def diagnose_case(case: dict) -> dict:
    """
    Run AI diagnosis on a single case row from cases.csv.

    Args:
        case: A dict with keys from cases.csv (case_id, symptom, topology_note,
              show_command_output, expected_fault, etc.)

    Returns:
        A dict with all diagnosis fields + metadata (provider_used, ai_error, etc.).
        On error, ai_error=True and diagnosis fields are blank — NEVER fabricated.
    """
    case_id = str(case.get("case_id", "unknown"))
    expected_fault = str(case.get("expected_fault", ""))
    show_output = str(case.get("show_command_output", ""))

    # Determine provider name for logging
    provider_name = os.environ.get("AI_PROVIDER", "ollama")

    # Get provider instance
    try:
        provider = get_provider()
    except ProviderConfigError as e:
        return _make_error_result(case_id, provider_name, str(e))

    # Build prompts
    system_prompt = _build_system_prompt()
    user_prompt = _build_user_prompt(case)

    # Call provider — retry once on schema validation failure
    raw_response = None
    diagnosis = None
    validation_error = None

    for attempt in range(2):
        try:
            raw_response = provider.diagnose(system_prompt, user_prompt)
        except ProviderConfigError as e:
            return _make_error_result(case_id, provider_name, str(e))
        except ProviderCallError as e:
            return _make_error_result(
                case_id, provider_name,
                f"Provider call failed (attempt {attempt + 1}/2): {e}"
            )

        # Validate the response
        diagnosis, validation_error = validate_diagnosis(raw_response, show_output, case_id)
        if diagnosis is not None:
            break  # Valid response on this attempt

        # On first failure, tell the provider it needs to fix the output (via retry)
        # We don't modify the prompt here; the retry inherits the original prompt

    if diagnosis is None:
        # Both attempts failed validation
        return _make_error_result(
            case_id, provider_name,
            f"AI response failed schema validation after 2 attempts: {validation_error}. "
            f"Raw output: {str(raw_response)[:300]}"
        )

    # Compute matches_expected (informational only — not a substitute for human review)
    ai_root_cause = str(diagnosis.get("root_cause", "")).strip().lower()
    matches_expected = ai_root_cause == expected_fault.strip().lower()

    return {
        "case_id": case_id,
        "provider_used": provider_name,
        "root_cause": diagnosis.get("root_cause", ""),
        "osi_layer": diagnosis.get("osi_layer", ""),
        "confidence": diagnosis.get("confidence", ""),
        "evidence": json.dumps(diagnosis.get("evidence", [])),
        "next_command": diagnosis.get("next_command", ""),
        "fix_steps": json.dumps(diagnosis.get("fix_steps", [])),
        "matches_expected": matches_expected,
        "ai_error": False,
        "ai_error_message": "",
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }


def run_all_cases(cases_df: pd.DataFrame) -> pd.DataFrame:
    """
    Run AI diagnosis on all cases in the DataFrame.

    Args:
        cases_df: DataFrame loaded from data/cases.csv

    Returns:
        DataFrame of all results (written to results/ai_results.csv).
    """
    results = []
    for _, row in cases_df.iterrows():
        result = diagnose_case(row.to_dict())
        results.append(result)

    results_df = pd.DataFrame(results, columns=RESULTS_COLUMNS)

    # Save to results/ai_results.csv
    RESULTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    results_df.to_csv(RESULTS_FILE, index=False)

    return results_df


def get_diagnosis_for_case(case: dict) -> dict:
    """
    Convenience wrapper used by the Streamlit UI.
    Returns the structured diagnosis dict (or error dict) for a single case.
    """
    return diagnose_case(case)
