import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
from history import notification_history as ledger
from history import state
from config import MIN_PRISSANKNING_FOR_NY_NOTIS


class NotificationHistoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        p = patch.object(ledger, "PATH", Path(self.tmp.name) / "notifications.json")
        p.start()
        self.addCleanup(p.stop)
        ledger.load.cache_clear()
        self.addCleanup(ledger.load.cache_clear)

    def car(self, identity="vehicle:old", price=400000):
        return {"vehicle_id": identity, "annonspris": price,
                "url": "https://www.wayke.se/objekt/car?tracking=1"}

    def test_id_change_does_not_repeat_email_and_history_survives_restart(self):
        ledger.record(self.car())
        ledger.load.cache_clear()
        car = self.car("vehicle:new")
        car["url"] = "https://www.wayke.se/objekt/car/"
        self.assertTrue(state.redan_notifierad(car, {}))

    def test_price_cut_can_notify_once_then_new_price_is_saved(self):
        ledger.record(self.car())
        lower = self.car("vehicle:new", 400000 - MIN_PRISSANKNING_FOR_NY_NOTIS)
        self.assertFalse(state.redan_notifierad(lower, {}))
        state.markera_notifierad(lower, {})
        self.assertTrue(state.redan_notifierad(lower, {}))
        self.assertTrue(state.redan_notifierad(self.car(price=lower["annonspris"]+5000), {}))

    def test_all_cross_source_links_share_notification(self):
        car = self.car()
        car["urls"] = ["https://bilweb.se/car/123"]
        ledger.record(car)
        self.assertTrue(state.redan_notifierad({"vehicle_id":"new", "url":"https://bilweb.se/car/123", "annonspris":400000}, {}))

    def test_different_car_is_not_blocked(self):
        ledger.record(self.car())
        other = self.car("vehicle:other")
        other["url"] = "https://www.wayke.se/objekt/other"
        self.assertFalse(state.redan_notifierad(other, {}))

    def test_corrupt_history_is_not_silently_reset(self):
        ledger.PATH.write_text("broken json")
        with self.assertRaises(ValueError):
            state.redan_notifierad(self.car(), {})
