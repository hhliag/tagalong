import copy
import json

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app import config, main
from app.main import app
from pipeline import render

client = TestClient(app)
FIXTURE_RECORD = json.loads((config.FIXTURES_DIR / "library" / "whill-model-c2.json").read_text())
FIXTURE_CHAIR = json.loads((config.FIXTURES_DIR / "devices" / "chair-a.json").read_text())

ZONES = [
    {"id": "h1", "kind": "hold", "part_id": "frame", "reason": "Lift by the frame.",
     "source": {"page": 12, "quote": "Lift the chair by the frame.", "verified": True}, "verified": True},
    {"id": "h2", "kind": "no_hold", "part_id": "armrest", "reason": "Not by the armrests.",
     "source": {"page": 12, "quote": "Do not lift by the armrests.", "verified": True}, "verified": True},
]
NEW_PARTS = [
    {"id": "frame", "name": {"value": "Frame", "page": 12, "quote": "frame", "verified": True}, "where": "", "count": 1},
    {"id": "armrest", "name": {"value": "Armrest", "page": 12, "quote": "armrests", "verified": True}, "where": "", "count": 2},
]


def install(zone_status=("confirmed", "confirmed"), handling=ZONES):
    """Write a pipeline-style record + chair into the test library/devices folders."""
    record = copy.deepcopy(FIXTURE_RECORD)
    record["parts"] += NEW_PARTS
    record["handling"] = copy.deepcopy(handling)
    record["handling_missing"] = not handling
    chair = copy.deepcopy(FIXTURE_CHAIR)
    for z, status in zip(handling, zone_status):
        chair["labels"].append({"part_id": z["part_id"], "n": len(chair["labels"]) + 1, "photo": "left.jpg",
                                "x": 0.3, "y": 0.4, "box": [0.2, 0.3, 0.4, 0.5], "confidence": 0.8,
                                "status": status, "zone": z["kind"], "zone_id": z["id"]})
    for folder, name, data in ((config.LIBRARY_DIR, "whill-model-c2.json", record),
                               (config.DEVICES_DIR, "chair-a.json", chair)):
        folder.mkdir(parents=True, exist_ok=True)
        (folder / name).write_text(json.dumps(data))
    return record, chair


# ---------- pages ----------

def test_confirmed_zones_show_on_passport_print_and_crew():
    install()
    for path in ("/passport/chair-a", "/crew/AP-7Q4K"):
        page = client.get(path).text
        assert "How to hold this chair" in page
        assert "Lift by the frame." in page and "Not by the armrests." in page
        assert 'class="zone-mark hold confirmed"' in page and 'class="zone-box no_hold confirmed"' in page
        assert "/manual/whill-model-c2/12?step=h1" in page
        assert page.index("How to hold this chair") < page.index("Must do")
    printed = client.get("/passport/chair-a/print").text
    assert "Lift here" in printed and "Do not lift by" in printed and "Frame" in printed


@pytest.mark.parametrize("status", ["pending", "rejected"])
def test_pending_and_rejected_zones_never_appear(status):
    install(zone_status=(status, status))
    for path in ("/passport/chair-a", "/passport/chair-a/print", "/crew/AP-7Q4K"):
        page = client.get(path).text
        assert "Lift by the frame." not in page and "Not by the armrests." not in page
        assert "zone-mark hold confirmed\"" not in page and "zone-box" not in page
    assert "2 handling zones hidden" in client.get("/passport/chair-a").text


def test_handling_missing_shows_ask_the_owner_and_no_markers():
    install(handling=[])
    for path in ("/passport/chair-a", "/passport/chair-a/print", "/crew/AP-7Q4K"):
        page = client.get(path).text
        assert "The manual gives no lifting points. Ask the owner." in page
        assert 'id="box-' not in page and "zone-mark hold confirmed\"" not in page


def test_only_no_hold_zones_still_says_no_lifting_points():
    install(zone_status=("confirmed",), handling=[ZONES[1]])
    page = client.get("/passport/chair-a").text
    assert "The manual gives no lifting points. Ask the owner." in page and "Not by the armrests." in page


def test_confirm_lists_zones_with_question_marks():
    install(zone_status=("pending", "pending"))
    page = client.get("/confirm/chair-a").text
    assert "Lift here: Frame" in page and "Do not hold: Armrest" in page
    assert 'class="zone-mark hold pending"' in page          # pending = dashed + "?" (CSS)
    r = client.post("/api/labels/chair-a/3", json={"status": "confirmed"})
    assert r.status_code == 200
    assert "Lift by the frame." in client.get("/passport/chair-a").text


def test_record_without_handling_shows_no_box():
    page = client.get("/passport/chair-a").text      # the M1 fixture has no handling data
    assert "How to hold this chair" not in page


# ---------- crew lookup and the QR ----------

def test_crew_search_finds_tag_case_insensitive():
    r = client.get("/crew", params={"tag": " ap-7q4k "}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/crew/AP-7Q4K"
    assert "Crew view" in client.get("/crew/AP-7Q4K").text


def test_crew_unknown_tag():
    page = client.get("/crew", params={"tag": "ZZ-0000"}).text
    assert "No chair with tag" in page
    assert "No chair with tag" in client.get("/crew/ZZ-0000").text


def test_crew_link_on_every_page_and_home():
    assert 'href="/crew"' in client.get("/").text
    assert 'href="/crew"' in client.get("/passport/chair-a").text


def test_print_qr_opens_the_crew_view(monkeypatch):
    seen = []
    real = main.segno.make
    monkeypatch.setattr(main.segno, "make", lambda url, **kw: (seen.append(url), real(url, **kw))[1])
    client.get("/passport/chair-a/print")
    assert seen == ["http://testserver/crew/AP-7Q4K"]


# ---------- render ----------

def test_render_hold_and_no_hold_colours():
    image = Image.new("RGB", (1000, 750), (128, 128, 128))
    zones = [{"zone": "hold", "x": 0.25, "y": 0.5, "box": [0.15, 0.4, 0.35, 0.6]},
             {"zone": "no_hold", "x": 0.75, "y": 0.5, "box": [0.6, 0.3, 0.9, 0.7]}]
    out = render.draw_zones(image, zones)
    r = round(0.03 * 750)
    assert out.getpixel((250 - r + 4, 375)) == (0x1E, 0x8E, 0x3E)          # green circle (left of the check)
    assert out.getpixel((750 - r + 4, 375 - r + 8)) == (0xC5, 0x22, 0x1F)  # red square
    inside_box = out.getpixel((640, 240))                                  # red tint over grey, not the marker
    assert inside_box[0] > 128 and inside_box[1] < 128
    # Part dots drawn after the zones stay on top
    on_top = render.draw_labels(out, [{"n": 1, "x": 0.25, "y": 0.5}])
    assert on_top.getpixel((250 + 10, 375)) == (0xC3, 0xAC, 0x86)
