"""OPP1 v3.5 — the frozen E-family (E1/E2/E3/E5/E6 per venue, E4 removed from the gated
family) + A-O2 frozen-only MC2 input.

All functions take a quote DataFrame for ONE fixture: columns sportsbook, selection ('p1'/'p2'),
prob (implied ask probability of the stored top-of-book price), poll_ts, quote_ts (epoch s).
Every input obeys the leak-safe cutoff poll_ts <= T* — enforced here, not assumed.

PURE FUNCTIONS; no store/log access exists in this module.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

VENUES = ("Kalshi", "Polymarket")
WINDOW_S = 6 * 3600
MIN_SPAN_S = 2 * 3600


def _logit(p, eps=1e-6):
    p = min(max(float(p), eps), 1 - eps)
    return math.log(p / (1 - p))


def _cut(df, tstar):
    return df[df["poll_ts"] <= tstar]


def fair_pin_series(df: pd.DataFrame, tstar: float) -> pd.DataFrame:
    """Paired-Pinnacle de-vig series (the oo_steam.fair_series discipline): both selections
    sharing one quote_ts, observed by T*. Returns DataFrame(qts, poll_ts, fair) ascending."""
    pin = _cut(df[df["sportsbook"] == "Pinnacle"], tstar)
    rows = []
    for qts, g in pin.groupby("quote_ts"):
        if g["selection"].nunique() == 2:
            p1 = float(g[g["selection"] == "p1"]["prob"].iloc[-1])
            p2 = float(g[g["selection"] == "p2"]["prob"].iloc[-1])
            rows.append({"qts": float(qts), "poll_ts": float(g["poll_ts"].max()),
                         "fair": p1 / (p1 + p2)})
    if not rows:
        return pd.DataFrame(columns=["qts", "poll_ts", "fair"])
    return pd.DataFrame(rows).sort_values("qts").reset_index(drop=True)


def venue_series(df: pd.DataFrame, venue: str, tstar: float) -> pd.DataFrame:
    """Two-sided venue series by poll time: mid (player-1), spread = ask1+ask2."""
    v = _cut(df[df["sportsbook"] == venue], tstar)
    rows = []
    for pts, g in v.groupby("poll_ts"):
        if g["selection"].nunique() == 2:
            a1 = float(g[g["selection"] == "p1"]["prob"].iloc[-1])
            a2 = float(g[g["selection"] == "p2"]["prob"].iloc[-1])
            rows.append({"poll_ts": float(pts), "mid": (a1 + 1 - a2) / 2, "spread": a1 + a2})
    if not rows:
        return pd.DataFrame(columns=["poll_ts", "mid", "spread"])
    return pd.DataFrame(rows).sort_values("poll_ts").reset_index(drop=True)


def _last_at(series: pd.DataFrame, col: str, t: float):
    s = series[series["poll_ts"] <= t]
    return (float(s[col].iloc[-1]), float(s["poll_ts"].iloc[-1])) if len(s) else (None, None)


def _tw_mean(grid_ts, values, lo, hi):
    """Time-weighted mean of a last-known-carried step function over [lo, hi]."""
    pts = [(t, v) for t, v in zip(grid_ts, values) if t <= hi]
    if not pts:
        return None, 0.0
    total = 0.0
    weighted = 0.0
    for i, (t, v) in enumerate(pts):
        t0 = max(t, lo)
        t1 = min(pts[i + 1][0], hi) if i + 1 < len(pts) else hi
        if t1 > t0:
            weighted += v * (t1 - t0)
            total += (t1 - t0)
    return ((weighted / total) if total > 0 else None), total


def build_features(df: pd.DataFrame, tstar: float, mc2_p1=None, mc2_recon=False) -> dict:
    """E-family for one fixture + A-O2 MC2 input. Returns dict of values, *_ind missing
    indicators (1 = missing), and quote-age diagnostics."""
    out = {}
    lo = tstar - WINDOW_S
    fp = fair_pin_series(df, tstar)
    fair_t, _ = _last_at(fp.rename(columns={"qts": "poll_ts"})
                         if "poll_ts" not in fp else fp, "fair", tstar)
    for v, tag in (("Kalshi", "K"), ("Polymarket", "PM")):
        vs = venue_series(df, v, tstar)
        mid_t, mid_pts = _last_at(vs, "mid", tstar)
        # ---- E1: gap at T* ----
        if fair_t is None or mid_t is None:
            out["E1_%s" % tag], out["E1_%s_ind" % tag] = np.nan, 1
        else:
            out["E1_%s" % tag], out["E1_%s_ind" % tag] = fair_t - mid_t, 0
            out["age_%s_s" % tag] = tstar - mid_pts   # staleness, reported never capped
        # ---- E2: time-weighted mean gap over [T*-6h, T*] ----
        if fair_t is None or not len(vs):
            out["E2_%s" % tag], out["E2_%s_ind" % tag] = np.nan, 1
        else:
            grid = sorted(set(fp["poll_ts"]).union(vs["poll_ts"]))
            gaps, ts_ok = [], []
            for t in grid:
                f, _ = _last_at(fp, "fair", t)
                m, _ = _last_at(vs, "mid", t)
                if f is not None and m is not None:
                    gaps.append(f - m)
                    ts_ok.append(t)
            val, span = _tw_mean(ts_ok, gaps, lo, tstar)
            if val is None or span < MIN_SPAN_S:
                out["E2_%s" % tag], out["E2_%s_ind" % tag] = np.nan, 1
            else:
                out["E2_%s" % tag], out["E2_%s_ind" % tag] = val, 0
        # ---- E5/E6: change since common t0 (two-sided at BOTH endpoints for E6) ----
        if not len(vs) or not len(fp):
            e5 = e6 = None
        else:
            t0 = max(float(vs["poll_ts"].iloc[0]), float(fp["poll_ts"].iloc[0]))
            span = tstar - t0
            m0, _ = _last_at(vs, "mid", t0)
            s0, _ = _last_at(vs, "spread", t0)
            f0, _ = _last_at(fp, "fair", t0)
            s_t, _ = _last_at(vs, "spread", tstar)
            if span < MIN_SPAN_S or None in (m0, f0, mid_t, fair_t):
                e5 = None
            else:
                e5 = (mid_t - m0) - (fair_t - f0)
            e6 = (s_t - s0) if (span >= MIN_SPAN_S and None not in (s0, s_t)) else None
        out["E5_%s" % tag] = np.nan if e5 is None else e5
        out["E5_%s_ind" % tag] = 1 if e5 is None else 0
        out["E6_%s" % tag] = np.nan if e6 is None else e6
        out["E6_%s_ind" % tag] = 1 if e6 is None else 0

    # ---- E3: right-censored median venue adjust lag over Pinnacle re-prices in window ----
    reprices = fp[(fp["qts"] >= lo) & (fp["qts"] <= tstar)]
    venue_stamps = np.sort(_cut(df[df["sportsbook"].isin(VENUES)], tstar)["quote_ts"]
                           .astype(float).unique())
    if not len(reprices):
        out["E3"], out["E3_ind"] = np.nan, 1
    else:
        ds = []
        for qts in reprices["qts"]:
            later = venue_stamps[venue_stamps > qts]
            nxt = float(later[0]) if len(later) else tstar   # right-censored at T*
            ds.append(min(nxt, tstar) - qts)
        out["E3"], out["E3_ind"] = float(np.median(ds)), 0

    # ---- A-O2: frozen-only MC2; recon/missing -> registered missing-value path ----
    if mc2_recon or mc2_p1 is None or (isinstance(mc2_p1, float) and pd.isna(mc2_p1)):
        out["logit_mc2"], out["logit_mc2_ind"] = np.nan, 1
        out["mc2_recon_affected"] = 1 if mc2_recon else 0
    else:
        out["logit_mc2"], out["logit_mc2_ind"] = _logit(mc2_p1), 0
        out["mc2_recon_affected"] = 0
    out["logit_fair"] = np.nan if fair_t is None else _logit(fair_t)
    return out
