"""
Prediktion av marknadsvärde med tränad ML-modell.

Modellen använder:

    Mil
    ModelYear
    Model
    Variant

Modell och variant normaliseras alltid på
samma sätt som träningsdatan.

Om modellen saknas eller indata är ogiltig
returneras None.
"""

from __future__ import annotations

from pathlib import Path

import joblib
import pandas as pd

from ml.normalization import (
    normalisera_modell,
    normalisera_variant,
)


MODEL_FIL = Path(
    "data/ml/market_model.joblib"
)


def modell_finns() -> bool:
    """Returnerar True om en tränad ML-modell finns."""

    return MODEL_FIL.exists()


def ladda_modell():
    """Laddar den senast tränade modellen."""

    if not modell_finns():

        raise FileNotFoundError(
            f"Ingen tränad ML-modell finns i "
            f"{MODEL_FIL}"
        )

    return joblib.load(
        MODEL_FIL
    )


def prediktera_borpris(
    modell: str,
    mil: float | int,
    arsmodell: int,
    variant: str,
) -> float | None:
    """
    Predikterar bör-pris.

    Modell och variant normaliseras före
    prediktionen så att samma bil alltid
    använder samma ML-kategorier.
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

    modellnamn = (
        normalisera_modell(
            modell
        )
    )

    variantnamn = (
        normalisera_variant(
            variant
        )
    )

    if not modellnamn:
        return None

    if not variantnamn:
        return None

    data = pd.DataFrame(
        [
            {
                "Mil": mil,

                "ModelYear":
                    arsmodell,

                "Model":
                    modellnamn,

                "Variant":
                    variantnamn,
            }
        ]
    )

    try:

        tränad_modell = (
            ladda_modell()
        )

        prediktion = (
            tränad_modell.predict(
                data
            )
        )

    except Exception:

        return None

    if len(prediktion) != 1:
        return None

    pris = float(
        prediktion[0]
    )

    if pris <= 0:
        return None

    return round(
        pris
    )
