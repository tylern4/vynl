import os
import sys
from pathlib import Path
from urllib.parse import quote_plus

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = BACKEND_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))


def _load_local_env() -> None:
    """Seed env defaults from the repo .env so tests work against local dev Postgres."""
    env_path = REPO_DIR / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key, value.strip().strip('"').strip("'"))


_load_local_env()

db_user = quote_plus(os.environ.get("POSTGRES_USER", "vynl"))
db_password = quote_plus(os.environ.get("POSTGRES_PASSWORD", "vynl"))
db_name = os.environ.get("POSTGRES_DB", "vynl")
os.environ.setdefault(
    "DATABASE_URL",
    f"postgresql+psycopg://{db_user}:{db_password}@localhost:5432/{db_name}_test",
)
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("INVITE_CODE", "change-me")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from src.config import settings
from src.database import get_db
from src.migrations import run_migrations
from src.models import Base
from src.main import app


def _ensure_database(url: str) -> None:
    """Recreate a pristine test database on the Postgres server."""
    admin_url = url.rsplit("/", 1)[0] + "/postgres"
    dbname = url.rsplit("/", 1)[1]
    engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with engine.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{dbname}" WITH (FORCE)'))
        conn.execute(text(f'CREATE DATABASE "{dbname}"'))
    engine.dispose()


@pytest.fixture(scope="session")
def engine():
    """Apply migrations to the test database and expose a bound engine."""
    _ensure_database(settings.database_url)
    run_migrations()
    test_engine = create_engine(settings.database_url)
    Base.metadata.create_all(test_engine)
    yield test_engine
    Base.metadata.drop_all(test_engine)
    test_engine.dispose()


@pytest.fixture()
def db_session(engine):
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = factory()
    yield session
    session.close()


@pytest.fixture(autouse=True)
def _clean_tables(engine):
    with engine.begin() as conn:
        conn.execute(
            text(
                "TRUNCATE TABLE users, albums, tracks, tags, album_tags, plays "
                "RESTART IDENTITY CASCADE"
            )
        )
    yield


@pytest.fixture()
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    test_client = TestClient(app)
    yield test_client
    app.dependency_overrides.clear()


@pytest.fixture()
def register_user(client):
    def _register(
        name="Alice",
        email="alice@example.com",
        password="password123",
        invite_code=settings.invite_code,
    ):
        return client.post(
            "/api/auth/register",
            json={
                "name": name,
                "email": email,
                "password": password,
                "invite_code": invite_code,
            },
        )

    return _register


@pytest.fixture()
def admin(client, register_user):
    res = register_user(
        name="Admin",
        email="admin@example.com",
        invite_code=settings.invite_code,
    )
    assert res.status_code == 201, res.text
    return res.json()["user"]


@pytest.fixture()
def auth_headers(client):
    def _headers(email: str, password: str = "password123"):
        res = client.post(
            "/api/auth/login", json={"email": email, "password": password}
        )
        assert res.status_code == 200, res.text
        return {"Authorization": f"Bearer {res.json()['access_token']}"}

    return _headers
