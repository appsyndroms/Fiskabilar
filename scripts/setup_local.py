"""Skapa projektets egen Pythonmiljö. Kör med Python >= 3.11."""
import os
from pathlib import Path
import subprocess
import sys
import venv

ROOT = Path(__file__).resolve().parents[1]

if __name__ == "__main__":
    if sys.version_info < (3, 11):
        raise SystemExit("Python 3.11 eller senare behövs.")
    environment = ROOT / ".venv"
    if not (environment / "bin/python").exists():
        venv.EnvBuilder(with_pip=True).create(environment)
    subprocess.run([str(environment / "bin/python"), "-m", "pip", "install",
                    "-r", str(ROOT / "requirements.txt")], check=True)
    os.chmod(ROOT / "scripts/run_evening.sh", 0o755)
