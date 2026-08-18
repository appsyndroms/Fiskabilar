"""
Transparent marknadsvärdesmodell för fyndfiltrets bevakade bilar.

Modellen använder i första hand aktuella marknadsannonser som
jämförelseunderlag.

Grundtanke:
1. Hitta jämförbara bilar med samma modell, variant och årsmodell.
2. Justera jämförelsepris efter skillnad i miltal.
3. Använd medianen av de justerade jämförelsepriserna.
4. Justera för utrustningsnivå.
5. Justera för dragkrok, värmare, Volvo Selekt och batteristorlek.
6. Falla tillbaka till ett manuellt baspris om tillräckligt många
   jämförelsebilar saknas.

VIKTIGT:
Utrustningsnivå matchas med delsträngar i stället för exakt text.

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

    Varje grupp innehåller pris och miltal för de faktiska
    annonserna.

    Endast annonser med giltigt pris och miltal används.
    """

    underlag = {}

    for bil in bilar:

        pris = bil.get(
            "annonspris"
        )

        miltal = bil.get(
            "miltal"
        )

        if (
            not isinstance(
                pris,
                (int, float)
            )
            or pris <= 0
        ):
            continue

        if (
            not isinstance(
                miltal,
                (int, float)
            )
            or miltal < 0
        ):
            continue

        kategori = _marknadskategori(
            bil
        )

        underlag.setdefault(
            kategori,
            []
        ).append(
            {
                "pris": float(pris),
                "miltal": float(miltal),
            }
        )

    return underlag


def _hamta_jamforelsebilar(
    bil: dict,
    marknadsunderlag: dict | None,
) -> list[dict]:
    """
    Hämtar jämförelsebilar för aktuell bil.

    I första hand används exakt samma:
        modell + variant + årsmodell

    Om det finns fler än MAX_JAMFORELSEBILAR används de närmaste
    i miltal.
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


def _berakna_marknadspris_fran_jamforelser(
    bil: dict,
    jamforelser: list[dict],
) -> int | None:
    """
    Beräknar marknadsvärde från faktiska jämförelseannonser.

    Varje jämförelsepris justeras med KR_PER_MIL_AVVIKELSE för
    skillnaden i miltal mellan jämförelsebilen och mål-bilen.

    Därefter används medianen, vilket gör modellen mindre känslig
    för enstaka extremt dyra eller billiga annonser.
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

        # Om jämförelsebilen har fler mil än mål-bilen ska dess
        # pris justeras uppåt.
        #
        # Om jämförelsebilen har färre mil ska dess pris justeras
        # nedåt.
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

    return int(
        round(
            median(
                justerade_priser
            ) / 1000
        )
        * 1000
    )


# =========================================================
# MILTAL - FALLBACK
# =========================================================

# Tidigare modell använde 1 500 mil/år som normal körning.
#
# Vi använder därför en högre normalnivå och en mildare
# värdepåverkan per avvikande mil.
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


def _normalisera_text(
    text: str,
) -> str:
    """
    Normaliserar annonstext för robustare matchning.
    """

    return (
        (text or "")
        .strip()
        .lower()
        .replace("_", " ")
        .replace("-", " ")
    )


def _hamta_utrustningsjustering(
    bil: dict,
) -> int:
    """
    Identifierar utrustningsnivå genom delsträngsmatchning.
    """

    utrustning = _normalisera_text(
        bil.get("utrustningsniva")
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

    # -----------------------------------------------------
    # EMPIRISKT MARKNADSVÄRDE
    # -----------------------------------------------------

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

    anvander_empiriskt_underlag = (
        marknadspris is not None
    )

    if anvander_empiriskt_underlag:

        baspris = marknadspris

    else:

        baspris = _hamta_baspris(
            bil
        )

        if baspris is None:
            return 0

        # -------------------------------------------------
        # Miltal - endast fallback-modellen
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

    if bil.get("dragkrok"):
        tillval += DRAGKROK_VARDE

    if bil.get("varmare"):
        tillval += VARMARE_VARDE

    if bil.get("volvo_selekt"):
        tillval += SELEKT_VARDE

    if bil.get("stor_batteri"):
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
    }
