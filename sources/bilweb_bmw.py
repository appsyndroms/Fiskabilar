"""
BMW-specifik logik för Bilweb.

Hanterar:
- 530e / 530 e
- 330e / 330 e
- xDrive
- Touring
- detaljkontroll av kaross när Touring saknas i sluggen
"""

import re


BMW_MODELL_REGEX = re.compile(
    r"\b(530|330)\s*e\b",
    re.IGNORECASE,
)

BMW_XDRIVE_REGEX = re.compile(
    r"\bx\s*drive\b",
    re.IGNORECASE,
)

BMW_TOURING_REGEX = re.compile(
    r"\btouring\b",
    re.IGNORECASE,
)

BMW_530E_REGEX = re.compile(
    r"\b530\s*e\b",
    re.IGNORECASE,
)

BMW_330E_REGEX = re.compile(
    r"\b330\s*e\b",
    re.IGNORECASE,
)


BMW_MODELLER = {
    "530e-xdrive-touring",
    "330e-xdrive-touring",
}


def normalisera_bmw_modellslug(
    slug_text: str,
) -> str:

    if not slug_text:
        return slug_text

    slug_text = re.sub(
        r"\b530\s+e\b",
        "530e",
        slug_text,
        flags=re.IGNORECASE,
    )

    slug_text = re.sub(
        r"\b330\s+e\b",
        "330e",
        slug_text,
        flags=re.IGNORECASE,
    )

    return slug_text


def normalisera_bmw_matchtext(
    text: str,
) -> str:

    if not text:
        return ""

    text = str(text)

    text = re.sub(
        r"\b530\s+e\b",
        "530e",
        text,
        flags=re.IGNORECASE,
    )

    text = re.sub(
        r"\b330\s+e\b",
        "330e",
        text,
        flags=re.IGNORECASE,
    )

    return text


def ar_bmw_modell(
    bilkonfig: dict,
) -> bool:

    return (
        bilkonfig.get("marke_slug") == "bmw"
        and bilkonfig.get("modell_slug")
        in BMW_MODELLER
    )


def bmw_modell_matchar(
    bilkonfig: dict,
    text: str,
) -> bool:

    text = normalisera_bmw_matchtext(text)

    modell_slug = bilkonfig.get(
        "modell_slug",
        "",
    )

    if modell_slug == "530e-xdrive-touring":
        return (
            BMW_530E_REGEX.search(text)
            is not None
        )

    if modell_slug == "330e-xdrive-touring":
        return (
            BMW_330E_REGEX.search(text)
            is not None
        )

    return False


def bmw_xdrive_matchar(
    text: str,
) -> bool:

    if not text:
        return False

    return (
        BMW_XDRIVE_REGEX.search(str(text))
        is not None
    )


def bmw_touring_matchar(
    text: str,
) -> bool:

    if not text:
        return False

    return (
        BMW_TOURING_REGEX.search(str(text))
        is not None
    )


def bmw_kraver_detaljkontroll(
    bilkonfig: dict,
    slug_text: str,
) -> bool:

    """
    True om modellen + xDrive matchar men Touring
    saknas i sluggen.

    Då måste detaljsidan kontrolleras.
    """

    if not ar_bmw_modell(bilkonfig):
        return False

    slug_text = normalisera_bmw_matchtext(
        slug_text
    )

    if not bmw_modell_matchar(
        bilkonfig,
        slug_text,
    ):
        return False

    if not bmw_xdrive_matchar(slug_text):
        return False

    return not bmw_touring_matchar(
        slug_text
    )


def extrahera_kaross(
    text: str,
) -> str | None:

    if not text:
        return None

    normaliserad = re.sub(
        r"\s+",
        " ",
        str(text),
    ).strip()

    if re.search(
        r"\btouring\b",
        normaliserad,
        re.IGNORECASE,
    ):
        return "Touring"

    if re.search(
        r"\bcross\s*country\b",
        normaliserad,
        re.IGNORECASE,
    ):
        return "Cross Country"

    if re.search(
        r"\bkombi\b",
        normaliserad,
        re.IGNORECASE,
    ):
        return "Kombi"

    if re.search(
        r"\bsedan\b",
        normaliserad,
        re.IGNORECASE,
    ):
        return "Sedan"

    if re.search(
        r"\bsuv\b",
        normaliserad,
        re.IGNORECASE,
    ):
        return "SUV"

    return None


def kaross_kravs_for_bil(
    bilkonfig: dict,
) -> str | None:

    modell_slug = bilkonfig.get(
        "modell_slug",
        "",
    )

    if modell_slug in BMW_MODELLER:
        return "Touring"

    return None


def kaross_matchar(
    bilkonfig: dict,
    kaross: str | None,
    text: str,
) -> bool:

    krav = kaross_kravs_for_bil(
        bilkonfig
    )

    if krav is None:
        return True

    if krav == "Touring":

        if kaross == "Touring":
            return True

        return (
            BMW_TOURING_REGEX.search(
                text
            )
            is not None
        )

    return False
