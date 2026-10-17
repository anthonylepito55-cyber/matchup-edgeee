"""BUILD THE AS-OF MC2 RE-PRICER FOR MC6's RECON ROWS (2026-10-16).

The comparison between MC2 and MC6 on past days is not a fair fight: on MC6's 646 reconstructed
rows, MC2 is a GENUINE FORWARD value on 633 of them (98%). So MC6 has been replaying those
matches with correct as-of rating states, while MC2's number is whatever it actually produced at
the time -- on ratings that were up to four days stale, because the nightly rebuild did not exist
until 2026-10-13.

That is not leakage; nothing sees its own result. It is an input-quality advantage, and it is
exactly the shape that would manufacture MC6's +8.60pt lead on those rows while leaving only
+1.76pt on the forward ones.

This generates a variant of _mc2_recon_rebuild.py that re-prices MC2 AS-OF on precisely those
rows, so both heads can be compared with the same input quality. The original's safety
properties are preserved and are why it is being reused rather than rewritten: it writes to its
own parquet and never to the log, it asserts it cannot overwrite a live artifact before exec'ing
the builder, and it unpins the state between dates.

Only three things change: which rows are selected, and the three output paths so nothing collides
with the 2026-10-14 surface rebuild.
"""
import io
import os

DIR = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(DIR, "_mc2_recon_rebuild.py")
DST = os.path.join(DIR, "_mc2_asof_for_mc6rows.py")

s = io.open(SRC, encoding="utf-8").read()

OLD_SEL = '''RC = (log["mc2_recon"].fillna(False).astype(bool).to_numpy()
      if "mc2_recon" in log.columns else np.zeros(len(log), bool))
todo = log[RC & log["mc2_p1"].notna()].copy()'''
assert s.count(OLD_SEL) == 1, "selection block not found"

NEW_SEL = '''RC = (log["mc2_recon"].fillna(False).astype(bool).to_numpy()
      if "mc2_recon" in log.columns else np.zeros(len(log), bool))
R6 = (log["mc6_recon"].fillna(False).astype(bool).to_numpy()
      if "mc6_recon" in log.columns else np.zeros(len(log), bool))
# 2026-10-16: the rows where MC6 is RECONSTRUCTED but MC2 is a genuine FORWARD value -- 98% of
# MC6's recon window. On those matches MC6 has been replaying with correct as-of ratings while
# MC2 ran on states up to four days stale (the nightly rebuild landed 2026-10-13). Re-pricing MC2
# as-of here removes that input-quality gap instead of arguing about how big it is.
todo = log[R6 & ~RC & log["mc2_p1"].notna() & log["mc6_p1"].notna()].copy()'''
s = s.replace(OLD_SEL, NEW_SEL)

for old, new in (
    ('OUT = "data_cache/_mc2_recon2.parquet"',
     'OUT = "data_cache/_mc2_asof_mc6rows.parquet"'),
    ('TMP_STATE = "data_cache/_mc2_recon2_state.pkl"',
     'TMP_STATE = "data_cache/_mc2_asof_m6_state.pkl"'),
    ('TMP_FEAT = "data_cache/_mc2_recon2_feat.parquet"',
     'TMP_FEAT = "data_cache/_mc2_asof_m6_feat.parquet"'),
):
    assert s.count(old) == 1, "path not found: %s" % old
    s = s.replace(old, new)

s = s.replace("recon rows to re-price:", "MC6-recon / MC2-forward rows to re-price:")
io.open(DST, "w", encoding="utf-8", newline="").write(s)
print("wrote %s" % os.path.basename(DST))
for k in ("R6 & ~RC", "_mc2_asof_mc6rows.parquet", "_mc2_asof_m6_state.pkl"):
    print("   %-32s %d" % (k, s.count(k)))
# the original's guard must survive into the variant
assert 'assert bad not in src, "would overwrite a live artifact' in s, "safety assert lost"
print("   safety assert preserved: yes")
import py_compile
py_compile.compile(DST, doraise=True)
print("compiles: OK")
print("RESULT: OK")
