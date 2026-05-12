"""
File System Watcher Module for Bagheera Image Viewer.

This module provides functionality to monitor file system changes in real-time
using the watchdog library. It notifies the application about new, deleted, or
modified image files within watched directories, handling debouncing to ensure
stability during rapid file operations.

Classes:
    FileSystemWatcher: Coordinates file system monitoring and emits Qt signals.
"""
import os
try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
    HAVE_WATCHDOG = True
except ImportError:
    HAVE_WATCHDOG = False
from PySide6.QtCore import QObject, Signal, QTimer
from .constants import IMAGE_EXTENSIONS


class FileSystemWatcher(QObject):
    """
    Monitors file system events (created, deleted, modified) for specified directories.
    Emits signals to notify the main application thread of changes.
    """

    # Signals emitted to the rest of the application
    # ---------------------------------------------

    file_created = Signal(str)
    file_deleted = Signal(str)
    file_modified = Signal(str)
    _file_modified_from_handler = Signal(str)  # Internal signal from handler thread
    file_moved = Signal(str, str)
    monitoring_status_changed = Signal(bool)  # New: Signal for monitoring status
    directory_moved = Signal(str, str)
    directory_modified = Signal(str)  # For changes that might not be specific files

    _modified_events_queue = {}  # {path: QTimer}
    """Queue to manage debouncing of modification events."""

    def __init__(self, parent=None):
        """
        Initializes the FileSystemWatcher.

        Args:
            parent (QObject, optional): The parent object. Defaults to None.
        """
        super().__init__(parent)
        self._watched_directories = set()
        self._debounce_interval = 500  # milliseconds

        if HAVE_WATCHDOG:
            self._observer = Observer()
            self._event_handler = self._Handler(self)
            self._observer.start()
        else:
            self._observer = None  # Keep observer as None if watchdog is not available

        # Connect the internal signal to the debouncing slot
        if HAVE_WATCHDOG:
            self._file_modified_from_handler.connect(self._on_file_modified_debounced)

    def _on_file_modified_debounced(self, path):
        """
        Slot to handle modified events from the watchdog thread.

        Implements a debouncing mechanism: if multiple modification events
        arrive for the same path within the interval, previous timers are
        reset to avoid redundant UI updates or heavy disk operations.

        Args:
            path (str): The path of the modified file.
        """
        # Debounce timer for modified events to avoid multiple signals for a single save
        if path in self._modified_events_queue:
            self._modified_events_queue[path].stop()
        else:
            # Ensure timer lives in the main thread (parent is self)
            timer = QTimer(self)
            timer.setSingleShot(True)
            timer.setInterval(self._debounce_interval)
            timer.timeout.connect(lambda p=path: self._emit_modified_after_debounce(p))
            self._modified_events_queue[path] = timer
        self._modified_events_queue[path].start()

    def _emit_modified_after_debounce(self, path):
        """
        Emits the file_modified signal after the debounce period.

        Args:
            path (str): The path of the modified file.
        """
        self.file_modified.emit(path)
        if path in self._modified_events_queue:
            # Safely delete the QTimer object when done
            self._modified_events_queue[path].deleteLater()
            del self._modified_events_queue[path]

    def add_path(self, path):
        """
        Adds a directory to be monitored.

        This method ensures that redundant watches are avoided by checking if
        the path is already covered by an existing watch or if it should
        consolidate multiple sub-watches into a single parent watch.

        Args:
            path (str): The directory path to monitor.
        """
        if not HAVE_WATCHDOG or self._observer is None:
            return

        # Normalize and expand path to ensure consistent comparison
        abs_path = os.path.normpath(os.path.abspath(os.path.expanduser(path)))

        # 1. Check if path is already covered by an existing watch (exact or parent)
        for watched in self._watched_directories:
            if abs_path == watched:
                return
            parent_prefix = watched if watched.endswith(os.sep) else watched + os.sep
            if abs_path.startswith(parent_prefix):
                return  # Path is a subdirectory of an already watched directory

        old_monitoring_state = bool(self._watched_directories)

        # 2. Check if this new path covers existing watches (is a parent of them)
        # If so, consolidate them into this single parent watch
        child_prefix = abs_path if abs_path.endswith(os.sep) else abs_path + os.sep
        covered_children = [w for w in self._watched_directories
                            if w.startswith(child_prefix)]

        try:
            if covered_children:
                self._observer.unschedule_all()
                for child in covered_children:
                    self._watched_directories.remove(child)
                self._watched_directories.add(abs_path)
                for p in self._watched_directories:
                    self._observer.schedule(self._event_handler, p, recursive=True)
                print(f"Consolidated monitoring at parent: {abs_path}")
            else:
                self._observer.schedule(self._event_handler, abs_path, recursive=True)
                self._watched_directories.add(abs_path)
                print(f"Monitoring: {abs_path}")
        except Exception as e:
            print(f"Error scheduling watchdog for {abs_path}: {e}")
            return

        if not old_monitoring_state and self._watched_directories:
            self.monitoring_status_changed.emit(True)

    def remove_path(self, path):
        """
        Removes a directory from monitoring.

        Args:
            path (str): The directory path to stop monitoring.
        """
        if not HAVE_WATCHDOG or self._observer is None:
            return
        abs_path = os.path.normpath(os.path.abspath(os.path.expanduser(path)))
        if abs_path in self._watched_directories:
            old_monitoring_state = bool(self._watched_directories)
            self._observer.unschedule_all()  # Simpler to unschedule all and re-add
            self._watched_directories.remove(abs_path)
            for p in list(self._watched_directories):  # Iterate over a copy
                self._observer.schedule(self._event_handler, p, recursive=True)
            print(f"Stopped monitoring: {abs_path}")
            if HAVE_WATCHDOG and old_monitoring_state and not self._watched_directories:
                self.monitoring_status_changed.emit(False)

    def clear_paths(self):
        """Clears all monitored paths."""
        if not HAVE_WATCHDOG or not self._observer:
            return

        old_monitoring_state = bool(self._watched_directories)
        self._observer.unschedule_all()
        self._watched_directories.clear()
        print("Cleared all monitored paths.")
        if old_monitoring_state:
            self.monitoring_status_changed.emit(False)

    def stop(self):
        """
        Stops the file system observer and cleans up active timers.
        """
        if HAVE_WATCHDOG and self._observer:
            self._observer.stop()
            self._observer.join()
        for timer in self._modified_events_queue.values():
            timer.stop()

        if HAVE_WATCHDOG:
            print("FileSystemWatcher stopped.")

    if HAVE_WATCHDOG:
        class _Handler(FileSystemEventHandler):
            """
            Custom event handler for watchdog events.

            Translates low-level file system events into high-level application
            signals, filtering for supported image types.
            """
            # Signal to communicate to main thread
            file_modified_from_thread = Signal(str)

            def __init__(self, watcher):
                """
                Initializes the handler with a reference to the main watcher.
                """
                super().__init__()
                self.watcher = watcher

            def on_created(self, event):
                """Called when a file or directory is created."""
                if event.is_directory:
                    self.watcher.directory_modified.emit(event.src_path)
                    return
                if self._is_image_file(event.src_path):
                    self.watcher.file_created.emit(event.src_path)

            def on_deleted(self, event):
                """Called when a file or directory is deleted."""
                if event.is_directory:
                    self.watcher.directory_modified.emit(event.src_path)
                    return
                if self._is_image_file(event.src_path):
                    self.watcher.file_deleted.emit(event.src_path)

            def on_moved(self, event):
                """Called when a file or directory is moved or renamed."""
                if event.is_directory:
                    self.watcher.directory_moved.emit(event.src_path, event.dest_path)
                    self.watcher.directory_modified.emit(event.src_path)
                    self.watcher.directory_modified.emit(event.dest_path)
                    return
                self.watcher.file_moved.emit(event.src_path, event.dest_path)

            def on_closed(self, event):
                """Called when a file is closed."""
                if event.is_directory:
                    self.watcher.directory_modified.emit(event.src_path)
                    return
                if self._is_image_file(event.src_path):
                    self.watcher.file_modified.emit(event.src_path)

            def on_modified(self, event):
                """Called when a file or directory is modified."""
                if event.is_directory:
                    self.watcher.directory_modified.emit(event.src_path)
                    return
                if self._is_image_file(event.src_path):
                    self.watcher._file_modified_from_handler.emit(event.src_path)

            def _emit_modified(self, path):
                """
                Internal helper to emit the modified signal.

                Args:
                    path (str): The modified path.
                """
                self.watcher.file_modified.emit(path)
                if path in self.watcher._modified_events_queue:
                    del self.watcher._modified_events_queue[path]

            def _is_image_file(self, path):
                """
                Checks if a given path has a supported image extension.

                Args:
                    path (str): The file path to check.
                """
                return os.path.splitext(path)[1].lower() in IMAGE_EXTENSIONS
