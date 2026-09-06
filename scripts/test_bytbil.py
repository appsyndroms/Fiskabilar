"""
Diagnostiktest för Bytbil.

Syfte:
    Ta reda på exakt vad Bytbil returnerar till GitHub Actions.

Testet:
    - gör ett HTTP-anrop till Bytbil
    - visar HTTP-status
    - visar slutlig URL
    - visar HTML-storlek
    - visar sidans titel
    - räknar script-taggar
    - analyserar JSON-LD
    - letar efter relevanta länkar
    - söker efter V60/T6/T8 i HTML
    - visar relevanta HTML-fragment

Testet:
    - ändrar inte produktionsdata
    - sparar inte annonser
    - ändrar inte market_history
    - kör inte valuation
    - skickar inga mejl
"""

from __future__ import annotations

import json
import re
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


BAS_URL = "https://www.bytbil.com"

SOK_URL = (
    "https://www.bytbil.com/bil/volvo/v60"
)


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
        "text/html,"
        "application/xhtml+xml,"
        "application/xml;q=0.9,"
        "image/avif,"
        "image/webp,"
        "image/apng,"
        "*/*;q=0.8"
    ),
    "Accept-Language": (
        "sv-SE,sv;q=0.9,en-US;q=0.8,en;q=0.7"
    ),
    "Cache-Control": "no-cache",
}


def rubrik(text: str) -> None:
    print()
    print("=" * 70)
    print(text)
    print("=" * 70)


def rensa(text: str) -> str:
    return re.sub(
        r"\s+",
        " ",
        text or "",
    ).strip()


def analysera_json_ld(
    soup: BeautifulSoup,
) -> None:

    rubrik("JSON-LD")

    scripts = soup.find_all(
        "script",
        type="application/ld+json",
    )

    print(
        f"Antal JSON-LD-script: {len(scripts)}"
    )

    for index, script in enumerate(
        scripts,
        start=1,
    ):

        text = script.string

        if not text:
            print(
                f"\nJSON-LD #{index}: tom"
            )
            continue

        print(
            f"\nJSON-LD #{index}: "
            f"{len(text):,} tecken"
        )

        try:
            data = json.loads(text)

            if isinstance(data, dict):

                print(
                    "Typ:",
                    data.get("@type"),
                )

                print(
                    "Namn:",
                    data.get("name"),
                )

                print(
                    "URL:",
                    data.get("url"),
                )

                print(
                    "Pris:",
                    data.get("offers"),
                )

                print(
                    "Nycklar:",
                    list(data.keys())[:30],
                )

            elif isinstance(data, list):

                print(
                    f"Lista med {len(data)} objekt"
                )

                for objekt in data[:5]:

                    if isinstance(
                        objekt,
                        dict,
                    ):
                        print(
                            {
                                "type": objekt.get(
                                    "@type"
                                ),
                                "name": objekt.get(
                                    "name"
                                ),
                                "url": objekt.get(
                                    "url"
                                ),
                            }
                        )

        except Exception as e:

            print(
                "Kunde inte tolka JSON-LD:",
                repr(e),
            )


def analysera_lankar(
    soup: BeautifulSoup,
) -> None:

    rubrik("LÄNKAR MED /BIL/")

    lankar = []

    sedda = set()

    for element in soup.find_all(
        "a",
        href=True,
    ):

        href = element.get("href")

        if not href:
            continue

        url = urljoin(
            BAS_URL,
            href,
        )

        if "/bil/" not in url.lower():
            continue

        if url in sedda:
            continue

        sedda.add(url)

        text = rensa(
            element.get_text(
                " ",
                strip=True,
            )
        )

        lankar.append(
            (
                url,
                text,
            )
        )

    print(
        f"Antal unika /bil/-länkar: "
        f"{len(lankar)}"
    )

    for index, (
        url,
        text,
    ) in enumerate(
        lankar[:50],
        start=1,
    ):

        print()
        print(
            f"[{index}] {url}"
        )

        if text:
            print(
                f"    TEXT: {text[:300]}"
            )


