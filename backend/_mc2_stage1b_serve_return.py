# MC v2 — STAGE 1b (user priority #1): OPPONENT-ADJUSTED serve/return ratings, built in
# one leak-free chronological pass, folding in #2 (surface Elo), #4 (EB shrinkage via
# count-decaying K), #5 (slow career + fast half-life forms). Emits:
#   data_cache/_mc2_features.parquet  -- per-match PRE-MATCH features + realized-SPW
#                                        targets (the Stage-2 training table)
#   scorecard: closed-form point->game->set->match Markov from adjusted serve/return
#              (a first #3 read) vs Elo vs market, chronological 2024/25/26.
# Rating model (additive, Elo-style on serve points):
#   E[SPW A serving vs B] = base(surface) + S_A - R_B
#   after the match: S_A += kS*(actual-E),  R_B += kR*(E-actual)
# so every update is automatically strength-of-schedule adjusted (user point 2: actual
# minus expected-vs-THOSE-opponents), and K ~ 1/(n+n0) is the EB shrink.
import numpy as np
import pandas as pd
from functools import lru_cache

COLS = ["date", "player_slug", "rival_slugname", "rival_exists", "result", "score",
        "player_odd", "rival_odd", "surface", "tournament_level", "tournament",
        "first_serve_accuracy", "first_serve_points", "second_serve_points",
        "return_1st_serve_points", "return_2nd_serve_points",
        "serve_pressure_all", "serve_pressure_won",
        "return_pressure_all", "return_pressure_won"]
df = pd.read_parquet("data_cache/tennisratio/all_match_logs.parquet", columns=COLS)
df["date"] = pd.to_datetime(df["date"], errors="coerce")
df = df.dropna(subset=["date", "player_slug"])
m = df[df["rival_exists"] & df["rival_slugname"].notna()
       & (df["player_slug"] < df["rival_slugname"])].copy()
m = m.sort_values("date").reset_index(drop=True)
m["surf"] = m["surface"].fillna("Hard").str.lower().map(
    lambda s: "clay" if "clay" in s else ("grass" if "grass" in s else "hard"))
# gender + level group (2026-10-08 addition: gender-split training is first-class)
_lv = m["tournament_level"].fillna("").str.lower() + " " + m["tournament"].fillna("").str.lower()
m["wom"] = _lv.str.contains("wom|wta|girl|w15|w25|w35|w50|w75|w100").astype(int)
m["lvlg"] = m["tournament_level"].fillna("").str.lower().map(
    lambda v: 3 if "slam" in v else (2 if ("atp" in v or "wta" in v) else (1 if "challenger" in v else 0)))


def pct(v):
    try:
        v = float(v) / 100.0
    except (TypeError, ValueError):
        return np.nan
    return v if 0.0 <= v <= 1.0 else np.nan


W1 = 0.62      # global avg share of points on 1st serve (for the return-side inversion)


def spw_from(fsa, fsp, ssp):
    fsa, fsp, ssp = pct(fsa), pct(fsp), pct(ssp)
    if np.isnan(fsp) or np.isnan(ssp):
        return np.nan
    w = fsa if not np.isnan(fsa) else W1
    v = w * fsp + (1 - w) * ssp
    return v if 0.25 <= v <= 0.95 else np.nan


def spw_rival(r1, r2):
    r1, r2 = pct(r1), pct(r2)
    if np.isnan(r1) or np.isnan(r2):
        return np.nan
    v = 1 - (W1 * r1 + (1 - W1) * r2)
    return v if 0.25 <= v <= 0.95 else np.nan


# ---- closed-form Markov: point prob -> game/tb/set/match (user #3) ----
@lru_cache(maxsize=200000)
def p_game(p):
    q = 1 - p
    pd2 = p * p / (p * p + q * q)          # win from deuce
    return (p**4) * (1 + 4 * q + 10 * q * q) + 20 * (p**3) * (q**3) * pd2


