from france_load_forecast.agent.verify import unsupported

SOURCES = [
    '{"month": "2026-02", "reference": 41.222, "gap": -1.275, "climate": -2.423}',
    '{"coverage": {"all months": 78.934}, "mape": {"4-6 months": 3.539}}',
]


def test_rounded_numbers_are_supported() -> None:
    answer = "Février 2026 : 41,2 TWh prévus, -1,28 TWh d'écart dont -2,4 de climat ; 79 %."

    assert unsupported(answer, SOURCES) == []


def test_signs_are_not_compared() -> None:
    assert unsupported("Elle a baissé de 1,275 TWh, avec un climat à +2,42.", SOURCES) == []


def test_labels_are_not_figures() -> None:
    assert unsupported("La P90 du 1er mois, CO2 compris.", SOURCES) == []


def test_numbers_without_a_source_are_reported() -> None:
    answer = "Entre 4 et 6 mois, l'erreur est de 3,5 %, soit 5,1 % de moins qu'en 2019."

    assert unsupported(answer, SOURCES) == ["5,1", "2019"]


def test_more_decimals_than_the_source_must_still_round_to_it() -> None:
    assert unsupported("Un écart de 1,29 TWh.", SOURCES) == ["1,29"]
