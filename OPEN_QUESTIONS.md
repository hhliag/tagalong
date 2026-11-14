# Open questions

Where DESIGN.md was unclear, the simplest option was chosen and noted here. Change any of these by editing DESIGN.md.

## M1 (14 Nov 2026)

1. **Data folder not given.** `TAGALONG_DATA_DIR` defaults to `./data` (gitignored) when unset.
2. **The hand-written record holds placeholder content.** `app/fixtures/library/whill-model-c2.json` (moved there in M2) uses the WHILL Model C2 name from the DESIGN example, but its quotes, page numbers and figures were not taken from the manual. It has a `fixture_note` that the passport and check-in pages display. `verified: true` was set by hand because the verifier (§4.4) is not built yet. M2 replaces the whole record with extracted, verified data.
3. **`wh_each` left empty on purpose,** so the demo shows the §5.2 computed line (25.2 V × 10.8 Ah ≈ 272 Wh).
4. **Page links.** `/manual/{record_id}/{page}` is a stub: it lists the quotes cited on that page and marks the one for `?step=`. It has no page image (that needs the PDF, M2). `manual.url` is `null` until `sources.yaml` exists.
5. **Saved results in M1.** The saved plate and label results are the chair record in `devices/`, and the manual lookup runs for real against `library/`. `saved/<chair_id>/` arrives with live mode.
6. **No `/api/extract` endpoint yet.** When the manual is found in the library, §4.2 skips extract and verify, so the build page shows those two stages as skipped.
7. **Label decisions are shared.** ✓/✗ is stored on the server in `TAGALONG_DATA_DIR/state/<chair_id>.json`, so every viewer sees the same decisions. `--reset` clears them. If each judge's phone should keep its own decisions, they would need to move to the browser.
8. **Battery removal.** It is read only from the chair record's `removed_parts`: `null` = unknown (show WCLB or WCLX, "Confirm at check-in"); a list containing a battery part = removed (WCLX); any other list, including `[]`, = not removed (WCLB). The fixture has `[]`, so the demo shows WCLB.
9. **Unknown chemistry** on a power chair gives no code, just "Unknown battery · Confirm at check-in". A `chair_type` starting with `manual` gives WCMP.
10. **`derived` is not stored.** The SSR code and Wh are computed each time a page renders, so they cannot go stale. `derived` stays `null` in the file.
11. **Wh uses a cited value whenever `value` is not null,** whether or not its quote is verified. An unverified fact shows the "Quote not found on page" chip on the check-in page.
12. **Trust chips.** Every verified step shows `AI-extracted · page verified`. `Owner-confirmed` is added when the label for that step's part has been confirmed.
13. **Chair name on `/`** shows once the plate stage has run (server state), and the card reads "Model not read yet" before then.
14. **Photos missing** from the data folder show a placeholder SVG (file name + "Photo not in TAGALONG_DATA_DIR").
15. **Concept chip on the print.** The fixed corner chip is hidden on paper; the sheet header reads "Wheelchair passport · Concept" instead.
16. **QR target.** `PUBLIC_URL` when set, otherwise the URL the request came in on (uvicorn trusts proxy headers, so `https` through a tunnel is kept).
17. **Return checklist wording.** Each confirmed label becomes "<part name> in place", followed by the `at_arrival` step actions.
18. **Build pacing.** In M1 the browser waits 0.7 s before each stage so the ticks are visible; saved data would otherwise appear all at once.
19. **Git.** The folder was not a repository. It was initialised and the M1 commit made on `main`.

## Pipeline (M2 + M3, 14 Nov 2026)

