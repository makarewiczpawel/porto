from functools import lru_cache

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

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
