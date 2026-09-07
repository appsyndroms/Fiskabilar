"""
CSS för Fiskabilars statiska webbplats.
"""

from __future__ import annotations


def render_styles() -> str:
    """
    Returnerar all gemensam CSS för den statiska sidan.
    """

    return """
    <style>

    :root {
        --bg: #0b1020;
        --surface: #121a2b;
        --surface2: #182238;
        --border: #2b3854;
        --text: #edf2f7;
        --muted: #9aa9bf;
        --accent: #72a7ff;
        --positive: #68d391;
        --warning: #ecc94b;
        --negative: #fc8181;
    }

    * {
        box-sizing: border-box;
    }

    html {
        scroll-behavior: smooth;
    }

    body {
        margin: 0;
        background: var(--bg);
        color: var(--text);
        font-family:
            -apple-system,
            BlinkMacSystemFont,
            "Segoe UI",
            sans-serif;
        line-height: 1.5;
    }

    header {
        background: var(--surface);
        border-bottom: 1px solid var(--border);
    }

    .header-inner,
    .nav-inner,
    main,
    footer {
        width: min(1200px, calc(100% - 32px));
        margin: 0 auto;
    }

    .header-inner {
        padding: 34px 0 28px;
    }

    h1,
    h2,
    h3 {
        line-height: 1.2;
    }

    h1 {
        margin: 0 0 8px;
        font-size: clamp(1.8rem, 4vw, 2.6rem);
    }

    h2 {
        margin: 42px 0 16px;
        font-size: 1.45rem;
    }

    h3 {
        margin: 0 0 12px;
    }

    .subtitle {
        color: var(--muted);
        margin-top: 4px;
    }

    nav {
        position: sticky;
        top: 0;
        z-index: 20;
        background: rgba(11, 16, 32, .94);
        border-bottom: 1px solid var(--border);
        backdrop-filter: blur(10px);
    }

    .nav-inner {
        display: flex;
        gap: 6px;
        overflow-x: auto;
        padding: 8px 0;
    }

    nav a {
        color: var(--muted);
        text-decoration: none;
        white-space: nowrap;
        padding: 8px 10px;
        border-radius: 8px;
    }

    nav a:hover {
        color: var(--text);
        background: var(--surface2);
    }

    main {
        padding-bottom: 50px;
    }

    section {
        scroll-margin-top: 70px;
    }

    .card {
        background: var(--surface);
        border: 1px solid var(--border);
        border-radius: 14px;
        overflow: hidden;
    }

    .kpis {
        display: grid;
        grid-template-columns:
            repeat(
                5,
                minmax(0, 1fr)
            );
        gap: 12px;
    }

    .kpi {
        background: var(--surface);
        border: 1px solid var(--border);
        border-radius: 12px;
        padding: 16px;
    }

    .kpi span {
        display: block;
        color: var(--muted);
        font-size: .85rem;
        margin-bottom: 7px;
    }

    .kpi strong {
        display: block;
        font-size: 1.65rem;
    }

    table {
        width: 100%;
        border-collapse: collapse;
    }

    th,
    td {
        padding: 11px 13px;
        border-bottom: 1px solid var(--border);
        text-align: left;
        vertical-align: top;
    }

    th {
        color: var(--muted);
        font-size: .82rem;
        font-weight: 600;
        background: var(--surface2);
    }

    tr:last-child td {
        border-bottom: 0;
    }

    a {
        color: var(--accent);
    }

    .empty {
        padding: 24px;
        color: var(--muted);
    }

    .market-chart {
        width: 100%;
        height: auto;
        min-height: 260px;
        display: block;
    }

    .chart-title {
        fill: var(--text);
        font-size: 18px;
        font-weight: 700;
    }

    .axis {
        fill: var(--muted);
        font-size: 12px;
    }

    .gridline {
        stroke: var(--border);
        stroke-width: 1;
    }

    .legend-label {
        fill: var(--text);
        font-size: 12px;
    }

    .chart-card {
        padding: 16px;
        border-bottom: 1px solid var(--border);
    }

    .chart-card:last-child {
        border-bottom: 0;
    }

    .score-row,
    .outcome-row {
        padding: 12px 16px;
        border-bottom: 1px solid var(--border);
    }

    .score-row:last-child,
    .outcome-row:last-child {
        border-bottom: 0;
    }

    .score-bar,
    .outcome-bar {
        height: 10px;
        margin-top: 7px;
        border-radius: 999px;
        background: var(--surface2);
        overflow: hidden;
    }

    .score-bar > span,
    .outcome-bar > span {
        display: block;
        height: 100%;
        background: var(--accent);
        border-radius: inherit;
    }

    .ml-grid {
        display: grid;
        grid-template-columns:
            repeat(
                4,
                minmax(0, 1fr)
            );
        gap: 12px;
        padding: 16px;
    }

    .ml-stat {
        background: var(--surface2);
        border: 1px solid var(--border);
        border-radius: 10px;
        padding: 13px;
    }

    .ml-stat span {
        display: block;
        color: var(--muted);
        font-size: .82rem;
    }

    .ml-stat strong {
        display: block;
        margin-top: 4px;
        font-size: 1.2rem;
    }

    /*
     * Globalt filter.
     *
     * Vi ger både sektionen och själva kortet
     * explicit topputrymme så att filterrutan
     * inte upplevs ligga direkt mot innehållet
     * ovanför och så att rubriken inte ligger
     * kloss mot kortets överkant.
     */

    #global-filter {
        padding-top: 20px;
    }

    .global-filter-card {
        background: var(--surface);
        border: 1px solid var(--border);
        border-radius: 14px;
        padding: 24px 20px 20px;
    }

    .global-filter-header {
        display: flex;
        justify-content: space-between;
        align-items: flex-start;
        gap: 20px;
        margin-bottom: 18px;
    }

    .global-filter-header h2 {
        margin: 0 0 6px;
    }

    .global-filter-grid {
        display: grid;
        grid-template-columns:
            repeat(
                3,
                minmax(180px, 1fr)
            );
        gap: 14px;
    }

    .global-filter-grid label {
        display: flex;
        flex-direction: column;
        gap: 7px;
    }

    .global-filter-grid label span {
        color: var(--muted);
        font-size: .85rem;
        font-weight: 600;
    }

    .global-filter-grid select {
        width: 100%;
        padding: 11px 12px;
        border-radius: 9px;
        border: 1px solid var(--border);
        background: var(--surface2);
        color: var(--text);
        font-size: 1rem;
    }

    #global-filter-reset {
        border: 1px solid var(--border);
        background: var(--surface2);
        color: var(--text);
        border-radius: 9px;
        padding: 10px 14px;
        cursor: pointer;
        white-space: nowrap;
    }

    #global-filter-reset:hover {
        background: var(--border);
    }

    .global-filter-status {
        margin-top: 14px;
        color: var(--muted);
        font-size: .9rem;
        min-height: 20px;
    }

    .ml-filter-status {
        color: var(--muted);
        font-size: .9rem;
        margin-bottom: 14px;
    }

    [hidden] {
        display: none !important;
    }

    footer {
        color: var(--muted);
        border-top: 1px solid var(--border);
        padding: 24px 0 40px;
        font-size: .85rem;
    }

    @media (max-width: 900px) {

        .kpis {
            grid-template-columns:
                repeat(
                    2,
                    minmax(0, 1fr)
                );
        }

        .ml-grid {
            grid-template-columns:
                repeat(
                    2,
                    minmax(0, 1fr)
                );
        }

    }

    @media (max-width: 700px) {

        .header-inner,
        .nav-inner,
        main,
        footer {
            width: min(
                100% - 20px,
                1200px
            );
        }

        .global-filter-header {
            display: block;
        }

        #global-filter-reset {
            margin-top: 12px;
        }

        .global-filter-grid {
            grid-template-columns: 1fr;
        }

        .kpis,
        .ml-grid {
            grid-template-columns: 1fr;
        }

        .card {
            overflow-x: auto;
        }

        table {
            min-width: 650px;
        }

    }

    </style>
    """


def render_global_filter_styles() -> str:
    """
    Bakåtkompatibelt API.

    Den globala filterstylingen ligger numera i render_styles().
    page.py behöver därför fortfarande kunna importera denna funktion.
    """

    return ""
