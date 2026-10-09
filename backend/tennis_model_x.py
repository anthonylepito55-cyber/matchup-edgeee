"""MODEL X — the self-auditing meta-model (2026-10-03, user ask: "analyse every win/loss
on ended games, retrain daily, and if you catch info we had but didn't use, add it").

Model X is a STACKER over the frozen prediction log: it learns, from every settled game,
how much to trust each of A/B/C/D + their gray heads + the market + the Monte Carlos, and
how surface / league / round / price / model-disagreement shift the true odds. Every input
is a value ALREADY FROZEN in the log at first serve, so there is no as-of reconstruction and
no leakage (the discipline that the EWMA + stale-cache disasters taught -- see memory).

"Add what we missed" = a nightly CANDIDATE-DISCOVERY pass: each extra frozen signal not yet
in the model is tested by WALK-FORWARD out-of-sample log-loss; a candidate is AUTO-ADDED only
if it clears a strict gate (meaningful OOS improvement, no ROI harm, enough sample), and every
add/reject is written to an audit log. Non-core features already active are re-checked each
night and DROPPED if they stop helping -- so an overfit add cannot silently persist.

Serving model = L2 logistic regression (a stacker on ~hundreds of rows must stay simple;
XGB overfits here). Display-only until it earns a forward record, like everything else."""
import os
import json
import time
import numpy as np
import pandas as pd
import joblib

_here = os.path.dirname(os.path.abspath(__file__))
ARTIFACT_X = os.path.join(_here, "model_artifacts", "tennis_model_x.joblib")
META_X = os.path.join(_here, "model_artifacts", "tennis_model_x_meta.json")

# NO MARKET INPUTS (2026-10-09, user "I want the market price to be removed from x"):
# live, the market-fed X copied the price (picked the favourite 95% of the time) and was
# slightly WORSE than the market on accuracy/Brier/logloss (forward n=347, ROI -10.1%).
# Removed: the market itself, every model-minus-market spread, the dog flag, AND the gray
# heads (C-MA / D-MA / A-MA / B-MA), because those are models blended with the market and
# would carry the price straight back in. The market is still computed, but only as the
# BENCHMARK X has to beat (wf_market_logloss) and for ROI/edge display -- never an input.
# CORE = always active: the edge model (C) + Model D.
CORE = ["c_lg", "d_lg"]
# CANDIDATE pool: market-free signals only. The nightly pass auto-adds any that clear the
# walk-forward gate.
CANDIDATES = ["a_lg", "b_lg", "mc_lg", "mcc_lg", "mc75_lg", "mcutr_lg",
              "spread_a_c", "spread_mcc_c",
              "is_wta", "is_chal", "is_itf", "is_clay", "is_grass",
              "rd_late", "rd_early"]
ALL_FEATS = CORE + CANDIDATES

# auto-add gate
_MIN_OOS = 150        # need at least this many walk-forward OOS rows to trust a comparison
_MIN_LL_GAIN = 0.003  # candidate must cut OOS log-loss by at least this
_CACHE = {"mtime": None, "model": None, "meta": None}


def _lg(p):
    p = np.clip(np.asarray(p, dtype=float), 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p))


def _dec(a):
    try:
        a = float(a)
    except (TypeError, ValueError):
        return None
    if a == 0:
        return None
    return 1 + a / 100.0 if a > 0 else 1 + 100.0 / abs(a)


def build_features(d):
    """Full feature dict from a flat row (log row or live card normalised to flat keys).
    Missing model probs are imputed as a coin flip (logit 0) -- NOT the market, which X
    must never see as an input; spreads/flags default 0."""
    mkt = d.get("market_p1")
    mkt = 0.5 if mkt is None else min(max(float(mkt), 1e-6), 1 - 1e-6)
    mlg = float(_lg(mkt))

    def plg(key):
        v = d.get(key)
        return float(_lg(min(max(float(v), 1e-6), 1 - 1e-6))) if v is not None else 0.0

    c, cma, dd, dma = plg("c_p1"), plg("cma_p1"), plg("d_p1"), plg("dma_p1")
    a, b, ama, bma = plg("a_p1"), plg("b_p1"), plg("ama_p1"), plg("bma_p1")
    mc, mcc, mc75, mcutr = plg("mc_p1"), plg("mcc_p1"), plg("mc75_p1"), plg("mcutr_p1")
    lg = str(d.get("league") or "").lower()
    sf = str(d.get("surface") or "").lower()
    rd = str(d.get("round") or "").lower()
    return {
        "mkt_lg": mlg, "c_lg": c, "cma_lg": cma, "d_lg": dd, "dma_lg": dma,
        "a_lg": a, "b_lg": b, "ama_lg": ama, "bma_lg": bma,
        "mc_lg": mc, "mcc_lg": mcc, "mc75_lg": mc75, "mcutr_lg": mcutr,
        "spread_c_mkt": c - mlg, "spread_d_mkt": dd - mlg, "spread_a_c": a - c,
        "spread_cma_mkt": cma - mlg, "spread_mcc_c": mcc - c,
        "is_wta": 1.0 if lg == "wta" else 0.0,
        "is_chal": 1.0 if "challenger" in lg else 0.0,
        "is_itf": 1.0 if "itf" in lg else 0.0,
        "is_clay": 1.0 if "clay" in sf else 0.0,
        "is_grass": 1.0 if "grass" in sf else 0.0,
        "rd_late": 1.0 if any(k in rd for k in ("final", "semi", "quarter")) else 0.0,
        "rd_early": 1.0 if any(k in rd for k in ("1st", "qual", "128", "of 64")) else 0.0,
        "dog_mkt": 1.0 if mkt < 0.5 else 0.0,
    }


