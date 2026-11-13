"""Skicka den sparade kvällsrapporten efter lyckad webbpublicering."""
import argparse
from datetime import date
from . import daily_market_report as reports


def send(day: str, web_url: str) -> bool:
    day = date.fromisoformat(day).isoformat()
    post = reports._las_dagens_logg(day)
    if not post or post.get("status") == "FEL" or not post.get("rapport", "").strip():
        raise RuntimeError(f"Ingen giltig sparad kvällsrapport för {day}.")
    if post.get("email_skickat"):
        print(f"Kvällsrapport {day} är redan mejlad; inget nytt utskick.", flush=True)
        return False
    text = post["rapport"] + f"\n\nWebbpubliceringen är klar: {web_url}\n"
    if not reports.skicka_epost(f"Fiskabilar – kvällsrapport och webb {day}", text):
        raise RuntimeError("Kvällsrapportens mejl kunde inte skickas.")
    post = dict(post, email_skickat=True,
                email_skickat_tid=reports._nu().isoformat(timespec="seconds"),
                webb_url=web_url)
    reports._spara_logg(post)
    print(f"Kvällsrapport {day}: mejl skickat efter webbpublicering.", flush=True)
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True)
    parser.add_argument("--web-url", required=True)
    args = parser.parse_args()
    send(args.date, args.web_url)
