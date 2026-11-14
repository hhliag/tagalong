import re
from pathlib import Path

import segno
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from . import config, store, view

HERE = Path(__file__).resolve().parent
USES = {"checkin": "Check-in", "onboard": "On board", "return": "Return check"}
PHOTO_NAME = re.compile(r"^[a-z0-9_]+\.jpg$")
STEP_ID = re.compile(r"^s\d+$")
CONFIRM_VIEWS = ["left.jpg", "right.jpg", "front.jpg", "rear.jpg"]

app = FastAPI(title="TagAlong")
app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
templates = Jinja2Templates(directory=HERE / "templates")
templates.env.globals["letter"] = view.letter   # part codes A, B, C... from n


def fast_q(request):
    """"?fast=1" when the page was opened with it: every flow link keeps it and skips the step-done pages."""
    return "?fast=1" if request.query_params.get("fast") == "1" else ""


def flow_link(request, chair_id, step):
    """Where a page sends the owner after `step` (chosen | built | confirmed): its step-done page, or with
    ?fast=1 straight to the next page."""
    if fast_q(request):
        return view.STEP_DONE[step]["next"].format(c=chair_id) + fast_q(request)
    return f"/done/{chair_id}/{step}"


templates.env.globals["fast_q"] = fast_q
templates.env.globals["flow_link"] = flow_link


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


def _page(request, name, flow=None, **ctx):
    """flow: the step this page is in (view.FLOW key); draws the step bar."""
    if flow:
        chair = ctx.get("chair")
        ctx["steps"] = view.step_bar(flow, chair["chair_id"] if chair else None, fast_q(request))
    return templates.TemplateResponse(request, name, ctx)


def public_base(request):
    return config.PUBLIC_URL or str(request.base_url).rstrip("/")


def _passport_ctx(chair_id):
    chair = _chair(chair_id)
    record = _record(chair["record_id"])
    return {"chair": chair, "record": record, "v": view.passport(chair, record)}


# ---------- pages (DESIGN §2) ----------

@app.get("/")
def index(request: Request):
    chairs = [store.chair(cid) for cid in store.chair_ids()]
    cards = [{"chair": c, "name": view.chair_name(c)} for c in chairs]
    return _page(request, "index.html", flow="choose", cards=cards)


@app.get("/build/{chair_id}")
def build(request: Request, chair_id: str):
    return _page(request, "build.html", flow="build", chair=_chair(chair_id))


@app.get("/confirm/{chair_id}")
def confirm(request: Request, chair_id: str):
    chair = _chair(chair_id)
    record = _record(chair["record_id"])
    part_labels, zone_labels = view.split_labels(chair)
    # All four views, so the owner sees the whole chair; then any close-up that carries a label.
    files = CONFIRM_VIEWS + sorted({l["photo"] for l in chair["labels"] if l["photo"]} - set(CONFIRM_VIEWS))
    zones = {z["id"]: z for z in record.get("handling") or []}
    return _page(
        request, "confirm.html", flow="confirm", chair=chair, part_labels=part_labels, zone_labels=zone_labels, zones=zones,
        parts={p["id"]: p for p in record["parts"]},
        photos=[view.photo_entry(f, part_labels, zone_labels) for f in files],
    )


@app.get("/passport/{chair_id}")
def passport(request: Request, chair_id: str):
    return _page(request, "passport.html", flow="passport", **_passport_ctx(chair_id))


@app.get("/done/{chair_id}/{step}")
def step_done(request: Request, chair_id: str, step: str):
    """Between the main pages: what was just done, a QR to carry on on the phone, the next button."""
    if step not in view.STEP_DONE:
        raise HTTPException(404, "Unknown step")
    chair = _chair(chair_id)
    unfinished = view.step_is_done(step, chair)
    if unfinished:
        return RedirectResponse(unfinished + fast_q(request), status_code=303)
    info = view.STEP_DONE[step]
    next_url = info["next"].format(c=chair_id)
    if fast_q(request):
        return RedirectResponse(next_url + fast_q(request), status_code=303)
    record = _record(chair["record_id"])
    qr = segno.make(public_base(request) + next_url, error="m").svg_inline(dark="#044B52", omitsize=True)
    return _page(request, "done.html", flow=info["current"], chair=chair, info=info, next_url=next_url,
                 summary=view.step_summary(step, chair, record), qr=qr)


def crew_url(request, chair):
    """What the QR on the printed card opens: the crew view, found by the tag ID printed next to it."""
    return f"{public_base(request)}/crew/{chair['tag_id']}"


