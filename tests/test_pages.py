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
