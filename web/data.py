"""
Dataåtkomst för Fiskabilar Analytics.
Den här modulen är den centrala platsen där webbappen
läser analysdata från projektets datafiler.
"""
from __future__ import annotations
import json
from pathlib import Path
import pandas as pd
ROOT = Path(__file__).resolve().parent.parent
MARKET_HISTORY = (
    ROOT
    / "data"
    / "market_history"
    / "market_history.jsonl"
)
STATE_FILE = (
    ROOT
    / "data"
    / "state.json"
)
ML_METADATA_FILE = (
    ROOT
    / "data"
    / "ml"
    / "model_metadata.json"
)
ML_PREDICTIONS_FILE = (
    ROOT
    / "data"
    / "ml"
    / "predictions.jsonl"
)
def _las_jsonl(path: Path) -> list[dict]:
    """Läser en JSONL-fil."""
    if not path.exists():
        return []
    resultat = []
    with path.open(
        "r",
        encoding="utf-8",
    ) as fil:
        for rad in fil:
            rad = rad.strip()
            if not rad:
                continue
            try:
                data = json.loads(rad)
            except json.JSONDecodeError:
                continue
            if isinstance(data, dict):
                resultat.append(data)
    return resultat
def _las_json(path: Path) -> dict:
    """Läser en JSON-fil."""
    if not path.exists():
        return {}
    try:
        with path.open(
            "r",
            encoding="utf-8",
        ) as fil:
            data = json.load(fil)
        return data if isinstance(data, dict) else {}
    except (
        OSError,
        json.JSONDecodeError,
    ):
        return {}
def _las_state() -> dict:
    """Läser Fiskabilars state-fil."""
    return _las_json(STATE_FILE)
def hamta_historik() -> pd.DataFrame:
    """
    Läser marknadshistoriken.
    Returnerar en tom DataFrame om historikfilen saknas.
    """
    data = _las_jsonl(
        MARKET_HISTORY
    )
    if not data:
        return pd.DataFrame()
    return pd.DataFrame(data)
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
    if modell and "modell" in df.columns:
        df = df[
            df["modell"]
            .astype(str)
            .str.contains(
                modell,
                case=False,
                na=False,
            )
        ]
    if variant and "variant" in df.columns:
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
def hamta_ml_metrics() -> dict:
    """
    Hämtar metadata och modellresultat från ML-träningen.
    Returnerar en tom dict om modellen ännu inte har tränats.
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
    if modellnamn and isinstance(
        metrics,
        dict,
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
        "feature_importance": {},
        "all_models": metrics,
    }
def hamta_ml_predictions() -> pd.DataFrame:
    """
    Hämtar sparade ML-prediktioner om sådana finns.
    Den filen skapas inte av nuvarande träningspipeline,
    därför returneras en tom DataFrame tills den finns.
    """
    data = _las_jsonl(
        ML_PREDICTIONS_FILE
    )
    if not data:
        return pd.DataFrame()
    return pd.DataFrame(data)
def hamta_senaste_fynd() -> pd.DataFrame:
    """
    Hämtar de bästa aktuella fynden från state.
    """
    state = _las_state()
    fynd = state.get(
        "senaste_fynd",
        [],
    )
    if not fynd:
        return pd.DataFrame()
    if not isinstance(
        fynd,
        list,
    ):
        return pd.DataFrame()
    return pd.DataFrame(fynd)
def hamta_dashboard_data() -> dict:
    """
    Hämtar sammanfattande data till startsidan.
    """
    historik = hamta_historik()
    state = _las_state()
    ml = hamta_ml_metrics()
    historiska_annonser = len(
        historik
    )
    annonser_senaste_korning = state.get(
        "senaste_antal_annonser",
        0,
    )
    unika_bilar = state.get(
        "senaste_antal_unika",
        0,
    )
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
        "ml_modell":
            ml.get(
                "model"
            ) or "Ej tränad",
        "ml_mae":
            (
                f"{ml['mae']:,.0f} kr".replace(
                    ",",
                    " ",
                )
                if ml.get("mae") is not None
                else "—"
            ),
    }
