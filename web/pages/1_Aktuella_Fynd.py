"""
Aktuella fynd.

Visar de bilar som Fiskabilar just nu
identifierar som intressanta fynd.
"""

import pandas as pd
import streamlit as st

from web.data import (
    hamta_senaste_fynd,
)
from web.styles import (
    apply_styles,
)


st.set_page_config(
    page_title="Fiskabilar – Aktuella fynd",
    page_icon="🚗",
    layout="wide",
)

apply_styles()


st.title(
    "🚗 Aktuella fynd"
)

st.caption(
    "Bilar som just nu bedöms vara "
    "särskilt intressanta på marknaden."
)


df = hamta_senaste_fynd()


if df.empty:
    st.info(
        "Inga aktuella fynd hittades."
    )

    st.stop()


# ------------------------------------------------------------
# HJÄLPFUNKTION
# ------------------------------------------------------------

def hitta_kolumn(
    kandidater: list[str],
) -> str | None:
    for kandidat in kandidater:
        if kandidat in df.columns:
            return kandidat

    return None


# ------------------------------------------------------------
# KOLUMNER
# ------------------------------------------------------------

pris_kolumn = hitta_kolumn(
    [
        "pris",
        "annonspris",
        "Price",
    ]
)

score_kolumn = hitta_kolumn(
    [
        "score",
        "Score",
    ]
)

diff_kolumn = hitta_kolumn(
    [
        "diff",
        "prisdiff",
        "skillnad",
        "Skillnad",
        "price_difference",
    ]
)

modell_kolumn = hitta_kolumn(
    [
        "modell",
        "Modell",
    ]
)

url_kolumn = hitta_kolumn(
    [
        "url",
        "URL",
        "annons_url",
    ]
)


# ------------------------------------------------------------
# FILTER
# ------------------------------------------------------------

st.sidebar.header(
    "Filter"
)


if modell_kolumn:
    modeller = sorted(
        df[modell_kolumn]
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
            df[modell_kolumn]
            .astype(str)
            .isin(
                valt_modell
            )
        ]


if score_kolumn:
    scores = pd.to_numeric(
        df[score_kolumn],
        errors="coerce",
    )

    if not scores.dropna().empty:
        min_score = st.sidebar.slider(
            "Minsta score",
            0,
            100,
            0,
        )

        df = df[
            scores >= min_score
        ]


if df.empty:
    st.warning(
        "Inga fynd matchar filtreringen."
    )

    st.stop()


# ------------------------------------------------------------
# SORTERING
# ------------------------------------------------------------

if score_kolumn:
    df[score_kolumn] = pd.to_numeric(
        df[score_kolumn],
        errors="coerce",
    )

    df = df.sort_values(
        score_kolumn,
        ascending=False,
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


if score_kolumn:
    score = df[
        score_kolumn
    ].dropna()

    col2.metric(
        "Högsta score",
        (
            f"{score.max():.0f}"
            if not score.empty
            else "—"
        ),
    )


if diff_kolumn:
    diff = pd.to_numeric(
        df[diff_kolumn],
        errors="coerce",
    ).dropna()

    col3.metric(
        "Största diff",
        (
            f"{diff.max():,.0f} kr"
            .replace(
                ",",
                " ",
            )
            if not diff.empty
            else "—"
        ),
    )


if pris_kolumn:
    pris = pd.to_numeric(
        df[pris_kolumn],
        errors="coerce",
    ).dropna()

    col4.metric(
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


st.divider()


# ------------------------------------------------------------
# TOPP-FYND
# ------------------------------------------------------------

st.subheader(
    "🔥 Toppfynd"
)


for _, row in df.head(
    10
).iterrows():

    modell = (
        row.get(
            modell_kolumn,
            "Okänd bil",
        )
        if modell_kolumn
        else "Okänd bil"
    )

    with st.container():

        col1, col2, col3, col4 = (
            st.columns(
                [
                    3,
                    1,
                    1,
                    1,
                ]
            )
        )

        col1.markdown(
            f"### {modell}"
        )

        if pris_kolumn:
            pris = row.get(
                pris_kolumn
            )

            if pd.notna(pris):
                col2.metric(
                    "Pris",
                    f"{float(pris):,.0f} kr"
                    .replace(
                        ",",
                        " ",
                    ),
                )

        if score_kolumn:
            score = row.get(
                score_kolumn
            )

            if pd.notna(score):
                col3.metric(
                    "Score",
                    f"{float(score):.0f}",
                )

        if diff_kolumn:
            diff = row.get(
                diff_kolumn
            )

            if pd.notna(diff):
                col4.metric(
                    "Diff",
                    f"{float(diff):,.0f} kr"
                    .replace(
                        ",",
                        " ",
                    ),
                )

        if (
            url_kolumn
            and pd.notna(
                row.get(
                    url_kolumn
                )
            )
        ):
            st.link_button(
                "Öppna annons",
                str(
                    row[
                        url_kolumn
                    ]
                ),
            )

        st.divider()


# ------------------------------------------------------------
# TABELL
# ------------------------------------------------------------

st.subheader(
    "Alla aktuella fynd"
)

st.dataframe(
    df,
    use_container_width=True,
    hide_index=True,
)
