"""
Analyserar vad som hände med tidigare fynd.
Verktyget används manuellt från debug-workflowen.
Det kopplar ihop fyndögonblicket med den efterföljande
marknadshistoriken för samma vehicle_id.

Analysen identifierar:
- aktiva fynd
- prissänkta fynd
- försvunna annonser
- fynd som försvann efter prissänkning
- tid till första prissänkning
- total prissänkning
- tid till försvinnande
- snabba försvinnanden
- score mot faktiskt utfall
- prisdiff mot faktiskt utfall

Flera feedbackobservationer för samma bil under samma
sammanhängande fyndperiod räknas som ett enda fynd-event.

Resultatet används som underlag för framtida
förbättring av score och marknadsvärdering.

Scriptet ändrar inte den ursprungliga marknadshistoriken
eller feedbackhistoriken.
"""

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


TIDSZON = ZoneInfo(
    "Europe/Stockholm"
)

FEEDBACK_DIR = Path(
    "data/find_feedback"
)

MARKET_DIR = Path(
    "data/market_history"
)

RESULTAT_DIR = Path(
    "data/find_feedback"
)

# Samma grundprincip som lifecycle.py använder.
# Vi kräver att bilen observerats inom två dagar
# för att kalla den aktiv.
AKTIVITETSDAGAR = 2

# Ett fynd som försvinner inom detta antal dagar
# klassas som ett snabbt försvinnande.
SNABBT_UTFALL_DAGAR = 7


def _las_jsonl(
    katalog: Path,
) -> list[dict]:
    """
    Läser alla JSONL-filer i en katalog.

    Trasiga rader ignoreras så att en enskild
    korrupt post inte stoppar hela analysen.
    """
    poster = []

    if not katalog.exists():
        return poster

    for fil in sorted(
        katalog.glob("*.jsonl")
    ):
        try:
            with fil.open(
                encoding="utf-8"
            ) as f:
                for rad in f:
                    rad = rad.strip()

                    if not rad:
                        continue

                    try:
                        post = json.loads(
                            rad
                        )
                    except json.JSONDecodeError:
                        continue

                    if isinstance(
                        post,
                        dict,
                    ):
                        poster.append(
                            post
                        )

        except OSError:
            continue

    return poster


def _parse_tid(
    tid,
) -> datetime | None:
    """
    Tolkar en ISO-tidsstämpel.

    Äldre poster utan tidszon behandlas
    som Europe/Stockholm.
    """
    if not tid:
        return None

    try:
        dt = datetime.fromisoformat(
            tid
        )
    except (
        TypeError,
        ValueError,
    ):
        return None

    if dt.tzinfo is None:
        dt = dt.replace(
            tzinfo=TIDSZON
        )

    return dt


def _numeriskt_pris(
    pris,
) -> bool:
    """
    Kontrollerar om ett värde är numeriskt.
    """
    return (
        isinstance(
            pris,
            (int, float),
        )
        and not isinstance(
            pris,
            bool,
        )
    )


def _bygg_marknadshistorik() -> dict:
    """
    Bygger ett index:

        vehicle_id -> observationer

    Endast riktiga annonsobservationer används.

    Varje observation innehåller:
    - tid
    - pris
    - annons_id
    """
    index = {}

    poster = _las_jsonl(
        MARKET_DIR
    )

    for post in poster:
        if post.get(
            "typ"
        ) != "annons":
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

        if not _numeriskt_pris(
            pris
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
            key=lambda obs: obs["tid"]
        )

    return index


