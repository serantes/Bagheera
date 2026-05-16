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
    Context manager to preserve the modification time (mtime) of a file.

    This is useful when performing operations that might inadvertently update
    the file's modification time (like modifying extended attributes), but
    where the original timestamp should be retained. Supports both file paths
    and file descriptors.

    Args:
        path_or_fd (str | int): The file path or file descriptor.

    Yields:
        None: Control is yielded back to the caller context.
    """
    mtime = None
    try:
        # Check for valid input (non-empty string or integer)
        if path_or_fd is not None and (not isinstance(path_or_fd, str) or path_or_fd):
            stat_result = os.stat(path_or_fd)
            mtime = stat_result.st_mtime
    except (OSError, ValueError, TypeError):
        pass

    yield

    if mtime is not None:
        try:
            # Re-stat to get current atime, as reading might have updated it
            stat_result = os.stat(path_or_fd)
            atime = stat_result.st_atime
            os.utime(path_or_fd, (atime, mtime))
        except (OSError, ValueError, TypeError):
            pass
