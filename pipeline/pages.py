"""STAGE pages (no LLM): manual text per page, keep the pages that matter."""
import hashlib
import re

import pymupdf

from app import config
from .common import PipelineError, out_dir, read_meta, save_copy, write_json

KEYWORDS = [
    "freewheel", "free wheel", "brake release", "clutch", "manual mode", "battery", "lithium",
    "wh", "voltage", "power off", "power switch", "key", "lift", "carry", "transport", "aircraft",
    "airline", "fold", "disassemble", "remove", "detach", "weight", "dimension", "warning", "caution",
]
# Short words must match whole words ("wh" not in "when", "key" not in "keyboard");
# the others also match their inflections ("removed", "lifting", "dimensions").
WHOLE_WORD = {"wh", "key"}
SPEC_TERMS = ["specification", "weight", "dimension", "voltage", "kg", "mm", "ah", "wh", "km/h"]
KEEP_TOP = 15
MODEL_CHECK_PAGES = 5


def _pattern(word):
    tail = r"\b" if word in WHOLE_WORD else ""
    return re.compile(r"\b" + re.escape(word).replace(r"\ ", r"[\s-]*") + tail, re.IGNORECASE)


KEYWORD_RES = {k: _pattern(k) for k in KEYWORDS}
SPEC_RES = [re.compile(r"\b" + re.escape(t) + r"\b", re.IGNORECASE) for t in SPEC_TERMS]


def score_page(text):
    """(distinct keywords found, total matches): pages that touch many topics rank first."""
    counts = [len(r.findall(text)) for r in KEYWORD_RES.values()]
    return sum(1 for c in counts if c), sum(counts)


def spec_score(text):
    return sum(len(r.findall(text)) for r in SPEC_RES)


def read_pdf(path):
    if not path.is_file():
        raise PipelineError(f"Manual not found: {path}")
    with open(path, "rb") as f:
        if f.read(5) != b"%PDF-":
            raise PipelineError(f"Not a PDF: {path}")
    try:
        doc = pymupdf.open(path)
    except Exception as e:  # PyMuPDF raises several types for broken files
        raise PipelineError(f"Cannot open PDF {path}: {e}") from e
    with doc:
        return [page.get_text() for page in doc]


def _model_key(s):
    return re.sub(r"[^a-z0-9]", "", s.lower())


def run(chair_id):
    meta = read_meta(chair_id)
    pdf = config.DATA_DIR / "manuals" / meta["manual"]
    texts = read_pdf(pdf)

    pages = []
    for n, text in enumerate(texts, 1):
        distinct, total = score_page(text)
        pages.append({"page": n, "text": text, "score": [distinct, total], "spec_score": spec_score(text)})

    ranked = sorted((p for p in pages if p["score"][0]), key=lambda p: (-p["score"][0], -p["score"][1], p["page"]))
    kept = {p["page"] for p in ranked[:KEEP_TOP]}
    spec = max(pages, key=lambda p: (p["spec_score"], -p["page"]), default=None)
    spec_page = spec["page"] if spec and spec["spec_score"] else None
    if spec_page:
        kept.add(spec_page)

    first = _model_key(" ".join(texts[:MODEL_CHECK_PAGES]))
    model_found = _model_key(meta["model"]) in first
    empty = sum(1 for t in texts if not t.strip())

    result = {
        "chair_id": chair_id,
        "make": meta["make"],
        "model": meta["model"],
        "manual_file": meta["manual"],
        "manual_url": meta.get("manual_url"),
        "sha256": hashlib.sha256(pdf.read_bytes()).hexdigest(),
        "page_count": len(texts),
        "kept": sorted(kept),
        "spec_page": spec_page,
        "model_found_in_first_pages": model_found,
        "pages": pages,
    }
    path = out_dir(chair_id) / "pages.json"
    write_json(path, result)
    save_copy(chair_id, path)

    print(f"pages: {len(texts)} pages in {pdf.name}; kept {len(kept)}: {', '.join(map(str, sorted(kept)))}"
          f" (spec page: {spec_page or 'none found'})")
    if not model_found:
        print(f"WARNING: model name '{meta['model']}' not found in the first {MODEL_CHECK_PAGES} pages. Is this the right manual?")
    if empty > len(texts) / 2:
        print(f"WARNING: {empty} of {len(texts)} pages have no text. The PDF may be scanned and need OCR.")
    return result
