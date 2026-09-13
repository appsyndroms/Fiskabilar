import pandas as pd

from ml.comparable_market import (
    _jämförbara_observationer,
    _weighted_median,
)
from ml.model_diagnostics import _skapa_diagnostik


MODEL_THRESHOLD_PCT = 5.0
MARKET_THRESHOLD_PCT = -5.0
MIN_COMPARABLES = 3
MAX_RESULTS = 20


def _bygg_fyndkandidater(
    dataset,
    test,
    prediction,
):
    """
    Bygger en rankad lista över potentiella fynd.

    Ett fynd kräver att två oberoende signaler pekar åt samma håll:

      1. ML-modellen värderar bilen minst 5 % högre än annonspriset.
      2. Jämförbara bilar ligger minst 5 % högre än annonspriset.

    Fynddetektorn använder jämförelsemarknaden som ett oberoende
    marknadslager och använder inte modellens tidigare bias som en
    hårdkodad korrigering.
    """

    diagnostik = _skapa_diagnostik(
        test,
        prediction,
    )

    resultat = []

    for _, row in diagnostik.iterrows():
        jämförbara = _jämförbara_observationer(
            dataset,
            row,
            min_comparables=MIN_COMPARABLES,
        )

        if jämförbara.empty:
            continue

        faktisk_pris = float(row["Price"])
        prediction_value = float(row["Prediction"])

        viktad_median = _weighted_median(
            jämförbara["_PriceNum"],
            jämförbara["SimilarityWeight"],
        )

        if pd.isna(viktad_median) or viktad_median <= 0:
            continue

        model_signal_pct = (
            (prediction_value - faktisk_pris)
            / faktisk_pris
            * 100
            if faktisk_pris > 0
            else float("nan")
        )

        market_signal_pct = (
            (faktisk_pris - viktad_median)
            / viktad_median
            * 100
        )

        model_cheap = (
            model_signal_pct >= MODEL_THRESHOLD_PCT
        )

        market_cheap = (
            market_signal_pct <= MARKET_THRESHOLD_PCT
        )

        if not (model_cheap and market_cheap):
            continue

        model_gap_pct = max(
            0.0,
            model_signal_pct,
        )

        market_gap_pct = max(
            0.0,
            -market_signal_pct,
        )

        combined_score = (
            model_gap_pct
            + market_gap_pct
        )

        comparable_count = len(jämförbara)

        # 10 oberoende jämförelseobjekt ger full stabilitetsvikt.
        comparable_confidence = min(
            1.0,
            comparable_count / 10.0,
        )

        # Själva fyndpoängen består av:
        #
        # styrkan i ML-signalen
        # +
        # styrkan i marknadssignalen
        #
        # multiplicerat med hur mycket marknadsunderlag vi har.
        fynd_score = (
            combined_score
            * comparable_confidence
        )

        resultat.append(
            {
                "Model": row.get("Model", ""),
                "Variant": row.get("Variant", ""),
                "ModelYear": row.get("ModelYear", ""),
                "Mil": row.get("Mil", 0),
                "Price": faktisk_pris,
                "Prediction": prediction_value,
                "ModelVsActualPct": model_signal_pct,
                "ComparableWeightedMedian": viktad_median,
                "ComparableDeviationPct": market_signal_pct,
                "ComparableN": comparable_count,
                "CombinedScore": combined_score,
                "ComparableConfidence": comparable_confidence,
                "FyndScore": fynd_score,
                "Identity": row.get("Identity", ""),
            }
        )

    if not resultat:
        return pd.DataFrame()

    return (
        pd.DataFrame(resultat)
        .sort_values(
            [
                "FyndScore",
                "CombinedScore",
                "ComparableN",
            ],
            ascending=[
                False,
                False,
                False,
            ],
        )
        .reset_index(drop=True)
    )


def _fyndklass(score):
    if score >= 30:
        return "A – mycket starkt fynd"

    if score >= 20:
        return "B – starkt fynd"

    if score >= 12:
        return "C – intressant fynd"

    return "D – svagare fynd"


def detektera_fynd(
    dataset,
    test,
    prediction,
    max_results=MAX_RESULTS,
):
    """
    Kör den faktiska fynddetektorn och skriver en rankad shortlist.

    Resultatet returneras som DataFrame så att det senare kan
    användas för JSONL-export, notifieringar eller annan automation.
    """

    fynd = _bygg_fyndkandidater(
        dataset,
        test,
        prediction,
    )

    print("\n" + "=" * 70)
    print("FYNDPOSITION – AKTIV FYNDETEKTOR")
    print("=" * 70)

    if fynd.empty:
        print(
            "\nInga bilar uppfyller både ML- och "
            "jämförelsemarknadens fyndkriterier."
        )

        return fynd

    fynd["Fyndklass"] = fynd[
        "FyndScore"
    ].map(_fyndklass)

    print(
        f"\nFyndkandidater: {len(fynd)}"
    )

    print(
        f"Tröskel ML: "
        f"+{MODEL_THRESHOLD_PCT:.0f} %"
    )

    print(
        f"Tröskel marknad: "
        f"{MARKET_THRESHOLD_PCT:+.0f} %"
    )

    utskrift = (
        fynd
        .head(max_results)
        .copy()
    )

    for column in [
        "Price",
        "Prediction",
        "ComparableWeightedMedian",
    ]:
        utskrift[column] = utskrift[
            column
        ].map(
            lambda x:
            f"{x:,.0f} kr"
        )

    for column in [
        "ModelVsActualPct",
        "ComparableDeviationPct",
    ]:
        utskrift[column] = utskrift[
            column
        ].map(
            lambda x:
            f"{x:+.2f} %"
        )

    utskrift["CombinedScore"] = (
        utskrift["CombinedScore"]
        .map(
            lambda x:
            f"{x:.2f}"
        )
    )

    utskrift["ComparableConfidence"] = (
        utskrift[
            "ComparableConfidence"
        ]
        .map(
            lambda x:
            f"{x:.2f}"
        )
    )

    utskrift["FyndScore"] = (
        utskrift["FyndScore"]
        .map(
            lambda x:
            f"{x:.2f}"
        )
    )

    columns = [
        "Fyndklass",
        "FyndScore",
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
        "ComparableConfidence",
        "Identity",
    ]

    print("\nRankad fyndlista:")

    print(
        utskrift[
            columns
        ].to_string(
            index=False
        )
    )

    return fynd
