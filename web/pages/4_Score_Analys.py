"""
Score mot faktiskt utfall.

Analyserar om Fiskabilars score faktiskt
har samband med hur marknaden reagerar.
"""

import pandas as pd
import streamlit as st

from web.charts import (
    score_utfall_diagram,
)
from web.data import (
    hamta_fyndutfall,
    hamta_scoreanalys,
)
from web.styles import (
    apply_styles,
)


st.set_page_config(
    page_title="Fiskabilar – Score analys",
    page_icon="⭐",
    layout="wide",
)

apply_styles()


st.title(
    "⭐ Score mot faktiskt utfall"
)

st.caption(
    "Analyserar om högre score faktiskt "
    "ger bättre fynd."
)


analys = hamta_scoreanalys()

utfall = hamta_fyndutfall()


if analys.empty:
    st.info(
        "Det finns ännu inte tillräckligt "
        "med data för scoreanalys."
    )

    st.stop()


# ------------------------------------------------------------
# DIAGRAM
# ------------------------------------------------------------


fig = score_utfall_diagram(
    analys
)

if fig is not None:
    st.plotly_chart(
        fig,
        use_container_width=True,
    )


st.divider()


# ------------------------------------------------------------
# PROCENT PER SCOREINTERVALL
# ------------------------------------------------------------


st.subheader(
    "Fördelning per scoreintervall"
)


pivot = analys.pivot(
    index="scoreintervall",
    columns="utfall",
    values="antal",
).fillna(
    0
)


procent = (
    pivot
    .div(
        pivot.sum(
            axis=1
        ),
        axis=0,
    )
    * 100
).round(
    1
)


st.dataframe(
    procent,
    use_container_width=True,
)


st.divider()


# ------------------------------------------------------------
# SCORESTATISTIK
# ------------------------------------------------------------


if (
    not utfall.empty
    and "score" in utfall.columns
):
    data = utfall.copy()

    data["score"] = pd.to_numeric(
        data["score"],
        errors="coerce",
    )

    data = data.dropna(
        subset=["score"]
    )

    if not data.empty:

        st.subheader(
            "Scorestatistik"
        )

        col1, col2, col3 = st.columns(
            3
        )

        col1.metric(
            "Genomsnittlig score",
            f"{data['score'].mean():.1f}",
        )

        col2.metric(
            "Median score",
            f"{data['score'].median():.1f}",
        )

        col3.metric(
            "Högsta score",
            f"{data['score'].max():.0f}",
        )


st.divider()


# ------------------------------------------------------------
# TOLKNING
# ------------------------------------------------------------


st.subheader(
    "🧠 Vad betyder detta?"
)

st.markdown(
    """
    Målet är att Fiskabilars score ska kunna
    utvärderas mot faktisk marknadsutveckling.

    På sikt vill vi kunna se exempelvis:

    - Försvinner höga score snabbare?
    - Kräver låga score oftare prissänkning?
    - Ger stor prisdiff bättre utfall?
    - Vilken score ger bäst träffsäkerhet?

    Detta blir feedback-loopen mellan:

    **Score → Fynd → Marknad → Faktiskt utfall**
    """
)
