"""
ai/schema_validator.py
------------------------
Validates AI diagnosis output against the required JSON schema.

Provider-agnostic — works the same regardless of which AI provider produced the output.
Performs:
  1. JSON parsing
  2. Required keys check
  3. Enum value validation (root_cause, confidence)
  4. Evidence grounding check — at least one evidence string must be a substring
     of the case's actual show_command_output (prevents hallucinated evidence)
"""

import json
import re
from typing import Tuple, Optional

# Allowed enum values
VALID_ROOT_CAUSES = {"VLAN", "Gateway", "DHCP", "DNS", "Routing", "ACL", "NAT", "Wireless", "Other"}
VALID_CONFIDENCE = {"Low", "Medium", "High"}
REQUIRED_KEYS = {"case_id", "root_cause", "osi_layer", "confidence", "evidence", "next_command", "fix_steps"}


def extract_json(raw_text: str) -> Optional[str]:
    """
    Attempt to extract a JSON object from raw text that may contain extra content.
    Handles cases where the model wraps the JSON in markdown fences.

    Returns:
        The extracted JSON string, or None if no JSON object found.
    """
    # First: try the raw text directly
    raw_text = raw_text.strip()
    if raw_text.startswith("{"):
        return raw_text

    # Second: strip markdown code fences (```json ... ``` or ``` ... ```)
    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw_text, re.DOTALL)
    if fence_match:
        return fence_match.group(1)

    # Third: extract the first { ... } block
    brace_match = re.search(r"\{.*\}", raw_text, re.DOTALL)
    if brace_match:
        return brace_match.group(0)

    return None


def validate_diagnosis(
    raw_text: str,
    show_command_output: str,
    case_id: str
) -> Tuple[Optional[dict], Optional[str]]:
    """
    Parse and validate raw AI text output against the NetSage AI diagnosis schema.

    Args:
        raw_text: The raw string response from the AI provider.
        show_command_output: The actual show command output from the case (for evidence grounding).
        case_id: The expected case ID (for cross-checking).

    Returns:
        A tuple of (parsed_dict, error_message).
        - If valid: (dict, None)
        - If invalid: (None, "human-readable error explaining what failed")
    """
    if not raw_text or not raw_text.strip():
        return None, "AI returned an empty response."

    # Step 1: Extract JSON
    json_str = extract_json(raw_text)
    if json_str is None:
        return None, f"Could not find a JSON object in AI response. Raw output: {raw_text[:300]}"

    # Step 2: Parse JSON
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        return None, f"AI response is not valid JSON: {e}. Extracted: {json_str[:300]}"

    if not isinstance(data, dict):
        return None, f"AI response JSON is not an object (got {type(data).__name__})."

    # Step 3: Required keys
    missing_keys = REQUIRED_KEYS - set(data.keys())
    if missing_keys:
        return None, f"AI response is missing required keys: {', '.join(sorted(missing_keys))}"

    # Step 4: Validate root_cause enum
    root_cause = str(data.get("root_cause", "")).strip()
    if root_cause not in VALID_ROOT_CAUSES:
        return None, (
            f"Invalid root_cause: '{root_cause}'. "
            f"Must be one of: {', '.join(sorted(VALID_ROOT_CAUSES))}"
        )

    # Step 5: Validate confidence enum
    confidence = str(data.get("confidence", "")).strip()
    if confidence not in VALID_CONFIDENCE:
        return None, (
            f"Invalid confidence: '{confidence}'. "
            f"Must be one of: {', '.join(sorted(VALID_CONFIDENCE))}"
        )

    # Step 6: evidence must be a non-empty list
    evidence = data.get("evidence", [])
    if not isinstance(evidence, list) or len(evidence) == 0:
        return None, "AI response 'evidence' must be a non-empty list of strings."

    # Step 7: fix_steps must be a non-empty list
    fix_steps = data.get("fix_steps", [])
    if not isinstance(fix_steps, list) or len(fix_steps) == 0:
        return None, "AI response 'fix_steps' must be a non-empty list of strings."

    # Step 8: Evidence grounding check
    # At least one evidence item must be a substring (case-insensitive) of show_command_output
    show_output_lower = show_command_output.lower()
    grounded = False
    for item in evidence:
        if isinstance(item, str) and len(item) > 10:
            # Check if at least 15 consecutive chars of the evidence appear in the show output.
            # Using 15 chars to prevent short common phrases from passing grounding
            # while allowing for minor paraphrasing in longer evidence strings.
            evidence_lower = item.lower()
            window_size = 15
            matched = False
            if len(evidence_lower) >= window_size:
                for start in range(0, len(evidence_lower) - window_size + 1):
                    chunk = evidence_lower[start:start + window_size]
                    # Skip windows that are mostly spaces or generic words
                    non_space_chars = chunk.replace(' ', '')
                    if len(non_space_chars) >= 8 and chunk in show_output_lower:
                        matched = True
                        break
            else:
                # Short evidence: require full match
                matched = evidence_lower in show_output_lower
            if matched:
                grounded = True
                break

    if not grounded:
        return None, (
            "AI evidence is not grounded in show_command_output. "
            "None of the evidence strings match the provided show command output. "
            "This likely means the AI hallucinated the evidence."
        )

    return data, None
