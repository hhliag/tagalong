import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

DATA_DIR = Path(os.environ.get("TAGALONG_DATA_DIR") or ROOT / "data").expanduser()
STATE_DIR = DATA_DIR / "state"  # runtime copies of chair records (label decisions, build progress)
LIBRARY_DIR = ROOT / "library"
DEVICES_DIR = ROOT / "devices"

HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "8000"))
PUBLIC_URL = os.environ.get("PUBLIC_URL", "").rstrip("/")
