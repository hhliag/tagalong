"""STAGE figures: crop the manual figure a step refers to. The LLM never describes the figure.

Order for each step:
1. figure_ref (the caption the manual text names, e.g. "見圖4.10", copied by extract) -> that figure.
2. The step "needs a figure" (its quote says 圖/處/Fig/position/a marker letter) but has no usable
   figure_ref: one vision call with the page image asks ONLY which caption on the page the sentence
   refers to. Shown with the chip "Figure matched by AI".
3. Otherwise the whole cited page.
"""
import re
import unicodedata

import pymupdf

from app import config
from . import llm
from .common import out_dir, read_meta, read_stage_file, save_copy, write_json

NEEDS_WORD = re.compile(r"圖|图|處|处|\bfig|figure|position", re.IGNORECASE)
NEEDS_LETTER = re.compile(r"(?<![A-Za-z])[A-H](?![A-Za-z])")   # "拉到A 處", "position B"
CAPTION = re.compile(r"^(圖|图|Fig\.?|Figure)\s*\d+(\s*[\.\-]\s*\d+)?$", re.IGNORECASE)
CAPTION_HEAD = re.compile(r"^(圖|图|Fig\.?|Figure)$", re.IGNORECASE)
CAPTION_NUM = re.compile(r"^\d+(\s*[\.\-]\s*\d+)?$")
MIN_FIGURE_SIDE = 30      # points; smaller images are glyphs or icons, not figures
ZOOM = 2


def needs_figure(quote):
    quote = quote or ""
    return bool(NEEDS_WORD.search(quote) or NEEDS_LETTER.search(quote))


def caption_key(text):
    """'圖 4.10', '图4.10', 'Fig. 4-10' -> one comparable key."""
    t = unicodedata.normalize("NFKC", text or "")
    t = re.sub(r"\s+", "", t).replace("图", "圖")
    t = re.sub(r"(?i)^(figure|fig\.?)", "fig", t)
    return t.replace("-", ".").lower()


def _captions(page):
    """[(label, rect)] for captions on the page. A caption can be split in two words ("圖" + "4.1")."""
    words = sorted(page.get_text("words"), key=lambda w: (round((w[1] + w[3]) / 2), w[0]))
    found = []
    for i, w in enumerate(words):
        text, rect = w[4].strip(), pymupdf.Rect(w[:4])
        if CAPTION.match(text):
            found.append((text, rect))
        elif CAPTION_HEAD.match(text) and i + 1 < len(words):
            nxt = words[i + 1]
            same_row = abs((nxt[1] + nxt[3]) / 2 - (w[1] + w[3]) / 2) < 4
            if same_row and 0 <= nxt[0] - w[2] < 15 and CAPTION_NUM.match(nxt[4].strip()):
                found.append((f"{text}{nxt[4].strip()}", rect | pymupdf.Rect(nxt[:4])))
    return found


def _figure_boxes(page):
    """Image blocks and drawing clusters big enough to be a figure (not the whole page frame)."""
    boxes = [pymupdf.Rect(i["bbox"]) for i in page.get_image_info()]
    boxes += [pymupdf.Rect(r) for r in page.cluster_drawings()]
    page_area = page.rect.width * page.rect.height
    return [b for b in boxes
            if b.width >= MIN_FIGURE_SIDE and b.height >= MIN_FIGURE_SIDE and b.width * b.height < 0.5 * page_area]


def build_index(doc):
    """{caption key: [{page, label, rect, caption_rect}]}: each caption + the figure directly above it."""
    index = {}
    for page in doc:
        boxes = _figure_boxes(page)
        for label, cap in _captions(page):
            cx = (cap.x0 + cap.x1) / 2
            above = [b for b in boxes if b.y1 <= cap.y0 + 5 and b.x0 - 10 <= cx <= b.x1 + 10]
            if not above:
                continue
            fig = min(above, key=lambda b: cap.y0 - b.y1)
            index.setdefault(caption_key(label), []).append({
                "page": page.number + 1, "label": label,
                "rect": [round(v, 1) for v in fig], "caption_rect": [round(v, 1) for v in cap],
            })
    return index


