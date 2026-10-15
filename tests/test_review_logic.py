from contextlib import ExitStack
from datetime import datetime, timezone
import importlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd

from history import analysis_storage, analysis_trends
from ml import analyze_model, train_market_model
from ml.comparable_market import _jämförbara_observationer
from ml.current_findings import current_observations, build_current_findings
from ml.fynd_export import exportera_fynd
from ml.fynddetektor import _get_ad_url
from valuation import market_value
from reporting import daily_market_report as report

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "web"))
web = importlib.import_module("build_static")
web_data = importlib.import_module("data_loader")
web_analysis = importlib.import_module("analysis")


def observation(identity, price, time):
    return {"Identity": identity, "Price": price, "Tid": time, "Model": "v60",
            "Variant": "t6 awd", "Mil": 5000, "ModelYear": 2023}


class ReviewLogicTests(unittest.TestCase):
    def test_historical_comparisons_cannot_see_future_prices(self):
        row = observation("target", 300000, "2026-10-10T12:00:00Z")
        data = pd.DataFrame([observation(str(i), 400000, "2026-10-11T12:00:00Z") for i in range(3)])
        self.assertTrue(_jämförbara_observationer(data, row).empty)
        self.assertEqual(len(_jämförbara_observationer(data, row, as_of="2026-10-12T12:00:00Z")), 3)

    def test_current_findings_use_latest_price_and_ignore_expired_or_future_rows(self):
        data = pd.DataFrame([observation("car", 300000, "2026-10-14T12:00:00Z"),
                             observation("car", 400000, "2026-10-15T10:00:00Z"),
                             observation("old", 200000, "2026-10-01T12:00:00Z"),
                             observation("future", 200000, "2026-10-16T12:00:00Z")])
        current = current_observations(data, as_of="2026-10-15T12:00:00Z")
        self.assertEqual(current["Identity"].tolist(), ["car"])
        self.assertEqual(current["Price"].tolist(), [400000])

    def test_expired_comparison_cars_cannot_make_a_current_car_a_bargain(self):
        data = pd.DataFrame([observation("current", 300000, "2026-10-15T10:00:00Z"),
                             *[observation(str(i), 500000, "2026-10-01T12:00:00Z") for i in range(3)]])
        model = MagicMock()
        model.predict.side_effect = lambda x: np.full(len(x), 500000)
        self.assertTrue(build_current_findings(data, model, as_of="2026-10-15T12:00:00Z").empty)

    def test_live_findings_and_comparisons_follow_configured_mileage_and_years(self):
        rows = [{**observation(str(mil), 400000, "2026-10-15T10:00:00Z"), "Mil": mil}
                for mil in (0, 999, 1000, 12000, 12001)]
        rows.append({**observation("wrong-year", 400000, "2026-10-15T10:00:00Z"), "ModelYear": 2022})
        current = current_observations(pd.DataFrame(rows), as_of="2026-10-15T12:00:00Z")
        self.assertEqual(sorted(current["Mil"].tolist()), [1000, 12000])

    def test_export_uses_the_winning_model_instead_of_always_random_forest(self):
        data = pd.DataFrame([observation(str(i), 400000, pd.Timestamp("2026-10-01", tz="UTC") + pd.Timedelta(hours=i)) for i in range(60)])
        linear, forest = MagicMock(), MagicMock()
        for model in (linear, forest):
            model.predict.side_effect = lambda x: np.full(len(x), 400000)
        with tempfile.TemporaryDirectory() as tmp, ExitStack() as stack:
            replacements = {"_ladda_jsonl": MagicMock(return_value=data),
                            "_bygg_dataset": lambda x: x, "_deduplicera_dataset": lambda x: x,
                            "_modeller": lambda: {"linear_regression": linear, "random_forest": forest},
                            "_metrics": MagicMock(side_effect=[{"MAE": 1}, {"MAE": 10}]),
                            "_feature_importance": lambda x: None,
                            "build_current_findings": MagicMock(return_value=pd.DataFrame()),
                            "exportera_fynd": MagicMock(),
                            "MODEL_FIL": Path(tmp) / "model.joblib", "METADATA_FIL": Path(tmp) / "model.json"}
            for name in ("_modell_variant_diagnostik", "_största_felen", "_diagnostik_per_modell", "_diagnostik_330e_historik"):
                replacements[name] = MagicMock()
            for name, value in replacements.items():
                stack.enter_context(patch.object(analyze_model, name, value))
            stack.enter_context(patch.object(analyze_model.joblib, "dump"))
            analyze_model.main(["--debug"])
            self.assertIs(replacements["build_current_findings"].call_args.args[1], linear)
            self.assertEqual(json.loads((Path(tmp) / "model.json").read_text())["model_type"], "linear_regression")

    def test_identity_aliases_do_not_become_independent_ml_cars(self):
        with patch.object(train_market_model, "canonical_vehicle_id", return_value="vehicle:new"):
            self.assertEqual(train_market_model._första_identitet(pd.Series({"vehicle_id": "vehicle:old"})), "vehicle_id:vehicle:new")

    def test_trend_counts_each_car_once_and_uses_latest_price_of_day(self):
        rows = [{"vehicle_id": "a", "pris": 250000, "tid": "2026-10-15T10:00:00+02:00"}] * 10
        rows += [{"vehicle_id": "a", "pris": 450000, "tid": "2026-10-15T19:00:00+02:00"},
                 {"vehicle_id": "b", "pris": 400000, "tid": "2026-10-15T19:00:00+02:00"},
                 {"vehicle_id": "c", "pris": 410000, "tid": "2026-10-15T19:00:00+02:00"}]
        with patch.object(analysis_trends, "canonical_vehicle_id", side_effect=lambda x: x):
            daily = analysis_trends._bygg_dagliga_priser(rows)[0]
        self.assertEqual(daily["pris"], 410000)
        self.assertEqual(daily["antal_observationer"], 3)

    def test_model_aliases_do_not_split_trends_into_separate_markets(self):
        first = {"modell": "BMW 330E-xDrive Touring", "variant": "330e-xDrive Touring", "arsmodell": 2024}
        second = {"modell": "330e xDrive Touring", "variant": "330e xDrive Touring", "arsmodell": 2024}
        self.assertEqual(analysis_trends._trendkategori(first), analysis_trends._trendkategori(second))

    def test_valuation_history_keeps_the_score_needed_by_daily_report(self):
        with patch.object(analysis_storage, "resolve_vehicle_id", return_value="car"), patch.object(analysis_storage, "canonical_vehicle_id", return_value="car"), patch.object(analysis_storage, "_skriv") as save:
            analysis_storage.spara_marknadsvardesobservation({"vehicle_id": "car", "annonspris": 400000}, {"diff": 40000}, score=75)
        self.assertEqual(save.call_args.args[0]["fyndscore"], 75)

    def test_report_uses_saved_feedback_but_rejects_old_prices_and_previous_days(self):
        ad = {"typ": "annons", "vehicle_id": "car", "tid": "2026-10-15T19:00:00+02:00", "pris": 400000, "miltal": 5000}
        feedback = {"vehicle_id": "car", "tid": ad["tid"], "annonspris": 400000, "miltal": 5000, "fyndscore": 75, "diff": 40000}
        with patch.object(report, "_annonsobservationer", return_value=[ad]), patch.object(report, "_varderingar", return_value=[]), patch.object(report, "canonical_vehicle_id", side_effect=lambda x: x), patch.object(report, "_fyndfeedback", return_value=[feedback]):
            self.assertEqual(len(report._fynd("2026-10-15")), 1)
            feedback["annonspris"] = 350000
            self.assertEqual(report._fynd("2026-10-15"), [])
            feedback["annonspris"] = 400000
            feedback["tid"] = "2026-10-14T19:00:00+02:00"
            self.assertEqual(report._fynd("2026-10-15"), [])

    def test_web_cannot_attach_current_link_to_outdated_bargain_price(self):
        stamp = datetime.now(timezone.utc).isoformat()
        ad = {"typ": "annons", "vehicle_id": "car", "tid": stamp, "pris": 400000, "miltal": 5000,
              "arsmodell": 2023, "url": "https://example.test/current-car"}
        finding = {"Identity": "vehicle_id:car", "Price": 350000, "Mil": 5000, "ModelYear": 2023}
        self.assertEqual(web._berika_fynd_med_aktuell_url([finding], [ad])[0]["url"], "")
        finding["Price"] = 400000
        self.assertEqual(web._berika_fynd_med_aktuell_url([finding], [ad])[0]["url"], ad["url"])

    def test_latest_missing_url_cannot_revive_an_older_cheap_listing(self):
        stamp = datetime.now(timezone.utc)
        old = {"typ": "annons", "vehicle_id": "car", "tid": (stamp - pd.Timedelta(hours=1)).isoformat(),
               "pris": 350000, "miltal": 5000, "arsmodell": 2023, "url": "https://example.test/old"}
        current = {**old, "tid": stamp.isoformat(), "pris": 400000, "url": None}
        finding = {"Identity": "vehicle_id:car", "Price": 350000, "Mil": 5000, "ModelYear": 2023}
        self.assertEqual(web._berika_fynd_med_aktuell_url([finding], [old, current])[0]["url"], "")

    def test_naive_and_aware_times_compare_in_swedish_timezone(self):
        old = {"vehicle_id": "car", "tid": "2026-10-15T13:00:00", "pris": 350000}
        current = {"vehicle_id": "car", "tid": "2026-10-15T12:00:00Z", "pris": 400000}
        self.assertEqual(web_analysis.latest_by_vehicle([old, current])[0]["pris"], 400000)

    def test_corrupt_existing_files_fail_instead_of_disappearing_from_web_and_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "broken.jsonl"
            path.write_text('{"valid": true}\n{broken\n')
            with self.assertRaises(ValueError):
                web_data.read_jsonl(path)
            with patch.object(analysis_storage, "_historikfiler", return_value=[str(path)]):
                with self.assertRaises(ValueError):
                    analysis_storage._las_observationer()
            path.write_text("{broken")
            with self.assertRaises(ValueError):
                web_data.read_json(path, {})

    def test_failed_findings_export_preserves_previous_complete_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "findings.jsonl"
            path.write_text('{"previous": true}\n')
            with self.assertRaises(TypeError):
                exportera_fynd(pd.DataFrame({"value": [1, object()]}), path=path)
            self.assertEqual(path.read_text(), '{"previous": true}\n')

    def test_historical_finding_cannot_use_a_future_ad_url(self):
        row = observation("car", 400000, "2026-10-10T12:00:00Z")
        data = pd.DataFrame([{**row, "url": "https://example.test/known"},
                             {**row, "Tid": "2026-10-12T12:00:00Z", "url": "https://example.test/future"}])
        self.assertEqual(_get_ad_url(row, data), "https://example.test/known")

    def test_same_source_id_on_different_cars_is_not_self_comparison(self):
        first = {"vehicle_id": "car-a", "kalla": "bilweb", "annons_id": "123"}
        second = {"vehicle_id": "car-b", "kalla": "bytbil", "annons_id": "123"}
        with patch.object(market_value, "canonical_vehicle_id", side_effect=lambda x: x):
            self.assertFalse(market_value._ar_samma_annons(first, second))
            self.assertNotEqual(market_value._jamforelseidentitet(first), market_value._jamforelseidentitet(second))
            first.pop("vehicle_id")
            second.pop("vehicle_id")
            self.assertFalse(market_value._ar_samma_annons(first, second))
            self.assertNotEqual(market_value._jamforelseidentitet(first), market_value._jamforelseidentitet(second))

    def test_same_physical_car_is_excluded_even_when_ad_id_and_url_change(self):
        first = {"vehicle_id": "car", "annons_id": "old", "url": "https://example.test/old"}
        second = {"vehicle_id": "car", "annons_id": "new", "annons_url": "https://example.test/new"}
        with patch.object(market_value, "canonical_vehicle_id", side_effect=lambda x: x):
            self.assertTrue(market_value._ar_samma_annons(first, second))


if __name__ == "__main__":
    unittest.main()
