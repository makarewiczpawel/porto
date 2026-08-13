import pytest

from app.config import Settings


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        # What Railway and Heroku actually put in the variable.
        ("postgresql://user:pw@host:5432/db", "postgresql+psycopg://user:pw@host:5432/db"),
        ("postgres://user:pw@host:5432/db", "postgresql+psycopg://user:pw@host:5432/db"),
        # Already explicit — left alone.
        ("postgresql+psycopg://user:pw@host:5432/db", "postgresql+psycopg://user:pw@host:5432/db"),
        # A deliberately different driver must not be rewritten.
        ("postgresql+asyncpg://user:pw@host:5432/db", "postgresql+asyncpg://user:pw@host:5432/db"),
        # Non-Postgres URLs pass through untouched.
        ("sqlite:///local.db", "sqlite:///local.db"),
    ],
)
def test_database_url_gets_the_psycopg_driver(given: str, expected: str):
    assert Settings(database_url=given).database_url == expected


def test_password_with_special_characters_survives():
    """Providers generate passwords with slashes and colons — the rewrite must
    only touch the scheme, never the rest of the string."""
    given = "postgresql://porto:a/b:c@d@host.railway.internal:5432/railway"
    assert Settings(database_url=given).database_url == (
        "postgresql+psycopg://porto:a/b:c@d@host.railway.internal:5432/railway"
    )


def test_cors_origins_split_on_commas():
    settings = Settings(cors_origins=" https://a.example.com, https://b.example.com ,")
    assert settings.cors_origin_list == ["https://a.example.com", "https://b.example.com"]
