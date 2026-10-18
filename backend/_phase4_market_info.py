"""PHASE 4: does ANY existing head carry predictive information beyond the market?

Design (all evaluation strictly chronological, expanding-window; nothing fitted ever sees its
test rows; the Oct-31 lane checkpoint is not used to tune or select anything here):

  population   Phase-2 clean settled rows (BAD_ROW_FLAGS enforced), both odds present.
  market prob  proportional de-vig i1/(i1+i2) of the frozen (closing) book prices -- the same
               construction every lane uses. Limitations stated in the report: single-book
               (mostly FanDuel), proportional allocation does not correct favourite-longshot
               bias, and the overround median is 6.5%.
  M0 baseline  y ~ a + b*logit(p_mkt)          (recalibrated market)
  M1 per head  y ~ a + b*logit(p_mkt) + c*logit(p_head)   -- the incremental-information test
  M1 per feat  y ~ a + b*logit(p_mkt) + c*z(feature)      -- non-market row features
  folds        first 40%% of rows (by start time) are the minimum train window; the remaining
               60%% is split into 5 sequential test folds; models refit on everything earlier.
  metric       paired per-row OOS log-loss and Brier deltas (M0 - M1; positive = head adds),
               with a paired t. ~19 correlated tests run, so the bar for "credible" is t >= 3;
               2..3 is "suggestive"; below 2 is noise. Heads are labelled accordingly.
  calibration  (step 4) C75 anatomy: predicted-vs-actual by market-disagreement bucket, side,
               band, gender, level, surface; walk-forward logistic AND isotonic recalibration
               of C75 alone vs the market on the same OOS rows.
  segments     (step 5) pre-specified only: gender, level, surface, side, odds band,
               disagreement tertile -- evaluated on the SAME stored OOS per-row deltas (no
               per-segment refits, no new filters).
  betting      (step 6) computed only for a head whose OOS delta clears t >= 2, at executable
               prices, labelled exploratory.
Outputs: printed report blocks + data_cache/phase4_heads.csv + phase4_oos_rows.csv.
"""
import math
import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression

import tennis_log as T

HEADS = ["model_a", "model_b", "model_c", "model_d", "mc_c75", "mc_cutr", "model_g",
         "model_g2", "model_x", "mc2", "mc3", "mc5", "mc6"]


def _num(r, c):
    v = r.get(c)
    return float(v) if v is not None and pd.notna(v) else np.nan


log = pd.read_parquet(T.LOG_PATH)
bad = pd.Series(False, index=log.index)
for c in T.BAD_ROW_FLAGS:
    if c in log.columns:
        bad |= log[c].fillna(False).astype(bool)
ok = (~bad & log["p1_odds"].notna() & log["p2_odds"].notna()
      & log["settled"].fillna(False).astype(bool) & log["p1_won"].notna()
      & ~log["void"].fillna(False).astype(bool))
df = log[ok].copy()


def dec(a):
    a = float(a)
    return 1.0 + (a / 100.0 if a > 0 else 100.0 / -a)


df["d1"] = df["p1_odds"].map(dec)
df["d2"] = df["p2_odds"].map(dec)
df["mkt"] = (1 / df["d1"]) / (1 / df["d1"] + 1 / df["d2"])
df["y"] = df["p1_won"].astype(bool).astype(int)
df["lg"] = df["league"].astype(str)
df["gender"] = np.where(df["lg"].str.contains("wta|itf_women"), "W", "M")
df["tour"] = np.where(df["lg"].isin(["atp", "wta"]), "TOUR",
                      np.where(df["lg"] == "atp_challenger", "CHALL", "ITF"))
df["surf"] = df["surface"].astype(str)
df = df.sort_values("start_time_utc").reset_index(drop=True)
print("eligible settled rows: %d  (%s .. %s)" % (len(df), df["date"].astype(str).min()[:10], df["date"].astype(str).max()[:10]))

# non-market row features (player-1 oriented)
df["f_s52_serve"] = df.get("s52_sgw_p1") - df.get("s52_sgw_p2")
df["f_s52_return"] = df.get("s52_rgw_p1") - df.get("s52_rgw_p2")
df["f_pure_form"] = df.get("pf_edge_p1")
df["f_utr_edge"] = df.get("utr_edge_p1")
df["f_utr_mom"] = df.get("utr_mom_p1")
df["f_c_serve_gap"] = df.get("c_sp_diff_p1")
df["f_c_return_gap"] = df.get("c_rp_diff_p1")
FEAT_COLS = ["f_s52_serve", "f_s52_return", "f_pure_form", "f_utr_edge", "f_utr_mom",
             "f_c_serve_gap", "f_c_return_gap"]


