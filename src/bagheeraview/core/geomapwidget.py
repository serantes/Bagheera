"""OpenStreetMap widget for viewing and editing photo locations.

This module owns the map tab UI, Leaflet page, and Qt WebEngine integration.
Coordinate parsing and online place-name lookup live in :mod:`geolocation`,
while reading and writing image GPS metadata remains in :mod:`metadatamanager`.
WebEngine is imported lazily when the map tab is activated to avoid starting
Chromium during application initialization.

When the map is clicked outside location-edit mode, the widget shows a
temporary location marker that can be copied to the selected photos. Clicking
that marker removes it without changing image metadata. Search and placeholder
navigation zoom to the one-kilometer radius only when the current view is
wider; GPS metadata updates preserve the current map view.
"""
import json
import os

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton, QInputDialog,
    QDialog, QDialogButtonBox, QListWidget, QLabel, QRadioButton
)
from PySide6.QtGui import QIcon, QDesktopServices
from PySide6.QtCore import (
    Signal, Slot, Qt, QTimer, QObject, QUrl, QFile, QIODevice, QEvent
)

from .constants import UITexts
from .geolocation import parse_coordinates, search_nominatim_async
from .metadatamanager import MetadataManager, HAVE_EXIV2


class CoordinateSearchInput(QLineEdit):
    """Line edit that consumes Enter and requests a coordinate search."""

    search_requested = Signal()

    def event(self, event):
        if (event.type() == QEvent.Type.ShortcutOverride and
                event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)):
            event.accept()
            return True
        return super().event(event)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            event.accept()
            self.search_requested.emit()
            return
        super().keyPressEvent(event)


# ---------------------------------------------------------------------------
# GeoMapWidget
# ---------------------------------------------------------------------------

# WebEngine imports are deferred until the map tab is activated to avoid
# initializing Chromium during application startup.
# Do NOT import QWebEngineView at module level.
_HAVE_WEBENGINE = None  # None = not yet checked; True/False after first check
_QWebEngineView = None
_QWebChannel = None
_QWebEngineSettings = None


def _init_webengine():
    """Lazily import WebEngine modules. Safe to call multiple times."""
    global _HAVE_WEBENGINE, _QWebEngineView, _QWebChannel, _QWebEngineSettings
    if _HAVE_WEBENGINE is not None:
        return _HAVE_WEBENGINE
    try:
        from PySide6.QtWebEngineWidgets import QWebEngineView as _WEV
        from PySide6.QtWebChannel import QWebChannel as _WC
        from PySide6.QtWebEngineCore import QWebEngineSettings as _WES
        _QWebEngineView = _WEV
        _QWebChannel = _WC
        _QWebEngineSettings = _WES
        _HAVE_WEBENGINE = True
    except Exception:
        _HAVE_WEBENGINE = False
    return _HAVE_WEBENGINE


def _webchannel_script():
    """Read Qt's WebChannel client script for inline use in the map page."""
    resource = QFile(":/qtwebchannel/qwebchannel.js")
    if not resource.open(QIODevice.OpenModeFlag.ReadOnly):
        raise RuntimeError(
            "Could not read Qt WebChannel client script: "
            f"{resource.errorString()}")
    try:
        return bytes(resource.readAll()).decode("utf-8")
    finally:
        resource.close()


