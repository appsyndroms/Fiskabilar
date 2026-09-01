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


def _rensa_tal(
    text: str,
) -> int:

    siffror = re.sub(
        r"\D",
        "",
        str(text),
    )

    return int(siffror) if siffror else 0


def _normalisera_text(
    text: str,
) -> str:

    return re.sub(
        r"\s+",
        " ",
        text,
    ).strip()


def _extrahera_jsonld(
    soup: BeautifulSoup,
) -> list:

    resultat = []

    for script in soup.find_all(
        "script",
        attrs={
            "type": re.compile(
                r"application/ld\+json",
                re.IGNORECASE,
            )
        },
    ):

        innehall = script.string or script.get_text()

        if not innehall:
            continue

        try:

            data = json.loads(
                innehall
            )

        except (
            json.JSONDecodeError,
            TypeError,
        ):

            continue

        if isinstance(
            data,
            list,
        ):

            resultat.extend(
                data
            )

        else:

            resultat.append(
                data
            )

    return resultat


def _hitta_varde_i_jsonld(
    data,
    nycklar: set[str],
):

    if isinstance(
        data,
        dict,
    ):

        for key, value in data.items():

            if key.lower() in nycklar:

                if isinstance(
                    value,
                    (str, int, float),
                ):

                    return value

                if isinstance(
                    value,
                    dict,
                ):

                    for undernyckel in (
                        "value",
                        "amount",
                    ):

                        if undernyckel in value:

                            return value[
                                undernyckel
                            ]

            resultat = (
                _hitta_varde_i_jsonld(
                    value,
                    nycklar,
                )
            )

            if resultat is not None:

                return resultat

    elif isinstance(
        data,
        list,
    ):

        for item in data:

            resultat = (
                _hitta_varde_i_jsonld(
                    item,
                    nycklar,
                )
            )

            if resultat is not None:

                return resultat

    return None


def _extrahera_pris_fran_jsonld(
    soup: BeautifulSoup,
) -> int | None:

    jsonld_data = _extrahera_jsonld(
        soup
    )

    pris = _hitta_varde_i_jsonld(
        jsonld_data,
        {
            "price",
            "lowprice",
            "highprice",
        },
    )

    if pris is None:
        return None

    try:

        return _rensa_tal(
            pris
        )

    except (
        ValueError,
        TypeError,
    ):

        return None


def _extrahera_pris_fran_meta(
    soup: BeautifulSoup,
) -> int | None:

    meta_namn = {
        "price",
        "product:price:amount",
        "og:price:amount",
    }

    for meta in soup.find_all(
        "meta"
    ):

        namn = (
            meta.get("property")
            or meta.get("name")
            or ""
        ).lower()

        if namn not in meta_namn:
            continue

        content = meta.get(
            "content"
        )

        if not content:
            continue

        pris = _rensa_tal(
            content
        )

        if pris > 0:

            return pris

    return None


def _extrahera_pris_fran_text(
    text: str,
) -> int | None:

    # Försök först med den tidigare, mer precisa parsningen.
    pris_match = re.search(
        r"(?:^|\n)\s*Pris\s*(?:\([^)]*\))?\s*\n+\s*([\d\s]+)\s*kr",
        text,
        re.IGNORECASE,
    )

    if pris_match:

        return _rensa_tal(
            pris_match.group(1)
        )

    # Bilweb kan även presentera pris och värde
    # på samma rad eller med varierande whitespace.
    pris_match = PRIS_DETALJ_REGEX.search(
        text.replace(
            "\n",
            " ",
        )
    )

    if pris_match:

        return _rensa_tal(
            pris_match.group(1)
        )

    # Mer tolerant fallback:
    # "Pris 299 900 kr"
    # "Pris: 299 900 kr"
    # "Pris (inkl. moms) 299 900 kr"
    pris_match = re.search(
        r"\bPris\b"
        r"(?:\s*\([^)]*\))?"
        r"\s*:?"
        r"\s*([\d][\d\s]{2,})\s*kr\b",
        text,
        re.IGNORECASE,
    )

    if pris_match:

        return _rensa_tal(
            pris_match.group(1)
        )

    return None


def _extrahera_miltal_fran_text(
    text: str,
) -> int | None:

    # Tidigare format:
    # Mil
    # 12 345
    # 1:a regdatum
    mil_match = re.search(
        r"(?:^|\n)\s*Mil\s*\n+\s*(\d[\d\s]*)\s*(?:\n|$)",
        text,
        re.IGNORECASE,
    )

    if mil_match:

        return _rensa_tal(
            mil_match.group(1)
        )

    # Tidigare fallback.
    mil_match = MIL_DETALJ_REGEX.search(
        text
    )

    if mil_match:

        return _rensa_tal(
            mil_match.group(1)
        )

    # Mer tolerant format:
    # "Mil 12 345"
    # "Mil: 12 345"
    # "Mil\n12 345"
    #
    # Begränsa sökningen till ett rimligt antal
    # tecken efter "Mil" för att inte råka fånga
    # andra nummer längre ned på sidan.
    mil_match = re.search(
        r"\bMil\b"
        r"\s*:?"
        r"\s*(\d[\d\s]{1,10})"
        r"(?:\s*(?:mil|1:a\s+regdatum|km)\b|(?=\s|$))",
        text,
        re.IGNORECASE,
    )

    if mil_match:

        mil = _rensa_tal(
            mil_match.group(1)
        )

        if 0 < mil < 1_000_000:

            return mil

    return None


