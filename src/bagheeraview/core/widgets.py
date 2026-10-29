"""
Custom Widgets for the Bagheera Image Viewer.

This module provides specialized Qt widgets used throughout the Bagheera UI,
including:
- TagTreeView: A tree view with custom click handling for tag management.
- TagEditWidget: A comprehensive widget for viewing and editing file tags,
  integrating with Baloo for available tags.
- LayoutsWidget: A widget to manage, save, and load window layouts.
- HistoryWidget: A widget to display and manage search/view history.
"""
import os
import glob
import shutil
import json
import lmdb
import logging
import subprocess
from datetime import datetime
from collections import deque

from PySide6.QtWidgets import (
    QApplication, QWidget,  QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton,
    QMessageBox, QSizePolicy, QInputDialog, QTableWidget, QTableWidgetItem,
    QMenu, QHeaderView, QAbstractItemView, QTreeView, QLabel, QTextEdit,
    QComboBox, QCompleter, QToolBar, QDialog, QDialogButtonBox, QListWidget,
    QProgressBar, QRadioButton
)
from PySide6.QtGui import (
    QIcon, QStandardItemModel, QStandardItem, QColor, QPainter, QPen,
    QPalette, QAction, QKeySequence, QDesktopServices
)
from PySide6.QtCore import (
    Signal, QSortFilterProxyModel, Slot, QStringListModel, Qt, QTimer,
    QModelIndex, QObject, QUrl, QFile, QIODevice
)

from .md_editor import MarkdownEditorWidget
from .metadatamanager import XattrManager
from .xmpmanager import XmpManager
try:
    from bagheerasearch.core.search_lib.search import BagheeraSearcher
except ImportError:
    BagheeraSearcher = None
from .constants import (
    LAYOUTS_DIR, RATING_XATTR_NAME, XATTR_COMMENT_NAME, XATTR_NAME, UITexts,
    FACES_MENU_MAX_ITEMS_DEFAULT, APP_CONFIG, FAVORITES_PATH, PROG_FILE_NAME,
    DIRECTORY_TAG_INFO, TAG_INFO_TEMPLATE, APP_DATA_DIR
)

from .metadatamanager import MetadataManager, HAVE_EXIV2

logger = logging.getLogger(__name__)


class TagTreeView(QTreeView):
    """Custom TreeView supporting Ctrl+Click to force-mark changes.

    This class extends QTreeView to implement a special handling for Ctrl+Click
    events on checkable items, allowing users to forcefully toggle their state.
    """

    search_requested = Signal(object)
    search_on_new_session_requested = Signal(object)
    add_and_requested = Signal(object)
    add_or_requested = Signal(object)
    rename_all_requested = Signal(object)
    rename_viewed_requested = Signal(object)
    add_to_quick_tags_requested = Signal(object)
    remove_from_quick_tags_requested = Signal(object)
    tag_info_requested = Signal(object)

    def mousePressEvent(self, event):
        """Handles mouse press events to implement Ctrl+Click toggling.

        If Ctrl is held down while clicking a checkable item, its check state
        is toggled directly, bypassing the default model behavior. This is used
        to "force" a change state on a tag.

        Args:
            event (QMouseEvent): The mouse press event.
        """
        index = self.indexAt(event.position().toPoint())
        if index.isValid() and event.modifiers() == Qt.ControlModifier:
            # When Ctrl is pressed, we manually toggle the check state
            # of the item. This allows forcing a "changed" state even if
            # the tag is already applied to all/no files.
            model = self.model()
            source_index = (model.mapToSource(index)
                            if isinstance(model, QSortFilterProxyModel)
                            else index)
            item = model.sourceModel().itemFromIndex(source_index)
            if item and item.isCheckable():
                # Toggle check state manually
                new_state = (Qt.Unchecked if item.checkState() == Qt.Checked
                             else Qt.Checked)
                item.setCheckState(new_state)
                return
        super().mousePressEvent(event)

    def contextMenuEvent(self, event):
        """Shows a context menu to trigger a search for the selected tag."""
        index = self.indexAt(event.pos())
        if index.isValid():
            model = self.model()
            source_index = (model.mapToSource(index)
                            if isinstance(model, QSortFilterProxyModel)
                            else index)
            item = model.sourceModel().itemFromIndex(source_index)
            # Don't show menu for the root items "USED TAGS", "ALL TAGS"
            if item and item.parent():
                menu = QMenu(self)
                search_action = menu.addAction(
                    QIcon.fromTheme("system-search"), UITexts.SEARCH_BY_TAG)
                add_and_action = menu.addAction(
                    QIcon.fromTheme("add"), UITexts.SEARCH_ADD_AND)
                add_or_action = menu.addAction(
                    QIcon.fromTheme("add"), UITexts.SEARCH_ADD_OR)

                menu.addSeparator()

                search_on_new_session_action = menu.addAction(
                    QIcon.fromTheme("system-search"), UITexts.SEARCH_BY_TAG_ON_NEW_SESSION)

                menu.addSeparator()

                add_to_quick_tags_action = menu.addAction(
                    QIcon.fromTheme("bookmark-new"), UITexts.ADD_TAG_TO_QUICK_TAGS)
                remove_from_quick_tags_action = menu.addAction(
                    QIcon.fromTheme("bookmark-remove"), UITexts.REMOVE_TAG_FROM_QUICK_TAGS)

                menu.addSeparator()

                rename_all_action = menu.addAction(
                    QIcon.fromTheme("edit-rename"), UITexts.RENAME_TAGS_ALL)
                rename_viewed_action = menu.addAction(
                    QIcon.fromTheme("edit-rename"), UITexts.RENAME_TAGS_VIEWED)

                menu.addSeparator()
                tag_info_action = menu.addAction(
                    QIcon.fromTheme("tag-edit"), UITexts.EDIT_TAG_INFO)

                action = menu.exec(event.globalPos())
                if action == search_action:
                    self.search_requested.emit(index)
                elif action == search_on_new_session_action:
                    self.search_on_new_session_requested.emit(index)
                elif action == add_and_action:
                    self.add_and_requested.emit(index)
                elif action == add_or_action:
                    self.add_or_requested.emit(index)
                elif action == add_to_quick_tags_action:
                    self.add_to_quick_tags_requested.emit(index)
                elif action == remove_from_quick_tags_action:
                    self.remove_from_quick_tags_requested.emit(index)
                elif action == rename_all_action:
                    self.rename_all_requested.emit(index)
                elif action == rename_viewed_action:
                    self.rename_viewed_requested.emit(index)
                elif action == tag_info_action:
                    self.tag_info_requested.emit(index)
                else:
                    super().contextMenuEvent(event)


class TagRenameDialog(QDialog):
    """Dialog for renaming a tag, updating matching files and regions with progress tracking."""

    def __init__(self, tag_path: str, main_win=None, tag_edit_widget=None, parent=None, all_files: bool = True):
        super().__init__(parent)
        self.main_win = main_win
        self.tag_path = tag_path
        self.tag_edit_widget = tag_edit_widget
        self.all_files = all_files
        self.found_files = []

        self.setWindowTitle(UITexts.RENAME_TAG_TITLE)
        self.setMinimumWidth(450)

        layout = QVBoxLayout(self)

        lbl_path = QLabel(UITexts.RENAME_TAG_LABEL, self)
        self.edit_path = QLineEdit(self.tag_path, self)
        self.edit_path.setClearButtonEnabled(True)

        layout.addWidget(lbl_path)
        layout.addWidget(self.edit_path)

        self.lbl_count = QLabel(UITexts.RENAME_TAG_ITEMS_COUNT.format(0), self)
        layout.addWidget(self.lbl_count)

        self.progress_bar = QProgressBar(self)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.btn_accept = QPushButton(UITexts.ACCEPT, self)
        self.btn_cancel = QPushButton(UITexts.CANCEL, self)

        btn_layout.addWidget(self.btn_accept)
        btn_layout.addWidget(self.btn_cancel)
        layout.addLayout(btn_layout)

        self.btn_accept.clicked.connect(self.accept_rename)
        self.btn_cancel.clicked.connect(self.reject)

        self.load_matching_files()

    def load_matching_files(self):
        """Searches for all files containing the target tag."""
        words = self.tag_path.replace('/', ' ').split()
        search_terms = [f"tags='{word}'" for word in words if word not in ('-')]
        search_string = " ".join(search_terms)

        files = []
        if self.all_files:
            if BagheeraSearcher and search_string:
                try:
                    searcher = BagheeraSearcher()
                    main_opts = {}
                    other_opts = {
                        "having": None, "id": False, "konsole": False,
                        "limit": 99999999999, "offset": 0, "subquery": None,
                        "subquery_indent": "", "subquery_having": None,
                        "sort": None, "type": None, "verbose": False
                    }
                    for item in searcher.search(search_string, main_opts, other_opts):
                        p = item.get("path")
                        if p:
                            p = p.strip()
                            if p and os.path.exists(os.path.expanduser(p)) and p not in files:
                                files.append(p)
                except Exception as e:
                    logger.error(f"Error searching files with BagheeraSearcher: {e}")

        else:
            model = self.main_win.proxy_model
            if model and hasattr(model, '_name_filter_active'):
                if model._name_filter_active:
                    for path in model._name_matching_paths if hasattr(model, '_al_name_matching_pathsl_paths') else []:
                        files.append(path)

            if model and hasattr(model, '_tag_filter_active'):
                if model._tag_filter_active:
                    for path in model._tag_matching_paths if hasattr(model, '_name_matching_paths') else []:
                        files.append(path)

            if len(files) == 0:
                for path in model._all_paths if hasattr(model, '_all_paths') else []:
                    files.append(path)

        if self.tag_edit_widget and hasattr(self.tag_edit_widget, 'original_tags_per_file'):
            for path, tags in self.tag_edit_widget.original_tags_per_file.items():
                if any(t == self.tag_path or t.startswith(self.tag_path + "/") for t in tags):
                    if path not in files and os.path.exists(path):
                        files.append(path)

        self.found_files = files
        self.lbl_count.setText(UITexts.RENAME_TAG_ITEMS_COUNT.format(len(self.found_files)))
        self.progress_bar.setRange(0, max(len(self.found_files), 1))
        self.progress_bar.setValue(0)

    def get_matched_region_types(self, tag_path: str) -> set:
        """Determines which region types correspond to the given tag path based on APP_CONFIG."""
        matched = set()
        mappings = [
            ("person_tags", "Person", "Face"),
            ("pet_tags", "Pet", "Pet"),
            ("body_tags", "Body", "Body"),
            ("object_tags", "Object", "Object"),
            ("landmark_tags", "Landmark", "Landmark"),
        ]
        for config_key, default_val, region_type in mappings:
            config_val = APP_CONFIG.get(config_key, default_val)
            if not config_val or not config_val.strip():
                config_val = default_val
            prefixes = [p.strip() for p in config_val.split(',') if p.strip()]
            for prefix in prefixes:
                if tag_path == prefix or tag_path.startswith(prefix + "/"):
                    matched.add(region_type)
                    if region_type == "Face":
                        matched.add("Person")
                    break
        return matched

    def accept_rename(self):
        """Performs the tag and region renaming process across all matching files."""
        new_tag = self.edit_path.text().strip()
        old_tag = self.tag_path

        if not new_tag:
            QMessageBox.warning(self, UITexts.WARNING, "Tag path cannot be empty.")
            return

        if new_tag == old_tag:
            self.accept()
            return

        self.btn_accept.setEnabled(False)
        self.btn_cancel.setEnabled(False)
        self.edit_path.setEnabled(False)

        old_last_term = old_tag.split('/')[-1]
        new_last_term = new_tag.split('/')[-1]
        matched_region_types = self.get_matched_region_types(old_tag)

        total_files = len(self.found_files)
        self.progress_bar.setRange(0, max(total_files, 1))

        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            for idx, file_path in enumerate(self.found_files):
                self.progress_bar.setValue(idx)
                QApplication.processEvents()

                try:
                    raw_tags = XattrManager.get_attribute(file_path, XATTR_NAME)
                    if raw_tags:
                        file_tags = [t.strip() for t in raw_tags.split(',') if t.strip()]
                    else:
                        file_tags = []

                    updated_tags = []
                    tag_changed = False
                    for t in file_tags:
                        if t == old_tag:
                            updated_tags.append(new_tag)
                            tag_changed = True
                        elif t.startswith(old_tag + "/"):
                            new_child_tag = new_tag + t[len(old_tag):]
                            updated_tags.append(new_child_tag)
                            tag_changed = True
                        else:
                            updated_tags.append(t)

                    if tag_changed:
                        final_tags = sorted(list(set(updated_tags)))
                        tags_str = ",".join(final_tags) if final_tags else None
                        XattrManager.set_attribute(file_path, XATTR_NAME, tags_str)

                    if matched_region_types and old_last_term != new_last_term:
                        faces = XmpManager.load_regions(file_path)
                        if faces:
                            region_changed = False
                            for face in faces:
                                r_type = face.get('type', 'Face')
                                if r_type in matched_region_types and face.get('name') == old_last_term:
                                    face['name'] = new_last_term
                                    region_changed = True
                            if region_changed:
                                XmpManager.save_regions(file_path, faces)
                except Exception as e:
                    logger.error(f"Error updating file {file_path} during tag rename: {e}")

            self.progress_bar.setValue(total_files)
            QApplication.processEvents()
        finally:
            QApplication.restoreOverrideCursor()

        self.accept()


