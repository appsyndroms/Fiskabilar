import streamlit as st

from data import load_ml_metrics, load_ml_predictions


st.set_page_config(
    page_title="Fiskabilar – ML",
    page_icon="🤖",
    layout="wide",
)


st.title("Machine Learning")
st.caption("Statistik och resultat från Fiskabilars ML-modell.")


metrics = load_ml_metrics()
predictions = load_ml_predictions()


# ------------------------------------------------------------
# STATUS
# ------------------------------------------------------------

st.subheader("Modellstatus")

if not metrics:
    st.warning("Ingen ML-statistik hittades.")
    st.info(
        "När ML-modellen har tränats kommer modellens "
        "prestanda att visas här."
    )
    st.stop()


col1, col2, col3, col4 = st.columns(4)


if "r2" in metrics:
    col1.metric(
        "R²",
        f"{metrics['r2']:.3f}",
    )

if "mae" in metrics:
    col2.metric(
        "MAE",
        f"{metrics['mae']:,.0f} kr".replace(",", " "),
    )

if "rmse" in metrics:
    col3.metric(
        "RMSE",
        f"{metrics['rmse']:,.0f} kr".replace(",", " "),
    )

if "mape" in metrics:
    col4.metric(
        "MAPE",
        f"{metrics['mape']:.2f} %",
    )


# ------------------------------------------------------------
# MODELL
# ------------------------------------------------------------

st.divider()

st.subheader("Modellinformation")

col1, col2 = st.columns(2)

with col1:
    st.write(
        "**Modell:**",
        metrics.get("model", "Okänd"),
    )

    st.write(
        "**Träningsannonser:**",
        metrics.get("training_rows", "–"),
    )

with col2:
    st.write(
        "**Testannonser:**",
        metrics.get("test_rows", "–"),
    )

    st.write(
        "**Träningsdatum:**",
        metrics.get("trained_at", "–"),
    )


# ------------------------------------------------------------
# FEATURE IMPORTANCE
# ------------------------------------------------------------

if "feature_importance" in metrics:

    st.divider()

    st.subheader("Feature importance")

    importance = metrics["feature_importance"]

    if isinstance(importance, dict):
        importance_items = sorted(
            importance.items(),
            key=lambda x: x[1],
            reverse=True,
        )

        for feature, value in importance_items:
            st.write(
                f"**{feature}** — {value:.3f}"
            )


# ------------------------------------------------------------
# PREDIKTIONER
# ------------------------------------------------------------

if predictions is not None and not predictions.empty:

    st.divider()

    st.subheader("Modellens prediktioner")

    st.dataframe(
        predictions,
        use_container_width=True,
        hide_index=True,
    )
