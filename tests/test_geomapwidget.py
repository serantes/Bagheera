from types import SimpleNamespace

import pytest
from PySide6.QtCore import QEventLoop, QTimer, Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QApplication, QDialog, QDockWidget, QLabel, QListWidget, QMainWindow,
    QRadioButton, QTabWidget, QWidget
)

from bagheeraview.core.app import AppShortcutController
from bagheeraview.core import geolocation, geomapwidget, widgets


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


def test_map_webengine_is_initialized_only_when_tab_is_activated(monkeypatch):
    application = QApplication.instance() or QApplication([])
    init_calls = []

    def disable_webengine():
        init_calls.append(True)
        return False

    monkeypatch.setattr(geomapwidget, "_init_webengine", disable_webengine)
    map_widget = geomapwidget.GeoMapWidget()

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

    monkeypatch.setattr(geomapwidget, "_init_webengine", disable_webengine)
    parent = QWidget()
    parent._map_startup_ready = False
    parent._is_loading = True
    map_widget = geomapwidget.GeoMapWidget(parent)

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
    map_widget = geomapwidget.GeoMapWidget(window)
    tabs.addTab(map_widget, "Map")
    other_tab = QWidget()
    tabs.addTab(other_tab, "Other")

    leaflet_shim = """
    <script>
    window.fitBoundsCalls = 0;
    window.panToCalls = 0;
    window.visibleDiameter = 5000;
    const makeLayer = () => ({
      handlers: {},
      addTo() {return this},
      on(name, callback) {this.handlers[name] = callback; return this},
      fire(name, event) {
        if(this.handlers[name]) this.handlers[name](event);
        return this;
      },
      getBounds() {return []}
    });
    window.L = {
      map() {
        const instance = {
          handlers: {},
          setView() {return this},
          on(name, callback) {this.handlers[name] = callback; return this},
          fire(name, event) {
            if(this.handlers[name]) this.handlers[name](event);
            return this;
          },
          removeLayer() {},
          getContainer() {return {style: {}}},
          getZoom() {return 2},
          invalidateSize() {return this},
          fitBounds() {window.fitBoundsCalls++;},
          panTo() {window.panToCalls++; return this},
          getBounds() {
            return {
              getNorthEast() {
                return {distanceTo() {return window.visibleDiameter}};
              },
              getSouthWest() {
                return {distanceTo() {return 0}};
              }
            };
          }
        };
        return instance;
      },
      tileLayer() {return makeLayer()},
      icon(options) {return options},
      marker() {
        const marker = makeLayer();
        marker.bindPopup = function() {return this};
        return marker;
      },
      circle() {
        const circle = makeLayer();
        circle.getBounds = function() {
          return {
            getNorthEast() {return {distanceTo() {return 2000;}}},
            getSouthWest() {return {distanceTo() {return 0;}}}
          };
        };
        return circle;
      }
    };
    </script>
    """
    html = geomapwidget._MAP_HTML.replace(
        '<link rel="stylesheet"\\n'
        '      href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>',
        '')
    html = html.replace(
        '<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"\n'
        '        onerror=\'document.getElementById("map").textContent='
        '__MAP_LOAD_FAILED__\'></script>',
        leaflet_shim)
    monkeypatch.setattr(
        geomapwidget, "_MAP_HTML", html)

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
        "typeof map + ':' + typeof showMarkers + ':' + "
        "typeof showSearchResult + ':' + typeof setEditMode",
        javascript.append)
    loop = QEventLoop()
    QTimer.singleShot(1000, loop.quit)
    loop.exec()
    assert javascript == ["object:function:function:function"]

    path = "/tmp/geolocated-photo.jpg"
    second_path = "/tmp/second-photo.jpg"
    written_coordinates = []
    map_widget._current_paths = [path]
    map_widget._gps_cache[path] = None
    monkeypatch.setattr(geomapwidget, "HAVE_EXIV2", True)
    map_widget._update_buttons(geolocated_count=0, total=1)

    placeholder_loop = QEventLoop()
    map_widget._bridge.placeholder_set.connect(placeholder_loop.quit)
    QTimer.singleShot(3000, placeholder_loop.quit)
    map_widget.web_view.page().runJavaScript(
        "map.fire('click', {latlng: {lat: 12.5, lng: -45.6}});")
    placeholder_loop.exec()
    assert map_widget._search_result_coordinates == (12.5, -45.6)
    assert map_widget.btn_copy_location.isEnabled()

    cleared_loop = QEventLoop()
    map_widget._bridge.placeholder_cleared.connect(cleared_loop.quit)
    QTimer.singleShot(3000, cleared_loop.quit)
    map_widget.web_view.page().runJavaScript("searchMarker.fire('click');")
    cleared_loop.exec()
    assert map_widget._search_result_coordinates is None
    assert not map_widget.btn_copy_location.isEnabled()

    map_widget.web_view.page().runJavaScript(
        "window.visibleDiameter = 1000; showSearchResult(40, 50);")
    zoom_calls = []
    map_widget.web_view.page().runJavaScript(
        "JSON.stringify([window.fitBoundsCalls, window.panToCalls])",
        zoom_calls.append)
    loop = QEventLoop()
    QTimer.singleShot(1000, loop.quit)
    loop.exec()
    assert zoom_calls == ["[1,1]"]

    map_widget._current_paths = [path, second_path]
    map_widget._edit_paths = [path, second_path]
    map_widget.btn_edit.setEnabled(False)
    monkeypatch.setattr(
        geomapwidget.MetadataManager, "write_gps",
        lambda image_path, lat, lon:
        written_coordinates.append((image_path, lat, lon)))
    monkeypatch.setattr(
        geomapwidget.MetadataManager, "read_gps",
        lambda _image_path: (12.5, -45.6))

    map_click_loop = QEventLoop()
    map_widget._bridge.map_clicked.connect(map_click_loop.quit)
    QTimer.singleShot(3000, map_click_loop.quit)
    map_widget.web_view.page().runJavaScript(
        "bridge.mapClicked(12.5, -45.6);")
    map_click_loop.exec()
    preserved_zoom_calls = []
    map_widget.web_view.page().runJavaScript(
        "JSON.stringify([window.fitBoundsCalls, window.panToCalls])",
        preserved_zoom_calls.append)
    loop = QEventLoop()
    QTimer.singleShot(1000, loop.quit)
    loop.exec()
    assert preserved_zoom_calls == ["[1,1]"]

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
    map_widget = geomapwidget.GeoMapWidget()
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
        geomapwidget.MetadataManager, "write_gps",
        lambda path, lat, lon: writes.append((path, lat, lon)))
    monkeypatch.setattr(
        geomapwidget.MetadataManager, "read_gps",
        lambda _path: None)
    monkeypatch.setattr(
        geomapwidget.MetadataManager, "read_gps",
        lambda _path: None)

    map_widget._copy_location_to_selected()

    assert writes == [(ungeolocated, 30.0, 40.0)]


