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


def _bygg_annons_regex(wayke_anchor: str) -> re.Pattern:
    """
    Bygger annonsregexen dynamiskt per bilkonfiguration.

    Regexen bygger på de stabila textetiketter som verifierats
    på Waykes söksidor.
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


OBJEKT_LANK_REGEX = re.compile(
    r"/objekt/[0-9a-fA-F-]+"
)


def _normalisera_diagnostiktext(text: str) -> str:
    """Gör text lämplig för kompakt diagnostik."""

    return (
        text
        .strip()
        .replace("\n", " ")
        .replace("\r", " ")
    )


def _hitta_objekt_url(element) -> str | None:
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
    komplett Wayke-annonskort.

    Vi går uppåt i DOM-trädet och letar efter ett element vars text
    innehåller de stabila fälten som behövs för att tolka annonsen.

    Detta gör att URL och annonsdata kommer från samma DOM-segment.
    """

    element = anchor

    for _ in range(10):
        if element is None:
            break

        text = element.get_text(
            separator=""
        )

        if (
            "Plats:" in text
            and "Återförsäljare:" in text
            and "Mätarställning:" in text
            and "Model Year:" in text
            and "Kontantpris" in text
        ):
            return element

        element = element.parent

    return None


def _extrahera_annonskort(
    html: str,
    annons_regex: re.Pattern,
) -> list[dict]:
    """
    Extraherar annonser direkt från Waykes HTML-kort.

    Fördelen jämfört med den tidigare metoden är att vi inte längre
    behöver para ihop:

        objektlänkar[0] -> annons[0]
        objektlänkar[1] -> annons[1]

    URL:n följer i stället med det DOM-element där annonsen faktiskt
    finns.

    Returnerar poster med:

        {
            "url": ...,
            "match": re.Match,
        }

    Dubbletter av samma objekt-ID tas bort.
    """

    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    resultat: list[dict] = []
    sedda_urler: set[str] = set()

    # Alla länkar till enskilda objekt.
    anchors = soup.find_all(
        "a",
        href=OBJEKT_LANK_REGEX,
    )

    for anchor in anchors:
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

        text = kort.get_text(
            separator=""
        )

        match = annons_regex.search(
            text
        )

        if not match:
            continue

        sedda_urler.add(url)

        resultat.append(
            {
                "url": url,
                "match": match,
            }
        )

    return resultat


def _extrahera_lankar(
    html: str,
) -> list[str]:
    """
    Returnerar alla unika objektlänkar.

    Funktionen används endast för diagnostik.
    URL-länkningen av annonser sker numera via
    _extrahera_annonskort().
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

        sedda.add(full_url)
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

    Den gamla logiken betraktade varje skillnad i antal som ett
    totalt mismatch.

    Den nya logiken visar i stället:

        alla objektlänkar
        faktiskt tolkade annonser

    eftersom dessa nu extraheras från samma HTML-struktur.
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

    if not otolkade_lankar:
        return

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


def _logga_annonsdiagnostik(
    annonser: list[dict],
    bilkonfig: dict,
    arsmodell: int,
) -> None:
    """
    Kort diagnostik över de annonser som faktiskt tolkades.

    Används bara när URL-diagnostik behövs.
    """

    warning(
        "[wayke]   Tolkade annonskort:"
    )

    for index, annons in enumerate(
        annonser,
        start=1,
    ):
        match = annons["match"]

        titel = _normalisera_diagnostiktext(
            match.group("titel")
        )

        plats = _normalisera_diagnostiktext(
            match.group("plats")
        )

        dealer = _normalisera_diagnostiktext(
            match.group("dealer")
        )

        pris = _normalisera_diagnostiktext(
            match.group("pris")
        )

        mil = _normalisera_diagnostiktext(
            match.group("mil")
        )

        ar = _normalisera_diagnostiktext(
            match.group("ar")
        )

        warning(
            f"[wayke]     {index:02d}. "
            f"{bilkonfig['wayke_anchor']} "
            f"{titel[:100]} | "
            f"{ar} | "
            f"{mil} mil | "
            f"{pris} kr | "
            f"{plats[:60]} | "
            f"{dealer[:60]} | "
            f"{annons['url']}"
        )


def _rensa_tal(
    text: str,
) -> int:
    """Tar bort allt utom siffror och returnerar heltal."""

    siffror = re.sub(
        r"\D",
        "",
        text,
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

            # --------------------------------------------------------
            # NY URL-HANTERING
            #
            # URL och annonsdata hämtas från samma DOM-kort.
            #
            # Det betyder att en extra Wayke-länk inte längre gör att
            # alla andra URL:er måste kastas bort.
            # --------------------------------------------------------

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
                match = annons["match"]

                bil = _tolka_titel(
                    bilkonfig,
                    match.group(
                        "titel"
                    ),
                    match.group(
                        "plats"
                    ),
                    match.group(
                        "dealer"
                    ),
                )

                if bil is None:
                    continue

                bil.update(
                    {
                        "annonspris": _rensa_tal(
                            match.group(
                                "pris"
                            )
                        ),
                        "arsmodell": int(
                            match.group(
                                "ar"
                            )
                        ),
                        "miltal": _rensa_tal(
                            match.group(
                                "mil"
                            )
                        ),
                        "vaxellada": (
                            "Automat"
                            if "aut"
                            in match.group(
                                "gearbox"
                            ).lower()
                            else match.group(
                                "gearbox"
                            ).strip()
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
