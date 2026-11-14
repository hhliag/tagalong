# TagAlong

A wheelchair **passport** built from the maker's manual: handling steps with page numbers, parts marked on photos and confirmed by the owner, a printable A5 card, and other views of the same record. The design contract is in [DESIGN.md](DESIGN.md).

Core rule: **retrieve, don't generate.** Every step and fact is copied from the manual, with its page number.

## Status: M1

M1 is the app shell, driven by hand-written data. There is no LLM yet.

| Works | Saved or simulated |
| --- | --- |
| Pages `/`, `/build/{chair}`, `/confirm/{chair}`, `/passport/{chair}`, `/passport/{chair}/print`, `/uses/{chair}/checkin\|onboard\|return` | Every build stage returns saved data and is marked "Saved result" |
| Label ✓/✗ saved on the server; the passport shows only confirmed labels | The model record `library/whill-model-c2.json` is hand-written: its quotes, pages and figures are **placeholders**, not checked against the manual |
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
5. To make the QR on the printed card point there, put `PUBLIC_URL=https://<random>.trycloudflare.com` in `.env` and restart the app (step 2). The quick-tunnel URL changes every time cloudflared restarts.

Stop the tunnel with Ctrl-C when you are done: anyone with the link can open the app.

## Print the card

Open `/passport/chair-a/print` in Chrome → **Print**. The page sets A5 landscape with no margins. If Chrome shows headers or footers, untick "Headers and footers" under More settings.

## Tests

```bash
.venv/bin/python -m pytest -q
```

They cover the §5 rules (SSR code, Wh), the must-do and confirmed-label rules on the card, and every page.

## Layout

```
app/          FastAPI app (main.py routes, rules.py §5, view.py card data, store.py JSON files)
library/      model records (open library: short quotes + page numbers)
devices/      chair records (no name, no flight)
tests/
OPEN_QUESTIONS.md   choices made where DESIGN.md was unclear
```
