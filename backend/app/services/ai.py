"""Wywołania modelu językowego — jedyne miejsce, które rozmawia z Anthropic.

Moduł stoi na tych samych trzech zasadach co synteza mowy, bo problem jest ten
sam: płatne API, które łatwo wywołać za dużo razy.

1. **Każdy koszt jest zapisany.** Wiersz w `ai_generation_jobs` powstaje przy
   każdym wywołaniu — także nieudanym, bo tokeny wejściowe policzono i tak.
   Suma z bieżącego miesiąca jest tym, co widzi ekran ustawień, i tym, co
   zatrzymuje kolejne wywołanie.
2. **Twardy limit miesięczny.** Po przekroczeniu `AI_MONTHLY_BUDGET_USD`
   funkcje AI przestają działać z czytelnym komunikatem. Reszta aplikacji —
   nauka, powtórki, wymowa — działa dalej bez zmian.
3. **Tylko portugalski europejski.** Model domyślnie zsuwa się w brazylijski,
   bo tak wygląda większość portugalskiego w internecie. Zakaz jest w prompcie
   wypisany z nazwiska, słowo po słowie, a nie zasygnalizowany ogólnikiem.

Do tego jedna zasada, której przy wymowie nie było: **nic z modelu nie trafia
do słownika samo**. Wygenerowane pozycje czekają w `result` na przegląd
człowieka i dopiero zaakceptowane stają się pozycjami do nauki.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import AiCacheEntry, AiJob, Item, User

# Ceny w dolarach za milion tokenów. Nieznany model liczymy po najdroższej
# stawce, jaką znamy — pomyłka w tę stronę zatrzymuje wydawanie za wcześnie,
# a nie za późno.
MODEL_PRICES: dict[str, tuple[float, float]] = {
    "claude-opus-5": (5.00, 25.00),
    "claude-opus-4-8": (5.00, 25.00),
    "claude-opus-4-7": (5.00, 25.00),
    "claude-opus-4-6": (5.00, 25.00),
    "claude-sonnet-5": (3.00, 15.00),
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-haiku-4-5": (1.00, 5.00),
    "claude-fable-5": (10.00, 50.00),
}
FALLBACK_PRICE = (10.00, 50.00)

TIMEOUT_SECONDS = 120.0
# Generowanie zestawu to jedyne długie wyjście; reszta mieści się w kilkuset
# tokenach. Poniżej progu, przy którym dokumentacja zaleca strumieniowanie.
MAX_TOKENS_SET = 16000
MAX_TOKENS_SHORT = 2000


class AIError(RuntimeError):
    """Komunikat trafia wprost do interfejsu, więc jest po polsku."""


class AINotConfigured(AIError):
    pass


class AIBudgetReached(AIError):
    pass


class AIRefused(AIError):
    pass


# ── schematy odpowiedzi ───────────────────────────────────────────────────
# Pydantic jest tu kontraktem w obie strony: schemat leci do modelu jako
# wymuszony format wyjścia, a odpowiedź wraca już zwalidowana. Żadne pole nie
# ma wartości domyślnej — dzięki temu wszystkie są w schemacie wymagane i model
# musi świadomie wpisać `null`, zamiast po cichu pominąć rodzajnik.

PartOfSpeech = Literal[
    "noun", "verb", "adj", "adv", "phrase", "pron", "prep", "conj", "num", "interj"
]


class GeneratedItem(BaseModel):
    pt: str = Field(description="Hasło po portugalsku europejskim, bez rodzajnika.")
    pl: str = Field(description="Naturalne tłumaczenie na polski.")
    type: Literal["word", "phrase", "sentence"]
    part_of_speech: PartOfSpeech | None
    article: Literal["o", "a", "os", "as"] | None = Field(
        description="Rodzajnik określony dla rzeczownika; null dla pozostałych części mowy."
    )
    gender: Literal["m", "f"] | None = Field(
        description="Rodzaj gramatyczny rzeczownika; null dla pozostałych części mowy."
    )
    plural: str | None = Field(description="Liczba mnoga rzeczownika, jeśli nieregularna; inaczej null.")
    cefr_level: Literal["A1", "A2", "B1", "B2", "C1"]
    notes: str | None = Field(
        description="Jedna krótka uwaga po polsku, gdy jest istotna (np. różnica wobec brazylijskiego, "
        "fałszywy przyjaciel, wymowa). Inaczej null."
    )
    example_pt: str = Field(description="Zdanie przykładowe po portugalsku europejskim, z tym hasłem.")
    example_pl: str = Field(description="Tłumaczenie zdania przykładowego na polski.")


class GeneratedSet(BaseModel):
    deck_name: str = Field(description="Krótka nazwa talii po polsku, maksymalnie 40 znaków.")
    items: list[GeneratedItem]


class Explanation(BaseModel):
    verdict: Literal["blisko", "inne_slowo", "gramatyka", "ortografia", "brazylijski"] = Field(
        description="Rodzaj pomyłki."
    )
    explanation: str = Field(description="Maksymalnie dwa zdania po polsku, bez powtarzania pytania.")


class TranslationGrade(BaseModel):
    score: int = Field(ge=0, le=100, description="0 = zupełnie nie to, 100 = bez zarzutu.")
    corrected: str = Field(description="Poprawna wersja po portugalsku europejskim.")
    feedback: str = Field(description="Maksymalnie dwa zdania po polsku: co konkretnie poprawić.")


class ExampleSentence(BaseModel):
    pt: str
    pl: str


class ExampleSet(BaseModel):
    examples: list[ExampleSentence]


# ── prompty ───────────────────────────────────────────────────────────────
# Zakazane brazylizmy są wypisane parami, bo „pisz po europejsku" model rozumie
# jako sugestię, a konkretną listę traktuje jak regułę. Te słowa różnią się
# całkowicie, a nie akcentem — polski uczeń nie ma szans zauważyć podmianki.
BRAZILIANISMS = [
    ("ônibus", "autocarro"),
    ("trem", "comboio"),
    ("celular", "telemóvel"),
    ("geladeira", "frigorífico"),
    ("banheiro", "casa de banho"),
    ("café da manhã", "pequeno-almoço"),
    ("suco", "sumo"),
    ("sorvete", "gelado"),
    ("xícara", "chávena"),
    ("terno", "fato"),
    ("meias (skarpety)", "peúgas"),
    ("grama (trawa)", "relva"),
    ("time", "equipa"),
    ("tela", "ecrã"),
    ("aeromoça", "hospedeira de bordo"),
    ("açougue", "talho"),
    ("bala (cukierek)", "rebuçado"),
    ("fila", "bicha / fila"),
    ("carteira de motorista", "carta de condução"),
    ("bonde", "elétrico"),
    ("presunto", "fiambre"),
    ("apelido (przezwisko)", "alcunha — po europejsku „apelido​\" to nazwisko"),
    ("delicioso (nadużywane)", "saboroso"),
    ("legal", "fixe"),
    ("garçom", "empregado de mesa"),
    ("pedestre", "peão"),
    ("esporte", "desporto"),
    ("estação de trem", "estação de comboios"),
]

PT_PT_RULES = """Piszesz wyłącznie po portugalsku europejskim (PT-PT), tak jak mówi się w Portugalii.

