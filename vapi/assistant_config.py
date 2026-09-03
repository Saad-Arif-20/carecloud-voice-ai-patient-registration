"""
Builds the JSON payload used to create/update the Vapi assistant: the system prompt, the
tool (function) definitions the LLM can call, and the model/voice/transcriber/server
wiring. Kept separate from setup_vapi.py so the *shape* of the assistant is easy to review
independently of the script that pushes it to Vapi's API.
"""
import os
from pathlib import Path

_PROMPT_PATH = Path(__file__).parent / "system_prompt.md"


def load_system_prompt() -> str:
    text = _PROMPT_PATH.read_text(encoding="utf-8")
    start = text.index("```\n") + len("```\n")
    end = text.index("\n```", start)
    return text[start:end].strip()


# Every field in the assessment's data model, exposed to the LLM as tool parameters.
# Kept as a single dict so create_patient/update_patient tools can share it instead of
# drifting apart.
_PATIENT_FIELDS: dict = {
    "first_name": {"type": "string", "description": "Patient's legal first name."},
    "last_name": {"type": "string", "description": "Patient's legal last name."},
    "date_of_birth": {"type": "string", "description": "Date of birth in MM/DD/YYYY format."},
    "sex": {
        "type": "string",
        "enum": ["Male", "Female", "Other", "Decline to Answer"],
        "description": "One of the four allowed values, exactly as spelled here.",
    },
    "phone_number": {"type": "string", "description": "10-digit US phone number, digits only."},
    "email": {"type": "string", "description": "Optional email address."},
    "address_line_1": {"type": "string", "description": "Street address."},
    "address_line_2": {"type": "string", "description": "Optional apartment/suite/unit."},
    "city": {"type": "string"},
    "state": {"type": "string", "description": "2-letter US state abbreviation, e.g. CA, NY, TX."},
    "zip_code": {"type": "string", "description": "5-digit or ZIP+4 US zip code."},
    "insurance_provider": {"type": "string", "description": "Optional insurance company name."},
    "insurance_member_id": {"type": "string", "description": "Optional alphanumeric member/subscriber ID."},
    "preferred_language": {"type": "string", "description": "Optional; defaults to English."},
    "emergency_contact_name": {"type": "string", "description": "Optional full name."},
    "emergency_contact_phone": {"type": "string", "description": "Optional 10-digit US phone number."},
}

_REQUIRED_FOR_CREATE = [
    "first_name", "last_name", "date_of_birth", "sex", "phone_number",
    "address_line_1", "city", "state", "zip_code",
]


def build_tools() -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": "check_patient_by_phone",
                "description": (
                    "Look up whether a patient with this phone number already exists, for "
                    "duplicate-caller detection. Call this as soon as you have a valid "
                    "10-digit phone number and BEFORE asking any further questions."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "phone_number": {"type": "string", "description": "10-digit US phone number."},
                    },
                    "required": ["phone_number"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "create_patient",
                "description": (
                    "Create a new patient record. Only call this AFTER the caller has "
                    "explicitly confirmed the full read-back summary is correct."
                ),
                "parameters": {
                    "type": "object",
                    "properties": _PATIENT_FIELDS,
                    "required": _REQUIRED_FOR_CREATE,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "update_patient",
                "description": (
                    "Update one or more fields on an existing patient record identified by "
                    "patient_id (obtained from check_patient_by_phone). Only include fields "
                    "that actually changed."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "patient_id": {"type": "string", "description": "The existing patient's ID."},
                        **_PATIENT_FIELDS,
                    },
                    "required": ["patient_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "schedule_appointment",
                "description": (
                    "Bonus feature: schedule a mock first appointment for the patient after "
                    "successful registration, only if the caller wants one."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "patient_id": {"type": "string"},
                        "reason": {"type": "string", "description": "Defaults to 'New Patient Intake'."},
                    },
                    "required": ["patient_id"],
                },
            },
        },
    ]


def build_assistant_payload(
    server_url: str,
    server_secret: str | None,
    model_provider: str = "groq",
    model_name: str = "llama-3.3-70b-versatile",
    voice_provider: str = "vapi",
    voice_id: str = "Elliot",
) -> dict:
    server: dict = {"url": server_url}
    if server_secret:
        server["secret"] = server_secret

    return {
        "name": "CareCloud Patient Intake",
        "firstMessage": (
            "Thanks for calling CareCloud Health, this is Alex! "
            "I can get you registered as a new patient in just a couple of minutes. "
            "Can I start with your full name?"
        ),
        "model": {
            "provider": model_provider,
            "model": model_name,
            "temperature": 0.4,
            "messages": [{"role": "system", "content": load_system_prompt()}],
            "tools": build_tools(),
        },
        "voice": {"provider": voice_provider, "voiceId": voice_id},
        "transcriber": {"provider": "deepgram", "model": "nova-2", "language": "en"},
        "server": server,
        "endCallFunctionEnabled": True,
        "silenceTimeoutSeconds": 20,
        "maxDurationSeconds": 600,
    }


if __name__ == "__main__":
    import json

    print(json.dumps(build_assistant_payload("https://example.com/vapi/webhook", None), indent=2))
