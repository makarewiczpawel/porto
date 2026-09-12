"""Plan nadrabiania po przerwie — i to, żeby było widać, że się kurczy.

Po dwóch tygodniach przerwy zaległych powtórek potrafi być trzysta. Trzysta
kart naraz to nie nauka, tylko powód, żeby przestać, więc sesja bierze z nich
dzienną porcję, a ekran „Dziś" mówi, ile zostało i na kiedy.

Pierwsza wersja tego planu liczyła porcję jako `zaległości / 7` i pisała
„w 7 dni wrócisz na bieżąco". Wyglądała rozsądnie i była bezużyteczna: nazajutrz
liczyła `250 / 7` i znowu pisała „w 7 dni". **Obietnica nigdy się nie
przybliżała** — każdego ranka ten sam komunikat, te same siedem dni, żadnego
śladu po wczorajszej pracy.

Dlatego plan ma teraz termin i punkt startu, zapisane przy ustawieniach:

- `catch_up_until` — dzień, na który ma być czysto. Odlicza się sam.
- `catch_up_from` — ile zaległości było, gdy plan ruszał. Z tego bierze się
  „nadrobione 84 z 290", czyli jedyna liczba, która naprawdę rośnie.

Porcja na dziś wychodzi z podziału tego, co zostało, przez dni do terminu — więc
dzień opuszczony lekko ją podnosi, a dzień z zapasem obniża. Termin bierze się z
tempa, które użytkownik sam sobie ustawił (`daily_goal`), a nie ze stałej z
kodu: komu wystarcza dziesięć kart dziennie, ten nie dostanie planu po pięćdziesiąt.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.models import User

# Poniżej tylu zaległych nie ma czego rozkładać — to zwykły dzień z górką.
BACKLOG_THRESHOLD = 60
# Nadrabianie idzie szybciej niż zwykły dzień, ale nie ma być karą. Tyle razy
# dzienny cel użytkownika wynosi porcja, do której dąży plan.
COMFORT = 1.5
# Mniej niż tyle powtórek dziennie nie nadrobi żadnego nawisu w rozsądnym czasie.
MIN_PORTION = 10
# Plan krótszy niż dwa dni to nie plan, tylko ta sama ściana z inną etykietą.
MIN_DAYS = 2
# O ile porcja może przekroczyć spokojne tempo, zanim plan uznamy za nieaktualny.
# Dzień czy dwa opuszczone mają ją lekko podnieść; tydzień przerwy w środku
# nadrabiania ma założyć nowy plan, a nie wystawić rachunek za cały tydzień.
OVERRUN = 1.5


@dataclass(frozen=True)
class Plan:
    """Stan nadrabiania widziany przez ekran „Dziś"."""

    backlog: int
    """Ile zaległych powtórek zostało."""
    started_from: int
    """Ile ich było, gdy plan ruszał."""
    today: int
    """Porcja na dzisiejszą sesję."""
    days_left: int
    """Ile dni zostało do terminu, licząc dzisiejszy."""
    until: date
    """Dzień, na który ma być czysto."""
    finished: bool = False
    """Plan właśnie się domknął — nawis zszedł poniżej progu."""

    @property
    def done(self) -> int:
        return max(self.started_from - self.backlog, 0)

    @property
    def last_day(self) -> bool:
        """Po dzisiejszej porcji nawis schodzi poniżej progu i plan znika.

        Mierzone progiem, nie zerem: plan kończy się tam, gdzie kolejka
        przestaje być ścianą, a nie tam, gdzie jest pusta. Inaczej ostatni
        dzień nie nadchodziłby nigdy — kafelek znikałby wcześniej, niż
        zdążyłby powiedzieć, że to już koniec.
        """
        return self.backlog - self.today <= BACKLOG_THRESHOLD

    def as_dict(self) -> dict:
        return {
            "backlog": self.backlog,
            "started_from": self.started_from,
            "done": self.done,
            "today": self.today,
            "days_left": self.days_left,
            "until": self.until.isoformat(),
            "last_day": self.last_day,
            "finished": self.finished,
        }


def _comfortable(daily_goal: int, review_limit: int) -> int:
    """Porcja, przy której nadrabianie jest do przejścia, a nie do porzucenia."""
    return max(MIN_PORTION, min(round(daily_goal * COMFORT), review_limit))


def _fresh_deadline(due: int, daily_goal: int, review_limit: int, today: date) -> tuple[date, int]:
    """Termin dla planu ruszającego od zera: tyle dni, ile trzeba w spokojnym tempie."""
    days = max(MIN_DAYS, math.ceil(due / _comfortable(daily_goal, review_limit)))
    return today + timedelta(days=days), days


def refresh(db: Session, user: User, due: int, *, today: date | None = None, record: bool = True) -> Plan | None:
    """Plan na dziś — zakładany, przeliczany albo zamykany, zależnie od nawisu.

    `record=False` liczy to samo, ale niczego nie zapisuje. Tak woła to
    budowniczy sesji: porcję musi znać, ale stan planu prowadzi ekran „Dziś",
    żeby wejście prosto w naukę nie zamykało planu w tle i nie zabierało
    użytkownikowi wiadomości, że właśnie nadrobił.
    """
    today = today or date.today()
    settings = user.settings
    until = settings.catch_up_until
    started_from = settings.catch_up_from
    active = until is not None and started_from is not None and until >= today

    if due <= BACKLOG_THRESHOLD:
        if not active:
            return None
        # Nawis zszedł poniżej progu — plan zrobił swoje i znika. Ostatni raz
        # pokazuje się jako domknięty, żeby tydzień pracy nie kończył się
        # zniknięciem kafelka bez słowa.
        if record:
            settings.catch_up_until = None
            settings.catch_up_from = None
            db.flush()
        return Plan(
            backlog=due,
            started_from=started_from,
            today=due,
            days_left=0,
            until=until,
            finished=True,
        )

    goal = settings.daily_goal
    limit = settings.review_limit

    if active:
        days_left = max((until - today).days, 1)
        # Plan, którego nie da się dowieźć w spokojnym tempie, przestał być
        # planem. Zamiast pokazywać porcję, od której użytkownik odbije się jak
        # od ściany, zakłada się nowy termin — dłuższa przerwa w środku
        # nadrabiania nie ma karać rachunkiem za cały opuszczony tydzień.
        needed = math.ceil(due / days_left)
        if needed > limit or needed > _comfortable(goal, limit) * OVERRUN:
            until, days_left = _fresh_deadline(due, goal, limit, today)
            started_from = due
        else:
            # Nawis potrafi w międzyczasie urosnąć: wczorajsze karty wracają.
            # Punkt startu idzie wtedy w górę, żeby „nadrobione" nie zeszło
            # poniżej zera i nie pokazywało cofania się.
            started_from = max(started_from, due)
    else:
        until, days_left = _fresh_deadline(due, goal, limit, today)
        started_from = due

    if record:
        settings.catch_up_until = until
        settings.catch_up_from = started_from
        db.flush()

    portion = min(math.ceil(due / days_left), limit)
    return Plan(
        backlog=due,
        started_from=started_from,
        today=portion,
        days_left=days_left,
        until=until,
    )
