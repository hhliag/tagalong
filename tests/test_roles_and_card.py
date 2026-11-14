"""Home intro and doors, role chips, and the passport's card-first layout."""
import re

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_home_has_the_problem_line_and_both_doors():
    page = client.get("/").text
    assert "Her wheelchair flies without her." in page
    assert page.index("Her wheelchair flies without her.") < page.index("Pick a chair")
    assert '<a class="card door" href="#pick"><b>I am the passenger</b><span>Make the passport for my chair</span>' in page
    assert '<a class="card door" href="/crew"><b>I am ramp crew</b><span>Look up how to handle a chair</span>' in page
    assert 'id="pick"' in page
    assert "Demo: choose a sample chair. In real use, she takes 4 photos of her own." in page
    assert "Crew: look up a chair" not in page


def chips(page):
    return re.findall(r'<span class="role-chip role-\w+">([^<]+)</span>', page)


@pytest.mark.parametrize("url, chip", [
    ("/", "Owner view"),
    ("/build/chair-a", "Owner view"),
    ("/confirm/chair-a", "Owner view"),
    ("/passport/chair-a", "Owner view"),
    ("/uses/chair-a/onboard", "Owner view"),
    ("/uses/chair-a/return", "Owner view"),
    ("/crew", "Crew view"),
    ("/crew/AP-7Q4K", "Crew view"),
    ("/passport/chair-a/print", "Crew view"),
    ("/uses/chair-a/checkin", "Check-in view"),
])
def test_each_page_shows_its_role_chip(url, chip):
    page = client.get(url).text
    assert chips(page) == [chip]
    assert ('class="stepbar"' in page) == (chip == "Owner view" and "/print" not in url)


def test_done_page_is_owner_view():
    client.post("/api/labels/chair-a", json={"status": "confirmed"})
    for stage in ("plate", "manual", "label"):
        client.post(f"/api/{stage}/chair-a")
    assert chips(client.get("/done/chair-a/chosen").text) == ["Owner view"]


def test_passport_shows_the_card_before_the_record():
    page = client.get("/passport/chair-a").text
    preview = page.index('class="card-preview"')
    record = page.index("The full record")
    assert preview < page.index('<figure class="photo">')
    assert page.index('<div class="photos">') > record          # the record's photos come after the card
    assert "This card travels on her chair" in page
    assert '<a class="btn btn-gold" href="/passport/chair-a/print">Open the card</a>' in page
    assert "The card is one part of her chair's record. The full record is below." in page


def test_on_the_card_tags_follow_the_print_page():
    client.post("/api/labels/chair-a", json={"status": "confirmed"})
    page = client.get("/passport/chair-a").text
    printed = client.get("/passport/chair-a/print").text
    record = page.split("The full record", 1)[1]
    steps = re.findall(r'<li class="step">(.*?)</li>', record, re.S)
    assert steps
    for s in steps:
        action = re.search(r'<p class="step-action">([^<]+)</p>', s).group(1)
        assert ("On the card" in s) == (action in printed), action
    assert any("On the card" not in s for s in steps)     # s3 is not a must-do step, so not on the card


def test_other_uses_strip():
    page = client.get("/passport/chair-a").text
    strip = page.split("The same record also gives", 1)[1]
    assert "Same passport, other uses" not in page
    assert "Printed card" not in strip
    tiles = re.findall(r'<a class="card tile"[^>]*>(.*?)</a>', strip, re.S)
    concept = [re.search(r"<b>([^<]+)</b>", t).group(1) for t in tiles if "Concept" in t]
    assert concept == ["On board", "Return check"]
