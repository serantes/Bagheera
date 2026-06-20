#!/usr/bin/env python3
"""
Bagheera Image Viewer - Main Application.

This is the main entry point for the Bagheera Image Viewer application. It
initializes the main window, handles application-wide shortcuts, manages the
thumbnail grid, and coordinates background scanning, caching, and image
viewing.

The application uses a model-view-delegate pattern for the thumbnail grid to
efficiently handle very large collections of images.

Classes:
    AppShortcutController: Global event filter for keyboard shortcuts.
    MainWindow: The main application window containing the thumbnail grid and
    docks.
"""

import sys
import os
import subprocess
import json
import glob
import shutil
from datetime import datetime
from collections import deque, defaultdict
from itertools import groupby

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QVBoxLayout, QHBoxLayout,
    QLineEdit, QTextEdit, QPushButton, QFileDialog, QComboBox, QSlider,
    QMessageBox, QSizePolicy, QMenu, QInputDialog, QTableWidget,
    QTableWidgetItem, QHeaderView, QTabWidget, QProgressDialog, QDockWidget,
    QAbstractItemView, QRadioButton, QButtonGroup, QListView,
    QStyledItemDelegate, QStyle, QDialog, QKeySequenceEdit, QDialogButtonBox
)
from PySide6.QtGui import (
    QDesktopServices, QFont, QFontMetrics, QIcon, QTransform, QImageReader,
    QPalette, QStandardItemModel, QStandardItem, QColor, QPixmap, QPixmapCache,
    QPainter, QKeySequence, QAction, QActionGroup, QImage
)
from PySide6.QtCore import (
    Qt, QPoint, QUrl, QObject, QEvent, QTimer, QByteArray,
    QItemSelection, QSortFilterProxyModel, QItemSelectionModel, QRect, QSize,
    QThread, QPersistentModelIndex, QModelIndex
)
from PySide6.QtDBus import QDBusConnection, QDBusMessage, QDBus

from pathlib import Path

from .constants import (
    APP_CONFIG, CACHE_PATH, CONFIG_PATH, DEFAULT_GLOBAL_SHORTCUTS,
    DEFAULT_LANGUAGE, DEFAULT_VIEWER_SHORTCUTS, GLOBAL_ACTIONS,
    HISTORY_PATH, ICON_THEME, ICON_THEME_FALLBACK, SCANNER_GENERATE_SIZES,
    IMAGE_MIME_TYPES, IMAGE_EXTENSIONS, LAYOUTS_DIR, FAVORITES_PATH,
    PROG_AUTHOR, PROG_ID, PROG_NAME, PROG_VERSION, RATING_XATTR_NAME,
    SCANNER_SETTINGS_DEFAULTS, SUPPORTED_LANGUAGES, VIEWER_ACTIONS,
    TAGS_MENU_MAX_ITEMS_DEFAULT, THUMBNAILS_BG_COLOR_DEFAULT,
    THUMBNAILS_DEFAULT_SIZE, THUMBNAILS_FILENAME_COLOR_DEFAULT,
    THUMBNAILS_TOOLTIP_BG_COLOR_DEFAULT, HAVE_IMAGEHASH,
    FACES_MENU_MAX_ITEMS_DEFAULT, THUMBNAILS_TOOLTIP_FG_COLOR_DEFAULT,
    THUMBNAILS_FILENAME_LINES_DEFAULT, THUMBNAILS_FILENAME_FONT_SIZE_DEFAULT,
    THUMBNAILS_TAGS_LINES_DEFAULT, THUMBNAILS_TAGS_COLOR_DEFAULT,
    THUMBNAILS_RATING_COLOR_DEFAULT, THUMBNAILS_TAGS_FONT_SIZE_DEFAULT,
    THUMBNAILS_REFRESH_INTERVAL_DEFAULT, THUMBNAIL_SIZES, XATTR_NAME,
    UITexts, save_app_config, PATH_ROLE, MTIME_ROLE, TAGS_ROLE, RATING_ROLE,
    ITEM_TYPE_ROLE, DIR_ROLE, INODE_ROLE, DEVICE_ROLE, IMAGE_DATA_ROLE,
    GROUP_NAME_ROLE
)
from .settings import SettingsDialog
if HAVE_IMAGEHASH:
    from .duplicatecache import DuplicateCache, DuplicateDetector
    from .duplicatedialog import DuplicateManagerDialog
    from .similardialog import SimilarImagesDialog
else:
    DuplicateCache = None
    DuplicateDetector = None
from .imagescanner import (CacheCleaner, ImageScanner, ThumbnailCache,
                           ThumbnailGenerator, ThreadPoolManager)
from .imageviewer import ImageViewer
from .propertiesdialog import PropertiesDialog
from .widgets import (
    CircularProgressBar,
    TagEditWidget, LayoutsWidget, HistoryWidget, RatingWidget, CommentWidget,
    FavoritesWidget
)
from .metadatamanager import load_common_metadata
from .filesystemwatcher import FileSystemWatcher


class ShortcutHelpDialog(QDialog):
    """A dialog to display, filter, and edit keyboard shortcuts."""
    def __init__(self, global_shortcuts, viewer_shortcuts, main_win):
        super().__init__(main_win)
        self.global_shortcuts = global_shortcuts
        self.viewer_shortcuts = viewer_shortcuts
        self.main_win = main_win

        self.setWindowTitle(UITexts.SHORTCUTS_TITLE)
        self.resize(500, 450)

        layout = QVBoxLayout(self)

        # Search bar
        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText(UITexts.SHORTCUT_SEARCH_PLACEHOLDER)
        self.search_bar.textChanged.connect(self.filter_table)
        layout.addWidget(self.search_bar)

        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels([UITexts.SHORTCUTS_ACTION,
                                              UITexts.SHORTCUTS_KEY])
        self.table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.doubleClicked.connect(self.edit_shortcut)
        layout.addWidget(self.table)

        self.populate_table()

        # Close button
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        close_btn = QPushButton(UITexts.CLOSE)
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)

    def populate_table(self):
        """Fills the table with the current shortcuts."""
        self.table.setRowCount(0)
        shortcuts_list = []

        def get_int_modifiers(mods):
            try:
                return int(mods)
            except TypeError:
                return mods.value

        # Global Shortcuts
        for (key, mods), val in self.global_shortcuts.items():
            # val is (func, ignore, desc, category)
            desc = val[2]
            category = val[3] if len(val) > 3 else "Global"
            seq = QKeySequence(get_int_modifiers(mods) | key)
            shortcut_str = seq.toString(QKeySequence.NativeText)
            shortcuts_list.append(
                {'cat': category, 'desc': desc, 'sc': shortcut_str,
                 'key': (key, mods), 'src': self.global_shortcuts})

        # Viewer Shortcuts
        for (key, mods), (action, desc) in self.viewer_shortcuts.items():
            seq = QKeySequence(get_int_modifiers(mods) | key)
            shortcut_str = seq.toString(QKeySequence.NativeText)
            shortcuts_list.append(
                {'cat': "Viewer", 'desc': desc, 'sc': shortcut_str,
                 'key': (key, mods), 'src': self.viewer_shortcuts})

        # Sort by Category then Description
        shortcuts_list.sort(key=lambda x: (x['cat'], x['desc']))

        current_cat = None
        for item in shortcuts_list:
            if item['cat'] != current_cat:
                current_cat = item['cat']
                # Add header row
                row = self.table.rowCount()
                self.table.insertRow(row)
                header_item = QTableWidgetItem(current_cat)
                header_item.setFlags(Qt.ItemIsEnabled)
                header_item.setBackground(QColor(60, 60, 60))
                header_item.setForeground(Qt.white)
                font = header_item.font()
                font.setBold(True)
                header_item.setFont(font)
                header_item.setData(Qt.UserRole, "header")
                self.table.setItem(row, 0, header_item)
                self.table.setSpan(row, 0, 1, 2)

            row = self.table.rowCount()
            self.table.insertRow(row)

            item_desc = QTableWidgetItem(item['desc'])
            item_desc.setData(Qt.UserRole, (item['key'], item['src']))
            item_sc = QTableWidgetItem(item['sc'])
            item_sc.setData(Qt.UserRole, (item['key'], item['src']))

            self.table.setItem(row, 0, item_desc)
            self.table.setItem(row, 1, item_sc)

    def filter_table(self, text):
        """Hides or shows table rows based on the search text."""
        text = text.lower()
        current_header_row = -1
        category_has_visible_items = False

        for row in range(self.table.rowCount()):
            action_item = self.table.item(row, 0)
            if not action_item:
                continue

            if action_item.data(Qt.UserRole) == "header":
                # Process previous header visibility
                if current_header_row != -1:
                    self.table.setRowHidden(current_header_row,
                                            not category_has_visible_items)

                current_header_row = row
                category_has_visible_items = False
                self.table.setRowHidden(row, False)  # Show tentatively
            else:
                shortcut_item = self.table.item(row, 1)
                if action_item and shortcut_item:
                    action_text = action_item.text().lower()
                    shortcut_text = shortcut_item.text().lower()
                    match = text in action_text or text in shortcut_text
                    self.table.setRowHidden(row, not match)
                    if match:
                        category_has_visible_items = True

        # Handle last header
        if current_header_row != -1:
            self.table.setRowHidden(current_header_row,
                                    not category_has_visible_items)

    def edit_shortcut(self, index):
        """Handles the double-click event to allow shortcut customization."""
        if not index.isValid():
            return

        row = index.row()
        data = self.table.item(row, 0).data(Qt.UserRole)
        if not data or data == "header":
            return
        original_key_combo, source_dict = data

        current_sc_str = self.table.item(row, 1).text()
        current_sequence = QKeySequence.fromString(
            current_sc_str, QKeySequence.NativeText)

        dialog = QDialog(self)
        dialog.setWindowTitle(UITexts.SHORTCUT_EDIT_TITLE)
        layout = QVBoxLayout(dialog)
        layout.addWidget(
            QLabel(UITexts.SHORTCUT_EDIT_LABEL.format(
                self.table.item(row, 0).text())))
        key_edit = QKeySequenceEdit(current_sequence)
        layout.addWidget(key_edit)
        button_box = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)

        if dialog.exec() == QDialog.Accepted:
            new_sequence = key_edit.keySequence()
            if new_sequence.isEmpty() or new_sequence.count() == 0:
                return

            new_key_combo = new_sequence[0]
            new_key = new_key_combo.key()
            new_mods = new_key_combo.keyboardModifiers()
            new_key_tuple = (int(new_key), new_mods)

            # Check for conflicts globally
            conflict_desc = self.main_win.shortcut_controller.check_conflict(
                new_key, new_mods)

            is_same = (new_key_tuple == original_key_combo)

            if conflict_desc and not is_same:
                QMessageBox.warning(self, UITexts.SHORTCUT_CONFLICT_TITLE,
                                    UITexts.SHORTCUT_CONFLICT_TEXT.format(
                                        new_sequence.toString(
                                            QKeySequence.NativeText),
                                        conflict_desc))
                return

            shortcut_data = source_dict.pop(original_key_combo)
            source_dict[new_key_tuple] = shortcut_data

            self.table.item(row, 1).setText(
                new_sequence.toString(QKeySequence.NativeText))
            new_data = (new_key_tuple, source_dict)
            self.table.item(row, 0).setData(Qt.UserRole, new_data)
            self.table.item(row, 1).setData(Qt.UserRole, new_data)


class AppShortcutController(QObject):
    """
    Global event filter for application-wide keyboard shortcuts.

    This class is installed on the QApplication instance to intercept key press
    events before they reach their target widgets. This allows for defining
    global shortcuts that work regardless of which widget has focus, unless
    the user is typing in an input field.
    """
    def __init__(self, main_win):
        """Initializes the shortcut controller.

        Args:
            main_win (MainWindow): A reference to the main application window.
        """
        super().__init__()
        self.main_win = main_win
        self._actions = self._get_actions()
        self._shortcuts = {}
        self._favorite_shortcuts = {}
        self.action_to_shortcut = {}
        self._register_shortcuts()

        # Overwrite with loaded config if available
        if hasattr(self.main_win, 'loaded_global_shortcuts') \
           and self.main_win.loaded_global_shortcuts:
            user_shortcuts = {}
            for key_combo, val_list in self.main_win.loaded_global_shortcuts:
                if len(val_list) == 4:
                    k, m = key_combo
                    user_shortcuts[(k, Qt.KeyboardModifiers(m))] = tuple(val_list)

            user_actions = {v[0] for v in user_shortcuts.values()}
            user_keys = set(user_shortcuts.keys())

            # Start with user config
            final_shortcuts = user_shortcuts.copy()

            # Add defaults for actions or keys not present in user config
            for key, val in self._shortcuts.items():
                action_name = val[0]
                if action_name not in user_actions and key not in user_keys:
                    final_shortcuts[key] = val

            self._shortcuts = final_shortcuts
            self.action_to_shortcut = {v[0]: k for k, v in self._shortcuts.items()}
        self.refresh_favorite_shortcuts()

    def refresh_favorite_shortcuts(self):
        """Loads dynamic shortcuts assigned to favorite queries."""
        self._favorite_shortcuts.clear()
        if not os.path.exists(FAVORITES_PATH):
            return
        try:
            with open(FAVORITES_PATH, 'r', encoding='utf-8') as f:
                favorites = json.load(f)
                for fav in favorites:
                    sc_str = fav.get('shortcut', '')
                    if sc_str:
                        seq = QKeySequence(sc_str)
                        if not seq.isEmpty():
                            self._favorite_shortcuts[
                                (seq[0].key(), seq[0].keyboardModifiers())
                                ] = fav.get('query')
        except (json.JSONDecodeError, OSError):
            pass

    def check_conflict(self, key, mods):
        """Checks if a shortcut is already assigned and returns its
        description."""
        key_tuple = (int(key), mods)

        # Global
        if key_tuple in self._shortcuts:
            return self._shortcuts[key_tuple][2]

        # Viewer
        if key_tuple in self.main_win.viewer_shortcuts:
            return self.main_win.viewer_shortcuts[key_tuple][1]

        # Favorites
        if key_tuple in self._favorite_shortcuts:
            return f"{UITexts.FAVORITES_TAB}: {
                self._favorite_shortcuts[key_tuple]}"

        return None

    def _get_actions(self):
        """Returns a dictionary mapping action strings to callable
        functions."""
        return {
            "quit_app": self._quit_app,
            "toggle_visibility": self._toggle_visibility,
            "close_all_viewers": self._close_viewers,
            "load_more_images": self.main_win.load_more_images,
            "load_all_images": self.main_win.load_all_images,
            "save_layout": self.main_win.save_layout,
            "load_layout": self.main_win.load_layout_dialog,
            "open_folder": self.main_win.open_current_folder,
            "move_to_trash":
                lambda: self.main_win.delete_current_image(permanent=None),
            "delete_permanently":
                lambda: self.main_win.delete_current_image(permanent=True),
            "rename_image": self._rename_image,
            "hard_refresh_content": self.main_win.hard_refresh_content,
            "refresh_content": self.main_win.refresh_content,
            "first_image": lambda: self._handle_home_end(Qt.Key_Home),
            "last_image": lambda: self._handle_home_end(Qt.Key_End),
            "prev_page": lambda: self._handle_page_nav(Qt.Key_PageUp),
            "next_page": lambda: self._handle_page_nav(Qt.Key_PageDown),
            "zoom_in": lambda: self._handle_zoom(Qt.Key_Plus),
            "toggle_faces": self._toggle_faces,
            "zoom_out": lambda: self._handle_zoom(Qt.Key_Minus),
            "select_all": self.main_win.select_all_thumbnails,
            "select_none": self.main_win.select_none_thumbnails,
            "invert_selection": self.main_win.invert_selection_thumbnails,
        }

    def _register_shortcuts(self):
        """Registers all application shortcuts from constants."""
        self.action_to_shortcut.clear()
        for action, (key, mods, ignore) in DEFAULT_GLOBAL_SHORTCUTS.items():
            if action in GLOBAL_ACTIONS:
                desc, category = GLOBAL_ACTIONS[action]
                key_combo = (int(key), Qt.KeyboardModifiers(mods))
                self._shortcuts[key_combo] = (action, ignore, desc, category)
                self.action_to_shortcut[action] = key_combo

    def eventFilter(self, obj, event):
        """Filters events to handle global key presses."""
        if event.type() != QEvent.KeyPress:
            return False

        key = event.key()
        mods = event.modifiers() & (Qt.ShiftModifier | Qt.ControlModifier |
                                    Qt.AltModifier | Qt.MetaModifier)

        # Special case: Ignore specific navigation keys when typing
        focus_widget = QApplication.focusWidget()
        is_typing = isinstance(focus_widget, (QComboBox, QLineEdit, QTextEdit,
                                              QInputDialog))
        # if is_typing and key in (Qt.Key_Home, Qt.Key_End, Qt.Key_Delete,
        #                         Qt.Key_Left, Qt.Key_Right, Qt.Key_Backspace):
        if is_typing:
            return False

        # 1. Check Favorite Shortcuts FIRST (Priority Override)
        if (key, mods) in self._favorite_shortcuts:
            query = self._favorite_shortcuts[(key, mods)]
            self.main_win.process_term(query)
            return True

        # Check if we have a handler for this combination
        if (key, mods) in self._shortcuts:
            action_name, ignore_if_typing, _, _ = self._shortcuts[(key, mods)]

            if ignore_if_typing:
                focus_widget = QApplication.focusWidget()
                if isinstance(focus_widget, (QComboBox, QLineEdit, QTextEdit,
                                             QInputDialog)):
                    return False

            if action_name in self._actions:
                self._actions[action_name]()
            return True

        return False

    def show_help(self):
        """Displays a dialog listing all registered shortcuts."""
        dialog = ShortcutHelpDialog(self._shortcuts, self.main_win.viewer_shortcuts,
                                    self.main_win)
        dialog.exec()
        self.main_win.refresh_shortcuts()

    # --- Action Handlers ---

    def _quit_app(self):
        self.main_win.perform_shutdown()
        QApplication.quit()

    def _toggle_visibility(self):
        self.main_win.toggle_visibility()

    def _close_viewers(self):
        if not self.main_win.isVisible():
            self.main_win.toggle_visibility()
        self.main_win.close_all_viewers()

    def _rename_image(self):
        active_viewer = next((w for w in QApplication.topLevelWidgets()
                              if isinstance(w, ImageViewer)
                              and w.isActiveWindow()), None)
        if active_viewer:
            active_viewer.rename_current_image()
        elif self.main_win.thumbnail_view.selectedIndexes():
            self.main_win.rename_image(
                self.main_win.thumbnail_view.selectedIndexes()[0].row())

    def _handle_home_end(self, key):
        active_viewer = next((w for w in QApplication.topLevelWidgets()
                              if isinstance(w, ImageViewer)
                              and w.isActiveWindow()), None)
        if active_viewer:
            if key == Qt.Key_End:
                active_viewer.controller.last()
            else:
                active_viewer.controller.first()
            active_viewer.load_and_fit_image()
        elif self.main_win.proxy_model.rowCount() > 0:
            if key == Qt.Key_End \
               and self.main_win._scanner_last_index < \
               self.main_win._scanner_total_files:
                self.main_win.scanner.load_images(
                    self.main_win._scanner_last_index,
                    self.main_win._scanner_total_files -
                    self.main_win._scanner_last_index)

            # Find the first/last actual thumbnail, skipping headers
            model = self.main_win.proxy_model
            count = model.rowCount()
            target_row = -1

            if key == Qt.Key_Home:
                for row in range(count):
                    idx = model.index(row, 0)
                    if model.data(idx, ITEM_TYPE_ROLE) == 'thumbnail':
                        target_row = row
                        break
            else:  # End
                for row in range(count - 1, -1, -1):
                    idx = model.index(row, 0)
                    if model.data(idx, ITEM_TYPE_ROLE) == 'thumbnail':
                        target_row = row
                        break

            if target_row >= 0:
                target_idx = model.index(target_row, 0)
                self.main_win.set_selection(target_idx)

    def _handle_page_nav(self, key):
        active_viewer = next((w for w in QApplication.topLevelWidgets()
                              if isinstance(w, ImageViewer)
                              and w.isActiveWindow()), None)
        if active_viewer:
            if key == Qt.Key_PageDown:
                active_viewer.next_image()
            else:
                active_viewer.prev_image()
        elif self.main_win.isVisible():
            self.main_win.handle_page_nav(key)

    def _toggle_faces(self):
        if self.main_win.isVisible():
            self.main_win.toggle_faces()

    def _handle_zoom(self, key):
        active_viewer = next((w for w in QApplication.topLevelWidgets()
                              if isinstance(w, ImageViewer)
                              and w.isActiveWindow()), None)
        if active_viewer:
            if key == Qt.Key_Plus:
                active_viewer.controller.zoom_factor *= 1.1
                active_viewer.update_view(True)
            elif key == Qt.Key_Minus:
                active_viewer.controller.zoom_factor *= 0.9
                active_viewer.update_view(True)
        else:
            if self.main_win.isVisible() \
               and not any(isinstance(w, ImageViewer)
               and w.isActiveWindow() for w in QApplication.topLevelWidgets()):
                size = self.main_win.slider.value()
                if key == Qt.Key_Plus:
                    size += 16
                else:
                    size -= 16
                self.main_win.slider.setValue(size)