def _flat_from_log(r):
    g = lambda k: (float(r[k]) if (k in r and pd.notna(r[k])) else None)  # noqa: E731
    d1, d2 = _dec(r.get("p1_odds")), _dec(r.get("p2_odds"))
    mkt = None
    if d1 and d2:
        i1, i2 = 1 / d1, 1 / d2
        mkt = i1 / (i1 + i2)
    return {
        "market_p1": mkt, "c_p1": g("model_c_p1"), "cma_p1": g("model_cma_p1"),
        "d_p1": g("model_d_p1"), "dma_p1": g("model_dma_p1"),
        "a_p1": g("model_a_p1"), "b_p1": g("model_b_p1"),
        "ama_p1": g("model_ama_p1"), "bma_p1": g("model_bma_p1"),
        "mc_p1": g("mc_p1"), "mcc_p1": g("mc_c_p1"), "mc75_p1": g("mc_c75_p1"),
        "mcutr_p1": g("mc_cutr_p1"), "surface": r.get("surface"),
        "league": r.get("league"), "round": r.get("round"),
        "_o1": d1, "_o2": d2,
    }


def _prep(log):
    s = log[(log["settled"] == True) & log["p1_won"].notna()  # noqa: E712
            & log["model_c_p1"].notna() & log["p1_odds"].notna()
            & log["p2_odds"].notna()].copy()
    if s.empty:
        return pd.DataFrame()
    s = s.sort_values("date")
    rows = []
    for _, r in s.iterrows():
        fl = _flat_from_log(r)
        if not fl["_o1"] or not fl["_o2"]:
            continue
        f = build_features(fl)
        f["_y"] = int(bool(r["p1_won"]))
        f["_date"] = str(r.get("date") or "")
        f["_o1"], f["_o2"] = fl["_o1"], fl["_o2"]
        rows.append(f)
    return pd.DataFrame(rows)


def _fit(X, y):
    from sklearn.linear_model import LogisticRegression
    return LogisticRegression(max_iter=3000, C=0.3).fit(X, y)


def _wf(df, feats, n_blocks=5):
    """Expanding walk-forward OOS: split by date into blocks; predict each block from all
    prior. Returns (mean_logloss, flat_roi, n_oos). ROI = $1 on Model X's side at the odds."""
    from sklearn.linear_model import LogisticRegression
    if len(df) < 60:
        return None
    df = df.reset_index(drop=True)
    cuts = np.linspace(0, len(df), n_blocks + 1, dtype=int)
    yoos, poos, roi = [], [], []
    for i in range(1, n_blocks):
        tr = df.iloc[:cuts[i]]
        te = df.iloc[cuts[i]:cuts[i + 1]]
        if len(te) == 0 or tr["_y"].nunique() < 2:
            continue
        m = LogisticRegression(max_iter=3000, C=0.3).fit(tr[feats], tr["_y"])
        p = m.predict_proba(te[feats])[:, 1]
        for pi, yi, o1, o2 in zip(p, te["_y"].values, te["_o1"].values, te["_o2"].values):
            yoos.append(int(yi))
            poos.append(float(pi))
            side1 = pi >= 0.5
            o = o1 if side1 else o2
            roi.append((o - 1) if (side1 == bool(yi)) else -1.0)
    if len(yoos) < 30:
        return None
    pa = np.clip(np.array(poos), 1e-6, 1 - 1e-6)
    ya = np.array(yoos)
    ll = float(-np.mean(ya * np.log(pa) + (1 - ya) * np.log(1 - pa)))
    return ll, (100.0 * float(np.mean(roi)) if roi else 0.0), len(yoos)