def _gruppera_fynd_till_event(
    fynd: list[dict],
) -> list[dict]:
    """
    Grupperar återkommande fyndobservationer
    till sammanhängande fynd-event.

    Feedbackhistoriken innehåller medvetet flera
    observationer av samma bil. Exempelvis kan en bil
    som är ett fynd finnas kvar i flera körningar:

        NY
        AKTIV
        AKTIV
        AKTIV

    Dessa ska analyseras som ETT fynd-event.

    Ett nytt event startas när:
    - det är första fyndobservationen för bilen
    - bilen har status ÅTERKOMMEN
    - bilen har status NY efter ett tidigare event

    Övriga observationer tillhör det senaste
    pågående fynd-eventet.

    Funktionen ändrar inte originalposterna i
    feedbackhistoriken. Den returnerar endast den första
    observationen i varje fynd-event, eftersom det är den
    som representerar det faktiska fyndögonblicket.
    """
    grupper = {}

    for post in fynd:
        vehicle_id = post.get(
            "vehicle_id"
        )

        if not vehicle_id:
            continue

        grupper.setdefault(
            vehicle_id,
            [],
        ).append(
            post
        )

    resultat = []

    for vehicle_id, poster in grupper.items():
        poster.sort(
            key=lambda post: (
                _parse_tid(
                    post.get(
                        "tid",
                        "",
                    )
                )
                or datetime.min.replace(
                    tzinfo=TIDSZON
                )
            )
        )

        aktuellt_event = None

        for post in poster:
            status = post.get(
                "livscykelstatus"
            )

            if aktuellt_event is None:
                aktuellt_event = post
                continue

            if status in (
                "ÅTERKOMMEN",
                "NY",
            ):
                resultat.append(
                    aktuellt_event
                )

                aktuellt_event = post

        if aktuellt_event is not None:
            resultat.append(
                aktuellt_event
            )

    resultat.sort(
        key=lambda post: (
            _parse_tid(
                post.get(
                    "tid",
                    "",
                )
            )
            or datetime.min.replace(
                tzinfo=TIDSZON
            )
        )
    )

    return resultat


def _prisforandringar(
    observationer: list[dict],
) -> list[dict]:
    """
    Identifierar faktiska prisförändringar
    mellan konsekutiva observationer.
    """
    resultat = []

    tidigare = None

    for observation in observationer:
        pris = observation.get(
            "pris"
        )

        if not _numeriskt_pris(
            pris
        ):
            continue

        if tidigare is not None:
            tidigare_pris = tidigare[
                "pris"
            ]

            if pris != tidigare_pris:
                resultat.append(
                    {
                        "tid": observation[
                            "tid"
                        ].isoformat(),
                        "gammalt_pris": (
                            tidigare_pris
                        ),
                        "nytt_pris": (
                            pris
                        ),
                        "forandring": (
                            pris
                            - tidigare_pris
                        ),
                    }
                )

        tidigare = {
            "pris": pris,
            "tid": observation[
                "tid"
            ],
        }

    return resultat


def _senaste_observation(
    observationer: list[dict],
):
    if not observationer:
        return None

    return observationer[-1]


def _forsta_prissankning(
    observationer: list[dict],
    fynd_tid: datetime,
    initialpris: float,
):
    """
    Hittar första observation efter fyndet
    där priset är lägre än priset vid fyndet.

    Vi jämför mot priset vid fyndet, inte bara
    föregående observation, eftersom vi vill mäta
    den totala utvecklingen från fyndögonblicket.
    """
    for observation in observationer:
        if observation["tid"] <= fynd_tid:
            continue

        if observation["pris"] < initialpris:
            return observation

    return None


