"""Kontrollera HTTP-anslutningen utan att skriva annonsdata."""
import json
import requests
from curl_cffi import requests as curl_requests

URL = "https://www.wayke.se/sok/volvo/v60/2023"
HEADERS = {"User-Agent": "Fiskabilar/1.0 (+https://github.com/appsyndroms/Fiskabilar)"}

def main():
    for name, get, options in [
        ("requests", requests.get, {}),
        ("curl", curl_requests.get, {}),
        ("curl-http2", curl_requests.get, {"impersonate": "chrome"}),
    ]:
        try:
            response = get(URL, headers=HEADERS, timeout=25, **options)
            print(json.dumps({"client": name, "status": response.status_code,
                "bytes": len(response.content), "cards": response.text.count("<article"),
                "server": response.headers.get("server"),
                "title": response.text[:200] if response.status_code != 200 else ""}), flush=True)
        except Exception as exc:
            print(json.dumps({"client": name, "error": str(exc)}), flush=True)

if __name__ == "__main__":
    main()
