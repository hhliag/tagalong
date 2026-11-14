import json

import pytest

from app import config
from pipeline import pages
from pipeline.common import PipelineError
from tests.helpers import make_chair


def test_pages_keeps_relevant_pages_and_spec_page(capsys):
    make_chair()
    result = pages.run("chair-t")
    assert result["page_count"] == 7
    assert result["spec_page"] == 6
    assert {3, 4, 5, 6} <= set(result["kept"])
    assert 7 not in result["kept"]          # "Cleaning" has no keyword
    assert result["model_found_in_first_pages"] is True
    saved = json.loads((config.OUT_DIR / "chair-t" / "pages.json").read_text())
    assert saved["pages"][0]["page"] == 1    # 1-based
    assert (config.SAVED_DIR / "chair-t" / "pages.json").is_file()
    assert "pages: 7 pages in test-manual.pdf; kept 4: 3, 4, 5, 6" in capsys.readouterr().out


def test_keyword_matching_uses_word_boundaries():
    assert pages.score_page("When the keyboard is removed")[0] == 1   # only "remove"
    assert pages.score_page("272 Wh, remove the key")[0] == 3


def test_not_a_pdf_fails_clearly():
    folder = make_chair()
    (config.DATA_DIR / "manuals" / "test-manual.pdf").write_text("not a pdf")
    with pytest.raises(PipelineError, match="Not a PDF"):
        pages.run("chair-t")


def test_wrong_model_only_warns(capsys):
    make_chair(meta="make: WHILL\nmodel: Model F\nmanual: test-manual.pdf\n")
    pages.run("chair-t")
    assert "WARNING: model name 'Model F' not found" in capsys.readouterr().out


def test_missing_meta_fails_clearly():
    with pytest.raises(PipelineError, match="meta.yaml"):
        pages.run("nope")


def test_chinese_keywords_count_even_across_line_breaks():
    distinct, _ = pages.score_page("使用前請關閉電\n源，拉起離合器。電池為鋰電池。")
    assert distinct >= 4   # 關閉電源, 離合, 電池, 鋰
    assert pages.score_page("清潔：用軟布擦拭。")[0] == 0
