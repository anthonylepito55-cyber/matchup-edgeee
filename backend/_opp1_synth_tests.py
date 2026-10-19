"""OPP1 v3.5 synthetic test suite — constructed fixtures ONLY. Touches no live data:
no snapshot store, no frozen log, no outcomes/prices/model values, no API, no Phase 5.
The single external read is `git show b0f59fb:OPP1_SPEC_V3_5_PROPOSAL.md` (frozen local blob).
"""
import hashlib
import math
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import opp1_eligibility as EL          # noqa: E402
import opp1_link as LK                 # noqa: E402
import opp1_sample as SA               # noqa: E402
import opp1_features as FE             # noqa: E402
import opp1_eval as EV                 # noqa: E402

PASS = []


# ---- REGISTERED BLOB SOURCE, PORTABLE (2026-10-19, owner-approved) -------------------------
# The suites used to source the registered spec bytes ONLY through `git show b0f59fb:...`, which
# made them unrunnable on any host without that commit (the EC2 clone does not have it). They
# now prefer an explicitly configured OPP1_SEED_ARTIFACT -- the exact artifact already installed
# and verified on the host -- and fall back to the canonical git blob when the variable is
# absent. Either way the bytes are verified against the registered sha256 before use, and the
# seed is still derived by the committed SA.seed_from_bytes, so neither the production seed
# derivation nor the registered thinning is touched and reconstructed bytes can never be used.
def registered_blob():
    p = os.environ.get("OPP1_SEED_ARTIFACT")
    if p:
        blob = open(p, "rb").read()
        if hashlib.sha256(blob).hexdigest() != SA.REG_SHA256:
            raise RuntimeError("OPP1_SEED_ARTIFACT does not hash to the registered sha256")
        return blob
    return subprocess.run(["git", "show", "%s:%s" % (SA.REG_COMMIT, SA.REG_BLOB_PATH)],
                          cwd=ROOT, capture_output=True, check=True).stdout
FAIL = []


def check(name, cond):
    (PASS if cond else FAIL).append(name)
    print(("PASS " if cond else "FAIL ") + name)


# ================================================================ 1. eligibility
S = 1_800_000_000.0  # synthetic epoch start


def q(book, sel, prob, poll, qts):
    return {"sportsbook": book, "selection": sel, "prob": prob, "poll_ts": poll, "quote_ts": qts}


base = pd.DataFrame([
    q("Pinnacle", "p1", .60, S - 5 * 3600, S - 5 * 3600 - 5),
    q("Pinnacle", "p2", .44, S - 5 * 3600, S - 5 * 3600 - 5),
    q("Pinnacle", "p1", .62, S - 40 * 60, S - 41 * 60),
    q("Pinnacle", "p2", .42, S - 40 * 60, S - 41 * 60),
    q("Kalshi", "p1", .58, S - 40 * 60, S - 42 * 60),
    q("Kalshi", "p2", .46, S - 40 * 60, S - 42 * 60),
])
r = EL.tstar_for_fixture(base, S)
check("elig: T* = last poll in window", r["eligible"] and r["tstar"] == S - 40 * 60)
check("elig: fair from latest pair", abs(r["fair"] - .62 / 1.04) < 1e-12)
check("elig: no polls in window -> ineligible",
      not EL.tstar_for_fixture(base[base.poll_ts < S - 6 * 3600], S)["eligible"])
stale = base.copy()
stale.loc[stale.sportsbook == "Pinnacle", "quote_ts"] = S - 25 * 3600
check("elig: Pinnacle pair older than S-24h -> stale",
      EL.tstar_for_fixture(stale, S)["reason"] == "pinnacle_pair_stale")
# quote stamped early but POLLED after T* must not count (poll_ts cutoff)
late_poll = base.copy()
late_poll.loc[late_poll.sportsbook == "Pinnacle", "poll_ts"] = S - 10 * 60  # after window end
late_poll = pd.concat([late_poll[late_poll.sportsbook == "Pinnacle"],
                       base[base.sportsbook == "Kalshi"]], ignore_index=True)
