"""WHICH CARDS HAVE A BROKEN L5 LINE, AND WHY? (2026-10-11, user: "Some games the l5 stats
aren't working").

Three candidate causes, counted separately rather than guessed at:
  A. the player does not resolve at all          -> no context, no lines at all
  B. fewer than 3 matches on that surface        -> the L5 block is skipped by design
  C. the 5 matches exist but carry NO STAT LINE  -> the block is present and the win rate
     shows, but every serve/return field is null, so the line reads "L5: win 80%" alone
Cause C is the TennisRatio stat-line lag (37-55% on the freshest three days), so it should bite
the SHORTEST window hardest -- L5 harder than L10, and both harder than the 52-week figure.
"""
import json

import tennis_context as TC
import tennis_model_a as MA

MA._load()
STATS = ("sv1", "sv2", "sgw", "r1", "r2", "rgw")
d = json.load(open("/tmp/ta.json"))
ms = d.get("matches") or []
players = []
for m in ms:
    for k in ("player_1", "player_2"):
        if m.get(k):
            players.append((m[k], m.get("surface"), m.get("tournament"), m.get("league")))
seen, rows = set(), []
for nm, surf, tour, lg in players:
    if nm in seen:
        continue
    seen.add(nm)
    rows.append((nm, surf, tour, lg))
print(f"unique board players: {len(rows)}")

unresolved = thin = []
cnt = {"no_resolve": 0, "no_ctx": 0, "no_l5_block": 0, "l5_all_null": 0,
       "l5_partial": 0, "l5_full": 0, "l10_all_null": 0, "l10_full": 0}
examples = {"no_l5_block": [], "l5_all_null": [], "l5_partial": []}
for nm, surf, tour, lg in rows:
    if MA.resolve(nm) is None:
        cnt["no_resolve"] += 1
        continue
    ctx = TC.get_context(nm, surf)
    if not ctx or not ctx.get("surface_stats"):
        cnt["no_ctx"] += 1
        continue
    s = ctx["surface_stats"]
    q10, q5 = s.get("l10"), s.get("l5")
    if q10:
        nn = sum(1 for k in STATS if q10.get(k) is not None)
        cnt["l10_all_null" if nn == 0 else "l10_full"] += 1
    if not q5:
        cnt["no_l5_block"] += 1
        if len(examples["no_l5_block"]) < 6:
            examples["no_l5_block"].append(f"{nm} ({ctx.get('surface_used')}, 52w n={s.get('n')})")
        continue
    nn = sum(1 for k in STATS if q5.get(k) is not None)
    if nn == 0:
        cnt["l5_all_null"] += 1
        if len(examples["l5_all_null"]) < 8:
            examples["l5_all_null"].append(
                f"{nm} ({ctx.get('surface_used')} L{q5['n']}, win {q5['win']}, since {q5.get('from')})")
    elif nn < len(STATS):
        cnt["l5_partial"] += 1
        if len(examples["l5_partial"]) < 6:
            examples["l5_partial"].append(f"{nm}: {nn}/6 stats")
    else:
        cnt["l5_full"] += 1

print("\nCOUNTS")
for k, v in cnt.items():
    print(f"   {k:16s} {v}")
tot = cnt["l5_full"] + cnt["l5_partial"] + cnt["l5_all_null"] + cnt["no_l5_block"]
if tot:
    broken = cnt["l5_all_null"] + cnt["no_l5_block"]
    print(f"\n   L5 line unusable for {broken} of {tot} players with context "
          f"({100 * broken / tot:.1f}%)")
for k, ex in examples.items():
    if ex:
        print(f"\n   {k}:")
        for e in ex:
            print(f"      {e}")

print("\nWOULD 'LAST 5 WITH A STAT LINE' FIX IT?")
c = TC._load()
fixable = 0
checked = 0
for nm, surf, tour, lg in rows:
    slug = c["name_index"].get(TC._norm_name(nm)) if c else None
    if not slug:
        continue
    g = (c.get("groups") or {}).get(slug)
    if g is None:
        continue
    checked += 1
    sub = g if not surf else g[g["surface"].astype(str).str.title() == str(surf).title()]
    if sub.empty:
        continue
    withstat = sub[sub["sg_all"].notna()]
    if len(sub.tail(5)[sub.tail(5)["sg_all"].notna()]) == 0 and len(withstat) >= 3:
        fixable += 1
print(f"   players whose last-5 has no stats but who DO have 3+ charted matches on the"
      f" surface: {fixable}  (of {checked} checked)")
print("   -> that is the population a 'last 5 CHARTED' window would recover")
