"""
Gemensam normalisering av ML-kategorier.

Samma bil kan komma från olika källor med olika versaler,
bindestreck och mellanslag. ML-modellen måste alltid få samma
kategori vid träning och prediktion.
"""

from __future__ import annotations

import re


def _normalisera(value) -> str | None:
    """Grundnormalisering av text."""

    if value is None:
        return None

    text = str(value).strip().casefold()

    if not text:
        return None

    text = text.replace("_", " ")
    text = re.sub(
        r"[-/]+",
        " ",
        text,
    )
    text = re.sub(
        r"\s+",
        " ",
        text,
    ).strip()

    return text or None


def normalisera_modell(
    value,
) -> str | None:
    """Returnerar ett stabilt modellnamn."""

    text = _normalisera(value)

    if text is None:
        return None

    aliases = {
        "volvo v60": "v60",
        "v60": "v60",

        "volvo v90": "v90",
        "v90": "v90",

        "bmw 330e xdrive touring":
            "330e xdrive touring",

        "330e xdrive touring":
            "330e xdrive touring",

        "bmw 530e xdrive touring":
            "530e xdrive touring",

        "530e xdrive touring":
            "530e xdrive touring",
    }

    return aliases.get(
        text,
        text,
    )


def normalisera_variant(
    value,
) -> str | None:
    """Returnerar en stabil variantkategori."""

    text = _normalisera(value)

    if text is None:
        return None

    aliases = {
        "t6": "t6 awd",
        "t6 awd": "t6 awd",

        "t8": "t8 awd",
        "t8 awd": "t8 awd",

        "330e xdrive touring":
            "330e xdrive touring",

        "530e xdrive touring":
            "530e xdrive touring",
    }

    return aliases.get(
        text,
        text,
    )
