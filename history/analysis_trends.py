"""
Trendanalys för Fiskabilar.

Trendanalysen bygger på historiska annonsobservationer.

Den är avsiktligt separerad från 100-poängsscoren och valuation.

En trend kräver flera separata observationsdagar för att flera körningar
under samma dygn inte ska tolkas som en marknadsrörelse.
"""

from app_logging.logger import info

from collections import defaultdict
from datetime import datetime
from statistics import median
from zoneinfo import ZoneInfo

from .analysis_storage import (
    _las_observationer,
    _parse_tid,
)


TIDSZON = ZoneInfo(
    "Europe/Stockholm"
)


# ---------------------------------------------------------------------------
# Trendparametrar
# ---------------------------------------------------------------------------

MIN_TREND_DAGAR = 3

TREND_MIN_FORANDRING_PROCENT = 1.0

MIN_TREND_STEG = 2


def _trendkategori(
    post: dict,
) -> str:
    """
    Skapar en stabil marknadskategori.

    Trend ska inte baseras på enskilda registreringsnummer eftersom vi vill
    se hur marknaden för exempelvis:

        BMW 530e xDrive Touring 2023

    utvecklas över tid.
    """

    modell = str(
        post.get("modell")
        or ""
    ).strip().lower()

    variant = str(
        post.get("variant")
        or ""
    ).strip().lower()

    arsmodell = post.get(
        "arsmodell"
    )

    return (
        f"{modell}|"
        f"{variant}|"
        f"{arsmodell}"
    )


def _observationsdag(
    post: dict,
) -> str | None:
    """Returnerar kalenderdagen för observationen."""

    dt = _parse_tid(
        post.get("tid")
    )

    if not dt:
        return None

    return (
        dt.astimezone(
            TIDSZON
        )
        .date()
        .isoformat()
    )


def _bygg_dagliga_priser(
    observationer: list[dict],
) -> list[dict]:
    """
    Bygger en observation per dag.

    Om samma bilkategori observerats flera gånger samma dag används medianen.
    """

    per_dag: dict[
        str,
        list[float],
    ] = defaultdict(list)

    for post in observationer:
        pris = post.get(
            "pris"
        )

        if not isinstance(
            pris,
            (int, float),
        ):
            continue

        dag = _observationsdag(
            post
        )

        if not dag:
            continue

        per_dag[dag].append(
            float(pris)
        )

    resultat = []

    for dag, priser in sorted(
        per_dag.items()
    ):
        if not priser:
            continue

        resultat.append(
            {
                "dag": dag,
                "pris": median(
                    priser
                ),
                "antal_observationer": len(
                    priser
                ),
            }
        )

    return resultat


def _prisforandring_procent(
    tidigare: float,
    senare: float,
) -> float:
    """Beräknar procentuell förändring."""

    if tidigare <= 0:
        return 0.0

    return (
        (
            senare
            - tidigare
        )
        / tidigare
    ) * 100.0


def _klassificera_riktning(
    forandring_procent: float,
) -> str:
    """Klassificerar prisförändring."""

    if (
        forandring_procent
        >= TREND_MIN_FORANDRING_PROCENT
    ):
        return "upp"

    if (
        forandring_procent
        <= -TREND_MIN_FORANDRING_PROCENT
    ):
        return "ned"

    return "oforandrad"


