"""TENNIS MODEL G -- build + walk-forward validation (2026-10-12, user spec: "literally
just the 52 week stats compared with the amount of games taken into account and the
opponent ranks they're playing").

So G is deliberately NARROW. It is the nine 52-week figures the card already prints --
win%, 1st/2nd serve points won, service games won, return 1st/2nd, return games won,
serve- and return-pressure -- and nothing else. No last-10 block, no season block, no H2H,
no odds-performance, no market. Model C already has all of that; G exists to find out what
the stat line is worth once two things that have always been ignored are handled properly:

  1. HOW MANY GAMES IT RESTS ON. A 70% hold off four matches and a 70% hold off forty are
     not the same claim. Every rate is shrunk toward the tour mean by its OWN denominator
     (service games for hold%, return games for break%, pressure POINTS for the dials,
     matches for the per-match percentages) with an empirical-Bayes k estimated from the
     variance components -- so the shrinkage strength is measured, not chosen.

  2. WHO PRODUCED IT. A 70% hold against the top 50 is not a 70% hold against #600. Each
     past match's stat is discounted by what that opponent RANK normally concedes.

(2) is the real content of G, and it is a known gap: see the c52 note in
project_c_over_market_favs_fade -- C's 52w stats are raw, unadjusted for who was across
the net. The two earlier opponent-quality studies (_avg_opp_rank_bt, _better_competition_bt)
both tested schedule strength as a STANDALONE BET and both found it fully priced. Neither
ever used it to correct a stat, which is what happens here.

LEAKAGE DISCIPLINE
  * Every window is the prior 365 days on THIS surface, strictly before the match (shift(1)
    inside the player/surface group), exactly as the C build does it.
  * The opponent-rank discount curve and the shrinkage constants are fit ONCE on 2015-2023
    and then frozen. The walk-forward test years (2024/25/26) never touch their estimation.
  * The rank-difficulty curve is fit as a TWO-WAY additive model (player-surface effect +
    opponent-rank-bin effect), alternating means. Regressing a stat on opponent rank
    directly would be confounded -- good players mostly play good opponents, so the pooled
    slope would partly measure who-plays-whom rather than difficulty.

Honest harness, same as C: walk-forward by year, logloss/AUC against the raw market on the
same rows, then flat-1u ROI. A raw-stat control runs alongside -- identical pipeline,
shrinkage and all, minus the opponent adjustment -- because that is the only way to see
what the adjustment is actually worth. Writes model_artifacts/tennis_model_g.joblib.
"""
import time
import numpy as np
import pandas as pd

t0 = time.time()


def say(*a):
    print("[%6.1fs]" % (time.time() - t0), *a, flush=True)


P = "data_cache/tennisratio/all_match_logs.parquet"
df = pd.read_parquet(P)
df["surface"] = df["surface"].astype(str).str.title()
df["date"] = pd.to_datetime(df["date"], errors="coerce")
NUM = ("player_odd", "rival_odd", "rival_rank", "first_serve_points", "second_serve_points",
       "return_1st_serve_points", "return_2nd_serve_points", "serve_pressure_all",
       "serve_pressure_won", "return_pressure_all", "return_pressure_won")
for c in NUM:
    df[c] = pd.to_numeric(df[c], errors="coerce")
# The source has a handful of poisoned percentages -- 4 infinite second_serve_points and 4
# infinite return_2nd_serve_points out of 615k, plus a few above 100 or below 0. That is
# 0.0007% of rows, and on the first run it silently killed TWO of the nine stats: a single
# inf makes the mean and the variance over 336k matches inf, so sv2 and r2 came out with
# k=nan and a tour mean of 0.000 and contributed nothing. Percentages are bounded, so
# anything outside [0, 100] is bad data, not an extreme player.
PCT = ("first_serve_points", "second_serve_points", "return_1st_serve_points",
       "return_2nd_serve_points")
