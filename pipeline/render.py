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
RED_FILL, RED_HATCH = (197, 34, 31, 64), (197, 34, 31, 170)   # 25% fill, darker hatching
FACT_KEYS = ["battery_type", "voltage", "capacity", "wh", "removable", "power_off", "weight", "size", "removable_parts"]

_env = Environment(loader=FileSystemLoader(Path(__file__).parent / "templates"),
                   autoescape=select_autoescape(["html"]))


def _radius(image):
    return max(8, round(0.03 * min(image.size)))


def _hatch(size, step, width):
    """Transparent tile with red diagonal lines, to lay over a no_hold box."""
    w, h = size
    tile = Image.new("RGBA", (max(1, w), max(1, h)), RED_FILL)
    d = ImageDraw.Draw(tile)
    for k in range(-h, w, step):
        d.line((k, h, k + h, 0), fill=RED_HATCH, width=width)
    return tile


def draw_zones(image, zones):
    """hold: green circle with a white check; no_hold: red rounded square with a white cross, its box
    filled red at 25% with diagonal hatching. The shapes differ, so they still read in black and white."""
    base = image.convert("RGBA")
    r = _radius(image)
    line = max(2, r // 4)
    for z in zones:
        if z.get("box"):
            x0, y0, x1, y1 = (round(v * s) for v, s in zip(z["box"], (base.width, base.height) * 2))
            if z["zone"] == "no_hold":
                base.alpha_composite(_hatch((x1 - x0, y1 - y0), step=max(6, r // 2), width=max(1, r // 8)), (x0, y0))
            else:
                ImageDraw.Draw(base).rectangle((x0, y0, x1, y1), outline=LIGHT_GREEN, width=max(2, r // 5))
    draw = ImageDraw.Draw(base)
    for z in zones:
        cx, cy = z["x"] * base.width, z["y"] * base.height
        if z["zone"] == "hold":
            draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=GREEN, outline=WHITE, width=max(2, r // 6))
            draw.line([(cx - 0.5 * r, cy), (cx - 0.12 * r, cy + 0.4 * r), (cx + 0.5 * r, cy - 0.42 * r)],
                      fill=WHITE, width=line, joint="curve")
        else:
            draw.rounded_rectangle((cx - r, cy - r, cx + r, cy + r), radius=round(r * 0.3), fill=RED,
                                   outline=WHITE, width=max(2, r // 6))
            k = 0.45 * r
            draw.line((cx - k, cy - k, cx + k, cy + k), fill=WHITE, width=line)
            draw.line((cx - k, cy + k, cx + k, cy - k), fill=WHITE, width=line)
    return base.convert("RGB")


def draw_labels(image, labels):
    """Gold filled circle, white outline, dark teal number; radius ~3% of the short side."""
    image = image.copy()
    draw = ImageDraw.Draw(image)
    r = _radius(image)
    font = ImageFont.load_default(size=round(r * 1.2))
    for l in labels:
        cx, cy = l["x"] * image.width, l["y"] * image.height
        draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=GOLD, outline=WHITE, width=max(2, r // 6))
        draw.text((cx, cy), str(l["n"]), fill=TEAL, font=font, anchor="mm")
    return image


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
    zone_photo = {l.get("zone_id"): l["photo"] for l in device["labels"] if l.get("zone")}
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
                      f" | {_fmt(d['x'])} | {_fmt(d['y'])} | {n or ''} |  |")

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
                marker = "yes" if zone_photo.get(z["id"]) == photo else ""
                md.append(f"| {z['id']} | {z['kind']} | {names[z['part_id']]} | {z['source']['page']} | yes | {photo}"
                          f" | {'yes' if d['visible'] else 'no'} | {_fmt(d['confidence'])} | {_fmt(d['x'])} | {_fmt(d['y'])}"
                          f" | {marker} |  |")
    return "\n".join(md) + "\n"


def run(chair_id):
    record = read_stage_file(chair_id, "record.json", "extract")
    pages_data = read_stage_file(chair_id, "pages.json", "pages")
    device = read_stage_file(chair_id, "device.json", "label")
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
            # Zones first, so the gold part numbers stay on top and readable.
            image = draw_zones(im.convert("RGB"), [l for l in on_photo if l.get("zone")])
            image = draw_labels(image, [l for l in on_photo if not l.get("zone")])
        path = out / f"labelled_{stem}.png"
        image.save(path)
        save_copy(chair_id, path)
        labelled[photo] = image

    v = view.passport(device, record, include_pending=True)
    with_labels = [p for p in labelled if any(l["photo"] == p for l in device["labels"])]
    shown = with_labels or list(labelled)[:2]
    html = _env.get_template("card.html").render(
        record=record, device=device, v=v, fact_keys=FACT_KEYS,
        photos=[{"name": p, "src": _jpeg_data_uri(labelled[p]),
                 "zones": any(l["photo"] == p and l.get("zone") for l in device["labels"])} for p in shown],
        sample_photos=bool(meta.get("sample_photos")),
    )
    (out / "card.html").write_text(html, encoding="utf-8")
    (out / "REPORT.md").write_text(build_report(chair_id, record, pages_data, device, detections, handling),
                                   encoding="utf-8")
    for name in ("card.html", "REPORT.md"):
        save_copy(chair_id, out / name)

    print(f"render: {len(labelled)} labelled photos, card.html, REPORT.md -> {out}")
