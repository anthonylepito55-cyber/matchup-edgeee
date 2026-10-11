"""OPTICODDS SNAPSHOT FEED (2026-10-11, user: "start").

Builds the one asset the API will not sell us. `/fixtures/odds/historical` is 403 on this plan,
so there is no way to see where a line HAS BEEN -- which is what steam detection and CLV both
need. The fix is to poll `/fixtures/odds` on a schedule and keep every quote. History therefore
starts the moment this runs for the first time and compounds daily.

What each quote carries, verified against the live payload before this was written:
  price        American odds
  timestamp    per-QUOTE epoch seconds, not per-poll -- so a book that has not moved keeps its
               old timestamp and staleness is directly measurable
  limits.max   the venue's max stake
  order_book   FULL depth ladder [[price, size], ...] for Kalshi / Polymarket / Novig
               (Pinnacle returns null -- it has no exchange book, only limits.max)
  deep_link    straight to the market, with the Kalshi marketTicker / Polymarket marketSlug

Depth is the reason this module stores the whole ladder rather than just the top price: a gap
you cannot get filled at is not an edge, and a scanner that ignores size will always look
profitable. See `oo_scan.py`, which spends that depth.

Hard API limits, measured: **max 5 sportsbooks and max 5 fixture_ids per call**, 8,000 requests
per window. So one snapshot of a league costs ceil(fixtures/5) calls per book-group. Keeping two
book-groups (sharp, exchange) of <=5 each means 2 calls per 5 fixtures.

Read-only. Places no orders and moves no money.
"""
from __future__ import annotations

import json
import math
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

import pandas as pd

BASE = "https://api.opticodds.com/api/v3"
HERE = os.path.dirname(os.path.abspath(__file__))
SNAP_DIR = os.path.join(HERE, "data_cache", "oo_snapshots")

# Two groups of <=5, because the API caps sportsbooks at 5 per call. The sharp group defines
# fair value; the exchange group is where the user can actually act (Kalshi / Polymarket).
# BookMaker and Circa priced 0/3 and 1/3 of NBA fixtures when probed, so the sharp group leans
# on Pinnacle and BetOnline and keeps Circa as a third opinion rather than a dependency.
SHARP_BOOKS = ["Pinnacle", "BetOnline", "Circa Sports"]
EXCH_BOOKS = ["Kalshi", "Polymarket", "Novig", "Betfair Exchange"]
RETAIL_BOOKS = ["FanDuel", "DraftKings", "bet365"]

# US majors plus the long tail that the 2026-10-11 coverage sweep found has BOTH a sharp price
# and a Kalshi/Polymarket price. The tail is where the positive quotes actually are (LoL 25% of
# in-band quotes positive, challenger 7%) even though its MEAN is worse -- so this is where
# history is worth accruing. Cost is irrelevant: the 8,000 cap resets per minute.
DEFAULT_LEAGUES = ["nba", "nfl", "nhl", "ncaaf", "mlb",
                   "atp", "atp_challenger", "itf_men",
                   "cs2", "league_of_legends", "mobile_legends_bang_bang",
                   "afc_-_champions_league"]
MAX_BOOKS = 5
MAX_FIXTURES = 5


def load_key() -> str | None:
    k = os.environ.get("OPTICODDS_API_KEY")
    if k:
        return k.strip()
    p = os.path.join(HERE, ".env")
    if os.path.exists(p):
        with open(p, encoding="utf-8", errors="replace") as fh:
            for ln in fh:
                if ln.strip().startswith("OPTICODDS_API_KEY") and "=" in ln:
                    return ln.split("=", 1)[1].strip().strip('"').strip("'")
    return None


