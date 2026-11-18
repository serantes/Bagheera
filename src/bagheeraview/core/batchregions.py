"""Batch detection of face and pet regions."""
import logging
import os

from PySide6.QtCore import QThread, QTimer, Qt
from PySide6.QtGui import QImageReader, QPixmap
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QProgressBar, QPushButton, QVBoxLayout,
)

from .constants import (
    APP_CONFIG, AVAILABLE_FACE_ENGINES, AVAILABLE_PET_ENGINES, ITEM_TYPE_ROLE,
    MEDIAPIPE_FACE_MODEL_PATH, MEDIAPIPE_OBJECT_MODEL_PATH, PATH_ROLE, UITexts,
)
from .imagecontroller import ImageController
from .imageviewer import FaceNameDialog
from .metadatamanager import load_common_metadata
from .personrecognition import (
    FACE_REGION_IOU_THRESHOLD, PersonRecognitionDB, _regions_iou,
    extract_face_encoding,
)
from .widgets import TagSelectorDialog
from .xmpmanager import XmpManager
from . import xmpmanager

logger = logging.getLogger(__name__)


class RegionDetectionThread(QThread):
    def __init__(self, controller, region_type, recognition_enabled, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.region_type = region_type
        self.recognition_enabled = recognition_enabled
        self.regions = []
        self.encodings = []
        self.error = None

    def run(self):
        try:
            path = self.controller.get_current_path()
            if self.region_type == "Face":
                self.regions = self.controller.detect_faces(strict=True)
                if self.recognition_enabled:
                    self.encodings = [
                        extract_face_encoding(path, region) for region in self.regions
                    ]
            else:
                self.regions = self.controller.detect_pets(strict=True)
        except Exception as error:
            logger.exception("Region detection failed")
            self.error = error


class BatchRegionsDialog(QDialog):
    def __init__(self, main_win, parent=None):
        super().__init__(parent or main_win)
        self.setModal(False)
        self.main_win = main_win
        self.paths = []
        self.controller = None
        self.worker = None
        self.running = False
        self.cancelled = False
        self.position = 0

        self.setWindowTitle(UITexts.BATCH_REGIONS_TITLE)
        self.setMinimumWidth(500)
        layout = QVBoxLayout(self)
        row = QHBoxLayout()
        row.addWidget(QLabel(UITexts.BATCH_REGION_LABEL))
        self.region_combo = QComboBox()
        self.region_combo.addItem(UITexts.BATCH_FACES, "Face")
        self.region_combo.addItem(UITexts.BATCH_PETS, "Pet")
        row.addWidget(self.region_combo)
        self.displayed_check = QCheckBox(UITexts.BATCH_DISPLAYED_ONLY)
        self.displayed_check.setChecked(True)
        row.addWidget(self.displayed_check)
        layout.addLayout(row)
        self.count_label = QLabel()
        layout.addWidget(self.count_label)
        self.progress_bar = QProgressBar()
        layout.addWidget(self.progress_bar)

        tag_row = QHBoxLayout()
        tag_row.addWidget(QLabel(UITexts.BATCH_FORCE_TAG))
        self.tag_edit = QLineEdit()
        self.tag_edit.setClearButtonEnabled(True)
        tag_row.addWidget(self.tag_edit)
        self.tag_button = QPushButton("...")
        self.tag_button.clicked.connect(self.select_tag)
        tag_row.addWidget(self.tag_button)
        layout.addLayout(tag_row)

        buttons = QHBoxLayout()
        buttons.addStretch()
        self.accept_button = QPushButton(UITexts.ACCEPT)
        self.cancel_button = QPushButton(UITexts.CANCEL)
        buttons.addWidget(self.accept_button)
        buttons.addWidget(self.cancel_button)
        layout.addLayout(buttons)
        self.displayed_check.toggled.connect(self.update_paths)
        self.accept_button.clicked.connect(self.start)
        self.cancel_button.clicked.connect(self.reject)
        self.update_paths()

    def select_tag(self):
        dialog = TagSelectorDialog(self)
        if dialog.exec() == QDialog.Accepted:
            self.tag_edit.setText(dialog.get_selected_tag())

    def update_paths(self):
        if self.displayed_check.isChecked():
            model = self.main_win.proxy_model
            paths = []
            for row in range(model.rowCount()):
                index = model.index(row, 0)
                if model.data(index, ITEM_TYPE_ROLE) == "thumbnail":
                    path = model.data(index, PATH_ROLE)
                    if path:
                        paths.append(path)
        else:
            paths = self.main_win._gather_files_for_duplicates()
        self.paths = list(dict.fromkeys(paths)) if paths is not None else None
        count = len(self.paths) if self.paths is not None else 0
        self.count_label.setText(UITexts.BATCH_ITEMS_COUNT.format(count))
        self.progress_bar.setRange(0, max(count, 1))
        self.progress_bar.setValue(0)

    def start(self):
        self.update_paths()
        if self.paths is None:
            QMessageBox.warning(self, UITexts.WARNING, UITexts.DUPLICATE_WHITELIST_EMPTY)
            return
        if not self.paths:
            QMessageBox.information(self, UITexts.BATCH_REGIONS_TITLE, UITexts.BATCH_NO_IMAGES)
            return
        region_type = self.region_combo.currentData()
        forced_tag = self.tag_edit.text().strip()
        if region_type == "Pet" and not forced_tag:
            QMessageBox.warning(self, UITexts.WARNING, UITexts.BATCH_PET_TAG_REQUIRED)
            return
        if region_type == "Pet":
            usable = bool(AVAILABLE_PET_ENGINES) and os.path.exists(MEDIAPIPE_OBJECT_MODEL_PATH)
        else:
            usable = ("face_recognition" in AVAILABLE_FACE_ENGINES or
                      ("mediapipe" in AVAILABLE_FACE_ENGINES and
                       os.path.exists(MEDIAPIPE_FACE_MODEL_PATH)))
        if not usable:
            QMessageBox.warning(self, UITexts.WARNING, UITexts.BATCH_NO_ENGINE)
            return
        if not xmpmanager.exiv2:
            QMessageBox.critical(self, UITexts.ERROR, UITexts.BATCH_EXIV2_REQUIRED)
            return

        self.region_type = region_type
        self.forced_tag = forced_tag
        self.recognition_enabled = APP_CONFIG.get("person_recognition_enabled", False)
        self.controller = ImageController([], 0)
        self.controller.metadata_changed.connect(self.main_win.update_metadata_for_path)
        self.position = 0
        self.cancelled = False
        self.running = True
        for widget in (self.region_combo, self.displayed_check, self.tag_edit,
                       self.tag_button, self.accept_button):
            widget.setEnabled(False)
        self.next_image()

    def next_image(self):
        if self.cancelled or self.position >= len(self.paths):
            self.finish()
            return
        path = self.paths[self.position]
        try:
            existing = XmpManager.load_regions(path, strict=True)
        except Exception as error:
            logger.exception("Could not check existing regions for %s", path)
            QMessageBox.critical(self, UITexts.ERROR, f"{path}\n{error}")
            self.finish()
            return
        if any(region.get("type", "Face") == self.region_type
               for region in existing):
            self.position += 1
            self.progress_bar.setValue(self.position)
            QTimer.singleShot(0, self.next_image)
            return
        self.controller.image_list = [self.paths[self.position]]
        self.controller.index = 0
        self.worker = RegionDetectionThread(
            self.controller, self.region_type,
            self.recognition_enabled, self)
        self.worker.finished.connect(self.detection_finished)
        self.worker.finished.connect(self.worker.deleteLater)
        self.worker.start()

    def detection_finished(self):
        worker = self.worker
        self.worker = None
        if self.cancelled:
            self.finish()
            return
        path = self.paths[self.position]
        try:
            if worker.error:
                raise worker.error
            self.save_detections(path, worker.regions, worker.encodings)
        except Exception as error:
            logger.exception("Batch region processing failed for %s", path)
            QMessageBox.critical(self, UITexts.ERROR, f"{path}\n{error}")
            self.finish()
            return
        self.position += 1
        self.progress_bar.setValue(self.position)
        QTimer.singleShot(0, self.next_image)

    def save_detections(self, path, detected, encodings):
        if not detected:
            return
        existing = XmpManager.load_regions(path, strict=True)
        if any(region.get("type", "Face") == self.region_type
               for region in existing):
            return
        metadata = load_common_metadata(path)
        self.controller._current_tags = metadata.tags
        self.controller._current_rating = metadata.rating
        additions = []
        manual_faces = []
        rec_db = None
        for index, region in enumerate(detected):
            if any(_regions_iou(region, other) > FACE_REGION_IOU_THRESHOLD
                   for other in additions):
                continue
            encoding = encodings[index] if index < len(encodings) else None
            tag = self.forced_tag
            if (self.region_type == "Face" and self.recognition_enabled
                    and encoding):
                if rec_db is None:
                    rec_db = PersonRecognitionDB.get_instance()
                matched_tag, _ = rec_db.identify_person(encoding)
                if self.forced_tag:
                    matched_name = matched_tag.rsplit("/", 1)[-1] if matched_tag else ""
                    forced_name = self.forced_tag.rsplit("/", 1)[-1]
                    if matched_name != forced_name:
                        manual_faces.append((region, encoding, self.forced_tag))
                else:
                    tag = matched_tag
            if not tag and self.recognition_enabled and APP_CONFIG.get(
                    "unrecognized_person_action", "ask") == "assign_tag":
                tag = APP_CONFIG.get("unrecognized_person_tag", "Unrecognized")
            if not tag:
                history = self.main_win.face_names_history
                suggested = history[0] if history and APP_CONFIG.get(
                    "face_use_last_name", False) else ""
                tag, history, ok = self.ask_face_name(path, region, history, suggested)
                if not ok or not tag:
                    continue
                self.main_win.face_names_history = history
                if self.recognition_enabled and encoding:
                    manual_faces.append((region, encoding, tag))
            region = dict(region, name=tag)
            additions.append(region)
            if tag not in self.main_win.face_names_history and self.region_type == "Face":
                self.main_win.face_names_history.insert(0, tag)

        if not additions:
            return
        saved = [
            dict(region, name=region.get("name", "").split("/")[-1])
            for region in existing + additions
        ]
        if not XmpManager.save_regions(path, saved):
            raise IOError(UITexts.BATCH_WRITE_ERROR.format(path))
        for tag in {region["name"] for region in additions}:
            self.controller.toggle_tag(tag, True)
        for region, encoding, tag in manual_faces:
            if tag != APP_CONFIG.get("unrecognized_person_tag", "Unrecognized"):
                if rec_db is None:
                    rec_db = PersonRecognitionDB.get_instance()
                source = {"path": path, **{key: region[key] for key in ("x", "y", "w", "h")}}
                rec_db.add_face(None, encoding, tag, source=source)
        for viewer in self.main_win.viewers:
            for pane in viewer.panes:
                if pane.controller.get_current_path() == path:
                    pane.controller._current_tags = self.controller._current_tags
                    pane.controller.load_regions()
                    pane.canvas.update()
                    if pane is viewer.active_pane:
                        viewer.update_status_bar()

    def ask_face_name(self, path, region, history, suggested):
        dialog = FaceNameDialog(self, history, suggested, self.main_win)
        dialog.setWindowTitle(f"{UITexts.ADD_FACE_TITLE} - {os.path.basename(path)}")
        reader = QImageReader(path)
        image = reader.read()
        if image.isNull():
            raise IOError(reader.errorString())
        width, height = image.width(), image.height()
        x = max(0, int((region["x"] - region["w"] * 0.75) * width))
        y = max(0, int((region["y"] - region["h"] * 0.75) * height))
        w = min(width - x, int(region["w"] * 1.5 * width))
        h = min(height - y, int(region["h"] * 1.5 * height))
        preview = QLabel()
        preview.setPixmap(QPixmap.fromImage(image.copy(x, y, w, h)).scaled(
            250, 250, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        dialog.layout().insertWidget(0, preview)
        if dialog.exec() == QDialog.Accepted:
            return dialog.final_tag, dialog.final_history, True
        return suggested, history, False

    def finish(self):
        self.running = False
        if self.controller:
            self.controller.cleanup()
            self.controller = None
        for widget in (self.region_combo, self.displayed_check, self.tag_edit,
                       self.tag_button, self.accept_button):
            widget.setEnabled(True)
        if self.cancelled:
            super().reject()
        elif self.position >= len(self.paths):
            super().accept()

    def reject(self):
        if self.running:
            self.cancelled = True
        else:
            super().reject()

    def closeEvent(self, event):
        if self.running:
            self.cancelled = True
            event.ignore()
        else:
            super().closeEvent(event)
