import json
from types import SimpleNamespace

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QApplication, QComboBox, QDialog, QInputDialog, QLineEdit

from bagheeraview.core import app, widgets


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
    group = QComboBox()
    group.addItem("Flat", "flat")
    group.addItem("Folder", "folder")
    group.addItem("Day", "day")
    sort = QComboBox()
    sort.addItem("Name ascending", "name_asc")
    sort.addItem("Date descending", "date_desc")
    main_win = SimpleNamespace(
        view_mode_combo=group, sort_combo=sort,
        search_input=SimpleNamespace(currentText=lambda: "new query"),
        process_term=lambda term: None,
        viewer_shortcuts={})
    return widgets.BookmarksWidget(main_win), bookmarks_path


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


def test_add_overwrite_and_reorder_preserve_view_options(
        bookmarks_fixture, monkeypatch):
    widget, path = bookmarks_fixture
    monkeypatch.setattr(QInputDialog, "getText", lambda *args: ("Comment", True))
    widget.main_win.view_mode_combo.setCurrentIndex(1)
    widget.main_win.sort_combo.setCurrentIndex(1)
    widget.add_bookmark()
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved[1] == {
        "comment": "Comment", "query": "new query", "shortcut": "",
        "group": "folder", "sort": "date_desc",
    }

    widget.main_win.view_mode_combo.setCurrentIndex(2)
    widget.main_win.sort_combo.setCurrentIndex(0)
    widget.overwrite_bookmark()
    widget.move_up()
    widget.refresh_list()
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert (saved[0]["group"], saved[0]["sort"]) == ("day", "name_asc")
    assert widget.table.item(0, 3).text() == "Day"
    assert widget.table.item(0, 4).text() == "Name ascending"
    assert "group" not in saved[1] and "sort" not in saved[1]


def test_edit_options_can_be_selected_and_cleared_independently(
        bookmarks_fixture, monkeypatch):
    widget, path = bookmarks_fixture
    widget.table.setCurrentCell(0, 0)

    def select_options(dialog):
        group, sort = dialog.findChildren(QComboBox)
        assert group.currentData() is None
        assert sort.currentData() is None
        group.setCurrentIndex(group.findData("flat"))
        sort.setCurrentIndex(sort.findData("date_desc"))
        return QDialog.Accepted

    monkeypatch.setattr(QDialog, "exec", select_options)
    widget.edit_bookmark()
    saved = json.loads(path.read_text(encoding="utf-8"))[0]
    assert saved["group"] == "flat"
    assert saved["sort"] == "date_desc"

    def clear_group(dialog):
        group, sort = dialog.findChildren(QComboBox)
        assert group.currentData() == "flat"
        assert sort.currentData() == "date_desc"
        group.setCurrentIndex(0)
        return QDialog.Accepted

    monkeypatch.setattr(QDialog, "exec", clear_group)
    widget.edit_bookmark()
    widget.refresh_list()
    saved = json.loads(path.read_text(encoding="utf-8"))[0]
    assert "group" not in saved
    assert saved["sort"] == "date_desc"
    assert widget.table.item(0, 3).text() == ""
    widget.table.setCurrentCell(0, 0)
    widget.main_win.view_mode_combo.setCurrentIndex(2)
    widget.main_win.sort_combo.setCurrentIndex(0)
    widget.load_selected()
    assert widget.main_win.view_mode_combo.currentData() == "day"
    assert widget.main_win.sort_combo.currentData() == "date_desc"


def test_load_and_shortcut_apply_bookmark_options(
        bookmarks_fixture, monkeypatch):
    widget, path = bookmarks_fixture
    group = widget.main_win.view_mode_combo
    sort = widget.main_win.sort_combo
    terms = []
    widget.main_win.process_term = lambda term: terms.append(
        (term, group.currentData(), sort.currentData()))
    widget.table.setCurrentCell(0, 0)

    group.setCurrentIndex(1)
    sort.setCurrentIndex(1)
    widget.load_selected()
    assert terms == [("old query", "folder", "date_desc")]
    assert (group.currentData(), sort.currentData()) == ("folder", "date_desc")

    bookmarks = [{
        "query": "other query", "comment": "Other", "shortcut": "Ctrl+1",
        "group": "flat", "sort": "name_asc",
    }]
    path.write_text(json.dumps(bookmarks), encoding="utf-8")
    widget.refresh_list()
    widget.table.setCurrentCell(0, 0)
    widget.load_selected()
    assert terms[-1] == ("other query", "flat", "name_asc")
    assert (group.currentData(), sort.currentData()) == ("flat", "name_asc")

    group.setCurrentIndex(1)
    sort.setCurrentIndex(1)
    widget.main_win.bookmarks_tab = widget
    controller = SimpleNamespace(
        main_win=widget.main_win, _bookmark_shortcuts={}, _shortcuts={},
        _refresh_native_shortcuts=lambda: None)
    monkeypatch.setattr(app, "BOOKMARKS_PATH", str(path))
    app.AppShortcutController.refresh_bookmark_shortcuts(controller)
    sequence = QKeySequence("Ctrl+1")
    key = int(sequence[0].key())
    modifiers = Qt.KeyboardModifiers(sequence[0].keyboardModifiers())
    app.AppShortcutController._activate_shortcut(controller, key, modifiers)
    assert terms[-1] == ("other query", "flat", "name_asc")
    assert (group.currentData(), sort.currentData()) == ("flat", "name_asc")
    assert "other query" in app.AppShortcutController.check_conflict(
        controller, key, modifiers)

    path.write_text(json.dumps([{
        "query": "legacy", "comment": "Old", "shortcut": "Ctrl+1"}]),
        encoding="utf-8")
    app.AppShortcutController.refresh_bookmark_shortcuts(controller)
    group.setCurrentIndex(2)
    sort.setCurrentIndex(1)
    app.AppShortcutController._activate_shortcut(controller, key, modifiers)
    assert terms[-1] == ("legacy", "day", "date_desc")
    assert (group.currentData(), sort.currentData()) == ("day", "date_desc")


def test_layout_bookmark_options_override_restored_layout(bookmarks_fixture):
    widget, _path = bookmarks_fixture
    group = widget.main_win.view_mode_combo
    sort = widget.main_win.sort_combo

    def restore_layout(_term):
        group.setCurrentIndex(1)
        sort.setCurrentIndex(1)

    widget.main_win.process_term = restore_layout
    widget.run_bookmark({
        "query": "layout:/example", "group": "flat", "sort": "name_asc"})
    assert (group.currentData(), sort.currentData()) == ("flat", "name_asc")
