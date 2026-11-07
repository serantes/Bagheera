import json
from types import SimpleNamespace

import pytest
import shiboken6
from PySide6.QtWidgets import QApplication, QToolBar

from bagheeraview.core import app as app_module
from bagheeraview.core.widgets import LayoutSelectionDialog, LayoutsWidget


@pytest.fixture
def qapp():
    return QApplication.instance() or QApplication([])


def _layout_file(directory, name, created_at, last_used_at):
    path = directory / f"{name}.layout"
    path.write_text(json.dumps({
        "created_at": created_at,
        "last_used_at": last_used_at,
    }), encoding="utf-8")
    return str(path)


def _displayed_names(dialog):
    return [
        dialog.table.item(row, 0).text()
        for row in range(dialog.table.rowCount())
    ]


def test_layout_selection_sorts_by_last_use_by_default(qapp, tmp_path):
    older = _layout_file(tmp_path, "Older", 10, 20)
    newer = _layout_file(tmp_path, "Newer", 30, 40)

    dialog = LayoutSelectionDialog([older, newer])

    assert _displayed_names(dialog) == ["Newer", "Older"]
    assert dialog.selected_path() == newer


def test_layout_selection_supports_name_and_creation_date_order(qapp,
                                                                tmp_path):
    zulu = _layout_file(tmp_path, "Zulu", 40, 40)
    alpha = _layout_file(tmp_path, "alpha", 10, 10)
    middle = _layout_file(tmp_path, "Middle", 30, 30)

    dialog = LayoutSelectionDialog([zulu, alpha, middle])
    dialog.sort_field_combo.setCurrentIndex(
        dialog.sort_field_combo.findData("name"))
    dialog.sort_order_combo.setCurrentIndex(
        dialog.sort_order_combo.findData("ascending"))
    assert _displayed_names(dialog) == ["alpha", "Middle", "Zulu"]

    dialog.sort_field_combo.setCurrentIndex(
        dialog.sort_field_combo.findData("created_at"))
    dialog.sort_order_combo.setCurrentIndex(
        dialog.sort_order_combo.findData("descending"))
    assert _displayed_names(dialog) == ["Zulu", "Middle", "alpha"]


def test_layout_selection_supports_ascending_last_use(qapp, tmp_path):
    older = _layout_file(tmp_path, "Older", 10, 20)
    newer = _layout_file(tmp_path, "Newer", 30, 40)

    dialog = LayoutSelectionDialog([older, newer])
    dialog.sort_order_combo.setCurrentIndex(
        dialog.sort_order_combo.findData("ascending"))

    assert _displayed_names(dialog) == ["Older", "Newer"]


def test_missing_layout_reports_error_and_returns_without_quitting(
        tmp_path, monkeypatch):
    monkeypatch.setattr(app_module, "LAYOUTS_DIR", str(tmp_path))
    errors = []
    monkeypatch.setattr(
        app_module.QMessageBox, "critical",
        lambda *args: errors.append(args))
    main = SimpleNamespace(is_xcb=True, is_wayland=False)

    app_module.MainWindow.process_term(main, "layout:/Missing")

    assert len(errors) == 1
    assert errors[0][1] == app_module.UITexts.ERROR_LOADING_LAYOUT_TITLE.format(
        app_module.PROG_NAME)
    assert errors[0][2] == app_module.UITexts.ERROR_LOADING_LAYOUT_TEXT.format(
        "Missing")
    assert not hasattr(main, "history")


@pytest.mark.parametrize(
    "platform", [SimpleNamespace(is_xcb=True, is_wayland=False),
                 SimpleNamespace(is_xcb=False, is_wayland=True)])
def test_save_layout_starts_empty_offers_existing_names_and_rejects_empty(
        tmp_path, monkeypatch, platform):
    (tmp_path / "Existing.layout").write_text("{}", encoding="utf-8")
    (tmp_path / "Another.layout").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(app_module, "LAYOUTS_DIR", str(tmp_path))
    prompts = []
    responses = iter([("", True), ("", False)])

    def get_item(_parent, _title, _label, items, current, editable):
        prompts.append((items, current, editable))
        return next(responses)

    warnings = []
    monkeypatch.setattr(app_module.QInputDialog, "getItem", get_item)
    monkeypatch.setattr(
        app_module.QMessageBox, "warning",
        lambda *args: warnings.append(args))

    app_module.MainWindow.save_layout(platform)

    assert prompts == [
        (["", "Another", "Existing"], 0, True),
        (["", "Another", "Existing"], 0, True),
    ]
    assert len(warnings) == 1
    assert warnings[0][2] == app_module.UITexts.LAYOUT_NAME_REQUIRED


class _LayoutState:
    def toBase64(self):
        return self

    def data(self):
        return b""


class _LayoutBackend:
    def __init__(self):
        self.capture_calls = []
        self.apply_calls = []

    def capture_geometries(self, windows, pid):
        self.capture_calls.append((windows, pid))
        return {
            window["role"]: {"x": 101, "y": 202, "w": 303, "h": 404}
            for window in windows
        }

    def apply_layout(self, windows, pid):
        self.apply_calls.append((windows, pid))


