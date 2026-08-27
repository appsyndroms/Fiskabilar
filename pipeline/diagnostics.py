"""
Diagnostikutskrifter för Fiskabilar.

Visar:
- bästa fyndkandidater
- historikdiagnostik
- annonsens livscykel

Livscykeldiagnostiken jämför dagens population med
historikindexet och visar:

- NY
- AKTIV
- FÖRSVUNNEN
- ÅTERKOMMEN
"""

from datetime import datetime
from zoneinfo import ZoneInfo

from app_logging.logger import info

from history.lifecycle import (
    AKTIVITETSDAGAR,
)
from history.identity import (
    canonical_vehicle_id,
)


DIAGNOSTIK_ANTAL = 20
LIVSCYKEL_ANTAL = 20

TIDSZON = ZoneInfo(
    "Europe/Stockholm"
)


def _formatera_historikdiagnostik(
    kandidat: dict,
) -> str | None:

    observationer = kandidat.get(
        "historik_observationer",
        0,
    )

    if not observationer:
        return None

    delar = [
        f"Historik: {observationer} obs",
        (
            f"{kandidat.get('historik_dagar', 0)} "
            "dagar"
        ),
    ]

    forsta_pris = kandidat.get(
        "historik_forsta_pris"
    )

    senaste_pris = kandidat.get(
        "historik_senaste_pris"
    )

    prisfall = kandidat.get(
        "historik_prisfall",
        0,
    )

    if isinstance(
        forsta_pris,
        (int, float),
    ):
        delar.append(
            f"första pris "
            f"{forsta_pris:,.0f} kr".replace(
                ",",
                " ",
            )
        )

    if isinstance(
        senaste_pris,
        (int, float),
    ):
        delar.append(
            f"senaste "
            f"{senaste_pris:,.0f} kr".replace(
                ",",
                " ",
            )
        )

    if prisfall:
        delar.append(
            f"prisfall "
            f"{prisfall:,.0f} kr".replace(
                ",",
                " ",
            )
        )

    marknad = kandidat.get(
        "historik_marknadsvarde"
    )

    if isinstance(
        marknad,
        (int, float),
    ):
        delar.append(
            f"historiskt MV "
            f"{marknad:,.0f} kr".replace(
                ",",
                " ",
            )
        )

    return " | ".join(
        delar
    )


def _formatera_miltalsdiagnostik(
    kandidat: dict,
) -> str:

    miltal = kandidat.get(
        "miltal",
        0,
    )

    miltalspoang = kandidat.get(
        "miltalspoang",
        0,
    )

    try:
        miltal = int(miltal)
    except (
        TypeError,
        ValueError,
    ):
        miltal = 0

    try:
        miltalspoang = int(miltalspoang)
    except (
        TypeError,
        ValueError,
    ):
        miltalspoang = 0

    max_poang = 20

    miltalsavdrag = max(
        0,
        max_poang - miltalspoang,
    )

    if miltal >= 10000:
        klass = "MYCKET HÖG MIL"
    elif miltal >= 8000:
        klass = "HÖG MIL"
    elif miltal >= 5000:
        klass = "NORMAL/HÖG MIL"
    else:
        klass = "NORMAL/LÅG MIL"

    return (
        f"Miltal: {miltal:,} mil → "
        f"{miltalspoang}/{max_poang} "
        f"(-{miltalsavdrag} p) | "
        f"{klass}"
    ).replace(
        ",",
        " ",
    )


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


def _canonical_vehicle_id(
    bil: dict,
) -> str | None:

    vehicle_id = bil.get(
        "vehicle_id"
    )

    if not vehicle_id:
        return None

    return canonical_vehicle_id(
        vehicle_id
    )


def _senaste_historiska_tid(
    data: dict,
) -> datetime | None:

    observationer = (
        data.get("annonser")
        or []
    )

    senaste = None

    for observation in observationer:

        tid = _parse_tid(
            observation.get("tid")
        )

        if tid is None:
            continue

        if (
            senaste is None
            or tid > senaste
        ):
            senaste = tid

    return senaste


