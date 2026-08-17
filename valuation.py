"""
Transparent marknadsvärdesmodell för fyndfiltrets bevakade bilar.

Modellen är regelbaserad och medvetet enkel att kalibrera.

Grundtanke:
1. Baspris per modell, variant och årsmodell.
2. Avdrag/tillägg beroende på miltal.
3. Justering för utrustningsnivå.
4. Justering för dragkrok, värmare, Volvo Selekt och batteristorlek.

VIKTIGT:
Utrustningsnivå matchas med delsträngar i stället för exakt text.
"""

from datetime import date


# =========================================================
# BASPRIS
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
}


# =========================================================
# MILTAL
# =========================================================

# Tidigare modell använde 1 500 mil/år som normal körning.
# Det ger för låg förväntad körsträcka på nyare bilar.
#
# Vi använder därför en högre normalnivå och en mildare
# värdepåverkan per avvikande mil.
FORVANTAT_MIL_PER_AR = 1800

KR_PER_MIL_AVVIKELSE = 2.0


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
# MARKNADSVÄRDE
# =========================================================

def berakna_marknadsvarde(
    bil: dict,
) -> int:
    """
    Beräknar uppskattat marknadsvärde.
    """

    modell = (
        bil.get("modell")
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

    if baspris is None:

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
            return 0

        kandidater = sorted(
            kandidater
        )

        baspris = kandidater[
            len(kandidater) // 2
        ]

    # -----------------------------------------------------
    # Miltal
    # -----------------------------------------------------

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
        + mil_justering
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
) -> dict:
    """
    Returnerar:

        marknadsvarde
        diff
        niva
    """

    marknadsvarde = (
        berakna_marknadsvarde(
            bil
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
    }
