"""STAGE label (vision LLM, one call per photo) -> devices/<chair_id>.json."""
import hashlib

from PIL import Image, ImageOps

from app import config, store, view
from . import llm
from .common import VIEWS, PipelineError, chair_dir, out_dir, read_meta, read_stage_file, save_copy, write_json

LONG_SIDE = 1024


def photo_files(chair_id):
    folder = chair_dir(chair_id)
    files = [folder / f"{v}.jpg" for v in VIEWS if (folder / f"{v}.jpg").is_file()]
    return files + sorted(folder.glob("closeup_*.jpg"))


def load_photo(path):
    """EXIF rotation FIRST, then long side -> 1024 px. This one image is used for the LLM and for drawing."""
    with Image.open(path) as im:
        im = ImageOps.exif_transpose(im).convert("RGB")
    scale = LONG_SIDE / max(im.size)
    return im.resize((round(im.width * scale), round(im.height * scale)), Image.LANCZOS)


def resized_path(chair_id, stem):
    return out_dir(chair_id) / "resized" / f"{stem}.jpg"


ZONE_NOTE = {"hold": "the manual says to hold or lift the chair here",
             "no_hold": "the manual says NOT to hold or lift the chair by this"}


def build_prompt(view_name, parts, size, gemini, zone_kinds=None):
    zone_kinds = zone_kinds or {}
    lines = [
        f"This is one photo of a wheelchair: the {view_name}. It is {size[0]} x {size[1]} pixels.",
        "Find each part below in this photo. The 'where' text is from the manufacturer's manual.",
        "Look only at the wheelchair in the centre of the photo, the one the photo is about. "
        "Ignore other wheelchairs in the background.",
        "",
        "PARTS",
    ]
    for p in parts:
        note = "; ".join(ZONE_NOTE[k] for k in zone_kinds.get(p["id"], []))
        lines.append(f"- {p['id']}: {p['name']['value']}. Where: {p['where'] or 'not stated'}"
                     + (f" (handling: {note})" if note else ""))
    lines += [
        "",
        "For every part give: visible (true only if you can see the part itself in this photo), "
        "confidence (0 to 1), and its location.",
    ]
    if gemini:
        lines.append('Location: "box_2d": [ymin, xmin, ymax, xmax], integers on a 0-1000 scale of the image '
                     "height and width, a tight box around the part.")
        example = '{"part_id": "...", "visible": true, "confidence": 0.8, "box_2d": [ymin, xmin, ymax, xmax]}'
    else:
        lines.append('Location: "x" and "y", the centre of the part as fractions 0-1 of the image width '
                     '(from the left) and height (from the top), and "box": [x0, y0, x1, y1], a tight box '
                     "around the part as fractions 0-1 (left, top, right, bottom).")
        example = '{"part_id": "...", "visible": true, "confidence": 0.8, "x": 0.5, "y": 0.5, "box": [0.4, 0.4, 0.6, 0.6]}'
    lines += ["If a part appears more than once in this photo (for example a lever on each side, or two footrests), "
              "give one entry per visible instance, each with its own tight box around that one instance.",
              "When a part is not visible, give one entry with visible false and no location.", "",
              f'Reply with JSON only: {{"parts": [{example}, ...]}}.']
    return "\n".join(lines)


def _clamp(v):
    return min(1.0, max(0.0, float(v)))


def to_box(det):
    """box_2d [ymin, xmin, ymax, xmax] on 0-1000, or box [x0, y0, x1, y1] fractions -> [x0, y0, x1, y1] fractions."""
    try:
        if det.get("box_2d") and len(det["box_2d"]) >= 4:
            ymin, xmin, ymax, xmax = (float(b) / 1000 for b in det["box_2d"][:4])
        elif det.get("box") and len(det["box"]) >= 4:
            xmin, ymin, xmax, ymax = (float(b) for b in det["box"][:4])
        else:
            return None
    except (TypeError, ValueError):
        return None
    x0, x1 = sorted((_clamp(xmin), _clamp(xmax)))
    y0, y1 = sorted((_clamp(ymin), _clamp(ymax)))
    return [round(x0, 4), round(y0, 4), round(x1, 4), round(y1, 4)]


