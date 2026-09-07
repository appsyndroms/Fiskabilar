"""
Rendering av fyndutfall och score.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from data_loader import safe


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
        )
        for row in rows
    )

    total = sum(
        counts.values()
    )

    bars = []

    for outcome, count in (
        counts.most_common()
    ):

        share = (
            count
            / total
            * 100
            if total
            else 0
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
                        {count}
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

    return (
        '<div data-outcomes-container>'
        + "".join(bars)
        + "</div>"
    )


def render_score_analysis(
    rows: list[dict[str, Any]],
) -> str:

    if not rows:
        return """
        <div class="empty">
            Inte tillräckligt med data ännu.
        </div>
        """

    output = []

    for row in rows:

        bucket = row[
            "scoreintervall"
        ]

        count = row[
            "antal"
        ]

        outcomes = row[
            "utfall"
        ]

        parts = [

            (
                f"{safe(name)}: "
                f"{value}"
            )

            for name, value
            in sorted(
                outcomes.items()
            )

        ]

        output.append(
            f"""
            <div class="score-row">

                <div>

                    <strong>
                        {safe(bucket)}
                    </strong>

                    <span>
                        {count} event
                    </span>

                </div>

                <div>
                    {
                        " · ".join(parts)
                        if parts
                        else "—"
                    }
                </div>

            </div>
            """
        )

    return (
        '<div data-score-container>'
        + "".join(output)
        + "</div>"
    )
