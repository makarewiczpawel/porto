"""Lekcje — gramatyka i dialogi. Treść statyczna, wersjonowana razem z kodem.

Lekcje nie mieszkają w bazie. Nikt ich nie edytuje w aplikacji, nie mają
stanu per użytkownik, a każda poprawka i tak przechodzi przez przegląd w
repozytorium — tabela w bazie dołożyłaby tylko migrację i krok seedowania, w
którym coś może się rozjechać z plikiem.

Każda lekcja to jeden plik JSON w katalogu swojego rodzaju — `gramatyka/` albo
`dialogi/` — z numerem na początku nazwy, który wyznacza kolejność w obrębie
rodzaju. Treść pisana jest po polsku z dwoma znacznikami w tekście:

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

LESSONS_DIR = Path(__file__).parent
# Rodzaje lekcji w kolejności, w jakiej pokazuje je spis. Dialogi pierwsze:
# to od nich zaczyna się mówienie, a gramatyka tłumaczy, co się w nich dzieje.
KINDS = ("dialogi", "gramatyka")
Kind = Literal["dialogi", "gramatyka"]


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


class Line(BaseModel):
    # Kto mówi, po polsku. „Ty" to kwestie ucznia — ekran pozwala je zasłonić
    # i ćwiczyć swoją rolę.
    who: str = Field(min_length=1)
    pt: str = Field(min_length=1)
    pl: str = Field(min_length=1)


class Dialogue(BaseModel):
    type: Literal["dialogue"]
    lines: list[Line] = Field(min_length=2)

    @model_validator(mode="after")
    def _two_voices(self) -> Dialogue:
        if len({line.who for line in self.lines}) < 2:
            raise ValueError("dialog z jedną osobą to monolog")
        return self


Block = Annotated[
    Paragraph | Heading | Table | Examples | Tip | Dialogue, Field(discriminator="type")
]


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
    kind: Kind
    title: str
    summary: str
    level: Literal["A1", "A2", "B1"]
    part: str
    blocks: list[Block] = Field(min_length=1)
    check: list[Question] = Field(min_length=3)
    position: int = 0

    def spoken(self) -> list[str]:
        """Wszystko, co w tej lekcji da się odsłuchać: przykłady i kwestie dialogu."""
        out: list[str] = []
        for block in self.blocks:
            if isinstance(block, Examples):
                out += [example.pt for example in block.items]
            elif isinstance(block, Dialogue):
                out += [line.pt for line in block.lines]
        return out


@lru_cache(maxsize=1)
def lessons() -> tuple[Lesson, ...]:
    """Wszystkie lekcje: rodzaje w kolejności `KINDS`, w obrębie rodzaju — z nazw plików."""
    found: list[Lesson] = []
    for kind in KINDS:
        for position, path in enumerate(sorted((LESSONS_DIR / kind).glob("*.json")), start=1):
            data = json.loads(path.read_text(encoding="utf-8"))
            try:
                lesson = Lesson.model_validate({**data, "kind": kind, "position": position})
            except ValueError as exc:
                raise ValueError(f"{kind}/{path.name}: {exc}") from exc
            found.append(lesson)
    slugs = [lesson.slug for lesson in found]
    if len(set(slugs)) != len(slugs):
        raise ValueError(f"powtórzony slug lekcji: {slugs}")
    return tuple(found)


def of_kind(kind: str) -> tuple[Lesson, ...]:
    return tuple(lesson for lesson in lessons() if lesson.kind == kind)


def by_slug(slug: str) -> Lesson | None:
    return next((lesson for lesson in lessons() if lesson.slug == slug), None)


def spoken_texts() -> list[str]:
    """Wszystko, co w lekcjach brzmi — przykłady i kwestie dialogów.

    Czyta z tego biblioteka nagrań, żeby „Nagraj brakujące" obejmowało też
    lekcje. Bez tego zdania odzywałyby się głosem telefonu, a nie tym
    wybranym w ustawieniach — dokładnie ten błąd był już raz z odpowiedziami
    rozmówcy i zostawił po sobie zasadę: odtwarzanie i lista do nagrania
    czytają z jednego miejsca.
    """
    return [text for lesson in lessons() for text in lesson.spoken()]
