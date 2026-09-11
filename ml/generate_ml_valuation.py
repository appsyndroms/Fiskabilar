"""
Genererar data/ml_valuation.jsonl från den tränade ML-modellen.

Flöde:

    market_history
        ↓
    train_market_model.py
        ↓
    market_model.joblib
        ↓
    predict_market_value.py
        ↓
    ml_valuation.jsonl

Filen används därefter av valuation-systemet.
"""

from __future__ import annotations

import json
from pathlib import Path

from config import (
    BILAR,
    MAX_MIL,
    MIN_MIL,
    ML_VARDERING_FIL,
)
from ml.predict_market_value import (
    modell_finns,
    prediktera_borpris,
)


MILSTEG = 500


def _milintervall() -> list[int]:
    """Skapar de miltal som ska värderas."""

    resultat = list(
        range(
            MIN_MIL,
            MAX_MIL + 1,
            MILSTEG,
        )
    )

    if not resultat:
        raise ValueError(
            "Inget giltigt milintervall."
        )

    if resultat[-1] != MAX_MIL:
        resultat.append(
            MAX_MIL
        )

    return sorted(
        set(resultat)
    )


def _generera_rader() -> list[dict]:
    """Genererar alla ML-värderingar."""

    if not modell_finns():
        raise FileNotFoundError(
            "Ingen tränad ML-modell finns. "
            "Kör först ml.train_market_model."
        )

    rader = []

    miltal = _milintervall()

    for bil in BILAR:
        modell = bil[
            "modell_visning"
        ]

        arsmodell_min = int(
            bil["arsmodell_min"]
        )

        arsmodell_max = int(
            bil["arsmodell_max"]
        )

        for arsmodell in range(
            arsmodell_min,
            arsmodell_max + 1,
        ):
            for variant in (
                bil[
                    "variant_kraven"
                ].keys()
            ):
                for mil in miltal:
                    borpris = (
                        prediktera_borpris(
                            modell=modell,
                            mil=mil,
                            arsmodell=arsmodell,
                            variant=variant,
                        )
                    )

                    if borpris is None:
                        continue

                    rader.append(
                        {
                            "modell": modell,
                            "variant": variant,
                            "arsmodell": arsmodell,
                            "mil": mil,
                            "borpris": borpris,
                        }
                    )

    return rader


def skriv_ml_valuation() -> int:
    """Skriver den kompletta ML-värderingsfilen."""

    rader = _generera_rader()

    if not rader:
        raise ValueError(
            "ML-modellen producerade inga "
            "värderingsrader."
        )

    path = Path(
        ML_VARDERING_FIL
    )

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with path.open(
        "w",
        encoding="utf-8",
    ) as file:
        for rad in rader:
            file.write(
                json.dumps(
                    rad,
                    ensure_ascii=False,
                )
                + "\n"
            )

    return len(rader)


def main() -> None:
    """CLI-entrypoint."""

    antal = skriv_ml_valuation()

    print(
        "=========================================="
    )

    print(
        "ML-värdering genererad"
    )

    print(
        f"Fil: {ML_VARDERING_FIL}"
    )

    print(
        f"Antal rader: {antal}"
    )

    print(
        "=========================================="
    )


if __name__ == "__main__":
    main()
