import pandas as pd
from sklearn.metrics import (
    mean_absolute_error,
    mean_squared_error,
    r2_score,
)

from ml.features import FEATURES


def _metrics(y_true, y_pred):
    y_true = pd.Series(y_true).reset_index(drop=True)
    y_pred = pd.Series(y_pred).reset_index(drop=True)

    errors = y_pred - y_true
    non_zero = y_true != 0

    return {
        "MAE": mean_absolute_error(
            y_true,
            y_pred,
        ),
        "RMSE": mean_squared_error(
            y_true,
            y_pred,
        ) ** 0.5,
        "R2": r2_score(
            y_true,
            y_pred,
        ),
        "Bias": errors.mean(),
        "MAPE": (
            (
                errors[non_zero].abs()
                / y_true[non_zero].abs()
            ).mean()
            * 100
            if non_zero.any()
            else float("nan")
        ),
    }


def _feature_importance(model):
    preprocessor = model.named_steps["preprocessor"]
    estimator = model.named_steps["model"]

    try:
        feature_names = (
            preprocessor.get_feature_names_out()
        )
        importances = (
            estimator.feature_importances_
        )
    except AttributeError:
        return None

    rows = []

    for feature_name, importance in zip(
        feature_names,
        importances,
    ):
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
        name = name.replace(
            "numeric__",
            "",
        )
        name = name.replace(
            "categorical__",
            "",
        )

        for feature in FEATURES:
            if (
                name == feature
                or name.startswith(
                    feature + "_"
                )
            ):
                return feature

        return name

    result["base_feature"] = (
        result["feature"].map(
            base_feature
        )
    )

    grouped = (
        result.groupby(
            "base_feature",
            as_index=False,
        )["importance"]
        .sum()
        .sort_values(
            "importance",
            ascending=False,
        )
    )

    return grouped


def _skapa_diagnostik(test, prediction):
    diagnostik = (
        test.copy()
        .reset_index(drop=True)
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

    diagnostik[
        "AbsolutePercentageError"
    ] = (
        diagnostik["AbsoluteError"]
        / diagnostik["Price"].abs()
        * 100
    )

    return diagnostik


def _modell_variant_diagnostik(
    test,
    prediction,
):
    diagnostik = _skapa_diagnostik(
        test,
        prediction,
    )

    if (
        "Model" in diagnostik.columns
        and "Variant" in diagnostik.columns
    ):
        group_columns = [
            "Model",
            "Variant",
        ]
    elif "Model" in diagnostik.columns:
        group_columns = ["Model"]
    else:
        return

    grupper = []

    for keys, group in diagnostik.groupby(
        group_columns
    ):
        if not isinstance(keys, tuple):
            keys = (keys,)

        grupper.append(
            {
                "Model": keys[0],
                "Variant": (
                    keys[1]
                    if len(keys) > 1
                    else ""
                ),
                "n": len(group),
                "MAE": (
                    group["AbsoluteError"]
                    .mean()
                ),
                "MAPE": (
                    group[
                        "AbsolutePercentageError"
                    ].mean()
                ),
                "Bias": (
                    group["Error"].mean()
                ),
            }
        )

    if not grupper:
        return

    result = pd.DataFrame(grupper)

    print(
        "\nModell/variant-diagnostik:"
    )

    print(
        result.to_string(
            index=False,
            formatters={
                "MAE": (
                    lambda x:
                    f"{x:,.0f} kr"
                ),
                "MAPE": (
                    lambda x:
                    f"{x:.2f} %"
                ),
                "Bias": (
                    lambda x:
                    f"{x:+,.0f} kr"
                ),
            },
        )
    )


def _största_felen(
    test,
    prediction,
    antal=20,
):
    diagnostik = _skapa_diagnostik(
        test,
        prediction,
    )

    diagnostik = (
        diagnostik
        .sort_values(
            "AbsoluteError",
            ascending=False,
        )
        .reset_index(drop=True)
    )

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
        for column in (
            kolumner
            + identitetskolumner
        )
        if column in topp.columns
    ]

    print(
        f"\nDe {len(topp)} "
        "största absoluta felen:"
    )

    utskrift = topp[
        kolumner
    ].copy()

    if "Price" in utskrift.columns:
        utskrift["Price"] = (
            utskrift["Price"].map(
                lambda x:
                f"{x:,.0f} kr"
            )
        )

    if "Prediction" in utskrift.columns:
        utskrift["Prediction"] = (
            utskrift[
                "Prediction"
            ].map(
                lambda x:
                f"{x:,.0f} kr"
            )
        )

    if "Error" in utskrift.columns:
        utskrift["Error"] = (
            utskrift["Error"].map(
                lambda x:
                f"{x:+,.0f} kr"
            )
        )

    if (
        "AbsolutePercentageError"
        in utskrift.columns
    ):
        utskrift[
            "AbsolutePercentageError"
        ] = (
            utskrift[
                "AbsolutePercentageError"
            ].map(
                lambda x:
                f"{x:.2f} %"
            )
        )

    print(
        utskrift.to_string(
            index=False
        )
    )

    _sammanfatta_största_felen(
        topp
    )


