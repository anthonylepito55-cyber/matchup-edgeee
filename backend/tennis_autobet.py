"""AUTO-BET THE DOG TAB'S HIGHLIGHTS ON POLYMARKET -- PAPER MODE (2026-10-17).

User: "Is there a way to automatically bet on the dog tab highlights pick on Polymarket like just
have something auto place it for me daily" -> Polymarket, paper first.

WHAT IT DOES, every run (systemd timer, every 10 minutes):
  1. Reads the same /api/tennis/track-record the Dog tab reads and runs the tab's OWN pick code
     on it (static/dog_engine.cjs, bundled from DogPicksPanel.jsx by `npm run build`), so the bot
     bets exactly what the tab paints -- pink dogs and gold favourites -- never a Python copy.
  2. For each highlight starting within BET_WINDOW_MIN, finds its Polymarket moneyline market.
     Both players must match (surname+initial, compound-surname aware, the settler's matcher) and
     the pair must resolve to exactly ONE open market within 12h of the start, or it is skipped.
  3. PAPER-FILLS a $STAKE buy against the live order book: walks the asks up to a limit equal to
     the price the tab judged the pick at (never pays more than that), charges Polymarket's
     official sports taker fee (shares x 0.05 x p x (1-p), docs.polymarket.com/trading/fees),
     and respects the market's minimum order size.
  4. Settles filled paper bets from the frozen log (same settlement the lanes use; a retirement
     goes to the player who advances, as Polymarket resolves it).

WHAT IT NEVER DOES: place a real order. There is no live code path. AUTOBET_MODE must be "paper";
anything else stops the run. Live trading needs the venue confirmed (international Polymarket
blocks US order placement; Polymarket US has its own terms) and the user's own credentials,
which this file neither reads nor stores.

SAFETY RULES, in order:
  * both sides of one match highlighted -> neither is bet (opposite bets guarantee a loser)
  * no unique market -> skip; market not accepting orders -> skip
  * start already passed -> no new fill (pre-match only)
  * daily paper stake cap AUTOBET_MAX_DAY (default $1000)
  * kill switch: AUTOBET_ENABLED=0
"""
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
from datetime import datetime, timezone

import pandas as pd
import requests

import polymarket_data as P
import tennis_log as T
from tennis_itf_settle import name_keys

HERE = os.path.dirname(os.path.abspath(__file__))
ENGINE = os.path.join(HERE, "static", "dog_engine.cjs")
STATE = os.path.join(T.CACHE_DIR, "autobet_paper.json")
API = "http://127.0.0.1/api/tennis/track-record"
CLOB_BOOK = "https://clob.polymarket.com/book"

STAKE = float(os.environ.get("AUTOBET_STAKE", "25"))
MAX_DAY = float(os.environ.get("AUTOBET_MAX_DAY", "1000"))
BET_WINDOW_MIN = float(os.environ.get("AUTOBET_WINDOW_MIN", "30"))
SPORTS_TAKER_RATE = 0.05          # docs.polymarket.com/trading/fees, Sports, checked 2026-10-17
MATCH_WINDOW_H = 12.0


# ------------------------------------------------------------------------------ helpers
def _now():
    return datetime.now(timezone.utc)