def lgt(p):
    p = np.clip(np.asarray(p, dtype=float), 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p))


def ll(p, y):
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return -(y * np.log(p) + (1 - y) * np.log(1 - p))


def folds_for(n, min_frac=0.40, k=5):
    start = int(n * min_frac)
    edges = np.linspace(start, n, k + 1).astype(int)
    return [(edges[i], edges[i + 1]) for i in range(k) if edges[i + 1] > edges[i]]


def wf_eval(sub, xcols):
    """Expanding-window: fit M0 (mkt only) and M1 (mkt + xcols) on earlier rows, predict fold.
    Returns per-row OOS arrays: p0, p1 and index."""
    sub = sub.reset_index(drop=True)
    n = len(sub)
    p0 = np.full(n, np.nan)
    p1 = np.full(n, np.nan)
    coefs = []
    for a, b in folds_for(n):
        tr, te = sub.iloc[:a], sub.iloc[a:b]
        X0tr, X0te = lgt(tr["mkt"])[:, None], lgt(te["mkt"])[:, None]
        m0 = LogisticRegression(C=1.0, max_iter=1000).fit(X0tr, tr["y"])
        p0[a:b] = m0.predict_proba(X0te)[:, 1]
        X1tr = np.column_stack([lgt(tr["mkt"])] + [tr[c].to_numpy(dtype=float) for c in xcols])
        X1te = np.column_stack([lgt(te["mkt"])] + [te[c].to_numpy(dtype=float) for c in xcols])
        m1 = LogisticRegression(C=1.0, max_iter=1000).fit(X1tr, tr["y"])
        p1[a:b] = m1.predict_proba(X1te)[:, 1]
        coefs.append(m1.coef_[0][1:])
    m = ~np.isnan(p0)
    return sub[m], p0[m], p1[m], np.mean(coefs, axis=0)


def auc(ps, ys):
    o = np.argsort(ps)
    r = np.empty(len(ps))
    r[o] = np.arange(1, len(ps) + 1)
    # average ties
    s = pd.Series(ps)
    r = s.rank().to_numpy()
    pos = ys == 1
    if pos.sum() == 0 or (~pos).sum() == 0:
        return float("nan")
    return (r[pos].sum() - pos.sum() * (pos.sum() + 1) / 2) / (pos.sum() * (~pos).sum())


print("")
print("=" * 112)
print("STEP 2+3: INCREMENTAL INFORMATION OVER THE MARKET -- walk-forward, paired per-row OOS deltas")
print("=" * 112)
print("   %-14s %5s | head alone AUC/Brier | mkt OOS ll | d(logloss) x1000  t | d(Brier) x1000 | coef | verdict"
      % ("signal", "n_oos"))
rows_out, oos_store = [], {}
for h in HEADS + FEAT_COLS:
    if h in FEAT_COLS:
        m = df[h].notna()
        sub = df[m].copy()
        if len(sub) < 300:
            print("   %-14s n=%d too few rows" % (h, len(sub)))
            continue
        mu, sd = sub[h].mean(), sub[h].std() or 1.0
        sub["_x"] = (sub[h] - mu) / sd
        xc = ["_x"]
        alone_auc = alone_br = float("nan")
    else:
        c, rc = h + "_p1", h + "_recon"
        if c not in df.columns:
            continue
        m = df[c].notna()
        if rc in df.columns:
            m &= ~df[rc].fillna(False).astype(bool)
        sub = df[m].copy()
        if len(sub) < 300:
            print("   %-14s n=%d too few forward rows for 5-fold walk-forward -- reported, low power" % (h, len(sub)))
            if len(sub) < 150:
                continue
        sub["_x"] = lgt(sub[c])
        xc = ["_x"]
        alone_auc = auc(sub[c].to_numpy(dtype=float), sub["y"].to_numpy())
        alone_br = float(((sub[c] - sub["y"]) ** 2).mean())
    te, p0, p1, coef = wf_eval(sub, xc)
    y = te["y"].to_numpy()
    d_ll = ll(p0, y) - ll(p1, y)
    d_br = (p0 - y) ** 2 - (p1 - y) ** 2
    t = d_ll.mean() / (d_ll.std(ddof=1) / math.sqrt(len(d_ll))) if d_ll.std() > 0 else 0.0
    verdict = ("CREDIBLE" if t >= 3 else "suggestive" if t >= 2 else
               "none" if t > -2 else "NEGATIVE (hurts)")
    print("   %-14s %5d |      %.3f / %.4f    |   %.4f   | %+9.2f  %+5.2f | %+10.2f    | %+5.2f | %s"
          % (h, len(te), alone_auc, alone_br, ll(p0, y).mean(), 1000 * d_ll.mean(), t,
             1000 * d_br.mean(), coef[0], verdict))
    rows_out.append(dict(signal=h, n_oos=len(te), alone_auc=alone_auc, alone_brier=alone_br,
                         mkt_oos_logloss=ll(p0, y).mean(), d_logloss_x1000=1000 * d_ll.mean(),
                         t_logloss=t, d_brier_x1000=1000 * d_br.mean(), coef=coef[0], verdict=verdict))
    oos_store[h] = (te, p0, p1)

