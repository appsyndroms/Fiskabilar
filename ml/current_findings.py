"""Live-fynd bygger på senaste observationen per bil och den valda modellen."""
from __future__ import annotations

import pandas as pd

from config import BILAR, MIN_MIL, MAX_MIL
from ml.normalization import normalisera_modell, normalisera_variant

from ml.features import build_features
from ml.fynddetektor import detektera_fynd


def current_observations(dataset: pd.DataFrame, as_of=None, max_age_days: int = 2) -> pd.DataFrame:
    cutoff = pd.Timestamp.now(tz="UTC") if as_of is None else pd.to_datetime(as_of, utc=True)
    rows = dataset.copy()
    rows["Tid"] = pd.to_datetime(rows["Tid"], errors="coerce", utc=True)
    rows = rows[rows["Tid"].notna() & (rows["Tid"] <= cutoff)]
    rows = rows[rows["Identity"].notna() & rows["Identity"].astype(str).str.strip().ne("")]
    rows = rows.sort_values("Tid").drop_duplicates("Identity", keep="last")
    rows = rows[rows["Tid"] >= cutoff - pd.Timedelta(days=max_age_days)]
    rows = rows[pd.to_numeric(rows["Mil"], errors="coerce").between(MIN_MIL, MAX_MIL)]
    configured = {(normalisera_modell(car["modell_visning"]), normalisera_variant(variant)):
                  (car["arsmodell_min"], car["arsmodell_max"])
                  for car in BILAR for variant in car["variant_kraven"]}
    eligible = []
    for row in rows.to_dict("records"):
        limits = configured.get((normalisera_modell(row["Model"]), normalisera_variant(row["Variant"])))
        eligible.append(bool(limits and limits[0] <= row["ModelYear"] <= limits[1]))
    return rows.loc[eligible].reset_index(drop=True)


def build_current_findings(dataset: pd.DataFrame, model, as_of=None) -> pd.DataFrame:
    cutoff = pd.Timestamp.now(tz="UTC") if as_of is None else pd.to_datetime(as_of, utc=True)
    current = current_observations(dataset, as_of=cutoff)
    if current.empty:
        return pd.DataFrame()
    predictions = model.predict(build_features(current))
    # Live-jämförelser ska också vara aktuella annonser, inte gamla sålda objekt.
    return detektera_fynd(current, current, predictions, as_of=cutoff)
