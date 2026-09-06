"""
Gemensam styling för Fiskabilar Analytics.
"""

import streamlit as st


def apply_styles() -> None:
    """
    Applicerar gemensam styling.
    """
    st.markdown(
        """
        <style>

        .block-container {
            max-width: 1450px;
            padding-top: 2rem;
            padding-bottom: 3rem;
        }

        h1 {
            font-weight: 750;
        }

        h2,
        h3 {
            font-weight: 650;
        }

        [data-testid="stMetric"] {
            border: 1px solid
                rgba(128, 128, 128, 0.20);

            border-radius: 14px;

            padding: 1rem;

            background:
                rgba(255, 255, 255, 0.02);
        }

        [data-testid="stSidebar"] {
            border-right:
                1px solid
                rgba(128, 128, 128, 0.15);
        }

        div[data-testid="stDataFrame"] {
            border-radius: 12px;
            overflow: hidden;
        }

        .dashboard-card {
            border:
                1px solid
                rgba(128, 128, 128, 0.18);

            border-radius: 14px;

            padding: 1.2rem;

            margin-bottom: 1rem;
        }

        .dashboard-title {
            font-size: 1.2rem;
            font-weight: 650;
            margin-bottom: 0.4rem;
        }

        .dashboard-value {
            font-size: 2rem;
            font-weight: 750;
        }

        </style>
        """,
        unsafe_allow_html=True,
    )
