"""
Dubblettkontroll mellan källor.

Samma bil annonseras ofta på flera sajter samtidigt
(t.ex. Wayke speglar ofta Blocket/Bilweb).

Målet är att identifiera samma FYSISKA bil och endast räkna
den en gång.

Matchningen sker i flera nivåer:

1. Registreringsnummer
2. VIN/chassinummer
3. Stark kombination av bilens egenskaper
4. Poängbaserad fuzzy matching

Fingerprinten är avsiktligt konservativ:

    Det är bättre att missa en osäker dubblett än att slå ihop
    två olika bilar.

Viktiga principer:

- Regnr och VIN är starkaste identifierarna.
- Modell måste matcha vid fingerprint-matchning.
- Olika årsmodell är en konflikt när båda källorna anger årsmodell.
- Saknad årsmodell är däremot inte en konflikt.
- Första registrering är en mycket stark signal.
- Miltal är en stark signal.
- Variant är en stark signal när den finns i båda annonserna.
- Pris är en svag signal.
- Utrustning används endast när båda källorna faktiskt anger information.
- Identiska annonser ska inte behandlas som osäkra fuzzy-matchningar.
- Dubblettgrupper använder en stabil representant för att undvika
  transitiv "chain matching".
- Diagnostik skrivs till loggen så att matchningskvaliteten kan
  verifieras i GitHub Actions.

VIKTIGT om basannonsen (basbil):

    "Mest komplett" och "mest aktuell" är INTE samma sak.

    Statiska fält (regnr, vin, utrustningsniva, dragkrok, m.fl.)
    ändras normalt inte mellan omskrapningar av samma annons, så
    fullständighetspoängen blir ofta lika mellan flera observationer
    av samma bil. Python's max() väljer då konsekvent den FÖRSTA
    posten vid oavgjort - i praktiken den kronologiskt äldsta
    observationen.

    Volatila fält (annonspris, miltal, timestamp) måste därför alltid
    hämtas från den SENASTE observationen i gruppen, oavsett vilken
    post som används som bas för de statiska fälten. Annars riskerar
    både ML-träningsdata och fyndbedömning att jobba med inaktuellt
    pris efter en prissänkning.

Alla numeriska och textbaserade signaler normaliseras innan matchning.
"""

from __future__ import annotations

from app_logging.logger import info

import re
import unicodedata
from datetime import datetime
from difflib import SequenceMatcher


# ---------------------------------------------------------------------------
# Grundparametrar
# ---------------------------------------------------------------------------

MIL_MARGINAL = 300
PRIS_MARGINAL = 5000

# Minsta poäng för automatisk fingerprint-dubblett.
MATCHNINGSGRANS = 82

# Säker identifierare.
SIKER_MATCHNING = 100

# När variant saknas på ena sidan krävs flera oberoende starka signaler.
MINSTA_STARKA_SIGNALER = 3

# Fingerprint-matchningar under denna nivå loggas som REVIEW.
REVIEW_SCORE_GRANS = 90

# Fält som förväntas ändras mellan omskrapningar av samma annons.
# Dessa ska ALLTID hämtas från den senaste observationen i gruppen,
# oavsett vilken post som i övrigt används som bas (se _senaste_bil).
VOLATILA_FALT = (
    "annonspris",
    "miltal",
    "timestamp",
)


# ---------------------------------------------------------------------------
# Normalisering
# ---------------------------------------------------------------------------


def _normalisera_text(value) -> str:
    """
    Normaliserar text för jämförelse.

    Exempel:

        "V60 T6 AWD Recharge"
        "v60-t6 awd recharge"

    blir i praktiken samma jämförelsetext.
    """

    if value is None:
        return ""

    text = str(value).strip().lower()

    text = unicodedata.normalize(
        "NFKD",
        text,
    )

    text = "".join(
        c
        for c in text
        if not unicodedata.combining(c)
    )

    text = text.replace(
        "&",
        " och ",
    )

    text = re.sub(
        r"[/_|(),;:+\-]+",
        " ",
        text,
    )

    text = re.sub(
        r"[^\w\s]",
        " ",
        text,
    )

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text.strip()


def _normalisera_regnr(value) -> str:
    """Normaliserar registreringsnummer."""

    if not value:
        return ""

    return re.sub(
        r"[^A-Za-z0-9]",
        "",
        str(value),
    ).upper()


def _normalisera_vin(value) -> str:
    """Normaliserar VIN/chassinummer."""

    if not value:
        return ""

    return re.sub(
        r"[^A-Za-z0-9]",
        "",
        str(value),
    ).upper()


def _normalisera_variant(value) -> str:
    """
    Normaliserar variantnamn.

    Exempel:

        xDrive
        X-Drive
        x drive

    behandlas som samma variantinformation.
    """

    text = _normalisera_text(value)

    # Viktigt: ersätt längre uttryck före kortare uttryck.
    ersattningar = (
        ("x drive", "xdrive"),
        ("4 motion", "4motion"),
        ("plug in", "plugin"),
        ("plug-in", "plugin"),
        ("plug in hybrid", "plugin"),
        ("plug-in hybrid", "plugin"),
    )

    for gammal, ny in ersattningar:
        text = text.replace(
            gammal,
            ny,
        )

    return re.sub(
        r"\s+",
        " ",
        text,
    ).strip()


# ---------------------------------------------------------------------------
# Hjälpfunktioner
# ---------------------------------------------------------------------------


