"""DOES ADDING AS-OF H2H TO MC2 IMPROVE IT? WALK-FORWARD (2026-10-15)

User: "run it" -- the direct test, after the residual test said H2H is priced.

WHAT IS BUILT. MC2's real architecture, re-run here so H2H can be switched on and off inside it:

    base layers (market-blind) : surface Elo  +  point-level Markov
    learned blend              : logistic stack of the two logits, fit on TRAIN years only
    final layer                : XGB on the RESIDUAL against the no-vig close (won - imp)

The Markov layer uses the ADDITIVE point-probability stand-in p_match(pa_pt, pb_pt) -- the same
stand-in stage 4 itself uses to fit the blend on training years -- rather than re-fitting the
XGBoost point model per year. That keeps both of MC2's genuine base signals and its genuine
blend/residual architecture while making the run cheap; the earlier attempt at the full chain was
OOM-killed on this box. The comparison is WITH-H2H against WITHOUT-H2H inside the identical
pipeline, so the stand-in cancels: it cannot favour either arm.

H2H IS ADDED IN BOTH PLACES IT COULD GO -- the blend inputs and the residual layer -- and the
features are the user's own formulation, not just raw share:

    h2h_n        prior meetings (as-of)
    h2h_share    prior win share, centred
    h2h_recent   exponentially recency-weighted win share, 365-day half-life  <- "recent h2hs"
    h2h_days     days since the last meeting (capped)
    h2h_marg     average games margin in prior meetings                        <- "beat them easily"
    h2h_rmarg    recency-weighted games margin
    h2h_sn/_ss   prior meetings and win share ON THIS SURFACE

AS-OF THROUGHOUT: cumcount for counts, shifted cumsums for wins and margin, shift(1) for the last
meeting's date. Nothing can see its own result or any later one. An H2H feature built on full
history is the easiest way there is to leak a result into a backtest, so this is the part to be
strict about.

JUDGED ON: AUC and Brier on held-out years (2025, 2026), each trained only on earlier years, for
Market / Blend / Final in both arms, plus a PAIRED bootstrap on the Final AUC difference so the
comparison accounts for both arms being scored on identical rows.

Run: ./venv/bin/python _h2h_in_mc2_walkforward.py
"""
import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score

# reuse MC2's own helpers (p_game / p_tb / p_set / p_match / lg) and its feature table
src = open("_mc2_stage4_ensemble.py", encoding="utf-8").read()
ns = {}
exec(compile(src.split("NODES = ")[0], "mc2_stage4_head", "exec"), ns)  # noqa: S102
F, p_match, lg = ns["F"], ns["p_match"], ns["lg"]
print("feature rows: %d" % len(F), flush=True)

F = F.copy()
F["date"] = pd.to_datetime(F["date"], errors="coerce")
F = F[F["date"].notna() & F["a"].notna() & F["b"].notna() & F["won"].notna()]
F = F.sort_values("date", kind="stable").reset_index(drop=True)

# ---------------------------------------------------------------- as-of H2H features
import re


def _margin(s):
    """(games for a) - (games for b); the score is written a-first."""
    if not isinstance(s, str) or not s:
        return np.nan
    d = n = 0
    for x, y in re.findall(r"(\d+)\s*[-:]\s*(\d+)", s):
        x, y = int(x), int(y)
        if x > 30 or y > 30:          # tie-break point score, not games
            continue
        d += x - y
        n += 1
    return float(d) if n else np.nan


A = F["a"].astype(str).to_numpy()
B = F["b"].astype(str).to_numpy()
first_is_a = A < B
F["pair"] = np.where(first_is_a, A, B) + "\x00" + np.where(first_is_a, B, A)
F["pair_s"] = F["pair"] + "\x00" + F["surf"].astype(str)
won_a = F["won"].astype(bool).to_numpy()
mg_a = F["score"].map(_margin).to_numpy(float) if "score" in F.columns else np.full(len(F), np.nan)

wf = pd.Series(np.where(first_is_a, won_a, ~won_a).astype(float), index=F.index)
mf = pd.Series(np.where(first_is_a, mg_a, -mg_a), index=F.index).fillna(0.0)
HL = 365.0                                     # half-life for the recency weighting
tnum = F["date"].astype("int64").to_numpy() / 86_400_000_000_000.0   # days

gp = F.groupby("pair", sort=False)
n_prior = gp.cumcount().to_numpy()
prior_w_first = (wf.groupby(F["pair"], sort=False).cumsum() - wf).to_numpy()
prior_m_first = (mf.groupby(F["pair"], sort=False).cumsum() - mf).to_numpy()
prev_t = gp["date"].shift(1)
days_since = (F["date"] - prev_t).dt.days.to_numpy(float)

