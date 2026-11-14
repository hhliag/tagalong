import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

PAGES = [
    "/",
    "/build/chair-a",
    "/confirm/chair-a",
    "/passport/chair-a",
    "/passport/chair-a/print",
    "/uses/chair-a/checkin",
    "/uses/chair-a/onboard",
    "/uses/chair-a/return",
    "/manual/whill-model-c2/24?step=s2",
]


@pytest.mark.parametrize("path", PAGES)
def test_page_renders_with_concept_chip(path):
    r = client.get(path)
    assert r.status_code == 200
    assert 'class="concept-chip"' in r.text


@pytest.mark.parametrize("path", ["/build/chair-a", "/passport/chair-a"])
def test_sample_photo_note(path):
    assert "Sample photos. In real use the owner takes them." in client.get(path).text


def test_unknown_chair_and_use_404():
    assert client.get("/passport/nope").status_code == 404
    assert client.get("/uses/chair-a/nope").status_code == 404
    assert client.get("/photo/chair-a/..%2Fsecret.jpg").status_code == 404


def test_name_hidden_until_plate_read():
    assert "WHILL" not in client.get("/").text
    r = client.post("/api/plate/chair-a")
    assert r.json() == {"source": "saved", "make": "WHILL", "model": "Model C2", "raw": "WHILL Model C2"}
    assert "WHILL Model C2" in client.get("/").text


def test_pipeline_stages_return_saved_results():
    assert client.post("/api/manual/chair-a").json()["found"] == "library"
    assert client.post("/api/label/chair-a").json() == {"source": "saved", "count": 2}


def test_confirm_flow_drives_the_passport():
    before = client.get("/passport/chair-a").text
    assert "2 labels hidden" in before

    r = client.post("/api/labels/chair-a/1", json={"status": "confirmed"})
    assert r.json()["pending"] == 1
    client.post("/api/labels/chair-a/2", json={"status": "rejected"})

    after = client.get("/passport/chair-a").text
    assert "1 label hidden" in after
    assert "Owner-confirmed" in after
    assert 'id="dot-1"' in after and 'id="dot-2"' not in after

    ret = client.get("/uses/chair-a/return").text
    assert "Freewheel lever in place" in ret and "Battery in place" not in ret


def test_bad_label_status_rejected():
    assert client.post("/api/labels/chair-a/1", json={"status": "maybe"}).status_code == 422
    assert client.post("/api/labels/chair-a/9", json={"status": "confirmed"}).status_code == 404


def test_checkin_shows_ssr_and_computed_wh():
    text = client.get("/uses/chair-a/checkin").text
    assert "WCLB" in text
    assert "≈ 272 Wh (computed, not a manual figure)" in text
    assert "/manual/whill-model-c2/61" in text


def test_print_card():
    text = client.get("/passport/chair-a/print").text
    assert "Return to the aircraft door" in text
    assert "AP-7Q4K" in text
    assert "<svg" in text  # QR
    assert "52 kg" in text and "Press the power button" in text


def test_photo_placeholder_when_missing():
    r = client.get("/photo/chair-a/left.jpg")
    assert r.status_code == 200 and r.headers["content-type"].startswith("image/svg+xml")


def test_confirm_shows_all_four_views():
    text = client.get("/confirm/chair-a").text
    for view in ("left", "right", "front", "rear"):
        assert f'src="/photo/chair-a/{view}.jpg"' in text
    assert text.count('id="dot-') == 2   # the fixture's two labels, each on one photo


def test_confirm_pins_are_tap_targets_without_a_list():
    text = client.get("/confirm/chair-a").text
    assert 'data-id="1" role="button"' in text and 'data-id="2" role="button"' in text
    assert "decide-list" not in text and "btn-icon" not in text
    assert 'role="button"' not in client.get("/passport/chair-a").text   # only /confirm is clickable


def test_tap_cycle_back_to_pending_locks_done():
    client.post("/api/labels/chair-a/1", json={"status": "confirmed"})
    client.post("/api/labels/chair-a/2", json={"status": "rejected"})
    assert "disabled" not in client.get("/confirm/chair-a").text.split('id="done"')[1].split(">")[0]
    assert client.post("/api/labels/chair-a/2", json={"status": "pending"}).json()["pending"] == 1


def test_drag_moves_a_pin():
    r = client.post("/api/labels/chair-a/1/move", json={"x": 0.25, "y": 1.7})
    assert r.status_code == 200 and (r.json()["x"], r.json()["y"]) == (0.25, 1.0)   # clamped to the photo
    assert "left: 25.0%; top: 100.0%" in client.get("/confirm/chair-a").text
    assert client.post("/api/labels/chair-a/9/move", json={"x": 0.1, "y": 0.1}).status_code == 404


def test_check_all_confirms_every_label():
    assert 'id="check-all"' in client.get("/confirm/chair-a").text
    r = client.post("/api/labels/chair-a", json={"status": "confirmed"})
    assert r.json() == {"status": "confirmed", "count": 2, "pending": 0}
    assert "label hidden" not in client.get("/passport/chair-a").text
    assert client.post("/api/labels/chair-a", json={"status": "maybe"}).status_code == 422
