"""
HTTP- och detaljsidelogik för Bilweb.

Här ligger:
- HTTP-anrop
- pris/miltal
- antal ägare
- auktion
- kaross
- REGNR
- parallell detaljsidehämtning
- cache
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

from app_logging.logger import info

from .bilweb_regnr import (
    extrahera_regnr,
)
from .bilweb_bmw import (
    extrahera_kaross,
)


MAX_PARALLELLA_DETALJSIDOR = 6

ANTAL_DETALJSIDE_FORSOK = 3
DETALJSIDA_TIMEOUT_SEKUNDER = 15
DETALJSIDA_RETRY_PAUS_SEKUNDER = 1.0

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    ),
}

PRIS_DETALJ_REGEX = re.compile(
    r"Pris\s*(?:\([^)]*\))?\s*([\d\s]+?)\s*(?:kr|:-)",
    re.IGNORECASE,
)

KONTANTPRIS_REGEX = re.compile(
    r"(?:Kontantpris|Kontant)"
    r"\s*:?\s*"
    r"([\d\s]+?)"
    r"\s*(?:kr|:-)",
    re.IGNORECASE,
)

LEASING_REGEX = re.compile(
    r"privatleasing|företagsleasing|leasing",
    re.IGNORECASE,
)

PRISBELOPP_REGEX = re.compile(
    r"(?<!\d)"
    r"(\d[\d\s]{2,})"
    r"\s*(?:kr|:-)"
    r"(?!\s*/?\s*(?:mån|månad))",
    re.IGNORECASE,
)

MIL_DETALJ_REGEX = re.compile(
    r"Mätarställning\s+([\d\s]+?)\s+mil",
    re.IGNORECASE,
)

AGARE_DETALJ_REGEX = re.compile(
    r"Antal\s+ägare\s+(\d+)",
    re.IGNORECASE,
)

AUKTION_REGEX = re.compile(
    r"auktionsobjekt|Priset är ett uppskattat högsta slutpris",
    re.IGNORECASE,
)


def _rensa_tal(
    text: str,
) -> int:
    """
    Omvandlar ett svenskt tal/pris till heltal.

    Exempel:
        "214 299 kr"      -> 214299
        "214 299,00 kr"   -> 214299
        "214.299,00 kr"   -> 214299
        "214299 kr"       -> 214299

    Decimaldelen ignoreras eftersom priserna i historiken
    lagras som heltal kronor.
    """

    text = str(text).strip()

    text = re.sub(
        r",\d{2}\b",
        "",
        text,
    )

    siffror = re.sub(
        r"\D",
        "",
        text,
    )

    return int(siffror) if siffror else 0


def _hamta_json_ld(
    soup: BeautifulSoup,
) -> list[dict]:
    """
    Hämtar JSON-LD-block från sidan.
    """

    resultat = []

    for script in soup.find_all(
        "script",
        attrs={"type": "application/ld+json"},
    ):
        innehall = (
            script.string
            or script.get_text(strip=True)
        )

        if not innehall:
            continue

        try:
            data = json.loads(innehall)
        except Exception:
            continue

        if isinstance(data, dict):
            resultat.append(data)

        elif isinstance(data, list):
            resultat.extend(
                item
                for item in data
                if isinstance(item, dict)
            )

    return resultat


def _hitta_rekursivt(
    data,
    nycklar: set[str],
):
    """
    Söker rekursivt efter första förekomsten
    av någon av nycklarna.
    """

    if isinstance(data, dict):
        for key, value in data.items():

            if key.lower() in nycklar:
                return value

            resultat = _hitta_rekursivt(
                value,
                nycklar,
            )

            if resultat is not None:
                return resultat

    elif isinstance(data, list):
        for item in data:

            resultat = _hitta_rekursivt(
                item,
                nycklar,
            )

            if resultat is not None:
                return resultat

    return None


def _pris_fran_json_ld(
    json_ld: list[dict],
) -> int | None:
    value = _hitta_rekursivt(
        json_ld,
        {
            "price",
            "lowprice",
            "highprice",
        },
    )

    if value is None:
        return None

    if isinstance(value, (int, float)):
        return int(value)

    if isinstance(value, str):
        pris = _rensa_tal(
            value
        )

        if pris:
            return pris

    return None


def _mil_fran_json_ld(
    json_ld: list[dict],
) -> int | None:
    value = _hitta_rekursivt(
        json_ld,
        {
            "mileagefromodometer",
            "odometervalue",
            "mileage",
            "miltal",
        },
    )

    if value is None:
        return None

    if isinstance(value, dict):
        value = value.get("value")

    if isinstance(value, (int, float)):
        return int(value)

    if isinstance(value, str):
        siffror = re.sub(
            r"[^\d]",
            "",
            value,
        )

        if siffror:
            return int(siffror)

    return None


def _pris_fran_meta(
    soup: BeautifulSoup,
) -> int | None:
    """
    Försöker hitta pris i vanliga meta-attribut.
    """

    kandidater = [
        soup.find(
            "meta",
            attrs={
                "property": "product:price:amount",
            },
        ),
        soup.find(
            "meta",
            attrs={
                "name": "price",
            },
        ),
        soup.find(
            "meta",
            attrs={
                "itemprop": "price",
            },
        ),
    ]

    for meta in kandidater:

        if not meta:
            continue

        value = meta.get("content")

        if not value:
            continue

        pris = _rensa_tal(
            value
        )

        if pris:
            return pris

    meta_description = soup.find(
        "meta",
        attrs={
            "name": "description",
        },
    )

    if meta_description:
        content = meta_description.get(
            "content",
            "",
        )

        match = re.search(
            r"Pris\s+([\d\s]+)\s+kr",
            content,
            re.IGNORECASE,
        )

        if match:
            return _rensa_tal(
                match.group(1)
            )

    return None


def _ar_leasingannons(
    text: str,
) -> bool:
    """
    Avgör om annonsen sannolikt är en leasingannons.
    """

    for rad in text.splitlines()[:20]:

        if LEASING_REGEX.search(rad):
            return True

    return False


def _pris_fran_kontantpris(
    text: str,
) -> int | None:
    """
    Försöker hitta ett uttryckligt kontantpris.
    """

    match = KONTANTPRIS_REGEX.search(
        text
    )

    if not match:
        return None

    pris = _rensa_tal(
        match.group(1)
    )

    if pris < 100_000:
        return None

    return pris


def _pris_fran_synlig_text(
    text: str,
) -> int | None:
    """
    Försöker hitta Bilwebs synliga prisformat.
    """

    for rad in text.splitlines():

        rad = rad.strip()

        if not rad:
            continue

        if re.search(
            r"(?:/|\b)(?:mån|månad)\b",
            rad,
            re.IGNORECASE,
        ):
            continue

        match = PRISBELOPP_REGEX.search(
            rad
        )

        if not match:
            continue

        pris = _rensa_tal(
            match.group(1)
        )

        if pris < 100_000:
            continue

        return pris

    return None


def _pris_fran_prislabel(
    text: str,
) -> int | None:
    """
    Försöker hitta Bilwebs format:

        Pris
        319 700 kr
    """

    if _ar_leasingannons(text):
        return None

    pris_match = re.search(
        r"(?:^|\n)"
        r"\s*Pris"
        r"\s*(?:\([^)]*\))?"
        r"\s*\n+"
        r"\s*([\d\s]+)"
        r"\s*(?:kr|:-)",
        text,
        re.IGNORECASE,
    )

    if not pris_match:
        return None

    pris = _rensa_tal(
        pris_match.group(1)
    )

    if pris < 100_000:
        return None

    return pris


def _mil_fran_html_attribut(
    soup: BeautifulSoup,
) -> int | None:
    """
    Söker efter attribut som kan innehålla miltal.
    """

    attribut_namn = {
        "data-mileage",
        "data-milage",
        "data-miltal",
        "data-odometer",
        "data-km",
    }

    for element in soup.find_all(True):

        for namn in attribut_namn:

            value = element.get(namn)

            if value is None:
                continue

            siffror = re.sub(
                r"[^\d]",
                "",
                str(value),
            )

            if siffror:
                return int(siffror)

    return None


def _annons_id_fran_url(
    url: str,
) -> str | None:
    """
    Hämtar ett eventuellt numeriskt annons-ID från Bilweb-URL:en.
    """

    match = re.search(
        r"-(\d+)(?:[/?#]|$)",
        str(url),
    )

    if match:
        return match.group(1)

    return None


def _redirect_ser_ut_som_annan_sida(
    ursprunglig_url: str,
    slutlig_url: str,
) -> bool:
    """
    Avgör om requests har följt en redirect till en annan Bilweb-sida.

    En borttagen annons kan fortfarande ge HTTP 200 men redirectas
    till exempelvis en generell Bilweb-sida. Det ska inte tolkas som
    en giltig detaljsida.

    Om vi kan identifiera annons-ID kräver vi att samma ID fortfarande
    finns i slut-URL:en.
    """

    ursprunglig_url = str(
        ursprunglig_url
    ).rstrip("/")

    slutlig_url = str(
        slutlig_url
    ).rstrip("/")

    if ursprunglig_url == slutlig_url:
        return False

    ursprungligt_id = _annons_id_fran_url(
        ursprunglig_url
    )

    if not ursprungligt_id:
        return False

    return ursprungligt_id not in slutlig_url


def hamta_pris_mil_fran_detaljsida(
    url: str,
) -> dict | None:

    resp = None
    senaste_fel = None

    for forsok in range(
        1,
        ANTAL_DETALJSIDE_FORSOK + 1,
    ):

        try:
            resp = requests.get(
                url,
                headers=HEADERS,
                timeout=DETALJSIDA_TIMEOUT_SEKUNDER,
                allow_redirects=True,
            )

            resp.raise_for_status()

            if _redirect_ser_ut_som_annan_sida(
                url,
                resp.url,
            ):
                info(
                    "[bilweb]   Detaljsidan redirectades "
                    "till annan sida: "
                    f"{url} -> {resp.url}"
                )
                return None

            break

        except Exception as e:
            senaste_fel = e

            if forsok < ANTAL_DETALJSIDE_FORSOK:
                info(
                    "[bilweb]   Försök "
                    f"{forsok}/{ANTAL_DETALJSIDE_FORSOK} "
                    f"misslyckades för {url}: {e}. "
                    "Försöker igen."
                )

                time.sleep(
                    DETALJSIDA_RETRY_PAUS_SEKUNDER
                )

            else:
                info(
                    "[bilweb]   FEL vid hämtning "
                    f"av detaljsida {url} efter "
                    f"{ANTAL_DETALJSIDE_FORSOK} försök: "
                    f"{senaste_fel}"
                )

    if resp is None:
        return None

    html = resp.text

    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    text = soup.get_text(
        separator="\n",
        strip=True,
    )

    # ---------------------------------------------------------
    # Pris
    # ---------------------------------------------------------

    pris = None

    # 1. Explicit kontantpris.
    pris = _pris_fran_kontantpris(
        text
    )

    # 2. Pris i synlig text.
    if pris is None:

        pris = _pris_fran_synlig_text(
            text
        )

    # 3. Klassisk "Pris 479 800 kr".
    if pris is None:

        pris = _pris_fran_prislabel(
            text
        )

    # 4. Auktionsformat.
    if pris is None:

        pris_match = re.search(
            r"(?:^|\n)"
            r"\s*([\d\s]+)"
            r"\s*(?:kr|:-)"
            r"\s*\n+"
            r"\s*Priset är",
            text,
            re.IGNORECASE,
        )

        if pris_match:
            kandidatpris = _rensa_tal(
                pris_match.group(1)
            )

            if kandidatpris >= 100_000:
                pris = kandidatpris

    # 5. Prisregex mot hela texten.
    if (
        pris is None
        and not _ar_leasingannons(text)
    ):

        pris_match = PRIS_DETALJ_REGEX.search(
            text.replace("\n", " ")
        )

        if pris_match:

            kandidatpris = _rensa_tal(
                pris_match.group(1)
            )

            if kandidatpris >= 100_000:
                pris = kandidatpris

    # 6. Meta description / price-meta.
    if pris is None:

        pris = _pris_fran_meta(
            soup
        )

        if (
            pris is not None
            and pris < 100_000
        ):
            pris = None

    json_ld = _hamta_json_ld(
        soup
    )

    # 7. JSON-LD.
    if pris is None:

        pris = _pris_fran_json_ld(
            json_ld
        )

        if (
            pris is not None
            and pris < 100_000
        ):
            pris = None

    # Leasingannonser utan explicit kontantpris
    # ska inte användas som kontantprisobservationer.
    if (
        pris is not None
        and _ar_leasingannons(text)
        and _pris_fran_kontantpris(text) is None
    ):
        pris = None

    # ---------------------------------------------------------
    # Miltal
    # ---------------------------------------------------------

    miltal = None

    mil_match = re.search(
        r"(?:^|\n)"
        r"\s*Mätarställning"
        r"\s*\n+"
        r"\s*(\d[\d\s]*)"
        r"\s+mil",
        text,
        re.IGNORECASE,
    )

    if mil_match:
        miltal = _rensa_tal(
            mil_match.group(1)
        )

    if miltal is None:

        mil_match = MIL_DETALJ_REGEX.search(
            text
        )

        if mil_match:
            miltal = _rensa_tal(
                mil_match.group(1)
            )

    if miltal is None:

        miltal = _mil_fran_html_attribut(
            soup
        )

    if miltal is None:

        miltal = _mil_fran_json_ld(
            json_ld
        )

    # Nya bilar kan sakna registrerad mätarställning.
    if miltal is None:

        mil_match = re.search(
            r"(?:^|\n)"
            r"\s*Mätarställning"
            r"\s*\n+"
            r"\s*[–—-]"
            r"\s*(?:\n|$)",
            text,
            re.IGNORECASE,
        )

        if mil_match:
            miltal = 0

    if pris is None or miltal is None:
        return None

    # ---------------------------------------------------------
    # Övriga fält
    # ---------------------------------------------------------

    agare_match = AGARE_DETALJ_REGEX.search(
        text.replace("\n", " ")
    )

    antal_agare = (
        int(agare_match.group(1))
        if agare_match
        else None
    )

    ar_auktion = (
        AUKTION_REGEX.search(text)
        is not None
    )

    regnr = extrahera_regnr(
        soup,
        html,
    )

    kaross = extrahera_kaross(
        text,
    )

    return {
        "pris": pris,
        "miltal": miltal,
        "antal_agare": antal_agare,
        "auktion": ar_auktion,
        "regnr": regnr,
        "kaross": kaross,
        "text": text,
    }


def hamta_detaljsidor_parallellt(
    kandidater: list[dict],
    cache: dict,
) -> tuple[dict, int, int]:
    """
    Hämtar detaljsidor parallellt.

    Returnerar:
        resultat, antal_hamtade, antal_cache
    """

    resultat = {}

    urls_att_hamta = []

    antal_cache = 0

    for kandidat in kandidater:

        url = kandidat.get("url")

        if not url:
            continue

        if url in cache:

            kandidat_data = dict(
                kandidat
            )

            kandidat_data.update(
                cache[url]
            )

            resultat[url] = kandidat_data
            antal_cache += 1

        else:

            urls_att_hamta.append(
                (
                    url,
                    kandidat,
                )
            )

    antal_hamtade = len(
        urls_att_hamta
    )

    if urls_att_hamta:

        info(
            "[bilweb]   hämtar "
            f"{len(urls_att_hamta)} "
            "detaljsidor parallellt med "
            f"{MAX_PARALLELLA_DETALJSIDOR} workers"
        )

        with ThreadPoolExecutor(
            max_workers=MAX_PARALLELLA_DETALJSIDOR
        ) as executor:

            futures = {
                executor.submit(
                    hamta_pris_mil_fran_detaljsida,
                    url,
                ): (
                    url,
                    kandidat,
                )
                for url, kandidat in urls_att_hamta
            }

            for future in as_completed(
                futures
            ):

                url, kandidat = futures[
                    future
                ]

                try:
                    detaljdata = future.result()

                except Exception as e:

                    info(
                        "[bilweb]   FEL i "
                        "detaljsida-worker "
                        f"{url}: {e}"
                    )

                    continue

                if not detaljdata:
                    continue

                cache[url] = detaljdata

                kandidat_data = dict(
                    kandidat
                )

                kandidat_data.update(
                    detaljdata
                )

                resultat[url] = kandidat_data

    return (
        resultat,
        antal_hamtade,
        antal_cache,
    )
