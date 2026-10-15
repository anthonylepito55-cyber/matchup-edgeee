"""ONE ITF CARD PER MATCH (2026-10-15).

User: "fix that", on the duplicate I flagged -- Jodie Burrage vs Manon Leonard appearing twice
under different name forms, both marked, both logging.

MEASURED: 6 duplicate groups in 210 ITF cards, and every one is the same shape -- a TennisExplorer
fixture (hex id) paired with a Polymarket twin (pm_itf-...):

    fid 202610151943A2CB  Mingge Xu vs Cadence Brace     None/None   impl_sum None   mc2 YES
    fid pm_itf-xu6-brace1 Mimi Xu   vs Cadence Brace      111/-111   impl_sum 1.0    mc2 no

    fid 20261015EADE212C  Aditya Vishal Balsekar ...     1085/-1413  impl_sum 1.0183 mc2 no
    fid pm_itf-balsek1... Aditya Balsekar ...            1233/-1233  impl_sum 1.0    mc2 no

Two things follow from that table, and they pull in opposite directions:

  * The PM twin usually carries the only PRICE, and every PM twin's two implied probabilities sum
    to exactly 1.0 -- it is DE-VIGGED. The standing rule from the duplicate-row repair of
    2026-10-13 is to keep the VIGGED row, because a de-vigged price credits a lane the bookmaker's
    margin it never actually got.
  * The TE row usually carries the resolved MODEL HEADS, because the fuller name form
    ("Mingge Xu") resolves in TennisRatio where the short form ("Mimi Xu") does not.

So dropping either row loses something real. A plain drop is why this keeps coming back. These are
MERGED into one card instead:

    identity   the TE (non-pm_) card is the base when present -- its id is what the ITF settler's
               name+date matching was built around (2026-10-10)
    price      a genuinely VIGGED price wins (implied sum > 1.005). A de-vigged PM price is used
               only when it is the only price there is, and then it is tagged devigged_price so
               nothing downstream can mistake it for a book line
    heads      any model head, tr_context or gs missing on the base is filled from the twin, so
               the resolved-name side's work is not thrown away

Matching is on surname + first initial per player, plus the date, which is what catches
"Jodie Burrage" / "Jodie Anna Burrage" and "Mingge Xu" / "Mimi Xu". That is the same key shape the
log's _pair_key fallback settled on in the 2026-10-13 repair.

Placed BEFORE log_predictions, so the ledger gets one row per match rather than two -- which was
the actual damage: two rows for one match double-count it in every lane.
"""
import io
import os

P = os.path.join(os.path.dirname(os.path.abspath(__file__)), "main.py")
s = io.open(P, encoding="utf-8").read()
assert "_itf_dedupe_cards" not in s, "already patched"

ANCHOR = """    # LOG ITF TO THE LEDGER (2026-10-08): ITF cards were never logged (only mislabeled"""
assert s.count(ANCHOR) == 1, "anchor not found"

NEW = '''    # ONE CARD PER MATCH (2026-10-15, user "fix that"). The ITF slate carries the same match
    # twice when TennisExplorer and Polymarket name a player differently -- 6 groups in 210 cards,
    # always a hex TE fixture beside a pm_itf- twin. Both were marked and both were LOGGED, which
    # double-counts the match in every lane. See _patch_itf_dedupe.go.py for the measurements.
    cards = _itf_dedupe_cards(cards)

''' + ANCHOR
s = s.replace(ANCHOR, NEW)

