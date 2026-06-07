"""
Settings Module for Bagheera Image Viewer.

This module provides the main configuration dialog for the application,
allowing users to customize various aspects of its behavior, such as scanner
settings, face detection options, and thumbnail appearance.

Classes:
    ModelDownloader: A QThread worker for downloading the MediaPipe model file.
    SettingsDialog: The main QDialog that presents all configurable options
                    in a tabbed interface.
"""
import os
import shutil
import urllib.request

from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtGui import QColor, QIcon, QFont
from PySide6.QtWidgets import (
    QCheckBox, QColorDialog, QComboBox, QDialog, QDialogButtonBox,
    QHBoxLayout, QInputDialog, QLabel, QLineEdit, QMessageBox,
    QProgressDialog, QPushButton, QSpinBox, QTabWidget, QVBoxLayout,
    QWidget, QSlider, QFileDialog, QListWidget, QListView, QAbstractItemView,
    QListWidgetItem, QProgressBar
)
from .constants import (
    APP_CONFIG, AVAILABLE_FACE_ENGINES, DEFAULT_FACE_BOX_COLOR,
    DEFAULT_PET_BOX_COLOR, DEFAULT_OBJECT_BOX_COLOR, DEFAULT_LANDMARK_BOX_COLOR,
    FACES_MENU_MAX_ITEMS_DEFAULT, MEDIAPIPE_FACE_MODEL_PATH, MEDIAPIPE_FACE_MODEL_URL,
    AVAILABLE_PET_ENGINES, DEFAULT_BODY_BOX_COLOR,
    MEDIAPIPE_OBJECT_MODEL_PATH, MEDIAPIPE_OBJECT_MODEL_URL,
    HAVE_BAGHEERASEARCH_LIB, IMAGE_EXTENSIONS,
    SCANNER_SETTINGS_DEFAULTS, SEARCH_CMD, TAGS_MENU_MAX_ITEMS_DEFAULT,
    THUMBNAILS_FILENAME_LINES_DEFAULT,
    THUMBNAILS_REFRESH_INTERVAL_DEFAULT, THUMBNAILS_BG_COLOR_DEFAULT,
    THUMBNAILS_FILENAME_COLOR_DEFAULT, THUMBNAILS_TAGS_COLOR_DEFAULT,
    THUMBNAILS_RATING_COLOR_DEFAULT, THUMBNAILS_TOOLTIP_BG_COLOR_DEFAULT,
    THUMBNAILS_TOOLTIP_FG_COLOR_DEFAULT, THUMBNAILS_FILENAME_FONT_SIZE_DEFAULT,
    THUMBNAILS_TAGS_LINES_DEFAULT, THUMBNAILS_TAGS_FONT_SIZE_DEFAULT,
    VIEWER_AUTO_RESIZE_WINDOW_DEFAULT, VIEWER_WHEEL_SPEED_DEFAULT,
    UITexts, save_app_config, HAVE_DUPLICATE_RESNET_LIBS, HAVE_IMAGEHASH
)


class DuplicateFileCounter(QThread):
    """Thread to count images in whitelist/blacklist without freezing UI."""
    count_updated = Signal(int)
    finished = Signal(int)

    def __init__(self, whitelist, blacklist, extensions):
        super().__init__()
        self.whitelist = whitelist
        self.blacklist = blacklist
        self.extensions = extensions
        self._abort = False

    def stop(self):
        self._abort = True
        self.wait()

    def run(self):
        count = 0
        for root_path in self.whitelist:
            if self._abort:
                break
            if not os.path.exists(root_path):
                continue
            for root, dirs, files in os.walk(root_path):
                if self._abort:
                    break
                abs_root = os.path.abspath(root)
                dirs[:] = [d for d in dirs
                           if os.path.join(abs_root, d) not in self.blacklist]
                if abs_root in self.blacklist:
                    continue
                for f in files:
                    if self._abort:
                        break
                    if os.path.splitext(f)[1].lower() in self.extensions:
                        if os.path.join(abs_root, f) not in self.blacklist:
                            count += 1
                self.count_updated.emit(count)
        self.finished.emit(count)


class PathListWidget(QListWidget):
    """A QListWidget that accepts folder drops from external file explorers."""
    def __init__(self, add_callback, parent=None):
        super().__init__(parent)
        self.add_callback = add_callback
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path and os.path.isdir(path):
                self.add_callback(self, path)
        event.acceptProposedAction()


class ModelDownloader(QThread):
    """A thread to download the MediaPipe model file without freezing the UI."""
    download_complete = Signal(bool, str)  # success (bool), message (str)

    def __init__(self, url, dest_path, parent=None):
        super().__init__(parent)
        self.url = url
        self.dest_path = dest_path

    def run(self):
        try:
            os.makedirs(os.path.dirname(self.dest_path), exist_ok=True)
            with urllib.request.urlopen(self.url) as response, \
                 open(self.dest_path, 'wb') as out_file:
                shutil.copyfileobj(response, out_file)
            self.download_complete.emit(True, "")
        except Exception as e:
            if os.path.exists(self.dest_path):
                os.remove(self.dest_path)
            self.download_complete.emit(False, str(e))


