"""Fyndscore (0-100) och formatering av meddelandetext."""

from config import BILAR


_VISNINGSNAMN = {
    (b["marke_slug"], b["modell_slug"]): (
        b["marke_visning"],
        b["modell_visning"],
    )
    for b in BILAR
}


def bil_rubrik(bil: dict) -> str:
    """Bygger bilens visningsrubrik."""

    nyckel = (
        bil.get("marke_slug"),
        bil.get("modell_slug"),
    )

    marke_visning, modell_visning = _VISNINGSNAMN.get(
        nyckel,
        ("", (bil.get("modell") or "").upper()),
    )

    variant = bil.get("variant", "")

    if variant and variant.lower() != modell_visning.lower():
        return f"{marke_visning} {modell_visning} {variant}".strip()

    return f"{marke_visning} {modell_visning}".strip()


def berakna_fyndscore_breakdown(
    bil: dict,
    vardering: dict,
) -> dict:
    """
    Beräknar fyndscore och returnerar även komponenterna.

    Viktning:
        Prisvärde       60 p
        Miltal          20 p
        Utrustning       5 p
        Trygghet        15 p

    Returnerar exempelvis:

        {
            "pris": 34,
            "miltal": 15,
            "utrustning": 3,
            "trygghet": 8,
            "total": 60,
        }
    """

    # =========================================================
    # 1. PRISVÄRDE - MAX 60 POÄNG
    # =========================================================

    diff = max(
        0,
        vardering.get("diff", 0),
    )

    prispoang = 0

    if diff >= 60000:
        prispoang = 60

    elif diff >= 55000:
        prispoang = 56

    elif diff >= 50000:
        prispoang = 52

    elif diff >= 45000:
        prispoang = 48

    elif diff >= 40000:
        prispoang = 44

    elif diff >= 35000:
        prispoang = 40

    elif diff >= 30000:
        prispoang = 36

    elif diff >= 27500:
        prispoang = 33

    elif diff >= 25000:
        prispoang = 30

    elif diff >= 22500:
        prispoang = 27

    elif diff >= 20000:
        prispoang = 24

    elif diff >= 17500:
        prispoang = 21

    elif diff >= 15000:
        prispoang = 18

    elif diff >= 12500:
        prispoang = 15

    elif diff >= 10000:
        prispoang = 12

    elif diff >= 7500:
        prispoang = 9

    elif diff >= 5000:
        prispoang = 6

    elif diff >= 2500:
        prispoang = 3

    # =========================================================
    # 2. MILTAL - MAX 20 POÄNG
    # =========================================================

    miltal = bil.get(
        "miltal",
        999999,
    )

    miltalspoang = 0

    if miltal < 5000:
        miltalspoang = 20

    elif miltal < 6000:
        miltalspoang = 19

    elif miltal < 7000:
        miltalspoang = 17

    elif miltal < 8000:
        miltalspoang = 15

    elif miltal < 9000:
        miltalspoang = 13

    elif miltal < 10000:
        miltalspoang = 11

    elif miltal < 11000:
        miltalspoang = 9

    elif miltal < 12000:
        miltalspoang = 7

    elif miltal < 13000:
        miltalspoang = 5

    elif miltal < 14000:
        miltalspoang = 3

    # =========================================================
    # 3. UTRUSTNING - MAX 5 POÄNG
    # =========================================================

    utrustningsniva = (
        bil.get("utrustningsniva") or ""
    ).lower()

    utrustningspoang = 0

    if "ultimate" in utrustningsniva:
        utrustningspoang = 5

    elif "plus" in utrustningsniva:
        utrustningspoang = 4

    elif "inscription" in utrustningsniva:
        utrustningspoang = 3

    elif "momentum" in utrustningsniva:
        utrustningspoang = 2

    elif "core" in utrustningsniva:
        utrustningspoang = 1

    tillvalspoang = 0

    if bil.get("dragkrok"):
        tillvalspoang += 1

    if bil.get("varmare"):
        tillvalspoang += 1

    utrustningspoang += min(
        tillvalspoang,
        max(
            0,
            5 - utrustningspoang,
        ),
    )

    # =========================================================
    # 4. TRYGGHET - MAX 15 POÄNG
    # =========================================================

    trygghetspoang = 0

    if bil.get("volvo_selekt"):
        trygghetspoang += 5

    antal_agare = bil.get(
        "antal_agare"
    ) or 99

    if antal_agare <= 1:
        trygghetspoang += 4

    elif antal_agare == 2:
        trygghetspoang += 2

    if not bil.get("hyrbil"):
        trygghetspoang += 3

    if not bil.get("import"):
        trygghetspoang += 3

    # =========================================================
    # 5. AUKTION
    # =========================================================

    auktion_avdrag = 0

    if bil.get("auktion"):
        auktion_avdrag = 10

    # =========================================================
    # TOTAL
    # =========================================================

    total = (
        prispoang
        + miltalspoang
        + utrustningspoang
        + trygghetspoang
        - auktion_avdrag
    )

    total = max(
        0,
        min(100, total),
    )

    return {
        "pris": prispoang,
        "miltal": miltalspoang,
        "utrustning": utrustningspoang,
        "trygghet": trygghetspoang,
        "auktion_avdrag": auktion_avdrag,
        "total": total,
    }


