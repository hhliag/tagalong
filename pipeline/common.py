"""Paths and file helpers shared by the stages."""
import json
import re
import shutil
from pathlib import Path

import yaml

from app import config

VIEWS = ["left", "right", "front", "rear"]


class PipelineError(Exception):
    """A clear, expected failure: printed without a traceback, exit code 2."""


def chair_dir(chair_id):
    return config.DATA_DIR / "chairs" / chair_id


def out_dir(chair_id):
    d = config.OUT_DIR / chair_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def saved_dir(chair_id):
    d = config.SAVED_DIR / chair_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def slug(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def read_meta(chair_id):
    path = chair_dir(chair_id) / "meta.yaml"
    if not path.is_file():
        raise PipelineError(f"Missing {path} (needs make, model, manual).")
    meta = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    for key in ("make", "model", "manual"):
        if not meta.get(key):
            raise PipelineError(f"{path}: '{key}' is missing.")
    return meta


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def read_stage_file(chair_id, name, made_by):
    path = config.OUT_DIR / chair_id / name
    if not path.is_file():
        raise PipelineError(f"Missing {path}. Run --stage {made_by} first.")
    return json.loads(path.read_text(encoding="utf-8"))


def save_copy(chair_id, path):
    """Keep a copy of every result in saved/<chair_id>/ (DESIGN §4)."""
    shutil.copy2(path, saved_dir(chair_id) / Path(path).name)
