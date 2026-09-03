"""
Centralized environment configuration.

Everything that varies between local/dev and the deployed (Railway/Render) environment
lives here and is read from environment variables only -- nothing secret is hardcoded,
per the assessment's security requirement.
"""
import os

# SQLite by default (the assessment explicitly calls this out as a fine trade-off for a
# take-home). On Railway/Render this path should point at a mounted persistent volume
# (see README) so the file survives redeploys, not just process restarts.
DATABASE_PATH = os.getenv("DATABASE_PATH", "./data/patients.db")

# Shared secret the Vapi webhook must present (as a query param or bearer token) so random
# internet traffic can't call our tool-execution endpoint and write fake patients.
VAPI_WEBHOOK_SECRET = os.getenv("VAPI_WEBHOOK_SECRET", "")

# Used only by scripts/setup_vapi.py to provision the assistant + phone number via Vapi's
# REST API. Not needed by the running FastAPI app itself.
VAPI_API_KEY = os.getenv("VAPI_API_KEY", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# Public HTTPS URL of this deployed API, e.g. https://carecloud-voice-agent.up.railway.app
# Used by setup_vapi.py to point the assistant's tool-calls at us.
PUBLIC_API_BASE_URL = os.getenv("PUBLIC_API_BASE_URL", "http://localhost:8000")

LOG_FILE = os.getenv("LOG_FILE", "./data/agent_calls.log")

PORT = int(os.getenv("PORT", "8000"))
