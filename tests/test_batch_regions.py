from types import SimpleNamespace
from threading import Event

import pytest
from PySide6.QtCore import QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox, QWidget

from bagheeraview.core import batchregions
from bagheeraview.core.app import MainWindow
from bagheeraview.core import imagecontroller, widgets
from bagheeraview.core import xmpmanager
from bagheeraview.core.constants import ITEM_TYPE_ROLE, PATH_ROLE


@pytest.fixture
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def window(qapp):
    window = QWidget()
    rows = [("header", None), ("thumbnail", "/a.jpg"),
            ("thumbnail", "/b.jpg"), ("thumbnail", "/a.jpg")]
    window.proxy_model = SimpleNamespace(
        rowCount=lambda: len(rows), index=lambda row, _: row,
        data=lambda row, role: rows[row][0] if role == ITEM_TYPE_ROLE
        else rows[row][1] if role == PATH_ROLE else None,
    )
    window._gather_files_for_duplicates = lambda: ["/all.jpg", "/other.jpg", "/all.jpg"]
    window.face_names_history = []
    window.viewers = []
    window.batch_regions_dialog = None
    window.update_metadata_for_path = lambda *_args: None
    return window


def face(x=0.3):
    return {"x": x, "y": 0.3, "w": 0.2, "h": 0.2, "name": "", "type": "Face"}


def test_scope_count_uses_visible_thumbnails_or_duplicate_scanner(window):
    dialog = batchregions.BatchRegionsDialog(window)
    assert dialog.paths == ["/a.jpg", "/b.jpg"]
    assert dialog.count_label.text().endswith("2")
    dialog.displayed_check.setChecked(False)
    assert dialog.paths == ["/all.jpg", "/other.jpg"]
    assert dialog.count_label.text().endswith("2")
    window._gather_files_for_duplicates = lambda: None
    dialog.update_paths()
    assert dialog.paths is None
    assert dialog.count_label.text().endswith("0")


def test_batch_regions_window_is_modeless_and_reused(window):
    MainWindow.show_batch_regions(window)
    dialog = window.batch_regions_dialog

    assert dialog.isVisible()
    assert not dialog.isModal()

    MainWindow.show_batch_regions(window)
    assert window.batch_regions_dialog is dialog

    dialog.close()


def test_pets_require_tag_and_missing_whitelist_warn(window, monkeypatch):
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: warnings.append(args[-1]))
    dialog = batchregions.BatchRegionsDialog(window)
    dialog.region_combo.setCurrentIndex(1)
    dialog.start()
    assert warnings[-1] == batchregions.UITexts.BATCH_PET_TAG_REQUIRED
    window._gather_files_for_duplicates = lambda: None
    dialog.displayed_check.setChecked(False)
    dialog.start()
    assert warnings[-1] == batchregions.UITexts.DUPLICATE_WHITELIST_EMPTY


def prepare_save(dialog, monkeypatch, existing):
    writes, tags = [], []
    monkeypatch.setattr(batchregions.XmpManager, "load_regions",
                        lambda _path, strict=False: list(existing))
    monkeypatch.setattr(batchregions.XmpManager, "save_regions",
                        lambda path, regions: writes.append((path, regions)) or True)
    monkeypatch.setattr(batchregions, "load_common_metadata",
                        lambda _path: SimpleNamespace(tags=["Other"], rating=3))
    dialog.controller = SimpleNamespace(
        _current_tags=[], _current_rating=0,
        toggle_tag=lambda tag, add: tags.append((tag, add)))
    return writes, tags


