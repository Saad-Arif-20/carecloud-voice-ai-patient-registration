"""
The public REST API described in the assessment: GET/POST /patients, GET/PUT/DELETE
/patients/:id. Every input is (re-)validated here via Pydantic regardless of what the
voice agent already checked, and every response uses the { data, error } envelope with
the requested status codes (200/201/400/404/422/500).
"""
import json
import logging

from fastapi import APIRouter, Request
from pydantic import ValidationError

from .. import service
from ..database import SessionLocal
from ..envelope import fail, ok
from ..schemas import PatientCreate, PatientOut, PatientUpdate

router = APIRouter(prefix="/patients", tags=["patients"])
logger = logging.getLogger("carecloud.api")


def _format_validation_error(exc: ValidationError) -> list[dict]:
    out = []
    for err in exc.errors():
        field = err["loc"][-1] if err["loc"] else "body"
        out.append({"field": str(field), "message": err["msg"].removeprefix("Value error, ")})
    return out


@router.get("")
def list_patients(
    last_name: str | None = None,
    date_of_birth: str | None = None,
    phone_number: str | None = None,
):
    db = SessionLocal()
    try:
        patients = service.list_patients(db, last_name, date_of_birth, phone_number)
        return ok([PatientOut.from_model(p).model_dump(mode="json") for p in patients])
    finally:
        db.close()


@router.get("/{patient_id}")
def get_patient(patient_id: str):
    db = SessionLocal()
    try:
        patient = service.get_patient(db, patient_id)
        if patient is None:
            return fail("Patient not found.", 404)
        return ok(PatientOut.from_model(patient).model_dump(mode="json"))
    finally:
        db.close()


@router.post("")
async def create_patient(request: Request):
    try:
        body = await request.json()
    except json.JSONDecodeError:
        return fail("Request body must be valid JSON.", 400)
    if not isinstance(body, dict):
        return fail("Request body must be a JSON object.", 400)

    try:
        payload = PatientCreate(**body)
    except ValidationError as exc:
        return fail("Validation failed.", 422, details=_format_validation_error(exc))

    # Note: duplicate-phone-number detection (the assessment's bonus feature) is handled
    # at the voice-agent layer (see app/routes/vapi_webhook.py's check_patient_by_phone
    # tool) rather than here, so a plain REST client can still POST freely -- e.g. a
    # household that legitimately shares one phone number across two patients.
    db = SessionLocal()
    try:
        patient = service.create_patient(db, payload)
        logger.info("PATIENT_CREATED payload=%s", payload.model_dump())
        return ok(PatientOut.from_model(patient).model_dump(mode="json"), status_code=201)
    except service.ServiceError as exc:
        return fail(str(exc), 500)
    finally:
        db.close()


@router.put("/{patient_id}")
async def update_patient(patient_id: str, request: Request):
    try:
        body = await request.json()
    except json.JSONDecodeError:
        return fail("Request body must be valid JSON.", 400)
    if not isinstance(body, dict):
        return fail("Request body must be a JSON object.", 400)

    try:
        payload = PatientUpdate(**body)
    except ValidationError as exc:
        return fail("Validation failed.", 422, details=_format_validation_error(exc))

    db = SessionLocal()
    try:
        patient = service.update_patient(db, patient_id, payload)
        if patient is None:
            return fail("Patient not found.", 404)
        logger.info("PATIENT_UPDATED patient_id=%s fields=%s", patient_id, list(body.keys()))
        return ok(PatientOut.from_model(patient).model_dump(mode="json"))
    except service.ServiceError as exc:
        return fail(str(exc), 500)
    finally:
        db.close()


@router.delete("/{patient_id}")
def delete_patient(patient_id: str):
    db = SessionLocal()
    try:
        patient = service.soft_delete_patient(db, patient_id)
        if patient is None:
            return fail("Patient not found.", 404)
        logger.info("PATIENT_DELETED patient_id=%s", patient_id)
        return ok({"patient_id": patient_id, "deleted_at": patient.deleted_at.isoformat()})
    except service.ServiceError as exc:
        return fail(str(exc), 500)
    finally:
        db.close()
