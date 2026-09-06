"""
Marknadshistorik.

Visar historiska annonser och marknadsutveckling
från Fiskabilars marknadshistorik.
"""

import pandas as pd
import streamlit as st

from web.charts import (
    annonser_over_tid,
    pris_mot_miltal,
    pris_over_tid,
    prisfordelning,
)
from web.data import (
    hamta_historik,
)
from web.styles import (
    apply_styles,
)


st.set_page_config(
    page_title="Fiskabilar – Marknadshistorik",
    page_icon="🕒",
    layout="wide",
)

apply_styles()


st.title(
    "🕒 Marknadshistorik"
)

st.caption(
    "Analys av historiska bilannonser "
    "från Fiskabilar."
)


df = hamta_historik()


if df.empty:
    st.warning(
        "Ingen historisk marknadsdata hittades."
    )

    st.stop()


# ------------------------------------------------------------
# NORMALISERA
# ------------------------------------------------------------

for kolumn in [
    "arsmodell",
    "miltal",
    "annonspris",
    "pris",
]:
    if kolumn in df.columns:
        df[kolumn] = pd.to_numeric(
            df[kolumn],
            errors="coerce",
        )


# ------------------------------------------------------------
# FILTER
# ------------------------------------------------------------

st.sidebar.header(
    "Filter"
)


if "marke" in df.columns:
    marken = sorted(
        df["marke"]
        .dropna()
        .astype(str)
        .unique()
    )

    valt_marke = st.sidebar.multiselect(
        "Märke",
        marken,
    )

    if valt_marke:
        df = df[
            df["marke"]
            .astype(str)
            .isin(
                valt_marke
            )
        ]


if "modell" in df.columns:
    modeller = sorted(
        df["modell"]
        .dropna()
        .astype(str)
        .unique()
    )

    valt_modell = st.sidebar.multiselect(
        "Modell",
        modeller,
    )

    if valt_modell:
        df = df[
            df["modell"]
            .astype(str)
            .isin(
                valt_modell
            )
        ]


if "variant" in df.columns:
    varianter = sorted(
        df["variant"]
        .dropna()
        .astype(str)
        .unique()
    )

    valt_variant = st.sidebar.multiselect(
        "Variant",
        varianter,
    )

    if valt_variant:
        df = df[
            df["variant"]
            .astype(str)
            .isin(
                valt_variant
            )
        ]


if "arsmodell" in df.columns:
    ar = df[
        "arsmodell"
    ].dropna()

    if not ar.empty:
        min_year = int(
            ar.min()
        )

        max_year = int(
            ar.max()
        )

        if min_year < max_year:
            valt_ar = st.sidebar.slider(
                "Årsmodell",
                min_year,
                max_year,
                (
                    min_year,
                    max_year,
                ),
            )

            df = df[
                df["arsmodell"].between(
                    valt_ar[0],
                    valt_ar[1],
                )
            ]


if "miltal" in df.columns:
    mil = df[
        "miltal"
    ].dropna()

    if not mil.empty:
        min_mil = int(
            mil.min()
        )

        max_mil = int(
            mil.max()
        )

        if min_mil < max_mil:
            valt_mil = st.sidebar.slider(
                "Miltal",
                min_mil,
                max_mil,
                (
                    min_mil,
                    max_mil,
                ),
            )

            df = df[
                df["miltal"].between(
                    valt_mil[0],
                    valt_mil[1],
                )
            ]


if df.empty:
    st.warning(
        "Inga annonser matchar filtreringen."
    )

    st.stop()


# ------------------------------------------------------------
# KPI
# ------------------------------------------------------------

col1, col2, col3, col4 = st.columns(
    4
)


col1.metric(
    "Observationer",
    f"{len(df):,}".replace(
        ",",
        " ",
    ),
)


priskolumn = (
    "annonspris"
    if "annonspris" in df.columns
    else (
        "pris"
        if "pris" in df.columns
        else None
    )
)


if priskolumn:
    pris = df[
        priskolumn
    ].dropna()

    col2.metric(
        "Medianpris",
        (
            f"{pris.median():,.0f} kr"
            .replace(
                ",",
                " ",
            )
            if not pris.empty
            else "—"
        ),
    )

    col3.metric(
        "Snittpris",
        (
            f"{pris.mean():,.0f} kr"
            .replace(
                ",",
                " ",
            )
            if not pris.empty
            else "—"
        ),
    )


if "miltal" in df.columns:
    mil = df[
        "miltal"
    ].dropna()

    col4.metric(
        "Median mil",
        (
            f"{mil.median():,.0f}"
            .replace(
                ",",
                " ",
            )
            if not mil.empty
            else "—"
        ),
    )


st.divider()


# ------------------------------------------------------------
# PRISUTVECKLING
# ------------------------------------------------------------

st.subheader(
    "📈 Pris över tid"
)

fig = pris_over_tid(
    df
)

if fig is not None:
    st.plotly_chart(
        fig,
        use_container_width=True,
    )


# ------------------------------------------------------------
# ANTAL ANNONSER
# ------------------------------------------------------------

st.subheader(
    "📊 Marknadsaktivitet"
)

fig = annonser_over_tid(
    df
)

if fig is not None:
    st.plotly_chart(
        fig,
        use_container_width=True,
    )


# ------------------------------------------------------------
# PRIS MOT MILTAL
# ------------------------------------------------------------

left, right = st.columns(
    2
)


with left:
    st.subheader(
        "🚗 Pris mot miltal"
    )

    fig = pris_mot_miltal(
        df
    )

    if fig is not None:
        st.plotly_chart(
            fig,
            use_container_width=True,
        )


with right:
    st.subheader(
        "💰 Prisfördelning"
    )

    fig = prisfordelning(
        df
    )

    if fig is not None:
        st.plotly_chart(
            fig,
            use_container_width=True,
        )


st.divider()


# ------------------------------------------------------------
# TABELL
# ------------------------------------------------------------

st.subheader(
    "Marknadsdata"
)


st.dataframe(
    df,
    use_container_width=True,
    hide_index=True,
)
