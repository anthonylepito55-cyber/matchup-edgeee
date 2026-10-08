"""Tennis forward record (2026-09-06): freeze -> settle -> track record.

Tennis predictions were served for two months with NO ledger -- computed daily, displayed,
never frozen, never graded. This module gives tennis the same discipline as the MLB log:
each match's prediction and odds are UPSERTED until first serve and frozen after it,
settled from OpticOdds completed-fixture results (set totals), and served as a real
forward track record. Started 2026-09-06 -- the record begins now, empty, honestly.
"""
import json
import os
from datetime import datetime, timezone

import pandas as pd
import requests

from tennis_data import OPTICODDS_API_KEY, OPTICODDS_BASE_URL, TENNIS_LEAGUES, CACHE_DIR

LOG_PATH = os.path.join(CACHE_DIR, "tennis_prediction_log.parquet")

COLUMNS = ["date", "fixture_id", "league", "tournament", "round", "player_1", "player_2",
           "start_time_utc", "surface", "best_of_5", "p1_win_prob", "p1_odds", "p2_odds",
           "bookmaker", "logged_at", "settled", "p1_won", "sr_dog", "sos",
           "model_a_p1", "model_b_p1", "model_c_p1", "model_cma_p1",
           "model_ama_p1", "model_bma_p1", "model_d_p1", "model_dma_p1", "mc_p1", "mc_c_p1",
           "mc_c75_p1", "mc_cutr_p1", "mc_c_recon", "model_x_p1", "model_x_recon", "score",
           "h2h_n", "h2h_p1w", "h2h_p2w", "h2h_sn", "h2h_sp1w",
           # PURE-RESULTS FORM overlay (2026-10-06): p1 form minus p2 form, quality- +
           # competitiveness-adjusted last-10-on-surface, NO serve stats. Frozen at first
           # serve; feeds the contrarian pf_c75_* lanes. See tennis_pure_form.py.
           "pf_edge_p1",
           # REAL UTR (2026-10-07): utr_edge_p1 = p1 singlesUtr - p2 singlesUtr (UTR's own
           # public API, current ratings only -> FORWARD tracker, never retro-tested);
           # utr_mom_p1 = (p1 3mo-vs-level) - (p2 3mo-vs-level) = who's running hotter
           # than their established rating. See utr_data.py.
           "utr_edge_p1", "utr_mom_p1"]


def _read_log() -> pd.DataFrame:
    if os.path.exists(LOG_PATH):
        df = pd.read_parquet(LOG_PATH)
        for c in COLUMNS:
            if c not in df.columns:
                df[c] = None
        return df
    return pd.DataFrame(columns=COLUMNS)


def _write_log(df: pd.DataFrame):
    tmp = LOG_PATH + ".tmp"
    df.to_parquet(tmp)
    os.replace(tmp, LOG_PATH)


def _started(start_time_utc) -> bool:
    try:
        st = pd.Timestamp(start_time_utc)
        if st.tzinfo is None:
            st = st.tz_localize("UTC")
        return datetime.now(timezone.utc) >= st
    except Exception:
        return False


def log_predictions(matches: list, date: str):
    """Upsert today's predicted matches. A row updates freely until first serve and is
    FROZEN afterward (same freeze rule as the MLB log). Only matches carrying both a
    prediction and live odds are logged -- a record row must be gradeable and priced."""
    rows = []
    now = datetime.now(timezone.utc).isoformat()
    for m in matches:
        pred = m.get("prediction") or {}
        odds = m.get("live_odds") or {}
        ma = m.get("model_a") or {}
        mb = m.get("model_b") or {}
        mc = m.get("model_c") or {}
        md = m.get("model_d") or {}
        mx = m.get("model_x") or {}
        has_flag = m.get("sr_dog") in ("p1", "p2") or m.get("sos") in ("p1", "p2")
        has_ab = ma.get("p1_prob") is not None and mb.get("p1_prob") is not None
        if odds.get("player_1") is None or odds.get("player_2") is None:
            continue
        if pred.get("player_1_win_prob") is None and not has_flag and not has_ab:
            continue  # a row must be gradeable for SOMETHING: a pick, a flag, or the A/B pair
        if not m.get("fixture_id"):
            continue
        # CLOSING-LINE ONLY (2026-10-07, Tarvet case): never upsert from a match that is no
        # longer "unplayed" -- Polymarket trades in-play, and a match that starts EARLY (or a
        # postponed one with a stale schedule) would otherwise write a live price into the
        # ledger as if it were pre-match. Existing rows stay as logged (= the closing line);
        # a match first seen live simply never gets a priced row (no closing line exists).
        if (m.get("status") or "unplayed") != "unplayed":
            continue
        rows.append({
            "date": date, "fixture_id": m["fixture_id"], "league": m.get("league"),
            "tournament": m.get("tournament"), "round": m.get("round"),
            "player_1": m.get("player_1"), "player_2": m.get("player_2"),
            "start_time_utc": m.get("start_time_utc"), "surface": m.get("surface"),
            "best_of_5": bool(m.get("best_of_5")),
            "p1_win_prob": float(pred["player_1_win_prob"]) if pred.get("player_1_win_prob") is not None else None,
            "p1_odds": odds.get("player_1"), "p2_odds": odds.get("player_2"),
            "bookmaker": odds.get("bookmaker"), "logged_at": now, "settled": False, "p1_won": None,
            "sr_dog": m.get("sr_dog"), "sos": m.get("sos"),
            "model_a_p1": ma.get("p1_prob"), "model_b_p1": mb.get("p1_prob"),
            "model_c_p1": mc.get("p1_prob"),
            "model_cma_p1": mc.get("market_aware_p1"),
            "model_ama_p1": ma.get("market_aware_p1"), "model_bma_p1": mb.get("market_aware_p1"),
            "model_d_p1": md.get("p1_prob"), "model_dma_p1": md.get("market_aware_p1"),
            # Monte Carlo pick (2026-10-01, user "track how the MC does under $25"):
            # frozen as p1's win fraction over the sims. mc_p1 = the Model-D serve MC
            # (sUTR-anchored); mc_c_p1 = the Model-C-anchored MC (2026-10-02, user "track
            # all monte carlo c picks + how it does agreeing with model d monte carlo").
            "mc_p1": ((md.get("mc") or {}).get("p1_pct") / 100.0
                      if (md.get("mc") or {}).get("p1_pct") is not None else None),
            "mc_c_p1": ((mc.get("mc") or {}).get("p1_pct") / 100.0
                        if (mc.get("mc") or {}).get("p1_pct") is not None else None),
            # invisible C-MC variants tracked head-to-head vs mc_c_p1 (the visible c50):
            # c75 = harder C anchor; cutr = C anchor + stronger sUTR de-padding.
            "mc_c75_p1": mc.get("mc_c75_p1"),
            "mc_cutr_p1": mc.get("mc_cutr_p1"),
            # False = a genuine forward C-MC pick (counts in the tracking lanes); True is
            # set only by the one-time historical reconstruction (display in results-history
            # but excluded from the forward lanes, per forward-tests-only discipline).
            "mc_c_recon": False,
            # FROZEN as-of H2H (2026-10-04, user ask): the pair's head-to-head AS IT WAS at
            # first serve, from Model A's live-computed h2h. Frozen so results-history shows
            # the true as-of record, not a current one that may include later meetings.
            "h2h_n": (ma.get("h2h") or {}).get("n") if ma.get("h2h") else None,
            "h2h_p1w": (ma.get("h2h") or {}).get("p1_wins") if ma.get("h2h") else None,
            "h2h_p2w": (ma.get("h2h") or {}).get("p2_wins") if ma.get("h2h") else None,
            "h2h_sn": (ma.get("h2h") or {}).get("surface_n") if ma.get("h2h") else None,
            "h2h_sp1w": (ma.get("h2h") or {}).get("surface_p1_wins") if ma.get("h2h") else None,
            # Model X (2026-10-03): the meta-model's frozen p1 win prob. recon=False = a
            # genuine forward pick (counts in the lanes); True = walk-forward backfill of a
            # past game (display/post-mortem only, excluded from the forward lanes).
            "model_x_p1": mx.get("p1_prob"),
            "model_x_recon": False,
            # PURE-RESULTS FORM edge (2026-10-06): p1 minus p2 quality-adjusted L10-on-
            # surface form. Frozen like the models; drives the contrarian pf_c75_* lanes.
            "pf_edge_p1": (m.get("pure_form") or {}).get("edge"),
            # REAL UTR (2026-10-07): frozen at log time, forward lanes only (utr_data.py).
            "utr_edge_p1": (m.get("utr") or {}).get("edge"),
            "utr_mom_p1": (m.get("utr") or {}).get("mom"),
        })
    log = _read_log()
    # SELF-HEALING EARLY START (2026-10-07, Tarvet case): a match seen LIVE/completed while
    # its logged start is still in the future (PM lists a resumption time, or the schedule is
    # wrong) would stay upsertable -- pull its start back to now so the row freezes with the
    # closing line it already holds. Suspended matches then can't re-log an in-play price.
    if not log.empty:
        _live_now = {m.get("fixture_id") for m in matches
                     if m.get("fixture_id") and (m.get("status") or "unplayed") != "unplayed"}
        _heal = log["fixture_id"].isin(_live_now) & (log["settled"] != True) \
            & ~log["start_time_utc"].apply(_started)  # noqa: E712
        if _heal.any():
            log.loc[_heal, "start_time_utc"] = now
            _write_log(log)
            print(f"[tennis log] froze {int(_heal.sum())} early-started rows (live before listed start)")
    if not rows:
        return
    new = pd.DataFrame(rows)
    if log.empty:
        _write_log(new)
        return
    frozen_ids = set(log[(log["settled"] == True) | log["start_time_utc"].apply(_started)]["fixture_id"])  # noqa: E712
    new = new[~new["fixture_id"].isin(frozen_ids)]
    if new.empty:
        return
    keep = log[~log["fixture_id"].isin(set(new["fixture_id"]))]
    _write_log(pd.concat([keep, new], ignore_index=True))


def settle(max_dates: int = 10):
    """Fill winners for unsettled rows whose match has started, from OpticOdds completed
    fixtures (result.scores.*.total = sets won; player_1 is the home competitor). Falls back
    to Polymarket's resolved markets + per-set score for pm_-prefixed rows when OpticOdds is
    down (2026-10-06)."""
    log = _read_log()
    if log.empty:
        return
    todo = log[(log["settled"] != True) & log["start_time_utc"].apply(_started)]  # noqa: E712
    if todo.empty:
        return
    changed = False
    for date in sorted(todo["date"].unique())[-max_dates:]:
        try:
            # settle had the SAME un-paginated 100-fixture cap the slate fetch had (fixed
            # 2026-09-28) -- reuse the cursor-paginated fetch so nothing stays unsettled.
            from tennis_data import _fetch_tennis_fixtures
            fixtures = _fetch_tennis_fixtures(date)
        except Exception:  # noqa: BLE001
            continue
        for f in fixtures:
            if f.get("status") != "completed":
                continue
            scores = ((f.get("result") or {}).get("scores") or {})
            hs, as_ = (scores.get("home") or {}), (scores.get("away") or {})
            h, a = hs.get("total"), as_.get("total")
            if h is None or a is None or h == a:
                continue
            # per-set games from periods -> "6-4 6-2" (player_1 = home) for score-level
            # stats (set-2-winner, blowouts) -- user "watch the scores" 2026-10-04.
            hp, ap = (hs.get("periods") or {}), (as_.get("periods") or {})
            sets = []
            for k in sorted(set(hp) | set(ap)):
                hv, av = hp.get(k), ap.get(k)
                if hv is not None and av is not None:
                    sets.append(f"{hv}-{av}")
            score_str = " ".join(sets) if sets else None
            m = log["fixture_id"] == f.get("id")
            if not m.any():
                continue
            if not bool(log.loc[m, "settled"].iloc[0]):
                log.loc[m, "p1_won"] = bool(h > a)
                log.loc[m, "settled"] = True
                if score_str:
                    log.loc[m, "score"] = score_str
                changed = True
            elif score_str and (log.loc[m, "score"].isna().iloc[0]
                                 or not str(log.loc[m, "score"].iloc[0])):
                # backfill score on an already-settled row that predates score capture
                log.loc[m, "score"] = score_str
                changed = True
    # POLYMARKET fallback (2026-10-06): settle pm_-prefixed rows from Polymarket's resolved
    # markets (+ full per-set score) when OpticOdds returned no completed fixtures.
    try:
        import polymarket_data
        pm = polymarket_data.pm_results()
    except Exception as e:  # noqa: BLE001
        pm = {}
        print(f"[polymarket fallback] results failed: {e}")
    for fid, r in (pm or {}).items():
        m = log["fixture_id"] == fid
        if not m.any():
            continue
        if not bool(log.loc[m, "settled"].iloc[0]) and r.get("p1_won") is not None:
            log.loc[m, "p1_won"] = bool(r["p1_won"])
            log.loc[m, "settled"] = True
            if r.get("score"):
                log.loc[m, "score"] = r["score"]
            changed = True
        elif r.get("score") and (log.loc[m, "score"].isna().iloc[0]
                                 or not str(log.loc[m, "score"].iloc[0])):
            log.loc[m, "score"] = r["score"]
            changed = True
    if changed:
        _write_log(log)


def _decimal(am) -> float | None:
    try:
        am = float(am)
    except (TypeError, ValueError):
        return None
    return 1 + am / 100 if am > 0 else 1 + 100 / abs(am)


def _postmortem(row):
    """Model X win/loss post-mortem for one settled row (lazy import; never fatal)."""
    try:
        import tennis_model_x as _tmx
        return _tmx.analyze_game(row)
    except Exception:  # noqa: BLE001
        return None