20. **Where the hand-written records went.** They moved to `app/fixtures/`. `library/` and `devices/` now hold only pipeline output, and the app prefers them per record id or chair id. Tests point both folders at empty temp dirs, so the M1 page tests always use the fixtures.
21. **What `saved/` and `out/` keep.** Both are gitignored because `pages.json` and the offline request files hold the full manual text, and the PNGs and card hold our photos (§9). The JSON that may be public is committed through `library/` and `devices/`. `--freeze` (§4) is not built; nothing in the web app reads `saved/` yet.
22. **No `sources.yaml` yet.** The manual comes from `meta.yaml` (`manual`, optional `manual_url`), as the task says.
23. **Page scoring.** Rank = number of distinct keywords on the page, then total matches. "wh" and "key" must be whole words; other keywords also match inflections ("removed", "lifting"). Pages with no keyword are never kept. Spec page = the page with the most spec terms (specification, weight, dimension, voltage, kg, mm, ah, wh, km/h); none if no page has any.
24. **No default model.** `gemini`, `anthropic` and `openai` need `LLM_MODEL` or `--model`, to avoid guessing a model name that a key cannot call. With no `LLM_PROVIDER`, the provider is `offline`.
25. **Offline numbering and bad JSON.** Requests are `<stage>_<n>` in call order (extract 1; label 1..k in the order left, right, front, rear, then close-ups). A response file that is not valid JSON stops the run (exit 2) with a message to fix it; the live-provider "retry once" would otherwise clash with the next photo's number. Each rerun starts again from `pages`, which is fast and gives the same numbering.
26. **What code fixes in the LLM's answer.** Steps without a quote are dropped. An unknown `phase` becomes `before_loading`, an unknown `safety` becomes `comfort`, and a `part_id` not in `parts` becomes null. Step ids are renumbered s1..sn. Numbers like "25.2 V" become 25.2, and "yes"/"no" become booleans. The LLM's `must_do` is ignored; code decides it.
27. **Which steps qualify for must-do.** Freewheel / power switch = a `part_id` matching freewheel, free_wheel, clutch, brake_release, power_switch or power_button. Power off / its check / securing = the action or quote contains "power off", "turn ... off", "switch ... off", "power switch/button", "must not move", "does not move", "secur…", "tie-down" or "strap".
28. **`derived` in pipeline records.** The library record stores `wh_computed`, `wh_text` and `ssr_code`. Battery removal belongs to each chair, so the library's SSR always reads "WCLB or WCLX · Confirm at check-in" for lithium. The web pages still compute the SSR per chair (item 10).
29. **The §5.3 IATA lines** are stored in the record as `safety_lines` (power chairs only), with their source.
30. **Photo resizing.** Every photo is resized so its long side is exactly 1024 px (small photos are scaled up too), saved as JPEG in `out/<chair>/resized/`, and that file goes to the LLM and to drawing. Only lowercase `.jpg` names are read.
31. **Best photo per part.** A part is labelled only where it is visible with a location; parts never seen get no label. The location format follows the provider (box_2d for gemini, x/y for the others), but either answer is accepted.
32. **Card photos** are JPEG data URIs (PNG would make the file several MB); the PNGs stay in `out/`. The card shows the photos that carry labels, or the first two if none do. The sample-photos line needs `sample_photos: true` in `meta.yaml`.
33. **The dots follow the "~3% of the short side" rule** (23 px on a 1024 × 768 photo). On a 390 px phone screen that is a small dot, about 7 px in radius. Make it bigger if it is hard to see.
34. **New chair record fields** come from `meta.yaml` when present: `tag_id` (else made from the chair id), `battery_original`, `removed_parts` (else null = unknown).
35. **Old ✓/✗ decisions are cleared.** The label stage deletes the web app's runtime state for that chair, since those decisions were about the old labels.

## First real run: Kovital KV-E100 (14 Nov 2026)

36. **Model name.** The manual never says "KV-E100" or "Kovital"; it calls the chair SWWP12504 (N3502). `meta.yaml` uses make Kovital, model KV-E100 (the shop placard and photo names), so the pages stage warns that the model is not in the first pages. The LLM put SWWP12504(N3502) in `aliases`.
37. **Chinese manuals.** The page keywords now include Chinese terms (Traditional and Simplified), including this manual's word for the freewheel lever (制動杆, engaged 嚙合 / disengaged 脫開), plus 推動 (push) and 運送 (transport). Scoring runs on normalised text. The verifier drops whitespace next to CJK characters, because PDF line breaks split Chinese sentences.
38. **Language on the card.** Quotes and actions stay in the manual's language (Chinese here): translating would be generating, against the core rule. Values (facts, part names) are short English. For English-speaking judges, an English action would need a translation step, marked as such. Not built.
39. **Gemini on Vertex AI.** With `GOOGLE_GENAI_USE_VERTEXAI=True`, the client uses `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION` and the gcloud login instead of `GEMINI_API_KEY`.
40. **Timeout.** The live extract call took 39 s against the 40 s default `STAGE_TIMEOUT`. Set `STAGE_TIMEOUT=90` in `.env` for the pipeline.

## Handling zones and crew lookup (14 Nov 2026)