def _ts(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def _implied(odds):
    """Probability implied by the American odds the tab judged the pick at (vig included)."""
    o = float(odds)
    return 100.0 / (o + 100.0) if o > 0 else -o / (-o + 100.0)


def _american(p):
    return round(100 * (1 - p) / p) if p < 0.5 else -round(100 * p / (1 - p))


def _key(h):
    return "%s|||%s|||%s" % (h.get("date"), h.get("pick"), h.get("opp"))


def _match_key(h):
    return "%s|||%s" % (h.get("date"), "|||".join(sorted([str(h.get("pick")), str(h.get("opp"))])))


def _password():
    pw = os.environ.get("DASHBOARD_PASSWORD")
    if pw:
        return pw
    # the web service's own setting -- read, never copied into this file or a second unit
    try:
        out = subprocess.run(["systemctl", "show", "mlb.service", "-p", "Environment"],
                             capture_output=True, text=True, timeout=10).stdout
        for tok in out.replace("Environment=", "").split():
            if tok.startswith("DASHBOARD_PASSWORD="):
                return tok.split("=", 1)[1]
    except Exception:
        pass
    return ""


def load_state():
    if os.path.exists(STATE):
        with open(STATE, encoding="utf-8") as f:
            return json.load(f)
    return {"mode": "paper", "bets": {}}


def save_state(st):
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(STATE), suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(st, f, indent=1, default=str)
    os.replace(tmp, STATE)


# ------------------------------------------------------------------------------ the picks
def highlights(now_ms=None):
    """The Dog tab's highlighted picks, computed by the tab's own code."""
    req = urllib.request.Request(API, headers={"X-Dashboard-Password": _password()})
    raw = urllib.request.urlopen(req, timeout=180).read()
    args = ["node", ENGINE] + ([str(int(now_ms))] if now_ms else [])
    res = subprocess.run(args, input=raw, capture_output=True, timeout=120)
    if res.returncode != 0:
        raise RuntimeError("dog_engine failed: %s" % res.stderr.decode()[:400])
    return json.loads(res.stdout)


# ------------------------------------------------------------------------------ the market
def _keys_hit(a, b):
    return bool(name_keys(a) & name_keys(b))


def find_market(h, events):
    """The ONE open Polymarket moneyline for this pick, or (None, reason)."""
    st = _ts(h.get("start"))
    hits = []
    for ev in events:
        if not P._is_singles(ev):
            continue
        m = P._moneyline_market(ev)
        if not m or m.get("closed"):
            continue
        outs = P._as_list(m.get("outcomes"))
        if len(outs) != 2:
            continue
        for i in (0, 1):
            if _keys_hit(h["pick"], outs[i]) and _keys_hit(h["opp"], outs[1 - i]):
                es = _ts(P._start_time(ev))
                if st and es and abs((es - st).total_seconds()) > MATCH_WINDOW_H * 3600:
                    continue
                hits.append((ev, m, i))
    if not hits:
        return None, "no_market"
    if len({id(x[1]) for x in hits}) > 1:
        return None, "ambiguous"
    return hits[0], None


def paper_fill(token, limit):
    """Walk the live asks up to `limit`, buying at most STAKE of shares. Taker fee charged."""
    book = requests.get(CLOB_BOOK, params={"token_id": token}, timeout=15).json()
    asks = sorted((float(a["price"]), float(a["size"])) for a in (book.get("asks") or []))
    bids = sorted((float(b["price"]), float(b["size"])) for b in (book.get("bids") or []))
    min_size = float(book.get("min_order_size") or 5)
    left, shares, cost, fee = STAKE, 0.0, 0.0, 0.0
    for price, size in asks:
        if price > limit + 1e-9 or left < 0.01:
            break
        take = min(size, left / price)
        shares += take
        cost += take * price
        fee += take * SPORTS_TAKER_RATE * price * (1 - price)
        left -= take * price
    out = {"best_ask": asks[0][0] if asks else None, "best_bid": bids[-1][0] if bids else None,
           "limit": round(limit, 4), "min_size": min_size}
    if shares < min_size:
        out.update(filled=False)
        return out
    out.update(filled=True, shares=round(shares, 4), cost=round(cost, 4), fee=round(fee, 4),
               avg_price=round(cost / shares, 4), avg_american=_american(cost / shares),
               partial=left >= 0.01)
    return out


# ------------------------------------------------------------------------------ settlement
def settle(state):
    open_bets = [b for b in state["bets"].values() if b.get("status") == "filled" and "result" not in b]
    if not open_bets:
        return 0
    log = pd.read_parquet(T.LOG_PATH)
    n = 0
    for b in open_bets:
        rows = log[(log["date"].astype(str).str[:10] == str(b["date"])[:10])
                   & (((log["player_1"] == b["pick"]) & (log["player_2"] == b["opp"]))
                      | ((log["player_1"] == b["opp"]) & (log["player_2"] == b["pick"])))]
        if len(rows) != 1:
            continue
        r = rows.iloc[0]
        if bool(r.get("void")) if pd.notna(r.get("void")) else False:
            b.update(result="void", pnl=0.0)
            n += 1
            continue
        if not (bool(r["settled"]) and pd.notna(r["p1_won"])):
            continue
        pick_won = bool(r["p1_won"]) if r["player_1"] == b["pick"] else not bool(r["p1_won"])
        pnl = (b["shares"] - b["cost"] - b["fee"]) if pick_won else -(b["cost"] + b["fee"])
        b.update(result="won" if pick_won else "lost", pnl=round(pnl, 2),
                 score=r.get("score"), settled_at=_now().isoformat())
        n += 1
    return n


# ------------------------------------------------------------------------------ one run
def run(verbose=True, dry=False, window_min=None):
    """dry=True: same decisions, nothing saved -- for testing against live markets."""
    window = BET_WINDOW_MIN if window_min is None else float(window_min)
    if os.environ.get("AUTOBET_ENABLED", "1") == "0":
        print("autobet: disabled (AUTOBET_ENABLED=0)")
        return
    if os.environ.get("AUTOBET_MODE", "paper") != "paper":
        print("autobet: REFUSING -- only paper mode exists; no live order path is built")
        sys.exit(2)

    state = load_state()
    now = _now()
    hl = highlights()
    hs = hl.get("highlights") or []

    # both sides of one match highlighted -> neither is bet
    by_match = {}
    for h in hs:
        by_match.setdefault(_match_key(h), []).append(h)
    conflicts = {k for k, v in by_match.items() if len(v) > 1}

    today = now.strftime("%Y-%m-%d")
    staked_today = sum(b.get("cost", 0) for b in state["bets"].values()
                       if b.get("status") == "filled" and str(b.get("placed_at", ""))[:10] == today)

    events = None
    acted = []
    for h in hs:
        k = _key(h)
        b = state["bets"].get(k)
        if b and b.get("status") in ("filled", "conflict", "missed", "no_market", "ambiguous"):
            continue                                  # final states are never revisited
        st = _ts(h.get("start"))
        if not st:
            continue
        mins = (st - now).total_seconds() / 60
        rec = b or {"date": h["date"], "pick": h["pick"], "opp": h["opp"], "kind": h["kind"],
                    "tag": h["tag"], "league": h["league"], "start": h["start"],
                    "board_odds": h["odds"], "mc6_ev": h.get("mc6_ev"), "cells": h.get("cells"),
                    "first_seen": now.isoformat(), "attempts": 0}
        if mins <= 0:
            if b:                                     # window passed without a fill
                rec["status"] = rec.get("last_reason") or "missed"
                if rec["status"] not in ("no_market", "ambiguous"):
                    rec["status"] = "missed"
                state["bets"][k] = rec
            continue
        if mins > window:
            continue
        if _match_key(h) in conflicts:
            rec["status"] = "conflict"
            state["bets"][k] = rec
            acted.append((k, "conflict"))
            continue
        if staked_today + STAKE > MAX_DAY + 1e-9:
            rec["status"] = "waiting"
            rec["last_reason"] = "daily_cap"
            state["bets"][k] = rec
            continue
        if events is None:
            events = P._fetch_events(False)
        hit, why = find_market(h, events)
        rec["attempts"] = rec.get("attempts", 0) + 1
        if not hit:
            rec.update(status="waiting", last_reason=why)
            state["bets"][k] = rec
            acted.append((k, why))
            continue
        ev, m, idx = hit
        if m.get("acceptingOrders") is False:
            rec.update(status="waiting", last_reason="not_accepting")
            state["bets"][k] = rec
            continue
        tokens = P._as_list(m.get("clobTokenIds"))
        fill = paper_fill(tokens[idx], _implied(h["odds"]))
        rec.update(pm_slug=ev.get("slug"), pm_outcome=P._as_list(m.get("outcomes"))[idx],
                   pm_token=tokens[idx], pm_taker_base_fee=m.get("takerBaseFee"),
                   last_book=fill, last_try=now.isoformat())
        if fill.get("filled"):
            rec.update(status="filled", placed_at=now.isoformat(), mins_before=round(mins, 1),
                       shares=fill["shares"], cost=fill["cost"], fee=fill["fee"],
                       avg_price=fill["avg_price"], avg_american=fill["avg_american"],
                       partial=fill["partial"])
            staked_today += fill["cost"]
            acted.append((k, "FILLED %.2f @ %.3f" % (fill["cost"], fill["avg_price"])))
        else:
            rec.update(status="waiting", last_reason="price")
            acted.append((k, "no fill: best ask %s > limit %s" % (fill["best_ask"], fill["limit"])))
        state["bets"][k] = rec

    n_set = settle(state)
    state["last_run"] = now.isoformat()
    state["last_highlights"] = len(hs)
    state["last_conflicts"] = len(conflicts)
    if not dry:
        save_state(state)
    if verbose:
        if dry:
            print("DRY RUN -- nothing saved (window %.0f min)" % window)
        print("autobet %s: %d highlights, %d conflicts, %d actions, %d settled"
              % (now.strftime("%H:%M"), len(hs), len(conflicts), len(acted), n_set))
        for k, what in acted:
            print("   %-70s %s" % (k.replace("|||", " | ")[:70], what))


def summary():
    """For /api/tennis/autobet: every paper bet plus the running record."""
    st = load_state()
    bets = sorted(st["bets"].values(), key=lambda b: str(b.get("start")), reverse=True)
    done = [b for b in bets if b.get("result") in ("won", "lost")]
    staked = sum(b["cost"] + b["fee"] for b in done)
    pnl = sum(b["pnl"] for b in done)
    return {
        "mode": "paper", "last_run": st.get("last_run"), "stake": STAKE, "max_day": MAX_DAY,
        "window_min": BET_WINDOW_MIN, "fee_rate": SPORTS_TAKER_RATE,
        "settled": len(done), "wins": sum(1 for b in done if b["result"] == "won"),
        "staked": round(staked, 2), "pnl": round(pnl, 2),
        "roi_pct": round(100 * pnl / staked, 2) if staked else None,
        "open": sum(1 for b in bets if b.get("status") == "filled" and "result" not in b),
        "counts": pd.Series([b.get("status") for b in bets]).value_counts().to_dict() if bets else {},
        "bets": bets[:300],
    }


if __name__ == "__main__":
    _dry = "--dry" in sys.argv
    _w = None
    if "--window" in sys.argv:
        _w = float(sys.argv[sys.argv.index("--window") + 1])
    run(dry=_dry, window_min=_w)
