"""
Image Controller Module for Bagheera.

This module provides the core logic for managing image state, including navigation,
loading, transformations (zoom, rotation), and look-ahead preloading for a smooth
user experience.

Classes:
    ImagePreloader: A QThread worker that loads the next image in the background.
    ImageController: A QObject that manages the image list, current state, and
                     interacts with the ImagePreloader.
"""
import os
import logging
import math
from PySide6.QtCore import QThread, Signal, QMutex, QWaitCondition, QObject, Qt, QSize
from PySide6.QtGui import QImage, QImageReader, QPixmap, QTransform
from .xmpmanager import XmpManager
from .constants import (
    APP_CONFIG, AVAILABLE_FACE_ENGINES, AVAILABLE_PET_ENGINES, AVAILABLE_BODY_ENGINES,
    MEDIAPIPE_FACE_MODEL_PATH, MEDIAPIPE_FACE_MODEL_URL, MEDIAPIPE_OBJECT_MODEL_PATH,
    MEDIAPIPE_OBJECT_MODEL_URL, RATING_XATTR_NAME, XATTR_NAME, UITexts
)
from .metadatamanager import XattrManager, load_common_metadata

logger = logging.getLogger(__name__)


class ImagePreloader(QThread):
    """
    A worker thread to preload the next image in the sequence.

    This class runs in the background to load an image before it is needed,
    reducing perceived loading times during navigation.

    Signals:
        image_ready(int, str, QImage): Emitted when an image has been successfully
        preloaded, providing its index, path, and the QImage.
    """
    image_ready = Signal(int, str, QImage, list, int)  # Now emits tags and rating

    def __init__(self):
        """Initializes the preloader thread."""
        super().__init__()
        self.setObjectName("ImagePreloaderThread")
        self.path = None
        self.index = -1
        self.mutex = QMutex()
        self.condition = QWaitCondition()
        self._stop_flag = False
        self.current_processing_path = None

    def request_load(self, path, index):
        """
        Requests the thread to load a specific image.

        Args:
            path (str): The file path of the image to load.
            index (int): The index of the image in the main list.
        """
        self.mutex.lock()
        if self.current_processing_path == path:
            self.path = None
            self.mutex.unlock()
            return

        if self.path == path:
            self.index = index
            self.mutex.unlock()
            return

        self.path = path
        self.index = index
        self.condition.wakeOne()
        self.mutex.unlock()

    def stop(self):
        """Stops the worker thread gracefully."""
        self.mutex.lock()
        self._stop_flag = True
        self.condition.wakeOne()
        self.mutex.unlock()
        self.wait()

    def run(self):
        """
        The main execution loop for the thread.

        Waits for a load request, reads the image file, and emits the
        `image_ready` signal upon success.
        """
        while True:
            self.mutex.lock()
            self.current_processing_path = None
            while self.path is None and not self._stop_flag:
                self.condition.wait(self.mutex)

            if self._stop_flag:
                self.mutex.unlock()
                return

            path = self.path
            idx = self.index
            self.path = None
            self.current_processing_path = path
            self.mutex.unlock()

            # Ensure file exists before trying to read
            if path and os.path.exists(path):
                try:
                    reader = QImageReader(path)
                    reader.setAutoTransform(True)
                    img = reader.read()
                    if not img.isNull():
                        # Load tags and rating here to avoid re-reading in main thread
                        res = load_common_metadata(path)
                        self.image_ready.emit(idx, path, img, res.tags, res.rating)
                except Exception as e:
                    logger.warning(f"ImagePreloader failed to load {path}: {e}")


