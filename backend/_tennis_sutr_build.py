"""SURFACE UTR (2026-10-01, user ask): our own court-specific UTR-style rating.
Like UTR: a player's rating is a recency-weighted average of per-match performance
ratings, where each match's performance = opponent's rating +/- how the GAMES went
(games-won share), NOT just win/loss -- and opponent quality is the opponent's own
rating, never a ranking. Unlike UTR: computed PER SURFACE.

Mechanics: single chronological pass (strictly prior -> leak-free validation).
  perf = R_opp + (games_share - 0.5) * SPREAD        (SPREAD=10: 60/40 games ~ 1.0)
  R = sum(w * perf) / sum(w) over last 30 matches on surface within 365 days,
      w = 0.97^(matches ago); shrink toward 8.0 while n < 5 (provisional).
Validation: AUC of pre-match rating diff vs result, per year, vs the market."""
import numpy as np
import pandas as pd
from collections import defaultdict, deque

P = "data_cache/tennisratio/all_match_logs.parquet"
SPREAD = 10.0
BASE = 8.0

df = pd.read_parquet(P)
df["surface"] = df["surface"].astype(str).str.title()
df["date"] = pd.to_datetime(df["date"], errors="coerce")
for col, pre in (("service_games_won", "sg"), ("return_games_won", "rg")):
    parts = df[col].astype(str).str.extract(r"^(\d+)/(\d+)$")
    df[pre + "_w"] = pd.to_numeric(parts[0], errors="coerce")
    df[pre + "_a"] = pd.to_numeric(parts[1], errors="coerce")
df["won"] = (df["result"] == "Win").astype(int)
df["meff"] = (df["sg_w"] + df["rg_w"]) / (df["sg_a"] + df["rg_a"]).replace(0, np.nan)
for c in ("player_odd", "rival_odd"):
    df[c] = pd.to_numeric(df[c], errors="coerce")
df = df[df["date"].notna() & df["rival_slugname"].notna() & (df["rival_slugname"] != "")]
two = df[df["player_slug"] < df["rival_slugname"].astype(str)].copy()
two = two.drop_duplicates(["player_slug", "rival_slugname", "date"])
two = two.sort_values("date", kind="stable").reset_index(drop=True)
ip1 = 1 / two["player_odd"].where(two["player_odd"] > 1.005)
ip2 = 1 / two["rival_odd"].where(two["rival_odd"] > 1.005)
two["mkt"] = ip1 / (ip1 + ip2)
print(f"matches: {len(two)}", flush=True)

# maxlen 60 so the adaptive window below can reach back far enough for thin players.
hist = defaultdict(lambda: deque(maxlen=60))  # (slug, surface) -> deque[(date, perf)]
# Adaptive lookback (2026-10-05, user: "if a game has a thin rating, grab more games to make
# the UTR have more games logged"). We already ingest full career, so rather than scrape, we
# reach back into it ONLY when a player is thin on a surface: use the tight 365d recency
# window normally, but keep adding older matches (up to CAP_DAYS) until at least MIN_N are
# counted. Well-sampled players are unchanged (they hit MIN_N inside 365d); thin players get
# their real games. A/B validated 2026-10-05: standalone AUC up (2025 .6777->.6825, 2026
# .6840->.6867), market+sUTR logloss gain held, thin cells 40%->23%, and more players rated.
BASE_DAYS, MIN_N, CAP_DAYS = 365, 12, 1095


def rating(key, now):
    h = hist[key]
    num = den = 0.0
    n = 0
    k = 0
    for dt, perf in reversed(h):
        days = (now - dt).days
        if days > CAP_DAYS:
            break
        if days > BASE_DAYS and n >= MIN_N:
            break  # past the recency window AND already deep enough -> stop
        w = 0.97 ** k
        num += w * perf
        den += w
        n += 1
        k += 1
    if n == 0:
        return BASE, 0
    r = num / den
    return (r * n + BASE * max(0, 5 - n)) / max(n, 5), n  # shrink while provisional