class Feed:
    def __init__(self, key: str | None = None, verbose: bool = True):
        self.key = key or load_key()
        if not self.key:
            raise RuntimeError("no OPTICODDS_API_KEY (env or backend/.env)")
        self.verbose = verbose
        self.calls = 0
        self.remaining = None

    def get(self, path: str, params: dict | None = None, tries: int = 3):
        q = ("?" + urllib.parse.urlencode(params, doseq=True)) if params else ""
        req = urllib.request.Request(
            BASE + path + q, headers={"X-Api-Key": self.key, "Accept": "application/json"})
        last = None
        for attempt in range(tries):
            try:
                with urllib.request.urlopen(req, timeout=90) as r:
                    self.calls += 1
                    rem = r.headers.get("x-ratelimit-remaining")
                    if rem is not None:
                        try:
                            self.remaining = int(rem)
                        except ValueError:
                            pass
                    return json.loads(r.read().decode("utf-8", "replace")), None
            except urllib.error.HTTPError as e:
                body = e.read().decode("utf-8", "replace")[:200]
                last = "HTTP %s %s" % (e.code, body)
                # 400 is our own bad request (batch too big) -- retrying cannot help
                if e.code == 400:
                    return None, last
                time.sleep(1.5 * (attempt + 1))
            except Exception as e:                       # network blips
                last = "%s: %s" % (type(e).__name__, str(e)[:160])
                time.sleep(1.5 * (attempt + 1))
        return None, last

    # ---------------------------------------------------------------- fixtures
    def active_fixtures(self, league: str, within_hours: float | None = 48) -> list[dict]:
        """Open fixtures for a league, optionally only those starting soon.

        The window matters for cost and for relevance: /fixtures/active returns 100 NFL
        fixtures including games weeks away, whose prices barely move and which would dominate
        the call budget. It also EXCLUDES live games -- a price mid-game is a different animal
        and would pollute a pre-match CLV benchmark.
        """
        d, err = self.get("/fixtures/active", {"league": league})
        if err:
            if self.verbose:
                print("   [%s] fixtures failed: %s" % (league, err))
            return []
        out = []
        now = datetime.now(timezone.utc)
        for f in (d.get("data") or []):
            if not f.get("id") or f.get("is_live"):
                continue
            if str(f.get("status") or "unplayed") != "unplayed":
                continue
            sd = f.get("start_date")
            if within_hours is not None and sd:
                try:
                    st = pd.Timestamp(sd).tz_convert("UTC").to_pydatetime()
                    if st < now - timedelta(minutes=5) or st > now + timedelta(hours=within_hours):
                        continue
                except Exception:
                    pass
            out.append(f)
        return out

    # ------------------------------------------------------------------- odds
    def odds(self, fixtures: list[dict], books: list[str], market: str = "moneyline"):
        """Quotes for these fixtures from these books, batched to the API's 5x5 ceiling."""
        rows = []
        meta = {f["id"]: f for f in fixtures}
        for bi in range(0, len(books), MAX_BOOKS):
            bgroup = books[bi:bi + MAX_BOOKS]
            ids = [f["id"] for f in fixtures]
            for fi in range(0, len(ids), MAX_FIXTURES):
                batch = ids[fi:fi + MAX_FIXTURES]
                d, err = self.get("/fixtures/odds",
                                  {"fixture_id": batch, "sportsbook": bgroup, "market": market})
                if err:
                    if self.verbose:
                        print("   odds batch failed (%d fx x %d books): %s"
                              % (len(batch), len(bgroup), err))
                    continue
                for fx in (d.get("data") or []):
                    f = meta.get(fx.get("id")) or fx
                    # league arrives as a plain id on some sports and as a nested object on
                    # others. Flatten it here: an unhashable dict in this column silently
                    # breaks every later groupby("league").
                    lg = fx.get("league") or f.get("league")
                    if isinstance(lg, dict):
                        lg = lg.get("id") or lg.get("name")
                    for o in (fx.get("odds") or []):
                        if o.get("price") is None:
                            continue
                        ob = o.get("order_book")
                        lim = (o.get("limits") or {}).get("max")
                        rows.append({
                            "fixture_id": fx.get("id"),
                            "league": lg,
                            "start_date": f.get("start_date") or fx.get("start_date"),
                            "home": fx.get("home_team_display") or f.get("home_team_display"),
                            "away": fx.get("away_team_display") or f.get("away_team_display"),
                            "sportsbook": o.get("sportsbook"),
                            "selection": o.get("selection"),
                            "norm_selection": o.get("normalized_selection"),
                            "market": o.get("market_id") or market,
                            "price": o.get("price"),
                            "limit_max": lim,
                            # top-of-book size: the exchanges give a ladder, the books give
                            # only limits.max -- keep both and let the scanner decide
                            "top_size": (float(ob[0][1]) if (ob and ob[0] and len(ob[0]) > 1)
                                         else (float(lim) if lim is not None else None)),
                            "order_book": json.dumps(ob) if ob else None,
                            "quote_ts": o.get("timestamp"),
                            "deep_link": ((o.get("deep_link") or {}).get("desktop")
                                          if isinstance(o.get("deep_link"), dict) else None),
                        })
        return rows


