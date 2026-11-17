"""Live-fynd bygger på senaste observationen per bil och den valda modellen."""
from __future__ import annotations

import pandas as pd

from config import BILAR, MIN_MIL, MAX_MIL
from ml.normalization import normalisera_modell, normalisera_variant

from ml.features import build_features
from ml.calibration import required_margin
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
    # Ett färskt komplett insamlingsdygn ska inte blandas med gårdagens bilar.
    days = current["Tid"].dt.tz_convert("Europe/Stockholm").dt.date
    current = current.loc[days == days.max()].reset_index(drop=True)
    pricing_rows = current.copy()
    pricing_rows["Tid"] = cutoff
    predictions = model.predict(build_features(pricing_rows))
    profile = getattr(model, "calibration_", None)
    profile = profile if isinstance(profile, dict) else None
    if profile is not None:
        return _shared_calibrated_findings(current, predictions, profile)
    current = current.copy()
    current["RequiredMargin"] = [required_margin(m, v, p, calibration=profile)
                                 for m, v, p in zip(current["Model"], current["Variant"], predictions)]
    # Live-jämförelser ska också vara aktuella annonser, inte gamla sålda objekt.
    return detektera_fynd(current, current, predictions, as_of=cutoff)


def _shared_calibrated_findings(current, predictions, calibration):
    """Samma värdering, jämförelsepristak och kvalificering som fyndmejlen."""
    from valuation.market_value import bygg_marknadsunderlag, berakna_fynd
    from scoring.score import berakna_fyndscore
    from ml.fynddetektor import _fyndklass
    cars = []
    for row in current.to_dict("records"):
        car = {"modell": row["Model"], "variant": row["Variant"], "arsmodell": int(row["ModelYear"]),
               "miltal": float(row["Mil"]), "annonspris": float(row["Price"]),
               "vehicle_id": row["Identity"], "url": None if pd.isna(row.get("url")) else row.get("url")}
        for field in ("utrustningsniva", "dragkrok", "varmare", "volvo_selekt", "stor_batteri"):
            value = row.get(field)
            car[field] = None if pd.isna(value) else value
        cars.append(car)
    market = bygg_marknadsunderlag(cars)
    findings = []
    for car, prediction in zip(cars, predictions):
        value = berakna_fynd(car, market, ml_prediction=float(prediction), calibration=calibration)
        score = berakna_fyndscore(car, value)
        if value["niva"] is None or score < 60:
            continue
        price = car["annonspris"]
        peer = value["marknadsdiagnostik"]["median_justerat"]
        model_pct = value["diff"] / price * 100
        market_pct = (price-peer) / peer * 100
        rank = model_pct + max(0, -market_pct)
        findings.append({"Identity":car["vehicle_id"], "Model":car["modell"], "Variant":car["variant"], "ModelYear":car["arsmodell"],
                         "Mil":car["miltal"], "Price":price, "Prediction":value["marknadsvarde"],
                         "ModelVsActualPct":model_pct, "ComparableWeightedMedian":peer,
                         "ComparableDeviationPct":market_pct, "ComparableN":value["jamforelseantal"],
                         "RequiredMargin":value["fyndmarginal_kr"], "FyndScore":rank,
                         "CandidateScore":score, "Fyndklass":_fyndklass(rank), "url":car["url"]})
    return pd.DataFrame(findings).sort_values("FyndScore",ascending=False).reset_index(drop=True) if findings else pd.DataFrame()
