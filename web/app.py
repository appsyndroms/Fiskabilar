"""
Fiskabilar Analytics

Huvudapplikation för webbgränssnittet.
"""

from pathlib import Path

import streamlit as st

from web.styles import apply_styles
from web.data import (
    hamta_dashboard_data,
    hamta_senaste_fynd,
)


BASE_DIR = Path(__file__).resolve().parent.parent


st.set_page_config(
    page_title="Fiskabilar Analytics",
    page_icon="🚗",
    layout="wide",
    initial_sidebar_state="expanded",
)

apply_styles()


st.title("Fiskabilar Analytics")
st.caption(
    "Data-driven analys av den svenska begagnatbilsmarknaden"
)


data = hamta_dashboard_data()


# ------------------------------------------------------------
# KPI
# ------------------------------------------------------------

col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric(
        "Annonser senaste körningen",
        data["annonser_senaste_korning"],
    )

with col2:
    st.metric(
        "Unika bilar",
        data["unika_bilar"],
    )

with col3:
    st.metric(
        "Historiska annonser",
        data["historiska_annonser"],
    )

with col4:
    st.metric(
        "Aktiva fynd",
        data["aktiva_fynd"],
    )


st.divider()


# ------------------------------------------------------------
# Marknad
# ------------------------------------------------------------

left, right = st.columns([2, 1])

with left:
    st.subheader("📈 Marknaden just nu")

    st.write(
        "Välj **Marknad** i sidomenyn för detaljerad analys "
        "av pris, miltal och utveckling över tid."
    )

with right:
    st.subheader("🤖 ML-status")

    st.metric(
        "Modell",
        data["ml_modell"],
    )

    st.metric(
        "MAE",
        data["ml_mae"],
    )


st.divider()


# ------------------------------------------------------------
# Fynd
# ------------------------------------------------------------

st.subheader("🔥 Bästa fynd just nu")

fynd = hamta_senaste_fynd()

if fynd.empty:
    st.info(
        "Inga aktuella fynd finns tillgängliga."
    )
else:
    st.dataframe(
        fynd,
        use_container_width=True,
        hide_index=True,
    )


st.divider()

st.caption(
    "Fiskabilar Analytics • Automatisk marknadsanalys"
)
