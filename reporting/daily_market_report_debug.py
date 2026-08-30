“””
Debugversion av daglig marknadsrapport för Fiskabilar\.

Används för att verifiera rapportens innehåll manuellt innan
den riktiga dagliga rapporten körs i produktion\.

VIKTIGT:

- Läser samma marknadshistorik som produktionsrapporten\.
- Använder samma analysfunktioner\.
- Bygger samma rapport\.
- Skriver rapporten till Actions\-loggen\.
- Skapar INGEN rapportfil\.
- Ändrar INTE daily\_market\_report\-loggen\.
- Skickar ALDRIG mejl\.

Debugkörningen är därför helt isolerad från den riktiga
rapportkörningen klockan 22:00\.
“””

from **future** import annotations

import sys
from datetime import datetime
from zoneinfo import ZoneInfo

from app\_logging\.logger import always, error

from reporting\.daily\_market\_report import &#40;
\_bygg\_rapport,
\_forandringar,
\_fynd,
\_trender,
&#41;

TIDSZON = ZoneInfo&#40;
“Europe/Stockholm”
&#41;

def \_nu&#40;&#41; \-\> datetime:
return datetime\.now&#40;
TIDSZON
&#41;

def skapa\_debugrapport&#40;&#41; \-\> int:
“””
Bygger dagens marknadsrapport utan att skriva någon
rapportlogg och utan att skicka mejl\.
“””

```
now = _nu()

datum = now.date().isoformat()

always(
    "============================================================"
)

always(
    "FISKABILAR – DEBUG AV DAGLIG MARKNADSRAPPORT"
)

always(
    "============================================================"
)

always(
    f"[DEBUG] Datum: {datum}"
)

always(
    "[DEBUG] VIKTIGT: Ingen rapportfil skrivs."
)

always(
    "[DEBUG] VIKTIGT: Inget mejl skickas."
)

always(
    "[DEBUG] VIKTIGT: Produktionsloggen ändras inte."
)

try:

    # -----------------------------------------------------
    # BYGG SAMMA DATA SOM PRODUKTIONSRAPPORTEN
    # -----------------------------------------------------

    always(
        "[DEBUG] Bygger förändringsanalys..."
    )

    forandringar = _forandringar(
        datum
    )

    always(
        "[DEBUG] Bygger fyndanalys..."
    )

    fynd = _fynd(
        datum
    )

    always(
        "[DEBUG] Bygger trendanalys..."
    )

    trender = _trender()

    # -----------------------------------------------------
    # BYGG RAPPORTEN
    # -----------------------------------------------------

    text = _bygg_rapport(
        datum,
        forandringar,
        fynd,
        trender,
    )

    # -----------------------------------------------------
    # DIAGNOSTIK
    # -----------------------------------------------------

    always(
        ""
    )

    always(
        "============================================================"
    )

    always(
        "DEBUG – SAMMANFATTNING"
    )

    always(
        "============================================================"
    )

    always(
        (
            "Observerade bilar idag: "
            f"{forandringar['antal_idag']}"
        )
    )

    always(
        (
            "Observerade bilar igår: "
            f"{forandringar['antal_igar']}"
        )
    )

    always(
        (
            "Nya annonser: "
            f"{len(forandringar['nya'])}"
        )
    )

    always(
        (
            "Prisändringar: "
            f"{len(forandringar['prisandringar'])}"
        )
    )

    always(
        (
            "Försvunna annonser: "
            f"{len(forandringar['forsvunna'])}"
        )
    )

    always(
        (
            "Fynd: "
            f"{len(fynd)}"
        )
    )

    always(
        (
            "Trend upp: "
            f"{len(trender['upp'])}"
        )
    )

    always(
        (
            "Trend ned: "
            f"{len(trender['ned'])}"
        )
    )

    always(
        (
            "Trend stabil: "
            f"{trender['stabil']}"
        )
    )

    always(
        (
            "Trend otillräckligt: "
            f"{trender['otillrackligt']}"
        )
    )

    # -----------------------------------------------------
    # HELA RAPPORTEN
    # -----------------------------------------------------

    always(
        ""
    )

    always(
        "============================================================"
    )

    always(
        "DEBUG – HELA RAPPORTEN"
    )

    always(
        "============================================================"
    )

    for rad in text.splitlines():
        always(
            rad
        )

    always(
        "============================================================"
    )

    always(
        "[DEBUG] Rapporten byggdes utan fel."
    )

    always(
        "[DEBUG] Ingen fil har skrivits."
    )

    always(
        "[DEBUG] Inget mejl har skickats."
    )

    always(
        "============================================================"
    )

    return 0

except Exception as exc:

    error(
        "[DEBUG] Fel vid rapportgenerering: "
        f"{exc}"
    )

    return 1
```

def main&#40;&#41; \-\> None:

```
raise SystemExit(
    skapa_debugrapport()
)
```

if **name** == “**main**”:
main&#40;&#41;
