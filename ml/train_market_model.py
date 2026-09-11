"""
Träning av datadriven marknadsvärdering.

Modellen tränas på sparad historik i:

    data/market_history/*.jsonl

Målvariabel:
    Price = annonspris

Features:
    - Mil
    - ModelYear
    - Model
    - Variant

Två modeller testas:

    1. Linjär regression
    2. Random Forest

Random Forest används som slutlig modell om den ger bättre
R² än linjär regression.

Resultatet sparas i:

    data/ml/market_model.joblib
    data/ml/model_metadata.json
"""

from __future__ import annotations

import argparse
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
from sklearn.metrics import (
    mean_absolute_error,
    mean_squared_error,
    r2_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder


TIDSZON = ZoneInfo("Europe/Stockholm")

HISTORIK_DIR = Path("data/market_history")
OUTPUT_DIR = Path("data/ml")

MODEL_FIL = OUTPUT_DIR / "market_model.joblib"
METADATA_FIL = OUTPUT_DIR / "model_metadata.json"

MIN_TRAINING_OBSERVATIONER = 30

FEATURES_NUMERIC = [
    "Mil",
    "ModelYear",
]

FEATURES_KATEGORISK = [
    "Model",
    "Variant",
]

FEATURES = (
    FEATURES_NUMERIC
    + FEATURES_KATEGORISK
)

TARGET = "Price"


def _normalisera_text(value) -> str | None:
    """Normaliserar ett textfält."""

    if value is None:
        return None

    text = str(value).strip()

    if not text:
        return None

    return text


def _ladda_jsonl() -> pd.DataFrame:
    """Läser all sparad marknadshistorik."""

    filer = sorted(
        HISTORIK_DIR.glob("market_history_*.jsonl")
    )

    legacy = (
        HISTORIK_DIR
        / "market_history.jsonl"
    )

    if legacy.exists():
        filer.append(legacy)

    if not filer:
        raise FileNotFoundError(
            f"Ingen marknadshistorik hittades i "
            f"{HISTORIK_DIR}"
        )

    poster = []

    for fil in filer:
        with fil.open(
            "r",
            encoding="utf-8",
        ) as f:
            for radnummer, rad in enumerate(
                f,
                start=1,
            ):
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
                    post["_historikfil"] = fil.name
                    poster.append(post)

    if not poster:
        raise ValueError(
            "Historikfilerna innehåller inga "
            "giltiga JSONL-poster."
        )

    return pd.DataFrame(poster)


def _bygg_dataset(
    df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Bygger träningsdataset från rå historik.

    Marknadshistoriken använder:

        modell
        variant
        arsmodell
        miltal
        annonspris
        tid
    """

    resultat = pd.DataFrame()

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
        .apply(_normalisera_text)
    )

    resultat["Variant"] = (
        df.get("variant")
        .apply(_normalisera_text)
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
        .fillna("Okänd")
    )

    resultat["Variant"] = (
        resultat["Variant"]
        .fillna("Okänd")
    )

    resultat = resultat.sort_values(
        "Tid",
        na_position="last",
    ).reset_index(drop=True)

    return resultat


def _deduplicera_dataset(
    df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Tar bort exakta dubbletter.

    Samma bil kan finnas i flera observationer.
    Vi tar bara bort identiska observationer här.
    """

    nycklar = [
        "Mil",
        "ModelYear",
        "Model",
        "Variant",
        "Price",
    ]

    return (
        df.drop_duplicates(
            subset=nycklar
        )
        .reset_index(drop=True)
    )


def _skapa_preprocessor() -> ColumnTransformer:
    """Skapar preprocessing för modellerna."""

    numeric_pipeline = Pipeline(
        steps=[
            (
                "imputer",
                SimpleImputer(
                    strategy="median"
                ),
            )
        ]
    )

    categorical_pipeline = Pipeline(
        steps=[
            (
                "imputer",
                SimpleImputer(
                    strategy="most_frequent"
                ),
            ),
            (
                "onehot",
                OneHotEncoder(
                    handle_unknown="ignore"
                ),
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


def _bygg_modeller() -> dict[str, Pipeline]:
    """Returnerar modellerna som ska jämföras."""

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
                        n_estimators=300,
                        max_depth=None,
                        min_samples_leaf=2,
                        random_state=42,
                        n_jobs=-1,
                    ),
                ),
            ]
        ),
    }