def _livscykelstatus_for_aktuell_bil(
    bil: dict,
    historikindex: dict[str, dict],
) -> tuple[str, int | None]:

    vehicle_id = _canonical_vehicle_id(
        bil
    )

    if not vehicle_id:
        return (
            "OKÄND",
            None,
        )

    data = (
        historikindex.get(
            vehicle_id
        )
        or {}
    )

    observationer = (
        data.get("annonser")
        or []
    )

    if not observationer:
        return (
            "NY",
            None,
        )

    senaste_tid = _senaste_historiska_tid(
        data
    )

    if senaste_tid is None:
        return (
            "OKÄND",
            None,
        )

    nu = datetime.now(
        TIDSZON
    )

    dagar_sedan = max(
        0,
        (
            nu
            - senaste_tid
        ).days,
    )

    if dagar_sedan <= AKTIVITETSDAGAR:
        return (
            "AKTIV",
            dagar_sedan,
        )

    return (
        "ÅTERKOMMEN",
        dagar_sedan,
    )


def _livscykelrad(
    bil: dict,
    status: str,
    dagar_sedan: int | None,
) -> str:

    modell = (
        bil.get("modell")
        or "Okänd modell"
    )

    arsmodell = bil.get(
        "arsmodell",
        "?",
    )

    miltal = bil.get(
        "miltal",
        0,
    )

    pris = bil.get(
        "annonspris",
        0,
    )

    rubrik = (
        bil.get("variant")
        or bil.get("modell")
        or "Okänd bil"
    )

    extra = ""

    if dagar_sedan is not None:
        extra = (
            f" | senast historiskt "
            f"{dagar_sedan} dagar sedan"
        )

    return (
        f"{status}: "
        f"{arsmodell} | "
        f"{miltal:,} mil | "
        f"{pris:,} kr | "
        f"{modell} | "
        f"{rubrik}"
        f"{extra}"
    ).replace(
        ",",
        " ",
    )


def skriv_livscykel_diagnostik(
    bilar: list[dict],
    historikindex: dict[str, dict],
) -> None:
    """
    Jämför dagens bilar med historiken.

    Viktigt:
    historikindex byggs före dagens observationer sparas.
    Därför används dagens bilar som aktuell population.

    Det gör att vi kan identifiera:

    NY
        Ingen tidigare observation.

    AKTIV
        Finns idag och observerades nyligen.

    ÅTERKOMMEN
        Finns idag men senaste historiska observation
        ligger längre tillbaka än aktivitetsgränsen.

    FÖRSVUNNEN
        Finns i historikindex men finns inte bland
        dagens bilar.
    """

    nu = datetime.now(
        TIDSZON
    )

    aktuella = {}

    for bil in bilar:

        vehicle_id = _canonical_vehicle_id(
            bil
        )

        if not vehicle_id:
            continue

        aktuella[
            vehicle_id
        ] = bil

    grupper = {
        "NY": [],
        "AKTIV": [],
        "FÖRSVUNNEN": [],
        "ÅTERKOMMEN": [],
        "OKÄND": [],
    }

    for bil in bilar:

        vehicle_id = _canonical_vehicle_id(
            bil
        )

        if not vehicle_id:
            grupper[
                "OKÄND"
            ].append(
                bil
            )
            continue

        status, dagar_sedan = (
            _livscykelstatus_for_aktuell_bil(
                bil,
                historikindex,
            )
        )

        grupper[
            status
        ].append(
            (
                bil,
                dagar_sedan,
            )
        )

    # Historikbilar som inte längre finns i dagens
    # population betraktas som försvunna.
    for vehicle_id, data in (
        historikindex.items()
    ):

        canonical_id = canonical_vehicle_id(
            vehicle_id
        )

        if canonical_id in aktuella:
            continue

        senaste_tid = _senaste_historiska_tid(
            data
        )

        if senaste_tid is None:
            continue

        dagar_sedan = max(
            0,
            (
                nu
                - senaste_tid
            ).days,
        )

        # En bil som inte observerats sedan den senaste
        # aktivitetsperioden är försvunnen.
        if dagar_sedan > AKTIVITETSDAGAR:
            grupper[
                "FÖRSVUNNEN"
            ].append(
                (
                    data,
                    dagar_sedan,
                )
            )

    info(
        "\n"
        + "=" * 80
    )

    info(
        "=== ANNONSENS LIVSCYKEL ==="
    )

    info(
        "=" * 80
    )

    info(
        f"NY: {len(grupper['NY'])} | "
        f"AKTIV: {len(grupper['AKTIV'])} | "
        f"FÖRSVUNNEN: {len(grupper['FÖRSVUNNEN'])} | "
        f"ÅTERKOMMEN: {len(grupper['ÅTERKOMMEN'])} | "
        f"OKÄND: {len(grupper['OKÄND'])}"
    )

    for status in (
        "NY",
        "ÅTERKOMMEN",
        "FÖRSVUNNEN",
    ):

        poster = grupper[
            status
        ]

        if not poster:
            continue

        info(
            ""
        )

        info(
            f"--- {status} ---"
        )

        for post in poster[
            :LIVSCYKEL_ANTAL
        ]:

            if status == "FÖRSVUNNEN":

                data, dagar_sedan = post

                observationer = (
                    data.get(
                        "annonser"
                    )
                    or []
                )

                senaste = (
                    observationer[-1]
                    if observationer
                    else {}
                )

                modell = (
                    senaste.get(
                        "modell"
                    )
                    or "Okänd modell"
                )

                pris = senaste.get(
                    "pris",
                    0,
                )

                info(
                    f"FÖRSVUNNEN: "
                    f"{modell} | "
                    f"{pris:,} kr | "
                    f"senast observerad "
                    f"{dagar_sedan} dagar sedan"
                    .replace(
                        ",",
                        " ",
                    )
                )

            else:

                bil, dagar_sedan = post

                info(
                    "    "
                    + _livscykelrad(
                        bil,
                        status,
                        dagar_sedan,
                    )
                )

    info(
        "=" * 80
    )


