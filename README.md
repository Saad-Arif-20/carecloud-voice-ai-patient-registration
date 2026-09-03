# CareCloud Voice AI Patient Registration

A voice AI agent that answers a real phone number, conversationally registers a new
patient (or updates an existing one), persists the record to a database, and exposes it
through a REST API + tiny dashboard. Built for the CareCloud take-home technical
assessment.

**Live demo:**
- Phone number: `<FILL IN AFTER RUNNING vapi/setup_vapi.py>`
- API base URL: https://carecloud-voice-ai-production.up.railway.app
- Dashboard: https://carecloud-voice-ai-production.up.railway.app/dashboard

---

## Architecture

```
Caller (phone)
     │  PSTN call
     ▼
Vapi  ───────────────────────────────────────────────┐
 ├─ Telephony (provisions the real US number)         │
 ├─ Transcriber: Deepgram (speech → text)              │
 ├─ LLM: Groq Llama 3.3 70B (the conversation brain)   │  one HTTPS webhook
 └─ Voice: Vapi built-in TTS (text → speech)           │  for tool-calls +
                                                        │  end-of-call-report
     │ function/"tool" calls only (create_patient, etc)│
     ▼                                                 │
POST /vapi/webhook  ◄──────────────────────────────────┘
     │ same functions as the REST API, same validation
     ▼
app/service.py  (business logic, single source of truth)
     │
     ▼
SQLite (app/patients.db)  ◄────────────┐
     ▲                                 │
     │ same service layer             │
GET/POST/PUT/DELETE /patients   ◄──────┘  ordinary REST clients (curl, dashboard, reviewer)
     │
     ▼
static/dashboard.html  (bonus: minimal read-only web UI over GET /patients)
```

**Why this shape:** the assessment's own tip says platforms like Vapi "abstract much of
the telephony/STT/TTS complexity and let you focus on the LLM prompt, tool definitions,
and backend" — that's exactly the trade I made. Vapi owns the phone call; my code owns
everything after the LLM decides to call a tool. The voice agent and the plain REST API
both funnel through the exact same `app/service.py` functions, so there is one
implementation of "what a valid patient record looks like" and one implementation of
"how a patient gets saved," not two that could drift apart.

---

## Tech stack (and why)

| Layer | Choice | Why |
|---|---|---|
| Telephony + Voice AI | **Vapi** | Fastest path to a real phone number + STT/TTS/LLM orchestration without hand-rolling a media-streaming pipeline (Twilio + raw WebSocket audio) in a time-boxed assessment. Vapi also gives free trial phone numbers, so no Twilio account/cost is needed. |
| LLM | **Groq (Llama 3.3 70B versatile)** | Genuinely free tier (no card required) with tool-calling support, fast enough for real-time voice turn-taking. Swappable to OpenAI/Anthropic via one env var if quality needs outweigh cost (see `vapi/assistant_config.py`). |
| Backend | **Python + FastAPI** | Pydantic gives strict, declarative validation that maps 1:1 onto the assessment's field-by-field validation table; automatic `/docs` OpenAPI page is a free bonus for reviewers; async-friendly for a webhook-heavy service. |
| Database | **SQLite (SQLAlchemy ORM)** | Explicitly called out in the assessment as a legitimate trade-off ("SQLite over Postgres"). Zero infra to stand up, still gets a real schema with types, NOT NULL, and CHECK constraints (see `app/models.py`) — persisted to disk, survives process restarts. A Postgres swap is a one-line `DATABASE_URL` change since everything goes through SQLAlchemy. |
| Hosting | **Railway** (or Render, see below) | Suggested directly in the assessment; Dockerfile-based deploy with a mountable volume so the SQLite file survives redeploys, not just restarts. |

---

## Repo layout

