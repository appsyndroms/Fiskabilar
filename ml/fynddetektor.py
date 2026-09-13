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


def _evidensvikt(jämförbara):
    """
    Beräknar hur starkt jämförelseunderlaget är.

    Antalet oberoende bilar ökar säkerheten, men många jämförelser
    är inte automatiskt bra om marknaden samtidigt är mycket spretig.

    Därför vägs två saker ihop:
      1. antal oberoende jämförelseobjekt
      2. hur samlade deras priser är
    """

    antal = len(jämförbara)

    if antal < MIN_COMPARABLES:
        return 0.0, 0.0

    priser = pd.to_numeric(
        jämförbara["_PriceNum"],
        errors="coerce",
    ).dropna()

    if priser.empty:
        return 0.0, 0.0

    median = float(
        priser.median()
    )

    if median <= 0:
        return 0.0, 0.0

    mad = float(
        (priser - median)
        .abs()
        .median()
    )

    robust_spread_pct = (
        mad
        / median
        * 100
    )

    n_confidence = min(
        1.0,
        antal / 10.0,
    )

    spread_confidence = 1.0 / (
        1.0
        + robust_spread_pct / 20.0
    )

    confidence = (
        n_confidence
        * spread_confidence
    )

    return (
        confidence,
        robust_spread_pct,
    )


def _get_ad_url(
    row,
    dataset=None,
):
    """
    Hämtar den mest aktuella annons-URL:en för fyndet.

    Om Identity finns i det fullständiga datasetet används alltid den
    senaste observationen för samma Identity. Det är viktigt eftersom
    en diagnostikrad kan bära med sig en äldre URL medan samma fysiska
    bil senare fått en ny annons-URL.

    Prioritet:
      1. senaste matchande observation i datasetet
      2. URL direkt på raden
      3. tom sträng
    """

    identity = row.get(
        "Identity"
    )

    if (
        dataset is not None
        and identity is not None
        and str(identity).strip()
        and "Identity" in dataset.columns
    ):
        identity_text = str(
            identity
        ).strip()

        matches = dataset[
            dataset["Identity"]
            .astype(str)
            .str.strip()
            == identity_text
        ].copy()

        if not matches.empty:

            if "Tid" in matches.columns:
                matches = matches.sort_values(
                    "Tid",
                    na_position="last",
                )

            for _, match in (
                matches.iloc[::-1]
                .iterrows()
            ):
                for key in (
                    "url",
                    "URL",
                    "ad_url",
                    "adUrl",
                    "annons_url",
                    "annonsUrl",
                    "listing_url",
                    "listingUrl",
                ):
                    value = match.get(
                        key
                    )

                    if (
                        value is not None
                        and str(value).strip()
                    ):
                        return str(
                            value
                        ).strip()

    for key in (
        "url",
        "URL",
        "ad_url",
        "adUrl",
        "annons_url",
        "annonsUrl",
        "listing_url",
        "listingUrl",
    ):
        value = row.get(
            key
        )

        if (
            value is not None
            and str(value).strip()
        ):
            return str(
                value
            ).strip()

    return ""


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

        faktisk_pris = float(
            row["Price"]
        )

        prediction_value = float(
            row["Prediction"]
        )

        viktad_median = _weighted_median(
            jämförbara["_PriceNum"],
            jämförbara["SimilarityWeight"],
        )

        if (
            pd.isna(viktad_median)
            or viktad_median <= 0
        ):
            continue

        model_signal_pct = (
            (
                prediction_value
                - faktisk_pris
            )
            / faktisk_pris
            * 100
            if faktisk_pris > 0
            else float("nan")
        )

        market_signal_pct = (
            (
                faktisk_pris
                - viktad_median
            )
            / viktad_median
            * 100
        )

        model_cheap = (
            model_signal_pct
            >= MODEL_THRESHOLD_PCT
        )

        market_cheap = (
            market_signal_pct
            <= MARKET_THRESHOLD_PCT
        )

        if not (
            model_cheap
            and market_cheap
        ):
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

        comparable_count = len(
            jämförbara
        )

        (
            evidence_confidence,
            robust_spread_pct,
        ) = _evidensvikt(
            jämförbara
        )

        fynd_score = (
            combined_score
            * (
                0.5
                + 0.5
                * evidence_confidence
            )
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
                "ModelVsActualPct": (
                    model_signal_pct
                ),
                "ComparableWeightedMedian": (
                    viktad_median
                ),
                "ComparableDeviationPct": (
                    market_signal_pct
                ),
                "ComparableN": (
                    comparable_count
                ),
                "CombinedScore": (
                    combined_score
                ),
                "EvidenceConfidence": (
                    evidence_confidence
                ),
                "ComparableRobustSpreadPct": (
                    robust_spread_pct
                ),
                "FyndScore": (
                    fynd_score
                ),

                # Viktigt:
                # URL hämtas från den senaste observationen
                # för samma Identity i hela datasetet.
                "url": _get_ad_url(
                    row,
                    dataset,
                ),

                "Identity": row.get(
                    "Identity",
                    "",
                ),
            }
        )

    if not resultat:
        return pd.DataFrame()

    fynd = (
        pd.DataFrame(resultat)
        .sort_values(
            [
                "FyndScore",
                "CombinedScore",
                "EvidenceConfidence",
                "ComparableN",
            ],
            ascending=[
                False,
                False,
                False,
                False,
            ],
        )
        .reset_index(
            drop=True
        )
    )

    fynd["Fyndklass"] = fynd[
        "FyndScore"
    ].map(
        _fyndklass
    )

    return fynd


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
    Kör fynddetektorn.

    Returnerar en rankad DataFrame med fynd.

    Funktionen skriver inte ut något och har inga sidoeffekter.
    """

    fynd = _bygg_fyndkandidater(
        dataset,
        test,
        prediction,
    )

    if fynd.empty:
        return fynd

    return fynd.head(
        max_results
    ).reset_index(
        drop=True
    )
