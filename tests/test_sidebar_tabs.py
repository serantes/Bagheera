from types import SimpleNamespace

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from bagheeraview.core.app import MainWindow, ShortcutHelpDialog
from bagheeraview.core.constants import DEFAULT_GLOBAL_SHORTCUTS, GLOBAL_ACTIONS


class FakeTabs:
    def __init__(self, widgets):
        self.widgets = list(widgets)
        self.current = self.widgets[0] if self.widgets else None

    def indexOf(self, widget):
        try:
            return self.widgets.index(widget)
        except ValueError:
            return -1

    def setCurrentWidget(self, widget):
        self.current = widget

    def setCurrentIndex(self, index):
        self.current = self.widgets[index]

    def currentWidget(self):
        return self.current

    def currentIndex(self):
        return self.indexOf(self.current)

    def widget(self, index):
        return self.widgets[index]

    def count(self):
        return len(self.widgets)


class FakeDock:
    def __init__(self):
        self.shown = False
        self.raised = False

    def show(self):
        self.shown = True

    def raise_(self):
        self.raised = True


@pytest.fixture
def qapp():
    return QApplication.instance() or QApplication([])


def test_tab_shortcuts_are_registered_and_listed_for_configuration(qapp):
    expected = {
        "show_tags_tab": Qt.Key_T,
        "show_info_tab": Qt.Key_I,
        "show_filter_tab": Qt.Key_F,
        "show_bookmarks_tab": Qt.Key_B,
        "show_history_tab": Qt.Key_H,
        "show_layouts_tab": Qt.Key_L,
        "show_maps_tab": Qt.Key_M,
    }
    configured = {
        (key, modifiers): (action, ignore, GLOBAL_ACTIONS[action][0],
                           GLOBAL_ACTIONS[action][1])
        for action, (key, modifiers, ignore) in DEFAULT_GLOBAL_SHORTCUTS.items()
        if action in expected
    }

    assert len(configured) == len(expected)
    for action, key in expected.items():
        combo = next(
            combo
            for combo, value in configured.items()
            if value[0] == action
        )
        assert combo == (int(key), Qt.ControlModifier | Qt.ShiftModifier)

    dialog = ShortcutHelpDialog(configured, {}, {}, None)
    listed_actions = {
        dialog.table.item(row, 0).text()
        for row in range(dialog.table.rowCount())
        if dialog.table.item(row, 0)
        and dialog.table.item(row, 0).data(Qt.UserRole) != "header"
    }
    assert {GLOBAL_ACTIONS[action][0] for action in expected} <= listed_actions


def test_open_sidebar_tab_selects_a_nested_browse_tab():
    tags_tab, info_tab = object(), object()
    filter_tab, bookmarks_tab, history_tab = object(), object(), object()
    metadata_tabs = FakeTabs([tags_tab, info_tab])
    browse_tabs = FakeTabs([filter_tab, bookmarks_tab, history_tab])
    layouts_tab, maps_tab = object(), object()
    sidebar_tabs = FakeTabs(
        [metadata_tabs, browse_tabs, layouts_tab, maps_tab])
    dock = FakeDock()
    window = SimpleNamespace(
        metadata_tabs=metadata_tabs,
        browse_tabs=browse_tabs,
        sidebar_tabs=sidebar_tabs,
        main_dock=dock,
        on_sidebar_tab_changed=lambda: None,
    )

    MainWindow.open_sidebar_tab(window, bookmarks_tab)

    assert browse_tabs.currentWidget() is bookmarks_tab
    assert sidebar_tabs.currentWidget() is browse_tabs
    assert dock.shown and dock.raised


def test_open_sidebar_tab_selects_metadata_and_direct_tabs():
    tags_tab, info_tab = object(), object()
    filter_tab, bookmarks_tab, history_tab = object(), object(), object()
    metadata_tabs = FakeTabs([tags_tab, info_tab])
    browse_tabs = FakeTabs([filter_tab, bookmarks_tab, history_tab])
    layouts_tab, maps_tab = object(), object()
    sidebar_tabs = FakeTabs(
        [metadata_tabs, browse_tabs, layouts_tab, maps_tab])
    dock = FakeDock()
    window = SimpleNamespace(
        metadata_tabs=metadata_tabs,
        browse_tabs=browse_tabs,
        sidebar_tabs=sidebar_tabs,
        main_dock=dock,
        on_sidebar_tab_changed=lambda: None,
    )

    MainWindow.open_sidebar_tab(window, info_tab)
    assert metadata_tabs.currentWidget() is info_tab
    assert sidebar_tabs.currentWidget() is metadata_tabs

    MainWindow.open_sidebar_tab(window, maps_tab)
    assert sidebar_tabs.currentWidget() is maps_tab
