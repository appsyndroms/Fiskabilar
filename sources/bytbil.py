"""
Scraper för Bytbil.

Denna fil innehåller endast huvudflödet för Bytbil.

Detaljerad parsing ligger i:
    bytbil_parser.py

Generella hjälp- och normaliseringsfunktioner ligger i:
    bytbil_helpers.py

Urvalet av modeller, varianter och årsmodeller styrs av config.py.
"""

from __future__ import annotations

import time

import requests
from bs4 import BeautifulSoup

from app_logging.logger import info

from config import BILAR

from sources import (
    berika_fran_fritext,
    grundkrav_fel,
    identifiera_variant,
)

from .bytbil_helpers import bygg_sok_url
from .bytbil_parser import (
    hamta_datalayer_produkter,
    produkt_till_annons,
)


DELAY_SEKUNDER = 0.5

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


def _hamta_sida(
    url: str,
) -> BeautifulSoup | None:
    try:
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=20,
        )

        response.raise_for_status()

    except requests.RequestException as exc:
        info(
            "[bytbil] FEL vid hämtning "
            f"av {url}: {exc}"
        )
        return None

    time.sleep(
        DELAY_SEKUNDER
    )

    return BeautifulSoup(
        response.text,
        "html.parser",
    )


def _text_for_variant(
    annons: dict,
) -> str:
    produkt_raw = annons.get(
        "produkt_raw"
    )

    delar = [
        annons.get("namn"),
    ]

    if isinstance(
        produkt_raw,
        dict,
    ):
        for key in (
            "name",
            "title",
            "model",
            "variant",
            "description",
            "category",
            "brand",
        ):
            value = produkt_raw.get(key)

            if value is not None:
                delar.append(
                    str(value)
                )

    return " ".join(
        str(del_text)
        for del_text in delar
        if del_text
    )


def _skapa_bil(
    bilkonfig: dict,
    annons: dict,
) -> dict | None:
    text = _text_for_variant(
        annons
    )

    variant = identifiera_variant(
        bilkonfig,
        text,
    )

    if variant is None:
        return None

    bil = {
        "kalla": "bytbil",

        "url": annons.get(
            "url"
        ),

        "annons_id": annons.get(
            "annons_id"
        ),

        "marke_slug":
            bilkonfig["marke_slug"],

        "modell_slug":
            bilkonfig["modell_slug"],

        "modell":
            bilkonfig["modell_visning"],

        "variant":
            variant,

        "arsmodell":
            annons.get("arsmodell"),

        "arsmodell_raw":
            annons.get("arsmodell_raw"),

        "miltal":
            annons.get("miltal"),

        "miltal_raw":
            annons.get("miltal_raw"),

        "annonspris":
            annons.get("annonspris"),

        "pris_raw":
            annons.get("pris_raw"),

        "vaxellada":
            "Automat",

        "skadad":
            False,

        "utrustningsniva":
            annons.get("namn"),

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

        "import":
            None,

        "antal_agare":
            None,

        "auktion":
            False,

        "kaross":
            None,
    }

    bil = berika_fran_fritext(
        bil,
        text,
    )

    fel = grundkrav_fel(
        bil
    )

    if fel:
        return None

    return bil


def _hamta_for_konfiguration(
    bilkonfig: dict,
) -> list[dict]:
    url = bygg_sok_url(
        bilkonfig
    )

    modell = bilkonfig.get(
        "modell_visning",
        "okänd modell",
    )

    if not url:
        info(
            "[bytbil] Kunde inte bygga "
            "sök-URL för "
            f"{modell}"
        )
        return []

    soup = _hamta_sida(
        url
    )

    if soup is None:
        return []

    produkter = (
        hamta_datalayer_produkter(
            soup
        )
    )

    if not produkter:
        return []

    annonser = []

    sedda_id = set()

    for produkt in produkter:
        annons = produkt_till_annons(
            produkt
        )

        text = _text_for_variant(
            annons
        )

        variant = identifiera_variant(
            bilkonfig,
            text,
        )

        annons_id = annons.get(
            "annons_id"
        )

        if annons_id:
            if annons_id in sedda_id:
                continue

            sedda_id.add(
                annons_id
            )

        if variant is None:
            continue

        bil = _skapa_bil(
            bilkonfig,
            annons,
        )

        if bil is not None:
            annonser.append(
                bil
            )

    return annonser


def hamta_annonser() -> list[dict]:
    """
    Hämtar och filtrerar Bytbil-annonser.

    Alla modell-, variant- och årsmodellkrav
    kommer från config.py.
    """

    resultat = []

    sedda = set()

    for bilkonfig in BILAR:
        annonser = (
            _hamta_for_konfiguration(
                bilkonfig
            )
        )

        for bil in annonser:
            nyckel = (
                bil.get("annons_id")
                or bil.get("url")
            )

            if not nyckel:
                continue

            if nyckel in sedda:
                continue

            sedda.add(
                nyckel
            )

            resultat.append(
                bil
            )

    return resultat
