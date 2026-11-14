import re
from pathlib import Path

import segno
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from . import config, store, view

HERE = Path(__file__).resolve().parent
USES = {"checkin": "Check-in", "onboard": "On board", "return": "Return check"}
PHOTO_NAME = re.compile(r"^[a-z0-9_]+\.jpg$")

app = FastAPI(title="TagAlong")
app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
templates = Jinja2Templates(directory=HERE / "templates")


def _chair(chair_id):
    chair = store.chair(chair_id)
    if chair is None:
        raise HTTPException(404, "Unknown chair")
    return chair


def _record(record_id):
    record = store.record(record_id)
    if record is None:
        raise HTTPException(404, "Unknown model record")
    return record


def _page(request, name, **ctx):
    return templates.TemplateResponse(request, name, ctx)


def _passport_ctx(chair_id):
    chair = _chair(chair_id)
    record = _record(chair["record_id"])
    return {"chair": chair, "record": record, "v": view.passport(chair, record)}


# ---------- pages (DESIGN §2) ----------

@app.get("/")
def index(request: Request):
    chairs = [store.chair(cid) for cid in store.chair_ids()]
    cards = [{"chair": c, "name": view.chair_name(c)} for c in chairs]
    return _page(request, "index.html", cards=cards)


@app.get("/build/{chair_id}")
def build(request: Request, chair_id: str):
    return _page(request, "build.html", chair=_chair(chair_id))


@app.get("/confirm/{chair_id}")
def confirm(request: Request, chair_id: str):
    chair = _chair(chair_id)
    record = _record(chair["record_id"])
    labels = chair["labels"]
    return _page(
        request, "confirm.html", chair=chair,
        parts={p["id"]: p for p in record["parts"]},
        photos=view.photos_with_labels(chair, labels, max(2, len({l["photo"] for l in labels}))),
    )


@app.get("/passport/{chair_id}")
def passport(request: Request, chair_id: str):
    return _page(request, "passport.html", **_passport_ctx(chair_id))


@app.get("/passport/{chair_id}/print")
def passport_print(request: Request, chair_id: str):
    base = config.PUBLIC_URL or str(request.base_url).rstrip("/")
    qr = segno.make(f"{base}/passport/{chair_id}", error="m").svg_inline(dark="#044B52", omitsize=True)
    return _page(request, "print.html", qr=qr, **_passport_ctx(chair_id))


@app.get("/uses/{chair_id}/{use}")
def uses(request: Request, chair_id: str, use: str):
    if use not in USES:
        raise HTTPException(404, "Unknown use")
    return _page(request, f"uses_{use}.html", use_title=USES[use], **_passport_ctx(chair_id))


@app.get("/manual/{record_id}/{page}")
def manual_page(request: Request, record_id: str, page: int, step: str | None = None):
    """M1 stub: shows the quotes cited on this page. The page image comes with the PDFs (M2)."""
    record = _record(record_id)
    quotes = []
    for p in record["parts"]:
        quotes.append((f"Part: {p['name']['value']}", p["name"], None))
    for s in record["steps"]:
        quotes.append((s["action"], s["source"], s["id"]))
    for key, cited in record["facts"].items():
        for c in cited if isinstance(cited, list) else [cited]:
            quotes.append((key.replace("_", " ").capitalize(), c, None))
    quotes = [q for q in quotes if q[1].get("page") == page]
    return _page(request, "manual.html", record=record, page=page, step=step, quotes=quotes)


@app.get("/photo/{chair_id}/{name}")
def photo(chair_id: str, name: str):
    _chair(chair_id)
    if not PHOTO_NAME.match(name):
        raise HTTPException(404)
    path = config.DATA_DIR / "chairs" / chair_id / name
    if path.is_file():
        return FileResponse(path)
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 600">'
        '<rect width="800" height="600" fill="#0b5f66"/>'
        '<rect x="20" y="20" width="760" height="560" rx="24" fill="none" stroke="#C3AC86" '
        'stroke-width="4" stroke-dasharray="16 12"/>'
        f'<text x="400" y="290" fill="#C3AC86" font-family="sans-serif" font-size="44" '
        f'text-anchor="middle">{name}</text>'
        '<text x="400" y="350" fill="#ffffff" font-family="sans-serif" font-size="26" '
        'text-anchor="middle">Photo not in TAGALONG_DATA_DIR</text></svg>'
    )
    return Response(svg, media_type="image/svg+xml")


# ---------- pipeline API (DESIGN §4). M1: every stage returns the saved result. ----------

@app.post("/api/plate/{chair_id}")
def api_plate(chair_id: str):
    chair = _chair(chair_id)
    if "plate" not in chair["stages"]:
        chair["stages"].append("plate")
        store.save_chair(chair)
    return {"source": "saved", **chair["plate_read"]}


@app.post("/api/manual/{chair_id}")
def api_manual(chair_id: str):
    chair = _chair(chair_id)
    plate = chair["plate_read"]
    record = store.find_record(plate["make"], plate["model"])
    if record is None:
        return {"source": "saved", "found": None, "message": "No manual found → generic steps"}
    return {"source": "saved", "found": "library", "record_id": record["record_id"],
            "title": f"{record['make']} {record['model']}"}


@app.post("/api/label/{chair_id}")
def api_label(chair_id: str):
    chair = _chair(chair_id)
    if "label" not in chair["stages"]:
        chair["stages"].append("label")
        store.save_chair(chair)
    return {"source": "saved", "count": len(chair["labels"])}


class LabelDecision(BaseModel):
    status: str


@app.post("/api/labels/{chair_id}/{n}")
def api_label_decision(chair_id: str, n: int, body: LabelDecision):
    if body.status not in ("pending", "confirmed", "rejected"):
        raise HTTPException(422, "status must be pending, confirmed or rejected")
    chair = _chair(chair_id)
    label = next((l for l in chair["labels"] if l["n"] == n), None)
    if label is None:
        raise HTTPException(404, "Unknown label")
    label["status"] = body.status
    store.save_chair(chair)
    return {"n": n, "status": body.status,
            "pending": sum(l["status"] == "pending" for l in chair["labels"])}
