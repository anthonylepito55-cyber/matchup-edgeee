"""PHASE 1 AUDIT, part 1: the frozen prediction log's integrity.

Checks, in order: coverage and date span; settlement gaps; duplicate matches; the quality flags
(surface_bad / inplay_suspect / resolve_bad / void); odds sanity and timestamping; per-head
coverage and how much of each head is as-of RECONSTRUCTION rather than a genuine frozen read;
selection bias (which matches reach the log at all); and the archive the models train on.
"""
import collections
import os
import pandas as pd
import tennis_log as T

pd.set_option("display.width", 200)
log = pd.read_parquet(T.LOG_PATH)
print("=" * 100)
print("1. THE PREDICTION LOG  (%s)" % T.LOG_PATH)
print("=" * 100)
print("rows %d   columns %d   dates %s -> %s"
      % (len(log), len(log.columns), str(log["date"].min())[:10], str(log["date"].max())[:10]))
s = log["settled"].fillna(False).astype(bool)
print("settled %d   unsettled %d   with p1_won %d   settled-but-no-winner %d"
      % (s.sum(), (~s).sum(), log["p1_won"].notna().sum(), (s & log["p1_won"].isna()).sum()))

# ---------------------------------------------------------------- unsettled backlog by age
un = log[~s].copy()
un["d"] = pd.to_datetime(un["date"].astype(str).str[:10], errors="coerce")
today = pd.Timestamp(log["date"].max()).normalize()
old = un[un["d"] < today - pd.Timedelta(days=2)]
print("unsettled older than 2 days: %d  %s"
      % (len(old), ("dates " + str(old["d"].min())[:10] + " -> " + str(old["d"].max())[:10]) if len(old) else ""))

# ---------------------------------------------------------------- duplicates
def pk(r):
    return (str(r["date"])[:10], tuple(sorted([str(r["player_1"]), str(r["player_2"])])))


keys = [pk(r) for _, r in log.iterrows()]
cnt = collections.Counter(keys)
dups = {k: c for k, c in cnt.items() if c > 1}
print("duplicate (date, player-pair) groups: %d covering %d rows" % (len(dups), sum(dups.values())))
for k in list(dups)[:6]:
    g = log[[kk == k for kk in keys]]
    print("   %s %s  n=%d  settled=%s  odds=%s  srcs=%s"
          % (k[0], " / ".join(x[:18] for x in k[1]), len(g), list(g["settled"].fillna(False)),
             list(g["p1_odds"]), list(g.get("source", pd.Series(["?"] * len(g))))))

# ---------------------------------------------------------------- quality flags
print("")
print("QUALITY FLAGS (rows excluded from every lane)")
for c in ("surface_bad", "inplay_suspect", "resolve_bad", "void"):
    if c in log.columns:
        v = log[c].fillna(False).astype(bool)
        print("   %-16s %4d of %d (%.1f%%)   settled %d" % (c, v.sum(), len(log), 100 * v.mean(), (v & s).sum()))
    else:
        print("   %-16s column absent" % c)

# ---------------------------------------------------------------- odds sanity / timestamps
print("")
print("ODDS SANITY")
o = log[["p1_odds", "p2_odds"]].dropna()
print("   rows with both prices %d   missing %d" % (len(o), len(log) - len(o)))
bad = o[((o["p1_odds"] > 0) & (o["p2_odds"] > 0)) | ((o["p1_odds"] < 0) & (o["p2_odds"] < 0))]
print("   both-same-sign (no favourite/dog) %d" % len(bad))


def dec(a):
    a = float(a)
    return 1.0 + (a / 100.0 if a > 0 else 100.0 / -a)


ov = [(1 / dec(a) + 1 / dec(b)) for a, b in zip(o["p1_odds"], o["p2_odds"])]
ovs = pd.Series(ov)
print("   overround: median %.4f  p05 %.4f  p95 %.4f   | <=1.0 (arb/de-vigged already) %d  >1.15 %d"
      % (ovs.median(), ovs.quantile(.05), ovs.quantile(.95), (ovs <= 1.0).sum(), (ovs > 1.15).sum()))
