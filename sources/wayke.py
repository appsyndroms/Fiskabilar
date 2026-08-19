"""
Scraper för Wayke.

Wayke är server-renderad (fungerar utan JavaScript), så vanlig
requests.get() räcker. Vi bygger INTE på CSS-klasser här utan på de
stabila textetiketterna ("Plats:", "Återförsäljare:", "Fuel Type:",
"Mätarställning:", "Model Year:", "Gearbox Type:", "Kontantpris") som
verifierats för annonskorten.

URL-mönster:
    https://www.wayke.se/sok/{marke_slug}/{modell_slug}/{arsmodell}

Exempel:
    https://www.wayke.se/sok/volvo/v60/2023
    https://www.wayke.se/sok/volvo/v90/2023
    https://www.wayke.se/sok/bmw/530e-xdrive-touring/2023

Enskilda annonser ligger på:
    https://www.wayke.se/objekt/{uuid}

Sök-sidan kan innehålla samma annonslänk flera gånger i HTML:n.
Därför dedupliceras objektlänkar globalt, men deras ursprungliga
ordning bevaras.

Om antalet unika objektlänkar fortfarande inte stämmer med antalet
tolkade annonser vågar vi inte gissa vilken länk som hör till vilken
bil. Då sätts url=None för alla annonser i den körningen.

Vid mismatch skrivs kompakt diagnostik ut med samtliga objektlänkar
och de annonser som regexen faktiskt tolkade. Detta används för att
identifiera skillnader mellan Waykes HTML-struktur och annonsregexen.

Sålda bilar filtreras bort explicit eftersom "Sålt"/"Såld" kan förekomma
i dealer-fältet där "I lager" annars förväntades.

Paginering via ?page=2 har tidigare inte ändrat resultatet vid test.
Om en sökning har fler resultat än en sida visar kan Wayke eventuellt
ladda fler via JavaScript ("Visa fler"). Playwright/Selenium kan då
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

    Ankartexten, exempelvis "Volvo V60" eller
    "BMW 530e xDrive Touring", används för att hitta var
    varje annonsblock börjar.

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


# Fångar länkar till enskilda annonser.
#
# En och samma annons kan förekomma flera gånger i HTML:n.
# Därför dedupliceras resultatet i _extrahera_lankar().
OBJEKT_LANK_REGEX = re.compile(
    r'href="(/objekt/[0-9a-fA-F-]+)"'
)


def _extrahera_lankar(
    html: str,
) -> list[str]:
    """
    Plockar ut unika /objekt/-länkar i dokumentordning.

    Alla dubletter tas bort globalt, inte bara direkt efter varandra.
    """

    hittade_lankar = OBJEKT_LANK_REGEX.findall(html)

    unika_i_ordning: list[str] = []
    sedda: set[str] = set()

    for lank in hittade_lankar:
        if lank in sedda:
            continue

        sedda.add(lank)
        unika_i_ordning.append(lank)

    return unika_i_ordning


def _logga_lankdiagnostik(
    lankar: list[str],
    traffar: list[re.Match],
    bilkonfig: dict,
    arsmodell: int,
) -> None:
    """
    Skriver diagnostik när antalet Wayke-länkar och annonsblock
    inte överensstämmer.

    Diagnostiken är avsiktligt begränsad till just den aktuella
    sökningen/årsmodellen så att Actions-loggen inte fylls med
    onödig information vid normala körningar.
    """

    warning(
        "[wayke] URL-diagnostik vid mismatch:"
    )

    warning(
        f"[wayke]   Sökning: "
        f"{bilkonfig['marke_visning']} "
        f"{bilkonfig['modell_visning']} "
        f"{arsmodell}"
    )

    warning(
        f"[wayke]   Unika objektlänkar: "
        f"{len(lankar)}"
    )

    warning(
        f"[wayke]   Tolkade annonsblock: "
        f"{len(traffar)}"
    )

    warning(
        "[wayke]   Objektlänkar:"
    )

    for index, lank in enumerate(
        lankar,
        start=1,
    ):
        warning(
            f"[wayke]     {index:02d}. "
            f"{WAYKE_BAS}{lank}"
        )

    warning(
        "[wayke]   Tolkade annonsblock:"
    )

    for index, match in enumerate(
        traffar,
        start=1,
    ):
        titel = (
            match.group("titel")
            .strip()
            .replace("\n", " ")
        )

        plats = (
            match.group("plats")
            .strip()
            .replace("\n", " ")
        )

        dealer = (
            match.group("dealer")
            .strip()
            .replace("\n", " ")
        )

        pris = (
            match.group("pris")
            .strip()
            .replace("\n", " ")
        )

        mil = (
            match.group("mil")
            .strip()
            .replace("\n", " ")
        )

        ar = (
            match.group("ar")
            .strip()
        )

        warning(
            f"[wayke]     {index:02d}. "
            f"{bilkonfig['wayke_anchor']} "
            f"{titel[:100]} | "
            f"{ar} | "
            f"{mil} mil | "
            f"{pris} kr | "
            f"{plats[:60]} | "
            f"{dealer[:60]}"
        )


def _rensa_tal(text: str) -> int:
    """Tar bort allt utom siffror och returnerar heltal."""

    siffror = re.sub(
        r"\D",
        "",
        text,
    )

    return int(siffror) if siffror else 0


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

    # Sålda bilar kan förekomma i dealer-fältet som exempelvis:
    # "...SåldVolvo V60..."
    #
    # "Sålt" och "Såld" hanteras båda.

    if re.search(
        r"sål[dt]",
        dealer,
        re.IGNORECASE,
    ):
        return None

    # Kontrollera variant mot ankare + titel tillsammans.
    #
    # För Volvo innehåller titeln ofta variantinformationen.
    # För BMW kan hela varianten redan finnas i wayke_anchor.

    variant = identifiera_variant(
        bilkonfig,
        f"{bilkonfig['wayke_anchor']} {titel}",
    )

    if variant is None:
        return None

    return {
        "kalla": "wayke",
        "regnr": None,
        "marke_slug": bilkonfig["marke_slug"],
        "modell_slug": bilkonfig["modell_slug"],
        "modell": bilkonfig["modell_slug"],
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
            bilkonfig["wayke_anchor"]
        )

        # Varje bilmodell kan ha ett eget årsintervall.
        # Om det inte anges används de globala standardvärdena.

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
                    bilkonfig["marke_slug"],
                    bilkonfig["modell_slug"],
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

            text = BeautifulSoup(
                html,
                "html.parser",
            ).get_text(
                separator=""
            )

            traffar = list(
                annons_regex.finditer(text)
            )

            lankar = _extrahera_lankar(
                html
            )

            # ========================================================
            # DIAGNOSTIK VID MISMATCH
            #
            # Vi jämför nu de faktiska unika objektlänkarna med
            # annonsblocken som regexen har tolkat.
            #
            # Om de skiljer sig skriver vi ut båda uppsättningarna.
            # Vi kopplar INTE länkar på chans.
            # ========================================================

            if len(lankar) != len(traffar):
                _logga_lankdiagnostik(
                    lankar,
                    traffar,
                    bilkonfig,
                    ar,
                )

                # Ingen länkning vid osäkerhet.
                #
                # Antalet None matchar antalet annonsblock så att
                # zip() nedan fortfarande fungerar säkert.

                lankar_for_annonser = [
                    None
                    for _ in traffar
                ]

            else:
                lankar_for_annonser = [
                    WAYKE_BAS + lank
                    for lank in lankar
                ]

            for match, lank in zip(
                traffar,
                lankar_for_annonser,
            ):
                bil = _tolka_titel(
                    bilkonfig,
                    match.group("titel"),
                    match.group("plats"),
                    match.group("dealer"),
                )

                if bil is None:
                    continue

                bil.update(
                    {
                        "annonspris": _rensa_tal(
                            match.group("pris")
                        ),
                        "arsmodell": int(
                            match.group("ar")
                        ),
                        "miltal": _rensa_tal(
                            match.group("mil")
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
                        "url": lank,
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
                    bilar.append(bil)

            time.sleep(
                DELAY_SEKUNDER
            )

    info(
        f"[wayke] {len(bilar)} annonser "
        "matchade grundkraven"
    )

    return bilar