@lru_cache(maxsize=200000)
def p_tb(pa, pb):
    # first to 7 by 2; serves alternate -- approximate each point as the average
    # point-win prob for A across serve/return (standard closed-form shortcut)
    p = 0.5 * (pa + (1 - pb))
    q = 1 - p
    from math import comb
    win = sum(comb(6 + k, k) * (p**7) * (q**k) for k in range(6))
    reach66 = comb(12, 6) * (p**6) * (q**6)
    return win + reach66 * (p * p / (p * p + q * q))


@lru_cache(maxsize=200000)
def p_set(pa, pb):
    ga, gb = p_game(pa), 1 - p_game(pb)    # A's hold prob, A's break prob
    # dynamic program over games, A serves first (symmetrized later)
    from functools import lru_cache as lc

    def win_from(a, b, aserves):
        if a >= 6 and a - b >= 2:
            return 1.0
        if b >= 6 and b - a >= 2:
            return 0.0
        if a == 6 and b == 6:
            return p_tb(pa, pb)
        key = (a, b, aserves)
        if key in memo:
            return memo[key]
        pw = ga if aserves else gb
        r = pw * win_from(a + 1, b, not aserves) + (1 - pw) * win_from(a, b + 1, not aserves)
        memo[key] = r
        return r
    memo = {}
    return 0.5 * win_from(0, 0, True) + 0.5 * win_from(0, 0, False)


@lru_cache(maxsize=200000)
def p_match_bo3(pa, pb):
    s = p_set(pa, pb)
    return s * s + 2 * s * s * (1 - s)


def rnd(x):
    return round(min(max(x, 0.40), 0.85), 3)


# ---- chronological pass ----
BASE0 = 0.615
state = {}


def get(slug):
    st = state.get(slug)
    if st is None:
        st = {"elo": 1500.0, "elo_s": {"hard": 1500.0, "clay": 1500.0, "grass": 1500.0},
              "n": 0, "ns": {"hard": 0, "clay": 0, "grass": 0},
              "S": 0.0, "R": 0.0, "nS": 0, "nR": 0,
              "Sf": 0.0, "Rf": 0.0, "hist": [],
              "pw": 0.0, "pa": 0.0,          # cumulative pressure points won/all
              "tbw": 0, "tbn": 0,            # cumulative tiebreaks won/played
              # serve DECOMPOSITION ratings (1st-in mean + 1stW/2ndW vs matching returns)
              "f1": 0.62, "nf1": 0,
              "S1": 0.0, "R1": 0.0, "nS1": 0, "nR1": 0,
              "S2": 0.0, "R2": 0.0, "nS2": 0, "nR2": 0}
        state[slug] = st
    return st


def nsets_of(score):
    if not isinstance(score, str) or not score.strip():
        return 2.0
    return float(sum(1 for tok in score.split() if "-" in tok)) or 2.0


def tb_count(score):
    """(tb_won, tb_played) for the row's PLAYER from the score string: '7-6(5)' won,
    '6-7(3)' lost (player's games listed first)."""
    if not isinstance(score, str):
        return 0, 0
    w = p9 = 0
    for tok in score.split():
        t9 = tok.split("(")[0]
        if t9 == "7-6":
            w += 1; p9 += 1
        elif t9 == "6-7":
            p9 += 1
    return w, p9


def is_ret(score):
    return 1.0 if (isinstance(score, str) and ("ret" in score.lower() or "w/o" in score.lower() or "wo" == score.strip().lower())) else 0.0


def load_feats(st, date):
    """(rest_days, matches_last7, excess_sets_last7) strictly from PRIOR matches."""
    h = st["hist"]
    if not h:
        return 99.0, 0.0, 0.0, 0.0
    rest = (date - h[-1][0]).days
    m7 = [x for x in h if (date - x[0]).days <= 7]
    ret5 = sum(x[2] for x in h[-5:])
    return (float(min(rest, 99)), float(len(m7)),
            float(sum(x[1] for x in m7) - 2.0 * len(m7)), float(ret5))


