"""
CSS för Fiskabilars statiska webbplats.
"""


def render_styles() -> str:

    return """
<style>

:root {
    color-scheme: dark;

    --bg: #0b0f14;
    --surface: #121820;
    --surface2: #18212b;
    --border: #293440;
    --text: #edf2f7;
    --muted: #9aa8b5;
    --accent: #72a7ff;
    --green: #68d391;
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
}

a {
    color: var(--accent);
    text-decoration: none;
}

a:hover {
    text-decoration: underline;
}

header {
    padding: 36px 24px 28px;
    border-bottom: 1px solid var(--border);
    background: var(--surface);
}

.header-inner {
    max-width: 1500px;
    margin: auto;
}

h1 {
    margin: 0;
    font-size: 2.2rem;
}

.subtitle {
    color: var(--muted);
    margin-top: 8px;
}

nav {
    position: sticky;
    top: 0;
    z-index: 10;
    background: rgba(11, 15, 20, .94);
    backdrop-filter: blur(10px);
    border-bottom: 1px solid var(--border);
}

.nav-inner {
    max-width: 1500px;
    margin: auto;
    display: flex;
    gap: 8px;
    overflow-x: auto;
    padding: 10px 16px;
}

nav a {
    white-space: nowrap;
    padding: 8px 12px;
    border-radius: 8px;
}

nav a:hover {
    background: var(--surface2);
    text-decoration: none;
}

main {
    max-width: 1500px;
    margin: auto;
    padding: 28px 20px 80px;
}

section {
    margin-bottom: 46px;
    scroll-margin-top: 70px;
}

h2 {
    margin: 0 0 18px;
    font-size: 1.5rem;
}

h3 {
    margin-top: 30px;
}

.kpis {
    display: grid;
    grid-template-columns:
        repeat(
            auto-fit,
            minmax(190px, 1fr)
        );
    gap: 14px;
    margin-top: 24px;
}

.kpi {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 14px;
    padding: 18px;
}

.kpi span {
    color: var(--muted);
    font-size: .9rem;
}

.kpi strong {
    display: block;
    font-size: 1.8rem;
    margin-top: 6px;
}

.card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 14px;
    padding: 20px;
}

.table-wrap {
    overflow-x: auto;
    border: 1px solid var(--border);
    border-radius: 12px;
}

table {
    width: 100%;
    border-collapse: collapse;
    min-width: 760px;
}

th,
td {
    padding: 12px 14px;
    text-align: left;
    border-bottom: 1px solid var(--border);
}

th {
    color: var(--muted);
    font-size: .85rem;
    font-weight: 600;
}

tr:last-child td {
    border-bottom: 0;
}

.score {
    display: inline-block;
    min-width: 40px;
    text-align: center;
    padding: 4px 8px;
    border-radius: 8px;
    background: var(--surface2);
    font-weight: 700;
}

.empty {
    color: var(--muted);
    padding: 20px 0;
}

.muted {
    color: var(--muted);
}

.bar-row {
    margin-bottom: 18px;
}

.bar-label {
    display: flex;
    justify-content: space-between;
    margin-bottom: 7px;
}

.bar {
    height: 10px;
    background: var(--surface2);
    border-radius: 999px;
    overflow: hidden;
}

.bar > div {
    height: 100%;
    background: var(--accent);
    border-radius: inherit;
}

.score-row {
    display: flex;
    justify-content: space-between;
    gap: 20px;
    padding: 14px 0;
    border-bottom: 1px solid var(--border);
}

.score-row:last-child {
    border-bottom: 0;
}

.score-row span {
    color: var(--muted);
    margin-left: 12px;
}

.charts {
    display: grid;
    grid-template-columns:
        repeat(
            auto-fit,
            minmax(520px, 1fr)
        );
    gap: 16px;
    margin-top: 20px;
}

.chart-card {
    background: var(--surface2);
    border: 1px solid var(--border);
    border-radius: 14px;
    padding: 12px;
    overflow: hidden;
}

.market-chart {
    width: 100%;
    height: auto;
    display: block;
}

.gridline {
    stroke: var(--border);
    stroke-width: 1;
}

.axis {
    fill: var(--muted);
    font-size: 11px;
}

.chart-title {
    fill: var(--text);
    font-size: 16px;
    font-weight: 700;
}

.legend-label {
    fill: var(--text);
    font-size: 12px;
    font-weight: 600;
}

.ml-grid {
    display: grid;
    grid-template-columns:
        repeat(
            auto-fit,
            minmax(180px, 1fr)
        );
    gap: 14px;
}

.ml-card {
    background: var(--surface2);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 16px;
}

.ml-card span {
    display: block;
    color: var(--muted);
    font-size: .85rem;
}

.ml-card strong {
    display: block;
    margin-top: 5px;
    font-size: 1.35rem;
}

.progress-card {
    margin-top: 20px;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 18px;
}

.progress-header,
.progress-meta {
    display: flex;
    justify-content: space-between;
    gap: 20px;
}

.progress-header span,
.progress-meta {
    color: var(--muted);
    font-size: .9rem;
}

.progress {
    height: 12px;
    margin: 14px 0;
    background: var(--surface2);
    border-radius: 999px;
    overflow: hidden;
}

.progress > div {
    height: 100%;
    background: var(--green);
}

.ml-info {
    margin-top: 18px;
    color: var(--muted);
}

footer {
    max-width: 1500px;
    margin: auto;
    padding: 0 20px 40px;
    color: var(--muted);
    font-size: .85rem;
}

@media (max-width: 700px) {

    header {
        padding: 26px 18px;
    }

    h1 {
        font-size: 1.8rem;
    }

    main {
        padding: 22px 14px 60px;
    }

    .charts {
        grid-template-columns: 1fr;
    }

    .score-row {
        display: block;
    }

    .score-row > div:last-child {
        margin-top: 8px;
    }

    .progress-header,
    .progress-meta {
        display: block;
    }
}

</style>
"""
