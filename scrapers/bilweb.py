"""
Scraper för Bilweb.

Bilweb fungerar utan JavaScript för de delar vi behöver läsa ut.
Sökresultatsidan används endast för att hitta kandidat-URL:er.
Pris, miltal och övriga detaljuppgifter hämtas från respektive
annons egen detaljsida.

Registreringsnummer hämtas från samma detaljsida som pris/miltal.

VIKTIGT:
Registreringsnummer används som starkaste identifierare av fysisk bil,
men endast när Bilwebs sida uttryckligen anger ett registreringsnummer.

Vi gör INTE en generell sökning efter sex-/sjuteckenssträngar på sidan.
Det skulle kunna ge falska träffar som exempelvis:

    BMW530
    BMW330
    V60T6

Regnr-extraktionen använder därför flera säkra metoder:

1. Uttrycklig regnr-etikett + värde i samma text.
2. Uttrycklig regnr-etikett + närliggande DOM-element.
3. Uttrycklig regnr-etikett + närmaste container.
4. Strukturerad data / JSON-LD där regnr-fältet finns.
5. HTML-attribut nära en uttrycklig regnr-etikett.

Ingen metod accepterar ett godtyckligt ABC123 från hela sidan.

Detaljsidor cachas under varje körning så att samma URL aldrig hämtas
mer än en gång.

REGNR är diagnostisk information och är INTE ett grundkrav.
En annons utan registreringsnummer ska därför inte generera ett
individuellt felmeddelande.

PRESTANDA:
Detaljsidor hämtas parallellt med ett begränsat antal workers.
Sökresultatsidor hämtas sekventiellt.

Vi använder ingen artificiell delay efter detaljsidor.
"""

import json
import re
import time
from concurrent.futures import (
    ThreadPoolExecutor,
    as_completed,
)

import requests
from bs4 import BeautifulSoup

from config import BILAR, ARSMODELL_MIN, ARSMODELL_MAX
from scrapers import (
    matchar_grundkrav,
    grundkrav_fel,
    berika_fran_fritext,
    identifiera_variant,
)


# ---------------------------------------------------------------------------
# PRESTANDA
# ---------------------------------------------------------------------------

SOK_DELAY_SEKUNDER = 1.0

MAX_PARALLELLA_DETALJSIDOR = 6

DETALJ_DELAY_SEKUNDER = 0.0


SOK_URL_MALL = "https://bilweb.se/sok/{marke}/{modell}/{ar}"

BILWEB_BASE_URL = "https://bilweb.se"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    ),
}


PRIS_DETALJ_REGEX = re.compile(
    r"Pris\s*(?:\([^)]*\))?\s*([\d\s]+?)\s*kr",
    re.IGNORECASE,
)

MIL_DETALJ_REGEX = re.compile(
    r"Mil\s+([\d\s]+?)\s+1:a\s+regdatum",
    re.IGNORECASE,
)

AGARE_DETALJ_REGEX = re.compile(
    r"Antal\s+ägare\s+(\d+)",
    re.IGNORECASE,
)

