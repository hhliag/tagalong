import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

DATA_DIR = Path(os.environ.get("TAGALONG_DATA_DIR") or ROOT / "data").expanduser()
STATE_DIR = DATA_DIR / "state"  # runtime copies of chair records (label decisions, build progress)
LIBRARY_DIR = ROOT / "library"   # pipeline output (DESIGN §3.3); wins over the fixtures
DEVICES_DIR = ROOT / "devices"   # pipeline output (DESIGN §3.4)
FIXTURES_DIR = ROOT / "app" / "fixtures"  # hand-written M1 records, used when no pipeline output exists
# pipeline working files, one folder per chair; the app serves figure crops from here
OUT_DIR = Path(os.environ.get("TAGALONG_OUT_DIR") or ROOT / "out").expanduser()
SAVED_DIR = ROOT / "saved"       # copy of every pipeline result (DESIGN §4)

HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "8000"))
# Base of the links in QR codes. PUBLIC_BASE_URL, or the older name PUBLIC_URL; empty = the request's own address.
PUBLIC_URL = (os.environ.get("PUBLIC_BASE_URL") or os.environ.get("PUBLIC_URL", "")).rstrip("/")

# DESIGN §4: live | saved. Cloud Run sets K_SERVICE, so a deployed copy defaults to saved.
# Live mode is not built yet, so nothing reads this; every stage returns saved results.
MODE = os.environ.get("MODE") or ("saved" if os.environ.get("K_SERVICE") else "live")
