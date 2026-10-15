"""BUILD MC6's STATE: recent H2H + surface-form residual (2026-10-15).

MC6 is MC2's blend plus two terms (see tennis_mc6.py). Those terms need their own state, built
here from the same archive MC2 trains on and keyed on the SAME player slugs, so the two heads can
never disagree about who a player is.

WHAT IS STORED

  h2h[pairkey]        the last few meetings as (day, won_by_first, games_margin, surface).
                      The raw meetings are stored rather than a pre-computed weighted share
                      because the weighting is by AGE IN DAYS -- a share computed at build time
                      would silently stop decaying until the next rebuild, and a 300-day-old
                      meeting must not be read tomorrow as if it were fresh. Capped at the 12
                      most recent meetings per pair; beyond that the 365-day half-life has
                      reduced the weight below 1e-3.

  sform[(slug,surf)]  the exponentially-weighted mean of (result - what Elo expected) over that
                      player's matches on that surface, 5-match half-life. A MATCH-count
                      half-life, so unlike the H2H term it does not need decaying at read time.
                      The RESIDUAL is the point: a plain surface win rate would mostly re-state
                      Elo, while the residual is the part Elo has not absorbed.

  asof                the last date in the archive, so a stale state is visible rather than
                      silent. tennis_mc6 reports it and the nightly job replaces it.

Written temp -> validate -> atomic replace, with a .bak, matching the ratings rebuild that fixed
the 4-day staleness on 2026-10-13. A half-written pickle here would take the board's MC6 column
down, so it is never written in place.

Run: ./venv/bin/python _mc6_build_state.py
"""
import os
import pickle
import re
import shutil
import sys

import numpy as np
import pandas as pd

DIR = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(DIR, "data_cache", "_mc6_state.pkl")
TMP = OUT + ".tmp"
BAK = OUT + ".bak"
HL_MATCH = 5.0          # surface-form half-life, in matches
KEEP = 12               # meetings kept per pair


def margin(s):
    """(games for the first-named player) - (games for the other). Score is written a-first."""
    if not isinstance(s, str) or not s:
        return 0.0
    d = n = 0
    for x, y in re.findall(r"(\d+)\s*[-:]\s*(\d+)", s):
        x, y = int(x), int(y)
        if x > 30 or y > 30:          # a tie-break point score, not games
            continue
        d += x - y
        n += 1
    return float(d) if n else 0.0


def main():
    F = pd.read_parquet(os.path.join(DIR, "data_cache", "_mc2_features.parquet"),
                        columns=["date", "a", "b", "surf", "won", "p_elo", "score"])
    F["date"] = pd.to_datetime(F["date"], errors="coerce")
    F = F[F["date"].notna() & F["a"].notna() & F["b"].notna() & F["won"].notna()
          & F["p_elo"].notna()]
    F = F.sort_values("date", kind="stable").reset_index(drop=True)
    print("archive rows: %d   %s .. %s"
          % (len(F), F.date.min().date(), F.date.max().date()), flush=True)

    A = F["a"].astype(str).to_numpy()
    B = F["b"].astype(str).to_numpy()
    surf = F["surf"].astype(str).to_numpy()
    won_a = F["won"].astype(bool).to_numpy()
    p_elo = F["p_elo"].to_numpy(float)
    day = (F["date"].astype("int64").to_numpy() / 86_400_000_000_000.0)
    mg_a = F["score"].map(margin).to_numpy(float)

    # ---------------- H2H: the meetings themselves ----------------
    h2h = {}
    for i in range(len(F)):
        first_is_a = A[i] < B[i]
        key = (A[i], B[i]) if first_is_a else (B[i], A[i])
        wf = bool(won_a[i]) if first_is_a else (not bool(won_a[i]))
        mf = mg_a[i] if first_is_a else -mg_a[i]
        h2h.setdefault(key, []).append((float(day[i]), bool(wf), float(mf), surf[i]))
    for k in list(h2h):
        if len(h2h[k]) > KEEP:
            h2h[k] = h2h[k][-KEEP:]
    print("pairs with a meeting: %d   (2+ meetings: %d)"
          % (len(h2h), sum(1 for v in h2h.values() if len(v) > 1)), flush=True)

    # ---------------- surface form: EWMA of the Elo residual ----------------
    L = pd.DataFrame({
        "pl": np.concatenate([A, B]),
        "surf": np.concatenate([surf, surf]),
        "date": np.concatenate([F["date"].to_numpy(), F["date"].to_numpy()]),
        "resid": np.concatenate([won_a.astype(float) - p_elo,
                                 (~won_a).astype(float) - (1.0 - p_elo)])})
    L = L.sort_values(["pl", "surf", "date"], kind="stable")
    # the CURRENT value includes every match played, so no shift here -- the as-of shifting
    # belongs to the backtest (_mc6_sweep.py), not to the live state
    ew = (L.groupby(["pl", "surf"], sort=False)["resid"]
          .transform(lambda s: s.ewm(halflife=HL_MATCH, min_periods=1).mean()))
    L["ew"] = ew
    last = L.groupby(["pl", "surf"], sort=False).tail(1)
    sform = {(r.pl, r.surf): float(r.ew) for r in last.itertuples()}
    cnt = L.groupby(["pl", "surf"], sort=False).size()
    sform_n = {k: int(v) for k, v in cnt.items()}
    print("surface-form cells: %d   mean |resid| %.4f"
          % (len(sform), float(np.mean([abs(v) for v in sform.values()]))), flush=True)

    S = {"h2h": h2h, "sform": sform, "sform_n": sform_n,
         "asof": str(F["date"].max().date()), "hl_match": HL_MATCH, "keep": KEEP,
         "rows": int(len(F))}

    with open(TMP, "wb") as f:
        pickle.dump(S, f, protocol=4)
    # validate before it can replace anything
    with open(TMP, "rb") as f:
        chk = pickle.load(f)
    assert chk["h2h"] and chk["sform"], "empty state"
    assert len(chk["h2h"]) > 1000 and len(chk["sform"]) > 1000, "implausibly small state"
    if os.path.exists(OUT):
        shutil.copy2(OUT, BAK)
    os.replace(TMP, OUT)
    print("wrote %s  (%.1f MB)  asof %s"
          % (OUT, os.path.getsize(OUT) / 1e6, S["asof"]))
    print("RESULT: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
