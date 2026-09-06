"""
HTML-rendering för Fiskabilar Analytics.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from data_loader import (
    fmt_number,
    fmt_price,
    safe,
)

from charts import market_chart


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
            row.get(
                "arsmodell"
            )
            or row.get(
                "modell_ar"
            )
            or "—"
        )

        mileage = (
            row.get("miltal")
            or row.get("mil")
            or "—"
        )

        price = (
            row.get("pris")
            or row.get(
                "annonspris"
            )
        )

        diff = (
            row.get("diff")
            or row.get(
                "prisdiff"
            )
        )

        score = row.get(
            "score"
        )

        url = (
            row.get("url")
            or row.get(
                "annons_url"
            )
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
            row.get(
                "arsmodell"
            )
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
            <div class="bar-row">

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

    return "".join(
        bars
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

    return "".join(
        output
    )


def render_market_history(
    table: list[
        dict[str, Any]
    ],
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


def render_ml(
    ml: dict[str, Any],
) -> str:

    metadata = ml.get(
        "metadata",
        {},
    )

    if not metadata:
        return """
        <div class="empty">
            Ingen tränad ML-modell hittades ännu.
        </div>
        """

    model_key = str(
        metadata.get(
            "modell",
            "",
        )
    )

    model_names = {
        "random_forest":
            "Random Forest",

        "linear_regression":
            "Linear Regression",
    }

    model_name = model_names.get(
        model_key,
        model_key or "Okänd",
    )

    observations = (
        metadata.get(
            "antal_observationer",
            0,
        )
    )

    training = (
        metadata.get(
            "antal_traning",
            0,
        )
    )

    test = (
        metadata.get(
            "antal_test",
            0,
        )
    )

    created = (
        metadata.get(
            "skapad",
            "—",
        )
    )

    features = metadata.get(
        "features",
        [],
    )

    metrics = metadata.get(
        "metrics",
        {},
    )

    active_metrics = {}

    if isinstance(
        metrics,
        dict,
    ):

        model_metrics = (
            metrics.get(
                model_key,
                {},
            )
        )

        if isinstance(
            model_metrics,
            dict,
        ):
            active_metrics = (
                model_metrics.get(
                    "totalt",
                    {},
                )
            )

    r2 = active_metrics.get(
        "r2"
    )

    mae = active_metrics.get(
        "mae"
    )

    rmse = active_metrics.get(
        "rmse"
    )

    mape = active_metrics.get(
        "mape_procent"
    )

    training_number = (
        float(training or 0)
    )

    test_number = (
        float(test or 0)
    )

    total = (
        training_number
        + test_number
    )

    progress = (
        training_number
        / total
        * 100
        if total
        else 0
    )

    features_text = (
        ", ".join(
            str(feature)
            for feature
            in features
        )
        if isinstance(
            features,
            list,
        )
        else str(features)
    )

    comparison = []

    for key in (
        "linear_regression",
        "random_forest",
    ):

        data = {}

        if isinstance(
            metrics,
            dict,
        ):

            model_data = (
                metrics.get(
                    key,
                    {},
                )
            )

            if isinstance(
                model_data,
                dict,
            ):
                data = (
                    model_data.get(
                        "totalt",
                        {},
                    )
                )

        comparison.append(
            f"""
            <tr>

                <td>
                    <strong>
                        {safe(
                            model_names.get(
                                key,
                                key,
                            )
                        )}

                        {
                            " ⭐"
                            if key == model_key
                            else ""
                        }
                    </strong>
                </td>

                <td>
                    {fmt_number(
                        data.get("r2"),
                        3,
                    )}
                </td>

                <td>
                    {fmt_price(
                        data.get("mae")
                    )}
                </td>

                <td>
                    {fmt_price(
                        data.get("rmse")
                    )}
                </td>

                <td>
                    {fmt_number(
                        data.get(
                            "mape_procent"
                        ),
                        2,
                    )} %
                </td>

            </tr>
            """
        )

    return f"""
    <div class="ml-grid">

        <div class="ml-card">
            <span>
                Aktiv modell
            </span>

            <strong>
                {safe(model_name)}
            </strong>
        </div>

        <div class="ml-card">
            <span>
                Observationer
            </span>

            <strong>
                {fmt_number(
                    observations
                )}
            </strong>
        </div>

        <div class="ml-card">
            <span>
                R²
            </span>

            <strong>
                {fmt_number(
                    r2,
                    3,
                )}
            </strong>
        </div>

        <div class="ml-card">
            <span>
                MAE
            </span>

            <strong>
                {fmt_price(mae)}
            </strong>
        </div>

        <div class="ml-card">
            <span>
                RMSE
            </span>

            <strong>
                {fmt_price(rmse)}
            </strong>
        </div>

        <div class="ml-card">
            <span>
                MAPE
            </span>

            <strong>
                {fmt_number(
                    mape,
                    2,
                )} %
            </strong>
        </div>

    </div>

    <div class="progress-card">

        <div class="progress-header">

            <strong>
                ML-progress
            </strong>

            <span>
                {fmt_number(training)}
                träningsrader /
                {fmt_number(total)} totalt
            </span>

        </div>

        <div class="progress">

            <div
                style="width:{progress:.1f}%"
            ></div>

        </div>

        <div class="progress-meta">

            <span>
                Träning:
                {fmt_number(training)}
            </span>

            <span>
                Test:
                {fmt_number(test)}
            </span>

        </div>

    </div>

    <div class="ml-info">

        <p>
            <strong>
                Senast tränad:
            </strong>

            {safe(created)}
        </p>

        <p>
            <strong>
                Features:
            </strong>

            {safe(features_text)}
        </p>

    </div>

    <h3>
        Modelljämförelse
    </h3>

    <div class="table-wrap">

        <table>

            <thead>
                <tr>
                    <th>Modell</th>
                    <th>R²</th>
                    <th>MAE</th>
                    <th>RMSE</th>
                    <th>MAPE</th>
                </tr>
            </thead>

            <tbody>
                {"".join(comparison)}
            </tbody>

        </table>

    </div>
    """


def build_html(
    payload: dict[str, Any],
) -> str:

    summary = payload[
        "summary"
    ]

    current_findings = (
        payload[
            "current_findings"
        ]
    )

    reductions = (
        payload[
            "price_reductions"
        ]
    )

    outcomes = (
        payload[
            "find_outcomes"
        ]
    )

    score = (
        payload[
            "score_analysis"
        ]
    )

    history_table = (
        payload[
            "history_table"
        ]
    )

    history_series = (
        payload[
            "history_series"
        ]
    )

    ml = payload[
        "ml"
    ]

    generated_at = (
        payload[
            "generated_at"
        ]
    )

    return f"""<!DOCTYPE html>

