"""CAN A DIFFERENT WEIGHTING BEAT THE MARKET? (2026-10-11, user: "Is there anyway we can weigh
it differently to beat the market")

What is already settled, so this does not repeat it:
  * the best LINEAR reweighting of the stat line, with the price as a fixed baseline, beat the
    market in 3 of 9 years (men) by ~0.0005 log-loss -- i.e. nothing
  * the best NON-LINEAR reweighting is Model C, which DOES beat the market on accuracy in
    backtest (66.8% vs 63.4%, +3.4pt) and still returns -0.3%, because the accuracy lands on
    favourites where it cannot clear the vig
  * the one weighting that pays is Model P: offset on the market, trained on the +100..+200
    dog band, optimising PROFIT rather than accuracy

So the open question is whether P's recipe, applied to the FULL stat line rather than P's
smaller feature set, does better. Three variants, all walk-forward (train on prior years only):

    1. ACCURACY, everything      offset logistic on all stats, all matches -- the control
    2. ACCURACY, dogs only       same, but fitted only where the money is
    3. PROFIT, dogs only         same features, but the loss is -EV in units staked rather
                                 than log-loss, so the fit optimises the thing we care about

Each is then bet at a range of EV thresholds and scored at real odds. If none of them clears
the vig on out-of-sample years, "reweight the stat line" is closed as a route.
"""
import numpy as np
import pandas as pd

import tennis_archive as TA

MINM = 8


def frac(s):
    p = s.astype(str).str.extract(r"^(\d+)/(\d+)$")
    return pd.to_numeric(p[0], errors="coerce"), pd.to_numeric(p[1], errors="coerce")


COLS = ["surface", "service_games_won", "return_games_won", "double_faults", "aces",
        "first_serve_accuracy", "first_serve_points", "second_serve_points",
        "return_1st_serve_points", "return_2nd_serve_points",
        "breakpoints_saved_count", "breakpoints_converted_count",
        "rival_rank", "tournament_level"]
df = TA.load(columns=COLS, priced_only=True, require_mirror=True, verbose=False)
df["surf"] = df["surface"].astype(str).str.title().replace({"I.Hard": "Hard", "Carpet": "Hard"})
df["won"] = df["result"].eq("Win").astype(int)
df["sg_w"], df["sg_a"] = frac(df["service_games_won"])
df["rg_w"], df["rg_a"] = frac(df["return_games_won"])
df["bps_w"], df["bps_a"] = frac(df["breakpoints_saved_count"])
df["bpc_w"], df["bpc_a"] = frac(df["breakpoints_converted_count"])
for c in ("double_faults", "aces", "first_serve_accuracy", "first_serve_points",
          "second_serve_points", "return_1st_serve_points", "return_2nd_serve_points",
          "rival_rank"):
    df[c] = pd.to_numeric(df[c], errors="coerce")
df = df.sort_values(["player_slug", "surf", "date"], kind="stable").reset_index(drop=True)
g = df.groupby(["player_slug", "surf"], sort=False)
for c in ("sg_w", "sg_a", "rg_w", "rg_a", "bps_w", "bps_a", "bpc_w", "bpc_a",
          "double_faults", "aces", "won"):
    df["s_" + c] = (g[c].shift(1).groupby([df.player_slug, df.surf])
                    .rolling(40, min_periods=MINM).sum().reset_index(level=[0, 1], drop=True))
for c in ("first_serve_accuracy", "first_serve_points", "second_serve_points",
          "return_1st_serve_points", "return_2nd_serve_points", "rival_rank"):
    df["m_" + c] = (g[c].shift(1).groupby([df.player_slug, df.surf])
                    .rolling(40, min_periods=MINM).mean().reset_index(level=[0, 1], drop=True))
df["n_prev"] = (g["won"].shift(1).groupby([df.player_slug, df.surf])
                .rolling(40, min_periods=MINM).count().reset_index(level=[0, 1], drop=True))
for K, tag in ((10, "l10"), (5, "l5")):
    df["w_" + tag] = (g["won"].shift(1).groupby([df.player_slug, df.surf])
                      .rolling(K, min_periods=3).mean().reset_index(level=[0, 1], drop=True))

sg, rg = df.s_sg_a.replace(0, np.nan), df.s_rg_a.replace(0, np.nan)
F = pd.DataFrame(index=df.index)
F["hold"] = 100 * df.s_sg_w / sg
F["brk"] = 100 * df.s_rg_w / rg
F["sv1acc"] = df.m_first_serve_accuracy
F["sv1"] = df.m_first_serve_points
F["sv2"] = df.m_second_serve_points
F["r1"] = df.m_return_1st_serve_points
F["r2"] = df.m_return_2nd_serve_points
F["ace"] = df.s_aces / sg
F["df"] = -(df.s_double_faults / sg)
F["bpsv"] = 100 * df.s_bps_w / df.s_bps_a.replace(0, np.nan)
F["bpcv"] = 100 * df.s_bpc_w / df.s_bpc_a.replace(0, np.nan)
F["w52"] = 100 * df.s_won / df.n_prev.replace(0, np.nan)
F["wl10"] = 100 * df.w_l10
F["wl5"] = 100 * df.w_l5
F["orank"] = -df.m_rival_rank
FE = list(F.columns)
df = pd.concat([df, F], axis=1)

