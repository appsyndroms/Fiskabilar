"""Waykes publika marknadsplatssökning, samma operation som deras webbklient.

Inga partnernycklar eller cookies används. Version/hash kommer från webbklientens
SearchAdsV2-operation. Om kontraktet ändras ska insamlingen stoppa.
"""
import math
import time
from uuid import UUID

import requests

from app_logging.logger import info
from .errors import SourceFetchError

URL = "https://edge.wayke.se/graphql"
VERSION = "65de099d88709fae3920d0950fe0de8ab5dda456"
DOCUMENT_HASH = "b8c8d3a78216c81f81070460270abba5306fb521dcb894cf645839f7d7972839"
HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Origin": "https://www.wayke.se",
    "Referer": "https://www.wayke.se/",
    "Accept": "application/graphql-response+json, application/json",
    "x-graphql-client-version": VERSION,
}
PAGE_SIZE = 24
MAX_PAGES = 100
DELAY_SECONDS = 3


def variables(config, year, page):
    result = {"market": ["SE"], "manufacturer": [config["marke_visning"]],
              "modelYearMin": year, "modelYearMax": year,
              "page": page, "perPage": PAGE_SIZE, "withFacets": False}
    if config["marke_slug"] == "volvo":
        result["modelSeries"] = [config["modell_visning"]]
    else:
        result["model"] = [config["modell_visning"]]
    return result


def fetch_page(config, year, page):
    response = requests.post(URL, headers=HEADERS, timeout=25, json={
        "documentId": f"wayke-web-ui~{VERSION}~{DOCUMENT_HASH}",
        "operationName": "SearchAdsV2", "variables": variables(config, year, page),
    })
    response.raise_for_status()
    if "json" not in response.headers.get("Content-Type", "").lower():
        raise SourceFetchError("Wayke API: svarade med annat än JSON.")
    payload = response.json()
    if not isinstance(payload, dict) or payload.get("errors"):
        raise SourceFetchError("Wayke API: GraphQL-fel, även eventuella delresultat avvisas.")
    try:
        result = payload["data"]["search"]["ads"]
        found, hits = result["found"], result["hits"]
        if (type(found) is not int or found < 0 or not isinstance(hits, list)
                or result["page"] != page or result["perPage"] != PAGE_SIZE
                or len(hits) > PAGE_SIZE):
            raise ValueError("ogiltig paginering")
    except (KeyError, TypeError, ValueError) as exc:
        raise SourceFetchError("Wayke API: söksvarets schema har ändrats.") from exc
    return result


def number(value):
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError("bool i numeriskt fält")
    result = float(value)
    if not math.isfinite(result) or result < 0:
        raise ValueError("ogiltigt numeriskt värde")
    return int(result) if result.is_integer() else result


def parse_hit(hit, config, year):
    try:
        ad, iteration = hit["ad"], hit["iteration"]
        identity = str(UUID(ad["id"]))
        item = iteration["item"]
        actual_year = item["modelYear"]["intValue"]
        if type(actual_year) is not int:
            raise ValueError("ogiltig årsmodell")
        if actual_year != year:
            info(f"[wayke API] Filtrerar bort {identity}: faktisk årsmodell {actual_year}, sökår {year}.")
            return None
        if item["manufacturer"]["stringValue"].casefold() != config["marke_visning"].casefold():
            return None
        model_field = "modelSeries" if config["marke_slug"] == "volvo" else "modelName"
        if item[model_field]["stringValue"].casefold() != config["modell_visning"].casefold():
            return None
        channels = ad["channels"]
        if not isinstance(channels, list) or not channels:
            raise ValueError("kanalstatus saknas")
        if not any(c.get("status") == "PUBLISHED" and not c.get("soldAt")
                   and c.get("inventoryStatus") != "Sold" for c in channels):
            return None
        description = ad["salesDescription"]
        title = " ".join(dict.fromkeys(x.strip() for x in (
            description.get("title") or "", description.get("subtitle") or "",
            item["modelName"]["stringValue"]) if x.strip()))
        cash = (ad["pricing"].get("cash") or {}).get("price") or {}
        if cash.get("amount") is not None and cash.get("currency") != "SEK":
            raise ValueError("fel valuta")
        reading = (iteration.get("logistics") or {}).get("odometerReading")
        mileage = None
        if reading is not None:
            mileage = number(reading["value"])
            if reading["unit"] == "KILOMETER":
                mileage = mileage / 10 if mileage is not None else None
            elif reading["unit"] != "SCANDINAVIAN_MILE":
                raise ValueError("okänd enhet för mätarställning")
        branch = ad["branch"]
        return {"url": f"https://www.wayke.se/objekt/{identity}", "titel": title,
                "pris": number(cash.get("amount")), "miltal": mileage,
                "arsmodell": year, "gearbox": item["attributes"]["transmission"]["formattedValue"],
                "fuel": item["driveline"]["fuelTypesString"]["stringValue"],
                "plats": branch.get("city") or "", "dealer": branch.get("displayName") or ""}
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise SourceFetchError(f"Wayke API: ogiltig eller felmatchad annons: {exc}") from exc


def hamta_annonskort(config, year):
    cards, seen = [], set()
    expected = None
    for page in range(1, MAX_PAGES + 1):
        result = fetch_page(config, year, page)
        if expected is None:
            expected = result["found"]
        if result["found"] != expected:
            raise SourceFetchError("Wayke API: antal annonser ändrades under pagineringen; kör om.")
        hits = result["hits"]
        if not hits and len(seen) < expected:
            raise SourceFetchError("Wayke API: tom sida innan alla annonser hämtats.")
        for hit in hits:
            card = parse_hit(hit, config, year)
            identity = hit["ad"]["id"]
            if identity in seen:
                raise SourceFetchError("Wayke API: upprepad annons mellan resultatsidor.")
            seen.add(identity)
            if card is not None:
                cards.append(card)
        info(f"[wayke API] {config['modell_visning']} {year}, sida {page}: {len(hits)} annonser")
        if len(seen) == expected:
            return cards
        if len(seen) > expected:
            raise SourceFetchError("Wayke API: fler annonser än utlovat.")
        time.sleep(DELAY_SECONDS)
    raise SourceFetchError("Wayke API: sidgränsen nåddes; ofullständig insamling avvisas.")