check("elig: early-stamped quote polled after T* is invisible",
      EL.tstar_for_fixture(late_poll, S)["reason"] == "no_pinnacle_pair")
check("elig: feature_input_ok enforces poll_ts <= T*",
      EL.feature_input_ok(100.0, 100.0) and not EL.feature_input_ok(100.1, 100.0))

# ---- A-O1 parsing ----
check("A-O1: offset-aware converts to UTC",
      EL.parse_ts("2026-10-20T02:00:00+02:00")["ts"] == pd.Timestamp("2026-10-20T00:00:00Z"))
check("A-O1: naive interpreted-as-UTC is COUNTED",
      EL.parse_ts("2026-10-21 12:00:00")["kind"] == "naive_interpreted")
check("A-O1: date-only flagged, never an eligibility ts",
      EL.parse_ts("2026-10-21")["kind"] == "date_only")
check("A-O1: garbage -> malformed", EL.parse_ts("not a time")["kind"] == "malformed")
check("A-O1: empty/none/nan -> missing",
      all(EL.parse_ts(v)["kind"] == "missing" for v in ("", "None", "nan", None)))

# ---- A-O1 membership ----
m = EL.validate_membership("2026-10-20T00:00:00Z")
check("A-O1: cutoff boundary 00:00Z Oct20 is a dev member", m["dev_member"])
m = EL.validate_membership("2026-10-19T23:59:59Z")
check("A-O1: Oct19 23:59 excluded by cutoff",
      not m["dev_member"] and "before_dev_cutoff" in m["labels"])
m = EL.validate_membership("2026-10-15T10:00:00Z")
check("A-O1: Oct15 carries BOTH exposure and cutoff labels (independent rules)",
      "analyst_exposure_excluded" in m["labels"] and "before_dev_cutoff" in m["labels"])
m = EL.validate_membership("2026-10-21T10:00:00Z", "2026-10-22T01:00:00Z")
check("A-O1: UTC day disagreement -> validation_pending, excluded",
      not m["dev_member"] and m["labels"] == ["validation_pending"])
# adversarial: one reading eligible, the other not -> still pending (no auto-pick)
m = EL.validate_membership("2026-10-19T10:00:00Z", "2026-10-21T10:00:00Z")
check("A-O1: disagreement never auto-resolved toward eligibility",
      not m["dev_member"] and "validation_pending" in m["labels"])
m = EL.validate_membership("2026-10-19T10:00:00Z", "2026-10-21T10:00:00Z",
                           resolution={"source": "linked", "reason": "store carried the qualifying date; TE start verified"})
check("A-O1: documented resolution re-admits via adopted source",
      m["dev_member"] and m["resolution_used"]["source"] == "linked")
m = EL.validate_membership("2026-10-21T10:00:00Z", "2026-10-19T10:00:00Z",
                           resolution={"source": "linked", "reason": "store listed wrong day"})
check("A-O1: resolution can also EXCLUDE (adopted source before cutoff)", not m["dev_member"])
m = EL.validate_membership(None)
check("A-O1: missing ts flagged+excluded, never coerced",
      not m["dev_member"] and "ts_missing" in m["labels"])
m = EL.validate_membership("2026-10-21")
check("A-O1: date-only store ts cannot establish eligibility",
      not m["dev_member"] and "ts_date_only_not_eligibility" in m["labels"])

# ================================================================ 2. linkage
OUT = pd.DataFrame([
    {"fixture_id": "FX1", "p1": "Novak Djokovic", "p2": "Rafael Nadal",
     "day": "2026-10-21", "tournament": "Shanghai, China"},
    {"fixture_id": "", "p1": "Djokovic N.", "p2": "Alcaraz C.",
     "day": "2026-10-22", "tournament": "m15 monastir"},
    {"fixture_id": "", "p1": "Smith J.", "p2": "Jones A.", "day": "2026-10-23", "tournament": "X"},
    {"fixture_id": "", "p1": "Smith John", "p2": "Jones Adam", "day": "2026-10-23", "tournament": "Y"},
    {"fixture_id": "", "p1": "Zhu L.", "p2": "Park H.", "day": "2026-10-24", "tournament": "None"},
])
r = LK.link_fixture({"fixture_id": "FX1", "p1": "x", "p2": "y", "day": "2026-10-21"}, OUT)
check("link: fixture_id equality wins", r["status"] == "linked"
      and r["tournament_norm"] == "shanghai, china")
