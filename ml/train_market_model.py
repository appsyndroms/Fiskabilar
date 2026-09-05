"""
Träning av datadriven marknadsvärdering.

Modellen tränas på sparad historik i:

    data/market_history/*.jsonl

Målvariabel:
    Price = annonspris

Features:
    - Mil
    - ModelYear
    - Variant

Två modeller testas:

    1. Linjär regression
    2. Random Forest

Testdata hålls tidsmässigt separat från träningsdata för att
ge en bättre bild av hur modellen kan fungera på framtida
marknadsobservationer.

Resultatet sparas i:

    data/ml/market_model.joblib
    data/ml/model_metadata.json

Modulen påverkar inte den befintliga valuation-logiken ännu.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import joblib
import pandas as pd

from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder


TIDSZON = ZoneInfo("Europe/Stockholm")

HISTORIK_DIR = Path("data/market_history")
OUTPUT_DIR = Path("data/ml")

MODEL_FIL = OUTPUT_DIR / "market_model.joblib"
METADATA_FIL = OUTPUT_DIR / "model_metadata.json"

MIN_TRAINING_OBSERVATIONER = 30

FEATURES_NUMERIC = [
    "Mil",
    "ModelYear",
]

FEATURES_KATEGORISK = [
    "Variant",
]

FEATURES = FEATURES_NUMERIC + FEATURES_KATEGORISK

TARGET = "Price"


def _numeriskt(value):
    """Försöker konvertera ett värde till float."""

    if value is None:
        return None

    if isinstance(value, bool):
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalisera_variant(value) -> str | None:
    """Normaliserar modellvariant."""

    if value is None:
        return None

    text = str(value).strip()

    if not text:
        return None

    return text


def _ladda_jsonl() -> pd.DataFrame:
    """Läser all sparad marknadshistorik."""

    filer = sorted(
        HISTORIK_DIR.glob("market_history_*.jsonl")
    )

    legacy = HISTORIK_DIR / "market_history.jsonl"

    if legacy.exists():
        filer.append(legacy)

    if not filer:
        raise FileNotFoundError(
            f"Ingen marknadshistorik hittades i {HISTORIK_DIR}"
        )

    poster = []

    for fil in filer:
        with fil.open(
            "r",
            encoding="utf-8",
        ) as f:
            for radnummer, rad in enumerate(f, start=1):
                rad = rad.strip()

                if not rad:
                    continue

                try:
                    post = json.loads(rad)
                except json.JSONDecodeError:
                    print(
                        f"Varning: kunde inte läsa "
                        f"{fil}:{radnummer}"
                    )
                    continue

                if isinstance(post, dict):
                    post["_historikfil"] = fil.name
                    poster.append(post)

    if not poster:
        raise ValueError(
            "Historikfilerna innehåller inga giltiga JSONL-poster."
        )

    return pd.DataFrame(poster)


def _bygg_dataset(df: pd.DataFrame) -> pd.DataFrame:
    """
    Bygger träningsdataset från rå historik.

    Vi använder de faktiska fältnamnen från Fiskabilars
    marknadshistorik:

        annonspris
        miltal
        arsmodell
        variant
        tid
    """

    resultat = pd.DataFrame()

    resultat["Mil"] = pd.to_numeric(
        df.get("miltal"),
        errors="coerce",
    )

    resultat["ModelYear"] = pd.to_numeric(
        df.get("arsmodell"),
        errors="coerce",
    )

    resultat["Variant"] = (
        df.get("variant")
        .apply(_normalisera_variant)
    )

    resultat["Price"] = pd.to_numeric(
        df.get("annonspris"),
        errors="coerce",
    )

    resultat["Tid"] = pd.to_datetime(
        df.get("tid"),
        errors="coerce",
        utc=True,
    )

    # Pris, miltal och årsmodell krävs.
    resultat = resultat.dropna(
        subset=[
            "Mil",
            "ModelYear",
            "Price",
        ]
    )

    # Priset måste vara positivt.
    resultat = resultat[
        resultat["Price"] > 0
    ]

    # Miltal måste vara rimligt.
    resultat = resultat[
        resultat["Mil"] >= 0
    ]

    # Årsmodell måste vara rimlig.
    resultat = resultat[
        resultat["ModelYear"].between(
            1990,
            datetime.now(TIDSZON).year + 1,
        )
    ]

    # En saknad variant får behålla observationen.
    resultat["Variant"] = (
        resultat["Variant"]
        .fillna("Okänd")
    )

    # Sortera tidsmässigt.
    resultat = resultat.sort_values(
        "Tid",
        na_position="last",
    ).reset_index(drop=True)

    return resultat


def _deduplicera_dataset(
    df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Minskar risken att samma bil observerad många gånger
    får oproportionerligt stor påverkan på modellen.

    Om vehicle_id finns kan framtida versioner använda detta
    ännu bättre. Den första modellen håller sig medvetet till
    de features som roadmapen definierar.
    """

    nycklar = [
        "Mil",
        "ModelYear",
        "Variant",
        "Price",
    ]

    return df.drop_duplicates(
        subset=nycklar
    ).reset_index(drop=True)


