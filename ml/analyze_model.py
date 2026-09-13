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

    diagnostik["Prediction"] = pd.Series(prediction).reset_index(drop=True)

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


def _diagnostik_330e_historik(dataset, test, prediction):
    """
    Analyserar historiken för BMW 330e-observationer i testmängden.

    Detta påverkar inte modellträningen.
    """

    if (
        "Model" not in test.columns
        or "Identity" not in dataset.columns
    ):
        return

    mask_330e = (
        test["Model"]
        .astype(str)
        .str.contains("330e", case=False, na=False)
    )

    test_330e = test[mask_330e].copy()

    if test_330e.empty:
        return

    prediction = pd.Series(prediction).reset_index(drop=True)
    mask_330e_array = mask_330e.to_numpy()

    diagnostik = _skapa_diagnostik(
        test_330e,
        prediction[mask_330e_array],
    )

    print("\nBMW 330e – historik för testobservationerna:")

    historik = dataset.copy()

    if "Tid" in historik.columns:
        historik["Tid"] = pd.to_datetime(
            historik["Tid"],
            errors="coerce",
            utc=True,
        )

    for _, row in diagnostik.sort_values(
        "AbsoluteError",
        ascending=False,
    ).iterrows():
        identity = row.get("Identity")

        if pd.isna(identity) or not str(identity).strip():
            continue

        bil = historik[
            historik["Identity"].astype(str) == str(identity)
        ].copy()

        if bil.empty:
            continue

        if "Tid" in bil.columns:
            bil = bil.sort_values("Tid")

        första_pris = bil["Price"].iloc[0]
        sista_pris = bil["Price"].iloc[-1]
        prisförändring = sista_pris - första_pris
        min_pris = bil["Price"].min()
        max_pris = bil["Price"].max()

        datum_första = "?"
        datum_sista = "?"

        if "Tid" in bil.columns and bil["Tid"].notna().any():
            giltiga_datum = bil["Tid"].dropna()
            datum_första = giltiga_datum.iloc[0].strftime("%Y-%m-%d")
            datum_sista = giltiga_datum.iloc[-1].strftime("%Y-%m-%d")

        print(
            f"\n  {row.get('Model', '')} {row.get('ModelYear', '')} "
            f"| {row.get('Mil', 0):,.0f} mil "
            f"| faktisk={row['Price']:,.0f} kr "
            f"| pred={row['Prediction']:,.0f} kr "
            f"| fel={row['Error']:+,.0f} kr"
        )

        print(
            f"    Historik: {len(bil)} obs | "
            f"{datum_första} → {datum_sista} | "
            f"pris {första_pris:,.0f} → {sista_pris:,.0f} kr "
            f"({prisförändring:+,.0f} kr)"
        )

        print(
            f"    Prisintervall: "
            f"{min_pris:,.0f}–{max_pris:,.0f} kr"
        )


def _normalisera_text(value):
    if value is None or pd.isna(value):
        return ""

    return " ".join(
        str(value).strip().casefold().split()
    )


def _weighted_median(values, weights):
    """
    Viktad median.

    Högre vikt innebär att observationen ligger närmare målobjektet.
    """

    values = pd.to_numeric(
        pd.Series(values),
        errors="coerce",
    )

    weights = pd.to_numeric(
        pd.Series(weights),
        errors="coerce",
    )

    data = pd.DataFrame(
        {
            "value": values,
            "weight": weights,
        }
    ).dropna()

    data = data[data["weight"] > 0]

    if data.empty:
        return float("nan")

    data = data.sort_values("value")

    cumulative_weight = data["weight"].cumsum()
    cutoff = data["weight"].sum() / 2

    index = cumulative_weight.searchsorted(
        cutoff,
        side="left",
    )

    index = min(
        int(index),
        len(data) - 1,
    )

    return float(data.iloc[index]["value"])


