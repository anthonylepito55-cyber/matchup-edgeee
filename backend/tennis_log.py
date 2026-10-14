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

import numpy as np
import pandas as pd
import requests

from tennis_data import OPTICODDS_API_KEY, OPTICODDS_BASE_URL, TENNIS_LEAGUES, CACHE_DIR

LOG_PATH = os.path.join(CACHE_DIR, "tennis_prediction_log.parquet")

COLUMNS = ["date", "fixture_id", "league", "tournament", "round", "player_1", "player_2",
           "start_time_utc", "surface", "best_of_5", "p1_win_prob", "p1_odds", "p2_odds",
           "bookmaker", "logged_at", "settled", "p1_won", "sr_dog", "sos",
           "model_a_p1", "model_b_p1", "model_c_p1", "model_cma_p1",
           "model_ama_p1", "model_bma_p1", "model_d_p1", "model_dma_p1", "mc_p1", "mc_c_p1",
           "mc_c75_p1", "mc_cutr_p1", "mc_c_recon", "model_x_p1", "model_x_recon", "model_x_v",
           "model_cnohb_p1", "model_capi_p1",
           # MODEL G (2026-10-12, user ask): the nine 52w stats, opponent-rank-adjusted and
           # sample-size-shrunk. Logged to earn a forward record -- WATCH ONLY. No lane in the
           # bet() loop reads it and no mark depends on it, because its backtest has no
           # positive gender x side cell anywhere (-11% dogs, -6% favs over 53k bets).
           # model_g_recon=True marks a walk-forward BACKFILL onto a game that predates the
           # model (trained only on earlier years, result never read) -- dimmed ~ in the
           # history and EXCLUDED from the g_* forward lanes, the model_x_recon pattern.
           "model_g_p1", "model_gma_p1", "model_g_recon",
           # MODEL G2 (2026-10-12): G + the last-10-on-court block, walkovers excluded.
           "model_g2_p1", "model_g2ma_p1", "model_g2_recon",
           "model_p_dog", "model_p_prob", "model_p_ev", "model_p_fev", "ac_v",
           "open_p1_odds", "open_p2_odds", "open_at", "c_rp_diff_p1", "c_sp_diff_p1", "surface_bad", "inplay_suspect", "resolve_bad", "ue_set5_diff_p1", "score",
           "h2h_n", "h2h_p1w", "h2h_p2w", "h2h_sn", "h2h_sp1w",
           # PURE-RESULTS FORM overlay (2026-10-06): p1 form minus p2 form, quality- +
           # competitiveness-adjusted last-10-on-surface, NO serve stats. Frozen at first
           # serve; feeds the contrarian pf_c75_* lanes. See tennis_pure_form.py.
           "pf_edge_p1",
           # REAL UTR (2026-10-07): utr_edge_p1 = p1 singlesUtr - p2 singlesUtr (UTR's own
           # public API, current ratings only -> FORWARD tracker, never retro-tested);
           # utr_mom_p1 = (p1 3mo-vs-level) - (p2 3mo-vs-level) = who's running hotter
           # than their established rating. See utr_data.py.
           "utr_edge_p1", "utr_mom_p1",
           # MC v2 head (2026-10-08): frozen blend prob; display/watch-lane only.
           # mc2_recon=True marks a walk-forward BACKFILL (pre-match ratings only, result
           # never used) -- display-only, excluded from the mc2_* forward lanes.
           "mc2_p1", "mc2_recon",
           # MC v3 head (2026-10-13): MC2 + per-surface serve/return (shrunk toward career),
           # best-of-five modelled, day tilt in the pick. Own column so MC2's record stays
           # its own. WATCH ONLY on arrival -- no mark and no lane reads it yet.
           "mc3_p1", "mc3_recon",
           # MC v5 head (2026-10-13): MC3 + surface last-5 (recency weighted) + clutch.
           # WATCH ONLY on arrival. Every added term measured neutral-to-worse than MC3 on
           # 120,877 rows; shipped on the user's explicit call with the weights set where
           # that cost is zero.
           "mc5_p1", "mc5_recon",
           # MC2 input quality, frozen at log time (2026-10-13). mc2_svp_min = the thinner
           # side's 52w service-point count on this surface; mc2_stretch_d = how far back
           # the L10 window reached. NULL on every row logged before this shipped, and a
           # null is treated as "unknown", never as "bad" -- so the gate only ever applies
           # to rows that actually carry the measurement.
           "mc2_svp_min", "mc2_stretch_d",
           # FAV-VALUE fatigue freeze (2026-10-08): each side's settled matches + sets
           # played in the prior 7 days, counted from THIS log's own settled rows at log
           # time (the archive lags ~10d; our log is live). Lower-bound counts (we only
           # see games we track) — the lane fires less, never falsely. Drives fav_value.
           "p1_m7", "p1_sets7", "p2_m7", "p2_sets7",
           # POST-MATCH STATS (2026-10-10, user "How do we start logging unforced errors a
           # game"). Filled after the fact by tennis_postmatch.backfill, retried nightly
           # because both sources arrive days later. ue_*/win_* are REAL charted unforced
           # errors + winners from the Match Charting Project (small reach, ~2% of our games
           # and always will be -- charting is volunteer work). df_*/sgames_*/aces_* come from
           # the TennisRatio archive and reach ~100% of matches including ITF, about 10 days
           # late; a double fault is the one unforced error recorded for every match played.
           "ue_p1", "ue_p2", "ue_fh_p1", "ue_fh_p2", "win_p1", "win_p2", "ue_sets",
           "df_p1", "df_p2", "sgames_p1", "sgames_p2", "aces_p1", "aces_p2", "pm_src"]


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
    # 7-DAY LOAD MAP (fav_value lane, 2026-10-08): from our own settled rows. The
    # measured market bias: heavy-load favorites outrun their implied (fatigue
    # over-feared) — archive: all favs −5.2% vs heavy-load favs −0.9%.
    load7 = {}
    try:
        _lg = _read_log()
        if len(_lg):
            _lg = _lg[_lg["p1_won"].notna()]
            _cut = (pd.Timestamp(date) - pd.Timedelta(days=7)).strftime("%Y-%m-%d")
            _lg = _lg[(_lg["date"].astype(str).str[:10] >= _cut)
                      & (_lg["date"].astype(str).str[:10] < str(date)[:10])]
            for _r in _lg.itertuples():
                _sc = str(getattr(_r, "score", "") or "")
                _ns = sum(1 for t in _sc.replace(",", " ").split() if "-" in t)
                if _ns < 2:
                    _ns = 2
                for _nm in (_r.player_1, _r.player_2):
                    _e = load7.setdefault(str(_nm), [0, 0])
                    _e[0] += 1
                    _e[1] += _ns
    except Exception:  # noqa: BLE001
        load7 = {}
    for m in matches:
        pred = m.get("prediction") or {}
        odds = m.get("live_odds") or {}
        ma = m.get("model_a") or {}
        mb = m.get("model_b") or {}
        mc = m.get("model_c") or {}
        md = m.get("model_d") or {}
        mg = m.get("model_g") or {}
        mg2 = m.get("model_g2") or {}
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
            # FROZEN SEASONAL HOLD/BREAK (2026-10-11, user "Mark the band + favorite and band
            # + dog positive roi ones"): each player's 52-week-on-this-surface service-games-won
            # and return-games-won, frozen at first serve so the two s52 lanes below score the
            # same numbers the card showed. Computed from the live context (the board already
            # has it); as-of correctness for OLD rows comes from _backfill_s52.py, which uses
            # context_asof.
            **_s52_pair(m.get("player_1"), m.get("player_2"), m.get("surface")),
            "model_a_p1": ma.get("p1_prob"), "model_b_p1": mb.get("p1_prob"),
            "model_c_p1": mc.get("p1_prob"),
            "model_cma_p1": mc.get("market_aware_p1"),
            "model_ama_p1": ma.get("market_aware_p1"), "model_bma_p1": mb.get("market_aware_p1"),
            "model_d_p1": md.get("p1_prob"), "model_dma_p1": md.get("market_aware_p1"),
            "model_g_p1": mg.get("p1_prob"), "model_gma_p1": mg.get("market_aware_p1"),
            "model_g_recon": False,
            "model_g2_p1": mg2.get("p1_prob"), "model_g2ma_p1": mg2.get("market_aware_p1"),
            "model_g2_recon": False,
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
            # which Model X made this pick: 2 = market-free X (2026-10-09+). Old rows = None.
            "model_x_v": (2 if mx.get("p1_prob") is not None else None),
            # MODEL P (2026-10-09): dog side (1/2), P's dog win prob, EV at the logged price.
            "model_p_dog": (m.get("model_p") or {}).get("dog"),
            "model_p_prob": (m.get("model_p") or {}).get("p_dog"),
            "model_p_ev": (m.get("model_p") or {}).get("ev"),
            "model_p_fev": (m.get("model_p") or {}).get("fav_ev"),
            # tracked C variants (2026-10-10), frozen like every other model output
            "model_cnohb_p1": (m.get("model_c") or {}).get("p1_prob_nohb"),
            "model_capi_p1": (m.get("model_c") or {}).get("p1_prob_api"),
            # RETURNER DOG input (2026-10-09): p1 minus p2 return-PRESSURE points won %
            # (52w, surface), from live Model C.
            "c_rp_diff_p1": ((mc.get("pf") or {}).get("d_c_rp")),
            "c_sp_diff_p1": ((mc.get("pf") or {}).get("d_c_sp")),
            # LOW-ERROR DOG input (2026-10-09): p1 minus p2 unforced errors per set, last 5
            # charted matches (Tennis Abstract MCP). None unless both players are charted.
            "ue_set5_diff_p1": (lambda u: (u["p1"]["ue_set_5"] - u["p2"]["ue_set_5"])
                                if (u and u.get("p1") and u.get("p2") and u["p1"].get("ue_set_5") is not None
                                    and u["p2"].get("ue_set_5") is not None) else None)(m.get("ue")),
            # A/C version: 2 = rank-sign fix applied (2026-10-09). None = logged on the
            # reversed-rank A/C. Lets every A/C-based lane split before/after the fix.
            "ac_v": 2,
            "model_x_recon": False,
            # PURE-RESULTS FORM edge (2026-10-06): p1 minus p2 quality-adjusted L10-on-
            # surface form. Frozen like the models; drives the contrarian pf_c75_* lanes.
            "pf_edge_p1": (m.get("pure_form") or {}).get("edge"),
            # REAL UTR (2026-10-07): frozen at log time, forward lanes only (utr_data.py).
            "utr_edge_p1": (m.get("utr") or {}).get("edge"),
            "utr_mom_p1": (m.get("utr") or {}).get("mom"),
            "mc2_p1": (m.get("mc2") or {}).get("p1_prob"),
            "mc2_recon": False,
            "mc3_p1": (m.get("mc3") or {}).get("p1_prob"),
            "mc3_recon": False,
            "mc5_p1": (m.get("mc5") or {}).get("p1_prob"),
            "mc5_recon": False,
            "mc2_svp_min": (m.get("mc2") or {}).get("svp_min"),
            "mc2_stretch_d": (m.get("mc2") or {}).get("stretch_d"),
            "p1_m7": load7.get(str(m.get("player_1")), [0, 0])[0],
            "p1_sets7": load7.get(str(m.get("player_1")), [0, 0])[1],
            "p2_m7": load7.get(str(m.get("player_2")), [0, 0])[0],
            "p2_sets7": load7.get(str(m.get("player_2")), [0, 0])[1],
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
    # OPENING LINE (2026-10-09, user "follow market line movements"): the first prices we
    # ever logged for a fixture are kept as open_p1_odds/open_p2_odds (+ open_at) and never
    # overwritten; p1_odds/p2_odds keep updating until first serve, so close - open = the
    # line move every card and lane can read.
    new["open_p1_odds"], new["open_p2_odds"], new["open_at"] = new["p1_odds"], new["p2_odds"], now
    if not log.empty and "open_p1_odds" in log.columns:
        _o = log[log["open_p1_odds"].notna()].drop_duplicates("fixture_id", keep="last").set_index("fixture_id")
        _m = new["fixture_id"].isin(_o.index)
        if _m.any():
            _ix = new.loc[_m, "fixture_id"]
            new.loc[_m, "open_p1_odds"] = _ix.map(_o["open_p1_odds"]).values
            new.loc[_m, "open_p2_odds"] = _ix.map(_o["open_p2_odds"]).values
            new.loc[_m, "open_at"] = _ix.map(_o["open_at"]).values
    # IN-PLAY CAPTURE GUARD (2026-10-11, user: "itf lines are moving mid game i mean odds").
    #
    # The status guard above refuses any fixture the feed calls non-"unplayed", but it trusts
    # the feed's clock -- and on ITF the clock is wrong often enough to matter: courts run
    # early, qualifying slates carry nominal start times, so a match can be underway while the
    # slate still says unplayed. The audit found it: ITF's 99th-percentile move from its own
    # opening price is 33pp against 7-10pp for tour and challenger, including
    # -102 -> -1223 (+42pp) and +105 -> -290 (+26pp). A pre-match line does not travel 42
    # points; that is a price taken after someone won a set.
    #
    # A time-based rule cannot catch it, because the scheduled time itself is what is wrong. So
    # the test is the MOVE: a frozen price more than DRIFT_MAX_PP from its own opener is treated
    # as in-play contamination. Row is KEPT and flagged (same treatment as surface_bad) rather
    # than dropped, so it stays visible and auditable.
    #
    # Only works where an opener exists (255 of 1546 rows today), so this is a partial guard --
    # it catches the extreme cases, not every one.
    DRIFT_MAX_PP = 20.0
    try:
        def _ip(a):
            a = pd.to_numeric(a, errors="coerce")
            return np.where(a > 0, 100.0 / (a + 100.0), -a / (-a + 100.0))
        _hasopen = new["open_p1_odds"].notna() & new["p1_odds"].notna()
        if _hasopen.any():
            _d = 100.0 * (_ip(new.loc[_hasopen, "p1_odds"])
                          - _ip(new.loc[_hasopen, "open_p1_odds"]))
            new["inplay_suspect"] = False
            new.loc[_hasopen, "inplay_suspect"] = np.abs(_d) > DRIFT_MAX_PP
        else:
            new["inplay_suspect"] = False
    except Exception as _e:
        print(f"[tennis log] in-play guard skipped: {_e}")
        new["inplay_suspect"] = False
    if log.empty:
        _write_log(new)
        return
    frozen_ids = set(log[(log["settled"] == True) | log["start_time_utc"].apply(_started)]["fixture_id"])  # noqa: E712
    new = new[~new["fixture_id"].isin(frozen_ids)]
    if new.empty:
        return
    keep = log[~log["fixture_id"].isin(set(new["fixture_id"]))]
    # CROSS-FEED DEDUPE (2026-10-08): the OpticOdds board and the Polymarket feed give the
    # SAME match different fixture ids (e.g. "2026100811" vs "pm_1146640"), and the upsert
    # above only matches on fixture_id -- so 67 matches were logged twice and every lane
    # record double-counted them (68 extra settled rows, 6.7% of the settled log). Rule:
    # OpticOdds is primary. A pm_ row is dropped if an OpticOdds row for the same player
    # pair exists within +/-3 days; an arriving OpticOdds row evicts its pm_ twin.
    keep, new = _drop_cross_feed_twins(keep, new)
    if new.empty and len(keep) == len(log):
        return
    _write_log(pd.concat([keep, new], ignore_index=True))


def _pair_key(a, b):
    import unicodedata

    # word order + hyphens ignored (2026-10-09): feeds disagree on name order, e.g. OpticOdds
    # "Tian Jialin" vs Polymarket "Jialin Tian" -- the order-sensitive key let that twin in
    # and double-counted it in every lane.
    def n(x):
        x = unicodedata.normalize("NFKD", str(x or ""))
        x = "".join(c for c in x if not unicodedata.combining(c)).lower().replace("-", " ")
        return " ".join(sorted(x.split()))
    return tuple(sorted((n(a), n(b))))


