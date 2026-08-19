"""
Transparent marknadsvärdesmodell för fyndfiltrets bevakade bilar.

Modellen använder i första hand aktuella marknadsannonser som
jämförelseunderlag.

Grundtanke:
1. Hitta jämförbara bilar med samma modell, variant och årsmodell.
2. Ta bort annonser där priset faktiskt är ett leasing-/månadspris.
3. Ta bort orimliga kontantpriser.
4. Ta bort bilar under 1 000 mil från marknadsunderlaget.
5. Ta bort aktuell bil från sina egna jämförelser.
6. Justera jämförelsepris efter skillnad i miltal.
7. Normalisera jämförelsebilarnas utrustning mot aktuell bil.
8. Begränsa orimligt stora utrustningsjusteringar.
9. Använd medianen av de justerade jämförelsepriserna.
10. Falla tillbaka till ett manuellt baspris om tillräckligt många
    jämförelsebilar saknas.

VIKTIGT:
Marknadsunderlaget ska endast innehålla faktiska kontantpriser för
bilar som faktiskt säljs och bilar med minst 1 000 mil.

Leasingannonser, månadspriser och liknande får inte blandas ihop
med försäljningspriser.

Att en bil tidigare varit leasingbil innebär däremot INTE att
annonsen ska filtreras bort.

MARKNADSVÄRDERING:
Den aktuella annonsen får aldrig användas som sin egen jämförelsebil.

Exkludering sker i följande ordning:
1. Annons-ID.
2. Annons-URL.
3. Som sista fallback: samma modell, variant, årsmodell,
   exakt pris och exakt miltal.

Det sista steget behövs eftersom vissa annonskällor inte alltid
levererar ett stabilt annons-ID eller URL i det data som når
värderingsmodellen.

Marknadsmodellen är avsiktligt enkel och transparent. Den ska kunna
förbättras när vi får större historiskt underlag.
"""
from app_logging.logger import info

from datetime import date
from statistics import median


# =========================================================
# BASPRIS - FALLBACK
# =========================================================

BASPRIS = {
    ("v60", "T6 AWD", 2022): 335000,
    ("v60", "T6 AWD", 2023): 375000,
    ("v60", "T6 AWD", 2024): 420000,

    ("v60", "T8 AWD", 2022): 375000,
    ("v60", "T8 AWD", 2023): 415000,
    ("v60", "T8 AWD", 2024): 460000,

    ("v90", "T6 AWD", 2022): 355000,
    ("v90", "T6 AWD", 2023): 395000,
    ("v90", "T6 AWD", 2024): 440000,

    ("v90", "T8 AWD", 2022): 395000,
    ("v90", "T8 AWD", 2023): 435000,
    ("v90", "T8 AWD", 2024): 480000,

    (
        "530e-xdrive-touring",
        "530e xDrive Touring",
        2022,
    ): 315000,

    (
        "530e-xdrive-touring",
        "530e xDrive Touring",
        2023,
    ): 355000,

    (
        "530e-xdrive-touring",
        "530e xDrive Touring",
        2024,
    ): 395000,

    (
        "330e-xdrive-touring",
        "330e xDrive Touring",
        2024,
    ): 430000,

    (
        "330e-xdrive-touring",
        "330e xDrive Touring",
        2025,
    ): 470000,

    (
        "330e-xdrive-touring",
        "330e xDrive Touring",
        2026,
    ): 520000,
}


# =========================================================
# MARKNADSUNDERLAG
# =========================================================

MIN_JAMFORELSEBILAR = 3
MAX_JAMFORELSEBILAR = 15

PRIMAR_MAX_MILTALSSKILLNAD = 1500
MAX_MILTALSSKILLNAD = 3000

KR_PER_MIL_AVVIKELSE = 12.0

MIN_MILTAL = 1000

MIN_KONTANTPRIS = 100000
MAX_KONTANTPRIS = 2000000


