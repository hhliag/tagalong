# TagAlong — Design contract v2 (13 Nov 2026)

v2 replaces v1. It builds only the demo in `claude/15_DEMO.md`. Every build session reads this file first and follows it. If something is unclear, choose the simplest option, write it in `OPEN_QUESTIONS.md`, and keep going.

## 1. What we build

A web app where a judge picks a real chair (a set of photos), and the app builds that chair's **passport** live: it reads the model plate, finds the manufacturer's manual, copies the handling steps with page numbers, checks every quote, and places the parts on the photos. The owner confirms each label. The result is a card on screen, a printable card, and a strip of other uses of the same record.

Core rule: **retrieve, don't generate.** The LLM may only copy a step from the manual and shorten its own quote. It never adds a step. A label or step that is not confirmed is never shown as fact.

## 2. Pages

| Path | What it shows |
| --- | --- |
| `/` | Chair picker: 2 or 3 cards (one photo, chair name hidden until the plate is read) |
| `/build/{chair_id}` | One "Build the passport" button, then a list of stages that tick as they finish (§4) |
| `/confirm/{chair_id}` | Photos with numbered labels in gold. Tap ✓ (turns jade) or ✗ (hidden). "Done" when all are decided |
| `/passport/{chair_id}` | The card: 2 photos with confirmed labels, "Must do" list (≤ 8 steps), each step with label number, trust chip and page link. "More from the manual" folded below. Strip "Same passport, other uses" at the bottom |
| `/manual/{record_id}/{page}?step={step_id}` | The manual page as an image with the quoted sentence marked, and the source link |
| `/passport/{chair_id}/print` | One printable page (A5 landscape): key facts, 2 photos with labels, ≤ 8 steps, QR to the passport, tag ID |
| `/uses/{chair_id}/{use}` | `checkin` (facts + SSR code), `onboard` (phone notification mock), `return` (her checklist). Each has a "Concept" chip |

Every page: "Concept" chip in the corner; "Sample photos. In real use the owner takes them." on build and passport pages.

## 3. Data

### 3.1 Chair folders (outside the repo: `TAGALONG_DATA_DIR/chairs/<chair_id>/`)

```
plate.jpg  left.jpg  right.jpg  front.jpg  rear.jpg  [closeup_<part>.jpg]
meta.yaml  # expected make + model (fallback only), photo source, permission note
```

Manuals: `TAGALONG_DATA_DIR/manuals/<file>.pdf`, listed in `sources.yaml` (make, model, aliases → file, official URL, sha256, date downloaded). No live web search in the demo.

### 3.2 Cited value

```json
{ "value": "...", "page": 61, "quote": "exact short text from that page", "verified": true }
```

`page` = 1-based PDF page index. `value: null` = not in the manual; never guess. `verified` is set only by code (§4.4).

### 3.3 Model record (`library/<record_id>.json`, open library)

```jsonc
{
  "record_id": "whill-model-c2", "make": "WHILL", "model": "Model C2", "aliases": [],
  "chair_type": "power_modular",
  "manual": { "file": "...", "url": "...", "sha256": "...", "pages": 0 },
  "parts": [ { "id": "freewheel_lever", "name": {cited}, "where": "short text from the manual", "count": 2 } ],
  "steps": [ { "id": "s1", "phase": "before_loading",   // before_loading | lifting | in_hold | at_arrival
               "part_id": "freewheel_lever",            // may be null
               "action": "max ~20 words, shortens ONLY its own quote",
               "source": {cited, no value}, "safety": "dg", // dg | injury | damage | comfort
               "must_do": true, "trust": "ai_extracted" } ],
  "facts": { "battery_chemistry": {cited}, "voltage_v": {cited}, "capacity_ah": {cited},
             "wh_each": {cited}, "battery_removable": {cited}, "power_off_method": {cited},
             "weight_kg": {cited}, "dimensions": {cited}, "removable_parts": [ {cited} ] },
  "derived": { "wh_computed": null, "ssr_code": "..." },   // code only, never the LLM
  "missing": [], "built_at": "..."
}
```

### 3.4 Chair record (`devices/<chair_id>.json`, no name, no flight)

```jsonc
{ "chair_id": "chair-a", "tag_id": "AP-7Q4K", "record_id": "whill-model-c2",
  "plate_read": { "make": "...", "model": "...", "raw": "..." },
  "battery_original": true,
  "labels": [ { "part_id": "freewheel_lever", "n": 1, "photo": "left.jpg",
                "x": 0.42, "y": 0.71, "confidence": 0.8, "status": "pending" } ], // pending | confirmed | rejected
  "removed_parts": [] }
```

`x`, `y` are fractions of image width and height.

## 4. Pipeline (one API call per stage, so the page can tick each stage)

