"""DO THE USER'S OWN API KEYS DELIVER FINISHED MATCHES FASTER THAN TENNISRATIO? (2026-10-10)

The earlier probes tested these feeds for UNFORCED ERRORS and they came back null at every
level. That is a different question from SPEED, which was never tested.

The in-session tennis-stats MCP server answers on `/tennis/v2/{tour_type}/results/{date}` but
returns "You are not subscribed to this API" -- that is the MCP's own credential. The user's
`.rapidapi_key` is for `tennis-api-atp-wta-itf.p.rapidapi.com`, the SAME underlying API and the
same path shape, so their key may be authorized where the MCP's is not.

Measured against our own board for the same days: TennisRatio had 8% of today's matches and
37-38% of the last two days' stat lines, while Polymarket/TennisExplorer settled 95-100%
same-day. Anything that beats 8% today is an improvement on TennisRatio; anything that carries
serve/return/BP numbers same-day would be a genuine upgrade, because nothing we have does.

Keys are read from gitignored files at run time and never printed.
Budget: the free RapidAPI tier is ~50 requests/day, so this spends at most 4.
"""
import json
import os
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
HOST = "tennis-api-atp-wta-itf.p.rapidapi.com"


def read_key(name):
    p = os.path.join(HERE, name)
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8-sig") as fh:
        return fh.read().strip()


def shape(k):
    """Describe a key WITHOUT revealing it, so the log is safe to paste anywhere."""
    if not k:
        return "absent"
    pre = k.split("_")[0] + "_" if "_" in k[:8] else ""
    return (f"{len(k)} chars, {'prefix ' + pre if pre else 'no prefix'}, "
            f"{'uuid-shaped' if k.count('-') == 4 else 'opaque'}")


def get(url, headers, label, budget):
    if budget[0] <= 0:
        print(f"   {label}: SKIPPED (budget spent)")
        return None
    budget[0] -= 1
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            body = r.read().decode("utf-8", "replace")
            print(f"   {label}: HTTP {r.status}, {len(body)} bytes")
            try:
                return json.loads(body)
            except json.JSONDecodeError:
                print(f"      not JSON: {body[:160]}")
                return None
    except urllib.error.HTTPError as e:
        msg = e.read().decode("utf-8", "replace")[:200]
        print(f"   {label}: HTTP {e.code} -- {msg}")
    except Exception as e:  # noqa: BLE001
        print(f"   {label}: {type(e).__name__}: {e}")
    return None


def walk(o, depth=0, hits=None):
    """Collect the leaf field names, to see whether a stat line is present."""
    hits = hits if hits is not None else set()
    if depth > 4:
        return hits
    if isinstance(o, dict):
        for k, v in o.items():
            hits.add(k)
            walk(v, depth + 1, hits)
    elif isinstance(o, list) and o:
        walk(o[0], depth + 1, hits)
    return hits


print("=" * 86)
print("KEY INVENTORY (contents never printed)")
print("=" * 86)
K1 = read_key(".rapidapi_key")
K2 = read_key(".key2")
print(f"   .rapidapi_key  {shape(K1)}")
print(f"   .key2          {shape(K2)}")

budget = [4]
print("\n" + "=" * 86)
print("A. RAPIDAPI tennis-api-atp-wta-itf -- the same API the MCP server could not reach")
print("=" * 86)
if not K1:
    print("   no key file")
else:
    H = {"X-RapidAPI-Key": K1, "X-RapidAPI-Host": HOST, "Accept": "application/json"}
    for tour, date in (("wta", "2026-10-10"), ("atp", "2026-10-10")):
        q = urllib.parse.urlencode({"pageNo": 1, "pageSize": 50,
                                    "filter": "PlayerGroup:singles"})
        d = get(f"https://{HOST}/tennis/v2/{tour}/results/{date}?{q}",
                H, f"{tour.upper()} results {date}", budget)
        if not d:
            continue
        rows = d.get("data") or d.get("results") or (d if isinstance(d, list) else [])
        if isinstance(rows, dict):
            rows = rows.get("results") or rows.get("data") or []
        print(f"      finished singles matches returned: {len(rows)}")
        if rows:
            f = walk(rows[0])
            print(f"      top-level row fields: {sorted(list(f))[:22]}")
            statish = sorted(x for x in f if any(w in x.lower() for w in
                             ("ace", "serve", "break", "point", "stat", "winner",
                              "error", "double")))
            print(f"      stat-looking fields: {statish if statish else 'NONE'}")
            r0 = rows[0]
            keep = {k: v for k, v in r0.items() if not isinstance(v, (dict, list))}
            print(f"      sample row: {json.dumps(keep)[:400]}")

print("\n" + "=" * 86)
print("B. .key2 -- which service is it, and does it serve results?")
print("=" * 86)
if not K2:
    print("   no key file")
else:
    print(f"   shape suggests: {'livetennisapi (twjp_ prefix)' if K2.startswith('twjp') else 'unknown service'}")
    # try the plausible livetennisapi bases; a 401/404 costs nothing and still tells us
    # whether the host exists and whether the key is accepted at all
    for base, path in (("https://api.livetennisapi.com", "/v1/matches/today"),
                       ("https://livetennisapi.com/api", "/matches/today")):
        get(f"{base}{path}?key={urllib.parse.quote(K2)}", {"Accept": "application/json"},
            f"{base}{path}", budget)
print(f"\nrequests spent: {4 - budget[0]} of 4")
print("\nBENCHMARK TO BEAT -- our own board, same days:")
print("   2026-10-10: TennisRatio had 8% of matches, 5% with a stat line")
print("   2026-10-09: TennisRatio 75% of matches, 38% with a stat line")
print("   Polymarket/TennisExplorer: 95-100% settled same-day (scores only, no stats)")
