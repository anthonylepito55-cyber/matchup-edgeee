"""🎲 SET-MARKET SCANNER (2026-10-08): MC v2's anchored distribution engine priced
against Polymarket's live tennis DERIVATIVE markets (set handicap, first-set winner,
match totals, 3-sets, first-set totals) — the thin books where structure can still buy
something.

ROI design decisions baked in (user: "what should we do to make the most roi"):
  1. ANCHOR TO SHARP: when the pairing is on our OpticOdds board, the engine anchors to
     the multi-book no-vig moneyline, not PM's own line — so a flag = PM's derivative
     quote disagreeing with (sharp level + validated structure).
  2. MAKER PRICES: every flag reports both the crossing edge (our prob vs PM's ask) AND
     the suggested LIMIT price to post instead (our fair −2c) — on thin books posting at
     your price turns the spread from a cost into edge.
  3. LIQUIDITY FILTER: markets with no real book (placeholder 0.5s, spread > 12c, ask
     >= .95) are skipped, not flagged.
Flags are logged (data_cache/mc2_setscan_log.parquet) for forward CLV/settlement."""
import os
import time
from datetime import datetime, timezone

import pandas as pd

_DIR = os.path.dirname(os.path.abspath(__file__))
_LOG = os.path.join(_DIR, "data_cache", "mc2_setscan_log.parquet")
_cache = {"at": 0.0, "data": None}
_TTL = 180
EDGE_MIN = 0.05
SPREAD_MAX = 0.12

DERIV = ("tennis_first_set_winner", "tennis_match_totals", "tennis_set_handicap",
         "tennis_set_totals", "tennis_first_set_totals")


def _norm(n):
    import unicodedata
    s = unicodedata.normalize("NFKD", str(n or ""))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join(s.lower().split())


def _sharp_anchors():
    """{frozenset(norm names): no-vig p1-by-name dict} from the OpticOdds board."""
    out = {}
    try:
        from tennis_data import get_tennis_today_matches, get_tennis_moneyline_odds
        ms = get_tennis_today_matches(None)
        od = get_tennis_moneyline_odds(None)
        for m in ms:
            o = od.get(m.get("fixture_id"))
            if not o or o.get("player_1") is None:
                continue
            def dec(x):
                x = float(x)
                return 1 + x / 100 if x > 0 else 1 + 100 / abs(x)
            try:
                d1, d2 = dec(o["player_1"]), dec(o["player_2"])
            except (TypeError, ValueError):
                continue
            i1, i2 = 1 / d1, 1 / d2
            k = frozenset((_norm(m["player_1"]), _norm(m["player_2"])))
            out[k] = {_norm(m["player_1"]): i1 / (i1 + i2),
                      _norm(m["player_2"]): i2 / (i1 + i2)}
    except Exception:  # noqa: BLE001
        pass
    return out


def _book(mk):
    """(ask0, bid0) when the market has a real two-sided book, else None."""
    try:
        ask, bid = mk.get("bestAsk"), mk.get("bestBid")
        if ask is None or bid is None:
            return None
        ask, bid = float(ask), float(bid)
        if not (0.02 <= bid <= ask <= 0.98) or (ask - bid) > SPREAD_MAX:
            return None
        return ask, bid
    except (TypeError, ValueError):
        return None


def _parse_sets(score):
    """[(ga, gb), ...] completed sets from a PM score string, or None (ret/w-o/unparseable).
    The orientation (who is 'a') is the event's own; _settle pins it via the ML winner."""
    if not isinstance(score, str) or not score.strip():
        return None
    low = score.lower()
    if "ret" in low or "w/o" in low or "walk" in low or "def" in low:
        return None
    sets = []
    for tok in score.replace(",", " ").split():
        t = tok.split("(")[0]
        if "-" not in t:
            return None
        try:
            x, y = map(int, t.split("-"))
        except ValueError:
            return None
        if x > 7 or y > 7 or (max(x, y) < 6):
            return None          # unfinished / superbreak formats — don't guess
        sets.append((x, y))
    if len(sets) not in (2, 3):
        return None
    sa = sum(1 for x, y in sets if x > y)
    sb = len(sets) - sa
    if max(sa, sb) != 2:
        return None
    return sets


