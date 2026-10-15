"""
Prediktion av marknadsvärde med tränad ML-modell.
"""

from __future__ import annotations

from pathlib import Path
from functools import lru_cache

import joblib

from ml.features import (
    build_features,
    make_prediction_row,
)


MODEL_FIL = Path(
    "data/ml/market_model.joblib"
)


def modell_finns() -> bool:
    """Returnerar True om tränad modell finns."""

    return MODEL_FIL.exists()


def ladda_modell():
    """Laddar den senast tränade modellen."""

    if not modell_finns():
        raise FileNotFoundError(
            f"Ingen tränad ML-modell finns i "
            f"{MODEL_FIL}"
        )

    return _ladda_modell_cached(MODEL_FIL.resolve(), MODEL_FIL.stat().st_mtime_ns)


@lru_cache(maxsize=1)
def _ladda_modell_cached(path: Path, modified_ns: int):
    return joblib.load(path)


def prediktera_borpris(
    modell: str,
    mil: float | int,
    arsmodell: int,
    variant: str,
) -> float | None:
    """
    Predikterar bör-pris.

    Samma feature engineering används som
    under träningen.
    """

    if not modell_finns():
        return None

    if not modell:
        return None

    if not variant:
        return None

    try:
        mil = float(
            mil
        )

        arsmodell = int(
            arsmodell
        )

    except (
        TypeError,
        ValueError,
    ):
        return None

    if mil < 0:
        return None

    if arsmodell < 1990:
        return None

    try:
        rådata = make_prediction_row(
            modell=modell,
            mil=mil,
            arsmodell=arsmodell,
            variant=variant,
        )

        features = build_features(
            rådata
        )

        tränad_modell = (
            ladda_modell()
        )

        prediction = (
            tränad_modell.predict(
                features
            )
        )

    except Exception as exc:
        raise RuntimeError("ML-prediktionen misslyckades") from exc

    if len(prediction) != 1:
        return None

    pris = float(
        prediction[0]
    )

    if pris <= 0:
        return None

    return round(
        pris
    )
