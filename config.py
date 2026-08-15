"""
Konfiguration för bilfyndfiltret.
Justera fritt utan att röra övrig kod.
"""

# --- Grundkrav (gäller alla bilar nedan) ---
ARSMODELL_MIN = 2022
ARSMODELL_MAX = 2024
MAX_MIL = 12000
VAXELLADA = "Automat"
UTESLUT_SKADAD = True  # filtrera bort skadade/repobjekt

# --- Bilar att bevaka ---
# Varje post beskriver en märke/modell-kombination att söka efter.
#
# wayke_anchor: den exakta text som står direkt efter "I lager" på Wayke
#   (t.ex. "Volvo V60" eller "BMW 530e xDrive Touring") - används som
#   ankare för att hitta annonsblock i sidtexten.
# variant_kraven: dict där nyckeln är visningsnamnet för varianten och
#   värdet är en lista regex-mönster som ALLA måste matcha annonstiteln
#   (efter ankaret) för att varianten ska räknas. Om Wayke/Bilweb-sökningen
#   redan är helt variant-specifik (som BMW:s 530e-xdrive-touring-slug på
#   Wayke) räcker ett enda löst mönster som i praktiken alltid matchar.
# bilweb_modell_slug: modell-delen av bilweb.se/sok/{marke}/{modell}/kombi.
#   Kan skilja sig från wayke-sluggen eftersom Bilweb ofta bara har
#   grövre modellgrupper (t.ex. "530" istället för "530e-xdrive-touring").
BILAR = [
    {
        "marke_slug": "volvo", "marke_visning": "Volvo",
        "modell_slug": "v60", "modell_visning": "V60",
        "wayke_anchor": "Volvo V60",
        "bilweb_modell_slug": "v60",
        "variant_kraven": {
            "T6 AWD": [r"\bt6\b"],
            "T8 AWD": [r"\bt8\b"],
        },
    },
    {
        "marke_slug": "volvo", "marke_visning": "Volvo",
        "modell_slug": "v90", "modell_visning": "V90",
        "wayke_anchor": "Volvo V90",
        "bilweb_modell_slug": "v90",
        "variant_kraven": {
            "T6 AWD": [r"\bt6\b"],
            "T8 AWD": [r"\bt8\b"],
        },
    },
    {
        "marke_slug": "bmw", "marke_visning": "BMW",
        "modell_slug": "530e-xdrive-touring", "modell_visning": "530e xDrive Touring",
        "wayke_anchor": "BMW 530e xDrive Touring",
        # Bilweb saknar en variant-specifik slug för just 530e xDrive Touring,
        # så vi söker på den bredare "530"-gruppen (blandar in 530i/530d/mild-
        # hybrid) och filtrerar bort allt som inte matchar variant_kraven.
        "bilweb_modell_slug": "530",
        "variant_kraven": {
            "530e xDrive Touring": [r"530.?e", r"xdrive", r"touring"],
        },
    },
]

# --- Fyndnivåer (kr under beräknat marknadsvärde) ---
FYND_TROSKEL = 20000        # 🔥 FYND
EXTREMT_FYND_TROSKEL = 35000  # 🚨 EXTREMT FYND

# --- Prissänkning ---
# En prissänkning som skett efter minst så här många dagar räknas som
# "riktig" signal (bilen har testat marknaden och inte sålts)
MIN_DAGAR_FOR_SANKNING_RELEVANT = 14
STOR_SANKNING_KR = 15000

# --- Notifiering ---
NOTIS_METOD = "epost"  # "epost" | "logg"
EPOST_TILL = "ronnie.engstrand@gmail.com"       # mottagaradress
EPOST_FRAN = "ronnie.engstrand@gmail.com"  # skickande konto (Gmail-app-lösenord i secret EPOST_LOSENORD)
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587

# --- Källor att skanna ---
# blocket: ej verifierad, aktivt bot-skydd (Datadome) - avaktiverad som standard
# bytbil: ej verifierad denna session - avaktiverad som standard
# wayke, bilweb: verifierade 2026-08-09, fungerar med requests (ingen JS krävs)
AKTIVA_KALLOR = ["wayke", "bilweb"]

# --- Sökordslistor som markerar "hyrbil/företagsbil" resp. "Volvo Selekt" ---
HYRBIL_NYCKELORD = ["hyrbil", "bilpool", "leasingbil", "tjänstebil", "flikbil"]
SELEKT_NYCKELORD = ["volvo selekt", "selekt"]

# --- Filväg för att spara historik/state mellan körningar ---
STATE_FIL = "data/state.json"
