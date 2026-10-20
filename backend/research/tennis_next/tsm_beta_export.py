"""TSM D_rest paper beta — export a READ-ONLY public snapshot for the dashboard tab.

    python tsm_beta_export.py            # write backend/data_cache/tsm_beta_public.json

Reads the immutable paper prediction ledger and the settlement ledger and writes a flat
JSON snapshot. It never writes to either ledger, runs no model, contacts no feed, and
carries no odds, stake, ROI or bet of any kind -- this is a PAPER PREDICTION record.

The dashboard only ever reads this file, so the tab cannot trigger computation and cannot
drift from the ledger: the snapshot carries both chain heads so it can be checked.
"""
import collections
import datetime as dt
import hashlib
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import tsm_beta as B  # noqa: E402
import tsm_beta_settle as S  # noqa: E402

OUT = os.path.join(HERE, "..", "..", "data_cache", "tsm_beta_public.json")


LOG = os.path.join(HERE, "..", "..", "data_cache", "tennis_prediction_log.parquet")


def _implied(american):
    """American odds -> implied probability (still carries the book's margin)."""
    try:
        o = float(american)
    except (TypeError, ValueError):
        return None
    if o == 0:
        return None
    return (-o / (-o + 100.0)) if o < 0 else (100.0 / (o + 100.0))


def _name_tokens(name):
    """'Filip Cristian Jianu' -> ('f', ['cristian', 'jianu']).

    Same splitting rule as S.tr_name_parts (which also handles CamelCase TR slugs) but the
    surname tokens are kept SEPARATE. The blob that tr_name_parts returns cannot tell a
    dropped middle name from a different surname: 'martin' sits inside 'martinez' just as
    'salazar' sits inside 'salazarmartinez'.
    """
    s = str(name or "")
    if " " in s:
        toks = [t for t in re.split(r"\s+", s) if t]
    else:
        toks = [t for t in re.split(r"(?<=[a-z])(?=[A-Z])", s) if t]
    norm = [re.sub(r"[^a-z]", "", t.lower()) for t in toks]
    norm = [t for t in norm if t]
    if len(norm) < 2:
        return None, norm
    return norm[0][:1], norm[1:]


def _same_person(a, b):
    """Two token forms describe the same human.

    The board log carries shortened names where the schedule carries full ones, so the same
    player reads 'Filip Jianu' / 'Filip Cristian Jianu', 'J.J. Wolf' / 'J J Wolf',
    'Rodrigo Pacheco' / 'Rodrigo Pacheco Mendez'. In every such pair one surname token list
    is a prefix or a suffix of the other, which is exactly what a dropped name part looks
    like -- and which 'Martin' vs 'Martinez' is not.

    Deliberately conservative: the initials must agree, a shared initial is never enough on
    its own, and every relaxed match still has to win at the FIXTURE level -- both players,
    uniquely -- before Market.find() will use it.
    """
    (ia, ta), (ib, tb) = a, b
    if ia and ib and ia != ib:
        return False
    if not ta or not tb:
        return False
    if ta == tb:
        return True
    lo, hi = sorted((ta, tb), key=len)
    if len("".join(lo)) < 4:                 # 'de', 'van' alone prove nothing
        return False
    return lo == hi[:len(lo)] or lo == hi[-len(lo):]


