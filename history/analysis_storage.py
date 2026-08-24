"""
Lagring och läsning av Fiskabilars historik.

Ansvarar för:

- vehicle identity
- annonsnycklar
- JSONL-skrivning
- månadsvis filrotation
- migrering av äldre market_history.jsonl
- läsning av alla historikmånader
- historikindex
- historikdiagnostik för enskilda fordon

Trendanalysen ligger separat i analysis_trends.py.
"""

from app_logging.logger import info

import glob
import json
import os
import shutil
from datetime import datetime
from zoneinfo import ZoneInfo

from config import (
    HISTORIK_FIL,
    HISTORIK_KATALOG,
)

from .identity import (
    resolve_vehicle_id,
)


TIDSZON = ZoneInfo(
    "Europe/Stockholm"
)


def _nu() -> str:
    return datetime.now(
        TIDSZON
    ).isoformat(
        timespec="seconds"
    )


def _annonsnyckel(
    bil: dict,
) -> str:
    """
    Canonical historiknyckel.

    Nya observationer använder vehicle_id.

    Äldre nyckelformat finns kvar som fallback för att
    gamla historikposter fortfarande ska kunna läsas.
    """

    vehicle_id = bil.get(
        "vehicle_id"
    )

    if not vehicle_id:
        vehicle_id = resolve_vehicle_id(
            bil
        )

    if vehicle_id:
        bil[
            "vehicle_id"
        ] = vehicle_id

        return str(
            vehicle_id
        )

    regnr = bil.get(
        "regnr"
    )

    if regnr:
        return (
            "reg:"
            f"{str(regnr).upper().replace(' ', '')}"
        )

    for value in (
        bil.get("annons_id"),
        bil.get("url"),
    ):
        if value:
            return str(
                value
            ).strip()

    return (
        f"kal:{str(bil.get('modell') or '').lower()}:"
        f"{bil.get('variant')}:"
        f"{bil.get('arsmodell')}:"
        f"{bil.get('miltal')}:"
        f"{bil.get('annonspris')}"
    )


def _manadsfil() -> str:
    """
    Returnerar aktuell månads historikfil.

    Exempel:

        data/market_history/market_history_2026-08.jsonl
    """

    nu = datetime.now(
        TIDSZON
    )

    return os.path.join(
        HISTORIK_KATALOG,
        f"market_history_{nu:%Y-%m}.jsonl",
    )


def _migrera_legacy() -> None:
    """
    Migrerar den gamla:

        data/market_history/market_history.jsonl

    till aktuell månadsfil.
    """

    legacy = HISTORIK_FIL

    aktuell = _manadsfil()

    if not os.path.exists(
        legacy
    ):
        return

    if os.path.exists(
        aktuell
    ):
        return

    os.makedirs(
        HISTORIK_KATALOG,
        exist_ok=True,
    )

    try:
        shutil.move(
            legacy,
            aktuell,
        )

        info(
            "[HISTORIK] Migrerade legacy-fil till: "
            f"{aktuell}"
        )

    except OSError as e:
        info(
            "[HISTORIK] Kunde inte migrera legacy-fil: "
            f"{e}"
        )


def _historikfiler() -> list[str]:
    os.makedirs(
        HISTORIK_KATALOG,
        exist_ok=True,
    )

    filer = glob.glob(
        os.path.join(
            HISTORIK_KATALOG,
            "market_history_*.jsonl",
        )
    )

    if os.path.exists(
        HISTORIK_FIL
    ):
        filer.append(
            HISTORIK_FIL
        )

    return sorted(
        set(filer)
    )


def _skriv(
    post: dict,
) -> None:
    os.makedirs(
        HISTORIK_KATALOG,
        exist_ok=True,
    )

    _migrera_legacy()

    fil = _manadsfil()

    with open(
        fil,
        "a",
        encoding="utf-8",
    ) as f:
        f.write(
            json.dumps(
                post,
                ensure_ascii=False,
                separators=(
                    ",",
                    ":",
                ),
            )
            + "\n"
        )


def spara_annonsobservation(
    bil: dict,
) -> None:
    """
    Sparar en komplett marknadsobservation.

    vehicle_id är den permanenta identiteten för det fysiska
    fordonet. Annons-ID och URL sparas fortfarande som diagnostik.
    """

    vehicle_id = resolve_vehicle_id(
        bil
    )

    bil[
        "vehicle_id"
    ] = vehicle_id

    post = {
        "typ": "annons",
        "tid": _nu(),

        "vehicle_id": vehicle_id,

        "annons_nyckel": _annonsnyckel(
            bil
        ),

        "annons_id": bil.get(
            "annons_id"
        ),

        "regnr": bil.get(
            "regnr"
        ),

        "vin": bil.get(
            "vin"
        ),

        "modell": bil.get(
            "modell"
        ),

        "variant": bil.get(
            "variant"
        ),

        "arsmodell": bil.get(
            "arsmodell"
        ),

        "miltal": bil.get(
            "miltal"
        ),

        "pris": bil.get(
            "annonspris"
        ),

        "utrustningsniva": bil.get(
            "utrustningsniva"
        ),

        "dragkrok": bool(
            bil.get("dragkrok")
        ),

        "varmare": bool(
            bil.get("varmare")
        ),

        "volvo_selekt": bool(
            bil.get("volvo_selekt")
        ),

        "stor_batteri": bool(
            bil.get("stor_batteri")
        ),

        "kallor": bil.get(
            "kallor",
            [],
        ),

        "url": (
            bil.get("urls")
            or [
                bil.get("url")
            ]
        )[0]
        if (
            bil.get("urls")
            or bil.get("url")
        )
        else None,
    }

    _skriv(
        post
    )


