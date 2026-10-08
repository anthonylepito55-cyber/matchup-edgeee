# FATIGUE EVIDENCE GATE for MC v2 (2026-10-08, user "most accurate Monte Carlo possible"):
# before wiring fatigue into any sim, measure whether recent LOAD predicts anything the
# price doesn't already know. Walk-forward safe: each row's features use only matches
# strictly BEFORE that date. Residual = actual win% minus market-implied win%.
import numpy as np
import pandas as pd

df = pd.read_parquet("data_cache/tennisratio/all_match_logs.parquet",
                     columns=["date", "player_slug", "rival_slugname", "score", "result",
                              "player_odd", "rival_odd", "tournament_level"])
df["date"] = pd.to_datetime(df["date"], errors="coerce")
df = df.dropna(subset=["date", "player_slug"]).sort_values(["player_slug", "date"])
df = df.reset_index(drop=True)


def nsets(s):
    if not isinstance(s, str) or not s.strip():
        return np.nan
    return sum(1 for tok in s.split() if "-" in tok)


df["nsets"] = df["score"].map(nsets)

# per-player rolling load, strictly prior to each match (shift before rolling)
feats = {}
for slug, g in df.groupby("player_slug", sort=False):
    d = g["date"].values
    ns = g["nsets"].fillna(2.0).values
    n = len(g)
    rest = np.full(n, 99.0)
    m7 = np.zeros(n)
    s7 = np.zeros(n)
    j = 0
    for i in range(n):
        if i > 0:
            rest[i] = (d[i] - d[i - 1]) / np.timedelta64(1, "D")
        # window of prior matches within 7 days
        while j < i and (d[i] - d[j]) / np.timedelta64(1, "D") > 7:
            j += 1
        m7[i] = i - j
        s7[i] = ns[j:i].sum()
    feats[slug] = pd.DataFrame({"date": g["date"].values, "rest": rest,
                                "m7": m7, "s7": s7}, index=g.index)
F = pd.concat(feats.values()).sort_index()
df = df.join(F[["rest", "m7", "s7"]])

# rival features via (slug, date) lookup
key = pd.MultiIndex.from_arrays([df["player_slug"], df["date"]])
lut = pd.DataFrame({"r_rest": df["rest"].values, "r_m7": df["m7"].values,
                    "r_s7": df["s7"].values}, index=key)
lut = lut[~lut.index.duplicated(keep="first")]
rk = pd.MultiIndex.from_arrays([df["rival_slugname"].fillna(""), df["date"]])
rv = lut.reindex(rk)
df[["r_rest", "r_m7", "r_s7"]] = rv.values

# priced, recent, rival-features present
df = df[(df["date"] >= "2024-01-01") & df["player_odd"].notna() & df["rival_odd"].notna()
        & df["r_s7"].notna()]
df = df[(df["player_odd"] > 1.005) & (df["rival_odd"] > 1.005)]
i1 = 1 / df["player_odd"]
i2 = 1 / df["rival_odd"]
df["imp"] = i1 / (i1 + i2)
df["win"] = (df["result"] == "Win").astype(float)
# dedupe: keep one perspective per pairing (player_slug < rival)
df = df[df["player_slug"] < df["rival_slugname"].fillna("~~")]
print(f"priced matches 2024+ with both-side load features: {len(df)}", flush=True)


def cell(mask, label):
    g = df[mask]
    n = len(g)
    if n < 30:
        print(f"{label:44s} n={n} (too thin)")
        return
    win = g["win"].mean()
    imp = g["imp"].mean()
    pnl = np.where(g["win"] > 0, g["player_odd"] - 1, -1.0).mean()
    print(f"{label:44s} n={n:>6}  win {100*win:5.1f}%  implied {100*imp:5.1f}%  "
          f"residual {100*(win-imp):+5.1f}pt  ROI {100*pnl:+5.1f}%")


sd = df["s7"] - df["r_s7"]      # positive = PLAYER carried more sets last 7 days
print("\n-- load differential (player sets-in-7d minus rival's) --")
cell(sd <= -6, "player MUCH fresher (6+ fewer sets)")
cell((sd <= -3) & (sd > -6), "player fresher (3-6 fewer sets)")
cell((sd > -3) & (sd < 3), "even load")
cell((sd >= 3) & (sd < 6), "player more worn (3-6 extra sets)")
cell(sd >= 6, "player MUCH more worn (6+ extra sets)")
print("\n-- same, favorites only (player is market fav) --")
fav = df["imp"] >= 0.5
cell(fav & (sd >= 6), "worn FAVORITE (6+ extra sets)")
cell(fav & (sd <= -6), "fresh FAVORITE (6+ fewer)")
print("\n-- same, dogs only --")
cell(~fav & (sd >= 6), "worn DOG (6+ extra sets)")
cell(~fav & (sd <= -6), "fresh DOG (6+ fewer)")
print("\n-- rest days --")
cell((df["rest"] <= 1) & (df["r_rest"] >= 3), "player b2b days, rival rested 3+")
cell((df["rest"] >= 3) & (df["r_rest"] <= 1), "player rested 3+, rival b2b")
print("\n-- heavy absolute load --")
cell((df["s7"] >= 10) & (df["r_s7"] <= 4), "player 10+ sets/7d vs rival <=4")
cell((df["r_s7"] >= 10) & (df["s7"] <= 4), "rival 10+ sets/7d vs player <=4")
