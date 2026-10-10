"""Lekcje — gramatyka i dialogi: treść, która się nie rozjeżdża, i zdania, które brzmią.

Lekcje to statyczna treść pisana ręcznie, więc testy pilnują tego, czego
oko przy przeglądzie nie wyłapie: niedomkniętej klamry, która wyrenderuje się
jako surowy znak, brazylizmu wśród przykładów i kwestii dialogów, i zdania,
które aplikacja chce odtworzyć, a którego nikt nie nagra.
"""

import re

import pytest

from app import lessons
from app.models import AudioAsset
from app.services import ai, tts, voice_library

LESSONS = lessons.lessons()


def _texts(lesson: lessons.Lesson):
    """Każdy napis lekcji, z informacją, czy wolno w nim brazylizmów."""
    yield lesson.title, False
    yield lesson.summary, False
    for block in lesson.blocks:
        if block.type in ("p", "h"):
            yield block.text, False
        elif block.type == "tip":
            yield block.title, False
            yield block.text, False
        elif block.type == "table":
            yield from ((cell, False) for cell in block.head)
            for row in block.rows:
                for col, cell in enumerate(row):
                    yield cell, col in block.br_cols
        elif block.type == "examples":
            for example in block.items:
                yield example.pt, False
                yield example.pl, False
        elif block.type == "dialogue":
            for line in block.lines:
                yield line.who, False
                yield line.pt, False
                yield line.pl, False
    for question in lesson.check:
        yield question.q, False
        yield from ((option, False) for option in question.options)
        yield question.why, False


def _portuguese(lesson: lessons.Lesson):
    """Portugalski, który lekcja przedstawia jako poprawny.

    Poza zasięgiem są wskazówki, objaśnienia i złe odpowiedzi w quizie — tam
    brazylijska forma pada celowo, jako przykład tego, czego nie mówić. Wszystko
    inne, a zwłaszcza przykłady, które aplikacja odtwarza na głos, ma być
    europejskie.
    """
    for block in lesson.blocks:
        if block.type == "examples":
            yield from (example.pt for example in block.items)
        elif block.type == "dialogue":
            yield from (line.pt for line in block.lines)
        elif block.type in ("p", "h"):
            yield from re.findall(r"\{([^}]*)\}", block.text)
        elif block.type == "table":
            for row in block.rows:
                for col, cell in enumerate(row):
                    if col in block.br_cols:
                        continue
                    if col in block.pt_cols:
                        yield cell
                    yield from re.findall(r"\{([^}]*)\}", cell)
    for question in lesson.check:
        yield from re.findall(r"\{([^}]*)\}", question.options[question.answer])


def test_there_is_a_real_course_not_a_stub():
    grammar = lessons.of_kind("gramatyka")
    dialogues = lessons.of_kind("dialogi")
    assert len(grammar) >= 12
    assert len(dialogues) >= 8
    assert {"Zaimki", "Czasowniki"} <= {lesson.part for lesson in grammar}


def test_every_dialogue_gives_the_learner_a_part_to_play():
    """Kwestie „Ty” to rola ucznia — ekran pozwala je zasłonić i ćwiczyć.
    Dialog bez nich byłby tylko czytanką."""
    for lesson in lessons.of_kind("dialogi"):
        lines = [line for block in lesson.blocks if block.type == "dialogue" for line in block.lines]
        assert lines, lesson.slug
        assert any(line.who == "Ty" for line in lines), lesson.slug
        # Dwie kwestie ucznia pod rząd brzmią sztucznie — rozmowa to wymiana.
        whos = [line.who for line in lines]
        assert all(a != b or a != "Ty" for a, b in zip(whos, whos[1:], strict=False)), lesson.slug


@pytest.mark.parametrize("lesson", LESSONS, ids=lambda lesson: lesson.slug)
def test_markup_is_balanced(lesson):
    """Niedomknięta klamra albo gwiazdki wyrenderują się jako surowe znaki
    na środku zdania — i w całym tekście nikt tego nie zauważy przy przeglądzie."""
    for text, _ in _texts(lesson):
        depth = 0
        for char in text:
            depth += {"{": 1, "}": -1}.get(char, 0)
            assert 0 <= depth <= 1, f"zagnieżdżona albo osierocona klamra: {text!r}"
        assert depth == 0, f"niedomknięta klamra: {text!r}"
        assert text.count("**") % 2 == 0, f"niedomknięte wyróżnienie: {text!r}"
        assert '"' not in text, f"prosty cudzysłów zamiast polskiego: {text!r}"