def _extrahera_miltal_fran_html(
    soup: BeautifulSoup,
) -> int | None:

    # Bilweb kan ha data-attribut eller
    # andra strukturerade attribut för mätarställning.
    kandidater = (
        "mileage",
        "mileageFromOdometer",
        "odometer",
        "kilometers",
        "kilometer",
        "miltal",
    )

    for tag in soup.find_all():

        for attribut in kandidater:

            value = tag.get(
                attribut
            )

            if value is None:
                continue

            mil = _rensa_tal(
                value
            )

            if 0 <= mil < 1_000_000:

                return mil

    return None


def hamta_pris_mil_fran_detaljsida(
    url: str,
) -> dict | None:

    try:

        resp = requests.get(
            url,
            headers=HEADERS,
            timeout=15,
        )

        resp.raise_for_status()

    except Exception as e:

        info(
            f"[bilweb]   FEL vid hämtning av "
            f"detaljsida {url}: {e}"
        )

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

    normaliserad_text = _normalisera_text(
        text
    )

    # ---------------------------------------------------------
    # Pris
    # ---------------------------------------------------------

    pris = _extrahera_pris_fran_jsonld(
        soup
    )

    if pris is None:

        pris = _extrahera_pris_fran_meta(
            soup
        )

    if pris is None:

        pris = _extrahera_pris_fran_text(
            text
        )

    # ---------------------------------------------------------
    # Miltal
    # ---------------------------------------------------------

    miltal = _extrahera_miltal_fran_text(
        text
    )

    if miltal is None:

        miltal = _extrahera_miltal_fran_html(
            soup
        )

    # JSON-LD kan ibland innehålla mätarställning
    # via mileageFromOdometer/Odometer.
    if miltal is None:

        jsonld_data = _extrahera_jsonld(
            soup
        )

        odometer = _hitta_varde_i_jsonld(
            jsonld_data,
            {
                "mileagefromodometer",
                "odometer",
                "mileage",
            },
        )

        if isinstance(
            odometer,
            dict,
        ):

            odometer = (
                odometer.get(
                    "value"
                )
                or odometer.get(
                    "amount"
                )
            )

        if odometer is not None:

            kandidat_miltal = _rensa_tal(
                odometer
            )

            if 0 <= kandidat_miltal < 1_000_000:

                miltal = kandidat_miltal

    # ---------------------------------------------------------
    # Diagnostik
    # ---------------------------------------------------------

    if pris is None or miltal is None:

        info(
            f"[bilweb]   Kunde inte tolka "
            f"pris/mil på detaljsidan: "
            f"pris={'OK' if pris is not None else 'SAKNAS'}, "
            f"mil={'OK' if miltal is not None else 'SAKNAS'}: "
            f"{url}"
        )

        return None

    # ---------------------------------------------------------
    # Övriga fält
    # ---------------------------------------------------------

    agare_match = (
        AGARE_DETALJ_REGEX.search(
            normaliserad_text
        )
    )

    antal_agare = (
        int(
            agare_match.group(1)
        )
        if agare_match
        else None
    )

    ar_auktion = (
        AUKTION_REGEX.search(
            text
        )
        is not None
    )

    regnr = extrahera_regnr(
        soup,
        html,
    )

    kaross = extrahera_kaross(
        text
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

    resultat_per_url = {}

    nya_kandidater = []

    cachetraffar = 0

    for kandidat in kandidater:

        url = kandidat["url"]

        if url in cache:

            resultat_per_url[url] = cache[url]
            cachetraffar += 1

        else:

            nya_kandidater.append(
                kandidat
            )

    if not nya_kandidater:

        return (
            resultat_per_url,
            cachetraffar,
            0,
        )

    info(
        f"[bilweb]   hämtar "
        f"{len(nya_kandidater)} detaljsidor "
        f"parallellt med "
        f"{MAX_PARALLELLA_DETALJSIDOR} workers"
    )

    with ThreadPoolExecutor(
        max_workers=MAX_PARALLELLA_DETALJSIDOR
    ) as executor:

        framtida = {
            executor.submit(
                hamta_pris_mil_fran_detaljsida,
                kandidat["url"],
            ): kandidat["url"]
            for kandidat in nya_kandidater
        }

        for future in as_completed(
            framtida
        ):

            url = framtida[
                future
            ]

            try:

                resultat = future.result()

            except Exception as e:

                info(
                    f"[bilweb]   FEL i parallell "
                    f"detaljhämtning: {url}: {e}"
                )

                resultat = None

            cache[url] = resultat
            resultat_per_url[url] = resultat

    return (
        resultat_per_url,
        cachetraffar,
        len(nya_kandidater),
    )
