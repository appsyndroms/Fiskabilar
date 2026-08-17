"""Fyndscore (0-100) och formatering av meddelandetext."""

from config import BILAR


# Snabbuppslag: (marke_slug, modell_slug) ->
# (marke_visning, modell_visning)
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


def berakna_fyndscore(bil: dict, vardering: dict) -> int:
    """
    Beräknar fyndscore 0-100.

    Scoren ska beskriva hur attraktiv bilen är som köp,
    inte enbart hur mycket den ligger under den beräknade
    marknadsvärderingen.

    Poäng:
        Prisvärde       50 p
        Miltal          20 p
        Utrustning      10 p
        Trygghet        15 p
        Övrigt           5 p
    """

    score = 0

    # ---------------------------------------------------------
    # 1. PRISVÄRDE - max 50 p
    # ---------------------------------------------------------

    diff = max(0, vardering.get("diff", 0))

    if diff >= 50000:
        score += 50
    elif diff >= 40000:
        score += 44
    elif diff >= 35000:
        score += 40
    elif diff >= 30000:
        score += 36
    elif diff >= 25000:
        score += 32
    elif diff >= 20000:
        score += 28
    elif diff >= 15000:
        score += 23
    elif diff >= 10000:
        score += 17
    elif diff >= 5000:
        score += 9

    # ---------------------------------------------------------
    # 2. MILTAL - max 20 p
    # ---------------------------------------------------------

    miltal = bil.get("miltal", 999999)

    if miltal < 5000:
        score += 20
    elif miltal < 6000:
        score += 19
    elif miltal < 7000:
        score += 17
    elif miltal < 8000:
        score += 15
    elif miltal < 9000:
        score += 12
    elif miltal < 10000:
        score += 9
    elif miltal < 11000:
        score += 6
    elif miltal < 12000:
        score += 3

    # ---------------------------------------------------------
    # 3. UTRUSTNING - max 10 p
    # ---------------------------------------------------------

    utrustningsniva = (
        bil.get("utrustningsniva") or ""
    ).lower()

    if "ultimate" in utrustningsniva:
        score += 8
    elif "plus" in utrustningsniva:
        score += 6
    elif "inscription" in utrustningsniva:
        score += 5
    elif "momentum" in utrustningsniva:
        score += 3
    elif "core" in utrustningsniva:
        score += 1

    if bil.get("dragkrok"):
        score += 1

    if bil.get("varmare"):
        score += 1

    # ---------------------------------------------------------
    # 4. TRYGGHET - max 15 p
    # ---------------------------------------------------------

    if bil.get("volvo_selekt"):
        score += 5

    antal_agare = bil.get("antal_agare") or 99

    if antal_agare <= 1:
        score += 4
    elif antal_agare == 2:
        score += 2

    if not bil.get("hyrbil"):
        score += 3

    if not bil.get("import"):
        score += 3

    # ---------------------------------------------------------
    # 5. ÖVRIGT - max 5 p
    # ---------------------------------------------------------

    if bil.get("prissankning_relevant"):
        score += 5

    # Auktionspris är inte ett garanterat slutpris.
    if bil.get("auktion"):
        score -= 10

    return max(0, min(100, score))


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
        rader.append(" · ".join(utrustning_bitar))

    rader.append(
        f"Import: {'Ja ⚠️' if bil.get('import') else 'Nej'}"
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
                f"⚠️ Sänkt {bil['prissankning_kr']:,} kr "
                f"efter {bil['dagar_ute']} dagar ute"
            ).replace(",", " ")
        )

    elif bil.get("dagar_ute", 0) == 0:
        rader.append("Ny annons")

    if bil.get("kallor"):
        rader.append(
            f"Källor: {', '.join(bil['kallor'])}"
        )

    if bil.get("urls"):
        rader.append(bil["urls"][0])

    rader.append("")
    rader.append(f"Fyndscore: {score}/100")

    return "\n".join(rader)
