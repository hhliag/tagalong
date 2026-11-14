"""DESIGN §5: rules computed by code, never by the LLM."""


def _num(cited):
    value = (cited or {}).get("value")
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


# §5.1 SSR code

def battery_kind(chemistry):
    """Map the manual's battery chemistry text to lithium | sealed_lead_acid | wet | None (unknown)."""
    text = (chemistry or "").lower()
    if not text:
        return None
    if any(k in text for k in ("lithium", "li-ion", "li ion", "lifepo")):
        return "lithium"
    # Check sealed before wet: "non-spillable" contains "spillable".
    if any(k in text for k in ("sealed", "non-spillable", "gel", "agm", "vrla", "valve regulated")):
        return "sealed_lead_acid"
    if any(k in text for k in ("wet", "spillable")):
        return "wet"
    return None


def battery_removed(removed_parts):
    """True/False from the chair record's removed_parts; None when the owner has not said.

    Never inferred from the manual's battery_removable.
    """
    if removed_parts is None:
        return None
    return any("battery" in p for p in removed_parts)


def ssr_codes(kind, removed):
    """kind: "none" (no battery) | lithium | sealed_lead_acid | wet | None. removed: True/False/None."""
    if kind == "none":
        return {"codes": ["WCMP"], "confirm": False}
    if kind == "sealed_lead_acid":
        return {"codes": ["WCBD"], "confirm": False}
    if kind == "wet":
        return {"codes": ["WCBW"], "confirm": False}
    if kind == "lithium":
        if removed is True:
            return {"codes": ["WCLX"], "confirm": False}
        if removed is False:
            return {"codes": ["WCLB"], "confirm": False}
        return {"codes": ["WCLB", "WCLX"], "confirm": True}
    return {"codes": [], "confirm": True}


def ssr_text(ssr):
    codes = " or ".join(ssr["codes"]) or "Unknown battery"
    return f"{codes} · Confirm at check-in" if ssr["confirm"] else codes


# §5.2 Watt-hours

def wh_display(facts):
    wh = _num(facts.get("wh_each"))
    if wh is not None:
        return {"wh": wh, "kind": "manual", "text": f"{wh:g} Wh", "cites": [facts["wh_each"]]}
    volts, amp_hours = _num(facts.get("voltage_v")), _num(facts.get("capacity_ah"))
    if volts is not None and amp_hours is not None:
        wh = round(volts * amp_hours)
        return {
            "wh": wh,
            "kind": "computed",
            "text": f"≈ {wh} Wh (computed, not a manual figure)",
            "cites": [facts["voltage_v"], facts["capacity_ah"]],
        }
    return {"wh": None, "kind": "missing", "text": "not in the manual", "cites": []}
