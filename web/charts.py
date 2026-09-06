"""
Diagram för Fiskabilar Analytics.
"""

from __future__ import annotations

import pandas as pd
import plotly.express as px


def pris_over_tid(
    df: pd.DataFrame,
):
    if df.empty:
        return None

    datumkolumn = _hitta_kolumn(
        df,
        [
            "datum",
            "date",
            "timestamp",
            "scraped_at",
        ],
    )

    priskolumn = _hitta_kolumn(
        df,
        [
            "annonspris",
            "pris",
            "price",
        ],
    )

    if not datumkolumn or not priskolumn:
        return None

    data = df.copy()

    data[datumkolumn] = pd.to_datetime(
        data[datumkolumn],
        errors="coerce",
    )

    data[priskolumn] = pd.to_numeric(
        data[priskolumn],
        errors="coerce",
    )

    data = data.dropna(
        subset=[
            datumkolumn,
            priskolumn,
        ]
    )

    if data.empty:
        return None

    grupperad = (
        data
        .groupby(
            data[datumkolumn].dt.date
        )[priskolumn]
        .median()
        .reset_index()
    )

    grupperad.columns = [
        "datum",
        "medianpris",
    ]

    return px.line(
        grupperad,
        x="datum",
        y="medianpris",
        markers=True,
        title="Medianpris över tid",
        labels={
            "datum": "Datum",
            "medianpris": "Medianpris",
        },
    )


def pris_mot_miltal(
    df: pd.DataFrame,
):
    if df.empty:
        return None

    milkolumn = _hitta_kolumn(
        df,
        [
            "miltal",
            "mil",
            "mileage",
        ],
    )

    priskolumn = _hitta_kolumn(
        df,
        [
            "annonspris",
            "pris",
            "price",
        ],
    )

    if not milkolumn or not priskolumn:
        return None

    data = df.copy()

    data[milkolumn] = pd.to_numeric(
        data[milkolumn],
        errors="coerce",
    )

    data[priskolumn] = pd.to_numeric(
        data[priskolumn],
        errors="coerce",
    )

    data = data.dropna(
        subset=[
            milkolumn,
            priskolumn,
        ]
    )

    if data.empty:
        return None

    return px.scatter(
        data,
        x=milkolumn,
        y=priskolumn,
        title="Pris mot miltal",
        labels={
            milkolumn: "Miltal",
            priskolumn: "Pris",
        },
    )


def _hitta_kolumn(
    df: pd.DataFrame,
    kandidater: list[str],
) -> str | None:

    for kandidat in kandidater:
        if kandidat in df.columns:
            return kandidat

    return None
