"""RETRO (ARCHIVE BACKTEST) OF THE DOG CELLS, MC2 vs MC6 (2026-10-16)

User: "also show retro for both" -- the archive counterpart to the live-log band table.

This is a BACKTEST, and the standing rule on this project is that forward decides. It is useful
here for one specific reason: the live cells hold 2-61 bets each, so they cannot distinguish a
real cell from a lucky one. The archive holds tens of thousands and can say whether a cell's
SHAPE is plausible at all -- which bands work, which gender, whether the 6pt gate beats the 4pt.
It cannot say what the cells will return going forward, and a cell that is strong here and weak
live is not thereby vindicated.

BOTH HEADS ARE REBUILT FROM THE ARCHIVE, not read from the log:

    MC2 = sigmoid( 0.5*logit(p_elo) + 0.5*logit(p_markov) + asym_tilt )
    MC6 = sigmoid( logit(MC5) + 0.25*h2h + 0.50*sform )

MC5's legs come from its own feature table, and h2h / sform are built AS-OF -- strictly prior
meetings for the head-to-head, an EWMA shifted by one for the surface-form residual. The margin
convention is the one tennis_log uses (model's probability on the FAVOURITE minus the market's),
and it is self-checked against the live lane before anything prints.

Tab population: +100..+300, no ITF men, same first-match band assignment as the board.
"""
import math
import re

import numpy as np
import pandas as pd

from tennis_mc2 import _NODES, _rnd, asym_tilt, p_match

lgt = lambda p: np.log(np.clip(p, 1e-6, 1 - 1e-6) / (1 - np.clip(p, 1e-6, 1 - 1e-6)))
COLS = ["date", "year", "a", "b", "surf", "won", "imp", "p_elo", "pa_pt", "pb_pt",
        "nS_a", "nS_b", "score", "odd_a", "odd_b", "wom", "lvlg"]


def load(tag):
    F = pd.read_parquet("data_cache/_%s_features.parquet" % tag, columns=COLS)
    F["date"] = pd.to_datetime(F["date"], errors="coerce")
    return F


F2 = load("mc2")
F5 = load("mc5")
assert len(F2) == len(F5), "feature tables differ in length"
F = F2.sort_values("date", kind="stable")
order = F.index.to_numpy()
F = F.reset_index(drop=True)
F5 = F5.loc[order].reset_index(drop=True)
ok = (F.date.notna() & F.a.notna() & F.b.notna() & F.won.notna()
      & F.p_elo.notna() & F.pa_pt.notna() & F.pb_pt.notna()
      & F.odd_a.notna() & F.odd_b.notna())
F, F5 = F[ok].reset_index(drop=True), F5[ok].reset_index(drop=True)
print("archive rows with odds: %d  (%s .. %s)"
      % (len(F), F.date.min().date(), F.date.max().date()), flush=True)

# THE ARCHIVE STORES DECIMAL ODDS (1.01 .. 38.79), not American -- verified against `imp`,
# which correlates 0.9986 with 1/odd_a. Treating them as American silently emptied every band
# on the first run, because an American-converted 1.85 lands nowhere near +100..+300.
D1 = pd.to_numeric(F.odd_a, errors="coerce").to_numpy(float)
D2 = pd.to_numeric(F.odd_b, errors="coerce").to_numpy(float)
am = lambda d: np.where(d >= 2.0, (d - 1.0) * 100.0, -100.0 / np.maximum(d - 1.0, 1e-9))
o1, o2 = am(D1), am(D2)
mk1 = (1 / D1) / ((1 / D1) + (1 / D2))
Y1 = F.won.astype(bool).to_numpy()
isw = F.wom.fillna(0).astype(bool).to_numpy()
itfm = (F.lvlg.fillna(0).astype(int).to_numpy() == 2) & ~isw
dog1 = mk1 < 0.5
mkf = np.maximum(mk1, 1 - mk1)
dam = np.where(dog1, o1, o2)
dod = np.where(dog1, D1, D2)
dwon = np.where(dog1, Y1, ~Y1)
dpnl = np.where(dwon, dod - 1, -1.0)


def blend(G):
    sga = 0.10 / np.maximum(G.nS_a.to_numpy(float), 4) ** 0.5
    sgb = 0.10 / np.maximum(G.nS_b.to_numpy(float), 4) ** 0.5
    pa, pb = G.pa_pt.to_numpy(float), G.pb_pt.to_numpy(float)
    pm = np.zeros(len(G))
    for xi, wi in _NODES:
        for xj, wj in _NODES:
            pm += wi * wj * np.array([p_match(_rnd(x + xi * s1), _rnd(y + xj * s2), False)
                                      for x, y, s1, s2 in zip(pa, pb, sga, sgb)])
    az = np.array([asym_tilt(n1, n2) for n1, n2 in
                   zip(G.nS_a.to_numpy(float), G.nS_b.to_numpy(float))])
    return 0.5 * lgt(G.p_elo.to_numpy(float)) + 0.5 * lgt(pm) + az


Z2 = blend(F)
print("MC2 blend rebuilt", flush=True)
Z5 = blend(F5)
print("MC5 blend rebuilt", flush=True)

