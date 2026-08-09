"""
checker/rules.py
-----------------
Deterministic network rule checker for NetSage AI.

Contains 6 independent check functions that analyze show command output
using Python string parsing and regular expressions.

IMPORTANT: This module must NEVER call any AI provider, import any AI SDK,
or depend on the AI_PROVIDER environment variable. All checks are purely
algorithmic and deterministic.
"""

import re
from typing import List, Dict, Any, Optional


def _normalize(text: str) -> str:
    """Lowercase and strip whitespace for comparison."""
    return text.strip().lower()


# ---------------------------------------------------------------------------
# Check 1: Duplicate IP Address
# ---------------------------------------------------------------------------

def check_duplicate_ip(show_output: str) -> Dict[str, Any]:
    """
    Detect duplicate IP address conflicts in show command output.

    Looks for:
      - "DUPADDR" in syslog output
      - "Duplicate address" messages
      - Multiple ARP entries with the same IP but different MACs

    Args:
        show_output: Raw Cisco show command output string.

    Returns:
        dict with keys:
          triggered (bool): True if the fault is detected.
          rule (str): Name of this rule.
          message (str): Human-readable description.
          evidence (str): The specific line(s) that triggered the rule.
    """
    rule_name = "check_duplicate_ip"
    evidence_lines = []

    lines = show_output.splitlines()
    for line in lines:
        lower = _normalize(line)
        if "dupaddr" in lower or "duplicate address" in lower:
            evidence_lines.append(line.strip())

    # Check ARP table for duplicate IPs with different MACs
    arp_ip_to_macs: Dict[str, List[str]] = {}
    arp_pattern = re.compile(
        r"Internet\s+(\d+\.\d+\.\d+\.\d+)\s+\S+\s+([0-9a-f]{4}\.[0-9a-f]{4}\.[0-9a-f]{4})",
        re.IGNORECASE,
    )
    for line in lines:
        match = arp_pattern.search(line)
        if match:
            ip = match.group(1)
            mac = match.group(2)
            arp_ip_to_macs.setdefault(ip, []).append(mac)

    for ip, macs in arp_ip_to_macs.items():
        unique_macs = list(set(macs))
        if len(unique_macs) > 1:
            evidence_lines.append(
                f"ARP duplicate: {ip} has MACs {', '.join(unique_macs)}"
            )

    triggered = len(evidence_lines) > 0
    return {
        "triggered": triggered,
        "rule": rule_name,
        "message": "Duplicate IP address conflict detected." if triggered
                   else "No duplicate IP address detected.",
        "evidence": " | ".join(evidence_lines) if evidence_lines else "",
    }


# ---------------------------------------------------------------------------
# Check 2: Subnet Mask Error
# ---------------------------------------------------------------------------

def check_subnet_mask(show_output: str) -> Dict[str, Any]:
    """
    Detect obviously incorrect subnet masks (e.g. /8, /16 where /24 is expected,
    or common misconfiguration patterns).

    Looks for:
      - Interface IP with /8, /16 mask (flags as suspicious for small labs)
      - "255.255.0.0" or "255.0.0.0" on a LAN interface

    Args:
        show_output: Raw Cisco show command output string.

    Returns:
        Same dict format as other checks.
    """
    rule_name = "check_subnet_mask"
    evidence_lines = []

    # Pattern: ip address x.x.x.x 255.255.0.0 or ip address x.x.x.x 255.0.0.0
    # on an interface that appears to be a local LAN (Gi, Fa, Vlan)
    mask_pattern = re.compile(
        r"ip address\s+(\d+\.\d+\.\d+\.\d+)\s+(255\.0\.0\.0|255\.255\.0\.0)",
        re.IGNORECASE,
    )
    for line in show_output.splitlines():
        match = mask_pattern.search(line)
        if match:
            evidence_lines.append(
                f"Potentially incorrect mask: ip address {match.group(1)} {match.group(2)}"
            )

    # Also detect CIDR /8 or /16 in "Internet address is x.x.x.x/8" or /16
    cidr_pattern = re.compile(
        r"Internet address is (\d+\.\d+\.\d+\.\d+)/(8|16)\b",
        re.IGNORECASE,
    )
    for line in show_output.splitlines():
        match = cidr_pattern.search(line)
        if match:
            evidence_lines.append(
                f"Suspicious CIDR mask: Internet address {match.group(1)}/{match.group(2)}"
            )

    triggered = len(evidence_lines) > 0
    return {
        "triggered": triggered,
        "rule": rule_name,
        "message": "Possible subnet mask misconfiguration detected." if triggered
                   else "No obvious subnet mask error detected.",
        "evidence": " | ".join(evidence_lines) if evidence_lines else "",
    }


