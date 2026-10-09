"""POST-MORTEM ON EVERY LOSING MARKED PICK, LAST 5 DAYS (2026-10-08, user ask).
Replays the board's marks on the frozen log, lists the losses with the signals that
pointed the OTHER way, then asks the only question that matters: does any available
signal actually SEPARATE the marked winners from the marked losers?
"""
import numpy as np
import pandas as pd

LOG = "data_cache/_ec2_log_now.parquet"
df = pd.read_parquet(LOG)
df["d"] = df["date"].astype(str).str[:10]
d = df[(df["d"] >= "2026-10-04") & df["p1_won"].notna()
       & df["p1_odds"].notna() & df["p2_odds"].notna()].copy()


def dec(o):
    o = float(o)
    return 1 + o / 100 if o > 0 else 1 + 100 / abs(o)


SIMS = ("mc_c_p1", "mc_c75_p1", "mc_cutr_p1", "mc_p1")
rows = []
for r in d.itertuples():
    need = ("model_a_p1", "model_b_p1", "model_c_p1", "model_cma_p1")
    if any(pd.isna(getattr(r, c)) for c in need):
        continue
    i1, i2 = 1 / dec(r.p1_odds), 1 / dec(r.p2_odds)
    mk1 = i1 / (i1 + i2)
    dog1 = mk1 < 0.5
    lg = str(r.league or "")
    wom = ("wta" in lg) or ("itf_women" in lg)
    c1 = float(r.model_c_p1) >= 0.5
    g1 = float(r.model_cma_p1) >= 0.5
    aS = float(r.model_a_p1) >= 0.5
    bS = float(r.model_b_p1) >= 0.5
    alone = (aS != c1) and (bS != c1)
    mdog = mk1 if dog1 else 1 - mk1
    gdog = float(r.model_cma_p1) if dog1 else 1 - float(r.model_cma_p1)
    star = (c1 == g1) and (g1 == dog1)
    gray4 = (g1 == dog1) and (gdog - mdog >= 0.04)
    dog_od = float(r.p1_odds if dog1 else r.p2_odds)
    fav_od = float(r.p1_odds if not dog1 else r.p2_odds)
    favP = 1 - mdog
    marks = []            # (mark name, side_is_p1)
    # BLUE bedrock dog cells
    if alone and g1 == c1 and c1 == dog1:
        marks.append(("BLUE c-alone+gray", dog1))
    if star and (alone or gray4):
        marks.append(("BLUE tier1", dog1))
    if gray4:
        marks.append(("BLUE gray4", dog1))
    if (aS != c1) and (bS == c1) and c1 == dog1 and g1 == c1:
        marks.append(("BLUE fade-A", dog1))
    # c75 banded dog (blue) + the BLACK women cell
    if pd.notna(r.mc_c75_p1):
        c75dog = (float(r.mc_c75_p1) >= 0.5) == dog1
        if c75dog and 100 <= dog_od <= 200:
            marks.append(("BLUE c75 dog", dog1))
        if wom and c75dog and dog_od >= 100:
            marks.append(("BLACK women c75 dog", dog1))
    # GREEN bait + the MC-flip gate
    if all(pd.notna(getattr(r, c)) for c in SIMS):
        favs = [(float(getattr(r, c)) if not dog1 else 1 - float(getattr(r, c))) for c in SIMS]
        disc = 0.04 if wom else 0.06
        k = sum(1 for f in favs if f <= favP - disc)
        if k == 4 and 100 <= dog_od <= 200:
            flip = (float(r.mc_c75_p1) >= 0.5) == dog1
            marks.append(("GREEN bait" + (" (MC confirms)" if flip else " (MC refuses)"), dog1))
    # PURPLE CGF (gated), CE5, FGW
    if alone and g1 == c1 and c1 != dog1:
        gE = (float(r.model_cma_p1) if c1 else 1 - float(r.model_cma_p1)) - favP
        lo = -200 if wom else -150
        if lo <= fav_od <= -100 and gE >= 0.05 and "challenger" not in lg:
            marks.append(("PURPLE CGF", not dog1))
    cfav = (float(r.model_c_p1) if not dog1 else 1 - float(r.model_c_p1))
    if cfav - favP >= 0.05 and -200 <= fav_od <= -150:
        marks.append(("PURPLE CE5 (now watch)", not dog1))
    if wom and (mdog - gdog) >= 0.02 and -300 <= fav_od <= -200:
        marks.append(("PURPLE FGW", not dog1))
    if not marks:
        continue
    for nm, side in marks:
        won = bool(r.p1_won) == side
        od = float(r.p1_odds if side else r.p2_odds)
        pick = r.player_1 if side else r.player_2
        opp = r.player_2 if side else r.player_1
        # counter-signals: did each read favour the OTHER side?
        def against(col):
            v = getattr(r, col, None)
            if pd.isna(v):
                return None
            return (float(v) >= 0.5) != side
        rows.append({
            "date": r.d, "mark": nm, "pick": pick, "opp": opp, "od": od, "won": won,
            "wom": wom, "lg": lg, "score": r.score,
            "A_against": against("model_a_p1"), "B_against": against("model_b_p1"),
            "AB_both": (against("model_a_p1") is True) and (against("model_b_p1") is True),
            "X_against": against("model_x_p1"), "MC2_against": against("mc2_p1"),
            "c75_against": against("mc_c75_p1"), "c50_against": against("mc_c_p1"),
            "form_against": (None if pd.isna(r.pf_edge_p1)
                             else ((float(r.pf_edge_p1) > 0) != side)),
            "form_mag": (None if pd.isna(r.pf_edge_p1) else abs(float(r.pf_edge_p1))),
            "utr_against": (None if pd.isna(r.utr_edge_p1)
                            else ((float(r.utr_edge_p1) > 0) != side)),
            "late": any(t in str(r.round or "").lower()
                        for t in ("final", "semi", "quarter")),
            "ch": "challenger" in lg,
        })
