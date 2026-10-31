import json
from types import SimpleNamespace

import pytest
from PySide6.QtWidgets import QApplication, QTableWidget

from bagheeraview.core.app import MainWindow
from bagheeraview.core import widgets


@pytest.fixture
def qapp():
    return QApplication.instance() or QApplication([])


def test_tag_filter_items_show_their_full_label_in_tooltip(qapp):
    table = QTableWidget(0, 2)

    class FilterState:
        tags_list = table
        _suppress_updates = False
        found_items_data = [("path", None, None, ["a/long/tag"], None, None, None)]
        tag_search_input = SimpleNamespace(text=lambda: "")

        @staticmethod
        def filter_tags_list(_text):
            pass

    MainWindow.update_tag_list(FilterState())

    assert table.item(0, 0).toolTip() == "a/long/tag (1)"


def test_history_name_cell_has_tooltip(qapp):
    main_window = SimpleNamespace(full_history=[{
        "path": "search:/a/long/search/path",
        "date": "2026-10-31",
    }])

    history_widget = widgets.HistoryWidget(main_window)

    assert history_widget.table.item(0, 0).toolTip() == "a/long/search/path"


def test_favorite_comment_and_query_cells_have_tooltips(qapp, tmp_path,
                                                         monkeypatch):
    favorites_path = tmp_path / "favorites.json"
    favorites_path.write_text(json.dumps([{
        "comment": "A long favorite comment",
        "query": "tag:landscape AND name:mountain",
        "shortcut": "",
    }]), encoding="utf-8")
    monkeypatch.setattr(widgets, "FAVORITES_PATH", str(favorites_path))

    favorites_widget = widgets.FavoritesWidget(SimpleNamespace())

    assert favorites_widget.table.item(0, 0).toolTip() == "A long favorite comment"
    assert favorites_widget.table.item(0, 1).toolTip() == (
        "tag:landscape AND name:mountain")