class TagEditWidget(QWidget):
    """A widget for editing tags associated with one or more files."""
    tags_updated = Signal(dict)

    def __init__(self, main_win=None, parent=None):
        """Initializes the tag editing widget and its UI components."""
        super().__init__(parent)
        self.main_win = main_win
        self.file_paths = []  # Paths of the files being edited
        self.initial_states = {}
        self.original_tags_per_file = {}
        self.manually_changed = set()
        self.forced_sync_tags = set()
        self.item_mapping = {}
        self.available_tags = []
        self._is_updating = False
        self.root_favs = None
        self.root_all = None
        self._load_all = True

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Search bar and add button
        search_layout = QHBoxLayout()
        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText(UITexts.TAG_SEARCH_PLACEHOLDER)
        # Get the preferred height of the QLineEdit to use it for the buttons
        line_edit_height = self.search_bar.sizeHint().height()
        self.search_bar.setClearButtonEnabled(True)
        self.btn_add_tag = QPushButton("+")
        self.btn_add_tag.setFixedSize(30, line_edit_height)
        self.btn_add_tag.setToolTip(UITexts.TAG_ADD_TOOLTIP)
        self.btn_refresh_tags = QPushButton()
        self.btn_refresh_tags.setIcon(QIcon.fromTheme("view-refresh"))
        self.btn_refresh_tags.setFixedSize(30, line_edit_height)
        self.btn_refresh_tags.setToolTip(UITexts.TAG_REFRESH_TOOLTIP)
        search_layout.addWidget(self.search_bar)
        search_layout.addWidget(self.btn_add_tag)
        search_layout.addWidget(self.btn_refresh_tags)
        layout.addLayout(search_layout)

        # Tag tree view setup
        self.source_model = QStandardItemModel()
        self.proxy_model = QSortFilterProxyModel()
        self.proxy_model.setSourceModel(self.source_model)
        self.proxy_model.setRecursiveFilteringEnabled(True)

        self.tree_view = TagTreeView()
        self.tree_view.setModel(self.proxy_model)
        self.tree_view.setHeaderHidden(True)
        self.tree_view.setExpandsOnDoubleClick(False)
        self.tree_view.setEditTriggers(QTreeView.NoEditTriggers)
        layout.addWidget(self.tree_view)

        # Apply button
        self.btn_apply = QPushButton(UITexts.TAG_APPLY_CHANGES)
        layout.addWidget(self.btn_apply)

        self.load_available_tags()
        self._load_all = True

        # Connect signals to slots
        self.btn_apply.clicked.connect(self.save_changes)
        self.btn_add_tag.clicked.connect(self.create_new_tag)
        self.btn_refresh_tags.clicked.connect(self.refresh_available_tags)
        self.search_bar.textChanged.connect(self.handle_search)
        self.source_model.itemChanged.connect(self.sync_tags)
        self.tree_view.search_requested.connect(self.on_search_requested)
        self.tree_view.search_on_new_session_requested.connect(self.on_search_on_new_session_requested)
        self.tree_view.add_and_requested.connect(self.on_add_and_requested)
        self.tree_view.add_or_requested.connect(self.on_add_or_requested)
        self.tree_view.rename_all_requested.connect(self.on_rename_all_requested)
        self.tree_view.rename_viewed_requested.connect(self.on_rename_viewed_requested)
        self.tree_view.add_to_quick_tags_requested.connect(self.on_add_to_quick_tags_requested)
        self.tree_view.remove_from_quick_tags_requested.connect(self.on_remove_from_quick_tags_requested)
        self.tree_view.tag_info_requested.connect(self.on_tag_info_requested)

    def set_files_data(self, files_data):
        """Sets the files whose tags are to be edited.

        Args:
            files_data (dict): A dictionary mapping file paths to a list of
                               their current tags.
        """
        self.file_paths = list(files_data.keys())
        # Handle None tags safely to avoid crashes during selection changes
        self.original_tags_per_file = {
            path: set(tags) if tags is not None else set()
            for path, tags in files_data.items()
        }
        self.refresh_ui()

    def refresh_available_tags(self):
        """Manual refresh of available tags from Baloo."""
        self.search_bar.clear()
        self.initial_states = {}
        self.manually_changed = set()
        self.forced_sync_tags = set()
        self.load_available_tags()
        self._load_all = True
        self.init_data()

    def load_available_tags(self):
        """Loads all known tags from the Baloo index database."""
        db_path = os.path.expanduser("~/.local/share/baloo/index")
        if not os.path.exists(db_path) or not os.access(db_path, os.R_OK):
            self.available_tags = []
            self._load_all = True
            return
        tags = []
        success = False
        try:
            # Auto-detect if it's a directory or a file to set subdir correctly
            is_dir = os.path.isdir(db_path)
            # Connect to the LMDB environment for Baloo
            with lmdb.open(db_path, subdir=is_dir, readonly=True,
                           lock=False, max_dbs=20) as env:
                postingdb = env.open_db(b'postingdb')
                with env.begin() as txn:
                    cursor = txn.cursor(postingdb)
                    prefix = b'TAG-'
                    # Iterate over keys starting with the tag prefix
                    if cursor.set_range(prefix):
                        for key, _ in cursor:
                            if not key.startswith(prefix):
                                break
                            tags.append(key[4:].decode('utf-8'))
                success = True
        except Exception as e:
            logger.debug(f"Failed to load Baloo tags from {db_path}: {e}")

        if success:
            # Use set comparison to reliably detect any content change in tags
            if set(tags) != set(self.available_tags):
                self._load_all = True
            self.available_tags = tags

    def init_data(self):
        """Initializes or updates the tag tree model based on current files."""
        self.tree_view.setUpdatesEnabled(False)
        self._is_updating = True
        try:
            if self._load_all:
                # First time loading: build the full tree structure
                self.source_model.clear()
                self.item_mapping = {}
                self.root_favs = QStandardItem(UITexts.TAG_USED_TAGS)
                self.root_all = QStandardItem(UITexts.TAG_ALL_TAGS)

                self.root_favs.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                self.root_all.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)

                # self.source_model.insertRow(self.root_favs, 0)
                self.source_model.appendRow(self.root_favs)
                self.source_model.appendRow(self.root_all)

                tag_counts = {}
                for path in self.file_paths:
                    tags = self.original_tags_per_file.get(path, set())
                    for t in tags:
                        tag_counts[t] = tag_counts.get(t, 0) + 1
                # Combine tags from files and all available tags from Baloo
                master = sorted(
                    list(set(self.available_tags) | set(tag_counts.keys())))
                total = len(self.file_paths) if self.file_paths else 1

                for t_path in master:
                    count = tag_counts.get(t_path, 0)
                    is_checked = count > 0
                    # Italicize if the tag is applied to some but not all files
                    is_italic = (0 < count < total and len(self.file_paths) > 1)
                    self.initial_states[t_path] = is_checked

                    self.get_or_create_node(t_path, self.root_all, is_checked,
                                            is_italic)
                    if is_checked:
                        self.get_or_create_node(t_path, self.root_favs, True,
                                                is_italic)

                # Update internal list for external consumers (e.g. FaceNameInputWidget)
                self.available_tags = master
                self._load_all = False

            else:
                # Recovery: if roots are missing or ALL TAGS was never populated,
                # force a full load.
                if not self.root_all or (self.root_all.rowCount() == 0 and self.available_tags):
                    self._load_all = True
                    self.init_data()
                    return

                # Subsequent loads: update existing tree
                tag_counts = {}
                for path in self.file_paths:
                    tags = self.original_tags_per_file.get(path, set())
                    for t in tags:
                        tag_counts[t] = tag_counts.get(t, 0) + 1
                total = len(self.file_paths) if self.file_paths else 1

                if self.root_favs.hasChildren():
                    self.root_favs.removeRows(0, self.root_favs.rowCount())
                    # Clear references to deleted items in the 'Used Tags' section
                    for key in self.item_mapping:
                        self.item_mapping[key][1] = None

                # Optimization: Reset known nodes via map instead of recursive traversal
                for t_path, nodes in self.item_mapping.items():
                    self.initial_states[t_path] = False
                    node_all = nodes[0]
                    if node_all:
                        if node_all.checkState() != Qt.Unchecked:
                            node_all.setCheckState(Qt.Unchecked)
                        font = node_all.font()
                        if font.italic():
                            font.setItalic(False)
                            node_all.setFont(font)
                        if node_all.foreground().color().name() != "#ffffff":
                            node_all.setForeground(QColor("#ffffff"))

                # Iterate only active tags to check/italicize.
                # Also ensure discovered tags are in available_tags for autocomplete.
                new_discovery = False
                for t_path, count in tag_counts.items():
                    if count > 0:
                        is_italic = (0 < count < total and len(self.file_paths) > 1)
                        self.initial_states[t_path] = True

                        self.get_or_create_node(t_path, self.root_favs, True, is_italic)
                        self.get_or_create_node(t_path, self.root_all, True, is_italic)
                        if t_path not in self.available_tags:
                            self.available_tags.append(t_path)
                            new_discovery = True

                if new_discovery:
                    self.available_tags.sort()

            self.reset_expansion()
        finally:
            self._is_updating = False
            self.tree_view.setUpdatesEnabled(True)

    def get_or_create_node(self, full_path, root, checked, italic):
        """Finds or creates a hierarchical node in the tree for a given tag path.

        Args:
            full_path (str): The full hierarchical tag (e.g., "Photos/Family").
            root (QStandardItem): The root item to build under (e.g., "All Tags").
            checked (bool): The initial check state of the final node.
            italic (bool): Whether the node font should be italic.
        """
        parts, curr = full_path.split('/'), root
        for i, part in enumerate(parts):
            c_path = "/".join(parts[:i+1])
            found = None
            # Find if child already exists
            for row in range(curr.rowCount()):
                if curr.child(row, 0).text() == part:
                    found = curr.child(row, 0)
                    break
            if not found:
                # Create new node if it doesn't exist
                node = QStandardItem(part)
                node.setCheckable(True)  # All nodes are checkable, but only the final node's state is relevant.
                if c_path == full_path:
                    # This is the final node in the path, make it checkable
                    node.setCheckState(Qt.Checked if checked else Qt.Unchecked)
                    self._style_node(node, full_path, checked, italic)
                    if full_path not in self.item_mapping:
                        self.item_mapping[full_path] = [None, None]
                    # Store reference to the node under 'all' or 'used' root
                    self.item_mapping[full_path][0 if root == self.root_all else 1] = \
                        node
                curr.appendRow(node)
                curr = node
            else:
                # Node already exists, update it
                curr = found
                if c_path == full_path:
                    curr.setCheckState(Qt.Checked if checked else Qt.Unchecked)
                    self._style_node(curr, full_path, checked, italic)

    def _style_node(self, node, path, current_checked, italic):
        """Applies visual styling (font, color) to a tag node."""
        font = node.font()
        # Use italic for partially applied tags, unless forced
        font.setItalic(italic if path not in self.forced_sync_tags else False)
        node.setFont(font)
        # Highlight manually changed tags
        color = "#569cd6" if path in self.manually_changed else "#ffffff"
        node.setForeground(QColor(color))

    def reconstruct_path(self, item):
        """Builds the full hierarchical tag path from a model item."""
        p, c = [], item
        while c and c not in [self.root_all, self.root_favs]:
            p.insert(0, c.text())
            c = c.parent()
        return "/".join(p) if p else None

    def sync_tags(self, item):
        """Synchronizes the state of a tag between the 'Used' and 'All' trees.

        Triggered when a tag's check state changes. It also tracks manual
        changes to highlight them and prepare for saving.
        """
        if self._is_updating:
            return
        if not item:
            return
        path = self.reconstruct_path(item)
        if not path or path not in self.item_mapping:
            return

        new_state = (item.checkState() == Qt.Checked)
        if new_state:  # and self.item_mapping[path][1] is None:
            # If a tag is checked, ensure it appears in the "Used Tags" list
            self.get_or_create_node(path, self.root_favs, True, item.font().italic())
            self.reset_expansion()

        if QApplication.keyboardModifiers() == Qt.ControlModifier:
            # Ctrl+Click forces a tag to be considered "changed"
            self.forced_sync_tags.add(path)

        # Track if the state differs from the initial state
        if (new_state != self.initial_states.get(path, False)
                or path in self.forced_sync_tags):
            self.manually_changed.add(path)
        else:
            self.manually_changed.discard(path)

        # Update the corresponding node in the other tree to match
        self._is_updating = True
        try:
            for node in self.item_mapping[path]:
                if node:
                    try:
                        node.setCheckState(item.checkState())
                        self._style_node(node, path, new_state, node.font().italic())
                    except RuntimeError:
                        pass
        finally:
            self._is_updating = False

    def _get_tag_search_string(self, proxy_index):
        """Generates the search string for the tag at the given index."""
        source_index = self.proxy_model.mapToSource(proxy_index)
        item = self.source_model.itemFromIndex(source_index)
        if not item:
            return ""
        full_path = self.reconstruct_path(item)
        if not full_path:
            return ""
        words = full_path.replace('/', ' ').split()
        search_terms = [f"tags='{word}'" for word in words if word not in ('-')]
        return " ".join(search_terms)

    def _get_current_query_text(self):
        """Extracts the effective query text from the main window search input."""
        if not self.main_win:
            return ""
        text = self.main_win.search_input.currentText().strip()

        if text.startswith("search:/"):
            return text[8:]

        if text.startswith("file:/") or text.startswith("/") or os.path.exists(text):
            return ""
        return text

    @Slot(object)
    def on_search_requested(self, proxy_index):
        """Handles the request to search for a tag from the context menu."""
        search_string = self._get_tag_search_string(proxy_index)

        if search_string:
            self.main_win.process_term(f"search:/{search_string}")

    @Slot(object)
    def on_search_on_new_session_requested(self, proxy_index):
        """Handles the request to search for a tag in a new session."""
        search_string = self._get_tag_search_string(proxy_index)

        if search_string:
            subprocess.Popen([PROG_FILE_NAME, f"search:/{search_string}"])

    @Slot(object)
    def on_add_and_requested(self, proxy_index):
        """Handles request to add a tag with AND to the current search."""
        if not self.main_win:
            return
        new_term = self._get_tag_search_string(proxy_index)
        if not new_term:
            return

        current_query = self._get_current_query_text()

        if current_query:
            final_query = f"({current_query}) AND ({new_term})"
        else:
            final_query = new_term

        self.main_win.process_term(f"search:/{final_query}")

    @Slot(object)
    def on_add_or_requested(self, proxy_index):
        """Handles request to add a tag with OR to the current search."""
        if not self.main_win:
            return
        new_term = self._get_tag_search_string(proxy_index)
        if not new_term:
            return

        current_query = self._get_current_query_text()

        if current_query:
            final_query = f"({current_query}) OR ({new_term})"
        else:
            final_query = new_term

        self.main_win.process_term(f"search:/{final_query}")

    def on_rename_requested(self, proxy_index, all_files: bool = True):
        """Handles request to rename a tag from the context menu."""
        source_index = self.proxy_model.mapToSource(proxy_index)
        item = self.source_model.itemFromIndex(source_index)
        if not item:
            return
        full_path = self.reconstruct_path(item)
        if not full_path:
            return

        dialog = TagRenameDialog(full_path, self.main_win, tag_edit_widget=self, parent=self, all_files=all_files)
        if dialog.exec() == QDialog.Accepted:
            new_tag = dialog.edit_path.text().strip()
            old_tag = full_path

            # 1. Update internal available_tags list to replace old tag & child tags
            if new_tag and new_tag != old_tag:
                updated_available = []
                for t in self.available_tags:
                    if t == old_tag:
                        updated_available.append(new_tag)
                    elif t.startswith(old_tag + "/"):
                        updated_available.append(new_tag + t[len(old_tag):])
                    else:
                        updated_available.append(t)
                self.available_tags = sorted(list(set(updated_available)))

            # 2. Refresh tags from xattrs for all currently loaded files
            for path in list(self.original_tags_per_file.keys()):
                raw_tags = XattrManager.get_attribute(path, XATTR_NAME)
                if raw_tags:
                    self.original_tags_per_file[path] = set(
                        t.strip() for t in raw_tags.split(',') if t.strip()
                    )
                else:
                    self.original_tags_per_file[path] = set()

            # 3. Refresh available tags and rebuild TagTreeView
            self.refresh_available_tags()

            # 4. Notify main window components if available
            if self.main_win:
                if hasattr(self.main_win, 'on_tags_edited'):
                    try:
                        self.main_win.on_tags_edited()
                    except Exception:
                        pass
                if hasattr(self.main_win, 'update_tag_list'):
                    try:
                        self.main_win.update_tag_list()
                    except Exception:
                        pass
                if hasattr(self.main_win, 'update_tag_edit_widget'):
                    try:
                        self.main_win.update_tag_edit_widget()
                    except Exception:
                        pass
                if hasattr(self.main_win, 'refresh_current_view'):
                    try:
                        self.main_win.refresh_current_view()
                    except Exception:
                        pass

    @Slot(object)
    def on_rename_all_requested(self, proxy_index):
        self.on_rename_requested(proxy_index, all_files=True)

    @Slot(object)
    def on_rename_viewed_requested(self, proxy_index):
        self.on_rename_requested(proxy_index, all_files=False)

    @Slot(object)
    def on_tag_info_requested(self, proxy_index):
        """Handles request to edit tag information."""
        tag = self._get_tag_path_from_proxy_index(proxy_index)
        if not tag or not self.main_win:
            return

        os.makedirs(DIRECTORY_TAG_INFO, exist_ok=True)
        filepath = os.path.join(DIRECTORY_TAG_INFO, tag.replace('/', '_') + ".md")
        template_text = ""
        template_file = os.path.join(APP_DATA_DIR, TAG_INFO_TEMPLATE)

        dialog = QDialog(self)
        dialog.setWindowTitle(f"Tag Information - {tag}")
        dialog.resize(800, 600)
        dialog.setAttribute(Qt.WA_DeleteOnClose)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(0, 0, 0, 0)
        self.markdown_editor = MarkdownEditorWidget(
            filepath=filepath,
            template_text=template_text,
            template_file=template_file,
            parent=dialog,
            auto_load=True,
            capture_keys=True,
        )
        layout.addWidget(self.markdown_editor)
        dialog.show()

    def _get_tag_path_from_proxy_index(self, proxy_index):
        """Reconstructs the full tag path from a proxy model index."""
        source_index = self.proxy_model.mapToSource(proxy_index)
        item = self.source_model.itemFromIndex(source_index)
        if not item:
            return ""
        return self.reconstruct_path(item)

    @Slot(object)
    def on_add_to_quick_tags_requested(self, proxy_index):
        """Handles request to add a tag to the quick tags (mru_tags) list."""
        tag = self._get_tag_path_from_proxy_index(proxy_index)
        if not tag or not self.main_win:
            return
        self.main_win.add_to_mru_tags(tag)
        if hasattr(self.main_win, 'status_lbl'):
            self.main_win.status_lbl.setText(UITexts.QUICK_TAG_ADDED.format(tag))

    @Slot(object)
    def on_remove_from_quick_tags_requested(self, proxy_index):
        """Handles request to remove a tag from the quick tags (mru_tags) list."""
        tag = self._get_tag_path_from_proxy_index(proxy_index)
        if not tag or not self.main_win:
            return
        if not hasattr(self.main_win, 'mru_tags'):
            return
        if tag in self.main_win.mru_tags:
            self.main_win.mru_tags.remove(tag)
            self.main_win.save_config()
            if hasattr(self.main_win, 'status_lbl'):
                self.main_win.status_lbl.setText(UITexts.QUICK_TAG_REMOVED.format(tag))
        else:
            if hasattr(self.main_win, 'status_lbl'):
                self.main_win.status_lbl.setText(UITexts.QUICK_TAG_NOT_FOUND.format(tag))

    def save_changes(self):
        """Applies the tracked tag changes to the selected files' xattrs."""
        QApplication.setOverrideCursor(Qt.WaitCursor)
        paths_to_index = []
        all_newly_added_tags = set()
        updated_files_tags = {}
        try:
            for path in self.file_paths:
                try:
                    file_tags = self.original_tags_per_file.get(path, set()).copy()

                    original_file_tags = set(file_tags)

                    for t in self.manually_changed:
                        nodes = self.item_mapping.get(t)
                        if not nodes:
                            continue
                        node = nodes[0] or nodes[1]
                        if node.checkState() == Qt.Checked:
                            file_tags.add(t)
                        else:
                            file_tags.discard(t)

                    # Filter out any empty or whitespace-only tags before saving.
                    # The use of a set already handles duplicates.
                    final_tags = {tag.strip() for tag in file_tags if tag.strip()}

                    newly_added_tags = final_tags - original_file_tags
                    all_newly_added_tags.update(newly_added_tags)

                    tags_str = ",".join(sorted(list(final_tags))) if final_tags \
                        else None
                    XattrManager.set_attribute(path, XATTR_NAME, tags_str)

                    self.original_tags_per_file[path] = final_tags
                    updated_files_tags[path] = sorted(list(final_tags))
                    paths_to_index.append(path)
                except Exception:
                    continue

            if self.main_win:
                for tag in sorted(list(all_newly_added_tags)):
                    self.main_win.add_to_mru_tags(tag)

            # Refresh status bar on any open viewer showing one of the modified files
            if self.main_win:
                for viewer in list(self.main_win.viewers):
                    try:
                        if viewer.isVisible() and \
                           viewer.controller.get_current_path() in paths_to_index:
                            viewer.update_status_bar()
                    except RuntimeError:
                        continue

            self.load_available_tags()
            self._load_all = False
            self.refresh_ui()
            self.tags_updated.emit(updated_files_tags)
        except Exception as e:
            QMessageBox.critical(self, UITexts.ERROR, str(e))
        finally:
            QApplication.restoreOverrideCursor()

    def create_new_tag(self):
        """Opens a dialog to create a new tag and adds it to the trees."""
        new_tag, ok = QInputDialog.getText(self, UITexts.TAG_NEW_TAG_TITLE,
                                           UITexts.TAG_NEW_TAG_TEXT)
        if ok and new_tag.strip():
            tag_path = new_tag.strip()
            # Mark it as a forced, manual change to ensure it gets saved
            self.forced_sync_tags.add(tag_path)
            self.manually_changed.add(tag_path)
            # Add the new tag to both trees, checked by default
            self.get_or_create_node(tag_path, self.root_all, True, False)
            self.get_or_create_node(tag_path, self.root_favs, True, False)
            self.reset_expansion()

    def handle_search(self, text):
        """Filters the tag tree based on the search bar text."""
        self.proxy_model.setFilterCaseSensitivity(Qt.CaseInsensitive)
        self.proxy_model.setFilterFixedString(text)
        if text:
            self.tree_view.expandAll()
        else:
            self.reset_expansion(True)

    def reset_expansion(self, handling_search=False):
        """Resets the tree expansion to a default state."""
        if handling_search:
            self.tree_view.collapseAll()

        # Safety check to ensure model is populated
        if self.source_model.rowCount() < 2:
            return

        # Map source roots to proxy indices to expand correctly even when
        # the "Used Tags" root is filtered out or hidden.
        fav_idx = self.proxy_model.mapFromSource(self.source_model.index(0, 0))
        if fav_idx.isValid():
            self._expand_recursive(fav_idx)

        all_idx = self.proxy_model.mapFromSource(self.source_model.index(1, 0))
        if all_idx.isValid():
            # Expand only the top level of the "All Tags" section
            self.tree_view.expand(all_idx)

    def _expand_recursive(self, proxy_idx):
        """Recursively expands an item and all its children."""
        self.tree_view.expand(proxy_idx)
        for i in range(self.proxy_model.rowCount(proxy_idx)):
            child = self.proxy_model.index(i, 0, proxy_idx)
            if child.isValid():
                self._expand_recursive(child)

    def refresh_ui(self):
        """Resets the widget's state and re-initializes the data."""
        self.initial_states = {}
        self.manually_changed = set()
        self.forced_sync_tags = set()
        self.init_data()


