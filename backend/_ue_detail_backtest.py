"""SHARPER ERROR METRICS FROM THE MATCH CHARTING PROJECT (2026-10-10, user "yes test it").

We were using 4 of the project's 45 files. The unused ones break unforced errors down far
further, and this tests whether any of those beats the crude metric the live lane uses
(unforced errors per set, last 5 charted matches -> women's dogs +100..+250 with a 2.26+ gap,
backtest +11.1%, n=361).

Candidates, each built per charted player-match then averaged over that player's previous 5
charted matches (strictly prior, same construction as the shipped metric):

  ue_key   unforced errors per KEY point -- break points, game points and deuce combined
           (charting-*-stats-KeyPointsServe.csv). Errors under pressure, not errors at 40-0.
  ue_long  unforced errors per point in rallies of 7+ shots (charting-*-stats-Rally.csv).
           Who breaks down in long exchanges.
  ue_bh    backhand unforced errors per 100 backhands (charting-*-stats-ShotTypes.csv, row B).
  ue_fh    the same for the forehand.
  press    (induced_forced - unforced) / shots over all shots -- pressure CREATED minus errors
           GIVEN. We have no measure of the forcing side at all today.

THE COMPARISON IS RUN ON IDENTICAL ROWS. Each candidate is scored only on matches where both
players have that metric AND the existing ue_set metric, and the existing metric is re-scored on
exactly those rows. Otherwise a candidate could look better purely by landing on a different,
easier subsample -- which is the mistake that makes this kind of study worthless.

This buys DEPTH, NOT BREADTH: every file is derived from the same charted matches, so coverage
stays ~18% of our logged matches and 0% of ITF. A win here sharpens the ~18% where the lane
already fires; it cannot widen it.
"""
import sys

import numpy as np
import pandas as pd

MCP = "data_cache/mcp"
ARCH = "data_cache/tennisratio/all_match_logs.parquet"
BAND = (2.0, 3.5)          # dog decimal odds +100..+250
import os
MIN_N = int(os.environ.get("UE_MIN_N", "3"))   # charted matches needed for a profile.
# 3 matches the live lane (tennis_ue.profile requires 3). The first run of this study used 5 and
# the comparable samples collapsed to ~110 rows, at which size the SHIPPED metric itself swung
# between -4.0% and +2.1% across near-identical subsamples -- i.e. the test was measuring noise.


def norm(s):
    import re
    import unicodedata
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z]", "", s)


def num(df, cols):
    for c in cols:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


