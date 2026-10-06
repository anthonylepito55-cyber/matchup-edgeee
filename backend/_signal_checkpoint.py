"""Signal checkpoint (2026-10-05, user ask): diff current live lane ROIs against the frozen
baseline snapshot to see which edges HELD, FIRMED, or REGRESSED as more games settled.

Run on the box (hits localhost):  DASH_PW=xxx venv/bin/python _signal_checkpoint.py
Baseline = the newest _signal_baseline_*.json next to this file. Judges the lanes that were
POSITIVE on a decent sample (n>=15) at baseline -- the ones we'd actually bet -- per gender.
"""
import glob
import json
import os
import urllib.request

_here = os.path.dirname(os.path.abspath(__file__))
_base_path = sorted(glob.glob(os.path.join(_here, "_signal_baseline_*.json")))[-1]
B = json.load(open(_base_path, encoding="utf-8"))

_pw = os.environ.get("DASH_PW", "")
_req = urllib.request.Request("http://localhost/api/tennis/track-record",
                              headers={"X-Dashboard-Password": _pw})
st = json.load(urllib.request.urlopen(_req, timeout=60)).get("ab25", {}).get("study", {})


def cur(k, g):
    o = (st.get(k) or {}).get(g) or {}
    n = o.get("n") or 0
    return (round(o.get("roi_pct", 0), 1), o.get("wins", 0), n)


print("baseline captured:", B["captured"], "| source:", os.path.basename(_base_path))
for g, lab in (("m", "MEN"), ("w", "WOMEN")):
    print("\n==== %s : lanes that were +EV on n>=15 at baseline, then -> now ====" % lab)
    rows = []
    for k, v in B["lanes"].items():
        b = v.get(g, {})
        if b.get("n", 0) >= 15 and b.get("roi", 0) > 0:
            cr, cw, cn = cur(k, g)
            dn = cn - b["n"]
            flag = "FIRMED" if cr > b["roi"] + 2 else ("HELD" if cr > 0 else "REGRESSED")
            rows.append((cr, k, b, cr, cn, dn, flag))
    rows.sort(reverse=True)  # best current ROI first
    if not rows:
        print("  (none)")
    for _, k, b, cr, cn, dn, flag in rows:
        print("  %-18s %+6.1f%% (n%-3d) -> %+6.1f%% (n%-3d  +%d new)   %s"
              % (k, b["roi"], b["n"], cr, cn, dn, flag))