Zakazane słowa brazylijskie i ich europejskie odpowiedniki — użycie lewej strony to błąd:
{banned}

Zasady gramatyczne obowiązujące w Portugalii:
- Czas teraźniejszy ciągły to „estar a + bezokolicznik" („estou a comer"), nigdy „estar + gerúndio" („estou comendo").
- Zaimek nieakcentowany stoi po czasowniku z łącznikiem w zdaniu twierdzącym: „dá-me", „chamo-me", nigdy „me dá".
- Do osoby, którą się tyka, mówi się przez „tu" i drugą osobę liczby pojedynczej; grzecznościowo przez „o senhor / a senhora" albo trzecią osobę, nie przez „você".
- Formy grzecznościowe: „se faz favor", „faz favor", „obrigado" (mężczyzna) / „obrigada" (kobieta), „bom dia / boa tarde / boa noite".
- Pisownia po reformie ortograficznej z 1990 r., w wariancie używanym w Portugalii.

Ortografia portugalska jest częścią hasła: „avó" i „avô" to dwa różne słowa. Znaki diakrytyczne stawiaj zawsze."""


def pt_pt_rules() -> str:
    banned = "\n".join("- NIE " + bad + " — TAK " + good for bad, good in BRAZILIANISMS)
    return PT_PT_RULES.format(banned=banned)


SET_SYSTEM = """Jesteś lektorem portugalskiego europejskiego, który przygotowuje materiał dla polskiego ucznia.

