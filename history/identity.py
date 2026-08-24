"""
Identity resolution för Fiskabilar.

Målet är att identifiera samma FYSISKA bil över flera körningar,
även när annons-ID eller URL förändras.

Prioritet:

1. Registreringsnummer
2. VIN/chassinummer
3. Källa + annons-ID
4. URL
5. Modell + årsmodell + miltal + pris som sista fallback

Viktigt:

- En stark identifierare får inte ersättas av en svagare.
- URL är inte primär fordonsidentitet.
- Fingerprint används endast som sista fallback.
- Identity resolution påverkar inte valuation eller score.
"""

from __future__ import annotations

import json
import os
import re
import unicodedata
from hashlib import sha1

from app_logging.logger import info

from config import HISTORIK_KATALOG


IDENTITY_FIL = os.path.join(
    HISTORIK_KATALOG,
    "vehicle_identity.json",
)


def _normalisera_text(value) -> str:
    if value is None:
        return ""

    text = str(value).strip().lower()

    text = unicodedata.normalize(
        "NFKD",
        text,
    )

    text = "".join(
        c
        for c in text
        if not unicodedata.combining(c)
    )

    text = re.sub(
        r"[^a-z0-9]+",
        " ",
        text,
    )

    return " ".join(
        text.split()
    )


def _normalisera_regnr(value) -> str:
    if not value:
        return ""

    return re.sub(
        r"[^A-Za-z0-9]",
        "",
        str(value),
    ).upper()


def _normalisera_vin(value) -> str:
    if not value:
        return ""

    return re.sub(
        r"[^A-Za-z0-9]",
        "",
        str(value),
    ).upper()


def _normalisera_url(value) -> str:
    if not value:
        return ""

    return str(value).strip().rstrip("/")


def _hamta_url(bil: dict) -> str:
    url = bil.get("url")

    if url:
        return _normalisera_url(url)

    urls = bil.get("urls") or []

    for kandidat in urls:
        if kandidat:
            return _normalisera_url(kandidat)

    return ""


def _hamta_kalla(bil: dict) -> str:
    kallor = bil.get("kallor") or []

    if isinstance(
        kallor,
        (list, tuple),
    ):
        if kallor:
            return str(
                kallor[0]
            ).strip().lower()

    kalla = bil.get("kalla")

    if kalla:
        return str(
            kalla
        ).strip().lower()

    return ""


def _hamta_annons_id(bil: dict) -> str:
    value = bil.get(
        "annons_id"
    )

    if not value:
        return ""

    return str(
        value
    ).strip()


def _hamta_vin(bil: dict) -> str:
    for falt in (
        "vin",
        "chassinummer",
        "chassinr",
        "vin_nummer",
    ):
        value = _normalisera_vin(
            bil.get(falt)
        )

        if value:
            return value

    return ""


def _fingerprint(bil: dict) -> str:
    """
    Sista fallback.

    Pris ingår medvetet eftersom detta endast ska vara
    en sista-resort-identitet och inte en generell fuzzy-matchning.
    """

    modell = _normalisera_text(
        bil.get("modell")
    )

    variant = _normalisera_text(
        bil.get("variant")
    )

    arsmodell = str(
        bil.get("arsmodell")
        or ""
    ).strip()

    miltal = str(
        bil.get("miltal")
        or ""
    ).strip()

    pris = str(
        bil.get("annonspris")
        or ""
    ).strip()

    kalla = _hamta_kalla(
        bil
    )

    text = "|".join(
        (
            kalla,
            modell,
            variant,
            arsmodell,
            miltal,
            pris,
        )
    )

    digest = sha1(
        text.encode(
            "utf-8"
        )
    ).hexdigest()[:16]

    return f"fp:{digest}"


def _identifierare(bil: dict) -> list[tuple[str, str]]:
    """
    Returnerar identifierare i prioriterad ordning.
    """

    identifierare = []

    regnr = _normalisera_regnr(
        bil.get("regnr")
    )

    if regnr:
        identifierare.append(
            (
                "regnr",
                f"reg:{regnr}",
            )
        )

    vin = _hamta_vin(
        bil
    )

    if vin:
        identifierare.append(
            (
                "vin",
                f"vin:{vin}",
            )
        )

    kalla = _hamta_kalla(
        bil
    )

    annons_id = _hamta_annons_id(
        bil
    )

    if kalla and annons_id:
        identifierare.append(
            (
                "source_id",
                f"source:{kalla}:{annons_id}",
            )
        )

    url = _hamta_url(
        bil
    )

    if url:
        identifierare.append(
            (
                "url",
                f"url:{url}",
            )
        )

    identifierare.append(
        (
            "fingerprint",
            _fingerprint(bil),
        )
    )

    return identifierare


