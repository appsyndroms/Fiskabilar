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
    ):
        value = row.get(field)

        if pd.notna(value) and str(value).strip():
            return f"{field}:{str(value).strip()}"

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


def _skapa_preprocessor():
    numeric_pipeline = Pipeline(
        steps=[
            (
                "imputer",
                SimpleImputer(
                    strategy="median"
                )
            )
        ]
    )

    categorical_pipeline = Pipeline(
        steps=[
            (
                "imputer",
                SimpleImputer(
                    strategy="most_frequent"
                )
            ),
            (
                "onehot",
                OneHotEncoder(
                    handle_unknown="ignore"
                )
            ),
        ]
    )

    return ColumnTransformer(
        transformers=[
            (
                "numeric",
                numeric_pipeline,
                FEATURES_NUMERIC,
            ),
            (
                "categorical",
                categorical_pipeline,
                FEATURES_KATEGORISK,
            ),
        ]
    )


def _bygg_modeller():
    return {
        "linear_regression": Pipeline(
            steps=[
                (
                    "preprocessor",
                    _skapa_preprocessor(),
                ),
                (
                    "model",
                    LinearRegression(),
                ),
            ]
        ),
        "random_forest": Pipeline(
            steps=[
                (
                    "preprocessor",
                    _skapa_preprocessor(),
                ),
                (
                    "model",
                    RandomForestRegressor(
                        n_estimators=400,
                        max_depth=None,
                        min_samples_leaf=2,
                        random_state=42,
                        n_jobs=-1,
                    ),
                ),
            ]
        ),
    }


def _metrics(
    actual,
    predicted,
) -> dict:

    actual = (
        pd.Series(
            actual,
            dtype="float64",
        )
        .reset_index(drop=True)
    )

    predicted = (
        pd.Series(
            predicted,
            dtype="float64",
        )
        .reset_index(drop=True)
    )

    error = (
        predicted - actual
    )

    absolute_error = error.abs()

    percentage_error = (
        absolute_error
        / actual.replace(0, pd.NA)
        * 100
    )

    return {
        "antal_observationer": int(
            len(actual)
        ),
        "mae": round(
            float(
                mean_absolute_error(
                    actual,
                    predicted,
                )
            ),
            2,
        ),
        "median_absolutfel": round(
            float(
                absolute_error.median()
            ),
            2,
        ),
        "mape_procent": round(
            float(
                percentage_error
                .dropna()
                .mean()
            ),
            2,
        ),
        "rmse": round(
            float(
                mean_squared_error(
                    actual,
                    predicted,
                )
                ** 0.5
            ),
            2,
        ),
        "r2": round(
            float(
                r2_score(
                    actual,
                    predicted,
                )
            ),
            4,
        ),
        "bias": round(
            float(error.mean()),
            2,
        ),
        "faktiskt_medelpris": round(
            float(actual.mean()),
            2,
        ),
        "predikterat_medelpris": round(
            float(predicted.mean()),
            2,
        ),
    }


def _tidsmässig_split(
    df: pd.DataFrame,
    test_andel: float = 0.20,
    return_diagnostics: bool = False,
):
    """
    Tidsmässig split där samma identifierade bil
    inte hamnar i både train och test.

    De senaste observationerna används som preliminärt test.
    Om ett identifierat fordon också finns tidigare i train
    flyttas de tidigare observationerna till test. Det gör
    utvärderingen fordonsseparerad, men testmängden kan då
    innehålla historiska observationer.
    """

    df = (
        df
        .sort_values(
            "Tid",
            na_position="first",
        )
        .reset_index(drop=True)
    )

    test_antal = max(
        1,
        int(
            round(
                len(df)
                * test_andel
            )
        ),
    )

    cutoff = (
        len(df)
        - test_antal
    )

    prelim_test = (
        df.iloc[cutoff:]
        .copy()
    )

    test_id = set(
        prelim_test["Identity"]
        .dropna()
    )

    flytta = df.iloc[0:0].copy()

    if test_id:
        train = (
            df.iloc[:cutoff]
            .copy()
        )

        flytta = train[
            train["Identity"]
            .isin(test_id)
        ].copy()

        train = train[
            ~train["Identity"]
            .isin(test_id)
        ].copy()

        test = pd.concat(
            [
                flytta,
                prelim_test,
            ],
            ignore_index=True,
        )

    else:
        train = (
            df.iloc[:cutoff]
            .copy()
        )

        test = prelim_test

    if len(train) < MIN_TRAINING_OBSERVATIONER:
        raise ValueError(
            "För få träningsobservationer."
        )

    train = train.reset_index(drop=True)
    test = test.reset_index(drop=True)

    if not return_diagnostics:
        return train, test

    train_id = set(
        train["Identity"]
        .dropna()
    )

    final_test_id = set(
        test["Identity"]
        .dropna()
    )

    overlap = train_id & final_test_id

    diagnostics = {
        "test_andel": test_andel,
        "prelim_test_observationer": len(prelim_test),
        "historiska_observationer_flyttade_till_test": len(flytta),
        "train_observationer": len(train),
        "test_observationer": len(test),
        "unika_identifierade_fordon_totalt": int(
            df["Identity"].nunique(dropna=True)
        ),
        "unika_identifierade_fordon_train": len(train_id),
        "unika_identifierade_fordon_test": len(final_test_id),
        "fordon_i_bade_train_och_test": len(overlap),
        "train_tid_min": (
            train["Tid"].min().isoformat()
            if train["Tid"].notna().any()
            else None
        ),
        "train_tid_max": (
            train["Tid"].max().isoformat()
            if train["Tid"].notna().any()
            else None
        ),
        "test_tid_min": (
            test["Tid"].min().isoformat()
            if test["Tid"].notna().any()
            else None
        ),
        "test_tid_max": (
            test["Tid"].max().isoformat()
            if test["Tid"].notna().any()
            else None
        ),
    }

    if overlap:
        raise ValueError(
            "Split-fel: samma identifierade fordon finns i både "
            f"train och test ({len(overlap)} st)."
        )

    return train, test, diagnostics


