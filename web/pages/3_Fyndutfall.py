"""
Fyndutfall.

Visar vad som faktiskt hände efter att
Fiskabilar identifierade en bil som fynd.
"""

import streamlit as st

from web.charts import (
    fyndutfall_diagram,
)
from web.data import (
    hamta_fyndutfall,
)
from web.styles import (
    apply_styles,
)


st.set_page_config(
    page_title="Fiskabilar – Fyndutfall",
    page_icon="📊",
    layout="wide",
)

apply_styles()


st.title(
    "📊 Faktiska fyndutfall"
)

st.caption(
    "Feedback från marknaden efter att "
    "Fiskabilar identifierat ett fynd."
)


df = hamta_fyndutfall()


if df.empty:
    st.info(
        "Ingen fyndutfallsdata finns ännu."
    )

    st.stop()


# ------------------------------------------------------------
# KPI
# ------------------------------------------------------------

antal = len(
    df
)


def antal_utfall(
    namn: str,
) -> int:
    if "utfall" not in df.columns:
        return 0

    return int(
        (
            df["utfall"]
            == namn
        ).sum()
    )


aktiva = antal_utfall(
    "AKTIV"
)

prissankta = antal_utfall(
    "PRISSÄNKT"
)

forsvunna = antal_utfall(
    "FÖRSVUNNEN"
)

forsvunna_efter_sankning = (
    antal_utfall(
        "FÖRSVUNNEN_EFTER_PRISSÄNKNING"
    )
)


col1, col2, col3, col4, col5 = (
    st.columns(5)
)

col1.metric(
    "Fynd-event",
    antal,
)

col2.metric(
    "Aktiva",
    aktiva,
)

col3.metric(
    "Prissänkta",
    prissankta,
)

col4.metric(
    "Försvunna",
    forsvunna,
)

col5.metric(
    "Försvunna efter sänkning",
    forsvunna_efter_sankning,
)


st.divider()


# ------------------------------------------------------------
# DIAGRAM
# ------------------------------------------------------------

fig = fyndutfall_diagram(
    df
)

if fig is not None:
    st.plotly_chart(
        fig,
        use_container_width=True,
    )


# ------------------------------------------------------------
# SNABBA UTFALL
# ------------------------------------------------------------

st.subheader(
    "⚡ Snabba försvinnanden"
)


if "snabbt_forvinnande" in df.columns:
    snabba = df[
        df[
            "snabbt_forvinnande"
        ]
        == True
    ]

    col1, col2 = st.columns(
        2
    )

    col1.metric(
        "Snabba försvinnanden",
        len(snabba),
    )

    if (
        not snabba.empty
        and "dagar_till_forvinnande"
        in snabba.columns
    ):
        dagar = snabba[
            "dagar_till_forvinnande"
        ].dropna()

        if not dagar.empty:
            col2.metric(
                "Median dagar",
                f"{dagar.median():.1f}",
            )

else:
    st.info(
        "Ingen data om snabba försvinnanden ännu."
    )


st.divider()


# ------------------------------------------------------------
# UTFALLSTABELL
# ------------------------------------------------------------

st.subheader(
    "Alla fyndutfall"
)


visa_kolumner = [
    kolumn
    for kolumn in [
        "utfall",
        "score",
        "modell",
        "arsmodell",
        "miltal",
        "pris",
        "diff",
        "total_prissankning",
        "dagar_till_prissankning",
        "dagar_till_forvinnande",
        "snabbt_forvinnande",
    ]
    if kolumn in df.columns
]


if visa_kolumner:
    visa = df[
        visa_kolumner
    ]

else:
    visa = df


st.dataframe(
    visa,
    use_container_width=True,
    hide_index=True,
)