def berakna_fyndscore(
    bil: dict,
    vardering: dict,
) -> int:
    """Beräknar fyndscore 0-100."""

    breakdown = berakna_fyndscore_breakdown(
        bil,
        vardering,
    )

    return breakdown["total"]


def score_niva(score: int) -> str:
    """Returnerar läsbar nivå baserat på fyndscore."""

    if score >= 90:
        return "🚨 EXTREMT FYND"

    if score >= 80:
        return "🔥 RIKTIGT FYND"

    if score >= 70:
        return "🟢 MYCKET INTRESSANT"

    if score >= 60:
        return "🟡 INTRESSANT"

    return "⚪ BEVAKA"


def formatera_notis(
    bil: dict,
    vardering: dict,
    score: int,
) -> str:

    niva_emoji = score_niva(score)

    rader = [
        f"{niva_emoji} – {bil_rubrik(bil)}",
        (
            f"{bil.get('arsmodell')} · "
            f"{bil.get('miltal'):,} mil · "
            f"{bil.get('annonspris'):,} kr"
        ).replace(",", " "),
        (
            f"Marknadsvärde: "
            f"~{vardering['marknadsvarde']:,} kr"
        ).replace(",", " "),
        (
            f"Ca {vardering['diff']:,} kr under marknad"
        ).replace(",", " "),
    ]

    if bil.get("auktion"):
        rader.append(
            "⚠️ AUKTIONSPRIS - INTE ett fast köp-nu-pris, "
            "du kan behöva buda över beloppet för att vinna"
        )

    utrustning_bitar = []

    if bil.get("dragkrok"):
        utrustning_bitar.append("Drag")

    if bil.get("varmare"):
        utrustning_bitar.append("värmare")

    if bil.get("utrustningsniva"):
        utrustning_bitar.append(
            bil["utrustningsniva"].title()
        )

    if utrustning_bitar:
        rader.append(
            " · ".join(utrustning_bitar)
        )

    rader.append(
        "Import: "
        f"{'Ja ⚠️' if bil.get('import') else 'Nej'}"
    )

    rader.append(
        "Hyrbil/tjänstebil: "
        f"{'Ja ⚠️' if bil.get('hyrbil') else 'Nej'}"
    )

    rader.append(
        f"Ägare: {bil.get('antal_agare', '?')}"
    )

    if bil.get("prissankning_relevant"):

        rader.append(
            (
                f"⚠️ Sänkt "
                f"{bil['prissankning_kr']:,} kr "
                f"efter {bil['dagar_ute']} dagar ute"
            ).replace(",", " ")
        )

    elif bil.get("dagar_ute", 0) == 0:

        rader.append(
            "Ny annons"
        )

    if bil.get("kallor"):

        rader.append(
            f"Källor: "
            f"{', '.join(bil['kallor'])}"
        )

    if bil.get("urls"):

        rader.append(
            bil["urls"][0]
        )

    rader.append("")
    rader.append(
        f"Fyndscore: {score}/100"
    )

    return "\n".join(rader)
