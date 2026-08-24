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