def _elite_signals_for_row(r, mk1):
    """Which of the board's elite lane-signals a FINISHED game fired, with side + hit --
    computed from the FROZEN probability columns only (2026-10-05, user "update previous
    games with the new signals so i can see them"). Same predicates as the frontend Best
    tab / signal strip; this is reading the frozen log (not a live recompute), exactly like
    the track-record study. Returns a list of {label, side(1/2), hit} for fired signals."""
    if pd.isna(r.get("p1_won")):
        return []
    p1won = bool(r["p1_won"])

    def b(col):
        v = r.get(col)
        return None if (v is None or pd.isna(v)) else (float(v) >= 0.5)

    a, bb, c1 = b("model_a_p1"), b("model_b_p1"), b("model_c_p1")
    g1, d, dma = b("model_cma_p1"), b("model_d_p1"), b("model_dma_p1")
    c50, c75, cu, mcd = b("mc_c_p1"), b("mc_c75_p1"), b("mc_cutr_p1"), b("mc_p1")
    dog1 = (mk1 is not None and mk1 < 0.5)          # p1 is the market underdog
    have_mkt = mk1 is not None
    cma = r.get("model_cma_p1")
    gray_p1 = None if (cma is None or pd.isna(cma)) else float(cma)
    dma_p1v = r.get("model_dma_p1")
    dma_p1 = None if (dma_p1v is None or pd.isna(dma_p1v)) else float(dma_p1v)
    # dog/fav magnitudes (market vs gray) for the hate / depth gates
    hate = d5 = False
    if have_mkt and gray_p1 is not None:
        mdog = mk1 if dog1 else 1 - mk1
        gdog = gray_p1 if dog1 else 1 - gray_p1
        hate = (mdog - gdog) >= 0.02
        d5 = (mdog - gdog) >= 0.05
    dma_edge = False
    if have_mkt and dma is not None and dma_p1 is not None:
        ds = dma_p1 if dma else 1 - dma_p1
        mkp = mk1 if dma else 1 - mk1
        dma_edge = (ds - mkp) >= 0.02
    favp1 = (not dog1) if have_mkt else None        # favorite side as a p1-bool

    def S(side_p1bool):
        return {"side": 1 if side_p1bool else 2, "hit": bool(bool(side_p1bool) == p1won)}

    out = []
    def add(label, cond, side):
        if cond and side is not None:
            out.append({"label": label, **S(side)})

    # c75 SPLIT BY SIDE (2026-10-07, user "make sure all the new signals for every board
    # slip are added to the previous day tab"): the board chips are side-specific now, so
    # the history line is too — a c75 favorite ✓ must not blend into the dog lane's day.
    if c75 is not None and have_mkt:
        add("c75 DOG" if c75 == dog1 else "c75 FAV", True, c75)
    else:
        add("c75", c75 is not None, c75)
    add("c50+c75", (c50 is not None and c75 is not None and c50 == c75), c75)
    # ⚄4-MC DOG (2026-10-08, promoted per user): all four sims on a +100..+250 dog
    if (None not in (mcd, c50, c75, cu) and mcd == c50 == c75 == cu and c50 == dog1
            and have_mkt):
        _od4h = r.get("p1_odds") if c50 else r.get("p2_odds")
        if _od4h is not None and not pd.isna(_od4h) and 100 <= float(_od4h) <= 250:
            add("⚄4-MC DOG", True, c50)
            if c1 is not None and g1 is not None and c1 != g1 and g1 != dog1:
                add("⚔🐕FIGHT-FLIP", True, c50)
    # ⚄4MC>MKT FAV -200..-300 (2026-10-08, user promotion)
    _v4h = [r.get("mc_p1"), r.get("mc_c_p1"), r.get("mc_c75_p1"), r.get("mc_cutr_p1")]
    if have_mkt and all(v is not None and not pd.isna(v) for v in _v4h):
        _favh = not dog1
        _mkfh = max(mk1, 1 - mk1)
        if all((float(v) if _favh else 1 - float(v)) > _mkfh for v in _v4h):
            _odfh = r.get("p1_odds") if _favh else r.get("p2_odds")
            if _odfh is not None and not pd.isna(_odfh) and -300 <= float(_odfh) <= -200:
                add("⚄4MC>MKT FAV", True, _favh)
    # D-MA 2pt split (⭐✓ on the FAV half = one of the three backtest-positive favorite
    # cells, women +5.4%; dog half men +1.8 / women +15.2 bt26).
    if dma_edge and have_mkt:
        add("D-MA2 DOG" if dma == dog1 else "⭐✓D-MA2 FAV", True, dma)
    else:
        add("D-MA 2pt", dma_edge, dma)
    all10 = [a, bb, c1, g1, d, dma, mcd, c50, c75, cu]
    all10_ok = all(x is not None for x in all10) and len(set(all10)) == 1
    add("ALL-10", all10_ok, a)
    # ⭐✓ ALL-10 PRICE (men, pick frozen at −140..−300 American) — the marked band.
    if all10_ok and have_mkt and str(r.get("league") or "").lower() in ("atp", "itf_men"):
        _od = r.get("p1_odds") if a else r.get("p2_odds")
        if _od is not None and not pd.isna(_od) and -300 <= float(_od) <= -140:
            add("⭐✓ALL10 PRICE", True, a)
    add("MC 4/4", (None not in (a, bb, c1, d, c50) and a == bb == c1 == d == c50), c1)
    add("FIGHT gray", (c1 is not None and g1 is not None and c1 != g1), g1)
    # ⭐✓ FADE-GOLD (gray-hated dog -> bet the FAVORITE): one of the three favorite cells
    # positive in the gender×side backtest (M +2.7 / W +10.4 all-yrs).
    add("⭐✓FADE-GOLD5+", d5, favp1)
    add("GOLD DOG", ((c1 is not None and g1 is not None and dog1 is not None and c1 == g1 == dog1)), c1)
    if not any(s["label"] == "GOLD DOG" for s in out) and not d5:
        add("⭐✓FADE-GOLD", hate, favp1)
    # ⭐✓ C-EDGE 5pt FAV (bt M +5.3 / W +10.9) + the dog half, from the frozen C prob.
    _cp = r.get("model_c_p1")
    if have_mkt and _cp is not None and not pd.isna(_cp):
        _cpf = float(_cp)
        _ce1 = _cpf - mk1 >= 0.05
        _ce2 = (1 - _cpf) - (1 - mk1) >= 0.05
        if _ce1 or _ce2:
            _ceS = _ce1
            add("C-EDGE5 DOG" if (_ceS == dog1) else "⭐✓C-EDGE5 FAV", True, _ceS)
    # 🧊 FADE-FORM (pure-form overlay disagrees with the c75 pick), split dog/fav — the
    # board/Best chip's lane, from the frozen pf_edge_p1.
    _pfe = r.get("pf_edge_p1")
    if c75 is not None and have_mkt and _pfe is not None and not pd.isna(_pfe):
        if (float(_pfe) > 0) != c75:
            add("🧊FADE-FORM DOG" if (c75 == dog1) else "🧊FADE-FORM FAV", True, c75)
    # MC+GREEN (marked women signal): serve-MC agrees a plain green name.
    _passfav = (None not in (a, bb, c1, g1) and have_mkt
                and a != c1 and bb != c1 and g1 == c1 and c1 != dog1)
    _star = (c1 is not None and g1 is not None and have_mkt and c1 == g1 == dog1)
    if mcd is not None and g1 is not None and not _star and not hate and not _passfav:
        add("MC+GREEN", mcd == g1, g1)
    # 🔀 FADE 6-4 SPLIT: the 10 heads split exactly 6-4 -> the 4-minority side.
    if all(x is not None for x in all10):
        _n1 = sum(1 for x in all10 if x)
        if _n1 in (4, 6):
            add("FADE 6-4", True, _n1 == 4)
    add("FADE-A", (None not in (a, bb, c1) and a != bb and bb == c1), bb)
    add("C-ALONE+GRAY", (None not in (a, bb, c1, g1) and a != c1 and bb != c1 and g1 == c1), c1)
    add("D+GRAY DOG", (None not in (d, g1) and have_mkt and d == dog1 and g1 == dog1), dog1)
    add("D ALONE", (None not in (a, bb, c1, d) and a != d and bb != d and c1 != d), d)
    return out


def _conflict_resolvers_for_row(r, mk1):
    """⚖️ conflict-resolver verdicts for a FINISHED game (2026-10-05, user "add the new
    signals to the previous-day tab so I can see how it did"): when signals disagreed, which
    side the gender-specific rule said to trust + whether it won. From frozen probs only.
    Mirrors the board's dark-purple ⚖️ badges. Returns [{label, side(1/2), hit}]."""
    if pd.isna(r.get("p1_won")):
        return []
    p1won = bool(r["p1_won"])
    league = str(r.get("league") or "").lower()
    women = league in ("wta", "itf_women")

    def b(col):
        v = r.get(col)
        return None if (v is None or pd.isna(v)) else (float(v) >= 0.5)

    a, bb, c1, g1, d = (b("model_a_p1"), b("model_b_p1"), b("model_c_p1"),
                        b("model_cma_p1"), b("model_d_p1"))
    if mk1 is None or c1 is None or g1 is None:
        return []
    dog1 = mk1 < 0.5
    star = (c1 == g1 == dog1)
    cma = r.get("model_cma_p1")
    gray_p1 = float(cma) if (cma is not None and not pd.isna(cma)) else None
    hate = False
    if gray_p1 is not None:
        mdog = mk1 if dog1 else 1 - mk1
        gdog = gray_p1 if dog1 else 1 - gray_p1
        hate = (mdog - gdog) >= 0.02
    onfav = lambda x: x == (not dog1)
    collision = (hate and None not in (a, bb, c1, g1, d)
                 and onfav(a) and onfav(bb) and onfav(c1) and onfav(g1) and onfav(d))

    def S(side_p1bool):
        return {"side": 1 if side_p1bool else 2, "hit": bool(bool(side_p1bool) == p1won)}

    out = []
    if star and not women:
        out.append({"label": "⚖①DOG", **S(dog1)})
    if c1 != g1:
        out.append({"label": "⚖②GRAY" if women else "⚖②C", **S(g1 if women else c1)})
    if None not in (a, bb) and a != bb and bb == c1 and not women:
        out.append({"label": "⚖③FADE-A", **S(bb)})
    if hate:
        if not women:
            out.append({"label": "⚖④FAV", **S(not dog1)})
        elif collision:
            favp = max(mk1, 1 - mk1)                              # price split on the fav
            lbl = "⚖⑤LEANFAV" if 0.65 <= favp < 0.85 else "⚖⑤PASS"
            out.append({"label": lbl, **S(not dog1)})             # tracks the fav side
        else:
            out.append({"label": "⚖④DOG", **S(dog1)})
    return out


def get_tennis_history(limit_dates: int = 30) -> dict:
    """Every FINISHED tennis match from the frozen log (2026-10-02, user ask), newest
    date first. Per match: who won, frozen pre-match odds, and what each model + the
    Monte Carlo picked with a hit/miss -- so the whole settled record is browsable, not
    just today's board. Display from the ledger only; never recomputed."""
    log = _read_log()
    if log.empty:
        return {"dates": [], "settled_total": 0}
    s = log[(log["settled"] == True) & log["p1_won"].notna()].copy()  # noqa: E712
    if s.empty:
        return {"dates": [], "settled_total": 0}
    s = s.sort_values("date")

    def pick(row, col):
        v = row.get(col)
        if pd.isna(v):
            return None
        p1side = float(v) >= 0.5
        return {"side": 1 if p1side else 2, "hit": bool(p1side == bool(row["p1_won"]))}

    def pickpct(row, col):
        """Like pick() but also carries p1's win % — for the purple C-MC line that shows
        the actual variant numbers on every history row (2026-10-03, user ask)."""
        v = row.get(col)
        if pd.isna(v):
            return None
        p1 = float(v)
        p1side = p1 >= 0.5
        return {"side": 1 if p1side else 2, "hit": bool(p1side == bool(row["p1_won"])),
                "p1_pct": round(p1 * 100, 1)}

    def _model(prob_col, gray_col, mk1):
        """Reconstruct a board-shaped model object from the frozen probabilities only."""
        v = s_r.get(prob_col)
        if pd.isna(v):
            return None
        p1 = float(v)
        o = {"p1_prob": round(p1, 4), "p2_prob": round(1 - p1, 4), "thin": False}
        if mk1 is not None:
            o["market_p1"] = mk1
            o["edge_p1"] = round(p1 - mk1, 4)
        g = s_r.get(gray_col)
        if not pd.isna(g):
            o["market_aware_p1"] = round(float(g), 4)
        return o

    out_dates = {}
    for _, r in s.iterrows():
        s_r = r
        d1, d2 = _decimal(r.get("p1_odds")), _decimal(r.get("p2_odds"))
        mk1 = None
        if d1 and d2:
            i1, i2 = 1 / d1, 1 / d2
            mk1 = round(i1 / (i1 + i2), 3)
        mc = r.get("mc_p1")
        p1o = (None if pd.isna(r.get("p1_odds")) else int(r["p1_odds"]))
        p2o = (None if pd.isna(r.get("p2_odds")) else int(r["p2_odds"]))
        # board-shaped card, rebuilt ONLY from frozen columns (no recompute). Pieces
        # not frozen (cUTR, MC sub-stats, D detail, tr_context) are simply absent --
        # MatchCard renders them conditionally.
        ma = _model("model_a_p1", "model_ama_p1", mk1)
        # H2H (2026-10-04 user bug + fix): prefer the FROZEN as-of record (frozen at first
        # serve from 2026-10-04 on); for older rows that predate freezing, fall back to the
        # current H2H record so no card falsely reads "no prior H2H".
        if ma is not None:
            if pd.notna(r.get("h2h_n")) and float(r.get("h2h_n")) > 0:
                ma["h2h"] = {"n": int(r["h2h_n"]),
                             "p1_wins": int(r["h2h_p1w"]) if pd.notna(r.get("h2h_p1w")) else 0,
                             "p2_wins": int(r["h2h_p2w"]) if pd.notna(r.get("h2h_p2w")) else 0,
                             "surface_n": int(r["h2h_sn"]) if pd.notna(r.get("h2h_sn")) else 0,
                             "surface_p1_wins": int(r["h2h_sp1w"]) if pd.notna(r.get("h2h_sp1w")) else 0,
                             "surface": str(r.get("surface") or "")}
            else:
                try:
                    import tennis_model_a as _tma_h
                    ma["h2h"] = _tma_h.h2h_for(r.get("player_1"), r.get("player_2"), r.get("surface"))
                except Exception:  # noqa: BLE001
                    pass
        mb = _model("model_b_p1", "model_bma_p1", mk1)
        mcd = _model("model_c_p1", "model_cma_p1", mk1)
        md = _model("model_d_p1", "model_dma_p1", mk1)
        if md is not None and not pd.isna(mc):
            md["mc"] = {"sims": 100000, "p1_pct": round(float(mc) * 100, 1),
                        "p1_wins": int(round(float(mc) * 100000)),
                        "p2_wins": int(round((1 - float(mc)) * 100000)),
                        "win_prob_home": None}
        # C-MC variants onto the history card's Model C (2026-10-03, user "include the 3
        # monte carlo things"): c50 visible line + the c75/cUTR frozen variants.
        _mcc = r.get("mc_c_p1")
        if mcd is not None and not pd.isna(_mcc):
            mcd["mc"] = {"sims": 40000, "p1_pct": round(float(_mcc) * 100, 1),
                         "p1_hold": None, "p2_hold": None, "straight_sets_pct": None,
                         "c_anchored": True}
        if mcd is not None:
            for _vc in ("mc_c75_p1", "mc_cutr_p1"):
                _vv = r.get(_vc)
                if not pd.isna(_vv):
                    mcd[_vc] = round(float(_vv), 4)
        card = {
            "fixture_id": str(r.get("fixture_id") or f"{r.get('date')}-{r.get('player_1')}"),
            "player_1": str(r.get("player_1") or ""), "player_2": str(r.get("player_2") or ""),
            "league": str(r.get("league") or ""), "surface": str(r.get("surface") or ""),
            "tournament": str(r.get("tournament") or ""), "round": str(r.get("round") or ""),
            "status": "finished", "p1_won": bool(r["p1_won"]),
            "score": (str(r.get("score")) if pd.notna(r.get("score")) else None),
            "best_of_5": bool(r.get("best_of_5")),
            "live_odds": ({"player_1": p1o, "player_2": p2o,
                           "bookmaker": str(r.get("bookmaker") or "")} if p1o is not None and p2o is not None else None),
            "model_a": ma, "model_b": mb, "model_c": mcd, "model_d": md,
        }
        rec = {
            "p1": str(r.get("player_1") or ""), "p2": str(r.get("player_2") or ""),
            "league": str(r.get("league") or ""), "tournament": str(r.get("tournament") or ""),
            "surface": str(r.get("surface") or ""),
            "p1_won": bool(r["p1_won"]),
            "score": (str(r.get("score")) if pd.notna(r.get("score")) else None),
            "p1_odds": p1o, "p2_odds": p2o,
            "market_p1": mk1,
            "models": {k: pick(r, c) for k, c in
                       (("A", "model_a_p1"), ("B", "model_b_p1"), ("C", "model_c_p1"),
                        ("gray", "model_cma_p1"), ("D", "model_d_p1"))},
            "mc": (None if pd.isna(mc) else {"p1_pct": round(float(mc) * 100, 1),
                   "side": 1 if float(mc) >= 0.5 else 2,
                   "hit": bool((float(mc) >= 0.5) == bool(r["p1_won"]))}),
            # the 3 Model-C Monte Carlo variants per match (2026-10-03, user "include the
            # 3 monte carlo things so i can see"): c50 (visible), c75, cUTR — side + hit.
            "mc_c": {"c50": pickpct(r, "mc_c_p1"), "c75": pickpct(r, "mc_c75_p1"),
                     "cutr": pickpct(r, "mc_cutr_p1"),
                     "recon": bool(r.get("mc_c_recon")) if pd.notna(r.get("mc_c_recon")) else False},
            "model_x": (lambda p: ({**p, "recon": bool(r.get("model_x_recon"))
                                     if pd.notna(r.get("model_x_recon")) else False} if p else None))(pickpct(r, "model_x_p1")),
            # our headline pick (the favored side shown on the board) + the user's
            # c-MC+c75 take, for the daily hit % in results-history (2026-10-03). The board
            # headlines off prediction -> A -> B -> C (the old tour model is retired, so
            # p1_win_prob is often null now); mirror that fallback so "our" is never empty.
            "our": (pickpct(r, "p1_win_prob") or pickpct(r, "model_a_p1")
                    or pickpct(r, "model_b_p1") or pickpct(r, "model_c_p1")),
            "cmc_c75": (pickpct(r, "mc_c_p1")
                        if (pd.notna(r.get("mc_c_p1")) and pd.notna(r.get("mc_c75_p1"))
                            and (float(r["mc_c_p1"]) >= 0.5) == (float(r["mc_c75_p1"]) >= 0.5))
                        else None),
            # Model X win/loss post-mortem (2026-10-03, user ask): every signal's call +
            # who won + the info we had that pointed to the winner the market missed.
            "postmortem": _postmortem(r),
            # new elite lane-signals per finished game (2026-10-05, user "update previous
            # games with the new signals"): which Best-tab signals fired + hit, from frozen
            # probs only. Shown as a compact sub-line in results-history.
            "signals": _elite_signals_for_row(r, mk1),
            "conflicts": _conflict_resolvers_for_row(r, mk1),
            "card": card,
        }
        out_dates.setdefault(str(r.get("date") or "")[:10], []).append(rec)
    dates = sorted(out_dates.keys(), reverse=True)[:limit_dates]
    return {"settled_total": int(len(s)),
            "dates": [{"date": d, "n": len(out_dates[d]),
                       "matches": out_dates[d][::-1]} for d in dates]}


