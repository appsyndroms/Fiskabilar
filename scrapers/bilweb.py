"""
Scraper för Bilweb - VERIFIERAD mot verklig sidstruktur 2026-08-09,
utökad till V60+V90 2026-08-12, bugfixad 2026-08-12, generaliserad
till flera märken (inkl. BMW 530e xDrive Touring) 2026-08-13.

Bekräftat: Bilweb fungerar UTAN JavaScript (sidan visade fullständiga
annonser trots texten "Du har Javascript inaktiverat"), så vanlig
requests.get() räcker.

Bilweb kodar in märke, modell(grupp) och årsmodell direkt i annons-URL:en,
t.ex.:
  https://bilweb.se/orebro-lan/volvo-v60-recharge-t6-ii-ultimate-bright-2024-kombi-12825660
  https://bilweb.se/hallands-lan/bmw-530-e-xdrive-touring-ink-vinterhjul-m-sport-stop-go-2023-kombi-9769933

VIKTIGT: Bilweb har INTE lika granulära sök-sluggar som Wayke. För
Volvo matchar bilweb_modell_slug samma värde som Wayke (v60/v90), men
för BMW finns ingen variant-specifik slug - vi måste söka på den
bredare gruppen "530" (blandar in 530i/530d/mildhybrid) och filtrera
bort allt som inte matchar variant_kraven i efterhand, precis som vi
redan gör för T6 vs T8 på Volvo.

URL för sökning per bil (verifierat):
  https://bilweb.se/sok/{marke_slug}/{bilweb_modell_slug}/kombi

BUGFIX 2026-08-12: tidigare letade koden efter annons-ID:t i en redan
HTML-taggrensad text (via BeautifulSoup.get_text()), men ID:t finns
bara i href-attributet - som försvinner helt när taggar rensas bort.
Det gjorde att Bilweb aldrig gav en enda träff. Nu används positionen
i den RÅA HTML:n istället (där URL-matchningen redan sker), och bara
ett lokalt fönster runt den positionen taggrensas.
"""

import re
import time
import requests
from bs4 import BeautifulSoup

from config import BILAR
from scrapers import matchar_grundkrav, berika_fran_fritext, identifiera_variant

DELAY_SEKUNDER = 3.0
SOK_URL_MALL = "https://bilweb.se/sok/{marke}/{modell}/kombi"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
}

# Kompakt rad "2024, 8 176 mil, Örebro" som brukar stå nära annonsen
RAD_REGEX = re.compile(r"(\d{4}),\s*([\d\s]+)\s*mil,\s*([^\d,]+?)(?=Pris|Beräkna|$)")

PRIS_REGEX = re.compile(r"Pris\s*([\d\s]+)\s*kr")


def _bygg_url_regex(marke_slug: str) -> re.Pattern:
    """
    Matchar annons-URL:er för ett visst märke. Sluggen mellan märke och
    årtal fångas brett (den innehåller modell+utrustning hopslaget och
    formateringen varierar, t.ex. BMW:s "530-e" vs "530e") - vi filtrerar
    på INNEHÅLLET i den fångade sluggen efteråt via variant_kraven,
    istället för att försöka bygga ett exakt mönster per modell.
    """
    return re.compile(
        rf"https://bilweb\.se/[a-z-]+-lan/{re.escape(marke_slug)}-(?P<slug>[a-z0-9-]+?)-(?P<ar>\d{{4}})-kombi-(?P<id>\d+)"
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
        sok_url = SOK_URL_MALL.format(marke=marke_slug, modell=modell_slug)
        url_regex = _bygg_url_regex(marke_slug)

        try:
            resp = requests.get(sok_url, headers=HEADERS, timeout=15)
            resp.raise_for_status()
        except Exception as e:
            print(f"[bilweb] FEL vid hämtning av {bilkonfig['marke_visning']} "
                  f"{bilkonfig['modell_visning']}: {e}")
            continue

        time.sleep(DELAY_SEKUNDER)

        html = resp.text

        # DIAGNOSTIK: om sidan konsekvent ger 0 träffar utan fel är
        # misstanken att Bilweb bot-blockerar GitHub Actions IP-intervall
        # (returnerar 200 OK men en annan/tom sida). Dessa loggrader
        # avslöjar om vi ens fick förväntat innehåll tillbaka.
        print(f"[bilweb] {bilkonfig['marke_visning']} {bilkonfig['modell_visning']}: "
              f"{len(html)} tecken HTML, innehåller '{marke_slug}-': {marke_slug + '-' in html.lower()}, "
              f"innehåller 'kombi': {'kombi' in html.lower()}, "
              f"innehåller 'captcha/blocked': {'captcha' in html.lower() or 'blocked' in html.lower() or 'access denied' in html.lower()}")

        sedda_id = set()

        for m in url_regex.finditer(html):
            annons_id = m.group("id")
            if annons_id in sedda_id:
                continue  # samma annons dyker ofta upp flera gånger på sidan
            sedda_id.add(annons_id)

            slug_text = m.group("slug").replace("-", " ")
            variant = identifiera_variant(bilkonfig, slug_text)
            if variant is None:
                continue  # matchar ingen önskad variant - hoppa över

            # VIKTIGT: annons-ID:t finns bara i URL:en (href-attributet),
            # inte i den synliga texten - därför letar vi upp positionen
            # i den RÅA HTML:n (där matchningen redan skedde) och rensar
            # taggar bara i ett lokalt fönster runt den positionen.
            start = m.start()
            html_fonster = html[max(0, start - 2000):start + 2000]
            lokal_text = BeautifulSoup(html_fonster, "html.parser").get_text(separator=" ")

            rad_match = RAD_REGEX.search(lokal_text)
            pris_match = PRIS_REGEX.search(lokal_text)

            if not rad_match or not pris_match:
                continue  # kunde inte tolka - hoppa över hellre än gissa fel

            bil = {
                "kalla": "bilweb",
                "url": m.group(0),
                "regnr": None,
                "marke_slug": marke_slug,
                "modell_slug": bilkonfig["modell_slug"],
                "modell": bilkonfig["modell_slug"],  # bakåtkompatibelt fältnamn
                "annonspris": _rensa_tal(pris_match.group(1)),
                "variant": variant,
                "arsmodell": int(m.group("ar")),
                "miltal": _rensa_tal(rad_match.group(2)),
                "vaxellada": "Automat",  # sökningen filtrerar redan på kombi; verifiera vid behov
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
                bilar.append(bil)

    print(f"[bilweb] {len(bilar)} annonser matchade grundkraven")
    return bilar
