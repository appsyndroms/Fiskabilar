"""
V60-fyndfilter - huvudscript.

Kör: python main.py

Flöde:
0. Kontrollera att klockan är 06:00-22:00 svensk tid (annars avsluta,
   se _inom_aktiv_tid())
1. Hämta annonser från alla aktiva källor
2. Deduplicera (samma bil på flera sajter -> en post)
3. Berika med historik (dagar ute, prissänkning)
4. Beräkna marknadsvärde och fyndnivå per bil
5. För varje NY bil (aldrig notifierad förut) som är FYND/EXTREMT FYND:
   skicka ett eget mejl DIREKT och markera den som notifierad omedelbart
   - varje bil notifieras alltså max en gång totalt, någonsin, och
     mejlet går ut så fort fyndet upptäcks istället för att samlas
     ihop och skickas som en sammanfattning i slutet
"""

from datetime import datetime
from zoneinfo import ZoneInfo

from config import AKTIVA_KALLOR
from dedup import deduplicera
from state import ladda_state, spara_state, uppdatera_och_berika, redan_notifierad, markera_notifierad
from valuation import berakna_fynd
from scoring import berakna_fyndscore, formatera_notis
from notify import skicka_epost

from scrapers import blocket, wayke, bytbil, bilweb

KALLA_TILL_MODUL = {
    "blocket": blocket,
    "wayke": wayke,
    "bytbil": bytbil,
    "bilweb": bilweb,
}

AKTIV_TID_START = 6   # 06:00
AKTIV_TID_SLUT = 22   # 22:00
TIDSZON = ZoneInfo("Europe/Stockholm")


def _inom_aktiv_tid() -> bool:
    """
    Avgör om det just nu är mellan 06:00-22:00 svensk tid.
    Beräknas dynamiskt mot Europe/Stockholm så att sommar-/vintertid
    (CEST/CET) hanteras korrekt automatiskt - workflow-schemat i
    .github/workflows/daily.yml triggar oftare än så här (för att
    täcka båda tidszonlägena) och den här funktionen är den som
    faktiskt avgör om en körning ska göra något.
    """
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
            alla.extend(modul.hamta_annonser())
        except Exception as e:
            print(f"FEL i källa '{kalla}': {e}")
    return alla


def main():
    print("=== V60-fyndfilter startar ===")

    if not _inom_aktiv_tid():
        nu = datetime.now(TIDSZON)
        print(f"Utanför aktiv tid ({nu.strftime('%H:%M')} svensk tid, "
              f"fönster är {AKTIV_TID_START:02d}:00-{AKTIV_TID_SLUT:02d}:00). Avslutar utan att göra något.")
        return

    raa_annonser = hamta_alla_annonser()
    print(f"Totalt {len(raa_annonser)} annonser innan dedup")

    bilar = deduplicera(raa_annonser)
    print(f"{len(bilar)} unika bilar efter dedup")

    state = ladda_state()
    bilar = uppdatera_och_berika(bilar, state)

    antal_skickade = 0

    for bil in bilar:
        vardering = berakna_fynd(bil)
        if vardering["niva"] is None:
            continue

        if redan_notifierad(bil, state):
            continue  # den här bilen har redan mejlats en gång - aldrig igen

        score = berakna_fyndscore(bil, vardering)
        text = formatera_notis(bil, vardering, score)

        niva_etikett = "EXTREMT FYND" if vardering["niva"] == "EXTREMT_FYND" else "FYND"
        amne = f