```
app/
  config.py            # all env vars, read once
  validators.py        # single source of truth for field validation rules
  models.py             # SQLAlchemy schema (Patient, CallLog, Appointment) + CHECK constraints
  schemas.py             # Pydantic request/response schemas, reuse validators.py
  service.py             # business logic / DB access -- used by BOTH routes below
  database.py            # SQLite engine/session setup
  seed.py                 # optional demo seed data
  logging_conf.py          # stdout + file logging setup
  routes/
    patients.py             # public REST API (GET/POST/PUT/DELETE /patients)
    vapi_webhook.py           # POST /vapi/webhook -- the voice agent's only entry point
  main.py                      # FastAPI app wiring, error envelope, /health, /dashboard
static/
  dashboard.html                 # bonus: minimal read-only patients dashboard
vapi/
  system_prompt.md                 # the literal LLM system prompt + documented rationale
  assistant_config.py                # builds the Vapi assistant JSON (prompt + tools + model)
  setup_vapi.py                        # one-shot script: creates the assistant + phone number
tests/
  test_api.py                           # bonus: pytest suite for the REST API
```

---

## Data model

`app/models.py` implements every field from the spec's table, with a native `Date`
column for `date_of_birth` (not a string) so the database enforces a real type, while the
API and voice tools speak the spec's `MM/DD/YYYY` string format at the boundary
(conversion lives in `app/validators.py::dob_str_to_date` / `date_to_dob_str`). `sex` and
`state` are backed by SQL `CHECK` constraints (not just app-level validation) using the
same value lists the Pydantic validators use, and `deleted_at` implements the required
soft delete. See the docstring at the top of `app/models.py` for the full reasoning.

One deliberate deviation from the letter of the spec: `first_name`/`last_name` allow an
internal space (e.g. "Van Der Berg") in addition to letters/hyphens/apostrophes — real
legal names need it, and rejecting them would be a worse experience than the stricter
reading of the spec. Documented in `app/validators.py`.

---

## REST API

All responses use the envelope `{ "data": ..., "error": ... }`.

| Method | Endpoint | Notes |
|---|---|---|
| GET | `/patients` | optional `?last_name=`, `?date_of_birth=` (MM/DD/YYYY), `?phone_number=` |
| GET | `/patients/{id}` | 404 if not found or soft-deleted |
| POST | `/patients` | 201 on success, 422 with per-field errors on invalid input |
| PUT | `/patients/{id}` | partial update, 422 if body has no valid fields |
| DELETE | `/patients/{id}` | soft delete (`deleted_at` set; row is never removed) |
| GET | `/health` | liveness check |
| GET | `/dashboard` | bonus HTML dashboard over the same data |

Every input is re-validated server-side via Pydantic (`app/schemas.py`) regardless of
what the voice agent already checked — the assessment is explicit that validation can't
rely solely on the LLM.

---

## The voice agent

The full system prompt lives in **[`vapi/system_prompt.md`](vapi/system_prompt.md)**,
with a "Design rationale" section at the top explaining *why* it's structured the way it
is (voice-first phrasing, field ordering, the confirmation gate, error-as-data instead of
error-as-HTTP-failure, "start over" handling, etc.) — worth reading in full for the
prompt-engineering half of the grading rubric.

The LLM has four tools, all defined in `vapi/assistant_config.py` and executed in
`app/routes/vapi_webhook.py` against the same `service.py` used by the REST API:

1. `check_patient_by_phone` — duplicate-caller detection (bonus), called immediately after
   the phone number is collected, before anything else.
2. `create_patient` — only called after the caller has confirmed a full read-back.
3. `update_patient` — used instead of #2 when #1 found an existing record and the caller
   opted to update.
4. `schedule_appointment` — bonus mock appointment slot, offered after a successful
   registration.

Tool results are structured JSON (`{"success": true/false, ...}`), not HTTP status codes,
because whatever a tool returns may end up read aloud to the caller — an opaque 422 is
useless to an LLM trying to explain *which* field was wrong. `create_patient` /
`update_patient` return `{"success": false, "error": "date_of_birth: cannot be in the
future"}`-style messages the model is instructed to turn into a targeted re-prompt.

