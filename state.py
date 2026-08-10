"""
Sparar historik mellan dagliga körningar (i en enkel JSON-fil) så vi kan:
- upptäcka prissänkningar
- veta hur länge en annons legat ute
- undvika att skicka notis för samma fynd flera dagar i rad
"""

import json
import os
from datetime import date

from config import STATE_FIL, MIN_DAGAR_FOR_SANKNING_RELEVANT, STOR_SANKNING_KR


def _nyckel(bil: dict) -> str:
    if bil.get("regnr"):
        return f"reg:{bil['regnr'].upper().replace(' ', '')}"
    return f"kal:{bil.get('variant')}:{bil.get('arsmodell')}:{bil.get('miltal')}"


def ladda_state() -> dict:
    if not os.path.exists(STATE_FIL):
        return {}
    with open(STATE_FIL, "r", encoding="utf-8") as f:
        return json.load(f)


def spara_state(state: dict) -> None:
    os.makedirs(os.path.dirname(STATE_FIL), exist_ok=True)
    with open(STATE_FIL, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def uppdatera_och_berika(bilar: list[dict], state: dict) -> list[dict]:
    """
    Jämför dagens bilar mot sparad historik. Lägger till på varje bil:
    - dagar_ute: hur många dagar annonsen synts i filtret
    - prissankning_kr: total sänkning sedan första observation
    - prissankning_relevant: bool, True om sänkningen skedde efter att
      bilen legat ute ett tag (dvs inte bara en ny annons redan
      prissatt lågt)
    - redan_notifierad: bool, om vi redan larmat om den här bilen
      på samma nivå tidigare
    """
    idag = date.today().isoformat()
    resultat = []

    for bil in bilar:
        nyckel = _nyckel(bil)
        historik = state.get(nyckel)

        if historik is None:
            state[nyckel] = {
                "forsta_sedd": idag,
                "forsta_pris": bil["annonspris"],
                "senaste_pris": bil["annonspris"],
                "senast_sedd": idag,
                "notifierad_nivaer": [],
            }
            bil["dagar_ute"] = 0
            bil["prissankning_kr"] = 0
            bil["prissankning_relevant"] = False
        else:
            forsta_sedd = date.fromisoformat(historik["forsta_sedd"])
            dagar_ute = (date.today() - forsta_sedd).days
            sankning = historik["forsta_pris"] - bil["annonspris"]

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


def redan_notifierad(bil: dict, state: dict, niva: str) -> bool:
    nyckel = _nyckel(bil)
    historik = state.get(nyckel, {})
    return niva in historik.get("notifierad_nivaer", [])


def markera_notifierad(bil: dict, state: dict, niva: str) -> None:
    nyckel = _nyckel(bil)
    if nyckel in state:
        nivaer = state[nyckel].setdefault("notifierad_nivaer", [])
        if niva not in nivaer:
            nivaer.append(niva)
