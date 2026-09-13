"""
Export av aktuella ML-fynd.

Fynddetektorn producerar en DataFrame.
Den här modulen ansvarar för att göra resultatet
tillgängligt för webbappen och andra konsumenter.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


FINDINGS_FILE = Path(
    "data/ml/fynd.jsonl"
)


def _jsonvärde(value):
    """
    Gör ett pandas/numpy-värde JSON-kompatibelt.
    """

    if pd.isna(value):
        return None

    if hasattr(value, "item"):
        try:
            return value.item()
        except (ValueError, TypeError):
            pass

    return value


def dataframe_till_records(
    fynd: pd.DataFrame,
) -> list[dict]:
    """
    Konverterar fynd-DataFrame till JSON-kompatibla records.
    """

    if fynd.empty:
        return []

    records = []

    for record in fynd.to_dict(
        orient="records"
    ):
        records.append(
            {
                key: _jsonvärde(value)
                for key, value in record.items()
            }
        )

    return records


def exportera_fynd(
    fynd: pd.DataFrame,
    path: Path = FINDINGS_FILE,
) -> Path:
    """
    Skriver aktuella fynd till JSONL.

    Filen ersätts varje gång eftersom den representerar
    den aktuella fyndlistan, inte historiken.
    """

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    records = dataframe_till_records(
        fynd
    )

    with path.open(
        "w",
        encoding="utf-8",
    ) as fil:

        for record in records:
            fil.write(
                json.dumps(
                    record,
                    ensure_ascii=False,
                )
                + "\n"
            )

    return path