class Market(object):
    """Frozen-log prices for a set of dates, matched onto beta fixtures.

    DISPLAY ONLY, and attached AFTER the fact. The model is market-blind: no price enters
    a prediction, its features, its calibration or its selection. These predictions were
    already written and sealed in the ledger before any price was read here.
    """

    def __init__(self, dates):
        self.exact, self.by_date, self.rows = {}, collections.defaultdict(list), 0
        try:
            import pandas as pd
        except ImportError:
            return
        if not os.path.exists(LOG):
            return
        df = pd.read_parquet(LOG, columns=["date", "player_1", "player_2", "p1_odds",
                                           "p2_odds"])
        df = df[df["date"].astype(str).str[:10].isin(dates)]
        for r in df.itertuples(index=False):
            i1, i2 = _implied(r.p1_odds), _implied(r.p2_odds)
            if i1 is None or i2 is None or (i1 + i2) <= 0:
                continue
            day = str(r.date)[:10]
            pay = {"p1_fair": i1 / (i1 + i2),      # two-way de-vig
                   "vig_pts": round(100 * (i1 + i2 - 1.0), 2),
                   "p1_name": r.player_1, "p2_name": r.player_2}
            self.rows += 1
            la, lb = _name_tokens(r.player_1), _name_tokens(r.player_2)
            self.exact[(day, S.pair_key(r.player_1, r.player_2))] = (la, lb, pay)
            self.by_date[day].append((la, lb, pay))

    @staticmethod
    def _orient(a, la, lb, pay):
        """Return the price with p1_fair restated for the BETA's player 1.

        The log row's own ordering is independent of the schedule's, and the exact key is
        a frozenset, so the side has to be re-established from the names every time.
        """
        if _same_person(a, lb) and not _same_person(a, la):
            out = dict(pay)
            out["p1_fair"] = 1.0 - pay["p1_fair"]
            out["p1_name"], out["p2_name"] = pay["p2_name"], pay["p1_name"]
            return out
        return pay

    def find(self, day, p1, p2):
        """-> (payload oriented to p1, mode). mode 'exact', 'relaxed', or None."""
        a, b = _name_tokens(p1), _name_tokens(p2)
        hit = self.exact.get((day, S.pair_key(p1, p2)))
        if hit is not None:
            la, lb, pay = hit
            return self._orient(a, la, lb, pay), "exact"
        hits = [(la, lb, pay) for (la, lb, pay) in self.by_date.get(day, ())
                if (_same_person(a, la) and _same_person(b, lb))
                or (_same_person(a, lb) and _same_person(b, la))]
        if len(hits) == 1:                  # ambiguous -> refuse, never guess a price
            la, lb, pay = hits[0]
            return self._orient(a, la, lb, pay), "relaxed"
        return None, None


PM_STORE = os.path.join(HERE, "..", "..", "data_cache", "tsm_beta_market_pm.json")
PM_LEAD_S = 120          # stop capturing this close to first serve


class PolymarketStore(object):
    """Second price source, for the fixtures the board's own log never priced.

    The board log only carries matches the board built a card for, and only at whatever
    its odds feed quoted -- today that is the Polymarket fallback filtered to the board's
    own league set, so ITF and every not-yet-built date come back empty. The schedule the
    beta predicts from is much wider, so most picks had no price at all.

    This reads Polymarket's public Gamma markets for the beta's own fixtures and keeps the
    FIRST pre-match capture per fixture, permanently. Two reasons it is frozen rather than
    re-read: a later read of a match in progress is an in-play price (a known trap on this
    feed), and a price that keeps moving is not a price the prediction can be compared to.
    Still display-only: nothing here reaches the model, its features or its selection.
    """

    def __init__(self):
        self.store, self.added, self.captured = {}, 0, False
        if os.path.exists(PM_STORE):
            try:
                with open(PM_STORE, encoding="utf-8") as fh:
                    self.store = json.load(fh)
            except (ValueError, OSError):
                self.store = {}

    def capture(self, preds):
        """Fill in any prediction that is still comfortably pre-match and has no price."""
        want = [p for p in preds
                if p["fixture_identity"] not in self.store
                and _seconds_to_start(p) > PM_LEAD_S]
        if not want:
            return
        cands = _pm_candidates()
        if cands is None:
            return
        self.captured = True
        now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        for p in want:
            hit = _pm_match(cands, p["scheduled_start_utc"], p["player_1"], p["player_2"])
            if hit is None:
                continue
            pay = dict(hit)
            pay["source"] = "polymarket_gamma"
            pay["captured_utc"] = now
            self.store[p["fixture_identity"]] = pay
            self.added += 1
        if self.added:
            with open(PM_STORE, "w", encoding="utf-8") as fh:
                json.dump(self.store, fh, indent=0, sort_keys=True)

    def find(self, p):
        pay = self.store.get(p["fixture_identity"])
        return (pay, "polymarket") if pay else (None, None)


def _seconds_to_start(p):
    try:
        t = dt.datetime.strptime(str(p["scheduled_start_utc"])[:19], "%Y-%m-%dT%H:%M:%S")
    except (ValueError, TypeError, KeyError):
        return -1
    t = t.replace(tzinfo=dt.timezone.utc)
    return (t - dt.datetime.now(dt.timezone.utc)).total_seconds()