print("building per-match error metrics…", flush=True)
parts = []
for g in ("m", "w"):
    mt = pd.read_csv(f"{MCP}/charting-{g}-matches.csv", dtype=str, encoding="latin-1")
    mt["date"] = pd.to_datetime(mt["Date"], format="%Y%m%d", errors="coerce")
    mt = mt[["match_id", "date", "Player 1", "Player 2"]].dropna(subset=["date"])

    # --- baseline: unforced per set, from Overview (what the live lane uses) --------------
    ov = pd.read_csv(f"{MCP}/charting-{g}-stats-Overview.csv", dtype=str, encoding="latin-1")
    ov = num(ov, ["unforced", "serve_pts", "return_pts"])
    nsets = ov[ov["set"] != "Total"].groupby(["match_id", "player"]).size().rename("sets")
    base = ov[ov["set"] == "Total"].merge(nsets, on=["match_id", "player"], how="left")
    base["ue_set"] = base["unforced"] / base["sets"].fillna(2).clip(lower=1)
    base = base[["match_id", "player", "ue_set"]]

    # --- ue_key: unforced per key point ---------------------------------------------------
    kp = pd.read_csv(f"{MCP}/charting-{g}-stats-KeyPointsServe.csv", dtype=str, encoding="latin-1")
    kp = num(kp, ["pts", "unforced"])
    k = kp[kp["row"].isin(["BP", "GP", "Deuce"])].groupby(["match_id", "player"])[["pts", "unforced"]].sum()
    k["ue_key"] = np.where(k["pts"] >= 8, k["unforced"] / k["pts"], np.nan)
    k = k[["ue_key"]].reset_index()

    # --- ue_long: unforced per point in rallies of 7+ ------------------------------------
    ra = pd.read_csv(f"{MCP}/charting-{g}-stats-Rally.csv", dtype=str, encoding="latin-1")
    ra = num(ra, ["pts", "pl1_unforced", "pl2_unforced"])
    ra = ra[ra["row"].isin(["7-9", "10"])]
    agg = ra.groupby("match_id")[["pts", "pl1_unforced", "pl2_unforced"]].sum().reset_index()
    agg = agg.merge(mt[["match_id", "Player 1", "Player 2"]], on="match_id", how="inner")
    long_rows = []
    for side, who in (("pl1_unforced", "Player 1"), ("pl2_unforced", "Player 2")):
        t = agg[["match_id", "pts", side, who]].rename(columns={side: "u", who: "player"})
        t["ue_long"] = np.where(t["pts"] >= 10, t["u"] / t["pts"], np.nan)
        long_rows.append(t[["match_id", "player", "ue_long"]])
    lng = pd.concat(long_rows, ignore_index=True)

    # --- ue_bh / ue_fh / press, from ShotTypes -------------------------------------------
    stt = pd.read_csv(f"{MCP}/charting-{g}-stats-ShotTypes.csv", dtype=str, encoding="latin-1",
                      usecols=["match_id", "player", "row", "shots", "unforced", "induced_forced"])
    stt = stt[stt["row"].isin(["B", "F", "Total"])]
    stt = num(stt, ["shots", "unforced", "induced_forced"])
    piv = stt.pivot_table(index=["match_id", "player"], columns="row",
                          values=["shots", "unforced", "induced_forced"], aggfunc="sum")
    piv.columns = [f"{a}_{b}" for a, b in piv.columns]
    piv = piv.reset_index()
    piv["ue_bh"] = np.where(piv.get("shots_B", 0) >= 30, 100 * piv["unforced_B"] / piv["shots_B"], np.nan)
    piv["ue_fh"] = np.where(piv.get("shots_F", 0) >= 30, 100 * piv["unforced_F"] / piv["shots_F"], np.nan)
    piv["press"] = np.where(piv.get("shots_Total", 0) >= 60,
                            (piv["induced_forced_Total"] - piv["unforced_Total"]) / piv["shots_Total"], np.nan)
    piv = piv[["match_id", "player", "ue_bh", "ue_fh", "press"]]

    d = (base.merge(k, on=["match_id", "player"], how="outer")
             .merge(lng, on=["match_id", "player"], how="outer")
             .merge(piv, on=["match_id", "player"], how="outer")
             .merge(mt[["match_id", "date"]], on="match_id", how="inner"))
    d["G"] = g.upper()
    parts.append(d)

C = pd.concat(parts, ignore_index=True)
C["key"] = C["player"].map(norm)
C = C.dropna(subset=["date", "key"]).sort_values("date")
METRICS = ["ue_set", "ue_key", "ue_long", "ue_bh", "ue_fh", "press"]
print(f"charted player-matches with metrics: {len(C)}")
for m in METRICS:
    print(f"  {m:8s} present on {int(C[m].notna().sum()):6d} "
          f"({100 * C[m].notna().mean():4.1f}%)  mean {C[m].mean():.3f}")

# --- as-of profiles: mean of the previous 5 charted matches --------------------------------
C = C.sort_values(["key", "date"], kind="stable")
prof = C[["key", "date"]].copy()
for m in METRICS:
    sh = C.groupby("key", sort=False)[m].shift(1)
    prof[m] = sh.groupby(C["key"]).rolling(MIN_N, min_periods=MIN_N).mean().reset_index(level=0, drop=True)
prof = prof.dropna(subset=["key"]).drop_duplicates(["key", "date"], keep="last")
P = {m: prof.dropna(subset=[m]).set_index(["date", "key"])[m] for m in METRICS}
print(f"\nas-of profiles built (needs {MIN_N} prior charted matches)")

