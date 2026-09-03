import json
from datetime import datetime
from zoneinfo import ZoneInfo

TIDSZON = ZoneInfo("Europe/Stockholm")

idag = datetime.now(TIDSZON).date().isoformat()

fil = f"data/market_history/market_history_{idag[:7]}.jsonl"

antal = 0
extrema = []
misstankta = []

with open(fil, encoding="utf-8") as f:
    for rad in f:
        rad = rad.strip()

        if not rad:
            continue

        post = json.loads(rad)

        if post.get("typ") != "annons":
            continue

        tid = post.get("tid", "")

        if not tid.startswith(idag):
            continue

        antal += 1

        pris = post.get("pris")

        if not isinstance(pris, (int, float)):
            continue

        if isinstance(pris, bool):
            continue

        if pris >= 1_000_000:
            extrema.append(post)

        # Letar efter typiska x100-fel.
        #
        # Exempel:
        # 21429900 istället för 214299
        # 17419900 istället för 174199
        if (
            pris >= 10_000_000
            and pris % 100 == 0
        ):
            misstankta.append(post)


print()
print("========================================")
print(" VERIFIERING AV DAGENS HISTORIK")
print("========================================")
print()

print(f"Datum: {idag}")
print(f"Fil: {fil}")
print()

print(
    "[VERIFIERING] "
    f"Dagens annonsobservationer: {antal}"
)

print(
    "[VERIFIERING] "
    f"Priser >= 1 000 000 kr: {len(extrema)}"
)

print(
    "[VERIFIERING] "
    f"Misstänkta x100-priser: {len(misstankta)}"
)

print()

if extrema:
    print("----------------------------------------")
    print("Priser >= 1 000 000 kr")
    print("----------------------------------------")

    for post in extrema:
        print(
            f"annons_id={post.get('annons_id')} "
            f"modell={post.get('modell')} "
            f"variant={post.get('variant')} "
            f"pris={post.get('pris')} "
            f"miltal={post.get('miltal')} "
            f"vehicle_id={post.get('vehicle_id')}"
        )

    print()

if misstankta:
    print("----------------------------------------")
    print("MISSTÄNKTA x100-PRISER")
    print("----------------------------------------")

    for post in misstankta:
        print(
            f"annons_id={post.get('annons_id')} "
            f"modell={post.get('modell')} "
            f"variant={post.get('variant')} "
            f"pris={post.get('pris')} "
            f"miltal={post.get('miltal')} "
            f"vehicle_id={post.get('vehicle_id')}"
        )

    print()

if not misstankta:
    print(
        "[RESULTAT] "
        "Inga misstänkta x100-priser hittades idag."
    )
else:
    print(
        "[RESULTAT] "
        "MISSTÄNKTA x100-PRISER HITTADES!"
    )

print()