def _numeriskt(value):
    """
    Försöker konvertera värde till float.

    Returnerar None om värdet saknas eller inte är numeriskt.
    """

    if value in (
        None,
        "",
    ):
        return None

    if isinstance(value, bool):
        return None

    try:
        if isinstance(value, str):
            text = value.replace(
                " ",
                "",
            ).replace(
                ",",
                ".",
            )

            text = re.sub(
                r"[^0-9.\-]",
                "",
                text,
            )

            if not text:
                return None

            return float(text)

        return float(value)

    except (
        TypeError,
        ValueError,
    ):
        return None


def _heltal(value):
    """Konverterar numeriskt värde till int där det är möjligt."""

    numeriskt = _numeriskt(value)

    if numeriskt is None:
        return None

    return int(
        round(numeriskt)
    )


def _parse_tidsstampel(value):
    """
    Försöker tolka ett timestamp-fält som datetime.

    Returnerar None om värdet saknas eller inte går att tolka.
    Hanterar bland annat ISO 8601 med tidszon
    (t.ex. "2026-08-18 18:15:11+02:00") samt vanlig "Z"-suffix.
    """

    if value in (
        None,
        "",
    ):
        return None

    if isinstance(value, datetime):
        return value

    text = str(value).strip()

    # datetime.fromisoformat i äldre Python-versioner klarar inte "Z".
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"

    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _textlikhet(a, b) -> float:
    """
    Returnerar 0.0–1.0 beroende på hur lika två texter är.
    """

    a_norm = _normalisera_text(a)
    b_norm = _normalisera_text(b)

    if not a_norm or not b_norm:
        return 0.0

    if a_norm == b_norm:
        return 1.0

    return SequenceMatcher(
        None,
        a_norm,
        b_norm,
    ).ratio()


def _variantlikhet(a, b) -> float:
    """Jämför två variantnamn."""

    a_norm = _normalisera_variant(a)
    b_norm = _normalisera_variant(b)

    if not a_norm or not b_norm:
        return 0.0

    if a_norm == b_norm:
        return 1.0

    return SequenceMatcher(
        None,
        a_norm,
        b_norm,
    ).ratio()


def _bool_finns(
    bil: dict,
    falt: str,
) -> bool:
    """
    Returnerar True endast om fältet uttryckligen innehåller information.

    False betyder alltså inte att vi vet att utrustningen saknas.
    Det kan lika gärna betyda att källan inte anger informationen.
    """

    return bil.get(falt) not in (
        None,
        "",
    )


# ---------------------------------------------------------------------------
# Identisk annons
# ---------------------------------------------------------------------------


def _identisk_annons(
    a: dict,
    b: dict,
) -> bool:
    """
    Kontrollerar om två poster innehåller samma kärndata.

    Detta används främst för diagnostik.

    Om samma post förekommer flera gånger i insamlingen ska den inte
    presenteras som en osäker fuzzy-matchning.

    Regnr/VIN hanteras separat eftersom de kan vara saknade.
    """

    modell_a = _normalisera_text(
        a.get("modell")
    )
    modell_b = _normalisera_text(
        b.get("modell")
    )

    variant_a = _normalisera_variant(
        a.get("variant")
    )
    variant_b = _normalisera_variant(
        b.get("variant")
    )

    if (
        not modell_a
        or not modell_b
        or modell_a != modell_b
    ):
        return False

    arsmodell_a = _arsmodell(a)
    arsmodell_b = _arsmodell(b)

    if (
        arsmodell_a is not None
        and arsmodell_b is not None
        and arsmodell_a != arsmodell_b
    ):
        return False

    if (
        variant_a
        and variant_b
        and variant_a != variant_b
    ):
        return False

    mil_a = _numeriskt(
        a.get("miltal")
    )
    mil_b = _numeriskt(
        b.get("miltal")
    )

    if (
        mil_a is not None
        and mil_b is not None
        and abs(mil_a - mil_b) > 1
    ):
        return False

    pris_a = _numeriskt(
        a.get("annonspris")
    )
    pris_b = _numeriskt(
        b.get("annonspris")
    )

    if (
        pris_a is not None
        and pris_b is not None
        and abs(pris_a - pris_b) > 1
    ):
        return False

    regnr_a = _normalisera_regnr(
        a.get("regnr")
    )
    regnr_b = _normalisera_regnr(
        b.get("regnr")
    )

    if (
        regnr_a
        and regnr_b
        and regnr_a != regnr_b
    ):
        return False

    vin_a = _hamta_vin(a)
    vin_b = _hamta_vin(b)

    if (
        vin_a
        and vin_b
        and not vin_a.intersection(vin_b)
    ):
        return False

    datum_a = _normalisera_text(
        a.get("forsta_registrering")
    )
    datum_b = _normalisera_text(
        b.get("forsta_registrering")
    )

    if (
        datum_a
        and datum_b
        and datum_a != datum_b
    ):
        return False

    return True


# ---------------------------------------------------------------------------
# Identifierare
# ---------------------------------------------------------------------------


def _regnr_matchar(
    a: dict,
    b: dict,
) -> bool:
    """Kontrollerar registreringsnummer."""

    regnr_a = _normalisera_regnr(
        a.get("regnr")
    )

    regnr_b = _normalisera_regnr(
        b.get("regnr")
    )

    if not regnr_a or not regnr_b:
        return False

    return regnr_a == regnr_b