---

## Setup — local development

Requires Python 3.11+.

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows PowerShell/cmd
# source .venv/bin/activate   # macOS/Linux

pip install -r requirements.txt
copy .env.example .env        # cp on macOS/Linux — then edit as needed

uvicorn app.main:app --reload
```

The API is now at `http://localhost:8000` (Swagger docs at `/docs`, dashboard at
`/dashboard`). SQLite lives at `./data/patients.db` and is created + seeded with 2 demo
patients on first run.

Run the test suite:

```bash
pytest tests/ -v
```

To test the voice-agent webhook locally without a live phone call, `curl` it directly
(see "Manual webhook testing" below) or use `ngrok http 8000` to get a temporary public
URL and point a Vapi assistant at `https://<ngrok-id>.ngrok-free.app/vapi/webhook`.

### Manual webhook testing

```bash
curl -X POST http://localhost:8000/vapi/webhook -H "Content-Type: application/json" -d '{
  "message": {
    "type": "tool-calls",
    "call": {"id": "manual-test-1"},
    "toolCallList": [{
      "id": "tc1", "type": "function",
      "function": {"name": "create_patient", "arguments": {
        "first_name": "Test", "last_name": "Patient", "date_of_birth": "01/01/1990",
        "sex": "Other", "phone_number": "2135551234",
        "address_line_1": "1 Test St", "city": "Testville", "state": "CA", "zip_code": "90001"
      }}
    }]
  }
}'
```

---

## Deployment (Railway)