def get_ab25_record() -> dict:
    """$25/game A-vs-B lanes (registered 2026-09-28, user ask): on settled rows where BOTH
    tennis models froze a pick at first serve, three lanes -- Model A alone (B disagrees),
    Model B alone (A disagrees), both agree -- each $25 flat at the frozen odds. Both models
    are display-only (the market beat them in validation); these lanes are the public
    forward test of that verdict, priced in dollars."""
    log = _read_log()
    if log.empty or "model_a_p1" not in log.columns:
        return {"registered": "2026-09-28", "stake_usd": 25, "lanes": {}, "pending": 0}
    both = log[log["model_a_p1"].notna() & log["model_b_p1"].notna()
               & log["p1_odds"].notna() & log["p2_odds"].notna()]
    lanes = {"a_alone": [], "b_alone": [], "agree": []}
    # full M/W separation (2026-09-30, user ask "everything computed separate"):
    # every lane carries gender sub-lists; agg'd into m/w keys on the way out.
    lanes_g = {k: {"m": [], "w": []} for k in lanes}
    pending = 0
    for _, r in both.iterrows():
        a1 = float(r["model_a_p1"]) >= 0.5
        b1 = float(r["model_b_p1"]) >= 0.5
        if not bool(r["settled"]) or pd.isna(r["p1_won"]):
            pending += 1
            continue
        won1 = bool(r["p1_won"])
        _lg = "w" if str(r.get("league")) == "wta" else "m"

        def pnl(side1):
            dec = _decimal(r["p1_odds"] if side1 else r["p2_odds"])
            if dec is None:
                return None
            return 25.0 * (dec - 1.0) if (won1 == side1) else -25.0

        if a1 == b1:
            v = pnl(a1)
            if v is not None:
                lanes["agree"].append(v)
                lanes_g["agree"][_lg].append(v)
        else:
            va, vb = pnl(a1), pnl(b1)
            if va is not None:
                lanes["a_alone"].append(va)
                lanes_g["a_alone"][_lg].append(va)
            if vb is not None:
                lanes["b_alone"].append(vb)
                lanes_g["b_alone"][_lg].append(vb)

    def agg(v):
        if not v:
            return {"n": 0, "wins": 0, "staked_usd": 0, "profit_usd": 0.0, "roi_pct": None}
        return {"n": len(v), "wins": sum(1 for x in v if x > 0),
                "staked_usd": 25 * len(v), "profit_usd": round(sum(v), 2),
                "roi_pct": round(100 * sum(v) / (25 * len(v)), 2)}
    # PER-LANE PICK LISTS (2026-09-30, user ask "i want everything on each pick"): one
    # dedicated pass re-derives every lane's individual picks -- matchup, side, frozen price,
    # result -- so each card on the $25 tab can expand to show exactly what it bet.
    # SIDE-SPLIT for the ROOT lanes too (2026-10-07, user "no favorite or dog icon on these"):
    # the picks loop below walks every root lane with its exact side, so accumulate dog/fav +
    # gender×side PnL here and merge it into the returned lane dicts -- the $25 cards then
    # render their 🐕/⭐ and crossed lines exactly like the study lanes.
    _sideagg = {}

    def _lane_picks():
        out = {}

        def put(key, r, side1, settled, won1):
            if settled:
                dd1, dd2 = _decimal(r.get("p1_odds")), _decimal(r.get("p2_odds"))
                if dd1 and dd2:
                    mk9 = (1 / dd1) / ((1 / dd1) + (1 / dd2))
                    isdog = (side1 == (mk9 < 0.5))
                    pnl9 = 25.0 * ((dd1 if side1 else dd2) - 1.0) if (won1 == side1) else -25.0
                    g9 = "w" if str(r.get("league")) == "wta" else "m"
                    b9 = _sideagg.setdefault(key, {"d": [], "f": [], "md": [], "mf": [], "wd": [], "wf": []})
                    b9["d" if isdog else "f"].append(pnl9)
                    b9[g9 + ("d" if isdog else "f")].append(pnl9)
            pr9 = r.get("p1_odds") if side1 else r.get("p2_odds")
            out.setdefault(key, []).append({
                "d": str(r.get("date") or "")[5:],
                "s": str(r.get("player_1") if side1 else r.get("player_2")),
                "o": str(r.get("player_2") if side1 else r.get("player_1")),
                "pr": (None if pd.isna(pr9) else int(pr9)),
                "w": (None if not settled else bool(won1 == side1)),
                "lg": "W" if str(r.get("league")) == "wta" else "M"})

        base = log[log["p1_odds"].notna() & log["p2_odds"].notna()]
        for _, r in base.iterrows():
            d1, d2 = _decimal(r["p1_odds"]), _decimal(r["p2_odds"])
            if not d1 or not d2:
                continue
            i1, i2 = 1 / d1, 1 / d2
            mk1 = i1 / (i1 + i2)
            dog1 = mk1 < 0.5
            settled = bool(r["settled"]) and pd.notna(r["p1_won"])
            won1 = bool(r["p1_won"]) if settled else None
            ap, bp = r.get("model_a_p1"), r.get("model_b_p1")
            cpv, gv = r.get("model_c_p1"), r.get("model_cma_p1")
            a1 = float(ap) >= 0.5 if pd.notna(ap) else None
            b1 = float(bp) >= 0.5 if pd.notna(bp) else None
            c1 = float(cpv) >= 0.5 if pd.notna(cpv) else None
            g1 = float(gv) >= 0.5 if pd.notna(gv) else None
            if a1 is not None and b1 is not None:
                if a1 == b1:
                    put("agree", r, a1, settled, won1)
                else:
                    put("a_alone", r, a1, settled, won1)
                    put("b_alone", r, b1, settled, won1)
            if c1 is not None:
                put("c_all", r, c1, settled, won1)
                cf = float(cpv)
                if (cf - mk1 >= 0.05) or ((1 - cf) - (1 - mk1) >= 0.05):
                    put("c_edge", r, cf - mk1 >= 0.05, settled, won1)
                if a1 is not None and b1 is not None:
                    if a1 != c1 and b1 != c1:
                        put("c_alone", r, c1, settled, won1)
                    elif a1 == c1 or b1 == c1:
                        put("c_with", r, c1, settled, won1)
            if g1 is not None:
                put("cma_all", r, g1, settled, won1)
                gf = float(gv)
                if (gf - mk1 >= 0.02) or ((1 - gf) - (1 - mk1) >= 0.02):
                    put("cma_edge", r, gf - mk1 >= 0.02, settled, won1)
            if c1 is not None and g1 is not None:
                gf = float(gv)
                mdog = mk1 if dog1 else 1 - mk1
                gdog = gf if dog1 else 1 - gf
                star = (c1 == g1) and (g1 == dog1)
                hate = (mdog - gdog) >= 0.02
                if star:
                    put("agree_dog", r, dog1, settled, won1)
                    put("gold_names", r, dog1, settled, won1)
                    if (gdog - mdog) >= 0.04:
                        put("gray_dog4", r, dog1, settled, won1)
                    _ddp = d1 if dog1 else d2
                    if _ddp >= 2.0:
                        put("stardog_prime", r, dog1, settled, won1)
                        if a1 is not None and b1 is not None and a1 != c1 and b1 != c1:
                            put("apex_dog", r, dog1, settled, won1)
                    rnd9 = str(r.get("round") or "").lower()
                    if not ("1st" in rnd9 or "qual" in rnd9 or "128" in rnd9 or "of 64" in rnd9):
                        put("cgray_dog_late", r, dog1, settled, won1)
                elif hate:
                    put("grayhate_dog", r, dog1, settled, won1)
                    put("grayhate_fav", r, not dog1, settled, won1)
                    put("gold_names", r, not dog1, settled, won1)
                if c1 != g1:
                    put("cvg_c", r, c1, settled, won1)
                    put("cvg_gray", r, g1, settled, won1)
                if a1 is not None and b1 is not None:
                    passfav = (a1 != c1 and b1 != c1 and g1 == c1 and c1 != dog1)
                    if a1 == b1 == c1:
                        put("abc_agree", r, c1, settled, won1)
                        if c1 == dog1:
                            put("abc_dog", r, c1, settled, won1)
                    if a1 != c1 and b1 != c1 and g1 == c1:
                        put("c_alone_gray", r, c1, settled, won1)
                        put("c_alone_gray_dog" if c1 == dog1 else "c_alone_gray_fav",
                            r, c1, settled, won1)
                    amv, bmv = r.get("model_ama_p1"), r.get("model_bma_p1")
                    if pd.notna(amv) and pd.notna(bmv):
                        if a1 == b1 == c1 == g1 == (float(amv) >= 0.5) == (float(bmv) >= 0.5):
                            put("all6_agree", r, c1, settled, won1)
                    if not star and not hate and not passfav:
                        put("green_names", r, g1, settled, won1)
                    if a1 != b1 and b1 == c1:
                        put("fade_a", r, b1, settled, won1)
                        if b1 == dog1:
                            put("fade_a_dog", r, b1, settled, won1)
                            if g1 == b1:
                                put("fade_a_dog_gray", r, b1, settled, won1)
                        else:
                            put("fade_a_fav", r, b1, settled, won1)
                # Model D pick lists (2026-09-30)
                dp0, dg0 = r.get("model_d_p1"), r.get("model_dma_p1")
                if pd.notna(dp0):
                    d1x = float(dp0) >= 0.5
                    put("d_all", r, d1x, settled, won1)
                    if pd.notna(dg0):
                        dg1x = float(dg0) >= 0.5
                        put("dma_all", r, dg1x, settled, won1)
                        if d1x == dg1x and d1x == dog1:
                            put("d_gray_dog", r, d1x, settled, won1)
                    if a1 is not None and b1 is not None and a1 != d1x and b1 != d1x and c1 != d1x:
                        put("d_alone", r, d1x, settled, won1)
                mc0 = r.get("mc_p1")
                if pd.notna(mc0):
                    mc1 = float(mc0) >= 0.5
                    put("mc_all", r, mc1, settled, won1)
                    if 0.50 <= max(float(mc0), 1 - float(mc0)) < 0.60:
                        put("mc_tossup", r, mc1, settled, won1)
                    if mc1 == dog1:
                        put("mc_dog", r, mc1, settled, won1)
                        dp9 = float(mc0) if dog1 else 1 - float(mc0)
                        if dp9 >= 0.60:
                            put("mc_dog_big", r, mc1, settled, won1)
                            if g1 == dog1:
                                put("mc_biggray", r, mc1, settled, won1)
                    # MC co-fire pick lists (2026-10-02)
                    pf9 = (a1 is not None and b1 is not None and a1 != c1 and b1 != c1
                           and g1 == c1 and c1 != dog1)
                    gold9 = (dog1 if star else ((not dog1) if hate else None))
                    if gold9 is not None and mc1 == gold9:
                        put("mc_gold", r, gold9, settled, won1)
                    if (not star) and (not hate) and (not pf9) and mc1 == g1:
                        put("mc_green", r, g1, settled, won1)
                    if a1 is not None and b1 is not None and pd.notna(dp0) \
                            and a1 == b1 == c1 == (float(dp0) >= 0.5) and mc1 == c1:
                        put("mc_4of4", r, c1, settled, won1)
                # tier pick lists (2026-09-30): same ribbon logic, from today forward
                alone9 = a1 is not None and b1 is not None and a1 != c1 and b1 != c1
                if star and (alone9 or (gdog - mdog) >= 0.04):
                    tk, ts = "tier1", dog1
                elif star:
                    tk, ts = "tier2", dog1
                elif hate:
                    tk, ts = "tier3", not dog1
                elif (alone9 and g1 == c1 and c1 != dog1) or c1 != g1:
                    tk, ts = "tier_avoid", c1
                else:
                    tk, ts = "tier_nobet", g1
                if str(r.get("date") or "") >= "2026-09-30":
                    put(tk, r, ts, settled, won1)
        return {k: v[-20:][::-1] for k, v in out.items()}

    # C-EDGE $25 lane (registered 2026-09-28): Model C's audited-but-unproven claim, tested
    # forward -- when |C - devigged frozen market| >= 5pts, $25 on C's side at frozen odds.
    ce, ce_pending = [], 0
    call_g = {"m": [], "w": []}
    c_alone_g = {"m": [], "w": []}
    c_with_g = {"m": [], "w": []}
    cma_all_g = {"m": [], "w": []}
    # gender + edge-side splits (2026-09-30, user ask): live shows these lanes only
    # earn on MEN'S FAVORITES (C-edge fav M +10.8 / gray2 fav M +7.6) while the
    # edge-on-dog halves are -19..-40% both genders -- the chips read these cells.
    _gs_keys = ("m", "w", "m_fav", "m_dog", "w_fav", "w_dog")
    ce_g = {k: [] for k in _gs_keys}
    cme_g = {k: [] for k in _gs_keys}
    call, call_pending = [], 0  # EVERY C pick, $25 on its favored side (user ask 2026-09-28)
    c_alone, c_alone_pending = [], 0
    c_with, c_with_pending = [], 0
    cma_all, cma_all_pending = [], 0   # market-aware C, favored side (user ask 2026-09-28)
    cma_edge, cma_edge_pending = [], 0  # market-aware C when it moves >=2pt off the market
    agdog, agdog_pending = [], 0  # C + gray AGREE on a market DOG -- the best backtest cell
    agdog_g = {"m": [], "w": []}  # gender split (2026-09-30): women hit 63% bt vs men 54%
    # found (2026-09-28): +24.4/+21.6/+13.7% by year on 8,320, hit 54.8% at plus prices.
    if "model_c_p1" in log.columns:
        crows = log[log["model_c_p1"].notna() & log["p1_odds"].notna() & log["p2_odds"].notna()]
        for _, r in crows.iterrows():
            d1, d2 = _decimal(r["p1_odds"]), _decimal(r["p2_odds"])
            if not d1 or not d2:
                continue
            i1, i2 = 1 / d1, 1 / d2
            mk1 = i1 / (i1 + i2)
            cp = float(r["model_c_p1"])
            settled = bool(r["settled"]) and pd.notna(r["p1_won"])
            fav1 = cp >= 0.5
            _pnl_c = None
            _lgc = "w" if str(r.get("league")) == "wta" else "m"
            if settled:
                won1 = bool(r["p1_won"])
                _pnl_c = 25.0 * ((d1 if fav1 else d2) - 1.0) if (won1 == fav1) else -25.0
                call.append(_pnl_c)
                call_g[_lgc].append(_pnl_c)
            else:
                call_pending += 1
            # C vs the other models (user ask 2026-09-28): C ALONE = both A and B took the
            # OTHER side; C AGREES = at least one of A/B is on C's side.
            _sibs = [bool(float(r[k]) >= 0.5) for k in ("model_a_p1", "model_b_p1")
                     if pd.notna(r.get(k))]
            if _sibs:
                if any(s == fav1 for s in _sibs):
                    if settled:
                        c_with.append(_pnl_c)
                        c_with_g[_lgc].append(_pnl_c)
                    else:
                        c_with_pending += 1
                elif len(_sibs) == 2:
                    if settled:
                        c_alone.append(_pnl_c)
                        c_alone_g[_lgc].append(_pnl_c)
                    else:
                        c_alone_pending += 1
            side1 = cp - mk1 >= 0.05
            side2 = (1 - cp) - (1 - mk1) >= 0.05
            if not side1 and not side2:
                continue
            if not settled:
                ce_pending += 1
                continue
            won1 = bool(r["p1_won"])
            dec = d1 if side1 else d2
            _pce = 25.0 * (dec - 1.0) if (won1 == side1) else -25.0
            ce.append(_pce)
            _g9 = "w" if str(r.get("league")) == "wta" else "m"
            _sd9 = (mk1 < 0.5) == side1
            ce_g[_g9].append(_pce)
            ce_g[_g9 + ("_dog" if _sd9 else "_fav")].append(_pce)
    # market-aware C lanes: its edges are 1-3pt by construction (it hugs the price), so the
    # edge lane uses a 2pt bar; the all-picks lane doubles as a market-favorite control.
    if "model_cma_p1" in log.columns:
        marows = log[log["model_cma_p1"].notna() & log["p1_odds"].notna() & log["p2_odds"].notna()]
        for _, r in marows.iterrows():
            d1, d2 = _decimal(r["p1_odds"]), _decimal(r["p2_odds"])
            if not d1 or not d2:
                continue
            i1, i2 = 1 / d1, 1 / d2
            mk1 = i1 / (i1 + i2)
            cma = float(r["model_cma_p1"])
            settled = bool(r["settled"]) and pd.notna(r["p1_won"])
            fav1 = cma >= 0.5
            if settled:
                won1 = bool(r["p1_won"])
                pnl_ma = 25.0 * ((d1 if fav1 else d2) - 1.0) if (won1 == fav1) else -25.0
                cma_all.append(pnl_ma)
                cma_all_g["w" if str(r.get("league")) == "wta" else "m"].append(pnl_ma)
            else:
                cma_all_pending += 1
            _cp0 = r.get("model_c_p1")
            if pd.notna(_cp0):
                _c1 = float(_cp0) >= 0.5
                if _c1 == fav1 and ((mk1 < 0.5) if fav1 else (mk1 >= 0.5)):
                    if settled:
                        won1 = bool(r["p1_won"])
                        _dg = d1 if fav1 else d2
                        _p9 = 25.0 * (_dg - 1.0) if (won1 == fav1) else -25.0
                        agdog.append(_p9)
                        agdog_g["w" if str(r.get("league")) == "wta" else "m"].append(_p9)
                    else:
                        agdog_pending += 1
            e1 = cma - mk1 >= 0.02
            e2 = (1 - cma) - (1 - mk1) >= 0.02
            if e1 or e2:
                if settled:
                    won1 = bool(r["p1_won"])
                    dec = d1 if e1 else d2
                    _pme = 25.0 * (dec - 1.0) if (won1 == e1) else -25.0
                    cma_edge.append(_pme)
                    _g8 = "w" if str(r.get("league")) == "wta" else "m"
                    _sd8 = (mk1 < 0.5) == e1
                    cme_g[_g8].append(_pme)
                    cme_g[_g8 + ("_dog" if _sd8 else "_fav")].append(_pme)
                else:
                    cma_edge_pending += 1
    # STUDY LANES (2026-09-28, user "i still want to live everything"): every configuration
    # examined today, forward-tested. Backtest citations in the frontend tooltips.
    # vd/vf = the PICK was a market DOG / FAVORITE (2026-10-06, user "split dog/fav with every
    # single signal"); vmd/vmf/vwd/vwf = gender×side crossed cells so the Best/Prices tabs can
    # gate a pick by its signal's record on THAT exact (gender, dog/fav) cell -- which drops
    # losing favorite picks and keeps the dog edge. Populated generically in bet().
    study = {k: {"v": [], "p": 0, "vm": [], "vw": [], "vd": [], "vf": [],
                 "vmd": [], "vmf": [], "vwd": [], "vwf": []} for k in
             ("cvg_c", "cvg_gray", "gray_dog4", "grayhate_dog", "grayhate_fav",
              "abc_agree", "abc_dog", "c_alone_gray", "c_alone_gray_dog",
              "c_alone_gray_fav", "gold_names", "green_names", "all6_agree",
              "tier1", "tier2", "tier3", "tier_avoid", "tier_nobet", "fade_a",
              "fade_a_dog", "fade_a_dog_gray", "fade_a_fav",
              "goldfav_d45", "goldfav_d5",
              "d_all", "dma_all", "d_gray_dog", "d_alone", "mc_all", "mc_dog",
              "mc_dog_big", "mc_4of4", "mc_gold", "mc_green", "mc_biggray",
              "stardog_prime", "mc_tossup", "cgray_dog_late", "apex_dog",
              "mc_c_all", "mc_c_and_d", "mc_c75_all", "mc_cutr_all",
              # c75 split by side (2026-10-06, user "split it that way"): the c75 edge is ALL
              # in the dogs; favorites flat/neg. c75fav_formfade = the ONE +ROI favorite cell
              # (c75 fav that recent form DISAGREES with, men +7.5%).
              "mc_c75_dog", "mc_c75_fav", "c75fav_formfade",
              "model_x_all", "model_x_edge2", "mcc_c75_agree",
              "cc75_d_dog", "cc75_nod_dog", "dma_edge2", "all10_agree", "cc75_dog",
              "against_a",
              # ⚖️ CONFLICT-RESOLVER lanes (2026-10-05, user "add the collision as a real
              # lane + all live signals auto-updating every game"): each bets EXACTLY what
              # its dark-purple badge recommends, gender-conditionally, so the badge shows
              # its own live auto-updating record (m/w split as usual).
              "cr1_stardog", "cr2_cvg", "cr3_fadea", "cr4_grayhate", "cr5_collision",
              # collision split by the favorite's market price (2026-10-05): the pass is
              # NOT uniform -- a 65-85% favorite has been mildly +EV, the extremes negative.
              "cr5_coll_leanfav", "cr5_coll_passfav",
              # ALL-10-agree men pick priced −140..−300 (2026-10-05, user) -- auto-updating.
              "all10_price_m",
              # 🔀 FADE 6-4 SPLIT (2026-10-05, user): heads split 6-4 -> bet the 4-minority
              # side. Forward-tracked from registration (bt +80.7% men but n=17, unvalidated).
              "split64_fade",
              # 🧊 PURE-FORM × mc_c75 (2026-10-06, user "wire that tracker"): on an mc_c75
              # pick, split by whether the pure-results recent-form overlay AGREES or
              # DISAGREES with the c75 side. Live edge is in the DISAGREE cell (men +18.2%,
              # the market overvalues recent form); agree is flat/negative. m/w split as
              # usual. Surfaced on the board/Best/Prices only where the cell's ROI is +.
              "pf_c75_dis", "pf_c75_agr",
              "utr_all", "utr_dog", "utr_mom_hot", "utr_mom_fade",
              "mc4_dog", "mc4_dog_band", "mc4ovr_fav", "mc4ovr_fav_band", "fight_mc4_dog",
              # FORM-FADE split by the pick's side (2026-10-06): forward dogs carry it (+72%),
              # favorites lose (−5%). The board/Best 🧊 tag reads these so it only greens on dogs.
              "pf_c75_dis_dog", "pf_c75_dis_fav",
              # 🔒 HIGH-HIT FAVORITE STACK candidates (2026-10-06, user "track all of these"):
              # favorite + form-confirms, in a price band; ~85-91% hit + small +ROI in-sample,
              # UNVALIDATED (tiny n / multiple-comparison) -- forward-tracked, not yet a take.
              "pf_ghfav", "pf_ghfav_pr", "pf_c75fav_pr", "pf_a10fav_pr")}
    if "model_cma_p1" in log.columns:
        srows = log[log["model_c_p1"].notna() & log["model_cma_p1"].notna()
                    & log["p1_odds"].notna() & log["p2_odds"].notna()]
        for _, r in srows.iterrows():
            d1, d2 = _decimal(r["p1_odds"]), _decimal(r["p2_odds"])
            if not d1 or not d2:
                continue
            i1, i2 = 1 / d1, 1 / d2
            mk1 = i1 / (i1 + i2)
            dog1 = mk1 < 0.5           # defined up front: bet() reads it for the dog/fav split
            cp = float(r["model_c_p1"])
            cma = float(r["model_cma_p1"])
            c1, g1 = cp >= 0.5, cma >= 0.5
            settled = bool(r["settled"]) and pd.notna(r["p1_won"])
            won1 = bool(r["p1_won"]) if settled else None

            _isw = str(r.get("league")) == "wta"

            def bet(key, side1):
                if settled:
                    dec = d1 if side1 else d2
                    pnl9 = 25.0 * (dec - 1.0) if (won1 == side1) else -25.0
                    study[key]["v"].append(pnl9)
                    _g = "vw" if _isw else "vm"
                    _sd = "vd" if (side1 == dog1) else "vf"   # pick is a market DOG iff side1==dog1
                    study[key][_g].append(pnl9)
                    study[key][_sd].append(pnl9)
                    study[key][_g + _sd[1]].append(pnl9)      # gender×side: vmd/vmf/vwd/vwf
                else:
                    study[key]["p"] += 1

            if c1 != g1:                       # C vs gray FIGHT (2026 bt: C-side -1.5%)
                bet("cvg_c", c1)
                bet("cvg_gray", g1)
            dog1 = mk1 < 0.5                   # player_1 is the market dog
            mdog = mk1 if dog1 else 1 - mk1
            gdog = cma if dog1 else 1 - cma
            if gdog - mdog >= 0.04 and (g1 == dog1):   # gray 4pt+ ON the dog (2026 +9.1%)
                bet("gray_dog4", dog1)
            if mdog - gdog >= 0.02:            # gray-hated dog (dog bt -25..-28%, fav +2..4%)
                bet("grayhate_dog", dog1)
                bet("grayhate_fav", not dog1)
                # depth buckets (2026-09-30, user ask): 4-5pt and 5pt+ gold favorites
                # get their own live records; the 5pt+ chip reads the m/w sub-aggs.
                _dp = (mdog - gdog) * 100
                if 4 <= _dp < 5:
                    bet("goldfav_d45", not dog1)
                elif _dp >= 5:
                    bet("goldfav_d5", not dog1)
            # META-LANES mirroring the board colors exactly (2026-09-29, user ask):
            # gold_names = every neon-yellow name ($25 on it); green_names = every PLAIN
            # dark-green name (gray's pick where no gold/red overrides -- the reference
            # color's own record).
            mdog0 = mk1 if dog1 else 1 - mk1
            gdog0 = cma if dog1 else 1 - cma
            hate0 = (mdog0 - gdog0) >= 0.02
            star0 = (c1 == g1) and (g1 == dog1)
            if star0:
                bet("gold_names", g1)
                # PRICED STAR DOG (2026-10-02, backtest-corrected): star-dog ROI RISES
                # monotonically with price -- bt +20.5% at 2.0-2.5 (n=3733), +34.6% at
                # 2.5-3.0, +59% at 3.0-4.0; only <1.8 dogs are dead (-2%). So the filter
                # is "dog decimal >= 2.0" (plus-money), NOT a 2.0-3.0 cap (the live cap
                # was an 18-bet artifact). Longer price = higher ROI + higher variance.
                _ddec = d1 if dog1 else d2
                if _ddec >= 2.0:
                    bet("stardog_prime", dog1)
                    # APEX DOG (2026-10-02): the maximal validated stack -- C-alone+gray
                    # dog AND priced (>=2.0). Live +47.6% (and +70.8% on the men's half);
                    # each component backtest-validated. The board's best-pick tier.
                    _axa, _axb = r.get("model_a_p1"), r.get("model_b_p1")
                    if pd.notna(_axa) and pd.notna(_axb) \
                            and (float(_axa) >= 0.5) != c1 and (float(_axb) >= 0.5) != c1:
                        bet("apex_dog", dog1)
                # LATE-ROUND watch (2026-10-02, user ask): C+gray dog in QF/SF/F etc.
                # (not R1/qualifying) -- live +18% on 19, thin. Possibly confounded
                # (later rounds = fewer, higher-quality matches). Tracked as a watch.
                _rnd = str(r.get("round") or "").lower()
                if not ("1st" in _rnd or "qual" in _rnd or "128" in _rnd or "of 64" in _rnd):
                    bet("cgray_dog_late", dog1)
            elif hate0:
                bet("gold_names", not dog1)
            ap, bp = r.get("model_a_p1"), r.get("model_b_p1")
            _passfav = False
            if pd.notna(ap) and pd.notna(bp):
                _a1, _b1 = float(ap) >= 0.5, float(bp) >= 0.5
                _passfav = (_a1 != c1 and _b1 != c1 and g1 == c1 and c1 != dog1)
            if not star0 and not hate0 and not _passfav:
                bet("green_names", g1)
            # TIER LANES (registered 2026-09-30, user ask "live test how each tier does"):
            # $25 on the tier ribbon's side from today forward only -- mirrors the
            # TennisSection tier logic exactly (keep in lockstep with the frontend).
            # TIER 1/2 bet the star dog, TIER 3 bets the fade-gold favorite; AVOID bets
            # C's side and NO BET bets gray's side so the ledger proves the pass verdicts.
            _alone9 = (pd.notna(ap) and pd.notna(bp)
                       and (float(ap) >= 0.5) != c1 and (float(bp) >= 0.5) != c1)
            if star0 and (_alone9 or (gdog0 - mdog0) >= 0.04):
                _tk, _ts = "tier1", dog1
            elif star0:
                _tk, _ts = "tier2", dog1
            elif hate0:
                _tk, _ts = "tier3", not dog1
            elif (_alone9 and g1 == c1 and c1 != dog1) or c1 != g1:
                # C+GRAY FAV DEMOTED back to AVOID (2026-10-02, user call): live -6.7%
                # on 31 settles -- the favorite half of C-alone+gray loses (the DOG half
                # is the +40% play). Only fade-gold stays in TIER 3 now.
                _tk, _ts = "tier_avoid", c1
            else:
                _tk, _ts = "tier_nobet", g1
            if str(r.get("date") or "") >= "2026-09-30":
                bet(_tk, _ts)
            # ⚖️ CONFLICT RESOLVERS as their own auto-updating lanes (2026-10-05). Each bets
            # the gender-specific side its board badge tells you to trust, so the badge can
            # cite its own live record. Gender via bet()'s vm/vw split.
            _dp9 = r.get("model_d_p1")
            _d1_9 = (float(_dp9) >= 0.5) if pd.notna(_dp9) else None
            # ① C+gray both on the market dog, MEN only -> take the dog.
            if star0 and not _isw:
                bet("cr1_stardog", dog1)
            # ② C vs gray disagree -> men side with C, women side with gray.
            if c1 != g1:
                bet("cr2_cvg", g1 if _isw else c1)
            # ③ A dissents from B&C, MEN only -> take the B&C side (fade A).
            if pd.notna(ap) and pd.notna(bp) and not _isw:
                _a1b, _b1b = float(ap) >= 0.5, float(bp) >= 0.5
                if _a1b != _b1b and _b1b == c1:
                    bet("cr3_fadea", _b1b)
            # ④ gray hates the dog -> men take the favorite, women take the dog.
            if hate0:
                bet("cr4_grayhate", dog1 if _isw else (not dog1))
            # ⑤ COLLISION (the "20-8" lane): ALL base models (A,B,C,gray,D) on the market
            # favorite AND gray hates the dog -> take the DOG. Women edge (+8.3% n28 at
            # build); tracked for both via m/w split.
            if hate0 and _d1_9 is not None and pd.notna(ap) and pd.notna(bp):
                _onfav = lambda x1: x1 == (not dog1)
                if (_onfav(float(ap) >= 0.5) and _onfav(float(bp) >= 0.5) and _onfav(c1)
                        and _onfav(g1) and _onfav(_d1_9)):
                    bet("cr5_collision", dog1)
                    # price-split on the FAVORITE side: 65-85% fav mildly +EV, else pass.
                    _favp = max(mk1, 1 - mk1)
                    bet("cr5_coll_leanfav" if 0.65 <= _favp < 0.85
                        else "cr5_coll_passfav", not dog1)
            # ALL-10 AGREE price lane (2026-10-05, user "mark −140..−300 all-10, auto-update"):
            # MEN only. All 10 model heads on the same side AND the pick priced −140..−300 ->
            # the band spot that pays (+12.8% at build; −200..−300 is the strong half).
            if not _isw:
                _cols = [ap, bp, r.get("model_c_p1"), r.get("model_cma_p1"), _dp9,
                         r.get("model_dma_p1"), r.get("mc_p1"), r.get("mc_c_p1"),
                         r.get("mc_c75_p1"), r.get("mc_cutr_p1")]
                if all(pd.notna(x) for x in _cols):
                    _sd = [float(x) >= 0.5 for x in _cols]
                    if len(set(_sd)) == 1:
                        _a10side = _sd[0]
                        _a10od = r.get("p1_odds") if _a10side else r.get("p2_odds")
                        if pd.notna(_a10od) and -300 <= float(_a10od) <= -140:
                            bet("all10_price_m", _a10side)
            # 🔀 FADE 6-4 SPLIT (2026-10-05, user "watch the 4/6"): the 10 heads split exactly
            # 6-4 -> bet the 4-MINORITY side (fade the slim majority). Forward-tracked from
            # registration day only (bt +80.7% men / +58% all, n=17 -- noise, unvalidated).
            if str(r.get("date") or "") >= "2026-10-05":
                _c6 = [ap, bp, r.get("model_c_p1"), r.get("model_cma_p1"), _dp9,
                       r.get("model_dma_p1"), r.get("mc_p1"), r.get("mc_c_p1"),
                       r.get("mc_c75_p1"), r.get("mc_cutr_p1")]
                if all(pd.notna(x) for x in _c6):
                    _nt6 = sum(1 for x in _c6 if float(x) >= 0.5)   # heads on p1
                    if _nt6 in (4, 6):                              # exactly 6-4
                        bet("split64_fade", _nt6 == 4)             # take the 4-side (p1 iff 4 on p1)
            # 🧊 PURE-FORM × mc_c75 (2026-10-06, user "wire that tracker"): on every mc_c75
            # pick, bet the c75 side and bucket by whether the pure-results recent-form
            # overlay agrees or disagrees with it. The live edge is in the DISAGREE bucket
            # (market overvalues recent form); m/w split via bet(). pf_edge_p1 frozen at
            # first serve; backfilled for pre-2026-10-06 games so the lane has sample now.
            # FORWARD-ONLY (2026-10-06): the pf_* lanes exclude reconstructed rows, same as the
            # mc_c75 lanes -- otherwise backfilled history inflates them. And FORM-FADE is split
            # dog/fav because the edge is ALL in the dogs (forward dogs +72%, favorites −5%).
            _recon_pf = bool(r.get("mc_c_recon")) if pd.notna(r.get("mc_c_recon")) else False
            _c75v = r.get("mc_c75_p1")
            _pfe = r.get("pf_edge_p1")
            if pd.notna(_c75v) and pd.notna(_pfe) and not _recon_pf:
                _c75s = float(_c75v) >= 0.5
                _pf_agree = (float(_pfe) > 0) == _c75s
                if _pf_agree:
                    bet("pf_c75_agr", _c75s)
                else:
                    bet("pf_c75_dis", _c75s)                       # FORM-FADE (take the model side)
                    bet("pf_c75_dis_dog" if (_c75s == dog1) else "pf_c75_dis_fav", _c75s)
            # 📏 REAL-UTR lanes (2026-10-07, user "get real utr data ... do tests with it"):
            # UTR's public API serves CURRENT ratings only -> these are FORWARD-ONLY lanes
            # (a retro test with today's rating would leak the results it was built from).
            # utr_all   = $25 on the higher-real-UTR side, every rated match (the judge:
            #             does the real rating beat the market at all?)
            # utr_dog   = the market DOG is the HIGHER-rated player by >=0.2 (the market
            #             prices someone below their established level)
            # utr_mom_hot/fade = 3mo form rating vs established level, gap >=0.2: back the
            #             hotter side vs fade it (the form-fade thesis says fade wins).
            _ue9 = r.get("utr_edge_p1")
            _um9 = r.get("utr_mom_p1")
            if pd.notna(_ue9) and float(_ue9) != 0:
                _uS = float(_ue9) > 0
                bet("utr_all", _uS)
                if abs(float(_ue9)) >= 0.2 and _uS == dog1:
                    bet("utr_dog", _uS)
            if pd.notna(_um9) and abs(float(_um9)) >= 0.2:
                bet("utr_mom_hot", float(_um9) > 0)
                bet("utr_mom_fade", float(_um9) <= 0)
            # 🔒 HIGH-HIT FAVORITE STACKS (2026-10-06, user "track all of these on the $25
            # tab"): a heavy favorite that recent FORM confirms (form on the fav), in a sane
            # price band -- candidates that scanned ~85-91% hit + small +ROI IN-SAMPLE.
            # UNVALIDATED (tiny n, found by scanning many gate×price combos = multiple-
            # comparison risk). Forward-tracked from today to see if they hold out of sample.
            if pd.notna(_pfe) and not _recon_pf:
                _favside = not dog1                        # the market favorite (p1-bool)
                _formfav = (float(_pfe) > 0) == _favside    # recent form backs the favorite
                _favimp = max(mk1, 1 - mk1)
                if _formfav:
                    if hate0:
                        bet("pf_ghfav", _favside)                       # grayhate+form (any price)
                        if 0.75 <= _favimp <= 0.88:
                            bet("pf_ghfav_pr", _favside)                # + priced −300..−730
                    if pd.notna(_c75v) and (float(_c75v) >= 0.5) == _favside and 0.78 <= _favimp <= 0.88:
                        bet("pf_c75fav_pr", _favside)                   # c75 IS the fav + priced
                    _allc = [ap, bp, r.get("model_c_p1"), r.get("model_cma_p1"), _dp9,
                             r.get("model_dma_p1"), r.get("mc_p1"), r.get("mc_c_p1"),
                             r.get("mc_c75_p1"), r.get("mc_cutr_p1")]
                    if all(pd.notna(x) for x in _allc):
                        _allsd = [float(x) >= 0.5 for x in _allc]
                        if len(set(_allsd)) == 1 and _allsd[0] == _favside and 0.78 <= _favimp <= 0.88:
                            bet("pf_a10fav_pr", _favside)               # ALL-10 on the fav + priced
            # MODEL D lanes (registered 2026-09-30, user "live test how D does"):
            # d_all = D's side every match; dma_all = D's gray head; d_gray_dog = D +
            # its gray on a market dog (bt decayed +9.3 -> +10.1 -> +1.1 -- this lane is
            # the live judge); d_alone = D against A, B AND C (bt says zero info).
            _dp0, _dg0 = r.get("model_d_p1"), r.get("model_dma_p1")
            if pd.notna(_dp0):
                _d1 = float(_dp0) >= 0.5
                bet("d_all", _d1)
                if pd.notna(_dg0):
                    _dg1 = float(_dg0) >= 0.5
                    bet("dma_all", _dg1)
                    if _d1 == _dg1 and _d1 == dog1:
                        bet("d_gray_dog", _d1)
                    # D-MA 2pt EDGE (2026-10-04, user ask): the market-aware D head's side
                    # where its prob on that side is >=2pts OVER the market's implied -- the
                    # only mkt-aware head that's +ROI when it dissents (backfill +7.5%/53).
                    _dside = float(_dg0) if _dg1 else 1 - float(_dg0)
                    _mside = mk1 if _dg1 else 1 - mk1
                    if _dside - _mside >= 0.02:
                        bet("dma_edge2", _dg1)
                if pd.notna(ap) and pd.notna(bp):
                    if (float(ap) >= 0.5) != _d1 and (float(bp) >= 0.5) != _d1 and c1 != _d1:
                        bet("d_alone", _d1)
            # MONTE CARLO lanes (registered 2026-10-01, user ask): $25 on the side the
            # 100k-sim MC favors, every match -- plus the slice where MC backs the dog.
            _mc0 = r.get("mc_p1")
            if pd.notna(_mc0):
                _mc1 = float(_mc0) >= 0.5
                bet("mc_all", _mc1)
                # MC TOSS-UP (2026-10-02, user ask): MC's closest calls (confidence
                # 50-60%) -- live +15.3% on 13, thin/watch. The one MC bucket positive
                # live; mechanism unclear (MC defers to market on coin-flips).
                _mcconf = max(float(_mc0), 1 - float(_mc0))
                if 0.50 <= _mcconf < 0.60:
                    bet("mc_tossup", _mc1)
                if _mc1 == dog1:
                    bet("mc_dog", _mc1)
                    # user hypothesis (2026-10-01, Jacquet case): "if it's favoring a
                    # dog THAT much the dog probably wins" -- MC backs the market dog
                    # with >=60% sim confidence. Forward-tracked, unproven.
                    _dp = float(_mc0) if dog1 else 1 - float(_mc0)
                    if _dp >= 0.60:
                        bet("mc_dog_big", _mc1)
                        # the ONLY profitable MC-dog slice in backtest (+19.3% vs -6.0%
                        # for the raw big dog): the MC big dog that GRAY also likes.
                        if g1 == dog1:
                            bet("mc_biggray", _mc1)
                # MC co-fire lanes (registered 2026-10-02, user ask). TRACKED, NOT TAKES
                # -- backtest says MC+4of4 -2.2% (29k) and MC+gold inherits gold's thin
                # favorite; live samples days old. Mark the slips, judge over time.
                _gold_side = (dog1 if star0 else ((not dog1) if hate0 else None))
                if _gold_side is not None and _mc1 == _gold_side:
                    bet("mc_gold", _gold_side)
                if (not star0) and (not hate0) and (not _passfav) and _mc1 == g1:
                    bet("mc_green", g1)
                if pd.notna(ap) and pd.notna(bp) and pd.notna(_dp0):
                    if (float(ap) >= 0.5) == (float(bp) >= 0.5) == c1 == (float(_dp0) >= 0.5) \
                            and _mc1 == c1:
                        bet("mc_4of4", c1)
            # MODEL-C MONTE CARLO lanes (registered 2026-10-02, user "track all monte carlo
            # c picks + how it does agreeing with model d monte carlo"). mc_c_all = $25 on
            # the C-anchored serve MC's side every match; mc_c_and_d = the C-MC and the
            # Model-D serve MC (mc_p1) land on the SAME side. Tracked, not takes.
            # forward lanes EXCLUDE reconstructed history rows (mc_c_recon True) -- those
            # are display-only, simmed after the fact; only genuine forward picks count.
            _recon = bool(r.get("mc_c_recon")) if pd.notna(r.get("mc_c_recon")) else False
            _mcc0 = r.get("mc_c_p1")
            if pd.notna(_mcc0) and not _recon:
                _mcc1 = float(_mcc0) >= 0.5
                bet("mc_c_all", _mcc1)
                if pd.notna(_mc0) and (float(_mc0) >= 0.5) == _mcc1:
                    bet("mc_c_and_d", _mcc1)
            # the two invisible C-MC variants, same $25-every-match lane as mc_c_all so the
            # three anchorings (c50 / c75 / cutr) are judged head-to-head (user 2026-10-02).
            _mc75 = r.get("mc_c75_p1")
            if pd.notna(_mc75) and not _recon:
                _c75b = float(_mc75) >= 0.5
                bet("mc_c75_all", _c75b)
                # DOG/FAV split (2026-10-06, user "split it that way"): the c75 edge lives
                # entirely in the dogs (men +34.6%); favorites are flat/neg (−6.7%). Splitting
                # stops a dog-earned ROI from displaying on a favorite pick. c75 side is the
                # market dog when its p1-bool matches dog1.
                _c75dog = (_c75b == dog1)
                bet("mc_c75_dog" if _c75dog else "mc_c75_fav", _c75b)
                # POSITIVE-ROI FAVORITE SIGNAL (2026-10-06, user "find a positive roi favorite
                # signal"): a c75 FAVORITE that recent FORM disagrees with = men +7.5% (n82) --
                # the only favorite cell that pays. Form-backed favorites are −8%. Fade the form.
                _pf75 = r.get("pf_edge_p1")
                if (not _c75dog) and pd.notna(_pf75) and ((float(_pf75) > 0) != _c75b):
                    bet("c75fav_formfade", _c75b)
            # user's take (2026-10-03): "I'm taking every game c-MC and c75 agree on" --
            # $25 on the agreed side whenever c50 and c75 land together (forward only).
            if pd.notna(_mcc0) and pd.notna(_mc75) and not _recon:
                if (float(_mcc0) >= 0.5) == (float(_mc75) >= 0.5):
                    bet("mcc_c75_agree", float(_mcc0) >= 0.5)
                    # user hypothesis (2026-10-04): a market DOG that c50 AND c75 like AND
                    # Model D also backs. Backfill said D-agrees is WORSE (46% vs 58% base),
                    # but forward sample n=2 -- this lane is the live judge. Also track the
                    # D-against half so the two can diverge on real settles.
                    _dd0 = r.get("model_d_p1")
                    _agd = (float(_mcc0) >= 0.5) == (float(_mc75) >= 0.5)
                    _side = float(_mcc0) >= 0.5
                    _isdog = (mk1 < 0.5) == _side
                    # c50+c75 on the market DOG, regardless of Model D (2026-10-04 analysis:
                    # 47% actual vs 38% implied, flat +19%). The take; D-split tracked below.
                    if _isdog:
                        bet("cc75_dog", _side)
                    if _agd and _isdog and pd.notna(_dd0):
                        if (float(_dd0) >= 0.5) == _side:
                            bet("cc75_d_dog", _side)
                        else:
                            bet("cc75_nod_dog", _side)
            _mcutr = r.get("mc_cutr_p1")
            if pd.notna(_mcutr) and not _recon:
                bet("mc_cutr_all", float(_mcutr) >= 0.5)
            # ⚄⚄ ALL-4 MONTE CARLOS ON THE DOG (2026-10-08, user "a dog priced +100 to
            # +250 like Aliona should have been on the best tab" — promoted on the
            # measured cell: banded 15-15 +17.3%, outside the band 0-7): D-serve MC +
            # c50 + c75 + cUTR all on the market underdog. mc4_dog = any price (the
            # honest control); mc4_dog_band = +100..+250 only (the Best-tab signal).
            if (pd.notna(_mc0) and pd.notna(_mcc0) and pd.notna(_mc75)
                    and pd.notna(_mcutr) and not _recon):
                _s4 = [float(_mc0) >= 0.5, float(_mcc0) >= 0.5,
                       float(_mc75) >= 0.5, float(_mcutr) >= 0.5]
                if len(set(_s4)) == 1 and _s4[0] == dog1:
                    bet("mc4_dog", _s4[0])
                    _od4 = r.get("p1_odds") if _s4[0] else r.get("p2_odds")
                    if pd.notna(_od4) and 100 <= float(_od4) <= 250:
                        bet("mc4_dog_band", _s4[0])
                        # ⚔→🐕 FIGHT-FLIP (2026-10-08, user "gray fight favorites alone
                        # get overpowered if all MCs are on the dog — change every bet
                        # like that to the dog"): gray fights C onto the FAVORITE while
                        # ALL FOUR sims take the banded dog -> bet the DOG. 10-6 +48.1%
                        # banded at registration (men 7-2 +78%); outside the band 0-3.
                        if c1 != g1 and g1 != dog1:
                            bet("fight_mc4_dog", _s4[0])
                # ⚄ ALL-4 MCs OVER THE MARKET on the FAVORITE (2026-10-08, user "add the
                # -200 to -300 picks to the best tab" — promoted at n=6, 6-0 +41.8% in
                # that pocket; any-price control is breakeven, -100/-200 loses -10%,
                # >=10pt sim edges are 1-5: ONLY the -200..-300 band is marked).
                _favb9 = not dog1
                _mkf9 = max(mk1, 1 - mk1)
                _pf49 = [float(v) if _favb9 else 1 - float(v)
                         for v in (_mc0, _mcc0, _mc75, _mcutr)]
                if all(p9 > _mkf9 for p9 in _pf49):
                    bet("mc4ovr_fav", _favb9)
                    _odf9 = r.get("p1_odds") if _favb9 else r.get("p2_odds")
                    if pd.notna(_odf9) and -300 <= float(_odf9) <= -200:
                        bet("mc4ovr_fav_band", _favb9)
            # MODEL X lanes (2026-10-03): x_all = $25 on Model X's side every match;
            # x_edge2 = only where X disagrees with the market by 2+ points (where a meta-
            # model could actually have an edge over the price).
            _mx0 = r.get("model_x_p1")
            _mxrecon = bool(r.get("model_x_recon")) if pd.notna(r.get("model_x_recon")) else False
            if pd.notna(_mx0) and not _mxrecon:
                _mx1 = float(_mx0) >= 0.5
                bet("model_x_all", _mx1)
                d1x, d2x = _decimal(r.get("p1_odds")), _decimal(r.get("p2_odds"))
                if d1x and d2x:
                    i1x, i2x = 1 / d1x, 1 / d2x
                    mkx = i1x / (i1x + i2x)
                    if abs(float(_mx0) - mkx) >= 0.02:
                        bet("model_x_edge2", _mx1)
            # ALL-10 AGREE (2026-10-04, user ask): every model + MC on the SAME side --
            # A, B, C, gray, D, D-ma, serve-MC, c50, c75, cUTR. 80% hit / +4.4% backfill,
            # near-always a clear favorite (highest-hit marker). Forward only (skip recon).
            _a10 = [r.get(k) for k in ("model_a_p1", "model_b_p1", "model_c_p1",
                    "model_cma_p1", "model_d_p1", "model_dma_p1", "mc_p1", "mc_c_p1",
                    "mc_c75_p1", "mc_cutr_p1")]
            if not _recon and all(pd.notna(v) for v in _a10):
                _s10 = [float(v) >= 0.5 for v in _a10]
                if all(x == _s10[0] for x in _s10):
                    bet("all10_agree", _s10[0])
            # AGAINST-A watch (2026-10-04, user ask): $25 on the OPPOSITE of Model A's pick
            # every match. A is the weakest model (52% win / -10% flat), so straight-fading
            # it is a natural watch -- but live it's 49% / -4% (fading A blindly also catches
            # A's correct calls). Watch lane; the validated fade is fade_a (A vs B&C) below.
            if pd.notna(ap):
                bet("against_a", not (float(ap) >= 0.5))
            # FADE-A lane (registered 2026-09-30): A against BOTH B and C -> $25 on the
            # B&C side. bt: +8.0%/5,080 all-years; dog side +14.8%; dog+gray +20.5%
            # (2026 +19.7%). A-alone's own side bt -20.6% (live 13-39, -34%).
            if pd.notna(ap) and pd.notna(bp):
                _fa1, _fb1 = float(ap) >= 0.5, float(bp) >= 0.5
                if _fa1 != _fb1 and _fb1 == c1:
                    bet("fade_a", _fb1)
                    # sub-cells (2026-09-30, user "add these all to our board"):
                    # dog +14.8/+11.5, dog+gray +20.5/+19.7, fav thin +2.4/+1.6
                    if _fb1 == dog1:
                        bet("fade_a_dog", _fb1)
                        if g1 == _fb1:
                            bet("fade_a_dog_gray", _fb1)
                    else:
                        bet("fade_a_fav", _fb1)
            if pd.notna(ap) and pd.notna(bp):
                a1, b1 = float(ap) >= 0.5, float(bp) >= 0.5
                if a1 == b1 == c1:             # all three agree (bt -1.9%; dog 2026 +0.3%)
                    bet("abc_agree", c1)
                    if c1 == dog1:
                        bet("abc_dog", c1)
                # C ALONE + GRAY CONFIRMS (registered 2026-09-29): the best large-sample
                # cell found -- bt +15.1%/6,778 (2026 +9.5%); DOG half +25.2%/3,097
                # (2026 +16.8%). Without gray confirmation C-alone went 0-4 live.
                # ALL SIX heads agree (exact, from frozen A/B gray heads; 2026-09-30)
                amap, bmap = r.get("model_ama_p1"), r.get("model_bma_p1")
                if pd.notna(amap) and pd.notna(bmap):
                    if a1 == b1 == c1 == g1 == (float(amap) >= 0.5) == (float(bmap) >= 0.5):
                        bet("all6_agree", c1)
                if a1 != c1 and b1 != c1 and g1 == c1:
                    bet("c_alone_gray", c1)
                    if c1 == dog1:
                        bet("c_alone_gray_dog", c1)
                    else:
                        # the RED-flagged pass config (board highlights the name red)
                        bet("c_alone_gray_fav", c1)
    study_out = {k: {**agg(d["v"]), "pending": int(d["p"]),
                     "m": agg(d["vm"]), "w": agg(d["vw"]),
                     "dog": agg(d["vd"]), "fav": agg(d["vf"]),
                     "m_dog": agg(d["vmd"]), "m_fav": agg(d["vmf"]),
                     "w_dog": agg(d["vwd"]), "w_fav": agg(d["vwf"])} for k, d in study.items()}
    # PRICE-BAND Best-pick records (2026-10-05, user: live color-coded legend on the Prices
    # tab). For each settled MEN game: the Best pick (top gated signal) bucketed by its price
    # (dog +100..+250 / chalk −300..−600), plus the ALL-10 split (−200..−300 / −140..−200).
    # Auto-recomputes every call; merged into study_out so the frontend reads them live.
    def _gate_m(key):
        o = study_out.get(key, {}).get("m") or {}
        n = o.get("n") or 0
        return n >= 20 and 100 * o["wins"] / n >= 65 and (o.get("roi_pct") or -99) >= 4
    _pb = {k: [] for k in ("price_dog_m", "price_chalk_m", "all10_200_300_m", "all10_140_200_m")}
    _sm = log[(log["settled"] == True) & log["p1_won"].notna() & log["model_c_p1"].notna()  # noqa: E712
              & log["model_cma_p1"].notna() & log["p1_odds"].notna() & log["p2_odds"].notna()]
    for _, rr in _sm.iterrows():
        if str(rr.get("league")).lower() in ("wta", "itf_women"):
            continue
        d1b, d2b = _decimal(rr["p1_odds"]), _decimal(rr["p2_odds"])
        if not d1b or not d2b:
            continue
        mkb = (1 / d1b) / ((1 / d1b) + (1 / d2b))

        def _bb(c):
            v = rr.get(c)
            return None if (v is None or pd.isna(v)) else (float(v) >= 0.5)
        c1b, g1b = _bb("model_c_p1"), _bb("model_cma_p1")
        if c1b is None or g1b is None:
            continue
        won1b = bool(rr["p1_won"])
        dgb = mkb < 0.5
        ab, bbb, dbb = _bb("model_a_p1"), _bb("model_b_p1"), _bb("model_d_p1")
        dmab, c50b, c75b, cub, mcdb = (_bb("model_dma_p1"), _bb("mc_c_p1"), _bb("mc_c75_p1"),
                                       _bb("mc_cutr_p1"), _bb("mc_p1"))
        cmab = rr.get("model_cma_p1")
        gpb = float(cmab) if pd.notna(cmab) else None
        mdogb = mkb if dgb else 1 - mkb
        gdogb = (gpb if dgb else 1 - gpb) if gpb is not None else mdogb
        hateb = (mdogb - gdogb) >= 0.02
        d5b = (mdogb - gdogb) >= 0.05
        dmaedge = False
        if dmab is not None and pd.notna(rr.get("model_dma_p1")):
            dpb = float(rr["model_dma_p1"])
            dmaedge = ((dpb if dmab else 1 - dpb) - (mkb if dmab else 1 - mkb)) >= 0.02
        cand = []

        def _add(key, side):
            if side is not None and _gate_m(key):
                cand.append((study_out[key]["m"]["roi_pct"], side))
        _add("mc_c75_all", c75b)
        if c50b is not None and c75b is not None and c50b == c75b:
            _add("mcc_c75_agree", c75b)
        if dmaedge:
            _add("dma_edge2", dmab)
        allvb = [ab, bbb, c1b, g1b, dbb, dmab, mcdb, c50b, c75b, cub]
        all10b = all(x is not None for x in allvb) and len(set(allvb)) == 1
        if all10b:
            _add("all10_agree", ab)
        if None not in (ab, bbb, dbb, c50b) and ab == bbb == c1b == dbb == c50b:
            _add("mc_4of4", c1b)
        if c1b != g1b:
            _add("cvg_gray", g1b)
        if d5b:
            _add("goldfav_d5", not dgb)
        if hateb:
            _add("grayhate_fav", not dgb)
        if None not in (ab, bbb) and ab != bbb and bbb == c1b and bbb != dgb:
            _add("fade_a_fav", bbb)
        if None not in (ab, bbb) and ab != bbb and bbb == c1b:
            _add("fade_a", bbb)
        if None not in (ab, bbb) and ab != c1b and bbb != c1b and g1b == c1b:
            _add("c_alone_gray", c1b)
        if c1b == g1b == dgb:
            _add("gold_names", c1b)
        elif hateb:
            _add("gold_names", not dgb)
        if cand:
            cand.sort(reverse=True)
            sp = cand[0][1]
            op = float(rr["p1_odds"] if sp else rr["p2_odds"])
            pn = (25 * ((d1b if sp else d2b) - 1)) if (sp == won1b) else -25
            if 100 <= op <= 250:
                _pb["price_dog_m"].append(pn)
            elif -600 <= op <= -300:
                _pb["price_chalk_m"].append(pn)
        if all10b:
            op = float(rr["p1_odds"] if ab else rr["p2_odds"])
            pn = (25 * ((d1b if ab else d2b) - 1)) if (ab == won1b) else -25
            if -300 <= op <= -200:
                _pb["all10_200_300_m"].append(pn)
            elif -200 < op <= -140:
                _pb["all10_140_200_m"].append(pn)
    for _k, _v in _pb.items():
        study_out[_k] = {**agg(_v), "m": agg(_v), "w": agg([])}

    # 🔵★2+ BLUE 2-STACK lane (2026-10-07, user "mark these ones too"): a men DOG priced
    # +100..+250 whose Best pick carries 2+ DISTINCT signal FAMILIES under the side-aware
    # gate (the Best tab's current logic). +55.5% (16-7, n23) at build -- the board's best
    # measured cell. Auto-recomputes every call; the Best/Prices 💎 A+ badge reads this.
    _FAM2 = {"mc_c75_dog": "mc", "mcc_c75_agree": "mc", "mc4_dog_band": "mc", "mc4ovr_fav_band": "mc", "fight_mc4_dog": "mc", "mc_4of4": "consensus",
             "all10_agree": "consensus", "dma_edge2": "dma", "cvg_gray": "gray",
             "mc_green": "gray", "goldfav_d5": "gold", "grayhate_fav": "gold",
             "gold_names": "gold", "c_alone_gray": "calone", "fade_a": "fadea",
             "fade_a_fav": "fadea"}

    def _gate_sa(key, isdog, gen="m"):
        o = study_out.get(key, {}).get(f"{gen}_{'dog' if isdog else 'fav'}") or {}
        n = o.get("n") or 0
        if n < 12 or o.get("roi_pct") is None:
            return None
        hit = 100 * o["wins"] / n
        roi = o["roi_pct"]
        return roi if ((hit >= 65 and roi >= 4) or roi >= 15) else None
    _b2 = []
    # 🤝 BOTH-TABS OVERLAP lanes (2026-10-07, user "when the favorites overlap mark it on
    # the best tab"): a settled game where the Best-tab pick (side-aware gated signals)
    # AND the ⭐ Picks sheet (c50+c75 agree & over the market) land on the SAME side.
    # ovl_fav = that side is the market FAVORITE (replay: 19-3 +26.7%, the only favorite
    # cell that has paid); ovl_dog = the dog half. Both genders; $25 flat.
    _ovf = {"m": [], "w": []}
    _ovd = {"m": [], "w": []}
    # WOMEN'S dog price band (2026-10-08, user "mark the women ones too"): the women's
    # Best pick on a +100..+250 market dog — the analogue of price_dog_m, gated on the
    # women's side-aware cells. Feeds the 🔵 band badge + 💰 Prices tab for women.
    _pdw = []
    for _, rr in _sm.iterrows():
        genb = "w" if str(rr.get("league")).lower() in ("wta", "itf_women") else "m"
        d1b, d2b = _decimal(rr["p1_odds"]), _decimal(rr["p2_odds"])
        if not d1b or not d2b:
            continue
        mkb = (1 / d1b) / ((1 / d1b) + (1 / d2b))
        dgb = mkb < 0.5

        def _bb2(c):
            v = rr.get(c)
            return None if (v is None or pd.isna(v)) else (float(v) >= 0.5)
        c1b, g1b = _bb2("model_c_p1"), _bb2("model_cma_p1")
        if c1b is None or g1b is None:
            continue
        ab, bbb, dbb = _bb2("model_a_p1"), _bb2("model_b_p1"), _bb2("model_d_p1")
        dmab, c50b, c75b, cub, mcdb = (_bb2("model_dma_p1"), _bb2("mc_c_p1"),
                                       _bb2("mc_c75_p1"), _bb2("mc_cutr_p1"), _bb2("mc_p1"))
        gpb = float(rr["model_cma_p1"])
        mdogb = mkb if dgb else 1 - mkb
        gdogb = gpb if dgb else 1 - gpb
        hateb = (mdogb - gdogb) >= 0.02
        star0b = (c1b == g1b and g1b == dgb)
        passfavb = (ab is not None and bbb is not None and ab != c1b and bbb != c1b
                    and g1b == c1b and c1b != dgb)
        fires = []

        def _F(k, side):
            if side is None:
                return
            roi = _gate_sa(k, side == dgb, genb)
            if roi is not None:
                fires.append((roi, k, side))
        if c75b is not None and c75b == dgb:
            _F("mc_c75_dog", c75b)
        if c50b is not None and c75b is not None and c50b == c75b:
            _F("mcc_c75_agree", c75b)
        # ⚄⚄ all-4 MCs on a banded dog (2026-10-08, lockstep with _best_tab_side)
        _mc4b0 = False
        if (None not in (mcdb, c50b, c75b, cub) and mcdb == c50b == c75b == cub
                and c50b == dgb):
            _od4b = rr.get("p1_odds") if c50b else rr.get("p2_odds")
            if pd.notna(_od4b) and 100 <= float(_od4b) <= 250:
                _mc4b0 = True
                _F("mc4_dog_band", c50b)
                if c1b != g1b and g1b != dgb:
                    _cf0 = study_out.get("fight_mc4_dog") or {}
                    fires.append(((_cf0.get("roi_pct") or 48.0), "fight_mc4_dog", c50b))
        if dmab is not None and pd.notna(rr.get("model_dma_p1")):
            dpb = float(rr["model_dma_p1"])
            if ((dpb if dmab else 1 - dpb) - (mkb if dmab else 1 - mkb)) >= 0.02:
                _F("dma_edge2", dmab)
        allvb = [ab, bbb, c1b, g1b, dbb, dmab, mcdb, c50b, c75b, cub]
        if all(x is not None for x in allvb) and len(set(allvb)) == 1:
            _F("all10_agree", ab)
        if None not in (ab, bbb, dbb, c50b) and ab == bbb == c1b == dbb == c50b:
            _F("mc_4of4", c1b)
        if c1b != g1b and not (_mc4b0 and g1b != dgb):
            _F("cvg_gray", g1b)
        if mcdb is not None and (not star0b) and (not hateb) and (not passfavb) and mcdb == g1b:
            _F("mc_green", g1b)
        if (mdogb - gdogb) >= 0.05:
            _F("goldfav_d5", not dgb)
        if hateb:
            _F("grayhate_fav", not dgb)
        if star0b:
            _F("gold_names", c1b)
        elif hateb:
            _F("gold_names", not dgb)
        if None not in (ab, bbb) and ab != c1b and bbb != c1b and g1b == c1b:
            _F("c_alone_gray", c1b)
        if None not in (ab, bbb) and ab != bbb and bbb == c1b and bbb != dgb:
            _F("fade_a_fav", bbb)
        if None not in (ab, bbb) and ab != bbb and bbb == c1b:
            _F("fade_a", bbb)
        # the two MEN-FAVORITE price signals the Best tab also pushes (lockstep w/ frontend)
        if genb == "m":
            _favside = not dgb
            _favod = rr.get("p1_odds") if _favside else rr.get("p2_odds")
            _favod = float(_favod) if pd.notna(_favod) else None

            def _Ffav(k, cond):
                c9 = study_out.get(k, {}).get("m") or {}
                if cond and (c9.get("n") or 0) >= 12 and (c9.get("roi_pct") or 0) > 0:
                    fires.append((c9["roi_pct"], k, _favside))
            allok = all(x is not None for x in allvb) and len(set(allvb)) == 1
            _Ffav("all10_price_m", allok and allvb[0] == _favside
                  and _favod is not None and -300 <= _favod <= -140)
            _Ffav("cr5_coll_leanfav", hateb and None not in (ab, bbb, dbb)
                  and ab == _favside and bbb == _favside and c1b == _favside
                  and g1b == _favside and dbb == _favside
                  and 0.65 <= max(mkb, 1 - mkb) <= 0.85)
        # ⚄ 4-MC over-market fav -200..-300 (2026-10-08, lockstep w/ _best_tab_side)
        _v4b = [rr.get("mc_p1"), rr.get("mc_c_p1"), rr.get("mc_c75_p1"), rr.get("mc_cutr_p1")]
        if all(pd.notna(v) for v in _v4b):
            _favb0 = not dgb
            _mkf0 = max(mkb, 1 - mkb)
            if all((float(v) if _favb0 else 1 - float(v)) > _mkf0 for v in _v4b):
                _odf0 = rr.get("p1_odds") if _favb0 else rr.get("p2_odds")
                if pd.notna(_odf0) and -300 <= float(_odf0) <= -200:
                    _c40 = study_out.get("mc4ovr_fav_band") or {}
                    fires.append(((_c40.get("roi_pct") or 0), "mc4ovr_fav_band", _favb0))
        if not fires:
            continue
        fires.sort(reverse=True)
        sp = fires[0][2]
        kept = [f for f in fires if f[2] == sp]
        won1b = bool(rr["p1_won"])
        pnl25 = (25 * ((d1b if sp else d2b) - 1)) if (sp == won1b) else -25
        # women's Best pick on a +100..+250 dog -> price_dog_w (user 2026-10-08)
        if genb == "w" and sp == dgb:
            _opw = float(rr["p1_odds"] if sp else rr["p2_odds"])
            if 100 <= _opw <= 250:
                _pdw.append(pnl25)
        # 🤝 OVERLAP: does the ⭐ Picks sheet land on the SAME side? (c50+c75 agree,
        # non-recon, and that side's c50 prob is OVER the market's implied)
        _rc = bool(rr.get("mc_c_recon")) if pd.notna(rr.get("mc_c_recon")) else False
        _c50v, _c75v = rr.get("mc_c_p1"), rr.get("mc_c75_p1")
        if not _rc and pd.notna(_c50v) and pd.notna(_c75v):
            _s50 = float(_c50v) >= 0.5
            if _s50 == (float(_c75v) >= 0.5):
                _cps = float(_c50v) if _s50 else 1 - float(_c50v)
                _mps = mkb if _s50 else 1 - mkb
                if _cps > _mps and _s50 == sp:
                    if sp != dgb:
                        _ovf[genb].append(pnl25)
                    else:
                        # DOG half gated to +100..+250 (2026-10-08, user "I only want the
                        # +100 to +250 ones"): the overlap-dog edge lives in that band;
                        # longer dogs (e.g. +614) are excluded from the lane AND the badge.
                        _op9 = float(rr["p1_odds"] if sp else rr["p2_odds"])
                        if 100 <= _op9 <= 250:
                            _ovd[genb].append(pnl25)
        # 🔵★2+ blue 2-stack: men dog +100..+250 with 2+ distinct families (unchanged)
        if genb != "m":
            continue
        if len({_FAM2.get(f[1], f[1]) for f in kept}) < 2:
            continue                       # need 2+ DISTINCT families
        if sp != dgb:
            continue                       # the pick must be the market DOG
        op = float(rr["p1_odds"] if sp else rr["p2_odds"])
        if not (100 <= op <= 250):
            continue                       # blue band only
        _b2.append(pnl25)
    study_out["blue2stack"] = {**agg(_b2), "m": agg(_b2), "w": agg([])}
    study_out["ovl_fav"] = {**agg(_ovf["m"] + _ovf["w"]), "m": agg(_ovf["m"]), "w": agg(_ovf["w"])}
    study_out["ovl_dog"] = {**agg(_ovd["m"] + _ovd["w"]), "m": agg(_ovd["m"]), "w": agg(_ovd["w"])}
    study_out["price_dog_w"] = {**agg(_pdw), "m": agg([]), "w": agg(_pdw)}

    def _mw(g):
        return {"m": agg(g["m"]), "w": agg(g["w"])}
    _picks = _lane_picks()      # populates _sideagg -- must run before _sc merges below

    def _sc(key):
        b = _sideagg.get(key) or {}
        return {"dog": agg(b.get("d") or []), "fav": agg(b.get("f") or []),
                "m_dog": agg(b.get("md") or []), "m_fav": agg(b.get("mf") or []),
                "w_dog": agg(b.get("wd") or []), "w_fav": agg(b.get("wf") or [])}
    return {"registered": "2026-09-28", "stake_usd": 25,
            "picks": _picks,
            "lanes": {k: {**agg(v), **_mw(lanes_g[k]), **_sc(k)} for k, v in lanes.items()},
            "study": study_out,
            "cma_all": {**agg(cma_all), "pending": int(cma_all_pending), **_mw(cma_all_g), **_sc("cma_all")},
            "agree_dog": {**agg(agdog), "pending": int(agdog_pending), **_mw(agdog_g), **_sc("agree_dog")},
            "cma_edge": {**agg(cma_edge), "pending": int(cma_edge_pending),
                         **{k: agg(cme_g[k]) for k in _gs_keys}},
            "c_edge": {**agg(ce), "pending": int(ce_pending),
                       **{k: agg(ce_g[k]) for k in _gs_keys}},
            "c_all": {**agg(call), "pending": int(call_pending), **_mw(call_g), **_sc("c_all")},
            "c_alone": {**agg(c_alone), "pending": int(c_alone_pending), **_mw(c_alone_g), **_sc("c_alone")},
            "c_with": {**agg(c_with), "pending": int(c_with_pending), **_mw(c_with_g), **_sc("c_with")},
            "pending": int(pending)}


