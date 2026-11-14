"""STAGE render (no LLM): labelled PNGs, a self-contained card.html, REPORT.md."""
import base64
import io
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from PIL import ImageDraw, ImageFont, Image

from app import view
from .common import out_dir, read_meta, read_stage_file, save_copy
from .label import resized_path

GOLD, TEAL, WHITE = "#C3AC86", "#044B52", "#FFFFFF"
FACT_KEYS = ["battery_type", "voltage", "capacity", "wh", "removable", "power_off", "weight", "size", "removable_parts"]

_env = Environment(loader=FileSystemLoader(Path(__file__).parent / "templates"),
                   autoescape=select_autoescape(["html"]))


def draw_labels(image, labels):
    """Gold filled circle, white outline, dark teal number; radius ~3% of the short side."""
    image = image.copy()
    draw = ImageDraw.Draw(image)
    r = max(8, round(0.03 * min(image.size)))
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


def build_report(chair_id, record, pages_data, device, detections):
    names = {p["id"]: p["name"]["value"] for p in record["parts"]}
    label_at = {(l["part_id"], l["photo"]): l["n"] for l in device["labels"]}
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
    return "\n".join(md) + "\n"


def run(chair_id):
    record = read_stage_file(chair_id, "record.json", "extract")
    pages_data = read_stage_file(chair_id, "pages.json", "pages")
    device = read_stage_file(chair_id, "device.json", "label")
    detections = read_stage_file(chair_id, "detections.json", "label")
    meta = read_meta(chair_id)
    out = out_dir(chair_id)

    labelled = {}
    for photo in detections["photos"]:
        stem = Path(photo).stem
        with Image.open(resized_path(chair_id, stem)) as im:
            image = draw_labels(im.convert("RGB"), [l for l in device["labels"] if l["photo"] == photo])
        path = out / f"labelled_{stem}.png"
        image.save(path)
        save_copy(chair_id, path)
        labelled[photo] = image

    v = view.passport(device, record, include_pending=True)
    with_labels = [p for p in labelled if any(l["photo"] == p for l in device["labels"])]
    shown = with_labels or list(labelled)[:2]
    html = _env.get_template("card.html").render(
        record=record, device=device, v=v, fact_keys=FACT_KEYS,
        photos=[{"name": p, "src": _jpeg_data_uri(labelled[p])} for p in shown],
        sample_photos=bool(meta.get("sample_photos")),
    )
    (out / "card.html").write_text(html, encoding="utf-8")
    (out / "REPORT.md").write_text(build_report(chair_id, record, pages_data, device, detections), encoding="utf-8")
    for name in ("card.html", "REPORT.md"):
        save_copy(chair_id, out / name)

    print(f"render: {len(labelled)} labelled photos, card.html, REPORT.md -> {out}")
