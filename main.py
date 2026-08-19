"""
Fiskabilar - huvudscript.

Flöde:
1. Kontrollera aktiv tid.
2. Hämta annonser.
3. Deduplicera.
4. Uppdatera state.
5. Läs och berika med långtidshistorik.
6. Spara annonsobservationer till långtidshistoriken.
7. Bygg marknadsunderlag.
8. Beräkna marknadsvärde/fynd.
9. Spara marknadsvärdesobservationer.
10. Kör trendanalys exakt en gång efter att dagens historik sparats.
11. Skicka nya fynd.
12. Spara state även när inget mejl skickats.

Trendanalysen påverkar inte score eller valuation.
"""
from app_logging.logger import info

from datetime import datetime
from zoneinfo import ZoneInfo

from app_logging.logger import configure_from_argv
from config import AKTIVA_KALLOR
from matching.deduplicate import deduplicera
from history.state import (
    ladda_state,
    spara_state,
    uppdatera_och_berika,
    redan_notifierad,
    markera_notifierad,
)
from valuation.market_value import (
    bygg_marknadsunderlag,
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
from notifications.email import skicka_epost
from history.analysis import (
    spara_annonsobservation,
    spara_marknadsvardesobservation,
    bygg_historikindex,
    berika_med_historik,
    bygg_marknadstrender,
)
from sources import blocket, wayke, bytbil, bilweb


KALLA_TILL_MODUL = {
    "blocket": blocket,
    "wayke": wayke,
    "bytbil": bytbil,
    "bilweb": bilweb,
}

AKTIV_TID_START = 6
AKTIV_TID_SLUT = 22
TIDSZON = ZoneInfo("Europe/Stockholm")

MIN_SCORE_FOR_NOTIS = 60
MIN_DIFF_FOR_CANDIDATE = 15000
MIN_MILTAL_FOR_KANDIDAT = 1000
DIAGNOSTIK_ANTAL = 20


def _inom_aktiv_tid() -> bool:
    nu = datetime.now(TIDSZON)
    return AKTIV_TID_START <= nu.hour < AKTIV_TID_SLUT


def hamta_alla_annonser() -> list[dict]:
    alla = []

    for kalla in AKTIVA_KALLOR:
        modul = KALLA_TILL_MODUL.get(kalla)

        if modul is None:
            info(f"Okänd källa i config: {kalla}")
            continue

        try:
            annonser = modul.hamta_annonser()
            info(f"[KÄLLA] {kalla}: {len(annonser)} annonser")
            alla.extend(annonser)
        except Exception as e:
            info(f"FEL i källa '{kalla}': {e}")

    return alla


def _annons_namn(bil: dict) -> str:
    try:
        return bil_rubrik(bil)
    except Exception:
        return str(bil.get("modell") or "Okänd modell")


def _logga_kandidat(
    bil: dict,
    vardering: dict,
    score: int,
    status: str,
) -> dict:
    breakdown = berakna_fyndscore_breakdown(bil, vardering)
    mildiag = berakna_miltalsdiagnostik(bil)

    return {
        "score": score,
        "prispoang": breakdown["pris"],
        "miltalspoang": breakdown["miltal"],
        "utrustningspoang": breakdown["utrustning"],
        "trygghetspoang": breakdown["trygghet"],
        "auktion_avdrag": breakdown["auktion_avdrag"],
        "diff": vardering.get("diff", 0),
        "marknad": vardering.get("marknadsvarde", 0),
        "pris": bil.get("annonspris", 0),
        "miltal": bil.get("miltal", 0),
        "arsmodell": bil.get("arsmodell", "?"),
        "modell": _annons_namn(bil),
        "utrustning": bil.get("utrustningsniva", ""),
        "status": status,
        "url": (bil.get("urls") or [bil.get("url") or ""])[0],
        "alder_ar": mildiag["alder_ar"],
        "forvantat_mil": mildiag["forvantat_mil"],
        "mil_avvikelse": mildiag["mil_avvikelse"],
        "mil_justering": mildiag["mil_justering"],
        "marknadsdiagnostik": vardering.get("marknadsdiagnostik"),

        # Historik visas endast som diagnostik.
        # Den påverkar inte score eller valuation.
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


def _formatera_historikdiagnostik(k: dict) -> str | None:
    observationer = k.get("historik_observationer", 0)

    if not observationer:
        return None

    delar = [
        f"Historik: {observationer} obs",
        f"{k.get('historik_dagar', 0)} dagar",
    ]

    forsta_pris = k.get("historik_forsta_pris")
    senaste_pris = k.get("historik_senaste_pris")
    prisfall = k.get("historik_prisfall", 0)

    if isinstance(forsta_pris, (int, float)):
        delar.append(
            f"första pris {forsta_pris:,.0f} kr".replace(
                ",",
                " ",
            )
        )

    if isinstance(senaste_pris, (int, float)):
        delar.append(
            f"senaste {senaste_pris:,.0f} kr".replace(
                ",",
                " ",
            )
        )

    if prisfall:
        delar.append(
            f"prisfall {prisfall:,.0f} kr".replace(
                ",",
                " ",
            )
        )

    marknad = k.get("historik_marknadsvarde")

    if isinstance(marknad, (int, float)):
        delar.append(
            f"historiskt MV {marknad:,.0f} kr".replace(
                ",",
                " ",
            )
        )

    return " | ".join(delar)


def _skriv_diagnostik(kandidater: list[dict]) -> None:
    if not kandidater:
        info("\n=== DIAGNOSTIK ===")
        info("Inga kandidater passerade valuation.")
        return

    kandidater = sorted(
        kandidater,
        key=lambda x: (x["score"], x["diff"]),
        reverse=True,
    )

    info("\n" + "=" * 80)
    info("=== DIAGNOSTIK: BÄSTA KANDIDATER ===")
    info("=" * 80)

    for i, k in enumerate(kandidater[:DIAGNOSTIK_ANTAL], 1):
        info(
            f"{i:02d}. {k['score']:3d}/100 | "
            f"{k['arsmodell']} | {k['miltal']:,} mil | "
            f"{k['pris']:,} kr | diff +{k['diff']:,} | "
            f"{k['modell']} | {k['utrustning']} | {k['status']}"
            .replace(",", " ")
        )

        info(
            "    "
            f"Pris: {k['prispoang']}/60 | "
            f"Miltal: {k['miltalspoang']}/20 | "
            f"Utrustning: {k['utrustningspoang']}/5 | "
            f"Trygghet: {k['trygghetspoang']}/15"
        )

        historiktext = _formatera_historikdiagnostik(k)

        if historiktext:
            info(f"    {historiktext}")

    info("=" * 80)


def main():
    info("\n=== Bilfyndfilter startar ===\n")

    if not _inom_aktiv_tid():
        nu = datetime.now(TIDSZON)

        info(
            f"Utanför aktiv tid ({nu.strftime('%H:%M')} svensk tid, "
            f"fönster {AKTIV_TID_START:02d}:00-"
            f"{AKTIV_TID_SLUT:02d}:00). Avslutar."
        )

        return

    raa_annonser = hamta_alla_annonser()

    info(
        f"Totalt {len(raa_annonser)} annonser innan dedup"
    )

    bilar = deduplicera(raa_annonser)

    info(
        f"{len(bilar)} unika bilar efter dedup"
    )

    state = ladda_state()

    bilar = uppdatera_och_berika(
        bilar,
        state,
    )

    # Läs långtidshistoriken innan dagens observationer sparas.
    #
    # Därmed beskriver historikfälten endast tidigare körningar
    # och dagens observation blandas inte in i underlaget.
    historikindex = bygg_historikindex()

    for bil in bilar:
        try:
            berika_med_historik(
                bil,
                historikindex,
            )

        except Exception as e:
            info(
                "[HISTORIK] Kunde inte läsa historik för annons: "
                f"{e}"
            )

    # Långtidshistorik:
    # en observation per hittad annons och körning.
    for bil in bilar:
        try:
            spara_annonsobservation(bil)

        except Exception as e:
            info(
                "[HISTORIK] Kunde inte spara annonsobservation: "
                f"{e}"
            )

    marknadsunderlag = bygg_marknadsunderlag(
        bilar
    )

    info(
        f"{len(marknadsunderlag)} marknadskategorier byggda"
    )

    statistik = {
        "totalt": len(bilar),
        "leasing_stoppade": 0,
        "miltal_stoppade": 0,
        "valuation_ok": 0,
        "under_diff": 0,
        "score_ok": 0,
        "redan_notifierade": 0,
        "mejl_skickade": 0,
    }

    kandidater = []

    for bil in bilar:

        if _ar_leasingannons(bil):
            statistik["leasing_stoppade"] += 1
            continue

        miltal = bil.get("miltal")

        if (
            not isinstance(miltal, (int, float))
            or miltal < MIN_MILTAL_FOR_KANDIDAT
        ):
            statistik["miltal_stoppade"] += 1
            continue

        try:
            vardering = berakna_fynd(
                bil,
                marknadsunderlag,
            )

        except Exception as e:
            info(
                f"[FEL valuation] {_annons_namn(bil)}: {e}"
            )
            continue

        # Spara värderingen till långtidshistoriken.
        #
        # Historiken påverkar inte dagens valuation eller score.
        try:
            spara_marknadsvardesobservation(
                bil,
                vardering,
            )

        except Exception as e:
            info(
                "[HISTORIK] Kunde inte spara värdeobservation: "
                f"{e}"
            )

        if vardering.get("niva") is None:
            continue

        statistik["valuation_ok"] += 1

        diff = vardering.get(
            "diff",
            0,
        )

        if diff < MIN_DIFF_FOR_CANDIDATE:
            continue

        statistik["under_diff"] += 1

        try:
            score = berakna_fyndscore(
                bil,
                vardering,
            )

        except Exception as e:
            info(
                f"[FEL scoring] {_annons_namn(bil)}: {e}"
            )
            continue

        if score < MIN_SCORE_FOR_NOTIS:
            kandidater.append(
                _logga_kandidat(
                    bil,
                    vardering,
                    score,
                    f"STOPP: score < {MIN_SCORE_FOR_NOTIS}",
                )
            )
            continue

        statistik["score_ok"] += 1

        if redan_notifierad(
            bil,
            state,
        ):
            statistik["redan_notifierade"] += 1

            kandidater.append(
                _logga_kandidat(
                    bil,
                    vardering,
                    score,
                    "STOPP: väntar på minst 15 000 kr "
                    "lägre prisnivå",
                )
            )

            continue

        kandidater.append(
            _logga_kandidat(
                bil,
                vardering,
                score,
                "SKICKAS",
            )
        )

        score_text = score_niva(score)

        emoji, etikett = score_text.split(
            " ",
            1,
        )

        text = formatera_notis(
            bil,
            vardering,
            score,
        )

        diff_formaterad = f"{diff:,}".replace(
            ",",
            " ",
        )

        amne = (
            f"{emoji} {etikett}: "
            f"{bil_rubrik(bil)} "
            f"{bil.get('arsmodell')} - "
            f"{diff_formaterad} kr under marknad"
        )

        skickat = skicka_epost(
            amne,
            text,
        )

        if skickat:
            info(
                f"Mejl skickat: {amne}"
            )

            markera_notifierad(
                bil,
                state,
            )

            statistik["mejl_skickade"] += 1

        else:
            info(
                "OBS: mejl INTE skickat, "
                "försöker igen nästa körning: "
                f"{amne}"
            )

    # ------------------------------------------------------------
    # TRENDANALYS
    #
    # Körs exakt EN gång per huvudkörning.
    #
    # Viktigt:
    # - dagens annonsobservationer är redan sparade
    # - dagens marknadsvärdesobservationer är redan sparade
    # - trendanalysen läser därför hela aktuella historiken
    # - trendanalysen påverkar INTE valuation
    # - trendanalysen påverkar INTE score
    # - trendanalysen används endast som separat marknadsdiagnostik
    # ------------------------------------------------------------

    try:
        bygg_marknadstrender()

    except Exception as e:
        info(
            "[TREND] Kunde inte köra trendanalysen: "
            f"{e}"
        )

    # State sparas alltid.
    #
    # Därmed går även prisförändringar och migrationer
    # tillbaka till GitHub Actions, inte bara körningar
    # där ett mejl skickades.
    spara_state(state)

    _skriv_diagnostik(
        kandidater
    )

    info("\n" + "=" * 70)
    info("=== SAMMANFATTNING ===")
    info("=" * 70)

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
        f"{MIN_MILTAL_FOR_KANDIDAT:,} mil stoppade: "
        f"{statistik['miltal_stoppade']}"
        .replace(",", " ")
    )

    info(
        f"Valuation OK: "
        f"{statistik['valuation_ok']}"
    )

    info(
        f"Över prisdiff-gränsen "
        f"({MIN_DIFF_FOR_CANDIDATE:,} kr): "
        f"{statistik['under_diff']}"
        .replace(",", " ")
    )

    info(
        f"Score >= {MIN_SCORE_FOR_NOTIS}: "
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

    info("=" * 70)


if __name__ == "__main__":
    main()
