"""
Similar Image Search Dialog Module for Bagheera.

This module implements the SimilarImagesDialog, a dialog that searches for
images visually similar to a target image. The similarity search runs in a
background thread (see FAISSSimilarSearchWorker) and its results are shown in a
table, with an image preview pane that supports zooming, region detection,
fast tagging and file management actions.

Classes:
    SimilarImagesDialog: Dialog to search for and manage similar images.
"""
import os
import subprocess
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QProgressBar, QTableWidget, QTableWidgetItem, QHeaderView,
    QSpinBox, QSplitter, QWidget, QMenu, QApplication, QAbstractItemView,
    QMessageBox
)
from PySide6.QtGui import (
    QDesktopServices, QIcon, QImage, QKeySequence, QShortcut
)
from PySide6.QtCore import Qt, QUrl
from .constants import (
    UITexts, APP_CONFIG, AVAILABLE_FACE_ENGINES, AVAILABLE_PET_ENGINES,
    DEFAULT_DIALOG_SHORTCUTS
)
from .faiss_worker import FAISSSimilarSearchWorker
from .imageviewer import ImagePane
from .propertiesdialog import PropertiesDialog


class SimilarImagesDialog(QDialog):
    """
    A dialog to search for and manage images visually similar to a target file.

    Similarity results are listed on the left-hand table together with an
    image preview pane on the right. The preview reuses the ImagePane
    machinery to support zooming, automatic region detection (faces and pets),
    fast tagging, deletion and metadata editing of the selected result.
    """

    # The dialog resolves the context-menu keyboard shortcuts itself, so the
    # application-wide shortcut controller must not intercept those keys.
    handles_own_shortcuts = True

    def __init__(self, target_path, main_win):
        """
        Initializes the SimilarImagesDialog.

        Args:
            target_path (str): Path of the image against which the similarity
                is computed.
            main_win (MainWindow): Reference to the main application window.
        """
        super().__init__(main_win)
        self.target_path = os.path.abspath(os.path.normpath(target_path))
        self.main_win = main_win
        self.worker = None
        self.results = []

        self.active_pane = None

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
        ctrl_layout.addWidget(QLabel(UITexts.SETTINGS_SIMILAR_THRESHOLD_LABEL))
        self.threshold_spin = QSpinBox()
        self.threshold_spin.setRange(40, 100)
        self.threshold_spin.setValue(APP_CONFIG.get("similar_threshold", 65))
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
        self._setup_dialog_shortcuts()
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
        """
        Starts a new similarity search using the current threshold.

        The search button is disabled and an indeterminate progress bar is
        shown while a FAISSSimilarSearchWorker runs in the background. If a
        search is already running, this method does nothing.
        """
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
        """
        Callback for the progress updates emitted by the search worker.

        Args:
            cur (int): Number of images processed so far.
            total (int): Total number of images to process.
            msg (str): Human readable progress message.
        """
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
        """
        Callback for the similarity results emitted by the search worker.

        Args:
            results (list): List of ``(path, similarity)`` tuples ordered by
                descending similarity.
        """
        self.results = results
        self._populate_table()

    def _populate_table(self):
        """
        Fills the results table with the current similarity results.

        Each row shows the similarity percentage and the file name of the
        corresponding match; the first row is selected when results exist.
        """
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
        """Restores the dialog controls after the search worker finishes."""
        self.progress_bar.hide()
        self.status_lbl.setText("")
        self.status_lbl.hide()
        self.btn_search.setEnabled(True)

    def _on_cell_changed(self, row, col, prev_row, prev_col):
        """
        Updates the preview pane when the current table row changes.

        Args:
            row (int): New current row.
            col (int): New current column.
            prev_row (int): Previous current row.
            prev_col (int): Previous current column.
        """
        if row >= 0 and row < len(self.results):
            path = self.results[row][0]
            self._update_preview(path)

    def _update_preview(self, path):
        """
        Loads the given image into the preview pane and updates its labels.

        If the file no longer exists, an informative placeholder is shown.

        Args:
            path (str): Path of the image to preview.
        """
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
        """
        Formats a byte count into a human readable size string.

        Args:
            size (float): Size in bytes.

        Returns:
            str: Size formatted with the most appropriate binary unit.
        """
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

        # If regions are shown and the click falls inside one, display the
        # region menu instead of the general image menu.
        global_pos = self.preview_pane.mapToGlobal(pos)
        if self._show_region_context_menu(global_pos):
            return

        menu = QMenu(self)

        # 1. Open Submenu
        open_menu = menu.addMenu(QIcon.fromTheme("document-open"), UITexts.CONTEXT_MENU_OPEN)
        self.main_win.populate_open_with_submenu(open_menu, path)

        action_open_bagheeraview = menu.addAction(QIcon.fromTheme("system-run"), UITexts.CONTEXT_MENU_OPEN_BAGHEERAVIEW)
        action_open_bagheeraview.triggered.connect(lambda: self._open_location_in_bagheeraview(path))

        action_open_default_app = menu.addAction(QIcon.fromTheme("system-run"), UITexts.CONTEXT_MENU_OPEN_DEFAULT_APP)
        # action_open_default_app.triggered.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(path))))
        action_open_default_app.triggered.connect(
            lambda: subprocess.Popen(['dolphin', '--select', path])
            if os.path.isfile(path)
            else QDesktopServices.openUrl(
                QUrl.fromLocalFile(
                    path if os.path.isdir(path) else os.path.dirname(path)
                )
            )
        )

        menu.addSeparator()

        # 2. Quick tags
        action_fast_tag = menu.addAction(
            QIcon.fromTheme("document-properties"),
            self._menu_text(UITexts.VIEWER_MENU_TAGS, "fast_tag"))
        action_fast_tag.triggered.connect(self._show_fast_tags)

        # 3. Region management
        region_menu = menu.addMenu(
            QIcon.fromTheme("edit-image-face-recognize"),
            UITexts.VIEWER_MENU_DETECT_AREAS)

        action_detect_faces = region_menu.addAction(
            self._menu_text(UITexts.VIEWER_MENU_DETECT_FACES, "detect_faces"))
        action_detect_faces.setEnabled(bool(AVAILABLE_FACE_ENGINES))
        action_detect_faces.triggered.connect(
            lambda: self._run_region_detection("faces"))

        action_detect_pets = region_menu.addAction(
            self._menu_text(UITexts.VIEWER_MENU_DETECT_PETS, "detect_pets"))
        action_detect_pets.setEnabled(bool(AVAILABLE_PET_ENGINES))
        action_detect_pets.triggered.connect(
            lambda: self._run_region_detection("pets"))

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
        action_copy_path.triggered.connect(lambda: QApplication.clipboard().setText(f"'{path}'"))

        action_copy_dir = clip_menu.addAction(QIcon.fromTheme("folder"), UITexts.CONTEXT_MENU_COPY_DIR)
        action_copy_dir.triggered.connect(lambda: QApplication.clipboard().setText(f"'{os.path.dirname(path)}'"))

        menu.addSeparator()

        # 5. Show faces & other regions
        action_show_faces = menu.addAction(
            QIcon.fromTheme("edit-image-face-show"),
            self._menu_text(UITexts.SHOW_FACES, "toggle_faces"))
        action_show_faces.setCheckable(True)
        action_show_faces.setChecked(self.preview_pane.controller.show_faces)
        action_show_faces.triggered.connect(self.toggle_faces)

        menu.addSeparator()

        # 6. Trash & Delete
        action_trash = menu.addAction(
            QIcon.fromTheme("user-trash"),
            self._menu_text(UITexts.CONTEXT_MENU_TRASH, "move_to_trash"))
        action_trash.triggered.connect(
            lambda: self._handle_deletion(path, permanent=False))

        action_delete = menu.addAction(
            QIcon.fromTheme("edit-delete"),
            self._menu_text(UITexts.CONTEXT_MENU_DELETE, "delete_permanently"))
        action_delete.triggered.connect(
            lambda: self._handle_permanent_delete(path))

        menu.addSeparator()

        # 7. Properties
        action_props = menu.addAction(
            QIcon.fromTheme("document-properties"),
            self._menu_text(UITexts.CONTEXT_MENU_PROPERTIES, "properties"))
        action_props.triggered.connect(lambda: self._show_properties(path))

        menu.exec(global_pos)

    def _show_region_context_menu(self, global_pos):
        """
        Shows the region context menu when the click falls over a region.

        Regions are shown when face display is enabled. The menu offers the
        same actions as the image viewer: delete the region and rename it.

        Args:
            global_pos (QPoint): Global position of the context-menu request.

        Returns:
            bool: True if a region was clicked and its menu was shown.
        """
        controller = self.preview_pane.controller
        if not controller.show_faces:
            return False

        canvas = self.preview_pane.canvas
        if canvas is None:
            return False

        clicked_face = self._get_clicked_face(canvas.mapFromGlobal(global_pos))
        if not clicked_face:
            return False

        menu = QMenu(self)
        action_delete = menu.addAction(QIcon.fromTheme("edit-delete"),
                                       UITexts.DELETE_AREA_TITLE)
        action_rename = menu.addAction(QIcon.fromTheme("edit-rename"),
                                       UITexts.RENAME_REGION_TITLE)
        res = menu.exec(global_pos)

        if res == action_delete:
            face_name = clicked_face.get('name', '')
            controller.remove_face(clicked_face)
            if face_name:
                has_other = any(f.get('name') == face_name
                                for f in controller.faces)
                if not has_other:
                    controller.toggle_tag(face_name, False)
            canvas.update()
        elif res == action_rename:
            self.rename_face(clicked_face)
        return True

    def _handle_permanent_delete(self, path):
        """
        Asks for confirmation and permanently deletes the given file.

        Args:
            path (str): Path of the file to delete.
        """
        confirm = QMessageBox(self)
        confirm.setIcon(QMessageBox.Warning)
        confirm.setText(UITexts.CONFIRM_DELETE_TEXT)
        confirm.setInformativeText(UITexts.CONFIRM_DELETE_INFO.format(os.path.basename(path)))
        confirm.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        confirm.setDefaultButton(QMessageBox.No)
        if confirm.exec() == QMessageBox.Yes:
            self._handle_deletion(path, permanent=True)

    def _handle_deletion(self, path, permanent=None):
        """
        Deletes the given file (moving it to trash by default) and refreshes
        the results table.

        Args:
            path (str): Path of the file to delete.
            permanent (bool, optional): If True, the file is deleted without
                using the trash bin. When None, the ``default_delete_to_trash``
                application setting is used.
        """
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
        """
        Opens the properties dialog for the given image.

        Args:
            path (str): Path of the image whose properties are requested.
        """
        tags = self.preview_pane.controller._current_tags
        rating = self.preview_pane.controller._current_rating
        dlg = PropertiesDialog(path, initial_tags=tags, initial_rating=rating, parent=self)
        dlg.exec()

    def set_next_region_type(self, region_type):
        """
        Sets the region type for the next manual region added by the user.

        Args:
            region_type (str): Region type identifier (e.g. "Face", "Pet").
        """
        self._next_region_type = region_type
        if not self.preview_pane.controller.show_faces:
            self.preview_pane.controller.show_faces = True
            self.preview_pane.canvas.update()

    def toggle_faces(self):
        """Toggles the display of face regions on the preview image."""
        self.preview_pane.controller.show_faces = not self.preview_pane.controller.show_faces
        self.preview_pane.canvas.update()

    def _show_fast_tags(self):
        """Shows the fast tagging menu for the current preview image."""
        from .imageviewer import FastTagManager
        if not hasattr(self.preview_pane, "update_status_bar"):
            self.preview_pane.update_status_bar = lambda: None
        manager = FastTagManager(self.preview_pane)
        manager.show_menu()

    def _menu_text(self, base_text, action=None):
        """
        Appends the keyboard shortcut assigned to ``action`` to ``base_text``.

        Args:
            base_text (str): Original action text.
            action (str, optional): Action name whose shortcut is displayed,
                if one is configured.

        Returns:
            str: The text with the shortcut hint appended (``\\t<shortcut>``)
            when a shortcut is available.
        """
        key_combo = self._menu_action_shortcuts.get(action) if action else None
        if key_combo is None:
            return base_text
        key, mods = key_combo
        try:
            mod_val = int(mods)
        except TypeError:
            mod_val = mods.value
        seq = QKeySequence(mod_val | key)
        shortcut_str = seq.toString(QKeySequence.NativeText)
        return f"{base_text}\t{shortcut_str}" if shortcut_str else base_text

    def _setup_dialog_shortcuts(self):
        """
        Registers the context-menu shortcuts for this dialog.

        The shortcuts are taken from the viewer shortcuts of the main window
        (so they are configurable by the user) and are installed with the
        ``WidgetWithChildrenShortcut`` context, which guarantees they work no
        matter which child widget (results table, preview pane, ...) has the
        focus.
        """
        self._menu_action_shortcuts = {}
        viewer_shortcuts = getattr(self.main_win, "viewer_shortcuts", {}) or {}
        for _key_combo, (action, _desc) in viewer_shortcuts.items():
            self._menu_action_shortcuts[action] = _key_combo

        # The trash and permanent-delete actions reuse the global shortcuts.
        controller = getattr(self.main_win, "shortcut_controller", None)
        if controller is not None:
            for action in ("move_to_trash", "delete_permanently"):
                key_combo = getattr(
                    controller, "action_to_shortcut", {}).get(action)
                if key_combo is not None:
                    self._menu_action_shortcuts[action] = key_combo

        self._shortcut_objects = []
        self._menu_handlers = {
            "fast_tag": self._show_fast_tags,
            "detect_faces": lambda: self._run_region_detection("faces"),
            "detect_pets": lambda: self._run_region_detection("pets"),
            "toggle_faces": self.toggle_faces,
            "properties": self._show_properties_current,
            "move_to_trash": self._shortcut_trash,
            "delete_permanently": self._shortcut_delete,
        }
        # Reverse map used as a keyPressEvent fallback (same lookup that the
        # ImageViewer uses), so the shortcuts keep working even if the widget
        # that holds the focus forwards the key event to the dialog.
        self._menu_shortcut_keys = {
            key_combo: action
            for action, key_combo in self._menu_action_shortcuts.items()
        }
        for action, handler in self._menu_handlers.items():
            key_combo = self._menu_action_shortcuts.get(action)
            if key_combo is None:
                continue
            key, mods = key_combo
            try:
                mod_val = int(mods)
            except TypeError:
                mod_val = mods.value
            shortcut = QShortcut(
                QKeySequence(mod_val | key), self)
            shortcut.setContext(Qt.WidgetWithChildrenShortcut)
            shortcut.activated.connect(handler)
            self._shortcut_objects.append(shortcut)

    def _show_properties_current(self):
        """Shows the properties dialog for the currently previewed image."""
        path = (self.preview_pane.controller.get_current_path()
                if self.preview_pane else None)
        if path:
            self._show_properties(path)

    def _shortcut_trash(self):
        """Moves the currently previewed image to the trash."""
        path = (self.preview_pane.controller.get_current_path()
                if self.preview_pane else None)
        if path:
            self._handle_deletion(path, permanent=False)

    def _shortcut_delete(self):
        """Permanently deletes the currently previewed image."""
        path = (self.preview_pane.controller.get_current_path()
                if self.preview_pane else None)
        if path:
            self._handle_permanent_delete(path)

    def _open_location_in_bagheeraview(self, path):
        """
        Opens the folder containing the given file in the main window and
        positions the thumbnail grid on that image.

        Args:
            path (str): Path of the file whose location is opened.
        """
        self.main_win.locate_path_in_view(path)

    def _run_region_detection(self, detect_type):
        """
        Runs automatic region detection on the preview image.

        Newly detected regions are merged with the existing ones, discarding
        overlapping duplicates, and the user is asked to name each of them.

        Args:
            detect_type (str): Detection kind, one of "faces", "pets" or any
                other value (which results in no detection).
        """
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
        """
        Computes the Intersection over Union (IoU) of two bounding boxes.

        Args:
            boxA (dict): First box with keys ``x``, ``y``, ``w`` and ``h``.
            boxB (dict): Second box with keys ``x``, ``y``, ``w`` and ``h``.

        Returns:
            float: The IoU value in the range [0, 1].
        """
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
        """No-op implementation required by the ImagePane API."""
        pass

    def on_metadata_changed(self, path, metadata=None):
        """No-op implementation required by the ImagePane API."""
        pass

    def on_controller_list_updated(self, index):
        """No-op implementation required by the ImagePane API."""
        pass

    def update_view_for_pane(self, pane, resize_win=False):
        """
        Refreshes the pixmap shown on the given pane's canvas.

        Args:
            pane (ImagePane): Pane whose canvas is updated.
            resize_win (bool, optional): Unused, kept for API compatibility.
        """
        pixmap = pane.controller.get_display_pixmap()
        if not pixmap.isNull():
            pane.canvas.setPixmap(pixmap)
            pane.canvas.adjustSize()

    def load_and_fit_image_for_pane(self, pane, restore_config=None):
        """No-op implementation required by the ImagePane API."""
        pass

    def reset_inactivity_timer(self):
        """No-op implementation required by the ImagePane API."""
        pass

    def sync_filmstrip_selection(self, index):
        """No-op implementation required by the ImagePane API."""
        pass

    def _get_clicked_face_for_pane(self, pane, pos):
        """
        Returns the face region under the given canvas position, if any.

        Args:
            pane (ImagePane): The pane whose regions are inspected.
            pos (QPoint): Position in canvas coordinates.

        Returns:
            dict or None: The clicked face/pet region or ``None``.
        """
        if pane is None:
            return None
        for face in pane.controller.faces:
            rect = pane.canvas.map_from_source(face)
            if rect.contains(pos):
                return face
        return None

    def _get_clicked_face(self, pos):
        """
        Returns the face region under the given preview canvas position.

        This method completes the ImagePane/ImageViewer API expected by the
        FaceCanvas so that double-clicking a region can zoom to it.

        Args:
            pos (QPoint): Position in canvas coordinates.

        Returns:
            dict or None: The clicked face/pet region or ``None``.
        """
        return self._get_clicked_face_for_pane(self.preview_pane, pos)

    @property
    def zoom_manager(self):
        """
        Zoom manager of the preview pane (ImagePane API compatibility).

        Returns:
            ZoomManager or None: The preview pane zoom manager.
        """
        return self.preview_pane.zoom_manager if self.preview_pane else None

    def _update_person_recognition_for_face(self, face_region, new_tag):
        """
        No-op implementation required by the FaceCanvas drawing flow.

        Person recognition is a viewer-level feature; the Similar Images
        dialog relies on the main window for that workflow.

        Args:
            face_region (dict): The face region data.
            new_tag (str): The name assigned to the face.
        """
        pass

    def rename_face(self, face):
        """
        Opens a dialog to rename a specific region of the preview image.

        The region type determines which name history is used, and the
        resulting tag is stored in the image metadata.

        Args:
            face (dict): Region whose name will be changed.
        """
        if not face:
            return

        from .imageviewer import FaceNameDialog

        controller = self.preview_pane.controller
        canvas = self.preview_pane.canvas
        region_type = face.get('type', 'Face')

        history_list = []
        if self.main_win:
            if region_type == "Pet":
                history_list = self.main_win.pet_names_history
            elif region_type == "Body":
                history_list = self.main_win.body_names_history
            elif region_type == "Object":
                history_list = self.main_win.object_names_history
            elif region_type == "Landmark":
                history_list = self.main_win.landmark_names_history
            else:  # Face
                history_list = self.main_win.face_names_history

        history = history_list if self.main_win else []
        current_name = face.get('name', '')

        new_full_tag, updated_history, ok = FaceNameDialog.get_name(
            self, history, current_name, main_win=self.main_win,
            region_type=region_type, title=UITexts.RENAME_REGION)

        if not (ok and new_full_tag) or new_full_tag == current_name:
            return

        # Remove the old tag if it is not used by any other region.
        if current_name:
            has_other = any(f.get('name') == current_name
                            for f in controller.faces if f is not face)
            if not has_other:
                controller.toggle_tag(current_name, False)

        face['name'] = new_full_tag
        if self.main_win:
            if region_type == "Pet":
                self.main_win.pet_names_history = updated_history
            elif region_type == "Body":
                self.main_win.body_names_history = updated_history
            elif region_type == "Object":
                self.main_win.object_names_history = updated_history
            elif region_type == "Landmark":
                self.main_win.landmark_names_history = updated_history
            else:  # Face
                self.main_win.face_names_history = updated_history

        try:
            controller.save_faces()
            controller.toggle_tag(new_full_tag, True)
            if region_type == "Face":
                self._update_person_recognition_for_face(face, new_full_tag)
        except Exception as e:
            QMessageBox.critical(self, UITexts.ERROR, str(e))

        if canvas:
            canvas.update()

    def toggle_fullscreen(self):
        """No-op implementation required by the ImagePane API."""
        pass

    def wheelEvent(self, event):
        """
        Zooms the preview image when the wheel is rotated with Ctrl pressed.

        Args:
            event (QWheelEvent): The wheel event to handle.
        """
        if event.modifiers() & Qt.ControlModifier and self.preview_pane:
            focus_pos = self.preview_pane.mapFromGlobal(event.globalPosition().toPoint())
            if event.angleDelta().y() > 0:
                self.preview_pane.zoom_manager.zoom(1.1, focus_point=focus_pos)
            else:
                self.preview_pane.zoom_manager.zoom(0.9, focus_point=focus_pos)
            event.accept()
        else:
            super().wheelEvent(event)

    def _dialog_key_matches(self, event, action):
        """Checks whether a key event matches the configured dialog shortcut.

        The shortcut is read from the main window configuration (falling back
        to the defaults when no main window is present), so the dialog keys
        stay configurable through the "Configure keyboard shortcuts" dialog.

        Args:
            event (QKeyEvent): The key event to test.
            action (str): One of the keys in ``DIALOG_ACTIONS``.

        Returns:
            bool: ``True`` when the event's key and modifiers match the
            configured shortcut.
        """
        key, mods = self._dialog_shortcut(action)
        mods_mask = (Qt.ShiftModifier | Qt.ControlModifier
                     | Qt.AltModifier | Qt.MetaModifier)
        return (event.key() == key
                and event.modifiers() & mods_mask == mods)

    def _dialog_shortcut(self, action):
        """Returns the ``(key, modifiers)`` tuple configured for an action."""
        main_win = getattr(self, "main_win", None)
        getter = getattr(main_win, "get_dialog_shortcut", None)
        if getter is not None:
            return getter(action)
        return DEFAULT_DIALOG_SHORTCUTS.get(
            action, (Qt.Key_unknown, Qt.NoModifier))

    def keyPressEvent(self, event):
        """
        Handles the keyboard shortcuts used for zooming the preview image
        and for the context-menu actions.

        Supported keys: ``sim_zoom_in``/``sim_zoom_out``/``sim_reset_zoom``
        (zoom in, zoom out and reset zoom) and ``sim_toggle_fit`` (toggle
        fit-to-screen), all configurable through the "Configure keyboard
        shortcuts" dialog. ``=`` is kept as a hard-coded alias of the zoom-in
        key. The context-menu actions (quick tags, detection, show faces,
        properties and trash/delete) use the viewer shortcuts configured in
        the main window.

        Args:
            event (QKeyEvent): The key event to handle.
        """
        key = event.key()
        if self._dialog_key_matches(event, "sim_zoom_in") \
                or key == Qt.Key_Equal:
            if self.preview_pane:
                self.preview_pane.zoom_manager.zoom(1.1)
            event.accept()
        elif self._dialog_key_matches(event, "sim_zoom_out"):
            if self.preview_pane:
                self.preview_pane.zoom_manager.zoom(0.9)
            event.accept()
        elif self._dialog_key_matches(event, "sim_reset_zoom"):
            if self.preview_pane:
                self.preview_pane.zoom_manager.zoom(1.0, reset=True)
            event.accept()
        elif self._dialog_key_matches(event, "sim_toggle_fit"):
            if self.preview_pane:
                self.preview_pane.zoom_manager.toggle_fit_to_screen()
            event.accept()
        else:
            modifiers = event.modifiers() & (
                Qt.ShiftModifier | Qt.ControlModifier |
                Qt.AltModifier | Qt.MetaModifier)
            action = self._menu_shortcut_keys.get((key, modifiers))
            handler = self._menu_handlers.get(action)
            if handler is not None:
                handler()
                event.accept()
            else:
                super().keyPressEvent(event)

    def done(self, r):
        """
        Stops the search worker and cleans up the preview pane on close.

        Args:
            r (int): Result code passed by the dialog's close mechanism.
        """
        if self.worker and self.worker.isRunning():
            self.worker.stop()
        if self.preview_pane:
            self.preview_pane.cleanup()
        super().done(r)