{rules}

Zasady doboru materiału:
- Każda pozycja to słowo, utarty zwrot albo całe zdanie — realnie używane, nie słownikowa ciekawostka.
- Przy rzeczowniku zawsze podaj rodzajnik określony („o" / „a") i rodzaj („m" / „f"). To nie jest pole opcjonalne dla rzeczownika.
- W polu `pt` nie umieszczaj rodzajnika — on ma własne pole.
- Do każdej pozycji dołącz jedno krótkie zdanie przykładowe po portugalsku wraz z tłumaczeniem na polski. Zdanie ma pokazywać hasło w użyciu, a nie je definiować.
- Tłumaczenie polskie ma brzmieć jak polski, a nie jak kalka: „casa de banho" to „łazienka", nie „dom kąpieli".
- Poziom CEFR ustaw uczciwie względem trudności hasła, nie względem tego, o co poprosił użytkownik.
- Notatkę dodaj tylko wtedy, gdy naprawdę coś wnosi: różnicę wobec brazylijskiego, fałszywego przyjaciela z polskim albo nieoczywistą wymowę.
- Nie powtarzaj pozycji ani nie podawaj dwóch wariantów tego samego hasła."""

EXPLAIN_SYSTEM = """Jesteś lektorem portugalskiego europejskiego. Uczeń odpowiedział źle i pyta dlaczego.

{rules}

Odpowiadasz po polsku, maksymalnie dwoma zdaniami. Mówisz, na czym konkretnie polega różnica między jego odpowiedzią a poprawną — bez powtarzania pytania, bez pocieszania, bez wstępu. Jeśli jego odpowiedź jest poprawnym słowem brazylijskim, powiedz to wprost i podaj wersję używaną w Portugalii."""

GRADE_SYSTEM = """Jesteś lektorem portugalskiego europejskiego, który ocenia tłumaczenie ucznia z polskiego na portugalski.

{rules}

Oceniasz w skali 0-100. Liczy się przekazanie sensu i poprawność gramatyczna; drobna literówka nie zabiera więcej niż kilka punktów, użycie słowa brazylijskiego zamiast europejskiego owszem. Zdanie może być poprawne inaczej niż wzorzec — jeśli jest poprawne po europejsku, ma dostać wysoką ocenę. Feedback po polsku, maksymalnie dwa zdania, o tym co poprawić."""

EXAMPLES_SYSTEM = """Jesteś lektorem portugalskiego europejskiego.

{rules}