base = {"hard": BASE0, "clay": 0.60, "grass": 0.63}
base1 = {"hard": 0.67, "clay": 0.655, "grass": 0.685}   # 1st-serve points won
base2 = {"hard": 0.49, "clay": 0.48, "grass": 0.50}     # 2nd-serve points won
tsp = {}            # tournament -> [spw-deviation sum, n]  (as-of court speed)
bn = {"hard": 200.0, "clay": 200.0, "grass": 200.0}
AF = 0.12                       # fast half-life ~5-6 matches
rows = []
for t in m.itertuples(index=False):
    a, b = get(t.player_slug), get(t.rival_slugname)
    s = t.surf
    bs = base[s]
    # pre-match predictions
    wa = a["ns"][s] / (a["ns"][s] + 20.0)
    wb = b["ns"][s] / (b["ns"][s] + 20.0)
    elo_a = 0.7 * a["elo"] + 0.3 * (wa * a["elo_s"][s] + (1 - wa) * a["elo"])
    elo_b = 0.7 * b["elo"] + 0.3 * (wb * b["elo_s"][s] + (1 - wb) * b["elo"])
    p_elo = 1 / (1 + 10 ** ((elo_b - elo_a) / 400))
    Sa = 0.7 * a["S"] + 0.3 * a["Sf"]
    Ra = 0.7 * a["R"] + 0.3 * a["Rf"]
    Sb = 0.7 * b["S"] + 0.3 * b["Sf"]
    Rb = 0.7 * b["R"] + 0.3 * b["Rf"]
    rest_a, m7_a, ex_a, ret5_a = load_feats(a, t.date)
    rest_b, m7_b, ex_b, ret5_b = load_feats(b, t.date)
    # as-of EB-shrunk clutch (pressure-point delta vs 0.5) and tiebreak skill
    clutch_a = (a["pw"] + 25 * 0.5) / (a["pa"] + 25) - 0.5
    clutch_b = (b["pw"] + 25 * 0.5) / (b["pa"] + 25) - 0.5
    tbr_a = (a["tbw"] + 5 * 0.5) / (a["tbn"] + 5) - 0.5
    tbr_b = (b["tbw"] + 5 * 0.5) / (b["tbn"] + 5) - 0.5
    _tk = str(t.tournament or "").strip().lower()
    _td = tsp.get(_tk)
    tspeed = (_td[0] / _td[1]) if (_td and _td[1] >= 30) else 0.0
    pa_pt = rnd(bs + Sa - Rb + 0.5 * tspeed)
    pb_pt = rnd(bs + Sb - Ra + 0.5 * tspeed)
    # decomposed pre-match point estimates
    pa_dec = rnd(a["f1"] * (base1[s] + a["S1"] - b["R1"])
                 + (1 - a["f1"]) * (base2[s] + a["S2"] - b["R2"]) + 0.5 * tspeed)
    pb_dec = rnd(b["f1"] * (base1[s] + b["S1"] - a["R1"])
                 + (1 - b["f1"]) * (base2[s] + b["S2"] - a["R2"]) + 0.5 * tspeed)
    won = 1.0 if t.result == "Win" else 0.0
    priced = (pd.notna(t.player_odd) and pd.notna(t.rival_odd)
              and t.player_odd > 1.005 and t.rival_odd > 1.005)
    imp = np.nan
    if priced:
        i1, i2 = 1 / t.player_odd, 1 / t.rival_odd
        imp = i1 / (i1 + i2)
    spw_a = spw_from(t.first_serve_accuracy, t.first_serve_points, t.second_serve_points)
    spw_b = spw_rival(t.return_1st_serve_points, t.return_2nd_serve_points)
    rows.append((t.date, t.date.year, t.player_slug, t.rival_slugname, s,
                 elo_a, elo_b, p_elo, Sa, Ra, Sb, Rb,
                 a["nS"], b["nS"], pa_pt, pb_pt, imp, won, spw_a, spw_b,
                 float(t.player_odd) if priced else np.nan,
                 float(t.rival_odd) if priced else np.nan,
                 t.wom, t.lvlg, a["nR"], b["nR"], tspeed,
                 rest_a, m7_a, ex_a, rest_b, m7_b, ex_b, ret5_a, ret5_b,
                 clutch_a, clutch_b, tbr_a, tbr_b,
                 a["f1"], b["f1"], a["S1"], a["R1"], b["S1"], b["R1"],
                 a["S2"], a["R2"], b["S2"], b["R2"], pa_dec, pb_dec,
                 str(t.score or "")))
    # ---- updates ----
    K = 250.0 / (5 + a["n"]) + 5.0
    a["elo"] += K * (won - p_elo)
    K2 = 250.0 / (5 + b["n"]) + 5.0
    b["elo"] += K2 * ((1 - won) - (1 - p_elo))
    pse = 1 / (1 + 10 ** ((b["elo_s"][s] - a["elo_s"][s]) / 400))
    a["elo_s"][s] += (250.0 / (5 + a["ns"][s]) + 5.0) * (won - pse)
    b["elo_s"][s] += (250.0 / (5 + b["ns"][s]) + 5.0) * ((1 - won) - (1 - pse))
    a["n"] += 1; b["n"] += 1; a["ns"][s] += 1; b["ns"][s] += 1
    _ns9 = nsets_of(t.score)
    _rt9 = is_ret(t.score)
    # pressure + TB updates (player-perspective row updates a only; b's own rows
    # update b over time)
    for col_a, col_w in (("serve_pressure_all", "serve_pressure_won"),
                         ("return_pressure_all", "return_pressure_won")):
        _pa9 = getattr(t, col_a, None); _pw9 = getattr(t, col_w, None)
        try:
            if _pa9 is not None and _pw9 is not None and not (np.isnan(float(_pa9)) or np.isnan(float(_pw9))):
                if 0 <= float(_pw9) <= float(_pa9) <= 200:
                    a["pa"] += float(_pa9); a["pw"] += float(_pw9)
        except (TypeError, ValueError):
            pass
    _tw9, _tp9 = tb_count(t.score)
    a["tbw"] += _tw9; a["tbn"] += _tp9
    b["tbw"] += (_tp9 - _tw9); b["tbn"] += _tp9
    for st9 in (a, b):
        st9["hist"].append((t.date, _ns9, _rt9))
        if len(st9["hist"]) > 12:
            st9["hist"] = st9["hist"][-12:]
    # decomposition updates (direction A serves): targets from the row's own cols
    _fsa = pct(t.first_serve_accuracy)
    _fsp = pct(t.first_serve_points)
    _ssp = pct(t.second_serve_points)
    if not np.isnan(_fsa) and 0.35 <= _fsa <= 0.85:
        a["f1"] += (0.9 / (a["nf1"] + 8)) * (_fsa - a["f1"]); a["nf1"] += 1
    if not np.isnan(_fsp) and 0.35 <= _fsp <= 0.95:
        e1 = base1[s] + a["S1"] - b["R1"]
        a["S1"] += (0.8 / (a["nS1"] + 6)) * (_fsp - e1)
        b["R1"] -= (0.8 / (b["nR1"] + 6)) * (_fsp - e1)
        a["nS1"] += 1; b["nR1"] += 1
    if not np.isnan(_ssp) and 0.20 <= _ssp <= 0.85:
        e2 = base2[s] + a["S2"] - b["R2"]
        a["S2"] += (0.8 / (a["nS2"] + 6)) * (_ssp - e2)
        b["R2"] -= (0.8 / (b["nR2"] + 6)) * (_ssp - e2)
        a["nS2"] += 1; b["nR2"] += 1
    # direction B serves, implied from the row's return cols
    _r1 = pct(t.return_1st_serve_points)
    _r2 = pct(t.return_2nd_serve_points)
    if not np.isnan(_r1) and 0.05 <= _r1 <= 0.65:
        _fspb = 1 - _r1
        e1 = base1[s] + b["S1"] - a["R1"]
        b["S1"] += (0.8 / (b["nS1"] + 6)) * (_fspb - e1)
        a["R1"] -= (0.8 / (a["nR1"] + 6)) * (_fspb - e1)
        b["nS1"] += 1; a["nR1"] += 1
    if not np.isnan(_r2) and 0.15 <= _r2 <= 0.80:
        _sspb = 1 - _r2
        e2 = base2[s] + b["S2"] - a["R2"]
        b["S2"] += (0.8 / (b["nS2"] + 6)) * (_sspb - e2)
        a["R2"] -= (0.8 / (a["nR2"] + 6)) * (_sspb - e2)
        b["nS2"] += 1; a["nR2"] += 1
    if not np.isnan(spw_a):
        _td = tsp.setdefault(_tk, [0.0, 0])
        _td[0] += spw_a - bs; _td[1] += 1
        e = bs + a["S"] - b["R"]
        err = spw_a - e
        a["S"] += (0.8 / (a["nS"] + 6)) * err
        b["R"] -= (0.8 / (b["nR"] + 6)) * err
        a["Sf"] += AF * (spw_a - (bs + a["Sf"] - b["R"]))
        a["nS"] += 1; b["nR"] += 1
        base[s] += (spw_a - base[s]) / bn[s]
        bn[s] = min(bn[s] + 1, 5000)
    if not np.isnan(spw_b):
        _td = tsp.setdefault(_tk, [0.0, 0])
        _td[0] += spw_b - bs; _td[1] += 1
        e = bs + b["S"] - a["R"]
        err = spw_b - e
        b["S"] += (0.8 / (b["nS"] + 6)) * err
        a["R"] -= (0.8 / (a["nR"] + 6)) * err
        b["Sf"] += AF * (spw_b - (bs + b["Sf"] - a["R"]))
        b["nS"] += 1; a["nR"] += 1

