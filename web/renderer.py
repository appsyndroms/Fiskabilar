"""
HTML-rendering för Fiskabilar Analytics.

Den här filen fungerar som ett tunt API-lager.
Den faktiska renderingen ligger i web/renderers/.
"""

from renderers import (
    build_html,
    render_findings,
    render_market_history,
    render_ml,
    render_outcomes,
    render_price_reductions,
    render_score_analysis,
)

__all__ = [
    "build_html",
    "render_findings",
    "render_price_reductions",
    "render_outcomes",
    "render_score_analysis",
    "render_market_history",
    "render_ml",
]
