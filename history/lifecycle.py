"""
Annonsens livscykel i Fiskabilar.

Ansvarar för:

- identifiera aktuell annonsstatus
- upptäcka prisändringar
- upptäcka återkomster
- upptäcka försvunna annonser
- beräkna tid mellan observationer
- sammanställa ett fordons livscykel
- berika aktuell bil med livscykeldata

Lagring sker via analysis_storage.py.
Den här modulen skriver ingen egen historik.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

from .identity import (
    canonical_vehicle_id,
    resolve_vehicle_id,
)


TIDSZON = ZoneInfo(
    "Europe/Stockholm"
)


# ---------------------------------------------------------------------------
# STATUS
# ---------------------------------------------------------------------------

STATUS_NY = "NY"
STATUS_AKTIV = "AKTIV"
STATUS_PRISSANKT = "PRISSANKT"
STATUS_PRISHOJD = "PRISHOJD"
STATUS_ATERKOMMEN = "ATERKOMMEN"
STATUS_FORSVUNNEN = "FORSVUNNEN"


# ---------------------------------------------------------------------------
# HJÄLPFUNKTIONER
# ---------------------------------------------------------------------------

def _parse_tid(
    value,
) -> datetime | None:
    """
    Tolkar en historiktid.

    Accepterar både tidszonssatta och äldre naiva timestamps.
    """

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


def _sortera_observationer(
    observationer: list[dict],
) -> list[dict]:
    """
    Sorterar observationer kronologiskt.
    """

    return sorted(
        observationer,
        key=lambda post:
        post.get("tid") or "",
    )


def _pris(
    post: dict,
):
    """
    Returnerar numeriskt pris eller None.
    """

    value = post.get(
        "pris"
    )

    if isinstance(
        value,
        (int, float),
    ):
        return value

    return None


def _fordonsnyckel(
    bil: dict,
) -> str | None:
    """
    Returnerar canonical vehicle_id.
    """

    vehicle_id = resolve_vehicle_id(
        bil
    )

    if not vehicle_id:
        return None

    return canonical_vehicle_id(
        vehicle_id
    )


# ---------------------------------------------------------------------------
# LIVSCYKEL
# ---------------------------------------------------------------------------

def analysera_livscykel(
    annonser: list[dict],
    aktuell_tid: datetime | None = None,
) -> dict:
    """
    Analyserar ett fordons historiska annonsobservationer.

    Returnerar en sammanfattning av fordonets livscykel.

    Exempel:

    {
        "status": "PRISSANKT",
        "observationer": 8,
        "forsta_observation": "...",
        "senaste_observation": "...",
        "forsta_pris": 429900,
        "senaste_pris": 399900,
        "prisforandring": -30000,
        "prisfall": 30000,
        "prissankningar": 2,
        "prishojningar": 0,
        "aterkomster": 0,
        "forsta_observation_dagar": 6
    }
    """

    aktuell_tid = (
        aktuell_tid
        or datetime.now(TIDSZON)
    )

    observationer = _sortera_observationer(
        list(annonser or [])
    )

    if not observationer:
        return {
            "status": STATUS_NY,
            "observationer": 0,
            "forsta_observation": None,
            "senaste_observation": None,
            "forsta_pris": None,
            "senaste_pris": None,
            "prisforandring": 0,
            "prisfall": 0,
            "prishojning": 0,
            "prissankningar": 0,
            "prishojningar": 0,
            "aterkomster": 0,
            "forsvunnen": False,
            "historik_dagar": 0,
        }

    forsta = observationer[0]
    senaste = observationer[-1]

    priser = [
        _pris(post)
        for post in observationer
        if _pris(post) is not None
    ]

    forsta_pris = (
        priser[0]
        if priser
        else None
    )

    senaste_pris = (
        priser[-1]
        if priser
        else None
    )

    prisforandring = 0
    prisfall = 0
    prishojning = 0

    if (
        forsta_pris is not None
        and senaste_pris is not None
    ):
        prisforandring = (
            senaste_pris
            - forsta_pris
        )

        prisfall = max(
            0,
            forsta_pris
            - senaste_pris,
        )

        prishojning = max(
            0,
            senaste_pris
            - forsta_pris,
        )

    prissankningar = 0
    prishojningar = 0

    storsta_prissankning = 0
    storsta_prishojning = 0

    tidigare_pris = None

    for post in observationer:

        pris = _pris(post)

        if pris is None:
            continue

        if tidigare_pris is not None:

            diff = pris - tidigare_pris

            if diff < 0:
                prissankningar += 1

                storsta_prissankning = max(
                    storsta_prissankning,
                    abs(diff),
                )

            elif diff > 0:
                prishojningar += 1

                storsta_prishojning = max(
                    storsta_prishojning,
                    diff,
                )

        tidigare_pris = pris

    forsta_tid = _parse_tid(
        forsta.get("tid")
    )

    senaste_tid = _parse_tid(
        senaste.get("tid")
    )

    historik_dagar = 0

    if forsta_tid:
        historik_dagar = max(
            0,
            (
                aktuell_tid
                - forsta_tid
            ).days,
        )

    # Återkomst kräver minst ett längre glapp mellan
    # observationer. Detta skyddar mot att en missad
    # observation i en enskild körning felaktigt tolkas
    # som att bilen försvunnit och återkommit.
    aterkomster = 0

    tidigare_tid = None

    for post in observationer:

        tid = _parse_tid(
            post.get("tid")
        )

        if (
            tidigare_tid
            and tid
        ):
            dagar = (
                tid
                - tidigare_tid
            ).days

            if dagar >= 2:
                aterkomster += 1

        if tid:
            tidigare_tid = tid

    # En bil betraktas inte som försvunnen bara för att den
    # saknas i aktuell körning. Själva försvinnandet måste
    # bestämmas mot aktuell körning av den som använder
    # livscykelanalysen.
    status = STATUS_AKTIV

    if len(observationer) == 1:
        status = STATUS_NY

    elif prissankningar > 0:
        status = STATUS_PRISSANKT

    elif prishojningar > 0:
        status = STATUS_PRISHOJD

    return {
        "status": status,

        "observationer": len(
            observationer
        ),

        "forsta_observation": (
            forsta.get("tid")
        ),

        "senaste_observation": (
            senaste.get("tid")
        ),

        "forsta_pris": forsta_pris,

        "senaste_pris": senaste_pris,

        "prisforandring": (
            prisforandring
        ),

        "prisfall": (
            prisfall
        ),

        "prishojning": (
            prishojning
        ),

        "prissankningar": (
            prissankningar
        ),

        "prishojningar": (
            prishojningar
        ),

        "storsta_prissankning": (
            storsta_prissankning
        ),

        "storsta_prishojning": (
            storsta_prishojning
        ),

        "aterkomster": (
            aterkomster
        ),

        "forsvunnen": False,

        "historik_dagar": (
            historik_dagar
        ),
    }


# ---------------------------------------------------------------------------
# FÖRSVINNANDE / ÅTERKOMST
# ---------------------------------------------------------------------------

def bedom_forsvunnen(
    annonser: list[dict],
    aktuell_tid: datetime | None = None,
    grans_dagar: int = 2,
) -> bool:
    """
    Avgör om ett fordon inte har observerats på minst
    grans_dagar.

    Detta används när aktuell körning jämförs med historiken.
    """

    if not annonser:
        return False

    aktuell_tid = (
        aktuell_tid
        or datetime.now(TIDSZON)
    )

    senaste = max(
        annonser,
        key=lambda post:
        post.get("tid") or "",
    )

    senaste_tid = _parse_tid(
        senaste.get("tid")
    )

    if not senaste_tid:
        return False

    return (
        aktuell_tid
        - senaste_tid
    ).days >= grans_dagar


def markera_forsvunnen(
    livscykel: dict,
) -> dict:
    """
    Markerar en befintlig livscykel som försvunnen.
    """

    resultat = dict(
        livscykel
    )

    resultat[
        "status"
    ] = STATUS_FORSVUNNEN

    resultat[
        "forsvunnen"
    ] = True

    return resultat


def markera_aterkommen(
    livscykel: dict,
) -> dict:
    """
    Markerar ett fordon som återkommet.
    """

    resultat = dict(
        livscykel
    )

    resultat[
        "status"
    ] = STATUS_ATERKOMMEN

    resultat[
        "aterkommen"
    ] = True

    return resultat


# ---------------------------------------------------------------------------
# HISTORIKINDEX
# ---------------------------------------------------------------------------

def bygg_livscykelindex(
    historikindex: dict[str, dict],
) -> dict[str, dict]:
    """
    Bygger ett livscykelindex från det befintliga
    historikindexet.

    Ingen ny historik läses från disk här.
    """

    resultat = {}

    for vehicle_id, data in (
        historikindex or {}
    ).items():

        annonser = list(
            (
                data
                or {}
            ).get(
                "annonser"
            )
            or []
        )

        livscykel = analysera_livscykel(
            annonser
        )

        resultat[
            vehicle_id
        ] = livscykel

    return resultat


# ---------------------------------------------------------------------------
# AKTUELL BIL
# ---------------------------------------------------------------------------

def berakna_livscykel(
    bil: dict,
    historikindex: dict[str, dict],
) -> dict:
    """
    Beräknar livscykeldata för en aktuell bil.

    Om bilen saknar historik betraktas den som NY.
    """

    vehicle_id = _fordonsnyckel(
        bil
    )

    if not vehicle_id:
        return analysera_livscykel(
            []
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

    livscykel = analysera_livscykel(
        annonser
    )

    return livscykel


def berika_med_livscykel(
    bil: dict,
    historikindex: dict[str, dict],
) -> dict:
    """
    Lägger livscykeldata direkt på bilobjektet.

    Påverkar inte score eller valuation.
    """

    livscykel = berakna_livscykel(
        bil,
        historikindex,
    )

    bil[
        "livscykel"
    ] = livscykel

    return bil


# ---------------------------------------------------------------------------
# DIAGNOSTIK
# ---------------------------------------------------------------------------

def livscykel_diagnostik(
    bil: dict,
    historikindex: dict[str, dict],
) -> str:
    """
    Returnerar en kort diagnostikrad för loggning.
    """

    livscykel = berakna_livscykel(
        bil,
        historikindex,
    )

    return (
        "[LIVSCYKEL] "
        f"{livscykel.get('status')} | "
        f"observationer={livscykel.get('observationer')} | "
        f"dagar={livscykel.get('historik_dagar')} | "
        f"första pris={livscykel.get('forsta_pris')} | "
        f"senaste pris={livscykel.get('senaste_pris')} | "
        f"prisförändring={livscykel.get('prisforandring')} | "
        f"sänkningar={livscykel.get('prissankningar')} | "
        f"höjningar={livscykel.get('prishojningar')} | "
        f"återkomster={livscykel.get('aterkomster')}"
    )
