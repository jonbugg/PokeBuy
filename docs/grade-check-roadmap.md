# Grade Check: what "perfect" looks like

The goal: put a card on the scanner and know, before paying a grading fee, what it will most likely grade at each company, why, and whether grading it makes money.

Status key: **Built** (working now) · **Next** (high value, clear path) · **Later** (bigger projects or needs new hardware/data).

## 1. Capture

| Feature | Status | Notes |
|---|---|---|
| Drive the HP ENVY directly over Wi-Fi (eSCL), 600/1200 dpi | Built | No drivers or apps needed |
| Printable two-sheet guide (frame + cover), black and grey versions | Built | Grey for black-bordered cards |
| Quick preview that finds the guide and card, then scans only that area | Built | Handles mixed frame/cover combinations |
| Guided steps: front, back, front 180°, back 180° | Built | |
| Square-window guide + 90°/270° scans for a TAG-style grey "relief" surface map | Later | 4 light directions = photometric stereo, like TAG |
| Multi-card guide (2–4 windows) and batch scanning | Later | Scan a binder page's worth at once |
| Phone-camera capture as a fallback (with an angled light sweep) | Later | Lower accuracy than the scanner |
| Automatic dust check before the long 1200 dpi pass | Next | Use the preview to warn about specks on the glass |

## 2. Measurement accuracy

| Feature | Status | Notes |
|---|---|---|
| Centering to ~0.1 point repeatability (front), ~1 point (soft-edged backs) | Built | Checked by re-scanning after turning the card |
| Size to ~0.01" | Built | Matches TAG's DIG dimensions |
| Edge whitening judged against each card's own normal rim | Built | |
| Chips detected as backdrop showing inside the card's ideal edge | Built | Immune to silver artwork that matches the backdrop |
| Artwork-at-edge detection (silver foil, white panels) so it isn't called wear | Built | Traces each pale shape; >0.8 mm deep = artwork |
| Black-bordered cards: grey guide; edge tracer fallback on the black guide | Built | Corners/edges on black holo borders still need more real examples |
| Surface check from the 180° pair, with dust/lint told apart | Built | |
| Second-scan cross-check: findings missing from the 180° scan shown as "cleared" | Built | |
| Average front + 180° centering automatically and report the spread | Next | Tighter numbers and an honest ± |
| Learn per-scanner light direction to sharpen the edge-rim baseline | Next | |
| Surface relief map (4 rotations) to find dents, roller lines, print lines | Later | Needs the square-window guide |

## 3. Grading knowledge

| Feature | Status | Notes |
|---|---|---|
| PSA and CGC centering limits from their published standards | Built | |
| TAG ladder fitted from 106 public TAG DIG reports (centering + DINGS per grade) | Built | `scripts/calibrate_tag.py`; refits as more reports arrive |
| TAG-style Fray / Fill / Angle sub-scores per corner and edge | Built | Estimates on TAG's 1000-point style |
| Grade odds per company (not just one grade) | Built | Monte Carlo over centering wobble and borderline findings |
| Fit TAG sub-score formulas from TAG's own corner/edge numbers | Next | We have Fray/Fill/Angle for every report collected |
| Beckett (BGS) once its limits can be verified | Later | |
| Self-calibration from your own graded results | Next | Results are now recorded; use them to tune thresholds |

## 4. Money

| Feature | Status | Notes |
|---|---|---|
| Identify the card from its scan (OCR of the number + image match) | Built | Pokémon TCG API; search box as fallback |
| Raw market value (TCGplayer) | Built | |
| Graded values filled from eBay listings for the exact card, grader and grade (Browse API) | Built | `src/grading/market.py`; lower quartile of asking prices |
| Real sold prices: last sale, 30-day average, 90-day sold history chart and list per grade, TAG included | Built (needs key) | Add a free CompsAPI key as `COMPSAPI_API_KEY` in `.env` (100 lookups a month) |
| Fee tiers from TAG, PSA, CGC sites; cheapest tier that covers the value | Built | `src/grading/fees.py` |
| Expected profit per grader and a "best bet" recommendation | Built | |
| Accepted Best Offer prices (real price, not the listing price) | Next | CompsAPI `best_offer=1` once a key is in place |
| Submission planner: pick which cards to send where, meet bulk minimums | Next | e.g. TAG Value needs 10 cards |
| Connect to PokeBuy's deal finder: "buy raw, grade, sell" opportunities | Later | Use the same odds on listing photos |

## 5. Library and records

| Feature | Status | Notes |
|---|---|---|
| Every card saved with scans, close-ups, report, date | Built | |
| Name, identified card, values, actual graded result | Built | |
| Accuracy tracker (estimate vs actual) | Built | |
| CSV export; print / save report as PDF | Built | |
| Re-check a card later and compare (did it get worse?) | Later | |
| Share link / read-only report for buyers | Later | |

## 6. Experience

| Feature | Status | Notes |
|---|---|---|
| TAG DIG-style report, logos, colour-coded findings, zoom viewer with both scans locked | Built | |
| One-click "scan everything" (front → flip prompt → back → 180°s) with voice/sound cues | Next | Fewer clicks per card |
| Phone-friendly view of the library | Next | |
| Run as a small always-on app (menu-bar or launchd) | Later | |
