"""PHASE 3: prospective validation of the four frozen dog-side lanes.

Lanes re-derived INDEPENDENTLY from the frozen log with the rules read out of tennis_log.py
today (commit 02ab0ea), then reconciled against the live lane records before anything is
reported. No thresholds are touched.

  c75_dog_100plus  (born 2026-10-08)  C75 >= 50% on the market dog, dog odds >= +100
  mc_c75_dog       (born 2026-10-06)  C75's pick is the market dog, ANY dog price, not mc_c_recon
  mc6_dog2_all     (born 2026-10-16)  MC6 (non-recon) 2pt+ over the de-vigged market on the dog
  s52_fav_band_dog (born 2026-10-11)  dog +100..+200 where the FAVOURITE owns both 52w stat gaps

Eligibility = settled handling per spec: voids and pending shown separately, never as losses.
Population: both odds present, none of BAD_ROW_FLAGS; bet-loop lanes additionally require
model_c_p1 AND model_cma_p1 (a hidden dependency documented in the report); s52 requires its
four stat columns. PRE-BIRTH rows are the lane's replay of frozen reads made before the RULE
existed -- in-sample for the rule; PROSPECTIVE = start_time_utc after the rule was born.
"""
import math
import pandas as pd
import tennis_log as T

BIRTH = {"c75_dog_100plus": "2026-10-08", "mc_c75_dog": "2026-10-06",
         "mc6_dog2_all": "2026-10-16", "s52_fav_band_dog": "2026-10-11"}

log = pd.read_parquet(T.LOG_PATH)


def f(c):
    return log[c].fillna(False).astype(bool) if c in log.columns else pd.Series(False, index=log.index)


bad = pd.Series(False, index=log.index)
for c in T.BAD_ROW_FLAGS:
    bad |= f(c)


def dec(a):
    a = float(a)
    return 1.0 + (a / 100.0 if a > 0 else 100.0 / -a)


rows = []
for ix, r in log.iterrows():
    if bad.loc[ix] or pd.isna(r["p1_odds"]) or pd.isna(r["p2_odds"]):
        continue
    d1, d2 = dec(r["p1_odds"]), dec(r["p2_odds"])
    mk1 = (1 / d1) / (1 / d1 + 1 / d2)
    dog1 = mk1 < 0.5
    dodds = float(r["p1_odds"] if dog1 else r["p2_odds"])
    lg = str(r.get("league") or "")
    settled = bool(r["settled"]) and pd.notna(r["p1_won"])
    void = bool(r.get("void")) if pd.notna(r.get("void")) else False
    base = dict(
        fixture_id=r.get("fixture_id"), date=str(r["date"])[:10], start=str(r.get("start_time_utc") or ""),
        logged_at=str(r.get("logged_at") or ""), league=lg, surface=str(r.get("surface") or ""),
        tournament=str(r.get("tournament") or ""), player_1=r["player_1"], player_2=r["player_2"],
        gender="W" if ("wta" in lg or "itf_women" in lg) else "M",
        tour=("TOUR" if lg in ("atp", "wta") else ("CHALL" if lg == "atp_challenger" else "ITF")),
        dog1=dog1, dodds=dodds, ddec=(d1 if dog1 else d2), mkdog=min(mk1, 1 - mk1),
        settled=settled, void=void,
        dogwon=(None if (not settled or void) else (bool(r["p1_won"]) == dog1)),
        open_p1=r.get("open_p1_odds"), open_p2=r.get("open_p2_odds"), p1_odds=r["p1_odds"], p2_odds=r["p2_odds"])

    has_c = pd.notna(r.get("model_c_p1")) and pd.notna(r.get("model_cma_p1"))
    c75 = r.get("mc_c75_p1")
    if has_c and pd.notna(c75):
        c75dog = (float(c75) >= 0.5) == dog1
        if c75dog and dodds >= 100:
            rows.append(dict(base, lane="c75_dog_100plus", prob=(float(c75) if dog1 else 1 - float(c75))))
        mcrec = bool(r.get("mc_c_recon")) if pd.notna(r.get("mc_c_recon")) else False
        if c75dog and not mcrec:
            rows.append(dict(base, lane="mc_c75_dog", prob=(float(c75) if dog1 else 1 - float(c75))))
    m6 = r.get("mc6_p1")
    m6rec = bool(r.get("mc6_recon")) if pd.notna(r.get("mc6_recon")) else False
    if has_c and pd.notna(m6) and not m6rec:
        pdog = float(m6) if dog1 else 1 - float(m6)
        if pdog - base["mkdog"] >= 0.02:
            rows.append(dict(base, lane="mc6_dog2_all", prob=pdog))
    s52 = [r.get(c) for c in ("s52_sgw_p1", "s52_rgw_p1", "s52_sgw_p2", "s52_rgw_p2")]
    if all(pd.notna(x) for x in s52) and 100 <= dodds <= 200:
        sgn = 1.0 if dog1 else -1.0
        ds = sgn * (float(s52[0]) - float(s52[2]))
        dr = sgn * (float(s52[1]) - float(s52[3]))
        if ds < 0 and dr < 0:
            rows.append(dict(base, lane="s52_fav_band_dog", prob=None))

