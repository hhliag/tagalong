# Developing TagAlong

How to run the app with real data, run the pipeline, share a link, print the card and deploy. For what the app does, see the [README](../README.md); for the design rules, see [DESIGN.md](../DESIGN.md).

## Run

```bash
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env          # only needed for the pipeline's AI settings
.venv/bin/python -m app       # http://localhost:8000
```

`python -m app --reset` clears label decisions and build progress, then starts.

## Data folder

Photos and manuals are not in the repo (DESIGN §9). Set `TAGALONG_DATA_DIR` in `.env`; the default is `./data`, which is gitignored.

```
$TAGALONG_DATA_DIR/
  chairs/<chair_id>/  left.jpg right.jpg front.jpg rear.jpg  [plate.jpg] [closeup_<part_id>.jpg]
                      meta.yaml
  manuals/            <manual>.pdf
  state/              written by the app: label decisions, build progress
```

A missing photo shows a placeholder, so the app runs without any data. With no pipeline output, the app uses the hand-written sample records in `app/fixtures/`. Their quotes and pages are placeholders.

`meta.yaml`:

```yaml
make: Kovital
model: KV-E100
manual: kv-e100-zh.pdf         # file name in manuals/
manual_url: https://...        # optional: official link, shown in the record
photo_source: own photos, Nov 2026
sample_photos: true            # optional: pages say "Sample photos. In real use the owner takes them."
removed_parts: null            # optional: e.g. [battery]; null = the owner has not said (SSR shows both codes)
tag_id: AP-7Q4K                # optional: otherwise made from the chair id
```

## Pipeline: photos + manual → passport

```
python -m pipeline <chair_id> [--stage pages|extract|handling|figures|label|render|all]
                              [--provider gemini|anthropic|openai|offline] [--model NAME]
```

| Stage | AI | Reads | Writes |
| --- | --- | --- | --- |
| `pages` | none | meta.yaml, the PDF | `out/<chair>/pages.json` |
| `extract` | 1 text call | pages.json | `out/<chair>/record.json`, `library/<record_id>.json` |
| `handling` | 1 text call | pages.json, record.json | hold / no-hold zones in `record.json` and `library/`; dropped zones in `out/<chair>/handling.json` |
| `figures` | 0, or 1 vision call per step that needs a figure but names none | the PDF, record.json | `out/<chair>/figures/<step>.png`; `figure` on each step |
| `label` | 1 vision call per photo | record.json, photos | part and zone labels in `out/<chair>/device.json`, `detections.json`, `devices/<chair>.json` |
| `render` | none | all of the above | `out/<chair>/labelled_<view>.png`, `card.html`, `REPORT.md` |

- Each stage reads the previous stage's file, so you can rerun one stage alone.
- Every AI request and reply is logged in `out/<chair>/llm_log/`. Results are also copied to `saved/<chair>/`.
- Once `library/<record_id>.json` and `devices/<chair>.json` exist, the web app uses them; no restart is needed.
- The label stage clears that chair's decisions, because they were about the old labels.
- `out/` and `saved/` are gitignored: they hold the full manual text and the photos.

**Handling zones.** The `handling` stage keeps only the sentences where the manual says where to lift or hold the chair, or what not to hold. A zone whose quote is not found is dropped. On the photos, a green circle with ✓ means "lift here" and a red square with ✗ (dashed box) means "do not hold". The shapes differ, so they still read in black and white. The owner confirms zones on /confirm like the other labels.

### With an API key

Put `LLM_PROVIDER`, `LLM_MODEL` and the matching key in `.env` (see `.env.example`). For Gemini on Vertex AI, set `GOOGLE_CLOUD_PROJECT` and `GOOGLE_CLOUD_LOCATION` and log in with gcloud. Calls take 40–60 s, so set `STAGE_TIMEOUT=180`.

```bash
.venv/bin/python -m pipeline chair-a
```

### Without a key (offline: a person or a coding agent plays the AI)

```bash
.venv/bin/python -m pipeline chair-a --provider offline
```

The pipeline stops with exit code 3 and prints `Waiting for offline response: <path>`. The `_request.md` file next to that path holds the full prompt and the image paths. Write only the JSON reply to that path, then run the command again. The code still checks every quote.

### Check the result

Open `out/<chair>/card.html` on a phone, and fill in the "right / wrong" column in `out/<chair>/REPORT.md`.

## Share a public link

The app listens on `0.0.0.0:8000`.

- **Same Wi-Fi:** open `http://<your-computer-ip>:8000` on the phone. On a Mac, `ipconfig getifaddr en0` shows the IP.
- **Anywhere:** use a Cloudflare quick tunnel (no account needed). Run `brew install cloudflared`, then `cloudflared tunnel --url http://localhost:8000`, and use the `https://<random>.trycloudflare.com` URL it prints. To make the QR codes point there, set `PUBLIC_BASE_URL` to that URL in `.env` and restart the app. Stop the tunnel with Ctrl-C when you are done.

## Print the card

Open `/passport/<chair_id>/print` in Chrome and press **Print**. The page sets A5 landscape with no margins. If Chrome adds headers or footers, untick "Headers and footers" under More settings.

## Deploy to Google Cloud Run

The deployed app serves saved results (`MODE=saved` is the default on Cloud Run), so it needs no AI key and no `.env`.

One-time setup:

```bash
gcloud auth login
gcloud config set project <PROJECT_ID>
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com
# Builds run as the default compute service account, which needs the Cloud Run Builder role:
gcloud projects add-iam-policy-binding <PROJECT_ID> \
  --member=serviceAccount:<PROJECT_NUMBER>-compute@developer.gserviceaccount.com --role=roles/run.builder
```

Each deploy (Cloud Run builds from your local folder, not from GitHub):

```bash
./scripts/prepare_deploy.sh      # copies photos, manuals and figure crops into deploy_data/
gcloud run deploy tagalong --source . --region asia-east2 \
  --allow-unauthenticated --max-instances 1 --memory 1Gi
```

- `.gcloudignore` decides what is uploaded. It keeps `deploy_data/` (gitignored) and leaves out `.env`, `data/`, `out/`, `saved/` and `.git`.
- `library/` and `devices/` are uploaded as they are on your disk, including results you haven't committed.
- Label decisions live inside the container, so `--max-instances 1` keeps them consistent. They are lost when the instance restarts.
- The QR codes use the service URL automatically. To use a different address, set `PUBLIC_BASE_URL` with `--set-env-vars`.

Try the image locally first (needs Docker):

```bash
./scripts/prepare_deploy.sh
docker build -t tagalong .
docker run --rm -p 8080:8080 -e PORT=8080 -e K_SERVICE=local tagalong   # http://localhost:8080
```

## Tests

```bash
.venv/bin/python -m pytest -q
```

They cover the §5 rules (SSR code, watt-hours), the must-do and confirmed-label rules, every page, the quote verifier, label coordinates (including EXIF rotation) and a full offline pipeline run.
