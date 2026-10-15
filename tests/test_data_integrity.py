import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

from history import identity, state
from ml.analyze_model import _tidsmässig_split
from ml.train_market_model import _bygg_dataset
from ml import generate_ml_valuation, predict_market_value
from reporting import daily_market_report as report
from pipeline import candidates


class DataIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_corrupt_identity_store_is_not_replaced_with_empty_store(self):
        path = self.root / "identity.json"
        path.write_text("{broken")
        with patch.object(identity, "IDENTITY_FIL", str(path)), patch.object(identity, "_IDENTITY_CACHE", None):
            with self.assertRaises(RuntimeError):
                identity._ladda()
        self.assertEqual(path.read_text(), "{broken")

    def test_failed_state_serialization_preserves_last_good_file(self):
        path = self.root / "state.json"
        path.write_text('{"old": true}')
        with patch.object(state, "STATE_FIL", str(path)):
            with self.assertRaises(TypeError):
                state.spara_state({"invalid": object()})
        self.assertEqual(json.loads(path.read_text()), {"old": True})

    def test_same_day_rerun_does_not_mark_a_missing_car_disappeared(self):
        saved = {"car": {"status": "AKTIV", "missade_korningar": 0}}
        state._markera_forsvunna(saved, set(), "2026-10-14")
        state._markera_forsvunna(saved, set(), "2026-10-14")
        self.assertEqual(saved["car"]["status"], "SAKNAS")
        self.assertEqual(saved["car"]["missade_korningar"], 1)
        state._markera_forsvunna(saved, set(), "2026-10-15")
        self.assertEqual(saved["car"]["status"], "FÖRSVUNNEN")

    def test_ml_uses_ad_prices_as_well_as_valuation_observation_prices(self):
        shared = {"modell": "v60", "variant": "T6 AWD", "miltal": 5000,
                  "arsmodell": 2023, "tid": "2026-10-14T19:00:00+02:00"}
        data = pd.DataFrame([{**shared, "typ": "annons", "pris": 400000},
                             {**shared, "typ": "marknadsvarde", "annonspris": 410000}])
        self.assertEqual(sorted(_bygg_dataset(data)["Price"].tolist()), [400000, 410000])

    def test_training_and_test_do_not_share_an_observation_timestamp(self):
        data = pd.DataFrame({"Tid": pd.to_datetime(["2026-10-13", "2026-10-14", "2026-10-14", "2026-10-14"], utc=True)})
        train, test = _tidsmässig_split(data)
        self.assertLess(train["Tid"].max(), test["Tid"].min())

    def test_single_timestamp_cannot_claim_temporal_validation(self):
        data = pd.DataFrame({"Tid": pd.to_datetime(["2026-10-14", "2026-10-14"], utc=True)})
        with self.assertRaises(ValueError):
            _tidsmässig_split(data)

    def test_training_cli_fails_on_missing_data_instead_of_succeeding_without_work(self):
        project = Path(__file__).resolve().parents[1]
        result = subprocess.run([sys.executable, "-m", "ml.train_market_model"], cwd=self.root,
                                env=dict(os.environ, PYTHONPATH=str(project)), capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Ingen marknadshistorik", result.stderr)

    def test_corrupt_report_log_cannot_be_silently_overwritten(self):
        with patch.object(report, "DAILY_REPORT_KATALOG", str(self.root)):
            path = Path(report._rapportfil("2026-10-14"))
            path.write_text("{broken\n")
            with self.assertRaises(ValueError):
                report._spara_logg({"datum": "2026-10-14"})
        self.assertEqual(path.read_text(), "{broken\n")

    def test_report_serialization_failure_preserves_previous_report(self):
        with patch.object(report, "DAILY_REPORT_KATALOG", str(self.root)):
            report._spara_logg({"datum": "2026-10-14", "rapport": "old"})
            with self.assertRaises(TypeError):
                report._spara_logg({"datum": "2026-10-14", "rapport": object()})
            self.assertEqual(report._las_dagens_logg("2026-10-14")["rapport"], "old")

    def test_report_build_failure_returns_error_and_preserves_sent_email_marker(self):
        with patch.object(report, "DAILY_REPORT_KATALOG", str(self.root)), patch.object(report, "_forandringar", side_effect=RuntimeError("bad data")), patch.object(report, "always"), patch.object(report, "error"), patch.object(report, "skicka_epost") as send:
            report._spara_logg({"datum": "2026-10-14", "email_skickat": True,
                               "email_skickat_tid": "2026-10-14T22:00:00+02:00"})
            self.assertEqual(report.skapa_och_skicka_rapport(datum="2026-10-14", no_email=True), 1)
            self.assertTrue(report._las_dagens_logg("2026-10-14")["email_skickat"])
            send.assert_not_called()

    def test_partial_ml_predictions_cannot_overwrite_previous_valuations(self):
        path = self.root / "valuation.jsonl"
        path.write_text('{"old": true}\n')
        configuration = [{"modell_visning": "V60", "arsmodell_min": 2023,
                          "arsmodell_max": 2023, "variant_kraven": {"T6 AWD": []}}]
        with patch.object(generate_ml_valuation, "ML_VARDERING_FIL", str(path)), patch.object(generate_ml_valuation, "BILAR", configuration), patch.object(generate_ml_valuation, "modell_finns", return_value=True), patch.object(generate_ml_valuation, "_milintervall", return_value=[1000, 1500]), patch.object(generate_ml_valuation, "prediktera_borpris", side_effect=[400000, None]):
            with self.assertRaises(ValueError):
                generate_ml_valuation.skriv_ml_valuation()
        self.assertEqual(path.read_text(), '{"old": true}\n')

    def test_prediction_loads_model_once_and_invalidates_on_file_change(self):
        path = self.root / "model.joblib"
        path.write_bytes(b"first")
        with patch.object(predict_market_value, "MODEL_FIL", path), patch.object(predict_market_value.joblib, "load", side_effect=["first model", "second model"]) as load:
            self.assertEqual(predict_market_value.ladda_modell(), "first model")
            self.assertEqual(predict_market_value.ladda_modell(), "first model")
            stamp = path.stat().st_mtime_ns
            os.utime(path, ns=(stamp + 1000000, stamp + 1000000))
            self.assertEqual(predict_market_value.ladda_modell(), "second model")
            self.assertEqual(load.call_count, 2)

    def test_valuation_bug_cannot_silently_remove_a_candidate(self):
        with patch.object(candidates, "_ar_leasingannons", return_value=False), patch.object(candidates, "berakna_fynd", side_effect=RuntimeError("bad valuation")):
            with self.assertRaisesRegex(RuntimeError, "bad valuation"):
                candidates.processa_kandidater([{"modell": "v60", "miltal": 5000}], {}, {})

    def test_failed_observation_write_stops_candidate_processing(self):
        with patch.object(candidates, "_ar_leasingannons", return_value=False), patch.object(candidates, "berakna_fynd", return_value={"niva": "test", "diff": 20000}), patch.object(candidates, "berakna_fyndscore", return_value=70), patch.object(candidates, "spara_marknadsvardesobservation", side_effect=OSError("disk full")), patch.object(candidates, "spara_fyndfeedback") as feedback:
            with self.assertRaises(OSError):
                candidates.processa_kandidater([{"modell": "v60", "miltal": 5000}], {}, {})
            feedback.assert_not_called()


if __name__ == "__main__":
    unittest.main()
