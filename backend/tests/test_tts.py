from datetime import datetime, timedelta, timezone

import pytest

from app.config import settings
from app.models import AudioAsset, Item, UserItemState
from app.services import task_builder as tb
from app.services import tts
from tests.conftest import make_items


class FakeProvider:
    """Zamiast Google. Liczy wywołania, bo najważniejsze w tym module jest to,
    ile razy *nie* zadzwoniło się po płatną syntezę."""

    name = "fake"

    def __init__(self, fail: Exception | None = None) -> None:
        self.calls: list[tuple[str, str, float]] = []
        self.fail = fail

    def synthesize(self, text: str, voice: str, speed: float) -> tts.Spoken:
        self.calls.append((text, voice, speed))
        if self.fail:
            raise self.fail
        return tts.Spoken(data=b"ID3fake-mp3-bytes", mime="audio/mpeg", char_count=len(text))

    def voices(self) -> list[dict]:
        return [{"name": "pt-PT-Wavenet-A", "gender": "female", "quality": "wavenet"}]


# ── klucz cache ───────────────────────────────────────────────────────────
def test_same_text_same_key_regardless_of_spacing():
    assert tts.cache_key("bom  dia", "pt-PT-Wavenet-A", 1.0) == tts.cache_key(
        " bom dia ", "pt-PT-Wavenet-A", 1.0
    )


def test_voice_and_speed_change_the_key():
    base = tts.cache_key("bom dia", "pt-PT-Wavenet-A", 1.0)
    assert base != tts.cache_key("bom dia", "pt-PT-Wavenet-B", 1.0)
    assert base != tts.cache_key("bom dia", "pt-PT-Wavenet-A", 0.75)


def test_accents_are_part_of_the_word_not_noise():
    assert tts.cache_key("avó", "pt-PT-Wavenet-A", 1.0) != tts.cache_key("avo", "pt-PT-Wavenet-A", 1.0)


# ── synteza ───────────────────────────────────────────────────────────────
def test_recording_is_paid_for_once(db):
    provider = FakeProvider()
    first = tts.speak(db, "bom dia", voice="pt-PT-Wavenet-A", provider=provider)
    db.commit()
    second = tts.speak(db, "bom dia", voice="pt-PT-Wavenet-A", provider=provider)

    assert first.id == second.id
    assert len(provider.calls) == 1, "drugie żądanie musi trafić w cache"
    assert first.data == b"ID3fake-mp3-bytes"
    assert first.char_count == len("bom dia")


def test_brazilian_voice_is_refused(db):
    provider = FakeProvider()
    with pytest.raises(tts.TTSError, match="portugalskim europejskim"):
        tts.speak(db, "bom dia", voice="pt-BR-Neural2-A", provider=provider)
    assert provider.calls == [], "odrzucenie musi nastąpić przed zapłaceniem za nagranie"


def test_empty_and_overlong_text_never_reach_the_provider(db):
    provider = FakeProvider()
    with pytest.raises(tts.TTSError):
        tts.speak(db, "   ", provider=provider)
    with pytest.raises(tts.TTSError):
        tts.speak(db, "a" * (tts.MAX_CHARS + 1), provider=provider)
    assert provider.calls == []


def test_monthly_limit_stops_new_recordings_but_not_old_ones(db, monkeypatch):
    provider = FakeProvider()
    monkeypatch.setattr(settings, "tts_monthly_char_limit", 10)

    tts.speak(db, "bom dia", provider=provider)  # 7 znaków — mieści się
    db.commit()

    with pytest.raises(tts.TTSLimitReached):
        tts.speak(db, "boa tarde", provider=provider)

    # To, co już nagrane, dalej działa bez pytania dostawcy.
    again = tts.speak(db, "bom dia", provider=provider)
    assert again is not None
    assert len(provider.calls) == 1


def test_last_months_usage_does_not_count_against_this_month(db, monkeypatch):
    old = AudioAsset(
        cache_key="x" * 64,
        text="stare",
        voice="pt-PT-Wavenet-A",
        speed=1.0,
        data=b"x",
        size=1,
        char_count=9_000,
        created_at=datetime.now(timezone.utc) - timedelta(days=40),
    )
    db.add(old)
    db.commit()

    assert tts.chars_this_month(db) == 0


def test_provider_failure_does_not_leave_a_broken_row(db):
    provider = FakeProvider(fail=tts.TTSError("Klucz API został odrzucony przez Google."))
    with pytest.raises(tts.TTSError):
        tts.speak(db, "bom dia", provider=provider)
    db.rollback()
    assert tts.lookup(db, "bom dia", settings.tts_voice_default, 1.0) is None


# ── dobór trybu ───────────────────────────────────────────────────────────
def test_listening_needs_a_recording(db):
    _, items = make_items(db, count=2)
    assert tb.supports("listening", items[0], has_audio=False) is False
    assert tb.supports("listening", items[0], has_audio=True) is True


def test_listening_is_skipped_when_the_word_has_no_audio(db):
    _, items = make_items(db, count=4)
    state = UserItemState(state="review", stability=60.0, due=datetime.now(timezone.utc))
    enabled = ["listening", "flashcard", "mcq_pt_pl"]

    silent = tb.choose_mode(state, "recognition", enabled, items[0], has_audio=False)
    assert silent != "listening"
    assert tb.choose_mode(state, "recognition", enabled, items[0], has_audio=True) == "listening"


