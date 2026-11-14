import copy
import json

import pytest

from app import config
from pipeline import extract, handling, llm, pages
from tests.helpers import make_chair
from tests.test_pipeline_extract import RESPONSE

# The test manual (tests/helpers.py) says on page 5: "Remove the key before lifting."
PAGES_DATA = {
    "kept": [3, 5],
    "pages": [
        {"page": 3, "text": "Manual mode\nPull the freewheel levers on both sides."},
        {"page": 5, "text": "Battery\nLift the chair by the frame only.\nDo not lift the chair by the armrests."},
        {"page": 9, "text": "Transport\nDo not lift the chair by the footrests or the joystick."},
        {"page": 10, "text": "Cleaning\nWipe with a soft cloth."},
    ],
}
RECORD = {"make": "WHILL", "model": "Model C2",
          "parts": [{"id": "freewheel_lever", "name": {"value": "Freewheel lever"}, "where": "rear"}]}


def zone(kind, part_id, quote, page, **extra):
    return {"kind": kind, "part_id": part_id, "reason": quote[:20], "source": {"page": page, "quote": quote}, **extra}


def build(raw):
    return handling.build_handling(raw, copy.deepcopy(RECORD), PAGES_DATA)


def test_pick_pages_adds_handling_pages():
    assert handling.pick_pages(PAGES_DATA) == [3, 5, 9]     # 9 talks about lifting; 10 does not


def test_fake_quote_is_dropped():
    record, report = build({"handling": [
        zone("hold", "frame", "Lift the chair by the frame only.", 5,
             part_name={"value": "Frame", "page": 5, "quote": "the frame"}),
        zone("hold", "seat", "Lift the chair by the seat.", 5),          # not in the manual
    ]})
    assert [(z["id"], z["part_id"]) for z in record["handling"]] == [("h1", "frame")]
    assert report["dropped"][0]["source"]["quote"] == "Lift the chair by the seat."
    assert report["dropped"][0]["why"] == "quote not found in the manual"
    assert "seat" not in [p["id"] for p in record["parts"]]           # no part for a dropped zone
    frame = next(p for p in record["parts"] if p["id"] == "frame")
    assert frame["name"]["verified"] is True


def test_quote_on_wrong_page_is_corrected():
    record, _ = build({"handling": [zone("no_hold", "footrest", "Do not lift the chair by the footrests", 5)]})
    z = record["handling"][0]
    assert z["source"]["page"] == 9 and z["source"]["note"] == "page corrected by code"


def test_conflict_keeps_no_hold():
    record, report = build({"handling": [
        zone("hold", "armrest", "Lift the chair by the frame only.", 5),
        zone("no_hold", "armrest", "Do not lift the chair by the armrests.", 5),
    ]})
    assert [(z["kind"], z["part_id"]) for z in record["handling"]] == [("no_hold", "armrest")]
    assert report["conflicts"][0]["kind"] == "hold"


def test_no_guidance_sets_handling_missing():
    record, _ = build({"handling": [], "handling_missing": True})
    assert record["handling"] == [] and record["handling_missing"] is True
    record, _ = build({"handling": [zone("hold", "seat", "Lift by the seat.", 5)]})   # only a fake one
    assert record["handling"] == [] and record["handling_missing"] is True


def test_handling_stage_offline(capsys):
    make_chair()
    run_dir = config.OUT_DIR / "chair-t"
    llm.configure("offline", None, run_dir)
    pages.run("chair-t")
    (run_dir / "offline").mkdir(parents=True, exist_ok=True)
    (run_dir / "offline" / "extract_1_response.json").write_text(json.dumps(RESPONSE))
    extract.run("chair-t")

    with pytest.raises(llm.OfflineWaiting) as w:
        handling.run("chair-t")
    assert w.value.path.name == "handling_1_response.json"
    assert "KNOWN PARTS" in (run_dir / "offline" / "handling_1_request.md").read_text()

    (run_dir / "offline" / "handling_1_response.json").write_text(json.dumps({"handling": [
        zone("no_hold", "battery", "Remove the key before lifting.", 5),
        zone("hold", "frame", "Lift the chair by its frame.", 5),       # not in the test manual
    ]}))
    llm.configure("offline", None, run_dir)   # a new run, as the CLI does
    record = handling.run("chair-t")
    assert "handling: 0 hold, 1 no_hold, 1 dropped" in capsys.readouterr().out
    lib = json.loads((config.LIBRARY_DIR / "whill-model-c2.json").read_text())
    assert lib["handling"] == record["handling"] and lib["handling_missing"] is False
    assert (config.SAVED_DIR / "chair-t" / "handling.json").is_file()
