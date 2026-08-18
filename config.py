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
#
# Varje bil kan ha ett eget årsintervall:
#
#   arsmodell_min
#   arsmodell_max
#
# Om dessa saknas används de globala ARSMODELL_MIN/MAX ovan.
#
# wayke_anchor:
#   Den exakta text som står direkt efter "I lager" på Wayke.
#
# variant_kraven:
#   Regex-mönster som ALLA måste matcha för att varianten ska räknas.
#
# bilweb_modell_slug:
#   Modell-delen av Bilwebs sök-URL.
#
BILAR = [

    {
        "marke_slug": "volvo",
        "marke_visning": "Volvo",

        "modell_slug": "v60",
        "modell_visning": "V60",

        "wayke_anchor": "Volvo V60",
        "bilweb_modell_slug": "v60",

        "arsmodell_min": 2022,
        "arsmodell_max": 2024,

        "variant_kraven": {
            "T6 AWD": [
                r"\bt6\b",
            ],
            "T8 AWD": [
                r"\bt8\b",
            ],
        },
    },

    {
        "marke_slug": "volvo",
        "marke_visning": "Volvo",

        "modell_slug": "v90",
        "modell_visning": "V90",

        "wayke_anchor": "Volvo V90",
        "bilweb_modell_slug": "v90",

        "arsmodell_min": 2022,
        "arsmodell_max": 2024,

        "variant_kraven": {
            "T6 AWD": [
                r"\bt6\b",
            ],
            "T8 AWD": [
                r"\bt8\b",
            ],
        },
    },

    {
        "marke_slug": "bmw",
        "marke_visning": "BMW",

        "modell_slug": "530e-xdrive-touring",
        "modell_visning": "530e xDrive Touring",

        "wayke_anchor": "BMW 530e xDrive Touring",

        # Bilweb saknar en variant-specifik slug för just
        # 530e xDrive Touring.
        #
        # Därför söker vi på den bredare "530"-gruppen och
        # filtrerar därefter på variant_kraven.
        "bilweb_modell_slug": "530",

        "arsmodell_min": 2022,
        "arsmodell_max": 2024,

        "variant_kraven": {
            "530e xDrive Touring": [
                r"530.?e",
                r"xdrive",
                r"touring",
            ],
        },
    },

    {
        "marke_slug": "bmw",
        "marke_visning": "BMW",

        "modell_slug": "330e-xdrive-touring",
        "modell_visning": "330e xDrive Touring",

        "wayke_anchor": "BMW 330e xDrive Touring",

        # Bilweb har en bredare 330-grupp.
        # Vi filtrerar därför på 330e + xDrive + Touring.
        "bilweb_modell_slug": "330",

        # Den här modellen vill vi bevaka från och med 2024.
        "arsmodell_min": 2024,
        "arsmodell_max": 2026,

        "variant_kraven": {
            "330e xDrive Touring": [
                r"330.?e",
                r"xdrive",
                r"touring",
            ],
        },
    },
]


# --- Fyndnivåer (kr under beräknat marknadsvärde) ---

FYND_TROSKEL = 20000
EXTREMT_FYND_TROSKEL = 35000


# --- Prissänkning ---

# En prissänkning som skett efter minst så här många dagar räknas
# som "riktig" signal (bilen har testat marknaden och inte sålts).

MIN_DAGAR_FOR_SANKNING_RELEVANT = 14
STOR_SANKNING_KR = 15000


# --- Notifiering ---

NOTIS_METOD = "epost"

EPOST_TILL = "ronnie.engstrand@gmail.com"
EPOST_FRAN = "ronnie.engstrand@gmail.com"

SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587


# --- Källor att skanna ---

# blocket: ej verifierad, aktivt bot-skydd (Datadome)
# bytbil: ej verifierad denna session
# wayke, bilweb: verifierade och aktiva

AKTIVA_KALLOR = [
    "wayke",
    "bilweb",
]


# --- Sökordslistor som markerar "hyrbil/företagsbil"
#     resp. "Volvo Selekt" ---

HYRBIL_NYCKELORD = [
    "hyrbil",
    "bilpool",
    "leasingbil",
    "tjänstebil",
    "flikbil",
]

SELEKT_NYCKELORD = [
    "volvo selekt",
    "selekt",
]


# --- Filväg för att spara historik/state mellan körningar ---

STATE_FIL = "data/state.json"
