"""
Append-only historik för Fiskabilar.

Två huvudtyper av observationer sparas i JSONL:
1. annons - vad marknaden faktiskt visade för en bil vid en viss tidpunkt
2. marknadsvärde - vilket värde modellen räknade fram och vilket underlag
   som användes

Filen skrivs bara genom att nya rader läggs till. Den påverkas därför inte
av migrationer av state.json och kan senare analyseras för att förbättra
värderingsmodellen.
"""

import json
import os
from datetime import datetime
from zoneinfo import ZoneInfo

from config import HISTORIK_FIL

TIDSZON = ZoneInfo("Europe/Stockholm")


def _nu() -> str:
    return datetime.now(TIDSZON).isoformat(timespec="seconds")


def _annonsnyckel(bil: dict) -> str:
    regnr = bil.get("regnr")
    if regnr:
        return f"reg:{str(regnr).upper().replace(' ', '')}"

    for value in (
        bil.get("annons_id"),
        bil.get("url"),
    ):
        if value:
            return str(value).strip()

    return (
        f"kal:{str(bil.get('modell') or '').lower()}:"
        f"{bil.get('variant')}:{bil.get('arsmodell')}:"
        f"{bil.get('miltal')}:{bil.get('annonspris')}"
    )


def _skriv(post: dict) -> None:
    katalog = os.path.dirname(HISTORIK_FIL)
    if katalog:
        os.makedirs(katalog, exist_ok=True)

    with open(HISTORIK_FIL, "a", encoding="utf-8") as f:
        f.write(json.dumps(post, ensure_ascii=False, separators=(",", ":")) + "\n")


def spara_annonsobservation(bil: dict) -> None:
    """Sparar en komplett marknadsobservation för den aktuella bilen."""
    post = {
        "typ": "annons",
        "tid": _nu(),
        "annons_nyckel": _annonsnyckel(bil),
        "annons_id": bil.get("annons_id"),
        "regnr": bil.get("regnr"),
        "modell": bil.get("modell"),
        "variant": bil.get("variant"),
        "arsmodell": bil.get("arsmodell"),
        "miltal": bil.get("miltal"),
        "pris": bil.get("annonspris"),
        "utrustningsniva": bil.get("utrustningsniva"),
        "dragkrok": bool(bil.get("dragkrok")),
        "varmare": bool(bil.get("varmare")),
        "volvo_selekt": bool(bil.get("volvo_selekt")),
        "stor_batteri": bool(bil.get("stor_batteri")),
        "kallor": bil.get("kallor", []),
        "url": (bil.get("urls") or [bil.get("url")])[0]
        if (bil.get("urls") or bil.get("url"))
        else None,
    }
    _skriv(post)


def spara_marknadsvardesobservation(
    bil: dict,
    vardering: dict,
) -> None:
    """Sparar modellens värdering och styrkan på dess jämförelseunderlag."""
    diagnostik = vardering.get("marknadsdiagnostik") or {}

    post = {
        "typ": "marknadsvarde",
        "tid": _nu(),
        "annons_nyckel": _annonsnyckel(bil),
        "modell": bil.get("modell"),
        "variant": bil.get("variant"),
        "arsmodell": bil.get("arsmodell"),
        "miltal": bil.get("miltal"),
        "annonspris": bil.get("annonspris"),
        "marknadsvarde": vardering.get("marknadsvarde"),
        "diff": vardering.get("diff"),
        "fyndprocent": vardering.get("fyndprocent"),
        "jamforelseantal": vardering.get("jamforelseantal"),
        "underlagsstyrka": vardering.get("underlagsstyrka"),
        "median_justerat": diagnostik.get("median_justerat"),
    }
    _skriv(post)