AUKTION_REGEX = re.compile(
    r"auktionsobjekt",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Registreringsnummer
# ---------------------------------------------------------------------------

REGNR_REGEX = re.compile(
    r"(?<![A-ZÅÄÖ0-9])"
    r"([A-ZÅÄÖ]{3})"
    r"[\s-]?"
    r"("
    r"\d{3}"
    r"|"
    r"\d{2}[A-Z]"
    r")"
    r"(?![A-ZÅÄÖ0-9])",
    re.IGNORECASE,
)


REGNR_ETIKETT_REGEX = re.compile(
    r"(?:"
    r"\bregistreringsnummer\b"
    r"|"
    r"\bregistreringsnr\b"
    r"|"
    r"\breg\.?\s*nr\.?\b"
    r"|"
    r"\bregnr\b"
    r"|"
    r"\breg\.?\s*nummer\b"
    r")",
    re.IGNORECASE,
)


REGNR_FALTNAMN = (
    "registrationnumber",
    "registration_number",
    "registrationno",
    "registration_no",
    "registernumber",
    "reg_number",
    "regnr",
    "registration",
)


# ---------------------------------------------------------------------------
# Hjälpfunktioner
# ---------------------------------------------------------------------------


def _bygg_href_regex(
    marke_slug: str,
) -> re.Pattern:

    return re.compile(
        rf"{re.escape(marke_slug)}-"
        rf"(?P<slug>[a-z0-9-]+?)-"
        rf"(?P<ar>\d{{4}})-kombi-"
        rf"(?P<id>\d+)",
        re.IGNORECASE,
    )


def _rensa_tal(
    text: str,
) -> int:

    siffror = re.sub(
        r"\D",
        "",
        text,
    )

    return int(siffror) if siffror else 0


# ---------------------------------------------------------------------------
# BMW-modellslug-normalisering
# ---------------------------------------------------------------------------
#
# Bilweb kan skriva BMW:s laddhybrider både som:
#
#     530e
#     530 e
#
# samt:
#
#     330e
#     330 e
#
# Våra variantdefinitioner använder:
#
#     530e
#     330e
#
# Därför normaliseras dessa skrivsätt innan identifiera_variant()
# körs.
#
# Detta gäller endast 530e och 330e.
#
# Exempel:
#
#     "530 e xdrive m sport pano drag"
#
# blir:
#
#     "530e xdrive m sport pano drag"
#
# ---------------------------------------------------------------------------


def _normalisera_bmw_modellslug(
    slug_text: str,
) -> str:

    if not slug_text:
        return slug_text

    slug_text = re.sub(
        r"\b530\s+e\b",
        "530e",
        slug_text,
        flags=re.IGNORECASE,
    )

    slug_text = re.sub(
        r"\b330\s+e\b",
        "330e",
        slug_text,
        flags=re.IGNORECASE,
    )

    return slug_text


# ---------------------------------------------------------------------------
# REGNR
# ---------------------------------------------------------------------------


def _normalisera_regnr(
    regnr: str | None,
) -> str | None:

    if not regnr:
        return None

    normaliserat = re.sub(
        r"[^A-Za-zÅÄÖåäö0-9]",
        "",
        str(regnr),
    ).upper()

    if len(normaliserat) not in (6, 7):
        return None

    if not re.fullmatch(
        r"[A-ZÅÄÖ]{3}(?:\d{3}|\d{2}[A-Z])",
        normaliserat,
        re.IGNORECASE,
    ):
        return None

    return normaliserat


def _extrahera_regnr_kandidat(
    text: str | None,
) -> str | None:

    if not text:
        return None

    match = REGNR_REGEX.search(
        str(text)
    )

    if not match:
        return None

    kandidat = (
        f"{match.group(1)}"
        f"{match.group(2)}"
    )

    return _normalisera_regnr(
        kandidat
    )


def _extrahera_regnr_etikett_samma_text(
    text: str,
) -> str | None:

    if not text:
        return None

    match = REGNR_ETIKETT_REGEX.search(
        text
    )

    if not match:
        return None

    efter = text[
        match.end():
    ]

    prefix = re.match(
        r"^[\s:;=\-–—]*",
        efter,
    )

    if not prefix:
        return None

    kandidat_text = efter[
        prefix.end():
        prefix.end() + 30
    ]

    return _extrahera_regnr_kandidat(
        kandidat_text
    )


def _extrahera_regnr_dom(
    soup: BeautifulSoup,
) -> str | None:

    textnoder = soup.find_all(
        string=REGNR_ETIKETT_REGEX
    )

    for textnod in textnoder:

        text = str(textnod).strip()

        kandidat = _extrahera_regnr_etikett_samma_text(
            text
        )

        if kandidat:
            return kandidat

        element = getattr(
            textnod,
            "parent",
            None,
        )

        if element is None:
            continue

        element_text = element.get_text(
            " ",
            strip=True,
        )

        kandidat = _extrahera_regnr_etikett_samma_text(
            element_text
        )

        if kandidat:
            return kandidat

        for child in element.find_all(
            recursive=True
        ):

            child_text = child.get_text(
                " ",
                strip=True,
            )

            if len(child_text) > 300:
                continue

            if REGNR_ETIKETT_REGEX.search(
                child_text
            ):

                kandidat = (
                    _extrahera_regnr_etikett_samma_text(
                        child_text
                    )
                )

                if kandidat:
                    return kandidat

                for sibling in child.find_all_next(
                    limit=5
                ):

                    sibling_text = sibling.get_text(
                        " ",
                        strip=True,
                    )

                    if len(sibling_text) > 100:
                        continue

                    kandidat = _extrahera_regnr_kandidat(
                        sibling_text
                    )

                    if kandidat:
                        return kandidat

        for sibling in element.find_all_next(
            limit=8
        ):

            sibling_text = sibling.get_text(
                " ",
                strip=True,
            )

            if not sibling_text:
                continue

            if len(sibling_text) > 150:
                continue

            if (
                sibling is not element
                and REGNR_ETIKETT_REGEX.search(
                    sibling_text
                )
            ):

                kandidat = (
                    _extrahera_regnr_etikett_samma_text(
                        sibling_text
                    )
                )

                if kandidat:
                    return kandidat

            kandidat = _extrahera_regnr_kandidat(
                sibling_text
            )

            if kandidat:
                return kandidat

        container = element

        for _ in range(4):

            container = getattr(
                container,
                "parent",
                None,
            )

            if container is None:
                break

            container_text = container.get_text(
                " ",
                strip=True,
            )

            if len(container_text) > 1000:
                continue

            etikett_match = REGNR_ETIKETT_REGEX.search(
                container_text
            )

            if not etikett_match:
                continue

            efter = container_text[
                etikett_match.end():
            ]

            efter = efter[:100]

            kandidat = _extrahera_regnr_kandidat(
                efter
            )

            if kandidat:
                return kandidat

    return None


# ---------------------------------------------------------------------------
# REGNR från attribut
# ---------------------------------------------------------------------------


def _extrahera_regnr_attribut(
    soup: BeautifulSoup,
) -> str | None:

    for element in soup.find_all(True):

        attributtext = " ".join(
            str(value)
            for key, value in element.attrs.items()
            if isinstance(value, (str, list))
        )

        if not REGNR_ETIKETT_REGEX.search(
            attributtext
        ):
            continue

        for key, value in element.attrs.items():

            if isinstance(value, list):
                value = " ".join(
                    str(v)
                    for v in value
                )

            value = str(value)

            key_normaliserad = re.sub(
                r"[^a-z0-9]",
                "",
                key.lower(),
            )

            if (
                key_normaliserad in REGNR_FALTNAMN
                or "registration" in key_normaliserad
                or "regnr" in key_normaliserad
            ):

                kandidat = _extrahera_regnr_kandidat(
                    value
                )

                if kandidat:
                    return kandidat

        element_text = element.get_text(
            " ",
            strip=True,
        )

        kandidat = (
            _extrahera_regnr_etikett_samma_text(
                element_text
            )
        )

        if kandidat:
            return kandidat

    return None


# ---------------------------------------------------------------------------
# REGNR från JSON-LD / strukturerad data
# ---------------------------------------------------------------------------


def _iterera_json_objekt(
    obj,
):

    if isinstance(obj, dict):

        yield obj

       
