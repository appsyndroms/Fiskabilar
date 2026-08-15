```python
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

    Breddad 2026-08-14: tillåter valfritt "www.", både http/https, och
    diakritiska tecken (å/ä/ö) i länsdelen av URL:en (t.ex.
    "västra-götalands-lan") - tidigare versionen krävde strikt [a-z-]+
    vilket kan ha missat län med sådana tecken om Bilweb inte alltid
    translittererar dem till orebro/skane-stil ASCII.
    """
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

        # DIAGNOSTIK: räkna faktiska regex-träffar och, om noll, visa en
        # bit av HTML:en runt "kombi-" så vi ser exakt hur en riktig
        # annons-URL faktiskt ser ut i den råa källkoden. Det avslöjar
        # om regexen bara missar formatet (t.ex. "www.", andra tecken i
        # länsdelen) eller om innehållet verkligen saknar annonser.
        forekomster_kombi = html.lower().count("-kombi-")
        antal_url_traffar = len(list(url_regex.finditer(html)))
        print(f"[bilweb] {bilkonfig['marke_visning']} {bilkonfig['modell_visning']}: "
              f"{len(html)} tecken HTML, '-kombi-' förekommer {forekomster_kombi} ggr, "
              f"url_regex matchade {antal_url_traffar} ggr")

        if antal_url_traffar == 0 and forekomster_kombi > 0:
            pos = html.lower().find("-kombi-")
            snutt = html[max(0, pos - 200):pos + 50]
            print(f"[bilweb] Snutt av rå HTML runt första '-kombi-' (för felsökning): {snutt!r}")

        sedda_id = set()
        rak_variant = 0
        rak_rad_pris = 0
        rak_grundkrav = 0
        exempel_avvisade_slugs = []
        diagnostik_utskriven = False

        for m in url_regex.finditer(html):
            annons_id = m.group("id")
            if annons_id in sedda_id:
                continue  # samma annons dyker ofta upp flera gånger på sidan
            sedda_id.add(annons_id)

            slug_text = m.group("slug").replace("-", " ")
            variant = identifiera_variant(bilkonfig, slug_text)
            if variant is None:
                if len(exempel_avvisade_slugs) < 3:
                    exempel_avvisade_slugs.append(slug_text)
                continue  # matchar ingen önskad variant - hoppa över
            rak_variant += 1

            # VIKTIGT: annons-ID:t finns bara i URL:en (href-attributet),
            # inte i den synliga texten - därför letar vi upp positionen
            # i den RÅA HTML:n (där matchningen redan skedde) och rensar
            # taggar bara i ett lokalt fönster runt den positionen.
            start = m.start()
            html_fonster = html[max(0, start - 4000):start + 4000]
            lokal_text = BeautifulSoup(html_fonster, "html.parser").get_text(separator=" ")

            rad_match = RAD_REGEX.search(lokal_text)
            pris_match = PRIS_REGEX.search(lokal_text)

            if not rad_match or not pris_match:
                if not diagnostik_utskriven:
                    diagnostik_utskriven = True
                    print(f"[bilweb] FELSÖKNING - lokal text runt en avvisad annons "
                          f"(rad_match={rad_match is not None}, pris_match={pris_match is not None}, "
                          f"lokal_text-längd={len(lokal_text)}):")
                    print(f"[bilweb]   {lokal_text!r}")
                continue  # kunde inte tolka - hoppa över hellre än gissa fel
            rak_rad_pris += 1

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
                rak_grundkrav += 1
                bilar.append(bil)

        print(f"[bilweb] {bilkonfig['marke_visning']} {bilkonfig['modell_visning']}: "
              f"{antal_url_traffar} rå-URL:er -> {rak_variant} matchade variant -> "
              f"{rak_rad_pris} kunde tolka pris/mil -> {rak_grundkrav} klarade grundkraven")
        if exempel_avvisade_slugs:
            print(f"[bilweb] Exempel på slugs som INTE matchade någon variant: {exempel_avvisade_slugs}")

    print(f"[bilweb] {len(bilar)} annonser matchade grundkraven")
    return bilar
```
