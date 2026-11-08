import unittest
from unittest.mock import patch
from scripts.check_source_connection import main
from sources.errors import SourceFetchError


class SourceConnectionTests(unittest.TestCase):
    def test_failure_cannot_report_success(self):
        with patch("scripts.check_source_connection.fetch_page", side_effect=SourceFetchError("403")):
            with self.assertRaises(SourceFetchError):
                main()

    def test_empty_page_cannot_report_success(self):
        with patch("scripts.check_source_connection.fetch_page", return_value={"hits": [], "found": 0}):
            with self.assertRaises(SourceFetchError):
                main()

    def test_real_cards_report_success(self):
        with patch("scripts.check_source_connection.fetch_page", return_value={"hits": [{}], "found": 1}), patch("scripts.check_source_connection.parse_hit", return_value={"url": "test"}), patch("builtins.print") as output:
            main()
            self.assertEqual(output.call_count, 4)
