"""
Trendanalys för Fiskabilar.

Trendanalysen bygger på historiska annonsobservationer.

Den är avsiktligt separerad från 100-poängsscoren och valuation.

Trendanalysen använder ett rullande tidsfönster för att beskriva
den aktuella marknadsrörelsen. Äldre historik sparas fortfarande
men ska inte dominera den aktuella trenden.

En trend kräver flera separata observationsdagar för att flera körningar
under samma dygn inte ska tolkas som en marknadsrörelse.

Utöver prisrörelsen beskriver analysen även marknadens storlek och
prisintervall inom trendfönstret. Detta gör att historiken kan användas
som ett faktiskt marknadsunderlag och inte bara som en prisindikator.
"""

from app_logging.logger import debug

from collections import defaultdict
from datetime import timedelta
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

# Två separata observationsdagar räcker för att fånga första rörelsen.
MIN_TREND_DAGAR = 2

# En förändring måste vara minst 1 % för att räknas som UPP eller NED.
TREND_MIN_FORANDRING_PROCENT = 1.0

# Ett steg mellan två separata observationsdagar räcker.
MIN_TREND_STEG = 1

# Aktuell trend beräknas endast inom detta rullande tidsfönster.
#
# Exempel:
# Om senaste observationen är 2026-08-19 används observationer
# från och med 2026-08-06.
#
# Detta gör att gamla prisrörelser inte fortsätter att beskrivas
# som en aktuell marknadstrend.
TREND_FONSTER_DAGAR = 14


