"""PHASE 2 (2026-10-18): PRICE-VALIDITY GUARDS -- synthetic quotes and post-start captures.

Phase 1 found two classes of rows whose logged price was never an executable pre-match offer:
  * 156 SYNTHETIC prices: bookmaker 'Polymarket' fallback rows whose two American odds are a
    single probability mirrored (-147/+147), overround exactly 1.0000 -- a fair mark, not a quote.
  * 154 POST-START prices: logged_at at/after start_time_utc, caught by nothing because the only
    guard (inplay_suspect) needs an opening price AND >20pp drift.
Why ~120 synthetic rows reached lanes: the de-vig twin-merge policy only applies when a vigged
twin EXISTS; when Polymarket is the only source its de-vigged row is the only row, and no gate
ever looked at the overround or the bookmaker.

WHAT THIS PATCH DOES (data integrity only -- no model, weight, or threshold changes):
  1. BAD_ROW_FLAGS module constant: the one list every lane gate reads from now.
  2. _apply_price_flags(df): computes price_synthetic / price_poststart / price_reject_reason.
     Robust detection, not just overround==1:
       synthetic  <- mirrored pair (p1 == -p2) OR overround <= 1.0001 OR both odds positive
                     OR bookmaker exactly 'Polymarket' (the fallback; 'Polymarket (USA)' is the
                     real order-book feed and is NOT matched)
       poststart  <- logged_at >= start_time_utc, or either timestamp missing/unparseable
                     (pre-match eligibility cannot be established -> ineligible, per spec)
     Original timestamps are already immutable on the row; the reason string survives with them.
  3. Flags computed on every NEW row at insert (log_predictions), after the drift guard.
  4. Every lane gate extended: the bet() loop, the s52 and conflict passes, G/G2/MC2 blocks,
     the orange band, and get_tennis_track_record (which had NO flag filtering at all).
Rows are KEPT and flagged -- nothing is deleted, market-free analyses still see the outcomes.
"""
import io
import os

P = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tennis_log.py")
s = io.open(P, encoding="utf-8").read()
assert "BAD_ROW_FLAGS" not in s, "already patched"


def rep(old, new, c=1):
    global s
    assert s.count(old) == c, "found %d of %r" % (s.count(old), old[:100])
    s = s.replace(old, new)


# ------------------------------------------------- 1+2. constant + the flag function
ANCHOR = "def _started(start_time_utc) -> bool:"
HELPER = '''# PHASE 2 (2026-10-18): every flag that makes a row ineligible for BETTING lanes. One list so a
# new lane cannot forget one -- the history of this file is three gates each missing a different
# flag. Rows stay in the log and in market-free analyses; they just cannot be "bet".
BAD_ROW_FLAGS = ("surface_bad", "inplay_suspect", "resolve_bad",
                 "price_synthetic", "price_poststart")


def _row_flagged(r, flags=BAD_ROW_FLAGS):
    """True when any ineligibility flag is set on a row/dict-like."""
    for _f in flags:
        _v = r.get(_f)
        if _v is not None and not pd.isna(_v) and bool(_v):
            return True
    return False


def _apply_price_flags(df):
    """price_synthetic / price_poststart / price_reject_reason, from immutable row fields.

    SYNTHETIC: the price pair is a probability in costume, not an executable quote --
      mirrored American pair (p1 == -p2), or overround <= 1.0001 (no book offers a free arb),
      or both sides positive, or bookmaker exactly 'Polymarket' (the de-vigged fallback feed;
      'Polymarket (USA)' is the real order-book source and is NOT matched).
    POSTSTART: logged_at >= start_time_utc, or either timestamp missing -- if pre-match
      eligibility cannot be established the row is ineligible (Phase 2 spec).
    Deterministic in the row's frozen fields, so recomputing is always safe; persisted so the
    verdict survives every pipeline stage. Reasons concatenate when both fire.
    """
    if df.empty:
        return df
    o1 = pd.to_numeric(df.get("p1_odds"), errors="coerce")
    o2 = pd.to_numeric(df.get("p2_odds"), errors="coerce")
    dec1 = np.where(o1 > 0, 1.0 + o1 / 100.0, 1.0 + 100.0 / np.abs(o1))
    dec2 = np.where(o2 > 0, 1.0 + o2 / 100.0, 1.0 + 100.0 / np.abs(o2))
    with np.errstate(divide="ignore", invalid="ignore"):
        ovr = 1.0 / dec1 + 1.0 / dec2
    have = o1.notna() & o2.notna() & (o1 != 0) & (o2 != 0)
    mirrored = have & (o1 == -o2)
    both_pos = have & (o1 > 0) & (o2 > 0)
    low_ovr = have & pd.Series(ovr, index=df.index).le(1.0001)
    bm = df.get("bookmaker")
    pm_fallback = (bm.astype(str) == "Polymarket") if bm is not None else pd.Series(False, index=df.index)
    synth = mirrored | both_pos | low_ovr | pm_fallback

    st = pd.to_datetime(df.get("start_time_utc"), errors="coerce", utc=True)
    lg = pd.to_datetime(df.get("logged_at"), errors="coerce", utc=True)
    post = st.isna() | lg.isna() | (lg >= st)

    reason = pd.Series("", index=df.index, dtype=object)
    reason[mirrored] = reason[mirrored] + "mirrored_pair;"
    reason[low_ovr & ~mirrored] = reason[low_ovr & ~mirrored] + "overround_le_1;"
    reason[both_pos] = reason[both_pos] + "both_positive;"
    reason[pm_fallback & ~mirrored & ~low_ovr] = reason[pm_fallback & ~mirrored & ~low_ovr] + "pm_fallback_devig;"
    reason[post & (st.isna() | lg.isna())] = reason[post & (st.isna() | lg.isna())] + "timestamp_missing;"
    reason[post & st.notna() & lg.notna()] = reason[post & st.notna() & lg.notna()] + "logged_at_ge_start;"
    df["price_synthetic"] = synth.fillna(False).astype(bool)
    df["price_poststart"] = post.fillna(False).astype(bool)
    df["price_reject_reason"] = reason.replace("", None)
    return df


''' + ANCHOR
rep(ANCHOR, HELPER)