pre1 = np.empty(len(two))
pre2 = np.empty(len(two))
n1a = np.empty(len(two), dtype=int)
n2a = np.empty(len(two), dtype=int)
rows = zip(two["player_slug"].values, two["rival_slugname"].astype(str).values,
           two["surface"].values, two["date"].values, two["won"].values, two["meff"].values)
for i, (s1, s2, surf, dt, w1, me) in enumerate(rows):
    dt = pd.Timestamp(dt)
    k1, k2 = (s1, surf), (s2, surf)
    r1, n1 = rating(k1, dt)
    r2, n2 = rating(k2, dt)
    pre1[i], pre2[i], n1a[i], n2a[i] = r1, r2, n1, n2
    if not np.isnan(me):
        m1 = min(max(me, 0.0), 1.0)
    else:
        m1 = 0.62 if w1 else 0.38  # score missing: credit a typical winning share
    hist[k1].append((dt, r2 + (m1 - 0.5) * SPREAD))
    hist[k2].append((dt, r1 + ((1 - m1) - 0.5) * SPREAD))
two["r1"], two["r2"], two["n1"], two["n2"] = pre1, pre2, n1a, n2a
print("pass done", flush=True)
# strictly-prior per-match ratings for model training (Model D v6 merges d_sutr)
two[["player_slug", "rival_slugname", "date", "r1", "r2", "n1", "n2"]].to_parquet(
    "data_cache/tennis_sutr_prematch.parquet")
print("saved tennis_sutr_prematch.parquet", flush=True)

from sklearn.metrics import roc_auc_score
for yr in (2024, 2025, 2026):
    t = two[(two["date"].dt.year == yr) & (two["n1"] >= 5) & (two["n2"] >= 5)
            & two["mkt"].notna()]
    if not len(t):
        continue
    d = t["r1"] - t["r2"]
    auc_r = roc_auc_score(t["won"], d)
    auc_m = roc_auc_score(t["won"], t["mkt"])
    acc = 100 * np.mean((d > 0) == (t["won"] == 1))
    macc = 100 * np.mean((t["mkt"] >= 0.5) == (t["won"] == 1))
    # does sUTR add anything on top of the market? logit blend on train<yr
    tr = two[(two["date"].dt.year < yr) & (two["n1"] >= 5) & (two["n2"] >= 5) & two["mkt"].notna()]
    from sklearn.linear_model import LogisticRegression
    lg = lambda p: np.log(np.clip(p, 1e-6, 1 - 1e-6) / (1 - np.clip(p, 1e-6, 1 - 1e-6)))
    Xtr = np.column_stack([lg(tr["mkt"]), tr["r1"] - tr["r2"]])
    Xte = np.column_stack([lg(t["mkt"]), d])
    lrm = LogisticRegression(max_iter=1000).fit(Xtr, tr["won"])
    from sklearn.metrics import log_loss
    ll_b = log_loss(t["won"], lrm.predict_proba(Xte)[:, 1])
    ll_m = log_loss(t["won"], t["mkt"])
    print(f"{yr}: n={len(t)}  sUTR auc {auc_r:.4f} acc {acc:.1f}%  | mkt auc {auc_m:.4f} acc {macc:.1f}%"
          f"  | logloss mkt {ll_m:.4f} vs mkt+sUTR {ll_b:.4f}", flush=True)

# current ratings artifact for serving/display
import joblib, time
cur = {}
today = two["date"].max()
for (slug, surf) in list(hist.keys()):
    r, n = rating((slug, surf), today)
    if n >= 3:
        cur.setdefault(slug, {})[surf] = {"r": round(float(r), 2), "n": int(n)}
joblib.dump({"ratings": cur, "spread": SPREAD, "built_at": time.strftime("%Y-%m-%d"),
             "asof": str(pd.Timestamp(today).date())},
            "model_artifacts/tennis_sutr.joblib")
print(f"saved tennis_sutr.joblib: {len(cur)} rated players", flush=True)
qs = [v[s]["r"] for v in cur.values() for s in v]
print("rating distribution:", np.percentile(qs, [1, 25, 50, 75, 99]).round(1))
