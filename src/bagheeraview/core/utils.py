"""
Utility Module for Bagheera.

This module contains general-purpose utility functions and context managers
used throughout the application, such as file system helpers.
"""
import os
from contextlib import contextmanager
from PySide6.QtDBus import QDBusConnection, QDBusInterface
from .constants import UITexts


class PowerManager:
    """Manages system power inhibition (screensaver, sleep) via DBus."""
    _inhibit_counter = 0
    _inhibit_cookie = None

    @classmethod
    def inhibit(cls, application_name="Bagheera", reason="Running background tasks"):
        """
        Requests an inhibit lock from the screensaver via DBus
        and stores the returned uint32 cookie.
        """
        if cls._inhibit_counter == 0:
            try:
                iface = QDBusInterface(
                    "org.freedesktop.ScreenSaver",
                    "/org/freedesktop/ScreenSaver",
                    "org.freedesktop.ScreenSaver",
                    QDBusConnection.sessionBus()
                )

                if iface.isValid():
                    reply = iface.call("Inhibit", application_name, reason)

                    if reply.type() == reply.MessageType.ReplyMessage:
                        arguments = reply.arguments()
                        if arguments:
                            # Capturamos la cookie devuelta y aseguramos el rango uint32
                            cls._inhibit_cookie = int(arguments[0]) & 0xFFFFFFFF
                            cls._inhibit_counter += 1
                    else:
                        print(f"{UITexts.ERROR} inhibiting: {reply.errorMessage()}")
                else:
                    print(f"{UITexts.ERROR} inhibiting: Invalid DBus interface")
            except Exception as e:
                print(f"{UITexts.ERROR} inhibiting: {e}")
        else:
            cls._inhibit_counter += 1

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
                iface = QDBusInterface(
                    "org.freedesktop.ScreenSaver",
                    "/org/freedesktop/ScreenSaver",
                    "org.freedesktop.ScreenSaver",
                    QDBusConnection.sessionBus()
                )

                if iface.isValid():
                    # Aseguramos el rango de 32 bits sin signo con la máscara
                    cookie_val = int(cls._inhibit_cookie) & 0xFFFFFFFF
                    reply = iface.call("UnInhibit", cookie_val)

                    if reply.type() == reply.MessageType.ErrorMessage:
                        print(f"{UITexts.ERROR} uninhibiting: {reply.errorMessage()}")
                    else:
                        cls._inhibit_cookie = None
                else:
                    print(f"{UITexts.ERROR} uninhibiting: Invalid DBus interface")
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
