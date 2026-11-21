import json
import subprocess
from concurrent.futures import Future
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QRect, QTimer
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QApplication, QLabel, QWidget

from bagheeraview.core import imagecontroller, imageviewer


@pytest.fixture
def qapp():
    return QApplication.instance() or QApplication([])


def test_controller_uses_initial_image_only_for_its_original_path(qapp, monkeypatch):
    initial = QImage(32, 24, QImage.Format.Format_RGB32)
    replacement = QImage(12, 8, QImage.Format.Format_RGB32)
    future = Future()
    future.set_result(initial)
    reads = []
    monkeypatch.setattr(
        imagecontroller, "read_image",
        lambda path: reads.append(path) or replacement)
    monkeypatch.setattr(
        imagecontroller, "load_common_metadata",
        lambda _path: SimpleNamespace(tags=[], rating=0))
    monkeypatch.setattr(imagecontroller.ImageController, "load_regions", lambda _self: None)
    controller = imagecontroller.ImageController(
        ["initial.jpg", "replacement.jpg"], 0, initial_image_future=future)
    controller._trigger_preload = lambda: None
    try:
        assert controller.load_image() == (True, True)
        assert controller.pixmap_original.size().toTuple() == (32, 24)
        assert not reads
        controller.index = 1
        assert controller.load_image() == (True, True)
        assert controller.pixmap_original.size().toTuple() == (12, 8)
        assert reads == ["replacement.jpg"]
    finally:
        controller.cleanup()


def test_initial_decode_failure_is_reported(qapp):
    future = Future()
    future.set_exception(RuntimeError("decode failed"))
    controller = imagecontroller.ImageController(
        ["initial.jpg"], 0, initial_image_future=future)
    try:
        with pytest.raises(RuntimeError, match="decode failed"):
            controller.load_image()
    finally:
        controller.cleanup()


def test_initial_invalid_image_keeps_existing_load_failure(qapp):
    future = Future()
    future.set_result(QImage())
    controller = imagecontroller.ImageController(
        ["invalid.jpg"], 0, initial_image_future=future)
    try:
        assert controller.load_image() == (False, False)
        assert controller.pixmap_original.isNull()
    finally:
        controller.cleanup()


def test_initial_decode_is_not_used_after_path_changes(qapp, monkeypatch):
    future = Future()
    future.set_result(QImage(32, 24, QImage.Format.Format_RGB32))
    replacement = QImage(12, 8, QImage.Format.Format_RGB32)
    monkeypatch.setattr(imagecontroller, "read_image", lambda _path: replacement)
    monkeypatch.setattr(
        imagecontroller, "load_common_metadata",
        lambda _path: SimpleNamespace(tags=[], rating=0))
    monkeypatch.setattr(imagecontroller.ImageController, "load_regions", lambda _self: None)
    controller = imagecontroller.ImageController(
        ["initial.jpg", "replacement.jpg"], 0, initial_image_future=future)
    controller._trigger_preload = lambda: None
    try:
        controller.index = 1
        assert controller.load_image() == (True, True)
        assert controller.pixmap_original.size().toTuple() == (12, 8)
    finally:
        controller.cleanup()


def test_standalone_resolution_uses_matching_kwin_primary_screen(
        qapp, tmp_path, monkeypatch):
    class Screen:
        def __init__(self, name, geometry):
            self._name = name
            self._geometry = geometry

        def name(self):
            return self._name

        def geometry(self):
            return self._geometry

    secondary = Screen("HDMI-A-1", QRect(0, 17, 800, 1422))
    primary = Screen("DP-1", QRect(800, 0, 2560, 1440))
    config = [
        {"name": "outputs", "data": [
            {"connectorName": "HDMI-A-1"},
            {"connectorName": "DP-1"},
        ]},
        {"name": "setups", "data": [
            {"outputs": [
                {"enabled": True, "outputIndex": 0, "priority": 1,
                 "position": {"x": 0, "y": 0}},
            ]},
            {"outputs": [
                {"enabled": True, "outputIndex": 0, "priority": 2,
                 "position": {"x": 0, "y": 17}},
                {"enabled": True, "outputIndex": 1, "priority": 1,
                 "position": {"x": 800, "y": 0}},
            ]},
        ]},
    ]
    config_path = tmp_path / "kwinoutputconfig.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    monkeypatch.setattr(imageviewer, "KWINOUTPUTCONFIG_PATH", str(config_path))
    monkeypatch.setattr(QApplication, "screens", lambda: [secondary, primary])
    monkeypatch.setattr(QApplication, "primaryScreen", lambda: secondary)
    monkeypatch.setattr(QApplication, "platformName", lambda: "wayland")
    monkeypatch.setattr(
        imageviewer, "_kscreen_primary_screen",
        lambda _screens: pytest.fail("matching KWin setup should not use a subprocess"))

    viewer = SimpleNamespace(_desktop_width=0, _desktop_height=0)
    assert imageviewer.ImageViewer.get_desktop_resolution(viewer) == (2560, 1440)


