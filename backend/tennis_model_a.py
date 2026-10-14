"""TENNIS MODEL A (2026-09-28, user ask): per-surface stat + form + opponent-quality + H2H
model over the full-site TennisRatio pull, serving a win % to compare with the market on
every tennis card.

HONEST LABEL (walk-forward, 109,915 priced matches, test years 2024/2025/2026 -- see
_tennis_model_a_build.py): Model A alone AUC .66-.68 (a real predictor), the market .71-.73
EVERY year, market+model == market to the 4th decimal, and betting Model A's disagreements
loses 10.6-12.0% flat at every edge size. DISPLAY-ONLY: when Model A and the market disagree,
the market has been right. The % and the H2H record are context, never a pick.

Artifacts: model_artifacts/tennis_model_a.joblib (LR + XGB ensemble on 15 diff features,
refit on all data by train()). Live profiles/H2H rebuild from all_match_logs.parquet on
mtime change, same construction as training (tail windows over strictly-prior matches).
"""
import os
import re

import joblib
import numpy as np
import pandas as pd

_here = os.path.dirname(os.path.abspath(__file__))
LOGS_PARQUET = os.path.join(_here, "data_cache", "tennisratio", "all_match_logs.parquet")
ARTIFACT = os.path.join(_here, "model_artifacts", "tennis_model_a.joblib")

FEATURES = ["d_sr10", "d_l10", "d_l20", "d_swin", "d_sgw", "d_rgw", "d_sp", "d_rp",
            "d_oppq", "d_v100", "d_rust", "d_lrank", "f_h2h_n", "f_h2h_share", "f_h2h_s_share"]
# MODEL B (2026-09-28): last-10-on-surface only -- recent stats + WHO they beat/lost to,
# rank-adjusted (log rank of opponents faced/beaten/lost-to, best win). Same honest harness.
ARTIFACT_B = os.path.join(_here, "model_artifacts", "tennis_model_b.joblib")
# MODEL C (2026-09-28): full 52-weeks-on-surface profile + season + rank-band matchup +
# last-10 + H2H. AUDITED, not leak-found, but the label is careful: its backtest edge is vs
# the site's AVERAGE book odds (decaying by year, mostly sub-tour) -- likely the stale-soft-
# price mechanism the scanner exploits, NOT proof against sharp closes. c_edge25 forward
# lane in tennis_log is the judge.
ARTIFACT_C = os.path.join(_here, "model_artifacts", "tennis_model_c.joblib")
# MODEL D (2026-09-30, user ask): HEAVY last-10 form -- recent win rates (surface +
# overall), form vs the player's OWN 52w baseline, competitiveness vs top-150 (games
# share, record, loss closeness), quality of recent scalps. Walk-forward verdict:
# honest forecaster (AUC .65-.68) but market-beaten; its D+gray-dog cell decayed
# +12.4 -> +7.4 -> +1.0 by year. DISPLAY-ONLY like A and B.
ARTIFACT_D = os.path.join(_here, "model_artifacts", "tennis_model_d.joblib")
# MODEL C TRACKING VARIANTS (2026-10-10): strict subsets of C's feature list, scored through
# predict_c's existing path because it builds every feature and then selects mdl["features"].
# Cached separately from _load() so the main artifact's invalidation logic is untouched.
ARTIFACT_C_VAR = {
    "nohb": os.path.join(_here, "model_artifacts", "tennis_model_c_nohb.joblib"),
    "api": os.path.join(_here, "model_artifacts", "tennis_model_c_api.joblib"),
}
_c_var_cache = {}


def c_variant(tag):
    """The variant artifact, reloaded when the file changes. None if it is not built."""
    p = ARTIFACT_C_VAR.get(tag)
    if not p or not os.path.exists(p):
        return None
    mt = os.path.getmtime(p)
    if _c_var_cache.get(tag, (None, None))[0] != mt:
        _c_var_cache[tag] = (mt, joblib.load(p))
    return _c_var_cache[tag][1]
# SURFACE UTR (2026-10-01, user ask): our court-specific UTR-style rating -- games-share
# performance vs opponent rating, recency-weighted last 30 on surface, no rankings.
# Validated: AUC .675/.678/.684 by year (improving), the only single stat besides gray-C
# that nudges the market's logloss down. Rebuilt by _tennis_sutr_build.py.
ARTIFACT_SUTR = os.path.join(_here, "model_artifacts", "tennis_sutr.joblib")
# MODEL G (2026-10-12, user ask): the nine 52-week figures the card prints and NOTHING else
# -- no last-10, no season, no H2H, no market -- with the two things the stat line has always
# been missing. (a) every rate shrunk toward the tour mean by its OWN denominator (service
# games, return games, pressure points, matches) so a hold% off four matches is not read like
# one off forty; (b) each past match discounted by what that OPPONENT RANK normally concedes,
# because 70% hold against the top 50 is not 70% hold against #600.
# WALK-FORWARD VERDICT: the opponent adjustment is real and growing (+1.2/+2.0/+2.8 AUC pts
# over the identical raw pipeline, against a 0.35pt se) and it is what stops the raw stat
# line's year-over-year decay. The shrinkage is a wash (+0.1/0.0/-0.1). But G is 6.5 AUC pts
# BEHIND the market, behind Model C, and has no betting edge anywhere: -11.3%/-11.8% on dogs
# and -7.6%/-5.4% on favourites over 53k bets, with no positive gender x side x year cell and
# no gradient in the edge buckets. So: DISPLAY AND LOG ONLY. No mark, no gate, no lane that
# anything reads. It is logged so it can earn a forward record like every other head.
ARTIFACT_G = os.path.join(_here, "model_artifacts", "tennis_model_g.joblib")
# MODEL G2 (2026-10-12, user "Make a g2 right under G that takes g and then just add in last 10
# game stats as well with who they won and how they performed and who they lost to and make sure
# u see if any walkovers to not count them"): every G feature untouched, plus a LAST-10-ON-THIS-
# COURT block -- the record, who they BEAT (avg + best win), who they LOST TO (avg + worst loss),
# who they played, and how they performed (games-won share, hold%, break%, how close the losses
# were). Walkovers and retirements are excluded from that block.
# WALK-FORWARD: G2 beats G in all three years -- AUC .6648/.6643/.6723 against G's .6546/.6599/
# .6597 on identical rows, logloss better each year. "Who they lost to" turned out to be the
# strongest of the new features, ahead of who they beat. Still market-beaten (.727) and still no
# betting edge (bet@5pt -10.4%), so DISPLAY AND LOG ONLY like G.
ARTIFACT_G2 = os.path.join(_here, "model_artifacts", "tennis_model_g2.joblib")
_g2_cache = {"mtime": None, "obj": None}
G2_T10 = ["t10_win", "t10_faced", "t10_beaten", "t10_bestwin", "t10_lost", "t10_worstloss",
          "t10_meff", "t10_losscl", "t10_hold", "t10_brk", "t10_n"]


def g2_model():
    """The Model G2 artifact, reloaded when the file changes. None if it is not built."""
    if not os.path.exists(ARTIFACT_G2):
        return None
    mt = os.path.getmtime(ARTIFACT_G2)
    if _g2_cache["mtime"] != mt:
        try:
            _g2_cache["obj"] = joblib.load(ARTIFACT_G2)
        except Exception:  # noqa: BLE001
            return None
        _g2_cache["mtime"] = mt
    return _g2_cache["obj"]


def _walkover_mask(sub):
    """True where the match never finished. TennisRatio does not flag these -- "ret" appears
    zero times in 615k scores -- so they are read off the SHAPE of the score: no parseable score
    at all (WO / BYE / DEF / empty, 53 rows), or the winner never reached a winning set count,
    2 in a best-of-3 and 3 in a best-of-5 (9,543 rows, 1.55%). Those carry a median of 4 service
    games against 10 for a completed match, so one of them inside a ten-match window puts a fifth
    of the weight on a three-game sample. Identical rule to _tennis_model_g2_build.py."""
    sc = sub["score"].astype(str)
    pairs = sc.str.findall(r"(\d+)-(\d+)")
    n = pairs.map(len)

    def _sets(ps):
        a = b = 0
        for x, y in ps:
            x, y = int(x), int(y)
            if x > y:
                a += 1
            elif y > x:
                b += 1
        return a, b
    sw = pairs.map(_sets)
    sf = np.array([x[0] for x in sw], dtype=float)
    sa = np.array([x[1] for x in sw], dtype=float)
    need = np.where((sf + sa) >= 4, 3, 2)
    winsets = np.where(sub["won"].to_numpy() == 1, sf, sa)
    return (n.to_numpy() == 0) | ((winsets < need) & (n.to_numpy() > 0))
_g_cache = {"mtime": None, "obj": None}
# (name, per-match numerator, per-match denominator) -- None denominator = already a
# percentage per match, so it shrinks on MATCH count. Must stay identical to the STATS list
# in _tennis_model_g_build.py or the live features stop matching the training ones.
G_STATS = [("win", "won", None), ("sv1", "first_serve_points", None),
           ("sv2", "second_serve_points", None), ("r1", "return_1st_serve_points", None),
           ("r2", "return_2nd_serve_points", None), ("sgw", "sg_won", "sg_all"),
           ("rgw", "rg_won", "rg_all"),
           ("svp", "serve_pressure_won", "serve_pressure_all"),
           ("rtp", "return_pressure_won", "return_pressure_all")]