def _loose_name_keys(x):
    """Candidate "surname|initial" keys for one name, as a set.

    Which token is the surname cannot be guessed reliably across feeds, so nothing is guessed.
    Every token of 5+ characters is offered as a candidate surname, paired with the first
    letter of EVERY other token. Two names are the same person when their candidate sets
    intersect, which requires them to agree on BOTH a long token and an initial.

    The two constraints are what keep it safe, and each was put there by a failing case:

      * pairing with every other initial, not just one, because which token is "the first
        name" is not stable when the feeds disagree about how many tokens there are --
        "Facundo Diaz Acosta" vs "Facundo Acosta" has to survive a dropped middle name.
      * the 5-character floor on the candidate surname, because without it a shared GIVEN
        name becomes a key and "Juan Martin Del Potro" collides with "Juan Monaco" on
        "juan|m".

    Worked through: "Alexander Zverev" gives {zverev|a, alexander|z} and "Mischa Zverev" gives
    {zverev|m, mischa|z} -- no overlap, so two Zverevs facing the same opponent are NOT merged.
    "Abdullah Shelbayh" and "Abedallah Shelbayh" both give shelbayh|a and so are. Reordered
    names still work: "Tian Jialin" and "Jialin Tian" both give jialin|t.
    """
    import unicodedata

    x = unicodedata.normalize("NFKD", str(x or ""))
    x = "".join(c for c in x if not unicodedata.combining(c)).lower().replace("-", " ")
    parts = [t for t in x.split() if t]
    if not parts:
        return set()
    if len(parts) == 1:
        return {"%s|" % parts[0]}
    out = set()
    for a9, t in enumerate(parts):
        if len(t) < 5:
            continue
        for b9, o in enumerate(parts):
            if a9 != b9 and o:
                out.add("%s|%s" % (t, o[:1]))
    # a name with no token of 5+ characters still needs one key, or it can never match itself
    return out or {"%s|%s" % (max(parts, key=len), min(parts, key=len)[:1])}


def _pair_keys_loose(a, b):
    """All order-insensitive candidate pair keys for a fixture. A twin is declared when any
    one key is shared, which requires BOTH players to agree on a candidate -- the reason a
    false positive would need two simultaneous surname+initial collisions in one match."""
    ka, kb = _loose_name_keys(a), _loose_name_keys(b)
    return {tuple(sorted((x, y))) for x in ka for y in kb}


def _drop_cross_feed_twins(keep, new, window_days=3):
    """OpticOdds-vs-Polymarket twin removal (see the note in log_predictions)."""
    if keep.empty and new.empty:
        return keep, new
    both = pd.concat([keep.assign(_src="keep"), new.assign(_src="new")], ignore_index=True)
    both["_pm"] = both["fixture_id"].astype(str).str.startswith("pm_")
    both["_pair"] = [_pair_key(a, b) for a, b in zip(both["player_1"], both["player_2"])]
    both["_pairl"] = [_pair_keys_loose(a, b)
                      for a, b in zip(both["player_1"], both["player_2"])]
    both["_d"] = pd.to_datetime(both["date"].astype(str).str[:10], errors="coerce")
    oo = both[~both["_pm"]]
    drop = set()
    if not oo.empty:
        oo_days, oo_days_l = {}, {}
        for pr, prl, dd in zip(oo["_pair"], oo["_pairl"], oo["_d"]):
            oo_days.setdefault(pr, []).append(dd)
            for k9 in prl:                      # a row is indexed under every candidate
                oo_days_l.setdefault(k9, []).append(dd)
        _n_loose = 0
        for i, r in both[both["_pm"]].iterrows():
            if pd.isna(r["_d"]):
                continue
            def _near(days):
                return bool(days) and any(
                    pd.notna(x) and abs((x - r["_d"]).days) <= window_days for x in days)
            if _near(oo_days.get(r["_pair"])):
                drop.add(i)
            elif any(_near(oo_days_l.get(k9)) for k9 in r["_pairl"]):
                # the strict key missed it and surname+initial caught it: a spelling variant
                drop.add(i)
                _n_loose += 1
        if _n_loose:
            print(f"[tennis log] {_n_loose} twin(s) matched only on surname+initial "
                  f"(feed name-spelling variant)")
    if not drop:
        return keep, new
    both = both.drop(index=list(drop))
    both = both.drop(columns=[c for c in ("_pairl",) if c in both.columns])
    cols = [c for c in keep.columns]
    k2 = both[both["_src"] == "keep"][cols].reset_index(drop=True)
    n2 = both[both["_src"] == "new"][[c for c in new.columns]].reset_index(drop=True)
    print(f"[tennis log] cross-feed dedupe dropped {len(drop)} pm_ twin row(s)")
    return k2, n2


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
    # ITF fallback (2026-10-10): ITF rows carry fixture ids no source can match -- 93 synthetic
    # hex ids OpticOdds never issued, and 37 "pm_"+slug ids that pm_results() returns no ITF
    # keys for. All 130 had never settled, so every ITF pick sat permanently pending and absent
    # from every lane record. tennis_itf_settle matches on player name + date against
    # TennisExplorer instead. It fetches web pages, so it is rate-limited to once every
    # ITF_SETTLE_EVERY seconds -- settle() is on the slate path and must not block on it.
    import time as _t
    if _t.time() - _ITF_LAST[0] >= ITF_SETTLE_EVERY:
        _ITF_LAST[0] = _t.time()
        try:
            import tennis_itf_settle
            r9 = tennis_itf_settle.settle(verbose=False)
            if r9.get("settled"):
                print(f"[tennis log] ITF settlement: {r9}")
        except Exception as e:  # noqa: BLE001
            print(f"[tennis log] ITF settlement failed: {e}")


ITF_SETTLE_EVERY = 1800          # seconds between TennisExplorer settlement sweeps
_ITF_LAST = [0.0]


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
    return _tag_watch_signals(out, r, mk1, dog1, gray_p1, c1, have_mkt)


# WATCH TAGGING (2026-10-08, user: "the z bai game still said it was a signal to take her").
# The history line is a RECORD of which signals fired, and it should keep that record --
# that is how we learned these cells lose. But a signal must not LOOK like a pick unless the
# current board would actually tell you to bet it. Favourite-side signals that were demoted
# or refuted on 2026-10-08 keep their entry, lose the ⭐✓ "validated" star, gain a 👁 prefix
# and a watch=True flag, and the history tab draws them grey without ✓/✗ emphasis:
#   FADE-GOLD (fav)    -> demoted: clean live -3.9% (17-8), bt only +4.4%
#   C-EDGE5 FAV        -> demoted: live -26.5% (50 settles)
#   FADE-FORM FAV      -> backtest flat: men -0.6% (n=9,626) / women +0.5% (n=6,031)
#   D-MA2 FAV          -> live negative on 243 settles (men -2.0% / women -8.5%)
#   c75 FAV, c50+c75 on the favourite -> not a board bet (c75 favourites are negative
#                         for men in every band of the as-of backtest)
#   C-ALONE+GRAY on the favourite -> only a bet when it clears the gated 💜 CGF mark
#                         (gray >= 5pt over market, not challenger, men -100..-150 /
#                         women -100..-200); otherwise watch. When it does clear the gates
#                         it is relabelled 💜CGF FAV so it reads as the mark it is.
# LANES THAT KEEP A PICK-BY-PICK RECORD (2026-10-09, user: "keep a live record of low error
# dogs"). Every lane already tracks aggregate PnL; these also remember WHO each pick was, at
# what price, and how it finished, so the record is browsable instead of just a running ROI.
# Kept to an allowlist -- all 128 lanes would bloat /api/tennis/track-record.
# MODEL G LIVE LOG (2026-10-12, user "just restarted the G $25 tab and start a live log
# starting now ... our first game should be juan bautista torres as a dog"). Every G lane counts
# ONLY frozen live picks whose match starts at or after this moment. The backfilled replay is
# gone from the tab entirely -- the user's verdict on it was "those were not the flips", and they
# were right that it never showed those marks on a board, so it has no business in a money
# tracker. The 21 genuine picks that had already started before this cut are excluded too, so the
# log opens on Juan Bautista Torres +152 (G 57.1% on the market dog = a flip) at 22:00Z.
G_LIVE_FROM = "2026-10-12T22:00:00Z"
# How far G must sit ABOVE the market's own price on the favourite before the black mark fires.
# ANY margin, on the user's call: briefly set to 4 points on 2026-10-12 and reverted the same day
# ("nvm all black over the market is fine"). The measurement supports either choice -- a 4pt gate
# cut the cell from 24% of favourites to 14% and moved ROI from -7.25% to -7.23%, flat the whole
# way out to 12pt and every step inside its own standard error -- so the threshold was buying
# selectivity, not accuracy, and it is not worth the complication on a watch-only cell.
# Must stay in lockstep with gMark in TennisSection.jsx and with _g_hist below: a mark and its
# live number have to cover the same games.
G_FAV_OVER_MIN = 0.0

# MODEL G2 LIVE LOG (2026-10-12, user "Track g2 live roi as well when it's done" +
# "Dog flips and favorites over 4+ pts"). G2 = G plus the last-10-on-this-court block. Its
# favourite cell takes the 4-point gate that G was reverted away from, on the user's explicit
# call for G2 -- so the two models are tracked under deliberately different favourite rules and
# the comparison will show whether the gate matters once there is a live sample.
G2_LIVE_FROM = "2026-10-13T01:00:00Z"
G2_FAV_OVER_MIN = 0.04

# MC2 BROWN MARKS (2026-10-13, user "Okay highlight all favorites 2pt + to 8pt a brown and all
# underdog flips a brown for mc2"). Two cells, one colour:
#   mc2_fav_band -- MC2 between 2 and 8 points over the market's price on the FAVOURITE. A BAND,
#                   not a floor: on the live log the favourite side is an inverted U, worthless
#                   at any margin (-1.4% on 87), best around 3-4pt, and negative again past 10pt
#                   -- a huge claimed margin on a short price means MC2 has misread the match,
#                   not found value. Measured in-band: +4.46% on 36 (M -5.2 / W +17.9).
#   mc2_dog_flip -- MC2 puts the market UNDERDOG past 50%. +14.63% on 57 (M +23.0 / W -3.4),
#                   against +2.24% for backing every dog on the same rows.
# Both are WATCH cells on five days of data with standard errors of 12-15 points. The one
# sturdier fact behind them is the dog side at scale: any-margin dog +6.75% on 256.
MC2_LIVE_FROM = "2026-10-13T02:00:00Z"

# THE TAKE RULE'S OWN CLOCK (2026-10-13, user: "those arent forward tests though" -- correct).
#
# The take lanes lit up with 380 settles the moment they were registered, because the lane pass
# replays every frozen row it can find. Those probabilities ARE genuinely pre-match -- frozen
# before each match, so no model input leaks -- but the RULE was written today, after a full day
# of looking at those same outcomes. The replay is therefore in-sample for the rule, and calling
# it a forward test would be wrong.
#
# So the take lanes only count matches starting from here. The replay numbers are kept in the
# card tooltips, labelled as replay, and the lane records below are a clean forward test of the
# rule from this timestamp on.
#
# Replay figures at registration, for the record (frozen rows, in-sample for the rule):
#   mc2_take_fav   men -10.76% / 60    women +12.15% / 53
#   mc2_take_dog   men  +4.17% /155    women +25.62% /112
#   mc3_take_fav   men  -4.64% /  3    women  +9.43% /  3
#   mc3_take_dog   men  -6.00% / 11    women +53.00% / 10
#   both_take_fav  men  -4.64% /  3    women -17.11% /  2
#   both_take_dog  men +29.25% /  8    women +72.14% /  7
TAKE_LIVE_FROM = "2026-10-13T16:00:00Z"
# SAMPLE-ASYMMETRY TILT CUTOVER (2026-10-13). MC2/MC3/MC5 gained a log-odds correction that
# pushes probability away from the thinner-sampled player (tennis_mc2.MC_TILT = 0.35), after
# the user spotted that the heads overprice whoever has fewer matches. Rows logged BEFORE this
# stamp were priced without it, so any mc2_*/mc3_*/mc5_* lane record that straddles this date is
# two different models averaged together. Split on it before reading a lane as evidence.
ASYM_LIVE_FROM = "2026-10-13T22:00:00Z"
# Model P band extension went live with the same deploy. The four p_*_250up/400up lanes
# did not exist before it, so they carry no pre-stamp history to replay.
P_WIDE_LIVE_FROM = "2026-10-13T22:00:00Z"
MC2_FAV_BAND = (0.02, 0.08)
# DEEP favourite cell (2026-10-13, user "Those can be brown highlighted too", about the 9pt+
# favourites). Set at 8pt rather than 9 so the two brown favourite cells are CONTINUOUS -- a card
# at 8.5pt would otherwise fall in a dead zone for no reason, and the 8-9pt sliver is +8.62% on 6
# forward, so there is nothing to exclude. Kept as its OWN cell rather than folded into the band
# because the two are different claims: the band is "a modest, plausible edge", the deep cell is
# "MC2 thinks the market is badly wrong about a favourite". Forward: 8pt+ is +3.28% on 23,
# 9pt+ +1.40% on 17, both inside noise of chalk (-8.46%), and the backfill disagrees (9pt+
# -4.25% on 22). Watch only, and the mark auto-unmarks once its own lane is negative at n>=25.
# Note the shape: at 8pt+ the average favourite is only -158 against -325 for chalk overall, so
# a big claimed margin almost always means a near-coin-flip favourite, not a mispriced strong one.
MC2_FAV_DEEP = 0.08

# MC2 DOG: TAKE vs DEAD ZONE (2026-10-13, user "mark everything above -3 pts take the dog
# Anything -1 to below -3 mark don't take dog").
#
# How far MC2 sits BELOW the market on the favourite, which is the same as how far above it on
# the dog. The measured shape, dog +100..+250, forward then all-rows:
#     within 1pt (agrees)   -44.00% / 26      -30.12% /  66     <- worst state of all
#     -1 to -3 (dead zone)  -64.75% / 12      -17.11% /  63     <- hit 16.7% / 34.9%
#     -3pt or more          +13.23% / 153      +4.53% / 485     <- hit 45.1% / 41.2%
# against a baseline of -0.76% / -0.90% for backing every dog in the band. Both samples agree
# on the sign in all three states and on where it flips, so this is a real threshold rather than
# a tuned one: it takes about three points before MC2 is saying anything, and below that its
# shading is noise that costs money.
#
# So two cells, and the second one is an AVOID -- the first anti-signal mark on this board. Its
# lane bets the dog anyway, which is the only way to keep proving the avoid is right; a lane that
# bets nothing can never be checked.
MC2_DOG_TAKE = 0.03          # MC2 at least this far below the market on the favourite
MC2_DOG_DEAD = (0.01, 0.03)  # the dead zone: shading the dog without really disagreeing
MC2_DOG_AM = (100.0, 250.0)  # dog price band, the user's

# The THIRD brown favourite slice (2026-10-13, user: mark "-100 to -250 that's mc 2 exactly on
# market or over market by anything", then by example on a Putintseva card at ~2pt over).
#
# The 2-8pt band and the 8pt+ deep cell already existed; this fills 0 to 2pt so coverage from
# "exactly on the market" upward is CONTINUOUS. That also removes a real boundary problem: the
# card that prompted this showed MC2 58% against a market 56%, but de-vigging -140/+115 gives a
# 55.6% favourite and MC2's 58% is itself rounded, so the true margin sat somewhere between 1.9
# and 2.4pt -- right on the old 2pt edge, and liable to fall either side of it from rounding
# alone.
#
# Measured, favourite -100..-250, forward then all-rows:
#     0-2pt over   -3.04% /  22      -6.55% /  53
#     2-8pt over   +2.09% /  26      -5.72% /  98
#     8pt+ over    +7.98% /  22      -1.21% /  48
#     all over>=0  +2.33% /  70      -4.86% / 199
#     baseline     -6.79% / 202      -7.08% / 652
# So every slice beats chalk by 1-6 points and NONE of them is profitable on the all-rows check.
# The 0-2pt slice is the weakest and is negative in both samples. It ships because the combined
# cell is positive on forward data and that is the agreed rule, and it will auto-unmark itself
# once it reaches 25 settles if it stays negative.
MC2_FAV_ON = (0.0, 0.02)
# the favourite price band, applied to ALL THREE brown favourite slices. They had no band at all
# before; the user has now specified -100..-250 for favourites twice.
MC2_FAV_AM = (-250.0, -100.0)