class ImageController(QObject):
    """
    Manages image list navigation, state, and loading logic.

    This controller is the central point for handling the currently displayed
    image. It manages the list of images, the current index, zoom/rotation/flip
    state, and uses an `ImagePreloader` to implement a look-ahead cache for
    the next image to provide a smoother user experience.
    """
    metadata_changed = Signal(str, dict)
    list_updated = Signal(int)

    def __init__(self, image_list, current_index, initial_tags=None, initial_rating=0):
        """
        Initializes the ImageController.
        """
        super().__init__()
        self.image_list = image_list
        self.index = current_index
        self.zoom_factor = 1.0
        self.rotation = 0
        self.flip_h = False
        self.flip_v = False
        self.pixmap_original = QPixmap()
        self.faces = []
        self._current_tags = initial_tags if initial_tags is not None else []
        self._current_rating = initial_rating
        self._current_metadata_path = None
        self._loaded_path = None
        self.show_faces = False

        # Preloading
        self.preloader = ImagePreloader()
        self.preloader.image_ready.connect(self._handle_preloaded_image)
        self.preloader.start()
        self._cached_next_image = None
        self._cached_next_index = -1

    def cleanup(self):
        """Stops the background preloader thread."""
        self.preloader.stop()
        self._current_metadata_path = None
        self._loaded_path = None
        self._current_tags = []
        self._current_rating = 0
        self._cached_next_image = None
        self._cached_next_index = -1

    def _trigger_preload(self):
        """Identifies the next image in the list and asks the preloader to load it."""
        if not self.image_list:
            return
        next_idx = (self.index + 1) % len(self.image_list)
        if next_idx == self.index:
            return

        if next_idx != self._cached_next_index:
            self.preloader.request_load(self.image_list[next_idx], next_idx)

    def _handle_preloaded_image(self, index, path, image, tags, rating):
        """Slot to receive and cache the image and its metadata from the preloader.

        Args:
            index (int): The index of the preloaded image.
            path (str): The file path of the preloaded image.
            image (QImage): The preloaded image data.
            tags (list): Preloaded tags for the image.
            rating (int): Preloaded rating for the image.
        """
        # The signal now emits (index, path, QImage, tags, rating)
        # Verify if the loaded path still corresponds to the next index
        if self.image_list:
            next_idx = (self.index + 1) % len(self.image_list)
            if self.image_list[next_idx] == path:
                self._cached_next_index = next_idx
                self._cached_next_image = image

                # Store preloaded metadata
                self._cached_next_tags = tags
                self._cached_next_rating = rating

    def get_current_path(self):
        """
        Gets the file path of the current image.

        Returns:
            str or None: The path of the current image, or None if the list is empty.
        """
        if 0 <= self.index < len(self.image_list):
            return self.image_list[self.index]
        return None

    def load_image(self):
        """
        Loads the current image into the controller's main pixmap.
        """
        path = self.get_current_path()

        # Optimization: Check if image is already loaded
        if path and self._loaded_path == path and not self.pixmap_original.isNull():
            # Ensure metadata is consistent with current path
            if self._current_metadata_path != path:
                res = load_common_metadata(path)
                self._current_tags, self._current_rating = res.tags, res.rating
                self._current_metadata_path = path

            self._trigger_preload()
            return True, False

        self.pixmap_original = QPixmap()
        self._loaded_path = None
        self.rotation = 0
        self.flip_h = False
        self.flip_v = False
        self.faces = []

        if not path:
            return False, False

        # Check cache
        if self.index == self._cached_next_index and self._cached_next_image:
            self.pixmap_original = QPixmap.fromImage(self._cached_next_image)
            # Clear cache to free memory as we have consumed the image
            self._current_tags = self._cached_next_tags
            self._current_rating = self._cached_next_rating
            self._current_metadata_path = path
            self._cached_next_image = None
            self._cached_next_index = -1
            self._cached_next_tags = None
            self._cached_next_rating = None
        else:
            reader = QImageReader(path)  # This is a disk read
            reader.setAutoTransform(True)
            image = reader.read()
            if image.isNull():
                self._trigger_preload()
                return False, False
            self.pixmap_original = QPixmap.fromImage(image)

            # Load tags and rating if not already set for this path
            if self._current_metadata_path != path:
                res = load_common_metadata(path)
                self._current_tags, self._current_rating = res.tags, res.rating
                self._current_metadata_path = path

        self._loaded_path = path
        self.load_faces()
        self._trigger_preload()
        return True, True

    def load_faces(self):
        """
        Loads face regions from XMP metadata and resolves short names to full
        tag paths.
        """
        path = self.get_current_path()
        faces_from_xmp = XmpManager.load_regions(path)

        if not faces_from_xmp:
            self.faces = []
            return

        resolved_faces = []
        seen_faces = set()

        for face in faces_from_xmp:
            # Validate geometry to discard malformed regions
            if not self._clamp_and_validate_face(face):
                continue

            # Check for exact duplicates based on geometry and name
            face_sig = (face.get('x'), face.get('y'), face.get('w'),
                        face.get('h'), face.get('name'))
            if face_sig in seen_faces:
                continue
            seen_faces.add(face_sig)

            short_name = face.get('name', '')
            # If name is a short name (no slash) and we have tags on the image
            if short_name and '/' not in short_name and self._current_tags:
                # Find all full tags on the image that match this short name
                possible_matches = [
                    tag for tag in self._current_tags
                    if tag.split('/')[-1] == short_name
                ]

                if len(possible_matches) >= 1:
                    # If multiple matches, pick the first. This is an ambiguity,
                    # but it's the best we can do. e.g. if image has both
                    # 'Person/Joe' and 'Friends/Joe' and face is named 'Joe'.
                    face['name'] = possible_matches[0]

            resolved_faces.append(face)

        self.faces = resolved_faces

    def save_faces(self):
        """
        Saves the current faces list to XMP metadata, storing only the short name.
        """
        path = self.get_current_path()
        if not path:
            return

        # Create a temporary list of faces with short names for saving to XMP
        faces_to_save = []
        seen_faces = set()

        for face in self.faces:
            face_copy = face.copy()
            # If the name is a hierarchical tag, save only the last part
            if 'name' in face_copy and face_copy['name']:
                face_copy['name'] = face_copy['name'].split('/')[-1]

            # Deduplicate to prevent file bloat
            face_sig = (
                face_copy.get('x'), face_copy.get('y'),
                face_copy.get('w'), face_copy.get('h'),
                face_copy.get('name')
            )
            if face_sig in seen_faces:
                continue
            seen_faces.add(face_sig)

            faces_to_save.append(face_copy)

        return XmpManager.save_regions(path, faces_to_save)

    def add_face(self, name, x, y, w, h, region_type="Face"):
        """Adds a new face. The full tag path should be passed as 'name'."""
        new_face = {
            'name': name,  # Expecting full tag path
            'x': x, 'y': y, 'w': w, 'h': h,
            'type': region_type
        }
        validated_face = self._clamp_and_validate_face(new_face)
        if validated_face:
            self.faces.append(validated_face)
            self.save_faces()

    def remove_face(self, face):
        """Removes a face and saves metadata."""
        if face in self.faces:
            self.faces.remove(face)
            self.save_faces()

    def toggle_tag(self, tag_name, add_tag):
        """Adds or removes a tag from the current image's xattrs."""
        current_path = self.get_current_path()
        if not current_path:
            return

        tags_set = set(self._current_tags)

        tag_changed = False
        if add_tag and tag_name not in tags_set:
            tags_set.add(tag_name)
            tag_changed = True
        elif not add_tag and tag_name in tags_set:
            tags_set.remove(tag_name)
            tag_changed = True

        if tag_changed:
            new_tags_list = sorted(list(tags_set))
            new_tags_str = ",".join(new_tags_list) if new_tags_list else None
            try:
                XattrManager.set_attribute(current_path, XATTR_NAME, new_tags_str)
                self._current_tags = new_tags_list  # Update internal state
                self.metadata_changed.emit(current_path,
                                           {'tags': new_tags_list,
                                            'rating': self._current_rating})
            except Exception:
                raise

    def set_rating(self, new_rating):
        current_path = self.get_current_path()
        if not current_path:
            return
        try:
            XattrManager.set_attribute(current_path, RATING_XATTR_NAME, str(new_rating))
            self._current_rating = new_rating  # Update internal state
            self.metadata_changed.emit(current_path,
                                       {'tags': self._current_tags,
                                        'rating': new_rating})
        except IOError as e:
            print(f"Error setting tags for {current_path}: {e}")

    def _clamp_and_validate_face(self, face_data):
        """
        Clamps face coordinates to be within the [0, 1] range and ensures validity.
        Returns a validated face dictionary or None if invalid.
        """
        x = face_data.get('x', 0.5)
        y = face_data.get('y', 0.5)
        w = face_data.get('w', 0.0)
        h = face_data.get('h', 0.0)

        # Ensure all values are finite numbers to prevent propagation of NaN/Inf
        if not all(math.isfinite(val) for val in (x, y, w, h)):
            return None

        # Basic validation: width and height must be positive
        if w <= 0 or h <= 0:
            return None

        # Clamp width and height to be at most 1.0
        w = min(w, 1.0)
        h = min(h, 1.0)

        # Clamp center coordinates to ensure the box is fully within the image
        face_data['x'] = max(w / 2.0, min(x, 1.0 - w / 2.0))
        face_data['y'] = max(h / 2.0, min(y, 1.0 - h / 2.0))
        face_data['w'] = w
        face_data['h'] = h
        return face_data

    def _create_region_from_pixels(self, x, y, w, h, img_w, img_h, region_type):
        """
        Creates a normalized region dictionary from pixel coordinates.

        Args:
            x (float): Top-left x coordinate in pixels.
            y (float): Top-left y coordinate in pixels.
            w (float): Width in pixels.
            h (float): Height in pixels.
            img_w (int): Image width in pixels.
            img_h (int): Image height in pixels.
            region_type (str): The type of region (Face, Pet, Body).

        Returns:
            dict: Validated normalized region or None.
        """
        if img_w <= 0 or img_h <= 0:
            return None

        if w <= 0 or h <= 0:
            return None

        new_region = {
            'name': '',
            'x': (x + w / 2) / img_w,
            'y': (y + h / 2) / img_h,
            'w': w / img_w,
            'h': h / img_h,
            'type': region_type
        }
        return self._clamp_and_validate_face(new_region)

    def _detect_faces_face_recognition(self, path):
        """Detects faces using the 'face_recognition' library."""
        import face_recognition
        new_faces = []
        try:
            image = face_recognition.load_image_file(path)
            face_locations = face_recognition.face_locations(image)
            h, w, _ = image.shape
            for (top, right, bottom, left) in face_locations:
                box_w = right - left
                box_h = bottom - top
                validated_face = self._create_region_from_pixels(
                    left, top, box_w, box_h, w, h, 'Face'
                )
                if validated_face:
                    new_faces.append(validated_face)
        except Exception as e:
            print(f"Error during face_recognition detection: {e}")
        return new_faces

    def _detect_faces_mediapipe(self, path):
        """Detects faces using the 'mediapipe' library with the new Tasks API."""
        import mediapipe as mp
        from mediapipe.tasks import python
        from mediapipe.tasks.python import vision

        new_faces = []

        if not os.path.exists(MEDIAPIPE_FACE_MODEL_PATH):
            print(f"MediaPipe model not found at: {MEDIAPIPE_FACE_MODEL_PATH}")
            print("Please download 'blaze_face_short_range.tflite' and place it there.")
            print(f"URL: {MEDIAPIPE_FACE_MODEL_URL}")
            return new_faces

        try:
            base_options = python.BaseOptions(
                model_asset_path=MEDIAPIPE_FACE_MODEL_PATH)
            options = vision.FaceDetectorOptions(base_options=base_options,
                                                 min_detection_confidence=0.5)

            # Silence MediaPipe warnings (stderr) during initialization
            stderr_fd = 2
            null_fd = os.open(os.devnull, os.O_WRONLY)
            save_fd = os.dup(stderr_fd)
            try:
                os.dup2(null_fd, stderr_fd)
                detector = vision.FaceDetector.create_from_options(options)
            finally:
                os.dup2(save_fd, stderr_fd)
                os.close(null_fd)
                os.close(save_fd)

            mp_image = mp.Image.create_from_file(path)
            detection_result = detector.detect(mp_image)

            if detection_result.detections:
                img_h, img_w = mp_image.height, mp_image.width
                for detection in detection_result.detections:
                    bbox = detection.bounding_box  # This is in pixels
                    validated_face = self._create_region_from_pixels(
                        bbox.origin_x, bbox.origin_y, bbox.width, bbox.height,
                        img_w, img_h, 'Face'
                    )
                    if validated_face:
                        new_faces.append(validated_face)

        except Exception as e:
            print(f"Error during MediaPipe detection: {e}")
        return new_faces

    def _detect_objects_mediapipe(self, path, allowlist, max_results, region_type):
        """
        Generic method to detect objects using MediaPipe ObjectDetector.

        Args:
            path (str): Path to image file.
            allowlist (list): List of category names to detect.
            max_results (int): Maximum number of results to return.
            region_type (str): The 'type' label for the detected regions.
        """
        import mediapipe as mp
        from mediapipe.tasks import python
        from mediapipe.tasks.python import vision

        new_regions = []

        if not os.path.exists(MEDIAPIPE_OBJECT_MODEL_PATH):
            print(f"MediaPipe model not found at: {MEDIAPIPE_OBJECT_MODEL_PATH}")
            print("Please download 'efficientdet_lite0.tflite' and place it there.")
            print(f"URL: {MEDIAPIPE_OBJECT_MODEL_URL}")
            return new_regions

        try:
            base_options = python.BaseOptions(
                model_asset_path=MEDIAPIPE_OBJECT_MODEL_PATH)
            options = vision.ObjectDetectorOptions(
                base_options=base_options,
                score_threshold=0.5,
                max_results=max_results,
                category_allowlist=allowlist)

            # Silence MediaPipe warnings (stderr) during initialization
            stderr_fd = 2
            null_fd = os.open(os.devnull, os.O_WRONLY)
            save_fd = os.dup(stderr_fd)
            try:
                os.dup2(null_fd, stderr_fd)
                detector = vision.ObjectDetector.create_from_options(options)
            finally:
                os.dup2(save_fd, stderr_fd)
                os.close(null_fd)
                os.close(save_fd)

            mp_image = mp.Image.create_from_file(path)
            detection_result = detector.detect(mp_image)

            if detection_result.detections:
                img_h, img_w = mp_image.height, mp_image.width
                for detection in detection_result.detections:
                    bbox = detection.bounding_box
                    validated_region = self._create_region_from_pixels(
                        bbox.origin_x, bbox.origin_y, bbox.width, bbox.height,
                        img_w, img_h, region_type
                    )
                    if validated_region:
                        new_regions.append(validated_region)

        except Exception as e:
            print(f"Error during MediaPipe {region_type} detection: {e}")
        return new_regions

    def _detect_pets_mediapipe(self, path):
        """Detects pets using the 'mediapipe' library object detection."""
        return self._detect_objects_mediapipe(path, ["cat", "dog"], 5, "Pet")

    def _detect_bodies_mediapipe(self, path):
        """Detects bodies using the 'mediapipe' library object detection."""
        return self._detect_objects_mediapipe(path, ["person"], 10, "Body")

    def detect_faces(self):
        """
        Detects faces using a configured or available detection engine.

        The detection order is determined by the user's configuration and
        library availability, with a fallback mechanism.
        """
        path = self.get_current_path()
        if not path:
            return []

        if not AVAILABLE_FACE_ENGINES:
            print(UITexts.NO_FACE_LIBS)
            return []

        preferred_engine = APP_CONFIG.get("face_detection_engine")

        # Create an ordered list of engines to try, starting with the preferred one.
        engines_to_try = []
        if preferred_engine in AVAILABLE_FACE_ENGINES:
            engines_to_try.append(preferred_engine)
        # Add other available engines as fallbacks.
        for engine in AVAILABLE_FACE_ENGINES:
            if engine not in engines_to_try:
                engines_to_try.append(engine)

        all_faces = []
        for engine in engines_to_try:
            if engine == "mediapipe":
                all_faces = self._detect_faces_mediapipe(path)
            elif engine == "face_recognition":
                all_faces = self._detect_faces_face_recognition(path)

            if all_faces:
                break  # Stop after the first successful detection.

        return all_faces

    def detect_pets(self):
        """
        Detects pets using a configured or available detection engine.
        """
        path = self.get_current_path()
        if not path:
            return []

        if not AVAILABLE_PET_ENGINES:
            print("No pet detection libraries found.")
            return []

        engine = APP_CONFIG.get("pet_detection_engine", "mediapipe")

        if engine == "mediapipe":
            return self._detect_pets_mediapipe(path)

        return []

    def detect_bodies(self):
        """
        Detects bodies using a configured or available detection engine.
        """
        path = self.get_current_path()
        if not path:
            return []

        engine = APP_CONFIG.get("body_detection_engine", "mediapipe")

        if engine == "mediapipe" and "mediapipe" in AVAILABLE_BODY_ENGINES:
            return self._detect_bodies_mediapipe(path)

        return []

    def get_display_pixmap(self):
        """
        Applies current transformations (rotation, zoom, flip) to the original
        pixmap.

        Returns:
            QPixmap: The transformed pixmap ready for display.
        """
        if self.pixmap_original.isNull():
            return QPixmap()

        # Start with an identity transform
        transform = QTransform()

        # Apply rotation
        if self.rotation != 0:
            transform.rotate(float(self.rotation))

        # Apply flips
        if self.flip_h:
            transform.scale(-1, 1)
        if self.flip_v:
            transform.scale(1, -1)

        # Apply the cumulative transform to the original pixmap
        transformed_pixmap = self.pixmap_original.transformed(
            transform, Qt.TransformationMode.SmoothTransformation)

        # Apply scaling (zoom) separately after rotation and flips,
        # as scaling should be based on the *transformed* dimensions.
        # This is important: if you scale before rotation, the scaling
        # factors might be applied to the wrong axes.
        if self.zoom_factor != 1.0:
            new_size_f = transformed_pixmap.size() * self.zoom_factor
            new_size = QSize(int(new_size_f.width()), int(new_size_f.height()))
            scaled_pixmap = transformed_pixmap.scaled(
                new_size, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation)
            return scaled_pixmap
        else:
            return transformed_pixmap

    def rotate(self, angle):
        """
        Adds to the current rotation angle.

        Args:
            angle (int): The angle in degrees to add (e.g., 90 or -90).
        """
        self.rotation += angle

    def toggle_flip_h(self):
        """Toggles the horizontal flip state of the image."""
        self.flip_h = not self.flip_h

    def toggle_flip_v(self):
        """Toggles the vertical flip state of the image."""
        self.flip_v = not self.flip_v

    def first(self):
        """Navigates to the first image in the list."""
        if not self.image_list:
            return
        self.index = 0

    def last(self):
        """Navigates to the last image in the list."""
        if not self.image_list:
            return
        self.index = max(0, len(self.image_list) - 1)

    def next(self):
        """Navigates to the next image, wrapping around if at the end."""
        if not self.image_list:
            return
        self.index = (self.index + 1) % len(self.image_list)

    def prev(self):
        """Navigates to the previous image, wrapping around if at the beginning."""
        if not self.image_list:
            return
        self.index = (self.index - 1) % len(self.image_list)

    def update_list(self, new_list, new_index=None, current_image_tags=None,
                    current_image_rating=0):
        """
        Updates the internal image list and optionally the current index.

        This method is used to refresh the list of images the controller works
        with, for example, after a filter is applied in the main window.

        Args:
            new_list (list): The new list of image paths.
            new_index (int, optional): The new index to set. If None, the
                                       controller tries to maintain the current
                                       index, adjusting if it's out of bounds.
                                       Defaults to None.
        """
        self.image_list = new_list
        if new_index is not None:
            self.index = new_index

        if not self.image_list:
            self.index = -1
        elif self.index >= len(self.image_list):
            self.index = max(0, len(self.image_list) - 1)
        elif self.index < 0:
            self.index = 0

        # Update current image metadata
        if current_image_tags is not None:
            self._current_tags = current_image_tags
            self._current_rating = current_image_rating
            self._current_metadata_path = self.get_current_path()
        else:
            # Reload from disk if not provided to ensure consistency
            path = self.get_current_path()
            if path:
                res = load_common_metadata(path)
                self._current_tags, self._current_rating = res.tags, res.rating
                self._current_metadata_path = path
            else:
                self._current_tags = []
                self._current_rating = 0
                self._current_metadata_path = None

        self._cached_next_image = None
        self._cached_next_index = -1
        self._trigger_preload()
        self.list_updated.emit(self.index)

    def update_list_on_exists(self, new_list, new_index=None):
        """
        Updates the list only if the old list is a subset of the new one.

        This is a specialized update method used to prevent jarring navigation
        changes. For instance, when a single image is opened directly, the initial
        list contains only that image. When the rest of the directory is scanned
        in the background, this method ensures the list is only updated if the
        original image is still present, making the transition seamless.
        """
        if set(self.image_list) <= set(new_list):
            self.image_list = new_list
            if new_index is not None:
                self.index = new_index
            if self.index >= len(self.image_list):
                self.index = max(0, len(self.image_list) - 1)

        # Reload metadata for the current image to avoid stale/empty state
        path = self.get_current_path()
        if path:
            res = load_common_metadata(path)
            self._current_tags, self._current_rating = res.tags, res.rating
            self._current_metadata_path = path
        else:
            self._current_tags = []
            self._current_rating = 0
            self._current_metadata_path = None

        self._cached_next_image = None
        self._cached_next_index = -1
        self._trigger_preload()
        self.list_updated.emit(self.index)
