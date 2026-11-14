"""JSON file storage. library/ and devices/ are the saved data; STATE_DIR holds runtime changes."""
import json
import re
import shutil

from . import config


def _read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def records():
    return [_read(p) for p in sorted(config.LIBRARY_DIR.glob("*.json"))]


def record(record_id):
    return next((r for r in records() if r["record_id"] == record_id), None)


def find_record(make, model):
    """Library lookup by make + model or alias (DESIGN §4.2)."""
    def key(s):
        return re.sub(r"[^a-z0-9]", "", (s or "").lower())

    for r in records():
        names = {key(r["model"]), *(key(a) for a in r.get("aliases", []))}
        if key(r["make"]) == key(make) and key(model) in names:
            return r
    return None


def chair_ids():
    return [p.stem for p in sorted(config.DEVICES_DIR.glob("*.json"))]


def chair(chair_id):
    if chair_id not in chair_ids():
        return None
    state = config.STATE_DIR / f"{chair_id}.json"
    if state.exists():
        return _read(state)
    data = _read(config.DEVICES_DIR / f"{chair_id}.json")
    data["stages"] = []  # build stages finished so far
    return data


def save_chair(data):
    config.STATE_DIR.mkdir(parents=True, exist_ok=True)
    path = config.STATE_DIR / f"{data['chair_id']}.json"
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def reset():
    shutil.rmtree(config.STATE_DIR, ignore_errors=True)