# THE LONG-DOG CELL (2026-10-13, user "mark it" about MC2 10pt+ over on a +200..+250 dog).
#
# Its own cell rather than part of mc2_dog3, because it is the one place a LONGER price has held
# up and the mechanism is different: at +225 you only need to beat about 31% to profit, so a
# model that lifts the hit rate 9 points is worth far more there than the same lift on a
# favourite.
#
# Measured, dog +200..+250 with MC2 at least 10pt over on the dog:
#     forward   +21.21% / 19   (36.8% hit)      women +43.56% /  9,  men +1.10% / 10
#     all rows  +28.27% / 55   (40.0% hit)      women +60.60% / 20,  men +9.80% / 35
#     baseline every +200..+250 dog: -1.94% / 50 forward, +1.79% / 146 all-rows
# Positive for both genders in both samples, which is why it is not gender-gated, though the
# women's half carries most of it.
#
# THE PRICE WINDOW IS BOUNDED ON BOTH SIDES, which is the strongest argument that it is real
# rather than scanned. At 10pt+ over, by dog price (all rows):
#     +100..+150   -0.67% /  75
#     +150..+200   -7.22% /  79
#     +200..+250  +22.55% /  49    <- this cell
#     +250..+300  +32.11% /  53    <- also positive, but outside the user's +100..+250 band
#     +300 and up -24.35% / 107    <- the graveyard the archive already warned about
# So the effect starts at +200 and dies by +300. The cell stops at +250 because that is the band
# the user set for marks; +250..+300 is left unmarked and is the obvious extension to discuss.
# THE INPUT-QUALITY GATE (2026-10-13). A thin or stale stat line does not merely add noise to
# MC2, it makes MC2 MORE confident: mean |MC2 - market| is 12.5pt on stale rows against 8.5pt on
# fresh ones, and its Brier gap to the market widens from +0.006 to +0.066. Both gates measured
# in the same direction in the forward sample and the backfill, which is why they ship together:
#     thinner side < 400 service pts : -11.20% /566 all, -6.93% /178 fwd  (>=400: +2.50%, +15.64%)
#     L10 stretch > 450 days         : -51.57% / 36 all, -74.81% / 13 fwd (>730d: 0 wins in 8)
# Deliberately NOT gated on match count: that measured noisy and flipped sign between samples
# (<12 matches was -24.27% on 72 all-rows but +21.19% on 29 forward), so points are the knob.
# NOT IN USE (reverted 2026-10-13, user: "leave mc2 how it was"). Kept only as the record of
# what was measured, because mc2_svp_min / mc2_stretch_d are still frozen per card and the
# question can be revisited. Nothing reads these two numbers -- no mark and no lane is gated.
# They are also NOT the explanation I first gave: MC2 never reads the TennisRatio stat line
# (tennis_mc2 uses tennis_context only to resolve a name to a slug), so svp_n was a proxy,
# most likely for level and data coverage, not a measure of MC2's own inputs.
_UNUSED_MC2_IQ_MIN_SVP = 400.0
_UNUSED_MC2_IQ_MAX_STRETCH = 450.0
MC2_DOG_LONG_AM = (200.0, 250.0)
MC2_DOG_LONG_T = 0.10

_PICK_LANES = {"lowerr_dog_w", "allround_dog_w", "allround_dog_w_big", "returner_dog_w",
               "p_dog_flip"}

_WATCH_LABELS = {
    "⭐✓FADE-GOLD5+": "👁FADE-GOLD (demoted)", "⭐✓FADE-GOLD": "👁FADE-GOLD (demoted)",
    "⭐✓C-EDGE5 FAV": "👁C-EDGE5 FAV (demoted)", "🧊FADE-FORM FAV": "👁FADE-FORM FAV (flat bt)",
    "⭐✓D-MA2 FAV": "👁D-MA2 FAV (live −)", "c75 FAV": "👁c75 FAV",
}


def _tag_watch_signals(out, r, mk1, dog1, gray_p1, c1, have_mkt):
    favp1 = (not dog1) if have_mkt else None
    lg = str(r.get("league") or "")
    wom = ("wta" in lg) or ("itf_women" in lg)
    for e in out:
        lab = e["label"]
        side_p1 = e["side"] == 1
        if lab in _WATCH_LABELS:
            e["label"] = _WATCH_LABELS[lab]
            e["watch"] = True
        elif lab == "c50+c75" and favp1 is not None and side_p1 == favp1:
            e["label"] = "👁c50+c75 FAV"
            e["watch"] = True
        elif lab == "C-ALONE+GRAY" and favp1 is not None and side_p1 == favp1:
            od = r.get("p1_odds") if side_p1 else r.get("p2_odds")
            gate = False
            if (have_mkt and gray_p1 is not None and od is not None and not pd.isna(od)):
                fav_mk = mk1 if side_p1 else 1 - mk1
                g_fav = gray_p1 if side_p1 else 1 - gray_p1
                lo = -200 if wom else -150
                gate = ((g_fav - fav_mk) >= 0.05 and lo <= float(od) <= -100
                        and "challenger" not in lg)
            if gate:
                e["label"] = "💜CGF FAV"
            else:
                e["label"] = "👁C-ALONE+GRAY FAV"
                e["watch"] = True
    return out


_FIXCOLS = ["model_a_p1", "model_ama_p1", "model_b_p1", "model_bma_p1", "model_c_p1",
            "model_cma_p1", "model_d_p1", "model_dma_p1", "mc_p1", "mc_c_p1", "mc_c75_p1",
            "mc_cutr_p1", "c_rp_diff_p1", "c_sp_diff_p1", "model_p_dog", "model_p_prob",
            "model_p_ev", "model_p_fev", "model_g_p1", "model_gma_p1",
            "model_g2_p1", "model_g2ma_p1"]
_fixcache = {"mtime": None, "by": {}}


def _surface_fixes():
    """The wrong-court replay keyed by fixture_id (2026-10-09, user "fix the wrongs for
    previous days"). _surface_fix_history.py recomputes every surface_bad row twice -- on the
    court we had and on the court the match was really played on -- using only data from before
    that match. Missing file = no corrections to show."""
    fp = os.path.join(CACHE_DIR, "_surface_fix_history.parquet")
    try:
        mt = os.path.getmtime(fp)
    except OSError:
        return {}
    if _fixcache["mtime"] == mt:
        return _fixcache["by"]
    try:
        F = pd.read_parquet(fp)
    except Exception:  # noqa: BLE001
        return {}
    by = {}
    for _, x in F.iterrows():
        by[str(x.get("fixture_id"))] = {
            "logged": str(x.get("surface_logged") or ""), "true": str(x.get("surface_true") or ""),
            "src": str(x.get("surface_src") or ""),
            "f": {c: x.get(f"f_{c}") for c in _FIXCOLS},
            "w": {c: x.get(f"w_{c}") for c in _FIXCOLS},
        }
    _fixcache.update({"mtime": mt, "by": by})
    return by


def _ue_asof(r):
    """UNFORCED ERRORS on a finished game (2026-10-10, user "where is the unforced errors on
    result tab" -- they were only ever on today's board). Two different things, both useful:

    "pre"    each player's error profile AS IT STOOD before the match (tennis_ue.profile with
             asof=match date, so no hindsight) -- what the card was reading at the time, and
             the input to the LOW-ERROR DOG gate.
    "actual" what actually happened in THIS match: unforced errors, winners and sets, written
             by tennis_postmatch.backfill from the Match Charting Project once somebody charts
             it. Rare (charting lags ~5 days and covers a fraction of matches) but it is the
             only place the record shows whether the error read came true.
    """
    out = {}
    try:
        import tennis_ue as _tue
        d = pd.Timestamp(str(r.get("date"))[:10])
        sf = str(r.get("surface") or "Hard")
        a, b = _tue.profile(r.get("player_1"), d, sf), _tue.profile(r.get("player_2"), d, sf)
        if a or b:
            out["pre"] = {"p1": a, "p2": b}
    except Exception:  # noqa: BLE001
        pass
    u1, u2 = r.get("ue_p1"), r.get("ue_p2")
    if u1 is not None and not pd.isna(u1) and u2 is not None and not pd.isna(u2):
        def g(c):
            v = r.get(c)
            return None if (v is None or pd.isna(v)) else float(v)
        out["actual"] = {"p1": float(u1), "p2": float(u2), "sets": g("ue_sets"),
                         "win_p1": g("win_p1"), "win_p2": g("win_p2"),
                         "fh_p1": g("ue_fh_p1"), "fh_p2": g("ue_fh_p2")}
    return out or None


def _s52_pair(p1, p2, surface):
    """The seasonal (52-week-on-surface) hold%/break% for both players, as four flat columns.
    Live path: reads the current context, which at log time IS the as-of value because the
    match has not been played yet. Never raises -- a missing player just yields None, and the
    lanes are gated on all four being present."""
    out = {}
    for tag, nm in (("p1", p1), ("p2", p2)):
        sgw = rgw = None
        try:
            import tennis_context as _TC
            st = (_TC.get_context(nm, surface) or {}).get("surface_stats") or {}
            sgw, rgw = st.get("sgw"), st.get("rgw")
        except Exception:
            pass
        out["s52_sgw_" + tag] = None if sgw is None else float(sgw)
        out["s52_rgw_" + tag] = None if rgw is None else float(rgw)
    return out


def _sr_asof(r):
    try:
        import tennis_context as _tcx
        d = pd.Timestamp(str(r.get("date"))[:10])
        sf = str(r.get("surface") or "Hard")
        a = _tcx.context_asof(r.get("player_1"), sf, d)
        b = _tcx.context_asof(r.get("player_2"), sf, d)
        return {"p1": a, "p2": b} if (a or b) else None
    except Exception:  # noqa: BLE001
        return None


def _p_hist(r, mk1):
    try:
        import tennis_model_p as _tp
        return _tp.history_p(r, mk1)
    except Exception:  # noqa: BLE001
        return None


def _g_hist(r, mk1):
    """Ⓖ MODEL G for one finished row (2026-10-12, user "show the new model on the results
    history as well").

    Carries BOTH readings, because they are not the same question:
      * side / hit        -- did G simply pick the winner (what the other model chips show)
      * cell / cell_hit   -- which of G's two RECORDED cells fired, and whether that bet won

    The second is the one the lanes score, and it is the one that matters now the forward
    record is narrowed to fav-over-the-market and dog-flip. A row where G leans to the dog
    without flipping it gets cell=None: that is 52.3% of G's matches and deliberately not a
    recorded bet, so the history must not imply we had a position on it.
    """
    v = r.get("model_g_p1")
    if v is None or pd.isna(v) or pd.isna(r.get("p1_won")) or mk1 is None:
        return None
    p1, p1won = float(v), bool(r["p1_won"])
    fav1 = mk1 >= 0.5
    mkfav = mk1 if fav1 else 1 - mk1
    gfav = p1 if fav1 else 1 - p1
    cell = cell_side = None
    if gfav - mkfav > G_FAV_OVER_MIN:
        cell, cell_side = "FAV-OVER", (1 if fav1 else 2)
    elif gfav < 0.5:
        cell, cell_side = "DOG-FLIP", (2 if fav1 else 1)
    _rc = r.get("model_g_recon")
    out = {"recon": bool(_rc) if (_rc is not None and not pd.isna(_rc)) else False,
           "p1_pct": round(100 * p1, 1), "side": 1 if p1 >= 0.5 else 2,
           "hit": bool((p1 >= 0.5) == p1won), "over_fav": round(gfav - mkfav, 4),
           "cell": cell, "cell_side": cell_side,
           "cell_hit": (None if cell is None else bool((cell_side == 1) == p1won))}
    gm = r.get("model_gma_p1")
    if gm is not None and not pd.isna(gm):
        out["ma_p1_pct"] = round(100 * float(gm), 1)
    return out


def _g2_hist(r, mk1):
    """Ⓖ² MODEL G2 for one finished row (2026-10-12, user "And I want g2 to show on previous
    day slips also"). Same two readings as _g_hist, with G2's own favourite gate: its FAV-OVER
    cell needs 4+ points over the market where G's takes any margin, so the two models can be
    read side by side on the same game and the gate's effect is visible."""
    v = r.get("model_g2_p1")
    if v is None or pd.isna(v) or pd.isna(r.get("p1_won")) or mk1 is None:
        return None
    p1, p1won = float(v), bool(r["p1_won"])
    fav1 = mk1 >= 0.5
    mkfav = mk1 if fav1 else 1 - mk1
    gfav = p1 if fav1 else 1 - p1
    cell = cell_side = None
    if gfav - mkfav >= G2_FAV_OVER_MIN:
        cell, cell_side = "FAV-OVER", (1 if fav1 else 2)
    elif gfav < 0.5:
        cell, cell_side = "DOG-FLIP", (2 if fav1 else 1)
    _rc = r.get("model_g2_recon")
    out = {"recon": bool(_rc) if (_rc is not None and not pd.isna(_rc)) else False,
           "p1_pct": round(100 * p1, 1), "side": 1 if p1 >= 0.5 else 2,
           "hit": bool((p1 >= 0.5) == p1won), "over_fav": round(gfav - mkfav, 4),
           "cell": cell, "cell_side": cell_side,
           "cell_hit": (None if cell is None else bool((cell_side == 1) == p1won))}
    gm = r.get("model_g2ma_p1")
    if gm is not None and not pd.isna(gm):
        out["ma_p1_pct"] = round(100 * float(gm), 1)
    return out


def _g2_signals(r, mk1):
    """Ⓖ² entry for the results-history signal line. Watch-only, like G's."""
    hg = _g2_hist(r, mk1)
    if not hg or not hg.get("cell"):
        return []
    pre = "~" if hg.get("recon") else ""
    return [{"label": pre + "Ⓖ² " + hg["cell"] + " ⚠", "side": hg["cell_side"],
             "hit": bool(hg["cell_hit"]), "watch": True, "recon": bool(hg.get("recon"))}]


def _g_signals(r, mk1):
    """Ⓖ entry for the results-history signal line. Only the two RECORDED cells appear, and
    each is flagged watch-only -- G has no positive backtest cell, so this is a tracker and must
    never read as a pick we recommended."""
    hg = _g_hist(r, mk1)
    if not hg or not hg.get("cell"):
        return []
    pre = "~" if hg.get("recon") else ""
    return [{"label": pre + "Ⓖ " + hg["cell"] + " ⚠", "side": hg["cell_side"],
             "hit": bool(hg["cell_hit"]), "watch": True, "recon": bool(hg.get("recon"))}]


