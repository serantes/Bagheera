"""
Duplicate Management Dialog Module for Bagheera.

This module implements the DuplicateManagerDialog, a specialized interface
for comparing and resolving duplicate image pairs identified by the
DuplicateDetector. It provides side-by-side viewing with synchronized
zooming and scrolling.

Classes:
    DuplicateManagerDialog: A dialog to review and manage duplicate image pairs.
"""
import os
import subprocess
from datetime import datetime
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QSplitter, QWidget, QMessageBox, QApplication, QMenu,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView
)
from PySide6.QtGui import QIcon, QImageReader, QImage, QDesktopServices
from PySide6.QtCore import Qt, QTimer, QUrl
from .imageviewer import ImagePane
from .constants import APP_CONFIG, UITexts
from .propertiesdialog import PropertiesDialog


class DuplicateManagerDialog(QDialog):
    """
    A dialog to review and manage duplicate image pairs found by the detector.
    """
    def __init__(self, duplicates, duplicate_cache, main_win, review_mode=False):
        """
        Initializes the DuplicateManagerDialog.

        Args:
            duplicates (list): List of DuplicateResult tuples.
            duplicate_cache (DuplicateCache): The persistent hash/exception cache.
            main_win (MainWindow): Reference to the main application window.
            review_mode (bool, optional): If True, shows previously ignored duplicates.
        """
        super().__init__(main_win)
        self.duplicates = duplicates  # List of DuplicateResult
        self.cache = duplicate_cache
        self.main_win = main_win
        self.review_mode = review_mode

        self.active_pane = None  # Track the focused pane
        self.current_dup_pair = None  # Stores the current DuplicateResult object
        self.panes_linked = True  # Default to linked
        self._user_link_preference = True  # Persists user intent
        self._is_syncing = False  # Guard to prevent recursion during synchronization

        self.setWindowTitle(UITexts.DUPLICATE_MANAGER_TITLE)
        self.resize(1000, 700)

        self._setup_ui()
        self._populate_list()

        if self.main_win and hasattr(self.main_win, 'fs_watcher'):
            self.main_win.fs_watcher.file_deleted.connect(
                self._on_file_deleted_externally)
            self.main_win.fs_watcher.file_moved.connect(
                self._on_file_moved_externally)

        if self.duplicates:
            self.table_widget.setCurrentCell(0, 0)

    def _setup_ui(self):
        """Sets up the user interface components for the duplicate manager."""
        layout = QHBoxLayout(self)

        # Left side: List of pairs
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)

        header_layout = QHBoxLayout()
        header_layout.addWidget(QLabel(UITexts.DUPLICATE_LIST_HEADER))
        self.counter_lbl = QLabel()
        self.counter_lbl.setStyleSheet("color: #3498db; font-weight: bold;")
        header_layout.addStretch()
        header_layout.addWidget(self.counter_lbl)
        left_layout.addLayout(header_layout)

        self.table_widget = QTableWidget()
        if self.review_mode:
            columns = 3
            self.table_widget.setColumnCount(columns)
            self.table_widget.setHorizontalHeaderLabels(
                [UITexts.IGNORED_DATE, "%", UITexts.CONTEXT_MENU_OPEN])
            self.table_widget.horizontalHeader().setSectionResizeMode(
                0, QHeaderView.ResizeToContents)
            self.table_widget.horizontalHeader().setSectionResizeMode(
                1, QHeaderView.ResizeToContents)
            self.table_widget.horizontalHeader().setSectionResizeMode(
                2, QHeaderView.Stretch)
        else:
            columns = 2
            self.table_widget.setColumnCount(columns)
            self.table_widget.setHorizontalHeaderLabels(
                ["%", UITexts.CONTEXT_MENU_OPEN])
            self.table_widget.horizontalHeader().setSectionResizeMode(
                0, QHeaderView.ResizeToContents)
            self.table_widget.horizontalHeader().setSectionResizeMode(
                1, QHeaderView.Stretch)

        self.table_widget.verticalHeader().setVisible(False)
        self.table_widget.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table_widget.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table_widget.currentCellChanged.connect(self._on_cell_changed)
        self.table_widget.setSortingEnabled(True)
        left_layout.addWidget(self.table_widget)

        # Right side: Comparison area
        self.splitter = QSplitter(Qt.Vertical)

        # Top area: Side by side images
        self.comparison_widget = QWidget()
        comp_layout = QHBoxLayout(self.comparison_widget)

        # Left Image Panel
        self.left_pane_widget = self._create_comparison_pane_widget()
        comp_layout.addWidget(self.left_pane_widget)

        # Right Image Panel
        self.right_pane_widget = self._create_comparison_pane_widget()
        comp_layout.addWidget(self.right_pane_widget)

        # Buttons Area
        button_widget = QWidget()
        btn_layout = QHBoxLayout(button_widget)

        self.btn_del_left = QPushButton(
            QIcon.fromTheme("user-trash"), UITexts.DUPLICATE_DELETE_LEFT)
        self.btn_del_left.clicked.connect(self._delete_left)

        self.btn_del_right = QPushButton(
            QIcon.fromTheme("user-trash"), UITexts.DUPLICATE_DELETE_RIGHT)
        self.btn_del_right.clicked.connect(self._delete_right)

        self.btn_link_panes = QPushButton(
            QIcon.fromTheme("object-link"), UITexts.VIEWER_MENU_LINK_PANES)
        self.btn_link_panes.setCheckable(True)
        self.btn_link_panes.setChecked(self.panes_linked)
        self.btn_link_panes.clicked.connect(self._toggle_link_panes)

        self.btn_keep_both = QPushButton(
            QIcon.fromTheme("emblem-important"), UITexts.DUPLICATE_KEEP_BOTH)
        self.btn_keep_both.clicked.connect(self._keep_both)

        self.btn_skip = QPushButton(UITexts.DUPLICATE_SKIP)
        self.btn_skip.clicked.connect(self._skip)

        btn_layout.addWidget(self.btn_del_left)
        btn_layout.addWidget(self.btn_del_right)
        btn_layout.addWidget(self.btn_link_panes)
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_keep_both)
        btn_layout.addWidget(self.btn_skip)

        if self.review_mode:
            self.btn_keep_both.hide()
            self.btn_skip.setText(UITexts.DUPLICATE_REMOVE_IGNORED)
            self.btn_skip.setIcon(QIcon.fromTheme("list-remove"))

        self.similarity_lbl = QLabel()
        self.similarity_lbl.setAlignment(Qt.AlignCenter)
        self.similarity_lbl.setMinimumHeight(30)
        self.similarity_lbl.setStyleSheet(
            "font-weight: bold; color: #f39c12; font-size: 15px; "
            "background-color: #222; border: 1px solid #444; border-radius: 4px;")

        main_right_layout = QVBoxLayout()
        main_right_layout.addWidget(self.comparison_widget, 1)
        main_right_layout.addWidget(self.similarity_lbl)
        main_right_layout.addWidget(button_widget)

        right_container = QWidget()
        right_container.setLayout(main_right_layout)

        layout.addWidget(left_panel, 1)
        layout.addWidget(right_container, 4)

        # Store references to the actual ImagePane instances
        self.left_pane = self.left_pane_widget.pane
        self.right_pane = self.right_pane_widget.pane

    def closeEvent(self, event):
        """
        Handles the dialog close event.

        Disconnects external signals from the file system watcher and
        performs cleanup on the image panes to free resources.
        """
        if self.main_win and hasattr(self.main_win, 'fs_watcher'):
            try:
                self.main_win.fs_watcher.file_deleted.disconnect(
                    self._on_file_deleted_externally)
                self.main_win.fs_watcher.file_moved.disconnect(
                    self._on_file_moved_externally)
            except (RuntimeError, TypeError):
                pass

        if hasattr(self, 'left_pane') and self.left_pane:
            self.left_pane.cleanup()
        if hasattr(self, 'right_pane') and self.right_pane:
            self.right_pane.cleanup()
        super().closeEvent(event)

    def resizeEvent(self, event):
        """
        Handles the dialog resize event.

        Triggers a recalculation of the image scaling to ensure they fit
        optimally within the new available space.
        """
        super().resizeEvent(event)  # Call base class resizeEvent
        self._apply_linked_scaling()

    def _apply_linked_scaling(self):
        """Applies custom linked scaling logic to both panels."""
        if not self.left_pane or not self.right_pane:
            return

        # Ensure images are loaded to get original dimensions.
        # This also ensures pane.controller.pixmap_original is populated.
        self.left_pane.controller.load_image()
        self.right_pane.controller.load_image()

        p_l = self.left_pane.controller.pixmap_original
        p_r = self.right_pane.controller.pixmap_original

        # If panels are not linked or any image is null, adjust independently
        if not self.panes_linked or p_l.isNull() or p_r.isNull():
            self._is_syncing = True  # Avoid recursion in _sync_zoom
            try:
                self.load_and_fit_image_for_pane(self.left_pane)
                self.load_and_fit_image_for_pane(self.right_pane)
            finally:
                self._is_syncing = False
            return

        self._is_syncing = True
        try:
            # Get original dimensions
            w_l_orig, h_l_orig = p_l.width(), p_l.height()
            w_r_orig, h_r_orig = p_r.width(), p_r.height()

            # Get available viewport size for each panel
            viewport_l = self.left_pane.scroll_area.viewport()
            viewport_r = self.right_pane.scroll_area.viewport()
            vp_w_l, vp_h_l = viewport_l.width(), viewport_l.height()
            vp_w_r, vp_h_r = viewport_r.width(), viewport_r.height()

            # Determine the highest resolution image
            res_l = w_l_orig * h_l_orig
            res_r = w_r_orig * h_r_orig

            if res_l >= res_r:
                high_res_pane = self.left_pane
                low_res_pane = self.right_pane
                high_res_w, high_res_h = w_l_orig, h_l_orig
                low_res_w, low_res_h = w_r_orig, h_r_orig
                vp_w_high, vp_h_high = vp_w_l, vp_h_l
            else:
                high_res_pane = self.right_pane
                low_res_pane = self.left_pane
                high_res_w, high_res_h = w_r_orig, h_r_orig
                low_res_w, low_res_h = w_l_orig, h_l_orig
                vp_w_high, vp_h_high = vp_w_r, vp_h_r

            # Calculate zoom factor for high-res image to fit its panel
            zoom_high = 1.0
            if high_res_w > 0 and high_res_h > 0:
                zoom_high = min(vp_w_high / high_res_w, vp_h_high / high_res_h)

            high_res_pane.controller.zoom_factor = zoom_high
            high_res_pane.update_view(resize_win=False)

            # Calculate and apply zoom for low-res image relative to high-res
            zoom_low = 1.0
            if high_res_w > 0 and high_res_h > 0:
                relative_scale_factor = min(low_res_w / high_res_w,
                                            low_res_h / high_res_h)
                zoom_low = zoom_high * relative_scale_factor
            low_res_pane.controller.zoom_factor = zoom_low
            low_res_pane.update_view(resize_win=False)
        finally:
            self._is_syncing = False

    def wheelEvent(self, event):
        """
        Handles mouse wheel events for zooming.

        If the Control modifier is held, zooms the active image pane
        centered on the mouse cursor position.
        """
        if event.modifiers() & Qt.ControlModifier and self.active_pane:
            # Calculate the focus point relative to the active pane.
            focus_pos = self.active_pane.mapFromGlobal(event.globalPosition().toPoint())
            if event.angleDelta().y() > 0:
                self.active_pane.zoom_manager.zoom(1.1, focus_point=focus_pos)
            else:
                self.active_pane.zoom_manager.zoom(0.9, focus_point=focus_pos)
            event.accept()
        else:
            super().wheelEvent(event)

    def keyPressEvent(self, event):
        """
        Handles keyboard shortcuts for navigation and actions.

        Provides quick access to deletion (U/I), ignore (O), and skip (P),
        as well as standard zoom controls (Z/+/ -).
        """
        key = event.key()
        if key == Qt.Key_U:
            self._delete_left()
            event.accept()
            return
        elif key == Qt.Key_I:
            self._delete_right()
            event.accept()
            return
        elif key == Qt.Key_O:
            if not self.review_mode:
                self._keep_both()
                event.accept()
            return
        elif key == Qt.Key_P:
            self._skip()
            event.accept()
            return

        if not self.active_pane:
            super().keyPressEvent(event)
            return

        if key == Qt.Key_Plus or key == Qt.Key_Equal:
            self.active_pane.zoom_manager.zoom(1.1)
        elif key == Qt.Key_Minus:
            self.active_pane.zoom_manager.zoom(0.9)
        elif key == Qt.Key_Z:
            self.active_pane.zoom_manager.zoom(reset=True)
        else:
            super().keyPressEvent(event)

    # --- Viewer API Implementation for ImagePane ---

    def set_active_pane(self, pane):
        """
        Sets the currently focused pane for synchronization reference.

        Args:
            pane (ImagePane): The pane that gained focus.
        """
        self.active_pane = pane
        self.update_highlight()

    def update_highlight(self):
        """Applies visual feedback (border) to the active pane."""
        for pw in [self.left_pane_widget, self.right_pane_widget]:
            pw.setStyleSheet("border: 2px solid #3498db;" if pw.pane == self.active_pane
                             else "border: 2px solid transparent;")

    def on_metadata_changed(self, path, metadata=None):
        """
        Updates labels when image metadata is modified.

        Args:
            path (str): The file path.
            metadata (dict, optional): The updated metadata.
        """
        # Find the widget displaying this path and update its info
        for pw in [self.left_pane_widget, self.right_pane_widget]:
            if pw.pane.controller.get_current_path() == path:
                size_str = self._format_size(os.path.getsize(path))
                pw.info_lbl.setText(UITexts.DUPLICATE_INFO_FORMAT.format(
                    size=size_str,
                    width=pw.pane.controller.pixmap_original.width(),
                    height=pw.pane.controller.pixmap_original.height()))

        if self.main_win:
            self.main_win.update_metadata_for_path(path, metadata)

    def on_controller_list_updated(self, index):
        """Required by ImagePane API, no-op in this dialog."""
        pass

    def update_view_for_pane(self, pane, resize_win=False):
        """
        Refreshes the canvas for a specific pane.

        Args:
            pane (ImagePane): The pane to update.
            resize_win (bool): Ignored in this context.
        """
        pixmap = pane.controller.get_display_pixmap()
        if not pixmap.isNull():
            pane.canvas.setPixmap(pixmap)
            pane.canvas.adjustSize()

    def load_and_fit_image_for_pane(self, pane, restore_config=None):
        """
        Loads and calculates initial zoom to fit the pane viewport.

        Args:
            pane (ImagePane): The target pane.
            restore_config (dict, optional): Unused here.
        """
        success, _ = pane.controller.load_image()
        if success:
            viewport = pane.scroll_area.viewport()
            w, h = viewport.width(), viewport.height()
            # If not yet laid out, defer to next event loop
            if w <= 1 or h <= 1:
                QTimer.singleShot(0, lambda: self.load_and_fit_image_for_pane(pane))
                return
            pane.zoom_manager.calculate_initial_zoom(w, h, True)
            self.update_view_for_pane(pane)

    def reset_inactivity_timer(self):
        """Required by ImagePane API, no-op in this dialog."""
        pass

    def sync_filmstrip_selection(self, index):
        """Required by ImagePane API, no-op in this dialog."""
        pass

    def _get_clicked_face_for_pane(self, pane, pos):
        """Required by ImagePane API, no-op in this dialog."""
        return None

    def rename_face(self, face):
        """Required by ImagePane API, no-op in this dialog."""
        pass

    def toggle_fullscreen(self):
        """Required by ImagePane API, no-op in this dialog."""
        pass

    def _create_comparison_pane_widget(self):
        """
        Factory method to create a pane widget containing an ImagePane and info labels.
        """
        widget = QWidget()
        v_layout = QVBoxLayout(widget)
        v_layout.setContentsMargins(0, 0, 0, 0)

        info_lbl = QLabel()
        info_lbl.setAlignment(Qt.AlignCenter)
        info_lbl.setStyleSheet("font-weight: bold; color: #aaa;")
        v_layout.addWidget(info_lbl)

        # Create ImagePane
        pane = ImagePane(self, self.main_win.cache, [], 0, None, 0)
        pane.setContextMenuPolicy(Qt.CustomContextMenu)
        pane.controller.show_faces = False  # Disable showing and adding areas
        pane.customContextMenuRequested.connect(self._show_pane_context_menu)
        v_layout.addWidget(pane)

        # Attach references
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

        # Connect signals for synchronization
        pane.scrolled.connect(self._sync_scroll)
        pane.zoom_manager.zoomed.connect(self._sync_zoom)
        pane.activated.connect(self._on_pane_activated)
        return widget

    def _populate_list(self):
        """Fills the table widget with the list of duplicate results."""
        self.table_widget.setSortingEnabled(False)
        self.table_widget.blockSignals(True)
        self.table_widget.setRowCount(0)
        for i, dup in enumerate(self.duplicates):
            name1 = os.path.basename(dup.path1)
            name2 = os.path.basename(dup.path2)

            row = self.table_widget.rowCount()
            self.table_widget.insertRow(row)

            if self.review_mode:
                # Column 0: Ignored Date
                ts = dup.timestamp if hasattr(dup, 'timestamp') and dup.timestamp else 0
                date_str = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M") \
                    if ts else "-"
                date_item = QTableWidgetItem(date_str)
                # Store original index here for _load_pair
                date_item.setData(Qt.UserRole, i)
                date_item.setTextAlignment(Qt.AlignCenter)
                self.table_widget.setItem(row, 0, date_item)
                col_offset = 1
            else:
                col_offset = 0

            # Similarity column (using DisplayRole with int for numerical sorting).
            sim_item = QTableWidgetItem()
            sim_item.setData(Qt.DisplayRole, dup.similarity
                             if dup.similarity is not None else 0)
            sim_item.setTextAlignment(Qt.AlignCenter)
            if not self.review_mode:
                sim_item.setData(Qt.UserRole, i)

            # Column 1: File names
            names_item = QTableWidgetItem(f"{name1} ↔ {name2}")

            self.table_widget.setItem(row, col_offset, sim_item)
            self.table_widget.setItem(row, col_offset + 1, names_item)

        self.counter_lbl.setText(str(len(self.duplicates)))
        self.table_widget.blockSignals(False)
        self.table_widget.setSortingEnabled(True)
        self.table_widget.sortItems(0, Qt.DescendingOrder)

    def _on_cell_changed(self, row, col, prev_row, prev_col):
        """Slot triggered when the selected row in the pairs table changes."""
        if row >= 0:
            self._load_pair(row)

    def _load_pair(self, row):
        """
        Loads the duplicate pair corresponding to the specified table row.
        """
        if row < 0 or row >= self.table_widget.rowCount():
            return

        # Get the real index of the duplicates list stored in the UserRole of
        # the item.
        item = self.table_widget.item(row, 0)
        if not item:
            return
        original_index = item.data(Qt.UserRole)
        dup = self.duplicates[original_index]
        self.current_dup_pair = dup  # Store the original pair

        # Update similarity label
        similarity_color = "#f39c12"  # Default (amber)
        if dup.similarity is not None:
            if dup.similarity == 100:
                similarity_color = "#2ecc71"  # Green
            elif dup.similarity < 80:
                similarity_color = "#e74c3c"  # Red

            self.similarity_lbl.setText(f"{dup.similarity}% Similarity")
            self.similarity_lbl.setStyleSheet(
                f"font-weight: bold; color: {similarity_color}; "
                "font-size: 12px; margin-top: 5px;")
            self.similarity_lbl.show()
        else:
            self.similarity_lbl.hide()

        # Get paths and their components
        path_left = dup.path1
        path_right = dup.path2

        filename_left = os.path.basename(path_left)
        dir_left = os.path.dirname(path_left)
        filename_right = os.path.basename(path_right)
        dir_right = os.path.dirname(path_right)

        # Determine colors for comparison
        green_color = "#2ecc71"  # Green for match
        red_color = "#e74c3c"    # Red for mismatch

        filename_color = green_color if filename_left == filename_right else red_color
        dir_color = green_color if dir_left == dir_right else red_color

        # Determine which path goes to which pane based on mtime
        mtime1 = os.path.getmtime(path_left) if os.path.exists(path_left) else 0
        mtime2 = os.path.getmtime(path_right) if os.path.exists(path_right) else 0

        # Recent image to the left, older to the right
        if mtime1 >= mtime2:
            dis_l = self._set_pane_data(
                self.left_pane_widget, path_left, filename_color,
                dir_color, filename_left, dir_left)
            dis_r = self._set_pane_data(
                self.right_pane_widget, path_right, filename_color,
                dir_color, filename_right, dir_right)
        else:
            dis_l = self._set_pane_data(
                self.left_pane_widget, path_right, filename_color,
                dir_color, filename_right, dir_right)
            dis_r = self._set_pane_data(
                self.right_pane_widget, path_left, filename_color,
                dir_color, filename_left, dir_left)

        can_link = not (dis_l or dis_r)
        self.panes_linked = self._user_link_preference and can_link
        self.btn_link_panes.setEnabled(can_link)
        self.btn_link_panes.setChecked(self.panes_linked)

        # Compare resolutions and highlight the best one
        p_l = self.left_pane.controller.pixmap_original
        p_r = self.right_pane.controller.pixmap_original
        if not p_l.isNull() and not p_r.isNull():
            res_l = p_l.width() * p_l.height()
            res_r = p_r.width() * p_r.height()

            winner = 0  # 0: none, 1: left, 2: right
            if res_l > res_r:
                winner = 1
            elif res_r > res_l:
                winner = 2
            else:
                # Same resolution, compare file sizes
                try:
                    path_l = self.left_pane.controller.get_current_path()
                    path_r = self.right_pane.controller.get_current_path()
                    size_l = os.path.getsize(path_l)
                    size_r = os.path.getsize(path_r)
                    if size_l > size_r:
                        winner = 1
                    elif size_r > size_l:
                        winner = 2
                except (OSError, AttributeError):
                    pass

            if winner == 1:
                self.left_pane_widget.info_lbl.setStyleSheet(
                    "font-weight: bold; color: #2ecc71;")
                self.left_pane_widget.info_lbl.setText(
                    "✓ " + self.left_pane_widget.info_lbl.text())
                self.right_pane_widget.info_lbl.setStyleSheet(
                    "font-weight: bold; color: #aaa;")
            elif winner == 2:
                self.right_pane_widget.info_lbl.setStyleSheet(
                    "font-weight: bold; color: #2ecc71;")
                self.right_pane_widget.info_lbl.setText(
                    "✓ " + self.right_pane_widget.info_lbl.text())
                self.left_pane_widget.info_lbl.setStyleSheet(
                    "font-weight: bold; color: #aaa;")
            else:
                self.left_pane_widget.info_lbl.setStyleSheet(
                    "font-weight: bold; color: #aaa;")
                self.right_pane_widget.info_lbl.setStyleSheet(
                    "font-weight: bold; color: #aaa;")
        else:
            self.left_pane_widget.info_lbl.setStyleSheet(
                "font-weight: bold; color: #aaa;")
            self.right_pane_widget.info_lbl.setStyleSheet(
                "font-weight: bold; color: #aaa;")

        # Force view update and proportional scaling
        self._apply_linked_scaling()

    def _set_pane_data(self, pane_widget, path, filename_color, dir_color,
                       filename_text, dir_text) -> bool:
        """
        Updates an ImagePane and its labels with file data.

        Args:
            pane_widget (QWidget): The container widget for the pane.
            path (str): File path to load.
            filename_color (str): Hex color for filename label.
            dir_color (str): Hex color for directory label.
            filename_text (str): Name to display.
            dir_text (str): Directory path to display.

        Returns:
            bool: True if linked scaling should be disabled (e.g., animation).
        """
        pane = pane_widget.pane
        info_lbl = pane_widget.info_lbl
        filename_lbl = pane_widget.filename_lbl
        dir_lbl = pane_widget.dir_lbl

        if not os.path.exists(path):
            info_lbl.setText(UITexts.FILE_NOT_FOUND)
            pane.controller.update_list([], 0)  # Clear pane
            pane.controller.load_image()
            filename_lbl.setText("N/A")
            dir_lbl.setText("N/A")
            return True

        # Load image into pane's controller FIRST to get accurate pixmap state
        pane.controller.update_list([path], 0)
        pane.controller.load_image()

        # Metadata
        size_bytes = os.path.getsize(path)
        size_str = self._format_size(size_bytes)

        # Detection of animated images or invalid resolutions
        reader = QImageReader(path)
        is_animated = reader.supportsAnimation() and reader.imageCount() > 1
        is_invalid = (pane.controller.pixmap_original.isNull() or
                      not pane.controller.pixmap_original.size().isValid())
        disable_linking = is_animated or is_invalid

        # Update info labels
        if not pane.controller.pixmap_original.isNull():
            info_lbl.setText(UITexts.DUPLICATE_INFO_FORMAT.format(
                size=size_str,
                width=pane.controller.pixmap_original.width(),
                height=pane.controller.pixmap_original.height()))
        else:
            info_lbl.setText(f"{size_str} - N/A")

        filename_lbl.setText(filename_text)
        filename_lbl.setStyleSheet(
            f"font-size: 11px; font-weight: bold; color: {filename_color};")
        dir_lbl.setText(dir_text)
        dir_lbl.setStyleSheet(f"font-size: 9px; color: {dir_color};")
        return disable_linking

    def _show_pane_context_menu(self, pos):
        """
        Displays a context menu for the pane that requested it.

        Args:
            pos (QPoint): Local coordinates of the request.
        """
        pane = self.sender()
        path = pane.controller.get_current_path()
        if not path or not os.path.exists(path):
            return

        menu = QMenu(self)

        # Open with...
        open_menu = menu.addMenu(
            QIcon.fromTheme("document-open"), UITexts.CONTEXT_MENU_OPEN)
        self.main_win.populate_open_with_submenu(open_menu, path)

        # Open location
        action_open_default_app = menu.addAction(
            QIcon.fromTheme("system-run"),
            UITexts.CONTEXT_MENU_OPEN_DEFAULT_APP)
        # action_open_default_app.triggered.connect(
        #     lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(path))))
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

        # Clipboard
        clip_menu = menu.addMenu(
            QIcon.fromTheme("edit-copy"), UITexts.CONTEXT_MENU_CLIPBOARD)

        action_copy_image = clip_menu.addAction(
            QIcon.fromTheme("image-x-generic"), UITexts.VIEWER_MENU_COPY_IMAGE)
        action_copy_image.triggered.connect(
            lambda: QApplication.clipboard().setImage(QImage(path)))

        action_copy_path = clip_menu.addAction(
            QIcon.fromTheme("document-properties"), UITexts.VIEWER_MENU_COPY_PATH)
        action_copy_path.triggered.connect(
            lambda: QApplication.clipboard().setText(path))

        menu.addSeparator()

        # Trash / Delete
        action_trash = menu.addAction(
            QIcon.fromTheme("user-trash"), UITexts.CONTEXT_MENU_TRASH)
        action_trash.triggered.connect(
            lambda: self._handle_action(delete_path=path, permanent=False))

        action_delete = menu.addAction(
            QIcon.fromTheme("edit-delete"), UITexts.CONTEXT_MENU_DELETE)
        action_delete.triggered.connect(
            lambda: self._handle_permanent_delete(path))

        menu.addSeparator()

        # Properties
        action_props = menu.addAction(
            QIcon.fromTheme("document-properties"), UITexts.CONTEXT_MENU_PROPERTIES)
        action_props.triggered.connect(
            lambda: self._show_properties(path, pane))

        menu.exec(pane.mapToGlobal(pos))

    def _handle_permanent_delete(self, path):
        """
        Prompts for and executes permanent deletion of a file.

        Args:
            path (str): File path to delete.
        """
        confirm = QMessageBox(self)
        confirm.setIcon(QMessageBox.Warning)
        confirm.setText(UITexts.CONFIRM_DELETE_TEXT)
        confirm.setInformativeText(
            UITexts.CONFIRM_DELETE_INFO.format(os.path.basename(path)))
        confirm.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        confirm.setDefaultButton(QMessageBox.No)
        if confirm.exec() == QMessageBox.Yes:
            self._handle_action(delete_path=path, permanent=True)

    def _show_properties(self, path, pane):
        """
        Shows the file properties dialog for a pane's image.

        Args:
            path (str): File path.
            pane (ImagePane): The pane containing the image.
        """
        tags = pane.controller._current_tags
        rating = pane.controller._current_rating
        dlg = PropertiesDialog(
            path, initial_tags=tags, initial_rating=rating, parent=self)
        dlg.exec()

    def _on_pane_activated(self):
        """
        Handles pane activation to synchronize viewing state if linked.

        Ensures that the activated pane becomes the leader for synchronization.
        """
        # When a pane is activated, ensure its zoom/scroll is the reference for linking
        if self.panes_linked:
            active_pane = self.sender()  # The pane that emitted activated signal
            other_pane = self.left_pane \
                if active_pane == self.right_pane else self.right_pane
            self._sync_zoom(active_pane.controller.zoom_factor, source_pane=active_pane)
            # Need to get scroll position from active_pane and apply to other
            h_bar = active_pane.scroll_area.horizontalScrollBar()
            v_bar = active_pane.scroll_area.verticalScrollBar()
            x_pct = h_bar.value() / h_bar.maximum() if h_bar.maximum() > 0 else 0
            y_pct = v_bar.value() / v_bar.maximum() if v_bar.maximum() > 0 else 0
            other_pane.set_scroll_relative(x_pct, y_pct)

    def _sync_scroll(self, x_pct, y_pct):
        """
        Synchronizes scroll position between panes if linked.

        Args:
            x_pct (float): Horizontal scroll percentage.
            y_pct (float): Vertical scroll percentage.
        """
        if not self.panes_linked:
            return
        source_pane = self.sender()
        if source_pane == self.left_pane:
            self.right_pane.set_scroll_relative(x_pct, y_pct)
        elif source_pane == self.right_pane:
            self.left_pane.set_scroll_relative(x_pct, y_pct)

    def _sync_zoom(self, factor, source_pane=None):
        """
        Synchronizes zoom factor between panes if linked.

        Args:
            factor (float): New zoom factor.
            source_pane (ImagePane, optional): The leader pane.
        """
        if not self.panes_linked or self._is_syncing:
            return
        if source_pane is None:
            # Emitter is ZoomManager, its parent is ImagePane
            sender = self.sender()
            source_pane = sender.parent() if sender else None

        if not source_pane:
            return

        # Ensure both images are loaded before syncing zoom
        if self.left_pane.controller.pixmap_original.isNull() or \
           self.right_pane.controller.pixmap_original.isNull():
            return

        self._is_syncing = True
        try:
            p_l = self.left_pane.controller.pixmap_original
            p_r = self.right_pane.controller.pixmap_original

            w_l_orig, h_l_orig = p_l.width(), p_l.height()
            w_r_orig, h_r_orig = p_r.width(), p_r.height()

            if w_l_orig == 0 or h_l_orig == 0 or w_r_orig == 0 or h_r_orig == 0:
                return  # Avoid division by zero

            # Calculate original size relationship.
            # Use ratio of "master" (high-res) to "slave" (low-res)
            # to maintain relative size.
            res_l = w_l_orig * h_l_orig
            res_r = w_r_orig * h_r_orig

            if res_l >= res_r:  # Left is same or higher resolution
                high_res_w, high_res_h = w_l_orig, h_l_orig
                low_res_w, low_res_h = w_r_orig, h_r_orig
                high_res_pane = self.left_pane
                low_res_pane = self.right_pane
            else:  # Right is higher resolution
                high_res_w, high_res_h = w_r_orig, h_r_orig
                low_res_w, low_res_h = w_l_orig, h_l_orig
                high_res_pane = self.right_pane
                low_res_pane = self.left_pane

            # 'factor' is the new zoom factor of the source panel.
            # Apply this to the high-res panel, then calculate low-res zoom.
            if source_pane == high_res_pane:
                low_res_pane.controller.zoom_factor = factor * min(
                    low_res_w / high_res_w, low_res_h / high_res_h)
                low_res_pane.update_view(resize_win=False)
            else:  # source_pane == low_res_pane
                high_res_pane.controller.zoom_factor = factor / min(
                    low_res_w / high_res_w, low_res_h / high_res_h)
                high_res_pane.update_view(resize_win=False)
        finally:
            self._is_syncing = False

    def _format_size(self, size):
        """
        Formats a file size in bytes to a human-readable string.

        Args:
            size (int): Size in bytes.
        """
        for unit in ['B', 'KiB', 'MiB', 'GiB']:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TiB"

    def _delete_left(self):
        """Triggers deletion of the image in the left pane."""
        path_to_delete = self.left_pane.controller.get_current_path()
        if path_to_delete:
            self._handle_action(delete_path=path_to_delete)

    def _delete_right(self):
        """Triggers deletion of the image in the right pane."""
        path_to_delete = self.right_pane.controller.get_current_path()
        if path_to_delete:
            self._handle_action(delete_path=path_to_delete)

    def _toggle_link_panes(self):
        """Toggles the synchronized viewing state between panes."""
        self._user_link_preference = self.btn_link_panes.isChecked()
        self.panes_linked = self._user_link_preference
        if self.panes_linked:
            # When linking, synchronize the other pane to the active one
            # For simplicity, let's always sync right to left if linking is enabled
            active_pane = self.left_pane
            self._sync_zoom(active_pane.controller.zoom_factor, source_pane=active_pane)
            h_bar = active_pane.scroll_area.horizontalScrollBar()
            v_bar = active_pane.scroll_area.verticalScrollBar()
            x_pct = h_bar.value() / h_bar.maximum() if h_bar.maximum() > 0 else 0
            y_pct = v_bar.value() / v_bar.maximum() if v_bar.maximum() > 0 else 0
            self.right_pane.set_scroll_relative(x_pct, y_pct)

    def _on_file_deleted_externally(self, path):
        """
        Handles file deletion events from the FileSystemWatcher.

        Args:
            path (str): The deleted path.
        """
        path = os.path.abspath(path)

        # 1. Identify pairs to remove and clean up the pending DB
        pairs_to_remove = [d for d in self.duplicates
                           if d.path1 == path or d.path2 == path]
        if not pairs_to_remove:
            return

        for p in pairs_to_remove:
            self.cache.mark_as_pending(p.path1, p.path2, False)

        # 2. Update the local list
        self.duplicates = [d for d in self.duplicates if d not in pairs_to_remove]

        # 3. Refresh UI
        self._populate_list()
        if not self.duplicates:
            self.close()
        else:
            current_row = self.table_widget.currentRow()
            new_row = min(max(0, current_row), self.table_widget.rowCount() - 1)
            self.table_widget.selectRow(new_row)
            self.table_widget.setCurrentCell(new_row, 0)

    def _on_file_moved_externally(self, old_path, new_path):
        """
        Handles file move/rename events from the FileSystemWatcher.

        Args:
            old_path (str): Original path.
            new_path (str): Target path.
        """
        old_path = os.path.abspath(old_path)
        new_path = os.path.abspath(new_path)

        updated = False
        for i, d in enumerate(self.duplicates):
            if d.path1 == old_path or d.path2 == old_path:
                p1 = new_path if d.path1 == old_path else d.path1
                p2 = new_path if d.path2 == old_path else d.path2
                # Update the named tuple using _replace
                self.duplicates[i] = d._replace(path1=p1, path2=p2)
                updated = True

        if updated:
            current_row = self.table_widget.currentRow()
            self._populate_list()
            if current_row >= 0:
                new_row = min(current_row, self.table_widget.rowCount() - 1)
                self.table_widget.selectRow(new_row)
                self.table_widget.setCurrentCell(new_row, 0)

    def _keep_both(self):
        """Marks the current pair as an exception to ignore in future scans."""
        if self.current_dup_pair:
            self.cache.mark_as_exception(
                self.current_dup_pair.path1,
                self.current_dup_pair.path2,
                True,
                similarity=self.current_dup_pair.similarity
            )
        self._handle_action(skip=False, permanent=False)

    def _skip(self):
        """Skips the current pair without marking it as an exception."""
        if self.review_mode and self.current_dup_pair:
            self.cache.mark_as_exception(
                self.current_dup_pair.path1, self.current_dup_pair.path2, False)
            # Clear hashes so the detector treats them as new images and
            # forces a new comparison in the next scan. We use
            # clear_relationships=False to preserve other possible matches
            # already identified.
            self.cache.remove_hash_for_path(
                self.current_dup_pair.path1, clear_relationships=False)
            self.cache.remove_hash_for_path(
                self.current_dup_pair.path2, clear_relationships=False)
            self._handle_action(skip=False, permanent=False)
        else:
            self._handle_action(skip=True)

    def _handle_action(self, delete_path=None, skip=False, permanent=None):
        """
        Handles management actions (delete, skip, keep) for duplicate pairs.
        Updates the local list and the persistent databases.

        Args:
            delete_path (str, optional): Path to delete.
            skip (bool): Whether to skip without ignoring permanently.
            permanent (bool, optional): If True, deletes without trash.
        """
        current_row = self.table_widget.currentRow()
        if current_row < 0:
            return

        item = self.table_widget.item(current_row, 0)
        original_index = item.data(Qt.UserRole)

        # Get the pair before potentially popping it
        current_pair = self.duplicates[original_index]

        if delete_path:
            if permanent is not True:
                if APP_CONFIG.get("duplicate_confirm_delete", True):
                    reply = QMessageBox.question(
                        self, UITexts.CONFIRM_TRASH_TITLE,
                        UITexts.CONFIRM_TRASH_TEXT,
                        QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
                    if reply != QMessageBox.Yes:
                        return

            # Remove all pairs containing this path from the persistent pending DB
            # because the file will be gone.
            pairs_to_unmark = [d for d in self.duplicates
                               if d.path1 == delete_path or d.path2 == delete_path]
            for p in pairs_to_unmark:
                self.cache.mark_as_pending(p.path1, p.path2, False)

            self.main_win.delete_file_by_path(delete_path, permanent=permanent)
            if os.path.exists(delete_path):
                QMessageBox.warning(
                    self, UITexts.ERROR,
                    UITexts.ERROR_DELETING_FILE.format(delete_path))
                return

            # Remove all pairs containing this path because it no longer exists
            self.duplicates = [d for d in self.duplicates
                               if d.path1 != delete_path and d.path2 != delete_path]
        else:
            # Skip or KeepBoth:
            if not skip:  # "Keep Both" case
                # It's no longer pending, it's an exception (already marked in
                # _keep_both)
                self.cache.mark_as_pending(
                    current_pair.path1, current_pair.path2, False)
            # Note: if it's "Skip", we do NOT remove it from pending DB, so it stays
            # there for next time.
            if 0 <= original_index < len(self.duplicates):
                self.duplicates.pop(original_index)

        # Repopulate list widget to ensure all indices are correct and counter is
        # updated
        self._populate_list()

        # Try to restore selection to same position (or last item)
        if self.duplicates:
            new_row = min(current_row, self.table_widget.rowCount() - 1)
            self.table_widget.selectRow(new_row)
            self.table_widget.setCurrentCell(new_row, 0)
        else:
            self.close()
