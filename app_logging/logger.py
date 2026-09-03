"""
Central lognivå för Fiskabilar.

Nivåer:
    QUIET = 0
    INFO  = 1
    DEBUG = 2
    TRACE = 3

Om --log-level inte anges används QUIET.
"""
from __future__ import annotations

import argparse
import sys
from contextlib import contextmanager
from enum import IntEnum
from time import perf_counter
from typing import Iterator


class LogLevel(IntEnum):
    QUIET = 0
    INFO = 1
    DEBUG = 2
    TRACE = 3


_LEVEL = LogLevel.QUIET


def set_level(value: str | LogLevel | None) -> None:
    global _LEVEL

    if value is None:
        _LEVEL = LogLevel.QUIET
        return

    if isinstance(value, LogLevel):
        _LEVEL = value
        return

    try:
        _LEVEL = LogLevel[str(value).upper()]
    except KeyError as exc:
        raise ValueError(
            f"Okänd loggnivå: {value}. "
            "Giltiga nivåer: QUIET, INFO, DEBUG, TRACE."
        ) from exc


def get_level() -> LogLevel:
    return _LEVEL


def _write(message: str) -> None:
    print(
        message,
        file=sys.stdout,
        flush=True,
    )


def always(message: str) -> None:
    """
    Skriver alltid ut meddelandet, oberoende av loggnivå.

    Används för händelser som måste kunna granskas i exempelvis
    GitHub Actions även när körningen använder QUIET.
    """
    _write(
        str(message)
    )


def log(
    message: str,
    level: LogLevel = LogLevel.INFO,
) -> None:
    if _LEVEL >= level:
        _write(message)


def info(message: str) -> None:
    text = str(message)
    upper = text.upper()

    if (
        "FEL" in upper
        or "ERROR" in upper
        or "VARNING" in upper
    ):
        _write(text)
        return

    log(
        text,
        LogLevel.INFO,
    )


def debug(message: str) -> None:
    log(
        message,
        LogLevel.DEBUG,
    )


def trace(message: str) -> None:
    log(
        message,
        LogLevel.TRACE,
    )


def warning(message: str) -> None:
    # Varningar ska alltid synas även i QUIET.
    _write(message)


def error(message: str) -> None:
    # Fel ska alltid synas även i QUIET.
    _write(message)


@contextmanager
def debug_timer(
    label: str,
) -> Iterator[None]:
    """
    Mäter tiden för ett kodblock endast vid DEBUG eller TRACE.

    Vid QUIET/INFO startas ingen tidtagning och ingen diagnostik
    skrivs ut.
    """
    if _LEVEL < LogLevel.DEBUG:
        yield
        return

    start = perf_counter()

    try:
        yield
    finally:
        elapsed = perf_counter() - start
        debug(
            f"[TID] {label}: {elapsed:.2f} s"
        )


def configure_from_argv(
    argv: list[str] | None = None,
) -> LogLevel:
    parser = argparse.ArgumentParser(
        add_help=True
    )

    parser.add_argument(
        "--log-level",
        choices=(
            "QUIET",
            "INFO",
            "DEBUG",
            "TRACE",
        ),
        default=None,
        type=str.upper,
        help="Loggnivå. Standard: QUIET.",
    )

    args, _ = parser.parse_known_args(
        argv
    )

    set_level(
        args.log_level
    )

    return get_level()