# =========================================================
# LEASING / MÅNADSPRIS
# =========================================================

LEASING_NYCKELORD = (
    "privatleasing",
    "företagsleasing",
    "foretagsleasing",
    "leasingpris",
    "leasingkostnad",
    "leasingavgift",
    "leasing erbjudande",
    "leasing erbjuds",
    "leasing från",
    "leasing fr.",
    "månadspris",
    "manadspris",
    "månadsavgift",
    "manadsavgift",
    "kr/mån",
    "kr / mån",
    "kr/månaden",
    "kr per månad",
    "per månad",
    "per manad",
    "/månad",
    "/manad",
)


TIDIGARE_LEASING_NYCKELORD = (
    "tidigare leasingbil",
    "tidigare leasing",
    "fd leasingbil",
    "f d leasingbil",
    "före detta leasingbil",
    "fore detta leasingbil",
    "leasinghistorik",
)


def _normalisera_text(text: str) -> str:
    return (
        str(text or "")
        .strip()
        .lower()
        .replace("_", " ")
        .replace("-", " ")
    )


def _normalisera_url(url) -> str | None:
    """
    Normalisera URL för jämförelse.

    Tar bort:
    - whitespace
    - avslutande /
    - fragment

    Detta gör URL-jämförelsen mindre känslig för små skillnader
    i hur samma annons levereras från olika delar av programmet.
    """

    if not url:
        return None

    text = str(url).strip()

    if not text:
        return None

    text = text.split("#", 1)[0]
    text = text.rstrip("/")

    return text


def _hamta_annons_url(
    bil: dict,
):
    """
    Hämta annonsens URL så stabilt som möjligt.
    """

    url = bil.get("url")

    if url:
        return _normalisera_url(url)

    urls = bil.get("urls")

    if urls:
        for kandidat in urls:

            normaliserad = _normalisera_url(
                kandidat
            )

            if normaliserad:
                return normaliserad

    return None


def _ar_sant(value) -> bool:
    """
    Tolka booleska värden robust.

    Viktigt:
    bool("false") == True i Python.

    Annonsdata kan däremot innehålla exempelvis:
    "false", "0", "no", "nej", etc.
    Dessa ska behandlas som False.
    """

    if isinstance(value, bool):
        return value

    if value is None:
        return False

    if isinstance(value, (int, float)):
        return value != 0

    if isinstance(value, str):

        normaliserat = (
            value
            .strip()
            .lower()
        )

        if normaliserat in (
            "",
            "false",
            "0",
            "no",
            "nej",
            "n",
            "none",
            "null",
        ):
            return False

        if normaliserat in (
            "true",
            "1",
            "yes",
            "ja",
            "j",
            "y",
        ):
            return True

    return bool(value)


def _annons_text(bil: dict) -> str:

    delar = []

    for falt in (
        "utrustningsniva",
        "modell",
        "variant",
        "pris_text",
        "annonsrubrik",
        "rubrik",
        "beskrivning",
        "fritext",
        "leasing",
        "finansiering",
    ):

        value = bil.get(falt)

        if value:
            delar.append(
                str(value)
            )

    url = bil.get("url")

    if url:
        delar.append(
            str(url)
        )

    urls = bil.get("urls")

    if urls:
        delar.extend(
            str(x)
            for x in urls
            if x
        )

    return _normalisera_text(
        " ".join(delar)
    )


def _ar_leasingannons(
    bil: dict,
) -> bool:
    """
    Avgör om annonsen faktiskt verkar vara en leasingannons.

    "Tidigare leasingbil" ska inte räknas som leasingannons.
    """

    text = _annons_text(bil)

    if not text:
        return False

    for nyckel in TIDIGARE_LEASING_NYCKELORD:

        if nyckel in text:
            text = text.replace(
                nyckel,
                "",
            )

    return any(
        nyckel in text
        for nyckel in LEASING_NYCKELORD
    )


