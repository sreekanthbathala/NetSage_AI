"""
tests/test_ai_schema.py
------------------------
Tests for AI schema validation — uses a MOCK provider, no real API key needed.

Tests:
  - Valid JSON response passes validation
  - Missing keys fail validation
  - Invalid enum values fail validation
  - Hallucinated evidence (not in show output) fails grounding check
  - Retry logic works correctly
  - Markdown-wrapped JSON is correctly extracted
"""

import sys
import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

from ai.schema_validator import validate_diagnosis, extract_json


# ─── Sample show command output for grounding tests ───────────────────────────

SAMPLE_SHOW_OUTPUT = """
Router#show ip interface brief
Interface              IP-Address      OK? Method Status                Protocol
GigabitEthernet0/0     192.168.10.1    YES NVRAM  up                    up
GigabitEthernet0/0.30  unassigned      YES unset  up                    up

Router#show running-config interface gi0/0.30
interface GigabitEthernet0/0.30
 no ip address
"""

VALID_DIAGNOSIS = {
    "case_id": "NS-014",
    "root_cause": "Routing",
    "osi_layer": "Layer 3",
    "confidence": "High",
    "evidence": [
        "GigabitEthernet0/0.30  unassigned      YES unset  up",
        "interface GigabitEthernet0/0.30 has no ip address configured"
    ],
    "next_command": "show running-config interface gi0/0.30",
    "fix_steps": [
        "interface GigabitEthernet0/0.30",
        "encapsulation dot1Q 30",
        "ip address 192.168.30.1 255.255.255.0"
    ]
}


class TestExtractJson:
    def test_raw_json_object(self):
        raw = '{"key": "value"}'
        result = extract_json(raw)
        assert result is not None
        assert "key" in result

    def test_markdown_code_fence(self):
        raw = '```json\n{"key": "value"}\n```'
        result = extract_json(raw)
        assert result is not None

    def test_json_with_preamble(self):
        raw = "Here is the diagnosis:\n\n{\"root_cause\": \"VLAN\"}"
        result = extract_json(raw)
        assert result is not None
        assert "root_cause" in result

    def test_no_json_returns_none(self):
        result = extract_json("This is just plain text with no JSON.")
        assert result is None


class TestValidateDiagnosis:
    def test_valid_response_passes(self):
        raw = json.dumps(VALID_DIAGNOSIS)
        result, error = validate_diagnosis(raw, SAMPLE_SHOW_OUTPUT, "NS-014")
        assert result is not None, f"Expected valid result but got error: {error}"
        assert error is None

    def test_empty_response_fails(self):
        result, error = validate_diagnosis("", SAMPLE_SHOW_OUTPUT, "NS-014")
        assert result is None
        assert error is not None
        assert "empty" in error.lower()

    def test_missing_required_key_fails(self):
        incomplete = {k: v for k, v in VALID_DIAGNOSIS.items() if k != "evidence"}
        raw = json.dumps(incomplete)
        result, error = validate_diagnosis(raw, SAMPLE_SHOW_OUTPUT, "NS-014")
        assert result is None
        assert "evidence" in error

    def test_invalid_root_cause_fails(self):
        bad = {**VALID_DIAGNOSIS, "root_cause": "WiFi"}  # Not in allowed enum
        raw = json.dumps(bad)
        result, error = validate_diagnosis(raw, SAMPLE_SHOW_OUTPUT, "NS-014")
        assert result is None
        assert "root_cause" in error.lower() or "Invalid" in error

    def test_invalid_confidence_fails(self):
        bad = {**VALID_DIAGNOSIS, "confidence": "Very High"}
        raw = json.dumps(bad)
        result, error = validate_diagnosis(raw, SAMPLE_SHOW_OUTPUT, "NS-014")
        assert result is None
        assert "confidence" in error.lower() or "Invalid" in error

    def test_hallucinated_evidence_fails(self):
        """Evidence that doesn't appear in show output should fail grounding check."""
        bad = {**VALID_DIAGNOSIS, "evidence": [
            "show ip ospf neighbor output shows dead timer expired",
            "EIGRP neighbor relationship is down",
        ]}
        raw = json.dumps(bad)
        result, error = validate_diagnosis(raw, SAMPLE_SHOW_OUTPUT, "NS-014")
        assert result is None
        assert "grounded" in error.lower() or "evidence" in error.lower()

    def test_grounded_evidence_passes(self):
        """Evidence that IS a substring of show output should pass."""
        good = {**VALID_DIAGNOSIS, "evidence": [
            "GigabitEthernet0/0.30  unassigned      YES unset  up",  # appears verbatim in SAMPLE_SHOW_OUTPUT
        ]}
        raw = json.dumps(good)
        result, error = validate_diagnosis(raw, SAMPLE_SHOW_OUTPUT, "NS-014")
        assert result is not None, f"Expected pass but got: {error}"

    def test_markdown_wrapped_json_passes(self):
        """Model may wrap JSON in markdown — should still parse correctly."""
        raw = f"```json\n{json.dumps(VALID_DIAGNOSIS)}\n```"
        result, error = validate_diagnosis(raw, SAMPLE_SHOW_OUTPUT, "NS-014")
        assert result is not None, f"Markdown-wrapped JSON should pass. Error: {error}"

    def test_all_valid_root_cause_values(self):
        """Test that all 9 allowed root_cause values pass validation."""
        for rc in ["VLAN", "Gateway", "DHCP", "DNS", "Routing", "ACL", "NAT", "Wireless", "Other"]:
            case = {**VALID_DIAGNOSIS, "root_cause": rc}
            raw = json.dumps(case)
            result, error = validate_diagnosis(raw, SAMPLE_SHOW_OUTPUT, "NS-014")
            assert result is not None, f"root_cause='{rc}' should be valid but got: {error}"

    def test_all_valid_confidence_values(self):
        """Test that Low, Medium, High all pass."""
        for conf in ["Low", "Medium", "High"]:
            case = {**VALID_DIAGNOSIS, "confidence": conf}
            raw = json.dumps(case)
            result, error = validate_diagnosis(raw, SAMPLE_SHOW_OUTPUT, "NS-014")
            assert result is not None, f"confidence='{conf}' should be valid but got: {error}"

    def test_empty_evidence_list_fails(self):
        bad = {**VALID_DIAGNOSIS, "evidence": []}
        raw = json.dumps(bad)
        result, error = validate_diagnosis(raw, SAMPLE_SHOW_OUTPUT, "NS-014")
        assert result is None
        assert "evidence" in error.lower()

    def test_empty_fix_steps_fails(self):
        bad = {**VALID_DIAGNOSIS, "fix_steps": []}
        raw = json.dumps(bad)
        result, error = validate_diagnosis(raw, SAMPLE_SHOW_OUTPUT, "NS-014")
        assert result is None
        assert "fix_steps" in error.lower()


