import os
import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Point the app at a scratch database before anything imports the settings.
BASE_URL = os.environ.get("TEST_DATABASE_URL", "postgresql+psycopg://porto@127.0.0.1:5433")
TEST_DB = "porto_test"
os.environ["DATABASE_URL"] = f"{BASE_URL}/{TEST_DB}"
os.environ["INVITE_CODE"] = "test-invite"
os.environ["JWT_SECRET"] = "test-secret"
os.environ["JWT_REFRESH_SECRET"] = "test-refresh-secret"

from app.db import engine, get_db  # noqa: E402
from app.deps import auth_rate_limit  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Base, Deck, DeckItem, Example, Item  # noqa: E402


def _recreate_database() -> None:
    admin = create_engine(f"{BASE_URL}/postgres", isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(
            text(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = :name AND pid <> pg_backend_pid()"
            ),
            {"name": TEST_DB},
        )
        conn.execute(text(f'DROP DATABASE IF EXISTS "{TEST_DB}"'))
        conn.execute(text(f'CREATE DATABASE "{TEST_DB}"'))
    admin.dispose()


@pytest.fixture(scope="session", autouse=True)
def database():
    _recreate_database()
    Base.metadata.create_all(engine)
    yield
    engine.dispose()


TestingSession = None


@pytest.fixture
def db(database):
    global TestingSession
    if TestingSession is None:
        TestingSession = sessionmaker(bind=engine, autoflush=False, future=True)
    session = TestingSession()
    yield session
    session.close()


@pytest.fixture(autouse=True)
def clean_tables(database):
    """Every test starts from an empty database — no order dependencies."""
    with engine.begin() as conn:
        tables = ",".join(f'"{t.name}"' for t in reversed(Base.metadata.sorted_tables))
        conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    auth_rate_limit.reset()
    yield


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def registered(client):
    response = client.post(
        "/api/auth/register",
        json={
            "email": "pawel@example.com",
            "password": "bem-vindo-2026",
            "display_name": "Paweł",
            "invite_code": "test-invite",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    client.headers["Authorization"] = f"Bearer {body['access_token']}"
    return body


def make_items(db, count: int = 12, deck_name: str = "Test", level: str = "A1", pos: str = "noun"):
    """A deck of `count` simple nouns, enough to build sessions from."""
    deck = Deck(slug=f"deck-{uuid.uuid4().hex[:8]}", name=deck_name, position=1, is_shared=True)
    db.add(deck)
    db.flush()
    items = []
    for i in range(count):
        item = Item(
            pt=f"palavra{i}",
            pl=f"slowo{i}",
            article="a",
            gender="f",
            part_of_speech=pos,
            cefr_level=level,
            type="word",
            source="seed",
            verified=True,
        )
        db.add(item)
        db.flush()
        db.add(Example(item_id=item.id, pt=f"Esta é a palavra{i}.", pl=f"To jest slowo{i}.", source="seed"))
        db.add(DeckItem(deck_id=deck.id, item_id=item.id, position=i))
        items.append(item)
    db.commit()
    return deck, items


def now_utc() -> datetime:
    return datetime.now(timezone.utc)
