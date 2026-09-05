"""
Kandidatpipeline för Fiskabilar.
Ansvarar för:
- leasingfilter
- miltalsfilter
- valuation
- historisk värdeobservation
- fyndscore
- feedback från faktiska fynd
- notifieringskontroll
- mejlutskick
- kandidatdiagnostik
Själva huvudflödet ligger i main.py.
"""

from app_logging.logger import (
    info,
    always,
)

from config import (
    DEBUG,
)

from valuation.market_value import (
    berakna_fynd,
    berakna_miltalsdiagnostik,
    _ar_leasingannons,
)

from scoring.score import (
    berakna_fyndscore,
    berakna_fyndscore_breakdown,
    formatera_notis,
    bil_rubrik,
    score_niva,
)

from notifications.email import (
    skicka_epost,
)

from history.analysis import (
    spara_marknadsvardesobservation,
)

from history.find_feedback import (
    spara_fyndfeedback,
)

from history.state import (
    redan_notifierad,
    markera_notifierad,
)


MIN_SCORE_FOR_NOTIS = 60
MIN_DIFF_FOR_CANDIDATE = 15000
MIN_MILTAL_FOR_KANDIDAT = 1000


def _annons_namn(
    bil: dict,
) -> str:
    try:
        return bil_rubrik(
            bil
        )
    except Exception:
        return str(
            bil.get("modell")
            or "Okänd modell"
        )


def _logga_kandidat(
    bil: dict,
    vardering: dict,
    score: int,
    status: str,
) -> dict:
    breakdown = (
        berakna_fyndscore_breakdown(
            bil,
            vardering,
        )
    )

    mildiag = (
        berakna_miltalsdiagnostik(
            bil
        )
    )

    return {
        "score": score,
        "prispoang": breakdown["pris"],
        "miltalspoang": breakdown["miltal"],
        "utrustningspoang": breakdown[
            "utrustning"
        ],
        "trygghetspoang": breakdown[
            "trygghet"
        ],
        "historikspoang": breakdown[
            "historik"
        ],
        "auktion_avdrag": breakdown[
            "auktion_avdrag"
        ],
        "diff": vardering.get(
            "diff",
            0,
        ),
        "marknad": vardering.get(
            "marknadsvarde",
            0,
        ),
        "pris": bil.get(
            "annonspris",
            0,
        ),
        "miltal": bil.get(
            "miltal",
            0,
        ),
        "arsmodell": bil.get(
            "arsmodell",
            "?",
        ),
        "modell": _annons_namn(
            bil
        ),
        "utrustning": bil.get(
            "utrustningsniva",
            "",
        ),
        "status": status,
        "url": (
            bil.get("urls")
            or [
                bil.get("url")
                or ""
            ]
        )[0],
        "alder_ar": mildiag[
            "alder_ar"
        ],
        "forvantat_mil": mildiag[
            "forvantat_mil"
        ],
        "mil_avvikelse": mildiag[
            "mil_avvikelse"
        ],
        "mil_justering": mildiag[
            "mil_justering"
        ],
        "marknadsdiagnostik": (
            vardering.get(
                "marknadsdiagnostik"
            )
        ),
        "historik_observationer": bil.get(
            "historik_observationer",
            0,
        ),
        "historik_dagar": bil.get(
            "historik_dagar",
            0,
        ),
        "historik_forsta_pris": bil.get(
            "historik_forsta_pris"
        ),
        "historik_senaste_pris": bil.get(
            "historik_senaste_pris"
        ),
        "historik_prisfall": bil.get(
            "historik_prisfall",
            0,
        ),
        "historik_prisforandring": bil.get(
            "historik_prisforandring",
            0,
        ),
        "historik_marknadsvarde": bil.get(
            "historik_marknadsvarde"
        ),
    }


def _skicka_kandidat(
    bil: dict,
    vardering: dict,
    score: int,
) -> bool:
    diff = vardering.get(
        "diff",
        0,
    )

    score_text = score_niva(
        score
    )

    emoji, etikett = (
        score_text.split(
            " ",
            1,
        )
    )

    text = formatera_notis(
        bil,
        vardering,
        score,
    )

    diff_formaterad = (
        f"{diff:,}".replace(
            ",",
            " ",
        )
    )

    amne = (
        f"{emoji} {etikett}: "
        f"{bil_rubrik(bil)} "
        f"{bil.get('arsmodell')} - "
        f"{diff_formaterad} kr "
        f"under marknad"
    )

    url = (
        bil.get("urls")
        or [
            bil.get("url")
            or ""
        ]
    )[0]

    # ------------------------------------------------------------
    # DEBUG
    # ------------------------------------------------------------

    if DEBUG:
        always(
            "DEBUG: mejl INTE skickat: "
            f"{amne} | "
            f"URL: {url}"
        )
        return False

    skickat = skicka_epost(
        amne,
        text,
    )

    if skickat:
        always(
            f"Mejl skickat: "
            f"{amne} | "
            f"URL: {url}"
        )
    else:
        always(
            "OBS: mejl INTE skickat, "
            "försöker igen nästa körning: "
            f"{amne} | "
            f"URL: {url}"
        )

    return skickat


