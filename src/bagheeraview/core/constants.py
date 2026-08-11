"""
Constants Module for Bagheera Image Viewer.

This file centralizes all application-wide constants, settings, and static text.
It is organized into several sections:

- General application information (name, version).
- Configuration paths for settings and cache files.
- Default values for application behavior (e.g., cache sizes, scanner limits).
- UI-related constants (e.g., icon themes, default sizes).
- A `UITexts` class that provides internationalized strings for the UI based
  on the current language configuration.
"""
import importlib.util
import json
import os
import shutil
import sys

from PySide6.QtCore import Qt

# --- PLATFORM WORKAROUNDS ---
# Wayland does not reliably support moving/positioning windows programmatically,
# which is used for layout restoration. Forcing X11 via xcb is a workaround.
FORCE_X11 = "--x11" in sys.argv
if FORCE_X11:
    os.environ["QT_QPA_PLATFORM"] = "xcb"

# --- CONFIGURATION ---
PROG_NAME = "Bagheera Image Viewer"
PROG_ID = "bagheeraview"
PROG_VERSION = "1.0.0"
PROG_AUTHOR = "Ignacio Serantes"

# --- CACHE SETTINGS ---
# Maximum number of paths to track in the in-memory cache.
CACHE_MAX_SIZE = 10000

# Dynamic RAM limit for thumbnails to avoid swapping on low-end systems.
try:
    import psutil
    _total_ram_bytes = psutil.virtual_memory().total
    # Use 10% of system RAM, clamped between 128MB and 512MB
    CACHE_MAX_RAM_BYTES = int(max(128 * 1024 * 1024,
                                  min(512 * 1024 * 1024, _total_ram_bytes * 0.10)))
except (ImportError, Exception):
    # Fallback to a safe 256MB if psutil is missing or fails
    CACHE_MAX_RAM_BYTES = 256 * 1024 * 1024

# Minimum percentage of free system RAM required.
# Aggressive cache pruning will trigger if available memory falls below this.
MIN_FREE_RAM_PERCENT = 5.0

# Maximum size of the persistent disk cache file.
# 10 GB limit for persistent cache file
DISK_CACHE_MAX_BYTES = 10 * 1024 * 1024 * 1024

# --- PATHS ---
CONFIG_FILE = f"{PROG_ID}rc"
CONFIG_LOCATION = os.environ.get('XDG_CONFIG_HOME')
CONFIG_DIR = os.path.join(CONFIG_LOCATION, 'iserantes', PROG_ID)
CONFIG_PATH = os.path.join(CONFIG_DIR, CONFIG_FILE)

APP_DATA_LOCATION = os.path.expanduser('~/.local/share')
APP_DATA_DIR = os.path.join(APP_DATA_LOCATION, 'iserantes', PROG_ID)

CACHE_PATH = os.path.join(APP_DATA_DIR, "thumbnails")

HISTORY_FILE = "history.json"
HISTORY_PATH = os.path.join(APP_DATA_DIR, HISTORY_FILE)
LAYOUTS_DIR = os.path.join(APP_DATA_DIR, "layouts")  # Layouts saving directory
FAVORITES_FILE = "favorites.json"
FAVORITES_PATH = os.path.join(APP_DATA_DIR, FAVORITES_FILE)
DUPLICATE_CACHE_PATH = os.path.join(APP_DATA_DIR, "duplicates")
DUPLICATE_HASH_DB_NAME = b"hashes"
DUPLICATE_EXCEPTIONS_DB_NAME = b"exceptions"
DUPLICATE_PENDING_DB_NAME = b"pending"
DUPLICATE_BKTREE_DB_NAME = b"bktree"
DUPLICATE_HASH_TO_FILES_DB_NAME = b"hash_to_files"
METADATA_DB_NAME = b"metadata"
DIRECTORY_DB_NAME = b"directories"


def save_app_config():
    """Saves the main application configuration to the JSON file."""
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
            # Use APP_CONFIG global
            json.dump(APP_CONFIG, f, indent=4)
    except Exception as e:
        print(f"CRITICAL: Failed to save configuration to {CONFIG_PATH}: {e}")


# --- CONFIGURATION LOADING ---
def load_app_config():
    """Loads the main application configuration from the JSON file."""
    if not os.path.exists(CONFIG_PATH):
        return {}
    try:
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        # In case of error, return empty config to avoid crash
        return {}


APP_CONFIG = load_app_config()

# --- UI: ICONS & THEMES ---
ICON_THEME = "bagheeraview"
ICON_THEME_FALLBACK = "org.kde.dolphin"
ICON_THEME_VIEWER = "bagheeraview"
ICON_THEME_VIEWER_FALLBACK = "image"

# --- FILE HANDLING ---
IMAGE_EXTENSIONS = {'.bmp', '.gif', '.jpeg', '.jpg', '.png', '.tiff', '.webp'}
IMAGE_MIME_TYPES = "Image files (*" + ' *'.join(IMAGE_EXTENSIONS) + ")"

# Path to KDE's screen configuration file. Used for more accurate screen
# geometry. Maybe needed, maybe not, for calculating screen geometry
KSCREEN_DOCTOR_MARGIN = 0
KWINOUTPUTCONFIG_PATH = os.path.join(os.path.expanduser("~"),
                                     ".config/kwinoutputconfig.json")

# --- EXTERNAL TOOLS ---
# Command definitions for external search tools.
try:
    import bagheerasearch.core.search_lib.search  # noqa: F401
    HAVE_BAGHEERASEARCH_LIB = True
except ImportError:
    HAVE_BAGHEERASEARCH_LIB = False
    pass

BALOOSEARCH_EXEC = shutil.which("baloosearch") or shutil.which("baloosearch6")
SEARCH_CMD = [BALOOSEARCH_EXEC, "--type", "image"] \
    if BALOOSEARCH_EXEC else None

# --- TAGS ---
TAGS_MENU_MAX_ITEMS_DEFAULT = 25

# --- SCANNER SETTINGS ---
SCANNER_SETTINGS_DEFAULTS = {
    "scan_max_level": 2,
    "scan_batch_size": 64,
    "scan_full_on_start": True,
    "person_tags": "",
    "generation_threads": 4,
    "search_engine": "",
    "face_use_last_name": False,
    "pet_use_last_name": False,
    "body_use_last_name": False,
    "object_use_last_name": False,
    "landmark_use_last_name": False,
    "duplicate_threshold": 90,  # Similarity percentage (50-100)
    "duplicate_method": "histogram_hashing",
    "duplicate_confirm_delete": True,
    "default_delete_to_trash": True,
    "duplicate_whitelist": "",
    "duplicate_blacklist": "",
    "areas_reset_to_face": False
}

# --- IMAGE VIEWER DEFAULTS ---
VIEWER_LABEL = "BagheeraView"
VIEWER_FORM_MARGIN = 10

# --- THUMBNAIL GRID DEFAULTS ---
# Default size of the thumbnail widget in the grid view.
THUMBNAILS_DEFAULT_SIZE = 128
# The different size tiers for thumbnails that can be cached.
THUMBNAIL_SIZES = [128, 256, 512]
# The sizes that the initial scanner will generate. A smaller one for the initial
# grid view, and a larger one to have ready for zooming.
SCANNER_GENERATE_SIZES = [128]
THUMBNAILS_MARGIN = 10
THUMBNAILS_REFRESH_INTERVAL_DEFAULT = 200
THUMBNAILS_BG_COLOR_DEFAULT = "#191919"
THUMBNAILS_FILENAME_COLOR_DEFAULT = "#DDDDDD"
THUMBNAILS_TAGS_COLOR_DEFAULT = "#3498db"
THUMBNAILS_RATING_COLOR_DEFAULT = "#f1c40f"
THUMBNAILS_FILENAME_FONT_SIZE_DEFAULT = 8
THUMBNAILS_TOOLTIP_FG_COLOR_DEFAULT = "#DDDDDD"
THUMBNAILS_TOOLTIP_BG_COLOR_DEFAULT = "#333333"
THUMBNAILS_TAGS_FONT_SIZE_DEFAULT = 7
THUMBNAILS_FILENAME_LINES_DEFAULT = 1
THUMBNAILS_TAGS_LINES_DEFAULT = 2
VIEWER_WHEEL_SPEED_DEFAULT = 5
VIEWER_AUTO_RESIZE_WINDOW_DEFAULT = True

# --- METADATA ---
# The extended attribute name used for storing tags, following the freedesktop.org spec.
XATTR_NAME = "user.xdg.tags"
RATING_XATTR_NAME = "user.baloo.rating"
XATTR_COMMENT_NAME = "user.xdg.comment"

# --- BEHAVIOR ---
# The initial zoom ratio to use when opening an image, relative to screen size.
ZOOM_DESKTOP_RATIO = 0.93

# --- FACES ---
FACES_MENU_MAX_ITEMS_DEFAULT = 25
FACES_MENU_MAX_ITEMS = APP_CONFIG.get("faces_menu_max_items",
                                      FACES_MENU_MAX_ITEMS_DEFAULT)

# --- FACE DETECTION ---
HAVE_MEDIAPIPE = False
if importlib.util.find_spec("mediapipe") is not None:
    try:
        import mediapipe
        # Verify that the tasks module (new API) is available
        if hasattr(mediapipe, "tasks"):
            HAVE_MEDIAPIPE = True
    except Exception:
        pass
HAVE_FACE_RECOGNITION = importlib.util.find_spec("face_recognition") is not None

MEDIAPIPE_FACE_MODEL_PATH = os.path.join(
    APP_DATA_DIR, "blaze_face_short_range.tflite")
MEDIAPIPE_FACE_MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/face_detector/"
    "blaze_face_short_range/float16/1/blaze_face_short_range.tflite"
)

MEDIAPIPE_OBJECT_MODEL_PATH = os.path.join(
    APP_DATA_DIR, "efficientdet_lite0.tflite")
MEDIAPIPE_OBJECT_MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/object_detector/"
    "efficientdet_lite0/float16/1/efficientdet_lite0.tflite"
)

# Ordered list of available detection engines. The first one found will be the default.
# MediaPipe is generally preferred for its performance.
AVAILABLE_FACE_ENGINES = []
if HAVE_FACE_RECOGNITION:
    AVAILABLE_FACE_ENGINES.append("face_recognition")
if HAVE_MEDIAPIPE:
    AVAILABLE_FACE_ENGINES.append("mediapipe")

AVAILABLE_PET_ENGINES = []
if HAVE_MEDIAPIPE:
    AVAILABLE_PET_ENGINES.append("mediapipe")

AVAILABLE_BODY_ENGINES = []
if HAVE_MEDIAPIPE:
    AVAILABLE_BODY_ENGINES.append("mediapipe")

# Determine the default engine. This can be overridden by user config.
DEFAULT_FACE_ENGINE = AVAILABLE_FACE_ENGINES[0] if AVAILABLE_FACE_ENGINES else None
DEFAULT_PET_ENGINE = AVAILABLE_PET_ENGINES[0] if AVAILABLE_PET_ENGINES else None

# --- Data roles for the thumbnail model ---
PATH_ROLE = Qt.UserRole + 1
MTIME_ROLE = Qt.UserRole + 2
TAGS_ROLE = Qt.UserRole + 3
RATING_ROLE = Qt.UserRole + 4
ITEM_TYPE_ROLE = Qt.UserRole + 5
DIR_ROLE = Qt.UserRole + 6
INODE_ROLE = Qt.UserRole + 7
DEVICE_ROLE = Qt.UserRole + 8
IMAGE_DATA_ROLE = Qt.UserRole + 9
GROUP_NAME_ROLE = Qt.UserRole + 10

HAVE_IMAGEHASH = importlib.util.find_spec("imagehash") is not None

# --- DUPLICATE DETECTION ---
HAVE_DUPLICATE_RESNET_LIBS = all(
    importlib.util.find_spec(lib) is not None
    for lib in ["torch", "torchvision", "numpy", "sklearn"]
)

MAX_DHASH_DISTANCE = 64  # For 64-bit dHash

DEFAULT_FACE_BOX_COLOR = "#FFFFFF"
# Load preferred engine from config, or use the default.
FACE_DETECTION_ENGINE = APP_CONFIG.get("face_detection_engine",
                                       DEFAULT_FACE_ENGINE)
PET_DETECTION_ENGINE = APP_CONFIG.get("pet_detection_engine",
                                      DEFAULT_PET_ENGINE)

DEFAULT_PET_BOX_COLOR = "#98FB98"  # PaleGreen
DEFAULT_BODY_BOX_COLOR = "#FF4500"  # OrangeRed
DEFAULT_OBJECT_BOX_COLOR = "#FFD700"  # Gold
DEFAULT_LANDMARK_BOX_COLOR = "#00BFFF"  # DeepSkyBlue
# --- SHORTCUTS ---
GLOBAL_ACTIONS = {
    "quit_app": ("Quit Application", "Global"),
    "toggle_visibility": ("Toggle Visibility", "Global"),
    "close_all_viewers": ("Close All Viewers", "Global"),
    "load_more_images": ("Load More Images", "File"),
    "load_all_images": ("Load All Images", "File"),
    "save_layout": ("Save Layout", "File"),
    "load_layout": ("Load Layout", "File"),
    "open_folder": ("Open Folder", "File"),
    "move_to_trash": ("Move to Trash", "File"),
    "delete_permanently": ("Delete Permanently", "File"),
    "rename_image": ("Rename Image", "Actions"),
    "hard_refresh_content": ("Hard Refresh Content", "Actions"),
    "refresh_content": ("Refresh Content", "Actions"),
    "first_image": ("First Image", "Navigation"),
    "last_image": ("Last Image", "Navigation"),
    "prev_page": ("Previous Page", "Navigation"),
    "next_page": ("Next Page", "Navigation"),
    "zoom_in": ("Zoom In", "Navigation"),
    "zoom_out": ("Zoom Out", "Navigation"),
    "toggle_faces": ("Show Faces", "View"),
    "select_all": ("Select All", "Selection"),
    "select_none": ("Select None", "Selection"),
    "invert_selection": ("Invert Selection", "Selection"),
}

DEFAULT_GLOBAL_SHORTCUTS = {
    # action_name: (key, mods, ignore_if_typing)
    "quit_app": (Qt.Key_Q, Qt.ControlModifier, False),
    "toggle_visibility": (Qt.Key_H, Qt.ControlModifier, False),
    "close_all_viewers": (Qt.Key_Q, Qt.ShiftModifier, False),
    "load_more_images": (Qt.Key_D, Qt.ControlModifier, True),
    "load_all_images": (Qt.Key_D, Qt.ControlModifier | Qt.ShiftModifier, True),
    "save_layout": (Qt.Key_S, Qt.NoModifier, True),
    "load_layout": (Qt.Key_L, Qt.NoModifier, True),
    "open_folder": (Qt.Key_F, Qt.ControlModifier, True),
    "move_to_trash": (Qt.Key_Delete, Qt.NoModifier, True),
    "delete_permanently": (Qt.Key_Delete, Qt.ShiftModifier, True),
    "rename_image": (Qt.Key_F2, Qt.NoModifier, True),
    "hard_refresh_content": (Qt.Key_F5, Qt.ControlModifier, True),
    "refresh_content": (Qt.Key_F5, Qt.NoModifier, True),
    "first_image": (Qt.Key_Home, Qt.NoModifier, True),
    "last_image": (Qt.Key_End, Qt.NoModifier, True),
    "prev_page": (Qt.Key_PageUp, Qt.NoModifier, True),
    "next_page": (Qt.Key_PageDown, Qt.NoModifier, True),
    "zoom_in": (Qt.Key_Plus, Qt.NoModifier, True),
    "zoom_out": (Qt.Key_Minus, Qt.NoModifier, True),
    "toggle_faces": (Qt.Key_F7, Qt.NoModifier, True),
    "select_all": (Qt.Key_A, Qt.ControlModifier, True),
    "select_none": (Qt.Key_A, Qt.ControlModifier | Qt.ShiftModifier, True),
    "invert_selection": (Qt.Key_I, Qt.ControlModifier, True),
}

VIEWER_ACTIONS = {
    "close": ("Close Viewer / Exit Fullscreen", "Window"),
    "next": ("Next Image", "Navigation"),
    "prev": ("Previous Image", "Navigation"),
    "rename": ("Rename Image", "File"),
    "toggle_statusbar": ("Toggle Status Bar", "View"),
    "toggle_filmstrip": ("Toggle Filmstrip", "View"),
    "slideshow": ("Toggle Slideshow", "View"),
    "slideshow_reverse": ("Toggle Reverse Slideshow", "View"),
    "toggle_faces": ("Show Faces", "View"),
    "fullscreen": ("Toggle Fullscreen", "Window"),
    "detect_faces": ("Detect Faces", "Actions"),
    "detect_pets": ("Detect Pets", "Actions"),
    "fast_tag": ("Quick Tags", "Actions"),
    "detect_bodies": ("Detect Bodies", "Actions"),
    "rotate_right": ("Rotate Right", "Transform"),
    "rotate_left": ("Rotate Left", "Transform"),
    "zoom_in": ("Zoom In", "Transform"),
    "zoom_out": ("Zoom Out", "Transform"),
    "reset_zoom": ("Reset Zoom (100%)", "Transform"),
    "toggle_animation": ("Pause/Resume Animation", "Playback"),
    "properties": ("Properties", "File"),
    "toggle_visibility": ("Show/Hide Main Window", "Window"),
    "toggle_crop": ("Toggle Crop Mode", "Edit"),
    "save_crop": ("Save Cropped Image", "File"),
    "copy_image": ("Copy Image to Clipboard", "Edit"),
    "copy_path": ("Copy File Path", "Edit"),
    "compare_1": ("Single View", "View"),
    "compare_2": ("Compare 2 Images", "View"),
    "compare_4": ("Compare 4 Images", "View"),
    "link_panes": ("Link Panes", "View"),
}

DEFAULT_VIEWER_SHORTCUTS = {
    # action_name: (key, mods)
    "close": (Qt.Key_Escape, Qt.NoModifier),
    "next": (Qt.Key_Space, Qt.NoModifier),
    "prev": (Qt.Key_Backspace, Qt.NoModifier),
    "rename": (Qt.Key_F2, Qt.NoModifier),
    "toggle_statusbar": (Qt.Key_F3, Qt.NoModifier),
    "toggle_filmstrip": (Qt.Key_F4, Qt.NoModifier),
    "slideshow": (Qt.Key_F6, Qt.NoModifier),
    "slideshow_reverse": (Qt.Key_F6, Qt.ShiftModifier),
    "toggle_faces": (Qt.Key_F8, Qt.NoModifier),
    "fullscreen": (Qt.Key_F11, Qt.NoModifier),
    "detect_faces": (Qt.Key_F, Qt.NoModifier),
    "detect_pets": (Qt.Key_P, Qt.NoModifier),
    "detect_bodies": (Qt.Key_B, Qt.NoModifier),
    "fast_tag": (Qt.Key_T, Qt.NoModifier),
    "rotate_right": (Qt.Key_Plus, Qt.ControlModifier),
    "rotate_left": (Qt.Key_Minus, Qt.ControlModifier),
    "zoom_in": (Qt.Key_Plus, Qt.NoModifier),
    "zoom_out": (Qt.Key_Minus, Qt.NoModifier),
    "reset_zoom": (Qt.Key_Z, Qt.NoModifier),
    "toggle_animation": (Qt.Key_P, Qt.ShiftModifier),
    "properties": (Qt.Key_Return, Qt.AltModifier),
    "toggle_visibility": (Qt.Key_H, Qt.ControlModifier),
    "toggle_crop": (Qt.Key_C, Qt.NoModifier),
    "save_crop": (Qt.Key_S, Qt.ControlModifier),
    "compare_1": (Qt.Key_1, Qt.AltModifier),
    "compare_2": (Qt.Key_2, Qt.AltModifier),
    "compare_4": (Qt.Key_4, Qt.AltModifier),
    "link_panes": (Qt.Key_L, Qt.AltModifier),
}


