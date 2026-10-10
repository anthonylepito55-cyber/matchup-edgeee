"""WHICH RAPIDAPI TENNIS HOST IS THIS KEY ACTUALLY SUBSCRIBED TO? (2026-10-10)

_ue_api_probe.py keeps getting 403 {"message":"You are not subscribed to this API."} from
tennis-api-atp-wta-itf.p.rapidapi.com even after the user subscribed. A 403 of that kind is
subscription-level, not path-level, so either the subscription has not propagated or it is
against a different listing whose host string differs.

RapidAPI has no public "list my subscriptions" endpoint, so this sends ONE minimal request per
candidate host and reports the status, which distinguishes the cases:
    200 / 404 / 400  -> the key IS authorized for that host (the request reached the API)
    403              -> not subscribed to that host
    429              -> throttled; wait and retry
Flashscore-derived hosts are deliberately NOT in the list -- that data is not usable here.

Costs one request per host against the free allowance.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

CANDIDATES = [
    "tennis-api-atp-wta-itf.p.rapidapi.com",      # the one we want (docs: matchstat.com)
    "ultimate-tennis1.p.rapidapi.com",
    "tennisapi1.p.rapidapi.com",
    "tennis-live-data.p.rapidapi.com",
]
PATH = "/tennis/v2/atp/rankings"                   # harmless; shape differs per host, that's fine


def key():
    k = os.environ.get("RAPIDAPI_KEY", "").strip()
    if k:
        return k
    f = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".rapidapi_key")
    try:
        with open(f, encoding="utf-8-sig") as fh:
            return fh.read().strip()
    except OSError:
        return ""


def main():
    k = key()
    if not k:
        print("no key found (backend/.rapidapi_key or RAPIDAPI_KEY)")
        return
    print(f"testing {len(CANDIDATES)} hosts with one request each\n")
    print(f"{'status':>7}  host")
    authorized = []
    for host in CANDIDATES:
        req = urllib.request.Request(
            f"https://{host}{PATH}",
            headers={"X-RapidAPI-Key": k, "X-RapidAPI-Host": host,
                     "Accept": "application/json", "User-Agent": "matchup-edge/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                st, body = r.status, r.read(200).decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            st, body = e.code, e.read(200).decode("utf-8", "replace")
        except Exception as e:  # noqa: BLE001
            st, body = None, str(e)[:120]
        note = ""
        try:
            note = (json.loads(body).get("message") or "")[:60]
        except Exception:  # noqa: BLE001
            note = body.replace("\n", " ")[:60]
        if st in (200, 400, 404):
            authorized.append(host)
            note = "AUTHORIZED (request reached the API) " + note
        print(f"{str(st):>7}  {host}\n{'':>9}{note}")
        time.sleep(1.0)
    print()
    if authorized:
        print("This key is subscribed to:")
        for h in authorized:
            print(f"  {h}")
        if CANDIDATES[0] not in authorized:
            print(f"\nBut NOT to {CANDIDATES[0]}, which is the one whose docs promise\n"
                  "player1Stats.unforcedErrors. Subscribe to that exact listing, or tell me\n"
                  "which host you did subscribe to and I will check whether it carries the field.")
    else:
        print("No candidate host authorized. Either the subscription has not propagated yet\n"
              "(wait a minute and re-run) or it is against a listing not in this list -- open the\n"
              "API's Endpoints tab on RapidAPI and read the X-RapidAPI-Host value from the code\n"
              "snippet; that string is what has to match.")
    sys.stdout.flush()


if __name__ == "__main__":
    main()
