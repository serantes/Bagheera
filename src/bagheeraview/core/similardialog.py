import os
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QProgressBar, QTableWidget, QTableWidgetItem, QHeaderView,
    QSpinBox, QSplitter, QWidget, QMenu, QApplication, QAbstractItemView,
    QMessageBox
)
from PySide6.QtGui import QIcon, QImage, QDesktopServices
from PySide6.QtCore import Qt, QUrl
from .constants import UITexts, APP_CONFIG, AVAILABLE_FACE_ENGINES, AVAILABLE_PET_ENGINES
from .faiss_worker import FAISSSimilarSearchWorker
from .imageviewer import ImagePane
from .propertiesdialog import PropertiesDialog


class SimilarImagesDialog(QDialog):
    """Dialog to display and search for similar images."""
    def __init__(self, target_path, main_win):
        super().__init__(main_win)
        self.target_path = os.path.abspath(os.path.normpath(target_path))
        self.main_win = main_win
        self.worker = None
        self.results = []

        title = UITexts.SIMILAR_SEARCH_TITLE.format(
            os.path.basename(target_path))
        self.setWindowTitle(title)
        self.resize(1000, 700)

        layout = QVBoxLayout(self)

        # Main Splitter
        self.splitter = QSplitter(Qt.Horizontal)
        layout.addWidget(self.splitter)

        # Left Side Container
        left_container = QWidget()
        left_layout = QVBoxLayout(left_container)
        left_layout.setContentsMargins(0, 0, 0, 0)

        # Controls (Spinner and Search button)
        ctrl_layout = QHBoxLayout()
        ctrl_layout.addWidget(QLabel(UITexts.SETTINGS_DUPLICATE_THRESHOLD_LABEL))
        self.threshold_spin = QSpinBox()
        self.threshold_spin.setRange(50, 100)
        self.threshold_spin.setValue(APP_CONFIG.get("similar_threshold", 75))
        self.threshold_spin.setSuffix("%")
        ctrl_layout.addWidget(self.threshold_spin)

        self.btn_search = QPushButton(UITexts.RESCAN)
        self.btn_search.setIcon(QIcon.fromTheme("system-search"))
        self.btn_search.clicked.connect(self.start_search)
        ctrl_layout.addWidget(self.btn_search)
        left_layout.addLayout(ctrl_layout)

        # Progress area
        self.progress_bar = QProgressBar()
        self.progress_bar.hide()
        left_layout.addWidget(self.progress_bar)
        self.status_lbl = QLabel()
        left_layout.addWidget(self.status_lbl)

        # Results Table (Similarity % and Name)
        self.table = QTableWidget()
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(["%", UITexts.CONTEXT_MENU_OPEN])
        self.table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.currentCellChanged.connect(self._on_cell_changed)
        left_layout.addWidget(self.table)

        self.splitter.addWidget(left_container)

        # Right Side Container (Preview)
        self.right_pane_widget = self._create_preview_pane_widget()
        self.splitter.addWidget(self.right_pane_widget)
        self.preview_pane = self.right_pane_widget.pane
        self.splitter.setStretchFactor(0, 0)  # Left table doesn't stretch
        self.splitter.setStretchFactor(1, 1)  # Right image stretches
        self._next_region_type = "Face"
        self.start_search()

    def _create_preview_pane_widget(self):
        """Creates the right pane for image preview."""
        widget = QWidget()
        v_layout = QVBoxLayout(widget)
        v_layout.setContentsMargins(0, 0, 0, 0)

        info_lbl = QLabel()
        info_lbl.setAlignment(Qt.AlignCenter)
        info_lbl.setStyleSheet("font-weight: bold; color: #aaa;")
        v_layout.addWidget(info_lbl)

        pane = ImagePane(self, self.main_win.cache, [], 0, None, 0)
        pane.setContextMenuPolicy(Qt.CustomContextMenu)
        pane.controller.show_faces = False
        pane.customContextMenuRequested.connect(self._show_pane_context_menu)
        v_layout.addWidget(pane)

        widget.info_lbl = info_lbl
        widget.pane = pane
        widget.filename_lbl = QLabel()
        widget.filename_lbl.setAlignment(Qt.AlignCenter)
        widget.filename_lbl.setStyleSheet("font-size: 11px; font-weight: bold;")
        v_layout.addWidget(widget.filename_lbl)
        widget.dir_lbl = QLabel()
        widget.dir_lbl.setAlignment(Qt.AlignCenter)
        widget.dir_lbl.setStyleSheet("font-size: 9px; color: #888;")
        v_layout.addWidget(widget.dir_lbl)
        return widget

    def start_search(self):
        if self.worker and self.worker.isRunning():
            return

        self.table.setRowCount(0)
        self.results = []
        self.btn_search.setEnabled(False)
        self.progress_bar.show()
        self.progress_bar.setRange(0, 0)

        whitelist = APP_CONFIG.get("duplicate_whitelist", "")
        blacklist = APP_CONFIG.get("duplicate_blacklist", "")

        self.worker = FAISSSimilarSearchWorker(
            self.target_path,
            self.threshold_spin.value(), whitelist, blacklist)

        self.worker.progress_update.connect(self.on_progress)
        self.worker.results_found.connect(self.on_results_found)
        self.worker.finished.connect(self.on_finished)
        self.worker.start()

    def on_progress(self, cur, total, msg):
        self.status_lbl.show()
        if total > 0:
            self.progress_bar.show()
            self.progress_bar.setRange(0, total)
            self.progress_bar.setValue(cur)
        else:
            self.progress_bar.show()
            self.progress_bar.setRange(0, 0)
        self.status_lbl.setText(msg)

    def on_results_found(self, results):
        self.results = results
        self._populate_table()

    def _populate_table(self):
        self.table.blockSignals(True)
        self.table.setRowCount(len(self.results))
        for i, (path, sim) in enumerate(self.results):
            sim_item = QTableWidgetItem(f"{sim}%")
            sim_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 0, sim_item)
            self.table.setItem(i, 1, QTableWidgetItem(os.path.basename(path)))
        self.table.blockSignals(False)

        if self.results:
            self.table.setCurrentCell(0, 0)

    def on_finished(self):
        self.progress_bar.hide()
        self.status_lbl.setText("")
        self.status_lbl.hide()
        self.btn_search.setEnabled(True)

    def _on_cell_changed(self, row, col, prev_row, prev_col):
        if row >= 0 and row < len(self.results):
            path = self.results[row][0]
            self._update_preview(path)

    def _update_preview(self, path):
        if path:
            if not os.path.exists(path):
                self.preview_pane.controller.update_list([], 0)
                self.preview_pane.controller.load_image()
                self.right_pane_widget.info_lbl.setText(UITexts.FILE_NOT_FOUND)
                self.right_pane_widget.filename_lbl.setText("N/A")
                self.right_pane_widget.dir_lbl.setText("N/A")
                return

            self.preview_pane.controller.update_list([path], 0)
            self.preview_pane.controller.load_image()

            size_bytes = os.path.getsize(path)
            size_str = self._format_size(size_bytes)
            pix = self.preview_pane.controller.pixmap_original
            if not pix.isNull():
                self.right_pane_widget.info_lbl.setText(f"{size_str} - {pix.width()}x{pix.height()}")
            else:
                self.right_pane_widget.info_lbl.setText(f"{size_str} - N/A")

            self.right_pane_widget.filename_lbl.setText(os.path.basename(path))
            self.right_pane_widget.dir_lbl.setText(os.path.dirname(path))

            # Adjust zoom to fill the preview area
            viewport = self.preview_pane.scroll_area.viewport()
            w, h = viewport.width(), viewport.height()
            if w > 1 and h > 1:
                self.preview_pane.zoom_manager.calculate_initial_zoom(w, h, True)
                self.preview_pane.update_view()

    def _format_size(self, size):
        for unit in ['B', 'KiB', 'MiB', 'GiB']:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TiB"

    def _show_pane_context_menu(self, pos):
        """Shows context menu for the preview image."""
        path = self.preview_pane.controller.get_current_path()
        if not path or not os.path.exists(path):
            return

        menu = QMenu(self)

        # 1. Open Submenu
        open_menu = menu.addMenu(QIcon.fromTheme("document-open"), UITexts.CONTEXT_MENU_OPEN)
        self.main_win.populate_open_with_submenu(open_menu, path)

        action_open_bagheeraview = menu.addAction(QIcon.fromTheme("system-run"), UITexts.CONTEXT_MENU_OPEN_BAGHEERAVIEW)
        action_open_bagheeraview.triggered.connect(lambda: self._open_location_in_bagheeraview(path))

        action_open_default_app = menu.addAction(QIcon.fromTheme("system-run"), UITexts.CONTEXT_MENU_OPEN_DEFAULT_APP)
        action_open_default_app.triggered.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(path))))

        menu.addSeparator()

        # 2. Quick tags
        action_fast_tag = menu.addAction(QIcon.fromTheme("document-properties"), UITexts.VIEWER_MENU_TAGS)
        action_fast_tag.triggered.connect(self._show_fast_tags)

        # 3. Region management
        region_menu = menu.addMenu(QIcon.fromTheme("edit-image-face-recognize"), UITexts.VIEWER_MENU_DETECT_AREAS)

        action_detect_faces = region_menu.addAction(UITexts.VIEWER_MENU_DETECT_FACES)
        action_detect_faces.setEnabled(bool(AVAILABLE_FACE_ENGINES))
        action_detect_faces.triggered.connect(lambda: self._run_region_detection("faces"))

        action_detect_pets = region_menu.addAction(UITexts.VIEWER_MENU_DETECT_PETS)
        action_detect_pets.setEnabled(bool(AVAILABLE_PET_ENGINES))
        action_detect_pets.triggered.connect(lambda: self._run_region_detection("pets"))

        region_menu.addSeparator()

        action_add_face = region_menu.addAction(QIcon.fromTheme("list-add"), UITexts.VIEWER_MENU_ADD_FACE)
        action_add_face.triggered.connect(lambda: self.set_next_region_type("Face"))

        action_add_pet = region_menu.addAction(QIcon.fromTheme("list-add"), UITexts.VIEWER_MENU_ADD_PET)
        action_add_pet.triggered.connect(lambda: self.set_next_region_type("Pet"))

        action_add_body = region_menu.addAction(QIcon.fromTheme("list-add"), UITexts.VIEWER_MENU_ADD_BODY)
        action_add_body.triggered.connect(lambda: self.set_next_region_type("Body"))

        action_add_object = region_menu.addAction(QIcon.fromTheme("list-add"), UITexts.VIEWER_MENU_ADD_OBJECT)
        action_add_object.triggered.connect(lambda: self.set_next_region_type("Object"))

        action_add_landmark = region_menu.addAction(QIcon.fromTheme("list-add"), UITexts.VIEWER_MENU_ADD_LANDMARK)
        action_add_landmark.triggered.connect(lambda: self.set_next_region_type("Landmark"))

        menu.addSeparator()

        # 4. Clipboard
        clip_menu = menu.addMenu(QIcon.fromTheme("edit-copy"), UITexts.CONTEXT_MENU_CLIPBOARD)

        action_copy_image = clip_menu.addAction(QIcon.fromTheme("image-x-generic"), UITexts.VIEWER_MENU_COPY_IMAGE)
        action_copy_image.triggered.connect(lambda: QApplication.clipboard().setImage(QImage(path)))

        action_copy_path = clip_menu.addAction(QIcon.fromTheme("document-properties"), UITexts.VIEWER_MENU_COPY_PATH)
        action_copy_path.triggered.connect(lambda: QApplication.clipboard().setText(path))

        action_copy_dir = clip_menu.addAction(QIcon.fromTheme("folder"), UITexts.CONTEXT_MENU_COPY_DIR)
        action_copy_dir.triggered.connect(lambda: QApplication.clipboard().setText(os.path.dirname(path)))

        menu.addSeparator()

        # 5. Show faces & other regions
        action_show_faces = menu.addAction(QIcon.fromTheme("edit-image-face-show"), UITexts.SHOW_FACES)
        action_show_faces.setCheckable(True)
        action_show_faces.setChecked(self.preview_pane.controller.show_faces)
        action_show_faces.triggered.connect(self.toggle_faces)

        menu.addSeparator()

        # 6. Trash & Delete
        action_trash = menu.addAction(QIcon.fromTheme("user-trash"), UITexts.CONTEXT_MENU_TRASH)
        action_trash.triggered.connect(lambda: self._handle_deletion(path, permanent=False))

        action_delete = menu.addAction(QIcon.fromTheme("edit-delete"), UITexts.CONTEXT_MENU_DELETE)
        action_delete.triggered.connect(lambda: self._handle_permanent_delete(path))

        menu.addSeparator()

        # 7. Properties
        action_props = menu.addAction(QIcon.fromTheme("document-properties"), UITexts.CONTEXT_MENU_PROPERTIES)
        action_props.triggered.connect(lambda: self._show_properties(path))

        menu.exec(self.preview_pane.mapToGlobal(pos))

    def _handle_permanent_delete(self, path):
        confirm = QMessageBox(self)
        confirm.setIcon(QMessageBox.Warning)
        confirm.setText(UITexts.CONFIRM_DELETE_TEXT)
        confirm.setInformativeText(UITexts.CONFIRM_DELETE_INFO.format(os.path.basename(path)))
        confirm.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        confirm.setDefaultButton(QMessageBox.No)
        if confirm.exec() == QMessageBox.Yes:
            self._handle_deletion(path, permanent=True)

    def _handle_deletion(self, path, permanent=None):
        _permanent = permanent if permanent is not None else not APP_CONFIG.get("default_delete_to_trash", True)
        if not _permanent and APP_CONFIG.get("duplicate_confirm_delete", True):
            reply = QMessageBox.question(
                self, UITexts.CONFIRM_TRASH_TITLE, UITexts.CONFIRM_TRASH_TEXT,
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply != QMessageBox.Yes:
                return

        self.main_win.delete_file_by_path(path, permanent=_permanent)

        # Update local list and table
        current_row = self.table.currentRow()
        self.results = [r for r in self.results if r[0] != path]
        self._populate_table()

        if self.results:
            new_row = min(current_row, self.table.rowCount() - 1)
            self.table.selectRow(new_row)
            self.table.setCurrentCell(new_row, 0)
        else:
            # Clear preview labels
            self.preview_pane.controller.update_list([], 0)
            self.preview_pane.controller.load_image()
            self.right_pane_widget.info_lbl.setText("")
            self.right_pane_widget.filename_lbl.setText("")
            self.right_pane_widget.dir_lbl.setText("")

    def _show_properties(self, path):
        tags = self.preview_pane.controller._current_tags
        rating = self.preview_pane.controller._current_rating
        dlg = PropertiesDialog(path, initial_tags=tags, initial_rating=rating, parent=self)
        dlg.exec()

    def set_next_region_type(self, region_type):
        self._next_region_type = region_type
        if not self.preview_pane.controller.show_faces:
            self.preview_pane.controller.show_faces = True
            self.preview_pane.canvas.update()

    def toggle_faces(self):
        self.preview_pane.controller.show_faces = not self.preview_pane.controller.show_faces
        self.preview_pane.canvas.update()

    def _show_fast_tags(self):
        from .imageviewer import FastTagManager
        if not hasattr(self.preview_pane, "update_status_bar"):
            self.preview_pane.update_status_bar = lambda: None
        manager = FastTagManager(self.preview_pane)
        manager.show_menu()

    def _open_location_in_bagheeraview(self, path):
        folder_path = os.path.dirname(path)
        self.main_win.start_scan([folder_path])
        self.main_win.show()
        self.main_win.raise_()
        self.main_win.activateWindow()

    def _run_region_detection(self, detect_type):
        from .imageviewer import FaceNameDialog
        controller = self.preview_pane.controller
        canvas = self.preview_pane.canvas
        scroll_area = self.preview_pane.scroll_area

        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            if detect_type == "faces":
                new_regions = controller.detect_faces()
            elif detect_type == "pets":
                new_regions = controller.detect_pets()
            else:
                new_regions = []
        finally:
            QApplication.restoreOverrideCursor()

        if not new_regions:
            return

        IOU_THRESHOLD = 0.7
        added_count = 0
        for new_reg in new_regions:
            is_duplicate = False
            for existing_reg in controller.faces:
                iou = self._calculate_iou(new_reg, existing_reg)
                if iou > IOU_THRESHOLD:
                    is_duplicate = True
                    break

            if is_duplicate:
                continue

            if not controller.show_faces:
                controller.show_faces = True
                canvas.update()

            controller.faces.append(new_reg)
            canvas.update()

            w = canvas.width() if canvas else 0
            h = canvas.height() if canvas else 0
            if scroll_area:
                scroll_area.ensureVisible(int(new_reg.get('x', 0) * w),
                                          int(new_reg.get('y', 0) * h), 50, 50)
            QApplication.processEvents()

            history = self.main_win.face_names_history if self.main_win else []
            suggested = history[0] if history and APP_CONFIG.get(
                "face_use_last_name", False) else ""

            full_tag, updated_history, ok = FaceNameDialog.get_name(
                self, history, current_name=suggested, main_win=self.main_win)

            if ok and full_tag:
                new_reg['name'] = full_tag
                controller.toggle_tag(full_tag, True)
                if self.main_win:
                    self.main_win.face_names_history = updated_history
                added_count += 1
            else:
                controller.faces.pop()
                canvas.update()

        if added_count > 0:
            try:
                controller.save_faces()
            except Exception as e:
                QMessageBox.critical(self, UITexts.ERROR, str(e))

    def _calculate_iou(self, boxA, boxB):
        boxA_x1 = boxA['x'] - boxA['w'] / 2
        boxA_y1 = boxA['y'] - boxA['h'] / 2
        boxA_x2 = boxA['x'] + boxA['w'] / 2
        boxA_y2 = boxA['y'] + boxA['h'] / 2

        boxB_x1 = boxB['x'] - boxB['w'] / 2
        boxB_y1 = boxB['y'] - boxB['h'] / 2
        boxB_x2 = boxB['x'] + boxB['w'] / 2
        boxB_y2 = boxB['y'] + boxB['h'] / 2

        xA = max(boxA_x1, boxB_x1)
        yA = max(boxA_y1, boxB_y1)
        xB = min(boxA_x2, boxB_x2)
        yB = min(boxA_y2, boxB_y2)

        interArea = max(0, xB - xA) * max(0, yB - yA)
        boxAArea = boxA['w'] * boxA['h']
        boxBArea = boxB['w'] * boxB['h']

        denominator = float(boxAArea + boxBArea - interArea)
        iou = interArea / denominator if denominator > 0 else 0
        return iou

    # Implementation of API required for ImagePane
    def set_active_pane(self, pane):
        pass

    def on_metadata_changed(self, path, metadata=None):
        pass

    def on_controller_list_updated(self, index):
        pass

    def update_view_for_pane(self, pane, resize_win=False):
        pixmap = pane.controller.get_display_pixmap()
        if not pixmap.isNull():
            pane.canvas.setPixmap(pixmap)
            pane.canvas.adjustSize()

    def load_and_fit_image_for_pane(self, pane, restore_config=None):
        pass

    def reset_inactivity_timer(self):
        pass

    def sync_filmstrip_selection(self, index):
        pass

    def _get_clicked_face_for_pane(self, pane, pos):
        return None

    def rename_face(self, face):
        pass

    def toggle_fullscreen(self):
        pass

    def wheelEvent(self, event):
        """Handles mouse wheel events for zooming the preview image."""
        if event.modifiers() & Qt.ControlModifier and self.preview_pane:
            focus_pos = self.preview_pane.mapFromGlobal(event.globalPosition().toPoint())
            if event.angleDelta().y() > 0:
                self.preview_pane.zoom_manager.zoom(1.1, focus_point=focus_pos)
            else:
                self.preview_pane.zoom_manager.zoom(0.9, focus_point=focus_pos)
            event.accept()
        else:
            super().wheelEvent(event)

    def keyPressEvent(self, event):
        """Handles keyboard shortcuts for zooming."""
        key = event.key()
        if key in (Qt.Key_Plus, Qt.Key_Equal):
            if self.preview_pane:
                self.preview_pane.zoom_manager.zoom(1.1)
            event.accept()
        elif key == Qt.Key_Minus:
            if self.preview_pane:
                self.preview_pane.zoom_manager.zoom(0.9)
            event.accept()
        elif key == Qt.Key_0:
            if self.preview_pane:
                self.preview_pane.zoom_manager.zoom(1.0, reset=True)
            event.accept()
        elif key == Qt.Key_Z:
            if self.preview_pane:
                self.preview_pane.zoom_manager.toggle_fit_to_screen()
            event.accept()
        else:
            super().keyPressEvent(event)

    def done(self, r):
        if self.worker and self.worker.isRunning():
            self.worker.stop()
        if self.preview_pane:
            self.preview_pane.cleanup()
        super().done(r)
