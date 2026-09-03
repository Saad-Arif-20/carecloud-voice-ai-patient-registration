"""
Bonus: automated tests for the REST API layer -- create/read/update/soft-delete, filters,
and the server-side validation the assessment explicitly requires (invalid data must be
rejected with 422 regardless of what the voice agent already checked).
"""


def _valid_patient(**overrides):
    payload = {
        "first_name": "Alice",
        "last_name": "Johnson",
        "date_of_birth": "05/12/1988",
        "sex": "Female",
        "phone_number": "2135551212",
        "email": "alice.johnson@example.com",
        "address_line_1": "789 Pine St",
        "city": "Los Angeles",
        "state": "CA",
        "zip_code": "90001",
    }
    payload.update(overrides)
    return payload


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200


def test_seed_data_present(client):
    resp = client.get("/patients", params={"last_name": "Doe"})
    body = resp.json()
    assert resp.status_code == 200
    assert body["error"] is None
    assert any(p["first_name"] == "Jane" for p in body["data"])


def test_create_and_get_patient(client):
    resp = client.post("/patients", json=_valid_patient())
    assert resp.status_code == 201
    body = resp.json()
    assert body["error"] is None
    assert body["data"]["patient_id"]
    assert body["data"]["date_of_birth"] == "05/12/1988"

    patient_id = body["data"]["patient_id"]
    resp2 = client.get(f"/patients/{patient_id}")
    assert resp2.status_code == 200
    assert resp2.json()["data"]["last_name"] == "Johnson"


def test_get_unknown_patient_returns_404(client):
    resp = client.get("/patients/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404
    assert resp.json()["data"] is None
    assert resp.json()["error"] is not None


def test_missing_required_field_returns_422(client):
    payload = _valid_patient()
    del payload["address_line_1"]
    resp = client.post("/patients", json=payload)
    assert resp.status_code == 422
    assert resp.json()["error"] is not None


def test_future_date_of_birth_rejected(client):
    resp = client.post("/patients", json=_valid_patient(date_of_birth="01/01/2999"))
    assert resp.status_code == 422


def test_invalid_phone_number_rejected(client):
    resp = client.post("/patients", json=_valid_patient(phone_number="123"))
    assert resp.status_code == 422


def test_invalid_state_rejected(client):
    resp = client.post("/patients", json=_valid_patient(state="ZZ"))
    assert resp.status_code == 422


def test_invalid_sex_rejected(client):
    resp = client.post("/patients", json=_valid_patient(sex="Robot"))
    assert resp.status_code == 422


def test_list_filter_by_phone_number(client):
    created = client.post("/patients", json=_valid_patient(phone_number="3105557890")).json()["data"]
    resp = client.get("/patients", params={"phone_number": "3105557890"})
    assert resp.status_code == 200
    ids = [p["patient_id"] for p in resp.json()["data"]]
    assert created["patient_id"] in ids


def test_list_filter_by_partial_last_name(client):
    client.post("/patients", json=_valid_patient(last_name="Winterbourne", phone_number="2135550001"))
    resp = client.get("/patients", params={"last_name": "inter"})  # substring, wrong case
    assert resp.status_code == 200
    assert any(p["last_name"] == "Winterbourne" for p in resp.json()["data"])


def test_list_filter_by_q_matches_first_or_last_name(client):
    client.post("/patients", json=_valid_patient(first_name="Zendaya", last_name="Okafor", phone_number="2135550002"))
    by_first = client.get("/patients", params={"q": "zend"})
    by_last = client.get("/patients", params={"q": "okaf"})
    assert any(p["first_name"] == "Zendaya" for p in by_first.json()["data"])
    assert any(p["first_name"] == "Zendaya" for p in by_last.json()["data"])


def test_update_partial(client):
    created = client.post("/patients", json=_valid_patient(phone_number="4155551111")).json()["data"]
    resp = client.put(f"/patients/{created['patient_id']}", json={"city": "San Francisco"})
    assert resp.status_code == 200
    body = resp.json()["data"]
    assert body["city"] == "San Francisco"
    assert body["last_name"] == "Johnson"  # untouched fields survive a partial update


def test_update_unknown_patient_returns_404(client):
    resp = client.put("/patients/00000000-0000-0000-0000-000000000000", json={"city": "Nowhere"})
    assert resp.status_code == 404


def test_soft_delete_hides_but_does_not_erase(client):
    created = client.post("/patients", json=_valid_patient(phone_number="6175559999")).json()["data"]
    patient_id = created["patient_id"]

    resp = client.delete(f"/patients/{patient_id}")
    assert resp.status_code == 200

    # No longer retrievable via the normal API ...
    assert client.get(f"/patients/{patient_id}").status_code == 404

    # ... but the row is a soft delete, not a hard delete, per spec.
    from app.database import SessionLocal
    from app.models import Patient

    db = SessionLocal()
    try:
        row = db.get(Patient, patient_id)
        assert row is not None
        assert row.deleted_at is not None
    finally:
        db.close()


def test_persistence_survives_new_session(client):
    """Simulates 'call back later': a fresh DB session must still see prior writes."""
    created = client.post("/patients", json=_valid_patient(phone_number="9295550000")).json()["data"]

    from app.database import SessionLocal
    from app.models import Patient

    db = SessionLocal()
    try:
        row = db.get(Patient, created["patient_id"])
        assert row is not None
        assert row.first_name == "Alice"
    finally:
        db.close()