def _ar_rimligt_kontantpris(
    pris: int | float,
) -> bool:

    if not isinstance(
        pris,
        (int, float),
    ):
        return False

    return (
        MIN_KONTANTPRIS
        <= pris
        <= MAX_KONTANTPRIS
    )


# =========================================================
# ANNONS-ID
# =========================================================

def _hamta_annons_id(
    bil: dict,
):
    """
    Skapa ett så stabilt annons-ID som möjligt.

    Prioritet:
    1. annons_id
    2. id
    3. url
    4. första URL
    """

    annons_id = bil.get(
        "annons_id"
    )

    if annons_id:
        return str(
            annons_id
        ).strip()

    annons_id = bil.get(
        "id"
    )

    if annons_id:
        return str(
            annons_id
        ).strip()

    url = _hamta_annons_url(
        bil
    )

    if url:
        return url

    return None


# =========================================================
# JÄMFÖRELSE AV AKTUELL ANNONS
# =========================================================

def _ar_samma_annons(
    aktuell_bil: dict,
    jamforelse: dict,
) -> bool:
    """
    Avgör om en jämförelsebil egentligen är samma annons
    som bilen som värderas.

    Matchning sker i prioriterad ordning:

    1. Annons-ID.
    2. URL.
    3. Fallback på exakt:
       modell + variant + årsmodell + pris + miltal.

    Fallbacken används endast när ID och URL saknas.

    Detta förhindrar framför allt problemet där aktuell annons
    råkar sakna annons-ID men ändå hamnar i marknadsunderlaget.
    """

    aktuell_id = _hamta_annons_id(
        aktuell_bil
    )

    jamforelse_id = jamforelse.get(
        "annons_id"
    )

    if (
        aktuell_id
        and jamforelse_id
        and str(aktuell_id).strip()
        == str(jamforelse_id).strip()
    ):
        return True

    aktuell_url = _hamta_annons_url(
        aktuell_bil
    )

    jamforelse_url = _normalisera_url(
        jamforelse.get("annons_url")
    )

    if (
        aktuell_url
        and jamforelse_url
        and aktuell_url == jamforelse_url
    ):
        return True

    # -----------------------------------------------------
    # SISTA FALLBACK
    #
    # Om ingen identifierare finns kan vi fortfarande
    # upptäcka samma annons när samtliga kärnvärden är
    # identiska.
    # -----------------------------------------------------

    if (
        not aktuell_id
        and not aktuell_url
    ) or (
        not jamforelse_id
        and not jamforelse_url
    ):

        aktuell_modell = (
            str(
                aktuell_bil.get(
                    "modell",
                    "",
                )
            ).lower()
        )

        jamforelse_modell = (
            str(
                jamforelse.get(
                    "modell",
                    aktuell_modell,
                )
            ).lower()
        )

        aktuell_variant = aktuell_bil.get(
            "variant"
        )

        jamforelse_variant = jamforelse.get(
            "variant"
        )

        aktuell_arsmodell = aktuell_bil.get(
            "arsmodell"
        )

        jamforelse_arsmodell = jamforelse.get(
            "arsmodell"
        )

        aktuell_pris = aktuell_bil.get(
            "annonspris"
        )

        jamforelse_pris = jamforelse.get(
            "pris"
        )

        aktuell_miltal = aktuell_bil.get(
            "miltal"
        )

        jamforelse_miltal = jamforelse.get(
            "miltal"
        )

        if (
            aktuell_modell
            == jamforelse_modell
            and aktuell_variant
            == jamforelse_variant
            and aktuell_arsmodell
            == jamforelse_arsmodell
            and isinstance(
                aktuell_pris,
                (int, float),
            )
            and isinstance(
                jamforelse_pris,
                (int, float),
            )
            and aktuell_pris
            == jamforelse_pris
            and isinstance(
                aktuell_miltal,
                (int, float),
            )
            and isinstance(
                jamforelse_miltal,
                (int, float),
            )
            and aktuell_miltal
            == jamforelse_miltal
        ):
            return True

    return False


