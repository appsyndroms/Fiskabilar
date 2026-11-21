from contextlib import ExitStack
from datetime import datetime
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import main as app
from history import analysis_storage as storage


class CollectionSnapshotTests(unittest.TestCase):
    def test_all_ads_receive_actual_completed_snapshot_time_after_midnight(self):
        start = datetime.fromisoformat("2026-11-20T23:57:00+01:00")
        finish = datetime.fromisoformat("2026-11-21T00:02:00+01:00")
        current = [start]
        cars = [{"vehicle_id": "one"}, {"vehicle_id": "two"}]

        def collect(*args):
            current[0] = finish
            return cars

        with ExitStack() as stack:
            for name in ("logga_identity_diagnostik", "skriv_livscykel_diagnostik", "berika_med_historik", "bygg_marknadstrender", "spara_state", "skriv_diagnostik", "skriv_sammanfattning"):
                stack.enter_context(patch.object(app, name))
            clock = stack.enter_context(patch.object(app, "datetime"))
            clock.now.side_effect = lambda *args: current[0]
            stack.enter_context(patch.object(app, "hamta_alla_annonser", side_effect=collect))
            stack.enter_context(patch.object(app, "deduplicera", return_value=cars))
            stack.enter_context(patch.object(app, "uppdatera_och_berika", return_value=cars))
            stack.enter_context(patch.object(app, "ladda_state", return_value={}))
            stack.enter_context(patch.object(app, "bygg_historikindex", return_value={}))
            stack.enter_context(patch.object(app, "bygg_marknadsunderlag", return_value={}))
            stack.enter_context(patch.object(app, "processa_kandidater", return_value=({}, [])))
            save = stack.enter_context(patch.object(app, "spara_annonsobservation"))
            result = app.main(evening=True)
        self.assertEqual(result, {"date": "2026-11-21", "observed_at": finish.isoformat(), "ads": 2})
        self.assertEqual(save.call_count, 2)
        for args in save.call_args_list:
            self.assertEqual(args.kwargs["observed_at"], finish)

    def test_snapshot_month_and_timestamp_are_preserved_during_later_writes(self):
        stamp = datetime.fromisoformat("2026-11-30T23:59:00+01:00")
        with tempfile.TemporaryDirectory() as directory, patch.object(storage, "HISTORIK_KATALOG", directory), patch.object(storage, "_migrera_legacy"), patch.object(storage, "resolve_vehicle_id", return_value="car"), patch.object(storage, "canonical_vehicle_id", side_effect=lambda x: x):
            storage.spara_annonsobservation({"annonspris": 400000}, observed_at=stamp)
            path = Path(directory) / "market_history_2026-11.jsonl"
            row = json.loads(path.read_text())
            self.assertEqual(row["tid"], stamp.isoformat())
            self.assertEqual(row["pris"], 400000)
            self.assertEqual(len(list(Path(directory).glob("*.jsonl"))), 1)

    def test_snapshot_requires_timezone(self):
        with self.assertRaises(ValueError):
            storage.spara_annonsobservation({}, observed_at=datetime(2026, 11, 21))
