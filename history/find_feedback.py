"""
Feedbackdata för Fiskabilar.

Sparar observationer av bilar som klassats som fynd.
Dessa observationer används senare för att analysera:

- vilka fyndsignaler som fungerar
- falska fynd
- prisutveckling efter fynd
- tid till försvinnande
- prisnivåer som verkar leda till snabb försäljning

Feedbacklagret påverkar inte score eller valuation.
"""

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


TIDSZON = ZoneInfo("Europe/Stockholm")

HISTORIK_DIR = Path(
    "data/find_feedback"
)


def _filnamn() -> Path:
    idag = datetime.now(
        TIDSZON
    ).date().isoformat()

    return (
        HISTORIK_DIR
        / f"find_feedback_{idag[:7]}.jsonl"
    )


def spara_fyndfeedback(
    bil: dict,
    vardering: dict,
    score: int,
) -> None:
    """
    Sparar en fyndobservation.

    En observation representerar hur Fiskabilar
    såg bilen när den klassades som ett fynd.

    Funktionen är medvetet append-baserad.
    Vi ändrar aldrig tidigare observationer.
    """

    HISTORIK_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    breakdown = (
        vardering.get(
            "score_breakdown"
        )
        or {}
    )

    url = (
        bil.get("urls")
        or [
            bil.get("url")
            or ""
        ]
    )[0]

    observation = {
        "typ": "fynd",
        "tid": datetime.now(
            TIDSZON
        ).isoformat(),

        "vehicle_id": bil.get(
            "vehicle_id"
        ),

        "annons_id": bil.get(
            "annons_id"
        ),

        "modell": bil.get(
            "modell"
        ),

        "variant": bil.get(
            "variant"
        ),

        "utrustningsniva": bil.get(
            "utrustningsniva"
        ),

        "arsmodell": bil.get(
            "arsmodell"
        ),

        "miltal": bil.get(
            "miltal"
        ),

        "pris": bil.get(
            "annonspris"
        ),

        "marknadsvarde": vardering.get(
            "marknadsvarde"
        ),

        "diff": vardering.get(
            "diff"
        ),

        "score": score,

        "prispoang": breakdown.get(
            "pris"
        ),

        "miltalspoang": breakdown.get(
            "miltal"
        ),

        "utrustningspoang": breakdown.get(
            "utrustning"
        ),

        "trygghetspoang": breakdown.get(
            "trygghet"
        ),

        "historikspoang": breakdown.get(
            "historik"
        ),

        "auktion_avdrag": breakdown.get(
            "auktion_avdrag"
        ),

        "historik_observationer": bil.get(
            "historik_observationer",
            0,
        ),

        "historik_dagar": bil.get(
            "historik_dagar",
            0,
        ),

        "historik_forsta_pris": bil.get(
            "historik_forsta_pris"
        ),

        "historik_senaste_pris": bil.get(
            "historik_senaste_pris"
        ),

        "historik_prisfall": bil.get(
            "historik_prisfall",
            0,
        ),

        "historik_marknadsvarde": bil.get(
            "historik_marknadsvarde"
        ),

        "url": url,
    }

    with _filnamn().open(
        "a",
        encoding="utf-8",
    ) as f:
        f.write(
            json.dumps(
                observation,
                ensure_ascii=False,
            )
            + "\n"
        )
