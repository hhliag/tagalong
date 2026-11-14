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


MAX_PRINT_ZONES = 3
NO_LIFT_POINTS = "The manual gives no lifting points. Ask the owner."


def split_labels(chair):
    """(part labels, zone labels). Zone labels are the hold / no_hold markers (DESIGN handling zones)."""
    labels = chair["labels"]
    return [l for l in labels if not l.get("zone")], [l for l in labels if l.get("zone")]


def photos_with_labels(chair, labels, count, zones=()):
    """Photos that carry the given labels or zones first (in label order), then the default views, up to `count`."""
    files = []
    for label in sorted([*labels, *zones], key=lambda l: l.get("id", l.get("n"))):
        if label["photo"] and label["photo"] not in files:
            files.append(label["photo"])
    for f in DEFAULT_PHOTOS:
        if f not in files:
            files.append(f)
    return [{"file": f, "labels": [l for l in labels if l["photo"] == f],
             "zones": [z for z in zones if z["photo"] == f]} for f in files[:count]]


def handling(record, zone_labels, include_pending=False):
    """The "How to hold this chair" box. Only zones the owner confirmed (or pending ones, for the pipeline card).

    None when the record has no handling data at all (made before the handling stage existed).
    """
    if "handling" not in record:
        return None
    parts = {p["id"]: p for p in record["parts"]}
    by_zone = {}
    for l in zone_labels:  # a zone can have a marker on several photos
        by_zone.setdefault(l.get("zone_id"), set()).add(l["status"])
    shown_status = {"confirmed", "pending"} if include_pending else {"confirmed"}
    items = {"hold": [], "no_hold": []}
    for z in record["handling"]:
        statuses = by_zone.get(z["id"], set())
        if not statuses & shown_status:
            continue
        items[z["kind"]].append({**z, "part_name": parts[z["part_id"]]["name"]["value"],
                                 "owner_confirmed": "confirmed" in statuses})
    shown = len(items["hold"]) + len(items["no_hold"])
    return {
        "hold": items["hold"],
        "no_hold": items["no_hold"],
        "no_lift_points": not any(z["kind"] == "hold" for z in record["handling"]),
        "hidden_count": len(record["handling"]) - shown,
    }


def passport(chair, record, include_pending=False):
    """include_pending: number steps by pending labels too (the pipeline's card, before the owner confirms)."""
    parts = {p["id"]: p for p in record["parts"]}
    part_labels, zone_labels = split_labels(chair)
    confirmed = [l for l in part_labels if l["status"] == "confirmed"]
    numbered = [l for l in part_labels if l["status"] != "rejected"] if include_pending else confirmed
    label_n = {l["part_id"]: l["n"] for l in numbered}
    confirmed_parts = {l["part_id"] for l in confirmed}
    shown_zones = [z for z in zone_labels if z["photo"] and
                   (z["status"] == "confirmed" or (include_pending and z["status"] == "pending"))]
    phase_order = {key: i for i, (key, _) in enumerate(PHASES)}

    steps = []
    for s in record["steps"]:
        verified = s["source"].get("verified") is True
        steps.append({
            **s,
            "verified": verified,
            "must": bool(s.get("must_do")) and verified,  # §4.4: unverified is never must_do
            "label_n": label_n.get(s.get("part_id")),
            "owner_confirmed": s.get("part_id") in confirmed_parts,
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
        "hidden_count": len(part_labels) - len(confirmed),
        # Every photo that carries a confirmed marker (at least 2); the A5 print shows the first 2.
        "photos": photos_with_labels(chair, confirmed, max(2, len({l["photo"] for l in confirmed + shown_zones})),
                                     shown_zones),
        "handling": handling(record, zone_labels, include_pending),
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
        "return_checks": [f"{parts[pid]['name']['value']} in place" for pid in dict.fromkeys(l["part_id"] for l in confirmed)]
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