def to_xy(det):
    """The box centre when there is a box; else x, y fractions. Clamped to 0-1."""
    box = to_box(det)
    if box:
        return (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
    try:
        if det.get("x") is not None and det.get("y") is not None:
            return _clamp(det["x"]), _clamp(det["y"])
    except (TypeError, ValueError):
        pass
    return None


def _confidence(v):
    try:
        return _clamp(v)
    except (TypeError, ValueError):
        return 0.0


MIN_CONFIDENCE = 0.5   # visible detections below this get no dot


def parse_detections(raw, part_ids):
    """Every visible instance of every part (a part can appear twice, e.g. left and right levers),
    plus one not-visible entry for each part that was not seen."""
    seen, not_seen = [], {}
    for det in raw.get("parts") or []:
        pid = det.get("part_id")
        if pid not in part_ids:
            continue
        xy = to_xy(det)
        conf = _confidence(det.get("confidence"))
        if det.get("visible") and xy is not None:
            seen.append({"part_id": pid, "visible": True, "confidence": conf,
                         "x": round(xy[0], 4), "y": round(xy[1], 4), "box": to_box(det)})
        else:
            not_seen.setdefault(pid, conf)
    seen_ids = {d["part_id"] for d in seen}
    missing = [{"part_id": pid, "visible": False, "confidence": not_seen.get(pid, 0.0), "x": None, "y": None,
                "box": None} for pid in part_ids if pid not in seen_ids]
    return seen + missing


def visible_on(detections, part_id):
    """[(photo, detection)] for every photo where the part is visible with enough confidence, in photo order."""
    return [(photo, d) for photo, dets in detections.items() for d in dets
            if d["part_id"] == part_id and d["visible"] and d["confidence"] >= MIN_CONFIDENCE]


def number_order(record):
    """Part ids in label order: first must_do step (phase order) that uses the part, then the rest."""
    phase = {key: i for i, (key, _) in enumerate(view.PHASES)}
    must = sorted((s for s in record["steps"] if s.get("must_do")), key=lambda s: phase[s["phase"]])
    order = []
    for s in must:
        if s.get("part_id") and s["part_id"] not in order:
            order.append(s["part_id"])
    return order + [p["id"] for p in record["parts"] if p["id"] not in order]


def make_labels(record, detections):
    """A dot on every photo where a part is visible. The same part keeps the same number n on every photo
    (n follows the first must_do step that uses the part); "id" is unique per dot, so the owner can
    confirm each dot on its own. Then zone labels the same way.

    A zone whose part is not visible in any photo still gets one label with photo null, so the owner
    can confirm it from the list on /confirm.
    """
    labels, n = [], 0
    for pid in number_order(record):
        hits = visible_on(detections, pid)
        if not hits:
            continue
        n += 1
        for photo, d in hits:
            labels.append({"id": len(labels) + 1, "part_id": pid, "n": n, "photo": photo, "x": d["x"], "y": d["y"],
                           "box": d.get("box"), "confidence": d["confidence"], "status": "pending", "zone": None})
    for z in record.get("handling") or []:
        for photo, d in visible_on(detections, z["part_id"]) or [(None, {})]:
            labels.append({"id": len(labels) + 1, "part_id": z["part_id"], "n": None, "photo": photo,
                           "x": d.get("x"), "y": d.get("y"), "box": d.get("box"),
                           "confidence": d.get("confidence", 0.0), "status": "pending",
                           "zone": z["kind"], "zone_id": z["id"]})
    return labels


def tag_id(chair_id):
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    digest = hashlib.sha256(chair_id.encode()).digest()
    return "AP-" + "".join(alphabet[b % len(alphabet)] for b in digest[:4])


def run(chair_id):
    record = read_stage_file(chair_id, "record.json", "extract")
    meta = read_meta(chair_id)
    photos = photo_files(chair_id)
    if not photos:
        raise PipelineError(f"No photos in {chair_dir(chair_id)} (left/right/front/rear.jpg).")
    if not record["parts"]:
        raise PipelineError("The record has no parts to label. Check the extract stage.")
    part_ids = [p["id"] for p in record["parts"]]
    gemini = llm.provider() == "gemini"
    zone_kinds = {}
    for z in record.get("handling") or []:
        zone_kinds.setdefault(z["part_id"], []).append(z["kind"])

    detections, sizes = {}, {}
    for path in photos:
        image = load_photo(path)
        resized = resized_path(chair_id, path.stem)
        resized.parent.mkdir(parents=True, exist_ok=True)
        image.save(resized, quality=90)
        view_name = (f"close-up of the {path.stem[len('closeup_'):].replace('_', ' ')}"
                     if path.stem.startswith("closeup_") else f"{path.stem} view")
        raw = llm.ask_json("label", build_prompt(view_name, record["parts"], image.size, gemini, zone_kinds),
                           images=[resized])
        detections[path.name] = parse_detections(raw, part_ids)
        sizes[path.name] = list(image.size)

    device = {
        "chair_id": chair_id,
        "tag_id": meta.get("tag_id") or tag_id(chair_id),
        "record_id": record["record_id"],
        "plate_read": {"make": meta["make"], "model": meta["model"], "raw": "from sample data"},
        "battery_original": meta.get("battery_original"),
        "labels": make_labels(record, detections),
        "removed_parts": meta.get("removed_parts"),
    }
    out = out_dir(chair_id)
    write_json(out / "detections.json", {"sizes": sizes, "photos": detections})
    write_json(out / "device.json", device)
    write_json(config.DEVICES_DIR / f"{chair_id}.json", device)
    for name in ("detections.json", "device.json"):
        save_copy(chair_id, out / name)
    store.reset(chair_id)  # the M1 pages must not keep decisions about the old labels

    names = {p["id"]: p["name"]["value"] for p in record["parts"]}
    part_labels = [l for l in device["labels"] if not l["zone"]]
    zone_labels = [l for l in device["labels"] if l["zone"]]
    placed = {}
    for l in part_labels:
        placed.setdefault((l["n"], l["part_id"]), []).append(l["photo"].rsplit(".", 1)[0])
    summary = ", ".join(f"{n} {names[pid]} ({'/'.join(ps)})" for (n, pid), ps in placed.items())
    zones = ", ".join(f"{l['zone']} {names[l['part_id']]} ({l['photo'] or 'not visible'})" for l in zone_labels)
    print(f"label: {len(photos)} photos, {len(placed)} of {len(part_ids)} parts placed, {len(part_labels)} dots: "
          f"{summary or 'none'}" + (f"; zones: {zones}" if zones else "") + f" -> devices/{chair_id}.json")
    return device
