"""WOULD H2H HISTORY HELP MC2 -- INCLUDING THE RECENCY/MARGIN VERSION (2026-10-15)

User: "do u think adding h2h history to mc2 would help it ?" and then, more precisely:

    "if someone plays better or worse against someone especially recent h2hs -- if its a long
     time ago it doesn't matter as much, if the h2h is recent and they beat them easily h2h i
     think its relevant"

That is a better hypothesis than raw H2H share and it is tested on its own terms here: RECENCY
(days since the last meeting) and MARGIN (how easily they won it), not just the win/loss.

MC2, MC3 and MC5 read no H2H at all today (zero references in all three modules), so this is a
genuine candidate, not a duplicate feature.

RUN ON MC2'S OWN FEATURE TABLE (data_cache/_mc2_features.parquet, 170,714 rows). That is the
table MC2 is built from, so a feature that carries information here is a feature MC2 could use --
no proxy dataset, no separate join to argue about. Only the columns needed are loaded; the
earlier attempt reused the Model D build chain and was OOM-killed on this box.

THE BAR A NEW MC2 FEATURE HAS TO CLEAR. MC2 is only useful where it DISAGREES with the market --
the board bets its disagreements. So a feature already inside the price cannot help: adding it
would pull MC2 toward the market and shrink exactly those disagreements. The test is therefore not
"does the H2H leader win more often" (they obviously do -- they are usually the better player) but

    does the H2H leader win MORE OFTEN THAN THE PRICE ALREADY SAYS?

`imp` is the market's implied probability for player a, so the comparison is actual win rate minus
mean imp, with a z on the difference. A diff near zero means priced.

EVERYTHING IS AS-OF. Prior meetings only: cumcount for the count, shifted cumsum for wins and
margin, shift(1) for the previous meeting's date. No row can see its own result or any later one.
This matters more than usual here -- an H2H feature built from the full history is the single
easiest way to leak a result into a backtest.

Run: ./venv/bin/python _h2h_for_mc2.py
"""
import re

import numpy as np
import pandas as pd

COLS = ["date", "a", "b", "surf", "won", "imp", "odd_a", "odd_b", "score", "wom"]
m = pd.read_parquet("data_cache/_mc2_features.parquet", columns=COLS)
m["date"] = pd.to_datetime(m["date"], errors="coerce")
m = m[m["date"].notna() & m["a"].notna() & m["b"].notna() & m["won"].notna()]
m = m.sort_values("date", kind="stable").reset_index(drop=True)
print("rows: %d   %s .. %s" % (len(m), m.date.min().date(), m.date.max().date()))

A = m["a"].astype(str).to_numpy()
B = m["b"].astype(str).to_numpy()
first_is_a = A < B
pair = np.where(first_is_a, A, B) + "\x00" + np.where(first_is_a, B, A)
m["pair"] = pair
won_a = m["won"].astype(bool).to_numpy()
won_first = np.where(first_is_a, won_a, ~won_a)


# ---- games margin from the score string, from player a's perspective -------------------------
def margin(s):
    """(games for a) - (games for b). The score is written a-first, so '6-4 6-3' is +5."""
    if not isinstance(s, str) or not s:
        return np.nan
    d = 0
    n = 0
    for g in re.findall(r"(\d+)\s*[-:]\s*(\d+)", s):
        x, y = int(g[0]), int(g[1])
        if x > 30 or y > 30:            # a tie-break point score, not a games score
            continue
        d += x - y
        n += 1
    return float(d) if n else np.nan


mg_a = m["score"].map(margin).to_numpy(float)
mg_first = np.where(first_is_a, mg_a, -mg_a)

g = m.groupby("pair", sort=False)
n_prior = g.cumcount().to_numpy()
cum_first = g["won"].transform(lambda s: s.cumsum()).to_numpy()  # placeholder, replaced below
# cumulative wins by the FIRST-named player, strictly prior
wf = pd.Series(won_first.astype(float), index=m.index)
prior_wins_first = (wf.groupby(m["pair"], sort=False).cumsum() - wf).to_numpy()
mgf = pd.Series(mg_first, index=m.index)
prior_marg_first = (mgf.groupby(m["pair"], sort=False).cumsum().shift(0)
                    - mgf.fillna(0)).to_numpy()
# the previous meeting's date for this pair
prev_date = g["date"].shift(1)
days_since = (m["date"] - prev_date).dt.days.to_numpy(float)

# translate to player a's perspective
prior_wins_a = np.where(first_is_a, prior_wins_first, n_prior - prior_wins_first)
prior_marg_a = np.where(first_is_a, prior_marg_first, -prior_marg_first)

