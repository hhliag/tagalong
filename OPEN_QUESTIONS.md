# Open questions

Where DESIGN.md was unclear, the simplest option was chosen and noted here. Change any of these by editing DESIGN.md.

## M1 (14 Nov 2026)

1. **Data folder not given.** `TAGALONG_DATA_DIR` defaults to `./data` (gitignored) when unset.
2. **The hand-written record holds placeholder content.** `library/whill-model-c2.json` uses the WHILL Model C2 name from the DESIGN example, but its quotes, page numbers and figures were not taken from the manual. It has a `fixture_note` that the passport and check-in pages display. `verified: true` was set by hand because the verifier (§4.4) is not built yet. M2 replaces the whole record with extracted, verified data.
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
