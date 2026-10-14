"""Skapa eller installera Macens kvällsschema och lokala webbserver."""
import argparse
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / ".local"


def definitions() -> list[dict]:
    common = {
        "WorkingDirectory": str(ROOT),
        "EnvironmentVariables": {
            "PATH": f"{ROOT / '.venv/bin'}:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin",
            "TZ": "Europe/Stockholm",
        },
    }
    return [
        {**common, "Label": "se.fiskabilar.evening",
         "ProgramArguments": ["/bin/bash", str(ROOT / "scripts/run_evening.sh")],
         "StartCalendarInterval": {"Hour": 22, "Minute": 0},
         "StandardOutPath": str(LOCAL / "logs/scheduler.log"),
         "StandardErrorPath": str(LOCAL / "logs/scheduler-error.log")},
        {**common, "Label": "se.fiskabilar.web",
         "ProgramArguments": [str(ROOT / ".venv/bin/python"), "-m", "http.server",
                              "8766", "--bind", "127.0.0.1", "--directory", str(ROOT / "web_site")],
         "RunAtLoad": True, "KeepAlive": True, "ThrottleInterval": 10,
         "StandardOutPath": str(LOCAL / "logs/web.log"),
         "StandardErrorPath": str(LOCAL / "logs/web-error.log")},
    ]


def main(install: bool) -> None:
    generated = LOCAL / "launchd"
    generated.mkdir(parents=True, exist_ok=True)
    (LOCAL / "logs").mkdir(exist_ok=True)
    for definition in definitions():
        source = generated / f"{definition['Label']}.plist"
        source.write_bytes(plistlib.dumps(definition))
        if install:
            if sys.platform != "darwin":
                raise SystemExit("Automatiskt schema kräver macOS.")
            destination = Path.home() / "Library/LaunchAgents" / source.name
            destination.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(["launchctl", "bootout", f"gui/{os.getuid()}/{definition['Label']}"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            shutil.copy2(source, destination)
            subprocess.run(["launchctl", "bootstrap", f"gui/{os.getuid()}", str(destination)], check=True)
            print(f"Installerad: {definition['Label']}")
        else:
            print(source)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--install", action="store_true", help="Installera och aktivera LaunchAgents.")
    main(parser.parse_args().install)