def processa_kandidater(
    bilar: list[dict],
    marknadsunderlag: dict,
    state: dict,
) -> tuple[dict, list[dict]]:

    statistik = {
        "totalt": len(bilar),
        "leasing_stoppade": 0,
        "miltal_stoppade": 0,
        "valuation_ok": 0,
        "under_diff": 0,
        "score_ok": 0,
        "redan_notifierade": 0,
        "mejl_skickade": 0,

        # Används av diagnostics.py.
        "min_score": MIN_SCORE_FOR_NOTIS,
        "min_diff": MIN_DIFF_FOR_CANDIDATE,
        "min_miltal": MIN_MILTAL_FOR_KANDIDAT,
    }

    kandidater = []

    for bil in bilar:

        # --------------------------------------------------------
        # LEASING
        # --------------------------------------------------------

        if _ar_leasingannons(
            bil
        ):
            statistik[
                "leasing_stoppade"
            ] += 1
            continue

        # --------------------------------------------------------
        # MILTAL
        # --------------------------------------------------------

        miltal = bil.get(
            "miltal"
        )

        if (
            not isinstance(
                miltal,
                (int, float),
            )
            or miltal
            < MIN_MILTAL_FOR_KANDIDAT
        ):
            statistik[
                "miltal_stoppade"
            ] += 1
            continue

        # --------------------------------------------------------
        # VALUATION
        # --------------------------------------------------------

        try:
            vardering = (
                berakna_fynd(
                    bil,
                    marknadsunderlag,
                )
            )

        except Exception as e:
            info(
                f"[FEL valuation] "
                f"{_annons_namn(bil)}: "
                f"{e}"
            )
            continue

        if (
            vardering.get(
                "niva"
            )
            is None
        ):
            continue

        statistik[
            "valuation_ok"
        ] += 1

        # --------------------------------------------------------
        # PRISDIFF
        # --------------------------------------------------------

        diff = vardering.get(
            "diff",
            0,
        )

        if (
            diff
            < MIN_DIFF_FOR_CANDIDATE
        ):
            continue

        statistik[
            "under_diff"
        ] += 1

        # --------------------------------------------------------
        # SCORE
        # --------------------------------------------------------

        try:
            score = (
                berakna_fyndscore(
                    bil,
                    vardering,
                )
            )

        except Exception as e:
            info(
                f"[FEL scoring] "
                f"{_annons_namn(bil)}: "
                f"{e}"
            )
            continue

        # --------------------------------------------------------
        # HISTORIK
        # --------------------------------------------------------
        #
        # Spara observationen efter att score har räknats fram.
        #
        # Historiken ska vara komplett även om bilen senare
        # stoppas av score- eller notifieringsregler.
        # --------------------------------------------------------

        try:
            spara_marknadsvardesobservation(
                bil,
                vardering,
            )

        except Exception as e:
            info(
                "[HISTORIK] Kunde inte spara "
                f"värdeobservation: {e}"
            )

        if (
            score
            < MIN_SCORE_FOR_NOTIS
        ):
            kandidater.append(
                _logga_kandidat(
                    bil,
                    vardering,
                    score,
                    (
                        "STOPP: score < "
                        f"{MIN_SCORE_FOR_NOTIS}"
                    ),
                )
            )
            continue

        statistik[
            "score_ok"
        ] += 1

        # --------------------------------------------------------
        # FEEDBACK / LÄRANDE
        # --------------------------------------------------------
        #
        # Alla bilar som passerar fyndscore-gränsen registreras
        # som fynd. Detta görs innan notifieringskontrollen så att
        # även fynd som redan notifierats kan följas över tid.
        #
        # Feedbacklagret sparar bland annat:
        # - fyndscore
        # - score-breakdown
        # - pris
        # - marknadsvärde
        # - prisdiff
        # - miltal
        # - årsmodell
        # - modell
        # - utrustning
        # - URL / identitet
        #
        # Detta påverkar inte score eller valuation.
        # --------------------------------------------------------

        try:
            spara_fyndfeedback(
                bil,
                vardering,
                score,
            )

        except Exception as e:
            info(
                "[FEEDBACK] Kunde inte spara "
                f"fyndfeedback: {e}"
            )

        # --------------------------------------------------------
        # DUPLICERAD NOTIFIERING
        # --------------------------------------------------------

        if redan_notifierad(
            bil,
            state,
        ):
            statistik[
                "redan_notifierade"
            ] += 1

            kandidater.append(
                _logga_kandidat(
                    bil,
                    vardering,
                    score,
                    "STOPP: väntar på minst "
                    "15 000 kr lägre prisnivå",
                )
            )
            continue

        # --------------------------------------------------------
        # SKICKA
        # --------------------------------------------------------

        kandidater.append(
            _logga_kandidat(
                bil,
                vardering,
                score,
                "SKICKAS",
            )
        )

        skickat = _skicka_kandidat(
            bil,
            vardering,
            score,
        )

        if skickat:
            markera_notifierad(
                bil,
                state,
            )

            statistik[
                "mejl_skickade"
            ] += 1

    return (
        statistik,
        kandidater,
    )
