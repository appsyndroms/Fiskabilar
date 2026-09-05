"""
Profilering av historiska marknadsdata.

Ansvar:
- sekventiell filtrering
- bortfallsanalys
- orimliga värden
- deduplicering
- variantanalys
- variant × årsmodell
- statistik
- observationer per månad
- metadata coverage
- historiskt tidsintervall

Modulen skriver inte ut något.
Den returnerar strukturerad data som kan användas av CLI,
tester och framtida ML-pipeline.
"""

from __future__ import annotations

import math
import statistics
from collections import Counter
from datetime import datetime
from typing import Any


MIN_PRICE = 1_000
MAX_PRICE = 10_000_000

MIN_MILEAGE = 0
MAX_MILEAGE = 1_000_000

MIN_MODEL_YEAR = 1990
MAX_MODEL_YEAR = 2035


def statistics_for(
    values: list[float],
) -> dict[str, float | int | None]:
    """Beräknar grundläggande statistik."""

    if not values:
        return {
            "count": 0,
            "min": None,
            "p25": None,
            "median": None,
            "p75": None,
            "max": None,
        }

    ordered = sorted(values)

    def percentile(p: float) -> float:
        if len(ordered) == 1:
            return ordered[0]

        index = (len(ordered) - 1) * p
        lower = math.floor(index)
        upper = math.ceil(index)

        if lower == upper:
            return ordered[lower]

        weight = index - lower

        return (
            ordered[lower] * (1 - weight)
            + ordered[upper] * weight
        )

    return {
        "count": len(values),
        "min": min(values),
        "p25": percentile(0.25),
        "median": statistics.median(values),
        "p75": percentile(0.75),
        "max": max(values),
    }


def deduplication_key(
    observation: dict[str, Any],
) -> tuple[Any, ...]:
    """
    Identifierar en observation.

    Prioritet:
    vehicle_id → ad_id → URL → fallback.

    Den här funktionen bör senare ersättas med exakt samma
    dedupliceringsregel som används av ML-pipelinen.
    """

    timestamp = observation["timestamp"]

    if observation["vehicle_id"] is not None:
        return (
            "vehicle_id",
            str(observation["vehicle_id"]),
            timestamp,
        )

    if observation["ad_id"] is not None:
        return (
            "ad_id",
            str(observation["ad_id"]),
            timestamp,
        )

    if observation["url"] is not None:
        return (
            "url",
            str(observation["url"]),
            timestamp,
        )

    return (
        "fallback",
        observation["price"],
        observation["mileage"],
        observation["model_year"],
        observation["variant"],
        timestamp,
    )


def deduplicate(
    observations: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], int]:
    """Deduplicerar observationer."""

    seen: set[tuple[Any, ...]] = set()
    result: list[dict[str, Any]] = []

    duplicates = 0

    for observation in observations:
        key = deduplication_key(observation)

        if key in seen:
            duplicates += 1
            continue

        seen.add(key)
        result.append(observation)

    return result, duplicates


