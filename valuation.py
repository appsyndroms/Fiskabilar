"""
Enkel men transparent marknadsvärdesmodell för V60 Recharge (T6/T8).

Modellen är medvetet regelbaserad (inte ML) så att du begriper och
kan justera VARJE parameter. När du har samlat ~30-50 riktiga
annonser kan du med fördel byta ut detta mot en regression
(t.ex. sklearn LinearRegression på pris ~ ålder + mil + utrustning),
men regelmodellen ger vettiga resultat direkt.

Grundtanke:
1. Baspris per variant och årsmodell (nypris minus generell depreciering)
2. Avdrag per mil utöver "normalt" miltal för åldern
3. Justering för utrustningsnivå (Inscription/Plus/Core etc)
4. Justering för dragkrok, värmare, Volvo Selekt, batteristorlek
"""

from datetime import date

# Ungefärliga baspriser (kr) vid ~7000 mil/år, medelutrustning.
# Dessa ÄR grova uppskattningar - uppdatera efter vad du ser på marknaden.
BASPRIS = {
    ("T6 AWD", 2022): 335000,
    ("T6 AWD", 2023): 375000,
    ("T6 AWD", 2024): 420000,
    ("T8 AWD", 2022): 375000,
    ("T8 AWD", 2023): 415000,
    ("T8 AWD", 2024): 460000,
}

# Kr per mil över/under förväntat miltal för åldern
KR_PER_MIL_AVVIKELSE = 4.5

# Förväntat miltal per år i drift (schablon)
FORVANTAT_MIL_PER_AR = 1500

UTRUSTNINGSNIVA_JUSTERING = {
    "core": -15000,
    "plus": 0,
    "plus, dark": 5000,
    "ultimate": 15000,
    "inscription": 20000,
    "inscription expression": 25000,
    "polestar engineered": 30000,
}
# KÄND BEGRÄNSNING (upptäckt vid testkörning mot riktiga annonser):
# den här matchningen är exakt, inte "innehåller". En annonstitel som
# "R-Design Pano Drag HK Elstol" matchar INGEN nyckel ovan och får då
# ingen utrustningsjustering alls (0 kr), trots att R-Design normalt
# är en premiumnivå. Det kan få välutrustade R-Design-bilar att se
# dyrare/mindre attraktiva ut i jämförelsen än de borde. Åtgärda genom
# att antingen lägga till fler nyckelord (t.ex. "r-design": 10000) eller
# byta ut den exakta matchningen mot en delsträngssökning i titeln.


DRAGKROK_VARDE = 8000
VARMARE_VARDE = 4000  # motor-/kupévärmare
SELEKT_VARDE = 6000   # certifierad begagnad, ger trygghet -> högre efterfrågan
STOR_BATTERI_VARDE = 12000  # 2022/2023 med större batterimodell


def _ar_sedan_arsmodell(arsmodell: int) -> float:
    idag = date.today()
    return max(0.0, (idag.year - arsmodell) + (idag.month - 6) / 12)


def berakna_marknadsvarde(bil: dict) -> int:
    """
    bil förväntas innehålla nycklarna:
    variant (str, "T6 AWD"/"T8 AWD"), arsmodell (int), miltal (int),
    utrustningsniva (str, valfri), dragkrok (bool), varmare (bool),
    volvo_selekt (bool), stor_batteri (bool)
    """
    variant = bil.get("variant")
    arsmodell = bil.get("arsmodell")

    baspris = BASPRIS.get((variant, arsmodell))
    if baspris is None:
        # okänd kombination -> interpolera grovt från närmaste årsmodell
        kandidater = [v for (var, ar), v in BASPRIS.items() if var == variant]
        if not kandidater:
            return 0
        baspris = sorted(kandidater)[len(kandidater) // 2]

    alder_ar = _ar_sedan_arsmodell(arsmodell)
    forvantat_mil = alder_ar * FORVANTAT_MIL_PER_AR
    mil_avvikelse = bil.get("miltal", forvantat_mil) - forvantat_mil
    mil_justering = -mil_avvikelse * KR_PER_MIL_AVVIKELSE

    utrustning = (bil.get("utrustningsniva") or "").strip().lower()
    utrustning_justering = UTRUSTNINGSNIVA_JUSTERING.get(utrustning, 0)

    tillval = 0
    if bil.get("dragkrok"):
        tillval += DRAGKROK_VARDE
    if bil.get("varmare"):
        tillval += VARMARE_VARDE
    if bil.get("volvo_selekt"):
        tillval += SELEKT_VARDE
    if bil.get("stor_batteri"):
        tillval += STOR_BATTERI_VARDE

    marknadsvarde = baspris + mil_justering + utrustning_justering + tillval
    return round(marknadsvarde / 1000) * 1000  # avrunda till närmsta tusental


def berakna_fynd(bil: dict) -> dict:
    """Returnerar dict med marknadsvarde, diff (kr under marknad) och nivå."""
    marknadsvarde = berakna_marknadsvarde(bil)
    annonspris = bil.get("annonspris", 0)
    diff = marknadsvarde - annonspris  # positivt = bra fynd

    if diff >= 35000:
        niva = "EXTREMT_FYND"
    elif diff >= 20000:
        niva = "FYND"
    else:
        niva = None

    return {
        "marknadsvarde": marknadsvarde,
        "diff": diff,
        "niva": niva,
    }
