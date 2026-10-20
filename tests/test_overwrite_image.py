"""
Tests for the MainWindow image overwrite support.

These tests exercise resolve_overwrite_target and overwrite_image_file with a
dummy MainWindow that skips the real __init__ (same pattern as
test_bagheeraview_modified) and real temporary files.
"""
import os

import pytest
from unittest.mock import MagicMock

from bagheeraview.core.app import MainWindow


class DummyMainWindow(MainWindow):
    """MainWindow with every heavy attribute mocked out."""

    def __init__(self):
        self._paths_being_modified_by_app = set()
        self._mark_path_as_app_modified = MagicMock()
        self.propagate_rename = MagicMock()
        self.on_fs_file_modified = MagicMock()
        self.delete_file_by_path = MagicMock()
        self._forget_path = MagicMock()

        self.cache = MagicMock()
        self.duplicate_cache = MagicMock()
        self.proxy_model = MagicMock()
        self.thumbnail_model = MagicMock()
        self._path_to_model_index = {}
        self._group_info_cache = {}
        self.found_items_data = []
        self._known_paths = set()
        self._visible_paths_cache = {}


@pytest.fixture(autouse=True)
def _qapp():
    """Ensures a QApplication exists for every test in this module."""
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def _write_file(path, content):
    """Writes a small file with the given content."""
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def test_same_extension_renames_source_over_target(tmp_path):
    """Same-extension overwrite renames and replaces the target file."""
    source = tmp_path / "a.png"
    target = tmp_path / "b.png"
    _write_file(source, "SOURCE")
    _write_file(target, "TARGET")

    win = DummyMainWindow()
    mode = win.overwrite_image_file(str(source), str(target))

    assert mode == "renamed"
    assert not source.exists()
    with open(target, encoding="utf-8") as f:
        assert f.read() == "SOURCE"
    win._forget_path.assert_called_once_with(str(target))
    win.propagate_rename.assert_called_once_with(str(source), str(target))
    win.on_fs_file_modified.assert_not_called()


def test_cross_device_fallback_copies(tmp_path, monkeypatch):
    """If os.replace fails the file is copied overwriting the target."""
    source = tmp_path / "a.png"
    target = tmp_path / "b.png"
    _write_file(source, "SOURCE")
    _write_file(target, "TARGET")

    def _fail_replace(*args, **kwargs):
        raise OSError("EXDEV")

    monkeypatch.setattr(os, "replace", _fail_replace)
    win = DummyMainWindow()
    mode = win.overwrite_image_file(str(source), str(target))

    assert mode == "copied"
    assert source.exists()  # copy keeps the source
    with open(target, encoding="utf-8") as f:
        assert f.read() == "SOURCE"
    win.propagate_rename.assert_not_called()
    win.on_fs_file_modified.assert_called_once_with(str(target))


def test_extension_mismatch_trashes_target(tmp_path):
    """Different extensions keep the source extension and trash the target."""
    source = tmp_path / "a.png"
    target = tmp_path / "b.jpg"
    _write_file(source, "SOURCE")
    _write_file(target, "TARGET")

    win = DummyMainWindow()

    def _fake_delete(path, permanent=False):
        os.remove(path)

    win.delete_file_by_path = _fake_delete
    mode = win.overwrite_image_file(str(source), str(target))

    final = tmp_path / "b.png"
    assert mode == "renamed"
    assert not source.exists()
    assert not target.exists()  # old target trashed
    with open(final, encoding="utf-8") as f:
        assert f.read() == "SOURCE"
    win.propagate_rename.assert_called_once_with(str(source), str(final))


def test_extension_mismatch_conflicting_final_raises(tmp_path):
    """A third file occupying the resolved path aborts the operation."""
    source = tmp_path / "a.png"
    target = tmp_path / "b.jpg"
    conflict = tmp_path / "b.png"
    _write_file(source, "SOURCE")
    _write_file(target, "TARGET")
    _write_file(conflict, "CONFLICT")

    win = DummyMainWindow()
    with pytest.raises(FileExistsError):
        win.overwrite_image_file(str(source), str(target))


def test_same_path_rejected(tmp_path):
    """Source equal to target is rejected."""
    path = tmp_path / "a.png"
    _write_file(path, "X")
    win = DummyMainWindow()
    with pytest.raises(ValueError):
        win.overwrite_image_file(str(path), str(path))