41. **Zone labels.** Each verified zone gets one label (`zone`: hold / no_hold, plus `zone_id` and `box`), numbered after the part labels so /confirm can use the same ✓/✗ API. A zone whose part is not visible in any photo still gets a label with `photo: null`; the owner confirms it from the list, and it has no marker. (The E100's lifting straps sit under the seat cushion, so this happens on the first real run.)
42. **"Only confirmed zones" on /passport, /print and the crew view;** the pipeline's `card.html` shows pending zones, because nothing is confirmed when it is made (it already says "Labels not yet confirmed by the owner").
43. **"The manual gives no lifting points. Ask the owner."** shows when the record has no verified hold zone, also when it has no_hold zones. `handling_missing` is true when no zone survives verification.
44. **Zone parts get part labels too.** A part that the handling stage adds (e.g. armrest) is a normal part, so it also gets a gold number when visible, as the spec says ("a part label stays as it is"). Zones are drawn under the numbers.
45. **Markers in the web pages are HTML** (like the part dots); the PNGs use Pillow drawing. Check and cross are drawn as lines in the PNGs, because the default font has no ✓ / ✗.
46. **The handling stage reads `record.json`, so rerun handling after extract** (`--stage all` does). Dropped zones and conflicts are kept in `out/<chair>/handling.json` for the report, not in the library record.
47. **Crew lookup (asked for in chat, not in DESIGN).** `/crew` takes a tag ID (case and spaces ignored); `/crew/{tag_id}` is the crew view: how to hold, photos, must do, battery and size, IATA lines. The QR on the printed card now opens `/crew/{tag_id}` instead of `/passport/{chair_id}` (§6), labelled "Crew: scan". Scanning uses the phone's own camera app; there is no in-page scanner. §10 lists an "inspector page" as out of scope; this is a read-only view of the same record.
48. **Timeout.** The handling call on the E100 manual (17 pages) took 60 s and failed once with 504 at 90 s; it worked with `STAGE_TIMEOUT=180`.

## Dots on every photo (14 Nov 2026, after the first review)

49. **A dot on every photo where the part shows** (was: best photo only). The same part keeps the same number on every photo; each dot has its own `id`, and the owner confirms each dot on its own, since a part can be right on one photo and wrong on another. Older chair records without `id` use `n`. The "closeup wins" rule is gone: a close-up just adds dots.
50. **One entry per instance.** The label prompt asks for one box per visible instance (left and right levers, two footrests), because one box around both put the dot on empty space between them. It also says to ignore wheelchairs in the background.
51. **Minimum confidence 0.5** for a dot. Below that, the detection stays in REPORT.md but gets no dot.
52. **Zones too** get a marker on every photo where their part shows; a zone is on the passport when at least one of its markers is confirmed.

## Card fixes: figures, clean actions, see-through pins, letters (14 Nov 2026)

53. **Figures are a new pipeline stage, `figures`** (after handling, before label), so the vision fallback has a place to run and can be rerun alone. Crops are in `out/<chair>/figures/<step>.png`; the app serves them at `/figure/<chair>/<step>`.
54. **Caption index.** A caption may be split in two words ("圖" + "4.1", as in the Kovital manual), so words on the same row are joined. The figure is the nearest image block or drawing cluster above the caption that covers its centre; images or clusters smaller than 30 pt, or larger than half the page, are ignored. References inside sentences ("見圖4.1") are not captions.
55. **Which figure a step gets:** (1) `figure_ref` from extract, found in the index (same page first, else any page; the Kovital text on p. 10 names figures printed on p. 11); (2) if the step needs a figure but names none, one vision call asks only which caption on the cited page it means; chip "Figure matched by AI"; skipped when the page has no captions; (3) otherwise the whole page, chip "Whole page". The "quote rectangle + nearest image" idea from the first part of the request is not used: the caption index and the vision question replace it.
56. **Figures on the print** only when there are at most 4 must-do steps (a small thumbnail per step), so the sheet stays on one A5 page. The card.html figures are embedded images without a link (the file has no server for /manual).
57. **List markers.** Stripped for display only: circled digits, or 1–2 digits followed by "." "、" ")" "）" (not followed by another digit). A plain number followed by a space is kept ("2 people lift"), so "24V" and "2.5 kg" stay whole.
58. **Part names are now as the manual writes them** (extract and handling prompts changed): the chip, legend and /confirm show 制動杆, 踏腳板… for the Kovital manual. Fact values stay short English for the §5 rules.
59. **Chip without a letter.** A step whose part has no shown label gets the part name only.
60. **Pins.** Ring radius 3% of the short side in the PNGs and 14 px on the HTML pages; the badge sits 0.07 of the photo out on both axes. The side is picked by `app.view.pin_sides` for both: the first of up-right, up-left, down-right, down-left that stays inside the photo (5% margin), preferring the most room from the other rings and badges. Zone rings are green (hold) / red (no_hold) with a check / cross badge; their boxes are outlines only (solid green / dashed red), the hatching is gone.
61. **Letters** come from n at display time (1 → A, 27 → AA); n stays in the JSON. Steps are numbered 1, 2, 3 through the whole Must do list.

## Confirm by tapping the photos (14 Nov 2026)

62. **No list on /confirm.** Each ring on the photos is the control: tap cycles grey (pending) → green (confirmed) → red (rejected) → grey, using the same `/api/labels/<chair>/<id>` call. A legend above the photos names each letter and zone. Rejected rings stay visible (red) on /confirm so the owner can undo; they are still hidden on every other page. A zone whose part shows on no photo gets a tap chip under the photos ("Not visible in the photos"), with the same cycle.
63. **Pin moving (DESIGN §10 listed it as out of scope; the owner asked for it).** Dragging a ring saves its new centre with `POST /api/labels/<chair>/<id>/move` (clamped to the photo) and sets `moved: true`; a zone box moves by the same amount. Moving does not change the status, so the owner still taps to confirm. A press that moves less than 6 px counts as a tap. The badge side is worked out again on the next page load. The pipeline PNGs and REPORT.md do not see moves until the render stage runs again from the chair record.
64. **Colours on /confirm show the owner's decision, not the zone kind.** Zone rings are grey / green / red like part rings; their badge says "Lift" (round) or "No" (square) in place of ✓ / ✗, and the ✓ / ✗ zone key under the photos is hidden on this page. The passport, print and crew views keep green hold / red no_hold.
65. **Bigger photos and pins on /confirm only.** The page is up to 1200 px wide with 2 photos per row (1 per row under 760 px); rings are 44 px with 32 px badges. Other pages are unchanged.
66. **"Check all" on /confirm** (owner request) turns every ring, zone marker and chip green in one call (`POST /api/labels/<chair>` with a status), including ones already marked red. The owner can still tap single rings afterwards.

## Step bar and step-done pages (14 Nov 2026)

67. **Where the step bar shows:** /, /build, /confirm, /passport, /uses/* and the step-done pages. Not on /print and /manual (as asked), and not on /crew and /crew/<tag>: those are the crew's lookup, not the owner's four steps.
68. **Done / current is by page position**, not by saved progress: on /confirm, steps 1–2 are done, 3 is current. /uses/* count as step 4. A step-done page marks the step it closes as done and the next one as current (/done/…/chosen: 1 done, 2 current). Done steps link to /, /build, /confirm, /passport; on / there is no chair yet, so nothing links.
69. **When a step counts as done:** "chosen" always (the chair exists). "built" once the label stage has run (`label` in the chair's `stages`, set by /build), else redirect to /build. "confirmed" when no label is pending, else redirect to /confirm. Unknown step → 404.
70. **Summary values.** Chosen: make + model once the plate stage has run (same rule as the picker), else "Model not read yet". Built: steps = `len(record.steps)`; quotes = `record.quotes` (verified / total, written by the extract stage); left out when the record has no counts (the hand-written M1 record). Parts = distinct parts with at least one dot on a photo (zone markers not counted). Confirmed: labels = every dot and zone marker; hidden = rejected ones.
71. **PUBLIC_BASE_URL** is the base for every QR (step-done pages and the printed card). The older `PUBLIC_URL` still works as a fallback, so existing `.env` files keep working. The step-done QR has the plain next URL, without `?fast=1`.
72. **?fast=1.** Flow links (picker cards, /build "Continue", /confirm "Done", step bar) point straight at the next page and keep `?fast=1`. A /done link opened with `?fast=1` redirects to the next page (after the guard). Other links (passport tiles, page links) do not carry it.
73. **/build** keeps its button hidden until the last stage ticks; it now says "Continue →" and goes to /done/<chair>/built. No automatic jump.
