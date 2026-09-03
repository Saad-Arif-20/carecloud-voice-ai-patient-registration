"""Optional demo seed data, per the assessment's "Optionally include 1-2 seed patient
records for demonstration." Only runs if the patients table is empty."""
import logging

from sqlalchemy import select

from .database import SessionLocal
from .models import Patient
from .validators import dob_str_to_date

logger = logging.getLogger("carecloud.seed")

SEED_PATIENTS = [
    dict(
        first_name="Jane",
        last_name="Doe",
        date_of_birth=dob_str_to_date("03/14/1990"),
        sex="Female",
        phone_number="5551234567",
        email="jane.doe@example.com",
        address_line_1="123 Main St",
        address_line_2=None,
        city="Springfield",
        state="IL",
        zip_code="62701",
        insurance_provider="Blue Cross Blue Shield",
        insurance_member_id="BC1234567",
        preferred_language="English",
        emergency_contact_name="John Doe",
        emergency_contact_phone="5559876543",
    ),
    dict(
        first_name="Carlos",
        last_name="Mendez",
        date_of_birth=dob_str_to_date("07/22/1985"),
        sex="Male",
        phone_number="5552223333",
        email=None,
        address_line_1="456 Oak Ave",
        address_line_2="Apt 2B",
        city="Austin",
        state="TX",
        zip_code="73301",
        insurance_provider=None,
        insurance_member_id=None,
        preferred_language="Spanish",
        emergency_contact_name=None,
        emergency_contact_phone=None,
    ),
]


def seed_if_empty() -> None:
    db = SessionLocal()
    try:
        existing = db.execute(select(Patient.patient_id).limit(1)).first()
        if existing:
            return
        for data in SEED_PATIENTS:
            db.add(Patient(**data))
        db.commit()
        logger.info("Seeded %d demo patient record(s).", len(SEED_PATIENTS))
    finally:
        db.close()
