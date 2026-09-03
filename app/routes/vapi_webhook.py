"""
The bridge between the Vapi voice assistant and our data layer.

Vapi calls this single endpoint for two kinds of events:
  1. "tool-calls"       -- the LLM decided to invoke one of the functions we defined for
                            the assistant (see vapi/assistant_config.py). We execute it
                            against app/service.py (the SAME code path the REST API uses)
                            and hand back a result the LLM can speak to the caller.
  2. "end-of-call-report" -- Vapi's post-call summary/transcript. We log it (Observability
                            requirement) and store it against the patient it produced, if
                            any (bonus: call transcript linked to patient record).

Everything the tools return is a short, plain-language-friendly string or JSON object --
never a raw stack trace -- because whatever we return here, the LLM may read straight to
the caller. That is also why validation failures are returned as data (not HTTP errors):
an HTTP 422 would just show up to the LLM as "the tool failed," with no way to know which
field was wrong.
"""
import json
import logging

from fastapi import APIRouter, Header, Request

from .. import config, service
from ..database import SessionLocal
from ..models import CallLog
from ..schemas import PatientCreate, PatientUpdate
from ..validators import ValidationFailure
from pydantic import ValidationError

router = APIRouter(prefix="/vapi", tags=["vapi"])
logger = logging.getLogger("carecloud.vapi")

# Best-effort in-memory map of Vapi call id -> patient_id, so that when the end-of-call
# report arrives we can link the transcript to the record the call produced. This resets
# on process restart; acceptable for a take-home demo (documented in README).
_CALL_TO_PATIENT: dict[str, str] = {}


def _parse_args(raw) -> dict:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {}
    return {}


def _validation_error_message(exc: ValidationError | ValidationFailure) -> str:
    if isinstance(exc, ValidationFailure):
        return str(exc)
    first = exc.errors()[0]
    field = first["loc"][-1] if first["loc"] else "field"
    msg = first["msg"].removeprefix("Value error, ")
    return f"{field}: {msg}"


def _handle_check_patient_by_phone(db, args: dict, call_id: str | None) -> dict:
    phone = args.get("phone_number", "")
    patient = service.find_by_phone(db, phone)
    if patient is None:
        return {"found": False}
    return {
        "found": True,
        "patient_id": patient.patient_id,
        "first_name": patient.first_name,
        "last_name": patient.last_name,
        "message": (
            f"Existing patient found: {patient.first_name} {patient.last_name}. "
            f"Ask the caller if they'd like to update their information instead of "
            f"creating a new record, then use update_patient with this patient_id."
        ),
    }


def _handle_create_patient(db, args: dict, call_id: str | None) -> dict:
    try:
        payload = PatientCreate(**args)
    except (ValidationError, ValidationFailure) as exc:
        return {"success": False, "error": _validation_error_message(exc)}

    try:
        patient = service.create_patient(db, payload)
    except service.ServiceError as exc:
        logger.error("create_patient DB failure: %s", exc)
        return {
            "success": False,
            "error": "internal_error",
            "message": "We could not save the record right now. Apologize and offer to try again in a moment.",
        }

    logger.info("VAPI_PATIENT_CREATED call_id=%s payload=%s", call_id, payload.model_dump())
    if call_id:
        _CALL_TO_PATIENT[call_id] = patient.patient_id
    return {
        "success": True,
        "patient_id": patient.patient_id,
        "message": f"Saved successfully for {patient.first_name} {patient.last_name}.",
    }


