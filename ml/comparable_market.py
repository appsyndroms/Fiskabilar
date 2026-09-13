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


def _diagnostik_fyndprofil(result):
    """
    Analyserar observationer där både
    Random Forest och jämförelsemarknaden
    signalerar undervärdering.

    Detta är diagnostik-only.

    Syftet är att hitta strukturella
    mönster i fynden innan själva
    fynddetektorn byggs.
    """

    if result.empty:
        return

    dubbla = result[
        result["DoubleUndervaluation"]
    ].copy()

    if dubbla.empty:
        print(
            "\nFyndprofil: "
            "inga dubbla signaler."
        )
        return

    dubbla["CombinedScore"] = (
        dubbla[
            "ModelVsActualPct"
        ].clip(lower=0)
        + (
            -dubbla[
                "ComparableDeviationPct"
            ]
        ).clip(lower=0)
    )

    dubbla["MileageBand"] = pd.cut(
        dubbla["Mil"],
        bins=[
            -float("inf"),
            2000,
            4000,
            6000,
            8000,
            10000,
            float("inf"),
        ],
        labels=[
            "<2 000",
            "2 000–3 999",
            "4 000–5 999",
            "6 000–7 999",
            "8 000–9 999",
            "10 000+",
        ],
    )

    dubbla["PriceBand"] = pd.cut(
        dubbla["Price"],
        bins=[
            -float("inf"),
            350000,
            400000,
            450000,
            500000,
            600000,
            float("inf"),
        ],
        labels=[
            "<350k",
            "350–399k",
            "400–449k",
            "450–499k",
            "500–599k",
            "600k+",
        ],
    )

    print("\n" + "=" * 70)
    print(
        "FYNDPOSITION – PROFIL "
        "FÖR DUBBLA SIGNALER"
    )
    print("=" * 70)

    print(
        f"\nAntal dubbelsignaler: "
        f"{len(dubbla)} "
        f"av {len(result)} "
        f"jämförbara testobservationer "
        f"({len(dubbla) / len(result) * 100:.1f} %)"
    )

    print(
        "Median ML-signal: "
        f"{dubbla['ModelVsActualPct'].median():+.2f} %"
    )

    print(
        "Median marknadssignal: "
        f"{dubbla['ComparableDeviationPct'].median():+.2f} %"
    )

    print(
        "Median CombinedScore: "
        f"{dubbla['CombinedScore'].median():.2f}"
    )

    print(
        "90-percentil CombinedScore: "
        f"{dubbla['CombinedScore'].quantile(0.90):.2f}"
    )

    def print_group(
        title,
        grouped,
    ):
        print(f"\n{title}")
        print(
            grouped.to_string(
                index=False,
                formatters={
                    "MedianScore":
                        lambda x:
                        f"{x:.2f}",
                    "MedianML":
                        lambda x:
                        f"{x:+.2f} %",
                    "MedianMarknad":
                        lambda x:
                        f"{x:+.2f} %",
                    "MedianPris":
                        lambda x:
                        f"{x:,.0f} kr",
                    "MedianMil":
                        lambda x:
                        f"{x:,.0f}",
                },
            )
        )

    model_columns = [
        column
        for column in [
            "Model",
            "Variant",
        ]
        if column in dubbla.columns
    ]

    if model_columns:
        grouped = (
            dubbla.groupby(
                model_columns,
                dropna=False,
            )
            .agg(
                Fynd=(
                    "CombinedScore",
                    "size",
                ),
                MedianScore=(
                    "CombinedScore",
                    "median",
                ),
                MedianML=(
                    "ModelVsActualPct",
                    "median",
                ),
                MedianMarknad=(
                    "ComparableDeviationPct",
                    "median",
                ),
                MedianPris=(
                    "Price",
                    "median",
                ),
                MedianMil=(
                    "Mil",
                    "median",
                ),
            )
            .reset_index()
            .sort_values(
                "Fynd",
                ascending=False,
            )
        )

        print_group(
            "\nProfil per modell/variant:",
            grouped,
        )

    grouped = (
        dubbla.groupby(
            "ModelYear",
            dropna=False,
        )
        .agg(
            Fynd=(
                "CombinedScore",
                "size",
            ),
            MedianScore=(
                "CombinedScore",
                "median",
            ),
            MedianML=(
                "ModelVsActualPct",
                "median",
            ),
            MedianMarknad=(
                "ComparableDeviationPct",
                "median",
            ),
            MedianPris=(
                "Price",
                "median",
            ),
        )
        .reset_index()
        .sort_values(
            "Fynd",
            ascending=False,
        )
    )

    print_group(
        "Profil per årsmodell:",
        grouped,
    )

    grouped = (
        dubbla.groupby(
            "MileageBand",
            observed=False,
        )
        .agg(
            Fynd=(
                "CombinedScore",
                "size",
            ),
            MedianScore=(
                "CombinedScore",
                "median",
            ),
            MedianML=(
                "ModelVsActualPct",
                "median",
            ),
            MedianMarknad=(
                "ComparableDeviationPct",
                "median",
            ),
            MedianPris=(
                "Price",
                "median",
            ),
        )
        .reset_index()
        .sort_values(
            "Fynd",
            ascending=False,
        )
    )

    print_group(
        "Profil per miltal:",
        grouped,
    )

    grouped = (
        dubbla.groupby(
            "PriceBand",
            observed=False,
        )
        .agg(
            Fynd=(
                "CombinedScore",
                "size",
            ),
            MedianScore=(
                "CombinedScore",
                "median",
            ),
            MedianML=(
                "ModelVsActualPct",
                "median",
            ),
            MedianMarknad=(
                "ComparableDeviationPct",
                "median",
            ),
            MedianMil=(
                "Mil",
                "median",
            ),
        )
        .reset_index()
        .sort_values(
            "Fynd",
            ascending=False,
        )
    )

    print_group(
        "Profil per prisnivå:",
        grouped,
    )

    grouped = (
        dubbla.groupby(
            "ComparableN",
            dropna=False,
        )
        .agg(
            Fynd=(
                "CombinedScore",
                "size",
            ),
            MedianScore=(
                "CombinedScore",
                "median",
            ),
            MedianML=(
                "ModelVsActualPct",
                "median",
            ),
            MedianMarknad=(
                "ComparableDeviationPct",
                "median",
            ),
        )
        .reset_index()
        .sort_values(
            "ComparableN"
        )
    )

    print_group(
        "Profil per antal jämförelseobjekt:",
        grouped,
    )

    print(
        "\nTopp 20 starkaste dubbelsignaler:"
    )

    topp = (
        dubbla
        .sort_values(
            "CombinedScore",
            ascending=False,
        )
        .head(20)
        .copy()
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
        "Identity",
    ]

    kolumner = [
        column
        for column in kolumner
        if column in topp.columns
    ]

    utskrift = topp[
        kolumner
    ].copy()

    for column in [
        "Price",
        "Prediction",
        "ComparableWeightedMedian",
    ]:
        if column in utskrift.columns:
            utskrift[column] = (
                utskrift[column].map(
                    lambda x:
                    f"{x:,.0f} kr"
                )
            )

    for column in [
        "ModelVsActualPct",
        "ComparableDeviationPct",
    ]:
        if column in utskrift.columns:
            utskrift[column] = (
                utskrift[column].map(
                    lambda x:
                    f"{x:+.2f} %"
                )
            )

    if "CombinedScore" in utskrift.columns:
        utskrift["CombinedScore"] = (
            utskrift[
                "CombinedScore"
            ].map(
                lambda x:
                f"{x:.2f}"
            )
        )

    print(
        utskrift.to_string(
            index=False
        )
    )


