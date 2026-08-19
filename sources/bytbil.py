"""
Scraper för Bytbil.

STATUS: EJ VERIFIERAD (2026-08-09). Websökningen hittade inte
Bytbils faktiska sökresultatsidor den här sessionen - bara norska
Finn.no-annonser dök upp. Koden nedan är alltså fortfarande en
overifierad strukturmall.

Rekommendation: Eftersom Bilweb och Wayke tillsammans redan täcker
en stor del av marknaden (Bilweb ensam hade 1 300+ V60-annonser),
överväg att köra utan Bytbil till en början. Om du vill lägga till
den senare: öppna bytbil.com i webbläsaren, sök fram V60 Recharge,
och stäm av mot mönstret nedan (eller be mig göra en ny sökning i en
kommande session).
"""
from app_logging.logger import info

import time
import requests
from bs4 import BeautifulSoup

from sources import matchar_grundkrav, berika_fran_fritext

DELAY_SEKUNDER = 3.0
SOK_URL = "https://www.bytbil.com/Volvo/V60/sok"  # TODO: verifiera parametrar för Recharge/T6/T8

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; personligt-fyndfilter/1.0)",
}


def _tolka_annonskort(kort) -> dict | None:
    """
    TODO: Bytbil renderar troligen annonslistan server-side (HTML),
    så det här är en BeautifulSoup-baserad mall. Öppna sidans källkod
    och justera CSS-selektorerna nedan (klassnamnen är gissningar).
    """
    try:
        titel = kort.select_one(".ad-title")
        pris_el = kort.select_one(".ad-price")
        url_el = kort.select_one("a")

        titel_text = titel.get_text(strip=True) if titel else ""
        pris_text = pris_el.get_text(strip=True) if pris_el else ""
        pris = int("".join(c for c in pris_text if c.isdigit())) if pris_text else None

        bil = {
            "kalla": "bytbil",
            "url": url_el["href"] if url_el and url_el.has_attr("href") else None,
            "regnr": None,
            "annonspris": pris,
            "variant": "T6 AWD" if "t6" in titel_text.lower() else ("T8 AWD" if "t8" in titel_text.lower() else None),
            "arsmodell": None,  # TODO
            "miltal": None,     # TODO
            "vaxellada": "Automat",
            "skadad": False,
            "utrustningsniva": None,
            "antal_agare": None,
            "import": None,
            "hyrbil": None,
            "servicehistorik": None,
            "senaste_service": None,
            "nasta_service": None,
            "forsta_registrering": None,
            "dragkrok": None,
            "varmare": None,
            "volvo_selekt": None,
            "stor_batteri": None,
        }
        return berika_fran_fritext(bil, titel_text)
    except Exception as e:
        info(f"[bytbil] kunde inte tolka annonskort: {e}")
        return None


def hamta_annonser() -> list[dict]:
    info("[bytbil] hämtar annonser...")
    try:
        resp = requests.get(SOK_URL, headers=HEADERS, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        info(f"[bytbil] FEL vid hämtning: {e}. Verifiera riktig URL.")
        return []

    time.sleep(DELAY_SEKUNDER)

    soup = BeautifulSoup(resp.text, "html.parser")
    kort_lista = soup.select(".ad-card")  # TODO: verifiera faktisk CSS-klass

    bilar = []
    for kort in kort_lista:
        bil = _tolka_annonskort(kort)
        if bil and bil.get("annonspris") and matchar_grundkrav(bil):
            bilar.append(bil)

    info(f"[bytbil] {len(bilar)} annonser matchade grundkraven")
    return bilar
