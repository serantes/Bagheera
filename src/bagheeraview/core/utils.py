"""
Utility Module for Bagheera.

This module contains general-purpose utility functions and context managers
used throughout the application, such as file system helpers.
"""
import os
from contextlib import contextmanager
from PySide6.QtCore import QMetaType
from PySide6.QtDBus import (
    QDBusArgument, QDBusConnection, QDBusInterface, QDBusMessage
)
from PySide6.QtCore import QProcess
from .constants import UITexts


SS_SERVICE = "org.freedesktop.ScreenSaver"
SS_PATH = "/org/freedesktop/ScreenSaver"
SS_IFACE = "org.freedesktop.ScreenSaver"


class PowerManager:
    _inhibit_counter = 0
    _inhibit_cookie = None

    @classmethod
    def inhibit(cls, application_name="Bagheera", reason="Running background tasks"):
        if cls._inhibit_counter > 0:
            cls._inhibit_counter += 1
            return

        try:
            iface = QDBusInterface(SS_SERVICE, SS_PATH, SS_IFACE,
                                   QDBusConnection.sessionBus())
            if not iface.isValid():
                print(f"{UITexts.ERROR} inhibiting: Invalid DBus interface")
                return

            reply = iface.call("Inhibit", application_name, reason)
            if reply.type() == QDBusMessage.MessageType.ReplyMessage:
                args = reply.arguments()
                if args:
                    cls._inhibit_cookie = int(args[0]) & 0xFFFFFFFF
                    cls._inhibit_counter = 1
            else:
                print(f"{UITexts.ERROR} inhibiting: {reply.errorMessage()}")
        except Exception as e:
            print(f"{UITexts.ERROR} inhibiting: {e}")

    @classmethod
    def uninhibit(cls):
        if cls._inhibit_counter > 0:
            cls._inhibit_counter -= 1

        if cls._inhibit_counter != 0 or cls._inhibit_cookie is None:
            return

        cookie = int(cls._inhibit_cookie) & 0xFFFFFFFF

        # Does not work at all, so we use dbus-send instead. Leaving this here for reference.
        # try:
        #     msg = QDBusMessage.createMethodCall(
        #         SS_SERVICE, SS_PATH, SS_IFACE, "UnInhibit"
        #     )
        #     msg.setArguments([QDBusArgument(cookie, QMetaType.Type.UInt)])
        #     reply = QDBusConnection.sessionBus().call(msg)

        #     if reply.type() != QDBusMessage.MessageType.ErrorMessage:
        #         cls._inhibit_cookie = None
        #         return
        #     print(f"{UITexts.ERROR} uninhibiting: {reply.errorName()} - {reply.errorMessage()}")
        # except Exception as e:
        #     print(f"{UITexts.ERROR} uninhibiting (QDBusArgument): {e}")

        code = QProcess.execute("dbus-send", [
            "--session", "--type=method_call",
            f"--dest={SS_SERVICE}", SS_PATH,
            f"{SS_IFACE}.UnInhibit",
            f"uint32:{cookie}",
        ])
        if code == 0:
            cls._inhibit_cookie = None
        else:
            print(f"{UITexts.ERROR} uninhibiting: dbus-send exit code {code}")


@contextmanager
def preserve_mtime(path_or_fd):
    """
    Context manager to preserve a file's access and modification times.

    This is useful when performing operations that might inadvertently update
    filesystem timestamps (such as metadata writes), but where the original
    timestamps should be retained. Supports paths and file descriptors.
    The filesystem change time (ctime) is managed by the operating system and
    cannot be restored by this context manager.

    Args:
        path_or_fd (str | int): The file path or file descriptor.

    Yields:
        None: Control is yielded back to the caller context.
    """
    if path_or_fd is None or (isinstance(path_or_fd, str) and not path_or_fd):
        raise ValueError("A file path or descriptor is required")
    stat_result = os.stat(path_or_fd)
    atime_ns = stat_result.st_atime_ns
    mtime_ns = stat_result.st_mtime_ns

    try:
        yield
    finally:
        os.utime(path_or_fd, ns=(atime_ns, mtime_ns))