<html lang="sv">

<head>

<meta charset="utf-8">

<meta
    name="viewport"
    content="width=device-width, initial-scale=1"
>

<title>
    Fiskabilar Analytics
</title>

<style>

:root {{

    color-scheme: dark;

    --bg: #0b0f14;
    --surface: #121820;
    --surface2: #18212b;
    --border: #293440;
    --text: #edf2f7;
    --muted: #9aa8b5;
    --accent: #72a7ff;
    --green: #68d391;

}}

* {{
    box-sizing: border-box;
}}

html {{
    scroll-behavior: smooth;
}}

body {{

    margin: 0;

    background:
        var(--bg);

    color:
        var(--text);

    font-family:
        -apple-system,
        BlinkMacSystemFont,
        "Segoe UI",
        sans-serif;

}}

a {{
    color:
        var(--accent);

    text-decoration:
        none;
}}

a:hover {{
    text-decoration:
        underline;
}}

header {{

    padding:
        36px 24px 28px;

    border-bottom:
        1px solid var(--border);

    background:
        var(--surface);

}}

.header-inner {{

    max-width:
        1500px;

    margin:
        auto;

}}

h1 {{

    margin:
        0;

    font-size:
        2.2rem;

}}

.subtitle {{

    color:
        var(--muted);

    margin-top:
        8px;

}}

nav {{

    position:
        sticky;

    top:
        0;

    z-index:
        10;

    background:
        rgba(11,15,20,.94);

    backdrop-filter:
        blur(10px);

    border-bottom:
        1px solid var(--border);

}}

.nav-inner {{

    max-width:
        1500px;

    margin:
        auto;

    display:
        flex;

    gap:
        8px;

    overflow-x:
        auto;

    padding:
        10px 16px;

}}

nav a {{

    white-space:
        nowrap;

    padding:
        8px 12px;

    border-radius:
        8px;

}}

