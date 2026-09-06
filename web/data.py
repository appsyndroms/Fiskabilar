"""
Dataåtkomst för Fiskabilar Analytics.

Den här modulen ska vara den enda plats där webbappen
läser analysdata från projektets datafiler.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parent.parent

MARKET_HISTORY = (
    ROOT
    / "data"
    / "market_history"
    / "market_history.jsonl"
)

STATE_FILE = (
    ROOT
    / "data"
    / "state.json"
)


def _las_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []

    resultat = []

    with path.open(
        "r",
        encoding="utf-8",
    ) as fil:
        for rad in fil:
            rad = rad.strip()

            if not rad:
                continue

            try:
                resultat.append(
                    json.loads(rad)
                )
            except json.JSONDecodeError:
                continue

    return resultat


def _las_state() -> dict:
    if not STATE_FILE.exists():
        return {}

    try:
        with STATE_FILE.open(
            "r",
            encoding="utf-8",
        ) as fil:
            return json.load(fil)
    except (
        OSError,
        json.JSONDecodeError,
    ):
        return {}


def hamta_historik() -> pd.DataFrame:
    """
    Läser marknadshistoriken och returnerar en DataFrame.
    """

    data = _las_jsonl(
        MARKET_HISTORY
    )

    if not data:
        return pd.DataFrame()

    return pd.DataFrame(data)


def hamta_dashboard_data() -> dict:
    """
    Hämtar sammanfattande data till dashboarden.
    """

    historik = hamta_historik()
    state = _las_state()

    historiska_annonser = len(
        historik
    )

    annonser_senaste_korning = (
        state.get(
            "senaste_antal_annonser",
            0,
        )
    )

    unika_bilar = state.get(
        "senaste_antal_unika",
        0,
    )

    aktiva_fynd = state.get(
        "senaste_antal_fynd",
        0,
    )

    return {
        "annonser_senaste_korning":
            annonser_senaste_korning,

        "unika_bilar":
            unika_bilar,

        "historiska_annonser":
            historiska_annonser,

        "aktiva_fynd":
            aktiva_fynd,

        "ml_modell":
            "Ej tränad",

        "ml_mae":
            "—",
    }


def hamta_marknadsdata(
    modell: str | None = None,
    variant: str | None = None,
) -> pd.DataFrame:
    """
    Returnerar historiska marknadsdata filtrerade
    på modell och/eller variant.
    """

    df = hamta_historik()

    if df.empty:
        return df

    if modell and "modell" in df.columns:
        df = df[
            df["modell"].astype(str).str.contains(
                modell,
                case=False,
                na=False,
            )
        ]

    if variant and "variant" in df.columns:
        df = df[
            df["variant"].astype(str).str.contains(
                variant,
                case=False,
                na=False,
            )
        ]

    return df


def hamta_senaste_fynd() -> pd.DataFrame:
    """
    Hämtar de bästa aktuella fynden.

    Den första versionen försöker läsa fynddata från state.
    Senare kopplas denna direkt till scoring/valuation-lagret.
    """

    state = _las_state()

    fynd = state.get(
        "senaste_fynd",
        [],
    )

    if not fynd:
        return pd.DataFrame(
            columns=[
                "Modell",
                "Årsmodell",
                "Miltal",
                "Pris",
                "Bör-pris",
                "Skillnad",
                "Score",
            ]
        )

    return pd.DataFrame(fynd)
