"""
Diagnostik för Fiskabilars ML-modell.

Normal körning:
    python ml/analyze_model.py

Ingen output utan --debug.

Debug:
    python ml/analyze_model.py --debug

Diagnostiken analyserar bland annat:

- antal råa observationer
- antal användbara observationer
- antal observationer efter deduplicering
- normaliserade modeller
- normaliserade varianter
- antal observationer per modell
- antal observationer per variant
- prisstatistik
- prisutveckling över tid
- tränings-/testfördelning
- MAE
- median absolutfel
- RMSE
- R²
- bias
- fel per modell
- fel per årsmodell
- eventuell skillnad mellan linjär regression
  och Random Forest

Filen ändrar inte modellen eller någon data.
Den är endast diagnostisk.
"""

from __future__ import annotations

import argparse
import json

from pathlib import Path
from typing import Any

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

from ml.normalization import (
    normalisera_modell,
    normalisera_variant,
)


HISTORIK_DIR = Path(
    "data/market_history"
)

MODEL_FIL = Path(
    "data/ml/market_model.joblib"
)

METADATA_FIL = Path(
    "data/ml/model_metadata.json"
)


FEATURES_NUMERIC = [
    "Mil",
    "ModelYear",
]

FEATURES_CATEGORICAL = [
    "Model",
    "Variant",
]

FEATURES = (
    FEATURES_NUMERIC
    + FEATURES_CATEGORICAL
)

TARGET = "Price"


def _print_debug(
    debug: bool,
    message: str = "",
) -> None:
    """
    Skriver endast ut om debug är aktiverat.
    """

    if debug:
        print(message)


def _load_jsonl(
    debug: bool = False,
) -> pd.DataFrame:
    """
    Läser all marknadshistorik.
    """

    files = sorted(
        HISTORIK_DIR.glob(
            "market_history_*.jsonl"
        )
    )

    legacy = (
        HISTORIK_DIR
        / "market_history.jsonl"
    )

    if legacy.exists():
        files.append(
            legacy
        )

    if not files:
        raise FileNotFoundError(
            f"Inga historikfiler hittades i "
            f"{HISTORIK_DIR}"
        )

    records: list[dict[str, Any]] = []

    for file in files:

        file_records = 0

        with file.open(
            "r",
            encoding="utf-8",
        ) as handle:

            for line_number, line in enumerate(
                handle,
                start=1,
            ):

                line = line.strip()

                if not line:
                    continue

                try:

                    record = json.loads(
                        line
                    )

                except json.JSONDecodeError:

                    _print_debug(
                        debug,
                        (
                            "Varning: kunde inte läsa "
                            f"{file}:{line_number}"
                        ),
                    )

                    continue

                if isinstance(
                    record,
                    dict,
                ):

                    record[
                        "_historikfil"
                    ] = file.name

                    records.append(
                        record
                    )

                    file_records += 1

        _print_debug(
            debug,
            (
                f"  {file.name}: "
                f"{file_records} observationer"
            ),
        )

    if not records:
        raise ValueError(
            "Historikfilerna innehåller inga "
            "giltiga observationer."
        )

    return pd.DataFrame(
        records
    )


def _build_dataset(
    raw: pd.DataFrame,
    debug: bool = False,
) -> pd.DataFrame:
    """
    Bygger ett normaliserat ML-dataset.
    """

    result = pd.DataFrame()

    result["Mil"] = pd.to_numeric(
        raw.get("miltal"),
        errors="coerce",
    )

    result[
        "ModelYear"
    ] = pd.to_numeric(
        raw.get("arsmodell"),
        errors="coerce",
    )

    result["Model"] = (
        raw.get("modell")
        .apply(
            normalisera_modell
        )
    )

    result["Variant"] = (
        raw.get("variant")
        .apply(
            normalisera_variant
        )
    )

    result["Price"] = pd.to_numeric(
        raw.get("annonspris"),
        errors="coerce",
    )

    result["Tid"] = pd.to_datetime(
        raw.get("tid"),
        errors="coerce",
        utc=True,
    )

    before = len(
        result
    )

    result = result.dropna(
        subset=[
            "Mil",
            "ModelYear",
            "Price",
        ]
    )

    result = result[
        result["Price"] > 0
    ]

    result = result[
        result["Mil"] >= 0
    ]

    after = len(
        result
    )

    _print_debug(
        debug,
        (
            f"  Bortsorterade ogiltiga "
            f"observationer: "
            f"{before - after}"
        ),
    )

    result["Model"] = (
        result["Model"]
        .fillna("okänd")
    )

    result["Variant"] = (
        result["Variant"]
        .fillna("okänd")
    )

    result = result.sort_values(
        "Tid",
        na_position="last",
    ).reset_index(
        drop=True
    )

    return result


