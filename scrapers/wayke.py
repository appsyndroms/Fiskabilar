"""
Scraper för Wayke - VERIFIERAD mot verklig sidstruktur 2026-08-09,
utökad till V60+V90 2026-08-12, generaliserad till flera märken
(inkl. BMW 530e xDrive Touring) 2026-08-13.

Wayke är server-renderad (fungerar utan JavaScript), så vanlig
requests.get() räcker. Vi bygger INTE på CSS-klasser här utan på de
stabila textetiketterna ("Plats:", "Återförsäljare:", "Fuel Type:",
"Mätarställning:", "Model Year:", "Gearbox Type:", "Kontantpris") som
verifierades vara identiska för varje annonskort, oavsett märke.

URL-mönster (verifierat för volvo/v60, volvo/v90, bmw/530e-xdrive-touring):
  https://www.wayke.se/sok/{marke_slug}/{modell_slug}/{arsmodell}
  ex: https://www.wayke.se/sok/volvo/v60/2023
      https://www.wayke.se/sok/bmw/530e-xdrive-touring/2023

Notera: BMW:s modell_slug är redan variant-specifik (bara 530e xDrive
Touring, inte 530i/530d), så variant_kraven för BMW är i praktiken
alltid sant - men körs ändå genom samma generella logik för enkelhets
skull och som skydd om Wayke skulle blanda in närliggande varianter.

Enskilda annonser ligger på https://www.wayke.se/objekt/{uuid}. Sök-
sidan innehåller en sådan länk per annonskort; vi matchar länkarna mot
annonsblocken i den ordning de förekommer i HTML:n (se
_extrahera_lankar()). Om antalet länkar inte stämmer med antalet
tolkade annonser vågar vi inte gissa - då sätts url=None för alla i
den körningen, hellre än att riskera att peka på fel bil.

OBSERVERAT: paginering via ?page=2 verkade INTE ändra resultatet vid
test. Om en sökning har fler resultat än en sida visar kan Wayke ladda
fler via en "Visa fler"-knapp med JS istället - Playwright/Selenium
kan då behövas. Testa själv om du misstänker att du missar bilar.

BUGFIX 2026-08-12: sålda bilar ("Sålt" ersätter "I lager" i texten)
filtreras nu bort explicit - annars kunde de fångas upp av misstag
eftersom "I lager" bara var ett frivilligt mönster i regexen.
"""

import re
import time
import requests
from bs4 import BeautifulSoup

from config import ARSMODELL_MIN, ARSMODELL_MAX, BILAR
from scrapers import matchar_grundkrav, berika_fran_fritext, identifiera_variant

DELAY_SEKUNDER = 3.0
BAS_URL = "https://www.wayke.se/sok/{marke}/{modell}/{ar}"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
}


def _bygg_annons_regex(wayke_anchor: str) -> re.Pattern:
    """
    Bygger annonsregexen dynamiskt per bilkonfig, eftersom ankartexten
    (t.ex. "Volvo V60" eller "BMW 530e xDrive Touring") används för att
    hitta var varje annonsblock börjar. Byggd och testad mot verklig
    sidtext (se docstring ovan) för Volvo; BMW-strukturen verifierad
    separat och följer identisk mall.
    """
    return re.compile(
        r"Plats:(?P<plats>.*?)"
        r"Återförsäljare:(?P<dealer>.*?)"
        rf"(?:I lager)?{re.escape(wayke_anchor)}(?P<titel>.*?)"
        r"Fuel Type:(?P<fuel>.*?)"
        r"Mätarställning:(?P<mil>[\d\s]+?)\s*mil"
        r"Model Year:(?P<ar>\d{4})"
        r"Gearbox Type:(?P<gearbox>.*?)"
        r"Kontantpris(?P<pris>[\d\s]+?)\s*kr",
        re.DOTALL,
    )


# Fångar länkar till enskilda annonser i den ordning de förekommer i HTML:n.
OBJEKT_LANK_REGEX = re.compile(r'href="(/objekt/[0-9a-fA-F-]+)"')
WAYKE_BAS = "https://www.wayke.se"