def _hamta_vin(bil: dict) -> set[str]:
    """
    Hämtar alla VIN/chassinummer som finns i en annons.

    Olika scrapers/källor kan använda olika fältnamn.
    """

    vin_falt = (
        "vin",
        "chassinummer",
        "chassinr",
        "vin_nummer",
    )

    resultat = set()

    for falt in vin_falt:
        vin = _normalisera_vin(
            bil.get(falt)
        )

        if vin:
            resultat.add(vin)

    return resultat


def _vin_matchar(
    a: dict,
    b: dict,
) -> bool:
    """
    Kontrollerar VIN/chassinummer.

    Alla kända VIN-fält på respektive annons jämförs mot varandra.
    """

    vin_a = _hamta_vin(a)
    vin_b = _hamta_vin(b)

    if not vin_a or not vin_b:
        return False

    return bool(
        vin_a.intersection(vin_b)
    )


# ---------------------------------------------------------------------------
# Modell
# ---------------------------------------------------------------------------


def _modell_matchar(
    a: dict,
    b: dict,
) -> bool:
    """
    Modell måste matcha.

    V60 får exempelvis aldrig matchas mot V90 bara för att
    årsmodell, miltal och pris råkar vara lika.
    """

    modell_a = _normalisera_text(
        a.get("modell")
    )

    modell_b = _normalisera_text(
        b.get("modell")
    )

    if not modell_a or not modell_b:
        return False

    return modell_a == modell_b


# ---------------------------------------------------------------------------
# Årsmodell
# ---------------------------------------------------------------------------


def _arsmodell(
    bil: dict,
):
    """Returnerar årsmodell som int eller None."""

    return _heltal(
        bil.get("arsmodell")
    )


def _arsmodell_matchar(
    a: dict,
    b: dict,
) -> bool:
    """
    Kontrollerar årsmodell.

    Returnerar False om någon årsmodell saknas.
    Använd _arsmodell_konfliktar() när det ska avgöras om
    skillnaden faktiskt är en blockerande konflikt.
    """

    arsmodell_a = _arsmodell(a)
    arsmodell_b = _arsmodell(b)

    if (
        arsmodell_a is None
        or arsmodell_b is None
    ):
        return False

    return arsmodell_a == arsmodell_b


def _arsmodell_konfliktar(
    a: dict,
    b: dict,
) -> bool:
    """
    Returnerar True endast när båda källorna anger årsmodell
    och de faktiskt skiljer sig.

    Saknad information är inte en konflikt.
    """

    arsmodell_a = _arsmodell(a)
    arsmodell_b = _arsmodell(b)

    if (
        arsmodell_a is None
        or arsmodell_b is None
    ):
        return False

    return arsmodell_a != arsmodell_b


# ---------------------------------------------------------------------------
# Första registrering
# ---------------------------------------------------------------------------


def _forsta_registrering_matchar(
    a: dict,
    b: dict,
) -> bool:
    """
    Jämför första registreringsdatum.

    Textnormalisering används eftersom olika källor kan skriva
    datum på olika sätt.
    """

    datum_a = _normalisera_text(
        a.get("forsta_registrering")
    )

    datum_b = _normalisera_text(
        b.get("forsta_registrering")
    )

    if not datum_a or not datum_b:
        return False

    return datum_a == datum_b


# ---------------------------------------------------------------------------
# Miltal
# ---------------------------------------------------------------------------


def _miltal_likhet(
    a: dict,
    b: dict,
) -> float:
    """
    Ger 0–1 baserat på hur nära miltalen ligger.

    <= 50 mil   : 1.00
    <= 100 mil  : 0.95–1.00
    <= 300 mil  : gradvis avtagande
    > 300 mil   : 0
    """

    mil_a = _numeriskt(
        a.get("miltal")
    )

    mil_b = _numeriskt(
        b.get("miltal")
    )

    if (
        mil_a is None
        or mil_b is None
    ):
        return 0.0

    skillnad = abs(
        mil_a - mil_b
    )

    if skillnad <= 50:
        return 1.0

    if skillnad <= 100:
        return 0.95

    if skillnad > MIL_MARGINAL:
        return 0.0

    return 0.95 - (
        (
            skillnad - 100
        )
        / (
            MIL_MARGINAL - 100
        )
    ) * 0.95


# ---------------------------------------------------------------------------
# Pris
# ---------------------------------------------------------------------------


def _pris_likhet(
    a: dict,
    b: dict,
) -> float:
    """
    Ger 0–1 baserat på prisskillnad.

    Pris är en svag signal eftersom samma bil kan vara publicerad
    med olika pris på olika sajter.
    """

    pris_a = _numeriskt(
        a.get("annonspris")
    )

    pris_b = _numeriskt(
        b.get("annonspris")
    )

    if (
        pris_a is None
        or pris_b is None
    ):
        return 0.0

    skillnad = abs(
        pris_a - pris_b
    )

    if skillnad <= 1000:
        return 1.0

    if skillnad > PRIS_MARGINAL:
        return 0.0

    return 1.0 - (
        (
            skillnad - 1000
        )
        / (
            PRIS_MARGINAL - 1000
        )
    ) * 0.5


# ---------------------------------------------------------------------------
# Utrustning
# ---------------------------------------------------------------------------