def _analysera_fynd(
    fynd: dict,
    observationer: list[dict],
) -> dict:
    """
    Analyserar ett enskilt fynd-event mot
    efterföljande marknadshistorik.
    """
    fynd_tid = _parse_tid(
        fynd.get(
            "tid",
            "",
        )
    )

    initialpris = fynd.get(
        "pris"
    )

    vehicle_id = fynd.get(
        "vehicle_id"
    )

    if (
        fynd_tid is None
        or not _numeriskt_pris(
            initialpris
        )
        or not vehicle_id
    ):
        return {
            **fynd,
            "utfall": "OKÄNT",
        }

    senare = [
        observation
        for observation in observationer
        if observation["tid"] > fynd_tid
    ]

    if not senare:
        return {
            **fynd,
            "utfall": "INGEN_DATA",
            "dagar_efter_fynd": 0,
        }

    nu = datetime.now(
        TIDSZON
    )

    senaste = _senaste_observation(
        senare
    )

    senaste_tid = senaste[
        "tid"
    ]

    dagar_sedan_senaste = (
        nu - senaste_tid
    ).total_seconds() / 86400

    dagar_efter_fynd = (
        senaste_tid - fynd_tid
    ).total_seconds() / 86400

    forsta_prissankning = (
        _forsta_prissankning(
            senare,
            fynd_tid,
            initialpris,
        )
    )

    minpris = min(
        observation["pris"]
        for observation in senare
    )

    total_prissankning = max(
        0,
        initialpris - minpris,
    )

    procent_prissankning = 0

    if initialpris > 0:
        procent_prissankning = (
            total_prissankning
            / initialpris
            * 100
        )

    aktiv = (
        dagar_sedan_senaste
        <= AKTIVITETSDAGAR
    )

    if forsta_prissankning is not None:
        dagar_till_prissankning = (
            forsta_prissankning["tid"]
            - fynd_tid
        ).total_seconds() / 86400

    else:
        dagar_till_prissankning = None

    if aktiv:
        if forsta_prissankning is not None:
            utfall = "PRISSÄNKT"
        else:
            utfall = "AKTIV"

        dagar_till_forvinnande = None

    else:
        if forsta_prissankning is not None:
            utfall = (
                "FÖRSVUNNEN_EFTER_PRISSÄNKNING"
            )
        else:
            utfall = "FÖRSVUNNEN"

        # Försvinnandet mäts från fyndet
        # till den sista säkra observationen.
        dagar_till_forvinnande = (
            senaste_tid - fynd_tid
        ).total_seconds() / 86400

    snabbt_forvinnande = (
        not aktiv
        and dagar_till_forvinnande is not None
        and dagar_till_forvinnande
        <= SNABBT_UTFALL_DAGAR
    )

    return {
        **fynd,
        "utfall": utfall,
        "dagar_efter_fynd": round(
            dagar_efter_fynd,
            2,
        ),
        "senaste_observation": (
            senaste_tid.isoformat()
        ),
        "dagar_sedan_senaste_observation": round(
            dagar_sedan_senaste,
            2,
        ),
        "forsta_prissankning": (
            forsta_prissankning["tid"].isoformat()
            if forsta_prissankning
            else None
        ),
        "dagar_till_prissankning": (
            round(
                dagar_till_prissankning,
                2,
            )
            if dagar_till_prissankning is not None
            else None
        ),
        "initialpris": initialpris,
        "lagsta_pris": minpris,
        "total_prissankning": total_prissankning,
        "procent_prissankning": round(
            procent_prissankning,
            2,
        ),
        "dagar_till_forvinnande": (
            round(
                dagar_till_forvinnande,
                2,
            )
            if dagar_till_forvinnande is not None
            else None
        ),
        "snabbt_forvinnande": snabbt_forvinnande,
    }


def _scoreintervall(
    score,
) -> str:
    """
    Grupperar score för jämförelser.
    """
    if not _numeriskt_pris(
        score
    ):
        return "OKÄNT"

    if score < 70:
        return "60-69"

    if score < 80:
        return "70-79"

    if score < 90:
        return "80-89"

    return "90+"


def _skriv_resultatfil(
    resultat: list[dict],
) -> Path:
    """
    Skriver om aktuell månads analysrapport.

    Rapporten är en härledd produkt och kan därför
    byggas om från historiken utan att originaldata
    ändras.
    """
    idag = datetime.now(
        TIDSZON
    ).date().isoformat()

    fil = (
        RESULTAT_DIR
        / f"find_outcomes_{idag[:7]}.jsonl"
    )

    RESULTAT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    with fil.open(
        "w",
        encoding="utf-8",
    ) as f:
        for post in resultat:
            f.write(
                json.dumps(
                    post,
                    ensure_ascii=False,
                )
                + "\n"
            )

    return fil


def _skriv_scoreanalys(
    resultat: list[dict],
) -> None:
    """
    Skriver en enkel score -> utfall-analys.

    Detta är diagnostik, inte ännu en ändring
    av score-viktningen.
    """
    grupper = {}

    for post in resultat:
        utfall = post.get(
            "utfall"
        )

        if utfall in (
            "INGEN_DATA",
            "OKÄNT",
        ):
            continue

        intervall = _scoreintervall(
            post.get(
                "score"
            )
        )

        grupper.setdefault(
            intervall,
            {},
        )

        grupper[
            intervall
        ][
            utfall
        ] = (
            grupper[
                intervall
            ].get(
                utfall,
                0,
            )
            + 1
        )

    if not grupper:
        return

    print()
    print(
        "------------------------------------------------------------"
    )
    print(
        " SCORE MOT UTFALL"
    )
    print(
        "------------------------------------------------------------"
    )

    ordning = [
        "60-69",
        "70-79",
        "80-89",
        "90+",
    ]

    utfall_ordning = [
        "AKTIV",
        "PRISSÄNKT",
        "FÖRSVUNNEN",
        "FÖRSVUNNEN_EFTER_PRISSÄNKNING",
    ]

    for intervall in ordning:
        if intervall not in grupper:
            continue

        data = grupper[
            intervall
        ]

        print()
        print(
            f"Score {intervall}:"
        )

        for utfall in utfall_ordning:
            antal = data.get(
                utfall,
                0,
            )

            if antal:
                print(
                    f"  {utfall}: "
                    f"{antal}"
                )