class LayoutsWidget(QWidget):
    """A widget for managing saved window and viewer layouts."""
    def __init__(self, main_win):
        """Initializes the layouts widget and its UI.

        Args:
            main_win (MainWindow): Reference to the main application window.
        """
        super().__init__()
        self.main_win = main_win
        layout = QVBoxLayout(self)

        # Table to display saved layouts
        self.table = QTableWidget()
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(UITexts.LAYOUTS_TABLE_HEADER)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setSortingEnabled(True)
        self.table.doubleClicked.connect(self.load_selected)
        layout.addWidget(self.table)

        toolbar = QToolBar()
        layout.addWidget(toolbar)

        load_action = QAction(QIcon.fromTheme("document-open"), UITexts.LOAD, self)
        load_action.triggered.connect(self.load_selected)
        toolbar.addAction(load_action)

        create_action = QAction(QIcon.fromTheme("document-new"), UITexts.CREATE, self)
        create_action.triggered.connect(self.create_layout)
        toolbar.addAction(create_action)

        save_action = QAction(QIcon.fromTheme("document-save"), UITexts.SAVE, self)
        save_action.triggered.connect(self.save_selected_layout)
        toolbar.addAction(save_action)

        rename_action = QAction(QIcon.fromTheme("edit-rename"), UITexts.RENAME_LAYOUT_TOOLTIP, self)
        rename_action.triggered.connect(self.rename_layout)
        toolbar.addAction(rename_action)

        copy_action = QAction(QIcon.fromTheme("edit-copy"), UITexts.COPY, self)
        copy_action.triggered.connect(self.copy_layout)
        toolbar.addAction(copy_action)

        delete_action = QAction(QIcon.fromTheme("edit-delete"), UITexts.DELETE, self)
        delete_action.triggered.connect(self.delete_layout)
        toolbar.addAction(delete_action)

        self.refresh_list()

    def resizeEvent(self, event):
        """Adjusts column widths on resize."""
        width = self.table.viewport().width()
        self.table.setColumnWidth(0, int(width * 0.80))
        super().resizeEvent(event)

    def refresh_list(self):
        """Reloads the list of saved layouts from the layouts directory."""
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        if not os.path.exists(LAYOUTS_DIR):
            return

        # Find all .layout files
        files = glob.glob(os.path.join(LAYOUTS_DIR, "*.layout"))
        files.sort(key=os.path.getmtime, reverse=True)

        self.table.setRowCount(len(files))
        for i, f_path in enumerate(files):
            name = os.path.basename(f_path).replace(".layout", "")
            mtime = os.path.getmtime(f_path)
            dt = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")

            item_name = QTableWidgetItem(name)
            item_name.setData(Qt.UserRole, f_path)
            item_date = QTableWidgetItem(dt)

            self.table.setItem(i, 0, item_name)
            self.table.setItem(i, 1, item_date)
        self.table.setSortingEnabled(True)

    def get_selected_path(self):
        """Gets the file path of the currently selected layout in the table.

        Returns:
            str or None: The full path to the selected .layout file, or None.
        """
        row = self.table.currentRow()
        if row >= 0:
            return self.table.item(row, 0).data(Qt.UserRole)
        return None

    def load_selected(self):
        """Loads the currently selected layout."""
        path = self.get_selected_path()
        if path:
            self.main_win.restore_layout(path)

    def create_layout(self):
        """Saves the current session as a new layout."""
        self.main_win.save_layout()
        self.refresh_list()

    def save_selected_layout(self):
        """Overwrites the selected layout with the current session state."""
        path = self.get_selected_path()
        if path:
            self.main_win.save_layout(target_path=path)
        else:
            # If nothing is selected, treat it as a "create new" action
            self.create_layout()

    def delete_layout(self):
        """Deletes the selected layout file after confirmation."""
        path = self.get_selected_path()
        if path:
            if QMessageBox.question(self,
                                    UITexts.CONFIRM_DELETE_LAYOUT_TITLE,
                                    UITexts.CONFIRM_DELETE_LAYOUT_TEXT.format(
                                        os.path.basename(path)), QMessageBox.Yes
                                    | QMessageBox.No) == QMessageBox.Yes:
                os.remove(path)
                self.refresh_list()

    def rename_layout(self):
        """Renames the selected layout file."""
        path = self.get_selected_path()
        if not path:
            return
        old_name = os.path.basename(path).replace(".layout", "")
        new_name, ok = QInputDialog.getText(self,
                                            UITexts.RENAME_LAYOUT_TITLE,
                                            UITexts.RENAME_LAYOUT_TOOLTIP,
                                            text=old_name)
        if ok and new_name:
            new_path = os.path.join(os.path.dirname(path), new_name + ".layout")
            if not os.path.exists(new_path):
                os.rename(path, new_path)
                self.refresh_list()
            else:
                QMessageBox.warning(self, UITexts.ERROR, UITexts.LAYOUT_ALREADY_EXISTS)

    def copy_layout(self):
        """Creates a copy of the selected layout with a new name."""
        path = self.get_selected_path()
        if not path:
            return
        old_name = os.path.basename(path).replace(".layout", "")
        new_name, ok = QInputDialog.getText(self,
                                            UITexts.COPY_LAYOUT_TITLE,
                                            UITexts.COPY_LAYOUT_TEXT,
                                            text=old_name + "_copy")
        if ok and new_name:
            new_path = os.path.join(os.path.dirname(path), new_name + ".layout")
            if not os.path.exists(new_path):
                shutil.copy(path, new_path)
                self.refresh_list()
            else:
                QMessageBox.warning(self, UITexts.ERROR, UITexts.LAYOUT_ALREADY_EXISTS)


