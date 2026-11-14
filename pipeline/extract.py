"""STAGE extract (one text-only LLM call) + verify + code-only rules -> library/<record_id>.json."""
import re
from datetime import datetime, timezone

from app import config, rules, view
from . import llm, verify
from .common import out_dir, read_stage_file, save_copy, slug, write_json

PHASES = [key for key, _ in view.PHASES]
SAFETY = ["dg", "injury", "damage", "comfort"]
NUMERIC_FACTS = ["voltage_v", "capacity_ah", "wh_each", "weight_kg"]
FACT_KEYS = ["battery_chemistry", "voltage_v", "capacity_ah", "wh_each", "battery_removable",
             "power_off_method", "weight_kg", "dimensions"]
MAX_MUST_DO = view.MAX_MUST_DO

MUST_PART = re.compile(r"free_?wheel|clutch|brake_release|power_(switch|button)")
MUST_TEXT = re.compile(
    r"power off|power switch|power button|"
    r"(turn|switch)(ing)? (the )?(power |chair |controller )?off|"
    r"must not move|does not move|secur|tie[- ]?down|strap"
)

_cited_schema = {
    "type": "object",
    "properties": {"value": {}, "page": {"type": ["integer", "null"]}, "quote": {"type": ["string", "null"]}},
    "required": ["value", "page", "quote"],
}
SCHEMA = {
    "type": "object",
    "required": ["aliases", "chair_type", "parts", "steps", "facts"],
    "properties": {
        "aliases": {"type": "array", "items": {"type": "string"}, "description": "other names for this model in the manual"},
        "chair_type": {"type": "string", "description": "power_modular | power_folding | power_standard | manual_folding | manual_rigid"},
        "parts": {"type": "array", "items": {
            "type": "object", "required": ["id", "name", "where", "count"],
            "properties": {
                "id": {"type": "string", "description": "snake_case, e.g. freewheel_lever"},
                "name": _cited_schema,
                "where": {"type": "string", "description": "short text from the manual saying where the part is"},
                "count": {"type": "integer"},
            }}},
        "steps": {"type": "array", "items": {
            "type": "object", "required": ["id", "phase", "part_id", "action", "source", "safety"],
            "properties": {
                "id": {"type": "string"},
                "phase": {"enum": PHASES},
                "part_id": {"type": ["string", "null"], "description": "id from parts, or null"},
                "action": {"type": "string", "description": "max ~20 words; only shortens its own quote"},
                "source": {"type": "object", "required": ["page", "quote"],
                           "properties": {"page": {"type": "integer"}, "quote": {"type": "string"}}},
                "safety": {"enum": SAFETY},
                "figure_ref": {"type": ["string", "null"], "description": "caption the text names, e.g. 圖4.10, or null"},
            }}},
        "facts": {
            "type": "object",
            "required": FACT_KEYS + ["removable_parts"],
            "properties": {
                **{k: _cited_schema for k in FACT_KEYS},
                "removable_parts": {"type": "array", "items": _cited_schema},
            },
            "description": "voltage_v, capacity_ah, wh_each, weight_kg: numbers; battery_removable: boolean",
        },
    },
}

RULES = """You copy facts and handling steps from a wheelchair manufacturer's manual for airline ground staff.

RULES
1. Copy every "quote" EXACTLY from the page text: at most 25 words (Chinese or Japanese: at most 60 characters), no paraphrase, no translation, no fixing typos, no joining text from different places.
2. "page" is the n of the [[PAGE n]] marker of the page where the quote is.
3. When the manual does not say something, set its value, page and quote to null. Never guess.
4. Never add a step that has no quote. Each step has one source quote.
5. "action" (at most ~20 words or 40 Chinese characters) may only shorten its own quote, in the quote's language. Do not translate, and do not add words, advice or facts.
6. Fact "value" fields are short and in English whatever the manual's language: numbers as numbers (25.2, not "25.2 V"), battery chemistry like "Lithium-ion" or "Sealed lead acid". The quote is the proof for the value.
   A part's name "value" is the part's name exactly as the manual writes it, in the manual's language (e.g. "制動杆", "Freewheel lever"), and its quote contains that name.
   "figure_ref": the figure caption the manual text names for this step (e.g. "圖4.10" from "（見圖4.10）"), copied exactly, or null. Never guess a figure the text does not name.
7. Parts are physical parts a handler touches: freewheel levers, joystick, battery, armrests, footrest, seat, headrest, power switch, lift points.
8. phase: before_loading, lifting, in_hold or at_arrival. safety: dg (battery / dangerous goods), injury, damage or comfort.
9. Reply with the JSON object only."""


def build_prompt(pages_data):
    by_page = {p["page"]: p["text"] for p in pages_data["pages"]}
    body = "\n\n".join(f"[[PAGE {n}]]\n{by_page[n].strip()}" for n in pages_data["kept"])
    return f"{RULES}\n\nMANUAL: {pages_data['make']} {pages_data['model']}\n\n{body}"


def _number(value):
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return value
    m = re.search(r"-?\d+(?:[.,]\d+)?", str(value))
    return float(m.group().replace(",", ".")) if m else None


def _bool(value):
    if isinstance(value, bool) or value is None:
        return value
    text = str(value).strip().lower()
    if text in ("yes", "true", "removable", "y"):
        return True
    if text in ("no", "false", "not removable", "n"):
        return False
    return None