class SettingsDialog(QDialog):
    """A dialog to configure application settings."""

    def __init__(self, parent=None):
        """Initializes the settings dialog window.

        This sets up the tabbed interface and all the individual configuration
        widgets for scanner, faces, thumbnails, and viewer settings.

        Args:
            parent (QWidget, optional): The parent widget. Defaults to None.
        """

        super().__init__(parent)
        self.setWindowTitle(UITexts.MENU_SETTINGS)
        self.setMinimumWidth(500)
        self.scan_max_level_min = 0
        self.scan_max_level_max = 10

        self.current_face_color = DEFAULT_FACE_BOX_COLOR
        self.current_pet_color = DEFAULT_PET_BOX_COLOR
        self.current_body_color = DEFAULT_BODY_BOX_COLOR
        self.current_object_color = DEFAULT_OBJECT_BOX_COLOR
        self.current_landmark_color = DEFAULT_LANDMARK_BOX_COLOR
        self.current_thumbs_bg_color = THUMBNAILS_BG_COLOR_DEFAULT
        self.current_thumbs_filename_color = THUMBNAILS_FILENAME_COLOR_DEFAULT
        self.current_thumbs_tags_color = THUMBNAILS_TAGS_COLOR_DEFAULT
        self.current_thumbs_rating_color = THUMBNAILS_RATING_COLOR_DEFAULT
        self.current_thumbs_tooltip_bg_color = THUMBNAILS_TOOLTIP_BG_COLOR_DEFAULT
        self.current_thumbs_tooltip_fg_color = THUMBNAILS_TOOLTIP_FG_COLOR_DEFAULT
        self.downloader_thread = None
        self.counter_thread = None

        layout = QVBoxLayout(self)

        tabs = QTabWidget()
        layout.addWidget(tabs)

        # --- Create all tabs and layouts first ---
        thumbs_tab = QWidget()
        thumbs_layout = QVBoxLayout(thumbs_tab)

        viewer_tab = QWidget()
        viewer_layout = QVBoxLayout(viewer_tab)

        quick_tags_tab = QWidget()
        quick_tags_layout = QVBoxLayout(quick_tags_tab)

        faces_tab = QWidget()
        faces_layout = QVBoxLayout(faces_tab)

        scanner_tab = QWidget()
        scanner_layout = QVBoxLayout(scanner_tab)

        duplicates_tab = QWidget()
        duplicates_layout = QVBoxLayout(duplicates_tab)

        # --- Thumbnails Tab ---

        mru_tags_layout = QHBoxLayout()
        self.mru_tags_spin = QSpinBox()
        self.mru_tags_spin.setRange(5, 100)
        mru_label = QLabel(UITexts.SETTINGS_MRU_TAGS_COUNT_LABEL)
        mru_tags_layout.addWidget(mru_label)
        mru_tags_layout.addWidget(self.mru_tags_spin)
        mru_label.setToolTip(UITexts.SETTINGS_MRU_TAGS_TOOLTIP)
        self.mru_tags_spin.setToolTip(UITexts.SETTINGS_MRU_TAGS_TOOLTIP)
        thumbs_layout.addLayout(mru_tags_layout)

        thumbs_refresh_layout = QHBoxLayout()
        self.thumbs_refresh_spin = QSpinBox()
        self.thumbs_refresh_spin.setRange(50, 1000)
        self.thumbs_refresh_spin.setSingleStep(10)
        self.thumbs_refresh_spin.setSuffix(" ms")
        thumbs_refresh_label = QLabel(UITexts.SETTINGS_THUMBS_REFRESH_LABEL)
        thumbs_refresh_layout.addWidget(thumbs_refresh_label)
        thumbs_refresh_layout.addWidget(self.thumbs_refresh_spin)
        thumbs_refresh_label.setToolTip(UITexts.SETTINGS_THUMBS_REFRESH_TOOLTIP)
        self.thumbs_refresh_spin.setToolTip(UITexts.SETTINGS_THUMBS_REFRESH_TOOLTIP)
        thumbs_layout.addLayout(thumbs_refresh_layout)

        thumbs_bg_color_layout = QHBoxLayout()
        thumbs_bg_color_label = QLabel(UITexts.SETTINGS_THUMBS_BG_COLOR_LABEL)
        self.thumbs_bg_color_btn = QPushButton()
        self.thumbs_bg_color_btn.clicked.connect(self.choose_thumbs_bg_color)
        thumbs_bg_color_layout.addWidget(thumbs_bg_color_label)
        thumbs_bg_color_layout.addWidget(self.thumbs_bg_color_btn)
        thumbs_bg_color_label.setToolTip(UITexts.SETTINGS_THUMBS_BG_COLOR_TOOLTIP)
        self.thumbs_bg_color_btn.setToolTip(UITexts.SETTINGS_THUMBS_BG_COLOR_TOOLTIP)
        thumbs_layout.addLayout(thumbs_bg_color_layout)

        thumbs_filename_color_layout = QHBoxLayout()
        thumbs_filename_color_label = QLabel(
            UITexts.SETTINGS_THUMBS_FILENAME_COLOR_LABEL)
        self.thumbs_filename_color_btn = QPushButton()
        self.thumbs_filename_color_btn.clicked.connect(
            self.choose_thumbs_filename_color)
        thumbs_filename_color_layout.addWidget(thumbs_filename_color_label)
        thumbs_filename_color_layout.addWidget(self.thumbs_filename_color_btn)
        thumbs_filename_color_label.setToolTip(
            UITexts.SETTINGS_THUMBS_FILENAME_COLOR_TOOLTIP)
        self.thumbs_filename_color_btn.setToolTip(
            UITexts.SETTINGS_THUMBS_FILENAME_COLOR_TOOLTIP)
        thumbs_layout.addLayout(thumbs_filename_color_layout)

        thumbs_tags_color_layout = QHBoxLayout()
        thumbs_tags_color_label = QLabel(UITexts.SETTINGS_THUMBS_TAGS_COLOR_LABEL)
        self.thumbs_tags_color_btn = QPushButton()
        self.thumbs_tags_color_btn.clicked.connect(self.choose_thumbs_tags_color)
        thumbs_tags_color_layout.addWidget(thumbs_tags_color_label)
        thumbs_tags_color_layout.addWidget(self.thumbs_tags_color_btn)
        thumbs_tags_color_label.setToolTip(UITexts.SETTINGS_THUMBS_TAGS_COLOR_TOOLTIP)
        self.thumbs_tags_color_btn.setToolTip(
            UITexts.SETTINGS_THUMBS_TAGS_COLOR_TOOLTIP)
        thumbs_layout.addLayout(thumbs_tags_color_layout)

        thumbs_rating_color_layout = QHBoxLayout()
        thumbs_rating_color_label = QLabel(UITexts.SETTINGS_THUMBS_RATING_COLOR_LABEL)
        self.thumbs_rating_color_btn = QPushButton()
        self.thumbs_rating_color_btn.clicked.connect(self.choose_thumbs_rating_color)
        thumbs_rating_color_layout.addWidget(thumbs_rating_color_label)
        thumbs_rating_color_layout.addWidget(self.thumbs_rating_color_btn)
        thumbs_rating_color_label.setToolTip(
            UITexts.SETTINGS_THUMBS_RATING_COLOR_TOOLTIP)
        self.thumbs_rating_color_btn.setToolTip(
            UITexts.SETTINGS_THUMBS_RATING_COLOR_TOOLTIP)
        thumbs_layout.addLayout(thumbs_rating_color_layout)

        filename_font_size_layout = QHBoxLayout()
        self.filename_font_size_spin = QSpinBox()
        self.filename_font_size_spin.setRange(6, 16)
        self.filename_font_size_spin.setSuffix(" pt")
        filename_font_label = QLabel(UITexts.SETTINGS_THUMBS_FILENAME_FONT_SIZE_LABEL)
        filename_font_size_layout.addWidget(filename_font_label)
        filename_font_size_layout.addWidget(self.filename_font_size_spin)
        filename_font_label.setToolTip(
            UITexts.SETTINGS_THUMBS_FILENAME_FONT_SIZE_TOOLTIP)
        self.filename_font_size_spin.setToolTip(
            UITexts.SETTINGS_THUMBS_FILENAME_FONT_SIZE_TOOLTIP)
        thumbs_layout.addLayout(filename_font_size_layout)

        tags_font_size_layout = QHBoxLayout()
        self.tags_font_size_spin = QSpinBox()
        self.tags_font_size_spin.setRange(6, 16)
        self.tags_font_size_spin.setSuffix(" pt")
        tags_font_label = QLabel(UITexts.SETTINGS_THUMBS_TAGS_FONT_SIZE_LABEL)
        tags_font_size_layout.addWidget(tags_font_label)
        tags_font_size_layout.addWidget(self.tags_font_size_spin)
        tags_font_label.setToolTip(UITexts.SETTINGS_THUMBS_TAGS_FONT_SIZE_TOOLTIP)
        self.tags_font_size_spin.setToolTip(
            UITexts.SETTINGS_THUMBS_TAGS_FONT_SIZE_TOOLTIP)
        thumbs_layout.addLayout(tags_font_size_layout)

        # --- Thumbs Tooltip Background Color ---
        thumbs_tooltip_bg_color_layout = QHBoxLayout()
        thumbs_tooltip_bg_color_label = QLabel(
            UITexts.SETTINGS_THUMBS_TOOLTIP_BG_COLOR_LABEL)
        self.thumbs_tooltip_bg_color_btn = QPushButton()
        self.thumbs_tooltip_bg_color_btn.clicked.connect(
            self.choose_thumbs_tooltip_bg_color)
        thumbs_tooltip_bg_color_layout.addWidget(thumbs_tooltip_bg_color_label)
        thumbs_tooltip_bg_color_layout.addWidget(self.thumbs_tooltip_bg_color_btn)
        thumbs_tooltip_bg_color_label.setToolTip(
            UITexts.SETTINGS_THUMBS_TOOLTIP_BG_COLOR_TOOLTIP)
        self.thumbs_tooltip_bg_color_btn.setToolTip(
            UITexts.SETTINGS_THUMBS_TOOLTIP_BG_COLOR_TOOLTIP)
        thumbs_layout.addLayout(thumbs_tooltip_bg_color_layout)

        # --- Thumbs Tooltip Foreground Color ---
        thumbs_tooltip_fg_color_layout = QHBoxLayout()
        thumbs_tooltip_fg_color_label = QLabel(
            UITexts.SETTINGS_THUMBS_TOOLTIP_FG_COLOR_LABEL)
        self.thumbs_tooltip_fg_color_btn = QPushButton()
        self.thumbs_tooltip_fg_color_btn.clicked.connect(
            self.choose_thumbs_tooltip_fg_color)
        thumbs_tooltip_fg_color_layout.addWidget(thumbs_tooltip_fg_color_label)
        thumbs_tooltip_fg_color_layout.addWidget(self.thumbs_tooltip_fg_color_btn)
        thumbs_tooltip_fg_color_label.setToolTip(
            UITexts.SETTINGS_THUMBS_TOOLTIP_FG_COLOR_TOOLTIP)
        self.thumbs_tooltip_fg_color_btn.setToolTip(
            UITexts.SETTINGS_THUMBS_TOOLTIP_FG_COLOR_TOOLTIP)
        thumbs_layout.addLayout(thumbs_tooltip_fg_color_layout)

        show_filename_layout = QHBoxLayout()
        self.show_filename_check = QCheckBox(
            UITexts.SETTINGS_THUMBS_SHOW_FILENAME_LABEL)
        self.show_filename_check.setToolTip(
            UITexts.SETTINGS_THUMBS_SHOW_FILENAME_TOOLTIP)
        show_filename_layout.addWidget(self.show_filename_check)
        thumbs_layout.addLayout(show_filename_layout)

        show_rating_layout = QHBoxLayout()
        self.show_rating_check = QCheckBox(UITexts.SETTINGS_THUMBS_SHOW_RATING_LABEL)
        self.show_rating_check.setToolTip(UITexts.SETTINGS_THUMBS_SHOW_RATING_TOOLTIP)
        show_rating_layout.addWidget(self.show_rating_check)
        thumbs_layout.addLayout(show_rating_layout)

        show_tags_layout = QHBoxLayout()
        self.show_tags_check = QCheckBox(UITexts.SETTINGS_THUMBS_SHOW_TAGS_LABEL)
        self.show_tags_check.setToolTip(UITexts.SETTINGS_THUMBS_SHOW_TAGS_TOOLTIP)
        show_tags_layout.addWidget(self.show_tags_check)
        thumbs_layout.addLayout(show_tags_layout)

        filename_lines_layout = QHBoxLayout()
        self.filename_lines_spin = QSpinBox()
        self.filename_lines_spin.setRange(1, 3)
        filename_lines_label = QLabel(UITexts.SETTINGS_THUMBS_FILENAME_LINES_LABEL)
        filename_lines_layout.addWidget(filename_lines_label)
        filename_lines_layout.addWidget(self.filename_lines_spin)
        filename_lines_label.setToolTip(UITexts.SETTINGS_THUMBS_FILENAME_LINES_TOOLTIP)
        self.filename_lines_spin.setToolTip(
            UITexts.SETTINGS_THUMBS_FILENAME_LINES_TOOLTIP)
        thumbs_layout.addLayout(filename_lines_layout)

        tags_lines_layout = QHBoxLayout()
        self.tags_lines_spin = QSpinBox()
        self.tags_lines_spin.setRange(1, 4)
        tags_lines_label = QLabel(UITexts.SETTINGS_THUMBS_TAGS_LINES_LABEL)
        tags_lines_layout.addWidget(tags_lines_label)
        tags_lines_layout.addWidget(self.tags_lines_spin)
        tags_lines_label.setToolTip(UITexts.SETTINGS_THUMBS_TAGS_LINES_TOOLTIP)
        self.tags_lines_spin.setToolTip(UITexts.SETTINGS_THUMBS_TAGS_LINES_TOOLTIP)
        thumbs_layout.addLayout(tags_lines_layout)
        thumbs_layout.addStretch()

        # --- Scanner Tab ---
        scan_max_level_layout = QHBoxLayout()
        scan_max_level_label = QLabel(UITexts.SETTINGS_SCAN_MAX_LEVEL_LABEL)
        self.scan_max_level_spin = QSpinBox()
        self.scan_max_level_spin.setRange(self.scan_max_level_min,
                                          self.scan_max_level_max)
        scan_max_level_layout.addWidget(scan_max_level_label)
        scan_max_level_layout.addWidget(self.scan_max_level_spin)
        scan_max_level_label.setToolTip(UITexts.SETTINGS_SCAN_MAX_LEVEL_TOOLTIP)
        self.scan_max_level_spin.setToolTip(UITexts.SETTINGS_SCAN_MAX_LEVEL_TOOLTIP)
        scanner_layout.addLayout(scan_max_level_layout)

        # --- Search Engine ---
        search_engine_layout = QHBoxLayout()
        search_engine_label = QLabel(UITexts.SETTINGS_SCANNER_SEARCH_ENGINE_LABEL)
        self.search_engine_combo = QComboBox()
        self.search_engine_combo.addItem(UITexts.SEARCH_ENGINE_NATIVE, "Bagheera")
        if SEARCH_CMD:
            self.search_engine_combo.addItem(UITexts.SEARCH_ENGINE_BALOO, "Baloo")

        search_engine_layout.addWidget(search_engine_label)
        search_engine_layout.addWidget(self.search_engine_combo)
        search_engine_label.setToolTip(UITexts.SETTINGS_SCANNER_SEARCH_ENGINE_TOOLTIP)
        self.search_engine_combo.setToolTip(
            UITexts.SETTINGS_SCANNER_SEARCH_ENGINE_TOOLTIP)
        scanner_layout.addLayout(search_engine_layout)

        scan_batch_size_layout = QHBoxLayout()
        scan_batch_size_label = QLabel(UITexts.SETTINGS_SCAN_BATCH_SIZE_LABEL)
        self.scan_batch_size_spin = QSpinBox()
        self.scan_batch_size_spin.setRange(16, 128)
        scan_batch_size_layout.addWidget(scan_batch_size_label)
        scan_batch_size_layout.addWidget(self.scan_batch_size_spin)
        scan_batch_size_label.setToolTip(UITexts.SETTINGS_SCAN_BATCH_SIZE_TOOLTIP)
        self.scan_batch_size_spin.setToolTip(UITexts.SETTINGS_SCAN_BATCH_SIZE_TOOLTIP)
        scanner_layout.addLayout(scan_batch_size_layout)

        scan_full_on_start_layout = QHBoxLayout()
        scan_full_on_start_label = QLabel(UITexts.SETTINGS_SCAN_FULL_ON_START_LABEL)
        self.scan_full_on_start_checkbox = QCheckBox()
        self.scan_full_on_start_checkbox.setText("")

        scan_full_on_start_layout.addWidget(scan_full_on_start_label)
        scan_full_on_start_layout.addStretch()
        scan_full_on_start_layout.addWidget(self.scan_full_on_start_checkbox)
        scan_full_on_start_label.setToolTip(
            UITexts.SETTINGS_SCAN_FULL_ON_START_TOOLTIP)
        self.scan_full_on_start_checkbox.setToolTip(
            UITexts.SETTINGS_SCAN_FULL_ON_START_TOOLTIP)

        # Threads
        threads_layout = QHBoxLayout()
        threads_label = QLabel(UITexts.SETTINGS_SCAN_THREADS_LABEL)
        self.threads_spin = QSpinBox()
        self.threads_spin.setRange(1, 32)
        threads_layout.addWidget(threads_label)
        threads_layout.addWidget(self.threads_spin)
        threads_label.setToolTip(UITexts.SETTINGS_SCAN_THREADS_TOOLTIP)
        self.threads_spin.setToolTip(UITexts.SETTINGS_SCAN_THREADS_TOOLTIP)
        scanner_layout.addLayout(threads_layout)

        scanner_layout.addLayout(scan_full_on_start_layout)
        scanner_layout.addStretch()

        # --- Duplicates Tab ---
        if not HAVE_IMAGEHASH:
            warning_lbl = QLabel(UITexts.SETTINGS_DUPLICATE_MISSING_LIBS)
            warning_lbl.setStyleSheet("color: #e74c3c; font-weight: bold;")
            warning_lbl.setWordWrap(True)
            duplicates_layout.addWidget(warning_lbl)

        method_layout = QHBoxLayout()
        method_label = QLabel(UITexts.SETTINGS_DUPLICATE_METHOD_LABEL)
        self.duplicate_method_combo = QComboBox()
        self.duplicate_method_combo.addItem(
            UITexts.METHOD_HISTOGRAM_HASHING, "histogram_hashing")
        self.duplicate_method_combo.addItem(UITexts.METHOD_RESNET, "resnet")

        self.duplicate_method_combo.setEnabled(HAVE_IMAGEHASH)

        if not HAVE_DUPLICATE_RESNET_LIBS:
            resnet_idx = self.duplicate_method_combo.findData("resnet")
            if resnet_idx != -1:
                item = self.duplicate_method_combo.model().item(resnet_idx)
                if item:
                    item.setEnabled(False)

        method_layout.addWidget(method_label)
        method_layout.addWidget(self.duplicate_method_combo)
        method_label.setToolTip(UITexts.SETTINGS_DUPLICATE_METHOD_TOOLTIP)
        self.duplicate_method_combo.setToolTip(
            UITexts.SETTINGS_DUPLICATE_METHOD_TOOLTIP)
        duplicates_layout.addLayout(method_layout)

        threshold_layout = QHBoxLayout()
        threshold_label = QLabel(UITexts.SETTINGS_DUPLICATE_THRESHOLD_LABEL)
        self.duplicate_threshold_slider = QSlider(Qt.Horizontal)
        self.duplicate_threshold_slider.setRange(50, 100)
        self.duplicate_threshold_value_label = QLabel("0%")

        self.duplicate_threshold_slider.setEnabled(HAVE_IMAGEHASH)
        self.duplicate_threshold_value_label.setFixedWidth(40)

        threshold_layout.addWidget(threshold_label)
        threshold_layout.addWidget(self.duplicate_threshold_slider)
        threshold_layout.addWidget(self.duplicate_threshold_value_label)

        threshold_label.setToolTip(UITexts.SETTINGS_DUPLICATE_THRESHOLD_TOOLTIP)
        self.duplicate_threshold_slider.setToolTip(
            UITexts.SETTINGS_DUPLICATE_THRESHOLD_TOOLTIP)

        self.duplicate_threshold_slider.valueChanged.connect(
            lambda v: self.duplicate_threshold_value_label.setText(f"{v}%"))

        def create_path_list_ui(label_text, tooltip):
            container = QWidget()
            v_layout = QVBoxLayout(container)
            v_layout.setContentsMargins(0, 0, 0, 0)
            v_layout.addWidget(QLabel(label_text))
            h_layout = QHBoxLayout()
            lst = PathListWidget(self._add_path_to_list)
            lst.setToolTip(tooltip)
            lst.setMinimumHeight(100)
            h_layout.addWidget(lst)
            btn_vbox = QVBoxLayout()
            add_btn = QPushButton()
            add_btn.setIcon(QIcon.fromTheme("list-add"))
            add_btn.setFixedWidth(30)
            rem_btn = QPushButton()
            rem_btn.setIcon(QIcon.fromTheme("list-remove"))
            rem_btn.setFixedWidth(30)
            btn_vbox.addWidget(add_btn)
            btn_vbox.addWidget(rem_btn)
            btn_vbox.addStretch()
            h_layout.addLayout(btn_vbox)
            v_layout.addLayout(h_layout)
            return container, lst, add_btn, rem_btn

        # Whitelist
        wl_cont, self.duplicate_whitelist_list, wl_add, wl_rem = create_path_list_ui(
            UITexts.SETTINGS_DUPLICATE_WHITELIST_LABEL,
            UITexts.SETTINGS_DUPLICATE_WHITELIST_TOOLTIP)
        wl_add.clicked.connect(self.add_whitelist_path)
        wl_rem.clicked.connect(self.remove_whitelist_path)
        duplicates_layout.addWidget(wl_cont)

        # Blacklist
        bl_cont, self.duplicate_blacklist_list, bl_add, bl_rem = create_path_list_ui(
            UITexts.SETTINGS_DUPLICATE_BLACKLIST_LABEL,
            UITexts.SETTINGS_DUPLICATE_BLACKLIST_TOOLTIP)
        bl_add.clicked.connect(self.add_blacklist_path)
        bl_rem.clicked.connect(self.remove_blacklist_path)
        duplicates_layout.addWidget(bl_cont)

        # Image Count Layout
        count_layout = QHBoxLayout()
        self.duplicate_scan_count_label = QLabel()
        self.duplicate_scan_count_label.setStyleSheet(
            "color: #3498db; font-weight: bold;")
        self.duplicate_scan_progress = QProgressBar()
        self.duplicate_scan_progress.setRange(0, 0)  # Indeterminate mode
        self.duplicate_scan_progress.setFixedHeight(10)
        self.duplicate_scan_progress.setFixedWidth(100)
        self.duplicate_scan_progress.hide()
        count_layout.addWidget(self.duplicate_scan_count_label)
        count_layout.addWidget(self.duplicate_scan_progress)
        count_layout.addStretch()
        duplicates_layout.addLayout(count_layout)

        # Timer for debounced count update
        self.count_update_timer = QTimer(self)
        self.count_update_timer.setSingleShot(True)
        self.count_update_timer.setInterval(500)
        self.count_update_timer.timeout.connect(self.update_duplicate_scan_count)

        self.duplicate_whitelist_list.model().rowsInserted.connect(
            lambda *args: self.count_update_timer.start())
        self.duplicate_whitelist_list.model().rowsRemoved.connect(
            lambda *args: self.count_update_timer.start())
        self.duplicate_blacklist_list.model().rowsInserted.connect(
            lambda *args: self.count_update_timer.start())
        self.duplicate_blacklist_list.model().rowsRemoved.connect(
            lambda *args: self.count_update_timer.start())

        self.default_delete_to_trash_checkbox = QCheckBox(
            UITexts.SETTINGS_DEFAULT_DELETE_TO_TRASH_LABEL)
        self.default_delete_to_trash_checkbox.setToolTip(
            UITexts.SETTINGS_DEFAULT_DELETE_TO_TRASH_TOOLTIP)
        duplicates_layout.addWidget(self.default_delete_to_trash_checkbox)

        duplicates_layout.addLayout(threshold_layout)

        self.duplicate_confirm_delete_checkbox = QCheckBox(
            UITexts.SETTINGS_DUPLICATE_CONFIRM_DELETE_LABEL)
        self.duplicate_confirm_delete_checkbox.setToolTip(
            UITexts.SETTINGS_DUPLICATE_CONFIRM_DELETE_TOOLTIP)
        duplicates_layout.addWidget(self.duplicate_confirm_delete_checkbox)

        duplicates_layout.addStretch()

        # --- Faces & People Tab ---

        # --- Quick Tags Tab ---
        self.quick_tags_list = QListWidget()
        self.quick_tags_list.setViewMode(QListView.IconMode)
        self.quick_tags_list.setResizeMode(QListView.Adjust)
        self.quick_tags_list.setMovement(QListView.Static)
        self.quick_tags_list.setFlow(QListView.LeftToRight)
        self.quick_tags_list.setWrapping(True)
        self.quick_tags_list.setSpacing(5)
        self.quick_tags_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.quick_tags_list.setStyleSheet("""
            QListWidget::item {
                background-color: #333;
                border-radius: 4px;
                padding: 5px;
                margin: 2px;
            }
            QListWidget::item:selected {
                background-color: #3498db;
            }
        """)
        quick_tags_layout.addWidget(self.quick_tags_list)

        qt_btns_layout = QHBoxLayout()
        self.add_qt_btn = QPushButton(UITexts.CREATE)
        self.add_qt_btn.setIcon(QIcon.fromTheme("list-add"))
        self.add_qt_btn.clicked.connect(self.add_quick_tag)
        self.remove_qt_btn = QPushButton(UITexts.DELETE)
        self.remove_qt_btn.setIcon(QIcon.fromTheme("list-remove"))
        self.remove_qt_btn.clicked.connect(self.remove_quick_tag)
        qt_btns_layout.addWidget(self.add_qt_btn)
        qt_btns_layout.addWidget(self.remove_qt_btn)
        qt_btns_layout.addStretch()
        quick_tags_layout.addLayout(qt_btns_layout)

        regions_tab = QWidget()
        regions_layout = QVBoxLayout(regions_tab)
        regions_layout.setContentsMargins(0, 0, 0, 0)

        self.regions_sub_tabs = QTabWidget()
        regions_layout.addWidget(self.regions_sub_tabs)

        # --- Face Sub-tab ---
        face_sub_tab = QWidget()
        face_sub_layout = QVBoxLayout(face_sub_tab)

        # Person Tags
        person_tags_layout = QHBoxLayout()
        person_tags_label = QLabel(UITexts.SETTINGS_PERSON_TAGS_LABEL)
        self.person_tags_edit = QLineEdit()
        self.person_tags_edit.setPlaceholderText(UITexts.SETTINGS_PLACEHOLDER_TAGS)
        self.person_tags_edit.setClearButtonEnabled(True)
        person_tags_layout.addWidget(person_tags_label)
        person_tags_layout.addWidget(self.person_tags_edit)
        person_tags_label.setToolTip(UITexts.SETTINGS_PERSON_TAGS_TOOLTIP)
        self.person_tags_edit.setToolTip(UITexts.SETTINGS_PERSON_TAGS_TOOLTIP)
        face_sub_layout.addLayout(person_tags_layout)

        if AVAILABLE_FACE_ENGINES:
            face_engine_layout = QHBoxLayout()
            face_engine_label = QLabel(UITexts.SETTINGS_FACE_ENGINE_LABEL)
            self.face_engine_combo = QComboBox()
            self.face_engine_combo.addItems(AVAILABLE_FACE_ENGINES)

            self.download_model_btn = QPushButton(
                UITexts.SETTINGS_DOWNLOAD_MEDIAPIPE_MODEL)
            self.download_model_btn.setIcon(QIcon.fromTheme("download"))
            self.download_model_btn.setToolTip(
                UITexts.SETTINGS_DOWNLOAD_MEDIAPIPE_MODEL_TOOLTIP)
            self.download_model_btn.clicked.connect(self.start_model_download)

            face_engine_layout.addWidget(face_engine_label)
            face_engine_layout.addWidget(self.face_engine_combo, 1)
            face_engine_layout.addWidget(self.download_model_btn)

            face_engine_label.setToolTip(UITexts.SETTINGS_FACE_ENGINE_TOOLTIP)
            self.face_engine_combo.setToolTip(UITexts.SETTINGS_FACE_ENGINE_TOOLTIP)
            face_sub_layout.addLayout(face_engine_layout)
        else:
            self.face_engine_combo = None
            self.download_model_btn = None

        face_color_layout = QHBoxLayout()
        face_color_label = QLabel(UITexts.SETTINGS_FACE_COLOR_LABEL)
        self.face_color_btn = QPushButton()
        self.face_color_btn.clicked.connect(self.choose_face_color)
        face_color_layout.addWidget(face_color_label)
        face_color_layout.addWidget(self.face_color_btn)
        face_color_label.setToolTip(UITexts.SETTINGS_FACE_COLOR_TOOLTIP)
        self.face_color_btn.setToolTip(UITexts.SETTINGS_FACE_COLOR_TOOLTIP)
        face_sub_layout.addLayout(face_color_layout)

        face_history_layout = QHBoxLayout()
        self.face_history_spin = QSpinBox()
        self.face_history_spin.setRange(5, 100)
        face_hist_label = QLabel(UITexts.SETTINGS_FACE_HISTORY_COUNT_LABEL)
        face_history_layout.addWidget(face_hist_label)
        face_history_layout.addWidget(self.face_history_spin)
        face_hist_label.setToolTip(UITexts.SETTINGS_FACE_HISTORY_TOOLTIP)
        self.face_history_spin.setToolTip(UITexts.SETTINGS_FACE_HISTORY_TOOLTIP)
        face_sub_layout.addLayout(face_history_layout)

        self.face_use_last_name_check = QCheckBox(UITexts.SETTINGS_USE_LAST_NAME_LABEL)
        self.face_use_last_name_check.setToolTip(UITexts.SETTINGS_USE_LAST_NAME_TOOLTIP)
        face_sub_layout.addWidget(self.face_use_last_name_check)
        face_sub_layout.addStretch()
        self.regions_sub_tabs.addTab(face_sub_tab, UITexts.TYPE_FACE)

        # --- Pet Sub-tab ---
        pet_sub_tab = QWidget()
        pet_sub_layout = QVBoxLayout(pet_sub_tab)

        pet_tags_layout = QHBoxLayout()
        pet_tags_label = QLabel(UITexts.SETTINGS_PET_TAGS_LABEL)
        self.pet_tags_edit = QLineEdit()
        self.pet_tags_edit.setPlaceholderText(UITexts.SETTINGS_PLACEHOLDER_TAGS)
        self.pet_tags_edit.setClearButtonEnabled(True)
        pet_tags_layout.addWidget(pet_tags_label)
        pet_tags_layout.addWidget(self.pet_tags_edit)
        pet_tags_label.setToolTip(UITexts.SETTINGS_PET_TAGS_TOOLTIP)
        self.pet_tags_edit.setToolTip(UITexts.SETTINGS_PET_TAGS_TOOLTIP)
        pet_sub_layout.addLayout(pet_tags_layout)

        pet_engine_layout = QHBoxLayout()
        pet_engine_label = QLabel(UITexts.SETTINGS_PET_ENGINE_LABEL)
        self.pet_engine_combo = QComboBox()
        self.pet_engine_combo.addItems(AVAILABLE_PET_ENGINES)

        self.download_pet_model_btn = QPushButton(
            UITexts.SETTINGS_DOWNLOAD_MEDIAPIPE_MODEL)
        self.download_pet_model_btn.setIcon(QIcon.fromTheme("download"))
        self.download_pet_model_btn.setToolTip(
            UITexts.SETTINGS_DOWNLOAD_MEDIAPIPE_MODEL_TOOLTIP)
        self.download_pet_model_btn.clicked.connect(self.start_pet_model_download)

        pet_engine_layout.addWidget(pet_engine_label)
        pet_engine_layout.addWidget(self.pet_engine_combo, 1)
        pet_engine_layout.addWidget(self.download_pet_model_btn)
        pet_engine_label.setToolTip(UITexts.SETTINGS_PET_ENGINE_TOOLTIP)
        self.pet_engine_combo.setToolTip(UITexts.SETTINGS_PET_ENGINE_TOOLTIP)
        pet_sub_layout.addLayout(pet_engine_layout)

        pet_color_layout = QHBoxLayout()
        pet_color_label = QLabel(UITexts.SETTINGS_PET_COLOR_LABEL)
        self.pet_color_btn = QPushButton()
        self.pet_color_btn.clicked.connect(self.choose_pet_color)
        pet_color_layout.addWidget(pet_color_label)
        pet_color_layout.addWidget(self.pet_color_btn)
        pet_color_label.setToolTip(UITexts.SETTINGS_PET_COLOR_TOOLTIP)
        self.pet_color_btn.setToolTip(UITexts.SETTINGS_PET_COLOR_TOOLTIP)
        pet_sub_layout.addLayout(pet_color_layout)

        pet_history_layout = QHBoxLayout()
        self.pet_history_spin = QSpinBox()
        self.pet_history_spin.setRange(5, 100)
        pet_hist_label = QLabel(UITexts.SETTINGS_PET_HISTORY_COUNT_LABEL)
        pet_history_layout.addWidget(pet_hist_label)
        pet_history_layout.addWidget(self.pet_history_spin)
        pet_hist_label.setToolTip(UITexts.SETTINGS_PET_HISTORY_TOOLTIP)
        self.pet_history_spin.setToolTip(UITexts.SETTINGS_PET_HISTORY_TOOLTIP)
        pet_sub_layout.addLayout(pet_history_layout)

        self.pet_use_last_name_check = QCheckBox(UITexts.SETTINGS_USE_LAST_NAME_LABEL)
        self.pet_use_last_name_check.setToolTip(UITexts.SETTINGS_USE_LAST_NAME_TOOLTIP)
        pet_sub_layout.addWidget(self.pet_use_last_name_check)
        pet_sub_layout.addStretch()
        self.regions_sub_tabs.addTab(pet_sub_tab, UITexts.TYPE_PET)

        # --- Body Sub-tab ---
        body_sub_tab = QWidget()
        body_sub_layout = QVBoxLayout(body_sub_tab)

        body_tags_layout = QHBoxLayout()
        body_tags_label = QLabel(UITexts.SETTINGS_BODY_TAGS_LABEL)
        self.body_tags_edit = QLineEdit()
        self.body_tags_edit.setPlaceholderText(UITexts.SETTINGS_PLACEHOLDER_TAGS)
        self.body_tags_edit.setClearButtonEnabled(True)
        body_tags_layout.addWidget(body_tags_label)
        body_tags_layout.addWidget(self.body_tags_edit)
        body_tags_label.setToolTip(UITexts.SETTINGS_BODY_TAGS_TOOLTIP)
        self.body_tags_edit.setToolTip(UITexts.SETTINGS_BODY_TAGS_TOOLTIP)
        body_sub_layout.addLayout(body_tags_layout)

        # body_engine_layout = QHBoxLayout()
        # body_engine_label = QLabel(UITexts.SETTINGS_BODY_ENGINE_LABEL)
        # self.body_engine_combo = QComboBox()
        # self.body_engine_combo.addItems(AVAILABLE_BODY_ENGINES)
        # body_engine_layout.addWidget(body_engine_label)
        # body_engine_layout.addWidget(self.body_engine_combo, 1)
        # body_engine_label.setToolTip(UITexts.SETTINGS_BODY_ENGINE_TOOLTIP)
        # self.body_engine_combo.setToolTip(UITexts.SETTINGS_BODY_ENGINE_TOOLTIP)
        # faces_layout.addLayout(body_engine_layout)

        body_color_layout = QHBoxLayout()
        body_color_label = QLabel(UITexts.SETTINGS_BODY_COLOR_LABEL)
        self.body_color_btn = QPushButton()
        self.body_color_btn.clicked.connect(self.choose_body_color)
        body_color_layout.addWidget(body_color_label)
        body_color_layout.addWidget(self.body_color_btn)
        body_color_label.setToolTip(UITexts.SETTINGS_BODY_COLOR_TOOLTIP)
        self.body_color_btn.setToolTip(UITexts.SETTINGS_BODY_COLOR_TOOLTIP)
        body_sub_layout.addLayout(body_color_layout)

        body_history_layout = QHBoxLayout()
        self.body_history_spin = QSpinBox()
        self.body_history_spin.setRange(5, 100)
        body_hist_label = QLabel(UITexts.SETTINGS_BODY_HISTORY_COUNT_LABEL)
        body_history_layout.addWidget(body_hist_label)
        body_history_layout.addWidget(self.body_history_spin)
        body_hist_label.setToolTip(UITexts.SETTINGS_BODY_HISTORY_TOOLTIP)
        self.body_history_spin.setToolTip(UITexts.SETTINGS_BODY_HISTORY_TOOLTIP)
        body_sub_layout.addLayout(body_history_layout)

        self.body_use_last_name_check = QCheckBox(UITexts.SETTINGS_USE_LAST_NAME_LABEL)
        self.body_use_last_name_check.setToolTip(UITexts.SETTINGS_USE_LAST_NAME_TOOLTIP)
        body_sub_layout.addWidget(self.body_use_last_name_check)
        body_sub_layout.addStretch()
        self.regions_sub_tabs.addTab(body_sub_tab, UITexts.TYPE_BODY)

        # --- Object Sub-tab ---
        object_sub_tab = QWidget()
        object_sub_layout = QVBoxLayout(object_sub_tab)

        object_tags_layout = QHBoxLayout()
        object_tags_label = QLabel(UITexts.SETTINGS_OBJECT_TAGS_LABEL)
        self.object_tags_edit = QLineEdit()
        self.object_tags_edit.setPlaceholderText(UITexts.SETTINGS_PLACEHOLDER_TAGS)
        self.object_tags_edit.setClearButtonEnabled(True)
        object_tags_layout.addWidget(object_tags_label)
        object_tags_layout.addWidget(self.object_tags_edit)
        object_tags_label.setToolTip(UITexts.SETTINGS_OBJECT_TAGS_TOOLTIP)
        self.object_tags_edit.setToolTip(UITexts.SETTINGS_OBJECT_TAGS_TOOLTIP)
        object_sub_layout.addLayout(object_tags_layout)

        # object_engine_layout = QHBoxLayout()
        # object_engine_label = QLabel(UITexts.SETTINGS_OBJECT_ENGINE_LABEL)
        # self.object_engine_combo = QComboBox()
        # object_engine_layout.addWidget(object_engine_label)
        # object_engine_layout.addWidget(self.object_engine_combo, 1)
        # object_engine_label.setToolTip(UITexts.SETTINGS_OBJECT_ENGINE_TOOLTIP)
        # self.object_engine_combo.setToolTip(UITexts.SETTINGS_OBJECT_ENGINE_TOOLTIP)
        # faces_layout.addLayout(object_engine_layout)

        object_color_layout = QHBoxLayout()
        object_color_label = QLabel(UITexts.SETTINGS_OBJECT_COLOR_LABEL)
        self.object_color_btn = QPushButton()
        self.object_color_btn.clicked.connect(self.choose_object_color)
        object_color_layout.addWidget(object_color_label)
        object_color_layout.addWidget(self.object_color_btn)
        object_color_label.setToolTip(UITexts.SETTINGS_OBJECT_COLOR_TOOLTIP)
        self.object_color_btn.setToolTip(UITexts.SETTINGS_OBJECT_COLOR_TOOLTIP)
        object_sub_layout.addLayout(object_color_layout)

        object_history_layout = QHBoxLayout()
        self.object_history_spin = QSpinBox()
        self.object_history_spin.setRange(5, 100)
        object_hist_label = QLabel(UITexts.SETTINGS_OBJECT_HISTORY_COUNT_LABEL)
        object_history_layout.addWidget(object_hist_label)
        object_history_layout.addWidget(self.object_history_spin)
        object_hist_label.setToolTip(UITexts.SETTINGS_OBJECT_HISTORY_TOOLTIP)
        self.object_history_spin.setToolTip(UITexts.SETTINGS_OBJECT_HISTORY_TOOLTIP)
        object_sub_layout.addLayout(object_history_layout)

        self.object_use_last_name_check = QCheckBox(
            UITexts.SETTINGS_USE_LAST_NAME_LABEL)
        self.object_use_last_name_check.setToolTip(
            UITexts.SETTINGS_USE_LAST_NAME_TOOLTIP)
        object_sub_layout.addWidget(self.object_use_last_name_check)
        object_sub_layout.addStretch()
        self.regions_sub_tabs.addTab(object_sub_tab, UITexts.TYPE_OBJECT)

        # --- Landmark Sub-tab ---
        landmark_sub_tab = QWidget()
        landmark_sub_layout = QVBoxLayout(landmark_sub_tab)

        landmark_tags_layout = QHBoxLayout()
        landmark_tags_label = QLabel(UITexts.SETTINGS_LANDMARK_TAGS_LABEL)
        self.landmark_tags_edit = QLineEdit()
        self.landmark_tags_edit.setPlaceholderText(UITexts.SETTINGS_PLACEHOLDER_TAGS)
        self.landmark_tags_edit.setClearButtonEnabled(True)
        landmark_tags_layout.addWidget(landmark_tags_label)
        landmark_tags_layout.addWidget(self.landmark_tags_edit)
        landmark_tags_label.setToolTip(UITexts.SETTINGS_LANDMARK_TAGS_TOOLTIP)
        self.landmark_tags_edit.setToolTip(UITexts.SETTINGS_LANDMARK_TAGS_TOOLTIP)
        landmark_sub_layout.addLayout(landmark_tags_layout)

        # landmark_engine_layout = QHBoxLayout()
        # landmark_engine_label = QLabel(UITexts.SETTINGS_LANDMARK_ENGINE_LABEL)
        # self.landmark_engine_combo = QComboBox()
        # landmark_engine_layout.addWidget(landmark_engine_label)
        # landmark_engine_layout.addWidget(self.landmark_engine_combo, 1)
        # landmark_engine_label.setToolTip(UITexts.SETTINGS_LANDMARK_ENGINE_TOOLTIP)
        # self.landmark_engine_combo.setToolTip(UITexts.SETTINGS_LANDMARK_ENGINE_TOOLTIP)
        # faces_layout.addLayout(landmark_engine_layout)

        landmark_color_layout = QHBoxLayout()
        landmark_color_label = QLabel(UITexts.SETTINGS_LANDMARK_COLOR_LABEL)
        self.landmark_color_btn = QPushButton()
        self.landmark_color_btn.clicked.connect(self.choose_landmark_color)
        landmark_color_layout.addWidget(landmark_color_label)
        landmark_color_layout.addWidget(self.landmark_color_btn)
        landmark_color_label.setToolTip(UITexts.SETTINGS_LANDMARK_COLOR_TOOLTIP)
        self.landmark_color_btn.setToolTip(UITexts.SETTINGS_LANDMARK_COLOR_TOOLTIP)
        landmark_sub_layout.addLayout(landmark_color_layout)

        landmark_history_layout = QHBoxLayout()
        self.landmark_history_spin = QSpinBox()
        self.landmark_history_spin.setRange(5, 100)
        landmark_hist_label = QLabel(UITexts.SETTINGS_LANDMARK_HISTORY_COUNT_LABEL)
        landmark_history_layout.addWidget(landmark_hist_label)
        landmark_history_layout.addWidget(self.landmark_history_spin)
        landmark_hist_label.setToolTip(UITexts.SETTINGS_LANDMARK_HISTORY_TOOLTIP)
        self.landmark_history_spin.setToolTip(UITexts.SETTINGS_LANDMARK_HISTORY_TOOLTIP)
        landmark_sub_layout.addLayout(landmark_history_layout)

        self.landmark_use_last_name_check = QCheckBox(
            UITexts.SETTINGS_USE_LAST_NAME_LABEL)
        self.landmark_use_last_name_check.setToolTip(
            UITexts.SETTINGS_USE_LAST_NAME_TOOLTIP)
        landmark_sub_layout.addWidget(self.landmark_use_last_name_check)
        landmark_sub_layout.addStretch()
        self.regions_sub_tabs.addTab(landmark_sub_tab, UITexts.TYPE_LANDMARK)

        # --- General Areas Settings ---
        interface_sub_tab = QWidget()
        interface_sub_layout = QVBoxLayout(interface_sub_tab)
        self.areas_reset_to_face_check = QCheckBox(UITexts.SETTINGS_AREAS_RESET_TO_FACE_LABEL)
        self.areas_reset_to_face_check.setToolTip(UITexts.SETTINGS_AREAS_RESET_TO_FACE_TOOLTIP)
        interface_sub_layout.addWidget(self.areas_reset_to_face_check)
        interface_sub_layout.addStretch()
        self.regions_sub_tabs.addTab(interface_sub_tab, "Interface")

        # --- Viewer Tab ---
        viewer_wheel_layout = QHBoxLayout()
        viewer_wheel_label = QLabel(UITexts.SETTINGS_VIEWER_WHEEL_SPEED_LABEL)
        self.viewer_wheel_spin = QSpinBox()
        self.viewer_wheel_spin.setRange(1, 10)
        viewer_wheel_layout.addWidget(viewer_wheel_label)
        viewer_wheel_layout.addWidget(self.viewer_wheel_spin)
        viewer_wheel_label.setToolTip(UITexts.SETTINGS_VIEWER_WHEEL_SPEED_TOOLTIP)
        self.viewer_wheel_spin.setToolTip(UITexts.SETTINGS_VIEWER_WHEEL_SPEED_TOOLTIP)
        viewer_layout.addLayout(viewer_wheel_layout)

        viewer_auto_resize_layout = QHBoxLayout()
        self.viewer_auto_resize_check = QCheckBox(
            UITexts.SETTINGS_VIEWER_AUTO_RESIZE_LABEL)
        self.viewer_auto_resize_check.setToolTip(
            UITexts.SETTINGS_VIEWER_AUTO_RESIZE_TOOLTIP)
        viewer_auto_resize_layout.addWidget(self.viewer_auto_resize_check)
        viewer_layout.addLayout(viewer_auto_resize_layout)

        filmstrip_pos_layout = QHBoxLayout()
        filmstrip_pos_label = QLabel(UITexts.MENU_FILMSTRIP_POSITION)
        self.filmstrip_pos_combo = QComboBox()
        self.filmstrip_pos_combo.addItems([
            UITexts.FILMSTRIP_BOTTOM,
            UITexts.FILMSTRIP_LEFT,
            UITexts.FILMSTRIP_TOP,
            UITexts.FILMSTRIP_RIGHT
        ])
        filmstrip_pos_layout.addWidget(filmstrip_pos_label)
        filmstrip_pos_layout.addWidget(self.filmstrip_pos_combo)
        filmstrip_pos_label.setToolTip(UITexts.FILMSTRIP_POS_CHANGED_INFO)
        self.filmstrip_pos_combo.setToolTip(UITexts.FILMSTRIP_POS_CHANGED_INFO)
        viewer_layout.addLayout(filmstrip_pos_layout)
        viewer_layout.addStretch()

        # Add tabs in the new order
        tabs.addTab(thumbs_tab, UITexts.SETTINGS_GROUP_THUMBNAILS)
        tabs.addTab(viewer_tab, UITexts.SETTINGS_GROUP_VIEWER)
        tabs.addTab(quick_tags_tab, UITexts.VIEWER_MENU_TAGS)
        tabs.addTab(regions_tab, UITexts.SETTINGS_GROUP_AREAS)
        tabs.addTab(scanner_tab, UITexts.SETTINGS_GROUP_SCANNER)
        tabs.addTab(duplicates_tab, UITexts.SETTINGS_GROUP_DUPLICATES)

        # --- Button Box ---
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        # Load current settings
        self.load_settings()

    def load_settings(self):
        """Loads settings from the application configuration."""
        # Example:
        # theme = APP_CONFIG.get("theme", "System")
        # self.theme_combo.setCurrentText(theme)

        scan_max_level = APP_CONFIG.get(
            "scan_max_level", SCANNER_SETTINGS_DEFAULTS["scan_max_level"])
        scan_batch_size = APP_CONFIG.get(
            "scan_batch_size", SCANNER_SETTINGS_DEFAULTS["scan_batch_size"])
        scan_full_on_start = APP_CONFIG.get(
            "scan_full_on_start", SCANNER_SETTINGS_DEFAULTS["scan_full_on_start"])
        scan_threads = APP_CONFIG.get(
            "generation_threads",
            SCANNER_SETTINGS_DEFAULTS.get("generation_threads", 4))
        search_engine = APP_CONFIG.get(
            "search_engine", SCANNER_SETTINGS_DEFAULTS.get("search_engine", "Native"))
        person_tags = APP_CONFIG.get(
            "person_tags", SCANNER_SETTINGS_DEFAULTS["person_tags"])
        pet_tags = APP_CONFIG.get("pet_tags", "")
        body_tags = APP_CONFIG.get("body_tags", "")
        object_tags = APP_CONFIG.get("object_tags", "")
        landmark_tags = APP_CONFIG.get("landmark_tags", "")

        face_detection_engine = APP_CONFIG.get("face_detection_engine")
        pet_detection_engine = APP_CONFIG.get("pet_detection_engine")
        body_detection_engine = APP_CONFIG.get("body_detection_engine")
        object_detection_engine = APP_CONFIG.get("object_detection_engine")
        landmark_detection_engine = APP_CONFIG.get("landmark_detection_engine")

        face_color = APP_CONFIG.get("face_box_color", DEFAULT_FACE_BOX_COLOR)
        pet_color = APP_CONFIG.get("pet_box_color", DEFAULT_PET_BOX_COLOR)
        body_color = APP_CONFIG.get("body_box_color", DEFAULT_BODY_BOX_COLOR)
        object_color = APP_CONFIG.get("object_box_color", DEFAULT_OBJECT_BOX_COLOR)
        landmark_color = APP_CONFIG.get("landmark_box_color",
                                        DEFAULT_LANDMARK_BOX_COLOR)

        mru_tags_count = APP_CONFIG.get(
            "tags_menu_max_items", TAGS_MENU_MAX_ITEMS_DEFAULT)
        face_history_count = APP_CONFIG.get(
            "faces_menu_max_items", FACES_MENU_MAX_ITEMS_DEFAULT)
        pet_history_count = APP_CONFIG.get(
            "pets_menu_max_items", FACES_MENU_MAX_ITEMS_DEFAULT)
        body_history_count = APP_CONFIG.get(
            "body_menu_max_items", FACES_MENU_MAX_ITEMS_DEFAULT)
        object_history_count = APP_CONFIG.get(
            "object_menu_max_items", FACES_MENU_MAX_ITEMS_DEFAULT)
        landmark_history_count = APP_CONFIG.get(
            "landmark_menu_max_items", FACES_MENU_MAX_ITEMS_DEFAULT)

        face_use_last_name = APP_CONFIG.get("face_use_last_name", False)
        pet_use_last_name = APP_CONFIG.get("pet_use_last_name", False)
        body_use_last_name = APP_CONFIG.get("body_use_last_name", False)
        object_use_last_name = APP_CONFIG.get("object_use_last_name", False)
        landmark_use_last_name = APP_CONFIG.get("landmark_use_last_name", False)
        areas_reset_to_face = APP_CONFIG.get("areas_reset_to_face", False)

        thumbs_refresh_interval = APP_CONFIG.get(
            "thumbnails_refresh_interval", THUMBNAILS_REFRESH_INTERVAL_DEFAULT)
        thumbs_bg_color = APP_CONFIG.get(
            "thumbnails_bg_color", THUMBNAILS_BG_COLOR_DEFAULT)
        thumbs_filename_color = APP_CONFIG.get(
            "thumbnails_filename_color", THUMBNAILS_FILENAME_COLOR_DEFAULT)
        thumbs_tags_color = APP_CONFIG.get(
            "thumbnails_tags_color", THUMBNAILS_TAGS_COLOR_DEFAULT)
        thumbs_rating_color = APP_CONFIG.get("thumbnails_rating_color",
                                             THUMBNAILS_RATING_COLOR_DEFAULT)
        thumbs_tooltip_bg_color = APP_CONFIG.get("thumbnails_tooltip_bg_color",
                                                 THUMBNAILS_TOOLTIP_BG_COLOR_DEFAULT)
        thumbs_tooltip_fg_color = APP_CONFIG.get("thumbnails_tooltip_fg_color",
                                                 THUMBNAILS_TOOLTIP_FG_COLOR_DEFAULT)
        thumbs_filename_font_size = \
            APP_CONFIG.get("thumbnails_filename_font_size",
                           THUMBNAILS_FILENAME_FONT_SIZE_DEFAULT)
        thumbs_tags_font_size = APP_CONFIG.get("thumbnails_tags_font_size",
                                               THUMBNAILS_TAGS_FONT_SIZE_DEFAULT)
        viewer_wheel_speed = APP_CONFIG.get("viewer_wheel_speed",
                                            VIEWER_WHEEL_SPEED_DEFAULT)
        viewer_auto_resize = APP_CONFIG.get("viewer_auto_resize_window",
                                            VIEWER_AUTO_RESIZE_WINDOW_DEFAULT)
        thumbs_filename_lines = APP_CONFIG.get("thumbnails_filename_lines",
                                               THUMBNAILS_FILENAME_LINES_DEFAULT)
        thumbs_tags_lines = APP_CONFIG.get("thumbnails_tags_lines",
                                           THUMBNAILS_TAGS_LINES_DEFAULT)
        show_filename = APP_CONFIG.get("thumbnails_show_filename", True)
        show_rating = APP_CONFIG.get("thumbnails_show_rating", True)
        show_tags = APP_CONFIG.get("thumbnails_show_tags", True)
        filmstrip_position = APP_CONFIG.get("filmstrip_position", "bottom")

        duplicate_method = APP_CONFIG.get("duplicate_method", "histogram_hashing")
        method_idx = self.duplicate_method_combo.findData(duplicate_method)
        if method_idx != -1:
            self.duplicate_method_combo.setCurrentIndex(method_idx)

        duplicate_threshold = APP_CONFIG.get(
            "duplicate_threshold", SCANNER_SETTINGS_DEFAULTS["duplicate_threshold"])
        self.duplicate_threshold_slider.setValue(duplicate_threshold)
        self.duplicate_threshold_value_label.setText(f"{duplicate_threshold}%")

        default_delete_to_trash = APP_CONFIG.get("default_delete_to_trash", True)
        self.default_delete_to_trash_checkbox.setChecked(default_delete_to_trash)

        duplicate_confirm_delete = APP_CONFIG.get("duplicate_confirm_delete", True)
        self.duplicate_confirm_delete_checkbox.setChecked(duplicate_confirm_delete)

        duplicate_whitelist = APP_CONFIG.get(
            "duplicate_whitelist", SCANNER_SETTINGS_DEFAULTS["duplicate_whitelist"])
        for p in [x.strip() for x in duplicate_whitelist.split(",") if x.strip()]:
            self._add_path_to_list(self.duplicate_whitelist_list, p)
        duplicate_blacklist = APP_CONFIG.get(
            "duplicate_blacklist", SCANNER_SETTINGS_DEFAULTS["duplicate_blacklist"])
        for p in [x.strip() for x in duplicate_blacklist.split(",") if x.strip()]:
            self._add_path_to_list(self.duplicate_blacklist_list, p)

        self.scan_max_level_spin.setValue(scan_max_level)
        self.scan_batch_size_spin.setValue(scan_batch_size)
        self.threads_spin.setValue(scan_threads)

        # Set search engine
        if HAVE_BAGHEERASEARCH_LIB:
            self.search_engine_combo.setEnabled(True)
            if search_engine != "Baloo":
                index = self.search_engine_combo.findData("Bagheera")
                if index != -1:
                    self.search_engine_combo.setCurrentIndex(index)
            else:
                index = self.search_engine_combo.findData("Baloo")
                if index != -1:
                    self.search_engine_combo.setCurrentIndex(index)
        else:
            self.search_engine_combo.setEnabled(False)
            if SEARCH_CMD:
                index = self.search_engine_combo.findData("Baloo")
                if index != -1:
                    self.search_engine_combo.setCurrentIndex(index)
            else:
                self.search_engine_combo.setCurrentIndex(-1)

        self.scan_full_on_start_checkbox.setChecked(scan_full_on_start)

        self.person_tags_edit.setText(person_tags)
        self.pet_tags_edit.setText(pet_tags)
        self.body_tags_edit.setText(body_tags)
        self.object_tags_edit.setText(object_tags)
        self.landmark_tags_edit.setText(landmark_tags)

        self.set_button_color(face_color)
        self.set_pet_button_color(pet_color)
        self.set_body_button_color(body_color)
        self.set_object_button_color(object_color)
        self.set_landmark_button_color(landmark_color)

        if self.face_engine_combo and face_detection_engine in AVAILABLE_FACE_ENGINES:
            self.face_engine_combo.setCurrentText(face_detection_engine)

        if self.pet_engine_combo and pet_detection_engine in AVAILABLE_PET_ENGINES:
            self.pet_engine_combo.setCurrentText(pet_detection_engine)

        if body_detection_engine and hasattr(self, "body_detection_engine_combo"):
            self.body_engine_combo.setCurrentText(body_detection_engine)
        if object_detection_engine and hasattr(self, "object_engine_combo"):
            self.object_engine_combo.setCurrentText(object_detection_engine)
        if landmark_detection_engine and hasattr(self, "landmark_engine_combo"):
            self.landmark_engine_combo.setCurrentText(landmark_detection_engine)

        self.mru_tags_spin.setValue(mru_tags_count)
        self.face_history_spin.setValue(face_history_count)
        self.pet_history_spin.setValue(pet_history_count)
        self.body_history_spin.setValue(body_history_count)
        self.object_history_spin.setValue(object_history_count)
        self.landmark_history_spin.setValue(landmark_history_count)

        self.face_use_last_name_check.setChecked(face_use_last_name)
        self.pet_use_last_name_check.setChecked(pet_use_last_name)
        self.body_use_last_name_check.setChecked(body_use_last_name)
        self.object_use_last_name_check.setChecked(object_use_last_name)
        self.landmark_use_last_name_check.setChecked(landmark_use_last_name)
        self.areas_reset_to_face_check.setChecked(areas_reset_to_face)

        self.thumbs_refresh_spin.setValue(thumbs_refresh_interval)
        self.set_thumbs_bg_button_color(thumbs_bg_color)
        self.set_thumbs_filename_button_color(thumbs_filename_color)
        self.set_thumbs_tags_button_color(thumbs_tags_color)
        self.set_thumbs_rating_button_color(thumbs_rating_color)
        self.set_thumbs_tooltip_bg_button_color(thumbs_tooltip_bg_color)
        self.set_thumbs_tooltip_fg_button_color(thumbs_tooltip_fg_color)
        self.filename_font_size_spin.setValue(thumbs_filename_font_size)
        self.tags_font_size_spin.setValue(thumbs_tags_font_size)
        self.viewer_wheel_spin.setValue(viewer_wheel_speed)
        self.viewer_auto_resize_check.setChecked(viewer_auto_resize)
        self.filename_lines_spin.setValue(thumbs_filename_lines)
        self.tags_lines_spin.setValue(thumbs_tags_lines)
        self.show_filename_check.setChecked(show_filename)
        self.show_rating_check.setChecked(show_rating)
        self.show_tags_check.setChecked(show_tags)

        pos_map = {
            'bottom': UITexts.FILMSTRIP_BOTTOM,
            'left': UITexts.FILMSTRIP_LEFT,
            'top': UITexts.FILMSTRIP_TOP,
            'right': UITexts.FILMSTRIP_RIGHT
        }
        self.filmstrip_pos_combo.setCurrentText(
            pos_map.get(filmstrip_position, UITexts.FILMSTRIP_BOTTOM))
        self.update_mediapipe_status()

        mru_tags = APP_CONFIG.get("mru_tags", [])
        self.quick_tags_list.clear()
        for tag in mru_tags:
            self.quick_tags_list.addItem(tag)
        self.update_duplicate_scan_count()

    def set_button_color(self, color_str):
        """Sets the background color of the button and stores the value."""
        self.face_color_btn.setStyleSheet(
            f"background-color: {color_str}; border: 1px solid gray;")
        self.current_face_color = color_str

    def choose_face_color(self):
        """Opens a color picker dialog."""
        color = QColorDialog.getColor(QColor(self.current_face_color), self)
        if color.isValid():
            self.set_button_color(color.name())

    def set_pet_button_color(self, color_str):
        """Sets the background color of the pet button and stores the value."""
        self.pet_color_btn.setStyleSheet(
            f"background-color: {color_str}; border: 1px solid gray;")
        self.current_pet_color = color_str

    def choose_pet_color(self):
        """Opens a color picker dialog for pet box."""
        color = QColorDialog.getColor(QColor(self.current_pet_color), self)
        if color.isValid():
            self.set_pet_button_color(color.name())

    def set_body_button_color(self, color_str):
        """Sets the background color of the body button and stores the value."""
        self.body_color_btn.setStyleSheet(
            f"background-color: {color_str}; border: 1px solid gray;")
        self.current_body_color = color_str

    def choose_body_color(self):
        """Opens a color picker dialog for body box."""
        color = QColorDialog.getColor(QColor(self.current_body_color), self)
        if color.isValid():
            self.set_body_button_color(color.name())

    def set_object_button_color(self, color_str):
        """Sets the background color of the object button."""
        self.object_color_btn.setStyleSheet(
            f"background-color: {color_str}; border: 1px solid gray;")
        self.current_object_color = color_str

    def choose_object_color(self):
        """Opens a color picker dialog for object box."""
        color = QColorDialog.getColor(QColor(self.current_object_color), self)
        if color.isValid():
            self.set_object_button_color(color.name())

    def set_landmark_button_color(self, color_str):
        """Sets the background color of the landmark button."""
        self.landmark_color_btn.setStyleSheet(
            f"background-color: {color_str}; border: 1px solid gray;")
        self.current_landmark_color = color_str

    def choose_landmark_color(self):
        """Opens a color picker dialog for landmark box."""
        color = QColorDialog.getColor(QColor(self.current_landmark_color), self)
        if color.isValid():
            self.set_landmark_button_color(color.name())

    def set_thumbs_bg_button_color(self, color_str):
        """Sets the background color of the button and stores the value."""
        self.thumbs_bg_color_btn.setStyleSheet(
            f"background-color: {color_str}; border: 1px solid gray;")
        self.current_thumbs_bg_color = color_str

    def choose_thumbs_bg_color(self):
        """Opens a color picker dialog."""
        color = QColorDialog.getColor(QColor(self.current_thumbs_bg_color), self)
        if color.isValid():
            self.set_thumbs_bg_button_color(color.name())

    def set_thumbs_filename_button_color(self, color_str):
        """Sets the background color of the button and stores the value."""
        self.thumbs_filename_color_btn.setStyleSheet(
            f"background-color: {color_str}; border: 1px solid gray;")
        self.current_thumbs_filename_color = color_str

    def choose_thumbs_filename_color(self):
        """Opens a color picker dialog."""
        color = QColorDialog.getColor(QColor(self.current_thumbs_filename_color), self)
        if color.isValid():
            self.set_thumbs_filename_button_color(color.name())

    def set_thumbs_tags_button_color(self, color_str):
        """Sets the background color of the button and stores the value."""
        self.thumbs_tags_color_btn.setStyleSheet(
            f"background-color: {color_str}; border: 1px solid gray;")
        self.current_thumbs_tags_color = color_str

    def choose_thumbs_tags_color(self):
        """Opens a color picker dialog."""
        color = QColorDialog.getColor(QColor(self.current_thumbs_tags_color), self)
        if color.isValid():
            self.set_thumbs_tags_button_color(color.name())

    def set_thumbs_rating_button_color(self, color_str):
        """Sets the background color of the button and stores the value."""
        self.thumbs_rating_color_btn.setStyleSheet(
            f"background-color: {color_str}; border: 1px solid gray;")
        self.current_thumbs_rating_color = color_str

    def choose_thumbs_rating_color(self):
        """Opens a color picker dialog."""
        color = QColorDialog.getColor(QColor(self.current_thumbs_rating_color), self)
        if color.isValid():
            self.set_thumbs_rating_button_color(color.name())

    def set_thumbs_tooltip_fg_button_color(self, color_str):
        """Sets the background color of the button and stores the value."""
        self.thumbs_tooltip_fg_color_btn.setStyleSheet(
            f"background-color: {color_str}; border: 1px solid gray;")
        self.current_thumbs_tooltip_fg_color = color_str

    def choose_thumbs_tooltip_fg_color(self):
        """Opens a color picker dialog."""
        color = QColorDialog.getColor(
            QColor(self.current_thumbs_tooltip_fg_color), self)
        if color.isValid():
            self.set_thumbs_tooltip_fg_button_color(color.name())

    def set_thumbs_tooltip_bg_button_color(self, color_str):
        """Sets the background color of the button and stores the value."""
        self.thumbs_tooltip_bg_color_btn.setStyleSheet(
            f"background-color: {color_str}; border: 1px solid gray;")
        self.current_thumbs_tooltip_bg_color = color_str

    def choose_thumbs_tooltip_bg_color(self):
        """Opens a color picker dialog."""
        color = QColorDialog.getColor(
            QColor(self.current_thumbs_tooltip_bg_color), self)
        if color.isValid():
            self.set_thumbs_tooltip_bg_button_color(color.name())

    def update_mediapipe_status(self):
        """Checks for MediaPipe model file and updates UI accordingly."""
        # --- Faces ---
        if self.face_engine_combo and "mediapipe" in AVAILABLE_FACE_ENGINES:
            model_exists = os.path.exists(MEDIAPIPE_FACE_MODEL_PATH)
            mediapipe_index = self.face_engine_combo.findText("mediapipe")

            if mediapipe_index != -1:
                item = self.face_engine_combo.model().item(mediapipe_index)
                if item:
                    item.setEnabled(model_exists)

            if self.download_model_btn:
                self.download_model_btn.setVisible(not model_exists)

            if self.face_engine_combo.currentText() == "mediapipe" and not model_exists:
                for i in range(self.face_engine_combo.count()):
                    if self.face_engine_combo.model().item(i).isEnabled():
                        self.face_engine_combo.setCurrentIndex(i)
                        break
        elif self.download_model_btn:
            self.download_model_btn.hide()

        # --- Pets ---
        if not AVAILABLE_PET_ENGINES:
            self.pet_engine_combo.setEnabled(False)
            self.pet_tags_edit.setEnabled(False)
            self.pet_history_spin.setEnabled(False)
            self.pet_color_btn.setEnabled(False)
            if self.download_pet_model_btn:
                self.download_pet_model_btn.hide()
        elif "mediapipe" in AVAILABLE_PET_ENGINES:
            pet_model_exists = os.path.exists(MEDIAPIPE_OBJECT_MODEL_PATH)
            if self.download_pet_model_btn:
                self.download_pet_model_btn.setVisible(not pet_model_exists)
        elif self.download_pet_model_btn:
            self.download_pet_model_btn.hide()

    def start_model_download(self):
        """Starts the background thread to download the MediaPipe model."""
        self.downloader_thread = ModelDownloader(
            MEDIAPIPE_FACE_MODEL_URL, MEDIAPIPE_FACE_MODEL_PATH, self)
        self.downloader_thread.download_complete.connect(self.on_download_finished)
        self.downloader_thread.finished.connect(self._on_downloader_finished)

        self.progress_dialog = QProgressDialog(
            UITexts.MEDIAPIPE_DOWNLOADING_TEXT, UITexts.CANCEL, 0, 0, self)
        self.progress_dialog.setWindowTitle(UITexts.MEDIAPIPE_DOWNLOADING_TITLE)
        self.progress_dialog.setWindowModality(Qt.WindowModal)
        self.progress_dialog.show()

        self.downloader_thread.start()

    def start_pet_model_download(self):
        """Starts the background thread to download the MediaPipe Object model."""
        self.downloader_thread = ModelDownloader(
            MEDIAPIPE_OBJECT_MODEL_URL, MEDIAPIPE_OBJECT_MODEL_PATH, self)
        self.downloader_thread.download_complete.connect(self.on_download_finished)
        self.downloader_thread.finished.connect(self._on_downloader_finished)

        self.progress_dialog = QProgressDialog(
            UITexts.MEDIAPIPE_DOWNLOADING_TEXT, UITexts.CANCEL, 0, 0, self)
        self.progress_dialog.setWindowTitle(UITexts.MEDIAPIPE_DOWNLOADING_TITLE)
        self.progress_dialog.setWindowModality(Qt.WindowModal)
        self.progress_dialog.show()

        self.downloader_thread.start()

    def accept(self):
        """Saves settings and closes the dialog."""
        APP_CONFIG["scan_max_level"] = self.scan_max_level_spin.value()
        APP_CONFIG["generation_threads"] = self.threads_spin.value()
        APP_CONFIG["scan_batch_size"] = self.scan_batch_size_spin.value()
        if HAVE_BAGHEERASEARCH_LIB:
            APP_CONFIG["search_engine"] = self.search_engine_combo.currentData()
        APP_CONFIG["scan_full_on_start"] = self.scan_full_on_start_checkbox.isChecked()
        APP_CONFIG["person_tags"] = self.person_tags_edit.text()
        APP_CONFIG["pet_tags"] = self.pet_tags_edit.text()
        APP_CONFIG["body_tags"] = self.body_tags_edit.text()
        APP_CONFIG["object_tags"] = self.object_tags_edit.text()
        APP_CONFIG["landmark_tags"] = self.landmark_tags_edit.text()
        APP_CONFIG["face_box_color"] = self.current_face_color
        APP_CONFIG["pet_box_color"] = self.current_pet_color
        APP_CONFIG["body_box_color"] = self.current_body_color
        APP_CONFIG["object_box_color"] = self.current_object_color
        APP_CONFIG["landmark_box_color"] = self.current_landmark_color
        APP_CONFIG["tags_menu_max_items"] = self.mru_tags_spin.value()
        APP_CONFIG["faces_menu_max_items"] = self.face_history_spin.value()
        APP_CONFIG["pets_menu_max_items"] = self.pet_history_spin.value()
        APP_CONFIG["body_menu_max_items"] = self.body_history_spin.value()
        APP_CONFIG["object_menu_max_items"] = self.object_history_spin.value()
        APP_CONFIG["landmark_menu_max_items"] = self.landmark_history_spin.value()

        APP_CONFIG["thumbnails_refresh_interval"] = self.thumbs_refresh_spin.value()
        APP_CONFIG["face_use_last_name"] = self.face_use_last_name_check.isChecked()
        APP_CONFIG["pet_use_last_name"] = self.pet_use_last_name_check.isChecked()
        APP_CONFIG["body_use_last_name"] = self.body_use_last_name_check.isChecked()
        APP_CONFIG["object_use_last_name"] = self.object_use_last_name_check.isChecked()
        APP_CONFIG["landmark_use_last_name"] = \
            self.landmark_use_last_name_check.isChecked()

        APP_CONFIG["thumbnails_bg_color"] = self.current_thumbs_bg_color
        APP_CONFIG["thumbnails_filename_color"] = self.current_thumbs_filename_color
        APP_CONFIG["thumbnails_tags_color"] = self.current_thumbs_tags_color
        APP_CONFIG["thumbnails_rating_color"] = self.current_thumbs_rating_color
        APP_CONFIG["thumbnails_tooltip_bg_color"] = \
            self.current_thumbs_tooltip_bg_color
        APP_CONFIG["thumbnails_tooltip_fg_color"] = \
            self.current_thumbs_tooltip_fg_color
        APP_CONFIG["thumbnails_filename_font_size"] = \
            self.filename_font_size_spin.value()
        APP_CONFIG["thumbnails_tags_font_size"] = self.tags_font_size_spin.value()

        APP_CONFIG["thumbnails_filename_lines"] = self.filename_lines_spin.value()
        APP_CONFIG["thumbnails_tags_lines"] = self.tags_lines_spin.value()
        APP_CONFIG["thumbnails_show_filename"] = self.show_filename_check.isChecked()
        APP_CONFIG["thumbnails_show_rating"] = self.show_rating_check.isChecked()
        APP_CONFIG["thumbnails_show_tags"] = self.show_tags_check.isChecked()
        APP_CONFIG["viewer_wheel_speed"] = self.viewer_wheel_spin.value()
        APP_CONFIG["duplicate_method"] = self.duplicate_method_combo.currentData()
        APP_CONFIG["duplicate_threshold"] = self.duplicate_threshold_slider.value()
        APP_CONFIG["default_delete_to_trash"] = \
            self.default_delete_to_trash_checkbox.isChecked()
        APP_CONFIG["duplicate_confirm_delete"] = \
            self.duplicate_confirm_delete_checkbox.isChecked()
        wl_paths = [self.duplicate_whitelist_list.item(i).text()
                    for i in range(self.duplicate_whitelist_list.count())]
        APP_CONFIG["duplicate_whitelist"] = ",".join(wl_paths)
        bl_paths = [self.duplicate_blacklist_list.item(i).text()
                    for i in range(self.duplicate_blacklist_list.count())]
        APP_CONFIG["duplicate_blacklist"] = ",".join(bl_paths)

        qt_tags = [
            self.quick_tags_list.item(i).text()
            for i in range(self.quick_tags_list.count())
        ]
        APP_CONFIG["mru_tags"] = qt_tags

        APP_CONFIG["viewer_auto_resize_window"] = \
            self.viewer_auto_resize_check.isChecked()
        APP_CONFIG["face_detection_engine"] = self.face_engine_combo.currentText()
        APP_CONFIG["pet_detection_engine"] = self.pet_engine_combo.currentText()
        if hasattr(self, "object_engine_combo"):
            APP_CONFIG["body_detection_engine"] = self.body_engine_combo.currentText()
        if hasattr(self, "object_engine_combo"):
            APP_CONFIG["object_detection_engine"] = \
                self.object_engine_combo.currentText()
        if hasattr(self, "landmark_engine_combo"):
            APP_CONFIG["landmark_detection_engine"] = \
                self.landmark_engine_combo.currentText()

        pos_map_inv = {
            UITexts.FILMSTRIP_BOTTOM: 'bottom',
            UITexts.FILMSTRIP_LEFT: 'left',
            UITexts.FILMSTRIP_TOP: 'top',
            UITexts.FILMSTRIP_RIGHT: 'right'
        }
        selected_text = self.filmstrip_pos_combo.currentText()
        APP_CONFIG["filmstrip_position"] = pos_map_inv.get(selected_text, 'bottom')

        save_app_config()
        super().accept()

    def on_download_finished(self, success, message):
        """Handles the result of the model download thread."""
        self.progress_dialog.close()

        if success:
            QMessageBox.information(
                self, UITexts.MEDIAPIPE_DOWNLOAD_SUCCESS_TITLE,
                UITexts.MEDIAPIPE_DOWNLOAD_SUCCESS_TEXT)
        else:
            QMessageBox.critical(self, UITexts.MEDIAPIPE_DOWNLOAD_ERROR_TITLE,
                                 UITexts.MEDIAPIPE_DOWNLOAD_ERROR_TEXT.format(message))
        self.update_mediapipe_status()

    def _on_downloader_finished(self):
        self.downloader_thread = None

    def _stop_downloader_thread(self):
        if self.downloader_thread and self.downloader_thread.isRunning():
            self.downloader_thread.stop()
            self.downloader_thread.wait()
            self.downloader_thread = None

    def done(self, r):
        self._stop_downloader_thread()  # Ensure downloader thread stops and waits.
        if self.counter_thread and self.counter_thread.isRunning():
            self.counter_thread.stop()
            self.counter_thread.wait()
        super().done(r)

    def closeEvent(self, event):
        self._stop_downloader_thread()  # Ensure downloader thread stops and waits.
        if self.counter_thread and self.counter_thread.isRunning():
            self.counter_thread.stop()
            self.counter_thread.wait()
        super().closeEvent(event)

    def add_quick_tag(self):
        """Opens a text input dialog to add a new quick tag."""
        tag, ok = QInputDialog.getText(
            self, UITexts.TAG_NEW_TAG_TITLE, UITexts.TAG_NEW_TAG_TEXT)
        if ok and tag.strip():
            t = tag.strip()
            # Avoid duplicates
            found = False
            for i in range(self.quick_tags_list.count()):
                if self.quick_tags_list.item(i).text() == t:
                    found = True
                    break
            if not found:
                self.quick_tags_list.addItem(t)

    def remove_quick_tag(self):
        """Removes the selected quick tags."""
        for item in self.quick_tags_list.selectedItems():
            self.quick_tags_list.takeItem(self.quick_tags_list.row(item))

    def _add_path_to_list(self, list_widget, path):
        """Adds a path to a QListWidget with existence validation."""
        path = os.path.abspath(os.path.expanduser(path.strip()))
        if not path:
            return

        to_remove = []
        for i in range(list_widget.count()):
            existing_p = list_widget.item(i).text()
            if existing_p == path:
                return

            # If a parent folder already exists, do not add this subfolder.
            if path.startswith(existing_p + os.sep):
                return

            # If the new path is a parent of an existing one, mark it for removal.
            if existing_p.startswith(path + os.sep):
                to_remove.append(i)

        # Remove unnecessary subfolders (reverse order to not alter indices).
        for i in sorted(to_remove, reverse=True):
            list_widget.takeItem(i)

        item = QListWidgetItem(path)
        if not os.path.isdir(path):
            item.setForeground(QColor("red"))
            item.setToolTip(
                UITexts.SETTINGS_PATH_NOT_FOUND_WARNING.format(path))
        list_widget.addItem(item)

    def add_whitelist_path(self):
        """Opens a directory dialog to add a folder to the whitelist."""
        dir_path = QFileDialog.getExistingDirectory(self, UITexts.SELECT)
        if dir_path:
            self._add_path_to_list(self.duplicate_whitelist_list, dir_path)

    def remove_whitelist_path(self):
        """Removes the selected folders from the whitelist list."""
        for item in self.duplicate_whitelist_list.selectedItems():
            self.duplicate_whitelist_list.takeItem(
                self.duplicate_whitelist_list.row(item))

    def add_blacklist_path(self):
        """Opens a directory dialog to add a folder to the blacklist."""
        dir_path = QFileDialog.getExistingDirectory(self, UITexts.SELECT)
        if dir_path:
            self._add_path_to_list(self.duplicate_blacklist_list, dir_path)

    def remove_blacklist_path(self):
        """Removes the selected folders from the blacklist list."""
        for item in self.duplicate_blacklist_list.selectedItems():
            self.duplicate_blacklist_list.takeItem(
                self.duplicate_blacklist_list.row(item))

    def update_duplicate_scan_count(self):
        """Calculates and updates the count of images in whitelist/blacklist
        using a background thread."""
        if self.counter_thread and self.counter_thread.isRunning():
            self.counter_thread.stop()
            self.counter_thread.wait()

        whitelist_paths = [self.duplicate_whitelist_list.item(i).text()
                           for i in range(self.duplicate_whitelist_list.count())]
        blacklist_paths = [self.duplicate_blacklist_list.item(i).text()
                           for i in range(self.duplicate_blacklist_list.count())]

        whitelist = [os.path.abspath(os.path.expanduser(p.strip()))
                     for p in whitelist_paths if p.strip()]
        blacklist = {os.path.abspath(os.path.expanduser(p.strip()))
                     for p in blacklist_paths if p.strip()}

        if not whitelist:
            self.duplicate_scan_count_label.setText(
                UITexts.SETTINGS_DUPLICATE_SCAN_COUNT_LABEL.format(0))
            self.duplicate_scan_progress.hide()
            return

        self.duplicate_scan_progress.show()
        self.counter_thread = DuplicateFileCounter(
            whitelist, blacklist, IMAGE_EXTENSIONS)
        self.counter_thread.count_updated.connect(
            lambda c: self.duplicate_scan_count_label.setText(
                UITexts.SETTINGS_DUPLICATE_SCAN_COUNT_LABEL.format(c)))
        self.counter_thread.finished.connect(
            lambda: self.duplicate_scan_progress.hide())
        self.counter_thread.start()