1. Push this repo to GitHub (already done if you're reading this from the repo).
2. On [railway.app](https://railway.app), **New Project → Deploy from GitHub repo**, pick
   this repo. Railway detects the `Dockerfile` automatically.
3. **Add a volume**: Service → Settings → Volumes → mount at `/data`. This is what makes
   the SQLite file survive redeploys, not just restarts — the whole point of the
   assessment's "call back later and the data is still there" requirement.
4. Set environment variables (Service → Variables):
   - `DATABASE_PATH=/data/patients.db`
   - `LOG_FILE=/data/agent_calls.log`
   - `VAPI_WEBHOOK_SECRET=<any random string>`
5. Deploy. Note the generated `https://<name>.up.railway.app` URL — that's
   `PUBLIC_API_BASE_URL` for the next step.

*(Render works too: same Dockerfile, use a Render Disk instead of a Railway Volume for
the same `/data` mount. Render's free tier cold-starts after 15 minutes idle, which can
add a few seconds of latency to the first tool call of a call — see Known Limitations.)*

---

## Provisioning the Vapi assistant + phone number

This is a one-time script, run from your own machine (not deployed):

1. **Sign up at [vapi.ai](https://vapi.ai)** (free trial credit, no card needed to start)
   and grab an API key from Settings → API Keys.
2. **Sign up at [console.groq.com](https://console.groq.com)** (free, no card) and grab an
   API key.
3. In the **Vapi dashboard → Settings → Provider Keys**, add your Groq key so Vapi can
   call it on your behalf during calls.
4. Locally:
   ```bash
   pip install httpx   # already in requirements.txt if you set up the venv above
   export VAPI_API_KEY=...
   export PUBLIC_API_BASE_URL=https://<your-railway-app>.up.railway.app
   export VAPI_WEBHOOK_SECRET=<the same random string you set on Railway>
   python vapi/setup_vapi.py
   ```
5. The script prints the assistant ID and a **free US phone number** — call it.

Re-running the script after editing `vapi/system_prompt.md` or `vapi/assistant_config.py`
is safe: it deletes the previous assistant with the same name and recreates it, so the
phone number's assistant binding is refreshed too — no manual cleanup needed.

---

## Observability

Every REST write and every voice-agent tool call is logged (`app/logging_conf.py`) to
stdout *and* `./data/agent_calls.log`, including the full validated payload on a
successful `create_patient`/`update_patient` call — this is the minimum the assessment
asks for ("log agent conversations, at minimum the final collected data payload"). Vapi's
`end-of-call-report` webhook event is also captured and stored in the `call_logs` table,
linked to the patient record it produced when one exists (bonus: call transcript/summary
storage).

---

## Edge cases & resilience (how each one is actually handled)

- **Invalid date of birth / phone / zip / state / sex** — rejected server-side
  (`app/validators.py` + SQL CHECK constraints as a second line of defense), and for the
  voice path, the tool returns a field-specific error string the prompt is instructed to
  turn into a targeted re-prompt (never a full restart).
- **Telephony connection drops mid-call** — nothing is persisted until `create_patient`/
  `update_patient` actually succeeds near the end of the call, so a dropped call simply
  leaves no record; the caller can call back and start clean. (A fancier version would
  persist a draft-per-call-id so a dropped call could resume — noted under Next Steps.)
- **Database write fails** — `service.py` catches `SQLAlchemyError`, rolls back, and
  raises `ServiceError`; the webhook handler turns that into `{"success": false, "error":
  "internal_error", "message": "..."}`, which the prompt is instructed to apologize for and
  offer a retry — never silence, never a raw exception.
- **Caller wants to start over mid-call** — purely a prompt-level instruction (see
  `system_prompt.md`): since nothing is saved until the end, an in-call restart has no
  data-layer side effects to undo.
- **Duplicate caller (bonus)** — `check_patient_by_phone` runs right after the phone
  number is collected; if found, the prompt asks whether to update instead of create.

---

## Known limitations / trade-offs

- **SQLite, not Postgres.** Fine for this assessment's scale and explicitly sanctioned by
  the prompt; would move to Postgres (one `DATABASE_URL` change, SQLAlchemy already
  abstracts it) for real concurrent load.
- **Groq Llama 3.3 instead of GPT-4o.** Chosen to keep this $0 to run. Tool-calling on
  Llama is solid but occasionally less precise than GPT-4o on subtle corrections
  ("actually, make that Davis, not Davies") — if conversational quality needs to go up,
  switch `VAPI_MODEL_PROVIDER`/`VAPI_MODEL_NAME` to `openai`/`gpt-4o-mini` and add an
  OpenAI key in the Vapi dashboard; no other code changes needed.
- **Spanish support is best-effort.** The prompt will switch languages, but the TTS voice
  (Vapi's free built-in voice) is tuned for English; accent quality in Spanish will be
  noticeably weaker than a dedicated multilingual voice provider.
- **`_CALL_TO_PATIENT` call→patient linkage is in-memory**, so it resets on a process
  restart between a call's tool-calls and its end-of-call-report (a multi-minute-long
  redeploy mid-call, in practice never). A persisted mapping keyed by Vapi call id would
  remove this edge case entirely.
- **No auth on the REST API** beyond the Vapi webhook secret. Fine for a take-home; a real
  deployment would put patient data behind proper authentication/authorization.
- **Render's free tier cold start** (if used instead of Railway) can add a few seconds of
  latency to the very first tool call after 15 minutes of inactivity.

---

## Next steps (if I had more time)

- Persist a "draft" registration keyed by Vapi call id so a dropped call can resume where
  it left off instead of restarting.
- Real appointment scheduling backed by an actual slot/calendar table instead of a fixed
  mock offset.
- Signed/rotated webhook secrets instead of a single static shared secret.
- A small admin auth layer on `/dashboard` and the REST API.
- Structured (JSON) logging instead of plain-text lines, for easier querying in production.

---

## Security notes

No API keys are hardcoded anywhere in this repo — everything sensitive is read from
environment variables (`app/config.py`) and `.env` is git-ignored. The Vapi webhook
endpoint checks an `x-vapi-secret` header against `VAPI_WEBHOOK_SECRET` before trusting
any request. All patient data in this system is synthetic/test data — do not enter real
personal information when testing (this is a technical assessment, not a HIPAA-compliant
system, per the assessment's own FAQ).
