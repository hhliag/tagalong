"""Turn a model record + chair record into what the card, print and uses pages show."""
from . import rules

PHASES = [
    ("before_loading", "Before loading"),
    ("lifting", "Lifting"),
    ("in_hold", "In the hold"),
    ("at_arrival", "At arrival"),
]
MAX_MUST_DO = 8
DEFAULT_PHOTOS = ["left.jpg", "right.jpg"]

SAFETY_LINES = [
    "Cut power by the maker's method, then check: drive mode, power on, push the joystick; the chair must not move.",
    "Freewheel: engage to push by hand; disengage before securing.",
    "Removed lithium batteries go in the cabin.",
]
SAFETY_SOURCE = "IATA guidance for battery-powered mobility aids"


def chair_name(chair):
    """Hidden (None) until the plate stage has run."""
    if "plate" not in chair.get("stages", []):
        return None
    plate = chair["plate_read"]
    return f"{plate['make']} {plate['model']}"


def photos_with_labels(chair, labels, count):
    """Photos that carry the given labels first (in label order), then the default views, up to `count`."""
    files = []
    for label in sorted(labels, key=lambda l: l["n"]):
        if label["photo"] not in files:
            files.append(label["photo"])
    for f in DEFAULT_PHOTOS:
        if f not in files:
            files.append(f)
    return [{"file": f, "labels": [l for l in labels if l["photo"] == f]} for f in files[:count]]


def passport(chair, record):
    parts = {p["id"]: p for p in record["parts"]}
    confirmed = [l for l in chair["labels"] if l["status"] == "confirmed"]
    label_n = {l["part_id"]: l["n"] for l in confirmed}
    phase_order = {key: i for i, (key, _) in enumerate(PHASES)}

    steps = []
    for s in record["steps"]:
        verified = s["source"].get("verified") is True
        steps.append({
            **s,
            "verified": verified,
            "must": bool(s.get("must_do")) and verified,  # §4.4: unverified is never must_do
            "label_n": label_n.get(s.get("part_id")),
            "owner_confirmed": s.get("part_id") in label_n,
        })
    must = sorted((s for s in steps if s["must"]), key=lambda s: phase_order[s["phase"]])[:MAX_MUST_DO]
    must_ids = {s["id"] for s in must}
    for i, s in enumerate(must, 1):
        s["num"] = i
    must_groups = [(title, [s for s in must if s["phase"] == key]) for key, title in PHASES]

    facts = record["facts"]
    kind = "none" if record["chair_type"].startswith("manual") else rules.battery_kind(
        facts["battery_chemistry"]["value"])
    ssr = rules.ssr_codes(kind, rules.battery_removed(chair.get("removed_parts")))
    wh = rules.wh_display(facts)

    return {
        "name": f"{record['make']} {record['model']}",
        "parts": parts,
        "confirmed": confirmed,
        "hidden_count": len(chair["labels"]) - len(confirmed),
        "photos": photos_with_labels(chair, confirmed, 2),
        "must": must,
        "must_groups": [(t, g) for t, g in must_groups if g],
        "more": [s for s in steps if s["id"] not in must_ids],
        "is_power": record["chair_type"].startswith("power"),
        "safety_lines": SAFETY_LINES,
        "safety_source": SAFETY_SOURCE,
        "ssr": ssr,
        "ssr_text": rules.ssr_text(ssr),
        "wh": wh,
        "facts": fact_rows(facts, wh),
        "return_checks": [f"{parts[l['part_id']]['name']['value']} in place" for l in confirmed]
        + [s["action"] for s in steps if s["phase"] == "at_arrival"],
    }


def _fmt(value, unit=""):
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, (int, float)):
        return f"{value:g}{unit}"
    return str(value)


def _row(label, cited, unit=""):
    value = cited.get("value")
    return {
        "label": label,
        "text": "not in the manual" if value is None else _fmt(value, unit),
        "cites": [cited] if value is not None else [],
    }


def fact_rows(facts, wh):
    """Check-in rows (§7): battery type, V, Ah, Wh, removable, power-off, weight, size."""
    removable = [c for c in facts.get("removable_parts", []) if c.get("value") is not None]
    return {
        "battery_type": _row("Battery type", facts["battery_chemistry"]),
        "voltage": _row("Voltage", facts["voltage_v"], " V"),
        "capacity": _row("Capacity", facts["capacity_ah"], " Ah"),
        "wh": {"label": "Watt-hours", "text": wh["text"], "cites": wh["cites"]},
        "removable": _row("Battery removable", facts["battery_removable"]),
        "power_off": _row("Power off", facts["power_off_method"]),
        "weight": _row("Weight", facts["weight_kg"], " kg"),
        "size": _row("Size", facts["dimensions"]),
        "removable_parts": {
            "label": "Removable parts",
            "text": ", ".join(str(c["value"]) for c in removable) or "not in the manual",
            "cites": removable,
        },
    }