F = pd.DataFrame(rows, columns=["date", "year", "a", "b", "surf", "elo_a", "elo_b",
                                "p_elo", "S_a", "R_a", "S_b", "R_b", "nS_a", "nS_b",
                                "pa_pt", "pb_pt", "imp", "won", "spw_a", "spw_b",
                                "odd_a", "odd_b", "wom", "lvlg", "nR_a", "nR_b",
                                "tspeed",
                                "rest_a", "m7_a", "ex_a", "rest_b", "m7_b", "ex_b",
                                "ret5_a", "ret5_b",
                                "clutch_a", "clutch_b", "tbr_a", "tbr_b",
                                "f1_a", "f1_b", "S1_a", "R1_a", "S1_b", "R1_b",
                                "S2_a", "R2_a", "S2_b", "R2_b", "pa_dec", "pb_dec",
                                "score"])
F.to_parquet("data_cache/_mc2_features.parquet")
# live production state (2026-10-08): final per-player ratings for tennis_mc2.py
import pickle
with open("data_cache/_mc2_state.pkl", "wb") as f9:
    pickle.dump({"players": state, "base": base, "base1": base1, "base2": base2,
                 "tsp": {k: v for k, v in tsp.items() if v[1] >= 30}}, f9)
print(f"live state saved: {len(state)} players", flush=True)
print(f"feature table: {len(F)} matches -> data_cache/_mc2_features.parquet", flush=True)