@app.get("/passport/{chair_id}/print")
def passport_print(request: Request, chair_id: str):
    ctx = _passport_ctx(chair_id)
    qr = segno.make(crew_url(request, ctx["chair"]), error="m").svg_inline(dark="#044B52", omitsize=True)
    return _page(request, "print.html", qr=qr, **ctx)


@app.get("/crew")
def crew_search(request: Request, tag: str | None = None):
    """Crew lookup: scan the QR on the chair's card, or type the tag ID."""
    if tag:
        chair = store.find_chair_by_tag(tag)
        if chair:
            return RedirectResponse(f"/crew/{chair['tag_id']}", status_code=303)
    return _page(request, "crew_search.html", tag=tag, not_found=bool(tag))


@app.get("/crew/{tag_id}")
def crew_view(request: Request, tag_id: str):
    chair = store.find_chair_by_tag(tag_id)
    if chair is None:
        return _page(request, "crew_search.html", tag=tag_id, not_found=True)
    return _page(request, "crew.html", **_passport_ctx(chair["chair_id"]))


@app.get("/uses/{chair_id}/{use}")
def uses(request: Request, chair_id: str, use: str):
    if use not in USES:
        raise HTTPException(404, "Unknown use")
    return _page(request, f"uses_{use}.html", flow="passport", use_title=USES[use], **_passport_ctx(chair_id))


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
    for z in record.get("handling") or []:
        quotes.append((f"{'Lift here' if z['kind'] == 'hold' else 'Do not lift by'}: {z['reason']}", z["source"], z["id"]))
    quotes = [q for q in quotes if q[1].get("page") == page]
    return _page(request, "manual.html", record=record, page=page, step=step, quotes=quotes)


@app.get("/figure/{chair_id}/{step_id}")
def figure(chair_id: str, step_id: str):
    """The manual figure a step refers to, cropped by the pipeline's figures stage."""
    _chair(chair_id)
    path = config.OUT_DIR / chair_id / "figures" / f"{step_id}.png"
    if not STEP_ID.match(step_id) or not path.is_file():
        raise HTTPException(404)
    return FileResponse(path)


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


@app.post("/api/labels/{chair_id}/{label_id}")
def api_label_decision(chair_id: str, label_id: int, body: LabelDecision):
    """One dot (part label or zone marker), by its unique id."""
    if body.status not in ("pending", "confirmed", "rejected"):
        raise HTTPException(422, "status must be pending, confirmed or rejected")
    chair = _chair(chair_id)
    label = next((l for l in chair["labels"] if l["id"] == label_id), None)
    if label is None:
        raise HTTPException(404, "Unknown label")
    label["status"] = body.status
    store.save_chair(chair)
    return {"id": label_id, "status": body.status,
            "pending": sum(l["status"] == "pending" for l in chair["labels"])}


class LabelMove(BaseModel):
    x: float
    y: float


@app.post("/api/labels/{chair_id}/{label_id}/move")
def api_label_move(chair_id: str, label_id: int, body: LabelMove):
    """The owner dragged a ring on /confirm: new centre in 0-1 fractions. A zone box moves with it."""
    chair = _chair(chair_id)
    label = next((l for l in chair["labels"] if l["id"] == label_id), None)
    if label is None or not label.get("photo"):
        raise HTTPException(404, "Unknown label")
    x, y = min(max(body.x, 0.0), 1.0), min(max(body.y, 0.0), 1.0)
    if label.get("box"):
        dx, dy = x - label["x"], y - label["y"]
        b = label["box"]
        label["box"] = [b[0] + dx, b[1] + dy, b[2] + dx, b[3] + dy]
    label["x"], label["y"] = x, y
    label["moved"] = True
    store.save_chair(chair)
    return {"id": label_id, "x": x, "y": y, "box": label.get("box")}


@app.post("/api/labels/{chair_id}")
def api_label_decision_all(chair_id: str, body: LabelDecision):
    """"Check all" on /confirm: every dot and zone marker gets the same status."""
    if body.status not in ("pending", "confirmed", "rejected"):
        raise HTTPException(422, "status must be pending, confirmed or rejected")
    chair = _chair(chair_id)
    for label in chair["labels"]:
        label["status"] = body.status
    store.save_chair(chair)
    return {"status": body.status, "count": len(chair["labels"]),
            "pending": sum(l["status"] == "pending" for l in chair["labels"])}
