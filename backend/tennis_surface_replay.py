"""AS-OF SURFACE REPLAY (2026-10-09, user: "fix the wrongs for previous days so i can see what
i would have chosen if it was the correct court and put who u told me to take that day").

_surface_history_audit.py found 140 logged matches before 10-08 played on a different court than
we had on the card (data_cache/_surface_history_audit.csv). Those rows carry surface_bad=True and
are already excluded from every lane. This module answers the other half of the question: what
WOULD the board have shown if the court had been right?

recompute(date, p1, p2, surface, ...) rebuilds Model A/B/C/D, their market-aware heads, the four
Monte Carlo variants and Model P for a past match using only archive matches STRICTLY BEFORE that
match's date -- the same _profile/_feats code and the same artifacts the live board uses, with
tennis_model_a's global cache swapped for an as-of one. Call it twice per row, once on the logged
court and once on the true court, and the only thing that differs is the surface.

HONEST LIMITS (both recomputes share them, so the wrong-vs-right comparison stays clean):
  * Today's artifacts and today's sUTR, not the ones that were live that day. So neither side is
    a bit-exact replay of the original card. _surface_fix_history.py reports how closely the
    logged-court replay reproduces the frozen column, which is the check on that.
  * The TennisRatio archive's own per-match surfaces are untouched: a player's "last 10 on clay"
    can still contain a match that site also mislabelled. Only the court OF THIS MATCH is fixed.
  * Monte Carlo is stochastic; it is seeded per call here so a rerun reproduces the same numbers.
"""
import os

import numpy as np
import pandas as pd

import tennis_model_a as A

_src = {"df": None, "mtime": None}
_asof = {"date": None}


def _base():
    """Parse the archive once, with the per-row derivations from A._load that are already
    as-of safe (opp_form is a shifted rolling mean; lvl is per row)."""
    mt = os.path.getmtime(A.LOGS_PARQUET)
    if _src["df"] is not None and _src["mtime"] == mt:
        return _src["df"]
    df = A._parse(pd.read_parquet(A.LOGS_PARQUET))
    df = df.sort_values(["player_slug", "date"], kind="stable").reset_index(drop=True)
    _s0 = df.groupby("player_slug", sort=False)["won"].shift(1)
    df["_o10w"] = _s0.groupby(df["player_slug"]).rolling(10, min_periods=4).mean() \
        .reset_index(level=0, drop=True)
    _opp = df[["player_slug", "date", "_o10w"]].rename(
        columns={"player_slug": "rival_slugname", "_o10w": "opp_form"})
    _opp = _opp.drop_duplicates(["rival_slugname", "date"])
    df = df.merge(_opp, on=["rival_slugname", "date"], how="left")
    _sl = df["tournament_level"].astype(str).str.lower()
    df["lvl"] = np.where(_sl.str.contains("challenger"), 1,
                         np.where(_sl.str.contains("future") | _sl.str.contains("itf"), 2, 0))
    _src.update({"df": df, "mtime": mt})
    return df


def set_asof(date):
    """Pin tennis_model_a's cache to profiles/H2H built only from matches before `date`.

    A._load() returns early while _cache["mtime"] matches the archive's mtime, so the pinned
    cache survives every later predict_* call until the next set_asof.
    """
    d = pd.Timestamp(str(date)[:10])
    if _asof["date"] == d:
        return
    df = _base()
    A._load()                      # load the joblib artifacts before we overwrite the cache
    cut = df[df["date"] < d].copy()
    # own rank proxy = the latest rank an opponent's row gave us BEFORE this date (A._load
    # takes the latest over all time, which would look ahead on a replay)
    own = (cut[["rival_slugname", "date", "rival_rank"]].dropna()
           .sort_values("date").groupby("rival_slugname")["rival_rank"].last())
    cut["rank_proxy"] = cut["player_slug"].map(own)
    profiles = {slug: A._profile(g, d) for slug, g in cut.groupby("player_slug")}
    h2h = {}
    two = cut[cut["rival_slugname"].notna() & (cut["rival_slugname"] != "")]
    for (a, b), g in two.groupby([two["player_slug"], two["rival_slugname"].astype(str)]):
        key = tuple(sorted((a, b)))
        if a != key[0]:                        # each match appears once per side
            continue
        e = h2h.setdefault(key, {"n": 0, "wins": {}, "surf": {}})
        e["n"] = int(len(g))
        e["wins"][a] = int(g["won"].sum())
        e["wins"][b] = int(len(g) - g["won"].sum())
        for surf, sg in g.groupby("surface"):
            e["surf"][surf] = {"n": int(len(sg)), a: int(sg["won"].sum()),
                               b: int(len(sg) - sg["won"].sum())}
    A._cache.update({"mtime": _src["mtime"], "profiles": profiles, "h2h": h2h,
                     "name_map": {A._norm_name(A._slug_name(s)): s for s in profiles}})
    _asof["date"] = d