def _utrustningssignal(
    a: dict,
    b: dict,
) -> tuple[int, int]:
    """
    Returnerar:

        (antal_matchande_kända_fält, antal_kända_fält)

    Endast fält där båda annonserna faktiskt innehåller information
    används.

    Saknad information behandlas inte som konflikt.
    """

    falt = [
        "utrustningsniva",
        "dragkrok",
        "varmare",
        "volvo_selekt",
        "stor_batteri",
        "antal_agare",
        "servicehistorik",
        "senaste_service",
        "nasta_service",
        "forsta_registrering",
        "hyrbil",
        "import",
    ]

    matchningar = 0
    kanda = 0

    for falt_namn in falt:

        finns_a = _bool_finns(
            a,
            falt_namn,
        )

        finns_b = _bool_finns(
            b,
            falt_namn,
        )

        if not finns_a or not finns_b:
            continue

        kanda += 1

        va = a.get(falt_namn)
        vb = b.get(falt_namn)

        if (
            isinstance(va, str)
            or isinstance(vb, str)
        ):
            if (
                _normalisera_text(va)
                == _normalisera_text(vb)
            ):
                matchningar += 1

        elif va == vb:
            matchningar += 1

    return (
        matchningar,
        kanda,
    )


# ---------------------------------------------------------------------------
# Fingerprint-score
# ---------------------------------------------------------------------------


def _matchningsscore(
    a: dict,
    b: dict,
) -> tuple[int, dict]:
    """
    Beräknar ett fingerprint-score 0–100.

    Poäng:

        Modell                 blockerande krav
        Årsmodell              15
        Variant                25
        Miltal                 25
        Första registrering    20
        Pris                    3
        Utrustning              7
        Övriga signaler         5

    Totalt: 100 poäng.

    Regnr och VIN hanteras separat som säkra identifierare.

    Den nya viktningen gör framför allt årsmodell, variant, miltal
    och första registrering till de bärande signalerna.

    Pris får endast mycket liten påverkan.
    """

    # -------------------------------------------------------
    # Modell är blockerande.
    # -------------------------------------------------------

    if not _modell_matchar(a, b):
        return 0, {
            "orsak": "olika_modell",
        }

    # -------------------------------------------------------
    # Årsmodell är blockerande endast när båda är kända
    # och faktiskt skiljer sig.
    # -------------------------------------------------------

    if _arsmodell_konfliktar(a, b):
        return 0, {
            "orsak": "olika_arsmodell",
        }

    score = 0

    detaljer = {
        "modell": True,
        "arsmodell": False,
        "arsmodell_kand_a": _arsmodell(a) is not None,
        "arsmodell_kand_b": _arsmodell(b) is not None,
        "variantlikhet": 0.0,
        "miltallikhet": 0.0,
        "forsta_registrering": False,
        "prislikhet": 0.0,
        "utrustningsmatchningar": 0,
        "utrustningskanda": 0,
        "extra_score": 0,
        "extra_max": 0,
    }

    # -------------------------------------------------------
    # Årsmodell: 15 poäng
    # -------------------------------------------------------

    if _arsmodell_matchar(a, b):
        score += 15
        detaljer["arsmodell"] = True

    # -------------------------------------------------------
    # Variant: 25 poäng
    # -------------------------------------------------------

    variant_a = _normalisera_variant(
        a.get("variant")
    )

    variant_b = _normalisera_variant(
        b.get("variant")
    )

    variantlikhet = _variantlikhet(
        a.get("variant"),
        b.get("variant"),
    )

    detaljer["variantlikhet"] = variantlikhet

    if variant_a and variant_b:

        if variantlikhet >= 0.95:
            score += 25

        elif variantlikhet >= 0.90:
            score += 23

        elif variantlikhet >= 0.80:
            score += 18

        elif variantlikhet >= 0.70:
            score += 10

        elif variantlikhet >= 0.60:
            score += 5

    # -------------------------------------------------------
    # Miltal: 25 poäng
    # -------------------------------------------------------

    miltallikhet = _miltal_likhet(
        a,
        b,
    )

    detaljer["miltallikhet"] = miltallikhet

    score += round(
        miltallikhet * 25
    )

    # -------------------------------------------------------
    # Första registrering: 20 poäng
    # -------------------------------------------------------

    if _forsta_registrering_matchar(
        a,
        b,
    ):
        score += 20
        detaljer[
            "forsta_registrering"
        ] = True

    # -------------------------------------------------------
    # Pris: endast 3 poäng
    # -------------------------------------------------------

    prislikhet = _pris_likhet(
        a,
        b,
    )

    detaljer["prislikhet"] = prislikhet

    score += round(
        prislikhet * 3
    )

    # -------------------------------------------------------
    # Utrustning: 7 poäng
    # -------------------------------------------------------

    matchningar, kanda = _utrustningssignal(
        a,
        b,
    )

    detaljer[
        "utrustningsmatchningar"
    ] = matchningar

    detaljer[
        "utrustningskanda"
    ] = kanda

    if kanda:
        utrustningspoang = (
            matchningar
            / kanda
        ) * 7

        score += round(
            utrustningspoang
        )

    # -------------------------------------------------------
    # Övriga signaler: 5 poäng
    # -------------------------------------------------------

    extra_score = 0
    extra_max = 0

    # Antal ägare.
    if (
        a.get("antal_agare") is not None
        and b.get("antal_agare") is not None
    ):
        extra_max += 1

        if (
            _heltal(
                a.get("antal_agare")
            )
            == _heltal(
                b.get("antal_agare")
            )
        ):
            extra_score += 1

    # Dragkrok.
    if (
        a.get("dragkrok") is not None
        and b.get("dragkrok") is not None
    ):
        extra_max += 1

        if (
            bool(a.get("dragkrok"))
            == bool(b.get("dragkrok"))
        ):
            extra_score += 1

    # Värmare.
    if (
        a.get("varmare") is not None
        and b.get("varmare") is not None
    ):
        extra_max += 1

        if (
            bool(a.get("varmare"))
            == bool(b.get("varmare"))
        ):
            extra_score += 1

    # Stor batteriversion.
    if (
        a.get("stor_batteri") is not None
        and b.get("stor_batteri") is not None
    ):
        extra_max += 1

        if (
            bool(a.get("stor_batteri"))
            == bool(b.get("stor_batteri"))
        ):
            extra_score += 1

    # Volvo Selekt.
    if (
        a.get("volvo_selekt") is not None
        and b.get("volvo_selekt") is not None
    ):
        extra_max += 1

        if (
            bool(a.get("volvo_selekt"))
            == bool(b.get("volvo_selekt"))
        ):
            extra_score += 1

    if extra_max:
        score += round(
            (
                extra_score
                / extra_max
            ) * 5
        )

    detaljer["extra_score"] = extra_score
    detaljer["extra_max"] = extra_max

    return min(
        100,
        score,
    ), detaljer


