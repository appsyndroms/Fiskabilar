"""
Gemensam filtreringslogik som alla scrapers kör sina råa resultat genom.
"""

from config import (
    ARSMODELL_MIN, ARSMODELL_MAX, MAX_MIL, VARIANT_KRAV, UTESLUT_SKADAD,
    HYRBIL_NYCKELORD, SELEKT_NYCKELORD,
)


def matchar_grundkrav(bil: dict) -> bool:
    if bil.get("variant") not in VARIANT_KRAV:
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
