from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.deps import auth_rate_limit, get_current_user
from app.errors import conflict, forbidden, unauthorized
from app.models import DEFAULT_MODES, User, UserSettings
from app.schemas import LoginIn, MeOut, RegisterIn, TokenOut
from app.security import (
    REFRESH,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])

REFRESH_COOKIE = "porto_refresh"


def _set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        REFRESH_COOKIE,
        token,
        max_age=settings.refresh_token_days * 86400,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,  # type: ignore[arg-type]
        domain=settings.cookie_domain or None,
        path="/api/auth",
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        REFRESH_COOKIE, domain=settings.cookie_domain or None, path="/api/auth"
    )


@router.post("/register", response_model=TokenOut, dependencies=[Depends(auth_rate_limit)])
def register(body: RegisterIn, response: Response, db: Session = Depends(get_db)) -> TokenOut:
    if body.invite_code != settings.invite_code:
        raise forbidden("INVITE_INVALID", "Nieprawidłowy kod zaproszenia.")

    email = body.email.strip().lower()
    exists = db.execute(select(User.id).where(func.lower(User.email) == email)).scalar_one_or_none()
    if exists:
        raise conflict("EMAIL_TAKEN", "Konto z tym adresem już istnieje.")

    user = User(
        email=email,
        password_hash=hash_password(body.password),
        display_name=body.display_name.strip(),
        timezone=body.timezone,
        last_login_at=datetime.now(timezone.utc),
    )
    user.settings = UserSettings(enabled_modes=list(DEFAULT_MODES))
    db.add(user)
    db.commit()
    db.refresh(user)

    _set_refresh_cookie(response, create_refresh_token(user.id))
    return TokenOut(access_token=create_access_token(user.id), user=user)


@router.post("/login", response_model=TokenOut, dependencies=[Depends(auth_rate_limit)])
def login(body: LoginIn, response: Response, db: Session = Depends(get_db)) -> TokenOut:
    email = body.email.strip().lower()
    user = db.execute(select(User).where(func.lower(User.email) == email)).scalar_one_or_none()
    if user is None or not verify_password(body.password, user.password_hash):
        raise unauthorized("CREDENTIALS_INVALID", "Nieprawidłowy e-mail lub hasło.")

    user.last_login_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(user)

    _set_refresh_cookie(response, create_refresh_token(user.id))
    return TokenOut(access_token=create_access_token(user.id), user=user)


@router.post("/refresh", response_model=TokenOut)
def refresh(request: Request, response: Response, db: Session = Depends(get_db)) -> TokenOut:
    token = request.cookies.get(REFRESH_COOKIE)
    if not token:
        raise unauthorized("NO_REFRESH_TOKEN", "Brak sesji. Zaloguj się.")
    user_id = decode_token(token, REFRESH)
    if user_id is None:
        _clear_refresh_cookie(response)
        raise unauthorized("REFRESH_INVALID", "Sesja wygasła. Zaloguj się ponownie.")
    user = db.get(User, user_id)
    if user is None:
        _clear_refresh_cookie(response)
        raise unauthorized("REFRESH_INVALID", "Sesja wygasła. Zaloguj się ponownie.")

    # Rotate the refresh token on every use.
    _set_refresh_cookie(response, create_refresh_token(user.id))
    return TokenOut(access_token=create_access_token(user.id), user=user)


@router.post("/logout", status_code=204)
def logout(response: Response, _: User = Depends(get_current_user)) -> Response:
    _clear_refresh_cookie(response)
    response.status_code = 204
    return response


@router.get("/me", response_model=MeOut)
def me(user: User = Depends(get_current_user)) -> MeOut:
    return MeOut(user=user, settings=user.settings)
