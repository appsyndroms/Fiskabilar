import unittest
from unittest.mock import patch

import requests

from scripts.check_source_connection import main
from sources.errors import SourceFetchError


class SourceConnectionTests(unittest.TestCase):
    def test_http_failure_cannot_report_success(self):
        with patch("scripts.check_source_connection.wayke._hamta_sida", side_effect=requests.HTTPError("403")):
            with self.assertRaises(requests.HTTPError):
                main()

    def test_empty_page_cannot_report_success(self):
        with patch("scripts.check_source_connection.wayke._hamta_sida", return_value="<html></html>"):
            with self.assertRaises(SourceFetchError):
                main()

    def test_real_cards_report_success(self):
        with patch("scripts.check_source_connection.wayke._hamta_sida", return_value="html"), patch("scripts.check_source_connection.wayke._extrahera_annonskort", return_value=[{"url": "test"}]), patch("builtins.print") as output:
            main()
            output.assert_called_once_with("Wayke OK: 1 tolkningsbara annonser på första sidan.")
