"""
checker/test_rules.py
----------------------
Unit tests for checker/rules.py.

Each of the 6 rule functions has:
  - A passing test (rule NOT triggered — output is clean)
  - A failing test (rule IS triggered — fault is present)

These tests run with ZERO AI provider configured — the rule checker has no AI dependency.
"""

import os
import sys
import pytest

# Ensure the project root is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from checker.rules import (
    check_duplicate_ip,
    check_subnet_mask,
    check_gateway_mismatch,
    check_interface_down,
    check_missing_vlan,
    check_missing_route,
    run_all_checks,
    get_triggered_checks,
)


# ============================================================
# Check 1: Duplicate IP
# ============================================================

class TestCheckDuplicateIp:
    def test_clean_no_duplicate(self):
        output = """
Router#show arp
Protocol  Address          Age (min)  Hardware Addr   Type   Interface
Internet  192.168.1.1             0   aabb.cc00.0001  ARPA   GigabitEthernet0/0
Internet  192.168.1.5             5   aabb.cc00.0002  ARPA   GigabitEthernet0/0
"""
        result = check_duplicate_ip(output)
        assert result["triggered"] is False
        assert result["rule"] == "check_duplicate_ip"

    def test_dupaddr_syslog(self):
        output = """
%IP-4-DUPADDR: Duplicate address 192.168.10.1 on GigabitEthernet0/0, sourced by aabb.cc11.2222
"""
        result = check_duplicate_ip(output)
        assert result["triggered"] is True
        assert "evidence" in result
        assert len(result["evidence"]) > 0

    def test_arp_table_duplicate_macs(self):
        output = """
Router#show arp
Protocol  Address          Age (min)  Hardware Addr   Type   Interface
Internet  192.168.10.1            0   aabb.cc00.0001  ARPA   GigabitEthernet0/0
Internet  192.168.10.1            1   aabb.cc11.2222  ARPA   GigabitEthernet0/0
"""
        result = check_duplicate_ip(output)
        assert result["triggered"] is True


# ============================================================
# Check 2: Subnet Mask
# ============================================================

class TestCheckSubnetMask:
    def test_clean_correct_mask(self):
        output = """
interface GigabitEthernet0/0
 ip address 192.168.1.1 255.255.255.0
"""
        result = check_subnet_mask(output)
        assert result["triggered"] is False

    def test_class_b_mask_on_lan(self):
        output = """
interface GigabitEthernet0/0
 ip address 192.168.10.1 255.255.0.0
"""
        result = check_subnet_mask(output)
        assert result["triggered"] is True
        assert "255.255.0.0" in result["evidence"]

    def test_cidr_16_in_interface_output(self):
        output = """
GigabitEthernet0/0 is up, line protocol is up
  Internet address is 192.168.10.1/16
"""
        result = check_subnet_mask(output)
        assert result["triggered"] is True
        assert "/16" in result["evidence"]


# ============================================================
# Check 3: Gateway Mismatch
# ============================================================

class TestCheckGatewayMismatch:
    def test_clean_gateway_matches(self):
        output = """
PC>ipconfig
   Default Gateway . . . : 192.168.1.1

Router#show ip interface brief
Interface              IP-Address      OK? Method Status                Protocol
GigabitEthernet0/0     192.168.1.1     YES NVRAM  up                    up
"""
        result = check_gateway_mismatch(output)
        assert result["triggered"] is False

    def test_gateway_mismatch_detected(self):
        output = """
PC>ipconfig
   Default Gateway . . . : 192.168.20.1

Router#show ip interface brief
Interface              IP-Address      OK? Method Status                Protocol
GigabitEthernet0/0     192.168.10.1    YES NVRAM  up                    up
GigabitEthernet0/1     192.168.30.1    YES NVRAM  up                    up
"""
        result = check_gateway_mismatch(output)
        assert result["triggered"] is True
        assert "192.168.20.1" in result["evidence"]

    def test_dhcp_pool_gateway_mismatch(self):
        output = """
Router#show ip dhcp pool
Pool CLIENTS :
 Network: 172.16.1.0 255.255.255.0
 Default router: 172.16.2.1
"""
        result = check_gateway_mismatch(output)
        assert result["triggered"] is True