# recency-weighted prior win share / margin, computed per pair (small groups, so a loop is fine)
rw = np.zeros(len(F))
rm_ = np.zeros(len(F))
rwn = np.zeros(len(F))
for _, idx in gp.indices.items():
    if len(idx) < 2:
        continue
    idx = np.sort(idx)
    for k in range(1, len(idx)):
        i = idx[k]
        j = idx[:k]
        w = 0.5 ** ((tnum[i] - tnum[j]) / HL)
        sw = w.sum()
        if sw <= 0:
            continue
        rwn[i] = sw
        rw[i] = float((w * wf.to_numpy()[j]).sum() / sw)
        rm_[i] = float((w * mf.to_numpy()[j]).sum() / sw)

gs = F.groupby("pair_s", sort=False)
sn = gs.cumcount().to_numpy()
prior_w_first_s = (wf.groupby(F["pair_s"], sort=False).cumsum() - wf).to_numpy()

has = n_prior > 0
to_a = lambda v: np.where(first_is_a, v, -v)
H = pd.DataFrame(index=F.index)
H["h2h_n"] = np.minimum(n_prior, 10)
H["h2h_share"] = np.where(has, np.where(first_is_a, prior_w_first, n_prior - prior_w_first)
                          / np.maximum(n_prior, 1) - 0.5, 0.0)
H["h2h_recent"] = np.where(rwn > 0, np.where(first_is_a, rw, 1 - rw) - 0.5, 0.0)
H["h2h_days"] = np.where(has, np.minimum(np.nan_to_num(days_since, nan=1825.0), 1825.0), 1825.0)
H["h2h_marg"] = np.where(has, to_a(prior_m_first) / np.maximum(n_prior, 1), 0.0)
H["h2h_rmarg"] = np.where(rwn > 0, to_a(rm_), 0.0)
H["h2h_sn"] = np.minimum(sn, 6)
H["h2h_ss"] = np.where(sn > 0, np.where(first_is_a, prior_w_first_s, sn - prior_w_first_s)
                       / np.maximum(sn, 1) - 0.5, 0.0)
HCOLS = list(H.columns)
F = pd.concat([F, H], axis=1)
print("with >=1 prior meeting: %d (%.0f%%)   recency-weighted present: %d"
      % (has.sum(), 100 * has.mean(), int((rwn > 0).sum())), flush=True)

# ---------------------------------------------------------------- the Markov stand-in
pa = pd.to_numeric(F["pa_pt"], errors="coerce").to_numpy(float)
pb = pd.to_numeric(F["pb_pt"], errors="coerce").to_numpy(float)
good = ~np.isnan(pa) & ~np.isnan(pb)
pmk = np.full(len(F), np.nan)
pmk[good] = [p_match(round(float(min(max(x, 0.40), 0.85)), 2),
                     round(float(min(max(y, 0.40), 0.85)), 2))
             for x, y in zip(pa[good], pb[good])]
F["p_mkv"] = pmk
F = F[F["imp"].notna() & F["p_elo"].notna() & F["p_mkv"].notna()
      & (F["nS_a"] >= 8) & (F["nS_b"] >= 8)].reset_index(drop=True)
print("usable priced rows: %d   years %s"
      % (len(F), sorted(F["year"].unique().tolist())), flush=True)


def res_feats(df, with_h2h):
    X = pd.DataFrame({
        "imp": df["imp"].to_numpy(float),
        "d_blend": lg(df["p_blend"]) - lg(df["imp"]),
        "d_elo": lg(df["p_elo"]) - lg(df["imp"]),
        "d_mkv": lg(df["p_mkv"]) - lg(df["imp"]),
        "wom": df["wom"].to_numpy(float), "lvlg": df["lvlg"].to_numpy(float),
        "sgm": 0.10 / np.sqrt(np.maximum(df["nS_a"].to_numpy(float), 4))
               + 0.10 / np.sqrt(np.maximum(df["nS_b"].to_numpy(float), 4)),
        "dog": (df["imp"].to_numpy(float) < 0.5).astype(int)}, index=df.index)
    if with_h2h:
        for c in HCOLS:
            X[c] = df[c].to_numpy(float)
    return X