# Markov match prob from adjusted point probs
F["p_mkv"] = [p_match_bo3(pa, pb) for pa, pb in zip(F["pa_pt"], F["pb_pt"])]
sc = F[(F["year"] >= 2024) & F["imp"].notna() & (F["nS_a"] >= 8) & (F["nS_b"] >= 8)]
from sklearn.metrics import roc_auc_score, log_loss
print(f"scored (priced, 8+ serve-rated matches both): {len(sc)}")
for yr in (2024, 2025, 2026, None):
    g = sc if yr is None else sc[sc["year"] == yr]
    if len(g) < 500:
        continue
    out = [str(yr or 'ALL'), f"n={len(g)}"]
    for col, name in (("p_elo", "Elo"), ("p_mkv", "Markov"), ("imp", "Market")):
        y = g["won"]
        p = np.clip(g[col], 1e-6, 1 - 1e-6)
        out.append(f"{name} AUC {roc_auc_score(y, p):.4f} LL {log_loss(y, p):.4f}")
    p = np.clip(0.5 * g["p_elo"] + 0.5 * g["p_mkv"], 1e-6, 1 - 1e-6)
    out.append(f"Elo+Mkv AUC {roc_auc_score(g['won'], p):.4f} LL {log_loss(g['won'], p):.4f}")
    print(" | ".join(out), flush=True)