class HistoryWidget(QWidget):
    """A widget to display and manage the application's browsing history."""
    def __init__(self, main_win):
        """Initializes the history widget and its UI.

        Args:
            main_win (MainWindow): Reference to the main application window.
        """
        super().__init__()
        self.main_win = main_win
        layout = QVBoxLayout(self)

        # Table to display history entries
        self.table = QTableWidget()
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(UITexts.HISTORY_TABLE_HEADER)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setSortingEnabled(True)
        self.table.doubleClicked.connect(self.open_selected)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.show_context_menu)
        layout.addWidget(self.table)

        toolbar = QToolBar()
        layout.addWidget(toolbar)

        clear_action = QAction(QIcon.fromTheme("user-trash"),
                               UITexts.HISTORY_BTN_CLEAR_ALL_TOOLTIP, self)
        clear_action.triggered.connect(self.clear_all)
        toolbar.addAction(clear_action)

        delete_action = QAction(QIcon.fromTheme("edit-delete"),
                                UITexts.HISTORY_BTN_DELETE_SELECTED_TOOLTIP, self)
        delete_action.triggered.connect(self.delete_selected)
        toolbar.addAction(delete_action)

        delete_older_action = QAction(QIcon.fromTheme("edit-clear"),
                                      UITexts.HISTORY_BTN_DELETE_OLDER_TOOLTIP, self)
        delete_older_action.triggered.connect(self.delete_older)
        toolbar.addAction(delete_older_action)

        self.refresh_list()

    def resizeEvent(self, event):
        """Adjusts column widths on resize."""
        width = self.table.viewport().width()
        self.table.setColumnWidth(0, int(width * 0.80))
        super().resizeEvent(event)

    def refresh_list(self):
        """Reloads the history from the main window's data."""
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)

        # Filter invalid items to avoid crashes and empty rows
        history = [e for e in self.main_win.full_history
                   if isinstance(e, dict) and e.get('path')]

        self.table.setRowCount(len(history))
        for i, entry in enumerate(history):
            raw_path = entry.get('path', '')
            text = raw_path.replace("search:/", "").replace("file:/", "")
            icon_name = "system-search"

            if raw_path.startswith("file:/"):
                path = raw_path[6:]
                if os.path.isdir(os.path.expanduser(path)):
                    icon_name = "folder"
                else:
                    icon_name = "image-x-generic"
            elif raw_path.startswith("layout:/"):
                icon_name = "view-grid"
                text = text.replace("layout:/", "")
            elif raw_path.startswith("search:/"):
                icon_name = "system-search"

            item_name = QTableWidgetItem(text)
            item_name.setIcon(QIcon.fromTheme(icon_name))
            item_name.setData(Qt.UserRole, raw_path)
            item_date = QTableWidgetItem(entry.get('date', ''))
            self.table.setItem(i, 0, item_name)
            self.table.setItem(i, 1, item_date)
        self.table.setSortingEnabled(True)

    def open_selected(self):
        """Opens the path/search from the selected history item."""
        row = self.table.currentRow()
        if row >= 0:
            # Use UserRole if available (contains full raw path), else fallback to text
            path = self.table.item(row, 0).data(Qt.UserRole)
            if not path:
                path = self.table.item(row, 0).text()
            self.main_win.process_term(path)

    def show_context_menu(self, pos):
        """Shows a context menu for the history table."""
        item = self.table.itemAt(pos)
        if not item:
            return

        menu = QMenu(self)
        delete_action = menu.addAction(QIcon.fromTheme("edit-delete"),
                                       UITexts.DELETE)
        action = menu.exec(self.table.mapToGlobal(pos))

        if action == delete_action:
            self.table.setCurrentItem(item)
            self.delete_selected()

    def clear_all(self):
        """Clears the entire history after confirmation."""
        if QMessageBox.question(self,
                                UITexts.HISTORY_CLEAR_ALL_TITLE,
                                UITexts.HISTORY_CLEAR_ALL_TEXT, QMessageBox.Yes
                                | QMessageBox.No) == QMessageBox.Yes:
            self.main_win.full_history = []
            self.main_win.save_full_history()
            self.refresh_list()

    def delete_selected(self):
        """Deletes the currently selected entry from the history."""
        row = self.table.currentRow()
        if row >= 0:
            item = self.table.item(row, 0)
            path = item.data(Qt.UserRole)
            if not path:
                path = item.text()

            # Safely filter history handling potentially corrupted items
            self.main_win.full_history = [
                x for x in self.main_win.full_history
                if isinstance(x, dict) and x.get('path') != path]
            self.main_win.save_full_history()
            self.refresh_list()

    def delete_older(self):
        """Deletes the selected history entry and all entries older than it."""
        row = self.table.currentRow()
        if row >= 0:
            # The visual row might not match the list index if sorted
            item = self.table.item(row, 0)
            path = item.data(Qt.UserRole)
            if not path:
                path = item.text()
            idx = -1
            # Find the actual index in the unsorted full_history list
            for i, entry in enumerate(self.main_win.full_history):
                if isinstance(entry, dict) and entry.get('path') == path:
                    idx = i
                    break

            if idx != -1:
                # Delete from this index to the end (older entries)
                del self.main_win.full_history[idx:]
                self.main_win.save_full_history()
                self.refresh_list()


