import random
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.models import DeckItem, Example, Item, User, UserItemState, UserSettings
from app.services import task_builder as tb
from tests.conftest import make_items


def a_user(db) -> User:
    user = User(email="t@example.com", password_hash="x", display_name="T")
    user.settings = UserSettings(enabled_modes=["flashcard", "mcq_pt_pl", "mcq_pl_pt"])
    db.add(user)
    db.commit()
    return user


def a_state(db, user, item, **kwargs) -> UserItemState:
    defaults = {
        "user_id": user.id,
        "item_id": item.id,
        "direction": "recognition",
        "state": "review",
        "due": datetime.now(timezone.utc) - timedelta(hours=1),
        "stability": 5.0,
        "difficulty": 5.0,
        "reps": 3,
        "correct_reps": 3,
        "lapses": 0,
    }
    defaults.update(kwargs)
    state = UserItemState(**defaults)
    db.add(state)
    db.commit()
    return state


# ── mode selection ────────────────────────────────────────────────────────
def test_new_card_is_shown_not_tested():
    assert tb.pick_mode(None, "recognition", ["flashcard", "mcq_pt_pl"]) == "flashcard"


def test_learning_card_gets_multiple_choice():
    state = UserItemState(state="learning", due=datetime.now(timezone.utc))
    assert tb.pick_mode(state, "recognition", ["flashcard", "mcq_pt_pl"]) == "mcq_pt_pl"
    assert tb.pick_mode(state, "production", ["flashcard", "mcq_pl_pt"]) == "mcq_pl_pt"


def test_well_known_production_card_asks_for_typing_when_available():
    state = UserItemState(state="review", stability=60.0, due=datetime.now(timezone.utc))
    assert tb.pick_mode(state, "production", ["mcq_pl_pt", "typing", "cloze"]) == "typing"


def test_mode_selection_respects_what_the_user_enabled():
    state = UserItemState(state="review", stability=60.0, due=datetime.now(timezone.utc))
    # Typing and listening switched off — must fall back, never return them.
    chosen = tb.pick_mode(state, "production", ["mcq_pl_pt"])
    assert chosen == "mcq_pl_pt"


# ── distractors ───────────────────────────────────────────────────────────
def test_mcq_options_contain_the_answer_exactly_once(db):
    user = a_user(db)
    deck, items = make_items(db, count=10)
    item = items[0]
    task = tb.build_task(db, 0, item, "recognition", "mcq_pt_pl", True, [deck.id], None, 0.9)

    options = task.payload["options"]
    assert len(options) == 4
    assert len(set(options)) == 4, "distractors must not repeat"
    assert options[task.payload["answer_index"]] == item.pl
    assert options.count(item.pl) == 1


def test_distractors_never_include_a_synonym(db):
    a_user(db)
    deck, items = make_items(db, count=6)
    # A second item with the same Polish meaning — it must not be offered as a
    # wrong answer for the first.
    twin = Item(pt="outra", pl=items[0].pl, part_of_speech="noun", cefr_level="A1", verified=True)
    db.add(twin)
    db.commit()

    for _ in range(15):
        task = tb.build_task(db, 0, items[0], "recognition", "mcq_pt_pl", True, [deck.id], None, 0.9)
        wrong = [o for i, o in enumerate(task.payload["options"]) if i != task.payload["answer_index"]]
        assert items[0].pl not in wrong


def test_distractors_fall_back_when_the_pool_is_tiny(db):
    a_user(db)
    deck, items = make_items(db, count=2)
    task = tb.build_task(db, 0, items[0], "recognition", "mcq_pt_pl", True, [deck.id], None, 0.9)
    # Only one other item exists, so fewer than four options is expected —
    # but the answer must still be there and be findable.
    options = task.payload["options"]
    assert options[task.payload["answer_index"]] == items[0].pl


