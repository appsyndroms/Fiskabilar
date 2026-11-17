"""Empirisk korrigering och felmarginal från tidsmässigt undanlagda annonser.

Marginalen är en uppmätt felkvantil, inte en garanti eller sannolikhet för fynd.
Utrustning och faktiska slutpriser saknas fortfarande i modellunderlaget.
"""
from functools import lru_cache
import json
from pathlib import Path
import numpy as np
import pandas as pd
from ml.normalization import normalisera_modell, normalisera_variant

METADATA_FILE = Path("data/ml/model_metadata.json")
MIN_GROUP_CARS = 30
ERROR_QUANTILE = 0.90
MIN_MARGIN_KR = 20000.0
MIN_MARGIN_PCT = 0.05


def key(model, variant):
    return f"{normalisera_modell(model)} | {normalisera_variant(variant)}"


def _stats(errors):
    correction = max(0.0, float(errors.mean()))
    residuals = errors - correction
    return {"cars": len(errors), "overvaluation_kr": correction,
            "error_margin_kr": max(0.0, float(residuals.quantile(ERROR_QUANTILE))),
            "raw_bias_kr": float(errors.mean()), "raw_mae_kr": float(errors.abs().mean())}


def build_calibration(test, predictions):
    rows = test.copy().reset_index(drop=True)
    rows["_error"] = np.asarray(predictions, dtype=float) - rows["Price"].to_numpy(dtype=float)
    if rows.empty or not np.isfinite(rows["_error"]).all():
        raise ValueError("Kalibrering kräver giltiga testprediktioner.")
    # En fysisk bil ska inte få större vikt för att den annonserats ofta.
    if "Identity" in rows:
        known = rows["Identity"].notna() & rows["Identity"].astype(str).str.strip().ne("")
        rows = pd.concat([rows.loc[known].sort_values("Tid").drop_duplicates("Identity", keep="last"), rows.loc[~known]])
    rows["_group"] = [key(m, v) for m, v in zip(rows["Model"], rows["Variant"])]
    return {"version": 1, "quantile": ERROR_QUANTILE, "min_group_cars": MIN_GROUP_CARS,
            "global": _stats(rows["_error"]),
            "groups": {name: _stats(group["_error"]) for name, group in rows.groupby("_group") if len(group) >= MIN_GROUP_CARS},
            "evaluated_from": str(rows["Tid"].min()), "evaluated_until": str(rows["Tid"].max())}


def stats_for(calibration, model, variant):
    return calibration["groups"].get(key(model, variant), calibration["global"])


class CalibratedModel:
    """Exporterad modell: samma nedåtkorrigering för direktprediktion och webb."""
    def __init__(self, estimator, calibration):
        self.estimator = estimator
        self.calibration_ = calibration

    def predict(self, features):
        # Små enbilsprediktioner ska inte starta en trådpool för varje annons.
        # Detta ändrar endast parallellismen, inte modellens beräkning.
        steps = getattr(self.estimator, "named_steps", {})
        if isinstance(steps, dict):
            final = steps.get("model")
            if final is not None and hasattr(final, "n_jobs") and final.n_jobs != 1:
                final.set_params(n_jobs=1)
        predictions = np.asarray(self.estimator.predict(features), dtype=float)
        corrections = np.array([stats_for(self.calibration_, m, v)["overvaluation_kr"]
                                for m, v in zip(features["Model"], features["Variant"])])
        if not np.isfinite(predictions).all():
            raise ValueError("Modellen gav ogiltiga prisprognoser.")
        return np.maximum(1.0, predictions - corrections)


@lru_cache(maxsize=1)
def _read_metadata(path, modified_ns):
    return json.loads(path.read_text(encoding="utf-8"))


def metadata():
    if not METADATA_FILE.exists():
        return {}
    return _read_metadata(METADATA_FILE.resolve(), METADATA_FILE.stat().st_mtime_ns)


def required_margin(model, variant, prediction, calibration=None):
    if calibration is None:
        saved = metadata()
        calibration = saved.get("calibration")
    else:
        saved = {}
    if calibration:
        error = stats_for(calibration, model, variant)["error_margin_kr"]
    else:
        # Kompatibilitet vid uppgradering från en äldre modell, inte en felkvantil.
        error = saved.get("metrics", {}).get("MAE", 0)
    return float(max(MIN_MARGIN_KR, MIN_MARGIN_PCT * prediction, error))