def g_model():
    """The Model G artifact, reloaded when the file changes. None if it is not built."""
    if not os.path.exists(ARTIFACT_G):
        return None
    mt = os.path.getmtime(ARTIFACT_G)
    if _g_cache["mtime"] != mt:
        try:
            _g_cache["obj"] = joblib.load(ARTIFACT_G)
        except Exception:  # noqa: BLE001
            return None
        _g_cache["mtime"] = mt
    return _g_cache["obj"]
FEATURES_B = ["d_swin", "d_sr10", "d_sgw", "d_rgw", "d_sp", "d_rp",
              "d_faced", "d_beaten", "d_lost", "d_bestwin"]

_cache = {"mtime": None, "profiles": None, "h2h": None, "name_map": None, "model": None, "model_b": None, "model_c": None, "model_d": None}


def _norm_name(s):
    return " ".join(sorted(re.sub(r"[^a-z ]", "", str(s).lower().replace("-", " ")).split()))


def _slug_name(slug):
    return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", str(slug))


def _parse(df):
    df = df.copy()
    df["surface"] = df["surface"].astype(str).str.title()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    for c in ("player_odd", "rival_odd", "rival_rank", "first_serve_points", "second_serve_points",
              "return_1st_serve_points", "return_2nd_serve_points", "serve_pressure_all",
              "serve_pressure_won", "return_pressure_all", "return_pressure_won"):
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    for col, pre in (("service_games_won", "sg"), ("return_games_won", "rg")):
        parts = df[col].astype(str).str.extract(r"^(\d+)/(\d+)$")
        df[pre + "_won"] = pd.to_numeric(parts[0], errors="coerce")
        df[pre + "_all"] = pd.to_numeric(parts[1], errors="coerce")
    df = df[df["date"].notna()].sort_values(["player_slug", "date"]).reset_index(drop=True)
    df["won"] = (df["result"] == "Win").astype(int)
    df["sgw_pct"] = 100 * df["sg_won"] / df["sg_all"].replace(0, np.nan)
    df["rgw_pct"] = 100 * df["rg_won"] / df["rg_all"].replace(0, np.nan)
    df["sp_rate"] = 100 * df["serve_pressure_won"] / df["serve_pressure_all"].replace(0, np.nan)
    df["rp_rate"] = 100 * df["return_pressure_won"] / df["return_pressure_all"].replace(0, np.nan)
    df["top100_win"] = np.where(df["rival_rank"].notna() & (df["rival_rank"] <= 100), df["won"], np.nan)
    df["logr"] = np.log(pd.to_numeric(df["rival_rank"], errors="coerce").clip(1, 2000))
    # Model C extras
    for c in ("first_serve_accuracy", "aces", "double_faults"):
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    for col, pre in (("breakpoints_saved_count", "bps"), ("breakpoints_converted_count", "bpc")):
        parts = df[col].astype(str).str.extract(r"^(\d+)/(\d+)$")
        df[pre + "_w"] = pd.to_numeric(parts[0], errors="coerce")
        df[pre + "_a"] = pd.to_numeric(parts[1], errors="coerce")
    df["tb_w"] = df["score"].astype(str).str.count(r"7-6")
    df["tb_n"] = df["tb_w"] + df["score"].astype(str).str.count(r"6-7")
    df["w_logr"] = np.where(df["won"] == 1, df["logr"], np.nan)
    df["perf"] = np.where(df["player_odd"] > 1.005, df["won"] - 1 / df["player_odd"], np.nan)
    _svp = (df["first_serve_points"] + df["second_serve_points"]) / 2
    _rtp = (df["return_1st_serve_points"] + df["return_2nd_serve_points"]) / 2
    df["dr"] = (_rtp / (100 - _svp).clip(1)).clip(0, 5)
    df["meff"] = (df["sg_won"] + df["rg_won"]) / (df["sg_all"] + df["rg_all"]).replace(0, np.nan)
    df["l_meff"] = np.where(df["won"] == 0, df["meff"], np.nan)
    return df


_SURF_COLS = ("first_serve_points", "second_serve_points", "return_1st_serve_points",
              "return_2nd_serve_points", "sgw_pct", "rgw_pct", "sp_rate", "rp_rate", "won")


