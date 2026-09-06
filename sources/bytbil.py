"""
Scraper för Bytbil.

Bytbil-scrapern ska endast hämta och normalisera rådata.
Vilka modeller, varianter och årsmodeller som är intressanta
styrs av config.py.

Aktuella modeller hämtas från BILAR i config.py.

Scrapern använder Bytbils dataLayer/ecommerce.impressions som
primär källa eftersom annonserna inte ligger som vanliga statiska
annonskort i HTML.

Därefter används annonslänkar och vid behov annonsens detaljsida
för att komplettera data som årsmodell och miltal.

Resultatet skickas genom samma gemensamma grundkravslogik som
övriga källor.
"""

from __future__ import annotations

import json
import re
import time
from ast import literal_eval
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from app_logging.logger import info

from config import BILAR

from sources import (
    berika_fran_fritext,
    grundkrav_fel,
    identifiera_variant,
)


DELAY_SEKUNDER = 0.5

BAS_URL = "https://www.bytbil.com"


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 "
        "(Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/131.0.0.0 "
        "Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,"
        "application/xml;q=0.9,image/avif,image/webp,"
        "image/apng,*/*;q=0.8"
    ),
    "Accept-Language": (
        "sv-SE,sv;q=0.9,en-US;q=0.8,en;q=0.7"
    ),
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}


# ----------------------------------------------------------------------
# Bytbil URL-struktur
# ----------------------------------------------------------------------

def _bygg_sok_url(
    bilkonfig: dict,
) -> str | None:
    """
    Bygger Bytbils sök-URL från bilkonfigurationen.

    Detta är endast en mappning till Bytbils URL-struktur.
    Själva urvalet av modeller/varianter/årsmodeller ligger i config.py.
    """

    marke = (
        bilkonfig.get("marke_slug")
        or ""
    ).lower()

    modell = (
        bilkonfig.get("modell_slug")
        or ""
    ).lower()

    if marke == "volvo":
        if modell == "v60":
            return (
                f"{BAS_URL}/bil/volvo/v60"
            )

        if modell == "v90":
            return (
                f"{BAS_URL}/bil/volvo/v90"
            )

    if marke == "bmw":
        if modell.startswith("330e"):
            return (
                f"{BAS_URL}/bil/bmw/3-serie"
            )

        if modell.startswith("530e"):
            return (
                f"{BAS_URL}/bil/bmw/5-serie"
            )

    info(
        "[bytbil] VARNING: kunde inte bygga sök-URL "
        f"för {bilkonfig.get('modell_visning')}"
    )

    return None


# ----------------------------------------------------------------------
# Text / numeriska värden
# ----------------------------------------------------------------------

def _rensa_text(
    value,
) -> str:
    """Rensar text från överflödiga whitespace-tecken."""

    if value is None:
        return ""

    return re.sub(
        r"\s+",
        " ",
        str(value),
    ).strip()


def _tolka_pris(
    value,
) -> int | None:
    """
    Tolkar ett pris.

    Exempel:
        279 000
        279000
        279 000 kr
        279.000 kr
    """

    if value is None:
        return None

    text = _rensa_text(value)

    if not text:
        return None

    match = re.search(
        r"(\d[\d\s.,\xa0]{3,})",
        text,
    )

    if not match:
        return None

    nummer = (
        match.group(1)
        .replace("\xa0", "")
        .replace(" ", "")
        .replace(".", "")
        .replace(",", "")
    )

    if not nummer.isdigit():
        return None

    pris = int(nummer)

    if pris < 10_000:
        return None

    return pris


def _tolka_arsmodell(
    value,
) -> int | None:
    """Försöker hitta årsmodell i text."""

    if value is None:
        return None

    text = _rensa_text(value)

    match = re.search(
        r"\b(19[9]\d|20\d{2})\b",
        text,
    )

    if not match:
        return None

    arsmodell = int(
        match.group(1)
    )

    if not 1990 <= arsmodell <= 2030:
        return None

    return arsmodell


