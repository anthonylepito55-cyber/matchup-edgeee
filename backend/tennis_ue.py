"""UNFORCED-ERROR PROFILES from Tennis Abstract's Match Charting Project (2026-10-09, user:
"pull real unforced errors" + "check tennis abstract" + the per-player metric list).

Source: github.com/JeffSackmann/tennis_MatchChartingProject (CC BY-NC-SA -- non-commercial
use only). Files in data_cache/mcp/: charting-{m,w}-matches.csv, charting-{m,w}-stats-Overview.csv.

Per charted player-match: UEs (total, forehand, backhand), winners, points played (serve +
return), sets played (number of per-set rows), surface, date, opponent.
profile(name, asof, surface=None) -> as-of metrics from charted matches STRICTLY BEFORE asof:
  ue_match_5/10   UEs per match, last 5 / last 10
  ue_set_5/10     UEs per set
  ue_100_5/10     UEs per 100 points played
  ue_100_surf10   UEs per 100 points, last 10 on this surface
  wue_10          winners / UEs ratio, last 10
  fh_100_10, bh_100_10, fh_share_10   forehand / backhand UEs per 100 points, FH share of UEs
  pts_10          points played per match (match-duration proxy; MCP has no clock times)
  n_10, last_date  sample size + freshness
"""
import os
import re
import unicodedata

import numpy as np
import pandas as pd

_here = os.path.dirname(os.path.abspath(__file__))
_DIR = os.path.join(_here, "data_cache", "mcp")
_CACHE = {"df": None, "by": None}


def norm(s):
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z]", "", s)


def load(force=False):
    if _CACHE["df"] is not None and not force:
        return _CACHE["df"]
    parts = []
    for g in ("m", "w"):
        mt = pd.read_csv(os.path.join(_DIR, f"charting-{g}-matches.csv"), dtype=str, encoding="latin-1")
        ov = pd.read_csv(os.path.join(_DIR, f"charting-{g}-stats-Overview.csv"), dtype=str, encoding="latin-1")
        for c in ("serve_pts", "return_pts", "unforced", "unforced_fh", "unforced_bh", "winners"):
            ov[c] = pd.to_numeric(ov[c], errors="coerce")
        nsets = (ov[ov["set"] != "Total"].groupby(["match_id", "player"]).size().rename("sets"))
        tot = ov[ov["set"] == "Total"].merge(nsets, on=["match_id", "player"], how="left")
        tot = tot.merge(mt[["match_id", "Date", "Surface", "Player 1", "Player 2"]], on="match_id", how="left")
        tot["opp"] = np.where(tot["player"] == tot["Player 1"], tot["Player 2"], tot["Player 1"])
        tot["date"] = pd.to_datetime(tot["Date"], format="%Y%m%d", errors="coerce")
        tot["G"] = g.upper()
        tot = tot.merge(_detail(g, mt), on=["match_id", "player"], how="left")
        parts.append(tot)
    # site pulls newer than GitHub (tennis_ue_refresh.refresh_site) -- same columns
    for _f, _src in ((os.path.join(_DIR, "ta_extra.csv"), "site"),
                     (os.path.join(_DIR, "manual_ue.csv"), "manual")):
        if not os.path.exists(_f):
            continue
        X = pd.read_csv(_f, dtype=str, comment="#")
        X = X[X.get("player").notna()] if "player" in X.columns else X
        if X.empty:
            continue
        for c in ("serve_pts", "return_pts", "unforced", "unforced_fh", "unforced_bh", "winners", "sets"):
            if c not in X.columns:
                X[c] = None
            X[c] = pd.to_numeric(X[c], errors="coerce")
        X["date"] = pd.to_datetime(X["Date"], format="%Y%m%d", errors="coerce")
        if "Surface" not in X.columns:
            X["Surface"] = None
        X["src"] = _src
        parts.append(X)
    D = pd.concat(parts, ignore_index=True)
    D = D.drop_duplicates(["match_id", "player"], keep="first")
    D["pts"] = D.serve_pts + D.return_pts
    if "src" not in D.columns:
        D["src"] = "mcp"
    D["src"] = D["src"].fillna("mcp")
    # MANUALLY ENTERED rows (2026-10-10, user asked about going game by game): a hand-typed
    # row realistically carries unforced errors and sets but not the point counts, and the
    # pts >= 40 guard would silently drop it. Keep those -- ue_set still computes; ue_100 and
    # the per-100-point metrics are simply absent for them.
    _keep_manual = (D["src"] == "manual") & D.unforced.notna() & D.sets.notna()
    D = D[((D.pts >= 40) | _keep_manual) & D.unforced.notna() & D.date.notna()].copy()
    D["sets"] = D["sets"].fillna(2).clip(lower=1)
    D["key"] = D.player.map(norm)
    D["okey"] = D.opp.map(norm)
    D["surface"] = D["Surface"].astype(str).str.title().replace({"Carpet": "Hard"})
    D = D.sort_values("date").reset_index(drop=True)
    _CACHE["df"] = D
    _CACHE["by"] = {k: g for k, g in D.groupby("key")}
    return D