# Leaflet map HTML/JS template.  All external resources are loaded from CDN.
# Communication with Python uses Qt WebChannel (qt.webChannelTransport).
_MAP_HTML = """\
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>Map</title>
<link rel="stylesheet"
      href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<style>
  html,body,#map{height:100%;margin:0;padding:0;background:#1a1a2e;}
  .leaflet-popup-content-wrapper{background:#2a2a4a;color:#e0e0ff;border:1px solid #4a4aaa;}
  .leaflet-popup-tip{background:#2a2a4a;}
  .leaflet-popup-content a{color:#88aaff;}
</style>
</head>
<body>
<div id="map"></div>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"
        onerror='document.getElementById("map").textContent=__MAP_LOAD_FAILED__'></script>
<script src="qrc:///qtwebchannel/qwebchannel.js"></script>
<script>
var map = L.map('map', {zoomControl:true, attributionControl:true})
           .setView([20,0], 2);

L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
  attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
  maxZoom: 19
}).addTo(map);

var markers = [];
var editMode = false;
var bridge = null;

// Marker icons
var blueIcon = L.icon({
  iconUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png',
  iconRetinaUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png',
  shadowUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
  iconSize:[25,41], iconAnchor:[12,41], popupAnchor:[1,-34], shadowSize:[41,41]
});

var redIcon = L.icon({
  iconUrl: 'https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-2x-red.png',
  shadowUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
  iconSize:[25,41], iconAnchor:[12,41], popupAnchor:[1,-34], shadowSize:[41,41]
});

new QWebChannel(qt.webChannelTransport, function(channel) {
  bridge = channel.objects.bridge;
});

function clearMarkers() {
  markers.forEach(function(m){ map.removeLayer(m); });
  markers = [];
}

function showMarkers(data, preserveView) {
  // data: array of {path, name, lat, lon, selected}
  clearMarkers();
  var bounds = [];
  data.forEach(function(item) {
    var icon = item.selected ? redIcon : blueIcon;
    var m = L.marker([item.lat, item.lon], {icon: icon, title: item.name});
    m.bindPopup('<b>' + item.name + '</b>');
    m.on('click', function() {
      if(bridge) bridge.markerClicked(item.path);
    });
    m.addTo(map);
    markers.push(m);
    bounds.push([item.lat, item.lon]);
  });
  if(preserveView) {
    return;
  }
  if(bounds.length === 1) {
    map.setView(bounds[0], Math.max(map.getZoom(), 13));
  } else if(bounds.length > 1) {
    map.fitBounds(bounds, {padding:[30,30], maxZoom:15});
  }
}

var searchMarker = null;
var searchCircle = null;
function clearPlaceholder(notifyBridge) {
  if(searchMarker) map.removeLayer(searchMarker);
  if(searchCircle) map.removeLayer(searchCircle);
  searchMarker = null;
  searchCircle = null;
  if(notifyBridge && bridge) bridge.placeholderCleared();
}

function showPlaceholder(lat, lon, notifyBridge) {
  clearPlaceholder(false);
  var location = [lat, lon];
  searchMarker = L.marker(location, {icon: blueIcon}).addTo(map);
  searchCircle = L.circle(location, {
    radius: 1000,
    color: '#ffcc33',
    fillColor: '#ffcc33',
    fillOpacity: 0.12,
    bubblingMouseEvents: false
  }).addTo(map);
  searchMarker.on('click', function() {
    clearPlaceholder(true);
  });
  searchCircle.on('click', function() {
    clearPlaceholder(true);
  });
  if(notifyBridge && bridge) bridge.placeholderSet(lat, lon);
  var currentBounds = map.getBounds();
  var visibleDiameter = currentBounds.getNorthEast().distanceTo(
    currentBounds.getSouthWest());
  var placeholderBounds = searchCircle.getBounds();
  var placeholderDiameter = placeholderBounds.getNorthEast().distanceTo(
    placeholderBounds.getSouthWest());
  if(visibleDiameter > placeholderDiameter) {
    map.fitBounds(placeholderBounds);
  } else {
    map.panTo(location);
  }
}

function showSearchResult(lat, lon) {
  showPlaceholder(lat, lon, false);
}

function showMapPlaceholder(lat, lon) {
  showPlaceholder(lat, lon, true);
}

function setEditMode(enabled) {
  editMode = enabled;
  map.getContainer().style.cursor = enabled ? 'crosshair' : '';
}

map.on('click', function(e) {
  if(editMode && bridge) {
    bridge.mapClicked(e.latlng.lat, e.latlng.lng);
    setEditMode(false);
  } else {
    showMapPlaceholder(e.latlng.lat, e.latlng.lng);
  }
});

map.on('contextmenu', function(e) {
  if(editMode) {
    setEditMode(false);
    if(bridge) bridge.editCancelled();
  }
});

window.addEventListener('resize', function() {
  map.invalidateSize({pan:false});
});
</script>
</body>
</html>
"""