def _beräkna_metrics(
    faktiskt: pd.Series,
    predikterat,
) -> dict:
    """Beräknar modellens felstatistik."""

    faktiskt = pd.Series(
        faktiskt,
        dtype="float64",
    ).reset_index(drop=True)

    predikterat = pd.Series(
        predikterat,
        dtype="float64",
    ).reset_index(drop=True)

    fel = (
        predikterat
        - faktiskt
    )

    absolut_fel = fel.abs()

    procent_fel = (
        absolut_fel
        / faktiskt.replace(0, pd.NA)
        * 100
    )

    return {
        "antal_observationer": int(
            len(faktiskt)
        ),
        "mae": round(
            float(
                mean_absolute_error(
                    faktiskt,
                    predikterat,
                )
            ),
            2,
        ),
        "medianfel": round(
            float(
                fel.median()
            ),
            2,
        ),
        "median_absolutfel": round(
            float(
                absolut_fel.median()
            ),
            2,
        ),
        "mape_procent": round(
            float(
                procent_fel
                .dropna()
                .mean()
            ),
            2,
        ),
        "rmse": round(
            float(
                mean_squared_error(
                    faktiskt,
                    predikterat,
                )
                ** 0.5
            ),
            2,
        ),
        "r2": round(
            float(
                r2_score(
                    faktiskt,
                    predikterat,
                )
            ),
            4,
        ),
        "faktiskt_medelpris": round(
            float(
                faktiskt.mean()
            ),
            2,
        ),
        "predikterat_medelpris": round(
            float(
                predikterat.mean()
            ),
            2,
        ),
        "bias": round(
            float(
                fel.mean()
            ),
            2,
        ),
    }


def _utvärdera_per_grupp(
    test: pd.DataFrame,
    prediktioner,
    kolumn: str,
) -> dict:
    """Beräknar resultat per modellgrupp."""

    data = test[
        [
            kolumn,
            TARGET,
        ]
    ].copy()

    data["_prediktion"] = prediktioner

    resultat = {}

    for grupp, gruppdata in (
        data.groupby(
            kolumn,
            dropna=False,
        )
    ):
        if pd.isna(grupp):
            gruppnamn = "Okänd"
        else:
            gruppnamn = str(grupp)

        resultat[gruppnamn] = (
            _beräkna_metrics(
                gruppdata[TARGET],
                gruppdata["_prediktion"],
            )
        )

    return resultat


def _utvärdera(
    modell: Pipeline,
    test: pd.DataFrame,
) -> dict:
    """Beräknar fullständig modellstatistik."""

    x_test = test[FEATURES]
    y_test = test[TARGET]

    prediktioner = modell.predict(
        x_test
    )

    return {
        "totalt": _beräkna_metrics(
            y_test,
            prediktioner,
        ),
        "per_modell": _utvärdera_per_grupp(
            test,
            prediktioner,
            "Model",
        ),
        "per_variant": _utvärdera_per_grupp(
            test,
            prediktioner,
            "Variant",
        ),
        "per_årsmodell": _utvärdera_per_grupp(
            test,
            prediktioner,
            "ModelYear",
        ),
    }


def _skriv_ut_metrics(
    namn: str,
    metrics: dict,
) -> None:
    """Skriver modellresultat."""

    totalt = metrics["totalt"]

    print()
    print(
        f"=== {namn} ==="
    )

    print(
        f"Observationer: "
        f"{totalt['antal_observationer']}"
    )

    print(
        f"MAE: "
        f"{totalt['mae']:,.0f} kr"
    )

    print(
        f"Medianfel: "
        f"{totalt['medianfel']:,.0f} kr"
    )

    print(
        f"MAPE: "
        f"{totalt['mape_procent']:.2f} %"
    )

    print(
        f"RMSE: "
        f"{totalt['rmse']:,.0f} kr"
    )

    print(
        f"R²: "
        f"{totalt['r2']:.4f}"
    )

    print(
        f"Faktiskt medelpris: "
        f"{totalt['faktiskt_medelpris']:,.0f} kr"
    )

    print(
        f"Predikterat medelpris: "
        f"{totalt['predikterat_medelpris']:,.0f} kr"
    )

    print(
        f"Bias: "
        f"{totalt['bias']:,.0f} kr"
    )


