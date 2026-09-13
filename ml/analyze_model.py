import argparse
import json
from pathlib import Path

import joblib
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LinearRegression
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
from ml.model_diagnostics import (
    _diagnostik_330e_historik,
    _diagnostik_per_modell,
    _feature_importance,
    _metrics,
    _modell_variant_diagnostik,
    _största_felen,
)
from ml.comparable_market import (
    _diagnostik_jämförbar_marknad,
)
from ml.fynddetektor import (
    detektera_fynd,
)


MODEL_FIL = Path("data/ml/market_model.joblib")
METADATA_FIL = Path("data/ml/model_metadata.json")


def _skapa_preprocessor() -> ColumnTransformer:
    numeric_pipeline = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="median")),
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
        ],
        remainder="drop",
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


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--debug",
        action="store_true",
        help="Kör diagnostik av tränad marknadsmodell.",
    )

    args = parser.parse_args()

    if not args.debug:
        return

    print("Laddar marknadsdata...")

    observations = _ladda_jsonl()

    print(
        f"Råa observationer: "
        f"{len(observations):,}"
    )

    dataset = _bygg_dataset(observations)

    print(
        f"Dataset före deduplicering: "
        f"{len(dataset):,}"
    )

    dataset = _deduplicera_dataset(dataset)

    print(
        f"Dataset efter deduplicering: "
        f"{len(dataset):,}"
    )

    train, test = _tidsmässig_split(dataset)

    print(f"Train: {len(train):,}")
    print(f"Test:  {len(test):,}")

    X_train = build_features(train)
    X_test = build_features(test)

    y_train = train["Price"]
    y_test = test["Price"]

    modeller = _modeller()

    resultat = {}

    for namn, model in modeller.items():
        print(f"\nTränar {namn}...")

        model.fit(
            X_train,
            y_train,
        )

        prediction = model.predict(
            X_test
        )

        metrics = _metrics(
            y_test,
            prediction,
        )

        resultat[namn] = {
            "model": model,
            "prediction": prediction,
            "metrics": metrics,
        }

        print(f"\n{namn}:")

        for key, value in metrics.items():
            if key == "R2":
                print(
                    f"  {key}: "
                    f"{value:.4f}"
                )
            elif key == "MAPE":
                print(
                    f"  {key}: "
                    f"{value:.2f} %"
                )
            else:
                print(
                    f"  {key}: "
                    f"{value:,.0f} kr"
                )

    rf = resultat["random_forest"]

    print(
        "\nRandom Forest feature importance:"
    )

    importance = _feature_importance(
        rf["model"]
    )

    if importance is not None:
        print(
            importance.to_string(
                index=False,
                formatters={
                    "importance":
                        lambda x: f"{x:.4f}"
                },
            )
        )

    _modell_variant_diagnostik(
        test,
        rf["prediction"],
    )

    _största_felen(
        test,
        rf["prediction"],
        antal=20,
    )

    _diagnostik_per_modell(
        test,
        rf["prediction"],
    )

    _diagnostik_330e_historik(
        dataset,
        test,
        rf["prediction"],
    )

    _diagnostik_jämförbar_marknad(
        dataset,
        test,
        rf["prediction"],
    )

    detektera_fynd(
        dataset,
        test,
        rf["prediction"],
    )

    winner = min(
        resultat.items(),
        key=lambda item:
            item[1]["metrics"]["MAE"],
    )

    winner_name = winner[0]
    winner_model = winner[1]["model"]

    print(
        f"\nVinnande modell: "
        f"{winner_name}"
    )

    MODEL_FIL.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    joblib.dump(
        winner_model,
        MODEL_FIL,
    )

    metadata = {
        "model_type": winner_name,
        "features": FEATURES,
        "metrics": winner[1]["metrics"],
    }

    with METADATA_FIL.open(
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            metadata,
            f,
            ensure_ascii=False,
            indent=2,
        )

    print(
        f"Modell sparad: "
        f"{MODEL_FIL}"
    )

    print(
        f"Metadata sparad: "
        f"{METADATA_FIL}"
    )


if __name__ == "__main__":
    main()
