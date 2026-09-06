import streamlit as st


st.set_page_config(
    page_title="Fiskabilar – Model Lab",
    page_icon="🔬",
    layout="wide",
)


st.title("Model Lab")
st.caption(
    "Jämför olika modeller och experimentera med "
    "Fiskabilars värderingsmodell."
)


# ------------------------------------------------------------
# INTRO
# ------------------------------------------------------------

st.subheader("Modelljämförelse")

st.write(
    """
    Här kan vi jämföra olika ML-modeller som används för
    att uppskatta bilarnas bör-pris.

    Tanken är att ersätta fasta regler i värderingen med
    en datadriven modell som tränas på historiska annonser.
    """
)


# ------------------------------------------------------------
# MODELLER
# ------------------------------------------------------------

col1, col2 = st.columns(2)


with col1:

    st.markdown("### Linear Regression")

    st.write(
        """
        En enkel och transparent modell.

        Fördelar:
        - lätt att tolka
        - snabb att träna
        - visar tydligt hur varje variabel påverkar priset
        """
    )


with col2:

    st.markdown("### Random Forest")

    st.write(
        """
        En mer flexibel modell som kan fånga
        icke-linjära samband.

        Fördelar:
        - kan hantera komplexare samband
        - kräver inte en linjär prisrelation
        - kan ge feature importance
        """
    )


# ------------------------------------------------------------
# FEATURES
# ------------------------------------------------------------

st.divider()

st.subheader("Features")

features = [
    "Mil",
    "Årsmodell",
    "Variant",
    "Märke",
    "Modell",
]


for feature in features:
    st.checkbox(
        feature,
        value=True,
        disabled=True,
    )


# ------------------------------------------------------------
# RESULTAT
# ------------------------------------------------------------

st.divider()

st.subheader("Resultat")

st.info(
    """
    Modelljämförelsen aktiveras när träningspipen för ML
    är på plats.

    Då visas exempelvis:

    • R²
    • MAE
    • RMSE
    • MAPE
    • träningsdata
    • testdata
    • feature importance
    """
)


# ------------------------------------------------------------
# FRAMTIDA EXPERIMENT
# ------------------------------------------------------------

st.divider()

st.subheader("Experiment")

st.write(
    """
    Framtida experiment kan exempelvis vara:

    1. Linear Regression
    2. Random Forest
    3. Random Forest med fler features
    4. Gradient Boosting
    5. jämförelse mellan modellernas prediktioner
    """
)
