import json

import pytest
from PIL import Image

from app import config
from pipeline import label, llm, render


# ---------- coordinates ----------

def test_box_2d_to_centre_fractions():
    assert label.to_xy({"box_2d": [100, 200, 300, 600]}) == (0.4, 0.2)


def test_xy_fractions_and_clamping():
    assert label.to_xy({"x": 0.25, "y": 0.75}) == (0.25, 0.75)
    assert label.to_xy({"x": 1.4, "y": -0.2}) == (1.0, 0.0)
    assert label.to_xy({"box_2d": [0, 900, 1200, 1300]}) == (1.0, 0.6)


def test_missing_location_is_not_visible():
    dets = label.parse_detections({"parts": [{"part_id": "a", "visible": True, "confidence": 0.9}]}, ["a", "b"])
    assert dets[0]["visible"] is False and dets[1]["visible"] is False


# ---------- choosing and numbering ----------

def test_best_photo_per_part_and_closeup_wins():
    det = lambda pid, conf, vis=True: {"part_id": pid, "visible": vis, "confidence": conf, "x": 0.5, "y": 0.5}
    detections = {
        "left.jpg": [det("lever", 0.9), det("battery", 0.4)],
        "rear.jpg": [det("lever", 0.5), det("battery", 0.8)],
        "closeup_lever.jpg": [det("lever", 0.3), det("battery", 0.99, vis=False)],
    }
    best = label.best_per_part(detections)
    assert best["lever"][0] == "closeup_lever.jpg"
    assert best["battery"][0] == "rear.jpg"


def test_labels_numbered_by_first_must_do_step():
    record = {
        "parts": [{"id": "battery"}, {"id": "joystick"}, {"id": "lever"}],
        "steps": [
            {"phase": "at_arrival", "part_id": "joystick", "must_do": True},
            {"phase": "before_loading", "part_id": "lever", "must_do": True},
            {"phase": "before_loading", "part_id": "battery", "must_do": False},
        ],
    }
    assert label.number_order(record) == ["lever", "joystick", "battery"]
    det = lambda pid: {"part_id": pid, "visible": True, "confidence": 0.7, "x": 0.1, "y": 0.2}
    labels = label.make_labels(record, {"left.jpg": [det("battery"), det("lever")]})
    assert [(l["part_id"], l["n"], l["status"]) for l in labels] == [("lever", 1, "pending"), ("battery", 2, "pending")]


# ---------- EXIF rotation ----------

def _red_centre(image):
    px = [(x, y) for y in range(image.height) for x in range(image.width)
          if image.getpixel((x, y))[0] > 200 and image.getpixel((x, y))[1] < 80]
    return (sum(p[0] for p in px) / len(px) / image.width, sum(p[1] for p in px) / len(px) / image.height)


def test_exif_rotation_keeps_xy_on_the_right_place(tmp_path):
    # Stored landscape 200x100 with a red mark at (150, 20); EXIF orientation 6 = shown rotated 90° clockwise.
    stored = Image.new("RGB", (200, 100), (90, 110, 120))
    for x in range(145, 156):
        for y in range(15, 26):
            stored.putpixel((x, y), (255, 0, 0))
    exif = Image.Exif()
    exif[0x0112] = 6
    path = tmp_path / "left.jpg"
    stored.save(path, exif=exif, quality=100)

    image = label.load_photo(path)
    assert image.size == (512, 1024)                     # portrait, long side 1024
    x, y = _red_centre(image)
    assert x == pytest.approx(0.795, abs=0.02) and y == pytest.approx(0.75, abs=0.02)

    # The LLM sees this same image, so it answers in its frame; drawing there hits the mark.
    drawn = render.draw_labels(image, [{"n": 1, "x": x, "y": y}])
    centre = drawn.getpixel((round(x * image.width), round(y * image.height)))
    ring = drawn.getpixel((round(x * image.width) + 10, round(y * image.height)))  # radius is 15 px here
    assert centre != image.getpixel((round(x * image.width), round(y * image.height)))   # something drawn
    assert ring == (0xC3, 0xAC, 0x86)                    # gold fill around the number


# ---------- the stage, through the offline provider ----------

def test_label_stage_offline(tmp_path):
    from tests.helpers import make_chair
    from tests.test_pipeline_extract import RESPONSE
    from pipeline import extract, pages
    make_chair()
    run_dir = config.OUT_DIR / "chair-t"
    llm.configure("offline", None, run_dir)
    pages.run("chair-t")
    (run_dir / "offline").mkdir(parents=True, exist_ok=True)
    (run_dir / "offline" / "extract_1_response.json").write_text(json.dumps(RESPONSE))
    extract.run("chair-t")

    with pytest.raises(llm.OfflineWaiting) as w:
        label.run("chair-t")
    assert w.value.path.name == "label_1_response.json"
    request = (run_dir / "offline" / "label_1_request.md").read_text()
    assert "left view" in request and "freewheel_lever" in request and '"x"' in request
    assert (run_dir / "offline" / "label_1_left.jpg").is_file()
    with Image.open(run_dir / "offline" / "label_1_left.jpg") as im:
        assert max(im.size) == 1024