def profile_dataset(
    observations: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Profilerar datasetet genom hela ML-pipelinen.
    """

    raw_count = len(observations)

    # ---------------------------------------------------------------
    # Steg 1 – giltigt miltal
    # ---------------------------------------------------------------

    after_mileage = []

    missing_mileage = 0
    invalid_mileage = 0

    for observation in observations:
        mileage = observation["mileage"]

        if mileage is None:
            missing_mileage += 1
            continue

        if not (
            MIN_MILEAGE
            <= mileage
            <= MAX_MILEAGE
        ):
            invalid_mileage += 1
            continue

        after_mileage.append(observation)

    # ---------------------------------------------------------------
    # Steg 2 – giltig årsmodell
    # ---------------------------------------------------------------

    after_model_year = []

    missing_model_year = 0
    invalid_model_year = 0

    for observation in after_mileage:
        year = observation["model_year"]

        if year is None:
            missing_model_year += 1
            continue

        if not (
            MIN_MODEL_YEAR
            <= year
            <= MAX_MODEL_YEAR
        ):
            invalid_model_year += 1
            continue

        after_model_year.append(observation)

    # ---------------------------------------------------------------
    # Steg 3 – giltigt pris
    # ---------------------------------------------------------------

    after_price = []

    missing_price = 0
    invalid_price = 0

    for observation in after_model_year:
        price = observation["price"]

        if price is None:
            missing_price += 1
            continue

        if not (
            MIN_PRICE
            <= price
            <= MAX_PRICE
        ):
            invalid_price += 1
            continue

        after_price.append(observation)

    # ---------------------------------------------------------------
    # Deduplicering
    # ---------------------------------------------------------------

    before_deduplication = len(after_price)

    after_deduplication, duplicates_removed = deduplicate(
        after_price
    )

    # ---------------------------------------------------------------
    # Statistik
    # ---------------------------------------------------------------

    prices = [
        item["price"]
        for item in after_deduplication
        if item["price"] is not None
    ]

    mileages = [
        item["mileage"]
        for item in after_deduplication
        if item["mileage"] is not None
    ]

    model_years = [
        item["model_year"]
        for item in after_deduplication
        if item["model_year"] is not None
    ]

    # ---------------------------------------------------------------
    # Variant
    # ---------------------------------------------------------------

    variants = Counter(
        item["variant"]
        if item["variant"] is not None
        else "<saknas>"
        for item in after_deduplication
    )

    variant_model_year = Counter(
        (
            item["variant"]
            if item["variant"] is not None
            else "<saknas>",
            item["model_year"]
            if item["model_year"] is not None
            else "<saknas>",
        )
        for item in after_deduplication
    )

    # ---------------------------------------------------------------
    # Observationer per månad
    # ---------------------------------------------------------------

    observations_by_month = Counter()

    timestamps: list[datetime] = []

    for item in after_deduplication:
        timestamp = item["timestamp"]

        if timestamp is None:
            continue

        timestamps.append(timestamp)

        observations_by_month[
            timestamp.strftime("%Y-%m")
        ] += 1

    # ---------------------------------------------------------------
    # Metadata coverage
    # ---------------------------------------------------------------

    metadata_coverage = {}

    for field in (
        "vehicle_id",
        "ad_id",
        "url",
        "timestamp",
    ):
        count = sum(
            1
            for item in observations
            if item[field] is not None
        )

        metadata_coverage[field] = {
            "count": count,
            "percentage": (
                count / raw_count * 100
                if raw_count
                else 0
            ),
        }

    # ---------------------------------------------------------------
    # Slutresultat
    # ---------------------------------------------------------------

    return {
        "raw_count": raw_count,

        "pipeline": {
            "raw": raw_count,

            "after_mileage": len(after_mileage),
            "removed_missing_mileage": missing_mileage,
            "removed_invalid_mileage": invalid_mileage,

            "after_model_year": len(after_model_year),
            "removed_missing_model_year": missing_model_year,
            "removed_invalid_model_year": invalid_model_year,

            "after_price": len(after_price),
            "removed_missing_price": missing_price,
            "removed_invalid_price": invalid_price,

            "before_deduplication": before_deduplication,
            "duplicates_removed": duplicates_removed,
            "after_deduplication": len(after_deduplication),
        },

        "statistics": {
            "price": statistics_for(prices),
            "mileage": statistics_for(mileages),
            "model_year": statistics_for(model_years),
        },

        "variants": variants,

        "variant_model_year": variant_model_year,

        "observations_by_month": observations_by_month,

        "metadata_coverage": metadata_coverage,

        "history": {
            "first": min(timestamps)
            if timestamps
            else None,
            "last": max(timestamps)
            if timestamps
            else None,
            "count_with_timestamp": len(timestamps),
        },

        "thresholds": {
            "price": {
                "min": MIN_PRICE,
                "max": MAX_PRICE,
            },
            "mileage": {
                "min": MIN_MILEAGE,
                "max": MAX_MILEAGE,
            },
            "model_year": {
                "min": MIN_MODEL_YEAR,
                "max": MAX_MODEL_YEAR,
            },
        },
    }
