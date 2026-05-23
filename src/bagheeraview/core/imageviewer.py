
"""Image Viewer Module for Bagheera.

This module implements the main image viewing window (ImageViewer) and its
associated widgets, such as the filmstrip thumbnail browser (FilmStripWidget).
It provides functionalities for navigating, zooming, rotating, and presenting
images in a slideshow mode.

Classes:
    ImageViewer: A standalone window for viewing and manipulating an image.
"""
import os
import subprocess
import json

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QScrollArea, QLabel, QHBoxLayout, QListWidget,
    QListWidgetItem, QAbstractItemView, QMenu, QInputDialog, QDialog, QDialogButtonBox,
    QGridLayout, QApplication, QMessageBox, QLineEdit, QFileDialog
)
from PySide6.QtGui import (
    QPixmap, QIcon, QTransform, QDrag, QPainter, QPen, QColor, QAction, QCursor,
    QImageReader, QMovie, QKeySequence, QPainterPath, QImage
)
from PySide6.QtCore import (
    Signal, QPoint, QSize, Qt, QMimeData, QUrl, QTimer, QEvent, QRect, Slot, QRectF,
    QThread, QObject
)

from .constants import (
    APP_CONFIG, DEFAULT_FACE_BOX_COLOR, DEFAULT_PET_BOX_COLOR, DEFAULT_VIEWER_SHORTCUTS,
    DEFAULT_BODY_BOX_COLOR,
    DEFAULT_OBJECT_BOX_COLOR, DEFAULT_LANDMARK_BOX_COLOR, FORCE_X11, ICON_THEME_VIEWER,
    ICON_THEME_VIEWER_FALLBACK, KSCREEN_DOCTOR_MARGIN, KWINOUTPUTCONFIG_PATH,
    VIEWER_AUTO_RESIZE_WINDOW_DEFAULT, VIEWER_FORM_MARGIN, VIEWER_LABEL,
    VIEWER_WHEEL_SPEED_DEFAULT, XATTR_NAME, ZOOM_DESKTOP_RATIO, UITexts,
    AVAILABLE_FACE_ENGINES, AVAILABLE_PET_ENGINES
)
from .imagecontroller import ImageController
from .widgets import FaceNameInputWidget
from .utils import PowerManager
from .propertiesdialog import PropertiesDialog


class HighlightWidget(QWidget):
    """Widget to show a highlight border around the active pane."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setStyleSheet("border: 2px solid #3498db; background: transparent;")
        self.hide()


class FaceNameDialog(QDialog):
    """A dialog to get a face name using the FaceNameInputWidget."""
    def __init__(self, parent=None, history=None, current_name="", main_win=None,
                 region_type="Face"):
        super().__init__(parent)
        if region_type == "Pet":
            self.setWindowTitle(UITexts.ADD_PET_TITLE)
            layout_label = UITexts.ADD_PET_LABEL
        elif region_type == "Body":
            self.setWindowTitle(UITexts.ADD_BODY_TITLE)
            layout_label = UITexts.ADD_BODY_LABEL
        elif region_type == "Object":
            self.setWindowTitle(UITexts.ADD_OBJECT_TITLE)
            layout_label = UITexts.ADD_OBJECT_LABEL
        elif region_type == "Landmark":
            self.setWindowTitle(UITexts.ADD_LANDMARK_TITLE)
            layout_label = UITexts.ADD_LANDMARK_LABEL
        else:
            self.setWindowTitle(UITexts.ADD_FACE_TITLE)
            layout_label = UITexts.ADD_FACE_LABEL
        self.setMinimumWidth(350)
        self.main_win = main_win

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(layout_label))

        # Our custom widget.
        self.name_input = FaceNameInputWidget(self.main_win, self,
                                              region_type=region_type)
        self.name_input.load_data(history or [])
        if current_name:
            self.name_input.name_combo.setEditText(current_name.split('/')[-1])

        self.name_input.name_combo.lineEdit().selectAll()

        layout.addWidget(self.name_input)

        # OK / Cancel buttons.
        self.button_box = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        layout.addWidget(self.button_box)

        # Connections.
        self.button_box.accepted.connect(self.name_input._on_accept)
        self.button_box.rejected.connect(self.reject)
        self.name_input.name_accepted.connect(self._on_tag_selected)

        self.final_tag = ""
        self.final_history = history or []

    def _on_tag_selected(self, full_tag):
        """Handles the signal from the input widget and closes the dialog."""
        self.final_tag = full_tag
        self.final_history = self.name_input.get_history()
        super().accept()

    @staticmethod
    def get_name(parent=None, history=None, current_name="", main_win=None,
                 region_type="Face", title=None):
        """Static method to show the dialog and get the result."""
        dialog = FaceNameDialog(parent, history, current_name, main_win, region_type)
        if title:
            dialog.setWindowTitle(title)
        result = dialog.exec()
        if result == QDialog.Accepted:
            return dialog.final_tag, dialog.final_history, True
        # Return original history if cancelled
        return current_name, history, False


class FilmstripLoader(QThread):
    """Thread to load filmstrip thumbnails asynchronously."""
    thumbnail_loaded = Signal(int, QImage)

    def __init__(self, cache, items_to_load, icon_size):
        super().__init__()
        self.cache = cache
        # items_to_load is a list of (index, path) tuples
        self.items = items_to_load
        self.icon_size = icon_size
        self.target_index = 0
        self._abort = False
        self._sort_needed = True

    def set_target_index(self, index):
        if self.target_index != index:
            self.target_index = index
            self._sort_needed = True

    def run(self):
        self.setPriority(QThread.IdlePriority)
        while self.items:
            if self._abort:
                return

            if self._sort_needed:
                # Pick the item closest to the target index (visible area)
                # Sorting descending allows O(1) pop from end
                self.items.sort(
                    key=lambda x: abs(x[0] - self.target_index), reverse=True)
                self._sort_needed = False

            index, path = self.items.pop()

            # Small sleep to prevent UI freezing during heavy IO bursts
            self.msleep(1)
            try:
                res = self.cache.get_thumbnail(path, self.icon_size)
                if res.image and not res.image.isNull():
                    self.thumbnail_loaded.emit(index, res.image)
            except Exception:
                pass

    def stop(self):
        self._abort = True
        self.wait()


class FastTagManager:
    """Manages the creation and interaction of the fast tag menu."""
    def __init__(self, viewer):
        self.viewer = viewer
        self.main_win = viewer.main_win

    def show_menu(self):
        """Builds and shows a context menu for quickly adding/removing tags."""
        controller = self.viewer.controller
        if not self.main_win or not controller or not controller.get_current_path():
            return

        current_path = controller.get_current_path()
        try:
            raw_tags = os.getxattr(current_path, XATTR_NAME).decode('utf-8')
            current_tags = {t.strip() for t in raw_tags.split(',') if t.strip()}
        except (OSError, AttributeError):
            current_tags = set()

        mru_tags = list(self.main_win.mru_tags) \
            if hasattr(self.main_win, 'mru_tags') else []

        if not mru_tags and not current_tags:
            return

        menu = FastTagMenu(self)

        mru_tags_to_show = [tag for tag in mru_tags if tag not in current_tags]
        if mru_tags_to_show:
            for tag in mru_tags_to_show:
                action = menu.addAction(tag)
                if '/' in tag:
                    action.setProperty("is_hierarchical", True)
                    menu.style().unpolish(menu)
                    menu.style().polish(menu)
                action.setCheckable(True)
                action.setChecked(False)

        if mru_tags_to_show and current_tags:
            menu.addSeparator()

        if current_tags:
            for tag in sorted(list(current_tags)):
                action = menu.addAction(tag)
                if '/' in tag:
                    action.setProperty("is_hierarchical", True)
                    menu.style().unpolish(menu)
                    menu.style().polish(menu)
                action.setCheckable(True)
                action.setChecked(True)

        menu.ensurePolished()

        actions = menu.actions()
        if actions:
            first_action = next((a for a in actions if not a.isSeparator()), None)
            if first_action:
                menu.setActiveAction(first_action)
        menu.exec(QCursor.pos())

    def on_tag_toggled(self, action):
        """Handles the toggling of a tag from the fast tag menu."""
        if not isinstance(action, QAction):
            return
        tag_name = action.text()
        is_checked = action.isChecked()
        controller = self.viewer.controller
        current_path = controller.get_current_path() if controller else None
        if not current_path:
            return
        try:
            controller.toggle_tag(tag_name, is_checked)
        except Exception as e:
            QMessageBox.critical(self.viewer, UITexts.ERROR, str(e))
        self.viewer.update_status_bar()
        if self.main_win:
            if is_checked:
                self.main_win.add_to_mru_tags(tag_name)
            self.main_win.update_metadata_for_path(current_path)


class FastTagMenu(QMenu):
    """A QMenu that allows toggling actions with the mouse or spacebar without "
    "closing."""
    def __init__(self, manager):
        super().__init__(manager.viewer)
        self.manager = manager
        self.setStyleSheet("""
            QMenu::item[is_hierarchical="true"] {
                color: #a9d0f5;  /* Light blue for hierarchical tags */
                padding-left: 20px;
            }
        """)

    def mouseReleaseEvent(self, event):
        action = self.actionAt(event.pos())
        if action and action.isCheckable():
            action.setChecked(not action.isChecked())
            if self.manager:
                self.manager.on_tag_toggled(action)
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Space or event.key() == Qt.Key_Return:
            action = self.activeAction()
            if action and action.isCheckable():
                # Manually toggle and trigger to keep menu open
                action.setChecked(not action.isChecked())
                if self.manager:
                    self.manager.on_tag_toggled(action)
                event.accept()
                if event.key() == Qt.Key_Space:
                    return
        super().keyPressEvent(event)


