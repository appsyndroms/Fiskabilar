"""Skickar e-post via SMTP. Använder miljövariabler för lösenord
(sätts som secret i GitHub Actions - se README)."""

import os
import smtplib
from email.mime.text import MIMEText

from config import EPOST_TILL, EPOST_FRAN, SMTP_SERVER, SMTP_PORT


def skicka_epost(amne: str, brodtext: str) -> None:
    losenord = os.environ.get("EPOST_LOSENORD")
    if not losenord:
        print("VARNING: EPOST_LOSENORD saknas som miljövariabel/secret. "
              "Skriver ut meddelandet i loggen istället.")
        print(f"ÄMNE: {amne}\n{brodtext}")
        return

    msg = MIMEText(brodtext, "plain", "utf-8")
    msg["Subject"] = amne
    msg["From"] = EPOST_FRAN
    msg["To"] = EPOST_TILL

    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
        server.starttls()
        server.login(EPOST_FRAN, losenord)
        server.sendmail(EPOST_FRAN, [EPOST_TILL], msg.as_string())
