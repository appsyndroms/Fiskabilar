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

Vi gör INTE en generell sökning efter sex-/sjuteckenssträngar på sidan.
Det skulle kunna ge falska träffar som exempelvis:

    BMW530
    BMW330
    V60T6

Regnr-extraktionen använder därför flera säkra metoder:

1. Uttrycklig regnr-etikett + värde i samma text.
2. Uttrycklig regnr-etikett + närliggande DOM-element.
3. Uttrycklig regnr-etikett + närmaste container.
4. Strukturerad data / JSON-LD där regnr-fältet finns.
5. HTML-attribut nära en uttrycklig regnr-etikett.

Ingen metod accepterar ett godtyckligt ABC123 från hela sidan.

Detaljsidor cachas under varje körning så att samma URL aldrig hämtas
mer än en gång.

REGNR är diagnostisk information och är INTE ett grundkrav.
En annons utan registreringsnummer ska därför inte generera ett
individuellt felmeddelande.

PRESTANDA:
Detaljsidor hämtas parallellt med ett begränsat antal workers.
Sökresultatsidor hämtas sekventiellt.

Vi använder ingen artificiell delay efter detaljsidor.
"""
from app_logging.logger import info

import json
import re
import time
from concurrent.futures import (
    ThreadPoolExecutor,
    as_completed,
)

import requests
from bs4 import BeautifulSoup

from config import BILAR, ARSMODELL_MIN, ARSMODELL_MAX
from sources import (
    matchar_grundkrav,
    grundkrav_fel,
    berika_fran_fritext,
    identifiera_variant,
)


# ---------------------------------------------------------------------------
# PRESTANDA
# ---------------------------------------------------------------------------

SOK_DELAY_SEKUNDER = 1.0

MAX_PARALLELLA_DETALJSIDOR = 6

DETALJ_DELAY_SEKUNDER = 0.0


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

REGNR_REGEX = re.compile(
    r"(?<![A-ZÅÄÖ0-9])"
    r"([A-ZÅÄÖ]{3})"
    r"[\s-]?"
    r"("
    r"\d{3}"
    r"|"
    r"\d{2}[A-Z]"
    r")"
    r"(?![A-ZÅÄÖ0-9])",
    re.IGNORECASE,
)


REGNR_ETIKETT_REGEX = re.compile(
    r"(?:"
    r"\bregistreringsnummer\b"
    r"|"
    r"\bregistreringsnr\b"
    r"|"
    r"\breg\.?\s*nr\.?\b"
    r"|"
    r"\bregnr\b"
    r"|"
    r"\breg\.?\s*nummer\b"
    r")",
    re.IGNORECASE,
)


REGNR_FALTNAMN = (
    "registrationnumber",
    "registration_number",
    "registrationno",
    "registration_no",
    "registernumber",
    "reg_number",
    "regnr",
    "registration",
)


# ---------------------------------------------------------------------------
# BMW
# ---------------------------------------------------------------------------
#
# Bilweb kan skriva:
#
#     530e
#     530 e
#     330e
#     330 e
#
# Dessa ska alltid betraktas som samma modell.
#
# Vi normaliserar därför BMW:s modellbeteckning innan
# identifiera_variant() körs.
#
# Kaross:
#
#     Touring
#
# ska kontrolleras separat. Om sluggen inte innehåller "touring"
# hämtas detaljsidan ändå om modell + xDrive matchar. Där kontrolleras
# sedan karossen mot detaljsidans text.
# ---------------------------------------------------------------------------


BMW_MODELL_REGEX = re.compile(
    r"\b(530|330)\s*e\b",
    re.IGNORECASE,
)

BMW_XDRIVE_REGEX = re.compile(
    r"\bx\s*drive\b",
    re.IGNORECASE,
)

BMW_TOURING_REGEX = re.compile(
    r"\btouring\b",
    re.IGNORECASE,
)

BMW_530E_REGEX = re.compile(
    r"\b530\s*e\b",
    re.IGNORECASE,
)

BMW_330E_REGEX = re.compile(
    r"\b330\s*e\b",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Hjälpfunktioner
# ---------------------------------------------------------------------------


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
# BMW-modellslug-normalisering
# ---------------------------------------------------------------------------


def _normalisera_bmw_modellslug(
    slug_text: str,
) -> str:

    if not slug_text:
        return slug_text

    # 530 e -> 530e
    slug_text = re.sub(
        r"\b530\s+e\b",
        "530e",
        slug_text,
        flags=re.IGNORECASE,
    )

    # 330 e -> 330e
    slug_text = re.sub(
        r"\b330\s+e\b",
        "330e",
        slug_text,
        flags=re.IGNORECASE,
    )

    return slug_text


def _normalisera_bmw_matchtext(
    text: str,
) -> str:

    """
    Normaliserar text inför BMW-matchning.

    Exempel:

        530 e xdrive touring
        -> 530e xdrive touring

        330 e xdrive touring
        -> 330e xdrive touring

    Även HTML/kommatecken etc. tolereras eftersom regexerna
    nedan arbetar på vanlig text.
    """

    if not text:
        return ""

    text = str(text)

    text = re.sub(
        r"\b530\s+e\b",
        "530e",
        text,
        flags=re.IGNORECASE,
    )

    text = re.sub(
        r"\b330\s+e\b",
        "330e",
        text,
        flags=re.IGNORECASE,
    )

    return text


def _ar_bmw_modell(
    bilkonfig: dict,
) -> bool:

    return (
        bilkonfig.get("marke_slug") == "bmw"
        and bilkonfig.get("modell_slug")
        in {
            "530e-xdrive-touring",
            "330e-xdrive-touring",
        }
    )


def _bmw_modell_matchar(
    bilkonfig: dict,
    text: str,
) -> bool:

    """
    Kontrollerar BMW-modellen oberoende av om Bilweb skriver:

        530e
        530 e

    respektive:

        330e
        330 e
    """

    text = _normalisera_bmw_matchtext(
        text
    )

    modell_slug = bilkonfig.get(
        "modell_slug",
        "",
    )

    if modell_slug == "530e-xdrive-touring":

        return (
            BMW_530E_REGEX.search(text)
            is not None
        )

    if modell_slug == "330e-xdrive-touring":

        return (
            BMW_330E_REGEX.search(text)
            is not None
        )

    return False


def _bmw_xdrive_matchar(
    text: str,
) -> bool:

    if not text:
        return False

    text = str(text)

    return (
        BMW_XDRIVE_REGEX.search(text)
        is not None
    )


def _bmw_touring_matchar(
    text: str,
) -> bool:

    if not text:
        return False

    text = str(text)

    return (
        BMW_TOURING_REGEX.search(text)
        is not None
    )


def _bmw_kraver_detaljkontroll(
    bilkonfig: dict,
    slug_text: str,
) -> bool:

    """
    Returnerar True när BMW-annonsen har rätt modell + xDrive
    men sluggen inte själv bekräftar Touring.

    Då ska detaljsidan hämtas och karossen verifieras där.

    Om sluggen redan uttryckligen innehåller Touring behöver vi
    inte göra en extra karosskontroll för att kvalificera kandidaten.
    """

    if not _ar_bmw_modell(
        bilkonfig
    ):
        return False

    slug_text = _normalisera_bmw_matchtext(
        slug_text
    )

    if not _bmw_modell_matchar(
        bilkonfig,
        slug_text,
    ):
        return False

    if not _bmw_xdrive_matchar(
        slug_text,
    ):
        return False

    return not _bmw_touring_matchar(
        slug_text
    )


# ---------------------------------------------------------------------------
# REGNR
# ---------------------------------------------------------------------------


def _normalisera_regnr(
    regnr: str | None,
) -> str | None:

    if not regnr:
        return None

    normaliserat = re.sub(
        r"[^A-Za-zÅÄÖåäö0-9]",
        "",
        str(regnr),
    ).upper()

    if len(normaliserat) not in (6, 7):
        return None

    if not re.fullmatch(
        r"[A-ZÅÄÖ]{3}(?:\d{3}|\d{2}[A-Z])",
        normaliserat,
        re.IGNORECASE,
    ):
        return None

    return normaliserat


def _extrahera_regnr_kandidat(
    text: str | None,
) -> str | None:

    if not text:
        return None

    match = REGNR_REGEX.search(
        str(text)
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


def _extrahera_regnr_etikett_samma_text(
    text: str,
) -> str | None:

    if not text:
        return None

    match = REGNR_ETIKETT_REGEX.search(
        text
    )

    if not match:
        return None

    efter = text[
        match.end():
    ]

    prefix = re.match(
        r"^[\s:;=\-–—]*",
        efter,
    )

    if not prefix:
        return None

    kandidat_text = efter[
        prefix.end():
        prefix.end() + 30
    ]

    return _extrahera_regnr_kandidat(
        kandidat_text
    )


def _extrahera_regnr_dom(
    soup: BeautifulSoup,
) -> str | None:

    textnoder = soup.find_all(
        string=REGNR_ETIKETT_REGEX
    )

    for textnod in textnoder:

        text = str(textnod).strip()

        kandidat = _extrahera_regnr_etikett_samma_text(
            text
        )

        if kandidat:
            return kandidat

        element = getattr(
            textnod,
            "parent",
            None,
        )

        if element is None:
            continue

        element_text = element.get_text(
            " ",
            strip=True,
        )

        kandidat = _extrahera_regnr_etikett_samma_text(
            element_text
        )

        if kandidat:
            return kandidat

        for child in element.find_all(
            recursive=True
        ):

            child_text = child.get_text(
                " ",
                strip=True,
            )

            if len(child_text) > 300:
                continue

            if REGNR_ETIKETT_REGEX.search(
                child_text
            ):

                kandidat = (
                    _extrahera_regnr_etikett_samma_text(
                        child_text
                    )
                )

                if kandidat:
                    return kandidat

                for sibling in child.find_all_next(
                    limit=5
                ):

                    sibling_text = sibling.get_text(
                        " ",
                        strip=True,
                    )

                    if len(sibling_text) > 100:
                        continue

                    kandidat = _extrahera_regnr_kandidat(
                        sibling_text
                    )

                    if kandidat:
                        return kandidat

        for sibling in element.find_all_next(
            limit=8
        ):

            sibling_text = sibling.get_text(
                " ",
                strip=True,
            )

            if not sibling_text:
                continue

            if len(sibling_text) > 150:
                continue

            if (
                sibling is not element
                and REGNR_ETIKETT_REGEX.search(
                    sibling_text
                )
            ):

                kandidat = (
                    _extrahera_regnr_etikett_samma_text(
                        sibling_text
                    )
                )

                if kandidat:
                    return kandidat

            kandidat = _extrahera_regnr_kandidat(
                sibling_text
            )

            if kandidat:
                return kandidat

        container = element

        for _ in range(4):

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

            if len(container_text) > 1000:
                continue

            etikett_match = REGNR_ETIKETT_REGEX.search(
                container_text
            )

            if not etikett_match:
                continue

            efter = container_text[
                etikett_match.end():
            ]

            efter = efter[:100]

            kandidat = _extrahera_regnr_kandidat(
                efter
            )

            if kandidat:
                return kandidat

    return None


# ---------------------------------------------------------------------------
# REGNR från attribut
# ---------------------------------------------------------------------------


def _extrahera_regnr_attribut(
    soup: BeautifulSoup,
) -> str | None:

    for element in soup.find_all(True):

        attributtext = " ".join(
            str(value)
            for key, value in element.attrs.items()
            if isinstance(value, (str, list))
        )

        if not REGNR_ETIKETT_REGEX.search(
            attributtext
        ):
            continue

        for key, value in element.attrs.items():

            if isinstance(value, list):
                value = " ".join(
                    str(v)
                    for v in value
                )

            value = str(value)

            key_normaliserad = re.sub(
                r"[^a-z0-9]",
                "",
                key.lower(),
            )

            if (
                key_normaliserad in REGNR_FALTNAMN
                or "registration" in key_normaliserad
                or "regnr" in key_normaliserad
            ):

                kandidat = _extrahera_regnr_kandidat(
                    value
                )

                if kandidat:
                    return kandidat

        element_text = element.get_text(
            " ",
            strip=True,
        )

        kandidat = (
            _extrahera_regnr_etikett_samma_text(
                element_text
            )
        )

        if kandidat:
            return kandidat

    return None


# ---------------------------------------------------------------------------
# REGNR från JSON-LD / strukturerad data
# ---------------------------------------------------------------------------


def _iterera_json_objekt(
    obj,
):

    if isinstance(obj, dict):

        yield obj

        for value in obj.values():

            yield from _iterera_json_objekt(
                value
            )

    elif isinstance(obj, list):

        for value in obj:

            yield from _iterera_json_objekt(
                value
            )


def _extrahera_regnr_json(
    soup: BeautifulSoup,
) -> str | None:

    for script in soup.find_all(
        "script"
    ):

        script_text = script.string

        if not script_text:
            script_text = script.get_text(
                strip=True
            )

        if not script_text:
            continue

        typ = script.get(
            "type",
            "",
        ).lower()

        if (
            "json" not in typ
            and "application/ld+json" not in typ
        ):
            continue

        try:

            data = json.loads(
                script_text
            )

        except (
            ValueError,
            TypeError,
        ):
            continue

        for obj in _iterera_json_objekt(
            data
        ):

            for key, value in obj.items():

                key_normaliserad = re.sub(
                    r"[^a-z0-9]",
                    "",
                    str(key).lower(),
                )

                if key_normaliserad not in REGNR_FALTNAMN:
                    continue

                if isinstance(
                    value,
                    (dict, list),
                ):
                    continue

                kandidat = _extrahera_regnr_kandidat(
                    str(value)
                )

                if kandidat:
                    return kandidat

    return None


# ---------------------------------------------------------------------------
# REGNR från HTML
# ---------------------------------------------------------------------------


def _extrahera_regnr_html(
    html: str,
) -> str | None:

    if not html:
        return None

    match = REGNR_ETIKETT_REGEX.search(
        html
    )

    if not match:
        return None

    start = max(
        0,
        match.start() - 100,
    )

    slut = min(
        len(html),
        match.end() + 500,
    )

    område = html[
        start:slut
    ]

    område = re.sub(
        r"<[^>]+>",
        " ",
        område,
    )

    område = re.sub(
        r"\s+",
        " ",
        område,
    )

    etikett_match = REGNR_ETIKETT_REGEX.search(
        område
    )

    if not etikett_match:
        return None

    efter = område[
        etikett_match.end():
    ]

    efter = efter[:100]

    return _extrahera_regnr_kandidat(
        efter
    )


# ---------------------------------------------------------------------------
# Huvudfunktion för REGNR
# ---------------------------------------------------------------------------


def _extrahera_regnr(
    soup: BeautifulSoup,
    html: str,
) -> str | None:

    regnr = _extrahera_regnr_dom(
        soup
    )

    if regnr:
        return regnr

    regnr = _extrahera_regnr_attribut(
        soup
    )

    if regnr:
        return regnr

    regnr = _extrahera_regnr_json(
        soup
    )

    if regnr:
        return regnr

    regnr = _extrahera_regnr_html(
        html
    )

    if regnr:
        return regnr

    return None


# ---------------------------------------------------------------------------
# Kaross
# ---------------------------------------------------------------------------


def _extrahera_kaross(
    text: str,
) -> str | None:

    """
    Identifierar kaross från detaljsidans text.

    För BMW 530e/330e är Touring den kaross vi vill ha.

    Funktionen är avsiktligt enkel och konservativ:
    den accepterar endast uttryckliga karossord.
    """

    if not text:
        return None

    normaliserad = re.sub(
        r"\s+",
        " ",
        str(text),
    ).strip()

    if re.search(
        r"\btouring\b",
        normaliserad,
        re.IGNORECASE,
    ):
        return "Touring"

    if re.search(
        r"\bcross\s*country\b",
        normaliserad,
        re.IGNORECASE,
    ):
        return "Cross Country"

    if re.search(
        r"\bkombi\b",
        normaliserad,
        re.IGNORECASE,
    ):
        return "Kombi"

    if re.search(
        r"\bsedan\b",
        normaliserad,
        re.IGNORECASE,
    ):
        return "Sedan"

    if re.search(
        r"\bsuv\b",
        normaliserad,
        re.IGNORECASE,
    ):
        return "SUV"

    return None


def _kaross_kravs_for_bil(
    bilkonfig: dict,
) -> str | None:

    modell_slug = bilkonfig.get(
        "modell_slug",
        "",
    )

    if modell_slug in {
        "530e-xdrive-touring",
        "330e-xdrive-touring",
    }:
        return "Touring"

    return None


def _kaross_matchar(
    bilkonfig: dict,
    kaross: str | None,
    text: str,
) -> bool:

    krav = _kaross_kravs_for_bil(
        bilkonfig
    )

    if krav is None:
        return True

    if krav == "Touring":

        if kaross == "Touring":
            return True

        # Fallback direkt mot texten.
        return (
            BMW_TOURING_REGEX.search(
                text
            )
            is not None
        )

    return False


# ---------------------------------------------------------------------------
# Bilweb sökresultat
# ---------------------------------------------------------------------------


def _hamta_kandidat_urler(
    bilkonfig: dict,
    ar: int,
) -> list[dict]:

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

        info(
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

        # ------------------------------------------------------------
        # BMW-normalisering.
        # ------------------------------------------------------------

        slug_text = _normalisera_bmw_modellslug(
            slug_text
        )

        # ------------------------------------------------------------
        # Vanlig variantmatchning.
        # ------------------------------------------------------------

        variant = identifiera_variant(
            bilkonfig,
            slug_text,
        )

        # ------------------------------------------------------------
        # BMW-specialfall:
        #
        # Om Bilwebs slug innehåller rätt BMW-modell + xDrive
        # men saknar "Touring", låter vi detaljsidan avgöra
        # karossen.
        #
        # Detta gör att exempelvis:
        #
        #     530e xdrive m sport ...
        #
        # inte kastas bort bara för att "touring" saknas
        # i sluggen.
        #
        # Samma gäller:
        #
        #     530 e xdrive ...
        #     330e xdrive ...
        #     330 e xdrive ...
        # ------------------------------------------------------------

        detalj_karosskontroll = (
            _bmw_kraver_detaljkontroll(
                bilkonfig,
                slug_text,
            )
        )

        if variant is None and not detalj_karosskontroll:

            if len(avvisade_slugs) < 5:

                avvisade_slugs.append(
                    slug_text
                )

            continue

        if detalj_karosskontroll:

            variant = (
                "530e xDrive Touring"
                if bilkonfig.get(
                    "modell_slug"
                ) == "530e-xdrive-touring"
                else "330e xDrive Touring"
            )

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
                "kraver_karosskontroll":
                    detalj_karosskontroll,
            }
        )

    info(
        f"[bilweb] "
        f"{bilkonfig['marke_visning']} "
        f"{bilkonfig['modell_visning']} "
        f"{ar}: "
        f"{len(sedda_id)} unika annons-URL:er "
        f"-> {len(kandidater)} matchade variant/kaross"
    )

    if avvisade_slugs:

        info(
            f"[bilweb]   Exempel på slugs som INTE "
            f"matchade variant/kaross: "
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
    str | None,
    str,
] | None:

    try:

        resp = requests.get(
            url,
            headers=HEADERS,
            timeout=15,
        )

        resp.raise_for_status()

    except Exception as e:

        info(
            f"[bilweb]   FEL vid hämtning av "
            f"detaljsida {url}: {e}"
        )

        return None

    html = resp.text

    soup = BeautifulSoup(
        html,
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

        info(
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
    #
    # REGNR är diagnostisk information.
    # ------------------------------------------------------------

    regnr = _extrahera_regnr(
        soup,
        html,
    )

    # ------------------------------------------------------------
    # Kaross
    # ------------------------------------------------------------

    kaross = _extrahera_kaross(
        text
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
        kaross,
        text,
    )


# ---------------------------------------------------------------------------
# Parallell hämtning av detaljsidor
# ---------------------------------------------------------------------------


def _hamta_detaljsidor_parallellt(
    kandidater: list[dict],
    cache: dict,
) -> tuple[dict, int, int]:
    """
    Hämtar alla nya detaljsidor parallellt.

    Cache används först så att en URL aldrig hämtas två gånger.

    Returnerar:

        (
            resultat_per_url,
            antal_cachetraffar,
            antal_nya_hamtningar,
        )
    """

    resultat_per_url = {}

    nya_kandidater = []

    cachetraffar = 0

    # ------------------------------------------------------------
    # Identifiera vilka URL:er som faktiskt behöver hämtas.
    # ------------------------------------------------------------

    for kandidat in kandidater:

        url = kandidat["url"]

        if url in cache:

            resultat_per_url[url] = cache[url]
            cachetraffar += 1

        else:

            nya_kandidater.append(
                kandidat
            )

    if not nya_kandidater:

        return (
            resultat_per_url,
            cachetraffar,
            0,
        )

    info(
        f"[bilweb]   hämtar "
        f"{len(nya_kandidater)} detaljsidor "
        f"parallellt med "
        f"{MAX_PARALLELLA_DETALJSIDOR} workers"
    )

    # ------------------------------------------------------------
    # Parallell hämtning.
    # ------------------------------------------------------------

    with ThreadPoolExecutor(
        max_workers=MAX_PARALLELLA_DETALJSIDOR
    ) as executor:

        framtida = {
            executor.submit(
                _hamta_pris_mil_fran_detaljsida,
                kandidat["url"],
            ): kandidat["url"]
            for kandidat in nya_kandidater
        }

        for future in as_completed(
            framtida
        ):

            url = framtida[
                future
            ]

            try:

                resultat = future.result()

            except Exception as e:

                info(
                    f"[bilweb]   FEL i parallell "
                    f"detaljhämtning: {url}: {e}"
                )

                resultat = None

            cache[url] = resultat
            resultat_per_url[url] = resultat

    return (
        resultat_per_url,
        cachetraffar,
        len(nya_kandidater),
    )


# ---------------------------------------------------------------------------
# Huvudfunktion
# ---------------------------------------------------------------------------


def hamta_annonser() -> list[dict]:

    starttid = time.monotonic()

    info(
        "[bilweb] hämtar annonser..."
    )

    info(
        "[bilweb] PARALLELLA DETALJSIDOR: "
        f"{MAX_PARALLELLA_DETALJSIDOR}"
    )

    bilar = []

    rak_grundkrav_totalt = 0

    regnr_detaljsidor = 0
    regnr_hittade = 0

    detaljsidor_hamtade = 0
    detaljsidor_cachetraffar = 0

    # ------------------------------------------------------------
    # Detaljsidecache
    #
    # En URL hämtas maximalt en gång under hela körningen.
    # Även misslyckade resultat cachas.
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

            if not kandidater:
                continue

            # --------------------------------------------------------
            # Hämta detaljsidor parallellt.
            # --------------------------------------------------------

            (
                resultat_per_url,
                cachetraffar,
                nya_hamtningar,
            ) = _hamta_detaljsidor_parallellt(
                kandidater,
                detaljsida_cache,
            )

            detaljsidor_cachetraffar += (
                cachetraffar
            )

            detaljsidor_hamtade += (
                nya_hamtningar
            )

            # --------------------------------------------------------
            # Grundkrav
            # --------------------------------------------------------

            rak_grundkrav = 0

            for kandidat in kandidater:

                url = kandidat["url"]

                resultat = resultat_per_url.get(
                    url
                )

                if resultat is None:
                    continue

                (
                    pris,
                    mil,
                    antal_agare,
                    ar_auktion,
                    regnr,
                    kaross,
                    detaljtext,
                ) = resultat

                regnr_detaljsidor += 1

                if regnr:
                    regnr_hittade += 1

                # ----------------------------------------------------
                # Karosskontroll.
                #
                # För BMW annonser där sluggen saknade "touring"
                # måste detaljsidan uttryckligen bekräfta Touring.
                # ----------------------------------------------------

                if kandidat.get(
                    "kraver_karosskontroll",
                    False,
                ):

                    if not _kaross_matchar(
                        bilkonfig,
                        kaross,
                        detaljtext,
                    ):

                        continue

                bil = {
                    "kalla": "bilweb",

                    "url": url,

                    "annons_id":
                        kandidat["annons_id"],

                    "regnr":
                        regnr,

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

                    "kaross":
                        kaross,
                }

                # ------------------------------------------------
                # Berika annonsen från URL/slug.
                # ------------------------------------------------

                bil = berika_fran_fritext(
                    bil,
                    bil["utrustningsniva"],
                )

                # ------------------------------------------------
                # Grundkrav.
                #
                # Vi skriver INTE längre ut varje individuell
                # bortvald bil. Det håller loggen ren.
                # ------------------------------------------------

                fel = grundkrav_fel(
                    bil
                )

                if not fel:

                    rak_grundkrav += 1
                    rak_grundkrav_totalt += 1

                    bilar.append(
                        bil
                    )

            info(
                f"[bilweb]   -> "
                f"{rak_grundkrav} av "
                f"{len(kandidater)} "
                f"klarade grundkraven "
                f"efter kontroll av detaljsidor"
            )

    # ------------------------------------------------------------
    # Slutsammanfattning
    # ------------------------------------------------------------

    totaltid = (
        time.monotonic()
        - starttid
    )

    info(
        f"[bilweb] "
        f"{len(bilar)} annonser "
        f"matchade grundkraven totalt"
    )

    info(
        "[bilweb] PRESTANDA: "
        f"{len(detaljsida_cache)} unika detaljsidor "
        f"fanns i cache"
    )

    info(
        "[bilweb] PRESTANDA: "
        f"{detaljsidor_hamtade} detaljsidor "
        f"hämtades från nätet"
    )

    if detaljsidor_cachetraffar:

        info(
            "[bilweb] PRESTANDA: "
            f"{detaljsidor_cachetraffar} detaljsidor "
            f"återanvändes från cache"
        )

    info(
        "[bilweb] KÖRTID: "
        f"{totaltid:.1f} sekunder"
    )

    # ------------------------------------------------------------
    # REGNR-DIAGNOSTIK
    # ------------------------------------------------------------

    info(
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

        info(
            "[bilweb] REGNR-TÄCKNING: "
            f"{procent:.1f}%"
        )

    else:

        info(
            "[bilweb] REGNR-TÄCKNING: "
            "0.0%"
        )

    return bilar