class TestDiagnoseWithMockProvider:
    """Test ai/diagnose.py using a mocked provider — no real API key needed."""

    def test_diagnose_success_with_mock(self):
        """Mocked provider returning valid JSON should produce a non-error result."""
        from ai.diagnose import diagnose_case

        mock_raw = json.dumps(VALID_DIAGNOSIS)
        mock_provider = MagicMock()
        mock_provider.diagnose.return_value = mock_raw

        case = {
            "case_id": "NS-014",
            "symptom": "PC cannot reach server in VLAN 30",
            "topology_note": "Router-on-a-stick",
            "show_command_output": SAMPLE_SHOW_OUTPUT,
            "expected_fault": "Routing",
        }

        with patch("ai.diagnose.get_provider", return_value=mock_provider):
            result = diagnose_case(case)

        assert result["ai_error"] is False
        assert result["root_cause"] == "Routing"
        assert result["confidence"] == "High"

    def test_diagnose_provider_config_error(self):
        """ProviderConfigError should produce ai_error=True, not fabricate."""
        from ai.diagnose import diagnose_case
        from ai.providers.base import ProviderConfigError

        case = {
            "case_id": "NS-014",
            "symptom": "test",
            "topology_note": "test",
            "show_command_output": SAMPLE_SHOW_OUTPUT,
            "expected_fault": "Routing",
        }

        with patch("ai.diagnose.get_provider", side_effect=ProviderConfigError("No API key")):
            result = diagnose_case(case)

        assert result["ai_error"] is True
        assert "No API key" in result["ai_error_message"]
        assert result["root_cause"] == ""  # No fabricated diagnosis

    def test_diagnose_bad_json_retries_then_errors(self):
        """If provider always returns bad JSON, ai_error=True after 2 attempts."""
        from ai.diagnose import diagnose_case

        mock_provider = MagicMock()
        mock_provider.diagnose.return_value = "This is not JSON at all!!!"

        case = {
            "case_id": "NS-999",
            "symptom": "test",
            "topology_note": "test",
            "show_command_output": SAMPLE_SHOW_OUTPUT,
            "expected_fault": "VLAN",
        }

        with patch("ai.diagnose.get_provider", return_value=mock_provider):
            result = diagnose_case(case)

        assert result["ai_error"] is True
        assert mock_provider.diagnose.call_count == 2  # Retried once
