from __future__ import annotations

import json
import re
from ast import literal_eval

from bs4 import BeautifulSoup

from .bytbil_helpers import (
    hamta_falt,
    normalisera_url,
    rensa_text,
    tolka_arsmodell,
    tolka_miltal,
    tolka_pris,
)


def balanserad_del(
    text: str,
    start: int,
    oppning: str,
    stangning: str,
) -> str | None:
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

        if tecken in ('"', "'", "`"):
            in_string = True
            string_tecken = tecken
            i += 1
            continue

        if tecken == oppning:
            djup += 1

        elif tecken == stangning:
            djup -= 1

            if djup == 0:
                return text[start:i + 1]

        i += 1

    return None


def hitta_array_efter_nyckel(
    text: str,
    nyckel: str,
) -> str | None:
    monster = re.compile(
        r"""["']?"""
        + re.escape(nyckel)
        + r"""["']?\s*:\s*(\[)""",
        re.IGNORECASE,
    )

    match = monster.search(text)

    if not match:
        return None

    return balanserad_del(
        text,
        match.start(1),
        "[",
        "]",
    )


def js_till_python(text: str):
    if not text:
        return None

    try:
        return json.loads(text)

    except (
        json.JSONDecodeError,
        TypeError,
    ):
        pass

    try:
        return literal_eval(text)

    except (
        ValueError,
        SyntaxError,
    ):
        pass

    normaliserad = text

    normaliserad = re.sub(
        r"\btrue\b",
        "True",
        normaliserad,
        flags=re.IGNORECASE,
    )

    normaliserad = re.sub(
        r"\bfalse\b",
        "False",
        normaliserad,
        flags=re.IGNORECASE,
    )

    normaliserad = re.sub(
        r"\bnull\b",
        "None",
        normaliserad,
        flags=re.IGNORECASE,
    )

    normaliserad = re.sub(
        r",\s*([}\]])",
        r"\1",
        normaliserad,
    )

    try:
        return literal_eval(
            normaliserad
        )

    except (
        ValueError,
        SyntaxError,
    ):
        return None


def hamta_datalayer_produkter(
    soup: BeautifulSoup,
) -> list[dict]:
    """
    Hämtar produktobjekt från Bytbils
    JavaScript-dataLayer.

    Bytbil lägger annonserna i bland annat:

        ecommerce.impressions

    Funktionen letar efter både:

        impressions
        productList

    och returnerar alla produktobjekt
    som hittas.
    """

    produkter = []

    for script in soup.find_all("script"):
        text = script.string

        if not text:
            text = script.get_text()

        if not text:
            continue

        text_lower = text.lower()

        if (
            "impressions" not in text_lower
            and "productlist" not in text_lower
        ):
            continue

        for nyckel in (
            "impressions",
            "productList",
        ):
            block = hitta_array_efter_nyckel(
                text,
                nyckel,
            )

            if not block:
                continue

            data = js_till_python(
                block
            )

            if not isinstance(
                data,
                list,
            ):
                continue

            for item in data:
                if isinstance(
                    item,
                    dict,
                ):
                    produkter.append(
                        item
                    )

    return produkter


def hitta_annonslankar(
    soup: BeautifulSoup,
) -> list[str]:
    urler = []
    sedda = set()

    for a in soup.find_all(
        "a",
        href=True,
    ):
        href = a.get("href")

        if not href:
            continue

        href_lower = href.lower()

        if "/bil/" not in href_lower:
            continue

        url = normalisera_url(
            href
        )

        if not url:
            continue

        if url in sedda:
            continue

        sedda.add(url)
        urler.append(url)

    return urler


def produkt_till_annons(
    produkt: dict,
) -> dict:
    namn = rensa_text(
        hamta_falt(
            produkt,
            "name",
            "title",
            "model",
        )
    )

    pris_raw = hamta_falt(
        produkt,
        "price",
        "annonspris",
        "listPrice",
    )

    miltal_raw = hamta_falt(
        produkt,
        "mileage",
        "miltal",
        "mileageValue",
        "dimension2",
    )

    arsmodell_raw = hamta_falt(
        produkt,
        "year",
        "modelYear",
        "arsmodell",
    )

    url = normalisera_url(
        hamta_falt(
            produkt,
            "url",
            "link",
            "productUrl",
        )
    )

    annons_id = hamta_falt(
        produkt,
        "id",
        "annons_id",
        "productId",
    )

    pris = tolka_pris(
        pris_raw
    )

    arsmodell = tolka_arsmodell(
        arsmodell_raw
    )

    miltal = tolka_miltal(
        miltal_raw
    )

    return {
        "namn": namn,
        "annonspris": pris,
        "pris_raw": pris_raw,
        "arsmodell": arsmodell,
        "arsmodell_raw": arsmodell_raw,
        "miltal": miltal,
        "miltal_raw": miltal_raw,
        "annons_id": (
            str(annons_id)
            if annons_id is not None
            else None
        ),
        "url": url,
        "produkt_raw": produkt,
    }