def _profile(gdf, today):
    """Current 'as of next match' feature values for one player -- tail windows, min 4."""
    def tmean(s, w, mn=4):
        v = s.dropna().tail(w)
        return float(v.mean()) if len(v) >= mn else None
    p = {"l10": tmean(gdf["won"], 10, 3), "l20": tmean(gdf["won"], 20, 6),
         "oppq": (float(gdf["rival_rank"].dropna().tail(10).median())
                  if gdf["rival_rank"].dropna().tail(10).shape[0] >= 4 else None),
         "v100": tmean(gdf["top100_win"], 25),
         "days_off": min(120, max(0, (today - gdf["date"].max()).days)),
         "rank": (float(gdf["rank_proxy"].dropna().iloc[-1]) if gdf["rank_proxy"].notna().any() else None),
         "last_date": str(gdf["date"].max().date()), "n": int(len(gdf)), "surf": {}}
    for surf, sd in gdf.groupby("surface"):
        e = {c: tmean(sd[c], 10) for c in _SURF_COLS}
        if all(e.get(k) is not None for k in ("first_serve_points", "second_serve_points",
                                              "return_1st_serve_points", "return_2nd_serve_points")):
            e["sr10"] = (0.6 * e["first_serve_points"] + 0.4 * e["second_serve_points"]
                         + 0.5 * e["return_1st_serve_points"] + 0.5 * e["return_2nd_serve_points"])
        else:
            e["sr10"] = None
        t = sd.tail(10)
        lrs = t["logr"].dropna()
        wl = t.loc[t["won"] == 1, "logr"].dropna()
        ll = t.loc[t["won"] == 0, "logr"].dropna()
        e["faced10"] = float(lrs.mean()) if len(lrs) >= 4 else None
        e["beaten10"] = float(wl.mean()) if len(wl) else None
        e["lost10"] = float(ll.mean()) if len(ll) else None
        e["bestwin10"] = float(wl.min()) if len(wl) else None
        lc = t["l_meff"].dropna()
        e["losscl10"] = float(lc.mean()) if len(lc) else None
        # Model D extras (2026-09-30): L10 games share, vs-top-150 competitiveness,
        # and recency-weighted (0.9/match) serve-return splits on this surface.
        e["meff10"] = tmean(sd["meff"], 10)
        hi10 = t[t["rival_rank"].notna() & (t["rival_rank"] <= 150)]
        e["hw150_10"] = float(hi10["won"].mean()) if len(hi10) else None
        _m150 = hi10["meff"].dropna() if len(hi10) else pd.Series(dtype=float)
        e["meff150_10"] = float(_m150.mean()) if len(_m150) else None
        # Model D v4: the last-10 opponents judged by THEIR OWN L10 form (no ranks)
        e["fq_faced"] = tmean(sd["opp_form"], 10)
        _wf = t.loc[t["won"] == 1, "opp_form"].dropna()
        e["fq_beaten"] = float(_wf.mean()) if len(_wf) else None
        e["fq_bestwin"] = float(_wf.max()) if len(_wf) else None
        _hot = t[t["opp_form"] >= 0.6]
        e["fq_hotwin"] = float(_hot["won"].mean()) if len(_hot) else None
        _hm = _hot["meff"].dropna() if len(_hot) else pd.Series(dtype=float)
        e["fq_hotmeff"] = float(_hm.mean()) if len(_hm) else None
        _sga = sd["sg_all"].replace(0, np.nan)
        _dcols = {"hold": sd["sgw_pct"], "break": sd["rgw_pct"],
                  "fsp": sd["first_serve_points"], "ssp": sd["second_serve_points"],
                  "r1": sd["return_1st_serve_points"], "r2": sd["return_2nd_serve_points"],
                  "aces": sd["aces"] / _sga, "dfs": sd["double_faults"] / _sga,
                  "bpcv": 100 * sd["bpc_w"] / sd["bpc_a"].replace(0, np.nan)}
        ewd = {}
        for nm9, s9 in _dcols.items():
            v9 = s9.dropna()
            ewd[nm9] = float(v9.ewm(alpha=0.1).mean().iloc[-1]) if len(v9) >= 4 else None
        e["ewd"] = ewd
        # Model C: prior-365-days-on-this-surface window
        w52 = sd[sd["date"] >= today - pd.Timedelta(days=365)]
        if len(w52) >= 5:
            def fm(col):
                v = w52[col].dropna()
                return float(v.mean()) if len(v) else None
            def fr(a, b, scale=100.0):
                sa, sb = w52[a].sum(), w52[b].sum()
                return float(scale * sa / sb) if sb else None
            c52 = {"m_won": fm("won"), "m_first_serve_accuracy": fm("first_serve_accuracy"),
                   "m_first_serve_points": fm("first_serve_points"),
                   "m_second_serve_points": fm("second_serve_points"),
                   "m_return_1st_serve_points": fm("return_1st_serve_points"),
                   "m_return_2nd_serve_points": fm("return_2nd_serve_points"),
                   "m_logr": fm("logr"), "m_w_logr": fm("w_logr"), "m_perf": fm("perf"),
                   "m_dr": fm("dr"), "m_meff": fm("meff"), "w_n": int(len(w52)),
                   "c_sgw": fr("sg_won", "sg_all"), "c_rgw": fr("rg_won", "rg_all"),
                   "c_bpsav": fr("bps_w", "bps_a"), "c_bpconv": fr("bpc_w", "bpc_a"),
                   "c_bpcre_pg": fr("bpc_a", "rg_all", 1.0), "c_bpdef_pg": fr("bps_a", "sg_all", 1.0),
                   "c_aces_pg": fr("aces", "sg_all", 1.0), "c_dfs_pg": fr("double_faults", "sg_all", 1.0),
                   "c_sp": fr("serve_pressure_won", "serve_pressure_all"),
                   "c_rp": fr("return_pressure_won", "return_pressure_all"),
                   "c_tb": fr("tb_w", "tb_n")}
            for bi, (blo, bhi) in enumerate(((1, 50), (51, 150), (151, 400), (401, 99999))):
                inb = w52["rival_rank"].between(blo, bhi)
                c52[f"s_bn{bi}"] = int(inb.sum())
                c52[f"m_bw{bi}"] = float(w52.loc[inb, "won"].mean()) if inb.any() else None
            e["c52"] = c52
        else:
            e["c52"] = None
        # MODEL G (2026-10-12): the same prior-365d window, but stored as SUMS so the
        # opponent-rank discount and the shrinkage can be applied at predict time, when the
        # league (and therefore the gender) is known. Per stat: the weighted numerator, its
        # denominator, and the weighted discount under each gender's curve. The discount has
        # to be applied per PAST MATCH -- each one is deflated by the rank band of the
        # opponent who produced it -- so it cannot be done after aggregating, which is why
        # both genders' sums are carried rather than one resolved number.
        # ADAPTIVE WINDOW (2026-10-12, user: a card where one player read "hard L20" and G
        # priced nothing -- "no 52 week on this game"). Under 5 matches in the 365-day window,
        # fall back to the last 20 on this surface, which is exactly what tennis_context already
        # shows on the card. Two reasons it has to be this rule and not a stricter one:
        #   * the card can describe the player, so G refusing to is a gap, not a safeguard;
        #   * the BUILD has no minimum-match floor at all, so the old `len(w52) >= 5` here made
        #     LIVE STRICTER THAN TRAINING -- a silent live/training mismatch of the exact kind
        #     that made Model E drift. The build now widens on the same threshold, so the two
        #     sides agree by construction.
        _gm = g_model()
        e["g52"] = None
        _gw = w52 if len(w52) >= 5 else sd.sort_values("date").tail(20)
        if _gm is not None and len(_gw) and _gw["logr"].notna().any():
            _ed = np.asarray(_gm["bin_edges"], dtype=float)
            _nb = len(_ed) - 1
            _bin = np.clip(np.searchsorted(_ed, _gw["logr"].to_numpy(dtype=float),
                                           side="left") - 1, 0, _nb - 1)
            g52 = {"w_n": int(len(_gw)), "wide": 0.0 if len(w52) >= 5 else 1.0,
                   "faced": float(_gw["logr"].dropna().mean()) if _gw["logr"].notna().any() else None}
            for _nm, _num, _den in G_STATS:
                if _den is None:
                    _r = pd.to_numeric(_gw[_num], errors="coerce").astype(float)
                    if _nm != "win":
                        _r = _r / 100.0
                    _r = _r.where(_r.between(0, 1))       # same inf/out-of-range guard as the build
                    _d = _r.notna().astype(float)
                else:
                    _dd = pd.to_numeric(_gw[_den], errors="coerce").astype(float).replace(0, np.nan)
                    _r = pd.to_numeric(_gw[_num], errors="coerce").astype(float) / _dd
                    _d = _dd.where(_r.notna())
                _ok = _r.notna().to_numpy() & np.isfinite(_d.to_numpy(dtype=float))
                _dv = np.where(_ok, _d.to_numpy(dtype=float), 0.0)
                _rv = np.where(_ok, _r.to_numpy(dtype=float), 0.0)
                _st = {"num": float((_rv * _dv).sum()), "den": float(_dv.sum())}
                for _g in ("M", "W"):
                    _eff = _gm["opp_eff"].get((_g, _nm))
                    _st["eff" + _g] = (float((np.asarray(_eff)[_bin] * _dv).sum())
                                       if _eff is not None else 0.0)
                g52[_nm] = _st
            e["g52"] = g52
        # MODEL G2 (2026-10-12): the LAST 10 ON THIS COURT -- `sd` is already the per-surface
        # frame, so this block is court-specific by construction, matching the build where the
        # rolling window is grouped on player|surface. Walkovers and retirements are dropped
        # before the window is taken, not down-weighted: a win over someone who retired is not a
        # win over them, and their 4-service-game stat lines are not a stat line.
        e["t10g"] = None
        if g2_model() is not None and len(sd):
            _sdc = sd[~_walkover_mask(sd)].sort_values("date")
            _t = _sdc.tail(10)
            if len(_t) >= 3:                      # same min_periods as the build
                def _mn(v):
                    v = pd.to_numeric(v, errors="coerce").dropna()
                    return float(v.mean()) if len(v) else None
                _wl = _t.loc[_t["won"] == 1, "logr"].dropna()     # who they BEAT
                _ll = _t.loc[_t["won"] == 0, "logr"].dropna()     # who they LOST to
                _sga = _t["sg_all"].replace(0, np.nan)
                _rga = _t["rg_all"].replace(0, np.nan)
                e["t10g"] = {
                    "t10_win": float(_t["won"].mean()),
                    "t10_faced": _mn(_t["logr"]),
                    "t10_beaten": float(_wl.mean()) if len(_wl) else None,
                    "t10_bestwin": float(_wl.min()) if len(_wl) else None,
                    "t10_lost": float(_ll.mean()) if len(_ll) else None,
                    "t10_worstloss": float(_ll.max()) if len(_ll) else None,
                    "t10_meff": _mn(_t["meff"]),
                    "t10_losscl": _mn(_t["l_meff"]),
                    "t10_hold": _mn(_t["sg_won"] / _sga),
                    "t10_brk": _mn(_t["rg_won"] / _rga),
                    "t10_n": int(len(_t)),
                    "wo_dropped": int(len(sd) - len(_sdc)),
                }
        p["surf"][surf] = e
    # Model C: this-season (calendar year, any surface)
    yr = gdf[gdf["date"].dt.year == today.year]
    p["season"] = {"sn_win": float(yr["won"].mean()) if len(yr) else None,
                   "sn_n": int(len(yr)),
                   "sn_logr": float(yr["logr"].dropna().mean()) if yr["logr"].notna().any() else None,
                   "sn_sv": float(yr["first_serve_points"].dropna().mean()) if yr["first_serve_points"].notna().any() else None,
                   "sn_meff": (float(yr["meff"].dropna().mean())
                               if "meff" in yr.columns and yr["meff"].notna().any() else None)}
    # Model D v5 (2026-10-01): home-platform block -- prior-365d share / win rate /
    # games share per tournament level (0=tour, 1=challenger, 2=futures/ITF).
    w365a = gdf[gdf["date"] >= today - pd.Timedelta(days=365)]
    p["lvl"] = {}
    if len(w365a) and "lvl" in w365a.columns:
        ntot = len(w365a)
        for lv, lg in w365a.groupby("lvl"):
            _me = lg["meff"].dropna()
            p["lvl"][int(lv)] = {"share": float(len(lg) / ntot), "n": int(len(lg)),
                                 "win": float(lg["won"].mean()),
                                 "meff": float(_me.mean()) if len(_me) else None}
    return p


def _load():
    try:
        mtime = os.path.getmtime(LOGS_PARQUET)
    except OSError:
        return None
    try:
        su_mt = os.path.getmtime(ARTIFACT_SUTR)
    except OSError:
        su_mt = None
    if _cache["profiles"] is not None and _cache["mtime"] == mtime:
        # sUTR hot-reload (2026-10-05, Charaeva case): the court-UTR is a SEPARATE artifact
        # from the match log; reload it whenever it's rebuilt, even if the log is unchanged,
        # so a fresh nightly rating isn't ignored until a restart.
        if su_mt is not None and _cache.get("sutr_mtime") != su_mt:
            try:
                _cache["sutr"] = joblib.load(ARTIFACT_SUTR)
                _cache["sutr_mtime"] = su_mt
            except Exception:  # noqa: BLE001
                pass
        return _cache
    df = _parse(pd.read_parquet(LOGS_PARQUET))
    # own current rank: what opponents' rows say about us (their rival_rank), latest known
    own = df[["rival_slugname", "date", "rival_rank"]].dropna()
    own = own.sort_values("date").groupby("rival_slugname")["rival_rank"].last()
    df["rank_proxy"] = df["player_slug"].map(own)
    # Model D v4 (2026-10-01, user instruction): each opponent judged by their OWN
    # prior any-surface L10 win rate at the time of the match (no ranks) -- merged on
    # so _profile can aggregate "form of the last 10 opponents" per player.
    df = df.sort_values(["player_slug", "date"], kind="stable").reset_index(drop=True)
    _s0 = df.groupby("player_slug", sort=False)["won"].shift(1)
    df["_o10w"] = _s0.groupby(df["player_slug"]).rolling(10, min_periods=4).mean() \
        .reset_index(level=0, drop=True)
    _opp = df[["player_slug", "date", "_o10w"]].rename(
        columns={"player_slug": "rival_slugname", "_o10w": "opp_form"})
    _opp = _opp.drop_duplicates(["rival_slugname", "date"])
    df = df.merge(_opp, on=["rival_slugname", "date"], how="left")
    # Model D v5: tournament level bucket (0=tour, 1=challenger, 2=futures/ITF)
    _sl = df["tournament_level"].astype(str).str.lower()
    df["lvl"] = np.where(_sl.str.contains("challenger"), 1,
                         np.where(_sl.str.contains("future") | _sl.str.contains("itf"), 2, 0))
    today = df["date"].max()
    profiles = {slug: _profile(g, today) for slug, g in df.groupby("player_slug")}
    h2h = {}
    two = df[df["rival_slugname"].notna() & (df["rival_slugname"] != "")]
    for (a, b), g in two.groupby([two["player_slug"], two["rival_slugname"].astype(str)]):
        key = tuple(sorted((a, b)))
        e = h2h.setdefault(key, {"n": 0, "wins": {}, "surf": {}})
        # each match appears once per side; count only from the lexicographically-first side
        if a != key[0]:
            continue
        e["n"] = int(len(g))
        e["wins"][a] = int(g["won"].sum())
        e["wins"][b] = int(len(g) - g["won"].sum())
        for surf, sg2 in g.groupby("surface"):
            e["surf"][surf] = {"n": int(len(sg2)), a: int(sg2["won"].sum()),
                               b: int(len(sg2) - sg2["won"].sum())}
    name_map = {_norm_name(_slug_name(s)): s for s in profiles}
    _cache.update({"mtime": mtime, "profiles": profiles, "h2h": h2h, "name_map": name_map})
    if _cache["model"] is None and os.path.exists(ARTIFACT):
        _cache["model"] = joblib.load(ARTIFACT)
    if _cache["model_b"] is None and os.path.exists(ARTIFACT_B):
        _cache["model_b"] = joblib.load(ARTIFACT_B)
    if _cache["model_c"] is None and os.path.exists(ARTIFACT_C):
        _cache["model_c"] = joblib.load(ARTIFACT_C)
    if _cache["model_d"] is None and os.path.exists(ARTIFACT_D):
        _cache["model_d"] = joblib.load(ARTIFACT_D)
    if su_mt is not None and (_cache.get("sutr") is None or _cache.get("sutr_mtime") != su_mt):
        _cache["sutr"] = joblib.load(ARTIFACT_SUTR)
        _cache["sutr_mtime"] = su_mt
    return _cache


