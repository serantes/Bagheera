import json
from types import SimpleNamespace
import time

import pytest
from PySide6.QtCore import QObject, QThreadPool, Qt, Signal
from PySide6.QtGui import QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from bagheeraview.core import app as app_module, filesystemwatcher, metadatamanager
from bagheeraview.core import geomapwidget, imagescanner, widgets
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


@pytest.fixture
def sidebar_window_factory(qapp, tmp_path, monkeypatch):
    class Cache(QObject):
        thumbnail_loaded = Signal(str, int)

    class Pool:
        def set_user_active(self, _active):
            pass

        def get_pool(self):
            return QThreadPool.globalInstance()

    monkeypatch.setattr(app_module, "CONFIG_PATH", str(tmp_path / "config"))
    monkeypatch.setattr(app_module, "HISTORY_PATH", str(tmp_path / "history"))
    monkeypatch.setattr(app_module, "BOOKMARKS_PATH", str(tmp_path / "bookmarks"))
    monkeypatch.setattr(widgets, "BOOKMARKS_PATH", str(tmp_path / "bookmarks"))
    monkeypatch.setattr(widgets, "TAG_INFO_DB_PATH", str(tmp_path / "tag-info"))
    monkeypatch.setattr(widgets, "APP_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(widgets, "DIRECTORY_TAG_INFO", str(tmp_path / "legacy"))
    monkeypatch.setattr(widgets, "list_baloo_tags", lambda: ["Face/Ada"])
    monkeypatch.setattr(geomapwidget, "_init_webengine", lambda: False)
    monkeypatch.setattr(filesystemwatcher, "HAVE_WATCHDOG", False)
    monkeypatch.setattr(metadatamanager, "set_app_modified_callback", lambda _: None)
    monkeypatch.setattr(MainWindow, "handle_initial_args", lambda self, args: None)
    monkeypatch.setattr(MainWindow, "process_term", lambda self, term: None)
    monkeypatch.setattr(MainWindow, "save_config", lambda self: None)
    windows = []

    def create(args, config=None):
        (tmp_path / "config").write_text(json.dumps(config or {}))
        window = MainWindow(Cache(), args, Pool(), None)
        windows.append(window)
        return window

    yield create
    for window in windows:
        window.deleteLater()
    qapp.processEvents()


@pytest.fixture
def lazy_window(sidebar_window_factory, tmp_path):
    image = tmp_path / "image.jpg"
    image.touch()
    return sidebar_window_factory([str(image)])


@pytest.mark.parametrize("launch", ["file", "history_file", "directory", "history_search"])
@pytest.mark.parametrize("view_mode", [1, 3, 6])
def test_startup_defaults_only_for_direct_viewer(
        sidebar_window_factory, tmp_path, launch, view_mode):
    image = tmp_path / "image.jpg"
    image.touch()
    config = {
        "sort_order": 3,
        "view_mode": view_mode,
        "active_dock_tab": 1,
        "active_metadata_tab": 0,
        "active_browse_tab": 1,
    }
    if launch == "file":
        args = [image.as_uri()]
    elif launch == "history_file":
        args = []
        config["history"] = [f"file:/{image}"]
    elif launch == "directory":
        args = [str(tmp_path)]
    else:
        args = []
        config["history"] = ["search:/example"]

    window = sidebar_window_factory(args, config)
    direct_viewer = launch in ("file", "history_file")
    assert window.sort_combo.currentData() == (
        "name_asc" if direct_viewer else "date_desc")
    assert window.view_mode_combo.currentIndex() == (0 if direct_viewer else view_mode)
    assert window.sidebar_tabs.currentWidget() is (
        window.metadata_tabs if direct_viewer else window.browse_tabs)
    assert window.metadata_tabs.currentWidget() is (
        window.info_widget if direct_viewer else window.tag_edit_widget)
    assert window._sidebar_content == {}


def test_sidebar_constructs_only_opened_tabs(lazy_window, qapp):
    window = lazy_window
    assert not window.isVisible()
    assert window._sidebar_content == {}
    assert window.get_available_tags() == ["Face/Ada"]
    assert window._sidebar_content == {}

    window.show()
    qapp.processEvents()
    assert window._sidebar_content == {}

    window.open_sidebar_tab(window.info_widget)
    qapp.processEvents()
    assert set(window._sidebar_content) == {window.info_widget}
    assert window.rating_widget is not None

    window.open_sidebar_tab(window.filter_widget)
    qapp.processEvents()
    assert set(window._sidebar_content) == {window.info_widget, window.filter_widget}
    assert window.tags_list.rowCount() == 0

    window.open_sidebar_tab(window.bookmarks_tab)
    qapp.processEvents()
    assert window.bookmarks_tab in window._sidebar_content
    assert window.history_tab not in window._sidebar_content

    window.open_sidebar_tab(window.tag_edit_widget)
    qapp.processEvents()
    editor = window._sidebar_content[window.tag_edit_widget]
    assert window.get_available_tags() == ["Face/Ada"]
    window.main_dock.hide()
    window.metadata_tabs.setCurrentWidget(window.info_widget)
    window.metadata_tabs.setCurrentWidget(window.tag_edit_widget)
    assert window._sidebar_content[window.tag_edit_widget] is editor

    window.open_sidebar_tab(window.maps_tab)
    qapp.processEvents()
    map_widget = window._sidebar_content[window.maps_tab]
    assert map_widget.is_active()
    window.main_dock.hide()
    qapp.processEvents()
    assert not map_widget.is_active()


def test_restored_sidebar_selection_waits_until_dock_opens(lazy_window, qapp):
    window = lazy_window
    window._restore_sidebar_tabs({
        "active_dock_tab": 1, "active_metadata_tab": 1, "active_browse_tab": 2})
    assert window._sidebar_content == {}

    window.show()
    qapp.processEvents()
    window.main_dock.show()
    qapp.processEvents()
    assert set(window._sidebar_content) == {window.history_tab}


def test_direct_viewer_scans_without_creating_sidebar_tabs(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(app_module, "CONFIG_PATH", str(tmp_path / "config"))
    monkeypatch.setattr(app_module, "HISTORY_PATH", str(tmp_path / "history"))
    monkeypatch.setattr(app_module, "BOOKMARKS_PATH", str(tmp_path / "bookmarks"))
    monkeypatch.setattr(imagescanner, "APP_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(imagescanner, "CACHE_PATH", str(tmp_path / "cache"))
    monkeypatch.setattr(filesystemwatcher, "HAVE_WATCHDOG", False)
    monkeypatch.setattr(metadatamanager, "set_app_modified_callback", lambda _: None)
    monkeypatch.setattr(MainWindow, "save_config", lambda self: None)
    monkeypatch.setattr(app_module.ImageViewer, "inhibit_screensaver", lambda self: None)
    monkeypatch.setattr(app_module.ImageViewer, "uninhibit_screensaver", lambda self: None)
    (tmp_path / "config").write_text(json.dumps({
        "sort_order": 3, "view_mode": 6, "active_dock_tab": 1,
        "active_metadata_tab": 0, "active_browse_tab": 1,
    }))
    image = tmp_path / "B.png"
    pixels = QImage(16, 16, QImage.Format_RGB32)
    pixels.fill(Qt.red)
    assert pixels.save(str(image))
    second_image = tmp_path / "a.png"
    assert pixels.save(str(second_image))

    cache = imagescanner.ThumbnailCache()
    pool = imagescanner.ThreadPoolManager()
    window = None
    try:
        window = MainWindow(cache, [str(image)], pool, None)
        deadline = time.monotonic() + 10
        while window._is_loading and time.monotonic() < deadline:
            QTest.qWait(20)
        assert not window._is_loading
        QTest.qWait(200)
        assert window._sidebar_content == {}
        assert window.view_mode_combo.currentData() == "flat"
        assert not window.proxy_model.group_by_rating
        assert window.active_viewer.controller.get_current_path() == str(image)
        assert not window.active_viewer.controller.pixmap_original.isNull()
        assert window.active_viewer.controller.image_list == [
            str(second_image), str(image)]

        window.show()
        window.open_sidebar_tab(window.filter_widget)
        window.filter_name_input.setText("a.png")
        QTest.qWait(400)
        assert window.get_visible_image_paths() == [str(second_image)]
    finally:
        if window is not None:
            for viewer in window.viewers:
                viewer.controller.preloader.stop()
                viewer.deleteLater()
            window.perform_shutdown()
            window.deleteLater()
        else:
            cache.lmdb_close()
        qapp.processEvents()
