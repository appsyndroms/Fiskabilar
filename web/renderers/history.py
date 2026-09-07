"""
Rendering av marknadshistorik.
"""

from __future__ import annotations

from typing import Any

from charts import market_chart
from data_loader import (
    fmt_number,
    fmt_price,
    safe,
)


def render_market_history(
    table: list[dict[str, Any]],
    series: dict[
        str,
        dict[
            str,
            list[
                dict[str, Any]
            ],
        ],
    ],
) -> str:

    if not table:
        return """
        <div class="empty">
            Ingen marknadshistorik hittades.
        </div>
        """

    rows = []

    for row in table:

        rows.append(
            f"""
            <tr>

                <td>
                    <strong>
                        {safe(
                            row["modell"]
                        )}
                    </strong>
                </td>

                <td>
                    {row["arsmodell"]}
                </td>

                <td>
                    {fmt_number(
                        row["antal"]
                    )}
                </td>

                <td>
                    {fmt_price(
                        row["medianpris"]
                    )}
                </td>

                <td>
                    {fmt_price(
                        row["snittpris"]
                    )}
                </td>

                <td>
                    {fmt_number(
                        row["medianmiltal"]
                    )}
                </td>

            </tr>
            """
        )

    charts = []

    for model, years in sorted(
        series.items()
    ):

        charts.append(
            f"""
            <div class="chart-card">

                {market_chart(
                    model,
                    years,
                )}

            </div>
            """
        )

    return f"""
    <h3>
        Marknadsöversikt
    </h3>

    <p class="muted">
        Varje diagram visar en modell.
        Varje linje representerar en årsmodell.
        Priset är daglig median av observerade annonser.
    </p>

    <div class="table-wrap">

        <table>

            <thead>
                <tr>
                    <th>Modell</th>
                    <th>År</th>
                    <th>Observationer</th>
                    <th>Medianpris</th>
                    <th>Snittpris</th>
                    <th>Medianmiltal</th>
                </tr>
            </thead>

            <tbody>
                {"".join(rows)}
            </tbody>

        </table>

    </div>

    <h3>
        Pris över tid
    </h3>

    <div class="charts">
        {"".join(charts)}
    </div>
    """
