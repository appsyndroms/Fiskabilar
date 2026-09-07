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

        model = row[
            "modell"
        ]

        year = row[
            "arsmodell"
        ]

        rows.append(
            f"""
            <tr
                data-history-row
                data-filter-model="{safe(model)}"
                data-filter-year="{safe(year)}"
            >

                <td>
                    <strong>
                        {safe(model)}
                    </strong>
                </td>

                <td>
                    {safe(year)}
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

        year_names = ",".join(
            str(year)
            for year in sorted(
                years.keys()
            )
        )


        charts.append(
            f"""
            <div
                class="chart-card"
                data-chart-model="{safe(model)}"
                data-chart-years="{safe(year_names)}"
            >

                {market_chart(
                    model,
                    years,
                )}

            </div>
            """
        )


    return f"""

    <h3>
        Pris över tid
    </h3>

    <p class="muted">
        Varje diagram visar en modell.
        Varje linje representerar en årsmodell.
        Priset är daglig median av observerade annonser.
    </p>

    <div class="charts">

        {"".join(charts)}

    </div>


    <details class="market-overview">

        <summary>
            Marknadsöversikt
        </summary>

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

    </details>

    """
