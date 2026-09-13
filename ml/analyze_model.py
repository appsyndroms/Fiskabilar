import argparse
import json
from datetime import datetime, timezone
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
)

from ml.model_diagnostics import (
    _diagnostik_330e_historik,
    _diagnostik_per_modell,
    _feature_importance,
    _metrics,
    _modell_variant_diagnostik,
    _största_felen,
)

from ml.fynddetektor import (
    detektera_fynd,
)

from ml.fynd_export import (
    exportera_fynd,
)


MODEL_FIL = Path(
    "data/ml/market_model.joblib"
)

METADATA_FIL = Path(
    "data/ml/model_metadata.json"
)


def _tidsmässig_split(
    dataset,
    testandel=0.2,
):
    """
    Delar datasetet tidsmässigt.

    Äldre observationer används för träning och de
    senaste observationerna används för test.

    Detta undviker att framtida observationer läcker
    in i träningsdata.
    """

    if dataset.empty:
        raise ValueError(
            "Datasetet är tomt."
        )

    if not 0 < testandel < 1:
        raise ValueError(
            "testandel måste ligga mellan 0 och 1."
        )

    dataset = (
        dataset
        .sort_values(
            "Tid",
            na_position="last",
        )
        .reset_index(drop=True)
    )

    split_index = int(
        len(dataset) * (1 - testandel)
    )

    split_index = max(
        1,
        min(
            split_index,
            len(dataset) - 1,
        ),
    )

    train = (
        dataset
        .iloc[:split_index]
        .copy()
    )

    test = (
        dataset
        .iloc[split_index:]
        .copy()
    )

    print(
        "\nTidsmässig split:"
    )

    print(
        f"Träning: {len(train)} observationer"
    )

    print(
        f"Test: {len(test)} observationer"
    )

    return train, test


def _skapa_preprocessor() -> ColumnTransformer:

    numeric_pipeline = Pipeline(
        steps=[
            (
                "imputer",
                SimpleImputer(
                    strategy="median"
                ),
            ),
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
        help=(
            "Kör diagnostik av tränad "
            "marknadsmodell."
        ),
    )

    args = parser.parse_args()

    if not args.debug:
        return

    observations = _ladda_jsonl()

    dataset = _bygg_dataset(
        observations
    )

    dataset = _deduplicera_dataset(
        dataset
    )

    train, test = _tidsmässig_split(
        dataset
    )

    X_train = build_features(
        train
    )

    X_test = build_features(
        test
    )

    y_train = train["Price"]

    y_test = test["Price"]

    modeller = _modeller()

    resultat = {}

    for namn, model in modeller.items():

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

    rf = resultat[
        "random_forest"
    ]

    importance = _feature_importance(
        rf["model"]
    )

    if importance is not None:

        print(
            "\nRandom Forest feature importance:"
        )

        print(
            importance.to_string(
                index=False,
                formatters={
                    "importance":
                        lambda x:
                        f"{x:.4f}"
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

    # --------------------------------------------------------
    # FYNDEKTION + EXPORT
    # --------------------------------------------------------

    fynd = detektera_fynd(
        dataset,
        test,
        rf["prediction"],
    )

    exportera_fynd(
        fynd
    )

    # --------------------------------------------------------
    # VINNANDE MODELL
    # --------------------------------------------------------

    winner = min(
        resultat.items(),
        key=lambda item:
            item[1]["metrics"]["MAE"],
    )

    winner_name = winner[0]

    winner_model = winner[1]["model"]

    MODEL_FIL.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    joblib.dump(
        winner_model,
        MODEL_FIL,
    )

    # Metadata används av webbappen.
    #
    # observations = hela datasetet efter deduplicering.
    # training_rows = den del som faktiskt används för träning.
    # test_rows = den del som används för utvärdering.
    # trained_at = exakt tidpunkt då modellen tränades.
    metadata = {
        "model_type": winner_name,
        "features": FEATURES,
        "metrics": winner[1]["metrics"],
        "trained_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "observations": int(
            len(dataset)
        ),
        "training_rows": int(
            len(train)
        ),
        "test_rows": int(
            len(test)
        ),
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


if __name__ == "__main__":
    main()
