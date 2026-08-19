"""
Scraper för Blocket.

VIKTIGT (läs innan du kör detta live):
Blocket har aktivt anti-bot-skydd (bl.a. Datadome) och deras
användarvillkor tillåter inte automatiserad datainsamling i strid mot
sajtens spärrar. Koden nedan är en STRUKTURMALL: den visar hur sökningen
och parsningen ska hänga ihop, men de faktiska CSS-selektorerna/API-
anropen måste du själv verifiera i din webbläsares utvecklarverktyg
(Nätverksfliken -> leta efter Blockets interna JSON-API som sidan
faktiskt anropar - det är oftast enklare och stabilare än att parsa HTML).

Rekommendation: kör detta script med rimlig fördröjning mellan anrop
(se DELAY nedan), sätt en vanlig User-Agent, och sluta genast om du
ser captcha/blockering istället för att kringgå den.
"""
from app_logging.logger import info

import time
import requests

from sources import matchar_grundkrav, berika_fran_fritext

SOKORD = "volvo v60 recharge"
DELAY_SEKUNDER = 3.0

# TODO: verifiera aktuell endpoint via webbläsarens nätverksflik.
# Detta är en PLACEHOLDER-URL, inte ett bekräftat API.
SOK_URL = "https://api.blocket.se/search_bff/v2/content?q=volvo+v60+recharge&cg=1401"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; personligt-fyndfilter/1.0)",
}


def _tolka_annons(raw: dict) -> dict | None:
    """
    TODO: mappa om enligt Blockets faktiska JSON-struktur.
    Fälten nedan är exempel på vad du sannolikt behöver plocka ut.
    """
    try:
        titel = raw.get("subject", "")
        pris = raw.get("price", {}).get("value")
        text = raw.get("body", "")

        bil = {
            "kalla": "blocket",
            "url": raw.get("share_url") or raw.get("url"),
            "regnr": None,  # sällan i annonstext, ofta dolt
            "annonspris": pris,
            "variant": "T6 AWD" if "t6" in titel.lower() else ("T8 AWD" if "t8" in titel.lower() else None),
            "arsmodell": None,  # TODO: plocka ur strukturerade fält om de finns
            "miltal": None,     # TODO: plocka ur strukturerade fält (mätarställning)
            "vaxellada": "Automat",
            "skadad": "skadad" in text.lower() or "rep-objekt" in text.lower(),
            "utrustningsniva": None,
            "antal_agare": None,
            "import": "import" in text.lower(),
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
        bil = berika_fran_fritext(bil, titel + " " + text)
        return bil
    except Exception as e:
        info(f"[blocket] kunde inte tolka annons: {e}")
        return None


def hamta_annonser() -> list[dict]:
    info("[blocket] hämtar annonser...")
    try:
        resp = requests.get(SOK_URL, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        info(f"[blocket] FEL vid hämtning: {e}. "
              f"Endpointen ovan är en placeholder - verifiera riktig URL.")
        return []

    time.sleep(DELAY_SEKUNDER)

    raw_annonser = data.get("data", [])  # TODO: verifiera faktisk nyckel
    bilar = []
    for raw in raw_annonser:
        bil = _tolka_annons(raw)
        if bil and bil.get("annonspris") and matchar_grundkrav(bil):
            bilar.append(bil)

    info(f"[blocket] {len(bilar)} annonser matchade grundkraven")
    return bilar