def test_standalone_resolution_falls_back_when_kwin_setup_is_stale(
        qapp, tmp_path, monkeypatch):
    secondary = SimpleNamespace(
        name=lambda: "HDMI-A-1", geometry=lambda: QRect(0, 0, 800, 600))
    primary = SimpleNamespace(
        name=lambda: "DP-1", geometry=lambda: QRect(800, 0, 1920, 1080))
    config_path = tmp_path / "kwinoutputconfig.json"
    config_path.write_text('{"invalid": true}', encoding="utf-8")
    monkeypatch.setattr(imageviewer, "KWINOUTPUTCONFIG_PATH", str(config_path))
    monkeypatch.setattr(QApplication, "screens", lambda: [secondary, primary])
    monkeypatch.setattr(QApplication, "primaryScreen", lambda: secondary)
    monkeypatch.setattr(QApplication, "platformName", lambda: "wayland")
    monkeypatch.setattr(
        imageviewer, "_kscreen_primary_screen", lambda _screens: primary)

    viewer = SimpleNamespace(_desktop_width=0, _desktop_height=0)
    assert imageviewer.ImageViewer.get_desktop_resolution(viewer) == (1920, 1080)
    monkeypatch.setattr(
        imageviewer, "_kscreen_primary_screen",
        lambda _screens: pytest.fail("the resolution should be cached"))
    assert imageviewer.ImageViewer.get_desktop_resolution(viewer) == (1920, 1080)


def test_kscreen_fallback_resolves_primary_by_name(monkeypatch):
    secondary = SimpleNamespace(name=lambda: "HDMI-A-1")
    primary = SimpleNamespace(name=lambda: "DP-1")
    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(stdout=(
            "Output: 1 HDMI-A-1 id\n\tpriority 2\n"
            "Output: 2 DP-1 id\n\tpriority 1\n"))

    monkeypatch.setattr(imageviewer.subprocess, "run", run)
    assert imageviewer._kscreen_primary_screen([secondary, primary]) is primary
    assert calls[0][1]["timeout"] == 2


def test_standalone_resolution_reports_fallback_failure(qapp, monkeypatch, caplog):
    secondary = SimpleNamespace(geometry=lambda: QRect(0, 0, 800, 600))
    monkeypatch.setattr(QApplication, "screens", lambda: [secondary, object()])
    monkeypatch.setattr(QApplication, "primaryScreen", lambda: secondary)
    monkeypatch.setattr(QApplication, "platformName", lambda: "wayland")

    def invalid_config(_screens):
        raise ValueError("stale config")

    def timeout(_screens):
        raise subprocess.TimeoutExpired("kscreen-doctor", 2)

    monkeypatch.setattr(imageviewer, "_kwin_primary_screen", invalid_config)
    monkeypatch.setattr(imageviewer, "_kscreen_primary_screen", timeout)
    viewer = SimpleNamespace(_desktop_width=0, _desktop_height=0)
    assert imageviewer.ImageViewer.get_desktop_resolution(viewer) == (800, 600)
    assert "Cannot identify the KDE primary screen" in caplog.text


def test_standalone_x11_resolution_uses_qt_primary_screen(qapp, monkeypatch):
    primary = SimpleNamespace(geometry=lambda: QRect(0, 0, 2560, 1440))
    monkeypatch.setattr(QApplication, "screens", lambda: [primary])
    monkeypatch.setattr(QApplication, "primaryScreen", lambda: primary)
    monkeypatch.setattr(QApplication, "platformName", lambda: "xcb")
    monkeypatch.setattr(
        imageviewer, "_kscreen_primary_screen",
        lambda _screens: pytest.fail("X11 should use Qt's primary screen"))

    viewer = SimpleNamespace(_desktop_width=0, _desktop_height=0)
    assert imageviewer.ImageViewer.get_desktop_resolution(viewer) == (2560, 1440)


