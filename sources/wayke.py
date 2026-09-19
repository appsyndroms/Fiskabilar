"""
Scraper för Wayke.

Wayke är server-renderad (fungerar utan JavaScript), så vanlig
requests.get() räcker.

VIKTIGT:
Annonsens URL och dess innehåll extraheras från samma HTML-kort.
Vi förlitar oss alltså inte längre på att:

    [14 objektlänkar] == [14 annonsblock]

ska gälla.

Wayke kan innehålla extra /objekt/-länkar i HTML:n som inte motsvarar
ett tolkningsbart annonskort. Sådana länkar ignoreras.

För varje annonskort försöker vi hitta:
- objekt-URL
- plats
- återförsäljare
- titel
- bränsle
- miltal
- årsmodell
- växellåda
- kontantpris

URL kopplas därför direkt till den annons som innehåller länken.

Om ett annonskort inte kan tolkas skrivs det ut som diagnostik,
men övriga annonser påverkas inte.

Sålda bilar filtreras bort explicit eftersom "Sålt"/"Såld" kan förekomma
i dealer-fältet.

Paginering via ?page=2 har tidigare inte ändrat resultatet vid test.
Om Wayke laddar ytterligare annonser via JavaScript kan Playwright/Selenium
behövas.
"""

from app_logging.logger import error, info, warning

import re
import time

import requests
from bs4 import BeautifulSoup

from config import ARSMODELL_MIN, ARSMODELL_MAX, BILAR
from sources import (
    berika_fran_fritext,
    identifiera_variant,
    matchar_grundkrav,
)


DELAY_SEKUNDER = 3.0

BAS_URL = "https://www.wayke.se/sok/{marke}/{modell}/{ar}"

WAYKE_BAS = "https://www.wayke.se"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    ),
}


OBJEKT_LANK_REGEX = re.compile(
    r"/objekt/[0-9a-fA-F-]+"
)


def _normalisera_text(
    text: str,
) -> str:
    """
    Normaliserar whitespace så att fält kan extraheras
    även om Wayke ändrar HTML-rader eller spacing.
    """

    return re.sub(
        r"\s+",
        " ",
        text or "",
    ).strip()


def _normalisera_diagnostiktext(
    text: str,
) -> str:
    """Gör text lämplig för kompakt diagnostik."""

    return _normalisera_text(
        text
    )


def _bygg_annons_regex(
    wayke_anchor: str,
) -> re.Pattern:
    """
    Behålls för kompatibilitet med befintligt anrop.

    Den gamla parsern använde en enda stor regex för hela kortet.
    Den nya parsern använder i första hand individuella fält.
    """

    return re.compile(
        re.escape(wayke_anchor),
        re.IGNORECASE,
    )


def _hitta_objekt_url(
    element,
) -> str | None:
    """
    Letar efter objekt-URL i ett HTML-element.

    Söker först på elementet och därefter bland dess länkar.
    """

    if element.name == "a":
        href = element.get("href")

        if href:
            match = OBJEKT_LANK_REGEX.search(
                href
            )

            if match:
                return WAYKE_BAS + match.group(0)

    for anchor in element.find_all(
        "a",
        href=True,
    ):
        href = anchor.get("href")

        match = OBJEKT_LANK_REGEX.search(
            href or ""
        )

        if match:
            return WAYKE_BAS + match.group(0)

    return None


def _hitta_annonskort(
    anchor,
):
    """
    Letar upp det närmaste HTML-element som representerar ett
    Wayke-annonskort.

    Tidigare krävdes att kortet samtidigt innehöll flera exakta
    textetiketter. Det gjorde att ett mindre HTML-/språkbyte kunde
    ge 0 tolkade annonser.

    Nu använder vi i stället en kombination av:
    - objektlänk
    - rimlig kortstorlek
    - annonsrelaterad information

    och går sedan uppåt i DOM-trädet.
    """

    element = anchor

    kandidater = []

    for _ in range(12):

        if element is None:
            break

        text = _normalisera_text(
            element.get_text(
                separator=" "
            )
        )

        if not text:
            element = element.parent
            continue

        har_annonsdata = (
            "Mätarställning" in text
            or "Model Year" in text
            or "Kontantpris" in text
            or "Fuel Type" in text
            or "Gearbox Type" in text
            or "Återförsäljare" in text
            or "Plats:" in text
            or "mil" in text.lower()
            or "kr" in text.lower()
        )

        if har_annonsdata:
            kandidater.append(
                element
            )

        # När vi kommer upp till ett mycket stort block har vi
        # sannolikt lämnat själva annonskortet.
        if len(text) > 5000:
            break

        element = element.parent

    if not kandidater:
        return None

    # Välj det minsta rimliga elementet som fortfarande innehåller
    # annonsinformation.
    kandidater.sort(
        key=lambda e: len(
            _normalisera_text(
                e.get_text(
                    separator=" "
                )
            )
        )
    )

    return kandidater[0]


