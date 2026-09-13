import argparse
import json
from pathlib import Path

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
    build_features,
)
from ml.train_market_model import (
    _bygg_dataset,
    _deduplicera_dataset,
    _ladda_jsonl,
    _tidsmässig_split,
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
            ("imputer", SimpleImputer(strategy="most_frequent")),
            ("onehot", OneHotEncoder(handle_unknown="ignore")),
        ]
    )

    return ColumnTransformer(
        transformers=[
            ("numeric", numeric_pipeline, FEATURES_NUMERIC),
            ("categorical", categorical_pipeline, FEATURES_KATEGORISK),
        ],
        remainder="drop",
    )


def _modeller():
    return {
        "linear_regression": Pipeline(
            steps=[
                ("preprocessor", _skapa_preprocessor()),
                ("model", LinearRegression()),
            ]
        ),
        "random_forest": Pipeline(
            steps=[
                ("preprocessor", _skapa_preprocessor()),
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


def _metrics(y_true, y_pred):
    y_true = pd.Series(y_true).reset_index(drop=True)
    y_pred = pd.Series(y_pred).reset_index(drop=True)

    errors = y_pred - y_true

    non_zero = y_true != 0

    return {
        "MAE": mean_absolute_error(y_true, y_pred),
        "RMSE": mean_squared_error(y_true, y_pred) ** 0.5,
        "R2": r2_score(y_true, y_pred),
        "Bias": errors.mean(),
        "MAPE": (
            (errors[non_zero].abs() / y_true[non_zero].abs()).mean() * 100
            if non_zero.any()
            else float("nan")
        ),
    }


def _feature_importance(model):
    preprocessor = model.named_steps["preprocessor"]
    estimator = model.named_steps["model"]

    try:
        feature_names = preprocessor.get_feature_names_out()
        importances = estimator.feature_importances_
    except AttributeError:
        return None

    rows = []

    for feature_name, importance in zip(feature_names, importances):
        rows.append(
            {
                "feature": feature_name,
                "importance": importance,
            }
        )

    result = pd.DataFrame(rows)

    if result.empty:
        return result

    def base_feature(name):
        name = name.replace("numeric__", "")
        name = name.replace("categorical__", "")

        for feature in FEATURES:
            if name == feature or name.startswith(feature + "_"):
                return feature

        return name

    result["base_feature"] = result["feature"].map(base_feature)

    grouped = (
        result.groupby("base_feature", as_index=False)["importance"]
        .sum()
        .sort_values("importance", ascending=False)
    )

    return grouped


def _skapa_diagnostik(test, prediction):
    diagnostik = test.copy().reset_index(drop=True)

    diagnostik["Prediction"] = (
        pd.Series(prediction).reset_index(drop=True)
    )

    diagnostik["Error"] = (
        diagnostik["Prediction"] - diagnostik["Price"]
    )

    diagnostik["AbsoluteError"] = diagnostik["Error"].abs()

    diagnostik["AbsolutePercentageError"] = (
        diagnostik["AbsoluteError"]
        / diagnostik["Price"].abs()
        * 100
    )

    return diagnostik


def _modell_variant_diagnostik(test, prediction):
    diagnostik = _skapa_diagnostik(test, prediction)

    if "Model" in diagnostik.columns and "Variant" in diagnostik.columns:
        group_columns = ["Model", "Variant"]
    elif "Model" in diagnostik.columns:
        group_columns = ["Model"]
    else:
        return

    grupper = []

    for keys, group in diagnostik.groupby(group_columns):
        if not isinstance(keys, tuple):
            keys = (keys,)

        grupper.append(
            {
                "Model": keys[0],
                "Variant": keys[1] if len(keys) > 1 else "",
                "n": len(group),
                "MAE": group["AbsoluteError"].mean(),
                "MAPE": group["AbsolutePercentageError"].mean(),
                "Bias": group["Error"].mean(),
            }
        )

    if not grupper:
        return

    result = pd.DataFrame(grupper)

    print("\nModell/variant-diagnostik:")
    print(
        result.to_string(
            index=False,
            formatters={
                "MAE": lambda x: f"{x:,.0f} kr",
                "MAPE": lambda x: f"{x:.2f} %",
                "Bias": lambda x: f"{x:+,.0f} kr",
            },
        )
    )


def _största_felen(test, prediction, antal=20):
    diagnostik = _skapa_diagnostik(test, prediction)

    diagnostik = diagnostik.sort_values(
        "AbsoluteError",
        ascending=False,
    ).reset_index(drop=True)

    topp = diagnostik.head(antal)

    kolumner = [
        "Model",
        "Variant",
        "ModelYear",
        "Mil",
        "Price",
        "Prediction",
        "Error",
        "AbsolutePercentageError",
    ]

    identitetskolumner = [
        "Identity",
        "vehicle_id",
        "annons_id",
        "url",
    ]

    kolumner = [
        column
        for column in kolumner + identitetskolumner
        if column in topp.columns
    ]

    print(f"\nDe {len(topp)} största absoluta felen:")

    utskrift = topp[kolumner].copy()

    if "Price" in utskrift.columns:
        utskrift["Price"] = utskrift["Price"].map(
            lambda x: f"{x:,.0f} kr"
        )

    if "Prediction" in utskrift.columns:
        utskrift["Prediction"] = utskrift["Prediction"].map(
            lambda x: f"{x:,.0f} kr"
        )

    if "Error" in utskrift.columns:
        utskrift["Error"] = utskrift["Error"].map(
            lambda x: f"{x:+,.0f} kr"
        )

    if "AbsolutePercentageError" in utskrift.columns:
        utskrift["AbsolutePercentageError"] = (
            utskrift["AbsolutePercentageError"].map(
                lambda x: f"{x:.2f} %"
            )
        )

    print(utskrift.to_string(index=False))

    _sammanfatta_största_felen(topp)


def _sammanfatta_största_felen(topp):
    """
    Sammanfattar de största felen per modell/variant.

    Detta påverkar inte modellträningen.
    """

    if "Model" not in topp.columns:
        return

    group_columns = ["Model"]

    if "Variant" in topp.columns:
        group_columns.append("Variant")

    grupper = []

    for keys, group in topp.groupby(group_columns):
        if not isinstance(keys, tuple):
            keys = (keys,)

        grupper.append(
            {
                "Model": keys[0],
                "Variant": keys[1] if len(keys) > 1 else "",
                "Antal toppfel": len(group),
                "MAE": group["AbsoluteError"].mean(),
                "Största fel": group["AbsoluteError"].max(),
                "Genomsnittligt fel": group["Error"].mean(),
                "MAPE": group["AbsolutePercentageError"].mean(),
            }
        )

    if not grupper:
        return

    result = (
        pd.DataFrame(grupper)
        .sort_values(
            ["Antal toppfel", "MAE"],
            ascending=[False, False],
        )
        .reset_index(drop=True)
    )

    print("\nSammanfattning av topp 20-felen per modell/variant:")

    print(
        result.to_string(
            index=False,
            formatters={
                "MAE": lambda x: f"{x:,.0f} kr",
                "Största fel": lambda x: f"{x:,.0f} kr",
                "Genomsnittligt fel": lambda x: f"{x:+,.0f} kr",
                "MAPE": lambda x: f"{x:.2f} %",
            },
        )
    )


def _diagnostik_per_modell(test, prediction):
    """
    Visar samtliga testobservationer för varje modell.

    Syftet är att kunna se om en modell/variant har ett systematiskt
    problem som inte syns enbart i topp 20 största fel.
    """

    diagnostik = _skapa_diagnostik(test, prediction)

    if "Model" not in diagnostik.columns:
        return

    print("\nDetaljerad diagnostik per modell:")

    for model, group in diagnostik.groupby("Model"):
        print(f"\n--- {model} ---")

        if "Variant" in group.columns:
            variants = group["Variant"].dropna().unique()

            if len(variants) > 1:
                print(
                    "Varianter: "
                    + ", ".join(str(value) for value in variants)
                )

        print(f"Observationer: {len(group)}")
        print(
            f"MAE: {group['AbsoluteError'].mean():,.0f} kr"
        )
        print(
            f"Median absolutfel: "
            f"{group['AbsoluteError'].median():,.0f} kr"
        )
        print(
            f"MAPE: "
            f"{group['AbsolutePercentageError'].mean():.2f} %"
        )
        print(
            f"Bias: "
            f"{group['Error'].mean():+,.0f} kr"
        )

        if "ModelYear" in group.columns:
            print("\nMAE per årsmodell:")

            per_year = (
                group.groupby("ModelYear")
                .agg(
                    n=("AbsoluteError", "size"),
                    MAE=("AbsoluteError", "mean"),
                    MAPE=("AbsolutePercentageError", "mean"),
                    Bias=("Error", "mean"),
                )
                .sort_index()
            )

            for year, row in per_year.iterrows():
                print(
                    f"  {year}: "
                    f"n={int(row['n'])} | "
                    f"MAE={row['MAE']:,.0f} kr | "
                    f"MAPE={row['MAPE']:.2f} % | "
                    f"Bias={row['Bias']:+,.0f} kr"
                )


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

    print(f"Råa observationer: {len(observations):,}")

    dataset = _bygg_dataset(observations)

    print(
        f"Dataset före deduplicering: {len(dataset):,}"
    )

    dataset = _deduplicera_dataset(dataset)

    print(
        f"Dataset efter deduplicering: {len(dataset):,}"
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

        model.fit(X_train, y_train)

        prediction = model.predict(X_test)

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
                print(f"  {key}: {value:.4f}")
            elif key == "MAPE":
                print(f"  {key}: {value:.2f} %")
            else:
                print(f"  {key}: {value:,.0f} kr")

    rf = resultat["random_forest"]

    print("\nRandom Forest feature importance:")

    importance = _feature_importance(
        rf["model"]
    )

    if importance is not None:
        print(
            importance.to_string(
                index=False,
                formatters={
                    "importance": lambda x: f"{x:.4f}"
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

    winner = min(
        resultat.items(),
        key=lambda item: item[1]["metrics"]["MAE"],
    )

    winner_name = winner[0]
    winner_model = winner[1]["model"]

    print(f"\nVinnande modell: {winner_name}")

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

    print(f"Modell sparad: {MODEL_FIL}")
    print(f"Metadata sparad: {METADATA_FIL}")


if __name__ == "__main__":
    main()
