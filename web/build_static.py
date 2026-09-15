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


def _is_valid_url(value) -> bool:
    """
    Returnerar True endast för en faktisk användbar HTTP(S)-URL.

    Detta är viktigt eftersom pandas/JSON kan ge oss värden som:

        NaN
        "nan"
        None
        "null"
        ""

    Dessa får aldrig bli klickbara länkar på webbplatsen.
    """

    if value is None:
        return False

    try:
        if value != value:
            return False
    except Exception:
        pass

    text = str(value).strip()

    if not text:
        return False

    if text.lower() in {
        "nan",
        "none",
        "null",
    }:
        return False

    return text.startswith((
        "http://",
        "https://",
    ))


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


def _get_vehicle_id(row: dict) -> str:
    """
    Hämtar vehicle_id från ett record.

    ML-fynd använder normalt:
        Identity = vehicle_id:vehicle:00000255

    Market history använder:
        vehicle_id = vehicle:00000255
    """

    value = (
        row.get("Identity")
        or row.get("identity")
        or row.get("vehicle_id")
        or row.get("VehicleId")
        or row.get("VehicleID")
    )

    return _normalisera_vehicle_id(value)


def _get_url(row: dict):
    """
    Hämtar en giltig annons-URL från ett record.

    Ogiltiga värden som NaN, "nan", None, null och
    tomma strängar ignoreras.
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

        if isinstance(value, list):

            for item in value:

                if _is_valid_url(item):
                    return str(item).strip()

        elif _is_valid_url(value):

            return str(value).strip()

    return None


def _parse_tid(value):
    """
    Försöker tolka historikens tidsstämpel.

    Market history använder exempelvis:

        2026-09-13T10:23:45+02:00
    """

    if not value:
        return None

    try:
        return datetime.fromisoformat(
            str(value)
        )

    except (
        TypeError,
        ValueError,
    ):
        return None


def _load_vehicle_identity_urls() -> dict[str, str]:
    """
    Läser vehicle_identity.json och bygger en mapping:

        vehicle:00000255 -> https://...

    Endast giltiga URL:er används.

    Om flera URL-identiteter finns för samma vehicle_id
    behålls den senast påträffade giltiga URL:en.
    """

    data = read_json(
        VEHICLE_IDENTITY_FILE,
        {},
    )

    if not isinstance(
        data,
        dict,
    ):
        return {}

    identifiers = data.get(
        "identifiers",
        {},
    )

    if not isinstance(
        identifiers,
        dict,
    ):
        return {}

    result: dict[str, str] = {}

    for identifier, vehicle_id in identifiers.items():

        if not isinstance(
            identifier,
            str,
        ):
            continue

        if not identifier.startswith(
            "url:"
        ):
            continue

        url = identifier[
            len("url:"):
        ].strip()

        if not _is_valid_url(url):
            continue

        normalized_vehicle_id = (
            _normalisera_vehicle_id(
                vehicle_id
            )
        )

        if not normalized_vehicle_id:
            continue

        result[
            normalized_vehicle_id
        ] = url

    return result


def _load_latest_market_urls(
    market_history: list[dict],
) -> dict[str, str]:
    """
    Bygger en mapping:

        vehicle_id -> senaste kända giltiga annons-URL

    Endast riktiga annonsobservationer används.

    Den senaste observationen avgörs av 'tid', inte av
    ordningen i listan.

    Detta är viktigt eftersom samma fysiska bil kan få
    ett nytt Bilweb-annons-ID och därmed en helt ny URL.
    """

    latest: dict[
        str,
        tuple[datetime, str],
    ] = {}

    for row in market_history:

        if not isinstance(
            row,
            dict,
        ):
            continue

        if row.get("typ") != "annons":
            continue

        vehicle_id = _get_vehicle_id(
            row
        )

        if not vehicle_id:
            continue

        url = _get_url(
            row
        )

        if not url:
            continue

        tid = _parse_tid(
            row.get("tid")
        )

        if tid is None:
            continue

        previous = latest.get(
            vehicle_id
        )

        if (
            previous is None
            or tid > previous[0]
        ):
            latest[
                vehicle_id
            ] = (
                tid,
                url,
            )

    return {
        vehicle_id: value[1]
        for vehicle_id, value
        in latest.items()
    }


def _berika_fynd_med_url(
    findings: list[dict],
    market_history: list[dict],
    vehicle_identity_urls: dict[str, str],
) -> list[dict]:
    """
    Kompletterar ML-fynd med aktuell annons-URL.

    Prioritetsordning:

    1. Giltig URL som redan finns direkt på ML-fyndet
    2. Senaste giltiga annonsobservationen i market_history
    3. vehicle_identity.json som fallback

    Ogiltiga värden, exempelvis "nan", betraktas som
    om URL saknas.
    """

    if not findings:
        return findings

    latest_market_urls = (
        _load_latest_market_urls(
            market_history
        )
    )

    enriched: list[dict] = []

    direct_matches = 0
    market_matches = 0
    identity_matches = 0
    missing_matches = 0

    for finding in findings:

        result = dict(
            finding
        )

        existing_url = _get_url(
            result
        )

        if existing_url:

            result["url"] = (
                existing_url
            )

            direct_matches += 1

            enriched.append(
                result
            )

            continue

        vehicle_id = _get_vehicle_id(
            result
        )

        market_url = (
            latest_market_urls.get(
                vehicle_id
            )
        )

        if _is_valid_url(
            market_url
        ):

            result["url"] = (
                market_url
            )

            market_matches += 1

            enriched.append(
                result
            )

            continue

        identity_url = (
            vehicle_identity_urls.get(
                vehicle_id
            )
        )

        if _is_valid_url(
            identity_url
        ):

            result["url"] = (
                identity_url
            )

            identity_matches += 1

        else:

            result["url"] = ""

            missing_matches += 1

        enriched.append(
            result
        )

    print(
        "URL-komplettering: "
        f"{direct_matches} direkt, "
        f"{market_matches} via market_history, "
        f"{identity_matches} via vehicle_identity, "
        f"{missing_matches} saknas"
    )

    print(
        "Aktuella URL-mappningar: "
        f"{len(latest_market_urls)} fordon"
    )

    return enriched


def get_ml_data() -> dict:
    """
    Läser ML-metadata och prediktioner.
    """

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


def get_ml_findings(
    market_history: list[dict],
) -> list[dict]:
    """
    Läser aktuella ML-fynd.

    Ett fynd räknas som aktivt endast om det finns
    en fungerande annons-URL.

    Fynd utan URL ligger kvar i fynd.jsonl som rådata,
    men tas bort från webbplatsens current_findings.
    """

    findings = read_jsonl(
        ML_FINDINGS_FILE
    )

    vehicle_identity_urls = (
        _load_vehicle_identity_urls()
    )

    findings = _berika_fynd_med_url(
        findings,
        market_history,
        vehicle_identity_urls,
    )

    # Ett fynd utan fungerande annons-URL är inte
    # ett aktivt fynd eftersom användaren inte kan agera på det.
    findings = [
        row
        for row in findings
        if _is_valid_url(
            row.get("url")
        )
    ]

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
    """
    Läser all data och bygger webbplatsens payload.
    """

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

    current_findings = get_ml_findings(
        market_history
    )

    price_reductions = (
        get_price_reductions(
            feedback,
        )
    )

    outcomes = get_find_outcomes(
        feedback,
    )

    score_analysis = (
        get_score_analysis(
            outcomes,
        )
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
    """
    Bygger web_site/.
    """

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