def _extrahera_falt(
    text: str,
    labels: list[str],
) -> str | None:
    """
    Extraherar texten efter en etikett fram till nästa kända
    etikettliknande segment.

    Används som fallback när Waykes HTML-format förändras.
    """

    normaliserad = _normalisera_text(
        text
    )

    for label in labels:

        pattern = re.compile(
            rf"{re.escape(label)}\s*:?\s*"
            rf"(.+?)(?="
            rf"\s+(?:Plats|Återförsäljare|Fuel Type|"
            rf"Model Year|Gearbox Type|Mätarställning|"
            rf"Kontantpris|Pris)\s*:?"
            rf"|$)",
            re.IGNORECASE,
        )

        match = pattern.search(
            normaliserad
        )

        if match:
            value = match.group(
                1
            ).strip()

            if value:
                return value

    return None


def _extrahera_ar(
    text: str,
) -> int | None:
    """
    Hämtar årsmodell.
    """

    patterns = [
        r"Model Year\s*:?\s*(\d{4})",
        r"Årsmodell\s*:?\s*(\d{4})",
        r"Modellår\s*:?\s*(\d{4})",
    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            text,
            re.IGNORECASE,
        )

        if match:
            return int(
                match.group(1)
            )

    return None


def _extrahera_mil(
    text: str,
) -> int | None:
    """
    Hämtar miltal.
    """

    patterns = [
        r"Mätarställning\s*:?\s*([\d\s.,]+)\s*mil",
        r"([\d\s.,]+)\s*mil",
    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            text,
            re.IGNORECASE,
        )

        if not match:
            continue

        value = re.sub(
            r"[^\d]",
            "",
            match.group(1),
        )

        if value:
            return int(
                value
            )

    return None


def _extrahera_pris(
    text: str,
) -> int | None:
    """
    Hämtar kontantpris.

    Prioriterar uttrycklig Kontantpris men har flera fallback-format.
    """

    patterns = [
        r"Kontantpris\s*:?\s*([\d\s.,]+)\s*kr",
        r"Kontant\s*:?\s*([\d\s.,]+)\s*kr",
        r"Pris\s*:?\s*([\d\s.,]+)\s*kr",
        r"([\d\s.,]+)\s*kr",
    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            text,
            re.IGNORECASE,
        )

        if not match:
            continue

        value = re.sub(
            r"[^\d]",
            "",
            match.group(1),
        )

        if not value:
            continue

        pris = int(
            value
        )

        if pris >= 100_000:
            return pris

    return None


