# NetSage AI — Few-Shot Examples

These are worked examples demonstrating the exact JSON schema the model must return.
They are included in the diagnosis prompt for few-shot learning.

---

## Example 1 — VLAN Fault

**Case ID:** NS-EX-001

**Symptom:** PC1 in VLAN 10 cannot reach the printer in VLAN 10 even though both show link up.

**Topology:** SW1 with PC1 on Fa0/1, Printer on Fa0/2. No trunk yet.

**Show Command Output:**
```
Switch#show vlan brief
VLAN Name                             Status    Ports
----  -------------------------------- --------- -------------------------------
1    default                          active    Fa0/1, Fa0/2
10   STAFF                            active

Switch#show interfaces Fa0/1 switchport
Name: Fa0/1
Administrative Mode: static access
Access Mode VLAN: 1 (default)
```

**Expected JSON Response:**
```json
{
  "case_id": "NS-EX-001",
  "root_cause": "VLAN",
  "osi_layer": "Layer 2",
  "confidence": "High",
  "evidence": [
    "Fa0/1, Fa0/2 appear under VLAN 1 (default) in show vlan brief, not under VLAN 10",
    "Access Mode VLAN: 1 (default) confirms Fa0/1 is not in VLAN 10"
  ],
  "next_command": "show interfaces Fa0/2 switchport",
  "fix_steps": [
    "interface Fa0/1",
    "switchport mode access",
    "switchport access vlan 10",
    "interface Fa0/2",
    "switchport mode access",
    "switchport access vlan 10"
  ]
}
```

---

## Example 2 — DHCP Relay Missing

**Case ID:** NS-EX-002

**Symptom:** PC receives 169.254.x.x address. DHCP server is on a different subnet.

**Topology:** PC on VLAN 10 (sub-interface Gi0/0.10), DHCP server on VLAN 20.

**Show Command Output:**
```
Router#show running-config interface gi0/0.10
interface GigabitEthernet0/0.10
 encapsulation dot1Q 10
 ip address 192.168.10.1 255.255.255.0

Router#show ip interface gi0/0.10
GigabitEthernet0/0.10 is up, line protocol is up
  Internet address is 192.168.10.1/24
  Helper address is not set
```

**Expected JSON Response:**
```json
{
  "case_id": "NS-EX-002",
  "root_cause": "DHCP",
  "osi_layer": "Layer 3",
  "confidence": "High",
  "evidence": [
    "Helper address is not set on GigabitEthernet0/0.10",
    "DHCP broadcasts from VLAN 10 clients cannot reach the server on a different subnet without a relay"
  ],
  "next_command": "show ip dhcp pool",
  "fix_steps": [
    "interface GigabitEthernet0/0.10",
    "ip helper-address <DHCP-server-IP>"
  ]
}
```

---

## Example 3 — Static Route Missing

**Case ID:** NS-EX-003

**Symptom:** Hosts on 192.168.1.0/24 cannot reach 10.2.0.0/24 network behind R2.

**Topology:** R1 Serial0/0 connects to R2 Serial0/0 via 10.0.0.0/30 link.

**Show Command Output:**
```
Router R1#show ip route
Codes: C - connected, S - static

Gateway of last resort is not set

C    10.0.0.0/30 is directly connected, Serial0/0
C    192.168.1.0/24 is directly connected, GigabitEthernet0/0
```

**Expected JSON Response:**
```json
{
  "case_id": "NS-EX-003",
  "root_cause": "Routing",
  "osi_layer": "Layer 3",
  "confidence": "High",
  "evidence": [
    "show ip route on R1 shows no route to 10.2.0.0/24",
    "Only connected routes are present: 10.0.0.0/30 and 192.168.1.0/24"
  ],
  "next_command": "traceroute 10.2.0.1",
  "fix_steps": [
    "ip route 10.2.0.0 255.255.255.0 10.0.0.2"
  ]
}
```