def _detail(g, mt):
    """Per-match error detail from the Match Charting Project files we were not using
    (2026-10-10, user "yes test it" then "ship it"). Same matches as Overview -- 1,739 players
    either way, measured -- so this adds DEPTH, not coverage:

      ue_key   unforced errors per key point (break/game/deuce), from KeyPointsServe
      ue_long  unforced errors per point in rallies of 7+ shots, from Rally
      ue_bh    backhand unforced errors per 100 backhands, from ShotTypes (row B)
      ue_fh    the same for the forehand (row F)
      press    (induced_forced - unforced) / shots -- pressure CREATED minus errors GIVEN

    DISPLAY ONLY. Every one of these backtested NEGATIVE as a betting gate for +100..+250 dogs
    (women -4% to -24%, men -8% to -15%, _ue_detail_backtest.py), and on that subsample even the
    shipped ue_set metric reads -10..-25% against its true +11.1% -- requiring detail for both
    players selects for heavily-charted top-level players, where the women's low-error dog edge
    does not exist. So these are card context, never a mark. Missing files degrade to NaN.
    """
    import numpy as _np

    def _num(d, cols):
        for c in cols:
            d[c] = pd.to_numeric(d[c], errors="coerce")
        return d

    out = None
    try:
        kp = pd.read_csv(os.path.join(_DIR, f"charting-{g}-stats-KeyPointsServe.csv"),
                         dtype=str, encoding="latin-1", usecols=["match_id", "player", "row", "pts", "unforced"])
        kp = _num(kp[kp["row"].isin(["BP", "GP", "Deuce"])], ["pts", "unforced"])
        k = kp.groupby(["match_id", "player"])[["pts", "unforced"]].sum()
        k["ue_key"] = _np.where(k["pts"] >= 8, k["unforced"] / k["pts"], _np.nan)
        out = k[["ue_key"]].reset_index()
    except Exception:  # noqa: BLE001
        pass
    try:
        ra = pd.read_csv(os.path.join(_DIR, f"charting-{g}-stats-Rally.csv"), dtype=str,
                         encoding="latin-1", usecols=["match_id", "row", "pts", "pl1_unforced", "pl2_unforced"])
        ra = _num(ra[ra["row"].isin(["7-9", "10"])], ["pts", "pl1_unforced", "pl2_unforced"])
        ag = ra.groupby("match_id")[["pts", "pl1_unforced", "pl2_unforced"]].sum().reset_index()
        ag = ag.merge(mt[["match_id", "Player 1", "Player 2"]], on="match_id", how="inner")
        # pl1/pl2 are the match file's Player 1 / Player 2 (the file's server/returner column
        # names are labels for those two, not who actually served -- verified 2026-10-10)
        lg = []
        for col, who in (("pl1_unforced", "Player 1"), ("pl2_unforced", "Player 2")):
            t = ag[["match_id", "pts", col, who]].rename(columns={col: "u", who: "player"})
            t["ue_long"] = _np.where(t["pts"] >= 10, t["u"] / t["pts"], _np.nan)
            lg.append(t[["match_id", "player", "ue_long"]])
        lg = pd.concat(lg, ignore_index=True)
        out = lg if out is None else out.merge(lg, on=["match_id", "player"], how="outer")
    except Exception:  # noqa: BLE001
        pass
    try:
        st = pd.read_csv(os.path.join(_DIR, f"charting-{g}-stats-ShotTypes.csv"), dtype=str,
                         encoding="latin-1", usecols=["match_id", "player", "row", "shots", "unforced", "induced_forced"])
        st = _num(st[st["row"].isin(["B", "F", "Total"])], ["shots", "unforced", "induced_forced"])
        pv = st.pivot_table(index=["match_id", "player"], columns="row",
                            values=["shots", "unforced", "induced_forced"], aggfunc="sum")
        pv.columns = [f"{a}_{b}" for a, b in pv.columns]
        pv = pv.reset_index()
        for side in ("B", "F"):
            sc, uc = f"shots_{side}", f"unforced_{side}"
            pv[f"ue_{side.lower()}h"] = (_np.where(pv[sc] >= 30, 100 * pv[uc] / pv[sc], _np.nan)
                                         if sc in pv and uc in pv else _np.nan)
        if "shots_Total" in pv:
            pv["press"] = _np.where(pv["shots_Total"] >= 60,
                                    (pv["induced_forced_Total"] - pv["unforced_Total"]) / pv["shots_Total"], _np.nan)
        cols = ["match_id", "player"] + [c for c in ("ue_bh", "ue_fh", "press") if c in pv]
        out = pv[cols] if out is None else out.merge(pv[cols], on=["match_id", "player"], how="outer")
    except Exception:  # noqa: BLE001
        pass
    if out is None:
        out = pd.DataFrame(columns=["match_id", "player"])
    for c in DETAIL:
        if c not in out.columns:
            out[c] = float("nan")
    return out