def _page(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _cited(raw, with_value=True):
    raw = raw if isinstance(raw, dict) else {}
    c = {"value": raw.get("value")} if with_value else {}
    c.update(page=_page(raw.get("page")), quote=raw.get("quote") or None, verified=False)
    return c


def _snake(text):
    return re.sub(r"[^a-z0-9]+", "_", str(text or "").lower()).strip("_")


def qualifies_for_must_do(step):
    text = verify.normalise(f"{step['action']} {step['source'].get('quote') or ''}")
    return (step["safety"] in ("dg", "injury")
            or bool(MUST_PART.search(step.get("part_id") or ""))
            or bool(MUST_TEXT.search(text)))


def select_must_do(steps):
    """must_do by code: verified AND qualifies; at most 8, in phase order. Sets step["must_do"]."""
    order = {p: i for i, p in enumerate(PHASES)}
    picks = [s for s in steps if s["source"]["verified"] and qualifies_for_must_do(s)]
    picks.sort(key=lambda s: order[s["phase"]])  # stable: keeps manual order within a phase
    chosen = {id(s) for s in picks[:MAX_MUST_DO]}
    for s in steps:
        s["must_do"] = id(s) in chosen
    return steps


def build_record(raw, pages_data, provider=None, model=None):
    norm = verify.normalise_pages({p["page"]: p["text"] for p in pages_data["pages"]})

    parts, seen = [], set()
    for p in raw.get("parts") or []:
        name = _cited(p.get("name"))
        pid = _snake(p.get("id") or name["value"])
        if not pid or pid in seen:
            continue
        seen.add(pid)
        parts.append({"id": pid, "name": name, "where": p.get("where") or "", "count": _number(p.get("count")) or 1})

    steps = []
    for p in raw.get("steps") or []:
        source = _cited(p.get("source"), with_value=False)
        if not source["quote"]:
            continue  # rule 4: no quote, no step
        part_id = _snake(p.get("part_id")) or None
        steps.append({
            "id": f"s{len(steps) + 1}",
            "phase": p.get("phase") if p.get("phase") in PHASES else "before_loading",
            "part_id": part_id if part_id in seen else None,
            "action": (p.get("action") or "").strip(),
            "source": source,
            "safety": p.get("safety") if p.get("safety") in SAFETY else "comfort",
            "figure_ref": p.get("figure_ref") if isinstance(p.get("figure_ref"), str) and p["figure_ref"].strip() else None,
            "must_do": False,
            "trust": "ai_extracted",
        })

    raw_facts = raw.get("facts") or {}
    facts = {k: _cited(raw_facts.get(k)) for k in FACT_KEYS}
    for k in NUMERIC_FACTS:
        facts[k]["value"] = _number(facts[k]["value"])
    facts["battery_removable"]["value"] = _bool(facts["battery_removable"]["value"])
    facts["removable_parts"] = [c for c in (_cited(r) for r in raw_facts.get("removable_parts") or [])
                                if c["value"] is not None]

    cited = ([p["name"] for p in parts] + [s["source"] for s in steps]
             + [facts[k] for k in FACT_KEYS] + facts["removable_parts"])
    for c in cited:
        verify.verify_cited(c, norm)
    select_must_do(steps)

    make, model_name = pages_data["make"], pages_data["model"]
    chair_type = str(raw.get("chair_type") or "power_standard")
    kind = "none" if chair_type.startswith("manual") else rules.battery_kind(facts["battery_chemistry"]["value"])
    wh = rules.wh_display(facts)
    quoted = [c for c in cited if c.get("quote")]

    return {
        "record_id": slug(f"{make} {model_name}"),
        "make": make,
        "model": model_name,
        "aliases": [a for a in raw.get("aliases") or [] if isinstance(a, str)],
        "chair_type": chair_type,
        "manual": {"file": pages_data["manual_file"], "url": pages_data.get("manual_url"),
                   "sha256": pages_data["sha256"], "pages": pages_data["page_count"]},
        "parts": parts,
        "steps": steps,
        "facts": facts,
        "derived": {
            "wh_computed": wh["wh"] if wh["kind"] == "computed" else None,
            "wh_text": wh["text"],
            # Removal is per chair, so the library record keeps "Confirm at check-in" (§5.1).
            "ssr_code": rules.ssr_text(rules.ssr_codes(kind, None)),
        },
        "safety_lines": ({"source": view.SAFETY_SOURCE, "lines": view.SAFETY_LINES}
                         if chair_type.startswith("power") else None),
        "missing": [k for k in FACT_KEYS if facts[k]["value"] is None]
        + ([] if facts["removable_parts"] else ["removable_parts"]),
        "quotes": {"verified": sum(1 for c in quoted if c["verified"]), "total": len(quoted)},
        "pages_kept": pages_data["kept"],
        "built_with": {"provider": provider, "model": model},
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def run(chair_id):
    pages_data = read_stage_file(chair_id, "pages.json", "pages")
    raw = llm.ask_json("extract", build_prompt(pages_data), schema=SCHEMA)
    record = build_record(raw, pages_data, llm.provider(), llm.model_name())

    for path in (out_dir(chair_id) / "record.json", config.LIBRARY_DIR / f"{record['record_id']}.json"):
        write_json(path, record)
    save_copy(chair_id, out_dir(chair_id) / "record.json")

    q = record["quotes"]
    print(f"extract: {len(record['steps'])} steps, {q['verified']} of {q['total']} quotes verified"
          f" -> library/{record['record_id']}.json")
    return record