@pytest.mark.parametrize("lesson", LESSONS, ids=lambda lesson: lesson.slug)
def test_no_brazilian_words_outside_the_marked_contrast(lesson):
    """Brazylijskie formy wolno pokazać tylko w kolumnie oznaczonej jako
    kontrast. Gdziekolwiek indziej uczą czegoś, czego w Portugalii nie usłyszysz."""
    banned = [bad.split(" (")[0] for bad, _ in ai.BRAZILIANISMS]
    gerund_progressive = re.compile(r"\best(?:ou|ás|á|amos|ão)\s+\w+ndo\b")
    offenders = []
    for text in _portuguese(lesson):
        low = text.lower()
        offenders += [(text, word) for word in banned if re.search(rf"\b{re.escape(word)}\b", low)]
        if gerund_progressive.search(low):
            offenders.append((text, "estar + gerúndio"))
    assert offenders == []


def test_the_contrast_column_is_actually_brazilian():
    """Kolumna kontrastu, w której nie ma niczego brazylijskiego, to po prostu
    wyciszona i źle podpisana treść — znak, że znacznik trafił w złą kolumnę."""
    for lesson in LESSONS:
        for block in lesson.blocks:
            if block.type == "table" and block.br_cols:
                cells = " ".join(row[c] for row in block.rows for c in block.br_cols).lower()
                assert "ndo" in cells or "você" in cells, lesson.slug


@pytest.mark.parametrize("lesson", LESSONS, ids=lambda lesson: lesson.slug)
def test_every_lesson_teaches_by_example_and_checks_itself(lesson):
    assert len(lesson.spoken()) >= 3, "lekcja bez przykładów to wykład"
    assert len(lesson.check) >= 4
    answers = [question.answer for question in lesson.check]
    # Wszystkie poprawne odpowiedzi pod pierwszą opcją to test, który
    # zdaje się bez czytania lekcji. Ekran i tak tasuje, ale treść ma się bronić sama.
    assert len(set(answers)) > 1, f"wszystkie odpowiedzi pod tą samą opcją: {answers}"


def test_slugs_are_unique_and_positions_follow_the_files():
    assert len({lesson.slug for lesson in LESSONS}) == len(LESSONS)
    for kind in lessons.KINDS:
        of_kind = lessons.of_kind(kind)
        assert [lesson.position for lesson in of_kind] == list(range(1, len(of_kind) + 1))


def test_a_broken_lesson_file_stops_the_app_instead_of_rendering_half(tmp_path, monkeypatch):
    (tmp_path / "gramatyka").mkdir()
    (tmp_path / "dialogi").mkdir()
    (tmp_path / "gramatyka" / "01_zla.json").write_text(
        '{"slug": "zla", "title": "x", "summary": "x", "level": "A1", "part": "x",'
        ' "blocks": [{"type": "p", "text": "x"}],'
        ' "check": [{"q": "?", "options": ["a", "b"], "answer": 5, "why": "x"}]}',
        encoding="utf-8",
    )
    monkeypatch.setattr(lessons, "LESSONS_DIR", tmp_path)
    lessons.lessons.cache_clear()
    try:
        with pytest.raises(ValueError, match="gramatyka/01_zla.json"):
            lessons.lessons()
    finally:
        lessons.lessons.cache_clear()


# ── nagrania ──────────────────────────────────────────────────────────────
def test_lesson_examples_are_on_the_recording_list(db):
    """Odtwarzanie i lista „do nagrania” czytają z jednego miejsca.

    Gdy kiedyś się rozeszły, odpowiedzi rozmówcy odzywały się głosem telefonu
    i żadne „Nagraj brakujące” nie mogło tego naprawić."""
    planned = {text for text, _speed in voice_library.planned(db)}
    missing = [text for text in lessons.spoken_texts() if tts.normalize_text(text) not in planned]
    assert missing == []


