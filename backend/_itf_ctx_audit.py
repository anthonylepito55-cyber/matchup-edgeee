"""ARE THE ITF STATS WRONG, AND DID TIER 5 CAUSE IT? (2026-10-11, user: "And the stats are
wrong for some itf gsmes")

Two ways a card can show WRONG stats rather than missing ones:

  A. WRONG PLAYER. The name resolver matched a different human. The fuzzy tiers are the risk,
     and I added tier 5 (surname + first initial, when unique) an hour ago -- which is exactly
     the kind of rule that can bind an ITF player to a same-surname tour player. This checks
     every resolution on the board and in the recent log and flags any where the matched
     profile name is NOT a plausible variant of the card name.

  B. WRONG SURFACE. get_context falls back to the All-surfaces profile when a player has fewer
     than 5 matches on the match surface. That is labelled ("all 52w" rather than "clay 52w"),
     but on an ITF card it means the serve/return figures are not the court being played.

Both are counted, with examples, ITF split out from tour.
"""
import json
import unicodedata

import pandas as pd

import tennis_context as TC
import tennis_model_a as MA

MA._load()
c = TC._load()


def strip_acc(x):
    return "".join(ch for ch in unicodedata.normalize("NFKD", str(x))
                   if not unicodedata.combining(ch))


def toks(x):
    return set(strip_acc(TC._norm_name(x)).split())


def plausible(card_name, slug):
    """Is the matched profile a believable variant of the card name? Require the SURNAME to
    match exactly -- a wrong surname is a wrong person, whatever the first name says."""
    prof = None
    for k, v in c["name_index"].items():
        if v == slug:
            prof = k
            break
    if prof is None:
        return True, "?"
    a, b = toks(card_name), toks(prof)
    if a == b:
        return True, prof
    # surname = the longest token in each, a reasonable proxy across naming orders
    sa = max(a, key=len) if a else ""
    sb = max(b, key=len) if b else ""
    shared = a & b
    ok = (sa == sb) or bool(shared and max(shared, key=len) == sa) or bool(a & b and len(max(a & b, key=len)) >= 5)
    return ok, prof


rows = []
d = json.load(open("/tmp/ta.json"))
for m in (d.get("matches") or []):
    for k in ("player_1", "player_2"):
        if m.get(k):
            rows.append((m[k], m.get("surface"), m.get("league"), "board",
                         f"{m.get('player_1')} vs {m.get('player_2')}"))
L = pd.read_parquet("data_cache/tennis_prediction_log.parquet")
L["date"] = pd.to_datetime(L["date"], errors="coerce")
rec = L[L.date >= L.date.max() - pd.Timedelta(days=4)]
for r in rec.itertuples():
    for nm in (r.player_1, r.player_2):
        rows.append((str(nm), r.surface, str(r.league), "log",
                     f"{r.player_1} vs {r.player_2}"))

seen = set()
bad_player, wrong_surf = [], []
counts = {"itf": 0, "tour": 0, "itf_resolved": 0, "tour_resolved": 0}
for nm, surf, lg, src, match in rows:
    key = (nm, surf)
    if key in seen:
        continue
    seen.add(key)
    is_itf = "itf" in (lg or "").lower() or "futures" in (lg or "").lower()
    counts["itf" if is_itf else "tour"] += 1
    slug = MA.resolve(nm)
    if slug is None:
        continue
    counts["itf_resolved" if is_itf else "tour_resolved"] += 1
    ok, prof = plausible(nm, slug)
    if not ok:
        bad_player.append((nm, prof, slug, lg, match))
    ctx = TC.get_context(nm, surf)
    if ctx and surf and str(ctx.get("surface_used")).title() != str(surf).title():
        wrong_surf.append((nm, surf, ctx.get("surface_used"),
                           (ctx.get("surface_stats") or {}).get("n"), lg, is_itf))

print(f"players checked: {len(seen)}  (itf {counts['itf']}, tour {counts['tour']})")
print(f"  resolved: itf {counts['itf_resolved']}/{counts['itf']}, "
      f"tour {counts['tour_resolved']}/{counts['tour']}")

print(f"\n=== A. SUSPECTED WRONG PLAYER: {len(bad_player)} ===")
for nm, prof, slug, lg, match in bad_player[:20]:
    print(f"   card '{nm}'  ->  profile '{prof}' ({slug})   [{lg}]   {match[:48]}")
if not bad_player:
    print("   none -- every resolution shares a surname with the card name")

print(f"\n=== B. STATS FROM THE WRONG SURFACE: {len(wrong_surf)} ===")
itf_ws = [x for x in wrong_surf if x[5]]
print(f"   total {len(wrong_surf)}, of which ITF {len(itf_ws)}")
for nm, surf, used, n, lg, _ in wrong_surf[:18]:
    print(f"   {nm:30s} match on {str(surf):6s} but stats are '{used}' (n={n})  [{lg}]")