def test_searched_coordinate_is_first_copy_source_without_photo(monkeypatch):
    map_widget = geomapwidget.GeoMapWidget()
    map_widget._current_paths = ["/photos/source.jpg", "/photos/target.jpg"]
    map_widget._gps_cache = {
        "/photos/source.jpg": (10.0, 20.0),
        "/photos/target.jpg": None,
    }
    map_widget._search_result_coordinates = (30.0, 40.0)
    monkeypatch.setattr(widgets, "HAVE_EXIV2", True)
    copy_options = []

    def choose_searched_location(locations, _count):
        copy_options.extend(locations)
        return locations[0][1], False

    monkeypatch.setattr(
        map_widget, "_choose_copy_location", choose_searched_location)
    writes = []
    monkeypatch.setattr(
        geomapwidget.MetadataManager, "write_gps",
        lambda path, lat, lon: writes.append((path, lat, lon)))

    map_widget._copy_location_to_selected()

    assert copy_options == [
        (None, (30.0, 40.0)),
        ("/photos/source.jpg", (10.0, 20.0)),
    ]
    assert writes == [("/photos/target.jpg", 30.0, 40.0)]


def test_map_placeholder_enables_copy_for_single_selected_photo(monkeypatch):
    map_widget = geomapwidget.GeoMapWidget()
    map_widget._current_paths = ["/photos/only.jpg"]
    map_widget._gps_cache = {"/photos/only.jpg": None}
    monkeypatch.setattr(geomapwidget, "HAVE_EXIV2", True)

    map_widget._update_buttons(geolocated_count=0, total=1)
    assert not map_widget.btn_copy_location.isEnabled()

    map_widget._on_placeholder_set(12.5, -45.6)
    assert map_widget._search_result_coordinates == (12.5, -45.6)
    assert map_widget.btn_copy_location.isEnabled()

    map_widget._on_placeholder_cleared()
    assert map_widget._search_result_coordinates is None
    assert not map_widget.btn_copy_location.isEnabled()


