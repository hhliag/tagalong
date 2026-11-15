# Decisions and open questions

A build log of decisions. Where DESIGN.md was silent or unclear, the simplest option was chosen and written down here, so every behaviour can be traced to a choice. The first section lists what is still open.

## Still open (owner's call)

1. **English for judges.** Steps and part names stay in the manual's language (Chinese for the Kovital manual), because translating would be generating. An English version would need a translation step, clearly marked as such. Not built.
2. **Shared ✓/✗ decisions.** Label decisions and pin moves are stored on the server (`data/state/<chair>.json`), so every viewer sees and changes the same ones. Per-phone decisions would have to move to the browser.
3. **Photos are served full size** (5–7 MB each), slow on phones over a tunnel. Resized copies were offered.
4. **Pipeline results for the three Kovital chairs** (`library/kovital-*.json`, `devices/chair-{a,b,c}.json`) are not committed. §9 allows short quotes in the repo.
5. **Is the D06T manual right for chair C?** The photos' placard says Kovital KV-C2 Apex 500W: DC 24 V 10 Ah (240 Wh), 16 kg without battery, 500 W. The "D06T" English manual names no model and says 25.9 V 10 Ah, 11.9 kg without battery, 2 × 150 W. The passport shows the manual's numbers (≈ 259 Wh, 11.9 kg). Find the C2 Apex manual, or confirm the D06T is it.
6. **Step-done pages "chosen" and "built"** have no QR any more; they could be dropped so the only in-between page is the passport QR.

## Pages and flow

