"""
Scraper för Bytbil.

Hämtar Volvo V60-annonser från Bytbil och försöker extrahera:

    - titel
    - pris
    - årsmodell
    - miltal
    - variant
    - URL

Scrapern använder flera strategier eftersom Bytbils HTML-struktur
kan förändras:

    1. JSON-LD / strukturerad data
    2. Annonslänkar i HTML
    3. Annonsdata i länkarnas omgivande HTML

Första versionen fokuserar på att få fram stabil grunddata.
Detaljerad berikning kan byggas ut senare.
"""

from __future__ import annotations

import json
import re
import time
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from app_logging.logger import info

from sources import (
    berika_fran_fritext,
    matchar_grundkrav,
)


DELAY_SEKUNDER = 3.0

BAS_URL = "https://www.bytbil.com"

SOK_URLER = [
    "https://www.bytbil.com/bil/volvo/v60",
]


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 "
        "(Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/131.0.0.0 "
        "Safari/537.36"
    ),
    "Accept-Language": (
        "sv-SE,sv;q=0.9,en;q=0.8"
    ),
}


def _rensa_text(
    value,
) -> str:
    """Rensar text från extra whitespace."""

    if value is None:
        return ""

    return re.sub(
        r"\s+",
        " ",
        str(value),
    ).strip()


def _tolka_pris(
    text: str,
) -> int | None:
    """
    Extraherar pris från text.

    Exempel:

        289 900 kr
        394000 kr
        Pris: 489 000
    """

    if not text:
        return None

    match = re.search(
        r"(\d[\d\s\xa0]{3,})\s*(?:kr)?",
        text,
        re.IGNORECASE,
    )

    if not match:
        return None

    siffror = re.sub(
        r"\D",
        "",
        match.group(1),
    )

    if not siffror:
        return None

    try:
        pris = int(siffror)
    except ValueError:
        return None

    if pris < 10_000:
        return None

    return pris


def _tolka_arsmodell(
    text: str,
) -> int | None:
    """
    Extraherar årsmodell.

    Exempel:

        2024
        2024 | 5 922 mil
        Årsmodell 2024
    """

    if not text:
        return None

    match = re.search(
        r"\b(19[9]\d|20\d{2})\b",
        text,
    )

    if not match:
        return None

    try:
        arsmodell = int(
            match.group(1)
        )
    except ValueError:
        return None

    if not 1990 <= arsmodell <= 2030:
        return None

    return arsmodell


def _tolka_miltal(
    text: str,
) -> float | None:
    """
    Extraherar miltal.

    Exempel:

        5 922 mil
        9020 mil
        12,5 mil
    """

    if not text:
        return None

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
        miltal = float(nummer)
    except ValueError:
        return None

    if miltal < 0:
        return None

    return miltal


def _bestam_variant(
    text: str,
) -> str | None:
    """
    Bestämmer bilvariant från titel och annonstext.
    """

    text_lower = text.lower()

    if "t8" in text_lower:
        return "T8 AWD"

    if "t6" in text_lower:
        return "T6 AWD"

    if "530e" in text_lower:
        return "530e"

    return None


def _ar_relevant_lank(
    href: str,
) -> bool:
    """
    Filtrerar fram länkar som sannolikt är bilannonser.
    """

    if not href:
        return False

    href_lower = href.lower()

    if "/bil/" not in href_lower:
        return False

    if href_lower.rstrip("/") in {
        "/bil",
        "/bil/volvo",
        "/bil/volvo/v60",
    }:
        return False

    return True


def _hamta_json_ld(
    soup: BeautifulSoup,
) -> list[dict]:
    """
    Hämtar objekt från JSON-LD-script.
    """

    objekt = []

    for script in soup.find_all(
        "script",
        type="application/ld+json",
    ):
        text = script.string

        if not text:
            continue

        try:
            data = json.loads(text)
        except (
            json.JSONDecodeError,
            TypeError,
        ):
            continue

        if isinstance(data, list):
            objekt.extend(data)

        elif isinstance(data, dict):

            graf = data.get("@graph")

            if isinstance(graf, list):
                objekt.extend(graf)

            else:
                objekt.append(data)

    return objekt