def skriv_diagnostik(
    kandidater: list[dict],
) -> None:

    if not kandidater:
        info(
            "\n=== DIAGNOSTIK ==="
        )

        info(
            "Inga kandidater passerade valuation."
        )

        return

    kandidater = sorted(
        kandidater,
        key=lambda x: (
            x["score"],
            x["diff"],
        ),
        reverse=True,
    )

    info(
        "\n" + "=" * 80
    )

    info(
        "=== DIAGNOSTIK: BÄSTA KANDIDATER ==="
    )

    info(
        "=" * 80
    )

    for i, kandidat in enumerate(
        kandidater[
            :DIAGNOSTIK_ANTAL
        ],
        1,
    ):
        info(
            f"{i:02d}. "
            f"{kandidat['score']:3d}/100 | "
            f"{kandidat['arsmodell']} | "
            f"{kandidat['miltal']:,} mil | "
            f"{kandidat['pris']:,} kr | "
            f"diff +{kandidat['diff']:,} | "
            f"{kandidat['modell']} | "
            f"{kandidat['utrustning']} | "
            f"{kandidat['status']}"
            .replace(
                ",",
                " ",
            )
        )

        info(
            "    "
            f"Pris: {kandidat['prispoang']}/60 | "
            f"Miltal: {kandidat['miltalspoang']}/20 | "
            f"Utrustning: "
            f"{kandidat['utrustningspoang']}/5 | "
            f"Trygghet: "
            f"{kandidat['trygghetspoang']}/15"
        )

        info(
            "    "
            + _formatera_miltalsdiagnostik(
                kandidat
            )
        )

        historik = (
            _formatera_historikdiagnostik(
                kandidat
            )
        )

        if historik:
            info(
                f"    {historik}"
            )

    info(
        "=" * 80
    )


def skriv_sammanfattning(
    statistik: dict,
) -> None:

    info(
        "\n" + "=" * 70
    )

    info(
        "=== SAMMANFATTNING ==="
    )

    info(
        "=" * 70
    )

    info(
        f"Totalt efter dedup: "
        f"{statistik['totalt']}"
    )

    info(
        f"Leasingannonser stoppade: "
        f"{statistik['leasing_stoppade']}"
    )

    info(
        f"Bilar under "
        f"{statistik['min_miltal']:,} mil stoppade: "
        f"{statistik['miltal_stoppade']}"
        .replace(
            ",",
            " ",
        )
    )

    info(
        f"Valuation OK: "
        f"{statistik['valuation_ok']}"
    )

    info(
        f"Över prisdiff-gränsen "
        f"({statistik['min_diff']:,} kr): "
        f"{statistik['under_diff']}"
        .replace(
            ",",
            " ",
        )
    )

    info(
        f"Score >= "
        f"{statistik['min_score']}: "
        f"{statistik['score_ok']}"
    )

    info(
        f"Redan notifierade: "
        f"{statistik['redan_notifierade']}"
    )

    info(
        f"Mejl skickade: "
        f"{statistik['mejl_skickade']}"
    )

    info(
        "=" * 70
    )
