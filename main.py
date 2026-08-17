"""
V60-fyndfilter - huvudscript.

Kör:
    python main.py

Flöde:
1. Kontrollera aktiv tid.
2. Hämta annonser från aktiva källor.
3. Deduplicera annonser.
4. Berika med historik.
5. Beräkna marknadsvärde.
6. Beräkna fyndscore.
7. Logga kandidater och filterresultat.
8. Skicka nya intressanta fynd direkt via mejl.
9. Markera skickade annonser i state.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

from config import AKTIVA_KALLOR
from dedup import deduplicera
from state import (
    ladda_state,
    spara_state,
    uppdatera_och_berika,
    redan_notifierad,
    markera_notifierad,
)
from valuation import berakna_fynd
from scoring import (
    berakna_fyndscore,
    formatera_notis,
    bil_rubrik,
)
from notify import skicka_epost

from scrapers import (
    blocket,
    wayke,
    bytbil,
    bilweb,
)


KALLA_TILL_MODUL = {
    "blocket": blocket,
    "wayke": wayke,
    "bytbil": bytbil,
    "bilweb": bilweb,
}


AKTIV_TID_START = 6
AKTIV_TID_SLUT = 22
TIDSZON = ZoneInfo("Europe/Stockholm")


# =========================================================
# FILTERGRÄNSER
# =========================================================

MIN_SCORE_FOR_NOTIS = 70
MIN_DIFF_FOR_CANDIDATE = 15000

# Hur många kandidater som ska visas i diagnostiken.
DIAGNOSTIK_ANTAL = 20


def _inom_aktiv_tid() -> bool:
    """Avgör om det just nu är mellan 06:00-22:00 svensk tid."""

    nu = datetime.now(TIDSZON)

    return (
        AKTIV_TID_START
        <= nu.hour
        < AKTIV_TID_SLUT
    )


def hamta_alla_annonser() -> list[dict]:
    """Hämtar annonser från alla aktiva källor."""

    alla = []

    for kalla in AKTIVA_KALLOR:

        modul = KALLA_TILL_MODUL.get(kalla)

        if modul is None:
            print(
                f"Okänd källa i config: {kalla}"
            )
            continue

        try:
            annonser = modul.hamta_annonser()

            print(
                f"[KÄLLA] {kalla}: "
                f"{len(annonser)} annonser"
            )

            alla.extend(annonser)

        except Exception as e:
            print(
                f"FEL i källa '{kalla}': {e}"
            )

    return alla


def _annons_namn(bil: dict) -> str:
    """Försöker skapa en användbar kort rubrik för loggen."""

    try:
        return bil_rubrik(bil)
    except Exception:
        modell = bil.get("modell") or "Okänd modell"
        return str(modell)


def _logga_kandidat(
    bil: dict,
    vardering: dict,
    score: int,
    status: str,
) -> dict:
    """Skapar en kompakt diagnostikpost."""

    return {
        "score": score,
        "diff": vardering.get("diff", 0),
        "marknad": vardering.get(
            "marknadsvarde",
            0,
        ),
        "pris": bil.get(
            "annonspris",
            0,
        ),
        "miltal": bil.get(
            "miltal",
            0,
        ),
        "arsmodell": bil.get(
            "arsmodell",
            "?",
        ),
        "modell": _annons_namn(bil),
        "utrustning": bil.get(
            "utrustningsniva",
            "",
        ),
        "status": status,
        "url": (
            bil.get("urls", [""])[0]
            if bil.get("urls")
            else ""
        ),
    }


def _skriv_diagnostik(
    kandidater: list[dict],
) -> None:
    """
    Skriver ut de bästa kandidaterna.

    Dessa kan ha skickats, stoppats av score,
    redan vara notifierade eller av annan anledning
    inte blivit mejlade.
    """

    if not kandidater:
        print("")
        print("=== DIAGNOSTIK ===")
        print("Inga kandidater passerade valuation.")
        return

    kandidater = sorted(
        kandidater,
        key=lambda x: (
            x["score"],
            x["diff"],
        ),
        reverse=True,
    )

    print("")
    print("=" * 70)
    print("=== DIAGNOSTIK: BÄSTA KANDIDATER ===")
    print("=" * 70)

    for index, kandidat in enumerate(
        kandidater[:DIAGNOSTIK_ANTAL],
        start=1,
    ):

        print(
            f"{index:02d}. "
            f"{kandidat['score']:3d}/100 | "
            f"{kandidat['arsmodell']} | "
            f"{kandidat['miltal']:,} mil | "
            f"{kandidat['pris']:,} kr | "
            f"diff +{kandidat['diff']:,} | "
            f"{kandidat['modell']} | "
            f"{kandidat['utrustning']} | "
            f"{kandidat['status']}"
        )

        if kandidat["url"]:
            print(
                f"    {kandidat['url']}"
            )

    print("=" * 70)
    print("")


def main():

    print("")
    print("=== Bilfyndfilter startar ===")
    print("")

    # =====================================================
    # AKTIV TID
    # =====================================================

    if not _inom_aktiv_tid():

        nu = datetime.now(TIDSZON)

        print(
            f"Utanför aktiv tid "
            f"({nu.strftime('%H:%M')} svensk tid, "
            f"fönster är "
            f"{AKTIV_TID_START:02d}:00-"
            f"{AKTIV_TID_SLUT:02d}:00). "
            "Avslutar utan att göra något."
        )

        return

    # =====================================================
    # HÄMTA
    # =====================================================

    raa_annonser = hamta_alla_annonser()

    print("")
    print(
        f"Totalt {len(raa_annonser)} "
        "annonser innan dedup"
    )

    # =====================================================
    # DEDUP
    # =====================================================

    bilar = deduplicera(
        raa_annonser
    )

    print(
        f"{len(bilar)} unika bilar efter dedup"
    )

    # =====================================================
    # STATE / HISTORIK
    # =====================================================

    state = ladda_state()

    bilar = uppdatera_och_berika(
        bilar,
        state,
    )

    # =====================================================
    # STATISTIK
    # =====================================================

    statistik = {
        "totalt": len(bilar),
        "valuation_ok": 0,
        "under_diff": 0,
        "score_ok": 0,
        "redan_notifierade": 0,
        "mejl_skickade": 0,
    }

    kandidater = []

    # =====================================================
    # BEDÖM ALLA BILAR
    # =====================================================

    for bil in bilar:

        try:
            vardering = berakna_fynd(
                bil
            )
        except Exception as e:

            print(
                "[FEL valuation] "
                f"{_annons_namn(bil)}: {e}"
            )

            continue

        # -------------------------------------------------
        # Valuation
        # -------------------------------------------------

        if vardering.get("niva") is None:

            continue

        statistik["valuation_ok"] += 1

        diff = vardering.get(
            "diff",
            0,
        )

        # -------------------------------------------------
        # Prisfilter
        # -------------------------------------------------

        if diff < MIN_DIFF_FOR_CANDIDATE:

            continue

        statistik["under_diff"] += 1

        # -------------------------------------------------
        # Score
        # -------------------------------------------------

        try:
            score = berakna_fyndscore(
                bil,
                vardering,
            )
        except Exception as e:

            print(
                "[FEL scoring] "
                f"{_annons_namn(bil)}: {e}"
            )

            continue

        # -------------------------------------------------
        # Kandidat
        # -------------------------------------------------

        if score < MIN_SCORE_FOR_NOTIS:

            kandidater.append(
                _logga_kandidat(
                    bil,
                    vardering,
                    score,
                    "STOPP: score < 70",
                )
            )

            continue

        statistik["score_ok"] += 1

        # -------------------------------------------------
        # Redan notifierad
        # -------------------------------------------------

        if redan_notifierad(
            bil,
            state,
        ):

            statistik["redan_notifierade"] += 1

            kandidater.append(
                _logga_kandidat(
                    bil,
                    vardering,
                    score,
                    "STOPP: redan notifierad",
                )
            )

            continue

        # -------------------------------------------------
        # Kandidat som faktiskt kan skickas
        # -------------------------------------------------

        kandidater.append(
            _logga_kandidat(
                bil,
                vardering,
                score,
                "SKICKAS",
            )
        )

        # -------------------------------------------------
        # Mejlets nivå
        # -------------------------------------------------

        if score >= 90:
            niva_etikett = (
                "EXTREMT FYND"
            )
            emoji = "🚨"

        elif score >= 80:
            niva_etikett = (
                "RIKTIGT FYND"
            )
            emoji = "🔥"

        else:
            niva_etikett = (
                "MYCKET INTRESSANT"
            )
            emoji = "🟢"

        # -------------------------------------------------
        # Formatera
        # -------------------------------------------------

        text = formatera_notis(
            bil,
            vardering,
            score,
        )

        diff_formaterad = (
            f"{diff:,}"
            .replace(",", " ")
        )

        amne = (
            f"{emoji} "
            f"{niva_etikett}: "
            f"{bil_rubrik(bil)} "
            f"{bil.get('arsmodell')} - "
            f"{diff_formaterad} kr under marknad"
        )

        # -------------------------------------------------
        # Skicka
        # -------------------------------------------------

        skickat = skicka_epost(
            amne,
            text,
        )

        if skickat:

            print(
                f"Mejl skickat: {amne}"
            )

            markera_notifierad(
                bil,
                state,
            )

            spara_state(
                state
            )

            statistik["mejl_skickade"] += 1

        else:

            print(
                "OBS: mejl INTE skickat, "
                "försöker igen nästa körning: "
                f"{amne}"
            )

    # =====================================================
    # DIAGNOSTIK
    # =====================================================

    _skriv_diagnostik(
        kandidater
    )

    # =====================================================
    # SAMMANFATTNING
    # =====================================================

    print("")
    print("=" * 70)
    print("=== SAMMANFATTNING ===")
    print("=" * 70)

    print(
        f"Totalt efter dedup: "
        f"{statistik['totalt']}"
    )

    print(
        f"Valuation OK: "
        f"{statistik['valuation_ok']}"
    )

    print(
        f"Över prisdiff-gränsen "
        f"({MIN_DIFF_FOR_CANDIDATE:,} kr): "
        f"{statistik['under_diff']}"
        .replace(",", " ")
    )

    print(
        f"Score >= "
        f"{MIN_SCORE_FOR_NOTIS}: "
        f"{statistik['score_ok']}"
    )

    print(
        f"Redan notifierade: "
        f"{statistik['redan_notifierade']}"
    )

    print(
        f"Mejl skickade: "
        f"{statistik['mejl_skickade']}"
    )

    print("=" * 70)

    if statistik["mejl_skickade"] == 0:

        print(
            "Inga nya fynd denna körning."
        )

    else:

        print(
            f"Totalt "
            f"{statistik['mejl_skickade']} "
            "nya fynd mejlade denna körning."
        )


if __name__ == "__main__":
    main()
