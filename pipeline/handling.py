"""STAGE handling (one text LLM call): where the manual says to hold / lift the chair, and what not to hold.

Core rule: a zone exists only if the manual states it with an exact quote. Zones whose quote is not
found are dropped completely, because a wrong "lift here" is dangerous.
"""
import re

from app import config
from . import llm, verify
from .common import out_dir, read_stage_file, save_copy, write_json
from .extract import _cited, _snake

KINDS = ["hold", "no_hold"]
MAX_EXTRA_PAGES = 10
KEYWORDS = [
    "lift", "carry", "hold", "grip", "grasp", "handle", "do not lift", "never lift", "must not",
    "detachable", "removable", "armrest", "footrest", "push handle", "frame",
    # Chinese (Traditional, then Simplified where it differs)
    "抬", "提起", "向上提", "搬", "握", "抓", "扶手", "腳踏", "脚踏", "踏腳板", "踏脚板", "擱腳板", "搁脚板", "推把",
    "車架", "车架", "提手", "不要", "禁止", "不可", "拆卸", "可拆",
]
_KEYWORD_RES = [re.compile(re.escape(k), re.IGNORECASE) for k in KEYWORDS]

RULES = """You find HANDLING ZONES in a wheelchair maker's manual for airline ground staff:
where the chair may be held or lifted ("hold"), and which parts must NOT be held or lifted by ("no_hold").

RULES
1. List only statements where the manual itself says where to hold or lift the chair, or what NOT to hold or lift it by. Never infer a hold point from a picture, a part's shape or common sense.
2. Copy each "quote" EXACTLY from the page text: at most 25 words (Chinese or Japanese: at most 60 characters), no paraphrase, no translation, no fixing typos.
3. "page" is the n of the [[PAGE n]] marker of the page where the quote is.
4. "reason" (at most ~15 words or 30 Chinese characters) may only shorten its own quote, in the quote's language.
5. "part_id": use an id from KNOWN PARTS when it fits. Otherwise make a new snake_case id and also give "part_name" (value: the part's name exactly as the manual writes it, in the manual's language; page and exact quote naming the part) and "where" (short text from the manual saying where the part is).
6. If the manual gives no such statement, return {"handling": [], "handling_missing": true}.
7. Reply with the JSON object only."""

_cited_schema = {
    "type": ["object", "null"],
    "properties": {"value": {"type": "string"}, "page": {"type": "integer"}, "quote": {"type": "string"}},
}
SCHEMA = {
    "type": "object",
    "required": ["handling", "handling_missing"],
    "properties": {
        "handling": {"type": "array", "items": {
            "type": "object", "required": ["kind", "part_id", "reason", "source"],
            "properties": {
                "kind": {"enum": KINDS},
                "part_id": {"type": "string"},
                "part_name": _cited_schema,
                "where": {"type": ["string", "null"]},
                "reason": {"type": "string"},
                "source": {"type": "object", "required": ["page", "quote"],
                           "properties": {"page": {"type": "integer"}, "quote": {"type": "string"}}},
            }}},
        "handling_missing": {"type": "boolean"},
    },
}


def pick_pages(pages_data):
    """The extract stage's kept pages + up to 10 more pages that talk about lifting or holding."""
    kept = set(pages_data["kept"])
    scored = []
    for p in pages_data["pages"]:
        if p["page"] in kept:
            continue
        text = verify.normalise(p["text"])
        hits = sum(len(r.findall(text)) for r in _KEYWORD_RES)
        if hits:
            scored.append((-hits, p["page"]))
    extra = [n for _, n in sorted(scored)[:MAX_EXTRA_PAGES]]
    return sorted(kept | set(extra))


def build_prompt(pages_data, record, page_numbers):
    by_page = {p["page"]: p["text"] for p in pages_data["pages"]}
    known = "\n".join(f"- {p['id']}: {p['name']['value']} (where: {p['where'] or 'not stated'})" for p in record["parts"])
    body = "\n\n".join(f"[[PAGE {n}]]\n{by_page[n].strip()}" for n in page_numbers)
    return f"{RULES}\n\nMANUAL: {record['make']} {record['model']}\n\nKNOWN PARTS\n{known}\n\n{body}"


def build_handling(raw, record, pages_data):
    """Verify zones, drop the unverified ones, apply the conflict rule. Returns (record, report)."""
    norm = verify.normalise_pages({p["page"]: p["text"] for p in pages_data["pages"]})
    parts = {p["id"]: p for p in record["parts"]}
    new_parts, zones, dropped = [], [], []

    for z in raw.get("handling") or []:
        kind = z.get("kind")
        source = _cited(z.get("source"), with_value=False)
        part_id = _snake(z.get("part_id"))
        entry = {"kind": kind, "part_id": part_id, "reason": (z.get("reason") or "").strip(), "source": source}
        if kind not in KINDS or not part_id or not source["quote"]:
            dropped.append({**entry, "why": "incomplete zone (kind, part or quote missing)"})
            continue
        verify.verify_cited(source, norm)
        if not source["verified"]:
            dropped.append({**entry, "why": "quote not found in the manual"})
            continue
        if part_id not in parts:
            name = _cited(z.get("part_name"))
            name["value"] = name["value"] or part_id.replace("_", " ").capitalize()
            verify.verify_cited(name, norm)
            part = {"id": part_id, "name": name, "where": z.get("where") or "", "count": 1}
            parts[part_id] = part
            new_parts.append(part)
        zones.append({**entry, "verified": True})

    # Conflict rule: a part that is both hold and no_hold keeps only no_hold.
    no_hold_parts = {z["part_id"] for z in zones if z["kind"] == "no_hold"}
    conflicts = [z for z in zones if z["kind"] == "hold" and z["part_id"] in no_hold_parts]
    zones = [z for z in zones if z not in conflicts]

    # Only keep new parts that a surviving zone uses.
    used = {z["part_id"] for z in zones}
    record["parts"] += [p for p in new_parts if p["id"] in used]
    record["handling"] = [{"id": f"h{i}", **z} for i, z in enumerate(zones, 1)]
    record["handling_missing"] = not zones
    report = {
        "dropped": dropped,
        "conflicts": [{**z, "why": "part is also no_hold: hold dropped"} for z in conflicts],
    }
    return record, report


def run(chair_id):
    pages_data = read_stage_file(chair_id, "pages.json", "pages")
    record = read_stage_file(chair_id, "record.json", "extract")
    page_numbers = pick_pages(pages_data)
    raw = llm.ask_json("handling", build_prompt(pages_data, record, page_numbers), schema=SCHEMA)
    record, report = build_handling(raw, record, pages_data)

    out = out_dir(chair_id)
    write_json(out / "handling.json", {"pages_used": page_numbers, "zones": record["handling"], **report})
    for path in (out / "record.json", config.LIBRARY_DIR / f"{record['record_id']}.json"):
        write_json(path, record)
    for name in ("handling.json", "record.json"):
        save_copy(chair_id, out / name)

    hold = sum(z["kind"] == "hold" for z in record["handling"])
    no_hold = len(record["handling"]) - hold
    dropped = len(report["dropped"]) + len(report["conflicts"])
    print(f"handling: {hold} hold, {no_hold} no_hold, {dropped} dropped (pages {', '.join(map(str, page_numbers))})"
          + ("  -> the manual gives no lifting or holding guidance" if record["handling_missing"] else ""))
    return record
