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

Detta är mer robust än att kräva att modell, variant, miltal
och pris måste ligga inom fasta marginaler.

Fingerprinten är avsiktligt konservativ:
det är bättre att missa en osäker dubblett än att slå ihop
två olika bilar.

Alla numeriska och textbaserade signaler normaliseras innan
matchning.
"""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher


# ---------------------------------------------------------------------------
# Grundparametrar
# ---------------------------------------------------------------------------

MIL_MARGINAL = 300
PRIS_MARGINAL = 5000

# Minsta poäng för automatisk dubblett.
MATCHNINGSGRANS = 82

# Om regnr eller VIN matchar behöver vi normalt inte använda poängmodellen.
SIKER_MATCHNING = 100

# Pris och miltal används som signaler men får inte ensamma skapa matchning.
MINSTA_STARKA_SIGNALER = 3


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

    text = text.replace("&", " och ")

    # Vanliga separators behandlas som mellanslag.
    text = re.sub(
        r"[/_|(),;:+\-]+",
        " ",
        text,
    )

    # Ta bort övrig interpunktion.
    text = re.sub(
        r"[^\w\s]",
        " ",
        text,
    )

    # Normalisera whitespace.
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

    Vi behåller själva informationen men gör jämförelsen mindre
    känslig för exempelvis:

        xDrive
        X-Drive
        x drive

    """

    text = _normalisera_text(value)

    # Vanliga skrivvarianter.
    ersattningar = {
        "x drive": "xdrive",
        "awd": "awd",
        "4 motion": "4motion",
        "4motion": "4motion",
        "quattro": "quattro",
        "recharge": "recharge",
        "plug in": "plugin",
        "phev": "plugin",
    }

    for gammal, ny in ersattningar.items():
        text = text.replace(gammal, ny)

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

    if value in (None, ""):
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

            # Ta bort allt utom siffror, minus och decimalpunkt.
            text = re.sub(
                r"[^0-9.\-]",
                "",
                text,
            )

            if not text:
                return None

            return float(text)

        return float(value)

    except (TypeError, ValueError):
        return None


def _heltal(value):
    """Konverterar numeriskt värde till int där det är möjligt."""

    numeriskt = _numeriskt(value)

    if numeriskt is None:
        return None

    return int(round(numeriskt))


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


def _bool_finns(bil: dict, falt: str) -> bool:
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
# Identifierare
# ---------------------------------------------------------------------------


def _regnr_matchar(a: dict, b: dict) -> bool:
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


def _vin_matchar(a: dict, b: dict) -> bool:
    """Kontrollerar VIN/chassinummer."""

    vin_falt = (
        "vin",
        "chassinummer",
        "chassinr",
        "vin_nummer",
    )

    for falt in vin_falt:
        vin_a = _normalisera_vin(
            a.get(falt)
        )

        vin_b = _normalisera_vin(
            b.get(falt)
        )

        if vin_a and vin_b:
            return vin_a == vin_b

    return False


# ---------------------------------------------------------------------------
# Modell
# ---------------------------------------------------------------------------


