"""
Properties Dialog Module for Bagheera Image Viewer.

This module provides the properties dialog for the application, which displays
detailed information about an image file across several tabs: general file
info, editable metadata (extended attributes), and EXIF/XMP/IPTC data.

Classes:
    PropertiesDialog: A QDialog that presents file properties in a tabbed
                      interface.
"""
from PySide6.QtWidgets import (
    QWidget, QLabel,  QVBoxLayout, QMessageBox, QMenu, QInputDialog,
    QDialog, QTableWidget, QTableWidgetItem, QHeaderView, QTabWidget,
    QFormLayout, QDialogButtonBox, QApplication, QToolBar, QAbstractItemView
)
from PySide6.QtGui import (
    QImageReader, QIcon, QColor
)
from PySide6.QtCore import (QThread, Signal, Qt, QFileInfo, QLocale)
from .constants import (
    RATING_XATTR_NAME, XATTR_NAME, UITexts
)
from .metadatamanager import MetadataManager, HAVE_EXIV2, XattrManager


class PropertiesLoader(QThread):
    """Background thread to load metadata (xattrs and EXIF) asynchronously."""
    loaded = Signal(dict, dict)

    def __init__(self, path, parent=None):
        super().__init__(parent)
        self.path = path
        self._abort = False

    def stop(self):
        """Signals the thread to stop and waits for it."""
        self._abort = True
        self.wait()

    def run(self):
        # Xattrs
        if self._abort:
            return
        xattrs = XattrManager.get_all_attributes(self.path)

        if self._abort:
            return

        # EXIF
        exif_data = MetadataManager.read_all_metadata(self.path)
        if not self._abort:
            self.loaded.emit(xattrs, exif_data)


