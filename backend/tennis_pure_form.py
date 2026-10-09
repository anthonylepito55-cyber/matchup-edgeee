"""Pure-results recent-form overlay (2026-10-06, user ask: "what if it wasn't based off
stats at all -- just the last 10 on surface, who faced better opponents and won or lost,
kept it close in 3 sets or 2 sets etc, no tennis stats").

A player's recent form on a surface built from RESULTS ONLY -- no serve/return stats:
  * each of the last 10 matches ON that surface contributes a signed value
  * the value = set + game margin ("kept it close" vs "straight sets" vs "blown out")
    SCALED by opponent quality (rival_rank): beating a strong opponent counts big, losing
    to a weak one is punished hard, losing close to a strong one is softened
  * recency-weighted with the last 3 matches boosted heaviest

NOTE ON USAGE -- now BACKTESTED (2026-10-08, `_pure_form_bt.py`). This module was shipped
forward-only on the belief it couldn't be replayed, but form() takes `asof` and only ever
reads matches strictly before it, so a leak-free as-of replay is possible. 67,096 matches
2024-26, true gender, flat 1u at archive closing odds:
  * STANDALONE is dead: back the better-form player = men -6.0% (n=39,727) / women -6.1%
    (n=27,369); negative as a dog, as a favourite, in the top form-gap quartile, and in
    all three years (-5.5 / -6.1 / -6.5). Never bet it on its own.
  * FADING form outright is also dead (men -8.7% / women -10.0%) -- it is not a simple
    inverse either.
  * THE CONTRARIAN OVERLAY IS CONFIRMED, and it is strongest on DOGS:
      C + form DISAGREE -> back C's side: men +2.1% (n=14,655) | women +8.9% (n=9,658)
        C's side is the DOG:              men +7.4% (n=5,029)  | women +23.0% (n=3,627)
        C's side is the FAVOURITE:        men -0.6% (n=9,626)  | women +0.5% (n=6,031)
      backing FORM instead on a disagreement: men -15.5% / women -21.1%.
    The live log said the same thing first (dis_dog +34.2%, dis_fav +1.5%), so the
    dog-only gate on the board was right; the backtest just sizes it and shows WOMEN are
    the stronger half (+23.0% vs +7.4%), the reverse of the men-first framing of 2026-10-06.
Forward-tracked via the pf_c75_* lanes in tennis_log; the 🧊 chip shows bt + live.
"""
import os
from collections import defaultdict

import numpy as np
import pandas as pd

from tennis_data import CACHE_DIR

_ALL = os.path.join(CACHE_DIR, "tennisratio", "all_match_logs.parquet")
DECAY, TOP3, K, CAP_DAYS, MINN = 0.9, 2.5, 10, 540, 5

_H = None          # {(slug, surface): sorted list[(np.datetime64, contrib)]}
_H_MTIME = None


def _perf(score, result):
    """Set+game margin from the player's perspective, in [-1, 1]. 2-0 ~ +1, 2-1 ~ +0.3,
    1-2 ~ -0.3 (kept it close), 0-2 ~ -1. Blends set differential (0.6) with games (0.4)."""
    sw = sl = gw = gl = 0
    for s in str(score).split():
        s = s.split("(")[0]
        if "-" not in s:
            continue
        try:
            a, b = s.split("-")
            a, b = int(a), int(b)
        except Exception:  # noqa: BLE001
            continue
        gw += a
        gl += b
        if a > b:
            sw += 1
        elif b > a:
            sl += 1
    tot = sw + sl
    if tot == 0:
        return 0.5 if result == "Win" else -0.5
    ps = (sw - sl) / tot
    gm = (2 * gw / (gw + gl) - 1) if (gw + gl) > 0 else 0.0
    return 0.6 * ps + 0.4 * gm


def _qual(rank):
    """Opponent quality in [0, 1] from rival_rank: #1 ~ 1.0, #400+ ~ 0. Missing/0 -> 0.10."""
    try:
        r = float(rank)
    except Exception:  # noqa: BLE001
        r = 0.0
    if not (r == r) or r <= 0:
        return 0.10
    return max(0.0, (400.0 - min(r, 400.0)) / 400.0)


def _build():
    df = pd.read_parquet(_ALL, columns=["player_slug", "surface", "date", "score",
                                        "result", "rival_rank"])
    df["surface"] = df["surface"].astype(str).str.title()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df[df["date"].notna() & (df["date"] >= pd.Timestamp("2022-06-01"))
            & df["score"].notna()]
    rank = pd.to_numeric(df["rival_rank"], errors="coerce").values
    h = defaultdict(list)
    for slug, surf, dt, sc, res, rk in zip(df["player_slug"].values, df["surface"].values,
                                           df["date"].values, df["score"].values,
                                           df["result"].values, rank):
        bp = _perf(sc, res)
        d = _qual(rk)
        h[(slug, surf)].append((dt, bp * (0.5 + d) if bp >= 0 else bp * (1.5 - d)))
    for k in h:
        h[k].sort(key=lambda x: x[0])
    return dict(h)


def _ensure():
    """Lazy build, cached in-process; rebuilt only when the match-log parquet changes
    (e.g. after the nightly ingest). First call after a restart/ingest pays the build."""
    global _H, _H_MTIME
    try:
        mt = os.path.getmtime(_ALL)
    except OSError:
        return _H or {}
    if _H is None or mt != _H_MTIME:
        _H = _build()
        _H_MTIME = mt
    return _H


def form(slug, surface, asof=None):
    """(score, n) for one player on a surface as of `asof` (default: today). None score when
    the player has fewer than MINN surface matches in the window."""
    h = _ensure()
    lst = h.get((slug, str(surface).title()))
    if not lst:
        return None, 0
    asof = (np.datetime64(pd.Timestamp(asof)) if asof is not None
            else np.datetime64(pd.Timestamp.utcnow().date()))
    cap = np.timedelta64(CAP_DAYS, "D")
    rec = [(d, r) for d, r in lst if d < asof and (asof - d) <= cap]
    if len(rec) < MINN:
        return None, len(rec)
    rec = rec[-K:][::-1]  # most recent first
    num = den = 0.0
    for j, (_d, r) in enumerate(rec):
        w = (DECAY ** j) * (TOP3 if j < 3 else 1.0)
        num += w * r
        den += w
    return num / den, len(rec)


def edge(p1_name, p2_name, surface, asof=None):
    """(edge, n1, n2): player_1's pure-form score minus player_2's, on the surface, as of
    `asof`. Positive -> p1 in better quality-adjusted recent form. None edge when either
    player is thin. Names are resolved to TennisRatio slugs via tennis_context."""
    import tennis_context as tc

    def _slug(nm):
        try:
            g = tc.get_context(nm, surface)
            return g["slug"] if g else None
        except Exception:  # noqa: BLE001
            return None

    s1, s2 = _slug(p1_name), _slug(p2_name)
    f1, n1 = form(s1, surface, asof) if s1 else (None, 0)
    f2, n2 = form(s2, surface, asof) if s2 else (None, 0)
    if f1 is None or f2 is None:
        return None, n1, n2
    return f1 - f2, n1, n2