class _LayoutMainWindow:
    def __init__(self, is_wayland, backend):
        self.is_xcb = not is_wayland
        self.is_wayland = is_wayland
        self.kwin_layout_backend = backend
        self._layout_window_role = "bagheera-main"
        self.viewers = []
        self.cache = None
        self.search_input = SimpleNamespace(
            currentText=lambda: "",
            setEditText=lambda _text: None)
        self.status_lbl = SimpleNamespace(setText=lambda _text: None)
        self._scan_all = False

    def isVisible(self):
        return True

    def x(self):
        return 1

    def y(self):
        return 2

    def width(self):
        return 3

    def height(self):
        return 4

    def saveState(self):
        return _LayoutState()

    def get_current_selected_path(self):
        return None

    def windowTitle(self):
        return "Bagheera"

    def show(self):
        pass

    def activateWindow(self):
        pass

    def hide(self):
        pass

    def close_all_viewers(self):
        self.viewers.clear()

    def _setup_viewer_sync(self, _viewer):
        pass

    def start_scan(self, _paths, select_paths=None):
        self.scan_selection = select_paths

    def _apply_kwin_layout(self, windows):
        self.kwin_layout_backend.apply_layout(windows, 0)


def test_save_layout_uses_qt_geometry_on_x11_and_kwin_on_wayland(
        tmp_path, monkeypatch):
    monkeypatch.setattr(app_module, "LAYOUTS_DIR", str(tmp_path))
    names = iter(["x11", "wayland"])
    monkeypatch.setattr(
        app_module.QInputDialog, "getItem",
        lambda *_args: (next(names), True))

    x11_backend = _LayoutBackend()
    x11_main = _LayoutMainWindow(is_wayland=False, backend=x11_backend)
    x11_path = tmp_path / "x11.layout"
    app_module.MainWindow.save_layout(x11_main)

    x11_data = json.loads(x11_path.read_text(encoding="utf-8"))
    assert x11_data["main_window"]["geometry"] == {
        "x": 1, "y": 2, "w": 3, "h": 4}
    assert "layout_role" not in x11_data["main_window"]
    assert x11_backend.capture_calls == []

    wayland_backend = _LayoutBackend()
    wayland_main = _LayoutMainWindow(is_wayland=True, backend=wayland_backend)
    wayland_path = tmp_path / "wayland.layout"
    app_module.MainWindow.save_layout(wayland_main)

    wayland_data = json.loads(wayland_path.read_text(encoding="utf-8"))
    assert wayland_data["main_window"]["geometry"] == {
        "x": 101, "y": 202, "w": 303, "h": 404}
    assert wayland_data["main_window"]["layout_role"] == "bagheera-main"
    assert len(wayland_backend.capture_calls) == 1


@pytest.mark.parametrize("is_wayland", [False, True], ids=["x11", "wayland"])
def test_restore_layout_keeps_platform_specific_window_placement(
        tmp_path, monkeypatch, is_wayland):
    image_path = tmp_path / "photo.jpg"
    image_path.touch()
    layout_path = tmp_path / "restore.layout"
    layout_path.write_text(json.dumps({
        "main_window": {
            "visible": True,
            "geometry": {"x": 11, "y": 22, "w": 333, "h": 444},
        },
        "viewers": [{
            "path": str(image_path),
            "geometry": {"x": 55, "y": 66, "w": 777, "h": 888},
            "layout_role": "bagheera-viewer-test",
        }],
    }), encoding="utf-8")

    backend = _LayoutBackend()
    main = _LayoutMainWindow(is_wayland=is_wayland, backend=backend)
    timers = []
    monkeypatch.setattr(
        app_module.QTimer, "singleShot",
        lambda _delay, callback: timers.append(callback))

    class _Signal:
        def connect(self, _callback):
            pass

    class _Viewer:
        def __init__(self, _cache, _paths, _index, **kwargs):
            self.restore_config = kwargs["restore_config"]
            self._layout_window_role = self.restore_config.get("layout_role")
            self.destroyed = _Signal()
            self.geometry_calls = []

        def setGeometry(self, *geometry):
            self.geometry_calls.append(geometry)

        def update_title(self):
            pass

        def windowTitle(self):
            return "photo.jpg"

        def show(self):
            pass

    monkeypatch.setattr(app_module, "ImageViewer", _Viewer)
    app_module.MainWindow.restore_layout(main, str(layout_path))
    viewer = main.viewers[0]

    if is_wayland:
        assert viewer.geometry_calls == []
        assert len(timers) == 1
        timers[0]()
        assert len(backend.apply_calls) == 1
        targets, _pid = backend.apply_calls[0]
        assert [target["role"] for target in targets] == [
            "bagheera-main", "bagheera-viewer-test"]
    else:
        assert viewer.geometry_calls == [(55, 66, 777, 888)]
        assert timers == []
        assert backend.apply_calls == []


def test_layouts_save_button_opens_name_selector(qapp):
    calls = []

    class MainWindow:
        def save_layout(self, **kwargs):
            calls.append(kwargs)

    layouts_widget = LayoutsWidget(MainWindow())
    layouts_widget.save_selected_layout()

    assert calls == [{}]


def test_layouts_widget_shows_save_and_edit_actions_on_wayland(qapp):
    class MainWindow:
        def restore_layout(self, _path):
            pass

    layouts_widget = LayoutsWidget(MainWindow())
    toolbar = layouts_widget.findChild(QToolBar)

    assert toolbar is not None
    assert len(toolbar.actions()) == 6
    assert toolbar.actions()[0].text() == app_module.UITexts.LOAD


def test_deleted_qt_viewers_are_skipped_when_checking_visibility(
        qapp, monkeypatch):
    monkeypatch.setattr(app_module, "ImageViewer", app_module.QWidget)
    live_viewer = app_module.QWidget()
    live_viewer.show()
    deleted_viewer = app_module.QWidget()
    shiboken6.delete(deleted_viewer)

    assert app_module._is_visible_viewer(live_viewer)
    assert not app_module._is_visible_viewer(deleted_viewer)