Układasz krótkie zdania przykładowe pokazujące podane hasło w codziennym użyciu, każde z tłumaczeniem na polski. Zdanie ma być na tyle proste, żeby uczeń na tym poziomie je zrozumiał, i pokazywać hasło w naturalnym kontekście, a nie je definiować."""


# ── silnik ────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Completion:
    data: dict
    input_tokens: int
    output_tokens: int
    model: str


class Engine(Protocol):
    name: str

    def complete(
        self, *, system: str, prompt: str, schema: type[BaseModel], effort: str, max_tokens: int
    ) -> Completion: ...


class AnthropicEngine:
    """Anthropic Messages API przez oficjalny SDK.

    Wyjście jest wymuszone schematem (`output_format`), więc odpowiedź wraca
    jako zwalidowany obiekt Pydantic, a nie jako tekst do sparsowania. To
    usuwa całą klasę błędów „model dopisał zdanie przed nawiasem klamrowym".
    """

    name = "anthropic"

    def __init__(self, api_key: str, model: str) -> None:
        import anthropic

        self._anthropic = anthropic
        self.model = model
        self.client = anthropic.Anthropic(api_key=api_key, timeout=TIMEOUT_SECONDS)

    def complete(
        self, *, system: str, prompt: str, schema: type[BaseModel], effort: str, max_tokens: int
    ) -> Completion:
        anthropic = self._anthropic
        try:
            response = self.client.messages.parse(
                model=self.model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": prompt}],
                thinking={"type": "adaptive"},
                output_config={"effort": effort},
                output_format=schema,
            )
        except anthropic.AuthenticationError as exc:
            raise AIError("Klucz API Anthropic został odrzucony.") from exc
        except anthropic.RateLimitError as exc:
            raise AIError("Anthropic chwilowo ogranicza żądania. Spróbuj za chwilę.") from exc
        except anthropic.APITimeoutError as exc:
            raise AIError("Model nie odpowiedział na czas. Spróbuj z mniejszą liczbą pozycji.") from exc
        except anthropic.APIConnectionError as exc:
            raise AIError(f"Nie udało się połączyć z Anthropic: {exc}") from exc
        except anthropic.APIStatusError as exc:
            raise AIError(f"Anthropic odpowiedział błędem (HTTP {exc.status_code}).") from exc

        usage = response.usage
        tokens = (
            int(getattr(usage, "input_tokens", 0) or 0),
            int(getattr(usage, "output_tokens", 0) or 0),
        )

        if response.stop_reason == "refusal":
            raise AIRefused("Model odmówił odpowiedzi na tę prośbę. Spróbuj sformułować ją inaczej.")
        if response.stop_reason == "max_tokens":
            raise AIError("Odpowiedź nie zmieściła się w limicie. Poproś o mniej pozycji naraz.")

        parsed = response.parsed_output
        if parsed is None:
            raise AIError("Model zwrócił odpowiedź w nieoczekiwanym formacie.")

        return Completion(
            data=parsed.model_dump(),
            input_tokens=tokens[0],
            output_tokens=tokens[1],
            model=response.model or self.model,
        )


def is_configured() -> bool:
    return bool(settings.anthropic_api_key)


def get_engine() -> Engine:
    if not is_configured():
        raise AINotConfigured(
            "Funkcje AI nie są skonfigurowane — brakuje zmiennej ANTHROPIC_API_KEY."
        )
    return AnthropicEngine(settings.anthropic_api_key, settings.ai_model)


# ── koszt i budżet ────────────────────────────────────────────────────────
def cost_of(model: str, input_tokens: int, output_tokens: int) -> Decimal:
    price_in, price_out = MODEL_PRICES.get(model, FALLBACK_PRICE)
    total = (input_tokens * price_in + output_tokens * price_out) / 1_000_000
    return Decimal(f"{total:.6f}")


def _month_start(now: datetime | None = None) -> datetime:
    now = now or datetime.now(timezone.utc)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def spend_this_month(db: Session, now: datetime | None = None) -> Decimal:
    total = db.execute(
        select(func.coalesce(func.sum(AiJob.cost_usd), 0)).where(AiJob.created_at >= _month_start(now))
    ).scalar_one()
    return Decimal(str(total))


def usage(db: Session, now: datetime | None = None) -> dict:
    spent = spend_this_month(db, now)
    budget = Decimal(str(settings.ai_monthly_budget_usd))
    calls = db.execute(
        select(func.count(AiJob.id)).where(AiJob.created_at >= _month_start(now))
    ).scalar_one()
    return {
        "configured": is_configured(),
        "model": settings.ai_model,
        "spent_usd": float(spent),
        "budget_usd": float(budget),
        "remaining_usd": float(max(budget - spent, Decimal("0"))),
        "calls_this_month": int(calls),
        "over_budget": spent >= budget,
    }


def check_budget(db: Session) -> None:
    if spend_this_month(db) >= Decimal(str(settings.ai_monthly_budget_usd)):
        raise AIBudgetReached(
            "Miesięczny budżet na funkcje AI został wyczerpany. "
            "Nauka i wymowa działają dalej, a limit odnowi się pierwszego dnia miesiąca."
        )


# ── wywołanie z zapisem kosztu ────────────────────────────────────────────
REPAIR_NOTE = (
    "\n\nPoprzednia odpowiedź nie spełniła wymagań: {problem}. "
    "Odpowiedz jeszcze raz, tym razem trzymając się schematu i zasad co do joty."
)


def run(
    db: Session,
    *,
    user: User | None,
    kind: str,
    system: str,
    prompt: str,
    schema: type[BaseModel],
    effort: str = "medium",
    max_tokens: int = MAX_TOKENS_SHORT,
    engine: Engine | None = None,
    validate: Callable[[Any], None] | None = None,
) -> tuple[BaseModel, AiJob]:
    """Woła model, zapisuje koszt i zwraca zwalidowaną odpowiedź.

    `validate` dostaje sparsowany obiekt i podnosi `ValueError`, gdy odpowiedź
    jest formalnie poprawna, ale merytorycznie nie do przyjęcia (np. pusty
    zestaw). Wtedy — i tylko wtedy — idzie jedna próba naprawcza z opisem
    problemu; druga porażka kończy się `failed`, bo trzecie wywołanie kosztuje
    tyle samo co dwa pierwsze razem wzięte i rzadko coś zmienia.
    """
    check_budget(db)
    worker = engine or get_engine()

    attempt_prompt = prompt
    last_problem = ""
    job: AiJob | None = None

    for attempt in (1, 2):
        try:
            completion = worker.complete(
                system=system,
                prompt=attempt_prompt,
                schema=schema,
                effort=effort,
                max_tokens=max_tokens,
            )
        except AIError as exc:
            # Nieudane wywołanie też zostawia ślad — tokeny wejściowe zostały
            # policzone przez dostawcę, nawet jeśli nic sensownego nie wróciło.
            db.add(
                AiJob(
                    user_id=user.id if user else None,
                    kind=kind,
                    status="failed",
                    model=settings.ai_model,
                    prompt=prompt[:4000],
                    error=str(exc),
                )
            )
            db.commit()
            raise

        job = AiJob(
            user_id=user.id if user else None,
            kind=kind,
            status="ready",
            model=completion.model,
            prompt=prompt[:4000],
            input_tokens=completion.input_tokens,
            output_tokens=completion.output_tokens,
            cost_usd=cost_of(completion.model, completion.input_tokens, completion.output_tokens),
        )
        db.add(job)
        db.flush()

        try:
            parsed = schema.model_validate(completion.data)
            if validate is not None:
                validate(parsed)
        except (ValueError, TypeError) as exc:
            last_problem = str(exc)[:300]
            job.status = "failed"
            job.error = last_problem
            db.commit()
            if attempt == 2:
                break
            attempt_prompt = prompt + REPAIR_NOTE.format(problem=last_problem)
            continue

        job.result = completion.data
        db.commit()
        return parsed, job

    raise AIError(f"Model nie zwrócił poprawnej odpowiedzi. Powód: {last_problem or 'nieznany'}")


# ── pamięć podręczna odpowiedzi ───────────────────────────────────────────
def cache_key(kind: str, *parts: str) -> str:
    raw = "|".join([kind, *(" ".join(p.split()).strip().lower() for p in parts)])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def cached(db: Session, key: str) -> dict | None:
    entry = db.execute(select(AiCacheEntry).where(AiCacheEntry.cache_key == key)).scalar_one_or_none()
    return dict(entry.payload) if entry is not None else None


def remember(db: Session, key: str, kind: str, payload: dict) -> None:
    if cached(db, key) is not None:
        return
    db.add(AiCacheEntry(cache_key=key, kind=kind, payload=payload))
    db.flush()


# ── konkretne zadania ─────────────────────────────────────────────────────
def describe_item(item: Item) -> str:
    """Pozycja opisana tak, jak widzi ją uczeń — z rodzajnikiem i przykładem."""
    lines = [f"Hasło portugalskie: {item.display_pt}", f"Znaczenie po polsku: {item.pl}"]
    if item.part_of_speech:
        lines.append(f"Część mowy: {item.part_of_speech}")
    if item.notes:
        lines.append(f"Notatka: {item.notes}")
    if item.examples:
        lines.append(f"Zdanie przykładowe: {item.examples[0].pt}")
    return "\n".join(lines)


def generate_set(
    db: Session,
    user: User,
    *,
    topic: str,
    count: int,
    level: str,
    engine: Engine | None = None,
    avoid: list[str] | None = None,
) -> tuple[GeneratedSet, AiJob]:
    """Zestaw propozycji na zadany temat. Nic nie trafia jeszcze do słownika."""
    lines = [
        f"Przygotuj {count} pozycji do nauki na temat: {topic}",
        f"Docelowy poziom: {level}.",
    ]
    if avoid:
        # Słowa, które uczeń już ma. Wysłanie ich do modelu jest tańsze niż
        # wygenerowanie duplikatów i odrzucenie ich po fakcie — a przy okazji
        # zestaw wychodzi pełny, zamiast skurczyć się o połowę na przeglądzie.
        joined = ", ".join(avoid[:150])
        lines.append(f"Pomiń hasła, które uczeń już zna: {joined}.")
    prompt = "\n".join(lines)

    def check(result: GeneratedSet) -> None:
        if len(result.items) == 0:
            raise ValueError("zestaw był pusty")
        seen = {(i.pt.strip().lower(), i.pl.strip().lower()) for i in result.items}
        if len(seen) != len(result.items):
            raise ValueError("zestaw zawierał powtórzone pozycje")
        for entry in result.items:
            if entry.part_of_speech == "noun" and not (entry.article and entry.gender):
                raise ValueError("rzeczownik " + entry.pt + " bez rodzajnika lub rodzaju")

    result, job = run(
        db,
        user=user,
        kind="set",
        system=SET_SYSTEM.format(rules=pt_pt_rules()),
        prompt=prompt,
        schema=GeneratedSet,
        # Dobór słownictwa i sprawdzenie każdej pozycji pod kątem wariantu to
        # praca, na której warto dać modelowi pomyśleć — to jedyne wywołanie,
        # które ląduje w bazie na stałe.
        effort="high",
        max_tokens=MAX_TOKENS_SET,
        engine=engine,
        validate=check,
    )
    return result, job  # type: ignore[return-value]


def explain_mistake(
    db: Session,
    user: User,
    *,
    item: Item,
    user_answer: str,
    expected: str,
    engine: Engine | None = None,
) -> tuple[dict, bool]:
    """„Dlaczego źle?" — dwa zdania po polsku, liczone raz na pomyłkę."""
    key = cache_key("explain", str(item.id), user_answer, expected)
    hit = cached(db, key)
    if hit is not None:
        return hit, True

    prompt = (
        f"{describe_item(item)}\n"
        f"Poprawna odpowiedź: {expected}\n"
        f"Odpowiedź ucznia: {user_answer}\n\n"
        "Wyjaśnij, na czym polega różnica."
    )
    result, _ = run(
        db,
        user=user,
        kind="explain",
        system=EXPLAIN_SYSTEM.format(rules=pt_pt_rules()),
        prompt=prompt,
        schema=Explanation,
        effort="low",
        engine=engine,
    )
    payload = result.model_dump()
    remember(db, key, "explain", payload)
    db.commit()
    return payload, False


