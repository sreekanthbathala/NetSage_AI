# NetSage AI — Handoff Document

**Prepared for:** Next developer / OpenCode agent / grader  
**Project:** Cisco Project 2 — Applied AI + Network Troubleshooting (v2 Corrected Spec)  
**Status as of handoff:** See `docs/PROJECT_STATUS.md` for exact completion state

---

## What Is This Project?

NetSage AI is a Streamlit application that demonstrates AI-assisted network troubleshooting
with a human-in-the-loop review workflow and Responsible AI logging.

**Key design decisions (v2 corrections):**
1. **Provider-agnostic AI adapter** — swap providers via `AI_PROVIDER` env var with zero code changes
2. **No hard Anthropic dependency** — default provider is Ollama (free, local)
3. **Explicit agreement** — computed from `normalize(ai_root_cause) == normalize(human_root_cause)`, never assumed from `review_status`
4. **No fabricated data** — responsible AI log only populated from real human reviews

---

## How to Run

```bash
cd netsage-ai
pip install -r requirements.txt

# Minimal (Ollama, local, free):
cp .env.example .env
# Edit .env: set OLLAMA_MODEL to your model (e.g. llama3.1)
ollama serve   # in a separate terminal
streamlit run app.py
```

---

## What's Done

All code files are implemented and non-placeholder:
- `app.py` — 3 fully-wired Streamlit tabs
- `ai/providers/` — 4 provider implementations + factory
- `checker/rules.py` — 6 deterministic checks
- `review/review_store.py` — full review CRUD + agreement computation
- `dashboard/charts.py` — live metrics from CSV files
- `tests/` — full pytest suite (6 test files)
- `docs/` — README, PROJECT_STATUS, PACKET_TRACER_VERIFICATION

---

## What's Outstanding (Student Must Do)

### 1. ❌ Complete 5 Real Reviews (MANDATORY for submission)

The student must manually use the Human Review tab to review real AI diagnoses.
At least 5 reviews must result in `agreement=False` (Edited/Rejected with different root cause).

**Test that must pass:** `tests/test_responsible_ai.py::test_at_least_5_corrections_logged`  
**Currently:** FAILING (expected — no real reviews done yet)  
**Fix:** Do NOT generate fake data. Complete real reviews in the app.

### 2. ❌ Verify NS-014 in Packet Tracer (Recommended)

Build the demo case topology in Cisco Packet Tracer, confirm the fault and fix.
Flip `verified_in_packet_tracer=TRUE` for NS-014 in `data/cases.csv`.

### 3. ⏳ Run AI on All 32 Cases (Optional for full results CSV)

With a working AI provider: running the app and triggering AI diagnoses on all 32 cases
will populate `results/ai_results.csv`. This isn't required for the app to function.

---

## Architecture Cheat Sheet

```
app.py
  ├── checker/rules.py        → run_all_checks(show_output) → list[dict]
  ├── ai/diagnose.py          → get_diagnosis_for_case(case) → dict
  │     └── ai/providers/
  │           ├── provider_factory.py → get_provider() based on AI_PROVIDER env var
  │           └── {ollama,gemini,anthropic,openrouter}_provider.py → Provider.diagnose()
  ├── review/review_store.py  → save_review(), load_reviews(), agreement computation
  └── dashboard/charts.py     → render_dashboard()
```

---

## Key Files Reference

| File | Purpose |
|------|---------|
| `app.py` | Main Streamlit app — 3 tabs |
| `ai/providers/base.py` | Abstract `Provider` class + `ProviderConfigError`, `ProviderCallError` |
| `ai/providers/provider_factory.py` | Reads `AI_PROVIDER`, returns correct provider instance |
| `ai/schema_validator.py` | Validates AI JSON output + evidence grounding |
| `checker/rules.py` | 6 deterministic checks — no AI, pure Python |
| `review/review_store.py` | `compute_agreement()`, `save_review()`, `_regenerate_responsible_ai_log()` |
| `dashboard/charts.py` | Dashboard renders from `agreement` column directly |
| `data/cases.csv` | 32 cases, 12 columns incl. `verified_in_packet_tracer` |
| `review/reviews.csv` | Generated — one row per reviewed case |
| `logs/responsible_ai_log.csv` | Generated — only `agreement=False` rows from reviews |
| `results/ai_results.csv` | Generated — raw AI output per case |

---

## Environment Variables Reference

| Variable | Used By | Default | Required |
|----------|---------|---------|----------|
| `AI_PROVIDER` | `provider_factory.py` | `ollama` | No |
| `OLLAMA_HOST` | `ollama_provider.py` | `http://localhost:11434` | No |
| `OLLAMA_MODEL` | `ollama_provider.py` | `llama3.1` | Recommended |
| `GEMINI_API_KEY` | `gemini_provider.py` | — | Only if `AI_PROVIDER=gemini` |
| `GEMINI_MODEL` | `gemini_provider.py` | `gemini-1.5-flash` | No |
| `ANTHROPIC_API_KEY` | `anthropic_provider.py` | — | Only if `AI_PROVIDER=anthropic` |
| `ANTHROPIC_MODEL` | `anthropic_provider.py` | `claude-3-haiku-20240307` | No |
| `OPENROUTER_API_KEY` | `openrouter_provider.py` | — | Only if `AI_PROVIDER=openrouter` |
| `OPENROUTER_MODEL` | `openrouter_provider.py` | `mistralai/mistral-7b-instruct` | No |

---

## Running Tests

```bash
# All tests (checker tests don't need any AI provider):
pytest tests/ checker/ -v

# Expected result at handoff:
#   PASSED: all tests EXCEPT test_at_least_5_corrections_logged
#   FAILED: test_at_least_5_corrections_logged (intentionally — student must do real reviews)
```