# ---------------------------------------------------------------------------
# Check 3: Gateway Mismatch
# ---------------------------------------------------------------------------

def check_gateway_mismatch(show_output: str) -> Dict[str, Any]:
    """
    Detect gateway configuration mismatches.

    Looks for:
      - PC ipconfig showing a default gateway not present in the router's interface list
      - DHCP pool default-router on a different subnet than the pool network

    Args:
        show_output: Raw Cisco show command output string.

    Returns:
        Same dict format as other checks.
    """
    rule_name = "check_gateway_mismatch"
    evidence_lines = []

    # Extract default gateway from ipconfig output
    gw_match = re.search(r"Default Gateway[.\s]+:\s*(\d+\.\d+\.\d+\.\d+)", show_output, re.IGNORECASE)
    # Extract router interface IPs
    router_ips = re.findall(
        r"(\d+\.\d+\.\d+\.\d+)\s+YES\s+\S+\s+up\s+up",
        show_output,
        re.IGNORECASE,
    )

    if gw_match:
        pc_gateway = gw_match.group(1)
        # Check if the PC's gateway is in the list of actual router IPs
        if router_ips and pc_gateway not in router_ips:
            evidence_lines.append(
                f"PC default gateway {pc_gateway} is not an active router interface IP. "
                f"Active IPs: {', '.join(router_ips)}"
            )

    # DHCP pool: default-router not on same /24 as pool network
    pool_network_match = re.search(r"Network:\s+(\d+\.\d+\.\d+)\.\d+", show_output, re.IGNORECASE)
    default_router_match = re.search(r"Default router:\s+(\d+\.\d+\.\d+)\.\d+", show_output, re.IGNORECASE)
    if pool_network_match and default_router_match:
        pool_prefix = pool_network_match.group(1)
        gw_prefix = default_router_match.group(1)
        if pool_prefix != gw_prefix:
            evidence_lines.append(
                f"DHCP pool network prefix {pool_prefix}.x does not match "
                f"default-router prefix {gw_prefix}.x"
            )

    triggered = len(evidence_lines) > 0
    return {
        "triggered": triggered,
        "rule": rule_name,
        "message": "Gateway mismatch detected." if triggered
                   else "No gateway mismatch detected.",
        "evidence": " | ".join(evidence_lines) if evidence_lines else "",
    }


# ---------------------------------------------------------------------------
# Check 4: Interface Down
# ---------------------------------------------------------------------------

def check_interface_down(show_output: str) -> Dict[str, Any]:
    """
    Detect interfaces that are administratively down or line protocol is down.

    Looks for:
      - "administratively down" in show ip interface brief output
      - Interface status line showing "down down"

    Args:
        show_output: Raw Cisco show command output string.

    Returns:
        Same dict format as other checks.
    """
    rule_name = "check_interface_down"
    evidence_lines = []

    lines = show_output.splitlines()
    for line in lines:
        lower = _normalize(line)
        if "administratively down" in lower:
            evidence_lines.append(line.strip())
        elif re.search(r"\bdown\s+down\b", lower):
            # "Interface ... down down" — both physical and protocol down
            evidence_lines.append(line.strip())
        elif re.search(r"\bup\s+down\b", lower):
            # "Interface ... up down" — physical up but line protocol down
            evidence_lines.append(line.strip())

    triggered = len(evidence_lines) > 0
    return {
        "triggered": triggered,
        "rule": rule_name,
        "message": "Interface(s) are down or administratively shut down." if triggered
                   else "No interface down condition detected.",
        "evidence": " | ".join(evidence_lines[:5]) if evidence_lines else "",  # Cap at 5
    }


# ---------------------------------------------------------------------------
# Check 5: Missing VLAN
# ---------------------------------------------------------------------------

