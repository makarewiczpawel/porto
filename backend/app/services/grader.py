"""Grading typed answers.

Three outcomes, not two. A missing accent or a single slipped key is not the
same failure as writing the wrong word: it comes back sooner than a clean hit,
but it does not reset progress the way a real mistake does.
"""

import re
import unicodedata
from dataclasses import dataclass
from enum import Enum

from rapidfuzz.distance import Levenshtein

# Words shorter than this are graded strictly — in a three-letter word a single
# wrong letter usually means a different word, not a typo.
MIN_LENGTH_FOR_TYPO = 4
MAX_TYPO_DISTANCE = 1

_PUNCTUATION = re.compile(r"[.,;:!?¿¡\"'`´“”„«»…()\[\]]")
_WHITESPACE = re.compile(r"\s+")
_COMBINING = re.compile("[" + chr(0x300) + "-" + chr(0x36F) + "]")


class Match(str, Enum):
    EXACT = "exact"
    ACCENT = "accent"  # right letters, missing or wrong diacritics
    TYPO = "typo"  # one slipped key
    WRONG = "wrong"


@dataclass
class Grade:
    is_correct: bool
    match: Match
    correct_answer: str
    #: True when the answer counts, but should come back sooner than usual.
    partial: bool

    @property
    def as_dict(self) -> dict:
        return {
            "is_correct": self.is_correct,
            "match": self.match.value,
            "correct_answer": self.correct_answer,
            "partial": self.partial,
        }


def normalize(value: str) -> str:
    """Lowercase, drop punctuation, collapse whitespace.

    Portuguese articles are part of what is being learned, so they are NOT
    stripped here — `casa` and `a casa` stay different answers unless the item
    lists both.
    """
    text = value.strip().lower()
    text = _PUNCTUATION.sub("", text)
    text = _WHITESPACE.sub(" ", text)
    return text.strip()


def strip_accents(value: str) -> str:
    decomposed = unicodedata.normalize("NFD", value)
    return _COMBINING.sub("", decomposed)


def grade(
    answer: str,
    expected: str,
    *,
    alternatives: list[str] | None = None,
    accent_strict: bool = False,
) -> Grade:
    """Compare a typed answer against the expected one.

    `alternatives` are other spellings or translations that count as correct.
    `accent_strict` decides whether `avo` for `avó` is a mistake or "almost".
    """
    candidates = [expected, *(alternatives or [])]
    given = normalize(answer)

    if not given:
        return Grade(False, Match.WRONG, expected, partial=False)

    # 1. Exact, ignoring case and punctuation.
    for candidate in candidates:
        if given == normalize(candidate):
            return Grade(True, Match.EXACT, expected, partial=False)

    # 2. Right letters, wrong or missing diacritics.
    given_bare = strip_accents(given)
    for candidate in candidates:
        if given_bare == strip_accents(normalize(candidate)):
            if accent_strict:
                return Grade(False, Match.ACCENT, expected, partial=False)
            return Grade(True, Match.ACCENT, expected, partial=True)

    # 3. One slipped key. Compared without accents so a typo *and* a missing
    #    accent together still reads as a typo rather than a different word.
    for candidate in candidates:
        target_bare = strip_accents(normalize(candidate))
        if len(target_bare) < MIN_LENGTH_FOR_TYPO:
            continue
        if Levenshtein.distance(given_bare, target_bare) <= MAX_TYPO_DISTANCE:
            return Grade(True, Match.TYPO, expected, partial=True)

    return Grade(False, Match.WRONG, expected, partial=False)


def diff_hint(answer: str, expected: str) -> str:
    """The expected answer with differing characters wrapped in `»…«`.

    Shows *what* was off instead of only reprinting the correct form — the
    point is to make a missing accent visible: `av»ó«`.

    The comparison is positional, so it is exact for same-length differences
    (accents, one substituted letter) and only approximate once a character is
    inserted or dropped. That is the case it is used for.
    """
    given = normalize(answer)
    target = normalize(expected)
    if given == target:
        return expected

    out: list[str] = []
    for index, char in enumerate(target):
        typed = given[index] if index < len(given) else ""
        out.append(char if typed == char else f"»{char}«")
    return "".join(out)