def get_tennis_track_record() -> dict:
    """Forward record of the frozen tennis log: model accuracy vs the market's own favorite
    on the same matches, plus flat-1u ROI at the logged odds for (a) every model pick and
    (b) only the matches where model and market disagree -- the only bets that could ever
    carry an edge. Empty until matches settle; grows one slate at a time."""
    log = _read_log()
    settled_all = log[(log["settled"] == True) & log["p1_won"].notna()]  # noqa: E712 -- tracker rows may lack a model prob
    settled = settled_all[settled_all["p1_win_prob"].notna()]
    out = {"total_logged": int(len(log)), "settled": int(len(settled)), "since": str(log["date"].min()) if len(log) else None}
    if settled_all.empty:
        return out
    rows = []
    for _, r in settled.iterrows():
        d1, d2 = _decimal(r["p1_odds"]), _decimal(r["p2_odds"])
        if d1 is None or d2 is None:
            continue
        i1, i2 = 1 / d1, 1 / d2
        mkt_p1 = i1 / (i1 + i2)
        model_p1_pick = r["p1_win_prob"] >= 0.5
        mkt_p1_pick = mkt_p1 >= 0.5
        won = bool(r["p1_won"])
        model_right = (model_p1_pick == won)
        dec_pick = d1 if model_p1_pick else d2
        rows.append({"model_right": model_right, "mkt_right": (mkt_p1_pick == won),
                     "disagree": model_p1_pick != mkt_p1_pick,
                     "flat": (dec_pick - 1.0) if model_right else -1.0})
    d = pd.DataFrame(rows)
    if not d.empty:
        out.update({
        "n": int(len(d)),
        "model_accuracy": round(float(d["model_right"].mean()), 4),
        "market_accuracy": round(float(d["mkt_right"].mean()), 4),
        "flat_roi_pct": round(100 * float(d["flat"].mean()), 2),
        "n_disagree": int(d["disagree"].sum()),
        "disagree_model_accuracy": round(float(d[d["disagree"]]["model_right"].mean()), 4) if d["disagree"].any() else None,
        "disagree_flat_roi_pct": round(100 * float(d[d["disagree"]]["flat"].mean()), 2) if d["disagree"].any() else None,
        })
    # SR-DOG pre-registered tracker (registered 2026-09-26, checkpoint 50 settled): the one rule
    # that survived the flat-ROI battery on the TennisRatio core in BOTH seasons -- the UNDERDOG
    # (>=2.00 dec) whose last-10-on-surface serve+return composite beats the favorite's.
    # Backtest 2025 +21.2% (90) / 2026 +1.2% (89); sole survivor of 24 slices, haircut applies.
    if "sr_dog" in settled_all.columns:
        srows = []
        for _, r in settled_all[settled_all["sr_dog"].isin(["p1", "p2"])].iterrows():
            dec = _decimal(r["p1_odds"] if r["sr_dog"] == "p1" else r["p2_odds"])
            if dec is None:
                continue
            won = bool(r["p1_won"]) == (r["sr_dog"] == "p1")
            srows.append((dec - 1.0) if won else -1.0)
        n = len(srows)
        out["sr_dog"] = {
            "n": n,
            "flat_roi_pct": round(100 * sum(srows) / n, 2) if n else None,
            "hit_pct": round(100 * sum(1 for x in srows if x > 0) / n, 1) if n else None,
            "registered": "2026-09-26", "checkpoint": 50,
            # Frozen-ledger record BEFORE registration (scored 2026-09-26 over the ledger's
            # settled matches since 9/6 at their frozen first-serve odds, sr10 as-of each date;
            # 7 qualifiers only -- the pool was 156 players until the 9/26 expansion). A frozen
            # snapshot by definition, same as the MLB trackers' at_registration blocks.
            "at_registration": {"n": 7, "flat_roi_pct": 54.9, "hit_pct": 42.9,
                                "units": 3.8, "through": "2026-09-26"},
        }
    # SOS tracker (registered 2026-09-26): stats-not-worse + clearly tougher schedule ->
    # WIN-RATE tracker (they win 63-65% in backtest but the market prices it: ROI negative).
    if "sos" in settled_all.columns:
        wrows = []
        for _, r in settled_all[settled_all["sos"].isin(["p1", "p2"])].iterrows():
            dec = _decimal(r["p1_odds"] if r["sos"] == "p1" else r["p2_odds"])
            if dec is None:
                continue
            won = bool(r["p1_won"]) == (r["sos"] == "p1")
            wrows.append((1 if won else 0, (dec - 1.0) if won else -1.0))
        n = len(wrows)
        out["sos"] = {
            "n": n,
            "win_pct": round(100 * sum(w for w, _ in wrows) / n, 1) if n else None,
            "flat_roi_pct": round(100 * sum(p for _, p in wrows) / n, 2) if n else None,
            "registered": "2026-09-26",
            "at_registration": {"n": 7, "win_pct": 57.1, "flat_roi_pct": -17.6, "through": "2026-09-26"},
        }
    return out