def _analysera_trendsegment(
    dagliga_priser: list[dict],
) -> dict:
    """
    Identifierar aktuell marknadstrend.

    Kräver:
      - minst MIN_TREND_DAGAR
      - minst MIN_TREND_STEG konsekutiva rörelser
      - varje rörelse över tröskeln
    """

    resultat = {
        "trend": "otillrackligt_underlag",
        "trendstyrka": 0,
        "trendforandring_procent": 0.0,
        "trendforandring_kr": 0.0,
        "trend_start_dag": None,
        "trend_slut_dag": None,
        "trend_observationsdagar": len(
            dagliga_priser
        ),
    }

    if (
        len(dagliga_priser)
        < MIN_TREND_DAGAR
    ):
        return resultat

    riktningar = []

    for tidigare, senare in zip(
        dagliga_priser,
        dagliga_priser[1:],
    ):
        forandring_procent = (
            _prisforandring_procent(
                tidigare["pris"],
                senare["pris"],
            )
        )

        riktningar.append(
            {
                "fran_dag": tidigare[
                    "dag"
                ],
                "till_dag": senare[
                    "dag"
                ],
                "fran_pris": tidigare[
                    "pris"
                ],
                "till_pris": senare[
                    "pris"
                ],
                "forandring_kr": (
                    senare["pris"]
                    - tidigare["pris"]
                ),
                "forandring_procent": (
                    forandring_procent
                ),
                "riktning": (
                    _klassificera_riktning(
                        forandring_procent
                    )
                ),
            }
        )

    if not riktningar:
        return resultat

    aktuell_riktning = (
        riktningar[-1]["riktning"]
    )

    if (
        aktuell_riktning
        == "oforandrad"
    ):
        resultat["trend"] = "stabil"
        return resultat

    konsekutiva = 0

    for steg in reversed(
        riktningar
    ):
        if (
            steg["riktning"]
            == aktuell_riktning
        ):
            konsekutiva += 1
        else:
            break

    if (
        konsekutiva
        < MIN_TREND_STEG
    ):
        resultat["trend"] = "stabil"
        return resultat

    segment = riktningar[
        -konsekutiva:
    ]

    start_pris = segment[
        0
    ]["fran_pris"]

    slut_pris = segment[
        -1
    ]["till_pris"]

    total_forandring_kr = (
        slut_pris
        - start_pris
    )

    if start_pris > 0:
        total_forandring_procent = (
            total_forandring_kr
            / start_pris
        ) * 100.0
    else:
        total_forandring_procent = 0.0

    resultat["trend"] = (
        aktuell_riktning
    )

    resultat[
        "trendstyrka"
    ] = konsekutiva

    resultat[
        "trendforandring_procent"
    ] = total_forandring_procent

    resultat[
        "trendforandring_kr"
    ] = total_forandring_kr

    resultat[
        "trend_start_dag"
    ] = segment[0][
        "fran_dag"
    ]

    resultat[
        "trend_slut_dag"
    ] = segment[-1][
        "till_dag"
    ]

    return resultat


def _formatera_kr(
    value,
) -> str:
    if not isinstance(
        value,
        (int, float),
    ):
        return "?"

    return (
        f"{value:,.0f} kr"
        .replace(",", " ")
    )


def _formatera_procent(
    value,
) -> str:
    if not isinstance(
        value,
        (int, float),
    ):
        return "?"

    return (
        f"{value:+.2f} %"
    )


def _kort_kategori(
    kategori: str,
) -> str:
    delar = kategori.split(
        "|"
    )

    if len(delar) != 3:
        return kategori

    modell, variant, arsmodell = (
        delar
    )

    modell = modell.strip()
    variant = variant.strip()

    if len(variant) > 80:
        variant = (
            variant[:77]
            + "..."
        )

    return (
        f"{modell} | "
        f"{variant} | "
        f"{arsmodell}"
    )


def _logga_trendkategori(
    kategori: str,
    analys: dict,
) -> None:
    trend = analys.get(
        "trend"
    )

    if trend not in (
        "upp",
        "ned",
    ):
        return

    info(
        "[TREND] "
        f"{_kort_kategori(kategori)} | "
        f"{trend.upper()} | "
        f"dagar={analys.get('trend_observationsdagar', 0)} | "
        f"steg={analys.get('trendstyrka', 0)} | "
        f"förändring={_formatera_kr(analys.get('trendforandring_kr', 0))} "
        f"({_formatera_procent(analys.get('trendforandring_procent', 0.0))})"
    )


def _logga_trendsammanfattning(
    trender: dict[str, dict],
) -> None:
    antal_upp = 0
    antal_ned = 0
    antal_stabil = 0
    antal_otillrackligt = 0

    for analys in trender.values():
        trend = analys.get(
            "trend"
        )

        if trend == "upp":
            antal_upp += 1

        elif trend == "ned":
            antal_ned += 1

        elif trend == "stabil":
            antal_stabil += 1

        else:
            antal_otillrackligt += 1

    info(
        "[TREND] Lägesbild: "
        f"UPP={antal_upp} | "
        f"NED={antal_ned} | "
        f"STABIL={antal_stabil} | "
        f"OTILLRÄCKLIGT={antal_otillrackligt}"
    )

    if antal_ned:
        info(
            "[TREND] ⚠ Det finns marknadskategorier "
            "med identifierad prisnedgång."
        )

    if antal_upp:
        info(
            "[TREND] Det finns marknadskategorier "
            "med identifierad prisuppgång."
        )