def _utvärdera(
    modell,
    test,
):
    prediction = modell.predict(
        build_features(test)
    )

    return _metrics(
        test[TARGET],
        prediction,
    )


def _skriv_metrics(
    namn,
    metrics,
):
    print()
    print(
        f"=== {namn} ==="
    )

    print(
        f"Observationer: "
        f"{metrics['antal_observationer']}"
    )

    print(
        f"MAE: "
        f"{metrics['mae']:,.0f} kr"
    )

    print(
        f"Median absolutfel: "
        f"{metrics['median_absolutfel']:,.0f} kr"
    )

    print(
        f"MAPE: "
        f"{metrics['mape_procent']:.2f} %"
    )

    print(
        f"RMSE: "
        f"{metrics['rmse']:,.0f} kr"
    )

    print(
        f"R²: "
        f"{metrics['r2']:.4f}"
    )

    print(
        f"Bias: "
        f"{metrics['bias']:,.0f} kr"
    )


def main():
    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    rådata = _ladda_jsonl()

    print(
        f"Råa observationer: "
        f"{len(rådata)}"
    )

    dataset = _bygg_dataset(
        rådata
    )

    dataset = _deduplicera_dataset(
        dataset
    )

    train, test, split_diagnostics = (
        _tidsmässig_split(
            dataset,
            return_diagnostics=True,
        )
    )

    print()
    print(
        "=== DATASET ==="
    )

    print(
        f"Observationer: "
        f"{len(dataset)}"
    )

    print(
        f"Träning: "
        f"{len(train)}"
    )

    print(
        f"Test: "
        f"{len(test)}"
    )

    print(
        f"Unika identifierade fordon: "
        f"{dataset['Identity'].nunique(dropna=True)}"
    )

    print()
    print(
        "=== SPLIT-DIAGNOSTIK ==="
    )

    print(
        f"Preliminärt test: "
        f"{split_diagnostics['prelim_test_observationer']}"
    )

    print(
        f"Historiska observationer flyttade till test: "
        f"{split_diagnostics['historiska_observationer_flyttade_till_test']}"
    )

    print(
        f"Unika fordon totalt: "
        f"{split_diagnostics['unika_identifierade_fordon_totalt']}"
    )

    print(
        f"Unika fordon train: "
        f"{split_diagnostics['unika_identifierade_fordon_train']}"
    )

    print(
        f"Unika fordon test: "
        f"{split_diagnostics['unika_identifierade_fordon_test']}"
    )

    print(
        f"Fordon i både train och test: "
        f"{split_diagnostics['fordon_i_bade_train_och_test']}"
    )

    print(
        f"Train tidsintervall: "
        f"{split_diagnostics['train_tid_min']} → "
        f"{split_diagnostics['train_tid_max']}"
    )

    print(
        f"Test tidsintervall: "
        f"{split_diagnostics['test_tid_min']} → "
        f"{split_diagnostics['test_tid_max']}"
    )

    print()
    print(
        "Nya features:"
    )

    for feature in FEATURES:
        print(
            f"  {feature}"
        )

    modeller = _bygg_modeller()

    resultat = {}

    for namn, modell in (
        modeller.items()
    ):
        modell.fit(
            build_features(train),
            train[TARGET],
        )

        metrics = _utvärdera(
            modell,
            test,
        )

        resultat[namn] = metrics

        _skriv_metrics(
            namn,
            metrics,
        )

    vald_modell = min(
        resultat,
        key=lambda namn:
            resultat[namn]["mae"],
    )

    slutmodell = modeller[
        vald_modell
    ]

    slutmodell.fit(
        build_features(dataset),
        dataset[TARGET],
    )

    joblib.dump(
        slutmodell,
        MODEL_FIL,
    )

    metadata = {
        "model": vald_modell,
        "selection_metric": "mae",
        "features": FEATURES,
        "numeric_features": FEATURES_NUMERIC,
        "categorical_features": FEATURES_KATEGORISK,
        "dataset_observations": len(dataset),
        "train_observations": len(train),
        "test_observations": len(test),
        "unique_identified_vehicles": int(
            dataset["Identity"]
            .nunique(dropna=True)
        ),
        "split_diagnostics": split_diagnostics,
        "metrics": resultat,
        "deduplication": {
            "uses_vehicle_identity": True,
            "fallback_without_identity": [
                "Mil",
                "ModelYear",
                "Model",
                "Variant",
                "Price",
            ],
            "grouped_vehicle_split": True,
            "test_contains_moved_historical_observations": (
                split_diagnostics[
                    "historiska_observationer_flyttade_till_test"
                ] > 0
            ),
        },
        "trained_at": datetime.now(
            TIDSZON
        ).isoformat(),
    }

    with METADATA_FIL.open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            metadata,
            file,
            ensure_ascii=False,
            indent=2,
        )

    print()
    print(
        "=========================================="
    )

    print(
        f"Vald modell: "
        f"{vald_modell}"
    )

    print(
        "Urvalsprincip: lägst MAE"
    )

    print(
        f"Modell sparad: "
        f"{MODEL_FIL}"
    )

    print(
        f"Metadata sparad: "
        f"{METADATA_FIL}"
    )

    print(
        "=========================================="
    )


if __name__ == "__main__":
    main()
