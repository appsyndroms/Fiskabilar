"""
Scraper för Bilweb.

Bilwebs sökresultat används för att hitta kandidat-URL:er.
Detaljsidor hämtas parallellt och cachas under körningen.

Specialiserad logik ligger i:
    bilweb_bmw.py
    bilweb_regnr.py
    bilweb_scraper.py
"""

import re
import time

import requests
from bs4 import BeautifulSoup

from app_logging.logger import info

from config import (
    BILAR,
    ARSMODELL_MIN,
    ARSMODELL_MAX,
)

from sources import (
    grundkrav_fel,
    berika_fran_fritext,
    identifiera_variant,
)

from .bilweb_bmw import (
    normalisera_bmw_modellslug,
    bmw_kraver_detaljkontroll,
    kaross_matchar,
)

from .bilweb_scraper import (
    MAX_PARALLELLA_DETALJSIDOR,
    hamta_detaljsidor_parallellt,
)


SOK_DELAY_SEKUNDER = 0.2

SOK_URL_MALL = (
    "https://bilweb.se/sok/{marke}/{modell}/{ar}"
)

BILWEB_BASE_URL = "https://bilweb.se"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    ),
}


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

        slug_text = (
            normalisera_bmw_modellslug(
                slug_text
            )
        )

        variant = identifiera_variant(
            bilkonfig,
            slug_text,
        )

        detalj_karosskontroll = (
            bmw_kraver_detaljkontroll(
                bilkonfig,
                slug_text,
            )
        )

        if (
            variant is None
            and not detalj_karosskontroll
        ):

            if len(avvisade_slugs) < 5:
                avvisade_slugs.append(
                    slug_text
                )

            continue

        if detalj_karosskontroll:

            variant_kraven = bilkonfig.get(
                "variant_kraven",
                {}
            )

            if len(variant_kraven) == 1:

                variant = next(
                    iter(
                        variant_kraven
                    )
                )

            else:

                variant = (
                    bilkonfig.get(
                        "modell_visning"
                    )
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

    regnr_detaljsidor = 0
    regnr_hittade = 0

    detaljsidor_hamtade = 0
    detaljsidor_cachetraffar = 0

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

            (
                resultat_per_url,
                cachetraffar,
                nya_hamtningar,
            ) = hamta_detaljsidor_parallellt(
                kandidater,
                detaljsida_cache,
            )

            detaljsidor_cachetraffar += (
                cachetraffar
            )

            detaljsidor_hamtade += (
                nya_hamtningar
            )

            rak_grundkrav = 0

            for kandidat in kandidater:

                url = kandidat["url"]

                resultat = (
                    resultat_per_url.get(
                        url
                    )
                )

                if resultat is None:
                    continue

                pris = resultat["pris"]
                mil = resultat["miltal"]
                antal_agare = (
                    resultat["antal_agare"]
                )
                ar_auktion = (
                    resultat["auktion"]
                )
                regnr = resultat["regnr"]
                kaross = resultat["kaross"]
                detaljtext = resultat["text"]

                regnr_detaljsidor += 1

                if regnr:
                    regnr_hittade += 1

                if kandidat.get(
                    "kraver_karosskontroll",
                    False,
                ):

                    if not kaross_matchar(
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

                bil = berika_fran_fritext(
                    bil,
                    bil["utrustningsniva"],
                )

                fel = grundkrav_fel(
                    bil
                )

                if not fel:

                    rak_grundkrav += 1

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

    totaltid = (
        time.monotonic()
        - starttid
    )

    info(
        f"[bilweb] "
        f"{len(bilar)} annonser "
        f"matchade grundkraven totalt"
    )

    detaljsidor_totalt = (
        detaljsidor_hamtade
        + detaljsidor_cachetraffar
    )

    info(
        "[bilweb] PRESTANDA: "
        f"{detaljsidor_totalt} unika detaljsidor "
        f"behövdes totalt"
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
