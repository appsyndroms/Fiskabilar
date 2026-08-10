"""
Dubblettkontroll mellan källor.

Samma bil annonseras ofta på flera sajter samtidigt (t.ex. Wayke
speglar ofta Blocket/Bilweb). Vi vill räkna varje FYSISK bil en gång,
och helst behålla den annons som har mest komplett information.

Matchningsstrategi (i turordning, mest tillförlitlig först):
1. Registreringsnummer om det finns i annonsen (starkast signal)
2. Kombination av: variant + årsmodell + miltal (±100 mil) + pris (±2000 kr)
   -> om alla stämmer inom marginal räknas det som samma bil
"""

MIL_MARGINAL = 100
PRIS_MARGINAL = 2000


def _matchar(a: dict, b: dict) -> bool:
    if a.get("regnr") and b.get("regnr"):
        return a["regnr"].upper().replace(" ", "") == b["regnr"].upper().replace(" ", "")

    if a.get("variant") != b.get("variant"):
        return False
    if a.get("arsmodell") != b.get("arsmodell"):
        return False
    if abs(a.get("miltal", 0) - b.get("miltal", 0)) > MIL_MARGINAL:
        return False
    if abs(a.get("annonspris", 0) - b.get("annonspris", 0)) > PRIS_MARGINAL:
        return False
    return True


def _fullstandighetspoang(bil: dict) -> int:
    """Fler kända fält = mer komplett annons, föredras vid dubblett."""
    falt = [
        "regnr", "utrustningsniva", "dragkrok", "varmare", "volvo_selekt",
        "stor_batteri", "antal_agare", "servicehistorik", "senaste_service",
        "nasta_service", "forsta_registrering", "hyrbil", "import",
    ]
    return sum(1 for f in falt if bil.get(f) not in (None, "", False))


def deduplicera(bilar: list[dict]) -> list[dict]:
    """
    Slår ihop bilar som förekommer på flera källor till en post,
    och sparar med vilka källor/URL:er den hittades.
    """
    grupper: list[list[dict]] = []

    for bil in bilar:
        placerad = False
        for grupp in grupper:
            if _matchar(grupp[0], bil):
                grupp.append(bil)
                placerad = True
                break
        if not placerad:
            grupper.append([bil])

    resultat = []
    for grupp in grupper:
        basbil = max(grupp, key=_fullstandighetspoang).copy()
        basbil["kallor"] = sorted({b["kalla"] for b in grupp if b.get("kalla")})
        basbil["urls"] = [b.get("url") for b in grupp if b.get("url")]
        resultat.append(basbil)

    return resultat