def discover_and_train(log=None, verbose=True):
    """Nightly: walk-forward candidate discovery (auto-add passers, drop stale adds), then
    fit the serving stacker on all settled rows. Writes the artifact + an audit meta file."""
    if log is None:
        import tennis_log
        log = tennis_log._read_log()
    df = _prep(log)
    if len(df) < 80:
        meta = {"trained_at": time.strftime("%Y-%m-%d %H:%M"), "n": int(len(df)),
                "status": "insufficient_data (need 80+ settled)", "active": CORE}
        _save_meta(meta)
        return meta

    # market-only baseline (the number to beat)
    mkt_ll = _wf(df, ["mkt_lg"])
    base = _wf(df, CORE)
    active = list(CORE)
    audit = []
    if base:
        cur_ll = base[0]
        # GREEDY auto-add: test each candidate; keep if it clears the gate.
        for cand in CANDIDATES:
            trial = _wf(df, active + [cand])
            if not trial:
                audit.append({"cand": cand, "decision": "skip", "reason": "wf_none"})
                continue
            gain = cur_ll - trial[0]
            roi_ok = trial[1] >= (base[1] - 1.0)  # don't let a feature tank ROI
            if trial[2] >= _MIN_OOS and gain >= _MIN_LL_GAIN and roi_ok:
                active.append(cand)
                audit.append({"cand": cand, "decision": "ADD", "ll_gain": round(gain, 4),
                              "oos_roi": round(trial[1], 1), "n_oos": trial[2]})
                cur_ll = trial[0]
            else:
                audit.append({"cand": cand, "decision": "reject",
                              "ll_gain": round(gain, 4), "oos_roi": round(trial[1], 1),
                              "n_oos": trial[2]})
        final = _wf(df, active)
    else:
        final = None

    X, y = df[active], df["_y"]
    model = _fit(X, y)
    joblib.dump({"model": model, "features": active,
                 "trained_at": time.strftime("%Y-%m-%d %H:%M"), "n": int(len(df))}, ARTIFACT_X)
    meta = {
        "trained_at": time.strftime("%Y-%m-%d %H:%M"), "n": int(len(df)),
        "active": active, "core": CORE,
        "added": [a["cand"] for a in audit if a["decision"] == "ADD"],
        "wf_market_logloss": round(mkt_ll[0], 4) if mkt_ll else None,
        "wf_core_logloss": round(base[0], 4) if base else None,
        "wf_final_logloss": round(final[0], 4) if final else None,
        "wf_final_roi_pct": round(final[1], 1) if final else None,
        "wf_final_n": final[2] if final else None,
        "audit": audit,
    }
    _save_meta(meta)
    if verbose:
        print(f"[model_x] n={len(df)} active={active}")
        print(f"[model_x] wf logloss market={meta['wf_market_logloss']} "
              f"core={meta['wf_core_logloss']} final={meta['wf_final_logloss']} "
              f"roi={meta['wf_final_roi_pct']}% (n_oos={meta['wf_final_n']})")
        print(f"[model_x] auto-added: {meta['added'] or 'none'}")
    return meta


def backfill_history(log=None, save=True, min_train=80):
    """Apply Model X to PAST settled games (user ask 2026-10-03) the honest way: expanding
    WALK-FORWARD — each past game is predicted by a model trained ONLY on games with an
    earlier date (no in-sample inflation, leakage-safe). Flags them model_x_recon=True so
    they show in the history/post-mortems but are EXCLUDED from the forward lanes. Never
    overwrites a genuine forward pick (one already frozen with recon False)."""
    import tennis_log
    from sklearn.linear_model import LogisticRegression
    if log is None:
        log = tennis_log._read_log()
    meta = get_meta()
    active = (meta or {}).get("active") or CORE
    s = log[(log["settled"] == True) & log["p1_won"].notna()  # noqa: E712
            & log["model_c_p1"].notna() & log["p1_odds"].notna()
            & log["p2_odds"].notna()].copy().sort_values("date")
    rows = []
    for i, r in s.iterrows():
        fl = _flat_from_log(r)
        if not fl["_o1"] or not fl["_o2"]:
            continue
        f = build_features(fl)
        f["_y"] = int(bool(r["p1_won"]))
        f["_date"] = str(r.get("date") or "")
        f["_idx"] = i
        rows.append(f)
    if not rows:
        return {"backfilled": 0}
    df = pd.DataFrame(rows)
    preds = {}
    for d in sorted(df["_date"].unique()):
        tr = df[df["_date"] < d]
        te = df[df["_date"] == d]
        if len(tr) < min_train or tr["_y"].nunique() < 2:
            continue
        m = LogisticRegression(max_iter=3000, C=0.3).fit(tr[active], tr["_y"])
        p = m.predict_proba(te[active])[:, 1]
        for idx, pi in zip(te["_idx"].values, p):
            preds[idx] = float(pi)
    if "model_x_recon" not in log.columns:
        log["model_x_recon"] = False
    n = 0
    for idx, pi in preds.items():
        cur = log.at[idx, "model_x_p1"]
        reconflag = log.at[idx, "model_x_recon"] if "model_x_recon" in log.columns else None
        # only fill rows that have no Model X yet, or are already reconstructed (refresh them)
        if pd.isna(cur) or (pd.notna(reconflag) and bool(reconflag)):
            log.at[idx, "model_x_p1"] = round(pi, 4)
            log.at[idx, "model_x_recon"] = True
            n += 1
    if save:
        tennis_log._write_log(log)
    return {"backfilled": n, "covered": len(preds), "settled": int(len(df))}