key = ["date", "player_slug", "rival_slugname"]
opp = df[key + FE].rename(columns={"player_slug": "rival_slugname",
                                   "rival_slugname": "player_slug",
                                   **{f: "o_" + f for f in FE}})
M = df.merge(opp, on=key, how="inner")
i1 = 1 / M.player_odd.where(M.player_odd > 1.005)
i2 = 1 / M.rival_odd.where(M.rival_odd > 1.005)
M["mkt"] = i1 / (i1 + i2)
M = M[M.mkt.notna()].copy()
M["pair"] = [tuple(sorted((a, str(b)))) for a, b in zip(M.player_slug.astype(str),
                                                        M.rival_slugname)]
M = M.drop_duplicates(["date", "pair"]).reset_index(drop=True)
for f in FE:
    M["d_" + f] = M[f] - M["o_" + f]
M = M[M[["d_" + f for f in FE]].notna().all(axis=1)].copy()
M["yr"] = M.date.dt.year
print("complete matches: %d   %s..%s" % (len(M), M.date.min().date(), M.date.max().date()))

X_ALL = M[["d_" + f for f in FE]].to_numpy(float)
mu, sd = X_ALL.mean(0), X_ALL.std(0, ddof=0)
X_ALL = (X_ALL - mu) / sd
y = M.won.to_numpy(float)
mk = np.clip(M.mkt.to_numpy(float), 1e-4, 1 - 1e-4)
off = np.log(mk / (1 - mk))
dec = M.player_odd.to_numpy(float)
yrs = M.yr.to_numpy()
dog = mk < 0.5


def fit_logloss(Xtr, ytr, otr, lam=3.0, iters=4000, lr=0.1):
    w = np.zeros(Xtr.shape[1])
    for _ in range(iters):
        p = 1 / (1 + np.exp(-(otr + Xtr @ w)))
        w -= lr * (Xtr.T @ (p - ytr) + lam * w) / len(ytr)
    return w


def fit_profit(Xtr, ytr, otr, dtr, lam=3.0, iters=4000, lr=0.05):
    """Maximise expected PROFIT, not likelihood.

    Stake a soft amount s = sigmoid(model_logit - market_logit), i.e. bet more the further the
    model sits above the price, and maximise mean(s * pnl). That is the quantity the account
    actually experiences; log-loss is only a proxy for it and -- as the whole session has shown
    -- a model can win the proxy and lose the money.
    """
    w = np.zeros(Xtr.shape[1])
    pnl_win, pnl_los = dtr - 1.0, -1.0
    for _ in range(iters):
        z = Xtr @ w                      # model logit minus market logit
        sgm = 1 / (1 + np.exp(-z))       # stake in [0,1]
        pnl = np.where(ytr > 0.5, pnl_win, pnl_los)
        # d/dw of mean(s*pnl) = mean(pnl * s(1-s) * x)
        grad = -(Xtr * (pnl * sgm * (1 - sgm))[:, None]).mean(0) + lam * w / len(ytr)
        w -= lr * grad
    return w


def evaluate(name, fitter, dogs_only):
    rows = []
    for ytest in sorted(set(yrs)):
        tr = yrs < ytest
        te = yrs == ytest
        if dogs_only:
            tr = tr & dog
        if tr.sum() < 3000 or (te & dog).sum() < 300:
            continue
        if fitter is fit_profit:
            w = fitter(X_ALL[tr], y[tr], off[tr], dec[tr])
        else:
            w = fitter(X_ALL[tr], y[tr], off[tr])
        p = 1 / (1 + np.exp(-(off[te] + X_ALL[te] @ w)))
        ev = p * dec[te] - 1.0
        # p and ev are aligned to the test slice, so the dog mask must be too
        sub_dog = dog[te]
        pnl_te = np.where(y[te] > 0.5, dec[te] - 1.0, -1.0)
        for thr in (0.0, 0.05, 0.10):
            sel = sub_dog & (ev >= thr)
            if sel.sum() < 50:
                continue
            rows.append((ytest, thr, int(sel.sum()), 100 * pnl_te[sel].mean()))
    print("\n   %s" % name)
    if not rows:
        print("      no year had enough bets")
        return
    R = pd.DataFrame(rows, columns=["yr", "thr", "n", "roi"])
    for thr, grp in R.groupby("thr"):
        tot_n = grp.n.sum()
        wavg = (grp.roi * grp.n).sum() / tot_n
        yrs_pos = (grp.roi > 0).sum()
        print("      EV>=%-5.2f  pooled ROI %+6.1f%%  over %5d dog bets  |  positive in %d of %d years  |  %s"
              % (thr, wavg, tot_n, yrs_pos, len(grp),
                 " ".join("%d:%+.0f%%" % (r.yr, r.roi) for r in grp.itertuples())))


print("\n" + "=" * 112)
print("CAN A REWEIGHTING BEAT THE MARKET? walk-forward, bet the DOG when the model says +EV")
print("=" * 112)
evaluate("1. ACCURACY fit, trained on EVERYTHING (the control)", fit_logloss, False)
evaluate("2. ACCURACY fit, trained on DOGS only", fit_logloss, True)
evaluate("3. PROFIT fit, trained on DOGS only (Model P's idea, full stat line)",
         fit_profit, True)
print("\n   baseline for comparison: backing every +100..+200 dog is about -7%,")
print("   and Model P's own recipe is +14% (men) / +21% (women) walk-forward.")
