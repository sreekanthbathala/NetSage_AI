# Packet Tracer Verification Status

## Statement of Honesty

The cases in the NetSage AI dataset (`data/cases.csv`) are **carefully designed lab scenarios**
consistent with real Cisco networking behavior. Each case's `show_command_output` is crafted
to reflect authentic Cisco IOS output that would be observed in a real lab environment for the
described fault condition.

**However: designing a realistic scenario is not the same as building and running it.**

Only cases marked `verified_in_packet_tracer = TRUE` in `data/cases.csv` have been
**physically built, configured, and confirmed** in Cisco Packet Tracer by the student. As of
initial project submission, verification is limited to the following:

| Case ID | Status | Notes |
|---------|--------|-------|
| NS-014 | Pending (FALSE) | Designed for PT verification — router-on-a-stick, 2 VLANs, 1 router, 1 server. Student must build and flip to TRUE after confirming. |
| All others | FALSE | Verified logically against Cisco documentation and IOS behavior but not yet built in PT. |

## How to Verify a Case in Packet Tracer

1. Read the case's `topology_note` and `show_command_output` in `cases.csv`.
2. Build the corresponding topology in Cisco Packet Tracer using the described devices.
3. Intentionally introduce the fault described by `expected_fault`.
4. Run the `show` commands listed in `show_command_output` and confirm the output matches.
5. Apply `expected_fix_summary` and confirm the fault is resolved.
6. Update `verified_in_packet_tracer` to `TRUE` for that case in `cases.csv`.

## Demo Case: NS-014

**Title:** Inter-VLAN Routing Failure — PC Cannot Reach Server in VLAN 30

**Topology (reproducible in Packet Tracer):**
- 1x Router (e.g. Cisco 1941)
- 1x Switch (e.g. Cisco 2960)
- 1x PC in VLAN 10 (e.g. 192.168.10.5)
- 1x Server in VLAN 30 (e.g. 192.168.30.10)
- Router port Gi0/0 connected to switch trunk port
- Sub-interfaces: Gi0/0.10 (VLAN 10) and Gi0/0.30 (VLAN 30, intentionally misconfigured — no IP address)

**Fault introduced:** `GigabitEthernet0/0.30` has no `encapsulation dot1Q 30` or `ip address`,
so VLAN 30 traffic cannot be routed and the server is unreachable.

**Expected student action:** Configure the missing sub-interface, then verify with `ping 192.168.30.10` from the PC.

---
*This document must be updated by the student whenever a new case is verified in Packet Tracer.*
