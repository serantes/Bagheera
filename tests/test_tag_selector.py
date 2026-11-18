import os
from types import SimpleNamespace

import lmdb
import pytest
from PySide6.QtWidgets import QApplication

from bagheerasearch.tools.baloo_tools.baloo_tools import BalooTools
from bagheeraview.core import widgets


@pytest.fixture
def qapp():
    return QApplication.instance() or QApplication([])


def test_tag_selector_and_editor_share_open_baloo_environment(qapp, tmp_path, monkeypatch):
    index = tmp_path / "index"
    env = lmdb.open(str(index), max_dbs=20)
    posting = env.open_db(b"postingdb", create=True)
    with env.begin(write=True) as txn:
        for key in (b"TAG-People/Alice", b"TAG-Pets/Cat", b"OTHER"):
            txn.put(key, b"1", db=posting)
    monkeypatch.setattr(BalooTools, "_shared_env", env)
    monkeypatch.setattr(BalooTools, "_shared_dbs", {})
    expanduser = os.path.expanduser
    monkeypatch.setattr(
        os.path, "expanduser",
        lambda path: str(index) if path == "~/.local/share/baloo/index"
        else expanduser(path))
    try:
        selector = widgets.TagSelectorDialog()
        assert selector.selector_widget.available_tags == ["People/Alice", "Pets/Cat"]
        selector.selector_widget.line_edit.setText("Alice")
        assert selector.selector_widget.proxy_model.rowCount() == 1

        editor = SimpleNamespace(available_tags=[], _load_all=False)
        widgets.TagEditWidget.load_available_tags(editor)
        assert editor.available_tags == ["People/Alice", "Pets/Cat"]
    finally:
        env.close()


@pytest.mark.parametrize("subdir", [True, False])
def test_baloo_tags_open_file_or_directory_index(tmp_path, monkeypatch, subdir):
    index = tmp_path / "index"
    env = lmdb.open(str(index), subdir=subdir, max_dbs=20)
    posting = env.open_db(b"postingdb", create=True)
    with env.begin(write=True) as txn:
        txn.put(b"TAG-Family/Alice", b"1", db=posting)
    env.close()

    monkeypatch.setattr(BalooTools, "_shared_env", None)
    monkeypatch.setattr(BalooTools, "_shared_dbs", {})
    tools = BalooTools()
    tools.baloo_db_path = str(index)
    try:
        assert tools.list_tags() == ["Family/Alice"]
        assert BalooTools().env is tools.env
    finally:
        tools.env.close()


def test_tag_loading_logs_failure_and_keeps_previous_tags(monkeypatch, caplog):
    editor = SimpleNamespace(available_tags=["Existing"], _load_all=False)

    def fail():
        raise lmdb.Error("index unavailable")

    monkeypatch.setattr(widgets, "list_baloo_tags", fail)
    widgets.TagEditWidget.load_available_tags(editor)
    assert editor.available_tags == ["Existing"]
    assert "Failed to load Baloo tags: index unavailable" in caplog.text
