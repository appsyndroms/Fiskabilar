"""
Data loading för Fiskabilar Analytics.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]

DATA_DIR = (
    ROOT / "data"
)

OUTPUT_DIR = (
    ROOT / "web_site"
)

STATE_FILE = (
    DATA_DIR / "state.json"
)

MARKET_HISTORY_DIR = (
    DATA_DIR / "market_history"
)

FIND_FEEDBACK_DIR = (
    DATA_DIR / "find_feedback"
)

ML_DIR = (
    DATA_DIR / "ml"
)


def read_json(
    path: Path,
    default: Any = None,
) -> Any:
    """
    Läser en JSON-fil.
    """

    if not path.exists():
        return default

    try:
        with path.open(
            "r",
            encoding="utf-8",
        ) as f:
            return json.load(f)

    except (
        OSError,
        json.JSONDecodeError,
    ):
        return default


def read_jsonl(
    path: Path,
) -> list[dict[str, Any]]:
    """
    Läser en JSONL-fil.

    Felaktiga enskilda rader hoppas över
    så att en trasig rad inte stoppar hela bygget.
    """

    rows: list[
        dict[str, Any]
    ] = []

    if not path.exists():
        return rows

    try:
        with path.open(
            "r",
            encoding="utf-8",
        ) as f:

            for line in f:
                line = line.strip()

                if not line:
                    continue

                try:
                    value = json.loads(
                        line
                    )

                except json.JSONDecodeError:
                    continue

                if isinstance(
                    value,
                    dict,
                ):
                    rows.append(
                        value
                    )

    except OSError:
        pass

    return rows


def read_all_jsonl(
    directory: Path,
    pattern: str = "*.jsonl",
) -> list[dict[str, Any]]:
    """
    Läser alla JSONL-filer i en katalog.
    """

    rows: list[
        dict[str, Any]
    ] = []

    if not directory.exists():
        return rows

    for path in sorted(
        directory.glob(pattern)
    ):
        rows.extend(
            read_jsonl(path)
        )

    return rows


def to_number(
    value: Any,
) -> float | None:
    """
    Konverterar ett värde till float.
    """

    if value is None:
        return None

    if isinstance(
        value,
        bool,
    ):
        return None

    try:
        return float(value)

    except (
        TypeError,
        ValueError,
    ):
        return None


def fmt_number(
    value: Any,
    decimals: int = 0,
) -> str:
    """
    Svensk nummerformatering.
    """

    number = to_number(
        value
    )

    if number is None:
        return "—"

    return (
        f"{number:,.{decimals}f}"
        .replace(",", " ")
    )


def fmt_price(
    value: Any,
) -> str:
    """
    Svensk prisformatering.
    """

    number = to_number(
        value
    )

    if number is None:
        return "—"

    return (
        f"{number:,.0f}"
        .replace(",", " ")
        + " kr"
    )


def safe(
    value: Any,
) -> str:
    """
    HTML-escape.
    """

    import html

    return html.escape(
        str(
            value
            if value is not None
            else ""
        )
    )
