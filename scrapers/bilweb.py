"""
Scraper för Bilweb - VERIFIERAD mot verklig sidstruktur 2026-08-09,
utökad till V60+V90 2026-08-12, bugfixad 2026-08-12, generaliserad
till flera märken (inkl. BMW 530e xDrive Touring) 2026-08-13,
omskriven till årsloop 2026-08-15.

Bekräftat: Bilweb fungerar UTAN JavaScript (sidan visade fullständiga
annonser trots texten "Du har Javascript inaktiverat"), så vanlig
requests.get() räcker.

Bilweb kodar in märke, modell(grupp) och årsmodell direkt i annons-URL:en,
t.ex.:
  https://bilweb.se/orebro-lan/volvo-v60-recharge-t6-ii-ultimate-bright-2024-kombi-12825660
  https://bilweb.se/hallands-lan/bmw-530-e-xdrive-touring-ink-vinterhjul-m-sport-stop-go-2023-kombi-9769933

VIKTIGT ÄNDRING 2026-08-15: tidigare användes en enda sökning på
bilweb.se/sok/{marke}/{modell}/kombi, som bara visar FÖRSTA SIDAN,
sorterad på senast publicerad annons - INTE på årsmodell. Det gjorde
att vi i praktiken bara såg de allra senaste/nyaste bilarna (t.ex.
årsmodell 2025/2026), som sedan korrekt men poänglöst avvisades av
årsmodellskravet (2022-2024). Bilweb har - precis som Wayke - en
årsspecifik sökväg (bekräftat för volvo/v60/2023), så vi loopar nu
över ARSMODELL_MIN..ARSMODELL_MAX precis som wayke.py gör.

BMW-specifikt: url-mönstret bilweb.se/sok/bmw/530/{lan} bekräftades
fungera som eget filter (per län), vilket ger goda skäl att tro att
bilweb.se/sok/bmw/530/{år} fungerar likadant - men det är INTE lika
hundraprocentigt verifierat mot en riktig sida som volvo-mönstret.
Om BMW ger 0 träffar efter den här ändringen medan Volvo fungerar,
är det första man ska misstänka.

Eftersom den årsspecifika sökningen inte kan kombineras med "kombi"-
filtret (ospårat om det stödjer flera filter samtidigt) läggs "touring"
till som ett extra krav i BMW:s variant_kraven (se config.py) istället
- annars skulle BMW 530e xDrive SEDAN kunna smyga med, vilket du
uttryckligen inte vill ha.

BUGFIX 2026-08-12: tidigare letade koden efter annons-ID:t i en redan
HTML-taggrensad text (via BeautifulSoup.get_text()), men ID:t finns
bara i href-attributet - som försvinner helt när taggar rensas bort.
Nu används positionen i den RÅA HTML:n istället.

BUGFIX 2026-08-15: RAD_REGEX bytt till MIL_REGEX - det verkliga
formatet på Bilweb är "Mil: ... År: ..." som separata etiketter, inte
"ÅÅÅÅ, X XXX mil, Stad" i ett sammanhängande stycke som tidigare
antaget utan verifiering.
"""

import re
import time
import requests
from bs4 import BeautifulSoup

from config import BILAR, ARSMODELL_MIN, ARSMODELL_MAX
from scrapers import matchar_grundkrav, berika_fran_fritext, identifiera_variant

DELAY_SEKUNDER = 3.0
SOK_URL_MALL = "https://bilweb.se/sok/{marke}/{modell}/{ar}"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
}

MIL_REGEX = re.compile(r"Mil:\s*(.*?)\s*År:", re.DOTALL)
PRIS_REGEX = re.compile(r"Pris\s*([\d\s]+)\s*kr")


def _bygg_url_regex(marke_slug: str) -> re.Pattern:
    return re.compile(
        rf"https?://(?:www\.)?bilweb\.se/[a-zA-ZåäöÅÄÖ-]+-lan/{re.escape(marke_slug)}-(?P<slug>[a-z0-9-]+?)-(?P<ar>\d{{4}})-kombi-(?P<id>\d+)",
        re.IGNORECASE,
    )


def _rensa_tal(text: str) -> int:
    siffror = re.sub(r"\D", "", text)
    return int(siffror) if siffror else 0


def hamta_annonser() -> list[dict]:
    print("[bilweb] hämtar annonser...")
    bilar = []

    for bilkonfig in BILAR:
        marke_slug = bilkonfig["marke_slug"]
        modell_slug = bilkonfig.get("bilweb_modell_slug", bilkonfig["modell_slug"])
        url_regex = _bygg_url_regex(marke_slug)

        for ar in range(ARSMODELL_MIN, ARSMODELL_MAX + 1):
            sok_url = SOK_URL_MALL.format(marke=marke_slug, modell=modell_slug, ar=ar)

            try:
                resp = requests.get(sok_url, headers=HEADERS, timeout=15)
                resp.raise_for_status()
            except Exception as e:
                print(f"[bilweb] FEL vid hämtning av {bilkonfig['marke_visning']} "
                      f"{bilkonfig['modell_visning']} årsmodell {ar}: {e}")
                continue

            time.sleep(DELAY_SEKUNDER)

            html = resp.text
            antal_url_traffar = len(list(url_regex.finditer(html)))

            sedda_id = set()
            rak_variant = 0
            rak_rad_pris = 0
            rak_grundkrav = 0
            exempel_avvisade_slugs = []

            for m in url_regex.finditer(html):
                annons_id = m.group("id")
                if annons_id in sedda_id:
                    continue
                sedda_id.add(annons_id)

                slug_text = m.group("slug").replace("-", " ")
                variant = identifiera_variant(bilkonfig, slug_text)
                if variant is None:
                    if len(exempel_avvisade_slugs) < 3:
                        exempel_avvisade_slugs.append(slug_text)
                    continue
                rak_variant += 1

                start = m.start()
                html_fonster = html[max(0, start - 4000):start + 4000]
                lokal_text = BeautifulSoup(html_fonster, "html.parser").get_text(separator=" ")

                mil_match = MIL_REGEX.search(lokal_text)
                pris_match = PRIS_REGEX.search(lokal_text)

                if not mil_match or not pris_match:
                    continue
                rak_rad_pris += 1

                bil = {
                    "kalla": "bilweb",
                    "url": m.group(0),
                    "regnr": None,
                    "marke_slug": marke_slug,
                    "modell_slug": bilkonfig["modell_slug"],
                    "modell": bilkonfig["modell_slug"],
                    "annonspris": _rensa_tal(pris_match.group(1)),
                    "variant": variant,
                    "arsmodell": int(m.group("ar")),
                    "miltal": _rensa_tal(mil_match.group(1)),
                    "vaxellada": "Automat",
                    "skadad": False,
                    "utrustningsniva": slug_text,
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
                    rak_grundkrav += 1
                    bilar.append(bil)

            print(f"[bilweb] {bilkonfig['marke_visning']} {bilkonfig['modell_visning']} {ar}: "
                  f"{antal_url_traffar} rå-URL:er -> {rak_variant} matchade variant -> "
                  f"{rak_rad_pris} kunde tolka pris/mil -> {rak_grundkrav} klarade grundkraven")
            if exempel_avvisade_slugs:
                print(f"[bilweb]   Exempel på slugs som INTE matchade någon variant: {exempel_avvisade_slugs}")

    print(f"[bilweb] {len(bilar)} annonser matchade grundkraven totalt")
    return bilar
