"""
Gemensam filtreringslogik som alla scrapers kör sina råa resultat genom.
"""

import re

from config import (
    ARSMODELL_MIN,
    ARSMODELL_MAX,
    MAX_MIL,
    BILAR,
    UTESLUT_SKADAD,
    HYRBIL_NYCKELORD,
    SELEKT_NYCKELORD,
)


# Snabbuppslag:
# (marke_slug, modell_slug) -> bilkonfiguration
#
# Används bland annat för att hitta rätt årsintervall för varje modell.
_BILKONFIG_PER_BIL = {
    (
        b["marke_slug"],
        b["modell_slug"],
    ): b
    for b in BILAR
}


# Snabbuppslag:
# (marke_slug, modell_slug) -> giltiga variantnamn
_GILTIGA_VARIANTER_PER_BIL = {
    (
        b["marke_slug"],
        b["modell_slug"],
    ): set(b["variant_kraven"].keys())
    for b in BILAR
}


def _hamta_bilkonfig(bil: dict) -> dict | None:
    """
    Hämtar konfigurationen för den bilmodell som annonsen tillhör.
    """

    nyckel = (
        bil.get("marke_slug"),
        bil.get("modell_slug"),
    )

    return _BILKONFIG_PER_BIL.get(nyckel)


def _hamta_arsmodell_intervall(
    bil: dict,
) -> tuple[int, int]:
    """
    Hämtar årsmodellens min/max för den aktuella bilmodellen.

    Om modellen har egna gränser används dessa.
    Annars används de globala standardvärdena.
    """

    bilkonfig = _hamta_bilkonfig(bil)

    if bilkonfig is None:
        return (
            ARSMODELL_MIN,
            ARSMODELL_MAX,
        )

    arsmodell_min = bilkonfig.get(
        "arsmodell_min",
        ARSMODELL_MIN,
    )

    arsmodell_max = bilkonfig.get(
        "arsmodell_max",
        ARSMODELL_MAX,
    )

    return (
        arsmodell_min,
        arsmodell_max,
    )


def grundkrav_fel(
    bil: dict,
) -> list[str]:
    """
    Returnerar en lista med orsaker till att en bil inte klarar
    grundkraven.

    En tom lista betyder att bilen klarar samtliga grundkrav.

    Funktionen används för diagnostik så att vi kan se varför
    kandidater filtreras bort, utan att själva filtreringen behöver
    ändras.
    """

    fel = []

    nyckel = (
        bil.get("marke_slug"),
        bil.get("modell_slug"),
    )

    giltiga_varianter = (
        _GILTIGA_VARIANTER_PER_BIL.get(nyckel)
    )

    if (
        giltiga_varianter is None
        or bil.get("variant") not in giltiga_varianter
    ):
        fel.append(
            "ogiltig variant"
        )

    arsmodell = bil.get(
        "arsmodell"
    )

    arsmodell_min, arsmodell_max = (
        _hamta_arsmodell_intervall(bil)
    )

    if arsmodell is None:
        fel.append(
            "årsmodell saknas"
        )

    elif not (
        arsmodell_min
        <= arsmodell
        <= arsmodell_max
    ):
        fel.append(
            f"årsmodell {arsmodell} "
            f"utanför tillåtet intervall "
            f"{arsmodell_min}-{arsmodell_max}"
        )

    miltal = bil.get(
        "miltal"
    )

    if miltal is None:
        fel.append(
            "miltal saknas"
        )

    elif miltal > MAX_MIL:
        fel.append(
            f"miltal {miltal} "
            f"över MAX_MIL {MAX_MIL}"
        )

    vaxellada = bil.get(
        "vaxellada",
        "Automat",
    )

    if vaxellada != "Automat":
        fel.append(
            f"växellåda '{vaxellada}' "
            f"är inte Automat"
        )

    if (
        UTESLUT_SKADAD
        and bil.get("skadad")
    ):
        fel.append(
            "markerad som skadad"
        )

    return fel


def matchar_grundkrav(
    bil: dict,
) -> bool:
    """
    Returnerar True om bilen klarar samtliga grundkrav.

    Själva filtreringslogiken ligger i grundkrav_fel() så att samma
    regler kan användas både för filtrering och diagnostik.
    """

    return len(
        grundkrav_fel(bil)
    ) == 0


def identifiera_variant(
    bilkonfig: dict,
    text: str,
) -> str | None:
    """
    Går igenom variant_kraven för en bilkonfig och returnerar namnet
    på FÖRSTA varianten där ALLA regex-mönster matchar den givna texten.

    Returnerar None om ingen variant matchar.
    """

    text_lower = (
        text or ""
    ).lower()

    for variantnamn, monster in (
        bilkonfig["variant_kraven"].items()
    ):

        if all(
            re.search(
                m,
                text_lower,
                re.IGNORECASE,
            )
            for m in monster
        ):
            return variantnamn

    return None


def berika_fran_fritext(
    bil: dict,
    fritext: str,
) -> dict:
    """
    Härleder fält som hyrbil/Selekt/stor batteri m.m. ur annonsens
    fritext, som fallback när sajten inte har strukturerade fält.
    """

    text = (
        fritext or ""
    ).lower()

    if bil.get("hyrbil") is None:
        bil["hyrbil"] = any(
            ord in text
            for ord in HYRBIL_NYCKELORD
        )

    if bil.get("volvo_selekt") is None:
        bil["volvo_selekt"] = any(
            ord in text
            for ord in SELEKT_NYCKELORD
        )

    if bil.get("stor_batteri") is None:
        # 2022/2023 T6/T8 med större batteri brukar nämna "18,8 kWh"
        bil["stor_batteri"] = (
            "18,8" in text
            or "18.8" in text
        )

    if bil.get("dragkrok") is None:
        bil["dragkrok"] = (
            "dragkrok" in text
        )

    if bil.get("varmare") is None:
        bil["varmare"] = (
            "värmare" in text
            or "kupévärmare" in text
            or "motorvärmare" in text
        )

    return bil
