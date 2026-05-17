import httpx
import html as html_lib
import sys

API_URL = "https://abhigyan-codes-tg-to-number-api.onrender.com/@abhigyan_codes/userid={userid}"


def lookup_userid(userid: str):
    if not userid.isdigit():
        print("Invalid user ID. Must be numeric.")
        sys.exit(1)

    url = API_URL.format(userid=userid)
    print(f"[*] Querying: {url}\n")

    with httpx.Client(timeout=30) as client:
        resp = client.get(url)

    print(f"[*] Status: {resp.status_code}\n")
    data = resp.json()

    result = data.get("result", {})
    if "number" not in result:
        result = result.get("result", {})

    country      = result.get("country", "N/A")
    country_code = result.get("country_code", "N/A")
    number       = result.get("number", "N/A")

    if number == "N/A":
        print("Not found.")
        return

    print(f"Country      : {country}")
    print(f"Country Code : {country_code}")
    print(f"Number       : {number}")


def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python tg_lookup.py 123456789    # Telegram user ID lookup")
        sys.exit(1)

    userid = sys.argv[1].strip()
    lookup_userid(userid)


if __name__ == "__main__":
    main()
