"""
Bygger Fiskabilars statiska webbplats.
Detta är endast orchestratorn.
Logik för inläsning, analys, diagram och HTML-rendering
ligger i separata moduler.
"""
from __future__ import annotations
import json
from datetime import datetime
from pathlib import Path
from data_loader import (
    DATA_DIR,
    FIND_FEEDBACK_DIR,
    MARKET_HISTORY_DIR,
    OUTPUT_DIR,
    STATE_FILE,
    read_all_jsonl,
    read_json,
    read_jsonl,
)
from analysis import (
    get_find_outcomes,
    get_market_history_analysis,
    get_price_reductions,
    get_score_analysis,
)
from renderer import build_html
ROOT = Path(__file__).resolve().parents[1]
ML_DIR = DATA_DIR / "ml"
ML_FINDINGS_FILE = ML_DIR / "fynd.jsonl"
VEHICLE_IDENTITY_FILE = (
    DATA_DIR
    / "market_history"
    / "vehicle_identity.json"
)
def _normalisera_vehicle_id(value) -> str:
    """
    Normaliserar vehicle_id så att både:
        vehicle_id:vehicle:00000255
    och:
        vehicle:00000255
    jämförs som samma identitet.
    """
    if value is None:
        return ""
    text = str(value).strip()
    if text.startswith("vehicle_id:"):
        return text[len("vehicle_id:"):]
    return text
def _get_url(row: dict):
    """Hämtar annons-URL från ett record."""
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
        if isinstance(value, list):
            for item in value:
                if item is not None and str(item).strip():
                    return str(item).strip()
        elif value is not None and str(value).strip():
            return str(value).strip()
    return None
def _load_vehicle_identity_urls() -> dict[str, str]:
    """
    Läser den permanenta fordonsidentitetsdatabasen och bygger:
        vehicle:00000255 -> https://...
    vehicle_identity.json är den auktoritativa kopplingen mellan
    ett fordons permanenta identitet och dess annons-URL.
    """
    data = read_json(
        VEHICLE_IDENTITY_FILE,
        {},
    )
    if not isinstance(data, dict):
        return {}
    identifiers = data.get("identifiers", {})
    if not isinstance(identifiers, dict):
        return {}
    result: dict[str, str] = {}
    for identifier, vehicle_id in identifiers.items():
        if not isinstance(identifier, str):
            continue
        if not identifier.startswith("url:"):
            continue
        url = identifier[len("url:"):].strip()
        normalized_vehicle_id = _normalisera_vehicle_id(
            vehicle_id
        )
        if not normalized_vehicle_id or not url:
            continue
        result[normalized_vehicle_id] = url
    return result
def _berika_fynd_med_url(
    findings: list[dict],
    vehicle_identity_urls: dict[str, str],
) -> list[dict]:
    """
    Kompletterar ML-fynd med URL via den permanenta fordonsidentiteten.
    Matchningen sker endast via Identity/vehicle_id. Vi försöker inte
    gissa URL genom modell, miltal eller pris eftersom projektet redan
    har en exakt identitetsmappning i vehicle_identity.json.
    """
    if not findings or not vehicle_identity_urls:
        return findings
    enriched: list[dict] = []
    matched = 0
    for finding in findings:
        result = dict(finding)
        existing_url = _get_url(result)
        if existing_url:
            result["url"] = existing_url
            matched += 1
            enriched.append(result)
            continue
        identity = (
            result.get("Identity")
            or result.get("vehicle_id")
        )
        normalized_identity = _normalisera_vehicle_id(
            identity
        )
        url = vehicle_identity_urls.get(
            normalized_identity
        )
        if url:
            result["url"] = url
            matched += 1
        else:
            result["url"] = ""
        enriched.append(result)
    print(
        f"URL-komplettering: "
        f"{matched}/{len(findings)} fynd har annons-URL"
    )
    return enriched
def get_ml_data() -> dict:
    """Läser ML-metadata och prediktioner."""
    metadata = read_json(
        ML_DIR / "model_metadata.json",
        {},
    )
    prediction_file = (
        ML_DIR
        / "predictions.jsonl"
    )
    if prediction_file.exists():
        predictions = read_jsonl(
            prediction_file
        )
    else:
        predictions = []
    return {
        "metadata": (
            metadata
            if isinstance(
                metadata,
                dict,
            )
            else {}
        ),
        "predictions": predictions,
    }
def get_ml_findings() -> list[dict]:
    """Läser aktuella ML-fynd och kompletterar deras annons-URL."""
    findings = read_jsonl(
        ML_FINDINGS_FILE
    )
    vehicle_identity_urls = (
        _load_vehicle_identity_urls()
    )
    findings = _berika_fynd_med_url(
        findings,
        vehicle_identity_urls,
    )
    def fynd_score(
        row: dict,
    ) -> float:
        try:
            return float(
                row.get(
                    "FyndScore",
                    0,
                )
            )
        except (
            TypeError,
            ValueError,
        ):
            return 0
    return sorted(
        findings,
        key=fynd_score,
        reverse=True,
    )
def build_payload() -> dict:
    """Läser all data och bygger webbplatsens payload."""
    state = read_json(
        STATE_FILE,
        {},
    )
    feedback = read_all_jsonl(
        FIND_FEEDBACK_DIR,
    )
    market_history = read_all_jsonl(
        MARKET_HISTORY_DIR,
    )
    current_findings = get_ml_findings()
    price_reductions = get_price_reductions(
        feedback,
    )
    outcomes = get_find_outcomes(
        feedback,
    )
    score_analysis = get_score_analysis(
        outcomes,
    )
    (
        history_table,
        history_series,
    ) = get_market_history_analysis(
        market_history,
    )
    ml = get_ml_data()
    return {
        "generated_at": (
            datetime.now()
            .astimezone()
            .isoformat()
        ),
        "summary": {
            "current_findings":
                len(current_findings),
            "find_events":
                len(outcomes),
            "price_reductions":
                len(price_reductions),
            "market_observations":
                len(market_history),
            "model_year_groups":
                len(history_table),
        },
        "current_findings":
            current_findings,
        "price_reductions":
            price_reductions,
        "find_outcomes":
            outcomes,
        "score_analysis":
            score_analysis,
        "market_history":
            market_history,
        "history_table":
            history_table,
        "history_series":
            history_series,
        "ml":
            ml,
        "state":
            state,
    }
def main() -> None:
    """Bygger web_site/."""
    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )
    payload = build_payload()
    data_path = (
        OUTPUT_DIR
        / "data.json"
    )
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
    html_path = (
        OUTPUT_DIR
        / "index.html"
    )
    html_path.write_text(
        build_html(payload),
        encoding="utf-8",
    )
    nojekyll = (
        OUTPUT_DIR
        / ".nojekyll"
    )
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
        f"Modell/årsmodell: "
        f"{len(payload['history_table'])}"
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
