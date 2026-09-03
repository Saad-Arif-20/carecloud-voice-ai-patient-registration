"""Point the app at a throwaway temp DB/log file BEFORE app.main (and therefore
app.config/app.database) get imported by any test module, so tests never touch the real
data/patients.db used by local dev or production."""
import os
import tempfile

_tmp_dir = tempfile.mkdtemp(prefix="carecloud_test_")
os.environ["DATABASE_PATH"] = os.path.join(_tmp_dir, "test.db")
os.environ["LOG_FILE"] = os.path.join(_tmp_dir, "test.log")

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c