r = LK.link_fixture({"fixture_id": "FXZ", "p1": "N. Djokovic", "p2": "C. Alcaraz",
                     "day": "2026-10-22"}, OUT)
check("link: unique name/day fallback", r["status"] == "linked"
      and r["tournament_norm"] == "m15 monastir")
r = LK.link_fixture({"fixture_id": "FXZ", "p1": "J. Smith", "p2": "A. Jones",
                     "day": "2026-10-23"}, OUT)
check("A-O3: two candidates -> unlinked_ambiguous", r["status"] == "unlinked_ambiguous")
r = LK.link_fixture({"fixture_id": "FXZ", "p1": "Nobody Q.", "p2": "Unknown Z.",
                     "day": "2026-10-23"}, OUT)
check("link: zero candidates -> unlinked_no_candidate", r["status"] == "unlinked_no_candidate")
r = LK.link_fixture({"fixture_id": "FXZ", "p1": "L. Zhu", "p2": "H. Park",
                     "day": "2026-10-24"}, OUT)
check("V3: tournament 'None' -> metadata_incomplete, reported separately from ambiguity",
      r["status"] == "linked_metadata_incomplete" and "metadata_incomplete" in r["labels"])
check("V3: normalization order cast->trim->lower",
      LK.norm_tournament("  NaN ") == (None, True) and
      LK.norm_tournament(" M15 Monastir ") == ("m15 monastir", False))

# ================================================================ 3. sample: seed, K, thinning
blob = None
try:
    import subprocess
    blob = registered_blob()
except Exception:
    pass
check("seed: registered blob readable", blob is not None and len(blob) > 1000)
check("seed: blob hashes to the registered sha256",
      hashlib.sha256(blob).hexdigest() == SA.REG_SHA256)
seed = SA.seed_from_bytes(registered_blob())
check("seed: equals int(first 16 hex of registered sha, 16)",
      seed == int("7539adbbafc84d22", 16))
crlf = blob.replace(b"\n", b"\r\n")
try:
    SA.seed_from_bytes(crlf)
    check("seed: CRLF-converted copy must FAIL", False)
except ValueError:
    check("seed: CRLF-converted copy must FAIL", True)

check("K: ISO year-week handles year boundary",
      SA.iso_week(pd.Timestamp("2024-12-30T12:00:00Z")) == "2025-W01" and
      SA.iso_week(pd.Timestamp("2027-01-01T12:00:00Z")) == "2026-W53")

dup = pd.DataFrame({"fixture_id": ["A", "A", "B"], "K": [("t", "w")] * 3})
check("dedup: one row per match", list(SA.dedup(dup)["fixture_id"]) == ["A", "B"])

rows = []
for kname, n in (("a", 10), ("b", 10), ("c", 10)):
    for i in range(n):
        rows.append({"fixture_id": "%s%02d" % (kname, i), "K": (kname, "2026-W44")})
df30 = pd.DataFrame(rows)
kept1, info1 = SA.thin(df30, seed)
kept2, _ = SA.thin(df30, seed)
check("thin: cap = floor(0.10 x N_pre) = 3", info1["cap_size"] == 3)
check("thin: deterministic across runs", kept1.equals(kept2))
check("thin: one pass only — final shares exceed 10% and are REPORTED, not re-thinned",
      len(kept1) == 9 and abs(SA.per_key_shares(kept1).max() - 1 / 3) < 1e-12)
# independent reimplementation of the kept-index draw for key 'a'
rng = np.random.default_rng(seed)
idx = np.sort(rng.choice(10, size=3, replace=False))
g = df30[df30["K"] == ("a", "2026-W44")].sort_values("fixture_id").reset_index(drop=True)
check("thin: independent reimplementation reproduces kept rows for first key",
      list(kept1[kept1["K"] == ("a", "2026-W44")]["fixture_id"]) ==
      list(g.iloc[idx]["fixture_id"]))