def _pris_ar_anvandbart_i_trend(
    pris,
) -> bool:
    """
    Avgör om ett historiskt annonspris är rimligt
    att använda i trendanalysen.

    Gamla historikposter kan innehålla felaktiga priser,
    exempelvis gamla parserfel där ett pris med två decimaler
    lagrats 100 gånger för högt.

    Råhistoriken ändras inte.
    Felaktiga värden ignoreras endast av trendanalysen.
    """

    return (
        isinstance(
            pris,
            (int, float),
        )
        and not isinstance(
            pris,
            bool,
        )
        and 100_000 <= pris < 1_000_000
    )


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

    Detta är viktigt eftersom en körning kan innehålla många observationer
    av samma marknad under samma dygn. Flera körningar samma dag ska därför
    inte räknas som flera separata marknadsdagar.

    Förutom medianpriset sparas även:
      - antal observationer
      - lägsta pris
      - högsta pris

    Uppenbart orimliga historiska priser ignoreras.
    Råhistoriken påverkas inte.
    """

    per_dag: dict[
        str,
        list[float],
    ] = defaultdict(list)

    for post in observationer:
        pris = post.get(
            "pris"
        )

        if not _pris_ar_anvandbart_i_trend(
            pris
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
                "lagsta_pris": min(
                    priser
                ),
                "hogsta_pris": max(
                    priser
                ),
            }
        )

    return resultat


def _begransa_trendfonster(
    dagliga_priser: list[dict],
) -> list[dict]:
    """
    Begränsar dagliga priser till det aktuella trendfönstret.

    Fönstret räknas bakåt från den senaste observationsdagen.

    Exempel:

        senaste dag = 2026-08-19
        fönster     = 14 dagar

    Då används observationer från och med 2026-08-06.

    Det gör att den historiska JSONL-datan kan vara mycket större än
    själva underlaget som används för aktuell trendanalys.
    """

    if not dagliga_priser:
        return []

    senaste_dag = dagliga_priser[-1].get(
        "dag"
    )

    if not senaste_dag:
        return []

    try:
        senaste_datum = (
            __import__(
                "datetime"
            )
            .date.fromisoformat(
                senaste_dag
            )
        )
    except (
        TypeError,
        ValueError,
    ):
        return dagliga_priser

    startdatum = (
        senaste_datum
        - timedelta(
            days=TREND_FONSTER_DAGAR - 1
        )
    )

    resultat = []

    for post in dagliga_priser:
        dag = post.get(
            "dag"
        )

        if not isinstance(
            dag,
            str,
        ):
            continue

        try:
            datum = (
                __import__(
                    "datetime"
                )
                .date.fromisoformat(
                    dag
                )
            )

        except (
            TypeError,
            ValueError,
        ):
            continue

        if (
            startdatum
            <= datum
            <= senaste_datum
        ):
            resultat.append(
                post
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


def _analysera_marknadsstorlek(
    dagliga_priser: list[dict],
) -> dict:
    """
    Analyserar marknadens storlek inom trendfönstret.

    Antalet observationer används som marknadsindikator.

    Första och senaste observationsdag jämförs. Detta säger exempelvis
    om det finns fler eller färre observerade bilar än tidigare.

    Det är observationer, inte unika fordon. Livscykelanalysen ansvarar
    för identitet och annonsers livscykel.
    """

    resultat = {
        "marknad_antal_forsta_dag": 0,
        "marknad_antal_senaste_dag": 0,
        "marknad_antal_forandring": 0,
        "marknad_antal_forandring_procent": 0.0,
        "marknad_minsta_pris": None,
        "marknad_hogsta_pris": None,
        "marknad_prisintervall": None,
    }

    if not dagliga_priser:
        return resultat

    forsta = dagliga_priser[0]
    senaste = dagliga_priser[-1]

    antal_forsta = forsta.get(
        "antal_observationer",
        0,
    )

    antal_senaste = senaste.get(
        "antal_observationer",
        0,
    )

    if not isinstance(
        antal_forsta,
        (int, float),
    ):
        antal_forsta = 0

    if not isinstance(
        antal_senaste,
        (int, float),
    ):
        antal_senaste = 0

    resultat[
        "marknad_antal_forsta_dag"
    ] = int(
        antal_forsta
    )

    resultat[
        "marknad_antal_senaste_dag"
    ] = int(
        antal_senaste
    )

    resultat[
        "marknad_antal_forandring"
    ] = int(
        antal_senaste
        - antal_forsta
    )

    if antal_forsta > 0:
        resultat[
            "marknad_antal_forandring_procent"
        ] = (
            (
                antal_senaste
                - antal_forsta
            )
            / antal_forsta
        ) * 100.0

    lagsta_priser = [
        post.get(
            "lagsta_pris"
        )
        for post in dagliga_priser
        if isinstance(
            post.get(
                "lagsta_pris"
            ),
            (int, float),
        )
    ]

    hogsta_priser = [
        post.get(
            "hogsta_pris"
        )
        for post in dagliga_priser
        if isinstance(
            post.get(
                "hogsta_pris"
            ),
            (int, float),
        )
    ]

    if lagsta_priser:
        resultat[
            "marknad_minsta_pris"
        ] = min(
            lagsta_priser
        )

    if hogsta_priser:
        resultat[
            "marknad_hogsta_pris"
        ] = max(
            hogsta_priser
        )

    if (
        resultat[
            "marknad_minsta_pris"
        ] is not None
        and resultat[
            "marknad_hogsta_pris"
        ] is not None
    ):
        resultat[
            "marknad_prisintervall"
        ] = (
            resultat[
                "marknad_hogsta_pris"
            ]
            - resultat[
                "marknad_minsta_pris"
            ]
        )

    return resultat


def _analysera_trendsegment(
    dagliga_priser: list[dict],
) -> dict:
    """
    Identifierar aktuell marknadstrend.

    Kräver:
      - minst MIN_TREND_DAGAR
      - minst MIN_TREND_STEG konsekutiva rörelser
      - varje rörelse över tröskeln

    Endast dagliga observationer som redan ligger inom det rullande
    trendfönstret ska skickas in till denna funktion.
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

    resultat.update(
        _analysera_marknadsstorlek(
            dagliga_priser
        )
    )

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
    """
    Skriver ut trendstatus för varje marknadskategori.

    Alla kategorier skrivs ut, även när underlaget är otillräckligt
    eller när marknaden klassificeras som stabil.
    """

    trend = analys.get(
        "trend",
        "otillrackligt_underlag",
    )

    if trend == "upp":
        status = "UPP"

    elif trend == "ned":
        status = "NED"

    elif trend == "stabil":
        status = "STABIL"

    else:
        status = "OTILLRACKLIGT_UNDERLAG"

    debug(
        "[TREND] "
        f"{_kort_kategori(kategori)} | "
        f"{status} | "
        f"dagar={analys.get('trend_observationsdagar', 0)} | "
        f"steg={analys.get('trendstyrka', 0)} | "
        f"förändring={_formatera_kr(analys.get('trendforandring_kr', 0))} "
        f"({_formatera_procent(analys.get('trendforandring_procent', 0.0))}) | "
        f"marknad={analys.get('marknad_antal_senaste_dag', 0)} "
        f"({analys.get('marknad_antal_forandring', 0):+d}) | "
        f"spann={_formatera_kr(analys.get('marknad_prisintervall'))}"
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

    debug(
        "[TREND] Lägesbild: "
        f"UPP={antal_upp} | "
        f"NED={antal_ned} | "
        f"STABIL={antal_stabil} | "
        f"OTILLRÄCKLIGT={antal_otillrackligt}"
    )

    if antal_ned:
        debug(
            "[TREND] ⚠ Det finns marknadskategorier "
            "med identifierad prisnedgång."
        )

    if antal_upp:
        debug(
            "[TREND] Det finns marknadskategorier "
            "med identifierad prisuppgång."
        )


def bygg_marknadstrender() -> dict[str, dict]:
    """
    Analyserar hela historiken och bygger aktuella marknadstrender.

    Den historiska JSONL-datan kan innehålla många månader av historik,
    men den aktuella trendanalysen använder endast ett rullande
    trendfönster på TREND_FONSTER_DAGAR.

    Trendanalysen innehåller:
      - prisutveckling
      - trendriktning
      - trendstyrka
      - antal observationsdagar
      - marknadens storlek
      - förändring av marknadsstorlek
      - lägsta observerade pris
      - högsta observerade pris
      - prisintervall

    Trendanalysen påverkar inte score eller valuation.
    """

    observationer = _las_observationer()

    debug(
        "[TREND] =================================================="
    )

    debug(
        "[TREND] Startar trendanalys."
    )

    debug(
        "[TREND] Totalt antal historiska poster: "
        f"{len(observationer)}"
    )

    if not observationer:
        debug(
            "[TREND] Ingen historik hittades."
        )

        debug(
            "[TREND] Trendanalys avslutad: "
            "otillräckligt underlag."
        )

        debug(
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

    debug(
        "[TREND] Annonsobservationer: "
        f"{antal_annonsobservationer}"
    )

    debug(
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

    debug(
        "[TREND] Marknadskategorier: "
        f"{len(per_kategori)}"
    )

    debug(
        "[TREND] Rullande trendfönster: "
        f"{TREND_FONSTER_DAGAR} dagar."
    )

    debug(
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
        alla_dagliga_priser = (
            _bygg_dagliga_priser(
                poster
            )
        )

        dagliga_priser = (
            _begransa_trendfonster(
                alla_dagliga_priser
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

        # Spara endast det aktuella trendfönstret i trendresultatet.
        analys[
            "dagliga_priser"
        ] = dagliga_priser

        analys[
            "trend_fonster_dagar"
        ] = TREND_FONSTER_DAGAR

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

    debug(
        "[TREND] Trendanalys påverkar INTE "
        "100-poängsscore eller valuation."
    )

    debug(
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

            "marknadstrend_styrka":
                0,

            "marknadstrend_forandring_procent":
                0.0,

            "marknadstrend_forandring_kr":
                0.0,

            "marknadstrend_start":
                None,

            "marknadstrend_slut":
                None,

            "marknadstrend_observationsdagar":
                0,

            "marknadstrend_fonster_dagar":
                TREND_FONSTER_DAGAR,

            "marknad_antal_forsta_dag":
                0,

            "marknad_antal_senaste_dag":
                0,

            "marknad_antal_forandring":
                0,

            "marknad_antal_forandring_procent":
                0.0,

            "marknad_minsta_pris":
                None,

            "marknad_hogsta_pris":
                None,

            "marknad_prisintervall":
                None,
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

        "marknadstrend_fonster_dagar":
            trend.get(
                "trend_fonster_dagar",
                TREND_FONSTER_DAGAR,
            ),

        "marknad_antal_forsta_dag":
            trend.get(
                "marknad_antal_forsta_dag",
                0,
            ),

        "marknad_antal_senaste_dag":
            trend.get(
                "marknad_antal_senaste_dag",
                0,
            ),

        "marknad_antal_forandring":
            trend.get(
                "marknad_antal_forandring",
                0,
            ),

        "marknad_antal_forandring_procent":
            trend.get(
                "marknad_antal_forandring_procent",
                0.0,
            ),

        "marknad_minsta_pris":
            trend.get(
                "marknad_minsta_pris"
            ),

        "marknad_hogsta_pris":
            trend.get(
                "marknad_hogsta_pris"
            ),

        "marknad_prisintervall":
            trend.get(
                "marknad_prisintervall"
            ),
    }
