"""
Konfiguration för bilfyndfiltret.
Justera fritt utan att röra övrig kod.
"""

# --- Grundkrav (gäller alla bilar nedan) ---

ARSMODELL_MIN = 2022
ARSMODELL_MAX = 2024

MIN_MIL = 1000
MAX_MIL = 12000
VAXELLADA = "Automat"
UTESLUT_SKADAD = True


# --- Bilar att bevaka ---
#
# Varje bil kan ha ett eget årsintervall:
#
#   arsmodell_min
#   arsmodell_max
#
# Om dessa saknas används de globala ARSMODELL_MIN/MAX ovan.
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

        "bilweb_modell_slug": "330",

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


# --- Fyndnivåer ---

FYND_TROSKEL = 20000
EXTREMT_FYND_TROSKEL = 35000


# --- Prissänkning ---

MIN_DAGAR_FOR_SANKNING_RELEVANT = 14
STOR_SANKNING_KR = 15000


# --- Notifiering ---

NOTIS_METOD = "epost"

EPOST_TILL = "ronnie.engstrand@gmail.com"
EPOST_FRAN = "ronnie.engstrand@gmail.com"

SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587


# --- Källor att skanna ---

AKTIVA_KALLOR = [
    "wayke",
    "bilweb",
]


# --- Sökordslistor ---

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


# --- Filväg för state ---

STATE_FIL = "data/state.json"
