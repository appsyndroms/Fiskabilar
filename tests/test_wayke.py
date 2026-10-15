import unittest
from unittest.mock import patch

from sources import wayke


def card(identity, title="Volvo V60 Recharge T6 AWD Plus", price="399 900", year_label="Årsmodell"):
    return f"""<article aria-describedby="subtitle-{identity}">
      <div><dl><dt>Plats:</dt><dd>Teststad</dd><dt>Återförsäljare:</dt><dd>Testbil</dd></dl>
        <h2><a href="/objekt/{identity}" title="{title}">Volvo V60</a></h2>
        <div id="subtitle-{identity}">Recharge T6 AWD Plus</div>
        <dl><dt>{year_label}:</dt><dd>2023</dd><dt>Mätarställning:</dt><dd>6 500 mil</dd>
        <dt>Växellåda:</dt><dd>Automat</dd><dt>Bränsle:</dt><dd>Bensin+El</dd></dl>
      </div><footer><dl><dt>Kontantpris</dt><dd>{price} kr</dd></dl></footer>
    </article>"""


class WaykeTests(unittest.TestCase):
    regex = wayke._bygg_annons_regex("Volvo V60")

    def test_title_variant_footer_price_and_fields_stay_with_their_car(self):
        html = card("aaaa", price="399 900") + card("bbbb", title="Volvo V60 T8 AWD", price="459 000")
        parsed = wayke._extrahera_annonskort(html, self.regex)
        self.assertEqual(len(parsed), 2)
        self.assertEqual([p["pris"] for p in parsed], [399900, 459000])
        self.assertIn("T6", parsed[0]["titel"])
        self.assertIn("T8", parsed[1]["titel"])
        self.assertEqual(parsed[0]["dealer"], "Testbil")
        self.assertEqual(parsed[0]["gearbox"], "Automat")
        self.assertEqual(parsed[0]["miltal"], 6500)
        self.assertEqual(parsed[0]["arsmodell"], 2023)

    def test_missing_anchor_title_uses_accessible_card_description(self):
        html = card("aaaa").replace(' title="Volvo V60 Recharge T6 AWD Plus"', "")
        self.assertIn("T6", wayke._extrahera_annonskort(html, self.regex)[0]["titel"])

    def test_english_year_label_is_still_supported(self):
        parsed = wayke._extrahera_annonskort(card("aaaa", year_label="Model Year"), self.regex)
        self.assertEqual(parsed[0]["arsmodell"], 2023)

    def test_pagination_follows_next_link_and_deduplicates_overlap(self):
        next_link = '<a data-testid="search-pagination-next" href="/sok/volvo/v60/2023?page=2">Nästa sida</a>'
        with patch.object(wayke, "_hamta_sida", side_effect=[card("aaaa") + next_link, card("aaaa") + card("bbbb")]) as fetch, patch.object(wayke.time, "sleep"):
            parsed = wayke._hamta_annonskort("volvo", "v60", 2023, self.regex)
        self.assertEqual(len(parsed), 2)
        self.assertEqual(fetch.call_args_list[1].kwargs["page"], 2)

    def test_repeated_page_is_rejected(self):
        next_link = '<a data-testid="search-pagination-next" href="/sok/volvo/v60/2023?page=2">Nästa sida</a>'
        with patch.object(wayke, "_hamta_sida", side_effect=[card("aaaa") + next_link, card("aaaa")]), patch.object(wayke.time, "sleep"):
            with self.assertRaisesRegex(RuntimeError, "upprepade"):
                wayke._hamta_annonskort("volvo", "v60", 2023, self.regex)

    def test_pagination_cannot_change_model(self):
        next_link = '<a data-testid="search-pagination-next" href="/sok/bmw/330e/2023?page=2">Nästa sida</a>'
        with patch.object(wayke, "_hamta_sida", return_value=card("aaaa") + next_link):
            with self.assertRaisesRegex(RuntimeError, "ogiltig"):
                wayke._hamta_annonskort("volvo", "v60", 2023, self.regex)


if __name__ == "__main__":
    unittest.main()