def _lg(p):
    p = min(max(float(p), 1e-6), 1 - 1e-6)
    return np.log(p / (1 - p))


def resolve(name):
    c = _load()
    if not c:
        return None
    nm = _norm_name(name)
    s = c["name_map"].get(nm)
    if s is None:
        # token-subset fallback (2026-09-28, Ayeni case) -- see tennis_context.get_context
        qt = set(nm.split())
        if len(qt) >= 2:
            hits = [v for k, v in c["name_map"].items() if qt <= set(k.split())]
            if len(hits) != 1:
                hits = [v for k, v in c["name_map"].items()
                        if len(set(k.split())) >= 2 and set(k.split()) <= qt]
            if len(hits) != 1:
                def _covers(ptoks, t):
                    if t in ptoks:
                        return True
                    for i in range(1, len(t)):
                        if t[:i] in ptoks and _covers(ptoks, t[i:]):
                            return True
                    return False
                hits = [v for k, v in c["name_map"].items()
                        if all(_covers(set(k.split()), t) for t in qt)]
            if len(hits) != 1:
                # tier 4: transliteration fuzz (2026-09-30, Starodubtseva case) --
                # feed "Yulia" vs the site's "Yuliia". Whole-name close match at a
                # high bar; accept only an unambiguous winner.
                import difflib
                close = difflib.get_close_matches(nm, list(c["name_map"]), n=2, cutoff=0.88)
                if len(close) == 1:
                    hits = [c["name_map"][close[0]]]
                elif len(close) == 2:
                    r = [difflib.SequenceMatcher(None, nm, x).ratio() for x in close]
                    if r[0] - r[1] >= 0.06:
                        hits = [c["name_map"][close[0]]]
            if len(hits) != 1:
                # tier 5: SURNAME + FIRST INITIAL (2026-10-11, Catherine/Caty McNally
                # case). Nickname-vs-formal-name swaps defeat every tier above -- the token
                # sets are not subsets either way and difflib scores below 0.80. Only taken
                # when surname+initial is UNIQUE in the pool (non-unique for 88 of 1,760
                # names, which are therefore left unresolved rather than guessed). Measured
                # on 391 board players: recovers 1 of 47 misses and disagrees with 0 of 344
                # existing resolutions.
                _qt = nm.split()
                if len(_qt) >= 2:
                    _sur, _ini = _qt[-1], _qt[0][0]
                    hits = [v for k, v in c["name_map"].items()
                            if (lambda p: len(p) >= 2 and p[-1] == _sur
                                and p[0][:1] == _ini)(k.split())]
                    # (silva, a) matches strangers, so confirm it is the same person
                    if len(hits) == 1 and not _t5_same_person(
                            nm, [k for k, v in c["name_map"].items() if v == hits[0]]):
                        hits = []
            if len(hits) == 1:
                s = hits[0]
    return s



# Tier-5 safety check (2026-10-13). See _patch_tier5.py: tier 5 reduces a name to
# (alphabetically-last token, alphabetically-first token's initial), which collides across
# different people -- "adan freire da silva" and "andrade da lucas silva" both give
# (silva, a). This confirms the candidate is the SAME PERSON before tier 5 is trusted.
_T5_PARTICLES = {"da", "de", "del", "dos", "das", "van", "von", "la", "le", "di", "el",
                 "bin", "al", "ben", "der", "den", "do", "dela"}


def _t5_same_person(query_norm, profile_keys):
    """True when every substantive token of the profile has a partner in the query.

    Partner = identical, a 3+ character shared prefix (caty~catherine), or a close spelling
    (Deigo~Diego, Giorgia~Georgia, which differ at character 2 so a prefix rule misses them).
    Checked in this direction because boards legitimately ADD tokens to a name; requiring
    every QUERY token to match was measured and destroyed four correct resolutions.
    """
    import difflib
    import os as _os
    sub = lambda k: [t for t in k.split() if t not in _T5_PARTICLES]
    qs = sub(query_norm)
    if not qs:
        return False

    def partner(p):
        for t in qs:
            if p == t or len(_os.path.commonprefix([p, t])) >= 3:
                return True
            if difflib.SequenceMatcher(None, p, t).ratio() >= 0.75:
                return True
        return False

    for k in profile_keys:
        ps = sub(k)
        if ps and all(partner(p) for p in ps):
            return True
    return False


def _feats(p1, p2, surface, h):
    s1 = p1["surf"].get(surface) or {}
    s2 = p2["surf"].get(surface) or {}
    def d(a, b):
        return (a - b) if (a is not None and b is not None) else 0.0
    n = h["n"] if h else 0
    w1 = (h["wins"].get("_p1", 0) if False else (h["wins"].get(p1["_slug"], 0) if h else 0))
    hs = (h.get("surf", {}).get(surface) if h else None) or {}
    sn = hs.get("n", 0)
    sw1 = hs.get(p1["_slug"], 0)
    f = {
        "d_sr10": d(s1.get("sr10"), s2.get("sr10")),
        "d_l10": d(p1["l10"], p2["l10"]),
        "d_l20": d(p1["l20"], p2["l20"]),
        "d_swin": d(s1.get("won"), s2.get("won")),
        "d_sgw": d(s1.get("sgw_pct"), s2.get("sgw_pct")),
        "d_rgw": d(s1.get("rgw_pct"), s2.get("rgw_pct")),
        "d_sp": d(s1.get("sp_rate"), s2.get("sp_rate")),
        "d_rp": d(s1.get("rp_rate"), s2.get("rp_rate")),
        "d_oppq": d(p2["oppq"], p1["oppq"]),
        "d_v100": d(p1["v100"], p2["v100"]),
        "d_rust": d(p2["days_off"], p1["days_off"]),
        # RANK-SIGN FIX (2026-10-09): training (_tennis_model_a_build.py) defines the gap as
        # log(p1 rank) - log(p2 rank) (+ = p1 worse); live had it reversed, which left Model A
        # at 51.7% live (n=718) vs ~61% for B/C/D. Now matches training.
        "d_lrank": (np.log(min(max(p1["rank"] or 0, 1), 2000)) - np.log(min(max(p2["rank"] or 0, 1), 2000))
                    if (p1["rank"] and p2["rank"]) else 0.0),
        "f_h2h_n": min(n, 20),
        "f_h2h_share": (w1 / n - 0.5) if n else 0.0,
        "f_h2h_s_share": (sw1 / sn - 0.5) if sn else 0.0,
    }
    return f


def predict(name1, name2, surface, market_p1=None):
    """Model A % for name1 beating name2 on this surface + the pair's real H2H record.
    Returns None when either player is outside the pool or artifacts are missing."""
    c = _load()
    if not c or c["model"] is None:
        return None
    s1, s2 = resolve(name1), resolve(name2)
    if not s1 or not s2 or s1 == s2:
        return None
    p1 = dict(c["profiles"][s1], _slug=s1)
    p2 = dict(c["profiles"][s2], _slug=s2)
    surface = str(surface or "Hard").title()
    h = c["h2h"].get(tuple(sorted((s1, s2))))
    f = _feats(p1, p2, surface, h)
    X = np.array([[f[k] for k in FEATURES]])
    mdl = c["model"]
    prob = float(0.5 * (mdl["lr"].predict_proba(X)[0, 1] + mdl["xgb"].predict_proba(X)[0, 1]))
    out = {"p1_prob": round(prob, 4), "p2_prob": round(1 - prob, 4),
           "h2h": None, "trained_at": mdl.get("trained_at"),
           "thin": bool(p1["surf"].get(surface) is None or p2["surf"].get(surface) is None)}
    if market_p1 is not None and mdl.get("lr_ms") is not None:
        Xm = np.column_stack([[_lg(market_p1)], X])
        out["market_aware_p1"] = round(float(mdl["lr_ms"].predict_proba(Xm)[0, 1]), 4)
    if h and h["n"]:
        hs = (h.get("surf", {}).get(surface) or {})
        out["h2h"] = {"n": h["n"], "p1_wins": h["wins"].get(s1, 0), "p2_wins": h["wins"].get(s2, 0),
                      "surface_n": hs.get("n", 0), "surface_p1_wins": hs.get(s1, 0),
                      "surface": surface}
    return out


