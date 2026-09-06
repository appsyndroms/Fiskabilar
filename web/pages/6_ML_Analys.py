"""
ML Analytics.

Visar status, kvalitet och utveckling
för Fiskabilars maskininlärningsmodell.
"""

import pandas as pd
import streamlit as st

from web.data import (
    hamta_ml_metrics,
    hamta_ml_predictions,
)
from web.styles import (
    apply_styles,
)


st.set_page_config(
    page_title="Fiskabilar – ML Analytics",
    page_icon="🤖",
    layout="wide",
)

apply_styles()


st.title(
    "🤖 ML Analytics"
)

st.caption(
    "Utvecklingen av Fiskabilars "
    "datadrivna marknadsvärdering."
)


metrics = hamta_ml_metrics()

predictions = hamta_ml_predictions()


# ------------------------------------------------------------
# STATUS
# ------------------------------------------------------------

if not metrics:

    st.warning(
        "Ingen tränad ML-modell hittades."
    )

    st.info(
        """
        När ML-träningen har producerat:

        `data/ml/model_metadata.json`

        kommer modellens statistik att
        visas automatiskt här.
        """
    )

    st.stop()


# ------------------------------------------------------------
# HUVUDSTATUS
# ------------------------------------------------------------

st.subheader(
    "🧠 Modellstatus"
)


col1, col2, col3 = st.columns(
    3
)


col1.metric(
    "Aktiv modell",
    metrics.get(
        "model"
    )
    or "Okänd",
)


observations = (
    metrics.get(
        "observations"
    )
    or 0
)


col2.metric(
    "Observationer",
    f"{observations:,}".replace(
        ",",
        " ",
    ),
)


trained_at = (
    metrics.get(
        "trained_at"
    )
    or "—"
)


col3.metric(
    "Senast tränad",
    str(
        trained_at
    ),
)


st.divider()


# ------------------------------------------------------------
# MODELLPRECISION
# ------------------------------------------------------------

st.subheader(
    "📊 Modellprecision"
)


col1, col2, col3, col4 = st.columns(
    4
)


col1.metric(
    "R²",
    (
        f"{metrics['r2']:.3f}"
        if metrics.get(
            "r2"
        )
        is not None
        else "—"
    ),
)


col2.metric(
    "MAE",
    (
        f"{metrics['mae']:,.0f} kr"
        .replace(
            ",",
            " ",
        )
        if metrics.get(
            "mae"
        )
        is not None
        else "—"
    ),
)


col3.metric(
    "RMSE",
    (
        f"{metrics['rmse']:,.0f} kr"
        .replace(
            ",",
            " ",
        )
        if metrics.get(
            "rmse"
        )
        is not None
        else "—"
    ),
)


col4.metric(
    "MAPE",
    (
        f"{metrics['mape']:.2f} %"
        if metrics.get(
            "mape"
        )
        is not None
        else "—"
    ),
)


st.divider()


# ------------------------------------------------------------
# TRÄNINGSPROGRESS
# ------------------------------------------------------------

st.subheader(
    "📈 ML-progress"
)


training_rows = (
    metrics.get(
        "training_rows"
    )
    or 0
)

test_rows = (
    metrics.get(
        "test_rows"
    )
    or 0
)


total = (
    training_rows
    + test_rows
)


if total > 0:

    train_share = (
        training_rows
        / total
    )

    st.write(
        f"**Träningsdata:** "
        f"{training_rows:,}"
        .replace(
            ",",
            " ",
        )
    )

    st.progress(
        train_share
    )

    st.write(
        f"**Testdata:** "
        f"{test_rows:,}"
        .replace(
            ",",
            " ",
        )
    )


st.caption(
    """
    ML-progressen kommer automatiskt att bli
    mer intressant när historiken växer och
    fler träningskörningar sparas över tid.
    """
)


# ------------------------------------------------------------
# MODELLINFORMATION
# ------------------------------------------------------------

st.divider()


st.subheader(
    "🔧 Modellinformation"
)


col1, col2 = st.columns(
    2
)


with col1:

    st.write(
        "**Target:**",
        metrics.get(
            "target",
            "—",
        ),
    )

    st.write(
        "**Träningsrader:**",
        training_rows,
    )

    st.write(
        "**Testrader:**",
        test_rows,
    )


with col2:

    st.write(
        "**Medianfel:**",
        (
            f"{metrics['median_error']:,.0f} kr"
            .replace(
                ",",
                " ",
            )
            if metrics.get(
                "median_error"
            )
            is not None
            else "—"
        ),
    )

    st.write(
        "**Median absolutfel:**",
        (
            f"{metrics['median_absolute_error']:,.0f} kr"
            .replace(
                ",",
                " ",
            )
            if metrics.get(
                "median_absolute_error"
            )
            is not None
            else "—"
        ),
    )

    st.write(
        "**Bias:**",
        (
            f"{metrics['bias']:,.0f} kr"
            .replace(
                ",",
                " ",
            )
            if metrics.get(
                "bias"
            )
            is not None
            else "—"
        ),
    )


# ------------------------------------------------------------
# FEATURES
# ------------------------------------------------------------

features = metrics.get(
    "features",
    [],
)


if features:

    st.divider()

    st.subheader(
        "🧩 Features"
    )

    st.write(
        ", ".join(
            str(feature)
            for feature in features
        )
    )


# ------------------------------------------------------------
# MODELLJÄMFÖRELSE
# ------------------------------------------------------------

all_models = metrics.get(
    "all_models",
    {},
)


if all_models:

    st.divider()

    st.subheader(
        "🔬 Modelljämförelse"
    )

    rows = []

    for namn, resultat in (
        all_models.items()
    ):
        totalt = resultat.get(
            "totalt",
            {}
        )

        rows.append(
            {
                "Modell": namn,
                "MAE": totalt.get(
                    "mae"
                ),
                "RMSE": totalt.get(
                    "rmse"
                ),
                "R²": totalt.get(
                    "r2"
                ),
                "MAPE": totalt.get(
                    "mape_procent"
                ),
            }
        )

    if rows:

        jamforelse = pd.DataFrame(
            rows
        )

        st.dataframe(
            jamforelse,
            use_container_width=True,
            hide_index=True,
        )


# ------------------------------------------------------------
# PREDIKTIONER
# ------------------------------------------------------------

if not predictions.empty:

    st.divider()

    st.subheader(
        "🔮 Sparade prediktioner"
    )

    st.dataframe(
        predictions,
        use_container_width=True,
        hide_index=True,
    )


else:

    st.divider()

    st.info(
        """
        Det finns ännu ingen separat fil med
        sparade prediktioner.

        När en predictions.jsonl börjar skapas
        kommer den automatiskt att visas här.
        """
    )


# ------------------------------------------------------------
# FRAMTID
# ------------------------------------------------------------

st.divider()


st.subheader(
    "🚀 Nästa steg för ML"
)


st.markdown(
    """
    Fiskabilars ML-utveckling går mot:

    1. Mer marknadshistorik
    2. Fler observerade prisförändringar
    3. Bättre feature engineering
    4. Jämförelse mellan modeller
    5. Prediktion av bör-pris
    6. Automatisk feedback från faktiska fyndutfall

    Målet är att systemet över tid ska kunna
    ersätta allt fler fasta regler med
    datadriven marknadsvärdering.
    """
)