# ------------------------------------------------- 3. flags on every new row at insert
OLD_INS = '''    except Exception as _e:
        print(f"[tennis log] in-play guard skipped: {_e}")
        new["inplay_suspect"] = False'''
rep(OLD_INS, OLD_INS + '''
    # PHASE 2 price-validity flags on every incoming row (synthetic quote / post-start capture)
    try:
        new = _apply_price_flags(new)
    except Exception as _e:
        print(f"[tennis log] price flags skipped: {_e}")''')

# ------------------------------------------------- 4a. the bet() loop gate
OLD_RB = '''            _rb9 = r.get("resolve_bad")
            if _rb9 is not None and not pd.isna(_rb9) and bool(_rb9):
                continue'''
rep(OLD_RB, OLD_RB + '''
            # NON-EXECUTABLE PRICE (Phase 2, 2026-10-18): synthetic de-vigged quote, or a price
            # captured at/after the start. Row stays in the log; no lane may bet it.
            if _row_flagged(r, ("price_synthetic", "price_poststart")):
                continue''')

# ------------------------------------------------- 4b. tuple gates -> BAD_ROW_FLAGS
rep('for _bad in ("surface_bad", "inplay_suspect", "resolve_bad"):',
    "for _bad in BAD_ROW_FLAGS:", 3)
rep('for _c in ("surface_bad", "inplay_suspect"):', "for _c in BAD_ROW_FLAGS:", 1)

# ------------------------------------------------- 4c. the two surface_bad-only gates
OLD_S1 = '''            if "surface_bad" in _sq.columns:
                _sb = rr.get("surface_bad")
                if _sb is not None and not pd.isna(_sb) and bool(_sb):
                    continue'''
rep(OLD_S1, '''            if _row_flagged(rr):     # Phase 2: all ineligibility flags, not surface alone
                continue''')
OLD_S2 = '''            if "surface_bad" in _sq.columns:
                _sbx = rr.get("surface_bad")
                if _sbx is not None and not pd.isna(_sbx) and bool(_sbx):
                    continue'''
rep(OLD_S2, '''            if _row_flagged(rr):     # Phase 2: all ineligibility flags, not surface alone
                continue''')

# ------------------------------------------------- 4d. the legacy track record had NO flags
OLD_TR = '''    settled_all = log[(log["settled"] == True) & log["p1_won"].notna()]  # noqa: E712 -- tracker rows may lack a model p'''
rep(OLD_TR, OLD_TR + '''
    # Phase 2 (2026-10-18): this function claims flat-1u ROI at the logged odds but applied NO
    # ineligibility flags at all -- wrong surface, in-play, wrong player, synthetic and
    # post-start rows were all counted. Now gated like every other lane.
    for _bad in BAD_ROW_FLAGS:
        if _bad in settled_all.columns:
            settled_all = settled_all[~settled_all[_bad].fillna(False).astype(bool)]''')

io.open(P, "w", encoding="utf-8", newline="").write(s)
import py_compile
py_compile.compile(P, doraise=True)
print("tennis_log.py patched and compiles")
print("  BAD_ROW_FLAGS refs : %d" % s.count("BAD_ROW_FLAGS"))
print("  _row_flagged refs  : %d" % s.count("_row_flagged"))
print("  _apply_price_flags : %d" % s.count("_apply_price_flags"))
print("RESULT: OK")
