"""OPP1 v3.5 — chronological walk-forward, fold-local preprocessing, M0-M3, paired log-loss
contrasts, K-cluster bootstrap, design effect / effective n, stopping + extension (blinded),
permutation integrity check, calibration-slope gates.

Registered machinery (v3.5 §4): expanding MONTHLY walk-forward, minimum train = first 6 months;
symmetric league fixed effects in ALL of M0-M3; per-fold z-scores / imputation / logistic
recalibration fitted on each fold's training window only; L2 C=1.0.

Gated: H1 mean paired dll(M0-M2) > 0, H2 mean dll(M1-M3) > 0 (dll in log-LOSS terms, positive =
candidate better). Dev t >= 3 floor +2.0e-3; tiers t >= 2 same sign floor +1.0e-3; calibration
slopes 0.9-1.1 (M2 gates H1, M3 gates H2, measured on the evaluated rows of that stage);
permutation null is an additional NECESSARY integrity condition, never sufficient.

PURE FUNCTIONS over passed-in frames; no store/log access exists in this module. The bootstrap
and permutation RNG seeds are REQUIRED explicit arguments — the registered spec does not fix
them, and this module refuses to default them silently (reported owner decision).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

# ---- registered constants (v3.5 §4) --------------------------------------------------------
L2_C = 1.0
MIN_TRAIN_MONTHS = 6
B_BOOT = 2000
B_PERM = 200
DEV_T, DEV_FLOOR = 3.0, 2.0e-3
TIER_T, TIER_FLOOR = 2.0, 1.0e-3
CAL_LO, CAL_HI = 0.9, 1.1
EFF_MIN_DEV = 8000
LEAGUES = ("atp", "atp_challenger", "itf_men")   # dummies: challenger, itf (atp = reference)
EPS = 1e-12


class DataIntegrityAbort(RuntimeError):
    """D2: undefined variance / zero iid denominator -> stop, documented review; never
    contrast-dropping, contrast-selection, or continued accrual."""


# ---------------------------------------------------------------- model matrix + fold fitting
def _league_dummies(df):
    return np.column_stack([(df["league"] == "atp_challenger").astype(float).values,
                            (df["league"] == "itf_men").astype(float).values])


def _matrix(df, cols, mu=None, sd=None):
    """Impute to training mean, z-score by training std (fold-local), append league FE raw."""
    X = df[cols].astype(float).values
    if mu is None:
        mu = np.nanmean(X, axis=0)
        mu = np.where(np.isfinite(mu), mu, 0.0)
        sd = np.nanstd(X, axis=0)
        sd = np.where((sd > 0) & np.isfinite(sd), sd, 1.0)
    X = np.where(np.isfinite(X), X, mu)
    X = (X - mu) / sd
    return np.column_stack([X, _league_dummies(df)]), mu, sd


def _fit_predict(train, test, cols):
    Xtr, mu, sd = _matrix(train, cols)
    Xte, _, _ = _matrix(test, cols, mu, sd)
    y = train["y"].astype(int).values
    m = LogisticRegression(C=L2_C, max_iter=2000).fit(Xtr, y)
    lo_tr = m.decision_function(Xtr).reshape(-1, 1)
    recal = LogisticRegression(C=1e6, max_iter=2000).fit(lo_tr, y)   # fold-local Platt
    lo_te = m.decision_function(Xte).reshape(-1, 1)
    return recal.predict_proba(lo_te)[:, 1]


MODEL_COLS = {
    "M0": ["logit_fair"],
    "M1": ["logit_fair", "logit_mc2", "logit_mc2_ind"],
}


def model_cols(e_cols):
    c = dict(MODEL_COLS)
    c["M2"] = c["M0"] + list(e_cols)
    c["M3"] = c["M1"] + list(e_cols)
    return c


def walk_forward(df, e_cols):
    """Expanding monthly walk-forward. df: start (tz-aware), y, league, K, evaluated (bool),
    feature columns. Training uses ALL chronologically prior rows (thinned rows included, Q2);
    ONLY evaluated rows are scored. Returns (scored_df with p_M0..p_M3, fold_log)."""
    df = df.sort_values("start").reset_index(drop=True)
    month = df["start"].dt.tz_convert("UTC").dt.strftime("%Y-%m")
    months = sorted(month.unique())
    cols = model_cols(e_cols)
    scored, fold_log = [], []
    for m in months[MIN_TRAIN_MONTHS:]:
        wall = pd.Timestamp(m + "-01", tz="UTC")
        train = df[df["start"] < wall]
        test = df[(month == m) & df["evaluated"]]
        if not len(test) or not len(train) or train["y"].nunique() < 2:
            continue
        assert train["start"].max() < wall, "chronological fold wall violated"
        rows = test.copy()
        for name, c in cols.items():
            rows["p_%s" % name] = _fit_predict(train, test, c)
        scored.append(rows)
        fold_log.append({"month": m, "wall": wall, "n_train": len(train),
                         "n_test": len(test), "max_train_start": train["start"].max()})
    out = pd.concat(scored, ignore_index=True) if scored else pd.DataFrame()
    return out, fold_log


# ---------------------------------------------------------------- contrasts, bootstrap, DE
def _loss(y, p):
    p = np.clip(np.asarray(p, float), 1e-12, 1 - 1e-12)
    y = np.asarray(y, float)
    return -(y * np.log(p) + (1 - y) * np.log(1 - p))


def contrasts(scored):
    """Paired per-match dll, positive = candidate better. H1: M0 vs M2, H2: M1 vs M3."""
    y = scored["y"].values
    return {"H1": _loss(y, scored["p_M0"]) - _loss(y, scored["p_M2"]),
            "H2": _loss(y, scored["p_M1"]) - _loss(y, scored["p_M3"])}


def cluster_bootstrap(d, keys, seed, B=B_BOOT):
    """Studentized mean via cluster (key K) bootstrap. Returns dict(mean, t, V_clust, V_iid)."""
    d = np.asarray(d, float)
    idx: dict = {}
    for i, k in enumerate(keys):
        idx.setdefault(k, []).append(i)
    uniq = sorted(idx)
    groups = {k: d[np.asarray(idx[k])] for k in uniq}
    rng = np.random.default_rng(seed)
    means = np.empty(B)
    for b in range(B):
        pick = rng.choice(len(uniq), size=len(uniq), replace=True)
        samp = np.concatenate([groups[uniq[i]] for i in pick])
        means[b] = samp.mean()
    v_clust = float(means.var(ddof=1))
    n = len(d)
    s2 = float(d.var(ddof=1))
    if not np.isfinite(s2) or s2 == 0 or n < 2:
        raise DataIntegrityAbort("iid variance undefined or zero (D2) — documented review")
    v_iid = s2 / n
    if not np.isfinite(v_clust) or v_clust <= 0:
        raise DataIntegrityAbort("cluster variance undefined (D2) — documented review")
    t = float(d.mean() / np.sqrt(v_clust))
    # Registered 95% PERCENTILE CI (v3.5 §4): the percentile method applied to the cluster-
    # bootstrap distribution of resampled MEANS of the gated statistic (mean paired dll).
    ci95 = (float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5)))
    return {"mean": float(d.mean()), "t": t, "V_clust": v_clust, "V_iid": v_iid, "n": n,
            "ci95": ci95}


def variances_only(stat: dict) -> tuple:
    """D6 blinding helper: strip a cluster_bootstrap result to (V_clust, V_iid) so downstream
    extension decisions can never see means, t, or CIs."""
    return float(stat["V_clust"]), float(stat["V_iid"])


def governing_de(v_clust_h1: float, v_iid_h1: float,
                 v_clust_h2: float, v_iid_h2: float) -> float:
    """DE = max(DE_H1, DE_H2), floored at 1 (D1/D2). Takes VARIANCES ONLY — no result dicts."""
    for v in (v_clust_h1, v_iid_h1, v_clust_h2, v_iid_h2):
        if not np.isfinite(v) or v <= 0:
            raise DataIntegrityAbort("variance undefined or non-positive (D2) — documented review")
    return max(1.0, v_clust_h1 / v_iid_h1, v_clust_h2 / v_iid_h2)


def decide_extension(v_clust_h1: float, v_iid_h1: float, v_clust_h2: float, v_iid_h2: float,
                     n_evaluated: int):
    """BLINDED extension decision (B1 + D6): accepts ONLY the four variances and the evaluated
    count — full bootstrap result dicts (which carry means/t/CIs) cannot be passed. Exposes
    only variances, governing DE, effective n, and the verdict."""
    de = governing_de(v_clust_h1, v_iid_h1, v_clust_h2, v_iid_h2)
    eff = n_evaluated / de
    return {"V_clust_H1": v_clust_h1, "V_iid_H1": v_iid_h1,
            "V_clust_H2": v_clust_h2, "V_iid_H2": v_iid_h2,
            "governing_DE": de, "effective_n": eff,
            "extend": bool(eff < EFF_MIN_DEV),
            "rule": "extend by whole ISO-weeks until effective n >= %d" % EFF_MIN_DEV}


# ---------------------------------------------------------------- gates + integrity checks
def calibration_slope(y, p):
    lo = np.log(np.clip(p, 1e-12, 1 - 1e-12) / (1 - np.clip(p, 1e-12, 1 - 1e-12)))
    m = LogisticRegression(C=1e6, max_iter=2000).fit(lo.reshape(-1, 1), np.asarray(y, int))
    return float(m.coef_[0][0])


def dev_gate(stat, slope):
    return bool(stat["t"] >= DEV_T and stat["mean"] >= DEV_FLOOR and CAL_LO <= slope <= CAL_HI)


def tier_gate(stat, slope):
    return bool(stat["t"] >= TIER_T and stat["mean"] >= TIER_FLOOR and CAL_LO <= slope <= CAL_HI)


def permutation_check(df, e_cols, true_means, seed, B=B_PERM):
    """200-permutation label-shuffle null — an additional NECESSARY integrity condition, never
    sufficient and never a substitute for H1/H2. Pass = null mean within +/-2 null-SE of zero
    AND the true mean above the null's 99th percentile, per hypothesis."""
    rng = np.random.default_rng(seed)
    nulls = {"H1": [], "H2": []}
    for _ in range(B):
        shuf = df.copy()
        shuf["y"] = rng.permutation(shuf["y"].values)
        scored, _ = walk_forward(shuf, e_cols)
        if not len(scored):
            continue
        c = contrasts(scored)
        nulls["H1"].append(c["H1"].mean())
        nulls["H2"].append(c["H2"].mean())
    out = {}
    for h in ("H1", "H2"):
        a = np.asarray(nulls[h])
        se = a.std(ddof=1) / np.sqrt(len(a))
        out[h] = {"null_mean": float(a.mean()), "null_se": float(se),
                  "null_p99": float(np.percentile(a, 99)),
                  "pass": bool(abs(a.mean()) <= 2 * se and true_means[h] > np.percentile(a, 99))}
    return out
