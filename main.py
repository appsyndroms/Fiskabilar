"""
Fiskabilar - huvudscript.

Flöde:
1. Kontrollera aktiv tid.
2. Hämta annonser.
3. Deduplicera.
4. Uppdatera state.
5. Spara annonsobservationer till långtidshistoriken.
6. Bygg marknadsunderlag.
7. Beräkna marknadsvärde/fynd.
8. Spara marknadsvärdesobservationer.
9. Skicka nya fynd.
10. Spara state även när inget mejl skickats.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

from config import AKTIVA_KALLOR
from dedup import deduplicera
from state import (
    ladda_state,
    spara_state,
    uppdatera_och_berika,
    redan_notifierad,
    markera_notifierad,
)
from valuation import (
    bygg_marknadsunderlag,
    berakna_fynd,
    berakna_miltalsdiagnostik,
    _ar_leasingannons,
)
from scoring import (
    berakna_fyndscore,
    berakna_fyndscore_breakdown,
    formatera_notis,
    bil_rubrik,
    score_niva,
)
from notify import skicka_epost
from history import (
    spara_annonsobservation,
    spara_marknadsvardesobservation,
)
from scrapers import blocket, wayke, bytbil, bilweb


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
            print(f"Okänd källa i config: {kalla}")
            continue

        try:
            annonser = modul.hamta_annonser()
            print(f"[KÄLLA] {kalla}: {len(annonser)} annonser")
            alla.extend(annonser)
        except Exception as e:
            print(f"FEL i källa '{kalla}': {e}")

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
    }


def _skriv_diagnostik(kandidater: list[dict]) -> None:
    if not kandidater:
        print("\n=== DIAGNOSTIK ===")
        print("Inga kandidater passerade valuation.")
        return

    kandidater = sorted(
        kandidater,
        key=lambda x: (x["score"], x["diff"]),
        reverse=True,
    )

    print("\n" + "=" * 80)
    print("=== DIAGNOSTIK: BÄSTA KANDIDATER ===")
    print("=" * 80)

    for i, k in enumerate(kandidater[:DIAGNOSTIK_ANTAL], 1):
        print(
            f"{i:02d}. {k['score']:3d}/100 | "
            f"{k['arsmodell']} | {k['miltal']:,} mil | "
            f"{k['pris']:,} kr | diff +{k['diff']:,} | "
            f"{k['modell']} | {k['utrustning']} | {k['status']}"
            .replace(",", " ")
        )
        print(
            "    "
            f"Pris: {k['prispoang']}/60 | "
            f"Miltal: {k['miltalspoang']}/20 | "
            f"Utrustning: {k['utrustningspoang']}/5 | "
            f"Trygghet: {k['trygghetspoang']}/15"
        )

    print("=" * 80)


def main():
    print("\n=== Bilfyndfilter startar ===\n")

    if not _inom_aktiv_tid():
        nu = datetime.now(TIDSZON)
        print(
            f"Utanför aktiv tid ({nu.strftime('%H:%M')} svensk tid, "
            f"fönster {AKTIV_TID_START:02d}:00-"
            f"{AKTIV_TID_SLUT:02d}:00). Avslutar."
        )
        return

    raa_annonser = hamta_alla_annonser()
    print(f"Totalt {len(raa_annonser)} annonser innan dedup")

    bilar = deduplicera(raa_annonser)
    print(f"{len(bilar)} unika bilar efter dedup")

    state = ladda_state()
    bilar = uppdatera_och_berika(bilar, state)

    # Långtidshistorik: en observation per hittad annons och körning.
    for bil in bilar:
        try:
            spara_annonsobservation(bil)
        except Exception as e:
            print(f"[HISTORIK] Kunde inte spara annonsobservation: {e}")

    marknadsunderlag = bygg_marknadsunderlag(bilar)
    print(f"{len(marknadsunderlag)} marknadskategorier byggda")

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
        if not isinstance(miltal, (int, float)) or miltal < MIN_MILTAL_FOR_KANDIDAT:
            statistik["miltal_stoppade"] += 1
            continue

        try:
            vardering = berakna_fynd(bil, marknadsunderlag)
        except Exception as e:
            print(f"[FEL valuation] {_annons_namn(bil)}: {e}")
            continue

        # Spara även värderingar som inte blir fynd.
        try:
            spara_marknadsvardesobservation(bil, vardering)
        except Exception as e:
            print(f"[HISTORIK] Kunde inte spara värdeobservation: {e}")

        if vardering.get("niva") is None:
            continue

        statistik["valuation_ok"] += 1

        diff = vardering.get("diff", 0)
        if diff < MIN_DIFF_FOR_CANDIDATE:
            continue

        statistik["under_diff"] += 1

        try:
            score = berakna_fyndscore(bil, vardering)
        except Exception as e:
            print(f"[FEL scoring] {_annons_namn(bil)}: {e}")
            continue

        if score < MIN_SCORE_FOR_NOTIS:
            kandidater.append(
                _logga_kandidat(
                    bil, vardering, score,
                    f"STOPP: score < {MIN_SCORE_FOR_NOTIS}",
                )
            )
            continue

        statistik["score_ok"] += 1

        if redan_notifierad(bil, state):
            statistik["redan_notifierade"] += 1
            kandidater.append(
                _logga_kandidat(
                    bil, vardering, score,
                    "STOPP: väntar på minst 15 000 kr lägre prisnivå",
                )
            )
            continue

        kandidater.append(
            _logga_kandidat(
                bil, vardering, score, "SKICKAS"
            )
        )

        score_text = score_niva(score)
        emoji, etikett = score_text.split(" ", 1)
        text = formatera_notis(bil, vardering, score)

        diff_formaterad = f"{diff:,}".replace(",", " ")
        amne = (
            f"{emoji} {etikett}: {bil_rubrik(bil)} "
            f"{bil.get('arsmodell')} - {diff_formaterad} kr under marknad"
        )

        skickat = skicka_epost(amne, text)

        if skickat:
            print(f"Mejl skickat: {amne}")
            markera_notifierad(bil, state)
            statistik["mejl_skickade"] += 1
        else:
            print(
                "OBS: mejl INTE skickat, försöker igen nästa körning: "
                f"{amne}"
            )

    # State sparas alltid. Därmed går även prisförändringar och migrationer
    # tillbaka till GitHub Actions, inte bara körningar där ett mejl skickades.
    spara_state(state)

    _skriv_diagnostik(kandidater)

    print("\n" + "=" * 70)
    print("=== SAMMANFATTNING ===")
    print("=" * 70)
    print(f"Totalt efter dedup: {statistik['totalt']}")
    print(f"Leasingannonser stoppade: {statistik['leasing_stoppade']}")
    print(f"Bilar under {MIN_MILTAL_FOR_KANDIDAT:,} mil stoppade: "
          f"{statistik['miltal_stoppade']}".replace(",", " "))
    print(f"Valuation OK: {statistik['valuation_ok']}")
    print(f"Över prisdiff-gränsen ({MIN_DIFF_FOR_CANDIDATE:,} kr): "
          f"{statistik['under_diff']}".replace(",", " "))
    print(f"Score >= {MIN_SCORE_FOR_NOTIS}: {statistik['score_ok']}")
    print(f"Redan notifierade: {statistik['redan_notifierade']}")
    print(f"Mejl skickade: {statistik['mejl_skickade']}")
    print("=" * 70)


if __name__ == "__main__":
    main()