# simple regularized combo of the four signal families on common rows
combo_heads = ["mc2_p1", "model_g2_p1", "mc_c75_p1", "model_a_p1"]
m = pd.Series(True, index=df.index)
for c in combo_heads:
    m &= df[c].notna()
for rc in ("mc2_recon", "model_g2_recon"):
    if rc in df.columns:
        m &= ~df[rc].fillna(False).astype(bool)
sub = df[m].copy()
for c in combo_heads:
    sub["_x_" + c] = lgt(sub[c])
te, p0, p1, coef = wf_eval(sub, ["_x_" + c for c in combo_heads])
y = te["y"].to_numpy()
d_ll = ll(p0, y) - ll(p1, y)
t = d_ll.mean() / (d_ll.std(ddof=1) / math.sqrt(len(d_ll)))
print("   %-14s %5d |          --          |   %.4f   | %+9.2f  %+5.2f | %+10.2f    | %s | %s"
      % ("4-family combo", len(te), ll(p0, y).mean(), 1000 * d_ll.mean(), t,
         1000 * ((p0 - y) ** 2 - (p1 - y) ** 2).mean(),
         "/".join("%+.2f" % c for c in coef), "CREDIBLE" if t >= 3 else "suggestive" if t >= 2 else "none"))
pd.DataFrame(rows_out).to_csv("data_cache/phase4_heads.csv", index=False)

print("")
print("=" * 112)
print("STEP 4: C75 CALIBRATION ANATOMY -- where does 56%% -> 39%% come from?")
print("=" * 112)
c = "mc_c75_p1"
sub = df[df[c].notna()].copy()
sub["p_dog"] = np.where(sub["mkt"] < 0.5, sub[c], 1 - sub[c])      # prob on the market DOG
sub["mk_dog"] = np.minimum(sub["mkt"], 1 - sub["mkt"])
sub["dogwon"] = (sub["y"] == 1) == (sub["mkt"] < 0.5)
sub["disag"] = sub["p_dog"] - sub["mk_dog"]
print("   by DISAGREEMENT with the market (c75's dog prob minus the market's):")
print("   %-18s %5s %9s %9s %9s %9s" % ("bucket", "n", "c75 pred", "mkt pred", "ACTUAL", "gap c75"))
for lo, hi, lab in ((-1, -0.05, "c75 5pt+ UNDER"), (-0.05, 0.0, "0..5 under"), (0.0, 0.05, "0..5 over"),
                    (0.05, 0.10, "5..10 over"), (0.10, 0.20, "10..20 over"), (0.20, 1, "20pt+ over")):
    b = sub[(sub["disag"] > lo) & (sub["disag"] <= hi)]
    if len(b) < 25:
        continue
    print("   %-18s %5d %8.1f%% %8.1f%% %8.1f%% %+8.1fpt"
          % (lab, len(b), 100 * b["p_dog"].mean(), 100 * b["mk_dog"].mean(),
             100 * b["dogwon"].mean(), 100 * (b["p_dog"].mean() - b["dogwon"].mean())))
