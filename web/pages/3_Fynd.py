import streamlit as st
import pandas as pd

from data import load_current_findings


st.set_page_config(
    page_title="Fiskabilar – Fynd",
    page_icon="🔥",
    layout="wide",
)


st.title("Fynd")
st.caption("Bilar som bedöms vara särskilt intressanta just nu.")


df = load_current_findings()


if df.empty:
    st.info("Inga aktuella fynd hittades.")
    st.stop()


# ------------------------------------------------------------
# FILTER
# ------------------------------------------------------------

st.sidebar.header("Filter")

if "modell" in df.columns:

    modeller = sorted(
        df["modell"].dropna().unique()
    )

    valt_modell = st.sidebar.multiselect(
        "Modell",
        modeller,
    )

    if valt_modell:
        df = df[
            df["modell"].isin(valt_modell)
        ]


if "score" in df.columns:

    min_score = st.sidebar.slider(
        "Minsta score",
        0,
        100,
        0,
    )

    df = df[
        df["score"] >= min_score
    ]


if df.empty:
    st.warning("Inga fynd matchar filtreringen.")
    st.stop()


# ------------------------------------------------------------
# SORTERING
# ------------------------------------------------------------

if "score" in df.columns:
    df = df.sort_values(
        "score",
        ascending=False,
    )


# ------------------------------------------------------------
# KPI
# ------------------------------------------------------------

col1, col2, col3 = st.columns(3)

col1.metric(
    "Antal fynd",
    len(df),
)

if "score" in df.columns:
    col2.metric(
        "Högsta score",
        f"{df['score'].max():.0f}",
    )

if "prisdiff" in df.columns:
    col3.metric(
        "Största rabatt",
        f"{df['prisdiff'].max():,.0f} kr".replace(",", " "),
    )


# ------------------------------------------------------------
# TOPP-FYND
# ------------------------------------------------------------

st.divider()

st.subheader("Bästa fynd just nu")


for _, row in df.head(10).iterrows():

    modell = row.get(
        "modell",
        "Okänd bil",
    )

    pris = row.get(
        "pris",
        None,
    )

    score = row.get(
        "score",
        None,
    )

    prisdiff = row.get(
        "prisdiff",
        None,
    )

    with st.container():

        col1, col2, col3, col4 = st.columns(
            [3, 1, 1, 1]
        )

        col1.write(
            f"### {modell}"
        )

        if pris is not None:
            col2.metric(
                "Pris",
                f"{pris:,.0f} kr".replace(",", " "),
            )

        if score is not None:
            col3.metric(
                "Score",
                f"{score:.0f}",
            )

        if prisdiff is not None:
            col4.metric(
                "Under marknad",
                f"{prisdiff:,.0f} kr".replace(",", " "),
            )

        if "url" in row and pd.notna(row["url"]):
            st.link_button(
                "Öppna annons",
                row["url"],
            )

        st.divider()


# ------------------------------------------------------------
# FULL TABELL
# ------------------------------------------------------------

st.subheader("Alla aktuella fynd")

st.dataframe(
    df,
    use_container_width=True,
    hide_index=True,
)
