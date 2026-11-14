import copy
import json

import pytest

from app import config, rules, view


def cited(value, page=1):
    return {"value": value, "page": page, "quote": "q", "verified": value is not None}


# ---------- §5.1 SSR code ----------

@pytest.mark.parametrize("text, kind", [
    ("Lithium-ion", "lithium"),
    ("Li-ion battery pack", "lithium"),
    ("LiFePO4", "lithium"),
    ("Sealed lead acid (SLA)", "sealed_lead_acid"),
    ("Non-spillable gel battery", "sealed_lead_acid"),
    ("AGM", "sealed_lead_acid"),
    ("Wet cell lead acid", "wet"),
    ("Spillable battery", "wet"),
    (None, None),
    ("", None),
    ("Unobtainium", None),
])
def test_battery_kind(text, kind):
    assert rules.battery_kind(text) == kind


@pytest.mark.parametrize("kind, removed, codes, confirm", [
    ("none", None, ["WCMP"], False),
    ("sealed_lead_acid", None, ["WCBD"], False),
    ("wet", None, ["WCBW"], False),
    ("lithium", False, ["WCLB"], False),
    ("lithium", True, ["WCLX"], False),
    ("lithium", None, ["WCLB", "WCLX"], True),
    (None, None, [], True),
])
def test_ssr_codes(kind, removed, codes, confirm):
    assert rules.ssr_codes(kind, removed) == {"codes": codes, "confirm": confirm}


def test_ssr_text_unknown_removal_shows_both():
    assert rules.ssr_text(rules.ssr_codes("lithium", None)) == "WCLB or WCLX · Confirm at check-in"


@pytest.mark.parametrize("removed_parts, expected", [
    (None, None),
    ([], False),
    (["joystick"], False),
    (["battery"], True),
    (["joystick", "battery_pack"], True),
])
def test_battery_removed(removed_parts, expected):
    assert rules.battery_removed(removed_parts) is expected


def _fixture():
    record = json.loads((config.FIXTURES_DIR / "library" / "whill-model-c2.json").read_text())
    chair = json.loads((config.FIXTURES_DIR / "devices" / "chair-a.json").read_text())
    return record, chair


def test_removal_is_not_inferred_from_battery_removable():
    record, chair = _fixture()
    assert record["facts"]["battery_removable"]["value"] is True
    chair["removed_parts"] = None
    assert view.passport(chair, record)["ssr"] == {"codes": ["WCLB", "WCLX"], "confirm": True}


def test_manual_chair_is_wcmp():
    record, chair = _fixture()
    record = copy.deepcopy(record)
    record["chair_type"] = "manual_folding"
    assert view.passport(chair, record)["ssr"]["codes"] == ["WCMP"]


# ---------- §5.2 Watt-hours ----------

def test_wh_uses_cited_figure_first():
    facts = {"wh_each": cited(250), "voltage_v": cited(25.2), "capacity_ah": cited(10.8)}
    wh = rules.wh_display(facts)
    assert wh["kind"] == "manual" and wh["text"] == "250 Wh" and wh["wh"] == 250


def test_wh_computed_from_v_and_ah():
    facts = {"wh_each": cited(None), "voltage_v": cited(25.2), "capacity_ah": cited(10.8)}
    wh = rules.wh_display(facts)
    assert wh["kind"] == "computed"
    assert wh["wh"] == 272
    assert wh["text"] == "≈ 272 Wh (computed, not a manual figure)"
    assert len(wh["cites"]) == 2


@pytest.mark.parametrize("facts", [
    {"wh_each": cited(None), "voltage_v": cited(24), "capacity_ah": cited(None)},
    {"wh_each": cited(None), "voltage_v": cited(None), "capacity_ah": cited(None)},
    {},
])
def test_wh_missing(facts):
    wh = rules.wh_display(facts)
    assert wh == {"wh": None, "kind": "missing", "text": "not in the manual", "cites": []}


def test_wh_accepts_numeric_strings():
    facts = {"wh_each": cited("265.5")}
    assert rules.wh_display(facts)["text"] == "265.5 Wh"


# ---------- card rules that sit on top of §4.4 ----------

def test_unverified_step_is_never_must_do():
    record, chair = _fixture()
    record["steps"][0]["source"]["verified"] = False
    v = view.passport(chair, record)
    assert "s1" not in [s["id"] for s in v["must"]]
    assert "s1" in [s["id"] for s in v["more"]]


def test_only_confirmed_labels_are_shown():
    record, chair = _fixture()
    chair["labels"][0]["status"] = "confirmed"
    v = view.passport(chair, record)
    shown = [l["n"] for p in v["photos"] for l in p["labels"]]
    assert shown == [1]
    assert v["hidden_count"] == 1
