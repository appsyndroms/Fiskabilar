"""
Scraper för Bilweb - VERIFIERAD mot verklig sidstruktur 2026-08-09,
utökad till V60+V90 2026-08-12, bugfixad 2026-08-12, generaliserad
till flera märken (inkl. BMW 530e xDrive Touring) 2026-08-13,
omskriven till årsloop 2026-08-15, omskriven till detaljsides-
hämtning 2026-08-15 (se motivering nedan).

Bekräftat: Bilweb fungerar UTAN JavaScript, så vanlig requests.get()
räcker - både för sökresultatsidan och för enskilda annonssidor.

VIKTIGT ÄNDRING 2026-08-15 (årsloop): tidigare användes en enda
sökning på bilweb.se/sok/{marke}/{modell}/kombi, som bara visar
FÖRSTA SIDAN sorterad på senast publicerad annons - INTE på
årsmodell. Bilweb har - precis som Wayke - en årsspecifik sökväg, så
vi loopar nu över ARSMODELL_MIN..ARSMODELL_MAX.

STÖRRE OMSKRIVNING 2026-08-15 (VIKTIGAST): två tidigare försök att
läsa ut pris/mil direkt ur SÖKRESULTATSIDAN (dels teckenpositioner i
rå HTML, dels DOM-uppåtvandring till närmaste förälder) visade sig
båda kunna ge FEL värden - verifierat konkret mot en riktig annons
(429 900 kr / 5 434 mil enligt annonsens egen sida, men 354 900 kr /
5 692 mil extraherat från sökresultatlistan). Orsaken är att samma
annons ofta länkas flera gånger på sökresultatsidan (kompakt rutnät +
expanderad lista), och den kompakta representationen ibland saknar
egen pris/mil-text helt - då "ärver" extraktionen av misstag en
GRANNANNONS siffror istället, oavsett hur avgränsningslogiken byggs.

Lösningen är att helt sluta gissa på sökresultatsidans struktur och
istället hämta varje kandidat-annons EGEN detaljsida (verifierad
otvetydig: "Pris 429 900 kr" och "Mil 5 434" förekommer där bara en
gång var, ingen risk för sammanblandning). Sökresultatsidan används
nu bara för att hitta KANDIDAT-URL:er (baserat på variant i sluggen),
inte för att läsa ut pris/mil.

Konsekvens: fler HTTP-anrop (ett per kandidat, utöver själva
sökningen) => längre körtid. Bedömd rimlig avvägning eftersom
felaktiga pris/mil-siffror direkt påverkar ett köpbeslut.

ÄNDRING 2026-08-18:
En detaljsida hämtas nu maximalt EN gång per URL under en körning.
Om samma annons dyker upp igen via en annan sökning/årsloop/variant
används det tidigare resultatet från cachen istället för ett nytt
HTTP-anrop.

Detta gäller även annonser som redan har avfärdats efter kontroll av
detaljsidan. Vi behöver alltså inte hämta samma URL igen bara för att
konstatera samma sak en gång till.

ÄNDRING 2026-08-18:
Registreringsnummer extraheras från samma detaljsida som redan hämtas
för pris/miltal. Ingen extra HTTP-förfrågan görs.

Registreringsnumret används som stark identifierare av fysisk bil i
dedupliceringen och långtidshistoriken när det finns tillgängligt.

Om Bilweb inte visar registreringsnummer lämnas fältet None och
befintlig dedupliceringslogik används som fallback.

ÄNDRING 2026-08-18:
Registreringsnummer får ENDAST identifieras när Bilwebs detaljsida
innehåller en uttrycklig etikett för registreringsnummer och ett
registreringsnummer direkt efter etiketten.

Den tidigare försiktiga fallback-sökningen i hela sidans text är
borttagen. Det förhindrar att andra sex- eller sjuteckenssträngar,
exempelvis BMW530 eller BMW330, feltolkas som registreringsnummer.
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


# Registreringsnummer:
#
# Svenska registreringsnummer är normalt:
#   ABC123
#   ABC 123
#   ABC12A
#   ABC 12A
#
# Vi använder detta ENDAST efter att vi först har hittat en relevant
# etikett på detaljsidan.
REGNR_REGEX = re.compile(
    r"\b([A-ZÅÄÖ]{3})[\s-]?(\d{2,3}|"
    r"\d{2}[A-Z])\b",
    re.IGNORECASE,
)

REGNR_ETIKETT_REGEX = re.compile(
    r"(?:"
    r"Registreringsnummer"
    r"|Registreringsnr"
    r"|Registreringsnummer:"
    r"|Reg\.?\s*nr"
    r"|Regnr"
    r"|Regnr:"
    r")",
    re.IGNORECASE,
)


def _bygg_href_regex(marke_slug: str) -> re.Pattern:
    return re.compile(
        rf"{re.escape(marke_slug)}-"
        rf"(?P<slug>[a-z0-9-]+?)-"
        rf"(?P<ar>\d{{4}})-kombi-"
        rf"(?P<id>\d+)",
        re.IGNORECASE,
    )


def _rensa_tal(text: str) -> int:
    siffror = re.sub(r"\D", "", text)
    return int(siffror) if siffror else 0


def _normalisera_regnr(regnr: str | None) -> str | None:
    """
    Normaliserar registreringsnummer så att exempelvis:

        ABC 123
        ABC-123
        abc123

    blir:

        ABC123

    Detta gör dedupliceringen mellan källor mer robust.
    """

    if not regnr:
        return None

    normaliserat = re.sub(
        r"[^A-Za-zÅÄÖåäö0-9]",
        "",
        regnr,
    ).upper()

    if len(normaliserat) < 6 or len(normaliserat) > 7:
        return None

    return normaliserat


def _extrahera_regnr(text: str) -> str | None:
    """
    Försöker hitta registreringsnummer på detaljsidan.

    Viktigt:
    Funktionen arbetar ENDAST på text som redan hämtats från
    detaljsidan. Den gör alltså inget extra HTTP-anrop.

    Registreringsnummer accepteras ENDAST om det finns en uttrycklig
    registreringsnummer-etikett och ett giltigt registreringsnummer
    direkt efter etiketten.

    Ingen fallback-sökning görs i hela sidans text.
    """

    # ------------------------------------------------------------
    # Endast stark signal:
    # registreringsnummer direkt efter relevant etikett.
    # ------------------------------------------------------------

    etikett_match = REGNR_ETIKETT_REGEX.search(text)

    if not etikett_match:
        return None

    efter = text[
        etikett_match.end():
    ]

    # Begränsa sökningen till ett kort område efter etiketten.
    # Det minskar risken för att träffa text längre ner på sidan.
    efter = efter[:200]

    match = REGNR_REGEX.search(
        efter
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


def _hamta_kandidat_urler(
    bilkonfig: dict,
    ar: int
) -> list[dict]:
    """
    Hämtar sökresultatsidan för en modell/årsmodell och plockar ut
    KANDIDAT-URL:er vars slug matchar önskad variant.
    """

    marke_slug = bilkonfig["marke_slug"]

    modell_slug = bilkonfig.get(
        "bilweb_modell_slug",
        bilkonfig["modell_slug"]
    )

    sok_url = SOK_URL_MALL.format(
        marke=marke_slug,
        modell=modell_slug,
        ar=ar
    )

    href_regex = _bygg_href_regex(
        marke_slug
    )

    try:
        resp = requests.get(
            sok_url,
            headers=HEADERS,
            timeout=15
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
        "html.parser"
    )

    sedda_id = set()
    kandidater = []
    avvisade_slugs = []

    for a in soup.find_all(
        "a",
        href=True
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
            slug_text
        )

        if variant is None:

            if len(avvisade_slugs) < 3:
                avvisade_slugs.append(
                    slug_text
                )

            continue

        href = a["href"]

        full_url = (
            f"https://bilweb.se{href}"
            if href.startswith("/")
            else href
        )

        kandidater.append({
            "url": full_url,
            "annons_id": annons_id,
            "slug_text": slug_text,
            "variant": variant,
            "arsmodell": int(
                m.group("ar")
            ),
        })

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
    url: str
) -> tuple[int, int, int | None, bool, str | None] | None:

    """
    Hämtar en enskild annons egen sida och läser ut:

        pris
        mil
        antal ägare
        auktion
        registreringsnummer

    Returnerar:

        (pris, mil, antal_agare, ar_auktion, regnr)

    eller None om något gick fel.

    Registreringsnumret hämtas från SAMMA HTTP-svar som pris/miltal.
    Inget extra anrop görs.
    """

    try:
        resp = requests.get(
            url,
            headers=HEADERS,
            timeout=15
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
        "html.parser"
    )

    text = soup.get_text(
        separator="\n",
        strip=True
    )

    # ------------------------------------------------------------
    # Pris
    # ------------------------------------------------------------

    pris_match = re.search(
        r"(?:^|\n)\s*Pris\s*(?:\([^)]*\))?\s*\n+\s*([\d\s]+)\s*kr",
        text,
        re.IGNORECASE
    )

    # ------------------------------------------------------------
    # Miltal
    # ------------------------------------------------------------

    mil_match = re.search(
        r"(?:^|\n)\s*Mil\s*\n+\s*(\d[\d\s]*)\s*(?:\n|$)",
        text,
        re.IGNORECASE
    )

    if not pris_match:
        pris_match = PRIS_DETALJ_REGEX.search(
            text.replace("\n", " ")
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
        text.replace("\n", " ")
    )

    antal_agare = (
        int(agare_match.group(1))
        if agare_match
        else None
    )

    # ------------------------------------------------------------
    # Auktion
    # ------------------------------------------------------------

    ar_auktion = (
        AUKTION_REGEX.search(text)
        is not None
    )

    # ------------------------------------------------------------
    # Registreringsnummer
    #
    # OBS:
    # Detta använder samma "text" som redan hämtats.
    # Ingen ny requests.get().
    #
    # Endast explicit etikett accepteras.
    # ------------------------------------------------------------

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

    # Cache för detaljsidor under denna körning.
    detaljsida_cache = {}

    for bilkonfig in BILAR:

        arsmodell_min = bilkonfig.get(
            "arsmodell_min",
            ARSMODELL_MIN
        )

        arsmodell_max = bilkonfig.get(
            "arsmodell_max",
            ARSMODELL_MAX
        )

        for ar in range(
            arsmodell_min,
            arsmodell_max + 1
        ):

            kandidater = _hamta_kandidat_urler(
                bilkonfig,
                ar
            )

            rak_grundkrav = 0

            for kandidat in kandidater:

                url = kandidat["url"]

                # ------------------------------------------------
                # Cache:
                # samma detaljsida hämtas maximalt en gång.
                # ------------------------------------------------

                if url in detaljsida_cache:

                    resultat = detaljsida_cache[url]

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

                    detaljsida_cache[url] = resultat

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
                    bil["utrustningsniva"]
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
