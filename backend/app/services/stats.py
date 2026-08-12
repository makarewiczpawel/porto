"""Daily aggregates and the streak.

A "day" is a calendar day in the user's own timezone, not UTC — otherwise the
streak would break at 01:00 or 02:00 local time depending on the season.
"""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import DailyStat, User, UserSettings


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
