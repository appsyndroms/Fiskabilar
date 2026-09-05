"""
Analyserar vad som hände med tidigare fynd.

Verktyget används manuellt från debug-workflowen.

Det försöker identifiera:

- aktiva fynd
- prissänkta fynd
- försvunna annonser
- fynd som försvann efter prissänkning
- tid till första prissänkning
- total prissänkning
- tid till försvinnande

Resultatet används som underlag för framtida
förbättring av score och marknadsvärdering.

Scriptet ändrar inte historiken.
"""

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


TIDSZON = ZoneInfo("Europe/Stockholm")

FEEDBACK_DIR = Path(
    "data/find_feedback"
)

MARKET_DIR = Path(
    "data/market_history"
)


def _las_jsonl(
    katalog: Path,
) -> list[dict]:
    poster = []

    if not katalog.exists():
        return poster

    for fil in sorted(
        katalog.glob("*.jsonl")
    ):
        with fil.open(
            encoding="utf-8"
        ) as f:
            for rad in f:
                rad = rad.strip()

                if not rad:
                    continue

                try:
                    poster.append(
                        json.loads(rad)
                    )
                except json.JSONDecodeError:
                    continue

    return poster


def _parse_tid(
    tid: str,
):
    if not tid:
        return None

    try:
        return datetime.fromisoformat(
            tid
        )
    except ValueError:
        return None


def _bygg_marknadshistorik() -> dict:
    """
    Bygger index:

        vehicle_id -> observationer

    Endast riktiga annonsobservationer används.
    """

    index = {}

    poster = _las_jsonl(
        MARKET_DIR
    )

    for post in poster:
        if post.get("typ") != "annons":
            continue

        vehicle_id = post.get(
            "vehicle_id"
        )

        if not vehicle_id:
            continue

        tid = _parse_tid(
            post.get(
                "tid",
                "",
            )
        )

        if tid is None:
            continue

        pris = post.get(
            "pris"
        )

        if not isinstance(
            pris,
            (int, float),
        ):
            continue

        if isinstance(
            pris,
            bool,
        ):
            continue

        index.setdefault(
            vehicle_id,
            [],
        ).append(
            {
                "tid": tid,
                "pris": pris,
                "annons_id": post.get(
                    "annons_id"
                ),
            }
        )

    for observationer in index.values():
        observationer.sort(
            key=lambda x: x["tid"]
        )

    return index


def _analysera_fynd(
    fynd: dict,
    observationer: list[dict],
) -> dict:
    fynd_tid = _parse_tid(
        fynd.get(
            "tid",
            "",
        )
    )

    initialpris = fynd.get(
        "pris"
    )

    if (
        fynd_tid is None
        or not isinstance(
            initialpris,
            (int, float),
        )
    ):
        return {
            **fynd,
            "utfall": "OKÄNT",
        }

    senare = [
        obs
        for obs in observationer
        if obs["tid"] >= fynd_tid
    ]

    if not senare:
        return {
            **fynd,
            "utfall": "INGEN_DATA",
        }

    prisfall = [
        obs
        for obs in senare
        if obs["pris"] < initialpris
    ]

    forsvunnen = False
    sista_observation = senare[-1]

    # Om annonsen inte längre observeras kan vi
    # inte säkert säga att bilen såldes.
    #
    # Därför använder vi "FÖRSVUNNEN" och inte
    # "SÅLD".
    #
    # En senare implementation kan använda
    # lifecycle-information för bättre klassificering.

    if prisfall:
        forsta_prisfall = prisfall[0]

        dagar_till_prisfall = (
            forsta_prisfall["tid"]
            - fynd_tid
        ).total_seconds() / 86400

        slutpris = min(
            obs["pris"]
            for obs in senare
        )

        total_prisfall = (
            initialpris
            - slutpris
        )

        return {
            **fynd,
            "utfall": "PRISSÄNKT",
            "dagar_till_prissankning":
                round(
                    dagar_till_prisfall,
                    2,
                ),
            "slutpris": slutpris,
            "total_prissankning":
                total_prisfall,
            "procent_prissankning":
                round(
                    (
                        total_prisfall
                        / initialpris
                    ) * 100,
                    2,
                ),
            "senaste_observation":
                sista_observation["tid"].isoformat(),
        }

    return {
        **fynd,
        "utfall": "AKTIV",
        "senaste_observation":
            sista_observation["tid"].isoformat(),
    }


def main():
    fynd = _las_jsonl(
        FEEDBACK_DIR
    )

    fynd = [
        post
        for post in fynd
        if post.get("typ") == "fynd"
    ]

    if not fynd:
        print(
            "Inga fyndobservationer hittades."
        )
        return

    marknad = (
        _bygg_marknadshistorik()
    )

    resultat = []

    for post in fynd:
        vehicle_id = post.get(
            "vehicle_id"
        )

        observationer = (
            marknad.get(
                vehicle_id,
                [],
            )
        )

        resultat.append(
            _analysera_fynd(
                post,
                observationer,
            )
        )

    antal = len(resultat)

    aktiva = sum(
        1
        for post in resultat
        if post["utfall"] == "AKTIV"
    )

    prissankta = sum(
        1
        for post in resultat
        if post["utfall"] == "PRISSÄNKT"
    )

    ingen_data = sum(
        1
        for post in resultat
        if post["utfall"] == "INGEN_DATA"
    )

    okanda = sum(
        1
        for post in resultat
        if post["utfall"] == "OKÄNT"
    )

    print()
    print(
        "============================================================"
    )
    print(
        " ANALYS AV FAKTISKA FYNDUTFALL"
    )
    print(
        "============================================================"
    )
    print()

    print(
        f"Antal fyndobservationer: {antal}"
    )

    print(
        f"Aktiva: {aktiva}"
    )

    print(
        f"Prissänkta: {prissankta}"
    )

    print(
        f"Ingen efterföljande data: {ingen_data}"
    )

    print(
        f"Okända: {okanda}"
    )

    print()

    print(
        "------------------------------------------------------------"
    )
    print(
        " FYND"
    )
    print(
        "------------------------------------------------------------"
    )

    for post in sorted(
        resultat,
        key=lambda x: (
            x.get("score", 0),
            x.get("diff", 0),
        ),
        reverse=True,
    ):
        print(
            f"{post.get('utfall'):12} | "
            f"score {post.get('score', 0):3} | "
            f"{post.get('arsmodell', '?')} | "
            f"{post.get('miltal', 0):>6} mil | "
            f"{post.get('pris', 0):>9,} kr | "
            f"diff {post.get('diff', 0):>8,} | "
            f"{post.get('modell', '')}"
        )

    print()

    prissankningar = [
        post
        for post in resultat
        if post["utfall"]
        == "PRISSÄNKT"
    ]

    if prissankningar:
        print(
            "------------------------------------------------------------"
        )
        print(
            " PRISSÄNKNINGAR"
        )
        print(
            "------------------------------------------------------------"
        )

        for post in sorted(
            prissankningar,
            key=lambda x:
                x.get(
                    "dagar_till_prissankning",
                    9999,
                ),
        ):
            print(
                f"score {post.get('score', 0):3} | "
                f"diff {post.get('diff', 0):>8,} | "
                f"första sänkning "
                f"{post.get('dagar_till_prissankning')} dagar | "
                f"total sänkning "
                f"{post.get('total_prissankning', 0):,} kr | "
                f"{post.get('modell', '')}"
            )

        print()

    print(
        "============================================================"
    )


if __name__ == "__main__":
    main()