R = pd.DataFrame(rows)
R.to_parquet("data_cache/_loss_postmortem.parquet")
print(f"marked picks, 2026-10-04..08: {len(R)}  "
      f"({int(R.won.sum())} won / {int((~R.won).sum())} lost)\n")

print("=== EVERY LOSING MARKED PICK ===")
L = R[~R.won].sort_values(["date", "mark"])
for r in L.itertuples():
    ag = [nm for nm, v in (("A", r.A_against), ("B", r.B_against), ("X", r.X_against),
                           ("MC2", r.MC2_against), ("c75", r.c75_against),
                           ("c50", r.c50_against), ("form", r.form_against),
                           ("UTR", r.utr_against)) if v is True]
    print(f"  {r.date}  {r.mark:26s} {str(r.pick)[:22]:22s} {r.od:>6.0f}  "
          f"vs {str(r.opp)[:18]:18s} | against: {','.join(ag) if ag else 'nothing'}"
          f"{' | ' + str(r.score) if r.score else ''}")

print("\n=== DOES ANY SIGNAL SEPARATE THE MARKED WINNERS FROM THE LOSERS? ===")
print("   (win rate of the marked pick when each counter-signal is present vs absent)")
for col in ("A_against", "B_against", "AB_both", "X_against", "MC2_against",
            "c75_against", "c50_against", "form_against", "utr_against", "late", "ch"):
    sub = R[R[col].notna()] if R[col].dtype == object else R
    on = sub[sub[col] == True]
    off = sub[sub[col] == False]
    if len(on) < 8 or len(off) < 8:
        print(f"  {col:14s} n_on={len(on)} n_off={len(off)} (thin)")
        continue
    def roi(x):
        pnl = np.where(x.won, [dec(o) - 1 for o in x.od], -1)
        return 100 * pnl.mean()
    print(f"  {col:14s} present: {100*on.won.mean():5.1f}% win  ROI {roi(on):+7.1f}%  (n={len(on)})"
          f"   | absent: {100*off.won.mean():5.1f}% win  ROI {roi(off):+7.1f}%  (n={len(off)})")
print("\n=== BY MARK FAMILY ===")
for mk, sub in R.groupby("mark"):
    pnl = np.where(sub.won, [dec(o) - 1 for o in sub.od], -1)
    print(f"  {mk:28s} {int(sub.won.sum())}-{int((~sub.won).sum())}  "
          f"ROI {100*pnl.mean():+7.1f}%  (n={len(sub)})")
