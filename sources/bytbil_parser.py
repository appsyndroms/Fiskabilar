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
    if start < 0 or start >= len(text) or text[start] != oppning:
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
        rf"""["']?{re.escape(nyckel)}["']?\s*:\s*(\[)""",
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
        return literal_eval(normaliserad)
    except (
        ValueError,
        SyntaxError,
    ):
        return None


def _hitta_annonsmetadata(
    soup: BeautifulSoup,
) -> dict[str, dict]:
    """
    Bygger ett index över Bytbils synliga
    annonsinformation.

    Bytbil visar årsmodell och miltal på
    annonssidan/listkortet, men dessa värden
    saknas i dataLayer-produktobjektet.

    Vi kopplar därför ihop annonsens ID med
    dess länk och den synliga texten i närmaste
    HTML-behållare.
    """
    metadata = {}

    for a in soup.find_all(
        "a",
        href=True,
    ):
        href = a.get("href")

        if not href:
            continue

        href_text = str(href)

        match = re.search(
            r"-(\d{5,})/?$",
            href_text,
        )

        if not match:
            continue

        annons_id = match.group(1)

        url = normalisera_url(
            href_text
        )

        textdelar = []

        for parent in a.parents:
            if parent is None:
                break

            text = rensa_text(
                parent.get_text(
                    " ",
                    strip=True,
                )
            )

            if not text:
                continue

            textdelar.append(text)

            # Vi vill ha den minsta rimliga
            # behållaren som innehåller både
            # årsmodell och miltal.
            if (
                re.search(
                    r"\b(?:19|20)\d{2}\b",
                    text,
                )
                and re.search(
                    r"\b\d[\d\s\xa0.,]*\s*mil\b",
                    text,
                    re.IGNORECASE,
                )
            ):
                break

            if len(textdelar) >= 6:
                break

        metadata[annons_id] = {
            "url": url,
            "text": " ".join(textdelar),
        }

    return metadata


def _hitta_arsmodell_i_text(
    text: str | None,
) -> int | None:
    if not text:
        return None

    match = re.search(
        r"\b(19\d{2}|20\d{2})\b",
        text,
    )

    if not match:
        return None

    return tolka_arsmodell(
        match.group(1)
    )


def _hitta_miltal_i_text(
    text: str | None,
) -> float | None:
    if not text:
        return None

    match = re.search(
        r"(\d[\d\s\xa0.,]*)\s*mil\b",
        text,
        re.IGNORECASE,
    )

    if not match:
        return None

    return tolka_miltal(
        match.group(0)
    )


def _berika_produkt_med_metadata(
    produkt: dict,
    metadata: dict[str, dict],
) -> dict:
    """
    Kopplar ett dataLayer-produktobjekt till
    information från HTML-listningen.
    """
    produkt = dict(produkt)

    annons_id = hamta_falt(
        produkt,
        "id",
        "annons_id",
        "productId",
    )

    if annons_id is None:
        return produkt

    metadata_i = metadata.get(
        str(annons_id)
    )

    if not metadata_i:
        return produkt

    produkt["_bytbil_url"] = metadata_i.get(
        "url"
    )

    produkt["_bytbil_text"] = metadata_i.get(
        "text"
    )

    return produkt


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

    Dessutom kopplas varje produkt ihop med
    motsvarande HTML-annons så att information
    som årsmodell och miltal kan hämtas även
    när den saknas i dataLayer.
    """
    produkter = []

    metadata = _hitta_annonsmetadata(
        soup
    )

    for script in soup.find_all(
        "script"
    ):
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
                if not isinstance(
                    item,
                    dict,
                ):
                    continue

                produkt = (
                    _berika_produkt_med_metadata(
                        item,
                        metadata,
                    )
                )

                produkter.append(
                    produkt
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

    metadata_text = produkt.get(
        "_bytbil_text"
    )

    metadata_url = produkt.get(
        "_bytbil_url"
    )

    arsmodell = tolka_arsmodell(
        arsmodell_raw
    )

    if arsmodell is None:
        arsmodell = _hitta_arsmodell_i_text(
            metadata_text
        )

    miltal = tolka_miltal(
        miltal_raw
    )

    miltal_fran_html = _hitta_miltal_i_text(
        metadata_text
    )

    if miltal_fran_html is not None:
        miltal = miltal_fran_html

        match_miltal = re.search(
            r"(\d[\d\s\xa0.,]*)\s*mil\b",
            metadata_text,
            re.IGNORECASE,
        )

        if match_miltal:
            miltal_raw = match_miltal.group(0)

    url = normalisera_url(
        hamta_falt(
            produkt,
            "url",
            "link",
            "productUrl",
        )
    )

    if url is None:
        url = metadata_url

    annons_id = hamta_falt(
        produkt,
        "id",
        "annons_id",
        "productId",
    )

    pris = tolka_pris(
        pris_raw
    )

    return {
        "namn": namn,
        "annonspris": pris,
        "pris_raw": pris_raw,
        "arsmodell": arsmodell,
        "arsmodell_raw": (
            arsmodell_raw
            if arsmodell_raw is not None
            else arsmodell
        ),
        "miltal": miltal,
        "miltal_raw": (
            miltal_raw
            if miltal_raw is not None
            else miltal
        ),
        "annons_id": (
            str(annons_id)
            if annons_id is not None
            else None
        ),
        "url": url,
        "produkt_raw": produkt,
    }
