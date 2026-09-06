from __future__ import annotations

import re
from urllib.parse import urljoin


BAS_URL = "https://www.bytbil.com"


def rensa_text(value) -> str:
    if value is None:
        return ""

    return re.sub(
        r"\s+",
        " ",
        str(value),
    ).strip()


def tolka_pris(value) -> int | None:
    if value is None:
        return None

    if isinstance(value, (int, float)):
        pris = int(value)
        return pris if pris >= 10_000 else None

    text = rensa_text(value)

    if not text:
        return None

    match = re.search(
        r"(\d[\d\s.,\xa0]{3,})",
        text,
    )

    if not match:
        return None

    nummer = (
        match.group(1)
        .replace("\xa0", "")
        .replace(" ", "")
        .replace(".", "")
        .replace(",", "")
    )

    if not nummer.isdigit():
        return None

    pris = int(nummer)

    if pris < 10_000:
        return None

    return pris


def tolka_arsmodell(value) -> int | None:
    if value is None:
        return None

    if isinstance(value, (int, float)):
        ar = int(value)

        if 1990 <= ar <= 2030:
            return ar

        return None

    text = rensa_text(value)

    match = re.search(
        r"\b(19[9]\d|20\d{2})\b",
        text,
    )

    if not match:
        return None

    ar = int(match.group(1))

    if not 1990 <= ar <= 2030:
        return None

    return ar


def tolka_miltal(value) -> float | None:
    if value is None:
        return None

    if isinstance(value, (int, float)):
        mil = float(value)

        return mil if mil >= 0 else None

    text = rensa_text(value)

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
        mil = float(nummer)
    except ValueError:
        return None

    if mil < 0:
        return None

    return mil


def normalisera_url(url: str | None) -> str | None:
    if not url:
        return None

    url = str(url).strip()

    if not url:
        return None

    return urljoin(
        BAS_URL,
        url,
    )


def hamta_falt(data: dict, *namn):
    for namn_i in namn:
        if namn_i in data:
            value = data[namn_i]

            if value is not None and value != "":
                return value

    return None


def bygg_sok_url(bilkonfig: dict) -> str | None:
    marke = (
        bilkonfig.get("marke_slug")
        or ""
    ).lower()

    modell = (
        bilkonfig.get("modell_slug")
        or ""
    ).lower()

    if marke == "volvo":
        if modell == "v60":
            return f"{BAS_URL}/bil/volvo/v60"

        if modell == "v90":
            return f"{BAS_URL}/bil/volvo/v90"

    if marke == "bmw":
        if modell.startswith("330e"):
            return f"{BAS_URL}/bil/bmw/3-serie"

        if modell.startswith("530e"):
            return f"{BAS_URL}/bil/bmw/5-serie"

    return None
