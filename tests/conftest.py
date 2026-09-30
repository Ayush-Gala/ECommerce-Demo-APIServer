import sys

from tests import fake_ibm_db

sys.modules["ibm_db"] = fake_ibm_db

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402


def make_settings(**overrides) -> Settings:
    values = dict(
        db2_host="db2.test",
        db2_port=50000,
        db2_database="COMMERCE",
        db2_user="db2inst1",
        db2_password="secret",
        pool_min_size=1,
        pool_max_size=2,
        pool_acquire_timeout=0.2,
        app_port=8000,
        log_level="INFO",
    )
    values.update(overrides)
    return Settings(**values)


@pytest.fixture
def fake_db():
    fake_ibm_db.STATE.reset()
    yield fake_ibm_db
    fake_ibm_db.STATE.reset()


@pytest.fixture
def make_client(fake_db):
    clients = []

    def _make(**overrides):
        client = TestClient(create_app(make_settings(**overrides)), raise_server_exceptions=False)
        client.__enter__()
        clients.append(client)
        return client

    yield _make
    for c in clients:
        c.__exit__(None, None, None)


@pytest.fixture
def client(make_client):
    return make_client()
