"""Skickade fynd per annonslänk, oberoende av ändrade fordons-ID:n."""
from functools import lru_cache
import json
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

PATH = Path("data/notification_history.json")


def urls(car):
    values = [car.get("url"), *(car.get("urls") or [])]
    result = set()
    for value in values:
        if not isinstance(value, str) or not value.strip():
            continue
        parts = urlsplit(value.strip())
        if parts.scheme in ("http", "https") and parts.netloc:
            result.add(urlunsplit(("https", parts.netloc.lower(), parts.path.rstrip("/"), "", "")))
    return result


@lru_cache(maxsize=1)
def load():
    if not PATH.exists():
        return {}
    value = json.loads(PATH.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Ogiltig notifieringshistorik")
    for item in value.values():
        price = item.get("price") if isinstance(item, dict) else None
        if type(price) not in (int, float) or not 0 < price < float("inf"):
            raise ValueError("Ogiltigt notifierat pris")
    return value


def prices(car):
    data = load()
    return [data[url]["price"] for url in urls(car) if url in data]


def record(car):
    price = car.get("annonspris")
    if type(price) not in (int, float) or not 0 < price < float("inf"):
        raise ValueError("Kan inte spara notifiering utan giltigt pris")
    data = dict(load())
    for url in urls(car):
        previous = data.get(url, {}).get("price", price)
        data[url] = {"price": min(price, previous)}
    PATH.parent.mkdir(parents=True, exist_ok=True)
    temp = PATH.with_suffix(".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(PATH)
    load.cache_clear()
