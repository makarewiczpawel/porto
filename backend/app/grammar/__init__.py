"""Lekcje gramatyki — treść statyczna, wersjonowana razem z kodem.

Lekcje nie mieszkają w bazie. Nikt ich nie edytuje w aplikacji, nie mają
stanu per użytkownik, a każda poprawka i tak przechodzi przez przegląd w
repozytorium — tabela w bazie dołożyłaby tylko migrację i krok seedowania, w
którym coś może się rozjechać z plikiem.

Każda lekcja to jeden plik JSON w `lekcje/`, z numerem na początku nazwy, który
wyznacza kolejność. Treść pisana jest po polsku z dwoma znacznikami w tekście:

- `{...}` — wstawka po portugalsku, składana krojem portugalskim,
- `**...**` — wyróżnienie.

Wczytywane raz przy imporcie i walidowane schematem: literówka w pliku ma
wywrócić start aplikacji i testy, a nie wyrenderować pół lekcji.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_validator

LESSONS_DIR = Path(__file__).parent / "lekcje"


class Example(BaseModel):
    pt: str = Field(min_length=1)
    pl: str = Field(min_length=1)


class Paragraph(BaseModel):
    type: Literal["p"]
    text: str = Field(min_length=1)


class Heading(BaseModel):
    type: Literal["h"]
    text: str = Field(min_length=1)


class Table(BaseModel):
    type: Literal["table"]
    caption: str | None = None
    head: list[str]
    rows: list[list[str]]
    # Kolumny w całości po portugalsku — składane krojem portugalskim bez
    # stawiania klamer w każdej komórce tabeli odmiany.
    pt_cols: list[int] = []
    # Kolumny z formami brazylijskimi, pokazane świadomie jako kontrast.
    # Ekran wycisza je i podpisuje, a test na brazylizmy je pomija — tylko tu
    # wolno im się pojawić.
    br_cols: list[int] = []

    @model_validator(mode="after")
    def _shape(self) -> Table:
        width = len(self.head)
        for row in self.rows:
            if len(row) != width:
                raise ValueError(f"wiersz {row!r} ma {len(row)} komórek, nagłówek {width}")
        for col in [*self.pt_cols, *self.br_cols]:
            if not 0 <= col < width:
                raise ValueError(f"kolumna {col} poza tabelą o szerokości {width}")
        return self


class Examples(BaseModel):
    type: Literal["examples"]
    items: list[Example] = Field(min_length=1)


class Tip(BaseModel):
    type: Literal["tip"]
    # trap — pułapka; pt — „tak mówi się w Portugalii"; info — dopowiedzenie.
    tone: Literal["trap", "pt", "info"] = "info"
    title: str = Field(min_length=1)
    text: str = Field(min_length=1)


Block = Annotated[Paragraph | Heading | Table | Examples | Tip, Field(discriminator="type")]


class Question(BaseModel):
    q: str = Field(min_length=1)
    options: list[str] = Field(min_length=2, max_length=4)
    answer: int
    why: str = Field(min_length=1)

    @model_validator(mode="after")
    def _answer_exists(self) -> Question:
        if not 0 <= self.answer < len(self.options):
            raise ValueError(f"odpowiedź {self.answer} poza listą opcji w pytaniu {self.q!r}")
        if len(set(self.options)) != len(self.options):
            raise ValueError(f"powtórzona opcja w pytaniu {self.q!r}")
        return self


class Lesson(BaseModel):
    slug: str = Field(pattern=r"^[a-z0-9-]+$")
    title: str
    summary: str
    level: Literal["A1", "A2", "B1"]
    part: str
    blocks: list[Block] = Field(min_length=1)
    check: list[Question] = Field(min_length=3)
    position: int = 0

    def examples(self) -> list[Example]:
        return [ex for block in self.blocks if isinstance(block, Examples) for ex in block.items]


@lru_cache(maxsize=1)
def lessons() -> tuple[Lesson, ...]:
    """Wszystkie lekcje w kolejności z nazw plików."""
    found: list[Lesson] = []
    for position, path in enumerate(sorted(LESSONS_DIR.glob("*.json")), start=1):
        data = json.loads(path.read_text(encoding="utf-8"))
        try:
            lesson = Lesson.model_validate({**data, "position": position})
        except ValueError as exc:
            raise ValueError(f"{path.name}: {exc}") from exc
        found.append(lesson)
    slugs = [lesson.slug for lesson in found]
    if len(set(slugs)) != len(slugs):
        raise ValueError(f"powtórzony slug lekcji: {slugs}")
    return tuple(found)


def by_slug(slug: str) -> Lesson | None:
    return next((lesson for lesson in lessons() if lesson.slug == slug), None)


def spoken_texts() -> list[str]:
    """Zdania przykładowe ze wszystkich lekcji — to, co w gramatyce brzmi.

    Czyta z tego biblioteka nagrań, żeby „Nagraj brakujące" obejmowało też
    lekcje. Bez tego przykłady odzywałyby się głosem telefonu, a nie tym
    wybranym w ustawieniach — dokładnie ten błąd był już raz z odpowiedziami
    rozmówcy i zostawił po sobie zasadę: odtwarzanie i lista do nagrania
    czytają z jednego miejsca.
    """
    return [example.pt for lesson in lessons() for example in lesson.examples()]