def sok_text(
    html: str,
) -> None:

    rubrik("TEXTSÖKNING")

    text = html.lower()

    sokord = [
        "v60",
        "t6",
        "t8",
        "recharge",
        "twin engine",
        "volvo",
        "annons",
        "pris",
        "miltal",
        "årsmodell",
    ]

    for ordet in sokord:

        antal = text.count(
            ordet.lower()
        )

        print(
            f"{ordet:15} {antal}"
        )


def visa_relevanta_fragment(
    html: str,
) -> None:

    rubrik(
        "RELEVANTA HTML-FRAGMENT"
    )

    monster = re.compile(
        r".{0,300}"
        r"(?:v60|t6|t8|recharge|twin engine)"
        r".{0,500}",
        re.IGNORECASE,
    )

    matcher = monster.findall(
        html
    )

    print(
        f"Antal hittade fragment: "
        f"{len(matcher)}"
    )

    for index, fragment in enumerate(
        matcher[:20],
        start=1,
    ):

        print()
        print(
            f"--- FRAGMENT {index} ---"
        )

        print(
            rensa(fragment)[:1000]
        )


def analysera_script(
    soup: BeautifulSoup,
) -> None:

    rubrik("SCRIPT-TAGGAR")

    scripts = soup.find_all(
        "script"
    )

    print(
        f"Antal script-taggar: "
        f"{len(scripts)}"
    )

    for index, script in enumerate(
        scripts[:30],
        start=1,
    ):

        src = script.get("src")

        if src:

            print(
                f"[{index}] SRC: {src}"
            )

        else:

            text = script.string or ""

            print(
                f"[{index}] inline: "
                f"{len(text):,} tecken"
            )


def analysera_html(
    html: str,
) -> None:

    rubrik("HTML")

    print(
        f"HTML-storlek: "
        f"{len(html):,} bytes"
    )

    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    title = soup.find(
        "title"
    )

    if title:

        print(
            "TITLE:",
            rensa(
                title.get_text()
            ),
        )

    else:

        print(
            "TITLE: saknas"
        )

    print(
        "BODY finns:",
        soup.body is not None,
    )

    print(
        "DIV-taggar:",
        len(
            soup.find_all("div")
        ),
    )

    print(
        "A-taggar:",
        len(
            soup.find_all("a")
        ),
    )

    analysera_script(
        soup
    )

    analysera_json_ld(
        soup
    )

    analysera_lankar(
        soup
    )


def main() -> None:

    rubrik(
        "BYTBIL DIAGNOSTIK"
    )

    print(
        f"URL: {SOK_URL}"
    )

    print(
        f"User-Agent: "
        f"{HEADERS['User-Agent']}"
    )

    print()

    try:

        response = requests.get(
            SOK_URL,
            headers=HEADERS,
            timeout=30,
            allow_redirects=True,
        )

    except Exception as e:

        rubrik(
            "HTTP-FEL"
        )

        print(
            repr(e)
        )

        return

    rubrik(
        "HTTP-RESULTAT"
    )

    print(
        "Status:",
        response.status_code,
    )

    print(
        "URL efter redirects:",
        response.url,
    )

    print(
        "Content-Type:",
        response.headers.get(
            "content-type"
        ),
    )

    print(
        "Server:",
        response.headers.get(
            "server"
        ),
    )

    print(
        "Content-Length:",
        response.headers.get(
            "content-length"
        ),
    )

    print(
        "X-Powered-By:",
        response.headers.get(
            "x-powered-by"
        ),
    )

    html = response.text

    analysera_html(
        html
    )

    sok_text(
        html
    )

    visa_relevanta_fragment(
        html
    )

    rubrik(
        "FÄRDIG"
    )

    print(
        "Inga filer har skrivits."
    )

    print(
        "Ingen produktionsdata har ändrats."
    )


if __name__ == "__main__":
    main()
