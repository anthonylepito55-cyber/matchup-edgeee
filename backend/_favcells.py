"""Combined LIVE record of every favourite-side cell vs every dog-side cell, straight from
tennis_log's own lane study -- the question being whether 'five favourite cells failed live'
is a real signal or just five small samples."""
import tennis_log as TL

st = TL.study() if hasattr(TL, "study") else None
if st is None:
    for nm in ("lane_study", "build_study", "lanes", "compute_study"):
        if hasattr(TL, nm):
            st = getattr(TL, nm)()
            break
if isinstance(st, dict) and "study" in st:
    st = st["study"]
print(f"lanes available: {len(st)}")

FAV = ["ce5_deep_fav", "pf_ghfav", "pf_ghfav_pr", "pf_c75fav_pr", "pf_a10fav_pr",
       "fav_value", "p_fav", "cgf_shallow_fav", "cgf_premium", "c75fav_formfade",
       "cr5_coll_leanfav", "fadegold_pocket_w", "p_close"]
DOG = ["p_dog", "p_dog_flip", "x_dog", "c75_dog_100plus", "d_gray_dog", "lowerr_dog_w",
       "allround_dog_w", "allround_dog_w_big", "returner_dog_w", "pink_mc2_dog"]


def block(names, label):
    tn = tw = 0
    ts = tp = 0.0
    print(f"\n{label}")
    print(f"   {'lane':24s} {'rec':>9s} {'hit':>7s} {'ROI':>8s} {'profit':>9s}")
    for k in names:
        v = st.get(k)
        if not isinstance(v, dict) or not v.get("n"):
            continue
        n, w = v["n"], v.get("wins", 0)
        s = v.get("staked_usd") or 0.0
        p = v.get("profit_usd") or 0.0
        tn += n
        tw += w
        ts += s
        tp += p
        print(f"   {k:24s} {f'{w}-{n - w}':>9s} {100 * w / n:6.1f}% "
              f"{v.get('roi_pct', 0):+7.1f}% {p:+9.2f}")
    print(f"   {'-' * 62}")
    print(f"   {'COMBINED':24s} {f'{tw}-{tn - tw}':>9s} {100 * tw / max(tn, 1):6.1f}% "
          f"{100 * tp / max(ts, 1):+7.1f}% {tp:+9.2f}   on ${ts:.0f} staked")
    return tn, tw, ts, tp


fn, fw, fs, fp = block(FAV, "FAVOURITE-SIDE CELLS (live, frozen log)")
dn, dw, ds, dp = block(DOG, "DOG-SIDE CELLS (live, frozen log)")
print(f"\n>>> favourite cells {fn} settles at {100 * fp / max(fs, 1):+.1f}% "
      f"| dog cells {dn} settles at {100 * dp / max(ds, 1):+.1f}%")