def _lookup(index, key, page):
    entries = index.get(key) or []
    return next((e for e in entries if e["page"] == page), entries[0] if entries else None)


def _render(doc, page_no, rect, path):
    page = doc[page_no - 1]
    if rect is None:
        clip = page.rect
    else:
        r = pymupdf.Rect(rect)
        mx, my = r.width * 0.05, r.height * 0.05
        clip = (r + (-mx, -my, mx, my)) & page.rect
    page.get_pixmap(matrix=pymupdf.Matrix(ZOOM, ZOOM), clip=clip).save(path)


def _crop_rect(entry):
    return list(pymupdf.Rect(entry["rect"]) | pymupdf.Rect(entry["caption_rect"]))


def ask_caption(doc, chair_id, page_no, quote, labels):
    """Vision fallback: which caption on this page does the sentence refer to? Returns a label or None."""
    image = out_dir(chair_id) / "figures" / f"page_{page_no}.png"
    _render(doc, page_no, None, image)
    prompt = "\n".join([
        f"This is page {page_no} of a wheelchair manual. Captions on this page: {', '.join(labels)}.",
        f"Sentence from this page: \"{quote}\"",
        "Which caption id on this page does this sentence refer to? Answer only from what the page shows; "
        "do not describe the figure.",
        'Reply with JSON only: {"caption": "<one of the captions above>"} or {"caption": null}.',
    ])
    answer = llm.ask_json("figures", prompt, images=[image]).get("caption")
    return answer if answer and caption_key(answer) in {caption_key(l) for l in labels} else None


def run(chair_id):
    record = read_stage_file(chair_id, "record.json", "extract")
    meta = read_meta(chair_id)
    folder = out_dir(chair_id) / "figures"
    folder.mkdir(parents=True, exist_ok=True)
    counts = {"manual_text": 0, "ai": 0, "page": 0}

    with pymupdf.open(config.DATA_DIR / "manuals" / meta["manual"]) as doc:
        index = build_index(doc)
        for step in record["steps"]:
            step.pop("figure", None)
            quote, page_no = step["source"].get("quote"), step["source"].get("page")
            if not page_no or not (step.get("figure_ref") or needs_figure(quote)):
                continue
            entry = _lookup(index, caption_key(step.get("figure_ref")), page_no) if step.get("figure_ref") else None
            matched_by = "manual_text" if entry else None
            if entry is None:
                labels = [e["label"] for entries in index.values() for e in entries if e["page"] == page_no]
                if labels:
                    label = ask_caption(doc, chair_id, page_no, quote, labels)
                    entry = _lookup(index, caption_key(label), page_no) if label else None
                    matched_by = "ai" if entry else None
            path = folder / f"{step['id']}.png"
            if entry:
                _render(doc, entry["page"], _crop_rect(entry), path)
                step["figure"] = {"file": f"figures/{path.name}", "page": entry["page"], "caption": entry["label"],
                                  "matched_by": matched_by}
            else:
                _render(doc, page_no, None, path)
                step["figure"] = {"file": f"figures/{path.name}", "page": page_no, "caption": None,
                                  "matched_by": "page"}
                matched_by = "page"
            counts[matched_by] += 1
            save_copy(chair_id, path)

    out = out_dir(chair_id)
    write_json(out / "figures.json", {"index": index})
    for path in (out / "record.json", config.LIBRARY_DIR / f"{record['record_id']}.json"):
        write_json(path, record)
    for name in ("figures.json", "record.json"):
        save_copy(chair_id, out / name)
    print(f"figures: {sum(len(v) for v in index.values())} captions indexed; steps with a figure: "
          f"{counts['manual_text']} named in the text, {counts['ai']} matched by AI, {counts['page']} whole page")
    return record
