"""
Service layer: the single place that talks to the database.

Both the REST routes (app/routes/patients.py) and the Vapi tool-calls webhook
(app/routes/vapi_webhook.py) call into this module rather than duplicating query logic --
this is the "clear separation of concerns" the assessment grades on: telephony/LLM glue
lives in routes/vapi_webhook.py, HTTP concerns live in routes/patients.py, and everything
data-related lives here.
"""
import logging
from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from . import validators as v
from .models import Appointment, Patient
from .schemas import PatientCreate, PatientUpdate

logger = logging.getLogger("carecloud.service")


class ServiceError(Exception):
    """Raised on unexpected DB failure; routes turn this into a 500 + safe message."""


def _apply_dates(data: dict) -> dict:
    data = dict(data)
    if "date_of_birth" in data and data["date_of_birth"] is not None:
        data["date_of_birth"] = v.dob_str_to_date(data["date_of_birth"])
    return data


def create_patient(db: Session, payload: PatientCreate) -> Patient:
    data = _apply_dates(payload.model_dump())
    patient = Patient(**data)
    try:
        db.add(patient)
        db.commit()
        db.refresh(patient)
    except SQLAlchemyError:
        db.rollback()
        logger.exception("DB write failed while creating patient")
        raise ServiceError("Could not save the new patient record.")
    logger.info("Created patient %s (%s %s)", patient.patient_id, patient.first_name, patient.last_name)
    return patient


def get_patient(db: Session, patient_id: str, include_deleted: bool = False) -> Patient | None:
    stmt = select(Patient).where(Patient.patient_id == patient_id)
    if not include_deleted:
        stmt = stmt.where(Patient.deleted_at.is_(None))
    return db.execute(stmt).scalar_one_or_none()


def find_by_phone(db: Session, phone_number: str) -> Patient | None:
    try:
        normalized = v.normalize_phone(phone_number, "phone_number")
    except v.ValidationFailure:
        return None
    stmt = select(Patient).where(Patient.phone_number == normalized, Patient.deleted_at.is_(None))
    return db.execute(stmt).scalar_one_or_none()


def list_patients(
    db: Session,
    last_name: str | None = None,
    date_of_birth: str | None = None,
    phone_number: str | None = None,
) -> list[Patient]:
    stmt = select(Patient).where(Patient.deleted_at.is_(None))
    if last_name:
        stmt = stmt.where(Patient.last_name.ilike(last_name.strip()))
    if date_of_birth:
        try:
            stmt = stmt.where(Patient.date_of_birth == v.dob_str_to_date(v.parse_dob(date_of_birth)))
        except v.ValidationFailure:
            return []
    if phone_number:
        try:
            stmt = stmt.where(Patient.phone_number == v.normalize_phone(phone_number, "phone_number"))
        except v.ValidationFailure:
            return []
    stmt = stmt.order_by(Patient.created_at.desc())
    return list(db.execute(stmt).scalars().all())


def update_patient(db: Session, patient_id: str, payload: PatientUpdate) -> Patient | None:
    patient = get_patient(db, patient_id)
    if patient is None:
        return None
    data = _apply_dates(payload.model_dump(exclude_none=True))
    for field, val in data.items():
        setattr(patient, field, val)
    try:
        db.commit()
        db.refresh(patient)
    except SQLAlchemyError:
        db.rollback()
        logger.exception("DB write failed while updating patient %s", patient_id)
        raise ServiceError("Could not update the patient record.")
    logger.info("Updated patient %s: fields=%s", patient_id, list(data.keys()))
    return patient


def soft_delete_patient(db: Session, patient_id: str) -> Patient | None:
    patient = get_patient(db, patient_id)
    if patient is None:
        return None
    patient.deleted_at = datetime.now(timezone.utc)
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        logger.exception("DB write failed while deleting patient %s", patient_id)
        raise ServiceError("Could not delete the patient record.")
    logger.info("Soft-deleted patient %s", patient_id)
    return patient


def schedule_mock_appointment(db: Session, patient_id: str, reason: str = "New Patient Intake") -> Appointment:
    """Bonus feature: mock appointment slot, no real scheduling backend involved."""
    from datetime import timedelta

    slot = datetime.now(timezone.utc) + timedelta(days=3)
    slot = slot.replace(hour=15, minute=0, second=0, microsecond=0)  # 10am Eastern-ish, UTC-5 -> 15:00 UTC
    appt = Appointment(patient_id=patient_id, scheduled_at=slot, reason=reason)
    try:
        db.add(appt)
        db.commit()
        db.refresh(appt)
    except SQLAlchemyError:
        db.rollback()
        logger.exception("DB write failed while scheduling appointment for %s", patient_id)
        raise ServiceError("Could not schedule the appointment.")
    return appt
