"""
Diagnostikutskrifter för Fiskabilar.
"""

from app_logging.logger import info


DIAGNOSTIK_ANTAL = 20


def _formatera_historikdiagnostik(
    kandidat: dict,
) -> str | None:

    observationer = kandidat.get(
        "historik_observationer",
        0,
    )

    if not observationer:
        return None

    delar = [
        f"Historik: {observationer} obs",
        (
            f"{kandidat.get('historik_dagar', 0)} "
            "dagar"
        ),
    ]

    forsta_pris = kandidat.get(
        "historik_forsta_pris"
    )

    senaste_pris = kandidat.get(
        "historik_senaste_pris"
    )

    prisfall = kandidat.get(
        "historik_prisfall",
        0,
    )

    if isinstance(
        forsta_pris,
        (int, float),
    ):
        delar.append(
            f"första pris "
            f"{forsta_pris:,.0f} kr".replace(
                ",",
                " ",
            )
        )

    if isinstance(
        senaste_pris,
        (int, float),
    ):
        delar.append(
            f"senaste "
            f"{senaste_pris:,.0f} kr".replace(
                ",",
                " ",
            )
        )

    if prisfall:
        delar.append(
            f"prisfall "
            f"{prisfall:,.0f} kr".replace(
                ",",
                " ",
            )
        )

    marknad = kandidat.get(
        "historik_marknadsvarde"
    )

    if isinstance(
        marknad,
        (int, float),
    ):
        delar.append(
            f"historiskt MV "
            f"{marknad:,.0f} kr".replace(
                ",",
                " ",
            )
        )

    return " | ".join(
        delar
    )


def skriv_diagnostik(
    kandidater: list[dict],
) -> None:

    if not kandidater:
        info(
            "\n=== DIAGNOSTIK ==="
        )

        info(
            "Inga kandidater passerade valuation."
        )

        return

    kandidater = sorted(
        kandidater,
        key=lambda x: (
            x["score"],
            x["diff"],
        ),
        reverse=True,
    )

    info(
        "\n" + "=" * 80
    )

    info(
        "=== DIAGNOSTIK: BÄSTA KANDIDATER ==="
    )

    info(
        "=" * 80
    )

    for i, kandidat in enumerate(
        kandidater[
            :DIAGNOSTIK_ANTAL
        ],
        1,
    ):
        info(
            f"{i:02d}. "
            f"{kandidat['score']:3d}/100 | "
            f"{kandidat['arsmodell']} | "
            f"{kandidat['miltal']:,} mil | "
            f"{kandidat['pris']:,} kr | "
            f"diff +{kandidat['diff']:,} | "
            f"{kandidat['modell']} | "
            f"{kandidat['utrustning']} | "
            f"{kandidat['status']}"
            .replace(",", " ")
        )

        info(
            "    "
            f"Pris: {kandidat['prispoang']}/60 | "
            f"Miltal: {kandidat['miltalspoang']}/20 | "
            f"Utrustning: "
            f"{kandidat['utrustningspoang']}/5 | "
            f"Trygghet: "
            f"{kandidat['trygghetspoang']}/15"
        )

        historik = (
            _formatera_historikdiagnostik(
                kandidat
            )
        )

        if historik:
            info(
                f"    {historik}"
            )

    info(
        "=" * 80
    )


def skriv_sammanfattning(
    statistik: dict,
) -> None:

    info(
        "\n" + "=" * 70
    )

    info(
        "=== SAMMANFATTNING ==="
    )

    info(
        "=" * 70
    )

    info(
        f"Totalt efter dedup: "
        f"{statistik['totalt']}"
    )

    info(
        f"Leasingannonser stoppade: "
        f"{statistik['leasing_stoppade']}"
    )

    info(
        f"Bilar under "
        f"{statistik['min_miltal']:,} mil stoppade: "
        f"{statistik['miltal_stoppade']}"
        .replace(",", " ")
    )

    info(
        f"Valuation OK: "
        f"{statistik['valuation_ok']}"
    )

    info(
        f"Över prisdiff-gränsen "
        f"({statistik['min_diff']:,} kr): "
        f"{statistik['under_diff']}"
        .replace(",", " ")
    )

    info(
        f"Score >= "
        f"{statistik['min_score']}: "
        f"{statistik['score_ok']}"
    )

    info(
        f"Redan notifierade: "
        f"{statistik['redan_notifierade']}"
    )

    info(
        f"Mejl skickade: "
        f"{statistik['mejl_skickade']}"
    )

    info(
        "=" * 70
    )
