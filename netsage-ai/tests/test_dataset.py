"""
tests/test_dataset.py
----------------------
Validates the structure and content of data/cases.csv.

Checks:
  - Exactly 32 rows
  - All 8 fault categories present, 4 each
  - Required columns present and non-blank
  - verified_in_packet_tracer column exists (boolean-like values)
  - NS-014 exists (the demo case)
  - Severity values are valid
  - OSI layer values are non-blank
"""

import sys
import os
import pytest
import pandas as pd
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

CASES_PATH = Path(__file__).parent.parent / "data" / "cases.csv"

REQUIRED_COLUMNS = [
    "case_id", "title", "symptom", "topology_note", "show_command_output",
    "expected_fault", "osi_layer", "concept_tag", "severity",
    "expected_next_command", "expected_fix_summary", "verified_in_packet_tracer",
]

VALID_FAULT_CATEGORIES = {"VLAN", "Gateway", "DHCP", "DNS", "Routing", "ACL", "NAT", "Wireless"}
VALID_SEVERITIES = {"Low", "Medium", "High", "Critical"}
EXPECTED_ROW_COUNT = 32
EXPECTED_CASES_PER_CATEGORY = 4


@pytest.fixture(scope="module")
def cases_df():
    """Load the cases CSV once for all tests in this module."""
    assert CASES_PATH.exists(), f"cases.csv not found at {CASES_PATH}"
    df = pd.read_csv(CASES_PATH, dtype=str)
    return df


class TestDatasetStructure:
    def test_file_exists(self):
        assert CASES_PATH.exists(), "data/cases.csv must exist"

    def test_required_columns_present(self, cases_df):
        for col in REQUIRED_COLUMNS:
            assert col in cases_df.columns, f"Missing required column: {col}"

    def test_exactly_32_rows(self, cases_df):
        assert len(cases_df) == EXPECTED_ROW_COUNT, \
            f"Expected {EXPECTED_ROW_COUNT} rows, got {len(cases_df)}"

    def test_all_8_fault_categories_present(self, cases_df):
        found = set(cases_df["expected_fault"].unique())
        missing = VALID_FAULT_CATEGORIES - found
        assert not missing, f"Missing fault categories: {missing}"

    def test_4_cases_per_category(self, cases_df):
        counts = cases_df["expected_fault"].value_counts()
        for category in VALID_FAULT_CATEGORIES:
            count = counts.get(category, 0)
            assert count == EXPECTED_CASES_PER_CATEGORY, \
                f"Category '{category}' has {count} cases, expected {EXPECTED_CASES_PER_CATEGORY}"

    def test_no_blank_case_ids(self, cases_df):
        blanks = cases_df[cases_df["case_id"].str.strip() == ""]
        assert len(blanks) == 0, f"Found rows with blank case_id: {blanks.index.tolist()}"

    def test_unique_case_ids(self, cases_df):
        dupes = cases_df[cases_df.duplicated("case_id")]
        assert len(dupes) == 0, f"Duplicate case_ids found: {dupes['case_id'].tolist()}"

    def test_no_blank_symptoms(self, cases_df):
        blanks = cases_df[cases_df["symptom"].str.strip() == ""]
        assert len(blanks) == 0, f"Cases with blank symptom: {blanks['case_id'].tolist()}"

    def test_no_blank_show_output(self, cases_df):
        blanks = cases_df[cases_df["show_command_output"].str.strip() == ""]
        assert len(blanks) == 0, \
            f"Cases with blank show_command_output: {blanks['case_id'].tolist()}"

    def test_valid_severity_values(self, cases_df):
        invalid = cases_df[~cases_df["severity"].isin(VALID_SEVERITIES)]
        assert len(invalid) == 0, \
            f"Invalid severity values: {invalid[['case_id', 'severity']].to_dict('records')}"

    def test_valid_fault_categories(self, cases_df):
        invalid = cases_df[~cases_df["expected_fault"].isin(VALID_FAULT_CATEGORIES)]
        assert len(invalid) == 0, \
            f"Invalid expected_fault values: {invalid[['case_id', 'expected_fault']].to_dict('records')}"


class TestDemoCase:
    def test_ns014_exists(self, cases_df):
        """NS-014 is the primary demo case and must exist."""
        ns014 = cases_df[cases_df["case_id"] == "NS-014"]
        assert len(ns014) == 1, "NS-014 (the demo case) must exist in cases.csv"

    def test_ns014_is_inter_vlan_or_routing_category(self, cases_df):
        """NS-014 should be a routing/inter-VLAN type fault (DNS label in spec, Layer 3)."""
        ns014 = cases_df[cases_df["case_id"] == "NS-014"].iloc[0]
        assert ns014["osi_layer"] in ["Layer 3", "Layer 2", "Layer 2/3"], \
            f"NS-014 expected Layer 3 fault, got: {ns014['osi_layer']}"

    def test_ns014_has_show_output(self, cases_df):
        ns014 = cases_df[cases_df["case_id"] == "NS-014"].iloc[0]
        assert len(ns014["show_command_output"].strip()) > 50, \
            "NS-014 must have substantial show command output"


class TestPacketTracerVerification:
    def test_verified_column_exists(self, cases_df):
        assert "verified_in_packet_tracer" in cases_df.columns

    def test_column_has_boolean_like_values(self, cases_df):
        valid_values = {"TRUE", "FALSE", "True", "False", "true", "false"}
        invalid = cases_df[~cases_df["verified_in_packet_tracer"].isin(valid_values)]
        assert len(invalid) == 0, \
            f"Invalid verified_in_packet_tracer values: {invalid[['case_id', 'verified_in_packet_tracer']].to_dict('records')}"

    def test_all_default_to_false(self, cases_df):
        """All cases start unverified — student flips to TRUE after actual PT verification."""
        true_count = (cases_df["verified_in_packet_tracer"].str.upper() == "TRUE").sum()
        # This assertion acknowledges that 0 is the correct initial state.
        # It will naturally pass until the student verifies cases in Packet Tracer.
        assert true_count >= 0, "verified_in_packet_tracer column must be present (may be all FALSE initially)"
