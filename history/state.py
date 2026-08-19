"""
Sparar kortsiktig körnings-/notifieringsstate.

Den långsiktiga marknadshistoriken ligger separat i
data/market_history.jsonl och ska aldrig behöva migreras tillsammans
med state.json.
"""
from app_logging.logger import info

import json
import os
from datetime import date

from config import (
    STATE_FIL,
    MIN_DAGAR_FOR_SANKNING_RELEVANT,
    STOR_SANKNING_KR,
    MIN_PRISSANKNING_FOR_NY_NOTIS,
)


def _nyckel(bil: dict) -> str:
    """Stabil nyckel för samma annons över tid."""
    if bil.get("regnr"):
        return f"reg:{str(bil['regnr']).upper().replace(' ', '')}"

    if bil.get("annons_id"):
        return f"annons:{str(bil['annons_id']).strip()}"

    url = bil.get("url")
    if url:
        return f"url:{str(url).strip().rstrip('/')}"

    urls = bil.get("urls") or []
    for kandidat in urls:
        if kandidat:
            return f"url:{str(kandidat).strip().rstrip('/')}"

    # Sista fallback för gamla/inkompletta datakällor.
    modell = (bil.get("modell") or "v60").lower()
    return (
        f"kal:{modell}:{bil.get('variant')}:"
        f"{bil.get('arsmodell')}:{bil.get('miltal')}"
    )


def _gammal_nyckel(bil: dict) -> str:
    modell = (bil.get("modell") or "v60").lower()
    return (
        f"kal:{modell}:{bil.get('variant')}:"
        f"{bil.get('arsmodell')}:{bil.get('miltal')}"
    )


def _hamta_historik(bil: dict, state: dict):
    nyckel = _nyckel(bil)
    historik = state.get(nyckel)

    if historik is not None:
        return nyckel, historik

    # Försiktig migration av gamla state-poster. Vi migrerar endast
    # när den gamla nyckeln matchar exakt. Vi gissar aldrig mellan
    # flera möjliga bilar.
    gammal = _gammal_nyckel(bil)
    historik = state.get(gammal)

    if historik is not None and nyckel != gammal:
        state[nyckel] = historik
        state[nyckel]["migrerad_fran"] = gammal
        return nyckel, historik

    return nyckel, None


def ladda_state() -> dict:
    if not os.path.exists(STATE_FIL):
        return {}

    with open(STATE_FIL, "r", encoding="utf-8") as f:
        state = json.load(f)

    migrerade = False

    # Försiktig migration:
    # gamla notifierade poster får senaste pris som första kända
    # notifieringsnivå. Därmed skickas inga gamla fynd ut igen direkt.
    for historik in state.values():
        if not isinstance(historik, dict):
            continue

        if historik.get("notifierad") is True:
            if "notifierad_pris" not in historik:
                pris = historik.get("senaste_pris")
                if isinstance(pris, (int, float)):
                    historik["notifierad_pris"] = pris
                    migrerade = True

    if migrerade:
        info(
            "[STATE] Migrering klar: gamla notifieringar har fått "
            "notifierad_pris baserat på senaste kända pris."
        )

    return state


def spara_state(state: dict) -> None:
    os.makedirs(os.path.dirname(STATE_FIL), exist_ok=True)

    with open(STATE_FIL, "w", encoding="utf-8") as f:
        json.dump(
            state,
            f,
            ensure_ascii=False,
            indent=2,
        )


def uppdatera_och_berika(
    bilar: list[dict],
    state: dict,
) -> list[dict]:
    """
    Jämför dagens bilar mot sparad state och lägger till:
    - dagar_ute
    - prissankning_kr
    - prissankning_relevant
    """

    idag = date.today().isoformat()
    resultat = []

    for bil in bilar:
        nyckel, historik = _hamta_historik(bil, state)

        if historik is None:
            state[nyckel] = {
                "forsta_sedd": idag,
                "forsta_pris": bil["annonspris"],
                "senaste_pris": bil["annonspris"],
                "senast_sedd": idag,
                "notifierad": False,
            }

            bil["dagar_ute"] = 0
            bil["prissankning_kr"] = 0
            bil["prissankning_relevant"] = False

        else:
            forsta_sedd = date.fromisoformat(
                historik["forsta_sedd"]
            )

            dagar_ute = (
                date.today() - forsta_sedd
            ).days

            sankning = (
                historik["forsta_pris"]
                - bil["annonspris"]
            )

            bil["dagar_ute"] = dagar_ute
            bil["prissankning_kr"] = sankning
            bil["prissankning_relevant"] = (
                sankning >= STOR_SANKNING_KR
                and dagar_ute >= MIN_DAGAR_FOR_SANKNING_RELEVANT
            )

            historik["senaste_pris"] = bil["annonspris"]
            historik["senast_sedd"] = idag

        resultat.append(bil)

    return resultat


def redan_notifierad(
    bil: dict,
    state: dict,
) -> bool:
    """
    True om bilen fortfarande ligger på samma notifieringsnivå.

    En gammal notifierad=True utan notifierad_pris migreras i ladda_state()
    och spärras därför tills bilen faktiskt blivit minst 15 000 kr billigare.
    """

    nyckel, historik = _hamta_historik(bil, state)
    historik = historik or {}

    if not historik.get("notifierad", False):
        return False

    notifierad_pris = historik.get("notifierad_pris")

    if not isinstance(
        notifierad_pris,
        (int, float),
    ):
        # Säkerhetsfallback: gammal post utan pris ska inte orsaka spam.
        return True

    aktuellt_pris = bil.get("annonspris")

    if not isinstance(
        aktuellt_pris,
        (int, float),
    ):
        return True

    return (
        aktuellt_pris
        > notifierad_pris - MIN_PRISSANKNING_FOR_NY_NOTIS
    )


def markera_notifierad(
    bil: dict,
    state: dict,
) -> None:
    nyckel, historik = _hamta_historik(bil, state)

    if historik is not None:
        state[nyckel]["notifierad"] = True
        state[nyckel]["notifierad_pris"] = bil.get(
            "annonspris"
        )
