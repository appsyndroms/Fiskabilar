"""Fyndscore (0-100) och formatering av meddelandetext."""

from config import BILAR

# Snabbuppslag: (marke_slug, modell_slug) -> (marke_visning, modell_visning)
_VISNINGSNAMN = {
    (b["marke_slug"], b["modell_slug"]): (b["marke_visning"], b["modell_visning"])
    for b in BILAR
}


def bil_rubrik(bil: dict) -> str:
    """Bygger 'Volvo V60 T6 AWD' resp. 'BMW 530e xDrive Touring' utan
    att dubblera variantnamnet när modell och variant redan är samma
    text (som för BMW, där sökningen redan är variant-specifik)."""
    nyckel = (bil.get("marke_slug"), bil.get("modell_slug"))
    marke_visning, modell_visning = _VISNINGSNAMN.get(nyckel, ("", (bil.get("modell") or "").upper()))
    variant = bil.get("variant", "")

    if variant and variant.lower() != modell_visning.lower():
        return f"{marke_visning} {modell_visning} {variant}".strip()
    return f"{marke_visning} {modell_visning}".strip()


def berakna_fyndscore(bil: dict, vardering: dict) -> int:
    score = 0

    # Prisavvikelse är starkast signal (upp till 60p)
    diff = vardering["diff"]
    score += min(60, max(0, round(diff / 700)))

    # Låga mil för åldern (upp till 15p) - redan inbakat i diff, men
    # ger ändå lite extra vikt eftersom mil är det köpare oroar sig mest för
    if bil.get("miltal", 999999) < 6000:
        score += 15
    elif bil.get("miltal", 999999) < 9000:
        score += 8

    # Relevant prissänkning = säljaren är motiverad (upp till 10p)
    if bil.get("prissankning_relevant"):
        score += 10

    # Trygghetsfaktorer (upp till 15p)
    if bil.get("volvo_selekt"):
        score += 5
    if (bil.get("antal_agare") or 99) <= 1:
        score += 5
    if not bil.get("hyrbil"):
        score += 3
    if not bil.get("import"):
        score += 2

    # Auktionspris (t.ex. Kvdbil) är inte ett fast köp-nu-pris - du kan
    # behöva buda över det visade beloppet för att vinna. Dra av poäng
    # för att spegla den extra osäkerheten, men avvisa inte helt (kan
    # ändå vara ett bra utgångsläge).
    if bil.get("auktion"):
        score -= 15

    return max(0, min(100, score))


def formatera_notis(bil: dict, vardering: dict, score: int) -> str:
    niva_emoji = "🚨 EXTREMT FYND" if vardering["niva"] == "EXTREMT_FYND" else "🔥 FYND"

    rader = [
        f"{niva_emoji} – {bil_rubrik(bil)}",
        f"{bil.get('arsmodell')} · {bil.get('miltal'):,} mil · {bil.get('annonspris'):,} kr".replace(",", " "),
        f"Marknadsvärde: ~{vardering['marknadsvarde']:,} kr".replace(",", " "),
        f"Ca {vardering['diff']:,} kr under marknad".replace(",", " "),
    ]

    if bil.get("auktion"):
        rader.append("⚠️ AUKTIONSPRIS (t.ex. Kvdbil) - INTE ett fast köp-nu-pris, "
                      "du kan behöva buda över beloppet för att vinna")

    utrustning_bitar = []
    if bil.get("dragkrok"):
        utrustning_bitar.append("Drag")
    if bil.get("varmare"):
        utrustning_bitar.append("värmare")
    if bil.get("utrustningsniva"):
        utrustning_bitar.append(bil["utrustningsniva"].title())
    if utrustning_bitar:
        rader.append(" · ".join(utrustning_bitar))

    rader.append(f"Import: {'Ja ⚠️' if bil.get('import') else 'Nej'}")
    rader.append(f"Hyrbil/tjänstebil: {'Ja ⚠️' if bil.get('hyrbil') else 'Nej'}")
    rader.append(f"Ägare: {bil.get('antal_agare', '?')}")

    if bil.get("prissankning_relevant"):
        rader.append(
            f"⚠️ Sänkt {bil['prissankning_kr']:,} kr efter {bil['dagar_ute']} dagar ute".replace(",", " ")
        )
    elif bil.get("dagar_ute", 0) == 0:
        rader.append("Ny annons")

    if bil.get("kallor"):
        rader.append(f"Källor: {', '.join(bil['kallor'])}")
    if bil.get("urls"):
        rader.append(bil["urls"][0])

    rader.append("")
    rader.append(f"Fyndscore: {score}/100")

    return "\n".join(rader)
