"""WHAT DOES THE OPTICODDS KEY GIVE FOR TENNIS? (2026-10-10, user ask)

Memory says the key died and the board fell back to public Polymarket Gamma, auto-reverting if
OpticOdds came back. The key is still configured in backend/.env, so first question is whether
it is alive at all -- and if it is, what tennis surfaces it actually serves.

The high-value question after today: does it carry POST-MATCH STATISTICS? TennisRatio is the
only stat-line source we have and it runs 37-55% for the freshest three days. A sportsbook feed
would not normally carry serve/return stats, but OpticOdds does publish results and player
surfaces for some sports, so it is worth asking rather than assuming.

Key is read from the environment / .env at run time and never printed.
Deliberately few calls, in case the plan is rate- or credit-limited.
"""
import json
import os
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://api.opticodds.com/api/v3"
HERE = os.path.dirname(os.path.abspath(__file__))


def load_key():
    k = os.environ.get("OPTICODDS_API_KEY")
    if k:
        return k.strip()
    p = os.path.join(HERE, ".env")
    if os.path.exists(p):
        with open(p, encoding="utf-8", errors="replace") as fh:
            for ln in fh:
                if ln.strip().startswith("OPTICODDS_API_KEY") and "=" in ln:
                    return ln.split("=", 1)[1].strip().strip('"').strip("'")
    return None


KEY = load_key()
print(f"key loaded: {bool(KEY)} ({len(KEY) if KEY else 0} chars)\n")


def get(path, params=None, label=None):
    q = ("?" + urllib.parse.urlencode(params)) if params else ""
    url = f"{BASE}{path}{q}"
    req = urllib.request.Request(url, headers={"X-Api-Key": KEY,
                                               "Accept": "application/json"})
    lab = label or path
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            body = r.read().decode("utf-8", "replace")
            print(f"  {lab:46s} HTTP {r.status}  {len(body)} bytes")
            return json.loads(body) if body.strip().startswith(("{", "[")) else None
    except urllib.error.HTTPError as e:
        msg = e.read().decode("utf-8", "replace")[:160].replace("\n", " ")
        print(f"  {lab:46s} HTTP {e.code}  {msg}")
    except Exception as e:  # noqa: BLE001
        print(f"  {lab:46s} {type(e).__name__}: {e}")
    return None


def items(d):
    if not d:
        return []
    v = d.get("data") if isinstance(d, dict) else d
    return v if isinstance(v, list) else ([v] if v else [])


print("=" * 86)
print("1. IS THE KEY ALIVE?")
print("=" * 86)
sports = get("/sports", label="/sports")
names = []
for s in items(sports):
    nm = s.get("name") or s.get("id") if isinstance(s, dict) else str(s)
    names.append(str(nm))
if names:
    print(f"     sports on the plan ({len(names)}): {sorted(names)[:14]}")
    print(f"     tennis present: {any('tennis' in n.lower() for n in names)}")

print("\n" + "=" * 86)
print("2. TENNIS LEAGUES -- does it cover ITF/Challenger as well as tour?")
print("=" * 86)
lg = get("/leagues", {"sport": "tennis"}, "/leagues?sport=tennis")
ln = []
for x in items(lg):
    if isinstance(x, dict):
        ln.append(str(x.get("name") or x.get("id")))
if ln:
    print(f"     {len(ln)} leagues: {sorted(ln)[:25]}")

print("\n" + "=" * 86)
print("3. MARKETS -- what can be priced (sets, games, totals, props?)")
print("=" * 86)
mk = get("/markets", {"sport": "tennis"}, "/markets?sport=tennis")
mn = sorted({str(x.get("name") or x.get("id")) for x in items(mk) if isinstance(x, dict)})
if mn:
    print(f"     {len(mn)} markets. A sample: {mn[:30]}")
    props = [m for m in mn if any(w in m.lower() for w in
             ("ace", "double", "break", "game", "player", "total"))]
    print(f"     prop/stat-shaped markets: {props[:20]}")

print("\n" + "=" * 86)
print("4. FIXTURES + do they carry RESULTS or STATS?")
print("=" * 86)
fx = get("/fixtures", {"sport": "tennis", "status": "completed"},
         "/fixtures?sport=tennis&status=completed")
fi = items(fx)
print(f"     completed fixtures returned: {len(fi)}")
if fi:
    f0 = fi[0]
    flat = {k: v for k, v in f0.items() if not isinstance(v, (dict, list))}
    print(f"     fixture fields: {sorted(f0.keys())}")
    print(f"     sample: {json.dumps(flat)[:320]}")
    fid = f0.get("id") or f0.get("fixture_id")
    if fid:
        for path, lab in (("/fixtures/results", "results"),
                          ("/fixtures/player-results", "player-results")):
            d = get(path, {"fixture_id": fid}, f"{path} (fixture {fid})")
            it = items(d)
            if it:
                s = json.dumps(it[0])
                print(f"       {lab} fields: {sorted(it[0].keys()) if isinstance(it[0], dict) else type(it[0])}")
                low = s.lower()
                print("       stat check: " + ", ".join(
                    f"{w}={'Y' if w in low else '-'}" for w in
                    ("ace", "double_fault", "first_serve", "break_point", "unforced",
                     "games_won", "points")))

print("\n" + "=" * 86)
print("5. SPORTSBOOKS available for tennis (what the price scanner could shop)")
print("=" * 86)
sb = get("/sportsbooks", {"sport": "tennis"}, "/sportsbooks?sport=tennis")
bn = sorted({str(x.get("name") or x.get("id")) for x in items(sb) if isinstance(x, dict)})
if bn:
    print(f"     {len(bn)} books: {bn[:30]}")
    for want in ("Kalshi", "Polymarket", "Pinnacle", "FanDuel", "DraftKings", "Circa"):
        print(f"       {want:12s} {'YES' if any(want.lower() in b.lower() for b in bn) else '--'}")
