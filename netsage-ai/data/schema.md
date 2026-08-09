# NetSage AI — Dataset Schema

## File: `cases.csv`

This file contains 32 Cisco network lab cases across 8 fault categories (4 per category).

### Columns

| Column | Type | Description |
|--------|------|-------------|
| `case_id` | string | Unique identifier, format NS-XXX |
| `title` | string | Short human-readable title |
| `symptom` | string | What the user observes (from the student/end-user perspective) |
| `topology_note` | string | Brief description of the physical/logical topology involved |
| `show_command_output` | string | Realistic Cisco `show` command output that provides evidence of the fault |
| `expected_fault` | enum | One of: VLAN, Gateway, DHCP, DNS, Routing, ACL, NAT, Wireless |
| `osi_layer` | string | The OSI layer primarily affected (e.g. Layer 2, Layer 3, Layer 4, Layer 7) |
| `concept_tag` | string | Specific concept being tested (e.g. vlan-trunk, dhcp-relay, nat-pool) |
| `severity` | enum | Low, Medium, High, Critical |
| `expected_next_command` | string | The best next `show` command to further diagnose the issue |
| `expected_fix_summary` | string | Plain-English description of the corrective action |
| `verified_in_packet_tracer` | boolean | `TRUE` only if this case has been physically built and confirmed in Cisco Packet Tracer by the student. Defaults to `FALSE`. |

### Fault Categories (8 × 4 = 32 cases)

| Category | Case IDs |
|----------|----------|
| VLAN | NS-001, NS-002, NS-003, NS-004 |
| Gateway | NS-005, NS-006, NS-007, NS-008 |
| DHCP | NS-009, NS-010, NS-011, NS-012 |
| DNS | NS-013, NS-014, NS-015, NS-016 |
| Routing | NS-017, NS-018, NS-019, NS-020 |
| ACL | NS-021, NS-022, NS-023, NS-024 |
| NAT | NS-025, NS-026, NS-027, NS-028 |
| Wireless | NS-029, NS-030, NS-031, NS-032 |

### Demo Case

**NS-014** is the primary demo case. It uses a standard, reproducible router-on-a-stick topology (1 router, 1 switch, 2 VLANs, 1 server) that a student can rebuild in Cisco Packet Tracer. See `docs/PACKET_TRACER_VERIFICATION.md` for verification status.