def _best_tab_side(r, study, d1, d2, mk1):
    """The 🏆 Best tab's pick for a FROZEN log row, or None — the server-side mirror of
    BestPanel (2026-10-08, user "a separate tab that tracks daily profit taking every bet
    on the best tab and on the prices tab"). Side-aware gates on the CURRENT lane records
    (the tab's own gate moves daily — past days are a faithful reconstruction, not a
    freeze; noted in the tab header). Returns (side_p1bool, all10_bool) or (None, False).
    KEEP IN LOCKSTEP with TennisSection BEST_SIGNALS/BestPanel + the ovl post-pass."""
    def b(col):
        v = r.get(col)
        return None if (v is None or pd.isna(v)) else (float(v) >= 0.5)
    c1, g1 = b("model_c_p1"), b("model_cma_p1")
    if c1 is None or g1 is None:
        return None, False
    dog1 = mk1 < 0.5
    aP, bP, dP = b("model_a_p1"), b("model_b_p1"), b("model_d_p1")
    dmaP, mcdS = b("model_dma_p1"), b("mc_p1")
    mcS, c75, cuS = b("mc_c_p1"), b("mc_c75_p1"), b("mc_cutr_p1")
    cma = float(r["model_cma_p1"])
    mdog = mk1 if dog1 else 1 - mk1
    gdog = cma if dog1 else 1 - cma
    hate = (mdog - gdog) >= 0.02
    star = (c1 == g1 == dog1)
    passfav = (aP is not None and bP is not None and aP != c1 and bP != c1
               and g1 == c1 and c1 != dog1)
    dmaE = False
    if dmaP is not None:
        dv = float(r["model_dma_p1"])
        dmaE = ((dv if dmaP else 1 - dv) - (mk1 if dmaP else 1 - mk1)) >= 0.02
    gen = "w" if str(r.get("league", "")).lower() in ("wta", "itf_women") else "m"
    a10l = [aP, bP, c1, g1, dP, dmaP, mcdS, mcS, c75, cuS]
    all10 = all(x is not None for x in a10l) and len(set(a10l)) == 1

    def gate(key, isdog):
        c9 = (study.get(key) or {}).get(gen + ("_dog" if isdog else "_fav")) or {}
        n = c9.get("n") or 0
        if n < 12 or c9.get("roi_pct") is None:
            return None
        hit = 100.0 * c9["wins"] / n
        roi = c9["roi_pct"]
        return roi if ((hit >= 65 and roi >= 4) or roi >= 15) else None
    fires = []

    def F(k, s):
        if s is None:
            return
        roi = gate(k, s == dog1)
        if roi is not None:
            fires.append((roi, k, s))
    if c75 is not None and c75 == dog1:
        F("mc_c75_dog", c75)
    if mcdS is not None and not star and not hate and not passfav and mcdS == g1:
        F("mc_green", g1)
    if mcS is not None and c75 is not None and mcS == c75:
        F("mcc_c75_agree", c75)
    # ⚄⚄ all-4 MCs on a banded dog (2026-10-08, promoted per user)
    _mc4band9 = False
    if None not in (mcdS, mcS, c75, cuS) and mcdS == mcS == c75 == cuS and mcS == dog1:
        _od4 = r.get("p1_odds") if mcS else r.get("p2_odds")
        if pd.notna(_od4) and 100 <= float(_od4) <= 250:
            _mc4band9 = True
            F("mc4_dog_band", mcS)
            # ⚔→🐕 FIGHT-FLIP (2026-10-08, user): gray fav overpowered by unanimous
            # sims on a banded dog -> explicit DOG push (no n-floor; user mark).
            if c1 != g1 and g1 != dog1:
                _cf9 = study.get("fight_mc4_dog") or {}
                fires.append(((_cf9.get("roi_pct") or 48.0), "fight_mc4_dog", mcS))
    if dmaE:
        F("dma_edge2", dmaP)
    if all10:
        F("all10_agree", a10l[0])
    if None not in (aP, bP, dP, mcS) and aP == bP == c1 == dP and mcS == c1:
        F("mc_4of4", c1)
    # FIGHT gray-side is SUPPRESSED when its favorite is overpowered by all-4 sims on
    # the banded dog (2026-10-08, user: the dog is the bet there, not gray's fav).
    if c1 != g1 and not (_mc4band9 and g1 != dog1):
        F("cvg_gray", g1)
    if (mdog - gdog) >= 0.05:
        F("goldfav_d5", not dog1)
    if hate:
        F("grayhate_fav", not dog1)
    if None not in (aP, bP) and aP != bP and bP == c1:
        if bP != dog1:
            F("fade_a_fav", bP)
        F("fade_a", bP)
    if None not in (aP, bP) and aP != c1 and bP != c1 and g1 == c1:
        F("c_alone_gray", c1)
    if star:
        F("gold_names", c1)
    elif hate:
        F("gold_names", not dog1)
    if gen == "m":
        favs = not dog1
        favod = r.get("p1_odds") if favs else r.get("p2_odds")
        favod = float(favod) if pd.notna(favod) else None
        for key, cond in (
                ("all10_price_m", all10 and a10l[0] == favs
                 and favod is not None and -300 <= favod <= -140),
                ("cr5_coll_leanfav", hate and None not in (aP, bP, dP)
                 and aP == favs and bP == favs and c1 == favs and g1 == favs
                 and dP == favs and 0.65 <= max(mk1, 1 - mk1) <= 0.85)):
            c9 = (study.get(key) or {}).get("m") or {}
            if cond and (c9.get("n") or 0) >= 12 and (c9.get("roi_pct") or 0) > 0:
                fires.append((c9["roi_pct"], key, favs))
    # ⚄ 4-MC OVER-MARKET FAV, -200..-300 (2026-10-08, user promotion at n=6): every
    # sim prices the favorite above the market AND the price sits in the one pocket
    # that paid. Explicit mark (no n-floor, ⚠ in the UI until the lane matures).
    _v49 = [r.get("mc_p1"), r.get("mc_c_p1"), r.get("mc_c75_p1"), r.get("mc_cutr_p1")]
    if all(pd.notna(v) for v in _v49):
        _favb9 = not dog1
        _mkf9 = max(mk1, 1 - mk1)
        if all((float(v) if _favb9 else 1 - float(v)) > _mkf9 for v in _v49):
            _odf9 = r.get("p1_odds") if _favb9 else r.get("p2_odds")
            if pd.notna(_odf9) and -300 <= float(_odf9) <= -200:
                _c49 = study.get("mc4ovr_fav_band") or {}
                fires.append(((_c49.get("roi_pct") or 0), "mc4ovr_fav_band", _favb9))
    if not fires:
        return None, all10
    fires.sort(reverse=True)
    sp = fires[0][2]
    od = float(r["p1_odds"] if sp else r["p2_odds"])
    if sp == dog1 and od > 250:
        return None, all10      # long-dog gate (2026-10-08): >+250 dogs never make the tab
    return sp, all10