nav a:hover {{

    background:
        var(--surface2);

    text-decoration:
        none;

}}

main {{

    max-width:
        1500px;

    margin:
        auto;

    padding:
        28px 20px 80px;

}}

section {{

    margin-bottom:
        46px;

    scroll-margin-top:
        70px;

}}

h2 {{

    margin:
        0 0 18px;

    font-size:
        1.5rem;

}}

h3 {{
    margin-top:
        30px;
}}

.kpis {{

    display:
        grid;

    grid-template-columns:
        repeat(
            auto-fit,
            minmax(190px, 1fr)
        );

    gap:
        14px;

    margin-top:
        24px;

}}

.kpi {{

    background:
        var(--surface);

    border:
        1px solid var(--border);

    border-radius:
        14px;

    padding:
        18px;

}}

.kpi span {{

    color:
        var(--muted);

    font-size:
        .9rem;

}}

.kpi strong {{

    display:
        block;

    font-size:
        1.8rem;

    margin-top:
        6px;

}}

.card {{

    background:
        var(--surface);

    border:
        1px solid var(--border);

    border-radius:
        14px;

    padding:
        20px;

}}

.table-wrap {{

    overflow-x:
        auto;

    border:
        1px solid var(--border);

    border-radius:
        12px;

}}

table {{

    width:
        100%;

    border-collapse:
        collapse;

    min-width:
        760px;

}}

th,
td {{

    padding:
        12px 14px;

    text-align:
        left;

    border-bottom:
        1px solid var(--border);

}}

th {{

    color:
        var(--muted);

    font-size:
        .85rem;

    font-weight:
        600;

}}

tr:last-child td {{
    border-bottom:
        0;
}}

.score {{

    display:
        inline-block;

    min-width:
        40px;

    text-align:
        center;

    padding:
        4px 8px;

    border-radius:
        8px;

    background:
        var(--surface2);

    font-weight:
        700;

}}

.empty {{

    color:
        var(--muted);

    padding:
        20px 0;

}}

.muted {{
    color:
        var(--muted);
}}

.bar-row {{
    margin-bottom:
        18px;
}}

.bar-label {{

    display:
        flex;

    justify-content:
        space-between;

    margin-bottom:
        7px;

}}

.bar {{

    height:
        10px;

    background:
        var(--surface2);

    border-radius:
        999px;

    overflow:
        hidden;

}}

.bar > div {{

    height:
        100%;

    background:
        var(--accent);

    border-radius:
        inherit;

}}

.score-row {{

    display:
        flex;

    justify-content:
        space-between;

    gap:
        20px;

    padding:
        14px 0;

    border-bottom:
        1px solid var(--border);

}}

.score-row:last-child {{
    border-bottom:
        0;
}}

.score-row span {{

    color:
        var(--muted);

    margin-left:
        12px;

}}

.charts {{

    display:
        grid;

    grid-template-columns:
        repeat(
            auto-fit,
            minmax(520px, 1fr)
        );

    gap:
        16px;

    margin-top:
        20px;

}}

.chart-card {{

    background:
        var(--surface2);

    border:
        1px solid var(--border);

    border-radius:
        14px;

    padding:
        12px;

    overflow:
        hidden;

}}

.market-chart {{

    width:
        100%;

    height:
        auto;

    display:
        block;

}}

.gridline {{

    stroke:
        var(--border);

    stroke-width:
        1;

}}

.axis {{

    fill:
        var(--muted);

    font-size:
        11px;

}}

.chart-title {{

    fill:
        var(--text);

    font-size:
        16px;

    font-weight:
        700;

}}

.legend-label {{

    fill:
        var(--text);

    font-size:
        12px;

    font-weight:
        600;

}}

.ml-grid {{

    display:
        grid;

    grid-template-columns:
        repeat(
            auto-fit,
            minmax(180px, 1fr)
        );

    gap:
        14px;

}}

.ml-card {{

    background:
        var(--surface2);

    border:
        1px solid var(--border);

    border-radius:
        12px;

    padding:
        16px;

}}

.ml-card span {{

    display:
        block;

    color:
        var(--muted);

    font-size:
        .85rem;

}}

.ml-card strong {{

    display:
        block;

    margin-top:
        5px;

    font-size:
        1.35rem;

}}

