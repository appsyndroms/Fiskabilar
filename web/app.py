"""
Fiskabilar Analytics.

Huvudapplikation och startsida för webbgränssnittet.

Webben är ett presentationslager ovanpå:

    data/
        ↓
    web/data.py
        ↓
    Streamlit
        ↓
    Dashboard
"""

import streamlit as st

from web.charts import (
    fyndutfall_diagram,
)
from web.data import (
    hamta_dashboard_data,
    hamta_fyndutfall,
    hamta_senaste_fynd,
)
from web.styles import (
    apply_styles,
)


st.set_page_config(
    page_title="Fiskabilar Analytics",
    page_icon="🚗",
    layout="wide",
    initial_sidebar_state="expanded",
)

apply_styles()


st.title(
    "🚗 Fiskabilar Analytics"
)

st.caption(
    "Data-driven analys av den svenska "
    "begagnatbilsmarknaden"
)


data = hamta_dashboard_data()


# ------------------------------------------------------------
# KPI
# ------------------------------------------------------------


st.subheader(
    "Översikt"
)

col1, col2, col3, col4 = st.columns(
    4
)

with col1:
    st.metric(
        "Annonser senaste körningen",
        f"{data['annonser_senaste_korning']:,}"
        .replace(
            ",",
            " ",
        ),
    )

with col2:
    st.metric(
        "Unika bilar",
        f"{data['unika_bilar']:,}"
        .replace(
            ",",
            " ",
        ),
    )

with col3:
    st.metric(
        "Historiska annonser",
        f"{data['historiska_annonser']:,}"
        .replace(
            ",",
            " ",
        ),
    )

with col4:
    st.metric(
        "Aktuella fynd",
        data["aktiva_fynd"],
    )


st.divider()


# ------------------------------------------------------------
# BÄSTA FYND
# ------------------------------------------------------------


st.subheader(
    "🔥 Bästa fynd just nu"
)

fynd = hamta_senaste_fynd()

if fynd.empty:
    st.info(
        "Inga aktuella fynd finns "
        "tillgängliga ännu."
    )

else:
    data_fynd = fynd.copy()

    if "score" in data_fynd.columns:
        data_fynd["score"] = (
            data_fynd["score"]
            .astype(float)
        )

        data_fynd = data_fynd.sort_values(
            "score",
            ascending=False,
        )

    kolumner = [
        kolumn
        for kolumn in [
            "score",
            "modell",
            "arsmodell",
            "miltal",
            "pris",
            "diff",
        ]
        if kolumn in data_fynd.columns
    ]

    if kolumner:
        st.dataframe(
            data_fynd[
                kolumner
            ].head(10),
            use_container_width=True,
            hide_index=True,
        )

    else:
        st.dataframe(
            data_fynd.head(10),
            use_container_width=True,
            hide_index=True,
        )

    st.caption(
        "Se sidan 🚗 Aktuella fynd "
        "för komplett lista."
    )


st.divider()


# ------------------------------------------------------------
# FYNDUTFALL
# ------------------------------------------------------------


left, right = st.columns(
    [2, 1]
)

with left:
    st.subheader(
        "📊 Fyndutfall"
    )

    utfall = hamta_fyndutfall()

    fig = fyndutfall_diagram(
        utfall
    )

    if fig is not None:
        st.plotly_chart(
            fig,
            use_container_width=True,
        )

    else:
        st.info(
            "Fyndutfall visas när "
            "find_outcomes-filen innehåller data."
        )


with right:
    st.subheader(
        "🤖 ML-status"
    )

    st.metric(
        "Modell",
        data["ml_modell"],
    )

    if (
        data["ml_mae"]
        is not None
    ):
        st.metric(
            "MAE",
            f"{data['ml_mae']:,.0f} kr"
            .replace(
                ",",
                " ",
            ),
        )

    else:
        st.metric(
            "MAE",
            "—",
        )

    st.metric(
        "Observationer",
        f"{data['ml_observationer']:,}"
        .replace(
            ",",
            " ",
        ),
    )


st.divider()


# ------------------------------------------------------------
# SYSTEM
# ------------------------------------------------------------


st.subheader(
    "🧠 Så arbetar Fiskabilar"
)

col1, col2, col3, col4 = st.columns(
    4
)

with col1:
    st.markdown(
        """
        ### 📥 Marknad

        Systemet samlar in annonser och
        bygger marknadshistorik.
        """
    )

with col2:
    st.markdown(
        """
        ### 🔎 Fynd

        Intressanta bilar identifieras
        genom pris och marknadsvärde.
        """
    )

with col3:
    st.markdown(
        """
        ### 📊 Feedback

        Fynd följs över tid för att se
        vad som faktiskt händer.
        """
    )

with col4:
    st.markdown(
        """
        ### 🤖 ML

        Historiska data används för att
        förbättra marknadsvärderingen.
        """
    )


st.divider()


st.caption(
    "Fiskabilar Analytics • "
    "Marknad → Fynd → Utfall → Feedback → ML"
)
