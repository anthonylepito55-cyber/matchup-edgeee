"""Would FADING the demoted favourite signals (backing the dog instead) make money?
Frozen live log only (forward-test doctrine). For every watch-tagged favourite signal:
back the OTHER side at its frozen odds, by gender, vs the baseline of backing every
dog in the same games' price range (so we can tell signal from 'dogs in general')."""
import sys
import numpy as np
import pandas as pd
import tennis_log as T

df = pd.read_parquet("data_cache/_ec2_log_now.parquet")
df = df[df["p1_won"].notna() & df["p1_odds"].notna() & df["p2_odds"].notna()]


def dec(o):
    o = float(o)
    return 1 + o / 100 if o > 0 else 1 + 100 / abs(o)


rows = []
for _, r in df.iterrows():
    i1, i2 = 1 / dec(r.p1_odds), 1 / dec(r.p2_odds)
    mk1 = i1 / (i1 + i2)
    lg = str(r.get("league") or "")
    G = "W" if (("wta" in lg) or ("itf_women" in lg)) else "M"
    dog_p1 = mk1 < 0.5
    dog_od = float(r.p1_odds if dog_p1 else r.p2_odds)
    dog_won = bool(r.p1_won) == dog_p1
    labs = {e["label"]: e for e in T._elite_signals_for_row(r, mk1) if e.get("watch")}
    base = {"G": G, "dog_od": dog_od, "dog_won": dog_won, "ch": "challenger" in lg}
    rows.append({**base, "lab": "__ALL__"})
    for lab, e in labs.items():
        fav_side = 1 if not dog_p1 else 2
        if e["side"] != fav_side:
            continue                       # only favourite-side watch signals
        rows.append({**base, "lab": lab})
D = pd.DataFrame(rows)


def rep(sub):
    if not len(sub):
        return "n=0"
    w = sub.dog_won.values
    pnl = np.where(w, [dec(o) - 1 for o in sub.dog_od], -1.0)
    return f"{int(w.sum())}-{int((~w).sum())}  ROI {100*pnl.mean():+6.1f}%  (n={len(sub)})"


ALL = D[D.lab == "__ALL__"]
print(f"settled live games: {len(ALL)}\n")
print("BASELINE -- back every market dog")
for G in "MW":
    print(f"  {G}: {rep(ALL[ALL.G == G])}")
print("\nFADE = back the DOG when this favourite signal fires")
for lab in sorted(set(D.lab) - {"__ALL__"}):
    S = D[D.lab == lab]
    print(f"\n{lab}")
    for G in "MW":
        s = S[S.G == G]
        print(f"  {G} all prices : {rep(s)}")
        b = s[s.dog_od.between(100, 250)]
        print(f"  {G} dog +100..+250: {rep(b)}")

print("\n=== SAME-BAND BASELINE (every dog +100..+250, no signal) ===")
for G in "MW":
    print(f"  {G}: {rep(ALL[(ALL.G == G) & ALL.dog_od.between(100, 250)])}")
print("\n=== complement: +100..+250 dogs where the signal did NOT fire ===")
D["key"] = D.index  # placeholder
