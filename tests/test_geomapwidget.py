import pytest
from PySide6.QtCore import QEvent, QObject, QEventLoop, QTimer, Qt
from PySide6.QtWidgets import (
    QApplication, QDockWidget, QLabel, QMainWindow, QTabWidget, QWidget
)

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


def test_webengine_map_load_does_not_crash_with_application_event_filter(
        app, monkeypatch):
    pytest.importorskip("PySide6.QtWebEngineWidgets")

    class ShortcutFilter(QObject):
        def __init__(self, parent):
            super().__init__(parent)
            self.event_count = 0

        def eventFilter(self, _obj, _event):
            self.event_count += 1
            return False

    window = QMainWindow()
    tabs = QTabWidget()
    dock = QDockWidget(window)
    dock.setWidget(tabs)
    window.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
    map_widget = widgets.GeoMapWidget(window)
    tabs.addTab(map_widget, "Map")

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

    shortcut_filter = ShortcutFilter(window)
    window.shortcut_controller = shortcut_filter
    window.resize(900, 600)
    window.show()
    dock.show()
    app.processEvents()
    map_widget.set_active(True)

    app.installEventFilter(shortcut_filter)
    map_widget.set_active(map_widget.is_active())

    loop = QEventLoop()
    map_widget.web_view.loadFinished.connect(loop.quit)
    QTimer.singleShot(10000, loop.quit)
    loop.exec()

    assert map_widget.web_view is not None
    assert map_widget._map_loaded
    assert map_widget._shortcut_filter_suspended
    assert map_widget._shortcut_controller is shortcut_filter
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

    shortcut_filter.event_count = 0
    app.sendEvent(window, QEvent(QEvent.User))
    assert shortcut_filter.event_count == 0

    map_widget.set_active(False)
    app.sendEvent(window, QEvent(QEvent.User))
    assert shortcut_filter.event_count > 0

    app.removeEventFilter(shortcut_filter)
    window.close()
