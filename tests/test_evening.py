import fcntl
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from scripts import evening
from scripts.install_local_schedule import definitions
from main import main
from reporting import daily_market_report as report


class EveningTests(unittest.TestCase):
    def setUp(self):
        self.previous = Path.cwd()
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.local = self.root / ".local"
        self.local.mkdir()
        self.addCleanup(self.temporary.cleanup)
        self.addCleanup(os.chdir, self.previous)
        for name, value in (("ROOT", self.root), ("LOCAL", self.local)):
            patcher = patch.object(evening, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_failed_collection_stops_report_and_training(self):
        with patch.object(evening.subprocess, "run", return_value=subprocess.CompletedProcess([], 1)) as run:
            self.assertEqual(evening.run(), 1)
        self.assertEqual(run.call_count, 1)
        self.assertIn("main.py", run.call_args.args[0])
        self.assertEqual(json.loads((self.local / "evening-status.json").read_text())["status"], "failed")

    def test_concurrent_run_cannot_collect_or_send(self):
        with (self.local / "evening.lock").open("w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with patch.object(evening.subprocess, "run") as run:
                self.assertEqual(evening.run(), 1)
                run.assert_not_called()

    def test_build_only_does_not_collect_train_or_email(self):
        with patch.object(evening.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)) as run, patch.object(evening, "validate_web"):
            self.assertEqual(evening.run(build_only=True), 0)
        self.assertEqual(run.call_count, 1)
        self.assertIn("web/build_static.py", run.call_args.args[0])

    def test_empty_collection_after_hours_preserves_state(self):
        with patch("main.inom_aktiv_tid", return_value=False), patch("main.hamta_alla_annonser", return_value=[]), patch("main.ladda_state") as state:
            with self.assertRaisesRegex(RuntimeError, "inga annonser"):
                main(evening=True)
            state.assert_not_called()

    def test_web_requires_complete_data(self):
        website = self.root / "web_site"
        website.mkdir()
        (website / "index.html").write_text("<html></html>")
        (website / "data.json").write_text("{}")
        (website / ".nojekyll").touch()
        with self.assertRaisesRegex(RuntimeError, "Ofullständig"):
            evening.validate_web()

    def test_failed_web_build_preserves_live_website_and_full_run_status(self):
        website = self.root / "web_site"
        website.mkdir()
        (website / "index.html").write_text("previous good website")
        (self.local / "evening-status.json").write_text('{"status": "failed"}')
        with patch.object(evening.subprocess, "run", return_value=subprocess.CompletedProcess([], 1)):
            self.assertEqual(evening.run(build_only=True), 1)
        self.assertEqual((website / "index.html").read_text(), "previous good website")
        self.assertEqual(json.loads((self.local / "evening-status.json").read_text())["status"], "failed")

    def test_invalid_web_output_does_not_replace_live_website(self):
        website = self.root / "web_site"
        website.mkdir()
        (website / "index.html").write_text("previous good website")
        with patch.object(evening.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)):
            self.assertEqual(evening.run(build_only=True), 1)
        self.assertEqual((website / "index.html").read_text(), "previous good website")

    def test_archive_preserves_previous_month(self):
        data = self.root / "data"
        data.mkdir()
        (data / "ml_valuation.jsonl").write_text('{"borpris": 100000}\n')
        (self.local / "valuation-month.txt").write_text("2020-01")
        evening.archive_valuations()
        archive = data / "ml_valuation_archive/2020-01.jsonl"
        self.assertEqual(archive.read_text(), '{"borpris": 100000}\n')
        (data / "ml_valuation.jsonl").write_text('{"borpris": 200000}\n')
        evening.archive_valuations()
        self.assertEqual(archive.read_text(), '{"borpris": 100000}\n')

    def test_only_web_agent_remains_without_evening_schedule(self):
        agents = definitions()
        self.assertEqual(len(agents), 1)
        web = agents[0]
        self.assertEqual(web["Label"], "se.fiskabilar.web")
        self.assertNotIn("StartCalendarInterval", web)
        self.assertIn("127.0.0.1", web["ProgramArguments"])
        self.assertIn("8766", web["ProgramArguments"])

    def test_local_report_never_sends_email(self):
        with patch.object(report, "DAILY_REPORT_KATALOG", str(self.root / "reports")), patch.object(report, "_forandringar", return_value={"nya": [], "prisandringar": [], "forsvunna": []}), patch.object(report, "_fynd", return_value=[]), patch.object(report, "_trender", return_value={"upp": [], "ned": [], "stabil": 0}), patch.object(report, "_bygg_rapport", return_value="Test"), patch.object(report, "always"), patch.object(report, "skicka_epost") as send:
            self.assertEqual(report.skapa_och_skicka_rapport(datum="2026-10-14", no_email=True), 0)
            send.assert_not_called()
            saved = report._las_dagens_logg("2026-10-14")
            self.assertEqual(saved["rapport"], "Test")
            self.assertFalse(saved["email_skickat"])


if __name__ == "__main__":
    unittest.main()
