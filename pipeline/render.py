"""STAGE render (no LLM): labelled PNGs, a self-contained card.html, REPORT.md."""
import base64
import io
import json
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from PIL import ImageDraw, ImageFont, Image

from app import view
from .common import out_dir, read_meta, read_stage_file, save_copy
from .label import resized_path

GOLD, TEAL, WHITE = "#C3AC86", "#044B52", "#FFFFFF"
GREEN, RED = "#1E8E3E", "#C5221F"
LIGHT_GREEN = (129, 201, 149, 255)
FACT_KEYS = ["battery_type", "voltage", "capacity", "wh", "removable", "power_off", "weight", "size", "removable_parts"]

_env = Environment(loader=FileSystemLoader(Path(__file__).parent / "templates"),
                   autoescape=select_autoescape(["html"]))


def _radius(image):
    return max(8, round(0.03 * min(image.size)))


JADE = "#005D63"
PIN_COLOUR = {"pending": GOLD, "confirmed": JADE}


def _ring(draw, cx, cy, r, colour):
    """Hollow ring: 3 px in the colour, with a 1 px white line outside and inside. The centre is untouched."""
    draw.ellipse((cx - r - 2, cy - r - 2, cx + r + 2, cy + r + 2), outline=WHITE, width=1)
    draw.ellipse((cx - r - 1, cy - r - 1, cx + r + 1, cy + r + 1), outline=colour, width=3)
    draw.ellipse((cx - r + 2, cy - r + 2, cx + r - 2, cy + r - 2), outline=WHITE, width=1)


def _dashed_rect(draw, box, colour, width, dash):
    x0, y0, x1, y1 = box
    for a, b, horizontal, fixed in ((x0, x1, True, y0), (x0, x1, True, y1), (y0, y1, False, x0), (y0, y1, False, x1)):
        for start in range(int(a), int(b), dash * 2):
            end = min(start + dash, b)
            line = (start, fixed, end, fixed) if horizontal else (fixed, start, fixed, end)
            draw.line(line, fill=colour, width=width)