class PropertiesDialog(QDialog):
    """
    A dialog window to display detailed properties of an image file.

    This dialog features multiple tabs:
    - General: Basic file information (size, dates, dimensions). This involves os.stat
    and QImageReader.
    - Metadata: Editable key-value pairs, primarily for extended attributes (xattrs).
    - EXIF: Detailed EXIF, IPTC, and XMP metadata, loaded via the exiv2 library.
    """
    def __init__(self, path, initial_tags=None, initial_rating=0, parent=None):
        """
        Initializes the PropertiesDialog.

        Args:
            path (str): The absolute path to the image file.
            parent (QWidget, optional): The parent widget. Defaults to None.
        """
        super().__init__(parent)
        self.path = path
        self.setWindowTitle(UITexts.PROPERTIES_TITLE)
        self._initial_tags = initial_tags if initial_tags is not None else []
        self._initial_rating = initial_rating
        self.original_xattrs = {}
        self.original_exif = {}
        self.loader = None
        self.resize(400, 500)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        layout = QVBoxLayout(self)
        tabs = QTabWidget()
        layout.addWidget(tabs)

        # --- General Tab ---
        general_widget = QWidget()
        form_layout = QFormLayout(general_widget)
        form_layout.setLabelAlignment(Qt.AlignRight)
        form_layout.setFormAlignment(Qt.AlignLeft | Qt.AlignTop)
        form_layout.setContentsMargins(20, 20, 20, 20)
        form_layout.setSpacing(10)

        info = QFileInfo(path)
        reader = QImageReader(path)
        reader.setAutoTransform(True)

        # Basic info
        form_layout.addRow(UITexts.PROPERTIES_FILENAME, QLabel(info.fileName()))
        form_layout.addRow(UITexts.PROPERTIES_LOCATION, QLabel(info.path()))
        form_layout.addRow(UITexts.PROPERTIES_SIZE,
                           QLabel(self.format_size(info.size())))

        # Dates
        form_layout.addRow(UITexts.PROPERTIES_CREATED,
                           QLabel(QLocale.system().toString(info.birthTime(),
                                                            QLocale.ShortFormat)))
        form_layout.addRow(UITexts.PROPERTIES_MODIFIED,
                           QLabel(QLocale.system().toString(info.lastModified(),
                                                            QLocale.ShortFormat)))

        # Image info
        size = reader.size()
        fmt = reader.format().data().decode('utf-8').upper()
        if size.isValid():
            form_layout.addRow(UITexts.PROPERTIES_DIMENSIONS,
                               QLabel(f"{size.width()} x {size.height()} px"))
            megapixels = (size.width() * size.height()) / 1_000_000
            form_layout.addRow(UITexts.PROPERTIES_MEGAPIXELS,
                               QLabel(f"{megapixels:.2f} MP"))

            # Read image to get depth
            img = reader.read()
            if not img.isNull():
                form_layout.addRow(UITexts.PROPERTIES_COLOR_DEPTH,
                                   QLabel(f"{img.depth()} {UITexts.BITS}"))

        if fmt:
            form_layout.addRow(UITexts.PROPERTIES_FORMAT, QLabel(fmt))

        tabs.addTab(general_widget, QIcon.fromTheme("dialog-information"),
                    UITexts.PROPERTIES_GENERAL_TAB)

        # --- Metadata Tab ---
        meta_widget = QWidget()
        meta_layout = QVBoxLayout(meta_widget)

        self.meta_toolbar = QToolBar()
        self._setup_table_toolbar(
            self.meta_toolbar, self.on_add_meta, self.on_delete_meta,
            self.on_delete_all_meta, self.on_save_meta, self.on_cancel_meta)
        meta_layout.addWidget(self.meta_toolbar)

        self.table = QTableWidget()
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(UITexts.PROPERTIES_TABLE_HEADER)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QAbstractItemView.DoubleClicked |
                                   QAbstractItemView.EditKeyPressed |
                                   QAbstractItemView.AnyKeyPressed)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)

        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.show_context_menu)

        # Initial partial load (synchronous, just passed args)
        self.update_metadata_table({}, initial_only=True)
        meta_layout.addWidget(self.table)
        tabs.addTab(meta_widget, QIcon.fromTheme("document-properties"),
                    UITexts.PROPERTIES_METADATA_TAB)

        # --- EXIF Tab ---
        exif_widget = QWidget()
        exif_layout = QVBoxLayout(exif_widget)

        self.exif_toolbar = QToolBar()
        self._setup_table_toolbar(
            self.exif_toolbar, self.on_add_exif, self.on_delete_exif,
            self.on_delete_all_exif, self.on_save_exif, self.on_cancel_exif)
        exif_layout.addWidget(self.exif_toolbar)

        self.exif_table = QTableWidget()
        # This table will display EXIF/XMP/IPTC data.
        # Reading this data involves opening the file with exiv2, which is a disk read.
        # This is generally acceptable for a properties dialog, as it's an explicit
        # user request for detailed information. Caching all possible EXIF data
        # for every image might be too memory intensive if not frequently accessed.
        # Therefore, this disk read is considered necessary and not easily optimizable
        # without a significant architectural change (e.g., a dedicated metadata DB).
        self.exif_table.setColumnCount(2)
        self.exif_table.setHorizontalHeaderLabels(UITexts.PROPERTIES_TABLE_HEADER)
        self.exif_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.exif_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.exif_table.verticalHeader().setVisible(False)
        self.exif_table.setAlternatingRowColors(True)
        self.exif_table.setEditTriggers(QAbstractItemView.DoubleClicked |
                                        QAbstractItemView.EditKeyPressed |
                                        QAbstractItemView.AnyKeyPressed)
        self.exif_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.exif_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.exif_table.setContextMenuPolicy(Qt.CustomContextMenu)
        # This is a disk read.
        self.exif_table.customContextMenuRequested.connect(self.show_exif_context_menu)

        # Placeholder for EXIF
        self.update_exif_table(None)

        exif_layout.addWidget(self.exif_table)
        tabs.addTab(exif_widget, QIcon.fromTheme("view-details"),
                    UITexts.PROPERTIES_EXIF_TAB)

        # Buttons
        btn_box = QDialogButtonBox(QDialogButtonBox.Close)
        close_button = btn_box.button(QDialogButtonBox.Close)
        if close_button:
            close_button.setIcon(QIcon.fromTheme("window-close"))
        btn_box.rejected.connect(self.close)
        layout.addWidget(btn_box)

        # Start background loading
        self.reload_metadata()

    def _setup_table_toolbar(self, toolbar, add_slot, del_slot, del_all_slot, save_slot,
                             cancel_slot):
        """Helper to populate toolbars with buttons."""
        toolbar.addAction(QIcon.fromTheme("list-add"), UITexts.CREATE, add_slot)
        toolbar.addAction(QIcon.fromTheme("list-remove"), UITexts.DELETE, del_slot)
        toolbar.addAction(
            QIcon.fromTheme("edit-clear-all"), UITexts.PROPERTIES_DELETE_ALL,
            del_all_slot)
        toolbar.addSeparator()
        toolbar.addAction(QIcon.fromTheme("document-save"), UITexts.SAVE, save_slot)
        toolbar.addAction(QIcon.fromTheme("edit-undo"), UITexts.CANCEL, cancel_slot)

    def on_add_meta(self):
        key, ok = QInputDialog.getText(
            self, UITexts.PROPERTIES_ADD_ATTR, UITexts.PROPERTIES_ADD_ATTR_NAME)
        if ok and key:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(key))
            v_item = QTableWidgetItem("")
            self.table.setItem(row, 1, v_item)
            self.table.setCurrentItem(v_item)
            self.table.editItem(v_item)

    def on_delete_meta(self):
        rows = sorted(set(index.row() for index in self.table.selectedIndexes()),
                      reverse=True)
        for row in rows:
            self.table.removeRow(row)

    def on_delete_all_meta(self):
        self.table.setRowCount(0)

    def on_save_meta(self):
        new_attrs = {}
        for r in range(self.table.rowCount()):
            k_item, v_item = self.table.item(r, 0), self.table.item(r, 1)
            if k_item and v_item:
                new_attrs[k_item.text()] = v_item.text()
        try:
            for k in self.original_xattrs:
                if k not in new_attrs:
                    XattrManager.set_attribute(self.path, k, None)
            for k, v in new_attrs.items():
                XattrManager.set_attribute(self.path, k, v)
            self.reload_metadata()
        except Exception as e:
            QMessageBox.critical(self, UITexts.ERROR, str(e))

    def on_cancel_meta(self):
        self.update_metadata_table(self.original_xattrs)

    def on_add_exif(self):
        key, ok = QInputDialog.getText(
            self, UITexts.PROPERTIES_ADD_ATTR, UITexts.PROPERTIES_ADD_ATTR_NAME)
        if ok and key:
            row = self.exif_table.rowCount()
            self.exif_table.insertRow(row)
            self.exif_table.setItem(row, 0, QTableWidgetItem(key))
            v_item = QTableWidgetItem("")
            self.exif_table.setItem(row, 1, v_item)
            self.exif_table.setCurrentItem(v_item)
            self.exif_table.editItem(v_item)

    def on_delete_exif(self):
        rows = sorted(
            set(index.row() for index in self.exif_table.selectedIndexes()),
            reverse=True)
        for row in rows:
            self.exif_table.removeRow(row)

    def on_delete_all_exif(self):
        self.exif_table.setRowCount(0)

    def on_save_exif(self):
        new_exif = {}
        for r in range(self.exif_table.rowCount()):
            k_item, v_item = self.exif_table.item(r, 0), self.exif_table.item(r, 1)
            if k_item and v_item:
                new_exif[k_item.text()] = v_item.text()
        try:
            MetadataManager.write_metadata(self.path, new_exif)
            self.reload_metadata()
        except Exception as e:
            QMessageBox.critical(self, UITexts.ERROR, str(e))

    def on_cancel_exif(self):
        self.update_exif_table(self.original_exif)

    def done(self, r):
        if self.loader and self.loader.isRunning():
            self.loader.stop()
        super().done(r)

    def closeEvent(self, event):
        if self.loader and self.loader.isRunning():
            self.loader.stop()
        super().closeEvent(event)

    def update_metadata_table(self, disk_xattrs, initial_only=False):
        """
        Updates the metadata table with extended attributes.
        Merges initial tags/rating with loaded xattrs.
        """
        self.table.blockSignals(True)
        self.table.setRowCount(0)

        # Use pre-loaded tags and rating if available
        preloaded_xattrs = {}
        if self._initial_tags:
            preloaded_xattrs[XATTR_NAME] = ", ".join(self._initial_tags)
        if self._initial_rating > 0:
            preloaded_xattrs[RATING_XATTR_NAME] = str(self._initial_rating)

        # Combine preloaded and newly read xattrs
        all_xattrs = preloaded_xattrs.copy()
        if not initial_only and disk_xattrs:
            self.original_xattrs = disk_xattrs.copy()
            # Disk data takes precedence or adds to it
            all_xattrs.update(disk_xattrs)

        self.table.setRowCount(len(all_xattrs))

        row = 0
        # Display all xattrs
        for key, val in all_xattrs.items():
            # QImageReader.textKeys() is not used here as it's not xattr.
            k_item = QTableWidgetItem(key)
            k_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable)
            v_item = QTableWidgetItem(val)
            v_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable)
            self.table.setItem(row, 0, k_item)
            self.table.setItem(row, 1, v_item)
            row += 1
        self.table.blockSignals(False)

    def reload_metadata(self):
        """Starts the background thread to load metadata."""
        if self.loader and self.loader.isRunning():
            # Already running
            return
        self.loader = PropertiesLoader(self.path, self)
        self.loader.loaded.connect(self.on_data_loaded)
        self.loader.start()

    def on_data_loaded(self, xattrs, exif_data):
        """Slot called when metadata is loaded from the thread."""
        self.update_metadata_table(xattrs, initial_only=False)
        self.update_exif_table(exif_data)

    def update_exif_table(self, exif_data):
        """Updates the EXIF table with loaded data."""
        self.exif_table.blockSignals(True)
        self.exif_table.setRowCount(0)

        if exif_data is None:
            # Loading state
            self.exif_table.setRowCount(1)
            item = QTableWidgetItem(UITexts.LOADING_DATA)
            item.setFlags(Qt.ItemIsEnabled)
            self.exif_table.setItem(0, 0, item)
            self.exif_table.blockSignals(False)
            return

        if not HAVE_EXIV2:
            self.exif_table.setRowCount(1)
            error_color = QColor("red")
            item = QTableWidgetItem(UITexts.ERROR)
            item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            item.setForeground(error_color)
            self.exif_table.setItem(0, 0, item)
            msg_item = QTableWidgetItem(UITexts.EXIV2_NOT_INSTALLED)
            msg_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            msg_item.setForeground(error_color)
            self.exif_table.setItem(0, 1, msg_item)
            self.exif_table.blockSignals(False)
            return

        if not exif_data:
            self.exif_table.setRowCount(1)
            item = QTableWidgetItem(UITexts.INFO)
            item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            self.exif_table.setItem(0, 0, item)
            msg_item = QTableWidgetItem(UITexts.NO_METADATA_FOUND)
            msg_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            self.exif_table.setItem(0, 1, msg_item)
            self.exif_table.blockSignals(False)
            return

        self.original_exif = exif_data.copy()
        self.exif_table.setRowCount(len(exif_data))
        error_color = QColor("red")
        error_text_lower = UITexts.ERROR.lower()
        warning_text_lower = UITexts.WARNING.lower()

        for row, (key, value) in enumerate(sorted(exif_data.items())):
            k_item = QTableWidgetItem(str(key))
            k_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable)
            v_item = QTableWidgetItem(str(value))
            v_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable)

            key_str_lower = str(key).lower()
            val_str_lower = str(value).lower()
            if (error_text_lower in key_str_lower or warning_text_lower
                in key_str_lower or
                    error_text_lower in val_str_lower
                    or warning_text_lower in val_str_lower):
                k_item.setForeground(error_color)
                v_item.setForeground(error_color)

            self.exif_table.setItem(row, 0, k_item)
            self.exif_table.setItem(row, 1, v_item)

        self.exif_table.blockSignals(False)

    def show_context_menu(self, pos):
        """
        Displays a context menu in the metadata table.

        Args:
            pos (QPoint): The position where the context menu was requested.
        """
        menu = QMenu()
        add_action = menu.addAction(QIcon.fromTheme("list-add"),
                                    UITexts.PROPERTIES_ADD_ATTR)

        item = self.table.itemAt(pos)
        copy_action = None
        delete_action = None

        if item:
            copy_action = menu.addAction(QIcon.fromTheme("edit-copy"),
                                         UITexts.COPY)
            val_item = self.table.item(item.row(), 1)
            if val_item.flags() & Qt.ItemIsEditable:
                delete_action = menu.addAction(QIcon.fromTheme("list-remove"),
                                               UITexts.PROPERTIES_DELETE_ATTR)

        action = menu.exec(self.table.mapToGlobal(pos))
        if action == add_action:
            self.add_attribute()
        elif copy_action and action == copy_action:
            val = self.table.item(item.row(), 1).text()
            QApplication.clipboard().setText(val)
        elif delete_action and action == delete_action:
            self.delete_attribute(item.row())

    def show_exif_context_menu(self, pos):
        """Displays a context menu in the EXIF table (Copy only)."""
        menu = QMenu()
        item = self.exif_table.itemAt(pos)
        if item:
            copy_action = menu.addAction(QIcon.fromTheme("edit-copy"), UITexts.COPY)
            action = menu.exec(self.exif_table.mapToGlobal(pos))
            if action == copy_action:
                val = self.exif_table.item(item.row(), 1).text()
                QApplication.clipboard().setText(val)

    def add_attribute(self):
        """
        Opens dialogs to get a key and value for a new extended attribute and applies
        it.
        """
        key, ok = QInputDialog.getText(self, UITexts.PROPERTIES_ADD_ATTR,
                                       UITexts.PROPERTIES_ADD_ATTR_NAME)
        if ok and key:
            val, ok2 = QInputDialog.getText(self, UITexts.PROPERTIES_ADD_ATTR,
                                            UITexts.PROPERTIES_ADD_ATTR_VALUE.format(
                                                key))
            if ok2:
                try:
                    XattrManager.set_attribute(self.path, key, val)
                    self.reload_metadata()
                except Exception as e:
                    QMessageBox.warning(self, UITexts.ERROR,
                                        UITexts.PROPERTIES_ERROR_ADD_ATTR.format(e))

    def delete_attribute(self, row):
        """
        Deletes the extended attribute corresponding to the given table row.

        Args:
            row (int): The row index of the attribute to delete.
        """
        key = self.table.item(row, 0).text()
        try:
            XattrManager.set_attribute(self.path, key, None)
            self.table.removeRow(row)
        except Exception as e:
            QMessageBox.warning(self, UITexts.ERROR,
                                UITexts.PROPERTIES_ERROR_DELETE_ATTR.format(e))

    def format_size(self, size):
        """
        Formats a size in bytes into a human-readable string (B, KiB, MiB, etc.).

        Args:
            size (int): The size in bytes.

        Returns:
            str: The formatted size string.
        """
        for unit in ['B', 'KiB', 'MiB', 'GiB']:
            if size < 1024:
                return f"{size:.2f} {unit}"
            size /= 1024
        return f"{size:.2f} TiB"
