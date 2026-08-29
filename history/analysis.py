"""
Publikt historik-API för Fiskabilar.

Historiken är uppdelad i:

- analysis_storage.py
    JSONL-lagring, månadsrotation och annons-/värdehistorik.

- analysis_trends.py
    Marknadstrender.

- lifecycle.py
    Annonsens livscykel från första observation till
    prisändringar, försvinnande och eventuell återkomst.

Denna fil fungerar som ett stabilt API för resten av applikationen.
"""

from .analysis_storage import (
    spara_annonsobservation,
    spara_marknadsvardesobservation,
    bygg_historikindex,
    berakna_historik,
)

from .analysis_trends import (
    bygg_marknadstrender,
    berakna_marknadstrend_for_bil,
)

from .lifecycle import (
    analysera_livscykel,
)


def _bygg_prishistorik(
    bil: dict,
    historikindex: dict[str, dict],
) -> list[int | float]:
    """
    Bygger en kompakt prisserie för aktuell bil.

    Historiken kommer från tidigare observationer i historikindexet.
    Dagens annonspris läggs därefter till om det skiljer sig från
    den senast kända prisnivån.

    Upprepade observationer av samma pris visas bara en gång, så att
    mejlet exempelvis kan visa:

        459 000 -> 449 000 -> 439 000 kr

    i stället för samma pris upprepat för varje körning.
    """

    vehicle_id = bil.get(
        "vehicle_id"
    )

    data = (
        historikindex.get(
            vehicle_id
        )
        or {}
    )

    annonser = list(
        data.get(
            "annonser"
        )
        or []
    )

    annonser.sort(
        key=lambda x:
        x.get(
            "tid"
        )
        or ""
    )

    priser: list[int | float] = []

    for post in annonser:
        pris = post.get(
            "pris"
        )

        if not isinstance(
            pris,
            (int, float),
        ):
            continue

        if not priser or pris != priser[-1]:
            priser.append(
                pris
            )

    aktuellt_pris = bil.get(
        "annonspris"
    )

    if isinstance(
        aktuellt_pris,
        (int, float),
    ):
        if not priser or aktuellt_pris != priser[-1]:
            priser.append(
                aktuellt_pris
            )

    return priser


def berika_med_historik(
    bil: dict,
    historikindex: dict[str, dict],
    trender: dict[str, dict] | None = None,
) -> dict:
    """
    Lägger historikfält, marknadstrend och livscykelstatus
    på bilens dict.

    Trendinformationen är diagnostisk och påverkar inte
    100-poängsscoren.

    Lifecycle-informationen är diagnostisk och påverkar inte
    100-poängsscoren eller valuation.

    Trendinformationen skickas normalt in färdigberäknad
    från huvudflödet.

    Om den inte skickas in används ett tomt trendunderlag.

    Viktigt:
    Den här funktionen får inte själv starta trendanalysen.

    Trendanalysen körs explicit en gång från huvudflödet.
    """

    historik = berakna_historik(
        bil,
        historikindex,
    )

    historik[
        "historik_priser"
    ] = _bygg_prishistorik(
        bil,
        historikindex,
    )

    if trender is None:
        trender = {}

    trend = berakna_marknadstrend_for_bil(
        bil,
        trender,
    )

    lifecycle = analysera_livscykel(
        bil,
        historikindex,
    )

    bil.update(
        historik
    )

    bil.update(
        trend
    )

    bil.update(
        lifecycle
    )

    return bil