kept0, info0 = SA.thin(df30.head(9), seed)
check("thin: cap_size=0 -> NO thinning + boundary-fail flag",
      info0["boundary_fail_cap0"] and len(kept0) == 9)
under = pd.concat([df30, pd.DataFrame([{"fixture_id": "d%02d" % i, "K": ("d", "2026-W44")}
                                       for i in range(2)])], ignore_index=True)
_, infou = SA.thin(under, seed)
check("thin: key at/below cap untouched (no RNG call recorded)",
      ("d", "2026-W44") not in infou["keys_capped"])

start = pd.date_range("2026-11-02", periods=12000, freq="39min", tz="UTC")
big = pd.DataFrame({"start": start,
                    "league": ["atp", "atp_challenger", "itf_men"] * 4000,
                    "K": [("t%d" % (i % 300), "w") for i in range(12000)]})
c = SA.dev_counts(big)
check("counter: dev minimums met at 12k/9mo/3 tiers",
      c["meets_dev_minimums"] and c["iso_months"] >= 9)
check("counter: dev fails below 12,000 raw",
      not SA.dev_counts(big.head(11999))["meets_dev_minimums"])
t = SA.tier_counts(big.head(2250))
check("counter: tier needs 2,250 raw AND 12 ISO-weeks",
      t["meets_tier_minimums"] == (t["iso_weeks"] >= 12 and t["n_raw"] >= 2250))

# ================================================================ 4. features
T = S - 40 * 60
fx = pd.DataFrame([
    q("Pinnacle", "p1", .60, T - 4 * 3600, T - 4 * 3600 - 5),
    q("Pinnacle", "p2", .44, T - 4 * 3600, T - 4 * 3600 - 5),
    q("Kalshi", "p1", .58, T - 4 * 3600, T - 4 * 3600 - 10),
    q("Kalshi", "p2", .46, T - 4 * 3600, T - 4 * 3600 - 10),
    q("Pinnacle", "p1", .62, T, T - 60),
    q("Pinnacle", "p2", .42, T, T - 60),
    q("Kalshi", "p1", .59, T, T - 120),
    q("Kalshi", "p2", .45, T, T - 120),
])
f = FE.build_features(fx, T, mc2_p1=.55, mc2_recon=False)
fair0, fair1 = .60 / 1.04, .62 / 1.04
mid0, mid1 = (.58 + 1 - .46) / 2, (.59 + 1 - .45) / 2
check("E1_K exact", abs(f["E1_K"] - (fair1 - mid1)) < 1e-12)
check("E2_K = time-weighted gap (single step value here)",
      abs(f["E2_K"] - ((fair0 - mid0) * (4 * 3600 - 0) + 0) / (4 * 3600)) < 1e-9
      or abs(f["E2_K"] - ((fair0 - mid0))) < 1e-9)
check("E5_K exact", abs(f["E5_K"] - ((mid1 - mid0) - (fair1 - fair0))) < 1e-12)
check("E6_K exact spread change", abs(f["E6_K"] - ((.59 + .45) - (.58 + .46))) < 1e-12)
check("E4 does not exist in the family", not any(k.startswith("E4") for k in f))
check("PM absent -> missing + indicator", f["E1_PM_ind"] == 1 and np.isnan(f["E1_PM"]))
# E3 censoring: venue stamps all BEFORE the last pin re-price -> censored at T*
ds_expected = np.median([(T - 4 * 3600 - 10) - (T - 4 * 3600 - 5) if False else 0])  # unused
f3 = FE.build_features(fx, T)
pin_re = [T - 4 * 3600 - 5, T - 60]
venue_st = [T - 4 * 3600 - 10, T - 120]
d1 = min([v for v in venue_st if v > pin_re[0]] + [T]) - pin_re[0]
d2 = min([v for v in venue_st if v > pin_re[1]] + [T]) - pin_re[1]   # none later -> T-censored
check("E3 right-censored median", abs(f3["E3"] - float(np.median([d1, d2]))) < 1e-9)
no_re = fx[fx.poll_ts < T]  # only the early pair remains
f4 = FE.build_features(pd.concat([no_re[no_re.sportsbook == "Kalshi"]], ignore_index=True), T)
check("E3 missing (no Pinnacle re-price) -> indicator, never zero",
      f4["E3_ind"] == 1 and np.isnan(f4["E3"]))
