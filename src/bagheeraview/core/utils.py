"""
Utility Module for Bagheera.

This module contains general-purpose utility functions and context managers
used throughout the application, such as file system helpers.
"""
import os
from contextlib import contextmanager
from PySide6.QtDBus import QDBusConnection, QDBusMessage
from .constants import PROG_ID, UITexts


class PowerManager:
    """Manages system power inhibition (screensaver, sleep) via DBus."""
    _inhibit_counter = 0
    _inhibit_cookie = None

    @classmethod
    def inhibit(cls):
        """
        Increments the inhibition counter and sends a DBus request to inhibit
        the screensaver if it's the first request.
        """
        cls._inhibit_counter += 1
        if cls._inhibit_counter > 1:
            return

        try:
            msg = QDBusMessage.createMethodCall(
                "org.freedesktop.ScreenSaver",
                "/org/freedesktop/ScreenSaver",
                "org.freedesktop.ScreenSaver",
                "Inhibit"
            )
            msg.setArguments([PROG_ID, "Viewing images"])
            reply = QDBusConnection.sessionBus().call(msg)
            if reply.type() == QDBusMessage.ReplyMessage:
                cls._inhibit_cookie = reply.arguments()[0]
            else:
                cls._inhibit_cookie = None
        except Exception as e:
            print(f"{UITexts.ERROR} inhibiting power management: {e}")
            cls._inhibit_cookie = None

    @classmethod
    def uninhibit(cls):
        """
        Decrements the counter and releases the screensaver inhibit lock
        via DBus when the counter reaches zero.
        """
        if cls._inhibit_counter > 0:
            cls._inhibit_counter -= 1

        if cls._inhibit_counter == 0 and cls._inhibit_cookie is not None:
            try:
                msg = QDBusMessage.createMethodCall(
                    "org.freedesktop.ScreenSaver",
                    "/org/freedesktop/ScreenSaver",
                    "org.freedesktop.ScreenSaver",
                    "UnInhibit"
                )
                msg.setArguments([int(cls._inhibit_cookie)])
                QDBusConnection.sessionBus().call(msg)
                cls._inhibit_cookie = None
            except Exception as e:
                print(f"{UITexts.ERROR} uninhibiting: {e}")


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