class FilmStripWidget(QListWidget):
    """
    A horizontal, scrollable list of thumbnails for image navigation.

    This widget displays thumbnails for all images in the current list,
    allowing the user to quickly jump to an image by clicking its thumbnail.
    It also supports dragging files out of the application.
    """
    def __init__(self, viewer, parent=None):
        """
        Initializes the FilmStripWidget.

        Args:
            viewer (ImageViewer): The viewer that owns this filmstrip.
            parent (QWidget, optional): The parent widget. Defaults to None.
        """
        super().__init__(parent)
        self.viewer = viewer
        self.setDragEnabled(True)

    @property
    def controller(self):
        """Returns the controller of the active pane in the viewer."""
        return self.viewer.controller

    def startDrag(self, supportedActions):
        """
        Initiates a drag-and-drop operation for the selected image(s).
        """
        items = self.selectedItems()
        if not items:
            return

        urls = []
        for item in items:
            row = self.row(item)
            if self.controller and 0 <= row < len(self.controller.image_list):
                path = self.controller.image_list[row]
                urls.append(QUrl.fromLocalFile(path))

        if not urls:
            return

        drag = QDrag(self)
        mime_data = QMimeData()
        mime_data.setUrls(urls)
        drag.setMimeData(mime_data)

        icon = items[0].icon()
        if not icon.isNull():
            pixmap = icon.pixmap(64, 64)
            drag.setPixmap(pixmap)
            drag.setHotSpot(QPoint(pixmap.width() // 2, pixmap.height() // 2))

        drag.exec(Qt.CopyAction)

    def _get_selected_paths(self):
        """Helper to get paths of all selected items."""
        return [item.data(Qt.UserRole)
                for item in self.selectedItems() if item.data(Qt.UserRole)]

    def contextMenuEvent(self, event):
        """Shows a context menu for the selected items."""
        selected_items = self.selectedItems()
        if not selected_items:
            return

        menu = QMenu(self)

        # Clipboard Submenu
        clipboard_menu = menu.addMenu(
            QIcon.fromTheme("edit-copy"), UITexts.CONTEXT_MENU_CLIPBOARD)

        # Copy Image
        action_copy_image = clipboard_menu.addAction(
            QIcon.fromTheme("image-x-generic"), UITexts.VIEWER_MENU_COPY_IMAGE)
        action_copy_image.triggered.connect(self._copy_image_to_clipboard)
        if len(selected_items) > 1:
            action_copy_image.setEnabled(False)

        # Copy Path
        action_copy_path = clipboard_menu.addAction(
            QIcon.fromTheme("document-properties"), UITexts.VIEWER_MENU_COPY_PATH)
        action_copy_path.triggered.connect(self._copy_path_to_clipboard)

        # Copy Directory Path
        action_copy_dir = clipboard_menu.addAction(
            QIcon.fromTheme("folder"), UITexts.CONTEXT_MENU_COPY_DIR)
        action_copy_dir.triggered.connect(self._copy_dir_to_clipboard)

        menu.exec(event.globalPos())

    def _copy_image_to_clipboard(self):
        """Copies the currently selected image to the system clipboard."""
        paths = self._get_selected_paths()
        if len(paths) == 1 and paths[0] and os.path.exists(paths[0]):
            img = QImage(paths[0])
            if not img.isNull():
                QApplication.clipboard().setImage(img)

    def _copy_path_to_clipboard(self):
        """Copies the file path(s) of the selected image(s) to the clipboard."""
        paths = self._get_selected_paths()
        if paths:
            QApplication.clipboard().setText("\n".join(paths))

    def _copy_dir_to_clipboard(self):
        """Copies the directory path(s) of the selected image(s) to the clipboard."""
        paths = self._get_selected_paths()
        if paths:
            dir_paths = sorted(list(set(os.path.dirname(p) for p in paths)))
            QApplication.clipboard().setText("\n".join(dir_paths))


class FaceCanvas(QLabel):
    """
    A custom QLabel that draws face regions on top of the image.
    Handles mouse interaction for creating and managing face regions.
    """
    def __init__(self, viewer):
        super().__init__()
        self.viewer = viewer
        self.controller = viewer.controller
        self.setMouseTracking(True)
        self.drawing = False
        self.start_pos = QPoint()
        self.current_rect = QRect()
        self.dragging = False
        self.drag_start_pos = QPoint()
        self.drag_start_scroll_x = 0
        self.drag_start_scroll_y = 0
        self.editing = False
        self.edit_index = -1
        self.edit_handle = None
        self.edit_start_rect = QRect()
        self.resize_margin = 8

        # Zoom indicator
        self.zoom_indicator_point = None
        self.zoom_indicator_timer = QTimer(self)
        self.zoom_indicator_timer.setSingleShot(True)
        self.zoom_indicator_timer.setInterval(500)  # Show for 500ms
        self.zoom_indicator_timer.timeout.connect(self._clear_zoom_indicator)
        self.crop_rect = QRect()
        self.crop_handle = None
        self.crop_start_pos = QPoint()
        self.crop_start_rect = QRect()

    def _clear_zoom_indicator(self):
        self.zoom_indicator_point = None
        self.update()

    def map_from_source(self, face_data):
        """Maps original normalized face data to current canvas QRect."""
        nx = face_data.get('x', 0)
        ny = face_data.get('y', 0)
        nw = face_data.get('w', 0)
        nh = face_data.get('h', 0)

        rot = self.controller.rotation % 360
        flip_h = self.controller.flip_h
        flip_v = self.controller.flip_v

        cx, cy = nx, ny
        cw, ch = nw, nh

        # 1. Rotation (applied to normalized center coordinates 0.5, 0.5)
        if rot == 90:
            cx, cy = 1.0 - cy, cx
            cw, ch = nh, nw
        elif rot == 180:
            cx, cy = 1.0 - cx, 1.0 - cy
        elif rot == 270:
            cx, cy = cy, 1.0 - cx
            cw, ch = nh, nw

        # 2. Flips
        if flip_h:
            cx = 1.0 - cx
        if flip_v:
            cy = 1.0 - cy

        w = self.width()
        h = self.height()

        # Convert Center-Normalized to Top-Left-Pixel
        rx = (cx - cw / 2) * w
        ry = (cy - ch / 2) * h
        rw = cw * w
        rh = ch * h

        return QRect(int(rx), int(ry), int(rw), int(rh))

    def map_to_source(self, rect):
        """Maps a canvas QRect to original normalized coordinates (x, y, w, h)."""
        w = self.width()
        h = self.height()
        if w == 0 or h == 0:
            return 0.5, 0.5, 0.0, 0.0

        # Pixel Rect to Normalized Center
        cx = (rect.x() + rect.width() / 2.0) / w
        cy = (rect.y() + rect.height() / 2.0) / h
        cw = rect.width() / w
        ch = rect.height() / h

        rot = self.controller.rotation % 360
        flip_h = self.controller.flip_h
        flip_v = self.controller.flip_v

        # Inverse Flips
        if flip_h:
            cx = 1.0 - cx
        if flip_v:
            cy = 1.0 - cy

        # Inverse Rotation
        nx, ny = cx, cy
        nw, nh = cw, ch

        if rot == 90:
            # Inverse of 90 is 270: (y, 1-x)
            nx, ny = cy, 1.0 - cx
            nw, nh = ch, cw
        elif rot == 180:
            nx, ny = 1.0 - cx, 1.0 - cy
        elif rot == 270:
            # Inverse of 270 is 90: (1-y, x)
            nx, ny = 1.0 - cy, cx
            nw, nh = ch, cw

        return nx, ny, nw, nh

    def paintEvent(self, event):
        super().paintEvent(event)
        if not self.controller.show_faces and not self.viewer.crop_mode:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Draw existing faces
        face_color_str = APP_CONFIG.get("face_box_color", DEFAULT_FACE_BOX_COLOR)
        face_color = QColor(face_color_str)
        pet_color_str = APP_CONFIG.get("pet_box_color", DEFAULT_PET_BOX_COLOR)
        pet_color = QColor(pet_color_str)
        body_color_str = APP_CONFIG.get("body_box_color", DEFAULT_BODY_BOX_COLOR)
        body_color = QColor(body_color_str)
        object_color_str = APP_CONFIG.get("object_box_color", DEFAULT_OBJECT_BOX_COLOR)
        object_color = QColor(object_color_str)
        landmark_color_str = APP_CONFIG.get("landmark_box_color",
                                            DEFAULT_LANDMARK_BOX_COLOR)
        landmark_color = QColor(landmark_color_str)

        if self.controller.show_faces:
            for face in self.controller.faces:
                rect = self.map_from_source(face)

                is_pet = face.get('type') == 'Pet'
                is_body = face.get('type') == 'Body'
                is_object = face.get('type') == 'Object'
                is_landmark = face.get('type') == 'Landmark'

                if is_pet:
                    color = pet_color
                elif is_body:
                    color = body_color
                elif is_object:
                    color = object_color
                elif is_landmark:
                    color = landmark_color
                else:
                    color = face_color

                painter.setPen(QPen(color, 2))
                painter.setBrush(Qt.NoBrush)
                painter.drawRect(rect)

                name = face.get('name', '')
                if name:
                    display_name = name.split('/')[-1]
                    fm = painter.fontMetrics()
                    tw = fm.horizontalAdvance(display_name)
                    th = fm.height()

                    bg_height = th + 4
                    bg_width = tw + 8
                    # Default position is top-left, outside the box
                    bg_y = rect.top() - bg_height

                    # If there is no space at the top, move it to the bottom
                    if bg_y < 0:
                        bg_y = rect.bottom()

                    bg_rect = QRect(rect.left(), bg_y, bg_width, bg_height)
                    painter.setPen(Qt.NoPen)
                    painter.setBrush(QColor(100, 100, 100))
                    painter.drawRect(bg_rect)
                    painter.setPen(QPen(color, 1))
                    painter.drawText(bg_rect, Qt.AlignCenter, display_name)

        # Draw rubber band for new face
        if self.drawing and not self.viewer.crop_mode:
            painter.setPen(QPen(QColor(0, 120, 255), 2, Qt.DashLine))
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(self.current_rect)

        # Draw crop rectangle if in crop mode
        if self.viewer.crop_mode and not self.crop_rect.isNull():
            # Draw dimmed overlay outside crop rect
            painter.setBrush(QColor(0, 0, 0, 160))
            painter.setPen(Qt.NoPen)
            path = QPainterPath()
            path.addRect(QRectF(self.rect()))
            path.addRect(QRectF(self.crop_rect))
            path.setFillRule(Qt.OddEvenFill)
            painter.drawPath(path)

            painter.setPen(QPen(QColor(255, 255, 0), 2, Qt.DashLine))
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(self.crop_rect)

            # Draw rule of thirds grid
            if self.crop_rect.width() > 60 and self.crop_rect.height() > 60:
                grid_pen = QPen(QColor(255, 255, 255, 100), 1, Qt.SolidLine)
                painter.setPen(grid_pen)

                x, y = self.crop_rect.x(), self.crop_rect.y()
                w, h = self.crop_rect.width(), self.crop_rect.height()

                x1, x2 = int(x + w / 3), int(x + 2 * w / 3)
                y1, y2 = int(y + h / 3), int(y + 2 * h / 3)

                painter.drawLine(x1, y, x1, y + h)
                painter.drawLine(x2, y, x2, y + h)
                painter.drawLine(x, y1, x + w, y1)
                painter.drawLine(x, y2, x + w, y2)

            # Draw crop handles
            painter.setPen(QPen(QColor(0, 0, 0), 1))
            painter.setBrush(QColor(255, 255, 255))
            handle_size = 8
            offset = handle_size // 2
            handles = [
                self.crop_rect.topLeft(), self.crop_rect.topRight(),
                self.crop_rect.bottomLeft(), self.crop_rect.bottomRight()
            ]
            for pt in handles:
                painter.drawRect(pt.x() - offset, pt.y() - offset,
                                 handle_size, handle_size)

        # Draw zoom indicator
        if self.zoom_indicator_point:
            painter.setPen(QPen(QColor(255, 255, 0), 2))  # Yellow crosshair
            painter.drawLine(self.zoom_indicator_point.x() - 10,
                             self.zoom_indicator_point.y(),
                             self.zoom_indicator_point.x() + 10,
                             self.zoom_indicator_point.y())
            painter.drawLine(self.zoom_indicator_point.x(),
                             self.zoom_indicator_point.y() - 10,
                             self.zoom_indicator_point.x(),
                             self.zoom_indicator_point.y() + 10)

    def _hit_test(self, pos):
        """Determines if the mouse is over a name, handle, or body."""
        if not self.controller.show_faces:
            return -1, None

        margin = self.resize_margin
        fm = self.fontMetrics()

        # Iterate in reverse to pick top-most face if overlapping
        for i in range(len(self.controller.faces) - 1, -1, -1):
            face = self.controller.faces[i]
            rect = self.map_from_source(face)

            # Check if click is on the name label first
            name = face.get('name', '')
            if name:
                display_name = name.split('/')[-1]
                tw = fm.horizontalAdvance(display_name)
                th = fm.height()
                bg_height = th + 4
                bg_width = tw + 8
                bg_y = rect.top() - bg_height
                if bg_y < 0:
                    bg_y = rect.bottom()

                bg_rect = QRect(rect.left(), bg_y, bg_width, bg_height)
                if bg_rect.contains(pos):
                    return i, 'NAME'

            # Check outer boundary with margin
            outer = rect.adjusted(-margin, -margin, margin, margin)
            if not outer.contains(pos):
                continue

            x, y = pos.x(), pos.y()
            l, t, r, b = rect.left(), rect.top(), rect.right(), rect.bottom()

            # Determine proximity to edges
            on_left = abs(x - l) <= margin
            on_right = abs(x - r) <= margin
            on_top = abs(y - t) <= margin
            on_bottom = abs(y - b) <= margin

            # Check Corners
            if on_left and on_top:
                return i, 'TL'
            if on_right and on_top:
                return i, 'TR'
            if on_left and on_bottom:
                return i, 'BL'
            if on_right and on_bottom:
                return i, 'BR'

            # Check Edges
            if on_left:
                return i, 'L'
            if on_right:
                return i, 'R'
            if on_top:
                return i, 'T'
            if on_bottom:
                return i, 'B'

            if rect.contains(pos):
                return i, 'BODY'
        return -1, None

    def _hit_test_crop(self, pos):
        """Determines if mouse is over a crop handle or body."""
        if self.crop_rect.isNull():
            return None

        handle_size = 12  # Hit area slightly larger than drawn handle
        # margin = handle_size // 2

        rects = {
            'TL': QRect(0, 0, handle_size, handle_size),
            'TR': QRect(0, 0, handle_size, handle_size),
            'BL': QRect(0, 0, handle_size, handle_size),
            'BR': QRect(0, 0, handle_size, handle_size)
        }
        rects['TL'].moveCenter(self.crop_rect.topLeft())
        rects['TR'].moveCenter(self.crop_rect.topRight())
        rects['BL'].moveCenter(self.crop_rect.bottomLeft())
        rects['BR'].moveCenter(self.crop_rect.bottomRight())

        for key, r in rects.items():
            if r.contains(pos):
                return key

        if self.crop_rect.contains(pos):
            return 'BODY'
        return None

    def mousePressEvent(self, event):
        """Handles mouse press for drawing new faces or panning."""
        if hasattr(self.viewer, 'reset_inactivity_timer'):
            self.viewer.reset_inactivity_timer()
        if self.viewer.crop_mode and event.button() == Qt.LeftButton:
            handle = self._hit_test_crop(event.position().toPoint())
            if handle:
                self.crop_handle = handle
                self.crop_start_pos = event.position().toPoint()
                self.crop_start_rect = self.crop_rect
                event.accept()
                return

            self.drawing = True
            self.start_pos = event.position().toPoint()
            self.crop_rect = QRect()
            self.update()
            event.accept()
            return

        # Activate the pane on click
        if hasattr(self.viewer, 'activate'):
            self.viewer.activate()

        if self.controller.show_faces and event.button() == Qt.LeftButton:
            self.start_pos = event.position().toPoint()

            # Check if we clicked on an existing face to edit
            idx, handle = self._hit_test(self.start_pos)
            if idx != -1:
                if handle == 'NAME':
                    self.viewer.rename_face(self.controller.faces[idx])
                    event.accept()
                    return

                self.editing = True
                self.edit_index = idx
                self.edit_handle = handle
                self.edit_start_rect = self.map_from_source(self.controller.faces[idx])
                event.accept()
            else:
                self.drawing = True
                self.current_rect = QRect(self.start_pos, self.start_pos)
                event.accept()
        elif event.button() == Qt.LeftButton:
            self.dragging = True
            self.drag_start_pos = event.globalPosition().toPoint()
            self.drag_start_scroll_x = \
                self.viewer.scroll_area.horizontalScrollBar().value()
            self.drag_start_scroll_y = \
                self.viewer.scroll_area.verticalScrollBar().value()
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()
        else:
            event.ignore()

    def mouseMoveEvent(self, event):
        """Handles mouse move for drawing new faces or panning."""
        if hasattr(self.viewer, 'reset_inactivity_timer'):
            self.viewer.reset_inactivity_timer()
        if self.viewer.crop_mode:
            curr_pos = event.position().toPoint()

            if self.crop_handle:
                dx = curr_pos.x() - self.crop_start_pos.x()
                dy = curr_pos.y() - self.crop_start_pos.y()
                rect = QRect(self.crop_start_rect)

                if self.crop_handle == 'BODY':
                    rect.translate(dx, dy)
                    # Bounds check
                    rect.moveLeft(max(0, rect.left()))
                    rect.moveTop(max(0, rect.top()))
                    if rect.right() > self.width():
                        rect.moveRight(self.width())
                    if rect.bottom() > self.height():
                        rect.moveBottom(self.height())
                else:
                    # Determine fixed anchor point based on handle
                    fixed = None
                    moving = None
                    if self.crop_handle == 'TL':
                        fixed = self.crop_start_rect.bottomRight()
                        moving = self.crop_start_rect.topLeft()
                    elif self.crop_handle == 'TR':
                        fixed = self.crop_start_rect.bottomLeft()
                        moving = self.crop_start_rect.topRight()
                    elif self.crop_handle == 'BL':
                        fixed = self.crop_start_rect.topRight()
                        moving = self.crop_start_rect.bottomLeft()
                    elif self.crop_handle == 'BR':
                        fixed = self.crop_start_rect.topLeft()
                        moving = self.crop_start_rect.bottomRight()

                    if fixed is None or moving is None:
                        return

                    # Calculate new moving point candidate
                    current_moving = moving + QPoint(dx, dy)

                    # Vector from fixed to moving
                    w = current_moving.x() - fixed.x()
                    h = current_moving.y() - fixed.y()

                    # Aspect ratio constraint with Shift
                    if event.modifiers() & Qt.ShiftModifier \
                       and self.crop_start_rect.height() != 0:
                        ratio = self.crop_start_rect.width() / \
                            self.crop_start_rect.height()
                        if abs(w) / ratio > abs(h):
                            h = w / ratio
                        else:
                            w = h * ratio

                    rect = QRect(fixed, QPoint(int(fixed.x() + w), int(fixed.y() + h)))

                self.crop_rect = rect.normalized()
                self.update()
                event.accept()
                return
            elif self.drawing:
                if event.modifiers() & Qt.ShiftModifier:
                    dx = curr_pos.x() - self.start_pos.x()
                    dy = curr_pos.y() - self.start_pos.y()
                    side = max(abs(dx), abs(dy))
                    curr_pos = QPoint(
                        self.start_pos.x() + (side if dx >= 0 else -side),
                        self.start_pos.y() + (side if dy >= 0 else -side))
                self.crop_rect = QRect(self.start_pos,
                                       curr_pos).normalized()
                self.update()
                event.accept()
                return
            else:
                # Cursor update
                handle = self._hit_test_crop(curr_pos)
                if handle in ['TL', 'BR']:
                    self.setCursor(Qt.SizeFDiagCursor)
                elif handle in ['TR', 'BL']:
                    self.setCursor(Qt.SizeBDiagCursor)
                elif handle == 'BODY':
                    self.setCursor(Qt.SizeAllCursor)
                else:
                    self.setCursor(Qt.CrossCursor)
                event.accept()
                return

        if self.drawing:
            self.current_rect = QRect(self.start_pos,
                                      event.position().toPoint()).normalized()
            self.update()
            event.accept()
        elif self.editing:
            curr_pos = event.position().toPoint()
            dx = curr_pos.x() - self.start_pos.x()
            dy = curr_pos.y() - self.start_pos.y()

            # Calculate new rect based on handle
            new_rect = QRect(self.edit_start_rect)
            min_size = 5

            if self.edit_handle == 'BODY':
                new_rect.translate(dx, dy)
            else:
                if 'L' in self.edit_handle:
                    new_rect.setLeft(
                        min(new_rect.right() - min_size,
                            self.edit_start_rect.left() + dx))
                if 'R' in self.edit_handle:
                    new_rect.setRight(
                        max(new_rect.left() + min_size,
                            self.edit_start_rect.right() + dx))
                if 'T' in self.edit_handle:
                    new_rect.setTop(
                        min(new_rect.bottom() - min_size,
                            self.edit_start_rect.top() + dy))
                if 'B' in self.edit_handle:
                    new_rect.setBottom(
                        max(new_rect.top() + min_size,
                            self.edit_start_rect.bottom() + dy))

            # Normalize and update face data
            # Convert screen rect back to normalized source coordinates
            nx, ny, nw, nh = self.map_to_source(new_rect)

            # Update the face in the controller in real-time
            face = self.controller.faces[self.edit_index]
            face['x'], face['y'], face['w'], face['h'] = nx, ny, nw, nh

            self.update()
            event.accept()
        elif not self.drawing and not self.dragging and self.controller.show_faces:
            # Update cursor based on hover
            _, handle = self._hit_test(event.position().toPoint())
            if handle in ['TL', 'BR']:
                self.setCursor(Qt.SizeFDiagCursor)
            elif handle in ['TR', 'BL']:
                self.setCursor(Qt.SizeBDiagCursor)
            elif handle in ['T', 'B']:
                self.setCursor(Qt.SizeVerCursor)
            elif handle in ['L', 'R']:
                self.setCursor(Qt.SizeHorCursor)
            elif handle == 'BODY':
                self.setCursor(Qt.SizeAllCursor)
            elif handle == 'NAME':
                self.setCursor(Qt.PointingHandCursor)
            else:
                self.setCursor(Qt.CrossCursor)
            event.accept()
        elif self.dragging:
            delta = event.globalPosition().toPoint() - self.drag_start_pos
            h_bar = self.viewer.scroll_area.horizontalScrollBar()
            v_bar = self.viewer.scroll_area.verticalScrollBar()
            h_bar.setValue(self.drag_start_scroll_x - delta.x())
            v_bar.setValue(self.drag_start_scroll_y - delta.y())
            event.accept()
        else:
            event.ignore()

    def mouseReleaseEvent(self, event):
        """Handles mouse release for drawing new faces or panning."""
        if self.viewer.crop_mode:
            if self.crop_handle:
                self.crop_handle = None
                self.update()
            elif self.drawing:
                self.drawing = False
                self.update()

            event.accept()
            return

        if self.drawing:
            self.drawing = False
            if self.current_rect.width() > 10 and self.current_rect.height() > 10:
                region_type = self.viewer.viewer._next_region_type
                # Check if Control key was held down to allow selecting type
                if event.modifiers() & Qt.ControlModifier:
                    menu = QMenu(self)
                    action_face = menu.addAction(UITexts.TYPE_FACE)
                    action_pet = menu.addAction(UITexts.TYPE_PET)
                    action_body = menu.addAction(UITexts.TYPE_BODY)
                    action_object = menu.addAction(UITexts.TYPE_OBJECT)
                    action_landmark = menu.addAction(UITexts.TYPE_LANDMARK)
                    # Show menu at mouse release position
                    res = menu.exec(event.globalPosition().toPoint())
                    if res == action_pet:
                        region_type = "Pet"
                    elif res == action_body:
                        region_type = "Body"
                    elif res == action_object:
                        region_type = "Object"
                    elif res == action_landmark:
                        region_type = "Landmark"
                    elif res == action_face:
                        region_type = "Face"
                    else:
                        # Cancelled
                        self.current_rect = QRect()
                        self.update()
                        return

                history_list = []
                if self.viewer.main_win:
                    if region_type == "Pet":
                        history_list = self.viewer.main_win.pet_names_history
                    elif region_type == "Body":
                        history_list = self.viewer.main_win.body_names_history
                    elif region_type == "Object":
                        history_list = self.viewer.main_win.object_names_history
                    elif region_type == "Landmark":
                        history_list = self.viewer.main_win.landmark_names_history
                    else:
                        history_list = self.viewer.main_win.face_names_history

                history = history_list \
                    if self.viewer.main_win else []

                setting_key = f"{region_type.lower()}_use_last_name"
                suggested = history[0] if history and APP_CONFIG.get(
                    setting_key, False) else ""

                full_tag, updated_history, ok = FaceNameDialog.get_name(
                    self.viewer, history, current_name=suggested,
                    main_win=self.viewer.main_win, region_type=region_type)

                if ok and full_tag:
                    if not self.controller.show_faces:
                        self.viewer.viewer.toggle_faces()

                    if self.viewer.main_win:
                        if region_type == "Pet":
                            self.viewer.main_win.pet_names_history = updated_history
                        elif region_type == "Body":
                            self.viewer.main_win.body_names_history = updated_history
                        elif region_type == "Object":
                            self.viewer.main_win.object_names_history = updated_history
                        elif region_type == "Landmark":
                            self.viewer.main_win.landmark_names_history = \
                                updated_history
                        else:
                            self.viewer.main_win.face_names_history = updated_history

                    center_x, center_y, norm_w, norm_h = self.map_to_source(
                        self.current_rect)

                    self.controller.add_face(
                        full_tag, center_x, center_y, norm_w, norm_h,
                        region_type=region_type)

                    if region_type != "Face" and APP_CONFIG.get("areas_reset_to_face", False):
                        self.viewer.viewer.set_next_region_type("Face")

                    self.controller.toggle_tag(full_tag, True)
                    self.update()  # Repaint to show the new face with its name
            self.current_rect = QRect()
            self.update()
            event.accept()
        elif self.editing:
            # Finish editing
            self.editing = False
            self.edit_index = -1
            self.edit_handle = None
            self.controller.save_faces()
            event.accept()
        elif self.dragging:
            self.dragging = False
            self.setCursor(Qt.ArrowCursor)
            event.accept()
        else:
            event.ignore()

    def mouseDoubleClickEvent(self, event):
        """Zooms to a face on double-click."""
        if self.controller.show_faces and event.button() == Qt.LeftButton:
            # The event position is already local to the canvas
            clicked_face = self.viewer._get_clicked_face(event.position().toPoint())
            if clicked_face:
                self.viewer.zoom_manager.zoom_to_rect(clicked_face)
                event.accept()
                return

        # Double click to toggle fullscreen if handled by viewer/pane
        if hasattr(self.viewer, 'toggle_fullscreen'):
            self.viewer.toggle_fullscreen()
        # If no face was double-clicked, pass the event on
        super().mouseDoubleClickEvent(event)


class SlideshowManager(QObject):
    """
    Manages the slideshow functionality for the ImageViewer.
    Separates the timing logic from the UI logic.
    """
    def __init__(self, viewer):
        super().__init__(viewer)
        self.viewer = viewer
        self.timer = QTimer(self)
        self.timer.setInterval(3000)
        self.timer.timeout.connect(self._on_timeout)
        self._reverse = False

    def _on_timeout(self):
        """Called when the timer fires to advance the slideshow."""
        if self._reverse:
            self.viewer.prev_image()
        else:
            self.viewer.next_image()

    def start(self, reverse=False):
        """Starts the slideshow in the specified direction."""
        self._reverse = reverse
        self.timer.start()

    def stop(self):
        """Stops the slideshow."""
        self.timer.stop()

    def toggle(self, reverse=False):
        """Toggles the slideshow on/off or changes direction."""
        if self.timer.isActive():
            if self._reverse == reverse:
                self.stop()
            else:
                self.start(reverse)
        else:
            self.start(reverse)

    def is_running(self):
        """Returns whether the slideshow is currently active."""
        return self.timer.isActive()

    def is_forward(self):
        """Returns whether the slideshow is running in forward mode."""
        return self.timer.isActive() and not self._reverse

    def is_reverse(self):
        """Returns whether the slideshow is running in reverse mode."""
        return self.timer.isActive() and self._reverse

    def set_interval(self, ms):
        """Sets the interval in milliseconds."""
        self.timer.setInterval(ms)
        if self.timer.isActive():
            self.timer.start()

    def get_interval(self):
        """Returns the current interval in milliseconds."""
        return self.timer.interval()


class ZoomManager(QObject):
    """
    Manages zoom calculations and state for the ImageViewer.
    """
    zoomed = Signal(float)

    def __init__(self, viewer):
        super().__init__(viewer)
        self.viewer = viewer

    def zoom(self, factor=1.1, reset=False, focus_point=None, absolute_factor=None):
        """Applies zoom to the image, centering on focus_point if provided."""
        if not self.viewer.controller or \
           self.viewer.controller.pixmap_original.isNull():
            return

        c_point = None

        if reset:
            self.viewer.controller.zoom_factor = 1.0
            self.viewer.update_view(resize_win=True)
            if self.viewer.canvas:
                c_point = self.viewer.canvas.rect().center()
        elif absolute_factor is not None:  # New: set absolute zoom factor
            self.viewer.controller.zoom_factor = absolute_factor
            # Don't resize window for sync zoom
            self.viewer.update_view(resize_win=False)
            if focus_point is not None and self.viewer.canvas:
                scroll_area = self.viewer.scroll_area
                viewport = scroll_area.viewport()
                v_point = viewport.mapFrom(self.viewer, focus_point)
                c_point = self.viewer.canvas.mapFrom(viewport, v_point)
        else:
            # 1. Determine focus point in viewport coordinates
            scroll_area = self.viewer.scroll_area
            viewport = scroll_area.viewport()

            if focus_point is None:
                v_point = viewport.rect().center()
            else:
                # focus_point is relative to the self.viewer widget
                # (ImageViewer or ImagePane)
                v_point = viewport.mapFrom(self.viewer, focus_point)

            # 2. Map focus point to canvas coordinates before zoom
            c_point = self.viewer.canvas.mapFrom(viewport, v_point)

            self.viewer.controller.zoom_factor *= factor
            # Apply update (this resizes the canvas)
            self.viewer.update_view(resize_win=(not self.viewer.isFullScreen()))

            # 3. Adjust scrollbars to maintain pixel under cursor
            scroll_area.horizontalScrollBar().setValue(
                int(c_point.x() * factor - v_point.x()))
            scroll_area.verticalScrollBar().setValue(
                int(c_point.y() * factor - v_point.y()))

            # Notify the main window that the image (and possibly index) has changed
            # so it can update its selection.
            self.viewer.index_changed.emit(self.viewer.controller.index)

        if focus_point is not None and self.viewer.canvas:
            self.viewer.canvas.zoom_indicator_point = c_point
            self.viewer.canvas.zoom_indicator_timer.start()
            self.viewer.canvas.update()

        self.zoomed.emit(self.viewer.controller.zoom_factor)
        if hasattr(self.viewer, 'sync_filmstrip_selection'):
            self.viewer.sync_filmstrip_selection(self.viewer.controller.index)

    def toggle_fit_to_screen(self):
        """
        Toggles between fitting the image to the window and 100% actual size.
        """
        # If close to 100%, fit to window. Otherwise 100%.
        if abs(self.viewer.controller.zoom_factor - 1.0) < 0.01:
            self.fit_to_window()
        else:
            self.zoom(1.0, reset=True)

    def fit_to_window(self):
        """
        Calculates the zoom factor required to make the image fit perfectly
        within the current viewport dimensions.
        """
        if self.viewer.controller.pixmap_original.isNull():
            return

        viewport = self.viewer.scroll_area.viewport()
        w_avail = viewport.width()
        h_avail = viewport.height()

        transform = QTransform().rotate(self.viewer.controller.rotation)
        transformed_pixmap = self.viewer.controller.pixmap_original.transformed(
            transform, Qt.SmoothTransformation)
        img_w = transformed_pixmap.width()
        img_h = transformed_pixmap.height()

        if img_w == 0 or img_h == 0:
            return

        self.viewer.controller.zoom_factor = min(w_avail / img_w, h_avail / img_h)
        self.zoomed.emit(self.viewer.controller.zoom_factor)
        self.viewer.update_view(resize_win=False)

    def calculate_initial_zoom(self, available_w, available_h, is_fullscreen):
        """Calculates and sets the initial zoom factor when loading an image."""
        orig_w = self.viewer.controller.pixmap_original.width()
        orig_h = self.viewer.controller.pixmap_original.height()

        if orig_w > 0 and orig_h > 0:
            factor = min(available_w / orig_w, available_h / orig_h)
            if is_fullscreen:
                self.viewer.controller.zoom_factor = factor
            else:
                self.viewer.controller.zoom_factor = min(1.0, factor)
        else:
            self.viewer.controller.zoom_factor = 1.0

        self.zoomed.emit(self.viewer.controller.zoom_factor)

    def zoom_to_rect(self, face_rect):
        """Zooms and pans the view to center on a given normalized rectangle."""
        if self.viewer.controller.pixmap_original.isNull():
            return

        viewport = self.viewer.scroll_area.viewport()
        vp_w = viewport.width()
        vp_h = viewport.height()

        # Use the original pixmap dimensions for zoom calculation
        transform = QTransform().rotate(self.viewer.controller.rotation)
        transformed_pixmap = self.viewer.controller.pixmap_original.transformed(
            transform, Qt.SmoothTransformation)
        img_w = transformed_pixmap.width()
        img_h = transformed_pixmap.height()

        if img_w == 0 or img_h == 0:
            return

        # Calculate the size of the face in original image pixels
        face_pixel_w = face_rect['w'] * img_w
        face_pixel_h = face_rect['h'] * img_h

        if face_pixel_w == 0 or face_pixel_h == 0:
            return

        # Calculate zoom factor to make the face fill ~70% of the viewport
        zoom_w = (vp_w * 0.7) / face_pixel_w
        zoom_h = (vp_h * 0.7) / face_pixel_h
        new_zoom = min(zoom_w, zoom_h)

        self.viewer.controller.zoom_factor = new_zoom
        self.zoomed.emit(new_zoom)
        self.viewer.update_view(resize_win=False)

        # Defer centering until after the view has been updated
        QTimer.singleShot(0, lambda: self._center_on_face(face_rect))

    def _center_on_face(self, face_rect):
        """Scrolls the viewport to center on the face."""
        canvas_w = self.viewer.canvas.width()
        canvas_h = self.viewer.canvas.height()

        viewport = self.viewer.scroll_area.viewport()
        vp_w = viewport.width()
        vp_h = viewport.height()

        # Face center in the newly zoomed canvas coordinates
        face_center_x_px = face_rect['x'] * canvas_w
        face_center_y_px = face_rect['y'] * canvas_h

        # Calculate the target scrollbar value to center the point
        scroll_x = face_center_x_px - (vp_w / 2)
        scroll_y = face_center_y_px - (vp_h / 2)

        self.viewer.scroll_area.horizontalScrollBar().setValue(int(scroll_x))
        self.viewer.scroll_area.verticalScrollBar().setValue(int(scroll_y))


class ImagePane(QWidget):
    """
    A single image viewport containing the canvas, scroll area, and controller.
    Used within ImageViewer to support comparison modes.
    """
    activated = Signal()
    index_changed = Signal(int)
    scrolled = Signal(float, float)

    def __init__(self, parent_viewer, cache, image_list, index, initial_tags=None,
                 initial_rating=0):
        super().__init__(parent_viewer)
        self.viewer = parent_viewer  # Reference to main ImageViewer
        self.main_win = parent_viewer.main_win
        self.cache = cache

        self.controller = ImageController(image_list, index, initial_tags,
                                          initial_rating)
        if self.main_win:
            self.controller.show_faces = self.main_win.show_faces

        # Connect signals
        self.controller.metadata_changed.connect(self.viewer.on_metadata_changed)
        self.controller.list_updated.connect(self.viewer.on_controller_list_updated)

        self.zoom_manager = ZoomManager(self)
        self.canvas = FaceCanvas(self)
        self.movie = None
        self.crop_mode = False

        # Layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.scroll_area = QScrollArea()
        self.scroll_area.setAlignment(Qt.AlignCenter)
        self.scroll_area.setStyleSheet("background-color: #000; border: none;")
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_area.setWidget(self.canvas)
        layout.addWidget(self.scroll_area)

        self.scroll_area.horizontalScrollBar().valueChanged.connect(self._on_scroll)
        self.scroll_area.verticalScrollBar().valueChanged.connect(self._on_scroll)
        self._suppress_scroll_signal = False

    def activate(self):
        """Sets this pane as the active one in the viewer."""
        self.viewer.set_active_pane(self)
        self.activated.emit()

    def reset_inactivity_timer(self):
        """Delegates to parent viewer."""
        self.viewer.reset_inactivity_timer()

    def sync_filmstrip_selection(self, index):
        """Delegates to parent viewer if this is the active pane."""
        if self.viewer.active_pane == self:
            self.viewer.sync_filmstrip_selection(index)

    def load_and_fit_image(self, restore_config=None):
        """Loads image using shared logic, adapted for Pane."""
        # reuse logic from ImageViewer (now moved/adapted)
        self.viewer.load_and_fit_image_for_pane(self, restore_config)

    def update_view(self, resize_win=False):
        """Updates this pane's view."""
        self.viewer.update_view_for_pane(self, resize_win)

    def _on_scroll(self):
        if self._suppress_scroll_signal:
            return
        h_bar = self.scroll_area.horizontalScrollBar()
        v_bar = self.scroll_area.verticalScrollBar()

        h_max = h_bar.maximum()
        v_max = v_bar.maximum()

        x_pct = h_bar.value() / h_max if h_max > 0 else 0
        y_pct = v_bar.value() / v_max if v_max > 0 else 0

        self.scrolled.emit(x_pct, y_pct)

    def set_scroll_relative(self, x_pct, y_pct):
        self._suppress_scroll_signal = True
        h_bar = self.scroll_area.horizontalScrollBar()
        v_bar = self.scroll_area.verticalScrollBar()
        h_bar.setValue(int(x_pct * h_bar.maximum()))
        v_bar.setValue(int(y_pct * v_bar.maximum()))
        self._suppress_scroll_signal = False

    def toggle_fullscreen(self):
        self.viewer.toggle_fullscreen()

    def next_image(self):
        self.controller.next()
        self.index_changed.emit(self.controller.index)
        self.load_and_fit_image()

    def prev_image(self):
        self.controller.prev()
        self.index_changed.emit(self.controller.index)
        self.load_and_fit_image()

    def first_image(self):
        self.controller.first()
        self.index_changed.emit(self.controller.index)
        self.load_and_fit_image()

    def last_image(self):
        self.controller.last()
        self.index_changed.emit(self.controller.index)
        self.load_and_fit_image()

    def _get_clicked_face(self, pos):
        return self.viewer._get_clicked_face_for_pane(self, pos)

    def rename_face(self, face):
        self.viewer.rename_face(face)

    def cleanup(self):
        if self.movie:
            self.movie.stop()
        self.controller.cleanup()

    # Event handlers specific to the pane surface (e.g. drop) can go here
    def mousePressEvent(self, event):
        self.activate()
        super().mousePressEvent(event)

    def update_image_list(self, new_list):
        # Logic similar to ImageViewer.update_image_list but for this controller
        current_path = self.controller.get_current_path()
        if not current_path and new_list:
            self.controller.update_list(new_list, 0)
            self.load_and_fit_image()
            return

        if current_path in new_list:
            idx = new_list.index(current_path)
            self.controller.update_list(new_list, idx)
        else:
            self.controller.update_list(new_list)
            if self.controller.get_current_path() != current_path:
                self.load_and_fit_image()


class ImageViewer(QWidget):
    """
    A standalone window for viewing and manipulating a single image.

    This viewer supports navigation (next/previous) through a list of images,
    zooming, panning, rotation, mirroring, and a slideshow mode. It also
    integrates a filmstrip for quick navigation and a status bar for showing
    image information.

    Signals:
        index_changed(int): Emitted when the current image index changes.
    """
    index_changed = Signal(int)
    activated = Signal()

    def __init__(self, cache, image_list, current_index, initial_tags=None,
                 initial_rating=0, parent=None,
                 restore_config=None, persistent=False, first_load=True):
        """
        Initializes the ImageViewer window.

        Args:
            cache (ThumbnailCache): The thumbnail cache instance.
            image_list (list): The list of image paths to display.
            current_index (int): The starting index in the image_list.
            parent (QWidget, optional): The parent widget (MainWindow). Defaults to
            None.
            restore_config (dict, optional): A state dictionary to restore a previous
                                             session. Defaults to None.
            persistent (bool, optional): If True, the viewer is part of a saved layout.
                                         Defaults to False.
        """
        super().__init__()
        self.main_win = parent
        self.cache = cache
        self.set_window_icon()
        self._next_region_type = "Face"
        self.setAttribute(Qt.WA_DeleteOnClose)
        # Standard window buttons
        self.setWindowFlags(self.windowFlags() | Qt.WindowMaximizeButtonHint |
                            Qt.WindowMinimizeButtonHint)

        self._first_load = first_load
        self._is_persistent = persistent
        self.crop_mode = False
        self._wheel_scroll_accumulator = 0
        self.filmstrip_loader = None

        # Pane management
        self.panes = []
        self.active_pane = None
        self.panes_linked = True

        self.fast_tag_manager = FastTagManager(self)
        self._setup_shortcuts()
        self._setup_actions()

        self.inhibit_cookie = None

        filmstrip_position = 'bottom'  # Default
        if self.main_win and hasattr(self.main_win, 'filmstrip_position'):
            filmstrip_position = self.main_win.filmstrip_position

        # UI Layout
        is_vertical_filmstrip = filmstrip_position in ('left', 'right')
        if is_vertical_filmstrip:
            self.layout = QHBoxLayout(self)
        else:
            self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)

        # Container for panes (Grid)
        self.view_container = QWidget()
        self.grid_layout = QGridLayout(self.view_container)
        self.grid_layout.setContentsMargins(0, 0, 0, 0)
        self.grid_layout.setSpacing(2)

        # self.scroll_area = QScrollArea() ... Moved to ImagePane
        # self.canvas = FaceCanvas(self) ... Moved to ImagePane
        # self.scroll_area.setWidget(self.canvas)

        self.filmstrip = FilmStripWidget(self)
        self.filmstrip.setSpacing(2)
        self.filmstrip.itemClicked.connect(self.on_filmstrip_clicked)

        self.status_bar_container = QWidget()
        self.status_bar_container.setStyleSheet("background-color: #222; color: #aaa; "
                                                "font-size: 11px;")
        sb_layout = QHBoxLayout(self.status_bar_container)
        sb_layout.setContentsMargins(5, 2, 5, 2)
        self.sb_index_label = QLabel()
        self.sb_tags_label = QLabel()
        self.sb_info_label = QLabel()
        self.sb_info_label.setAlignment(Qt.AlignRight)
        sb_layout.addWidget(self.sb_index_label)
        sb_layout.addWidget(self.sb_tags_label)
        sb_layout.addStretch()
        sb_layout.addWidget(self.sb_info_label)

        if is_vertical_filmstrip:
            center_pane = QWidget()
            center_layout = QVBoxLayout(center_pane)
            center_layout.setContentsMargins(0, 0, 0, 0)
            center_layout.setSpacing(0)
            center_layout.addWidget(self.view_container)
            center_layout.addWidget(self.status_bar_container)

            self.filmstrip.setFixedWidth(120)
            self.filmstrip.setViewMode(QListWidget.IconMode)
            self.filmstrip.setFlow(QListWidget.TopToBottom)
            self.filmstrip.setWrapping(False)
            self.filmstrip.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            self.filmstrip.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            self.filmstrip.setIconSize(QSize(100, 100))

            border_side = "border-right" if filmstrip_position == 'left' \
                else "border-left"
            self.filmstrip.setStyleSheet(f"QListWidget {{ background-color: #222; "
                                         f"{border_side}: 1px solid #444; }} "
                                         "QListWidget::item:selected "
                                         "{ background-color: #3498db; }")

            if filmstrip_position == 'left':
                self.layout.addWidget(self.filmstrip)
                self.layout.addWidget(center_pane)
            else:
                self.layout.addWidget(center_pane)
                self.layout.addWidget(self.filmstrip)
        else:
            self.filmstrip.setFixedHeight(100)
            self.filmstrip.setViewMode(QListWidget.IconMode)
            self.filmstrip.setFlow(QListWidget.LeftToRight)
            self.filmstrip.setWrapping(False)
            self.filmstrip.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            self.filmstrip.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            self.filmstrip.setIconSize(QSize(80, 80))

            border_side = "border-top" if filmstrip_position == 'bottom' \
                else "border-bottom"
            self.filmstrip.setStyleSheet(f"QListWidget {{ background-color: #222; "
                                         f"{border_side}: 1px solid #444; }} "
                                         "QListWidget::item:selected "
                                         "{ background-color: #3498db; }")

            if filmstrip_position == 'top':
                self.layout.addWidget(self.filmstrip)
                self.layout.addWidget(self.view_container)
                self.layout.addWidget(self.status_bar_container)
            else:  # bottom
                self.layout.addWidget(self.view_container)
                self.layout.addWidget(self.filmstrip)
                self.layout.addWidget(self.status_bar_container)

        if self.main_win:
            self.filmstrip.setVisible(self.main_win.show_filmstrip)
        else:
            self.filmstrip.setVisible(False)

        if self.main_win:
            self.status_bar_container.setVisible(self.main_win.show_viewer_status_bar)

        # Inactivity timer for fullscreen
        self.hide_controls_timer = QTimer(self)
        self.hide_controls_timer.setInterval(3000)
        self.hide_controls_timer.timeout.connect(self.hide_controls)

        # Slideshow
        self.slideshow_manager = SlideshowManager(self)
        self.zoom_manager = ZoomManager(self)

        # Connect viewer-level zoom manager (triggered by shortcuts) to sync
        self.zoom_manager.zoomed.connect(self._sync_zoom)

        # Highlight frame for active pane
        self.highlight = HighlightWidget(self.view_container)

        # Global power management
        self.inhibit_screensaver()

        # Initialize first pane
        self.add_pane(image_list, current_index, initial_tags, initial_rating)
        self.set_active_pane(self.panes[0])

        # Load image
        if restore_config:
            # If restoring a layout, don't auto-fit to screen. Instead, use
            # the saved geometry and state.
            QTimer.singleShot(1000, self.restore_image_list)
            self.populate_filmstrip()
            self.load_and_fit_image(restore_config)
        else:
            self.populate_filmstrip()
            self.load_and_fit_image()

    @property
    def controller(self):
        return self.active_pane.controller if self.active_pane else None

    @property
    def canvas(self):
        return self.active_pane.canvas if self.active_pane else None

    @property
    def scroll_area(self):
        return self.active_pane.scroll_area if self.active_pane else None

    @property
    def movie(self):
        return self.active_pane.movie if self.active_pane else None

    def add_pane(self, image_list, index, initial_tags, initial_rating):
        pane = ImagePane(self, self.cache, image_list, index, initial_tags,
                         initial_rating)
        self.panes.append(pane)
        self.update_grid_layout()
        return pane

    def set_active_pane(self, pane):
        if pane in self.panes:
            # Disconnect signals from previous active pane to avoid double-syncing
            if self.active_pane:
                try:
                    self.active_pane.scrolled.disconnect(self._sync_scroll)
                    self.active_pane.zoom_manager.zoomed.disconnect(self._sync_zoom)
                except RuntimeError:
                    pass  # Signal wasn't connected

            self.active_pane = pane

            # Connect new active pane signals
            pane.scrolled.connect(self._sync_scroll)
            pane.zoom_manager.zoomed.connect(self._sync_zoom)

            self.populate_filmstrip()
            self.sync_filmstrip_selection(pane.controller.index)
            self.update_status_bar()
            self.update_highlight()

    def _sync_scroll(self, x_pct, y_pct):
        if len(self.panes) > 1 and self.panes_linked:
            for pane in self.panes:
                if pane != self.active_pane:
                    pane.set_scroll_relative(x_pct, y_pct)

    def _sync_zoom(self, factor):
        if len(self.panes) > 1 and self.panes_linked:
            for pane in self.panes:
                if pane != self.active_pane:
                    pane.controller.zoom_factor = factor
                    pane.update_view(resize_win=False)

            # Re-apply relative scroll after zoom changes bounds
            # We defer this to the next event loop iteration to ensure
            # that QScrollArea has updated its scrollbar maximums.
            if self.active_pane:
                h_bar = self.active_pane.scroll_area.horizontalScrollBar()
                v_bar = self.active_pane.scroll_area.verticalScrollBar()
                h_max = h_bar.maximum()
                v_max = v_bar.maximum()
                x_pct = h_bar.value() / h_max if h_max > 0 else 0
                y_pct = v_bar.value() / v_max if v_max > 0 else 0

                for pane in self.panes:
                    if pane != self.active_pane:
                        QTimer.singleShot(
                            0, lambda p=pane, x=x_pct,
                            y=y_pct: p.set_scroll_relative(x, y))

    def update_grid_layout(self):
        # Clear layout
        for i in reversed(range(self.grid_layout.count())):
            self.grid_layout.itemAt(i).widget().setParent(None)

        count = len(self.panes)
        if count == 1:
            self.grid_layout.addWidget(self.panes[0], 0, 0)
        elif count == 2:
            self.grid_layout.addWidget(self.panes[0], 0, 0)
            self.grid_layout.addWidget(self.panes[1], 0, 1)
        elif count >= 3:
            # 2x2 grid
            for i, pane in enumerate(self.panes):
                row = i // 2
                col = i % 2
                self.grid_layout.addWidget(pane, row, col)

        self.update_highlight()

    def set_comparison_mode(self, count):
        current_panes = len(self.panes)
        if count == current_panes:
            return

        if count > 1 and self.slideshow_manager.is_running():
            self.slideshow_manager.stop()
            self.update_title()

        if count > current_panes:
            # Add panes
            base_controller = self.active_pane.controller
            start_idx = base_controller.index
            img_list = base_controller.image_list
            for i in range(count - current_panes):
                new_idx = (start_idx + i + 1) % len(img_list)
                pane = self.add_pane(img_list, new_idx, None, 0)  # Metadata will load
                if self.panes_linked and self.active_pane:
                    pane.controller.zoom_factor = \
                        self.active_pane.controller.zoom_factor
                pane.load_and_fit_image()
        else:
            # Remove panes (keep active if possible, else keep first)
            while len(self.panes) > count:
                # Remove the last one
                pane = self.panes.pop()
                pane.cleanup()
                if pane == self.active_pane:
                    self.set_active_pane(self.panes[0])
            self.update_grid_layout()

            # Restore default behavior (auto-resize) if we go back to single view
            if count == 1 and self.active_pane:
                # Allow layout to settle before resizing window to ensure accurate
                # sizing
                QTimer.singleShot(
                    0, lambda: self.active_pane.update_view(resize_win=True))
        self.adjustSize()

    def toggle_link_panes(self):
        """Toggles the synchronized zoom/scroll for comparison mode."""
        self.panes_linked = not self.panes_linked
        if self.panes_linked and self.active_pane:
            self._sync_zoom(self.active_pane.controller.zoom_factor)
        self.update_status_bar()

    def update_highlight(self):
        if len(self.panes) > 1 and self.active_pane:
            self.highlight.show()
            self.highlight.raise_()
            # Adjust geometry to active pane
            self.highlight.setGeometry(self.active_pane.geometry())
        else:
            self.highlight.hide()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update_highlight()

    def reset_inactivity_timer(self):
        """Resets the inactivity timer and restores controls visibility."""
        if self.active_pane and self.active_pane.canvas:
            self.active_pane.canvas._clear_zoom_indicator()

        if self.isFullScreen():
            self.unsetCursor()
            if self.main_win and self.main_win.show_viewer_status_bar:
                self.status_bar_container.show()
            if not self.hide_controls_timer.isActive():
                self.hide_controls_timer.start()
            else:
                self.hide_controls_timer.start()  # Restart triggers full interval

    def hide_controls(self):
        """Hides cursor and status bar in fullscreen mode."""
        if self.isFullScreen():
            self.setCursor(Qt.BlankCursor)
            self.status_bar_container.hide()

    def _setup_shortcuts(self):
        """Initializes the shortcut mapping from the main window or defaults."""
        self.action_to_shortcut = {}
        if self.main_win and self.main_win.viewer_shortcuts:
            # The dictionary from main_win is already prepared with
            # (int, Qt.KeyboardModifiers) keys. The value is (action, desc).
            # We just need the action.
            self.shortcuts = {key: val[0]
                              for key, val in self.main_win.viewer_shortcuts.items()}
            for key, action in self.shortcuts.items():
                self.action_to_shortcut[action] = key
        else:
            # Use defaults from the new constant structure
            self.shortcuts = {}
            for action, (key, mods) in DEFAULT_VIEWER_SHORTCUTS.items():
                key_combo = (int(key), Qt.KeyboardModifiers(mods))
                self.shortcuts[key_combo] = action
                self.action_to_shortcut[action] = key_combo

    def _setup_actions(self):
        """Initializes the action map for executing shortcuts."""
        self._actions = {
            "close": self.close_or_exit_fullscreen,
            "next": self.next_image,
            "prev": self.prev_image,
            "slideshow": self.toggle_slideshow,
            "slideshow_reverse": self.toggle_slideshow_reverse,
            "fullscreen": self.toggle_fullscreen,
            "rename": self.rename_current_image,
            "toggle_faces": self.toggle_faces,
            "toggle_statusbar": self.toggle_status_bar,
            "toggle_filmstrip": self.toggle_filmstrip,
            "flip_horizontal": self.toggle_flip_horizontal,
            "flip_vertical": self.toggle_flip_vertical,
            "detect_faces": self.run_face_detection,
            "detect_pets": self.run_pet_detection,
            "add_face_mode": lambda: self.set_next_region_type("Face"),
            "add_pet_mode": lambda: self.set_next_region_type("Pet"),
            "add_body_mode": lambda: self.set_next_region_type("Body"),
            "add_object_mode": lambda: self.set_next_region_type("Object"),
            "add_landmark_mode": lambda: self.set_next_region_type("Landmark"),
            "detect_bodies": self.run_body_detection,
            "fast_tag": self.show_fast_tag_menu,
            "rotate_right": lambda: self.apply_rotation(90, True),
            "rotate_left": lambda: self.apply_rotation(-90, True),
            "zoom_in": lambda: self.zoom_manager.zoom(1.1),
            "zoom_out": lambda: self.zoom_manager.zoom(0.9),
            "reset_zoom": lambda: self.zoom_manager.zoom(1.0, reset=True),
            "toggle_animation": self.toggle_animation_pause,
            "properties": self.show_properties,
            "toggle_visibility": self.toggle_main_window_visibility,
            "toggle_crop": self.toggle_crop_mode,
            "copy_image": self.copy_image_to_clipboard,
            "copy_path": self.copy_file_path_to_clipboard,
            "copy_dir_path": self.copy_dir_path_to_clipboard,
            "save_crop": self.save_cropped_image,
            "compare_1": lambda: self.set_comparison_mode(1),
            "compare_2": lambda: self.set_comparison_mode(2),
            "compare_4": lambda: self.set_comparison_mode(4),
            "link_panes": self.toggle_link_panes,
        }

    def _execute_action(self, action):
        """Executes the method corresponding to the action name."""
        if self.slideshow_manager.is_running():
            allowed_actions = ('slideshow', 'slideshow_reverse', 'close', 'fullscreen')
            if action not in allowed_actions:
                return

        if action in self._actions:
            self._actions[action]()

    def populate_filmstrip(self):
        """
        Populates the filmstrip widget with thumbnails from the image list.

        Optimized to update the existing list if possible, rather than
        rebuilding it entirely.
        """
        if self.filmstrip.isHidden():
            return

        # --- OPTIMIZATION ---
        # Check if the filmstrip content is already in sync with the controller's list.
        # If so, just update the selection and avoid a full rebuild.
        new_list = self.controller.image_list
        if self.filmstrip.count() == len(new_list):
            is_synced = True
            # This check is fast enough for typical filmstrip sizes.
            for i in range(len(new_list)):
                # Assuming UserRole stores the path
                if self.filmstrip.item(i).data(Qt.UserRole) != new_list[i]:
                    is_synced = False
                    break
            if is_synced:
                self.sync_filmstrip_selection(self.controller.index)
                return
        # --- END OPTIMIZATION ---

        if self.filmstrip_loader and self.filmstrip_loader.isRunning():
            self.filmstrip_loader.stop()

        current_count = self.filmstrip.count()
        fallback_icon = QIcon.fromTheme("image-x-generic")

        # Check if we can perform an incremental update (append)
        can_append = True
        if current_count > len(new_list):
            can_append = False
        else:
            for i in range(current_count):
                item = self.filmstrip.item(i)
                if item.data(Qt.UserRole) != new_list[i]:
                    can_append = False
                    break

        if can_append:
            # Append only new items
            for i in range(current_count, len(new_list)):
                path = new_list[i]
                item = QListWidgetItem(fallback_icon, "")
                item.setData(Qt.UserRole, path)
                self.filmstrip.addItem(item)
        else:
            # Smart rebuild: reuse items to preserve icons/loaded state
            existing_items = {}
            # Remove from end to beginning to avoid index shifting overhead
            for i in range(self.filmstrip.count() - 1, -1, -1):
                item = self.filmstrip.takeItem(i)
                existing_items[item.data(Qt.UserRole)] = item

            for path in new_list:
                if path in existing_items:
                    item = existing_items.pop(path)
                else:
                    item = QListWidgetItem(fallback_icon, "")
                    item.setData(Qt.UserRole, path)
                self.filmstrip.addItem(item)

        # Determine which items need thumbnail loading
        items_to_load = []
        LOADED_ROLE = Qt.UserRole + 1

        for i in range(self.filmstrip.count()):
            item = self.filmstrip.item(i)
            if not item.data(LOADED_ROLE):
                path = item.data(Qt.UserRole)
                items_to_load.append((i, path))

        if items_to_load:
            self.filmstrip_loader = FilmstripLoader(
                self.cache, items_to_load, self.filmstrip.iconSize().width())
            self.filmstrip_loader.set_target_index(self.controller.index)
            self.filmstrip_loader.thumbnail_loaded.connect(
                self._on_filmstrip_thumb_loaded)
            self.filmstrip_loader.start()

        # Defer selection sync to ensure the list widget has updated its layout
        # and bounds, fixing issues where the wrong item seems selected or scrolled to.
        QTimer.singleShot(
            0, lambda: self.sync_filmstrip_selection(self.controller.index))

    @Slot(int, QImage)
    def _on_filmstrip_thumb_loaded(self, index, image):
        """Updates the filmstrip item icon once the thumbnail is loaded."""
        if 0 <= index < self.filmstrip.count():
            item = self.filmstrip.item(index)
            item.setIcon(QIcon(QPixmap.fromImage(image)))
            # Mark as loaded to prevent reloading on subsequent updates
            item.setData(Qt.UserRole + 1, True)

    def sync_filmstrip_selection(self, index):
        """
        Highlights the thumbnail in the filmstrip corresponding to the given index.
        Args:
            index (int): The index of the image to select in the filmstrip.
        """
        if self.filmstrip.count() == 0:
            return
        if 0 <= index < self.filmstrip.count():
            item = self.filmstrip.item(index)
            self.filmstrip.setCurrentItem(item)
            self.filmstrip.scrollToItem(item, QAbstractItemView.PositionAtCenter)

            # Update loader priority if running
            if self.filmstrip_loader and self.filmstrip_loader.isRunning():
                self.filmstrip_loader.set_target_index(index)

    def on_filmstrip_clicked(self, item):
        """
        Slot that handles clicks on a filmstrip item.

        Args:
            item (QListWidgetItem): The clicked list widget item.
        """
        idx = self.filmstrip.row(item)
        if idx != self.controller.index:
            self.controller.index = idx
            self.index_changed.emit(self.controller.index)
            self.load_and_fit_image()

    def restore_image_list(self):
        """Restores the full image list from the main window.

        This is used when a viewer is restored from a layout, ensuring its
        internal image list is synchronized with the main application's list.
        """
        current_path = self.controller.get_current_path()
        image_paths = self.main_win.get_all_image_paths()
        if current_path and current_path in image_paths:
            index = image_paths.index(current_path)
            if index >= 0:
                self.controller.update_list(image_paths, index)

    def get_desktop_resolution(self):
        """
        Determines the resolution of the primary desktop.
        """
        try:
            """
            kwinoutputconfig.json
            """
            return self.screen().availableGeometry().width(), \
                self.screen().availableGeometry().height()
            # We run kscreen-doctor and look for the primary monitor line.
            if FORCE_X11:
                if os.path.exists(KWINOUTPUTCONFIG_PATH):
                    scale = 1
                    primary_monitor = subprocess.check_output("xrandr | grep "
                                                              "' primary' | cut -d' '"
                                                              " -f1",
                                                              shell=True,
                                                              text=True).strip()
                    try:
                        with open(KWINOUTPUTCONFIG_PATH, 'r', encoding='utf-8') as f:
                            data_json = json.load(f)

                        # Find the section where "name" is "outputs"
                        outputs_section = next((item for item in data_json if
                                                item.get("name") == "outputs"), None)

                        if outputs_section:
                            # Iterate over the "data" elements within that section
                            for device in outputs_section.get("data", []):
                                if device.get("connectorName") == primary_monitor:
                                    scale = float(device.get("scale"))
                                    mode = device.get("mode", {})
                                    output = f"{mode.get('width')}x{mode.get('height')}"
                                    break

                    except json.JSONDecodeError:
                        scale = 1
                        output = subprocess.check_output("xrandr | grep ' primary' | "
                                                         "awk '{print $4}' | cut -d'+' "
                                                         "-f1", shell=True, text=True)
                    except Exception:
                        scale = 1
                        output = subprocess.check_output("xrandr | grep ' primary' | "
                                                         "awk '{print $4}' | cut -d'+' "
                                                         "-f1", shell=True, text=True)
                else:
                    scale = 1
                    output = subprocess.check_output("xrandr | grep ' primary' | "
                                                     "awk '{print $4}' | cut -d'+' "
                                                     "-f1", shell=True, text=True)

                width, height = map(int, output.split('x'))
                return width / scale - KSCREEN_DOCTOR_MARGIN, height / scale - \
                    KSCREEN_DOCTOR_MARGIN

            else:
                # This can hang on X11.
                output = subprocess.check_output("kscreen-doctor -o | grep -A 10 "
                                                 "'priority 1' | grep 'Geometry' "
                                                 "| cut -d' ' -f3", shell=True,
                                                 text=True)
                width, height = map(int, output.split('x'))
                return width-KSCREEN_DOCTOR_MARGIN, height-KSCREEN_DOCTOR_MARGIN
        except Exception:
            screen_geo = self.screen().availableGeometry()
            return screen_geo.width(), screen_geo.height()

    def load_and_fit_image_for_pane(self, pane, restore_config=None):
        """
        Logic for loading image into a specific pane.
        """
        success, reloaded = pane.controller.load_image()

        if not success:
            if pane.movie:
                pane.movie.stop()
                pane.movie = None
            pane.canvas.setPixmap(QPixmap())
            if pane == self.active_pane:
                self.update_status_bar()
            return

        path = pane.controller.get_current_path()

        if reloaded:
            if pane.movie:
                pane.movie.stop()
                pane.movie = None
            pane.canvas.crop_rect = QRect()  # Clear crop rect on new image
            if path:
                reader = QImageReader(path)
                if reader.supportsAnimation() and reader.imageCount() > 1:
                    pane.movie = QMovie(path)
                    pane.movie.setCacheMode(QMovie.CacheAll)
                    pane.movie.frameChanged.connect(
                        lambda: self._on_movie_frame_for_pane(pane))
                    pane.movie.start()

        self.reset_inactivity_timer()
        if restore_config:
            pane.controller.zoom_factor = restore_config.get("zoom", 1.0)
            pane.controller.rotation = restore_config.get("rotation", 0)
            pane.controller.show_faces = restore_config.get(
                "show_faces", pane.controller.show_faces)
            self.status_bar_container.setVisible(
                restore_config.get("status_bar_visible", False))
            self.filmstrip.setVisible(
                restore_config.get("filmstrip_visible", False))
            if self.filmstrip.isVisible():
                self.populate_filmstrip()
            pane.update_view(resize_win=False)
            QTimer.singleShot(
                0, lambda: self.restore_scroll_for_pane(pane, restore_config))
        elif reloaded:
            # Calculate zoom to fit the image on the screen
            if self.isFullScreen():
                viewport = pane.scroll_area.viewport()
                available_w = viewport.width()
                available_h = viewport.height()
                should_resize = False
            else:
                if self._first_load:
                    if self.main_win and self.main_win.isVisible():
                        # Get resolution from main windows
                        screen_geo = self.main_win.screen().availableGeometry()
                        screen_width = screen_geo.width()
                        screen_height = screen_geo.height()
                    else:
                        # Tried to guess
                        screen_width, screen_height = self.get_desktop_resolution()
                    if pane == self.panes[0]:
                        self._first_load = False
                else:
                    screen_geo = self.screen().availableGeometry()
                    screen_width = screen_geo.width()
                    screen_height = screen_geo.height()

                # Calculate available screen space for the image itself
                available_w = screen_width * ZOOM_DESKTOP_RATIO
                available_h = screen_height * ZOOM_DESKTOP_RATIO

                filmstrip_position = self.main_win.filmstrip_position \
                    if self.main_win else 'bottom'

                if self.filmstrip.isVisible():
                    if filmstrip_position in ('left', 'right'):
                        available_w -= self.filmstrip.width()
                    else:  # top, bottom
                        available_h -= self.filmstrip.height()

                if self.status_bar_container.isVisible():
                    available_h -= self.status_bar_container.sizeHint().height()
                should_resize = True

            if self.panes_linked and self.active_pane and pane != self.active_pane:
                # Inherit zoom from active pane instead of recalculating
                pane.controller.zoom_factor = self.active_pane.controller.zoom_factor
            else:
                pane.zoom_manager.calculate_initial_zoom(available_w, available_h,
                                                         self.isFullScreen())

            self.update_view(resize_win=should_resize)
        else:
            # Image was reused and no restore config; just refresh the view to ensure
            # metadata/faces are up to date without resetting zoom/pan.
            self.update_view(resize_win=False)

        # Defer sync to ensure layout and scroll area are ready, fixing navigation sync
        if pane == self.active_pane:
            QTimer.singleShot(
                0, lambda: self.sync_filmstrip_selection(pane.controller.index))

    def load_and_fit_image(self, restore_config=None):
        """Proxy method for active pane."""
        if self.active_pane:
            self.active_pane.load_and_fit_image(restore_config)

    @Slot(list)
    def update_image_list(self, new_list):
        """Updates the controller's image list ensuring the current image remains
        selected."""
        current_path = self.controller.get_current_path()

        # If controller is empty but we have a new list, perform initial load logic
        if not current_path and new_list:
            self.controller.update_list(new_list, 0)
            self.load_and_fit_image()
            return

        final_list = list(new_list)
        new_index = -1

        if current_path:
            # 1. Try exact match
            try:
                new_index = final_list.index(current_path)
            except ValueError:
                # 2. Try normpath match (fixes slashes/dots issues)
                norm_current = os.path.normpath(current_path)
                abs_current = os.path.abspath(current_path)
                real_current = os.path.realpath(current_path)
                for i, path in enumerate(final_list):
                    if os.path.normpath(path) == norm_current or \
                       os.path.abspath(path) == abs_current or \
                       os.path.realpath(path) == real_current:
                        new_index = i
                        break

            # 3. If still not found, add it to preserve context
            if new_index == -1:
                if current_path not in final_list:
                    final_list.append(current_path)
                final_list.sort()
                try:
                    new_index = final_list.index(current_path)
                except ValueError:
                    new_index = 0

        if new_index != -1:
            self.controller.update_list(final_list, new_index)
        else:
            # If current path lost, just update list, index defaults/clamps
            self.controller.update_list(final_list)
            # Only reload if the path actually changed effectively
            if self.controller.get_current_path() != current_path:
                self.load_and_fit_image()

    @Slot(int)
    def on_controller_list_updated(self, new_index):
        """Handles the controller's list_updated signal to refresh the UI."""
        self.populate_filmstrip()
        self.update_status_bar(index=new_index)

    def _on_movie_frame_for_pane(self, pane):
        """Updates the view with the current frame from the movie for a specific
        pane."""
        if pane.movie and pane.movie.isValid():
            pane.controller.pixmap_original = pane.movie.currentPixmap()
            pane.update_view(resize_win=False)

    def toggle_animation_pause(self):
        """Pauses or resumes the current animation."""
        if self.movie:
            is_paused = self.movie.state() == QMovie.Paused
            self.movie.setPaused(not is_paused)
            self.update_title()

    def apply_rotation(self, rotation, resize_win=False):
        """
        Applies a rotation to the current image.

        Args:
            rotation (int): The angle in degrees to rotate by.
            resize_win (bool): If True, the window will be resized. Defaults to False.
        """
        if self.controller.pixmap_original.isNull():
            return
        self.controller.rotate(rotation)
        if self.active_pane:
            self.active_pane.update_view(resize_win)

    def update_view_for_pane(self, pane, resize_win=False):
        """
        Updates the canvas with the current pixmap for a specific pane.
        """
        pixmap = pane.controller.get_display_pixmap()
        if pixmap.isNull():
            return

        pane.canvas.setPixmap(pixmap)
        pane.canvas.adjustSize()

        # Disable resizing window in comparison mode (more than 1 pane)
        if len(self.panes) > 1:
            resize_win = False

        if resize_win and APP_CONFIG.get("viewer_auto_resize_window",
                                         VIEWER_AUTO_RESIZE_WINDOW_DEFAULT):
            # Adjust window size to content
            content_w = pane.canvas.width()
            content_h = pane.canvas.height()

            filmstrip_position = self.main_win.filmstrip_position \
                if self.main_win else 'bottom'
            is_vertical_filmstrip = filmstrip_position in ('left', 'right')

            if self.status_bar_container.isVisible():
                content_h += self.status_bar_container.sizeHint().height()

            if self.filmstrip.isVisible():
                if is_vertical_filmstrip:
                    content_w += self.filmstrip.width()
                else:  # top, bottom
                    content_h += self.filmstrip.height()

            target_w = content_w + VIEWER_FORM_MARGIN
            target_h = content_h + VIEWER_FORM_MARGIN

            # Use robust resolution detection for standalone mode to fix sizing issues
            if not self.isVisible() and (
               not self.main_win or not self.main_win.isVisible()):
                sw, sh = self.get_desktop_resolution()
                target_w = min(target_w, sw)
                target_h = min(target_h, sh)
            else:
                screen = self.screen()
                if not self.isVisible() and self.main_win and self.main_win.isVisible():
                    screen = self.main_win.screen()
                avail_geo = screen.availableGeometry()
                target_w = min(target_w, avail_geo.width())
                target_h = min(target_h, avail_geo.height())
            self.resize(target_w, target_h)

        if pane == self.active_pane:
            self.update_title()
            self.update_status_bar()

    def update_view(self, resize_win=False):
        if self.active_pane:
            self.active_pane.update_view(resize_win)

    def rename_current_image(self):
        """
        Opens a dialog to rename the current image file.

        Handles the file system rename operation and updates the internal state.
        """
        if not self.controller.image_list:
            return

        old_path = self.controller.get_current_path()
        if not old_path:
            return

        old_dir = os.path.dirname(old_path)
        old_filename = os.path.basename(old_path)
        base_name, extension = os.path.splitext(old_filename)

        new_base, ok = QInputDialog.getText(
            self, UITexts.RENAME_VIEWER_TITLE,
            UITexts.RENAME_VIEWER_TEXT.format(old_filename),
            QLineEdit.Normal, base_name
        )

        if ok and new_base and new_base != base_name:
            new_base_name, new_extension = os.path.splitext(new_base)
            if new_extension == extension:
                new_filename = new_base
            else:
                new_filename = new_base_name + extension

            new_path = os.path.join(old_dir, new_filename)

            if self.movie:
                self.movie.stop()
                self.movie = None

            if os.path.exists(new_path):
                QMessageBox.warning(self, UITexts.ERROR,
                                    UITexts.RENAME_VIEWER_ERROR_EXISTS.format(
                                        new_filename))
                return

            try:
                os.rename(old_path, new_path)
                self.controller.image_list[self.controller.index] = new_path
                if self.main_win:
                    self.main_win.propagate_rename(old_path, new_path, self)
                self.update_view(resize_win=False)
                self.populate_filmstrip()
                self.update_title()
            except Exception as e:
                QMessageBox.critical(self,
                                     UITexts.RENAME_VIEWER_ERROR_SYSTEM,
                                     UITexts.RENAME_VIEWER_ERROR_TEXT.format(str(e)))

    def toggle_crop_mode(self):
        """Toggles the crop selection mode."""
        if self.active_pane:
            self.active_pane.crop_mode = not self.active_pane.crop_mode
            self.active_pane.canvas.crop_rect = QRect()
            self.active_pane.canvas.update()

            if self.active_pane.crop_mode:
                self.active_pane.canvas.setCursor(Qt.CrossCursor)
                self.sb_info_label.setText(
                    f"{self.sb_info_label.text()}{UITexts.CROP_INDICATOR}")
            else:
                self.active_pane.canvas.setCursor(Qt.ArrowCursor)
                self.update_status_bar()

    def show_crop_menu(self, global_pos):
        """Shows a context menu for the crop selection."""
        menu = QMenu(self)
        save_action = menu.addAction(UITexts.VIEWER_MENU_SAVE_CROP)
        cancel_action = menu.addAction(UITexts.CLOSE)

        res = menu.exec(global_pos)
        if res == save_action:
            self.save_cropped_image()
        elif res == cancel_action:
            if self.active_pane:
                self.active_pane.canvas.crop_rect = QRect()
                self.active_pane.canvas.update()

    def save_cropped_image(self):
        """Saves the area currently selected in crop mode as a new image."""
        if not self.active_pane or not self.active_pane.crop_mode \
           or self.active_pane.canvas.crop_rect.isNull():
            return

        # Get normalized coordinates from the canvas rect
        nx, ny, nw, nh = self.active_pane.canvas.map_to_source(
            self.active_pane.canvas.crop_rect)

        # Use original pixmap to extract high-quality crop
        orig = self.active_pane.controller.pixmap_original
        if orig.isNull():
            return

        W, H = orig.width(), orig.height()

        # Convert normalized center/size back to top-left pixel coordinates
        # nx, ny are center coordinates
        x = int((nx - nw/2) * W)
        y = int((ny - nh/2) * H)
        w = int(nw * W)
        h = int(nh * H)

        # Validate boundaries
        x = max(0, x)
        y = max(0, y)
        w = min(w, W - x)
        h = min(h, H - y)

        if w <= 0 or h <= 0:
            return

        cropped = orig.copy(x, y, w, h)

        default_dir = os.path.dirname(self.controller.get_current_path())
        file_name, _ = QFileDialog.getSaveFileName(
            self, UITexts.SAVE_CROP_TITLE, default_dir, UITexts.SAVE_CROP_FILTER)

        if file_name:
            cropped.save(file_name)
            # Optionally stay in crop mode or exit
            self.active_pane.canvas.crop_rect = QRect()
            self.active_pane.canvas.update()

    def update_title(self):
        """Updates the window title with the current image name."""
        title = f"{VIEWER_LABEL} - {os.path.basename(
            self.controller.get_current_path())}"
        if self.slideshow_manager.is_running():
            title += UITexts.VIEWER_TITLE_SLIDESHOW
        if self.movie and self.movie.state() == QMovie.Paused:
            title += UITexts.VIEWER_TITLE_PAUSED
        self.setWindowTitle(title)

    def update_status_bar(self, metadata=None, index=None):
        """
        Updates the status bar with image dimensions, zoom level, and tags
        read from extended attributes.
        """
        total = len(self.controller.image_list)

        # Use provided index if available, otherwise get from controller
        current_idx = index if index is not None else self.controller.index
        idx = current_idx + 1 if total > 0 else 0
        self.sb_index_label.setText(f"[{idx}/{total}]")

        if self.controller.pixmap_original.isNull():
            self.sb_info_label.setText("")
            self.sb_tags_label.setText("")
            return

        w = self.controller.pixmap_original.width()
        h = self.controller.pixmap_original.height()
        zoom = int(self.controller.zoom_factor * 100)
        info_text = f"{w} x {h} px  |  {zoom}%"

        if len(self.panes) > 1:
            info_text += UITexts.COMPARE_LINKED \
                if self.panes_linked else UITexts.COMPARE_UNLINKED

        if self.controller.show_faces and hasattr(self, '_next_region_type') \
           and self._next_region_type:
            type_text = getattr(UITexts, f"TYPE_{self._next_region_type.upper()}")
            info_text += f"  |  {UITexts.NEXT_AREA.format(type_text)}"

        self.sb_info_label.setText(info_text)

        # Use tags from metadata if provided (priority to avoid race conditions),
        # otherwise fallback to controller's internal state.
        tags_source = self.controller._current_tags
        if metadata and 'tags' in metadata:
            tags_source = metadata['tags']

        display_tags = [t.strip().split('/')[-1]
                        for t in tags_source if t.strip()]
        self.sb_tags_label.setText(", ".join(display_tags))

    @Slot(str, dict)
    def on_metadata_changed(self, path, metadata=None):
        """
        Slot to handle metadata changes from the controller.
        Updates the status bar and notifies the main window to refresh its views.
        """
        if self.controller.get_current_path() == path:
            self.update_status_bar(metadata)
        if self.main_win:
            self.main_win.update_metadata_for_path(path, metadata)

    def copy_image_to_clipboard(self):
        """Copies the currently displayed image to the system clipboard."""
        if self.controller and not self.controller.pixmap_original.isNull():
            QApplication.clipboard().setImage(self.controller.pixmap_original.toImage())

    def copy_file_path_to_clipboard(self):
        """Copies the current image's file path to the system clipboard."""
        if self.controller:
            path = self.controller.get_current_path()
            if path:
                QApplication.clipboard().setText(path)

    def copy_dir_path_to_clipboard(self):
        """Copies the directory path of the current image to the system clipboard."""
        if self.controller:
            path = self.controller.get_current_path()
            if path:
                QApplication.clipboard().setText(os.path.dirname(path))

    def _populate_open_with_menu(self, menu):
        """Populates the 'Open With' submenu."""
        if self.main_win:
            path = self.controller.get_current_path()
            if path:
                self.main_win.populate_open_with_submenu(menu, path)

    def _build_menu_from_data(self, target_menu, items):
        """Builds a menu or submenu from a list of dictionary items."""
        for item in items:
            if item == "separator":
                target_menu.addSeparator()
                continue

            # Handle dynamic submenus that need to be populated by a function
            if "dynamic_submenu" in item:
                icon = QIcon.fromTheme(item.get("icon", ""))
                submenu = target_menu.addMenu(icon, item["text"])
                item["dynamic_submenu"](submenu)
                continue

            action_name = item.get("action")
            display_text = item["text"]

            # Add shortcut string to display text if available
            if action_name and "submenu" not in item and \
               action_name in self.action_to_shortcut:
                key, mods = self.action_to_shortcut[action_name]
                try:
                    mod_val = int(mods)
                except TypeError:
                    mod_val = mods.value
                seq = QKeySequence(mod_val | key)
                shortcut_str = seq.toString(QKeySequence.NativeText)
                if shortcut_str:
                    display_text += f"\t{shortcut_str}"

            icon = QIcon.fromTheme(item.get("icon", ""))

            if "submenu" in item:
                submenu = target_menu.addMenu(icon, item["text"])
                self._build_menu_from_data(submenu, item["submenu"])
            else:
                action = target_menu.addAction(icon, display_text)
                slot = item.get("slot")
                if action_name:
                    action.triggered.connect(
                        lambda checked=False, name=action_name:
                            self._execute_action(name))
                elif slot:
                    action.triggered.connect(slot)

                if item.get("checkable"):
                    action.setCheckable(True)
                    action.setChecked(item.get("checked", False))

                if "enabled" in item:
                    action.setEnabled(item["enabled"])

                if "tooltip" in item:
                    action.setToolTip(item["tooltip"])
                    action.setStatusTip(item["tooltip"])

    def restore_scroll_for_pane(self, pane, config):
        """
        Applies the saved scrollbar positions from a layout configuration.

        Args:
            config (dict): The layout configuration dictionary.
        """
        pane.scroll_area.horizontalScrollBar().setValue(config.get("scroll_x", 0))
        pane.scroll_area.verticalScrollBar().setValue(config.get("scroll_y", 0))

    def get_state(self):
        """
        Captures the complete state of the viewer for saving to a layout.

        Returns:
            dict: A dictionary containing geometry, zoom, rotation, scroll
                  positions, and the current image path.
        """
        geo = self.geometry()
        return {
            "path": self.controller.get_current_path(),
            "index": self.controller.index,
            "geometry": {
                "x": geo.x(), "y": geo.y(), "w": geo.width(), "h": geo.height()
            },
            "zoom": self.controller.zoom_factor,
            "rotation": self.controller.rotation,
            "show_faces": self.controller.show_faces,
            "flip_h": self.controller.flip_h,
            "flip_v": self.controller.flip_v,
            "scroll_x": self.scroll_area.horizontalScrollBar().value()
            if self.scroll_area else 0,
            "scroll_y": self.scroll_area.verticalScrollBar().value()
            if self.scroll_area else 0,
            "status_bar_visible": self.status_bar_container.isVisible(),
            "filmstrip_visible": self.filmstrip.isVisible()
        }

    def first_image(self):
        """Navigates to the first image in the list."""
        self.controller.first()
        self.index_changed.emit(self.controller.index)
        self._is_persistent = False
        self.load_and_fit_image()

    def last_image(self):
        """Navigates to the last image in the list."""
        self.controller.last()
        self.index_changed.emit(self.controller.index)
        self._is_persistent = False
        self.load_and_fit_image()

    def next_image(self):
        """Navigates to the next image in the list (wraps around)."""
        self.controller.next()
        self.index_changed.emit(self.controller.index)
        self._is_persistent = False
        self.load_and_fit_image()

    def prev_image(self):
        """Navigates to the previous image in the list (wraps around)."""
        self.controller.prev()
        self.index_changed.emit(self.controller.index)
        self._is_persistent = False
        self.load_and_fit_image()

    def toggle_slideshow(self):
        """Starts or stops the automatic slideshow timer."""
        if len(self.panes) > 1:
            return
        self.slideshow_manager.toggle(reverse=False)
        self.update_view(resize_win=False)

    def toggle_slideshow_reverse(self):
        """Starts or stops the automatic reverse slideshow timer."""
        if len(self.panes) > 1:
            return
        self.slideshow_manager.toggle(reverse=True)
        self.update_view(resize_win=False)

    def set_slideshow_interval(self):
        """Opens a dialog to set the slideshow interval in seconds."""
        val, ok = QInputDialog.getInt(self,
                                      UITexts.SLIDESHOW_INTERVAL_TITLE,
                                      UITexts.SLIDESHOW_INTERVAL_TEXT,
                                      self.slideshow_manager.get_interval() // 1000,
                                      1, 3600)
        if ok:
            new_interval_ms = val * 1000
            self.slideshow_manager.set_interval(new_interval_ms)

    def toggle_fullscreen(self):
        """Toggles the viewer window between fullscreen and normal states."""
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def close_or_exit_fullscreen(self):
        """Closes the viewer or exits fullscreen if active."""
        if self.isFullScreen():
            self.toggle_fullscreen()
        else:
            self.close()

    def refresh_shortcuts(self):
        """Re-loads shortcuts from the main window configuration."""
        self._setup_shortcuts()

    def _get_clicked_face_for_pane(self, pane, pos):
        """Checks if a click position is inside any face bounding box."""
        for face in pane.controller.faces:
            rect = pane.canvas.map_from_source(face)
            if rect.contains(pos):
                return face
        return None

    def _show_face_context_menu(self, event):
        """
        Shows a context menu for a clicked face region.
        Returns True if a menu was shown, False otherwise.
        """
        if not self.controller.show_faces:
            return False

        pos = self.canvas.mapFromGlobal(event.globalPos()) if self.canvas else QPoint()
        clicked_face = self.active_pane._get_clicked_face(pos) \
            if self.active_pane else None

        if not clicked_face:
            return False

        menu = QMenu(self)
        action_del = menu.addAction(UITexts.DELETE_AREA_TITLE)
        action_ren = menu.addAction(UITexts.RENAME_AREA_TITLE)
        res = menu.exec(event.globalPos())

        if res == action_del:
            face_name = clicked_face.get('name', '')
            self.controller.remove_face(clicked_face)
            if face_name:
                has_other = any(f.get('name') == face_name
                                for f in self.controller.faces)
                if not has_other:
                    self.controller.toggle_tag(face_name, False)
            if self.canvas:
                self.canvas.update()
        elif res == action_ren:
            self.rename_face(clicked_face)
        return True

    def rename_face(self, face_to_rename):
        """Opens a dialog to rename a specific face/area."""
        if not face_to_rename:
            return

        region_type = face_to_rename.get('type', 'Face')
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
        current_name = face_to_rename.get('name', '')

        new_full_tag, updated_history, ok = FaceNameDialog.get_name(
            self, history, current_name, main_win=self.main_win,
            region_type=region_type, title=UITexts.RENAME_AREA_TITLE)

        if ok and new_full_tag and new_full_tag != current_name:
            # Remove old tag if it's not used by other faces
            if current_name:
                has_other = any(f.get('name') == current_name
                                for f in self.controller.faces
                                if f is not face_to_rename)
                if not has_other:
                    self.controller.toggle_tag(current_name, False)

            # Update face and history
            face_to_rename['name'] = new_full_tag
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

            # Save changes and add new tag
            try:
                self.controller.save_faces()
                self.controller.toggle_tag(new_full_tag, True)
            except Exception as e:
                QMessageBox.critical(self, UITexts.ERROR, str(e))
            if self.canvas:
                self.canvas.update()

    def toggle_main_window_visibility(self):
        """Toggles the visibility of the main window."""
        if self.main_win:
            self.main_win.toggle_visibility()

    def show_properties(self):
        """Shows the properties dialog for the current image."""
        path = self.controller.get_current_path()
        if path:
            tags = self.controller._current_tags
            rating = self.controller._current_rating
            dlg = PropertiesDialog(
                path, initial_tags=tags, initial_rating=rating, parent=self)
            dlg.exec()

    def _create_viewer_context_menu(self):
        """Builds and returns the general viewer context menu."""
        menu = QMenu(self)

        menu_structure = []
        if self.slideshow_manager.is_running():
            is_fwd = self.slideshow_manager.is_forward()
            is_rev = self.slideshow_manager.is_reverse()
            menu_structure = [
                {"text": UITexts.VIEWER_MENU_STOP_SLIDESHOW if is_fwd
                 else UITexts.VIEWER_MENU_START_SLIDESHOW, "action": "slideshow",
                 "icon": "media-playback-stop" if is_fwd else "media-playback-start"},
                {"text": UITexts.VIEWER_MENU_STOP_REVERSE_SLIDESHOW if is_rev
                 else UITexts.VIEWER_MENU_START_REVERSE_SLIDESHOW,
                 "action": "slideshow_reverse",
                 "icon": "media-playback-stop" if is_rev else "media-seek-backward"},
                {"text": UITexts.VIEWER_MENU_SET_INTERVAL,
                 "slot": self.set_slideshow_interval, "icon": "preferences-system-time"}
            ]

        else:
            # Build the normal menu structure
            is_fwd = self.slideshow_manager.is_forward()
            is_rev = self.slideshow_manager.is_reverse()

            slideshow_submenu = [
                {"text": UITexts.VIEWER_MENU_STOP_SLIDESHOW if is_fwd
                 else UITexts.VIEWER_MENU_START_SLIDESHOW, "action": "slideshow",
                 "icon": "media-playback-stop" if is_fwd else "media-playback-start"},
                {"text": UITexts.VIEWER_MENU_STOP_REVERSE_SLIDESHOW if is_rev
                 else UITexts.VIEWER_MENU_START_REVERSE_SLIDESHOW,
                 "action": "slideshow_reverse",
                 "icon": "media-playback-stop" if is_rev else "media-seek-backward"},
                {"text": UITexts.VIEWER_MENU_SET_INTERVAL,
                 "slot": self.set_slideshow_interval, "icon": "preferences-system-time"}
            ]

            menu_structure = [
                {"text": UITexts.CONTEXT_MENU_OPEN, "icon": "document-open",
                 "dynamic_submenu": self._populate_open_with_menu},
                "separator",
                {"text": UITexts.VIEWER_MENU_TAGS,
                 "action": "fast_tag", "icon": "document-properties"},
                {"text": UITexts.VIEWER_MENU_DETECT_AREAS,
                 "icon": "edit-image-face-recognize", "submenu": [
                    {"text": UITexts.VIEWER_MENU_DETECT_FACES,
                     "action": "detect_faces",
                     "enabled": bool(AVAILABLE_FACE_ENGINES),
                     "tooltip": "" if AVAILABLE_FACE_ENGINES else UITexts.NO_FACE_LIBS},
                    {"text": UITexts.VIEWER_MENU_DETECT_PETS,
                     "action": "detect_pets",
                     "enabled": bool(AVAILABLE_PET_ENGINES),
                     "tooltip": "" if AVAILABLE_PET_ENGINES else UITexts.NO_FACE_LIBS},
                    "separator",
                    {
                        "text": UITexts.VIEWER_MENU_ADD_FACE,
                        "action": "add_face_mode",
                        "icon": "list-add"
                    },
                    {
                        "text": UITexts.VIEWER_MENU_ADD_PET,
                        "action": "add_pet_mode",
                        "icon": "list-add"
                    },
                    {
                        "text": UITexts.VIEWER_MENU_ADD_BODY,
                        "action": "add_body_mode",
                        "icon": "list-add"
                    },
                    {
                        "text": UITexts.VIEWER_MENU_ADD_OBJECT,
                        "action": "add_object_mode",
                        "icon": "list-add"
                    },
                    {
                        "text": UITexts.VIEWER_MENU_ADD_LANDMARK,
                        "action": "add_landmark_mode",
                        "icon": "list-add"
                    },
                    ]},
                "separator",
                {"text": UITexts.VIEWER_MENU_MANIPULATE,
                 "icon": "transform", "submenu": [
                    {"text": UITexts.VIEWER_MENU_ROTATE,
                     "icon": "transform-rotate", "submenu": [
                        {"text": UITexts.VIEWER_MENU_ROTATE_LEFT,
                         "action": "rotate_left", "icon": "object-rotate-left"},
                        {"text": UITexts.VIEWER_MENU_ROTATE_RIGHT,
                         "action": "rotate_right", "icon": "object-rotate-right"}
                        ]},
                    {"text": UITexts.VIEWER_MENU_FLIP,
                     "icon": "transform-flip", "submenu": [
                        {"text": UITexts.VIEWER_MENU_FLIP_H,
                         "action": "flip_horizontal", "icon": "object-flip-horizontal"},
                        {"text": UITexts.VIEWER_MENU_FLIP_V,
                         "action": "flip_vertical", "icon": "object-flip-vertical"}
                        ]}
                    ]},
                {"text": UITexts.VIEWER_MENU_ZOOM, "icon": "zoom", "submenu": [
                    {"text": UITexts.VIEWER_MENU_ZOOM_IN,
                     "action": "zoom_in", "icon": "zoom-in"},
                    {"text": UITexts.VIEWER_MENU_ZOOM_OUT,
                     "action": "zoom_out", "icon": "zoom-out"},
                    "separator",
                    {"text": UITexts.VIEWER_MENU_FIT_SCREEN,
                     "slot": self.zoom_manager.toggle_fit_to_screen,
                     "icon": "zoom-fit-best"},
                ]},
                "separator",
                {"text": UITexts.VIEWER_MENU_RENAME,
                 "action": "rename", "icon": "edit-rename"},
                {"text": UITexts.CONTEXT_MENU_CLIPBOARD,
                 "icon": "edit-copy", "submenu": [
                    {"text": UITexts.VIEWER_MENU_COPY_IMAGE,
                     "action": "copy_image", "icon": "image-x-generic"},
                    {"text": UITexts.VIEWER_MENU_COPY_PATH,
                     "action": "copy_path", "icon": "document-properties"},
                    {"text": UITexts.CONTEXT_MENU_COPY_DIR,
                     "action": "copy_dir_path", "icon": "folder"},
                 ]},
                {"text": UITexts.VIEWER_MENU_CROP,
                 "action": "toggle_crop", "icon": "transform-crop", "checkable": True,
                 "checked": self.crop_mode},
                "separator",
                {"text": UITexts.VIEWER_MENU_COMPARE, "icon": "view-grid", "submenu": [
                    {"text": UITexts.VIEWER_MENU_COMPARE_1,
                     "action": "compare_1", "icon": "view-restore"},
                    {"text": UITexts.VIEWER_MENU_COMPARE_2,
                     "action": "compare_2", "icon": "view-split-left-right"},
                    {"text": UITexts.VIEWER_MENU_COMPARE_4,
                     "action": "compare_4", "icon": "view-grid"},
                    "separator",
                    {"text": UITexts.VIEWER_MENU_LINK_PANES,
                     "action": "link_panes", "icon": "object-link",
                     "checkable": True, "checked": self.panes_linked}
                ]},
                "separator",
            ]

            if self.movie:
                is_paused = self.movie.state() == QMovie.Paused
                pause_text = UITexts.VIEWER_MENU_RESUME_ANIMATION \
                    if is_paused else UITexts.VIEWER_MENU_PAUSE_ANIMATION
                pause_icon = "media-playback-start" \
                    if is_paused else "media-playback-pause"
                menu_structure.append(
                    {"text": pause_text, "action": "toggle_animation",
                     "icon": pause_icon})

            menu_structure.extend([
                {"text": UITexts.VIEWER_MENU_SLIDESHOW,
                 "icon": "view-presentation", "submenu": slideshow_submenu},
                "separator",
                {"text": UITexts.SHOW_FACES,
                 "action": "toggle_faces", "icon": "edit-image-face-show",
                 "checkable": True,
                 "checked": self.controller.show_faces if self.controller else False},
                {"text": UITexts.VIEWER_MENU_SHOW_FILMSTRIP,
                 "action": "toggle_filmstrip", "icon": "view-filmstrip",
                 "checkable": True, "checked": self.filmstrip.isVisible()},
                {"text": UITexts.VIEWER_MENU_SHOW_STATUSBAR,
                 "action": "toggle_statusbar", "icon": "view-bottom-panel",
                 "checkable": True, "checked": self.status_bar_container.isVisible()},
                "separator",
                {"text": UITexts.VIEWER_MENU_EXIT_FULLSCREEN
                 if self.isFullScreen() else UITexts.VIEWER_MENU_ENTER_FULLSCREEN,
                 "action": "fullscreen", "icon": "view-fullscreen"
                 if not self.isFullScreen() else "view-restore"},
                "separator",
                {"text": UITexts.MENU_TOGGLE_MAIN_WINDOW,
                 "action": "toggle_visibility", "icon": "view-restore"},
                "separator",
                {"text": UITexts.CONTEXT_MENU_PROPERTIES,
                 "action": "properties", "icon": "document-properties"}
            ])

        self._build_menu_from_data(menu, menu_structure)

        return menu

    def _show_viewer_context_menu(self, event):
        """Creates and shows the general viewer context menu."""
        menu = self._create_viewer_context_menu()
        menu.exec(event.globalPos())

    def _calculate_iou(self, boxA, boxB):
        """Calculates Intersection over Union for two face boxes."""
        # Convert from center-based (x,y,w,h) to corner-based (x1,y1,x2,y2)
        boxA_x1 = boxA['x'] - boxA['w'] / 2
        boxA_y1 = boxA['y'] - boxA['h'] / 2
        boxA_x2 = boxA['x'] + boxA['w'] / 2
        boxA_y2 = boxA['y'] + boxA['h'] / 2

        boxB_x1 = boxB['x'] - boxB['w'] / 2
        boxB_y1 = boxB['y'] - boxB['h'] / 2
        boxB_x2 = boxB['x'] + boxB['w'] / 2
        boxB_y2 = boxB['y'] + boxB['h'] / 2

        # Determine the coordinates of the intersection rectangle
        xA = max(boxA_x1, boxB_x1)
        yA = max(boxA_y1, boxB_y1)
        xB = min(boxA_x2, boxB_x2)
        yB = min(boxA_y2, boxB_y2)

        # Compute the area of intersection
        interArea = max(0, xB - xA) * max(0, yB - yA)

        # Compute the area of both bounding boxes
        boxAArea = boxA['w'] * boxA['h']
        boxBArea = boxB['w'] * boxB['h']

        # Compute the intersection over union
        denominator = float(boxAArea + boxBArea - interArea)
        iou = interArea / denominator if denominator > 0 else 0

        return iou

    def toggle_flip_horizontal(self):
        """Horizontally flips the image."""
        self.controller.toggle_flip_h()
        self.update_view(resize_win=False)

    def toggle_flip_vertical(self):
        """Vertically flips the image."""
        self.controller.toggle_flip_v()
        self.update_view(resize_win=False)

    def set_next_region_type(self, region_type):
        self._next_region_type = region_type
        self.update_status_bar()
        if not self.controller.show_faces:
            self.toggle_faces()

    def contextMenuEvent(self, event):
        """Shows a context menu with viewer options.

        If a face region is clicked while face display is active, it shows
        a context menu for that face. Otherwise, it shows the general
        viewer context menu.

        Args:
            event (QContextMenuEvent): The context menu event.
        """
        if self.active_pane and self.active_pane.crop_mode \
           and not self.active_pane.canvas.crop_rect.isNull():
            pos = self.active_pane.canvas.mapFromGlobal(event.globalPos())
            if self.active_pane.canvas.crop_rect.contains(pos):
                self.show_crop_menu(event.globalPos())
                return

        if self._show_face_context_menu(event):
            return  # Face menu was shown and handled

        # If no face was clicked or faces are not shown, show the general menu
        self._show_viewer_context_menu(event)

    def run_face_detection(self):
        """Runs face detection on the current image."""
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            new_faces = self.controller.detect_faces()
        finally:
            QApplication.restoreOverrideCursor()

        if not new_faces:
            return

        IOU_THRESHOLD = 0.7  # If IoU is > 70%, consider it the same face
        added_count = 0
        for new_face in new_faces:
            is_duplicate = False
            for existing_face in self.controller.faces:
                iou = self._calculate_iou(new_face, existing_face)
                if iou > IOU_THRESHOLD:
                    is_duplicate = True
                    break

            if is_duplicate:
                continue

            if not self.controller.show_faces:
                self.toggle_faces()

            self.controller.faces.append(new_face)
            if self.canvas:
                self.canvas.update()

            w = self.canvas.width() if self.canvas else 0
            h = self.canvas.height() if self.canvas else 0
            if self.scroll_area:
                self.scroll_area.ensureVisible(int(new_face.get('x', 0) * w),
                                               int(new_face.get('y', 0) * h), 50, 50)
            QApplication.processEvents()

            history = self.main_win.face_names_history if self.main_win else []
            suggested = history[0] if history and APP_CONFIG.get(
                "face_use_last_name", False) else ""
            full_tag, updated_history, ok = FaceNameDialog.get_name(
                self, history, current_name=suggested, main_win=self.main_win)

            if ok and full_tag:
                new_face['name'] = full_tag
                self.controller.toggle_tag(full_tag, True)
                if self.main_win:
                    self.main_win.face_names_history = updated_history
                added_count += 1
            else:
                # If user cancels, remove the face that was temporarily added
                self.controller.faces.pop()
                if self.canvas:
                    self.canvas.update()

        if added_count > 0:
            try:
                self.controller.save_faces()
            except Exception as e:
                QMessageBox.critical(self, UITexts.ERROR, str(e))

    def run_pet_detection(self):
        """Runs pet detection on the current image."""
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            new_pets = self.controller.detect_pets()
        finally:
            QApplication.restoreOverrideCursor()

        if not new_pets:
            return

        IOU_THRESHOLD = 0.7
        added_count = 0
        for new_pet in new_pets:
            is_duplicate = False
            for existing_face in self.controller.faces:
                iou = self._calculate_iou(new_pet, existing_face)
                if iou > IOU_THRESHOLD:
                    is_duplicate = True
                    break

            if is_duplicate:
                continue

            if not self.controller.show_faces:
                self.toggle_faces()

            self.controller.faces.append(new_pet)
            if self.canvas:
                self.canvas.update()

            w = self.canvas.width() if self.canvas else 0
            h = self.canvas.height() if self.canvas else 0
            if self.scroll_area:
                self.scroll_area.ensureVisible(int(new_pet.get('x', 0) * w),
                                               int(new_pet.get('y', 0) * h), 50, 50)
            QApplication.processEvents()

            history = self.main_win.pet_names_history if self.main_win else []
            suggested = history[0] if history and APP_CONFIG.get(
                "pet_use_last_name", False) else ""
            full_tag, updated_history, ok = FaceNameDialog.get_name(
                self, history, current_name=suggested, main_win=self.main_win,
                region_type="Pet")

            if ok and full_tag:
                new_pet['name'] = full_tag
                self.controller.toggle_tag(full_tag, True)
                if self.main_win:
                    self.main_win.pet_names_history = updated_history
                added_count += 1
            else:
                self.controller.faces.pop()
                if self.canvas:
                    self.canvas.update()

        if added_count > 0:
            try:
                self.controller.save_faces()
            except Exception as e:
                QMessageBox.critical(self, UITexts.ERROR, str(e))

    def run_body_detection(self):
        """Runs body detection on the current image."""
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            new_bodies = self.controller.detect_bodies()
        finally:
            QApplication.restoreOverrideCursor()

        if not new_bodies:
            return

        IOU_THRESHOLD = 0.7
        added_count = 0
        for new_body in new_bodies:
            is_duplicate = False
            for existing_face in self.controller.faces:
                iou = self._calculate_iou(new_body, existing_face)
                if iou > IOU_THRESHOLD:
                    is_duplicate = True
                    break

            if is_duplicate:
                continue

            if not self.controller.show_faces:
                self.toggle_faces()

            self.controller.faces.append(new_body)
            if self.canvas:
                self.canvas.update()

            w = self.canvas.width() if self.canvas else 0
            h = self.canvas.height() if self.canvas else 0
            if self.scroll_area:
                self.scroll_area.ensureVisible(int(new_body.get('x', 0) * w),
                                               int(new_body.get('y', 0) * h), 50, 50)
            QApplication.processEvents()

            # For bodies, we typically don't ask for a name immediately unless desired
            # Or we can treat it like pets/faces and ask. Let's ask.
            history = self.main_win.body_names_history if self.main_win else []
            suggested = history[0] if history and APP_CONFIG.get(
                "body_use_last_name", False) else ""
            full_tag, updated_history, ok = FaceNameDialog.get_name(
                self, history, current_name=suggested, main_win=self.main_win,
                region_type="Body")

            if ok and full_tag:
                new_body['name'] = full_tag
                self.controller.toggle_tag(full_tag, True)
                if self.main_win:
                    self.main_win.body_names_history = updated_history
                added_count += 1
            else:
                self.controller.faces.pop()
                if self.canvas:
                    self.canvas.update()

        if added_count > 0:
            try:
                self.controller.save_faces()
            except Exception as e:
                QMessageBox.critical(self, UITexts.ERROR, str(e))

    def toggle_filmstrip(self):
        """Shows or hides the filmstrip widget."""
        visible = not self.filmstrip.isVisible()
        self.filmstrip.setVisible(visible)
        if visible:
            self.populate_filmstrip()
        if self.main_win:
            self.main_win.show_filmstrip = visible
            self.main_win.save_config()

    def toggle_status_bar(self):
        """Shows or hides the status bar widget."""
        visible = not self.status_bar_container.isVisible()
        self.status_bar_container.setVisible(visible)
        if self.main_win:
            self.main_win.show_viewer_status_bar = visible
            self.main_win.save_config()

    def toggle_faces(self):
        """Toggles the display of face regions."""
        for pane in self.panes:
            pane.controller.show_faces = not pane.controller.show_faces
            pane.canvas.update()

        if self.main_win:
            if self.active_pane:
                self.main_win.show_faces = self.active_pane.controller.show_faces
            self.main_win.save_config()
        self.update_status_bar()

    def show_fast_tag_menu(self):
        """Shows a context menu for quickly adding/removing tags."""
        self.fast_tag_manager.show_menu()

    def changeEvent(self, event):
        """
        Handles window state changes to sync with the main view on activation.
        """
        if event.type() == QEvent.ActivationChange and self.isActiveWindow():
            self.activated.emit()
        elif event.type() == QEvent.WindowStateChange:
            if self.windowState() & Qt.WindowFullScreen:
                self.reset_inactivity_timer()
            else:
                self.hide_controls_timer.stop()
                self.unsetCursor()
                if self.main_win:
                    self.status_bar_container.setVisible(
                        self.main_win.show_viewer_status_bar)
        super().changeEvent(event)

    def wheelEvent(self, event):
        """
        Handles mouse wheel events for zooming (with Ctrl) or navigation.

        Args:
            event (QWheelEvent): The mouse wheel event.
        """
        self.reset_inactivity_timer()
        if event.modifiers() & Qt.ControlModifier:
            # Zoom with Ctrl + Wheel
            focus_pos = event.position().toPoint()
            if event.angleDelta().y() > 0:
                self.zoom_manager.zoom(1.1, focus_point=focus_pos)
            else:
                self.zoom_manager.zoom(0.9, focus_point=focus_pos)
        else:
            # Navigate next/previous based on configurable speed
            speed = APP_CONFIG.get("viewer_wheel_speed", VIEWER_WHEEL_SPEED_DEFAULT)
            # A standard tick is 120. We define a threshold based on speed.
            # Speed 1 (slowest) requires a full 120 delta.
            # Speed 10 (fastest) requires 120/10 = 12 delta.
            # Still too fast so speed / 2.
            threshold = 120 / speed * 2

            self._wheel_scroll_accumulator += event.angleDelta().y()

            # Process all accumulated delta
            while abs(self._wheel_scroll_accumulator) >= threshold:
                if self._wheel_scroll_accumulator < 0:
                    # Scrolled down -> next image
                    self.next_image()
                    self._wheel_scroll_accumulator += threshold
                else:
                    # Scrolled up -> previous image
                    self.prev_image()
                    self._wheel_scroll_accumulator -= threshold

    # --- Keyboard Handling ---
    def keyPressEvent(self, event):
        """
        Handles key press events for navigation and other shortcuts.

        Args:
            event (QKeyEvent): The key press event.
        """
        self.reset_inactivity_timer()
        key_code = event.key()
        modifiers = event.modifiers() & (Qt.ShiftModifier | Qt.ControlModifier |
                                         Qt.AltModifier | Qt.MetaModifier)

        key_combo = (key_code, modifiers)
        action = self.shortcuts.get(key_combo)

        if action:
            self._execute_action(action)
            event.accept()
        else:
            super().keyPressEvent(event)

    # --- Delete Management ---
    def refresh_after_delete(self, new_list, deleted_idx=-1):
        """
        Refreshes the viewer after an image has been deleted from the main window.

        Args:
            new_list (list): The updated list of image paths.
            deleted_idx (int): The index of the deleted image in the old list.
        """
        self.controller.update_list(new_list)
        if not self.controller.image_list:
            self.close()
            return

        if 0 <= deleted_idx < self.filmstrip.count():
            item = self.filmstrip.takeItem(deleted_idx)
            del item  # Ensure the QListWidgetItem is deleted
        else:
            self.populate_filmstrip()  # Fallback to full rebuild

        # Reload image in case the current one was deleted or index changed
        self.load_and_fit_image()

        # Notify the main window that the image (and possibly index) has changed
        # so it can update its selection.
        self.index_changed.emit(self.controller.index)

    # --- Window Close ---
    def closeEvent(self, event):
        """
        Handles the window close event.

        Ensures the screensaver is uninhibited and checks if the application
        should exit if it's the last open viewer.

        Args:
            event (QCloseEvent): The close event.
        """
        for pane in self.panes:
            pane.cleanup()

        self.slideshow_manager.stop()
        if self.filmstrip_loader and self.filmstrip_loader.isRunning():
            self.filmstrip_loader.stop()
        self.uninhibit_screensaver()
        # If we close the last viewer and the main window is hidden, quit.
        if self.main_win and not self.main_win.isVisible():
            # Check how many viewers are left
            viewers = [w for w in QApplication.topLevelWidgets() if isinstance(
                w, ImageViewer) and w.isVisible()]
            # 'viewers' includes 'self' as it's not fully destroyed yet
            if len(viewers) <= 1:
                self.main_win.perform_shutdown()
                QApplication.quit()

    def set_window_icon(self):
        """Sets the window icon from the current theme."""
        icon = QIcon.fromTheme(ICON_THEME_VIEWER,
                               QIcon.fromTheme(ICON_THEME_VIEWER_FALLBACK))
        self.setWindowIcon(icon)

    # --- DBus Inhibition ---
    def inhibit_screensaver(self):
        """
        Prevents the screensaver or power management from activating.

        Uses DBus to send an inhibit request to the session's screen saver
        service, which is common on Linux desktops.
        """
        PowerManager.inhibit()

    def uninhibit_screensaver(self):
        """
        Releases the screensaver inhibit lock.

        Uses DBus to uninhibit the screensaver using the cookie obtained
        during the inhibit call.
        """
        PowerManager.uninhibit()
