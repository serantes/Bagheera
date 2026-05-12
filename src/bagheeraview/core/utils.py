"""
Utility Module for Bagheera.

This module contains general-purpose utility functions and context managers
used throughout the application, such as file system helpers.
"""
import os
from contextlib import contextmanager


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
