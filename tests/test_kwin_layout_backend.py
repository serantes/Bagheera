import json
import os

import pytest
from PySide6.QtDBus import QDBusMessage

from bagheeraview.core import kwin_layout_backend
from bagheeraview.core.kwin_layout_backend import KWinLayoutBackend


class _Reply:
    def __init__(self, arguments=()):
        self._arguments = list(arguments)

    def type(self):
        return QDBusMessage.MessageType.ReplyMessage

    def arguments(self):
        return self._arguments


class _Interface:
    def __init__(self):
        self.calls = []

    def isValid(self):
        return True

    def call(self, method, *arguments):
        self.calls.append((method, arguments))
        return _Reply([1] if method == "loadScript" else [])


class _ErrorReply:
    def type(self):
        return QDBusMessage.MessageType.ErrorMessage

    def errorMessage(self):
        return "KWin unavailable"


def test_kwin_script_matches_pid_and_role_and_applies_geometry():
    windows = [{
        "title": 'BagheeraView - "quoted".jpg',
        "role": "bagheera-viewer-test",
        "x": 20,
        "y": 30,
        "w": 640,
        "h": 480,
    }]

    script = KWinLayoutBackend._build_script(windows, 1234)

    assert json.dumps(windows) in script
    assert "win.pid !== pid" in script
    assert "t.role && t.role === win.windowRole" in script
    assert "if (index < 0)" in script
    assert "t.title === win.captionNormal" in script
    assert "win.frameGeometry = {" in script
    assert "width: geometry.w" in script
    assert "height: geometry.h" in script
    assert "Qt.rect" not in script
    assert "workspace.windowAdded.connect(place)" in script
    assert "const pid = 1234;" in script


def test_geometry_script_reports_frames_by_role():
    script = KWinLayoutBackend._build_geometry_script(
        [
            {"role": "bagheera-main", "title": "Bagheera"},
            {"role": "bagheera-viewer-test", "title": "photo.jpg"},
        ],
        1234,
        "org.bagheera.LayoutBridge.p1234.test",
    )

    assert "t.role === win.windowRole" in script
    assert "t.title === win.captionNormal" in script
    assert "win.frameGeometry" in script
    assert "role: saved.role" in script
    assert "x: geometry.x" in script
    assert "y: geometry.y" in script
    assert "w: geometry.width" in script
    assert "h: geometry.height" in script
    assert '"ReportWindows"' in script


def test_geometry_bridge_uses_existing_unique_bus_name(monkeypatch):
    class _Bus:
        def __init__(self):
            self.registered_objects = []

        def baseService(self):
            return ":1.123"

        def registerVirtualObject(self, path, bridge, _options):
            self.registered_objects.append((path, bridge))
            return True

        def registerService(self, _service):
            pytest.fail("The bridge should not register a second bus service")

    bus = _Bus()
    monkeypatch.setattr(
        kwin_layout_backend.QDBusConnection, "sessionBus", lambda: bus)

    backend = KWinLayoutBackend()
    backend._ensure_geometry_bridge()
    backend._ensure_geometry_bridge()

    assert backend._bridge_service == ":1.123"
    assert len(bus.registered_objects) == 1
    assert bus.registered_objects[0][0] == KWinLayoutBackend.BRIDGE_PATH


def test_apply_layout_loads_and_starts_kwin_script(
        monkeypatch, tmp_path):
    monkeypatch.setattr(kwin_layout_backend.tempfile, "tempdir", str(tmp_path))
    interface = _Interface()
    monkeypatch.setattr(
        kwin_layout_backend, "QDBusInterface",
        lambda *args: interface)

    backend = KWinLayoutBackend()
    windows = [{"title": "viewer", "x": 1, "y": 2, "w": 300, "h": 200}]
    backend.apply_layout(windows, 1234)
    first_script = backend._script_path
    with open(first_script, encoding="utf-8") as script_file:
        assert json.dumps(windows) in script_file.read()
    backend.apply_layout(windows, 1234)

    assert [call[0] for call in interface.calls] == [
        "loadScript", "run", "unloadScript", "loadScript", "run"]
    assert interface.calls[0][1][1] == "bagheera-layout-1234"
    assert not os.path.exists(first_script)
    assert os.path.exists(backend._script_path)


def test_apply_layout_surfaces_dbus_errors(monkeypatch, tmp_path):
    monkeypatch.setattr(kwin_layout_backend.tempfile, "tempdir", str(tmp_path))

    class FailingInterface(_Interface):
        def call(self, method, *arguments):
            return _ErrorReply()

    monkeypatch.setattr(
        kwin_layout_backend, "QDBusInterface",
        lambda *args: FailingInterface())

    with pytest.raises(RuntimeError, match="KWin unavailable"):
        KWinLayoutBackend().apply_layout(
            [{"title": "viewer", "x": 1, "y": 2, "w": 300, "h": 200}],
            1234)
    assert list(tmp_path.iterdir()) == []