# ============================================================
# Check 4: Interface Down
# ============================================================

class TestCheckInterfaceDown:
    def test_clean_all_up(self):
        output = """
Interface              IP-Address      OK? Method Status                Protocol
GigabitEthernet0/0     192.168.1.1     YES NVRAM  up                    up
GigabitEthernet0/1     10.0.0.1        YES NVRAM  up                    up
"""
        result = check_interface_down(output)
        assert result["triggered"] is False

    def test_admin_down_detected(self):
        output = """
Interface              IP-Address      OK? Method Status                Protocol
GigabitEthernet0/1     10.0.1.1        YES NVRAM  administratively down down
"""
        result = check_interface_down(output)
        assert result["triggered"] is True
        assert "administratively down" in result["evidence"].lower()

    def test_line_protocol_down(self):
        output = """
Interface              IP-Address      OK? Method Status                Protocol
Serial0/0              10.0.0.1        YES NVRAM  up                    down
"""
        result = check_interface_down(output)
        assert result["triggered"] is True


# ============================================================
# Check 5: Missing VLAN
# ============================================================

class TestCheckMissingVlan:
    def test_clean_vlan_active(self):
        output = """
VLAN Name                             Status    Ports
----  -------------------------------- --------- ------
10   STAFF                            active    Fa0/1

Name: Fa0/1
Access Mode VLAN: 10 (STAFF)
"""
        result = check_missing_vlan(output)
        assert result["triggered"] is False

    def test_inactive_vlan_detected(self):
        output = """
Name: Fa0/5
Switchport: Enabled
Administrative Mode: static access
Access Mode VLAN: 30 (Inactive)
"""
        result = check_missing_vlan(output)
        assert result["triggered"] is True
        assert "inactive" in result["evidence"].lower()

    def test_vlan_not_in_database(self):
        output = """
VLAN Name                             Status    Ports
----  -------------------------------- --------- ------
1    default                          active    Fa0/1
10   STAFF                            active    Fa0/2

Name: Fa0/3
Access Mode VLAN: 30
"""
        result = check_missing_vlan(output)
        assert result["triggered"] is True


# ============================================================
# Check 6: Missing Route
# ============================================================

class TestCheckMissingRoute:
    def test_clean_has_routes(self):
        output = """
Router#show ip route
C    192.168.1.0/24 is directly connected, GigabitEthernet0/0
S    10.0.0.0/8 [1/0] via 192.168.1.2
S*   0.0.0.0/0 [1/0] via 203.0.113.1
"""
        result = check_missing_route(output)
        assert result["triggered"] is False

    def test_no_default_route(self):
        output = """
Router#show ip route
Gateway of last resort is not set

C    10.0.0.0/30 is directly connected, Serial0/0
"""
        result = check_missing_route(output)
        assert result["triggered"] is True
        assert "gateway of last resort" in result["evidence"].lower()

    def test_only_connected_routes(self):
        output = """
Router#show ip route
Codes: C - connected

C    10.0.0.0/30 is directly connected, Serial0/0
C    192.168.1.0/24 is directly connected, GigabitEthernet0/0
"""
        result = check_missing_route(output)
        assert result["triggered"] is True
        assert "only connected routes" in result["evidence"].lower()


# ============================================================
# Integration: run_all_checks and get_triggered_checks
# ============================================================

class TestRunAllChecks:
    def test_returns_six_results(self):
        result = run_all_checks("some arbitrary show output")
        assert len(result) == 6

    def test_each_has_required_keys(self):
        results = run_all_checks("Router#show ip interface brief\n")
        for r in results:
            assert "triggered" in r
            assert "rule" in r
            assert "message" in r
            assert "evidence" in r

    def test_get_triggered_checks_subset(self):
        output = """
%IP-4-DUPADDR: Duplicate address 10.0.0.1 on Gi0/0
Gateway of last resort is not set
C    10.0.0.0/30 is directly connected
"""
        triggered = get_triggered_checks(output)
        assert all(r["triggered"] is True for r in triggered)
        # Should detect both duplicate IP and missing route
        triggered_rules = {r["rule"] for r in triggered}
        assert "check_duplicate_ip" in triggered_rules
        assert "check_missing_route" in triggered_rules


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
