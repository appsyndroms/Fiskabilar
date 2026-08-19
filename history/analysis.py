"""
Publikt historik-API för Fiskabilar.

Historiken är uppdelad i:

- analysis_storage.py
    JSONL-lagring, månadsrotation och annons-/värdehistorik.

- analysis_trends.py
    Marknadstrender.

Denna fil fungerar som ett stabilt API för resten av applikationen.
"""

from .analysis_storage import (
    spara_annonsobservation,
    spara_marknadsvardesobservation,
    bygg_historikindex,
    berakna_historik,
)

from .analysis_trends import (
    berakna_marknadstrend_for_bil,
)


def berika_med_historik(
    bil: dict,
    historikindex: dict[str, dict],
    trender: dict[str, dict] | None = None,
) -> dict:
    """
    Lägger historikfält och marknadstrend på bilens dict.

    Trendinformationen är diagnostisk och påverkar inte 100-poängsscoren.

    Trendanalysen ska byggas explicit av huvudflödet exakt en gång per
    körning. Den här funktionen får därför aldrig själv starta trendanalysen.

    Om trender inte skickas in används ett tomt trendunderlag. Det gör att
    historik kan läsas och berikas utan att trendanalysen körs som bieffekt.
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

    bil.update(
        historik
    )

    bil.update(
        trend
    )

    return bil
