"""
Aktuella fynd.

Visar de bilar som ML-modellen identifierar
som särskilt intressanta fynd.
"""

import pandas as pd
import streamlit as st

from web.data import (
    hamta_senaste_fynd,
)


st.set_page_config(
    page_title="Blankdiss – Aktuella fynd",
    page_icon="🚗",
    layout="wide",
)


st.title(
    "🚗 Aktuella fynd"
)

st.caption(
    "Fynd identifieras genom en kombination av "
    "ML-värdering, jämförbara marknadspriser "
    "och styrkan i jämförelseunderlaget."
)


df = hamta_senaste_fynd()


if df.empty:

    st.info(
        "Inga aktuella fynd hittades."
    )

    st.stop()


# ------------------------------------------------------------
# NUMERISKA FÄLT
# ------------------------------------------------------------

for column in [
    "Price",
    "Prediction",
    "ModelVsActualPct",
    "ComparableWeightedMedian",
    "ComparableDeviationPct",
    "ComparableN",
    "CombinedScore",
    "EvidenceConfidence",
    "ComparableRobustSpreadPct",
    "FyndScore",
    "Mil",
]:

    if column in df.columns:

        df[column] = pd.to_numeric(
            df[column],
            errors="coerce",
        )


# ------------------------------------------------------------
# FILTER
# ------------------------------------------------------------

st.sidebar.header(
    "Filter"
)


if "Model" in df.columns:

    modeller = sorted(
        df["Model"]
        .dropna()
        .astype(str)
        .unique()
    )

    valda_modeller = (
        st.sidebar.multiselect(
            "Modell",
            modeller,
        )
    )

    if valda_modeller:

        df = df[
            df["Model"]
            .astype(str)
            .isin(
                valda_modeller
            )
        ]


if "FyndScore" in df.columns:

    min_score = st.sidebar.slider(
        "Minsta FyndScore",
        0.0,
        float(
            max(
                30,
                df["FyndScore"]
                .max(),
            )
        ),
        0.0,
    )

    df = df[
        df["FyndScore"]
        >= min_score
    ]


if df.empty:

    st.warning(
        "Inga fynd matchar filtreringen."
    )

    st.stop()


# ------------------------------------------------------------
# SORTERING
# ------------------------------------------------------------

if "FyndScore" in df.columns:

    df = df.sort_values(
        "FyndScore",
        ascending=False,
    )


# ------------------------------------------------------------
# KPI
# ------------------------------------------------------------

col1, col2, col3, col4 = (
    st.columns(4)
)


col1.metric(
    "Antal fynd",
    len(df),
)


if "FyndScore" in df.columns:

    col2.metric(
        "Högsta FyndScore",
        f"{df['FyndScore'].max():.1f}",
    )


if "ModelVsActualPct" in df.columns:

    col3.metric(
        "Bästa ML-gap",
        (
            f"+{df['ModelVsActualPct'].max():.1f} %"
        ),
    )


if "ComparableDeviationPct" in df.columns:

    col4.metric(
        "Bästa marknadsgap",
        (
            f"{df['ComparableDeviationPct'].min():.1f} %"
        ),
    )


st.divider()


# ------------------------------------------------------------
# TOPPFYND
# ------------------------------------------------------------

st.subheader(
    "🔥 Toppfynd"
)


for _, row in df.head(
    10
).iterrows():

    model = row.get(
        "Model",
        "Okänd bil",
    )

    variant = row.get(
        "Variant",
        "",
    )

    title = str(model)

    if pd.notna(variant) and str(
        variant
    ).strip():

        title += (
            f" {variant}"
        )


    with st.container():

        st.markdown(
            f"### {title}"
        )

        col1, col2, col3, col4 = (
            st.columns(4)
        )

        if pd.notna(
            row.get("Price")
        ):

            col1.metric(
                "Pris",
                (
                    f"{row['Price']:,.0f} kr"
                    .replace(",", " ")
                ),
            )


        if pd.notna(
            row.get("Prediction")
        ):

            col2.metric(
                "ML-värdering",
                (
                    f"{row['Prediction']:,.0f} kr"
                    .replace(",", " ")
                ),
            )


        if pd.notna(
            row.get("FyndScore")
        ):

            col3.metric(
                "FyndScore",
                f"{row['FyndScore']:.1f}",
            )


        if pd.notna(
            row.get("ModelVsActualPct")
        ):

            col4.metric(
                "ML-gap",
                (
                    f"+{row['ModelVsActualPct']:.1f} %"
                ),
            )


        col1, col2, col3 = (
            st.columns(3)
        )


        if pd.notna(
            row.get(
                "ComparableWeightedMedian"
            )
        ):

            col1.metric(
                "Jämförbart marknadsvärde",
                (
                    f"{row['ComparableWeightedMedian']:,.0f} kr"
                    .replace(",", " ")
                ),
            )


        if pd.notna(
            row.get(
                "ComparableDeviationPct"
            )
        ):

            col2.metric(
                "Marknadsgap",
                (
                    f"{row['ComparableDeviationPct']:.1f} %"
                ),
            )


        if pd.notna(
            row.get("EvidenceConfidence")
        ):

            col3.metric(
                "Evidens",
                (
                    f"{row['EvidenceConfidence']:.2f}"
                ),
            )


        if pd.notna(
            row.get("Fyndklass")
        ):

            st.write(
                f"**{row['Fyndklass']}**"
            )


        if pd.notna(
            row.get("ComparableN")
        ):

            st.caption(
                "Jämförelseobjekt: "
                f"{int(row['ComparableN'])}"
            )


        st.divider()


# ------------------------------------------------------------
# TABELL
# ------------------------------------------------------------

st.subheader(
    "Alla aktuella fynd"
)


display_columns = [
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
    "EvidenceConfidence",
    "CombinedScore",
]


display_columns = [
    column
    for column in display_columns
    if column in df.columns
]


st.dataframe(
    df[
        display_columns
    ],
    use_container_width=True,
    hide_index=True,
)
