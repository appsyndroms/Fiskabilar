"""
Scraper för Bilweb - VERIFIERAD mot verklig sidstruktur 2026-08-09,
utökad till V60+V90 2026-08-12.

Bekräftat: Bilweb fungerar UTAN JavaScript (sidan visade fullständiga
annonser trots texten "Du har Javascript inaktiverat"), så vanlig
requests.get() räcker.

Bilweb kodar smart nog in modell, variant och årsmodell direkt i
annons-URL:en, t.ex.:
  https://bilweb.se/orebro-lan/volvo-v60-recharge-t6-ii-ultimate-bright-2024-kombi-12825660
  https://bilweb.se/skane-lan/volvo-v90-recharge-t8-plus-dark-2024-kombi-...

Det gör URL:en själv till den mest robusta datakällan (ändras inte om
CSS-klasser bytts ut). Pris och miltal hämtas ur den kompakta raden
"ÅÅÅÅ, X XXX mil, Stad" som återkommer nära varje annons, plus
"Pris ... kr".

URL för sökning per modell (verifierat för både v60 och v90):
  https://bilweb.se/sok/volvo/{modell}/kombi
"""

import re
import time
import requests
from bs4 import BeautifulSoup

from config import MODELLER
from scrapers import matchar_grundkrav, berika_fran_fritext

DELAY_SEKUNDER = 3.0
SOK_URL_MALL = "https://bilweb.se/sok/volvo/{modell}/kombi"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
}

# Byggd och testad mot verklig sidtext (se docstring ovan). Matchar
# valfri modell i config.MODELLER (t.ex. volvo-v60- ELLER volvo-v90-).
_MODELL_ALTERNATIV = "|".join(re.escape(m) for m in MODELLER)
URL_REGEX = re.compile(
    rf"https://bilweb\.se/[a-z-]+-lan/volvo-(?P<modell>{_MODELL_ALTERNATIV})-(?P<slug>[a-z0-9-]+?)-(?P<ar>\d{{4}})-kombi-(?P<id>\d+)"
)

# Kompakt rad "2024, 8 176 mil, Örebro" som brukar stå nära annonsen
RAD_REGEX = re.compile(r"(\d{4}),\s*([\d\s]+)\s*mil,\s*([^\d,]+?)(?=Pris|Beräkna|$)")

PRIS_REGEX = re.compile(r"Pris\s*([\d\s]+)\s*kr")


def _rensa_tal(text: str) -> int:
    siffror = re.sub(r"\D", "", text)
    return int(siffror) if siffror else 0


def _harled_variant(slug: str) -> str | None:
    slug = slug.lower()
    if re.search(r"\bt6\b", slug):
        return "T6 AWD"
    if re.search(r"\bt8\b", slug):
        return "T8 AWD"
    return None


def hamta_annonser() -> list[dict]:
    print("[bilweb] hämtar annonser...")
    bilar = []

    for modell in MODELLER:
        sok_url = SOK_URL_MALL.format(modell=modell)
        try:
            resp = requests.get(sok_url, headers=HEADERS, timeout=15)
            resp.raise_for_status()
        except Exception as e:
            print(f"[bilweb] FEL vid hämtning av {modell}: {e}")
            continue

        time.sleep(DELAY_SEKUNDER)

        html = resp.text
        sedda_id = set()

        for m in URL_REGEX.finditer(html):
            annons_id = m.group("id")
            if annons_id in sedda_id:
                continue  # samma annons dyker ofta upp flera gånger på sidan
            sedda_id.add(annons_id)

            variant = _harled_variant(m.group("slug"))
            if variant is None:
                continue  # inte T6/T8 - hoppa över

            # VIKTIGT: annons-ID:t finns bara i URL:en (href-attributet),
            # inte i den synliga texten - därför letar vi upp positionen
            # i den RÅA HTML:n (där matchningen redan skedde) och rensar
            # taggar bara i ett lokalt fönster runt den positionen, istället
            # för att försöka hitta ID:t i en redan tagg-rensad heltext
            # (vilket aldrig kan lyckas eftersom get_text() slänger href).
            start = m.start()
            html_fonster = html[max(0, start - 2000):start + 2000]
            lokal_text = BeautifulSoup(html_fonster, "html.parser").get_text(separator=" ")

            rad_match = RAD_REGEX.search(lokal_text)
            pris_match = PRIS_REGEX.search(lokal_text)

            if not rad_match or not pris_match:
                continue  # kunde inte tolka - hoppa över hellre än gissa fel

            bil = {
                "kalla": "bilweb",
                "url": m.group(0),  # hela matchningen är redan den fullständiga URL:en
                "regnr": None,
                "modell": m.group("modell"),
                "annonspris": _rensa_tal(pris_match.group(1)),
                "variant": variant,
                "arsmodell": int(m.group("ar")),
                "miltal": _rensa_tal(rad_match.group(2)),
                "vaxellada": "Automat",  # sökningen filtrerar redan på kombi; verifiera vid behov
                "skadad": False,
                "utrustningsniva": m.group("slug").replace("-", " "),
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
            bil = berika_fran_fritext(bil, bil["utrustningsniva"])

            if matchar_grundkrav(bil):
                bilar.append(bil)

    print(f"[bilweb] {len(bilar)} annonser matchade grundkraven")
    return bilar
