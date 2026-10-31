import json
from types import SimpleNamespace

import pytest
from PySide6.QtWidgets import QApplication, QDialog, QLineEdit

from bagheeraview.core import widgets


@pytest.fixture
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def favorites_fixture(qapp, tmp_path, monkeypatch):
    favorites_path = tmp_path / "favorites.json"
    favorites_path.write_text(json.dumps([{
        "comment": "Old comment",
        "query": "old query",
        "shortcut": "Ctrl+1",
    }]), encoding="utf-8")
    monkeypatch.setattr(widgets, "FAVORITES_PATH", str(favorites_path))
    return widgets.FavoritesWidget(SimpleNamespace()), favorites_path


def test_edit_favorite_updates_comment_and_query(
        favorites_fixture, monkeypatch):
    favorite_widget, favorites_path = favorites_fixture
    dialog_minimum_width = []

    def accept_with_edits(dialog):
        dialog_minimum_width.append(dialog.minimumWidth())
        comment_edit, query_edit = dialog.findChildren(QLineEdit)
        comment_edit.setText("Updated comment")
        query_edit.setText("updated query")
        return QDialog.Accepted

    monkeypatch.setattr(QDialog, "exec", accept_with_edits)
    favorite_widget.table.setCurrentCell(0, 0)

    favorite_widget.edit_favorite()

    assert dialog_minimum_width == [500]
    assert favorite_widget.table.item(0, 0).text() == "Updated comment"
    assert favorite_widget.table.item(0, 0).toolTip() == "Updated comment"
    assert favorite_widget.table.item(0, 1).text() == "updated query"
    assert favorite_widget.table.item(0, 1).toolTip() == "updated query"
    saved = json.loads(favorites_path.read_text(encoding="utf-8"))
    assert saved == [{
        "comment": "Updated comment",
        "query": "updated query",
        "shortcut": "Ctrl+1",
    }]

def test_edit_favorite_cancel_keeps_values(favorites_fixture, monkeypatch):
    favorite_widget, _favorites_path = favorites_fixture
    monkeypatch.setattr(QDialog, "exec", lambda _dialog: QDialog.Rejected)
    favorite_widget.table.setCurrentCell(0, 0)

    favorite_widget.edit_favorite()

    assert favorite_widget.table.item(0, 0).text() == "Old comment"
    assert favorite_widget.table.item(0, 1).text() == "old query"