S = pd.DataFrame(rows)
S["prospective"] = [r["start"][:10] > BIRTH[r["lane"]] for _, r in S.iterrows()]

# ---------------------------------------------------------------- reconcile vs the live lanes
rec = T.get_ab25_record()["study"]
print("RECONCILE (derived settled non-void count vs live lane record)")
ok = True
for ln in BIRTH:
    mine = int((S["lane"] == ln)[(S["settled"]) & (~S["void"])].sum()) if len(S) else 0
    mine = len(S[(S["lane"] == ln) & S["settled"] & ~S["void"]])
    lane_n = (rec.get(ln) or {}).get("n")
    status = "OK" if lane_n is not None and abs(mine - lane_n) <= 2 else "MISMATCH"
    ok &= status == "OK"
    print("   %-18s derived %-5d lane %-5s %s" % (ln, mine, lane_n, status))
assert ok, "derived selections do not reproduce the lanes -- refusing to report"


def wilson(w, n, z=1.96):
    if not n:
        return (0, 0)
    p = w / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return (c - h, c + h)


def block(df, lab, show_min=1):
    st = df[df["settled"] & ~df["void"]]
    n = len(st)
    if n < show_min:
        return None
    w = int(st["dogwon"].sum())
    pnl = [(x["ddec"] - 1.0) if x["dogwon"] else -1.0 for _, x in st.iterrows()]
    roi = sum(pnl) / n if n else 0
    sd = (sum((p - roi) ** 2 for p in pnl) / (n - 1)) ** 0.5 if n > 1 else 0
    se = sd / math.sqrt(n) if n else 0
    lo, hi = wilson(w, n)
    avg_d = st["ddec"].mean()
    need = (1 / st["ddec"]).mean()
    mk = st["mkdog"].mean()
    pend = len(df[~df["settled"] & ~df["void"]])
    vd = int(df["void"].sum())
    print("   %-26s n=%-4d %2d-%-3d win %5.1f%% [%4.1f-%4.1f]  avg +%d  mkt %4.1f%% need %4.1f%%  "
          "ROI %+7.2f%% ±%.1f  $%+8.2f  pend %d void %d"
          % (lab, n, w, n - w, 100 * w / n, 100 * lo, 100 * hi,
             round((avg_d - 1) * 100), 100 * mk, 100 * need, 100 * roi, 196 * se, 25 * sum(pnl), pend, vd))
    return dict(n=n, w=w, roi=roi, se=se, pnl=pnl)


print("")
print("=" * 118)
print("PER LANE -- ALL eligible rows, then PRE-BIRTH (replay, in-sample for the rule) vs PROSPECTIVE")
print("=" * 118)
res = {}
for ln in BIRTH:
    g = S[S["lane"] == ln]
    print("%s  (rule born %s)" % (ln, BIRTH[ln]))
    block(g, "all eligible")
    block(g[~g["prospective"]], "pre-birth replay")
    res[ln] = block(g[g["prospective"]], "PROSPECTIVE")
    for gd in ("M", "W"):
        block(g[g["prospective"] & (g["gender"] == gd)], "  prospective %s" % gd)
    print("")

print("=" * 118)
print("STEP 5 -- the women's underdog hypothesis (PROSPECTIVE rows only)")
print("=" * 118)
for ln in ("c75_dog_100plus", "mc_c75_dog", "s52_fav_band_dog", "mc6_dog2_all"):
    g = S[(S["lane"] == ln) & S["prospective"] & (S["gender"] == "W")]
    print("%s, women prospective:" % ln)
    block(g, "  all women")
    block(g[g["tour"] == "ITF"], "  ITF")
    block(g[g["tour"] != "ITF"], "  tour+challenger")
    for lo2, hi2, bl in ((100, 150, "+100..+150"), (150.001, 200, "+151..+200"), (200.001, 300, "+201..+300"), (300.001, 10000, "+300+")):
        block(g[(g["dodds"] > lo2 - 0.001) & (g["dodds"] <= hi2)], "  %s" % bl, show_min=5)
    # concentration
    st = g[g["settled"] & ~g["void"]]
    if len(st) >= 10:
        st = st.assign(pnl=[(x["ddec"] - 1.0) if x["dogwon"] else -1.0 for _, x in st.iterrows()])
        tot = st["pnl"].sum()
        top5 = st.nlargest(5, "pnl")["pnl"].sum()
        bytour = st.groupby("tournament")["pnl"].sum().sort_values(ascending=False)
        print("     concentration: total %+0.2fu | top-5 matches %+0.2fu | best tournament %r %+0.2fu | odds>=+250 share %+0.2fu"
              % (tot, top5, str(bytour.index[0])[:22], bytour.iloc[0], st[st["dodds"] >= 250]["pnl"].sum()))
    print("")