# --- betting universe, same definition as every other study -------------------------------
KEEP = ["date", "player_slug", "rival_slugname", "player_odd", "rival_odd", "result"]
df = pd.read_parquet(ARCH, columns=KEEP)
df["date"] = pd.to_datetime(df["date"])
df["won"] = (df["result"] == "Win").astype(int)
for c in ("player_odd", "rival_odd"):
    df[c] = pd.to_numeric(df[c], errors="coerce")
df["rival_slugname"] = df["rival_slugname"].astype(str)
side = df[["player_slug", "rival_slugname", "date"]].copy()
mir = side.rename(columns={"player_slug": "rival_slugname", "rival_slugname": "player_slug"})
df = df.merge(mir, on=["player_slug", "rival_slugname", "date"], how="inner")
m = df[df["player_slug"].astype(str) < df["rival_slugname"]].copy()
m = m.drop_duplicates(["player_slug", "rival_slugname", "date"])
i1 = 1 / m["player_odd"].where(m["player_odd"] > 1.005)
i2 = 1 / m["rival_odd"].where(m["rival_odd"] > 1.005)
m["mkt"] = i1 / (i1 + i2)
GM = pd.read_parquet("data_cache/_slug_gender.parquet")["g"].to_dict()
B = m[(m.date.dt.year >= 2024) & m.mkt.notna() & (m.mkt < 0.5)
      & m.player_odd.between(*BAND)].copy()
B["G"] = B.player_slug.astype(str).map(GM)
B = B[B.G.isin(["M", "W"])]
B["k"] = B.player_slug.astype(str).map(norm)
B["ok"] = B.rival_slugname.astype(str).map(norm)
B["dn"] = B.date.dt.normalize()
for m_ in METRICS:
    B[f"d_{m_}"] = [P[m_].get((d, k), np.nan) for d, k in zip(B.dn, B.k)]
    B[f"f_{m_}"] = [P[m_].get((d, k), np.nan) for d, k in zip(B.dn, B.ok)]
print(f"priced dogs in band 2024-26: {len(B)} (women {int((B.G == 'W').sum())})")


def roi(s):
    w = s.won.astype(bool)
    return 100 * np.where(w, s.player_odd - 1, -1).mean()


def line(s):
    n = len(s)
    if n < 25:
        return f"n={n} (thin)"
    w = s.won.astype(bool)
    return (f"{int(w.sum())}-{n - int(w.sum())} hit {100 * w.mean():4.1f}% "
            f"vs mkt {100 * s.mkt.mean():4.1f}% | ROI {roi(s):+6.1f}% (n={n})")


print("\n" + "=" * 78)
print("EACH CANDIDATE vs THE SHIPPED METRIC, ON IDENTICAL ROWS")
print("=" * 78)
for G, lab in (("W", "WOMEN"), ("M", "MEN")):
    print(f"\n--- {lab} dogs +100..+250 ---")
    for m_ in METRICS:
        if m_ == "ue_set":
            continue
        ok = B[(B.G == G) & B[f"d_{m_}"].notna() & B[f"f_{m_}"].notna()
               & B["d_ue_set"].notna() & B["f_ue_set"].notna()].copy()
        if len(ok) < 50:
            print(f"  {m_:8s} only {len(ok)} comparable rows -- too thin")
            continue
        # press: HIGHER is better, so the dog's edge is dog-minus-fav; the rest are errors
        sign = -1.0 if m_ == "press" else 1.0
        ok["gap"] = sign * (ok[f"f_{m_}"] - ok[f"d_{m_}"])
        ok["gap_base"] = ok["f_ue_set"] - ok["d_ue_set"]
        thr, thr_b = ok.gap.median(), ok.gap_base.median()
        cand, base_ = ok[ok.gap >= thr], ok[ok.gap_base >= thr_b]
        print(f"  {m_:8s} {line(cand)}")
        print(f"  {'(ue_set)':8s} {line(base_)}   <- same {len(ok)} rows, shipped metric")
        yr = " ".join(f"{Y}:{roi(cand[cand.date.dt.year == Y]):+.0f}%"
                      for Y in (2024, 2025, 2026) if len(cand[cand.date.dt.year == Y]) >= 15)
        print(f"  {'':8s} candidate by year: {yr or 'thin'}")
sys.stdout.flush()
