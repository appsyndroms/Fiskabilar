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
"""

import re
import time
import requests
from bs4 import BeautifulSoup

from config import BILAR, ARSMODELL_MIN, ARSMODELL_MAX
from scrapers import matchar_grundkrav, berika_fran_fritext, identifiera_variant

SOK_DELAY_SEKUNDER = 3.0
DETALJ_DELAY_SEKUNDER = 1.5

SOK_URL_MALL = "https://bilweb.se/sok/{marke}/{modell}/{ar}"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
}


PRIS_DETALJ_REGEX = re.compile(
    r"Pris\s*(?:\([^)]*\))?\s*\n*\s*([\d\s]+)\s*kr"
)

MIL_DETALJ_REGEX = re.compile(
    r"Mil\s*\n+\s*([\d\s]+?)\s*\n+[-\s]*1:a regdatum"
)

AGARE_DETALJ_REGEX = re.compile(
    r"Antal ägare\s*\n+\s*(\d+)"
)

AUKTION_REGEX = re.compile(
    r"auktionsobjekt",
    re.IGNORECASE
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
) -> tuple[int, int, int | None, bool] | None:

    """
    Hämtar en enskild annons egen sida och läser ut
    pris/mil/antal ägare.

    Returnerar:
        (pris, mil, antal_agare, ar_auktion)

    eller None om något gick fel.
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

    text = BeautifulSoup(
        resp.text,
        "html.parser"
    ).get_text(
        separator=" "
    )

    pris_match = PRIS_DETALJ_REGEX.search(
        text
    )

    mil_match = MIL_DETALJ_REGEX.search(
        text
    )

    if not pris_match or not mil_match:
        print(
            f"[bilweb]   Kunde inte tolka "
            f"pris/mil på detaljsidan: {url}"
        )
        return None

    agare_match = AGARE_DETALJ_REGEX.search(
        text
    )

    antal_agare = (
        int(agare_match.group(1))
        if agare_match
        else None
    )

    ar_auktion = (
        AUKTION_REGEX.search(text)
        is not None
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
    )


def hamta_annonser() -> list[dict]:

    print(
        "[bilweb] hämtar annonser..."
    )

    bilar = []
    rak_grundkrav_totalt = 0

    for bilkonfig in BILAR:

        # Varje bilmodell kan ha ett eget årsintervall.
        # Saknas modellens egna gränser används de globala.
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

                resultat = (
                    _hamta_pris_mil_fran_detaljsida(
                        kandidat["url"]
                    )
                )

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
                ) = resultat

                bil = {
                    "kalla": "bilweb",
                    "url": kandidat["url"],
                    "regnr": None,

                    "marke_slug":
                        bilkonfig["marke_slug"],

                    "modell_slug":
                        bilkonfig["modell_slug"],

                    "modell":
                        bilkonfig["modell_slug"],

                    "annonspris": pris,

                    "variant":
                        kandidat["variant"],

                    "arsmodell":
                        kandidat["arsmodell"],

                    "miltal": mil,

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

                if matchar_grundkrav(
                    bil
                ):
                    rak_grundkrav += 1
                    rak_grundkrav_totalt += 1

                    bilar.append(
                        bil
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

    return bilar
