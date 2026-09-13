"""Träning av datadriven marknadsvärdering."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import joblib
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

from ml.features import (
    FEATURES,
    FEATURES_KATEGORISK,
    FEATURES_NUMERIC,
    TARGET,
    build_features,
)
from ml.normalization import normalisera_modell, normalisera_variant


TIDSZON = ZoneInfo("Europe/Stockholm")
HISTORIK_DIR = Path("data/market_history")
OUTPUT_DIR = Path("data/ml")
MODEL_FIL = OUTPUT_DIR / "market_model.joblib"
METADATA_FIL = OUTPUT_DIR / "model_metadata.json"

MIN_TRAINING_OBSERVATIONER = 30


def _ladda_jsonl() -> pd.DataFrame:
    filer = sorted(HISTORIK_DIR.glob("market_history_*.jsonl"))

    legacy = HISTORIK_DIR / "market_history.jsonl"

    if legacy.exists():
        filer.append(legacy)

    if not filer:
        raise FileNotFoundError(
            f"Ingen marknadshistorik hittades i {HISTORIK_DIR}"
        )

    poster = []

    for fil in filer:
        with fil.open("r", encoding="utf-8") as file:
            for radnummer, rad in enumerate(file, start=1):
                rad = rad.strip()

                if not rad:
                    continue

                try:
                    post = json.loads(rad)
                except json.JSONDecodeError:
                    print(
                        f"Varning: kunde inte läsa "
                        f"{fil}:{radnummer}"
                    )
                    continue

                if isinstance(post, dict):
                    poster.append(post)

    if not poster:
        raise ValueError(
            "Historikfilerna innehåller inga giltiga JSONL-poster."
        )

    return pd.DataFrame(poster)


def _första_identitet(row: pd.Series) -> str | None:
    """Använder befintlig fysisk fordonsidentitet före annons-/URL-identitet."""

    for field in (
        "vehicle_id",
        "vehicleId",
        "car_id",
        "carId",
        "annons_id",
        "annonsId",
        "ad_id",
        "adId",
        "url",
        "URL",
    ):
        value = row.get(field)

        if pd.notna(value) and str(value).strip():
            return f"{field}:{str(value).strip()}"

    return None


def _första_url(row: pd.Series) -> str | None:
    """Hämtar annonsens URL från de URL-fält som stöds av rådata."""

    for field in (
        "url",
        "URL",
        "ad_url",
        "adUrl",
        "listing_url",
        "listingUrl",
        "annons_url",
        "annonsUrl",
    ):
        value = row.get(field)

        if pd.notna(value) and str(value).strip():
            return str(value).strip()

    return None


def _bygg_dataset(df: pd.DataFrame) -> pd.DataFrame:
    resultat = pd.DataFrame(index=df.index)

    resultat["Mil"] = pd.to_numeric(
        df.get("miltal"),
        errors="coerce",
    )

    resultat["ModelYear"] = pd.to_numeric(
        df.get("arsmodell"),
        errors="coerce",
    )

    resultat["Model"] = (
        df.get("modell")
        .apply(normalisera_modell)
    )

    resultat["Variant"] = (
        df.get("variant")
        .apply(normalisera_variant)
    )

    resultat["Price"] = pd.to_numeric(
        df.get("annonspris"),
        errors="coerce",
    )

    resultat["Tid"] = pd.to_datetime(
        df.get("tid"),
        errors="coerce",
        utc=True,
    )

    # Behåll annonsens URL genom hela ML-pipelinen.
    resultat["url"] = df.apply(
        _första_url,
        axis=1,
    )

    # Identitet används endast för deduplicering/split,
    # aldrig som ML-feature.
    resultat["Identity"] = df.apply(
        _första_identitet,
        axis=1,
    )

    resultat = resultat.dropna(
        subset=[
            "Mil",
            "ModelYear",
            "Price",
        ]
    )

    resultat = resultat[
        resultat["Price"] > 0
    ]

    resultat = resultat[
        resultat["Mil"] >= 0
    ]

    resultat = resultat[
        resultat["ModelYear"].between(
            1990,
            datetime.now(TIDSZON).year + 1,
        )
    ]

    resultat["Model"] = (
        resultat["Model"]
        .fillna("okänd")
    )

    resultat["Variant"] = (
        resultat["Variant"]
        .fillna("okänd")
    )

    return (
        resultat
        .sort_values(
            "Tid",
            na_position="last",
        )
        .reset_index(drop=True)
    )


def _deduplicera_dataset(
    df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Tar bort identiska snapshots utan att slå ihop olika fysiska bilar.
    """

    före = len(df)

    resultat = df.copy()

    med_identitet = (
        resultat["Identity"].notna()
    )

    nycklar = [
        "Mil",
        "ModelYear",
        "Model",
        "Variant",
        "Price",
    ]

    # Har bilen en stabil identitet ska den ingå i nyckeln.
    # Annars kan två olika bilar med samma egenskaper slås ihop.
    resultat_med_id = (
        resultat.loc[med_identitet]
        .drop_duplicates(
            subset=["Identity"] + nycklar,
            keep="last",
        )
    )

    # Saknas identitet använder vi gamla fallback-regeln.
    resultat_utan_id = (
        resultat.loc[~med_identitet]
        .drop_duplicates(
            subset=nycklar,
            keep="last",
        )
    )

    resultat = pd.concat(
        [
            resultat_med_id,
            resultat_utan_id,
        ],
        ignore_index=True,
    )

    resultat = (
        resultat
        .sort_values(
            "Tid",
            na_position="last",
        )
        .reset_index(drop=True)
    )

    efter = len(resultat)

    identiteter = int(
        resultat["Identity"]
        .notna()
        .sum()
    )

    print(
        f"Deduplicering: "
        f"{före} → {efter} "
        f"({före - efter} borttagna)"
    )

    print(
        f"Observationer med fordonsidentitet: "
        f"{identiteter}"
    )

    return resultat