class ThumbnailDelegate(QStyledItemDelegate):
    """Draws each thumbnail in the virtualized view.

    This delegate is responsible for painting each item in the QListView,
    including the image, filename, rating, and tags. This is much more
    performant than creating a separate widget for each thumbnail.
    """
    HEADER_HEIGHT = 25

    def __init__(self, parent=None):
        super().__init__(parent)
        self.main_win = parent

    def paint(self, painter, option, index):
        painter.save()
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        item_type = index.data(ITEM_TYPE_ROLE)

        if item_type == 'header':
            self.paint_header(painter, option, index)
        else:
            self.paint_thumbnail(painter, option, index)

        painter.restore()

    def paint_header(self, painter, option, index):
        """Draws a group header item."""
        folder_path = index.data(DIR_ROLE)
        group_name = index.data(GROUP_NAME_ROLE)

        is_collapsed = group_name in self.main_win.proxy_model.collapsed_groups

        prefix = "▶ " if is_collapsed else "▼ "
        folder_name = prefix + (folder_path if folder_path else UITexts.UNKNOWN)

        # Background band
        painter.fillRect(option.rect, option.palette.alternateBase())

        # Separator line
        sep_color = option.palette.text().color()
        sep_color.setAlpha(80)
        painter.setPen(sep_color)
        line_y = option.rect.center().y()
        painter.drawLine(option.rect.left(), line_y, option.rect.right(), line_y)

        # Folder name text with its own background to cover the line
        font = painter.font()
        font.setBold(True)
        painter.setFont(font)
        fm = painter.fontMetrics()
        text_w = fm.horizontalAdvance(folder_name) + 20
        text_bg_rect = QRect(option.rect.center().x() - text_w // 2,
                             option.rect.top(),
                             text_w,
                             option.rect.height())
        painter.fillRect(text_bg_rect, option.palette.alternateBase())
        painter.setPen(option.palette.text().color())
        painter.drawText(option.rect, Qt.AlignCenter, folder_name)

    def paint_thumbnail(self, painter, option, index):
        """Draws a thumbnail item with image, text, rating, and tags."""
        thumb_size = self.main_win.current_thumb_size
        path = index.data(PATH_ROLE)
        mtime = index.data(MTIME_ROLE)

        # Optimization: Use QPixmapCache to avoid expensive QImage->QPixmap
        # conversion on every paint event.
        actual_tier = self.main_win.cache.get_available_tier(path, thumb_size, mtime)
        # Use int representation of mtime for a stable cache key
        mtime_key = int(mtime * 1000) if mtime else 0
        cache_key = f"thumb_{path}_{mtime_key}_{thumb_size}_{actual_tier}"
        source_pixmap = QPixmapCache.find(cache_key)

        if not source_pixmap or source_pixmap.isNull():
            # Not in UI cache, try to get from main thumbnail cache (Memory/LMDB)
            inode = index.data(INODE_ROLE)
            device_id = index.data(DEVICE_ROLE)
            res = self.main_win.cache.get_thumbnail(
                path, requested_size=thumb_size, curr_mtime=mtime,
                inode=inode, device_id=device_id, async_load=True)

            if res.image and not res.image.isNull():
                source_pixmap = QPixmap.fromImage(res.image)
                # Use the tier actually returned for the key to avoid redundant conversions
                tier_key = f"thumb_{path}_{mtime_key}_{thumb_size}_{res.tier}"
                QPixmapCache.insert(tier_key, source_pixmap)
            else:
                # Fallback: Check a separate cache key for the placeholder to avoid
                # blocking the high-res update while still preventing repetitive
                # conversions.
                fallback_key = f"fb_{path}_{mtime}"
                source_pixmap = QPixmapCache.find(fallback_key)

                if not source_pixmap or source_pixmap.isNull():
                    # Fallback to IMAGE_DATA_ROLE (low res scan thumbnail)
                    img_fallback = index.data(IMAGE_DATA_ROLE)
                    if img_fallback and hasattr(img_fallback, 'isNull') \
                       and not img_fallback.isNull():
                        source_pixmap = QPixmap.fromImage(img_fallback)
                        QPixmapCache.insert(fallback_key, source_pixmap)
                    else:
                        # Fallback to the icon stored in the model
                        icon = index.data(Qt.DecorationRole)
                        if icon and not icon.isNull():
                            source_pixmap = icon.pixmap(thumb_size, thumb_size)
                            # Icons are usually internally cached by Qt, minimal
                            # overhead
                        else:
                            # Empty fallback if nothing exists
                            source_pixmap = QPixmap()

        filename = index.data(Qt.DisplayRole)
        tags = index.data(TAGS_ROLE) or []
        rating = index.data(RATING_ROLE) or 0

        # --- Rectangles and Styles ---
        full_rect = QRect(option.rect)
        if option.state & QStyle.State_Selected:
            painter.fillRect(full_rect, option.palette.highlight())
            pen_color = option.palette.highlightedText().color()
        else:
            pen_color = option.palette.text().color()
        # --- Draw Components ---
        # 1. Thumbnail Pixmap
        img_bbox = QRect(full_rect.x(), full_rect.y() + 5,
                         full_rect.width(), thumb_size)

        # Calculate destination rect maintaining aspect ratio
        pic_size = source_pixmap.size()
        pic_size.scale(img_bbox.size(), Qt.KeepAspectRatio)

        pixmap_rect = QRect(QPoint(0, 0), pic_size)
        pixmap_rect.moveCenter(img_bbox.center())
        painter.drawPixmap(pixmap_rect, source_pixmap)

        # Start drawing text below the thumbnail
        text_y = full_rect.y() + thumb_size + 8

        # 2. Filename
        if APP_CONFIG.get("thumbnails_show_filename", True):
            font = painter.font()  # Get a copy
            filename_font_size = APP_CONFIG.get("thumbnails_filename_font_size",
                                                THUMBNAILS_FILENAME_FONT_SIZE_DEFAULT)
            font.setPointSize(filename_font_size)
            painter.setFont(font)

            fm = painter.fontMetrics()
            line_height = fm.height()
            num_lines = APP_CONFIG.get("thumbnails_filename_lines",
                                       THUMBNAILS_FILENAME_LINES_DEFAULT)
            rect_height = line_height * num_lines

            text_rect = QRect(full_rect.x() + 4, text_y,
                              full_rect.width() - 8, rect_height)

            if option.state & QStyle.State_Selected:
                painter.setPen(pen_color)
            else:
                filename_color_str = APP_CONFIG.get("thumbnails_filename_color",
                                                    THUMBNAILS_FILENAME_COLOR_DEFAULT)
                painter.setPen(QColor(filename_color_str))

            # Elide text to fit approximately in the given number of lines, then wrap.
            elided_text = fm.elidedText(filename.replace('\n', ' '), Qt.ElideRight,
                                        text_rect.width() * num_lines)

            flags = Qt.AlignCenter | Qt.TextWordWrap
            painter.drawText(text_rect, flags, elided_text)
            text_y += rect_height

        # 3. Rating (stars)
        if APP_CONFIG.get("thumbnails_show_rating", True):
            font = option.font  # Reset font to avoid compounding size changes
            font.setBold(False)
            # Keep rating size relative but consistent
            font.setPointSize(font.pointSize() - 1)
            painter.setFont(font)
            num_stars = (rating + 1) // 2
            stars_text = '★' * num_stars + '☆' * (5 - num_stars)
            rating_rect = QRect(full_rect.x(), text_y,
                                full_rect.width(), 15)

            rating_color_str = APP_CONFIG.get("thumbnails_rating_color",
                                              THUMBNAILS_RATING_COLOR_DEFAULT)
            painter.setPen(QColor(rating_color_str))
            painter.drawText(rating_rect, Qt.AlignCenter, stars_text)
            text_y += 15

        # 4. Tags
        if APP_CONFIG.get("thumbnails_show_tags", True):
            font = painter.font()  # Reset font again
            tags_font_size = APP_CONFIG.get("thumbnails_tags_font_size",
                                            THUMBNAILS_TAGS_FONT_SIZE_DEFAULT)
            font.setPointSize(tags_font_size)
            painter.setFont(font)

            fm = painter.fontMetrics()
            line_height = fm.height()
            num_lines = APP_CONFIG.get("thumbnails_tags_lines",
                                       THUMBNAILS_TAGS_LINES_DEFAULT)
            rect_height = line_height * num_lines

            if option.state & QStyle.State_Selected:
                painter.setPen(pen_color)
            else:
                tags_color_str = APP_CONFIG.get("thumbnails_tags_color",
                                                THUMBNAILS_TAGS_COLOR_DEFAULT)
                painter.setPen(QColor(tags_color_str))

            display_tags = [t.split('/')[-1] for t in tags]
            tags_text = ", ".join(display_tags)
            tags_rect = QRect(full_rect.x() + 4, text_y,
                              full_rect.width() - 8, rect_height)
            elided_tags = fm.elidedText(tags_text, Qt.ElideRight,
                                        tags_rect.width() * num_lines)
            painter.drawText(tags_rect, Qt.AlignCenter | Qt.TextWordWrap, elided_tags)

    def sizeHint(self, option, index):
        """Provides the size hint for each item, including all elements."""
        # Check for the special 'header' type only if we have a valid index
        if index and index.isValid():
            item_type = index.data(ITEM_TYPE_ROLE)
            if item_type == 'header':
                # To ensure the header item occupies a full row in the flow layout
                # of the IconMode view, we set its width to the viewport's width
                # minus a small margin. This prevents other items from trying to
                # flow next to it.
                return QSize(self.main_win.thumbnail_view.viewport().width() - 5,
                             self.HEADER_HEIGHT)

        # Default size for a standard thumbnail item (or when index is None)
        thumb_size = self.main_win.current_thumb_size
        # Height: thumb + top padding
        height = thumb_size + 8

        # Use a temporary font to get font metrics for accurate height calculation
        font = QFont(self.main_win.font())

        if APP_CONFIG.get("thumbnails_show_filename", True):
            font.setPointSize(APP_CONFIG.get(
                "thumbnails_filename_font_size", THUMBNAILS_FILENAME_FONT_SIZE_DEFAULT))
            fm = QFontMetrics(font)
            num_lines = APP_CONFIG.get(
                "thumbnails_filename_lines", THUMBNAILS_FILENAME_LINES_DEFAULT)
            height += fm.height() * num_lines

        if APP_CONFIG.get("thumbnails_show_rating", True):
            height += 15  # rating rect height

        if APP_CONFIG.get("thumbnails_show_tags", True):
            font.setPointSize(APP_CONFIG.get(
                "thumbnails_tags_font_size", THUMBNAILS_TAGS_FONT_SIZE_DEFAULT))
            fm = QFontMetrics(font)
            num_lines = APP_CONFIG.get(
                "thumbnails_tags_lines", THUMBNAILS_TAGS_LINES_DEFAULT)
            height += fm.height() * num_lines

        height += 5  # bottom padding
        width = thumb_size + 10
        return QSize(width, height)