def _jämförbara_observationer(
    dataset,
    row,
    max_year_diff=1,
    max_mileage_diff=1500,
    min_comparables=3,
):
    """
    Hittar jämförbara observationer.

    Matchningen sker i första hand på:

      Model + Variant
      årsmodell ±1
      miltal ±1500

    Om Variant saknas används Model.

    Samma fordon exkluderas via Identity.

    Funktionen används endast diagnostiskt och påverkar inte träningen.
    """

    required = {
        "Model",
        "ModelYear",
        "Mil",
        "Price",
    }

    if not required.issubset(dataset.columns):
        return pd.DataFrame()

    model = _normalisera_text(
        row.get("Model")
    )

    variant = _normalisera_text(
        row.get("Variant")
    )

    model_year = pd.to_numeric(
        pd.Series([row.get("ModelYear")]),
        errors="coerce",
    ).iloc[0]

    mileage = pd.to_numeric(
        pd.Series([row.get("Mil")]),
        errors="coerce",
    ).iloc[0]

    if (
        not model
        or pd.isna(model_year)
        or pd.isna(mileage)
    ):
        return pd.DataFrame()

    kandidater = dataset.copy()

    kandidater["_ModelNorm"] = (
        kandidater["Model"]
        .map(_normalisera_text)
    )

    if "Variant" in kandidater.columns:
        kandidater["_VariantNorm"] = (
            kandidater["Variant"]
            .map(_normalisera_text)
        )
    else:
        kandidater["_VariantNorm"] = ""

    kandidater["_ModelYearNum"] = pd.to_numeric(
        kandidater["ModelYear"],
        errors="coerce",
    )

    kandidater["_MilNum"] = pd.to_numeric(
        kandidater["Mil"],
        errors="coerce",
    )

    kandidater["_PriceNum"] = pd.to_numeric(
        kandidater["Price"],
        errors="coerce",
    )

    # Samma modell.
    kandidater = kandidater[
        kandidater["_ModelNorm"] == model
    ].copy()

    # Samma variant när sådan finns.
    #
    # Vi blandar inte automatiskt olika varianter eftersom det
    # riskerar att göra jämförelsen mindre meningsfull.
    if variant:
        kandidater = kandidater[
            kandidater["_VariantNorm"] == variant
        ].copy()

    # Årsmodell ±1.
    kandidater = kandidater[
        kandidater["_ModelYearNum"].between(
            model_year - max_year_diff,
            model_year + max_year_diff,
        )
    ]

    # Miltal ±1500.
    kandidater = kandidater[
        (
            kandidater["_MilNum"] - mileage
        ).abs().le(max_mileage_diff)
    ]

    kandidater = kandidater[
        kandidater["_PriceNum"].notna()
    ].copy()

    # Samma bil får inte jämföra med sig själv.
    identity = row.get("Identity")

    if (
        identity is not None
        and not pd.isna(identity)
        and str(identity).strip()
        and "Identity" in kandidater.columns
    ):
        kandidater = kandidater[
            kandidater["Identity"].astype(str)
            != str(identity)
        ]

    if kandidater.empty:
        return kandidater

    kandidater["MileageDifference"] = (
        kandidater["_MilNum"] - mileage
    ).abs()

    kandidater["YearDifference"] = (
        kandidater["_ModelYearNum"] - model_year
    ).abs()

    # Ett avstånd där 1500 mil motsvarar ungefär ett årsmodellsteg.
    kandidater["SimilarityDistance"] = (
        kandidater["MileageDifference"]
        + kandidater["YearDifference"] * 1500
    )

    # Närmare bilar får högre vikt.
    kandidater["SimilarityWeight"] = (
        1
        / (
            250
            + kandidater["SimilarityDistance"]
        )
    )

    kandidater = kandidater.sort_values(
        [
            "SimilarityDistance",
            "MileageDifference",
            "YearDifference",
        ]
    )

    # Minst tre oberoende observationer krävs.
    if len(kandidater) < min_comparables:
        return pd.DataFrame()

    return kandidater