def _extrahera_annonskort(
    html: str,
    annons_regex: re.Pattern,
) -> list[dict]:
    """
    Extraherar annonser direkt från Waykes HTML-kort.

    URL och annonsdata kommer från samma DOM-segment.

    Den nya parsern använder individuella fält i stället för
    en enda stor regex. Det gör parsern tåligare mot mindre
    ändringar i Waykes HTML.
    """

    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    resultat: list[dict] = []
    sedda_urler: set[str] = set()

    anchors = soup.find_all(
        "a",
        href=True,
    )

    for anchor in anchors:

        href = anchor.get(
            "href",
            "",
        )

        if not OBJEKT_LANK_REGEX.search(
            href
        ):
            continue

        url = _hitta_objekt_url(
            anchor
        )

        if not url:
            continue

        if url in sedda_urler:
            continue

        kort = _hitta_annonskort(
            anchor
        )

        if kort is None:
            continue

        text = _normalisera_text(
            kort.get_text(
                separator=" "
            )
        )

        if not text:
            continue

        arsmodell = _extrahera_ar(
            text
        )

        miltal = _extrahera_mil(
            text
        )

        pris = _extrahera_pris(
            text
        )

        # Titel försöks först hämtas från Waykes anchor-text,
        # eftersom den ofta ligger närmare själva fordonsnamnet.
        titel = _normalisera_text(
            anchor.get_text(
                separator=" "
            )
        )

        if not titel:
            titel = _extrahera_falt(
                text,
                [
                    "I lager",
                ],
            )

        plats = _extrahera_falt(
            text,
            [
                "Plats",
            ],
        )

        dealer = _extrahera_falt(
            text,
            [
                "Återförsäljare",
                "Dealer",
            ],
        )

        fuel = _extrahera_falt(
            text,
            [
                "Fuel Type",
                "Bränsle",
            ],
        )

        gearbox = _extrahera_falt(
            text,
            [
                "Gearbox Type",
                "Växellåda",
            ],
        )

        if (
            arsmodell is None
            and miltal is None
            and pris is None
        ):
            continue

        sedda_urler.add(
            url
        )

        resultat.append(
            {
                "url": url,
                "titel": titel or "",
                "plats": plats or "",
                "dealer": dealer or "",
                "fuel": fuel or "",
                "gearbox": gearbox or "",
                "arsmodell": arsmodell,
                "miltal": miltal,
                "pris": pris,
                "text": text,
            }
        )

    return resultat


def _extrahera_lankar(
    html: str,
) -> list[str]:
    """
    Returnerar alla unika objektlänkar.

    Funktionen används endast för diagnostik.
    """

    hittade_lankar = OBJEKT_LANK_REGEX.findall(
        html
    )

    unika_i_ordning: list[str] = []
    sedda: set[str] = set()

    for lank in hittade_lankar:

        full_url = WAYKE_BAS + lank

        if full_url in sedda:
            continue

        sedda.add(
            full_url
        )

        unika_i_ordning.append(
            full_url
        )

    return unika_i_ordning


def _logga_lankdiagnostik(
    alla_lankar: list[str],
    annonser: list[dict],
    bilkonfig: dict,
    arsmodell: int,
) -> None:
    """
    Diagnostik för Waykes URL-/annonsmatchning.
    """

    tolkade_urler = {
        annons["url"]
        for annons in annonser
        if annons.get("url")
    }

    otolkade_lankar = [
        lank
        for lank in alla_lankar
        if lank not in tolkade_urler
    ]

    warning(
        "[wayke] URL-diagnostik:"
    )

    warning(
        f"[wayke]   Sökning: "
        f"{bilkonfig['marke_visning']} "
        f"{bilkonfig['modell_visning']} "
        f"{arsmodell}"
    )

    warning(
        f"[wayke]   Unika objektlänkar: "
        f"{len(alla_lankar)}"
    )

    warning(
        f"[wayke]   Tolkade annonskort: "
        f"{len(annonser)}"
    )

    warning(
        f"[wayke]   Objektlänkar utan "
        f"tolkningsbart annonskort: "
        f"{len(otolkade_lankar)}"
    )

    if otolkade_lankar:

        warning(
            "[wayke]   Ej tolkade länkar:"
        )

        for index, lank in enumerate(
            otolkade_lankar,
            start=1,
        ):
            warning(
                f"[wayke]     {index:02d}. "
                f"{lank}"
            )


def _rensa_tal(
    text: str,
) -> int:
    """Tar bort allt utom siffror och returnerar heltal."""

    siffror = re.sub(
        r"\D",
        "",
        text or "",
    )

    return int(
        siffror
    ) if siffror else 0


