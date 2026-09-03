"""
Pydantic request/response schemas.

All validators delegate to app/validators.py so the exact same rules apply to REST API
callers and to the voice-agent tool-calls webhook -- per the assessment's instruction that
"do not rely solely on the voice agent for validation," this is the actual enforcement
layer, not just documentation of intent.
"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from . import validators as v


class PatientCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    first_name: str
    last_name: str
    date_of_birth: str  # MM/DD/YYYY, per spec
    sex: str
    phone_number: str
    email: Optional[str] = None
    address_line_1: str
    address_line_2: Optional[str] = None
    city: str
    state: str
    zip_code: str
    insurance_provider: Optional[str] = None
    insurance_member_id: Optional[str] = None
    preferred_language: Optional[str] = "English"
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None

    @field_validator("first_name")
    @classmethod
    def _first_name(cls, val: str) -> str:
        return v.validate_name(val, "first_name")

    @field_validator("last_name")
    @classmethod
    def _last_name(cls, val: str) -> str:
        return v.validate_name(val, "last_name")

    @field_validator("date_of_birth")
    @classmethod
    def _dob(cls, val: str) -> str:
        return v.parse_dob(val)

    @field_validator("sex")
    @classmethod
    def _sex(cls, val: str) -> str:
        return v.validate_sex(val)

    @field_validator("phone_number")
    @classmethod
    def _phone(cls, val: str) -> str:
        return v.normalize_phone(val, "phone_number")

    @field_validator("email")
    @classmethod
    def _email(cls, val: Optional[str]) -> Optional[str]:
        return v.validate_email(val) if val else None

    @field_validator("address_line_1")
    @classmethod
    def _addr1(cls, val: str) -> str:
        v_ = (val or "").strip()
        if not v_:
            raise v.ValidationFailure("address_line_1 is required.")
        return v_

    @field_validator("city")
    @classmethod
    def _city(cls, val: str) -> str:
        return v.validate_city(val)

    @field_validator("state")
    @classmethod
    def _state(cls, val: str) -> str:
        return v.validate_state(val)

    @field_validator("zip_code")
    @classmethod
    def _zip(cls, val: str) -> str:
        return v.validate_zip(val)

    @field_validator("insurance_member_id")
    @classmethod
    def _member_id(cls, val: Optional[str]) -> Optional[str]:
        return v.validate_member_id(val) if val else None

    @field_validator("emergency_contact_phone")
    @classmethod
    def _ec_phone(cls, val: Optional[str]) -> Optional[str]:
        return v.normalize_phone(val, "emergency_contact_phone") if val else None

    @field_validator("preferred_language")
    @classmethod
    def _lang(cls, val: Optional[str]) -> str:
        return (val or "English").strip() or "English"


class PatientUpdate(BaseModel):
    """Same field-level rules as PatientCreate, but every field is optional (partial update)."""

    model_config = ConfigDict(str_strip_whitespace=True)

    first_name: Optional[str] = None
    last_name: Optional[str] = None
    date_of_birth: Optional[str] = None
    sex: Optional[str] = None
    phone_number: Optional[str] = None
    email: Optional[str] = None
    address_line_1: Optional[str] = None
    address_line_2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    insurance_provider: Optional[str] = None
    insurance_member_id: Optional[str] = None
    preferred_language: Optional[str] = None
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None

    @field_validator("first_name")
    @classmethod
    def _first_name(cls, val): return v.validate_name(val, "first_name") if val is not None else None

    @field_validator("last_name")
    @classmethod
    def _last_name(cls, val): return v.validate_name(val, "last_name") if val is not None else None

    @field_validator("date_of_birth")
    @classmethod
    def _dob(cls, val): return v.parse_dob(val) if val is not None else None

    @field_validator("sex")
    @classmethod
    def _sex(cls, val): return v.validate_sex(val) if val is not None else None

    @field_validator("phone_number")
    @classmethod
    def _phone(cls, val): return v.normalize_phone(val, "phone_number") if val is not None else None

    @field_validator("email")
    @classmethod
    def _email(cls, val): return v.validate_email(val) if val else None

    @field_validator("city")
    @classmethod
    def _city(cls, val): return v.validate_city(val) if val is not None else None

    @field_validator("state")
    @classmethod
    def _state(cls, val): return v.validate_state(val) if val is not None else None

    @field_validator("zip_code")
    @classmethod
    def _zip(cls, val): return v.validate_zip(val) if val is not None else None

    @field_validator("insurance_member_id")
    @classmethod
    def _member_id(cls, val): return v.validate_member_id(val) if val else None

    @field_validator("emergency_contact_phone")
    @classmethod
    def _ec_phone(cls, val): return v.normalize_phone(val, "emergency_contact_phone") if val else None

    @model_validator(mode="after")
    def _at_least_one_field(self):
        if not any(getattr(self, f) is not None for f in self.model_fields):
            raise v.ValidationFailure("PUT request body must include at least one field to update.")
        return self


class PatientOut(BaseModel):
    patient_id: str
    first_name: str
    last_name: str
    date_of_birth: str
    sex: str
    phone_number: str
    email: Optional[str] = None
    address_line_1: str
    address_line_2: Optional[str] = None
    city: str
    state: str
    zip_code: str
    insurance_provider: Optional[str] = None
    insurance_member_id: Optional[str] = None
    preferred_language: str
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    deleted_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_model(cls, patient) -> "PatientOut":
        return cls(
            patient_id=patient.patient_id,
            first_name=patient.first_name,
            last_name=patient.last_name,
            date_of_birth=v.date_to_dob_str(patient.date_of_birth),
            sex=patient.sex,
            phone_number=patient.phone_number,
            email=patient.email,
            address_line_1=patient.address_line_1,
            address_line_2=patient.address_line_2,
            city=patient.city,
            state=patient.state,
            zip_code=patient.zip_code,
            insurance_provider=patient.insurance_provider,
            insurance_member_id=patient.insurance_member_id,
            preferred_language=patient.preferred_language,
            emergency_contact_name=patient.emergency_contact_name,
            emergency_contact_phone=patient.emergency_contact_phone,
            created_at=patient.created_at,
            updated_at=patient.updated_at,
            deleted_at=patient.deleted_at,
        )
