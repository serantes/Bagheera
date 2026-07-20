import os
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QProgressBar, QTableWidget, QTableWidgetItem, QHeaderView,
    QSpinBox, QSplitter, QWidget, QMenu, QApplication, QAbstractItemView,
    QMessageBox
)
from PySide6.QtGui import QIcon, QImage, QDesktopServices
from PySide6.QtCore import Qt, QUrl
from .constants import UITexts, APP_CONFIG
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
        if total > 0:
            self.progress_bar.setRange(0, total)
            self.progress_bar.setValue(cur)
        else:
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

        # Submenú Abrir con...
        open_menu = menu.addMenu(QIcon.fromTheme("document-open"), UITexts.CONTEXT_MENU_OPEN)
        self.main_win.populate_open_with_submenu(open_menu, path)

        # Abrir ubicación
        action_open_default_app = menu.addAction(QIcon.fromTheme("system-run"), UITexts.CONTEXT_MENU_OPEN_DEFAULT_APP)
        action_open_default_app.triggered.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(path))))

        menu.addSeparator()

        # Portapapeles
        clip_menu = menu.addMenu(QIcon.fromTheme("edit-copy"), UITexts.CONTEXT_MENU_CLIPBOARD)
        action_copy_image = clip_menu.addAction(QIcon.fromTheme("image-x-generic"), UITexts.VIEWER_MENU_COPY_IMAGE)
        action_copy_image.triggered.connect(lambda: QApplication.clipboard().setImage(QImage(path)))
        action_copy_path = clip_menu.addAction(QIcon.fromTheme("document-properties"), UITexts.VIEWER_MENU_COPY_PATH)
        action_copy_path.triggered.connect(lambda: QApplication.clipboard().setText(path))

        menu.addSeparator()

        # Papelera / Borrar
        action_trash = menu.addAction(QIcon.fromTheme("user-trash"), UITexts.CONTEXT_MENU_TRASH)
        action_trash.triggered.connect(lambda: self._handle_deletion(path, permanent=False))

        action_delete = menu.addAction(QIcon.fromTheme("edit-delete"), UITexts.CONTEXT_MENU_DELETE)
        action_delete.triggered.connect(lambda: self._handle_permanent_delete(path))

        menu.addSeparator()

        # Propiedades
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

    def done(self, r):
        if self.worker and self.worker.isRunning():
            self.worker.stop()
        if self.preview_pane:
            self.preview_pane.cleanup()
        super().done(r)