print("")
print("   same cut within segments (c75 overconfidence in pt, where n>=40): ")
over = sub[sub["disag"] >= 0.05]
for col, vals in (("gender", ["M", "W"]), ("tour", ["TOUR", "CHALL", "ITF"]), ("surf", ["Hard", "Clay"])):
    for v in vals:
        b = over[over[col] == v]
        if len(b) < 40:
            continue
        print("      %-6s %-6s n=%-4d pred %5.1f%% actual %5.1f%% gap %+5.1fpt"
              % (col, v, len(b), 100 * b["p_dog"].mean(), 100 * b["dogwon"].mean(),
                 100 * (b["p_dog"].mean() - b["dogwon"].mean())))
b = over[(over["dodds"] >= 100) & (over["dodds"] <= 200)] if "dodds" in over.columns else None
over["dodds_am"] = np.where(over["mkt"] < 0.5, over["p1_odds"], over["p2_odds"])
for lo, hi, lab in ((100, 150, "+100..+150"), (150, 200, "+151..+200"), (200, 300, "+201..+300"), (300, 9999, "+300+")):
    b = over[(over["dodds_am"] > lo - 0.001) & (over["dodds_am"] <= hi)]
    if len(b) < 30:
        continue
    print("      band %-10s n=%-4d pred %5.1f%% actual %5.1f%% gap %+5.1fpt"
          % (lab, len(b), 100 * b["p_dog"].mean(), 100 * b["dogwon"].mean(),
             100 * (b["p_dog"].mean() - b["dogwon"].mean())))

print("")
print("   walk-forward recalibration of C75 ALONE vs the market, same OOS rows:")
sub2 = sub.reset_index(drop=True)
n = len(sub2)
pl = np.full(n, np.nan)
pi = np.full(n, np.nan)
for a, b2 in folds_for(n):
    tr, te2 = sub2.iloc[:a], sub2.iloc[a:b2]
    mlog = LogisticRegression(C=1.0, max_iter=1000).fit(lgt(tr[c])[:, None], tr["y"])
    pl[a:b2] = mlog.predict_proba(lgt(te2[c])[:, None])[:, 1]
    iso = IsotonicRegression(out_of_bounds="clip").fit(tr[c], tr["y"])
    pi[a:b2] = np.clip(iso.predict(te2[c]), 1e-4, 1 - 1e-4)
mm = ~np.isnan(pl)
yy = sub2["y"].to_numpy()[mm]
for nm, pp in (("raw c75", sub2[c].to_numpy()[mm]), ("logistic recal", pl[mm]),
               ("isotonic recal", pi[mm]), ("market", sub2["mkt"].to_numpy()[mm])):
    print("      %-16s Brier %.4f  logloss %.4f  AUC %.4f"
          % (nm, ((pp - yy) ** 2).mean(), ll(pp, yy).mean(), auc(pp, yy)))

print("")
print("=" * 112)
print("STEP 5: PRE-SPECIFIED SEGMENTS -- OOS incremental d(logloss) x1000 (mkt+head vs mkt), paired t")
print("=" * 112)
oos_rows = []
for h in ("mc2", "model_g2", "mc_c75", "model_d"):
    if h not in oos_store:
        continue
    te, p0, p1 = oos_store[h]
    y = te["y"].to_numpy()
    d = ll(p0, y) - ll(p1, y)
    te = te.assign(_d=d, _p0=p0, _p1=p1)
    oos_rows.append(te.assign(head=h)[["head", "date", "lg", "gender", "tour", "surf", "mkt", "y", "_p0", "_p1", "_d"]])
    print("   %s:" % h)
    segs = [("gender", "M"), ("gender", "W"), ("tour", "TOUR"), ("tour", "CHALL"), ("tour", "ITF"),
            ("surf", "Hard"), ("surf", "Clay")]
    parts = []
    for col, v in segs:
        b = te[te[col] == v]
        if len(b) < 40:
            continue
        tt = b["_d"].mean() / (b["_d"].std(ddof=1) / math.sqrt(len(b))) if b["_d"].std() > 0 else 0
        parts.append("%s=%s %+0.2f(t%+.1f,n%d)" % (col[:1], v[:5], 1000 * b["_d"].mean(), tt, len(b)))
    print("      " + " | ".join(parts))
pd.concat(oos_rows).to_csv("data_cache/phase4_oos_rows.csv", index=False)
print("")
print("OOS per-row deltas saved: data_cache/phase4_oos_rows.csv")