# --- TEXT CONSTANTS ---

# Supported languages
SUPPORTED_LANGUAGES = {
    "system": "System",
    "en": "English",
    "es": "Español",
    "gl": "Galego"
}

# Default language for configuration
DEFAULT_LANGUAGE = "system"
# Fallback language for translations
FALLBACK_LANGUAGE = "en"

_UI_TEXTS = {
    "en": {
        "READY": "Ready",
        "SEARCH": "Search",
        "SELECT": "Select",
        "ERROR": "Error",
        "FILE_NOT_FOUND": "File not found",
        "WARNING": "Warning",
        "INFO": "Info",
        "LOAD": "Load",
        "SAVE": "Save",
        "CREATE": "Create",
        "CANCEL": "Cancel",
        "RENAME": "Rename",
        "COPY": "Copy",
        "DELETE": "Delete",
        "UNKNOWN": "Unknown",
        "MENU_LANGUAGE": "Language",
        "RESTART_REQUIRED_TITLE": "Restart Required",
        "RESTART_REQUIRED_TEXT": "The language has been changed to {language}.\nPlease "
        "restart the application for the changes to take full effect.",
        "SORT_NAME_ASC": "Name ↑",
        "SORT_NAME_DESC": "Name ↓",
        "SORT_DATE_ASC": "Date ↑",
        "SORT_DATE_DESC": "Date ↓",
        "VIEW_MODE_FLAT": "Flat",
        "MENU_VIEW_MODE": "View Mode",
        "FILTERED_COUNT": "Filtered: {}",
        "VIEW_MODE_DAY": "Separate by Day",
        "VIEW_MODE_WEEK": "Separate by Week",
        "MENU_FIND_SIMILAR": "Find similar images",
        "SIMILAR_SEARCH_TITLE": "Similar images to '{}'",
        "SIMILAR_SEARCH_PROGRESS": "Searching similar images: {} found...",
        "RESCAN": "Rescan",
        "VIEW_MODE_MONTH": "Separate by Month",
        "VIEW_MODE_YEAR": "Separate by Year",
        "VIEW_MODE_RATING": "Separate by Rating",
        "FILTERED_ZERO": "Filtered: 0",
        "VIEW_MODE_FOLDER": "Separate by Folder",
        "LOAD_MORE_TOOLTIP": f"Load {APP_CONFIG.get('scan_batch_size', 64)} images "
        "more (Ctrl+D)",
        "LOAD_ALL_TOOLTIP": "Load all images (Ctrl+Shift+D)",
        "LOAD_ALL_TOOLTIP_ALT": "Cancel loading all images (Ctrl+Shift+D)",
        "CONFIRM_LOAD_ALL_TITLE": "Confirm load",
        "CONFIRM_LOAD_ALL_TEXT": "Are you sure you want to load {} images left?",
        "DONE_SCAN": "Done: {} images",
        "GROUP_BY_WEEK_FORMAT": "{year} - Week {week}",
        "GROUP_HEADER_FORMAT": "{group_name} - {count} images",
        "GROUP_HEADER_FORMAT_SINGULAR": "{group_name} - 1 image",
        "GROUP_BY_RATING_FORMAT": "{stars} Stars",
        "LOADING_SCAN": "Loading... {} / {}",
        "SHUTTING_DOWN": "Shutting down...",
        "LOADED_PARTIAL": "Loaded {} / {}",
        "HIGH_RES_GENERATED": "High-res thumbnails generated.",
        "SCANNING_DIRS": "Scanning directories...",
        "SELECT_IMAGE_TITLE": "Select Image",
        "VIEWER_TITLE_PAUSED": " [Paused]",
        "IMAGE_NOT_IN_VIEW": "Image '{}' not in current view.",
        "VIEWER_TITLE_SLIDESHOW": " [Slideshow]",
        "RENAME_VIEWER_TITLE": "Rename File",
        "RENAME_VIEWER_TEXT": "New name for '{}':",
        "RENAME_VIEWER_ERROR_EXISTS": "File '{}' already exists.",
        "RENAME_VIEWER_ERROR_SYSTEM": "System Error",
        "RENAME_VIEWER_ERROR_TEXT": "Could not rename file: {}",
        "ADD_FACE_TITLE": "Add Face",
        "ADD_PET_TITLE": "Add Pet",
        "ADD_BODY_TITLE": "Add Body",
        "ADD_OBJECT_TITLE": "Add Object",
        "ADD_LANDMARK_TITLE": "Add Landmark",
        "ADD_FACE_LABEL": "Name:",
        "ADD_PET_LABEL": "Name:",
        "ADD_BODY_LABEL": "Name:",
        "ADD_OBJECT_LABEL": "Name:",
        "ADD_LANDMARK_LABEL": "Name:",
        "NEXT_AREA": "Next region: {}",
        "DELETE_AREA_TITLE": "Delete region",
        "CREATE_TAG_TITLE": "Create Tag",
        "CREATE_TAG_TEXT": "The tag for '{}' does not exist. Do you want to create a "
        "new one?",
        "NEW_PERSON_TAG_TITLE": "New Person Tag",
        "NEW_PERSON_TAG_TEXT": "Enter the full path for the tag:",
        "NEW_PET_TAG_TITLE": "New Pet Tag",
        "NEW_PET_TAG_TEXT": "Enter the full path for the tag:",
        "NEW_BODY_TAG_TITLE": "New Body Tag",
        "NEW_BODY_TAG_TEXT": "Enter the full path for the tag:",
        "NEW_OBJECT_TAG_TITLE": "New Object Tag",
        "NEW_OBJECT_TAG_TEXT": "Enter the full path for the tag:",
        "NEW_LANDMARK_TAG_TITLE": "New Landmark Tag",
        "NEW_LANDMARK_TAG_TEXT": "Enter the full path for the tag:",
        "SELECT_TAG_TITLE": "Select Tag",
        "SELECT_TAG_TEXT": "Multiple tags found for '{}'. Please select the correct "
        "one:",
        "FACE_NAME_TOOLTIP": "Type a name or select from history.",
        "CLEAR_TEXT_TOOLTIP": "Clear text field",
        "RENAME_AREA_TITLE": "Rename region",
        "SHOW_FACES": "Show Faces && other regions",
        "DETECT_FACES": "Detect Face",
        "DETECT_PETS": "Detect Pets",
        "DETECT_BODIES": "Detect Bodies",
        "NO_FACE_LIBS": "No face detection libraries found. Install 'mediapipe' or "
        "'face_recognition'.",
        "THUMBNAIL_NO_NAME": "No name",
        "THUMBNAIL_NO_TAGS": "No tags",
        "MENU_ABOUT": "About",
        "MENU_ABOUT_TITLE": "About {}",
        "MENU_ABOUT_TEXT": "<b>{0}</b> v{1}<br><br>A simple image viewer and manager "
        "for KDE with Baloo support.<br><br>Created by {2} with the help of AI, but "
        "mostly thanks to the job of the good people at KDE and Qt.",
        "MENU_CACHE": "Cache",
        "MENU_CLEAR_CACHE": "Clear cache ({} items, {:.1f} MB, {:.1f} MB on disk)",
        "MENU_CLEAN_CACHE": "Clean up invalid cache entries",
        "MENU_CLEAN_METADATA_CACHE": "Clean up stale metadata cache",
        "MENU_CLEAN_DIRECTORY_CACHE": "Clean up stale directory cache",
        "MENU_SHOW_TAGS": "Show Tags",
        "MENU_SHOW_INFO": "Show Information",
        "MENU_SHOW_FAVORITES": "Show Favorites",
        "FAVORITES_TAB": "Favorites",
        "FAVORITES_SEARCH_PLACEHOLDER": "Search favorites...",
        "FAVORITES_TABLE_HEADER": ["Comment", "Query", "Shortcut"],
        "ADD_FAVORITE_TOOLTIP": "Add current search to favorites",
        "EDIT_COMMENT_TITLE": "Edit Comment",
        "EDIT_COMMENT_TEXT": "Comment for '{}':",
        "EDIT_SHORTCUT_TITLE": "Assign Shortcut",
        "EDIT_SHORTCUT_TEXT": "Press keys for '{}':",
        "MOVE_UP": "Move Up",
        "MOVE_DOWN": "Move Down",
        "MENU_SHOW_FILTER": "Show Filter",
        "MENU_SHOW_LAYOUTS": "Show Layouts",
        "MENU_SHOW_HISTORY": "Show History",
        "MENU_SETTINGS": "Settings",
        "SETTINGS_GROUP_DUPLICATES": "Duplicates",
        "MENU_DUPLICATES": "Duplicates",
        "MENU_DETECT_CURRENT_SEARCH": "Detect in current search",
        "MENU_DETECT_ALL": "Detect all",
        "MENU_FORCE_FULL_ALL_ANALYSIS": "Force full all analysis",
        "MENU_FORCE_FULL_ANALYSIS": "Force full analysis",
        "MENU_REVIEW_IGNORED": "Review ignored",
        "MENU_CLEAN_UP_HASHES": "Clean up",
        "MENU_REPAIR_DATABASE": "Repair index",
        "MENU_CLEAR_EXCEPTIONS": "Clear ignored pairs",
        "CONFIRM_CLEAR_EXCEPTIONS_TITLE": "Confirm Clear Ignored Pairs",
        "CONFIRM_CLEAR_EXCEPTIONS_TEXT": "Are you sure you want to clear all "
        "ignored duplicate pairs? They will be detected again in the next scan.",
        "REPAIRING_DATABASE": "Repairing duplicate index...",
        "MENU_CLEAR_HASHES": "Clear hashes ({} items, {:.1f} MB on disk)",
        "CONFIRM_CLEAR_HASHES_TITLE": "Confirm Clear Hashes",
        "CONFIRM_CLEAR_HASHES_TEXT": "Are you sure you want to permanently delete "
        "the entire hash database?",
        "CONFIRM_CLEAR_HASHES_INFO": "This will remove all calculated image hashes. "
        "They will be recalculated as you detect duplicates, which may be slow. This "
        "action cannot be undone.",
        "SETTINGS_DUPLICATE_METHOD_LABEL": "Method:",
        "SETTINGS_DUPLICATE_METHOD_TOOLTIP": "Select the method for duplicate "
        "detection.",
        "METHOD_HISTOGRAM_HASHING": "Histogram + Hashing",
        "METHOD_RESNET": "ResNet (AI Based)",
        "SETTINGS_DUPLICATE_CONFIRM_DELETE_LABEL": "Confirm before deleting duplicates",
        "SETTINGS_DUPLICATE_WHITELIST_LABEL": "Whitelist (folders to include):",
        "SETTINGS_DUPLICATE_WHITELIST_TOOLTIP": "Comma-separated paths of folders to "
        "scan when using 'Detect all'.",
        "SETTINGS_DUPLICATE_BLACKLIST_LABEL": "Blacklist (folders to exclude):",
        "SETTINGS_DUPLICATE_BLACKLIST_TOOLTIP": "Comma-separated paths of folders to "
        "ignore during 'Detect all' scans.",
        "SETTINGS_DUPLICATE_SCAN_COUNT_LABEL": "Images found for 'Detect all': {}",
        "SETTINGS_DEFAULT_DELETE_TO_TRASH_LABEL": "Delete key sends to trash by "
        "default",
        "SETTINGS_DEFAULT_DELETE_TO_TRASH_TOOLTIP": "If checked, pressing the Delete "
        "key will move files to trash. If unchecked, it will permanently delete them.",
        "SETTINGS_DUPLICATE_CONFIRM_DELETE_TOOLTIP": "Show a confirmation dialog "
        "before moving a duplicate image to the trash.",
        "SETTINGS_DUPLICATE_THRESHOLD_LABEL": "Similarity Threshold:",
        "SETTINGS_DUPLICATE_THRESHOLD_TOOLTIP": "Set the similarity threshold 2 "
        "(50-100%). Higher values mean images must be more similar to be considered "
        "duplicates.",
        "SETTINGS_DUPLICATE_MISSING_LIBS": "The 'imagehash' library is required for "
        "duplicate detection but was not found. This feature is disabled.",
        "MENU_DETECT_DUPLICATES": "Detect Duplicates",
        "DUPLICATE_WHITELIST_EMPTY": "Whitelist is empty. Please configure it "
        "in Settings.",
        "DUPLICATE_DETECTION_TITLE": "Duplicate Detection",
        "DUPLICATE_ALREADY_RUNNING": "Duplicate detection is already in progress.",
        "DUPLICATE_NO_IMAGES": "No images loaded to detect duplicates.",
        "DUPLICATE_STARTING": "Starting duplicate detection...",
        "DUPLICATE_PROGRESS": "Duplicate detection: {message} ({current}/{total})",
        "DUPLICATE_NONE_FOUND": "No duplicates found.",
        "DUPLICATE_FOUND_TITLE": "Duplicates Found",
        "DUPLICATE_FOUND_MSG": "The following duplicates were found:\n",
        "DUPLICATE_FOUND_MORE": "... and {count} more.",
        "DUPLICATE_FINISHED": "Duplicate detection finished.",
        "DUPLICATE_MSG_HASHING": "Hashing {filename}",
        "DUPLICATE_MSG_ANALYZING": "Analyzing {filename}",
        "DUPLICATE_MANAGER_TITLE": "Manage Duplicate Images",
        "DUPLICATE_DELETE_LEFT": "Trash Left",
        "DUPLICATE_DELETE_RIGHT": "Trash Right",
        "CONFIRM_TRASH_TITLE": "Move to Trash",
        "CONFIRM_TRASH_TEXT": "Do you want to move this image to the trash?",
        "DUPLICATE_KEEP_BOTH": "Keep Both (Ignore)",
        "DUPLICATE_SKIP": "Skip",
        "DUPLICATE_REMOVE_IGNORED": "Remove from ignored",
        "DUPLICATE_INFO_FORMAT": "{size} - {width}x{height}",
        "VIEWER_MENU_LINK_PANES": "Link Panes",
        "DUPLICATE_OPEN_COMPARISON": "Open Comparison",
        "DUPLICATE_LIST_HEADER": "Duplicate Pairs",
        "IGNORED_DATE": "Ignored Date",
        "SETTINGS_GROUP_SCANNER": "Scanner",
        "SETTINGS_GROUP_AREAS": "Regions",
        "SETTINGS_GROUP_THUMBNAILS": "Thumbnails",
        "SETTINGS_GROUP_VIEWER": "Image Viewer",
        "SETTINGS_PERSON_TAGS_LABEL": "Person tags:",
        "SETTINGS_FACE_ENGINE_LABEL": "Face Detection Engine:",
        "SETTINGS_FACE_COLOR_LABEL": "Face box color:",
        "SETTINGS_MRU_TAGS_COUNT_LABEL": "Max MRU tags:",
        "SETTINGS_PET_TAGS_LABEL": "Pet tags:",
        "SETTINGS_PET_ENGINE_LABEL": "Pet Detection Engine:",
        "SETTINGS_PET_COLOR_LABEL": "Pet box color:",
        "SETTINGS_PET_HISTORY_COUNT_LABEL": "Max pet history:",
        "SETTINGS_PET_TAGS_TOOLTIP": "Default tags for pets, separated by commas.",
        "SETTINGS_PET_ENGINE_TOOLTIP": "Library used for pet detection.",
        "SETTINGS_PET_COLOR_TOOLTIP": "Color of the bounding box drawn around "
        "detected pets.",
        "SETTINGS_PET_HISTORY_TOOLTIP": "Maximum number of recently used pet names "
        "to remember.",
        "TYPE_FACE": "Face",
        "TYPE_PET": "Pet",
        "TYPE_BODY": "Body",
        "TYPE_OBJECT": "Object",
        "TYPE_LANDMARK": "Landmark",
        "SETTINGS_BODY_TAGS_LABEL": "Body tags:",
        "SETTINGS_BODY_ENGINE_LABEL": "Body Detection Engine:",
        "SETTINGS_BODY_COLOR_LABEL": "Body box color:",
        "SETTINGS_BODY_HISTORY_COUNT_LABEL": "Max body history:",
        "SETTINGS_BODY_TAGS_TOOLTIP": "Default tags for bodies, separated by commas.",
        "SETTINGS_BODY_ENGINE_TOOLTIP": "Library used for body detection.",
        "SETTINGS_BODY_COLOR_TOOLTIP": "Color of the bounding box drawn around "
        "detected bodies.",
        "SETTINGS_BODY_HISTORY_TOOLTIP": "Maximum number of recently used body names "
        "to remember.",
        "SETTINGS_OBJECT_TAGS_LABEL": "Object tags:",
        "SETTINGS_OBJECT_ENGINE_LABEL": "Object Detection Engine:",
        "SETTINGS_OBJECT_COLOR_LABEL": "Object box color:",
        "SETTINGS_OBJECT_HISTORY_COUNT_LABEL": "Max object history:",
        "SETTINGS_OBJECT_TAGS_TOOLTIP": "Default tags for objects, separated by "
        "commas.",
        "SETTINGS_OBJECT_ENGINE_TOOLTIP": "Library used for object detection.",
        "SETTINGS_OBJECT_COLOR_TOOLTIP": "Color of the bounding box drawn around "
        "objects.",
        "SETTINGS_OBJECT_HISTORY_TOOLTIP": "Maximum number of recently used object "
        "names to remember.",
        "SETTINGS_LANDMARK_TAGS_LABEL": "Landmark tags:",
        "SETTINGS_LANDMARK_ENGINE_LABEL": "Landmark Detection Engine:",
        "SETTINGS_LANDMARK_COLOR_LABEL": "Landmark box color:",
        "SETTINGS_LANDMARK_HISTORY_COUNT_LABEL": "Max landmark history:",
        "SETTINGS_LANDMARK_TAGS_TOOLTIP": "Default tags for landmarks, separated "
        "by commas.",
        "SETTINGS_LANDMARK_ENGINE_TOOLTIP": "Library used for landmark detection.",
        "SETTINGS_LANDMARK_COLOR_TOOLTIP": "Color of the bounding box drawn around "
        "landmarks.",
        "SETTINGS_LANDMARK_HISTORY_TOOLTIP": "Maximum number of recently used "
        "landmark names to remember.",
        "SETTINGS_PATH_NOT_FOUND_WARNING": "Warning: Path not found or is not "
        "a directory: {}",
        "SETTINGS_USE_LAST_NAME_LABEL": "Use last name by default",
        "SETTINGS_USE_LAST_NAME_TOOLTIP": "Automatically fill the assignment window "
        "with the last used name.",
        "SETTINGS_AREAS_RESET_TO_FACE_LABEL": "Reset to 'Face' after selection",
        "SETTINGS_AREAS_RESET_TO_FACE_TOOLTIP": "Automatically switch back to 'Face' "
        "mode after adding a different region type (Pet, Body, etc.).",
        "SETTINGS_FACE_HISTORY_COUNT_LABEL": "Max face history:",
        "SETTINGS_THUMBS_REFRESH_LABEL": "Thumbs refresh interval (ms):",
        "MENU_VIEWER_SETTINGS": "Viewer Settings",
        "SETTINGS_THUMBS_BG_COLOR_LABEL": "Thumbnails background color:",
        "SETTINGS_THUMBS_FILENAME_COLOR_LABEL": "Thumbnails filename color:",
        "SETTINGS_THUMBS_TAGS_COLOR_LABEL": "Thumbnails tags color:",
        "SETTINGS_THUMBS_RATING_COLOR_LABEL": "Thumbnails rating color:",
        "SETTINGS_THUMBS_FILENAME_FONT_SIZE_LABEL": "Thumbnails filename font size:",
        "SETTINGS_THUMBS_TAGS_FONT_SIZE_LABEL": "Thumbnails tags font size:",
        "SETTINGS_SCAN_THREADS_LABEL": "Generation threads:",
        "SETTINGS_SCAN_THREADS_TOOLTIP": "Maximum number of simultaneous threads to "
        "generate thumbnails.",
        "SETTINGS_SCAN_MAX_LEVEL_LABEL": "Scan Max Level:",
        "SETTINGS_SCAN_BATCH_SIZE_LABEL": "Scan Batch Size:",
        "SETTINGS_SCAN_FULL_ON_START_LABEL": "Scan Full On Start:",
        "SETTINGS_SCANNER_SEARCH_ENGINE_LABEL": "File search engine:",
        "SETTINGS_SCANNER_SEARCH_ENGINE_TOOLTIP": "Engine to use for finding files. "
        "'Bagheera' uses BagheeraSearch library. 'Baloo' uses 'baloosearch' command.",
        "SETTINGS_SCAN_MAX_LEVEL_TOOLTIP": "Maximum directory depth to scan "
        "recursively.",
        "SETTINGS_SCAN_BATCH_SIZE_TOOLTIP": "Number of images to load in each batch.",
        "SETTINGS_SCAN_FULL_ON_START_TOOLTIP": "Automatically scan all images in the "
        "folder on startup.",
        "SETTINGS_PERSON_TAGS_TOOLTIP": "Default tags for people, separated by commas.",
        "SETTINGS_FACE_ENGINE_TOOLTIP": "Library used for face detection (MediaPipe "
        "recommended).",
        "SETTINGS_FACE_COLOR_TOOLTIP": "Color of the bounding box drawn around "
        "detected faces.",
        "SETTINGS_MRU_TAGS_TOOLTIP": "Maximum number of recently used tags to "
        "remember.",
        "SETTINGS_FACE_HISTORY_TOOLTIP": "Maximum number of recently used face names "
        "to remember.",
        "SETTINGS_THUMBS_REFRESH_TOOLTIP": "Delay in milliseconds before refreshing "
        "thumbnails after resizing.",
        "SETTINGS_THUMBS_BG_COLOR_TOOLTIP": "Background color of the thumbnail grid "
        "view.",
        "SETTINGS_THUMBS_FILENAME_COLOR_TOOLTIP": "Font color for filenames in "
        "thumbnails.",
        "SETTINGS_THUMBS_TAGS_COLOR_TOOLTIP": "Font color for tags in thumbnails.",
        "SETTINGS_THUMBS_RATING_COLOR_TOOLTIP": "Color for rating stars in thumbnails.",
        "SETTINGS_THUMBS_FILENAME_FONT_SIZE_TOOLTIP": "Font size for filenames in "
        "thumbnails.",
        "SETTINGS_THUMBS_TAGS_FONT_SIZE_TOOLTIP": "Font size for tags in thumbnails.",
        "SEARCH_ENGINE_NATIVE": "Bagheera",
        "SEARCH_ENGINE_BALOO": "Baloo",
        "SETTINGS_VIEWER_WHEEL_SPEED_LABEL": "Viewer mouse wheel speed:",
        "SETTINGS_THUMBS_FILENAME_LINES_LABEL": "Filename lines:",
        "SETTINGS_THUMBS_FILENAME_LINES_TOOLTIP": "Number of lines for the filename "
        "text under the thumbnail.",
        "SETTINGS_THUMBS_TAGS_LINES_LABEL": "Tag lines:",
        "SETTINGS_THUMBS_TOOLTIP_BG_COLOR_LABEL": "Tooltip background color:",
        "SETTINGS_THUMBS_TOOLTIP_FG_COLOR_LABEL": "Tooltip text color:",
        "SETTINGS_THUMBS_TOOLTIP_FG_COLOR_TOOLTIP": "Text color for tooltips on "
        "thumbnails.",
        "SETTINGS_THUMBS_TOOLTIP_BG_COLOR_TOOLTIP": "Background color for tooltips on "
        "thumbnails.",
        "SETTINGS_THUMBS_TAGS_LINES_TOOLTIP": "Number of lines for the tags text under "
        "the thumbnail.",
        "SETTINGS_THUMBS_SHOW_FILENAME_LABEL": "Show filename",
        "SETTINGS_THUMBS_SHOW_RATING_LABEL": "Show rating",
        "SETTINGS_THUMBS_SHOW_TAGS_LABEL": "Show tags",
        "SETTINGS_THUMBS_SHOW_FILENAME_TOOLTIP": "Show or hide the filename under the "
        "thumbnail.",
        "SETTINGS_THUMBS_SHOW_RATING_TOOLTIP": "Show or hide the rating stars under "
        "the thumbnail.",
        "SETTINGS_THUMBS_SHOW_TAGS_TOOLTIP": "Show or hide the tags under the "
        "thumbnail.",
        "SETTINGS_VIEWER_WHEEL_SPEED_TOOLTIP": "Adjusts how fast scrolling the mouse "
        "wheel changes images in the viewer.",
        "SETTINGS_VIEWER_AUTO_RESIZE_LABEL": "Auto resize window on zoom",
        "SETTINGS_VIEWER_AUTO_RESIZE_TOOLTIP": "Automatically resize the window when "
        "zooming or changing images, fitting to the content.",
        "SETTINGS_DOWNLOAD_MEDIAPIPE_MODEL": "Download Model",
        "SETTINGS_DOWNLOAD_MEDIAPIPE_MODEL_TOOLTIP": "Download the required model file "
        "for MediaPipe face detection.",
        "MEDIAPIPE_DOWNLOADING_TITLE": "Downloading Model",
        "MEDIAPIPE_DOWNLOADING_TEXT": "Downloading MediaPipe face detection model...",
        "MEDIAPIPE_DOWNLOAD_SUCCESS_TITLE": "Download Complete",
        "MEDIAPIPE_DOWNLOAD_SUCCESS_TEXT": "The MediaPipe model has been downloaded "
        "successfully.",
        "MEDIAPIPE_DOWNLOAD_ERROR_TITLE": "Download Error",
        "MEDIAPIPE_DOWNLOAD_ERROR_TEXT": "Failed to download the MediaPipe model: {}",
        "MENU_FILMSTRIP_POSITION": "Filmstrip Position",
        "FILMSTRIP_BOTTOM": "Bottom",
        "VIEWER_MENU_COMPARE": "Comparison Mode",
        "FILMSTRIP_LEFT": "Left",
        "FILMSTRIP_TOP": "Top",
        "FILMSTRIP_RIGHT": "Right",
        "FILMSTRIP_POS_CHANGED_INFO": "The new filmstrip position will be applied to "
        "newly opened viewers.",
        "MENU_SHOW_SHORTCUTS": "Configure Keyboard Shortcuts...",
        "VIEWER_MENU_MANIPULATE": "Manipulate",
        "VIEWER_MENU_ZOOM": "Zoom",
        "SAVE_CROP_TITLE": "Save Cropped Image",
        "COMPARE_LINKED": " [Linked]",
        "COMPARE_UNLINKED": " [Unlinked]",
        "CROP_INDICATOR": " [CROP]",
        "OPEN_WITH_OTHER": "Open with other application...",
        "COLLAPSE_EXPAND_GROUP": "Collapse/Expand Group",
        "MENU_TOGGLE_MAIN_WINDOW": "Show/Hide Main Window",
        "LOADING_DATA": "Loading data...",
        "SETTINGS_PLACEHOLDER_TAGS": "tag1, tag2, tag3/subtag",
        "THUMBNAILS_GENERATE_PROGRESS": "Generating {}px thumbnails: {}/{}",
        "THUMBNAILS_REGENERATE_PROGRESS": "Regenerating thumbnail: {}/{}",
        "SHORTCUTS_TITLE": "Keyboard Shortcuts",
        "SHORTCUTS_ACTION": "Action",
        "SHORTCUTS_KEY": "Shortcut",
        "CLOSE": "Close",
        "SHORTCUT_EDIT_TITLE": "Change Shortcut",
        "SHORTCUT_EDIT_LABEL": "Enter new shortcut for '{}'",
        "SHORTCUT_CONFLICT_TITLE": "Shortcut Conflict",
        "SHORTCUT_CONFLICT_TEXT": "The shortcut '{}' is already assigned to '{}'.",
        "SHORTCUT_OVERRIDE_QUESTION": "Do you want to override it?",
        "SHORTCUT_SEARCH_PLACEHOLDER": "Search shortcuts...",
        "CACHE_CLEANING": "Cleaning cache...",
        "CACHE_CLEANED": "Cache cleaned. Removed {} invalid entries.",
        "CACHE_CLEARED": "Thumbnail cache cleared.",
        "ERROR_DELETING_FILE": "Error trying to delete file:\n{}",
        "RENAME_FILE_TITLE": "Rename File",
        "RENAME_FILE_TEXT": "New name for '{}':",
        "RENAME_ERROR_TITLE": "Rename Error",
        "RENAME_ERROR_EXISTS": "File '{}' already exists.",
        "FILE_RENAMED": "File renamed to {}",
        "CONFIRM_CLEAR_CACHE_TITLE": "Confirm Clear Cache",
        "CONFIRM_CLEAR_CACHE_TEXT": "Are you sure you want to permanently delete the "
        "entire thumbnail cache?",
        "CONFIRM_CLEAR_CACHE_INFO": "This will remove all cached thumbnails from "
        "memory and disk. They will be regenerated as you browse, which may be slow. "
        "This action cannot be undone.",
        "CONFIRM_DELETE_TITLE": "Confirm Permanent Deletion",
        "CONFIRM_DELETE_TEXT": "Do you want to permanently delete this image?",
        "CONFIRM_DELETE_INFO": "File: {}\n\nThis action CANNOT be undone.",
        "SYSTEM_ERROR": "System Error",
        "ERROR_DELETING_FILE": "Error trying to delete file:\n{}",
        "RENAME_FILE_TITLE": "Rename File",
        "RENAME_FILE_TEXT": "New name for '{}':",
        "RENAME_ERROR_TITLE": "Rename Error",
        "RENAME_ERROR_EXISTS": "File '{}' already exists.",
        "FILE_RENAMED": "File renamed to {}",
        "ERROR_RENAME": "Could not rename file: {}",
        "ERROR_JPEG_METADATA_LIMIT": "Metadata size limit exceeded for '{}'. This "
        "JPEG file has too much existing metadata (XMP) to save more.",
        "MAIN_DOCK_TITLE": "",
        "LAYOUTS_TAB": "Layouts",
        "LAYOUTS_TABLE_HEADER": ["Name", "Last Modified"],
        "SAVE_LAYOUT_TITLE": "Save Layout",
        "SAVE_LAYOUT_TEXT": "Enter name for layout:",
        "LAYOUT_EXISTS_TITLE": "Layout already exists",
        "LAYOUT_EXISTS_TEXT": "Do you want to overwrite layout \"{}\"?",
        "LAYOUT_EXISTS_INFO": "This action CANNOT be undone.",
        "LAYOUT_SAVED": "Layout '{0}' saved.",
        "ERROR_SAVING_LAYOUT": "Could not save layout: {}",
        "LOAD_LAYOUT_TITLE": "Load Layout",
        "NO_LAYOUTS_FOUND": "No saved layouts found.",
        "SELECT_LAYOUT": "Select layout:",
        "LAYOUT_RESTORED": "Layout restored.",
        "ERROR_LOADING_LAYOUT_TITLE": "{}: Error",
        "ERROR_LOADING_LAYOUT_TEXT": "Failed to load layout file:\n\"{}\"",
        "RENAME_LAYOUT_TITLE": "Rename Layout",
        "RENAME_LAYOUT_TEXT": "New Name:",
        "COPY_LAYOUT_TITLE": "Copy Layout",
        "COPY_LAYOUT_TEXT": "New Name:",
        "LAYOUT_ALREADY_EXISTS": "Layout already exists.",
        "CONFIRM_DELETE_LAYOUT_TITLE": "Confirm Delete",
        "CONFIRM_DELETE_LAYOUT_TEXT": "Delete layout '{}'?",
        "INFO_TAB": "Information",
        "INFO_RATING_LABEL": "Rating:",
        "INFO_COMMENT_LABEL": "Comment:",
        "COMMENT_APPLY_CHANGES": "Apply Changes",
        "ENTER_COMMENT": "Enter comment...",
        "TAGS_TAB": "Tags",
        "TAG_FILTER_TAB": "Filter",
        "TAG_SEARCH_PLACEHOLDER": "Search tags...",
        "TAG_APPLY_CHANGES": "Apply Changes",
        "TAG_USED_TAGS": "⭐ USED TAGS",
        "TAG_ALL_TAGS": "📂 ALL TAGS",
        "TAG_NEW_TAG_TITLE": "New Tag",
        "SEARCH_BY_TAG": "Search by this tag",
        "TAG_ADD_TOOLTIP": "Create a new tag",
        "TAG_REFRESH_TOOLTIP": "Refresh available tags from Baloo database",
        "TAG_NEW_TAG_TEXT": "Enter tag name (use / for hierarchy):",
        "SEARCH_ADD_AND": "Add AND this tag to search",
        "SEARCH_ADD_OR": "Add OR this tag to search",
        "FILTER_AND": "AND",
        "FILTER_OR": "OR",
        "FILTER_INVERT": "Invert",
        "FILTER_TAG_COLUMN": "Tag",
        "FILTER_NOT_COLUMN": "NOT",
        "FILTER_STATS_HIDDEN": "{} items hidden",
        "FILTER_NAME_PLACEHOLDER": "Filter by filename...",
        "HISTORY_TAB": "History",
        "HISTORY_TABLE_HEADER": ["Name", "Date"],
        "HISTORY_BTN_CLEAR_ALL_TOOLTIP": "Clear All",
        "HISTORY_BTN_DELETE_SELECTED_TOOLTIP": "Delete Selected",
        "HISTORY_BTN_DELETE_OLDER_TOOLTIP": "Delete Older",
        "HISTORY_CLEAR_ALL_TITLE": "Confirm",
        "HISTORY_CLEAR_ALL_TEXT": "Clear entire history?",
        "PROPERTIES_TITLE": "Properties",
        "PROPERTIES_GENERAL_TAB": "General",
        "PROPERTIES_METADATA_TAB": "Metadata",
        "PROPERTIES_EXIF_TAB": "EXIF",
        "PROPERTIES_FILENAME": "File Name:",
        "PROPERTIES_LOCATION": "Location:",
        "PROPERTIES_SIZE": "Size:",
        "PROPERTIES_CREATED": "Created:",
        "PROPERTIES_MODIFIED": "Modified:",
        "PROPERTIES_DIMENSIONS": "Dimensions:",
        "PROPERTIES_FORMAT": "Format:",
        "PROPERTIES_MEGAPIXELS": "Megapixels:",
        "PROPERTIES_COLOR_DEPTH": "Color Depth:",
        "BITS": "bits",
        "PROPERTIES_TABLE_HEADER": ["Property", "Value"],
        "PROPERTIES_ADD_ATTR": "Add Attribute",
        "PROPERTIES_ADD_ATTR_NAME": "Attribute Name (e.g. user.comment):",
        "PROPERTIES_DELETE_ALL": "Delete All",
        "PROPERTIES_ADD_ATTR_VALUE": "Value for {}:",
        "PROPERTIES_ERROR_SET_ATTR": "Failed to set xattr: {}",
        "PROPERTIES_ERROR_ADD_ATTR": "Failed to add xattr: {}",
        "PROPERTIES_DELETE_ATTR": "Delete Attribute",
        "PROPERTIES_ERROR_DELETE_ATTR": "Failed to remove xattr: {}",
        "EXIV2_NOT_INSTALLED": "exiv2 library not installed. Install python exiv2.",
        "NO_METADATA_FOUND": "No metadata found (EXIF/XMP/IPTC).",
        "VIEWER_MENU_SLIDESHOW": "Slideshow",
        "VIEWER_MENU_STOP_SLIDESHOW": "Stop Slideshow",
        "VIEWER_MENU_START_SLIDESHOW": "Start Slideshow",
        "VIEWER_MENU_START_REVERSE_SLIDESHOW": "Start Reverse Slideshow",
        "VIEWER_MENU_STOP_REVERSE_SLIDESHOW": "Stop Reverse Slideshow",
        "VIEWER_MENU_SET_INTERVAL": "Set Interval...",
        "VIEWER_MENU_ROTATE": "Rotate",
        "VIEWER_MENU_ROTATE_LEFT": "Left",
        "VIEWER_MENU_ROTATE_RIGHT": "Right",
        "VIEWER_MENU_EXIT_FULLSCREEN": "Exit Fullscreen ",
        "VIEWER_MENU_ENTER_FULLSCREEN": "Fullscreen",
        "VIEWER_MENU_RENAME": "Rename",
        "VIEWER_MENU_FIT_SCREEN": "Fit to Screen / Actual Size",
        "VIEWER_MENU_SHOW_FILMSTRIP": "Show Filmstrip",
        "VIEWER_MENU_FLIP": "Flip",
        "VIEWER_MENU_FLIP_H": "Horizontal",
        "VIEWER_MENU_PAUSE_ANIMATION": "Pause Animation",
        "VIEWER_MENU_RESUME_ANIMATION": "Resume Animation",
        "VIEWER_MENU_FLIP_V": "Vertical",
        "VIEWER_MENU_SHOW_STATUSBAR": "Show Status Bar",
        "VIEWER_MENU_TAGS": "Quick tags",
        "VIEWER_MENU_CROP": "Crop Mode",
        "VIEWER_MENU_SAVE_CROP": "Save Selection...",
        "VIEWER_MENU_COPY_PATH": "Copy File Path",
        "VIEWER_MENU_COPY_IMAGE": "Copy Image to Clipboard",
        "VIEWER_MENU_DETECT_AREAS": "Regions management",
        "VIEWER_MENU_DETECT_FACES": "Detect faces",
        "VIEWER_MENU_DETECT_PETS": "Detect pets",
        "VIEWER_MENU_ADD_FACE": "Add face",
        "VIEWER_MENU_ADD_PET": "Add pet",
        "VIEWER_MENU_ADD_BODY": "Add body",
        "VIEWER_MENU_ADD_OBJECT": "Add object",
        "VIEWER_MENU_ADD_LANDMARK": "Add landmark",
        "VIEWER_MENU_MANIPULATE": "Manipulate",
        "VIEWER_MENU_ZOOM": "Zoom",
        "VIEWER_MENU_ZOOM_IN": "Zoom In",
        "VIEWER_MENU_ZOOM_OUT": "Zoom Out",
        "SAVE_CROP_TITLE": "Save Cropped Image",
        "VIEWER_MENU_COMPARE": "Comparison Mode",
        "VIEWER_MENU_COMPARE_1": "Single View",
        "VIEWER_MENU_COMPARE_2": "2 Images",
        "VIEWER_MENU_COMPARE_4": "4 Images",
        "VIEWER_MENU_LINK_PANES": "Link Panes",
        "SAVE_CROP_FILTER": "Images (*.jpg *.jpeg *.png *.bmp *.webp)",
        "SLIDESHOW_INTERVAL_TITLE": "Slideshow Interval",
        "SLIDESHOW_INTERVAL_TEXT": "Seconds:",
        "CONTEXT_MENU_VIEW": "View",
        "CONTEXT_MENU_OPEN": "Open",
        "CONTEXT_MENU_OPEN_SEARCH_LOCATION": "Open and search location",
        "CONTEXT_MENU_OPEN_DEFAULT_APP": "Open location with Dolphin",
        "CONTEXT_MENU_OPEN_BAGHEERAVIEW": "Open location with BagheeraView",
        "CONTEXT_MENU_FULLSCREEN_VIEWER": "Open in Fullscreen Viewer",
        "CONTEXT_MENU_MOVE_TO": "Move to...",
        "CONTEXT_MENU_COPY_TO": "Copy to...",
        "CONTEXT_MENU_ROTATE": "Rotate",
        "CONTEXT_MENU_ROTATE_LEFT": "Left",
        "CONTEXT_MENU_ROTATE_RIGHT": "Right",
        "CONTEXT_MENU_TRASH": "Move to Trash",
        "CONTEXT_MENU_CLIPBOARD": "Clipboard",
        "CONTEXT_MENU_COPY_FILE": "Copy File URL",
        "CONTEXT_MENU_COPY_DIR": "Copy Directory Path",
        "CONTEXT_MENU_PROPERTIES": "Properties",
        "CONTEXT_MENU_NO_APPS_FOUND": "No apps found",
        "CONTEXT_MENU_REGENERATE": "Regenerate Thumbnail",
        "CONTEXT_MENU_ERROR_LISTING_APPS": "Error listing apps",
        "CONTEXT_MENU_RENAME": "Rename...",
        "CONTEXT_MENU_DELETE": "Delete",
        "CONTEXT_MENU_SELECT_ALL": "Select All",
        "CONTEXT_MENU_SELECT_NONE": "Select None",
        "CONTEXT_MENU_INVERT_SELECTION": "Invert Selection",
        "CONFIRM_OVERWRITE_TITLE": "Confirm Overwrite",
        "CONFIRM_OVERWRITE_TEXT": "File already exists in destination:\n{}\n\nDo "
        "you want to overwrite it?",
        "ERROR_MOVE_FILE": "Could not move file: {}",
        "ERROR_COPY_FILE": "Could not copy file: {}",
        "MOVED_TO": "Moved to {}",
        "FS_WATCHER_TOOLTIP": "File System Watcher (monitoring active directories)",
        "COPIED_TO": "Copied to {}",
        "ERROR_ROTATE_IMAGE": "Could not rotate image: {}",
        "PREPARING_QUERY": "Preparing query...",
    },
    "es": {
        "READY": "Listo",
        "SEARCH": "Buscar",
        "SELECT": "Seleccionar",
        "ERROR": "Error",
        "FILE_NOT_FOUND": "Archivo no encontrado",
        "WARNING": "Advertencia",
        "INFO": "Información",
        "LOAD": "Cargar",
        "SAVE": "Guardar",
        "CREATE": "Crear",
        "CANCEL": "Cancelar",
        "RENAME": "Renombrar",
        "COPY": "Copiar",
        "DELETE": "Eliminar",
        "UNKNOWN": "Desconocido",
        "MENU_LANGUAGE": "Idioma",
        "RESTART_REQUIRED_TITLE": "Reinicio Requerido",
        "RESTART_REQUIRED_TEXT": "El idioma se ha cambiado a {language}.\nPor favor, "
        "reinicie la aplicación para que los cambios surtan efecto.",
        "SORT_NAME_ASC": "Nombre ↑",
        "SORT_NAME_DESC": "Nombre ↓",
        "SORT_DATE_ASC": "Fecha ↑",
        "SORT_DATE_DESC": "Fecha ↓",
        "VIEW_MODE_FLAT": "Plano",
        "MENU_VIEW_MODE": "Modo de Vista",
        "FILTERED_COUNT": "Filtrados: {}",
        "VIEW_MODE_DAY": "Separar por Día",
        "VIEW_MODE_WEEK": "Separar por Semana",
        "MENU_FIND_SIMILAR": "Buscar imágenes similares",
        "SIMILAR_SEARCH_TITLE": "Imágenes similares a '{}'",
        "SIMILAR_SEARCH_PROGRESS": "Buscando imágenes similares: {} encontradas...",
        "RESCAN": "Buscar de nuevo",
        "VIEW_MODE_MONTH": "Separar por Mes",
        "VIEW_MODE_YEAR": "Separar por Año",
        "VIEW_MODE_RATING": "Separar por Valoración",
        "FILTERED_ZERO": "Filtrados: 0",
        "VIEW_MODE_FOLDER": "Separar por Carpeta",
        "LOAD_MORE_TOOLTIP": f"Cargar {APP_CONFIG.get('scan_batch_size', 64)} imágenes "
        "más (Ctrl+D)",
        "LOAD_ALL_TOOLTIP": "Cargar todas las imágenes (Ctrl+Shift+D)",
        "LOAD_ALL_TOOLTIP_ALT": "Cancelar cargar todas las images (Ctrl+Shift+D)",
        "CONFIRM_LOAD_ALL_TITLE": "Confirmar carga",
        "CONFIRM_LOAD_ALL_TEXT": "¿Seguro que quieres cargar las {} imágenes "
        "restantes?",
        "DONE_SCAN": "Hecho: {} imágenes",
        "LOADING_SCAN": "Cargando... {} / {}",
        "GROUP_HEADER_FORMAT": "{group_name} - {count} fotos",
        "GROUP_HEADER_FORMAT_SINGULAR": "{group_name} - 1 foto",
        "GROUP_BY_WEEK_FORMAT": "{year} - Semana {week}",
        "GROUP_BY_RATING_FORMAT": "{stars} Estrellas",
        "SHUTTING_DOWN": "Cerrando...",
        "LOADED_PARTIAL": "Cargadas {} / {}",
        "HIGH_RES_GENERATED": "Miniaturas de alta resolución generadas.",
        "SCANNING_DIRS": "Escaneando directorios...",
        "SELECT_IMAGE_TITLE": "Seleccionar Imagen",
        "VIEWER_TITLE_PAUSED": " [Pausado]",
        "IMAGE_NOT_IN_VIEW": "La imagen '{}' no está en la vista actual.",
        "VIEWER_TITLE_SLIDESHOW": " [Presentación]",
        "RENAME_VIEWER_TITLE": "Renombrar Archivo",
        "RENAME_VIEWER_TEXT": "Nuevo nombre para '{}':",
        "RENAME_VIEWER_ERROR_EXISTS": "El archivo '{}' ya existe.",
        "RENAME_VIEWER_ERROR_SYSTEM": "Error de Sistema",
        "RENAME_VIEWER_ERROR_TEXT": "No se pudo renombrar el archivo: {}",
        "ADD_FACE_TITLE": "Añadir Rostro",
        "ADD_PET_TITLE": "Añadir Mascota",
        "ADD_BODY_TITLE": "Añadir Cuerpo",
        "ADD_OBJECT_TITLE": "Añadir Objeto",
        "ADD_LANDMARK_TITLE": "Añadir Lugar",
        "ADD_FACE_LABEL": "Nombre:",
        "ADD_PET_LABEL": "Nombre:",
        "ADD_BODY_LABEL": "Nombre:",
        "ADD_OBJECT_LABEL": "Nombre:",
        "ADD_LANDMARK_LABEL": "Nombre:",
        "NEXT_AREA": "Próxima región: {}",
        "DELETE_AREA_TITLE": "Eliminar región",
        "CREATE_TAG_TITLE": "Crear Etiqueta",
        "CREATE_TAG_TEXT": "La etiqueta para '{}' no existe. ¿Deseas crear una nueva?",
        "NEW_PERSON_TAG_TITLE": "Nueva Etiqueta de Persona",
        "NEW_PERSON_TAG_TEXT": "Introduce la ruta completa de la etiqueta:",
        "NEW_PET_TAG_TITLE": "Nueva Etiqueta de Mascota",
        "NEW_PET_TAG_TEXT": "Introduce la ruta completa de la etiqueta:",
        "NEW_BODY_TAG_TITLE": "Nueva Etiqueta de Cuerpo",
        "NEW_BODY_TAG_TEXT": "Introduce la ruta completa de la etiqueta:",
        "NEW_OBJECT_TAG_TITLE": "Nueva Etiqueta de Objeto",
        "NEW_OBJECT_TAG_TEXT": "Introduce la ruta completa de la etiqueta:",
        "NEW_LANDMARK_TAG_TITLE": "Nueva Etiqueta de Lugar",
        "NEW_LANDMARK_TAG_TEXT": "Introduce la ruta completa de la etiqueta:",
        "SELECT_TAG_TITLE": "Seleccionar Etiqueta",
        "SELECT_TAG_TEXT": "Se encontraron múltiples etiquetas para '{}'. Por favor, "
        "selecciona la correcta:",
        "FACE_NAME_TOOLTIP": "Escribe un nombre o selecciónalo del historial.",
        "CLEAR_TEXT_TOOLTIP": "Limpiar el campo de texto",
        "RENAME_AREA_TITLE": "Renombrar región",
        "SHOW_FACES": "Mostrar Rostros y otras regiones",
        "DETECT_FACES": "Detectar Rostros",
        "DETECT_PETS": "Detectar Mascotas",
        "DETECT_BODIES": "Detectar Cuerpos",
        "NO_FACE_LIBS": "No se encontraron librerías de detección de rostros. Instale "
        "'mediapipe' o 'face_recognition'.",
        "THUMBNAIL_NO_NAME": "Sin nombre",
        "THUMBNAIL_NO_TAGS": "Sin etiquetas",
        "MENU_ABOUT": "Acerca de",
        "MENU_ABOUT_TITLE": "Acerca de {}",
        "MENU_ABOUT_TEXT": "<b>{0}</b> v{1}<br><br>Un visor y gestor de imágenes "
        "simple para KDE con soporte para Baloo.<br><br>Creado por {2} con la ayuda de "
        "la IA, pero mayormente gracias al trabajo de la buena gente de KDE y Qt.",
        "MENU_CACHE": "Caché",
        "MENU_CLEAR_CACHE": "Limpiar caché ({} ítems, {:.1f} MB, {:.1f} MB en disco)",
        "MENU_CLEAN_CACHE": "Limpiar entradas de caché inválidas",
        "MENU_CLEAN_METADATA_CACHE": "Limpiar caché de metadatos obsoletos",
        "MENU_CLEAN_DIRECTORY_CACHE": "Limpiar caché de directorios obsoletos",
        "MENU_SHOW_TAGS": "Mostrar Etiquetas",
        "MENU_SHOW_INFO": "Mostrar Información",
        "MENU_SHOW_FAVORITES": "Mostrar Favoritos",
        "FAVORITES_TAB": "Favoritos",
        "FAVORITES_SEARCH_PLACEHOLDER": "Buscar favoritos...",
        "FAVORITES_TABLE_HEADER": ["Comentario", "Consulta", "Atajo"],
        "ADD_FAVORITE_TOOLTIP": "Añadir búsqueda actual a favoritos",
        "EDIT_COMMENT_TITLE": "Editar Comentario",
        "EDIT_COMMENT_TEXT": "Comentario para '{}':",
        "EDIT_SHORTCUT_TITLE": "Asignar Atajo",
        "EDIT_SHORTCUT_TEXT": "Pulsa las teclas para '{}':",
        "MOVE_UP": "Subir",
        "MOVE_DOWN": "Bajar",
        "MENU_SHOW_FILTER": "Mostrar Filtro",
        "MENU_SHOW_LAYOUTS": "Mostrar Diseños",
        "MENU_SHOW_HISTORY": "Mostrar Historial",
        "MENU_SETTINGS": "Opciones",
        "SETTINGS_GROUP_DUPLICATES": "Duplicados",
        "MENU_DUPLICATES": "Duplicados",
        "MENU_DETECT_CURRENT_SEARCH": "Detectar en búsqueda actual",
        "MENU_DETECT_ALL": "Detectar todos",
        "MENU_FORCE_FULL_ALL_ANALYSIS": "Forzar análisis completo de todo",
        "MENU_FORCE_FULL_ANALYSIS": "Forzar análisis completo",
        "MENU_REVIEW_IGNORED": "Revisar ignorados",
        "MENU_CLEAN_UP_HASHES": "Limpiar",
        "MENU_REPAIR_DATABASE": "Reparar índice",
        "MENU_CLEAR_EXCEPTIONS": "Limpiar parejas ignoradas",
        "CONFIRM_CLEAR_EXCEPTIONS_TITLE": "Confirmar Limpieza de Ignorados",
        "CONFIRM_CLEAR_EXCEPTIONS_TEXT": "¿Seguro que quieres borrar todas las parejas "
        "de duplicados ignoradas? Se volverán a detectar en el próximo escaneo.",
        "REPAIRING_DATABASE": "Reparando índice de duplicados...",
        "MENU_CLEAR_HASHES": "Limpiar hashes ({} ítems, {:.1f} MB en disco)",
        "CONFIRM_CLEAR_HASHES_TITLE": "Confirmar Limpieza de Hashes",
        "CONFIRM_CLEAR_HASHES_TEXT": "¿Seguro que quieres eliminar permanentemente "
        "toda la base de datos de hashes?",
        "CONFIRM_CLEAR_HASHES_INFO": "Esto eliminará todos los hashes de imágenes "
        "calculados. Se recalcularán a medida que detectes duplicados, lo que puede "
        "ser lento. Esta acción no se puede deshacer.",
        "SETTINGS_DUPLICATE_METHOD_LABEL": "Método:",
        "SETTINGS_DUPLICATE_METHOD_TOOLTIP": "Selecciona el método para la detección "
        "de duplicados.",
        "METHOD_HISTOGRAM_HASHING": "Histograma + Hashing",
        "METHOD_RESNET": "ResNet (Basado en IA)",
        "SETTINGS_DUPLICATE_CONFIRM_DELETE_LABEL": "Confirmar antes de borrar "
        "duplicados",
        "SETTINGS_DUPLICATE_WHITELIST_LABEL": "Lista blanca (carpetas a incluir):",
        "SETTINGS_DUPLICATE_WHITELIST_TOOLTIP": "Rutas de carpetas separadas por comas "
        "para escanear al usar 'Detectar todos'.",
        "SETTINGS_DUPLICATE_BLACKLIST_LABEL": "Lista negra (carpetas a excluir):",
        "SETTINGS_DUPLICATE_BLACKLIST_TOOLTIP": "Rutas de carpetas separadas por comas "
        "para ignorar durante escaneos de 'Detectar todos'.",
        "SETTINGS_DUPLICATE_SCAN_COUNT_LABEL": "Imágenes encontradas para 'Detectar "
        "todos': {}",
        "SETTINGS_DEFAULT_DELETE_TO_TRASH_LABEL": "La tecla Supr envía a la papelera "
        "por defecto",
        "SETTINGS_DEFAULT_DELETE_TO_TRASH_TOOLTIP": "Si está marcada, al pulsar la "
        "tecla Supr se moverán los archivos a la papelera. Si no, se eliminarán "
        "permanentemente.",
        "SETTINGS_DUPLICATE_CONFIRM_DELETE_TOOLTIP": "Muestra un diálogo de "
        "confirmación antes de mover una imagen duplicada a la papelera.",
        "SETTINGS_DUPLICATE_THRESHOLD_LABEL": "Umbral de Similitud:",
        "SETTINGS_DUPLICATE_THRESHOLD_TOOLTIP": "Establece el umbral de similitud "
        "(50-100%). Valores más altos significan que las imágenes deben ser más "
        "parecidas para considerarse duplicadas.",
        "SETTINGS_DUPLICATE_MISSING_LIBS": "La librería 'imagehash' es necesaria "
        "para la detección de duplicados pero no se ha encontrado. Esta función "
        "está desactivada.",
        "MENU_DETECT_DUPLICATES": "Detectar Duplicados",
        "DUPLICATE_WHITELIST_EMPTY": "La lista blanca está vacía. Por favor, "
        "configúrela en Opciones.",
        "DUPLICATE_DETECTION_TITLE": "Detección de Duplicados",
        "DUPLICATE_ALREADY_RUNNING": "La detección de duplicados ya está en curso.",
        "DUPLICATE_NO_IMAGES": "No hay imágenes cargadas para detectar duplicados.",
        "DUPLICATE_STARTING": "Iniciando detección de duplicados...",
        "DUPLICATE_PROGRESS": "Detección de duplicados: {message} ({current}/{total})",
        "DUPLICATE_NONE_FOUND": "No se encontraron duplicados.",
        "DUPLICATE_FOUND_TITLE": "Duplicados Encontrados",
        "DUPLICATE_FOUND_MSG": "Se encontraron los siguientes duplicados:\n",
        "DUPLICATE_FOUND_MORE": "... y {count} más.",
        "DUPLICATE_FINISHED": "Detección de duplicados finalizada.",
        "DUPLICATE_MSG_HASHING": "Procesando {filename}",
        "DUPLICATE_MSG_ANALYZING": "Analizando {filename}",
        "DUPLICATE_MANAGER_TITLE": "Gestionar Imágenes Duplicadas",
        "DUPLICATE_DELETE_LEFT": "Papelera Izquierda",
        "DUPLICATE_DELETE_RIGHT": "Papelera Derecha",
        "CONFIRM_TRASH_TITLE": "Mover a la papelera",
        "CONFIRM_TRASH_TEXT": "¿Deseas mover esta imagen a la papelera?",
        "DUPLICATE_KEEP_BOTH": "Mantener Ambas (Ignorar)",
        "DUPLICATE_SKIP": "Omitir",
        "DUPLICATE_REMOVE_IGNORED": "Eliminar de ignorados",
        "DUPLICATE_INFO_FORMAT": "{size} - {width}x{height}",
        "VIEWER_MENU_LINK_PANES": "Vincular Paneles",
        "DUPLICATE_OPEN_COMPARISON": "Abrir Comparación",
        "DUPLICATE_LIST_HEADER": "Parejas Duplicadas",
        "IGNORED_DATE": "Fecha Ignorado",
        "SETTINGS_GROUP_SCANNER": "Escáner",
        "SETTINGS_GROUP_REGIONS": "Regiones",
        "SETTINGS_GROUP_THUMBNAILS": "Miniaturas",
        "SETTINGS_GROUP_VIEWER": "Visor de Imágenes",
        "SETTINGS_PERSON_TAGS_LABEL": "Etiquetas de persona:",
        "SETTINGS_FACE_ENGINE_LABEL": "Motor de detección de caras:",
        "SETTINGS_FACE_COLOR_LABEL": "Color del recuadro de cara:",
        "SETTINGS_MRU_TAGS_COUNT_LABEL": "Máximo número de etiquetas recientes:",
        "SETTINGS_PET_TAGS_LABEL": "Etiquetas de mascota:",
        "SETTINGS_PET_ENGINE_LABEL": "Motor de detección de mascotas:",
        "SETTINGS_PET_COLOR_LABEL": "Color del recuadro de mascota:",
        "SETTINGS_PET_HISTORY_COUNT_LABEL": "Máximo historial de mascotas:",
        "SETTINGS_PET_TAGS_TOOLTIP": "Etiquetas predeterminadas para mascotas, "
        "separadas por comas.",
        "SETTINGS_PET_ENGINE_TOOLTIP": "Librería utilizada para la detección de "
        "mascotas.",
        "SETTINGS_PET_COLOR_TOOLTIP": "Color del cuadro delimitador dibujado "
        "alrededor de las mascotas detectadas.",
        "SETTINGS_PET_HISTORY_TOOLTIP": "Número máximo de nombres de mascotas "
        "usados recientemente para recordar.",
        "TYPE_FACE": "Cara",
        "TYPE_PET": "Mascota",
        "TYPE_BODY": "Cuerpo",
        "TYPE_OBJECT": "Objeto",
        "TYPE_LANDMARK": "Lugar",
        "SETTINGS_BODY_TAGS_LABEL": "Etiquetas de cuerpo:",
        "SETTINGS_BODY_ENGINE_LABEL": "Motor de detección de cuerpos:",
        "SETTINGS_BODY_COLOR_LABEL": "Color del recuadro de cuerpo:",
        "SETTINGS_BODY_HISTORY_COUNT_LABEL": "Máximo historial de cuerpos:",
        "SETTINGS_BODY_TAGS_TOOLTIP": "Etiquetas predeterminadas para cuerpos, "
        "separadas por comas.",
        "SETTINGS_BODY_ENGINE_TOOLTIP": "Librería utilizada para la detección de "
        "cuerpos.",
        "SETTINGS_BODY_COLOR_TOOLTIP": "Color del cuadro delimitador dibujado "
        "alrededor de los cuerpos detectados.",
        "SETTINGS_BODY_HISTORY_TOOLTIP": "Número máximo de nombres de cuerpos "
        "usados recientemente para recordar.",
        "SETTINGS_OBJECT_TAGS_LABEL": "Etiquetas de objeto:",
        "SETTINGS_OBJECT_ENGINE_LABEL": "Motor de detección de objetos:",
        "SETTINGS_OBJECT_COLOR_LABEL": "Color del recuadro de objeto:",
        "SETTINGS_OBJECT_HISTORY_COUNT_LABEL": "Máximo historial de objetos:",
        "SETTINGS_OBJECT_TAGS_TOOLTIP": "Etiquetas predeterminadas para objetos, "
        "separadas por comas.",
        "SETTINGS_OBJECT_ENGINE_TOOLTIP": "Librería utilizada para la detección "
        "de objetos.",
        "SETTINGS_OBJECT_COLOR_TOOLTIP": "Color del cuadro delimitador dibujado "
        "alrededor de los objetos.",
        "SETTINGS_OBJECT_HISTORY_TOOLTIP": "Número máximo de nombres de objetos "
        "usados recientemente para recordar.",
        "SETTINGS_LANDMARK_TAGS_LABEL": "Etiquetas de lugar:",
        "SETTINGS_LANDMARK_ENGINE_LABEL": "Motor de detección de lugares:",
        "SETTINGS_LANDMARK_COLOR_LABEL": "Color del recuadro de lugar:",
        "SETTINGS_LANDMARK_HISTORY_COUNT_LABEL": "Máximo historial de lugares:",
        "SETTINGS_LANDMARK_TAGS_TOOLTIP": "Etiquetas predeterminadas para "
        "lugares/monumentos, separadas por comas.",
        "SETTINGS_LANDMARK_ENGINE_TOOLTIP": "Librería utilizada para la detección "
        "de lugares.",
        "SETTINGS_LANDMARK_COLOR_TOOLTIP": "Color del cuadro delimitador dibujado "
        "alrededor de los lugares.",
        "SETTINGS_LANDMARK_HISTORY_TOOLTIP": "Número máximo de nombres de lugares "
        "usados recientemente para recordar.",
        "SETTINGS_PATH_NOT_FOUND_WARNING": "Advertencia: La ruta no existe o "
        "no es un directorio: {}",
        "SETTINGS_USE_LAST_NAME_LABEL": "Usar último nombre por defecto",
        "SETTINGS_USE_LAST_NAME_TOOLTIP": "Rellena automáticamente la ventana de "
        "asignación con el último nombre utilizado.",
        "SETTINGS_FACE_HISTORY_COUNT_LABEL": "Máximo historial de caras:",
        "SETTINGS_THUMBS_REFRESH_LABEL": "Intervalo refresco miniaturas (ms):",
        "SETTINGS_THUMBS_BG_COLOR_LABEL": "Color de fondo de miniaturas:",
        "SETTINGS_THUMBS_FILENAME_COLOR_LABEL": "Color del nombre de fichero:",
        "SETTINGS_THUMBS_TAGS_COLOR_LABEL": "Color de etiquetas de miniaturas:",
        "SETTINGS_THUMBS_RATING_COLOR_LABEL": "Color de valoración de miniaturas:",
        "SETTINGS_THUMBS_FILENAME_FONT_SIZE_LABEL": "Tamaño de fuente del nombre de "
        "fichero:",
        "SETTINGS_SCAN_THREADS_LABEL": "Hilos de generación:",
        "SETTINGS_SCAN_THREADS_TOOLTIP": "Número máximo de hilos simultaneos para "
        "generar miniaturas.",
        "SETTINGS_THUMBS_TAGS_FONT_SIZE_LABEL": "Tamaño de fuente de las etiquetas:",
        "SETTINGS_SCAN_MAX_LEVEL_LABEL": "Nivel Máximo de Escaneo:",
        "SETTINGS_SCAN_BATCH_SIZE_LABEL": "Tamaño de Lote de Escaneo:",
        "SETTINGS_SCANNER_SEARCH_ENGINE_LABEL": "Motor de búsqueda de archivos:",
        "SETTINGS_SCANNER_SEARCH_ENGINE_TOOLTIP": "Motor a usar para buscar archivos. "
        "'Bagheera' usa la librería de BagheeraSearch. 'Baloo' usa el commando "
        "'baloosearch'",
        "SETTINGS_SCAN_FULL_ON_START_LABEL": "Escanear Todo al Inicio:",
        "SETTINGS_SCAN_MAX_LEVEL_TOOLTIP": "Profundidad máxima de directorio para "
        "escanear recursivamente.",
        "SETTINGS_SCAN_BATCH_SIZE_TOOLTIP": "Número de imágenes a cargar en cada lote.",
        "SETTINGS_SCAN_FULL_ON_START_TOOLTIP": "Escanear automáticamente todas las "
        "imágenes de la carpeta al inicio.",
        "SETTINGS_PERSON_TAGS_TOOLTIP": "Etiquetas predeterminadas para personas, "
        "separadas por comas.",
        "SETTINGS_FACE_ENGINE_TOOLTIP": "Librería utilizada para la detección de "
        "rostros (se recomienda MediaPipe).",
        "SETTINGS_FACE_COLOR_TOOLTIP": "Color del cuadro delimitador dibujado "
        "alrededor de los rostros detectados.",
        "SETTINGS_MRU_TAGS_TOOLTIP": "Número máximo de etiquetas usadas recientemente "
        "para recordar.",
        "SETTINGS_FACE_HISTORY_TOOLTIP": "Número máximo de nombres de rostros usados "
        "recientemente para recordar.",
        "SETTINGS_THUMBS_REFRESH_TOOLTIP": "Retraso en milisegundos antes de "
        "actualizar las miniaturas tras redimensionar.",
        "SETTINGS_THUMBS_BG_COLOR_TOOLTIP": "Color de fondo de la vista de cuadrícula "
        "de miniaturas.",
        "SETTINGS_THUMBS_FILENAME_COLOR_TOOLTIP": "Color de fuente para nombres de "
        "archivo en miniaturas.",
        "SETTINGS_THUMBS_TAGS_COLOR_TOOLTIP": "Color de fuente para etiquetas en "
        "miniaturas.",
        "SETTINGS_THUMBS_RATING_COLOR_TOOLTIP": "Color para las estrellas de "
        "valoración en miniaturas.",
        "SETTINGS_THUMBS_FILENAME_FONT_SIZE_TOOLTIP": "Tamaño de fuente para nombres "
        "de archivo en miniaturas.",
        "SETTINGS_THUMBS_TAGS_FONT_SIZE_TOOLTIP": "Tamaño de fuente para etiquetas en "
        "miniaturas.",
        "SETTINGS_THUMBS_FILENAME_LINES_LABEL": "Líneas para nombre de archivo:",
        "SETTINGS_THUMBS_FILENAME_LINES_TOOLTIP": "Número de líneas para el nombre del "
        "archivo debajo de la miniatura.",
        "SETTINGS_THUMBS_TAGS_LINES_LABEL": "Líneas para etiquetas:",
        "SETTINGS_THUMBS_TOOLTIP_BG_COLOR_LABEL": "Color de fondo del tooltip:",
        "SETTINGS_THUMBS_TOOLTIP_FG_COLOR_LABEL": "Color de texto del tooltip:",
        "SETTINGS_THUMBS_TOOLTIP_FG_COLOR_TOOLTIP": "Color del texto para los tooltips "
        "en las miniaturas.",
        "SETTINGS_THUMBS_TOOLTIP_BG_COLOR_TOOLTIP": "Color de fondo para los tooltips "
        "en las miniaturas.",
        "SETTINGS_THUMBS_TAGS_LINES_TOOLTIP": "Número de líneas para el texto de las "
        "etiquetas debajo de la miniatura.",
        "SETTINGS_THUMBS_SHOW_FILENAME_LABEL": "Mostrar nombre de archivo",
        "SETTINGS_THUMBS_SHOW_RATING_LABEL": "Mostrar valoración",
        "SETTINGS_THUMBS_SHOW_TAGS_LABEL": "Mostrar etiquetas",
        "SETTINGS_THUMBS_SHOW_FILENAME_TOOLTIP": "Mostrar u ocultar el nombre del "
        "archivo debajo de la miniatura.",
        "SETTINGS_THUMBS_SHOW_RATING_TOOLTIP": "Mostrar u ocultar las estrellas de "
        "valoración debajo de la miniatura.",
        "SETTINGS_THUMBS_SHOW_TAGS_TOOLTIP": "Mostrar u ocultar las etiquetas debajo "
        "de la miniatura.",
        "SETTINGS_VIEWER_WHEEL_SPEED_LABEL": "Velocidad de la rueda del ratón en el "
        "visor:",
        "SETTINGS_VIEWER_AUTO_RESIZE_LABEL": "Redimensionar ventana automáticamente",
        "SETTINGS_VIEWER_AUTO_RESIZE_TOOLTIP": "Redimensiona la ventana "
        "automáticamente "
        "al hacer zoom o cambiar de imagen para ajustarse al contenido.",
        "SETTINGS_VIEWER_WHEEL_SPEED_TOOLTIP": "Ajusta la velocidad con la que la "
        "rueda del ratón cambia de imagen en el visor.",
        "SETTINGS_DOWNLOAD_MEDIAPIPE_MODEL": "Descargar Modelo",
        "SETTINGS_DOWNLOAD_MEDIAPIPE_MODEL_TOOLTIP": "Descarga el archivo de modelo "
        "necesario para la detección de caras con MediaPipe.",
        "MEDIAPIPE_DOWNLOADING_TITLE": "Descargando Modelo",
        "MEDIAPIPE_DOWNLOADING_TEXT": "Descargando el modelo de detección de caras de "
        "MediaPipe...",
        "MEDIAPIPE_DOWNLOAD_SUCCESS_TITLE": "Descarga Completa",
        "MEDIAPIPE_DOWNLOAD_SUCCESS_TEXT": "El modelo de MediaPipe se ha descargado "
        "correctamente.",
        "MEDIAPIPE_DOWNLOAD_ERROR_TITLE": "Error de Descarga",
        "MEDIAPIPE_DOWNLOAD_ERROR_TEXT": "Fallo al descargar el modelo de MediaPipe: "
        "{}",
        "MENU_VIEWER_SETTINGS": "Opciones del Visor",
        "VIEWER_MENU_COMPARE": "Modo Comparación",
        "MENU_FILMSTRIP_POSITION": "Posición de la Tira de Imágenes",
        "FILMSTRIP_BOTTOM": "Abajo",
        "FILMSTRIP_LEFT": "Izquierda",
        "FILMSTRIP_TOP": "Arriba",
        "FILMSTRIP_RIGHT": "Derecha",
        "FILMSTRIP_POS_CHANGED_INFO": "La nueva posición de la tira de imágenes se "
        "aplicará a los nuevos visores que se abran.",
        "SAVE_CROP_TITLE": "Guardar Imagen Recortada",
        "COMPARE_LINKED": " [Vinculado]",
        "COMPARE_UNLINKED": " [Desvinculado]",
        "CROP_INDICATOR": " [RECORTE]",
        "OPEN_WITH_OTHER": "Abrir con otra aplicación...",
        "COLLAPSE_EXPAND_GROUP": "Contraer/Expandir Grupo",
        "MENU_TOGGLE_MAIN_WINDOW": "Mostrar/Ocultar ventana principal",
        "LOADING_DATA": "Cargando datos...",
        "SETTINGS_PLACEHOLDER_TAGS": "etiqueta1, etiqueta2, carpeta/etiqueta",
        "THUMBNAILS_GENERATE_PROGRESS": "Generando miniaturas de {}px: {}/{}",
        "THUMBNAILS_REGENERATE_PROGRESS": "Regenerando miniatura: {}/{}",
        "MENU_SHOW_SHORTCUTS": "Configurar Atajos de Teclado...",
        "SHORTCUTS_TITLE": "Atajos de Teclado",
        "SHORTCUTS_ACTION": "Acción",
        "SHORTCUTS_KEY": "Atajo",
        "CLOSE": "Cerrar",
        "SHORTCUT_EDIT_TITLE": "Cambiar Atajo",
        "SHORTCUT_EDIT_LABEL": "Nuevo atajo para '{}'",
        "SHORTCUT_CONFLICT_TITLE": "Conflicto de Atajos",
        "SHORTCUT_CONFLICT_TEXT": "El atajo '{}' ya está asignado a '{}'.",
        "SHORTCUT_OVERRIDE_QUESTION": "¿Deseas sobrescribirlo?",
        "SHORTCUT_SEARCH_PLACEHOLDER": "Buscar atajos...",
        "CACHE_CLEANING": "Limpiando caché...",
        "CACHE_CLEANED": "Caché limpiada. Se eliminaron {} entradas inválidas.",
        "CACHE_CLEARED": "Caché de miniaturas limpiada.",
        "CONFIRM_CLEAR_CACHE_TITLE": "Confirmar Limpieza de Caché",
        "CONFIRM_CLEAR_CACHE_TEXT": "¿Seguro que quieres eliminar permanentemente toda "
        "la caché de miniaturas?",
        "CONFIRM_CLEAR_CACHE_INFO": "Esto eliminará todas las miniaturas cacheadas de "
        "la memoria y el disco. Se regenerarán mientras navegas, lo que puede ser "
        "lento. Esta acción no se puede deshacer.",
        "CONFIRM_DELETE_TITLE": "Confirmar Borrado Permanente",
        "CONFIRM_DELETE_TEXT": "¿Deseas eliminar permanentemente esta imagen?",
        "CONFIRM_DELETE_INFO": "Archivo: {}\n\nEsta acción NO se puede deshacer.",
        "SYSTEM_ERROR": "Error de Sistema",
        "ERROR_DELETING_FILE": "Error al intentar borrar el archivo:\n{}",
        "RENAME_FILE_TITLE": "Renombrar Archivo",
        "RENAME_FILE_TEXT": "Nuevo nombre para '{}':",
        "RENAME_ERROR_TITLE": "Error al Renombrar",
        "RENAME_ERROR_EXISTS": "El archivo '{}' ya existe.",
        "FILE_RENAMED": "Archivo renombrado a {}",
        "ERROR_RENAME": "No se pudo renombrar el archivo: {}",
        "ERROR_JPEG_METADATA_LIMIT": "Límite de metadatos excedido para '{}'. Este "
        "archivo JPEG ya tiene demasiados metadatos (XMP) para guardar más.",
        "MAIN_DOCK_TITLE": "Panel principal",
        "LAYOUTS_TAB": "Diseños",
        "LAYOUTS_TABLE_HEADER": ["Nombre", "Última Modificación"],
        "SAVE_LAYOUT_TITLE": "Guardar Diseño",
        "SAVE_LAYOUT_TEXT": "Introduce un nombre para el diseño:",
        "LAYOUT_EXISTS_TITLE": "El diseño ya existe",
        "LAYOUT_EXISTS_TEXT": "¿Deseas sobreescribir el diseño \"{}\"?",
        "LAYOUT_EXISTS_INFO": "Esta acción NO se puede deshacer.",
        "LAYOUT_SAVED": "Diseño '{0}' guardado.",
        "ERROR_SAVING_LAYOUT": "No se pudo guardar el diseño: {}",
        "LOAD_LAYOUT_TITLE": "Cargar Diseño",
        "NO_LAYOUTS_FOUND": "No se encontraron diseños guardados.",
        "SELECT_LAYOUT": "Seleccionar diseño:",
        "LAYOUT_RESTORED": "Diseño restaurado.",
        "ERROR_LOADING_LAYOUT_TITLE": "{}: Error",
        "ERROR_LOADING_LAYOUT_TEXT": "Fallo al cargar el archivo de diseño:\n\"{}\"",
        "RENAME_LAYOUT_TITLE": "Renombrar Diseño",
        "RENAME_LAYOUT_TEXT": "Nuevo Nombre:",
        "COPY_LAYOUT_TITLE": "Copiar Diseño",
        "COPY_LAYOUT_TEXT": "Nuevo Nombre:",
        "LAYOUT_ALREADY_EXISTS": "El diseño ya existe.",
        "CONFIRM_DELETE_LAYOUT_TITLE": "Confirmar Eliminación",
        "CONFIRM_DELETE_LAYOUT_TEXT": "¿Eliminar el diseño '{}'?",
        "INFO_TAB": "Información",
        "INFO_RATING_LABEL": "Puntuación:",
        "INFO_COMMENT_LABEL": "Comentario:",
        "COMMENT_APPLY_CHANGES": "Aplicar Cambios",
        "ENTER_COMMENT": "Escribe un comentario...",
        "TAGS_TAB": "Etiquetas",
        "TAG_FILTER_TAB": "Filtro",
        "TAG_SEARCH_PLACEHOLDER": "Buscar etiquetas...",
        "TAG_APPLY_CHANGES": "Aplicar Cambios",
        "TAG_USED_TAGS": "⭐ ETIQUETAS USADAS",
        "TAG_ALL_TAGS": "📂 TODAS LAS ETIQUETAS",
        "TAG_NEW_TAG_TITLE": "Nueva Etiqueta",
        "SEARCH_BY_TAG": "Buscar por esta etiqueta",
        "TAG_ADD_TOOLTIP": "Crear una nueva etiqueta",
        "TAG_REFRESH_TOOLTIP": "Refrescar etiquetas disponibles desde el base de datos "
        "de Baloo",
        "TAG_NEW_TAG_TEXT": "Introduce el nombre de la etiqueta (usa / para "
        "jerarquía):",
        "SEARCH_ADD_AND": "Añadir AND esta etiqueta a la búsqueda",
        "SEARCH_ADD_OR": "Añadir OR esta etiqueta a la búsqueda",
        "FILTER_AND": "Y",
        "FILTER_OR": "O",
        "FILTER_INVERT": "Invertir",
        "FILTER_TAG_COLUMN": "Etiqueta",
        "FILTER_NOT_COLUMN": "NO",
        "FILTER_STATS_HIDDEN": "{} ítems ocultos",
        "FILTER_NAME_PLACEHOLDER": "Filtrar por nombre de archivo...",
        "HISTORY_TAB": "Historial",
        "HISTORY_TABLE_HEADER": ["Nombre", "Fecha"],
        "HISTORY_BTN_CLEAR_ALL_TOOLTIP": "Limpiar Todo",
        "HISTORY_BTN_DELETE_SELECTED_TOOLTIP": "Eliminar Seleccionados",
        "HISTORY_BTN_DELETE_OLDER_TOOLTIP": "Eliminar Antiguos",
        "HISTORY_CLEAR_ALL_TITLE": "Confirmar",
        "HISTORY_CLEAR_ALL_TEXT": "¿Limpiar todo el historial?",
        "PROPERTIES_TITLE": "Propiedades",
        "PROPERTIES_GENERAL_TAB": "General",
        "PROPERTIES_METADATA_TAB": "Metadatos",
        "PROPERTIES_EXIF_TAB": "EXIF",
        "PROPERTIES_FILENAME": "Nombre de Archivo:",
        "PROPERTIES_LOCATION": "Ubicación:",
        "PROPERTIES_SIZE": "Tamaño:",
        "PROPERTIES_CREATED": "Creado:",
        "PROPERTIES_MODIFIED": "Modificado:",
        "PROPERTIES_DIMENSIONS": "Dimensiones:",
        "PROPERTIES_FORMAT": "Formato:",
        "PROPERTIES_MEGAPIXELS": "Megapíxeles:",
        "PROPERTIES_COLOR_DEPTH": "Profundidad de color:",
        "BITS": "bits",
        "PROPERTIES_TABLE_HEADER": ["Propiedad", "Valor"],
        "PROPERTIES_ADD_ATTR": "Añadir Atributo",
        "PROPERTIES_ADD_ATTR_NAME": "Nombre del Atributo (ej. user.comment):",
        "PROPERTIES_DELETE_ALL": "Borrar Todo",
        "PROPERTIES_ADD_ATTR_VALUE": "Valor para {}:",
        "PROPERTIES_ERROR_SET_ATTR": "Fallo al establecer xattr: {}",
        "PROPERTIES_ERROR_ADD_ATTR": "Fallo al añadir xattr: {}",
        "PROPERTIES_DELETE_ATTR": "Eliminar Atributo",
        "PROPERTIES_ERROR_DELETE_ATTR": "Fallo al eliminar xattr: {}",
        "EXIV2_NOT_INSTALLED": "Librería exiv2 no instalada. Instale python exiv2.",
        "NO_METADATA_FOUND": "No se encontraron metadatos (EXIF/XMP/IPTC).",
        "VIEWER_MENU_SLIDESHOW": "Presentación",
        "VIEWER_MENU_STOP_SLIDESHOW": "Detener Presentación",
        "VIEWER_MENU_START_SLIDESHOW": "Iniciar Presentación",
        "VIEWER_MENU_START_REVERSE_SLIDESHOW": "Iniciar Presentación Inversa",
        "VIEWER_MENU_STOP_REVERSE_SLIDESHOW": "Detener Presentación Inversa",
        "VIEWER_MENU_SET_INTERVAL": "Establecer Intervalo...",
        "VIEWER_MENU_ROTATE": "Rotar",
        "VIEWER_MENU_ROTATE_LEFT": "Izquierda",
        "VIEWER_MENU_ROTATE_RIGHT": "Derecha",
        "VIEWER_MENU_EXIT_FULLSCREEN": "Salir de Pantalla Completa",
        "VIEWER_MENU_ENTER_FULLSCREEN": "Pantalla Completa",
        "VIEWER_MENU_RENAME": "Renombrar",
        "VIEWER_MENU_FIT_SCREEN": "Ajustar a Pantalla / Tamaño Real",
        "VIEWER_MENU_SHOW_FILMSTRIP": "Mostrar Tira de Imágenes",
        "VIEWER_MENU_FLIP": "Voltear",
        "VIEWER_MENU_FLIP_H": "Horizontal",
        "VIEWER_MENU_PAUSE_ANIMATION": "Pausar Animación",
        "VIEWER_MENU_RESUME_ANIMATION": "Reanudar Animación",
        "VIEWER_MENU_FLIP_V": "Vertical",
        "VIEWER_MENU_SHOW_STATUSBAR": "Mostrar Barra de Estado",
        "VIEWER_MENU_TAGS": "Etiquetas rápidas",
        "VIEWER_MENU_CROP": "Modo Recorte",
        "VIEWER_MENU_SAVE_CROP": "Guardar Selección...",
        "VIEWER_MENU_COPY_PATH": "Copiar Ruta del Archivo",
        "VIEWER_MENU_COPY_IMAGE": "Copiar Imagen al Portapapeles",
        "VIEWER_MENU_DETECT_AREAS": "Gestión de regiones",
        "VIEWER_MENU_DETECT_FACES": "Detectar caras",
        "VIEWER_MENU_DETECT_PETS": "Detectar mascotas",
        "VIEWER_MENU_ADD_FACE": "Añadir cara",
        "VIEWER_MENU_ADD_PET": "Añadir mascota",
        "VIEWER_MENU_ADD_BODY": "Añadir cuerpo",
        "VIEWER_MENU_ADD_OBJECT": "Añadir objeto",
        "VIEWER_MENU_ADD_LANDMARK": "Añadir lugar",
        "VIEWER_MENU_MANIPULATE": "Manipular",
        "VIEWER_MENU_ZOOM": "Zoom",
        "VIEWER_MENU_ZOOM_IN": "Acercar",
        "VIEWER_MENU_ZOOM_OUT": "Alejar",
        "VIEWER_MENU_COMPARE": "Modo Comparación",
        "VIEWER_MENU_COMPARE_1": "Vista Única",
        "VIEWER_MENU_COMPARE_2": "2 Imágenes",
        "VIEWER_MENU_COMPARE_4": "4 Imágenes",
        "VIEWER_MENU_LINK_PANES": "Vincular Paneles",
        "SAVE_CROP_TITLE": "Guardar Imagen Recortada",
        "SAVE_CROP_FILTER": "Imágenes (*.jpg *.jpeg *.png *.bmp *.webp)",
        "SLIDESHOW_INTERVAL_TITLE": "Intervalo de Presentación",
        "SLIDESHOW_INTERVAL_TEXT": "Segundos:",
        "CONTEXT_MENU_VIEW": "Ver",
        "CONTEXT_MENU_OPEN": "Abrir",
        "CONTEXT_MENU_OPEN_SEARCH_LOCATION": "Abrir y buscar en ubicación",
        "CONTEXT_MENU_OPEN_DEFAULT_APP": "Abrir ubicación con Dolphin",
        "CONTEXT_MENU_OPEN_BAGHEERAVIEW": "Abrir ubicación con BagheeraView",
        "CONTEXT_MENU_FULLSCREEN_VIEWER": "Abrir con Visor a Pantalla Completa",
        "CONTEXT_MENU_MOVE_TO": "Mover a...",
        "CONTEXT_MENU_COPY_TO": "Copiar a...",
        "CONTEXT_MENU_ROTATE": "Girar",
        "CONTEXT_MENU_ROTATE_LEFT": "Izquierda",
        "CONTEXT_MENU_ROTATE_RIGHT": "Derecha",
        "CONTEXT_MENU_TRASH": "Mover a la Papelera",
        "CONTEXT_MENU_CLIPBOARD": "Portapapeles",
        "CONTEXT_MENU_COPY_FILE": "Copiar URL del Archivo",
        "CONTEXT_MENU_COPY_DIR": "Copiar Ruta del Directorio",
        "CONTEXT_MENU_PROPERTIES": "Propiedades",
        "CONTEXT_MENU_NO_APPS_FOUND": "No se encontraron aplicaciones",
        "CONTEXT_MENU_REGENERATE": "Regenerar Miniatura",
        "CONTEXT_MENU_ERROR_LISTING_APPS": "Error listando aplicaciones",
        "CONTEXT_MENU_RENAME": "Renombrar...",
        "CONTEXT_MENU_DELETE": "Borrar",
        "CONTEXT_MENU_SELECT_ALL": "Seleccionar Todo",
        "CONTEXT_MENU_SELECT_NONE": "No Seleccionar Nada",
        "CONTEXT_MENU_INVERT_SELECTION": "Invertir Selección",
        "CONFIRM_OVERWRITE_TITLE": "Confirmar Sobrescritura",
        "CONFIRM_OVERWRITE_TEXT": "El archivo ya existe en el destino:\n{}\n\n¿Deseas "
        "sobrescribirlo?",
        "ERROR_MOVE_FILE": "No se pudo mover el archivo: {}",
        "ERROR_COPY_FILE": "No se pudo copiar el archivo: {}",
        "MOVED_TO": "Movido a {}",
        "FS_WATCHER_TOOLTIP": "Monitor de Sistema de Archivos (monitoreando "
        "directorios activos)",
        "COPIED_TO": "Copiado a {}",
        "ERROR_ROTATE_IMAGE": "No se pudo girar la imagen: {}",
        "PREPARING_QUERY": "Preparando consulta...",
    },
    "gl": {
        "READY": "Listo",
        "SEARCH": "Buscar",
        "SELECT": "Seleccionar",
        "ERROR": "Erro",
        "FILE_NOT_FOUND": "Ficheiro non atopado",
        "WARNING": "Advertencia",
        "INFO": "Información",
        "LOAD": "Cargar",
        "SAVE": "Gardar",
        "CREATE": "Crear",
        "CANCEL": "Cancelar",
        "RENAME": "Renomear",
        "COPY": "Copiar",
        "DELETE": "Eliminar",
        "UNKNOWN": "Descoñecido",
        "MENU_LANGUAGE": "Idioma",
        "RESTART_REQUIRED_TITLE": "Requírese Reinicio",
        "RESTART_REQUIRED_TEXT": "O idioma cambiouse a {language}.\nPor favor, "
        "reinicie a aplicación para que os cambios teñan efecto.",
        "SORT_NAME_ASC": "Nome ↑",
        "SORT_NAME_DESC": "Nome ↓",
        "SORT_DATE_ASC": "Data ↑",
        "SORT_DATE_DESC": "Data ↓",
        "VIEW_MODE_FLAT": "Plano",
        "MENU_VIEW_MODE": "Modo de Vista",
        "FILTERED_COUNT": "Filtrados: {}",
        "VIEW_MODE_DAY": "Separar por Día",
        "VIEW_MODE_WEEK": "Separar por Semana",
        "MENU_FIND_SIMILAR": "Buscar imaxes similares",
        "SIMILAR_SEARCH_TITLE": "Imaxes similares a '{}'",
        "SIMILAR_SEARCH_PROGRESS": "Buscando imaxes similares: {} atopadas...",
        "RESCAN": "Buscar de novo",
        "VIEW_MODE_MONTH": "Separar por Mes",
        "VIEW_MODE_YEAR": "Separar por Ano",
        "VIEW_MODE_RATING": "Separar por Valoración",
        "FILTERED_ZERO": "Filtrados: 0",
        "VIEW_MODE_FOLDER": "Separar por Cartafol",
        "LOAD_MORE_TOOLTIP": f"Cargar {APP_CONFIG.get('scan_batch_size', 64)} imaxes "
        "máis (Ctrl+D)",
        "LOAD_ALL_TOOLTIP": "Cargar tódalas imaxes (Ctrl+Shift+D)",
        "LOAD_ALL_TOOLTIP_ALT": "Cancelar carga de tódalas imaxes (Ctrl+Shift+D)",
        "CONFIRM_LOAD_ALL_TITLE": "Confirmar carga",
        "CONFIRM_LOAD_ALL_TEXT": "Seguro que queres cargar as {} imaxes "
        "restantes?",
        "DONE_SCAN": "Feito: {} imaxes",
        "LOADING_SCAN": "Cargando... {} / {}",
        "GROUP_HEADER_FORMAT": "{group_name} - {count} imaxes",
        "GROUP_HEADER_FORMAT_SINGULAR": "{group_name} - 1 imaxe",
        "GROUP_BY_WEEK_FORMAT": "{year} - Semana {week}",
        "GROUP_BY_RATING_FORMAT": "{stars} Estrelas",
        "SHUTTING_DOWN": "Pechando...",
        "LOADED_PARTIAL": "Cargadas {} / {}",
        "HIGH_RES_GENERATED": "Miniaturas de alta resolución xeradas.",
        "SCANNING_DIRS": "Escaneando directorios...",
        "SELECT_IMAGE_TITLE": "Seleccionar Imaxe",
        "VIEWER_TITLE_PAUSED": " [Pausado]",
        "IMAGE_NOT_IN_VIEW": "A imaxe '{}' non está na vista actual.",
        "VIEWER_TITLE_SLIDESHOW": " [Presentación]",
        "RENAME_VIEWER_TITLE": "Renomear Arquivo",
        "RENAME_VIEWER_TEXT": "Novo nome para '{}':",
        "RENAME_VIEWER_ERROR_EXISTS": "O ficheiro '{}' xa existe.",
        "RENAME_VIEWER_ERROR_SYSTEM": "Erro do Sistema",
        "RENAME_VIEWER_ERROR_TEXT": "Non se puido renomear o ficheiro: {}",
        "ADD_FACE_TITLE": "Engadir Rostro",
        "ADD_PET_TITLE": "Engadir Mascota",
        "ADD_BODY_TITLE": "Engadir Corpo",
        "ADD_OBJECT_TITLE": "Engadir Obxecto",
        "ADD_LANDMARK_TITLE": "Engadir Lugar",
        "ADD_FACE_LABEL": "Nome:",
        "ADD_PET_LABEL": "Nome:",
        "ADD_BODY_LABEL": "Nome:",
        "ADD_OBJECT_LABEL": "Nome:",
        "ADD_LANDMARK_LABEL": "Nome:",
        "NEXT_AREA": "Próxima rexión: {}",
        "DELETE_AREA_TITLE": "Eliminar rexión",
        "CREATE_TAG_TITLE": "Crear Etiqueta",
        "CREATE_TAG_TEXT": "A etiqueta para '{}' non existe. Desexas crear unha nova?",
        "NEW_PERSON_TAG_TITLE": "Nova Etiqueta de Persoa",
        "NEW_PERSON_TAG_TEXT": "Introduce a ruta completa da etiqueta:",
        "NEW_PET_TAG_TITLE": "Nova Etiqueta de Mascota",
        "NEW_PET_TAG_TEXT": "Introduce a ruta completa da etiqueta:",
        "NEW_BODY_TAG_TITLE": "Nova Etiqueta de Corpo",
        "NEW_BODY_TAG_TEXT": "Introduce a ruta completa da etiqueta:",
        "NEW_OBJECT_TAG_TITLE": "Nova Etiqueta de Obxecto",
        "NEW_OBJECT_TAG_TEXT": "Introduce a ruta completa da etiqueta:",
        "NEW_LANDMARK_TAG_TITLE": "Nova Etiqueta de Lugar",
        "NEW_LANDMARK_TAG_TEXT": "Introduce a ruta completa da etiqueta:",
        "SELECT_TAG_TITLE": "Seleccionar Etiqueta",
        "SELECT_TAG_TEXT": "Atopáronse varias etiquetas para '{}'. Por favor, "
        "selecciona a correcta:",
        "FACE_NAME_TOOLTIP": "Escribe un nome ou selecciónao do historial.",
        "CLEAR_TEXT_TOOLTIP": "Limpar o campo de texto",
        "RENAME_AREA_TITLE": "Renomear rexión",
        "SHOW_FACES": "Amosar Rostros e outras rexións",
        "DETECT_FACES": "Detectar Rostros",
        "DETECT_PETS": "Detectar Mascotas",
        "DETECT_BODIES": "Detectar Corpos",
        "NO_FACE_LIBS": "Non se atoparon librarías de detección de rostros. Instale "
        "'mediapipe' ou 'face_recognition'.",
        "THUMBNAIL_NO_NAME": "Sen nome",
        "THUMBNAIL_NO_TAGS": "Sen etiquetas",
        "MENU_ABOUT": "Acerca de",
        "MENU_ABOUT_TITLE": "Acerca de {}",
        "MENU_ABOUT_TEXT": "<b>{0}</b> v{1}<br><br>Un visor e xestor de imaxes "
        "sinxelo para KDE con soporte para Baloo.<br><br>Creado por {2} coa axuda da "
        " IA, pero maiormente gracias ó traballo da boa xente de KDE e Qt.",
        "MENU_CACHE": "Caché",
        "MENU_CLEAR_CACHE": "Limpar caché ({} elementos, {:.1f} MB, {:.1f} MB en "
        "disco)",
        "MENU_CLEAN_METADATA_CACHE": "Limpar caché de metadatos obsoletos",
        "MENU_CLEAN_DIRECTORY_CACHE": "Limpar caché de directorios obsoletos",
        "MENU_CLEAN_CACHE": "Limpar entradas de caché inválidas",
        "MENU_SHOW_TAGS": "Amosar Etiquetas",
        "MENU_SHOW_INFO": "Amosar Información",
        "MENU_SHOW_FAVORITES": "Amosar Favoritos",
        "FAVORITES_TAB": "Favoritos",
        "FAVORITES_SEARCH_PLACEHOLDER": "Buscar favoritos...",
        "FAVORITES_TABLE_HEADER": ["Comentario", "Consulta", "Atallo"],
        "ADD_FAVORITE_TOOLTIP": "Engadir busca actual a favoritos",
        "EDIT_COMMENT_TITLE": "Editar Comentario",
        "EDIT_COMMENT_TEXT": "Comentario para '{}':",
        "EDIT_SHORTCUT_TITLE": "Asignar Atallo",
        "EDIT_SHORTCUT_TEXT": "Preme as teclas para '{}':",
        "MOVE_UP": "Subir",
        "MOVE_DOWN": "Baixar",
        "MENU_SHOW_FILTER": "Amosar Filtro",
        "MENU_SHOW_LAYOUTS": "Amosar Deseños",
        "MENU_SHOW_HISTORY": "Amosar Historial",
        "MENU_SETTINGS": "Opcións",
        "SETTINGS_GROUP_DUPLICATES": "Duplicados",
        "MENU_DUPLICATES": "Duplicados",
        "MENU_DETECT_CURRENT_SEARCH": "Detectar na busca actual",
        "MENU_DETECT_ALL": "Detectar todos",
        "MENU_FORCE_FULL_ALL_ANALYSIS": "Forzar análise completa de todo",
        "MENU_FORCE_FULL_ANALYSIS": "Forzar análise completa",
        "MENU_REVIEW_IGNORED": "Revisar ignorados",
        "MENU_CLEAN_UP_HASHES": "Limpar",
        "MENU_REPAIR_DATABASE": "Reparar índice",
        "MENU_CLEAR_EXCEPTIONS": "Limpar parellas ignoradas",
        "CONFIRM_CLEAR_EXCEPTIONS_TITLE": "Confirmar Limpeza de Ignorados",
        "CONFIRM_CLEAR_EXCEPTIONS_TEXT": "Seguro que queres borrar todas as parellas "
        "de duplicados ignoradas? Volveranse detectar no vindeiro escaneo.",
        "REPAIRING_DATABASE": "Reparando índice de duplicados...",
        "MENU_CLEAR_HASHES": "Limpar hashes ({} elementos, {:.1f} MB en disco)",
        "CONFIRM_CLEAR_HASHES_TITLE": "Confirmar Limpeza de Hashes",
        "CONFIRM_CLEAR_HASHES_TEXT": "Seguro que queres eliminar permanentemente toda "
        "a base de datos de hashes?",
        "CONFIRM_CLEAR_HASHES_INFO": "Isto eliminará todos os hashes de imaxes "
        "calculados. Rexeneraranse a medida que detectes duplicados, o que pode ser "
        "lento. Esta acción non se pode deshacer.",
        "SETTINGS_DUPLICATE_METHOD_LABEL": "Método:",
        "SETTINGS_DUPLICATE_METHOD_TOOLTIP": "Selecciona o método para a detección "
        "de duplicados.",
        "METHOD_HISTOGRAM_HASHING": "Histograma + Hashing",
        "METHOD_RESNET": "ResNet (Baseado en IA)",
        "SETTINGS_DUPLICATE_CONFIRM_DELETE_LABEL": "Confirmar antes de borrar "
        "duplicados",
        "SETTINGS_DUPLICATE_WHITELIST_LABEL": "Lista branca (cartafoles a incluír):",
        "SETTINGS_DUPLICATE_WHITELIST_TOOLTIP": "Rutas de cartafoles separadas por "
        "comas para escanear ao usar 'Detectar todos'.",
        "SETTINGS_DUPLICATE_BLACKLIST_LABEL": "Lista negra (cartafoles a excluír):",
        "SETTINGS_DUPLICATE_BLACKLIST_TOOLTIP": "Rutas de cartafoles separadas por "
        "comas para ignorar durante escaneos de 'Detectar todos'.",
        "SETTINGS_DUPLICATE_SCAN_COUNT_LABEL": "Imaxes atopadas para 'Detectar "
        "todos': {}",
        "SETTINGS_DEFAULT_DELETE_TO_TRASH_LABEL": "A tecla Supr envía á papeleira por "
        "defecto",
        "SETTINGS_DEFAULT_DELETE_TO_TRASH_TOOLTIP": "Se está marcada, ao premer a "
        "tecla Supr moveranse os ficheiros á papeleira. Se non, eliminaranse "
        "permanentemente.",
        "SETTINGS_DUPLICATE_CONFIRM_DELETE_TOOLTIP": "Amosa un diálogo de confirmación "
        "antes de mover unha imaxe duplicada á papeleira.",
        "SETTINGS_DUPLICATE_THRESHOLD_LABEL": "Umbral de Similitude:",
        "SETTINGS_DUPLICATE_THRESHOLD_TOOLTIP": "Establece o umbral de similitude "
        "(50-100%). Valores máis altos significan que as imaxes deben ser máis "
        "parecidas para considerarse duplicadas.",
        "SETTINGS_DUPLICATE_MISSING_LIBS": "A librería 'imagehash' é necesaria para a "
        "detección de duplicados pero non se atopou. Esta función está desactivada.",
        "MENU_DETECT_DUPLICATES": "Detectar Duplicados",
        "DUPLICATE_WHITELIST_EMPTY": "A lista branca está baleira. Por favor, "
        "configúrea en Opcións.",
        "DUPLICATE_DETECTION_TITLE": "Detección de Duplicados",
        "DUPLICATE_ALREADY_RUNNING": "A detección de duplicados xa está en curso.",
        "DUPLICATE_NO_IMAGES": "Non hai imaxes cargadas para detectar duplicados.",
        "DUPLICATE_STARTING": "Iniciando detección de duplicados...",
        "DUPLICATE_PROGRESS": "Detección de duplicados: {message} ({current}/{total})",
        "DUPLICATE_NONE_FOUND": "Non se atoparon duplicados.",
        "DUPLICATE_FOUND_TITLE": "Duplicados Atopados",
        "DUPLICATE_FOUND_MSG": "Atopáronse os seguintes duplicados:\n",
        "DUPLICATE_FOUND_MORE": "... e {count} máis.",
        "DUPLICATE_FINISHED": "Detección de duplicados finalizada.",
        "DUPLICATE_MSG_HASHING": "Procesando {filename}",
        "DUPLICATE_MSG_ANALYZING": "Analizando {filename}",
        "DUPLICATE_MANAGER_TITLE": "Xestionar Imaxes Duplicadas",
        "DUPLICATE_DELETE_LEFT": "Papeleira Esquerda",
        "DUPLICATE_DELETE_RIGHT": "Papeleira Dereita",
        "CONFIRM_TRASH_TITLE": "Mover á papeleira",
        "CONFIRM_TRASH_TEXT": "Desexas mover esta imaxe á papeleira?",
        "DUPLICATE_KEEP_BOTH": "Manter Ambas (Ignorar)",
        "DUPLICATE_SKIP": "Omitir",
        "DUPLICATE_REMOVE_IGNORED": "Eliminar de ignorados",
        "DUPLICATE_INFO_FORMAT": "{size} - {width}x{height}",
        "VIEWER_MENU_LINK_PANES": "Vincular Paneis",
        "DUPLICATE_OPEN_COMPARISON": "Abrir Comparación",
        "DUPLICATE_LIST_HEADER": "Parellas Duplicadas",
        "IGNORED_DATE": "Data Ignorado",
        "SETTINGS_GROUP_SCANNER": "Escáner",
        "SETTINGS_GROUP_AREAS": "Rexións",
        "SETTINGS_GROUP_THUMBNAILS": "Miniaturas",
        "SETTINGS_GROUP_VIEWER": "Visor de Imaxes",
        "SETTINGS_PERSON_TAGS_LABEL": "Etiquetas de persoa:",
        "SETTINGS_FACE_ENGINE_LABEL": "Motor de detección de caras:",
        "SETTINGS_FACE_COLOR_LABEL": "Cor do cadro de cara:",
        "SETTINGS_MRU_TAGS_COUNT_LABEL": "Máximo número de etiquetas recentes:",
        "SETTINGS_PET_TAGS_LABEL": "Etiquetas de mascota:",
        "SETTINGS_PET_ENGINE_LABEL": "Motor de detección de mascotas:",
        "SETTINGS_PET_COLOR_LABEL": "Cor do cadro de mascota:",
        "SETTINGS_PET_HISTORY_COUNT_LABEL": "Máximo historial de mascotas:",
        "SETTINGS_PET_TAGS_TOOLTIP": "Etiquetas predeterminadas para mascotas, "
        "separadas por comas.",
        "SETTINGS_PET_ENGINE_TOOLTIP": "Libraría utilizada para a detección de "
        "mascotas.",
        "SETTINGS_PET_COLOR_TOOLTIP": "Cor do cadro delimitador debuxado arredor "
        "das mascotas detectadas.",
        "SETTINGS_PET_HISTORY_TOOLTIP": "Número máximo de nomes de mascotas usados "
        "recentemente para lembrar.",
        "TYPE_FACE": "Cara",
        "TYPE_PET": "Mascota",
        "TYPE_BODY": "Corpo",
        "TYPE_OBJECT": "Obxecto",
        "TYPE_LANDMARK": "Lugar",
        "SETTINGS_BODY_TAGS_LABEL": "Etiquetas de corpo:",
        "SETTINGS_BODY_ENGINE_LABEL": "Motor de detección de corpos:",
        "SETTINGS_BODY_COLOR_LABEL": "Cor do cadro de corpo:",
        "SETTINGS_BODY_HISTORY_COUNT_LABEL": "Máximo historial de corpos:",
        "SETTINGS_BODY_TAGS_TOOLTIP": "Etiquetas predeterminadas para corpos, "
        "separadas por comas.",
        "SETTINGS_BODY_ENGINE_TOOLTIP": "Libraría utilizada para a detección de "
        "corpos.",
        "SETTINGS_BODY_COLOR_TOOLTIP": "Cor do cadro delimitador debuxado arredor "
        "dos corpos detectados.",
        "SETTINGS_BODY_HISTORY_TOOLTIP": "Número máximo de nomes de corpos usados "
        "recentemente para lembrar.",
        "SETTINGS_OBJECT_TAGS_LABEL": "Etiquetas de obxecto:",
        "SETTINGS_OBJECT_ENGINE_LABEL": "Motor de detección de obxectos:",
        "SETTINGS_OBJECT_COLOR_LABEL": "Cor do cadro de obxecto:",
        "SETTINGS_OBJECT_HISTORY_COUNT_LABEL": "Máximo historial de obxectos:",
        "SETTINGS_OBJECT_TAGS_TOOLTIP": "Etiquetas predeterminadas para obxectos, "
        "separadas por comas.",
        "SETTINGS_OBJECT_ENGINE_TOOLTIP": "Libraría utilizada para a detección de "
        "obxectos.",
        "SETTINGS_OBJECT_COLOR_TOOLTIP": "Cor do cadro delimitador debuxado arredor "
        "dos obxectos.",
        "SETTINGS_OBJECT_HISTORY_TOOLTIP": "Número máximo de nomes de obxectos "
        "usados recentemente para lembrar.",
        "SETTINGS_LANDMARK_TAGS_LABEL": "Etiquetas de lugar:",
        "SETTINGS_LANDMARK_ENGINE_LABEL": "Motor de detección de lugares:",
        "SETTINGS_LANDMARK_COLOR_LABEL": "Cor do cadro de lugar:",
        "SETTINGS_LANDMARK_HISTORY_COUNT_LABEL": "Máximo historial de lugares:",
        "SETTINGS_LANDMARK_TAGS_TOOLTIP": "Etiquetas predeterminadas para "
        "lugares/monumentos, separadas por comas.",
        "SETTINGS_LANDMARK_ENGINE_TOOLTIP": "Libraría utilizada para a detección "
        "de lugares.",
        "SETTINGS_LANDMARK_COLOR_TOOLTIP": "Cor do cadro delimitador debuxado "
        "arredor dos lugares.",
        "SETTINGS_LANDMARK_HISTORY_TOOLTIP": "Número máximo de nomes de lugares "
        "usados recentemente para lembrar.",
        "SETTINGS_PATH_NOT_FOUND_WARNING": "Advertencia: A ruta non existe ou "
        "non é un directorio: {}",
        "SETTINGS_USE_LAST_NAME_LABEL": "Usar o último nome por defecto",
        "SETTINGS_USE_LAST_NAME_TOOLTIP": "Rechea automáticamente a ventá de "
        "asignación có último nome utilizado.",
        "SETTINGS_FACE_HISTORY_COUNT_LABEL": "Máximo historial de caras:",
        "SETTINGS_THUMBS_REFRESH_LABEL": "Intervalo refresco miniaturas (ms):",
        "SETTINGS_THUMBS_BG_COLOR_LABEL": "Cor de fondo de miniaturas:",
        "SETTINGS_THUMBS_FILENAME_COLOR_LABEL": "Cor do nome de ficheiro:",
        "SETTINGS_THUMBS_TAGS_COLOR_LABEL": "Cor das etiquetas das miniaturas:",
        "SETTINGS_THUMBS_RATING_COLOR_LABEL": "Cor da valoración das miniaturas:",
        "SETTINGS_THUMBS_FILENAME_FONT_SIZE_LABEL": "Tamaño da fonte do nome de "
        "ficheiro:",
        "SETTINGS_SCAN_THREADS_LABEL": "Fios de xeración:",
        "SETTINGS_SCAN_THREADS_TOOLTIP": "Número máximo de fios simultaneos para "
        "xerar miniaturas.",
        "SETTINGS_THUMBS_TAGS_FONT_SIZE_LABEL": "Tamaño da fonte das etiquetas:",
        "SETTINGS_SCAN_MAX_LEVEL_LABEL": "Nivel Máximo de Escaneo:",
        "SETTINGS_SCAN_BATCH_SIZE_LABEL": "Tamaño do Lote de Escaneo:",
        "SETTINGS_SCANNER_SEARCH_ENGINE_LABEL": "Motor de busca de ficheiros:",
        "SETTINGS_SCANNER_SEARCH_ENGINE_TOOLTIP": "Motor a usar para buscar ficheiros. "
        "'Bagheera' usa a libraría de BagheeraSearch. 'Baloo' usa o comando de "
        "'baloosearch'.",
        "SETTINGS_SCAN_FULL_ON_START_LABEL": "Escanear Todo ao Inicio:",
        "SETTINGS_SCAN_MAX_LEVEL_TOOLTIP": "Profundidade máxima de directorio para "
        "escanear recursivamente.",
        "SETTINGS_SCAN_BATCH_SIZE_TOOLTIP": "Número de imaxes a cargar en cada lote.",
        "SETTINGS_SCAN_FULL_ON_START_TOOLTIP": "Escanear automaticamente todas as "
        "imaxes do cartafol ao inicio.",
        "SETTINGS_PERSON_TAGS_TOOLTIP": "Etiquetas predeterminadas para persoas, "
        "separadas por comas.",
        "SETTINGS_FACE_ENGINE_TOOLTIP": "Libraría utilizada para a detección de "
        "rostros (recoméndase MediaPipe).",
        "SETTINGS_FACE_COLOR_TOOLTIP": "Cor do cadro delimitador debuxado arredor dos "
        "rostros detectados.",
        "SETTINGS_MRU_TAGS_TOOLTIP": "Número máximo de etiquetas usadas recentemente "
        "para lembrar.",
        "SETTINGS_FACE_HISTORY_TOOLTIP": "Número máximo de nomes de rostros usados "
        "recentemente para lembrar.",
        "SETTINGS_THUMBS_REFRESH_TOOLTIP": "Atraso en milisegundos antes de actualizar "
        "as miniaturas tras redimensionar.",
        "SETTINGS_THUMBS_BG_COLOR_TOOLTIP": "Cor de fondo da vista de grade de "
        "miniaturas.",
        "SETTINGS_THUMBS_FILENAME_COLOR_TOOLTIP": "Cor de fonte para nomes de ficheiro "
        "en miniaturas.",
        "SETTINGS_THUMBS_TAGS_COLOR_TOOLTIP": "Cor de fonte para etiquetas en "
        "miniaturas.",
        "SETTINGS_THUMBS_RATING_COLOR_TOOLTIP": "Cor para as estrelas de valoración en "
        "miniaturas.",
        "SETTINGS_THUMBS_FILENAME_FONT_SIZE_TOOLTIP": "Tamaño de fonte para nomes de "
        "ficheiro en miniaturas.",
        "SETTINGS_THUMBS_TAGS_FONT_SIZE_TOOLTIP": "Tamaño de fonte para etiquetas en "
        "miniaturas.",
        "SEARCH_ENGINE_NATIVE": "Bagheera",
        "SEARCH_ENGINE_BALOO": "Baloo",
        "SETTINGS_THUMBS_FILENAME_LINES_LABEL": "Liñas para nome de ficheiro:",
        "SETTINGS_THUMBS_FILENAME_LINES_TOOLTIP": "Número de liñas para o nome do "
        "ficheiro debaixo da miniatura.",
        "SETTINGS_THUMBS_TAGS_LINES_LABEL": "Liñas para etiquetas:",
        "SETTINGS_THUMBS_TOOLTIP_BG_COLOR_LABEL": "Cor de fondo do tooltip:",
        "SETTINGS_THUMBS_TOOLTIP_FG_COLOR_LABEL": "Cor do texto do tooltip:",
        "SETTINGS_THUMBS_TOOLTIP_FG_COLOR_TOOLTIP": "Cor do texto para os tooltips "
        "nas miniaturas.",
        "SETTINGS_THUMBS_TOOLTIP_BG_COLOR_TOOLTIP": "Cor de fondo para os tooltips "
        "nas miniaturas.",
        "SETTINGS_THUMBS_TAGS_LINES_TOOLTIP": "Número de liñas para o texto das "
        "etiquetas debaixo da miniatura.",
        "SETTINGS_THUMBS_SHOW_FILENAME_LABEL": "Amosar nome de ficheiro",
        "SETTINGS_THUMBS_SHOW_RATING_LABEL": "Amosar valoración",
        "SETTINGS_THUMBS_SHOW_TAGS_LABEL": "Amosar etiquetas",
        "SETTINGS_THUMBS_SHOW_FILENAME_TOOLTIP": "Amosar ou ocultar o nome do ficheiro "
        "debaixo da miniatura.",
        "SETTINGS_THUMBS_SHOW_RATING_TOOLTIP": "Amosar ou ocultar as estrelas de "
        "valoración debaixo da miniatura.",
        "SETTINGS_THUMBS_SHOW_TAGS_TOOLTIP": "Amosar ou ocultar as etiquetas debaixo "
        "da miniatura.",
        "SETTINGS_VIEWER_WHEEL_SPEED_LABEL": "Velocidade da roda do rato no visor:",
        "SETTINGS_VIEWER_AUTO_RESIZE_LABEL": "Redimensionar xanela automaticamente",
        "SETTINGS_VIEWER_AUTO_RESIZE_TOOLTIP": "Redimensiona a xanela automaticamente "
        "ao facer zoom ou cambiar de imaxe para axustarse ao contido.",
        "SETTINGS_VIEWER_WHEEL_SPEED_TOOLTIP": "Axusta a velocidade coa que a roda do "
        "rato cambia de imaxe no visor.",
        "SETTINGS_DOWNLOAD_MEDIAPIPE_MODEL": "Descargar Modelo",
        "SETTINGS_DOWNLOAD_MEDIAPIPE_MODEL_TOOLTIP": "Descarga o ficheiro de modelo "
        "necesario para a detección de caras con MediaPipe.",
        "MEDIAPIPE_DOWNLOADING_TITLE": "Descargando Modelo",
        "MEDIAPIPE_DOWNLOADING_TEXT": "Descargando o modelo de detección de caras de "
        "MediaPipe...",
        "MEDIAPIPE_DOWNLOAD_SUCCESS_TITLE": "Descarga Completa",
        "MEDIAPIPE_DOWNLOAD_SUCCESS_TEXT": "O modelo de MediaPipe descargouse "
        "correctamente.",
        "MEDIAPIPE_DOWNLOAD_ERROR_TITLE": "Erro de Descarga",
        "MEDIAPIPE_DOWNLOAD_ERROR_TEXT": "Fallo ao descargar o modelo de MediaPipe: {}",
        "MENU_VIEWER_SETTINGS": "Opcións do Visor",
        "MENU_FILMSTRIP_POSITION": "Posición da Tira de Imaxes",
        "VIEWER_MENU_COMPARE": "Modo Comparación",
        "FILMSTRIP_BOTTOM": "Abaixo",
        "FILMSTRIP_LEFT": "Esquerda",
        "FILMSTRIP_TOP": "Arriba",
        "FILMSTRIP_RIGHT": "Dereita",
        "FILMSTRIP_POS_CHANGED_INFO": "A nova posición da tira de imaxes aplicarase "
        "aos novos visores que se abran.",
        "MENU_SHOW_SHORTCUTS": "Configurar Atallos de Teclado...",
        "COMPARE_LINKED": " [Vencellado]",
        "COMPARE_UNLINKED": " [Desvencellado]",
        "CROP_INDICATOR": " [RECORTE]",
        "OPEN_WITH_OTHER": "Abrir con outra aplicación...",
        "COLLAPSE_EXPAND_GROUP": "Contraer/Expandir Grupo",
        "MENU_TOGGLE_MAIN_WINDOW": "Amosar/Ocultar xanela principal",
        "LOADING_DATA": "Cargando datos...",
        "SETTINGS_PLACEHOLDER_TAGS": "etiqueta1, etiqueta2, cartafol/etiqueta",
        "THUMBNAILS_GENERATE_PROGRESS": "Xerando miniaturas de {}px: {}/{}",
        "THUMBNAILS_REGENERATE_PROGRESS": "Rexerando miniatura: {}/{}",
        "SAVE_CROP_TITLE": "Gardar Imaxe Recortada",
        "SHORTCUTS_TITLE": "Atallos de Teclado",
        "SHORTCUTS_ACTION": "Acción",
        "SHORTCUTS_KEY": "Atallo",
        "CLOSE": "Pechar",
        "SHORTCUT_EDIT_TITLE": "Cambiar Atallo",
        "SHORTCUT_EDIT_LABEL": "Novo Atallo para '{}'",
        "SHORTCUT_CONFLICT_TITLE": "Conflito de Atallos",
        "SHORTCUT_CONFLICT_TEXT": "O atallo '{}' xa está asignado a '{}'.",
        "SHORTCUT_OVERRIDE_QUESTION": "Desexas sobrescribilo?",
        "SHORTCUT_SEARCH_PLACEHOLDER": "Buscar atallos...",
        "CACHE_CLEANING": "Limpando caché...",
        "CACHE_CLEANED": "Caché limpada. Elimináronse {} entradas inválidas.",
        "CACHE_CLEARED": "Caché de miniaturas limpada.",
        "CONFIRM_CLEAR_CACHE_TITLE": "Confirmar Limpeza de Caché",
        "CONFIRM_CLEAR_CACHE_TEXT": "Seguro que queres eliminar permanentemente toda "
        "a caché de miniaturas?",
        "CONFIRM_CLEAR_CACHE_INFO": "Isto eliminará todas as miniaturas da caché da "
        "memoria e do disco. Rexeneraranse mentres navegas, o que pode ser "
        "lento. Esta acción non se pode desfacer.",
        "CONFIRM_DELETE_TITLE": "Confirmar Borrado Permanente",
        "CONFIRM_DELETE_TEXT": "Desexas eliminar permanentemente esta imaxe?",
        "CONFIRM_DELETE_INFO": "Ficheiro: {}\n\nEsta acción NON se pode desfacer.",
        "SYSTEM_ERROR": "Erro do Sistema",
        "ERROR_DELETING_FILE": "Erro ao intentar borrar o ficheiro:\n{}",
        "RENAME_FILE_TITLE": "Renomear Ficheiro",
        "RENAME_FILE_TEXT": "Novo nome para '{}':",
        "RENAME_ERROR_TITLE": "Erro ao renomear",
        "RENAME_ERROR_EXISTS": "O ficheiro '{}' xa existe.",
        "FILE_RENAMED": "Ficheiro renomeado a {}",
        "ERROR_RENAME": "Non se puido renomear o ficheiro: {}",
        "ERROR_JPEG_METADATA_LIMIT": "Límite de metadatos excedido para '{}'. Este "
        "ficheiro JPEG xa ten demasiados metadatos (XMP) para gardar máis.",
        "MAIN_DOCK_TITLE": "Panel principal",
        "LAYOUTS_TAB": "Deseños",
        "LAYOUTS_TABLE_HEADER": ["Nome", "Última Modificación"],
        "SAVE_LAYOUT_TITLE": "Gardar Deseño",
        "SAVE_LAYOUT_TEXT": "Introduce un nome para o deseño:",
        "LAYOUT_EXISTS_TITLE": "O deseño xa existe",
        "LAYOUT_EXISTS_TEXT": "Desexas sobrescribir o deseño \"{}\"?",
        "LAYOUT_EXISTS_INFO": "Esta acción NON se pode desfacer.",
        "LAYOUT_SAVED": "Deseño '{0}' gardado.",
        "ERROR_SAVING_LAYOUT": "Non se puido gardar o deseño: {}",
        "LOAD_LAYOUT_TITLE": "Cargar Deseño",
        "NO_LAYOUTS_FOUND": "Non se atoparon deseños gardados.",
        "SELECT_LAYOUT": "Seleccionar deseño:",
        "LAYOUT_RESTORED": "Deseño restaurado.",
        "ERROR_LOADING_LAYOUT_TITLE": "{}: Erro",
        "ERROR_LOADING_LAYOUT_TEXT": "Fallo ao cargar o ficheiro de deseño:\n\"{}\"",
        "RENAME_LAYOUT_TITLE": "Renomear Deseño",
        "RENAME_LAYOUT_TEXT": "Novo Nome:",
        "COPY_LAYOUT_TITLE": "Copiar Deseño",
        "COPY_LAYOUT_TEXT": "Novo Nome:",
        "LAYOUT_ALREADY_EXISTS": "O deseño xa existe.",
        "CONFIRM_DELETE_LAYOUT_TITLE": "Confirmar Eliminación",
        "CONFIRM_DELETE_LAYOUT_TEXT": "Eliminar o deseño '{}'?",
        "INFO_TAB": "Información",
        "INFO_RATING_LABEL": "Puntuación:",
        "INFO_COMMENT_LABEL": "Comentario:",
        "COMMENT_APPLY_CHANGES": "Aplicar Cambios",
        "ENTER_COMMENT": "Escribe un comentario...",
        "TAGS_TAB": "Etiquetas",
        "TAG_FILTER_TAB": "Filtro",
        "TAG_SEARCH_PLACEHOLDER": "Buscar etiquetas...",
        "TAG_APPLY_CHANGES": "Aplicar Cambios",
        "TAG_USED_TAGS": "⭐ ETIQUETAS USADAS",
        "TAG_ALL_TAGS": "📂 TÓDALAS ETIQUETAS",
        "TAG_NEW_TAG_TITLE": "Nova Etiqueta",
        "SEARCH_BY_TAG": "Buscar por esta etiqueta",
        "TAG_ADD_TOOLTIP": "Crear unha nova etiqueta",
        "TAG_REFRESH_TOOLTIP": "Refrescar etiquetas dispoñibles dende a base de datos "
        "de Baloo",
        "TAG_NEW_TAG_TEXT": "Introduce o nome da etiqueta (usa / para "
        "xerarquía):",
        "SEARCH_ADD_AND": "Engadir AND esta etiqueta á busca",
        "SEARCH_ADD_OR": "Engadir OR esta etiqueta á busca",
        "FILTER_AND": "E",
        "FILTER_OR": "OU",
        "FILTER_INVERT": "Inverter",
        "FILTER_TAG_COLUMN": "Etiqueta",
        "FILTER_NOT_COLUMN": "NON",
        "FILTER_STATS_HIDDEN": "{} elementos ocultos",
        "FILTER_NAME_PLACEHOLDER": "Filtrar por nome de ficheiro...",
        "HISTORY_TAB": "Historial",
        "HISTORY_TABLE_HEADER": ["Nome", "Data"],
        "HISTORY_BTN_CLEAR_ALL_TOOLTIP": "Limpiar Todo",
        "HISTORY_BTN_DELETE_SELECTED_TOOLTIP": "Eliminar Seleccionados",
        "HISTORY_BTN_DELETE_OLDER_TOOLTIP": "Eliminar Antiguos",
        "HISTORY_CLEAR_ALL_TITLE": "Confirmar",
        "HISTORY_CLEAR_ALL_TEXT": "Limpar todo o historial?",
        "PROPERTIES_TITLE": "Propiedades",
        "PROPERTIES_GENERAL_TAB": "Xeral",
        "PROPERTIES_METADATA_TAB": "Metadatos",
        "PROPERTIES_EXIF_TAB": "EXIF",
        "PROPERTIES_FILENAME": "Nome do Ficheiro:",
        "PROPERTIES_LOCATION": "Localización:",
        "PROPERTIES_SIZE": "Tamaño:",
        "PROPERTIES_CREATED": "Creado:",
        "PROPERTIES_MODIFIED": "Modificado:",
        "PROPERTIES_DIMENSIONS": "Dimensións:",
        "PROPERTIES_FORMAT": "Formato:",
        "PROPERTIES_MEGAPIXELS": "Megapíxeles:",
        "PROPERTIES_COLOR_DEPTH": "Profundidade da cor:",
        "BITS": "bits",
        "PROPERTIES_TABLE_HEADER": ["Propiedade", "Valor"],
        "PROPERTIES_ADD_ATTR": "Engadir Atributo",
        "PROPERTIES_ADD_ATTR_NAME": "Nome do Atributo (ex. user.comment):",
        "PROPERTIES_DELETE_ALL": "Borrar Todo",
        "PROPERTIES_ADD_ATTR_VALUE": "Valor para {}:",
        "PROPERTIES_ERROR_SET_ATTR": "Fallo ao establecer xattr: {}",
        "PROPERTIES_ERROR_ADD_ATTR": "Fallo ao engadir xattr: {}",
        "PROPERTIES_DELETE_ATTR": "Eliminar Atributo",
        "PROPERTIES_ERROR_DELETE_ATTR": "Fallo ao eliminar xattr: {}",
        "EXIV2_NOT_INSTALLED": "Libraría exiv2 non instalada. Instale python-exiv2.",
        "NO_METADATA_FOUND": "Non se atoparon metadatos (EXIF/XMP/IPTC).",
        "VIEWER_MENU_SLIDESHOW": "Presentación",
        "VIEWER_MENU_STOP_SLIDESHOW": "Deter Presentación",
        "VIEWER_MENU_START_SLIDESHOW": "Iniciar Presentación",
        "VIEWER_MENU_START_REVERSE_SLIDESHOW": "Iniciar Presentación Inversa",
        "VIEWER_MENU_STOP_REVERSE_SLIDESHOW": "Deter Presentación Inversa",
        "VIEWER_MENU_SET_INTERVAL": "Establecer Intervalo...",
        "VIEWER_MENU_ROTATE": "Xirar",
        "VIEWER_MENU_ROTATE_LEFT": "Esquerda",
        "VIEWER_MENU_ROTATE_RIGHT": "Dereita",
        "VIEWER_MENU_EXIT_FULLSCREEN": "Saír de Pantalla Completa",
        "VIEWER_MENU_ENTER_FULLSCREEN": "Pantalla Completa",
        "VIEWER_MENU_RENAME": "Renomear",
        "VIEWER_MENU_FIT_SCREEN": "Axustar á Pantalla / Tamaño Real",
        "VIEWER_MENU_SHOW_FILMSTRIP": "Amosar Tira de Imaxes",
        "VIEWER_MENU_FLIP": "Voltear",
        "VIEWER_MENU_FLIP_H": "Horizontal",
        "VIEWER_MENU_PAUSE_ANIMATION": "Pausar Animación",
        "VIEWER_MENU_RESUME_ANIMATION": "Reanudar Animación",
        "VIEWER_MENU_FLIP_V": "Vertical",
        "VIEWER_MENU_SHOW_STATUSBAR": "Amosar Barra de Estado",
        "VIEWER_MENU_TAGS": "Etiquetas rápidas",
        "VIEWER_MENU_CROP": "Modo Recorte",
        "VIEWER_MENU_SAVE_CROP": "Gardar Selección...",
        "VIEWER_MENU_COPY_PATH": "Copiar Ruta do Ficheiro",
        "VIEWER_MENU_COPY_IMAGE": "Copiar Imaxe ao Portapapeis",
        "VIEWER_MENU_DETECT_AREAS": "Xestión de rexións",
        "VIEWER_MENU_DETECT_FACES": "Detectar caras",
        "VIEWER_MENU_DETECT_PETS": "Detectar mascotas",
        "VIEWER_MENU_ADD_FACE": "Engadir cara",
        "VIEWER_MENU_ADD_PET": "Engadir mascota",
        "VIEWER_MENU_ADD_BODY": "Engadir corpo",
        "VIEWER_MENU_ADD_OBJECT": "Engadir obxecto",
        "VIEWER_MENU_ADD_LANDMARK": "Engadir lugar",
        "VIEWER_MENU_MANIPULATE": "Manipular",
        "VIEWER_MENU_ZOOM": "Zoom",
        "VIEWER_MENU_ZOOM_IN": "Achegar",
        "VIEWER_MENU_ZOOM_OUT": "Afastar",
        "VIEWER_MENU_COMPARE": "Modo Comparación",
        "VIEWER_MENU_COMPARE_1": "Vista Única",
        "VIEWER_MENU_COMPARE_2": "2 Imaxes",
        "VIEWER_MENU_COMPARE_4": "4 Imaxes",
        "VIEWER_MENU_LINK_PANES": "Vincular Paneis",
        "SAVE_CROP_TITLE": "Gardar Imaxe Recortada",
        "SAVE_CROP_FILTER": "Imaxes (*.jpg *.jpeg *.png *.bmp *.webp)",
        "SLIDESHOW_INTERVAL_TITLE": "Intervalo da Presentación",
        "SLIDESHOW_INTERVAL_TEXT": "Segundos:",
        "CONTEXT_MENU_VIEW": "Ver",
        "CONTEXT_MENU_OPEN": "Abrir",
        "CONTEXT_MENU_OPEN_SEARCH_LOCATION": "Abrir e buscar na localización",
        "CONTEXT_MENU_OPEN_DEFAULT_APP": "Abrir localización con Dolphin",
        "CONTEXT_MENU_OPEN_BAGHEERAVIEW": "Abrir localización con BagheeraView",
        "CONTEXT_MENU_MOVE_TO": "Mover a...",
        "CONTEXT_MENU_COPY_TO": "Copiar a...",
        "CONTEXT_MENU_ROTATE": "Xirar",
        "CONTEXT_MENU_ROTATE_LEFT": "Esquerda",
        "CONTEXT_MENU_ROTATE_RIGHT": "Dereita",
        "CONTEXT_MENU_TRASH": "Mover á Papeleira",
        "CONTEXT_MENU_CLIPBOARD": "Portapapeis",
        "CONTEXT_MENU_COPY_FILE": "Copiar URL do Ficheiro",
        "CONTEXT_MENU_COPY_DIR": "Copiar Ruta do Directorio",
        "CONTEXT_MENU_PROPERTIES": "Propiedades",
        "CONTEXT_MENU_FULLSCREEN_VIEWER": "Abrir con Visor a Pantalla Completa",
        "CONTEXT_MENU_NO_APPS_FOUND": "Non se atoparon aplicacións",
        "CONTEXT_MENU_REGENERATE": "Rexenerar Miniatura",
        "CONTEXT_MENU_ERROR_LISTING_APPS": "Erro listando aplicacións",
        "CONTEXT_MENU_RENAME": "Renomear...",
        "CONTEXT_MENU_DELETE": "Borrar",
        "CONTEXT_MENU_SELECT_ALL": "Seleccionar Todo",
        "CONTEXT_MENU_SELECT_NONE": "Non Seleccionar Nada",
        "CONTEXT_MENU_INVERT_SELECTION": "Inverter Selección",
        "CONFIRM_OVERWRITE_TITLE": "Confirmar Sobrescritura",
        "CONFIRM_OVERWRITE_TEXT": "O ficheiro xa existe no destino:\n{}\n\nDesexas "
        "sobrescribilo?",
        "ERROR_MOVE_FILE": "Non se puido mover o ficheiro: {}",
        "ERROR_COPY_FILE": "Non se puido copiar o ficheiro: {}",
        "MOVED_TO": "Movido a {}",
        "FS_WATCHER_TOOLTIP": "Monitor do Sistema de Ficheiros (monitoreando "
        "directorios activos)",
        "COPIED_TO": "Copiado a {}",
        "ERROR_ROTATE_IMAGE": "Non se puido xirar a imaxe: {}",
        "PREPARING_QUERY": "Preparando consulta...",
    }
}