for c in PCT:
    df[c] = df[c].replace([np.inf, -np.inf], np.nan).where(df[c].between(0, 100))
for col, pre in (("service_games_won", "sg"), ("return_games_won", "rg")):
    parts = df[col].astype(str).str.extract(r"^(\d+)/(\d+)$")
    df[pre + "_w"] = pd.to_numeric(parts[0], errors="coerce")
    df[pre + "_a"] = pd.to_numeric(parts[1], errors="coerce")
df = df[df["date"].notna()].reset_index(drop=True)
df["won"] = (df["result"] == "Win").astype(int)
df["logr"] = np.log(df["rival_rank"].clip(1, 2000))
GM = pd.read_parquet("data_cache/_slug_gender.parquet")["g"].to_dict()
df["G"] = df["player_slug"].astype(str).map(GM).fillna("?")
say("%d rows parsed  (M %d / W %d / unknown %d)" % (
    len(df), (df.G == "M").sum(), (df.G == "W").sum(), (df.G == "?").sum()))

# ---------------------------------------------------------------------------
# THE NINE 52-WEEK STATS. Each entry is (name, per-match numerator, per-match denominator).
# A denominator of None means the source already gives a percentage per match, so the
# sample size is one match -- those shrink on MATCH count. The rest are true ratios and
# shrink on the games or points actually played, which is the honest sample size.
# ---------------------------------------------------------------------------
STATS = [
    ("win",  "won",                      None),
    ("sv1",  "first_serve_points",       None),
    ("sv2",  "second_serve_points",      None),
    ("r1",   "return_1st_serve_points",  None),
    ("r2",   "return_2nd_serve_points",  None),
    ("sgw",  "sg_w",                     "sg_a"),
    ("rgw",  "rg_w",                     "rg_a"),
    ("svp",  "serve_pressure_won",       "serve_pressure_all"),
    ("rtp",  "return_pressure_won",      "return_pressure_all"),
]
for nm, num, den in STATS:
    if den is None:
        r = df[num].astype(float)
        df["rate_" + nm] = r if nm == "win" else r / 100.0
        df["den_" + nm] = np.where(df["rate_" + nm].notna(), 1.0, np.nan)
    else:
        d = df[den].astype(float).replace(0, np.nan)
        df["rate_" + nm] = df[num].astype(float) / d
        df["den_" + nm] = np.where(df["rate_" + nm].notna(), d, np.nan)

# ---------------------------------------------------------------------------
# (2) OPPONENT-RANK DIFFICULTY, two-way additive, frozen on 2015-2023.
# ---------------------------------------------------------------------------
NB = 12
fitmask = df["date"].dt.year.between(2015, 2023) & df["G"].isin(["M", "W"])
edges = np.quantile(df.loc[fitmask, "logr"].dropna(), np.linspace(0, 1, NB + 1))
edges = np.unique(edges)
edges[0], edges[-1] = -np.inf, np.inf
df["rbin"] = pd.cut(df["logr"], bins=edges, labels=False)
df["punit"] = df["player_slug"].astype(str) + "|" + df["surface"].astype(str)
NBINS = int(len(edges) - 1)

OPP_EFF = {}       # (gender, stat) -> array of per-rank-bin effects; + = that band concedes more
for gd in ("M", "W"):
    sub = df[fitmask & (df.G == gd)]
    for nm, _, _ in STATS:
        s = sub[["punit", "rbin", "rate_" + nm]].dropna()
        if len(s) < 5000:
            continue
        y = s["rate_" + nm].to_numpy(float)
        pu, rb = s["punit"].to_numpy(), s["rbin"].to_numpy(int)
        wb = np.bincount(rb, minlength=NBINS).astype(float)
        eff_o = np.zeros(NBINS)
        for _ in range(4):
            ep = pd.Series(y - eff_o[rb]).groupby(pu).transform("mean").to_numpy()
            eo = pd.Series(y - ep).groupby(rb).mean()
            eff_o = np.array([float(eo.get(b, 0.0)) for b in range(NBINS)])
            eff_o -= np.average(eff_o, weights=np.maximum(wb, 1e-9))
        OPP_EFF[(gd, nm)] = eff_o
