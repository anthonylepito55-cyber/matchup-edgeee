"""TENNIS MODEL G2 -- build + walk-forward validation (2026-10-12, user: "Make a g2 right under
G that takes g and then just add in last 10 game stats as well with who they won and how they
performed and who they lost to and make sure u see if any walkovers to not count them").

G2 = every Model G feature, untouched, PLUS a last-10 block:
  * the record over the last 10, and how many of them survived the walkover filter
  * WHO THEY BEAT     -- average rank of the opponents they won against, and their best win
  * WHO THEY LOST TO  -- average rank of the opponents they lost to
  * WHO THEY PLAYED   -- average rank of the whole 10, so "beat good players" can be separated
                         from "played good players"
  * HOW THEY PERFORMED -- games-won share across the 10, hold% and break% over the same games,
                         and how competitive the LOSSES were (a straight-sets loss reads ~0.30,
                         a three-tiebreak loss ~0.48)

WALKOVERS AND RETIREMENTS ARE EXCLUDED (the user's explicit instruction, and _walkover_audit.py
says why it matters). TennisRatio does not flag them -- "ret" appears zero times in 615k scores
-- so they are detected from the shape of the match:
  * no parseable score at all (WO / BYE / DEF / empty): 53 rows
  * the winner never reached a winning set count, i.e. 2 sets in a best-of-3 or 3 in a
    best-of-5: 9,543 rows (1.55%), with scores like "4-1", "2-1", "6-4 1-1"
Those rows carry a median of 4 service games against 10 for a completed match, so inside a
10-match window one of them can put 20% of the weight on a 3-game sample. They are dropped from
the last-10 block entirely -- not down-weighted -- because a win over someone who retired is not
a win over them, which is the half of the user's instruction that is about meaning rather than
noise.

G's own 52-week half is left EXACTLY as it is, so any difference in the walk-forward is
attributable to the last-10 block and nothing else. (Whether to filter walkovers out of the
52-week window too is a separate question, measured at the end of this script.)

Honest harness, same as G: walk-forward by year, G2 against G and against the raw market on
identical rows, then flat-1u ROI. Writes model_artifacts/tennis_model_g2.joblib.
"""
import time
import numpy as np
import pandas as pd

t0 = time.time()


def say(*a):
    print("[%6.1fs]" % (time.time() - t0), *a, flush=True)


# ---- G's prep verbatim: df carries the adjusted+shrunk 52w stats, punit, logr, won ----
ns = {}
src = open("_tennis_model_g_build.py", encoding="utf-8").read()
exec(compile(src.split("from sklearn.linear_model")[0], "_g_prep", "exec"), ns)
df, SN, GFC = ns["df"], ns["SN"], ns["FC"]
say("G prep reused: %d player-match rows, %d G features" % (len(df), len(GFC)))

# ---- WALKOVER / RETIREMENT FLAG ----
_sc = df["score"].astype(str)
_pairs = _sc.str.findall(r"(\d+)-(\d+)")
df["nsets"] = _pairs.map(len)


def _sets(ps):
    a = b = 0
    for x, y in ps:
        x, y = int(x), int(y)
        if x > y:
            a += 1
        elif y > x:
            b += 1
    return a, b


_sw = _pairs.map(_sets)
df["sets_for"] = [x[0] for x in _sw]
df["sets_ag"] = [x[1] for x in _sw]
df["games_tot"] = _pairs.map(lambda ps: sum(int(x) + int(y) for x, y in ps))
_need = np.where((df["sets_for"] + df["sets_ag"]) >= 4, 3, 2)
_winsets = np.where(df["won"] == 1, df["sets_for"], df["sets_ag"])
df["walkover"] = (df["nsets"] == 0) | ((_winsets < _need) & (df["nsets"] > 0))
say("walkovers/retirements flagged: %d (%.2f%%)"
    % (int(df["walkover"].sum()), 100 * float(df["walkover"].mean())))

# ---- the LAST-10 BLOCK, over completed matches on this surface only ----
# games-won share = how dominant the match was, which is the "how did they perform" axis that a
# win/loss column cannot carry
_sga = df["sg_a"].replace(0, np.nan)
_rga = df["rg_a"].replace(0, np.nan)
df["meff"] = (df["sg_w"] + df["rg_w"]) / (df["sg_a"] + df["rg_a"]).replace(0, np.nan)
df["hold1"] = df["sg_w"] / _sga
df["brk1"] = df["rg_w"] / _rga
df["w_logr"] = np.where(df["won"] == 1, df["logr"], np.nan)      # who they BEAT
df["l_logr"] = np.where(df["won"] == 0, df["logr"], np.nan)      # who they LOST to
df["l_meff"] = np.where(df["won"] == 0, df["meff"], np.nan)      # how close the losses were

