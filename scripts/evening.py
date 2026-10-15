"""En lokal kvällskedja med lås, fast rapportdatum och granskningsbar status."""
from __future__ import annotations

import argparse
from datetime import datetime
import fcntl
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / ".local"
TZ = ZoneInfo("Europe/Stockholm")


def now() -> str:
    return datetime.now(TZ).isoformat(timespec="seconds")


def save_status(status: dict) -> None:
    path = LOCAL / ("web-build-status.json" if status.get("mode") == "web" else "evening-status.json")
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(status, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(path)


def archive_valuations() -> None:
    """Rotera utifrån befintliga värderingars månad, även vid missade kördagar."""
    current = ROOT / "data/ml_valuation.jsonl"
    if not current.exists():
        return
    with current.open() as handle:
        first = next((json.loads(line) for line in handle if line.strip()), {})
    marker = LOCAL / "valuation-month.txt"
    stamp = first.get("tid") or first.get("generated_at")
    month = (marker.read_text().strip() if marker.exists() else
             datetime.fromisoformat(stamp).strftime("%Y-%m") if stamp else
             datetime.fromtimestamp(current.stat().st_mtime, TZ).strftime("%Y-%m"))
    if month == datetime.now(TZ).strftime("%Y-%m"):
        return
    archive = ROOT / "data/ml_valuation_archive" / f"{month}.jsonl"
    archive.parent.mkdir(parents=True, exist_ok=True)
    if not archive.exists():
        shutil.copy2(current, archive)


def validate_web(directory: Path | None = None) -> None:
    directory = directory or ROOT / "web_site"
    for name in ("index.html", "data.json", ".nojekyll"):
        if not (directory / name).is_file():
            raise RuntimeError(f"Webbfil saknas: {name}")
    data = json.loads((directory / "data.json").read_text())
    required = {"generated_at", "summary", "current_findings", "price_reductions",
                "find_outcomes", "score_analysis", "market_history", "ml"}
    if required - data.keys():
        raise RuntimeError(f"Ofullständig webbdata: {required - data.keys()}")
    if "<html" not in (directory / "index.html").read_text().lower():
        raise RuntimeError("Webbens HTML är ogiltig")


def publish_web(staging: Path) -> None:
    """Ersätt först efter validering och återställ förra webben om flytten misslyckas."""
    live = ROOT / "web_site"
    with tempfile.TemporaryDirectory(prefix="previous-web-", dir=LOCAL) as backup_dir:
        backup = Path(backup_dir) / "web_site"
        if live.exists():
            live.rename(backup)
        try:
            staging.rename(live)
        except OSError:
            if backup.exists():
                backup.rename(live)
            raise


def run(build_only: bool = False) -> int:
    os.chdir(ROOT)
    LOCAL.mkdir(exist_ok=True)
    with (LOCAL / "evening.lock").open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("En kvällskörning pågår redan.", flush=True)
            return 1
        day = datetime.now(TZ).date().isoformat()
        status = {"date": day, "started_at": now(), "status": "running",
                  "mode": "web" if build_only else "full", "steps": [],
                  "web_url": os.getenv("FISKABILAR_WEBB_URL", "http://127.0.0.1:8766")}
        status["email_status"] = "disabled"
        save_status(status)
        env = dict(os.environ, TZ="Europe/Stockholm", FISKABILAR_ONLY_DAILY_REPORT="1",
                   FISKABILAR_WEBB_URL=status["web_url"])
        env.pop("EPOST_LOSENORD", None)

        def step(name: str, command: list[str]) -> None:
            record = {"name": name, "started_at": now(), "status": "running"}
            status["steps"].append(record)
            save_status(status)
            print(f"\n[{now()}] {name}", flush=True)
            result = subprocess.run([sys.executable, "-u", *command], cwd=ROOT, env=env)
            record.update(finished_at=now(), returncode=result.returncode,
                          status="success" if result.returncode == 0 else "failed")
            save_status(status)
            result.check_returncode()

        try:
            if not build_only:
                step("Datainsamling och fyndanalys", ["main.py", "--evening", "--log-level", "INFO"])
                if datetime.now(TZ).date().isoformat() != day:
                    raise RuntimeError("Datainsamlingen passerade midnatt; kör om för den nya dagen.")
                step("Fyndutfall", ["scripts/analysera_fyndutfall.py"])
                step("Daglig rapport", ["-m", "reporting.daily_market_report", "--date", day, "--no-email"])
                from reporting.daily_market_report import _las_dagens_logg
                report = _las_dagens_logg(day)
                if not report or report.get("status") == "FEL":
                    raise RuntimeError("Den dagliga rapporten kunde inte byggas.")
                step("Träna ML-modell och diagnostik", ["-m", "ml.train_market_model"])
                archive_valuations()
                step("ML-värderingar", ["-m", "ml.generate_ml_valuation"])
                (LOCAL / "valuation-month.txt").write_text(datetime.now(TZ).strftime("%Y-%m"))
            with tempfile.TemporaryDirectory(prefix="web-build-", dir=LOCAL) as directory:
                staging = Path(directory)
                env["FISKABILAR_WEB_OUTPUT"] = str(staging)
                step("Bygg lokal webb", ["web/build_static.py"])
                validate_web(staging)
                publish_web(staging)
            status.update(status="complete", finished_at=now())
            save_status(status)
            print(f"Klart: {status['web_url']}", flush=True)
            return 0
        except Exception as exc:
            status.update(status="failed", finished_at=now(), error=str(exc))
            save_status(status)
            print(f"Kvällskörningen misslyckades: {exc}", file=sys.stderr)
            return 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--build-only", action="store_true", help="Bygg bara webben från sparad data.")
    raise SystemExit(run(parser.parse_args().build_only))