def _deduplicate(
    data: pd.DataFrame,
    debug: bool = False,
) -> pd.DataFrame:
    """
    Tar bort identiska observationer.

    Samma kombination av:

        Mil
        ModelYear
        Model
        Variant
        Price

    räknas som samma observation.
    """

    keys = [
        "Mil",
        "ModelYear",
        "Model",
        "Variant",
        "Price",
    ]

    before = len(
        data
    )

    result = (
        data
        .drop_duplicates(
            subset=keys
        )
        .reset_index(
            drop=True
        )
    )

    after = len(
        result
    )

    _print_debug(
        debug,
        (
            f"  Deduplicering: "
            f"{before} → {after} "
            f"({before - after} borttagna)"
        ),
    )

    return result


def _build_preprocessor() -> ColumnTransformer:
    """
    Skapar preprocessing för ML-modellerna.
    """

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
                FEATURES_CATEGORICAL,
            ),
        ]
    )


def _build_models() -> dict[str, Pipeline]:
    """
    Skapar samma modeller som träningskoden.
    """

    return {

        "linear_regression":
            Pipeline(
                steps=[
                    (
                        "preprocessor",
                        _build_preprocessor(),
                    ),
                    (
                        "model",
                        LinearRegression(),
                    ),
                ]
            ),

        "random_forest":
            Pipeline(
                steps=[
                    (
                        "preprocessor",
                        _build_preprocessor(),
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


def _time_split(
    data: pd.DataFrame,
    test_ratio: float = 0.20,
) -> tuple[
    pd.DataFrame,
    pd.DataFrame,
]:
    """
    Samma tidsmässiga split som träningsmodellen.

    Äldsta 80 %:
        träning

    Nyaste 20 %:
        test
    """

    data = (
        data
        .sort_values(
            "Tid",
            na_position="first",
        )
        .reset_index(
            drop=True
        )
    )

    test_count = max(
        1,
        int(
            round(
                len(data)
                * test_ratio
            )
        ),
    )

    train_count = (
        len(data)
        - test_count
    )

    train = data.iloc[
        :train_count
    ].copy()

    test = data.iloc[
        train_count:
    ].copy()

    return (
        train,
        test,
    )


def _metrics(
    actual: pd.Series,
    predicted,
) -> dict[str, float]:
    """
    Beräknar felstatistik.
    """

    actual = pd.Series(
        actual,
        dtype="float64",
    ).reset_index(
        drop=True
    )

    predicted = pd.Series(
        predicted,
        dtype="float64",
    ).reset_index(
        drop=True
    )

    error = (
        predicted
        - actual
    )

    absolute_error = (
        error.abs()
    )

    return {

        "antal":
            int(
                len(actual)
            ),

        "mae":
            float(
                mean_absolute_error(
                    actual,
                    predicted,
                )
            ),

        "median_absolutfel":
            float(
                absolute_error.median()
            ),

        "rmse":
            float(
                mean_squared_error(
                    actual,
                    predicted,
                )
                ** 0.5
            ),

        "r2":
            float(
                r2_score(
                    actual,
                    predicted,
                )
            ),

        "bias":
            float(
                error.mean()
            ),

        "faktiskt_medelpris":
            float(
                actual.mean()
            ),

        "predikterat_medelpris":
            float(
                predicted.mean()
            ),
    }


def _print_metrics(
    name: str,
    metrics: dict[str, float],
) -> None:
    """
    Skriver modellens metrics.
    """

    print()
    print(
        f"--- {name} ---"
    )

    print(
        f"Antal: "
        f"{metrics['antal']}"
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

    print(
        f"Faktiskt medelpris: "
        f"{metrics['faktiskt_medelpris']:,.0f} kr"
    )

    print(
        f"Predikterat medelpris: "
        f"{metrics['predikterat_medelpris']:,.0f} kr"
    )


def _group_metrics(
    test: pd.DataFrame,
    predictions,
    column: str,
) -> dict[str, dict]:
    """
    Beräknar fel per grupp.
    """

    data = test[
        [
            column,
            TARGET,
        ]
    ].copy()

    data[
        "_prediction"
    ] = predictions

    result = {}

    for group, group_data in (
        data.groupby(
            column,
            dropna=False,
        )
    ):

        name = (
            "okänd"
            if pd.isna(group)
            else str(group)
        )

        result[
            name
        ] = _metrics(
            group_data[
                TARGET
            ],
            group_data[
                "_prediction"
            ],
        )

    return result


def _print_group_metrics(
    title: str,
    groups: dict[str, dict],
    minimum_observations: int = 2,
) -> None:
    """
    Skriver gruppresultat.
    """

    print()
    print(
        f"--- {title} ---"
    )

    for name, metrics in sorted(
        groups.items()
    ):

        if (
            metrics["antal"]
            < minimum_observations
        ):
            continue

        print(
            f"{name}: "
            f"{metrics['antal']} obs, "
            f"MAE "
            f"{metrics['mae']:,.0f} kr, "
            f"bias "
            f"{metrics['bias']:,.0f} kr"
        )


def _print_distribution(
    data: pd.DataFrame,
) -> None:
    """
    Skriver datasetets fördelning.
    """

    print()
    print(
        "--- DATASET ---"
    )

    print(
        f"Observationer: "
        f"{len(data)}"
    )

    print(
        f"Unika modeller: "
        f"{data['Model'].nunique()}"
    )

    print(
        f"Unika varianter: "
        f"{data['Variant'].nunique()}"
    )

    print(
        f"Unika kombinationer "
        f"modell/variant: "
        f"{data[['Model', 'Variant']].drop_duplicates().shape[0]}"
    )

    print()
    print(
        "Observationer per modell:"
    )

    for model, count in (
        data["Model"]
        .value_counts()
        .items()
    ):

        print(
            f"  {model}: "
            f"{count}"
        )

    print()
    print(
        "Observationer per variant:"
    )

    for variant, count in (
        data["Variant"]
        .value_counts()
        .items()
    ):

        print(
            f"  {variant}: "
            f"{count}"
        )


def _print_duplicate_analysis(
    raw: pd.DataFrame,
    normalized: pd.DataFrame,
) -> None:
    """
    Visar hur mycket kategorierna förändras
    genom normaliseringen.
    """

    print()
    print(
        "--- NORMALISERING ---"
    )

    if "modell" in raw.columns:

        original_models = (
            raw["modell"]
            .dropna()
            .astype(str)
            .str.strip()
        )

        normalized_models = (
            original_models
            .apply(
                normalisera_modell
            )
        )

        print(
            f"Originala modellnamn: "
            f"{original_models.nunique()}"
        )

        print(
            f"Normaliserade modellnamn: "
            f"{normalized_models.nunique()}"
        )

    if "variant" in raw.columns:

        original_variants = (
            raw["variant"]
            .dropna()
            .astype(str)
            .str.strip()
        )

        normalized_variants = (
            original_variants
            .apply(
                normalisera_variant
            )
        )

        print(
            f"Originala variantnamn: "
            f"{original_variants.nunique()}"
        )

        print(
            f"Normaliserade variantnamn: "
            f"{normalized_variants.nunique()}"
        )


def _print_time_analysis(
    data: pd.DataFrame,
) -> None:
    """
    Visar prisutvecklingen över tid.
    """

    print()
    print(
        "--- TIDSANALYS ---"
    )

    dated = data.dropna(
        subset=["Tid"]
    ).copy()

    if dated.empty:

        print(
            "Ingen tidsinformation finns."
        )

        return

    dated["Månad"] = (
        dated["Tid"]
        .dt.to_period("M")
        .astype(str)
    )

    monthly = (
        dated
        .groupby("Månad")
        .agg(
            antal=(
                "Price",
                "size",
            ),
            medelpris=(
                "Price",
                "mean",
            ),
            medianpris=(
                "Price",
                "median",
            ),
        )
    )

    for month, row in (
        monthly.iterrows()
    ):

        print(
            f"{month}: "
            f"{int(row['antal'])} obs, "
            f"median "
            f"{row['medianpris']:,.0f} kr, "
            f"medel "
            f"{row['medelpris']:,.0f} kr"
        )


def _print_train_test(
    train: pd.DataFrame,
    test: pd.DataFrame,
) -> None:
    """
    Visar hur den tidsmässiga splitten ser ut.
    """

    print()
    print(
        "--- TRAIN / TEST ---"
    )

    print(
        f"Träning: "
        f"{len(train)} observationer"
    )

    print(
        f"Test: "
        f"{len(test)} observationer"
    )

    if not train.empty:

        print(
            "Träning från: "
            f"{train['Tid'].min()}"
        )

        print(
            "Träning till: "
            f"{train['Tid'].max()}"
        )

    if not test.empty:

        print(
            "Test från: "
            f"{test['Tid'].min()}"
        )

        print(
            "Test till: "
            f"{test['Tid'].max()}"
        )

    if not train.empty and not test.empty:

        train_price = (
            train["Price"].mean()
        )

        test_price = (
            test["Price"].mean()
        )

        difference = (
            test_price
            - train_price
        )

        print()
        print(
            f"Medelpris träning: "
            f"{train_price:,.0f} kr"
        )

        print(
            f"Medelpris test: "
            f"{test_price:,.0f} kr"
        )

        print(
            f"Skillnad test - träning: "
            f"{difference:+,.0f} kr"
        )


def _print_feature_information(
    model: Pipeline,
) -> None:
    """
    Visar hur många features modellen faktiskt
    får efter one-hot encoding.
    """

    print()
    print(
        "--- FEATURES ---"
    )

    preprocessor = (
        model.named_steps[
            "preprocessor"
        ]
    )

    try:

        names = (
            preprocessor
            .get_feature_names_out()
        )

        print(
            f"Antal features efter "
            f"encoding: "
            f"{len(names)}"
        )

        print(
            "Exempel:"
        )

        for name in names[:20]:

            print(
                f"  {name}"
            )

        if len(names) > 20:

            print(
                f"  ... "
                f"({len(names) - 20} till)"
            )

    except Exception as exc:

        print(
            "Kunde inte läsa feature-namn: "
            f"{exc}"
        )


def _print_random_forest_importance(
    model: Pipeline,
) -> None:
    """
    Visar feature importance för Random Forest.
    """

    print()
    print(
        "--- RANDOM FOREST FEATURE IMPORTANCE ---"
    )

    if (
        "model"
        not in model.named_steps
    ):
        return

    estimator = (
        model.named_steps[
            "model"
        ]
    )

    if not isinstance(
        estimator,
        RandomForestRegressor,
    ):
        print(
            "Modellen är inte en "
            "RandomForestRegressor."
        )

        return

    try:

        preprocessor = (
            model.named_steps[
                "preprocessor"
            ]
        )

        names = (
            preprocessor
            .get_feature_names_out()
        )

        importances = (
            estimator
            .feature_importances_
        )

        importance = sorted(
            zip(
                names,
                importances,
            ),
            key=lambda item:
                item[1],
            reverse=True,
        )

        for name, value in (
            importance[:20]
        ):

            print(
                f"{name}: "
                f"{value:.4f}"
            )

    except Exception as exc:

        print(
            "Kunde inte beräkna "
            f"feature importance: {exc}"
        )


def _load_existing_metadata() -> dict | None:
    """
    Läser befintlig metadata om den finns.
    """

    if not METADATA_FIL.exists():
        return None

    try:

        return json.loads(
            METADATA_FIL.read_text(
                encoding="utf-8"
            )
        )

    except (
        json.JSONDecodeError,
        OSError,
    ):

        return None


def _compare_existing_model(
    debug: bool,
) -> None:
    """
    Jämför diagnostiken med sparad modellmetadata.
    """

    metadata = (
        _load_existing_metadata()
    )

    if metadata is None:
        return

    print()
    print(
        "--- SPARAD MODELL ---"
    )

    print(
        f"Vald modell: "
        f"{metadata.get('modell', 'okänd')}"
    )

    print(
        f"Urvalsprincip: "
        f"{metadata.get('urvalsprincip', 'okänd')}"
    )

    metrics = metadata.get(
        "metrics",
        {},
    )

    for name, result in (
        metrics.items()
    ):

        total = result.get(
            "totalt",
            {},
        )

        print(
            f"{name}: "
            f"MAE "
            f"{total.get('mae', 0):,.0f} kr, "
            f"R² "
            f"{total.get('r2', 0):.4f}, "
            f"bias "
            f"{total.get('bias', 0):,.0f} kr"
        )


def run_diagnostics() -> None:
    """
    Kör hela diagnostiken.
    """

    print(
        "=========================================="
    )

    print(
        "FISKABILAR ML-DIAGNOSTIK"
    )

    print(
        "=========================================="
    )

    print()
    print(
        f"Historik: "
        f"{HISTORIK_DIR}"
    )

    print(
        f"Modell: "
        f"{MODEL_FIL}"
    )

    raw = _load_jsonl(
        debug=True
    )

    print()
    print(
        f"Råa observationer: "
        f"{len(raw)}"
    )

    dataset = _build_dataset(
        raw,
        debug=True,
    )

    _print_duplicate_analysis(
        raw,
        dataset,
    )

    dataset = _deduplicate(
        dataset,
        debug=True,
    )

    _print_distribution(
        dataset
    )

    _print_time_analysis(
        dataset
    )

    train, test = (
        _time_split(
            dataset
        )
    )

    _print_train_test(
        train,
        test,
    )

    models = _build_models()

    predictions_by_model = {}

    print()
    print(
        "=========================================="
    )

    print(
        "MODELLJÄMFÖRELSE"
    )

    print(
        "=========================================="
    )

    for name, model in (
        models.items()
    ):

        model.fit(
            train[
                FEATURES
            ],
            train[
                TARGET
            ],
        )

        predictions = (
            model.predict(
                test[
                    FEATURES
                ]
            )
        )

        predictions_by_model[
            name
        ] = predictions

        metrics = _metrics(
            test[
                TARGET
            ],
            predictions,
        )

        _print_metrics(
            name,
            metrics,
        )

        if name == "random_forest":

            _print_feature_information(
                model
            )

            _print_random_forest_importance(
                model
            )

        groups = _group_metrics(
            test,
            predictions,
            "Model",
        )

        _print_group_metrics(
            "Fel per modell",
            groups,
        )

        groups = _group_metrics(
            test,
            predictions,
            "ModelYear",
        )

        _print_group_metrics(
            "Fel per årsmodell",
            groups,
        )

    _compare_existing_model(
        debug=True
    )

    print()
    print(
        "=========================================="
    )

    print(
        "DIAGNOSTIK KLAR"
    )

    print(
        "=========================================="
    )


def main() -> None:
    """
    CLI-entrypoint.

    Utan --debug gör filen ingenting och skriver
    ingenting.
    """

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--debug",
        action="store_true",
        help=(
            "Kör och skriv ut full "
            "ML-diagnostik."
        ),
    )

    args = (
        parser.parse_args()
    )

    if not args.debug:
        return

    run_diagnostics()


if __name__ == "__main__":
    main()
