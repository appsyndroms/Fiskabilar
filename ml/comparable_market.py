import pandas as pd

from ml.model_diagnostics import (
    _skapa_diagnostik,
)


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
