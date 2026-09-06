"""
Bygger Fiskabilars statiska webbplats.

Läser data från data/ och skapar:

    web_site/
        index.html
        data.json
        .nojekyll

Webbplatsen kan därefter publiceras med GitHub Pages.
"""

from __future__ import annotations

import json
import html
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]

DATA_DIR = ROOT / "data"
OUTPUT_DIR = ROOT / "web_site"

STATE_FILE = DATA_DIR / "state.json"
MARKET_HISTORY_DIR = DATA_DIR / "market_history"
FIND_FEEDBACK_DIR = DATA_DIR / "find_feedback"
ML_DIR = DATA_DIR / "ml"


def read_json(path: Path, default: Any = None) -> Any:
    """Läser JSON-fil och returnerar default vid fel."""
    if not path.exists():
        return default

    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return default


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    """Läser JSONL-fil."""
    rows: list[dict[str, Any]] = []

    if not path.exists():
        return rows

    try:
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()

                if not line:
                    continue

                try:
                    value = json.loads(line)

                    if isinstance(value, dict):
                        rows.append(value)

                except json.JSONDecodeError:
                    continue

    except OSError:
        pass

    return rows


def read_all_jsonl(directory: Path) -> list[dict[str, Any]]:
    """Läser alla JSONL-filer i en katalog."""
    rows: list[dict[str, Any]] = []

    if not directory.exists():
        return rows

    for path in sorted(directory.glob("*.jsonl")):
        rows.extend(read_jsonl(path))

    return rows


def to_number(value: Any) -> float | None:
    """Försöker konvertera ett värde till tal."""
    if value is None:
        return None

    if isinstance(value, bool):
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def fmt_number(value: Any, decimals: int = 0) -> str:
    """Svensk talformatering."""
    number = to_number(value)

    if number is None:
        return "—"

    if decimals == 0:
        return f"{number:,.0f}".replace(",", " ")

    return f"{number:,.{decimals}f}".replace(",", " ")


def fmt_price(value: Any) -> str:
    """Formaterar pris."""
    number = to_number(value)

    if number is None:
        return "—"

    return f"{number:,.0f}".replace(",", " ") + " kr"


def safe(value: Any) -> str:
    """HTML-säker sträng."""
    return html.escape(str(value if value is not None else ""))


def vehicle_key(row: dict[str, Any]) -> str:
    """
    Hämtar stabil identitet för en bil.

    vehicle_id prioriteras eftersom den representerar
    samma fysiska bil även om annonsens ID/URL ändras.
    """
    return str(
        row.get("vehicle_id")
        or row.get("annons_id")
        or row.get("id")
        or row.get("url")
        or ""
    )


def parse_time(value: Any) -> datetime | None:
    """Parsar ISO-tid."""
    if not value:
        return None

    try:
        return datetime.fromisoformat(
            str(value).replace("Z", "+00:00")
        )
    except ValueError:
        return None