def _bil_fran_json_ld(
    objekt: dict,
) -> dict | None:
    """
    Försöker skapa en bil från JSON-LD-data.
    """

    if not isinstance(
        objekt,
        dict,
    ):
        return None

    namn = _rensa_text(
        objekt.get("name")
        or objekt.get("headline")
        or objekt.get("description")
    )

    if not namn:
        return None

    typ = objekt.get("@type")

    if isinstance(typ, list):
        typ_text = " ".join(
            str(value)
            for value in typ
        )
    else:
        typ_text = str(typ or "")

    combined = (
        f"{namn} "
        f"{typ_text}"
    )

    if "v60" not in combined.lower():
        return None

    offers = objekt.get("offers")

    pris = None

    if isinstance(offers, dict):
        pris = _tolka_pris(
            str(
                offers.get("price")
                or ""
            )
        )

    if pris is None:
        pris = _tolka_pris(
            _rensa_text(
                objekt.get("price")
            )
        )

    url = (
        objekt.get("url")
        or (
            offers.get("url")
            if isinstance(offers, dict)
            else None
        )
    )

    if url:
        url = urljoin(
            BAS_URL,
            url,
        )

    text = combined

    bil = {
        "kalla": "bytbil",
        "url": url,
        "regnr": None,
        "annonspris": pris,
        "variant": _bestam_variant(text),
        "arsmodell": _tolka_arsmodell(text),
        "miltal": _tolka_miltal(text),
        "vaxellada": "Automat",
        "skadad": False,
        "utrustningsniva": None,
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

    return berika_fran_fritext(
        bil,
        text,
    )


def _hamta_annonslankar(
    soup: BeautifulSoup,
) -> list:
    """
    Hämtar sannolika annonslänkar från sidan.
    """

    lankar = []

    sedda_urler = set()

    for lank in soup.find_all(
        "a",
        href=True,
    ):
        href = lank.get("href")

        if not _ar_relevant_lank(href):
            continue

        url = urljoin(
            BAS_URL,
            href,
        )

        if url in sedda_urler:
            continue

        sedda_urler.add(url)

        lankar.append(lank)

    return lankar


def _tolka_annonslank(
    lank,
) -> dict | None:
    """
    Försöker tolka en annons från en länk och dess
    närmaste omgivande HTML.
    """

    href = lank.get("href")

    if not href:
        return None

    url = urljoin(
        BAS_URL,
        href,
    )

    titel = _rensa_text(
        lank.get_text(
            " ",
            strip=True,
        )
    )

    container = lank

    for _ in range(5):

        parent = container.parent

        if parent is None:
            break

        container = parent

        text = _rensa_text(
            container.get_text(
                " ",
                strip=True,
            )
        )

        if (
            _tolka_pris(text)
            and _tolka_arsmodell(text)
            and _tolka_miltal(text)
        ):
            break

    text = _rensa_text(
        container.get_text(
            " ",
            strip=True,
        )
    )

    combined_text = (
        f"{titel} {text}"
    )

    if "v60" not in combined_text.lower():
        return None

    pris = _tolka_pris(
        combined_text
    )

    arsmodell = _tolka_arsmodell(
        combined_text
    )

    miltal = _tolka_miltal(
        combined_text
    )

    bil = {
        "kalla": "bytbil",
        "url": url,
        "regnr": None,
        "annonspris": pris,
        "variant": _bestam_variant(
            combined_text
        ),
        "arsmodell": arsmodell,
        "miltal": miltal,
        "vaxellada": "Automat",
        "skadad": False,
        "utrustningsniva": None,
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

    return berika_fran_fritext(
        bil,
        combined_text,
    )


def _ar_komplett_bil(
    bil: dict,
) -> bool:
    """
    Kontrollerar att grundläggande data finns innan
    bilen skickas vidare.
    """

    krav = [
        "annonspris",
        "arsmodell",
        "miltal",
    ]

    return all(
        bil.get(falt) is not None
        for falt in krav
    )


def _deduplicera(
    bilar: list[dict],
) -> list[dict]:
    """
    Tar bort dubbletter baserat på URL.
    """

    resultat = []

    sedda = set()

    for bil in bilar:

        nyckel = (
            bil.get("url")
            or (
                bil.get("annonspris"),
                bil.get("arsmodell"),
                bil.get("miltal"),
            )
        )

        if nyckel in sedda:
            continue

        sedda.add(nyckel)

        resultat.append(bil)

    return resultat


def hamta_annonser() -> list[dict]:
    """
    Hämtar annonser från Bytbil.

    Flera strategier används för att göra scrapern mindre
    känslig för förändringar i HTML-strukturen.
    """

    info(
        "[bytbil] hämtar annonser..."
    )

    alla_bilar = []

    for sok_url in SOK_URLER:

        info(
            f"[bytbil] hämtar: {sok_url}"
        )

        try:

            resp = requests.get(
                sok_url,
                headers=HEADERS,
                timeout=30,
            )

            info(
                f"[bytbil] HTTP-status: "
                f"{resp.status_code}"
            )

            resp.raise_for_status()

        except Exception as e:

            info(
                f"[bytbil] FEL vid hämtning: "
                f"{e}"
            )

            continue

        time.sleep(
            DELAY_SEKUNDER
        )

        soup = BeautifulSoup(
            resp.text,
            "html.parser",
        )

        info(
            f"[bytbil] HTML-storlek: "
            f"{len(resp.text):,} bytes"
        )

        # --------------------------------
        # Strategi 1:
        # JSON-LD / strukturerad data
        # --------------------------------

        json_ld_objekt = (
            _hamta_json_ld(soup)
        )

        info(
            f"[bytbil] JSON-LD objekt: "
            f"{len(json_ld_objekt)}"
        )

        for objekt in json_ld_objekt:

            bil = _bil_fran_json_ld(
                objekt
            )

            if bil:
                alla_bilar.append(
                    bil
                )

        # --------------------------------
        # Strategi 2:
        # Annonslänkar i HTML
        # --------------------------------

        annonslankar = (
            _hamta_annonslankar(
                soup
            )
        )

        info(
            f"[bytbil] möjliga "
            f"annonslänkar: "
            f"{len(annonslankar)}"
        )

        for lank in annonslankar:

            bil = _tolka_annonslank(
                lank
            )

            if bil:
                alla_bilar.append(
                    bil
                )

    # --------------------------------
    # Deduplicering
    # --------------------------------

    alla_bilar = _deduplicera(
        alla_bilar
    )

    info(
        f"[bytbil] totalt tolkade "
        f"annonser: "
        f"{len(alla_bilar)}"
    )

    # --------------------------------
    # Kontrollera datakvalitet
    # --------------------------------

    kompletta_bilar = [
        bil
        for bil in alla_bilar
        if _ar_komplett_bil(bil)
    ]

    info(
        f"[bytbil] kompletta annonser: "
        f"{len(kompletta_bilar)}"
    )

    # --------------------------------
    # Grundkrav Fiskabilar
    # --------------------------------

    matchande_bilar = []

    for bil in kompletta_bilar:

        try:

            if matchar_grundkrav(bil):

                matchande_bilar.append(
                    bil
                )

        except Exception as e:

            info(
                f"[bytbil] kunde inte "
                f"kontrollera grundkrav: "
                f"{e}"
            )

    info(
        f"[bytbil] "
        f"{len(matchande_bilar)} annonser "
        f"matchade grundkraven"
    )

    return matchande_bilar
