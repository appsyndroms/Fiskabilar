"""
Append-only historik för Fiskabilar.

Två huvudtyper av observationer sparas i JSONL:
1. annons - vad marknaden faktiskt visade för en bil vid en viss tidpunkt
2. marknadsvärde - vilket värde modellen räknade fram och vilket underlag
   som användes

Historiken är append-only.

Trendanalysen bygger på historiska marknadsobservationer och är avsiktligt
separerad från 100-poängsscoren. Den används endast för att observera
marknadens riktning.

En trend identifieras först när det finns tillräckligt många observationer
från separata kördagar. Detta förhindrar att flera körningar samma dag
felaktigt tolkas som en marknadstrend.

Trenddiagnostik hålls medvetet kort i loggen:
- Endast identifierade upp- och nedtrender skrivs ut.
- Kategorier med otillräckligt underlag skrivs inte individuellt.
- Stabilt underlag skrivs inte individuellt.
- Varje identifierad trend skrivs på EN rad.
- En sammanfattande lägesbild skrivs alltid.
"""
from app_logging.logger import info

import json
import os
from collections import defaultdict
from datetime import datetime
from statistics import median
from zoneinfo import ZoneInfo

from config import HISTORIK_FIL


TIDSZON = ZoneInfo("Europe/Stockholm")


# ---------------------------------------------------------------------------
# Trendparametrar
# ---------------------------------------------------------------------------

# Minsta antal separata observationsdagar innan trend får identifieras.
MIN_TREND_DAGAR = 3

# Minsta förändring mellan två observationsdagar för att riktningen
# ska räknas som verklig prisrörelse.
TREND_MIN_FORANDRING_PROCENT = 1.0

# Minsta antal konsekutiva riktningar som krävs för en trend.
MIN_TREND_STEG = 2


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


# ---------------------------------------------------------------------------
# Trendanalys
# ---------------------------------------------------------------------------


def _trendkategori(post: dict) -> str:
    """
    Skapar en stabil marknadskategori.

    Trend ska inte baseras på enskilda registreringsnummer eftersom vi vill
    se hur marknaden för exempelvis:

        BMW 530e xDrive Touring 2023

    utvecklas över tid.
    """

    modell = str(post.get("modell") or "").strip().lower()
    variant = str(post.get("variant") or "").strip().lower()
    arsmodell = post.get("arsmodell")

    return f"{modell}|{variant}|{arsmodell}"


def _observationsdag(post: dict) -> str | None:
    """Returnerar kalenderdagen för observationen."""

    dt = _parse_tid(post.get("tid"))

    if not dt:
        return None

    return dt.astimezone(TIDSZON).date().isoformat()


def _bygg_dagliga_priser(observationer: list[dict]) -> list[dict]:
    """
    Bygger en observation per dag.

    Om samma bilkategori observerats flera gånger samma dag används medianen.
    Det gör trendanalysen robust mot flera körningar under samma dygn.
    """

    per_dag: dict[str, list[float]] = defaultdict(list)

    for post in observationer:
        pris = post.get("pris")

        if not isinstance(pris, (int, float)):
            continue

        dag = _observationsdag(post)

        if not dag:
            continue

        per_dag[dag].append(float(pris))

    resultat = []

    for dag, priser in sorted(per_dag.items()):
        if not priser:
            continue

        resultat.append(
            {
                "dag": dag,
                "pris": median(priser),
                "antal_observationer": len(priser),
            }
        )

    return resultat


def _prisforandring_procent(
    tidigare: float,
    senare: float,
) -> float:
    """Beräknar procentuell förändring från tidigare till senare pris."""

    if tidigare <= 0:
        return 0.0

    return ((senare - tidigare) / tidigare) * 100.0


def _klassificera_riktning(
    forandring_procent: float,
) -> str:
    """
    Klassificerar en prisförändring.

    Små rörelser ignoreras för att undvika brus.
    """

    if forandring_procent >= TREND_MIN_FORANDRING_PROCENT:
        return "upp"

    if forandring_procent <= -TREND_MIN_FORANDRING_PROCENT:
        return "ned"

    return "oforandrad"