def test_forced_face_is_saved_for_recognition_and_preserves_existing(
        window, monkeypatch):
    dialog = batchregions.BatchRegionsDialog(window)
    existing = [dict(face(), name="Cat", type="Pet")]
    writes, tags = prepare_save(dialog, monkeypatch, existing)
    dialog.region_type = "Face"
    dialog.forced_tag = "People/Forced"
    dialog.recognition_enabled = True
    stored = []
    identified = []
    db = SimpleNamespace(
        identify_person=lambda encoding: identified.append(encoding) or (
            "People/Existing", "face-1"),
        add_face=lambda *args, **kwargs: stored.append((args, kwargs)))
    monkeypatch.setattr(batchregions.PersonRecognitionDB, "get_instance",
                        lambda: db)
    dialog.save_detections("/a.jpg", [face()], [[2]])
    assert writes[0][1] == [existing[0], dict(face(), name="Forced")]
    assert tags == [("People/Forced", True)]
    assert identified == [[2]]
    assert len(stored) == 1
    assert stored[0][0][1] == [2]
    assert stored[0][0][2] == "People/Forced"
    assert stored[0][1]["source"] == {
        "path": "/a.jpg", "x": 0.3, "y": 0.3, "w": 0.2, "h": 0.2}


@pytest.mark.parametrize("region_type", ["Face", "Pet"])
def test_existing_region_of_scanned_type_skips_image(
        window, monkeypatch, region_type):
    dialog = batchregions.BatchRegionsDialog(window)
    existing = [dict(face(), name="Existing", type=region_type)]
    writes, tags = prepare_save(dialog, monkeypatch, existing)
    dialog.region_type = region_type
    dialog.forced_tag = "People/Forced"
    dialog.recognition_enabled = True
    monkeypatch.setattr(
        batchregions.PersonRecognitionDB, "get_instance",
        lambda: pytest.fail("skipped images must not identify faces"))

    detected = [dict(face(), type=region_type)]
    dialog.save_detections("/a.jpg", detected, [[1]] if region_type == "Face" else [])

    assert writes == []
    assert tags == []


@pytest.mark.parametrize("region_type", ["Face", "Pet"])
def test_batch_advances_without_detecting_existing_region_type(
        window, monkeypatch, region_type):
    dialog = batchregions.BatchRegionsDialog(window)
    dialog.paths = ["/a.jpg"]
    dialog.position = 0
    dialog.region_type = region_type
    monkeypatch.setattr(
        batchregions.XmpManager, "load_regions",
        lambda _path, strict=False: [dict(face(), type=region_type)])
    scheduled = []
    monkeypatch.setattr(batchregions.QTimer, "singleShot",
                        lambda _delay, callback: scheduled.append(callback))

    dialog.next_image()

    assert dialog.position == 1
    assert dialog.progress_bar.value() == 1
    assert dialog.worker is None
    assert len(scheduled) == 1


def test_forced_face_with_matching_region_name_is_not_relearned(
        window, monkeypatch):
    dialog = batchregions.BatchRegionsDialog(window)
    writes, _tags = prepare_save(dialog, monkeypatch, [])
    dialog.region_type = "Face"
    dialog.forced_tag = "People/Alice"
    dialog.recognition_enabled = True
    stored = []
    db = SimpleNamespace(
        identify_person=lambda _encoding: ("Family/Alice", "face-1"),
        add_face=lambda *args, **kwargs: stored.append((args, kwargs)))
    monkeypatch.setattr(batchregions.PersonRecognitionDB, "get_instance",
                        lambda: db)

    dialog.save_detections("/a.jpg", [face()], [[1]])

    assert writes[0][1][0]["name"] == "Alice"
    assert stored == []


def test_face_recognition_and_unknown_setting(window, monkeypatch):
    dialog = batchregions.BatchRegionsDialog(window)
    writes, tags = prepare_save(dialog, monkeypatch, [])
    dialog.region_type = "Face"
    dialog.forced_tag = ""
    dialog.recognition_enabled = True
    monkeypatch.setattr(batchregions, "APP_CONFIG",
                        {"unrecognized_person_action": "assign_tag",
                         "unrecognized_person_tag": "People/Unknown"})
    db = SimpleNamespace(identify_person=lambda encoding: (
        ("People/Alice", 0.1) if encoding == [1] else (None, None)))
    monkeypatch.setattr(batchregions.PersonRecognitionDB, "get_instance", lambda: db)
    dialog.save_detections("/a.jpg", [face(), face(0.8)], [[1], [2]])
    assert [region["name"] for region in writes[0][1]] == ["Alice", "Unknown"]
    assert set(tags) == {("People/Alice", True), ("People/Unknown", True)}


