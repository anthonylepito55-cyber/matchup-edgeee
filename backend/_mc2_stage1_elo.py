# MC v2 — STAGE 1a: surface-Elo family over the full archive (2026-10-08, user spec).
# Chronological Elo per player: overall + per-surface (hard/clay/grass/indoor-ish),
# K decaying with matches played, surface rating adaptively shrunk toward overall when
# thin (user point 7). Walk-forward scorecard on 2024+ priced matches: AUC/logloss of
# (a) overall Elo, (b) surface Elo blend, vs (c) the de-vigged market.
import numpy as np
import pandas as pd

df = pd.read_parquet("data_cache/tennisratio/all_match_logs.parquet",
                     columns=["date", "player_slug", "rival_slugname", "rival_exists",
                              "result", "player_odd", "rival_odd", "surface",
                              "tournament_level", "tournament"])
df["date"] = pd.to_datetime(df["date"], errors="coerce")
df = df.dropna(subset=["date", "player_slug"])
# one row per match: the player_slug < rival perspective, rival must exist in pool
m = df[df["rival_exists"] & df["rival_slugname"].notna()
       & (df["player_slug"] < df["rival_slugname"])].copy()
m = m.sort_values("date").reset_index(drop=True)
m["surf"] = m["surface"].fillna("Hard").str.lower().map(
    lambda s: "clay" if "clay" in s else ("grass" if "grass" in s else "hard"))
print(f"paired matches: {len(m)} | {m['date'].min().date()}..{m['date'].max().date()}", flush=True)

R = {}       # slug -> {"all": r, "hard": r, "clay": r, "grass": r, "n": {...}}
BASE = 1500.0


def get(slug):
    r = R.get(slug)
    if r is None:
        r = {"all": BASE, "hard": BASE, "clay": BASE, "grass": BASE,
             "n_all": 0, "n_hard": 0, "n_clay": 0, "n_grass": 0}
        R[slug] = r
    return r


def kfac(n):
    return 250.0 / (5 + n) + 5.0      # fast early, ~10 late (FiveThirtyEight-ish)


rows = []
for t in m.itertuples(index=False):
    a, b = get(t.player_slug), get(t.rival_slugname)
    s = t.surf
    # adaptive surface rating: shrink toward overall by surface sample
    wa = a[f"n_{s}"] / (a[f"n_{s}"] + 10.0)
    wb = b[f"n_{s}"] / (b[f"n_{s}"] + 10.0)
    sa = wa * a[s] + (1 - wa) * a["all"]
    sb = wb * b[s] + (1 - wb) * b["all"]
    p_all = 1 / (1 + 10 ** ((b["all"] - a["all"]) / 400))
    p_surf = 1 / (1 + 10 ** ((sb - sa) / 400))
    won = 1.0 if t.result == "Win" else 0.0
    # record a scoring row when priced + both players have history
    if (t.date >= pd.Timestamp("2024-01-01") and pd.notna(t.player_odd)
            and pd.notna(t.rival_odd) and t.player_odd > 1.005 and t.rival_odd > 1.005
            and a["n_all"] >= 10 and b["n_all"] >= 10):
        i1, i2 = 1 / t.player_odd, 1 / t.rival_odd
        rows.append((t.date.year, won, p_all, p_surf, i1 / (i1 + i2)))
    # updates
    ka, kb = kfac(a["n_all"]), kfac(b["n_all"])
    a["all"] += ka * (won - p_all)
    b["all"] += kb * ((1 - won) - (1 - p_all))
    ps_up = 1 / (1 + 10 ** ((b[s] - a[s]) / 400))
    a[s] += kfac(a[f"n_{s}"]) * (won - ps_up)
    b[s] += kfac(b[f"n_{s}"]) * ((1 - won) - (1 - ps_up))
    a["n_all"] += 1; b["n_all"] += 1
    a[f"n_{s}"] += 1; b[f"n_{s}"] += 1

sc = pd.DataFrame(rows, columns=["year", "won", "p_all", "p_surf", "p_mkt"])
print(f"scored priced matches 2024+: {len(sc)}", flush=True)


def auc(y, p):
    from sklearn.metrics import roc_auc_score, log_loss
    return roc_auc_score(y, p), log_loss(y, np.clip(p, 1e-6, 1 - 1e-6))


for yr in (2024, 2025, 2026, None):
    g = sc if yr is None else sc[sc["year"] == yr]
    if len(g) < 500:
        continue
    out = [str(yr or 'ALL'), f"n={len(g)}"]
    for col, name in (("p_all", "EloAll"), ("p_surf", "EloSurf"), ("p_mkt", "Market")):
        a9, l9 = auc(g["won"], g[col])
        out.append(f"{name} AUC {a9:.4f} LL {l9:.4f}")
    # 50/50 blend of surface elo and market, and elo-vs-market disagreement check
    a9, l9 = auc(g["won"], 0.5 * g["p_surf"] + 0.5 * g["p_mkt"])
    out.append(f"Surf+Mkt AUC {a9:.4f} LL {l9:.4f}")
    print(" | ".join(out), flush=True)

# persist ratings for stage 2
import pickle
with open("data_cache/_mc2_elo.pkl", "wb") as f:
    pickle.dump(R, f)
print(f"saved ratings for {len(R)} players -> data_cache/_mc2_elo.pkl")