# =========================================================
# MARKNADSKATEGORI
# =========================================================

def _marknadskategori(
    bil: dict,
) -> tuple:

    return (
        str(
            bil.get(
                "modell",
                "",
            )
        ).lower(),

        bil.get(
            "variant"
        ),

        bil.get(
            "arsmodell"
        ),
    )


# =========================================================
# MARKNADSUNDERLAG
# =========================================================

def bygg_marknadsunderlag(
    bilar: list[dict],
) -> dict:

    underlag = {}

    borttagna_leasing = 0
    borttagna_pris = 0
    borttagna_miltal = 0
    godkanda = 0

    for bil in bilar:

        if _ar_leasingannons(
            bil
        ):

            borttagna_leasing += 1
            continue

        pris = bil.get(
            "annonspris"
        )

        if not _ar_rimligt_kontantpris(
            pris
        ):

            borttagna_pris += 1
            continue

        miltal = bil.get(
            "miltal"
        )

        if (
            not isinstance(
                miltal,
                (int, float),
            )
            or miltal < 0
        ):

            borttagna_pris += 1
            continue

        if miltal < MIN_MILTAL:

            borttagna_miltal += 1
            continue

        kategori = _marknadskategori(
            bil
        )

        annons_id = _hamta_annons_id(
            bil
        )

        annons_url = _hamta_annons_url(
            bil
        )

        underlag.setdefault(
            kategori,
            [],
        ).append(
            {
                "pris": float(
                    pris
                ),

                "miltal": float(
                    miltal
                ),

                "annons_id": annons_id,

                "annons_url": annons_url,

                "modell": bil.get(
                    "modell"
                ),

                "variant": bil.get(
                    "variant"
                ),

                "arsmodell": bil.get(
                    "arsmodell"
                ),

                "utrustningsniva": bil.get(
                    "utrustningsniva"
                ),

                "dragkrok": _ar_sant(
                    bil.get(
                        "dragkrok"
                    )
                ),

                "varmare": _ar_sant(
                    bil.get(
                        "varmare"
                    )
                ),

                "volvo_selekt": _ar_sant(
                    bil.get(
                        "volvo_selekt"
                    )
                ),

                "stor_batteri": _ar_sant(
                    bil.get(
                        "stor_batteri"
                    )
                ),
            }
        )

        godkanda += 1

    info(
        "[MARKNAD] "
        f"{godkanda} annonser används som "
        "kontantprisunderlag"
    )

    info(
        "[MARKNAD] "
        f"{borttagna_leasing} leasing-/månadsprisannonser "
        "borttagna"
    )

    info(
        "[MARKNAD] "
        f"{borttagna_pris} annonser med "
        "orimligt pris/miltal borttagna"
    )

    info(
        "[MARKNAD] "
        f"{borttagna_miltal} annonser under "
        f"{MIN_MILTAL:,} mil borttagna från "
        "marknadsunderlaget"
        .replace(
            ",",
            " ",
        )
    )

    return underlag


# =========================================================
# JÄMFÖRELSEBILAR
# =========================================================

