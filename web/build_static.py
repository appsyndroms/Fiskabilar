from __future__ import annotations

import json
import math
import re
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]

ML_DATA_FILE = ROOT / "data" / "ml_valuation.jsonl"
ML_FINDINGS_FILE = ROOT / "data" / "ml" / "fynd.jsonl"
MARKET_HISTORY_DIR = ROOT / "data" / "market_history"

OUTPUT_HTML = ROOT / "index.html"
OUTPUT_DATA = ROOT / "data.json"

# Samma grundprincip som history/lifecycle.py:
# en annons betraktas som aktiv om den observerats inom detta antal dagar.
AKTIVITETSDAGAR = 2


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []

    rows: list[dict[str, Any]] = []

    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()

            if not line:
                continue

            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue

            if isinstance(value, dict):
                rows.append(value)

    return rows


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            default=_json_default,
        ),
        encoding="utf-8",
    )


def _json_default(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()

    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass

    if isinstance(value, float) and math.isnan(value):
        return None

    return str(value)


def _is_valid_url(value: Any) -> bool:
    """
    Returnerar True endast för riktiga HTTP(S)-URL:er.

    Viktigt eftersom pandas NaN annars kan bli strängen "nan".
    """
    if value is None:
        return False

    try:
        if isinstance(value, float) and math.isnan(value):
            return False
    except Exception:
        pass

    text = str(value).strip()

    if not text:
        return False

    if text.lower() in {"nan", "none", "null"}:
        return False

    return text.startswith("http://") or text.startswith("https://")


def _normalisera_vehicle_id(value: Any) -> str | None:
    if value is None:
        return None

    text = str(value).strip()

    if not text:
        return None

    # Hantera eventuella varianter som:
    # vehicle_id:vehicle:00000123
    # vehicle:00000123
    if text.startswith("vehicle_id:"):
        text = text[len("vehicle_id:") :]

    return text


def _get_vehicle_id(row: dict[str, Any]) -> str | None:
    """
    Försöker hitta vehicle_id/Identity i ett fynd eller
    en marknadshistorikpost.
    """
    for key in (
        "vehicle_id",
        "vehicleId",
        "VehicleId",
        "identity",
        "Identity",
    ):
        value = row.get(key)

        if value is None:
            continue

        normalized = _normalisera_vehicle_id(value)

        if normalized:
            return normalized

    return None


def _get_url(row: dict[str, Any]) -> str | None:
    """
    Hämtar URL från en rad och accepterar endast riktiga HTTP(S)-URL:er.
    """
    for key in (
        "url",
        "URL",
        "urls",
        "ad_url",
        "adUrl",
        "annons_url",
        "annonsUrl",
        "listing_url",
        "listingUrl",
    ):
        value = row.get(key)

        if _is_valid_url(value):
            return str(value).strip()

    return None


def _parse_tid(value: Any) -> datetime | None:
    """
    Tolkar tid från marknadshistoriken.
    """
    if value is None:
        return None

    if isinstance(value, datetime):
        return value

    text = str(value).strip()

    if not text:
        return None

    # ISO 8601, inklusive Z.
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        pass

    # Några vanliga alternativa format.
    formats = (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
    )

    for fmt in formats:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue

    return None


def _load_market_history() -> list[dict[str, Any]]:
    """
    Läser all marknadshistorik från data/market_history/*.jsonl.
    """
    if not MARKET_HISTORY_DIR.exists():
        return []

    rows: list[dict[str, Any]] = []

    for path in sorted(MARKET_HISTORY_DIR.glob("*.jsonl")):
        rows.extend(_read_jsonl(path))

    return rows


def _load_active_market_ads(
    market_history: list[dict[str, Any]],
) -> dict[str, tuple[datetime, str]]:
    """
    Bygger en mapping:

        vehicle_id -> (senaste observationstid, aktuell URL)

    Endast annonser som observerats inom AKTIVITETSDAGAR räknas som
    aktuella.

    Detta är viktigt: en gammal URL från vehicle_identity.json får inte
    göra ett historiskt ML-fynd till ett aktuellt fynd.
    """
    latest: dict[str, tuple[datetime, str]] = {}

    now = datetime.now().astimezone()

    for row in market_history:
        if not isinstance(row, dict):
            continue

        # Vi vill bara använda faktiska annonsobservationer.
        if row.get("typ") != "annons":
            continue

        vehicle_id = _get_vehicle_id(row)

        if not vehicle_id:
            continue

        url = _get_url(row)

        if not url:
            continue

        tid = _parse_tid(row.get("tid"))

        if tid is None:
            continue

        # Gör tidsjämförelsen timezone-aware.
        if tid.tzinfo is None:
            tid = tid.astimezone()

        dagar = (now - tid).total_seconds() / 86400

        # Framtida observationer ska inte räknas som aktuella.
        if dagar < 0:
            continue

        # Samma princip som lifecycle.py.
        if dagar > AKTIVITETSDAGAR:
            continue

        previous = latest.get(vehicle_id)

        if previous is None or tid > previous[0]:
            latest[vehicle_id] = (tid, url)

    return latest


def _berika_fynd_med_aktuell_url(
    findings: list[dict[str, Any]],
    market_history: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Kopplar ML-fynd till den aktuella annonsen.

    Ett fynd får endast en URL om samma vehicle_id har en aktiv
    annonsobservation i marknadshistoriken.

    Vi använder alltså INTE gamla URL:er från vehicle_identity.json.
    """
    active_ads = _load_active_market_ads(market_history)

    enriched: list[dict[str, Any]] = []

    for finding in findings:
        result = dict(finding)

        vehicle_id = _get_vehicle_id(result)
        active = active_ads.get(vehicle_id)

        if active is None:
            result["url"] = ""
        else:
            result["url"] = active[1]

        enriched.append(result)

    return enriched


def get_ml_data() -> list[dict[str, Any]]:
    """
    Läser ML-värderingarna.
    """
    return _read_jsonl(ML_DATA_FILE)


def get_ml_findings() -> list[dict[str, Any]]:
    """
    Hämtar ML-fynd och begränsar dem till aktuella annonser.

    Ett ML-fynd visas på webbplatsen endast om:
      1. det finns i fynd.jsonl
      2. vehicle_id kan matchas
      3. samma fordon har observerats som annons inom de senaste
         AKTIVITETSDAGAR
      4. den aktuella observationen innehåller en giltig HTTP(S)-URL
    """
    findings = _read_jsonl(ML_FINDINGS_FILE)

    market_history = _load_market_history()

    findings = _berika_fynd_med_aktuell_url(
        findings,
        market_history,
    )

    # Ett fynd utan aktuell, klickbar annons ska inte visas som
    # "aktuellt fynd".
    findings = [
        row
        for row in findings
        if _is_valid_url(row.get("url"))
    ]

    return findings


def _clean_value(value: Any) -> Any:
    """
    Gör data JSON-säkra och tar bort NaN/Infinity.
    """
    if value is None:
        return None

    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None

        return value

    if isinstance(value, dict):
        return {
            str(key): _clean_value(val)
            for key, val in value.items()
        }

    if isinstance(value, list):
        return [_clean_value(item) for item in value]

    if hasattr(value, "item"):
        try:
            return _clean_value(value.item())
        except Exception:
            pass

    return value


def build_payload(
    ml_data: list[dict[str, Any]],
    current_findings: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Bygger hela datamodellen som frontend använder.
    """
    return {
        "generated_at": datetime.now().astimezone().isoformat(),
        "ml_data": _clean_value(ml_data),
        "current_findings": _clean_value(current_findings),
        "summary": {
            "ml_data": len(ml_data),
            "current_findings": len(current_findings),
        },
    }


HTML_TEMPLATE = """<!doctype html>
<html lang="sv">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Fiskabilar</title>
  <style>
    body {
      font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI",
        sans-serif;
      margin: 0;
      padding: 24px;
      background: #f5f5f5;
      color: #222;
    }

    main {
      max-width: 1200px;
      margin: 0 auto;
    }

    h1 {
      margin-top: 0;
    }

    .summary {
      margin-bottom: 24px;
    }

    .finding {
      background: white;
      border-radius: 12px;
      padding: 16px;
      margin-bottom: 12px;
      box-shadow: 0 1px 4px rgba(0,0,0,.08);
    }

    .finding a {
      display: inline-block;
      margin-top: 8px;
    }

    .muted {
      color: #666;
    }
  </style>
</head>
<body>
<main>
  <h1>Fiskabilar</h1>

  <div id="summary" class="summary"></div>

  <h2>Aktuella fynd</h2>
  <div id="findings"></div>
</main>

<script>
const state = {
  data: null
};

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function update() {
  const data = state.data;

  const summary = document.getElementById("summary");
  const findings = document.getElementById("findings");

  const currentFindings = data.current_findings || [];

  summary.innerHTML = `
    <strong>Aktuella fynd: ${currentFindings.length}</strong>
  `;

  if (!currentFindings.length) {
    findings.innerHTML = `
      <p class="muted">
        Inga aktuella ML-fynd med aktiv annons just nu.
      </p>
    `;

    return;
  }

  findings.innerHTML = currentFindings.map(row => {
    const url = row.url;

    return `
      <article class="finding">
        <strong>${escapeHtml(row.Model || row.model || "")}</strong>

        <div>
          Pris:
          ${escapeHtml(row.Price ?? row.price ?? "")}
        </div>

        <div>
          Prognos:
          ${escapeHtml(
            row.PredictedPrice ??
            row.predicted_price ??
            row.prediction ??
            ""
          )}
        </div>

        <div>
          Avvikelse:
          ${escapeHtml(
            row.RelativeError ??
            row.relative_error ??
            row.discount ??
            ""
          )}
        </div>

        <a
          href="${escapeHtml(url)}"
          target="_blank"
          rel="noopener"
        >Öppna annons</a>
      </article>
    `;
  }).join("");
}

async function init() {
  const response = await fetch("data.json", {
    cache: "no-store"
  });

  state.data = await response.json();

  update();
}

init();
</script>
</body>
</html>
"""


def build_html() -> None:
    OUTPUT_HTML.write_text(
        HTML_TEMPLATE,
        encoding="utf-8",
    )


def main() -> None:
    ml_data = get_ml_data()

    current_findings = get_ml_findings()

    print(
        f"Aktuella fynd: {len(current_findings)}"
    )

    payload = build_payload(
        ml_data,
        current_findings,
    )

    _write_json(
        OUTPUT_DATA,
        payload,
    )

    build_html()

    print(
        f"Skrev {OUTPUT_DATA}"
    )

    print(
        f"Skrev {OUTPUT_HTML}"
    )

    print(
        f"Aktuella fynd med giltig aktuell URL: "
        f"{len(current_findings)}"
    )


if __name__ == "__main__":
    main()
