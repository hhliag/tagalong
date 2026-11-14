# TagAlong

A wheelchair **passport** built from the manufacturer's manual: handling steps with page numbers, parts marked on photos and confirmed by the owner, a printable A5 card, and other views of the same record. The design contract is in [DESIGN.md](DESIGN.md).

Core rule: **retrieve, don't generate.** Every step and fact is copied from the manual, with its page number.

## Status: M1

M1 is the app shell, driven by hand-written data. There is no LLM yet.

| Works | Saved or simulated |
| --- | --- |
| Pages `/`, `/build/{chair}`, `/confirm/{chair}`, `/passport/{chair}`, `/passport/{chair}/print`, `/uses/{chair}/checkin\|onboard\|return` | Every build stage returns saved data and is marked "Saved result" |
| Label ✓/✗ saved on the server; the passport shows only confirmed labels | The M1 model record `app/fixtures/library/whill-model-c2.json` is hand-written: its quotes, pages and figures are **placeholders**, not checked against the manual |
| SSR code (§5.1) and Wh (§5.2) computed by code, with tests | `/manual/...` shows the cited quotes only; the page image arrives with the PDFs |
| Phone layout (390 px), A5 landscape print with QR | Photos: a placeholder appears until you add real ones (see below) |

## Run

```bash
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env          # optional in M1
.venv/bin/python -m app       # http://localhost:8000
```

`python -m app --reset` forgets label decisions and build progress, then starts.

Demo path: `/` → pick Chair A → **Build the passport** → **Confirm the labels** (✓/✗ each) → **Done** → the passport → the "Same passport, other uses" tiles.

## Data folder

Photos and manuals are not in the repo (DESIGN §9). Set `TAGALONG_DATA_DIR` in `.env` (default `./data`, which is gitignored):

```
$TAGALONG_DATA_DIR/
  chairs/chair-a/  plate.jpg left.jpg right.jpg front.jpg rear.jpg
  manuals/         (PDFs, from M2)
  state/           (written by the app: label decisions, build progress)
```

A missing photo shows a placeholder, so the demo runs without any data.

## Share a public link (phones)

The app listens on `0.0.0.0:8000`.

**Same Wi-Fi:** open `http://<your-computer-ip>:8000` on the phone (on a Mac, the IP is shown by `ipconfig getifaddr en0`).

**Anywhere, with a Cloudflare quick tunnel** (no account needed):

1. Install: `brew install cloudflared`
2. Start the app: `.venv/bin/python -m app`
3. In a second terminal: `cloudflared tunnel --url http://localhost:8000`
4. Copy the `https://<random>.trycloudflare.com` URL it prints. That is the public link.
5. To make the QR on the printed card point there, put `PUBLIC_BASE_URL=https://<random>.trycloudflare.com` in `.env` (the older name `PUBLIC_URL` still works) and restart the app (step 2). The quick-tunnel URL changes every time cloudflared restarts.

Stop the tunnel with Ctrl-C when you are done: anyone with the link can open the app.

## Crew lookup

`/crew` lets ground crew find a chair by its tag ID, and the QR on the printed card opens `/crew/<tag_id>` straight from the phone camera. The crew view leads with "How to hold this chair", then the photos with confirmed labels, the must-do steps, battery facts and the IATA lines. Every page has a "Crew lookup" link in the top bar.

## Print the card

Open `/passport/chair-a/print` in Chrome → **Print**. The page sets A5 landscape with no margins. If Chrome shows headers or footers, untick "Headers and footers" under More settings.

## Pipeline: photos + manual → labelled passport

```
python -m pipeline <chair_id> [--stage pages|extract|handling|figures|label|render|all]
                              [--provider gemini|anthropic|openai|offline] [--model NAME]
```

Input, in `TAGALONG_DATA_DIR`:

```
chairs/chair-a/  left.jpg right.jpg front.jpg rear.jpg  [closeup_<part_id>.jpg]
                 meta.yaml
manuals/         whill-model-c2.pdf
```