def _hamta_jamforelsebilar(
    bil: dict,
    marknadsunderlag: dict | None,
) -> list[dict]:

    if not marknadsunderlag:
        return []

    kategori = _marknadskategori(
        bil
    )

    jamforelser = list(
        marknadsunderlag.get(
            kategori,
            [],
        )
    )

    if not jamforelser:
        return []

    # -----------------------------------------------------
    # VIKTIGT:
    #
    # Ta bort aktuell annons innan miltalsurvalet görs.
    # -----------------------------------------------------

    exkluderade = []

    filtrerade = []

    for jamforelse in jamforelser:

        if _ar_samma_annons(
            bil,
            jamforelse,
        ):

            exkluderade.append(
                jamforelse
            )

        else:

            filtrerade.append(
                jamforelse
            )

    jamforelser = filtrerade

    target_mil = bil.get(
        "miltal"
    )

    if not isinstance(
        target_mil,
        (int, float),
    ):
        return []

    # -----------------------------------------------------
    # STEG 1
    #
    # Försök först hitta minst tre bilar inom ±1 500 mil.
    # -----------------------------------------------------

    primara = [
        x
        for x in jamforelser
        if abs(
            x["miltal"]
            - target_mil
        ) <= PRIMAR_MAX_MILTALSSKILLNAD
    ]

    primara.sort(
        key=lambda x: abs(
            x["miltal"]
            - target_mil
        )
    )

    if len(primara) >= MIN_JAMFORELSEBILAR:

        return primara[
            :MAX_JAMFORELSEBILAR
        ]

    # -----------------------------------------------------
    # STEG 2
    #
    # Om marknaden är tunn utökas intervallet till ±3 000 mil.
    # -----------------------------------------------------

    utokade = [
        x
        for x in jamforelser
        if abs(
            x["miltal"]
            - target_mil
        ) <= MAX_MILTALSSKILLNAD
    ]

    utokade.sort(
        key=lambda x: abs(
            x["miltal"]
            - target_mil
        )
    )

    return utokade[
        :MAX_JAMFORELSEBILAR
    ]


# =========================================================
# UTRUSTNINGSNIVÅ
# =========================================================

UTRUSTNINGSNIVA_JUSTERING = [
    (
        (
            "polestar engineered",
            "polestar engineered",
        ),
        30000,
    ),

    (
        (
            "inscription expression",
        ),
        25000,
    ),

    (
        (
            "inscription",
        ),
        20000,
    ),

    (
        (
            "ultimate",
        ),
        15000,
    ),

    (
        (
            "r design",
            "rdesign",
        ),
        10000,
    ),

    (
        (
            "plus dark",
            "plus dark edition",
        ),
        5000,
    ),

    (
        (
            "plus",
        ),
        0,
    ),

    (
        (
            "momentum",
        ),
        0,
    ),

    (
        (
            "core",
        ),
        -15000,
    ),
]


# =========================================================
# TILLVAL
# =========================================================

DRAGKROK_VARDE = 8000
VARMARE_VARDE = 4000
SELEKT_VARDE = 6000
STOR_BATTERI_VARDE = 12000


MAX_TOTAL_UTRUSTNINGSJUSTERING = 40000


def _begransa_utrustningsjustering(
    justering: int | float,
) -> int:

    return int(
        max(
            -MAX_TOTAL_UTRUSTNINGSJUSTERING,
            min(
                MAX_TOTAL_UTRUSTNINGSJUSTERING,
                justering,
            ),
        )
    )


def _hamta_utrustningsjustering(
    bil: dict,
) -> int:

    utrustning = _normalisera_text(
        bil.get(
            "utrustningsniva"
        )
        or ""
    )

    if not utrustning:
        return 0

    for (
        nyckelord,
        justering,
    ) in UTRUSTNINGSNIVA_JUSTERING:

        for nyckel in nyckelord:

            normaliserad_nyckel = (
                _normalisera_text(
                    nyckel
                )
            )

            if (
                normaliserad_nyckel
                in utrustning
            ):
                return justering

    return 0


def _hamta_tillvalsjustering(
    bil: dict,
) -> int:

    justering = 0

    if _ar_sant(
        bil.get(
            "dragkrok"
        )
    ):
        justering += DRAGKROK_VARDE

    if _ar_sant(
        bil.get(
            "varmare"
        )
    ):
        justering += VARMARE_VARDE

    if _ar_sant(
        bil.get(
            "volvo_selekt"
        )
    ):
        justering += SELEKT_VARDE

    if _ar_sant(
        bil.get(
            "stor_batteri"
        )
    ):
        justering += STOR_BATTERI_VARDE

    return justering


