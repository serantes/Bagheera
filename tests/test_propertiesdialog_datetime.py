import os
from datetime import datetime

from PySide6.QtCore import QDateTime
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication, QMessageBox

from bagheeraview.core import propertiesdialog
from bagheeraview.core.constants import UITexts
from bagheeraview.core.propertiesdialog import PropertiesDialog


def _make_dialog(path, monkeypatch):
    monkeypatch.setattr(PropertiesDialog, "reload_metadata", lambda _self: None)
    dialog = PropertiesDialog(str(path))
    dialog.on_data_loaded(
        {},
        {"Exif.Photo.DateTimeOriginal": "2024:05:06 07:08:09"})
    return dialog


def _create_image(path):
    image = QImage(2, 2, QImage.Format.Format_RGB32)
    image.fill(0xFFFFFFFF)
    assert image.save(str(path))


def test_modified_date_controls_only_appear_when_exif_time_differs(
        tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    path = tmp_path / "photo.png"
    _create_image(path)

    exiv_time = datetime(2024, 5, 6, 7, 8, 9).timestamp()
    os.utime(path, (exiv_time, exiv_time))
    dialog = _make_dialog(path, monkeypatch)

    assert dialog.assign_exiv_date_button.text() == UITexts.PROPERTIES_ASSIGN_EXIV_DATE
    assert not dialog.exiv_datetime_edit.isVisible()
    assert not dialog.assign_exiv_date_button.isVisible()
    dialog.close()
    app.processEvents()

    os.utime(path, (exiv_time, exiv_time - 60))
    dialog = _make_dialog(path, monkeypatch)

    assert dialog.exiv_datetime_edit.isHidden()
    assert dialog.assign_exiv_date_button.isHidden()
    dialog.close()
    app.processEvents()

    os.utime(path, (exiv_time, exiv_time - 61))
    dialog = _make_dialog(path, monkeypatch)

    assert not dialog.exiv_datetime_edit.isHidden()
    assert not dialog.assign_exiv_date_button.isHidden()
    assert dialog.exiv_datetime_edit.dateTime().toSecsSinceEpoch() == int(exiv_time)
    dialog.close()
    app.processEvents()


def test_assign_exiv_date_sets_mtime_and_hides_controls(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    path = tmp_path / "photo.png"
    _create_image(path)

    dialog = _make_dialog(path, monkeypatch)
    original_atime_ns = 1_700_000_000_123_456_789
    os.utime(
        path,
        ns=(original_atime_ns, path.stat().st_mtime_ns - 1_000_000_000))

    assigned_timestamp = 1_710_000_000
    dialog.exiv_datetime_edit.setDateTime(
        QDateTime.fromSecsSinceEpoch(assigned_timestamp))
    mark_modified = []
    notify_index = []
    monkeypatch.setattr(
        propertiesdialog, "mark_app_modified", mark_modified.append)
    monkeypatch.setattr(
        propertiesdialog, "notify_baloo", notify_index.append)

    dialog.assign_exiv_date_button.click()

    stat_result = path.stat()
    assert stat_result.st_atime_ns == original_atime_ns
    assert stat_result.st_mtime_ns == assigned_timestamp * 1_000_000_000
    assert mark_modified == [str(path)]
    assert notify_index == [str(path)]
    assert dialog.exiv_datetime_edit.isHidden()
    assert dialog.assign_exiv_date_button.isHidden()
    dialog.close()
    app.processEvents()


def test_assign_exiv_date_reports_filesystem_errors(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    path = tmp_path / "photo.png"
    _create_image(path)
    dialog = _make_dialog(path, monkeypatch)
    critical = []
    monkeypatch.setattr(
        QMessageBox, "critical",
        lambda *args: critical.append(args))
    def fail_utime(*_args, **_kwargs):
        raise OSError("permission denied")

    monkeypatch.setattr(propertiesdialog.os, "utime", fail_utime)

    dialog.assign_exiv_date()

    assert critical
    assert "permission denied" in critical[0][-1]
    assert not dialog.exiv_datetime_edit.isHidden()
    assert not dialog.assign_exiv_date_button.isHidden()
    dialog.close()
    app.processEvents()
