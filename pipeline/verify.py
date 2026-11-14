"""DESIGN §4.4: check every quote against the manual text, in code."""
import re
import unicodedata

from rapidfuzz import fuzz

THRESHOLD = 90
PAGE_CORRECTED = "page corrected by code"

_TABLE = str.maketrans({
    **dict.fromkeys("‐‑‒–—―−﹘﹣－", "-"),
    **dict.fromkeys("‘’‚‛′´`", "'"),
    **dict.fromkeys("“”„‟″«»", '"'),
    "­": None,  # soft hyphen
})


_CJK = r"[⺀-鿿豈-﫿]"


def normalise(text):
    """Lowercase, NFKC, unify quotes and dashes, join words hyphenated across line breaks, collapse whitespace.

    Whitespace next to a Chinese/Japanese character is dropped: those scripts use no spaces, so a
    space there only comes from a PDF line break.
    """
    t = unicodedata.normalize("NFKC", text or "").translate(_TABLE)
    t = re.sub(r"(\w)-[ \t]*\r?\n\s*(\w)", r"\1\2", t)
    t = re.sub(r"\s+", " ", t)
    t = re.sub(rf"\s+(?={_CJK})|(?<={_CJK})\s+", "", t)
    return t.strip().lower()


def normalise_pages(pages):
    """{page: text} -> {page: normalised text}."""
    return {n: normalise(t) for n, t in pages.items()}


def verify_cited(cited, norm_pages):
    """Set cited["verified"]; move the page if the quote is found on another page. Returns cited."""
    quote = normalise(cited.get("quote"))
    cited.pop("note", None)
    if not quote:
        cited["verified"] = False
        return cited
    page = cited.get("page")
    if page in norm_pages and fuzz.partial_ratio(quote, norm_pages[page]) >= THRESHOLD:
        cited["verified"] = True
        return cited
    best_score, best_page = max(((fuzz.partial_ratio(quote, t), -n) for n, t in norm_pages.items()),
                                default=(0, None))
    if best_score >= THRESHOLD:
        cited["page"] = -best_page
        cited["verified"] = True
        cited["note"] = PAGE_CORRECTED
    else:
        cited["verified"] = False
    return cited
