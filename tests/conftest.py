import pytest

from app import config


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path, monkeypatch):
    """Never touch the real TAGALONG_DATA_DIR in tests."""
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "STATE_DIR", tmp_path / "state")