def get_tab_profit(limit_dates: int = 21) -> dict:
    """📊 Tab P/L (2026-10-08, user ask): flat 1u on EVERY 🏆 Best-tab pick vs EVERY 💰
    Prices-tab pick (the sweet-priced subset), per day from the frozen ledger, so the two
    tabs' daily profit can be compared head-to-head. Prices ⊆ Best by construction.
    Sweet windows mirror the frontend: men +100..+250 / −600..−300 / ALL-10 −300..−140;
    women +100..+250 (dog band only)."""
    study = (get_ab25_record() or {}).get("study") or {}
    log = _read_log()
    log = log[(log["settled"] == True) & log["p1_won"].notna()  # noqa: E712
              & log["p1_odds"].notna() & log["p2_odds"].notna()]
    days = {}
    for _, r in log.iterrows():
        d1, d2 = _decimal(r["p1_odds"]), _decimal(r["p2_odds"])
        if not d1 or not d2 or d1 <= 1.005 or d2 <= 1.005:
            continue
        mk1 = (1 / d1) / ((1 / d1) + (1 / d2))
        sp, all10 = _best_tab_side(r, study, d1, d2, mk1)
        if sp is None:
            continue
        od = float(r["p1_odds"] if sp else r["p2_odds"])
        won = bool(r["p1_won"]) == sp
        pnl = ((d1 if sp else d2) - 1.0) if won else -1.0
        gen = "w" if str(r.get("league", "")).lower() in ("wta", "itf_women") else "m"
        if gen == "w":
            sweet = 100 <= od <= 250
        else:
            sweet = (100 <= od <= 250) or (-600 <= od <= -300) \
                or (all10 and -300 <= od <= -140)
        day = days.setdefault(str(r.get("date")), {
            "best": {"n": 0, "w": 0, "pnl": 0.0},
            "prices": {"n": 0, "w": 0, "pnl": 0.0}})
        day["best"]["n"] += 1
        day["best"]["w"] += int(won)
        day["best"]["pnl"] += pnl
        if sweet:
            day["prices"]["n"] += 1
            day["prices"]["w"] += int(won)
            day["prices"]["pnl"] += pnl
    out_days = []
    for dt in sorted(days, reverse=True)[:limit_dates]:
        d = days[dt]
        for k in ("best", "prices"):
            d[k]["pnl"] = round(d[k]["pnl"], 2)
            n = d[k]["n"]
            d[k]["roi_pct"] = round(100 * d[k]["pnl"] / n, 1) if n else None
        out_days.append({"date": dt, **d})
    tot = {k: {"n": sum(x[k]["n"] for x in out_days),
               "w": sum(x[k]["w"] for x in out_days),
               "pnl": round(sum(x[k]["pnl"] for x in out_days), 2)} for k in ("best", "prices")}
    for k in ("best", "prices"):
        n = tot[k]["n"]
        tot[k]["roi_pct"] = round(100 * tot[k]["pnl"] / n, 1) if n else None
    tot["best_days_won"] = sum(1 for x in out_days if x["best"]["pnl"] > x["prices"]["pnl"])
    tot["prices_days_won"] = sum(1 for x in out_days if x["prices"]["pnl"] > x["best"]["pnl"])
    return {"days": out_days, "totals": tot}
