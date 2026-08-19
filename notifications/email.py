"""Skickar e-post via SMTP. Använder miljövariabler för lösenord
(sätts som secret i GitHub Actions - se README)."""
from app_logging.logger import info

import os
import smtplib
from email.mime.text import MIMEText

from config import EPOST_TILL, EPOST_FRAN, SMTP_SERVER, SMTP_PORT


def skicka_epost(amne: str, brodtext: str) -> bool:
    """Returnerar True om mejlet faktiskt skickades, annars False.
    VIKTIGT: anroparen (main.py) måste kolla returvärdet - annars ser
    det ut som att mejl skickats även när det bara loggades ut."""
    losenord = os.environ.get("EPOST_LOSENORD")
    if not losenord:
        info("VARNING: EPOST_LOSENORD saknas som miljövariabel/secret - "
              "INGET MEJL SKICKAS. Kontrollera GitHub-secreten. "
              "Skriver ut meddelandet i loggen istället:")
        info(f"ÄMNE: {amne}\n{brodtext}")
        return False

    msg = MIMEText(brodtext, "plain", "utf-8")
    msg["Subject"] = amne
    msg["From"] = EPOST_FRAN
    msg["To"] = EPOST_TILL

    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(EPOST_FRAN, losenord)
            server.sendmail(EPOST_FRAN, [EPOST_TILL], msg.as_string())
        return True
    except Exception as e:
        info(f"FEL vid mejlutskick: {e}")
        info(f"(ÄMNE var: {amne})")
        return False