# ---------------------------------------------------------------------------
# Matchningstyp
# ---------------------------------------------------------------------------


def _matchningstyp(
    a: dict,
    b: dict,
) -> str:
    """
    Returnerar vilken typ av identifiering som användes.
    """

    if _regnr_matchar(a, b):
        return "regnr"

    if _vin_matchar(a, b):
        return "vin"

    return "fingerprint"


# ---------------------------------------------------------------------------
# Huvudmatchning
# ---------------------------------------------------------------------------


def _matchar(
    a: dict,
    b: dict,
) -> bool:
    """
    Avgör om två annonser sannolikt avser samma fysiska bil.

    Prioritetsordning:

        1. Regnr
        2. VIN
        3. Fingerprint-score

    Fingerprint-matchningen är konservativ.
    """

    # -------------------------------------------------------
    # 1. Registreringsnummer
    # -------------------------------------------------------

    if _regnr_matchar(a, b):
        return True

    # -------------------------------------------------------
    # 2. VIN/chassinummer
    # -------------------------------------------------------

    if _vin_matchar(a, b):
        return True

    # -------------------------------------------------------
    # Modell måste finnas och matcha.
    # -------------------------------------------------------

    if not _modell_matchar(a, b):
        return False

    # -------------------------------------------------------
    # Olika kända årsmodeller är en hård konflikt.
    # -------------------------------------------------------

    if _arsmodell_konfliktar(a, b):
        return False

    # -------------------------------------------------------
    # Fingerprint.
    # -------------------------------------------------------

    score, detaljer = _matchningsscore(
        a,
        b,
    )

    # -------------------------------------------------------
    # Skydd mot för svag matchning när variant saknas.
    # -------------------------------------------------------

    variant_a = _normalisera_variant(
        a.get("variant")
    )

    variant_b = _normalisera_variant(
        b.get("variant")
    )

    if not variant_a or not variant_b:

        starka_signaler = 0

        # Samma kända årsmodell.
        if _arsmodell_matchar(a, b):
            starka_signaler += 1

        # Mycket likt miltal.
        if (
            detaljer.get(
                "miltallikhet",
                0,
            )
            >= 0.75
        ):
            starka_signaler += 1

        # Mycket likt pris.
        if (
            detaljer.get(
                "prislikhet",
                0,
            )
            >= 0.75
        ):
            starka_signaler += 1

        # Samma första registrering.
        if detaljer.get(
            "forsta_registrering",
            False,
        ):
            starka_signaler += 2

        # Minst två matchande utrustningsfält.
        if (
            detaljer.get(
                "utrustningsmatchningar",
                0,
            )
            >= 2
        ):
            starka_signaler += 1

        if (
            starka_signaler
            < MINSTA_STARKA_SIGNALER
        ):
            return False

    # -------------------------------------------------------
    # Slutlig gräns.
    # -------------------------------------------------------

    return score >= MATCHNINGSGRANS


# ---------------------------------------------------------------------------
# Diagnostik
# ---------------------------------------------------------------------------


def fingerprint_score(
    a: dict,
    b: dict,
) -> dict:
    """
    Returnerar detaljerad diagnostik.

    Exempel:

        {
            "matchar": True,
            "score": 94,
            "confidence": 94,
            "orsak": "fingerprint",
            "matchningstyp": "fingerprint",
            "detaljer": {...}
        }
    """

    if _regnr_matchar(a, b):
        return {
            "matchar": True,
            "score": SIKER_MATCHNING,
            "confidence": SIKER_MATCHNING,
            "orsak": "regnr",
            "matchningstyp": "regnr",
            "detaljer": {},
        }

    if _vin_matchar(a, b):
        return {
            "matchar": True,
            "score": SIKER_MATCHNING,
            "confidence": SIKER_MATCHNING,
            "orsak": "vin",
            "matchningstyp": "vin",
            "detaljer": {},
        }

    # Identiska poster ska betraktas som säkra matchningar
    # för diagnostikens skull. Detta påverkar inte själva
    # gruppindelningen.
    if _identisk_annons(a, b):
        return {
            "matchar": True,
            "score": SIKER_MATCHNING,
            "confidence": SIKER_MATCHNING,
            "orsak": "identisk_annons",
            "matchningstyp": "fingerprint",
            "detaljer": {
                "identisk_annons": True,
            },
        }

    score, detaljer = _matchningsscore(
        a,
        b,
    )

    matchar = _matchar(
        a,
        b,
    )

    return {
        "matchar": matchar,
        "score": score,
        "confidence": score,
        "orsak": detaljer.get(
            "orsak",
            "fingerprint",
        ),
        "matchningstyp": "fingerprint",
        "detaljer": detaljer,
    }