def test_initial_zoom_accounts_for_controls_before_viewer_is_shown(
        qapp, tmp_path, monkeypatch):
    image_path = tmp_path / "image.png"
    assert QPixmap(32, 24).save(str(image_path))

    viewer = QWidget()
    viewer._first_load = False
    viewer.panes_linked = False
    viewer.filmstrip_position = "bottom"
    viewer.status_bar_container = QWidget(viewer)
    viewer.status_bar_container.setFixedHeight(24)
    viewer.status_bar_container.setVisible(True)
    viewer.filmstrip = QWidget(viewer)
    viewer.filmstrip.setFixedHeight(100)
    viewer.filmstrip.setVisible(True)
    viewer.main_win = SimpleNamespace(
        filmstrip_position="bottom",
        isVisible=lambda: True,
        screen=qapp.primaryScreen,
    )
    zoom_args = []
    controller = SimpleNamespace(
        load_image=lambda: (True, True),
        get_current_path=lambda: str(image_path),
        index=0,
    )
    pane = SimpleNamespace(
        controller=controller,
        movie=None,
        canvas=SimpleNamespace(crop_rect=None),
        reset_inactivity_timer=lambda: None,
        zoom_manager=SimpleNamespace(
            calculate_initial_zoom=lambda *args: zoom_args.append(args)),
    )
    pane.canvas.crop_rect = QRect()
    viewer.active_pane = pane
    viewer.panes = [pane]
    viewer.reset_inactivity_timer = lambda: None
    viewer.update_view = lambda resize_win=False: None
    viewer.sync_filmstrip_selection = lambda _index: None
    monkeypatch.setattr(QTimer, "singleShot", lambda *_args: None)

    assert not viewer.isVisible()
    assert not viewer.status_bar_container.isVisible()
    assert not viewer.filmstrip.isVisible()
    assert not viewer.status_bar_container.isHidden()
    assert not viewer.filmstrip.isHidden()

    imageviewer.ImageViewer.load_and_fit_image_for_pane(viewer, pane)

    screen = qapp.primaryScreen().availableGeometry()
    assert zoom_args == [(
        int(screen.width() * imageviewer.ZOOM_DESKTOP_RATIO),
        int(screen.height() * imageviewer.ZOOM_DESKTOP_RATIO)
        - viewer.filmstrip.height()
        - viewer.status_bar_container.sizeHint().height(),
        False,
    )]


def test_auto_resize_includes_visible_controls_before_viewer_is_shown(
        qapp, monkeypatch):
    class ResizeRecordingWidget(QWidget):
        def resize(self, width, height):
            self.resize_dimensions = (width, height)
            super().resize(width, height)

    viewer = ResizeRecordingWidget()
    viewer.panes = []
    viewer.filmstrip_position = "bottom"
    viewer.status_bar_container = QWidget(viewer)
    viewer.status_bar_container.setFixedHeight(24)
    viewer.status_bar_container.setVisible(True)
    viewer.filmstrip = QWidget(viewer)
    viewer.filmstrip.setFixedHeight(100)
    viewer.filmstrip.setVisible(True)
    viewer.main_win = SimpleNamespace(
        filmstrip_position="bottom",
        isVisible=lambda: True,
        screen=qapp.primaryScreen,
    )
    canvas = QLabel(viewer)
    canvas.setPixmap(QPixmap(200, 100))
    controller = SimpleNamespace(
        get_display_pixmap=lambda: QPixmap(200, 100),
        pixmap_original=QPixmap(200, 100),
        get_current_path=lambda: "image.png",
    )
    pane = SimpleNamespace(controller=controller, canvas=canvas)
    viewer.active_pane = pane
    viewer.panes = [pane]
    viewer.update_title = lambda: None
    viewer.update_status_bar = lambda: None

    monkeypatch.setitem(imageviewer.APP_CONFIG, "viewer_auto_resize_window", True)

    imageviewer.ImageViewer.update_view_for_pane(viewer, pane, resize_win=True)

    assert viewer.resize_dimensions == (
        canvas.width() + imageviewer.VIEWER_FORM_MARGIN,
        canvas.height() + viewer.status_bar_container.sizeHint().height()
        + viewer.filmstrip.height() + imageviewer.VIEWER_FORM_MARGIN,
    )


def test_reused_image_can_resize_window_after_filter_replacement(
        qapp, monkeypatch):
    viewer = QWidget()
    viewer.active_pane = None
    viewer.panes = []
    viewer.isFullScreen = lambda: False
    viewer.reset_inactivity_timer = lambda: None
    updates = []
    viewer.update_view = lambda resize_win=False: updates.append(resize_win)
    viewer.sync_filmstrip_selection = lambda _index: None
    monkeypatch.setattr(QTimer, "singleShot", lambda *_args: None)

    pane = SimpleNamespace(
        controller=SimpleNamespace(
            load_image=lambda: (True, False),
            get_current_path=lambda: "replacement.png",
            index=1,
        ),
        movie=None,
        canvas=SimpleNamespace(setPixmap=lambda _pixmap: None),
        update_view=lambda resize_win=False: updates.append(resize_win),
        reset_inactivity_timer=lambda: None,
    )
    viewer.active_pane = pane
    viewer.panes = [pane]

    imageviewer.ImageViewer.load_and_fit_image_for_pane(
        viewer, pane, resize_win=True)

    assert updates == [True]