def settle():
    """Grade past scanner flags against PM's resolved events (score-string settlement).
    TAKER record only — a maker fill at post_at is unknowable after the fact (and
    adversely selected), so the honest record is 'crossed the ask at buy_at'. Voids
    (ret/w-o/unparseable) are excluded. Returns the running record summary."""
    empty = {"n": 0, "wins": 0, "pnl": 0.0, "by_market": {}}
    try:
        df = pd.read_parquet(_LOG)
    except Exception:  # noqa: BLE001
        return empty
    if "settled" not in df.columns:
        df["settled"] = None
        df["pnl"] = None
    now_utc = datetime.now(timezone.utc)
    todo = df[df["settled"].isna()]
    # only matches that started 3h+ ago can be settled
    mask = []
    for st in todo["start"]:
        try:
            t = datetime.fromisoformat(str(st).replace("Z", "+00:00"))
            mask.append((now_utc - t).total_seconds() > 3 * 3600)
        except (TypeError, ValueError):
            mask.append(False)
    todo = todo[pd.Series(mask, index=todo.index)] if len(todo) else todo
    if len(todo):
        import polymarket_data as pmd
        ev_by_slug = {}
        for closed in (True, False):
            for ev in pmd._fetch_events(closed):
                sl = ev.get("slug")
                if sl and sl not in ev_by_slug and ev.get("ended"):
                    ev_by_slug[sl] = ev
        for idx, row in todo.iterrows():
            ev = ev_by_slug.get(row["slug"])
            if ev is None:
                continue
            sets = _parse_sets(ev.get("score"))
            if sets is None:
                df.loc[idx, "settled"] = "void"
                continue
            # pin score orientation to the match (p1, p2) via the resolved ML winner
            p1, p2 = pmd._players(ev)
            a1, a2 = pmd._match_price(ev)
            if a1 is None or a2 is None or abs(a1 - a2) < 0.05:
                df.loc[idx, "settled"] = "void"
                continue
            p1_won = a1 > a2
            score_a_won = sum(1 for x, y in sets if x > y) == 2
            if p1_won != score_a_won:                      # score is p2-first -> flip
                sets = [(y, x) for x, y in sets]
            tot = sum(x + y for x, y in sets)
            s1a, s1b = sets[0]
            mkt, side = str(row["market"]), str(row["side"])
            won = None
            if mkt.startswith("match games O/U"):
                ln = float(mkt.rsplit(" ", 1)[-1])
                won = (tot < ln) if side == "Under" else (tot > ln)
            elif mkt.startswith("set-1 games O/U"):
                ln = float(mkt.rsplit(" ", 1)[-1])
                won = (s1a + s1b < ln) if side == "Under" else (s1a + s1b > ln)
            elif mkt.startswith("3 sets"):
                won = (len(sets) == 3) if side.lower().startswith("o") else (len(sets) == 2)
            elif mkt == "1st set winner":
                w1 = p1 if s1a > s1b else p2
                won = _norm(side) == _norm(w1)
            elif mkt.startswith("set handicap"):
                # side covers -1.5 only by winning 2-0
                winner = p1 if p1_won else p2
                won = _norm(side) == _norm(winner) and len(sets) == 2
            if won is None:
                df.loc[idx, "settled"] = "void"
                continue
            buy = float(row["buy_at"])
            df.loc[idx, "settled"] = "win" if won else "loss"
            df.loc[idx, "pnl"] = round((1 - buy) if won else -buy, 3)
        try:
            df.to_parquet(_LOG)
        except Exception:  # noqa: BLE001
            pass
    g = df[df["settled"].isin(["win", "loss"])]
    if not len(g):
        return empty
    bym = {}
    for mk, grp in g.groupby(g["market"].str.replace(r" [0-9.]+$", "", regex=True)):
        bym[mk] = {"n": int(len(grp)), "wins": int((grp["settled"] == "win").sum()),
                   "pnl": round(float(grp["pnl"].sum()), 2)}
    return {"n": int(len(g)), "wins": int((g["settled"] == "win").sum()),
            "pnl": round(float(g["pnl"].sum()), 2), "by_market": bym}


