"""
Scraper för Wayke - VERIFIERAD mot verklig sidstruktur 2026-08-09.

Wayke är server-renderad (fungerar utan JavaScript), så vanlig
requests.get() räcker. Vi bygger INTE på CSS-klasser här utan på de
stabila textetiketterna ("Plats:", "Återförsäljare:", "Fuel Type:",
"Mätarställning:", "Model Year:", "Gearbox Type:", "Kontantpris") som
verifierades vara identiska för varje annonskort. Det är mer robust
mot att Wayke ändrar styling/CSS-klasser.

URL-mönster (verifierat):
  https://www.wayke.se/sok/volvo/v60/{arsmodell}
  ex: https://www.wayke.se/sok/volvo/v60/2023

Enskilda annonser ligger på https://www.wayke.se/objekt/{uuid} (verifierat
via en riktig annons). Sök-sidan innehåller en sådan länk per annonskort;
vi matchar länkarna mot annonsblocken i den ordning de förekommer i HTML:n
(se _extrahera_lankar()). Om Wayke någon gång skulle lägga till extra
/objekt/-länkar utanför listkorten (t.ex. i en "liknande bilar"-sektion)
kan ordningen glida - därför jämför koden antalet länkar mot antalet
annonser och struntar i länkningen (sätter url=None) om de inte stämmer,
hellre än att riskera att peka på fel bil.

OBSERVERAT: paginering via ?page=2 verkade INTE ändra resultatet vid
test (samma bilar oavsett sida-parameter). Om Wayke har fler resultat
än vad som visas på en sida kan de laddas via en "Visa fler"-knapp
med JS istället. Testa själv och justera om du misstänker att du
missar bilar - i så fall kan Playwright/Selenium behövas istället.
"""

import re
import time
import requests
from bs4 import BeautifulSoup

from config import ARSMODELL_MIN, ARSMODELL_MAX
from scrapers import matchar_grundkrav, berika_fran_fritext

DELAY_SEKUNDER = 3.0
BAS_URL = "https://www.wayke.se/sok/volvo/v60/{ar}"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
}

# Byggd och testad mot verklig sidtext (se docstring ovan).
ANNONS_REGEX = re.compile(
    r"Plats:(?P<plats>.*?)"
    r"Återförsäljare:(?P<dealer>.*?)"
    r"(?:I lager)?Volvo V60(?P<titel>.*?)"
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
    # Ta bort ev. dubbletter i följd (samma bil kan länkas två gånger
    # inom samma kort, t.ex. både bild och rubrik)
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


def _tolka_titel(titel: str, plats: str, dealer: str) -> dict | None:
    variant = None
    if re.search(r"\bt6\b", titel, re.IGNORECASE):
        variant = "T6 AWD"
    elif re.search(r"\bt8\b", titel, re.IGNORECASE):
        variant = "T8 AWD"

    if variant is None:
        return None  # inte T6/T8 (t.ex. B4-diesel) - hoppa över

    return {
        "kalla": "wayke",
        "regnr": None,  # Wayke visar inte regnr i listvyn
        "variant": variant,
        "utrustningsniva": titel.strip()[:60] or None,
        "plats": plats.strip(),
        "dealer": dealer.strip(),
    }


def _hamta_sida(arsmodell: int) -> str:
    url = BAS_URL.format(ar=arsmodell)
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    return resp.text


def hamta_annonser() -> list[dict]:
    print("[wayke] hämtar annonser...")
    bilar = []

    for ar in range(ARSMODELL_MIN, ARSMODELL_MAX + 1):
        try:
            html = _hamta_sida(ar)
        except Exception as e:
            print(f"[wayke] FEL vid hämtning av årsmodell {ar}: {e}")
            continue

        text = BeautifulSoup(html, "html.parser").get_text(separator="")
        traffar = list(ANNONS_REGEX.finditer(text))
        lankar = _extrahera_lankar(html, len(traffar))

        for m, lank in zip(traffar, lankar):
            bil = _tolka_titel(m.group("titel"), m.group("plats"), m.group("dealer"))
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