def _tolka_titel(
    bilkonfig: dict,
    titel: str,
    plats: str,
    dealer: str,
) -> dict | None:
    """
    Tolkar titel och grundinformation för ett annonsblock.

    Sålda bilar filtreras bort innan annonsen skapas.
    """

    if re.search(
        r"sål[dt]",
        dealer,
        re.IGNORECASE,
    ):
        return None

    variant = identifiera_variant(
        bilkonfig,
        f"{bilkonfig['wayke_anchor']} {titel}",
    )

    if variant is None:
        return None

    return {
        "kalla": "wayke",
        "regnr": None,
        "marke_slug": bilkonfig[
            "marke_slug"
        ],
        "modell_slug": bilkonfig[
            "modell_slug"
        ],
        "modell": bilkonfig[
            "modell_slug"
        ],
        "variant": variant,
        "utrustningsniva": (
            titel.strip()[:60]
            or None
        ),
        "plats": plats.strip(),
        "dealer": dealer.strip(),
    }


def _hamta_sida(
    marke: str,
    modell: str,
    arsmodell: int,
) -> str:
    """Hämtar en Wayke-söksida."""

    url = BAS_URL.format(
        marke=marke,
        modell=modell,
        ar=arsmodell,
    )

    resp = requests.get(
        url,
        headers=HEADERS,
        timeout=15,
    )

    resp.raise_for_status()

    return resp.text


def hamta_annonser() -> list[dict]:
    """Hämtar och tolkar annonser från Wayke."""

    info(
        "[wayke] hämtar annonser..."
    )

    bilar: list[dict] = []

    for bilkonfig in BILAR:

        annons_regex = _bygg_annons_regex(
            bilkonfig[
                "wayke_anchor"
            ]
        )

        arsmodell_min = bilkonfig.get(
            "arsmodell_min",
            ARSMODELL_MIN,
        )

        arsmodell_max = bilkonfig.get(
            "arsmodell_max",
            ARSMODELL_MAX,
        )

        for ar in range(
            arsmodell_min,
            arsmodell_max + 1,
        ):

            try:

                html = _hamta_sida(
                    bilkonfig[
                        "marke_slug"
                    ],
                    bilkonfig[
                        "modell_slug"
                    ],
                    ar,
                )

            except Exception as exc:

                error(
                    f"[wayke] FEL vid hämtning av "
                    f"{bilkonfig['marke_visning']} "
                    f"{bilkonfig['modell_visning']} "
                    f"årsmodell {ar}: {exc}"
                )

                continue

            annonskort = _extrahera_annonskort(
                html,
                annons_regex,
            )

            alla_lankar = _extrahera_lankar(
                html
            )

            if len(alla_lankar) != len(
                annonskort
            ):

                _logga_lankdiagnostik(
                    alla_lankar,
                    annonskort,
                    bilkonfig,
                    ar,
                )

            for annons in annonskort:

                titel = annons.get(
                    "titel",
                    "",
                )

                plats = annons.get(
                    "plats",
                    "",
                )

                dealer = annons.get(
                    "dealer",
                    "",
                )

                bil = _tolka_titel(
                    bilkonfig,
                    titel,
                    plats,
                    dealer,
                )

                if bil is None:
                    continue

                annonspris = annons.get(
                    "pris"
                )

                miltal = annons.get(
                    "miltal"
                )

                arsmodell_tolkad = annons.get(
                    "arsmodell"
                )

                # Ett annonskort utan pris eller årsmodell
                # ska inte bli en halv bil som sedan kan
                # förstöra history-state.
                if (
                    annonspris is None
                    or arsmodell_tolkad is None
                ):
                    warning(
                        "[wayke]   Ofullständigt "
                        f"annonskort ignoreras: "
                        f"{annons.get('url')}"
                    )
                    continue

                if miltal is None:
                    miltal = 0

                gearbox = annons.get(
                    "gearbox",
                    "",
                )

                bil.update(
                    {
                        "annonspris": annonspris,
                        "arsmodell": arsmodell_tolkad,
                        "miltal": miltal,
                        "vaxellada": (
                            "Automat"
                            if "aut"
                            in gearbox.lower()
                            else gearbox.strip()
                        ),
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
                        "url": annons[
                            "url"
                        ],
                    }
                )

                bil = berika_fran_fritext(
                    bil,
                    bil.get(
                        "utrustningsniva",
                        "",
                    ),
                )

                if matchar_grundkrav(
                    bil
                ):
                    bilar.append(
                        bil
                    )

            time.sleep(
                DELAY_SEKUNDER
            )

    info(
        f"[wayke] {len(bilar)} annonser "
        "matchade grundkraven"
    )

    return bilar