say("opponent-rank discount curves fit on %d matches (2015-23), %d bins" % (int(fitmask.sum()), NBINS))
for nm in ("sgw", "rgw"):
    say("   M %s discount by rank bin (toughest -> easiest): %s"
        % (nm, " ".join("%+.3f" % v for v in OPP_EFF[("M", nm)])))

for nm, _, _ in STATS:
    eff = np.zeros(len(df))
    for gd in ("M", "W"):
        if (gd, nm) not in OPP_EFF:
            continue
        sel = ((df.G == gd) & df["rbin"].notna()).to_numpy()
        eff[sel] = OPP_EFF[(gd, nm)][df.loc[sel, "rbin"].to_numpy(int)]
    df["adj_" + nm] = df["rate_" + nm] - eff

# ---------------------------------------------------------------------------
# 52-WEEK WINDOW ON THIS SURFACE, strictly prior. Weighted by each stat's own denominator,
# so hold% over the window is total service games won / total service games played -- not
# an average of per-match percentages, which would let a three-game walkover count as much
# as a five-setter. Same treatment the card's 52w line uses.
# ---------------------------------------------------------------------------
df = df.sort_values(["punit", "date"], kind="stable").reset_index(drop=True)
for nm, _, _ in STATS:
    df["wnum_" + nm] = df["adj_" + nm] * df["den_" + nm]
    df["rnum_" + nm] = df["rate_" + nm] * df["den_" + nm]
    df["dsum_" + nm] = df["den_" + nm]
SUMS = sum([["wnum_" + n, "rnum_" + n, "dsum_" + n] for n, _, _ in STATS], [])
g = df.groupby("punit", sort=False)
roll = g.rolling("365D", on="date")[SUMS].sum().reset_index(drop=True)
roll["w_n"] = g.rolling("365D", on="date")["won"].count().reset_index(drop=True)
roll["w_logr"] = g.rolling("365D", on="date")["logr"].mean().reset_index(drop=True)
roll = roll.groupby(df["punit"].to_numpy()).shift(1)          # strictly prior
df = pd.concat([df.drop(columns=SUMS), roll], axis=1)
say("52w windows built")

# ---------------------------------------------------------------------------
# (1) SHRINKAGE BY SAMPLE SIZE. Empirical Bayes: k = within-player sampling variance over
# between-player variance, both measured on the frozen 2015-23 block, per gender and per
# stat. k is the denominator at which the raw figure and the tour mean get equal weight, so
# it reads directly as "how many games before I believe this number".
# ---------------------------------------------------------------------------
KS, PRIOR = {}, {}
for gd in ("M", "W"):
    sub = df[fitmask & (df.G == gd)]
    for nm, _, _ in STATS:
        obs, den = sub["adj_" + nm], sub["den_" + nm]
        PRIOR[(gd, nm)] = float(np.nansum(obs * den) / np.nansum(den))
        pm = (obs * den).groupby(sub["punit"]).sum() / den.groupby(sub["punit"]).sum()
        pd_ = den.groupby(sub["punit"]).sum()
        keep = pd_ >= 10
        pm, pd_ = pm[keep], pd_[keep]
        sig2 = float(np.nanvar(obs - obs.groupby(sub["punit"]).transform("mean")))
        tau2 = float(np.nanvar(pm) - sig2 * float(np.nanmean(1.0 / pd_)))
        KS[(gd, nm)] = float(np.clip(sig2 / max(tau2, 1e-9), 1.0, 1e5))
say("shrinkage constants k = sample size at which the raw figure earns half the weight:")
for nm, _, _ in STATS:
    say("   %-4s  M k=%8.1f  W k=%8.1f   tour mean M %.3f / W %.3f"
        % (nm, KS[("M", nm)], KS[("W", nm)], PRIOR[("M", nm)], PRIOR[("W", nm)]))

