"""
Konfiguration för bilfyndfiltret.
Justera fritt utan att röra övrig kod.
"""

import os


# --- Grundkrav (gäller alla bilar nedan) ---

ARSMODELL_MIN = 2022
ARSMODELL_MAX = 2026

MIN_MIL = 1000
MAX_MIL = 12000
VAXELLADA = "Automat"
UTESLUT_SKADAD = True


# --- Bilar att bevaka ---

BILAR = [
    {
        "marke_slug": "volvo",
        "marke_visning": "Volvo",
        "modell_slug": "v60",
        "modell_visning": "V60",
        "wayke_anchor": "Volvo V60",
        "bilweb_modell_slug": "v60",
        "arsmodell_min": 2023,
        "arsmodell_max": 2026,
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
        "arsmodell_min": 2023,
        "arsmodell_max": 2026,
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
        "arsmodell_min": 2024,
        "arsmodell_max": 2024,
        "variant_kraven": {
            "530e xDrive Touring": [
                r"530.?e",
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
            ],
        },
    },
]


FYND_TROSKEL = 20000
EXTREMT_FYND_TROSKEL = 35000

MIN_DAGAR_FOR_SANKNING_RELEVANT = 14
STOR_SANKNING_KR = 15000

NOTIS_METOD = "epost"
EPOST_TILL = "ronnie.engstrand@gmail.com"
EPOST_FRAN = "ronnie.engstrand@gmail.com"
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587


AKTIVA_KALLOR = [
    "wayke",
    "bilweb",
]


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


STATE_FIL = "data/state.json"


# --- Historik ---

# Katalog för den nya månadsvis roterade historiken.
#
# Exempel:
#   data/market_history/market_history_2026-08.jsonl
#
# analysis_storage.py använder denna katalog för både
# skrivning och läsning av historiken.
HISTORIK_KATALOG = "data/market_history"

# Äldre historikfil som används vid migrering till den
# månadsvis roterade strukturen.
#
# Denna fil ska inte längre användas som aktiv skrivfil.
HISTORIK_FIL = "data/market_history/market_history.jsonl"

HISTORIK_SPARA_VARJE_KORNING = True


# --- Notifiering ---

# En redan notifierad bil får en ny notis först när priset är minst
# 10 000 kr lägre än den prisnivå som låg till grund för senaste notisen.
MIN_PRISSANKNING_FOR_NY_NOTIS = 10000


# ------------------------------------------------------------
# DEBUG
# ------------------------------------------------------------

# DEBUG styrs via miljövariabeln DEBUG.
#
# Vanlig körning:
#   DEBUG saknas -> False
#
# Debug-körning:
#   DEBUG=true -> True
#
# När DEBUG=True körs hela kandidatpipen men inga mejl skickas.
# Notifieringsstate markeras inte heller.
DEBUG = os.getenv(
    "DEBUG",
    "false",
).lower() == "true"