def run(with_h2h):
    """MC2's blend + residual layer, walk-forward, with or without the H2H block."""
    out = {}
    blended = {}
    for Y in (2024, 2025, 2026):
        tr, te = F[F["year"] < Y], F[F["year"] == Y].copy()
        if len(tr) < 5000 or not len(te):
            continue
        cols = [lg(tr["p_elo"]), lg(tr["p_mkv"])]
        colt = [lg(te["p_elo"]), lg(te["p_mkv"])]
        if with_h2h:                       # H2H also offered to the BLEND, not only the residual
            for c in HCOLS:
                cols.append(tr[c].to_numpy(float))
                colt.append(te[c].to_numpy(float))
        stk = LogisticRegression(max_iter=3000).fit(np.column_stack(cols), tr["won"])
        te["p_blend"] = stk.predict_proba(np.column_stack(colt))[:, 1]
        blended[Y] = te
    P = pd.concat(blended.values())
    for Y in (2025, 2026):
        tr, te = P[P["year"] < Y], P[P["year"] == Y].copy()
        if not len(te) or len(tr) < 2000:
            continue
        rm = xgb.XGBRegressor(n_estimators=250, max_depth=3, learning_rate=0.04,
                              subsample=0.9, colsample_bytree=0.9, n_jobs=4)
        rm.fit(res_feats(tr, with_h2h), tr["won"] - tr["imp"])
        adj = np.clip(rm.predict(res_feats(te, with_h2h)), -0.25, 0.25)
        te["p_final"] = np.clip(te["imp"] + adj, 0.02, 0.98)
        out[Y] = te
    return out


BAR = "=" * 100
print("\nrunning WITHOUT h2h ...", flush=True)
A0 = run(False)
print("running WITH h2h ...", flush=True)
A1 = run(True)

print("\n" + BAR)
print("WALK-FORWARD, HELD-OUT YEARS   (trained only on earlier years)")
print(BAR)
print("   %-6s %-22s %8s %8s %8s" % ("year", "model", "AUC", "Brier", "LogLoss"))
for Y in (2025, 2026):
    if Y not in A0 or Y not in A1:
        continue
    t0, t1 = A0[Y], A1[Y]
    y = t0["won"].astype(int).to_numpy()
    rows = [("Market", t0["imp"]), ("Blend  (no h2h)", t0["p_blend"]),
            ("Blend  (+ h2h)", t1["p_blend"]), ("Final  (no h2h)", t0["p_final"]),
            ("Final  (+ h2h)", t1["p_final"])]
    for nm, p in rows:
        p = np.clip(np.asarray(p, float), 1e-6, 1 - 1e-6)
        print("   %-6d %-22s %8.4f %8.4f %8.4f"
              % (Y, nm, roc_auc_score(y, p), brier_score_loss(y, p), log_loss(y, p)))
    print()

# ---- paired bootstrap on the Final AUC difference ----
print(BAR)
print("PAIRED BOOTSTRAP on the Final AUC difference (+h2h minus no-h2h), same rows both arms")
print(BAR)
rng = np.random.default_rng(11)
for Y in (2025, 2026):
    if Y not in A0 or Y not in A1:
        continue
    y = A0[Y]["won"].astype(int).to_numpy()
    p0 = np.clip(A0[Y]["p_final"].to_numpy(float), 1e-6, 1 - 1e-6)
    p1 = np.clip(A1[Y]["p_final"].to_numpy(float), 1e-6, 1 - 1e-6)
    n = len(y)
    d = np.empty(500)
    for i in range(500):
        k = rng.integers(0, n, n)
        yy = y[k]
        d[i] = (np.nan if yy.all() or not yy.any()
                else roc_auc_score(yy, p1[k]) - roc_auc_score(yy, p0[k]))
    lo, hi = np.nanpercentile(d, [2.5, 97.5])
    print("   %d   diff %+.4f   95%% [%+.4f, %+.4f]   P(h2h better) %.0f%%   n=%d"
          % (Y, roc_auc_score(y, p1) - roc_auc_score(y, p0), lo, hi,
             100 * np.nanmean(d > 0), n))

# ---- what the blend actually learned about H2H ----
print("\n" + BAR)
print("DID THE BLEND EVEN USE IT?  logistic coefficients in the +h2h arm (2026 fit)")
print(BAR)
tr = F[F["year"] < 2026]
cols = [lg(tr["p_elo"]), lg(tr["p_mkv"])] + [tr[c].to_numpy(float) for c in HCOLS]
stk = LogisticRegression(max_iter=3000).fit(np.column_stack(cols), tr["won"])
for nm, c in zip(["lg(p_elo)", "lg(p_mkv)"] + HCOLS, stk.coef_[0]):
    print("   %-14s %+9.4f" % (nm, c))
print("\n" + BAR)
print("READ: if the +h2h AUC/Brier sit on top of the no-h2h ones and the bootstrap interval")
print("straddles zero, H2H adds nothing to MC2 -- which is what the residual test predicted.")
print(BAR)