fr = FE.build_features(fx, T, mc2_p1=.55, mc2_recon=True)
check("A-O2: mc2_recon -> missing path + affected count",
      fr["logit_mc2_ind"] == 1 and np.isnan(fr["logit_mc2"]) and fr["mc2_recon_affected"] == 1)
check("A-O2: frozen mc2 used when clean", abs(f["logit_mc2"] - math.log(.55 / .45)) < 1e-9)

# ================================================================ 5. eval
rng = np.random.default_rng(7)
N_M, MONTHS = 40, 14
rows = []
for mi in range(MONTHS):
    t0 = pd.Timestamp("2026-11-01", tz="UTC") + pd.DateOffset(months=mi)
    for i in range(N_M):
        lf = rng.normal(0, 1)
        e1 = rng.normal(0, 1)
        key = ("t%d" % rng.integers(0, 6), t0.strftime("%G-W%V"))
        p = 1 / (1 + np.exp(-(lf + 0.8 * e1)))
        rows.append({"start": t0 + pd.Timedelta(hours=int(i)), "league": ["atp", "atp_challenger", "itf_men"][i % 3],
                     "K": key, "evaluated": i % 10 != 9,   # every 10th row is thinned (train-only)
                     "logit_fair": lf, "logit_mc2": lf + rng.normal(0, .3), "logit_mc2_ind": 0,
                     "E1_K": e1, "y": int(rng.random() < p)})
sim = pd.DataFrame(rows)
scored, folds = EV.walk_forward(sim, ["E1_K"])
check("eval: >= 6-month min train honored", folds[0]["month"] >= "2027-05")
check("eval: chronological walls (no training row postdates its wall)",
      all(f["max_train_start"] < f["wall"] for f in folds))
check("eval: thinned rows are never scored",
      len(scored) == len(sim[(sim.evaluated) & (sim.start >= folds[0]["wall"])]))
check("eval: thinned rows DO train (train counts include them)",
      folds[0]["n_train"] == len(sim[sim.start < folds[0]["wall"]]))
con = EV.contrasts(scored)
s1 = EV.cluster_bootstrap(con["H1"], scored["K"].values, seed=seed, B=400)
s2 = EV.cluster_bootstrap(con["H2"], scored["K"].values, seed=seed, B=400)
check("eval: planted E1 signal detected (H1 mean > 0, t > 2)", s1["mean"] > 0 and s1["t"] > 2)
# DE machinery
clus = np.repeat(np.arange(40), 25)
d_corr = np.random.default_rng(3).normal(0, .02, 1000) + np.repeat(
    np.random.default_rng(4).normal(0, .05, 40), 25)
sc = EV.cluster_bootstrap(d_corr, clus, seed=1, B=400)
check("DE: clustered data -> DE well above 1", sc["V_clust"] / sc["V_iid"] > 3)
check("DE: governing = max, floored at 1",
      EV.governing_de(.5, 1.0, .8, 1.0) == 1.0 and
      EV.governing_de(sc["V_clust"], sc["V_iid"], 1.0, 1.0) == sc["V_clust"] / sc["V_iid"])
try:
    EV.cluster_bootstrap(np.zeros(100), np.arange(100), seed=1, B=50)
    check("DE: s2=0 raises DataIntegrityAbort", False)
except EV.DataIntegrityAbort:
    check("DE: s2=0 raises DataIntegrityAbort", True)
try:
    EV.governing_de(1.0, 0.0, 1.0, 1.0)
    check("DE: zero iid variance input aborts", False)
except EV.DataIntegrityAbort:
    check("DE: zero iid variance input aborts", True)
vc1, vi1 = EV.variances_only(sc)
dec = EV.decide_extension(vc1, vi1, vc1, vi1, 5000)
check("blinding: extension decision exposes no mean/t/ci/roi/p-value",
      dec["extend"] and not any(k in dec for k in ("mean", "t", "ci95", "roi", "p_value")))
