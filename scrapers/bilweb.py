"""
Scraper för Bilweb.

Bilweb fungerar utan JavaScript för de delar vi behöver läsa ut.
Sökresultatsidan används endast för att hitta kandidat-URL:er.
Pris, miltal och övriga detaljuppgifter hämtas från respektive
annons egen detaljsida.

Registreringsnummer hämtas från samma detaljsida som pris/miltal.

VIKTIGT:
Registreringsnummer används som starkaste identifierare av fysisk bil,
men endast när Bilwebs sida uttryckligen anger ett registreringsnummer.

Ingen generell sökning efter sex-/sjuteckenssträngar görs, eftersom
exempelvis BMW530 annars kan feltolkas som ett registreringsnummer.

Detaljsidor cachas under varje körning så att samma URL aldrig hämtas
mer än en gång.
"""

import re
import time

import requests
from bs4 import BeautifulSoup

from config import BILAR, ARSMODELL_MIN, ARSMODELL_MAX
from scrapers import (
    matchar_grundkrav,
    grundkrav_fel,
    berika_fran_fritext,
    identifiera_variant,
)


SOK_DELAY_SEKUNDER = 3.0
DETALJ_DELAY_SEKUNDER = 1.5

SOK_URL_MALL = "https://bilweb.se/sok/{marke}/{modell}/{ar}"

BILWEB_BASE_URL = "https://bilweb.se"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    ),
}


PRIS_DETALJ_REGEX = re.compile(
    r"Pris\s*(?:\([^)]*\))?\s*([\d\s]+?)\s*kr",
    re.IGNORECASE,
)

MIL_DETALJ_REGEX = re.compile(
    r"Mil\s+([\d\s]+?)\s+1:a\s+regdatum",
    re.IGNORECASE,
)

AGARE_DETALJ_REGEX = re.compile(
    r"Antal\s+ägare\s+(\d+)",
    re.IGNORECASE,
)