def _tidsmässig_split(
    df: pd.DataFrame,
    test_andel: float = 0.20,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Delar datasetet tidsmässigt.

    De äldsta observationerna används för träning.
    De nyaste används för test.
    """

    df = df.sort_values(
        "Tid",
        na_position="first",
    ).reset_index(drop=True)

    antal = len(df)

    test_antal = max(
        1,
        int(
            round(
                antal * test_andel
            )
        ),
    )

    train_antal = (
        antal - test_antal
    )

    if train_antal < MIN_TRAINING_OBSERVATIONER:
        raise ValueError(
            "För få träningsobservationer. "
            f"Minst {MIN_TRAINING_OBSERVATIONER} "
            f"krävs."
        )

    train = df.iloc[
        :train_antal
    ].copy()

    test = df.iloc[
        train_antal:
    ].copy()

    if test.empty:
        raise ValueError(
            "Testdatasetet blev tomt."
        )

    return train, test


def _metadata(
    vald_modell: str,
    dataset: pd.DataFrame,
    train: pd.DataFrame,
    test: pd.DataFrame,
    metrics: dict,
) -> dict:
    """Bygger metadatafilen."""

    return {
        "skapad": datetime.now(
            TIDSZON
        ).isoformat(),
        "modell": vald_modell,
        "features": FEATURES,
        "target": TARGET,
        "antal_observationer": int(
            len(dataset)
        ),
        "antal_traning": int(
            len(train)
        ),
        "antal_test": int(
            len(test)
        ),
        "metrics": metrics,
        "historik_dir": str(
            HISTORIK_DIR
        ),
    }


def träna(
    verbose: bool = True,
) -> dict:
    """Tränar, utvärderar och sparar modellen."""

    rådata = _ladda_jsonl()

    dataset = _bygg_dataset(
        rådata
    )

    dataset = _deduplicera_dataset(
        dataset
    )

    if len(dataset) < MIN_TRAINING_OBSERVATIONER:
        raise ValueError(
            "För få användbara observationer: "
            f"{len(dataset)}. "
            f"Minst {MIN_TRAINING_OBSERVATIONER} krävs."
        )

    train, test = _tidsmässig_split(
        dataset
    )

    x_train = train[FEATURES]
    y_train = train[TARGET]

    modeller = _bygg_modeller()

    metrics = {}

    for namn, modell in modeller.items():
        modell.fit(
            x_train,
            y_train,
        )

        metrics[namn] = _utvärdera(
            modell,
            test,
        )

        if verbose:
            _skriv_ut_metrics(
                namn,
                metrics[namn],
            )

    vald_modell = max(
        metrics,
        key=lambda namn: (
            metrics[namn]["totalt"]["r2"]
        ),
    )

    slutlig_modell = modeller[
        vald_modell
    ]

    slutlig_modell.fit(
        dataset[FEATURES],
        dataset[TARGET],
    )

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    joblib.dump(
        slutlig_modell,
        MODEL_FIL,
    )

    metadata = _metadata(
        vald_modell,
        dataset,
        train,
        test,
        metrics,
    )

    METADATA_FIL.write_text(
        json.dumps(
            metadata,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print()
    print(
        "=========================================="
    )
    print(
        f"Vald modell: {vald_modell}"
    )
    print(
        f"Modell sparad: {MODEL_FIL}"
    )
    print(
        f"Metadata sparad: {METADATA_FIL}"
    )
    print(
        "=========================================="
    )

    return metadata


def main() -> None:
    """CLI-entrypoint."""

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Minska utskriften.",
    )

    args = parser.parse_args()

    träna(
        verbose=not args.quiet
    )


if __name__ == "__main__":
    main()