def _pm_candidates():
    """[(day, tokens1, tokens2, p1_fair, vig_pts, names)] for every open PM singles market."""
    try:
        sys.path.insert(0, os.path.join(HERE, "..", ".."))
        import polymarket_data as PM
    except ImportError:
        return None
    try:
        evs = PM._fetch_events(False)
    except Exception:  # noqa: BLE001  -- a public feed being down must not fail the export
        return None
    out = []
    for ev in evs:
        try:
            if not PM._is_singles(ev) or ev.get("ended"):
                continue                       # a resolved market prices 1.00 / 0.00
            names = PM._players(ev)
            if not names or len(names) < 2:
                continue
            # _match_price returns the two outcome PROBABILITIES in player_1/player_2 order
            i1, i2 = PM._match_price(ev)
            if i1 is None or i2 is None or min(i1, i2) < 0.03 or (i1 + i2) <= 0:
                continue                       # degenerate / resolving / dead market
            out.append((str(PM._start_time(ev))[:10],
                        _name_tokens(names[0]), _name_tokens(names[1]),
                        {"p1_fair": i1 / (i1 + i2),
                         "vig_pts": round(100 * (i1 + i2 - 1.0), 2),
                         "p1_name": names[0], "p2_name": names[1]}))
        except Exception:  # noqa: BLE001  -- one malformed event must not drop the rest
            continue
    return out


def _pm_match(cands, start_utc, p1, p2):
    """Unique name-pair match within a day of the scheduled start, oriented to p1."""
    day = str(start_utc)[:10]
    a, b = _name_tokens(p1), _name_tokens(p2)
    hits = []
    for (cday, ca, cb, pay) in cands:
        if not _within_a_day(day, cday):
            continue
        if _same_person(a, ca) and _same_person(b, cb):
            hits.append(pay)
        elif _same_person(a, cb) and _same_person(b, ca):
            flip = dict(pay)
            flip["p1_fair"] = 1.0 - pay["p1_fair"]
            flip["p1_name"], flip["p2_name"] = pay["p2_name"], pay["p1_name"]
            hits.append(flip)
    return hits[0] if len(hits) == 1 else None      # ambiguous -> refuse


def _within_a_day(d1, d2):
    """PM's own start time can sit a day either side of the schedule's."""
    try:
        return abs((dt.date.fromisoformat(d1) - dt.date.fromisoformat(d2)).days) <= 1
    except (ValueError, TypeError):
        return False


def _no_market_reason(p, mkt, pm):
    """Why this prediction still carries no price, after both sources were tried."""
    if not pm.captured:
        return "price_source_unavailable"         # Polymarket not reachable this run
    if _seconds_to_start(p) <= PM_LEAD_S:
        # too late for a clean pre-match capture, and we refuse to show an in-play price
        return "started_before_any_price_was_seen"
    return "no_market_open_yet"                   # nobody is quoting this fixture