class FavoritesWidget(QWidget):
    """A widget for managing favorite search queries."""
    favorites_changed = Signal()

    def __init__(self, main_win):
        super().__init__()
        self.main_win = main_win
        layout = QVBoxLayout(self)

        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText(UITexts.FAVORITES_SEARCH_PLACEHOLDER)
        self.search_bar.setClearButtonEnabled(True)
        self.search_bar.textChanged.connect(self.filter_favorites)
        layout.addWidget(self.search_bar)

        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(UITexts.FAVORITES_TABLE_HEADER)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.doubleClicked.connect(self.load_selected)
        layout.addWidget(self.table)

        toolbar = QToolBar()
        layout.addWidget(toolbar)

        load_action = QAction(QIcon.fromTheme("system-run"), UITexts.LOAD, self)
        load_action.triggered.connect(self.load_selected)
        toolbar.addAction(load_action)

        add_action = QAction(QIcon.fromTheme("list-add"), UITexts.CREATE, self)
        add_action.setToolTip(UITexts.ADD_FAVORITE_TOOLTIP)
        add_action.triggered.connect(self.add_favorite)
        toolbar.addAction(add_action)

        overwrite_action = QAction(QIcon.fromTheme("document-save"), UITexts.OVERWRITE, self)
        overwrite_action.setToolTip(UITexts.OVERWRITE_FAVORITE_TOOLTIP)
        overwrite_action.triggered.connect(self.overwrite_favorite)
        toolbar.addAction(overwrite_action)

        edit_action = QAction(QIcon.fromTheme("edit-rename"), UITexts.RENAME, self)
        edit_action.setToolTip(UITexts.EDIT_FAVORITE_TOOLTIP)
        edit_action.triggered.connect(self.edit_comment)
        toolbar.addAction(edit_action)

        shortcut_action = QAction(
            QIcon.fromTheme("preferences-desktop-keyboard-shortcuts"),
            UITexts.SHORTCUTS_KEY, self)
        shortcut_action.triggered.connect(self.edit_shortcut)
        toolbar.addAction(shortcut_action)

        delete_action = QAction(QIcon.fromTheme("edit-delete"), UITexts.DELETE, self)
        delete_action.triggered.connect(self.delete_favorite)
        toolbar.addAction(delete_action)

        toolbar.addSeparator()

        up_action = QAction(QIcon.fromTheme("go-up"), UITexts.MOVE_UP, self)
        up_action.triggered.connect(self.move_up)
        toolbar.addAction(up_action)

        down_action = QAction(QIcon.fromTheme("go-down"), UITexts.MOVE_DOWN, self)
        down_action.triggered.connect(self.move_down)
        toolbar.addAction(down_action)

        self.refresh_list()

    def resizeEvent(self, event):
        width = self.table.viewport().width()
        self.table.setColumnWidth(0, int(width * 0.60))
        self.table.setColumnWidth(2, int(width * 0.15))
        super().resizeEvent(event)

    def refresh_list(self):
        self.table.setRowCount(0)
        if not os.path.exists(FAVORITES_PATH):
            return

        try:
            with open(FAVORITES_PATH, 'r', encoding='utf-8') as f:
                favorites = json.load(f)
        except (json.JSONDecodeError, OSError):
            favorites = []

        self.table.setRowCount(len(favorites))
        for i, fav in enumerate(favorites):
            query = fav.get('query', '')
            comment = fav.get('comment', '')
            shortcut = fav.get('shortcut', '')
            self.table.setItem(i, 0, QTableWidgetItem(comment))
            self.table.setItem(i, 1, QTableWidgetItem(query))
            self.table.setItem(i, 2, QTableWidgetItem(shortcut))

    def filter_favorites(self, text):
        search_text = text.lower()
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item:
                self.table.setRowHidden(row, search_text not in item.text().lower())

    def save_favorites(self):
        favorites = []
        for i in range(self.table.rowCount()):
            item_comment = self.table.item(i, 0)
            item_query = self.table.item(i, 1)
            item_shortcut = self.table.item(i, 2)
            comment = item_comment.text() if item_comment else ""
            query = item_query.text() if item_query else ""
            shortcut = item_shortcut.text() if item_shortcut else ""
            favorites.append({'query': query, 'comment': comment, 'shortcut': shortcut})

        try:
            with open(FAVORITES_PATH, 'w', encoding='utf-8') as f:
                json.dump(favorites, f, indent=4)
            self.favorites_changed.emit()
        except OSError:
            pass

    def load_selected(self):
        row = self.table.currentRow()
        if row >= 0:
            query = self.table.item(row, 1).text()
            self.main_win.process_term(query)

    def add_favorite(self):
        query = self.main_win.search_input.currentText().strip()
        if not query:
            return

        # Ask for a comment before adding the favorite
        new_comment, ok = QInputDialog.getText(
            self, UITexts.EDIT_COMMENT_TITLE,
            UITexts.EDIT_COMMENT_TEXT.format(query),
            QLineEdit.Normal, "")

        if not ok:
            return

        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, QTableWidgetItem(new_comment))
        self.table.setItem(row, 1, QTableWidgetItem(query))
        self.table.setItem(row, 2, QTableWidgetItem(""))
        self.table.setCurrentCell(row, 0)
        self.save_favorites()

    def overwrite_favorite(self):
        row = self.table.currentRow()
        if row < 0:
            return
        query = self.main_win.search_input.currentText().strip()
        if not query:
            return

        # Ask for a comment before overwriting the favorite
        new_comment, ok = QInputDialog.getText(
            self, UITexts.EDIT_COMMENT_TITLE,
            UITexts.EDIT_COMMENT_TEXT.format(query),
            QLineEdit.Normal, self.table.item(row, 0).text())

        if not ok:
            return

        self.table.item(row, 0).setText(new_comment)
        self.table.item(row, 1).setText(query)
        self.save_favorites()

    def edit_comment(self):
        row = self.table.currentRow()
        if row < 0:
            return
        comment_item = self.table.item(row, 0)
        query = self.table.item(row, 1).text()
        old_comment = comment_item.text() if comment_item else ""

        new_comment, ok = QInputDialog.getText(
            self, UITexts.EDIT_COMMENT_TITLE,
            UITexts.EDIT_COMMENT_TEXT.format(query),
            QLineEdit.Normal, old_comment)

        if ok:
            self.table.item(row, 0).setText(new_comment)
            self.save_favorites()

    def edit_shortcut(self):
        row = self.table.currentRow()
        if row < 0:
            return
        query = self.table.item(row, 1).text()
        current_sc = self.table.item(row, 2).text()

        dialog = QDialog(self)
        dialog.setWindowTitle(UITexts.EDIT_SHORTCUT_TITLE)
        dlg_layout = QVBoxLayout(dialog)
        dlg_layout.addWidget(QLabel(UITexts.EDIT_SHORTCUT_TEXT.format(query)))

        from PySide6.QtWidgets import QKeySequenceEdit, QDialogButtonBox
        key_edit = QKeySequenceEdit(QKeySequence(current_sc))
        dlg_layout.addWidget(key_edit)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel | QDialogButtonBox.Reset)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        buttons.button(QDialogButtonBox.Reset).clicked.connect(
            lambda: key_edit.setKeySequence(QKeySequence()))
        dlg_layout.addWidget(buttons)

        if dialog.exec() == QDialog.Accepted:
            new_sequence = key_edit.keySequence()
            new_sc_str = new_sequence.toString(QKeySequence.NativeText)
            if not new_sequence.isEmpty():
                new_key_combo = new_sequence[0]
                new_key = new_key_combo.key()
                new_mods = new_key_combo.keyboardModifiers()

                conflict_desc = self.main_win.shortcut_controller.check_conflict(
                    new_key, new_mods)
                if conflict_desc and new_sc_str != current_sc:
                    res = QMessageBox.question(self, UITexts.SHORTCUT_CONFLICT_TITLE,
                                               UITexts.SHORTCUT_CONFLICT_TEXT.format(
                                                   new_sc_str, conflict_desc) +
                                               "\n\n" +
                                               UITexts.SHORTCUT_OVERRIDE_QUESTION,
                                               QMessageBox.Yes | QMessageBox.No)
                    if res == QMessageBox.No:
                        return

            self.table.item(row, 2).setText(new_sc_str)
            self.save_favorites()

    def delete_favorite(self):
        row = self.table.currentRow()
        if row >= 0:
            self.table.removeRow(row)
            self.save_favorites()

    def move_up(self):
        row = self.table.currentRow()
        if row > 0:
            self._swap_rows(row, row - 1)
            self.table.setCurrentCell(row - 1, 0)
            self.save_favorites()

    def move_down(self):
        row = self.table.currentRow()
        if row >= 0 and row < self.table.rowCount() - 1:
            self._swap_rows(row, row + 1)
            self.table.setCurrentCell(row + 1, 0)
            self.save_favorites()

    def _swap_rows(self, row1, row2):
        for col in range(self.table.columnCount()):
            item1 = self.table.takeItem(row1, col)
            item2 = self.table.takeItem(row2, col)
            self.table.setItem(row1, col, item2)
            self.table.setItem(row2, col, item1)


class RatingStar(QLabel):
    """An individual star label for the rating widget."""
    # Emits the star index (1-5)
    clicked = Signal(int)

    def __init__(self, index, parent=None):
        super().__init__(parent)
        self.index = index
        self.setCursor(Qt.PointingHandCursor)

    def mousePressEvent(self, event):
        """Handles the click to emit its own index."""
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.index)
        super().mousePressEvent(event)


class RatingWidget(QWidget):
    """A widget to view and edit file ratings."""
    rating_updated = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.file_paths = []
        self._current_rating = 0

        # Icons and colors
        self.star_full = QIcon.fromTheme("rating_full")
        self.star_half = QIcon.fromTheme("rating_half")
        self.star_empty = QIcon.fromTheme("rating_empty")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(2)

        rating_layout = QHBoxLayout()
        rating_layout.addWidget(QLabel(UITexts.INFO_RATING_LABEL))
        self.stars = []
        for i in range(1, 6):
            star_label = RatingStar(i, self)
            star_label.clicked.connect(self.on_star_clicked)
            self.stars.append(star_label)
            rating_layout.addWidget(star_label)
        rating_layout.addStretch()

        layout.addLayout(rating_layout)

        self.btn_apply = QPushButton(UITexts.TAG_APPLY_CHANGES)
        self.btn_apply.clicked.connect(self.save_rating)
        self.btn_apply.hide()

        btn_container_layout = QHBoxLayout()
        btn_container_layout.addStretch()
        btn_container_layout.addWidget(self.btn_apply)
        layout.addLayout(btn_container_layout)

        self.update_stars()

    def set_files(self, file_paths):
        """Sets the current files and loads rating from the first one."""
        self.file_paths = file_paths if file_paths else []
        self.load_rating()
        self.btn_apply.hide()

    def load_rating(self):
        """Loads the rating using the XattrManager."""
        self._current_rating = 0
        if self.file_paths:
            rating_str = XattrManager.get_attribute(self.file_paths[0],
                                                    RATING_XATTR_NAME, "0")
            try:
                self._current_rating = int(rating_str)
            except (ValueError, TypeError):
                self._current_rating = 0
        self.update_stars()

    @Slot(int)
    def on_star_clicked(self, star_index):
        """
        Handles a click on a star to cycle its state and update the rating.
        The cycle is: OFF -> FULL -> HALF -> OFF.
        """
        rating_for_half = star_index * 2 - 1
        rating_for_full = star_index * 2
        rating_previous = (star_index - 1) * 2

        current_rating = self._current_rating

        if current_rating > rating_for_full:
            # If a higher star is active, clicking a lower one sets the rating
            # to "full" of the clicked star.
            self._current_rating = rating_for_full
        elif current_rating == rating_for_full:
            # The star is full: cycle to half.
            self._current_rating = rating_for_half
        elif current_rating == rating_for_half:
            # The star is half: cycle to off.
            self._current_rating = rating_previous
        else:  # current_rating < rating_for_half
            # The star is off: cycle to full.
            self._current_rating = rating_for_full

        self.update_stars()
        self.btn_apply.show()

    def update_stars(self):
        """Updates the appearance of the 5 stars according to the rating."""
        rating = self._current_rating
        pixmap_size = self.fontMetrics().height() + 8

        # Get base pixmaps from the theme
        full_pixmap = self.star_full.pixmap(pixmap_size, pixmap_size)
        half_pixmap = self.star_half.pixmap(pixmap_size, pixmap_size)
        empty_pixmap = self.star_empty.pixmap(pixmap_size, pixmap_size)

        for i, star_label in enumerate(self.stars):
            star_value = i * 2 + 2

            if rating >= star_value:
                star_label.setPixmap(full_pixmap)
            elif rating == star_value - 1:
                star_label.setPixmap(half_pixmap)
            else:
                star_label.setPixmap(empty_pixmap)

    def save_rating(self):
        """Saves the current rating using the XattrManager."""
        if not self.file_paths:
            return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            value_to_set = str(self._current_rating) \
                if self._current_rating > 0 else None
            for path in self.file_paths:
                XattrManager.set_attribute(path, RATING_XATTR_NAME, value_to_set)
            self.btn_apply.hide()
            self.rating_updated.emit()
        except IOError as e:
            QMessageBox.critical(self, UITexts.ERROR, str(e))
        finally:
            QApplication.restoreOverrideCursor()


class CircularProgressBar(QWidget):
    """A circular progress bar widget."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self._value = 0
        self._min = 0
        self._max = 100
        self._custom_color = None
        self._angle = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._rotate)
        # Match the height of other status bar widgets like buttons
        self.setFixedSize(22, 22)
        self.setToolTip(f"{self._value}%")

    def _rotate(self):
        self._angle = (self._angle + 10) % 360
        self.update()

    def setRange(self, min_val, max_val):
        """Sets the progress range. Use (0, 0) for indeterminate mode."""
        self._min = min_val
        self._max = max_val
        if min_val == 0 and max_val == 0:
            if not self._timer.isActive():
                self._timer.start(50)
        else:
            self._timer.stop()
            self._angle = 0
        self.update()

    def hideEvent(self, event):
        self._timer.stop()
        super().hideEvent(event)

    def showEvent(self, event):
        if self._min == 0 and self._max == 0:
            self._timer.start(50)
        super().showEvent(event)

    def setCustomColor(self, color):
        """Sets a custom color for the progress arc. Pass None to use default."""
        self._custom_color = color
        self.update()

    def setValue(self, value):
        """Sets the progress value (0-100)."""
        if self._min == 0 and self._max == 0:
            # Switching from indeterminate to normal
            self.setRange(0, 100)
        if self._value != value:
            self._value = max(0, min(100, value))
            self.setToolTip(f"{self._value}%")
            self.update()  # Trigger a repaint

    def value(self):
        """Returns the current progress value."""
        return self._value

    def paintEvent(self, event):
        """Paints the circular progress bar."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Use the widget's rectangle, with a small margin
        rect = self.rect().adjusted(2, 2, -2, -2)

        # 1. Draw the background circle (the track)
        # Use a color from the palette for theme-awareness
        track_color = self.palette().color(self.backgroundRole()).darker(130)
        painter.setPen(QPen(track_color, 2))
        painter.drawEllipse(rect)

        # 2. Draw the foreground arc
        if self._min == 0 and self._max == 0:
            # Indeterminate mode (spinning animation)
            if self._custom_color:
                progress_color = self._custom_color
            else:
                progress_color = self.palette().color(QPalette.Highlight)
            pen = QPen(progress_color, 2)
            pen.setCapStyle(Qt.RoundCap)
            painter.setPen(pen)
            start_angle = (90 - self._angle) * 16
            span_angle = -120 * 16  # Fixed length arc for spinning
            painter.drawArc(rect, start_angle, span_angle)
        elif self._value > 0:
            # Use the palette's highlight color for the progress arc
            if self._custom_color:
                progress_color = self._custom_color
            else:
                progress_color = self.palette().color(QPalette.Highlight)
            pen = QPen(progress_color, 2)
            pen.setCapStyle(Qt.RoundCap)
            painter.setPen(pen)

            # Angles are in 1/16th of a degree.
            # 0 degrees is at the 3 o'clock position. We start at 12 o'clock (90 deg).
            start_angle = 90 * 16
            # Span is negative for clockwise. 360 degrees for 100%.
            span_angle = -int(self._value * 3.6 * 16)

            painter.drawArc(rect, start_angle, span_angle)


