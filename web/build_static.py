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
    OUTPUT_DIR,
    FIND_FEEDBACK_DIR,
    MARKET_HISTORY_DIR,
    STATE_FILE,
    read_all_jsonl,
    read_json,
)

from analysis import (
    get_current_findings,
    get_find_outcomes,
    get_market_history_analysis,
    get_price_reductions,
    get_score_analysis,
    parse_time,
    vehicle_key,
)

from renderer import build_html


ROOT = Path(__file__).resolve().parents[1]


def get_ml_data() -> dict:
    """
    Läser ML-metadata och prediktioner.
    """
    metadata = read_json(
        DATA_DIR / "ml" / "model_metadata.json",
        {},
    )

    predictions = read_all_jsonl(
        DATA_DIR / "ml",
    )

    # predictions.jsonl ska inte blandas ihop med
    # eventuella andra JSONL-filer i ml/.
    prediction_file = (
        DATA_DIR
        / "ml"
        / "predictions.jsonl"
    )

    if prediction_file.exists():
        predictions = read_all_jsonl(
            DATA_DIR / "ml",
            pattern="predictions.jsonl",
        )
    else:
        predictions = []

    return {
        "metadata": (
            metadata
            if isinstance(metadata, dict)
            else {}
        ),
        "predictions": predictions,
    }


def add_find_age(
    current_findings: list[dict],
    find_events: list[dict],
) -> list[dict]:
    """
    Lägger till antal dagar som det aktuella fynd-eventet har varit ute.

    Dagarna räknas från fynd-eventets ursprungliga `tid`, inte från
    senaste observationen av bilen. På så sätt återställs inte åldern
    varje gång annonsen observeras igen.
    """

    event_by_vehicle: dict[str, list[datetime]] = {}

    for event in find_events:
        key = vehicle_key(event)
        event_time = parse_time(event.get("tid"))

        if not key or event_time is None:
            continue

        event_by_vehicle.setdefault(
            key,
            [],
        ).append(event_time)

    today = datetime.now().astimezone().date()

    result = []

    for row in current_findings:
        copy = dict(row)

        key = vehicle_key(row)
        observation_time = parse_time(
            row.get("tid")
        )

        candidates = event_by_vehicle.get(
            key,
            [],
        )

        if (
            candidates
            and observation_time is not None
        ):
            candidates = [
                event_time
                for event_time in candidates
                if event_time <= observation_time
            ]

        if candidates:
            event_date = max(
                candidates
            ).date()

            copy["dagar_ute"] = max(
                0,
                (
                    today
                    - event_date
                ).days,
            )

        else:
            copy["dagar_ute"] = 0

        result.append(copy)

    return result


def build_payload() -> dict:
    """
    Läser all data och bygger webbplatsens payload.

    `current_findings` betyder aktiva fynd just nu.
    Det är medvetet inte samma sak som dagens nya fynd i
    den dagliga e-postrapporten.
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

    current_findings = (
        get_current_findings(
            feedback
        )
    )

    price_reductions = (
        get_price_reductions(
            feedback
        )
    )

    outcomes = (
        get_find_outcomes(
            feedback
        )
    )

    current_findings = add_find_age(
        current_findings,
        outcomes,
    )

    score_analysis = (
        get_score_analysis(
            outcomes
        )
    )

    (
        history_table,
        history_series,
    ) = get_market_history_analysis(
        market_history
    )

    ml = get_ml_data()

    return {
        "generated_at":
            datetime.now()
            .astimezone()
            .isoformat(),

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