check("blinding: decide_extension accepts variances only (floats, not result dicts)",
      all(isinstance(v, float) for v in (vc1, vi1)))
dec2 = EV.decide_extension(1.0, 1.0, 1.0, 1.0, 9000)
check("blinding: no extension at effective n >= 8,000", not dec2["extend"])
# gates
check("gates: registered constants frozen",
      (EV.DEV_T, EV.DEV_FLOOR, EV.TIER_T, EV.TIER_FLOOR, EV.B_BOOT, EV.B_PERM,
       EV.CAL_LO, EV.CAL_HI, EV.MIN_TRAIN_MONTHS, EV.L2_C)
      == (3.0, 2e-3, 2.0, 1e-3, 2000, 200, 0.9, 1.1, 6, 1.0))
slope = EV.calibration_slope(scored["y"].values, scored["p_M2"].values)
check("gates: calibration slope near 1 on well-specified model", 0.7 < slope < 1.3)
check("gates: dev gate needs t>=3 AND floor AND slope",
      EV.dev_gate({"t": 3.1, "mean": 3e-3}, 1.0) and
      not EV.dev_gate({"t": 3.1, "mean": 1e-3}, 1.0) and
      not EV.dev_gate({"t": 2.9, "mean": 3e-3}, 1.0) and
      not EV.dev_gate({"t": 3.1, "mean": 3e-3}, 1.3))
perm = EV.permutation_check(sim, ["E1_K"], {"H1": s1["mean"], "H2": s2["mean"]},
                            seed=seed, B=12)
check("permutation: null centered at zero; true H1 above null p99",
      abs(perm["H1"]["null_mean"]) <= 3 * perm["H1"]["null_se"] + 1e-6 and perm["H1"]["pass"])

# ================================================================ 6. CI (F1)
s_ci = EV.cluster_bootstrap(d_corr, clus, seed=5, B=400)
rng_ci = np.random.default_rng(5)
idxm = {}
for i, k in enumerate(clus):
    idxm.setdefault(k, []).append(i)
uq = sorted(idxm)
grp = {k: d_corr[np.asarray(idxm[k])] for k in uq}
mns = np.empty(400)
for b in range(400):
    pick = rng_ci.choice(len(uq), size=len(uq), replace=True)
    mns[b] = np.concatenate([grp[uq[i]] for i in pick]).mean()
check("CI: percentile endpoints match an independent recomputation exactly",
      s_ci["ci95"] == (float(np.percentile(mns, 2.5)), float(np.percentile(mns, 97.5))))
check("CI: interval brackets the point estimate", s_ci["ci95"][0] < s_ci["mean"] < s_ci["ci95"][1])
flat = np.random.default_rng(11).normal(0.5, 1.0, 4000)
s_flat = EV.cluster_bootstrap(flat, np.arange(4000) % 400, seed=6, B=600)
width = s_flat["ci95"][1] - s_flat["ci95"][0]
check("CI: width ~ 2x1.96xsd/sqrt(n) on iid data", abs(width - 2 * 1.96 / np.sqrt(4000)) < 0.02)

# ================================================================ 7. exclusion taxonomy (G2)
tx = EL.exclusion_taxonomy
r = tx("2026-10-21T10:00:00Z", "2026-10-21T16:00:00Z")
check("taxonomy: exactly 6h reschedule NOT excluded (strictly greater rule)",
      r["eligible"] and "rescheduled_gt6h" not in r["labels"])
r = tx("2026-10-21T10:00:00Z", "2026-10-21T16:00:01Z")
check("taxonomy: 6h+1s reschedule excluded", not r["eligible"] and "rescheduled_gt6h" in r["labels"])
r = tx("2026-10-21T10:00:00Z", None)
check("taxonomy: missing actual start -> unverifiable, counted NOT excluded",
      r["eligible"] and "reschedule_unverifiable" in r["labels"])
r = tx("garbage", "2026-10-21T10:00:00Z")
check("taxonomy: malformed original start -> unverifiable, not silently fired",
      r["eligible"] and "reschedule_unverifiable" in r["labels"])
