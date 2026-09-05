"""
Läsning och normalisering av historiska marknadsdata.

Modulen ansvarar endast för att:
- läsa JSONL
- läsa flera JSONL-filer
- hitta relevanta fält
- normalisera pris, miltal och årsmodell
- tolka identifierare och tidsstämplar

Modulen filtrerar inte bort observationer.
"""

from __future__ import annotations

import json
import math
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable


FIELD_ALIASES = {
    "price": (
        "annonspris",
        "price",
        "pris",
        "asking_price",
        "listing_price",
        "advertised_price",
    ),
    "mileage": (
        "miltal",
        "mileage",
        "milage",
        "mil",
        "odometer",
        "km",
        "kilometers",
        "kilometres",
    ),
    "model_year": (
        "arsmodell",
        "årsmodell",
        "model_year",
        "modelYear",
        "year",
        "registration_year",
        "reg_year",
    ),
    "variant": (
        "variant",
        "model_variant",
        "modelVariant",
        "version",
        "engine_variant",
        "motor_variant",
        "trim",
    ),
    "vehicle_id": (
        "vehicle_id",
        "vehicleId",
        "car_id",
        "carId",
    ),
    "ad_id": (
        "annons_id",
        "annonsId",
        "ad_id",
        "adId",
        "listing_id",
        "listingId",
    ),
    "url": (
        "url",
        "ad_url",
        "adUrl",
        "listing_url",
        "listingUrl",
        "annons_url",
        "annonsUrl",
    ),
    "timestamp": (
        "tid",
        "timestamp",
        "observed_at",
        "observedAt",
        "observation_date",
        "observationDate",
        "scraped_at",
        "scrapedAt",
        "created_at",
        "createdAt",
        "date",
        "datum",
    ),
}


def first_value(
    record: dict[str, Any],
    keys: Iterable[str],
) -> Any:
    """Returnerar första existerande, icke-tomma värdet."""

    for key in keys:
        if key not in record:
            continue

        value = record[key]

        if value is None:
            continue

        if isinstance(value, str) and not value.strip():
            continue

        return value

    return None


def parse_number(value: Any) -> float | None:
    """Försöker tolka ett värde som ett ändligt flyttal."""

    if value is None or isinstance(value, bool):
        return None

    if isinstance(value, (int, float)):
        number = float(value)
        return number if math.isfinite(number) else None

    if not isinstance(value, str):
        return None

    text = value.strip()

    if not text:
        return None

    text = (
        text
        .replace("\xa0", " ")
        .replace("kr", "")
        .replace("mil", "")
        .replace("km", "")
        .strip()
    )

    text = text.replace(" ", "")

    if "," in text and "." in text:
        text = text.replace(".", "").replace(",", ".")
    elif "," in text:
        text = text.replace(",", ".")

    try:
        number = float(text)
    except ValueError:
        return None

    return number if math.isfinite(number) else None


def parse_integer(value: Any) -> int | None:
    """Tolkar ett värde som heltal."""

    number = parse_number(value)

    if number is None:
        return None

    return int(round(number))


def parse_datetime(value: Any) -> datetime | None:
    """Tolkar vanliga datum- och tidsformat."""

    if value is None:
        return None

    if isinstance(value, datetime):
        return value

    text = str(value).strip()

    if not text:
        return None

    try:
        return datetime.fromisoformat(
            text.replace("Z", "+00:00")
        )
    except ValueError:
        pass

    formats = (
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
        "%Y-%m",
        "%d-%m-%Y",
        "%d/%m/%Y",
    )

    for date_format in formats:
        try:
            return datetime.strptime(
                text,
                date_format,
            )
        except ValueError:
            continue

    return None


def normalize_variant(value: Any) -> str | None:
    """Minimal normalisering av variant."""

    if value is None:
        return None

    text = str(value).strip()

    return text if text else None


def load_jsonl(
    path: Path,
    encoding: str = "utf-8",
) -> list[dict[str, Any]]:
    """
    Läser en JSONL-fil.

    Ogiltiga rader rapporteras men stoppar inte hela läsningen.
    """

    records: list[dict[str, Any]] = []

    with path.open(
        "r",
        encoding=encoding,
    ) as file:
        for line_number, line in enumerate(
            file,
            start=1,
        ):
            line = line.strip()

            if not line:
                continue

            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                print(
                    f"VARNING: ogiltig JSON på rad "
                    f"{line_number}: {exc}",
                    file=sys.stderr,
                )
                continue

            if not isinstance(record, dict):
                print(
                    f"VARNING: rad {line_number} "
                    "innehåller inte ett JSON-objekt.",
                    file=sys.stderr,
                )
                continue

            records.append(record)

    return records


def load_jsonl_files(
    paths: Iterable[Path],
    encoding: str = "utf-8",
) -> list[dict[str, Any]]:
    """Läser flera JSONL-filer i angiven ordning."""

    records: list[dict[str, Any]] = []

    for path in paths:
        records.extend(
            load_jsonl(
                path,
                encoding=encoding,
            )
        )

    return records


def extract_fields(
    record: dict[str, Any],
) -> dict[str, Any]:
    """
    Skapar en standardiserad vy av en råpost.

    Originalposten påverkas inte.
    """

    return {
        "price": parse_number(
            first_value(
                record,
                FIELD_ALIASES["price"],
            )
        ),
        "mileage": parse_number(
            first_value(
                record,
                FIELD_ALIASES["mileage"],
            )
        ),
        "model_year": parse_integer(
            first_value(
                record,
                FIELD_ALIASES["model_year"],
            )
        ),
        "variant": normalize_variant(
            first_value(
                record,
                FIELD_ALIASES["variant"],
            )
        ),
        "vehicle_id": first_value(
            record,
            FIELD_ALIASES["vehicle_id"],
        ),
        "ad_id": first_value(
            record,
            FIELD_ALIASES["ad_id"],
        ),
        "url": first_value(
            record,
            FIELD_ALIASES["url"],
        ),
        "timestamp": parse_datetime(
            first_value(
                record,
                FIELD_ALIASES["timestamp"],
            )
        ),
    }


def extract_dataset(
    records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Normaliserar hela datasetet."""

    return [
        extract_fields(record)
        for record in records
    ]