def _p_signals(r, mk1):
    """Ⓟ entries for the results-history signal line (2026-10-09). Frozen P picks from 10-09
    on; earlier days get the ~P lite replay (recon, display-only, never in the P lanes)."""
    if pd.isna(r.get("p1_won")):
        return []
    hp = _p_hist(r, mk1)
    if not hp:
        return []
    p1won = bool(r["p1_won"])
    pre = "~" if hp["recon"] else ""
    out = []
    if hp["bet"]:
        out.append({"label": f"{pre}Ⓟ DOG", "side": hp["dog"], "hit": bool((hp["dog"] == 1) == p1won),
                    "recon": hp["recon"]})
    if hp.get("close"):
        out.append({"label": f"{pre}Ⓟ CLOSE T{hp.get('close_tier', 1)}", "side": hp["fav"], "hit": bool((hp["fav"] == 1) == p1won),
                    "recon": hp["recon"]})
    elif hp["fav_bet"]:
        out.append({"label": f"{pre}Ⓟ FAV⚠", "side": hp["fav"], "hit": bool((hp["fav"] == 1) == p1won),
                    "recon": hp["recon"]})
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
            # the history card's Ⓖ line. n1/n2/gender are live-only (never frozen), so the
            # line renders without them; recon rides along so a backfilled read is dimmed.
            "model_g2": (lambda o: ({**o, "recon": bool(r.get("model_g2_recon"))
                                     if pd.notna(r.get("model_g2_recon")) else False} if o else None))(
                _model("model_g2_p1", "model_g2ma_p1", mk1)),
            "model_g": (lambda o: ({**o, "recon": bool(r.get("model_g_recon"))
                                    if pd.notna(r.get("model_g_recon")) else False} if o else None))(
                _model("model_g_p1", "model_gma_p1", mk1)),
            # SERVE/RETURN as it stood BEFORE this match (2026-10-09, user "I want to see
            # serve/return stats on the previous day page") -- tennis_context.context_asof.
            "tr_context": _sr_asof(r),
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
                        ("gray", "model_cma_p1"), ("D", "model_d_p1"),
                        ("G", "model_g_p1"), ("G2", "model_g2_p1"))},
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
            # MC v2's read per game (2026-10-08, user "put it on previous days tab"):
            # frozen forward picks, plus recon=True walk-forward backfills ("put it on
            # previous games without knowing who won them") — computed from pre-match
            # ratings only, shown dimmed with ~, never in the forward lanes.
            "mc2": (lambda p: ({**p, "recon": bool(r.get("mc2_recon"))
                                 if pd.notna(r.get("mc2_recon")) else False} if p else None))(pickpct(r, "mc2_p1")),
            "mc3": (lambda p: ({**p, "recon": bool(r.get("mc3_recon"))
                                 if pd.notna(r.get("mc3_recon")) else False} if p else None))(pickpct(r, "mc3_p1")),
            "mc5": (lambda p: ({**p, "recon": bool(r.get("mc5_recon"))
                                 if pd.notna(r.get("mc5_recon")) else False} if p else None))(pickpct(r, "mc5_p1")),
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
            "signals": (_elite_signals_for_row(r, mk1) + _p_signals(r, mk1)
                        + _g_signals(r, mk1) + _g2_signals(r, mk1)),
            "model_p": _p_hist(r, mk1),
            # Ⓖ MODEL G per finished game (2026-10-12, user "show the new model on the
            # results history as well"): the probability plus which recorded cell fired.
            "model_g": _g_hist(r, mk1),
            "model_g2": _g2_hist(r, mk1),
            "ue": _ue_asof(r),
            "conflicts": _conflict_resolvers_for_row(r, mk1),
            "card": card,
        }
        # WRONG COURT (2026-10-09, user "fix the wrongs for previous days so i can see what i
        # would have chosen if it was the correct court and put who u told me to take that
        # day"). rec above is the card AS IT WAS -- who we told them to take. Here we add the
        # same reads recomputed on the court the match was actually played on, plus the
        # wrong-court replay so rows that never froze a pick still show what the bad court
        # produced. Both replays come from _surface_fix_history.parquet (as-of, no hindsight).
        _fx = _surface_fixes().get(str(r.get("fixture_id")))
        if _fx:
            def _side(v):
                if v is None or pd.isna(v):
                    return None
                p1side = float(v) >= 0.5
                return {"side": 1 if p1side else 2, "hit": bool(p1side == bool(r["p1_won"])),
                        "p1_pct": round(float(v) * 100, 1)}

            def _reads(vals):
                r9 = r.copy()
                r9["surface"] = _fx["true"] if vals is _fx["f"] else _fx["logged"]
                for _c, _v in vals.items():
                    r9[_c] = _v
                return r9, {
                    "models": {k: _side(vals.get(c)) for k, c in
                               (("A", "model_a_p1"), ("B", "model_b_p1"), ("C", "model_c_p1"),
                                ("gray", "model_cma_p1"), ("D", "model_d_p1"))},
                    "mc_c": {"c50": _side(vals.get("mc_c_p1")), "c75": _side(vals.get("mc_c75_p1")),
                             "cutr": _side(vals.get("mc_cutr_p1"))},
                    "mc": _side(vals.get("mc_p1")),
                    "signals": _elite_signals_for_row(r9, mk1) + _p_signals(r9, mk1),
                    "model_p": _p_hist(r9, mk1),
                }
            _rt, _right = _reads(_fx["f"])
            _rw, _wrong = _reads(_fx["w"])
            # did the correct court actually change a read? (side flip on any model, or a
            # different set of fired signals)
            def _sig_names(v):
                return sorted(str((x or {}).get("n") or "") for x in (v.get("signals") or []))
            _flip = [k for k in _right["models"]
                     if _right["models"][k] and _wrong["models"][k]
                     and _right["models"][k]["side"] != _wrong["models"][k]["side"]]
            _changed = bool(_flip) or _sig_names(_right) != _sig_names(_wrong)
            rec["surface_fix"] = {
                "logged": _fx["logged"], "true": _fx["true"], "src": _fx["src"],
                # was anything actually frozen on the card that day? 107 of the 140 wrong-court
                # rows are from September, before the model columns were logged -- for those no
                # pick was ever shown, and "wrong" below is the only picture of the bad court.
                "frozen": bool(pd.notna(r.get("model_c_p1"))),
                "right": _right, "wrong": _wrong,
                "flips": _flip, "changed": _changed,
            }
            if _changed:
                s_r = _rt                       # _model() reads s_r from this scope
                _ma2 = _model("model_a_p1", "model_ama_p1", mk1)
                _mb2 = _model("model_b_p1", "model_bma_p1", mk1)
                _mc2 = _model("model_c_p1", "model_cma_p1", mk1)
                _md2 = _model("model_d_p1", "model_dma_p1", mk1)
                if _md2 is not None and _fx["f"].get("mc_p1") is not None and pd.notna(_fx["f"]["mc_p1"]):
                    _md2["mc"] = {"sims": 100000, "p1_pct": round(float(_fx["f"]["mc_p1"]) * 100, 1),
                                  "p1_wins": None, "p2_wins": None, "win_prob_home": None}
                if _mc2 is not None:
                    if _fx["f"].get("mc_c_p1") is not None and pd.notna(_fx["f"]["mc_c_p1"]):
                        _mc2["mc"] = {"sims": 40000, "p1_pct": round(float(_fx["f"]["mc_c_p1"]) * 100, 1),
                                      "p1_hold": None, "p2_hold": None, "straight_sets_pct": None,
                                      "c_anchored": True}
                    for _vc in ("mc_c75_p1", "mc_cutr_p1"):
                        _vv = _fx["f"].get(_vc)
                        if _vv is not None and pd.notna(_vv):
                            _mc2[_vc] = round(float(_vv), 4)
                rec["surface_fix"]["card"] = {**card, "surface": _fx["true"],
                                              "fixture_id": str(card["fixture_id"]) + "-fixed",
                                              "model_a": _ma2, "model_b": _mb2,
                                              "model_c": _mc2, "model_d": _md2,
                                              "model_p": _p_hist(_rt, mk1)}
                s_r = r                         # restore for the next iteration
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
                 "vmd": [], "vmf": [], "vwd": [], "vwf": [], "picks": []} for k in
             ("cvg_c", "cvg_gray", "gray_dog4", "grayhate_dog", "grayhate_fav",
              "abc_agree", "abc_dog", "c_alone_gray", "c_alone_gray_dog",
              "c_alone_gray_fav", "gold_names", "green_names", "all6_agree",
              "tier1", "tier2", "tier3", "tier_avoid", "tier_avoid_dog", "tier_nobet", "fade_a",
              "fade_a_dog", "fade_a_dog_gray", "fade_a_fav",
              "goldfav_d45", "goldfav_d5",
              "d_all", "dma_all", "d_gray_dog", "d_alone", "mc_all", "mc_dog",
              "mc_dog_big", "mc_4of4", "mc_gold", "mc_green", "mc_biggray",
              "stardog_prime", "mc_tossup", "cgray_dog_late", "apex_dog",
              "coinflip_c_dog", "mchall_dog_marks",
              # STACK-COUNT lanes (2026-10-11, user "make sure all the numbers are live
              # rois"): how many of the four stackable dog families fire on one card. The
              # board's STACK x1/x2/x3 chip had only an archive backtest number; these give
              # it a live one. One bet per game on the dog, from registration forward.
              "stack1", "stack2", "stack3",
              # 🔵 C-GRAY DOG (2026-10-11, user "Mark all of those dog picks dark blue with
              # positive roi in backtest and live for women or men"). The plain cell: Model C's
              # market-aware head (the board's gray line) on the market UNDERDOG -- no 4pt
              # threshold, no price band. Qualified on BOTH layers for BOTH genders:
              # backtest 3y men +14.8% (n=7,706) / women +39.5% (n=951), 2026 men +10.6% /
              # women +32.2%, live men +1.6% (n=39) / women +14.3% (n=25).
              # A's and B's gray heads were tested and FAILED the backtest (men -4.9% / -0.2%,
              # women -21.7%); D's gray head cannot be backtested with the shipped A/B/C prep,
              # so it is excluded by the both-layers rule despite +26.8% live.
              "cma_dog",
              # 🔵 D-GRAY DOG (2026-10-11, user "It's okay mark Ds dark blue too"). Model D's
              # market-aware head on the market dog. Shipped on the user's explicit call
              # DESPITE having no backtest: the A/B/C walk-forward prep has no core_d, so D's
              # gray head cannot be replayed. Live only -- +26.8% (n=33) at the time of the
              # call. Thinner evidence than cma_dog by construction; the card says so.
              "dma_dog",
              # 🔵 SEASONAL BAND lanes (2026-10-11, user "Mark the band + favorite and band +
              # dog positive roi ones highlight them blue on the board"). Both BET THE DOG at
              # +100..+200; they differ only in which side owns the seasonal hold%+break%.
              # Measured on this log before shipping: fav-better +25.2% (69-63, n=132, 2.4se,
              # band baseline -0.8% on n=632); dog-better +4.2% (40-49, n=89). The mixed case
              # (one stat each) is the negative remainder and is deliberately NOT a lane.
              "s52_fav_band_dog", "s52_dog_band_dog",
              # tracked Model C variants (2026-10-10): same rule, three feature sets, so the
              # control c_ship_dog is what makes the other two readable
              "c_ship_dog", "c_nohb_dog", "c_api_dog",
              "pink_fadeb_dog_m", "pink_wcons_dog", "pink_wall9_fav", "pink_cc75_dog",
              "pink_cclose_c75fav_m", "pink_mc2_dog", "x_dog", "p_dog", "p_dog_any", "p_pass", "p_fav", "p_dog_w250", "p_dog_flip", "p_dog_250up", "p_dog_400up",
              "p_fav_200_250", "p_fav_250up", "p_fav_400up", "p_close", "p_close_t1", "p_close_t2", "p_close_t3", "returner_dog_w", "allround_dog_w", "allround_dog_w_big", "lowerr_dog_w",
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
              "mc2_all", "mc2_edge2", "mc2_dog_band",
              # MC v3 watch lanes (2026-10-13). The first three mirror MC2's exactly so the
              # two heads are measured on the same rules. The last two are the point of
              # building MC3 separately: a PAIRED head-to-head on the rows where the two
              # disagree about which side to take. Pooled records cannot settle it, because
              # the heads agree on most cards and the agreement rows just add identical noise
              # to both -- only the disagreements carry information about which is better.
              "mc3_all", "mc3_edge2", "mc3_dog_band",
              "mc5_all", "mc5_edge2", "mc5_dog_band", "mc5_vs_mc3",
              "mc5_take_fav", "mc5_take_dog",
              # THE USER'S OWN TAKE RULE (2026-10-13, stated verbatim): "favorites are anything
              # mc2 and mc3 have prices over the market or at the same price at the market are
              # the ones i take, then dogs are anything the market has -4 or more on a favorite
              # or a completely flipped side dog to 50% or more on the dog".
              #
              #   FAV  take when the head rates the market favourite AT or ABOVE the market's
              #        own de-vigged number                                 (over >= 0)
              #   DOG  take when the head rates that favourite 4+ points BELOW the market
              #        (over <= -0.04), OR puts the dog at 50% or more outright.
              #
              # The flip clause is NOT redundant with -4pt: a flip on a -300 favourite is
              # already -26pt, but a flip on a -105 favourite is only about -2pt and would
              # otherwise fall in the gap between the two rules.
              #
              # Logged per head AND as an agreement pair, because "mc2 and mc3" can be read
              # either way and measuring both settles it rather than guessing.
              "mc2_take_fav", "mc2_take_dog", "mc3_take_fav", "mc3_take_dog",
              "both_take_fav", "both_take_dog",
              "mc3_vs_mc2", "mc2_vs_mc3",
              "mc4_dog", "mc4_dog_band", "mc4ovr_fav", "mc4ovr_fav_band", "fight_mc4_dog",
              # FORM-FADE split by the pick's side (2026-10-06): forward dogs carry it (+72%),
              # favorites lose (−5%). The board/Best 🧊 tag reads these so it only greens on dogs.
              "pf_c75_dis_dog", "pf_c75_dis_fav",
              # 🔒 HIGH-HIT FAVORITE STACK candidates (2026-10-06, user "track all of these"):
              # favorite + form-confirms, in a price band; ~85-91% hit + small +ROI in-sample,
              # UNVALIDATED (tiny n / multiple-comparison) -- forward-tracked, not yet a take.
              "pf_ghfav", "pf_ghfav_pr", "pf_c75fav_pr", "pf_a10fav_pr",
              # 2026-10-08 watch lanes: fatigue-residual favorites; the MC2-edge cells
              # the replay tour surfaced (orange band fav, 3-5pt banded dog, c75 dog
              # countersigned 5pt+); and the 🪤 bait-favorite dog (all-sim discount).
              "fav_value", "mc2e58_fav", "mc2e35_dog_band", "c75_mc2e5_dog", "bait_dog",
              "bait_dog_prime", "bait_dog_rest", "cgf_shallow_fav", "cgf_premium", "ce5_deep_fav",
              "bait_mcflip", "bait_noflip", "c75_dog_100plus",
              "fadegold_pocket_w")}
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

            _lg9 = str(r.get("league") or "")
            _isw = ("wta" in _lg9) or ("itf_women" in _lg9)
            # WRONG-SURFACE rows (2026-10-09): models ran on the wrong court -> not a valid
            # pick; excluded from every live lane (row kept, flagged surface_bad).
            _sb9 = r.get("surface_bad")
            if _sb9 is not None and not pd.isna(_sb9) and bool(_sb9):
                continue
            # in-play-contaminated price (2026-10-11): the frozen number is not a closing line,
            # so the pick it implies was never on offer pre-match. Same treatment as surface_bad.
            _ip9 = r.get("inplay_suspect")
            if _ip9 is not None and not pd.isna(_ip9) and bool(_ip9):
                continue
            # WRONG PLAYER (2026-10-13): resolver tier 5 substituted a different human when a
            # player was absent from the rating pool -- 15 of 1,120 logged players, several
            # borrowing a tour player's ratings (Ekaterina Agureeva -> EkaterinaAlexandrova,
            # Pedro Henrique Chabalgoity -> PedroCachin). The resolver is fixed so it cannot
            # recur, but the frozen numbers on these rows are about someone else, so the pick
            # they imply was never a pick about these players. Same treatment as surface_bad:
            # row kept, excluded from every lane.
            _rb9 = r.get("resolve_bad")
            if _rb9 is not None and not pd.isna(_rb9) and bool(_rb9):
                continue
            # BLUE GATES (2026-10-09, lockstep with TennisSection tier1Blue): from 10-09
            # forward, a coin-flip C (C < 52% on the dog) no longer counts for
            # C-ALONE+GRAY / TIER-1 / STAR, and men's challenger stats dog marks are
            # NO BET. Those games go to coinflip_c_dog / mchall_dog_marks (one bet per
            # game on the dog) instead, so the downgrade is itself tested forward.
            _fwd9 = str(r.get("date") or "")[:10] >= "2026-10-09"
            _cdog9 = cp if (mk1 < 0.5) else 1 - cp
            _coin9 = _fwd9 and _cdog9 < 0.52
            _mch9 = _fwd9 and (not _isw) and ("challenger" in _lg9)
            _gate_hit = set()
            _fired9 = set()        # (lane, side) pairs this row bet, for the stack count

            def bet(key, side1):
                _fired9.add((key, bool(side1)))
                if key in _PICK_LANES:
                    _od9 = r.get("p1_odds") if side1 else r.get("p2_odds")
                    _ug9 = r.get("ue_set5_diff_p1")
                    study[key]["picks"].append({
                        "date": str(r.get("date"))[:10], "league": r.get("league"),
                        "tournament": r.get("tournament"), "surface": r.get("surface"),
                        "p1": r.get("player_1"), "p2": r.get("player_2"),
                        "pick": r.get("player_1") if side1 else r.get("player_2"),
                        "opp": r.get("player_2") if side1 else r.get("player_1"),
                        "odds": (None if pd.isna(_od9) else int(_od9)),
                        # dog's UE/set minus the favourite's (negative = the dog makes fewer)
                        "ue_gap": (None if (_ug9 is None or pd.isna(_ug9))
                                   else round(float(_ug9) * (1 if side1 else -1), 2)),
                        "score": r.get("score"), "settled": bool(settled),
                        "won": (None if not settled else bool(won1 == side1)),
                        "pnl": (None if not settled else round(
                            25.0 * ((d1 if side1 else d2) - 1.0) if (won1 == side1) else -25.0, 2)),
                    })
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

            # TRACKED C VARIANTS (2026-10-10, user "Yes" to forward-tracking rather than
            # shipping on a backtest). Identical rule per lane -- back the market dog when
            # that flavour of C prefers it -- so the three lanes are comparable game by game.
            # Backtest 2024-26 dog ROI: ship +14.2%, nohb +15.5%, api +14.6%. WATCH ONLY:
            # none of these colours a card or changes a pick.
            # All three lanes are gated on ALL THREE columns being present, so they cover
            # IDENTICAL games. Without that the control would carry its historical rows
            # (156 settles) while the variants started at zero, and the numbers would not be
            # comparable -- which is the whole point of having a control.
            _vcols = ("model_c_p1", "model_cnohb_p1", "model_capi_p1")
            if all(r.get(c9) is not None and pd.notna(r.get(c9)) for c9 in _vcols):
                for _vtag, _vcol in (("c_ship_dog", "model_c_p1"),
                                     ("c_nohb_dog", "model_cnohb_p1"),
                                     ("c_api_dog", "model_capi_p1")):
                    _vside = float(r.get(_vcol)) >= 0.5   # which player this flavour prefers
                    if _vside == dog1:                    # it prefers the market dog
                        bet(_vtag, _vside)

            if c1 != g1:                       # C vs gray FIGHT (2026 bt: C-side -1.5%)
                bet("cvg_c", c1)
                bet("cvg_gray", g1)
            dog1 = mk1 < 0.5                   # player_1 is the market dog
            mdog = mk1 if dog1 else 1 - mk1
            gdog = cma if dog1 else 1 - cma
            if gdog - mdog >= 0.04 and (g1 == dog1):   # gray 4pt+ ON the dog (2026 +9.1%)
                if _mch9:
                    _gate_hit.add("mchall_dog_marks")
                else:
                    bet("gray_dog4", dog1)
            # 🔵 the gray line simply prefers the dog. Deliberately UNFILTERED: gray_dog4
            # above needs a 4pt margin, and the 2026-only backtest showed that threshold is
            # not where the edge is (+8.7 / +8.4 / +15.0 by gap bucket in 2026, a far flatter
            # gradient than the 3-year -3.0 / +6.4 / +25.5), so this lane carries the whole cell.
            if g1 == dog1:
                bet("cma_dog", dog1)
            _dma9 = r.get("model_dma_p1")
            if _dma9 is not None and pd.notna(_dma9) and (float(_dma9) >= 0.5) == dog1:
                bet("dma_dog", dog1)
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
                if _ddec >= 2.0 and (_coin9 or _mch9):
                    _gate_hit.add("coinflip_c_dog" if _coin9 else "mchall_dog_marks")
                elif _ddec >= 2.0:
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
            if _tk in ("tier1", "tier2") and (_coin9 or _mch9):
                _gate_hit.add("coinflip_c_dog" if _coin9 else "mchall_dog_marks")
                _tk = None
            if _tk and str(r.get("date") or "") >= "2026-09-30":
                bet(_tk, _ts)
                # 🟢 THE DOG HALF OF "AVOID" (2026-10-10, user "yes"). tier_avoid exists as a
                # CONTROL that was supposed to LOSE and prove the avoid verdict; instead its
                # dog half runs +19.1% (n=98), men +17.4% / women +22.1%, while its favourite
                # half is +0.9% on n=16 with men-fav -27.3%. Scored separately so the card
                # mark cites the dog-only record rather than the mixed one.
                if _tk == "tier_avoid" and _ts == dog1:
                    bet("tier_avoid_dog", _ts)
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
            # MC v5 watch lanes (2026-10-13), mirroring MC3's so the two are measured on the
            # same rules, plus mc5_vs_mc3 for the rows where the pair disagrees -- the only
            # rows that can separate them, since MC5's weights are deliberately set so that
            # it tracks MC3 closely.
            _m59 = r.get("mc5_p1")
            _m5rec = bool(r.get("mc5_recon")) if pd.notna(r.get("mc5_recon")) else False
            if pd.notna(_m59) and not _m5rec:
                _m5b = float(_m59) >= 0.5
                bet("mc5_all", _m5b)
                _ms5 = float(_m59) if _m5b else 1 - float(_m59)
                _mk5 = mk1 if _m5b else 1 - mk1
                if _ms5 - _mk5 >= 0.02:
                    bet("mc5_edge2", _m5b)
                if _m5b == dog1:
                    _od5 = r.get("p1_odds") if _m5b else r.get("p2_odds")
                    if pd.notna(_od5) and 100 <= float(_od5) <= 250:
                        bet("mc5_dog_band", _m5b)
                if pd.notna(_m39) and not _m3rec and (float(_m39) >= 0.5) != _m5b:
                    bet("mc5_vs_mc3", _m5b)
            # THE USER'S TAKE RULE, per head and as an agreement pair. See the lane-name
            # block above for the verbatim statement. Forward rows only -- a recon backfill is
            # not a pick that was ever shown, so it cannot belong in a money lane.
            _tk = {}
            _tst = str(r.get("start_time_utc") or "")
            for _tag, _pv, _rc9 in ((("mc2", r.get("mc2_p1"), r.get("mc2_recon")),
                                     ("mc3", r.get("mc3_p1"), r.get("mc3_recon")),
                                     ("mc5", r.get("mc5_p1"), r.get("mc5_recon")))
                                    if _tst >= TAKE_LIVE_FROM else ()):
                if pd.isna(_pv):
                    continue
                if pd.notna(_rc9) and bool(_rc9):
                    continue
                _pv = float(_pv)
                _favp = _pv if not dog1 else 1 - _pv      # the head on the MARKET favourite
                _mkf = max(mk1, 1 - mk1)
                _ov = _favp - _mkf
                _flip = _favp < 0.5                        # dog at 50%+ outright
                if _ov >= 0:
                    bet("%s_take_fav" % _tag, not dog1)
                    _tk[_tag] = "fav"
                elif _ov <= -0.04 or _flip:
                    bet("%s_take_dog" % _tag, dog1)
                    _tk[_tag] = "dog"
                else:
                    _tk[_tag] = None                       # the dead zone between the rules
            if _tk.get("mc2") and _tk.get("mc2") == _tk.get("mc3"):
                # both heads say the same thing, which is the stricter reading of "mc2 and mc3"
                bet("both_take_%s" % _tk["mc2"], (not dog1) if _tk["mc2"] == "fav" else dog1)
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
            # 🧮 MC v2 watch lanes (2026-10-08): forward-only, display-grade model.
            # mc2_all = its side every rated match; mc2_edge2 = 2+pt over the market;
            # mc2_dog_band = its pick is a +100..+250 market dog (the house pattern).
            _m29 = r.get("mc2_p1")
            _m2rec = bool(r.get("mc2_recon")) if pd.notna(r.get("mc2_recon")) else False
            if pd.notna(_m29) and not _m2rec:
                _m2b = float(_m29) >= 0.5
                bet("mc2_all", _m2b)
                _ms2 = float(_m29) if _m2b else 1 - float(_m29)
                _mk2 = mk1 if _m2b else 1 - mk1
                if _ms2 - _mk2 >= 0.02:
                    bet("mc2_edge2", _m2b)
                if _m2b == dog1:
                    _od2 = r.get("p1_odds") if _m2b else r.get("p2_odds")
                    if pd.notna(_od2) and 100 <= float(_od2) <= 250:
                        bet("mc2_dog_band", _m2b)
            # 🧮³ MC v3 watch lanes (2026-10-13): MC2 plus per-surface serve/return
            # ratings and best-of-five actually modelled. Same three reads as MC2 above, on
            # the same rows and under the same bet() gate, so the pair is comparable.
            #
            # mc3_vs_mc2 / mc2_vs_mc3 are the pair that matters. On cards where the two heads
            # take DIFFERENT sides, each lane backs its own head. The heads agree on most
            # cards, and those rows contribute the same result to both records, so a pooled
            # comparison is mostly noise cancelling out -- the disagreements are the only
            # rows that can tell them apart, and they are paired by construction (same match,
            # same price, opposite sides, so the two ROIs are a zero-sum read on each other).
            _m39 = r.get("mc3_p1")
            _m3rec = bool(r.get("mc3_recon")) if pd.notna(r.get("mc3_recon")) else False
            if pd.notna(_m39) and not _m3rec:
                _m3b = float(_m39) >= 0.5
                bet("mc3_all", _m3b)
                _ms3 = float(_m39) if _m3b else 1 - float(_m39)
                _mk3 = mk1 if _m3b else 1 - mk1
                if _ms3 - _mk3 >= 0.02:
                    bet("mc3_edge2", _m3b)
                if _m3b == dog1:
                    _od3 = r.get("p1_odds") if _m3b else r.get("p2_odds")
                    if pd.notna(_od3) and 100 <= float(_od3) <= 250:
                        bet("mc3_dog_band", _m3b)
                # the head-to-head, only where they actually differ
                if pd.notna(_m29) and not _m2rec:
                    _m2side = float(_m29) >= 0.5
                    if _m2side != _m3b:
                        bet("mc3_vs_mc2", _m3b)
                        bet("mc2_vs_mc3", _m2side)
            # 🟠 MC2 DOG-EDGE CELLS (2026-10-08, user picked 5-8pt as a watch band; the
            # board paints those cards orange): three forward lanes adjudicate today's
            # replay cells before any of them becomes a bet mark. Genuine mc2 rows only
            # (recon excluded above via _m2rec). mc2e58_fav = take the FAVORITE when MC2
            # prices the dog 5-8pts over market (+5.6% replay, neighbors negative =
            # noise risk); mc2e35_dog_band = 3-5pt dog edge, dog at +100..+250 (+25.8%
            # replay, n=58); c75_mc2e5_dog = c75's dog flip countersigned by a 5pt+ MC2
            # edge (+27.1% replay, fading it -20.5% — the two-sided cell).
            if pd.notna(_m29) and not _m2rec:
                _d2g = float(_m29) if dog1 else 1 - float(_m29)
                _mk2g = mk1 if dog1 else 1 - mk1
                _e2g = _d2g - _mk2g
                if 0.05 <= _e2g < 0.08:
                    bet("mc2e58_fav", not dog1)
                if 0.03 <= _e2g < 0.05:
                    _od3 = r.get("p1_odds") if dog1 else r.get("p2_odds")
                    if pd.notna(_od3) and 100 <= float(_od3) <= 250:
                        bet("mc2e35_dog_band", dog1)
                if _e2g >= 0.05 and pd.notna(r.get("mc_c75_p1")) and (float(r.get("mc_c75_p1")) >= 0.5) == dog1:
                    bet("c75_mc2e5_dog", dog1)
            # 🪤 BAIT_DOG (2026-10-08, user "highlight these green full card"): all 4
            # sims price the FAVORITE >=6pts (women >=4pts) below the no-vig market AND
            # the dog is +100..+200 -> bet the DOG. Replay: +23.4% at 6pts (W +40.1%,
            # M +13.6%), dose-response clean; +200..250 variant loses -42.5% (excluded).
            _bt_heads = [r.get("mc_c_p1"), r.get("mc_c75_p1"), r.get("mc_cutr_p1"), r.get("mc_p1")]
            if all(pd.notna(v) for v in _bt_heads):
                _bt_fav1 = not dog1
                _bt_mkf = mk1 if _bt_fav1 else 1 - mk1
                _bt_wom = "wta" in str(r.get("league") or "") or "itf_women" in str(r.get("league") or "")
                _bt_disc = 0.04 if _bt_wom else 0.06
                _bt_do = r.get("p1_odds") if dog1 else r.get("p2_odds")
                if (pd.notna(_bt_do) and 100 <= float(_bt_do) <= 200
                        and all((float(v) if _bt_fav1 else 1 - float(v)) <= _bt_mkf - _bt_disc
                                for v in _bt_heads)):
                    bet("bait_dog", dog1)
                    # category split (2026-10-08, user "which specific category it lands
                    # in"): PRIME = dog +100..+150 AND full 6pt+ discount; REST = the
                    # remainder of the green cell. Same side, separate records.
                    _bt_fv = [(float(v) if _bt_fav1 else 1 - float(v)) for v in _bt_heads]
                    if float(_bt_do) <= 150 and all(v <= _bt_mkf - 0.06 for v in _bt_fv):
                        bet("bait_dog_prime", dog1)
                    else:
                        bet("bait_dog_rest", dog1)
                    # MC GATE (2026-10-08): does c75 actually FLIP to the dog, or merely
                    # discount the favourite? Full as-of universe: flip M +1.9%
                    # (n=1,492) / W +2.4% (n=1,153); no-flip M -5.3% (n=793) /
                    # W -13.2% (n=631); the UNGATED cell is negative (M -0.6%, W -3.1%).
                    # The card shows ✓ MC CONFIRMS vs ⛔ MC REFUSES · NO BET off this.
                    if (float(r.get("mc_c75_p1")) >= 0.5) == dog1:
                        bet("bait_mcflip", dog1)
                    else:
                        bet("bait_noflip", dog1)
            # ⚫ C75 DOG >= +100 (2026-10-08): the BLACK card's exact cell -- c75 on the
            # market dog at +100 or longer. Full as-of universe: W +8.1% (748-1020,
            # n=1,768) and it improves as the price lengthens; M +5.1% (n=2,308).
            # Odds-on dogs (<+100) are excluded (near-flat +1.4%). The women's cell is
            # the mark; the lane's gender split keeps both halves honest.
            if pd.notna(r.get("mc_c75_p1")):
                _c75d = (float(r.get("mc_c75_p1")) >= 0.5) == dog1
                _c75o = r.get("p1_odds") if dog1 else r.get("p2_odds")
                if _c75d and pd.notna(_c75o) and float(_c75o) >= 100:
                    bet("c75_dog_100plus", dog1)
            # 💜 CGF (2026-10-08, GATED by its own dissection -- _cgf_deep_bt.py, 740
            # in-band fires): C ALONE against A and B, gray confirms, C's side is the
            # FAVORITE, and now three evidence-backed gates that must stay in LOCKSTEP
            # with purpleCGF in TennisSection.jsx:
            #   gray >= 5pt over market  (<2pt ran M -6.3% / W -34.5%; 5pt+ M +12.1% / W +20.6%)
            #   NOT challenger level     (M +2.6% n=260 / W -12.0% n=32)
            #   band: men -100..-150     (men -150..-200 is only +0.7%, n=414)
            #         women -100..-200   (women -150..-200 is +14.7%, n=225)
            # Gated cell: M +24.4% (n=133) / W +22.2% (n=298); with C >= 5pt too
            # (the ★ premium tier) M +31.0% (n=93) / W +26.4% (n=180), all 3 years
            # positive both genders. cgf_premium = the starred sub-cell.
            _cg_a = r.get("model_a_p1"); _cg_b = r.get("model_b_p1")
            _cg_c = r.get("model_c_p1"); _cg_g = r.get("model_cma_p1")
            if all(pd.notna(v) for v in (_cg_a, _cg_b, _cg_c, _cg_g)):
                _cg_c1 = float(_cg_c) >= 0.5
                if ((float(_cg_a) >= 0.5) != _cg_c1 and (float(_cg_b) >= 0.5) != _cg_c1
                        and (float(_cg_g) >= 0.5) == _cg_c1 and _cg_c1 != dog1):
                    _cg_o = r.get("p1_odds") if _cg_c1 else r.get("p2_odds")
                    _cg_lg = str(r.get("league") or "")
                    _cg_wom = "wta" in _cg_lg or "itf_women" in _cg_lg
                    _cg_favp = mk1 if _cg_c1 else 1 - mk1
                    _cg_gray = (float(_cg_g) if _cg_c1 else 1 - float(_cg_g)) - _cg_favp
                    _cg_cedge = (float(_cg_c) if _cg_c1 else 1 - float(_cg_c)) - _cg_favp
                    _cg_lo = -200 if _cg_wom else -150
                    if (pd.notna(_cg_o) and _cg_lo <= float(_cg_o) <= -100
                            and _cg_gray >= 0.05 and "challenger" not in _cg_lg):
                        bet("cgf_shallow_fav", _cg_c1)
                        if _cg_cedge >= 0.05:
                            bet("cgf_premium", _cg_c1)
            # 💜 CE5-DEEP (2026-10-08, user "mark both men and women... purple with the
            # live roi and backtested roi"): raw C prices the FAVORITE >=5pts over the
            # market AND the fav is -150..-200 — the strongest favorite cell in the
            # full backtest (2026: men +11.7% on 466-194/n=660; women +6.9% on 40-19;
            # 3yr +8.1%/+14.3%). This lane is the live judge for the purple mark.
            _ce_c = r.get("model_c_p1")
            if pd.notna(_ce_c):
                _ce_fav1 = not dog1
                _ce_cf = float(_ce_c) if _ce_fav1 else 1 - float(_ce_c)
                _ce_mf = mk1 if _ce_fav1 else 1 - mk1
                _ce_o = r.get("p1_odds") if _ce_fav1 else r.get("p2_odds")
                if (_ce_cf - _ce_mf >= 0.05 and pd.notna(_ce_o)
                        and -200 <= float(_ce_o) <= -150):
                    bet("ce5_deep_fav", _ce_fav1)
            # 💜 FADE-GOLD POCKET W (2026-10-08, user "highlight it the same color as the
            # other favorites"): women only — gray hates the dog >=2pts (FADE-GOLD fires)
            # AND the favorite is -200..-300. The band-split tiebreaker showed the
            # women's all-price -11.5% live record is shallow bands + deep chalk
            # bleeding around a healthy pocket: live -200..-300 = 23-8 ~+4.5%,
            # bt26 -200..-250 +16.9% (54-13) — live and backtest CONVERGE here.
            if pd.notna(r.get("model_cma_p1")):
                _fg_wom = "wta" in str(r.get("league") or "") or "itf_women" in str(r.get("league") or "")
                if _fg_wom:
                    _fg_mdog = mk1 if dog1 else 1 - mk1
                    _fg_gdog = float(r.get("model_cma_p1")) if dog1 else 1 - float(r.get("model_cma_p1"))
                    _fg_o = r.get("p1_odds") if not dog1 else r.get("p2_odds")
                    if (_fg_mdog - _fg_gdog >= 0.02 and pd.notna(_fg_o)
                            and -300 <= float(_fg_o) <= -200):
                        bet("fadegold_pocket_w", not dog1)
            # 💪 FAV-VALUE (2026-10-08, user "make a model that's precise with favorites"):
            # the measured fatigue-residual favorite. Archive 2024-26: ALL favorites
            # −5.2%, heavy-load favorites −0.9% (banded −0.1% vs −5.1%) — the market
            # over-fears fatigue by ~4-5 ROI pts, which clears most of the vig; best
            # available price must do the rest. Lane: market fav at −150..−400 whose
            # frozen 7-day load (our own log) shows 3+ matches AND 2+ excess sets.
            # WATCH-ONLY until the forward record speaks.
            _fv_fav = not dog1
            _fvo = r.get("p1_odds") if _fv_fav else r.get("p2_odds")
            _fvm7 = r.get("p1_m7") if _fv_fav else r.get("p2_m7")
            _fvs7 = r.get("p1_sets7") if _fv_fav else r.get("p2_sets7")
            if (pd.notna(_fvo) and -400 <= float(_fvo) <= -150
                    and pd.notna(_fvm7) and pd.notna(_fvs7)
                    and float(_fvm7) >= 3 and float(_fvs7) - 2 * float(_fvm7) >= 2):
                bet("fav_value", _fv_fav)
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
                    if c1 == dog1 and (_coin9 or _mch9):
                        _gate_hit.add("coinflip_c_dog" if _coin9 else "mchall_dog_marks")
                    elif c1 == dog1:
                        bet("c_alone_gray_dog", c1)
                    else:
                        # the RED-flagged pass config (board highlights the name red)
                        bet("c_alone_gray_fav", c1)
            # 🩷 PINK WATCH LANES (2026-10-09, lockstep with TennisSection pinkCells):
            # FADE-B DOG men (A+C on a +100..+200 dog, B on the fav), W CONSENSUS DOG
            # (women, 7+ of 9 heads on a +100..+200 dog), W ALL-9 FAV (women, all 9
            # heads on a -100..-200 favourite). Nine heads = A, B, C, gray, D, D-MA,
            # c50, c75, serve-MC -- the backtest's nine, same frozen columns.
            _dod9 = float(r["p1_odds"] if dog1 else r["p2_odds"])
            _fod9 = float(r["p2_odds"] if dog1 else r["p1_odds"])
            _pa9, _pb9 = r.get("model_a_p1"), r.get("model_b_p1")
            if (not _isw) and pd.notna(_pa9) and pd.notna(_pb9) and 100 <= _dod9 <= 200:
                if ((float(_pa9) >= 0.5) == dog1) and (c1 == dog1) and ((float(_pb9) >= 0.5) != dog1):
                    bet("pink_fadeb_dog_m", dog1)
            if _isw:
                _hd9 = [r.get(k) for k in ("model_a_p1", "model_b_p1", "model_c_p1", "model_cma_p1",
                                           "model_d_p1", "model_dma_p1", "mc_c_p1", "mc_c75_p1", "mc_p1")]
                if all(v is not None and not pd.isna(v) for v in _hd9):
                    _nd9 = sum(1 for v in _hd9 if (float(v) >= 0.5) == dog1)
                    if _nd9 >= 7 and 100 <= _dod9 <= 200:
                        bet("pink_wcons_dog", dog1)
                    if _nd9 == 0 and -200 <= _fod9 <= -100:
                        bet("pink_wall9_fav", not dog1)
            # 🩷 C + c75 DOG (2026-10-09): C and the c75 sim both on the market dog.
            _c759 = r.get("mc_c75_p1")
            if pd.notna(_c759) and c1 == dog1 and (float(_c759) >= 0.5) == dog1:
                bet("pink_cc75_dog", dog1)
            # 🩷 C-CLOSE c75 FAV men (2026-10-09, user call): C within 5pt of 50%, c75 >= 55%
            # on the market favourite. Live 18-4 at ship; bt 2026 -15.1% (n=295).
            if (not _isw) and pd.notna(_c759) and abs(cp - 0.5) < 0.05:
                _c75f9 = (1 - float(_c759)) if dog1 else float(_c759)
                if _c75f9 >= 0.55:
                    bet("pink_cclose_c75fav_m", not dog1)
            # 🩷 MC2 DOG (2026-10-09): MC2 picks the market dog (men TAKE / women WATCH on the card).
            _m29 = r.get("mc2_p1")
            if _m29 is not None and pd.notna(_m29) and (float(_m29) >= 0.5) == dog1:
                bet("pink_mc2_dog", dog1)
            # ✖ X DOG (2026-10-09, user "start with today's games"): market-free Model X
            # picks the market dog. Scored only on picks the NEW X actually froze
            # (model_x_v == 2, stamped at log time; today's earlier rows were stamped only
            # where the frozen pick equals the new X's output). Recon rows excluded.
            _x9 = r.get("model_x_p1")
            _xr9 = r.get("model_x_recon")
            _xv9 = r.get("model_x_v")
            if (_x9 is not None and pd.notna(_x9) and not (pd.notna(_xr9) and bool(_xr9))
                    and _xv9 is not None and pd.notna(_xv9) and int(_xv9) == 2
                    and (float(_x9) >= 0.5) == dog1):
                bet("x_dog", dog1)
            # Ⓟ MODEL P lanes (2026-10-09): P's bet rule (EV >= 5%) on +100..+200 dogs, plus
            # every P-positive dog (EV > 0) and P's passes (EV <= 0) for contrast.
            _pe9, _pd9 = r.get("model_p_ev"), r.get("model_p_dog")
            if _pe9 is not None and pd.notna(_pe9) and _pd9 is not None and pd.notna(_pd9):
                _ps9 = int(_pd9) == 1
                if float(_pe9) >= 0.05:
                    bet("p_dog", _ps9)
                    # women's +200..+250 extension (2026-10-09) scored on its own too
                    if (d1 if _ps9 else d2) > 3.0:
                        bet("p_dog_w250", _ps9)
                    # 👑 Ⓟ DOG FLIP (2026-10-10, user "mark if any games have P dog flips
                    # with a crown on those picks): P puts the market DOG above 50% -- it is
                    # not finding a few points of value, it is saying the market picked the
                    # wrong favourite. Walk-forward (_model_p_flip_bt.py) this splits the
                    # existing P dog gate cleanly in half:
                    #     women  flip +32.6% (n=1,495) vs no-flip +15.2% (n=1,501)
                    #     men    flip +21.1% (n=1,410) vs no-flip  +9.1% (n=2,425)
                    # Flip alone: W +31.9% (56.1% win vs market's 40.0%), M +20.7%. Positive
                    # every year but decaying -- W +45.3/+34.0/+17.1, M +27.9/+24.2/+7.7 --
                    # and stronger at longer prices (W +58.4% at +200..+250). Flips are ~18%
                    # of women's dogs and ~11% of men's, and nearly always EV bets too
                    # (flip-but-not-EV is n=37/57), so this is a TIER inside p_dog, not a new
                    # universe. Lane p_dog_flip.
                    _pf9 = r.get("model_p_prob")
                    if _pf9 is not None and pd.notna(_pf9) and float(_pf9) > 0.50:
                        bet("p_dog_flip", _ps9)
                if float(_pe9) > 0:
                    bet("p_dog_any", _ps9)
                else:
                    bet("p_pass", _ps9)
                # Ⓟ CLOSE (2026-10-09): fav -100..-150 that P reads >= 3pt above market.
                _pp9 = r.get("model_p_prob")
                _fdc = d2 if _ps9 else d1
                if _pp9 is not None and pd.notna(_pp9) and (1 + 100 / 150) <= _fdc <= 2.0:
                    _mf9 = (1 - mk1) if _ps9 else mk1
                    _ce9 = (1 - float(_pp9)) - _mf9
                    if _ce9 >= 0.03:
                        bet("p_close", not _ps9)
                        bet("p_close_t3" if _ce9 >= 0.15 else ("p_close_t2" if _ce9 >= 0.10 else "p_close_t1"), not _ps9)
                # P FAVOURITE (2026-10-09, user call): fav -100..-200, P fav EV >= 3%.
                _pf9 = r.get("model_p_fev")
                _fd9 = d2 if _ps9 else d1
                if _pf9 is not None and pd.notna(_pf9) and float(_pf9) >= 0.03 and 1.5 <= _fd9 <= 2.0:
                    bet("p_fav", not _ps9)
                # P BAND EXTENSION (2026-10-13, user "model p can go over -250 and over
                # +250 now"). P was retrained on dogs out to +500 / favourites in to -500
                # (_model_p_wide_build.py). The two new regions are scored as SEPARATE
                # lanes because they are different bets and the evidence for them is not
                # the same strength:
                #   favourites below -250, P fav EV >= 3%  -- walk-forward men +10.0%
                #     (n=1,481) and women +13.7% (n=1,512), every year positive both
                #     genders, and the region is independently measured UNDERpriced by
                #     +2.1pt. The better-motivated half.
                #   dogs above +250, P EV >= 5%  -- walk-forward men +13.3% and women
                #     +32.3%, BUT men's 2026 is only +2.9% (+250..+400 alone -6.9%), the
                #     women's figure leans on a +78% 2024, and the region is measured
                #     OVERpriced by 1.7-2.2pt, so a good number here is suspect.
                # Watch-only. No board mark until the live lanes say something, per the
                # colour-promotion rule and the six archive favourite cells that have
                # already failed forward.
                if _pf9 is not None and pd.notna(_pf9) and float(_pf9) >= 0.03 and _fd9 < 1.5:
                    if _fd9 >= 1.4:
                        bet("p_fav_200_250", not _ps9)      # newly open, NOT separately measured
                    else:
                        bet("p_fav_250up", not _ps9)        # the measured cell: M +10.0% W +13.7%
                        if _fd9 < 1.25:
                            bet("p_fav_400up", not _ps9)    # M +10.9% W +13.6%
                if float(_pe9) >= 0.05 and (d1 if _ps9 else d2) > 3.5:
                    bet("p_dog_250up", _ps9)
                    if (d1 if _ps9 else d2) > 5.0:
                        bet("p_dog_400up", _ps9)
            # 🎾 RETURNER DOG (W) (2026-10-09, user "yes"): women, dog +100..+250, the dog
            # wins >= 4.56pt more return-PRESSURE points (52w surface; top third of the gap).
            # Backtest 2025-26: +6.3% (n=751); 2025 +2.8%, 2026 +12.1%; every dog -7.5%.
            _rp9 = r.get("c_rp_diff_p1")
            if _isw and _rp9 is not None and pd.notna(_rp9):
                _dd9 = d1 if dog1 else d2
                if 2.0 <= _dd9 <= 3.5 and (float(_rp9) if dog1 else -float(_rp9)) >= 4.5567:
                    bet("returner_dog_w", dog1)
            # 🧤 LOW-ERROR DOG (W) (2026-10-09, user "do it"; NON-CLAY from 2026-10-10,
            # user "yes"): women, dog +100..+250 whose unforced errors per set (last 5 charted
            # matches) are >= 2.26 lower than the favourite's (the women's median gap), on any
            # court EXCEPT clay. Charted (top-level) players only.
            #
            # The surface split (_ue_surface_split.py) is why clay is out. The gate was shipped
            # on a blended +11.1% (n=361), but by court:
            #     hard  +16.9% (n=199)  2024 +15.9 / 2025 +19.8 / 2026 +13.5  -- every year
            #     grass +22.2% (n=59)
            #     clay  -16.6% (n=72)   2024 -13.2 / 2025 +5.1 / 2026 -37.7
            # against ungated baselines of -0.5% hard, +5.9% grass, -1.0% clay. So the gate
            # ADDS ~17pt on hard and grass and SUBTRACTS ~16pt on clay -- it was not a weaker
            # edge there, it was an inverted one. Dropping clay leaves 258 bets at roughly
            # +18% instead of 330 at +10.5%. Likely mechanism: clay rallies are longer, so
            # error counts inflate for both players and the GAP carries less information --
            # the same effect measured as a +1.69 errors/set clay shift when the Roland Garros
            # data was tested.
            _ue9 = r.get("ue_set5_diff_p1")
            _sf9 = str(r.get("surface") or "").strip().title()
            if _isw and _ue9 is not None and pd.notna(_ue9) and _sf9 != "Clay":
                _dd7 = d1 if dog1 else d2
                _dgap7 = (-float(_ue9)) if dog1 else float(_ue9)     # fav UE/set - dog UE/set
                if 2.0 <= _dd7 <= 3.5 and _dgap7 >= 2.264:
                    bet("lowerr_dog_w", dog1)
            # 🎾 ALL-ROUND DOG (W) (2026-10-09, user "yes", replaces RETURNER DOG on the board):
            # women, dog +100..+250 that is better than the favourite on BOTH serve-pressure
            # and return-pressure points won (52w surface). Backtest 2025-26: +10.2% (n=829;
            # 2025 +8.9 / 2026 +12.6). Tier 2 = both gaps above the women's median (3.08 serve,
            # 3.11 return): +27.5% (n=199; 2025 +28.6 / 2026 +24.9).
            _sp9 = r.get("c_sp_diff_p1")
            if _isw and _rp9 is not None and pd.notna(_rp9) and _sp9 is not None and pd.notna(_sp9):
                _dd8 = d1 if dog1 else d2
                _sgn8 = 1.0 if dog1 else -1.0
                _ds8, _dr8 = _sgn8 * float(_sp9), _sgn8 * float(_rp9)
                if 2.0 <= _dd8 <= 3.5 and _ds8 > 0 and _dr8 > 0:
                    bet("allround_dog_w", dog1)
                    if _ds8 >= 3.0798 and _dr8 >= 3.1104:
                        bet("allround_dog_w_big", dog1)
            # one bet per gated game on the dog (coin-flip takes precedence)
            if "coinflip_c_dog" in _gate_hit:
                bet("coinflip_c_dog", dog1)
            elif "mchall_dog_marks" in _gate_hit:
                bet("mchall_dog_marks", dog1)
            # STACK COUNT (2026-10-11): the same four families the frontend's STACK chip
            # counts -- C-ALONE+GRAY, TIER-1, GRAY 4pt+ DOG, FADE-A DOG+GRAY -- all on the
            # market dog. Must stay in lockstep with TennisSection's STACKABLE set.
            _nst9 = sum(1 for _k9 in ("c_alone_gray_dog", "tier1", "gray_dog4",
                                      "fade_a_dog_gray")
                        if (_k9, bool(dog1)) in _fired9)
            if _nst9:
                bet("stack%d" % min(_nst9, 3), dog1)
    study_out = {k: {**agg(d["v"]), "pending": int(d["p"]),
                     "m": agg(d["vm"]), "w": agg(d["vw"]),
                     "dog": agg(d["vd"]), "fav": agg(d["vf"]),
                     "m_dog": agg(d["vmd"]), "m_fav": agg(d["vmf"]),
                     "w_dog": agg(d["vwd"]), "w_fav": agg(d["vwf"]),
                     **({"picks": d["picks"]} if d.get("picks") else {})}
                 for k, d in study.items()}
    # 🔵 SEASONAL BAND lanes (2026-10-11, user "Mark the band + favorite and band + dog
    # positive roi ones highlight them blue on the board").
    #
    # These run in their OWN pass, deliberately NOT inside the lane loop above. That loop is
    # gated on model_c_p1 AND model_cma_p1 being present, and the blue mark is not -- it needs
    # only the price and the two frozen seasonal pairs. Scoring the lane on the narrower
    # model-gated set gave a visibly different answer (the dog cell read +35.6% on 65 settles
    # there against +4.2% on 89 over all qualifying rows), i.e. the heads were silently
    # selecting the sample. A mark and its live number must cover the SAME games, so the lane
    # mirrors the mark's own condition exactly and nothing else.
    #
    # Both lanes BET THE DOG at +100..+200; they differ only in which side owns BOTH seasonal
    # hold% and break%. The mixed case (one stat each) is the negative remainder, left unlaned.
    _s52 = {k: {"v": [], "m": [], "w": [], "p": 0}
            for k in ("s52_fav_band_dog", "s52_dog_band_dog")}
    _s52cols = ("s52_sgw_p1", "s52_rgw_p1", "s52_sgw_p2", "s52_rgw_p2")
    if all(c in log.columns for c in _s52cols):
        _sq = log[log["p1_odds"].notna() & log["p2_odds"].notna()
                  & log[list(_s52cols)].notna().all(axis=1)]
        for _, rr in _sq.iterrows():
            if "surface_bad" in _sq.columns:
                _sb = rr.get("surface_bad")
                if _sb is not None and not pd.isna(_sb) and bool(_sb):
                    continue
            d1b, d2b = _decimal(rr["p1_odds"]), _decimal(rr["p2_odds"])
            if not d1b or not d2b:
                continue
            i1b, i2b = 1 / d1b, 1 / d2b
            mk1b = i1b / (i1b + i2b)
            dgb = mk1b < 0.5                      # player_1 is the market dog
            dodd = float(rr["p1_odds"] if dgb else rr["p2_odds"])
            if not (100 <= dodd <= 200):
                continue
            sgn = 1.0 if dgb else -1.0            # orient the stat gaps to the DOG
            ds = sgn * (float(rr["s52_sgw_p1"]) - float(rr["s52_sgw_p2"]))
            dr = sgn * (float(rr["s52_rgw_p1"]) - float(rr["s52_rgw_p2"]))
            if ds < 0 and dr < 0:
                key = "s52_fav_band_dog"
            elif ds > 0 and dr > 0:
                key = "s52_dog_band_dog"
            else:
                continue
            if not bool(rr["settled"]) or pd.isna(rr["p1_won"]):
                _s52[key]["p"] += 1
                continue
            won1b = bool(rr["p1_won"])
            dec = d1b if dgb else d2b
            pnl = 25.0 * (dec - 1.0) if (won1b == dgb) else -25.0
            _lgb = str(rr.get("league") or "")
            _s52[key]["v"].append(pnl)
            _s52[key]["w" if ("wta" in _lgb or "itf_women" in _lgb) else "m"].append(pnl)
        for k, v in _s52.items():
            # every pick is a DOG by construction, so dog == overall and fav is empty
            study_out[k] = {**agg(v["v"]), "pending": int(v["p"]),
                            "m": agg(v["m"]), "w": agg(v["w"]),
                            "dog": agg(v["v"]), "fav": agg([]),
                            "m_dog": agg(v["m"]), "m_fav": agg([]),
                            "w_dog": agg(v["w"]), "w_fav": agg([])}

    # MODEL G lanes (2026-10-12). WATCH ONLY -- nothing reads these to gate a pick or paint a
    # card. The lanes exist so the one thing G's backtest says is real -- the opponent-rank
    # adjustment, +1.2/+2.0/+2.8 AUC pts by year -- gets a forward test instead of a promise.
    #
    # ONLY TWO CELLS, on the user's call ("i only want G live record if G has a favorite over
    # the market or an underdog flipping"). The first cut used a flat 5pt threshold on either
    # side, which counted every near-coin-flip wobble; these are the two reads that actually
    # say something, and they are the same shape as the 👑 P DOG FLIP gate and the c75-flip
    # gate that both measured real:
    #   g_fav_over  -- G rates the MARKET FAVOURITE above the market's own price on it. Bets
    #                  the favourite. Strictly over, no threshold: the user asked for "over
    #                  the market", and a size cut can be added later if the cell earns it.
    #   g_dog_flip  -- G puts the market UNDERDOG above 50%, i.e. it does not merely prefer
    #                  the dog, it picks it outright. Bets the dog.
    # They partition cleanly and cannot both fire: G above the market on the favourite implies
    # G has the favourite over 50% (the market favourite is already >= 50%), and flipping the
    # dog implies the opposite. The excluded remainder -- G leaning to the dog without flipping
    # it -- is deliberately unlaned, which is the whole point of the narrowing.
    #
    # OWN PASS, for the reason spelled out above the seasonal block: the lane loop is gated on
    # model_c_p1 AND model_cma_p1, and G's availability is different (it needs a 52w window for
    # both players, which ITF usually lacks). Scoring G on C's rows would let C select G's
    # sample. Gated on model_g_p1 alone, so the lane covers exactly the games G priced.
    #
    # $25 TAB (2026-10-12, user "put model G in the $25 bet tab with all model G's black and
    # gold highlighted picks from every game since we made it yesterday and the roi"): each cell
    # keeps its picks and is scored TWICE --
    #   g_fav_over        / g_dog_flip        = the FORWARD record, frozen live picks only
    #   g_fav_over_replay / g_dog_flip_replay = the backfilled replay, every earlier game
    # kept apart because they are different claims. The forward one is a handful of settles and
    # is the only one that is a record; the replay covers ~1,480 games but was scored after the
    # fact, so it belongs beside the backtest, not in the bankroll. Each pick carries recon so
    # the tab can dim the replayed ones.
    _g = {k: {"v": [], "m": [], "w": [], "p": 0}
          for k in ("g_fav_over", "g_dog_flip", "gma_fav_over", "gma_dog_flip")}
    _gpicks = {k: [] for k in ("g_fav_over", "g_dog_flip")}
    if "model_g_p1" in log.columns:
        _gq = log[log["p1_odds"].notna() & log["p2_odds"].notna() & log["model_g_p1"].notna()]
        if "model_g_recon" in _gq.columns:        # a backfill is not a pick we ever showed
            _gq = _gq[~_gq["model_g_recon"].fillna(False).astype(bool)]
        if "start_time_utc" in _gq.columns:       # and the log opens at G_LIVE_FROM, not earlier
            _gq = _gq[_gq["start_time_utc"].notna()
                      & (_gq["start_time_utc"].astype(str) >= G_LIVE_FROM)]
        for _, rr in _gq.iterrows():
            _rc9 = False
            for _bad in ("surface_bad", "inplay_suspect", "resolve_bad"):
                _bv = rr.get(_bad) if _bad in _gq.columns else None
                if _bv is not None and not pd.isna(_bv) and bool(_bv):
                    break
            else:
                d1g, d2g = _decimal(rr["p1_odds"]), _decimal(rr["p2_odds"])
                if not d1g or not d2g:
                    continue
                mk1g = (1 / d1g) / ((1 / d1g) + (1 / d2g))
                fav1 = mk1g >= 0.5                  # player_1 is the market favourite
                mkfav = mk1g if fav1 else 1 - mk1g  # the market's price on the favourite
                for _tag, _col in (("g", "model_g_p1"), ("gma", "model_gma_p1")):
                    pv = rr.get(_col)
                    if pv is None or pd.isna(pv):
                        continue
                    gfav = float(pv) if fav1 else 1 - float(pv)   # G's read on the favourite
                    if gfav - mkfav > G_FAV_OVER_MIN:
                        key, takes1 = _tag + "_fav_over", fav1
                    elif gfav < 0.5:                 # G flips the market dog outright
                        key, takes1 = _tag + "_dog_flip", not fav1
                    else:
                        continue                     # leans to the dog but never flips it
                    dec = d1g if takes1 else d2g
                    _settled9 = bool(rr["settled"]) and not pd.isna(rr["p1_won"])
                    hit = bool(rr["p1_won"]) == takes1 if _settled9 else None
                    pnl = (None if hit is None else
                           round(25.0 * (dec - 1.0) if hit else -25.0, 2))
                    if key in _gpicks:
                        # SAME COMPACT KEYS the $25 tab's pick list already renders (d/s/o/pr/w/lg)
                        # -- a long-form dict here would render blank rows. g/mk are G's and the
                        # market's number ON THE SIDE TAKEN, and rc dims a replayed pick.
                        _od9 = rr.get("p1_odds") if takes1 else rr.get("p2_odds")
                        _gpicks[key].append({
                            "d": str(rr.get("date") or "")[5:],
                            "s": str(rr.get("player_1") if takes1 else rr.get("player_2")),
                            "o": str(rr.get("player_2") if takes1 else rr.get("player_1")),
                            "pr": (None if pd.isna(_od9) else int(_od9)),
                            "w": hit,
                            "lg": "W" if str(rr.get("league")) in ("wta", "itf_women") else "M",
                            "g": round(100 * (float(pv) if takes1 else 1 - float(pv)), 1),
                            "mk": round(100 * (mk1g if takes1 else 1 - mk1g), 1),
                            "pnl": pnl, "rc": _rc9,
                            "_sort": str(rr.get("start_time_utc") or rr.get("date") or "")})
                    if not _settled9:
                        _g[key]["p"] += 1
                        continue
                    _lgg = str(rr.get("league") or "")
                    _g[key]["v"].append(pnl)
                    _g[key]["w" if ("wta" in _lgg or "itf_women" in _lgg) else "m"].append(pnl)
        for k in _gpicks:
            _gpicks[k].sort(key=lambda x: x.get("_sort") or "", reverse=True)  # newest first
        for k in _gpicks:
            for _x in _gpicks[k]:
                _x.pop("_sort", None)
        for k, v in _g.items():
            # every pick in a cell is the same side by construction, so one of dog/fav is empty
            _isdog = "_dog_flip" in k
            _split = {"from": G_LIVE_FROM}
            study_out[k] = {**agg(v["v"]), "pending": int(v["p"]), **_split,
                            "m": agg(v["m"]), "w": agg(v["w"]),
                            "dog": agg(v["v"] if _isdog else []),
                            "fav": agg([] if _isdog else v["v"]),
                            "m_dog": agg(v["m"] if _isdog else []),
                            "m_fav": agg([] if _isdog else v["m"]),
                            "w_dog": agg(v["w"] if _isdog else []),
                            "w_fav": agg([] if _isdog else v["w"])}

    # MODEL G2 lanes (2026-10-12, user "Track g2 live roi as well when it's done" + "Dog flips
    # and favorites over 4+ pts"). Same two-cell shape as G, same own-pass reasoning, but the
    # favourite cell requires G2 to sit at least 4 points over the market where G's takes any
    # margin -- the user's call, and it means the pair of models will eventually answer whether
    # that gate is worth anything on live money rather than only in the archive.
    _g2 = {k: {"v": [], "m": [], "w": [], "p": 0}
           for k in ("g2_fav_over", "g2_dog_flip")}
    _g2picks = {k: [] for k in _g2}
    if "model_g2_p1" in log.columns:
        _q2 = log[log["p1_odds"].notna() & log["p2_odds"].notna() & log["model_g2_p1"].notna()]
        if "model_g2_recon" in _q2.columns:       # a backfill is never a forward pick
            _q2 = _q2[~_q2["model_g2_recon"].fillna(False).astype(bool)]
        if "start_time_utc" in _q2.columns:
            _q2 = _q2[_q2["start_time_utc"].notna()
                      & (_q2["start_time_utc"].astype(str) >= G2_LIVE_FROM)]
        for _, rr in _q2.iterrows():
            _skip = False
            for _bad in ("surface_bad", "inplay_suspect", "resolve_bad"):
                _bv = rr.get(_bad) if _bad in _q2.columns else None
                if _bv is not None and not pd.isna(_bv) and bool(_bv):
                    _skip = True
            if _skip:
                continue
            d1h, d2h = _decimal(rr["p1_odds"]), _decimal(rr["p2_odds"])
            if not d1h or not d2h:
                continue
            mk1h = (1 / d1h) / ((1 / d1h) + (1 / d2h))
            fav1h = mk1h >= 0.5
            mkfavh = mk1h if fav1h else 1 - mk1h
            pv = rr.get("model_g2_p1")
            if pv is None or pd.isna(pv):
                continue
            gfavh = float(pv) if fav1h else 1 - float(pv)
            if gfavh - mkfavh >= G2_FAV_OVER_MIN:
                key, takes1 = "g2_fav_over", fav1h
            elif gfavh < 0.5:
                key, takes1 = "g2_dog_flip", not fav1h
            else:
                continue
            dech = d1h if takes1 else d2h
            _st2 = bool(rr["settled"]) and not pd.isna(rr["p1_won"])
            hit2 = (bool(rr["p1_won"]) == takes1) if _st2 else None
            pnl2 = None if hit2 is None else round(25.0 * (dech - 1.0) if hit2 else -25.0, 2)
            _od2 = rr.get("p1_odds") if takes1 else rr.get("p2_odds")
            _g2picks[key].append({
                "d": str(rr.get("date") or "")[5:],
                "s": str(rr.get("player_1") if takes1 else rr.get("player_2")),
                "o": str(rr.get("player_2") if takes1 else rr.get("player_1")),
                "pr": (None if pd.isna(_od2) else int(_od2)),
                "w": hit2,
                "lg": "W" if str(rr.get("league")) in ("wta", "itf_women") else "M",
                "g": round(100 * (float(pv) if takes1 else 1 - float(pv)), 1),
                "mk": round(100 * (mk1h if takes1 else 1 - mk1h), 1),
                "pnl": pnl2, "rc": False,
                "_sort": str(rr.get("start_time_utc") or rr.get("date") or "")})
            if not _st2:
                _g2[key]["p"] += 1
                continue
            _lg2 = str(rr.get("league") or "")
            _g2[key]["v"].append(pnl2)
            _g2[key]["w" if ("wta" in _lg2 or "itf_women" in _lg2) else "m"].append(pnl2)
        for k in _g2picks:
            _g2picks[k].sort(key=lambda x: x.get("_sort") or "", reverse=True)
            for _x in _g2picks[k]:
                _x.pop("_sort", None)
        for k, v in _g2.items():
            _isdog2 = k.endswith("_dog_flip")
            study_out[k] = {**agg(v["v"]), "pending": int(v["p"]),
                            "from": G2_LIVE_FROM,
                            "m": agg(v["m"]), "w": agg(v["w"]),
                            "dog": agg(v["v"] if _isdog2 else []),
                            "fav": agg([] if _isdog2 else v["v"]),
                            "m_dog": agg(v["m"] if _isdog2 else []),
                            "m_fav": agg([] if _isdog2 else v["m"]),
                            "w_dog": agg(v["w"] if _isdog2 else []),
                            "w_fav": agg([] if _isdog2 else v["w"])}

    # MC2 BROWN lanes (2026-10-13). Own pass, same reasoning as G's: MC2 is frozen independently
    # of the model heads, so scoring it inside the model-gated loop would let those heads select
    # its sample. Forward picks only -- mc2_recon backfills are dropped, and matches must start at
    # or after MC2_LIVE_FROM so the log opens clean rather than on games already decided.
    # the *_ev keys (2026-10-13) score only the FAVOURITE marks that clear break-even at the
    # offered price. The ungated keys stay as the control: 7 of 9 brown favourite marks on the
    # board that prompted this were negative EV, so the two records should diverge.
    _m2 = {k: {"v": [], "m": [], "w": [], "p": 0}
           for k in ("mc2_fav_on", "mc2_fav_band", "mc2_fav_deep", "mc2_dog_flip",
                     "mc2_dog3", "mc2_dog_dead", "mc2_dog_long", "mc2_dog_250_300",
                     "mc2_fav_on_ev", "mc2_fav_band_ev", "mc2_fav_deep_ev")}
    _m2picks = {k: [] for k in _m2}
    _m2_meta = {"take": MC2_DOG_TAKE, "dead": list(MC2_DOG_DEAD),
                "dog_am": list(MC2_DOG_AM), "fav_am": list(MC2_FAV_AM),
                "fav_on": list(MC2_FAV_ON),
                "dog_long_am": list(MC2_DOG_LONG_AM),
                "dog_long_t": MC2_DOG_LONG_T}
    if "mc2_p1" in log.columns:
        _q3 = log[log["p1_odds"].notna() & log["p2_odds"].notna() & log["mc2_p1"].notna()]
        if "mc2_recon" in _q3.columns:
            _q3 = _q3[~_q3["mc2_recon"].fillna(False).astype(bool)]
        if "start_time_utc" in _q3.columns:
            _q3 = _q3[_q3["start_time_utc"].notna()
                      & (_q3["start_time_utc"].astype(str) >= MC2_LIVE_FROM)]
        for _, rr in _q3.iterrows():
            _sk = False
            for _bad in ("surface_bad", "inplay_suspect", "resolve_bad"):
                _bv = rr.get(_bad) if _bad in _q3.columns else None
                if _bv is not None and not pd.isna(_bv) and bool(_bv):
                    _sk = True
            if _sk:
                continue
            d1m, d2m = _decimal(rr["p1_odds"]), _decimal(rr["p2_odds"])
            if not d1m or not d2m:
                continue
            mk1m = (1 / d1m) / ((1 / d1m) + (1 / d2m))
            fav1m = mk1m >= 0.5
            mkfavm = mk1m if fav1m else 1 - mk1m
            pv = float(rr["mc2_p1"])
            mcfav = pv if fav1m else 1 - pv
            overm = mcfav - mkfavm
            _dogodd = d2m if fav1m else d1m
            _dogam = (_dogodd - 1) * 100
            _dogband = MC2_DOG_AM[0] <= _dogam <= MC2_DOG_AM[1]
            _favodd = d1m if fav1m else d2m
            _favam = ((_favodd - 1) * 100 if _favodd >= 2
                      else -100.0 / max(_favodd - 1, 1e-9))
            _favband = MC2_FAV_AM[0] <= _favam <= MC2_FAV_AM[1]
            # +250..+300 with ALL THREE heads 8pt+ over on the dog (2026-10-13, user
            # "lets cap it at 300"). Three-head agreement is part of the rule, so the lane
            # reads mc3_p1 and mc5_p1 too -- a mark the board shows on three heads must not be
            # scored here on one. A row missing either head cannot satisfy the rule.
            _ag8 = None
            if 250 < _dogam <= 300 and overm <= -0.08:
                _ag8 = True
                for _c8 in ("mc3_p1", "mc5_p1"):
                    _v8 = rr.get(_c8) if _c8 in _q3.columns else None
                    if _v8 is None or pd.isna(_v8):
                        _ag8 = False
                        break
                    _pf8 = float(_v8) if fav1m else 1.0 - float(_v8)
                    if (_pf8 - mkfavm) > -0.08:      # that head is not 8pt+ on the dog
                        _ag8 = False
                        break
            if _ag8:
                key, takes1 = "mc2_dog_250_300", (not fav1m)
            elif (MC2_DOG_LONG_AM[0] <= _dogam <= MC2_DOG_LONG_AM[1]
                    and overm <= -MC2_DOG_LONG_T):
                # checked FIRST: it is the more specific claim and overlaps mc2_dog3
                key, takes1 = "mc2_dog_long", (not fav1m)
            elif _dogband and overm <= -MC2_DOG_TAKE:
                key, takes1 = "mc2_dog3", (not fav1m)
            elif _dogband and -MC2_DOG_DEAD[1] < overm <= -MC2_DOG_DEAD[0]:
                # the AVOID cell. The lane still bets the dog, because that is the only way to
                # keep testing whether the avoid is right -- a lane that bets nothing proves
                # nothing. The board shows it as "do not take", not as a pick.
                key, takes1 = "mc2_dog_dead", (not fav1m)
            elif _favband and overm > MC2_FAV_DEEP:
                key, takes1 = "mc2_fav_deep", fav1m
            elif _favband and MC2_FAV_BAND[0] <= overm <= MC2_FAV_BAND[1]:
                key, takes1 = "mc2_fav_band", fav1m
            elif _favband and MC2_FAV_ON[0] <= overm < MC2_FAV_ON[1]:
                key, takes1 = "mc2_fav_on", fav1m
            elif mcfav < 0.5 and overm <= -MC2_DOG_TAKE:
                # a flip under 3pt is NOT a take (2026-10-13, user "remove this signal from
                # anything under 3 pts"). MC2 can cross 50% on a tiny margin when the market is
                # near even, and those land in the measured dead zone: 1-3pt below on the
                # favourite is -17.11% on 63 all-rows at a 34.9% hit rate. The flip now needs
                # the same 3pt disagreement every other take needs.
                key, takes1 = "mc2_dog_flip", not fav1m
            else:
                continue
            decm = d1m if takes1 else d2m
            # EV at the offered price, for the favourite cells only. mcfav is MC2's own
            # probability on the favourite and _favodd its decimal price, so mcfav*_favodd - 1
            # is MC2's own EV on the bet the mark recommends. Negative means the mark cannot
            # make money by its own numbers.
            _favev_key = None
            if key in ("mc2_fav_on", "mc2_fav_band", "mc2_fav_deep"):
                if (mcfav * _favodd - 1.0) >= 0.0:
                    _favev_key = key + "_ev"
            _st3 = bool(rr["settled"]) and not pd.isna(rr["p1_won"])
            hit3 = (bool(rr["p1_won"]) == takes1) if _st3 else None
            pnl3 = None if hit3 is None else round(25.0 * (decm - 1.0) if hit3 else -25.0, 2)
            _od3 = rr.get("p1_odds") if takes1 else rr.get("p2_odds")
            _m2picks[key].append({
                "d": str(rr.get("date") or "")[5:],
                "s": str(rr.get("player_1") if takes1 else rr.get("player_2")),
                "o": str(rr.get("player_2") if takes1 else rr.get("player_1")),
                "pr": (None if pd.isna(_od3) else int(_od3)),
                "w": hit3,
                "lg": "W" if str(rr.get("league")) in ("wta", "itf_women") else "M",
                "g": round(100 * (pv if takes1 else 1 - pv), 1),
                "mk": round(100 * (mk1m if takes1 else 1 - mk1m), 1),
                "pnl": pnl3, "rc": False,
                "_sort": str(rr.get("start_time_utc") or rr.get("date") or "")})
            if _favev_key:
                _m2picks[_favev_key].append(dict(_m2picks[key][-1]))
            if not _st3:
                _m2[key]["p"] += 1
                if _favev_key:
                    _m2[_favev_key]["p"] += 1
                continue
            _lg3 = str(rr.get("league") or "")
            _wm3 = "w" if ("wta" in _lg3 or "itf_women" in _lg3) else "m"
            for _k3 in (key, _favev_key) if _favev_key else (key,):
                _m2[_k3]["v"].append(pnl3)
                _m2[_k3]["w" if _wm3 == "w" else "m"].append(pnl3)
        for k in _m2picks:
            _m2picks[k].sort(key=lambda x: x.get("_sort") or "", reverse=True)
            for _x in _m2picks[k]:
                _x.pop("_sort", None)
        for k, v in _m2.items():
            _isdog3 = k.endswith("_dog_flip") or k in ("mc2_dog3", "mc2_dog_long",
                                                          "mc2_dog_250_300", "mc2_dog_dead")
            study_out[k] = {**agg(v["v"]), "pending": int(v["p"]), "from": MC2_LIVE_FROM,
                            "m": agg(v["m"]), "w": agg(v["w"]),
                            "dog": agg(v["v"] if _isdog3 else []),
                            "fav": agg([] if _isdog3 else v["v"]),
                            "m_dog": agg(v["m"] if _isdog3 else []),
                            "m_fav": agg([] if _isdog3 else v["m"]),
                            "w_dog": agg(v["w"] if _isdog3 else []),
                            "w_fav": agg([] if _isdog3 else v["w"])}

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

    # ===================================================================================
    # ORANGE SCAN (2026-10-13, user: "mark all the positive roi forward tests on favorites for
    # men and women ... dark orange", then "and for the underdogs when favorites are 1 pts",
    # "Negative points by 4+ from our test", and "make sure it's only on -100 to -250 favorites
    # or +100 to +250 dogs").
    #
    # A catalogue of head x side x threshold x gender cells scored on FORWARD rows only, inside
    # the price band, with the positive ones at n >= 20 returned so the board can mark whichever
    # qualifying cell is performing best on a given card. Recomputed every call, so a cell drops
    # out the moment its forward record turns negative -- the forward-only rule applied to the
    # whole grid rather than to a few hand-picked marks.
    #
    # PRICE BAND: favourites -100..-250, dogs +100..+250. The user's constraint, and it matches
    # where this log has ever shown anything: longer dogs are a graveyard (+300 dogs went 2-14 in
    # one cell here) and deep chalk is unbeatable after vig.
    #
    # READ THE COVERAGE BEFORE READING THE CELLS. Over the full grid, dog cells come back ~52%
    # positive and favourite cells ~10%. If nothing were real you would expect about half either
    # way, so the dog side looks genuinely positive while the favourite side is a negative
    # distribution whose positives are its lucky tail -- kept BECAUSE they were up, out of 143
    # tries. The n and ROI travel with every mark so a 21-bet cell cannot pass for a 204-bet one.
    # ===================================================================================
    _OR_HEADS = [("A", "model_a_p1", None), ("B", "model_b_p1", None), ("C", "model_c_p1", None),
                 ("A-MA", "model_ama_p1", None), ("B-MA", "model_bma_p1", None),
                 ("C-MA", "model_cma_p1", None), ("D", "model_d_p1", None),
                 ("D-MA", "model_dma_p1", None), ("G", "model_g_p1", "model_g_recon"),
                 ("G-MA", "model_gma_p1", "model_g_recon"),
                 ("G2", "model_g2_p1", "model_g2_recon"),
                 ("G2-MA", "model_g2ma_p1", "model_g2_recon"),
                 ("MC2", "mc2_p1", "mc2_recon"), ("X", "model_x_p1", "model_x_recon"),
                 ("c50", "mc_c_p1", "mc_c_recon"), ("c75", "mc_c75_p1", "mc_c_recon"),
                 ("cUTR", "mc_cutr_p1", "mc_c_recon"), ("MCserve", "mc_p1", None)]
    _OR_FAV_T = (0.01, 0.02, 0.03, 0.04, 0.06, 0.08)
    # the dog grid matches the favourite grid (2026-10-13, user "Mark all of those as well too",
    # about the 3pt dog cells). It previously held only 1pt and 4pt, so the 3pt threshold -- the
    # best n-to-ROI tradeoff of the three on MC2 (forward +13.2% on 153 in band, all-rows +4.5%
    # on 485) -- could not enter the catalogue at all.
    _OR_DOG_T = (0.01, 0.02, 0.03, 0.04, 0.06, 0.08)
    _OR_MIN_N = 20
    _OR_FAV_AM = (-250.0, -100.0)      # American odds on the favourite
    _OR_DOG_AM = (100.0, 250.0)        # American odds on the dog
    _orange = []
    try:
        _ob = log[(log["settled"] == True) & log["p1_won"].notna()            # noqa: E712
                  & log["p1_odds"].notna() & log["p2_odds"].notna()].copy()
        for _c in ("surface_bad", "inplay_suspect"):
            if _c in _ob.columns:
                _ob = _ob[~_ob[_c].fillna(False).astype(bool)]
        if len(_ob) >= 50:
            _o1 = _ob["p1_odds"].map(_decimal).to_numpy(dtype=float)
            _o2 = _ob["p2_odds"].map(_decimal).to_numpy(dtype=float)
            _mk = (1 / _o1) / ((1 / _o1) + (1 / _o2))
            _w1 = _ob["p1_won"].astype(bool).to_numpy()
            _f1 = _mk >= 0.5
            _mkf = np.where(_f1, _mk, 1 - _mk)
            _fo = np.where(_f1, _o1, _o2)
            _fw = np.where(_f1, _w1, ~_w1)
            _fp = np.where(_fw, _fo - 1, -1.0)
            _do = np.where(_f1, _o2, _o1)
            _dw = ~_fw
            _dp = np.where(_dw, _do - 1, -1.0)
            # American prices, for the band guard
            _fam = np.where(_fo >= 2, (_fo - 1) * 100, -100 / np.maximum(_fo - 1, 1e-9))
            _dam = (_do - 1) * 100
            _infav = (_fam >= _OR_FAV_AM[0]) & (_fam <= _OR_FAV_AM[1])
            _indog = (_dam >= _OR_DOG_AM[0]) & (_dam <= _OR_DOG_AM[1])
            _gg = np.where(_ob["league"].astype(str).isin(["wta", "itf_women"]), "W", "M")
            for _lab, _col, _rc in _OR_HEADS:
                if _col not in _ob.columns:
                    continue
                _pv = pd.to_numeric(_ob[_col], errors="coerce").to_numpy(dtype=float)
                _hv = ~np.isnan(_pv)
                _rcm = (_ob[_rc].fillna(False).astype(bool).to_numpy()
                        if (_rc and _rc in _ob.columns) else np.zeros(len(_ob), bool))
                _fwd = _hv & ~_rcm                      # forward rows only, as asked
                for _side, _ts in (("fav", _OR_FAV_T), ("dog", _OR_DOG_T)):
                    _hd = (np.where(_f1, _pv, 1 - _pv) if _side == "fav"
                           else np.where(_f1, 1 - _pv, _pv))
                    _base = _mkf if _side == "fav" else (1 - _mkf)
                    _pnl, _hit = (_fp, _fw) if _side == "fav" else (_dp, _dw)
                    _band = _infav if _side == "fav" else _indog
                    for _t in _ts:
                        for _g in ("M", "W"):
                            _m = _fwd & _band & ((_hd - _base) >= _t) & (_gg == _g)
                            _n = int(_m.sum())
                            if _n < _OR_MIN_N:
                                continue
                            _roi = 100 * float(_pnl[_m].mean())
                            if _roi <= 0:
                                continue
                            _se = 100 * float(_pnl[_m].std()) / max(_n, 1) ** 0.5
                            _orange.append({
                                "head": _lab, "col": _col, "side": _side,
                                "t": round(_t, 4), "g": _g, "n": _n,
                                "wins": int(_hit[_m].sum()), "roi": round(_roi, 2),
                                "se": round(_se, 1),
                                # RANKING SCORE = ROI minus one standard error, a conservative
                                # lower bound. Needed because the thresholds within one head are
                                # NESTED -- 1pt, 2pt, 3pt and 4pt of the same head are largely
                                # the same bets -- so ranking on raw ROI would always surface
                                # whichever threshold got luckiest, usually the smallest one.
                                # This prefers a 156-bet cell at +11.6% over a 20-bet cell at
                                # +27.3%, which is the right preference. The raw ROI, n and se
                                # still travel to the card so nothing is hidden.
                                "score": round(_roi - _se, 2)})
            _orange.sort(key=lambda x: -x["score"])
    except Exception as _e_or:  # noqa: BLE001
        print(f"[orange scan] {_e_or}")

    def _mw(g):
        return {"m": agg(g["m"]), "w": agg(g["w"])}
    _picks = _lane_picks()      # populates _sideagg -- must run before _sc merges below
    # G is scored in its own ungated pass, so its picks never go through bet()/_lane_picks
    _picks.update({k: v for k, v in _gpicks.items() if v})
    _picks.update({k: v for k, v in _g2picks.items() if v})
    _picks.update({k: v for k, v in _m2picks.items() if v})

    def _sc(key):
        b = _sideagg.get(key) or {}
        return {"dog": agg(b.get("d") or []), "fav": agg(b.get("f") or []),
                "m_dog": agg(b.get("md") or []), "m_fav": agg(b.get("mf") or []),
                "w_dog": agg(b.get("wd") or []), "w_fav": agg(b.get("wf") or [])}
    return {"registered": "2026-09-28", "stake_usd": 25,
            # the orange catalogue: positive FORWARD cells at n>=20 inside the
            # price band (fav -100..-250, dog +100..+250), best ROI first
            "orange": _orange, "orange_min_n": _OR_MIN_N,
            "mc2_dog_rule": _m2_meta,
            "orange_band": {"fav": _OR_FAV_AM, "dog": _OR_DOG_AM},
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
