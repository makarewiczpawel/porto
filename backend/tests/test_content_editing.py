"""Własne pozycje, własne talie i import z CSV."""

from app.models import Deck, DeckItem, Item
from app.services import importer
from tests.conftest import make_items


# ── parser CSV ────────────────────────────────────────────────────────────
def test_excel_semicolons_are_understood_like_commas():
    """Polski Excel zapisuje CSV średnikami. To nie jest przypadek brzegowy —
    to domyślne zachowanie na maszynie użytkownika."""
    parsed = importer.parse("a casa;dom\no carro;samochód")
    assert [row.pt for row in parsed.rows] == ["a casa", "o carro"]


def test_header_is_recognised_by_polish_names_too():
    parsed = importer.parse("portugalski,polski,poziom\nobrigado,dziękuję,A1")
    assert len(parsed.rows) == 1
    assert parsed.rows[0].cefr_level == "A1"
    assert parsed.rows[0].pl == "dziękuję"


def test_first_row_is_data_when_it_is_not_a_header():
    parsed = importer.parse("obrigado,dziękuję\nadeus,do widzenia")
    assert len(parsed.rows) == 2, "wiersz danych nie może zniknąć wzięty za nagłówek"


def test_type_is_guessed_from_the_shape_of_the_text():
    parsed = importer.parse("casa,dom\nbom dia,dzień dobry\nNão tenho tempo.,Nie mam czasu")
    assert [row.type for row in parsed.rows] == ["word", "phrase", "sentence"]


def test_broken_row_reports_its_line_and_does_not_stop_the_rest():
    parsed = importer.parse("pt,pl\na casa,dom\n,brak\no carro,samochód")
    assert [row.pt for row in parsed.rows] == ["a casa", "o carro"]
    assert len(parsed.problems) == 1
    assert parsed.problems[0].line == 3, "numer wiersza musi zgadzać się z arkuszem"


def test_unknown_level_is_refused_rather_than_guessed():
    parsed = importer.parse("pt,pl,poziom\na casa,dom,C9")
    assert parsed.rows == []
    assert "C9" in parsed.problems[0].reason


def test_import_is_capped(monkeypatch):
    monkeypatch.setattr(importer, "MAX_ROWS", 3)
    parsed = importer.parse("\n".join(f"slowo{i},polskie{i}" for i in range(10)))
    assert len(parsed.rows) == 3
    assert "3 wierszy" in parsed.problems[0].reason


