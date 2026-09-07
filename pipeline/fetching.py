"""
Hämtning av annonser för Fiskabilar.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

from app_logging.logger import info

from sources import (
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

TIDSZON = ZoneInfo(
    "Europe/Stockholm"
)


def inom_aktiv_tid() -> bool:
    """
    Returnerar True om körningen ligger inom
    Fiskabilars aktiva tidsfönster.
    """

    nu = datetime.now(
        TIDSZON
    )

    return (
        AKTIV_TID_START
        <= nu.hour
        < AKTIV_TID_SLUT
    )


def hamta_alla_annonser(
    aktiva_kallor: list[str],
) -> list[dict]:
    """
    Hämtar annonser från alla aktiva källor.

    Varje källa loggas både före och efter hämtning så att
    GitHub Actions tydligt visar att scrapern faktiskt körts,
    även när resultatet är 0 annonser.
    """

    alla = []

    for kalla in aktiva_kallor:

        modul = KALLA_TILL_MODUL.get(
            kalla
        )

        if modul is None:
            info(
                f"Okänd källa i config: {kalla}"
            )
            continue

        # --------------------------------------------------------
        # STARTA SCRAPER
        # --------------------------------------------------------

        info(
            f"[{kalla}] hämtar annonser..."
        )

        try:

            annonser = (
                modul.hamta_annonser()
            )

            # ----------------------------------------------------
            # RESULTAT FRÅN KÄLLAN
            # ----------------------------------------------------

            info(
                f"[KÄLLA] {kalla}: "
                f"{len(annonser)} annonser hämtade"
            )

            alla.extend(
                annonser
            )

        except Exception as e:

            info(
                f"[KÄLLA] {kalla}: "
                f"FEL vid hämtning: {e}"
            )

    # ------------------------------------------------------------
    # TOTALT FÖRE DEDUPLICERING
    # ------------------------------------------------------------

    info(
        f"[KÄLLA] Totalt före dedup: "
        f"{len(alla)} annonser"
    )

    return alla