# ---- as-of h2h and sform, exactly as tennis_mc6 defines them ----
A = F.a.astype(str).to_numpy()
B = F.b.astype(str).to_numpy()
SU = F.surf.astype(str).to_numpy()
first = A < B
F["pair"] = np.where(first, A, B) + "\x00" + np.where(first, B, A)
TD = F.date.astype("int64").to_numpy() / 86_400_000_000_000.0


def margin(s):
    d = 0
    for x, y in re.findall(r"(\d+)\s*[-:]\s*(\d+)", str(s or "")):
        x, y = int(x), int(y)
        if x <= 30 and y <= 30:
            d += x - y
    return float(d)


MG = F.score.map(margin).to_numpy(float)
wf = np.where(first, Y1, ~Y1).astype(float)
mf = np.where(first, MG, -MG)
HW = np.zeros(len(F)); HS = np.zeros(len(F)); HM = np.zeros(len(F))
for idx in [np.sort(v) for v in F.groupby("pair", sort=False).indices.values() if len(v) > 1]:
    for k in range(1, len(idx)):
        i, j = idx[k], idx[:k]
        w = 0.5 ** ((TD[i] - TD[j]) / 365.0)
        sw = w.sum()
        if sw > 0:
            HW[i] = sw
            HS[i] = (w * wf[j]).sum() / sw - 0.5
            HM[i] = (w * mf[j]).sum() / sw
h2h = (np.where(first, 1.0, -1.0)
       * (0.65 * (2.0 * HS) + 0.35 * np.clip(HM / 6.0, -1.5, 1.5)) * (HW / (HW + 1.0)))
PE = F.p_elo.to_numpy(float)
L = pd.DataFrame({"pl": np.concatenate([A, B]), "surf": np.concatenate([SU, SU]),
                  "date": np.concatenate([F.date.to_numpy(), F.date.to_numpy()]),
                  "resid": np.concatenate([Y1.astype(float) - PE, (~Y1).astype(float) - (1 - PE)]),
                  "row": np.concatenate([np.arange(len(F)), np.arange(len(F))]),
                  "side": np.concatenate([np.zeros(len(F), int), np.ones(len(F), int)])})
L = L.sort_values(["pl", "surf", "date"], kind="stable")
L["sf"] = (L.groupby(["pl", "surf"], sort=False)["resid"]
           .transform(lambda s: s.shift(1).ewm(halflife=5, min_periods=1).mean())).fillna(0.0)
sfa = np.zeros(len(F)); sfb = np.zeros(len(F))
m0 = L.side.to_numpy() == 0
sfa[L.loc[m0, "row"].to_numpy()] = L.loc[m0, "sf"].to_numpy()
sfb[L.loc[~m0, "row"].to_numpy()] = L.loc[~m0, "sf"].to_numpy()
sform = np.clip(sfa - sfb, -0.6, 0.6)
print("as-of terms built", flush=True)

P2 = 1 / (1 + np.exp(-Z2))
P6 = 1 / (1 + np.exp(-(Z5 + 0.25 * h2h + 0.50 * sform)))
OV = {"MC2": np.where(dog1, 1 - P2, P2) - mkf, "MC6": np.where(dog1, 1 - P6, P6) - mkf}
share = (OV["MC2"] <= -0.04).mean()
print("self-check: MC2 fires the 4pt dog gate on %.1f%% of archive rows (live log: ~2.9%%)"
      % (100 * share))
assert 0.01 < share < 0.15, "margin convention looks wrong"

BANDS = ((100, 150), (150, 200), (200, 250), (250, 300))
BASE = ~itfm & (dam >= 100) & (dam <= 300)


def cell(m):
    n = int(m.sum())
    if n < 20:
        return "      --     "
    w = int(dwon[m].sum())
    r = dpnl[m].mean()
    g = (r * n + (n - w)) / w if w else 0
    v = (w * g * g + (n - w)) / n - r * r if w else 0
    t = " t%+.1f" % (r / (math.sqrt(v) / math.sqrt(n))) if v > 0 else ""
    return "%+6.1f%% /%-5d%s" % (100 * r, n, t)


BAR = "=" * 86
for th, nm in ((0.04, "4pt"), (0.06, "6pt")):
    print("\n" + BAR)
    print("RETRO (archive backtest): DOGS at %s over, +100..+300, no ITF men" % nm)
    print(BAR)
    print("   %-7s %-12s %20s %20s" % ("", "", "MC2 retro", "MC6 retro"))
    for gl, gm in (("men", ~isw), ("women", isw)):
        for lo, hi in BANDS:
            b = BASE & gm & (dam >= lo) & (dam <= hi)
            print("   %-7s %-12s %20s %20s" % (gl, "+%d..+%d" % (lo, hi),
                                               cell(b & (OV["MC2"] <= -th)),
                                               cell(b & (OV["MC6"] <= -th))))
        b = BASE & gm
        print("   %-7s %-12s %20s %20s" % ("", "ALL BANDS",
                                           cell(b & (OV["MC2"] <= -th)),
                                           cell(b & (OV["MC6"] <= -th))))
print("\n" + BAR)
print("READ: this is the archive, not the forward log. It says whether a cell's SHAPE is")
print("plausible -- which bands, which gender, 4pt vs 6pt -- on tens of thousands of bets.")
print("It does not say what the cells will return, and a cell strong here and weak live is")
print("not thereby vindicated.")
print(BAR)