kmap = {nm: df["G"].map({gd: KS[(gd, nm)] for gd in ("M", "W")}).astype(float) for nm, _, _ in STATS}
pmap = {nm: df["G"].map({gd: PRIOR[(gd, nm)] for gd in ("M", "W")}).astype(float) for nm, _, _ in STATS}
for nm, _, _ in STATS:
    dsum, k, pr = df["dsum_" + nm], kmap[nm], pmap[nm]
    df["g_" + nm] = (df["wnum_" + nm] + k * pr) / (dsum + k)        # opponent-adjusted + shrunk
    df["graw_" + nm] = (df["rnum_" + nm] + k * pr) / (dsum + k)     # shrunk only (the control)
    df["n_" + nm] = dsum
say("shrunk + adjusted stats done")

# ---------------------------------------------------------------------------
# PAIR THE TWO SIDES (one row per match) and diff. Mirror join exactly as the C build.
# ---------------------------------------------------------------------------
SN = [n for n, _, _ in STATS]
CARRY = (["g_" + n for n in SN] + ["graw_" + n for n in SN] + ["n_" + n for n in SN]
         + ["w_n", "w_logr", "rival_rank"])
mirror = df[["player_slug", "rival_slugname", "date"] + CARRY].copy()
mirror.columns = ["rival_slugname", "player_slug", "date"] + ["o_" + c for c in CARRY]
m = df.merge(mirror, on=["player_slug", "rival_slugname", "date"], how="inner")
m = m[m["player_slug"] < m["rival_slugname"].astype(str)]
m = m.drop_duplicates(["player_slug", "rival_slugname", "date"]).reset_index(drop=True)
ip1 = 1 / m["player_odd"].where(m["player_odd"] > 1.005)
ip2 = 1 / m["rival_odd"].where(m["rival_odd"] > 1.005)
m["mkt"] = ip1 / (ip1 + ip2)
say("two-sided rows: %d" % len(m))

feats, rawf = {}, {}
for nm in SN:
    feats["d_" + nm] = m["g_" + nm] - m["o_g_" + nm]
    rawf["d_" + nm] = m["graw_" + nm] - m["o_graw_" + nm]
    shared = np.log1p(m["n_" + nm]) - np.log1p(m["o_n_" + nm])   # whose figure rests on more
    feats["dn_" + nm] = shared
    rawf["dn_" + nm] = shared
for k_, v_ in (("d_matches", np.log1p(m["w_n"]) - np.log1p(m["o_w_n"])),
               ("f_nmin", np.log1p(np.minimum(m["w_n"], m["o_w_n"])))):
    feats[k_] = v_
    rawf[k_] = v_
feats["d_faced"] = m["o_w_logr"] - m["w_logr"]        # + = p1 has faced the tougher schedule

FC, RC = list(feats.keys()), list(rawf.keys())
X = pd.DataFrame({k: pd.to_numeric(v, errors="coerce") for k, v in feats.items()})
Xr = pd.DataFrame({k: pd.to_numeric(v, errors="coerce") for k, v in rawf.items()})
keep = m["mkt"].notna() & X.notna().sum(axis=1).ge(14) & m["G"].isin(["M", "W"])
core = m.loc[keep, ["date", "won", "mkt", "player_odd", "rival_odd", "G", "w_n", "o_w_n"]].join(X).reset_index(drop=True)
core_r = Xr[keep].reset_index(drop=True)
say("G core: %d rows, %d features (control %d)" % (len(core), len(FC), len(RC)))

from sklearn.linear_model import LogisticRegression          # noqa: E402
from sklearn.metrics import log_loss, roc_auc_score          # noqa: E402
import xgboost as xgb                                        # noqa: E402
import joblib                                                # noqa: E402


def lg(p):
    p = np.clip(np.asarray(p, dtype=float), 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p))