def _analysera_trendsegment(
    dagliga_priser: list[dict],
) -> dict:
    """
    Identifierar aktuell marknadstrend.

    En trend kräver:
      - minst MIN_TREND_DAGAR separata dagar
      - minst MIN_TREND_STEG konsekutiva prisrörelser
      - varje rörelse måste överstiga tröskeln
    """

    resultat = {
        "trend": "otillrackligt_underlag",
        "trendstyrka": 0,
        "trendforandring_procent": 0.0,
        "trendforandring_kr": 0.0,
        "trend_start_dag": None,
        "trend_slut_dag": None,
        "trend_observationsdagar": len(dagliga_priser),
    }

    if len(dagliga_priser) < MIN_TREND_DAGAR:
        return resultat

    riktningar = []

    for tidigare, senare in zip(
        dagliga_priser,
        dagliga_priser[1:],
    ):
        forandring_procent = _prisforandring_procent(
            tidigare["pris"],
            senare["pris"],
        )

        riktningar.append(
            {
                "fran_dag": tidigare["dag"],
                "till_dag": senare["dag"],
                "fran_pris": tidigare["pris"],
                "till_pris": senare["pris"],
                "forandring_kr": (
                    senare["pris"] - tidigare["pris"]
                ),
                "forandring_procent": forandring_procent,
                "riktning": _klassificera_riktning(
                    forandring_procent
                ),
            }
        )

    if not riktningar:
        return resultat

    # Vi tittar bakifrån eftersom det är den aktuella marknadsriktningen
    # vi vill fånga.
    aktuell_riktning = riktningar[-1]["riktning"]

    if aktuell_riktning == "oforandrad":
        resultat["trend"] = "stabil"
        return resultat

    konsekutiva = 0

    for steg in reversed(riktningar):
        if steg["riktning"] == aktuell_riktning:
            konsekutiva += 1
        else:
            break

    if konsekutiva < MIN_TREND_STEG:
        resultat["trend"] = "stabil"
        return resultat

    segment = riktningar[-konsekutiva:]

    start_pris = segment[0]["fran_pris"]
    slut_pris = segment[-1]["till_pris"]

    total_forandring_kr = slut_pris - start_pris

    if start_pris > 0:
        total_forandring_procent = (
            total_forandring_kr / start_pris
        ) * 100.0
    else:
        total_forandring_procent = 0.0

    resultat["trend"] = aktuell_riktning
    resultat["trendstyrka"] = konsekutiva
    resultat["trendforandring_procent"] = (
        total_forandring_procent
    )
    resultat["trendforandring_kr"] = total_forandring_kr
    resultat["trend_start_dag"] = segment[0]["fran_dag"]
    resultat["trend_slut_dag"] = segment[-1]["till_dag"]

    return resultat


# ---------------------------------------------------------------------------
# Trendloggning
# ---------------------------------------------------------------------------


def _formatera_kr(value) -> str:
    """Formaterar kronor för diagnostikloggar."""

    if not isinstance(value, (int, float)):
        return "?"

    return f"{value:,.0f} kr".replace(",", " ")


def _formatera_procent(value) -> str:
    """Formaterar procent för diagnostikloggar."""

    if not isinstance(value, (int, float)):
        return "?"

    return f"{value:+.2f} %"


def _kort_kategori(kategori: str) -> str:
    """
    Gör kategorinamnet lättare att läsa i Actions-loggen.

    Kategorin sparas oförändrad internt.
    """

    delar = kategori.split("|")

    if len(delar) != 3:
        return kategori

    modell, variant, arsmodell = delar

    modell = modell.strip()
    variant = variant.strip()

    if len(variant) > 80:
        variant = variant[:77] + "..."

    return f"{modell} | {variant} | {arsmodell}"


def _logga_trendkategori(
    kategori: str,
    analys: dict,
) -> None:
    """
    Skriver EN kompakt diagnostikrad för riktiga trender.

    Viktigt för loggstorleken:

    - otillräckligt_underlag -> ingen logg
    - stabil -> ingen logg
    - upp -> EN rad
    - ned -> EN rad

    Detaljer som period, senaste observation och enskilda steg skrivs
    inte ut här eftersom de annars snabbt gör Actions-loggen onödigt lång.
    Själva trendinformationen finns fortfarande kvar i analysresultatet.
    """

    trend = analys.get("trend")

    if trend not in ("upp", "ned"):
        return

    styrka = analys.get("trendstyrka", 0)
    dagar = analys.get("trend_observationsdagar", 0)
    forandring_kr = analys.get("trendforandring_kr", 0)
    forandring_procent = analys.get(
        "trendforandring_procent",
        0.0,
    )

    info(
        "[TREND] "
        f"{_kort_kategori(kategori)} | "
        f"{trend.upper()} | "
        f"dagar={dagar} | "
        f"steg={styrka} | "
        f"förändring={_formatera_kr(forandring_kr)} "
        f"({_formatera_procent(forandring_procent)})"
    )


