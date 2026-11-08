# Overnight work on Grade Check (Nov 7 → 8)

Nothing here is committed yet. Everything was checked against TAG's graded copies and re-run on every scan
you've saved (`scripts/qc_scans.py`), and the main checks are listed at the bottom.

## Needs you in the morning
- **Mega Darkrai ex: rescan the back turned 180°.** The "180°" back scan you did was the same way up as the
  first back scan (the standard Pokémon back looks almost the same upside down, and the app's check let it
  through). It threw off the back's surface check and its centering. I moved it aside to
  `data/scans/20261107-221551-c9f05a/.deleted/` (not deleted). The app now refuses this mistake.

## Fixed tonight
### Card finding and scanning
- **Cut-off scans:** a new card no longer reuses the sideways scan area left from the last card's 90°/270°
  scans (that's what cut the Mega Charizard X off). A scan whose area points the wrong way finds the card again.
- **Gold cards on red paper:** the app took a gold card for the paper. It now reads the paper colour from the
  edge of the scan.
- **180° scans the same way up:** caught now on card backs too (see above).

### Centering
- **Etched gold borders** (Mega Darkrai): the border changes tone along its length; it no longer reads as artwork.
- **Cross-hatched mesh borders** (Mega Charizard X): smoothed across the border before finding its edge.
- **Copyright line inside the border** ("©2025 Pokémon / Nintendo…"): no longer mistaken for the border's edge.
- Checked on 284 TAG card sides: within 2 points of TAG 83% (unchanged), within 1 point 61% (was 59%), 4 more
  sides measured.

### Corners and edges
- **"Chips" that were really the cut:** an edge cut a hair narrow over 10+ mm read as a long chip. Chips are now
  judged against the edge around them; a short bite still counts, and a deep one counts in full.
- **Corner wear vs the cut:** each corner is now measured against where its two neighbouring edges actually run.
  The Mega Darkrai's sides are cut ~0.15 mm narrow over the top 15–20 mm, and that showed up as ~0.2 mm of "wear"
  on both top corners. (I tried giving each corner its own curve first; it was unstable and was dropped.)
- **"Corner bent / lifted" needs more:** a corner sticking *out* past the ideal curve is almost always the cut on
  a flat scan (a bent corner lifts off the glass, it doesn't grow sideways), so it now needs 0.20 mm for yellow and
  0.30 mm for red. Missing material (wear) keeps the old, more sensitive limits (0.12 / 0.20 mm).
- **Your decision to check:** a *red* call that **none of two or more other scans** saw is now cleared (blue), not
  counted as borderline. With only the 180° scan to go on it still counts as borderline, as you asked earlier. This
  cleared the Mega Darkrai's "whitening" along its bottom edge (the gold etching's bright lines reach the cut edge
  and read as whitening under one light only). To undo: `grade_app.py`, search for `n >= 2`.

### Surface
- **Etched gold design read as dents:** the raised edges of a gold card's design shade differently from each
  side, like a dent. Print edges that are a change of colour (gold stripe against gold texture) are now damped
  like brightness edges. Mega Darkrai front: 20 marks (15 red) → 1 (not red). Other cards unchanged.
- **Surface check with only the 90°/270° pair:** it now runs on whichever opposite pair of scans exists.
- **Tiny faint specks** (under 0.5 mm and barely over the line) are listed but not counted: on dot-printed areas
  like the blue back, the print's dot pattern lines up a hair differently between two scans and leaves specks.
- **Holo sparkle** (a bright point in *both* scans, just brighter in one) is listed but not counted. That was the
  one red mark on Lance's Charizard V (a real PSA 10).
- Panels from the 90°/270° pair are now labelled as such (they said "180°").

### Relief map (TAG-style surface map)
- **Looks like TAG's now:** flat card sits at mid grey, ridges lighter and darker. Before, it was washed out.
- **Overlay slider:** fade between the card photo and the surface map, like the slider on TAG's report.
- **Built from 2, 3 or 4 angles**, with a note on how many and what that means.
- Compared with TAG's own surface maps of the same card (Mega Darkrai 10 and 9): theirs show the fine etching
  more crisply; ours shows the same raised design. Some printed colour still shows through ours (inks differ in
  gloss); converting to linear light didn't help, so that idea was dropped.

### Close-ups
- **Every angle in the zoom:** clicking a finding shows every scan of that side (first, 180°, 90°, 270°), in a
  2×2 grid for four.
- **Surface marks open in the same zoom** instead of a fixed two-image picture.

### App
- **Scan status bar** on every page, with a link back to the card; leaving mid-scan no longer loses it.
- **Progress bar follows the real steps** (scanning, receiving the image, measuring) and learns your printer's
  timings.
- **Saved reports open instantly** (0.02 s instead of ~35 s).
- **Library lists cards** even when you left before the report was built.
- **Library:** long "also scanned N more times" lists fold away behind a toggle (the Crown Zenith Pikachu had 16
  test scans listed).
- **A report could fail to draw** when centering found only some borders (it tried to print a missing number).
  Fixed in the centering panel and the DINGS map.
- **Cleared findings** now say which scans cleared them ("Not in any of the 3 other scans: 180°, 90°, 270°").
- **"Scanner busy" right after the preview:** the app waits it out.

## What I learned about the surface check (important)
I painted fake scratches and dents onto clean scans (`scripts/surface_fake_test.py`) to see what it catches.
**It mostly doesn't catch them.** It finds dust, lint and sharp specks well, and it found the faint marks we've
seen, but:
- It compares scans lit from different sides, so it sees things whose shading *changes* with the light. A fine
  scratch in the gloss scatters light the same way from every side (the hairline on your Charizard's border looked
  identical in all four scans), so it's largely invisible to this check by design.
- Anything wider than about 0.3 mm (a 1 mm dent) is removed with the scanner's gradual lighting before comparing.
- On textured full arts the card's own texture is louder than a faint scratch.
- I tried four changes to improve this; each found a little more and also put false marks on clean cards, so
  they're all switched off again (settings at the top of `src/grading/surface.py`).

What would work better: a separate **scratch check** that looks for thin lines present in *every* scan, on areas
where the print is plain (borders first). I prototyped it (`scripts/border_lines_prototype.py`): it finds real
things (a ~1.5 mm curved line on your Charizard ex back's top border, which is either a scratch or a fibre stuck to
the card; the faint hairline near its top-right corner) but also 30-70 false lines per card along the cut edge, so
it isn't wired in. And for **dents**, the relief map is the right tool (it keeps 1-3 mm shapes); turning relief
anomalies into findings is the next step. Until then: treat "no surface marks" as "no dust, specks or sharp marks",
not "no scratches", and use the relief map and its slider to look.

## Grade rules vs TAG
- The rules (centering + DINGS -> TAG grade) were fitted on 106 TAG reports; we now have 231. Tested fairly (each
  card predicted by rules fitted without it), refitting on all of them did **not** improve accuracy (51% exact /
  78% within half a grade, vs 55% / 80% now), so the rules are unchanged. `scripts/calibrate_tag.py` can now read
  every harvested report for when we have more.
- Predicting TAG's 1000-point score from centering and DINGS counts was much worse (28% exact): TAG's score depends
  on how bad each defect is, not how many.
- **Fixed a harvest mistake:** three Mega Darkrai copies were saved as "9.5" (scores 984–987, above the "10" at
  950). The harvest session checked TAG's report: they're **10 Gem Mint**. It had asked TAG for "9.5" copies, TAG
  has no such grade and returned 10s. Corrected in both Darkrai ladder files (with a note on each). The harvest
  session also warned that its per-grade *population* counts can overlap between grade pages, so don't trust those
  counts. TAG's own report says 97 Mega Darkrai graded, 28 of them Gem Mint.

## Your cards: before and after tonight
Every saved scan was re-measured from its original image (`scripts/reprocess_all.py`; each scan's previous result
is kept next to it as `<slot>.json.prev`) and every report rebuilt.

| Card | TAG / PSA / CGC before | after | what changed |
|---|---|---|---|
| Pikachu · Crown Zenith 160/159 | 10 / 10 / 10 | 10 / 10 / 10 | – |
| Lance's Charizard V (slab) | 10 / 10 / 10 | 10 / 10 / 10 | – |
| Lance's Charizard V (out of slab, real PSA 10) | 9 / 9 / 9 | 10 / 10 / 10 | a holo sparkle no longer counts as a mark |
| Charizard ex SVP 074 | 9 / 9 / 9 | 10 / 10 / 10 | false chips/corner flags gone; your ignore on the bottom-right corner applies again; 2 yellows left |
| Pikachu ex 30th Celebration | 10 / 10 / 10 | 10 / 10 / 10 | – |
| Mega Darkrai ex | below 8 / 7 / 7 | **9** / 10 / 10 | etched gold no longer read as wear and dents; 9 because the back centering (56.6/43.4) is just past TAG's usual 10 limit. TAG's 4 copies at 10 include one at 57/43 on the back, so the TAG comparison says 10 |
| Mega Charizard X ex | 9 / 9 / 9 | 10 / 10 / 10 | false chips gone; bottom border now found |

**Is it now too generous?** Five of seven are 10s, so I checked against TAG's graded copies
(`scripts/validate_on_tag.py`, which measures TAG's own photos as if they were scans; only 20 of 31 copies can be
measured from TAG's photos, so it's a small test). Tonight's rules vs before: exact grade 7/20 both, within half a
grade 12 vs 11, too harsh 6 vs 9, too generous 7 vs 4. Of the 3 new "too generous", two are Pristine-vs-Gem-Mint
10s. The third is a TAG 8.5 (V8089467, TAG noted edge wear) that we now call a 10: before, four corner "bent/lifted"
readings sank it, but TAG didn't flag any corner, so the old 8.5 was right for the wrong reasons. Its real edge wear
isn't detected by either version, which is a gap.
**Bottom line:** the corner/edge checks are now fairer, and the surface check is the weak spot (see above). A 10
from the app means "no corner, edge, centering or obvious surface problem found", not "proven 10".

## Still open
- **Rescan the Mega Darkrai back at 180°** (see the top).
- **Scratch check** (thin lines in every scan): prototype in `scripts/border_lines_prototype.py`, needs work.
- **Dents from the relief map:** turn relief anomalies into findings; the surface check can't see 1 mm+ dents.
- **Edge wear on TAG's photos** isn't caught (V8089467). Worth a look with our own scans of a worn card.
- **The four oldest test scans** (Nov 7, 12:28–12:38, 3400×3400 px with no resolution recorded) can't be
  re-measured; they're only in the library as "earlier scans" of the Crown Zenith Pikachu, so you may want to remove
  them there.
- **Scan progress:** the printer sometimes reports "not busy" for a moment as a scan starts; the app now waits for
  it to say so twice in a row before showing "Receiving the image". Not yet checked on a real scan.

## Tools added tonight
- `scripts/qc_scans.py snap NAME` / `diff OLD NEW`: re-measure every saved scan and list what changed.
- `scripts/reprocess_all.py`: re-measure every saved scan and rebuild every report (keeps the old results).
- `scripts/surface_fake_test.py <session> [side]`: paint fake scratches and dents and see what the surface check finds.
- `scripts/border_lines_prototype.py`: the scratch-check prototype.
- `scripts/centering_bench.py` now skips a TAG photo it can't read instead of stopping.

## How to undo a piece
Each change has a switch near the top of its file:
- `src/grading/closeups.py`: `LOCAL_CHIPS`, `LOCAL_CORNER_EDGES`, `CORNER_OUT_YELLOW_MM` / `CORNER_OUT_RED_MM`.
- `src/grading/surface.py`: `COLOUR_EDGES`, `FAINT_MM` / `FAINT_STRENGTH`, `SPARKLE_MM` / `SPARKLE_RISE`.
- `grade_app.py`: `CODE_STAMP` (bump it after changing grading code so saved reports rebuild once); `n >= 2` for
  the cleared-red rule.
After changing a corner/edge setting, run `scripts/reprocess_all.py` so saved cards pick it up.