class ThumbnailSortFilterProxyModel(QSortFilterProxyModel):
    """Proxy model to manage filtering and sorting of thumbnails.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.main_win = parent
        self._data_cache = {}
        self._tag_to_paths_index = defaultdict(set)
        self._all_paths = set()
        self.include_tags = set()
        self.exclude_tags = set()
        self.name_filter = ""
        self.match_mode = "AND"
        self._name_to_paths_index = defaultdict(set)
        self._name_matching_paths = set()
        self._name_filter_active = False
        self._last_name_criteria = None
        self.group_by_folder = False
        self.group_by_day = False
        self.group_by_week = False
        self.group_by_month = False
        self.group_by_year = False
        self.group_by_rating = False
        self.collapsed_groups = set()

        # Optimization: Pre-calculate tag filter results
        self._tag_matching_paths = set()
        self._tag_filter_active = False
        self._last_tag_criteria = None  # (frozenset(inc), frozenset(exc), mode)

    def _tokenize(self, text):
        """Splits text into words for indexing."""
        if not text:
            return []
        # Replace common separators with spaces
        for char in ' ._-()[]{}#@&!+=\\/:;,\'\"':
            text = text.replace(char, ' ')
        return [t for t in text.lower().split() if t]

    def _matches_name_tokens(self, name_lower, search_text):
        """Helper for incremental updates: checks if a name matches search tokens."""
        search_tokens = self._tokenize(search_text)
        if not search_tokens:
            return True
        for s_token in search_tokens:
            if s_token not in name_lower:
                return False
        return True

    def prepare_filter(self):
        """Updates the filter matching set if criteria have changed."""
        if not self.main_win:
            self._data_cache = {}
            return

        # Optimization: Pre-calculate which paths match the current tag criteria.
        current_criteria = (frozenset(self.include_tags),
                            frozenset(self.exclude_tags),
                            self.match_mode)

        if current_criteria != self._last_tag_criteria:
            # Criteria changed: Full re-evaluation required.
            self._last_tag_criteria = current_criteria
            self._tag_filter_active = bool(self.include_tags or self.exclude_tags)

            if not self._tag_filter_active:
                self._tag_matching_paths.clear()
                return

            # Optimized Inverted Index lookup using native set operations
            if self.include_tags:
                tag_sets = [self._tag_to_paths_index[t] for t in self.include_tags]
                if self.match_mode == "AND":
                    self._tag_matching_paths = set.intersection(*tag_sets)
                else:  # OR mode
                    self._tag_matching_paths = set.union(*tag_sets)
            else:
                # Exclusion only mode: start with everything
                self._tag_matching_paths = self._all_paths.copy()

            if self.exclude_tags:
                exclude_sets = [self._tag_to_paths_index[t] for t in self.exclude_tags]
                self._tag_matching_paths -= set.union(*exclude_sets)

        # Name filter optimization via word-based Inverted Index
        if self.name_filter != self._last_name_criteria:
            self._last_name_criteria = self.name_filter
            search_tokens = self._tokenize(self.name_filter)
            self._name_filter_active = bool(search_tokens)

            if self._name_filter_active:
                results = []
                for s_token in search_tokens:
                    token_paths = set()
                    # Search over unique words in index instead of scanning all files
                    for word, path_set in self._name_to_paths_index.items():
                        if s_token in word:
                            token_paths.update(path_set)

                    if not token_paths:
                        results = []
                        break
                    results.append(token_paths)

                if results:
                    self._name_matching_paths = set.intersection(*results)
                else:
                    self._name_matching_paths = set()
            else:
                self._name_matching_paths.clear()

    def _matches_tags(self, tags):
        """Internal helper to check if a set of tags matches current criteria."""
        show = False
        if not self.include_tags:
            show = True
        elif self.match_mode == "AND":
            show = self.include_tags.issubset(tags)
        else:  # OR mode
            show = not self.include_tags.isdisjoint(tags)

        if show and self.exclude_tags:
            if not self.exclude_tags.isdisjoint(tags):
                show = False
        return show

    def clear_cache(self):
        """Clears the internal filter data cache."""
        self._data_cache = {}
        self._tag_to_paths_index.clear()
        self._name_to_paths_index.clear()
        self._all_paths.clear()
        self._tag_matching_paths.clear()
        self._name_matching_paths.clear()
        self._last_tag_criteria = None
        self._last_name_criteria = None

    def add_to_cache(self, path, tags):
        """Adds a single item to the filter cache incrementally."""
        self._all_paths.add(path)
        name_lower = os.path.basename(path).lower()
        new_t_set = set(tags) if tags else set()

        # Update Inverted Index (handles updates correctly for existing items)
        if path in self._data_cache:
            old_t_set, _ = self._data_cache[path]
            for t in old_t_set - new_t_set:
                self._tag_to_paths_index[t].discard(path)
            for t in new_t_set - old_t_set:
                self._tag_to_paths_index[t].add(path)
        else:
            for t in new_t_set:
                self._tag_to_paths_index[t].add(path)

            # Index name tokens only on new items
            tokens = self._tokenize(name_lower)
            for token in tokens:
                self._name_to_paths_index[token].add(path)

        self._data_cache[path] = (new_t_set, name_lower)

        # Incremental update of matching paths avoids full cache scan in prepare_filter
        if self._tag_filter_active:
            if self._matches_tags(new_t_set):
                self._tag_matching_paths.add(path)
            else:
                self._tag_matching_paths.discard(path)

        if self._name_filter_active:
            if self._matches_name_tokens(name_lower, self.name_filter):
                self._name_matching_paths.add(path)
            else:
                self._name_matching_paths.discard(path)

    def remove_from_cache(self, path):
        """Removes an item from the cache and tracking sets."""
        self._all_paths.discard(path)
        if path in self._data_cache:
            tags, name_lower = self._data_cache.pop(path)
            for t in tags:
                self._tag_to_paths_index[t].discard(path)
            for token in self._tokenize(name_lower):
                self._name_to_paths_index[token].discard(path)

        self._tag_matching_paths.discard(path)
        self._name_matching_paths.discard(path)

    def filterAcceptsRow(self, source_row, source_parent):
        """Determines if a row should be visible based on current filters."""
        index = self.sourceModel().index(source_row, 0, source_parent)
        path = index.data(PATH_ROLE)

        if not path:
            item_type = index.data(ITEM_TYPE_ROLE)
            if item_type == 'header':
                return (self.group_by_folder or self.group_by_day or
                        self.group_by_week or self.group_by_month or
                        self.group_by_year or self.group_by_rating)
            return False

        # 1. Optimization: Check tags first using pre-calculated set (O(1) lookup)
        if self._tag_filter_active and path not in self._tag_matching_paths:
            return False

        if self._name_filter_active and path not in self._name_matching_paths:
            return False

        # Filter collapsed groups
        if self.main_win and (self.group_by_folder or self.group_by_day or
                              self.group_by_week or self.group_by_month or
                              self.group_by_year or self.group_by_rating):
            mtime = index.data(MTIME_ROLE)
            rating = index.data(RATING_ROLE)
            _, group_name = self.main_win._get_group_info(path, mtime, rating)
            if group_name in self.collapsed_groups:
                return False

        # Get cached lowercase name for remaining checks
        cached_data = self._data_cache.get(path)
        name_lower = cached_data[1] if cached_data else os.path.basename(path).lower()

        # Filter by filename
        if self.name_filter and self.name_filter not in name_lower:
            return False

        return True

    def lessThan(self, left, right):
        """Custom sorting logic for name and date."""
        sort_role = self.sortRole()

        if sort_role == MTIME_ROLE:
            left_data = self.sourceModel().data(left, sort_role)
            right_data = self.sourceModel().data(right, sort_role)
            # Treat None as 0 for safe comparison
            left_val = left_data if left_data is not None else 0
            right_val = right_data if right_data is not None else 0
            return left_val < right_val

        # Default (DisplayRole) is name sorting.
        # Optimization: Use the pre-calculated lowercase name from the cache
        # to avoid repeated string operations during sorting.
        left_path = self.sourceModel().data(left, PATH_ROLE)
        right_path = self.sourceModel().data(right, PATH_ROLE)

        # Fallback for non-thumbnail items (like headers) or if cache is missing
        if not left_path or not right_path or not self._data_cache:
            l_str = str(self.sourceModel().data(left, Qt.DisplayRole) or "")
            r_str = str(self.sourceModel().data(right, Qt.DisplayRole) or "")
            return l_str.lower() < r_str.lower()

        # Get from cache, with a fallback just in case
        _, left_name_lower = self._data_cache.get(
            left_path, (None, os.path.basename(left_path).lower()))
        _, right_name_lower = self._data_cache.get(
            right_path, (None, os.path.basename(right_path).lower()))

        return left_name_lower < right_name_lower


class MainWindow(QMainWindow):
    """
    The main application window, which serves as the central hub for browsing
    and managing images, including duplicate detection.

    It features a virtualized thumbnail grid for performance, a dockable sidebar
    for metadata editing and filtering, and manages the lifecycle of background
    scanners and individual image viewer windows.
    """

    def __init__(self, cache, args, thread_pool_manager, duplicate_cache):
        """Initializes the MainWindow.

        Args:
            cache (ThumbnailCache): The shared thumbnail cache instance.
            args (list): Command-line arguments passed to the application.
            thread_pool_manager (ThreadPoolManager): The shared thread pool manager.
            duplicate_cache (DuplicateCache): The shared duplicate cache instance.
        """
        super().__init__()
        self.cache = cache
        self.duplicate_cache = duplicate_cache
        self.setWindowTitle(f"{PROG_NAME} v{PROG_VERSION}")
        self.set_app_icon()

        self.viewer_shortcuts = {}
        self.thread_pool_manager = thread_pool_manager
        self.full_history = []
        self.history = []
        self.current_thumb_size = THUMBNAILS_DEFAULT_SIZE
        self.face_names_history = []
        self.pet_names_history = []
        self.body_names_history = []
        self.object_names_history = []
        self.landmark_names_history = []
        self.mru_tags = deque(maxlen=APP_CONFIG.get(
            "tags_menu_max_items", TAGS_MENU_MAX_ITEMS_DEFAULT))
        self.scanner = None
        self.thumbnail_generator = None
        self.show_viewer_status_bar = True
        self.show_filmstrip = False
        self.filmstrip_position = 'bottom'  # bottom, left, top, right
        self.show_faces = False
        self.is_cleaning = False
        self._scan_all = False
        self._suppress_updates = False
        self._is_loading_all = False
        self._force_thumbnail_refresh = False

        self._high_res_mode_active = False
        self._is_loading = False
        self._scanner_last_index = 0
        self._scanner_total_files = 0
        self._current_thumb_tier = 0
        self._open_with_cache = {}  # Cache for mime_type -> list of app info
        self._app_info_cache = {}  # Cache for desktop_file_id
        self._group_info_cache = {}
        self._visible_paths_cache = None  # Cache for visible image paths
        self._path_to_model_index = {}
        self._paths_being_modified_by_app = set()  # For ignoring FS events

        # Keep references to open viewers to manage their lifecycle
        self.viewers = []

        # --- UI Setup ---
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        self.loaded_global_shortcuts = None
        # Top bar with search and actions
        top = QHBoxLayout()
        self.search_input = QComboBox()
        self.search_input.setEditable(True)
        self.search_input.lineEdit().returnPressed.connect(self.on_search_triggered)
        self.search_input.lineEdit().setClearButtonEnabled(True)
        self.search_input.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        top.addWidget(self.search_input, 1)  # Make search input expandable

        for t, f in [(UITexts.SEARCH,
                     self.on_search_triggered),
                     (UITexts.SELECT, self.select_directory)]:
            btn = QPushButton(t)
            btn.clicked.connect(f)
            btn.setFocusPolicy(Qt.NoFocus)
            top.addWidget(btn)

        self.menu_btn = QPushButton()
        self.menu_btn.setIcon(QIcon.fromTheme("application-menu"))
        self.menu_btn.setFocusPolicy(Qt.NoFocus)
        self.menu_btn.clicked.connect(self.show_main_menu)
        self.menu_btn.setFixedHeight(self.search_input.height())
        top.addWidget(self.menu_btn)
        layout.addLayout(top)

        # --- Central Area (Virtualized Thumbnail View) ---
        self.thumbnail_view = QListView()
        self.thumbnail_view.setViewMode(QListView.IconMode)
        self.thumbnail_view.setResizeMode(QListView.Adjust)
        self.thumbnail_view.setMovement(QListView.Static)
        self.thumbnail_view.setUniformItemSizes(True)
        self.thumbnail_view.setSpacing(5)
        self.thumbnail_view.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.thumbnail_view.setContextMenuPolicy(Qt.CustomContextMenu)
        bg_color = APP_CONFIG.get("thumbnails_bg_color", THUMBNAILS_BG_COLOR_DEFAULT)
        self.thumbnail_view.setStyleSheet(f"background-color: {bg_color};")
        self.thumbnail_view.customContextMenuRequested.connect(self.show_context_menu)
        self.thumbnail_view.doubleClicked.connect(self.on_view_double_clicked)

        self.thumbnail_model = QStandardItemModel(self)
        self.proxy_model = ThumbnailSortFilterProxyModel(self)
        self.proxy_model.setSourceModel(self.thumbnail_model)
        self.proxy_model.setDynamicSortFilter(False)  # Manual invalidation

        self.thumbnail_view.setModel(self.proxy_model)
        self.thumbnail_view.selectionModel().selectionChanged.connect(
            self.on_selection_changed)

        self.delegate = ThumbnailDelegate(self)
        self.thumbnail_view.setItemDelegate(self.delegate)

        layout.addWidget(self.thumbnail_view)

        # Bottom bar with status and controls
        bot = QHBoxLayout()

        self.btn_load_all = QPushButton()
        self.btn_load_all.setFixedSize(24, 24)
        self.btn_load_all.setFocusPolicy(Qt.NoFocus)
        self.btn_load_all.clicked.connect(self.load_all_images)
        self.update_load_all_button_state()
        self.btn_load_all.hide()
        bot.addWidget(self.btn_load_all)

        self.btn_load_more = QPushButton()
        self.btn_load_more.setFixedSize(24, 24)
        self.btn_load_more.setFocusPolicy(Qt.NoFocus)
        self.btn_load_more.setToolTip(UITexts.LOAD_MORE_TOOLTIP)
        self.btn_load_more.clicked.connect(self.load_more_images)
        self.btn_load_more.hide()
        bot.addWidget(self.btn_load_more)

        self.btn_cancel_duplicates = QPushButton()
        self.btn_cancel_duplicates.setIcon(QIcon.fromTheme("process-stop"))
        self.btn_cancel_duplicates.setFixedSize(22, 22)
        self.btn_cancel_duplicates.setToolTip(UITexts.CANCEL)
        self.btn_cancel_duplicates.setFocusPolicy(Qt.NoFocus)
        self.btn_cancel_duplicates.hide()
        self.btn_cancel_duplicates.clicked.connect(self.cancel_duplicate_detection)
        bot.addWidget(self.btn_cancel_duplicates)

        self.progress_bar = CircularProgressBar(self)
        self.progress_bar.hide()
        bot.addWidget(self.progress_bar)

        self.status_counter_lbl = QLabel("")
        self.status_counter_lbl.hide()
        bot.addWidget(self.status_counter_lbl)

        self.status_lbl = QLabel(UITexts.READY)
        bot.addWidget(self.status_lbl)

        self.fs_watcher_status_lbl = QLabel()
        self.fs_watcher_status_lbl.setToolTip(UITexts.FS_WATCHER_TOOLTIP)
        self.fs_watcher_status_lbl.hide()
        bot.addWidget(self.fs_watcher_status_lbl)

        # Timer to hide progress bar with delay
        self.hide_progress_timer = QTimer(self)
        self.hide_progress_timer.setSingleShot(True)
        self.hide_progress_timer.timeout.connect(self.progress_bar.hide)

        bot.addStretch()

        self.filtered_count_lbl = QLabel(UITexts.FILTERED_ZERO)
        bot.addWidget(self.filtered_count_lbl)

        self.view_mode_combo = QComboBox()
        self.view_mode_combo.addItems([
            UITexts.VIEW_MODE_FLAT, UITexts.VIEW_MODE_FOLDER, UITexts.VIEW_MODE_DAY,
            UITexts.VIEW_MODE_WEEK, UITexts.VIEW_MODE_MONTH, UITexts.VIEW_MODE_YEAR,
            UITexts.VIEW_MODE_RATING
        ])
        self.view_mode_combo.setFocusPolicy(Qt.NoFocus)
        self.view_mode_combo.currentIndexChanged.connect(self.on_view_mode_changed)
        bot.addWidget(self.view_mode_combo)

        self.sort_combo = QComboBox()
        self.sort_combo.addItems([UITexts.SORT_NAME_ASC, UITexts.SORT_NAME_DESC,
                                  UITexts.SORT_DATE_ASC, UITexts.SORT_DATE_DESC])
        self.sort_combo.setFocusPolicy(Qt.NoFocus)
        self.sort_combo.currentIndexChanged.connect(self.on_sort_changed)
        bot.addWidget(self.sort_combo)

        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(64, 512)
        self.slider.setSingleStep(8)
        self.slider.setPageStep(8)
        self.slider.setValue(THUMBNAILS_DEFAULT_SIZE)
        self.slider.setMaximumWidth(100)
        self.slider.setMinimumWidth(75)
        self.slider.setFocusPolicy(Qt.NoFocus)
        self.slider.valueChanged.connect(self.on_slider_changed)
        bot.addWidget(self.slider)

        self.size_label = QLabel(f"{self.current_thumb_size}px")
        self.size_label.setFixedWidth(50)
        bot.addWidget(self.size_label)

        layout.addLayout(bot)

        # --- Main Dock ---
        self.main_dock = QDockWidget(UITexts.MAIN_DOCK_TITLE, self)
        self.main_dock.setObjectName("MainDock")
        self.main_dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)

        self.tags_tabs = QTabWidget()

        # Tab 1: Tags (Edit)
        self.tag_edit_widget = TagEditWidget(self)
        self.tag_edit_widget.tags_updated.connect(self.on_tags_edited)

        self.tags_tabs.addTab(self.tag_edit_widget, UITexts.TAGS_TAB)
        self.tags_tabs.currentChanged.connect(self.on_tags_tab_changed)

        # Tab 2: Information (Rating, Comment)
        self.info_widget = QWidget()
        info_layout = QVBoxLayout(self.info_widget)
        self.rating_widget = RatingWidget()
        self.rating_widget.rating_updated.connect(self.on_rating_edited)
        info_layout.addWidget(self.rating_widget)
        self.comment_widget = CommentWidget()
        info_layout.addWidget(self.comment_widget)
        self.tags_tabs.addTab(self.info_widget, UITexts.INFO_TAB)
        self.tags_tabs.currentChanged.connect(self.on_tags_tab_changed)

        # Timer for debouncing filter text input to prevent UI freezing
        self.filter_input_timer = QTimer(self)
        self.filter_input_timer.setSingleShot(True)
        self.filter_input_timer.setInterval(300)
        self.filter_input_timer.timeout.connect(self.apply_filters)

        # Timer for debouncing tag list updates in the filter tab for performance
        self.filter_refresh_timer = QTimer(self)
        self.filter_refresh_timer.setSingleShot(True)
        self.filter_refresh_timer.setInterval(1500)
        self.filter_refresh_timer.timeout.connect(self.update_tag_list)

        # Tab 3: Filter by Tags and Name
        self.filter_widget = QWidget()
        filter_layout = QVBoxLayout(self.filter_widget)

        self.filter_name_input = QLineEdit()
        self.filter_name_input.setPlaceholderText(UITexts.FILTER_NAME_PLACEHOLDER)
        # Use debounce timer instead of direct connection
        self.filter_name_input.textChanged.connect(self.filter_input_timer.start)
        self.filter_name_input.setClearButtonEnabled(True)
        filter_layout.addWidget(self.filter_name_input)

        mode_layout = QHBoxLayout()
        self.filter_mode_group = QButtonGroup(self)
        rb_and = QRadioButton(UITexts.FILTER_AND)
        rb_or = QRadioButton(UITexts.FILTER_OR)
        rb_and.setChecked(True)
        self.filter_mode_group.addButton(rb_and)
        self.filter_mode_group.addButton(rb_or)
        mode_layout.addWidget(rb_and)
        mode_layout.addWidget(rb_or)

        btn_invert = QPushButton(UITexts.FILTER_INVERT)
        btn_invert.setFixedWidth(60)
        btn_invert.clicked.connect(self.invert_tag_selection)
        mode_layout.addWidget(btn_invert)
        filter_layout.addLayout(mode_layout)
        self.filter_mode_group.buttonClicked.connect(self.apply_filters)

        self.filter_stats_lbl = QLabel()
        self.filter_stats_lbl.setAlignment(Qt.AlignCenter)
        self.filter_stats_lbl.setStyleSheet("color: gray; font-style: italic;")
        self.filter_stats_lbl.hide()
        filter_layout.addWidget(self.filter_stats_lbl)

        self.tag_search_input = QLineEdit()
        self.tag_search_input.setPlaceholderText(UITexts.TAG_SEARCH_PLACEHOLDER)
        self.tag_search_input.textChanged.connect(self.filter_tags_list)
        self.tag_search_input.setClearButtonEnabled(True)
        filter_layout.addWidget(self.tag_search_input)

        self.tags_list = QTableWidget()
        self.tags_list.setColumnCount(2)
        self.tags_list.setHorizontalHeaderLabels(
            [UITexts.FILTER_TAG_COLUMN, UITexts.FILTER_NOT_COLUMN])
        self.tags_list.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tags_list.horizontalHeader().setSectionResizeMode(1, QHeaderView.Fixed)
        self.tags_list.setColumnWidth(1, 40)
        self.tags_list.verticalHeader().setVisible(False)
        self.tags_list.setSelectionMode(QAbstractItemView.NoSelection)
        self.tags_list.itemChanged.connect(self.on_tag_changed)
        filter_layout.addWidget(self.tags_list)

        self.tags_tabs.addTab(self.filter_widget, UITexts.TAG_FILTER_TAB)

        # Tab 4: Favorites
        self.favorites_tab = FavoritesWidget(self)
        self.tags_tabs.addTab(self.favorites_tab, UITexts.FAVORITES_TAB)

        # Tab 5: Layouts
        self.is_xcb = QApplication.platformName() == "xcb"
        if self.is_xcb:
            self.layouts_tab = LayoutsWidget(self)
            self.tags_tabs.addTab(self.layouts_tab, UITexts.LAYOUTS_TAB)

        # Tab 6: History
        self.history_tab = HistoryWidget(self)
        self.tags_tabs.addTab(self.history_tab, UITexts.HISTORY_TAB)

        self.main_dock.setWidget(self.tags_tabs)
        self.addDockWidget(Qt.RightDockWidgetArea, self.main_dock)

        self.main_dock.hide()

        # Timer for debouncing UI refreshes to keep it smooth on resize
        self.thumbnails_refresh_timer = QTimer(self)
        self.thumbnails_refresh_timer.setSingleShot(True)
        refresh_interval = APP_CONFIG.get("thumbnails_refresh_interval",
                                          THUMBNAILS_REFRESH_INTERVAL_DEFAULT)
        self.thumbnails_refresh_timer.setInterval(refresh_interval)
        self.thumbnails_refresh_timer.timeout.connect(
            self.thumbnail_view.updateGeometries)

        # Queue and timer for incremental model updates (prevents UI freeze
        # on fast scan)
        self._model_update_queue = deque()
        self._model_update_timer = QTimer(self)
        self._model_update_timer.setInterval(30)  # ~30 FPS updates
        self._model_update_timer.timeout.connect(self._process_model_update_queue)

        # Data collection and model rebuilding logic
        self.found_items_data = []
        self._known_paths = set()
        self.cache.thumbnail_loaded.connect(self.on_thumbnail_loaded)
        self.rebuild_timer = QTimer(self)
        self.rebuild_timer.setSingleShot(True)
        self.rebuild_timer.setInterval(150)  # Rebuild view periodically during scan
        self.rebuild_timer.timeout.connect(self.rebuild_view)

        # Timer to resume scanning after user interaction stops
        self.duplicate_detector = None  # Worker for duplicate detection
        self.resume_scan_timer = QTimer(self)
        self.resume_scan_timer.setSingleShot(True)
        self.resume_scan_timer.setInterval(400)
        self.resume_scan_timer.timeout.connect(self._resume_scanning)

        # # Timer for debouncing tag list updates in the filter tab for performance
        # self.filter_refresh_timer = QTimer(self)
        # self.filter_refresh_timer.setSingleShot(True)
        # self.filter_refresh_timer.setInterval(1500)
        # self.filter_refresh_timer.timeout.connect(self.update_tag_list)

        # Monitor viewport resize to recalculate item layout (for headers)
        self.thumbnail_view.viewport().installEventFilter(self)
        self.thumbnail_view.verticalScrollBar().valueChanged.connect(
            self._on_scroll_interaction)

        # Initialize FileSystemWatcher
        self.fs_watcher = FileSystemWatcher()
        self.fs_watcher.file_created.connect(self.on_fs_file_created)
        self.fs_watcher.file_deleted.connect(self.on_fs_file_deleted)
        self.fs_watcher.file_modified.connect(self.on_fs_file_modified)
        self.fs_watcher.directory_modified.connect(self.on_fs_directory_modified)
        self.fs_watcher.file_moved.connect(self.on_fs_file_moved)
        self.fs_watcher.directory_moved.connect(self.on_fs_directory_moved)
        self.fs_watcher.monitoring_status_changed.connect(
            self.on_fs_watcher_status_changed)

        # Set up callback for metadata managers
        from .metadatamanager import set_app_modified_callback
        set_app_modified_callback(self._mark_path_as_app_modified)

        # Batching for file creation events
        self._fs_created_queue = set()
        self._fs_created_timer = QTimer(self)
        self._fs_created_timer.setSingleShot(True)
        self._fs_created_timer.setInterval(1000)  # 1 second debounce
        self._fs_created_timer.timeout.connect(self._process_fs_created_batch)

        # Debounce timer for full refreshes on directory modifications
        self._fs_dir_refresh_timer = QTimer(self)
        self._fs_dir_refresh_timer.setSingleShot(True)
        self._fs_dir_refresh_timer.setInterval(2500)  # 2.5 seconds debounce
        self._fs_dir_refresh_timer.timeout.connect(self.refresh_content)

        # Initial configuration loading
        self.load_config()
        self.load_full_history()

        # Initialize the shortcut controller (after config is loaded)
        self.shortcut_controller = AppShortcutController(self)
        self.favorites_tab.favorites_changed.connect(
            self.shortcut_controller.refresh_favorite_shortcuts)

        self._apply_global_stylesheet()
        # Set the initial thumbnail generation tier based on the loaded config size
        self._current_thumb_tier = self._get_tier_for_size(self.current_thumb_size)
        # SCANNER_GENERATE_SIZES = [self._current_thumb_tier]

        if hasattr(self, 'history_tab'):
            self.history_tab.refresh_list()

        # Handle initial arguments passed from the command line
        should_hide = False
        if args:
            path = " ".join(args).strip()
            # Fix `file:/` URLs from file managers
            if path.startswith("file:/"):
                path = path[6:]
            full_path = os.path.abspath(os.path.expanduser(path))
            if os.path.isfile(full_path) or path.startswith("layout:/"):
                # If a single file or a layout is passed, hide the main window
                should_hide = True

            self.handle_initial_args(args)
        elif self.history:
            # If no args, load the last used path or search from history
            last_term = self.history[0]
            # Check if the last item was a single file to decide on visibility
            if last_term.startswith("file:/") or last_term.startswith("/"):
                p = last_term[6:] if last_term.startswith("file:/") else last_term
                if os.path.isfile(os.path.abspath(os.path.expanduser(p))):
                    should_hide = True
                    self._scan_all = False

            self.process_term(last_term)

        if should_hide:
            self.hide()
        else:
            self.show()
            self.setFocus()

    def _process_model_update_queue(self):
        """Processes a chunk of the pending model updates."""
        if not self._model_update_queue:
            self._model_update_timer.stop()
            return

        # Process a chunk of items (e.g. 100 items per tick) to maintain responsiveness
        chunk = []
        try:
            for _ in range(100):
                chunk.append(self._model_update_queue.popleft())
        except IndexError:
            pass

        if chunk:
            self._incremental_add_to_model(chunk)

        # Stop if empty, otherwise it continues on next tick
        if not self._model_update_queue:
            self._model_update_timer.stop()
            # Ensure filter stats are updated at the end
            self.apply_filters()

    def _apply_global_stylesheet(self):
        """Applies application-wide stylesheets from config."""
        tooltip_bg = APP_CONFIG.get("thumbnails_tooltip_bg_color",
                                    THUMBNAILS_TOOLTIP_BG_COLOR_DEFAULT)
        tooltip_fg = APP_CONFIG.get(
            "thumbnails_tooltip_fg_color", THUMBNAILS_TOOLTIP_FG_COLOR_DEFAULT)

        # Using QPalette is often more robust for platform-themed widgets like tooltips,
        # as it's more likely to be respected by the style engine (e.g., KDE Breeze)
        # than a stylesheet alone.
        palette = QApplication.palette()
        palette.setColor(QPalette.ToolTipBase, QColor(tooltip_bg))
        palette.setColor(QPalette.ToolTipText, QColor(tooltip_fg))
        QApplication.setPalette(palette)

        qss = f"""
            QToolTip {{
                background-color: {tooltip_bg};
                color: {tooltip_fg};
                border: 1px solid #555;
                padding: 4px;
            }}
        """
        QApplication.instance().setStyleSheet(qss)

    def _on_scroll_interaction(self, value):
        """Pauses scanning during scroll to keep UI fluid."""
        if self.scanner and self.scanner.isRunning():
            self.thread_pool_manager.set_user_active(True)
            self.scanner.set_paused(True)
            self.resume_scan_timer.start()

    def _resume_scanning(self):
        """Resumes scanning after interaction pause."""
        if self.scanner:
            self.thread_pool_manager.set_user_active(False)
            # Prioritize currently visible images
            visible_paths = self.get_visible_image_paths()
            self.scanner.prioritize(visible_paths)
            self.scanner.set_paused(False)

    # --- Layout Management ---
    def save_layout(self, target_path=None):
        """Saves the current window and viewer layout to a JSON file."""
        if not self.is_xcb:
            return

        # Ensure the layouts directory exists
        os.makedirs(LAYOUTS_DIR, exist_ok=True)

        filename = None
        name = ""

        if target_path:
            filename = target_path
            name = os.path.basename(filename).replace(".layout", "")

            # Confirm overwrite if the file already exists
            confirm = QMessageBox(self)
            confirm.setIcon(QMessageBox.Warning)
            confirm.setWindowTitle(UITexts.LAYOUT_EXISTS_TITLE)
            confirm.setText(UITexts.LAYOUT_EXISTS_TEXT.format(name))
            confirm.setInformativeText(UITexts.LAYOUT_EXISTS_INFO)
            confirm.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
            confirm.setDefaultButton(QMessageBox.No)
            if confirm.exec() != QMessageBox.Yes:
                return
        else:
            # Prompt for a new layout name
            while True:
                name, ok = QInputDialog.getText(
                    self, UITexts.SAVE_LAYOUT_TITLE, UITexts.SAVE_LAYOUT_TEXT)
                if not ok or not name.strip():
                    return

                filename = os.path.join(LAYOUTS_DIR, f"{name.strip()}.layout")
                if os.path.exists(filename):
                    confirm = QMessageBox(self)
                    confirm.setIcon(QMessageBox.Warning)
                    confirm.setWindowTitle(UITexts.LAYOUT_EXISTS_TITLE)
                    confirm.setText(UITexts.LAYOUT_EXISTS_TEXT.format(name.strip()))
                    confirm.setInformativeText(UITexts.LAYOUT_EXISTS_INFO)
                    confirm.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
                    confirm.setDefaultButton(QMessageBox.No)
                    if confirm.exec() == QMessageBox.Yes:
                        break
                else:
                    break

        # Main window data to be saved
        # layout_data = {
        #     "main_window": {
        #         "visible": self.isVisible(),
        #         "geometry": {
        #             "x": self.x(), "y": self.y(),
        #             "w": self.width(), "h": self.height()
        #         },
        #         "search_text": self.search_input.currentText(),
        #         "selected_path": self.get_current_selected_path()
        #     },
        #     "viewers": []
        # }
        layout_data = {
            "main_window": {
                "visible": self.isVisible(),
                "search_text": self.search_input.currentText(),
                "geometry": {
                    "x": self.x(), "y": self.y(),
                    "w": self.width(), "h": self.height()
                },
                "window_state": self.saveState().toBase64().data().decode(),
                "selected_path": self.get_current_selected_path()
            },
            "viewers": []
        }

        # Data from open viewers
        # We filter to ensure the widget is still alive and visible
        active_viewers = [v for v in self.viewers
                          if isinstance(v, ImageViewer) and v.isVisible()]

        for v in active_viewers:
            layout_data["viewers"].append(v.get_state())

        try:
            with open(filename, 'w') as f:
                json.dump(layout_data, f, indent=4)
            self.status_lbl.setText(UITexts.LAYOUT_SAVED.format(name))
            if hasattr(self, 'layouts_tab'):
                self.layouts_tab.refresh_list()
        except Exception as e:
            QMessageBox.critical(
                self, UITexts.ERROR, UITexts.ERROR_SAVING_LAYOUT.format(e))

    def load_layout_dialog(self):
        """Shows a dialog to select and load a layout."""
        if not self.is_xcb:
            return

        if not os.path.exists(LAYOUTS_DIR):
            QMessageBox.information(self, UITexts.INFO, UITexts.NO_LAYOUTS_FOUND)
            return

        files = glob.glob(os.path.join(LAYOUTS_DIR, "*.layout"))
        if not files:
            QMessageBox.information(self, UITexts.INFO, UITexts.NO_LAYOUTS_FOUND)
            return

        # Get clean names without extension
        items = [os.path.basename(f).replace(".layout", "") for f in files]
        items.sort()

        item, ok = QInputDialog.getItem(
            self, UITexts.LOAD_LAYOUT_TITLE, UITexts.SELECT_LAYOUT, items, 0, False)
        if ok and item:
            full_path = os.path.join(LAYOUTS_DIR, f"{item}.layout")
            self.restore_layout(full_path)

    def close_all_viewers(self):
        """Closes all currently open image viewer windows gracefully."""
        for v in list(self.viewers):
            try:
                v.close()
            except Exception:
                pass
        self.viewers.clear()

    def restore_layout(self, filepath):
        """Restores the complete application state from a layout file."""
        try:
            with open(filepath, 'r') as f:
                data = json.load(f)
        except Exception as e:
            QMessageBox.critical(self, UITexts.ERROR,
                                 f"Failed to load layout file: {e}")
            return

        # Ensure main window is visible before restoring
        if not self.isVisible():
            self.show()

        # Clear any currently open viewers
        self.close_all_viewers()

        # Restore main window state
        mw_data = data.get("main_window", {})

        # Restore main window geometry and state (including docks)
        # if "geometry" in mw_data:
        #     g = mw_data["geometry"]
        #     self.setGeometry(g["x"], g["y"], g["w"], g["h"])

        selected_path = mw_data.get("selected_path")
        select_paths = [selected_path] if selected_path else None

        if "window_state" in mw_data:
            self.restoreState(
                QByteArray.fromBase64(mw_data["window_state"].encode()))

        # Restore viewers
        viewers_data = data.get("viewers", [])

        # Gather all unique paths from the viewers to scan
        paths = []
        for v_data in viewers_data:
            path = v_data.get("path")
            if path not in paths:
                paths.append(path)

        # Set scan mode and search text
        self._scan_all = True
        search_text = mw_data.get("search_text", "")

        # Restore main window visibility
        if mw_data.get("visible", True):
            self.show()
            self.activateWindow()
        else:
            self.hide()

        # Create and restore each viewer
        # 4. Restore Viewers
        for v_data in viewers_data:
            path = v_data.get("path")
            if os.path.exists(path):
                # Create viewer with a temporary list containing only its image.
                # The full list will be synced later after the scan completes.
                viewer = ImageViewer(self.cache, [path], 0, initial_tags=None,
                                     initial_rating=0, parent=self,
                                     restore_config=v_data, persistent=True)
                # Apply saved geometry
                v_geo = v_data.get("geometry")
                if v_geo:
                    viewer.setGeometry(v_geo["x"], v_geo["y"], v_geo["w"], v_geo["h"])

                self._setup_viewer_sync(viewer)
                self.viewers.append(viewer)
                viewer.destroyed.connect(
                    lambda obj=viewer: self.viewers.remove(obj)
                    if obj in self.viewers else None)
                viewer.show()

        self.status_lbl.setText(UITexts.LAYOUT_RESTORED)

        # 5. Start scanning all parent directories of the images in the layout
        unique_dirs = list({str(Path(p).parent) for p in paths})
        for d in unique_dirs:
            if d not in paths:
                paths.append(d)

        self.start_scan([p.strip() for p in paths if p.strip()
                         and os.path.exists(os.path.expanduser(p.strip()))],
                        select_paths=select_paths)

        if search_text:
            self.search_input.setEditText(search_text)

    # --- UI and Menu Logic ---
    def show_main_menu(self):
        """Displays the main application menu."""
        menu = QMenu(self)

        # Actions to show different tabs in the dock
        show_tags_action = menu.addAction(QIcon.fromTheme("document-properties"),
                                          UITexts.MENU_SHOW_TAGS)
        show_tags_action.triggered.connect(
            lambda: self.open_sidebar_tab(self.tags_tabs.indexOf(self.tag_edit_widget)))

        show_info_action = menu.addAction(QIcon.fromTheme("dialog-information"),
                                          UITexts.MENU_SHOW_INFO)
        show_info_action.triggered.connect(
            lambda: self.open_sidebar_tab(self.tags_tabs.indexOf(self.info_widget)))

        show_favorites_action = menu.addAction(QIcon.fromTheme("bookmarks"),
                                               UITexts.MENU_SHOW_FAVORITES)
        f_idx = self.tags_tabs.indexOf(self.favorites_tab)
        show_favorites_action.triggered.connect(lambda: self.open_sidebar_tab(f_idx))

        show_filter_action = menu.addAction(QIcon.fromTheme("view-filter"),
                                            UITexts.MENU_SHOW_FILTER)
        show_filter_action.triggered.connect(
            lambda: self.open_sidebar_tab(self.tags_tabs.indexOf(self.filter_widget)))

        if self.is_xcb:
            show_layouts_action = menu.addAction(QIcon.fromTheme("view-grid"),
                                                 UITexts.MENU_SHOW_LAYOUTS)
            l_idx = self.tags_tabs.indexOf(self.layouts_tab)
            show_layouts_action.triggered.connect(lambda: self.open_sidebar_tab(l_idx))

        show_history_action = menu.addAction(QIcon.fromTheme("view-history"),
                                             UITexts.MENU_SHOW_HISTORY)
        h_idx = self.tags_tabs.indexOf(self.history_tab)
        show_history_action.triggered.connect(lambda: self.open_sidebar_tab(h_idx))

        menu.addSeparator()

        # Cache management actions
        count, size = self.cache.get_cache_stats()
        size_mb = size / (1024 * 1024)

        disk_cache_size_mb = 0
        disk_cache_path = os.path.join(CACHE_PATH, "data.mdb")
        if os.path.exists(disk_cache_path):
            disk_cache_size_bytes = os.path.getsize(disk_cache_path)
            disk_cache_size_mb = disk_cache_size_bytes / (1024 * 1024)

        cache_menu = menu.addMenu(QIcon.fromTheme("drive-harddisk"), UITexts.MENU_CACHE)

        clean_cache_action = cache_menu.addAction(QIcon.fromTheme("edit-clear-all"),
                                                  UITexts.MENU_CLEAN_CACHE)
        clean_cache_action.triggered.connect(self.clean_thumbnail_cache)

        clear_cache_action = cache_menu.addAction(
            QIcon.fromTheme("user-trash-full"),
            UITexts.MENU_CLEAR_CACHE.format(count, size_mb, disk_cache_size_mb))
        clear_cache_action.triggered.connect(self.clear_thumbnail_cache)

        clean_metadata_action = cache_menu.addAction(
            QIcon.fromTheme("edit-clear"), UITexts.MENU_CLEAN_METADATA_CACHE)
        clean_metadata_action.triggered.connect(self.clean_stale_metadata_cache)

        clean_directory_action = cache_menu.addAction(
            QIcon.fromTheme("edit-clear"), UITexts.MENU_CLEAN_DIRECTORY_CACHE)
        clean_directory_action.triggered.connect(self.clean_stale_directory_cache)

        menu.addSeparator()

        duplicates_menu = menu.addMenu(
            QIcon.fromTheme("edit-find-replace"), UITexts.MENU_DUPLICATES)
        duplicates_menu.setEnabled(HAVE_IMAGEHASH)

        detect_current_action = duplicates_menu.addAction(
            UITexts.MENU_DETECT_CURRENT_SEARCH)
        detect_current_action.triggered.connect(self.start_duplicate_detection)

        force_full_action = duplicates_menu.addAction(UITexts.MENU_FORCE_FULL_ANALYSIS)
        force_full_action.triggered.connect(
            lambda: self.start_duplicate_detection(force_full=True))

        detect_all_action = duplicates_menu.addAction(UITexts.MENU_DETECT_ALL)
        detect_all_action.triggered.connect(self.detect_all_duplicates)

        force_full_all_action = duplicates_menu.addAction(
            UITexts.MENU_FORCE_FULL_ALL_ANALYSIS)
        force_full_all_action.triggered.connect(
            lambda: self.detect_all_duplicates(force_full=True))

        review_ignored_action = duplicates_menu.addAction(UITexts.MENU_REVIEW_IGNORED)
        review_ignored_action.triggered.connect(self.review_ignored_duplicates)

        duplicates_menu.addSeparator()

        clean_hashes_action = duplicates_menu.addAction(
            QIcon.fromTheme("edit-clear-all"), UITexts.MENU_CLEAN_UP_HASHES)
        clean_hashes_action.triggered.connect(self.clean_duplicate_hashes)

        repair_index_action = duplicates_menu.addAction(UITexts.MENU_REPAIR_DATABASE)
        repair_index_action.triggered.connect(self.repair_duplicate_index)

        clear_exceptions_action = duplicates_menu.addAction(
            UITexts.MENU_CLEAR_EXCEPTIONS)
        clear_exceptions_action.triggered.connect(self.clear_ignored_duplicates)

        if self.duplicate_cache:
            count, size_bytes = self.duplicate_cache.get_hash_stats()
            size_mb = size_bytes / (1024 * 1024)
            clear_hashes_action = duplicates_menu.addAction(
                QIcon.fromTheme("user-trash-full"),
                UITexts.MENU_CLEAR_HASHES.format(count, size_mb))
            clear_hashes_action.triggered.connect(self.clear_duplicate_hashes)

        menu.addSeparator()

        show_shortcuts_action = menu.addAction(QIcon.fromTheme("help-keys"),
                                               UITexts.MENU_SHOW_SHORTCUTS)
        show_shortcuts_action.triggered.connect(self.show_shortcuts_help)

        menu.addSeparator()

        # --- Language Menu ---
        language_menu = menu.addMenu(QIcon.fromTheme("preferences-desktop-locale"),
                                     UITexts.MENU_LANGUAGE)
        lang_group = QActionGroup(self)
        lang_group.setExclusive(True)
        lang_group.triggered.connect(self._on_language_changed)

        for code, name in SUPPORTED_LANGUAGES.items():
            action = QAction(name, self, checkable=True)
            action.setData(code)
            if code == APP_CONFIG.get("language", DEFAULT_LANGUAGE):
                action.setChecked(True)
            language_menu.addAction(action)
            lang_group.addAction(action)

        menu.addSeparator()

        settings_action = menu.addAction(QIcon.fromTheme("preferences-system"),
                                         UITexts.MENU_SETTINGS)
        settings_action.triggered.connect(self.show_settings_dialog)

        menu.addSeparator()

        about_action = menu.addAction(QIcon.fromTheme("help-about"), UITexts.MENU_ABOUT)
        about_action.triggered.connect(self.show_about_dialog)

        menu.exec(self.menu_btn.mapToGlobal(QPoint(0, self.menu_btn.height())))

    def detect_all_duplicates(self, force_full=False):
        """Gathers files from whitelist (respecting blacklist) and runs detector."""
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            paths = self._gather_files_for_duplicates()
        finally:
            QApplication.restoreOverrideCursor()

        if paths is None:
            QMessageBox.warning(
                self, UITexts.WARNING,
                UITexts.DUPLICATE_WHITELIST_EMPTY)
            return

        if not paths:
            QMessageBox.information(
                self, UITexts.DUPLICATE_DETECTION_TITLE, UITexts.DUPLICATE_NONE_FOUND)
            return

        # By default, we use optimized (incremental) mode to avoid repeating
        # comparisons.
        self.start_duplicate_detection(force_full=force_full, custom_paths=paths)

    def _gather_files_for_duplicates(self):
        """Helper to collect image paths based on whitelist and blacklist settings."""
        whitelist_str = APP_CONFIG.get("duplicate_whitelist", "")
        blacklist_str = APP_CONFIG.get("duplicate_blacklist", "")

        whitelist = [os.path.abspath(os.path.expanduser(p.strip()))
                     for p in whitelist_str.split(',') if p.strip()]
        blacklist = [os.path.abspath(os.path.expanduser(p.strip()))
                     for p in blacklist_str.split(',') if p.strip()]

        if not whitelist:
            return None

        all_paths = []
        blacklist_set = set(blacklist)

        for root_path in whitelist:
            if not os.path.exists(root_path):
                continue

            for root, dirs, files in os.walk(root_path):
                abs_root = os.path.abspath(root)
                # Prune dirs to stop walking into blacklisted paths
                dirs[:] = [d for d in dirs
                           if os.path.join(abs_root, d) not in blacklist_set]

                if abs_root in blacklist_set:
                    continue

                for f in files:
                    if os.path.splitext(f)[1].lower() in IMAGE_EXTENSIONS:
                        full_p = os.path.join(abs_root, f)
                        if full_p not in blacklist_set:
                            all_paths.append(full_p)
        return all_paths

    def clean_duplicate_hashes(self):
        if self.duplicate_cache:
            count = self.duplicate_cache.clean_stale_hashes()
            self.status_lbl.setText(f"Cleaned up {count} stale hash entries.")

    def repair_duplicate_index(self):
        """Regenerates the BK-Tree and reverse index."""
        if not self.duplicate_cache:
            return

        if self.duplicate_detector and self.duplicate_detector.isRunning():
            QMessageBox.information(self, UITexts.DUPLICATE_DETECTION_TITLE,
                                    UITexts.DUPLICATE_ALREADY_RUNNING)
            return

        self.status_lbl.setText(UITexts.REPAIRING_DATABASE)
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            self.duplicate_cache.regenerate_bktree()
            self.status_lbl.setText(UITexts.READY)
        finally:
            QApplication.restoreOverrideCursor()

    def clear_ignored_duplicates(self):
        """Clears the ignored pairs database after user confirmation."""
        if not self.duplicate_cache:
            return

        confirm = QMessageBox(self)
        confirm.setIcon(QMessageBox.Question)
        confirm.setWindowTitle(UITexts.CONFIRM_CLEAR_EXCEPTIONS_TITLE)
        confirm.setText(UITexts.CONFIRM_CLEAR_EXCEPTIONS_TEXT)
        confirm.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        confirm.setDefaultButton(QMessageBox.No)

        if confirm.exec() == QMessageBox.Yes:
            self.duplicate_cache.clear_exceptions()
            self.status_lbl.setText(UITexts.READY)

    def clear_duplicate_hashes(self):
        if not self.duplicate_cache:
            return

        confirm = QMessageBox(self)
        confirm.setIcon(QMessageBox.Warning)
        confirm.setWindowTitle(UITexts.CONFIRM_CLEAR_HASHES_TITLE)
        confirm.setText(UITexts.CONFIRM_CLEAR_HASHES_TEXT)
        confirm.setInformativeText(UITexts.CONFIRM_CLEAR_HASHES_INFO)
        confirm.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        confirm.setDefaultButton(QMessageBox.No)
        if confirm.exec() != QMessageBox.Yes:
            return

        self.duplicate_cache.clear_hashes()
        self.status_lbl.setText("Duplicate hash cache cleared.")

    def review_ignored_duplicates(self):
        if not self.duplicate_cache:
            return
        ignored = self.duplicate_cache.get_all_exceptions()
        if not ignored:
            QMessageBox.information(
                self, UITexts.DUPLICATE_DETECTION_TITLE, UITexts.DUPLICATE_NONE_FOUND)
            return
        dialog = DuplicateManagerDialog(
            ignored, self.duplicate_cache, self, review_mode=True)
        dialog.show()

    def show_about_dialog(self):
        """Shows the 'About' dialog box."""
        QMessageBox.about(self, UITexts.MENU_ABOUT_TITLE.format(PROG_NAME),
                          UITexts.MENU_ABOUT_TEXT.format(
                              PROG_NAME, PROG_VERSION, PROG_AUTHOR))

    def show_shortcuts_help(self):
        if hasattr(self, 'shortcut_controller') and self.shortcut_controller:
            self.shortcut_controller.show_help()

    def show_settings_dialog(self):
        dlg = SettingsDialog(self)
        if dlg.exec():
            # Update settings that affect the main window immediately
            new_interval = APP_CONFIG.get("thumbnails_refresh_interval",
                                          THUMBNAILS_REFRESH_INTERVAL_DEFAULT)
            self.thumbnails_refresh_timer.setInterval(new_interval)

            new_max_tags = APP_CONFIG.get("tags_menu_max_items",
                                          TAGS_MENU_MAX_ITEMS_DEFAULT)
            # Recreate deque with updated content and configured max size
            self.mru_tags = deque(APP_CONFIG.get("mru_tags", []),
                                  maxlen=new_max_tags)

            new_max_faces = APP_CONFIG.get("faces_menu_max_items",
                                           FACES_MENU_MAX_ITEMS_DEFAULT)
            if len(self.face_names_history) > new_max_faces:
                self.face_names_history = self.face_names_history[:new_max_faces]

            new_max_bodies = APP_CONFIG.get("body_menu_max_items",
                                            FACES_MENU_MAX_ITEMS_DEFAULT)
            if len(self.body_names_history) > new_max_bodies:
                self.body_names_history = self.body_names_history[:new_max_bodies]

            new_bg_color = APP_CONFIG.get("thumbnails_bg_color",
                                          THUMBNAILS_BG_COLOR_DEFAULT)
            self.thumbnail_view.setStyleSheet(f"background-color: {new_bg_color};")

            # Reload filmstrip position so it applies to new viewers
            self.filmstrip_position = APP_CONFIG.get("filmstrip_position", "bottom")

            # Trigger a repaint to apply other color changes like filename color
            self._apply_global_stylesheet()
            self.thread_pool_manager.update_default_thread_count()
            self.thumbnail_view.updateGeometries()
            self.thumbnail_view.viewport().update()

    def open_sidebar_tab(self, index):
        """Shows the dock and switches to the specified tab index."""
        self.main_dock.show()
        self.tags_tabs.setCurrentIndex(index)
        self.main_dock.raise_()
        self.on_tags_tab_changed(index)

    def refresh_shortcuts(self):
        """Saves current shortcuts configuration and updates running viewers."""
        self.save_config()
        for viewer in list(self.viewers):
            try:
                if isinstance(viewer, ImageViewer) and viewer.isVisible():
                    viewer.refresh_shortcuts()
            except RuntimeError:
                continue

    def clean_thumbnail_cache(self):
        """Starts a background thread to clean invalid entries from the cache."""
        self.status_lbl.setText(UITexts.CACHE_CLEANING)
        self.cache_cleaner = CacheCleaner(self.cache)
        self.cache_cleaner.finished_clean.connect(self.on_cache_cleaned)
        self.cache_cleaner.finished.connect(self._on_cache_cleaner_finished)
        self.cache_cleaner.start()

    def clean_stale_metadata_cache(self):
        """Starts a background thread to clean stale metadata entries."""
        self.status_lbl.setText("Cleaning stale metadata...")
        removed_count = self.cache.clean_stale_metadata()
        self.status_lbl.setText(f"Cleaned {removed_count} stale metadata entries.")
        self.rebuild_view()

    def clean_stale_directory_cache(self):
        """Starts a background thread to clean stale directory entries."""
        self.status_lbl.setText("Cleaning stale directory cache...")
        removed_count = self.cache.clean_stale_directories()
        self.status_lbl.setText(f"Cleaned {removed_count} stale directory cache entries.")
        self.rebuild_view()

    def on_cache_cleaned(self, count):
        """Slot for when the cache cleaning is finished."""
        self.status_lbl.setText(UITexts.CACHE_CLEANED.format(count))

    def _on_cache_cleaner_finished(self):
        """Clears the cleaner reference only when the thread has truly exited."""
        self.cache_cleaner = None

    def load_more_images(self):
        """Requests the scanner to load the next batch of images."""
        batch_size = APP_CONFIG.get(
            "scan_batch_size", SCANNER_SETTINGS_DEFAULTS["scan_batch_size"])
        self.request_more_images(batch_size)

    def load_all_images(self):
        """Toggles the automatic loading of all remaining images."""
        if self._is_loading_all:
            # If already loading all, cancel it
            self._is_loading_all = False
            if self.scanner:
                self.scanner.set_auto_load(False)
            self.update_load_all_button_state()
        else:
            # Start loading all remaining images
            remaining = self._scanner_total_files - self._scanner_last_index
            if remaining > 0:
                self._is_loading_all = True
                if self.scanner:
                    self.scanner.set_auto_load(True)
                self.update_load_all_button_state()
                batch_size = APP_CONFIG.get(
                    "scan_batch_size", SCANNER_SETTINGS_DEFAULTS["scan_batch_size"])
                self.request_more_images(batch_size)

    def perform_shutdown(self):
        """Performs cleanup operations before the application closes."""
        if getattr(self, '_is_shutting_down', False):
            return
        self._is_shutting_down = True
        self.is_cleaning = True

        # Save configuration early if visible, as per user request.
        # This ensures persistence even if subsequent cleanup hangs.
        if self.isVisible():
            self.save_config()

        # Stop all pending UI timers to prevent background tasks from triggering
        self.hide_progress_timer.stop()
        self.filter_input_timer.stop()
        self.filter_refresh_timer.stop()
        self.thumbnails_refresh_timer.stop()
        self.rebuild_timer.stop()
        self._model_update_timer.stop()
        self.resume_scan_timer.stop()

        # Close all viewers first to stop their preloader threads
        self.close_all_viewers()

        # Close duplicate manager if open to stop its preloader threads
        if HAVE_IMAGEHASH:
            for widget in QApplication.topLevelWidgets():
                if isinstance(widget, DuplicateManagerDialog):
                    widget.close()

        self.fs_watcher.stop()
        # 1. Stop all worker threads interacting with the cache

        # Signal all threads to stop first
        if self.scanner:
            self.scanner.stop()
        if self.thumbnail_generator and self.thumbnail_generator.isRunning():
            self.thumbnail_generator.stop()
        if self.duplicate_detector and self.duplicate_detector.isRunning():
            self.duplicate_detector.stop()

        # Create a list of threads to wait for
        threads_to_wait = []
        if self.scanner and self.scanner.isRunning():
            threads_to_wait.append(self.scanner)
        if self.thumbnail_generator and self.thumbnail_generator.isRunning():
            threads_to_wait.append(self.thumbnail_generator)
        if hasattr(self, 'cache_cleaner') and self.cache_cleaner \
           and self.cache_cleaner.isRunning():
            threads_to_wait.append(self.cache_cleaner)
        if self.duplicate_detector and self.duplicate_detector.isRunning():
            threads_to_wait.append(self.duplicate_detector)

        # Wait for them to finish while keeping the UI responsive
        if threads_to_wait:
            self.status_lbl.setText(UITexts.SHUTTING_DOWN)
            QApplication.setOverrideCursor(Qt.WaitCursor)

            for thread in threads_to_wait:
                while thread.isRunning():
                    if QApplication.instance():  # Check if QApplication is still valid
                        QApplication.processEvents()
                    QThread.msleep(50)  # Prevent high CPU usage

        # Ensure all QRunnables in the shared thread pool are finished
        if self.thread_pool_manager:
            pool = self.thread_pool_manager.get_pool()
            if pool.activeThreadCount() > 0:
                progress = QProgressDialog(UITexts.SHUTTING_DOWN, None, 0, 0, self)
                progress.setWindowTitle(PROG_NAME)
                progress.setWindowModality(Qt.ApplicationModal)
                progress.setMinimumDuration(0)
                progress.show()

                # Wait in small increments to keep the UI responsive
                while not pool.waitForDone(100):
                    if QApplication.instance():
                        QApplication.processEvents()
                progress.close()

        if self.duplicate_cache:
            self.duplicate_cache.lmdb_close()
            QApplication.restoreOverrideCursor()

        # 2. Close the cache safely now that no threads are using it
        self.cache.lmdb_close()

    def closeEvent(self, event):
        """Handles the main window close event to ensure graceful shutdown."""
        self.perform_shutdown()
        QApplication.quit()

    def on_view_double_clicked(self, proxy_index):
        """Handles double-clicking on a thumbnail to open the viewer."""
        item_type = self.proxy_model.data(proxy_index, ITEM_TYPE_ROLE)
        if item_type == 'thumbnail':
            self.open_viewer(proxy_index)
        elif item_type == 'header':
            group_name = self.proxy_model.data(proxy_index, GROUP_NAME_ROLE)
            if group_name:
                self.toggle_group_collapse(group_name)
            else:
                # Fallback for old headers if any
                self.proxy_model.invalidate()

    def get_current_selected_path(self):
        """Returns the file path of the first selected item in the view."""
        selected_indexes = self.thumbnail_view.selectedIndexes()
        if selected_indexes:
            proxy_index = selected_indexes[0]
            return self.proxy_model.data(proxy_index, PATH_ROLE)
        return None

    def get_all_image_paths(self):
        """Returns a list of all image paths in the source model."""
        paths = []
        for row in range(self.thumbnail_model.rowCount()):
            item = self.thumbnail_model.item(row)
            if item and item.data(ITEM_TYPE_ROLE) == 'thumbnail':
                paths.append(item.data(PATH_ROLE))
        return paths

    def get_visible_image_paths(self):
        """Return a list of all currently visible image paths from the proxy model."""
        if self._visible_paths_cache is not None:
            return self._visible_paths_cache

        # Optimization: Filter found_items_data in Python instead of iterating Qt model
        # rows which is slow due to overhead.
        paths = []
        name_filter = self.proxy_model.name_filter
        include_tags = self.proxy_model.include_tags
        exclude_tags = self.proxy_model.exclude_tags
        match_mode = self.proxy_model.match_mode
        collapsed_groups = self.proxy_model.collapsed_groups

        is_grouped = (self.proxy_model.group_by_folder or
                      self.proxy_model.group_by_day or
                      self.proxy_model.group_by_week or
                      self.proxy_model.group_by_month or
                      self.proxy_model.group_by_year or
                      self.proxy_model.group_by_rating)

        for item in self.found_items_data:
            # item: (path, qi, mtime, tags, rating, inode, dev)
            path = item[0]

            if is_grouped:
                # Check collapsed groups
                _, group_name = self._get_group_info(path, item[2], item[4])
                if group_name in collapsed_groups:
                    continue

            if name_filter and name_filter not in os.path.basename(path).lower():
                continue

            tags = set(item[3]) if item[3] else set()
            show = False
            if not include_tags:
                show = True
            elif match_mode == "AND":
                show = include_tags.issubset(tags)
            else:  # OR mode
                show = not include_tags.isdisjoint(tags)

            if show and (not exclude_tags or exclude_tags.isdisjoint(tags)):
                paths.append(path)

        self._visible_paths_cache = paths
        return paths

    def keyPressEvent(self, e):
        """Handles key presses for grid navigation."""
        # If in the search input, do not process grid navigation keys
        if self.search_input.lineEdit().hasFocus():
            return

        if self.proxy_model.rowCount() == 0:
            return

        current_proxy_idx = self.thumbnail_view.currentIndex()
        if not current_proxy_idx.isValid():
            current_proxy_idx = self.proxy_model.index(0, 0)

        current_vis_row = current_proxy_idx.row()

        total_visible = self.proxy_model.rowCount()
        if total_visible == 0:
            return

        grid_size = self.thumbnail_view.gridSize()
        if grid_size.width() == 0:
            return
        cols = max(1, self.thumbnail_view.viewport().width() // grid_size.width())
        next_vis_row = current_vis_row

        # Calculate next position based on key press
        if e.key() == Qt.Key_Right:
            next_vis_row += 1
        elif e.key() == Qt.Key_Left:
            next_vis_row -= 1
        elif e.key() == Qt.Key_Down:
            next_vis_row += cols
        elif e.key() == Qt.Key_Up:
            next_vis_row -= cols
        elif e.key() in (Qt.Key_Return, Qt.Key_Enter):
            if current_proxy_idx and current_proxy_idx.isValid():
                self.open_viewer(current_proxy_idx)
            return
        else:
            return

        # Clamp the next index within valid bounds
        if next_vis_row < 0:
            next_vis_row = 0
        if next_vis_row >= total_visible:
            # If at the end, try to load more images
            if self._scanner_last_index < self._scanner_total_files:
                self.request_more_images(1)
            next_vis_row = total_visible - 1

        target_proxy_index = self.proxy_model.index(next_vis_row, 0)
        if target_proxy_index.isValid():
            self.set_selection(target_proxy_index, modifiers=e.modifiers())

    def handle_page_nav(self, key):
        """Handles PageUp/PageDown navigation in the thumbnail grid."""
        if self.proxy_model.rowCount() == 0:
            return

        current_proxy_idx = self.thumbnail_view.currentIndex()
        if not current_proxy_idx.isValid():
            current_proxy_idx = self.proxy_model.index(0, 0)

        current_vis_row = current_proxy_idx.row()
        total_visible = self.proxy_model.rowCount()

        grid_size = self.thumbnail_view.gridSize()
        if grid_size.width() <= 0 or grid_size.height() <= 0:
            # Fallback to delegate size hint if grid size is not set
            grid_size = self.delegate.sizeHint(None, None)

        if grid_size.width() <= 0 or grid_size.height() <= 0:
            return

        # Calculate how many items fit in one page
        cols = max(1, self.thumbnail_view.viewport().width() // grid_size.width())
        rows_visible = max(1, self.thumbnail_view.viewport().height()
                           // grid_size.height())
        step = cols * rows_visible

        next_vis_idx = current_vis_row

        if key == Qt.Key_PageUp:
            next_vis_idx = max(0, current_vis_row - step)
        else:
            next_vis_idx = min(total_visible - 1, current_vis_row + step)
            # If we try to page down past the end, load more images
            if next_vis_idx == total_visible - 1 \
               and self._scanner_last_index < self._scanner_total_files:
                if current_vis_row + step >= total_visible:
                    self.request_more_images(step)

        target_proxy_index = self.proxy_model.index(next_vis_idx, 0)
        if target_proxy_index.isValid():
            self.set_selection(target_proxy_index,
                               modifiers=QApplication.keyboardModifiers())

    def set_selection(self, proxy_index, modifiers=Qt.NoModifier):
        """
        Sets the selection in the thumbnail view, handling multi-selection.

        Args:
            proxy_index (QModelIndex): The index in the proxy model to select.
            modifiers (Qt.KeyboardModifiers): Keyboard modifiers for selection mode.
        """
        if not proxy_index.isValid():
            return

        selection_model = self.thumbnail_view.selectionModel()
        selection_flags = QItemSelectionModel.NoUpdate

        # Determine selection flags based on keyboard modifiers
        if modifiers == Qt.NoModifier:
            selection_flags = QItemSelectionModel.ClearAndSelect
        elif modifiers & Qt.ControlModifier:
            selection_flags = QItemSelectionModel.Toggle
        elif modifiers & Qt.ShiftModifier:
            # QListView handles range selection automatically with this flag
            selection_flags = QItemSelectionModel.Select

        selection_model.select(proxy_index, selection_flags)
        self.thumbnail_view.setCurrentIndex(proxy_index)
        self.thumbnail_view.scrollTo(proxy_index, QAbstractItemView.EnsureVisible)

    def find_and_select_path(self, path_to_select):
        """Finds an item by its path in the model and selects it using a cache."""
        if not path_to_select:
            return False

        # Ensure path is normalized for reliable cache lookup
        path_to_select = os.path.abspath(os.path.expanduser(path_to_select))

        if path_to_select not in self._path_to_model_index:
            return False

        persistent_index = self._path_to_model_index[path_to_select]
        if not persistent_index.isValid():
            # The index might have become invalid (e.g., item removed)
            del self._path_to_model_index[path_to_select]
            return False

        source_index = QModelIndex(persistent_index)  # Convert back to QModelIndex
        proxy_index = self.proxy_model.mapFromSource(source_index)

        if proxy_index.isValid():
            # Optimization: skip if already selected and current to avoid
            # unnecessary signals and view updates.
            if self.thumbnail_view.currentIndex() == proxy_index and \
               self.thumbnail_view.selectionModel().isSelected(proxy_index):
                return True
            self.set_selection(proxy_index)
            return True

        return False

    def get_selected_paths(self):
        """Returns a list of all selected file paths."""
        paths = []
        seen = set()
        for idx in self.thumbnail_view.selectedIndexes():
            path = self.proxy_model.data(idx, PATH_ROLE)
            if path and path not in seen:
                paths.append(path)
                seen.add(path)
        return paths

    def restore_selection(self, paths):
        """Restores selection for a list of paths."""
        if not paths:
            return

        selection_model = self.thumbnail_view.selectionModel()
        selection = QItemSelection()
        first_valid_index = QModelIndex()

        for path in paths:
            if path in self._path_to_model_index:
                persistent_index = self._path_to_model_index[path]
                if persistent_index.isValid():
                    source_index = QModelIndex(persistent_index)
                    proxy_index = self.proxy_model.mapFromSource(source_index)
                    if proxy_index.isValid():
                        selection.select(proxy_index, proxy_index)
                        if not first_valid_index.isValid():
                            first_valid_index = proxy_index

        if not selection.isEmpty():
            selection_model.select(selection, QItemSelectionModel.ClearAndSelect)
            if first_valid_index.isValid():
                self.thumbnail_view.setCurrentIndex(first_valid_index)
                self.thumbnail_view.scrollTo(
                    first_valid_index, QAbstractItemView.EnsureVisible)

    def toggle_visibility(self):
        """Toggles the visibility of the main window, opening a viewer if needed."""
        if self.isVisible():
            # Find first thumbnail to ensure there are images and to auto-select
            first_thumb_idx = None
            for row in range(self.proxy_model.rowCount()):
                idx = self.proxy_model.index(row, 0)
                if self.proxy_model.data(idx, ITEM_TYPE_ROLE) == 'thumbnail':
                    first_thumb_idx = idx
                    break

            if not first_thumb_idx:
                return

            if not self.thumbnail_view.selectedIndexes():
                self.set_selection(first_thumb_idx)

            # If hiding and no viewers are open, open one for the selected image
            open_viewers = [w for w in QApplication.topLevelWidgets()
                            if isinstance(w, ImageViewer) and w.isVisible()]

            if not open_viewers and self.thumbnail_view.selectedIndexes():
                self.open_viewer(self.thumbnail_view.selectedIndexes()[0])
                self.hide()
            elif open_viewers:
                self.hide()
        else:
            self.show()
            self.raise_()
            self.activateWindow()
            self.setFocus()

    def delete_current_image(self, permanent=False):
        """Deletes the selected image(s), either to trash or permanently."""
        selected_indexes = self.thumbnail_view.selectedIndexes()
        if not selected_indexes:
            return

        paths = []
        for idx in selected_indexes:
            path = self.proxy_model.data(idx, PATH_ROLE)
            if path and path not in paths:
                paths.append(path)

        if not paths:
            return

        # Determine actual permanent status based on setting if not explicitly passed
        _permanent = permanent if permanent is not None \
            else not APP_CONFIG.get("default_delete_to_trash", True)

        if _permanent:
            confirm = QMessageBox(self)
            confirm.setIcon(QMessageBox.Warning)
            if len(paths) == 1:
                confirm.setText(UITexts.CONFIRM_DELETE_TEXT)
                confirm.setInformativeText(
                    UITexts.CONFIRM_DELETE_INFO.format(os.path.basename(paths[0])))
            else:
                confirm.setText(
                    f"Are you sure you want to permanently delete {len(paths)} images?")
                confirm.setInformativeText("This action CANNOT be undone.")
            confirm.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
            confirm.setDefaultButton(QMessageBox.No)
            if confirm.exec() != QMessageBox.Yes:
                return

        self.thumbnail_view.setUpdatesEnabled(False)
        try:
            for path in paths:
                self.delete_file_by_path(path, _permanent)
        finally:
            self.thumbnail_view.setUpdatesEnabled(True)
            self.rebuild_view()

    def delete_file_by_path(self, path, permanent=None):
        """
        Deletes a file and updates the application state.
        Logic extracted from delete_current_image for reuse.

        Args:
            path (str): The path to the file to delete.
            permanent (bool, optional): If True, deletes permanently. If False,
                                        sends to trash. If None, uses the
                                        'default_delete_to_trash' setting.
                                        Defaults to None.
        """
        _permanent = permanent if permanent is not None \
            else not APP_CONFIG.get("default_delete_to_trash", True)
        try:
            self._mark_path_as_app_modified(path)
            if _permanent:
                os.remove(path)
            else:
                # Use 'gio trash' for moving to trash can on Linux
                subprocess.run(["gio", "trash", path])

            # Notify open viewers of the deletion
            for w in QApplication.topLevelWidgets():
                if isinstance(w, ImageViewer):
                    if path in w.controller.image_list:
                        try:
                            deleted_idx = w.controller.image_list.index(path)
                            new_list = list(w.controller.image_list)
                            new_list.remove(path)
                            w.refresh_after_delete(new_list, deleted_idx)
                        except (ValueError, RuntimeError):
                            pass  # Viewer might be closing or list out of sync

            if path in self._path_to_model_index:
                p_idx = self._path_to_model_index[path]
                if p_idx.isValid():
                    self.thumbnail_model.removeRow(p_idx.row())

            if path in self._path_to_model_index:
                del self._path_to_model_index[path]

            self.duplicate_cache.remove_hash_for_path(path)
            # Remove from found_items_data to ensure consistency
            self.found_items_data = [x for x in self.found_items_data if x[0] != path]
            self._known_paths.discard(path)
            # Clean up group cache
            keys_to_remove = [k for k in self._group_info_cache if k[0] == path]
            for k in keys_to_remove:
                del self._group_info_cache[k]

            # Clean up proxy model cache
            if path in self.proxy_model._data_cache:
                del self.proxy_model._data_cache[path]

            self._visible_paths_cache = None
        except Exception as e:
            QMessageBox.critical(
                self, UITexts.SYSTEM_ERROR, UITexts.ERROR_DELETING_FILE.format(e))

    def move_current_image(self):
        """Moves the selected image(s) to another directory."""
        paths = self.get_selected_paths()
        if not paths:
            return

        # Use the directory of the first image as start point for the dialog
        start_dir = os.path.dirname(paths[0])
        target_dir = QFileDialog.getExistingDirectory(
            self, UITexts.CONTEXT_MENU_MOVE_TO, start_dir)

        if not target_dir:
            return

        moved_count = 0
        self.thumbnail_view.setUpdatesEnabled(False)
        try:
            for path in paths:
                new_path = os.path.join(target_dir, os.path.basename(path))
                if os.path.exists(new_path):
                    reply = QMessageBox.question(
                        self, UITexts.CONFIRM_OVERWRITE_TITLE,
                        UITexts.CONFIRM_OVERWRITE_TEXT.format(new_path),
                        QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
                    if reply != QMessageBox.Yes:
                        continue

                self._mark_path_as_app_modified(path)
                self._mark_path_as_app_modified(new_path)

                try:
                    shutil.move(path, new_path)
                    moved_count += 1

                    # Notify open viewers of the deletion
                    for w in QApplication.topLevelWidgets():
                        if isinstance(w, ImageViewer):
                            if path in w.controller.image_list:
                                try:
                                    deleted_idx = w.controller.image_list.index(path)
                                    new_list = list(w.controller.image_list)
                                    new_list.remove(path)
                                    w.refresh_after_delete(new_list, deleted_idx)
                                except (ValueError, RuntimeError):
                                    pass

                    # Remove from model using persistent index for efficiency
                    if path in self._path_to_model_index:
                        p_idx = self._path_to_model_index[path]
                        if p_idx.isValid():
                            self.thumbnail_model.removeRow(p_idx.row())
                        del self._path_to_model_index[path]

                    # Update internal data structures
                    self.found_items_data = [x for x in self.found_items_data
                                             if x[0] != path]
                    self._known_paths.discard(path)

                    # Clean up grouping and proxy caches
                    keys_to_remove = [k for k in self._group_info_cache if k[0] == path]
                    for k in keys_to_remove:
                        del self._group_info_cache[k]

                    self.proxy_model.remove_from_cache(path)
                    self._visible_paths_cache = None
                except Exception as e:
                    QMessageBox.critical(
                        self, UITexts.ERROR, UITexts.ERROR_MOVE_FILE.format(e))
                    break
        except Exception as e:
            QMessageBox.critical(self, UITexts.ERROR, UITexts.ERROR_MOVE_FILE.format(e))
        finally:
            self.thumbnail_view.setUpdatesEnabled(True)
            self.rebuild_view()
            if moved_count > 0:
                self.status_lbl.setText(UITexts.MOVED_TO.format(target_dir))

    def copy_current_image(self):
        """Copies the selected image(s) to another directory."""
        paths = self.get_selected_paths()
        if not paths:
            return

        start_dir = os.path.dirname(paths[0])
        target_dir = QFileDialog.getExistingDirectory(
            self, UITexts.CONTEXT_MENU_COPY_TO, start_dir)

        if not target_dir:
            return

        copied_count = 0
        for path in paths:
            new_path = os.path.join(target_dir, os.path.basename(path))
            if os.path.exists(new_path):
                reply = QMessageBox.question(
                    self, UITexts.CONFIRM_OVERWRITE_TITLE,
                    UITexts.CONFIRM_OVERWRITE_TEXT.format(new_path),
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
                if reply != QMessageBox.Yes:
                    continue

            try:
                shutil.copy2(path, new_path)
                copied_count += 1
            except Exception as e:
                QMessageBox.critical(
                    self, UITexts.ERROR, UITexts.ERROR_COPY_FILE.format(e))
                break

        if copied_count > 0:
            self.status_lbl.setText(UITexts.COPIED_TO.format(target_dir))

    def rotate_current_image(self, degrees):
        """Rotates the selected image, attempting lossless rotation for JPEGs."""
        path = self.get_current_selected_path()
        if not path:
            return

        _, ext = os.path.splitext(path)
        ext = ext.lower()
        success = False

        # Try lossless rotation for JPEGs using exiftran if available
        if ext in ['.jpg', '.jpeg']:
            try:
                cmd = []
                if degrees == 90:
                    cmd = ["exiftran", "-i", "-9", path]
                elif degrees == -90:
                    cmd = ["exiftran", "-i", "-2", path]
                elif degrees == 180:
                    cmd = ["exiftran", "-i", "-1", path]

                if cmd:
                    subprocess.check_call(cmd, stdout=subprocess.DEVNULL,
                                          stderr=subprocess.DEVNULL)
                    success = True
            except Exception:
                pass  # Fallback to lossy rotation

        # Fallback to lossy rotation using QImage
        if not success:
            try:
                self._mark_path_as_app_modified(path)
                reader = QImageReader(path)
                reader.setAutoTransform(True)
                img = reader.read()
                if img.isNull():
                    return

                transform = QTransform().rotate(degrees)
                new_img = img.transformed(transform, Qt.SmoothTransformation)
                new_img.save(path)
                success = True
            except Exception as e:
                QMessageBox.critical(self, UITexts.ERROR,
                                     UITexts.ERROR_ROTATE_IMAGE.format(e))
                return

        # Invalidate all cached thumbnails for this path. They will be regenerated
        # on demand.
        self.cache.invalidate_path(path)
        try:
            reader = QImageReader(path)
            reader.setAutoTransform(True)
            full_img = reader.read()
            if not full_img.isNull():
                # Regenerate the smallest thumbnail for immediate UI update
                stat_res = os.stat(path)
                new_mtime = stat_res.st_mtime
                new_inode = stat_res.st_ino
                new_dev = stat_res.st_dev

                smallest_size = min(SCANNER_GENERATE_SIZES) \
                    if SCANNER_GENERATE_SIZES else THUMBNAIL_SIZES[0]
                thumb_img = full_img.scaled(smallest_size, smallest_size,
                                            Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self.cache.set_thumbnail(path, thumb_img, new_mtime, smallest_size,
                                         inode=new_inode, device_id=new_dev)

                # Update model item
                if path in self._path_to_model_index:
                    p_idx = self._path_to_model_index[path]
                    if p_idx.isValid():
                        item = self.thumbnail_model.itemFromIndex(QModelIndex(p_idx))
                        item.setIcon(QIcon(QPixmap.fromImage(thumb_img)))
                        item.setData(new_mtime, MTIME_ROLE)
                        item.setData(new_inode, INODE_ROLE)
                        item.setData(new_dev, DEVICE_ROLE)
                        self._update_internal_data(path, qi=thumb_img, mtime=new_mtime,
                                                   inode=new_inode, dev=new_dev)
        except Exception:
            pass

        # Update any open viewers showing this image
        for w in QApplication.topLevelWidgets():
            if isinstance(w, ImageViewer):
                if w.controller.get_current_path() == path:
                    w.load_and_fit_image()

    def start_scan(self, paths, sync_viewer=False, active_viewer=None,
                   select_paths=None):
        """
        Starts a new background scan for images.

        Args:
            paths (list): A list of file paths or directories to scan.
            sync_viewer (bool): If True, avoids clearing the grid.
            active_viewer (ImageViewer): A viewer to sync with the scan results.
            select_paths (list): A list of paths to select automatically.
        """
        self.is_cleaning = True
        self._suppress_updates = True
        if self.scanner:
            self.scanner.stop()

        # Reset state for the new scan
        self._is_loading_all = APP_CONFIG.get(
            "scan_full_on_start", SCANNER_SETTINGS_DEFAULTS["scan_full_on_start"])
        self.update_load_all_button_state()

        # Clear the model if not syncing with an existing viewer
        if not sync_viewer:
            self.thumbnail_model.clear()
            self.found_items_data = []
            self._path_to_model_index.clear()
            self._known_paths.clear()
            self._group_info_cache.clear()
            self.proxy_model.clear_cache()
            self._model_update_queue.clear()
            self._model_update_timer.stop()
            self.fs_watcher.clear_paths()

        # Stop any pending hide action from previous scan
        self.hide_progress_timer.stop()

        # Hide load buttons during scan
        self.btn_load_more.hide()
        self.btn_load_all.hide()
        self.progress_bar.setValue(0)
        self.progress_bar.setCustomColor(None)
        self.progress_bar.show()

        self.is_cleaning = False
        self.scanner = ImageScanner(self.cache, paths, is_file_list=self._scan_all,
                                    thread_pool_manager=self.thread_pool_manager,
                                    viewers=self.viewers,  # Line 1071
                                    force_thumbnail_refresh=self._force_thumbnail_refresh,
                                    target_sizes=[self._current_thumb_tier])
        if self._is_loading_all:
            self.scanner.set_auto_load(True)
        self._is_loading = True
        self.scanner.images_found.connect(self.collect_found_images)

        # Add directories to file system watcher
        for p in paths:
            if os.path.isdir(os.path.abspath(os.path.expanduser(p))):
                self.fs_watcher.add_path(os.path.abspath(os.path.expanduser(p)))

        self.scanner.progress_percent.connect(self.update_progress_bar)
        self.scanner.progress_msg.connect(self.status_lbl.setText)
        self.scanner.more_files_available.connect(self.more_files_available)
        self.scanner.finished_scan.connect(
            lambda n: self._on_scan_finished(n, select_paths))
        self.scanner.start()
        self._scan_all = False
        self._force_thumbnail_refresh = False  # Reset the flag after starting scan

    def _on_scan_finished(self, n, select_paths=None):
        """Slot for when the image scanner has finished."""
        self._suppress_updates = False
        self._scanner_last_index = self._scanner_total_files

        self.btn_load_more.hide()
        self.btn_load_all.hide()

        # Turn green to indicate success and hide after 2 seconds
        self.progress_bar.setValue(100)
        self.progress_bar.setCustomColor(QColor("#2ecc71"))
        self.hide_progress_timer.start(2000)

        self.status_lbl.setText(UITexts.DONE_SCAN.format(n))
        self.setFocus()
        self._scan_all = False

        # Reset 'load all' state
        self._is_loading_all = False
        self.update_load_all_button_state()

        # Update dock widgets if visible
        if self.main_dock.isVisible():
            self.update_tag_list()
            if self.tag_edit_widget.isVisible():
                self.update_tag_edit_widget()

        # Select a specific path if requested (e.g., after layout restore)
        if select_paths:
            self.restore_selection(select_paths)

        # Final rebuild to ensure all items are correctly placed
        if self.rebuild_timer.isActive():
            self.rebuild_timer.stop()
        self.rebuild_view()

    def more_files_available(self, i, count):
        """Slot for when a batch of images has been loaded, with more available."""
        self._scanner_last_index = i
        self._scanner_total_files = count
        self._is_loading = False
        has_more = i < count
        self.btn_load_all.setVisible(has_more)

    def request_more_images(self, amount):
        """Requests the scanner to load a specific number of additional images."""
        if self._is_loading:
            return
        if self._scanner_last_index >= self._scanner_total_files:
            return
        self._is_loading = True
        self.scanner.load_images(self._scanner_last_index, amount)

    def _incremental_add_to_model(self, batch):
        """Appends new items directly to the model without full rebuild."""
        self._visible_paths_cache = None
        new_items = []
        for item in batch:
            path, qi, mtime, tags, rating, inode, dev = item
            new_item = self._create_thumbnail_item(
                path, qi, mtime, os.path.dirname(path),
                tags, rating, inode, dev)
            new_items.append(new_item)

        if new_items:
            # Disable updates briefly to prevent flickering during insertion
            self.thumbnail_view.setUpdatesEnabled(False)
            # Optimization: Use appendRow/insertRow with the item directly.
            # This avoids the "insert empty -> set data" double-signaling which forces
            # the ProxyModel to filter every row twice.
            for item in new_items:
                self.thumbnail_model.appendRow(item)
                path = item.data(PATH_ROLE)
                source_index = self.thumbnail_model.indexFromItem(item)
                self._path_to_model_index[path] = QPersistentModelIndex(source_index)
            self.thumbnail_view.setUpdatesEnabled(True)

    def collect_found_images(self, batch) -> None:
        """Collects a batch of found image data and triggers a view rebuild.

        This method adds new data to an internal list and then starts a timer
        to rebuild the view in a debounced manner, improving UI responsiveness
        during a scan.

        Args:
            batch (list): A list of tuples, where each tuple contains the data
                          for one found image (path, QImage, mtime, tags, rating).
        """
        # Add to the data collection, avoiding duplicates
        unique_batch = []
        is_first_batch = len(self.found_items_data) == 0

        for item in batch:
            path = item[0]
            if path not in self._known_paths:
                self._known_paths.add(path)
                # Store the QImage provided by the scanner for the initial model update.
                unique_batch.append(item)

                # Update proxy filter cache incrementally as data arrives
                self.proxy_model.add_to_cache(item[0], item[3])

        if unique_batch:
            self.found_items_data.extend(unique_batch)

            if is_first_batch:
                self._suppress_updates = False

            # Adjust rebuild timer interval based on total items to ensure UI
            # responsiveness.
            # Processing large lists takes time, so we update less frequently as the
            # list grows.
            total_count = len(self.found_items_data)
            if total_count < 2000:
                self.rebuild_timer.setInterval(150)
            elif total_count < 10000:
                self.rebuild_timer.setInterval(500)
            else:
                self.rebuild_timer.setInterval(1000)

            # Optimization: If scanning and in Flat view, just append to model
            # This avoids O(N) rebuilds/sorting during load
            is_flat_view = (self.view_mode_combo.currentIndex() == 0)

            # For the very first batch, rebuild immediately to give instant feedback.
            if is_first_batch:
                self.rebuild_view()
                self.rebuild_timer.start()
            elif is_flat_view:
                # Buffer updates to avoid freezing the UI with thousands of signals
                self._model_update_queue.extend(unique_batch)
                if not self._model_update_timer.isActive():
                    self._model_update_timer.start()
            # For grouped views or subsequent batches, debounce to avoid freezing.
            elif not self.rebuild_timer.isActive():
                self.rebuild_timer.start()

    def _update_internal_data(self, path, qi=None, mtime=None, tags=None, rating=None,
                              inode=None, dev=None):
        """Updates the internal data list to match model changes."""
        for i, item_data in enumerate(self.found_items_data):
            if item_data[0] == path:
                # tuple: (path, qi, mtime, tags, rating, inode, dev)
                # curr_qi = item_data[1]
                curr_mtime = item_data[2]
                curr_tags = item_data[3]
                curr_rating = item_data[4]
                # Preserve inode and dev if available (indices 5 and 6)
                curr_inode = item_data[5] if len(item_data) > 5 else None
                curr_dev = item_data[6] if len(item_data) > 6 else None

                new_qi = qi if qi is not None else item_data[1]  # Preserve existing qi if not explicitly provided
                new_mtime = mtime if mtime is not None else curr_mtime
                new_tags = tags if tags is not None else curr_tags
                new_rating = rating if rating is not None else curr_rating
                new_inode = inode if inode is not None else curr_inode
                new_dev = dev if dev is not None else curr_dev

                # Check if sorting/grouping keys (mtime, rating) changed
                if (mtime is not None and mtime != curr_mtime) or \
                   (rating is not None and rating != curr_rating):
                    cache_key = (path, curr_mtime, curr_rating)
                    if cache_key in self._group_info_cache:
                        del self._group_info_cache[cache_key]

                self.found_items_data[i] = (path, new_qi, new_mtime,
                                            new_tags, new_rating, new_inode, new_dev)
                break

    def _match_item(self, target, item):
        """Checks if a data target matches a model item."""
        if item is None:
            return False

        # Check for Header match
        # target format: ('HEADER', (key, header_text, count))
        if isinstance(target, tuple) and len(target) == 2 and target[0] == 'HEADER':
            target_group_name = target[1][0]
            return (item.data(ITEM_TYPE_ROLE) == 'header' and
                    item.data(GROUP_NAME_ROLE) == target_group_name)

        # Check for Thumbnail match
        # target format: (path, qi, mtime, tags, rating, inode, dev)
        # Target tuple length is now 7
        if item.data(ITEM_TYPE_ROLE) == 'thumbnail' and len(target) >= 5:
            return item.data(PATH_ROLE) == target[0]

        return False

    def _get_group_info(self, path, mtime, rating):
        """Calculates the grouping key and display name for a file with optimized
        caching."""
        # Determine resolution criteria for shared caching across all files in same
        # group
        if self.proxy_model.group_by_folder:
            crit = os.path.dirname(path)
            mode = 'F'
        elif self.proxy_model.group_by_rating:
            crit = (rating + 1) // 2 if rating is not None else 0
            mode = 'R'
        else:
            # Date modes: use datetime object parts as hashable criteria
            dt = datetime.fromtimestamp(int(mtime) if mtime else 0)
            if self.proxy_model.group_by_day:
                crit = (dt.year, dt.month, dt.day)
                mode = 'D'
            elif self.proxy_model.group_by_week:
                crit = (dt.year, int(dt.strftime("%W")))
                mode = 'W'
            elif self.proxy_model.group_by_month:
                crit = (dt.year, dt.month)
                mode = 'M'
            elif self.proxy_model.group_by_year:
                crit = dt.year
                mode = 'Y'
            else:
                return (None, None)

        # Shared cache by criteria ensures expensive formatting happens only once per
        # group
        shared_key = (crit, mode)
        if shared_key in self._group_info_cache:
            return self._group_info_cache[shared_key]

        # Perform actual calculation
        if mode == 'F':
            res = (crit, crit)
        elif mode == 'R':
            res = (str(crit), UITexts.GROUP_BY_RATING_FORMAT.format(stars=crit))
        else:
            if mode == 'D':
                sk = dn = dt.strftime("%Y-%m-%d")
            elif mode == 'W':
                sk = dt.strftime("%Y-%W")
                dn = UITexts.GROUP_BY_WEEK_FORMAT.format(
                    year=dt.strftime("%Y"), week=dt.strftime("%W"))
            elif mode == 'M':
                sk = dt.strftime("%Y-%m")
                dn = dt.strftime("%B %Y").capitalize()
            else:  # Year
                sk = dn = dt.strftime("%Y")
            res = (sk, dn)

        self._group_info_cache[shared_key] = res
        return res

    def _find_sorted_index_in_data(self, new_item_data):
        """Finds the correct index to insert an item to keep found_items_data sorted."""
        mode = self.sort_combo.currentText()
        rev = "↓" in mode
        sort_by_name = "Name" in mode

        def get_key(item):
            # item structure: (path, qi, mtime, tags, rating, inode, dev)
            path, _, mtime, _, _, _, _ = item
            if sort_by_name:
                return os.path.basename(path).lower()
            return mtime if mtime is not None else 0

        target_key = get_key(new_item_data)

        # Binary search for the insertion point (O(log N))
        lo = 0
        hi = len(self.found_items_data)
        while lo < hi:
            mid = (lo + hi) // 2
            mid_key = get_key(self.found_items_data[mid])
            if not rev:
                if mid_key < target_key:
                    lo = mid + 1
                else:
                    hi = mid
            else:
                if mid_key > target_key:
                    lo = mid + 1
                else:
                    hi = mid
        return lo

    def rebuild_view(self, full_reset=False):
        """
        Sorts all collected image data and rebuilds the source model, inserting
        headers for folder groups if required.
        """
        # On startup, the view mode is not always correctly applied visually
        # even if the combo box shows the correct value. This ensures the view's
        # layout properties (grid size, uniform items) are in sync with the
        # selected mode before any model rebuild.
        self._suppress_updates = True
        selected_paths = []
        try:
            index = self.view_mode_combo.currentIndex()

            self._model_update_queue.clear()
            self._model_update_timer.stop()

            # Update proxy model flags to ensure they match the UI state
            self.proxy_model.group_by_folder = (index == 1)
            self.proxy_model.group_by_day = (index == 2)
            self.proxy_model.group_by_week = (index == 3)
            self.proxy_model.group_by_month = (index == 4)
            self.proxy_model.group_by_year = (index == 5)
            self.proxy_model.group_by_rating = (index == 6)

            is_grouped = index > 0
            self.thumbnail_view.setUniformItemSizes(not is_grouped)
            if is_grouped:
                self.thumbnail_view.setGridSize(QSize())
            else:
                self.thumbnail_view.setGridSize(self.delegate.sizeHint(None, None))

            # Preserve selection
            selected_paths = self.get_selected_paths()

            mode = self.sort_combo.currentText()
            rev = "↓" in mode
            sort_by_name = "Name" in mode

            # 2. Sort the collected data. Python's sort is stable, so we apply sorts
            # from least specific to most specific.

            # First, sort by the user's preference (name or date).
            def user_sort_key(data_tuple):
                path, _, mtime, _, _, _, _ = data_tuple
                if sort_by_name:
                    return os.path.basename(path).lower()
                # Handle None mtime safely for sort
                return mtime if mtime is not None else 0

            self.found_items_data.sort(key=user_sort_key, reverse=rev)

            # 3. Rebuild the model. Disable view updates for a massive performance
            # boost.
            self.thumbnail_view.setUpdatesEnabled(False)

            target_structure = []

            if not is_grouped:
                # OPTIMIZATION: In Flat View, rely on Proxy Model for sorting.
                # This avoids expensive O(N) source model reshuffling/syncing on the
                # main thread.

                sort_role = Qt.DisplayRole if sort_by_name else MTIME_ROLE
                sort_order = Qt.DescendingOrder if rev else Qt.AscendingOrder
                self.proxy_model.setSortRole(sort_role)
                self.proxy_model.sort(0, sort_order)

                # Only rebuild source if requested or desynchronized (e.g. first batch)
                # If items were added incrementally, count matches and we skip rebuild.
                if full_reset or \
                   self.thumbnail_model.rowCount() != len(self.found_items_data):
                    self.thumbnail_model.clear()
                    self._path_to_model_index.clear()
                    # Fast append of all items
                    for item_data in self.found_items_data:
                        # item structure: (path, qi, mtime, tags, rating, inode, dev)
                        p, q, m, t, r, ino, d = item_data
                        new_item = self._create_thumbnail_item(
                            p, q, m, os.path.dirname(p), t, r, ino, d)
                        self.thumbnail_model.appendRow(new_item)
                        path = new_item.data(PATH_ROLE)
                        source_index = self.thumbnail_model.indexFromItem(new_item)
                        self._path_to_model_index[path] = \
                            QPersistentModelIndex(source_index)

            else:
                # For Grouped View, we must ensure source model order matches
                # groups/headers
                self.proxy_model.sort(-1)  # Disable proxy sorting

                if full_reset:
                    self.thumbnail_model.clear()
                    self._path_to_model_index.clear()

                # 1. Decorate: Calculate group info once per item with local memoization
                decorated_data = []
                local_memo = {}
                # Cache grouping flags to avoid property lookups in loop
                g_folder = self.proxy_model.group_by_folder

                for item in self.found_items_data:
                    # item structure: (path, qi, mtime, tags, rating, inode, dev)
                    path, _, mtime, _, rating, _, _ = item

                    # Local cache key: path for folders, (int_mtime, rating) for others
                    m_key = path if g_folder else (int(mtime) if mtime else 0, rating)

                    if m_key in local_memo:
                        stable_key, display_name = local_memo[m_key]
                    else:
                        stable_key, display_name = self._get_group_info(
                            path, mtime, rating)
                        local_memo[m_key] = (stable_key, display_name)

                    # Use empty string for None keys to ensure sortability
                    sort_key = stable_key if stable_key is not None else ""
                    decorated_data.append((sort_key, display_name, item))

                # 2. Sort by group key (stable sort preserves previous user order)
                is_reverse_group = not self.proxy_model.group_by_folder
                decorated_data.sort(key=lambda x: x[0], reverse=is_reverse_group)

                # Update master list to reflect the new group order
                self.found_items_data = [x[2] for x in decorated_data]

                # 3. Group and Insert
                for _, group_iter in groupby(decorated_data, key=lambda x: x[0]):
                    group_list = list(group_iter)
                    if not group_list:
                        continue

                    # Extract info from the first item in the group
                    _, display_name_group, _ = group_list[0]
                    count = len(group_list)

                    header_text = (UITexts.GROUP_HEADER_FORMAT_SINGULAR if count == 1
                                   else UITexts.GROUP_HEADER_FORMAT).format(
                                       group_name=display_name_group, count=count)

                    # ('HEADER', (key, header_text, count))
                    target_structure.append(
                        ('HEADER', (display_name_group, header_text, count)))

                    # Add items from the group
                    target_structure.extend([x[2] for x in group_list])

                # 4. Synchronize model with target_structure
                model_idx = 0
                target_idx = 0
                total_targets = len(target_structure)
                new_items_batch = []

                # Optimization: Pre-calculate sets for fast lookup of needed items
                target_paths_set = {t[0] for t in target_structure
                                    if isinstance(t, tuple) and len(t) >= 5}
                target_headers_set = {t[1][0] for t in target_structure
                                      if isinstance(t, tuple)
                                      and len(t) == 2 and t[0] == 'HEADER'}

                while target_idx < total_targets:
                    target = target_structure[target_idx]
                    current_item = self.thumbnail_model.item(model_idx)

                    if self._match_item(target, current_item):
                        # If it is a header, update the text in case the counter
                        # changed.
                        if isinstance(target, tuple) and target[0] == 'HEADER':
                            _, (_, header_text, _) = target
                            if current_item.data(DIR_ROLE) != header_text:
                                current_item.setData(header_text, DIR_ROLE)

                        model_idx += 1
                        target_idx += 1
                        continue

                    # 1. Identify and remove stale items (items in model but not in
                    # target structure)
                    if current_item:
                        is_needed = False
                        if current_item.data(ITEM_TYPE_ROLE) == 'thumbnail':
                            is_needed = current_item.data(PATH_ROLE) in target_paths_set
                        else:  # header
                            is_needed = current_item.data(GROUP_NAME_ROLE) \
                                in target_headers_set

                        if not is_needed:
                            path = current_item.data(PATH_ROLE)
                            if path and path in self._path_to_model_index:
                                del self._path_to_model_index[path]
                            self.thumbnail_model.removeRow(model_idx)
                            # Stay at same model_idx, check next model item against
                            # same target
                            continue

                    # 2. Try to MOVE target from later in the model (reordering
                    # optimization)
                    found_model_row = -1
                    if isinstance(target, tuple) and len(target) >= 5:  # Thumbnail
                        path = target[0]
                        p_idx = self._path_to_model_index.get(path)
                        if p_idx and p_idx.isValid() and p_idx.row() > model_idx:
                            found_model_row = p_idx.row()
                    elif isinstance(target, tuple) and target[0] == 'HEADER':
                        target_group_name = target[1][0]
                        for r in range(model_idx + 1, self.thumbnail_model.rowCount()):
                            it = self.thumbnail_model.item(r)
                            if it and it.data(ITEM_TYPE_ROLE) == 'header' and \
                               it.data(GROUP_NAME_ROLE) == target_group_name:
                                found_model_row = r
                                break

                    if found_model_row != -1:
                        # Move existing row to current position.
                        # Persistent indices and selection model will update
                        # automatically.
                        self.thumbnail_model.moveRow(QModelIndex(), found_model_row,
                                                     QModelIndex(), model_idx)
                        if isinstance(target, tuple) and target[0] == 'HEADER':
                            _, (_, header_text, _) = target
                            moved_item = self.thumbnail_model.item(model_idx)
                            if moved_item and moved_item.data(DIR_ROLE) != header_text:
                                moved_item.setData(header_text, DIR_ROLE)

                        model_idx += 1
                        target_idx += 1
                        continue

                    # 3. Target is truly NEW - use batch insertion
                    else:
                        # Prepare new item
                        if isinstance(target, tuple) and len(target) == 2 \
                           and target[0] == 'HEADER':
                            _, (group_name, header_text, _) = target
                            new_item = QStandardItem()
                            new_item.setData('header', ITEM_TYPE_ROLE)
                            new_item.setData(header_text, DIR_ROLE)
                            new_item.setData(group_name, GROUP_NAME_ROLE)
                            new_item.setFlags(Qt.ItemIsEnabled)
                        else:
                            path, qi, mtime, tags, rating, inode, dev = target
                            new_item = self._create_thumbnail_item(
                                path, qi, mtime, os.path.dirname(path),
                                tags, rating, inode, dev)

                        # Detect continuous block of new items for batch insertion
                        new_items_batch = [new_item]
                        target_idx += 1

                        # Look ahead to see if next items are also new (not in current
                        # model)
                        # This optimization drastically reduces proxy model
                        # recalculations
                        while target_idx < total_targets:
                            next_target = target_structure[target_idx]

                            # Check if next_target matches current model position
                            # (re-sync)
                            if self._match_item(
                               next_target, self.thumbnail_model.item(model_idx)):
                                break

                            # Check if next_target is a MOVE (exists elsewhere)
                            if isinstance(next_target, tuple) and len(next_target) >= 5:
                                n_p_idx = self._path_to_model_index.get(next_target[0])
                                if n_p_idx and n_p_idx.isValid() \
                                   and n_p_idx.row() > model_idx:
                                    break
                            # (simplified lookahead: headers always break batch)

                            # If not matching, it's another new item to insert
                            if isinstance(next_target, tuple) \
                               and len(next_target) == 2 and next_target[0] == 'HEADER':
                                _, (h_group, h_text, _) = next_target
                                n_item = QStandardItem()
                                n_item.setData('header', ITEM_TYPE_ROLE)
                                n_item.setData(h_text, DIR_ROLE)
                                n_item.setData(h_group, GROUP_NAME_ROLE)
                                n_item.setFlags(Qt.ItemIsEnabled)
                                new_items_batch.append(n_item)
                            else:
                                p, q, m, t, r, ino, d = next_target
                                n_item = self._create_thumbnail_item(
                                    p, q, m, os.path.dirname(p), t, r, ino, d)
                                new_items_batch.append(n_item)
                            target_idx += 1

                        # Perform batch insertion
                        # Optimization: Use appendRow/insertRow with the item directly
                        # to avoid double-signaling (rowsInserted + dataChanged) which
                        # forces the ProxyModel to filter every row twice.
                        if model_idx >= self.thumbnail_model.rowCount():
                            for item in new_items_batch:
                                self.thumbnail_model.appendRow(item)
                                if item.data(ITEM_TYPE_ROLE) == 'thumbnail':
                                    path = item.data(PATH_ROLE)
                                    source_index = \
                                        self.thumbnail_model.indexFromItem(item)
                                    self._path_to_model_index[path] = \
                                        QPersistentModelIndex(source_index)
                        else:
                            for i, item in enumerate(new_items_batch):
                                self.thumbnail_model.insertRow(model_idx + i, item)
                                if item.data(ITEM_TYPE_ROLE) == 'thumbnail':
                                    path = item.data(PATH_ROLE)
                                    source_index = self.thumbnail_model.index(
                                        model_idx + i, 0)
                                    self._path_to_model_index[path] = \
                                        QPersistentModelIndex(source_index)

                        model_idx += len(new_items_batch)

                # Remove any remaining trailing items in the model (e.g. if list shrank)
                if model_idx < self.thumbnail_model.rowCount():
                    for row in range(model_idx, self.thumbnail_model.rowCount()):
                        item = self.thumbnail_model.item(row)
                        if item and item.data(ITEM_TYPE_ROLE) == 'thumbnail':
                            path = item.data(PATH_ROLE)
                            if path in self._path_to_model_index:
                                # Only delete if it points to this specific row (stale)
                                # otherwise we might delete the index for a newly
                                # inserted item
                                p_idx = self._path_to_model_index[path]
                                if not p_idx.isValid() or p_idx.row() == row:
                                    del self._path_to_model_index[path]
                    self.thumbnail_model.removeRows(
                        model_idx, self.thumbnail_model.rowCount() - model_idx)
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"Error in rebuild_view: {e}")
        finally:
            self._suppress_updates = False
            self.apply_filters()
            self.thumbnail_view.setUpdatesEnabled(True)
            if selected_paths:
                self.restore_selection(selected_paths)

            if self.main_dock.isVisible() and \
               self.tags_tabs.currentWidget() == self.filter_widget:
                if not self.filter_refresh_timer.isActive():
                    self.filter_refresh_timer.start()

    def _create_thumbnail_item(self, path, qi, mtime, dir_path,
                               tags, rating, inode=None, dev=None):
        """Helper to create a standard item for the model."""
        thumb_item = QStandardItem()
        # Optimization: Do NOT create QIcon/QPixmap here.
        # The delegate handles painting from cache directly.
        # This avoids expensive main-thread image conversions during scanning.
        # thumb_item.setIcon(QIcon(QPixmap.fromImage(qi)))
        thumb_item.setText(os.path.basename(path))
        tooltip_text = f"{os.path.basename(path)}\n{path}"
        if tags:
            display_tags = [t.split('/')[-1] for t in tags]
            tooltip_text += f"\n{UITexts.TAGS_TAB}: {', '.join(display_tags)}"
        thumb_item.setToolTip(tooltip_text)
        thumb_item.setEditable(False)
        thumb_item.setData('thumbnail', ITEM_TYPE_ROLE)
        thumb_item.setData(path, PATH_ROLE)
        thumb_item.setData(mtime, MTIME_ROLE)
        thumb_item.setData(dir_path, DIR_ROLE)
        if qi:
            thumb_item.setData(qi, IMAGE_DATA_ROLE)
        # Set metadata that was loaded in the background thread
        thumb_item.setData(tags, TAGS_ROLE)
        thumb_item.setData(rating, RATING_ROLE)

        if inode is not None and dev is not None:
            thumb_item.setData(inode, INODE_ROLE)
            thumb_item.setData(dev, DEVICE_ROLE)
        return thumb_item

    def update_progress_bar(self, value):
        """Updates the circular progress bar value."""
        self.progress_bar.setValue(value)

    def on_thumbnail_loaded(self, _path, _size):
        """
        Called when a thumbnail has been loaded/generated and added to the
        in-memory cache.
        """
        # Once the thumbnail is in the in-memory cache, we can clear the QImage
        # from IMAGE_DATA_ROLE to save memory.
        if _path in self._path_to_model_index:
            p_idx = self._path_to_model_index[_path]
            if p_idx.isValid():
                item = self.thumbnail_model.itemFromIndex(QModelIndex(p_idx))
                if item and item.data(IMAGE_DATA_ROLE):
                    item.setData(None, IMAGE_DATA_ROLE)
        self.thumbnail_view.viewport().update()  # Force repaint

    def on_tags_tab_changed(self, index):
        """Updates the content of the sidebar dock when the active tab changes."""
        widget = self.tags_tabs.widget(index)
        if widget == self.tag_edit_widget:
            self.tag_edit_widget.load_available_tags()
            self.update_tag_edit_widget()
        elif widget == self.filter_widget:
            self.update_tag_list()
        elif widget == self.info_widget:
            self.update_info_widget()
        elif widget == self.favorites_tab:
            self.favorites_tab.refresh_list()

    def update_tag_edit_widget(self):
        """Updates the tag editor widget with data from the currently selected files."""
        if self._suppress_updates:
            return
        selected_indexes = self.thumbnail_view.selectedIndexes()
        if not selected_indexes:
            self.tag_edit_widget.set_files_data({})
            return

        files_data = {}
        for proxy_idx in selected_indexes:
            path = proxy_idx.data(PATH_ROLE)
            tags = proxy_idx.data(TAGS_ROLE)
            files_data[path] = tags
        self.tag_edit_widget.set_files_data(files_data)

    def update_info_widget(self):
        """Updates the information widget (rating, comment) with the current file's
        data."""
        if self._suppress_updates:
            return
        selected_indexes = self.thumbnail_view.selectedIndexes()
        paths = []
        if selected_indexes:
            for proxy_idx in selected_indexes:
                path = self.proxy_model.data(proxy_idx, PATH_ROLE)
                if path:
                    paths.append(path)
        self.rating_widget.set_files(paths)
        self.comment_widget.set_files(paths)

    def toggle_main_dock(self):
        """Toggles the visibility of the main sidebar dock widget."""
        if self.main_dock.isVisible():
            self.main_dock.hide()
        else:
            self.update_tag_list()
            self.main_dock.show()
            if self.tag_edit_widget.isVisible():
                self.update_tag_edit_widget()

    def toggle_faces(self):
        """Toggles the global 'show_faces' state and updates open viewers."""
        self.show_faces = not self.show_faces
        self.save_config()
        for viewer in list(self.viewers):
            try:
                if isinstance(viewer, ImageViewer) and viewer.isVisible():
                    viewer.controller.show_faces = self.show_faces
                    viewer.update_view(resize_win=False)
            except RuntimeError:
                continue

    def on_tags_edited(self, tags_per_file=None):
        """Callback to update model items after their tags have been edited."""
        for proxy_idx in self.thumbnail_view.selectedIndexes():
            source_idx = self.proxy_model.mapToSource(proxy_idx)
            item = self.thumbnail_model.itemFromIndex(source_idx)
            if item:
                path = item.data(PATH_ROLE)
                # Use provided tags if available, otherwise fallback to disk read
                try:
                    if isinstance(tags_per_file, dict) and path in tags_per_file:
                        tags = tags_per_file[path]
                    else:
                        raw = os.getxattr(path, XATTR_NAME).decode('utf-8')
                        tags = sorted(
                            list(set(t.strip() for t in raw.split(',') if t.strip())))
                    item.setData(tags, TAGS_ROLE)

                    tooltip_text = f"{os.path.basename(path)}\n{path}"
                    if tags:
                        display_tags = [t.split('/')[-1] for t in tags]
                        tooltip_text += f"\n{UITexts.TAGS_TAB}: {', '.join(
                            display_tags)}"
                    item.setToolTip(tooltip_text)
                except Exception:
                    item.setData([], TAGS_ROLE)

                self._update_internal_data(path, tags=item.data(TAGS_ROLE))

                # Update LMDB metadata cache
                try:
                    st = os.stat(path)
                    self.cache.set_metadata(st.st_dev, st.st_ino, st.st_mtime, tags, 0, path)
                except OSError:
                    pass

                # Update proxy filter cache immediately
                self.proxy_model.add_to_cache(path, tags)

                # Notify the view that the data has changed
                self.thumbnail_model.dataChanged.emit(
                    source_idx, source_idx, [TAGS_ROLE])

        self.update_tag_list()
        self.apply_filters()

    def on_rating_edited(self):
        """Callback to update a model item after its rating has been edited."""
        # The rating widget acts on the selected files, so we iterate through them.
        for proxy_idx in self.thumbnail_view.selectedIndexes():
            source_idx = self.proxy_model.mapToSource(proxy_idx)
            item = self.thumbnail_model.itemFromIndex(source_idx)
            if item:
                path = item.data(PATH_ROLE)
                # Re-read rating from xattr to be sure of the value
                new_rating = 0
                try:
                    raw_rating = os.getxattr(path, RATING_XATTR_NAME).decode('utf-8')
                    new_rating = int(raw_rating)
                except (OSError, ValueError, AttributeError):
                    pass

                # Update the model data, which will trigger a view update.
                item.setData(new_rating, RATING_ROLE)

                # Update LMDB metadata cache
                try:
                    st = os.stat(path)
                    tags = item.data(TAGS_ROLE) or []
                    self.cache.set_metadata(
                        st.st_dev, st.st_ino, st.st_mtime,
                        tags, new_rating, path)
                except OSError:
                    pass

                self._update_internal_data(path, rating=new_rating)

    def update_tag_list(self):
        """Updates the list of available tags in the filter panel from all loaded
        items."""
        if not hasattr(self, 'tags_list'):
            return
        if self._suppress_updates:
            return
        checked_tags = set()
        not_tags = set()
        # Preserve current filter state
        for i in range(self.tags_list.rowCount()):
            item_tag = self.tags_list.item(i, 0)
            item_not = self.tags_list.item(i, 1)

            tag_name = item_tag.data(Qt.UserRole) if item_tag else None
            if not tag_name and item_tag:
                tag_name = item_tag.text()

            if item_tag and item_tag.checkState() == Qt.Checked:
                checked_tags.add(tag_name)
            if item_tag and item_not and item_not.checkState() == Qt.Checked:
                not_tags.add(tag_name)

        self.tags_list.blockSignals(True)
        self.tags_list.setRowCount(0)

        # Gather all unique tags from found_items_data (Optimized)
        tag_counts = {}
        for item in self.found_items_data:
            # item structure: (path, qi, mtime, tags, rating, inode, dev)
            tags = item[3]
            if tags:
                for tag in tags:
                    tag_counts[tag] = tag_counts.get(tag, 0) + 1

        # Repopulate the filter list
        sorted_tags = sorted(list(tag_counts.keys()))
        self.tags_list.setRowCount(len(sorted_tags))

        for i, tag in enumerate(sorted_tags):
            count = tag_counts[tag]
            display_text = f"{tag} ({count})"

            item = QTableWidgetItem(display_text)
            item.setData(Qt.UserRole, tag)
            item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            item.setCheckState(Qt.Checked if tag in checked_tags else Qt.Unchecked)
            self.tags_list.setItem(i, 0, item)
            item_not = QTableWidgetItem()
            item_not.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            item_not.setCheckState(Qt.Checked if tag in not_tags else Qt.Unchecked)
            self.tags_list.setItem(i, 1, item_not)

        self.tags_list.blockSignals(False)

        if hasattr(self, 'tag_search_input'):
            self.filter_tags_list(self.tag_search_input.text())

    def filter_tags_list(self, text):
        """Filters the rows in the tags list table based on the search text."""
        search_text = text.strip().lower()
        for row in range(self.tags_list.rowCount()):
            item = self.tags_list.item(row, 0)
            if item:
                should_show = search_text in item.text().lower()
                self.tags_list.setRowHidden(row, not should_show)

    def on_tag_changed(self, item):
        """Handles checkbox changes in the tag filter list."""
        # When a checkbox is checked, uncheck the other in the same row to make
        # them mutually exclusive (a tag can't be both included and excluded).
        if item.checkState() == Qt.Checked:
            self.tags_list.blockSignals(True)
            row = item.row()
            if item.column() == 0:  # 'Tag' checkbox
                other_item = self.tags_list.item(row, 1)  # 'NOT' checkbox
                if other_item:
                    other_item.setCheckState(Qt.Unchecked)
            elif item.column() == 1:  # 'NOT' checkbox
                other_item = self.tags_list.item(row, 0)  # 'Tag' checkbox
                if other_item:
                    other_item.setCheckState(Qt.Unchecked)
            self.tags_list.blockSignals(False)

        self.apply_filters()

    def on_selection_changed(self, selected, deselected):
        """Callback to update dock widgets when the thumbnail selection changes."""
        # Always update tag edit widget data so available_tags is kept fresh
        # for name autocompletion in viewers, even if the sidebar is hidden.
        self.update_tag_edit_widget()

        if self.info_widget.isVisible():
            self.update_info_widget()

    def invert_tag_selection(self):
        """Inverts the selection of the 'include' checkboxes in the filter."""
        self.tags_list.blockSignals(True)
        for i in range(self.tags_list.rowCount()):
            item = self.tags_list.item(i, 0)
            if item.flags() & Qt.ItemIsUserCheckable:
                new_state = Qt.Unchecked \
                    if item.checkState() == Qt.Checked else Qt.Checked
                item.setCheckState(new_state)
        self.tags_list.blockSignals(False)
        self.apply_filters()

    def apply_filters(self):
        """Applies all current name and tag filters to the proxy model."""
        # Ensure UI components are initialized
        if not hasattr(self, 'tags_list') or \
           not hasattr(self, 'filter_mode_group') or \
           not self.filter_mode_group.buttons():
            return

        if self.is_cleaning or self._suppress_updates:
            return

        # Preserve selection
        selected_paths = self.get_selected_paths()

        # Gather filter criteria from the UI
        include_tags = set()
        exclude_tags = set()
        for i in range(self.tags_list.rowCount()):
            item_tag = self.tags_list.item(i, 0)
            item_not = self.tags_list.item(i, 1)

            tag_name = item_tag.data(Qt.UserRole)

            if item_tag.checkState() == Qt.Checked:
                include_tags.add(tag_name)
            if item_not.checkState() == Qt.Checked:
                exclude_tags.add(tag_name)

        # Set filter properties on the proxy model
        self.proxy_model.include_tags = include_tags
        self.proxy_model.exclude_tags = exclude_tags
        name_filter = self.filter_name_input.text().strip().lower()
        self.proxy_model.name_filter = name_filter
        self.proxy_model.match_mode = "AND" \
            if self.filter_mode_group.buttons()[0].isChecked() else "OR"

        # Optimization: Warm the filter cache before invalidating.
        # This ensures filterAcceptsRow uses O(1) lookups for all items.
        self.proxy_model.prepare_filter()

        # Invalidate the model to force a re-filter
        self.proxy_model.invalidate()
        self._visible_paths_cache = None

        # Update UI with filter statistics
        visible_count = self.proxy_model.rowCount()
        total_count = self.thumbnail_model.rowCount()
        hidden_count = total_count - visible_count

        if hidden_count > 0:
            self.filter_stats_lbl.setText(
                UITexts.FILTER_STATS_HIDDEN.format(hidden_count))
            self.filter_stats_lbl.show()
        else:
            self.filter_stats_lbl.hide()

        is_filter_active = bool(include_tags or exclude_tags or name_filter)
        if is_filter_active:
            self.filtered_count_lbl.setText(
                UITexts.FILTERED_COUNT.format(visible_count))
        else:
            self.filtered_count_lbl.setText(UITexts.FILTERED_ZERO)

        # Restore selection if it's still visible
        if selected_paths:
            self.restore_selection(selected_paths)

        # Sync open viewers with the new list of visible paths
        visible_paths = self.get_visible_image_paths()
        self.update_viewers_filter(visible_paths)

    def update_viewers_filter(self, visible_paths):
        """Updates all open viewers with the new filtered list of visible paths."""
        for w in list(self.viewers):
            try:
                if not isinstance(w, ImageViewer) or not w.isVisible():
                    continue
            except RuntimeError:
                # The widget was deleted, remove it from the list
                self.viewers.remove(w)
                continue

            # Get tags and rating for the current image in this viewer
            current_path_in_viewer = w.controller.get_current_path()
            viewer_tags = []
            viewer_rating = 0
            if current_path_in_viewer in self._known_paths:
                for item_data in self.found_items_data:
                    if item_data[0] == current_path_in_viewer:
                        viewer_tags = item_data[3]
                        viewer_rating = item_data[4]
                        break
            # Optimization: avoid update if list is identical
            current_path = w.controller.get_current_path()
            target_list = visible_paths
            new_index = -1

            if current_path:
                try:
                    new_index = target_list.index(current_path)
                except ValueError:
                    # Current image not in list.
                    # Check if it was explicitly filtered out (known but hidden) or
                    # just not loaded yet.
                    is_filtered = current_path in self._known_paths

                    if is_filtered and target_list:
                        # Filtered out: Move to nearest available neighbor
                        new_index = min(w.controller.index, len(target_list) - 1)
                    else:
                        # Not known (loading) or filtered but list empty: Preserve it
                        target_list = list(visible_paths)
                        target_list.append(current_path)
                        new_index = len(target_list) - 1

            # Check if we are preserving the image to pass correct metadata
            tags_to_pass = None
            rating_to_pass = 0

            if new_index != -1 and new_index < len(target_list):
                if target_list[new_index] == current_path_in_viewer:
                    tags_to_pass = viewer_tags
                    rating_to_pass = viewer_rating

            w.controller.update_list(
                target_list, new_index if new_index != -1 else None,
                tags_to_pass, rating_to_pass)
            if not w._is_persistent and not w.controller.image_list:
                w.close()
                continue

            w.populate_filmstrip()

            # Reload image if it changed, otherwise just sync selection
            if not w._is_persistent and w.controller.get_current_path() != current_path:
                w.load_and_fit_image()
            else:
                w.sync_filmstrip_selection(w.controller.index)

    def _setup_viewer_sync(self, viewer):
        """Connects viewer signals to main window slots for selection
        synchronization."""

        def sync_selection_from_viewer(*args):
            """Synchronize selection from a viewer to the main window.

            If the image from the viewer is not found in the main view, it may
            be because the main view has been filtered. This function will
            attempt to resynchronize the viewer's image list.
            """
            path = viewer.controller.get_current_path()
            if not path:
                return

            # First, try to select the image directly. This is the common case
            if self.find_and_select_path(path):
                return  # Success, image was found and selected.

            # If not found, it might be because the main view is filtered.
            # Attempt to resynchronize the viewer's list with the current view.
            # We perform the check inside the lambda to ensure it runs AFTER the sync.
            def sync_and_retry():
                self.update_viewers_filter(self.get_visible_image_paths())
                if not self.find_and_select_path(path):
                    self.status_lbl.setText(UITexts.IMAGE_NOT_IN_VIEW.format(
                        os.path.basename(path)))

            QTimer.singleShot(0, sync_and_retry)

        # This signal is emitted when viewer.controller.index changes
        viewer.index_changed.connect(sync_selection_from_viewer)
        viewer.activated.connect(sync_selection_from_viewer)

    def open_viewer(self, proxy_index, persistent=False):
        """
        Opens a new image viewer for the selected item.

        Args:
            proxy_index (QModelIndex): The index of the item in the proxy model.
            persistent (bool): Whether the viewer is part of a persistent layout.
        """
        if not proxy_index.isValid() or \
           self.proxy_model.data(proxy_index, ITEM_TYPE_ROLE) != 'thumbnail':
            return

        visible_paths = self.get_visible_image_paths()

        # The index of the clicked item in the visible list is NOT its row in the
        # proxy model when headers are present. We must find it.
        clicked_path = self.proxy_model.data(proxy_index, PATH_ROLE)
        try:
            new_idx = visible_paths.index(clicked_path)
        except ValueError:
            return  # Should not happen if get_visible_image_paths is correct

        if not visible_paths:
            return

        # Get tags and rating for the current image
        current_image_data = self.found_items_data[self.found_items_data.index(
            next(item for item in self.found_items_data if item[0] == clicked_path))]
        initial_tags = current_image_data[3]
        initial_rating = current_image_data[4]
        viewer = ImageViewer(self.cache, visible_paths, new_idx,
                             initial_tags, initial_rating, self, persistent=persistent)

        self._setup_viewer_sync(viewer)
        self.viewers.append(viewer)
        viewer.destroyed.connect(
            lambda: self.viewers.remove(viewer) if viewer in self.viewers else None)
        viewer.show()
        return viewer

    def open_comparison_viewer(self, paths):
        """
        Opens an ImageViewer specifically for comparing a set of paths.
        """
        if not paths:
            return

        viewer = ImageViewer(self.cache, paths, 0, None, 0, self)
        self._setup_viewer_sync(viewer)
        self.viewers.append(viewer)
        viewer.destroyed.connect(
            lambda obj=viewer: self.viewers.remove(obj)
            if obj in self.viewers else None)

        if len(paths) > 1:
            viewer.set_comparison_mode(len(paths))
        viewer.show()
        return viewer

    def load_full_history(self):
        """Loads the persistent browsing/search history from its JSON file."""
        if os.path.exists(HISTORY_PATH):
            try:
                with open(HISTORY_PATH, 'r') as f:
                    self.full_history = json.load(f)
            except Exception:
                self.full_history = []
        else:
            self.full_history = []

    def save_full_history(self):
        """Saves the persistent browsing/search history to its JSON file."""
        try:
            with open(HISTORY_PATH, 'w') as f:
                json.dump(self.full_history, f, indent=4)
        except Exception:
            pass

    def add_to_history(self, term):
        """Adds a new term to both the recent (in-memory) and persistent history."""
        # Update recent items in the ComboBox
        if term in self.history:
            self.history.remove(term)
        self.history.insert(0, term)
        if len(self.history) > 25:
            self.history = self.history[:25]
        self.save_config()

        # Update the full, persistent history
        entry = {
            "path": term,
            "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        # Remove duplicate to bump it to the top
        self.full_history = [x for x in self.full_history if x['path'] != term]
        self.full_history.insert(0, entry)
        self.save_full_history()

        if hasattr(self, 'history_tab'):
            self.history_tab.refresh_list()

    def add_to_mru_tags(self, tag):
        """Adds a tag to the Most Recently Used list."""
        if tag in self.mru_tags:
            self.mru_tags.remove(tag)
        self.mru_tags.appendleft(tag)
        self.save_config()  # Save on change

    def update_metadata_for_path(self, path, metadata=None):
        """Finds an item by path and updates its metadata in the model and internal
        data."""
        if not path:
            return

        # Determine tags and rating based on provided metadata or disk read
        if metadata:
            tags = metadata.get('tags', [])
            rating = metadata.get('rating', 0)
        else:
            res = load_common_metadata(path)
            tags, rating = res.tags, res.rating

        # Use cache for O(1) lookup in the source model
        path = os.path.abspath(os.path.expanduser(path))
        if path in self._path_to_model_index:
            p_idx = self._path_to_model_index[path]
            if p_idx.isValid():
                item = self.thumbnail_model.itemFromIndex(QModelIndex(p_idx))
                item.setData(tags, TAGS_ROLE)
                item.setData(rating, RATING_ROLE)

                tooltip_text = f"{os.path.basename(path)}\n{path}"
                if tags:
                    display_tags = [t.split('/')[-1] for t in tags]
                    tooltip_text += f"\n{UITexts.TAGS_TAB}: {', '.join(display_tags)}"
                item.setToolTip(tooltip_text)

                # Notify the view that the data has changed
                source_idx = QModelIndex(p_idx)
                self.thumbnail_model.dataChanged.emit(
                    source_idx, source_idx, [TAGS_ROLE, RATING_ROLE])

                # Update internal data structure to prevent stale data on rebuild
                self._update_internal_data(path, tags=tags, rating=rating)

                # Update proxy filter cache to prevent stale filtering
                self.proxy_model.add_to_cache(path, tags)

                # Update LMDB metadata cache
                try:
                    st = os.stat(path)
                    self.cache.set_metadata(st.st_dev, st.st_ino, st.st_mtime, tags, rating, path)
                except OSError:
                    pass

        if self.main_dock.isVisible():
            self.on_tags_tab_changed(self.tags_tabs.currentIndex())

        # Re-apply filters in case the tag change affects visibility
        self.apply_filters()

    def on_view_mode_changed(self, index):
        """Callback for when the view mode (Flat/Folder) changes."""
        self._suppress_updates = True
        self.proxy_model.group_by_folder = (index == 1)
        self.proxy_model.group_by_day = (index == 2)
        self.proxy_model.group_by_week = (index == 3)
        self.proxy_model.group_by_month = (index == 4)
        self.proxy_model.group_by_year = (index == 5)
        self.proxy_model.group_by_rating = (index == 6)

        self.proxy_model.collapsed_groups.clear()
        self._group_info_cache.clear()

        is_grouped = index > 0

        # Disable uniform item sizes in grouped modes to allow headers of different
        # height
        self.thumbnail_view.setUniformItemSizes(not is_grouped)

        if is_grouped:
            self.thumbnail_view.setGridSize(QSize())
        else:
            self.thumbnail_view.setGridSize(self.delegate.sizeHint(None, None))
        self.rebuild_view(full_reset=True)

        self.save_config()
        self.setFocus()

    def on_sort_changed(self):
        """Callback for when the sort order dropdown changes."""
        self.rebuild_view(full_reset=True)
        self.save_config()
        if hasattr(self, 'history_tab'):
            self.history_tab.refresh_list()
        self.setFocus()

    def _get_tier_for_size(self, requested_size):
        """Determines the ideal thumbnail tier based on the requested size."""
        if requested_size < 192:
            return 128
        if requested_size < 320:
            return 256
        return 512

    def on_slider_changed(self, v):
        """Callback for when the thumbnail size slider changes."""
        self.current_thumb_size = v
        self.size_label.setText(f"{v}px")

        new_tier = self._get_tier_for_size(v)

        # If the required tier for the new size is different, we trigger generation.
        if new_tier != self._current_thumb_tier:
            self._current_thumb_tier = new_tier

            # Update scanner if running to use the new tier for upcoming batches
            if self.scanner and self.scanner.isRunning():
                self.scanner.target_sizes = [new_tier]

            # 2. For all images ALREADY loaded, start a background job to
            #    generate the newly required thumbnail size. This is interruptible.
            self.generate_missing_thumbnails(new_tier)

        # Update the delegate's size hint and the view's grid size
        new_hint = self.delegate.sizeHint(None, None)

        is_grouped = (self.proxy_model.group_by_folder or
                      self.proxy_model.group_by_day or
                      self.proxy_model.group_by_week or
                      self.proxy_model.group_by_month or
                      self.proxy_model.group_by_year or
                      self.proxy_model.group_by_rating)

        if is_grouped:
            self.thumbnail_view.setGridSize(QSize())
            self.thumbnail_view.doItemsLayout()
        else:
            self.thumbnail_view.setGridSize(new_hint)
        self.thumbnail_view.update()
        self.setFocus()

    def generate_missing_thumbnails(self, size):
        """
        Starts a background thread to generate thumbnails of a specific size for all
        currently loaded images.
        """
        if self.thumbnail_generator and self.thumbnail_generator.isRunning():
            self.thumbnail_generator.stop()

        paths = self.get_all_image_paths()
        if not paths:
            return

        # Prioritize visible paths
        visible = self.get_visible_image_paths()
        visible_set = set(visible)
        ordered_paths = visible + [p for p in paths if p not in visible_set]

        self.thumbnail_generator = ThumbnailGenerator(
            self.cache, ordered_paths, size, self.thread_pool_manager)
        self.thumbnail_generator.generation_complete.connect(
            self.on_high_res_generation_finished)
        self.thumbnail_generator.progress.connect(
            lambda p, t: self.status_lbl.setText(
                f"Generating {size}px thumbnails: {p}/{t}")
        )
        self.thumbnail_generator.start()

    def on_high_res_generation_finished(self):
        """Slot called when the background thumbnail generation is complete."""
        self.status_lbl.setText(UITexts.HIGH_RES_GENERATED)
        self.thumbnail_view.viewport().update()

    def refresh_content(self):
        """Refreshes the current view by re-running the last search or scan."""
        if not self.history:
            return

        current_selection = self.get_selected_paths()
        term = self.history[0]
        if term.startswith("file:/"):
            path = term[6:]
            if os.path.isfile(path):
                self.start_scan([os.path.dirname(path)], select_paths=current_selection)
                return
        self.process_term(term, select_paths=current_selection)

    def hard_refresh_content(self):
        """Invalidates directory cache and re-scans content."""
        if not self.history:
            return

        term = self.history[0]
        path = term[6:] if term.startswith("file:/") else term
        # Don't invalidate for searches/layouts as they don't use directory cache
        if not term.startswith(("search:/", "layout:/")):
            abs_path = os.path.abspath(os.path.expanduser(path))
            target_dir = abs_path if os.path.isdir(abs_path) else \
                os.path.dirname(abs_path)
            self.cache.invalidate_directory_cache(target_dir)

        self._force_thumbnail_refresh = True
        self.refresh_content()

    def process_term(self, term, select_paths=None):
        """Processes a search term, file path, or layout directive."""
        self.add_to_history(term)
        self.update_search_input()

        # Ensure loading UI is active (backup for history/favorites calls)
        self.status_lbl.setText(UITexts.PREPARING_QUERY)
        self.progress_bar.setRange(0, 0)
        self.progress_bar.show()
        self.btn_load_all.hide()
        self.btn_load_more.hide()
        self.btn_cancel_duplicates.hide()
        QApplication.processEvents()

        if term.startswith("layout:/"):
            if not self.is_xcb:
                return

            # Handle loading a layout
            filename = os.path.join(LAYOUTS_DIR, f"{term[8:]}")
            base, ext = os.path.splitext(filename)
            if ext != ".layout":
                filename = filename + ".layout"

            if os.path.exists(filename):
                self.restore_layout(filename)
            else:
                self.is_cleaning = True
                if self.scanner:
                    self.scanner.stop()
                    self.scanner.wait()
                QMessageBox.critical(self,
                                     UITexts.ERROR_LOADING_LAYOUT_TITLE.format(
                                         PROG_NAME),
                                     UITexts.ERROR_LOADING_LAYOUT_TEXT.format(term[8:]))
                QApplication.quit()

        else:
            # Handle a file path or search query
            if term.startswith("search:/"):
                path = term[8:]
            else:
                path = term[6:] if term.startswith("file:/") else term
            if os.path.isfile(path):
                # If a single file is passed, open it in a viewer and scan its directory
                self.thumbnail_model.clear()
                self.active_viewer = ImageViewer(self.cache, [path], 0,
                                                 initial_tags=None,
                                                 initial_rating=0, parent=self,
                                                 persistent=True)
                self.start_scan([os.path.dirname(path)],
                                active_viewer=self.active_viewer)
                self._setup_viewer_sync(self.active_viewer)
                self.viewers.append(self.active_viewer)
                self.active_viewer.destroyed.connect(
                    lambda obj=self.active_viewer: self.viewers.remove(obj)
                    if obj in self.viewers else None)
                self.active_viewer.show()

            else:
                # If a directory or search term, start a scan
                self.start_scan([path], select_paths=select_paths)

    def update_search_input(self):
        """Updates the search input combo box with history items and icons."""
        self.search_input.clear()
        for h in self.history:
            icon = QIcon.fromTheme("system-search")
            text = h.replace("search:/", "").replace("file:/", "")

            if h.startswith("file:/"):
                path = h[6:]
                if os.path.isdir(os.path.expanduser(path)):
                    icon = QIcon.fromTheme("folder")
                else:
                    icon = QIcon.fromTheme("image-x-generic")
            elif h.startswith("layout:/"):
                icon = QIcon.fromTheme("view-grid")
            elif h.startswith("search:/"):
                icon = QIcon.fromTheme("system-search")

            self.search_input.addItem(icon, text)

    def on_search_triggered(self):
        """Callback for when a search is triggered from the input box."""
        t = self.search_input.currentText().strip()
        if t:
            # Detect if the term is an existing path or a search query
            is_file = os.path.exists(os.path.expanduser(t))
            self.process_term(f"file:/{t}" if is_file else f"search:/{t}")

    def select_directory(self):
        """Opens a file dialog to select an image or directory."""
        dialog = QFileDialog(self)
        dialog.setWindowTitle(UITexts.SELECT_IMAGE_TITLE)
        default_folder = os.path.expanduser("~")

        dialog.setDirectory(default_folder)
        dialog.setFileMode(QFileDialog.ExistingFile)
        # Don't force.
        # dialog.setOption(QFileDialog.Option.DontUseNativeDialog, False)

        dialog.setNameFilters([IMAGE_MIME_TYPES])

        if self.scanner and self.scanner._is_running:
            self.scanner.stop()
            self.scanner.wait()

        if dialog.exec():
            selected = dialog.selectedFiles()
            if selected:
                # Process the first selected file
                self.process_term(f"file:/{selected[0]}")

    def load_config(self):
        """Loads application settings from the JSON configuration file."""
        d = {}
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, 'r') as f:
                    d = json.load(f)
            except Exception as e:
                # Log the error to help diagnose why config might not be loading
                print(f"Error loading config file {CONFIG_PATH}: {e}")
                # import traceback; traceback.print_exc() # Uncomment for full traceback

        self.history = d.get("history", [])
        self.current_thumb_size = d.get("thumb_size",
                                        THUMBNAILS_DEFAULT_SIZE)
        self.slider.setValue(self.current_thumb_size)
        self.size_label.setText(f"{self.current_thumb_size}px")
        self.sort_combo.setCurrentIndex(d.get("sort_order", 0))
        self.view_mode_combo.setCurrentIndex(d.get("view_mode", 0))
        self.show_viewer_status_bar = d.get("show_viewer_status_bar", True)
        self.filmstrip_position = d.get("filmstrip_position", "bottom")
        self.show_filmstrip = d.get("show_filmstrip", False)
        self.show_faces = d.get("show_faces", False)
        if "active_dock_tab" in d:
            self.tags_tabs.setCurrentIndex(d["active_dock_tab"])
        self.face_names_history = d.get("face_names_history", [])
        self.pet_names_history = d.get("pet_names_history", [])
        self.body_names_history = d.get("body_names_history", [])
        self.object_names_history = d.get("object_names_history", [])
        self.landmark_names_history = d.get("landmark_names_history", [])

        max_tags = APP_CONFIG.get("tags_menu_max_items", TAGS_MENU_MAX_ITEMS_DEFAULT)
        self.mru_tags = deque(d.get("mru_tags", []),
                              maxlen=max_tags)

        self._load_shortcuts_config(d)

        # Restore window geometry and state
        if "geometry" in d:
            g = d["geometry"]
            self.setGeometry(g["x"], g["y"], g["w"], g["h"])
        if "window_state" in d:
            self.restoreState(
                QByteArray.fromBase64(d["window_state"].encode()))

    def _load_shortcuts_config(self, config_dict):
        """Loads global and viewer shortcuts from the configuration dictionary."""
        # Load global shortcuts
        self.loaded_global_shortcuts = config_dict.get("global_shortcuts")

        # Load viewer shortcuts
        # 1. Load defaults into a temporary dict.
        default_shortcuts = {}
        for action, (key, mods) in DEFAULT_VIEWER_SHORTCUTS.items():
            if action in VIEWER_ACTIONS:
                desc, _ = VIEWER_ACTIONS[action]
                default_shortcuts[(int(key),
                                   Qt.KeyboardModifiers(mods))] = (action, desc)

        # 2. Load user's config if it exists.
        v_shortcuts = config_dict.get("viewer_shortcuts", [])
        if v_shortcuts:
            user_shortcuts = {
                (k, Qt.KeyboardModifiers(m)): (act, desc)
                for (k, m), (act, desc) in v_shortcuts
            }

            # 3. Merge: Start with user's config, then add missing defaults.
            user_actions = {val[0] for val in user_shortcuts.values()}
            user_keys = set(user_shortcuts.keys())

            for key, (action, desc) in default_shortcuts.items():
                if action not in user_actions and key not in user_keys:
                    user_shortcuts[key] = (action, desc)

            self.viewer_shortcuts = user_shortcuts
        else:
            # No user config for viewer shortcuts, just use the defaults.
            self.viewer_shortcuts = default_shortcuts

    def save_config(self):
        """Saves application settings to the JSON configuration file."""
        # Update the global APP_CONFIG with the current state of the MainWindow
        APP_CONFIG["history"] = self.history
        APP_CONFIG["thumb_size"] = self.current_thumb_size
        APP_CONFIG["sort_order"] = self.sort_combo.currentIndex()
        APP_CONFIG["view_mode"] = self.view_mode_combo.currentIndex()
        APP_CONFIG["show_viewer_status_bar"] = self.show_viewer_status_bar
        APP_CONFIG["filmstrip_position"] = self.filmstrip_position
        APP_CONFIG["show_filmstrip"] = self.show_filmstrip
        APP_CONFIG["show_faces"] = self.show_faces
        APP_CONFIG["window_state"] = self.saveState().toBase64().data().decode()
        APP_CONFIG["active_dock_tab"] = self.tags_tabs.currentIndex()
        APP_CONFIG["face_names_history"] = self.face_names_history
        APP_CONFIG["pet_names_history"] = self.pet_names_history
        APP_CONFIG["body_names_history"] = self.body_names_history
        APP_CONFIG["object_names_history"] = self.object_names_history
        APP_CONFIG["landmark_names_history"] = self.landmark_names_history
        APP_CONFIG["mru_tags"] = list(self.mru_tags)

        # Save viewer shortcuts as list for JSON serialization
        v_shortcuts_list = []
        for (k, m), (act, desc) in self.viewer_shortcuts.items():
            try:
                mod_int = int(m)
            except TypeError:
                mod_int = m.value
            v_shortcuts_list.append([[k, mod_int], [act, desc]])
        APP_CONFIG["viewer_shortcuts"] = v_shortcuts_list

        # Save global shortcuts
        if hasattr(self, 'shortcut_controller') and self.shortcut_controller:
            g_shortcuts_list = []
            for (k, m), (act, ignore, desc, cat) in \
                    self.shortcut_controller._shortcuts.items():
                try:
                    mod_int = int(m)
                except TypeError:
                    mod_int = m.value
                g_shortcuts_list.append([[k, mod_int], [act, ignore, desc, cat]])
            APP_CONFIG["global_shortcuts"] = g_shortcuts_list

        APP_CONFIG["geometry"] = {"x": self.x(), "y": self.y(),
                                  "w": self.width(), "h": self.height()}

        save_app_config()

    def resizeEvent(self, e):
        """Handles window resize events to trigger a debounced grid refresh."""
        super().resizeEvent(e)
        self.thumbnails_refresh_timer.start()

    def eventFilter(self, source, event):
        """Filters events from child widgets, like viewport resize."""
        if source is self.thumbnail_view.viewport() and event.type() == QEvent.Resize:
            self.thumbnails_refresh_timer.start()
        return super().eventFilter(source, event)

    def open_current_folder(self):
        """Opens the directory of the selected image in the default file manager."""
        path = self.get_current_selected_path()
        if path:
            QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(path)))

    def handle_initial_args(self, args):
        """Handles command-line arguments passed to the application at startup."""
        path = " ".join(args).strip()
        full_path = os.path.abspath(os.path.expanduser(path))

        if os.path.isfile(full_path):
            self.add_to_history(f"file:/{full_path}")
            # Refresh combo box with history
            self.update_search_input()  # This is a disk read.

            # Open viewer directly
            self.active_viewer = ImageViewer(self.cache, [full_path], 0,
                                             initial_tags=None, initial_rating=0,
                                             parent=self, persistent=True)
            self._setup_viewer_sync(self.active_viewer)
            self.viewers.append(self.active_viewer)
            self.active_viewer.destroyed.connect(
                lambda obj=self.active_viewer: self.viewers.remove(obj)
                if obj in self.viewers else None)
            self.active_viewer.show()
            self.hide()  # Main window is hidden in direct view mode

            # Scan the file's directory in the background for context
            self._scan_all = False
            self.start_scan([full_path, str(Path(full_path).parent)],
                            sync_viewer=True, active_viewer=self.active_viewer)
        else:
            # If not a file, process as a generic term (path, search, or layout)
            term = path if path.startswith(("search:/", "file:/", "layout:/")) \
                else f"file:/{path}"
            self.process_term(term)

    def set_app_icon(self):
        """Sets the application icon from the current theme."""
        icon = QIcon.fromTheme(ICON_THEME, QIcon.fromTheme(ICON_THEME_FALLBACK))
        self.setWindowIcon(icon)

    # --- Context Menu ---
    def show_context_menu(self, pos):
        """Shows the context menu for the thumbnail view."""
        menu = QMenu(self)

        # Check if clicked on a header (which isn't usually selectable)
        index_at_pos = self.thumbnail_view.indexAt(pos)
        if index_at_pos.isValid() and \
           self.proxy_model.data(index_at_pos, ITEM_TYPE_ROLE) == 'header':
            group_name = self.proxy_model.data(index_at_pos, GROUP_NAME_ROLE)
            if group_name:
                action_toggle = menu.addAction(UITexts.COLLAPSE_EXPAND_GROUP)
                action_toggle.triggered.connect(
                    lambda: self.toggle_group_collapse(group_name))
                menu.exec(self.thumbnail_view.mapToGlobal(pos))
                return
        menu.setStyleSheet("QMenu { border: 1px solid #555; }")

        selected_indexes = self.thumbnail_view.selectedIndexes()
        if not selected_indexes:
            return

        def add_action_with_shortcut(target_menu, text, icon_name, action_name, slot):
            shortcut_str = ""
            if action_name and hasattr(self, 'shortcut_controller'):
                shortcut_map = self.shortcut_controller.action_to_shortcut
                if action_name in shortcut_map:
                    key, mods = shortcut_map[action_name]
                    try:
                        mod_val = int(mods)
                    except TypeError:
                        mod_val = mods.value
                    seq = QKeySequence(mod_val | key)
                    shortcut_str = seq.toString(QKeySequence.NativeText)

            display_text = f"{text}\t{shortcut_str}" if shortcut_str else text
            action = target_menu.addAction(QIcon.fromTheme(icon_name), display_text)
            action.triggered.connect(slot)
            return action

        action_view = menu.addAction(QIcon.fromTheme("image-x-generic"),
                                     UITexts.CONTEXT_MENU_VIEW)
        action_view.triggered.connect(lambda: self.open_viewer(selected_indexes[0]))

        menu.addSeparator()

        selection_menu = menu.addMenu(QIcon.fromTheme("edit-select"), UITexts.SELECT)
        add_action_with_shortcut(selection_menu, UITexts.CONTEXT_MENU_SELECT_ALL,
                                 "edit-select-all", "select_all",
                                 self.select_all_thumbnails)
        add_action_with_shortcut(selection_menu, UITexts.CONTEXT_MENU_SELECT_NONE,
                                 "edit-clear", "select_none",
                                 self.select_none_thumbnails)
        add_action_with_shortcut(selection_menu,
                                 UITexts.CONTEXT_MENU_INVERT_SELECTION,
                                 "edit-select-invert", "invert_selection",
                                 self.invert_selection_thumbnails)
        menu.addSeparator()

        open_submenu = menu.addMenu(QIcon.fromTheme("document-open"),
                                    UITexts.CONTEXT_MENU_OPEN)
        full_path = os.path.abspath(
            self.proxy_model.data(selected_indexes[0], PATH_ROLE))
        p_data = self.proxy_model.data(selected_indexes[0], PATH_ROLE)
        full_path = os.path.abspath(p_data) if p_data else ""
        self.populate_open_with_submenu(open_submenu, full_path)

        action_open_fullscreen = menu.addAction(
            QIcon.fromTheme("view-fullscreen"),
            UITexts.CONTEXT_MENU_FULLSCREEN_VIEWER)
        action_open_fullscreen.triggered.connect(
            lambda: self.open_in_fullscreen_viewer(selected_indexes[0]))

        path = self.proxy_model.data(selected_indexes[0], PATH_ROLE)
        action_open_location = menu.addAction(QIcon.fromTheme("folder-search"),
                                              UITexts.CONTEXT_MENU_OPEN_SEARCH_LOCATION)
        action_open_location.triggered.connect(
            lambda: self.process_term(f"file:/{os.path.dirname(path)}"))

        action_open_default_app = menu.addAction(
            QIcon.fromTheme("system-run"),
            UITexts.CONTEXT_MENU_OPEN_DEFAULT_APP)
        action_open_default_app.triggered.connect(
            lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(path))))

        menu.addSeparator()

        if HAVE_IMAGEHASH:
            action_find_similar = menu.addAction(QIcon.fromTheme("edit-find"), UITexts.MENU_FIND_SIMILAR)
            action_find_similar.triggered.connect(lambda: self.find_similar_images(path))

        menu.addSeparator()

        add_action_with_shortcut(menu, UITexts.CONTEXT_MENU_RENAME, "edit-rename",
                                 "rename_image",
                                 lambda: self.rename_image(selected_indexes[0].row()))

        action_move = menu.addAction(QIcon.fromTheme("edit-move"),
                                     UITexts.CONTEXT_MENU_MOVE_TO)
        action_move.triggered.connect(self.move_current_image)

        action_copy = menu.addAction(QIcon.fromTheme("edit-copy"),
                                     UITexts.CONTEXT_MENU_COPY_TO)
        action_copy.triggered.connect(self.copy_current_image)

        menu.addSeparator()

        rotate_menu = menu.addMenu(QIcon.fromTheme("transform-rotate"),
                                   UITexts.CONTEXT_MENU_ROTATE)

        action_rotate_ccw = rotate_menu.addAction(QIcon.fromTheme("object-rotate-left"),
                                                  UITexts.CONTEXT_MENU_ROTATE_LEFT)
        action_rotate_ccw.triggered.connect(lambda: self.rotate_current_image(-90))

        action_rotate_cw = rotate_menu.addAction(QIcon.fromTheme("object-rotate-right"),
                                                 UITexts.CONTEXT_MENU_ROTATE_RIGHT)
        action_rotate_cw.triggered.connect(lambda: self.rotate_current_image(90))

        menu.addSeparator()
        # The 'move_to_trash' action now uses the configurable default behavior
        add_action_with_shortcut(menu, UITexts.CONTEXT_MENU_TRASH, "user-trash",
                                 "move_to_trash",
                                 lambda: self.delete_current_image(permanent=None))
        add_action_with_shortcut(menu, UITexts.CONTEXT_MENU_DELETE, "edit-delete",
                                 "delete_permanently",
                                 lambda: self.delete_current_image(permanent=True))
        menu.addSeparator()

        clipboard_menu = menu.addMenu(QIcon.fromTheme("edit-copy"),
                                      UITexts.CONTEXT_MENU_CLIPBOARD)

        action_copy_image = clipboard_menu.addAction(QIcon.fromTheme("image-x-generic"),
                                                     UITexts.VIEWER_MENU_COPY_IMAGE)
        action_copy_image.triggered.connect(self.copy_image_to_clipboard)
        if len(selected_indexes) > 1:
            action_copy_image.setEnabled(False)

        action_copy_path = clipboard_menu.addAction(
            QIcon.fromTheme("document-properties"), UITexts.VIEWER_MENU_COPY_PATH)
        action_copy_path.triggered.connect(self.copy_file_path_to_clipboard)

        action_copy_dir = clipboard_menu.addAction(QIcon.fromTheme("folder"),
                                                   UITexts.CONTEXT_MENU_COPY_DIR)
        action_copy_dir.triggered.connect(self.copy_dir_path)

        menu.addSeparator()
        action_regenerate_thumbnail = menu.addAction(UITexts.CONTEXT_MENU_REGENERATE)
        action_regenerate_thumbnail.triggered.connect(
            lambda: self.regenerate_thumbnail(path))

        menu.addSeparator()

        action_props = menu.addAction(QIcon.fromTheme("document-properties"),
                                      UITexts.CONTEXT_MENU_PROPERTIES)
        action_props.triggered.connect(self.show_properties)

        menu.exec(self.thumbnail_view.mapToGlobal(pos))

    def toggle_group_collapse(self, group_name):
        """Toggles the collapsed state of a group."""
        if group_name in self.proxy_model.collapsed_groups:
            self.proxy_model.collapsed_groups.remove(group_name)
        else:
            self.proxy_model.collapsed_groups.add(group_name)
        self.proxy_model.invalidate()
        self._visible_paths_cache = None

    def regenerate_thumbnail(self, path):
        """Regenerates the thumbnail for the specified path."""
        if not path:
            return

        # Create a ThumbnailGenerator to regenerate the thumbnail
        size = self._get_tier_for_size(self.current_thumb_size)
        self.thumbnail_generator = ThumbnailGenerator(
            self.cache, [path], size, self.thread_pool_manager)
        self.thumbnail_generator.generation_complete.connect(
            self.on_high_res_generation_finished)
        self.thumbnail_generator.progress.connect(
            lambda p, t: self.status_lbl.setText(
                UITexts.THUMBNAILS_REGENERATE_PROGRESS.format(p, t))
        )
        self.thumbnail_generator.start()

        # Invalidate the cache so the new thumbnail is loaded
        self.cache.invalidate_path(path)
        self.rebuild_view()

    def get_app_info(self, desktop_file_id):
        """Gets the readable name and icon of an application from its .desktop file."""
        if desktop_file_id in self._app_info_cache:
            return self._app_info_cache[desktop_file_id]

        desktop_file_id = desktop_file_id.split(':')[-1].strip()
        desktop_path = desktop_file_id
        if not desktop_path.startswith("/"):
            # Search in standard application paths including flatpak/snap/local
            search_paths = [
                "/usr/share/applications",
                os.path.expanduser("~/.local/share/applications"),
                "/usr/local/share/applications",
                "/var/lib/flatpak/exports/share/applications",
                "/var/lib/snapd/desktop/applications"
            ]

            if "XDG_DATA_DIRS" in os.environ:
                for path in os.environ["XDG_DATA_DIRS"].split(":"):
                    if path:
                        app_path = os.path.join(path, "applications")
                        if app_path not in search_paths:
                            search_paths.append(app_path)

            for path in search_paths:
                full_p = os.path.join(path, desktop_file_id)
                if os.path.exists(full_p):
                    desktop_path = full_p
                    break

        name = ""
        icon = ""
        try:
            if os.path.exists(desktop_path):
                name = subprocess.check_output(
                    ["kreadconfig6", "--file", desktop_path,
                     "--group", "Desktop Entry", "--key", "Name"],
                    text=True
                ).strip()

                icon = subprocess.check_output(
                    ["kreadconfig6", "--file", desktop_path,
                     "--group", "Desktop Entry", "--key", "Icon"],
                    text=True
                ).strip()
        except Exception:
            pass

        if not name:
            name = os.path.basename(
                desktop_file_id).replace(".desktop", "").capitalize()

        result = (name, icon, desktop_path)
        self._app_info_cache[desktop_file_id] = result
        return result

    def populate_open_with_submenu(self, menu, full_path):
        """Populates the 'Open With' submenu with associated applications."""
        if not full_path:
            return
        try:
            # 1. Get the mimetype of the file
            mime_query = subprocess.check_output(["kmimetypefinder", full_path],
                                                 text=True).strip()

            if mime_query in self._open_with_cache:
                app_entries = self._open_with_cache[mime_query]
            else:
                # 2. Query for associated applications using 'gio mime'
                apps_cmd = ["gio", "mime", mime_query]
                output = subprocess.check_output(apps_cmd, text=True).splitlines()

                app_entries = []
                seen_resolved_paths = set()  # For deduplication based on resolved path

                for line in output:
                    line = line.strip()
                    if ":" not in line and line.endswith(".desktop"):
                        app_name, icon_name, resolved_path = self.get_app_info(line)
                        if resolved_path in seen_resolved_paths:
                            continue
                        seen_resolved_paths.add(resolved_path)
                        # Store original line for gtk-launch
                        app_entries.append((app_name, icon_name, line))
                self._open_with_cache[mime_query] = app_entries

            if not app_entries:
                menu.addAction(UITexts.CONTEXT_MENU_NO_APPS_FOUND).setEnabled(False)
            else:
                for app_name, icon_name, desktop_file_id_from_gio_mime in app_entries:
                    icon = QIcon.fromTheme(icon_name) if icon_name else QIcon()
                    action = menu.addAction(icon, app_name)
                    action.triggered.connect(
                        lambda checked=False, df=desktop_file_id_from_gio_mime:
                        subprocess.Popen(["gtk-launch", df, full_path]))

            # menu.addSeparator()
            # action_other = menu.addAction(QIcon.fromTheme("applications-other"),
            #                               UITexts.OPEN_WITH_OTHER)
            # action_other.triggered.connect(
            #     lambda: self.open_with_system_chooser(full_path))
        except Exception:
            action = menu.addAction(UITexts.CONTEXT_MENU_ERROR_LISTING_APPS)
            action.setEnabled(False)

    def open_with_system_chooser(self, path):
        """Opens the system application chooser using xdg-desktop-portal."""
        if not path:
            return

        # Use QDBusMessage directly to avoid binding issues with
        # QDBusInterface.asyncCall
        msg = QDBusMessage.createMethodCall(
            "org.freedesktop.portal.Desktop",
            "/org/freedesktop/portal/desktop",
            "org.freedesktop.portal.OpenURI",
            "OpenURI"
        )
        # Arguments: parent_window (str), uri (str), options (dict/a{sv})
        msg.setArguments(["", QUrl.fromLocalFile(path).toString(), {"ask": True}])
        QDBusConnection.sessionBus().call(msg, QDBus.NoBlock)

    def copy_image_to_clipboard(self):
        """Copies the full image of the selected thumbnail to the clipboard."""
        path = self.get_current_selected_path()
        if not path:
            return
        # This is a disk read, but it's on user action.
        img = QImage(path)
        if not img.isNull():
            QApplication.clipboard().setImage(img)

    def copy_file_path_to_clipboard(self):
        """Copies the file path(s) of the selected image(s) to the clipboard."""
        paths = self.get_selected_paths()
        if not paths:
            return
        QApplication.clipboard().setText("\n".join(paths))

    def copy_dir_path(self):
        """Copies the directory path(s) of the selected image(s) to the clipboard."""
        paths = self.get_selected_paths()
        if not paths:
            return
        dir_paths = sorted(list(set(os.path.dirname(p) for p in paths)))
        QApplication.clipboard().setText("\n".join(dir_paths))

    def show_properties(self):
        """Shows the custom properties dialog for the selected file."""
        full_path = self.get_current_selected_path()
        if not full_path:
            return
        full_path = os.path.abspath(full_path)

        # Extract metadata from selected item
        tags = []
        rating = 0
        selected_indexes = self.thumbnail_view.selectedIndexes()
        if selected_indexes:
            idx = selected_indexes[0]
            tags = self.proxy_model.data(idx, TAGS_ROLE)
            rating = self.proxy_model.data(idx, RATING_ROLE) or 0

        dlg = PropertiesDialog(
            full_path, initial_tags=tags, initial_rating=rating, parent=self)
        dlg.exec()

    def open_in_fullscreen_viewer(self, proxy_index):
        """Opens the selected image in a new ImageViewer in fullscreen mode."""
        viewer = self.open_viewer(proxy_index)
        if viewer:
            viewer.toggle_fullscreen()

    def clear_thumbnail_cache(self):
        """Clears the entire in-memory and on-disk thumbnail cache."""
        confirm = QMessageBox(self)
        confirm.setIcon(QMessageBox.Warning)
        confirm.setWindowTitle(UITexts.CONFIRM_CLEAR_CACHE_TITLE)
        confirm.setText(UITexts.CONFIRM_CLEAR_CACHE_TEXT)
        confirm.setInformativeText(UITexts.CONFIRM_CLEAR_CACHE_INFO)
        confirm.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        confirm.setDefaultButton(QMessageBox.No)
        if confirm.exec() != QMessageBox.Yes:
            return

        self.cache.clear_cache()
        self.status_lbl.setText(UITexts.CACHE_CLEARED)

    def on_fs_file_created(self, path):
        """Handles a new file being created in a monitored directory."""
        if os.path.abspath(path) in self._paths_being_modified_by_app:
            return
        # Add to batch queue and (re)start the debounce timer
        self._fs_created_queue.add(path)
        self._fs_created_timer.start()

    def _process_fs_created_batch(self):
        """Processes all accumulated file creation events at once."""
        paths = list(self._fs_created_queue)
        self._fs_created_queue.clear()

        valid_new_items = []
        for p in paths:
            p = os.path.abspath(p)
            if os.path.exists(p) and p not in self._known_paths:
                if os.path.splitext(p)[1].lower() in IMAGE_EXTENSIONS:
                    valid_new_items.append(p)

        if not valid_new_items:
            return

        # If the batch is very large, a full scan is more efficient than individual
        # stats
        if len(valid_new_items) > 50:
            self.refresh_content()
            return

        # For smaller batches, process metadata and update model
        for path in valid_new_items:
            try:
                res = load_common_metadata(path)
                stat_res = os.stat(path)
                mtime = stat_res.st_mtime
                inode = stat_res.st_ino
                dev = stat_res.st_dev

                # tuple: (path, qi, mtime, tags, rating, inode, dev)
                new_item_data = (path, None, mtime, res.tags, res.rating, inode, dev)
                self.found_items_data.append(new_item_data)
                self._known_paths.add(path)
                self.proxy_model.add_to_cache(path, res.tags)
            except Exception:
                continue

        # Trigger an incremental rebuild of the view
        self.rebuild_view()

        # Start background generation for the new items
        self.generate_missing_thumbnails(self._current_thumb_tier)

        if len(valid_new_items) == 1:
            msg = f"New file detected: {os.path.basename(valid_new_items[0])}"
        else:
            msg = f"Detected {len(valid_new_items)} new files"
        self.status_lbl.setText(msg)

    def on_fs_file_deleted(self, path):
        """Handles a file being deleted from a monitored directory."""
        path = os.path.abspath(path)
        if path in self._paths_being_modified_by_app:
            return
        if path not in self._known_paths:
            return  # Not a file we're tracking

        # Remove from internal data structures
        self.found_items_data = [item for item in self.found_items_data
                                 if item[0] != path]
        self._known_paths.discard(path)
        self.proxy_model.remove_from_cache(path)
        self.cache.invalidate_path(path)  # Clear from cache

        # Update any open viewers
        for w in QApplication.topLevelWidgets():
            if isinstance(w, ImageViewer):
                if path in w.controller.image_list:
                    try:
                        deleted_idx = w.controller.image_list.index(path)
                        new_list = list(w.controller.image_list)
                        new_list.remove(path)
                        w.refresh_after_delete(new_list, deleted_idx)
                    except (ValueError, RuntimeError):
                        pass

        # Invalidate caches that might hold references to the deleted path
        self._visible_paths_cache = None
        keys_to_remove = [k for k in self._group_info_cache if k[0] == path]
        for k in keys_to_remove:
            del self._group_info_cache[k]
        self.rebuild_view()
        self.status_lbl.setText(f"File deleted: {os.path.basename(path)}")

    def on_fs_file_moved(self, old_path, new_path):
        """Handles a file being renamed or moved."""
        old_path = os.path.abspath(old_path)
        new_path = os.path.abspath(new_path)

        if old_path in self._paths_being_modified_by_app:
            return

        is_old_img = os.path.splitext(old_path)[1].lower() in IMAGE_EXTENSIONS
        is_new_img = os.path.splitext(new_path)[1].lower() in IMAGE_EXTENSIONS

        if is_old_img and is_new_img:
            if old_path in self._known_paths:
                self.propagate_rename(old_path, new_path)
            else:
                self.on_fs_file_created(new_path)
        elif is_old_img:
            # Moved out or renamed to non-image
            self.on_fs_file_deleted(old_path)
        elif is_new_img:
            # Moved in from outside
            self.on_fs_file_created(new_path)

    def on_fs_file_modified(self, path):
        """Handles a file being modified in a monitored directory."""
        path = os.path.abspath(path)
        if path not in self._known_paths:
            return  # Not a file we're tracking

        # If this modification was initiated by the app, ignore it
        if path in self._paths_being_modified_by_app:
            return

        # External modification: refresh thumbnail, metadata, name
        try:
            new_stat = os.stat(path)
            new_mtime = new_stat.st_mtime

            # Invalidate the cache to force thumbnail regeneration
            self.cache.invalidate_path(path)

            # Re-read metadata from disk
            res = load_common_metadata(path)

            # Update our internal tracking list
            self._update_internal_data(
                path, mtime=new_mtime, tags=res.tags, rating=res.rating,
                inode=new_stat.st_ino, dev=new_stat.st_dev)

            # Update proxy filter cache
            self.proxy_model.add_to_cache(path, res.tags)

            # Create a ThumbnailGenerator to regenerate the thumbnail in the background
            size = self._get_tier_for_size(self.current_thumb_size)
            self.thumbnail_generator = ThumbnailGenerator(
                self.cache, [path], size, self.thread_pool_manager)
            self.thumbnail_generator.generation_complete.connect(
                self.thumbnail_view.viewport().update)
            self.thumbnail_generator.start()

            # Update the standard item in the model directly
            if path in self._path_to_model_index:
                p_idx = self._path_to_model_index[path]
                if p_idx.isValid():
                    item = self.thumbnail_model.itemFromIndex(QModelIndex(p_idx))
                    if item:
                        # Refresh name in case it changed
                        basename = os.path.basename(path)
                        item.setText(basename)

                        # Update metadata roles
                        item.setData(new_mtime, MTIME_ROLE)
                        item.setData(res.tags, TAGS_ROLE)
                        item.setData(res.rating, RATING_ROLE)
                        item.setData(new_stat.st_ino, INODE_ROLE)
                        item.setData(new_stat.st_dev, DEVICE_ROLE)

                        # Clear fallback scan thumbnail to force high-res reload
                        item.setData(None, IMAGE_DATA_ROLE)

                        # Update tooltip with new tags
                        tooltip_text = f"{basename}\n{path}"
                        if res.tags:
                            display_tags = [t.split('/')[-1] for t in res.tags]
                            tooltip_text += f"\n{UITexts.TAGS_TAB}: {', '.join(display_tags)}"
                        item.setToolTip(tooltip_text)

                        # Notify views that this item has changed
                        source_index = QModelIndex(p_idx)
                        self.thumbnail_model.dataChanged.emit(source_index, source_index)

            # Handle grouped vs flat views
            is_grouped = self.view_mode_combo.currentIndex() > 0
            if is_grouped:
                # Grouped views need a full rebuild to ensure correct group headers and order
                self.rebuild_view(full_reset=True)
            else:
                # Flat view: invalidate proxy model to update sorting and filtering on the item
                self.proxy_model.invalidate()

            # Update sidebar/status panel if this file is selected
            selected_indexes = self.thumbnail_view.selectedIndexes()
            selected_paths = [self.proxy_model.data(idx, PATH_ROLE) for idx in selected_indexes]
            if path in selected_paths:
                self.update_tag_edit_widget()
                self.update_info_widget()

            # Update other open viewers currently showing this file
            for v in list(self.viewers):
                try:
                    if isinstance(v, ImageViewer) and v.isVisible():
                        if v.controller.get_current_path() == path:
                            v.update_view(resize_win=False)
                            v.populate_filmstrip()
                        elif path in v.controller.image_list:
                            v.populate_filmstrip()
                except RuntimeError:
                    continue

            self.status_lbl.setText(f"File modified: {os.path.basename(path)}")
        except Exception:
            # Fallback to full refresh if error occurs
            self.refresh_content()

    def _mark_path_as_app_modified(self, path):
        """Marks a path as being modified by the application to ignore FS events."""
        abs_path = os.path.abspath(path)
        parent_path = os.path.dirname(abs_path)
        self._paths_being_modified_by_app.add(abs_path)
        self._paths_being_modified_by_app.add(parent_path)

        # Schedule removal after a delay to allow all FS events to propagate
        QTimer.singleShot(
            1000, lambda: self._paths_being_modified_by_app.discard(abs_path))
        QTimer.singleShot(
            1000, lambda: self._paths_being_modified_by_app.discard(parent_path))

    def on_fs_watcher_status_changed(self, is_monitoring):
        """Updates the UI indicator for the FileSystemWatcher."""
        if is_monitoring:
            self.fs_watcher_status_lbl.setPixmap(
                QIcon.fromTheme("folder-open").pixmap(16, 16))
            self.fs_watcher_status_lbl.show()
        else:
            self.fs_watcher_status_lbl.hide()

    def on_fs_directory_modified(self, path):
        """Handles a directory being modified (e.g., new subfolder, mass changes)."""
        path = os.path.abspath(path)

        if path in self._paths_being_modified_by_app:
            return

        # Trigger a debounced full refresh. This is useful for syncing large
        # external changes (bulk operations, directory deletions) that are
        # more robustly handled by a full scan than incremental updates.
        if not self._is_loading and not self.is_cleaning:
            self._fs_dir_refresh_timer.start()

    def on_fs_directory_moved(self, old_path, new_path):
        """Handles a directory being renamed or moved."""
        # For directory moves, a full refresh is the most reliable way to sync
        # since all child paths have changed and individual file move signals
        # might not be emitted for every item inside.
        self.on_fs_directory_modified(new_path)

    def propagate_rename(self, old_path, new_path, source_viewer=None):
        """Propagates a file rename across the application."""
        old_path = os.path.abspath(old_path)
        new_path = os.path.abspath(new_path)

        self._visible_paths_cache = None
        # Update found_items_data to ensure consistency on future rebuilds
        current_tags = None
        for i, item_data in enumerate(self.found_items_data):
            if item_data[0] == old_path:
                # tuple structure: (path, qi, mtime, tags, rating, inode, dev)
                self.found_items_data[i] = (new_path,) + item_data[1:]
                current_tags = item_data[3]
                self._known_paths.discard(old_path)
                self._known_paths.add(new_path)

                # Clean up group cache since the key (path) has changed
                self.duplicate_cache.rename_entry(old_path, new_path)
                cache_key = (old_path, item_data[2], item_data[4])
                if cache_key in self._group_info_cache:
                    del self._group_info_cache[cache_key]
                break

        # Update proxy model cache to avoid stale entries
        self.proxy_model.remove_from_cache(old_path)
        if current_tags is not None:
            self.proxy_model.add_to_cache(new_path, current_tags)

        # Update the main model
        if old_path in self._path_to_model_index:
            p_idx = self._path_to_model_index.pop(old_path)
            if p_idx.isValid():
                item = self.thumbnail_model.itemFromIndex(QModelIndex(p_idx))
                if item:
                    item.setData(new_path, PATH_ROLE)
                    item.setText(os.path.basename(new_path))
                    item.setData(os.path.dirname(new_path), DIR_ROLE)
                    # Actualizar el tooltip ya que contiene la ruta antigua
                    tags = item.data(TAGS_ROLE) or []
                    tooltip_text = f"{os.path.basename(new_path)}\n{new_path}"
                    if tags:
                        display_tags = [t.split('/')[-1] for t in tags]
                        tooltip_text += f"\n{UITexts.TAGS_TAB}: {', '.join(display_tags)}"
                    item.setToolTip(tooltip_text)

                    self._path_to_model_index[new_path] = p_idx
                    source_index = QModelIndex(p_idx)
                    self.thumbnail_model.dataChanged.emit(source_index, source_index)

        # Update the cache entry
        self.cache.rename_entry(old_path, new_path)

        # Invalidate parent directory cache to force re-scan
        self.cache.invalidate_directory_cache(os.path.dirname(old_path))
        new_dir = os.path.dirname(new_path)
        if new_dir != os.path.dirname(old_path):
            self.cache.invalidate_directory_cache(new_dir)

        # Update other open viewers
        for v in list(self.viewers):
            try:
                if v is not source_viewer and isinstance(v, ImageViewer) and v.isVisible():
                    if old_path in v.controller.image_list:
                        try:
                            idx = v.controller.image_list.index(old_path)
                            v.controller.image_list[idx] = new_path
                            if v.controller.index == idx:
                                v.update_view(resize_win=False)
                            v.populate_filmstrip()
                        except ValueError:
                            pass
            except RuntimeError:
                continue

        # rebuild_view(full_reset=False) garantiza que el orden se actualice
        # quirúrgicamente sin parpadeos ni re-escaneos de disco.
        self.rebuild_view(full_reset=False)

    def rename_image(self, proxy_row_index):
        """Handles the logic for renaming a file from the main thumbnail view."""
        proxy_index = self.proxy_model.index(proxy_row_index, 0)
        if not proxy_index.isValid():
            return

        while True:
            old_path = self.proxy_model.data(proxy_index, PATH_ROLE)
            if not old_path:
                return
            old_dir = os.path.dirname(old_path)
            old_filename = os.path.basename(old_path)
            base_name, extension = os.path.splitext(old_filename)

            new_base, ok = QInputDialog.getText(
                self, UITexts.RENAME_FILE_TITLE,
                UITexts.RENAME_FILE_TEXT.format(old_filename),
                QLineEdit.Normal, base_name
            )

            if ok and new_base and new_base != base_name:
                # Re-add extension if the user omitted it
                new_base_name, new_extension = os.path.splitext(new_base)
                if new_extension == extension:
                    new_filename = new_base
                else:
                    new_filename = new_base_name + extension

                new_path = os.path.join(old_dir, new_filename)
                self._mark_path_as_app_modified(old_path)
                self._mark_path_as_app_modified(new_path)

                if os.path.exists(new_path):
                    QMessageBox.warning(self,
                                        UITexts.RENAME_ERROR_TITLE,
                                        UITexts.RENAME_ERROR_EXISTS.format(
                                            new_filename))
                    # Loop again to ask for a different name
                else:
                    try:
                        os.rename(old_path, new_path)
                        self.propagate_rename(old_path, new_path)
                        self.status_lbl.setText(
                            UITexts.FILE_RENAMED.format(new_filename))
                        break
                    except Exception as e:
                        QMessageBox.critical(self,
                                             UITexts.SYSTEM_ERROR,
                                             UITexts.ERROR_RENAME.format(str(e)))
                        break
            else:
                break

    def select_all_thumbnails(self):
        """Selects all visible items in the thumbnail view."""
        if not self.thumbnail_view.isVisible() or self.proxy_model.rowCount() == 0:
            return
        selection_model = self.thumbnail_view.selectionModel()
        # Create a selection that covers all rows in the proxy model
        top_left = self.proxy_model.index(0, 0)
        bottom_right = self.proxy_model.index(self.proxy_model.rowCount() - 1, 0)
        selection = QItemSelection(top_left, bottom_right)
        selection_model.select(selection, QItemSelectionModel.Select)

    def select_none_thumbnails(self):
        """Clears the selection in the thumbnail view."""
        if not self.thumbnail_view.isVisible():
            return
        self.thumbnail_view.selectionModel().clearSelection()

    def invert_selection_thumbnails(self):
        """Inverts the current selection of visible items."""
        if not self.thumbnail_view.isVisible() or self.proxy_model.rowCount() == 0:
            return
        selection_model = self.thumbnail_view.selectionModel()

        # Get all selectable items
        all_items_selection = QItemSelection()
        for row in range(self.proxy_model.rowCount()):
            index = self.proxy_model.index(row, 0)
            if self.proxy_model.data(index, ITEM_TYPE_ROLE) == 'thumbnail':
                all_items_selection.select(index, index)

        # Invert the current selection against all selectable items
        selection_model.select(all_items_selection, QItemSelectionModel.Toggle)

    def update_load_all_button_state(self):
        """Updates the text and tooltip of the 'load all' button based on its state."""
        if self._is_loading_all:
            self.btn_load_all.setIcon(QIcon.fromTheme("process-stop"))
            self.btn_load_all.setToolTip(UITexts.LOAD_ALL_TOOLTIP_ALT)
        else:
            self.btn_load_all.setIcon(QIcon.fromTheme("media-playback-start"))
            self.btn_load_all.setToolTip(UITexts.LOAD_ALL_TOOLTIP)

    def _create_language_menu(self):
        """Creates the language selection menu and adds it to the menubar."""
        # Assuming you have a settings or view menu. Add it where you see fit.
        # If you don't have one, you can add it directly to the menu bar.
        settings_menu = self.menuBar().addMenu("&Settings")  # Or get an existing menu

        language_menu = settings_menu.addMenu(UITexts.MENU_LANGUAGE)
        lang_group = QActionGroup(self)
        lang_group.setExclusive(True)
        lang_group.triggered.connect(self._on_language_changed)

        for code, name in SUPPORTED_LANGUAGES.items():
            action = QAction(name, self, checkable=True)
            action.setData(code)
            if code == APP_CONFIG.get("language", DEFAULT_LANGUAGE):
                action.setChecked(True)
            language_menu.addAction(action)
            lang_group.addAction(action)

    def _on_language_changed(self, action):
        """Handles language change, saves config, and prompts for restart."""
        new_lang = action.data()
        # Only save and show message if the language actually changed
        if new_lang != APP_CONFIG.get("language", DEFAULT_LANGUAGE):
            APP_CONFIG["language"] = new_lang
            save_app_config()

            # Inform user that a restart is needed for the change to take effect
            msg_box = QMessageBox(self)
            msg_box.setWindowTitle(UITexts.RESTART_REQUIRED_TITLE)
            msg_box.setText(UITexts.RESTART_REQUIRED_TEXT.format(
                language=action.text()))
            msg_box.setIcon(QMessageBox.Information)
            msg_box.setStandardButtons(QMessageBox.Ok)
            msg_box.exec()

    def start_duplicate_detection(self, force_full=False, custom_paths=None):
        """Initiates the duplicate image detection process."""
        if self.duplicate_detector and self.duplicate_detector.isRunning():
            QMessageBox.information(self, UITexts.DUPLICATE_DETECTION_TITLE,
                                    UITexts.DUPLICATE_ALREADY_RUNNING)
            return

        # Get all image paths currently known to the application or provided list
        paths_to_scan = custom_paths \
            if custom_paths is not None else self.get_all_image_paths()
        if not paths_to_scan:
            QMessageBox.information(self, UITexts.DUPLICATE_DETECTION_TITLE,
                                    UITexts.DUPLICATE_NO_IMAGES)
            return

        # Get settings from APP_CONFIG
        method = APP_CONFIG.get("duplicate_method", "histogram_hashing")
        threshold = APP_CONFIG.get("duplicate_threshold", 90)

        self.duplicate_detector = DuplicateDetector(
            paths_to_scan, self.duplicate_cache,
            self.thread_pool_manager, method, threshold, force_full=force_full)

        self.duplicate_detector.progress_update.connect(
            self.on_duplicate_detection_progress)
        self.duplicate_detector.duplicates_found.connect(
            self.on_duplicates_found)
        self.duplicate_detector.detection_finished.connect(
            self.on_duplicate_detection_finished)

        self.progress_bar.setValue(0)
        self.progress_bar.setCustomColor(None)
        self.progress_bar.show()
        self.btn_cancel_duplicates.show()
        self.status_counter_lbl.show()
        self.status_lbl.setText(UITexts.DUPLICATE_STARTING)

        self.duplicate_detector.start()

    def on_duplicate_detection_progress(self, current, total, message):
        """Updates the UI with progress during duplicate detection."""
        percent = int((current / total) * 100) if total > 0 else 0

        # Visual differentiation of detection phases using colors:
        if percent < 50:
            # Phase 1: Hashing images (Blue)
            self.progress_bar.setCustomColor(QColor("#3498db"))
        else:
            # Phase 2: Mathematical comparison (Orange/Amber)
            self.progress_bar.setCustomColor(QColor("#f39c12"))

        self.progress_bar.setValue(percent)
        self.status_counter_lbl.setText(f"[{current}/{total}]")
        self.status_lbl.setText(message)

    def on_duplicates_found(self, duplicates):
        """Handles the list of found duplicate image pairs."""
        if not duplicates:
            QMessageBox.information(self, UITexts.DUPLICATE_DETECTION_TITLE,
                                    UITexts.DUPLICATE_NONE_FOUND)
            return

        dialog = DuplicateManagerDialog(duplicates, self.duplicate_cache, self)
        dialog.show()

    def on_duplicate_detection_finished(self):
        """Cleans up after duplicate detection is complete."""
        self.progress_bar.setValue(100)
        self.progress_bar.setCustomColor(
            QColor("#2ecc71"))  # Green for success
        self.hide_progress_timer.start(2000)  # Hide after 2 seconds
        self.btn_cancel_duplicates.hide()
        self.status_counter_lbl.hide()
        self.status_lbl.setText(UITexts.DUPLICATE_FINISHED)
        self.duplicate_detector = None

    def cancel_duplicate_detection(self):
        """Stops the duplicate detection thread."""
        if self.duplicate_detector and self.duplicate_detector.isRunning():
            self.duplicate_detector.stop()
            self.duplicate_detector.wait()
            self.status_lbl.setText(UITexts.CANCEL)
            self.btn_cancel_duplicates.hide()
            self.status_counter_lbl.hide()

    def find_similar_images(self, path):
        """Opens the similar images search dialog for the given path."""
        if not HAVE_IMAGEHASH:
            return
        dialog = SimilarImagesDialog(path, self)
        dialog.show()


def main():
    """The main entry point for the Bagheera Image Viewer application."""
    app = QApplication(sys.argv)

    # Increase QPixmapCache limit (default is usually small, ~10MB) to ~100MB
    QPixmapCache.setCacheLimit(104857600)  # Old value: 102400

    app.setApplicationName(PROG_NAME)
    app.setDesktopFileName(PROG_ID)

    icon_path = os.path.join(os.path.dirname(__file__), "..", "assets", "bagheeraview.png")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    duplicate_cache = DuplicateCache() if HAVE_IMAGEHASH else None
    thread_pool_manager = ThreadPoolManager()
    cache = ThumbnailCache()
    args = [a for a in sys.argv[1:] if a != "--x11"]
    win = MainWindow(cache, args, thread_pool_manager, duplicate_cache)
    app.installEventFilter(win.shortcut_controller)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