def _modell_matchar(a: dict, b: dict) -> bool:
    """
    Modell måste i praktiken matcha.

    Detta är en viktig skyddsregel.

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


def _arsmodell_matchar(a: dict, b: dict) -> bool:
    """Kontrollerar årsmodell."""

    arsmodell_a = _heltal(
        a.get("arsmodell")
    )

    arsmodell_b = _heltal(
        b.get("arsmodell")
    )

    if arsmodell_a is None or arsmodell_b is None:
        return False

    return arsmodell_a == arsmodell_b


# ---------------------------------------------------------------------------
# Miltal
# ---------------------------------------------------------------------------


def _miltal_likhet(a: dict, b: dict) -> float:
    """
    Ger 0–1 baserat på hur nära miltalen ligger.

    <= 100 mil  : 1.00
    <= 300 mil  : gradvis avtagande
    > 300 mil   : 0
    """

    mil_a = _numeriskt(
        a.get("miltal")
    )

    mil_b = _numeriskt(
        b.get("miltal")
    )

    if mil_a is None or mil_b is None:
        return 0.0

    skillnad = abs(
        mil_a - mil_b
    )

    if skillnad <= 100:
        return 1.0

    if skillnad > MIL_MARGINAL:
        return 0.0

    return 1.0 - (
        (skillnad - 100)
        / (MIL_MARGINAL - 100)
    ) * 0.5


# ---------------------------------------------------------------------------
# Pris
# ---------------------------------------------------------------------------


def _pris_likhet(a: dict, b: dict) -> float:
    """
    Ger 0–1 baserat på prisskillnad.

    Pris är en relativt svag signal eftersom samma bil kan vara
    publicerad med olika pris på olika sajter.
    """

    pris_a = _numeriskt(
        a.get("annonspris")
    )

    pris_b = _numeriskt(
        b.get("annonspris")
    )

    if pris_a is None or pris_b is None:
        return 0.0

    skillnad = abs(
        pris_a - pris_b
    )

    if skillnad <= 1000:
        return 1.0

    if skillnad > PRIS_MARGINAL:
        return 0.0

    return 1.0 - (
        (skillnad - 1000)
        / (PRIS_MARGINAL - 1000)
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

    Detta gör att en saknad uppgift inte behandlas som en konflikt.
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

        if isinstance(va, str) or isinstance(vb, str):
            if _normalisera_text(va) == _normalisera_text(vb):
                matchningar += 1

        elif va == vb:
            matchningar += 1

    return matchningar, kanda


# ---------------------------------------------------------------------------
# Fingerprint-score
# ---------------------------------------------------------------------------


def _matchningsscore(
    a: dict,
    b: dict,
) -> tuple[int, dict]:
    """
    Beräknar ett fingerprint-score 0–100.

    Viktning:

        Modell                 blockerande krav
        Årsmodell              20
        Variant                20
        Miltal                 20
        Pris                   10
        Utrustning             15
        Övriga signaler        15

    Regnr och VIN hanteras separat som säkra identifierare.
    """

    # Modell är blockerande.
    if not _modell_matchar(a, b):
        return 0, {
            "orsak": "olika_modell",
        }

    score = 0
    detaljer = {
        "modell": True,
        "arsmodell": False,
        "variantlikhet": 0.0,
        "miltallikhet": 0.0,
        "prislikhet": 0.0,
        "utrustningsmatchningar": 0,
        "utrustningskanda": 0,
    }

    # -------------------------------------------------------
    # Årsmodell: 20 poäng
    # -------------------------------------------------------

    if _arsmodell_matchar(a, b):
        score += 20
        detaljer["arsmodell"] = True
    else:
        # Olika årsmodell är en mycket stark konflikt.
        return 0, {
            "orsak": "olika_arsmodell",
        }

    # -------------------------------------------------------
    # Variant: 20 poäng
    # -------------------------------------------------------

    variantlikhet = _variantlikhet(
        a.get("variant"),
        b.get("variant"),
    )

    detaljer["variantlikhet"] = variantlikhet

    if variantlikhet >= 0.90:
        score += 20

    elif variantlikhet >= 0.75:
        score += 16

    elif variantlikhet >= 0.60:
        score += 10

    # -------------------------------------------------------
    # Miltal: 20 poäng
    # -------------------------------------------------------

    miltallikhet = _miltal_likhet(
        a,
        b,
    )

    detaljer["miltallikhet"] = miltallikhet

    score += round(
        miltallikhet * 20
    )

    # -------------------------------------------------------
    # Pris: 10 poäng
    # -------------------------------------------------------

    prislikhet = _pris_likhet(
        a,
        b,
    )

    detaljer["prislikhet"] = prislikhet

    score += round(
        prislikhet * 10
    )

    # -------------------------------------------------------
    # Utrustning: 15 poäng
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
        ) * 15

        score += round(
            utrustningspoang
        )

    # -------------------------------------------------------
    # Övriga identifierande signaler: 15 poäng
    # -------------------------------------------------------

    extra_score = 0
    extra_max = 0

    # Första registrering är ofta mycket stark.
    if (
        a.get("forsta_registrering")
        and b.get("forsta_registrering")
    ):
        extra_max += 5

        if (
            _normalisera_text(
                a.get("forsta_registrering")
            )
            == _normalisera_text(
                b.get("forsta_registrering")
            )
        ):
            extra_score += 5

    # Antal ägare kan vara användbart.
    if (
        a.get("antal_agare") is not None
        and b.get("antal_agare") is not None
    ):
        extra_max += 3

        if (
            _heltal(a.get("antal_agare"))
            == _heltal(b.get("antal_agare"))
        ):
            extra_score += 3

    # Dragkrok.
    if (
        a.get("dragkrok") is not None
        and b.get("dragkrok") is not None
    ):
        extra_max += 3

        if (
            bool(a.get("dragkrok"))
            == bool(b.get("dragkrok"))
        ):
            extra_score += 3

    # Värmare.
    if (
        a.get("varmare") is not None
        and b.get("varmare") is not None
    ):
        extra_max += 2

        if (
            bool(a.get("varmare"))
            == bool(b.get("varmare"))
        ):
            extra_score += 2

    # Stor batteriversion.
    if (
        a.get("stor_batteri") is not None
        and b.get("stor_batteri") is not None
    ):
        extra_max += 2

        if (
            bool(a.get("stor_batteri"))
            == bool(b.get("stor_batteri"))
        ):
            extra_score += 2

    if extra_max:
        score += round(
            (extra_score / extra_max)
            * 15
        )

    return min(
        100,
        score,
    ), detaljer


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
    # Årsmodell måste matcha om båda källorna anger den.
    # -------------------------------------------------------

    arsmodell_a = _heltal(
        a.get("arsmodell")
    )

    arsmodell_b = _heltal(
        b.get("arsmodell")
    )

    if (
        arsmodell_a is not None
        and arsmodell_b is not None
        and arsmodell_a != arsmodell_b
    ):
        return False

    score, detaljer = _matchningsscore(
        a,
        b,
    )

    # -------------------------------------------------------
    # Skydd mot för svag matchning.
    #
    # Om variant saknas på ena sidan får inte enbart modell +
    # årsmodell + ungefärligt pris/miltal räcka.
    # -------------------------------------------------------

    variant_a = _normalisera_variant(
        a.get("variant")
    )

    variant_b = _normalisera_variant(
        b.get("variant")
    )

    if not variant_a or not variant_b:
        starka_signaler = 0

        if _arsmodell_matchar(a, b):
            starka_signaler += 1

        if detaljer.get("miltallikhet", 0) >= 0.75:
            starka_signaler += 1

        if detaljer.get("prislikhet", 0) >= 0.75:
            starka_signaler += 1

        if (
            detaljer.get(
                "utrustningsmatchningar",
                0,
            )
            >= 2
        ):
            starka_signaler += 1

        if starka_signaler < MINSTA_STARKA_SIGNALER:
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

    Användbar vid felsökning och i GitHub Actions.

    Exempel:

        {
            "matchar": True,
            "score": 94,
            "orsak": "fingerprint",
            "detaljer": {...}
        }
    """

    if _regnr_matchar(a, b):
        return {
            "matchar": True,
            "score": SIKER_MATCHNING,
            "orsak": "regnr",
            "detaljer": {},
        }

    if _vin_matchar(a, b):
        return {
            "matchar": True,
            "score": SIKER_MATCHNING,
            "orsak": "vin",
            "detaljer": {},
        }

    score, detaljer = _matchningsscore(
        a,
        b,
    )

    return {
        "matchar": _matchar(a, b),
        "score": score,
        "orsak": detaljer.get(
            "orsak",
            "fingerprint",
        ),
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
    identifierats som samma bil.
    """

    falt = [
        "regnr",
        "vin",
        "chassinummer",
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
# Dubblettgruppering
# ---------------------------------------------------------------------------


def deduplicera(
    bilar: list[dict],
) -> list[dict]:
    """
    Slår ihop annonser som sannolikt avser samma fysiska bil.

    För varje grupp:

        - den mest kompletta annonsen används som bas
        - alla källor sparas
        - alla URL:er sparas
        - fingerprint-score sparas för diagnostik

    Viktigt:

    Matchningen görs mot gruppens mest representativa bil.
    Detta gör att en bil som finns på tre olika sajter kan samlas
    även om varje källa saknar lite olika information.
    """

    grupper: list[list[dict]] = []

    for bil in bilar:
        placerad = False

        for grupp in grupper:

            # Testa mot samtliga annonser i gruppen.
            # Detta är säkrare än att endast jämföra mot grupp[0],
            # eftersom olika källor kan ha olika komplett information.
            matchad = False
            basta_score = 0

            for kandidat in grupp:

                diagnostik = fingerprint_score(
                    kandidat,
                    bil,
                )

                if diagnostik["matchar"]:
                    matchad = True
                    basta_score = max(
                        basta_score,
                        diagnostik["score"],
                    )

            if matchad:
                grupp.append(bil)

                # Spara bästa matchning som diagnostik.
                bil["_fingerprint_score"] = basta_score

                placerad = True
                break

        if not placerad:
            bil["_fingerprint_score"] = 100
            grupper.append(
                [bil]
            )

    # -----------------------------------------------------------------------
    # Bygg slutresultat
    # -----------------------------------------------------------------------

    resultat = []

    for grupp in grupper:

        # Mest kompletta annonsen blir basannons.
        basbil = max(
            grupp,
            key=_fullstandighetspoang,
        ).copy()

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

            for url in (
                b.get("urls")
                or [b.get("url")]
            ):
                if url and url not in urls:
                    urls.append(url)

        basbil["urls"] = urls

        # -------------------------------------------------------
        # Fingerprint-information
        # -------------------------------------------------------

        basbil[
            "antal_dubblettkallor"
        ] = len(kallor)

        basbil[
            "antal_dubblettannonser"
        ] = len(grupp)

        # Bästa uppmätta fingerprint-score.
        score = 100

        if len(grupp) > 1:
            score = 0

            for i, a in enumerate(grupp):
                for b in grupp[i + 1:]:
                    diagnostik = fingerprint_score(
                        a,
                        b,
                    )

                    score = max(
                        score,
                        diagnostik["score"],
                    )

        basbil[
            "fingerprint_score"
        ] = score

        resultat.append(
            basbil
        )

    return resultat
