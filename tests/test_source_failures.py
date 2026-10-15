import unittest
from unittest.mock import patch

import requests

from config import BILAR
from main import main
from pipeline import fetching
from sources import bilweb, bilweb_scraper, bytbil, wayke, blocket
from sources.errors import SourceFetchError


def response(status, text="<html>example</html>"):
    value = requests.Response()
    value.status_code = status
    value.url = "https://example.test/car/123"
    value._content = text.encode()
    value.headers["Content-Type"] = "text/html"
    return value


class SourceFailureTests(unittest.TestCase):
    def test_http_errors_propagate_from_every_source_and_detail_worker(self):
        callers = [lambda: wayke.hamta_annonser(),
                   lambda: bilweb._hamta_kandidat_urler(BILAR[0], 2023),
                   lambda: bytbil._hamta_sida("https://example.test/search"),
                   lambda: bilweb_scraper.hamta_pris_mil_fran_detaljsida("https://example.test/car/123"),
                   lambda: blocket.hamta_annonser()]
        for status in (403, 404, 429, 500, 503):
            for caller in callers:
                with self.subTest(status=status, caller=caller), patch("requests.get", return_value=response(status)):
                    with self.assertRaises(SourceFetchError) as error:
                        caller()
                    self.assertIn(str(status), str(error.exception))

    def test_timeouts_propagate_from_every_active_source(self):
        callers = [wayke.hamta_annonser,
                   lambda: bilweb._hamta_kandidat_urler(BILAR[0], 2023),
                   lambda: bytbil._hamta_sida("https://example.test/search"),
                   lambda: bilweb_scraper.hamta_pris_mil_fran_detaljsida("https://example.test/car/123")]
        for caller in callers:
            with patch("requests.get", side_effect=requests.Timeout("Timeout")):
                with self.assertRaises(SourceFetchError):
                    caller()

    def test_http_200_challenge_is_not_an_empty_search(self):
        with patch("requests.get", return_value=response(200, "<html><title>Just a moment...</title></html>")):
            with self.assertRaises(SourceFetchError):
                wayke.hamta_annonser()

    def test_parallel_detail_failure_is_not_ignored(self):
        url = "https://example.test/car/123"
        with patch.object(bilweb_scraper, "hamta_pris_mil_fran_detaljsida", side_effect=SourceFetchError("403")):
            with self.assertRaises(SourceFetchError):
                bilweb_scraper.hamta_detaljsidor_parallellt([{"url": url}], {})

    def test_one_failed_source_preserves_state_even_after_another_succeeds(self):
        with patch.object(fetching.wayke, "hamta_annonser", return_value=[{"url": "test"}]), patch.object(fetching.bilweb, "hamta_annonser", side_effect=SourceFetchError("403")), patch("main.ladda_state") as state, patch("main.spara_annonsobservation") as save, patch("main.spara_state") as save_state:
            with self.assertRaises(SourceFetchError):
                main(evening=True)
            state.assert_not_called()
            save.assert_not_called()
            save_state.assert_not_called()

    def test_unknown_source_cannot_silently_drop_from_collection(self):
        with self.assertRaises(SourceFetchError):
            fetching.hamta_alla_annonser(["unknown"])


if __name__ == "__main__":
    unittest.main()