| Stage | Endpoint | Does | Fallback |
| --- | --- | --- | --- |
| 4.1 Plate | `POST /api/plate/{chair_id}` | Vision LLM reads `plate.jpg` → make, model | `meta.yaml` value, marked "from sample data" |
| 4.2 Manual | `POST /api/manual/{chair_id}` | Look up `library/` by make + model + aliases. Hit → say "found in library" and skip 4.3–4.4. Miss → find the PDF in `sources.yaml`, check it is a PDF and the model name is in the first pages | Error card: "No manual found → generic steps" (not built; text only) |
| 4.3 Extract | `POST /api/extract/{record_id}` | PyMuPDF text per page. Pick pages by keywords (freewheel, brake release, battery, power, lift, carry, transport, fold, disassemble, weight, dimension, warning). One LLM call with the JSON schema of §3.3, exact quotes, null when absent. Mark `must_do` for dg/injury steps, freewheel, power off and its check, securing; at most 8 | Saved record |
| 4.4 Verify | inside 4.3 | For every cited value: normalise text, fuzzy match the quote on its page (ratio ≥ 0.9, e.g. rapidfuzz `partial_ratio`). Set `verified`. Unverified steps stay, but show "Quote not found on page" and are never `must_do` | — |
| 4.5 Label | `POST /api/label/{chair_id}` | Vision LLM gets the 4 photos (long side ≤ 1024 px) and the parts list (name + "where" text). Returns per part per photo: visible, x, y (0–1), confidence. Keep the best photo per part. Number labels 1..n in step order | Saved labels |

Rules:
- Each stage has a timeout (`STAGE_TIMEOUT`, default 40 s). On timeout or error, the stage uses the saved result and the page shows "Saved result".
- `MODE=live|saved`. Judges' phones get `saved`. The presenter runs live with `?live=<LIVE_KEY>`.
- Every live result is also written to `saved/<chair_id>/` (keep the best one by hand; a flag `--freeze` stops overwriting).
- The LLM provider is a setting (`LLM_PROVIDER`, `LLM_MODEL`, key from `.env`): Anthropic, Gemini, or any OpenAI-compatible endpoint. Text and image calls both.

## 5. Rules computed by code (not the LLM)

### 5.1 SSR code
No battery → `WCMP`; sealed lead acid → `WCBD`; wet → `WCBW`; lithium → `WCLB` (battery stays in the chair) or `WCLX` (removed). Unknown removal → show both and "Confirm at check-in". Do not infer removal from `battery_removable`.

### 5.2 Watt-hours
Show cited `wh_each` if present. Else `V × Ah` as "≈ N Wh (computed, not a manual figure)". Else "not in the manual".

### 5.3 Safety lines on every power chair card
From IATA guidance for battery-powered mobility aids (label the source):
- Cut power by the maker's method, then check: drive mode, power on, push the joystick; the chair must not move.
- Freewheel: engage to push by hand; disengage before securing.
- Removed lithium batteries go in the cabin.

## 6. The card and the print

- "Must do" list first, numbered by phase. Each step: label number (matches the dot on the photo), action, trust chip (`AI-extracted · page verified`, then `Owner-confirmed`), page link.
- Only confirmed labels appear. A line says how many were hidden.
- Print layout (A5 landscape, one page): chair name, tag ID, weight, battery type, Wh, power-off method; 2 photos with dots; ≤ 8 steps in large type; QR to `/passport/{chair_id}`; "Return to the aircraft door". Prints correctly from Chrome.

## 7. Other uses strip (views of the same record, "Concept" chip on each)

| Tile | Shows |
| --- | --- |
| Printed card | Link to `/print` |
| On board | A phone notification mock: "Your wheelchair is on board." No real sending. |
| Check-in | Battery type, V, Ah, Wh (§5.2), removable, power-off method, weight, size, SSR code (§5.1). Each with page link |
| Return check | Her checklist from confirmed labels + `at_arrival` steps, e.g. "Joystick fitted", "Power on". Buttons "All OK" / "Problem with a part" (stored in the browser only) |

## 8. Stack and conventions

- Python 3.12+, FastAPI, Jinja + plain JS (no build step), JSON files. PyMuPDF for PDF text and page images. rapidfuzz for quotes.
- Style: dark teal `#044B52`, jade `#005D63`, gold `#C3AC86`, rounded boxes, airport-sign feel; Atkinson Hyperlegible. No Cathay logo. Works on a phone (390 px wide).
- One command to run: `python -m app`. `--reset` reloads saved data.
- Public link: run on `0.0.0.0` and expose with a tunnel (e.g. cloudflared). README explains both.
- pytest for §5 rules and the verifier. No secrets in git; `.env.example` lists every variable.

## 9. Data and rights (the repo is public)

Do not commit maker PDFs or photos we do not own. They stay in `TAGALONG_DATA_DIR`. The repo holds code, schema, the library JSON (short quotes + page numbers only), `sources.yaml` with official URLs, and a script that downloads the manuals.

## 10. Out of scope

Booking page, scan feed, status timeline, photo upload by the user, pin moving, inspector page, OWLv2, 3D, AR, login, real airline integration. Stretch only if everything works: let a judge upload 4 photos of their own chair.
