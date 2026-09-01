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

_DIAGNOSTIK_LOGGAD = False


def _rensa_tal(text: str) -> int:
    siffror = re.sub(r"\D", "", text)
    return int(siffror) if siffror else 0


def _logga_detaljsida_diagnostik(
    url: str,
    resp: requests.Response,
    html: str,
    text: str,
) -> None:
    """
    Loggar rådata från den första detaljsida där pris eller miltal
    inte kunde hittas.

    Syftet är att avgöra om Bilweb skickar:
    - riktig HTML
    - en JS-shell
    - ett bot-/captcha-svar
    - en redirect
    - eller data i något annat format.
    """

    global _DIAGNOSTIK_LOGGAD

    if _DIAGNOSTIK_LOGGAD:
        return

    _DIAGNOSTIK_LOGGAD = True

    html_lower = html.lower()

    markers = {
        "pris": "pris" in html_lower,
        "mil": re.search(r"\bmil\b", html, re.IGNORECASE) is not None,
        "kr": "kr" in html_lower,
        "regdatum": "regdatum" in html_lower,
        "next_data": "__next_data__" in html_lower,
        "jsonld": "application/ld+json" in html_lower,
        "cloudflare": "cloudflare" in html_lower,
        "captcha": "captcha" in html_lower,
        "access_denied": "access denied" in html_lower,
        "forbidden": "forbidden" in html_lower,
    }

    info("")
    info("[bilweb] ===== DETALJSIDE-DIAGNOSTIK =====")
    info(f"[bilweb] URL: {url}")
    info(f"[bilweb] HTTP-status: {resp.status_code}")
    info(f"[bilweb] Slutlig URL: {resp.url}")
    info(f"[bilweb] Content-Type: {resp.headers.get('Content-Type')}")
    info(f"[bilweb] Server: {resp.headers.get('Server')}")
    info(f"[bilweb] HTML-längd: {len(html)} tecken")
    info(f"[bilweb] Redirects: {len(resp.history)}")

    if resp.history:
        for i, history_response in enumerate(resp.history, start=1):
            info(
                "[bilweb]   redirect "
                f"{i}: {history_response.status_code} "
                f"{history_response.url}"
            )

    info("[bilweb] Markörer:")
    for name, value in markers.items():
        info(f"[bilweb]   {name}: {value}")

    info("[bilweb] ----- RÅ HTML, första 2000 tecknen -----")
    info(html[:2000])

    info("[bilweb] ----- EXTRAHERAD TEXT, första 2000 tecknen -----")
    info(text[:2000])

    info("[bilweb] ===== SLUT DIAGNOSTIK =====")
    info("")


def _hamta_json_ld(soup: BeautifulSoup) -> list[dict]:
    """
    Hämtar JSON-LD-block från sidan.
    Returnerar endast objekt som faktiskt går att tolka som dict.
    """

    resultat = []

    for script in soup.find_all(
        "script",
        attrs={"type": "application/ld+json"},
    ):
        innehall = script.string or script.get_text(strip=True)

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


def _hitta_rekursivt(data, nycklar: set[str]):
    """
    Söker rekursivt efter första förekomsten av någon av nycklarna.
    """

    if isinstance(data, dict):
        for key, value in data.items():
            if key.lower() in nycklar:
                return value

            resultat = _hitta_rekursivt(value, nycklar)
            if resultat is not None:
                return resultat

    elif isinstance(data, list):
        for item in data:
            resultat = _hitta_rekursivt(item, nycklar)
            if resultat is not None:
                return resultat

    return None


def _pris_fran_json_ld(json_ld: list[dict]) -> int | None:
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
        siffror = re.sub(r"[^\d]", "", value)
        if siffror:
            return int(siffror)

    return None


def _mil_fran_json_ld(json_ld: list[dict]) -> int | None:
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
        siffror = re.sub(r"[^\d]", "", value)
        if siffror:
            return int(siffror)

    return None


def _pris_fran_meta(soup: BeautifulSoup) -> int | None:
    """
    Försöker hitta pris i vanliga meta-attribut.
    """

    kandidater = [
        soup.find("meta", attrs={"property": "product:price:amount"}),
        soup.find("meta", attrs={"name": "price"}),
        soup.find("meta", attrs={"itemprop": "price"}),
    ]

    for meta in kandidater:
        if not meta:
            continue

        value = meta.get("content")
        if not value:
            continue

        siffror = re.sub(r"[^\d]", "", value)

        if siffror:
            return int(siffror)

    return None


def _mil_fran_html_attribut(soup: BeautifulSoup) -> int | None:
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

            siffror = re.sub(r"[^\d]", "", str(value))

            if siffror:
                return int(siffror)

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
            f"[bilweb]   FEL vid hämtning av detaljsida "
            f"{url}: {e}"
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

    # ---------------------------------------------------------
    # Pris
    # ---------------------------------------------------------

    pris = None

    pris_match = re.search(
        r"(?:^|\n)\s*Pris\s*(?:\([^)]*\))?\s*\n+\s*([\d\s]+)\s*kr",
        text,
        re.IGNORECASE,
    )

    if pris_match:
        pris = _rensa_tal(
            pris_match.group(1)
        )

    if pris is None:
        pris_match = PRIS_DETALJ_REGEX.search(
            text.replace("\n", " ")
        )

        if pris_match:
            pris = _rensa_tal(
                pris_match.group(1)
            )

    if pris is None:
        pris = _pris_fran_meta(soup)

    json_ld = _hamta_json_ld(soup)

    if pris is None:
        pris = _pris_fran_json_ld(json_ld)

    # ---------------------------------------------------------
    # Miltal
    # ---------------------------------------------------------

    miltal = None

    mil_match = re.search(
        r"(?:^|\n)\s*Mil\s*\n+\s*(\d[\d\s]*)\s*(?:\n|$)",
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

    # ---------------------------------------------------------
    # Diagnostik
    # ---------------------------------------------------------

    if pris is None or miltal is None:
        _logga_detaljsida_diagnostik(
            url=url,
            resp=resp,
            html=html,
            text=text,
        )

        info(
            "[bilweb]   Kunde inte tolka pris/mil "
            f"på detaljsidan: "
            f"pris={'OK' if pris is not None else 'SAKNAS'}, "
            f"mil={'OK' if miltal is not None else 'SAKNAS'}: "
            f"{url}"
        )

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
            kandidat_data = dict(kandidat)
            kandidat_data.update(
                cache[url]
            )

            resultat[url] = kandidat_data
            antal_cache += 1

        else:
            urls_att_hamta.append(
                (url, kandidat)
            )

    antal_hamtade = len(urls_att_hamta)

    if urls_att_hamta:
        info(
            "[bilweb]   hämtar "
            f"{len(urls_att_hamta)} detaljsidor parallellt "
            f"med {MAX_PARALLELLA_DETALJSIDOR} workers"
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

            for future in as_completed(futures):
                url, kandidat = futures[future]

                try:
                    detaljdata = future.result()

                except Exception as e:
                    info(
                        "[bilweb]   FEL i detaljsida-worker "
                        f"{url}: {e}"
                    )
                    continue

                if not detaljdata:
                    continue

                cache[url] = detaljdata

                kandidat_data = dict(kandidat)
                kandidat_data.update(
                    detaljdata
                )

                resultat[url] = kandidat_data

    return (
        resultat,
        antal_hamtade,
        antal_cache,
    )
