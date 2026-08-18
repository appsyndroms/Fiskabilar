"""
Transparent marknadsvärdesmodell för fyndfiltrets bevakade bilar.

Modellen använder i första hand aktuella marknadsannonser som
jämförelseunderlag.

Grundtanke:
1. Hitta jämförbara bilar med samma modell, variant och årsmodell.
2. Ta bort leasing-/månadsprisannonser från marknadsunderlaget.
3. Ta bort orimliga priser.
4. Ta bort aktuell bil från sina egna jämförelser.
5. Justera jämförelsepris efter skillnad i miltal.
6. Använd medianen av de justerade jämförelsepriserna.
7. Justera för utrustningsnivå.
8. Justera för dragkrok, värmare, Volvo Selekt och batteristorlek.
9. Falla tillbaka till ett manuellt baspris om tillräckligt många
   jämförelsebilar saknas.

VIKTIGT:
Marknadsunderlaget ska endast innehålla faktiska kontantpriser för
bilar som faktiskt säljs.

Leasingannonser, månadspriser och liknande får inte blandas ihop
med försäljningspriser.

Marknadsmodellen är avsiktligt enkel och transparent. Den ska kunna
förbättras när vi får större historiskt underlag.
"""

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

KR_PER_MIL_AVVIKELSE = 2.0


# ---------------------------------------------------------
# Rimlighetsgränser
# ---------------------------------------------------------

# Ett vanligt kontantpris för de bevakade bilarna ska inte
# kunna vara några tusen kronor.
MIN_KONTANTPRIS = 100000

# Skydd mot uppenbara felaktiga priser.
MAX_KONTANTPRIS = 2000000


# =========================================================
# LEASING / MÅNADSPRIS
# =========================================================

