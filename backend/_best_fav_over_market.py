"""WHICH MODEL IS BEST ON FAVOURITES WHEN IT SITS 1+ POINTS OVER THE MARKET? (2026-10-13)

Every head with a frozen probability in the log, scored in one cell: the match's market
FAVOURITE, backed at the frozen closing price, whenever that head rates it at least 1 point
above the market's own de-vigged number.

Ranked against the only bar that matters -- backing every favourite on the same rows. A head
that returns -6% in a universe where chalk returns -7% has found nothing; it has to clear the
baseline by enough to pay for the vig before it is a cell rather than a coincidence.

Two columns per head:
  ALL      -- every settled row the head priced, forward picks and walk-forward backfills alike
  FORWARD  -- only rows the head was genuinely frozen on, where a recon flag exists to tell them
              apart. Heads without a flag have never been backfilled, so the two are the same.
A head whose two columns disagree is telling you its number is an artefact of one of them --
that is exactly how MC2's favourite band turned out to be a 36-bet forward illusion.
"""
import numpy as np
import pandas as pd

import tennis_log

# (label, probability column, recon flag or None)
HEADS = [
    ("A", "model_a_p1", None), ("B", "model_b_p1", None),
    ("C", "model_c_p1", None), ("C gray (cma)", "model_cma_p1", None),
    ("D", "model_d_p1", None), ("D gray (dma)", "model_dma_p1", None),
    ("MC serve (D)", "mc_p1", None),
    ("C-MC c50", "mc_c_p1", "mc_c_recon"), ("C-MC c75", "mc_c75_p1", "mc_c_recon"),
    ("C-MC cUTR", "mc_cutr_p1", "mc_c_recon"),
    ("X (meta)", "model_x_p1", "model_x_recon"),
    ("MC2", "mc2_p1", "mc2_recon"),
    ("G", "model_g_p1", "model_g_recon"),
    ("G2", "model_g2_p1", "model_g2_recon"),
]

L = pd.read_parquet(tennis_log.LOG_PATH)
d = L[(L["settled"] == True) & L["p1_won"].notna()                      # noqa: E712
      & L["p1_odds"].notna() & L["p2_odds"].notna()].copy()
for c in ("surface_bad", "inplay_suspect"):
    if c in d.columns:
        d = d[~d[c].fillna(False).astype(bool)]
print("settled, clean rows: %d  (%s .. %s)"
      % (len(d), str(d["date"].min())[:10], str(d["date"].max())[:10]))


def dec(a):
    a = float(a)
    return 1 + a / 100 if a > 0 else 1 + 100 / abs(a)


d1, d2 = d["p1_odds"].map(dec).to_numpy(), d["p2_odds"].map(dec).to_numpy()
mk1 = (1 / d1) / ((1 / d1) + (1 / d2))
won1 = d["p1_won"].astype(bool).to_numpy()
fav1 = mk1 >= 0.5
mkfav = np.where(fav1, mk1, 1 - mk1)
favodd = np.where(fav1, d1, d2)
favwon = np.where(fav1, won1, ~won1)
favpnl = np.where(favwon, favodd - 1, -1.0)
gend = np.where(d["league"].astype(str).isin(["wta", "itf_women"]), "W", "M")

MIN = 0.01          # 1 point over the market


def cell(m):
    n = int(m.sum())
    if n < 1:
        return None
    p = favpnl[m]
    return {"n": n, "w": int(favwon[m].sum()), "roi": 100 * p.mean(),
            "se": 100 * p.std() / np.sqrt(n) if n > 1 else float("nan")}


def fmt(c):
    if not c:
        return "%-26s" % "      --"
    return ("n=%-4d %4d-%-4d %+7.2f%% +/-%4.1f" % (c["n"], c["w"], c["n"] - c["w"], c["roi"], c["se"]))


rows = []
for lab, col, rflag in HEADS:
    if col not in d.columns:
        continue
    pv = pd.to_numeric(d[col], errors="coerce").to_numpy(dtype=float)
    have = ~np.isnan(pv)
    hfav = np.where(fav1, pv, 1 - pv)
    sel = have & ((hfav - mkfav) >= MIN)
    rc = (d[rflag].fillna(False).astype(bool).to_numpy()
          if (rflag and rflag in d.columns) else np.zeros(len(d), bool))
    allc = cell(sel)
    fwdc = cell(sel & ~rc)
    base = cell(have)                      # chalk on the rows this head covers
    rows.append({"lab": lab, "all": allc, "fwd": fwdc, "base": base,
                 "m": cell(sel & (gend == "M")), "w": cell(sel & (gend == "W")),
                 "backfilled": int(rc.sum())})

print("\n" + "=" * 112)
print("FAVOURITE, backed when the head is 1pt+ OVER the market  --  sorted by the ALL column")
print("=" * 112)
print("%-14s %-30s %-30s %-16s" % ("head", "ALL rows", "FORWARD only", "chalk on same rows"))
for r in sorted(rows, key=lambda x: -(x["all"]["roi"] if x["all"] else -99)):
    b = r["base"]
    print("%-14s %-30s %-30s %s"
          % (r["lab"], fmt(r["all"]), fmt(r["fwd"]),
             ("%+.2f%% (n=%d)" % (b["roi"], b["n"])) if b else "--"))

print("\n" + "=" * 112)
print("EDGE OVER CHALK -- the ALL column minus backing every favourite on the head's own rows")
print("=" * 112)
scored = []
for r in rows:
    if not r["all"] or not r["base"]:
        continue
    scored.append((r["all"]["roi"] - r["base"]["roi"], r))
for diff, r in sorted(scored, key=lambda x: -x[0]):
    flag = ""
    if r["fwd"] and r["all"] and abs(r["fwd"]["roi"] - r["all"]["roi"]) > 8:
        flag = "   <-- forward and all disagree by %.0fpt, treat with suspicion" % abs(r["fwd"]["roi"] - r["all"]["roi"])
    print("   %-14s %+6.2f pt over chalk   (cell %+.2f%% on %d vs chalk %+.2f%%)%s"
          % (r["lab"], diff, r["all"]["roi"], r["all"]["n"], r["base"]["roi"], flag))

print("\n" + "=" * 112)
print("GENDER SPLIT of the same cell (ALL rows)")
print("=" * 112)
for r in sorted(rows, key=lambda x: -(x["all"]["roi"] if x["all"] else -99)):
    print("   %-14s M %-28s W %s" % (r["lab"], fmt(r["m"]), fmt(r["w"])))

print("\noverall chalk baseline: %s" % fmt(cell(np.ones(len(d), bool))))
