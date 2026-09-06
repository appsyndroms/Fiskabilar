import streamlit as st
import pandas as pd

from data import load_market_history
from charts import price_over_time, price_vs_mileage


st.set_page_config(
    page_title="Fiskabilar – Marknad",
    page_icon="📊",
    layout="wide",
)


st.title("Marknadsanalys")
st.caption("Analys av historiska bilannonser från Fiskabilar.")


df = load_market_history()

if df.empty:
    st.warning("Ingen historisk marknadsdata hittades.")
    st.stop()


# ------------------------------------------------------------
# FILTER
# ------------------------------------------------------------

st.sidebar.header("Filter")

if "marke" in df.columns:
    marken = sorted(df["marke"].dropna().unique())
    valt_marke = st.sidebar.multiselect(
        "Märke",
        marken,
    )

    if valt_marke:
        df = df[df["marke"].isin(valt_marke)]


if "modell" in df.columns:
    modeller = sorted(df["modell"].dropna().unique())
    valt_modell = st.sidebar.multiselect(
        "Modell",
        modeller,
    )

    if valt_modell:
        df = df[df["modell"].isin(valt_modell)]


if "arsmodell" in df.columns:
    min_year = int(df["arsmodell"].min())
    max_year = int(df["arsmodell"].max())

    valt_ar = st.sidebar.slider(
        "Årsmodell",
        min_year,
        max_year,
        (min_year, max_year),
    )

    df = df[
        df["arsmodell"].between(
            valt_ar[0],
            valt_ar[1],
        )
    ]


if "mil" in df.columns and not df.empty:
    min_mil = int(df["mil"].min())
    max_mil = int(df["mil"].max())

    valt_mil = st.sidebar.slider(
        "Miltal",
        min_mil,
        max_mil,
        (min_mil, max_mil),
    )

    df = df[
        df["mil"].between(
            valt_mil[0],
            valt_mil[1],
        )
    ]


if df.empty:
    st.warning("Inga annonser matchar filtreringen.")
    st.stop()


# ------------------------------------------------------------
# KPI
# ------------------------------------------------------------

col1, col2, col3, col4 = st.columns(4)

col1.metric(
    "Annonser",
    f"{len(df):,}".replace(",", " "),
)

if "pris" in df.columns:
    median_price = df["pris"].median()
    mean_price = df["pris"].mean()

    col2.metric(
        "Medianpris",
        f"{median_price:,.0f} kr".replace(",", " "),
    )

    col3.metric(
        "Snittpris",
        f"{mean_price:,.0f} kr".replace(",", " "),
    )

if "mil" in df.columns:
    col4.metric(
        "Median mil",
        f"{df['mil'].median():,.0f}".replace(",", " "),
    )


# ------------------------------------------------------------
# GRAFER
# ------------------------------------------------------------

st.divider()

if "datum" in df.columns and "pris" in df.columns:
    st.subheader("Prisutveckling")

    fig = price_over_time(df)
    st.plotly_chart(
        fig,
        use_container_width=True,
    )


if "mil" in df.columns and "pris" in df.columns:
    st.subheader("Pris kontra miltal")

    fig = price_vs_mileage(df)
    st.plotly_chart(
        fig,
        use_container_width=True,
    )


# ------------------------------------------------------------
# TABELL
# ------------------------------------------------------------

st.subheader("Marknadsdata")

st.dataframe(
    df,
    use_container_width=True,
    hide_index=True,
)