DETAIL = ["ue_key", "ue_long", "ue_bh", "ue_fh", "press"]


def _agg(g):
    if not len(g):
        return {}
    u, p, s, w = g.unforced.sum(), g.pts.sum(), g.sets.sum(), g.winners.sum()
    fh, bh = g.unforced_fh.sum(), g.unforced_bh.sum()
    return {"ue_match": u / len(g), "ue_set": u / s if s else None, "ue_100": 100 * u / p if p else None,
            "wue": (w / u) if u else None, "fh_100": 100 * fh / p if p else None,
            "bh_100": 100 * bh / p if p else None, "fh_share": (fh / (fh + bh)) if (fh + bh) else None,
            "pts": p / len(g), "n": len(g),
            # detail metrics (2026-10-10): plain means over the window, present only for
            # charted matches that carry them. Display context, never a mark -- see _detail.
            **{k: (float(g[k].mean()) if (k in g.columns and g[k].notna().any()) else None)
               for k in DETAIL}}


def profile(name, asof=None, surface=None, max_age_days=730):
    """As-of unforced-error profile for a player (matches strictly before `asof`)."""
    load()
    g = _CACHE["by"].get(norm(name))
    if g is None:
        return None
    asof = pd.Timestamp(asof) if asof is not None else pd.Timestamp.now().normalize() + pd.Timedelta(days=1)
    g = g[(g.date < asof) & (g.date >= asof - pd.Timedelta(days=max_age_days))]
    if len(g) < 3:
        return None
    l5, l10 = g.tail(5), g.tail(10)
    out = {f"{k}_5": v for k, v in _agg(l5).items()}
    out.update({f"{k}_10": v for k, v in _agg(l10).items()})
    if surface:
        gs = g[g.surface == str(surface).title()].tail(10)
        a = _agg(gs)
        out["ue_100_surf10"] = a.get("ue_100") if a.get("n", 0) >= 3 else None
        out["n_surf10"] = a.get("n", 0)
    out["last_date"] = str(g.date.iloc[-1].date())
    return out