def _hamta_total_utrustningsjustering(
    bil: dict,
) -> int:

    total = (
        _hamta_utrustningsjustering(
            bil
        )
        + _hamta_tillvalsjustering(
            bil
        )
    )

    return _begransa_utrustningsjustering(
        total
    )


# =========================================================
# MARKNADSPRIS
# =========================================================

def _berakna_marknadspris_fran_jamforelser(
    bil: dict,
    jamforelser: list[dict],
) -> int | None:

    if len(
        jamforelser
    ) < MIN_JAMFORELSEBILAR:

        return None

    target_mil = bil.get(
        "miltal"
    )

    if not isinstance(
        target_mil,
        (int, float),
    ):
        return None

    target_utrustning = (
        _hamta_total_utrustningsjustering(
            bil
        )
    )

    justerade_priser = []

    for jamforelse in jamforelser:

        pris = jamforelse[
            "pris"
        ]

        miltal = jamforelse[
            "miltal"
        ]

        miljustering = (
            miltal
            - target_mil
        ) * KR_PER_MIL_AVVIKELSE

        pris_efter_miltal = (
            pris
            + miljustering
        )

        jamforelse_utrustning = (
            _hamta_total_utrustningsjustering(
                jamforelse
            )
        )

        utrustningsjustering = (
            target_utrustning
            - jamforelse_utrustning
        )

        utrustningsjustering = (
            _begransa_utrustningsjustering(
                utrustningsjustering
            )
        )

        justerat_pris = (
            pris_efter_miltal
            + utrustningsjustering
        )

        justerade_priser.append(
            justerat_pris
        )

    if not justerade_priser:
        return None

    return int(
        round(
            median(
                justerade_priser
            ) / 1000
        )
        * 1000
    )


# =========================================================
# MARKNADSDIAGNOSTIK
# =========================================================

def _bestam_underlagsstyrka(
    antal: int,
) -> str:

    if antal >= 8:
        return "STARKT"

    if antal >= 5:
        return "GODKÄNT"

    if antal >= 3:
        return "SVAGT"

    return "OTILLRÄCKLIGT"


def _bygg_marknadsdiagnostik(
    bil: dict,
    jamforelser: list[dict],
) -> dict:

    target_mil = bil.get(
        "miltal"
    )

    underlagsstyrka = (
        _bestam_underlagsstyrka(
            len(jamforelser)
        )
    )

    if not isinstance(
        target_mil,
        (int, float),
    ):

        return {
            "antal": len(
                jamforelser
            ),

            "underlagsstyrka": (
                underlagsstyrka
            ),

            "malpris": bil.get(
                "annonspris"
            ),

            "miltal": None,

            "median_justerat": None,

            "jamforelser": [],
        }

    target_utrustning = (
        _hamta_total_utrustningsjustering(
            bil
        )
    )

    detaljer = []

    for jamforelse in jamforelser:

        pris = jamforelse[
            "pris"
        ]

        miltal = jamforelse[
            "miltal"
        ]

        milskillnad = (
            miltal
            - target_mil
        )

        miljustering = (
            milskillnad
            * KR_PER_MIL_AVVIKELSE
        )

        jamforelse_utrustning = (
            _hamta_total_utrustningsjustering(
                jamforelse
            )
        )

        utrustningsjustering = (
            target_utrustning
            - jamforelse_utrustning
        )

        utrustningsjustering = (
            _begransa_utrustningsjustering(
                utrustningsjustering
            )
        )

        justerat_pris = (
            pris
            + miljustering
            + utrustningsjustering
        )

        detaljer.append(
            {
                "pris": int(
                    round(pris)
                ),

                "miltal": int(
                    round(miltal)
                ),

                "milskillnad": int(
                    round(milskillnad)
                ),

                "miljustering": int(
                    round(miljustering)
                ),

                "jamforelse_utrustning": int(
                    round(
                        jamforelse_utrustning
                    )
                ),

                "malbil_utrustning": int(
                    round(
                        target_utrustning
                    )
                ),

                "utrustningsjustering": int(
                    round(
                        utrustningsjustering
                    )
                ),

                "justerat_pris": int(
                    round(
                        justerat_pris
                    )
                ),

                "annons_id": jamforelse.get(
                    "annons_id"
                ),

                "annons_url": jamforelse.get(
                    "annons_url"
                ),
            }
        )

    justerade = [
        x[
            "justerat_pris"
        ]
        for x in detaljer
    ]

    median_justerat = (
        median(
            justerade
        )
        if justerade
        else None
    )

    return {
        "antal": len(
            detaljer
        ),

        "underlagsstyrka": (
            underlagsstyrka
        ),

        "malpris": bil.get(
            "annonspris"
        ),

        "miltal": int(
            round(
                target_mil
            )
        ),

        "malbil_utrustning": int(
            round(
                target_utrustning
            )
        ),

        "median_justerat": (
            int(
                round(
                    median_justerat
                )
            )
            if median_justerat is not None
            else None
        ),

        "jamforelser": detaljer,
    }