# ── API ───────────────────────────────────────────────────────────────────
def test_the_list_needs_a_login(client):
    assert client.get("/api/lessons").status_code == 401


def test_the_list_comes_in_course_order(client, registered):
    body = client.get("/api/lessons").json()
    assert [entry["slug"] for entry in body["lessons"]] == [lesson.slug for lesson in LESSONS]
    assert body["lessons"][0]["kind"] == "dialogi"
    assert body["lessons"][0]["spoken"] > 0


def test_unknown_lesson_is_404(client, registered):
    response = client.get("/api/lessons/nie-ma-takiej")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "LESSON_NOT_FOUND"


def test_a_lesson_knows_its_neighbours_within_its_kind(client, registered):
    dialogues = lessons.of_kind("dialogi")
    grammar = lessons.of_kind("gramatyka")
    first = client.get(f"/api/lessons/{dialogues[0].slug}").json()
    assert first["previous"] is None
    assert first["next"]["slug"] == dialogues[1].slug
    # Po ostatnim dialogu „następna” nie przeskakuje do gramatyki.
    last = client.get(f"/api/lessons/{dialogues[-1].slug}").json()
    assert last["next"] is None
    assert client.get(f"/api/lessons/{grammar[0].slug}").json()["previous"] is None


def _record(db, text: str, voice: str):
    db.add(
        AudioAsset(
            cache_key=tts.cache_key(text, voice, 1.0),
            text=text,
            voice=voice,
            speed=1.0,
            mime="audio/mpeg",
            data=b"mp3",
            size=3,
            provider="test",
            char_count=len(text),
        )
    )
    db.commit()


@pytest.mark.parametrize("kind,block_type,key", [("gramatyka", "examples", "items"), ("dialogi", "dialogue", "lines")])
def test_spoken_lines_point_at_recordings_in_the_users_voice(client, registered, db, kind, block_type, key):
    lesson = lessons.of_kind(kind)[0]
    voice = client.get("/api/auth/me").json()["settings"]["tts_voice"]
    recorded, other = lesson.spoken()[0], lesson.spoken()[1]
    _record(db, recorded, voice)
    _record(db, other, "pt-PT-Inny-Glos")

    body = client.get(f"/api/lessons/{lesson.slug}").json()
    audio = {
        entry["pt"]: entry["audio"]
        for block in body["blocks"]
        if block["type"] == block_type
        for entry in block[key]
    }
    assert audio[recorded] == tts.audio_url(tts.cache_key(recorded, voice, 1.0))
    assert audio[other] is None, "nagranie innym głosem to nie nagranie"


def test_missing_recordings_are_ordered_and_announced(client, registered, monkeypatch):
    """Brak nagrania nie jest błędem i nic go nie zgłasza — dlatego odpowiedź
    mówi wprost, że nagrania się robią, a ekran wie, że ma dopytać."""
    monkeypatch.setattr(tts, "is_configured", lambda: True)
    ordered = []
    monkeypatch.setattr(
        voice_library,
        "synthesize_texts",
        lambda batch, texts, voice, limit=0: ordered.append((batch, list(texts), voice)),
    )
    lesson = LESSONS[0]
    body = client.get(f"/api/lessons/{lesson.slug}").json()

    assert body["audio_pending"] is True
    assert len(ordered) == 1
    batch, texts, _voice = ordered[0]
    assert batch == f"lekcja:{lesson.slug}"
    assert set(texts) == set(lesson.spoken())


def test_without_a_tts_key_nothing_is_promised(client, registered, monkeypatch):
    monkeypatch.setattr(tts, "is_configured", lambda: False)
    body = client.get(f"/api/lessons/{LESSONS[0].slug}").json()
    assert body["audio_pending"] is False


def test_a_batch_already_running_is_not_started_twice(monkeypatch):
    """Ekran dopytuje co kilka sekund. Bez tej blokady każde dopytanie
    odpalało nową partię tych samych zdań, ścigającą się z poprzednią."""
    monkeypatch.setattr(tts, "is_configured", lambda: True)
    voice_library._in_flight.add("lekcja:x|glos")
    try:
        assert voice_library.synthesize_texts("lekcja:x", ["Olá."], "glos") == 0
    finally:
        voice_library._in_flight.discard("lekcja:x|glos")
