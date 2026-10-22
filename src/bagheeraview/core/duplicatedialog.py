"""
Duplicate Management Dialog Module for Bagheera.

This module implements the DuplicateManagerDialog, a specialized interface
for comparing and resolving duplicate image pairs identified by the
DuplicateDetector. It provides side-by-side viewing with synchronized
zooming and scrolling.

Classes:
    DuplicateManagerDialog: A dialog to review and manage duplicate image pairs.
"""
import html
import os
import subprocess
from datetime import datetime
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QWidget, QMessageBox, QApplication, QMenu,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QTabWidget, QSlider, QSizePolicy
)
from PySide6.QtGui import (
    QBrush, QColor, QDesktopServices, QIcon, QImage, QImageReader,
    QKeySequence, QShortcut, QPixmap
)
from PySide6.QtCore import Qt, QTimer, QUrl
from .imageviewer import ImagePane
from .overlaycanvas import OverlayCanvas
from .constants import (
    APP_CONFIG, UITexts, DEFAULT_DIALOG_SHORTCUTS
)
from .propertiesdialog import PropertiesDialog


class DuplicateManagerDialog(QDialog):
    """
    A dialog to review and manage duplicate image pairs found by the detector.
    """

    # The dialog resolves its own keyboard shortcuts (deletion, etc.), so the
    # application-wide shortcut controller must not intercept those keys.
    handles_own_shortcuts = True

    # Default region type requested by the FaceCanvas API. The dialog never
    # offers region editing, but this value is read while drawing with the
    # middle mouse button, so it must exist.
    _next_region_type = "Face"

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
        self._can_link = True  # Whether linking is allowed for the current pair
        self._dirty = {"side": True, "overlay": True}  # Lazy update flags
        self._tab_shortcut = None  # Tab shortcut for the Overlay toggle mode

        self.setWindowTitle(UITexts.DUPLICATE_MANAGER_TITLE)
        self.resize(1000, 700)

        self._setup_ui()
        self._populate_list()
        self._setup_dialog_shortcuts()

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

        # Left side: List of pairs (always visible, outside any tab widget)
        left_panel = QWidget()
        left_panel.setMinimumWidth(260)
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

        # Right side: Main tabs + bottom action bar
        self.main_tabs = QTabWidget()
        self.main_tabs.setDocumentMode(True)

        # Tab 1: Side by Side comparison (existing panes)
        self.comparison_widget = QWidget()
        comp_layout = QHBoxLayout(self.comparison_widget)
        self.left_pane_widget = self._create_comparison_pane_widget()
        comp_layout.addWidget(self.left_pane_widget)
        self.right_pane_widget = self._create_comparison_pane_widget()
        comp_layout.addWidget(self.right_pane_widget)
        self.main_tabs.addTab(self.comparison_widget,
                              UITexts.DUPLICATE_TAB_SIDE_BY_SIDE)

        # Tab 2: Overlay comparison modes
        self.main_tabs.addTab(self._create_overlay_page(),
                              UITexts.DUPLICATE_TAB_OVERLAY)
        self.main_tabs.currentChanged.connect(self._on_main_tab_changed)

        # Right side: Comparison area
        # Bottom action bar: fixed, independent of the active tab
        self.btn_link_panes = QPushButton(
            QIcon.fromTheme("object-link"), UITexts.VIEWER_MENU_LINK_PANES)
        self.btn_link_panes.setCheckable(True)
        self.btn_link_panes.setChecked(self.panes_linked)
        self.btn_link_panes.clicked.connect(self._toggle_link_panes)
        self._set_button_shortcut_tooltip(self.btn_link_panes,
                                          UITexts.DUPLICATE_LINK_PANES_TOOLTIP,
                                          "dup_link_panes")

        self.btn_del_left = QPushButton(
            QIcon.fromTheme("user-trash"), UITexts.DUPLICATE_DELETE_LEFT)
        self.btn_del_left.clicked.connect(self._delete_left)
        self._set_button_shortcut_tooltip(self.btn_del_left,
                                          UITexts.DUPLICATE_DELETE_LEFT,
                                          "dup_delete_left")

        self.btn_del_right = QPushButton(
            QIcon.fromTheme("user-trash"), UITexts.DUPLICATE_DELETE_RIGHT)
        self.btn_del_right.clicked.connect(self._delete_right)
        self._set_button_shortcut_tooltip(self.btn_del_right,
                                          UITexts.DUPLICATE_DELETE_RIGHT,
                                          "dup_delete_right")

        self.btn_overwrite = QPushButton(
            QIcon.fromTheme("document-save-as"), UITexts.DUPLICATE_OVERWRITE)
        self.btn_overwrite.clicked.connect(self._overwrite_selected)
        self._set_button_shortcut_tooltip(self.btn_overwrite,
                                          UITexts.DUPLICATE_OVERWRITE_TOOLTIP,
                                          "dup_overwrite")

        self.btn_keep_both = QPushButton(
            QIcon.fromTheme("emblem-important"), UITexts.DUPLICATE_KEEP_BOTH)
        self.btn_keep_both.clicked.connect(self._keep_both)
        self._set_button_shortcut_tooltip(self.btn_keep_both,
                                          UITexts.DUPLICATE_KEEP_BOTH,
                                          "dup_keep_both")

        self.btn_skip = QPushButton(UITexts.DUPLICATE_SKIP)
        self.btn_skip.clicked.connect(self._skip)
        self._set_button_shortcut_tooltip(self.btn_skip,
                                          UITexts.DUPLICATE_SKIP,
                                          "dup_skip")

        bottom_bar = QWidget()
        bottom_bar.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        btn_layout = QHBoxLayout(bottom_bar)
        btn_layout.setContentsMargins(0, 0, 0, 0)
        btn_layout.addWidget(self.btn_link_panes)
        btn_layout.addWidget(self.btn_del_left)
        btn_layout.addWidget(self.btn_del_right)
        btn_layout.addWidget(self.btn_overwrite)
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_keep_both)
        btn_layout.addWidget(self.btn_skip)

        if self.review_mode:
            self.btn_keep_both.hide()
            self.btn_skip.setText(UITexts.DUPLICATE_REMOVE_IGNORED)
            self.btn_skip.setIcon(QIcon.fromTheme("list-remove"))
            self._set_button_shortcut_tooltip(self.btn_skip,
                                              UITexts.DUPLICATE_REMOVE_IGNORED,
                                              "dup_skip")

        main_right_layout = QVBoxLayout()
        main_right_layout.addWidget(self.main_tabs, 1)
        main_right_layout.addWidget(bottom_bar)

        right_container = QWidget()
        right_container.setLayout(main_right_layout)

        layout.addWidget(left_panel, 1)
        layout.addWidget(right_container, 4)

        # Store references to the actual ImagePane instances
        self.left_pane = self.left_pane_widget.pane
        self.right_pane = self.right_pane_widget.pane

    def _disconnect_fs_watcher(self):
        """
        Disconnects the file system watcher signals exactly once.

        Safe to call multiple times; subsequent calls are no-ops, which
        avoids libpyside warnings about failed disconnections.
        """
        if getattr(self, '_fs_signals_disconnected', False):
            return
        self._fs_signals_disconnected = True
        watcher = getattr(self.main_win, 'fs_watcher', None)
        if watcher is None:
            return
        for signal, slot in (
                (watcher.file_deleted, self._on_file_deleted_externally),
                (watcher.file_moved, self._on_file_moved_externally)):
            try:
                signal.disconnect(slot)
            except (RuntimeError, TypeError):
                pass

    def closeEvent(self, event):
        """
        Handles the dialog close event.

        Disconnects external signals from the file system watcher and
        performs cleanup on the image panes to free resources.
        """
        self._disconnect_fs_watcher()

        if hasattr(self, 'left_pane') and self.left_pane:
            self.left_pane.cleanup()
        if hasattr(self, 'right_pane') and self.right_pane:
            self.right_pane.cleanup()
        if hasattr(self, 'overlay_canvas'):
            self.overlay_canvas.set_pixmaps(QPixmap(), QPixmap())
        super().closeEvent(event)

    def resizeEvent(self, event):
        """
        Handles the dialog resize event.

        Triggers a recalculation of the image scaling only when the Side by
        Side tab is active; otherwise the view is marked dirty and refreshed
        lazily when the tab becomes active again.
        """
        super().resizeEvent(event)  # Call base class resizeEvent
        if self.main_tabs.currentIndex() == 0:
            self._apply_linked_scaling()
        else:
            self._dirty["side"] = True

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

        If the Control modifier is held and the visible tab is Side by Side,
        zooms the active image pane centered on the mouse cursor position.
        The Overlay tab handles its own wheel events inside the canvas.
        """
        if (event.modifiers() & Qt.ControlModifier
                and self.active_pane
                and self.main_tabs.currentIndex() == 0):
            # Calculate the focus point relative to the active pane.
            focus_pos = self.active_pane.mapFromGlobal(event.globalPosition().toPoint())
            if event.angleDelta().y() > 0:
                self.active_pane.zoom_manager.zoom(1.1, focus_point=focus_pos)
            else:
                self.active_pane.zoom_manager.zoom(0.9, focus_point=focus_pos)
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

    def _set_button_shortcut_tooltip(self, button, base_text, action):
        """Appends the configured shortcut to a button's tooltip.

        Args:
            button (QPushButton): The button whose tooltip is updated.
            base_text (str): The descriptive text shown before the shortcut.
            action (str): The dialog action whose shortcut is displayed.
        """
        key, mods = self._dialog_shortcut(action)
        try:
            mod_val = int(mods)
        except TypeError:
            mod_val = mods.value
        seq = QKeySequence(mod_val | key)
        shortcut_str = seq.toString(QKeySequence.NativeText)
        if shortcut_str:
            button.setToolTip(f"{base_text} ({shortcut_str})")
        else:
            button.setToolTip(base_text)

    def keyPressEvent(self, event):
        """
        Handles keyboard shortcuts for navigation and actions.

        Provides quick access to deletion (``dup_delete_left`` /
        ``dup_delete_right``), keep-both (``dup_keep_both``) and skip
        (``dup_skip``), as well as standard zoom controls
        (``dup_zoom_in``/``dup_zoom_out``/``dup_reset_zoom``). All of these
        keys are configurable through the "Configure keyboard shortcuts"
        dialog. ``Delete``/``Shift+Delete`` move the active pane's image to
        the trash or delete it permanently, reusing the global shortcuts.
        ``=`` is kept as a hard-coded alias of the zoom-in key.

        Args:
            event (QKeyEvent): The key event to handle.
        """
        key = event.key()
        if self._dialog_key_matches(event, "dup_delete_left"):
            self._delete_left()
            event.accept()
            return
        elif self._dialog_key_matches(event, "dup_delete_right"):
            self._delete_right()
            event.accept()
            return
        elif self._dialog_key_matches(event, "dup_keep_both"):
            if not self.review_mode:
                self._keep_both()
                event.accept()
            return
        elif self._dialog_key_matches(event, "dup_skip"):
            self._skip()
            event.accept()
            return
        elif self._dialog_key_matches(event, "dup_toggle_fit"):
            if self.main_tabs.currentIndex() == 1:
                self.overlay_canvas.toggle_fit_actual()
            elif self.active_pane:
                self.active_pane.zoom_manager.toggle_fit_to_screen()
            event.accept()
            return
        elif self._dialog_key_matches(event, "dup_swap_layers"):
            if self.main_tabs.currentIndex() == 1:
                self._swap_overlay_layers()
            event.accept()
            return
        elif self._dialog_key_matches(event, "dup_link_panes"):
            if self.main_tabs.currentIndex() == 0 and self.btn_link_panes.isEnabled():
                self.btn_link_panes.click()
            event.accept()
            return
        elif self._dialog_key_matches(event, "dup_overwrite"):
            self._overwrite_selected()
            event.accept()
            return
        elif key == Qt.Key_Delete:
            if event.modifiers() & Qt.ShiftModifier:
                self._shortcut_delete()
            else:
                self._shortcut_trash()
            event.accept()
            return

        # In the Overlay tab the zoom shortcuts do not depend on a pane.
        if self.main_tabs.currentIndex() == 1:
            if self._dialog_key_matches(event, "dup_zoom_in") \
                    or key == Qt.Key_Equal:
                self.overlay_canvas.zoom_view(1.1)
            elif self._dialog_key_matches(event, "dup_zoom_out"):
                self.overlay_canvas.zoom_view(0.9)
            elif self._dialog_key_matches(event, "dup_reset_zoom"):
                self._on_overlay_reset()
            else:
                super().keyPressEvent(event)
            return

        if not self.active_pane:
            super().keyPressEvent(event)
            return

        if self._dialog_key_matches(event, "dup_zoom_in") \
                or key == Qt.Key_Equal:
            self.active_pane.zoom_manager.zoom(1.1)
        elif self._dialog_key_matches(event, "dup_zoom_out"):
            self.active_pane.zoom_manager.zoom(0.9)
        elif self._dialog_key_matches(event, "dup_reset_zoom"):
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
        # Find the widget displaying this path and update its labels
        for pw in [self.left_pane_widget, self.right_pane_widget]:
            if pw.pane.controller.get_current_path() == path:
                size_str = self._format_size(os.path.getsize(path))
                pw.size_lbl.setText(
                    UITexts.DUPLICATE_SIZE_LABEL.format(size=size_str))
                pw.res_lbl.setText(UITexts.DUPLICATE_RESOLUTION_LABEL.format(
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
        for face in pane.controller.regions:
            rect = pane.canvas.map_from_source(face)
            if rect.contains(pos):
                return face
        return None

    def _get_clicked_face(self, pos):
        """
        Returns the face region under the given active pane canvas position.

        This method completes the ImagePane/ImageViewer API expected by the
        FaceCanvas so that double-clicking a region can zoom to it.

        Args:
            pos (QPoint): Position in canvas coordinates.

        Returns:
            dict or None: The clicked face/pet region or ``None``.
        """
        pane = self.active_pane or self.left_pane
        return self._get_clicked_face_for_pane(pane, pos)

    @property
    def zoom_manager(self):
        """
        Zoom manager of the active pane (ImagePane API compatibility).

        Returns:
            ZoomManager or None: The active pane zoom manager.
        """
        pane = self.active_pane or self.left_pane
        return pane.zoom_manager if pane else None

    def _update_person_recognition_for_face(self, face_region, new_tag):
        """
        No-op implementation required by the FaceCanvas drawing flow.

        Person recognition is a viewer-level feature; the duplicate
        management dialog only displays and compares images.

        Args:
            face_region (dict): The face region data.
            new_tag (str): The name assigned to the face.
        """
        pass

    def rename_face(self, face):
        """Required by ImagePane API, no-op in this dialog."""
        pass

    def toggle_faces(self):
        """Required by the FaceCanvas API, no-op in this dialog."""
        pass

    def set_next_region_type(self, region_type):
        """
        Required by the FaceCanvas API, no-op in this dialog.

        Args:
            region_type (str): Region type identifier (e.g. "Face").
        """
        pass

    def toggle_fullscreen(self):
        """Required by ImagePane API, no-op in this dialog."""
        pass

    def _create_comparison_pane_widget(self):
        """
        Factory method to create a pane widget containing an ImagePane and
        metadata labels arranged below the image (size, resolution, filename,
        directory).
        """
        widget = QWidget()
        v_layout = QVBoxLayout(widget)
        v_layout.setContentsMargins(0, 0, 0, 0)
        v_layout.setSpacing(2)

        # Create ImagePane (image area at the top)
        pane = ImagePane(self, self.main_win.cache, [], 0, None, 0)
        pane.setContextMenuPolicy(Qt.CustomContextMenu)
        pane.controller.show_regions = False  # Disable showing and adding areas
        pane.customContextMenuRequested.connect(self._show_pane_context_menu)
        v_layout.addWidget(pane, 1)

        # Metadata labels below the image, above the directory path
        size_lbl = QLabel()
        size_lbl.setAlignment(Qt.AlignCenter)
        size_lbl.setStyleSheet("font-size: 11px; font-weight: bold; color: #aaa;")
        v_layout.addWidget(size_lbl)

        res_lbl = QLabel()
        res_lbl.setAlignment(Qt.AlignCenter)
        res_lbl.setStyleSheet("font-size: 11px; font-weight: bold; color: #aaa;")
        v_layout.addWidget(res_lbl)

        filename_lbl = QLabel()
        filename_lbl.setAlignment(Qt.AlignCenter)
        filename_lbl.setStyleSheet("font-size: 11px; font-weight: bold;")
        v_layout.addWidget(filename_lbl)

        dir_lbl = QLabel()
        dir_lbl.setAlignment(Qt.AlignCenter)
        dir_lbl.setStyleSheet("font-size: 9px; color: #888;")
        v_layout.addWidget(dir_lbl)

        # Attach references
        widget.pane = pane
        widget.size_lbl = size_lbl
        widget.res_lbl = res_lbl
        widget.filename_lbl = filename_lbl
        widget.dir_lbl = dir_lbl

        # Connect signals for synchronization
        pane.scrolled.connect(self._sync_scroll)
        pane.zoom_manager.zoomed.connect(self._sync_zoom)
        pane.activated.connect(self._on_pane_activated)
        return widget

    def _create_overlay_page(self):
        """
        Builds the Overlay page: mode tabs, alignment tools and the shared
        OverlayCanvas used by all overlay sub-modes.
        """
        page = QWidget()
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(4)

        # Controls bar
        controls_bar = QWidget()
        controls_layout = QHBoxLayout(controls_bar)
        controls_layout.setContentsMargins(0, 0, 0, 0)

        self.btn_overlay_swap = QPushButton(
            QIcon.fromTheme("object-flip-horizontal"),
            UITexts.DUPLICATE_OVERLAY_SWAP)
        self.btn_overlay_swap.clicked.connect(self._swap_overlay_layers)
        self._set_button_shortcut_tooltip(self.btn_overlay_swap,
                                          UITexts.DUPLICATE_OVERLAY_SWAP_TOOLTIP,
                                          "dup_swap_layers")
        controls_layout.addWidget(self.btn_overlay_swap)

        self.btn_overlay_reset = QPushButton(
            QIcon.fromTheme("view-restore"), UITexts.DUPLICATE_OVERLAY_RESET)
        self.btn_overlay_reset.clicked.connect(self._on_overlay_reset)
        self._set_button_shortcut_tooltip(self.btn_overlay_reset,
                                          UITexts.DUPLICATE_OVERLAY_RESET_TOOLTIP,
                                          "dup_reset_zoom")
        controls_layout.addWidget(self.btn_overlay_reset)

        self.opacity_slider = QSlider(Qt.Horizontal)
        self.opacity_slider.setRange(0, 100)
        self.opacity_slider.setValue(50)
        self.opacity_slider.setFixedWidth(220)
        controls_layout.addWidget(self.opacity_slider)

        self.opacity_lbl = QLabel()
        self.opacity_lbl.setStyleSheet("color: #bbbbbb;")
        self.opacity_lbl.setText(
            UITexts.DUPLICATE_OVERLAY_OPACITY_LABEL.format(value=50))
        controls_layout.addWidget(self.opacity_lbl)

        controls_layout.addStretch()

        # Secondary document-style tabs: only the tab bar is visible, the
        # canvas below is shared by all sub-modes.
        self.overlay_tabs = QTabWidget()
        self.overlay_tabs.setDocumentMode(True)
        self.overlay_tabs.addTab(QWidget(), UITexts.DUPLICATE_OVERLAY_TOGGLE)
        self.overlay_tabs.addTab(QWidget(), UITexts.DUPLICATE_OVERLAY_SPLIT)
        self.overlay_tabs.addTab(QWidget(),
                                 UITexts.DUPLICATE_OVERLAY_DIFFERENCE)
        self.overlay_tabs.addTab(QWidget(), UITexts.DUPLICATE_OVERLAY_OPACITY)
        tab_bar_height = self.overlay_tabs.tabBar().sizeHint().height()
        self.overlay_tabs.setMaximumHeight(tab_bar_height + 2)

        self.overlay_canvas = OverlayCanvas()
        self.overlay_canvas.setToolTip(UITexts.DUPLICATE_OVERLAY_MOUSE_HINT)

        self.overlay_legend_lbl = QLabel()
        self.overlay_legend_lbl.setAlignment(Qt.AlignCenter)
        self.overlay_legend_lbl.setTextFormat(Qt.RichText)
        self.overlay_legend_lbl.setStyleSheet(
            "font-size: 10px; color: #888;")

        page_layout.addWidget(controls_bar)
        page_layout.addWidget(self.overlay_tabs)
        page_layout.addWidget(self.overlay_canvas, 1)
        page_layout.addWidget(self.overlay_legend_lbl)

        # Connections
        self.overlay_tabs.currentChanged.connect(self._on_overlay_tab_changed)
        self.overlay_canvas.layer_changed.connect(self._update_overlay_legend)
        self.opacity_slider.valueChanged.connect(self._on_opacity_changed)

        # The initial sub-tab is Toggle: hide the opacity controls right away,
        # otherwise they would be visible until the user changes sub-tab.
        self._update_overlay_controls(self.overlay_tabs.currentIndex())
        return page

    def _on_main_tab_changed(self, index):
        """
        Reacts to main tab switches, linking the Link Panes button state to
        the Side by Side tab and refreshing the newly shown view lazily.

        Args:
            index (int): The newly active main tab index (0 = Side by Side,
                1 = Overlay).
        """
        is_side = index == 0
        self.btn_link_panes.setEnabled(is_side and self._can_link)
        if is_side:
            self.panes_linked = self._user_link_preference and self._can_link
        else:
            self.panes_linked = False
        self.btn_link_panes.setChecked(self.panes_linked and is_side)
        self._refresh_active_view()

    def _on_overlay_tab_changed(self, index):
        """
        Reacts to overlay sub-tab switches: applies the new mode, shows the
        mode-specific controls and refreshes the canvas only if it is dirty.

        Args:
            index (int): The newly active overlay mode tab index.
        """
        self.overlay_canvas.set_mode(index)
        self._update_overlay_controls(index)
        self._update_overlay_legend()
        self._refresh_active_view()

    def _update_overlay_controls(self, index):
        """
        Shows or hides the mode-specific overlay controls.

        The opacity slider and its label are only visible in the Opacity
        sub-tab, and the Reset tooltip explains the mode-specific behaviour.

        Args:
            index (int): The active overlay mode tab index.
        """
        is_opacity = index == OverlayCanvas.MODE_OPACITY
        self.opacity_slider.setVisible(is_opacity)
        self.opacity_lbl.setVisible(is_opacity)

        if index == OverlayCanvas.MODE_SPLIT:
            tooltip = UITexts.DUPLICATE_OVERLAY_RESET_SPLIT_TOOLTIP
        elif index == OverlayCanvas.MODE_OPACITY:
            tooltip = UITexts.DUPLICATE_OVERLAY_RESET_OPACITY_TOOLTIP
        else:
            tooltip = UITexts.DUPLICATE_OVERLAY_RESET_TOOLTIP
        self._set_button_shortcut_tooltip(self.btn_overlay_reset, tooltip,
                                          "dup_reset_zoom")

    def _on_overlay_reset(self):
        """
        Resets the overlay view and the control of the active sub-mode.

        In Split the divider returns to the middle; in Opacity the slider
        returns to 50 %. In every mode the zoom and pan are reset as well.
        """
        self.overlay_canvas.reset_view()
        if self.overlay_tabs.currentIndex() == OverlayCanvas.MODE_SPLIT:
            self.overlay_canvas.reset_split()
        elif self.overlay_tabs.currentIndex() == OverlayCanvas.MODE_OPACITY:
            self.opacity_slider.setValue(50)

    def _reset_overlay_controls(self):
        """
        Resets the overlay control widgets when the image pair changes.

        The canvas itself is reset lazily by ``set_pixmaps`` when the Overlay
        tab is visible; here only the dialog-owned widgets are restored.
        """
        self.opacity_slider.blockSignals(True)
        self.opacity_slider.setValue(50)
        self.opacity_slider.blockSignals(False)
        self.opacity_lbl.setText(
            UITexts.DUPLICATE_OVERLAY_OPACITY_LABEL.format(value=50))

    def _refresh_active_view(self):
        """
        Refreshes only the currently visible view, honoring lazy updates.

        Hidden views keep their in-memory cache (the loaded Controller
        pixmaps) and are only updated when their tab becomes active again.
        """
        if self.main_tabs.currentIndex() == 1 and self._dirty["overlay"]:
            p_l = self.left_pane.controller.pixmap_original
            p_r = self.right_pane.controller.pixmap_original
            self.overlay_canvas.set_pixmaps(p_l, p_r)
            self.overlay_canvas.set_mode(self.overlay_tabs.currentIndex())
            self.overlay_canvas.set_opacity(self.opacity_slider.value())
            self._update_overlay_legend()
            self._dirty["overlay"] = False
        elif self.main_tabs.currentIndex() == 0 and self._dirty["side"]:
            self._apply_linked_scaling()
            self._dirty["side"] = False

    def _apply_comparison_colors(self):
        """
        Colors the size and resolution labels independently to indicate which
        side wins each comparison (green for best, red for worst, neutral
        grey for ties).
        """
        neutral = "#aaa"
        green = "#2ecc71"
        red = "#e74c3c"

        def style(color):
            """Returns a stylesheet string with the given label color."""
            return f"font-weight: bold; color: {color};"

        p_l = self.left_pane.controller.pixmap_original
        p_r = self.right_pane.controller.pixmap_original
        if p_l.isNull() or p_r.isNull():
            self.left_pane_widget.size_lbl.setStyleSheet(style(neutral))
            self.left_pane_widget.res_lbl.setStyleSheet(style(neutral))
            self.right_pane_widget.size_lbl.setStyleSheet(style(neutral))
            self.right_pane_widget.res_lbl.setStyleSheet(style(neutral))
            return

        res_l = p_l.width() * p_l.height()
        res_r = p_r.width() * p_r.height()
        if res_l > res_r:
            self.left_pane_widget.res_lbl.setStyleSheet(style(green))
            self.right_pane_widget.res_lbl.setStyleSheet(style(red))
        elif res_r > res_l:
            self.right_pane_widget.res_lbl.setStyleSheet(style(green))
            self.left_pane_widget.res_lbl.setStyleSheet(style(red))
        else:
            self.left_pane_widget.res_lbl.setStyleSheet(style(neutral))
            self.right_pane_widget.res_lbl.setStyleSheet(style(neutral))

        try:
            size_l = os.path.getsize(self.left_pane.controller.get_current_path())
            size_r = os.path.getsize(self.right_pane.controller.get_current_path())
        except (OSError, AttributeError):
            size_l = size_r = 0
        if size_l > size_r:
            self.left_pane_widget.size_lbl.setStyleSheet(style(green))
            self.right_pane_widget.size_lbl.setStyleSheet(style(red))
        elif size_r > size_l:
            self.right_pane_widget.size_lbl.setStyleSheet(style(green))
            self.left_pane_widget.size_lbl.setStyleSheet(style(red))
        else:
            self.left_pane_widget.size_lbl.setStyleSheet(style(neutral))
            self.right_pane_widget.size_lbl.setStyleSheet(style(neutral))

    def _swap_overlay_layers(self):
        """Swaps the overlay layers; the legend updates via layer_changed."""
        self.overlay_canvas.swap_layers()

    def _on_opacity_changed(self, value):
        """
        Applies a new top-layer opacity from the slider to the canvas.

        Args:
            value (int): The new opacity value in the 0-100 range.
        """
        self.opacity_lbl.setText(
            UITexts.DUPLICATE_OVERLAY_OPACITY_LABEL.format(value=value))
        self.overlay_canvas.set_opacity(value)

    def _update_overlay_legend(self):
        """
        Refreshes the overlay legend with the current top and bottom layers.

        In Toggle mode the visible layer is highlighted; after a swap the
        names follow the swapped roles.
        """
        left_path = self.left_pane.controller.get_current_path()
        right_path = self.right_pane.controller.get_current_path()
        left_name = os.path.basename(left_path) if left_path else "N/A"
        right_name = os.path.basename(right_path) if right_path else "N/A"

        swapped = self.overlay_canvas.is_swapped
        top_name, bottom_name = (right_name, left_name) if swapped else \
            (left_name, right_name)

        active_name = top_name if self.overlay_canvas.shows_top else bottom_name
        is_toggle = (self.overlay_tabs.currentIndex()
                     == OverlayCanvas.MODE_TOGGLE)
        plain = "color: #888;"
        highlighted = "color: #e8e8e8; font-weight: bold;"

        top_style = highlighted if (is_toggle and active_name == top_name) \
            else plain
        bottom_style = highlighted if (is_toggle and active_name == bottom_name) \
            else plain
        marker = "▶ " if is_toggle else ""

        self.overlay_legend_lbl.setText(
            f"<span style='{top_style}'>{marker}"
            f"{html.escape(UITexts.DUPLICATE_OVERLAY_TOP_LEGEND.format(name=top_name))}"
            f"</span>&nbsp;&nbsp;"
            f"<span style='{bottom_style}'>{marker}"
            f"{html.escape(UITexts.DUPLICATE_OVERLAY_BOTTOM_LEGEND.format(name=bottom_name))}"
            f"</span>")

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

            # Similarity column (using DisplayRole with int for numerical
            # sorting, plus a color that mirrors the removed similarity badge).
            sim_item = QTableWidgetItem()
            sim_item.setData(Qt.DisplayRole, dup.similarity
                             if dup.similarity is not None else 0)
            sim_item.setTextAlignment(Qt.AlignCenter)
            sim_color = self._similarity_color(dup.similarity)
            if sim_color:
                sim_item.setForeground(QBrush(QColor(sim_color)))
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

    @staticmethod
    def _similarity_color(similarity):
        """
        Maps a similarity percentage to the color used in the % column.

        Exact duplicates are green, matches below 80 % are red, anything in
        between is amber, and unknown values keep the default color.

        Args:
            similarity (float or None): The similarity percentage.

        Returns:
            str or None: Hex color string, or None when similarity is None.
        """
        if similarity is None:
            return None
        if similarity == 100:
            return "#2ecc71"
        if similarity < 80:
            return "#e74c3c"
        return "#f39c12"

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

        # Reset all overlay controls before loading the new pair.
        self._reset_overlay_controls()

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
        self._can_link = can_link
        self.panes_linked = self._user_link_preference and can_link
        self.btn_link_panes.setEnabled(
            can_link and self.main_tabs.currentIndex() == 0)
        self.btn_link_panes.setChecked(
            self.panes_linked and self.main_tabs.currentIndex() == 0)

        self._apply_comparison_colors()

        # Mark both views dirty and refresh only the active one (lazy update)
        self._dirty["side"] = True
        self._dirty["overlay"] = True
        self._refresh_active_view()

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
        size_lbl = pane_widget.size_lbl
        res_lbl = pane_widget.res_lbl
        filename_lbl = pane_widget.filename_lbl
        dir_lbl = pane_widget.dir_lbl

        if not os.path.exists(path):
            size_lbl.setText(UITexts.FILE_NOT_FOUND)
            res_lbl.setText("N/A")
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

        # Update size and resolution labels independently
        size_lbl.setText(UITexts.DUPLICATE_SIZE_LABEL.format(size=size_str))
        pixmap = pane.controller.pixmap_original
        if not pixmap.isNull():
            res_lbl.setText(UITexts.DUPLICATE_RESOLUTION_LABEL.format(
                width=pixmap.width(), height=pixmap.height()))
        else:
            res_lbl.setText("N/A")

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

        # Open location with the main application
        action_open_bagheeraview = menu.addAction(
            QIcon.fromTheme("system-run"),
            UITexts.CONTEXT_MENU_OPEN_BAGHEERAVIEW)
        action_open_bagheeraview.triggered.connect(
            lambda: self._open_location_in_bagheeraview(path))

        # Open location with Dolphin
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
            QIcon.fromTheme("user-trash"),
            self._menu_text(UITexts.CONTEXT_MENU_TRASH, "move_to_trash"))
        action_trash.triggered.connect(
            lambda: self._handle_action(delete_path=path, permanent=False))

        action_delete = menu.addAction(
            QIcon.fromTheme("edit-delete"),
            self._menu_text(UITexts.CONTEXT_MENU_DELETE, "delete_permanently"))
        action_delete.triggered.connect(
            lambda: self._handle_permanent_delete(path))

        menu.addSeparator()

        # Properties
        action_props = menu.addAction(
            QIcon.fromTheme("document-properties"),
            UITexts.CONTEXT_MENU_PROPERTIES)
        action_props.triggered.connect(
            lambda: self._show_properties(path, pane))

        menu.exec(pane.mapToGlobal(pos))

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
        Registers the deletion shortcuts for this dialog.

        ``Delete`` sends the focused pane's image to the trash and
        ``Shift+Delete`` deletes it permanently, reusing the global shortcut
        assignments so the behaviour stays configurable.
        """
        self._menu_action_shortcuts = {}
        controller = getattr(self.main_win, "shortcut_controller", None)
        if controller is not None:
            for action in ("move_to_trash", "delete_permanently"):
                key_combo = getattr(
                    controller, "action_to_shortcut", {}).get(action)
                if key_combo is not None:
                    self._menu_action_shortcuts[action] = key_combo

        self._shortcut_objects = []
        for action, handler in (("move_to_trash", self._shortcut_trash),
                                ("delete_permanently", self._shortcut_delete)):
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

        # Tab toggles the shown layer while the Overlay Toggle mode is active.
        self._tab_shortcut = QShortcut(QKeySequence(Qt.Key_Tab), self)
        self._tab_shortcut.setContext(Qt.WidgetWithChildrenShortcut)
        self._tab_shortcut.activated.connect(self._on_toggle_shortcut)
        self._shortcut_objects.append(self._tab_shortcut)

    def _on_toggle_shortcut(self):
        """
        Toggles the overlay layer only when the Overlay Toggle mode is active.

        Kept as a no-op in any other context so Tab keeps its normal focus
        traversal behaviour outside the dedicated Toggle sub-mode.
        """
        if (self.main_tabs.currentIndex() == 1
                and self.overlay_tabs.currentIndex() == OverlayCanvas.MODE_TOGGLE):
            self.overlay_canvas.toggle_layer()

    def _active_pane_path(self):
        """
        Returns the path shown by the currently focused pane, if any.

        Returns:
            str or None: The path of the active pane image.
        """
        pane = self.active_pane or self.left_pane
        if pane is None:
            return None
        return pane.controller.get_current_path()

    def _shortcut_trash(self):
        """Moves the image of the active pane to the trash."""
        path = self._active_pane_path()
        if path:
            self._handle_action(delete_path=path, permanent=False)

    def _shortcut_delete(self):
        """Permanently deletes the image of the active pane."""
        path = self._active_pane_path()
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
        if self.panes_linked and self.main_tabs.currentIndex() == 0:
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
        if not self.panes_linked or self.main_tabs.currentIndex() != 0:
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
        if not self.panes_linked or self._is_syncing \
                or self.main_tabs.currentIndex() != 0:
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

    def _overwrite_selected(self):
        """
        Renames the selected image to the name of the other one, replacing it.

        The whole flow is confirmed first with a dialog listing both full
        paths. If the direct rename is not possible (e.g. cross-device), the
        file is copied overwriting the target. On success the resolved pair is
        removed from the list because its content (or the very file) changed.
        """
        source = self._active_pane_path()
        if self.active_pane is self.right_pane:
            target = self.left_pane.controller.get_current_path()
        else:
            target = self.right_pane.controller.get_current_path()

        if not source or not target or not os.path.exists(source) \
                or not os.path.exists(target):
            QMessageBox.warning(
                self, UITexts.WARNING, UITexts.DUPLICATE_OVERWRITE_NO_SELECTION)
            return

        try:
            final = self.main_win.resolve_overwrite_target(source, target)
        except AttributeError:
            # Fall back to the plain target when the main window does not
            # expose the helper (tests or partial environments).
            final = target

        text = UITexts.DUPLICATE_OVERWRITE_CONFIRM_TEXT.format(
            source=source, target=target)
        if os.path.splitext(source)[1].lower() != os.path.splitext(target)[1].lower():
            text += "\n\n" + UITexts.DUPLICATE_OVERWRITE_CONFIRM_EXT_NOTE.format(
                final=final, target=target)

        reply = QMessageBox.question(
            self, UITexts.DUPLICATE_OVERWRITE_CONFIRM_TITLE, text,
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply != QMessageBox.Yes:
            return

        current_row = self.table_widget.currentRow()
        affected = [d for d in self.duplicates
                    if d.path1 in (source, target) or d.path2 in (source, target)]
        for p in affected:
            self.cache.mark_as_pending(p.path1, p.path2, False)

        try:
            self.main_win.overwrite_image_file(source, target)
        except Exception as e:
            # Restore the pending marks so the pair can be resolved later.
            for p in affected:
                self.cache.mark_as_pending(p.path1, p.path2, True)
            QMessageBox.critical(
                self, UITexts.ERROR,
                UITexts.DUPLICATE_OVERWRITE_ERROR.format(error=e))
            return

        self.duplicates = [d for d in self.duplicates if d not in affected]
        self._reselect_after_change(current_row)

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
        self._reselect_after_change(current_row)

    def _reselect_after_change(self, current_row):
        """
        Repopulates the duplicates list and restores the selection position.

        Args:
            current_row (int): The row that was selected before the change.
        """
        self._populate_list()
        if self.duplicates:
            new_row = min(current_row, self.table_widget.rowCount() - 1)
            self.table_widget.selectRow(new_row)
            self.table_widget.setCurrentCell(new_row, 0)
        else:
            self.close()