def _diagnostik_jämförbar_marknad(
    dataset,
    test,
    prediction,
):
    """
    Analyserar hur testbilarna ligger prismässigt mot jämförbara annonser.

    Matchning:
      - samma Model
      - samma Variant när Variant finns
      - årsmodell ±1
      - miltal ±1500
      - minst 3 jämförelseobjekt

    Jämförelsepris:
      - vanlig median
      - viktad median
      - Q25
      - Q75

    Dessutom identifieras fall där:
      1. Random Forest tycker att bilen är billig
      2. marknaden samtidigt tycker att bilen är billig

    Detta är diagnostik-only och används inte som träningsfeature.
    """

    required = {
        "Model",
        "ModelYear",
        "Mil",
        "Price",
    }

    if not required.issubset(test.columns):
        return

    diagnostik = _skapa_diagnostik(
        test,
        prediction,
    )

    resultat = []

    for _, row in diagnostik.iterrows():
        jämförbara = _jämförbara_observationer(
            dataset,
            row,
        )

        if jämförbara.empty:
            continue

        priser = jämförbara["_PriceNum"]

        medianpris = priser.median()

        viktad_median = _weighted_median(
            jämförbara["_PriceNum"],
            jämförbara["SimilarityWeight"],
        )

        q25 = priser.quantile(0.25)
        q75 = priser.quantile(0.75)

        faktisk_pris = float(row["Price"])
        prediction_value = float(row["Prediction"])

        avvikelse_kr = (
            faktisk_pris - viktad_median
        )

        avvikelse_procent = (
            avvikelse_kr
            / viktad_median
            * 100
            if viktad_median
            else float("nan")
        )

        # Positivt värde betyder att ML-modellen värderar bilen
        # högre än faktiskt pris.
        model_vs_actual_kr = (
            prediction_value - faktisk_pris
        )

        model_vs_actual_pct = (
            model_vs_actual_kr
            / faktisk_pris
            * 100
            if faktisk_pris
            else float("nan")
        )

        # Två oberoende signaler.
        model_cheap = (
            model_vs_actual_pct >= 5
        )

        market_cheap = (
            avvikelse_procent <= -5
        )

        double_undervaluation = (
            model_cheap
            and market_cheap
        )

        resultat.append(
            {
                "Model": row.get("Model", ""),
                "Variant": row.get("Variant", ""),
                "ModelYear": row.get("ModelYear", ""),
                "Mil": row.get("Mil", 0),
                "Price": faktisk_pris,
                "Prediction": prediction_value,
                "ModelError": row["Error"],
                "ModelVsActualPct": model_vs_actual_pct,
                "ComparableN": len(jämförbara),
                "ComparableMedian": medianpris,
                "ComparableWeightedMedian": viktad_median,
                "ComparableQ25": q25,
                "ComparableQ75": q75,
                "ComparableDeviation": avvikelse_kr,
                "ComparableDeviationPct": avvikelse_procent,
                "ModelCheap": model_cheap,
                "MarketCheap": market_cheap,
                "DoubleUndervaluation": double_undervaluation,
                "Identity": row.get("Identity", ""),
            }
        )

    if not resultat:
        print(
            "\nJämförbar marknad: inga testbilar hade "
            "minst tre tillräckligt lika jämförelseobjekt."
        )
        return

    result = pd.DataFrame(resultat)

    print(
        "\nJämförbar marknad – diagnostik:"
    )

    print(
        f"  Testobservationer: {len(test)}"
    )

    print(
        f"  Med minst 3 jämförelseobjekt: "
        f"{len(result)}"
    )

    print(
        f"  Medianavvikelse mot jämförelsemarknad: "
        f"{result['ComparableDeviationPct'].median():+.2f} %"
    )

    result["PotentialBargain"] = (
        result["ComparableDeviationPct"] <= -5
    )

    print(
        f"  Under -5 % mot marknadsmedian: "
        f"{int(result['PotentialBargain'].sum())}"
    )

    print(
        f"  RF minst 5 % över faktiskt pris: "
        f"{int(result['ModelCheap'].sum())}"
    )

    print(
        f"  Både RF + marknad signalerar fynd: "
        f"{int(result['DoubleUndervaluation'].sum())}"
    )

    # ---------------------------------------------------------
    # Starkaste kombinerade fynd
    # ---------------------------------------------------------

    dubbla = result[
        result["DoubleUndervaluation"]
    ].copy()

    if not dubbla.empty:
        dubbla["CombinedScore"] = (
            dubbla["ModelVsActualPct"].clip(lower=0)
            + (-dubbla["ComparableDeviationPct"]).clip(lower=0)
        )

        dubbla = dubbla.sort_values(
            "CombinedScore",
            ascending=False,
        )

    print(
        "\nStarkaste fynd – både ML-modell och jämförelsemarknad:"
    )

    if dubbla.empty:
        print(
            "  Inga objekt uppfyller båda kriterierna."
        )
    else:
        utskrift = dubbla.head(20).copy()

        for column in [
            "Price",
            "Prediction",
            "ComparableWeightedMedian",
        ]:
            utskrift[column] = utskrift[column].map(
                lambda x: f"{x:,.0f} kr"
            )

        utskrift["ModelVsActualPct"] = (
            utskrift["ModelVsActualPct"].map(
                lambda x: f"{x:+.2f} %"
            )
        )

        utskrift["ComparableDeviationPct"] = (
            utskrift["ComparableDeviationPct"].map(
                lambda x: f"{x:+.2f} %"
            )
        )

        utskrift["CombinedScore"] = (
            utskrift["CombinedScore"].map(
                lambda x: f"{x:.2f}"
            )
        )

        utskrift["ModelError"] = (
            utskrift["ModelError"].map(
                lambda x: f"{x:+,.0f} kr"
            )
        )

        kolumner = [
            "Model",
            "Variant",
            "ModelYear",
            "Mil",
            "Price",
            "Prediction",
            "ModelVsActualPct",
            "ComparableWeightedMedian",
            "ComparableDeviationPct",
            "ComparableN",
            "CombinedScore",
            "ModelError",
            "Identity",
        ]

        print(
            utskrift[kolumner].to_string(
                index=False
            )
        )

    # ---------------------------------------------------------
    # Starkaste marknadsfynd
    # ---------------------------------------------------------

    fynd = result[
        result["ComparableDeviationPct"] < 0
    ].copy()

    fynd = fynd.sort_values(
        "ComparableDeviationPct"
    )

    print(
        "\nStarkaste marknadsfynd:"
    )

    if fynd.empty:
        print(
            "  Inga testbilar ligger under "
            "jämförelsemedianen."
        )
    else:
        utskrift = fynd.head(20).copy()

        for column in [
            "Price",
            "Prediction",
            "ComparableWeightedMedian",
        ]:
            utskrift[column] = utskrift[column].map(
                lambda x: f"{x:,.0f} kr"
            )

        utskrift["ComparableDeviation"] = (
            utskrift["ComparableDeviation"].map(
                lambda x: f"{x:+,.0f} kr"
            )
        )

        utskrift["ComparableDeviationPct"] = (
            utskrift["ComparableDeviationPct"].map(
                lambda x: f"{x:+.2f} %"
            )
        )

        utskrift["ModelVsActualPct"] = (
            utskrift["ModelVsActualPct"].map(
                lambda x: f"{x:+.2f} %"
            )
        )

        kolumner = [
            "Model",
            "Variant",
            "ModelYear",
            "Mil",
            "Price",
            "ComparableWeightedMedian",
            "ComparableDeviation",
            "ComparableDeviationPct",
            "ComparableN",
            "Prediction",
            "ModelVsActualPct",
            "Identity",
        ]

        print(
            utskrift[kolumner].to_string(
                index=False
            )
        )

    # ---------------------------------------------------------
    # Diagnostik per modell/variant
    # ---------------------------------------------------------

    if "Model" in result.columns:
        print(
            "\nJämförbar marknad per modell/variant:"
        )

        group_columns = ["Model"]

        if (
            "Variant" in result.columns
            and result["Variant"]
            .fillna("")
            .astype(str)
            .str.strip()
            .ne("")
            .any()
        ):
            group_columns.append("Variant")

        grupper = (
            result.groupby(group_columns)
            .agg(
                n=("ComparableDeviationPct", "size"),
                MedianDeviationPct=(
                    "ComparableDeviationPct",
                    "median",
                ),
                Under5Pct=(
                    "PotentialBargain",
                    "sum",
                ),
                DoubleUndervaluation=(
                    "DoubleUndervaluation",
                    "sum",
                ),
            )
            .reset_index()
        )

        print(
            grupper.to_string(
                index=False,
                formatters={
                    "MedianDeviationPct":
                        lambda x: f"{x:+.2f} %",
                },
            )
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