for c in ("quote_ts", "price_ts", "odds_ts", "start_time_utc", "logged_at", "created_at"):
    if c in log.columns:
        print("   timestamp column present: %-16s non-null %d" % (c, log[c].notna().sum()))

# price captured after the start = a price that was never on offer pre-match
if "start_time_utc" in log.columns and "logged_at" in log.columns:
    st = pd.to_datetime(log["start_time_utc"], errors="coerce", utc=True)
    lg = pd.to_datetime(log["logged_at"], errors="coerce", utc=True)
    late = (lg > st) & st.notna() & lg.notna()
    print("   rows whose price was logged AFTER the start: %d" % late.sum())

# ---------------------------------------------------------------- per-head coverage
print("")
print("PER-HEAD COVERAGE (settled rows only; FWD = genuine frozen read, RECON = as-of rebuild)")
heads = [(c[:-3], c, c[:-3] + "_recon") for c in log.columns if c.endswith("_p1")]
print("   %-18s %7s %7s %7s   %-12s %s" % ("head", "settled", "FWD", "RECON", "fwd span", "note"))
ss = log[s]
for nm, col, rc in sorted(heads):
    if ss[col].notna().sum() == 0:
        continue
    has = ss[col].notna()
    if rc in ss.columns:
        r = ss[rc].fillna(False).astype(bool)
    else:
        r = pd.Series(False, index=ss.index)
    fwd = ss[has & ~r]
    span = ("%s..%s" % (str(fwd["date"].min())[5:10], str(fwd["date"].max())[5:10])) if len(fwd) else "-"
    note = "" if rc in ss.columns else "no recon flag"
    print("   %-18s %7d %7d %7d   %-12s %s" % (nm, has.sum(), len(fwd), (has & r).sum(), span, note))

# ---------------------------------------------------------------- selection bias
print("")
print("=" * 100)
print("2. SELECTION BIAS -- which matches reach the log")
print("=" * 100)
for c in ("league", "surface", "source", "tournament_level", "round"):
    if c in log.columns:
        vc = log[c].astype(str).value_counts(dropna=False)
        print("   %-16s %s" % (c, dict(list(vc.items())[:8])))
print("   settled rate by league:")
for lg_, g in log.groupby(log["league"].astype(str)):
    gs = g["settled"].fillna(False).astype(bool)
    print("      %-16s n=%-5d settled %5.1f%%" % (lg_, len(g), 100 * gs.mean()))

# ---------------------------------------------------------------- the training archive
print("")
print("=" * 100)
print("3. THE ARCHIVE THE MODELS TRAIN ON")
print("=" * 100)
import tennis_model_a as A
p = A.LOGS_PARQUET
print("   %s  exists=%s  size=%.1f MB  mtime=%s"
      % (p, os.path.exists(p), os.path.getsize(p) / 1e6 if os.path.exists(p) else 0,
         pd.Timestamp(os.path.getmtime(p), unit="s") if os.path.exists(p) else "-"))
ar = pd.read_parquet(p)
print("   rows %d  columns %d" % (len(ar), len(ar.columns)))
d = pd.to_datetime(ar["date"], errors="coerce")
print("   dates %s -> %s   (staleness vs log: %s days)"
      % (str(d.min())[:10], str(d.max())[:10], (today - d.max().normalize()).days))
print("   players %d   surfaces %s" % (ar["player_slug"].nunique(), dict(ar["surface"].astype(str).value_counts().head(6))))
if "won" in ar.columns:
    print("   win rate %.4f  (two rows per match -> should be ~0.5000)" % ar["won"].mean())
if "tournament_level" in ar.columns:
    print("   levels %s" % dict(ar["tournament_level"].astype(str).str.lower().value_counts().head(8)))
# retirements / walkovers kept?
if "score" in ar.columns:
    sc = ar["score"].astype(str)
    print("   archive scores containing ret/walkover markers: %d of %d"
          % (sc.str.contains("ret|w/o|walk", case=False, na=False).sum(), len(sc)))
