import pytest

from app.services.grader import Match, diff_hint, grade, normalize, strip_accents


def test_normalize_ignores_case_punctuation_and_spacing():
    assert normalize("  A Casa!! ") == "a casa"
    assert normalize("Não  percebo.") == "não percebo"
    assert normalize("«Bom dia»") == "bom dia"


def test_strip_accents_keeps_letters():
    assert strip_accents("avó") == "avo"
    assert strip_accents("pequeno-almoço") == "pequeno-almoco"
    assert strip_accents("amanhã") == "amanha"


# ── exact ─────────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "given",
    ["a casa de banho", "A Casa de Banho", "  a casa de banho  ", "a casa de banho."],
)
def test_exact_answers_ignore_case_and_punctuation(given):
    result = grade(given, "a casa de banho")
    assert result.is_correct
    assert result.match is Match.EXACT
    assert result.partial is False


def test_alternatives_count_as_exact():
    result = grade("por favor", "se faz favor", alternatives=["por favor"])
    assert result.is_correct
    assert result.match is Match.EXACT


# ── accents ───────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    ("given", "expected"),
    [
        ("a avo", "a avó"),
        ("amanha", "amanhã"),
        ("o pequeno-almoco", "o pequeno-almoço"),
        ("nao", "não"),
        ("tres", "três"),
    ],
)
def test_missing_accent_is_almost_not_wrong(given, expected):
    result = grade(given, expected)
    assert result.is_correct, "a missing accent must not reset the card"
    assert result.match is Match.ACCENT
    assert result.partial is True, "but it should come back sooner"


def test_accent_strict_turns_missing_accents_into_mistakes():
    result = grade("a avo", "a avó", accent_strict=True)
    assert result.is_correct is False
    assert result.match is Match.ACCENT


def test_wrong_accent_also_counts_as_accent_slip():
    assert grade("a avô", "a avó").match is Match.ACCENT


# ── typos ─────────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    ("given", "expected"),
    [
        ("obrigadoo", "obrigado"),  # doubled letter
        ("obrigdo", "obrigado"),  # dropped letter
        ("obrugado", "obrigado"),  # wrong letter
        ("a casa de banha", "a casa de banho"),
    ],
)
def test_one_slipped_key_is_almost(given, expected):
    result = grade(given, expected)
    assert result.is_correct
    assert result.match is Match.TYPO
    assert result.partial is True


def test_two_errors_are_a_mistake():
    assert grade("obrugadu", "obrigado").match is Match.WRONG


def test_short_words_are_graded_strictly():
    """In a three-letter word one wrong letter is usually a different word."""
    assert grade("mas", "mar").match is Match.WRONG
    assert grade("sim", "sem").match is Match.WRONG


def test_a_different_word_of_similar_length_is_wrong():
    assert grade("o prato", "o talher").match is Match.WRONG
    assert grade("comboio", "autocarro").match is Match.WRONG


def test_typo_on_top_of_a_missing_accent_still_reads_as_a_typo():
    """Dropped an `o` *and* skipped the cedilla — one slip, not two words."""
    assert grade("pequeno-almco", "pequeno-almoço").match is Match.TYPO


# ── empty and junk ────────────────────────────────────────────────────────
@pytest.mark.parametrize("given", ["", "   ", "..."])
def test_empty_answers_are_wrong(given):
    result = grade(given, "a casa")
    assert result.is_correct is False
    assert result.match is Match.WRONG
    assert result.correct_answer == "a casa"


# ── diff ──────────────────────────────────────────────────────────────────
def test_diff_marks_the_missing_accent():
    assert diff_hint("avo", "avó") == "av»ó«"


def test_diff_returns_the_answer_unchanged_when_it_matches():
    assert diff_hint("A Casa!", "a casa") == "a casa"


def test_diff_marks_the_tail_when_the_answer_is_too_short():
    assert diff_hint("cas", "casa") == "cas»a«"