def test_session_only_offers_audio_that_exists(db):
    _, items = make_items(db, count=3)
    voice = "pt-PT-Wavenet-A"
    provider = FakeProvider()
    tts.speak(db, items[0].display_pt, voice=voice, provider=provider)
    db.commit()

    index = tb.audio_index(db, items, voice)
    assert index[items[0].id]["pt"].endswith(".mp3")
    assert "pt_slow" not in index[items[0].id], "wolnej wersji jeszcze nie nagrano"
    assert index[items[1].id] == {}, "nienagrane pozycje nie dostają adresu"


def test_audio_index_asks_the_database_once(db):
    _, items = make_items(db, count=25)
    index = tb.audio_index(db, items, "pt-PT-Wavenet-A")
    assert len(index) == 25
    assert all(value == {} for value in index.values())


# ── endpointy ─────────────────────────────────────────────────────────────
def test_recording_plays_without_a_token_but_is_cached_forever(client, registered, db):
    asset = tts.speak(db, "bom dia", provider=FakeProvider())
    db.commit()

    bare = client.__class__(client.app)  # nowy klient, bez nagłówka Authorization
    response = bare.get(f"/api/audio/{asset.cache_key}.mp3")

    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/mpeg"
    assert "immutable" in response.headers["cache-control"]
    assert response.content == b"ID3fake-mp3-bytes"


def test_unknown_recording_is_a_clean_404(client, registered):
    response = client.get(f"/api/audio/{'a' * 64}.mp3")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "AUDIO_NOT_FOUND"


def test_usage_needs_a_login(client):
    assert client.get("/api/audio/usage").status_code == 401


def test_usage_reports_what_is_stored(client, registered, db):
    tts.speak(db, "bom dia", provider=FakeProvider())
    db.commit()

    body = client.get("/api/audio/usage").json()
    assert body["clips_stored"] == 1
    assert body["chars_this_month"] == 7
    assert body["configured"] is False, "w testach nie ma klucza API"


def test_speak_endpoint_refuses_without_a_key(client, registered):
    response = client.post("/api/audio/speak", json={"text": "bom dia"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "TTS_NOT_CONFIGURED"


def test_quiz_hides_the_recording_when_it_would_give_the_answer(db):
    from app.routers.quizzes import _public

    questions = [
        {"mode": "typing", "pt": "a casa", "pl": "dom", "audio": {"pt": "/api/audio/a.mp3"}},
        {"mode": "mcq_pt_pl", "pt": "a casa", "pl": "dom", "audio": {"pt": "/api/audio/a.mp3"}},
        {"mode": "listening", "pt": "a casa", "pl": "dom", "audio": {"pt": "/api/audio/a.mp3"}},
    ]
    typed, recognition, listening = _public(questions)

    assert typed["audio"] == {}, "wpisywanie: usłyszenie odpowiedzi to ta sama ściąga co jej przeczytanie"
    assert "pt" not in typed
    assert recognition["audio"]["pt"], "rozpoznawanie: słowo i tak jest na ekranie"
    assert listening["audio"]["pt"], "ze słuchu: nagranie JEST pytaniem"
    assert "pt" not in listening, "…ale zapisane słowo zdradziłoby odpowiedź"


def test_dictionary_exposes_audio_when_it_exists(client, registered, db):
    _, items = make_items(db, count=2)
    # Ten sam głos, który ma świeże konto — słownik szuka nagrań po nazwie głosu
    # z ustawień, więc rozjazd tutaj znaczyłby ciszę w całej aplikacji.
    tts.speak(db, items[0].display_pt, voice=settings.tts_voice_default, provider=FakeProvider())
    db.commit()

    rows = {row["display_pt"]: row for row in client.get("/api/items").json()["items"]}
    assert rows[items[0].display_pt]["audio_url"] is not None
    assert rows[items[1].display_pt]["audio_url"] is None


def test_new_accounts_use_the_voice_the_synthesiser_records_in(client, db):
    """Domyślny głos konta i domyślny głos syntezy to musi być ta sama nazwa.

    Rozjazd nie wywala niczego — po prostu żadne nagranie nigdy się nie dopasuje
    i cała aplikacja milczy bez jednego komunikatu o błędzie. Dokładnie tak
    zachowywał się nieistniejący `pt-PT-Neural2-A` sprzed migracji.
    """
    from app.models import UserSettings

    column_default = UserSettings.__table__.c.tts_voice.default.arg
    assert column_default == settings.tts_voice_default


def test_every_list_of_words_carries_its_audio(client, registered, db):
    """Słownik, talia i karta pozycji — wszędzie ten sam głośnik.

    Widok talii przez chwilę był jedynym miejscem, które nie doklejało adresu
    nagrania: przycisk był, ale milczał albo znikał. Test pilnuje wszystkich
    trzech dróg naraz, bo pominięcie jednej nie wywołuje żadnego błędu.
    """
    deck, items = make_items(db, count=3)
    item = items[0]
    provider = FakeProvider()
    tts.speak(db, item.display_pt, voice=settings.tts_voice_default, provider=provider)
    tts.speak(db, item.examples[0].pt, voice=settings.tts_voice_default, provider=provider)
    db.commit()

    listed = next(
        row for row in client.get("/api/items").json()["items"] if row["id"] == str(item.id)
    )
    assert listed["audio_url"], "słownik"

    in_deck = next(
        row for row in client.get(f"/api/decks/{deck.id}").json()["items"] if row["id"] == str(item.id)
    )
    assert in_deck["audio_url"], "widok talii"

    detail = client.get(f"/api/items/{item.id}").json()
    assert detail["audio_url"], "karta pozycji"
    assert detail["examples"][0]["audio_url"], "zdanie przykładowe ma własne nagranie"