# Determine which language to use for UI strings
def _get_current_language():
    """Determines the language to use for UI strings based on environment."""
    lang = os.getenv("BAGHEERA_LANG") or APP_CONFIG.get("language", DEFAULT_LANGUAGE)

    if lang == "system":
        sys_lang = os.getenv("LANG")
        if sys_lang:
            # LANG is usually something like 'en_US.UTF-8'
            lang = sys_lang[0:2].lower()
        else:
            lang = FALLBACK_LANGUAGE

    # If the resolved language is not supported by our translation dictionaries,
    # fallback to English.
    return lang if lang in _UI_TEXTS else FALLBACK_LANGUAGE


CURRENT_LANGUAGE = _get_current_language()


class _UITextsProxy:
    """
    A proxy class to access UI strings from the _UI_TEXTS dictionary.

    This allows using `UITexts.SOME_STRING` syntax, which dynamically fetches
    the string for the CURRENT_LANGUAGE, with a fallback to the DEFAULT_LANGUAGE.
    This makes the rest of the application code independent of the language management
    logic.
    """
    def __getattr__(self, name):
        # Get the dictionary for the current language, or fallback to the default.
        lang_texts = _UI_TEXTS.get(CURRENT_LANGUAGE, _UI_TEXTS[FALLBACK_LANGUAGE])
        # Get the specific string. If not found in the current language,
        # try the default language.
        text = lang_texts.get(name)
        if text is None:
            default_texts = _UI_TEXTS[FALLBACK_LANGUAGE]
            # Return a placeholder if not found anywhere
            text = default_texts.get(name, f"_{name}_")
        return text


# Create a single instance to be used throughout the application.
UITexts = _UITextsProxy()
