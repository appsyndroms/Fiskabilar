"""
Dataåtkomst för Fiskabilar Analytics.

Den här modulen är den centrala platsen där
webbappen läser och sammanställer data från:

- data/state.json
- data/market_history/*.jsonl
- data/find_feedback/*.jsonl
- data/find_feedback/find_outcomes_*.jsonl
- data/ml/model_metadata.json

Webbappen ändrar aldrig originaldata.
Den läser endast och presenterar resultatet.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


ROOT = Path(
    __file__
).resolve().parent.parent

DATA_DIR = (
    ROOT
    / "data"
)

MARKET_HISTORY_DIR = (
    DATA_DIR
    / "market_history"
)

FEEDBACK_DIR = (
    DATA_DIR
    / "find_feedback"
)

STATE_FILE = (
    DATA_DIR
    / "state.json"
)

ML_DIR = (
    DATA_DIR
    / "ml"
)

ML_METADATA_FILE = (
    ML_DIR
    / "model_metadata.json"
)

ML_PREDICTIONS_FILE = (
    ML_DIR
    / "predictions.jsonl"
)


def _las_jsonl(
    path: Path,
) -> list[dict]:
    """
    Läser en JSONL-fil.

    Trasiga rader ignoreras så att en enskild
    korrupt post inte stoppar webbappen.
    """
    if not path.exists():
        return []

    resultat = []

    try:
        with path.open(
            "r",
            encoding="utf-8",
        ) as fil:
            for rad in fil:
                rad = rad.strip()

                if not rad:
                    continue

                try:
                    data = json.loads(
                        rad
                    )
                except json.JSONDecodeError:
                    continue

                if isinstance(
                    data,
                    dict,
                ):
                    resultat.append(
                        data
                    )

    except OSError:
        return []

    return resultat


def _las_jsonl_katalog(
    katalog: Path,
    monster: str = "*.jsonl",
) -> list[dict]:
    """
    Läser alla JSONL-filer i en katalog.
    """
    if not katalog.exists():
        return []

    resultat = []

    for fil in sorted(
        katalog.glob(
            monster
        )
    ):
        resultat.extend(
            _las_jsonl(
                fil
            )
        )

    return resultat


def _las_json(
    path: Path,
) -> dict:
    """
    Läser en JSON-fil.
    """
    if not path.exists():
        return {}

    try:
        with path.open(
            "r",
            encoding="utf-8",
        ) as fil:
            data = json.load(
                fil
            )

        if isinstance(
            data,
            dict,
        ):
            return data

    except (
        OSError,
        json.JSONDecodeError,
    ):
        return {}

    return {}


def _numerisk_serie(
    df: pd.DataFrame,
    kolumn: str,
) -> pd.Series:
    """
    Returnerar en numerisk serie om kolumnen finns.
    """
    if kolumn not in df.columns:
        return pd.Series(
            dtype="float64"
        )

    return pd.to_numeric(
        df[kolumn],
        errors="coerce",
    )


def _hitta_senaste_fil(
    katalog: Path,
    monster: str,
) -> Path | None:
    """
    Hittar den senast sorterade filen som matchar
    angivet filnamnsmönster.
    """
    if not katalog.exists():
        return None

    filer = sorted(
        katalog.glob(
            monster
        )
    )

    if not filer:
        return None

    return filer[-1]


# ------------------------------------------------------------
# STATE
# ------------------------------------------------------------

def hamta_state() -> dict:
    """
    Läser Fiskabilars state-fil.
    """
    return _las_json(
        STATE_FILE
    )


# ------------------------------------------------------------
# MARKNADSHISTORIK
# ------------------------------------------------------------

def hamta_historik() -> pd.DataFrame:
    """
    Läser all marknadshistorik.

    Projektet använder månadsvisa filer:

        market_history_YYYY-MM.jsonl

    Funktionen läser alla historikfiler.
    """
    data = _las_jsonl_katalog(
        MARKET_HISTORY_DIR,
        "market_history_*.jsonl",
    )

    if not data:
        # Bakåtkompatibilitet med äldre struktur.
        data = _las_jsonl_katalog(
            MARKET_HISTORY_DIR,
            "*.jsonl",
        )

    if not data:
        return pd.DataFrame()

    df = pd.DataFrame(
        data
    )

    return df


def hamta_marknadsdata(
    modell: str | None = None,
    variant: str | None = None,
) -> pd.DataFrame:
    """
    Returnerar historiska marknadsdata.

    Kan filtrera på modell och variant.
    """
    df = hamta_historik()

    if df.empty:
        return df

    if (
        modell
        and "modell" in df.columns
    ):
        df = df[
            df["modell"]
            .astype(str)
            .str.contains(
                modell,
                case=False,
                na=False,
            )
        ]

    if (
        variant
        and "variant" in df.columns
    ):
        df = df[
            df["variant"]
            .astype(str)
            .str.contains(
                variant,
                case=False,
                na=False,
            )
        ]

    return df


def hamta_senaste_marknadsdatum():
    """
    Returnerar senaste observationstidpunkt
    från marknadshistoriken.
    """
    df = hamta_historik()

    if (
        df.empty
        or "tid" not in df.columns
    ):
        return None

    tider = pd.to_datetime(
        df["tid"],
        errors="coerce",
    ).dropna()

    if tider.empty:
        return None

    return tider.max()


# ------------------------------------------------------------
# FYND
# ------------------------------------------------------------

def hamta_senaste_fynd() -> pd.DataFrame:
    """
    Hämtar de senaste aktuella fynden.

    Primär källa:

        data/state.json

    Funktionen hanterar flera möjliga strukturer
    eftersom state-formatet kan utvecklas.
    """
    state = hamta_state()

    kandidater = [
        "senaste_fynd",
        "fynd",
        "aktuella_fynd",
    ]

    fynd = []

    for nyckel in kandidater:
        data = state.get(
            nyckel
        )

        if isinstance(
            data,
            list,
        ):
            fynd = data
            break

    if not fynd:
        return pd.DataFrame()

    return pd.DataFrame(
        fynd
    )


# ------------------------------------------------------------
# FYNDUTFALL
# ------------------------------------------------------------

def hamta_fyndutfall() -> pd.DataFrame:
    """
    Hämtar den senaste härledda analysen
    av faktiska fyndutfall.

    Exempel:

        find_outcomes_2026-09.jsonl
    """
    fil = _hitta_senaste_fil(
        FEEDBACK_DIR,
        "find_outcomes_*.jsonl",
    )

    if fil is None:
        return pd.DataFrame()

    data = _las_jsonl(
        fil
    )

    if not data:
        return pd.DataFrame()

    return pd.DataFrame(
        data
    )


def hamta_prissankningar() -> pd.DataFrame:
    """
    Returnerar fynd-event som har fått
    en observerad prissänkning.
    """
    df = hamta_fyndutfall()

    if df.empty:
        return df

    if "utfall" not in df.columns:
        return pd.DataFrame()

    return df[
        df["utfall"].isin(
            [
                "PRISSÄNKT",
                "FÖRSVUNNEN_EFTER_PRISSÄNKNING",
            ]
        )
    ].copy()


# ------------------------------------------------------------
# SCORE
# ------------------------------------------------------------

def hamta_scoreanalys() -> pd.DataFrame:
    """
    Sammanställer score mot faktiskt utfall.
    """
    df = hamta_fyndutfall()

    if (
        df.empty
        or "score" not in df.columns
        or "utfall" not in df.columns
    ):
        return pd.DataFrame()

    data = df.copy()

    data["score"] = pd.to_numeric(
        data["score"],
        errors="coerce",
    )

    data = data.dropna(
        subset=[
            "score",
            "utfall",
        ]
    )

    def scoreintervall(
        score,
    ) -> str:
        if score < 70:
            return "60-69"

        if score < 80:
            return "70-79"

        if score < 90:
            return "80-89"

        return "90+"

    data["scoreintervall"] = (
        data["score"].apply(
            scoreintervall
        )
    )

    resultat = (
        data
        .groupby(
            [
                "scoreintervall",
                "utfall",
            ]
        )
        .size()
        .reset_index(
            name="antal"
        )
    )

    return resultat


# ------------------------------------------------------------
# ML
# ------------------------------------------------------------

def hamta_ml_metrics() -> dict:
    """
    Hämtar metadata och modellresultat
    från ML-träningen.
    """
    metadata = _las_json(
        ML_METADATA_FILE
    )

    if not metadata:
        return {}

    modellnamn = metadata.get(
        "modell"
    )

    metrics = metadata.get(
        "metrics",
        {},
    )

    valt_resultat = {}

    if (
        modellnamn
        and isinstance(
            metrics,
            dict,
        )
    ):
        valt_resultat = metrics.get(
            modellnamn,
            {},
        )

    totalt = {}

    if isinstance(
        valt_resultat,
        dict,
    ):
        totalt = valt_resultat.get(
            "totalt",
            {},
        )

    return {
        "model": modellnamn,
        "trained_at": metadata.get(
            "skapad"
        ),
        "training_rows": metadata.get(
            "antal_traning"
        ),
        "test_rows": metadata.get(
            "antal_test"
        ),
        "observations": metadata.get(
            "antal_observationer"
        ),
        "features": metadata.get(
            "features",
            [],
        ),
        "target": metadata.get(
            "target"
        ),
        "r2": totalt.get(
            "r2"
        ),
        "mae": totalt.get(
            "mae"
        ),
        "rmse": totalt.get(
            "rmse"
        ),
        "mape": totalt.get(
            "mape_procent"
        ),
        "median_error": totalt.get(
            "medianfel"
        ),
        "median_absolute_error": totalt.get(
            "median_absolutfel"
        ),
        "bias": totalt.get(
            "bias"
        ),
        "all_models": metrics,
    }


def hamta_ml_predictions() -> pd.DataFrame:
    """
    Hämtar sparade ML-prediktioner.

    Funktionen är redo för framtida predictions.jsonl.
    """
    data = _las_jsonl(
        ML_PREDICTIONS_FILE
    )

    if not data:
        return pd.DataFrame()

    return pd.DataFrame(
        data
    )


# ------------------------------------------------------------
# DASHBOARD
# ------------------------------------------------------------

def hamta_dashboard_data() -> dict:
    """
    Hämtar sammanfattande data till startsidan.
    """
    historik = hamta_historik()
    fynd = hamta_senaste_fynd()
    utfall = hamta_fyndutfall()
    ml = hamta_ml_metrics()

    state = hamta_state()

    historiska_annonser = len(
        historik
    )

    if (
        not historik.empty
        and "vehicle_id" in historik.columns
    ):
        unika_bilar = historik[
            "vehicle_id"
        ].nunique()

    else:
        unika_bilar = state.get(
            "senaste_antal_unika",
            0,
        )

    annonser_senaste_korning = (
        state.get(
            "senaste_antal_annonser",
            0,
        )
    )

    aktiva_fynd = len(
        fynd
    )

    if aktiva_fynd == 0:
        aktiva_fynd = state.get(
            "senaste_antal_fynd",
            0,
        )

    return {
        "annonser_senaste_korning":
            annonser_senaste_korning,

        "unika_bilar":
            unika_bilar,

        "historiska_annonser":
            historiska_annonser,

        "aktiva_fynd":
            aktiva_fynd,

        "fyndutfall":
            len(utfall),

        "ml_modell":
            ml.get(
                "model"
            )
            or "Ej tränad",

        "ml_mae":
            ml.get(
                "mae"
            ),

        "ml_observationer":
            ml.get(
                "observations"
            )
            or 0,
    }