check("taxonomy: postponed excluded", not tx("2026-10-21T10:00:00Z", status="postponed")["eligible"])
check("taxonomy: void excluded", not tx("2026-10-21T10:00:00Z", status="void")["eligible"])
r = tx("2026-10-21T10:00:00Z", status="void", winner="p1")
check("taxonomy: void WITH winner -> status_contradictory, excluded pending review",
      not r["eligible"] and "status_contradictory" in r["labels"])
r = tx("2026-10-21T10:00:00Z", "2026-10-21T10:30:00Z", status="retired", advancing="p2")
check("taxonomy: retirement -> eligible, advancing player is the outcome",
      r["eligible"] and r["outcome"] == "p2")
r = tx("2026-10-21T10:00:00Z", status="retired", advancing=None)
check("taxonomy: retirement without advancing -> excluded unresolved",
      not r["eligible"] and "retirement_unresolved" in r["labels"])
r = tx("2026-10-21T10:00:00Z", "2026-10-22T10:00:00Z", status="postponed")
check("taxonomy: overlapping labels both recorded (postponed + rescheduled)",
      not r["eligible"] and {"postponed", "rescheduled_gt6h"} <= set(r["labels"]))
# taxonomy applies BEFORE N_pre: an excluded row must shrink the thinning denominator
tax_ok = [tx("2026-10-21T10:00:00Z", "2026-10-21T11:00:00Z") for _ in range(9)]
tax_bad = tx("2026-10-21T10:00:00Z", status="void")
pre = pd.DataFrame({"fixture_id": ["f%d" % i for i in range(10)],
                    "K": [("t", "2026-W43")] * 10,
                    "eligible": [t["eligible"] for t in tax_ok] + [tax_bad["eligible"]]})
cand = pre[pre["eligible"]]
_, info_tax = SA.thin(cand.drop(columns=["eligible"]), seed)
check("taxonomy: exclusions shrink N_pre (applied before the cap denominator)",
      info_tax["n_pre"] == 9)

# ================================================================ 8. RNG policy (approved)
import hashlib as _h
REG = SA.REG_SHA256
labels6 = SA.SEED_LABELS
vals = {L: SA.derive_seed(L) for L in labels6}
check("seed policy: derive_seed matches the approved formula for every label",
      all(vals[L] == int(_h.sha256((REG + "|" + L).encode("utf-8")).hexdigest()[:16], 16)
          for L in labels6))
check("seed policy: six labels, all distinct, none equal to the thinning root",
      len(set(vals.values())) == 6 and seed not in vals.values())
check("seed policy: thinning root unchanged by the policy",
      SA.seed_from_bytes(registered_blob()) == int("7539adbbafc84d22", 16))
try:
    SA.derive_seed("boot:unregistered")
    check("seed policy: unknown label refused", False)
except ValueError:
    check("seed policy: unknown label refused", True)
check("seed policy: streams differ (first draws distinct across labels)",
      len({np.random.default_rng(v).integers(0, 2**63) for v in vals.values()}) == 6)

# ================================================================ 9. feature span/N4 gaps
T2 = T
fx_short = pd.DataFrame([
    q("Pinnacle", "p1", .60, T2 - 3600, T2 - 3600 - 5),
    q("Pinnacle", "p2", .44, T2 - 3600, T2 - 3600 - 5),
    q("Kalshi", "p1", .58, T2 - 3600, T2 - 3600 - 10),
    q("Kalshi", "p2", .46, T2 - 3600, T2 - 3600 - 10),
    q("Pinnacle", "p1", .62, T2, T2 - 60),
    q("Pinnacle", "p2", .42, T2, T2 - 60),
    q("Kalshi", "p1", .59, T2, T2 - 120),
    q("Kalshi", "p2", .45, T2, T2 - 120),
])
fs = FE.build_features(fx_short, T2)
check("E2: <2h observed span -> missing + indicator", fs["E2_K_ind"] == 1 and np.isnan(fs["E2_K"]))
check("E5: <2h common span -> missing + indicator", fs["E5_K_ind"] == 1 and np.isnan(fs["E5_K"]))
check("E6: <2h span -> missing + indicator (endpoint rule subsumed)",
      fs["E6_K_ind"] == 1 and np.isnan(fs["E6_K"]))
