"""If E's skill is real (it wins its disagreements 53.3-46.7) but live ROI is ~0, the leak is
PRICE, not prediction. This finds the minimum edge that survives realistic vig. (2026-09-04)

The backtest settles at fair de-vigged prices minus an assumed 2% haircut. Real books charge
more; a thin 2-pt edge can be entirely juice. Sweeps the favorite/underdog minimum-edge
thresholds against several vig assumptions and reports ROI, bet count and total units, so the
tradeoff (higher ROI vs fewer bets vs total profit) is explicit.

Current live rule: favorites >= 2 pts, underdogs flip + >= 4 pts. Read-only."""
import numpy as np
import model_e

z = np.load("data_cache/_omega_vs_e_probs.npz", allow_pickle=True)
pE, mkt, y, fid, dates = z["pE"], z["mkt"], z["y"], z["fid"], z["dates"]
dates = np.array([str(d) for d in dates])
bad = (dates >= "2025-07-13") & (dates <= "2025-07-20")
ok = np.where((fid >= 2) & ~np.isnan(mkt) & ~np.isnan(pE) & ~bad)[0]
half = len(ok) // 2
early_set = set(ok[:half].tolist())

# every bet the CURRENT rule makes, with its edge, so thresholds can be applied afterwards
bets = []
for i in ok:
    bt = model_e.compute_bet(float(pE[i]), float(mkt[i]), "H", "A")
    if not bt:
        continue
    p_side = pE[i] if bt["side_is_home"] else 1 - pE[i]
    won = bool(y[i]) if bt["side_is_home"] else not bool(y[i])
    bets.append({"edge": p_side - bt["market_prob"], "mkt": bt["market_prob"], "won": won,
                 "dog": bt["type"] == "underdog", "early": i in early_set})
print(f"{len(bets)} bets from the current rule, {len(ok)} scored games\n")


def run(min_fav, min_dog, vig):
    pnl, early = [], []
    for b in bets:
        if b["edge"] < (min_dog if b["dog"] else min_fav):
            continue
        dec = (1.0 / b["mkt"]) * (1 - vig)
        if dec <= 1.0:
            continue
        pnl.append((dec - 1.0) if b["won"] else -1.0)
        early.append(b["early"])
    if len(pnl) < 25:
        return None
    pnl, early = np.array(pnl), np.array(early, dtype=bool)
    return len(pnl), 100 * pnl.mean(), pnl.sum(), 100 * pnl[early].mean(), 100 * pnl[~early].mean()


print("=== how the CURRENT rule (fav 2pts / dog 4pts) holds up as vig gets realistic ===")
print(f"{'vig assumption':>16s} {'bets':>6s} {'ROI':>8s} {'units':>9s}")
for vig, name in [(0.00, "0% (fair)"), (0.02, "2% (backtest)"), (0.035, "3.5% (typical shop)"), (0.05, "5% (single book)")]:
    r = run(0.02, 0.04, vig)
    print(f"{name:>16s} {r[0]:6d} {r[1]:+7.2f}% {r[2]:+8.1f}u")

for vig in (0.035, 0.05):
    print(f"\n=== threshold sweep at {vig*100:.1f}% vig ===")
    print(f"{'fav min':>8s} {'dog min':>8s} {'bets':>6s} {'ROI':>8s} {'units':>9s} {'early':>8s} {'late':>8s}")
    for mf in (0.02, 0.03, 0.04, 0.05, 0.06):
        for md in (0.04, 0.06, 0.08):
            r = run(mf, md, vig)
            if r is None:
                continue
            star = "  <-- current" if (mf == 0.02 and md == 0.04) else ""
            print(f"{mf*100:7.0f}% {md*100:7.0f}% {r[0]:6d} {r[1]:+7.2f}% {r[2]:+8.1f}u {r[3]:+7.2f}% {r[4]:+7.2f}%{star}")
print("\nDONE")