class FaceNameInputWidget(QWidget):
    """
    A widget for entering names that maintains a history of the last N used names.

    It features autocomplete and is sorted by recent usage (MRU).
    """
    name_accepted = Signal(str)

    def __init__(self, main_win, parent=None, region_type="Face"):
        """Initializes the widget with a history based on configuration."""
        super().__init__(parent)
        self.main_win = main_win
        self.region_type = region_type
        # Use deque to manage history efficiently with a configurable maximum
        # number of items.
        max_items = APP_CONFIG.get("faces_menu_max_items",
                                   FACES_MENU_MAX_ITEMS_DEFAULT)
        if self.region_type == "Pet":
            max_items = APP_CONFIG.get("pets_menu_max_items",
                                       FACES_MENU_MAX_ITEMS_DEFAULT)
        elif self.region_type == "Body":
            max_items = APP_CONFIG.get("body_menu_max_items",
                                       FACES_MENU_MAX_ITEMS_DEFAULT)
        elif self.region_type == "Object":
            max_items = APP_CONFIG.get("object_menu_max_items",
                                       FACES_MENU_MAX_ITEMS_DEFAULT)
        elif self.region_type == "Landmark":
            max_items = APP_CONFIG.get("landmark_menu_max_items",
                                       FACES_MENU_MAX_ITEMS_DEFAULT)
        self.history = deque(maxlen=max_items)
        self.name_to_tags_map = {}

        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self):
        """Configures the user interface of the widget."""
        self.name_combo = QComboBox()
        self.name_combo.setEditable(True)
        self.name_combo.setInsertPolicy(QComboBox.NoInsert)
        self.name_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.name_combo.setToolTip(UITexts.FACE_NAME_TOOLTIP)
        self.name_combo.lineEdit().setClearButtonEnabled(True)

        # 2. Completer for autocomplete functionality.
        self.completer = QCompleter(self)
        self.completer.setCaseSensitivity(Qt.CaseInsensitive)
        self.completer.setFilterMode(Qt.MatchContains)
        self.completer.setCompletionMode(QCompleter.PopupCompletion)

        self.model = QStringListModel(self)
        self.completer.setModel(self.model)
        self.name_combo.setCompleter(self.completer)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        layout.addWidget(self.name_combo)

    def _connect_signals(self):
        """Connects signals to slots."""
        self.name_combo.lineEdit().returnPressed.connect(self._on_accept)
        self.name_combo.activated.connect(self._on_accept)

    def _on_accept(self):
        """
        Triggered when Enter is pressed or an item is selected.
        Emits the `name_accepted` signal.
        """
        entered_name = self.name_combo.currentText().strip()
        if not entered_name:
            return

        matches = self.name_to_tags_map.get(entered_name, [])
        final_tag = None

        if len(matches) == 0:
            reply = QMessageBox.question(
                self, UITexts.CREATE_TAG_TITLE,
                UITexts.CREATE_TAG_TEXT.format(entered_name),
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                if self.region_type == "Pet":
                    parent_tags_str = APP_CONFIG.get("pet_tags", "Pet")
                    if not parent_tags_str or not parent_tags_str.strip():
                        parent_tags_str = "Pet"
                    dialog_title = UITexts.NEW_PET_TAG_TITLE
                    dialog_text = UITexts.NEW_PET_TAG_TEXT
                elif self.region_type == "Body":
                    parent_tags_str = APP_CONFIG.get("body_tags", "Body")
                    if not parent_tags_str or not parent_tags_str.strip():
                        parent_tags_str = "Body"
                    dialog_title = UITexts.NEW_BODY_TAG_TITLE
                    dialog_text = UITexts.NEW_BODY_TAG_TEXT
                elif self.region_type == "Object":
                    parent_tags_str = APP_CONFIG.get("object_tags", "Object")
                    if not parent_tags_str or not parent_tags_str.strip():
                        parent_tags_str = "Object"
                    dialog_title = UITexts.NEW_OBJECT_TAG_TITLE
                    dialog_text = UITexts.NEW_OBJECT_TAG_TEXT
                elif self.region_type == "Landmark":
                    parent_tags_str = APP_CONFIG.get("landmark_tags", "Landmark")
                    if not parent_tags_str or not parent_tags_str.strip():
                        parent_tags_str = "Landmark"
                    dialog_title = UITexts.NEW_LANDMARK_TAG_TITLE
                    dialog_text = UITexts.NEW_LANDMARK_TAG_TEXT
                else:
                    parent_tags_str = APP_CONFIG.get("person_tags", "Person")
                    if not parent_tags_str or not parent_tags_str.strip():
                        parent_tags_str = "Person"
                    dialog_title = UITexts.NEW_PERSON_TAG_TITLE
                    dialog_text = UITexts.NEW_PERSON_TAG_TEXT

                default_parent = parent_tags_str.split(',')[0].strip()
                suggested_tag = f"{default_parent}/{entered_name}"

                new_full_tag, ok = QInputDialog.getText(
                    self, dialog_title, dialog_text, QLineEdit.Normal, suggested_tag)
                if ok and new_full_tag:
                    final_tag = new_full_tag.strip()
        elif len(matches) == 1:
            final_tag = matches[0]
        else:
            chosen_tag, ok = QInputDialog.getItem(
                self, UITexts.SELECT_TAG_TITLE,
                UITexts.SELECT_TAG_TEXT.format(entered_name),
                matches, 0, False)
            if ok and chosen_tag:
                final_tag = chosen_tag

        if final_tag:
            self.update_history(final_tag)
            self.name_accepted.emit(final_tag)

    def update_history(self, full_tag_path: str):
        """
        Updates the history. Moves the used name to the top of the list (MRU -
        Most Recently Used).
        """
        if not full_tag_path:
            return

        if full_tag_path in self.history:
            self.history.remove(full_tag_path)
        self.history.appendleft(full_tag_path)

    def _update_models(self, display_names):
        """
        Updates the models of the QComboBox and QCompleter with the current history.
        """
        self.model.setStringList(display_names)

        self.name_combo.blockSignals(True)
        current_text = self.name_combo.currentText()
        self.name_combo.clear()
        self.name_combo.addItems(display_names)
        self.name_combo.setEditText(current_text)
        self.name_combo.blockSignals(False)

    def load_data(self, mru_history: list):
        """Loads person names from global tags and combines them with MRU history."""
        self.history.clear()
        if mru_history:
            # Prevent MRU eviction if history is larger than maxlen
            # We take the first N items (most recent) to ensure they fit.
            items_to_load = mru_history[:self.history.maxlen] \
                if self.history.maxlen is not None else mru_history
            for full_tag in items_to_load:
                if full_tag and isinstance(full_tag, str):
                    self.history.append(full_tag)

        all_tags = []
        if self.main_win and hasattr(self.main_win, 'tag_edit_widget'):
            all_tags = self.main_win.tag_edit_widget.available_tags

        if self.region_type == "Pet":
            parent_tags_str = APP_CONFIG.get("pet_tags", "Pet")
            if not parent_tags_str or not parent_tags_str.strip():
                parent_tags_str = "Pet"
        elif self.region_type == "Body":
            parent_tags_str = APP_CONFIG.get("body_tags", "Body")
            if not parent_tags_str or not parent_tags_str.strip():
                parent_tags_str = "Body"
        elif self.region_type == "Object":
            parent_tags_str = APP_CONFIG.get("object_tags", "Object")
            if not parent_tags_str or not parent_tags_str.strip():
                parent_tags_str = "Object"
        elif self.region_type == "Landmark":
            parent_tags_str = APP_CONFIG.get("landmark_tags", "Landmark")
            if not parent_tags_str or not parent_tags_str.strip():
                parent_tags_str = "Landmark"
        else:
            parent_tags_str = APP_CONFIG.get("person_tags", "Person")
            if not parent_tags_str or not parent_tags_str.strip():
                parent_tags_str = "Person"

        person_tag_parents = [p.strip() + '/' for p in parent_tags_str.split(',')
                              if p.strip()]

        self.name_to_tags_map.clear()
        all_person_short_names = set()

        # Combine all available tags with the user's history for a complete list
        tags_to_process = set(all_tags) | set(self.history)

        for tag in tags_to_process:
            is_valid = False
            # Always accept tags explicitly in history
            if tag in self.history:
                is_valid = True
            else:
                for parent in person_tag_parents:
                    if tag.startswith(parent):
                        is_valid = True
                        break

            if is_valid:
                short_name = tag.split('/')[-1]
                if short_name:
                    all_person_short_names.add(short_name)
                    if short_name not in self.name_to_tags_map:
                        self.name_to_tags_map[short_name] = []
                    # Ensure no duplicate full tags are added for a short name
                    if tag not in self.name_to_tags_map[short_name]:
                        self.name_to_tags_map[short_name].append(tag)

        # The display list is built from history first (for MRU order),
        # then supplemented with all other known person names.
        display_names = [tag.split('/')[-1] for tag in self.history]
        for short_name in sorted(list(all_person_short_names)):
            if short_name not in display_names:
                display_names.append(short_name)

        self._update_models(display_names)

    def get_history(self) -> list:
        """Returns the current history list, sorted by most recent."""
        return list(self.history)

    def clear(self):
        """Clears the editor text."""
        self.name_combo.clearEditText()


class CommentWidget(QWidget):
    """A widget to view and edit the 'user.comment' extended attribute."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.file_paths = []
        self._original_comment = ""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)

        layout.addWidget(QLabel(UITexts.INFO_COMMENT_LABEL))

        self.comment_edit = QTextEdit()
        self.comment_edit.setAcceptRichText(False)
        self.comment_edit.setPlaceholderText(UITexts.ENTER_COMMENT)
        self.comment_edit.textChanged.connect(self.on_text_changed)
        layout.addWidget(self.comment_edit)

        self.btn_apply = QPushButton(UITexts.COMMENT_APPLY_CHANGES)
        self.btn_apply.clicked.connect(self.save_comment)
        self.btn_apply.hide()

        btn_container_layout = QHBoxLayout()
        btn_container_layout.addStretch()
        btn_container_layout.addWidget(self.btn_apply)
        layout.addLayout(btn_container_layout)

    def set_files(self, file_paths):
        """Sets the file paths and loads the comment from the first one."""
        self.file_paths = file_paths if file_paths else []
        self.load_comment()
        self.btn_apply.hide()

    def load_comment(self):
        """Loads the comment using the XattrManager."""
        self.comment_edit.blockSignals(True)
        comment = ""
        if self.file_paths:
            comment = XattrManager.get_attribute(
                self.file_paths[0], XATTR_COMMENT_NAME, "")
        self._original_comment = comment
        self.comment_edit.setText(comment)
        self.comment_edit.blockSignals(False)

    def on_text_changed(self):
        """Shows the apply button if the text has changed."""
        self.btn_apply.setVisible(
            self.comment_edit.toPlainText() != self._original_comment)

    def save_comment(self):
        """Saves the comment using the XattrManager."""
        if not self.file_paths:
            return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            new_comment = self.comment_edit.toPlainText()
            value_to_set = new_comment if new_comment.strip() else None
            for path in self.file_paths:
                XattrManager.set_attribute(path, XATTR_COMMENT_NAME, value_to_set)
            self._original_comment = new_comment
            self.btn_apply.hide()
        except IOError as e:
            QMessageBox.critical(self, UITexts.ERROR, str(e))
        finally:
            QApplication.restoreOverrideCursor()


class TagFilterProxyModel(QSortFilterProxyModel):
    """Proxy model for hierarchical tag filtering supporting slash paths."""

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:
        """Determine if a row is accepted by the filter criteria."""
        model = self.sourceModel()
        index = model.index(source_row, 0, source_parent)
        if not index.isValid():
            return False

        path = index.data(Qt.UserRole) or ""
        filter_str = self.filterRegularExpression().pattern().strip().lower()

        if not filter_str:
            return True

        # Check if current path matches or contains the filter string
        if filter_str in path.lower():
            return True

        # Recursively check descendants so parent nodes remain visible if a child matches
        for i in range(model.rowCount(index)):
            if self.filterAcceptsRow(i, index):
                return True

        return False


class TagSelectorWidget(QWidget):
    """Widget containing a filter/input textbox, a tag treeview, and action buttons."""

    def __init__(self, parent: QWidget = None) -> None:
        """Initialize the tag selector widget by loading tags from the Baloo database."""
        super().__init__(parent)
        self.available_tags = []
        self._load_all = False
        self._tag_paths = set()

        self.load_available_tags()
        self._init_ui()
        self._populate_model()

    def load_available_tags(self) -> None:
        """Load all known tags from the Baloo index database."""
        db_path = os.path.expanduser("~/.local/share/baloo/index")
        if not os.path.exists(db_path) or not os.access(db_path, os.R_OK):
            self.available_tags = []
            self._load_all = True
            return

        tags = []
        success = False
        try:
            # Auto-detect if it's a directory or a file to set subdir correctly
            is_dir = os.path.isdir(db_path)
            # Connect to the LMDB environment for Baloo
            with lmdb.open(db_path, subdir=is_dir, readonly=True,
                           lock=False, max_dbs=20) as env:
                postingdb = env.open_db(b'postingdb')
                with env.begin() as txn:
                    cursor = txn.cursor(postingdb)
                    prefix = b'TAG-'
                    # Iterate over keys starting with the tag prefix
                    if cursor.set_range(prefix):
                        for key, _ in cursor:
                            if not key.startswith(prefix):
                                break
                            tags.append(key[4:].decode('utf-8'))
                success = True
        except Exception as e:
            logger.debug(f"Failed to load Baloo tags from {db_path}: {e}")

        if success:
            # Use set comparison to reliably detect any content change in tags
            if set(tags) != set(self.available_tags):
                self._load_all = True
            self.available_tags = tags

    def _init_ui(self) -> None:
        """Initialize user interface components and layouts."""
        main_layout = QVBoxLayout(self)

        # Textbox for filtering and input at the top
        self.line_edit = QLineEdit(self)
        self.line_edit.setPlaceholderText(
            "Filter or enter tag (e.g., Parent/Child)..."
        )
        self.line_edit.textChanged.connect(self._on_text_changed)
        main_layout.addWidget(self.line_edit)

        # TreeView for displaying hierarchical tags
        self.tree_view = QTreeView(self)
        self.tree_view.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tree_view.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tree_view.setHeaderHidden(True)

        self.source_model = QStandardItemModel(self)
        self.proxy_model = TagFilterProxyModel(self)
        self.proxy_model.setSourceModel(self.source_model)
        self.proxy_model.setRecursiveFilteringEnabled(True)

        self.tree_view.setModel(self.proxy_model)
        self.tree_view.clicked.connect(self._on_tree_item_clicked)
        main_layout.addWidget(self.tree_view)

        # Bottom buttons layout
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.action_button = QPushButton("Create", self)
        button_layout.addWidget(self.action_button)

        self.cancel_button = QPushButton("Cancel", self)
        button_layout.addWidget(self.cancel_button)

        main_layout.addLayout(button_layout)

    def _populate_model(self) -> None:
        """Parse available tags and populate the standard item model."""
        self.source_model.clear()
        self._tag_paths.clear()

        root = self.source_model.invisibleRootItem()
        item_dict = {}

        for tag_line in self.available_tags:
            tag_line = tag_line.strip()
            if not tag_line:
                continue

            self._tag_paths.add(tag_line)
            parts = [p.strip() for p in tag_line.split("/") if p.strip()]
            current_path = ""
            parent = root

            for part in parts:
                current_path = f"{current_path}/{part}" if current_path else part
                if current_path not in item_dict:
                    item = QStandardItem(part)
                    item.setData(current_path, Qt.UserRole)
                    parent.appendRow([item])
                    item_dict[current_path] = item
                parent = item_dict[current_path]

        self.tree_view.expandAll()
        self._update_action_button()

    def _on_text_changed(self, text: str) -> None:
        """Handle text changes in the filter/input textbox."""
        self.proxy_model.setFilterRegularExpression(text)
        self.tree_view.expandAll()
        self._update_action_button()

    def _on_tree_item_clicked(self, proxy_index: QModelIndex) -> None:
        """Handle tree item selection to populate the textbox."""
        source_index = self.proxy_model.mapToSource(proxy_index)
        path = source_index.data(Qt.UserRole)
        if path:
            self.line_edit.setText(path)

    def _update_action_button(self) -> None:
        """Update action button text based on whether input matches an existing tag."""
        current_text = self.line_edit.text().strip()
        if current_text in self._tag_paths:
            self.action_button.setText("Select")
        else:
            self.action_button.setText("Create")

    def get_current_text(self) -> str:
        """Return the current text in the input textbox."""
        return self.line_edit.text().strip()

    def is_existing_tag(self) -> bool:
        """Check if current textbox content corresponds to an existing tag."""
        return self.get_current_text() in self._tag_paths


class TagSelectorDialog(QDialog):
    """Dialog wrapper for TagSelectorWidget providing standard dialog behavior."""

    def __init__(self, parent: QWidget = None) -> None:
        """Initialize the tag selector dialog."""
        super().__init__(parent)
        self.setWindowTitle("Tag Selector")
        self.resize(450, 550)

        layout = QVBoxLayout(self)
        self.selector_widget = TagSelectorWidget(self)
        layout.addWidget(self.selector_widget)

        # Connect dialog buttons
        self.selector_widget.cancel_button.clicked.connect(self.reject)
        self.selector_widget.action_button.clicked.connect(self.accept)

    def get_selected_tag(self) -> str:
        """Return the selected or entered tag path."""
        return self.selector_widget.get_current_text()


# ---------------------------------------------------------------------------
# GeoMapWidget
# ---------------------------------------------------------------------------

# WebEngine imports are deferred until the map tab is activated to avoid
# initializing Chromium during application startup.
# Do NOT import QWebEngineView at module level.
_HAVE_WEBENGINE = None  # None = not yet checked; True/False after first check
_QWebEngineView = None
_QWebChannel = None
_QWebEngineSettings = None


def _init_webengine():
    """Lazily import WebEngine modules. Safe to call multiple times."""
    global _HAVE_WEBENGINE, _QWebEngineView, _QWebChannel, _QWebEngineSettings
    if _HAVE_WEBENGINE is not None:
        return _HAVE_WEBENGINE
    try:
        from PySide6.QtWebEngineWidgets import QWebEngineView as _WEV
        from PySide6.QtWebChannel import QWebChannel as _WC
        from PySide6.QtWebEngineCore import QWebEngineSettings as _WES
        _QWebEngineView = _WEV
        _QWebChannel = _WC
        _QWebEngineSettings = _WES
        _HAVE_WEBENGINE = True
    except Exception:
        _HAVE_WEBENGINE = False
    return _HAVE_WEBENGINE


def _webchannel_script():
    """Read Qt's WebChannel client script for inline use in the map page."""
    resource = QFile(":/qtwebchannel/qwebchannel.js")
    if not resource.open(QIODevice.OpenModeFlag.ReadOnly):
        raise RuntimeError(
            "Could not read Qt WebChannel client script: "
            f"{resource.errorString()}")
    try:
        return bytes(resource.readAll()).decode("utf-8")
    finally:
        resource.close()


# Leaflet map HTML/JS template.  All external resources are loaded from CDN.
# Communication with Python uses Qt WebChannel (qt.webChannelTransport).
_MAP_HTML = """\
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>Map</title>
<link rel="stylesheet"
      href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<style>
  html,body,#map{height:100%;margin:0;padding:0;background:#1a1a2e;}
  .leaflet-popup-content-wrapper{background:#2a2a4a;color:#e0e0ff;border:1px solid #4a4aaa;}
  .leaflet-popup-tip{background:#2a2a4a;}
  .leaflet-popup-content a{color:#88aaff;}
</style>
</head>
<body>
<div id="map"></div>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"
        onerror='document.getElementById("map").textContent=__MAP_LOAD_FAILED__'></script>
<script src="qrc:///qtwebchannel/qwebchannel.js"></script>
<script>
var map = L.map('map', {zoomControl:true, attributionControl:true})
           .setView([20,0], 2);

L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
  attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
  maxZoom: 19
}).addTo(map);

var markers = [];
var editMode = false;
var bridge = null;

// Marker icons
var blueIcon = L.icon({
  iconUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png',
  iconRetinaUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png',
  shadowUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
  iconSize:[25,41], iconAnchor:[12,41], popupAnchor:[1,-34], shadowSize:[41,41]
});

var redIcon = L.icon({
  iconUrl: 'https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-2x-red.png',
  shadowUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
  iconSize:[25,41], iconAnchor:[12,41], popupAnchor:[1,-34], shadowSize:[41,41]
});

new QWebChannel(qt.webChannelTransport, function(channel) {
  bridge = channel.objects.bridge;
});

function clearMarkers() {
  markers.forEach(function(m){ map.removeLayer(m); });
  markers = [];
}

function showMarkers(data) {
  // data: array of {path, name, lat, lon, selected}
  clearMarkers();
  var bounds = [];
  data.forEach(function(item) {
    var icon = item.selected ? redIcon : blueIcon;
    var m = L.marker([item.lat, item.lon], {icon: icon, title: item.name});
    m.bindPopup('<b>' + item.name + '</b>');
    m.on('click', function() {
      if(bridge) bridge.markerClicked(item.path);
    });
    m.addTo(map);
    markers.push(m);
    bounds.push([item.lat, item.lon]);
  });
  if(bounds.length === 1) {
    map.setView(bounds[0], Math.max(map.getZoom(), 13));
  } else if(bounds.length > 1) {
    map.fitBounds(bounds, {padding:[30,30], maxZoom:15});
  }
}

function setEditMode(enabled) {
  editMode = enabled;
  map.getContainer().style.cursor = enabled ? 'crosshair' : '';
}

map.on('click', function(e) {
  if(editMode && bridge) {
    bridge.mapClicked(e.latlng.lat, e.latlng.lng);
    setEditMode(false);
  }
});

map.on('contextmenu', function(e) {
  if(editMode) {
    setEditMode(false);
    if(bridge) bridge.editCancelled();
  }
});

window.addEventListener('resize', function() {
  map.invalidateSize({pan:false});
});
</script>
</body>
</html>
"""


class _MapBridge(QObject):
    """Qt/JS bridge object exposed via QWebChannel.

    Signals from JS to Python are handled here.
    """
    marker_clicked = Signal(str)   # path
    map_clicked = Signal(float, float)  # lat, lon
    edit_cancelled = Signal()

    @Slot(str)
    def markerClicked(self, path):
        self.marker_clicked.emit(path)

    @Slot(float, float)
    def mapClicked(self, lat, lon):
        self.map_clicked.emit(lat, lon)

    @Slot()
    def editCancelled(self):
        self.edit_cancelled.emit()


class GeoMapWidget(QWidget):
    """Sidebar tab widget that displays selected photos on an OpenStreetMap.

    Features:
    - Shows geolocated photos as Leaflet markers (free OpenStreetMap tiles).
    - Clicking a marker updates thumbnail selection in the main window.
    - "Open in Google Maps" button (free, no API key required).
    - Allows setting/editing GPS coordinates for non-geolocated photos.
    - Lazy refresh: only updates when the tab is active.

    Signals:
        selection_requested (list[str]): Emitted when the user clicks a marker
            on the map; carries a list of file paths to select.
    """

    selection_requested = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._is_active = False
        self._current_paths = []
        self._edit_paths = []    # paths being geolocated in edit mode
        self._gps_cache = {}     # path -> (lat, lon) or None, per refresh
        self.web_view = None     # set below if WebEngine is available
        self._bridge = None
        self._channel = None
        self._map_initialized = False
        self._map_loaded = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # ---- Toolbar ----
        tb = QHBoxLayout()
        tb.setSpacing(4)

        self.btn_googlemaps = QPushButton(UITexts.MAP_OPEN_GOOGLEMAPS)
        self.btn_googlemaps.setIcon(QIcon.fromTheme("internet-web-browser"))
        self.btn_googlemaps.setToolTip(UITexts.MAP_OPEN_GOOGLEMAPS_TOOLTIP)
        self.btn_googlemaps.setEnabled(False)
        self.btn_googlemaps.clicked.connect(self._open_google_maps)
        tb.addWidget(self.btn_googlemaps)

        self.btn_edit = QPushButton(UITexts.MAP_SET_LOCATION)
        self.btn_edit.setIcon(QIcon.fromTheme("document-edit"))
        self.btn_edit.setToolTip(UITexts.MAP_SET_LOCATION_TOOLTIP)
        self.btn_edit.setEnabled(False)
        self.btn_edit.clicked.connect(self._start_editing)
        tb.addWidget(self.btn_edit)

        self.btn_copy_location = QPushButton(UITexts.MAP_COPY_LOCATION)
        self.btn_copy_location.setIcon(QIcon.fromTheme("edit-copy"))
        self.btn_copy_location.setToolTip(
            UITexts.MAP_COPY_LOCATION_TOOLTIP)
        self.btn_copy_location.setEnabled(False)
        self.btn_copy_location.clicked.connect(
            self._copy_location_to_selected)
        tb.addWidget(self.btn_copy_location)

        self.btn_clear = QPushButton(UITexts.MAP_CLEAR_LOCATION)
        self.btn_clear.setIcon(QIcon.fromTheme("edit-delete"))
        self.btn_clear.setToolTip(UITexts.MAP_CLEAR_LOCATION_TOOLTIP)
        self.btn_clear.setEnabled(False)
        self.btn_clear.clicked.connect(self._clear_gps_location)
        tb.addWidget(self.btn_clear)

        layout.addLayout(tb)

        # ---- Status label ----
        self.status_lbl = QLabel(UITexts.MAP_NO_SELECTION)
        self.status_lbl.setWordWrap(True)
        self.status_lbl.setStyleSheet("color: gray; font-style: italic; font-size: 11px;")
        layout.addWidget(self.status_lbl)

        # Keep the map area empty until the user opens this tab. QtWebEngine
        # starts Chromium during widget construction, which can crash startup
        # on some Linux systems even when the containing dock is hidden.
        self._map_layout = QVBoxLayout()
        self._map_layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(self._map_layout, stretch=1)

        # ---- Ungeolocated list ----
        self.ungeo_lbl = QLabel()
        self.ungeo_lbl.setStyleSheet("color: #aaaaaa; font-size: 11px;")
        self.ungeo_lbl.setWordWrap(True)
        self.ungeo_lbl.hide()
        layout.addWidget(self.ungeo_lbl)

    def _initialize_map(self):
        """Create the WebEngine view only when the map tab is first opened."""
        if self._map_initialized:
            return
        self._map_initialized = True

        if _init_webengine():
            self.web_view = _QWebEngineView()
            self.web_view.settings().setAttribute(
                _QWebEngineSettings.WebAttribute.JavascriptEnabled, True)

            self._channel = _QWebChannel(self.web_view.page())
            self._bridge = _MapBridge(self)
            self._channel.registerObject("bridge", self._bridge)
            self.web_view.page().setWebChannel(self._channel)

            webchannel_tag = (
                '<script src="qrc:///qtwebchannel/qwebchannel.js"></script>')
            if webchannel_tag not in _MAP_HTML:
                raise RuntimeError(
                    "Map HTML is missing the Qt WebChannel script tag.")
            html = _MAP_HTML.replace(
                webchannel_tag, f"<script>{_webchannel_script()}</script>")
            html = html.replace(
                "__MAP_LOAD_FAILED__", json.dumps(UITexts.MAP_LOAD_FAILED))
            self.web_view.loadFinished.connect(self._on_map_load_finished)
            self.web_view.setHtml(html)
            self._map_layout.addWidget(self.web_view)

            self._bridge.marker_clicked.connect(self._on_marker_clicked)
            self._bridge.map_clicked.connect(self._on_map_clicked)
            self._bridge.edit_cancelled.connect(self._cancel_editing)
        else:
            fallback = QLabel(UITexts.MAP_WEBENGINE_MISSING)
            fallback.setAlignment(Qt.AlignCenter)
            fallback.setWordWrap(True)
            fallback.setStyleSheet("color: #cc8800; font-size: 13px; padding: 20px;")
            self._map_layout.addWidget(fallback)

    def _on_map_load_finished(self, success):
        self._map_loaded = success
        if success and self._is_active:
            self._invalidate_map_size()
            self._do_refresh()

    def showEvent(self, event):
        super().showEvent(event)
        self._invalidate_map_size()

    def _invalidate_map_size(self):
        if self.web_view is not None and self._map_loaded:
            QTimer.singleShot(
                0, lambda: self.web_view.page().runJavaScript(
                    "map.invalidateSize({pan:false});"))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def is_active(self) -> bool:
        return self._is_active

    def set_active(self, active: bool):
        """Called by the main window when this tab is shown or hidden."""
        self._is_active = active
        if active:
            self.initialize_if_ready()

    def initialize_if_ready(self):
        """Initialize the map when the main window is ready and not scanning."""
        if not self._is_active:
            return

        parent = self.parentWidget()
        while parent is not None:
            if not getattr(parent, "_map_startup_ready", True):
                return
            if getattr(parent, "_is_loading", False):
                return
            parent = parent.parentWidget()

        self._initialize_map()
        self.refresh(self._current_paths)

    def refresh(self, selected_paths: list):
        """Refreshes the map with the given list of selected file paths.

        This is a no-op if the tab is not currently active.
        """
        self._current_paths = list(selected_paths)
        if not self._is_active:
            return
        self._do_refresh()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _do_refresh(self):
        """Actually performs the map refresh (reads GPS, updates JS markers)."""
        paths = self._current_paths
        if not paths:
            self.status_lbl.setText(UITexts.MAP_NO_SELECTION)
            self._update_buttons(geolocated_count=0, total=0)
            self.ungeo_lbl.hide()
            if self.web_view is not None and self._map_loaded:
                self.web_view.page().runJavaScript("clearMarkers();")
            return

        # Read GPS data for all selected paths (use cache for speed)
        gps_data = []
        ungeolocated = []
        for path in paths:
            if path not in self._gps_cache:
                self._gps_cache[path] = MetadataManager.read_gps(path)
            coords = self._gps_cache[path]
            if coords:
                gps_data.append({
                    "path": path,
                    "name": os.path.basename(path),
                    "lat": coords[0],
                    "lon": coords[1],
                    "selected": True,
                })
            else:
                ungeolocated.append(os.path.basename(path))

        geolocated_count = len(gps_data)
        self._update_buttons(geolocated_count, len(paths))

        if geolocated_count == 0:
            self.status_lbl.setText(UITexts.MAP_NO_GPS)
        else:
            self.status_lbl.setText(
                f"{geolocated_count}/{len(paths)} photo(s) with GPS data.")

        # Show ungeolocated names
        if ungeolocated:
            self.ungeo_lbl.setText(
                UITexts.MAP_UNGEOLOCATED.format(len(ungeolocated)) +
                " " + ", ".join(ungeolocated[:8]) +
                (" …" if len(ungeolocated) > 8 else ""))
            self.ungeo_lbl.show()
        else:
            self.ungeo_lbl.hide()

        # Update JS map
        if self.web_view is not None and self._map_loaded:
            import json as _json
            js_data = _json.dumps(gps_data)
            self.web_view.page().runJavaScript(f"showMarkers({js_data});")

    def _update_buttons(self, geolocated_count: int, total: int):
        """Enables/disables toolbar buttons based on current selection."""
        has_geo = geolocated_count > 0
        has_selection = total > 0

        # Google Maps: enabled when at least one geolocated photo
        self.btn_googlemaps.setEnabled(has_geo)
        # Edit: a map click assigns the point to every selected photo.
        self.btn_edit.setEnabled(has_selection and HAVE_EXIV2)
        self.btn_copy_location.setEnabled(
            total > 1 and has_geo and HAVE_EXIV2)
        # Clear: enabled for single geolocated photo
        self.btn_clear.setEnabled(total == 1 and geolocated_count == 1
                                  and HAVE_EXIV2)

    def _open_google_maps(self):
        """Opens the first geolocated photo's coordinates in Google Maps
        using the browser (free, no API key required).
        """
        locations = self._get_geolocated_paths()
        if not locations:
            return

        distinct_coordinates = {tuple(coords) for _path, coords in locations}
        location_index = 0
        if len(distinct_coordinates) > 1:
            choices = [
                f"{os.path.basename(path)} — {lat:.6f}, {lon:.6f}"
                for path, (lat, lon) in locations
            ]
            selected, accepted = QInputDialog.getItem(
                self, UITexts.MAP_SELECT_GOOGLE_LOCATION_TITLE,
                UITexts.MAP_SELECT_GOOGLE_LOCATION_PROMPT, choices,
                0, False)
            if not accepted:
                return
            location_index = choices.index(selected)

        lat, lon = locations[location_index][1]
        url = QUrl(f"https://maps.google.com/?q={lat},{lon}")
        QDesktopServices.openUrl(url)

    def _get_geolocated_paths(self):
        """Returns selected paths with known GPS coordinates, reading cache misses."""
        locations = []
        for path in self._current_paths:
            if path not in self._gps_cache:
                self._gps_cache[path] = MetadataManager.read_gps(path)
            coords = self._gps_cache[path]
            if coords:
                locations.append((path, coords))
        return locations

    def _choose_copy_location(self, locations, ungeolocated_count):
        """Shows source-location and target-scope choices before copying."""
        dialog = QDialog(self)
        dialog.setWindowTitle(UITexts.MAP_COPY_LOCATION_TITLE)
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel(UITexts.MAP_COPY_LOCATION_PROMPT, dialog))

        distinct_coordinates = {tuple(coords) for _path, coords in locations}
        location_list = None
        if len(distinct_coordinates) > 1:
            location_list = QListWidget(dialog)
            for path, (lat, lon) in locations:
                location_list.addItem(
                    f"{os.path.basename(path)} — {lat:.6f}, {lon:.6f}")
            location_list.setCurrentRow(0)
            layout.addWidget(location_list)

        all_radio = QRadioButton(
            UITexts.MAP_COPY_LOCATION_ALL.format(len(self._current_paths)),
            dialog)
        ungeolocated_radio = QRadioButton(
            UITexts.MAP_COPY_LOCATION_UNGEOLOCATED.format(
                ungeolocated_count), dialog)
        ungeolocated_radio.setEnabled(ungeolocated_count > 0)
        if ungeolocated_count:
            ungeolocated_radio.setChecked(True)
        else:
            all_radio.setChecked(True)
        layout.addWidget(all_radio)
        layout.addWidget(ungeolocated_radio)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel, parent=dialog)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None

        location_index = location_list.currentRow() if location_list else 0
        if location_index < 0:
            return None
        return locations[location_index][1], all_radio.isChecked()

    def _copy_location_to_selected(self):
        """Copies one selected GPS location to all or ungeolocated selections."""
        locations = self._get_geolocated_paths()
        if not locations or not HAVE_EXIV2:
            return

        ungeolocated = [
            path for path in self._current_paths
            if self._gps_cache.get(path) is None
        ]
        choice = self._choose_copy_location(locations, len(ungeolocated))
        if choice is None:
            return
        coords, copy_to_all = choice
        targets = self._current_paths if copy_to_all else ungeolocated

        errors = []
        copied_count = 0
        for path in targets:
            try:
                MetadataManager.write_gps(path, *coords)
            except Exception as exc:
                errors.append((path, exc))
            else:
                self._gps_cache.pop(path, None)
                copied_count += 1

        self._do_refresh()
        if errors:
            path, error = errors[0]
            self.status_lbl.setText(
                UITexts.MAP_GPS_WRITE_ERROR.format(
                    f"{os.path.basename(path)}: {error}"))
            self.status_lbl.setStyleSheet(
                "color: #cc4444; font-style: italic;")
        else:
            self.status_lbl.setText(
                UITexts.MAP_COPY_LOCATION_DONE.format(copied_count))
            self.status_lbl.setStyleSheet(
                "color: gray; font-style: italic; font-size: 11px;")

    def _start_editing(self):
        """Enters editing mode: the next map click sets the GPS location."""
        if not self._current_paths:
            return
        self._edit_paths = list(self._current_paths)
        self.status_lbl.setText(UITexts.MAP_EDITING_LOCATION)
        self.btn_edit.setEnabled(False)
        if self.web_view is not None:
            self.web_view.page().runJavaScript("setEditMode(true);")

    def _cancel_editing(self):
        """Cancels editing mode without changing any data."""
        self._edit_paths = []
        self._do_refresh()

    @Slot(str)
    def _on_marker_clicked(self, path: str):
        """Called from JS when the user clicks a map marker."""
        if path:
            self.selection_requested.emit([path])

    @Slot(float, float)
    def _on_map_clicked(self, lat: float, lon: float):
        """Called from JS when the user clicks the map in edit mode."""
        paths = self._edit_paths
        self._edit_paths = []
        if not paths:
            return

        errors = []
        for path in paths:
            try:
                MetadataManager.write_gps(path, lat, lon)
            except Exception as exc:
                errors.append((path, exc))
            else:
                self._gps_cache.pop(path, None)

        self._do_refresh()
        if errors:
            path, error = errors[0]
            self.status_lbl.setText(UITexts.MAP_GPS_WRITE_ERROR.format(
                f"{os.path.basename(path)}: {error}"))
            self.status_lbl.setStyleSheet("color: #cc4444; font-style: italic;")
        else:
            self.status_lbl.setText(
                UITexts.MAP_LOCATION_ASSIGNED.format(
                    len(paths) - len(errors)))
            self.status_lbl.setStyleSheet(
                "color: gray; font-style: italic; font-size: 11px;")

    def _clear_gps_location(self):
        """Removes GPS EXIF tags from the single selected photo."""
        if not self._current_paths:
            return
        path = self._current_paths[0]
        try:
            MetadataManager.clear_gps(path)
            self._gps_cache.pop(path, None)
            self._do_refresh()
        except Exception as e:
            self.status_lbl.setText(UITexts.MAP_GPS_WRITE_ERROR.format(str(e)))
