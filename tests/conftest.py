import pytest

from app import config


@pytest.fixture(autouse=True)
def isolated_dirs(tmp_path, monkeypatch):
    """Never touch the real data folder or pipeline output in tests.

    library/ and devices/ start empty, so the M1 pages use the hand-written fixtures.
    """
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(config, "STATE_DIR", tmp_path / "data" / "state")
    monkeypatch.setattr(config, "LIBRARY_DIR", tmp_path / "library")
    monkeypatch.setattr(config, "DEVICES_DIR", tmp_path / "devices")
    monkeypatch.setattr(config, "OUT_DIR", tmp_path / "out")
    monkeypatch.setattr(config, "SAVED_DIR", tmp_path / "saved")