def _sammanfatta_största_felen(
    topp,
):
    """
    Sammanfattar de största felen
    per modell/variant.

    Detta påverkar inte modellträningen.
    """

    if "Model" not in topp.columns:
        return

    group_columns = ["Model"]

    if "Variant" in topp.columns:
        group_columns.append(
            "Variant"
        )

    grupper = []

    for keys, group in topp.groupby(
        group_columns
    ):
        if not isinstance(keys, tuple):
            keys = (keys,)

        grupper.append(
            {
                "Model": keys[0],
                "Variant": (
                    keys[1]
                    if len(keys) > 1
                    else ""
                ),
                "Antal toppfel": len(group),
                "MAE": (
                    group["AbsoluteError"]
                    .mean()
                ),
                "Största fel": (
                    group["AbsoluteError"]
                    .max()
                ),
                "Genomsnittligt fel": (
                    group["Error"].mean()
                ),
                "MAPE": (
                    group[
                        "AbsolutePercentageError"
                    ].mean()
                ),
            }
        )

    if not grupper:
        return

    result = (
        pd.DataFrame(grupper)
        .sort_values(
            [
                "Antal toppfel",
                "MAE",
            ],
            ascending=[
                False,
                False,
            ],
        )
        .reset_index(drop=True)
    )

    print(
        "\nSammanfattning av "
        "topp 20-felen per "
        "modell/variant:"
    )

    print(
        result.to_string(
            index=False,
            formatters={
                "MAE": (
                    lambda x:
                    f"{x:,.0f} kr"
                ),
                "Största fel": (
                    lambda x:
                    f"{x:,.0f} kr"
                ),
                "Genomsnittligt fel": (
                    lambda x:
                    f"{x:+,.0f} kr"
                ),
                "MAPE": (
                    lambda x:
                    f"{x:.2f} %"
                ),
            },
        )
    )


def _diagnostik_per_modell(
    test,
    prediction,
):
    """
    Visar samtliga testobservationer
    för varje modell.
    """

    diagnostik = _skapa_diagnostik(
        test,
        prediction,
    )

    if "Model" not in diagnostik.columns:
        return

    print(
        "\nDetaljerad diagnostik "
        "per modell:"
    )

    for model, group in (
        diagnostik.groupby("Model")
    ):
        print(
            f"\n--- {model} ---"
        )

        if "Variant" in group.columns:
            variants = (
                group["Variant"]
                .dropna()
                .unique()
            )

            if len(variants) > 1:
                print(
                    "Varianter: "
                    + ", ".join(
                        str(value)
                        for value
                        in variants
                    )
                )

        print(
            f"Observationer: {len(group)}"
        )

        print(
            f"MAE: "
            f"{group['AbsoluteError'].mean():,.0f} kr"
        )

        print(
            "Median absolutfel: "
            f"{group['AbsoluteError'].median():,.0f} kr"
        )

        print(
            "MAPE: "
            f"{group['AbsolutePercentageError'].mean():.2f} %"
        )

        print(
            "Bias: "
            f"{group['Error'].mean():+,.0f} kr"
        )

        if "ModelYear" in group.columns:
            print(
                "\nMAE per årsmodell:"
            )

            per_year = (
                group.groupby(
                    "ModelYear"
                )
                .agg(
                    n=(
                        "AbsoluteError",
                        "size",
                    ),
                    MAE=(
                        "AbsoluteError",
                        "mean",
                    ),
                    MAPE=(
                        "AbsolutePercentageError",
                        "mean",
                    ),
                    Bias=(
                        "Error",
                        "mean",
                    ),
                )
                .sort_index()
            )

            for year, row in (
                per_year.iterrows()
            ):
                print(
                    f"  {year}: "
                    f"n={int(row['n'])} | "
                    f"MAE={row['MAE']:,.0f} kr | "
                    f"MAPE={row['MAPE']:.2f} % | "
                    f"Bias={row['Bias']:+,.0f} kr"
                )


