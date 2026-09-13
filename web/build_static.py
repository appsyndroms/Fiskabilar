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


ML_DIR = (
    DATA_DIR
    / "ml"
)


ML_FINDINGS_FILE = (
    ML_DIR
    / "fynd.jsonl"
)


def _normalisera_vehicle_id(
    value,
) -> str:
    """
    Normaliserar vehicle_id så att både:

        vehicle_id:ABC123

    och:

        ABC123

    kan jämföras.
    """

    if value is None:
        return ""

    text = str(
        value
    ).strip()

    if text.startswith(
        "vehicle_id:"
    ):
        return text[
            len("vehicle_id:"):
        ]

    return text


def _get_url(
    row: dict,
):
    """
    Hämtar URL från ett godtyckligt fynd-/historikrecord.
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
        value = row.get(
            key
        )

        if isinstance(
            value,
            list,
        ):
            for item in value:
                if (
                    item is not None
                    and str(item).strip()
                ):
                    return str(
                        item
                    ).strip()

        elif (
            value is not None
            and str(value).strip()
        ):
            return str(
                value
            ).strip()

    return None


def _nummer(
    value,
):
    """
    Försöker konvertera ett värde till float.
    """

    if value is None:
        return None

    try:
        return float(
            value
        )

    except (
        TypeError,
        ValueError,
    ):
        return None


def _samma_nummer(
    vänster,
    höger,
    tolerans=0.01,
) -> bool:
    """
    Numerisk jämförelse med liten tolerans.
    """

    a = _nummer(
        vänster
    )

    b = _nummer(
        höger
    )

    if (
        a is None
        or b is None
    ):
        return False

    return abs(
        a - b
    ) <= tolerans


def _berika_fynd_med_url(
    findings: list[dict],
    market_history: list[dict],
) -> list[dict]:
    """
    Kompletterar ML-fynd med annons-URL från marknadshistoriken.

    Detta är en sista defensiv länk mellan fyndexporten och
    originalhistoriken.

    Fyndfilen behöver alltså inte själv bära URL hela vägen från
    ML-pipelinen för att webbplatsen ska kunna visa annonslänken.

    Matchningsordning:

      1. vehicle_id / Identity
      2. modell + variant + årsmodell + miltal + pris

    Senaste observationen med URL prioriteras.
    """

    if not findings:
        return findings

    if not market_history:
        return findings

    historik = []

    for row in market_history:

        if not isinstance(
            row,
            dict,
        ):
            continue

        url = _get_url(
            row
        )

        if not url:
            continue

        historik.append(
            (
                row,
                url,
            )
        )

    if not historik:
        return findings

    def sort_key(
        item,
    ):
        row = item[0]

        return str(
            row.get(
                "tid",
                ""
            )
        )

    historik.sort(
        key=sort_key
    )

    berikade = []

    for finding in findings:

        result = dict(
            finding
        )

        befintlig_url = _get_url(
            result
        )

        if befintlig_url:
            result["url"] = (
                befintlig_url
            )

            berikade.append(
                result
            )

            continue

        identity = (
            result.get(
                "Identity"
            )
            or result.get(
                "vehicle_id"
            )
        )

        identity = _normalisera_vehicle_id(
            identity
        )

        kandidater = []

        if identity:

            for (
                history_row,
                url,
            ) in historik:

                history_identity = (
                    history_row.get(
                        "vehicle_id"
                    )
                    or history_row.get(
                        "Identity"
                    )
                )

                history_identity = (
                    _normalisera_vehicle_id(
                        history_identity
                    )
                )

                if (
                    history_identity
                    and history_identity
                    == identity
                ):
                    kandidater.append(
                        (
                            history_row,
                            url,
                        )
                    )

        # Fallback om Identity inte ger träff.
        if not kandidater:

            finding_model = str(
                finding.get(
                    "Model",
                    ""
                )
            ).strip().lower()

            finding_variant = str(
                finding.get(
                    "Variant",
                    ""
                )
            ).strip().lower()

            finding_year = (
                finding.get(
                    "ModelYear"
                )
            )

            finding_mil = (
                finding.get(
                    "Mil"
                )
            )

            finding_price = (
                finding.get(
                    "Price"
                )
            )

            for (
                history_row,
                url,
            ) in historik:

                history_model = str(
                    history_row.get(
                        "modell",
                        history_row.get(
                            "Model",
                            ""
                        ),
                    )
                ).strip().lower()

                history_variant = str(
                    history_row.get(
                        "variant",
                        history_row.get(
                            "Variant",
                            ""
                        ),
                    )
                ).strip().lower()

                history_year = (
                    history_row.get(
                        "arsmodell",
                        history_row.get(
                            "ModelYear"
                        ),
                    )
                )

                history_mil = (
                    history_row.get(
                        "miltal",
                        history_row.get(
                            "Mil"
                        ),
                    )
                )

                history_price = (
                    history_row.get(
                        "pris",
                        history_row.get(
                            "annonspris",
                            history_row.get(
                                "Price"
                            ),
                        ),
                    )
                )

                if (
                    finding_model
                    and history_model
                    != finding_model
                ):
                    continue

                if (
                    finding_variant
                    and history_variant
                    and history_variant
                    != finding_variant
                ):
                    continue

                if not _samma_nummer(
                    finding_year,
                    history_year,
                    tolerans=0,
                ):
                    continue

                if not _samma_nummer(
                    finding_mil,
                    history_mil,
                    tolerans=1,
                ):
                    continue

                if not _samma_nummer(
                    finding_price,
                    history_price,
                    tolerans=1,
                ):
                    continue

                kandidater.append(
                    (
                        history_row,
                        url,
                    )
                )

        if kandidater:

            # Historiken är sorterad kronologiskt,
            # så sista träffen är den senaste.
            _, url = kandidater[-1]

            result["url"] = url

        else:
            result["url"] = (
                result.get(
                    "url"
                )
                or ""
            )

        berikade.append(
            result
        )

    return berikade


def get_ml_data() -> dict:
    """
    Läser ML-metadata och prediktioner.
    """

    metadata = read_json(
        DATA_DIR
        / "ml"
        / "model_metadata.json",
        {},
    )

    prediction_file = (
        DATA_DIR
        / "ml"
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
    market_history=None,
) -> list[dict]:
    """
    Läser aktuella fynd från ML-pipelinen.

    Primär källa:

        data/ml/fynd.jsonl

    Om URL saknas i fyndfilen kompletteras fyndet
    från marknadshistoriken.
    """

    findings = read_jsonl(
        ML_FINDINGS_FILE
    )

    if market_history:
        findings = _berika_fynd_med_url(
            findings,
            market_history,
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
    """
    Läser all data och bygger webbplatsens payload.

    Aktuella fynd kommer från ML-pipelinen:

        data/ml/fynd.jsonl

    Saknade URL:er kompletteras från
    marknadshistoriken.
    """

    state = read_json(
        STATE_FILE,
        {},
    )

    feedback = read_all_jsonl(
        FIND_FEEDBACK_DIR,
    )

    market_history = read_all_jsonl(
        MARKET_HISTORY_DIR
    )

    current_findings = (
        get_ml_findings(
            market_history
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