def _save_meta(meta):
    os.makedirs(os.path.dirname(META_X), exist_ok=True)
    with open(META_X, "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=2)


def _load():
    if not os.path.exists(ARTIFACT_X):
        return None
    mt = os.path.getmtime(ARTIFACT_X)
    if _CACHE["mtime"] != mt:
        _CACHE["model"] = joblib.load(ARTIFACT_X)
        _CACHE["mtime"] = mt
    return _CACHE["model"]


def get_meta():
    if os.path.exists(META_X):
        try:
            with open(META_X, encoding="utf-8") as fh:
                return json.load(fh)
        except (OSError, ValueError):
            return None
    return None


def predict_x(flat):
    """flat = dict with market_p1 + the model probs (c_p1, d_p1, ...) + surface/league/round.
    Returns {p1_prob, p2_prob, edge_p1, features_used} or None if Model X isn't trained."""
    art = _load()
    if not art:
        return None
    f = build_features(flat)
    X = np.array([[f.get(k, 0.0) for k in art["features"]]])
    p1 = float(art["model"].predict_proba(X)[0, 1])
    out = {"p1_prob": round(p1, 4), "p2_prob": round(1 - p1, 4),
           "trained_at": art.get("trained_at"), "n_train": art.get("n")}
    mk = flat.get("market_p1")
    if mk is not None:
        out["market_p1"] = round(float(mk), 4)
        out["edge_p1"] = round(p1 - float(mk), 4)
    return out


def analyze_game(row):
    """Per-game WIN/LOSS post-mortem from the frozen log row. For each signal: its pick, the
    actual winner, hit/miss. 'missed' = signals that DID point to the real winner while the
    market favorite (what the price implied) did not -- i.e. info we had that went unrewarded."""
    if pd.isna(row.get("p1_won")):
        return None
    fl = _flat_from_log(row)
    won1 = bool(row["p1_won"])
    mk = fl["market_p1"]
    sigs = {"market": mk, "A": fl["a_p1"], "B": fl["b_p1"], "C": fl["c_p1"],
            "gray": fl["cma_p1"], "D": fl["d_p1"], "C-MC": fl["mcc_p1"],
            "cUTR": fl["mcutr_p1"]}
    # prefer the FROZEN Model X value (walk-forward / forward pick) over an in-sample
    # re-prediction, so post-mortems on past games aren't inflated by hindsight.
    xv = row.get("model_x_p1")
    if pd.notna(xv):
        sigs["Model X"] = float(xv)
    else:
        xp = predict_x(fl)
        if xp:
            sigs["Model X"] = xp["p1_prob"]
    out = []
    mkt_side1 = (mk is not None and mk >= 0.5)
    for name, p in sigs.items():
        if p is None:
            continue
        side1 = p >= 0.5
        out.append({"signal": name, "pick": 1 if side1 else 2,
                    "pct": round(p * 100, 1), "hit": bool(side1 == won1)})
    # missed info: signals that beat the market's call (right when the price's favorite lost)
    missed = []
    if mk is not None and mkt_side1 != won1:  # the market favorite LOST
        for s in out:
            if s["signal"] not in ("market",) and s["hit"]:
                missed.append(s["signal"])
    return {"won_player": 1 if won1 else 2, "market_right": bool(mkt_side1 == won1),
            "signals": out, "missed_info": missed}