def _skapa_preprocessor() -> ColumnTransformer:
    """Skapar gemensam preprocessing för modellerna."""

    numeric_pipeline = Pipeline(
        steps=[
            (
                "imputer",
                SimpleImputer(
                    strategy="median"
                ),
            )
        ]
    )

    categorical_pipeline = Pipeline(
        steps=[
            (
                "imputer",
                SimpleImputer(
                    strategy="most_frequent"
                ),
            ),
            (
                "onehot",
                OneHotEncoder(
                    handle_unknown="ignore"
                ),
            ),
        ]
    )

    return ColumnTransformer(
        transformers=[
            (
                "numeric",
                numeric_pipeline,
                FEATURES_NUMERIC,
            ),
            (
                "categorical",
                categorical_pipeline,
                FEATURES_KATEGORISK,
            ),
        ]
    )


def _bygg_modeller() -> dict[str, Pipeline]:
    """Returnerar modellerna som ska jämföras."""

    return {
        "linear_regression": Pipeline(
            steps=[
                (
                    "preprocessor",
                    _skapa_preprocessor(),
                ),
                (
                    "model",
                    LinearRegression(),
                ),
            ]
        ),
        "random_forest": Pipeline(
            steps=[
                (
                    "preprocessor",
                    _skapa_preprocessor(),
                ),
                (
                    "model",
                    RandomForestRegressor(
                        n_estimators=300,
                        max_depth=None,
                        min_samples_leaf=2,
                        random_state=42,
                        n_jobs=-1,
                    ),
                ),
            ]
        ),
    }


def _dela_tidsmässigt(
    df: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Delar historiken tidsmässigt.

    Äldre observationer används för träning och nyare
    observationer används för test.

    Detta är mer relevant för marknadsvärdering än en
    helt slumpmässig train/test-split.
    """

    sorterad = df.sort_values(
        "Tid",
        na_position="first",
    ).reset_index(drop=True)

    split_index = max(
        1,
        int(len(sorterad) * 0.8),
    )

    if split_index >= len(sorterad):
        split_index = len(sorterad) - 1

    train = sorterad.iloc[
        :split_index
    ].copy()

    test = sorterad.iloc[
        split_index:
    ].copy()

    return train, test


def _utvärdera(
    modell: Pipeline,
    x_test: pd.DataFrame,
    y_test: pd.Series,
) -> dict:
    """Beräknar modellens träffsäkerhet."""

    prediktioner = modell.predict(
        x_test
    )

    mae = mean_absolute_error(
        y_test,
        prediktioner,
    )

    rmse = mean_squared_error(
        y_test,
        prediktioner,
    ) ** 0.5

    r2 = r2_score(
        y_test,
        prediktioner,
    )

    return {
        "mae": round(float(mae), 2),
        "rmse": round(float(rmse), 2),
        "r2": round(float(r2), 4),
    }


def träna(
    spara: bool = True,
) -> dict:
    """Tränar, jämför och eventuellt sparar bästa modell."""

    rådata = _ladda_jsonl()

    dataset = _bygg_dataset(
        rådata
    )

    dataset = _deduplicera_dataset(
        dataset
    )

    antal = len(dataset)

    if antal < MIN_TRAINING_OBSERVATIONER:
        raise ValueError(
            "För lite historiskt underlag: "
            f"{antal} observationer. "
            f"Minst {MIN_TRAINING_OBSERVATIONER} krävs."
        )

    train, test = _dela_tidsmässigt(
        dataset
    )

    if len(test) == 0:
        raise ValueError(
            "Testdataset blev tomt."
        )

    x_train = train[
        FEATURES
    ]

    y_train = train[
        TARGET
    ]

    x_test = test[
        FEATURES
    ]

    y_test = test[
        TARGET
    ]

    modeller = _bygg_modeller()

    resultat = {}

    tränade_modeller = {}

    for namn, modell in modeller.items():

        modell.fit(
            x_train,
            y_train,
        )

        metrics = _utvärdera(
            modell,
            x_test,
            y_test,
        )

        resultat[namn] = metrics
        tränade_modeller[namn] = modell

        print(
            f"{namn}: "
            f"MAE={metrics['mae']:,.0f} kr, "
            f"RMSE={metrics['rmse']:,.0f} kr, "
            f"R²={metrics['r2']:.3f}"
        )

    # MAE är den primära jämförelsen eftersom den är lätt
    # att tolka som genomsnittligt kronor-fel.
    bästa_namn = min(
        resultat,
        key=lambda namn: resultat[namn]["mae"],
    )

    bästa_modell = tränade_modeller[
        bästa_namn
    ]

    metadata = {
        "skapad": datetime.now(
            TIDSZON
        ).isoformat(),

        "modell": bästa_namn,

        "features": FEATURES,

        "target": TARGET,

        "antal_observationer": antal,

        "antal_traning": len(train),

        "antal_test": len(test),

        "metrics": resultat,

        "historik_dir": str(
            HISTORIK_DIR
        ),
    }

    if spara:

        OUTPUT_DIR.mkdir(
            parents=True,
            exist_ok=True,
        )

        joblib.dump(
            bästa_modell,
            MODEL_FIL,
        )

        with METADATA_FIL.open(
            "w",
            encoding="utf-8",
        ) as f:
            json.dump(
                metadata,
                f,
                ensure_ascii=False,
                indent=2,
            )

        print()
        print(
            f"Bästa modell: {bästa_namn}"
        )

        print(
            f"Modell sparad i: {MODEL_FIL}"
        )

        print(
            f"Metadata sparad i: {METADATA_FIL}"
        )

    return metadata


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Tränar och utvärderar ML-modeller "
            "för marknadsvärdering."
        )
    )

    parser.add_argument(
        "--no-save",
        action="store_true",
        help="Träna och utvärdera utan att spara modellen.",
    )

    args = parser.parse_args()

    träna(
        spara=not args.no_save
    )


if __name__ == "__main__":
    main()
