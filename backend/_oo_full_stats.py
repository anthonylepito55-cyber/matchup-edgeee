"""The COMPLETE OpticOdds tennis stat field list, and how much of Model C it can feed."""
import json
import os
import urllib.parse
import urllib.request

BASE = "https://api.opticodds.com/api/v3"
HERE = "/home/ec2-user/mlb-predictor/backend"
with open(os.path.join(HERE, ".env"), encoding="utf-8", errors="replace") as fh:
    KEY = next(l.split("=", 1)[1].strip().strip('"').strip("'") for l in fh
               if l.strip().startswith("OPTICODDS_API_KEY"))


def get(path, params=None):
    q = ("?" + urllib.parse.urlencode(params, doseq=True)) if params else ""
    r = urllib.request.urlopen(urllib.request.Request(
        f"{BASE}{path}{q}", headers={"X-Api-Key": KEY, "Accept": "application/json"}),
        timeout=40)
    b = r.read().decode("utf-8", "replace")
    return json.loads(b) if b.strip().startswith(("{", "[")) else None


def items(d):
    v = d.get("data") if isinstance(d, dict) else d
    return v if isinstance(v, list) else ([v] if v else [])


fx = items(get("/fixtures", {"sport": "tennis", "league": "ATP", "status": "completed"}))
rs = items(get("/fixtures/results", {"fixture_id": fx[0]["id"]}))
st = (rs[0].get("stats") or {}).get("home") or []
blocks = {b.get("period"): b.get("stats") for b in st if isinstance(b, dict)}
print(f"match: {fx[0]['home_team_display']} vs {fx[0]['away_team_display']}")
print(f"stat blocks by period: {list(blocks)}\n")
all_s = blocks.get("all") or {}
print(f"COMPLETE FIELD LIST ({len(all_s)} fields):")
for k, v in sorted(all_s.items()):
    print(f"   {k:34s} {v}")

print("\n" + "=" * 84)
print("WHAT OF MODEL C IT CAN FEED")
print("=" * 84)
MAP = {
    "aces": "d_c_aces_pg (with games_won for the denominator)",
    "double_faults": "d_c_dfs_pg",
    "first_serves_in / first_serves_total": "d_m_first_serve_accuracy",
    "first_serve_points_won / _total": "d_m_first_serve_points",
    "second_serve_points_won / _total": "d_m_second_serve_points",
    "break_points_won / break_points_total": "d_c_bpconv",
    "games_won": "d_m_meff, and hold%/break% -> d_c_sgw / d_c_rgw",
    "service_games / return_games": "the service split -> d_c_sgw, d_c_rgw, per-game rates",
}
for k, v in MAP.items():
    probe = k.split(" /")[0].strip()
    print(f"   {'HAVE' if probe in all_s else 'no  '}  {k:42s} -> {v}")
missing = [w for w in ("unforced_errors", "winners", "service_games_won",
                       "return_games_won", "serve_pressure") if w not in all_s]
print(f"\n   absent: {missing}")
print("\n   per-period blocks mean set-by-set stats are available too, not just match totals.")
