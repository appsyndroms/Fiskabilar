"""Kontrollera publika Wayke-API:et utan dataskrivning eller API-nycklar."""
from config import BILAR
from sources.wayke_public import fetch_page, parse_hit
from sources.errors import SourceFetchError


def main():
    for config in BILAR:
        year = config["arsmodell_min"]
        result = fetch_page(config, year, 1)
        if not result["hits"]:
            raise SourceFetchError(f"Wayke: inga kontrollannonser för {config['modell_visning']}.")
        cards = [parse_hit(hit, config, year) for hit in result["hits"]]
        print(f"Wayke API OK: {config['modell_visning']} {year}: {result['found']} träffar, {len(cards)} validerade på första sidan.", flush=True)


if __name__ == "__main__":
    main()
