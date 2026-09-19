"""
Sparar kortsiktig körnings-/notifieringsstate.

State använder Fiskabilars identity resolution när vehicle_id
finns. Därmed följer notifieringshistoriken samma fysiska bil
även när annons-ID eller URL förändras.

Annonslivscykel:
- NY
- AKTIV
- SAKNAS
- FÖRSVUNNEN
- ÅTERKOMMEN
"""

from app_logging.logger import info

import json
import os
from datetime import date

from config import (
    STATE_FIL,
    MIN_DAGAR_FOR_SANKNING_RELEVANT,
    STOR_SANKNING_KR,
    MIN_PRISSANKNING_FOR_NY_NOTIS,
)

from .identity import (
    resolve_vehicle_id,
)


# En enstaka missad körning ska inte räcka för att kalla en
# annons försvunnen. Två konsekutiva missade körningar krävs.
ANTAL_MISSAR_FOR_FORSVUNNEN = 2


def _ar_pris(value) -> bool:
    """
    Avgör om ett värde är ett giltigt numeriskt pris.

    bool exkluderas eftersom bool ärver från int i Python.
    """
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
    )


def _nyckel(
    bil: dict,
) -> str:
    """
    Stabil nyckel för samma fysiska bil.

    Identity resolution är primär.
    Gamla nyckelformat finns kvar som fallback för
    bakåtkompatibilitet med äldre state.
    """

    vehicle_id = bil.get(
        "vehicle_id"
    )

    if vehicle_id:
        return str(
            vehicle_id
        )

    vehicle_id = resolve_vehicle_id(
        bil
    )

    if vehicle_id:
        return vehicle_id

    if bil.get("regnr"):
        return (
            "reg:"
            f"{str(bil['regnr']).upper().replace(' ', '')}"
        )

    if bil.get("annons_id"):
        return (
            "annons:"
            f"{str(bil['annons_id']).strip()}"
        )

    url = bil.get(
        "url"
    )

    if url:
        return (
            "url:"
            f"{str(url).strip().rstrip('/')}"
        )

    urls = bil.get(
        "urls"
    ) or []

    for kandidat in urls:
        if kandidat:
            return (
                "url:"
                f"{str(kandidat).strip().rstrip('/')}"
            )

    modell = (
        bil.get("modell")
        or "v60"
    ).lower()

    return (
        f"kal:{modell}:"
        f"{bil.get('variant')}:"
        f"{bil.get('arsmodell')}:"
        f"{bil.get('miltal')}"
    )


def _gammal_nyckel(
    bil: dict,
) -> str:
    modell = (
        bil.get("modell")
        or "v60"
    ).lower()

    return (
        f"kal:{modell}:"
        f"{bil.get('variant')}:"
        f"{bil.get('arsmodell')}:"
        f"{bil.get('miltal')}"
    )


def _hamta_historik(
    bil: dict,
    state: dict,
):
    nyckel = _nyckel(
        bil
    )

    historik = state.get(
        nyckel
    )

    if historik is not None:
        return (
            nyckel,
            historik,
        )

    gammal = _gammal_nyckel(
        bil
    )

    historik = state.get(
        gammal
    )

    if (
        historik is not None
        and nyckel != gammal
    ):
        state[
            nyckel
        ] = historik

        state[
            nyckel
        ][
            "migrerad_fran"
        ] = gammal

        return (
            nyckel,
            historik,
        )

    return (
        nyckel,
        None,
    )


def ladda_state() -> dict:
    if not os.path.exists(
        STATE_FIL
    ):
        return {}

    with open(
        STATE_FIL,
        "r",
        encoding="utf-8",
    ) as f:
        state = json.load(
            f
        )

    migrerade = False

    for historik in state.values():
        if not isinstance(
            historik,
            dict,
        ):
            continue

        if historik.get(
            "notifierad"
        ) is True:
            if (
                "notifierad_pris"
                not in historik
            ):
                pris = historik.get(
                    "senaste_pris"
                )

                if _ar_pris(pris):
                    historik[
                        "notifierad_pris"
                    ] = pris

                    migrerade = True

    if migrerade:
        info(
            "[STATE] Migrering klar: gamla "
            "notifieringar har fått notifierad_pris "
            "baserat på senaste kända pris."
        )

    return state