has = n_prior > 0
share_a = np.where(has, prior_wins_a / np.maximum(n_prior, 1), np.nan)
avg_marg = np.where(has, prior_marg_a / np.maximum(n_prior, 1), np.nan)
imp = pd.to_numeric(m["imp"], errors="coerce").to_numpy(float)
ok = ~np.isnan(imp)
isw = m["wom"].fillna(0).astype(bool).to_numpy() if "wom" in m.columns else np.zeros(len(m), bool)

print("with >=1 prior meeting: %d (%.0f%%)   >=2: %d   >=3: %d   >=5: %d"
      % (has.sum(), 100 * has.mean(), int((n_prior >= 2).sum()),
         int((n_prior >= 3).sum()), int((n_prior >= 5).sum())))
print("priced rows (imp present): %d" % int(ok.sum()))
print("median days since last meeting: %.0f" % np.nanmedian(days_since[has]))
BAR = "=" * 104


def cmp(mask, lab, ind="   ", floor=200):
    mm = mask & ok
    n = int(mm.sum())
    if n < floor:
        print("%s%-36s n=%-6d (too few)" % (ind, lab, n)); return
    act, exp = won_a[mm].mean(), imp[mm].mean()
    se = np.sqrt(max(act * (1 - act), 1e-9) / n)
    print("%s%-36s n=%-6d  price %5.1f%%   ACTUAL %5.1f%%   diff %+5.2f pt   z %+5.2f"
          % (ind, lab, n, 100 * exp, 100 * act, 100 * (act - exp), (act - exp) / se))


print("\n" + BAR)
print("0. BASELINE -- is raw H2H already in the price?")
print(BAR)
cmp(has & (share_a > 0.5), "H2H leader")
cmp(has & (share_a < 0.5), "H2H trailer")
cmp(~has, "no prior meeting (control)")
for lo, hi, nm in ((1, 1, "1 prior"), (2, 2, "2 priors"), (3, 4, "3-4 priors"), (5, 99, "5+ priors")):
    b = (n_prior >= lo) & (n_prior <= hi)
    cmp(b & (share_a > 0.5), "  leader, " + nm)

print("\n" + BAR)
print("1. THE USER'S HYPOTHESIS, PART ONE: RECENCY -- does an OLD H2H matter less?")
print(BAR)
lead = has & (share_a > 0.5)
trail = has & (share_a < 0.5)
for lo, hi, nm in ((0, 180, "last met < 6 months ago"), (180, 365, "6-12 months"),
                   (365, 730, "1-2 years"), (730, 1e9, "over 2 years ago")):
    b = (days_since > lo) & (days_since <= hi)
    print("   %s" % nm)
    cmp(b & lead, "H2H leader", ind="      ")
    cmp(b & trail, "H2H trailer", ind="      ")

print("\n" + BAR)
print("2. PART TWO: MARGIN -- did they beat them EASILY? (avg games margin in prior meetings)")
print(BAR)
for lo, hi, nm in ((4, 99, "won easily (+4 games or more)"), (1, 4, "won close (+1 to +4)"),
                   (-4, -1, "lost close (-1 to -4)"), (-99, -4, "lost badly (-4 or worse)")):
    b = has & (avg_marg > lo) & (avg_marg <= hi)
    cmp(b, nm)

print("\n" + BAR)
print("3. BOTH TOGETHER -- the exact claim: RECENT *and* WON EASILY")
print(BAR)
recent = days_since <= 365
cmp(recent & (avg_marg >= 4), "met within 1y AND won by 4+ games")
cmp(recent & (avg_marg >= 6), "met within 1y AND won by 6+ games")
cmp(recent & (avg_marg <= -4), "met within 1y AND lost by 4+")
cmp(~recent & (avg_marg >= 4), "met OVER 1y ago, won by 4+ (control)")
print("   -- and the same split by gender --")
for gl, gm in (("men  ", ~isw), ("women", isw)):
    cmp(recent & (avg_marg >= 4) & gm, gl + ", within 1y, won by 4+", ind="      ", floor=120)

print("\n" + BAR)
print("4. WHERE IT WOULD BE BETTABLE: the market DOG with the H2H edge")
print(BAR)
cmp(lead & (imp < 0.5), "H2H leader who is the market dog")
cmp(recent & (avg_marg >= 4) & (imp < 0.5), "recent + easy winner, market dog")
cmp(lead & (imp > 0.40) & (imp < 0.60), "H2H leader, market close 40-60%")
print("\n" + BAR)
print("READ: MC2 only pays where it DISAGREES with the price, so a diff near 0 with |z| < 2 means")
print("the market has it and feeding it to MC2 would shrink the disagreements the board bets on.")
print("A diff of +2pt or more with |z| > 3 on a readable sample would be worth building.")
print(BAR)
