"""Daily aggregates and the streak.

A "day" is a calendar day in the user's own timezone, not UTC — otherwise the
streak would break at 01:00 or 02:00 local time depending on the season.
"""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import DailyStat, Item, Review, User, UserItemState, UserSettings


def user_zone(user: User) -> ZoneInfo:
    try:
        return ZoneInfo(user.timezone or "Europe/Warsaw")
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("Europe/Warsaw")


def local_day(user: User, moment: datetime) -> date:
    return moment.astimezone(user_zone(user)).date()


def record_activity(
    db: Session,
    user: User,
    user_settings: UserSettings,
    moment: datetime,
    *,
    reviews: int = 0,
    new_cards: int = 0,
    correct: int = 0,
    seconds: int = 0,
) -> DailyStat:
    day = local_day(user, moment)
    stat = db.get(DailyStat, (user.id, day))
    if stat is None:
        stat = DailyStat(user_id=user.id, date=day)
        db.add(stat)
        db.flush()
    stat.reviews_count += reviews
    stat.new_count += new_cards
    stat.correct_count += correct
    stat.time_spent_s += seconds
    stat.goal_met = stat.reviews_count >= user_settings.daily_goal
    return stat


def streak(db: Session, user: User, today: date) -> int:
    """Consecutive days with the daily goal met, counting back from today.

    Today not being finished yet does not break the streak — the count simply
    starts at yesterday in that case.
    """
    days = set(
        db.execute(
            select(DailyStat.date).where(DailyStat.user_id == user.id, DailyStat.goal_met.is_(True))
        )
        .scalars()
        .all()
    )
    if not days:
        return 0
    cursor = today if today in days else today - timedelta(days=1)
    count = 0
    while cursor in days:
        count += 1
        cursor -= timedelta(days=1)
    return count


def today_stat(db: Session, user: User, moment: datetime) -> DailyStat | None:
    return db.get(DailyStat, (user.id, local_day(user, moment)))


# ── faza 5: historia i prognoza ───────────────────────────────────────────
def heatmap(db: Session, user: User, today: date, days: int = 182) -> list[dict]:
    """Aktywność dzień po dniu, od pierwszego dnia nauki albo od `days` wstecz.

    Zwracamy także dni puste. Kalendarz z dziurami tam, gdzie nic nie było, to
    kalendarz kłamiący o rytmie — a rytm jest jedyną rzeczą, którą ta mapa ma
    pokazywać.
    """
    first = db.execute(
        select(func.min(DailyStat.date)).where(DailyStat.user_id == user.id)
    ).scalar_one_or_none()
    if first is None:
        # Konto bez ani jednego dnia nauki. Pół roku pustych kwadratów niczego
        # nie mówi, a wygląda jak zaniedbanie — lepiej nie pokazywać mapy wcale.
        return []
    start = max(today - timedelta(days=days - 1), first)

    rows = {
        row.date: row
        for row in db.execute(
            select(DailyStat).where(DailyStat.user_id == user.id, DailyStat.date >= start)
        ).scalars()
    }
    out: list[dict] = []
    day = start
    while day <= today:
        stat = rows.get(day)
        out.append(
            {
                "date": day.isoformat(),
                "reviews": stat.reviews_count if stat else 0,
                "new": stat.new_count if stat else 0,
                "correct": stat.correct_count if stat else 0,
                "seconds": stat.time_spent_s if stat else 0,
                "goal_met": bool(stat.goal_met) if stat else False,
            }
        )
        day += timedelta(days=1)
    return out


def forecast(db: Session, user: User, now: datetime, days: int = 14) -> list[dict]:
    """Ile powtórek wypada w każdym z najbliższych dni, w strefie użytkownika.

    Zaległości z przeszłości lądują w pierwszym dniu — bo właśnie tam czekają.
    """
    zone = user_zone(user)
    today = now.astimezone(zone).date()
    horizon = today + timedelta(days=days - 1)

    rows = db.execute(
        select(UserItemState.due).where(
            UserItemState.user_id == user.id,
            UserItemState.suspended.is_(False),
            UserItemState.due < datetime.combine(
                horizon + timedelta(days=1), datetime.min.time(), tzinfo=zone
            ),
        )
    ).scalars()

    counts: dict[date, int] = {}
    for due in rows:
        day = max(due.astimezone(zone).date(), today)
        counts[day] = counts.get(day, 0) + 1

    return [
        {"date": (today + timedelta(days=offset)).isoformat(), "due": counts.get(today + timedelta(days=offset), 0)}
        for offset in range(days)
    ]


def retention(db: Session, user: User, now: datetime, days: int = 30) -> float | None:
    """Skuteczność na powtórkach z ostatnich `days` dni.

    Liczona tylko na kartach powtarzanych, bez pierwszego kontaktu z nowym
    słowem — inaczej mierzyłaby, ile nowych pozycji się dodaje, a nie ile się
    pamięta. `None` znaczy „za mało danych", a nie „zero procent".
    """
    since = now - timedelta(days=days)
    total, correct = db.execute(
        select(func.count(), func.count().filter(Review.is_correct.is_(True))).where(
            Review.user_id == user.id,
            Review.reviewed_at >= since,
            Review.mode != "flashcard",
        )
    ).one()
    if not total:
        return None
    return round(correct / total * 100, 1)


def hardest(db: Session, user: User, limit: int = 10, min_reviews: int = 3) -> list[dict]:
    """Słowa, które najczęściej wracają jako pomyłka.

    Próg powtórek jest ważny: bez niego lista to jedno słowo pomylone raz,
    z wynikiem 0%, obok słowa pomylonego pięć razy na dwadzieścia. Pierwsze nie
    jest jeszcze problemem, drugie jest.
    """
    attempts = func.count(Review.id)
    misses = func.count(Review.id).filter(Review.is_correct.is_(False))
    rows = db.execute(
        select(
            Item,
            attempts.label("attempts"),
            misses.label("misses"),
            func.max(Review.reviewed_at).label("last_seen"),
        )
        .join(Review, Review.item_id == Item.id)
        .where(Review.user_id == user.id, Review.mode != "flashcard")
        .group_by(Item.id)
        .having(attempts >= min_reviews)
        .having(misses > 0)
        .order_by((misses * 1.0 / attempts).desc(), misses.desc())
        .limit(limit)
    ).all()

    states = {
        (row.item_id, row.direction): row
        for row in db.execute(
            select(UserItemState).where(
                UserItemState.user_id == user.id,
                UserItemState.item_id.in_([item.id for item, *_ in rows]) if rows else False,
            )
        ).scalars()
    }
    out = []
    for item, count, missed, last_seen in rows:
        related = [s for (item_id, _), s in states.items() if item_id == item.id]
        out.append(
            {
                "item_id": str(item.id),
                "pt": item.display_pt,
                "pl": item.pl,
                "attempts": int(count),
                "misses": int(missed),
                "accuracy": round((count - missed) / count * 100),
                "lapses": max((s.lapses for s in related), default=0),
                "leech": any(s.is_leech for s in related),
                "suspended": any(s.suspended for s in related),
                "last_seen": last_seen.isoformat() if last_seen else None,
            }
        )
    return out