7. **Step bar** (1 Choose chair, 2 Build passport, 3 Confirm, 4 Passport) on /, /build, /confirm, /passport, /uses/* and the step-done pages. Not on /print, /manual, /crew or /crew/<tag> (the crew's lookup is not part of the owner's steps). Done / current is by page position, not saved progress; /uses/* count as step 4. Done steps link back; on / there is no chair yet, so nothing links.
8. **Step-done pages** `/done/<chair>/<chosen|built|confirmed>`. A step counts as done: "chosen" always; "built" once the label stage has run (`label` in the chair's `stages`); "confirmed" when no label is pending. Otherwise the page redirects to /build or /confirm. /build shows "Continue →" only after the last stage ticks; no automatic jump.
9. **Summary values** come from the files. Chosen: make + model once the plate stage has run, else "Model not read yet" (same rule as the picker). Built: number of steps; `record.quotes` verified / total (left out when the record has no counts, as in the hand-written record); distinct parts with at least one dot on a photo. Confirmed: confirmed dots and zone markers · rejected ones as "hidden".
10. **The passport QR** is only on the "confirmed" page, between /confirm and /passport: it is what the ramp handler scans. It opens the crew view `/crew/<tag>`, the same QR as the printed card (DESIGN §6 said `/passport`). Base URL: `PUBLIC_BASE_URL`, or the older `PUBLIC_URL`, else the address the request came in on (proxy headers trusted, so `https` through a tunnel is kept).
11. **?fast=1.** Flow links (picker, /build "Continue", /confirm "Done", step bar) go straight to the next page and keep `?fast=1`; a /done link with it redirects after the guard. Other links do not carry it.
12. **Crew lookup** (asked for in chat, not in DESIGN). `/crew` takes a tag ID (case and spaces ignored); `/crew/<tag>` shows how to hold, photos, must do, battery and size, IATA lines. Scanning uses the phone's camera app. §10's "inspector page" is out of scope; this is a read-only view of the same record.
13. **Manual page links.** `/manual/<record>/<page>` is a stub: it lists the quotes cited on that page and marks the one for `?step=`. No page image; `manual.url` is null until `sources.yaml` exists.
14. **Concept chip on the print** is hidden on paper; the sheet header reads "Wheelchair passport · Concept". Missing photos show a placeholder SVG.
15. **Build page.** M1 stages return saved results; the browser waits 0.7 s per stage so the ticks show. When the manual is in the library, extract and verify show as skipped (no `/api/extract`).

## Confirm page

16. **Tap the rings, no list.** Tap cycles grey (pending) → green (confirmed) → red (rejected) → grey. Red rings stay visible on /confirm so the owner can undo; every other page shows confirmed labels only. A legend above the photos names each letter and zone. A zone whose part is on no photo gets a tap chip under the photos.
17. **"Check all"** turns every ring, zone marker and chip green in one call, including red ones.
18. **Dragging a ring** saves its new centre (clamped to the photo, `moved: true`); a zone box moves with it. Status does not change. Under 6 px of movement counts as a tap. The pipeline PNGs and REPORT.md do not see moves.
19. **Colours show the owner's decision.** Zone rings are grey / green / red too; their badge says "Lift" (round) or "No" (square). Passport, print and crew keep green hold / red no_hold.
20. **Bigger layout on /confirm only:** up to 1200 px wide, 2 photos per row (1 under 760 px), 44 px rings with 32 px badges.
21. **Relabelling clears decisions.** The label stage deletes `data/state/<chair>.json`, since old decisions were about old labels. `python -m app --reset` also clears them.

## Labels, pins and zones

22. **A dot on every photo where a part shows,** one per instance (both levers, both footrests), same letter per part; each dot is confirmed on its own (`id`; older records use `n`). Minimum confidence 0.5; lower detections stay in REPORT.md only. The label prompt says to ignore wheelchairs in the background.
23. **Letters** come from `n` at display time (1 → A, 27 → AA); steps are numbered 1, 2, 3 through the Must do list. A step whose part has no shown label gets a chip with the part name only.
24. **Pins** are hollow rings with the letter in a badge outside: 3% of the short side in the PNGs, 14 px on the web pages (bigger on /confirm). `app.view.pin_sides` picks the badge side for both: the first of up-right, up-left, down-right, down-left that stays inside the photo, preferring the most room. Web markers are HTML; PNGs are drawn with Pillow (check and cross as lines).
25. **Zones.** Each verified hold / no_hold zone gets a marker on every photo where its part shows (`zone`, `zone_id`, `box`), numbered after the part labels so the same API works. Boxes are outlines (solid green / dashed red). A zone is on the passport when at least one of its markers is confirmed; the pipeline's card.html shows pending ones. Parts the handling stage adds get normal part labels too.
26. **No lifting points:** when no verified hold zone exists, the "Lift here" part is left out (no "Ask the owner" line). With no zones to show at all, the "How to hold this chair" box and the print's zone box are left out too.
27. **Trust chips.** Verified steps show `AI-extracted · page verified`; `Owner-confirmed` is added when a label of that step's part is confirmed.

## Pipeline

28. **Stages** `pages → extract → handling → figures → label → render`, each reading the previous file in `out/<chair>/`. Rerun handling and figures after extract (`--stage all` does). Dropped zones and conflicts stay in `out/<chair>/handling.json`.
29. **Folders.** Hand-written records live in `app/fixtures/`; `library/` and `devices/` hold pipeline output and win per id. `out/` and `saved/` are gitignored (full manual text, our photos). `--freeze` and `sources.yaml` are not built; the manual comes from `meta.yaml` (`manual`, optional `manual_url`). New chair fields from `meta.yaml`: `tag_id`, `battery_original`, `removed_parts`.
30. **Page scoring.** Rank by distinct keywords, then total matches; English and Chinese (Traditional and Simplified) keywords, on normalised text. Pages with no keyword are never kept. Spec page = the page with the most spec terms.
31. **What code fixes in the LLM's answer.** Steps without a quote are dropped; unknown `phase` → `before_loading`, unknown `safety` → `comfort`, unknown `part_id` → null; ids renumbered s1..sn; "25.2 V" → 25.2, "yes"/"no" → booleans. `must_do` is decided by code: freewheel / power-switch parts, and power off, its check, or securing in the action or quote; at most 8.
32. **Verifier.** NFKC, quotes, dashes, hyphen breaks; whitespace next to CJK characters is dropped (PDF line breaks split Chinese sentences); `partial_ratio` ≥ 90.
33. **Language.** Quotes, actions and part names stay as the manual writes them; fact values are short English for the §5 rules.
34. **Figures** (own stage, before label). A caption index joins split captions ("圖" + "4.1"); the figure is the nearest image or drawing above the caption. A step gets (1) its `figure_ref` from the index, else (2) one vision call that only names a caption on the cited page (chip "Figure matched by AI"), else (3) the whole page (chip "Whole page"). Print shows figures only with at most 4 must-do steps. List markers ("1.", "2、", "①") are stripped for display only.
35. **Photos for the LLM** are resized to a 1024 px long side (EXIF transposed) in `out/<chair>/resized/`. Card photos are JPEG data URIs.
36. **LLM settings.** No default model: `gemini`, `anthropic`, `openai` need `LLM_MODEL`; no `LLM_PROVIDER` = `offline` (requests `<stage>_<n>` in call order; bad JSON in a response stops the run). Gemini on Vertex AI uses `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION` and the gcloud login. Calls take 40–60 s: use `STAGE_TIMEOUT=180`.

## Rules (DESIGN §5)

37. **Battery removal** is read only from the chair's `removed_parts`: null = unknown (WCLB or WCLX, "Confirm at check-in"); a list with a battery part = WCLX; any other list = WCLB. Unknown chemistry on a power chair gives no code; `chair_type` starting with `manual` gives WCMP.
38. **SSR and Wh are computed at render time** on the web pages, so they cannot go stale. Wh uses a cited `wh_each` whenever its value is not null, verified or not (an unverified fact shows "Quote not found on page"). Pipeline records also store `derived` for the report; the library's SSR reads "WCLB or WCLX" because removal belongs to each chair. The §5.3 IATA lines are stored as `safety_lines` with their source.
39. **Return checklist:** "<part name> in place" for each confirmed label, then the `at_arrival` steps.

## Data notes

40. **Hand-written record** (`app/fixtures/library/whill-model-c2.json`, WHILL Model C2) has placeholder quotes and pages, shown with a `fixture_note`; it is what the tests use. `wh_each` is empty on purpose so the §5.2 computed line shows.
41. **Kovital KV-E100.** The manual calls the chair SWWP12504 (N3502) and never says "KV-E100", so the pages stage warns; the LLM put SWWP12504(N3502) in `aliases`. Its freewheel lever is 制動杆 (engaged 嚙合 / disengaged 脫開).
42. **Kovital KV-E6 Ultra Plus (chair-b).** Photos from the shop (8 Nov), `back` renamed `rear`. The manual (`kv-e6-zh.pdf`, 16 pages, Traditional Chinese) calls the chair 室內型 SWWP02501 (NXN18-218) and never says "KV-E6", so the pages stage warns. 7 steps, 22/22 quotes verified; no handling zones in the manual; no figure captions (2 steps use the whole page).
43. **Kovital KV-C2 Apex 500W (chair-c).** Model from the placard on the rear photo; photos from WhatsApp (1200 × 1600), mapped front / left / rear / right by looking at them. Manual `d06t-en.pdf` (29 pages, English) from the owner; see item 5. 6 steps, 23/23 quotes verified; no handling zones; no figure captions.

## Cloud Run deploy

44. **Deploy commands** were not given in the task, so the README uses `gcloud run deploy tagalong --source .` (Cloud Build builds the Dockerfile) in `asia-east2` (Hong Kong), public, `--max-instances 1`, `--memory 1Gi`.
45. **Figure crops on Cloud Run.** The app serves them from `out/`, which is not uploaded. `scripts/prepare_deploy.sh` copies `out/<chair>/figures/` into `deploy_data/out/`, and the image sets a new variable `TAGALONG_OUT_DIR=/app/deploy_data/out` (default `./out`, so local runs are unchanged).
46. **State on Cloud Run** (label decisions, build progress) is written inside the container and lost on restart; `--max-instances 1` keeps every viewer on the same copy. `data/state/` is not copied, so a deploy starts with every label grey.
47. **MODE** defaults to `saved` when `K_SERVICE` is set, else `live`; `MODE` in the environment wins. Live mode is not built, so nothing reads it yet: behaviour is the same either way.
48. **Ignore files.** `.gcloudignore` (upload) and `.dockerignore` (image) both leave out `.env`, `.git`, `out/`, `saved/`, `data/`, `.venv/`, caches and `16_PIPELINE.md` (the owner's private prompt doc). Patterns are anchored (`/out/`) so `deploy_data/out/` is kept. The Dockerfile fails with a message when `deploy_data/` was not prepared.
49. **requirements.txt** lists every third-party package that `app/` and `pipeline/` import. `pydantic` was imported directly but only came in through FastAPI; it is now pinned (2.14.3, the version in use). `pytest` stays in, so the image can run the tests.

## Home, roles and the passport layout

50. **"maker's manual" in the new home text** is written as "manufacturer's manual", following the earlier request to use that phrase everywhere.
51. **Home page.** The headline is the page's `h1`; "Pick a chair" becomes an `h2` with `id="pick"`, the target of "I am the passenger". The doors sit between the intro and the picker.
52. **Role chips.** `/manual/...` gets no chip: owners and crew both open it from their own pages. `/print` has no top bar, so its chip sits in the toolbar (hidden when printed). `/uses/*/checkin` loses the step bar (Check-in view); `/uses/*/onboard` and `/return` keep it. The top bar now wraps on a phone, because the extra chip did not fit at 390 px.
53. **Card preview** is the real card markup (`_card.html`, shared with `/print`), scaled down by a small script (`card_preview.js`). Without JavaScript it shows at full size, cut off at the right edge. It is hidden from screen readers, since the full record below holds the same content.
54. **"On the card" tags** come from `v.card` (`view.card`), which the print page also draws from: the first 2 photos, the first 3 hold and 3 no-hold zones, and every must-do step. Key facts are not listed in the full record on `/passport`, so no fact carries a tag there; they show in the card preview and on the Check-in page.
55. **Other uses strip.** The Crew view and Check-in tiles lose their "Concept" chip; only On board and Return check keep it.
