"""Källfel måste stoppa körningen innan historik och state uppdateras."""
import re


class SourceFetchError(RuntimeError):
    """En aktiv datakälla kunde inte hämtas eller tolkas tillförlitligt."""


def require_html(response, source: str) -> None:
    """Avvisa HTTP-fel och vanliga tomma/spärrade felsvar med HTTP 200."""
    response.raise_for_status()
    content_type = response.headers.get("Content-Type", "").lower()
    if content_type and "text/html" not in content_type and "application/xhtml+xml" not in content_type:
        raise SourceFetchError(f"{source}: oväntad innehållstyp {content_type} från {response.url}")
    text = response.text
    if not text.strip():
        raise SourceFetchError(f"{source}: tomt HTML-svar från {response.url}")
    title = re.search(r"<title[^>]*>(.*?)</title>", text, re.IGNORECASE | re.DOTALL)
    if title and re.search(r"^(?:403|429|500|502|503)\b|access denied|just a moment|request blocked|attention required",
                           title.group(1).strip(), re.IGNORECASE):
        raise SourceFetchError(f"{source}: spärr- eller felsida från {response.url}")
