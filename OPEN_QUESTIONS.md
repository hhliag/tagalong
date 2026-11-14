# Open questions and decisions

Where DESIGN.md was unclear, the simplest option was chosen and written here. Change any of these by editing DESIGN.md. Tidied 14 Nov 2026: superseded entries removed, the rest grouped by topic.

## Still open (owner's call)

1. **English for judges.** Steps and part names stay in the manual's language (Chinese for the Kovital manual), because translating would be generating. An English version would need a translation step, clearly marked as such. Not built.
2. **Shared ✓/✗ decisions.** Label decisions and pin moves are stored on the server (`data/state/<chair>.json`), so every viewer sees and changes the same ones. Per-phone decisions would have to move to the browser.
3. **Photos are served full size** (5–7 MB each), slow on phones over a tunnel. Resized copies were offered.
4. **E100 library and device JSON** (`library/kovital-kv-e100.json`, `devices/chair-a.json`) are not committed. §9 allows short quotes in the repo.
5. **Step-done pages "chosen" and "built"** have no QR any more; they could be dropped so the only in-between page is the passport QR.

## Pages and flow

6. **Step bar** (1 Choose chair, 2 Build passport, 3 Confirm, 4 Passport) on /, /build, /confirm, /passport, /uses/* and the step-done pages. Not on /print, /manual, /crew or /crew/<tag> (the crew's lookup is not part of the owner's steps). Done / current is by page position, not saved progress; /uses/* count as step 4. Done steps link back; on / there is no chair yet, so nothing links.
7. **Step-done pages** `/done/<chair>/<chosen|built|confirmed>`. A step counts as done: "chosen" always; "built" once the label stage has run (`label` in the chair's `stages`); "confirmed" when no label is pending. Otherwise the page redirects to /build or /confirm. /build shows "Continue →" only after the last stage ticks; no automatic jump.
8. **Summary values** come from the files. Chosen: make + model once the plate stage has run, else "Model not read yet" (same rule as the picker). Built: number of steps; `record.quotes` verified / total (left out when the record has no counts, as in the hand-written record); distinct parts with at least one dot on a photo. Confirmed: confirmed dots and zone markers · rejected ones as "hidden".
9. **The passport QR** is only on the "confirmed" page, between /confirm and /passport: it is what the ramp handler scans. It opens the crew view `/crew/<tag>`, the same QR as the printed card (DESIGN §6 said `/passport`). Base URL: `PUBLIC_BASE_URL`, or the older `PUBLIC_URL`, else the address the request came in on (proxy headers trusted, so `https` through a tunnel is kept).
10. **?fast=1.** Flow links (picker, /build "Continue", /confirm "Done", step bar) go straight to the next page and keep `?fast=1`; a /done link with it redirects after the guard. Other links do not carry it.
11. **Crew lookup** (asked for in chat, not in DESIGN). `/crew` takes a tag ID (case and spaces ignored); `/crew/<tag>` shows how to hold, photos, must do, battery and size, IATA lines. Scanning uses the phone's camera app. §10's "inspector page" is out of scope; this is a read-only view of the same record.
12. **Manual page links.** `/manual/<record>/<page>` is a stub: it lists the quotes cited on that page and marks the one for `?step=`. No page image; `manual.url` is null until `sources.yaml` exists.
13. **Concept chip on the print** is hidden on paper; the sheet header reads "Wheelchair passport · Concept". Missing photos show a placeholder SVG.
14. **Build page.** M1 stages return saved results; the browser waits 0.7 s per stage so the ticks show. When the manual is in the library, extract and verify show as skipped (no `/api/extract`).

## Confirm page

15. **Tap the rings, no list.** Tap cycles grey (pending) → green (confirmed) → red (rejected) → grey. Red rings stay visible on /confirm so the owner can undo; every other page shows confirmed labels only. A legend above the photos names each letter and zone. A zone whose part is on no photo gets a tap chip under the photos.
16. **"Check all"** turns every ring, zone marker and chip green in one call, including red ones.
17. **Dragging a ring** saves its new centre (clamped to the photo, `moved: true`); a zone box moves with it. Status does not change. Under 6 px of movement counts as a tap. The pipeline PNGs and REPORT.md do not see moves.
18. **Colours show the owner's decision.** Zone rings are grey / green / red too; their badge says "Lift" (round) or "No" (square). Passport, print and crew keep green hold / red no_hold.
19. **Bigger layout on /confirm only:** up to 1200 px wide, 2 photos per row (1 under 760 px), 44 px rings with 32 px badges.
20. **Relabelling clears decisions.** The label stage deletes `data/state/<chair>.json`, since old decisions were about old labels. `python -m app --reset` also clears them.

## Labels, pins and zones

21. **A dot on every photo where a part shows,** one per instance (both levers, both footrests), same letter per part; each dot is confirmed on its own (`id`; older records use `n`). Minimum confidence 0.5; lower detections stay in REPORT.md only. The label prompt says to ignore wheelchairs in the background.
22. **Letters** come from `n` at display time (1 → A, 27 → AA); steps are numbered 1, 2, 3 through the Must do list. A step whose part has no shown label gets a chip with the part name only.
23. **Pins** are hollow rings with the letter in a badge outside: 3% of the short side in the PNGs, 14 px on the web pages (bigger on /confirm). `app.view.pin_sides` picks the badge side for both: the first of up-right, up-left, down-right, down-left that stays inside the photo, preferring the most room. Web markers are HTML; PNGs are drawn with Pillow (check and cross as lines).
24. **Zones.** Each verified hold / no_hold zone gets a marker on every photo where its part shows (`zone`, `zone_id`, `box`), numbered after the part labels so the same API works. Boxes are outlines (solid green / dashed red). A zone is on the passport when at least one of its markers is confirmed; the pipeline's card.html shows pending ones. Parts the handling stage adds get normal part labels too.
25. **"The manual gives no lifting points. Ask the owner."** shows when no verified hold zone exists, also when there are no_hold zones.
26. **Trust chips.** Verified steps show `AI-extracted · page verified`; `Owner-confirmed` is added when a label of that step's part is confirmed.

## Pipeline

27. **Stages** `pages → extract → handling → figures → label → render`, each reading the previous file in `out/<chair>/`. Rerun handling and figures after extract (`--stage all` does). Dropped zones and conflicts stay in `out/<chair>/handling.json`.
28. **Folders.** Hand-written records live in `app/fixtures/`; `library/` and `devices/` hold pipeline output and win per id. `out/` and `saved/` are gitignored (full manual text, our photos). `--freeze` and `sources.yaml` are not built; the manual comes from `meta.yaml` (`manual`, optional `manual_url`). New chair fields from `meta.yaml`: `tag_id`, `battery_original`, `removed_parts`.
29. **Page scoring.** Rank by distinct keywords, then total matches; English and Chinese (Traditional and Simplified) keywords, on normalised text. Pages with no keyword are never kept. Spec page = the page with the most spec terms.
30. **What code fixes in the LLM's answer.** Steps without a quote are dropped; unknown `phase` → `before_loading`, unknown `safety` → `comfort`, unknown `part_id` → null; ids renumbered s1..sn; "25.2 V" → 25.2, "yes"/"no" → booleans. `must_do` is decided by code: freewheel / power-switch parts, and power off, its check, or securing in the action or quote; at most 8.
31. **Verifier.** NFKC, quotes, dashes, hyphen breaks; whitespace next to CJK characters is dropped (PDF line breaks split Chinese sentences); `partial_ratio` ≥ 90.
32. **Language.** Quotes, actions and part names stay as the manual writes them; fact values are short English for the §5 rules.
33. **Figures** (own stage, before label). A caption index joins split captions ("圖" + "4.1"); the figure is the nearest image or drawing above the caption. A step gets (1) its `figure_ref` from the index, else (2) one vision call that only names a caption on the cited page (chip "Figure matched by AI"), else (3) the whole page (chip "Whole page"). Print shows figures only with at most 4 must-do steps. List markers ("1.", "2、", "①") are stripped for display only.
34. **Photos for the LLM** are resized to a 1024 px long side (EXIF transposed) in `out/<chair>/resized/`. Card photos are JPEG data URIs.
35. **LLM settings.** No default model: `gemini`, `anthropic`, `openai` need `LLM_MODEL`; no `LLM_PROVIDER` = `offline` (requests `<stage>_<n>` in call order; bad JSON in a response stops the run). Gemini on Vertex AI uses `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION` and the gcloud login. Calls take 40–60 s: use `STAGE_TIMEOUT=180`.

## Rules (DESIGN §5)

36. **Battery removal** is read only from the chair's `removed_parts`: null = unknown (WCLB or WCLX, "Confirm at check-in"); a list with a battery part = WCLX; any other list = WCLB. Unknown chemistry on a power chair gives no code; `chair_type` starting with `manual` gives WCMP.
37. **SSR and Wh are computed at render time** on the web pages, so they cannot go stale. Wh uses a cited `wh_each` whenever its value is not null, verified or not (an unverified fact shows "Quote not found on page"). Pipeline records also store `derived` for the report; the library's SSR reads "WCLB or WCLX" because removal belongs to each chair. The §5.3 IATA lines are stored as `safety_lines` with their source.
38. **Return checklist:** "<part name> in place" for each confirmed label, then the `at_arrival` steps.

## Data notes

39. **Hand-written record** (`app/fixtures/library/whill-model-c2.json`, WHILL Model C2) has placeholder quotes and pages, shown with a `fixture_note`; it is what the tests use. `wh_each` is empty on purpose so the §5.2 computed line shows.
40. **Kovital KV-E100.** The manual calls the chair SWWP12504 (N3502) and never says "KV-E100", so the pages stage warns; the LLM put SWWP12504(N3502) in `aliases`. Its freewheel lever is 制動杆 (engaged 嚙合 / disengaged 脫開).
