import time
from collections import defaultdict, deque

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.db import get_db
from app.errors import too_many, unauthorized
from app.models import User
from app.security import ACCESS, decode_token


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        raise unauthorized()
    user_id = decode_token(header[7:].strip(), ACCESS)
    if user_id is None:
        raise unauthorized("TOKEN_INVALID", "Sesja wygasła. Zaloguj się ponownie.")
    user = db.get(User, user_id)
    if user is None:
        raise unauthorized("TOKEN_INVALID", "Sesja wygasła. Zaloguj się ponownie.")
    return user


class RateLimiter:
    """Sliding window per client IP, held in process memory.

    Enough for a two-person app on a single instance. If the API is ever scaled
    out, this needs to move to shared storage.
    """

    def __init__(self, limit: int, window_seconds: int, code: str = "RATE_LIMITED"):
        self.limit = limit
        self.window = window_seconds
        self.code = code
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def __call__(self, request: Request) -> None:
        key = request.client.host if request.client else "unknown"
        now = time.monotonic()
        hits = self._hits[key]
        while hits and now - hits[0] > self.window:
            hits.popleft()
        if len(hits) >= self.limit:
            raise too_many(self.code, "Za dużo prób. Spróbuj ponownie za chwilę.")
        hits.append(now)

    def reset(self) -> None:
        self._hits.clear()


auth_rate_limit = RateLimiter(limit=10, window_seconds=60, code="AUTH_RATE_LIMITED")