def h2h_for(name1, name2, surface=None):
    """The current head-to-head record for a pair, shaped like predict()'s out['h2h'] (or
    None). Used to attach H2H to results-history cards, which are rebuilt from frozen
    columns that never stored it (2026-10-04 bug: history falsely showed 'no prior H2H').
    Uses the current cache, so for an older match it may include meetings since -- fine for
    a display record on recent results."""
    c = _load()
    if not c:
        return None
    s1, s2 = resolve(name1), resolve(name2)
    if not s1 or not s2 or s1 == s2:
        return None
    h = c["h2h"].get(tuple(sorted((s1, s2))))
    if not h or not h["n"]:
        return None
    surface = str(surface or "Hard").title()
    hs = (h.get("surf", {}).get(surface) or {})
    return {"n": h["n"], "p1_wins": h["wins"].get(s1, 0), "p2_wins": h["wins"].get(s2, 0),
            "surface_n": hs.get("n", 0), "surface_p1_wins": hs.get(s1, 0), "surface": surface}


def _feats_b(p1, p2, surface):
    s1 = p1["surf"].get(surface) or {}
    s2 = p2["surf"].get(surface) or {}
    def d(a, b):
        return (a - b) if (a is not None and b is not None) else 0.0
    return {
        "d_swin": d(s1.get("won"), s2.get("won")),
        "d_sr10": d(s1.get("sr10"), s2.get("sr10")),
        "d_sgw": d(s1.get("sgw_pct"), s2.get("sgw_pct")),
        "d_rgw": d(s1.get("rgw_pct"), s2.get("rgw_pct")),
        "d_sp": d(s1.get("sp_rate"), s2.get("sp_rate")),
        "d_rp": d(s1.get("rp_rate"), s2.get("rp_rate")),
        "d_faced": d(s2.get("faced10"), s1.get("faced10")),
        "d_beaten": d(s2.get("beaten10"), s1.get("beaten10")),
        "d_lost": d(s1.get("lost10"), s2.get("lost10")),
        "d_bestwin": d(s2.get("bestwin10"), s1.get("bestwin10")),
    }


def predict_b(name1, name2, surface, market_p1=None):
    """Model B: last-10-on-this-surface only -- recent stats plus rank-adjusted who-they-
    beat/lost-to. Stats-only % plus the market-aware head when market_p1 is given."""
    c = _load()
    if not c or c["model_b"] is None:
        return None
    s1, s2 = resolve(name1), resolve(name2)
    if not s1 or not s2 or s1 == s2:
        return None
    p1, p2 = c["profiles"][s1], c["profiles"][s2]
    surface = str(surface or "Hard").title()
    f = _feats_b(p1, p2, surface)
    X = np.array([[f[k] for k in FEATURES_B]])
    mdl = c["model_b"]
    prob = float(0.5 * (mdl["lr"].predict_proba(X)[0, 1] + mdl["xgb"].predict_proba(X)[0, 1]))
    out = {"p1_prob": round(prob, 4), "p2_prob": round(1 - prob, 4),
           "trained_at": mdl.get("trained_at"),
           "thin": bool(p1["surf"].get(surface) is None or p2["surf"].get(surface) is None)}
    if market_p1 is not None and mdl.get("lr_ms") is not None:
        Xm = np.column_stack([[_lg(market_p1)], X])
        out["market_aware_p1"] = round(float(mdl["lr_ms"].predict_proba(Xm)[0, 1]), 4)
    return out


def _band_of(rank):
    if rank is None:
        return 3
    r = float(rank)
    return 0 if r <= 50 else (1 if r <= 150 else (2 if r <= 400 else 3))


def predict_c(name1, name2, surface, market_p1=None, variant=None):
    """Model C: the full 52w-on-surface profile + season + rank-band matchup + last-10 +
    H2H. See ARTIFACT_C comment for the careful label -- edge shown only vs average odds."""
    c = _load()
    if not c or c["model_c"] is None:
        return None
    s1, s2 = resolve(name1), resolve(name2)
    if not s1 or not s2 or s1 == s2:
        return None
    p1, p2 = c["profiles"][s1], c["profiles"][s2]
    surface = str(surface or "Hard").title()
    e1 = (p1["surf"].get(surface) or {})
    e2 = (p2["surf"].get(surface) or {})
    c1, c2 = e1.get("c52"), e2.get("c52")
    h = c["h2h"].get(tuple(sorted((s1, s2))))

    def d(a, b):
        return (a - b) if (a is not None and b is not None) else 0.0
    f = {}
    KEYS = ("m_won", "m_first_serve_accuracy", "m_first_serve_points", "m_second_serve_points",
            "m_return_1st_serve_points", "m_return_2nd_serve_points", "m_perf", "m_dr", "m_meff",
            "c_sgw", "c_rgw", "c_bpsav", "c_bpconv", "c_bpcre_pg", "c_bpdef_pg", "c_aces_pg",
            "c_dfs_pg", "c_sp", "c_rp", "c_tb")
    for k in KEYS:
        f["d_" + k] = d(c1.get(k) if c1 else None, c2.get(k) if c2 else None)
    sn1, sn2 = p1.get("season") or {}, p2.get("season") or {}
    f["d_sn_win"] = d(sn1.get("sn_win"), sn2.get("sn_win"))
    f["d_sn_sv"] = d(sn1.get("sn_sv"), sn2.get("sn_sv"))
    f["d_sn_faced"] = d(sn2.get("sn_logr"), sn1.get("sn_logr"))
    f["d_t10_win"] = d(e1.get("won"), e2.get("won"))
    f["d_t10_faced"] = d(e2.get("faced10"), e1.get("faced10"))
    f["d_t10_beaten"] = d(e2.get("beaten10"), e1.get("beaten10"))
    f["d_t10_bestwin"] = d(e2.get("bestwin10"), e1.get("bestwin10"))
    f["d_t10_losscl"] = d(e1.get("losscl10"), e2.get("losscl10"))
    f["d_faced"] = d(c2.get("m_logr") if c2 else None, c1.get("m_logr") if c1 else None)
    f["d_beaten"] = d(c2.get("m_w_logr") if c2 else None, c1.get("m_w_logr") if c1 else None)
    b2i, b1i = _band_of(p2.get("rank")), _band_of(p1.get("rank"))
    v1 = (c1 or {}).get(f"m_bw{b2i}")
    v2 = (c2 or {}).get(f"m_bw{b1i}")
    f["d_vs_band"] = d(v1, v2)
    # RANK-SIGN FIX (2026-10-09): training convention log(p1 rank) - log(p2 rank).
    f["d_lrank"] = (np.log(min(max(p1.get("rank") or 0, 1), 2000)) - np.log(min(max(p2.get("rank") or 0, 1), 2000))
                    if (p1.get("rank") and p2.get("rank")) else 0.0)
    n = h["n"] if h else 0
    w1 = h["wins"].get(s1, 0) if h else 0
    hs = (h.get("surf", {}).get(surface) if h else None) or {}
    f["f_h2h_n"] = min(n, 20)
    f["f_h2h_share"] = (w1 / n - 0.5) if n else 0.0
    f["f_h2h_s_share"] = ((hs.get(s1, 0) / hs["n"]) - 0.5) if hs.get("n") else 0.0
    # `variant` picks a tracked subset-of-features artifact instead of the shipped one
    # (2026-10-10). Everything downstream is identical, so the variants are directly
    # comparable to C on the same game.
    mdl = c_variant(variant) if variant else c["model_c"]
    if mdl is None:
        return None
    X = np.array([[f.get(k, 0.0) for k in mdl["features"]]])
    prob = float(0.5 * (mdl["lr"].predict_proba(X)[0, 1] + mdl["xgb"].predict_proba(X)[0, 1]))
    out = {"p1_prob": round(prob, 4), "p2_prob": round(1 - prob, 4),
           "trained_at": mdl.get("trained_at"), "thin": bool(c1 is None or c2 is None)}
    # Model P inputs (2026-10-09): p1-minus-p2 stat diffs, same definitions as training.
    out["pf"] = {k: float(f.get(k) or 0.0) for k in ("d_vs_band", "d_m_perf", "d_m_won", "d_c_rp", "d_c_sp")}
    # rank gap in the TRAINING convention (log p1 rank - log p2 rank, + = p1 worse). The
    # live f["d_lrank"] above is the reverse (rank-sign bug found 2026-10-09), so P builds
    # its own from the ranks and stays correct whether or not that bug is fixed.
    out["pf"]["d_lrank"] = (float(np.log(min(max(p1.get("rank") or 0, 1), 2000)) - np.log(min(max(p2.get("rank") or 0, 1), 2000)))
                            if (p1.get("rank") and p2.get("rank")) else 0.0)
    if market_p1 is not None and mdl.get("lr_ms") is not None:
        Xm = np.column_stack([[_lg(market_p1)], X])
        out["market_aware_p1"] = round(float(mdl["lr_ms"].predict_proba(Xm)[0, 1]), 4)
    return out