def _extrahera_lankar(html: str, forvantat_antal: int) -> list[str | None]:
    """
    Plockar ut /objekt/-länkarna i dokumentordning. Om antalet inte
    matchar antalet hittade annonser vågar vi inte gissa vilken länk
    som hör till vilken bil - då returneras None för alla istället.
    """
    lankar = OBJEKT_LANK_REGEX.findall(html)
    unika_i_ordning = []
    for lank in lankar:
        if not unika_i_ordning or unika_i_ordning[-1] != lank:
            unika_i_ordning.append(lank)

    if len(unika_i_ordning) != forvantat_antal:
        print(f"[wayke] varning: {len(unika_i_ordning)} länkar hittade men "
              f"{forvantat_antal} annonser tolkade - hoppar över länkning "
              f"denna körning för att undvika felaktiga länkar.")
        return [None] * forvantat_antal

    return [WAYKE_BAS + lank for lank in unika_i_ordning]


def _rensa_tal(text: str) -> int:
    siffror = re.sub(r"\D", "", text)
    return int(siffror) if siffror else 0


def _tolka_titel(bilkonfig: dict, titel: str, plats: str, dealer: str) -> dict | None:
    # Sålda bilar smyger med i dealer-fältet som "...SåldVolvo V60..." eftersom
    # "Sålt"-statusen ersätter "I lager" i texten men fångas ändå av regexen
    # (som har "I lager" som frivilligt). Filtrera bort dem explicit här -
    # annars riskerar vi att mejla ut fynd på bilar som redan är sålda.
    if re.search(r"sål[dt]", dealer, re.IGNORECASE):
        return None

    # Kontrollera variant mot ANKARE+titel tillsammans, inte bara titel.
    # För Volvo räcker titel (t.ex. "Recharge T6 Core Edition"), men för
    # BMW ligger hela variantnamnet ("530e xDrive Touring") redan i
    # ankartexten - resttexten (titel) innehåller bara utrustningsdetaljer
    # som "M Sport, Drag" och skulle aldrig matcha på egen hand.
    variant = identifiera_variant(bilkonfig, f"{bilkonfig['wayke_anchor']} {titel}")
    if variant is None:
        return None  # matchar ingen av de önskade varianterna - hoppa över

    return {
        "kalla": "wayke",
        "regnr": None,  # Wayke visar inte regnr i listvyn
        "marke_slug": bilkonfig["marke_slug"],
        "modell_slug": bilkonfig["modell_slug"],
        "modell": bilkonfig["modell_slug"],  # bakåtkompatibelt fältnamn
        "variant": variant,
        "utrustningsniva": titel.strip()[:60] or None,
        "plats": plats.strip(),
        "dealer": dealer.strip(),
    }


def _hamta_sida(marke: str, modell: str, arsmodell: int) -> str:
    url = BAS_URL.format(marke=marke, modell=modell, ar=arsmodell)
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    return resp.text


def hamta_annonser() -> list[dict]:
    print("[wayke] hämtar annonser...")
    bilar = []

    for bilkonfig in BILAR:
        annons_regex = _bygg_annons_regex(bilkonfig["wayke_anchor"])

        for ar in range(ARSMODELL_MIN, ARSMODELL_MAX + 1):
            try:
                html = _hamta_sida(bilkonfig["marke_slug"], bilkonfig["modell_slug"], ar)
            except Exception as e:
                print(f"[wayke] FEL vid hämtning av {bilkonfig['marke_visning']} "
                      f"{bilkonfig['modell_visning']} årsmodell {ar}: {e}")
                continue

            text = BeautifulSoup(html, "html.parser").get_text(separator="")
            traffar = list(annons_regex.finditer(text))
            lankar = _extrahera_lankar(html, len(traffar))

            for m, lank in zip(traffar, lankar):
                bil = _tolka_titel(bilkonfig, m.group("titel"), m.group("plats"), m.group("dealer"))
                if bil is None:
                    continue

                bil.update({
                    "annonspris": _rensa_tal(m.group("pris")),
                    "arsmodell": int(m.group("ar")),
                    "miltal": _rensa_tal(m.group("mil")),
                    "vaxellada": "Automat" if "aut" in m.group("gearbox").lower() else m.group("gearbox").strip(),
                    "skadad": False,
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
                    "url": lank,
                })
                bil = berika_fran_fritext(bil, bil.get("utrustningsniva", ""))

                if matchar_grundkrav(bil):
                    bilar.append(bil)

            time.sleep(DELAY_SEKUNDER)

    print(f"[wayke] {len(bilar)} annonser matchade grundkraven")
    return bilar