def test_save_failure_does_not_apply_tags(window, monkeypatch):
    dialog = batchregions.BatchRegionsDialog(window)
    _, tags = prepare_save(dialog, monkeypatch, [])
    monkeypatch.setattr(batchregions.XmpManager, "save_regions", lambda *_args: False)
    dialog.region_type = "Pet"
    dialog.forced_tag = "Pets/Cat"
    dialog.recognition_enabled = False
    with pytest.raises(IOError):
        dialog.save_detections("/a.jpg", [face()], [])
    assert not tags


def test_batch_runs_detection_and_completes(window, monkeypatch):
    MainWindow.show_batch_regions(window)
    dialog = window.batch_regions_dialog
    dialog.tag_edit.setText("People/Forced")
    monkeypatch.setitem(batchregions.APP_CONFIG, "person_recognition_enabled", True)
    monkeypatch.setattr(batchregions, "AVAILABLE_FACE_ENGINES", ["face_recognition"])
    monkeypatch.setattr(batchregions.xmpmanager, "exiv2", object())
    monkeypatch.setattr(batchregions.XmpManager, "load_regions",
                        lambda _path, strict=False: [])
    monkeypatch.setattr(batchregions.ImageController, "detect_faces",
                        lambda self, strict=False: [face()])
    monkeypatch.setattr(batchregions, "extract_face_encoding",
                        lambda _path, _region: [42])
    saved = []
    monkeypatch.setattr(dialog, "save_detections",
                        lambda path, regions, encodings: saved.append(
                            (path, encodings)))
    dialog.start()
    for _ in range(200):
        if not dialog.running:
            break
        QTest.qWait(10)
    assert not dialog.running
    assert saved == [("/a.jpg", [[42]]), ("/b.jpg", [[42]])]
    assert dialog.progress_bar.value() == 2
    assert dialog.result() == QDialog.Accepted

    MainWindow.show_batch_regions(window)
    assert window.batch_regions_dialog is dialog
    assert dialog.tag_button.isEnabled()
    monkeypatch.setattr(
        widgets.TagSelectorWidget, "load_available_tags",
        lambda self: setattr(self, "available_tags", ["People/Alice"]))
    selected = []

    def select_tag():
        selector = QApplication.activeModalWidget()
        if not isinstance(selector, widgets.TagSelectorDialog):
            return
        selector.selector_widget.line_edit.setText("People/Alice")
        selected.append(selector.selector_widget.is_existing_tag())
        selector.selector_widget.action_button.click()

    QTimer.singleShot(0, select_tag)
    dialog.tag_button.click()
    assert selected == [True]
    assert dialog.tag_edit.text() == "People/Alice"
    dialog.close()


def test_manual_face_name_is_recorded_for_recognition(window, monkeypatch):
    dialog = batchregions.BatchRegionsDialog(window)
    writes, tags = prepare_save(dialog, monkeypatch, [])
    dialog.region_type = "Face"
    dialog.forced_tag = ""
    dialog.recognition_enabled = True
    monkeypatch.setattr(batchregions, "APP_CONFIG",
                        {"unrecognized_person_action": "ask"})
    stored = []
    db = SimpleNamespace(identify_person=lambda _encoding: (None, None),
                         add_face=lambda *args, **kwargs: stored.append((args, kwargs)))
    monkeypatch.setattr(batchregions.PersonRecognitionDB, "get_instance", lambda: db)
    monkeypatch.setattr(dialog, "ask_face_name",
                        lambda *_args: ("People/Bob", ["People/Bob"], True))
    dialog.save_detections("/a.jpg", [face()], [[1]])
    assert writes[0][1][0]["name"] == "Bob"
    assert tags == [("People/Bob", True)]
    assert stored[0][0][2] == "People/Bob"
    assert stored[0][1]["source"]["path"] == "/a.jpg"


