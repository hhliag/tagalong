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
