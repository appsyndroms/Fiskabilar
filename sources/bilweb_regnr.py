"""
Registreringsnummerextraktion för Bilweb.

REGNR accepteras endast när sidan uttryckligen kopplar
värdet till registreringsinformation.

Vi gör alltså INTE en generell sökning efter ABC123.
"""

import json
import re

from bs4 import BeautifulSoup


REGNR_REGEX = re.compile(
    r"(?<![A-ZÅÄÖ0-9])"
    r"([A-ZÅÄÖ]{3})"
    r"[\s-]?"
    r"("
    r"\d{3}"
    r"|"
    r"\d{2}[A-Z]"
    r")"
    r"(?![A-ZÅÄÖ0-9])",
    re.IGNORECASE,
)


REGNR_ETIKETT_REGEX = re.compile(
    r"(?:"
    r"\bregistreringsnummer\b"
    r"|"
    r"\bregistreringsnr\b"
    r"|"
    r"\breg\.?\s*nr\.?\b"
    r"|"
    r"\bregnr\b"
    r"|"
    r"\breg\.?\s*nummer\b"
    r")",
    re.IGNORECASE,
)


REGNR_FALTNAMN = (
    "registrationnumber",
    "registration_number",
    "registrationno",
    "registration_no",
    "registernumber",
    "reg_number",
    "regnr",
    "registration",
)


def normalisera_regnr(
    regnr: str | None,
) -> str | None:

    if not regnr:
        return None

    normaliserat = re.sub(
        r"[^A-Za-zÅÄÖåäö0-9]",
        "",
        str(regnr),
    ).upper()

    if len(normaliserat) not in (6, 7):
        return None

    if not re.fullmatch(
        r"[A-ZÅÄÖ]{3}(?:\d{3}|\d{2}[A-Z])",
        normaliserat,
        re.IGNORECASE,
    ):
        return None

    return normaliserat


def extrahera_regnr_kandidat(
    text: str | None,
) -> str | None:

    if not text:
        return None

    match = REGNR_REGEX.search(
        str(text)
    )

    if not match:
        return None

    kandidat = (
        f"{match.group(1)}"
        f"{match.group(2)}"
    )

    return normalisera_regnr(
        kandidat
    )


def extrahera_regnr_etikett_samma_text(
    text: str,
) -> str | None:

    if not text:
        return None

    match = REGNR_ETIKETT_REGEX.search(
        text
    )

    if not match:
        return None

    efter = text[
        match.end():
    ]

    prefix = re.match(
        r"^[\s:;=\-–—]*",
        efter,
    )

    if not prefix:
        return None

    kandidat_text = efter[
        prefix.end():
        prefix.end() + 30
    ]

    return extrahera_regnr_kandidat(
        kandidat_text
    )


def extrahera_regnr_dom(
    soup: BeautifulSoup,
) -> str | None:

    textnoder = soup.find_all(
        string=REGNR_ETIKETT_REGEX
    )

    for textnod in textnoder:

        text = str(textnod).strip()

        kandidat = (
            extrahera_regnr_etikett_samma_text(
                text
            )
        )

        if kandidat:
            return kandidat

        element = getattr(
            textnod,
            "parent",
            None,
        )

        if element is None:
            continue

        element_text = element.get_text(
            " ",
            strip=True,
        )

        kandidat = (
            extrahera_regnr_etikett_samma_text(
                element_text
            )
        )

        if kandidat:
            return kandidat

        for child in element.find_all(
            recursive=True
        ):

            child_text = child.get_text(
                " ",
                strip=True,
            )

            if len(child_text) > 300:
                continue

            if not REGNR_ETIKETT_REGEX.search(
                child_text
            ):
                continue

            kandidat = (
                extrahera_regnr_etikett_samma_text(
                    child_text
                )
            )

            if kandidat:
                return kandidat

            for sibling in child.find_all_next(
                limit=5
            ):

                sibling_text = sibling.get_text(
                    " ",
                    strip=True,
                )

                if len(sibling_text) > 100:
                    continue

                kandidat = (
                    extrahera_regnr_kandidat(
                        sibling_text
                    )
                )

                if kandidat:
                    return kandidat

        for sibling in element.find_all_next(
            limit=8
        ):

            sibling_text = sibling.get_text(
                " ",
                strip=True,
            )

            if not sibling_text:
                continue

            if len(sibling_text) > 150:
                continue

            if (
                sibling is not element
                and REGNR_ETIKETT_REGEX.search(
                    sibling_text
                )
            ):

                kandidat = (
                    extrahera_regnr_etikett_samma_text(
                        sibling_text
                    )
                )

                if kandidat:
                    return kandidat

            kandidat = (
                extrahera_regnr_kandidat(
                    sibling_text
                )
            )

            if kandidat:
                return kandidat

        container = element

        for _ in range(4):

            container = getattr(
                container,
                "parent",
                None,
            )

            if container is None:
                break

            container_text = container.get_text(
                " ",
                strip=True,
            )

            if len(container_text) > 1000:
                continue

            etikett_match = (
                REGNR_ETIKETT_REGEX.search(
                    container_text
                )
            )

            if not etikett_match:
                continue

            efter = container_text[
                etikett_match.end():
            ][:100]

            kandidat = (
                extrahera_regnr_kandidat(
                    efter
                )
            )

            if kandidat:
                return kandidat

    return None


