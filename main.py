"""
Fiskabilar - huvudscript.

Huvudflöde:
1. Kontrollera aktiv tid.
2. Hämta annonser.
3. Deduplicera.
4. Uppdatera state.
5. Läs och berika med långtidshistorik.
6. Spara dagens annonsobservationer.
7. Bygg marknadsunderlag.
8. Processa kandidater.
9. Kör trendanalys.
10. Spara state.
11. Skriv diagnostik och sammanfattning.

Detaljerad logik ligger i pipeline-modulerna.
"""

from app_logging.logger import info, configure_from_argv

from config import AKTIVA_KALLOR
from matching.deduplicate import deduplicera

from history.state import (
    ladda_state,
    spara_state,
    uppdatera_och_berika,
)

from history.analysis import (
    bygg_historikindex,
    berika_med_historik,
    spara_annonsobservation,
    bygg_marknadstrender,
)

from valuation.market_value import bygg_marknadsunderlag

from pipeline.fetching import (
    inom_aktiv_tid,
    hamta_alla_annonser,
)

from pipeline.candidates import processa_kandidater

from pipeline.diagnostics import (
    skriv_diagnostik,
    skriv_sammanfattning,
)


def main():
    info("\n=== Bilfyndfilter startar ===\n")

    if not inom_aktiv_tid():
        info("Utanför aktiv tid. Avslutar.")
        return

    # ------------------------------------------------------------
    # HÄMTNING
    # ------------------------------------------------------------

    raa_annonser = hamta_alla_annonser(
        AKTIVA_KALLOR
    )

    info(
        f"Totalt {len(raa_annonser)} "
        "annonser innan dedup"
    )

    bilar = deduplicera(
        raa_annonser
    )

    info(
        f"{len(bilar)} "
        "unika bilar efter dedup"
    )

    # ------------------------------------------------------------
    # STATE
    # ------------------------------------------------------------

    state = ladda_state()

    bilar = uppdatera_och_berika(
        bilar,
        state,
    )

    # ------------------------------------------------------------
    # HISTORIK
    # ------------------------------------------------------------

    historikindex = bygg_historikindex()

    for bil in bilar:
        try:
            berika_med_historik(
                bil,
                historikindex,
            )

        except Exception as e:
            info(
                "[HISTORIK] Kunde inte läsa "
                f"historik för annons: {e}"
            )

    for bil in bilar:
        try:
            spara_annonsobservation(
                bil
            )

        except Exception as e:
            info(
                "[HISTORIK] Kunde inte spara "
                f"annonsobservation: {e}"
            )

    # ------------------------------------------------------------
    # MARKNAD
    # ------------------------------------------------------------

    marknadsunderlag = bygg_marknadsunderlag(
        bilar
    )

    info(
        f"{len(marknadsunderlag)} "
        "marknadskategorier byggda"
    )

    # ------------------------------------------------------------
    # KANDIDATER / VALUATION / SCORE / MEJL
    # ------------------------------------------------------------

    statistik, kandidater = processa_kandidater(
        bilar=bilar,
        marknadsunderlag=marknadsunderlag,
        state=state,
    )

    # ------------------------------------------------------------
    # TRENDANALYS
    # ------------------------------------------------------------

    try:
        bygg_marknadstrender()

    except Exception as e:
        info(
            "[TREND] Kunde inte köra "
            f"trendanalysen: {e}"
        )

    # ------------------------------------------------------------
    # STATE
    # ------------------------------------------------------------

    spara_state(
        state
    )

    # ------------------------------------------------------------
    # DIAGNOSTIK
    # ------------------------------------------------------------

    skriv_diagnostik(
        kandidater
    )

    skriv_sammanfattning(
        statistik
    )


if __name__ == "__main__":
    configure_from_argv()
    main()
