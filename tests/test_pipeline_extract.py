import json

import pytest

from app import config
from pipeline import extract, llm, pages, verify
from pipeline.common import PipelineError
from tests.helpers import make_chair

PAGES = {
    3: "Manual mode\nPull the freewheel levers on both sides to switch to manual mode.\n"
       "Push the free-\nwheel levers back before driving.",
    4: "Power\nPress the power button to turn the power off.",
    6: "Specifications\nWeight: 52 kg",
}
NORM = verify.normalise_pages(PAGES)


def cited(quote, page):
    return {"value": "x", "page": page, "quote": quote}


# ---------- verifier (§4.4) ----------

def test_verify_exact():
    c = verify.verify_cited(cited("Press the power button to turn the power off.", 4), NORM)
    assert c["verified"] is True and c["page"] == 4 and "note" not in c


def test_verify_small_typo_passes():
    c = verify.verify_cited(cited("Pull the freewheel levers on both sdes to switch to manual mode.", 3), NORM)
    assert c["verified"] is True


def test_verify_hyphen_line_break_and_typography():
    c = verify.verify_cited(cited("Push the “freewheel” levers back before driving.", 3), NORM)
    assert c["verified"] is True
    assert verify.normalise("free-\nwheel  “Lever”") == 'freewheel "lever"'


def test_verify_wrong_page_is_corrected():
    c = verify.verify_cited(cited("Weight: 52 kg", 3), NORM)
    assert c["verified"] is True and c["page"] == 6 and c["note"] == verify.PAGE_CORRECTED


def test_verify_absent_quote_fails():
    c = verify.verify_cited(cited("Fold the backrest forward before lifting the chair.", 3), NORM)
    assert c["verified"] is False and c["page"] == 3


def test_verify_null_quote_fails():
    assert verify.verify_cited({"value": None, "page": None, "quote": None}, NORM)["verified"] is False


# ---------- must_do (code) ----------

def step(i, phase, safety="damage", part_id=None, verified=True, action="Wipe the seat."):
    return {"id": f"s{i}", "phase": phase, "part_id": part_id, "action": action, "safety": safety,
            "source": {"page": 1, "quote": action, "verified": verified}}


def test_must_do_rules():
    steps = [
        step(1, "before_loading", safety="injury"),
        step(2, "before_loading", safety="injury", verified=False),       # unverified: never
        step(3, "lifting", part_id="freewheel_lever"),                     # freewheel part
        step(4, "in_hold", action="Turn the power off at the joystick."),  # power off
        step(5, "in_hold", action="Secure the chair with straps."),        # securing
        step(6, "at_arrival", safety="comfort"),                           # does not qualify
    ]
    extract.select_must_do(steps)
    assert [s["id"] for s in steps if s["must_do"]] == ["s1", "s3", "s4", "s5"]


def test_must_do_cap_and_phase_order():
    steps = [step(i, phase, safety="dg") for i, phase in enumerate(
        ["at_arrival", "in_hold", "lifting", "before_loading"] * 3, 1)]
    extract.select_must_do(steps)
    chosen = [s for s in steps if s["must_do"]]
    assert len(chosen) == 8
    order = {p: i for i, p in enumerate(extract.PHASES)}
    ranked = sorted(chosen, key=lambda s: order[s["phase"]])
    assert [s["phase"] for s in ranked] == ["before_loading"] * 3 + ["lifting"] * 3 + ["in_hold"] * 2
    assert not any(s["must_do"] for s in steps if s["phase"] == "at_arrival")


# ---------- the stage, through the offline provider ----------

