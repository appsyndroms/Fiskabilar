"""
Diagnostik för Fiskabilars ML-modell.

Normalt:
    python -m ml.analyze_model

Detaljerad diagnostik:
    python -m ml.analyze_model --debug
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

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

from ml.features import (
    FEATURES,
    FEATURES_KATEGORISK,
    FEATURES_NUMERIC,
    build_features,
)
from ml.train_market_model import (
    _bygg_dataset,
    _deduplicera_dataset,
    _ladda_jsonl,
    _tidsmässig_split,
)


MODEL_FIL = Path(
    "data/ml/market_model.joblib"
)

METADATA_FIL = Path(
    "data/ml/model_metadata.json"
)


def _skapa_preprocessor():
    numeric = Pipeline(
        steps=[
            (
                "imputer",
                SimpleImputer(
                    strategy="median"
                ),
            )
        ]
    )

    categorical = Pipeline(
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
                numeric,
                FEATURES_NUMERIC,
            ),
            (
                "categorical",
                categorical,
                FEATURES_KATEGORISK,
            ),
        ]
    )


def _modeller():
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
    prediction,
):
    actual = pd.Series(
        actual
    ).reset_index(drop=True)

    prediction = pd.Series(
        prediction
    ).reset_index(drop=True)

    error = (
        prediction
        - actual
    )

    return {
        "mae": mean_absolute_error(
            actual,
            prediction,
        ),
        "rmse": (
            mean_squared_error(
                actual,
                prediction,
            )
            ** 0.5
        ),
        "r2": r2_score(
            actual,
            prediction,
        ),
        "bias": error.mean(),
        "mape": (
            (
                error.abs()
                / actual.abs()
            )
            .replace(
                [float("inf")],
                pd.NA,
            )
            .dropna()
            .mean()
            * 100
        ),
    }


def _feature_importance(
    modell,
):
    """
    Visar Random Forests betydelse per
    faktisk feature efter one-hot encoding.
    """

    preprocessor = (
        modell.named_steps[
            "preprocessor"
        ]
    )

    forest = (
        modell.named_steps[
            "model"
        ]
    )

    names = (
        preprocessor
        .get_feature_names_out()
    )

    importances = (
        forest.feature_importances_
    )

    data = pd.DataFrame(
        {
            "feature": names,
            "importance": importances,
        }
    )

    data["base_feature"] = (
        data["feature"]
        .str.replace(
            r"^[^_]+__",
            "",
            regex=True,
        )
    )

    grouped = (
        data.groupby(
            "base_feature"
        )["importance"]
        .sum()
        .sort_values(
            ascending=False
        )
    )

    print()
    print(
        "--- FEATURE IMPORTANCE ---"
    )

    for name, value in grouped.items():
        print(
            f"{name}: "
            f"{value:.4f}"
        )


def _modell_variant_diagnostik(
    test,
    prediction,
):
    """
    Visar modellens fel uppdelat per
    bilmodell och variant.

    Diagnostiken använder samma testset
    som den vanliga modellutvärderingen.
    Den påverkar inte träningen.
    """

    diagnostik = test[
        [
            "Model",
            "Variant",
            "Price",
        ]
    ].copy()

    diagnostik["Prediction"] = (
        prediction
    )

    diagnostik["Error"] = (
        diagnostik["Prediction"]
        - diagnostik["Price"]
    )

    diagnostik["AbsoluteError"] = (
        diagnostik["Error"]
        .abs()
    )

    diagnostik["AbsolutePercentageError"] = (
        (
            diagnostik["AbsoluteError"]
            / diagnostik["Price"].abs()
        )
        * 100
    )

    grupper = []

    for (
        model_name,
        variant_name,
    ), grupp in diagnostik.groupby(
        ["Model", "Variant"],
        dropna=False,
    ):
        antal = len(grupp)

        mae = (
            grupp["AbsoluteError"]
            .mean()
        )

        mape = (
            grupp[
                "AbsolutePercentageError"
            ]
            .replace(
                [float("inf")],
                pd.NA,
            )
            .dropna()
            .mean()
        )

        bias = (
            grupp["Error"]
            .mean()
        )

        grupper.append(
            {
                "Model": model_name,
                "Variant": variant_name,
                "Antal": antal,
                "MAE": mae,
                "MAPE": mape,
                "Bias": bias,
            }
        )

    resultat = pd.DataFrame(
        grupper
    )

    if resultat.empty:
        return

    resultat = resultat.sort_values(
        "MAE",
        ascending=False,
    )

    print()
    print(
        "--- FEL PER MODELL / VARIANT ---"
    )

    for _, row in resultat.iterrows():
        print(
            f"  {row['Model']} / "
            f"{row['Variant']}: "
            f"n={int(row['Antal'])}, "
            f"MAE={row['MAE']:,.0f} kr, "
            f"MAPE={row['MAPE']:.2f}%, "
            f"Bias={row['Bias']:+,.0f} kr"
        )


def _största_felen(
    test,
    prediction,
    antal=20,
):
    """
    Visar de testobservationer där Random Forest
    har störst absoluta fel.

    Detta är en ren diagnostik och påverkar inte
    modellträningen eller vilken modell som väljs.
    """

    kolumner = [
        "Model",
        "Variant",
        "ModelYear",
        "Mil",
        "Price",
    ]

    extra_kolumner = [
        "Identity",
        "vehicle_id",
        "annons_id",
        "url",
    ]

    diagnostik = test.copy().reset_index(
        drop=True
    )

    diagnostik["Prediction"] = (
        pd.Series(prediction)
        .reset_index(drop=True)
    )

    diagnostik["Error"] = (
        diagnostik["Prediction"]
        - diagnostik["Price"]
    )

    diagnostik["AbsoluteError"] = (
        diagnostik["Error"].abs()
    )

    diagnostik = diagnostik.sort_values(
        "AbsoluteError",
        ascending=False,
    )

    tillgängliga = [
        kolumn
        for kolumn in kolumner + extra_kolumner
        if kolumn in diagnostik.columns
    ]

    tillgängliga += [
        "Prediction",
        "Error",
    ]

    resultat = diagnostik[
        tillgängliga
    ].head(antal)

    print()
    print(
        f"--- TOPP {antal} STÖRSTA FEL ---"
    )

    for _, row in resultat.iterrows():
        model = row.get(
            "Model",
            "?",
        )

        variant = row.get(
            "Variant",
            "?",
        )

        model_year = row.get(
            "ModelYear",
            "?",
        )

        mil = row.get(
            "Mil",
            "?",
        )

        price = row.get(
            "Price",
            float("nan"),
        )

        prediction_value = row.get(
            "Prediction",
            float("nan"),
        )

        error = row.get(
            "Error",
            float("nan"),
        )

        identity = row.get(
            "Identity",
            "",
        )

        url = row.get(
            "url",
            "",
        )

        print(
            f"  {model} / {variant} | "
            f"år={model_year} | "
            f"mil={mil} | "
            f"pris={price:,.0f} kr | "
            f"prognos={prediction_value:,.0f} kr | "
            f"fel={error:+,.0f} kr"
        )

        if identity:
            print(
                f"    Identity: {identity}"
            )

        if url:
            print(
                f"    URL: {url}"
            )


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--debug",
        action="store_true",
        help="Visa detaljerad diagnostik.",
    )

    args = parser.parse_args()

    if not args.debug:
        return

    print(
        "=========================================="
    )

    print(
        "FISKABILAR ML-DIAGNOSTIK"
    )

    print(
        "=========================================="
    )

    rådata = _ladda_jsonl()

    print()
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

    print()
    print(
        "--- DATASET ---"
    )

    print(
        f"Observationer: "
        f"{len(dataset)}"
    )

    print(
        f"Modeller: "
        f"{dataset['Model'].nunique()}"
    )

    print(
        f"Varianter: "
        f"{dataset['Variant'].nunique()}"
    )

    print()
    print(
        "Observationer per modell:"
    )

    for name, count in (
        dataset["Model"]
        .value_counts()
        .items()
    ):
        print(
            f"  {name}: {count}"
        )

    train, test = (
        _tidsmässig_split(
            dataset
        )
    )

    print()
    print(
        "--- TRAIN / TEST ---"
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
        f"Träningsmedelpris: "
        f"{train['Price'].mean():,.0f} kr"
    )

    print(
        f"Testmedelpris: "
        f"{test['Price'].mean():,.0f} kr"
    )

    print()
    print(
        "--- FEATURES ---"
    )

    for feature in FEATURES:
        print(
            f"  {feature}"
        )

    print()
    print(
        "--- MODELLJÄMFÖRELSE ---"
    )

    resultat = {}

    for name, model in (
        _modeller().items()
    ):

        model.fit(
            build_features(
                train
            ),
            train["Price"],
        )

        prediction = (
            model.predict(
                build_features(
                    test
                )
            )
        )

        metrics = _metrics(
            test["Price"],
            prediction,
        )

        resultat[
            name
        ] = metrics

        print()
        print(
            f"--- {name} ---"
        )

        print(
            f"MAE: "
            f"{metrics['mae']:,.0f} kr"
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
            f"{metrics['bias']:+,.0f} kr"
        )

        print(
            f"MAPE: "
            f"{metrics['mape']:.2f}%"
        )

        if name == "random_forest":
            _feature_importance(
                model
            )

            _modell_variant_diagnostik(
                test,
                prediction,
            )

            _största_felen(
                test,
                prediction,
            )

    vald = min(
        resultat,
        key=lambda name:
            resultat[name]["mae"],
    )

    print()
    print(
        "=========================================="
    )

    print(
        f"Vinnare enligt MAE: "
        f"{vald}"
    )

    print(
        "=========================================="
    )

    if MODEL_FIL.exists():
        saved_model = joblib.load(
            MODEL_FIL
        )

        print()
        print(
            "--- SPARAD MODELL ---"
        )

        if hasattr(
            saved_model,
            "named_steps",
        ):
            model_step = (
                saved_model
                .named_steps
                .get("model")
            )

            if model_step is not None:
                print(
                    f"Typ: "
                    f"{type(model_step).__name__}"
                )

    if METADATA_FIL.exists():

        with METADATA_FIL.open(
            "r",
            encoding="utf-8",
        ) as file:

            metadata = json.load(
                file
            )

        print()
        print(
            "--- METADATA ---"
        )

        print(
            f"Vald modell: "
            f"{metadata.get('model')}"
        )

        print(
            f"Antal features: "
            f"{len(metadata.get('features', []))}"
        )

    print()
    print(
        "DIAGNOSTIK KLAR"
    )


if __name__ == "__main__":
    main()
