"""
Konfiguration för V60/V90-fyndfiltret.
Justera fritt utan att röra övrig kod.
"""

# --- Grundkrav ---
# Modeller att bevaka - slug matchar sökvägen på Wayke/Bilweb
# (wayke.se/sok/volvo/{slug}/{år}, bilweb.se/sok/volvo/{slug}/kombi)
MODELLER = ["v60", "v90"]
VARIANT_KRAV = ["T6 AWD", "T8 AWD"]  # accepterade drivlinor (Recharge) - samma för båda modellerna
ARSMODELL_MIN = 2022
ARSMODELL_MAX = 2024
MAX_MIL = 12000
VAXELLADA = "Automat"
UTESLUT_SKADAD = True  # filtrera bort skadade/repobjekt

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
