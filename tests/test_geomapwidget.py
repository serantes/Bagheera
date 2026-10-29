import pytest
from PySide6.QtCore import QEventLoop, QTimer, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QApplication, QDialog, QDockWidget, QLabel, QListWidget, QMainWindow,
    QRadioButton, QTabWidget, QWidget
)

from bagheeraview.core.app import AppShortcutController
from bagheeraview.core import widgets


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


def test_map_webengine_is_initialized_only_when_tab_is_activated(monkeypatch):
    application = QApplication.instance() or QApplication([])
    init_calls = []

    def disable_webengine():
        init_calls.append(True)
        return False

    monkeypatch.setattr(widgets, "_init_webengine", disable_webengine)
    map_widget = widgets.GeoMapWidget()

    assert init_calls == []
    assert map_widget.web_view is None

    map_widget.set_active(False)
    assert init_calls == []

    map_widget.set_active(True)
    assert init_calls == [True]
    assert map_widget._map_layout.count() == 1
    assert isinstance(map_widget._map_layout.itemAt(0).widget(), QLabel)

    map_widget.set_active(True)
    assert init_calls == [True]

    map_widget.close()
    application.processEvents()


def test_map_initialization_waits_for_startup_scan(monkeypatch):
    application = QApplication.instance() or QApplication([])
    init_calls = []

    def disable_webengine():
        init_calls.append(True)
        return False

    monkeypatch.setattr(widgets, "_init_webengine", disable_webengine)
    parent = QWidget()
    parent._map_startup_ready = False
    parent._is_loading = True
    map_widget = widgets.GeoMapWidget(parent)

    map_widget.set_active(True)
    assert init_calls == []

    parent._map_startup_ready = True
    map_widget.initialize_if_ready()
    assert init_calls == []

    parent._is_loading = False
    map_widget.initialize_if_ready()
    assert init_calls == [True]

    map_widget.close()
    parent.close()
    application.processEvents()


def test_webengine_map_keeps_working_with_native_application_shortcuts(
        app, monkeypatch):
    pytest.importorskip("PySide6.QtWebEngineWidgets")

    window = QMainWindow()
    window.viewer_shortcuts = {}
    window.dialog_shortcuts = {}
    for action in (
            "perform_shutdown", "toggle_visibility", "close_all_viewers",
            "load_more_images", "load_all_images", "save_layout",
            "load_layout_dialog", "open_current_folder",
            "delete_current_image", "hard_refresh_content", "refresh_content",
            "select_all_thumbnails", "select_none_thumbnails",
            "invert_selection_thumbnails"):
        setattr(window, action, lambda *args, **kwargs: None)
    tabs = QTabWidget()
    dock = QDockWidget(window)
    dock.setWidget(tabs)
    window.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
    map_widget = widgets.GeoMapWidget(window)
    tabs.addTab(map_widget, "Map")
    other_tab = QWidget()
    tabs.addTab(other_tab, "Other")

    leaflet_shim = """
    <script>
    const makeLayer = () => ({addTo() {return this}});
    window.L = {
      map() {
        return {
          setView() {return this},
          on() {return this},
          removeLayer() {},
          getContainer() {return {style: {}}},
          getZoom() {return 2},
          invalidateSize() {return this},
          fitBounds() {}
        };
      },
      tileLayer() {return makeLayer()},
      icon(options) {return options},
      marker() {
        return {
          bindPopup() {return this},
          on() {return this},
          addTo() {return this}
        };
      }
    };
    </script>
    """
    html = widgets._MAP_HTML.replace(
        '<link rel="stylesheet"\\n'
        '      href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>',
        '')
    html = html.replace(
        '<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"\n'
        '        onerror=\'document.getElementById("map").textContent='
        '__MAP_LOAD_FAILED__\'></script>',
        leaflet_shim)
    monkeypatch.setattr(
        widgets, "_MAP_HTML", html)

    window.resize(900, 600)
    window.show()
    dock.show()
    app.processEvents()
    map_widget.set_active(True)

    loop = QEventLoop()
    map_widget.web_view.loadFinished.connect(loop.quit)
    QTimer.singleShot(10000, loop.quit)
    loop.exec()

    assert map_widget.web_view is not None
    assert map_widget._map_loaded
    assert map_widget.web_view.width() > 0
    assert map_widget.web_view.height() > 0
    javascript = []
    map_widget.web_view.page().runJavaScript(
        "typeof map + ':' + typeof showMarkers + ':' + typeof setEditMode",
        javascript.append)
    loop = QEventLoop()
    QTimer.singleShot(1000, loop.quit)
    loop.exec()
    assert javascript == ["object:function:function"]

    path = "/tmp/geolocated-photo.jpg"
    second_path = "/tmp/second-photo.jpg"
    written_coordinates = []
    map_widget._current_paths = [path, second_path]
    map_widget._edit_paths = [path, second_path]
    map_widget.btn_edit.setEnabled(False)
    monkeypatch.setattr(widgets, "HAVE_EXIV2", True)
    monkeypatch.setattr(
        widgets.MetadataManager, "write_gps",
        lambda image_path, lat, lon:
        written_coordinates.append((image_path, lat, lon)))
    monkeypatch.setattr(
        widgets.MetadataManager, "read_gps",
        lambda _image_path: (12.5, -45.6))

    map_click_loop = QEventLoop()
    map_widget._bridge.map_clicked.connect(map_click_loop.quit)
    QTimer.singleShot(3000, map_click_loop.quit)
    map_widget.web_view.page().runJavaScript(
        "bridge.mapClicked(12.5, -45.6);")
    map_click_loop.exec()

    assert written_coordinates == [
        (path, 12.5, -45.6), (second_path, 12.5, -45.6)]
    assert map_widget._edit_paths == []
    assert map_widget.btn_edit.isEnabled()
    assert not map_widget.btn_clear.isEnabled()
    assert map_widget.btn_copy_location.isEnabled()
    assert map_widget.btn_googlemaps.isEnabled()

    map_widget._current_paths = [path]
    map_widget._edit_paths = [path]
    map_widget.btn_edit.setEnabled(False)
    map_widget._bridge.edit_cancelled.emit()
    assert map_widget._edit_paths == []
    assert map_widget.btn_edit.isEnabled()

    triggered = []
    controller = AppShortcutController(window)
    controller._shortcuts = {
        (int(Qt.Key.Key_K), Qt.KeyboardModifiers.NoModifier):
            ("test_action", False, "Test", "Test")
    }
    controller._favorite_shortcuts.clear()
    controller._actions = {"test_action": lambda: triggered.append(True)}
    controller._refresh_native_shortcuts()
    QTest.keyClick(map_widget.web_view, Qt.Key.Key_K)
    assert triggered == [True]

    tabs.setCurrentWidget(other_tab)
    map_widget.set_active(False)
    window.setFocus()
    QTest.keyClick(window, Qt.Key.Key_K)
    assert triggered == [True, True]

    loop = QEventLoop()
    QTimer.singleShot(1000, loop.quit)
    loop.exec()
    window.close()


