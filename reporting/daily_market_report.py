"""
Daglig marknadsrapport för Fiskabilar.

Rapporten körs separat från fyndmotorn och läser den redan sparade
marknadshistoriken.

Rapporten sammanfattar:
- nya annonser
- prisändringar
- försvunna annonser
- aktuella fynd
- marknadstrender

Rapporten sparas alltid innan mejl försöks skickas.
Ett mejlfel får därför aldrig innebära att dagens rapport förloras.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app_logging.logger import always, error

from config import (
    DAILY_REPORT_KATALOG,
    FYND_TROSKEL,
    EPOST_TILL,
)

from history.analysis_storage import _las_observationer
from history.analysis_trends import bygg_marknadstrender
from notifications.email import skicka_epost


TIDSZON = ZoneInfo("Europe/Stockholm")


def _nu() -> datetime:
    return datetime.now(TIDSZON)


def _parse_tid(value: str | None) -> datetime | None:
    if not value:
        return None

    try:
        dt = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=TIDSZON)

    return dt.astimezone(TIDSZON)


def _datum(post: dict) -> str | None:
    tid = _parse_tid(post.get("tid"))

    if not tid:
        return None

    return tid.date().isoformat()


def _kr(value) -> str:
    if not isinstance(value, (int, float)):
        return "?"

    return f"{value:,.0f}".replace(",", " ") + " kr"


def _diff(value) -> str:
    if not isinstance(value, (int, float)):
        return "?"

    return f"{value:+,.0f}".replace(",", " ") + " kr"


def _procent(value) -> str:
    if not isinstance(value, (int, float)):
        return "?"

    return f"{value:+.2f} %"


def _rubrik(post: dict) -> str:
    modell = str(
        post.get("modell") or ""
    ).strip()

    variant = str(
        post.get("variant") or ""
    ).strip()

    arsmodell = post.get(
        "arsmodell"
    )

    if variant and variant.lower() != modell.lower():
        return (
            f"{modell} "
            f"{variant} "
            f"{arsmodell}"
        ).strip()

    return (
        f"{modell} "
        f"{arsmodell}"
    ).strip()


def _annonsobservationer() -> list[dict]:
    return sorted(
        [
            post
            for post in _las_observationer()
            if post.get("typ") == "annons"
            and post.get("vehicle_id")
        ],
        key=lambda post:
        _parse_tid(
            post.get("tid")
        )
        or datetime.min.replace(
            tzinfo=TIDSZON
        ),
    )


def _varderingar() -> list[dict]:
    return sorted(
        [
            post
            for post in _las_observationer()
            if post.get("typ") == "marknadsvarde"
            and post.get("vehicle_id")
        ],
        key=lambda post:
        _parse_tid(
            post.get("tid")
        )
        or datetime.min.replace(
            tzinfo=TIDSZON
        ),
    )


def _senaste_per_dag_och_bil(
    observationer: list[dict],
) -> dict[tuple[str, str], dict]:

    resultat = {}

    for post in observationer:

        dag = _datum(post)
        vehicle_id = post.get(
            "vehicle_id"
        )

        if not dag or not vehicle_id:
            continue

        nyckel = (
            dag,
            str(vehicle_id),
        )

        tidigare = resultat.get(
            nyckel
        )

        if tidigare is None:
            resultat[nyckel] = post
            continue

        tidigare_tid = _parse_tid(
            tidigare.get("tid")
        )

        aktuell_tid = _parse_tid(
            post.get("tid")
        )

        if (
            aktuell_tid
            and (
                not tidigare_tid
                or aktuell_tid > tidigare_tid
            )
        ):
            resultat[nyckel] = post

    return resultat


def _forandringar(
    datum: str,
) -> dict:

    observationer = (
        _annonsobservationer()
    )

    dagliga = (
        _senaste_per_dag_och_bil(
            observationer
        )
    )

    idag = datetime.fromisoformat(
        datum
    ).date()

    igar = (
        idag
        - timedelta(days=1)
    ).isoformat()

    dagens = {
        vehicle_id: post
        for (
            dag,
            vehicle_id,
        ), post in dagliga.items()
        if dag == datum
    }

    gardagens = {
        vehicle_id: post
        for (
            dag,
            vehicle_id,
        ), post in dagliga.items()
        if dag == igar
    }

    # ---------------------------------------------------------
    # FÖRSTA OBSERVATION
    # ---------------------------------------------------------

    forsta = {}

    for post in observationer:

        vehicle_id = str(
            post.get(
                "vehicle_id"
            )
        )

        dag = _datum(post)

        if not dag:
            continue

        if (
            vehicle_id not in forsta
            or dag
            < forsta[
                vehicle_id
            ][0]
        ):
            forsta[
                vehicle_id
            ] = (
                dag,
                post,
            )

    # ---------------------------------------------------------
    # NYA
    # ---------------------------------------------------------

    nya = [
        post
        for vehicle_id, post
        in dagens.items()
        if (
            forsta.get(
                vehicle_id,
                (None, None),
            )[0]
            == datum
        )
    ]

    # ---------------------------------------------------------
    # PRISÄNDRINGAR
    # ---------------------------------------------------------

    prisandringar = []

    for (
        vehicle_id,
        aktuell,
    ) in dagens.items():

        tidigare = gardagens.get(
            vehicle_id
        )

        if not tidigare:
            continue

        gammalt = tidigare.get(
            "pris"
        )

        nytt = aktuell.get(
            "pris"
        )

        if not isinstance(
            gammalt,
            (int, float),
        ):
            continue

        if not isinstance(
            nytt,
            (int, float),
        ):
            continue

        if gammalt == nytt:
            continue

        prisandringar.append(
            {
                "vehicle_id":
                    vehicle_id,
                "bil":
                    _rubrik(
                        aktuell
                    ),
                "gammalt_pris":
                    gammalt,
                "nytt_pris":
                    nytt,
                "forandring":
                    nytt - gammalt,
                "miltal":
                    aktuell.get(
                        "miltal"
                    ),
                "url":
                    aktuell.get(
                        "url"
                    ),
            }
        )

    prisandringar.sort(
        key=lambda item:
        abs(
            item[
                "forandring"
            ]
        ),
        reverse=True,
    )

    # ---------------------------------------------------------
    # FÖRSVUNNA
    # ---------------------------------------------------------

    forsvunna = [
        post
        for vehicle_id, post
        in gardagens.items()
        if vehicle_id
        not in dagens
    ]

    return {
        "nya": nya,
        "prisandringar":
            prisandringar,
        "forsvunna":
            forsvunna,
        "antal_idag":
            len(dagens),
        "antal_igar":
            len(gardagens),
    }


def _fynd(
    datum: str,
) -> list[dict]:

    annonser = (
        _senaste_per_dag_och_bil(
            _annonsobservationer()
        )
    )

    varderingar = (
        _senaste_per_dag_och_bil(
            _varderingar()
        )
    )

    dagens = {
        vehicle_id: post
        for (
            dag,
            vehicle_id,
        ), post in annonser.items()
        if dag == datum
    }

    senaste_vardering = {}

    for (
        dag,
        vehicle_id,
    ), post in varderingar.items():

        if dag > datum:
            continue

        tidigare = (
            senaste_vardering.get(
                vehicle_id
            )
        )

        if (
            tidigare is None
            or dag > tidigare[0]
        ):
            senaste_vardering[
                vehicle_id
            ] = (
                dag,
                post,
            )

    resultat = []

    for (
        vehicle_id,
        bil,
    ) in dagens.items():

        value = (
            senaste_vardering.get(
                vehicle_id
            )
        )

        if not value:
            continue

        vardering = value[1]

        score = vardering.get(
            "fyndscore"
        )

        diff = vardering.get(
            "diff"
        )

        if not isinstance(
            score,
            (int, float),
        ):
            continue

        if score < 60:
            continue

        if not isinstance(
            diff,
            (int, float),
        ):
            continue

        if diff < FYND_TROSKEL:
            continue

        resultat.append(
            {
                "vehicle_id":
                    vehicle_id,
                "bil":
                    _rubrik(bil),
                "pris":
                    bil.get("pris"),
                "miltal":
                    bil.get("miltal"),
                "marknadsvarde":
                    vardering.get(
                        "marknadsvarde"
                    ),
                "diff":
                    diff,
                "score":
                    int(score),
                "url":
                    bil.get("url"),
            }
        )

    resultat.sort(
        key=lambda item:
        (
            item["score"],
            item["diff"],
        ),
        reverse=True,
    )

    return resultat


def _trender() -> dict:

    trender = (
        bygg_marknadstrender()
    )

    upp = []
    ned = []
    stabil = 0
    otillrackligt = 0

    for analys in (
        trender.values()
    ):

        trend = analys.get(
            "trend"
        )

        item = {
            "kategori":
                analys.get(
                    "kategori",
                    "",
                ),
            "trend":
                trend,
            "forandring_kr":
                analys.get(
                    "trendforandring_kr",
                    0,
                ),
            "forandring_procent":
                analys.get(
                    "trendforandring_procent",
                    0,
                ),
            "marknad_antal":
                analys.get(
                    "marknad_antal_senaste_dag",
                    0,
                ),
        }

        if trend == "upp":
            upp.append(item)

        elif trend == "ned":
            ned.append(item)

        elif trend == "stabil":
            stabil += 1

        else:
            otillrackligt += 1

    upp.sort(
        key=lambda item:
        abs(
            item[
                "forandring_procent"
            ]
        ),
        reverse=True,
    )

    ned.sort(
        key=lambda item:
        abs(
            item[
                "forandring_procent"
            ]
        ),
        reverse=True,
    )

    return {
        "upp": upp,
        "ned": ned,
        "stabil": stabil,
        "otillrackligt":
            otillrackligt,
        "totalt":
            len(trender),
    }


def _kort_kategori(
    kategori: str,
) -> str:

    delar = kategori.split(
        "|"
    )

    if len(delar) != 3:
        return kategori

    modell = delar[0].strip()
    variant = delar[1].strip()
    arsmodell = delar[2].strip()

    if len(variant) > 55:
        variant = (
            variant[:52]
            + "..."
        )

    return (
        f"{modell} "
        f"{variant} "
        f"{arsmodell}"
    )


def _bygg_rapport(
    datum: str,
    forandringar: dict,
    fynd: list[dict],
    trender: dict,
) -> str:

    rader = [
        "============================================================",
        (
            "FISKABILAR – DAGLIG "
            f"MARKNADSRAPPORT {datum}"
        ),
        "============================================================",
        "",
        "MARKNADSLÄGE",
        (
            "Observerade bilar idag: "
            f"{forandringar['antal_idag']}"
        ),
        (
            "Observerade bilar igår: "
            f"{forandringar['antal_igar']}"
        ),
        (
            f"Nya: {len(forandringar['nya'])} | "
            f"Prisändringar: "
            f"{len(forandringar['prisandringar'])} | "
            f"Försvunna: "
            f"{len(forandringar['forsvunna'])} | "
            f"Fynd: {len(fynd)}"
        ),
        "",
        "------------------------------------------------------------",
        "🆕 NYA ANNONSER",
        "------------------------------------------------------------",
    ]

    if forandringar["nya"]:

        for post in (
            forandringar["nya"][:20]
        ):
            rader.append(
                (
                    f"• {_rubrik(post)} | "
                    f"{post.get('miltal', '?')} mil | "
                    f"{_kr(post.get('pris'))}"
                )
            )

    else:
        rader.append(
            "Inga nya annonser idag."
        )

    rader += [
        "",
        "------------------------------------------------------------",
        "💰 PRISÄNDRINGAR",
        "------------------------------------------------------------",
    ]

    if forandringar[
        "prisandringar"
    ]:

        for item in (
            forandringar[
                "prisandringar"
            ][:30]
        ):

            pil = (
                "↓"
                if item[
                    "forandring"
                ] < 0
                else "↑"
            )

            rader.append(
                (
                    f"• {item['bil']} | "
                    f"{_kr(item['gammalt_pris'])} → "
                    f"{_kr(item['nytt_pris'])} "
                    f"{pil} "
                    f"{_diff(item['forandring'])}"
                )
            )

    else:
        rader.append(
            "Inga prisändringar idag."
        )

    rader += [
        "",
        "------------------------------------------------------------",
        "🚪 FÖRSVUNNA ANNONSER",
        "------------------------------------------------------------",
    ]

    if forandringar[
        "forsvunna"
    ]:

        for post in (
            forandringar[
                "forsvunna"
            ][:30]
        ):
            rader.append(
                (
                    f"• {_rubrik(post)} | "
                    f"{post.get('miltal', '?')} mil | "
                    f"{_kr(post.get('pris'))}"
                )
            )

    else:
        rader.append(
            "Inga annonser försvann sedan igår."
        )

    rader += [
        "",
        "------------------------------------------------------------",
        "⭐ DAGENS FYND",
        "------------------------------------------------------------",
    ]

    if fynd:

        for index, item in enumerate(
            fynd[:20],
            start=1,
        ):
            rader.append(
                (
                    f"{index:02d}. "
                    f"{item['bil']} | "
                    f"{item.get('miltal', '?')} mil | "
                    f"{_kr(item.get('pris'))} | "
                    f"score {item['score']}/100 | "
                    f"{_kr(item.get('diff'))} "
                    "under marknad"
                )
            )

            url = item.get("url")

            if url:
                rader.append(
                    f"    URL: {url}"
                )

    else:
        rader.append(
            "Inga fynd över fyndgränsen idag."
        )

    rader += [
        "",
        "------------------------------------------------------------",
        "📈 TREND",
        "------------------------------------------------------------",
        (
            f"UPP={len(trender['upp'])} | "
            f"NED={len(trender['ned'])} | "
            f"STABIL={trender['stabil']} | "
            f"OTILLRÄCKLIGT="
            f"{trender['otillrackligt']}"
        ),
    ]

    for item in trender["ned"][:10]:
        rader.append(
            (
                f"↓ {_kort_kategori(item['kategori'])} | "
                f"{_diff(item['forandring_kr'])} "
                f"({_procent(item['forandring_procent'])})"
            )
        )

    for item in trender["upp"][:10]:
        rader.append(
            (
                f"↑ {_kort_kategori(item['kategori'])} | "
                f"{_diff(item['forandring_kr'])} "
                f"({_procent(item['forandring_procent'])})"
            )
        )

    rader += [
        "",
        "============================================================",
    ]

    return "\n".join(rader)


def _rapportfil() -> str:

    now = _nu()

    os.makedirs(
        DAILY_REPORT_KATALOG,
        exist_ok=True,
    )

    return os.path.join(
        DAILY_REPORT_KATALOG,
        (
            "daily_market_report_"
            f"{now:%Y-%m}.jsonl"
        ),
    )


def _las_dagens_logg(
    datum: str,
) -> dict | None:

    fil = _rapportfil()

    if not os.path.exists(
        fil
    ):
        return None

    try:

        with open(
            fil,
            "r",
            encoding="utf-8",
        ) as handle:

            for rad in handle:

                if not rad.strip():
                    continue

                try:
                    post = json.loads(
                        rad
                    )
                except json.JSONDecodeError:
                    continue

                if (
                    post.get(
                        "datum"
                    )
                    == datum
                ):
                    return post

    except OSError:
        return None

    return None


def _spara_logg(
    post: dict,
) -> None:

    fil = _rapportfil()

    poster = []

    if os.path.exists(
        fil
    ):

        try:

            with open(
                fil,
                "r",
                encoding="utf-8",
            ) as handle:

                for rad in handle:

                    if not rad.strip():
                        continue

                    try:
                        befintlig = (
                            json.loads(rad)
                        )
                    except json.JSONDecodeError:
                        continue

                    if (
                        befintlig.get(
                            "datum"
                        )
                        != post.get(
                            "datum"
                        )
                    ):
                        poster.append(
                            befintlig
                        )

        except OSError as exc:
            error(
                "[RAPPORT] Kunde inte läsa "
                f"befintlig rapportlogg: {exc}"
            )

    poster.append(
        post
    )

    poster.sort(
        key=lambda item:
        item.get(
            "datum",
            "",
        )
    )

    with open(
        fil,
        "w",
        encoding="utf-8",
    ) as handle:

        for item in poster:

            handle.write(
                json.dumps(
                    item,
                    ensure_ascii=False,
                    separators=(
                        ",",
                        ":",
                    ),
                )
                + "\n"
            )


def skapa_och_skicka_rapport(
    force_email: bool = False,
) -> int:

    now = _nu()
    datum = now.date().isoformat()

    befintlig = (
        _las_dagens_logg(
            datum
        )
    )

    try:

        forandringar = (
            _forandringar(
                datum
            )
        )

        fynd = _fynd(
            datum
        )

        trender = _trender()

        text = _bygg_rapport(
            datum,
            forandringar,
            fynd,
            trender,
        )

        post = {
            "datum": datum,
            "skapad":
                now.isoformat(
                    timespec="seconds"
                ),
            "nya":
                len(
                    forandringar[
                        "nya"
                    ]
                ),
            "prisandringar":
                len(
                    forandringar[
                        "prisandringar"
                    ]
                ),
            "forsvunna":
                len(
                    forandringar[
                        "forsvunna"
                    ]
                ),
            "fynd":
                len(fynd),
            "trend_upp":
                len(trender["upp"]),
            "trend_ned":
                len(trender["ned"]),
            "trend_stabil":
                trender["stabil"],
            "rapport":
                text,
            "email_skickat":
                bool(
                    befintlig
                    and befintlig.get(
                        "email_skickat"
                    )
                ),
        }

        # -----------------------------------------------------
        # VIKTIGT:
        # LOGGA FÖRST.
        # -----------------------------------------------------

        _spara_logg(
            post
        )

        always(
            text
        )

        always(
            "[RAPPORT] Loggad: "
            f"{_rapportfil()}"
        )

        # Undvik dubbla mejl vid exempelvis manuell rerun.
        if (
            post["email_skickat"]
            and not force_email
        ):
            always(
                "[RAPPORT] Dagens mejl "
                "är redan skickat."
            )
            return 0

        amne = (
            "Fiskabilar – daglig "
            f"marknadsrapport {datum}"
        )

        skickat = skicka_epost(
            amne,
            text,
        )

        post[
            "email_skickat"
        ] = bool(
            skickat
        )

        post[
            "email_skickat_tid"
        ] = (
            _nu().isoformat(
                timespec="seconds"
            )
            if skickat
            else None
        )

        _spara_logg(
            post
        )

        if skickat:
            always(
                "[RAPPORT] Mejl skickat "
                f"till {EPOST_TILL}"
            )
        else:
            always(
                "[RAPPORT] Mejl kunde inte "
                "skickas. Rapporten är "
                "ändå sparad."
            )

        return 0

    except Exception as exc:

        # Även ett oväntat fel ska lämna ett
        # beständigt spår i rapportloggen.

        fallback = {
            "datum": datum,
            "skapad":
                now.isoformat(
                    timespec="seconds"
                ),
            "status": "FEL",
            "fel": str(exc),
            "rapport": (
                "FISKABILAR – DAGLIG "
                f"MARKNADSRAPPORT {datum}\n\n"
                "Rapporten kunde inte "
                "byggas komplett.\n\n"
                f"Fel: {exc}"
            ),
            "email_skickat": False,
        }

        try:
            _spara_logg(
                fallback
            )
        except Exception as log_exc:
            error(
                "[RAPPORT] Kunde inte "
                f"spara fallback-logg: {log_exc}"
            )

        error(
            "[RAPPORT] Fel vid "
            f"rapportgenerering: {exc}"
        )

        # Rapportjobbet ska inte förlora loggen
        # eller skapa en tom historik bara för att
        # mejlet/rapporten hade ett fel.
        return 0


def main() -> None:

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--force-email",
        action="store_true",
        help=(
            "Skicka dagens rapport igen "
            "även om den redan är skickad."
        ),
    )

    args = parser.parse_args()

    raise SystemExit(
        skapa_och_skicka_rapport(
            force_email=args.force_email
        )
    )


if __name__ == "__main__":

    main()