# ---------------------------------------------------------------------------
# Fullständighet
# ---------------------------------------------------------------------------


def _fullstandighetspoang(
    bil: dict,
) -> int:
    """
    Fler kända fält = mer komplett annons.

    Den mest kompletta annonsen används som bas när flera källor
    identifierats som samma bil - men OBS: endast för de statiska
    fälten. Se _senaste_bil() för volatila fält (pris/miltal/tid).
    """

    falt = [
        "regnr",
        "vin",
        "chassinummer",
        "chassinr",
        "vin_nummer",
        "utrustningsniva",
        "dragkrok",
        "varmare",
        "volvo_selekt",
        "stor_batteri",
        "antal_agare",
        "servicehistorik",
        "senaste_service",
        "nasta_service",
        "forsta_registrering",
        "hyrbil",
        "import",
        "annons_id",
        "miltal",
        "annonspris",
        "variant",
        "arsmodell",
        "modell",
    ]

    return sum(
        1
        for falt_namn in falt
        if bil.get(falt_namn)
        not in (
            None,
            "",
            False,
        )
    )


# ---------------------------------------------------------------------------
# Grupprepresentant
# ---------------------------------------------------------------------------


def _grupprepresentant(
    grupp: list[dict],
) -> dict:
    """
    Väljer en stabil representant för en dubblettgrupp.

    Används för fingerprint-jämförelser (matchning mot nya annonser).
    Vid lika fullständighet används annonsens ursprungliga ordning
    genom max()-beteendet, vilket gör valet stabilt.

    OBS: detta är INTE samma sak som vilken post vars pris/miltal
    som hamnar i slutresultatet - se _senaste_bil() och hur basbil
    byggs i deduplicera().
    """

    return max(
        grupp,
        key=_fullstandighetspoang,
    )


def _senaste_bil(
    grupp: list[dict],
) -> dict:
    """
    Väljer den kronologiskt SENASTE observationen i en grupp,
    baserat på fältet "timestamp".

    Detta används för att hämta aktuella volatila värden
    (annonspris, miltal) till basbilen, oavsett vilken post som
    valdes som representant för de statiska fälten.

    Om ingen post har en tolkbar tidsstämpel faller funktionen
    tillbaka på den sist tillagda posten i listan (ursprunglig
    ordning), vilket i normalfallet fortfarande är den senast
    skrapade.
    """

    senaste = None
    senaste_tid = None

    for bil in grupp:

        tid = _parse_tidsstampel(
            bil.get("timestamp")
        )

        if tid is None:
            continue

        if (
            senaste_tid is None
            or tid >= senaste_tid
        ):
            senaste = bil
            senaste_tid = tid

    if senaste is not None:
        return senaste

    # Fallback: ingen post hade tolkbar tidsstämpel.
    # Använd sista posten i ursprunglig ordning.
    return grupp[-1]


# ---------------------------------------------------------------------------
# Diagnostikformat
# ---------------------------------------------------------------------------


def _bil_beskrivning(
    bil: dict,
) -> str:
    """
    Skapar en kort, läsbar beskrivning för GitHub Actions-loggen.

    Registreringsnummer/VIN skrivs inte ut.
    """

    modell = (
        bil.get("modell")
        or "?"
    )

    variant = (
        bil.get("variant")
        or "?"
    )

    arsmodell = (
        bil.get("arsmodell")
        or "?"
    )

    miltal = (
        bil.get("miltal")
        if bil.get("miltal")
        not in (None, "")
        else "?"
    )

    pris = (
        bil.get("annonspris")
        if bil.get("annonspris")
        not in (None, "")
        else "?"
    )

    kalla = (
        bil.get("kalla")
        or "?"
    )

    return (
        f"{kalla} | "
        f"{modell} | "
        f"{variant} | "
        f"{arsmodell} | "
        f"{miltal} mil | "
        f"{pris} kr"
    )