`meta.yaml`:

```yaml
make: WHILL
model: Model C2
manual: whill-model-c2.pdf     # file name in manuals/
manual_url: https://...        # optional: official link, shown in the record
photo_source: own photos, Nov 2026
sample_photos: true            # optional: card says "Sample photos. In real use the owner takes them."
removed_parts: null            # optional: e.g. [battery]; null = owner has not said (SSR shows both codes)
tag_id: AP-7Q4K                # optional: otherwise made from the chair id
```

| Stage | LLM | Reads | Writes |
| --- | --- | --- | --- |
| `pages` | no | meta.yaml, the PDF | `out/<chair>/pages.json` |
| `extract` | 1 text call | pages.json | `out/<chair>/record.json`, `library/<record_id>.json` |
| `handling` | 1 text call | pages.json, record.json | hold / no_hold zones into `record.json` and `library/`; `out/<chair>/handling.json` (dropped zones) |
| `figures` | 0, or 1 vision call per step that needs a figure but names none | the PDF, record.json | `out/<chair>/figures/<step>.png` crops; `figure` on each step in `record.json` |
| `label` | 1 vision call per photo | record.json, photos | part + zone labels in `out/<chair>/device.json`, `detections.json`, `devices/<chair>.json` |
| `render` | no | all of the above | `out/<chair>/labelled_<view>.png`, `card.html`, `REPORT.md` |

Every result is also copied to `saved/<chair>/`. Each stage reads the previous stage's file, so you can rerun one stage alone. Every LLM request and reply is logged in `out/<chair>/llm_log/`.

Once `library/<record_id>.json` and `devices/<chair>.json` exist, the web app uses them instead of the hand-written M1 records in `app/fixtures/` (no restart needed). The label stage also clears that chair's ✓/✗ decisions, since they were about the old labels.

**Handling zones.** The `handling` stage keeps only sentences where the manual says where to lift or hold the chair, or what not to hold. A zone whose quote is not found is dropped completely. On the photos, a green circle with ✓ means "lift here" and a red rounded square with ✗ (hatched box) means "do not hold"; the shapes differ, so they read in black and white. The owner confirms zones on /confirm like labels; only confirmed zones reach the passport, the print and the crew view.

### With an API key

Put `LLM_PROVIDER`, `LLM_MODEL` and the matching key in `.env` (see `.env.example`), then:

```bash
.venv/bin/python -m pipeline chair-a
```

### Without a key (offline: Claude Code plays the LLM)

```bash
.venv/bin/python -m pipeline chair-a --provider offline
```

It stops with exit code 3 and prints `Waiting for offline response: <path>`. The matching `_request.md` next to it holds the full prompt and the image paths. Ask Claude Code to act as the LLM for that request and write only the JSON to that path, then run the command again. Expect 5 rounds: 1 for extract, then 1 per photo.

The code still checks every quote, so a wrong quote shows up as "not verified". Results made this way are saved results, not a live run.

### Check the result

Open `out/<chair>/card.html` on a phone. Fill the "right / wrong" column in `out/<chair>/REPORT.md`.

`out/` and `saved/` are gitignored: they hold the full manual text and the photos.

## Tests

```bash
.venv/bin/python -m pytest -q
```

They cover the §5 rules (SSR code, Wh), the must-do and confirmed-label rules on the card, every page, the quote verifier, label coordinates (box_2d, EXIF rotation), and a full offline pipeline run.

## Layout

```
app/          FastAPI app (main.py routes, rules.py §5, view.py card data, store.py JSON files)
app/fixtures/ hand-written M1 records (used when the pipeline has not made a record)
pipeline/     command-line pipeline (pages, extract + verify, label, render, llm.py)
library/      model records from the pipeline (open library: short quotes + page numbers)
devices/      chair records from the pipeline (no name, no flight)
tests/
OPEN_QUESTIONS.md   choices made where DESIGN.md was unclear
```
