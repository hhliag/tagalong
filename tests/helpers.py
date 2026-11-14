"""Build a tiny chair folder + manual PDF in the test data dir."""
import pymupdf
from PIL import Image

from app import config

MANUAL_PAGES = [
    "WHILL Model C2\nOwner's Manual",
    "Contents\nSafety\nDriving\nCare",
    "Manual mode\nPull the freewheel levers on both sides to switch to manual mode.\n"
    "WARNING: Do not use manual mode on a slope.\nPush the free-\nwheel levers back before driving.",
    "Power\nPress the power button to turn the power off.\nCheck that the chair does not move.",
    "Battery\nThe battery can be removed from the vehicle.\nLithium-ion battery. Remove the key before lifting.",
    "Specifications\nWeight: 52 kg\nDimensions: 985 x 554 x 743 mm\nNominal voltage: 25.2 V\nCapacity: 10.8 Ah",
    "Cleaning\nWipe with a soft cloth.",
]

META = "make: WHILL\nmodel: Model C2\nmanual: test-manual.pdf\nphoto_source: test images\n"


def make_pdf(path, pages=MANUAL_PAGES):
    doc = pymupdf.open()
    for text in pages:
        page = doc.new_page()
        page.insert_text((72, 72), text, fontsize=11)
    doc.save(path)
    doc.close()


def make_chair(chair_id="chair-t", meta=META, views=("left", "right", "front", "rear"), size=(1600, 1200)):
    folder = config.DATA_DIR / "chairs" / chair_id
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "meta.yaml").write_text(meta)
    for v in views:
        Image.new("RGB", size, (90, 110, 120)).save(folder / f"{v}.jpg")
    manuals = config.DATA_DIR / "manuals"
    manuals.mkdir(parents=True, exist_ok=True)
    make_pdf(manuals / "test-manual.pdf")
    return folder
