"""Page flow: step bar and the step-done pages between the main pages."""
import copy
import json

import pytest
from fastapi.testclient import TestClient

from app import config
from app.main import app

client = TestClient(app)
FIXTURE_RECORD = json.loads((config.FIXTURES_DIR / "library" / "whill-model-c2.json").read_text())
FIXTURE_CHAIR = json.loads((config.FIXTURES_DIR / "devices" / "chair-a.json").read_text())


def build_all():
    for stage in ("plate", "manual", "label"):
        client.post(f"/api/{stage}/chair-a")


def decide_all(status="confirmed"):
    client.post("/api/labels/chair-a", json={"status": status})


def get(url):
    return client.get(url, follow_redirects=False)


@pytest.mark.parametrize("step, headline, button, next_url", [
    ("chosen", "Wheelchair selected", "Build the passport", "/build/chair-a"),
    ("built", "Passport built from the manufacturer&#39;s manual", "Check the labels", "/confirm/chair-a"),
    ("confirmed", "Wheelchair information confirmed", "Go to wheelchair passport", "/passport/chair-a"),
])
def test_step_done_pages(step, headline, button, next_url):
    build_all()
    decide_all()
    r = get(f"/done/chair-a/{step}")
    assert r.status_code == 200
    assert headline in r.text
    assert f'<a class="btn btn-gold btn-big" href="{next_url}">{button}</a>' in r.text
    assert "Scan to continue on your phone" in r.text and "<svg" in r.text
    assert "Concept" in r.text


def test_qr_encodes_the_absolute_next_url(monkeypatch):
    monkeypatch.setattr(config, "PUBLIC_URL", "https://example.test")
    seen = []
    import segno
    real = segno.make
    monkeypatch.setattr(segno, "make", lambda content, **kw: seen.append(content) or real(content, **kw))
    assert get("/done/chair-a/chosen").status_code == 200
    assert seen == ["https://example.test/build/chair-a"]


def test_guard_redirects_when_the_step_is_not_done():
    r = get("/done/chair-a/built")
    assert r.status_code == 303 and r.headers["location"] == "/build/chair-a"
    build_all()
    r = get("/done/chair-a/confirmed")           # labels still pending
    assert r.status_code == 303 and r.headers["location"] == "/confirm/chair-a"
    assert get("/done/chair-a/nonsense").status_code == 404


def test_pages_link_to_the_step_done_pages():
    assert 'href="/done/chair-a/chosen"' in client.get("/").text
    assert 'href="/done/chair-a/built"' in client.get("/build/chair-a").text
    assert 'href="/done/chair-a/confirmed"' in client.get("/confirm/chair-a").text


def test_fast_skips_the_step_done_pages():
    assert 'href="/build/chair-a?fast=1"' in client.get("/?fast=1").text
    build_all()
    decide_all()
    page = client.get("/confirm/chair-a?fast=1").text
    done = page.split('id="done"')[1].split(">")[0]
    assert 'href="/passport/chair-a?fast=1"' in done           # "Done" goes straight to the passport
    r = get("/done/chair-a/confirmed?fast=1")                   # an old link redirects too
    assert r.status_code == 303 and r.headers["location"] == "/passport/chair-a?fast=1"
    assert 'href="/confirm/chair-a?fast=1"' in client.get("/passport/chair-a?fast=1").text  # step bar keeps it


def test_summary_line_counts_from_the_records():
    record = copy.deepcopy(FIXTURE_RECORD)
    record["quotes"] = {"verified": 5, "total": 7}
    chair = copy.deepcopy(FIXTURE_CHAIR)
    for folder, name, data in ((config.LIBRARY_DIR, "whill-model-c2.json", record),
                               (config.DEVICES_DIR, "chair-a.json", chair)):
        folder.mkdir(parents=True, exist_ok=True)
        (folder / name).write_text(json.dumps(data))
    n_steps = len(record["steps"])
    n_parts = len({l["part_id"] for l in chair["labels"] if l["photo"]})
    assert "Model not read yet" in get("/done/chair-a/chosen").text
    build_all()
    assert f"{record['make']} {record['model']}" in get("/done/chair-a/chosen").text
    built = get("/done/chair-a/built").text
    assert f"{n_steps} steps · 5 of 7 quotes verified · {n_parts} parts found on the photos" in built
    client.post("/api/labels/chair-a/1", json={"status": "confirmed"})
    client.post("/api/labels/chair-a/2", json={"status": "rejected"})
    assert "1 labels confirmed · 1 hidden" in get("/done/chair-a/confirmed").text


def test_summary_leaves_out_missing_quote_counts():
    build_all()   # the M1 fixture record has no "quotes" counts
    built = get("/done/chair-a/built").text
    assert "quotes verified" not in built and "parts found on the photos" in built


def test_step_bar():
    page = client.get("/confirm/chair-a").text
    assert 'class="stepbar"' in page
    assert 'class="step-done"' in page and '<a href="/build/chair-a">' in page   # done steps are links
    assert 'class="step-current" aria-current="step"' in page
    assert 'href="/passport/chair-a"' not in page.split('class="stepbar"')[1].split("</nav>")[0]  # later: no link
    for url in ("/", "/build/chair-a", "/passport/chair-a", "/uses/chair-a/checkin"):
        assert 'class="stepbar"' in client.get(url).text
    for url in ("/passport/chair-a/print", "/manual/whill-model-c2/61"):
        assert 'class="stepbar"' not in client.get(url).text
