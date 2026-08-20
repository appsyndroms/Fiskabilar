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

        try:
            annonser = (
                modul.hamta_annonser()
            )

            info(
                f"[KÄLLA] {kalla}: "
                f"{len(annonser)} annonser"
            )

            alla.extend(
                annonser
            )

        except Exception as e:
            info(
                f"FEL i källa "
                f"'{kalla}': {e}"
            )

    return alla
