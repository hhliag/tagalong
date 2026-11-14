"""JSON file storage. library/ and devices/ are the saved data; STATE_DIR holds runtime changes."""
import json
import re
import shutil

from . import config


def _read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _files(kind):
    """{stem: path} for library/ or devices/: pipeline output wins over the hand-written fixture."""
    found = {p.stem: p for p in sorted((config.FIXTURES_DIR / kind).glob("*.json"))}
    out_dir = config.LIBRARY_DIR if kind == "library" else config.DEVICES_DIR
    found.update({p.stem: p for p in sorted(out_dir.glob("*.json"))})
    return found


def records():
    return [_read(p) for p in _files("library").values()]


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
    return sorted(_files("devices"))


def chair(chair_id):
    source = _files("devices").get(chair_id)
    if source is None:
        return None
    state = config.STATE_DIR / f"{chair_id}.json"
    if state.exists():
        return _read(state)
    data = _read(source)
    data["stages"] = []  # build stages finished so far
    return data


def save_chair(data):
    config.STATE_DIR.mkdir(parents=True, exist_ok=True)
    path = config.STATE_DIR / f"{data['chair_id']}.json"
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def reset(chair_id=None):
    """Forget runtime changes: for one chair, or for all."""
    if chair_id:
        (config.STATE_DIR / f"{chair_id}.json").unlink(missing_ok=True)
    else:
        shutil.rmtree(config.STATE_DIR, ignore_errors=True)