# ── queue shape ───────────────────────────────────────────────────────────
def test_new_items_are_woven_between_reviews_not_dumped_up_front():
    reviews = [f"r{i}" for i in range(12)]
    news = [f"n{i}" for i in range(3)]
    mixed = tb.interleave(reviews, news)

    assert len(mixed) == 15
    assert mixed[0] == (False, "r0"), "a session should open with something familiar"
    positions = [i for i, (is_new, _) in enumerate(mixed) if is_new]
    assert positions[0] >= tb.NEW_EVERY
    assert positions == sorted(positions)
    assert len(positions) == 3


def test_interleave_keeps_all_new_items_when_there_are_few_reviews():
    mixed = tb.interleave(["r0"], ["n0", "n1", "n2"])
    assert sum(1 for is_new, _ in mixed if is_new) == 3
    assert len(mixed) == 4


def test_build_session_respects_limits(db):
    user = a_user(db)
    deck, items = make_items(db, count=20)

    tasks, _ = tb.build_session(db, user, user.settings, new_limit=5, review_limit=10)
    assert len(tasks) == 5, "no cards exist yet, so only new items can appear"
    assert all(t.is_new for t in tasks)
    assert all(t.direction == "recognition" for t in tasks), "production must not start on day one"
    assert {t.index for t in tasks} == set(range(5))


def test_build_session_puts_due_cards_first(db):
    user = a_user(db)
    deck, items = make_items(db, count=20)
    for item in items[:6]:
        # Below the unlock threshold, so these stay recognition-only.
        a_state(db, user, item, correct_reps=1)

    tasks, _ = tb.build_session(db, user, user.settings, new_limit=2, review_limit=50)
    kinds = [t.is_new for t in tasks]
    assert kinds[0] is False
    assert sum(1 for k in kinds if k is False) == 6
    assert sum(1 for k in kinds if k is True) == 2


def test_building_a_session_unlocks_production_for_well_known_words(db):
    """A word recognised reliably starts being asked the other way round —
    and that doubles how often it shows up."""
    user = a_user(db)
    deck, items = make_items(db, count=20)
    for item in items[:6]:
        a_state(db, user, item, correct_reps=tb.PRODUCTION_UNLOCK_AT)

    tasks, _ = tb.build_session(db, user, user.settings, new_limit=0, review_limit=50)
    directions = [t.direction for t in tasks]
    assert directions.count("recognition") == 6
    assert directions.count("production") == 6


def test_suspended_and_unverified_cards_stay_out_of_the_queue(db):
    user = a_user(db)
    deck, items = make_items(db, count=6)
    a_state(db, user, items[0], suspended=True)
    items[1].verified = False
    db.commit()

    tasks, _ = tb.build_session(db, user, user.settings, new_limit=10, review_limit=10)
    served = {t.item_id for t in tasks}
    assert items[0].id not in served
    assert items[1].id not in served


def test_production_unlocks_only_after_enough_correct_recognitions(db):
    user = a_user(db)
    deck, items = make_items(db, count=4)
    a_state(db, user, items[0], correct_reps=tb.PRODUCTION_UNLOCK_AT)
    a_state(db, user, items[1], correct_reps=tb.PRODUCTION_UNLOCK_AT - 1)

    created = tb.unlock_production(db, user, datetime.now(timezone.utc))
    db.commit()

    assert created == 1
    unlocked = db.get(UserItemState, (user.id, items[0].id, "production"))
    assert unlocked is not None and unlocked.state == "new"
    assert db.get(UserItemState, (user.id, items[1].id, "production")) is None

    # Running it again must not create a second production card.
    assert tb.unlock_production(db, user, datetime.now(timezone.utc)) == 0


def test_queue_counts_report_due_and_available(db):
    user = a_user(db)
    deck, items = make_items(db, count=8)
    a_state(db, user, items[0])
    a_state(db, user, items[1], due=datetime.now(timezone.utc) + timedelta(days=3))

    counts = tb.queue_counts(db, user, datetime.now(timezone.utc))
    assert counts["due"] == 1
    assert counts["new_available"] == 6
    assert counts["next_due_at"] is not None