L10 = {"t10_win": ("won", "mean"), "t10_faced": ("logr", "mean"),
       "t10_beaten": ("w_logr", "mean"), "t10_bestwin": ("w_logr", "min"),
       "t10_lost": ("l_logr", "mean"), "t10_worstloss": ("l_logr", "max"),
       "t10_meff": ("meff", "mean"), "t10_losscl": ("l_meff", "mean"),
       "t10_hold": ("hold1", "mean"), "t10_brk": ("brk1", "mean")}

comp = df[~df["walkover"]].sort_values(["punit", "date"], kind="stable").copy()
gc = comp.groupby("punit", sort=False)
agg = {}
for nm, (col, how) in L10.items():
    r = gc[col].rolling(10, min_periods=3)
    agg[nm] = getattr(r, how)().reset_index(level=0, drop=True)
agg["t10_n"] = gc["won"].rolling(10, min_periods=3).count().reset_index(level=0, drop=True)
l10 = pd.DataFrame(agg)
l10["punit"] = comp["punit"].to_numpy()
l10["date"] = comp["date"].to_numpy()
l10 = l10.sort_values("date", kind="stable").reset_index(drop=True)

# merge_asof with allow_exact_matches=False: every row sees only COMPLETED matches strictly
# BEFORE its own date, so the block is as-of and cannot see the match it is describing
left = df[["punit", "date"]].copy()
left["_i"] = np.arange(len(left))
left = left.sort_values("date", kind="stable")
mg = pd.merge_asof(left, l10, on="date", by="punit", direction="backward",
                   allow_exact_matches=False)
mg = mg.sort_values("_i")
for nm in list(L10) + ["t10_n"]:
    df[nm] = mg[nm].to_numpy()
say("last-10 block built (walkovers excluded); coverage %.1f%% of rows"
    % (100 * float(df["t10_win"].notna().mean())))

# ---- pair the two sides, exactly as G does ----
T10 = list(L10) + ["t10_n"]
CARRY = (["g_" + n for n in SN] + ["n_" + n for n in SN]
         + ["w_n", "w_logr_dummy" if False else "w_logr", "wide", "rival_rank"] + T10)
CARRY = [c for c in dict.fromkeys(CARRY)]
mirror = df[["player_slug", "rival_slugname", "date"] + CARRY].copy()
mirror.columns = ["rival_slugname", "player_slug", "date"] + ["o_" + c for c in CARRY]
m = df.merge(mirror, on=["player_slug", "rival_slugname", "date"], how="inner")
m = m[m["player_slug"] < m["rival_slugname"].astype(str)]
m = m.drop_duplicates(["player_slug", "rival_slugname", "date"]).reset_index(drop=True)
ip1 = 1 / m["player_odd"].where(m["player_odd"] > 1.005)
ip2 = 1 / m["rival_odd"].where(m["rival_odd"] > 1.005)
m["mkt"] = ip1 / (ip1 + ip2)
say("two-sided rows: %d" % len(m))

# G's features, rebuilt on this frame so G and G2 are scored on identical rows
feats = {}
for nm in SN:
    feats["d_" + nm] = m["g_" + nm] - m["o_g_" + nm]
    feats["dn_" + nm] = np.log1p(m["n_" + nm]) - np.log1p(m["o_n_" + nm])
feats["d_matches"] = np.log1p(m["w_n"]) - np.log1p(m["o_w_n"])
feats["f_nmin"] = np.log1p(np.minimum(m["w_n"], m["o_w_n"]))
feats["d_faced"] = m["o_w_logr"] - m["w_logr"]
feats["f_wide"] = m["wide"].fillna(0) + m["o_wide"].fillna(0)
GCOLS = list(feats.keys())

