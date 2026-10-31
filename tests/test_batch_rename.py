from types import SimpleNamespace

import pytest
from PySide6.QtWidgets import QApplication, QInputDialog

from bagheeraview.core import app as app_module
from bagheeraview.core.constants import ITEM_TYPE_ROLE, PATH_ROLE


@pytest.fixture
def qapp():
    return QApplication.instance() or QApplication([])


def _rename_window():
    return SimpleNamespace(
        _mark_path_as_app_modified=lambda _path: None,
        propagate_rename=lambda _old, _new: None,
        status_lbl=SimpleNamespace(setText=lambda _text: None),
    )


def test_rename_images_skips_unchanged_name_and_continues(
        qapp, tmp_path, monkeypatch):
    first = tmp_path / "first.jpg"
    second = tmp_path / "second.png"
    first.write_bytes(b"first")
    second.write_bytes(b"second")
    responses = iter([("first", True), ("renamed", True)])
    monkeypatch.setattr(
        QInputDialog, "getText", lambda *_args: next(responses))

    app_module.MainWindow.rename_images(
        _rename_window(), [str(first), str(second)])

    assert first.exists()
    assert not second.exists()
    assert (tmp_path / "renamed.png").read_bytes() == b"second"


def test_cancel_stops_renaming_remaining_selected_files(
        qapp, tmp_path, monkeypatch):
    first = tmp_path / "first.jpg"
    second = tmp_path / "second.jpg"
    first.write_bytes(b"first")
    second.write_bytes(b"second")
    responses = iter([("renamed", True), ("", False)])
    monkeypatch.setattr(
        QInputDialog, "getText", lambda *_args: next(responses))

    app_module.MainWindow.rename_images(
        _rename_window(), [str(first), str(second)])

    assert (tmp_path / "renamed.jpg").read_bytes() == b"first"
    assert second.exists()


def test_rename_selected_images_deduplicates_selected_indexes(qapp):
    indexes = [
        SimpleNamespace(path="/images/a.jpg", item_type="thumbnail"),
        SimpleNamespace(path="/images/a.jpg", item_type="thumbnail"),
        SimpleNamespace(path="/images/folder", item_type="directory"),
        SimpleNamespace(path="/images/b.jpg", item_type="thumbnail"),
    ]
    window = SimpleNamespace(
        thumbnail_view=SimpleNamespace(selectedIndexes=lambda: indexes),
        proxy_model=SimpleNamespace(
            data=lambda index, role: (
                index.path if role == PATH_ROLE else index.item_type)),
    )
    window.get_selected_paths = lambda: \
        app_module.MainWindow.get_selected_paths(window)
    renamed = []
    window.rename_images = lambda paths: renamed.extend(paths)

    app_module.MainWindow.rename_selected_images(window)

    assert renamed == ["/images/a.jpg", "/images/b.jpg"]
