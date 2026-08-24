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

Identity resolution stödjer även alias/merge:

- En bil kan först ha identifierats med URL/fingerprint.
- Senare kan regnr eller VIN bli känt.
- Den gamla identiteten kopplas då till den nya canonical vehicle_id.
- Historik och notifieringsstate kan därefter följa samma fysiska bil.

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


def _tom_store() -> dict:
    return {
        "version": 2,
        "identifiers": {},
        "vehicles": {},
        "aliases": {},
    }


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
        return _tom_store()

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

        return _tom_store()

    if not isinstance(
        data,
        dict,
    ):
        return _tom_store()

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

    data.setdefault(
        "aliases",
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


def _ny_vehicle_id(
    data: dict,
) -> str:
    nummer = len(
        data["vehicles"]
    ) + 1

    return (
        f"vehicle:{nummer:08d}"
    )


def _canonical_vehicle_id(
    data: dict,
    vehicle_id: str,
) -> str:
    """
    Följer alias-kedjor till canonical vehicle_id.

    Skyddar även mot trasiga/cykliska alias.
    """

    aktuell = vehicle_id
    besokta = set()

    while aktuell in data.get(
        "aliases",
        {}
    ):
        if aktuell in besokta:
            break

        besokta.add(
            aktuell
        )

        aktuell = data[
            "aliases"
        ][
            aktuell
        ]

    return aktuell


def canonical_vehicle_id(
    vehicle_id: str | None,
) -> str | None:
    """
    Publik hjälpfunktion för andra moduler som behöver
    översätta ett gammalt vehicle_id till canonical identity.
    """

    if not vehicle_id:
        return None

    data = _ladda()

    return _canonical_vehicle_id(
        data,
        str(vehicle_id),
    )


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


def _identifierare_for_vehicle(
    data: dict,
    vehicle_id: str,
) -> list[str]:
    canonical = _canonical_vehicle_id(
        data,
        vehicle_id,
    )

    return [
        identifierare
        for identifierare, kandidat in data[
            "identifiers"
        ].items()
        if _canonical_vehicle_id(
            data,
            kandidat,
        ) == canonical
    ]


def _merge_vehicle(
    data: dict,
    canonical: str,
    duplicate: str,
) -> None:
    """
    Slår ihop duplicate till canonical.

    Alla identifierare som pekar på duplicate flyttas till
    canonical och duplicate blir alias.

    Canonical väljs alltid av den starkaste identifieraren
    som hittades av resolve_vehicle_id().
    """

    canonical = _canonical_vehicle_id(
        data,
        canonical,
    )

    duplicate = _canonical_vehicle_id(
        data,
        duplicate,
    )

    if (
        canonical == duplicate
        or not duplicate
    ):
        return

    data.setdefault(
        "aliases",
        {},
    )

    data[
        "aliases"
    ][
        duplicate
    ] = canonical

    for identifierare, vehicle_id in list(
        data[
            "identifiers"
        ].items()
    ):
        if _canonical_vehicle_id(
            data,
            vehicle_id,
        ) == duplicate:
            data[
                "identifiers"
            ][
                identifierare
            ] = canonical

    canonical_vehicle = data[
        "vehicles"
    ].setdefault(
        canonical,
        {},
    )

    duplicate_vehicle = data[
        "vehicles"
    ].get(
        duplicate,
        {},
    )

    if duplicate_vehicle:
        gamla_alias = duplicate_vehicle.get(
            "aliases"
        ) or []

        canonical_alias = canonical_vehicle.setdefault(
            "aliases",
            [],
        )

        for alias in gamla_alias:
            if alias not in canonical_alias:
                canonical_alias.append(
                    alias
                )

        if duplicate not in canonical_alias:
            canonical_alias.append(
                duplicate
            )

    info(
        "[IDENTITY] Merge: "
        f"{duplicate} -> {canonical}"
    )


def _registrera_identifierare(
    data: dict,
    vehicle_id: str,
    bil: dict,
) -> None:
    vehicle_id = _canonical_vehicle_id(
        data,
        vehicle_id,
    )

    for typ, identifierare in _identifierare(
        bil
    ):
        befintlig = data[
            "identifiers"
        ].get(
            identifierare
        )

        if befintlig:
            befintlig = _canonical_vehicle_id(
                data,
                befintlig,
            )

            if befintlig != vehicle_id:
                # Detta ska normalt vara hanterat av
                # resolve_vehicle_id() innan registreringen.
                # Vi skriver därför inte över en annan identity
                # här utan starkare beslutsunderlag.
                continue

        data[
            "identifiers"
        ][
            identifierare
        ] = vehicle_id


def resolve_vehicle_id(
    bil: dict,
) -> str:
    """
    Returnerar canonical vehicle_id för bilen.

    Om en starkare identifierare dyker upp senare kan
    tidigare identiteter slås ihop.

    Exempel:

        körning 1:
            URL -> vehicle:00000017

        körning 2:
            regnr -> vehicle:00000042

        körning 2:
            URL + regnr
                ->
            vehicle:00000042

        resultat:
            vehicle:00000017 är alias till vehicle:00000042
    """

    data = _ladda()

    identifierare = _identifierare(
        bil
    )

    hittade: list[tuple[int, str, str]] = []

    for index, (
        typ,
        identifierare_value,
    ) in enumerate(
        identifierare
    ):
        vehicle_id = data[
            "identifiers"
        ].get(
            identifierare_value
        )

        if not vehicle_id:
            continue

        vehicle_id = _canonical_vehicle_id(
            data,
            vehicle_id,
        )

        hittade.append(
            (
                index,
                typ,
                vehicle_id,
            )
        )

    if hittade:
        # Första identifieraren är den starkaste.
        _, starkaste_typ, canonical = hittade[0]

    else:
        canonical = _ny_vehicle_id(
            data
        )

        data[
            "vehicles"
        ][
            canonical
        ] = {
            "created": True,
            "metadata": _metadata(
                bil
            ),
        }

        starkaste_typ = "new"

    # Om flera identifierare pekar på olika identiteter
    # har vi hittat ett identity conflict.
    #
    # Den starkaste identifieraren bestämmer canonical identity.
    # De svagare identiteterna blir alias till denna.
    unika = []

    for _, _, vehicle_id in hittade:
        if (
            vehicle_id != canonical
            and vehicle_id not in unika
        ):
            unika.append(
                vehicle_id
            )

    for duplicate in unika:
        _merge_vehicle(
            data,
            canonical,
            duplicate,
        )

    canonical = _canonical_vehicle_id(
        data,
        canonical,
    )

    _registrera_identifierare(
        data,
        canonical,
        bil,
    )

    data[
        "vehicles"
    ].setdefault(
        canonical,
        {
            "created": True,
        },
    )

    data[
        "vehicles"
    ][
        canonical
    ][
        "metadata"
    ] = _metadata(
        bil
    )

    data[
        "vehicles"
    ][
        canonical
    ][
        "last_seen"
    ] = bil.get(
        "annons_id"
    ) or bil.get(
        "url"
    )

    data[
        "vehicles"
    ][
        canonical
    ][
        "identifier_strength"
    ] = starkaste_typ

    data[
        "version"
    ] = 2

    _spara(
        data
    )

    bil[
        "vehicle_id"
    ] = canonical

    return canonical


def identity_diagnostik(
    bil: dict,
) -> dict:
    """
    Returnerar identifieringsinformation för diagnostik.
    """

    vehicle_id = bil.get(
        "vehicle_id"
    )

    if vehicle_id:
        vehicle_id = canonical_vehicle_id(
            vehicle_id
        )

    identifierare = _identifierare(
        bil
    )

    return {
        "vehicle_id": vehicle_id,
        "identifierare": [
            {
                "typ": typ,
                "value": value,
            }
            for typ, value in identifierare
        ],
    }
