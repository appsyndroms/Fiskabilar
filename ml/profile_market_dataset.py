"""
CLI för profilering av Fiskabilars historiska marknadsdata.

Exempel:

    python ml/profile_market_dataset.py data/market_history

eller:

    python ml/profile_market_dataset.py data/market_history/market_history_2026-08.jsonl

Scriptet läser datasetet, profilerar det och skriver ut en
reproducerbar rapport.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from ml.market_dataset_loader import (
    extract_dataset,
    load_jsonl,
    load_jsonl_files,
)

from ml.market_dataset_profiling import (
    profile_dataset,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Profilerar historiska bilannonser "
            "inför ML."
        )
    )

    parser.add_argument(
        "input",
        help=(
            "Sökväg till en JSONL-fil eller "
            "katalog med JSONL-filer."
        ),
    )

    parser.add_argument(
        "--encoding",
        default="utf-8",
        help="Filens encoding. Standard: utf-8.",
    )

    return parser.parse_args()


def fmt(value: Any) -> str:
    """Formaterar tal för rapporten."""

    if value is None:
        return "-"

    if isinstance(value, float):
        if value.is_integer():
            value = int(value)
        else:
            return (
                f"{value:,.2f}"
                .replace(",", " ")
            )

    if isinstance(value, int):
        return (
            f"{value:,}"
            .replace(",", " ")
        )

    return str(value)


def print_separator() -> None:
    print("-" * 78)


def print_profile(
    profile: dict[str, Any],
    input_path: Path,
) -> None:
    pipeline = profile["pipeline"]

    print()
    print("=" * 78)
    print("FISKABILAR – MARKET DATA PROFILE")
    print("=" * 78)
    print()
    print(f"Dataset: {input_path}")
    print()

    print("1. DATASET-PIPELINE")
    print_separator()

    print(
        f"Råposter:                    "
        f"{fmt(pipeline['raw'])}"
    )

    print(
        f"Saknade obligatoriska fält: "
        f"{fmt(pipeline['raw'] - pipeline['after_required_fields'])}"
    )

    print(
        f"Efter obligatoriska fält:    "
        f"{fmt(pipeline['after_required_fields'])}"
    )

    print(
        f"Efter giltigt pris:          "
        f"{fmt(pipeline['after_price'])}"
    )

    print(
        f"Efter giltigt miltal:        "
        f"{fmt(pipeline['after_mileage'])}"
    )

    print(
        f"Efter giltig årsmodell:      "
        f"{fmt(pipeline['after_model_year'])}"
    )

    print(
        f"Före deduplicering:          "
        f"{fmt(pipeline['before_deduplication'])}"
    )

    print(
        f"Efter deduplicering:         "
        f"{fmt(pipeline['after_deduplication'])}"
    )

    print()

    print("2. BORTFALL")
    print_separator()

    print(
        f"Saknat miltal:               "
        f"{fmt(pipeline['removed_missing_mileage'])}"
    )

    print(
        f"Saknad årsmodell:            "
        f"{fmt(pipeline['removed_missing_model_year'])}"
    )

    print(
        f"Saknat pris:                 "
        f"{fmt(pipeline['removed_missing_price'])}"
    )

    print(
        f"Orimligt pris:               "
        f"{fmt(pipeline['removed_invalid_price'])}"
    )

    print(
        f"Orimligt miltal:             "
        f"{fmt(pipeline['removed_invalid_mileage'])}"
    )

    print(
        f"Orimlig årsmodell:           "
        f"{fmt(pipeline['removed_invalid_model_year'])}"
    )

    print(
        f"Duplicerade poster:          "
        f"{fmt(pipeline['duplicates_removed'])}"
    )

    print()

    print("3. PRIS / MILTAL / ÅRSMODELL")
    print_separator()

    print(
        f"{'Fält':<15}"
        f"{'Antal':>10}"
        f"{'Min':>15}"
        f"{'Median':>15}"
        f"{'Max':>15}"
    )

    for field in (
        "price",
        "mileage",
        "model_year",
    ):
        stats = profile["statistics"][field]

        print(
            f"{field:<15}"
            f"{fmt(stats['count']):>10}"
            f"{fmt(stats['min']):>15}"
            f"{fmt(stats['median']):>15}"
            f"{fmt(stats['max']):>15}"
        )

    print()

    print("4. EXAKTA VARIANT-VÄRDEN")
    print_separator()

    for variant, count in sorted(
        profile["variants"].items(),
        key=lambda item: (
            -item[1],
            str(item[0]),
        ),
    ):
        print(
            f"{str(variant):<40}"
            f"{fmt(count):>10}"
        )

    print()

    print("5. VARIANT × ÅRSMODELL")
    print_separator()

    for (
        variant,
        year,
    ), count in sorted(
        profile["variant_model_year"].items(),
        key=lambda item: (
            str(item[0][0]),
            str(item[0][1]),
        ),
    ):
        print(
            f"{str(variant):<30}"
            f"{str(year):>12}"
            f"{fmt(count):>10}"
        )

    print()

    print("6. OBSERVATIONER PER MÅNAD")
    print_separator()

    for month, count in sorted(
        profile["observations_by_month"].items()
    ):
        print(
            f"{month:<20}"
            f"{fmt(count):>15}"
        )

    print()

    print("7. METADATA COVERAGE")
    print_separator()

    for field, data in (
        profile["metadata_coverage"].items()
    ):
        print(
            f"{field:<20}"
            f"{fmt(data['count']):>12}"
            f"{data['percentage']:>10.2f} %"
        )

    print()

    print("8. HISTORISKT TIDSINTERVALL")
    print_separator()

    history = profile["history"]

    print(
        f"Första observation: "
        f"{history['first'] or '-'}"
    )

    print(
        f"Sista observation:  "
        f"{history['last'] or '-'}"
    )

    print(
        f"Med tidsstämpel:    "
        f"{fmt(history['count_with_timestamp'])}"
    )

    print()

    print("9. SAMMANFATTNING")
    print_separator()

    raw = pipeline["raw"]
    final = pipeline["after_deduplication"]

    retention = (
        final / raw * 100
        if raw
        else 0
    )

    print(
        f"{fmt(raw)} råposter"
    )

    print(
        "    ↓ obligatoriska fält"
    )

    print(
        f"{fmt(pipeline['after_required_fields'])}"
    )

    print(
        "    ↓ giltigt pris"
    )

    print(
        f"{fmt(pipeline['after_price'])}"
    )

    print(
        "    ↓ giltigt miltal"
    )

    print(
        f"{fmt(pipeline['after_mileage'])}"
    )

    print(
        "    ↓ giltig årsmodell"
    )

    print(
        f"{fmt(pipeline['after_model_year'])}"
    )

    print(
        "    ↓ deduplicering"
    )

    print(
        f"{fmt(final)} ML-observationer"
    )

    print()

    print(
        f"Retention: {retention:.2f} %"
    )

    print()

    print("=" * 78)
    print("Profilering klar.")
    print("=" * 78)
    print()


def resolve_input_files(
    input_path: Path,
) -> list[Path]:
    """
    Returnerar de JSONL-filer som ska profileras.

    Om input är en fil används endast den filen.

    Om input är en katalog används:
        *.jsonl

    Filerna sorteras så att körningen blir reproducerbar.
    """

    if input_path.is_file():
        if input_path.suffix.lower() != ".jsonl":
            raise ValueError(
                f"Filen är inte en JSONL-fil: "
                f"{input_path}"
            )

        return [input_path]

    if input_path.is_dir():
        files = sorted(
            input_path.glob("*.jsonl")
        )

        if not files:
            raise FileNotFoundError(
                f"Inga JSONL-filer hittades i "
                f"{input_path}"
            )

        return files

    raise FileNotFoundError(
        f"Sökvägen finns inte: {input_path}"
    )


def main() -> int:
    args = parse_args()

    input_path = Path(args.input)

    try:
        files = resolve_input_files(
            input_path
        )
    except (
        FileNotFoundError,
        ValueError,
    ) as exc:
        print(
            str(exc),
            file=sys.stderr,
        )
        return 1

    print()

    print(
        f"Profilerar {len(files)} JSONL-fil(er):"
    )

    for file in files:
        print(
            f"  - {file}"
        )

    print()

    if len(files) == 1:
        raw_records = load_jsonl(
            files[0],
            encoding=args.encoding,
        )
    else:
        raw_records = load_jsonl_files(
            files,
            encoding=args.encoding,
        )

    if not raw_records:
        print(
            "Datasetet innehåller inga "
            "giltiga poster.",
            file=sys.stderr,
        )
        return 1

    observations = extract_dataset(
        raw_records
    )

    profile = profile_dataset(
        observations
    )

    print_profile(
        profile,
        input_path,
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
