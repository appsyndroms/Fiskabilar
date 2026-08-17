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
7. Skicka nya intressanta fynd direkt via mejl.
8. Markera skickade annonser i state.
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

# ---------------------------------------------------------
# FYNDSCORE
# ---------------------------------------------------------
#
# Vi använder valuation som ett första grovt filter,
# men fyndscore avgör om bilen faktiskt är intressant.
#
# 70+ = mejlas
# 80+ = riktigt fynd
# 90+ = extremt fynd
#
MIN_SCORE_FOR_NOTIS = 70

# Valuation måste fortfarande ligga tillräckligt under
# beräknat marknadsvärde för att bilen ska betraktas som
# en kandidat.
MIN_DIFF_FOR_CANDIDATE = 15000


def _inom_aktiv_tid() -> bool:
    """
    Avgör om det just nu är mellan 06:00-22:00 svensk tid.

    Europe/Stockholm hanterar automatiskt sommar-/vintertid.
    """

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
            alla.extend(
                modul.hamta_annonser()
            )
        except Exception as e:
            print(
                f"FEL i källa '{kalla}': {e}"
            )

    return alla


def main():
    print("=== Bilfyndfilter startar ===")

    # -----------------------------------------------------
    # Aktiv tid
    # -----------------------------------------------------

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

    # -----------------------------------------------------
    # Hämta annonser
    # -----------------------------------------------------

    raa_annonser = hamta_alla_annonser()

    print(
        f"Totalt {len(raa_annonser)} "
        "annonser innan dedup"
    )

    # -----------------------------------------------------
    # Deduplicera
    # -----------------------------------------------------

    bilar = deduplicera(raa_annonser)

    print(
        f"{len(bilar)} unika bilar efter dedup"
    )

    # -----------------------------------------------------
    # Historik / state
    # -----------------------------------------------------

    state = ladda_state()

    bilar = uppdatera_och_berika(
        bilar,
        state,
    )

    antal_skickade = 0

    # -----------------------------------------------------
    # Bedöm varje bil
    # -----------------------------------------------------

    for bil in bilar:

        vardering = berakna_fynd(bil)

        # Ingen tillräckligt bra värdering.
        if vardering.get("niva") is None:
            continue

        # Första grova prisfiltret.
        diff = vardering.get("diff", 0)

        if diff < MIN_DIFF_FOR_CANDIDATE:
            continue

        # -------------------------------------------------
        # Beräkna den riktiga fyndscoren.
        # -------------------------------------------------

        score = berakna_fyndscore(
            bil,
            vardering,
        )

        # Score avgör om vi vill ha mejl.
        if score < MIN_SCORE_FOR_NOTIS:
            continue

        # -------------------------------------------------
        # Skicka aldrig samma bil flera gånger.
        # -------------------------------------------------

        if redan_notifierad(
            bil,
            state,
        ):
            continue

        # -------------------------------------------------
        # Formatera mejl
        # -------------------------------------------------

        text = formatera_notis(
            bil,
            vardering,
            score,
        )

        # -------------------------------------------------
        # Ämnesrad baserad på score
        # -------------------------------------------------

        if score >= 90:
            niva_etikett = "EXTREMT FYND"
        elif score >= 80:
            niva_etikett = "RIKTIGT FYND"
        else:
            niva_etikett = "MYCKET INTRESSANT"

        amne = (
            f"{'🚨' if score >= 90 else '🔥' if score >= 80 else '🟢'} "
            f"{niva_etikett}: "
            f"{bil_rubrik(bil)} "
            f"{bil.get('arsmodell')} - "
            f"{diff:,} kr under marknad"
        ).replace(",", " ")

        # -------------------------------------------------
        # Skicka direkt
        # -------------------------------------------------

        skickat = skicka_epost(
            amne,
            text,
        )

        if skickat:

            print(
                f"Mejl skickat: {amne}"
            )

            # Markera direkt så bilen aldrig skickas igen.
            markera_notifierad(
                bil,
                state,
            )

            spara_state(state)

            antal_skickade += 1

        else:

            # Misslyckat mejl innebär att bilen INTE
            # markeras som notifierad.
            print(
                "OBS: mejl INTE skickat, "
                "försöker igen nästa körning: "
                f"{amne}"
            )

    # -----------------------------------------------------
    # Sammanfattning
    # -----------------------------------------------------

    if antal_skickade == 0:
        print(
            "Inga nya fynd denna körning."
        )
    else:
        print(
            f"Totalt {antal_skickade} "
            "nya fynd mejlade denna körning."
        )


if __name__ == "__main__":
    main()
