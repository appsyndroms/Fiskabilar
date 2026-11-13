import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
from reporting import daily_market_report as reports
from reporting.send_evening_report import send


class EveningReportEmailTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        p = patch.object(reports, "DAILY_REPORT_KATALOG", self.tmp.name)
        p.start()
        self.addCleanup(p.stop)
        self.day = "2026-11-12"
        self.post = {"datum": self.day, "rapport": "Sparad kvällsrapport", "email_skickat": False}
        reports._spara_logg(self.post)

    def test_sends_saved_report_and_records_receipt_once(self):
        with patch.object(reports, "skicka_epost", return_value=True) as mail:
            self.assertTrue(send(self.day, "https://example.test/"))
            self.assertFalse(send(self.day, "https://example.test/"))
            mail.assert_called_once()
            self.assertIn("Sparad kvällsrapport", mail.call_args.args[1])
            self.assertIn("https://example.test/", mail.call_args.args[1])
        saved = reports._las_dagens_logg(self.day)
        self.assertTrue(saved["email_skickat"])
        self.assertTrue(saved["email_skickat_tid"])
        self.assertEqual(saved["rapport"], self.post["rapport"])

    def test_delivery_failure_is_red_and_retryable(self):
        with patch.object(reports, "skicka_epost", return_value=False):
            with self.assertRaises(RuntimeError):
                send(self.day, "https://example.test/")
        self.assertFalse(reports._las_dagens_logg(self.day)["email_skickat"])

    def test_missing_or_failed_report_never_sends(self):
        with patch.object(reports, "skicka_epost") as mail:
            with self.assertRaises(RuntimeError):
                send("2026-11-11", "https://example.test/")
            reports._spara_logg(dict(self.post, status="FEL"))
            with self.assertRaises(RuntimeError):
                send(self.day, "https://example.test/")
            mail.assert_not_called()
