import streamlit as st
from web.data import (
    hamta_ml_metrics,
    hamta_ml_predictions,
)
st.set_page_config(
    page_title="Fiskabilar – ML",
    page_icon="🤖",
    layout="wide",
)
st.title("Machine Learning")
st.caption(
    "Statistik och resultat från Fiskabilars ML-modell."
)
metrics = hamta_ml_metrics()
predictions = hamta_ml_predictions()
# ------------------------------------------------------------
# STATUS
# ------------------------------------------------------------
st.subheader(
    "Modellstatus"
)
if not metrics:
    st.warning(
        "Ingen tränad ML-modell hittades."
    )
    st.info(
        "När ML-modellen har tränats och "
        "`data/ml/model_metadata.json` finns "
        "kommer modellens resultat att visas här."
    )
    st.stop()
# ------------------------------------------------------------
# KPI
# ------------------------------------------------------------
col1, col2, col3, col4 = st.columns(4)
if metrics.get("r2") is not None:
    col1.metric(
        "R²",
        f"{metrics['r2']:.3f}",
    )
if metrics.get("mae") is not None:
    col2.metric(
        "MAE",
        f"{metrics['mae']:,.0f} kr".replace(
            ",",
            " ",
        ),
    )
if metrics.get("rmse") is not None:
    col3.metric(
        "RMSE",
        f"{metrics['rmse']:,.0f} kr".replace(
            ",",
            " ",
        ),
    )
if metrics.get("mape") is not None:
    col4.metric(
        "MAPE",
        f"{metrics['mape']:.2f} %",
    )
# ------------------------------------------------------------
# MODELLINFORMATION
# ------------------------------------------------------------
st.divider()
st.subheader(
    "Modellinformation"
)
col1, col2 = st.columns(2)
with col1:
    st.write(
        "**Modell:**",
        metrics.get(
            "model",
            "Okänd",
        ),
    )
    st.write(
        "**Observationer:**",
        metrics.get(
            "observations",
            "–",
        ),
    )
    st.write(
        "**Träningsdata:**",
        metrics.get(
            "training_rows",
            "–",
        ),
    )
with col2:
    st.write(
        "**Testdata:**",
        metrics.get(
            "test_rows",
            "–",
        ),
    )
    st.write(
        "**Träningsdatum:**",
        metrics.get(
            "trained_at",
            "–",
        ),
    )
    st.write(
        "**Target:**",
        metrics.get(
            "target",
            "–",
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
        "Features"
    )
    st.write(
        ", ".join(
            str(feature)
            for feature in features
        )
    )
# ------------------------------------------------------------
# FELSTATISTIK
# ------------------------------------------------------------
st.divider()
st.subheader(
    "Felstatistik"
)
col1, col2, col3 = st.columns(3)
if metrics.get("median_error") is not None:
    col1.metric(
        "Medianfel",
        f"{metrics['median_error']:,.0f} kr".replace(
            ",",
            " ",
        ),
    )
if metrics.get("median_absolute_error") is not None:
    col2.metric(
        "Median absolutfel",
        f"{metrics['median_absolute_error']:,.0f} kr".replace(
            ",",
            " ",
        ),
    )
if metrics.get("bias") is not None:
    col3.metric(
        "Bias",
        f"{metrics['bias']:,.0f} kr".replace(
            ",",
            " ",
        ),
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
        "Jämförelse mellan modeller"
    )
    rows = []
    for namn, resultat in all_models.items():
        totalt = resultat.get(
            "totalt",
            {},
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
        st.dataframe(
            rows,
            use_container_width=True,
            hide_index=True,
        )
# ------------------------------------------------------------
# PREDIKTIONER
# ------------------------------------------------------------
if not predictions.empty:
    st.divider()
    st.subheader(
        "Modellens prediktioner"
    )
    st.dataframe(
        predictions,
        use_container_width=True,
        hide_index=True,
    )
else:
    st.info(
        "Det finns ännu ingen separat fil med "
        "sparade prediktioner."
    )
