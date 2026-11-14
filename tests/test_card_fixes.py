import copy
import io
import json

import pymupdf
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app import config, view
from app.main import app
from pipeline import figures, llm, render
from tests.helpers import make_chair

client = TestClient(app)
FIXTURE_RECORD = json.loads((config.FIXTURES_DIR / "library" / "whill-model-c2.json").read_text())
FIXTURE_CHAIR = json.loads((config.FIXTURES_DIR / "devices" / "chair-a.json").read_text())


# ---------- 2. action text ----------

@pytest.mark.parametrize("raw, shown", [
    ("1. Turn the power off.", "Turn the power off."),
    ("2、關閉電源", "關閉電源"),
    ("3) Pull both levers.", "Pull both levers."),
    ("① 拉起制動杆", "拉起制動杆"),
    ("Turn the power off.", "Turn the power off."),      # no marker
    ("24V battery inside", "24V battery inside"),        # a number that is not a marker
    ("2 people lift the chair", "2 people lift the chair"),
])
def test_list_marker_stripping(raw, shown):
    assert view.clean_action(raw) == shown


# ---------- 4. letters ----------

def test_n_to_letter():
    assert [view.letter(n) for n in (1, 2, 3, 26, 27, 28)] == ["A", "B", "C", "Z", "AA", "AB"]


# ---------- pages: letters, chips, legend, cleaned action, hidden labels ----------

def install(statuses=("confirmed", "confirmed"), action_prefix="1. "):
    record = copy.deepcopy(FIXTURE_RECORD)
    record["parts"][0]["name"]["value"] = "制動杆"           # names as the manual writes them
    for s in record["steps"]:
        s["action"] = action_prefix + s["action"]
    chair = copy.deepcopy(FIXTURE_CHAIR)
    for label, status in zip(chair["labels"], statuses):
        label["status"] = status
    for folder, name, data in ((config.LIBRARY_DIR, "whill-model-c2.json", record),
                               (config.DEVICES_DIR, "chair-a.json", chair)):
        folder.mkdir(parents=True, exist_ok=True)
        (folder / name).write_text(json.dumps(data))


def test_passport_shows_letters_chips_legend_and_clean_actions():
    install()
    page = client.get("/passport/chair-a").text
    assert '<span class="pin-badge">A</span>' in page                      # letter on the photo
    assert '<b>A</b> · 制動杆' in page                                      # step chip, manual's own name
    assert '<span class="code-badge">A</span> 制動杆' in page                # legend line
    assert "1. Pull both" not in page and "Pull both freewheel levers" in page
    printed = client.get("/passport/chair-a/print").text
    assert "A · 制動杆" in printed and "1. Pull" not in printed
    assert "A · 制動杆" in client.get("/confirm/chair-a").text


def test_steps_count_on_through_the_must_do_list():
    install()
    v = view.passport(json.loads((config.DEVICES_DIR / "chair-a.json").read_text()),
                      json.loads((config.LIBRARY_DIR / "whill-model-c2.json").read_text()))
    assert [s["num"] for s in v["must"]] == list(range(1, len(v["must"]) + 1))


@pytest.mark.parametrize("statuses", [("pending", "pending"), ("rejected", "rejected"), ("pending", "rejected")])
def test_pending_and_rejected_labels_never_appear(statuses):
    install(statuses)
    for path in ("/passport/chair-a", "/passport/chair-a/print"):
        page = client.get(path).text
        assert 'class="pin part' not in page and 'id="dot-' not in page
        assert 'class="label-legend"' not in page


# ---------- 3. see-through pins ----------

def test_pin_centre_pixel_is_unchanged():
    photo = Image.new("RGB", (768, 1024), (40, 90, 160))
    photo.putpixel((384, 512), (250, 10, 10))
    out = render.draw_labels(photo, [{"id": 1, "n": 1, "x": 0.5, "y": 0.5, "status": "pending"}])
    assert out.getpixel((384, 512)) == (250, 10, 10)
    r = round(0.03 * 768)
    assert out.getpixel((384 + r, 512)) == (0xC3, 0xAC, 0x86)          # gold ring, pending
    jade = render.draw_labels(photo, [{"id": 1, "n": 1, "x": 0.5, "y": 0.5, "status": "confirmed"}])
    assert jade.getpixel((384 + r, 512)) == (0x00, 0x5D, 0x63)