def spara_marknadsvardesobservation(
    bil: dict,
    vardering: dict,
) -> None:
    """
    Sparar modellens värdering.

    Även värdeobservationen kopplas till samma vehicle_id
    som annonsobservationen.
    """

    vehicle_id = resolve_vehicle_id(
        bil
    )

    bil[
        "vehicle_id"
    ] = vehicle_id

    diagnostik = (
        vardering.get(
            "marknadsdiagnostik"
        )
        or {}
    )

    post = {
        "typ": "marknadsvarde",

        "tid": _nu(),

        "vehicle_id": vehicle_id,

        "annons_nyckel": _annonsnyckel(
            bil
        ),

        "modell": bil.get(
            "modell"
        ),

        "variant": bil.get(
            "variant"
        ),

        "arsmodell": bil.get(
            "arsmodell"
        ),

        "miltal": bil.get(
            "miltal"
        ),

        "annonspris": bil.get(
            "annonspris"
        ),

        "marknadsvarde": vardering.get(
            "marknadsvarde"
        ),

        "diff": vardering.get(
            "diff"
        ),

        "fyndprocent": vardering.get(
            "fyndprocent"
        ),

        "jamforelseantal": vardering.get(
            "jamforelseantal"
        ),

        "underlagsstyrka": vardering.get(
            "underlagsstyrka"
        ),

        "median_justerat": diagnostik.get(
            "median_justerat"
        ),
    }

    _skriv(
        post
    )


def _las_observationer() -> list[dict]:
    observationer = []

    for fil in _historikfiler():
        try:
            with open(
                fil,
                "r",
                encoding="utf-8",
            ) as f:

                for rad in f:
                    rad = rad.strip()

                    if not rad:
                        continue

                    try:
                        post = json.loads(
                            rad
                        )

                    except json.JSONDecodeError:
                        continue

                    if isinstance(
                        post,
                        dict,
                    ):
                        observationer.append(
                            post
                        )

        except OSError:
            continue

    return observationer


def bygg_historikindex() -> dict[str, dict]:
    """
    Bygger historikindex.

    Nya poster använder vehicle_id.

    Äldre poster använder annons_nyckel. De läses fortfarande
    så att befintlig historik inte försvinner.
    """

    index: dict[str, dict] = {}

    for post in _las_observationer():

        nyckel = (
            post.get(
                "vehicle_id"
            )
            or post.get(
                "annons_nyckel"
            )
        )

        if not nyckel:
            continue

        data = index.setdefault(
            nyckel,
            {
                "annonser": [],
                "varderingar": [],
            },
        )

        typ = post.get(
            "typ"
        )

        if typ == "annons":
            data[
                "annonser"
            ].append(
                post
            )

        elif typ == "marknadsvarde":
            data[
                "varderingar"
            ].append(
                post
            )

    return index


def _parse_tid(
    value,
) -> datetime | None:
    if not value:
        return None

    try:
        dt = datetime.fromisoformat(
            value
        )

    except (
        TypeError,
        ValueError,
    ):
        return None

    if dt.tzinfo is None:
        dt = dt.replace(
            tzinfo=TIDSZON
        )

    return dt


def berakna_historik(
    bil: dict,
    historikindex: dict[str, dict],
) -> dict:
    """
    Beräknar historiska nyckeltal för aktuell bil.
    """

    vehicle_id = resolve_vehicle_id(
        bil
    )

    bil[
        "vehicle_id"
    ] = vehicle_id

    nyckel = (
        vehicle_id
        or _annonsnyckel(
            bil
        )
    )

    data = (
        historikindex.get(
            nyckel
        )
        or {}
    )

    annonser = list(
        data.get(
            "annonser"
        )
        or []
    )

    varderingar = list(
        data.get(
            "varderingar"
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

    varderingar.sort(
        key=lambda x:
        x.get(
            "tid"
        )
        or ""
    )

    priser = [
        post.get(
            "pris"
        )
        for post in annonser
        if isinstance(
            post.get(
                "pris"
            ),
            (int, float),
        )
    ]

    historik = {
        "historik_observationer": len(
            annonser
        ),
        "historik_dagar": 0,
        "historik_forsta_pris": None,
        "historik_senaste_pris": None,
        "historik_prisforandring": 0,
        "historik_prisfall": 0,
        "historik_marknadsvarde": None,
        "historik_marknadsvarde_forandring": None,
        "historik_marknadsvarde_observationer": len(
            varderingar
        ),
    }

    if annonser:

        historik[
            "historik_forsta_pris"
        ] = (
            priser[0]
            if priser
            else None
        )

        historik[
            "historik_senaste_pris"
        ] = (
            priser[-1]
            if priser
            else None
        )

        if priser:

            historik[
                "historik_prisforandring"
            ] = (
                priser[-1]
                - priser[0]
            )

            historik[
                "historik_prisfall"
            ] = max(
                0,
                priser[0]
                - priser[-1],
            )

        forsta_tid = _parse_tid(
            annonser[0].get(
                "tid"
            )
        )

        if forsta_tid:

            nu = datetime.now(
                TIDSZON
            )

            historik[
                "historik_dagar"
            ] = max(
                0,
                (
                    nu
                    - forsta_tid
                ).days,
            )

    marknadsvarden = [
        post.get(
            "marknadsvarde"
        )
        for post in varderingar
        if isinstance(
            post.get(
                "marknadsvarde"
            ),
            (int, float),
        )
    ]

    if marknadsvarden:

        historik[
            "historik_marknadsvarde"
        ] = (
            marknadsvarden[-1]
        )

        if len(
            marknadsvarden
        ) >= 2:

            historik[
                "historik_marknadsvarde_forandring"
            ] = (
                marknadsvarden[-1]
                - marknadsvarden[0]
            )

    return historik
