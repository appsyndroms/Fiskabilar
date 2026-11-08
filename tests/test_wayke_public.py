import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import requests
from config import BILAR
from sources import wayke_public as api
from sources.errors import SourceFetchError


class PublicWaykeTests(unittest.TestCase):
    def setUp(self):
        self.hit = json.loads((Path(__file__).parent / "fixtures/wayke_public_hit.json").read_text())

    def test_fields_and_units_match_real_api_response(self):
        card = api.parse_hit(self.hit, BILAR[0], 2023)
        self.assertEqual(card["pris"], 349800)
        self.assertEqual(card["miltal"], 8273)
        self.assertEqual(card["gearbox"], "Automat")
        self.assertEqual(card["fuel"], "Bensin+El")
        self.assertTrue(card["url"].endswith(self.hit["ad"]["id"]))
        reading = self.hit["iteration"]["logistics"]["odometerReading"]
        reading.update(unit="KILOMETER", value=82730)
        self.assertEqual(api.parse_hit(self.hit, BILAR[0], 2023)["miltal"], 8273)

    def test_filters_keep_bmw_model_and_swedish_market(self):
        variables = api.variables(BILAR[3], 2024, 2)
        self.assertEqual(variables["model"], ["330e xDrive Touring"])
        self.assertEqual(variables["market"], ["SE"])
        self.assertEqual(variables["page"], 2)
        self.assertEqual(variables["modelYearMax"], 2024)

    def test_sold_and_unpublished_ads_are_excluded(self):
        for changes in ({"soldAt": "2026-11-08"}, {"status": "DRAFT"}, {"inventoryStatus": "Sold"}):
            hit = copy.deepcopy(self.hit)
            hit["ad"]["channels"][0].update(changes)
            self.assertIsNone(api.parse_hit(hit, BILAR[0], 2023))

    def test_schema_and_filter_changes_fail(self):
        for mutate in (lambda h: h["iteration"]["item"]["modelYear"].update(intValue=2024),
                       lambda h: h["iteration"]["item"]["modelSeries"].update(stringValue="V90"),
                       lambda h: h["iteration"]["logistics"]["odometerReading"].update(unit="UNKNOWN"),
                       lambda h: h["ad"]["pricing"]["cash"]["price"].update(amount="nan")):
            hit = copy.deepcopy(self.hit)
            mutate(hit)
            with self.assertRaises(SourceFetchError):
                api.parse_hit(hit, BILAR[0], 2023)

    def test_http_json_and_graphql_failures_are_not_empty_successes(self):
        for status, text, content_type in [(403, "blocked", "text/html"), (429, "rate limited", "text/html"),
                (503, "unavailable", "text/html"), (200, "<html>challenge</html>", "text/html"),
                (200, '{"errors":[{"message":"error"}],"data":{"search":{"ads":null}}}', "application/json"),
                (200, '{"data":{}}', "application/json"), (200, "not json", "application/json")]:
            response = requests.Response()
            response.status_code = status
            response._content = text.encode()
            response.headers["Content-Type"] = content_type
            with self.subTest(status=status, text=text), patch.object(api.requests, "post", return_value=response):
                with self.assertRaises((SourceFetchError, requests.RequestException)):
                    api.fetch_page(BILAR[0], 2023, 1)

    def test_all_pages_are_required_and_duplicates_stop_collection(self):
        first = {"found": 2, "hits": [self.hit]}
        second_hit = copy.deepcopy(self.hit)
        second_hit["ad"]["id"] = "00000000-0000-4000-8000-000000000001"
        with patch.object(api, "fetch_page", side_effect=[first, {"found": 2, "hits": [second_hit]}]), patch.object(api.time, "sleep"):
            self.assertEqual(len(api.hamta_annonskort(BILAR[0], 2023)), 2)
        for second in ({"found": 2, "hits": []}, first, {"found": 3, "hits": [second_hit]}):
            with patch.object(api, "fetch_page", side_effect=[first, second]), patch.object(api.time, "sleep"):
                with self.assertRaises(SourceFetchError):
                    api.hamta_annonskort(BILAR[0], 2023)
