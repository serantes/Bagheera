"""Window placement through the KDE KWin scripting D-Bus interface."""

import json
import os
import tempfile
import uuid
from typing import List

from PySide6.QtCore import QEventLoop, QObject, QTimer, Signal
from PySide6.QtDBus import (
    QDBusConnection, QDBusInterface, QDBusMessage, QDBusVirtualObject
)


class _LayoutGeometryBridge(QDBusVirtualObject):
    """Receives KWin window geometry reports over the session bus."""

    INTERFACE = "org.bagheera.LayoutBridge"

    geometry_received = Signal(str)

    def introspect(self, _path):
        return (
            f'<interface name="{self.INTERFACE}">'
            '<method name="ReportWindows">'
            '<arg type="s" direction="in"/>'
            '</method></interface>')

    def handleMessage(self, message, connection):
        if (message.interface() != self.INTERFACE
                or message.member() != "ReportWindows"):
            return False
        arguments = message.arguments()
        if len(arguments) != 1 or not isinstance(arguments[0], str):
            connection.send(message.createErrorReply(
                "org.bagheera.LayoutBridge.InvalidArguments",
                "Expected a JSON string containing window geometries"))
            return True
        connection.send(message.createReply())
        self.geometry_received.emit(arguments[0])
        return True


class KWinLayoutBackend:
    """Applies saved window geometries using KWin's scripting interface."""

    SERVICE = "org.kde.KWin"
    PATH = "/Scripting"
    INTERFACE = "org.kde.kwin.Scripting"
    SCRIPT_INTERFACE = "org.kde.kwin.Script"
    BRIDGE_PATH = "/LayoutBridge"

    def __init__(self):
        self._script_name = None
        self._script_path = None
        self._geometry_bridge = None
        self._bridge_service = None

    @staticmethod
    def _build_script(windows, pid):
        targets = json.dumps(windows)
        return f"""
const target = {targets};
const pid = {int(pid)};
function place(win) {{
    if (win.pid !== pid) return;
    let index = target.findIndex(t => t.role && t.role === win.windowRole);
    if (index < 0) {{
        index = target.findIndex(t => t.title === win.captionNormal);
    }}
    if (index < 0) return;
    const geometry = target.splice(index, 1)[0];
    win.frameGeometry = {{
        x: geometry.x,
        y: geometry.y,
        width: geometry.w,
        height: geometry.h
    }};
    if (target.length === 0) workspace.windowAdded.disconnect(place);
}}
workspace.windowAdded.connect(place);
workspace.windowList().forEach(place);
"""

    @staticmethod
    def _build_geometry_script(windows, pid, service):
        target_list = json.dumps(windows)
        return f"""
const target = {target_list};
const pid = {int(pid)};
const windows = [];
workspace.windowList().forEach(win => {{
    if (win.pid !== pid) return;
    let index = target.findIndex(t => t.role && t.role === win.windowRole);
    if (index < 0) {{
        index = target.findIndex(t => t.title === win.captionNormal);
    }}
    if (index < 0) return;
    const saved = target.splice(index, 1)[0];
    const geometry = win.frameGeometry;
    windows.push({{
        role: saved.role,
        x: geometry.x,
        y: geometry.y,
        w: geometry.width,
        h: geometry.height
    }});
}});
callDBus(
    "{service}", "{KWinLayoutBackend.BRIDGE_PATH}",
    "{_LayoutGeometryBridge.INTERFACE}", "ReportWindows",
    JSON.stringify(windows));
"""

    @staticmethod
    def _check_reply(reply, operation):
        if reply.type() == QDBusMessage.MessageType.ErrorMessage:
            raise RuntimeError(f"{operation}: {reply.errorMessage()}")
        return reply.arguments()

    @staticmethod
    def _remove_script_file(path):
        if path is None:
            return
        try:
            os.unlink(path)
        except FileNotFoundError:
            pass
        except OSError as error:
            raise RuntimeError(
                f"Could not remove temporary KWin script: {error}") from error

    def _script_interface(self, script_id):
        return QDBusInterface(
            self.SERVICE, f"/Scripting/Script{script_id}",
            self.SCRIPT_INTERFACE, QDBusConnection.sessionBus())

    def _unload_script(self, iface, script_name, script_path):
        self._check_reply(
            iface.call("unloadScript", script_name),
            "Could not unload the previous layout script")
        self._remove_script_file(script_path)

    def _ensure_geometry_bridge(self):
        if self._geometry_bridge:
            return

        bus = QDBusConnection.sessionBus()
        service = bus.baseService()
        if not service:
            raise RuntimeError(
                "Could not get the D-Bus connection's unique service name")

        bridge = _LayoutGeometryBridge()
        if not bus.registerVirtualObject(
                self.BRIDGE_PATH, bridge,
                QDBusConnection.VirtualObjectRegisterOption.SingleNode):
            raise RuntimeError("Could not register layout geometry callback")

        self._geometry_bridge = bridge
        self._bridge_service = service

    def capture_geometries(self, windows: List[dict], pid: int) -> dict:
        """Read frame geometries from KWin using each window's role or title."""
        if not windows:
            return {}

        roles = [window["role"] for window in windows]
        self._ensure_geometry_bridge()
        iface = QDBusInterface(
            self.SERVICE, self.PATH, self.INTERFACE,
            QDBusConnection.sessionBus())
        if not iface.isValid():
            raise RuntimeError(
                f"Cannot connect to KWin scripting: "
                f"{iface.lastError().message()}")

        if self._script_name:
            self._unload_script(iface, self._script_name, self._script_path)
            self._script_name = None
            self._script_path = None

        script_name = f"bagheera-geometry-{pid}-{uuid.uuid4().hex}"
        with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", suffix=".js",
                prefix="bagheera-geometry-", delete=False) as script_file:
            script_file.write(self._build_geometry_script(
                windows, pid, self._bridge_service))
            script_path = script_file.name

        try:
            reply = iface.call("loadScript", script_path, script_name)
            arguments = self._check_reply(
                reply, "Could not load KWin geometry script")
            script_id = int(arguments[0])
            if script_id < 0:
                raise RuntimeError("KWin rejected the geometry script")
        except (RuntimeError, IndexError, TypeError, ValueError):
            self._remove_script_file(script_path)
            raise

        event_loop = QEventLoop()
        response = []
        bridge = self._geometry_bridge
        bridge.geometry_received.connect(
            lambda payload: (response.append(payload), event_loop.quit()))
        timeout = QTimer()
        timeout.setSingleShot(True)
        timeout.timeout.connect(event_loop.quit)
        timeout.start(3000)
        try:
            script_iface = self._script_interface(script_id)
            if not script_iface.isValid():
                raise RuntimeError(
                    "Could not connect to the loaded KWin geometry script")
            script_iface.asyncCall("run")
            event_loop.exec()
            if not response:
                raise RuntimeError(
                    "Timed out waiting for KWin window geometries")
            try:
                geometries = json.loads(response[0])
            except (TypeError, ValueError) as error:
                raise RuntimeError(
                    "KWin returned invalid window geometries") from error
            if not isinstance(geometries, list):
                raise RuntimeError("KWin returned invalid window geometries")
            result = {}
            for item in geometries:
                if not isinstance(item, dict):
                    continue
                role = item.get("role")
                if not isinstance(role, str) or role not in roles:
                    continue
                if not all(key in item for key in ("x", "y", "w", "h")):
                    raise RuntimeError(
                        "KWin returned incomplete window geometry")
                result[role] = {
                    key: item[key] for key in ("x", "y", "w", "h")
                }
            return result
        finally:
            timeout.stop()
            bridge.geometry_received.disconnect()
            try:
                self._check_reply(
                    iface.call("unloadScript", script_name),
                    "Could not unload KWin geometry script")
            finally:
                self._remove_script_file(script_path)

    def apply_layout(self, windows: List[dict], pid: int) -> None:
        """Restore matching windows' frame geometries via KWin."""
        if not windows:
            return

        iface = QDBusInterface(
            self.SERVICE, self.PATH, self.INTERFACE,
            QDBusConnection.sessionBus())
        if not iface.isValid():
            raise RuntimeError(
                f"Cannot connect to KWin scripting: "
                f"{iface.lastError().message()}")

        if self._script_name:
            self._unload_script(iface, self._script_name, self._script_path)
            self._script_name = None
            self._script_path = None

        script_name = f"bagheera-layout-{pid}"
        with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", suffix=".js",
                prefix="bagheera-layout-", delete=False) as script_file:
            script_file.write(self._build_script(windows, pid))
            script_path = script_file.name

        try:
            reply = iface.call("loadScript", script_path, script_name)
            arguments = self._check_reply(
                reply, "Could not load KWin layout script")
        except RuntimeError:
            self._remove_script_file(script_path)
            raise

        try:
            script_id = int(arguments[0])
        except (IndexError, TypeError, ValueError):
            self._remove_script_file(script_path)
            raise RuntimeError("KWin returned an invalid layout script ID")
        if script_id < 0:
            self._remove_script_file(script_path)
            raise RuntimeError("KWin rejected the layout script")

        self._script_name = script_name
        self._script_path = script_path
        try:
            script_iface = self._script_interface(script_id)
            self._check_reply(
                script_iface.call("run"), "Could not run KWin layout script")
        except RuntimeError as error:
            try:
                self._check_reply(
                    iface.call("unloadScript", script_name),
                    "Could not unload the failed layout script")
            except RuntimeError as cleanup_error:
                raise RuntimeError(f"{error}; {cleanup_error}") from error
            self._script_name = None
            try:
                self._remove_script_file(script_path)
            except RuntimeError as cleanup_error:
                self._script_path = None
                raise RuntimeError(
                    f"{error}; {cleanup_error}") from error
            self._script_path = None
            raise
