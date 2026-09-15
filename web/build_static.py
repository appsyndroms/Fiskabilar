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

# En annons räknas som aktuell om den observerats
# inom samma tidsfönster som history/lifecycle.py använder.
AKTIVITETSDAGAR = 2


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

    Denna mapping används INTE för att avgöra om ett fynd
    är aktuellt. Den finns kvar för övriga delar av systemet,
    men en gammal identity-URL får inte göra ett gammalt
    fynd till ett aktuellt webb-fynd.
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


def _load_active_market_urls(
    market_history: list[dict],
) -> dict[str, str]:
    """
    Bygger en mapping:

        vehicle_id -> aktuell annons-URL

    Endast annonsobservationer som är högst
    AKTIVITETSDAGAR gamla används.

    Detta är den viktiga skillnaden mot den tidigare
    implementationen som använde senaste historiska URL
    oavsett hur gammal den var.

    En gammal Bilweb-annons kan fortfarande finnas i
    market_history men vara borttagen från Bilweb.
    Den ska därför inte räknas som aktuell.
    """

    latest: dict[
        str,
        tuple[datetime, str],
    ] = {}

    now = datetime.now().astimezone()

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

        # Market history bör normalt redan vara timezone-aware.
        # Om en äldre post saknar timezone använder vi lokal tid.
        if tid.tzinfo is None:
            tid = tid.astimezone()

        age_days = (
            now - tid
        ).total_seconds() / 86400

        # Framtida observationer ska inte räknas.
        if age_days < 0:
            continue

        # Endast aktuella observationer.
        if age_days > AKTIVITETSDAGAR:
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


def _berika_fynd_med_aktuell_url(
    findings: list[dict],
    market_history: list[dict],
) -> list[dict]:
    """
    Kompletterar ML-fynd med aktuell annons-URL.

    Ett fynd får endast en URL om samma vehicle_id
    har en aktuell annonsobservation i market_history.

    vehicle_identity.json används medvetet INTE som
    fallback här.

    Detta förhindrar att gamla annonser blir presenterade
    som aktuella fynd.
    """

    if not findings:
        return findings

    active_market_urls = (
        _load_active_market_urls(
            market_history
        )
    )

    enriched: list[dict] = []

    active_matches = 0
    missing_matches = 0

    for finding in findings:

        result = dict(
            finding
        )

        vehicle_id = _get_vehicle_id(
            result
        )

        active_url = (
            active_market_urls.get(
                vehicle_id
            )
        )

        if _is_valid_url(
            active_url
        ):

            result["url"] = (
                active_url
            )

            active_matches += 1

        else:

            result["url"] = ""

            missing_matches += 1

        enriched.append(
            result
        )

    print(
        "Aktuell URL-komplettering: "
        f"{active_matches} aktuella, "
        f"{missing_matches} saknas"
    )

    print(
        "Aktuella URL-mappningar: "
        f"{len(active_market_urls)} fordon"
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
    Läser ML-fynd och begränsar dem till aktuella annonser.

    Ett fynd visas på webbplatsen endast om:

      1. det finns i fynd.jsonl
      2. vehicle_id kan matchas
      3. samma fordon har observerats som annons
         inom AKTIVITETSDAGAR
      4. observationen har en giltig HTTP(S)-URL

    Fynd utan aktuell URL ligger kvar i fynd.jsonl
    som rådata men tas bort från current_findings.
    """

    findings = read_jsonl(
        ML_FINDINGS_FILE
    )

    findings = _berika_fynd_med_aktuell_url(
        findings,
        market_history,
    )

    # Ett fynd utan aktuell fungerande annons-URL
    # är inte ett aktuellt webb-fynd.
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