def _ladda() -> dict:
    if not os.path.exists(
        IDENTITY_FIL
    ):
        return {
            "version": 1,
            "identifiers": {},
            "vehicles": {},
        }

    try:
        with open(
            IDENTITY_FIL,
            "r",
            encoding="utf-8",
        ) as f:
            data = json.load(f)

    except (
        OSError,
        json.JSONDecodeError,
    ):
        info(
            "[IDENTITY] Kunde inte läsa "
            f"{IDENTITY_FIL}; börjar med tom identity-store."
        )

        return {
            "version": 1,
            "identifiers": {},
            "vehicles": {},
        }

    if not isinstance(
        data,
        dict,
    ):
        return {
            "version": 1,
            "identifiers": {},
            "vehicles": {},
        }

    data.setdefault(
        "version",
        1,
    )

    data.setdefault(
        "identifiers",
        {},
    )

    data.setdefault(
        "vehicles",
        {},
    )

    return data


def _spara(data: dict) -> None:
    os.makedirs(
        HISTORIK_KATALOG,
        exist_ok=True,
    )

    temporar = (
        IDENTITY_FIL
        + ".tmp"
    )

    with open(
        temporar,
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=2,
        )

    os.replace(
        temporar,
        IDENTITY_FIL,
    )


def _ny_vehicle_id() -> str:
    data = _ladda()

    nummer = len(
        data["vehicles"]
    ) + 1

    return (
        f"vehicle:{nummer:08d}"
    )


def _registrera_identifierare(
    data: dict,
    vehicle_id: str,
    bil: dict,
) -> None:
    for typ, identifierare in _identifierare(
        bil
    ):
        befintlig = data[
            "identifiers"
        ].get(
            identifierare
        )

        if (
            befintlig
            and befintlig != vehicle_id
        ):
            continue

        data[
            "identifiers"
        ][identifierare] = vehicle_id


def _metadata(
    bil: dict,
) -> dict:
    return {
        "modell": bil.get(
            "modell"
        ),
        "variant": bil.get(
            "variant"
        ),
        "arsmodell": bil.get(
            "arsmodell"
        ),
        "regnr": _normalisera_regnr(
            bil.get("regnr")
        )
        or None,
        "vin": _hamta_vin(
            bil
        )
        or None,
    }


def resolve_vehicle_id(
    bil: dict,
) -> str:
    """
    Returnerar canonical vehicle_id för bilen.

    Om en starkare identifierare dyker upp senare försöker
    vi koppla den till samma fordon istället för att skapa
    ett nytt historikobjekt.
    """

    data = _ladda()

    identifierare = _identifierare(
        bil
    )

    hittade = []

    for _, identifierare_value in identifierare:
        vehicle_id = data[
            "identifiers"
        ].get(
            identifierare_value
        )

        if (
            vehicle_id
            and vehicle_id not in hittade
        ):
            hittade.append(
                vehicle_id
            )

    if hittade:
        vehicle_id = hittade[0]

    else:
        vehicle_id = _ny_vehicle_id()

        data[
            "vehicles"
        ][vehicle_id] = {
            "created": True,
            "metadata": _metadata(
                bil
            ),
        }

    # Om flera identifierare pekar på olika fordon
    # använder vi den första starkaste träffen som
    # canonical identity. Vi skriver inte ihop dem
    # automatiskt på grundval av en svag identifierare.
    #
    # Starkare identifierare prioriteras redan genom
    # ordningen i _identifierare().
    _registrera_identifierare(
        data,
        vehicle_id,
        bil,
    )

    data[
        "vehicles"
    ].setdefault(
        vehicle_id,
        {},
    )

    data[
        "vehicles"
    ][vehicle_id][
        "metadata"
    ] = _metadata(
        bil
    )

    _spara(
        data
    )

    bil[
        "vehicle_id"
    ] = vehicle_id

    return vehicle_id


def identity_diagnostik(
    bil: dict,
) -> dict:
    """
    Returnerar identifieringsinformation för diagnostik.
    """

    identifierare = _identifierare(
        bil
    )

    return {
        "vehicle_id": bil.get(
            "vehicle_id"
        ),
        "identifierare": [
            {
                "typ": typ,
                "value": value,
            }
            for typ, value in identifierare
        ],
    }