def spara_state(
    state: dict,
) -> None:
    os.makedirs(
        os.path.dirname(
            STATE_FIL
        ),
        exist_ok=True,
    )

    with open(
        STATE_FIL,
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            state,
            f,
            ensure_ascii=False,
            indent=2,
        )


def _normalisera_livscykel_state(
    historik: dict,
) -> None:
    """
    Säkerställer att äldre state får de fält som
    livscykeln behöver utan att befintlig historik ändras.
    """

    historik.setdefault(
        "status",
        "AKTIV",
    )

    historik.setdefault(
        "missade_korningar",
        0,
    )

    historik.setdefault(
        "antal_observationer",
        0,
    )

    historik.setdefault(
        "antal_prisandringar",
        0,
    )

    historik.setdefault(
        "prisandringar",
        [],
    )


def _registrera_prisandring(
    historik: dict,
    gammalt_pris,
    nytt_pris,
    datum: str,
) -> None:
    """
    Registrerar en faktisk förändring mellan två
    konsekutiva observationer.
    """

    if (
        not _ar_pris(gammalt_pris)
        or not _ar_pris(nytt_pris)
        or gammalt_pris == nytt_pris
    ):
        return

    forandring = (
        nytt_pris
        - gammalt_pris
    )

    historik[
        "antal_prisandringar"
    ] = (
        historik.get(
            "antal_prisandringar",
            0,
        )
        + 1
    )

    historik.setdefault(
        "prisandringar",
        [],
    ).append(
        {
            "datum": datum,
            "fran": gammalt_pris,
            "till": nytt_pris,
            "forandring": forandring,
        }
    )

    historik[
        "senaste_prisandring"
    ] = datum


def _markera_forsvunna(
    state: dict,
    dagens_nycklar: set[str],
    idag: str,
) -> None:
    """
    Markerar bilar som inte längre finns i dagens resultat.

    En missad körning ger SAKNAS.
    Två konsekutiva missade körningar ger FÖRSVUNNEN.

    När bilen återkommer senare återanvänds samma state
    tack vare identity resolution.
    """

    for nyckel, historik in state.items():

        if not isinstance(
            historik,
            dict,
        ):
            continue

        if nyckel in dagens_nycklar:
            continue

        _normalisera_livscykel_state(
            historik
        )

        missar = (
            historik.get(
                "missade_korningar",
                0,
            )
            + 1
        )

        historik[
            "missade_korningar"
        ] = missar

        if (
            missar
            >= ANTAL_MISSAR_FOR_FORSVUNNEN
        ):
            if (
                historik.get(
                    "status"
                )
                != "FÖRSVUNNEN"
            ):
                historik[
                    "forsvunnen_datum"
                ] = idag

            historik[
                "status"
            ] = "FÖRSVUNNEN"

        else:
            historik[
                "status"
            ] = "SAKNAS"