# =========================================================
# MILTAL - FALLBACK
# =========================================================

FORVANTAT_MIL_PER_AR = 1800


# =========================================================
# MILTALSDIAGNOSTIK
# =========================================================

def _ar_sedan_arsmodell(
    arsmodell: int,
) -> float:

    if not arsmodell:
        return 0.0

    idag = date.today()

    return max(
        0.0,
        (
            idag.year
            - arsmodell
        )
        + (
            idag.month
            - 6
        ) / 12,
    )


def berakna_miltalsdiagnostik(
    bil: dict,
) -> dict:

    arsmodell = bil.get(
        "arsmodell"
    )

    if not arsmodell:

        return {
            "arsmodell": None,
            "alder_ar": 0,
            "forvantat_mil": 0,
            "faktiskt_miltal": bil.get(
                "miltal",
                0,
            ),
            "mil_avvikelse": 0,
            "mil_justering": 0,
        }

    alder_ar = _ar_sedan_arsmodell(
        arsmodell
    )

    forvantat_mil = (
        alder_ar
        * FORVANTAT_MIL_PER_AR
    )

    faktiskt_miltal = bil.get(
        "miltal",
        forvantat_mil,
    )

    mil_avvikelse = (
        faktiskt_miltal
        - forvantat_mil
    )

    mil_justering = (
        -mil_avvikelse
        * KR_PER_MIL_AVVIKELSE
    )

    return {
        "arsmodell": arsmodell,

        "alder_ar": round(
            alder_ar,
            2,
        ),

        "forvantat_mil": round(
            forvantat_mil
        ),

        "faktiskt_miltal": (
            faktiskt_miltal
        ),

        "mil_avvikelse": round(
            mil_avvikelse
        ),

        "mil_justering": round(
            mil_justering
        ),
    }


# =========================================================
# MANUELLT BASPRIS
# =========================================================

def _hamta_baspris(
    bil: dict,
) -> int | None:

    modell = (
        bil.get(
            "modell"
        )
        or "v60"
    ).lower()

    variant = bil.get(
        "variant"
    )

    arsmodell = bil.get(
        "arsmodell"
    )

    baspris = BASPRIS.get(
        (
            modell,
            variant,
            arsmodell,
        )
    )

    if baspris is not None:
        return baspris

    kandidater = [
        pris
        for (
            mod,
            var,
            ar,
        ), pris in BASPRIS.items()
        if (
            mod == modell
            and var == variant
        )
    ]

    if not kandidater:
        return None

    return int(
        median(
            kandidater
        )
    )


# =========================================================
# MARKNADSVÄRDE
# =========================================================