def _tolka_miltal(
    value,
) -> float | None:
    """
    Försöker hitta miltal.

    Exempel:
        5 922 mil
        5922 mil
        9 020 mil
    """

    if value is None:
        return None

    text = _rensa_text(value)

    match = re.search(
        r"(\d[\d\s\xa0]*(?:[,.]\d+)?)\s*mil\b",
        text,
        re.IGNORECASE,
    )

    if not match:
        return None

    nummer = (
        match.group(1)
        .replace(" ", "")
        .replace("\xa0", "")
        .replace(",", ".")
    )

    try:
        miltal = float(
            nummer
        )
    except ValueError:
        return None

    if miltal < 0:
        return None

    return miltal


# ----------------------------------------------------------------------
# Konfigurationsmatchning
# ----------------------------------------------------------------------

def _matcha_bilkonfig(
    sok_bilkonfig: dict,
    text: str,
) -> str | None:
    """
    Identifierar variant enligt config.py.

    Ingen variant är hårdkodad här.
    """

    return identifiera_variant(
        sok_bilkonfig,
        text,
    )


# ----------------------------------------------------------------------
# JavaScript/dataLayer
# ----------------------------------------------------------------------

def _balanserad_del(
    text: str,
    start: int,
    oppning: str,
    stangning: str,
) -> str | None:
    """
    Hämtar en balanserad JS/JSON-del från en given position.

    Används för att plocka ut exempelvis:

        impressions: [ ... ]

    även när innehållet inte är strikt JSON.
    """

    if (
        start < 0
        or start >= len(text)
        or text[start] != oppning
    ):
        return None

    djup = 0
    i = start

    in_string = False
    string_tecken = None
    escaped = False

    while i < len(text):

        tecken = text[i]

        if in_string:

            if escaped:
                escaped = False

            elif tecken == "\\":
                escaped = True

            elif tecken == string_tecken:
                in_string = False

            i += 1
            continue

        if tecken in (
            '"',
            "'",
            "`",
        ):
            in_string = True
            string_tecken = tecken
            i += 1
            continue

        if tecken == oppning:
            djup += 1

        elif tecken == stangning:
            djup -= 1

            if djup == 0:
                return text[
                    start:i + 1
                ]

        i += 1

    return None