def draw_markers(image, labels, zones=()):
    """Part pins (hollow ring + letter badge) and zone pins (ring + check/cross badge) on one photo.

    The badge side comes from app.view.pin_sides, the same rule as the HTML pages. Zone boxes are
    outlines only, so nothing covers the part itself.
    """
    image = image.copy()
    draw = ImageDraw.Draw(image)
    w, h = image.size
    r = _radius(image)
    rb = max(7, round(r * 0.7))
    offset = view.PIN_OFFSET * min(w, h)
    font = ImageFont.load_default(size=round(rb * 1.3))
    sides = view.pin_sides([(view.label_key(m), m["x"], m["y"]) for m in [*zones, *labels]])
    vectors = {name: (sx, sy) for name, sx, sy in view.PIN_SIDES}

    for z in zones:
        if z.get("box"):
            box = (z["box"][0] * w, z["box"][1] * h, z["box"][2] * w, z["box"][3] * h)
            if z["zone"] == "hold":
                draw.rectangle(box, outline=LIGHT_GREEN, width=2)
            else:
                _dashed_rect(draw, box, RED, width=3, dash=max(6, r // 2))

    for m in [*zones, *labels]:
        cx, cy = m["x"] * w, m["y"] * h
        zone = m.get("zone")
        colour = (GREEN if zone == "hold" else RED) if zone else PIN_COLOUR.get(m.get("status"), GOLD)
        sx, sy = vectors[sides[view.label_key(m)]]
        bx, by = cx + sx * offset, cy + sy * offset
        unit = 0.7071
        line = (cx + sx * unit * (r + 2), cy + sy * unit * (r + 2), bx - sx * unit * rb, by - sy * unit * rb)
        draw.line(line, fill=WHITE, width=4)
        draw.line(line, fill=colour, width=2)
        _ring(draw, cx, cy, r, colour)
        if zone == "no_hold":
            draw.rounded_rectangle((bx - rb, by - rb, bx + rb, by + rb), radius=round(rb * 0.3), fill=colour,
                                   outline=WHITE, width=2)
            k = 0.45 * rb
            draw.line((bx - k, by - k, bx + k, by + k), fill=WHITE, width=max(2, rb // 4))
            draw.line((bx - k, by + k, bx + k, by - k), fill=WHITE, width=max(2, rb // 4))
        else:
            draw.ellipse((bx - rb, by - rb, bx + rb, by + rb), fill=colour, outline=WHITE, width=2)
            if zone == "hold":
                draw.line([(bx - 0.5 * rb, by), (bx - 0.12 * rb, by + 0.4 * rb), (bx + 0.5 * rb, by - 0.42 * rb)],
                          fill=WHITE, width=max(2, rb // 4), joint="curve")
            else:
                text_colour = TEAL if colour == GOLD else WHITE
                draw.text((bx, by), view.letter(m["n"]), fill=text_colour, font=font, anchor="mm")
    return image


def draw_labels(image, labels):
    return draw_markers(image, labels)


def draw_zones(image, zones):
    return draw_markers(image, [], zones)


def _jpeg_data_uri(image):
    buf = io.BytesIO()
    image.save(buf, format="JPEG", quality=82)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def _cited_items(record):
    """(what, cited) for every quote in the record, for the report."""
    items = [(f"part {p['id']}", p["name"]) for p in record["parts"]]
    items += [(f"step {s['id']}", s["source"]) for s in record["steps"]]
    for key, c in record["facts"].items():
        for one in c if isinstance(c, list) else [c]:
            items.append((f"fact {key}", one))
    return [(w, c) for w, c in items if c.get("quote")]


def _fmt(v):
    return "" if v is None else f"{v:.2f}" if isinstance(v, float) else str(v)


def build_report(chair_id, record, pages_data, device, detections, handling=None):
    names = {p["id"]: p["name"]["value"] for p in record["parts"]}
    label_at = {(l["part_id"], l["photo"]): l["n"] for l in device["labels"] if not l.get("zone")}
    zone_photos = {}
    for l in device["labels"]:
        if l.get("zone"):
            zone_photos.setdefault(l["zone_id"], set()).add(l["photo"])
    cited = _cited_items(record)
    failed = [(w, c) for w, c in cited if not c["verified"]]
    corrected = [(w, c) for w, c in cited if c.get("note")]
    must = [s for s in record["steps"] if s["must_do"]]
    built = record.get("built_with") or {}

    md = [f"# Pipeline report: {chair_id}", "",
          f"{record['make']} {record['model']} · record `{record['record_id']}` · built {record['built_at']}"
          f" with {built.get('provider')} / {built.get('model') or '-'}", ""]
    md += ["## Manual", "",
           f"- File: {pages_data['manual_file']} ({pages_data['page_count']} pages, sha256 {pages_data['sha256'][:12]}…)",
           f"- Pages kept: {', '.join(map(str, pages_data['kept']))}",
           f"- Spec page: {pages_data['spec_page'] or 'none found'}",
           f"- Model name in the first pages: {'yes' if pages_data['model_found_in_first_pages'] else 'NO, check the manual'}",
           ""]
    md += [f"## Steps: {len(record['steps'])} found, {len(must)} must-do", "",
           "| id | phase | must do | verified | page | action |", "| --- | --- | --- | --- | --- | --- |"]
    md += [f"| {s['id']} | {s['phase']} | {'yes' if s['must_do'] else ''} | {'yes' if s['source']['verified'] else 'NO'}"
           f" | {s['source']['page'] or ''} | {s['action']} |" for s in record["steps"]]
    md += ["", f"## Quotes: {len(cited) - len(failed)} of {len(cited)} verified", ""]
    if failed:
        md += ["Not found in the manual:", ""]
        md += [f"- {w} (cited p. {c.get('page') or '?'}): \"{c['quote']}\"" for w, c in failed]
        md.append("")
    if corrected:
        md += ["Page corrected by code:", ""]
        md += [f"- {w}: now p. {c['page']}: \"{c['quote']}\"" for w, c in corrected]
        md.append("")
    md += ["## Facts missing from the manual", ""]
    md += [f"- {k}" for k in record["missing"]] or ["- none"]
    md += ["", "## Labels: part × photo", "",
           "Fill the last column after looking at the labelled photos.", "",
           "| part | photo | visible | confidence | x | y | label | right / wrong |",
           "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for photo, dets in detections["photos"].items():
        for d in dets:
            n = label_at.get((d["part_id"], photo))
            md.append(f"| {names[d['part_id']]} | {photo} | {'yes' if d['visible'] else 'no'} | {_fmt(d['confidence'])}"
                      f" | {_fmt(d['x'])} | {_fmt(d['y'])} | {view.letter(n) if n else ''} |  |")

    if "handling" in record:
        zones = record["handling"]
        hold = sum(z["kind"] == "hold" for z in zones)
        md += ["", f"## Handling zones: {hold} hold, {len(zones) - hold} no_hold", ""]
        if record.get("handling_missing"):
            md += ["The manual gives no lifting or holding guidance.", ""]
        md += [f"- {z['id']} {z['kind']} {names[z['part_id']]} (p. {z['source']['page']}"
               f"{', page corrected by code' if z['source'].get('note') else ''}): \"{z['source']['quote']}\"" for z in zones]
        dropped = (handling or {}).get("dropped", []) + (handling or {}).get("conflicts", [])
        if dropped:
            md += ["", "Dropped (not on the card):", ""]
            md += [f"- {z['kind']} {z['part_id']}: {z['why']}: \"{z['source'].get('quote')}\" (cited p. {z['source'].get('page') or '?'})"
                   for z in dropped]
        md += ["", "### Zones: zone × photo", "",
               "Fill the last column after looking at the green ✓ / red ✗ markers.", "",
               "| zone | kind | part | page | verified | photo | visible | confidence | x | y | marker | right / wrong |",
               "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
        for z in zones:
            for photo, dets in detections["photos"].items():
                d = next((d for d in dets if d["part_id"] == z["part_id"]), None)
                if not d:
                    continue
                marker = "yes" if photo in zone_photos.get(z["id"], set()) else ""
                md.append(f"| {z['id']} | {z['kind']} | {names[z['part_id']]} | {z['source']['page']} | yes | {photo}"
                          f" | {'yes' if d['visible'] else 'no'} | {_fmt(d['confidence'])} | {_fmt(d['x'])} | {_fmt(d['y'])}"
                          f" | {marker} |  |")
    return "\n".join(md) + "\n"


def run(chair_id):
    record = read_stage_file(chair_id, "record.json", "extract")
    pages_data = read_stage_file(chair_id, "pages.json", "pages")
    device = read_stage_file(chair_id, "device.json", "label")
    for label in device["labels"]:
        label.setdefault("id", label["n"])  # device.json from before dots had their own id
    detections = read_stage_file(chair_id, "detections.json", "label")
    meta = read_meta(chair_id)
    out = out_dir(chair_id)
    handling_path = out / "handling.json"
    handling = json.loads(handling_path.read_text(encoding="utf-8")) if handling_path.is_file() else None

    labelled = {}
    for photo in detections["photos"]:
        stem = Path(photo).stem
        on_photo = [l for l in device["labels"] if l["photo"] == photo]
        with Image.open(resized_path(chair_id, stem)) as im:
            # Zones first, so the part pins stay on top and readable.
            image = draw_markers(im.convert("RGB"), [l for l in on_photo if not l.get("zone")],
                                 [l for l in on_photo if l.get("zone")])
        path = out / f"labelled_{stem}.png"
        image.save(path)
        save_copy(chair_id, path)
        labelled[photo] = image

    v = view.passport(device, record, include_pending=True)
    figures = {}
    for s in record["steps"]:
        fig = out / "figures" / f"{s['id']}.png"
        if s.get("figure") and fig.is_file():
            with Image.open(fig) as im:
                figures[s["id"]] = _jpeg_data_uri(im.convert("RGB"))
    with_labels = [p for p in labelled if any(l["photo"] == p for l in device["labels"])]
    shown = with_labels or list(labelled)[:2]
    html = _env.get_template("card.html").render(
        record=record, device=device, v=v, fact_keys=FACT_KEYS,
        photos=[{"name": p, "src": _jpeg_data_uri(labelled[p]),
                 "zones": any(l["photo"] == p and l.get("zone") for l in device["labels"])} for p in shown],
        sample_photos=bool(meta.get("sample_photos")), figures=figures,
    )
    (out / "card.html").write_text(html, encoding="utf-8")
    (out / "REPORT.md").write_text(build_report(chair_id, record, pages_data, device, detections, handling),
                                   encoding="utf-8")
    for name in ("card.html", "REPORT.md"):
        save_copy(chair_id, out / name)

    print(f"render: {len(labelled)} labelled photos, card.html, REPORT.md -> {out}")
