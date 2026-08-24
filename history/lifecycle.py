"""
Annonsens livscykel i Fiskabilar.

Ansvarar för att tolka historik för ett fordon som en livscykel:

- första observation
- senaste observation
- antal observationer
- antal observationsdagar
- första och senaste pris
- prisförändringar
- antal dagar på marknaden
- dagar sedan senaste observation
- om annonsen verkar aktiv
- om annonsen verkar ha försvunnit
- om annonsen senare återkommer
- antal tidigare återkomster

Lifecycle-analysen ändrar inte fyndscore eller valuation.

Den bygger enbart på historikindexet och använder samma
canonical vehicle identity som övriga historikfunktioner.
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


# En annons betraktas som aktiv om den har observerats
# inom detta antal dagar.
AKTIVITETSDAGAR = 2


def _parse_tid(
    value,
) -> datetime | None:
    """
    Tolkar en ISO-tidsstämpel.

    Äldre poster utan tidszon behandlas som
    Europe/Stockholm.
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
    Returnerar observationer sorterade kronologiskt.
    """

    return sorted(
        observationer,
        key=lambda post:
        _parse_tid(
            post.get("tid")
        )
        or datetime.min.replace(
            tzinfo=TIDSZON
        ),
    )


def _unika_observationsdagar(
    observationer: list[dict],
) -> int:
    """
    Räknar antal separata kalenderdagar då fordonet
    har observerats.
    """

    dagar = set()

    for post in observationer:

        tid = _parse_tid(
            post.get("tid")
        )

        if tid:
            dagar.add(
                tid.date()
            )

    return len(
        dagar
    )


def _prisforandringar(
    observationer: list[dict],
) -> list[dict]:
    """
    Identifierar faktiska prisförändringar mellan
    konsekutiva observationer.

    Observationer utan numeriskt pris ignoreras.
    """

    resultat = []

    tidigare = None

    for post in observationer:

        pris = post.get(
            "pris"
        )

        if not isinstance(
            pris,
            (int, float),
        ):
            continue

        tid = _parse_tid(
            post.get("tid")
        )

        if tidigare is not None:

            tidigare_pris = tidigare[
                "pris"
            ]

            if pris != tidigare_pris:

                resultat.append(
                    {
                        "tid": (
                            tid.isoformat()
                            if tid
                            else post.get("tid")
                        ),
                        "gammalt_pris": (
                            tidigare_pris
                        ),
                        "nytt_pris": (
                            pris
                        ),
                        "forandring": (
                            pris
                            - tidigare_pris
                        ),
                    }
                )

        tidigare = {
            "pris": pris,
            "tid": tid,
        }

    return resultat


def _detektera_gap(
    observationer: list[dict],
) -> list[dict]:
    """
    Identifierar luckor mellan observationer.

    Ett gap på mer än AKTIVITETSDAGAR innebär att
    annonsen inte observerats under en period.

    Funktionen markerar gapet men antar inte automatiskt
    att bilen är såld.
    """

    resultat = []

    tidigare_tid = None

    for post in observationer:

        tid = _parse_tid(
            post.get("tid")
        )

        if not tid:
            continue

        if tidigare_tid is not None:

            dagar = (
                tid.date()
                - tidigare_tid.date()
            ).days

            if dagar > AKTIVITETSDAGAR:

                resultat.append(
                    {
                        "fran": (
                            tidigare_tid.isoformat()
                        ),
                        "till": (
                            tid.isoformat()
                        ),
                        "dagar": dagar,
                    }
                )

        tidigare_tid = tid

    return resultat


def _hitta_vehicle_id(
    bil: dict,
) -> str | None:
    """
    Hämtar aktuell canonical vehicle_id.

    Samma identity-regler används som i övriga
    historikfunktioner.
    """

    vehicle_id = bil.get(
        "vehicle_id"
    )

    if not vehicle_id:
        vehicle_id = resolve_vehicle_id(
            bil
        )

    if not vehicle_id:
        return None

    return canonical_vehicle_id(
        vehicle_id
    )


def _tomt_resultat(
    status: str,
) -> dict:
    """
    Returnerar ett komplett lifecycle-resultat
    utan observationer.
    """

    return {
        "lifecycle_status": status,

        "lifecycle_observationer": 0,

        "lifecycle_observationsdagar": 0,

        "lifecycle_dagar": 0,

        "lifecycle_forsta_observation": None,

        "lifecycle_senaste_observation": None,

        "lifecycle_dagar_sedan_senaste_observation": None,

        "lifecycle_forsta_pris": None,

        "lifecycle_senaste_pris": None,

        "lifecycle_prisforandring": 0,

        "lifecycle_prisforandringar": [],

        "lifecycle_gap": [],

        "lifecycle_aterkomst": False,

        "lifecycle_antal_aterkomster": 0,
    }


def analysera_livscykel(
    bil: dict,
    historikindex: dict[str, dict],
) -> dict:
    """
    Beräknar livscykelstatus för aktuell bil.

    Resultatet är diagnostiskt och påverkar inte
    score eller valuation.

    Historiken identifieras via canonical vehicle_id,
    vilket gör att äldre identiteter som blivit alias
    till samma fordon samlas korrekt.
    """

    vehicle_id = _hitta_vehicle_id(
        bil
    )

    if not vehicle_id:
        return _tomt_resultat(
            "OKAND"
        )

    bil[
        "vehicle_id"
    ] = vehicle_id

    data = (
        historikindex.get(
            vehicle_id
        )
        or {}
    )

    observationer = _sortera_observationer(
        list(
            data.get(
                "annonser"
            )
            or []
        )
    )

    if not observationer:
        return _tomt_resultat(
            "NY"
        )

    forsta_tid = _parse_tid(
        observationer[0].get(
            "tid"
        )
    )

    senaste_tid = _parse_tid(
        observationer[-1].get(
            "tid"
        )
    )

    nu = datetime.now(
        TIDSZON
    )

    dagar = 0

    if forsta_tid:
        dagar = max(
            0,
            (
                nu
                - forsta_tid
            ).days,
        )

    senaste_dagar = None

    if senaste_tid:
        senaste_dagar = max(
            0,
            (
                nu
                - senaste_tid
            ).days,
        )

    priser = [
        post.get(
            "pris"
        )
        for post in observationer
        if isinstance(
            post.get("pris"),
            (int, float),
        )
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

    prisforandringar = _prisforandringar(
        observationer
    )

    total_prisforandring = 0

    if (
        forsta_pris is not None
        and senaste_pris is not None
    ):
        total_prisforandring = (
            senaste_pris
            - forsta_pris
        )

    gap = _detektera_gap(
        observationer
    )

    aktiv = (
        senaste_dagar is not None
        and senaste_dagar <= AKTIVITETSDAGAR
    )

    antal_aterkomster = len(
        gap
    )

    if aktiv:

        if gap:
            status = "ATERKOMMEN"

        else:
            status = "AKTIV"

    else:

        status = "FORSVUNNEN"

    if senaste_dagar is None:
        status = "OKAND"

    return {
        "lifecycle_status": status,

        "lifecycle_observationer": (
            len(observationer)
        ),

        "lifecycle_observationsdagar": (
            _unika_observationsdagar(
                observationer
            )
        ),

        "lifecycle_dagar": dagar,

        "lifecycle_forsta_observation": (
            forsta_tid.isoformat()
            if forsta_tid
            else None
        ),

        "lifecycle_senaste_observation": (
            senaste_tid.isoformat()
            if senaste_tid
            else None
        ),

        "lifecycle_dagar_sedan_senaste_observation": (
            senaste_dagar
        ),

        "lifecycle_forsta_pris": (
            forsta_pris
        ),

        "lifecycle_senaste_pris": (
            senaste_pris
        ),

        "lifecycle_prisforandring": (
            total_prisforandring
        ),

        "lifecycle_prisforandringar": (
            prisforandringar
        ),

        "lifecycle_gap": (
            gap
        ),

        "lifecycle_aterkomst": (
            status == "ATERKOMMEN"
        ),

        "lifecycle_antal_aterkomster": (
            antal_aterkomster
        ),
    }