def _handle_update_patient(db, args: dict, call_id: str | None) -> dict:
    patient_id = args.pop("patient_id", None)
    if not patient_id:
        return {"success": False, "error": "patient_id is required to update a record."}
    try:
        payload = PatientUpdate(**args)
    except (ValidationError, ValidationFailure) as exc:
        return {"success": False, "error": _validation_error_message(exc)}

    try:
        patient = service.update_patient(db, patient_id, payload)
    except service.ServiceError as exc:
        logger.error("update_patient DB failure: %s", exc)
        return {
            "success": False,
            "error": "internal_error",
            "message": "We could not update the record right now. Apologize and offer to try again in a moment.",
        }
    if patient is None:
        return {"success": False, "error": "No patient found with that id."}

    logger.info("VAPI_PATIENT_UPDATED call_id=%s patient_id=%s fields=%s", call_id, patient_id, list(args.keys()))
    if call_id:
        _CALL_TO_PATIENT[call_id] = patient.patient_id
    return {
        "success": True,
        "patient_id": patient.patient_id,
        "message": f"Updated successfully for {patient.first_name} {patient.last_name}.",
    }


def _handle_schedule_appointment(db, args: dict, call_id: str | None) -> dict:
    patient_id = args.get("patient_id")
    if not patient_id:
        return {"success": False, "error": "patient_id is required to schedule an appointment."}
    reason = args.get("reason") or "New Patient Intake"
    try:
        appt = service.schedule_mock_appointment(db, patient_id, reason)
    except service.ServiceError as exc:
        logger.error("schedule_appointment DB failure: %s", exc)
        return {"success": False, "error": "internal_error", "message": "Could not schedule the appointment."}
    return {
        "success": True,
        "scheduled_at": appt.scheduled_at.isoformat(),
        "message": f"Mock appointment scheduled for {appt.scheduled_at.strftime('%A, %B %d at %I:%M %p UTC')}.",
    }


_TOOL_HANDLERS = {
    "check_patient_by_phone": _handle_check_patient_by_phone,
    "create_patient": _handle_create_patient,
    "update_patient": _handle_update_patient,
    "schedule_appointment": _handle_schedule_appointment,
}


def _handle_tool_calls(db, message: dict) -> dict:
    call_id = (message.get("call") or {}).get("id")
    results = []
    for tool_call in message.get("toolCallList", []):
        tool_call_id = tool_call.get("id")
        fn = tool_call.get("function", {})
        name = fn.get("name")
        args = _parse_args(fn.get("arguments"))
        handler = _TOOL_HANDLERS.get(name)
        if handler is None:
            result = {"success": False, "error": f"Unknown tool '{name}'."}
        else:
            try:
                result = handler(db, dict(args), call_id)
            except Exception:
                logger.exception("Unhandled error running tool '%s'", name)
                result = {"success": False, "error": "internal_error", "message": "Something went wrong. Apologize and offer to retry."}
        results.append({"toolCallId": tool_call_id, "result": result})
    return {"results": results}


def _handle_end_of_call_report(db, message: dict) -> None:
    call = message.get("call") or {}
    call_id = call.get("id")
    patient_id = _CALL_TO_PATIENT.pop(call_id, None) if call_id else None

    log_row = CallLog(
        patient_id=patient_id,
        vapi_call_id=call_id,
        ended_reason=message.get("endedReason"),
        transcript=message.get("transcript"),
        summary=message.get("summary"),
    )
    db.add(log_row)
    db.commit()
    logger.info(
        "VAPI_CALL_ENDED call_id=%s patient_id=%s ended_reason=%s summary=%s",
        call_id, patient_id, message.get("endedReason"), message.get("summary"),
    )


@router.post("/webhook")
async def vapi_webhook(request: Request, x_vapi_secret: str | None = Header(default=None)):
    if config.VAPI_WEBHOOK_SECRET and x_vapi_secret != config.VAPI_WEBHOOK_SECRET:
        return {"error": "unauthorized"}

    body = await request.json()
    message = body.get("message", {})
    msg_type = message.get("type")
    logger.info("VAPI_WEBHOOK type=%s", msg_type)

    db = SessionLocal()
    try:
        if msg_type == "tool-calls":
            return _handle_tool_calls(db, message)
        if msg_type == "end-of-call-report":
            _handle_end_of_call_report(db, message)
            return {"received": True}
        return {"received": True}
    finally:
        db.close()