def test_map_placeholder_enables_google_maps_without_selected_photos(app):
    map_widget = geomapwidget.GeoMapWidget()

    map_widget._update_buttons(geolocated_count=0, total=0)
    assert not map_widget.btn_googlemaps.isEnabled()

    map_widget._on_placeholder_set(12.5, -45.6)

    assert map_widget.btn_googlemaps.isEnabled()


def test_map_placeholder_can_be_copied_to_single_selected_photo(monkeypatch):
    map_widget = geomapwidget.GeoMapWidget()
    photo_path = "/photos/only.jpg"
    map_widget._current_paths = [photo_path]
    map_widget._gps_cache = {photo_path: None}
    map_widget._search_result_coordinates = (12.5, -45.6)
    monkeypatch.setattr(geomapwidget, "HAVE_EXIV2", True)
    writes = []
    monkeypatch.setattr(
        geomapwidget.MetadataManager, "write_gps",
        lambda path, lat, lon: writes.append((path, lat, lon)))
    monkeypatch.setattr(
        geomapwidget.MetadataManager, "read_gps",
        lambda _path: (12.5, -45.6))
    monkeypatch.setattr(
        map_widget, "_choose_copy_location",
        lambda locations, count: (
            locations[0][1], False) if count == 1 else None)

    map_widget._copy_location_to_selected()

    assert writes == [(photo_path, 12.5, -45.6)]


def test_cancel_copy_location_does_not_write(monkeypatch):
    map_widget = geomapwidget.GeoMapWidget()
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
        geomapwidget.MetadataManager, "write_gps",
        lambda *args: writes.append(args))

    map_widget._copy_location_to_selected()

    assert writes == []


def test_copy_location_dialog_returns_chosen_source_and_scope(monkeypatch):
    map_widget = geomapwidget.GeoMapWidget()
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


def test_copy_location_dialog_lists_searched_coordinate_without_photo_name(
        monkeypatch):
    map_widget = geomapwidget.GeoMapWidget()
    map_widget._current_paths = ["/photos/first.jpg", "/photos/second.jpg"]
    displayed_choices = []

    def accept_with_searched_coordinate(dialog):
        location_list = dialog.findChild(QListWidget)
        displayed_choices.extend(
            location_list.item(index).text()
            for index in range(location_list.count()))
        location_list.setCurrentRow(0)
        dialog.findChildren(QRadioButton)[0].setChecked(True)
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(QDialog, "exec", accept_with_searched_coordinate)
    choice = map_widget._choose_copy_location(
        [(None, (5.0, 6.0)), ("/photos/first.jpg", (10.0, 20.0))],
        ungeolocated_count=1)

    assert displayed_choices == [
        widgets.UITexts.MAP_SEARCH_COORDINATE.format(5.0, 6.0),
        "first.jpg — 10.000000, 20.000000",
    ]
    assert choice == ((5.0, 6.0), True)


