"""
Reusable, server-side validation helpers.

These are the single source of truth for "is this field valid" -- used by the Pydantic
schemas (app/schemas.py) so the same rules apply whether a record comes in through the
public REST API or through the Vapi voice-agent tool-calls webhook. The assessment is
explicit that validation must not rely solely on the voice agent, so nothing here trusts
the LLM to have already cleaned the data.
"""
import re
from datetime import date, datetime

US_STATES = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID", "IL", "IN",
    "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV",
    "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC", "SD", "TN",
    "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
    "DC", "PR", "GU", "VI", "AS", "MP",  # DC + common US territories
}

# Alphabetic + hyphen/apostrophe per the spec. We allow an internal space too (documented
# deviation in README) since compound legal names ("Van Der Berg", "Mary Jane") are common
# and rejecting them outright would be a worse caller experience than the spec's letter is
# strict about.
_NAME_RE = re.compile(r"^[A-Za-z]+(?:[ '\-][A-Za-z]+)*$")

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_ZIP_RE = re.compile(r"^\d{5}(-\d{4})?$")
_MEMBER_ID_RE = re.compile(r"^[A-Za-z0-9]{1,30}$")

SEX_VALUES = ("Male", "Female", "Other", "Decline to Answer")


class ValidationFailure(ValueError):
    """Raised with a message intended to be safe to read back to a caller/API client."""


def validate_name(value: str, field_label: str) -> str:
    v = (value or "").strip()
    if not (1 <= len(v) <= 50):
        raise ValidationFailure(f"{field_label} must be between 1 and 50 characters.")
    if not _NAME_RE.match(v):
        raise ValidationFailure(
            f"{field_label} may only contain letters, hyphens, and apostrophes."
        )
    return v


def normalize_phone(value: str, field_label: str) -> str:
    digits = re.sub(r"\D", "", value or "")
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]  # strip US country code
    if len(digits) != 10:
        raise ValidationFailure(
            f"{field_label} must be a valid U.S. phone number with exactly 10 digits."
        )
    if digits[0] in ("0", "1"):
        raise ValidationFailure(f"{field_label} is not a valid U.S. phone number (bad area code).")
    return digits


def parse_dob(value: str) -> str:
    """Accepts MM/DD/YYYY (per spec) or ISO YYYY-MM-DD, returns normalized MM/DD/YYYY."""
    s = str(value).strip()
    parsed: date | None = None
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m-%d-%Y"):
        try:
            parsed = datetime.strptime(s, fmt).date()
            break
        except ValueError:
            continue
    if parsed is None:
        raise ValidationFailure("date_of_birth must be a valid date in MM/DD/YYYY format.")
    if parsed > date.today():
        raise ValidationFailure("date_of_birth cannot be in the future.")
    if parsed.year < 1900:
        raise ValidationFailure("date_of_birth must be a realistic birth date (year 1900 or later).")
    return parsed.strftime("%m/%d/%Y")


def dob_str_to_date(value: str) -> date:
    return datetime.strptime(value, "%m/%d/%Y").date()


def date_to_dob_str(value: date) -> str:
    return value.strftime("%m/%d/%Y")


def validate_sex(value: str) -> str:
    v = (value or "").strip()
    # Be forgiving of case/wording since this comes out of speech-to-text.
    lookup = {s.lower(): s for s in SEX_VALUES}
    lookup.update({"m": "Male", "f": "Female", "decline": "Decline to Answer",
                   "prefer not to say": "Decline to Answer", "rather not say": "Decline to Answer"})
    if v.lower() not in lookup:
        raise ValidationFailure(
            "sex must be one of: Male, Female, Other, Decline to Answer."
        )
    return lookup[v.lower()]


def validate_email(value: str) -> str:
    v = (value or "").strip()
    if not _EMAIL_RE.match(v):
        raise ValidationFailure("email is not a valid email address.")
    return v


def validate_state(value: str) -> str:
    v = (value or "").strip().upper()
    if v not in US_STATES:
        raise ValidationFailure("state must be a valid 2-letter U.S. state abbreviation.")
    return v


def validate_zip(value: str) -> str:
    v = (value or "").strip()
    if not _ZIP_RE.match(v):
        raise ValidationFailure("zip_code must be a 5-digit or ZIP+4 U.S. format (e.g. 12345 or 12345-6789).")
    return v


def validate_city(value: str) -> str:
    v = (value or "").strip()
    if not (1 <= len(v) <= 100):
        raise ValidationFailure("city must be between 1 and 100 characters.")
    return v


def validate_member_id(value: str) -> str:
    v = (value or "").strip()
    if not _MEMBER_ID_RE.match(v):
        raise ValidationFailure("insurance_member_id must be alphanumeric (up to 30 characters).")
    return v