def _hamta_impressions_block(
    script_text: str,
) -> str | None:
    """
    Letar efter ecommerce.impressions/productList/impressions
    i ett JavaScript-script.
    """

    monster = re.compile(
        r"""
        (?:
            ecommerce
            |
            productList
            |
            impressions
        )
        \s*
        :
        \s*
        ($begin:math:display$\)
        \"\"\"\,
        re\.IGNORECASE \| re\.VERBOSE\,
    \)

    for match in monster\.finditer\(
        script\_text
    \)\:
        start \= match\.start\(1\)

        block \= \_balanserad\_del\(
            script\_text\,
            start\,
            \"\[\"\,
            \"\]\"\,
        \)

        if block\:
            return block

    return None


def \_js\_till\_python\(
    text\: str\,
\)\:
    \"\"\"
    Försöker konvertera ett JavaScript\-liknande objekt
    till Python\-data\.

    Först testas strikt JSON\.
    Därefter literal\_eval för JS\-objekt som råkar vara
    kompatibla med Python\-literals\.
    \"\"\"

    if not text\:
        return None

    \# \-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-
    \# Strikt JSON
    \# \-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-

    try\:
        return json\.loads\(text\)

    except \(
        json\.JSONDecodeError\,
        TypeError\,
    \)\:
        pass

    \# \-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-
    \# Python\-liknande objekt
    \# \-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-

    try\:
        return literal\_eval\(
            text
        \)

    except \(
        ValueError\,
        SyntaxError\,
    \)\:
        pass

    \# \-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-
    \# Försök normalisera vanliga JS\-varianter
    \# \-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-

    normaliserad \= text

    normaliserad \= re\.sub\(
        r\"\\btrue\\b\"\,
        \"True\"\,
        normaliserad\,
        flags\=re\.IGNORECASE\,
    \)

    normaliserad \= re\.sub\(
        r\"\\bfalse\\b\"\,
        \"False\"\,
        normaliserad\,
        flags\=re\.IGNORECASE\,
    \)

    normaliserad \= re\.sub\(
        r\"\\bnull\\b\"\,
        \"None\"\,
        normaliserad\,
        flags\=re\.IGNORECASE\,
    \)

    \# JS trailing commas
    normaliserad \= re\.sub\(
        r\"\,\\s\*\(\[\}$end:math:display$])",
        r"\1",
        normaliserad,
    )

    # Ofta förekommer enkla citattecken.
    try:
        return literal_eval(
            normaliserad
        )

    except (
        ValueError,
        SyntaxError,
    ):
        return None


def _hamta_datalayer_produkter(
    soup: BeautifulSoup,
) -> list[dict]:
    """
    Hämtar produkt/impression-objekt från Bytbils dataLayer.

    Bytbil renderar annonserna i JavaScript och därför är
    dataLayer betydligt mer användbar än att försöka gissa
    CSS-klasser.
    """

    produkter = []

    for script in soup.find_all(
        "script"
    ):

        text = script.string

        if not text:
            text = script.get_text()

        if not text:
            continue

        if (
            "impressions" not in text.lower()
            and "productlist" not in text.lower()
        ):
            continue

        block = _hamta_impressions_block(
            text
        )

        if not block:
            continue

        data = _js_till_python(
            block
        )

        if isinstance(
            data,
            list,
        ):
            for item in data:

                if isinstance(
                    item,
                    dict,
                ):
                    produkter.append(
                        item
                    )

        if produkter:
            continue

        # ----------------------------------------------------------
        # Fallback:
        # plocka ut objekt ett och ett om arrayen inte gick att
        # tolka som helhet.
        # ----------------------------------------------------------

        objekt_start = 0

        while True:

            objekt_start = block.find(
                "{",
                objekt_start,
            )

            if objekt_start < 0:
                break

            objekt = _balanserad_del(
                block,
                objekt_start,
                "{",
                "}",
            )

            if not objekt:
                break

            data = _js_till_python(
                objekt
            )

            if isinstance(
                data,
                dict,
            ):
                produkter.append(
                    data
                )

            objekt_start += len(
                objekt
            )

    return produkter


# ----------------------------------------------------------------------
# Generisk fältåtkomst
# ----------------------------------------------------------------------

def _hamta_falt(
    objekt: dict,
    *namn,
):
    """
    Hämtar första existerande fältet.

    Tillåter även nästlade dictionaries.
    """

    if not isinstance(
        objekt,
        dict,
    ):
        return None

    for namnvariant in namn:

        if namnvariant in objekt:
            value = objekt.get(
                namnvariant
            )

            if value not in (
                None,
                "",
            ):
                return value

        # Stöd för punktnotation.
        delar = namnvariant.split(
            "."
        )

        aktuell = objekt

        lyckades = True

        for delnamn in delar:

            if not isinstance(
                aktuell,
                dict,
            ):
                lyckades = False
                break

            if delnamn not in aktuell:
                lyckades = False
                break

            aktuell = aktuell[
                delnamn
            ]

        if lyckades and aktuell not in (
            None,
            "",
        ):
            return aktuell

    return None


# ----------------------------------------------------------------------
# Annonslänkar
# ----------------------------------------------------------------------

def _hamta_annonslankar(
    soup: BeautifulSoup,
) -> list[dict]:
    """
    Hämtar alla Bytbil-länkar som ser ut som riktiga annonser.
    """

    resultat = []
    sedda = set()

    for a in soup.find_all(
        "a",
        href=True,
    ):

        href = a.get(
            "href"
        )

        if not href:
            continue

        href_lower = href.lower()

        if "/bil/" not in href_lower:
            continue

        full_url = urljoin(
            BAS_URL,
            href,
        )

        # Hoppa över generella kategorisidor.
        path = full_url.lower().split(
            "?",
            1,
        )[0].rstrip("/")

        if path in {
            "/bil",
            "/bil/volvo",
            "/bil/volvo/v60",
            "/bil/volvo/v90",
            "/bil/bmw",
            "/bil/bmw/3-serie",
            "/bil/bmw/5-serie",
        }:
            continue

        if full_url in sedda:
            continue

        sedda.add(
            full_url
        )

        text = _rensa_text(
            a.get_text(
                " ",
                strip=True,
            )
        )

        resultat.append(
            {
                "url": full_url,
                "text": text,
            }
        )

    return resultat


# ----------------------------------------------------------------------
# Detaljsida
# ----------------------------------------------------------------------

def _hamta_detaljdata(
    url: str,
) -> dict:
    """
    Hämtar kompletterande data från annonsens detaljsida.

    Detta används framför allt när årsmodell eller miltal
    saknas i sökresultatets dataLayer.
    """

    try:

        resp = requests.get(
            url,
            headers=HEADERS,
            timeout=20,
        )

        resp.raise_for_status()

    except Exception as e:

        info(
            "[bytbil] FEL vid detaljsida "
            f"{url}: {e}"
        )

        return {}

    soup = BeautifulSoup(
        resp.text,
        "html.parser",
    )

    text = _rensa_text(
        soup.get_text(
            " ",
            strip=True,
        )
    )

    return {
        "text": text,
        "arsmodell": _tolka_arsmodell(
            text
        ),
        "miltal": _tolka_miltal(
            text
        ),
        "pris": _tolka_pris(
            text
        ),
    }


# ----------------------------------------------------------------------
# Skapa intern bilrepresentation
# ----------------------------------------------------------------------

def _skapa_bil(
    bilkonfig: dict,
    produkt: dict,
    annons_url: str | None,
    extra_text: str = "",
) -> dict | None:
    """
    Skapar Fiskabilars interna bilrepresentation.

    All modell-/variantmatchning utgår från config.py.
    """

    namn = _rensa_text(
        _hamta_falt(
            produkt,
            "name",
            "title",
            "headline",
            "productName",
        )
    )

    brand = _rensa_text(
        _hamta_falt(
            produkt,
            "brand",
            "make",
            "manufacturer",
        )
    )

    model = _rensa_text(
        _hamta_falt(
            produkt,
            "model",
            "modell",
        )
    )

    pris_raw = _hamta_falt(
        produkt,
        "price",
        "annonspris",
        "pris",
        "offers.price",
    )

    arsmodell_raw = _hamta_falt(
        produkt,
        "year",
        "modelYear",
        "model_year",
        "arsmodell",
        "årsmodell",
    )

    miltal_raw = _hamta_falt(
        produkt,
        "mileage",
        "miltal",
        "mileageValue",
    )

    annons_id = _hamta_falt(
        produkt,
        "id",
        "productId",
        "product_id",
        "annonsId",
        "annons_id",
    )

    produkt_url = _hamta_falt(
        produkt,
        "url",
        "link",
        "productUrl",
        "product_url",
    )

    if not annons_url and produkt_url:
        annons_url = urljoin(
            BAS_URL,
            str(
                produkt_url
            ),
        )

    combined_text = _rensa_text(
        " ".join(
            [
                namn,
                brand,
                model,
                extra_text,
            ]
        )
    )

    # --------------------------------------------------------------
    # Pris
    # --------------------------------------------------------------

    pris = _tolka_pris(
        pris_raw
    )

    if pris is None:
        pris = _tolka_pris(
            combined_text
        )

    # --------------------------------------------------------------
    # Årsmodell
    # --------------------------------------------------------------

    arsmodell = _tolka_arsmodell(
        arsmodell_raw
    )

    if arsmodell is None:
        arsmodell = _tolka_arsmodell(
            combined_text
        )

    # --------------------------------------------------------------
    # Miltal
    # --------------------------------------------------------------

    miltal = _tolka_miltal(
        miltal_raw
    )

    if miltal is None:
        miltal = _tolka_miltal(
            combined_text
        )

    # --------------------------------------------------------------
    # Variant enligt config
    # --------------------------------------------------------------

    variant = _matcha_bilkonfig(
        bilkonfig,
        combined_text,
    )

    bil = {
        "kalla": "bytbil",

        "url": annons_url,

        "annons_id": (
            str(annons_id)
            if annons_id is not None
            else None
        ),

        "regnr": None,

        "marke_slug":
            bilkonfig["marke_slug"],

        "modell_slug":
            bilkonfig["modell_slug"],

        "modell":
            bilkonfig["modell_slug"],

        "annonspris":
            pris,

        "variant":
            variant,

        "arsmodell":
            arsmodell,

        "miltal":
            miltal,

        "vaxellada":
            "Automat",

        "skadad":
            False,

        "utrustningsniva":
            namn or model or None,

        "antal_agare":
            None,

        "auktion":
            False,

        "import":
            None,

        "hyrbil":
            None,

        "servicehistorik":
            None,

        "senaste_service":
            None,

        "nasta_service":
            None,

        "forsta_registrering":
            None,

        "dragkrok":
            None,

        "varmare":
            None,

        "volvo_selekt":
            None,

        "stor_batteri":
            None,
    }

    bil = berika_fran_fritext(
        bil,
        combined_text,
    )

    return bil


# ----------------------------------------------------------------------
# Matchning mellan dataLayer-produkt och annonslänk
# ----------------------------------------------------------------------

def _matcha_annonslank(
    produkt: dict,
    lankar: list[dict],
    anvanda_urler: set[str],
) -> tuple[str | None, str]:
    """
    Försöker koppla ett dataLayer-objekt till rätt annons-URL.

    Först används eventuell URL/id från dataLayer.
    Därefter titelmatchning.
    """

    produkt_url = _hamta_falt(
        produkt,
        "url",
        "link",
        "productUrl",
        "product_url",
    )

    if produkt_url:

        produkt_url = urljoin(
            BAS_URL,
            str(
                produkt_url
            ),
        )

        for lank in lankar:

            if (
                lank["url"]
                == produkt_url
            ):
                return (
                    produkt_url,
                    lank["text"],
                )

    namn = _rensa_text(
        _hamta_falt(
            produkt,
            "name",
            "title",
            "headline",
            "productName",
        )
    ).lower()

    if namn:

        namn_ord = [
            ordet
            for ordet in re.findall(
                r"[a-zåäö0-9]+",
                namn,
            )
            if len(ordet) >= 3
        ]

        if namn_ord:

            bast = None
            bast_poang = 0

            for lank in lankar:

                if lank["url"] in (
                    anvanda_urler
                ):
                    continue

                lank_text = (
                    lank["text"]
                    .lower()
                )

                poang = sum(
                    1
                    for ordet in namn_ord
                    if ordet in lank_text
                )

                if poang > bast_poang:

                    bast_poang = poang
                    bast = lank

            if bast is not None:
                return (
                    bast["url"],
                    bast["text"],
                )

    # Ingen säker URL hittad.
    return (
        None,
        "",
    )


# ----------------------------------------------------------------------
# Hämta annonser
# ----------------------------------------------------------------------

def hamta_annonser() -> list[dict]:
    """
    Hämtar annonser från Bytbil för samtliga modeller i BILAR.

    Configen styr:
        - vilka modeller som bevakas
        - vilka varianter som är giltiga
        - årsmodellintervall

    Bytbil-scrapern styr endast:
        - hämtning
        - parsing
        - normalisering
    """

    info(
        "[bytbil] hämtar annonser..."
    )

    alla_bilar = []

    for bilkonfig in BILAR:

        sok_url = _bygg_sok_url(
            bilkonfig
        )

        if not sok_url:
            continue

        modellnamn = bilkonfig.get(
            "modell_visning",
            bilkonfig.get(
                "modell_slug"
            ),
        )

        info(
            "[bytbil] söker: "
            f"{modellnamn}"
        )

        info(
            "[bytbil] URL: "
            f"{sok_url}"
        )

        try:

            resp = requests.get(
                sok_url,
                headers=HEADERS,
                timeout=30,
            )

            info(
                "[bytbil] HTTP-status "
                f"{modellnamn}: "
                f"{resp.status_code}"
            )

            resp.raise_for_status()

        except Exception as e:

            info(
                "[bytbil] FEL vid hämtning av "
                f"{modellnamn}: {e}"
            )

            continue

        soup = BeautifulSoup(
            resp.text,
            "html.parser",
        )

        info(
            "[bytbil] HTML-storlek "
            f"{modellnamn}: "
            f"{len(resp.text):,} bytes"
        )

        # ----------------------------------------------------------
        # DataLayer
        # ----------------------------------------------------------

        produkter = (
            _hamta_datalayer_produkter(
                soup
            )
        )

        info(
            "[bytbil] dataLayer-produkter "
            f"{modellnamn}: "
            f"{len(produkter)}"
        )

        # ----------------------------------------------------------
        # Annonslänkar
        # ----------------------------------------------------------

        lankar = (
            _hamta_annonslankar(
                soup
            )
        )

        info(
            "[bytbil] annonslänkar "
            f"{modellnamn}: "
            f"{len(lankar)}"
        )

        anvanda_urler = set()

        lokala_bilar = []

        # ----------------------------------------------------------
        # Primär väg: dataLayer
        # ----------------------------------------------------------

        for produkt in produkter:

            preliminar_text = _rensa_text(
                " ".join(
                    [
                        str(
                            _hamta_falt(
                                produkt,
                                "name",
                                "title",
                                "headline",
                                "productName",
                            )
                            or ""
                        ),
                        str(
                            _hamta_falt(
                                produkt,
                                "brand",
                                "make",
                                "manufacturer",
                            )
                            or ""
                        ),
                        str(
                            _hamta_falt(
                                produkt,
                                "model",
                                "modell",
                            )
                            or ""
                        ),
                    ]
                )
            )

            # ------------------------------------------------------
            # Kontrollera om produkten tillhör aktuell modell
            # ------------------------------------------------------

            variant = identifiera_variant(
                bilkonfig,
                preliminar_text,
            )

            if variant is None:
                continue

            annons_url, lank_text = (
                _matcha_annonslank(
                    produkt,
                    lankar,
                    anvanda_urler,
                )
            )

            if annons_url:
                anvanda_urler.add(
                    annons_url
                )

            bil = _skapa_bil(
                bilkonfig,
                produkt,
                annons_url,
                lank_text,
            )

            if bil is None:
                continue

            # ------------------------------------------------------
            # Om årsmodell eller miltal saknas:
            # hämta detaljsidan.
            # ------------------------------------------------------

            if (
                (
                    bil.get(
                        "arsmodell"
                    )
                    is None
                )
                or (
                    bil.get(
                        "miltal"
                    )
                    is None
                )
            ) and annons_url:

                detalj = (
                    _hamta_detaljdata(
                        annons_url
                    )
                )

                if (
                    bil.get(
                        "arsmodell"
                    )
                    is None
                ):
                    bil["arsmodell"] = (
                        detalj.get(
                            "arsmodell"
                        )
                    )

                if (
                    bil.get(
                        "miltal"
                    )
                    is None
                ):
                    bil["miltal"] = (
                        detalj.get(
                            "miltal"
                        )
                    )

                if (
                    bil.get(
                        "annonspris"
                    )
                    is None
                ):
                    bil["annonspris"] = (
                        detalj.get(
                            "pris"
                        )
                    )

            # ------------------------------------------------------
            # Gemensam grundkravsfiltrering
            # ------------------------------------------------------

            fel = grundkrav_fel(
                bil
            )

            if fel:

                info(
                    "[bytbil] avvisad "
                    f"{modellnamn}: "
                    f"{fel}"
                )

                continue

            lokala_bilar.append(
                bil
            )

        # ----------------------------------------------------------
        # Fallback:
        # Bytbil kan ändra dataLayer. Då använder vi annonslänkarna
        # som rådata och låter configen avgöra variant/årsmodell.
        # ----------------------------------------------------------

        if not lokala_bilar:

            info(
                "[bytbil] dataLayer gav inga "
                f"färdiga annonser för {modellnamn}; "
                "försöker med annonslänkar som fallback."
            )

            for lank in lankar:

                text = lank.get(
                    "text",
                    "",
                )

                variant = identifiera_variant(
                    bilkonfig,
                    text,
                )

                if variant is None:
                    continue

                produkt = {
                    "name": text,
                }

                bil = _skapa_bil(
                    bilkonfig,
                    produkt,
                    lank["url"],
                    text,
                )

                if bil is None:
                    continue

                if (
                    bil.get(
                        "arsmodell"
                    )
                    is None
                    or bil.get(
                        "miltal"
                    )
                    is None
                ):

                    detalj = (
                        _hamta_detaljdata(
                            lank["url"]
                        )
                    )

                    if (
                        bil.get(
                            "arsmodell"
                        )
                        is None
                    ):
                        bil["arsmodell"] = (
                            detalj.get(
                                "arsmodell"
                            )
                        )

                    if (
                        bil.get(
                            "miltal"
                        )
                        is None
                    ):
                        bil["miltal"] = (
                            detalj.get(
                                "miltal"
                            )
                        )

                    if (
                        bil.get(
                            "annonspris"
                        )
                        is None
                    ):
                        bil["annonspris"] = (
                            detalj.get(
                                "pris"
                            )
                        )

                fel = grundkrav_fel(
                    bil
                )

                if fel:
                    continue

                lokala_bilar.append(
                    bil
                )

        # ----------------------------------------------------------
        # Deduplicera inom modell
        # ----------------------------------------------------------

        sedda = set()
        unika = []

        for bil in lokala_bilar:

            nyckel = (
                bil.get(
                    "annons_id"
                )
                or bil.get(
                    "url"
                )
                or (
                    bil.get(
                        "annonspris"
                    ),
                    bil.get(
                        "arsmodell"
                    ),
                    bil.get(
                        "miltal"
                    ),
                    bil.get(
                        "variant"
                    ),
                )
            )

            if nyckel in sedda:
                continue

            sedda.add(
                nyckel
            )

            unika.append(
                bil
            )

        info(
            "[bytbil] "
            f"{modellnamn}: "
            f"{len(unika)} annonser matchade "
            "grundkraven"
        )

        alla_bilar.extend(
            unika
        )

        time.sleep(
            DELAY_SEKUNDER
        )

    # ------------------------------------------------------------------
    # Slutlig deduplicering
    # ------------------------------------------------------------------

    resultat = []
    sedda = set()

    for bil in alla_bilar:

        nyckel = (
            bil.get(
                "annons_id"
            )
            or bil.get(
                "url"
            )
            or (
                bil.get(
                    "marke_slug"
                ),
                bil.get(
                    "modell_slug"
                ),
                bil.get(
                    "variant"
                ),
                bil.get(
                    "annonspris"
                ),
                bil.get(
                    "arsmodell"
                ),
                bil.get(
                    "miltal"
                ),
            )
        )

        if nyckel in sedda:
            continue

        sedda.add(
            nyckel
        )

        resultat.append(
            bil
        )

    info(
        "[bytbil] TOTALT: "
        f"{len(resultat)} annonser "
        "matchade grundkraven"
    )

    return resultat