# ── tworzenie pozycji ─────────────────────────────────────────────────────
def test_own_item_lands_in_the_dictionary_with_its_example(client, registered, db):
    response = client.post(
        "/api/items",
        json={
            "pt": "a esplanada",
            "pl": "ogródek kawiarniany",
            "article": "a",
            "gender": "f",
            "cefr_level": "A2",
            "example_pt": "Vamos para a esplanada?",
            "example_pl": "Idziemy do ogródka?",
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["display_pt"] == "a esplanada"
    assert body["source"] == "user"
    assert body["examples"][0]["pt"] == "Vamos para a esplanada?"


def test_duplicate_item_is_refused_with_a_pointer_to_the_original(client, registered, db):
    payload = {"pt": "a esplanada", "pl": "ogródek kawiarniany"}
    first = client.post("/api/items", json=payload)
    assert first.status_code == 201

    second = client.post("/api/items", json=payload)
    assert second.status_code == 409
    assert second.json()["error"]["details"]["item_id"] == first.json()["id"]


def test_seed_items_cannot_be_edited_or_deleted(client, registered, db):
    _, items = make_items(db, count=1)
    item_id = items[0].id

    patched = client.patch(f"/api/items/{item_id}", json={"pl": "cokolwiek"})
    assert patched.status_code == 403
    assert patched.json()["error"]["code"] == "ITEM_READONLY"
    assert client.delete(f"/api/items/{item_id}").status_code == 403


def test_own_item_can_be_corrected_and_removed(client, registered, db):
    created = client.post("/api/items", json={"pt": "o telemovel", "pl": "telefon"}).json()

    fixed = client.patch(f"/api/items/{created['id']}", json={"pt": "o telemóvel"})
    assert fixed.status_code == 200
    assert fixed.json()["pt"] == "o telemóvel"

    assert client.delete(f"/api/items/{created['id']}").status_code == 204
    assert client.get(f"/api/items/{created['id']}").status_code == 404


# ── własne talie ──────────────────────────────────────────────────────────
def test_own_deck_is_private_and_holds_added_items(client, registered, db):
    deck = client.post("/api/decks", json={"name": "Praca"}).json()
    created = client.post(
        "/api/items", json={"pt": "a reunião", "pl": "spotkanie", "deck_id": deck["id"]}
    ).json()

    detail = client.get(f"/api/decks/{deck['id']}").json()
    assert [row["id"] for row in detail["items"]] == [created["id"]]

    stored = db.get(Deck, __import__("uuid").UUID(deck["id"]))
    assert stored.is_shared is False, "własna talia nie może pojawić się u drugiej osoby"


# ── import ────────────────────────────────────────────────────────────────
def test_dry_run_shows_a_preview_and_writes_nothing(client, registered, db):
    before = db.query(Item).count()
    response = client.post(
        "/api/items/import",
        json={"csv": "pt,pl\na praia,plaża\no mar,morze", "dry_run": True},
    )
    body = response.json()

    assert body["created"] == 0
    assert [row["pt"] for row in body["preview"]] == ["a praia", "o mar"]
    assert db.query(Item).count() == before


def test_import_creates_a_deck_and_reports_duplicates(client, registered, db):
    client.post("/api/items", json={"pt": "a praia", "pl": "plaża"})

    body = client.post(
        "/api/items/import",
        json={"csv": "pt,pl\na praia,plaża\no mar,morze\n,zły wiersz", "deck_name": "Wakacje"},
    ).json()

    assert body["created"] == 1
    assert body["skipped_duplicates"] == 1, "istniejąca pozycja nie jest dublowana"
    assert len(body["errors"]) == 1
    assert body["deck_id"] is not None

    deck_items = db.query(DeckItem).filter_by(deck_id=__import__("uuid").UUID(body["deck_id"])).count()
    assert deck_items == 2, "do talii trafiają obie pozycje, także ta, która już istniała"


def test_importing_the_same_file_twice_changes_nothing(client, registered, db):
    payload = {"csv": "pt,pl\na praia,plaża\no mar,morze", "deck_name": "Wakacje"}
    first = client.post("/api/items/import", json=payload).json()
    assert first["created"] == 2

    second = client.post(
        "/api/items/import", json={**payload, "deck_id": first["deck_id"], "deck_name": None}
    ).json()
    assert second["created"] == 0
    assert second["skipped_duplicates"] == 2
    assert db.query(DeckItem).filter_by(deck_id=__import__("uuid").UUID(first["deck_id"])).count() == 2


def test_imported_words_are_learnable_right_away(client, registered, db):
    client.post("/api/items/import", json={"csv": "pt,pl\na praia,plaża\no mar,morze"})
    summary = client.get("/api/study/queue/summary").json()
    assert summary["new_available"] >= 2


def test_a_word_added_without_a_deck_still_reaches_the_queue(client, registered, db):
    """Kolejka dobiera nowe pozycje przez talie. Słowo dodane „luzem" bez tego
    leżałoby w słowniku i nigdy nie pojawiło się w sesji — cicho i myląco."""
    client.post("/api/items", json={"pt": "a saudade", "pl": "tęsknota"})

    summary = client.get("/api/study/queue/summary").json()
    assert summary["new_available"] >= 1

    decks = {deck["name"] for deck in client.get("/api/decks").json()}
    assert "Moje słówka" in decks, "użytkownik musi widzieć, gdzie to słowo wylądowało"


def test_columns_after_the_first_two_are_read_by_content_not_position():
    """Ludzie piszą listy w dowolnej kolejności kolumn. Sztywne „trzecia to
    typ" znaczyło, że poziom A2 w trzeciej kolumnie po cichu znikał."""
    parsed = importer.parse(
        "uma toalha; ręcznik; A2\nbom dia; dzień dobry; phrase; B1; potocznie"
    )
    towel, greeting = parsed.rows

    assert towel.cefr_level == "A2"
    assert greeting.cefr_level == "B1"
    assert greeting.type == "phrase"
    assert greeting.notes == "potocznie"


def test_article_does_not_make_a_word_into_a_phrase():
    parsed = importer.parse("uma toalha,ręcznik\na casa,dom\nbom dia,dzień dobry")
    assert [row.type for row in parsed.rows] == ["word", "word", "phrase"]


def test_article_typed_into_the_word_is_not_doubled(client, registered):
    """`display_pt` dokleja rodzajnik z osobnej kolumny. Bez rozdzielenia
    „a esplanada" z rodzajnikiem „a" wyświetlało się jako „a a esplanada"."""
    body = client.post(
        "/api/items", json={"pt": "a esplanada", "pl": "ogródek", "article": "a"}
    ).json()
    assert body["pt"] == "esplanada"
    assert body["display_pt"] == "a esplanada"

    # Bez podanego rodzajnika też: wykrywamy go z samego tekstu.
    other = client.post("/api/items", json={"pt": "o comboio", "pl": "pociąg"}).json()
    assert other["article"] == "o"
    assert other["display_pt"] == "o comboio"
