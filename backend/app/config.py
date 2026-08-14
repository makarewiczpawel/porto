from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Porto API"
    version: str = "0.1.0"
    debug: bool = False

    database_url: str = "postgresql+psycopg://porto@localhost:5432/porto"

    jwt_secret: str = "change-me-in-production"
    jwt_refresh_secret: str = "change-me-too-in-production"
    access_token_minutes: int = 15
    refresh_token_days: int = 30

    # Registration is closed: an account can only be created with this code.
    invite_code: str = "porto"

    # Comma-separated list; the frontend origin must be explicit because the API
    # sends credentials (the refresh cookie) and wildcards are rejected then.
    cors_origins: str = "http://localhost:5173"

    # Cookie has to be readable by the frontend subdomain, hence the leading dot
    # in production (".pmakarewicz.com"). Empty means "host only", which is what
    # local development needs.
    cookie_domain: str = ""
    cookie_secure: bool = False
    # "lax" works whenever the frontend and the API share a registrable domain
    # (porto.pmakarewicz.com + api-porto.pmakarewicz.com). Only reach for "none"
    # if they ever end up on genuinely different sites — and that also requires
    # cookie_secure=true, or browsers drop the cookie silently.
    cookie_samesite: str = "lax"

    # ── synteza mowy ──────────────────────────────────────────────────────
    # Pusty klucz nie jest błędem: aplikacja działa bez audio, a przycisk
    # głośnika schodzi wtedy na głos wbudowany w przeglądarkę.
    google_tts_api_key: str = ""
    # Wavenet-A istnieje w pt-PT od lat i brzmi naturalnie. Listę wszystkich
    # dostępnych głosów zwraca `GET /api/audio/voices` — prosto od Google, więc
    # nie trzeba zgadywać, co dostawca akurat oferuje.
    tts_voice_default: str = "pt-PT-Wavenet-A"
    # Cała baza to ~15 tys. znaków, więc ten limit jest dziesięciokrotnym
    # zapasem, a nie ograniczeniem. Chodzi o to, żeby błąd w pętli nie zamienił
    # się w rachunek.
    tts_monthly_char_limit: int = 150_000

    # ── AI ────────────────────────────────────────────────────────────────
    # Bez klucza aplikacja działa jak dotąd, tylko ekrany AI mówią wprost, że
    # są wyłączone. Tak samo jak przy syntezie mowy: brak klucza to konfiguracja,
    # nie awaria.
    anthropic_api_key: str = ""
    ai_model: str = "claude-opus-5"
    # Rachunek za model rośnie po cichu. Ten limit jest twardy: po jego
    # przekroczeniu każde wywołanie kończy się czytelnym 429, a nie fakturą.
    # 5 USD to przy generowaniu zestawów kilkaset pozycji miesięcznie.
    ai_monthly_budget_usd: float = 5.0
    # Ile pozycji wolno poprosić za jednym razem. Powyżej tego odpowiedź robi
    # się długa, wolna i gorszej jakości.
    ai_max_items_per_set: int = 30

    @field_validator("database_url")
    @classmethod
    def _use_psycopg_driver(cls, value: str) -> str:
        """Accept the connection string exactly as hosting providers hand it out.

        Railway (and Heroku, and most managed Postgres) expose `postgresql://…`
        or the legacy `postgres://…`. SQLAlchemy reads that as "use psycopg2",
        which is not installed, and the app dies on boot with a driver error.
        Normalising here means the deployment variable can be pasted verbatim.
        """
        for prefix in ("postgresql+psycopg://", "postgresql+psycopg2://", "postgresql+asyncpg://"):
            if value.startswith(prefix):
                return value
        for prefix in ("postgresql://", "postgres://"):
            if value.startswith(prefix):
                return "postgresql+psycopg://" + value[len(prefix) :]
        return value

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