class _MapBridge(QObject):
    """Qt/JS bridge object exposed via QWebChannel.

    Signals from JS to Python are handled here.
    """
    marker_clicked = Signal(str)   # path
    map_clicked = Signal(float, float)  # lat, lon
    edit_cancelled = Signal()
    placeholder_set = Signal(float, float)
    placeholder_cleared = Signal()

    @Slot(str)
    def markerClicked(self, path):
        self.marker_clicked.emit(path)

    @Slot(float, float)
    def mapClicked(self, lat, lon):
        self.map_clicked.emit(lat, lon)

    @Slot()
    def editCancelled(self):
        self.edit_cancelled.emit()

    @Slot(float, float)
    def placeholderSet(self, lat, lon):
        self.placeholder_set.emit(lat, lon)

    @Slot()
    def placeholderCleared(self):
        self.placeholder_cleared.emit()


class GeoMapWidget(QWidget):
    """Sidebar tab widget that displays selected photos on an OpenStreetMap.

    Features:
    - Shows geolocated photos as Leaflet markers (free OpenStreetMap tiles).
    - Clicking a marker updates thumbnail selection in the main window.
    - "Open in Google Maps" button (free, no API key required).
    - Allows setting/editing GPS coordinates for non-geolocated photos.
    - Allows temporary map locations to be copied to selected photos.
    - Lazy refresh: only updates when the tab is active.

    Signals:
        selection_requested (list[str]): Emitted when the user clicks a marker
            on the map; carries a list of file paths to select.
    """

    selection_requested = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._is_active = False
        self._current_paths = []
        self._edit_paths = []    # paths being geolocated in edit mode
        self._gps_cache = {}     # path -> (lat, lon) or None, per refresh
        self.web_view = None     # set below if WebEngine is available
        self._bridge = None
        self._channel = None
        self._map_initialized = False
        self._map_loaded = False
        self._pending_coordinates = None
        self._search_result_coordinates = None
        self._geocoding_thread = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # ---- Toolbar ----
        tb = QHBoxLayout()
        tb.setSpacing(4)

        self.btn_googlemaps = QPushButton(UITexts.MAP_OPEN_GOOGLEMAPS)
        self.btn_googlemaps.setIcon(QIcon.fromTheme("internet-web-browser"))
        self.btn_googlemaps.setToolTip(UITexts.MAP_OPEN_GOOGLEMAPS_TOOLTIP)
        self.btn_googlemaps.setEnabled(False)
        self.btn_googlemaps.clicked.connect(self._open_google_maps)
        tb.addWidget(self.btn_googlemaps)

        self.btn_edit = QPushButton(UITexts.MAP_SET_LOCATION)
        self.btn_edit.setIcon(QIcon.fromTheme("document-edit"))
        self.btn_edit.setToolTip(UITexts.MAP_SET_LOCATION_TOOLTIP)
        self.btn_edit.setEnabled(False)
        self.btn_edit.clicked.connect(self._start_editing)
        tb.addWidget(self.btn_edit)

        self.btn_copy_location = QPushButton(UITexts.MAP_COPY_LOCATION)
        self.btn_copy_location.setIcon(QIcon.fromTheme("edit-copy"))
        self.btn_copy_location.setToolTip(
            UITexts.MAP_COPY_LOCATION_TOOLTIP)
        self.btn_copy_location.setEnabled(False)
        self.btn_copy_location.clicked.connect(
            self._copy_location_to_selected)
        tb.addWidget(self.btn_copy_location)

        self.btn_clear = QPushButton(UITexts.MAP_CLEAR_LOCATION)
        self.btn_clear.setIcon(QIcon.fromTheme("edit-delete"))
        self.btn_clear.setToolTip(UITexts.MAP_CLEAR_LOCATION_TOOLTIP)
        self.btn_clear.setEnabled(False)
        self.btn_clear.clicked.connect(self._clear_gps_location)
        tb.addWidget(self.btn_clear)

        layout.addLayout(tb)

        coordinate_row = QHBoxLayout()
        self.coordinate_input = CoordinateSearchInput(self)
        self.coordinate_input.setPlaceholderText(
            UITexts.MAP_COORDINATES_PLACEHOLDER)
        self.coordinate_input.search_requested.connect(
            self._go_to_coordinates)
        coordinate_row.addWidget(self.coordinate_input, stretch=1)

        self.btn_go_to_coordinates = QPushButton(self)
        self.btn_go_to_coordinates.setIcon(
            QIcon.fromTheme("mark-location", QIcon.fromTheme("map-marker")))
        self.btn_go_to_coordinates.setToolTip(
            UITexts.MAP_GO_TO_COORDINATES_TOOLTIP)
        self.btn_go_to_coordinates.clicked.connect(self._go_to_coordinates)
        coordinate_row.addWidget(self.btn_go_to_coordinates)
        layout.addLayout(coordinate_row)

        # ---- Status label ----
        self.status_lbl = QLabel(UITexts.MAP_NO_SELECTION)
        self.status_lbl.setWordWrap(True)
        self.status_lbl.setStyleSheet("color: gray; font-style: italic; font-size: 11px;")
        layout.addWidget(self.status_lbl)

        # Keep the map area empty until the user opens this tab. QtWebEngine
        # starts Chromium during widget construction, which can crash startup
        # on some Linux systems even when the containing dock is hidden.
        self._map_layout = QVBoxLayout()
        self._map_layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(self._map_layout, stretch=1)

        # ---- Ungeolocated list ----
        self.ungeo_lbl = QLabel()
        self.ungeo_lbl.setStyleSheet("color: #aaaaaa; font-size: 11px;")
        self.ungeo_lbl.setWordWrap(True)
        self.ungeo_lbl.hide()
        layout.addWidget(self.ungeo_lbl)

    def _go_to_coordinates(self):
        """Find coordinates directly or resolve a place name with Nominatim."""
        query = self.coordinate_input.text().strip()
        coordinates = parse_coordinates(query)
        if coordinates is None:
            if not query:
                self._show_geocoding_error(UITexts.MAP_INVALID_COORDINATES)
                return
            if self._geocoding_thread is not None:
                return
            self.status_lbl.setText(UITexts.MAP_SEARCHING)
            self.status_lbl.setStyleSheet(
                "color: gray; font-style: italic;")
            self.btn_go_to_coordinates.setEnabled(False)
            self._geocoding_thread = search_nominatim_async(
                query, self._on_nominatim_search_finished)
            return

        if self.web_view is None:
            return

        self._search_result_coordinates = coordinates
        self._update_buttons(
            sum(1 for _path, _coords in self._get_geolocated_paths()),
            len(self._current_paths))
        if not self._map_loaded:
            self._pending_coordinates = coordinates
            return

        self._center_map_at(*coordinates)
        self.status_lbl.setStyleSheet(
            "color: gray; font-style: italic; font-size: 11px;")

    def _on_nominatim_search_finished(self, query, coordinates, error):
        self._geocoding_thread = None
        self.btn_go_to_coordinates.setEnabled(True)

        if error:
            self._show_geocoding_error(
                UITexts.MAP_SEARCH_ERROR.format(error))
            return
        if coordinates is None:
            self._show_geocoding_error(UITexts.MAP_SEARCH_NOT_FOUND)
            return
        if self.web_view is None:
            return

        self._search_result_coordinates = coordinates
        self._update_buttons(
            sum(1 for _path, _coords in self._get_geolocated_paths()),
            len(self._current_paths))
        self.status_lbl.setText(query)
        self.status_lbl.setStyleSheet(
            "color: gray; font-style: italic; font-size: 11px;")
        if not self._map_loaded:
            self._pending_coordinates = coordinates
            return
        self._center_map_at(*coordinates)

    def _show_geocoding_error(self, message):
        self.status_lbl.setText(message)
        self.status_lbl.setStyleSheet(
            "color: #cc4444; font-style: italic;")

    def _center_map_at(self, lat, lon):
        if self.web_view is None or not self._map_loaded:
            return
        self._pending_coordinates = None
        self.web_view.page().runJavaScript(
            f"showSearchResult({lat}, {lon});")

    def _initialize_map(self):
        """Create the WebEngine view only when the map tab is first opened."""
        if self._map_initialized:
            return
        self._map_initialized = True

        if _init_webengine():
            self.web_view = _QWebEngineView()
            self.web_view.settings().setAttribute(
                _QWebEngineSettings.WebAttribute.JavascriptEnabled, True)

            self._channel = _QWebChannel(self.web_view.page())
            self._bridge = _MapBridge(self)
            self._channel.registerObject("bridge", self._bridge)
            self.web_view.page().setWebChannel(self._channel)

            webchannel_tag = (
                '<script src="qrc:///qtwebchannel/qwebchannel.js"></script>')
            if webchannel_tag not in _MAP_HTML:
                raise RuntimeError(
                    "Map HTML is missing the Qt WebChannel script tag.")
            html = _MAP_HTML.replace(
                webchannel_tag, f"<script>{_webchannel_script()}</script>")
            html = html.replace(
                "__MAP_LOAD_FAILED__", json.dumps(UITexts.MAP_LOAD_FAILED))
            self.web_view.loadFinished.connect(self._on_map_load_finished)
            self.web_view.setHtml(html)
            self._map_layout.addWidget(self.web_view)

            self._bridge.marker_clicked.connect(self._on_marker_clicked)
            self._bridge.map_clicked.connect(self._on_map_clicked)
            self._bridge.edit_cancelled.connect(self._cancel_editing)
            self._bridge.placeholder_set.connect(
                self._on_placeholder_set)
            self._bridge.placeholder_cleared.connect(
                self._on_placeholder_cleared)
        else:
            fallback = QLabel(UITexts.MAP_WEBENGINE_MISSING)
            fallback.setAlignment(Qt.AlignCenter)
            fallback.setWordWrap(True)
            fallback.setStyleSheet("color: #cc8800; font-size: 13px; padding: 20px;")
            self._map_layout.addWidget(fallback)

    def _on_map_load_finished(self, success):
        self._map_loaded = success
        if success and self._pending_coordinates is not None:
            self._center_map_at(*self._pending_coordinates)
        if success and self._is_active:
            self._invalidate_map_size()
            self._do_refresh()

    def showEvent(self, event):
        super().showEvent(event)
        self._invalidate_map_size()

    def _invalidate_map_size(self):
        if self.web_view is not None and self._map_loaded:
            QTimer.singleShot(
                0, lambda: self.web_view.page().runJavaScript(
                    "map.invalidateSize({pan:false});"))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def is_active(self) -> bool:
        return self._is_active

    def set_active(self, active: bool):
        """Called by the main window when this tab is shown or hidden."""
        self._is_active = active
        if active:
            self.initialize_if_ready()

    def initialize_if_ready(self):
        """Initialize the map when the main window is ready and not scanning."""
        if not self._is_active:
            return

        parent = self.parentWidget()
        while parent is not None:
            if not getattr(parent, "_map_startup_ready", True):
                return
            if getattr(parent, "_is_loading", False):
                return
            parent = parent.parentWidget()

        self._initialize_map()
        self.refresh(self._current_paths)

    def refresh(self, selected_paths: list):
        """Refreshes the map with the given list of selected file paths.

        This is a no-op if the tab is not currently active.
        """
        self._current_paths = list(selected_paths)
        if not self._is_active:
            return
        self._do_refresh()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _do_refresh(self, preserve_map_view=False):
        """Actually performs the map refresh (reads GPS, updates JS markers)."""
        paths = self._current_paths
        if not paths:
            self.status_lbl.setText(UITexts.MAP_NO_SELECTION)
            self._update_buttons(geolocated_count=0, total=0)
            self.ungeo_lbl.hide()
            if self.web_view is not None and self._map_loaded:
                self.web_view.page().runJavaScript("clearMarkers();")
            return

        # Read GPS data for all selected paths (use cache for speed)
        gps_data = []
        ungeolocated = []
        for path in paths:
            if path not in self._gps_cache:
                self._gps_cache[path] = MetadataManager.read_gps(path)
            coords = self._gps_cache[path]
            if coords:
                gps_data.append({
                    "path": path,
                    "name": os.path.basename(path),
                    "lat": coords[0],
                    "lon": coords[1],
                    "selected": True,
                })
            else:
                ungeolocated.append(os.path.basename(path))

        geolocated_count = len(gps_data)
        self._update_buttons(geolocated_count, len(paths))

        if geolocated_count == 0:
            self.status_lbl.setText(UITexts.MAP_NO_GPS)
        else:
            self.status_lbl.setText(
                f"{geolocated_count}/{len(paths)} photo(s) with GPS data.")

        # Show ungeolocated names
        if ungeolocated:
            self.ungeo_lbl.setText(
                UITexts.MAP_UNGEOLOCATED.format(len(ungeolocated)) +
                " " + ", ".join(ungeolocated[:8]) +
                (" …" if len(ungeolocated) > 8 else ""))
            self.ungeo_lbl.show()
        else:
            self.ungeo_lbl.hide()

        # Update JS map
        if self.web_view is not None and self._map_loaded:
            import json as _json
            js_data = _json.dumps(gps_data)
            preserve_view = "true" if preserve_map_view else "false"
            self.web_view.page().runJavaScript(
                f"showMarkers({js_data}, {preserve_view});")

    def _update_buttons(self, geolocated_count: int, total: int):
        """Enables/disables toolbar buttons based on current selection."""
        has_geo = geolocated_count > 0
        has_selection = total > 0

        # A temporary map placeholder can also be opened in Google Maps.
        has_google_maps_source = (
            has_geo or self._search_result_coordinates is not None)
        self.btn_googlemaps.setEnabled(has_google_maps_source)
        # Edit: a map click assigns the point to every selected photo.
        self.btn_edit.setEnabled(has_selection and HAVE_EXIV2)
        has_copy_source = (
            has_geo or self._search_result_coordinates is not None)
        self.btn_copy_location.setEnabled(
            has_selection and has_copy_source and HAVE_EXIV2 and
            (total > 1 or self._search_result_coordinates is not None))
        # Clear: enabled for single geolocated photo
        self.btn_clear.setEnabled(total == 1 and geolocated_count == 1
                                  and HAVE_EXIV2)

    def _open_google_maps(self):
        """Open a photo location or temporary map placeholder in Google Maps."""
        locations = self._get_geolocated_paths()
        if self._search_result_coordinates is not None:
            locations.insert(0, (None, self._search_result_coordinates))
        if not locations:
            return

        distinct_coordinates = {tuple(coords) for _path, coords in locations}
        location_index = 0
        if len(distinct_coordinates) > 1:
            choices = []
            for path, (lat, lon) in locations:
                if path is None:
                    label = UITexts.MAP_SEARCH_COORDINATE.format(lat, lon)
                else:
                    label = (
                        f"{os.path.basename(path)} — {lat:.6f}, {lon:.6f}")
                choices.append(label)
            selected, accepted = QInputDialog.getItem(
                self, UITexts.MAP_SELECT_GOOGLE_LOCATION_TITLE,
                UITexts.MAP_SELECT_GOOGLE_LOCATION_PROMPT, choices,
                0, False)
            if not accepted:
                return
            location_index = choices.index(selected)

        lat, lon = locations[location_index][1]
        url = QUrl(f"https://maps.google.com/?q={lat},{lon}")
        QDesktopServices.openUrl(url)

    def _get_geolocated_paths(self):
        """Returns selected paths with known GPS coordinates, reading cache misses."""
        locations = []
        for path in self._current_paths:
            if path not in self._gps_cache:
                self._gps_cache[path] = MetadataManager.read_gps(path)
            coords = self._gps_cache[path]
            if coords:
                locations.append((path, coords))
        return locations

    def _choose_copy_location(self, locations, ungeolocated_count):
        """Shows source-location and target-scope choices before copying."""
        dialog = QDialog(self)
        dialog.setWindowTitle(UITexts.MAP_COPY_LOCATION_TITLE)
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel(UITexts.MAP_COPY_LOCATION_PROMPT, dialog))

        distinct_coordinates = {tuple(coords) for _path, coords in locations}
        location_list = None
        if len(distinct_coordinates) > 1:
            location_list = QListWidget(dialog)
            for path, (lat, lon) in locations:
                if path is None:
                    label = UITexts.MAP_SEARCH_COORDINATE.format(lat, lon)
                else:
                    label = (
                        f"{os.path.basename(path)} — {lat:.6f}, {lon:.6f}")
                location_list.addItem(label)
            location_list.setCurrentRow(0)
            layout.addWidget(location_list)

        all_radio = QRadioButton(
            UITexts.MAP_COPY_LOCATION_ALL.format(len(self._current_paths)),
            dialog)
        ungeolocated_radio = QRadioButton(
            UITexts.MAP_COPY_LOCATION_UNGEOLOCATED.format(
                ungeolocated_count), dialog)
        ungeolocated_radio.setEnabled(ungeolocated_count > 0)
        if ungeolocated_count:
            ungeolocated_radio.setChecked(True)
        else:
            all_radio.setChecked(True)
        layout.addWidget(all_radio)
        layout.addWidget(ungeolocated_radio)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel, parent=dialog)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None

        location_index = location_list.currentRow() if location_list else 0
        if location_index < 0:
            return None
        return locations[location_index][1], all_radio.isChecked()

    def _copy_location_to_selected(self):
        """Copies one selected GPS location to all or ungeolocated selections."""
        locations = self._get_geolocated_paths()
        if self._search_result_coordinates is not None:
            locations.insert(0, (None, self._search_result_coordinates))
        if not locations or not HAVE_EXIV2:
            return

        ungeolocated = [
            path for path in self._current_paths
            if self._gps_cache.get(path) is None
        ]
        choice = self._choose_copy_location(locations, len(ungeolocated))
        if choice is None:
            return
        coords, copy_to_all = choice
        targets = self._current_paths if copy_to_all else ungeolocated

        errors = []
        copied_count = 0
        for path in targets:
            try:
                MetadataManager.write_gps(path, *coords)
            except Exception as exc:
                errors.append((path, exc))
            else:
                self._gps_cache.pop(path, None)
                copied_count += 1

        self._do_refresh(preserve_map_view=True)
        if errors:
            path, error = errors[0]
            self.status_lbl.setText(
                UITexts.MAP_GPS_WRITE_ERROR.format(
                    f"{os.path.basename(path)}: {error}"))
            self.status_lbl.setStyleSheet(
                "color: #cc4444; font-style: italic;")
        else:
            self.status_lbl.setText(
                UITexts.MAP_COPY_LOCATION_DONE.format(copied_count))
            self.status_lbl.setStyleSheet(
                "color: gray; font-style: italic; font-size: 11px;")

    @Slot(float, float)
    def _on_placeholder_set(self, lat: float, lon: float):
        """Store a temporary map location for copying to selected photos."""
        self._search_result_coordinates = (lat, lon)
        self._update_buttons(
            sum(1 for _path, _coords in self._get_geolocated_paths()),
            len(self._current_paths))

    @Slot()
    def _on_placeholder_cleared(self):
        """Forget a temporary map location and update the copy control."""
        self._search_result_coordinates = None
        self._update_buttons(
            sum(1 for _path, _coords in self._get_geolocated_paths()),
            len(self._current_paths))

    def _start_editing(self):
        """Enters editing mode: the next map click sets the GPS location."""
        if not self._current_paths:
            return
        self._edit_paths = list(self._current_paths)
        self.status_lbl.setText(UITexts.MAP_EDITING_LOCATION)
        self.btn_edit.setEnabled(False)
        if self.web_view is not None:
            self.web_view.page().runJavaScript("setEditMode(true);")

    def _cancel_editing(self):
        """Cancels editing mode without changing any data."""
        self._edit_paths = []
        self._do_refresh(preserve_map_view=True)

    @Slot(str)
    def _on_marker_clicked(self, path: str):
        """Called from JS when the user clicks a map marker."""
        if path:
            self.selection_requested.emit([path])

    @Slot(float, float)
    def _on_map_clicked(self, lat: float, lon: float):
        """Called from JS when the user clicks the map in edit mode."""
        paths = self._edit_paths
        self._edit_paths = []
        if not paths:
            return

        errors = []
        for path in paths:
            try:
                MetadataManager.write_gps(path, lat, lon)
            except Exception as exc:
                errors.append((path, exc))
            else:
                self._gps_cache.pop(path, None)

        self._do_refresh(preserve_map_view=True)
        if errors:
            path, error = errors[0]
            self.status_lbl.setText(UITexts.MAP_GPS_WRITE_ERROR.format(
                f"{os.path.basename(path)}: {error}"))
            self.status_lbl.setStyleSheet("color: #cc4444; font-style: italic;")
        else:
            self.status_lbl.setText(
                UITexts.MAP_LOCATION_ASSIGNED.format(
                    len(paths) - len(errors)))
            self.status_lbl.setStyleSheet(
                "color: gray; font-style: italic; font-size: 11px;")

    def _clear_gps_location(self):
        """Removes GPS EXIF tags from the single selected photo."""
        if not self._current_paths:
            return
        path = self._current_paths[0]
        try:
            MetadataManager.clear_gps(path)
            self._gps_cache.pop(path, None)
            self._do_refresh(preserve_map_view=True)
        except Exception as e:
            self.status_lbl.setText(UITexts.MAP_GPS_WRITE_ERROR.format(str(e)))