def grade_translation(
    db: Session,
    user: User,
    *,
    prompt_pl: str,
    expected_pt: str,
    user_answer: str,
    engine: Engine | None = None,
) -> tuple[dict, bool]:
    key = cache_key("grade", prompt_pl, expected_pt, user_answer)
    hit = cached(db, key)
    if hit is not None:
        return hit, True

    prompt = (
        f"Zdanie po polsku: {prompt_pl}\n"
        f"Wersja wzorcowa po portugalsku: {expected_pt}\n"
        f"Tłumaczenie ucznia: {user_answer}\n\n"
        "Oceń tłumaczenie ucznia."
    )
    result, _ = run(
        db,
        user=user,
        kind="grade",
        system=GRADE_SYSTEM.format(rules=pt_pt_rules()),
        prompt=prompt,
        schema=TranslationGrade,
        effort="low",
        engine=engine,
    )
    payload = result.model_dump()
    remember(db, key, "grade", payload)
    db.commit()
    return payload, False


def make_examples(
    db: Session,
    user: User,
    *,
    item: Item,
    count: int = 2,
    engine: Engine | None = None,
) -> tuple[list[dict], bool]:
    key = cache_key("examples", str(item.id), str(count))
    hit = cached(db, key)
    if hit is not None:
        return list(hit.get("examples", [])), True

    prompt = (
        f"{describe_item(item)}\n\n"
        f"Ułóż {count} zdania przykładowe z tym hasłem, odpowiednie dla poziomu {item.cefr_level}."
    )

    def check(result: ExampleSet) -> None:
        if not result.examples:
            raise ValueError("brak zdań")

    result, _ = run(
        db,
        user=user,
        kind="examples",
        system=EXAMPLES_SYSTEM.format(rules=pt_pt_rules()),
        prompt=prompt,
        schema=ExampleSet,
        effort="low",
        engine=engine,
        validate=check,
    )
    payload = result.model_dump()
    remember(db, key, "examples", payload)
    db.commit()
    return list(payload["examples"]), False