def predict_g(name1, name2, surface, market_p1=None, league=None):
    """Model G: the nine 52-week stats, opponent-rank-adjusted and sample-size-shrunk, and
    nothing else. See the ARTIFACT_G comment -- honest forecaster, market-beaten, NO betting
    edge on either side. Display and log only.

    Gender comes from the league exactly as the lanes derive it, because the rank-discount
    curves and the shrinkage constants are fit per gender and men's and women's stat levels
    differ far too much to pool (hold% 75.6% vs 60.2%).
    """
    mdl = g_model()
    c = _load()
    if mdl is None or not c:
        return None
    s1, s2 = resolve(name1), resolve(name2)
    if not s1 or not s2 or s1 == s2:
        return None
    surface = str(surface or "Hard").title()
    g1 = ((c["profiles"][s1]["surf"].get(surface) or {}).get("g52"))
    g2 = ((c["profiles"][s2]["surf"].get(surface) or {}).get("g52"))
    if not g1 or not g2:
        return None
    gd = "W" if str(league or "").lower() in ("wta", "itf_women") else "M"

    def stat(blk, nm):
        """Opponent-adjusted, then shrunk toward the tour mean by this stat's own
        denominator. k is the sample size at which the raw figure earns half the weight."""
        st = blk.get(nm)
        if not st or not st.get("den"):
            return None, 0.0
        k = float(mdl["k"].get((gd, nm), 1.0))
        pr = float(mdl["prior"].get((gd, nm), 0.0))
        num = st["num"] - st.get("eff" + gd, 0.0)
        return (num + k * pr) / (st["den"] + k), float(st["den"])

    f = {}
    for nm, _, _ in G_STATS:
        v1, d1 = stat(g1, nm)
        v2, d2 = stat(g2, nm)
        f["d_" + nm] = (v1 - v2) if (v1 is not None and v2 is not None) else 0.0
        f["dn_" + nm] = float(np.log1p(d1) - np.log1p(d2))
    n1, n2 = float(g1.get("w_n") or 0), float(g2.get("w_n") or 0)
    f["d_matches"] = float(np.log1p(n1) - np.log1p(n2))
    f["f_nmin"] = float(np.log1p(min(n1, n2)))
    fa1, fa2 = g1.get("faced"), g2.get("faced")
    # + = p1 has faced the TOUGHER schedule (lower log-rank), matching the training sign
    f["d_faced"] = float(fa2 - fa1) if (fa1 is not None and fa2 is not None) else 0.0
    # how many sides are read off a widened last-20 window rather than a real 365-day one
    f["f_wide"] = float(g1.get("wide") or 0.0) + float(g2.get("wide") or 0.0)

    X = np.array([[f.get(k, 0.0) for k in mdl["features"]]])
    prob = float(0.5 * (mdl["lr"].predict_proba(X)[0, 1] + mdl["xgb"].predict_proba(X)[0, 1]))
    out = {"p1_prob": round(prob, 4), "p2_prob": round(1 - prob, 4),
           "trained_at": mdl.get("trained_at"), "gender": gd,
           "n1": int(n1), "n2": int(n2),
           # which sides are read off a widened last-20 window instead of a real 365-day one,
           # so the card can say so rather than presenting a thin read as a full one
           "wide1": bool(g1.get("wide")), "wide2": bool(g2.get("wide"))}
    if market_p1 is not None and mdl.get("lr_ms") is not None:
        Xm = np.column_stack([[_lg(market_p1)], X])
        out["market_aware_p1"] = round(float(mdl["lr_ms"].predict_proba(Xm)[0, 1]), 4)
    return out


def predict_g2(name1, name2, surface, market_p1=None, league=None):
    """Model G2: every Model G feature plus the last-10-on-this-court block (who they beat, who
    they lost to, who they played, how they performed), walkovers excluded. See the ARTIFACT_G2
    comment -- beats G in all three walk-forward years but still market-beaten and still no
    betting edge, so display and log only."""
    mdl = g2_model()
    c = _load()
    if mdl is None or not c:
        return None
    s1, s2 = resolve(name1), resolve(name2)
    if not s1 or not s2 or s1 == s2:
        return None
    surface = str(surface or "Hard").title()
    e1 = (c["profiles"][s1]["surf"].get(surface) or {})
    e2 = (c["profiles"][s2]["surf"].get(surface) or {})
    g1, g2 = e1.get("g52"), e2.get("g52")
    if not g1 or not g2:
        return None
    t1, t2 = e1.get("t10g") or {}, e2.get("t10g") or {}
    gd = "W" if str(league or "").lower() in ("wta", "itf_women") else "M"

    def stat(blk, nm):
        st = blk.get(nm)
        if not st or not st.get("den"):
            return None, 0.0
        k = float(mdl["k"].get((gd, nm), 1.0))
        pr = float(mdl["prior"].get((gd, nm), 0.0))
        return (st["num"] - st.get("eff" + gd, 0.0) + k * pr) / (st["den"] + k), float(st["den"])

    f = {}
    for nm in mdl["stats"]:
        v1, d1 = stat(g1, nm)
        v2, d2 = stat(g2, nm)
        f["d_" + nm] = (v1 - v2) if (v1 is not None and v2 is not None) else 0.0
        f["dn_" + nm] = float(np.log1p(d1) - np.log1p(d2))
    n1, n2 = float(g1.get("w_n") or 0), float(g2.get("w_n") or 0)
    f["d_matches"] = float(np.log1p(n1) - np.log1p(n2))
    f["f_nmin"] = float(np.log1p(min(n1, n2)))
    fa1, fa2 = g1.get("faced"), g2.get("faced")
    f["d_faced"] = float(fa2 - fa1) if (fa1 is not None and fa2 is not None) else 0.0
    f["f_wide"] = float(g1.get("wide") or 0.0) + float(g2.get("wide") or 0.0)

    # the last-10 additions. The rank columns are LOG RANKS, so lower = tougher: those diff as
    # (opponent minus us) to keep "+ = p1 did the harder thing" consistent, exactly as trained.
    def d_(nm, flip=False):
        a, b_ = t1.get(nm), t2.get(nm)
        if a is None or b_ is None:
            return 0.0
        return float(b_ - a) if flip else float(a - b_)
    for nm in ("t10_win", "t10_meff", "t10_hold", "t10_brk", "t10_losscl"):
        f["d_" + nm] = d_(nm)
    for nm in ("t10_faced", "t10_beaten", "t10_bestwin", "t10_lost", "t10_worstloss"):
        f["d_" + nm] = d_(nm, flip=True)
    f["d_t10_n"] = float((t1.get("t10_n") or 0) - (t2.get("t10_n") or 0))
    f["f_t10_nmin"] = float(min(t1.get("t10_n") or 0, t2.get("t10_n") or 0))

    X = np.array([[f.get(k, 0.0) for k in mdl["features"]]])
    prob = float(0.5 * (mdl["lr"].predict_proba(X)[0, 1] + mdl["xgb"].predict_proba(X)[0, 1]))
    out = {"p1_prob": round(prob, 4), "p2_prob": round(1 - prob, 4),
           "trained_at": mdl.get("trained_at"), "gender": gd,
           "n1": int(n1), "n2": int(n2),
           "t10_n1": int(t1.get("t10_n") or 0), "t10_n2": int(t2.get("t10_n") or 0),
           "wo1": int(t1.get("wo_dropped") or 0), "wo2": int(t2.get("wo_dropped") or 0),
           "thin": bool(not t1 or not t2)}
    if market_p1 is not None and mdl.get("lr_ms") is not None:
        Xm = np.column_stack([[_lg(market_p1)], X])
        out["market_aware_p1"] = round(float(mdl["lr_ms"].predict_proba(Xm)[0, 1]), 4)
    return out


