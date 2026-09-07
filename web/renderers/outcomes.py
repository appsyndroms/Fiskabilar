"""
Rendering av fyndutfall och score.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from data_loader import (
    fmt_number,
    safe,
)


def _percentage(
    value: int,
    total: int,
) -> float:

    if not total:
        return 0.0

    return (
        value
        / total
        * 100
    )


def render_outcomes(
    rows: list[dict[str, Any]],
) -> str:

    if not rows:
        return """
        <div class="empty">
            Ingen fyndutfallsdata ännu.
        </div>
        """

    counts = Counter(
        str(
            row.get(
                "utfall",
                "OKÄNT",
            )
        ).strip()
        or "OKÄNT"
        for row in rows
    )

    total = sum(
        counts.values()
    )

    top_outcome = (
        counts.most_common(1)[0]
        if counts
        else ("—", 0)
    )

    bars = []

    for outcome, count in (
        counts.most_common()
    ):

        share = _percentage(
            count,
            total,
        )

        bars.append(
            f"""
            <div
                class="bar-row"
                data-outcome-row
            >

                <div class="bar-label">

                    <span>
                        {safe(outcome)}
                    </span>

                    <strong>
                        {fmt_number(count)}
                        <span class="muted">
                            ({share:.1f} %)
                        </span>
                    </strong>

                </div>

                <div class="bar">

                    <div
                        style="width:{share:.1f}%"
                    ></div>

                </div>

            </div>
            """
        )

    return f"""
    <div data-outcomes-container>

        <div class="stats-grid">

            <div class="stat-card">

                <span class="stat-label">
                    Totalt antal fyndevent
                </span>

                <strong class="stat-value">
                    {fmt_number(total)}
                </strong>

            </div>

            <div class="stat-card">

                <span class="stat-label">
                    Vanligaste utfall
                </span>

                <strong class="stat-value">
                    {safe(top_outcome[0])}
                </strong>

                <span class="muted">
                    {fmt_number(top_outcome[1])}
                    ({_percentage(
                        top_outcome[1],
                        total,
                    ):.1f} %)
                </span>

            </div>

            <div class="stat-card">

                <span class="stat-label">
                    Antal olika utfall
                </span>

                <strong class="stat-value">
                    {fmt_number(
                        len(counts)
                    )}
                </strong>

            </div>

        </div>


        <h3>
            Utfall
        </h3>

        <p class="muted">
            Fördelningen visar vad som hänt med de
            observerade fyndeventen.
        </p>

        <div class="outcome-bars">

            {"".join(bars)}

        </div>

    </div>
    """


def render_score_analysis(
    rows: list[dict[str, Any]],
) -> str:

    if not rows:
        return """
        <div class="empty">
            Inte tillräckligt med data ännu.
        </div>
        """

    total = sum(
        int(
            row.get(
                "antal",
                0,
            )
            or 0
        )
        for row in rows
    )

    high_score_count = sum(
        int(
            row.get(
                "antal",
                0,
            )
            or 0
        )
        for row in rows
        if str(
            row.get(
                "scoreintervall",
                "",
            )
        ).strip()
        in {
            "80–89",
            "90–100",
        }
    )

    output = []

    for row in rows:

        bucket = row[
            "scoreintervall"
        ]

        count = int(
            row.get(
                "antal",
                0,
            )
            or 0
        )

        outcomes = row.get(
            "utfall",
            {},
        )

        bucket_share = _percentage(
            count,
            total,
        )

        outcome_parts = []

        for name, value in sorted(
            outcomes.items()
        ):

            value = int(
                value
                or 0
            )

            outcome_share = _percentage(
                value,
                count,
            )

            outcome_parts.append(
                f"""
                <span class="score-outcome">
                    <strong>
                        {safe(name)}
                    </strong>
                    {fmt_number(value)}
                    ({outcome_share:.1f} %)
                </span>
                """
            )

        output.append(
            f"""
            <tr class="score-row">

                <td>
                    <strong>
                        {safe(bucket)}
                    </strong>
                </td>

                <td>
                    {fmt_number(count)}
                </td>

                <td>
                    {bucket_share:.1f} %
                </td>

                <td>
                    {
                        " · ".join(
                            outcome_parts
                        )
                        if outcome_parts
                        else "—"
                    }
                </td>

            </tr>
            """
        )

    high_score_share = _percentage(
        high_score_count,
        total,
    )

    return f"""
    <div data-score-container>

        <div class="stats-grid">

            <div class="stat-card">

                <span class="stat-label">
                    Fynd med score ≥ 80
                </span>

                <strong class="stat-value">
                    {fmt_number(
                        high_score_count
                    )}
                </strong>

                <span class="muted">
                    {high_score_share:.1f} %
                    av alla fyndevent
                </span>

            </div>

            <div class="stat-card">

                <span class="stat-label">
                    Fynd med score 90–100
                </span>

                <strong class="stat-value">
                    {
                        fmt_number(
                            next(
                                (
                                    int(
                                        row.get(
                                            "antal",
                                            0,
                                        )
                                        or 0
                                    )
                                    for row in rows
                                    if row.get(
                                        "scoreintervall"
                                    )
                                    == "90–100"
                                ),
                                0,
                            )
                        )
                    }
                </strong>

            </div>

            <div class="stat-card">

                <span class="stat-label">
                    Totalt analyserade event
                </span>

                <strong class="stat-value">
                    {fmt_number(total)}
                </strong>

            </div>

        </div>


        <h3>
            Utfall per scoreintervall
        </h3>

        <p class="muted">
            Här ser vi om högre score faktiskt
            sammanfaller med ett annat utfall.
            Procenten inom varje intervall räknas
            separat.
        </p>


        <div class="table-wrap">

            <table>

                <thead>

                    <tr>
                        <th>Score</th>
                        <th>Fyndevent</th>
                        <th>Andel</th>
                        <th>Utfall</th>
                    </tr>

                </thead>

                <tbody>

                    {"".join(output)}

                </tbody>

            </table>

        </div>

    </div>
    """