def release():
    """Drop the pinned as-of cache so the live board rebuilds normally."""
    A._cache.update({"mtime": None, "profiles": None, "h2h": None, "name_map": None})
    _asof["date"] = None


def _mk(p1_odds, p2_odds):
    d1, d2 = A_dec(p1_odds), A_dec(p2_odds)
    if not d1 or not d2:
        return None
    i1, i2 = 1 / d1, 1 / d2
    return round(i1 / (i1 + i2), 3)


def A_dec(am):
    if am is None or (isinstance(am, float) and np.isnan(am)):
        return None
    am = float(am)
    return 1 + (am / 100.0 if am > 0 else 100.0 / abs(am))


def recompute(date, p1, p2, surface, league=None, best_of_5=False,
              p1_odds=None, p2_odds=None, seed=12345):
    """Every frozen model column for one past match, as of its own date, on `surface`.

    Returns a dict with the same keys the prediction log uses, so a row can be rebuilt by
    dict-update and fed straight to the existing signal code.
    """
    set_asof(date)
    np.random.seed(seed)
    mk1 = _mk(p1_odds, p2_odds)
    out = {"surface": str(surface or "Hard").title(), "_mk1": mk1}

    def one(fn, *a, **k):
        try:
            return fn(*a, **k)
        except Exception:  # noqa: BLE001
            return None

    ma = one(A.predict, p1, p2, surface, mk1)
    mb = one(A.predict_b, p1, p2, surface, mk1)
    mc = one(A.predict_c, p1, p2, surface, mk1)
    md = one(A.predict_d, p1, p2, surface, mk1, league)
    for key, obj in (("a", ma), ("b", mb), ("c", mc), ("d", md)):
        out[f"model_{key}_p1"] = (obj or {}).get("p1_prob")
        out[f"model_{key}ma_p1"] = (obj or {}).get("market_aware_p1")
    # the four Monte Carlos, exactly as main.py builds them on a live card
    if md is not None:
        v = one(A.simulate_match, p1, p2, surface, level=league, best_of_5=bool(best_of_5))
        out["mc_p1"] = (v["p1_pct"] / 100.0) if v else None
        md["mc"] = v
    else:
        out["mc_p1"] = None
    out["mc_c_p1"] = out["mc_c75_p1"] = out["mc_cutr_p1"] = None
    if mc is not None and mc.get("p1_prob") is not None:
        cp = mc["p1_prob"]
        v = one(A.simulate_match, p1, p2, surface, level=league, best_of_5=bool(best_of_5),
                n=40000, c_anchor=cp, c_weight=0.5, sutr_weight=0.0)
        out["mc_c_p1"] = (v["p1_pct"] / 100.0) if v else None
        mc["mc"] = v
        for k, cw, sw in (("mc_c75_p1", 0.75, 0.0), ("mc_cutr_p1", 0.5, 0.75)):
            v = one(A.simulate_match, p1, p2, surface, level=league, best_of_5=bool(best_of_5),
                    n=20000, c_anchor=cp, c_weight=cw, sutr_weight=sw)
            out[k] = (v["p1_pct"] / 100.0) if v else None
            mc[k] = out[k]
    pc = (mc or {}).get("pf") or {}
    out["c_rp_diff_p1"], out["c_sp_diff_p1"] = pc.get("d_c_rp"), pc.get("d_c_sp")
    # MODEL P off the recomputed C and D
    out["model_p_dog"] = out["model_p_prob"] = out["model_p_ev"] = out["model_p_fev"] = None
    if mc is not None and md is not None and mk1 is not None:
        try:
            import tennis_model_p as P
            mp = P.predict_p(mc, md, mk1, league, p1_odds, p2_odds)
            if mp:
                out["model_p_dog"] = mp.get("dog")
                out["model_p_prob"] = mp.get("p_dog")
                out["model_p_ev"] = mp.get("ev")
                out["model_p_fev"] = mp.get("fav_ev")
                out["_p"] = mp
        except Exception:  # noqa: BLE001
            pass
    out["_objs"] = {"a": ma, "b": mb, "c": mc, "d": md}
    return out
