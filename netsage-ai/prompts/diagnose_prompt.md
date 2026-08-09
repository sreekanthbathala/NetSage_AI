# NetSage AI — Diagnosis Prompt Template

The following is the diagnosis request template. In the code, the fields in `{curly_braces}` are
replaced with real values from the case before being sent to the AI.

---

## Diagnosis Request

**Case ID:** {case_id}

**Symptom:**
{symptom}

**Topology:**
{topology_note}

**Show Command Output (evidence):**
```
{show_command_output}
```

---

Based ONLY on the show command output above, diagnose this network fault.

Return ONLY a JSON object with this exact structure:

```json
{
  "case_id": "{case_id}",
  "root_cause": "<one of: VLAN | Gateway | DHCP | DNS | Routing | ACL | NAT | Wireless | Other>",
  "osi_layer": "<e.g. Layer 2, Layer 3, Layer 4, Layer 7>",
  "confidence": "<Low | Medium | High>",
  "evidence": [
    "<exact quote or close paraphrase from show command output above>",
    "<another quote from the output>"
  ],
  "next_command": "<a single valid Cisco show/debug command to further investigate>",
  "fix_steps": [
    "<first corrective action>",
    "<second corrective action if needed>"
  ]
}
```

Important: Use ONLY evidence from the show command output provided. Do not invent evidence.
Return ONLY the JSON — no other text.