def uppdatera_och_berika(
    bilar: list[dict],
    state: dict,
) -> list[dict]:
    """
    Jämför dagens bilar mot sparad state och lägger till:

    - vehicle_id
    - dagar_ute
    - prissankning_kr
    - prissankning_relevant
    - livscykelstatus
    - prisandring

    Livscykeln följer bilen mellan körningar:

        NY
         ↓
       AKTIV
       ↙   ↘
    SAKNAS  PRISÄNDRING
       ↓
    FÖRSVUNNEN
       ↓
    ÅTERKOMMEN
       ↓
      AKTIV
    """

    idag = date.today().isoformat()

    # ------------------------------------------------------------
    # IDENTIFIERA DAGENS BILAR INNAN STATE ÄNDRAS
    # ------------------------------------------------------------

    dagens_nycklar = set()

    for bil in bilar:

        vehicle_id = resolve_vehicle_id(
            bil
        )

        bil[
            "vehicle_id"
        ] = vehicle_id

        nyckel = _nyckel(
            bil
        )

        dagens_nycklar.add(
            nyckel
        )

    # ------------------------------------------------------------
    # MARKERA BILAR SOM INTE FINNS I DAGENS RESULTAT
    # ------------------------------------------------------------

    _markera_forsvunna(
        state,
        dagens_nycklar,
        idag,
    )

    resultat = []

    # ------------------------------------------------------------
    # BEARBETA DAGENS BILAR
    # ------------------------------------------------------------

    for bil in bilar:

        vehicle_id = bil.get(
            "vehicle_id"
        )

        nyckel, historik = _hamta_historik(
            bil,
            state,
        )

        aktuellt_pris = bil.get(
            "annonspris"
        )

        # --------------------------------------------------------
        # NY BIL
        # --------------------------------------------------------

        if historik is None:

            giltigt_pris = (
                aktuellt_pris
                if _ar_pris(aktuellt_pris)
                else None
            )

            state[
                nyckel
            ] = {
                "vehicle_id": vehicle_id,
                "forsta_sedd": idag,
                "forsta_pris": giltigt_pris,
                "senaste_pris": giltigt_pris,
                "senast_sedd": idag,
                "notifierad": False,

                "status": "NY",
                "missade_korningar": 0,
                "antal_observationer": 1,
                "antal_prisandringar": 0,
                "prisandringar": [],
            }

            bil[
                "dagar_ute"
            ] = 0

            bil[
                "prissankning_kr"
            ] = 0

            bil[
                "prissankning_relevant"
            ] = False

            bil[
                "prisandring"
            ] = 0

            bil[
                "livscykelstatus"
            ] = "NY"

        # --------------------------------------------------------
        # BEFINTLIG BIL
        # --------------------------------------------------------

        else:

            _normalisera_livscykel_state(
                historik
            )

            tidigare_status = historik.get(
                "status",
                "AKTIV",
            )

            gammalt_pris = historik.get(
                "senaste_pris"
            )

            nytt_pris = bil.get(
                "annonspris"
            )

            # ----------------------------------------------------
            # PRISVALIDERING
            #
            # En misslyckad scraper/parser ska inte skriva över
            # ett tidigare giltigt pris med None.
            #
            # Om aktuell annons saknar pris används det senaste
            # giltiga priset för historikberäkning.
            # ----------------------------------------------------

            har_gammalt_pris = _ar_pris(
                gammalt_pris
            )

            har_nytt_pris = _ar_pris(
                nytt_pris
            )

            if not har_nytt_pris:
                nytt_pris_for_historik = (
                    gammalt_pris
                    if har_gammalt_pris
                    else None
                )
            else:
                nytt_pris_for_historik = nytt_pris

            # ----------------------------------------------------
            # FÖRSTA PRIS
            #
            # Äldre state kan ha saknat ett giltigt förstagångspris.
            # Om vi nu får ett giltigt pris fyller vi i det.
            # ----------------------------------------------------

            forsta_pris = historik.get(
                "forsta_pris"
            )

            if (
                not _ar_pris(forsta_pris)
                and har_nytt_pris
            ):
                forsta_pris = nytt_pris

                historik[
                    "forsta_pris"
                ] = forsta_pris

            forsta_sedd_text = historik.get(
                "forsta_sedd"
            )

            try:
                forsta_sedd = date.fromisoformat(
                    forsta_sedd_text
                )
            except (
                TypeError,
                ValueError,
            ):
                forsta_sedd = date.today()

                historik[
                    "forsta_sedd"
                ] = idag

            dagar_ute = (
                date.today()
                - forsta_sedd
            ).days

            # ----------------------------------------------------
            # PRISSÄNKNING
            # ----------------------------------------------------

            if (
                _ar_pris(forsta_pris)
                and har_nytt_pris
            ):
                sankning = (
                    forsta_pris
                    - nytt_pris
                )
            else:
                sankning = 0

            bil[
                "dagar_ute"
            ] = dagar_ute

            bil[
                "prissankning_kr"
            ] = sankning

            bil[
                "prissankning_relevant"
            ] = (
                sankning
                >= STOR_SANKNING_KR
                and dagar_ute
                >= MIN_DAGAR_FOR_SANKNING_RELEVANT
            )

            # ----------------------------------------------------
            # PRISÄNDRING
            # ----------------------------------------------------

            prisandrad = (
                har_gammalt_pris
                and har_nytt_pris
                and gammalt_pris
                != nytt_pris
            )

            if prisandrad:

                _registrera_prisandring(
                    historik,
                    gammalt_pris,
                    nytt_pris,
                    idag,
                )

                bil[
                    "prisandring"
                ] = (
                    nytt_pris
                    - gammalt_pris
                )

            else:

                bil[
                    "prisandring"
                ] = 0

            # ----------------------------------------------------
            # ÅTERKOMMEN
            # ----------------------------------------------------

            aterkommen = (
                tidigare_status
                == "FÖRSVUNNEN"
            )

            if aterkommen:

                historik[
                    "aterkommen_datum"
                ] = idag

                bil[
                    "livscykelstatus"
                ] = "ÅTERKOMMEN"

            else:

                bil[
                    "livscykelstatus"
                ] = "AKTIV"

            # ----------------------------------------------------
            # ÅTERSTÄLL AKTIV STATE
            # ----------------------------------------------------

            historik[
                "status"
            ] = (
                "ÅTERKOMMEN"
                if aterkommen
                else "AKTIV"
            )

            historik[
                "missade_korningar"
            ] = 0

            historik[
                "antal_observationer"
            ] = (
                historik.get(
                    "antal_observationer",
                    0,
                )
                + 1
            )

            # ----------------------------------------------------
            # SKRIV ALDRIG ÖVER ETT GILTIGT PRIS MED None
            # ----------------------------------------------------

            if har_nytt_pris:

                historik[
                    "senaste_pris"
                ] = nytt_pris

            elif not _ar_pris(
                historik.get(
                    "senaste_pris"
                )
            ):
                historik[
                    "senaste_pris"
                ] = None

            historik[
                "senast_sedd"
            ] = idag

            historik[
                "vehicle_id"
            ] = vehicle_id

        resultat.append(
            bil
        )

    return resultat


def redan_notifierad(
    bil: dict,
    state: dict,
) -> bool:
    nyckel, historik = _hamta_historik(
        bil,
        state,
    )

    historik = (
        historik
        or {}
    )

    if not historik.get(
        "notifierad",
        False,
    ):
        return False

    notifierad_pris = historik.get(
        "notifierad_pris"
    )

    if not _ar_pris(
        notifierad_pris
    ):
        return True

    aktuellt_pris = bil.get(
        "annonspris"
    )

    if not _ar_pris(
        aktuellt_pris
    ):
        return True

    return (
        aktuellt_pris
        > notifierad_pris
        - MIN_PRISSANKNING_FOR_NY_NOTIS
    )


def markera_notifierad(
    bil: dict,
    state: dict,
) -> None:
    nyckel, historik = _hamta_historik(
        bil,
        state,
    )

    if historik is not None:

        state[
            nyckel
        ][
            "notifierad"
        ] = True

        state[
            nyckel
        ][
            "notifierad_pris"
        ] = bil.get(
            "annonspris"
        )

        state[
            nyckel
        ][
            "vehicle_id"
        ] = bil.get(
            "vehicle_id"
        )
