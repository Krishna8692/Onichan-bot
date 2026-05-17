import httpx
import json
import sys

API_URL = "https://rootx-osint.in/?type=num&key=sachin&query={number}"
TG_API_URL = "https://invalid-tg-to-num-v2.pagals1818.workers.dev/?username={username}"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://rootx-osint.in/",
}

SKIP_KEYS = {"req_left", "req_total", "expiry", "developer"}


def lookup_number(number: str):
    url = API_URL.format(number=number)
    print(f"[*] Querying: {url}\n")
    with httpx.Client(timeout=15, verify=False, headers=HEADERS) as client:
        resp = client.get(url)
    print(f"[*] Status: {resp.status_code}\n")
    data = resp.json()
    clean = [item for item in data if isinstance(item, dict) and not SKIP_KEYS.intersection(item.keys())]
    if not clean:
        print("No data found.")
        return
    print(json.dumps(clean, indent=2, ensure_ascii=False))


def lookup_username(username: str):
    username = username.lstrip("@")
    url = TG_API_URL.format(username=username)
    print(f"[*] Querying: {url}\n")
    with httpx.Client(timeout=15) as client:
        resp = client.get(url)
    print(f"[*] Status: {resp.status_code}\n")
    data = resp.json()
    result = None
    if isinstance(data, list) and data:
        result = data[0]
    elif isinstance(data, dict):
        if data.get("number"):
            result = data
        elif data.get("data"):
            d = data["data"]
            result = d if isinstance(d, dict) else (d[0] if isinstance(d, list) and d else None)
    if not result or not result.get("number"):
        print("Username not found in database.")
        return
    print(f"USERNAME    : @{result.get('username', '-')}")
    print(f"TELEGRAM ID : {result.get('telegram_id', '-')}")
    print(f"NUMBER      : {result.get('country_code', '')}{result.get('number', '-')}")
    print(f"COUNTRY     : {result.get('country', '-')}")


def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python n_lookup.py 9955053727        # phone number lookup")
        print("  python n_lookup.py @username         # telegram username lookup")
        sys.exit(1)

    query = sys.argv[1].strip()

    if query.startswith("@") or (query.isalpha()):
        lookup_username(query)
    elif query.isdigit():
        lookup_number(query)
    else:
        print("Invalid input. Provide a phone number or @username.")
        sys.exit(1)


if __name__ == "__main__":
    main()