# the helper, placed just above the ITF endpoint's function; find a safe module-level insert point
HELPER = '''

def _itf_pair_key(card: dict):
    """(sorted surname+first-initial per player, date) -- the key that catches differing name
    forms for one match: "Jodie Burrage"/"Jodie Anna Burrage", "Mingge Xu"/"Mimi Xu". Same shape
    as the log's _pair_key surname+initial fallback (2026-10-13 duplicate-row repair)."""
    import re as _re

    def one(n):
        toks = [t for t in _re.split(r"[^A-Za-z]+", str(n or "").lower()) if t]
        if not toks:
            return ""
        return toks[-1] + "|" + toks[0][:1]

    names = tuple(sorted([one(card.get("player_1")), one(card.get("player_2"))]))
    return names + (str(card.get("start_time_utc") or "")[:10],)


def _itf_implied_sum(card: dict):
    """Sum of the two sides' implied probabilities, or None. ~1.0 means the price has been
    DE-VIGGED (every Polymarket twin measured exactly 1.0); >1 is a real book line with margin."""
    lo = card.get("live_odds") or {}
    try:
        o1, o2 = float(lo["player_1"]), float(lo["player_2"])
    except (KeyError, TypeError, ValueError):
        return None

    def dec(o):
        return 1 + o / 100.0 if o > 0 else 1 + 100.0 / abs(o)

    return 1 / dec(o1) + 1 / dec(o2)


# the fields worth rescuing from a twin: model heads and the stat context, which the
# resolved-name side of a duplicate often has and the other does not
_ITF_MERGE_FIELDS = ("mc2", "mc3", "mc5", "model_a", "model_b", "model_c", "model_d",
                     "model_g", "model_g2", "model_i", "model_x", "model_p",
                     "tr_context", "gs")


def _itf_dedupe_cards(cards: list) -> list:
    """Collapse same-match duplicates into one card. The TE (non-pm_) card is the base when
    present -- its id is what the ITF settler's name+date matching was built around. A genuinely
    vigged price beats a de-vigged one; a de-vigged price is used only when it is the only price
    and is then tagged devigged_price. Missing heads are filled from the twin."""
    groups = {}
    order = []
    for c in cards:
        k = _itf_pair_key(c)
        if k not in groups:
            groups[k] = []
            order.append(k)
        groups[k].append(c)
    out = []
    merged = 0
    for k in order:
        grp = groups[k]
        if len(grp) == 1:
            out.append(grp[0])
            continue
        merged += 1
        # base: prefer a canonical (non-Polymarket) fixture id
        base = next((c for c in grp if not str(c.get("fixture_id") or "").startswith("pm_")), grp[0])
        twins = [c for c in grp if c is not base]
        card = dict(base)
        # PRICE: a vigged line wins outright; otherwise take any price, flagging a de-vigged one
        best, best_rank = None, -1.0
        for c in grp:
            isum = _itf_implied_sum(c)
            if isum is None:
                continue
            rank = 2.0 + isum if isum > 1.005 else 1.0
            if rank > best_rank:
                best, best_rank = c, rank
        if best is not None:
            card["live_odds"] = best.get("live_odds")
            isum = _itf_implied_sum(best)
            if isum is not None and isum <= 1.005:
                # no bookmaker margin in it -- a de-vigged twin's price, kept only because it is
                # the only one. Flagged so a lane crediting it cannot be mistaken for a book line.
                card["devigged_price"] = True
        # HEADS: fill anything the base lacks from a twin (the fuller name form often resolves
        # in TennisRatio where the short one does not, e.g. "Mingge Xu" vs "Mimi Xu")
        for f in _ITF_MERGE_FIELDS:
            if card.get(f) is None:
                for t in twins:
                    if t.get(f) is not None:
                        card[f] = t[f]
                        break
        card["dupe_merged_from"] = [str(c.get("fixture_id")) for c in twins]
        out.append(card)
    if merged:
        print(f"[tennis itf] merged {merged} duplicate fixture group(s) -> one card each")
    return out

'''

MARK = "\n@app.get(\"/api/tennis/itf\")"
if MARK in s:
    s = s.replace(MARK, HELPER + MARK, 1)
else:
    # fall back: insert before the ITF endpoint's def
    import re
    m = re.search(r"\ndef tennis_itf\(", s)
    assert m, "could not find the ITF endpoint to anchor the helper"
    s = s[:m.start()] + HELPER + s[m.start():]

io.open(P, "w", encoding="utf-8", newline="").write(s)
print("patched main.py")
for k in ("_itf_dedupe_cards", "_itf_pair_key", "_itf_implied_sum", "devigged_price"):
    print("   %-22s %d" % (k, s.count(k)))
import py_compile
py_compile.compile(P, doraise=True)
print("compiles: OK")
print("RESULT: OK")