def test_copy_location_targets_only_ungeolocated_photos(monkeypatch):
    map_widget = widgets.GeoMapWidget()
    source = "/photos/source.jpg"
    other_location = "/photos/other-location.jpg"
    ungeolocated = "/photos/ungeolocated.jpg"
    map_widget._current_paths = [source, other_location, ungeolocated]
    map_widget._gps_cache = {
        source: (10.0, 20.0),
        other_location: (30.0, 40.0),
        ungeolocated: None,
    }
    monkeypatch.setattr(widgets, "HAVE_EXIV2", True)
    monkeypatch.setattr(
        map_widget, "_choose_copy_location",
        lambda locations, count: ((30.0, 40.0), False))
    writes = []
    monkeypatch.setattr(
        widgets.MetadataManager, "write_gps",
        lambda path, lat, lon: writes.append((path, lat, lon)))
    monkeypatch.setattr(
        widgets.MetadataManager, "read_gps",
        lambda _path: None)

    map_widget._copy_location_to_selected()

    assert writes == [(ungeolocated, 30.0, 40.0)]


def test_cancel_copy_location_does_not_write(monkeypatch):
    map_widget = widgets.GeoMapWidget()
    map_widget._current_paths = ["/photos/source.jpg", "/photos/target.jpg"]
    map_widget._gps_cache = {
        "/photos/source.jpg": (10.0, 20.0),
        "/photos/target.jpg": None,
    }
    monkeypatch.setattr(widgets, "HAVE_EXIV2", True)
    monkeypatch.setattr(
        map_widget, "_choose_copy_location", lambda *_args: None)
    writes = []
    monkeypatch.setattr(
        widgets.MetadataManager, "write_gps",
        lambda *args: writes.append(args))

    map_widget._copy_location_to_selected()

    assert writes == []


def test_copy_location_dialog_returns_chosen_source_and_scope(monkeypatch):
    map_widget = widgets.GeoMapWidget()
    map_widget._current_paths = ["/photos/first.jpg", "/photos/second.jpg"]

    def accept_with_second_location_and_all_targets(dialog):
        dialog.findChild(QListWidget).setCurrentRow(1)
        dialog.findChildren(QRadioButton)[0].setChecked(True)
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(
        QDialog, "exec", accept_with_second_location_and_all_targets)

    choice = map_widget._choose_copy_location(
        [("/photos/first.jpg", (10.0, 20.0)),
         ("/photos/second.jpg", (30.0, 40.0))],
        ungeolocated_count=1)

    assert choice == ((30.0, 40.0), True)


def test_google_maps_prompts_when_selected_photos_have_distinct_locations(
        monkeypatch):
    map_widget = widgets.GeoMapWidget()
    map_widget._current_paths = ["/photos/first.jpg", "/photos/second.jpg"]
    map_widget._gps_cache = {
        "/photos/first.jpg": (10.0, 20.0),
        "/photos/second.jpg": (30.0, 40.0),
    }
    prompts = []
    monkeypatch.setattr(
        widgets.QInputDialog, "getItem",
        lambda *args: (prompts.extend(args[3]) or args[3][1], True))
    opened_urls = []
    monkeypatch.setattr(
        widgets.QDesktopServices, "openUrl",
        lambda url: opened_urls.append(url.toString()))

    map_widget._open_google_maps()

    assert prompts == [
        "first.jpg — 10.000000, 20.000000",
        "second.jpg — 30.000000, 40.000000",
    ]
    assert opened_urls == ["https://maps.google.com/?q=30.0,40.0"]


def test_cancel_google_maps_location_selection_does_not_open_url(monkeypatch):
    map_widget = widgets.GeoMapWidget()
    map_widget._current_paths = ["/photos/first.jpg", "/photos/second.jpg"]
    map_widget._gps_cache = {
        "/photos/first.jpg": (10.0, 20.0),
        "/photos/second.jpg": (30.0, 40.0),
    }
    monkeypatch.setattr(
        widgets.QInputDialog, "getItem", lambda *_args: ("", False))
    opened_urls = []
    monkeypatch.setattr(
        widgets.QDesktopServices, "openUrl",
        lambda url: opened_urls.append(url.toString()))

    map_widget._open_google_maps()

    assert opened_urls == []
