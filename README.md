# TagAlong

**Her wheelchair flies without her.**

When a wheelchair user flies, her chair goes in the hold. The ramp crew who load it have usually never seen that model. They don't know where to lift it, how to put it in freewheel, or how to cut the power. A wrong grip can snap off a joystick or an armrest, and the passenger only finds out at the aircraft door.

TagAlong turns the **manufacturer's manual** into a **passport for her exact chair**. The passport gives the handling steps, with the manual's page number for each one, and the parts marked on photos of her chair. She checks every mark. The crew get a printed card on the chair and scan its QR code for the full record.

**Live demo:** https://tagalong-wyftmmulrq-df.a.run.app (works on a phone)

> This is a design concept. It is not a live airline service and has no airline integration.

---

## Try it in two minutes

1. **Home.** Choose **I am the passenger** and pick a chair. There are three real chairs, each with its own photos and manual.
2. **Build passport.** Press the button and watch the stages tick: read the model plate → find the manual → copy the steps → check every quote → place the parts on the photos.
3. **Confirm.** Every mark on the photos is grey. Tap one once for green (right), again for red (wrong), and a third time to clear it. Drag a mark if it sits on the wrong spot. **Check all** turns them all green.
4. **Passport QR.** This is the code the ramp handler scans.
5. **Passport.** The A5 card that travels on the chair comes first, then the full record it is drawn from. Items that also appear on the printed card carry an "On the card" tag.
6. **Ramp crew view.** On the home page choose **I am ramp crew** and type a tag ID, or scan the QR. This view starts with *How to hold this chair*.

The same record also feeds the **check-in** view (battery facts and the airline's SSR code), an **on-board notice** to the passenger and a **return checklist** for arrival.

## Why the crew can trust it

**Retrieve, don't generate.** The AI may only copy a step from the manual and shorten its own quote. It never adds a step.

- **Every step and fact cites a page.** Tap the page number to see the quoted sentence.
- **Code checks every quote.** It fuzzy-matches each quote against the text of that page. A quote that isn't found is marked "Quote not found on page" and is never made a must-do step.
- **The passenger confirms every mark on the photos.** Unconfirmed marks never reach the passport, the card or the crew view, and the page says how many were hidden.
- **Safety rules are code, not AI.** The SSR code (WCLB, WCLX and others) and the battery watt-hours are computed by rules with unit tests. A watt-hour figure the manual doesn't state is shown as *computed*.
- **Gaps stay visible.** A fact the manual doesn't give reads "not in the manual". Nothing is guessed.

Results for the three demo chairs (Kovital, manuals in Traditional Chinese and English):

| Chair | Manual | Steps | Quotes verified on their page |
| --- | --- | --- | --- |
| A · Kovital KV-E100 | 22 pages, Chinese | 7 | 23 / 23 |
| B · Kovital KV-E6 Ultra Plus | 16 pages, Chinese | 7 | 22 / 22 |
| C · Kovital KV-C2 Apex 500W | 29 pages, English | 6 | 23 / 23 |

## How it works

```
 photos of her chair ─┐
                      ├─► pages ─► extract ─► handling ─► figures ─► label ─► passport
 manufacturer's PDF ──┘   (pick     (copy      (where to   (crop the   (place     (card, crew view,
                          pages)    steps +    lift / not  manual's    parts on   check-in, print)
                                    verify)    to hold)    figures)    photos)
```

| Stage | What it does | AI |
| --- | --- | --- |
| pages | Reads the PDF and keeps the pages about freewheel, power, battery, lifting, folding and weight | none |
| extract | Copies the handling steps and facts with exact quotes and page numbers, then code verifies each quote | 1 text call |
| handling | Finds the sentences on where to lift and what not to hold | 1 text call |
| figures | Crops the manual's own drawing for each step | 0 or 1 vision call |
| label | Finds each part on each photo | 1 vision call per photo |

The demo uses Gemini on Vertex AI. The model provider is a setting: Gemini, Anthropic or any OpenAI-compatible endpoint. The live demo serves saved results, so it needs no AI key.

**Stack:** Python 3.12, FastAPI, Jinja templates with plain JavaScript (no build step), JSON files, PyMuPDF and rapidfuzz. It is deployed on Google Cloud Run. 150+ tests.

## Run it locally

```bash
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m app            # http://localhost:8000
.venv/bin/python -m pytest -q      # tests
```

A fresh clone runs without any data. It shows one hand-written sample chair, with placeholder photos and placeholder quotes. The real chairs' photos and manuals are not in the repo, because we don't redistribute the manufacturers' PDFs; to see the real chairs, use the live demo. [docs/DEVELOPING.md](docs/DEVELOPING.md) explains how to add your own chair and manual, run the pipeline, print the card and deploy.

## Repository

```
app/          web app: routes (main.py), safety rules (rules.py), card data (view.py), JSON store
pipeline/     photos + manual → passport (pages, extract, verify, handling, figures, label, render)
tests/        rules, verifier, every page, and a full offline pipeline run
docs/         DEVELOPING.md: running the pipeline, data folder, public link, deploy
DESIGN.md     the design contract every build session follows
OPEN_QUESTIONS.md   every choice made where the design was silent, and what is still open
```

## What is a concept and what is real

| Real, working | Concept / mock-up |
| --- | --- |
| Manual → cited steps, with code checking every quote | The on-board phone notice (nothing is sent) |
| Parts and lifting zones placed on photos by AI, then confirmed by the passenger | Check-in hand-off to an airline system |
| SSR code and watt-hour rules, unit tested | The passenger taking her own photos (the demo uses sample photos) |
| Printable A5 card with a QR to the crew view | Live AI runs on the public demo (it serves saved results) |
