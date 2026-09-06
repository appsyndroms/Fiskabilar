"""
Analyslogik för Fiskabilar Analytics.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
from statistics import median
from typing import Any


from data_loader import (
    to_number,
)


# ---------------------------------------------------------------------------
# Grundfunktioner
# ---------------------------------------------------------------------------

def vehicle_key(
    row: dict[str, Any],
) -> str:
    """
    Stabil identitet för en bil.
    """

    return str(
        row.get("vehicle_id")
        or row.get("annons_id")
        or row.get("id")
        or row.get("url")
        or ""
    )


def parse_time(
    value: Any,
) -> datetime | None:
    """
    Parsar ISO-tid.
    """

    if not value:
        return None

    try:
        return datetime.fromisoformat(
            str(value).replace(
                "Z",
                "+00:00",
            )
        )

    except ValueError:
        return None


def model_label(
    row: dict[str, Any],
) -> str:
    """
    Bygger modellnamn.

    Exempel:

        v60 + T6 AWD
        -> V60 T6 AWD
    """

    modell = str(
        row.get("modell")
        or ""
    ).strip()

    variant = str(
        row.get("variant")
        or ""
    ).strip()

    if not modell:
        return (
            variant
            or "Okänd modell"
        )

    if variant:
        return (
            modell.upper()
            + " "
            + variant.upper()
        )

    return modell.upper()


def latest_by_vehicle(
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Hämtar senaste observationen per bil.
    """

    latest: dict[
        str,
        dict[str, Any],
    ] = {}

    for row in rows:

        key = vehicle_key(
            row
        )

        if not key:
            continue

        current_time = (
            parse_time(
                row.get("tid")
            )
        )

        previous = (
            latest.get(key)
        )

        if previous is None:
            latest[key] = row
            continue

        previous_time = (
            parse_time(
                previous.get("tid")
            )
        )

        if (
            current_time
            and previous_time
        ):

            if (
                current_time
                >= previous_time
            ):
                latest[key] = row

        else:
            latest[key] = row

    return list(
        latest.values()
    )


# ---------------------------------------------------------------------------
# Aktuella fynd
# ---------------------------------------------------------------------------

