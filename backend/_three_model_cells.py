"""MC2 vs G vs G2 in the SAME two cells, on the SAME rows (2026-10-13, user: "And what's the live
roi of g and g2 for those things").

The honest obstacle: MC2 has been frozen on cards since 2026-10-08 and has 343 settled forward
rows. G went live at 22:00Z on 10-12 and G2 at 01:00Z on 10-13, so in these cells their FORWARD
samples are 1 settle and 0. There is no like-for-like forward comparison to be had yet.

So two tables:

  TABLE 1 -- the forward lanes exactly as they stand. Nearly empty for G and G2, and reported
             that way rather than padded.
  TABLE 2 -- all three scored on the IDENTICAL row set MC2's forward number came from, which
             means G and G2 are read off their walk-forward BACKFILL on those games while MC2 is
             read off genuinely frozen picks. That asymmetry is the whole caveat: a backfill was
             scored by a model trained only on earlier seasons and never saw the result, but it
             also never had to survive a live slate. It is the fairest available comparison, not
             an equal one.

Both favourite thresholds are shown for every model, because G's cell takes any margin and G2's
needs 4 points, so one column each would be comparing different rules.
"""
import numpy as np
import pandas as pd

import tennis_log

L = pd.read_parquet(tennis_log.LOG_PATH)
HEADS = [("mc2", "mc2_p1", "mc2_recon"),
         ("G", "model_g_p1", "model_g_recon"),
         ("G2", "model_g2_p1", "model_g2_recon")]

print("=" * 92)
print("TABLE 1 -- the FORWARD lanes as they stand (frozen live picks only)")
print("=" * 92)
st = tennis_log.get_ab25_record()["study"]
for k, lab in (("g_dog_flip", "G dog-flip"), ("g_fav_over", "G fav-over (any margin)"),
               ("g2_dog_flip", "G2 dog-flip"), ("g2_fav_over", "G2 fav-over (4pt+)")):
    v = st.get(k) or {}
    n = v.get("n") or 0
    roi = v.get("roi_pct")
    print("   %-26s n=%-4d pending=%-4s %s"
          % (lab, n, v.get("pending"),
             ("roi %+.2f%%" % roi) if (n and roi is not None) else "nothing settled yet"))
print("   %-26s see table 2 -- mc2 has no such lane, it is scored ad hoc below" % "mc2 cells")

# ---- the common row set: settled, priced, with ALL THREE heads present, clean flags ----
d = L[(L["settled"] == True) & L["p1_won"].notna()                      # noqa: E712
      & L["p1_odds"].notna() & L["p2_odds"].notna()].copy()
for _, col, _r in HEADS:
    d = d[d[col].notna()]
for c in ("surface_bad", "inplay_suspect"):
    if c in d.columns:
        d = d[~d[c].fillna(False).astype(bool)]
print("\ncommon settled rows carrying mc2 + G + G2: %d  (%s .. %s)"
      % (len(d), str(d["date"].min())[:10], str(d["date"].max())[:10]))
if not len(d):
    raise SystemExit("no overlap yet")

# MC2's forward number came from its NON-recon rows; restrict to those so table 2 is the same
# population the user was just quoted
if "mc2_recon" in d.columns:
    d = d[~d["mc2_recon"].fillna(False).astype(bool)]
print("of those, rows where mc2 was a genuine frozen pick: %d" % len(d))


def dec(a):
    a = float(a)
    return 1 + a / 100 if a > 0 else 1 + 100 / abs(a)


d1, d2 = d["p1_odds"].map(dec), d["p2_odds"].map(dec)
mk = (1 / d1) / ((1 / d1) + (1 / d2))
fav1 = mk >= 0.5
mkfav = np.where(fav1, mk, 1 - mk)
favodd = np.where(fav1, d1, d2)
dogodd = np.where(fav1, d2, d1)
favwon = np.where(fav1, d["p1_won"].astype(bool), ~d["p1_won"].astype(bool))
gend = np.where(d["league"].astype(str).isin(["wta", "itf_women"]), "W", "M")
favpnl = np.where(favwon, favodd - 1, -1.0)
dogpnl = np.where(~favwon, dogodd - 1, -1.0)


def row(lab, mask, pnl, won):
    n = int(mask.sum())
    if not n:
        return "   %-30s (none)" % lab
    p = pnl[mask]
    se = 100 * p.std() / np.sqrt(n) if n > 1 else float("nan")
    w = int(won[mask].sum())
    return ("   %-30s n=%-4d %4d-%-4d roi %+7.2f%% +/-%4.1f"
            % (lab, n, w, n - w, 100 * p.mean(), se))


print("\n" + "=" * 92)
print("TABLE 2 -- all three on the SAME %d rows" % len(d))
print("   mc2 = genuinely frozen picks.  G and G2 = walk-forward BACKFILL on these games.")
print("=" * 92)
for lab, col, _r in HEADS:
    pv = d[col].astype(float).to_numpy()
    hfav = np.where(fav1, pv, 1 - pv)
    over = hfav - mkfav
    print("  %s" % lab)
    print(row("  dog-flip", hfav < 0.5, dogpnl, ~favwon))
    for g in ("M", "W"):
        print(row("    %s" % g, (hfav < 0.5) & (gend == g), dogpnl, ~favwon))
    print(row("  fav-over, any margin", over > 0, favpnl, favwon))
    print(row("  fav-over, 4pt+", over >= 0.04, favpnl, favwon))
    for g in ("M", "W"):
        print(row("    4pt+ %s" % g, (over >= 0.04) & (gend == g), favpnl, favwon))

print("\n  baselines on the same rows")
print(row("  every dog", np.ones(len(d), bool), dogpnl, ~favwon))
print(row("  every favourite", np.ones(len(d), bool), favpnl, favwon))

print("\n" + "=" * 92)
print("AGREEMENT -- how often the three even pick the same cell")
print("=" * 92)
cells = {}
for lab, col, _r in HEADS:
    pv = d[col].astype(float).to_numpy()
    hfav = np.where(fav1, pv, 1 - pv)
    over = hfav - mkfav
    cells[lab] = np.where(over > 0, "FAV", np.where(hfav < 0.5, "DOG", "-"))
for a in ("mc2", "G", "G2"):
    for b in ("mc2", "G", "G2"):
        if a < b:
            same = (cells[a] == cells[b]).mean()
            print("   %-4s vs %-4s same cell on %.0f%% of rows" % (a, b, 100 * same))
