import streamlit as st
from web.data import hamta_historik
from web.charts import (
    pris_over_tid,
    pris_mot_miltal,
)
st.set_page_config(
    page_title="Fiskabilar – Marknad",
    page_icon="📊",
    layout="wide",
)
st.title("Marknadsanalys")
st.caption(
    "Analys av historiska bilannonser från Fiskabilar."
)
df = hamta_historik()
if df.empty:
    st.warning(
        "Ingen historisk marknadsdata hittades."
    )
    st.stop()
# ------------------------------------------------------------
# NORMALISERA NUMERISKA FÄLT
# ------------------------------------------------------------
if "arsmodell" in df.columns:
    df["arsmodell"] = pd.to_numeric(
        df["arsmodell"],
        errors="coerce",
    )
if "miltal" in df.columns:
    df["miltal"] = pd.to_numeric(
        df["miltal"],
        errors="coerce",
    )
if "annonspris" in df.columns:
    df["annonspris"] = pd.to_numeric(
        df["annonspris"],
        errors="coerce",
    )
# ------------------------------------------------------------
# FILTER
# ------------------------------------------------------------
st.sidebar.header("Filter")
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
            df["marke"].astype(str).isin(
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
            df["modell"].astype(str).isin(
                valt_modell
            )
        ]
if "arsmodell" in df.columns:
    ar = df["arsmodell"].dropna()
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
    mil = df["miltal"].dropna()
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
col1, col2, col3, col4 = st.columns(4)
col1.metric(
    "Annonser",
    f"{len(df):,}".replace(
        ",",
        " ",
    ),
)
if "annonspris" in df.columns:
    pris = df["annonspris"].dropna()
    if not pris.empty:
        col2.metric(
            "Medianpris",
            f"{pris.median():,.0f} kr".replace(
                ",",
                " ",
            ),
        )
        col3.metric(
            "Snittpris",
            f"{pris.mean():,.0f} kr".replace(
                ",",
                " ",
            ),
        )
if "miltal" in df.columns:
    mil = df["miltal"].dropna()
    if not mil.empty:
        col4.metric(
            "Median mil",
            f"{mil.median():,.0f}".replace(
                ",",
                " ",
            ),
        )
# ------------------------------------------------------------
# GRAFER
# ------------------------------------------------------------
st.divider()
fig = pris_over_tid(
    df
)
if fig is not None:
    st.subheader(
        "Prisutveckling"
    )
    st.plotly_chart(
        fig,
        use_container_width=True,
    )
fig = pris_mot_miltal(
    df
)
if fig is not None:
    st.subheader(
        "Pris kontra miltal"
    )
    st.plotly_chart(
        fig,
        use_container_width=True,
    )
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