def check_missing_vlan(show_output: str) -> Dict[str, Any]:
    """
    Detect ports assigned to VLANs that don't exist in the VLAN database.

    Looks for:
      - "(Inactive)" next to an Access Mode VLAN in switchport output
      - A VLAN ID referenced in switchport config but absent from "show vlan brief"

    Args:
        show_output: Raw Cisco show command output string.

    Returns:
        Same dict format as other checks.
    """
    rule_name = "check_missing_vlan"
    evidence_lines = []

    lines = show_output.splitlines()

    for line in lines:
        lower = _normalize(line)
        # "(Inactive)" on an access VLAN line
        if "access mode vlan" in lower and "inactive" in lower:
            evidence_lines.append(line.strip())
        # Native VLAN mismatch
        if "native_vlan_mismatch" in lower or "native vlan mismatch" in lower:
            evidence_lines.append(line.strip())

    # Check if any switchport access vlan references a VLAN not in "show vlan brief"
    # Extract VLANs from "show vlan brief" table
    vlan_brief_vlans = set(re.findall(r"^(\d+)\s+\S+\s+active", show_output, re.MULTILINE | re.IGNORECASE))

    # Extract VLAN from "Access Mode VLAN: <N>"
    access_vlan_matches = re.findall(r"Access Mode VLAN:\s+(\d+)", show_output, re.IGNORECASE)
    for vlan_id in access_vlan_matches:
        if vlan_brief_vlans and vlan_id not in vlan_brief_vlans:
            evidence_lines.append(
                f"Access Mode VLAN {vlan_id} not found in VLAN database (active VLANs: {', '.join(sorted(vlan_brief_vlans))})"
            )

    triggered = len(evidence_lines) > 0
    return {
        "triggered": triggered,
        "rule": rule_name,
        "message": "Missing or inactive VLAN configuration detected." if triggered
                   else "No missing VLAN detected.",
        "evidence": " | ".join(evidence_lines) if evidence_lines else "",
    }


# ---------------------------------------------------------------------------
# Check 6: Missing Route
# ---------------------------------------------------------------------------

def check_missing_route(show_output: str) -> Dict[str, Any]:
    """
    Detect missing routes in the routing table.

    Looks for:
      - No default route (no "S* 0.0.0.0/0" or "Gateway of last resort is not set")
      - Only connected routes (no static or dynamic routes)
      - Routing table appears to be missing expected entries

    Args:
        show_output: Raw Cisco show command output string.

    Returns:
        Same dict format as other checks.
    """
    rule_name = "check_missing_route"
    evidence_lines = []

    lower_output = _normalize(show_output)

    # Check for "gateway of last resort is not set"
    if "gateway of last resort is not set" in lower_output:
        evidence_lines.append("Gateway of last resort is not set (no default route).")

    # Check if only connected routes — no static or dynamic
    has_static = bool(re.search(r"^S\s", show_output, re.MULTILINE))
    has_ospf = bool(re.search(r"^O\s", show_output, re.MULTILINE))
    has_eigrp = bool(re.search(r"^D\s", show_output, re.MULTILINE))
    has_rip = bool(re.search(r"^R\s", show_output, re.MULTILINE))
    has_connected = bool(re.search(r"^C\s", show_output, re.MULTILINE))

    if has_connected and not any([has_static, has_ospf, has_eigrp, has_rip]):
        evidence_lines.append(
            "Routing table contains only connected routes — no static or dynamic routes present."
        )

    triggered = len(evidence_lines) > 0
    return {
        "triggered": triggered,
        "rule": rule_name,
        "message": "Missing route(s) detected in routing table." if triggered
                   else "Routing table appears to have routes configured.",
        "evidence": " | ".join(evidence_lines) if evidence_lines else "",
    }


# ---------------------------------------------------------------------------
# Run all checks
# ---------------------------------------------------------------------------

def run_all_checks(show_output: str) -> List[Dict[str, Any]]:
    """
    Run all 6 rule checks against a show command output string.

    Args:
        show_output: Raw Cisco show command output string.

    Returns:
        List of result dicts from each check (all 6, regardless of triggered status).
    """
    checks = [
        check_duplicate_ip,
        check_subnet_mask,
        check_gateway_mismatch,
        check_interface_down,
        check_missing_vlan,
        check_missing_route,
    ]
    return [check(show_output) for check in checks]


def get_triggered_checks(show_output: str) -> List[Dict[str, Any]]:
    """
    Return only the checks that were triggered (triggered=True).
    Convenience wrapper for the UI.
    """
    return [r for r in run_all_checks(show_output) if r["triggered"]]