def main():
    fynd = _las_jsonl(
        FEEDBACK_DIR
    )

    fynd = [
        post
        for post in fynd
        if post.get(
            "typ"
        ) == "fynd"
    ]

    if not fynd:
        print(
            "Inga fyndobservationer hittades."
        )
        return

    # Feedbackhistoriken innehåller flera observationer
    # av samma fynd när bilen ligger kvar som kandidat.
    #
    # Vi ska INTE ta bort dessa poster ur historiken.
    # I stället grupperar vi dem till sammanhängande
    # fynd-event för själva utfallsanalysen.
    fynd = _gruppera_fynd_till_event(
        fynd
    )

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

    antal = len(
        resultat
    )

    aktiva = sum(
        1
        for post in resultat
        if post.get(
            "utfall"
        ) == "AKTIV"
    )

    prissankta = sum(
        1
        for post in resultat
        if post.get(
            "utfall"
        ) == "PRISSÄNKT"
    )

    forsvunna = sum(
        1
        for post in resultat
        if post.get(
            "utfall"
        ) == "FÖRSVUNNEN"
    )

    forsvunna_efter_sankning = sum(
        1
        for post in resultat
        if post.get(
            "utfall"
        )
        == "FÖRSVUNNEN_EFTER_PRISSÄNKNING"
    )

    ingen_data = sum(
        1
        for post in resultat
        if post.get(
            "utfall"
        ) == "INGEN_DATA"
    )

    okanda = sum(
        1
        for post in resultat
        if post.get(
            "utfall"
        ) == "OKÄNT"
    )

    snabba_forvinnanden = sum(
        1
        for post in resultat
        if post.get(
            "snabbt_forvinnande"
        )
    )

    prissankningar = [
        post
        for post in resultat
        if post.get(
            "utfall"
        )
        in (
            "PRISSÄNKT",
            "FÖRSVUNNEN_EFTER_PRISSÄNKNING",
        )
    ]

    total_sankning = sum(
        post.get(
            "total_prissankning",
            0,
        )
        for post in prissankningar
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
        f"Antal fynd-event: "
        f"{antal}"
    )

    print(
        f"Aktiva: "
        f"{aktiva}"
    )

    print(
        f"Prissänkta: "
        f"{prissankta}"
    )

    print(
        f"Försvunna: "
        f"{forsvunna}"
    )

    print(
        f"Försvunna efter prissänkning: "
        f"{forsvunna_efter_sankning}"
    )

    print(
        f"Ingen efterföljande data: "
        f"{ingen_data}"
    )

    print(
        f"Okända: "
        f"{okanda}"
    )

    print()

    print(
        f"Snabba försvinnanden "
        f"(<= {SNABBT_UTFALL_DAGAR} dagar): "
        f"{snabba_forvinnanden}"
    )

    if prissankningar:
        print(
            f"Total observerad prissänkning: "
            f"{total_sankning:,} kr".replace(
                ",",
                " ",
            )
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
            x.get(
                "score",
                0,
            ),
            x.get(
                "diff",
                0,
            ),
        ),
        reverse=True,
    ):
        pris = post.get(
            "pris",
            0,
        )

        diff = post.get(
            "diff",
            0,
        )

        print(
            f"{post.get('utfall', 'OKÄNT'):32} | "
            f"score {post.get('score', 0):3} | "
            f"{post.get('arsmodell', '?')} | "
            f"{post.get('miltal', 0):>6} mil | "
            f"{pris:>9,} kr | "
            f"diff {diff:>8,} | "
            f"{post.get('modell', '')}"
            .replace(
                ",",
                " ",
            )
        )

    _skriv_scoreanalys(
        resultat
    )

    print()

    print(
        "------------------------------------------------------------"
    )
    print(
        " PRISSÄNKNINGAR"
    )
    print(
        "------------------------------------------------------------"
    )

    if not prissankningar:
        print(
            "Inga observerade prissänkningar ännu."
        )

    else:
        for post in sorted(
            prissankningar,
            key=lambda x: (
                x.get(
                    "dagar_till_prissankning"
                )
                if x.get(
                    "dagar_till_prissankning"
                )
                is not None
                else 9999
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
                .replace(
                    ",",
                    " "
                )
            )

    print()

    resultatfil = (
        _skriv_resultatfil(
            resultat
        )
    )

    print(
        f"Resultat sparat i: "
        f"{resultatfil}"
    )

    print()

    print(
        "============================================================"
    )


if __name__ == "__main__":
    main()