def _skriv_dedup_logg(
    bilar: list[dict],
    grupper: list[list[dict]],
) -> None:
    """
    Skriver sammanfattande dedup-diagnostik till stdout.

    Endast verkligt intressanta REVIEW-matchningar skrivs ut.

    Identiska poster och säkra identifierare räknas inte som
    osäkra fingerprint-matchningar.
    """

    totalt = len(bilar)
    unika = len(grupper)
    dubbletter = totalt - unika

    if totalt:
        dubblettandel = (
            dubbletter
            / totalt
        ) * 100
    else:
        dubblettandel = 0.0

    info(
        "[DEDUP] =================================================="
    )

    info(
        f"[DEDUP] Före: {totalt} annonser"
    )

    info(
        f"[DEDUP] Efter: {unika} unika bilar"
    )

    info(
        f"[DEDUP] Dubbletter: {dubbletter}"
    )

    info(
        f"[DEDUP] Dubblettandel: {dubblettandel:.1f}%"
    )

    # -------------------------------------------------------
    # Matchningstyper
    # -------------------------------------------------------

    matchningstyper = {
        "regnr": 0,
        "vin": 0,
        "fingerprint": 0,
    }

    fingerprint_scores = []

    review_matchningar = []

    for grupp in grupper:

        if len(grupp) <= 1:
            continue

        representant = _grupprepresentant(
            grupp
        )

        for bil in grupp:

            if bil is representant:
                continue

            diagnostik = fingerprint_score(
                representant,
                bil,
            )

            typ = diagnostik[
                "matchningstyp"
            ]

            # Identiska poster är fingerprint-baserade men
            # ska ändå inte räknas som osäkra.
            if typ in matchningstyper:
                matchningstyper[typ] += 1

            score = diagnostik[
                "score"
            ]

            if typ == "fingerprint":
                fingerprint_scores.append(
                    score
                )

                if (
                    score
                    < REVIEW_SCORE_GRANS
                    and diagnostik.get(
                        "orsak"
                    )
                    != "identisk_annons"
                ):
                    review_matchningar.append(
                        (
                            representant,
                            bil,
                            diagnostik,
                        )
                    )

    info(
        "[DEDUP] MATCHNINGSTYP"
    )

    info(
        f"[DEDUP]   REGNR:       {matchningstyper['regnr']}"
    )

    info(
        f"[DEDUP]   VIN:         {matchningstyper['vin']}"
    )

    info(
        f"[DEDUP]   FINGERPRINT: {matchningstyper['fingerprint']}"
    )

    # -------------------------------------------------------
    # Fingerprint-scorefördelning
    # -------------------------------------------------------

    info(
        "[DEDUP] FINGERPRINT-SCORE"
    )

    score_intervall = {
        "95-100": 0,
        "90-94": 0,
        "85-89": 0,
        "82-84": 0,
    }

    for score in fingerprint_scores:

        if score >= 95:
            score_intervall["95-100"] += 1

        elif score >= 90:
            score_intervall["90-94"] += 1

        elif score >= 85:
            score_intervall["85-89"] += 1

        elif score >= 82:
            score_intervall["82-84"] += 1

    info(
        f"[DEDUP]   95-100: {score_intervall['95-100']}"
    )

    info(
        f"[DEDUP]   90-94:  {score_intervall['90-94']}"
    )

    info(
        f"[DEDUP]   85-89:  {score_intervall['85-89']}"
    )

    info(
        f"[DEDUP]   82-84:  {score_intervall['82-84']}"
    )

    # -------------------------------------------------------
    # Källöverlapp
    # -------------------------------------------------------

    kalloverlapp = {}

    for grupp in grupper:

        kallor = sorted(
            {
                bil.get("kalla")
                for bil in grupp
                if bil.get("kalla")
            }
        )

        if len(kallor) < 2:
            continue

        nyckel = " + ".join(
            kallor
        )

        kalloverlapp[
            nyckel
        ] = (
            kalloverlapp.get(
                nyckel,
                0,
            )
            + 1
        )

    info(
        "[DEDUP] KÄLLÖVERLAPP"
    )

    if kalloverlapp:

        for nyckel, antal in sorted(
            kalloverlapp.items(),
            key=lambda item: (
                -item[1],
                item[0],
            ),
        ):
            info(
                f"[DEDUP]   {nyckel}: {antal}"
            )

    else:

        info(
            "[DEDUP]   inga källöverlapp"
        )

    # -------------------------------------------------------
    # Osäkra fingerprint-matchningar
    # -------------------------------------------------------

    info(
        "[DEDUP] REVIEW-MATCHNINGAR "
        f"(score < {REVIEW_SCORE_GRANS})"
    )

    if review_matchningar:

        review_matchningar.sort(
            key=lambda item: item[2]["score"],
            reverse=True,
        )

        for (
            representant,
            bil,
            diagnostik,
        ) in review_matchningar:

            info(
                "[DEDUP][REVIEW] "
                f"score={diagnostik['score']} | "
                f"{_bil_beskrivning(representant)} "
                f"<-> "
                f"{_bil_beskrivning(bil)}"
            )

    else:

        info(
            "[DEDUP]   inga osäkra fingerprint-matchningar"
        )

    info(
        "[DEDUP] =================================================="
    )


# ---------------------------------------------------------------------------
# Dubblettgruppering
# ---------------------------------------------------------------------------


