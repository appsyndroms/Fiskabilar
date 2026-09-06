from sources.bytbil import hamta_annonser


def main():

    annonser = hamta_annonser()

    print()
    print("=" * 60)
    print(f"ANTAL ANNONSER: {len(annonser)}")
    print("=" * 60)

    for index, bil in enumerate(
        annonser[:10],
        start=1,
    ):

        print()
        print(f"ANNONS {index}")

        for nyckel, varde in bil.items():
            print(f"{nyckel}: {varde}")


if __name__ == "__main__":
    main()
