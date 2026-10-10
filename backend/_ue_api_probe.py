"""DOES THE RAPIDAPI TENNIS FEED ACTUALLY CARRY UNFORCED ERRORS AT ITF / CHALLENGER LEVEL?
(2026-10-10, user: "would I be able to use rapidapi flashscore to get the stats")

Background. Every free route to unforced errors failed: Flashscore and Sofascore forbid or block
automated access, ATP and the US Open robots-block their stats paths, and the sources that do
permit access -- the WTA API, TennisExplorer -- have no unforced-errors field at all. The Match
Charting Project has real numbers but covers 1.8% of our logged matches and 0% of ITF.

`tennis-api-atp-wta-itf.p.rapidapi.com` (docs: tennisapidoc.matchstat.com) is the first
legitimate feed whose documented response actually contains the field:
    data.player1Stats.unforcedErrors / data.player2Stats.unforcedErrors
documented as "Unforced errors (where tracked)", with `atp`/`wta` covering "all supported
levels, not only the ATP Tour ... can include Grand Slams, ATP/WTA events, Challengers and ITF".

That hedging -- "where tracked", "where supported", "null means not available for the match" --
is the whole question, and it is exactly what killed the other leads. The women's LOW-ERROR DOG
edge (+11.1%, n=361) lives in +100..+250 women's dogs, which are mostly ITF/W-level. A feed that
only populates the field for tour matches buys us nothing, because the Match Charting Project
already covers tour matches better than it would.

So this probes the field against OUR OWN logged matches, level by level, and reports the non-null
rate per level. The FREE tier is 50 requests/day with the same payload as PRO, so one run answers
it at no cost.

USAGE -- the key is yours and never touches this repo:
    export RAPIDAPI_KEY=...            # set it in the shell, not in a file
    cd backend && venv/bin/python _ue_api_probe.py

The key is read from the environment, sent only as a header, and never printed or written. Run it
server-side. If the verdict is that ITF rows come back null, stop there and do not subscribe.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

import pandas as pd

HOST = "tennis-api-atp-wta-itf.p.rapidapi.com"
def _key():
    """From the environment, else from backend/.rapidapi_key (gitignored).

    The file exists so the key never has to be pasted into a chat or a command line: write it
    there once, chmod 600, and this reads it at run time. The value is only ever sent as a
    request header -- it is never printed, logged or written anywhere else.
    """
    k = os.environ.get("RAPIDAPI_KEY", "").strip()
    if k:
        return k
    f = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".rapidapi_key")
    try:
        with open(f, encoding="utf-8") as fh:
            return fh.read().strip()
    except OSError:
        return ""


KEY = _key()
BUDGET = int(os.environ.get("RAPIDAPI_BUDGET", "45"))      # stay inside the free 50/day
PER_LEVEL = int(os.environ.get("RAPIDAPI_PER_LEVEL", "6"))
used = 0


def call(path, params=None):
    """One GET. Returns (status, parsed_json_or_text). Never logs the key."""
    global used
    if used >= BUDGET:
        return None, "budget exhausted"
    url = f"https://{HOST}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={
        "X-RapidAPI-Key": KEY, "X-RapidAPI-Host": HOST,
        "Accept": "application/json", "User-Agent": "matchup-edge/1.0"})
    used += 1
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            body = r.read().decode("utf-8", "replace")
            try:
                return r.status, json.loads(body)
            except ValueError:
                return r.status, body[:400]
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:400]
        return e.code, body
    except Exception as e:  # noqa: BLE001
        return None, str(e)
    finally:
        time.sleep(0.3)                                     # 4 req/sec free-tier limit


def find_ue(obj, trail=""):
    """Walk a response and return every path whose key mentions unforced, with its value."""
    out = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            p = f"{trail}.{k}" if trail else k
            if "unforced" in k.lower():
                out.append((p, v))
            out += find_ue(v, p)
    elif isinstance(obj, list):
        for i, v in enumerate(obj[:3]):
            out += find_ue(v, f"{trail}[{i}]")
    return out


def main():
    if not KEY:
        print("No key found.\n"
              "Subscribe to the FREE tier of 'Tennis API ATP WTA ITF' on RapidAPI -- 50 requests\n"
              "a day, same payload as PRO -- then put the key in a file this reads at run time:\n"
              "    printf '%s' 'YOUR_KEY' > backend/.rapidapi_key && chmod 600 backend/.rapidapi_key\n"
              "(or export RAPIDAPI_KEY in your shell). The file is gitignored. The key is only\n"
              "ever sent as a request header -- never printed, logged or committed.")
        return

    # our own matches, newest first, grouped by level -- these are the games we actually bet
    L = pd.read_parquet("data_cache/tennis_prediction_log.parquet")
    L = L[(L["settled"] == True) & L["player_1"].notna()].copy()  # noqa: E712
    L["d"] = L["date"].astype(str).str[:10]
    L = L.sort_values("d", ascending=False)

    print(f"probing {HOST} | budget {BUDGET} requests\n")

    # 1. does the key work at all, and which path shape serves match stats by name?
    sample = L.iloc[0]
    tour = "wta" if str(sample["league"]).startswith(("wta", "itf_women")) else "atp"
    p1 = urllib.parse.quote(str(sample["player_1"]))
    p2 = urllib.parse.quote(str(sample["player_2"]))
    candidates = [
        f"/tennis/v2/{tour}/h2h/match-stats/{p1}/{p2}",
        f"/tennis/v2/h2h/match-stats/{p1}/{p2}",
        f"/tennis/v2/{tour}/h2h/{p1}/{p2}",
    ]
    working = None
    for path in candidates:
        st, body = call(path)
        print(f"  {st}  {path}")
        if st == 200:
            hits = find_ue(body)
            print(f"        unforced fields found: {hits if hits else 'NONE in this payload'}")
            if hits:
                working = path.replace(p1, "{p1}").replace(p2, "{p2}")
                break
        elif st == 403:
            print(f"        {str(body)[:160]}")
        if used >= BUDGET:
            break
    if not working:
        print("\nNo name-based path returned an unforced-errors field. The documented route is\n"
              "  /tennis/v2/{atp|wta}/h2h/match-stats/{tournamentId}/{player1Id}/{player2Id}\n"
              "which needs NUMERIC ids. Check the /misc and /players doc pages for the search\n"
              "endpoint, add it here, and re-run. Requests used: " + str(used))
        return

    # 2. the real question: per level, how often is the field non-null?
    print(f"\nusing: {working}\n")
    print("level            tried  got stats  UE non-null")
    verdict = {}
    for lg in ("itf_women", "itf_men", "atp_challenger", "wta", "atp"):
        G = L[L["league"].astype(str) == lg].head(PER_LEVEL)
        if G.empty:
            continue
        tried = ok = nn = 0
        for _, r in G.iterrows():
            if used >= BUDGET:
                break
            t = "wta" if lg.startswith(("wta", "itf_women")) else "atp"
            path = working.replace("{p1}", urllib.parse.quote(str(r["player_1"]))) \
                          .replace("{p2}", urllib.parse.quote(str(r["player_2"])))
            path = path.replace("/atp/", f"/{t}/").replace("/wta/", f"/{t}/")
            st, body = call(path)
            tried += 1
            if st == 200:
                ok += 1
                hits = find_ue(body)
                if any(v is not None for _, v in hits):
                    nn += 1
        verdict[lg] = (tried, ok, nn)
        print(f"  {lg:14s} {tried:5d} {ok:10d} {nn:12d}")
        if used >= BUDGET:
            print("  (budget exhausted)")
            break

    itf = sum(v[2] for k, v in verdict.items() if k.startswith("itf"))
    itf_t = sum(v[0] for k, v in verdict.items() if k.startswith("itf"))
    ch = verdict.get("atp_challenger", (0, 0, 0))
    print(f"\nrequests used: {used}")
    print("VERDICT")
    print(f"  ITF:        {itf}/{itf_t} matches came back with a real unforced-error number")
    print(f"  challenger: {ch[2]}/{ch[0]}")
    if itf_t and itf == 0 and ch[2] == 0:
        print("  -> the field is NOT populated below tour level. Do not subscribe: this buys\n"
              "     nothing the Match Charting Project does not already cover better.")
    elif itf:
        print("  -> ITF unforced errors ARE populated. This is the one source that fills the\n"
              "     gap; worth pricing the paid tier and wiring an ingest.")
    else:
        print("  -> inconclusive on ITF; re-run tomorrow with a fresh 50 or raise PER_LEVEL.")
    sys.stdout.flush()


if __name__ == "__main__":
    main()