def predict_d(name1, name2, surface, market_p1=None, level=None):
    """Model D (2026-09-30, user ask): HEAVY last-10 form. Recent win rates (surface +
    overall), form vs the player's OWN 52w surface baseline, recency-weighted
    (0.9/match) L10 serve-return splits, rest days, loss closeness. v4 (2026-10-01,
    user instruction "ranks can be misleading"): NO ranks anywhere -- each of the last
    10 opponents is judged by THEIR OWN L10 form at the time of the match (form of
    schedule faced, form of players beaten, best in-form scalp, record + games share
    vs in-form opponents). v5 adds (user): this-season quality + volume, and the
    home-platform block -- share/win/games-share at TODAY'S level (tour/challenger/
    ITF) over the prior 365d, via the `level` arg. DISPLAY-ONLY like A and B."""
    c = _load()
    if not c or c["model_d"] is None:
        return None
    s1, s2 = resolve(name1), resolve(name2)
    if not s1 or not s2 or s1 == s2:
        return None
    p1, p2 = c["profiles"][s1], c["profiles"][s2]
    surface = str(surface or "Hard").title()
    e1 = (p1["surf"].get(surface) or {})
    e2 = (p2["surf"].get(surface) or {})
    c1, c2 = e1.get("c52"), e2.get("c52")
    w1, w2 = e1.get("ewd") or {}, e2.get("ewd") or {}

    def d(a, b):
        return (a - b) if (a is not None and b is not None) else 0.0

    def form(e, cc, tk, mk):
        if cc and e.get(tk) is not None and cc.get(mk) is not None:
            return e[tk] - cc[mk]
        return None
    f = {
        "d_t10win": d(e1.get("won"), e2.get("won")),
        "d_o10win": d(p1.get("l10"), p2.get("l10")),
        "d_t10meff": d(e1.get("meff10"), e2.get("meff10")),
        "d_form_win": d(form(e1, c1, "won", "m_won"), form(e2, c2, "won", "m_won")),
        "d_form_meff": d(form(e1, c1, "meff10", "m_meff"), form(e2, c2, "meff10", "m_meff")),
        "d_form_srv": d(form(e1, c1, "first_serve_points", "m_first_serve_points"),
                        form(e2, c2, "first_serve_points", "m_first_serve_points")),
        # v4: opponent quality by the OPPONENTS' OWN L10 form (no ranks anywhere)
        "d_fq_faced": d(e1.get("fq_faced"), e2.get("fq_faced")),
        "d_fq_beaten": d(e1.get("fq_beaten"), e2.get("fq_beaten")),
        "d_fq_bestwin": d(e1.get("fq_bestwin"), e2.get("fq_bestwin")),
        "d_losscl": d(e1.get("losscl10"), e2.get("losscl10")),
        "d_fq_hotwin": d(e1.get("fq_hotwin"), e2.get("fq_hotwin")),
        "d_fq_hotmeff": d(e1.get("fq_hotmeff"), e2.get("fq_hotmeff")),
        "d_hold": d(w1.get("hold"), w2.get("hold")),
        "d_break": d(w1.get("break"), w2.get("break")),
        "d_fsp": d(w1.get("fsp"), w2.get("fsp")),
        "d_ssp": d(w1.get("ssp"), w2.get("ssp")),
        "d_r1": d(w1.get("r1"), w2.get("r1")),
        "d_r2": d(w1.get("r2"), w2.get("r2")),
        "d_aces": d(w1.get("aces"), w2.get("aces")),
        "d_dfs": d(w2.get("dfs"), w1.get("dfs")),
        "d_bpcv": d(w1.get("bpcv"), w2.get("bpcv")),
        "d_rest": min(p1.get("days_off") or 0, 30) - min(p2.get("days_off") or 0, 30),
    }
    # v5: this-season quality/volume + home-platform (today's level from the board's
    # league tag: atp/wta=tour, challenger=1, itf=2)
    sn1, sn2 = p1.get("season") or {}, p2.get("season") or {}
    f["d_sn_win"] = d(sn1.get("sn_win"), sn2.get("sn_win"))
    f["d_sn_meff"] = d(sn1.get("sn_meff"), sn2.get("sn_meff"))
    f["d_sn_vol"] = min(sn1.get("sn_n") or 0, 60) - min(sn2.get("sn_n") or 0, 60)
    _lg9 = str(level or "").lower()
    _bk = 1 if "challenger" in _lg9 else (2 if "itf" in _lg9 else 0)
    l1 = (p1.get("lvl") or {}).get(_bk) or {}
    l2 = (p2.get("lvl") or {}).get(_bk) or {}
    f["d_lvl_share"] = d(l1.get("share"), l2.get("share"))
    f["d_lvl_win"] = d(l1.get("win"), l2.get("win"))
    f["d_lvl_meff"] = d(l1.get("meff"), l2.get("meff"))
    # v6: court-specific UTR (surface rating; both need 5+ rated matches to diff)
    _su = (c.get("sutr") or {}).get("ratings") or {}
    _u1 = (_su.get(s1) or {}).get(surface) or {}
    _u2 = (_su.get(s2) or {}).get(surface) or {}
    f["d_sutr"] = (float(_u1["r"]) - float(_u2["r"])
                   if _u1.get("n", 0) >= 5 and _u2.get("n", 0) >= 5 else 0.0)
    mdl = c["model_d"]
    X = np.array([[f.get(k, 0.0) for k in mdl["features"]]])
    prob = float(0.5 * (mdl["lr"].predict_proba(X)[0, 1] + mdl["xgb"].predict_proba(X)[0, 1]))
    out = {"p1_prob": round(prob, 4), "p2_prob": round(1 - prob, 4),
           "trained_at": mdl.get("trained_at"),
           "thin": bool(e1.get("won") is None or e2.get("won") is None
                        or c1 is None or c2 is None)}
    # court-specific UTR for display (surface rating + matches rated)
    if _u1.get("r") is not None:
        out["sutr_p1"] = {"r": _u1["r"], "n": _u1.get("n")}
    if _u2.get("r") is not None:
        out["sutr_p2"] = {"r": _u2["r"], "n": _u2.get("n")}

    # per-player DETAIL readout (2026-10-01, user "i don't see v4/v5"): the season,
    # home-platform and opponent-form numbers the model actually uses, made visible.
    def _det(p, e, cc, lv):
        sn = p.get("season") or {}
        n9 = int(sn.get("sn_n") or 0)
        w9 = int(round((sn.get("sn_win") or 0) * n9))
        fw = None
        if cc and e.get("won") is not None and cc.get("m_won") is not None:
            fw = e["won"] - cc["m_won"]
        return {"ssn": (f"{w9}-{n9 - w9}" if n9 else None),
                "l10": e.get("won"), "form": fw,
                "lvl_share": lv.get("share"), "lvl_win": lv.get("win"),
                "fq_faced": e.get("fq_faced"), "fq_beaten": e.get("fq_beaten")}
    out["d1"] = _det(p1, e1, c1, l1)
    out["d2"] = _det(p2, e2, c2, l2)
    # Model P inputs (2026-10-09)
    out["pf"] = {k: float(f.get(k) or 0.0) for k in ("d_form_win", "d_sutr")}
    if market_p1 is not None and mdl.get("lr_ms") is not None:
        Xm = np.column_stack([[_lg(market_p1)], X])
        out["market_aware_p1"] = round(float(mdl["lr_ms"].predict_proba(Xm)[0, 1]), 4)
    return out


def _game_win(p):
    """Server wins a deuce-scoring game given per-point win prob p (closed form)."""
    q = 1 - p
    return p ** 4 * (1 + 4 * q + 10 * q * q) + 20 * (p ** 3) * (q ** 3) * (p * p / (1 - 2 * p * q))


def _tb_win(pa, pb):
    """P(player 1 wins a 7-point tiebreak, win by 2). pa = p1's point-win prob on own
    serve, pb = p1's point-win prob returning (= 1 - p2's serve-point prob). Serve
    order: p1 serves point 0, then alternating pairs. DP with deuce closed form at 6-6."""
    from functools import lru_cache

    def server_p(t):  # p1's win prob for point index t
        return pa if (t % 4 in (0, 3)) else pb

    @lru_cache(maxsize=None)
    def w(a, b):
        if a >= 7 and a - b >= 2:
            return 1.0
        if b >= 7 and b - a >= 2:
            return 0.0
        if a >= 6 and b >= 6:
            # sudden-deuce approximation: alternate serve -> avg point prob
            pavg = 0.5 * (pa + pb)
            return pavg * pavg / (pavg * pavg + (1 - pavg) * (1 - pavg))
        p = server_p(a + b)
        return p * w(a + 1, b) + (1 - p) * w(a, b + 1)
    return w(0, 0)


def _set_win(h1, h2, ptb):
    """P(p1 wins a set) from hold probs (p1 serves game 0) + tiebreak prob. Exact DP."""
    from functools import lru_cache

    @lru_cache(maxsize=None)
    def w(a, b):
        if a >= 6 and a - b >= 2 or a == 7:
            return 1.0
        if b >= 6 and b - a >= 2 or b == 7:
            return 0.0
        if a == 6 and b == 6:
            return ptb
        p = h1 if (a + b) % 2 == 0 else (1 - h2)  # p1's prob of winning this game
        return p * w(a + 1, b) + (1 - p) * w(a, b + 1)
    return w(0, 0)


