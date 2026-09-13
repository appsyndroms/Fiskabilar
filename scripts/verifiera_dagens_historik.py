"""
Rendering av aktuella fynd.
"""
from __future__ import annotations

from typing import Any

from analysis import model_label_from_values


def _safe(
    value: Any,
) -> str:
    if value is None:
        return "—"

    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _fmt_number(
    value: Any,
    decimals: int = 0,
) -> str:
    if value is None:
        return "—"

    try:
        number = float(value)

        if decimals == 0:
            return (
                f"{number:,.0f}"
                .replace(",", " ")
            )

        return (
            f"{number:,.{decimals}f}"
            .replace(",", " ")
        )

    except (
        TypeError,
        ValueError,
    ):
        return _safe(value)


def _fmt_price(
    value: Any,
) -> str:
    if value is None:
        return "—"

    try:
        return (
            f"{float(value):,.0f} kr"
            .replace(",", " ")
        )

    except (
        TypeError,
        ValueError,
    ):
        return _safe(value)


def _get_ad_url(
    row: dict[str, Any],
) -> Any:
    """
    Hämtar annons-URL oavsett vilket av projektets URL-fältnamn
    som används i underlaget.
    """
    for key in (
        "url",
        "URL",
        "ad_url",
        "adUrl",
        "annons_url",
        "annonsUrl",
        "listing_url",
        "listingUrl",
    ):
        value = row.get(key)

        if value:
            return value

    return None


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
        model = (
            row.get("Model")
            or row.get("modell")
            or "Okänd bil"
        )

        variant = (
            row.get("Variant")
            or row.get("variant")
            or ""
        )

        year = (
            row.get("ModelYear")
            or row.get("arsmodell")
            or "—"
        )

        mileage = (
            row.get("Mil")
            or row.get("miltal")
            or "—"
        )

        price = row.get(
            "Price"
        )

        prediction = row.get(
            "Prediction"
        )

        model_gap = row.get(
            "ModelVsActualPct"
        )

        market_value = row.get(
            "ComparableWeightedMedian"
        )

        market_gap = row.get(
            "ComparableDeviationPct"
        )

        comparable_n = row.get(
            "ComparableN"
        )

        evidence = row.get(
            "EvidenceConfidence"
        )

        combined = row.get(
            "CombinedScore"
        )

        fynd_score = row.get(
            "FyndScore"
        )

        fyndklass = row.get(
            "Fyndklass"
        )

        identity = row.get(
            "Identity"
        )

        url = _get_ad_url(
            row
        )

        title = _safe(
            model_label_from_values(
                model,
                variant,
            )
        )

        if url:
            link = (
                f'<a href="{_safe(url)}" '
                f'target="_blank" '
                f'rel="noopener">'
                f'Öppna annons</a>'
            )
        else:
            link = "—"

        html_rows.append(
            f"""
            <tr
                data-current-finding
                data-filter-model="{_safe(model)}"
                data-filter-year="{_safe(year)}"
            >
                <td>
                    <strong>
                        {title}
                    </strong>
                </td>

                <td>
                    {_safe(year)}
                </td>

                <td>
                    {_fmt_number(mileage)}
                </td>

                <td>
                    {_fmt_price(price)}
                </td>

                <td>
                    {_fmt_price(prediction)}
                </td>

                <td>
                    {_fmt_number(
                        model_gap,
                        1,
                    )} %
                </td>

                <td>
                    {_fmt_price(
                        market_value
                    )}
                </td>

                <td>
                    {_fmt_number(
                        market_gap,
                        1,
                    )} %
                </td>

                <td>
                    {_fmt_number(
                        comparable_n
                    )}
                </td>

                <td>
                    {_fmt_number(
                        evidence,
                        2,
                    )}
                </td>

                <td>
                    {_fmt_number(
                        combined,
                        1,
                    )}
                </td>

                <td>
                    <strong>
                        {_fmt_number(
                            fynd_score,
                            1,
                        )}
                    </strong>
                </td>

                <td>
                    {_safe(fyndklass)}
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
                    <th>År</th>
                    <th>Miltal</th>
                    <th>Pris</th>
                    <th>ML-värdering</th>
                    <th>ML-gap</th>
                    <th>Marknadsvärde</th>
                    <th>Marknadsgap</th>
                    <th>Jämförelser</th>
                    <th>Evidens</th>
                    <th>Combined</th>
                    <th>FyndScore</th>
                    <th>Klass</th>
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
        model = (
            row.get("Model")
            or row.get("modell")
            or "Okänd bil"
        )

        year = (
            row.get("ModelYear")
            or row.get("arsmodell")
            or "—"
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

        html_rows.append(
            f"""
            <tr
                data-price-reduction
                data-filter-model="{_safe(model)}"
                data-filter-year="{_safe(year)}"
            >
                <td>
                    <strong>
                        {_safe(model)}
                    </strong>
                </td>

                <td>
                    {_safe(year)}
                </td>

                <td>
                    {_fmt_price(initial)}
                </td>

                <td>
                    {_fmt_price(latest)}
                </td>

                <td>
                    <strong>
                        {_fmt_price(reduction)}
                    </strong>
                </td>

                <td>
                    {_fmt_number(
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