print("=" * 118)
print("MARKET BENCHMARK -- every eligible dog, same population & window, no model (prospective dates per lane)")
print("=" * 118)
# one shared benchmark population: all eligible rows (lane-agnostic), split by gender/band
bench = log[~bad & log["p1_odds"].notna() & log["p2_odds"].notna()].copy()
bench = bench[bench["settled"].fillna(False).astype(bool) & bench["p1_won"].notna()
              & ~bench["void"].fillna(False).astype(bool)]
rows_b = []
for _, r in bench.iterrows():
    d1, d2 = dec(r["p1_odds"]), dec(r["p2_odds"])
    mk1 = (1 / d1) / (1 / d1 + 1 / d2)
    dog1 = mk1 < 0.5
    lg = str(r.get("league") or "")
    rows_b.append(dict(date=str(r["date"])[:10], dodds=float(r["p1_odds"] if dog1 else r["p2_odds"]),
                       ddec=d1 if dog1 else d2, dogwon=bool(r["p1_won"]) == dog1,
                       gender="W" if ("wta" in lg or "itf_women" in lg) else "M"))
B = pd.DataFrame(rows_b)
for gd in ("W", "M"):
    for frm in ("2026-10-06", "2026-10-11"):
        g = B[(B["gender"] == gd) & (B["date"] > frm)]
        pnl = [(x.ddec - 1) if x.dogwon else -1.0 for x in g.itertuples()]
        n = len(pnl)
        g2 = g[(g["dodds"] >= 100) & (g["dodds"] <= 200)]
        pnl2 = [(x.ddec - 1) if x.dogwon else -1.0 for x in g2.itertuples()]
        print("   blind %s dogs from %s: all %+6.2f%% /%-4d | +100..+200 %+6.2f%% /%d"
              % (gd, frm, 100 * sum(pnl) / n if n else 0, n,
                 100 * sum(pnl2) / len(pnl2) if len(pnl2) else 0, len(pnl2)))

print("")
print("OVERLAP BETWEEN LANES (prospective settled selections, match-keyed)")
sets = {ln: set(zip(S[(S["lane"] == ln) & S["prospective"] & S["settled"] & ~S["void"]]["date"],
                    S[(S["lane"] == ln) & S["prospective"] & S["settled"] & ~S["void"]]["player_1"],
                    S[(S["lane"] == ln) & S["prospective"] & S["settled"] & ~S["void"]]["player_2"]))
        for ln in BIRTH}
for a in BIRTH:
    for b2 in BIRTH:
        if a < b2:
            inter = len(sets[a] & sets[b2])
            uni = len(sets[a] | sets[b2])
            print("   %-18s & %-18s shared %-4d jaccard %.2f" % (a, b2, inter, inter / uni if uni else 0))

# CLV vs opening line, where an opener exists and differs
print("")
print("CLV vs OPENING LINE (prospective, settled; frozen price is ~the close per the Pinnacle study)")
for ln in BIRTH:
    g = S[(S["lane"] == ln) & S["prospective"] & S["settled"] & ~S["void"]]
    deltas = []
    for _, x in g.iterrows():
        op = x["open_p1"] if x["dog1"] else x["open_p2"]
        if pd.isna(op) or op == (x["p1_odds"] if x["dog1"] else x["p2_odds"]):
            continue
        iop = 1 / dec(op)
        icl = 1 / x["ddec"]
        deltas.append(100 * (iop - icl))   # + = we hold a better (cheaper) price than the open
    if deltas:
        ds = pd.Series(deltas)
        print("   %-18s n=%-4d mean %+5.2fpp  median %+5.2fpp  (close cheaper than open = +)"
              % (ln, len(ds), ds.mean(), ds.median()))
    else:
        print("   %-18s no usable openers" % ln)

# selections export
S.to_csv("data_cache/phase3_selections.csv", index=False)
print("")
print("selections CSV: data_cache/phase3_selections.csv (%d selection-rows)" % len(S))
