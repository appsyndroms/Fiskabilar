"""
Diagram för Fiskabilar Analytics.

Diagrammen genereras som inline SVG så att webbplatsen
inte behöver Chart.js eller andra externa JavaScript-bibliotek.
"""

from __future__ import annotations

from typing import Any

from data_loader import (
    fmt_price,
    safe,
)


COLORS = [
    "#72a7ff",
    "#68d391",
    "#ecc94b",
    "#fc8181",
    "#b794f4",
    "#63b3ed",
    "#f6ad55",
    "#ed64a6",
]


def market_chart(
    model: str,
    year_series: dict[
        str,
        list[
            dict[str, Any]
        ],
    ],
) -> str:
    """
    Skapar ett prisdiagram för en modell.

    Varje årsmodell visas som en separat linje.
    """

    usable = {
        year: points
        for year, points
        in year_series.items()
        if points
    }

    if not usable:
        return """
        <div class="empty">
            Ingen tillräcklig historik.
        </div>
        """

    width = 900
    height = 360

    left = 90
    right = 70
    top = 50
    bottom = 60

    plot_width = (
        width
        - left
        - right
    )

    plot_height = (
        height
        - top
        - bottom
    )

    all_points = [
        point
        for points
        in usable.values()
        for point in points
    ]

    dates = sorted(
        {
            point["date"]
            for point in all_points
        }
    )

    prices = [
        float(
            point["price"]
        )
        for point
        in all_points
    ]

    min_price = min(
        prices
    )

    max_price = max(
        prices
    )

    if min_price == max_price:
        min_price -= 1
        max_price += 1

    date_index = {
        date: index
        for index, date
        in enumerate(dates)
    }

    def x_position(
        date: str,
    ) -> float:

        index = date_index[
            date
        ]

        if len(dates) <= 1:
            return (
                left
                + plot_width
                / 2
            )

        return (
            left
            + (
                index
                / (
                    len(dates)
                    - 1
                )
            )
            * plot_width
        )

    def y_position(
        price: float,
    ) -> float:

        return (
            top
            + (
                (
                    max_price
                    - price
                )
                / (
                    max_price
                    - min_price
                )
            )
            * plot_height
        )

    parts = [
        (
            '<svg '
            'class="market-chart" '
            f'viewBox="0 0 {width} {height}" '
            'preserveAspectRatio="xMidYMid meet" '
            'role="img" '
            f'aria-label="{safe(model)} '
            'prisutveckling">'
        )
    ]

    parts.append(
        f"""
        <text
            x="{left}"
            y="28"
            class="chart-title"
        >
            {safe(model)}
        </text>
        """
    )

    # Y-axel
    for tick in range(5):

        fraction = (
            tick / 4
        )

        value = (
            min_price
            + (
                max_price
                - min_price
            )
            * fraction
        )

        y = y_position(
            value
        )

        parts.append(
            f"""
            <line
                x1="{left}"
                y1="{y:.1f}"
                x2="{width-right}"
                y2="{y:.1f}"
                class="gridline"
            />

            <text
                x="5"
                y="{y + 4:.1f}"
                class="axis"
            >
                {safe(
                    fmt_price(value)
                )}
            </text>
            """
        )

    # X-axel
    if dates:

        x_dates = [
            dates[0],
            dates[-1],
        ]

        if len(dates) > 2:

            middle = dates[
                len(dates) // 2
            ]

            if middle not in x_dates:
                x_dates.insert(
                    1,
                    middle,
                )

        for date in x_dates:

            x = x_position(
                date
            )

            parts.append(
                f"""
                <text
                    x="{x:.1f}"
                    y="{height - 20}"
                    class="axis"
                    text-anchor="middle"
                >
                    {safe(date[:7])}
                </text>
                """
            )

    # Linjer
    for index, (
        year,
        points,
    ) in enumerate(
        sorted(
            usable.items(),
            key=lambda item:
                str(item[0]),
        )
    ):

        stroke = COLORS[
            index
            % len(COLORS)
        ]

        coordinates = " ".join(
            (
                f"{x_position(point['date']):.1f},"
                f"{y_position(float(point['price'])):.1f}"
            )
            for point in points
        )

        parts.append(
            f"""
            <polyline
                points="{coordinates}"
                fill="none"
                stroke="{stroke}"
                stroke-width="2.5"
                stroke-linejoin="round"
                stroke-linecap="round"
            />
            """
        )

        # Sista datapunkten
        last = points[-1]

        x = x_position(
            last["date"]
        )

        y = y_position(
            float(
                last["price"]
            )
        )

        parts.append(
            f"""
            <circle
                cx="{x:.1f}"
                cy="{y:.1f}"
                r="4"
                fill="{stroke}"
            />

            <text
                x="{x + 9:.1f}"
                y="{y + 4:.1f}"
                class="legend-label"
            >
                {safe(year)}
            </text>
            """
        )

    parts.append(
        "</svg>"
    )

    return "".join(parts)
