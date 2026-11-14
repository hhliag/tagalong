"""Turn a model record + chair record into what the card, print and uses pages show."""
import re

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


# A leading list marker in an action ("1.", "2、", "3)", "①"); display only, the stored quote is unchanged.
# A plain number needs punctuation after it, so "2 people lift" and "24V" stay whole.
LIST_MARKER = re.compile(r"^\s*(?:[①-⑳]|\(?\d{1,2}[\.、\)）](?!\d))\s*")

# Pins: a hollow ring on the part, the code in a badge outside it. The badge goes to the first side
# that stays inside the photo and keeps clear of the other rings (same rule in HTML and in Pillow).
PIN_SIDES = [("ur", 1, -1), ("ul", -1, -1), ("dr", 1, 1), ("dl", -1, 1)]
PIN_OFFSET = 0.07   # badge centre from the ring centre, as a fraction of the photo, on each axis
PIN_MARGIN = 0.05
PIN_CLEAR = 0.12


def clean_action(text):
    return LIST_MARKER.sub("", text or "", count=1)


def letter(n):
    """1 -> A, 2 -> B ... 26 -> Z, 27 -> AA."""
    code = ""
    while n:
        n, rest = divmod(n - 1, 26)
        code = chr(65 + rest) + code
    return code


def label_key(label):
    return label.get("id", label.get("n"))


def pin_sides(points):
    """points: [(key, x, y)] in 0-1 fractions -> {key: side}, side one of ur, ul, dr, dl."""
    sides, badges = {}, []
    for key, x, y in points:
        others = [(px, py) for k, px, py in points if k != key] + badges
        best = None
        for name, sx, sy in PIN_SIDES:
            bx, by = x + sx * PIN_OFFSET, y + sy * PIN_OFFSET
            inside = PIN_MARGIN <= bx <= 1 - PIN_MARGIN and PIN_MARGIN <= by <= 1 - PIN_MARGIN
            clear = min((((bx - ox) ** 2 + (by - oy) ** 2) ** 0.5 for ox, oy in others), default=1.0)
            score = (inside, round(min(clear, PIN_CLEAR), 3))
            if best is None or score > best[0]:
                best = (score, name, (bx, by))
        sides[key] = best[1]
        badges.append(best[2])
    return sides


def photo_entry(file, labels, zones=()):
    """One photo with its part pins (code + badge side) and zone pins."""
    on = [l for l in labels if l["photo"] == file]
    zs = [z for z in zones if z["photo"] == file]
    sides = pin_sides([(label_key(l), l["x"], l["y"]) for l in on + zs])
    return {"file": file,
            "labels": [{**l, "code": letter(l["n"]), "side": sides[label_key(l)]} for l in on],
            "zones": [{**z, "side": sides[label_key(z)]} for z in zs]}


def photos_with_labels(chair, labels, count, zones=()):
    """Photos that carry the given labels or zones first (in label order), then the default views, up to `count`."""
    files = []
    for label in sorted([*labels, *zones], key=label_key):
        if label["photo"] and label["photo"] not in files:
            files.append(label["photo"])
    for f in DEFAULT_PHOTOS:
        if f not in files:
            files.append(f)
    return [photo_entry(f, labels, zones) for f in files[:count]]


def legend(labels, parts):
    """One line per labelled part: (code, part name as written in the manual), in code order."""
    seen = {}
    for l in sorted(labels, key=lambda l: l["n"]):
        seen.setdefault(l["n"], parts[l["part_id"]]["name"]["value"])
    return [(letter(n), name) for n, name in seen.items()]


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
        n = label_n.get(s.get("part_id"))
        part = parts.get(s.get("part_id"))
        steps.append({
            **s,
            "verified": verified,
            "must": bool(s.get("must_do")) and verified,  # §4.4: unverified is never must_do
            "label_n": n,
            "label_code": letter(n) if n else None,
            "action_display": clean_action(s["action"]),
            "part_chip": {"code": letter(n) if n else None, "name": part["name"]["value"]} if part else None,
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
        "legend": legend(numbered, parts),
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
