"""
Rendering av fynd och prissänkningar.
"""

from __future__ import annotations

from typing import Any

from data_loader import (
    fmt_number,
    fmt_price,
    safe,
)


def render_findings(
    rows: list[dict[str, Any]],
) -> str:

    if not rows:
        return """
        <div class="empty">
            Inga aktuella fynd hittades.
        </div>
        """

    html_rows = []

    for row in rows:

        modell = (
            row.get("modell")
            or "Okänd bil"
        )

        variant = (
            row.get("variant")
            or ""
        )

        if variant:
            modell = (
                f"{modell} {variant}"
            )

        year = (
            row.get("arsmodell")
            or row.get("modell_ar")
            or "—"
        )

        mileage = (
            row.get("miltal")
            or row.get("mil")
            or "—"
        )

        price = (
            row.get("pris")
            or row.get("annonspris")
        )

        diff = (
            row.get("diff")
            or row.get("prisdiff")
        )

        score = row.get("score")

        url = (
            row.get("url")
            or row.get("annons_url")
        )

        if url:
            link = (
                f'<a href="{safe(url)}" '
                f'target="_blank" '
                f'rel="noopener">'
                f'Öppna annons</a>'
            )
        else:
            link = "—"

        html_rows.append(
            f"""
            <tr>
                <td>
                    <strong>
                        {safe(modell)}
                    </strong>
                </td>

                <td>
                    {safe(year)}
                </td>

                <td>
                    {fmt_number(mileage)}
                </td>

                <td>
                    {fmt_price(price)}
                </td>

                <td>
                    {fmt_price(diff)}
                </td>

                <td>
                    <span class="score">
                        {fmt_number(score)}
                    </span>
                </td>

                <td>
                    {link}
                </td>
            </tr>
            """
        )

    return f"""
    <div class="table-wrap">

        <table>

            <thead>
                <tr>
                    <th>Bil</th>
                    <th>Årsmodell</th>
                    <th>Miltal</th>
                    <th>Pris</th>
                    <th>Under marknad</th>
                    <th>Score</th>
                    <th>Annons</th>
                </tr>
            </thead>

            <tbody>
                {"".join(html_rows)}
            </tbody>

        </table>

    </div>
    """


def render_price_reductions(
    rows: list[dict[str, Any]],
) -> str:

    if not rows:
        return """
        <div class="empty">
            Inga observerade prissänkningar ännu.
        </div>
        """

    html_rows = []

    for row in rows[:100]:

        modell = (
            row.get("modell")
            or "Okänd bil"
        )

        variant = (
            row.get("variant")
            or ""
        )

        if variant:
            modell = (
                f"{modell} {variant}"
            )

        initial = row.get(
            "_display_initialpris"
        )

        latest = row.get(
            "_display_latestpris"
        )

        reduction = row.get(
            "_display_reduction"
        )

        percentage = row.get(
            "_display_percentage"
        )

        year = (
            row.get("arsmodell")
            or "—"
        )

        html_rows.append(
            f"""
            <tr>

                <td>
                    <strong>
                        {safe(modell)}
                    </strong>
                </td>

                <td>
                    {safe(year)}
                </td>

                <td>
                    {fmt_price(initial)}
                </td>

                <td>
                    {fmt_price(latest)}
                </td>

                <td>
                    <strong>
                        {fmt_price(reduction)}
                    </strong>
                </td>

                <td>
                    {fmt_number(
                        percentage,
                        1,
                    )} %
                </td>

            </tr>
            """
        )

    return f"""
    <div class="table-wrap">

        <table>

            <thead>
                <tr>
                    <th>Bil</th>
                    <th>År</th>
                    <th>Första pris</th>
                    <th>Senaste pris</th>
                    <th>Sänkning</th>
                    <th>%</th>
                </tr>
            </thead>

            <tbody>
                {"".join(html_rows)}
            </tbody>

        </table>

    </div>
    """