def build():
    preds, pred_head = S.read_predictions()
    invalid = S.read_invalidated()
    latest = S.latest_settlements()
    _, settle_head = S.read_settlements()
    mkt = Market({str(p["scheduled_start_utc"])[:10] for p in preds})
    pm = PolymarketStore()
    pm.capture([p for p in preds if p["fixture_identity"] not in invalid])
    rows = []
    for p in preds:
        st = latest.get(p["fixture_identity"])
        res = None
        if st is not None:
            if st["outcome"] == "void":
                res = {"status": "void", "note": st.get("outcome_note")}
            else:
                won = (1 if p["p1_prob"] >= 0.5 else 2) == st["outcome"]
                res = {"status": "settled", "winner": st.get("winner_name"),
                       "correct": bool(won), "note": st.get("outcome_note"),
                       "source": st.get("result_source"),
                       "retrieved_utc": st.get("retrieved_utc")}
        # market attached post-hoc for comparison; see Market -- the model never saw it,
        # and the prediction was sealed before any price was read.
        mk, m_mode = mkt.find(str(p["scheduled_start_utc"])[:10],
                              p["player_1"], p["player_2"])
        if mk is None:
            # the board's log never priced this fixture -> fall back to the frozen
            # pre-match Polymarket capture, which also covers ITF and future dates
            mk, m_mode = pm.find(p)
        m_p1 = m_pick = edge = None
        if mk:
            m_p1 = round(mk["p1_fair"], 4)
            # orient the market onto the SAME side the model picked
            model_on_p1 = p["p1_prob"] >= 0.5
            m_pick = round(m_p1 if model_on_p1 else 1 - m_p1, 4)
            edge = round(p["confidence"] - m_pick, 4)
        rows.append({
            "invalidated": p["fixture_identity"] in invalid,
            "market_p1": m_p1, "market_on_pick": m_pick, "edge_vs_market": edge,
            "market_vig_pts": (mk or {}).get("vig_pts"), "market_match": m_mode,
            "market_captured_utc": (mk or {}).get("captured_utc"),
            "market_absent_reason": None if m_mode else _no_market_reason(p, mkt, pm),
            "id": p["identity_digest"],
            "p1": p["player_1"], "p2": p["player_2"],
            "tournament": p["tournament"], "level": p["level"], "tier": p["tier"],
            "surface": p["surface"], "round": p["round"], "format": p["format"],
            "start_utc": p["scheduled_start_utc"],
            "predicted_utc": p["prediction_ts_utc"],
            "pick": p["predicted_winner"],
            "p1_prob": p["p1_prob"], "confidence": p["confidence"], "band": p["band"],
            "data_quality": p["data_quality"],
            "dq_reasons": p.get("data_quality_reasons") or [],
            "elo_only": bool(p.get("elo_only")),
            "ceil": bool(p.get("calibrator_saturated")),
            "archive_age_days": p.get("archive_age_days"),
            "missing_result_risk": p.get("missing_result_risk"),
            "result": res})
    rows.sort(key=lambda r: (r["start_utc"] or "", -r["confidence"]))
    live = [r for r in rows if not r["invalidated"]]
    settled = [r for r in live if r["result"] and r["result"]["status"] == "settled"]
    snap = {
        "schema": "tsm-d_rest-paper-beta/1",
        "generated_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "PAPER_ONLY": "paper predictions only - no money, no wager, no odds, no staking",
        "NO_ACCURACY_CLAIM": "live predictive accuracy has NOT been established; any "
                             "figures here are preliminary and small-sample",
        "SEPARATE_FROM_OFFICIAL_TRIAL": "this is the supervised paper beta; the official "
                                        "16-week prospective trial is inactive and has its "
                                        "own untouched ledger",
        "model": {"version": B.BETA_VERSION,
                  "artifact_sha256": None, "refit": False},
        "ledger": {"prediction_chain_head": pred_head,
                   "settlement_chain_head": settle_head,
                   "predictions": len(rows)},
        "counts": {
            "total": len(live),
            "invalidated": len(rows) - len(live),
            "settled": len(settled),
            "void": sum(1 for r in live if r["result"]
                        and r["result"]["status"] == "void"),
            "pending": sum(1 for r in live if not r["result"]),
            "no_known_data_issue": sum(1 for r in live
                                       if r["data_quality"] == "NO_KNOWN_DATA_ISSUE"),
            "data_quality_unverified": sum(
                1 for r in live if r["data_quality"] == "DATA-QUALITY-UNVERIFIED"),
            "elo_only": sum(1 for r in live if r["elo_only"]),
            "ceil": sum(1 for r in live if r["ceil"]),
            "ge90": sum(1 for r in live if r["confidence"] >= 0.90),
            "ge90_clean": sum(1 for r in live if r["confidence"] >= 0.90
                              and r["data_quality"] == "NO_KNOWN_DATA_ISSUE")},
        "market": {
            "source": "board log closing line (two-way de-vigged), else frozen pre-match Polymarket capture",
            "DISPLAY_ONLY": "attached after the fact for comparison; the model is "
                            "market-blind and no price enters a prediction, its features, "
                            "its calibration or its selection",
            "matched": sum(1 for r in live if r["market_on_pick"] is not None),
            "unmatched": sum(1 for r in live if r["market_on_pick"] is None),
            "from_board_log": sum(1 for r in live
                                  if r["market_match"] in ("exact", "relaxed")),
            "from_polymarket": sum(1 for r in live
                                   if r["market_match"] == "polymarket"),
            "log_rows_for_these_dates": mkt.rows,
            "pm_captures_total": len(pm.store), "pm_captures_new": pm.added,
            "absent_reasons": dict(collections.Counter(
                r["market_absent_reason"] for r in live
                if r["market_absent_reason"]))},
        "by_tier": dict(collections.Counter(r["tier"] for r in live)),
        "by_band": dict(collections.Counter(r["band"] for r in live)),
        "dq_reasons": dict(collections.Counter(x for r in live for x in r["dq_reasons"])),
        "performance": S.report(),
        "predictions": rows}
    try:
        snap["model"]["artifact_sha256"] = json.load(
            open(B.ARTIFACT, encoding="utf-8"))["content_sha256"]
    except Exception:  # noqa: BLE001
        pass
    return snap


if __name__ == "__main__":
    s = build()
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(s, fh)
    body = open(OUT, "rb").read()
    print(json.dumps({k: s[k] for k in ("schema", "generated_utc", "counts", "by_tier",
                                        "dq_reasons")}, indent=1))
    print("\nledger heads:", json.dumps(s["ledger"]))
    print("performance :", s["performance"].get("status")
          or ("scored %d" % s["performance"].get("scored", 0)))
    print("written     :", os.path.relpath(OUT, HERE), "%d bytes" % len(body),
          "sha256", hashlib.sha256(body).hexdigest()[:16])
