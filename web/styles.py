"""
Gemensam styling för Fiskabilar Analytics.
"""

import streamlit as st


def apply_styles() -> None:
    st.markdown(
        """
        <style>

        .block-container {
            max-width: 1400px;
            padding-top: 2rem;
            padding-bottom: 3rem;
        }

        h1 {
            font-weight: 700;
        }

        h2, h3 {
            font-weight: 600;
        }

        [data-testid="stMetric"] {
            border: 1px solid rgba(128,128,128,0.2);
            border-radius: 12px;
            padding: 1rem;
        }

        </style>
        """,
        unsafe_allow_html=True,
    )