RESPONSE = {
    "aliases": ["C2"],
    "chair_type": "power_modular",
    "parts": [
        {"id": "freewheel_lever", "name": {"value": "Freewheel lever", "page": 3, "quote": "freewheel levers"},
         "where": "both sides", "count": 2},
        {"id": "battery", "name": {"value": "Battery", "page": 5, "quote": "The battery"}, "where": "", "count": 1},
    ],
    "steps": [
        {"id": "a", "phase": "at_arrival", "part_id": "freewheel_lever", "action": "Push levers back before driving.",
         "source": {"page": 3, "quote": "Push the free-wheel levers back before driving."}, "safety": "damage"},
        {"id": "b", "phase": "before_loading", "part_id": None, "action": "Turn the power off.",
         "source": {"page": 3, "quote": "Press the power button to turn the power off."}, "safety": "injury"},
        {"id": "c", "phase": "before_loading", "part_id": "freewheel_lever", "action": "Pull both levers.",
         "source": {"page": 3, "quote": "Pull the freewheel levers on both sides to switch to manual mode."},
         "safety": "injury"},
        {"id": "d", "phase": "lifting", "part_id": None, "action": "Lift by the frame.",
         "source": {"page": 5, "quote": "Lift the chair by the frame only."}, "safety": "injury"},
        {"id": "e", "phase": "lifting", "part_id": None, "action": "No quote.", "source": {"page": 5, "quote": ""},
         "safety": "injury"},
    ],
    "facts": {
        "battery_chemistry": {"value": "Lithium-ion", "page": 5, "quote": "Lithium-ion battery."},
        "voltage_v": {"value": "25.2 V", "page": 6, "quote": "Nominal voltage: 25.2 V"},
        "capacity_ah": {"value": 10.8, "page": 6, "quote": "Capacity: 10.8 Ah"},
        "wh_each": {"value": None, "page": None, "quote": None},
        "battery_removable": {"value": "yes", "page": 5, "quote": "The battery can be removed from the vehicle."},
        "power_off_method": {"value": "Press the power button", "page": 4,
                             "quote": "Press the power button to turn the power off."},
        "weight_kg": {"value": 52, "page": 6, "quote": "Weight: 52 kg"},
        "dimensions": {"value": None, "page": None, "quote": None},
        "removable_parts": [{"value": "Battery", "page": 5, "quote": "The battery can be removed from the vehicle."}],
    },
}


def _offline_dir(chair_id="chair-t"):
    return config.OUT_DIR / chair_id / "offline"


def test_extract_offline_waits_then_uses_response(capsys):
    make_chair()
    llm.configure("offline", None, config.OUT_DIR / "chair-t")
    pages.run("chair-t")

    with pytest.raises(llm.OfflineWaiting) as waiting:
        extract.run("chair-t")
    assert waiting.value.path == (_offline_dir() / "extract_1_response.json").resolve()
    request = (_offline_dir() / "extract_1_request.md").read_text()
    assert "[[PAGE 3]]" in request and "copy every \"quote\" exactly" in request.lower()

    (_offline_dir() / "extract_1_response.json").write_text(json.dumps(RESPONSE))
    llm.configure("offline", None, config.OUT_DIR / "chair-t")
    record = extract.run("chair-t")

    assert record["record_id"] == "whill-model-c2"
    assert (config.LIBRARY_DIR / "whill-model-c2.json").is_file()
    assert [s["id"] for s in record["steps"]] == ["s1", "s2", "s3", "s4"]   # quoteless step dropped
    by_quote = {s["source"]["quote"]: s for s in record["steps"]}
    power = by_quote["Press the power button to turn the power off."]
    assert power["source"]["page"] == 4 and power["source"]["note"] == verify.PAGE_CORRECTED
    assert by_quote["Lift the chair by the frame only."]["source"]["verified"] is False
    assert by_quote["Lift the chair by the frame only."]["must_do"] is False
    # s1 (freewheel part, at_arrival), s2 (power off), s3 (injury); s4 is unverified
    assert [s["id"] for s in record["steps"] if s["must_do"]] == ["s1", "s2", "s3"]
    assert record["facts"]["voltage_v"]["value"] == 25.2
    assert record["facts"]["battery_removable"]["value"] is True
    assert record["derived"]["wh_text"] == "≈ 272 Wh (computed, not a manual figure)"
    assert record["derived"]["ssr_code"] == "WCLB or WCLX · Confirm at check-in"
    assert record["missing"] == ["wh_each", "dimensions"]
    assert record["safety_lines"]["lines"][0].startswith("Cut power")
    out = capsys.readouterr().out
    assert f"4 steps, {record['quotes']['verified']} of {record['quotes']['total']} quotes verified" in out
    assert record["quotes"]["verified"] == record["quotes"]["total"] - 1
    assert list((config.OUT_DIR / "chair-t" / "llm_log").glob("*_extract_1_response.txt"))


def test_offline_bad_json_fails_clearly():
    make_chair()
    llm.configure("offline", None, config.OUT_DIR / "chair-t")
    pages.run("chair-t")
    _offline_dir().mkdir(parents=True, exist_ok=True)
    (_offline_dir() / "extract_1_response.json").write_text("{not json")
    with pytest.raises(PipelineError, match="not valid JSON"):
        extract.run("chair-t")


def test_live_provider_retries_once_on_bad_json(monkeypatch, tmp_path):
    replies = iter(["Sure! here you go: {broken", '```json\n{"ok": 1}\n```'])
    prompts = []
    monkeypatch.setattr(llm, "_call", lambda prompt, images: (prompts.append(prompt), next(replies))[1])
    llm.configure("anthropic", "some-model", tmp_path)
    assert llm.ask_json("extract", "give json") == {"ok": 1}
    assert "could not be parsed as JSON" in prompts[1]
    assert len(list((tmp_path / "llm_log").glob("*_request.md"))) == 2
