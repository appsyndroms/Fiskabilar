"""
Dataåtkomst för Blankdiss.

Webbappen läser resultat från ML-pipelinen.
Den ändrar aldrig originaldata.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


ROOT = (
    Path(__file__)
    .resolve()
    .parent
    .parent
)

DATA_DIR = (
    ROOT
    / "data"
)

ML_DIR = (
    DATA_DIR
    / "ml"
)

FINDINGS_FILE = (
    ML_DIR
    / "fynd.jsonl"
)

STATE_FILE = (
    DATA_DIR
    / "state.json"
)


def _las_jsonl(
    path: Path,
) -> list[dict]:

    if not path.exists():
        return []

    resultat = []

    try:
        with path.open(
            "r",
            encoding="utf-8",
        ) as fil:

            for rad in fil:

                rad = rad.strip()

                if not rad:
                    continue

                try:
                    data = json.loads(
                        rad
                    )
                except json.JSONDecodeError:
                    continue

                if isinstance(
                    data,
                    dict,
                ):
                    resultat.append(
                        data
                    )

    except OSError:
        return []

    return resultat


def _las_json(
    path: Path,
) -> dict:

    if not path.exists():
        return {}

    try:

        with path.open(
            "r",
            encoding="utf-8",
        ) as fil:

            data = json.load(
                fil
            )

        if isinstance(
            data,
            dict,
        ):
            return data

    except (
        OSError,
        json.JSONDecodeError,
    ):
        pass

    return {}


def hamta_senaste_fynd() -> pd.DataFrame:
    """
    Hämtar den senaste fyndlistan från ML-exporten.

    Primär källa:
        data/ml/fynd.jsonl

    Fallback:
        data/state.json
    """

    data = _las_jsonl(
        FINDINGS_FILE
    )

    if data:
        return pd.DataFrame(
            data
        )

    state = _las_json(
        STATE_FILE
    )

    for nyckel in (
        "senaste_fynd",
        "fynd",
        "aktuella_fynd",
    ):

        data = state.get(
            nyckel
        )

        if isinstance(
            data,
            list,
        ):
            return pd.DataFrame(
                data
            )

    return pd.DataFrame()
