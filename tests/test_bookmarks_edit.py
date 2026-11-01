import json
from types import SimpleNamespace

import pytest
from PySide6.QtWidgets import QApplication, QDialog, QLineEdit

from bagheeraview.core import widgets


@pytest.fixture
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def bookmarks_fixture(qapp, tmp_path, monkeypatch):
    bookmarks_path = tmp_path / "favorites.json"
    bookmarks_path.write_text(json.dumps([{
        "comment": "Old comment",
        "query": "old query",
        "shortcut": "Ctrl+1",
    }]), encoding="utf-8")
    monkeypatch.setattr(widgets, "BOOKMARKS_PATH", str(bookmarks_path))
    return widgets.BookmarksWidget(SimpleNamespace()), bookmarks_path


def test_edit_bookmark_updates_comment_and_query(
        bookmarks_fixture, monkeypatch):
    bookmarks_widget, bookmarks_path = bookmarks_fixture
    dialog_minimum_width = []

    def accept_with_edits(dialog):
        dialog_minimum_width.append(dialog.minimumWidth())
        comment_edit, query_edit = dialog.findChildren(QLineEdit)
        comment_edit.setText("Updated comment")
        query_edit.setText("updated query")
        return QDialog.Accepted

    monkeypatch.setattr(QDialog, "exec", accept_with_edits)
    bookmarks_widget.table.setCurrentCell(0, 0)

    bookmarks_widget.edit_bookmark()

    assert dialog_minimum_width == [500]
    assert bookmarks_widget.table.item(0, 0).text() == "Updated comment"
    assert bookmarks_widget.table.item(0, 0).toolTip() == "Updated comment"
    assert bookmarks_widget.table.item(0, 1).text() == "updated query"
    assert bookmarks_widget.table.item(0, 1).toolTip() == "updated query"
    saved = json.loads(bookmarks_path.read_text(encoding="utf-8"))
    assert saved == [{
        "comment": "Updated comment",
        "query": "updated query",
        "shortcut": "Ctrl+1",
    }]

def test_edit_bookmark_cancel_keeps_values(bookmarks_fixture, monkeypatch):
    bookmarks_widget, _bookmarks_path = bookmarks_fixture
    monkeypatch.setattr(QDialog, "exec", lambda _dialog: QDialog.Rejected)
    bookmarks_widget.table.setCurrentCell(0, 0)

    bookmarks_widget.edit_bookmark()

    assert bookmarks_widget.table.item(0, 0).text() == "Old comment"
    assert bookmarks_widget.table.item(0, 1).text() == "old query"
