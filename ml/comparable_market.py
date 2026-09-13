import pandas as pd


MAX_JÄMFÖRBARA = 20


def _normalisera_text(value):
    if value is None or pd.isna(value):
        return ""

    return " ".join(
        str(value)
        .strip()
        .casefold()
        .split()
    )


def _weighted_median(
    values,
    weights,
):
    """
    Viktad median.

    Högre vikt innebär att observationen
    ligger närmare målobjektet.
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

    data = data[
        data["weight"] > 0
    ]

    if data.empty:
        return float("nan")

    data = data.sort_values(
        "value"
    )

    cumulative_weight = (
        data["weight"].cumsum()
    )

    cutoff = (
        data["weight"].sum()
        / 2
    )

    index = (
        cumulative_weight.searchsorted(
            cutoff,
            side="left",
        )
    )

    index = min(
        int(index),
        len(data) - 1,
    )

    return float(
        data.iloc[index]["value"]
    )


def _jämförbara_observationer(
    dataset,
    row,
    max_year_diff=1,
    max_mileage_diff=1500,
    min_comparables=3,
    max_jämförbara=MAX_JÄMFÖRBARA,
):
    """
    Hittar jämförbara observationer.

    Matchning:

      Model + Variant
      årsmodell ±1
      miltal ±1500

    Samma fordon exkluderas via Identity.

    För varje unik Identity används
    högst en observation.

    Den tidsmässigt närmaste observationen
    används när målobjektets Tid finns.

    Därefter används endast de
    max_jämförbara mest lika
    oberoende bilarna.

    Observationer utan Identity används
    inte som jämförelseobjekt.
    """

    required = {
        "Model",
        "ModelYear",
        "Mil",
        "Price",
    }

    if not required.issubset(
        dataset.columns
    ):
        return pd.DataFrame()

    model = _normalisera_text(
        row.get("Model")
    )

    variant = _normalisera_text(
        row.get("Variant")
    )

    model_year = pd.to_numeric(
        pd.Series(
            [row.get("ModelYear")]
        ),
        errors="coerce",
    ).iloc[0]

    mileage = pd.to_numeric(
        pd.Series(
            [row.get("Mil")]
        ),
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

    kandidater["_ModelYearNum"] = (
        pd.to_numeric(
            kandidater["ModelYear"],
            errors="coerce",
        )
    )

    kandidater["_MilNum"] = (
        pd.to_numeric(
            kandidater["Mil"],
            errors="coerce",
        )
    )

    kandidater["_PriceNum"] = (
        pd.to_numeric(
            kandidater["Price"],
            errors="coerce",
        )
    )

    if "Tid" in kandidater.columns:
        kandidater["_Tid"] = (
            pd.to_datetime(
                kandidater["Tid"],
                errors="coerce",
                utc=True,
            )
        )
    else:
        kandidater["_Tid"] = pd.NaT

    target_tid = pd.to_datetime(
        row.get("Tid"),
        errors="coerce",
        utc=True,
    )

    kandidater = kandidater[
        kandidater["_ModelNorm"]
        == model
    ].copy()

    if variant:
        kandidater = kandidater[
            kandidater["_VariantNorm"]
            == variant
        ].copy()

    kandidater = kandidater[
        kandidater["_ModelYearNum"].between(
            model_year - max_year_diff,
            model_year + max_year_diff,
        )
    ]

    kandidater = kandidater[
        (
            kandidater["_MilNum"]
            - mileage
        ).abs().le(
            max_mileage_diff
        )
    ]

    kandidater = kandidater[
        kandidater["_PriceNum"].notna()
    ].copy()

    if "Identity" not in kandidater.columns:
        return pd.DataFrame()

    kandidater["_IdentityNorm"] = (
        kandidater["Identity"]
        .fillna("")
        .astype(str)
        .str.strip()
    )

    kandidater = kandidater[
        kandidater["_IdentityNorm"].ne("")
    ].copy()

    if kandidater.empty:
        return pd.DataFrame()

    identity = row.get("Identity")

    if (
        identity is not None
        and not pd.isna(identity)
        and str(identity).strip()
    ):
        kandidater = kandidater[
            kandidater["_IdentityNorm"]
            != str(identity).strip()
        ].copy()

    if kandidater.empty:
        return pd.DataFrame()

    kandidater["MileageDifference"] = (
        kandidater["_MilNum"]
        - mileage
    ).abs()

    kandidater["YearDifference"] = (
        kandidater["_ModelYearNum"]
        - model_year
    ).abs()

    kandidater["SimilarityDistance"] = (
        kandidater["MileageDifference"]
        + kandidater["YearDifference"]
        * 1500
    )

    kandidater["SimilarityWeight"] = (
        1
        / (
            250
            + kandidater[
                "SimilarityDistance"
            ]
        )
    )

    if pd.notna(target_tid):
        kandidater["_TimeDifference"] = (
            kandidater["_Tid"]
            - target_tid
        ).abs()

        kandidater["_HasValidTime"] = (
            kandidater[
                "_TimeDifference"
            ].notna()
        )

        kandidater = kandidater.sort_values(
            [
                "_IdentityNorm",
                "_HasValidTime",
                "_TimeDifference",
                "SimilarityDistance",
                "MileageDifference",
                "YearDifference",
            ],
            ascending=[
                True,
                False,
                True,
                True,
                True,
                True,
            ],
        )

    else:
        kandidater = kandidater.sort_values(
            [
                "_IdentityNorm",
                "SimilarityDistance",
                "MileageDifference",
                "YearDifference",
            ],
            ascending=True,
        )

    kandidater = (
        kandidater
        .drop_duplicates(
            subset="_IdentityNorm",
            keep="first",
        )
        .copy()
    )

    kandidater = kandidater.sort_values(
        [
            "SimilarityDistance",
            "MileageDifference",
            "YearDifference",
        ],
        ascending=[
            True,
            True,
            True,
        ],
    )

    kandidater = (
        kandidater
        .head(max_jämförbara)
        .reset_index(drop=True)
    )

    if len(kandidater) < min_comparables:
        return pd.DataFrame()

    return kandidater
