"""EVERY board signal backtested GENDER x SIDE (2026-10-07 user ask: "whats the backtest
of every single dog signal and favorite signal for men seperate and women seperate").
Same walk-forward rig as _tennis_gender_full_bt (A/B/C/gray, 2024-26, shipped recipes)
plus the Model-D core for the D lanes. Every fired cell is bucketed into
(M dog / M fav / W dog / W fav) by whether the side it BETS is the market dog.
One-sided-by-construction lanes (star=always dog, fade=always fav...) fill one column.
MC/c75/cUTR/pure-form lanes are NOT here: no multi-year walk-forward exists for the
sims/overlay -- their dog/fav records are the forward log (Splits tab)."""
import numpy as np

ns = {}
src = open("_tennis_abc6_agree_bt.py", encoding="utf-8").read()
exec(compile(src.split("tot = {")[0], "_prep6", "exec"), ns)
KEY = ns["KEY"]
core_a, FC_A = ns["core_a"], ns["FC_A"]
core_b, FC_B = ns["core_b"], ns["FC_B"]
core_c, FC_C = ns["core_c"], ns["FC_C"]
mC = ns["mC"] if "mC" in ns else ns["m"]
lvl = {}
for k, l in zip(mC[KEY].itertuples(index=False, name=None), mC["tournament_level"].astype(str)):
    s = l.lower()
    if "wom" in s or "wta" in s:
        lvl[k] = "W"
    elif "atp" in s or "men" in s or "challenger" in s or "future" in s:
        lvl[k] = "M"
    else:
        lvl[k] = "?"
print("ABC cores ready", flush=True)

nd = {}
srcd = open("_tennis_model_d_build.py", encoding="utf-8").read()
exec(compile(srcd.split("from sklearn.linear_model")[0], "_tmd_prep", "exec"), nd)
core_d, FC_D = nd["core"], nd["FC_D"]
print(f"D core ready: {len(core_d)}", flush=True)

from sklearn.linear_model import LogisticRegression
import xgboost as xgb

def lg(p):
    p = np.clip(np.asarray(p, dtype=float), 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p))

def fit_p(core, FC, yr):
    tr = core[core["date"].dt.year < yr]
    te = core[core["date"].dt.year == yr]
    Xtr, Xte = tr[FC].fillna(0), te[FC].fillna(0)
    ytr = tr["won"]
    lr = LogisticRegression(max_iter=3000, C=0.5).fit(Xtr, ytr)
    bst = xgb.XGBClassifier(n_estimators=300, max_depth=4, learning_rate=0.05, subsample=0.9,
                            colsample_bytree=0.8, n_jobs=8, eval_metric="logloss").fit(Xtr, ytr)
    p = 0.5 * (lr.predict_proba(Xte)[:, 1] + bst.predict_proba(Xte)[:, 1])
    lr_ms = LogisticRegression(max_iter=3000, C=0.5).fit(np.column_stack([lg(tr["mkt"]), Xtr]), ytr)
    p_ms = lr_ms.predict_proba(np.column_stack([lg(te["mkt"]), Xte]))[:, 1]
    return {k: (float(pr), float(pm), bool(w), float(m1), a, b)
            for k, pr, pm, w, m1, a, b in zip(te[KEY].itertuples(index=False, name=None),
                                              p, p_ms, te["won"].values, te["mkt"].values,
                                              te["player_odd"].values, te["rival_odd"].values)}

CELLS = ("c_all", "c_with", "c_alone_all", "calone_gdog", "calone_gfav", "calone_nogray",
         "star", "star4", "gray_dog4", "fade_gold", "hated_dog", "cma_all",
         "gray2_fav", "gray2_dog", "cedge5_fav", "cedge5_dog",
         "ab_agree", "a_alone", "b_alone", "abc_agree", "abc_dog", "all6",
         "fade_a", "fade_a_dog", "fade_a_dog_gray", "fade_a_fav",
         "against_a", "cvg_c", "cvg_gray", "green",
         "tier1", "tier2", "tier3", "tier_avoid", "tier_nobet",
         "d_all", "dma_all", "d_gray_dog", "d_alone", "dma_edge2", "abcd_agree")
