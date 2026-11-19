# PROJECT_AUDIT.md
## Technical Audit Report — Wi-Fi Safety Assistant
**IBM Inter-Institute Hackathon · Bengaluru Commuter Cybersecurity**
**Audit date:** 2026-11-19 · **Auditor:** Bob (IBM)

---

## Table of Contents

1. [Project Structure](#1-project-structure)
2. [Three AI Agents — Actual Implementation](#2-three-ai-agents--actual-implementation)
3. [Supervisor / Orchestrator](#3-supervisor--orchestrator)
4. [AI Provider Integrations](#4-ai-provider-integrations)
5. [Backend — Flask API](#5-backend--flask-api)
6. [Database](#6-database)
7. [Security & Guardrails](#7-security--guardrails)
8. [Frontend & Dashboard](#8-frontend--dashboard)
9. [Bugs & Issues Found](#9-bugs--issues-found)
10. [Features Documented But Not Implemented](#10-features-documented-but-not-implemented)
11. [How to Test Each Agent and Verify Genuine AI Responses](#11-how-to-test-each-agent-and-verify-genuine-ai-responses)
12. [Quick-Reference Issue Table](#12-quick-reference-issue-table)

---

## 1. Project Structure

```
ibm hackathon/
├── .env                        # API keys — present, loaded correctly
├── .env.example                # Placeholder template — present
├── .gitignore                  # Present; .env correctly excluded
├── requirements.txt            # 15 packages (see §9 bug B1 — streamlit added)
├── run.py                      # Waitress launcher — works
├── Procfile                    # gunicorn for Render deploy — present
├── render.yaml                 # Render blueprint — present
├── backend/
│   ├── app.py                  # Flask app + 7 routes — fully implemented
│   ├── config.py               # Typed config from .env — works
│   ├── database.py             # SQLAlchemy ORM, SQLite/MySQL — works
│   ├── wsgi.py                 # WSGI entry point — works
│   ├── agents/
│   │   ├── agent1_risk.py      # Network Risk Assessment — implemented
│   │   ├── agent2_device.py    # Device Safety & Prevention — implemented
│   │   ├── agent3_incident.py  # Incident Response — implemented (see §9 bug B2)
│   │   └── supervisor.py       # Orchestrator — implemented
│   ├── services/
│   │   ├── granite_service.py  # IBM watsonx.ai — implemented, working
│   │   ├── gemini_service.py   # Google Gemini — implemented (see §9 bug B3)
│   │   ├── groq_service.py     # Groq — FILE EXISTS but provider is DISABLED
│   │   └── ai_model_manager.py # Centralized manager — implemented
│   └── security/
│       └── guardrails.py       # Input validation, PII, rate limiting — implemented
├── frontend/
│   ├── index.html              # 5-panel SPA — implemented
│   └── static/
│       ├── css/style.css       # Cybersecurity dark theme — implemented
│       └── js/app.js           # Dashboard logic — implemented
└── tests/
    ├── test_agents.py          # 17 tests — all passing
    └── test_api.py             # 12 tests — all passing
```

---

## 2. Three AI Agents — Actual Implementation

### Agent 1: NetworkRiskAgent (`backend/agents/agent1_risk.py`)

**What it actually does:**

1. **Rule-based pre-analysis** (`_pre_analyze()`): Before any AI call, it runs
   pure-Python regex matching against 25 suspicious SSID patterns (e.g.
   `free.*wifi`, `sbi.*wifi`, IP-as-SSID), checks the connection type against
   known insecure types (`open`, `wep`, `wep`, `none`), inspects location for
   risky public places, and scans `user_context` for 15 high-risk text
   indicators (e.g. `login portal`, `certificate warning`, `same name as`).
   Produces `{pre_risk: HIGH|MEDIUM|LOW, flags: [...]}`.

2. **IBM Granite LLM call**: Constructs a detailed prompt embedding the
   SSID, connection type, location, user context, pre-analysis flags, and
   the pre-risk estimate. Requests JSON output with keys `risk_level`,
   `risk_score`, `warning_signs`, `risk_factors`, `positive_indicators`,
   `explanation`, `cert_in_reference`. Uses `provider="granite"` and
   `max_tokens=800, temperature=0.2`.

3. **JSON parsing with two fallbacks**: First tries `json.loads()`. If that
   fails, `_extract_partial()` scans the raw text for the words HIGH/MEDIUM/LOW
   and returns a partial result. If the entire AI call fails, `_fallback_assessment()`
   returns a pure-rule-based result.

4. **Data handoff**: Returns a dict containing both the AI output and the
   original input, pre-analysis flags, model name, duration, and status
   (`complete` | `complete_with_fallback` | `error`). This dict is passed
   directly to Agent 2 by the Supervisor.

**Genuine AI vs fallback:** When Granite returns `success=True`, the
`risk_level`, `explanation`, `warning_signs` etc. come from the LLM.
When it returns `success=False`, `status=complete_with_fallback` and
`summary="Rule-based assessment: X risk"` distinguish it.

---

### Agent 2: DeviceSafetyAgent (`backend/agents/agent2_device.py`)

**What it actually does:**

1. **Reads Agent 1 output**: Extracts `risk_level`, `wifi_name`, `location`,
   `warning_signs`, `explanation` from the dict passed by the Supervisor.

2. **Static checklist lookup**: Immediately loads a hardcoded checklist from
   `DEVICE_CHECKLIST_BY_RISK` (10 items for HIGH, 7 for MEDIUM, 5 for LOW)
   and banking guidance from `BANKING_GUIDANCE`. These are always returned
   regardless of AI availability.

3. **IBM Granite LLM call**: Constructs a prompt with the risk context and
   requests JSON with keys `threat_explanation`, `immediate_actions`,
   `browsing_tips`, `app_security`, `bengaluru_specific`, `recovery_note`.
   Uses `provider="granite"`, `max_tokens=900, temperature=0.25`.

4. **JSON parsing**: Same pattern as Agent 1 — `json.loads()` first, then
   `_fallback_guidance()` if parsing fails or AI is unavailable.

5. **Data handoff**: Returns a dict merging the static checklist, banking
   guidance, and the AI-generated threat narrative. The Supervisor passes
   this whole dict to Agent 3.

**Genuine AI vs fallback:** The `device_checklist` and `banking_guidance`
are always static (not AI-generated). The `threat_explanation`,
`immediate_actions`, `browsing_tips`, `app_security`, and `bengaluru_specific`
fields are from Granite when `success=True`; from the hardcoded
`_fallback_guidance()` dict when not.

---

### Agent 3: IncidentResponseAgent (`backend/agents/agent3_incident.py`)

**What it actually does:**

1. **Reads combined Agent 1 + 2 output**: Extracts risk level, wifi name,
   location, warning signs, user context, threat explanation, and immediate
   actions from both upstream agents' dicts.

2. **Scenario detection** (`_identify_scenario()`): Pure Python string matching
   against combined warning signs + user context to classify: `phishing`,
   `account_compromise`, `fake_portal`, or `general`.

3. **Static immediate response lookup**: Loads `IMMEDIATE_RESPONSE_BY_SCENARIO`
   for the detected scenario (pre-written step-by-step actions).

4. **AI call — PRIMARY_PROVIDER = "groq", BACKUP_PROVIDER = "gemini"**:
   This is the key implementation detail. `PRIMARY_PROVIDER = "groq"` is set in
   the class, but the `AIModelManager` has Groq **disabled** (remaps `"groq"` →
   `"gemini"`). So in practice, Agent 3 always calls Gemini.
   See §9 for the full analysis of this discrepancy.

5. **Final report generation** (`_generate_final_report()`): Always runs
   regardless of AI success. Assembles a complete report dict from all three
   agents' outputs including `critical_actions`, `high_priority_actions`,
   `banking_recommendation`, `incident_scenario`, `models_used`.

6. **Data handoff**: Returns all of the above plus `reporting_resources`
   (CERT-In, I4C, cybercrime.gov.in, RBI Ombudsman) to the Supervisor.

**Genuine AI vs fallback:** `status=complete` means Gemini responded.
`status=complete_with_fallback` means both Groq (disabled) and Gemini failed,
and `_fallback_response()` was used. Check `model_used` in the response — it
will say `models/gemini-3.5-flash` for genuine AI or `none`/`unknown` for
fallback.

---

## 3. Supervisor / Orchestrator

**File:** `backend/agents/supervisor.py`

**Actual orchestration flow:**

```
process_request(wifi_name, connection_type, location, user_context, client_ip)
    │
    ├─ Step 0: guardrails.validate_input()          ← blocks bad inputs
    ├─ Step 1: db.create_task()                     ← persists task to SQLite
    ├─ Step 2: agent1.assess(...)                   ← IBM Granite
    │          db.update_task(agent1_output, risk_level, agent1_duration_ms)
    │          _log_model_call(agent1_output, "Agent 1")
    ├─ Step 3: agent2.analyze(agent1_output)        ← IBM Granite
    │          db.update_task(agent2_output, agent2_duration_ms)
    │          _log_model_call(agent2_output, "Agent 2")
    ├─ Step 4: agent3.respond(agent1_output, agent2_output) ← Gemini
    │          db.update_task(agent3_output, agent3_duration_ms)
    │          _log_model_call(agent3_output, "Agent 3")
    └─ Step 5: _consolidate() → unified response
               db.update_task(status="complete", supervisor_output, total_duration_ms)
               return unified + execution_log
```

**Conflict resolution:** `_consolidate()` has a `severity_rank` dict and
`agent3_severity` variable but **does not actually use them** — `final_risk`
is always set to `a1.get("risk_level", "UNKNOWN")` from Agent 1 only.
The conflict-resolution code is scaffolded but inactive (see §9 bug B4).

**Information transfer:** Genuine structured Python dicts are passed between
agents — not strings. Agent 2 receives the full Agent 1 output dict; Agent 3
receives both Agent 1 and Agent 2 output dicts.

---

## 4. AI Provider Integrations

### IBM Granite (`backend/services/granite_service.py`)

| Property | Value |
|----------|-------|
| SDK | `ibm-watsonx-ai==1.1.2` |
| Model | `ibm/granite-4-h-small` (from `.env`) |
| Endpoint | `https://eu-de.ml.cloud.ibm.com` (Frankfurt region) |
| API method | `ModelInference.chat()` → `/ml/v1/text/chat` |
| Token counting | Estimated from word count (not actual tokens) |
| Fallback | Rule-based; `status=complete_with_fallback` |
| Tested | YES — real API call confirmed: `"IBM Granite operational"` in ~760ms |

**How it calls the API:**
```python
credentials = Credentials(url=url, api_key=api_key)
model = ModelInference(model_id="ibm/granite-4-h-small",
                       credentials=credentials,
                       project_id=project_id)
response = model.chat(
    messages=[{"role": "user", "content": prompt}],
    params={MAX_NEW_TOKENS: 800, TEMPERATURE: 0.2, REPETITION_PENALTY: 1.1}
)
text = response["choices"][0]["message"]["content"]
```

**Identity verification:** A genuine Granite response always has
`provider="granite"`, `model="ibm/granite-4-h-small"`, `success=True`, and
`duration_ms > 0`. A fallback has `success=False` and `model="none"` or the
model name from the failed attempt.

---

### Google Gemini (`backend/services/gemini_service.py`)

| Property | Value |
|----------|-------|
| SDK | `google-genai==3.6.1` (new SDK, not deprecated `google-generativeai`) |
| Model | `models/gemini-3.5-flash` (from `.env`; prefix `models/` required) |
| Timeout | 30 000 ms (30 seconds) hardcoded in `HttpOptions` |
| Token counting | Real metadata from `usage_metadata` |
| Tested | YES — API connects, 429 quota exceeded during bulk testing |

**Known issue:** `response.text` can be `None` on `gemini-3.5-flash` with
short prompts. The service falls back to extracting from
`response.candidates[0].content.parts`. If parts are also empty, text is `""`.
`success` is still `True` — the connection succeeded but the model returned
empty content. The `note` field is set in this case.

**How it calls the API:**
```python
client = genai.Client(api_key=api_key,
                      http_options=HttpOptions(timeout=30000))
response = client.models.generate_content(
    model="models/gemini-3.5-flash",
    contents=prompt,
    config=GenerateContentConfig(max_output_tokens=900, temperature=0.2)
)
```

---

### Groq (`backend/services/groq_service.py`)

| Property | Value |
|----------|-------|
| SDK | `groq==1.7.0` (installed in venv) |
| Status | **DISABLED in `ai_model_manager.py`** |
| Configuration | `GROQ_API_KEY = ""` hardcoded in `config.py` |
| Effect | All `provider="groq"` calls are silently remapped to `"gemini"` |

The `groq_service.py` file is a full, correct implementation — it would work
if given a key. It was disabled during the two-provider reconfiguration.
Agent 3 still declares `PRIMARY_PROVIDER = "groq"` in its class, which is
misleading since the manager remaps it. See §9 for details.

---

## 5. Backend — Flask API

**Server:** Waitress 3.0.2 (Windows-compatible WSGI) on port 5000.
**Entry point:** `run.py` → `backend/wsgi.py` → `backend/app.py`.

### All Implemented Routes

| Method | Route | Purpose | Auth |
|--------|-------|---------|------|
| GET | `/` | Serve `frontend/index.html` | None |
| GET | `/static/<path>` | Serve CSS/JS/img | None |
| GET | `/api/health` | Server + model status | None |
| POST | `/api/assess` | Full 3-agent pipeline | None |
| GET | `/api/models/status` | AI provider availability | None |
| POST | `/api/models/test` | Test a specific AI provider | None |
| GET | `/api/tasks` | Task history (paginated) | None |
| GET | `/api/tasks/<id>` | Single task details | None |
| GET | `/api/analytics` | Aggregated metrics | None |
| POST | `/api/chat` | AI assistant Q&A | None |

**No authentication on any route.** This is acceptable for a hackathon demo
but is a security gap for production (see §9).

**CORS:** Enabled for all `/api/*` origins — intentionally open.

### `/api/models/status` stale label (bug B5)

The route returns `"secondary": ["Google Gemini", "Groq"]` even though Groq is
disabled. It is a cosmetic string in the response, not functional, but
misleading for evaluators.

---

## 6. Database

**Engine:** SQLAlchemy 2.0.31 — SQLite in development, MySQL in production.
**SQLite path:** `wifi_safety.db` at project root (or `/tmp/wifi_safety.db`
on Render as configured in `render.yaml`).

### Tables

**`task_records`**
- Stores full input + all three agent JSON outputs per task.
- Status enum: `pending | running | complete | error`.
- Risk level enum: `LOW | MEDIUM | HIGH | UNKNOWN`.
- Timing fields: `total_duration_ms`, `agent1/2/3_duration_ms`.
- `guardrail_flags` JSON column records any security flags.

**`model_call_logs`**
- One row per AI API call.
- Stores `provider`, `model_id`, `agent_name`, `duration_ms`, `success`, `error`.
- Used to compute per-provider success rates and average latency in `/api/analytics`.

**Known issue (bug B6):** When Agent 3 falls back (Groq remapped → Gemini →
also fails), `provider="none"` is logged. The analytics query groups by
provider, so a "none" provider bucket appears in dashboard stats. It is
cosmetically confusing.

**MySQL:** The `db_url()` method tries a live MySQL connection. If that fails,
it silently falls back to SQLite. This is correct behaviour for development but
means MySQL is never actually tested unless manually configured.

---

## 7. Security & Guardrails

**File:** `backend/security/guardrails.py`

### What is implemented and tested:

| Control | Implementation | Tested |
|---------|---------------|--------|
| Rate limiting | In-memory token bucket, 30 req/min per IP | YES |
| Required field | `wifi_name` must be non-empty | YES |
| Field length truncation | wifi_name≤100, context≤1000 etc. | YES |
| HTML escaping | `html.escape()` on all inputs | YES |
| Prompt injection detection | 14 regex patterns | YES |
| Dangerous request blocking | 12 regex patterns (nmap, exploit, scan…) | YES |
| PII: password hint | Redacted to `[PASSWORD REDACTED]` | YES |
| PII: Aadhaar / credit card | Redacted in user_context | YES |
| Output validation | `OutputValidator.validate()` strips PII from AI output | YES |
| Hallucination check | 6 patterns trigger flag | YES (unit) |

### Gaps:

1. **Output validator not called in the pipeline.** `Guardrails.validate_output()`
   exists and is tested in unit tests, but `supervisor.py` never calls it.
   AI output is returned to the frontend without output validation.

2. **Rate limiter is in-memory only.** It resets on server restart and does
   not work across multiple Waitress threads or processes.

3. **No authentication on any API route.** Any client can POST `/api/assess`.

4. **`ALLOWED_CONNECTION_TYPES` is defined but never enforced.** The set is
   declared in guardrails.py but `validate_input()` does not check
   `connection_type` against it.

5. **Phone numbers detected but not redacted.** `PII_PATTERNS` includes
   `phone_number` and `bank_account` but `validate_input()` only redacts
   `password_hint`, `aadhaar`, and `credit_card`. Phone numbers are not
   redacted.

---

## 8. Frontend & Dashboard

**File:** `frontend/index.html` (SPA, 15 429 bytes)
**CSS:** `frontend/static/css/style.css` (21 651 bytes, dark cybersecurity theme)
**JS:** `frontend/static/js/app.js` (22 183 bytes)

### Five Navigation Panels — All Present

| Panel | id | Key UI elements |
|-------|----|----------------|
| Dashboard | `panel-dashboard` | Model cards, quick stats, agent pipeline visualization, CTA, resources |
| Risk Assessment | `panel-assess` | Assessment form, risk badge, checklist, banking, agent log, final report |
| AI Assistant | `panel-assistant` | Chat interface, suggested questions |
| History | `panel-history` | Task table |
| Analytics | `panel-analytics` | Provider performance bars, risk distribution, handoff rate |

### What works (verified programmatically):

- All 5 panels present in HTML DOM.
- 12 key UI element IDs confirmed present.
- 9 key JavaScript functions confirmed in source:
  `switchPanel`, `sendChat`, `loadHistory`, `loadAnalytics`, `downloadReport`,
  `renderResults`, `renderChecklist`, `renderBanking`, `animateLoadingSteps`.
- CSS served correctly (HTTP 200, 21 KB).
- JS served correctly (HTTP 200, 22 KB).

### What needs manual browser testing:

- Tab switching animation.
- Assessment form → agent cards animate during pipeline.
- Risk badge colour change (RED/AMBER/GREEN).
- Download report button saves JSON file.
- Chat interface sends message and renders Granite response.

### Known UI issue (bug B7):

The model status cards on the Dashboard use `checkHealth()` → `/api/health`
to populate `available` badges. The health endpoint returns model availability
at startup, but the badges update only on initial page load. If a provider
becomes unavailable after startup, the UI will show stale "Active" badges.

---

## 9. Bugs & Issues Found

### B1 — `streamlit` added to requirements.txt (MEDIUM)

**File:** `requirements.txt` line 15.
**Problem:** `streamlit>=1.35.0` was added externally (shown as external change
in environment metadata). Streamlit is incompatible with this Flask + Waitress
architecture. It serves its own server on port 8501, conflicts with Flask,
and is not referenced anywhere in the codebase.
**Fix:** Remove `streamlit>=1.35.0` from requirements.txt.

---

### B2 — Agent 3 `PRIMARY_PROVIDER = "groq"` is misleading (LOW, cosmetic)

**File:** `backend/agents/agent3_incident.py` line 105.
**Problem:** Class declares `PRIMARY_PROVIDER = "groq"` and docstring says
"Uses Groq (fast inference)". In reality `AIModelManager.generate(provider="groq")`
silently remaps `"groq"` → `"gemini"`. Groq is never called. The agent
effectively always uses Gemini as its primary. This is confusing to anyone
reading the code.
**Fix:** Change `PRIMARY_PROVIDER = "groq"` to `PRIMARY_PROVIDER = "gemini"`
and update the docstring. Remove the `BACKUP_PROVIDER = "gemini"` and the
two-attempt fallback since there is only one active provider for Agent 3.

---

### B3 — Gemini `success=True` with empty text (MEDIUM)

**File:** `backend/services/gemini_service.py` lines 94–102.
**Problem:** When `gemini-3.5-flash` returns empty candidates (which happens
frequently with short or instruction-style prompts), the service returns
`{"success": True, "text": ""}`. Callers (agents, supervisor) treat `success`
as an indicator that the AI produced meaningful output, but an empty string
is indistinguishable from a valid empty response.
**Current mitigation:** The `test_connection()` method adds a `note` field.
But `generate()` itself does not distinguish empty-text success from
meaningful-text success, so agents may silently produce empty responses that
fall through to `_parse_llm_output()` → JSON parse failure → fallback, without
the agent being aware the AI "succeeded" with nothing.
**Fix:** In `generate()`, if `text` is empty after both extraction paths,
return `success=False` with a descriptive error so callers trigger fallback
correctly and log the event.

---

### B4 — Supervisor conflict resolution is unimplemented (LOW)

**File:** `backend/agents/supervisor.py` lines 199–202.
**Problem:** The comment says "Resolve any conflicting recommendations".
`severity_rank` and `agent3_severity` are computed but `final_risk` is
unconditionally set to `a1.get("risk_level", "UNKNOWN")`. Agent 3's severity
assessment never overrides Agent 1's risk level even if it is higher.
**Impact:** If Agent 3 LLM identifies a scenario as CRITICAL but Agent 1
said MEDIUM, the unified response always shows MEDIUM.
**Fix:** Implement the comparison:
```python
if severity_rank.get(agent3_severity, 0) > severity_rank.get(risk, 0):
    final_risk = agent3_severity if agent3_severity in ("LOW","MEDIUM","HIGH") else risk
```

---

### B5 — `/api/models/status` shows Groq as secondary (LOW, cosmetic)

**File:** `backend/app.py` line 141.
**Problem:** `"secondary": ["Google Gemini", "Groq"]` — Groq is disabled.
**Fix:** Change to `"secondary": ["Google Gemini"]`.

---

### B6 — `provider="none"` pollutes analytics (LOW)

**File:** `backend/agents/supervisor.py` → `_log_model_call()`.
**Problem:** When both Groq (remapped to Gemini) and Gemini fail, the model
manager returns `provider="none"`. This gets logged to `model_call_logs` with
`provider="none"`, creating a confusing "none" bucket in the analytics
provider stats visible on the dashboard.
**Fix:** In `_log_model_call()`, skip the DB write if `provider == "none"` or
`provider == "unknown"`, or map it to `"fallback"` for clarity.

---

### B7 — Model status badges are stale after startup (LOW)

**File:** `frontend/static/js/app.js` — `checkHealth()`.
**Problem:** Badges are set once on page load from `/api/health`. They are
never refreshed. If a provider's key expires or quota is exhausted mid-session,
badges remain green.
**Fix:** Add a periodic refresh (e.g. `setInterval(checkHealth, 60000)`).

---

### B8 — Output validator never called in pipeline (MEDIUM)

**File:** `backend/agents/supervisor.py`.
**Problem:** `Guardrails.validate_output()` exists and strips PII + checks
hallucination patterns, but `supervisor.py` never calls it on any agent output
before returning to the frontend.
**Fix:** Call `guardrails.validate_output(result["text"], risk_level)` in each
agent's `generate()` result handling, or once in `_consolidate()` on key text
fields before returning.

---

### B9 — `ALLOWED_CONNECTION_TYPES` defined but unused (LOW)

**File:** `backend/security/guardrails.py` lines 87–91.
**Problem:** A set of valid connection type strings is defined but
`validate_input()` never checks `connection_type` against it. Any arbitrary
string is accepted.
**Impact:** Minor — it doesn't create a security hole since the value is
only used as context in an LLM prompt, but it is dead code.

---

### B10 — Token counting is a word-count estimate for Granite (LOW)

**File:** `backend/services/granite_service.py` lines 108–109.
**Problem:** `"prompt_tokens": len(prompt.split())` and
`"completion_tokens": len(text.split())` count whitespace-separated words,
not BPE tokens. Actual token counts are typically 20–30% higher.
**Impact:** Analytics `avg_ms` is correct; token counts in `model_call_logs`
are understated.
**Fix:** Use `len(prompt) // 4` as a better estimate, or retrieve actual
counts from the watsonx.ai response metadata if available.

---

### B11 — `db_url()` tries a live MySQL connection at startup (MEDIUM)

**File:** `backend/config.py` lines 78–91.
**Problem:** Every time the application starts, `db_url()` attempts a live
MySQL connection even when MySQL is not configured. This adds ~1–2 seconds
to startup time and logs a spurious connection error on every cold start.
**Fix:** Only attempt MySQL if `MYSQL_PASSWORD` is non-empty:
```python
if cls.MYSQL_PASSWORD:
    # attempt MySQL
    ...
else:
    return f"sqlite:///{cls.SQLITE_DB_PATH}"
```

---

## 10. Features Documented But Not Implemented

| Feature | Claimed In | Reality |
|---------|-----------|---------|
| **Groq integration** | README, architecture.md, agent3_incident.py docstring | `groq_service.py` exists and is correct code, but `GROQ_API_KEY=""` and all calls remapped to Gemini. Not actually used. |
| **RAG (Retrieval-Augmented Generation)** | Problem statement §5 | Not implemented. No vector store, no document retrieval, no CERT-In document indexing. All knowledge is in hardcoded Python dicts or LLM training data. |
| **Tool calling** | Problem statement §5 | Not implemented. No function/tool schemas passed to any model. |
| **Context-aware conversation memory** | Problem statement §5 | Not implemented. Each `/api/chat` call is stateless. The chat endpoint constructs a fresh prompt each time. |
| **Human approval for critical actions** | Problem statement §5 | Not implemented. No approval gate exists in any workflow. |
| **Conflict resolution between agents** | Supervisor docstring | Code scaffolded but inactive (see bug B4). |
| **Output validation called on AI responses** | guardrails.py docstring | `validate_output()` exists but is never called from the pipeline. |
| **MySQL as primary database** | requirements.txt, README | SQLite is always used in practice (MySQL connection silently fails). |
| **Streamlit deployment** | requirements.txt (external addition) | `streamlit` is in requirements.txt but there is no Streamlit app file. It was added externally and is incompatible with this architecture. |

---

## 11. How to Test Each Agent and Verify Genuine AI Responses

### Prerequisites

```powershell
cd "c:\Users\Vinay.C.S\OneDrive\Desktop\ibm hackathon"
.\venv\Scripts\python.exe run.py
# Server logs should show:
# IBM Granite initialized: ibm/granite-4-h-small
# Google Gemini initialized: models/gemini-3.5-flash
# Serving on http://0.0.0.0:5000
```

---

### Test IBM Granite independently

```powershell
Invoke-RestMethod -Uri "http://localhost:5000/api/models/test" `
    -Method POST -ContentType "application/json" `
    -Body '{"provider":"granite"}' | ConvertTo-Json -Depth 3
```

**Genuine AI confirmed if:**
- `results.granite.success = true`
- `results.granite.model = "ibm/granite-4-h-small"`
- `results.granite.text = "IBM Granite operational"` (or similar)
- `results.granite.duration_ms > 100`
- `results.granite.error = null`

**Fallback/failure if:**
- `success = false`
- `error` contains "not configured" or an HTTP error

---

### Test Gemini independently

```powershell
Invoke-RestMethod -Uri "http://localhost:5000/api/models/test" `
    -Method POST -ContentType "application/json" `
    -Body '{"provider":"gemini"}' -TimeoutSec 40 | ConvertTo-Json -Depth 3
```

**Genuine AI confirmed if:**
- `results.gemini.success = true`
- `results.gemini.model = "models/gemini-3.5-flash"`
- `results.gemini.duration_ms > 100`
- `results.gemini.error = null`

**Note:** `text` may be empty even on genuine connection (`note` field
explains this — see bug B3). The API key may hit a 429 quota limit under
heavy testing.

---

### Test Agent 1 (Network Risk Assessment) with real Granite

```powershell
$body = '{"wifi_name":"Free_Station_WiFi","connection_type":"open","location":"Namma Metro, Bengaluru","user_context":""}'
$r = Invoke-RestMethod -Uri "http://localhost:5000/api/assess" `
    -Method POST -ContentType "application/json" -Body $body -TimeoutSec 120

# Verify Agent 1 made a genuine Granite call:
$r.agent_statuses.agent1 | Select-Object name, status, model, provider, duration_ms

# Genuine Granite response indicators:
# model    = "ibm/granite-4-h-small"
# provider = "granite"
# status   = "complete"          (not "complete_with_fallback")
# duration_ms > 500

# Distinguish AI output from rule-based fallback:
# AI:       risk_summary will be a natural-language sentence
# Fallback: risk_summary = "Rule-based assessment: HIGH risk"
Write-Host "Risk level:" $r.risk_level
Write-Host "Summary:"    $r.risk_summary
Write-Host "Explanation:" $r.risk_explanation
```

---

### Test Agent 2 (Device Safety) with real Granite

Agent 2 always runs after Agent 1 in the pipeline. Check its output:

```powershell
# From the same $r object above:
$r.agent_statuses.agent2 | Select-Object name, status, model, provider, duration_ms

# Genuine Granite response:
# threat_explanation, browsing_tips, app_security, bengaluru_specific come from LLM
# device_checklist and banking_guidance are ALWAYS static (not AI-generated)

Write-Host "Threat explanation (AI):" $r.threat_explanation
Write-Host "Browsing tips count:"     $r.browsing_tips.Count
# If status="complete_with_fallback", threat_explanation is from _fallback_guidance()
```

---

### Test Agent 3 (Incident Response) with real Gemini

```powershell
# Same pipeline — Agent 3 uses Gemini:
$r.agent_statuses.agent3 | Select-Object name, status, model, provider, duration_ms

# Genuine Gemini response:
# model    = "models/gemini-3.5-flash"
# provider = "gemini"
# situation_summary, prevention_summary, bengaluru_transit_tip come from LLM

Write-Host "Incident scenario:"  $r.incident_scenario
Write-Host "Situation summary (AI):" $r.situation_summary
Write-Host "Provider:" $r.agent_statuses.agent3.provider
```

---

### Test AI Chat (Granite)

```powershell
Invoke-RestMethod -Uri "http://localhost:5000/api/chat" `
    -Method POST -ContentType "application/json" `
    -Body '{"message":"Is public Wi-Fi at Namma Metro safe?"}' `
    -TimeoutSec 30

# Genuine response indicators:
# model    = "ibm/granite-4-h-small"
# provider = "granite"
# response = natural language answer (not a fixed string)
```

---

### Full end-to-end pipeline test (all three agents, synthetic HIGH-risk scenario)

```powershell
$body = @{
    wifi_name       = "Free_Bank_WiFi"
    connection_type = "open"
    location        = "Bangalore City Railway Station"
    user_context    = "It redirected me to a login portal asking for phone number"
} | ConvertTo-Json

$r = Invoke-RestMethod -Uri "http://localhost:5000/api/assess" `
    -Method POST -ContentType "application/json" -Body $body -TimeoutSec 120

# Expected outcome:
# risk_level = HIGH
# incident_scenario = phishing  (login portal in context triggers this)
# agent_statuses.agent1.provider = granite
# agent_statuses.agent2.provider = granite
# agent_statuses.agent3.provider = gemini
# execution_log should show 12 steps: running/complete pairs for each stage

$r.execution_log | ForEach-Object { Write-Host "[$($_.status)] $($_.step)" }
```

---

### Run automated test suite

```powershell
# All 29 tests (no live API calls — fully mocked):
.\venv\Scripts\python.exe -m pytest tests/ -v

# Expected: 29 passed, 0 warnings
```

---

## 12. Quick-Reference Issue Table

| ID | Severity | File | Description | Fix required |
|----|----------|------|-------------|-------------|
| B1 | MEDIUM | requirements.txt | `streamlit` added — incompatible, unused | Remove line |
| B2 | LOW | agent3_incident.py | `PRIMARY_PROVIDER="groq"` misleading — remapped to Gemini | Update to `"gemini"` |
| B3 | MEDIUM | gemini_service.py | `success=True` with empty text masks effective failure | Return `success=False` on empty text |
| B4 | LOW | supervisor.py | Conflict resolution code scaffolded but not active | Implement severity comparison |
| B5 | LOW | app.py | `/api/models/status` shows Groq as secondary | Remove Groq from secondary list |
| B6 | LOW | supervisor.py | `provider="none"` logged to analytics | Skip or remap to "fallback" |
| B7 | LOW | app.js | Model status badges stale after startup | Add periodic refresh |
| B8 | MEDIUM | supervisor.py | `validate_output()` never called — AI output not checked | Call in pipeline |
| B9 | LOW | guardrails.py | `ALLOWED_CONNECTION_TYPES` defined but unused | Enforce or remove |
| B10 | LOW | granite_service.py | Token count is word-count estimate | Improve estimate |
| B11 | MEDIUM | config.py | MySQL connection attempted at startup even when unconfigured | Guard with `if MYSQL_PASSWORD` |

---

*This report was generated by reading and analyzing every source file. No
changes were made to any project file during this audit.*
