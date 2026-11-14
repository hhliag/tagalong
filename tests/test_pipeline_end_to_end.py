import json

from fastapi.testclient import TestClient
from PIL import Image

from app import config
from app.main import app
from pipeline.__main__ import main
from tests.helpers import META, make_chair
from tests.test_pipeline_extract import RESPONSE

HANDLING = {"handling": [
    {"kind": "hold", "part_id": "seat_frame", "reason": "Hold the seat frame when lifting.",
     "part_name": {"value": "Seat frame", "page": 5, "quote": "seat frame"}, "where": "under the seat",
     "source": {"page": 5, "quote": "Hold the seat frame when lifting."}},
    {"kind": "no_hold", "part_id": "armrest", "reason": "Do not lift by the armrests.",
     "part_name": {"value": "Armrest", "page": 5, "quote": "armrests"}, "where": "",
     "source": {"page": 5, "quote": "Do not lift the chair by the armrests."}},
    {"kind": "hold", "part_id": "seat", "reason": "made up", "source": {"page": 5, "quote": "Lift by the cushion."}},
]}

LABELS = {  # offline label responses, one per photo: left, right, front, rear
    1: {"parts": [{"part_id": "freewheel_lever", "visible": True, "confidence": 0.9, "x": 0.3, "y": 0.6},
                  {"part_id": "armrest", "visible": True, "confidence": 0.7, "x": 0.6, "y": 0.4,
                   "box": [0.5, 0.35, 0.7, 0.45]},
                  {"part_id": "battery", "visible": False, "confidence": 0.1}]},
    2: {"parts": [{"part_id": "freewheel_lever", "visible": True, "confidence": 0.5, "x": 0.7, "y": 0.6}]},
    3: {"parts": []},
    4: {"parts": [{"part_id": "battery", "visible": True, "confidence": 0.8, "x": 0.5, "y": 0.4}]},
}


def test_offline_run_end_to_end(capsys):
    make_chair(meta=META + "sample_photos: true\n")
    off = config.OUT_DIR / "chair-t" / "offline"

    assert main(["chair-t", "--provider", "offline"]) == 3                                   # waits at extract
    assert "Waiting for offline response:" in capsys.readouterr().out
    (off / "extract_1_response.json").write_text(json.dumps(RESPONSE))
    assert main(["chair-t", "--provider", "offline"]) == 3                                   # then handling
    assert "handling_1_response.json" in capsys.readouterr().out
    (off / "handling_1_response.json").write_text(json.dumps(HANDLING))

    for n in range(1, 5):                                           # then once per photo
        assert main(["chair-t", "--provider", "offline"]) == 3
        assert f"label_{n}_response.json" in capsys.readouterr().out
        (off / f"label_{n}_response.json").write_text(json.dumps(LABELS[n]))

    assert main(["chair-t", "--provider", "offline"]) == 0
    out = config.OUT_DIR / "chair-t"

    device = json.loads((config.DEVICES_DIR / "chair-t.json").read_text())
    assert device["plate_read"]["raw"] == "from sample data"
    assert [(l["part_id"], l["n"], l["photo"]) for l in device["labels"] if not l["zone"]] == [
        ("freewheel_lever", 1, "left.jpg"), ("battery", 2, "rear.jpg"), ("armrest", 3, "left.jpg")]
    # one zone label per verified zone; the made-up "seat" zone was dropped; armrest seen on the left photo
    zones = [(l["zone"], l["part_id"], l["photo"], l["status"]) for l in device["labels"] if l["zone"]]
    assert zones == [("hold", "seat_frame", None, "pending"), ("no_hold", "armrest", "left.jpg", "pending")]

    for view in ("left", "right", "front", "rear"):
        with Image.open(out / f"labelled_{view}.png") as im:
            assert max(im.size) == 1024
    with Image.open(out / "labelled_left.png") as im:
        assert im.getpixel((round(0.3 * im.width) + 10, round(0.6 * im.height))) == (0xC3, 0xAC, 0x86)

    card = (out / "card.html").read_text()
    assert "Labels not yet confirmed by the owner." in card
    assert "Sample photos. In real use the owner takes them." in card
    assert card.count("data:image/jpeg;base64,") == 2               # the two photos with labels
    assert "AI-extracted · page verified" in card and "Quote not found on page" in card
    assert "≈ 272 Wh (computed, not a manual figure)" in card
    assert 'class="concept"' in card

    assert "How to hold this chair" in card and "Do not lift by" in card
    assert "The manual gives no lifting points" not in card       # the record has a hold zone
    report = (out / "REPORT.md").read_text()
    assert "Handling zones: 1 hold, 1 no_hold" in report and "Lift by the cushion." in report
    assert "| zone | kind | part |" in report
    assert "Lift the chair by the frame only." in report             # the failed quote is listed
    assert "| right / wrong |" in report
    assert "- wh_each" in report

    for name in ("pages.json", "record.json", "device.json", "detections.json", "card.html", "REPORT.md",
                 "labelled_left.png"):
        assert (config.SAVED_DIR / "chair-t" / name).is_file(), name

    # Re-run a single stage from the files in out/
    assert main(["chair-t", "--stage", "render", "--provider", "offline"]) == 0

    # Wire M1: the pages now use the pipeline's records
    client = TestClient(app)
    page = client.get("/passport/chair-t").text
    assert "WHILL Model C2" in page and "Pull both levers." in page
    assert "3 labels hidden" in page and "2 handling zones hidden" in page
    assert "WCLB or WCLX" in client.get("/uses/chair-t/checkin").text


def test_card_has_no_sample_line_unless_meta_says_so():
    make_chair()
    off = config.OUT_DIR / "chair-t" / "offline"
    off.mkdir(parents=True)
    (off / "extract_1_response.json").write_text(json.dumps(RESPONSE))
    (off / "handling_1_response.json").write_text(json.dumps(HANDLING))
    for n in range(1, 5):
        (off / f"label_{n}_response.json").write_text(json.dumps(LABELS[n]))
    assert main(["chair-t", "--provider", "offline"]) == 0
    assert "Sample photos" not in (config.OUT_DIR / "chair-t" / "card.html").read_text()


def test_stage_without_previous_file_fails_clearly(capsys):
    make_chair()
    assert main(["chair-t", "--stage", "label", "--provider", "offline"]) == 2
    assert "Run --stage extract first" in capsys.readouterr().out
