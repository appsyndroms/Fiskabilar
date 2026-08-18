"""
Append-only historik för Fiskabilar.

Två huvudtyper av observationer sparas i JSONL:
1. annons - vad marknaden faktiskt visade för en bil vid en viss tidpunkt
2. marknadsvärde - vilket värde modellen räknade fram och vilket underlag
   som användes

Historiken är append-only. Förutom skrivfunktionerna finns här läsning och
indexering av historiken så att aktuell annons kan berikas med tidigare
observationer innan dagens observation sparas.
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
        f.write(
            json.dumps(
                post,
                ensure_ascii=False,
                separators=(",", ":"),
            )
            + "\n"
        )


def spara_annonsobservation(bil: dict) -> None:
    """Sparar en komplett marknadsobservation för aktuell bil."""
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
    """Sparar modellens värdering och styrkan på jämförelseunderlaget."""
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


def _las_observationer() -> list[dict]:
    """Läser historikfilen och ignorerar trasiga enskilda rader."""
    if not os.path.exists(HISTORIK_FIL):
        return []

    observationer = []

    try:
        with open(HISTORIK_FIL, "r", encoding="utf-8") as f:
            for rad in f:
                rad = rad.strip()
                if not rad:
                    continue

                try:
                    post = json.loads(rad)
                except json.JSONDecodeError:
                    continue

                if isinstance(post, dict):
                    observationer.append(post)
    except OSError:
        return []

    return observationer


def bygg_historikindex() -> dict[str, dict]:
    """
    Bygger ett index med tidigare observationer per annonsnyckel.

    Dagens körning har ännu inte sparats när funktionen normalt anropas,
    vilket gör att historikfältet endast beskriver tidigare körningar.
    """
    index: dict[str, dict] = {}

    for post in _las_observationer():
        nyckel = post.get("annons_nyckel")
        if not nyckel:
            continue

        data = index.setdefault(
            nyckel,
            {
                "annonser": [],
                "varderingar": [],
            },
        )

        typ = post.get("typ")

        if typ == "annons":
            data["annonser"].append(post)
        elif typ == "marknadsvarde":
            data["varderingar"].append(post)

    return index


def _parse_tid(value) -> datetime | None:
    if not value:
        return None

    try:
        dt = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=TIDSZON)

    return dt


def berakna_historik(
    bil: dict,
    historikindex: dict[str, dict],
) -> dict:
    """
    Beräknar historiska nyckeltal för aktuell annons.

    Returnerar endast information från tidigare observationer.
    """
    nyckel = _annonsnyckel(bil)
    data = historikindex.get(nyckel) or {}

    annonser = list(data.get("annonser") or [])
    varderingar = list(data.get("varderingar") or [])

    annonser.sort(key=lambda x: x.get("tid") or "")
    varderingar.sort(key=lambda x: x.get("tid") or "")

    priser = [
        post.get("pris")
        for post in annonser
        if isinstance(post.get("pris"), (int, float))
    ]

    historik = {
        "historik_observationer": len(annonser),
        "historik_dagar": 0,
        "historik_forsta_pris": None,
        "historik_senaste_pris": None,
        "historik_prisforandring": 0,
        "historik_prisfall": 0,
        "historik_marknadsvarde": None,
        "historik_marknadsvarde_forandring": None,
        "historik_marknadsvarde_observationer": len(varderingar),
    }

    if annonser:
        historik["historik_forsta_pris"] = priser[0] if priser else None
        historik["historik_senaste_pris"] = priser[-1] if priser else None

        if priser:
            historik["historik_prisforandring"] = (
                priser[-1] - priser[0]
            )
            historik["historik_prisfall"] = max(
                0,
                priser[0] - priser[-1],
            )

        forsta_tid = _parse_tid(annonser[0].get("tid"))
        if forsta_tid:
            nu = datetime.now(TIDSZON)
            historik["historik_dagar"] = max(
                0,
                (nu - forsta_tid).days,
            )

    marknadsvarden = [
        post.get("marknadsvarde")
        for post in varderingar
        if isinstance(post.get("marknadsvarde"), (int, float))
    ]

    if marknadsvarden:
        historik["historik_marknadsvarde"] = marknadsvarden[-1]

        if len(marknadsvarden) >= 2:
            historik["historik_marknadsvarde_forandring"] = (
                marknadsvarden[-1] - marknadsvarden[0]
            )

    return historik


def berika_med_historik(
    bil: dict,
    historikindex: dict[str, dict],
) -> dict:
    """Lägger historikfält på bilens dict utan att mutera historikindex."""
    historik = berakna_historik(bil, historikindex)

    bil.update(historik)

    return bil