def test_google_maps_prompts_when_selected_photos_have_distinct_locations(
        monkeypatch):
    map_widget = geomapwidget.GeoMapWidget()
    map_widget._current_paths = ["/photos/first.jpg", "/photos/second.jpg"]
    map_widget._gps_cache = {
        "/photos/first.jpg": (10.0, 20.0),
        "/photos/second.jpg": (30.0, 40.0),
    }
    prompts = []
    monkeypatch.setattr(
        geomapwidget.QInputDialog, "getItem",
        lambda *args: (prompts.extend(args[3]) or args[3][1], True))
    opened_urls = []
    monkeypatch.setattr(
        geomapwidget.QDesktopServices, "openUrl",
        lambda url: opened_urls.append(url.toString()))

    map_widget._open_google_maps()

    assert prompts == [
        "first.jpg — 10.000000, 20.000000",
        "second.jpg — 30.000000, 40.000000",
    ]
    assert opened_urls == ["https://maps.google.com/?q=30.0,40.0"]


def test_google_maps_lists_manual_placeholder_first(app, monkeypatch):
    map_widget = geomapwidget.GeoMapWidget()
    map_widget._current_paths = ["/photos/first.jpg", "/photos/second.jpg"]
    map_widget._gps_cache = {
        "/photos/first.jpg": (10.0, 20.0),
        "/photos/second.jpg": (30.0, 40.0),
    }
    map_widget._search_result_coordinates = (50.0, 60.0)
    prompts = []
    monkeypatch.setattr(
        geomapwidget.QInputDialog, "getItem",
        lambda *args: (prompts.extend(args[3]) or args[3][0], True))
    opened_urls = []
    monkeypatch.setattr(
        geomapwidget.QDesktopServices, "openUrl",
        lambda url: opened_urls.append(url.toString()))

    map_widget._open_google_maps()

    assert prompts == [
        geomapwidget.UITexts.MAP_SEARCH_COORDINATE.format(50.0, 60.0),
        "first.jpg — 10.000000, 20.000000",
        "second.jpg — 30.000000, 40.000000",
    ]
    assert opened_urls == ["https://maps.google.com/?q=50.0,60.0"]


def test_cancel_google_maps_location_selection_does_not_open_url(monkeypatch):
    map_widget = geomapwidget.GeoMapWidget()
    map_widget._current_paths = ["/photos/first.jpg", "/photos/second.jpg"]
    map_widget._gps_cache = {
        "/photos/first.jpg": (10.0, 20.0),
        "/photos/second.jpg": (30.0, 40.0),
    }
    monkeypatch.setattr(
        geomapwidget.QInputDialog, "getItem", lambda *_args: ("", False))
    opened_urls = []
    monkeypatch.setattr(
        geomapwidget.QDesktopServices, "openUrl",
        lambda url: opened_urls.append(url.toString()))

    map_widget._open_google_maps()

    assert opened_urls == []


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("38.199083, 128.466750", (38.199083, 128.466750)),
        ('38°11\'56.7"N 128°28\'00.3"E',
         (38 + 11 / 60 + 56.7 / 3600,
          128 + 28 / 60 + 0.3 / 3600)),
        ('38°11\'56.7"S 128°28\'00.3"W',
         (-(38 + 11 / 60 + 56.7 / 3600),
          -(128 + 28 / 60 + 0.3 / 3600))),
        ("849VCWC8+R9", (37.4220625, -122.0840625)),
        ("849vcwc8+r9", (37.4220625, -122.0840625)),
        ("-90, -180", (-90.0, -180.0)),
    ],
)
def test_parse_coordinates_accepts_decimal_and_dms(value, expected):
    coordinates = geolocation.parse_coordinates(value)

    assert coordinates == pytest.approx(expected)


@pytest.mark.parametrize(
    "value",
    [
        "",
        "somewhere",
        "91, 0",
        "0, -181",
        '38°60\'00"N 128°00\'00"E',
        '90°00\'01"N 128°00\'00"E',
        '38°11\'00"N 128°00\'00"Q',
        "849VCWC8+R",
        "849VCWC8+R9X234567",
        "849VCWC8+R0",
        "849VCWC+R9",
    ],
)
def test_parse_coordinates_rejects_invalid_values(value):
    assert geolocation.parse_coordinates(value) is None


