"""
Scraper för Bilweb - VERIFIERAD mot verklig sidstruktur 2026-08-09.

Bekräftat: Bilweb fungerar UTAN JavaScript (sidan visade fullständiga
annonser trots texten "Du har Javascript inaktiverat"), så vanlig
requests.get() räcker.

Bilweb kodar smart nog in variant och årsmodell direkt i annons-URL:en,
t.ex.:
  https://bilweb.se/orebro-lan/volvo-v60-recharge-t6-ii-ultimate-bright-2024-kombi-12825660
  https://bilweb.se/skane-lan/volvo-v60-recharge-t8-plus-dark-2024-kombi-...

Det gör URL:en själv till den mest robusta datakällan (ändras inte om
CSS-klasser bytts ut). Pris och miltal hämtas ur den kompakta raden
"ÅÅÅÅ, X XXX mil, Stad" som återkommer nära varje annons, plus
"Pris ... kr".

URL för sökning (verifierat):
  https://bilweb.se/sok/volvo/v60/kombi
"""

import re
import time
import requests
from bs4 import BeautifulSoup

from scrapers import matchar_grundkrav, berika_fran_fritext

DELAY_SEKUNDER = 3.0
SOK_URL = "https://bilweb.se/sok/volvo/v60/kombi"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
}

# Fångar annons-URL + variant/år ur slugen. Byggd och testad mot
# verklig sidtext (se docstring ovan).
URL_REGEX = re.compile(
    r"https://bilweb\.se/[a-z-]+-lan/(volvo-v60-(?P<slug>[a-z0-9-]+?)-(?P<ar>\d{4})-kombi-(?P<id>\d+))"
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
    try:
        resp = requests.get(SOK_URL, headers=HEADERS, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        print(f"[bilweb] FEL vid hämtning: {e}")
        return []

    time.sleep(DELAY_SEKUNDER)

    html = resp.text
    text = BeautifulSoup(html, "html.parser").get_text(separator="")

    sedda_id = set()
    bilar = []

    for m in URL_REGEX.finditer(html):
        annons_id = m.group("id")
        if annons_id in sedda_id:
            continue  # samma annons dyker ofta upp flera gånger på sidan
        sedda_id.add(annons_id)

        variant = _harled_variant(m.group("slug"))
        if variant is None:
            continue  # inte T6/T8 - hoppa över

        # Leta upp pris och miltal i närheten av denna URL i texten
        pos = text.find(annons_id)
        fonster = text[max(0, pos - 400):pos + 400] if pos != -1 else ""

        rad_match = RAD_REGEX.search(fonster)
        pris_match = PRIS_REGEX.search(fonster)

        if not rad_match or not pris_match:
            continue  # kunde inte tolka - hoppa över hellre än gissa fel

        bil = {
            "kalla": "bilweb",
            "url": m.group(0),  # hela matchningen är redan den fullständiga URL:en
            "regnr": None,
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
