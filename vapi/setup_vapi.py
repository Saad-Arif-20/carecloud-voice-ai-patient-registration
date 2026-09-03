"""
One-shot provisioning script: creates (or replaces) the Vapi assistant from
assistant_config.py, then attaches a free Vapi-hosted US phone number to it.

Run locally, NOT on the server -- it's a setup tool, not part of the running app:

    python vapi/setup_vapi.py

Required env vars (see .env.example):
    VAPI_API_KEY          - from https://dashboard.vapi.ai -> Settings -> API Keys
    PUBLIC_API_BASE_URL   - your deployed FastAPI base URL, e.g. https://your-app.up.railway.app
    VAPI_WEBHOOK_SECRET   - any random string; must match what the deployed app has too

No separate Groq account/API key is needed: Vapi has a built-in Groq integration billed
through your own Vapi credits (see https://docs.vapi.ai/providers/model/groq), so
model.provider="groq" just works out of the box with only VAPI_API_KEY set.
"""
import os
import sys

import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vapi.assistant_config import build_assistant_payload  # noqa: E402

VAPI_API_BASE = "https://api.vapi.ai"


def main() -> None:
    api_key = os.environ.get("VAPI_API_KEY")
    base_url = os.environ.get("PUBLIC_API_BASE_URL")
    webhook_secret = os.environ.get("VAPI_WEBHOOK_SECRET", "")
    model_provider = os.environ.get("VAPI_MODEL_PROVIDER", "groq")
    model_name = os.environ.get("VAPI_MODEL_NAME", "openai/gpt-oss-120b")

    if not api_key:
        raise SystemExit("VAPI_API_KEY is not set. Export it and re-run.")
    if not base_url or base_url.startswith("http://localhost"):
        raise SystemExit(
            "PUBLIC_API_BASE_URL must be your deployed HTTPS URL (Vapi cannot reach "
            "localhost). Deploy first, then set this and re-run."
        )

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    server_url = base_url.rstrip("/") + "/vapi/webhook"

    payload = build_assistant_payload(
        server_url=server_url,
        server_secret=webhook_secret or None,
        model_provider=model_provider,
        model_name=model_name,
    )

    with httpx.Client(timeout=30) as client:
        # Clean up any assistant we previously created under this name, so re-running
        # this script after prompt tweaks doesn't leave a pile of duplicates behind.
        existing = client.get(f"{VAPI_API_BASE}/assistant", headers=headers)
        existing.raise_for_status()
        for a in existing.json():
            if a.get("name") == payload["name"]:
                print(f"Deleting previous assistant {a['id']} ...")
                client.delete(f"{VAPI_API_BASE}/assistant/{a['id']}", headers=headers)

        print("Creating assistant ...")
        resp = client.post(f"{VAPI_API_BASE}/assistant", headers=headers, json=payload)
        if resp.status_code >= 400:
            print("Vapi rejected the assistant payload:", resp.status_code, resp.text)
            resp.raise_for_status()
        assistant = resp.json()
        assistant_id = assistant["id"]
        print(f"Assistant created: {assistant_id}")

        area_code = os.environ.get("VAPI_AREA_CODE", "415")
        print(f"Requesting a free Vapi-hosted US phone number (area code {area_code}) ...")
        phone_resp = client.post(
            f"{VAPI_API_BASE}/phone-number",
            headers=headers,
            json={
                "provider": "vapi",
                "assistantId": assistant_id,
                "name": "CareCloud Intake Line",
                "numberDesiredAreaCode": area_code,
            },
        )
        if phone_resp.status_code >= 400:
            print("Vapi rejected the phone-number request:", phone_resp.status_code, phone_resp.text)
            print(
                "You can still attach a number manually in the Vapi dashboard: "
                "Phone Numbers -> Create -> Free Vapi Number -> select this assistant."
            )
            phone_resp.raise_for_status()
        phone = phone_resp.json()

    print("\n--- Done ---")
    print(f"Assistant ID:  {assistant_id}")
    print(f"Phone number:  {phone.get('number')}")
    print(f"Webhook URL:   {server_url}")
    print("\nCall the number above to test the agent end-to-end.")


if __name__ == "__main__":
    main()