def _diagnostik_330e_historik(
    dataset,
    test,
    prediction,
):
    """
    Analyserar historiken för
    BMW 330e-observationer i
    testmängden.

    Detta påverkar inte
    modellträningen.
    """

    if (
        "Model" not in test.columns
        or "Identity"
        not in dataset.columns
    ):
        return

    mask_330e = (
        test["Model"]
        .astype(str)
        .str.contains(
            "330e",
            case=False,
            na=False,
        )
    )

    test_330e = test[
        mask_330e
    ].copy()

    if test_330e.empty:
        return

    prediction = (
        pd.Series(prediction)
        .reset_index(drop=True)
    )

    mask_330e_array = (
        mask_330e.to_numpy()
    )

    diagnostik = _skapa_diagnostik(
        test_330e,
        prediction[
            mask_330e_array
        ],
    )

    print(
        "\nBMW 330e – historik "
        "för testobservationerna:"
    )

    historik = dataset.copy()

    if "Tid" in historik.columns:
        historik["Tid"] = (
            pd.to_datetime(
                historik["Tid"],
                errors="coerce",
                utc=True,
            )
        )

    for _, row in (
        diagnostik
        .sort_values(
            "AbsoluteError",
            ascending=False,
        )
        .iterrows()
    ):
        identity = row.get(
            "Identity"
        )

        if (
            pd.isna(identity)
            or not str(identity).strip()
        ):
            continue

        bil = historik[
            historik["Identity"]
            .astype(str)
            == str(identity)
        ].copy()

        if bil.empty:
            continue

        if "Tid" in bil.columns:
            bil = bil.sort_values(
                "Tid"
            )

        första_pris = (
            bil["Price"].iloc[0]
        )
        sista_pris = (
            bil["Price"].iloc[-1]
        )

        prisförändring = (
            sista_pris
            - första_pris
        )

        min_pris = bil[
            "Price"
        ].min()

        max_pris = bil[
            "Price"
        ].max()

        datum_första = "?"
        datum_sista = "?"

        if (
            "Tid" in bil.columns
            and bil["Tid"].notna().any()
        ):
            giltiga_datum = (
                bil["Tid"].dropna()
            )

            datum_första = (
                giltiga_datum
                .iloc[0]
                .strftime("%Y-%m-%d")
            )

            datum_sista = (
                giltiga_datum
                .iloc[-1]
                .strftime("%Y-%m-%d")
            )

        print(
            f"\n  {row.get('Model', '')} "
            f"{row.get('ModelYear', '')} "
            f"| {row.get('Mil', 0):,.0f} mil "
            f"| faktisk={row['Price']:,.0f} kr "
            f"| pred={row['Prediction']:,.0f} kr "
            f"| fel={row['Error']:+,.0f} kr"
        )

        print(
            f"    Historik: {len(bil)} obs | "
            f"{datum_första} → "
            f"{datum_sista} | "
            f"pris "
            f"{första_pris:,.0f} → "
            f"{sista_pris:,.0f} kr "
            f"({prisförändring:+,.0f} kr)"
        )

        print(
            f"    Prisintervall: "
            f"{min_pris:,.0f}–"
            f"{max_pris:,.0f} kr"
        )