LEASING_NYCKELORD = (
    "leasing",
    "privatleasing",
    "företagsleasing",
    "foretagsleasing",
    "leasingpris",
    "leasingkostnad",
    "leasingavgift",
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


def _normalisera_text(
    text: str,
) -> str:
    """
    Normaliserar annonstext för robustare matchning.
    """

    return (
        str(text or "")
        .strip()
        .lower()
        .replace("_", " ")
        .replace("-", " ")
    )


def _annons_text(
    bil: dict,
) -> str:
    """
    Samlar textfält som kan avslöja att annonsen är leasing
    eller månadspris.

    Vi använder flera fält eftersom olika scrapers kan placera
    annonstexten på olika ställen.
    """

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

        value = bil.get(
            falt
        )

        if value:
            delar.append(
                str(value)
            )

    url = bil.get(
        "url"
    )

    if url:
        delar.append(
            str(url)
        )

    urls = bil.get(
        "urls"
    )

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
    Returnerar True om annonsen sannolikt är leasing/månadspris.

    Leasingannonser ska inte användas som jämförelseannonser.
    """

    text = _annons_text(
        bil
    )

    return any(
        nyckel in text
        for nyckel in LEASING_NYCKELORD
    )


def _ar_rimligt_kontantpris(
    pris: int | float,
) -> bool:
    """
    Skydd mot uppenbart felaktiga priser.

    Detta är inte en generell marknadsvärdering utan ett
    skydd mot att exempelvis 4 495 kr/mån råkar tolkas som
    bilens försäljningspris.
    """

    if not isinstance(
        pris,
        (int, float)
    ):
        return False

    return (
        MIN_KONTANTPRIS
        <= pris
        <= MAX_KONTANTPRIS
    )


# =========================================================
# MARKNADSKATEGORI
# =========================================================

def _marknadskategori(
    bil: dict,
) -> tuple:
    """
    Skapar nyckeln som används för att hitta jämförbara bilar.

    Vi använder modell, variant och årsmodell.
    """

    return (
        str(
            bil.get(
                "modell",
                ""
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
    """
    Bygger ett marknadsunderlag från de annonser som samlats in
    under aktuell körning.

    Resultatet grupperas på:

        modell
        variant
        årsmodell

    Varje grupp innehåller pris, miltal och en identifierare.

    Leasingannonser och orimliga priser tas bort.
    """

    underlag = {}

    borttagna_leasing = 0
    borttagna_pris = 0
    godkanda = 0

    for bil in bilar:

        # -------------------------------------------------
        # Leasing
        # -------------------------------------------------

        if _ar_leasingannons(
            bil
        ):

            borttagna_leasing += 1

            continue

        # -------------------------------------------------
        # Pris
        # -------------------------------------------------

        pris = bil.get(
            "annonspris"
        )

        if not _ar_rimligt_kontantpris(
            pris
        ):

            borttagna_pris += 1

            continue

        # -------------------------------------------------
        # Miltal
        # -------------------------------------------------

        miltal = bil.get(
            "miltal"
        )

        if (
            not isinstance(
                miltal,
                (int, float)
            )
            or miltal < 0
        ):

            borttagna_pris += 1

            continue

        # -------------------------------------------------
        # Kategori
        # -------------------------------------------------

        kategori = _marknadskategori(
            bil
        )

        annons_id = (
            bil.get(
                "annons_id"
            )
            or bil.get(
                "id"
            )
            or bil.get(
                "url"
            )
            or (
                bil.get(
                    "urls",
                    [None]
                )[0]
                if bil.get("urls")
                else None
            )
        )

        underlag.setdefault(
            kategori,
            []
        ).append(
            {
                "pris": float(pris),
                "miltal": float(miltal),
                "annons_id": annons_id,
            }
        )

        godkanda += 1

    print(
        "[MARKNAD] "
        f"{godkanda} annonser används som "
        "kontantprisunderlag"
    )

    print(
        "[MARKNAD] "
        f"{borttagna_leasing} leasing-/månadsprisannonser "
        "borttagna"
    )

    print(
        "[MARKNAD] "
        f"{borttagna_pris} annonser med "
        "orimligt pris/miltal borttagna"
    )

    return underlag


# =========================================================
# JÄMFÖRELSEBILAR
# =========================================================

def _hamta_annons_id(
    bil: dict,
):
    """
    Hämtar stabil identifierare för aktuell annons.
    """

    annons_id = bil.get(
        "annons_id"
    )

    if annons_id:
        return annons_id

    annons_id = bil.get(
        "id"
    )

    if annons_id:
        return annons_id

    url = bil.get(
        "url"
    )

    if url:
        return url

    urls = bil.get(
        "urls"
    )

    if urls:
        return urls[0]

    return None


def _hamta_jamforelsebilar(
    bil: dict,
    marknadsunderlag: dict | None,
) -> list[dict]:
    """
    Hämtar jämförelsebilar för aktuell bil.

    Primärt:

        modell
        variant
        årsmodell

    Jämförelsebilen själv tas bort.

    De närmaste bilarna i miltal används först.
    """

    if not marknadsunderlag:
        return []

    kategori = _marknadskategori(
        bil
    )

    jamforelser = list(
        marknadsunderlag.get(
            kategori,
            []
        )
    )

    if not jamforelser:
        return []

    aktuell_id = _hamta_annons_id(
        bil
    )

    if aktuell_id:

        jamforelser = [
            x
            for x in jamforelser
            if x.get(
                "annons_id"
            ) != aktuell_id
        ]

    target_mil = bil.get(
        "miltal"
    )

    if isinstance(
        target_mil,
        (int, float)
    ):

        jamforelser.sort(
            key=lambda x: abs(
                x["miltal"]
                - target_mil
            )
        )

    return jamforelser[
        :MAX_JAMFORELSEBILAR
    ]


# =========================================================
# MARKNADSPRIS
# =========================================================

def _berakna_marknadspris_fran_jamforelser(
    bil: dict,
    jamforelser: list[dict],
) -> int | None:
    """
    Beräknar marknadsvärde från faktiska jämförelseannonser.

    Varje jämförelsepris justeras för skillnad i miltal.

    Median används för att minska påverkan från enstaka
    extrema annonser.
    """

    if len(
        jamforelser
    ) < MIN_JAMFORELSEBILAR:

        return None

    target_mil = bil.get(
        "miltal"
    )

    if not isinstance(
        target_mil,
        (int, float)
    ):

        return None

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

        justerat_pris = (
            pris
            + miljustering
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


def _bygg_marknadsdiagnostik(
    bil: dict,
    jamforelser: list[dict],
) -> dict:
    """
    Bygger transparent diagnostik för marknadsvärderingen.

    Diagnostiken ändrar inte värderingen.

    Den visar exakt hur varje jämförelsebil påverkar
    medianen efter miltalsjustering.
    """

    target_mil = bil.get(
        "miltal"
    )

    detaljer = []

    if not isinstance(
        target_mil,
        (int, float)
    ):

        return {
            "antal": len(jamforelser),
            "malpris": bil.get(
                "annonspris"
            ),
            "milmalspris": None,
            "median_justerat": None,
            "jamforelser": [],
        }

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

        justerat_pris = (
            pris
            + miljustering
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
                    round(
                        miltal
                        - target_mil
                    )
                ),
                "miljustering": int(
                    round(
                        miljustering
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
            }
        )

    justerade = [
        x[
            "justerat_pris"
        ]
        for x in detaljer
    ]

    median_justerat = (
        median(justerade)
        if justerade
        else None
    )

    return {
        "antal": len(
            detaljer
        ),
        "malpris": bil.get(
            "annonspris"
        ),
        "miltal": int(
            round(
                target_mil
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
# UTRUSTNING
# =========================================================

UTRUSTNINGSNIVA_JUSTERING = [
    (
        (
            "polestar engineered",
            "polestar-engineered",
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
            "r-design",
            "r design",
            "rdesign",
        ),
        10000,
    ),

    (
        (
            "plus, dark",
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


# =========================================================
# HJÄLPFUNKTIONER
# =========================================================

def _ar_sedan_arsmodell(
    arsmodell: int,
) -> float:
    """
    Beräknar ungefärlig ålder på bilen.

    Vi använder juni som mittpunkt för årsmodellen.
    """

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


def _hamta_utrustningsjustering(
    bil: dict,
) -> int:
    """
    Identifierar utrustningsnivå genom delsträngsmatchning.
    """

    utrustning = _normalisera_text(
        bil.get(
            "utrustningsniva"
        )
        or ""
    )

    if not utrustning:
        return 0

    for nyckelord, justering in (
        UTRUSTNINGSNIVA_JUSTERING
    ):

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


def berakna_miltalsdiagnostik(
    bil: dict,
) -> dict:
    """
    Returnerar detaljer om hur miltalsjusteringen beräknas.

    Påverkar inte själva marknadsvärdet.
    """

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
        "faktiskt_miltal": faktiskt_miltal,
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
    """
    Hämtar manuellt baspris som fallback.

    Om exakt årsmodell saknas används medianen av tillgängliga
    årsmodeller för samma modell och variant.
    """

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
    """
    Beräknar uppskattat marknadsvärde.

    Om minst MIN_JAMFORELSEBILAR relevanta annonser finns används
    deras faktiska marknadspriser.

    Annars används den manuella fallback-modellen.
    """

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

    if marknadspris is not None:

        baspris = marknadspris

    else:

        baspris = _hamta_baspris(
            bil
        )

        if baspris is None:
            return 0

        # -------------------------------------------------
        # Miltal - fallback
        # -------------------------------------------------

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

        baspris += mil_justering

    # -----------------------------------------------------
    # Utrustning
    # -----------------------------------------------------

    utrustning_justering = (
        _hamta_utrustningsjustering(
            bil
        )
    )

    # -----------------------------------------------------
    # Tillval
    # -----------------------------------------------------

    tillval = 0

    if bil.get(
        "dragkrok"
    ):
        tillval += DRAGKROK_VARDE

    if bil.get(
        "varmare"
    ):
        tillval += VARMARE_VARDE

    if bil.get(
        "volvo_selekt"
    ):
        tillval += SELEKT_VARDE

    if bil.get(
        "stor_batteri"
    ):
        tillval += STOR_BATTERI_VARDE

    # -----------------------------------------------------
    # Slutligt värde
    # -----------------------------------------------------

    marknadsvarde = (
        baspris
        + utrustning_justering
        + tillval
    )

    return (
        round(
            marknadsvarde / 1000
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
    """
    Returnerar:

        marknadsvarde
        diff
        niva
        jamforelseantal
        empiriskt_underlag
        marknadsdiagnostik

    Marknadsdiagnostiken påverkar inte själva värderingen.
    Den används för att kunna granska exakt vilka annonser
    som ligger bakom marknadsvärdet.
    """

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

    jamforelser = (
        _hamta_jamforelsebilar(
            bil,
            marknadsunderlag,
        )
    )

    empiriskt_underlag = (
        len(jamforelser)
        >= MIN_JAMFORELSEBILAR
    )

    marknadsdiagnostik = (
        _bygg_marknadsdiagnostik(
            bil,
            jamforelser,
        )
    )

    if diff >= 35000:

        niva = (
            "EXTREMT_FYND"
        )

    elif diff >= 20000:

        niva = "FYND"

    else:

        niva = None

    return {
        "marknadsvarde": marknadsvarde,
        "diff": diff,
        "niva": niva,
        "jamforelseantal": len(
            jamforelser
        ),
        "empiriskt_underlag": (
            empiriskt_underlag
        ),
        "marknadsdiagnostik": (
            marknadsdiagnostik
        ),
    }