def deduplicera(
    bilar: list[dict],
) -> list[dict]:
    """
    Slår ihop annonser som sannolikt avser samma fysiska bil.

    För varje grupp:

        - den mest kompletta annonsen används som bas för
          statiska fält (regnr, vin, utrustning, m.fl.)
        - volatila fält (annonspris, miltal, timestamp) hämtas
          alltid från den SENAST skrapade observationen i gruppen,
          oavsett hur fullständig just den posten är
        - alla källor sparas
        - alla URL:er sparas
        - fingerprint-score sparas
        - matchningstyp sparas

    En ny annons jämförs endast mot gruppens stabila representant.
    Detta förhindrar transitiv chain matching.

    Efter gruppering skrivs diagnostik till GitHub Actions-loggen.
    """

    grupper: list[list[dict]] = []

    for bil in bilar:

        placerad = False

        for grupp in grupper:

            representant = _grupprepresentant(
                grupp
            )

            diagnostik = fingerprint_score(
                representant,
                bil,
            )

            if not diagnostik["matchar"]:
                continue

            bil["_fingerprint_score"] = (
                diagnostik["score"]
            )

            bil["_matchningstyp"] = (
                diagnostik["matchningstyp"]
            )

            bil["_matchningsorsak"] = (
                diagnostik["orsak"]
            )

            grupp.append(
                bil
            )

            placerad = True
            break

        if not placerad:

            bil["_fingerprint_score"] = (
                SIKER_MATCHNING
            )

            bil["_matchningstyp"] = (
                "unik"
            )

            bil["_matchningsorsak"] = (
                "ingen_dubblett"
            )

            grupper.append(
                [bil]
            )

    # -----------------------------------------------------------------------
    # Diagnostik
    # -----------------------------------------------------------------------

    _skriv_dedup_logg(
        bilar,
        grupper,
    )

    # -----------------------------------------------------------------------
    # Bygg slutresultat
    # -----------------------------------------------------------------------

    resultat = []

    for grupp in grupper:

        # -------------------------------------------------------
        # Mest kompletta annonsen blir bas för statiska fält.
        # -------------------------------------------------------

        basbil = max(
            grupp,
            key=_fullstandighetspoang,
        ).copy()

        # -------------------------------------------------------
        # Volatila fält (pris, miltal, tidsstämpel) hämtas alltid
        # från den senaste observationen i gruppen - inte från
        # den mest kompletta. Annars riskerar t.ex. en
        # prissänkning att "försvinna" bakom en äldre, lika
        # komplett post.
        #
        # Görs endast när gruppen faktiskt har fler än en post;
        # med en enda post är basbil redan korrekt.
        # -------------------------------------------------------

        if len(grupp) > 1:

            senaste = _senaste_bil(
                grupp
            )

            for falt_namn in VOLATILA_FALT:

                varde = senaste.get(
                    falt_namn
                )

                if varde not in (
                    None,
                    "",
                ):
                    basbil[
                        falt_namn
                    ] = varde

        # -------------------------------------------------------
        # Källor
        # -------------------------------------------------------

        kallor = sorted(
            {
                b.get("kalla")
                for b in grupp
                if b.get("kalla")
            }
        )

        basbil["kallor"] = kallor

        # -------------------------------------------------------
        # URL:er
        # -------------------------------------------------------

        urls = []

        for b in grupp:

            kandidat_urls = (
                b.get("urls")
                or [b.get("url")]
            )

            for url in kandidat_urls:

                if (
                    url
                    and url not in urls
                ):
                    urls.append(
                        url
                    )

        basbil["urls"] = urls

        # -------------------------------------------------------
        # Antal dubbletter
        # -------------------------------------------------------

        basbil[
            "antal_dubblettkallor"
        ] = len(kallor)

        basbil[
            "antal_dubblettannonser"
        ] = len(grupp)

        # -------------------------------------------------------
        # Fingerprint-information
        # -------------------------------------------------------

        if len(grupp) <= 1:

            basbil[
                "fingerprint_score"
            ] = SIKER_MATCHNING

            basbil[
                "fingerprint_confidence"
            ] = SIKER_MATCHNING

            basbil[
                "fingerprint_matchningstyp"
            ] = "unik"

            basbil[
                "fingerprint_matchningsorsak"
            ] = "ingen_dubblett"

        else:

            representant = _grupprepresentant(
                grupp
            )

            basta_score = 0
            basta_typ = "fingerprint"
            basta_orsak = "fingerprint"

            for bil in grupp:

                if bil is representant:
                    continue

                diagnostik = fingerprint_score(
                    representant,
                    bil,
                )

                if (
                    diagnostik["score"]
                    > basta_score
                ):
                    basta_score = (
                        diagnostik["score"]
                    )

                    basta_typ = (
                        diagnostik[
                            "matchningstyp"
                        ]
                    )

                    basta_orsak = (
                        diagnostik[
                            "orsak"
                        ]
                    )

            basbil[
                "fingerprint_score"
            ] = basta_score

            basbil[
                "fingerprint_confidence"
            ] = basta_score

            basbil[
                "fingerprint_matchningstyp"
            ] = basta_typ

            basbil[
                "fingerprint_matchningsorsak"
            ] = basta_orsak

        # -------------------------------------------------------
        # Spara annons-ID:n från alla källor.
        # -------------------------------------------------------

        annons_ids = []

        for bil in grupp:

            annons_id = bil.get(
                "annons_id"
            )

            if (
                annons_id
                and annons_id not in annons_ids
            ):
                annons_ids.append(
                    annons_id
                )

        basbil[
            "dubblett_annons_ids"
        ] = annons_ids

        # -------------------------------------------------------
        # Spara diagnostik per källa.
        # -------------------------------------------------------

        matchningar = []

        if len(grupp) > 1:

            representant = _grupprepresentant(
                grupp
            )

            for bil in grupp:

                if bil is representant:
                    continue

                diagnostik = fingerprint_score(
                    representant,
                    bil,
                )

                matchningar.append(
                    {
                        "kalla": bil.get(
                            "kalla"
                        ),
                        "annons_id": bil.get(
                            "annons_id"
                        ),
                        "score": diagnostik[
                            "score"
                        ],
                        "confidence": diagnostik[
                            "confidence"
                        ],
                        "matchningstyp": diagnostik[
                            "matchningstyp"
                        ],
                        "orsak": diagnostik[
                            "orsak"
                        ],
                    }
                )

        basbil[
            "dubblett_matchningar"
        ] = matchningar

        resultat.append(
            basbil
        )

    return resultat