# the last-10 additions. Rank columns are LOG RANKS, so lower = tougher: those diff as
# (opponent minus us) to keep "+ = p1 did the harder thing" consistent with the rest.
feats["d_t10_win"] = m["t10_win"] - m["o_t10_win"]
feats["d_t10_meff"] = m["t10_meff"] - m["o_t10_meff"]
feats["d_t10_hold"] = m["t10_hold"] - m["o_t10_hold"]
feats["d_t10_brk"] = m["t10_brk"] - m["o_t10_brk"]
feats["d_t10_losscl"] = m["t10_losscl"] - m["o_t10_losscl"]
feats["d_t10_faced"] = m["o_t10_faced"] - m["t10_faced"]
feats["d_t10_beaten"] = m["o_t10_beaten"] - m["t10_beaten"]
feats["d_t10_bestwin"] = m["o_t10_bestwin"] - m["t10_bestwin"]
feats["d_t10_lost"] = m["o_t10_lost"] - m["t10_lost"]
feats["d_t10_worstloss"] = m["o_t10_worstloss"] - m["t10_worstloss"]
feats["d_t10_n"] = m["t10_n"] - m["o_t10_n"]
feats["f_t10_nmin"] = np.minimum(m["t10_n"], m["o_t10_n"])
FC = list(feats.keys())
X = pd.DataFrame({k: pd.to_numeric(v, errors="coerce") for k, v in feats.items()})
keep = m["mkt"].notna() & X[GCOLS].notna().sum(axis=1).ge(14) & m["G"].isin(["M", "W"])
core = m.loc[keep, ["date", "won", "mkt", "player_odd", "rival_odd", "G"]].join(X).reset_index(drop=True)
say("G2 core: %d rows | %d features (%d from G + %d last-10)"
    % (len(core), len(FC), len(GCOLS), len(FC) - len(GCOLS)))

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
    ytr, yte = tr["won"], te["won"]
    p2, _, _ = fitpair(tr[FC].fillna(0), ytr, te[FC].fillna(0))
    p1, _, _ = fitpair(tr[GCOLS].fillna(0), ytr, te[GCOLS].fillna(0))   # G on the same rows
    lrm = LogisticRegression(max_iter=3000, C=0.5).fit(
        np.column_stack([lg(tr["mkt"]), tr[FC].fillna(0)]), ytr)
    pma = lrm.predict_proba(np.column_stack([lg(te["mkt"]), te[FC].fillna(0)]))[:, 1]
    print("\n== %d (n=%d) ==" % (yr, int(ite.sum())), flush=True)
    for nm, p in (("G2 (G + last-10)", p2), ("G (same rows)", p1),
                  ("G2 mkt-aware", pma), ("raw market", te["mkt"].to_numpy())):
        ll, au = log_loss(yte, p), roc_auc_score(yte, p)
        ac = float(((np.asarray(p) >= .5) == yte.to_numpy()).mean())
        print("  %-18s logloss %.4f  auc %.4f  acc %.3f" % (nm, ll, au, ac), flush=True)
        rows.append({"yr": yr, "model": nm, "n": int(ite.sum()), "logloss": ll, "auc": au, "acc": ac})
    for nm, p in (("G2", p2), ("G2 mkt-aware", pma)):
        pnl, mk, yv = [], te["mkt"].to_numpy(), yte.to_numpy()
        for sel, odd, wn in (((p - mk) >= 0.05, te["player_odd"].to_numpy(), yv),
                             (((1 - p) - (1 - mk)) >= 0.05, te["rival_odd"].to_numpy(), 1 - yv)):
            for s_, o_, w_ in zip(sel, odd, wn):
                if s_ and o_ and o_ > 1.005:
                    pnl.append((o_ - 1) if w_ else -1.0)
        if pnl:
            print("  %-18s bet@5pt n=%-5d flat ROI %+.1f%%" % (nm, len(pnl), 100 * np.mean(pnl)),
                  flush=True)

pd.DataFrame(rows).to_csv("_model_g2_walkforward.csv", index=False)
Xall, yall = core[FC].fillna(0), core["won"]
_, lr, bst = fitpair(Xall, yall, Xall.head(5))
lrm = LogisticRegression(max_iter=3000, C=0.5).fit(np.column_stack([lg(core["mkt"]), Xall]), yall)
gm = ns["mdl"] if "mdl" in ns else None
joblib.dump({"lr": lr, "xgb": bst, "lr_ms": lrm, "features": FC, "g_features": GCOLS,
             "stats": SN, "t10": T10,
             "opp_eff": ns["OPP_EFF"], "k": ns["KS"], "prior": ns["PRIOR"],
             "bin_edges": ns["edges"],
             "trained_at": time.strftime("%Y-%m-%d"), "n_train": int(len(core))},
            "model_artifacts/tennis_model_g2.joblib")
imp = sorted(zip(FC, bst.feature_importances_), key=lambda x: -x[1])[:14]
say("saved tennis_model_g2.joblib | top: " + str([(a, round(float(b), 3)) for a, b in imp]))

# ---- the separate question: would filtering walkovers out of G's 52-WEEK window help too? ----
say("walkover share inside a 365-day window, for context:")
print("   rows whose own match was a walkover: %.2f%%" % (100 * float(df["walkover"].mean())))
print("   median service games, walkover vs completed: %.0f vs %.0f"
      % (df.loc[df.walkover, "sg_a"].median(), df.loc[~df.walkover, "sg_a"].median()))
print("   -> a 52w window averages ~%.1f of them per 40 matches"
      % (40 * float(df["walkover"].mean())))