def test_sentences_in_production_are_rebuilt_not_retyped(db):
    """Word order is what a sentence teaches — typing it out drills spelling."""
    user = a_user(db)
    deck, items = make_items(db, count=3)
    sentence = Item(
        pt="Não tenho tempo amanhã",
        pl="Nie mam jutro czasu",
        type="sentence",
        part_of_speech="expr",
        cefr_level="A2",
        verified=True,
    )
    db.add(sentence)
    db.commit()
    state = a_state(db, user, sentence, direction="production", stability=60.0)

    enabled = ["flashcard", "mcq_pl_pt", "typing", "cloze", "word_bank"]
    assert tb.choose_mode(state, "production", enabled, sentence) == "word_bank"
    # A single word never becomes a word bank, however mature it is.
    assert tb.choose_mode(state, "production", enabled, items[0]) != "word_bank"


def test_cloze_needs_an_example_that_actually_contains_the_word(db):
    a_user(db)
    with_example = Item(pt="conta", pl="rachunek", article="a", part_of_speech="noun", cefr_level="A1", verified=True)
    db.add(with_example)
    db.flush()
    db.add(
        Example(
            item_id=with_example.id,
            pt="Pode trazer a conta, se faz favor?",
            pl="Czy może pan przynieść rachunek?",
        )
    )
    orphan = Item(pt="bilheteira", pl="kasa biletowa", part_of_speech="noun", cefr_level="A2", verified=True)
    db.add(orphan)
    db.flush()
    db.add(Example(item_id=orphan.id, pt="Onde fica a estação?", pl="Gdzie jest dworzec?"))
    db.commit()
    db.refresh(with_example)
    db.refresh(orphan)

    assert tb.supports("cloze", with_example) is True
    assert tb.supports("cloze", orphan) is False, "the sentence never mentions the word"

    parts = tb.cloze_parts(with_example, with_example.examples[0])
    assert parts["answer"] == "conta"
    assert parts["before"].endswith("a ")
    assert parts["after"].startswith(",")


def test_cloze_finds_the_word_despite_accents_and_case(db):
    a_user(db)
    item = Item(pt="almoço", pl="obiad", article="o", part_of_speech="noun", cefr_level="A1", verified=True)
    db.add(item)
    db.flush()
    db.add(Example(item_id=item.id, pt="Almoço é às duas.", pl="Obiad jest o drugiej."))
    db.commit()
    db.refresh(item)

    parts = tb.cloze_parts(item, item.examples[0])
    assert parts is not None
    assert parts["answer"] == "Almoço", "the sentence's own casing is kept"


# ── kolejność wykładania kart ─────────────────────────────────────────────
def test_spread_pulls_apart_cards_from_the_same_deck():
    """Kolejność w talii jest tematyczna, więc podana wprost podpowiada odpowiedź.

    Po „wiośnie" następne pytanie jest o inną porę roku — wybór zawęża się do
    czterech, zanim uczeń cokolwiek sobie przypomni."""
    rng = random.Random(7)
    pory = [(f"pora{i}", "pory-roku", i) for i in range(4)]
    kolory = [(f"kolor{i}", "kolory", i) for i in range(4)]
    liczby = [(f"liczba{i}", "liczby", i) for i in range(4)]

    out = tb.spread(pory + kolory + liczby, lambda e: e, rng)
    sasiedzi = sum(1 for a, b in zip(out, out[1:], strict=False) if a[1] == b[1])
    assert sasiedzi == 0, [e[1] for e in out]


