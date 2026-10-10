# Goalserve tennis trial — request to send

**To:** Goalserve support (Contact Us form at goalserve.com, or support@goalserve.com)
**Subject:** Tennis API 30-day trial + one question on match statistics fields

---

Hi,

I'd like to take the free 30-day trial of the Tennis package.

Before that, one specific question that determines whether the feed fits my use case. I need
**per-match unforced errors and winners** for each player, and I specifically need them for
**WTA Tour main-draw singles** (WTA 250 / 500 / 1000 and Grand Slams).

Could you confirm:

1. Does the tennis feed include an **unforced errors** field per player per match? If so, what is
   the field/tag name?
2. Is it **actually populated** for WTA Tour main-draw singles matches, or is it present in the
   schema but usually empty? I'm asking because another provider documents the field and returns
   null for every match I tested, at every level.
3. Same two questions for **winners**.
4. Which feed/resource path carries match statistics? Your public live-score sample shows only
   scores and set results, so I couldn't tell from the samples page.
5. Is historical data available for completed matches (2024 onwards), or is the stats feed
   live/in-play only?

If it helps, a single sample response for any completed WTA Tour singles match showing the stats
block would answer all of the above at once.

Thanks,
Anthony

---

## Why these five questions

- **(1) and (3)** — the field has to exist at all.
- **(2) is the one that matters most.** The RapidAPI "Tennis API ATP WTA ITF" feed documents
  `player1Stats.unforcedErrors` as "unforced errors (where tracked)" and returned **null on 21 of
  21 matches**, including the Shanghai Masters and the China Open. A documented field is not a
  populated field, and that is the mistake to avoid paying for.
- **(4)** — their public samples (live score, odds, player profiles, rankings) contain no
  statistics fields whatsoever, so the stats resource is undocumented publicly.
- **(5)** — a live-only feed cannot backfill history, so the lane could only widen going forward
  rather than being re-validated on 2024-26.

## Pricing, for reference
Tennis package: **$150 / month**, ~$900-1,000 / 6 months, **$1,200 / year**. Free 30-day trial.
Coverage advertised: ATP, WTA, Challenger, ITF, Grand Slams, Davis/Fed Cup, juniors.

## What happens when the trial token arrives
Put it in `backend/.goalserve_key` (gitignored — never paste it into a command or a chat), then:

    cd backend && venv/Scripts/python.exe _goalserve_probe.py

That walks the candidate feed paths, dumps every field name, and reports whether anything
error-or-winner-like exists and is populated. If it is, the ingest merges into `tennis_ue` the
same way `manual_ue.csv` already does, so the 🧤 lane widens with no model change.

## What this is worth if it works
The women's unforced-error dog edge is a **WTA-tour** edge: **+10.8% (n=276)**, positive 2024
(+4.3%), 2025 (+13.6%) and 2026 (+12.5%) — against **−0.4%** for every charted dog in the same
band and level, so the gate itself supplies the whole lift. We currently have both players
charted on only **47%** of WTA-tour + slam women's dogs at +100..+250. Full tour coverage roughly
**doubles the lane: ~19 picks a month instead of ~9.**