def _logga_trendsammanfattning(
    trender: dict[str, dict],
) -> None:
    """Skriver en sammanfattning av hela marknadens riktning."""

    antal_upp = 0
    antal_ned = 0
    antal_stabil = 0
    antal_otillrackligt = 0

    for analys in trender.values():
        trend = analys.get("trend")

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

    Returnerar exempelvis:

    {
        "bmw 530e xdrive touring|...|2023": {
            "trend": "ned",
            "trendstyrka": 3,
            ...
        }
    }

    Trendanalysen påverkar inte score.

    Loggningen är medvetet komprimerad:
    endast identifierade upp- och nedtrender skrivs individuellt,
    och varje trend skrivs på en enda rad.
    """

    observationer = _las_observationer()

    info(
        "[TREND] =================================================="
    )
    info(
        "[TREND] Startar trendanalys."
    )
    info(
        "[TREND] Historikfil: "
        f"{HISTORIK_FIL}"
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
        if post.get("typ") == "annons"
    )

    antal_marknadsvardeobservationer = sum(
        1
        for post in observationer
        if post.get("typ") == "marknadsvarde"
    )

    info(
        "[TREND] Annonsobservationer: "
        f"{antal_annonsobservationer}"
    )

    info(
        "[TREND] Marknadsvärdesobservationer: "
        f"{antal_marknadsvardeobservationer}"
    )

    per_kategori: dict[str, list[dict]] = defaultdict(list)

    for post in observationer:
        if post.get("typ") != "annons":
            continue

        kategori = _trendkategori(post)

        if not kategori:
            continue

        per_kategori[kategori].append(post)

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
        dagliga_priser = _bygg_dagliga_priser(
            poster
        )

        analys = _analysera_trendsegment(
            dagliga_priser
        )

        analys["kategori"] = kategori
        analys["dagliga_priser"] = dagliga_priser

        trender[kategori] = analys

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

    kategori = _trendkategori(bil)

    trend = trender.get(kategori)

    if not trend:
        return {
            "marknadstrend": "otillrackligt_underlag",
            "marknadstrend_styrka": 0,
            "marknadstrend_forandring_procent": 0.0,
            "marknadstrend_forandring_kr": 0.0,
            "marknadstrend_start": None,
            "marknadstrend_slut": None,
            "marknadstrend_observationsdagar": 0,
        }

    return {
        "marknadstrend": trend.get(
            "trend",
            "otillrackligt_underlag",
        ),
        "marknadstrend_styrka": trend.get(
            "trendstyrka",
            0,
        ),
        "marknadstrend_forandring_procent": trend.get(
            "trendforandring_procent",
            0.0,
        ),
        "marknadstrend_forandring_kr": trend.get(
            "trendforandring_kr",
            0.0,
        ),
        "marknadstrend_start": trend.get(
            "trend_start_dag"
        ),
        "marknadstrend_slut": trend.get(
            "trend_slut_dag"
        ),
        "marknadstrend_observationsdagar": trend.get(
            "trend_observationsdagar",
            0,
        ),
    }


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

    annonser = list(
        data.get("annonser") or []
    )

    varderingar = list(
        data.get("varderingar") or []
    )

    annonser.sort(
        key=lambda x: x.get("tid") or ""
    )

    varderingar.sort(
        key=lambda x: x.get("tid") or ""
    )

    priser = [
        post.get("pris")
        for post in annonser
        if isinstance(
            post.get("pris"),
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
            annonser[0].get("tid")
        )

        if forsta_tid:
            nu = datetime.now(
                TIDSZON
            )

            historik[
                "historik_dagar"
            ] = max(
                0,
                (nu - forsta_tid).days,
            )

    marknadsvarden = [
        post.get("marknadsvarde")
        for post in varderingar
        if isinstance(
            post.get("marknadsvarde"),
            (int, float),
        )
    ]

    if marknadsvarden:
        historik[
            "historik_marknadsvarde"
        ] = (
            marknadsvarden[-1]
        )

        if len(marknadsvarden) >= 2:
            historik[
                "historik_marknadsvarde_forandring"
            ] = (
                marknadsvarden[-1]
                - marknadsvarden[0]
            )

    return historik


def berika_med_historik(
    bil: dict,
    historikindex: dict[str, dict],
    trender: dict[str, dict] | None = None,
) -> dict:
    """
    Lägger historikfält och marknadstrend på bilens dict.

    Trendinformationen är diagnostisk och påverkar inte 100-poängsscoren.

    Trendanalysen skickas normalt in färdigberäknad från huvudflödet.
    Detta är viktigt eftersom bygg_marknadstrender() annars skulle köras
    en gång per bil och läsa igenom hela historikfilen varje gång.

    Om trender inte skickas in byggs de som fallback.
    """

    historik = berakna_historik(
        bil,
        historikindex,
    )

    # ------------------------------------------------------------
    # VIKTIG ÄNDRING:
    #
    # Trendanalysen ska normalt byggas EN gång per körning och
    # sedan återanvändas för alla bilar.
    #
    # Tidigare kördes:
    #
    #     bygg_marknadstrender()
    #
    # här för varje enskild bil.
    #
    # Det skapade upprepade:
    #
    #     [TREND] Startar trendanalys.
    #
    # i Actions-loggen och läste dessutom hela historikfilen
    # om och om igen.
    #
    # Nu kan huvudflödet skicka in färdigberäknade trender.
    # ------------------------------------------------------------

    if trender is None:
        trender = bygg_marknadstrender()

    trend = berakna_marknadstrend_for_bil(
        bil,
        trender,
    )

    bil.update(historik)
    bil.update(trend)

    return bil