def test_badge_side_stays_inside_and_off_other_rings():
    sides = view.pin_sides([(1, 0.97, 0.03), (2, 0.5, 0.5), (3, 0.57, 0.43)])
    assert sides[1] == "dl"                     # top-right corner: badge goes down-left
    assert sides[2] != "ur"                     # up-right of 2 is where ring 3 sits


# ---------- 1. figures ----------

def _png(w, h, colour):
    buf = io.BytesIO()
    Image.new("RGB", (w, h), colour).save(buf, format="PNG")
    return buf.getvalue()


def make_figure_manual(path):
    doc = pymupdf.open()
    p1 = doc.new_page()                                     # a figure with its caption under it
    p1.insert_image(pymupdf.Rect(100, 100, 300, 250), stream=_png(200, 150, (200, 30, 30)))
    p1.insert_text((180, 268), "圖 1.1", fontname="china-t", fontsize=10)
    p1.insert_text((72, 320), "把制動杆拉到A 處（見圖1.1）", fontname="china-t", fontsize=11)
    p2 = doc.new_page()                                     # text only, no image block
    p2.insert_text((72, 100), "制動杆拉到A 處時，輪椅車就無法推動", fontname="china-t", fontsize=11)
    doc.save(path)
    doc.close()


def setup_figure_chair():
    make_chair()
    make_figure_manual(config.DATA_DIR / "manuals" / "test-manual.pdf")
    record = {"record_id": "whill-model-c2", "steps": [
        {"id": "s1", "source": {"page": 1, "quote": "把制動杆拉到A 處（見圖1.1）"}, "figure_ref": "圖1.1"},
        {"id": "s2", "source": {"page": 2, "quote": "制動杆拉到A 處時，輪椅車就無法推動"}, "figure_ref": None},
        {"id": "s3", "source": {"page": 1, "quote": "把制動杆拉到A 處"}, "figure_ref": None},
        {"id": "s4", "source": {"page": 2, "quote": "Wipe with a soft cloth"}, "figure_ref": None},
    ]}
    out = config.OUT_DIR / "chair-t"
    out.mkdir(parents=True, exist_ok=True)
    (out / "record.json").write_text(json.dumps(record))
    return out


def test_needs_figure():
    assert figures.needs_figure("制動杆拉到A 處時")
    assert figures.needs_figure("see Fig. 3") and figures.needs_figure("move to position B")
    assert not figures.needs_figure("將輪椅車放平在地上，關閉電源")


def test_caption_index_pairs_split_words():
    out = setup_figure_chair()
    with pymupdf.open(config.DATA_DIR / "manuals" / "test-manual.pdf") as doc:
        index = figures.build_index(doc)
    assert list(index) == ["圖1.1"] and index["圖1.1"][0]["page"] == 1


def test_figure_crops_and_full_page_fallback():
    out = setup_figure_chair()
    llm.configure("offline", None, out)
    with pytest.raises(llm.OfflineWaiting):       # s3 needs a figure but names none: asks the vision LLM
        figures.run("chair-t")
    (out / "offline").mkdir(exist_ok=True)
    (out / "offline" / "figures_1_response.json").write_text('{"caption": "圖 1.1"}')
    llm.configure("offline", None, out)
    figures.run("chair-t")

    steps = {s["id"]: s for s in json.loads((out / "record.json").read_text())["steps"]}
    assert steps["s1"]["figure"]["matched_by"] == "manual_text" and steps["s1"]["figure"]["caption"] == "圖1.1"
    assert steps["s3"]["figure"]["matched_by"] == "ai"
    assert steps["s2"]["figure"]["matched_by"] == "page"          # 處 but no image block on page 2
    assert "figure" not in steps["s4"]                             # no figure needed
    with Image.open(out / "figures" / "s1.png") as crop, Image.open(out / "figures" / "s2.png") as page:
        assert crop.width < 600 and crop.height < 500               # the figure + caption, at 2x
        assert page.size == (1190, 1684)                            # the whole A4 page, at 2x
    assert (config.LIBRARY_DIR / "whill-model-c2.json").is_file()


def test_figure_route_serves_the_crop():
    out = setup_figure_chair()
    (config.DEVICES_DIR).mkdir(parents=True, exist_ok=True)
    (config.DEVICES_DIR / "chair-t.json").write_text(json.dumps({**FIXTURE_CHAIR, "chair_id": "chair-t"}))
    (out / "figures").mkdir(exist_ok=True)
    Image.new("RGB", (10, 10)).save(out / "figures" / "s1.png")
    assert client.get("/figure/chair-t/s1").headers["content-type"] == "image/png"
    assert client.get("/figure/chair-t/..%2Frecord").status_code == 404
