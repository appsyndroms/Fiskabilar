"""Kontrollera Wayke med samma Python-kod som produktionen, utan dataskrivning.

HTTP-fel och svar utan tolkningsbara annonser ger felkod, aldrig grön status.
"""
from sources import wayke
from sources.errors import SourceFetchError


def main() -> None:
    html = wayke._hamta_sida("volvo", "v60", 2023)
    cards = wayke._extrahera_annonskort(html, wayke._bygg_annons_regex("Volvo V60"))
    if not cards:
        raise SourceFetchError("Wayke: söksidan saknar tolkningsbara annonskort.")
    print(f"Wayke OK: {len(cards)} tolkningsbara annonser på första sidan.")


if __name__ == "__main__":
    main()
