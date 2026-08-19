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
        text,
    )

    return int(siffror) if siffror else 0


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

    pris_match = re.search(
        r"(?:^|\n)\s*Pris\s*(?:\([^)]*\))?\s*\n+\s*([\d\s]+)\s*kr",
        text,
        re.IGNORECASE,
    )

    mil_match = re.search(
        r"(?:^|\n)\s*Mil\s*\n+\s*(\d[\d\s]*)\s*(?:\n|$)",
        text,
        re.IGNORECASE,
    )

    if not pris_match:

        pris_match = PRIS_DETALJ_REGEX.search(
            text.replace(
                "\n",
                " ",
            )
        )

    if not mil_match:

        mil_match = MIL_DETALJ_REGEX.search(
            text
        )

    if not pris_match or not mil_match:

        info(
            f"[bilweb]   Kunde inte tolka "
            f"pris/mil på detaljsidan: {url}"
        )

        return None

    agare_match = (
        AGARE_DETALJ_REGEX.search(
            text.replace(
                "\n",
                " ",
            )
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
        "pris": _rensa_tal(
            pris_match.group(1)
        ),
        "miltal": _rensa_tal(
            mil_match.group(1)
        ),
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