def snapshot(leagues: list[str] | None = None, within_hours: float | None = 48,
             books: list[str] | None = None, market: str = "moneyline",
             store: bool = True, verbose: bool = True) -> pd.DataFrame:
    """One pass over the configured leagues; returns the rows and appends them to today's file."""
    feed = Feed(verbose=verbose)
    leagues = leagues or DEFAULT_LEAGUES
    books = books or (SHARP_BOOKS + EXCH_BOOKS)
    poll_ts = time.time()
    allrows = []
    for lg in leagues:
        fx = feed.active_fixtures(lg, within_hours=within_hours)
        if not fx:
            if verbose:
                print("   [%s] no fixtures in the next %sh" % (lg, within_hours))
            continue
        rows = feed.odds(fx, books, market=market)
        if verbose:
            print("   [%s] %d fixtures -> %d quotes" % (lg, len(fx), len(rows)))
        allrows.extend(rows)
    df = pd.DataFrame(allrows)
    if df.empty:
        if verbose:
            print("   snapshot empty")
        return df
    df["poll_ts"] = poll_ts
    if store:
        os.makedirs(SNAP_DIR, exist_ok=True)
        day = datetime.fromtimestamp(poll_ts, timezone.utc).strftime("%Y-%m-%d")
        path = os.path.join(SNAP_DIR, "%s.parquet" % day)
        before = len(df)
        if os.path.exists(path):
            try:
                old = pd.read_parquet(path)
                df = pd.concat([old, df], ignore_index=True)
            except Exception as e:                       # never lose a poll to a bad file
                print("   WARN could not read %s (%s); writing fresh" % (path, e))
        # DEDUPE ON quote_ts, which is what makes a fast poll cheap to store.
        # Each quote carries the venue's OWN timestamp, and a book that has not moved returns
        # the same one poll after poll. So one row per (fixture, book, selection, quote_ts) is
        # exactly one row per actual PRICE CHANGE -- the thing steam detection needs -- instead
        # of one row per poll. Polling every minute then costs almost nothing on disk.
        # keep="last" so the stored row carries the freshest depth ladder for that quote.
        key = ["fixture_id", "sportsbook", "selection", "quote_ts"]
        if all(k in df.columns for k in key):
            n0 = len(df)
            df = df.drop_duplicates(subset=key, keep="last").reset_index(drop=True)
            dropped = n0 - len(df)
        else:
            dropped = 0
        df.to_parquet(path, index=False)
        if verbose:
            print("   stored -> %s (+%d new, %d unchanged dropped, %d rows total, "
                  "%d API calls, %s remaining)"
                  % (os.path.basename(path), before, dropped, len(df),
                     feed.calls, feed.remaining))
    return df


# ------------------------------------------------------------------ odds maths
def am_to_dec(a) -> float | None:
    """American odds -> decimal."""
    try:
        a = float(a)
    except (TypeError, ValueError):
        return None
    if a == 0:
        return None
    return 1.0 + a / 100.0 if a > 0 else 1.0 + 100.0 / abs(a)


def am_to_prob(a) -> float | None:
    d = am_to_dec(a)
    return None if not d else 1.0 / d


