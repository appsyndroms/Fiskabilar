import unittest
from unittest.mock import call, patch

import requests
from urllib3.exceptions import ReadTimeoutError

from sources import bilweb_scraper
from sources.errors import SourceFetchError


URL = "https://example.test/car/123"


def response(status=200, html=None):
    result = requests.Response()
    result.status_code = status
    result.url = URL
    result.headers["Content-Type"] = "text/html"
    result._content = (html or "<html><p>Kontantpris 479 900 kr</p>"
                      "<p>Mätarställning</p><p>2 988 mil</p></html>").encode()
    return result


class BilwebRetryTests(unittest.TestCase):
    def test_timeout_waits_fifteen_seconds_before_one_successful_retry(self):
        errors = (requests.ReadTimeout("slow response"), requests.ConnectTimeout("slow connect"),
                  requests.ConnectionError(ReadTimeoutError(None, URL, "Read timed out")))
        for error in errors:
            with self.subTest(error=error), patch.object(bilweb_scraper.requests, "get", side_effect=[error, response()]) as get, patch.object(bilweb_scraper.time, "sleep") as sleep:
                events = []
                get.side_effect = lambda *a, **kw: self._request(events, error, a, kw)
                sleep.side_effect = lambda seconds: events.append(("wait", seconds))
                result = bilweb_scraper.hamta_pris_mil_fran_detaljsida(URL)
                self.assertEqual(result["pris"], 479900)
                self.assertEqual(result["miltal"], 2988)
                self.assertEqual(events, ["request", ("wait", 15), "request"])
                sleep.assert_called_once_with(15)
                self.assertEqual(get.call_args_list, [call(URL, headers=bilweb_scraper.HEADERS, timeout=15, allow_redirects=True)] * 2)

    @staticmethod
    def _request(events, error, args, kwargs):
        first = not events
        events.append("request")
        if first:
            raise error
        return response()

    def test_second_timeout_stops_collection(self):
        with patch.object(bilweb_scraper.requests, "get", side_effect=requests.Timeout("slow")) as get, patch.object(bilweb_scraper.time, "sleep") as sleep:
            with self.assertRaises(SourceFetchError):
                bilweb_scraper.hamta_pris_mil_fran_detaljsida(URL)
            self.assertEqual(get.call_count, 2)
            sleep.assert_called_once_with(15)

    def test_other_errors_are_never_retried(self):
        cases = [response(status) for status in (403, 404, 429, 500, 503)]
        cases += [requests.ConnectionError("connection reset"),
                  response(html="<html><title>Just a moment...</title></html>")]
        for error in cases:
            with self.subTest(error=error), patch.object(bilweb_scraper.requests, "get", side_effect=[error]) as get, patch.object(bilweb_scraper.time, "sleep") as sleep:
                with self.assertRaises(SourceFetchError):
                    bilweb_scraper.hamta_pris_mil_fran_detaljsida(URL)
                get.assert_called_once()
                sleep.assert_not_called()

    def test_successful_first_request_does_not_wait_or_retry(self):
        with patch.object(bilweb_scraper.requests, "get", return_value=response()) as get, patch.object(bilweb_scraper.time, "sleep") as sleep:
            self.assertEqual(bilweb_scraper.hamta_pris_mil_fran_detaljsida(URL)["pris"], 479900)
            get.assert_called_once()
            sleep.assert_not_called()
