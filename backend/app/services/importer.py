"""Wczytywanie własnych słówek z CSV.

Format jest celowo wybaczający, bo po drugiej stronie jest arkusz kalkulacyjny,
a nie inny program: separator wykrywany automatycznie (przecinek, średnik albo
tabulator — Excel po polsku zapisuje średnikami), nagłówek opcjonalny, kolumny
rozpoznawane po nazwie, gdy jest.

Minimum to dwie kolumny: portugalski i polski. Reszta — typ, poziom, część
mowy, rodzajnik, notatka, zdanie przykładowe — jest opcjonalna.

Wiersz z błędem nie przerywa importu. Zwracany raport mówi, który to był wiersz
i co w nim nie grało, bo „import się nie udał" bez numeru wiersza jest
bezużyteczne przy pliku na dwieście pozycji.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field

MAX_ROWS = 2000
LEVELS = {"A1", "A2", "B1", "B2", "C1"}
TYPES = {"word", "phrase", "sentence"}
GENDERS = {"m", "f", "mf"}
ARTICLES = ("a", "o", "as", "os", "um", "uma")

# Nazwy kolumn, jakich ludzie faktycznie używają.
ALIASES = {
    "pt": {"pt", "portugalski", "portuguese", "słowo", "slowo", "wyrażenie", "wyrazenie"},
    "pl": {"pl", "polski", "polish", "tłumaczenie", "tlumaczenie", "znaczenie"},
    "type": {"type", "typ"},
    "level": {"level", "poziom", "cefr", "cefr_level"},
    "pos": {"pos", "część mowy", "czesc mowy", "part_of_speech", "odmiana"},
    "article": {"article", "rodzajnik"},
    "gender": {"gender", "rodzaj"},
    "notes": {"notes", "notatka", "uwagi", "uwaga"},
    "example_pt": {"example_pt", "przyklad_pt", "przykład_pt", "zdanie_pt"},
    "example_pl": {"example_pl", "przyklad_pl", "przykład_pl", "zdanie_pl"},
}


@dataclass
class Row:
    line: int
    pt: str
    pl: str
    type: str = "word"
    cefr_level: str = "A1"
    part_of_speech: str | None = None
    article: str | None = None
    gender: str | None = None
    notes: str | None = None
    example_pt: str | None = None
    example_pl: str | None = None

    def as_dict(self) -> dict:
        return {
            "line": self.line,
            "pt": self.pt,
            "pl": self.pl,
            "type": self.type,
            "cefr_level": self.cefr_level,
            "part_of_speech": self.part_of_speech,
            "article": self.article,
            "gender": self.gender,
            "notes": self.notes,
            "example_pt": self.example_pt,
            "example_pl": self.example_pl,
        }


@dataclass
class Problem:
    line: int
    reason: str
    raw: str


@dataclass
class Parsed:
    rows: list[Row] = field(default_factory=list)
    problems: list[Problem] = field(default_factory=list)


def _sniff_delimiter(text: str) -> str:
    head = text[:4000]
    counts = {sep: head.count(sep) for sep in (";", "\t", ",")}
    best = max(counts, key=lambda sep: counts[sep])
    return best if counts[best] > 0 else ","


def _header_map(cells: list[str]) -> dict[str, int] | None:
    """Mapa kolumna → indeks, jeśli pierwszy wiersz wygląda na nagłówek."""
    lowered = [cell.strip().lower().strip('"') for cell in cells]
    mapping: dict[str, int] = {}
    for key, names in ALIASES.items():
        for index, cell in enumerate(lowered):
            if cell in names:
                mapping[key] = index
                break
    # Nagłówek uznajemy tylko wtedy, gdy nazwał obie wymagane kolumny —
    # inaczej pierwszy wiersz danych zniknąłby, wzięty za tytuły.
    if "pt" in mapping and "pl" in mapping:
        return mapping
    return None


def _guess_type(pt: str) -> str:
    """Zdanie, zwrot czy pojedyncze słowo — po kształcie tekstu.

    Rodzajnik nie jest osobnym wyrazem w tym rachunku: „uma toalha" to jedno
    słowo do nauczenia, nie zwrot.
    """
    words = pt.split()
    if words and words[0].lower() in ARTICLES:
        words = words[1:]
    if len(words) >= 3 and pt[-1] in ".?!":
        return "sentence"
    return "phrase" if len(words) > 1 else "word"


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    return text or None


def parse(text: str) -> Parsed:
    result = Parsed()
    if not text.strip():
        return result

    delimiter = _sniff_delimiter(text)
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    # Numer wiersza pochodzi z pliku, nie z pozycji po odsianiu pustych linii —
    # inaczej pusta linia w środku przesuwałaby wszystkie numery w raporcie i
    # użytkownik szukałby błędu nie tam, gdzie jest.
    numbered = [
        (number, row)
        for number, row in enumerate(reader, start=1)
        if any(cell.strip() for cell in row)
    ]
    if not numbered:
        return result

    mapping = _header_map(numbered[0][1])
    headerless = mapping is None
    if not headerless:
        numbered = numbered[1:]
    else:
        # Bez nagłówka pewne są tylko dwie pierwsze kolumny. Resztę
        # rozpoznajemy po zawartości, a nie po pozycji: „a praia; plaża; A1"
        # i „a praia; plaża; phrase; A1" znaczą to samo, bo tak ludzie piszą
        # listy — kolejność dalszych kolumn jest przypadkowa.
        mapping = {"pt": 0, "pl": 1}

    def cell(row: list[str], key: str) -> str | None:
        index = mapping.get(key)
        if index is None or index >= len(row):
            return None
        return _clean(row[index])

    for line, row in numbered:
        raw = delimiter.join(row)[:200]
        if len(result.rows) >= MAX_ROWS:
            result.problems.append(
                Problem(line=line, reason=f"Import obejmuje najwyżej {MAX_ROWS} wierszy.", raw=raw)
            )
            break

        pt, pl = cell(row, "pt"), cell(row, "pl")
        if not pt or not pl:
            result.problems.append(
                Problem(line=line, reason="Brakuje portugalskiego albo polskiego.", raw=raw)
            )
            continue
        if len(pt) > 200 or len(pl) > 200:
            result.problems.append(Problem(line=line, reason="Tekst dłuższy niż 200 znaków.", raw=raw))
            continue

        extras = [_clean(value) for value in row[2:]] if headerless else []
        extras = [value for value in extras if value]

        if headerless:
            level = next((v.upper() for v in extras if v.upper() in LEVELS), "A1")
            declared_type = next((v.lower() for v in extras if v.lower() in TYPES), "")
            leftovers = [
                v for v in extras if v.upper() not in LEVELS and v.lower() not in TYPES
            ]
            note = leftovers[0] if leftovers else None
        else:
            level = (cell(row, "level") or "A1").upper()
            declared_type = (cell(row, "type") or "").lower()
            note = cell(row, "notes")

        if level not in LEVELS:
            result.problems.append(
                Problem(line=line, reason=f"Nieznany poziom {level}; dozwolone: A1–C1.", raw=raw)
            )
            continue

        kind = declared_type
        if kind not in TYPES:
            kind = _guess_type(pt)

        gender = (cell(row, "gender") or "").lower() or None
        if gender is not None and gender not in GENDERS:
            gender = None

        result.rows.append(
            Row(
                line=line,
                pt=pt,
                pl=pl,
                type=kind,
                cefr_level=level,
                part_of_speech=cell(row, "pos"),
                article=cell(row, "article"),
                gender=gender,
                notes=note,
                example_pt=cell(row, "example_pt"),
                example_pl=cell(row, "example_pl"),
            )
        )

    return result