def fitpair(Xtr, ytr, Xte):
    lr = LogisticRegression(max_iter=3000, C=0.5).fit(Xtr, ytr)
    bst = xgb.XGBClassifier(n_estimators=300, max_depth=4, learning_rate=0.05, subsample=0.9,
                            colsample_bytree=0.8, n_jobs=8, eval_metric="logloss").fit(Xtr, ytr)
    return 0.5 * (lr.predict_proba(Xte)[:, 1] + bst.predict_proba(Xte)[:, 1]), lr, bst


rows = []
for yr in (2024, 2025, 2026):
    itr = (core["date"].dt.year < yr).to_numpy()
    ite = (core["date"].dt.year == yr).to_numpy()
    if ite.sum() < 500:
        continue
    tr, te = core[itr], core[ite]
    Xtr, Xte = tr[FC].fillna(0), te[FC].fillna(0)
    ytr, yte = tr["won"], te["won"]
    p_g, _, _ = fitpair(Xtr, ytr, Xte)
    p_raw, _, _ = fitpair(core_r[itr].fillna(0), ytr, core_r[ite].fillna(0))
    lrm = LogisticRegression(max_iter=3000, C=0.5).fit(np.column_stack([lg(tr["mkt"]), Xtr]), ytr)
    p_ms = lrm.predict_proba(np.column_stack([lg(te["mkt"]), Xte]))[:, 1]
    print("\n== %d (n=%d) ==" % (yr, int(ite.sum())), flush=True)
    for nm, p in (("G stats-only", p_g), ("G raw (no opp-adj)", p_raw),
                  ("G mkt-aware", p_ms), ("raw market", te["mkt"].to_numpy())):
        ll, au = log_loss(yte, p), roc_auc_score(yte, p)
        ac = float(((np.asarray(p) >= .5) == yte.to_numpy()).mean())
        print("  %-19s logloss %.4f  auc %.4f  acc %.3f" % (nm, ll, au, ac), flush=True)
        rows.append({"yr": yr, "model": nm, "n": int(ite.sum()), "logloss": ll, "auc": au, "acc": ac})
    for nm, p in (("G", p_g), ("G mkt-aware", p_ms)):
        pnl = []
        mk, yv = te["mkt"].to_numpy(), yte.to_numpy()
        for sel, odd, wn in (((p - mk) >= 0.05, te["player_odd"].to_numpy(), yv),
                             (((1 - p) - (1 - mk)) >= 0.05, te["rival_odd"].to_numpy(), 1 - yv)):
            for s_, o_, w_ in zip(sel, odd, wn):
                if s_ and o_ and o_ > 1.005:
                    pnl.append((o_ - 1) if w_ else -1.0)
        if pnl:
            print("  %-19s bet@5pt n=%-5d flat ROI %+.1f%%" % (nm, len(pnl), 100 * np.mean(pnl)), flush=True)

pd.DataFrame(rows).to_csv("_model_g_walkforward.csv", index=False)
core.to_parquet("data_cache/_model_g_core.parquet")
Xall, yall = core[FC].fillna(0), core["won"]
_, lr, bst = fitpair(Xall, yall, Xall.head(5))
lrm = LogisticRegression(max_iter=3000, C=0.5).fit(np.column_stack([lg(core["mkt"]), Xall]), yall)
joblib.dump({"lr": lr, "xgb": bst, "lr_ms": lrm, "features": FC, "stats": SN,
             "opp_eff": OPP_EFF, "k": KS, "prior": PRIOR, "bin_edges": edges,
             "trained_at": time.strftime("%Y-%m-%d"), "n_train": int(len(core))},
            "model_artifacts/tennis_model_g.joblib")
imp = sorted(zip(FC, bst.feature_importances_), key=lambda x: -x[1])[:12]
say("saved tennis_model_g.joblib | top: " + str([(a, round(float(b), 3)) for a, b in imp]))