def latest_by_vehicle(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Tar senaste observationen per vehicle_id.
    """
    latest: dict[str, dict[str, Any]] = {}

    for row in rows:
        key = vehicle_key(row)

        if not key:
            continue

        current_time = parse_time(row.get("tid"))
        previous = latest.get(key)

        if previous is None:
            latest[key] = row
            continue

        previous_time = parse_time(previous.get("tid"))

        if current_time and previous_time:
            if current_time >= previous_time:
                latest[key] = row
        else:
            latest[key] = row

    return list(latest.values())


def get_current_findings(
    feedback: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Hämtar aktuella fynd från senaste fyndobservationen per bil.
    """
    fynd = [
        row
        for row in feedback
        if row.get("typ") == "fynd"
    ]

    latest = latest_by_vehicle(fynd)

    aktiva_statusar = {
        "AKTIV",
        "NY",
        "ÅTERKOMMEN",
    }

    result = [
        row
        for row in latest
        if str(
            row.get("livscykelstatus", "")
        ).upper()
        in aktiva_statusar
    ]

    result.sort(
        key=lambda row: (
            to_number(row.get("score")) or 0
        ),
        reverse=True,
    )

    return result


def get_price_reductions(
    feedback: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Hämtar observerade prissänkningar."""
    result = [
        row
        for row in feedback
        if row.get("utfall")
        in {
            "PRISSÄNKT",
            "FÖRSVUNNEN_EFTER_PRISSÄNKNING",
        }
    ]

    result.sort(
        key=lambda row: (
            to_number(
                row.get("total_prissankning")
            )
            or 0
        ),
        reverse=True,
    )

    return result


def get_find_outcomes(
    feedback: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Hämtar fynd-event.

    Feedbackhistoriken innehåller flera observationer av samma
    fynd eftersom pipeline körs återkommande.

    Här grupperas dessa till ett event för presentationen.
    """
    fynd = [
        row
        for row in feedback
        if row.get("typ") == "fynd"
    ]

    grouped: dict[str, list[dict[str, Any]]] = {}

    for row in fynd:
        key = vehicle_key(row)

        if not key:
            continue

        grouped.setdefault(key, []).append(row)

    events: list[dict[str, Any]] = []

    for key, rows in grouped.items():
        rows.sort(
            key=lambda row: (
                parse_time(row.get("tid"))
                or datetime.min
            )
        )

        current_event: dict[str, Any] | None = None

        for row in rows:
            status = str(
                row.get(
                    "livscykelstatus",
                    "",
                )
            ).upper()

            if (
                current_event is None
                or status in {
                    "NY",
                    "ÅTERKOMMEN",
                }
            ):
                current_event = dict(row)
                events.append(current_event)

    return events


def get_score_analysis(
    outcomes: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Bygger scoreintervall mot utfall."""
    buckets = {
        "0–39": [],
        "40–59": [],
        "60–69": [],
        "70–79": [],
        "80–89": [],
        "90–100": [],
    }

    for row in outcomes:
        score = to_number(row.get("score"))

        if score is None:
            continue

        if score < 40:
            bucket = "0–39"
        elif score < 60:
            bucket = "40–59"
        elif score < 70:
            bucket = "60–69"
        elif score < 80:
            bucket = "70–79"
        elif score < 90:
            bucket = "80–89"
        else:
            bucket = "90–100"

        buckets[bucket].append(row)

    result = []

    for bucket, rows in buckets.items():
        counts = Counter(
            str(
                row.get(
                    "utfall",
                    "OKÄNT",
                )
            )
            for row in rows
        )

        result.append(
            {
                "scoreintervall": bucket,
                "antal": len(rows),
                "utfall": dict(counts),
            }
        )

    return result


def get_ml_data() -> dict[str, Any]:
    """Läser ML-metadata och prediktioner."""
    metadata = read_json(
        ML_DIR / "model_metadata.json",
        {},
    )

    predictions = read_jsonl(
        ML_DIR / "predictions.jsonl"
    )

    return {
        "metadata": metadata
        if isinstance(metadata, dict)
        else {},
        "predictions": predictions,
    }


def build_payload() -> dict[str, Any]:
    """Bygger allt data som skickas till webbläsaren."""
    state = read_json(
        STATE_FILE,
        {},
    )

    feedback = read_all_jsonl(
        FIND_FEEDBACK_DIR
    )

    market_history = read_all_jsonl(
        MARKET_HISTORY_DIR
    )

    current_findings = get_current_findings(
        feedback
    )

    price_reductions = get_price_reductions(
        feedback
    )

    outcomes = get_find_outcomes(
        feedback
    )

    score_analysis = get_score_analysis(
        outcomes
    )

    ml = get_ml_data()

    return {
        "generated_at": datetime.now().astimezone().isoformat(),
        "summary": {
            "current_findings": len(
                current_findings
            ),
            "price_reductions": len(
                price_reductions
            ),
            "find_events": len(
                outcomes
            ),
            "market_observations": len(
                market_history
            ),
        },
        "current_findings": current_findings,
        "price_reductions": price_reductions,
        "find_outcomes": outcomes,
        "score_analysis": score_analysis,
        "market_history": market_history,
        "ml": ml,
        "state": state,
    }


def render_findings(rows: list[dict[str, Any]]) -> str:
    """Renderar aktuella fynd."""
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
            or row.get("namn")
            or "Okänd bil"
        )

        ar = (
            row.get("arsmodell")
            or row.get("modell_ar")
            or "—"
        )

        mil = (
            row.get("miltal")
            or row.get("mil")
            or "—"
        )

        pris = row.get(
            "pris",
            row.get("annonspris"),
        )

        diff = row.get(
            "diff",
            row.get("prisdiff"),
        )

        score = row.get("score")

        url = row.get(
            "url",
            row.get("annons_url"),
        )

        link = (
            f'<a href="{safe(url)}" '
            f'target="_blank">Öppna annons</a>'
            if url
            else "—"
        )

        html_rows.append(
            f"""
            <tr>
                <td>
                    <strong>{safe(modell)}</strong>
                </td>
                <td>{safe(ar)}</td>
                <td>{fmt_number(mil)}</td>
                <td>{fmt_price(pris)}</td>
                <td>{fmt_price(diff)}</td>
                <td>
                    <span class="score">
                        {fmt_number(score)}
                    </span>
                </td>
                <td>{link}</td>
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
                    <th>Diff</th>
                    <th>Score</th>
                    <th>Annons</th>
                </tr>
            </thead>
            <tbody>
                {''.join(html_rows)}
            </tbody>
        </table>
    </div>
    """


def render_price_reductions(
    rows: list[dict[str, Any]],
) -> str:
    """Renderar prissänkningar."""
    if not rows:
        return """
        <div class="empty">
            Inga observerade prissänkningar ännu.
        </div>
        """

    html_rows = []

    for row in rows[:50]:
        modell = (
            row.get("modell")
            or "Okänd bil"
        )

        initial = row.get(
            "initialpris"
        )

        lowest = row.get(
            "lagsta_pris"
        )

        reduction = row.get(
            "total_prissankning"
        )

        percentage = row.get(
            "procent_prissankning"
        )

        days = row.get(
            "dagar_till_prissankning"
        )

        html_rows.append(
            f"""
            <tr>
                <td><strong>{safe(modell)}</strong></td>
                <td>{fmt_price(initial)}</td>
                <td>{fmt_price(lowest)}</td>
                <td>{fmt_price(reduction)}</td>
                <td>{fmt_number(percentage, 1)} %</td>
                <td>{fmt_number(days, 1)}</td>
            </tr>
            """
        )

    return f"""
    <div class="table-wrap">
        <table>
            <thead>
                <tr>
                    <th>Bil</th>
                    <th>Initialpris</th>
                    <th>Lägsta pris</th>
                    <th>Sänkning</th>
                    <th>%</th>
                    <th>Dagar</th>
                </tr>
            </thead>
            <tbody>
                {''.join(html_rows)}
            </tbody>
        </table>
    </div>
    """


def render_outcomes(
    rows: list[dict[str, Any]],
) -> str:
    """Renderar fyndutfall."""
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

    total = sum(counts.values())

    bars = []

    for outcome, count in counts.most_common():
        share = (
            count / total * 100
            if total
            else 0
        )

        bars.append(
            f"""
            <div class="bar-row">
                <div class="bar-label">
                    <span>{safe(outcome)}</span>
                    <strong>{count}</strong>
                </div>
                <div class="bar">
                    <div style="width:{share:.1f}%"></div>
                </div>
            </div>
            """
        )

    return "".join(bars)


def render_score_analysis(
    rows: list[dict[str, Any]],
) -> str:
    """Renderar scoreanalys."""
    if not rows:
        return """
        <div class="empty">
            Inte tillräckligt med data ännu.
        </div>
        """

    output = []

    for row in rows:
        bucket = row["scoreintervall"]
        count = row["antal"]
        outcomes = row["utfall"]

        parts = [
            f"{safe(name)}: {value}"
            for name, value
            in sorted(outcomes.items())
        ]

        output.append(
            f"""
            <div class="score-row">
                <div>
                    <strong>{safe(bucket)}</strong>
                    <span>{count} event</span>
                </div>
                <div>
                    {' · '.join(parts) if parts else '—'}
                </div>
            </div>
            """
        )

    return "".join(output)


def render_market_history(
    rows: list[dict[str, Any]],
) -> str:
    """Renderar senaste marknadshistoriken."""
    if not rows:
        return """
        <div class="empty">
            Ingen marknadshistorik hittades.
        </div>
        """

    latest = sorted(
        rows,
        key=lambda row: (
            parse_time(row.get("tid"))
            or datetime.min
        ),
        reverse=True,
    )[:100]

    html_rows = []

    for row in latest:
        modell = (
            row.get("modell")
            or row.get("namn")
            or "Okänd"
        )

        tid = row.get(
            "tid",
            "—",
        )

        pris = row.get(
            "annonspris",
            row.get("pris"),
        )

        mil = row.get(
            "miltal",
            row.get("mil"),
        )

        html_rows.append(
            f"""
            <tr>
                <td>{safe(tid)}</td>
                <td><strong>{safe(modell)}</strong></td>
                <td>{fmt_number(mil)}</td>
                <td>{fmt_price(pris)}</td>
            </tr>
            """
        )

    return f"""
    <div class="table-wrap">
        <table>
            <thead>
                <tr>
                    <th>Tid</th>
                    <th>Bil</th>
                    <th>Miltal</th>
                    <th>Pris</th>
                </tr>
            </thead>
            <tbody>
                {''.join(html_rows)}
            </tbody>
        </table>
    </div>
    """


def render_ml(
    ml: dict[str, Any],
) -> str:
    """Renderar ML-statistik från model_metadata.json."""
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

    active_model_key = str(
        metadata.get(
            "modell",
            ""
        )
    ).strip()

    model_names = {
        "random_forest": "Random Forest",
        "linear_regression": "Linear Regression",
    }

    active_model_name = model_names.get(
        active_model_key,
        active_model_key or "Okänd",
    )

    observations = metadata.get(
        "antal_observationer",
        0,
    )

    training_rows = metadata.get(
        "antal_traning",
        0,
    )

    test_rows = metadata.get(
        "antal_test",
        0,
    )

    trained_at = metadata.get(
        "skapad",
        "—",
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

    if (
        isinstance(metrics, dict)
        and active_model_key
    ):
        model_metrics = metrics.get(
            active_model_key,
            {},
        )

        if isinstance(model_metrics, dict):
            active_metrics = model_metrics.get(
                "totalt",
                {},
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

    total_rows = (
        to_number(training_rows) or 0
    ) + (
        to_number(test_rows) or 0
    )

    training_number = (
        to_number(training_rows) or 0
    )

    progress = (
        training_number
        / total_rows
        * 100
        if total_rows
        else 0
    )

    features_text = (
        ", ".join(
            str(feature)
            for feature in features
        )
        if isinstance(features, list)
        and features
        else "—"
    )

    comparison_rows = []

    for model_key in (
        "linear_regression",
        "random_forest",
    ):
        model_name = model_names.get(
            model_key,
            model_key,
        )

        model_data = {}

        if isinstance(metrics, dict):
            model_metrics = metrics.get(
                model_key,
                {},
            )

            if isinstance(model_metrics, dict):
                model_data = model_metrics.get(
                    "totalt",
                    {},
                )

        comparison_rows.append(
            f"""
            <tr>
                <td>
                    <strong>{safe(model_name)}</strong>
                    {
                        " ⭐"
                        if model_key == active_model_key
                        else ""
                    }
                </td>
                <td>
                    {fmt_number(
                        model_data.get("r2"),
                        3
                    )}
                </td>
                <td>
                    {fmt_price(
                        model_data.get("mae")
                    )}
                </td>
                <td>
                    {fmt_price(
                        model_data.get("rmse")
                    )}
                </td>
                <td>
                    {fmt_number(
                        model_data.get(
                            "mape_procent"
                        ),
                        2
                    )} %
                </td>
            </tr>
            """
        )

    variant_rows = []

    per_variant = active_metrics.get(
        "per_variant",
        {},
    )

    if isinstance(per_variant, dict):
        for variant, values in sorted(
            per_variant.items()
        ):
            if not isinstance(values, dict):
                continue

            variant_rows.append(
                f"""
                <tr>
                    <td>
                        <strong>{safe(variant)}</strong>
                    </td>
                    <td>
                        {fmt_number(
                            values.get(
                                "antal_observationer"
                            )
                        )}
                    </td>
                    <td>
                        {fmt_number(
                            values.get("r2"),
                            3
                        )}
                    </td>
                    <td>
                        {fmt_price(
                            values.get("mae")
                        )}
                    </td>
                    <td>
                        {fmt_number(
                            values.get(
                                "mape_procent"
                            ),
                            2
                        )} %
                    </td>
                </tr>
                """
            )

    year_rows = []

    per_year = active_metrics.get(
        "per_årsmodell",
        {},
    )

    if isinstance(per_year, dict):
        for year, values in sorted(
            per_year.items(),
            key=lambda item: str(item[0]),
        ):
            if not isinstance(values, dict):
                continue

            year_rows.append(
                f"""
                <tr>
                    <td>
                        <strong>{safe(year)}</strong>
                    </td>
                    <td>
                        {fmt_number(
                            values.get(
                                "antal_observationer"
                            )
                        )}
                    </td>
                    <td>
                        {fmt_number(
                            values.get("r2"),
                            3
                        )}
                    </td>
                    <td>
                        {fmt_price(
                            values.get("mae")
                        )}
                    </td>
                    <td>
                        {fmt_number(
                            values.get(
                                "mape_procent"
                            ),
                            2
                        )} %
                    </td>
                </tr>
                """
            )

    variant_section = ""

    if variant_rows:
        variant_section = f"""
        <h3>Resultat per bilvariant</h3>

        <div class="table-wrap">
            <table>
                <thead>
                    <tr>
                        <th>Variant</th>
                        <th>Observationer</th>
                        <th>R²</th>
                        <th>MAE</th>
                        <th>MAPE</th>
                    </tr>
                </thead>
                <tbody>
                    {''.join(variant_rows)}
                </tbody>
            </table>
        </div>
        """

    year_section = ""

    if year_rows:
        year_section = f"""
        <h3>Resultat per årsmodell</h3>

        <div class="table-wrap">
            <table>
                <thead>
                    <tr>
                        <th>Årsmodell</th>
                        <th>Observationer</th>
                        <th>R²</th>
                        <th>MAE</th>
                        <th>MAPE</th>
                    </tr>
                </thead>
                <tbody>
                    {''.join(year_rows)}
                </tbody>
            </table>
        </div>
        """

    return f"""
    <div class="ml-grid">

        <div class="ml-card">
            <span>Aktiv modell</span>
            <strong>{safe(active_model_name)}</strong>
        </div>

        <div class="ml-card">
            <span>Observationer</span>
            <strong>{fmt_number(observations)}</strong>
        </div>

        <div class="ml-card">
            <span>R²</span>
            <strong>{fmt_number(r2, 3)}</strong>
        </div>

        <div class="ml-card">
            <span>MAE</span>
            <strong>{fmt_price(mae)}</strong>
        </div>

        <div class="ml-card">
            <span>RMSE</span>
            <strong>{fmt_price(rmse)}</strong>
        </div>

        <div class="ml-card">
            <span>MAPE</span>
            <strong>{fmt_number(mape, 2)} %</strong>
        </div>

    </div>

    <div class="progress-card">
        <div class="progress-header">
            <strong>ML-progress</strong>
            <span>
                {fmt_number(training_rows)}
                träningsrader /
                {fmt_number(total_rows)} totalt
            </span>
        </div>

        <div class="progress">
            <div style="width:{progress:.1f}%"></div>
        </div>

        <div class="progress-meta">
            <span>
                Träning: {fmt_number(training_rows)}
            </span>
            <span>
                Test: {fmt_number(test_rows)}
            </span>
        </div>
    </div>

    <div class="ml-info">
        <p>
            <strong>Senast tränad:</strong>
            {safe(trained_at)}
        </p>

        <p>
            <strong>Features:</strong>
            {safe(features_text)}
        </p>
    </div>

    <h3>Modelljämförelse</h3>

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
                {''.join(comparison_rows)}
            </tbody>
        </table>
    </div>

    {variant_section}

    {year_section}
    """


def build_html(payload: dict[str, Any]) -> str:
    """Bygger index.html."""
    summary = payload["summary"]

    current_findings = payload[
        "current_findings"
    ]

    price_reductions = payload[
        "price_reductions"
    ]

    outcomes = payload[
        "find_outcomes"
    ]

    score_analysis = payload[
        "score_analysis"
    ]

    market_history = payload[
        "market_history"
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
<meta name="viewport"
      content="width=device-width, initial-scale=1">

<title>Fiskabilar Analytics</title>

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
    --yellow: #ecc94b;
    --red: #fc8181;
}}

* {{
    box-sizing: border-box;
}}

html {{
    scroll-behavior: smooth;
}}

body {{
    margin: 0;
    background: var(--bg);
    color: var(--text);
    font-family:
        -apple-system,
        BlinkMacSystemFont,
        "Segoe UI",
        sans-serif;
}}

a {{
    color: var(--accent);
    text-decoration: none;
}}

a:hover {{
    text-decoration: underline;
}}

header {{
    padding: 36px 24px 28px;
    border-bottom: 1px solid var(--border);
    background: var(--surface);
}}

.header-inner {{
    max-width: 1500px;
    margin: auto;
}}

h1 {{
    margin: 0;
    font-size: 2.2rem;
}}

.subtitle {{
    color: var(--muted);
    margin-top: 8px;
}}

nav {{
    position: sticky;
    top: 0;
    z-index: 10;
    background: rgba(11, 15, 20, .94);
    backdrop-filter: blur(10px);
    border-bottom: 1px solid var(--border);
}}

.nav-inner {{
    max-width: 1500px;
    margin: auto;
    display: flex;
    gap: 8px;
    overflow-x: auto;
    padding: 10px 16px;
}}

nav a {{
    white-space: nowrap;
    padding: 8px 12px;
    border-radius: 8px;
}}

nav a:hover {{
    background: var(--surface2);
    text-decoration: none;
}}

main {{
    max-width: 1500px;
    margin: auto;
    padding: 28px 20px 80px;
}}

section {{
    margin-bottom: 46px;
    scroll-margin-top: 70px;
}}

h2 {{
    margin: 0 0 18px;
    font-size: 1.5rem;
}}

h3 {{
    margin-top: 28px;
}}

.kpis {{
    display: grid;
    grid-template-columns:
        repeat(auto-fit, minmax(190px, 1fr));
    gap: 14px;
    margin-top: 24px;
}}

.kpi {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 14px;
    padding: 18px;
}}

.kpi span {{
    color: var(--muted);
    font-size: .9rem;
}}

.kpi strong {{
    display: block;
    font-size: 1.8rem;
    margin-top: 6px;
}}

.card {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 14px;
    padding: 20px;
    margin-bottom: 16px;
}}

.table-wrap {{
    overflow-x: auto;
    border: 1px solid var(--border);
    border-radius: 12px;
}}

table {{
    width: 100%;
    border-collapse: collapse;
    min-width: 760px;
}}

th,
td {{
    padding: 12px 14px;
    text-align: left;
    border-bottom: 1px solid var(--border);
}}

th {{
    color: var(--muted);
    font-size: .85rem;
    font-weight: 600;
}}

tr:last-child td {{
    border-bottom: 0;
}}

.score {{
    display: inline-block;
    min-width: 40px;
    text-align: center;
    padding: 4px 8px;
    border-radius: 8px;
    background: var(--surface2);
    font-weight: 700;
}}

.empty {{
    color: var(--muted);
    padding: 20px 0;
}}

.bar-row {{
    margin-bottom: 18px;
}}

.bar-label {{
    display: flex;
    justify-content: space-between;
    margin-bottom: 7px;
}}

.bar {{
    height: 10px;
    background: var(--surface2);
    border-radius: 999px;
    overflow: hidden;
}}

.bar > div {{
    height: 100%;
    background: var(--accent);
    border-radius: inherit;
}}

.score-row {{
    display: flex;
    justify-content: space-between;
    gap: 20px;
    padding: 14px 0;
    border-bottom: 1px solid var(--border);
}}

.score-row:last-child {{
    border-bottom: 0;
}}

.score-row span {{
    color: var(--muted);
    margin-left: 12px;
}}

.ml-grid {{
    display: grid;
    grid-template-columns:
        repeat(auto-fit, minmax(180px, 1fr));
    gap: 14px;
}}

.ml-card {{
    background: var(--surface2);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 16px;
}}

.ml-card span {{
    display: block;
    color: var(--muted);
    font-size: .85rem;
}}

.ml-card strong {{
    display: block;
    margin-top: 5px;
    font-size: 1.35rem;
}}

.progress-card {{
    margin-top: 20px;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 18px;
}}

.progress-header,
.progress-meta {{
    display: flex;
    justify-content: space-between;
    gap: 20px;
}}

.progress-header span,
.progress-meta {{
    color: var(--muted);
    font-size: .9rem;
}}

.progress {{
    height: 12px;
    margin: 14px 0;
    background: var(--surface2);
    border-radius: 999px;
    overflow: hidden;
}}

.progress > div {{
    height: 100%;
    background: var(--green);
}}

.ml-info {{
    margin-top: 18px;
    color: var(--muted);
}}

footer {{
    max-width: 1500px;
    margin: auto;
    padding: 0 20px 40px;
    color: var(--muted);
    font-size: .85rem;
}}

@media (max-width: 700px) {{

    header {{
        padding: 26px 18px;
    }}

    h1 {{
        font-size: 1.8rem;
    }}

    main {{
        padding: 22px 14px 60px;
    }}

    .score-row {{
        display: block;
    }}

    .score-row > div:last-child {{
        margin-top: 8px;
        color: var(--muted);
    }}

}}

</style>
</head>

<body>

<header>
    <div class="header-inner">
        <h1>🚗 Fiskabilar Analytics</h1>
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
        <a href="#oversikt">Översikt</a>
        <a href="#fynd">🚗 Aktuella fynd</a>
        <a href="#score">⭐ Score</a>
        <a href="#sankningar">📉 Prissänkningar</a>
        <a href="#utfall">📊 Fyndutfall</a>
        <a href="#historik">🕒 Marknadshistorik</a>
        <a href="#ml">🤖 ML statistik</a>
    </div>
</nav>

<main>

<section id="oversikt">

    <h2>Översikt</h2>

    <div class="kpis">

        <div class="kpi">
            <span>Aktuella fynd</span>
            <strong>
                {summary["current_findings"]}
            </strong>
        </div>

        <div class="kpi">
            <span>Fynd-event</span>
            <strong>
                {summary["find_events"]}
            </strong>
        </div>

        <div class="kpi">
            <span>Prissänkningar</span>
            <strong>
                {summary["price_reductions"]}
            </strong>
        </div>

        <div class="kpi">
            <span>Marknadsobservationer</span>
            <strong>
                {summary["market_observations"]}
            </strong>
        </div>

    </div>

</section>

<section id="fynd">

    <h2>🚗 Aktuella fynd</h2>

    <div class="card">
        {render_findings(current_findings)}
    </div>

</section>

<section id="score">

    <h2>⭐ Score mot faktiskt utfall</h2>

    <div class="card">
        {render_score_analysis(score_analysis)}
    </div>

</section>

<section id="sankningar">

    <h2>📉 Prissänkningar</h2>

    <div class="card">
        {render_price_reductions(price_reductions)}
    </div>

</section>

<section id="utfall">

    <h2>📊 Fyndutfall</h2>

    <div class="card">
        {render_outcomes(outcomes)}
    </div>

</section>

<section id="historik">

    <h2>🕒 Marknadshistorik</h2>

    <div class="card">
        {render_market_history(market_history)}
    </div>

</section>

<section id="ml">

    <h2>🤖 ML statistik</h2>

    <div class="card">
        {render_ml(ml)}
    </div>

</section>

</main>

<footer>
    Fiskabilar Analytics · Statisk vy byggd automatiskt från data/
</footer>

</body>
</html>
"""


def main() -> None:
    """Bygger webbplatsen."""
    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    payload = build_payload()

    data_path = OUTPUT_DIR / "data.json"

    with data_path.open(
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            payload,
            f,
            ensure_ascii=False,
            indent=2,
        )

    html_path = OUTPUT_DIR / "index.html"

    html_path.write_text(
        build_html(payload),
        encoding="utf-8",
    )

    nojekyll = OUTPUT_DIR / ".nojekyll"

    nojekyll.write_text(
        "",
        encoding="utf-8",
    )

    print(
        "=================================================="
    )
    print(
        "Fiskabilar statiska webbplats"
    )
    print(
        "=================================================="
    )
    print(
        f"Aktuella fynd: "
        f"{len(payload['current_findings'])}"
    )
    print(
        f"Fynd-event: "
        f"{len(payload['find_outcomes'])}"
    )
    print(
        f"Prissänkningar: "
        f"{len(payload['price_reductions'])}"
    )
    print(
        f"Marknadsobservationer: "
        f"{len(payload['market_history'])}"
    )
    print(
        f"HTML: {html_path}"
    )
    print(
        f"Data: {data_path}"
    )
    print(
        "=================================================="
    )


if __name__ == "__main__":
    main()
