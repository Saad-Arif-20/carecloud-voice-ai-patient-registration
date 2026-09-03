import uuid
from datetime import date, datetime, timezone

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base
from .validators import SEX_VALUES, US_STATES


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _uuid() -> str:
    return str(uuid.uuid4())


_STATE_LIST_SQL = ",".join(f"'{s}'" for s in sorted(US_STATES))
_SEX_LIST_SQL = ",".join(f"'{s}'" for s in SEX_VALUES)


class Patient(Base):
    """
    The standard-minimum-demographic-dataset patient record described in the assessment.

    Design notes:
    - date_of_birth is stored as a native Date column (not a string) so the database can
      enforce/query it properly; the API layer converts to/from the MM/DD/YYYY string the
      spec asks for at the boundary (see app/schemas.py).
    - phone numbers are stored as normalized 10-digit strings (no formatting) so lookups
      (e.g. duplicate-caller detection) are exact-match and index-friendly.
    - Soft delete via deleted_at per spec (DELETE must not hard-delete).
    - CHECK constraints mirror the Pydantic validation so bad data can't sneak in even via
      a direct DB write that skips the service layer.
    """

    __tablename__ = "patients"
    __table_args__ = (
        CheckConstraint(f"sex IN ({_SEX_LIST_SQL})", name="ck_patients_sex"),
        CheckConstraint(f"state IN ({_STATE_LIST_SQL})", name="ck_patients_state"),
        CheckConstraint("length(phone_number) = 10", name="ck_patients_phone_len"),
        Index("ix_patients_last_name", "last_name"),
        Index("ix_patients_phone_number", "phone_number"),
    )

    patient_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)

    first_name: Mapped[str] = mapped_column(String(50), nullable=False)
    last_name: Mapped[str] = mapped_column(String(50), nullable=False)
    date_of_birth: Mapped[date] = mapped_column(Date, nullable=False)
    sex: Mapped[str] = mapped_column(String(20), nullable=False)
    phone_number: Mapped[str] = mapped_column(String(10), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)

    address_line_1: Mapped[str] = mapped_column(String(255), nullable=False)
    address_line_2: Mapped[str | None] = mapped_column(String(255), nullable=True)
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    state: Mapped[str] = mapped_column(String(2), nullable=False)
    zip_code: Mapped[str] = mapped_column(String(10), nullable=False)

    insurance_provider: Mapped[str | None] = mapped_column(String(255), nullable=True)
    insurance_member_id: Mapped[str | None] = mapped_column(String(30), nullable=True)
    preferred_language: Mapped[str] = mapped_column(String(50), nullable=False, default="English")
    emergency_contact_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    emergency_contact_phone: Mapped[str | None] = mapped_column(String(10), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class CallLog(Base):
    """
    Bonus: call transcript/summary storage, linked to the patient record it produced (if
    any -- a call that never completed registration still gets logged with patient_id NULL
    so nothing is silently dropped).
    """

    __tablename__ = "call_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    patient_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("patients.patient_id"), nullable=True
    )
    vapi_call_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    ended_reason: Mapped[str | None] = mapped_column(String(100), nullable=True)
    transcript: Mapped[str | None] = mapped_column(String, nullable=True)
    summary: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False)


class Appointment(Base):
    """Bonus: mock appointment scheduling, offered after a successful registration."""

    __tablename__ = "appointments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    patient_id: Mapped[str] = mapped_column(String(36), ForeignKey("patients.patient_id"), nullable=False)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    reason: Mapped[str] = mapped_column(String(255), nullable=False, default="New Patient Intake")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False)
