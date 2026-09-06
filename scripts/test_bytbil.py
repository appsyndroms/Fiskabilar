from sources.bytbil import hamta_annonser


def main():
    print()
    print("=" * 70)
    print("TEST AV BYTBIL-SCRAPER")
    print("=" * 70)

    try:
        annonser = hamta_annonser()
    except Exception as e:
        print()
        print("FEL VID HÄMTNING AV ANNONSER")
        print(f"{type(e).__name__}: {e}")
        raise

    print()
    print("=" * 70)
    print(f"ANTAL MATCHADE ANNONSER: {len(annonser)}")
    print("=" * 70)

    if not annonser:
        print()
        print("INGA MATCHADE ANNONSER HITTADES.")
        print()
        return

    for i, bil in enumerate(annonser[:30], 1):
        print()
        print(f"ANNONS {i}")
        print("-" * 70)

        print(f"  Källa:      {bil.get('kalla')}")
        print(f"  Märke:      {bil.get('marke_slug')}")
        print(f"  Modell:     {bil.get('modell_slug')}")
        print(f"  Variant:    {bil.get('variant')}")
        print(f"  Årsmodell:  {bil.get('arsmodell')}")
        print(f"  Miltal:     {bil.get('miltal')}")
        print(f"  Pris:       {bil.get('annonspris')}")
        print(f"  Annons-ID:  {bil.get('annons_id')}")
        print(f"  URL:        {bil.get('url')}")

        # Extra diagnostik om fälten finns
        if "miltal_raw" in bil:
            print(f"  Miltal rådata: {bil.get('miltal_raw')}")

        if "arsmodell_raw" in bil:
            print(f"  Årsmodell rådata: {bil.get('arsmodell_raw')}")

        if "pris_raw" in bil:
            print(f"  Pris rådata: {bil.get('pris_raw')}")

    if len(annonser) > 30:
        print()
        print("=" * 70)
        print(f"VISAR 30 AV {len(annonser)} MATCHADE ANNONSER")
        print("=" * 70)


if __name__ == "__main__":
    main()