def test_cancel_waits_for_current_detection_without_saving(window, monkeypatch):
    dialog = batchregions.BatchRegionsDialog(window)
    dialog.tag_edit.setText("People/Forced")
    monkeypatch.setattr(batchregions, "AVAILABLE_FACE_ENGINES", ["face_recognition"])
    monkeypatch.setattr(batchregions.xmpmanager, "exiv2", object())
    monkeypatch.setattr(batchregions.XmpManager, "load_regions",
                        lambda _path, strict=False: [])
    started, release = Event(), Event()

    def detect(_self, strict=False):
        started.set()
        release.wait(5)
        return [face()]

    monkeypatch.setattr(batchregions.ImageController, "detect_faces", detect)
    saved = []
    monkeypatch.setattr(dialog, "save_detections",
                        lambda *args: saved.append(args))
    dialog.start()
    try:
        assert started.wait(2)
        dialog.reject()
        assert dialog.running
    finally:
        release.set()
        for _ in range(200):
            if not dialog.running:
                break
            QTest.qWait(10)
    assert not dialog.running
    assert dialog.result() == QDialog.Rejected
    assert saved == []
    assert dialog.tag_button.isEnabled()


def test_strict_detection_surfaces_engine_error(qapp, monkeypatch):
    controller = imagecontroller.ImageController(["/a.jpg"], 0)
    monkeypatch.setattr(imagecontroller, "AVAILABLE_FACE_ENGINES", ["face_recognition"])
    monkeypatch.setattr(controller, "_detect_faces_face_recognition",
                        lambda path, strict=False: (_ for _ in ()).throw(IOError("bad image")))
    try:
        with pytest.raises(RuntimeError, match="bad image"):
            controller.detect_faces(strict=True)
    finally:
        controller.cleanup()


def test_strict_xmp_read_rejects_incomplete_regions(tmp_path, monkeypatch):
    path = tmp_path / "image.jpg"
    path.touch()
    datum = SimpleNamespace(
        key=lambda: "Xmp.mwg-rs.Regions/mwg-rs:RegionList[1]/mwg-rs:Name",
        toString=lambda: "Existing")
    image = SimpleNamespace(readMetadata=lambda: None, xmpData=lambda: [datum])
    monkeypatch.setattr(xmpmanager, "exiv2", SimpleNamespace(
        ImageFactory=SimpleNamespace(open=lambda _path: image)))
    assert xmpmanager.XmpManager.load_regions(str(path)) == []
    with pytest.raises(ValueError, match="Incomplete XMP region"):
        xmpmanager.XmpManager.load_regions(str(path), strict=True)


def test_pet_detection_assigns_forced_tag(window, monkeypatch):
    dialog = batchregions.BatchRegionsDialog(window)
    writes, tags = prepare_save(dialog, monkeypatch, [])
    dialog.region_type = "Pet"
    dialog.forced_tag = "Pets/Cat"
    dialog.recognition_enabled = True
    pet = dict(face(), type="Pet")
    dialog.save_detections("/a.jpg", [pet], [])
    assert writes[0][1] == [dict(pet, name="Cat")]
    assert tags == [("Pets/Cat", True)]


def test_updates_every_open_pane_for_changed_image(window, monkeypatch):
    dialog = batchregions.BatchRegionsDialog(window)
    prepare_save(dialog, monkeypatch, [])
    dialog.region_type = "Pet"
    dialog.forced_tag = "Pets/Cat"
    dialog.recognition_enabled = False
    refreshed = []

    def pane(path):
        return SimpleNamespace(
            controller=SimpleNamespace(
                get_current_path=lambda: path,
                load_regions=lambda: refreshed.append(path)),
            canvas=SimpleNamespace(update=lambda: None))

    first, second, other = pane("/a.jpg"), pane("/a.jpg"), pane("/b.jpg")
    window.viewers = [SimpleNamespace(
        panes=[first, second, other], active_pane=first,
        update_status_bar=lambda: refreshed.append("status"))]
    dialog.save_detections("/a.jpg", [dict(face(), type="Pet")], [])
    assert refreshed == ["/a.jpg", "status", "/a.jpg"]
