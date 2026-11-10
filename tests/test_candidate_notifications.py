import os
import unittest
from unittest.mock import patch

from pipeline import candidates


class CandidateNotificationTests(unittest.TestCase):
    def send(self):
        return candidates._skicka_kandidat(
            {"url": "https://example.test/annons", "arsmodell": 2024},
            {"diff": 25000}, 80)

    def test_frequent_mode_calls_email_sender(self):
        with patch.dict(os.environ, {"FISKABILAR_ONLY_DAILY_REPORT": "0"}), patch.object(candidates, "DEBUG", False), patch.object(candidates, "score_niva", return_value="⭐ Fynd"), patch.object(candidates, "formatera_notis", return_value="Ny fyndannons"), patch.object(candidates, "bil_rubrik", return_value="Volvo V60"), patch.object(candidates, "skicka_epost", return_value=True) as send:
            self.assertTrue(self.send())
            send.assert_called_once()
            self.assertEqual(send.call_args.args[1], "Ny fyndannons")
            self.assertIn("25 000 kr", send.call_args.args[0])

    def test_evening_mode_does_not_send_candidate_email(self):
        with patch.dict(os.environ, {"FISKABILAR_ONLY_DAILY_REPORT": "1"}), patch.object(candidates, "skicka_epost") as send:
            self.assertFalse(self.send())
            send.assert_not_called()

    def test_failed_delivery_does_not_report_success(self):
        with patch.dict(os.environ, {"FISKABILAR_ONLY_DAILY_REPORT": "0"}), patch.object(candidates, "DEBUG", False), patch.object(candidates, "score_niva", return_value="⭐ Fynd"), patch.object(candidates, "formatera_notis", return_value="Ny fyndannons"), patch.object(candidates, "bil_rubrik", return_value="Volvo V60"), patch.object(candidates, "skicka_epost", return_value=False):
            self.assertFalse(self.send())