def get_current_findings(
    feedback: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Hämtar aktuella fynd.

    Viktigt:

    Den aktuella feedback-datan använder `utfall=AKTIV`
    medan äldre struktur använder `livscykelstatus`.

    Därför kontrolleras båda.
    """

    fynd = [
        row
        for row in feedback
        if row.get("typ")
        == "fynd"
    ]

    latest = latest_by_vehicle(
        fynd
    )

    active_statuses = {
        "AKTIV",
        "NY",
        "ÅTERKOMMEN",
    }

    result = []

    for row in latest:

        status = str(
            row.get("utfall")
            or row.get(
                "livscykelstatus"
            )
            or ""
        ).strip().upper()

        if status in active_statuses:
            result.append(
                row
            )

    result.sort(
        key=lambda row: (
            to_number(
                row.get("score")
            )
            or 0
        ),
        reverse=True,
    )

    return result


# ---------------------------------------------------------------------------
# Prissänkningar
# ---------------------------------------------------------------------------

def has_price_reduction(
    row: dict[str, Any],
) -> bool:
    """
    Avgör om en bil faktiskt har haft en prissänkning.

    Vi använder flera fält eftersom olika generationer
    av feedback-data kan lagra informationen på olika sätt.
    """

    first = to_number(
        row.get(
            "historik_forsta_pris"
        )
    )

    latest = to_number(
        row.get(
            "historik_senaste_pris"
        )
    )

    total = to_number(
        row.get(
            "total_prissankning"
        )
    )

    fall = to_number(
        row.get(
            "historik_prisfall"
        )
    )

    initial = to_number(
        row.get(
            "initialpris"
        )
    )

    lowest = to_number(
        row.get(
            "lagsta_pris"
        )
    )

    lifecycle = str(
        row.get(
            "utfall"
        )
        or ""
    ).upper()

    if (
        fall is not None
        and fall > 0
    ):
        return True

    if (
        first is not None
        and latest is not None
        and latest < first
    ):
        return True

    if (
        total is not None
        and total > 0
    ):
        return True

    if (
        initial is not None
        and lowest is not None
        and lowest < initial
    ):
        return True

    if lifecycle in {
        "PRISSÄNKT",
        "FÖRSVUNNEN_EFTER_PRISSÄNKNING",
    }:
        return True

    return False


def get_price_reductions(
    feedback: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Hämtar faktiska prissänkningar.
    """

    result = []

    for row in feedback:

        if row.get("typ") != "fynd":
            continue

        if not has_price_reduction(
            row
        ):
            continue

        copy = dict(row)

        first = (
            to_number(
                row.get(
                    "historik_forsta_pris"
                )
            )
            or to_number(
                row.get(
                    "initialpris"
                )
            )
        )

        latest = (
            to_number(
                row.get(
                    "historik_senaste_pris"
                )
            )
            or to_number(
                row.get(
                    "lagsta_pris"
                )
            )
        )

        reduction = (
            to_number(
                row.get(
                    "total_prissankning"
                )
            )
        )

        if (
            reduction is None
            or reduction <= 0
        ):
            reduction = (
                to_number(
                    row.get(
                        "historik_prisfall"
                    )
                )
            )

        if (
            (
                reduction is None
                or reduction <= 0
            )
            and first is not None
            and latest is not None
        ):
            reduction = (
                first - latest
            )

        if reduction is None:
            reduction = 0

        copy[
            "_display_initialpris"
        ] = first

        copy[
            "_display_latestpris"
        ] = latest

        copy[
            "_display_reduction"
        ] = reduction

        if (
            first is not None
            and first > 0
        ):
            copy[
                "_display_percentage"
            ] = (
                reduction
                / first
                * 100
            )
        else:
            copy[
                "_display_percentage"
            ] = None

        result.append(
            copy
        )

    result.sort(
        key=lambda row: (
            to_number(
                row.get(
                    "_display_reduction"
                )
            )
            or 0
        ),
        reverse=True,
    )

    return result


# ---------------------------------------------------------------------------
# Fyndutfall
# ---------------------------------------------------------------------------

def get_find_outcomes(
    feedback: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Grupperar fyndobservationer till fynd-event.
    """

    fynd = [
        row
        for row in feedback
        if row.get("typ")
        == "fynd"
    ]

    grouped: dict[
        str,
        list[dict[str, Any]],
    ] = defaultdict(list)

    for row in fynd:

        key = vehicle_key(
            row
        )

        if key:
            grouped[
                key
            ].append(row)

    events = []

    for rows in grouped.values():

        rows.sort(
            key=lambda row: (
                parse_time(
                    row.get("tid")
                )
                or datetime.min
            )
        )

        current_event = None

        for row in rows:

            status = str(
                row.get("utfall")
                or row.get(
                    "livscykelstatus"
                )
                or ""
            ).upper()

            if (
                current_event is None
                or status in {
                    "NY",
                    "ÅTERKOMMEN",
                }
            ):
                current_event = dict(
                    row
                )

                events.append(
                    current_event
                )

    events.sort(
        key=lambda row: (
            parse_time(
                row.get("tid")
            )
            or datetime.min
        )
    )

    return events


# ---------------------------------------------------------------------------
# Score
# ---------------------------------------------------------------------------

def get_score_analysis(
    outcomes: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Delar in fynd i scoreintervall.
    """

    buckets = {
        "0–39": [],
        "40–59": [],
        "60–69": [],
        "70–79": [],
        "80–89": [],
        "90–100": [],
    }

    for row in outcomes:

        score = to_number(
            row.get("score")
        )

        if score is None:
            continue

        if score < 40:
            bucket = "0–39"

        elif score < 60:
            bucket = "40–59"

        elif score < 70:
            bucket = "60–69"

        elif score < 80:
            bucket = "70–79"

        elif score < 90:
            bucket = "80–89"

        else:
            bucket = "90–100"

        buckets[
            bucket
        ].append(row)

    result = []

    for bucket, rows in (
        buckets.items()
    ):

        counts = Counter(
            str(
                row.get(
                    "utfall",
                    "OKÄNT",
                )
            )
            for row in rows
        )

        result.append(
            {
                "scoreintervall":
                    bucket,

                "antal":
                    len(rows),

                "utfall":
                    dict(counts),
            }
        )

    return result


# ---------------------------------------------------------------------------
# Marknadshistorik
# ---------------------------------------------------------------------------

def get_market_history_analysis(
    rows: list[dict[str, Any]],
) -> tuple[
    list[dict[str, Any]],
    dict[
        str,
        dict[
            str,
            list[
                dict[str, Any]
            ],
        ],
    ],
]:
    """
    Bygger en översiktlig marknadshistorik.

    Grupp:

        modell + variant + årsmodell

    Sammanfattning:

        antal observationer
        medianpris
        snittpris
        medianmiltal

    Diagramdata:

        daglig medianpris
        per modell
        med en serie per årsmodell
    """

    groups: dict[
        tuple[str, int],
        list[
            dict[str, Any]
        ],
    ] = defaultdict(list)

    for row in rows:

        modell = str(
            row.get("modell")
            or ""
        ).strip()

        variant = str(
            row.get("variant")
            or ""
        ).strip()

        if modell:
            if variant:
                label = (
                    modell.upper()
                    + " "
                    + variant.upper()
                )
            else:
                label = modell.upper()
        else:
            label = (
                variant.upper()
                or "OKÄND MODELL"
            )

        year = (
            to_number(
                row.get(
                    "arsmodell"
                )
            )
            or to_number(
                row.get(
                    "modell_ar"
                )
            )
        )

        price = (
            to_number(
                row.get(
                    "annonspris"
                )
            )
            or to_number(
                row.get("pris")
            )
            or to_number(
                row.get("price")
            )
        )

        mileage = (
            to_number(
                row.get("miltal")
            )
            or to_number(
                row.get("mil")
            )
            or to_number(
                row.get("mileage")
            )
        )

        timestamp = (
            row.get("tid")
            or row.get("datum")
            or row.get("timestamp")
        )

        parsed = parse_time(
            timestamp
        )

        if (
            year is None
            or price is None
            or parsed is None
        ):
            continue

        groups[
            (
                label,
                int(year),
            )
        ].append(
            {
                "time":
                    parsed,

                "price":
                    price,

                "mileage":
                    mileage,
            }
        )

    table = []

    series: dict[
        str,
        dict[
            str,
            list[
                dict[str, Any]
            ],
        ],
    ] = defaultdict(
        lambda:
            defaultdict(list)
    )

    for (
        label,
        year,
    ), values in sorted(
        groups.items()
    ):

        prices = [
            value["price"]
            for value in values
        ]

        mileages = [
            value["mileage"]
            for value in values
            if value["mileage"]
            is not None
        ]

        table.append(
            {
                "modell":
                    label,

                "arsmodell":
                    year,

                "antal":
                    len(values),

                "medianpris":
                    median(prices),

                "snittpris":
                    (
                        sum(prices)
                        / len(prices)
                    ),

                "medianmiltal":
                    (
                        median(mileages)
                        if mileages
                        else None
                    ),
            }
        )

        by_day: dict[
            str,
            list[float],
        ] = defaultdict(list)

        for value in values:

            day = (
                value["time"]
                .date()
                .isoformat()
            )

            by_day[
                day
            ].append(
                value["price"]
            )

        series[
            label
        ][
            str(year)
        ] = [
            {
                "date":
                    day,

                "price":
                    median(
                        day_prices
                    ),
            }
            for day,
            day_prices
            in sorted(
                by_day.items()
            )
        ]

    return (
        table,
        {
            model: dict(
                years
            )
            for model, years
            in series.items()
        },
    )