AUKTION_REGEX = re.compile(
    r"auktionsobjekt",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Registreringsnummer
# ---------------------------------------------------------------------------
#
# Svenska registreringsnummer:
#
#   ABC123
#   ABC 123
#   ABC-123
#   ABC12A
#   ABC 12A
#
# Regexen används INTE på hela sidan.
# Den används endast efter en uttrycklig regnr-etikett.
# ---------------------------------------------------------------------------

REGNR_REGEX = re.compile(
    r"\b"
    r"([A-ZÅÄÖ]{3})"
    r"[\s-]?"
    r"("
    r"\d{3}"
    r"|"
    r"\d{2}[A-Z]"
    r")"
    r"\b",
    re.IGNORECASE,
)


REGNR_ETIKETT_REGEX = re.compile(
    r"\b(?:"
    r"registreringsnummer"
    r"|registreringsnr"
    r"|reg\.?\s*nr"
    r"|regnr"
    r")\b"
    r"\s*:?",
    re.IGNORECASE,
)


def _bygg_href_regex(
    marke_slug: str,
) -> re.Pattern:

    return re.compile(
        rf"{re.escape(marke_slug)}-"
        rf"(?P<slug>[a-z0-9-]+?)-"
        rf"(?P<ar>\d{{4}})-kombi-"
        rf"(?P<id>\d+)",
        re.IGNORECASE,
    )


def _rensa_tal(
    text: str,
) -> int:

    siffror = re.sub(
        r"\D",
        "",
        text,
    )

    return int(siffror) if siffror else 0


def _normalisera_regnr(
    regnr: str | None,
) -> str | None:
    """
    Normaliserar registreringsnummer.

    Exempel:

        ABC 123
        ABC-123
        abc123

    blir:

        ABC123
    """

    if not regnr:
        return None

    normaliserat = re.sub(
        r"[^A-Za-zÅÄÖåäö0-9]",
        "",
        regnr,
    ).upper()

    if len(normaliserat) not in (6, 7):
        return None

    return normaliserat


def _extrahera_regnr(
    text: str,
) -> str | None:
    """
    Extraherar registreringsnummer från detaljsidans text.

    Viktig säkerhetsprincip:

    Vi letar INTE efter registreringsnummer generellt i hela sidan.

    Först måste sidan innehålla en uttrycklig etikett som exempelvis:

        Registreringsnummer
        Registreringsnr
        Reg nr
        Reg.nr
        Regnr

    Därefter får ett registreringsnummer endast förekomma direkt efter
    etiketten, bortsett från whitespace och kolon.

    Detta förhindrar att exempelvis:

        BMW530
        BMW330
        V60T6

    feltolkas som registreringsnummer.
    """

    etikett_match = REGNR_ETIKETT_REGEX.search(
        text
    )

    if not etikett_match:
        return None

    efter = text[
        etikett_match.end():
    ]

    # Vi tillåter endast whitespace, kolon eller bindestreck
    # mellan etiketten och själva registreringsnumret.
    #
    # Om det kommer en massa annan text först ska vi inte försöka
    # gissa.
    direkt_prefix = re.match(
        r"^[\s:;\-]*",
        efter,
    )

    if not direkt_prefix:
        return None

    start = direkt_prefix.end()

    kandidattext = efter[
        start:start + 20
    ]

    match = REGNR_REGEX.match(
        kandidattext
    )

    if not match:
        return None

    kandidat = (
        f"{match.group(1)}"
        f"{match.group(2)}"
    )

    return _normalisera_regnr(
        kandidat
    )


def _extrahera_regnr_dom(
    soup: BeautifulSoup,
) -> str | None:
    """
    Försöker hitta registreringsnummer genom DOM-strukturen.

    Detta är ännu säkrare än att söka i hela sidans sammanslagna text.

    Vi letar efter ett element vars synliga text innehåller en
    registreringsnummer-etikett och undersöker sedan samma element,
    nästa syskon eller närmaste relevanta container.

    Om DOM-strukturen inte ger en entydig träff returneras None och
    den strikta textbaserade metoden får försöka.
    """

    etikett_element = None

    for element in soup.find_all(
        string=REGNR_ETIKETT_REGEX
    ):
        text = str(element).strip()

        if REGNR_ETIKETT_REGEX.search(
            text
        ):
            etikett_element = element
            break

    if etikett_element is None:
        return None

    # ------------------------------------------------------------
    # 1. Samma textnod
    # ------------------------------------------------------------

    kandidat = _extrahera_regnr(
        str(etikett_element)
    )

    if kandidat:
        return kandidat

    # ------------------------------------------------------------
    # 2. Föräldraelement
    # ------------------------------------------------------------

    parent = getattr(
        etikett_element,
        "parent",
        None,
    )

    if parent:
        parent_text = parent.get_text(
            " ",
            strip=True,
        )

        kandidat = _extrahera_regnr(
            parent_text
        )

        if kandidat:
            return kandidat

    # ------------------------------------------------------------
    # 3. Nästa syskon
    # ------------------------------------------------------------

    if parent:
        sibling = parent.find_next_sibling()

        if sibling:
            sibling_text = sibling.get_text(
                " ",
                strip=True,
            )

            match = REGNR_REGEX.search(
                sibling_text
            )

            if match:
                kandidat = (
                    f"{match.group(1)}"
                    f"{match.group(2)}"
                )

                kandidat = _normalisera_regnr(
                    kandidat
                )

                if kandidat:
                    return kandidat

    return None


def _hamta_kandidat_urler(
    bilkonfig: dict,
    ar: int,
) -> list[dict]:
    """
    Hämtar Bilwebs sökresultatsida för modell/årsmodell.

    Sidan används endast för att hitta kandidat-URL:er.
    Pris och miltal läses aldrig från sökresultatet.
    """

    marke_slug = bilkonfig[
        "marke_slug"
    ]

    modell_slug = bilkonfig.get(
        "bilweb_modell_slug",
        bilkonfig["modell_slug"],
    )

    sok_url = SOK_URL_MALL.format(
        marke=marke_slug,
        modell=modell_slug,
        ar=ar,
    )

    href_regex = _bygg_href_regex(
        marke_slug
    )

    try:
        resp = requests.get(
            sok_url,
            headers=HEADERS,
            timeout=15,
        )

        resp.raise_for_status()

    except Exception as e:

        print(
            f"[bilweb] FEL vid hämtning av söksida för "
            f"{bilkonfig['marke_visning']} "
            f"{bilkonfig['modell_visning']} "
            f"årsmodell {ar}: {e}"
        )

        return []

    time.sleep(
        SOK_DELAY_SEKUNDER
    )

    soup = BeautifulSoup(
        resp.text,
        "html.parser",
    )

    sedda_id = set()
    kandidater = []
    avvisade_slugs = []

    for a in soup.find_all(
        "a",
        href=True,
    ):

        m = href_regex.search(
            a["href"]
        )

        if not m:
            continue

        annons_id = m.group(
            "id"
        )

        if annons_id in sedda_id:
            continue

        sedda_id.add(
            annons_id
        )

        slug_text = (
            m.group("slug")
            .replace("-", " ")
        )

        variant = identifiera_variant(
            bilkonfig,
            slug_text,
        )

        if variant is None:

            if len(avvisade_slugs) < 3:
                avvisade_slugs.append(
                    slug_text
                )

            continue

        href = a["href"]

        full_url = (
            f"{BILWEB_BASE_URL}{href}"
            if href.startswith("/")
            else href
        )

        kandidater.append(
            {
                "url": full_url,
                "annons_id": annons_id,
                "slug_text": slug_text,
                "variant": variant,
                "arsmodell": int(
                    m.group("ar")
                ),
            }
        )

    print(
        f"[bilweb] "
        f"{bilkonfig['marke_visning']} "
        f"{bilkonfig['modell_visning']} "
        f"{ar}: "
        f"{len(sedda_id)} unika annons-URL:er "
        f"-> {len(kandidater)} matchade variant"
    )

    if avvisade_slugs:

        print(
            f"[bilweb]   Exempel på slugs som INTE "
            f"matchade någon variant: "
            f"{avvisade_slugs}"
        )

    return kandidater


def _hamta_pris_mil_fran_detaljsida(
    url: str,
) -> tuple[
    int,
    int,
    int | None,
    bool,
    str | None,
] | None:
    """
    Hämtar en annons egen detaljsida.

    Returnerar:

        pris
        mil
        antal ägare
        auktion
        registreringsnummer

    Registreringsnumret hämtas från samma HTTP-svar.
    """

    try:

        resp = requests.get(
            url,
            headers=HEADERS,
            timeout=15,
        )

        resp.raise_for_status()

    except Exception as e:

        print(
            f"[bilweb]   FEL vid hämtning av "
            f"detaljsida {url}: {e}"
        )

        return None

    soup = BeautifulSoup(
        resp.text,
        "html.parser",
    )

    text = soup.get_text(
        separator="\n",
        strip=True,
    )

    # ------------------------------------------------------------
    # Pris
    # ------------------------------------------------------------

    pris_match = re.search(
        r"(?:^|\n)\s*Pris\s*(?:\([^)]*\))?\s*\n+\s*([\d\s]+)\s*kr",
        text,
        re.IGNORECASE,
    )

    # ------------------------------------------------------------
    # Miltal
    # ------------------------------------------------------------

    mil_match = re.search(
        r"(?:^|\n)\s*Mil\s*\n+\s*(\d[\d\s]*)\s*(?:\n|$)",
        text,
        re.IGNORECASE,
    )

    if not pris_match:

        pris_match = PRIS_DETALJ_REGEX.search(
            text.replace(
                "\n",
                " ",
            )
        )

    if not mil_match:

        mil_match = MIL_DETALJ_REGEX.search(
            text
        )

    if not pris_match or not mil_match:

        print(
            f"[bilweb]   Kunde inte tolka "
            f"pris/mil på detaljsidan: {url}"
        )

        return None

    # ------------------------------------------------------------
    # Antal ägare
    # ------------------------------------------------------------

    agare_match = AGARE_DETALJ_REGEX.search(
        text.replace(
            "\n",
            " ",
        )
    )

    antal_agare = (
        int(
            agare_match.group(1)
        )
        if agare_match
        else None
    )

    # ------------------------------------------------------------
    # Auktion
    # ------------------------------------------------------------

    ar_auktion = (
        AUKTION_REGEX.search(
            text
        )
        is not None
    )

    # ------------------------------------------------------------
    # Registreringsnummer
    # ------------------------------------------------------------
    #
    # Först försöker vi använda DOM-strukturen.
    # Därefter den strikta textmetoden.
    #
    # Båda metoderna kräver uttrycklig regnr-etikett.
    # ------------------------------------------------------------

    regnr = _extrahera_regnr_dom(
        soup
    )

    if not regnr:

        regnr = _extrahera_regnr(
            text
        )

    if regnr:

        print(
            f"[bilweb]   REGNR hittat: "
            f"{regnr}"
        )

    else:

        print(
            f"[bilweb]   REGNR saknas: "
            f"{url}"
        )

    return (
        _rensa_tal(
            pris_match.group(1)
        ),
        _rensa_tal(
            mil_match.group(1)
        ),
        antal_agare,
        ar_auktion,
        regnr,
    )


def hamta_annonser() -> list[dict]:

    print(
        "[bilweb] hämtar annonser..."
    )

    bilar = []

    rak_grundkrav_totalt = 0

    regnr_detaljsidor = 0
    regnr_hittade = 0

    # ------------------------------------------------------------
    # Detaljsidecache
    #
    # En URL hämtas maximalt en gång under hela körningen.
    # Även misslyckade/avvisade resultat cachas.
    # ------------------------------------------------------------

    detaljsida_cache = {}

    for bilkonfig in BILAR:

        arsmodell_min = bilkonfig.get(
            "arsmodell_min",
            ARSMODELL_MIN,
        )

        arsmodell_max = bilkonfig.get(
            "arsmodell_max",
            ARSMODELL_MAX,
        )

        for ar in range(
            arsmodell_min,
            arsmodell_max + 1,
        ):

            kandidater = _hamta_kandidat_urler(
                bilkonfig,
                ar,
            )

            rak_grundkrav = 0

            for kandidat in kandidater:

                url = kandidat["url"]

                # ------------------------------------------------
                # Cache
                # ------------------------------------------------

                if url in detaljsida_cache:

                    resultat = detaljsida_cache[
                        url
                    ]

                    print(
                        f"[bilweb]   CACHE: "
                        f"detaljsida redan kontrollerad "
                        f"- hoppar över hämtning: {url}"
                    )

                else:

                    resultat = (
                        _hamta_pris_mil_fran_detaljsida(
                            url
                        )
                    )

                    detaljsida_cache[
                        url
                    ] = resultat

                    time.sleep(
                        DETALJ_DELAY_SEKUNDER
                    )

                if resultat is None:
                    continue

                (
                    pris,
                    mil,
                    antal_agare,
                    ar_auktion,
                    regnr,
                ) = resultat

                regnr_detaljsidor += 1

                if regnr:
                    regnr_hittade += 1

                bil = {
                    "kalla": "bilweb",
                    "url": url,

                    "annons_id":
                        kandidat["annons_id"],

                    "regnr": regnr,

                    "marke_slug":
                        bilkonfig["marke_slug"],

                    "modell_slug":
                        bilkonfig["modell_slug"],

                    "modell":
                        bilkonfig["modell_slug"],

                    "annonspris":
                        pris,

                    "variant":
                        kandidat["variant"],

                    "arsmodell":
                        kandidat["arsmodell"],

                    "miltal":
                        mil,

                    "vaxellada":
                        "Automat",

                    "skadad":
                        False,

                    "utrustningsniva":
                        kandidat["slug_text"],

                    "antal_agare":
                        antal_agare,

                    "auktion":
                        ar_auktion,

                    "import":
                        None,

                    "hyrbil":
                        None,

                    "servicehistorik":
                        None,

                    "senaste_service":
                        None,

                    "nasta_service":
                        None,

                    "forsta_registrering":
                        None,

                    "dragkrok":
                        None,

                    "varmare":
                        None,

                    "volvo_selekt":
                        None,

                    "stor_batteri":
                        None,
                }

                bil = berika_fran_fritext(
                    bil,
                    bil["utrustningsniva"],
                )

                fel = grundkrav_fel(
                    bil
                )

                if not fel:

                    rak_grundkrav += 1
                    rak_grundkrav_totalt += 1

                    bilar.append(
                        bil
                    )

                else:

                    print(
                        f"[bilweb]   BORTVALD: "
                        f"{bil['modell']} "
                        f"{bil['arsmodell']} "
                        f"{bil['miltal']} mil "
                        f"{bil['annonspris']} kr "
                        f"-> {', '.join(fel)}"
                    )

            if kandidater:

                print(
                    f"[bilweb]   -> "
                    f"{rak_grundkrav} av "
                    f"{len(kandidater)} "
                    f"klarade grundkraven "
                    f"efter kontroll av detaljsidor"
                )

    print(
        f"[bilweb] "
        f"{len(bilar)} annonser "
        f"matchade grundkraven totalt"
    )

    # ------------------------------------------------------------
    # REGNR-DIAGNOSTIK
    # ------------------------------------------------------------

    print(
        "[bilweb] REGNR-DIAGNOSTIK: "
        f"{regnr_hittade} av "
        f"{regnr_detaljsidor} "
        f"detaljsidor hade registreringsnummer"
    )

    if regnr_detaljsidor:

        procent = (
            regnr_hittade
            / regnr_detaljsidor
            * 100
        )

        print(
            "[bilweb] REGNR-TÄCKNING: "
            f"{procent:.1f}%"
        )

    else:

        print(
            "[bilweb] REGNR-TÄCKNING: "
            "0.0%"
        )

    return bilar
