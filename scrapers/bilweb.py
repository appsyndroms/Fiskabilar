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
# Regexen används INTE generellt på hela sidan.
# Den används endast i närheten av en uttrycklig regnr-etikett.
#
# Detta är viktigt eftersom exempelvis:
#
#   BMW530
#   BMW330
#   V60T6
#
# annars skulle kunna feltolkas som registreringsnummer.
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
    r"|registration\s*number"
    r"|registration"
    r")\b",
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


# ---------------------------------------------------------------------------
# Registreringsnummer - normalisering
# ---------------------------------------------------------------------------

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

    Även äldre format som:

        ABC12A

    stöds.
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

    if not re.fullmatch(
        r"[A-ZÅÄÖ]{3}(?:\d{3}|\d{2}[A-Z])",
        normaliserat,
    ):
        return None

    return normaliserat


def _match_regnr(
    text: str,
) -> str | None:
    """
    Försöker hitta ett registreringsnummer i ett begränsat textstycke.

    Denna funktion ska endast användas på text som redan är kopplad
    till en registreringsnummer-etikett eller dess närmaste DOM-element.
    """

    if not text:
        return None

    match = REGNR_REGEX.search(
        text
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


# ---------------------------------------------------------------------------
# Registreringsnummer - textbaserad
# ---------------------------------------------------------------------------

def _extrahera_regnr(
    text: str,
) -> str | None:
    """
    Extraherar registreringsnummer från text.

    Säkerhetsprincip:

    Vi letar INTE efter registreringsnummer generellt i hela sidan.

    Först måste sidan innehålla en uttrycklig etikett som exempelvis:

        Registreringsnummer
        Registreringsnr
        Reg nr
        Reg.nr
        Regnr

    Därefter undersöks endast ett begränsat område efter etiketten.

    Detta förhindrar att exempelvis:

        BMW530
        BMW330
        V60T6

    feltolkas som registreringsnummer.
    """

    if not text:
        return None

    etikett_match = REGNR_ETIKETT_REGEX.search(
        text
    )

    if not etikett_match:
        return None

    efter = text[
        etikett_match.end():
    ]

    # Tillåt endast begränsat avstånd mellan etikett och värde.
    #
    # Detta stödjer exempelvis:
    #
    # Registreringsnummer: ABC123
    # Registreringsnummer ABC 123
    # Registreringsnummer
    # ABC123
    #
    # men vi letar inte längre bort än 120 tecken.

    kandidattext = efter[
        :120
    ]

    return _match_regnr(
        kandidattext
    )


# ---------------------------------------------------------------------------
# Registreringsnummer - DOM-baserad
# ---------------------------------------------------------------------------

def _extrahera_regnr_dom(
    soup: BeautifulSoup,
) -> str | None:
    """
    Robust DOM-baserad extraktion av registreringsnummer.

    Bilweb kan placera etiketten och själva registreringsnumret
    i olika DOM-element.

    Vi kontrollerar därför:

      1. samma textnod
      2. föräldraelement
      3. förälderns barn
      4. nästa syskon
      5. nästa syskons barn
      6. närmaste containers
      7. ett begränsat lokalt DOM-område

    Vi söker fortfarande aldrig efter registreringsnummer generellt
    över hela sidan.
    """

    for etikett_node in soup.find_all(
        string=REGNR_ETIKETT_REGEX
    ):

        etikett_text = str(
            etikett_node
        ).strip()

        if not REGNR_ETIKETT_REGEX.search(
            etikett_text
        ):
            continue

        # ------------------------------------------------------------
        # 1. Samma textnod
        # ------------------------------------------------------------

        kandidat = _match_regnr(
            etikett_text
        )

        if kandidat:
            return kandidat

        parent = getattr(
            etikett_node,
            "parent",
            None,
        )

        if parent is None:
            continue

        # ------------------------------------------------------------
        # 2. Föräldraelement
        # ------------------------------------------------------------

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
        # 3. Förälderns direkta barn
        # ------------------------------------------------------------

        for child in parent.find_all(
            recursive=False
        ):

            child_text = child.get_text(
                " ",
                strip=True,
            )

            kandidat = _match_regnr(
                child_text
            )

            if kandidat:
                return kandidat

        # ------------------------------------------------------------
        # 4. Nästa syskon
        # ------------------------------------------------------------

        sibling = parent.find_next_sibling()

        if sibling:

            sibling_text = sibling.get_text(
                " ",
                strip=True,
            )

            kandidat = _match_regnr(
                sibling_text
            )

            if kandidat:
                return kandidat

            # --------------------------------------------------------
            # 5. Nästa syskons direkta barn
            # --------------------------------------------------------

            for child in sibling.find_all(
                recursive=False
            ):

                child_text = child.get_text(
                    " ",
                    strip=True,
                )

                kandidat = _match_regnr(
                    child_text
                )

                if kandidat:
                    return kandidat

        # ------------------------------------------------------------
        # 6. Närmaste containers
        # ------------------------------------------------------------

        container = parent

        for _ in range(3):

            container = getattr(
                container,
                "parent",
                None,
            )

            if container is None:
                break

            container_text = container.get_text(
                " ",
                strip=True,
            )

            # Undvik att undersöka hela sidan eller enorma containers.
            if len(container_text) > 500:
                continue

            if not REGNR_ETIKETT_REGEX.search(
                container_text
            ):
                continue

            kandidat = _extrahera_regnr(
                container_text
            )

            if kandidat:
                return kandidat

        # ------------------------------------------------------------
        # 7. Begränsat lokalt DOM-område
        # ------------------------------------------------------------

        delar = []

        aktuellt = parent

        for _ in range(3):

            if aktuellt is None:
                break

            delar.append(
                aktuellt.get_text(
                    " ",
                    strip=True,
                )
            )

            aktuellt = aktuellt.find_next_sibling()

        lokal_text = " ".join(
            delar
        )

        kandidat = _extrahera_regnr(
            lokal_text
        )

        if kandidat:
            return kandidat

    return None


# ---------------------------------------------------------------------------
# Bilweb sökresultat
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Bilweb detaljsida
# ---------------------------------------------------------------------------

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
    # Först DOM-baserad sökning.
    #
    # Därefter strikt textbaserad fallback.
    #
    # Båda kräver en uttrycklig registreringsnummer-etikett.
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


# ---------------------------------------------------------------------------
# Huvudfunktion
# ---------------------------------------------------------------------------

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

                    # REGNR är den starkaste identifieraren
                    # när Bilweb uttryckligen anger den.
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

    # ------------------------------------------------------------
    # Sammanfattning
    # ------------------------------------------------------------

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
