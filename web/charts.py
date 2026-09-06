"""
Diagram för Fiskabilar Analytics.
"""

from __future__ import annotations

import pandas as pd
import plotly.express as px


def _hitta_kolumn(
    df: pd.DataFrame,
    kandidater: list[str],
) -> str | None:
    """
    Hittar första existerande kolumnen
    från en lista av möjliga namn.
    """
    for kandidat in kandidater:
        if kandidat in df.columns:
            return kandidat

    return None


def pris_over_tid(
    df: pd.DataFrame,
):
    """
    Visar medianpris över tid.
    """
    if df.empty:
        return None

    datumkolumn = _hitta_kolumn(
        df,
        [
            "tid",
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

    if (
        not datumkolumn
        or not priskolumn
    ):
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
            data[
                datumkolumn
            ].dt.date
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
    """
    Visar pris i relation till miltal.
    """
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

    if (
        not milkolumn
        or not priskolumn
    ):
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
        hover_data=[
            kolumn
            for kolumn in [
                "modell",
                "variant",
                "arsmodell",
            ]
            if kolumn in data.columns
        ],
    )


def annonser_over_tid(
    df: pd.DataFrame,
):
    """
    Visar antal observationer per dag.
    """
    if (
        df.empty
        or "tid" not in df.columns
    ):
        return None

    data = df.copy()

    data["tid"] = pd.to_datetime(
        data["tid"],
        errors="coerce",
    )

    data = data.dropna(
        subset=["tid"]
    )

    if data.empty:
        return None

    grupperad = (
        data
        .groupby(
            data["tid"].dt.date
        )
        .size()
        .reset_index(
            name="annonser"
        )
    )

    grupperad.columns = [
        "datum",
        "annonser",
    ]

    return px.bar(
        grupperad,
        x="datum",
        y="annonser",
        title="Antal annonser över tid",
        labels={
            "datum": "Datum",
            "annonser": "Antal annonser",
        },
    )


def prisfordelning(
    df: pd.DataFrame,
):
    """
    Visar prisfördelning.
    """
    if df.empty:
        return None

    priskolumn = _hitta_kolumn(
        df,
        [
            "annonspris",
            "pris",
            "price",
        ],
    )

    if not priskolumn:
        return None

    data = df.copy()

    data[priskolumn] = pd.to_numeric(
        data[priskolumn],
        errors="coerce",
    )

    data = data.dropna(
        subset=[priskolumn]
    )

    if data.empty:
        return None

    return px.histogram(
        data,
        x=priskolumn,
        nbins=30,
        title="Prisfördelning",
        labels={
            priskolumn: "Pris",
        },
    )


def fyndutfall_diagram(
    df: pd.DataFrame,
):
    """
    Visar fördelningen mellan olika fyndutfall.
    """
    if (
        df.empty
        or "utfall" not in df.columns
    ):
        return None

    grupperad = (
        df["utfall"]
        .value_counts()
        .reset_index()
    )

    grupperad.columns = [
        "utfall",
        "antal",
    ]

    return px.bar(
        grupperad,
        x="utfall",
        y="antal",
        title="Fyndutfall",
        labels={
            "utfall": "Utfall",
            "antal": "Antal fynd-event",
        },
    )


def score_utfall_diagram(
    df: pd.DataFrame,
):
    """
    Visar scoreintervall mot faktiskt utfall.
    """
    if df.empty:
        return None

    krav = {
        "scoreintervall",
        "utfall",
        "antal",
    }

    if not krav.issubset(
        df.columns
    ):
        return None

    return px.bar(
        df,
        x="scoreintervall",
        y="antal",
        color="utfall",
        barmode="group",
        title="Score mot faktiskt utfall",
        labels={
            "scoreintervall": "Score",
            "antal": "Antal",
            "utfall": "Utfall",
        },
    )


def prissankningar_diagram(
    df: pd.DataFrame,
):
    """
    Visar observerade prissänkningar.
    """
    if df.empty:
        return None

    if "total_prissankning" not in df.columns:
        return None

    data = df.copy()

    data["total_prissankning"] = (
        pd.to_numeric(
            data[
                "total_prissankning"
            ],
            errors="coerce",
        )
    )

    data = data.dropna(
        subset=[
            "total_prissankning"
        ]
    )

    if data.empty:
        return None

    namn = []

    for index, row in data.iterrows():
        modell = str(
            row.get(
                "modell",
                "Okänd",
            )
        )

        namn.append(
            f"{modell} #{index}"
        )

    data["namn"] = namn

    data = data.sort_values(
        "total_prissankning",
        ascending=False,
    )

    return px.bar(
        data,
        x="namn",
        y="total_prissankning",
        title="Största observerade prissänkningar",
        labels={
            "namn": "Fynd",
            "total_prissankning":
                "Prissänkning",
        },
    )