.progress-card {{

    margin-top:
        20px;

    background:
        var(--surface);

    border:
        1px solid var(--border);

    border-radius:
        12px;

    padding:
        18px;

}}

.progress-header,
.progress-meta {{

    display:
        flex;

    justify-content:
        space-between;

    gap:
        20px;

}}

.progress-header span,
.progress-meta {{

    color:
        var(--muted);

    font-size:
        .9rem;

}}

.progress {{

    height:
        12px;

    margin:
        14px 0;

    background:
        var(--surface2);

    border-radius:
        999px;

    overflow:
        hidden;

}}

.progress > div {{

    height:
        100%;

    background:
        var(--green);

}}

.ml-info {{

    margin-top:
        18px;

    color:
        var(--muted);

}}

footer {{

    max-width:
        1500px;

    margin:
        auto;

    padding:
        0 20px 40px;

    color:
        var(--muted);

    font-size:
        .85rem;

}}

@media (max-width: 700px) {{

    header {{
        padding:
            26px 18px;
    }}

    h1 {{
        font-size:
            1.8rem;
    }}

    main {{
        padding:
            22px 14px 60px;
    }}

    .charts {{
        grid-template-columns:
            1fr;
    }}

    .score-row {{
        display:
            block;
    }}

    .score-row > div:last-child {{
        margin-top:
            8px;
    }}

    .progress-header,
    .progress-meta {{
        display:
            block;
    }}

}}

</style>

</head>

<body>

<header>

    <div class="header-inner">

        <h1>
            🚗 Fiskabilar Analytics
        </h1>

        <div class="subtitle">
            Marknadsdata, fynd, utfall och ML
        </div>

        <div class="subtitle">
            Senast byggd:
            {safe(generated_at)}
        </div>

    </div>

</header>

<nav>

    <div class="nav-inner">

        <a href="#oversikt">
            Översikt
        </a>

        <a href="#fynd">
            🚗 Aktuella fynd
        </a>

        <a href="#score">
            ⭐ Score
        </a>

        <a href="#sankningar">
            📉 Prissänkningar
        </a>

        <a href="#utfall">
            📊 Fyndutfall
        </a>

        <a href="#historik">
            🕒 Marknadshistorik
        </a>

        <a href="#ml">
            🤖 ML statistik
        </a>

    </div>

</nav>

<main>

<section id="oversikt">

    <h2>
        Översikt
    </h2>

    <div class="kpis">

        <div class="kpi">

            <span>
                Aktuella fynd
            </span>

            <strong>
                {summary["current_findings"]}
            </strong>

        </div>

        <div class="kpi">

            <span>
                Fynd-event
            </span>

            <strong>
                {summary["find_events"]}
            </strong>

        </div>

        <div class="kpi">

            <span>
                Prissänkningar
            </span>

            <strong>
                {summary["price_reductions"]}
            </strong>

        </div>

        <div class="kpi">

            <span>
                Marknadsobservationer
            </span>

            <strong>
                {summary["market_observations"]}
            </strong>

        </div>

        <div class="kpi">

            <span>
                Modell/årsmodell
            </span>

            <strong>
                {summary["model_year_groups"]}
            </strong>

        </div>

    </div>

</section>


<section id="fynd">

    <h2>
        🚗 Aktuella fynd
    </h2>

    <div class="card">

        {render_findings(
            current_findings
        )}

    </div>

</section>


<section id="score">

    <h2>
        ⭐ Score mot faktiskt utfall
    </h2>

    <div class="card">

        {render_score_analysis(
            score
        )}

    </div>

</section>


<section id="sankningar">

    <h2>
        📉 Prissänkningar
    </h2>

    <div class="card">

        {render_price_reductions(
            reductions
        )}

    </div>

</section>


<section id="utfall">

    <h2>
        📊 Fyndutfall
    </h2>

    <div class="card">

        {render_outcomes(
            outcomes
        )}

    </div>

</section>


<section id="historik">

    <h2>
        🕒 Marknadshistorik
    </h2>

    <div class="card">

        {render_market_history(
            history_table,
            history_series,
        )}

    </div>

</section>


<section id="ml">

    <h2>
        🤖 ML statistik
    </h2>

    <div class="card">

        {render_ml(
            ml
        )}

    </div>

</section>

</main>

<footer>

    Fiskabilar Analytics ·
    Statisk vy byggd automatiskt från data/

</footer>

</body>

</html>
"""
