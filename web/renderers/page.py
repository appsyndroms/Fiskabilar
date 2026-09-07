"""
Huvudlayout för Fiskabilars statiska webbplats.
"""
from __future__ import annotations
from typing import Any
from data_loader import safe
from .findings import (
    render_findings,
    render_price_reductions,
)
from .global_filter import (
    render_global_filter,
)
from .history import (
    render_market_history,
)
from .ml import (
    render_ml,
)
from .outcomes import (
    render_outcomes,
    render_score_analysis,
)
from .styles import (
    render_styles,
    render_global_filter_styles,
)
def build_html(
    payload: dict[str, Any],
) -> str:
    summary = payload[
        "summary"
    ]
    current_findings = payload[
        "current_findings"
    ]
    reductions = payload[
        "price_reductions"
    ]
    outcomes = payload[
        "find_outcomes"
    ]
    score = payload[
        "score_analysis"
    ]
    history_table = payload[
        "history_table"
    ]
    history_series = payload[
        "history_series"
    ]
    ml = payload[
        "ml"
    ]
    generated_at = payload[
        "generated_at"
    ]
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
{render_styles()}
{render_global_filter_styles()}
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
        <a href="#global-filter">
            🔎 Filter
        </a>
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
        <a href="#historik">
            🕒 Marknadshistorik
        </a>
        <a href="#utfall">
            📊 Fyndutfall
        </a>
        <a href="#score-utfall">
            ⭐ Score mot faktiskt utfall
        </a>
        <a href="#ml">
            🤖 ML statistik
        </a>
    </div>
</nav>
<main>
{render_global_filter()}
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
<section id="score-utfall">
    <h2>
        ⭐ Score mot faktiskt utfall
    </h2>
    <div class="card">
        {render_score_analysis(
            score
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
