"""
Prissänkningar.

Visar fynd som har fått observerade
prissänkningar efter fyndögonblicket.
"""

import pandas as pd
import streamlit as st

from web.charts import (
    prissankningar_diagram,
)
from web.data import (
    hamta_prissankningar,
)
from web.styles import (
    apply_styles,
)


st.set_page_config(
    page_title="Fiskabilar – Prissänkningar",
    page_icon="📉",
    layout="wide",
)

apply_styles()


st.title(
    "📉 Prissänkningar"
)

st.caption(
    "Observerad prisutveckling för tidigare fynd."
)


df = hamta_prissankningar()


if df.empty:
    st.info(
        "Inga observerade prissänkningar ännu."
    )

    st.stop()


# ------------------------------------------------------------
# NORMALISERA
# ------------------------------------------------------------

for kolumn in [
    "total_prissankning",
    "procent_prissankning",
    "dagar_till_prissankning",
    "score",
    "diff",
]:
    if kolumn in df.columns:
        df[kolumn] = pd.to_numeric(
            df[kolumn],
            errors="coerce",
        )


# ------------------------------------------------------------
# KPI
# ------------------------------------------------------------

col1, col2, col3, col4 = st.columns(
    4
)


col1.metric(
    "Antal fynd",
    len(df),
)


if "total_prissankning" in df.columns:
    sankningar = df[
        "total_prissankning"
    ].dropna()

    col2.metric(
        "Total prissänkning",
        (
            f"{sankningar.sum():,.0f} kr"
            .replace(
                ",",
                " ",
            )
            if not sankningar.empty
            else "—"
        ),
    )

    col3.metric(
        "Största sänkning",
        (
            f"{sankningar.max():,.0f} kr"
            .replace(
                ",",
                " ",
            )
            if not sankningar.empty
            else "—"
        ),
    )


if "dagar_till_prissankning" in df.columns:
    dagar = df[
        "dagar_till_prissankning"
    ].dropna()

    col4.metric(
        "Median dagar till sänkning",
        (
            f"{dagar.median():.1f}"
            if not dagar.empty
            else "—"
        ),
    )


st.divider()


# ------------------------------------------------------------
# DIAGRAM
# ------------------------------------------------------------

fig = prissankningar_diagram(
    df
)

if fig is not None:
    st.plotly_chart(
        fig,
        use_container_width=True,
    )


# ------------------------------------------------------------
# TABELL
# ------------------------------------------------------------

st.subheader(
    "Observerade prissänkningar"
)


visa_kolumner = [
    kolumn
    for kolumn in [
        "modell",
        "arsmodell",
        "score",
        "diff",
        "initialpris",
        "lagsta_pris",
        "total_prissankning",
        "procent_prissankning",
        "dagar_till_prissankning",
        "utfall",
    ]
    if kolumn in df.columns
]


if visa_kolumner:
    visa = df[
        visa_kolumner
    ].copy()

else:
    visa = df.copy()


if "total_prissankning" in visa.columns:
    visa = visa.sort_values(
        "total_prissankning",
        ascending=False,
    )


st.dataframe(
    visa,
    use_container_width=True,
    hide_index=True,
)
