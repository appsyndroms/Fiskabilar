"""
Gemensam feature engineering för marknadsvärderingen.

Alla features byggs här så att träning, diagnostik och prediktion
alltid använder exakt samma logik.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ml.normalization import (
    normalisera_modell,
    normalisera_variant,
)


FEATURES_NUMERIC = [
    "Mil",
    "ModelYear",
    "VehicleAge",
    "MileagePerYear",
    "LogMil",
    "ObservationDays",
    "MileageAgeInteraction",
]

FEATURES_KATEGORISK = [
    "Model",
    "Variant",
    "ModelVariant",
    "ObservationMonth",
]

FEATURES = (
    FEATURES_NUMERIC
    + FEATURES_KATEGORISK
)

TARGET = "Price"

EPOCH = pd.Timestamp(
    "2020-01-01",
    tz="UTC",
)


def build_features(
    df: pd.DataFrame,
    now: pd.Timestamp | None = None,
) -> pd.DataFrame:
    """
    Bygger samma features för träning och prediktion.
    """

    resultat = pd.DataFrame(
        index=df.index
    )

    resultat["Mil"] = pd.to_numeric(
        df["Mil"],
        errors="coerce",
    )

    resultat["ModelYear"] = pd.to_numeric(
        df["ModelYear"],
        errors="coerce",
    )

    resultat["Model"] = (
        df["Model"]
        .apply(
            normalisera_modell
        )
        .fillna("okänd")
    )

    resultat["Variant"] = (
        df["Variant"]
        .apply(
            normalisera_variant
        )
        .fillna("okänd")
    )

    resultat["Tid"] = pd.to_datetime(
        df.get("Tid"),
        errors="coerce",
        utc=True,
    )

    if now is None:
        now = pd.Timestamp.now(
            tz="UTC"
        )
    else:
        now = pd.Timestamp(now)

        if now.tzinfo is None:
            now = now.tz_localize(
                "UTC"
            )
        else:
            now = now.tz_convert(
                "UTC"
            )

    effektiv_tid = (
        resultat["Tid"]
        .fillna(now)
    )

    # Antal dagar sedan fast referensdatum.
    # Detta gör att linjär regression kan se marknadens tidsförändring.
    resultat["ObservationDays"] = (
        (
            effektiv_tid
            - EPOCH
        )
        .dt.total_seconds()
        / 86400.0
    )

    observation_year = (
        effektiv_tid.dt.year
        + effektiv_tid.dt.dayofyear
        / 365.25
    )

    # Bilens faktiska ålder vid observationstillfället.
    resultat["VehicleAge"] = (
        observation_year
        - resultat["ModelYear"]
    ).clip(
        lower=0
    )

    # Genomsnittligt miltal per år.
    resultat["MileagePerYear"] = (
        resultat["Mil"]
        / resultat["VehicleAge"]
        .clip(lower=1)
    )

    # Log-transform gör stora miltal mindre dominerande.
    resultat["LogMil"] = np.log1p(
        resultat["Mil"]
        .clip(lower=0)
    )

    # Interaktion mellan körsträcka och ålder.
    resultat["MileageAgeInteraction"] = (
        resultat["Mil"]
        * resultat["VehicleAge"]
    )

    # Gör kombinationen modell + variant till en egen kategori.
    resultat["ModelVariant"] = (
        resultat["Model"]
        + " | "
        + resultat["Variant"]
    )

    # Enkel månadseffekt.
    resultat["ObservationMonth"] = (
        effektiv_tid.dt.month
        .astype(str)
    )

    return resultat[
        FEATURES
    ]


def make_prediction_row(
    modell: str,
    mil: float | int,
    arsmodell: int,
    variant: str,
    now: pd.Timestamp | None = None,
) -> pd.DataFrame:
    """
    Skapar en rå rad som sedan passerar samma
    feature engineering som träningsdatan.
    """

    if now is None:
        now = pd.Timestamp.now(
            tz="UTC"
        )

    return pd.DataFrame(
        [
            {
                "Mil": mil,
                "ModelYear": arsmodell,
                "Model": modell,
                "Variant": variant,
                "Tid": now,
            }
        ]
    )