def simulate_match(name1, name2, surface, level=None, best_of_5=False, n=100000,
                   c_anchor=None, c_weight=0.5, sutr_weight=None):
    """MONTE CARLO (2026-10-01, user ask): simulate the match n times. Point probs from
    each player's recency-weighted serve stats vs the opponent's return stats (Model D's
    ewd block); exact game/tiebreak/set math; randomness drawn at set level (sets are
    independent in this model, so the match-outcome distribution is identical to a
    point-level sim). Seeded by the matchup so the number is stable between refreshes.

    c_anchor (2026-10-02, user "make C's MC like D's — independent, can disagree"): a
    Model-C match prob to anchor the serve sim toward INSTEAD of the court-UTR. Same
    half-shrink mechanism as the sUTR anchor, but the class read comes from Model C, so
    this is a genuine serve-based sim (real sims, serve dynamics, form noise) that is
    pulled toward C yet can still disagree with it. When given, the sUTR anchor is skipped."""
    import zlib
    c = _load()
    if not c:
        return None
    s1, s2 = resolve(name1), resolve(name2)
    if not s1 or not s2 or s1 == s2:
        return None
    p1, p2 = c["profiles"][s1], c["profiles"][s2]
    surface = str(surface or "Hard").title()
    need = ("fsp", "ssp", "r1", "r2")

    def _ewd_for(p):
        """Serve/return block for this surface; if it's empty (the player has matches on
        the surface but no serve statlines -- common in lower-tier WTA/ITF, the Golovina-vs-
        Micic case 2026-10-03), FALL BACK to another surface that does have the stats so the
        Monte Carlo can still run. Prefer Hard as the neutral default. Returns (ewd, fell_back)."""
        surfs = p.get("surf") or {}
        w = (surfs.get(surface) or {}).get("ewd") or {}
        if all(w.get(k) is not None for k in need):
            return w, False
        order = ["Hard", "Clay", "Grass"] + [s for s in surfs if s not in ("Hard", "Clay", "Grass")]
        for s in order:
            if s == surface:
                continue
            w2 = (surfs.get(s) or {}).get("ewd") or {}
            if all(w2.get(k) is not None for k in need):
                return w2, True
        return None, False

    w1, _fb1 = _ewd_for(p1)
    w2, _fb2 = _ewd_for(p2)
    if w1 is None or w2 is None:
        return None
    surface_fallback = bool(_fb1 or _fb2)
    AV_SV = 56.5 if "wta" in str(level or "").lower() or "women" in str(level or "").lower() else 61.0
    sv1 = 0.6 * w1["fsp"] + 0.4 * w1["ssp"]
    sv2 = 0.6 * w2["fsp"] + 0.4 * w2["ssp"]
    rt1 = 0.5 * w1["r1"] + 0.5 * w1["r2"]
    rt2 = 0.5 * w2["r1"] + 0.5 * w2["r2"]
    # opponent-adjusted per-point serve-win probs
    p1pt = float(np.clip((sv1 - (rt2 - (100 - AV_SV))) / 100.0, 0.35, 0.85))
    p2pt = float(np.clip((sv2 - (rt1 - (100 - AV_SV))) / 100.0, 0.35, 0.85))
    # sUTR ANCHOR (2026-10-01, Chwalinska 94% lesson): raw serve/return stats carry no
    # strength-of-schedule context -- a 125K regular's padded stats vs a tour player's
    # hard-earned ones produced a 94% sim on a -164 favorite who lost. The court UTR is
    # opponent-adjusted by construction, so shrink the stat-implied games share HALFWAY
    # toward the sUTR-implied share (1.0 rating pt ~ 60/40 games) before simulating.
    sutr_anchored = False
    c_anchored = False

    def _gshare(pa, pb):
        return (_game_win(pa) + 1 - _game_win(pb)) / 2.0

    def _matchp(pa, pb):
        """Analytic match win prob for p1 from the two per-point serve probs."""
        sp = _set_win(_game_win(pa), _game_win(pb), _tb_win(pa, 1 - pb))
        return (sp ** 3 * (6 * sp * sp - 15 * sp + 10)) if best_of_5 else (sp * sp * (3 - 2 * sp))

    # ANCHORS compose (2026-10-02): (1) sUTR games-share shrink (strength-of-schedule
    # correction, the Chwalinska fix), weight = sutr_weight, THEN (2) Model-C match-prob
    # anchor, weight = c_weight. Defaults keep the D-MC exactly as before (sutr_weight 0.5,
    # no C). The C-MC variants pass different weights (see main.py): c50 = C only (sutr 0);
    # c75 = harder C pull; cutr = C plus a STRONGER sUTR shrink to de-pad serve stats first.
    _sw = 0.5 if sutr_weight is None else float(sutr_weight)
    if _sw > 0:
        _sur = (c.get("sutr") or {}).get("ratings") or {}
        _a1 = (_sur.get(s1) or {}).get(surface) or {}
        _a2 = (_sur.get(s2) or {}).get(surface) or {}
        if _a1.get("n", 0) >= 5 and _a2.get("n", 0) >= 5:
            g_sutr = min(max(0.5 + (float(_a1["r"]) - float(_a2["r"])) / 10.0, 0.2), 0.8)
            target = (1 - _sw) * _gshare(p1pt, p2pt) + _sw * g_sutr
            lo, hi = -0.15, 0.15
            for _ in range(30):
                mid = (lo + hi) / 2.0
                if _gshare(float(np.clip(p1pt + mid, 0.35, 0.85)),
                           float(np.clip(p2pt - mid, 0.35, 0.85))) < target:
                    lo = mid
                else:
                    hi = mid
            d0 = (lo + hi) / 2.0
            p1pt = float(np.clip(p1pt + d0, 0.35, 0.85))
            p2pt = float(np.clip(p2pt - d0, 0.35, 0.85))
            sutr_anchored = True
    if c_anchor is not None:
        # MODEL-C ANCHOR: pull the serve sim toward Model C in MATCH-PROB space (not
        # games-share -- that amplifies through the bo3 structure and overshoots). Blend
        # the sim's own analytic match prob with C's at weight c_weight, then solve for the
        # per-point shift that produces it. Still independent (serve stats + any sUTR shrink
        # set the starting point and can keep it on the other side of 50%), centered on C.
        cw = min(max(float(c_weight), 0.0), 1.0)
        base = _matchp(p1pt, p2pt)
        tgt = (1 - cw) * base + cw * min(max(float(c_anchor), 0.02), 0.98)
        lo, hi = -0.25, 0.25
        for _ in range(45):
            mid = (lo + hi) / 2.0
            if _matchp(float(np.clip(p1pt + mid, 0.35, 0.85)),
                       float(np.clip(p2pt - mid, 0.35, 0.85))) < tgt:
                lo = mid
            else:
                hi = mid
        d0 = (lo + hi) / 2.0
        p1pt = float(np.clip(p1pt + d0, 0.35, 0.85))
        p2pt = float(np.clip(p2pt - d0, 0.35, 0.85))
        c_anchored = True
    h1, h2 = _game_win(p1pt), _game_win(p2pt)
    rng = np.random.default_rng(zlib.crc32(f"{s1}|{s2}|{surface}|{'C' if c_anchored else 'U'}".encode()))
    # DAY-TO-DAY FORM NOISE (2026-10-01, same lesson): fixed point probs assume both
    # players bring their exact average every night, which makes extremes overconfident.
    # Each simulated match draws its own serve form (~N(0, 4pts) per player, held for
    # the whole match); unique prob pairs share one exact set-DP evaluation.
    SIGMA = 0.04
    z = rng.normal(0.0, SIGMA, size=(n, 2))
    pp1 = np.clip(p1pt + z[:, 0], 0.35, 0.85)
    pp2 = np.clip(p2pt + z[:, 1], 0.35, 0.85)
    keys = (np.round(pp1 * 100).astype(np.int32) * 1000
            + np.round(pp2 * 100).astype(np.int32))
    uniq, inv = np.unique(keys, return_inverse=True)

    def _setp(k):
        aa, bb = (k // 1000) / 100.0, (k % 1000) / 100.0
        return _set_win(_game_win(aa), _game_win(bb), _tb_win(aa, 1 - bb))
    ps_vec = np.array([_setp(int(k)) for k in uniq])[inv]
    target = 3 if best_of_5 else 2
    max_sets = 5 if best_of_5 else 3
    sets1 = np.zeros(n, dtype=np.int8)
    sets2 = np.zeros(n, dtype=np.int8)
    for _ in range(max_sets):
        live = (sets1 < target) & (sets2 < target)
        if not live.any():
            break
        draw = rng.random(n) < ps_vec
        sets1 = sets1 + (live & draw)
        sets2 = sets2 + (live & ~draw)
    wins1 = int((sets1 >= target).sum())
    straight = int(((sets1 >= target) & (sets2 == 0)).sum() + ((sets2 >= target) & (sets1 == 0)).sum())
    return {"sims": int(n), "p1_wins": wins1, "p2_wins": int(n - wins1),
            "p1_pct": round(100.0 * wins1 / n, 1),
            "straight_sets_pct": round(100.0 * straight / n, 1),
            "p1_hold": round(100 * h1, 1), "p2_hold": round(100 * h2, 1),
            "sutr_anchored": sutr_anchored, "c_anchored": c_anchored,
            "surface_fallback": surface_fallback,
            "best_of_5": bool(best_of_5)}


def train():
    """Refit LR+XGB on every priced two-sided match through today; save artifacts.
    Feature construction mirrors _tennis_model_a_build.py exactly (walk-forward validated
    there; this refit is for SERVING, not for new validation claims)."""
    import time
    from sklearn.linear_model import LogisticRegression
    import xgboost as xgb
    ns = {}
    src = open(os.path.join(_here, "_tennis_model_a_build.py"), encoding="utf-8").read()
    body = src.split("from sklearn.linear_model")[0]
    exec(compile(body, "_tennis_model_a_build.py", "exec"), ns)  # noqa: S102 -- our own file
    core = ns["core"]
    FC = list(ns["feats"].keys())
    assert FC == FEATURES, f"feature drift: {FC} vs {FEATURES}"
    X, y = core[FC].fillna(0), core["won"]
    lr = LogisticRegression(max_iter=2000, C=0.5).fit(X, y)
    bst = xgb.XGBClassifier(n_estimators=300, max_depth=4, learning_rate=0.05,
                            subsample=0.9, colsample_bytree=0.8, n_jobs=8,
                            eval_metric="logloss").fit(X, y)
    os.makedirs(os.path.dirname(ARTIFACT), exist_ok=True)
    joblib.dump({"lr": lr, "xgb": bst, "features": FEATURES,
                 "trained_at": time.strftime("%Y-%m-%d"), "n_train": int(len(core)),
                 "validation": "display-only: market AUC .71-.73 vs model .66-.68 all 3 test "
                               "years; betting model edges -10.6..-12.0% (see build script)"},
                ARTIFACT)
    print(f"saved {ARTIFACT} (n={len(core)})")


if __name__ == "__main__":
    train()