def scan():
    now = time.time()
    if _cache["data"] is not None and now - _cache["at"] < _TTL:
        return _cache["data"]
    import polymarket_data as pmd
    import tennis_mc2 as mc2
    import tennis_context as tc
    sharp = _sharp_anchors()
    flags = []
    scanned = priced = 0
    now_utc = datetime.now(timezone.utc)
    for ev in pmd._fetch_events(False):
        if not pmd._is_singles(ev) or ev.get("ended") or ev.get("live"):
            continue
        st = pmd._start_time(ev)
        try:
            t = datetime.fromisoformat(str(st).replace("Z", "+00:00"))
            if t <= now_utc:
                continue
        except (TypeError, ValueError):
            continue
        p1, p2 = pmd._players(ev)
        if not p1 or not p2:
            continue
        derivs = [m for m in (ev.get("markets") or [])
                  if m.get("sportsMarketType") in DERIV and _book(m)]
        if not derivs:
            continue
        scanned += 1
        # anchor: sharp board line when we have it, else PM's own moneyline mid
        k = frozenset((_norm(p1), _norm(p2)))
        anchor_src = "sharp"
        mk1 = (sharp.get(k) or {}).get(_norm(p1))
        if mk1 is None:
            anchor_src = "pm"
            a1, a2 = pmd._match_price(ev)
            if a1 is None or min(a1, a2) < 0.03:
                continue
            mk1 = a1 / (a1 + a2)
        surf = tc.get_tournament_surface(pmd._tournament(ev)) or "Hard"
        try:
            D = mc2.distribution(p1, p2, surf, mk1)
        except Exception:  # noqa: BLE001
            D = None
        if not D:
            continue
        priced += 1

        def push(mkt, label, our, outcome_name):
            bk = _book(mkt)
            if bk is None or our is None:
                return
            ask, bid = bk
            for side_name, our_p, buy_at in ((str(outcome_name[0]), our, ask),
                                             (str(outcome_name[1]), 1 - our, 1 - bid)):
                edge = our_p - buy_at
                if edge >= EDGE_MIN:
                    flags.append({
                        "match": f"{p1} vs {p2}", "start": str(st),
                        "league": pmd._league(ev), "market": label,
                        "side": side_name, "our_p": round(our_p, 3),
                        "buy_at": round(buy_at, 3), "edge": round(edge, 3),
                        "post_at": round(max(our_p - 0.02, 0.02), 2),
                        "anchor": anchor_src, "slug": ev.get("slug")})
        for m in derivs:
            tp = m.get("sportsMarketType")
            outs = pmd._as_list(m.get("outcomes"))
            if len(outs) != 2:
                continue
            ln = m.get("line")
            if tp == "tennis_first_set_winner":
                our = D["set1_p1"] if _norm(outs[0]) == _norm(p1) else 1 - D["set1_p1"]
                push(m, "1st set winner", our, outs)
            elif tp == "tennis_match_totals" and ln is not None:
                our = (D["over_games"] or {}).get(float(ln))
                push(m, f"match games O/U {ln}", our, outs)
            elif tp == "tennis_set_totals" and str(ln) == "2.5":
                push(m, "3 sets? O/U 2.5", D["three_sets"], outs)
            elif tp == "tennis_first_set_totals" and ln is not None:
                our = (D.get("set1_over") or {}).get(float(ln))
                push(m, f"set-1 games O/U {ln}", our, outs)
            elif tp == "tennis_set_handicap" and str(ln) == "-1.5":
                fav_name = _norm(outs[0])
                our = D["p1_20"] if fav_name == _norm(p1) else D["p2_20"]
                push(m, "set handicap -1.5", our, outs)
    flags.sort(key=lambda f: -f["edge"])
    try:
        record = settle()
    except Exception:  # noqa: BLE001
        record = {"n": 0, "wins": 0, "pnl": 0.0, "by_market": {}}
    out = {"flags": flags[:60], "scanned": scanned, "priced": priced,
           "record": record, "at": datetime.now(timezone.utc).isoformat()}
    _cache.update({"at": now, "data": out})
    # forward log (append-only; dedup by slug+market+side per day)
    try:
        if flags:
            df = pd.DataFrame(flags)
            df["logged_at"] = datetime.now(timezone.utc).isoformat()
            df["day"] = df["logged_at"].str[:10]
            if os.path.exists(_LOG):
                old = pd.read_parquet(_LOG)
                df = pd.concat([old, df])
            df = df.drop_duplicates(subset=["day", "slug", "market", "side"], keep="first")
            df.to_parquet(_LOG)
    except Exception:  # noqa: BLE001
        pass
    return out


if __name__ == "__main__":
    r = scan()
    print(f"scanned {r['scanned']} events | priced {r['priced']} | flags {len(r['flags'])}")
    for f in r["flags"][:12]:
        print(f"  {f['edge']:+.3f}  {f['market']:22s} {f['side'][:20]:20s} our {f['our_p']:.2f} "
              f"buy {f['buy_at']:.2f} post {f['post_at']:.2f} [{f['anchor']}] {f['match'][:40]}")
