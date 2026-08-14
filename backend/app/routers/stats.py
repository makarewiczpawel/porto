"""Statystyki nauki: co się wydarzyło, co dopiero wypadnie i co nie wchodzi.

Trzy pytania, na które ten router odpowiada, i dla każdego osobny powód:

- **Czy się uczę regularnie?** Mapa aktywności. Rytm widać dopiero na tle dni
  pustych, więc te też są w odpowiedzi.
- **Co mnie czeka?** Prognoza powtórek. Zaległości lądują w dniu dzisiejszym,
  bo właśnie tam czekają, a nie w dniu, w którym miały wypaść.
- **Co mi nie wchodzi?** Lista słów z najgorszą skutecznością, z akcjami:
  zawieś albo zacznij od zera.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models import Item, Review, User, UserItemState
from app.services import stats as stats_service

router = APIRouter(prefix="/api/stats", tags=["stats"])


@router.get("/overview")
def overview(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    now = datetime.now(timezone.utc)
    by_state = dict(
        db.execute(
            select(UserItemState.state, func.count())
            .where(UserItemState.user_id == user.id)
            .group_by(UserItemState.state)
        ).all()
    )
    total_items = db.execute(
        select(func.count()).select_from(Item).where(Item.verified.is_(True))
    ).scalar_one()
    reviews_total, correct_total, seconds_total = db.execute(
        select(
            func.count(),
            func.count().filter(Review.is_correct.is_(True)),
            func.coalesce(func.sum(Review.elapsed_ms), 0) / 1000,
        ).where(Review.user_id == user.id)
    ).one()

    return {
        "streak": stats_service.streak(db, user, stats_service.local_day(user, now)),
        "cards_by_state": by_state,
        "items_total": total_items,
        "reviews_total": int(reviews_total),
        "accuracy": round(correct_total / reviews_total * 100, 1) if reviews_total else 0.0,
        # Retencja to co innego niż skuteczność od początku świata: liczy tylko
        # ostatni miesiąc i tylko karty powtarzane. To ona mówi, czy materiał
        # zostaje w głowie teraz.
        "retention_30d": stats_service.retention(db, user, now),
        "seconds_total": int(seconds_total or 0),
    }


@router.get("/heatmap")
def heatmap(
    days: int = Query(default=182, ge=7, le=730),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    today = stats_service.local_day(user, datetime.now(timezone.utc))
    entries = stats_service.heatmap(db, user, today, days)
    return {
        "days": entries,
        "total_reviews": sum(day["reviews"] for day in entries),
        "active_days": sum(1 for day in entries if day["reviews"] > 0),
    }


@router.get("/forecast")
def forecast(
    days: int = Query(default=14, ge=3, le=60),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    entries = stats_service.forecast(db, user, datetime.now(timezone.utc), days)
    return {"days": entries, "total": sum(day["due"] for day in entries)}


@router.get("/hardest")
def hardest(
    limit: int = Query(default=10, ge=1, le=50),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    return {"items": stats_service.hardest(db, user, limit)}
