"""
Prediktion av marknadsvärde med tränad ML-modell.

Den här modulen är avsiktligt frikopplad från den befintliga
valuation/market_value.py.

Om en tränad modell saknas, eller om underlaget är otillräckligt,
returneras None.

Det gör att valuation-systemet senare kan använda ML som första
alternativ och behålla den befintliga värderingen som fallback.
"""

from __future__ import annotations

from pathlib import Path

import joblib
import pandas as pd


MODEL_FIL = Path(
    "data/ml/market_model.joblib"
)


def modell_finns() -> bool:
    """Returnerar True om en tränad modell finns."""

    return MODEL_FIL.exists()


def ladda_modell():
    """Laddar den senast tränade modellen."""

    if not modell_finns():
        raise FileNotFoundError(
            f"Ingen tränad ML-modell finns i {MODEL_FIL}"
        )

    return joblib.load(
        MODEL_FIL
    )


def prediktera_borpris(
    mil: float | int,
    arsmodell: int,
    variant: str,
) -> float | None:
    """
    Predikterar bör-pris.

    Returnerar None om modellen inte finns.

    Parametrar:
        mil:
            Bilens miltal.

        arsmodell:
            Bilens årsmodell.

        variant:
            Modellvariant, exempelvis "T6 AWD",
            "T8 AWD" eller "530e xDrive Touring".
    """

    if not modell_finns():
        return None

    try:
        mil = float(mil)
        arsmodell = int(arsmodell)
    except (TypeError, ValueError):
        return None

    if mil < 0:
        return None

    if not variant:
        return None

    modell = ladda_modell()

    data = pd.DataFrame(
        [
            {
                "Mil": mil,
                "ModelYear": arsmodell,
                "Variant": str(variant).strip(),
            }
        ]
    )

    prediktion = modell.predict(
        data
    )

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