def devig_two_way(p_a, p_b) -> float | None:
    """Fair probability of A from a two-way market, by normalising the implied probabilities.

    Simple multiplicative de-vig. It is the method already used elsewhere in this codebase, and
    on a two-way market with a tight sharp spread the difference against power/Shin methods is
    well under a tenth of a point -- far below the noise this scanner is hunting.
    """
    ia, ib = am_to_prob(p_a), am_to_prob(p_b)
    if ia is None or ib is None:
        return None
    tot = ia + ib
    if tot <= 0:
        return None
    return ia / tot


def kalshi_fee_pp(prob: float) -> float:
    """Kalshi's trading fee, expressed in PROBABILITY POINTS of effective price.

    Kalshi charges 0.07 x contracts x P x (1 - P). Buying at price P therefore really costs
    P + 0.07 P (1-P), so in probability points the fee is 7 x P x (1-P): **1.75pt at even
    money**, 0.6pt at 90c. That is large relative to the edges this scanner looks for, which is
    exactly why it is netted off rather than mentioned in a footnote.
    """
    if prob is None or not (0 < prob < 1):
        return 0.0
    return 7.0 * prob * (1.0 - prob)


FEE_PP = {
    "Kalshi": kalshi_fee_pp,
    # Polymarket takes no trading fee today (gas only, and usually relayed). Novig is
    # commission-free on its exchange. Betfair commission applies to NET WINNINGS, not stake,
    # so it cannot be expressed as a price haircut -- flagged in the scanner instead.
    "Polymarket": lambda p: 0.0,
    "Polymarket (USA)": lambda p: 0.0,
    "Novig": lambda p: 0.0,
}


def takeable_size(order_book_json: str | None, target_price, top_size=None) -> float | None:
    """How much size is available AT target_price or better.

    This is the whole defence against the phantom-fill trap. For an exchange the ladder is
    [[price, size], ...] best-first; levels at least as good as the target are summed. "At least
    as good" has to be computed on probability, not on the American number, because American
    odds are discontinuous across zero (+100 and -100 are both 50%).
    """
    if not order_book_json:
        return float(top_size) if top_size is not None else None
    try:
        book = json.loads(order_book_json)
    except Exception:
        return float(top_size) if top_size is not None else None
    tp = am_to_prob(target_price)
    if tp is None:
        return None
    tot = 0.0
    for lvl in (book or []):
        if not lvl or len(lvl) < 2:
            continue
        lp = am_to_prob(lvl[0])
        if lp is None:
            continue
        # cheaper (lower implied probability) = better for a buyer
        if lp <= tp + 1e-12:
            try:
                tot += float(lvl[1])
            except (TypeError, ValueError):
                continue
    return tot if tot > 0 else None


def load_snapshots(days: int = 7) -> pd.DataFrame:
    """Every stored snapshot from the last `days` files."""
    if not os.path.isdir(SNAP_DIR):
        return pd.DataFrame()
    files = sorted(f for f in os.listdir(SNAP_DIR) if f.endswith(".parquet"))[-days:]
    frames = []
    for f in files:
        try:
            frames.append(pd.read_parquet(os.path.join(SNAP_DIR, f)))
        except Exception as e:
            print("   WARN skipping %s: %s" % (f, e))
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


if __name__ == "__main__":
    import sys
    lgs = sys.argv[1].split(",") if len(sys.argv) > 1 else None
    hrs = float(sys.argv[2]) if len(sys.argv) > 2 else 48
    print("snapshot: leagues=%s within=%sh" % (lgs or DEFAULT_LEAGUES, hrs))
    t0 = time.time()
    df = snapshot(leagues=lgs, within_hours=hrs)
    if not df.empty:
        print("   books present: %s"
              % ", ".join("%s=%d" % (k, v)
                          for k, v in df.sportsbook.value_counts().items()))
        print("   with a depth ladder: %d of %d quotes"
              % (int(df.order_book.notna().sum()), len(df)))
    print("   took %.1fs" % (time.time() - t0))
