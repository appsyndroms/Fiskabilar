"""
Data loading för Fiskabilar Analytics.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]

DATA_DIR = (
    ROOT / "data"
)

OUTPUT_DIR = Path(os.environ.get("FISKABILAR_WEB_OUTPUT", str(ROOT / "web_site")))

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

    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def read_jsonl(
    path: Path,
) -> list[dict[str, Any]]:
    """
    Läser en JSONL-fil.

    Befintliga filer måste vara giltiga; fel stoppar bygget i stället för
    att ge en grön webb med tyst bortfall av data.
    """

    rows: list[
        dict[str, Any]
    ] = []

    if not path.exists():
        return rows

    with path.open("r", encoding="utf-8") as handle:
        for number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise ValueError("Posten är inte ett objekt")
            except (ValueError, TypeError) as exc:
                raise ValueError(f"Ogiltig JSONL-post {path}:{number}") from exc
            rows.append(value)

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
        # macOS metadatafiler är inte datakällor.
        if path.name.startswith("._"):
            continue
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