def extrahera_regnr_attribut(
    soup: BeautifulSoup,
) -> str | None:

    for element in soup.find_all(True):

        attributtext = " ".join(
            str(value)
            for value in element.attrs.values()
            if isinstance(value, (str, list))
        )

        if not REGNR_ETIKETT_REGEX.search(
            attributtext
        ):
            continue

        for key, value in element.attrs.items():

            if isinstance(value, list):
                value = " ".join(
                    str(v)
                    for v in value
                )

            value = str(value)

            key_normaliserad = re.sub(
                r"[^a-z0-9]",
                "",
                key.lower(),
            )

            if (
                key_normaliserad in REGNR_FALTNAMN
                or "registration"
                in key_normaliserad
                or "regnr"
                in key_normaliserad
            ):

                kandidat = (
                    extrahera_regnr_kandidat(
                        value
                    )
                )

                if kandidat:
                    return kandidat

        kandidat = (
            extrahera_regnr_etikett_samma_text(
                element.get_text(
                    " ",
                    strip=True,
                )
            )
        )

        if kandidat:
            return kandidat

    return None


def _iterera_json_objekt(obj):

    if isinstance(obj, dict):

        yield obj

        for value in obj.values():

            yield from _iterera_json_objekt(
                value
            )

    elif isinstance(obj, list):

        for value in obj:

            yield from _iterera_json_objekt(
                value
            )


def extrahera_regnr_json(
    soup: BeautifulSoup,
) -> str | None:

    for script in soup.find_all(
        "script"
    ):

        script_text = script.string

        if not script_text:
            script_text = script.get_text(
                strip=True
            )

        if not script_text:
            continue

        typ = script.get(
            "type",
            "",
        ).lower()

        if (
            "json" not in typ
            and "application/ld+json"
            not in typ
        ):
            continue

        try:

            data = json.loads(
                script_text
            )

        except (
            ValueError,
            TypeError,
        ):
            continue

        for obj in _iterera_json_objekt(
            data
        ):

            for key, value in obj.items():

                key_normaliserad = re.sub(
                    r"[^a-z0-9]",
                    "",
                    str(key).lower(),
                )

                if (
                    key_normaliserad
                    not in REGNR_FALTNAMN
                ):
                    continue

                if isinstance(
                    value,
                    (dict, list),
                ):
                    continue

                kandidat = (
                    extrahera_regnr_kandidat(
                        str(value)
                    )
                )

                if kandidat:
                    return kandidat

    return None


def extrahera_regnr_html(
    html: str,
) -> str | None:

    if not html:
        return None

    match = REGNR_ETIKETT_REGEX.search(
        html
    )

    if not match:
        return None

    start = max(
        0,
        match.start() - 100,
    )

    slut = min(
        len(html),
        match.end() + 500,
    )

    område = html[
        start:slut
    ]

    område = re.sub(
        r"<[^>]+>",
        " ",
        område,
    )

    område = re.sub(
        r"\s+",
        " ",
        område,
    )

    etikett_match = (
        REGNR_ETIKETT_REGEX.search(
            område
        )
    )

    if not etikett_match:
        return None

    efter = område[
        etikett_match.end():
    ][:100]

    return extrahera_regnr_kandidat(
        efter
    )


def extrahera_regnr(
    soup: BeautifulSoup,
    html: str,
) -> str | None:

    regnr = extrahera_regnr_dom(
        soup
    )

    if regnr:
        return regnr

    regnr = extrahera_regnr_attribut(
        soup
    )

    if regnr:
        return regnr

    regnr = extrahera_regnr_json(
        soup
    )

    if regnr:
        return regnr

    return extrahera_regnr_html(
        html
    )
