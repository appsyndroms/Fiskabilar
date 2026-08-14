"""
Gemensam filtreringslogik som alla scrapers kör sina råa resultat genom.
"""

import re

from config import (
    ARSMODELL_MIN, ARSMODELL_MAX, MAX_MIL, BILAR, UTESLUT_SKADAD,
    HYRBIL_NYCKELORD, SELEKT_NYCKELORD,
)

# Snabbuppslag: (marke_slug, modell_slug) -> giltiga variantnamn, för
# matchar_grundkrav(). Byggs en gång vid import.
_GILTIGA_VARIANTER_PER_BIL = {
    (b["marke_slug"], b["modell_slug"]): set(b["variant_kraven"].keys())
    for b in BILAR
}


def matchar_grundkrav(bil: dict) -> bool:
    nyckel = (bil.get("marke_slug"), bil.get("modell_slug"))
    giltiga_varianter = _GILTIGA_VARIANTER_PER_BIL.get(nyckel)
    if giltiga_varianter is None or bil.get("variant") not in giltiga_varianter:
        return False
    ar = bil.get("arsmodell")
    if ar is None or not (ARSMODELL_MIN <= ar <= ARSMODELL_MAX):
        return False
    if bil.get("miltal") is None or bil["miltal"] > MAX_MIL:
        return False
    if bil.get("vaxellada", "Automat") != "Automat":
        return False
    if UTESLUT_SKADAD and bil.get("skadad"):
        return False
    return True


def identifiera_variant(bilkonfig: dict, text: str) -> str | None:
    """
    Går igenom variant_kraven för en bilkonfig (se config.BILAR) och
    returnerar namnet på FÖRSTA varianten där ALLA regex-mönster
    matchar den givna texten (t.ex. annonstiteln eller URL-sluggen).
    Returnerar None om ingen variant matchar.
    """
    text_lower = (text or "").lower()
    for variantnamn, monster in bilkonfig["variant_kraven"].items():
        if all(re.search(m, text_lower, re.IGNORECASE) for m in monster):
            return variantnamn
    return None


def berika_fran_fritext(bil: dict, fritext: str) -> dict:
    """Härleder fält som hyrbil/Selekt/stor batteri m.m. ur annonsens
    fritext, som fallback när sajten inte har strukturerade fält."""
    text = (fritext or "").lower()

    if bil.get("hyrbil") is None:
        bil["hyrbil"] = any(ord in text for ord in HYRBIL_NYCKELORD)

    if bil.get("volvo_selekt") is None:
        bil["volvo_selekt"] = any(ord in text for ord in SELEKT_NYCKELORD)

    if bil.get("stor_batteri") is None:
        # 2022/2023 T6/T8 med större batteri brukar nämna "18,8 kWh"
        bil["stor_batteri"] = "18,8" in text or "18.8" in text

    if bil.get("dragkrok") is None:
        bil["dragkrok"] = "dragkrok" in text

    if bil.get("varmare") is None:
        bil["varmare"] = "värmare" in text or "kupévärmare" in text or "motorvärmare" in text

    return bil