# agg[cell][gender][side] -> {"a": [(pnl,hit)], "y26": [...]}
agg = {c: {g: {sd: {"a": [], "y26": []} for sd in ("dog", "fav")} for g in ("M", "W")} for c in CELLS}
for yr in (2024, 2025, 2026):
    pa = fit_p(core_a, FC_A, yr)
    pb = fit_p(core_b, FC_B, yr)
    pc = fit_p(core_c, FC_C, yr)
    pd_ = fit_p(core_d, FC_D, yr)
    for k in set(pa) & set(pb) & set(pc):
        g = lvl.get(k, "?")
        if g == "?":
            continue
        pcr, pcg, w1, m1, a, b = pc[k]
        par, pag = pa[k][0], pa[k][1]
        pbr, pbg = pb[k][0], pb[k][1]
        cS, gS = pcr >= 0.5, pcg >= 0.5
        aS, bS = par >= 0.5, pbr >= 0.5
        agS, bgS = pag >= 0.5, pbg >= 0.5
        dog1 = m1 < 0.5
        mdog = m1 if dog1 else 1 - m1
        gdog = pcg if dog1 else 1 - pcg
        alone = aS != cS and bS != cS
        hate = (mdog - gdog) >= 0.02
        star = (cS == gS) and (gS == dog1)
        passfav = alone and gS == cS and cS != dog1

        fires = [("c_all", cS), ("cma_all", gS), ("against_a", not aS)]
        if aS == cS or bS == cS:
            fires.append(("c_with", cS))
        if alone:
            fires.append(("c_alone_all", cS))
            if gS == cS:
                fires.append(("calone_gdog" if cS == dog1 else "calone_gfav", cS))
            else:
                fires.append(("calone_nogray", cS))
        if star:
            fires.append(("star", dog1))
            if (gdog - mdog) >= 0.04:
                fires.append(("star4", dog1))
        if gS == dog1 and (gdog - mdog) >= 0.04:
            fires.append(("gray_dog4", dog1))
        if hate:
            fires.append(("fade_gold", not dog1))
            fires.append(("hated_dog", dog1))
        e1 = pcg - m1 >= 0.02
        e2 = (1 - pcg) - (1 - m1) >= 0.02
        if e1 or e2:
            eS = e1
            fires.append(("gray2_dog" if (m1 < 0.5) == eS else "gray2_fav", eS))
        f1 = pcr - m1 >= 0.05
        f2 = (1 - pcr) - (1 - m1) >= 0.05
        if f1 or f2:
            fS = f1
            fires.append(("cedge5_dog" if (m1 < 0.5) == fS else "cedge5_fav", fS))
        if aS == bS:
            fires.append(("ab_agree", aS))
        else:
            fires.append(("a_alone", aS))
            fires.append(("b_alone", bS))
            if bS == cS:
                fires.append(("fade_a", bS))
                if bS == dog1:
                    fires.append(("fade_a_dog", bS))
                    if gS == bS:
                        fires.append(("fade_a_dog_gray", bS))
                else:
                    fires.append(("fade_a_fav", bS))
        if aS == bS == cS:
            fires.append(("abc_agree", cS))
            if cS == dog1:
                fires.append(("abc_dog", cS))
            if cS == gS == agS == bgS:
                fires.append(("all6", cS))
        if cS != gS:
            fires.append(("cvg_c", cS))
            fires.append(("cvg_gray", gS))
        if not star and not hate and not passfav:
            fires.append(("green", gS))
        if star and (alone or (gdog - mdog) >= 0.04):
            fires.append(("tier1", dog1))
        elif star:
            fires.append(("tier2", dog1))
        elif hate or passfav:
            fires.append(("tier3", not dog1))
        elif cS != gS:
            fires.append(("tier_avoid", cS))
        else:
            fires.append(("tier_nobet", gS))
        # ---- Model D lanes (only where D has a walk-forward read on this match) ----
        if k in pd_:
            pdr, pdg = pd_[k][0], pd_[k][1]
            dS, dgS = pdr >= 0.5, pdg >= 0.5
            fires.append(("d_all", dS))
            fires.append(("dma_all", dgS))
            if dS == dgS and dS == dog1:
                fires.append(("d_gray_dog", dS))
            if aS != dS and bS != dS and cS != dS:
                fires.append(("d_alone", dS))
            dside = pdg if dgS else 1 - pdg
            mside = m1 if dgS else 1 - m1
            if dside - mside >= 0.02:
                fires.append(("dma_edge2", dgS))
            if aS == bS == cS == dS:
                fires.append(("abcd_agree", cS))

        for cell, side in fires:
            o = a if side else b
            if not o or o <= 1.005:
                continue
            v = (o - 1) if (w1 == side) else -1.0
            hit = (w1 == side)
            sd = "dog" if (side == dog1) else "fav"
            agg[cell][g][sd]["a"].append((v, hit))
            if yr == 2026:
                agg[cell][g][sd]["y26"].append((v, hit))
    print(f"{yr} done", flush=True)


def cellstr(v):
    if not v:
        return "--"
    wins = sum(1 for _, h in v if h)
    roi = 100 * np.mean([x for x, _ in v])
    return f"{wins}-{len(v)-wins} {100*wins/len(v):.0f}% {roi:+.1f}%"


for w, tag in (("a", "ALL YEARS (2024-26)"), ("y26", "2026 ONLY")):
    print(f"\n==== {tag} ====")
    print(f"{'cell':<16}{'MEN DOG':>24}{'MEN FAV':>24}{'WOMEN DOG':>24}{'WOMEN FAV':>24}")
    for c in CELLS:
        row = f"{c:<16}"
        for g in ("M", "W"):
            for sd in ("dog", "fav"):
                row += cellstr(agg[c][g][sd][w]).rjust(24)
        print(row)