def berakna_marknadsvarde(
    bil: dict,
    marknadsunderlag: dict | None = None,
) -> int:

    jamforelser = (
        _hamta_jamforelsebilar(
            bil,
            marknadsunderlag,
        )
    )

    marknadspris = (
        _berakna_marknadspris_fran_jamforelser(
            bil,
            jamforelser,
        )
    )

    # =====================================================
    # EMPIRISKT MARKNADSVÄRDE
    # =====================================================

    if marknadspris is not None:

        marknadsvarde = (
            marknadspris
        )

    # =====================================================
    # FALLBACK
    # =====================================================

    else:

        baspris = _hamta_baspris(
            bil
        )

        if baspris is None:
            return 0

        arsmodell = bil.get(
            "arsmodell"
        )

        alder_ar = _ar_sedan_arsmodell(
            arsmodell
        )

        forvantat_mil = (
            alder_ar
            * FORVANTAT_MIL_PER_AR
        )

        faktiskt_miltal = bil.get(
            "miltal",
            forvantat_mil,
        )

        mil_avvikelse = (
            faktiskt_miltal
            - forvantat_mil
        )

        mil_justering = (
            -mil_avvikelse
            * KR_PER_MIL_AVVIKELSE
        )

        utrustning_justering = (
            _hamta_total_utrustningsjustering(
                bil
            )
        )

        marknadsvarde = (
            baspris
            + mil_justering
            + utrustning_justering
        )

    return (
        round(
            marknadsvarde
            / 1000
        )
        * 1000
    )


# =========================================================
# FYND
# =========================================================

def berakna_fynd(
    bil: dict,
    marknadsunderlag: dict | None = None,
) -> dict:

    marknadsvarde = (
        berakna_marknadsvarde(
            bil,
            marknadsunderlag,
        )
    )

    annonspris = bil.get(
        "annonspris",
        0,
    )

    diff = (
        marknadsvarde
        - annonspris
    )

    # -----------------------------------------------------
    # FYNDPROCENT
    # -----------------------------------------------------

    if (
        isinstance(
            marknadsvarde,
            (int, float),
        )
        and marknadsvarde > 0
    ):

        fyndprocent = (
            diff
            / marknadsvarde
            * 100
        )

    else:

        fyndprocent = 0.0

    jamforelser = (
        _hamta_jamforelsebilar(
            bil,
            marknadsunderlag,
        )
    )

    antal_jamforelser = len(
        jamforelser
    )

    # -----------------------------------------------------
    # EMPIRISKT UNDERLAG
    # -----------------------------------------------------

    empiriskt_underlag = (
        antal_jamforelser
        >= MIN_JAMFORELSEBILAR
    )

    underlagsstyrka = (
        _bestam_underlagsstyrka(
            antal_jamforelser
        )
    )

    marknadsdiagnostik = (
        _bygg_marknadsdiagnostik(
            bil,
            jamforelser,
        )
    )

    # =====================================================
    # FYNDKLASSNING
    # =====================================================

    if (
        empiriskt_underlag
        and diff >= 35000
        and fyndprocent >= 8.0
        and underlagsstyrka
        in (
            "GODKÄNT",
            "STARKT",
        )
    ):

        niva = "EXTREMT_FYND"

    elif (
        empiriskt_underlag
        and diff >= 20000
        and fyndprocent >= 5.0
    ):

        niva = "FYND"

    else:

        niva = None

    return {
        "marknadsvarde": (
            marknadsvarde
        ),

        "diff": diff,

        "fyndprocent": round(
            fyndprocent,
            1,
        ),

        "niva": niva,

        "jamforelseantal": (
            antal_jamforelser
        ),

        "underlagsstyrka": (
            underlagsstyrka
        ),

        "empiriskt_underlag": (
            empiriskt_underlag
        ),

        "marknadsdiagnostik": (
            marknadsdiagnostik
        ),
    }
