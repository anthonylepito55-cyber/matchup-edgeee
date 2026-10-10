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


def _agg(g):
    if not len(g):
        return {}
    u, p, s, w = g.unforced.sum(), g.pts.sum(), g.sets.sum(), g.winners.sum()
    fh, bh = g.unforced_fh.sum(), g.unforced_bh.sum()
    return {"ue_match": u / len(g), "ue_set": u / s if s else None, "ue_100": 100 * u / p if p else None,
            "wue": (w / u) if u else None, "fh_100": 100 * fh / p if p else None,
            "bh_100": 100 * bh / p if p else None, "fh_share": (fh / (fh + bh)) if (fh + bh) else None,
            "pts": p / len(g), "n": len(g)}


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