def test_spread_pulls_apart_neighbours_from_one_shelf_of_a_deck():
    """Gniazdo tematyczne poznaje się po sąsiedztwie w talii, nie po nazwie talii.

    „Pory roku" nie są osobną talią — leżą obok siebie w środku większej, więc
    sama talia nie odróżnia ich od reszty. Odróżnia je miejsce w kolejności."""
    rng = random.Random(9)
    entries = [(f"slowo{i}", "jedna-talia", i) for i in range(14)]

    out = tb.spread(entries, lambda e: e, rng)
    blisko = sum(
        1 for a, b in zip(out, out[1:], strict=False) if abs(a[2] - b[2]) <= tb.NEAR_IN_DECK
    )
    assert blisko == 0, [e[2] for e in out]


def test_spread_never_asks_about_the_same_item_twice_in_a_row():
    """PL→PT tuż po PT→PL to nie powtórka, tylko przepisanie odpowiedzi,
    którą ma się przed oczami."""
    rng = random.Random(3)
    # Cztery pozycje z jednej talii, każda w obu kierunkach.
    entries = [(f"slowo{i}", "jedna-talia", i, kier) for i in range(4) for kier in ("r", "p")]

    out = tb.spread(entries, lambda e: (e[0], e[1], e[2]), rng)
    assert all(a[0] != b[0] for a, b in zip(out, out[1:], strict=False)), out


def test_spread_keeps_every_card():
    rng = random.Random(11)
    entries = [(i, i % 3, i) for i in range(30)]
    assert sorted(tb.spread(entries, lambda e: e, rng)) == sorted(entries)


def test_spread_shuffles_even_when_there_is_nothing_to_pull_apart():
    """Przy jednej talii w sesji nie ma czego rozsuwać — ale i wtedy kolejność
    z talii ma się rozejść, bo to w niej pory roku leżą obok siebie."""
    entries = [(i, "jedna-talia", i) for i in range(20)]
    out = tb.spread(entries, lambda e: e, random.Random(5))
    assert out != entries


def test_a_session_does_not_hand_out_one_deck_at_a_time(db):
    """Test na całej sesji, nie na samej funkcji: kolejka podaje nowy materiał
    po kolei z talii, więc bez rozsuwania cała talia szła jednym ciągiem."""
    user = a_user(db)
    # Osobne pozycje talii, jak w bazie startowej — bez tego kolejka i tak
    # przeplatałaby talie przypadkiem i test nie sprawdzałby niczego.
    for spot, (name, prefix) in enumerate(
        (("Pory roku", "pora"), ("Kolory", "cor"), ("Liczby", "num")), start=1
    ):
        make_items(
            db, count=6, deck_name=name, prefix=prefix, pl_prefix=f"{prefix}-pl", position=spot
        )

    tasks, _ = tb.build_session(
        db, user, user.settings, new_limit=12, review_limit=0, rng=random.Random(42)
    )
    miejsca = [
        db.execute(
            select(DeckItem.deck_id, DeckItem.position).where(DeckItem.item_id == t.item_id)
        ).first()
        for t in tasks
    ]
    pod_rzad = sum(
        1
        for a, b in zip(miejsca, miejsca[1:], strict=False)
        if a[0] == b[0] and abs(a[1] - b[1]) <= tb.NEAR_IN_DECK
    )
    assert pod_rzad == 0, f"materiał z jednej półki talii nadal idzie ciągiem: {miejsca}"


def test_spreading_does_not_change_which_cards_the_session_takes(db):
    """Rozsuwanie dotyczy kolejności, nie doboru. Program nauki i FSRS
    decydują, co wchodzi do sesji — to zostaje nietknięte."""
    user = a_user(db)
    make_items(db, count=30, deck_name="Jedna")

    wybrane = set()
    for seed in (1, 2, 3):
        tasks, _ = tb.build_session(
            db, user, user.settings, new_limit=8, review_limit=0, rng=random.Random(seed)
        )
        wybrane.add(frozenset(t.item_id for t in tasks))
    assert len(wybrane) == 1, "za każdym razem inny materiał, nie tylko inna kolejność"