def _diagnostik_jämförbar_marknad(
    dataset,
    test,
    prediction,
):
    """
    Analyserar hur testbilarna ligger
    prismässigt mot jämförbara annonser.

    Matchning:
      - samma Model
      - samma Variant när Variant finns
      - årsmodell ±1
      - miltal ±1500
      - högst en observation per unik Identity
      - tidsmässigt närmaste observation
      - högst 20 oberoende bilar
      - minst 3 jämförelseobjekt

    Jämförelsepris:
      - median
      - viktad median
      - Q25
      - Q75

    Dessutom identifieras fall där:
      1. Random Forest tycker att bilen är billig
      2. marknaden samtidigt tycker
         att bilen är billig

    Detta är diagnostik-only.
    """

    required = {
        "Model",
        "ModelYear",
        "Mil",
        "Price",
    }

    if not required.issubset(
        test.columns
    ):
        return

    diagnostik = _skapa_diagnostik(
        test,
        prediction,
    )

    resultat = []

    for _, row in (
        diagnostik.iterrows()
    ):
        jämförbara = (
            _jämförbara_observationer(
                dataset,
                row,
            )
        )

        if jämförbara.empty:
            continue

        priser = (
            jämförbara["_PriceNum"]
        )

        medianpris = priser.median()

        viktad_median = (
            _weighted_median(
                jämförbara[
                    "_PriceNum"
                ],
                jämförbara[
                    "SimilarityWeight"
                ],
            )
        )

        q25 = priser.quantile(0.25)
        q75 = priser.quantile(0.75)

        faktisk_pris = float(
            row["Price"]
        )

        prediction_value = float(
            row["Prediction"]
        )

        avvikelse_kr = (
            faktisk_pris
            - viktad_median
        )

        avvikelse_procent = (
            avvikelse_kr
            / viktad_median
            * 100
            if viktad_median
            else float("nan")
        )

        model_vs_actual_kr = (
            prediction_value
            - faktisk_pris
        )

        model_vs_actual_pct = (
            model_vs_actual_kr
            / faktisk_pris
            * 100
            if faktisk_pris
            else float("nan")
        )

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
                "Model": row.get(
                    "Model",
                    "",
                ),
                "Variant": row.get(
                    "Variant",
                    "",
                ),
                "ModelYear": row.get(
                    "ModelYear",
                    "",
                ),
                "Mil": row.get(
                    "Mil",
                    0,
                ),
                "Price": faktisk_pris,
                "Prediction": prediction_value,
                "ModelError": row["Error"],
                "ModelVsActualPct":
                    model_vs_actual_pct,
                "ComparableN":
                    len(jämförbara),
                "ComparableMedian":
                    medianpris,
                "ComparableWeightedMedian":
                    viktad_median,
                "ComparableQ25":
                    q25,
                "ComparableQ75":
                    q75,
                "ComparableDeviation":
                    avvikelse_kr,
                "ComparableDeviationPct":
                    avvikelse_procent,
                "ModelCheap":
                    model_cheap,
                "MarketCheap":
                    market_cheap,
                "DoubleUndervaluation":
                    double_undervaluation,
                "Identity": row.get(
                    "Identity",
                    "",
                ),
            }
        )

    if not resultat:
        print(
            "Jämförbar marknad: "
            "inga testbilar hade "
            "minst tre tillräckligt "
            "lika och oberoende "
            "jämförelseobjekt."
        )
        return

    result = pd.DataFrame(
        resultat
    )

    print(
        "\nJämförbar marknad – "
        "diagnostik:"
    )

    print(
        f"  Testobservationer: "
        f"{len(test)}"
    )

    print(
        "  Med minst 3 oberoende "
        "jämförelseobjekt: "
        f"{len(result)}"
    )

    print(
        "  Medianavvikelse mot "
        "jämförelsemarknad: "
        f"{result['ComparableDeviationPct'].median():+.2f} %"
    )

    result["PotentialBargain"] = (
        result[
            "ComparableDeviationPct"
        ] <= -5
    )

    print(
        "  Under -5 % mot "
        "marknadsmedian: "
        f"{int(result['PotentialBargain'].sum())}"
    )

    print(
        "  RF minst 5 % över "
        "faktiskt pris: "
        f"{int(result['ModelCheap'].sum())}"
    )

    print(
        "  Både RF + marknad "
        "signalerar fynd: "
        f"{int(result['DoubleUndervaluation'].sum())}"
    )

    dubbla = result[
        result["DoubleUndervaluation"]
    ].copy()

    if not dubbla.empty:
        dubbla["CombinedScore"] = (
            dubbla[
                "ModelVsActualPct"
            ].clip(lower=0)
            + (
                -dubbla[
                    "ComparableDeviationPct"
                ]
            ).clip(lower=0)
        )

        dubbla = dubbla.sort_values(
            "CombinedScore",
            ascending=False,
        )

    print(
        "\nStarkaste fynd – "
        "både ML-modell och "
        "jämförelsemarknad:"
    )

    if dubbla.empty:
        print(
            "  Inga objekt uppfyller "
            "båda kriterierna."
        )

    else:
        utskrift = (
            dubbla.head(20)
            .copy()
        )

        for column in [
            "Price",
            "Prediction",
            "ComparableWeightedMedian",
        ]:
            utskrift[column] = (
                utskrift[column].map(
                    lambda x:
                    f"{x:,.0f} kr"
                )
            )

        utskrift[
            "ModelVsActualPct"
        ] = (
            utskrift[
                "ModelVsActualPct"
            ].map(
                lambda x:
                f"{x:+.2f} %"
            )
        )

        utskrift[
            "ComparableDeviationPct"
        ] = (
            utskrift[
                "ComparableDeviationPct"
            ].map(
                lambda x:
                f"{x:+.2f} %"
            )
        )

        utskrift[
            "CombinedScore"
        ] = (
            utskrift[
                "CombinedScore"
            ].map(
                lambda x:
                f"{x:.2f}"
            )
        )

        utskrift["ModelError"] = (
            utskrift[
                "ModelError"
            ].map(
                lambda x:
                f"{x:+,.0f} kr"
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
            utskrift[
                kolumner
            ].to_string(
                index=False
            )
        )

    fynd = result[
        result[
            "ComparableDeviationPct"
        ] < 0
    ].copy()

    fynd = fynd.sort_values(
        "ComparableDeviationPct"
    )

    print(
        "\nStarkaste marknadsfynd:"
    )

    if fynd.empty:
        print(
            "  Inga testbilar ligger "
            "under jämförelsemedianen."
        )

    else:
        utskrift = (
            fynd.head(20)
            .copy()
        )

        for column in [
            "Price",
            "Prediction",
            "ComparableWeightedMedian",
        ]:
            utskrift[column] = (
                utskrift[column].map(
                    lambda x:
                    f"{x:,.0f} kr"
                )
            )

        utskrift[
            "ComparableDeviation"
        ] = (
            utskrift[
                "ComparableDeviation"
            ].map(
                lambda x:
                f"{x:+,.0f} kr"
            )
        )

        utskrift[
            "ComparableDeviationPct"
        ] = (
            utskrift[
                "ComparableDeviationPct"
            ].map(
                lambda x:
                f"{x:+.2f} %"
            )
        )

        utskrift[
            "ModelVsActualPct"
        ] = (
            utskrift[
                "ModelVsActualPct"
            ].map(
                lambda x:
                f"{x:+.2f} %"
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
            utskrift[
                kolumner
            ].to_string(
                index=False
            )
        )

    if "Model" in result.columns:
        print(
            "\nJämförbar marknad "
            "per modell/variant:"
        )

        group_columns = [
            "Model"
        ]

        if (
            "Variant"
            in result.columns
            and result["Variant"]
            .fillna("")
            .astype(str)
            .str.strip()
            .ne("")
            .any()
        ):
            group_columns.append(
                "Variant"
            )

        grupper = (
            result.groupby(
                group_columns
            )
            .agg(
                n=(
                    "ComparableDeviationPct",
                    "size",
                ),
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
                        lambda x:
                        f"{x:+.2f} %",
                },
            )
        )

    _diagnostik_fyndprofil(
        result
    )