def bygg_marknadstrender() -> dict[str, dict]:
    """
    Analyserar hela historiken och bygger marknadstrender.

    Trendanalysen påverkar inte score eller valuation.
    """

    observationer = _las_observationer()

    info(
        "[TREND] =================================================="
    )
    info(
        "[TREND] Startar trendanalys."
    )
    info(
        "[TREND] Totalt antal historiska poster: "
        f"{len(observationer)}"
    )

    if not observationer:
        info(
            "[TREND] Ingen historik hittades."
        )
        info(
            "[TREND] Trendanalys avslutad: "
            "otillräckligt underlag."
        )
        info(
            "[TREND] =================================================="
        )
        return {}

    antal_annonsobservationer = sum(
        1
        for post in observationer
        if post.get("typ")
        == "annons"
    )

    antal_marknadsvardeobservationer = sum(
        1
        for post in observationer
        if post.get("typ")
        == "marknadsvarde"
    )

    info(
        "[TREND] Annonsobservationer: "
        f"{antal_annonsobservationer}"
    )

    info(
        "[TREND] Marknadsvärdesobservationer: "
        f"{antal_marknadsvardeobservationer}"
    )

    per_kategori = defaultdict(
        list
    )

    for post in observationer:
        if (
            post.get("typ")
            != "annons"
        ):
            continue

        kategori = _trendkategori(
            post
        )

        if not kategori:
            continue

        per_kategori[
            kategori
        ].append(post)

    info(
        "[TREND] Marknadskategorier: "
        f"{len(per_kategori)}"
    )

    info(
        "[TREND] Premisser: "
        f"minst {MIN_TREND_DAGAR} separata observationsdagar, "
        f"minst {MIN_TREND_STEG} konsekutiva steg, "
        f"minst {TREND_MIN_FORANDRING_PROCENT:.1f} % "
        "förändring per steg."
    )

    trender = {}

    for kategori, poster in sorted(
        per_kategori.items()
    ):
        dagliga_priser = (
            _bygg_dagliga_priser(
                poster
            )
        )

        analys = (
            _analysera_trendsegment(
                dagliga_priser
            )
        )

        analys["kategori"] = (
            kategori
        )

        analys[
            "dagliga_priser"
        ] = dagliga_priser

        trender[
            kategori
        ] = analys

        _logga_trendkategori(
            kategori,
            analys,
        )

    _logga_trendsammanfattning(
        trender
    )

    info(
        "[TREND] Trendanalys påverkar INTE "
        "100-poängsscore eller valuation."
    )

    info(
        "[TREND] =================================================="
    )

    return trender


def berakna_marknadstrend_for_bil(
    bil: dict,
    trender: dict[str, dict],
) -> dict:
    """Hämtar aktuell trend för bilens marknadskategori."""

    kategori = _trendkategori(
        bil
    )

    trend = trender.get(
        kategori
    )

    if not trend:
        return {
            "marknadstrend":
                "otillrackligt_underlag",
            "marknadstrend_styrka": 0,
            "marknadstrend_forandring_procent": 0.0,
            "marknadstrend_forandring_kr": 0.0,
            "marknadstrend_start": None,
            "marknadstrend_slut": None,
            "marknadstrend_observationsdagar": 0,
        }

    return {
        "marknadstrend":
            trend.get(
                "trend",
                "otillrackligt_underlag",
            ),
        "marknadstrend_styrka":
            trend.get(
                "trendstyrka",
                0,
            ),
        "marknadstrend_forandring_procent":
            trend.get(
                "trendforandring_procent",
                0.0,
            ),
        "marknadstrend_forandring_kr":
            trend.get(
                "trendforandring_kr",
                0.0,
            ),
        "marknadstrend_start":
            trend.get(
                "trend_start_dag"
            ),
        "marknadstrend_slut":
            trend.get(
                "trend_slut_dag"
            ),
        "marknadstrend_observationsdagar":
            trend.get(
                "trend_observationsdagar",
                0,
            ),
    }