def test_coordinate_button_shows_search_marker_and_falls_back_to_nominatim(
        monkeypatch):
    map_widget = geomapwidget.GeoMapWidget()
    map_widget._map_loaded = True
    scripts = []

    class Page:
        def runJavaScript(self, script):
            scripts.append(script)

    class WebView:
        def page(self):
            return Page()

    map_widget.web_view = WebView()
    assert not map_widget.btn_go_to_coordinates.text()
    assert map_widget.btn_go_to_coordinates.toolTip()

    map_widget.coordinate_input.setText('38°11\'56.7"N 128°28\'00.3"E')
    map_widget.btn_go_to_coordinates.click()

    assert scripts == [
        "showSearchResult(38.19908333333333, 128.46675);"
    ]

    monkeypatch.setattr(
        geolocation, "_nominatim_geocode",
        lambda _query: SimpleNamespace(latitude=38.2, longitude=128.4))
    map_widget.coordinate_input.setText("Seoul")
    map_widget.btn_go_to_coordinates.click()
    loop = QEventLoop()
    QTimer.singleShot(1000, loop.quit)
    loop.exec()
    assert scripts[-1] == "showSearchResult(38.2, 128.4);"
    assert map_widget._search_result_coordinates == (38.2, 128.4)

    monkeypatch.setattr(geolocation, "_nominatim_geocode", lambda _query: None)
    map_widget.coordinate_input.setText("unknown place")
    map_widget.btn_go_to_coordinates.click()
    QTimer.singleShot(1000, loop.quit)
    loop.exec()
    assert map_widget.status_lbl.text() == widgets.UITexts.MAP_SEARCH_NOT_FOUND
    assert len(scripts) == 2


def test_coordinate_button_waits_until_map_loads():
    map_widget = geomapwidget.GeoMapWidget()
    scripts = []

    class Page:
        def runJavaScript(self, script):
            scripts.append(script)

    class WebView:
        def page(self):
            return Page()

    map_widget.web_view = WebView()
    map_widget.coordinate_input.setText("38.2, 128.4")
    map_widget.btn_go_to_coordinates.click()

    assert scripts == []
    assert map_widget._pending_coordinates == (38.2, 128.4)

    map_widget._on_map_load_finished(True)

    assert scripts == [
        "showSearchResult(38.2, 128.4);"
    ]
    assert map_widget._pending_coordinates is None


def test_nominatim_search_runs_asynchronously_and_marks_result(app, monkeypatch):
    map_widget = geomapwidget.GeoMapWidget()
    map_widget._map_loaded = True
    scripts = []

    class Page:
        def runJavaScript(self, script):
            scripts.append(script)

    class WebView:
        def page(self):
            return Page()

    monkeypatch.setattr(
        geolocation, "_nominatim_geocode",
        lambda query: SimpleNamespace(latitude=48.8566, longitude=2.3522))
    map_widget.web_view = WebView()
    map_widget.coordinate_input.setText("Paris")
    map_widget.btn_go_to_coordinates.click()

    loop = QEventLoop()
    QTimer.singleShot(1000, loop.quit)
    loop.exec()

    assert scripts == ["showSearchResult(48.8566, 2.3522);"]
    assert map_widget._search_result_coordinates == (48.8566, 2.3522)
    assert map_widget.btn_go_to_coordinates.isEnabled()


def test_coordinate_input_enter_searches_without_triggering_window_shortcut(app):
    window = QWidget()
    map_widget = geomapwidget.GeoMapWidget(window)
    map_widget._map_loaded = True
    scripts = []

    class Page:
        def runJavaScript(self, script):
            scripts.append(script)

    class WebView:
        def page(self):
            return Page()

    map_widget.web_view = WebView()
    shortcut = QShortcut(QKeySequence(Qt.Key.Key_Return), window)
    shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
    shortcut_triggered = []
    shortcut.activated.connect(lambda: shortcut_triggered.append(True))

    window.show()
    map_widget.coordinate_input.setText("48.8566, 2.3522")
    map_widget.coordinate_input.setFocus()
    QTest.keyClick(map_widget.coordinate_input, Qt.Key.Key_Return)

    assert scripts == ["showSearchResult(48.8566, 2.3522);"]
    assert shortcut_triggered == []
    window.close()