check("E1 still present on the short span (no span requirement at T*)", fs["E1_K_ind"] == 0)
fx_oneside = pd.concat([fx[fx.sportsbook == "Pinnacle"],
                        fx[(fx.sportsbook == "Kalshi") & (fx.selection == "p1")]],
                       ignore_index=True)
fo = FE.build_features(fx_oneside, T)
check("N4/E6: venue never two-sided -> every Kalshi feature missing",
      all(fo["%s_K_ind" % e] == 1 for e in ("E1", "E2", "E5", "E6")))

# ================================================================ 10. reports + N1 guard (G3)
import opp1_report as RP
kept_r = kept1.copy()
kept_r["start"] = pd.Timestamp("2026-11-03T10:00:00Z")
kept_r["league"] = "atp"
lab_lists = [["ts_naive_interpreted"], ["validation_pending"], ["ambiguous_linkage"],
             ["metadata_incomplete"], ["void", "status_contradictory"], []]
er = RP.exclusion_report(lab_lists)
check("report: per-label exclusion counts correct and zero-filled",
      er["ts_naive_interpreted"] == 1 and er["validation_pending"] == 1
      and er["status_contradictory"] == 1 and er["rescheduled_gt6h"] == 0)
RP.assert_post_thinning(kept_r, info1)
check("N1 guard: accepts the genuine post-thinning set", True)
try:
    RP.assert_post_thinning(df30.assign(start=pd.Timestamp("2026-11-03T10:00:00Z"),
                                        league="atp"), info1)
    check("N1 guard: rejects the unthinned set", False)
except AssertionError:
    check("N1 guard: rejects the unthinned set", True)
try:
    RP.assert_post_thinning(kept_r.assign(evaluated=[True] * (len(kept_r) - 1) + [False]), info1)
    check("N1 guard: rejects non-evaluated rows", False)
except AssertionError:
    check("N1 guard: rejects non-evaluated rows", True)
ar = RP.accrual_report(kept_r, info1, lab_lists)
check("report: accrual report = pure counts + thinning + shares + exclusions",
      not ar["counts"]["meets_dev_minimums"] and ar["thinning"]["cap_size"] == 3
      and ar["per_key_shares"]["den"] == 9)
fdf = pd.DataFrame([dict(f, league="atp"), dict(fr, league="atp"),
                    dict(f4, league="itf_men")])
cov = RP.coverage_staleness_report(fdf)
check("report: N5 coverage has numerator AND denominator on every percentage",
      cov["atp"]["features"]["E1_PM"]["missing_n"] == 2
      and cov["atp"]["features"]["E1_PM"]["den"] == 2
      and cov["atp"]["quote_age"]["K"]["median_s"] is not None)
check("report: mc2 recon count", RP.mc2_recon_report(fdf)["mc2_recon_affected_n"] == 1)
check("report: kalshi-only subset filters to _K columns",
      RP.kalshi_only_cols(["E1_K", "E1_K_ind", "E1_PM", "E3", "E5_PM_ind"]) == ["E1_K", "E1_K_ind"])
ko = RP.kalshi_only_readout(sim, ["E1_K"], SA.derive_seed("boot:dev"))
ab = RP.e3_ablation_readout(sim, ["E1_K"], SA.derive_seed("boot:dev"))
check("report: kalshi-only + E3-ablation run and stay NON-GATING",
      ko["non_gating"] and ab["non_gating"] and "H1" in ko and "H1" in ab)
rr = RP.results_report(cov, er, RP.per_key_share_table(kept_r), RP.mc2_recon_report(fdf),
                       {"H1": {"t": s1["t"]}}, {"kalshi_only": ko})
check("report: results structure puts coverage before any metric",
      list(rr)[0] == "1_coverage" and rr["6_non_gating_readouts"]["kalshi_only"]["non_gating"])

print("\n%d passed, %d failed" % (len(PASS), len(FAIL)))
if FAIL:
    print("FAILED:", *FAIL, sep="\n  ")
sys.exit(1 if FAIL else 0)
