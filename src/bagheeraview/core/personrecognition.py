"""
Person Recognition and DB Persistence Module for Bagheera.

This module provides two main pieces of functionality:

* :func:`extract_face_encoding`: builds a compact feature vector from a
  single face region of an image.
* :class:`PersonRecognitionDB`: an LMDB-backed persistence layer that maps
  face encodings to person tags and performs nearest-neighbour matching.

The primary encoding path uses the optional ``face_recognition`` library
(dlib 128-D vectors) when it is installed.  When the library is unavailable,
or fails to produce an encoding for a particular crop, a self-contained
mean-centred 32x32 grayscale descriptor is used as a fallback so that the
feature extraction never depends on optional dependencies.

Coordinates in ``face_region`` are normalized to the image dimensions (the
same convention used by MediaPipe / face_recognition face detection in
:mod:`bagheeraview.core.imagecontroller`), so ``x`` and ``y`` represent the
center of the region and ``w`` / ``h`` its width and height.
"""
import json
import logging
import math
import os
import threading
import time
import uuid
from pathlib import Path

import lmdb
import numpy as np
from PIL import Image

from .constants import PERSON_RECOGNITION_PATH, PERSON_RECOGNITION_DB_NAME

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module level constants
# ---------------------------------------------------------------------------

#: Default LMDB map size (1 GiB).
DEFAULT_MAP_SIZE = 1024 * 1024 * 1024

#: Maximum number of named LMDB databases.
DEFAULT_MAX_DBS = 512

#: Dimension of dlib / ``face_recognition`` feature vectors.
FACE_ENCODING_DIM = 128

#: Default matching tolerance for 128-D ``face_recognition`` vectors.
DEFAULT_FACE_TOLERANCE = 0.6

#: Matching tolerance used for fallback feature vectors of any other
#: dimensionality (e.g. the 1024-D grayscale descriptor).
DEFAULT_FALLBACK_TOLERANCE = 0.45

#: Side length (in pixels) of the square grayscale fallback descriptor.
FALLBACK_FEATURE_SIZE = 32

#: Minimum Intersection over Union for two face regions to be considered the
#: same face (matches the duplicate-detection threshold used by
#: :class:`~bagheeraview.core.imageviewer.ImageViewer`).
FACE_REGION_IOU_THRESHOLD = 0.7

#: Guard so the singleton factory is safe to call from several threads.
_instance_lock = threading.Lock()


def _default_tolerance(encoding_dim):
    """Return the default matching tolerance for an encoding dimension.

    Args:
        encoding_dim (int): Dimensionality of the feature vector.

    Returns:
        float: Default Euclidean distance threshold for that dimensionality.
    """
    if encoding_dim == FACE_ENCODING_DIM:
        return DEFAULT_FACE_TOLERANCE
    return DEFAULT_FALLBACK_TOLERANCE


def _normalize_vector(values):
    """Coerce ``values`` into a validated 1-D float32 array.

    Args:
        values (iterable): Flat sequence of numbers.

    Returns:
        numpy.ndarray or None: A 1-D ``float32`` array, or ``None`` when the
        input is empty, is not flat, or contains non-finite entries.
    """
    if values is None:
        return None
    try:
        arr = np.asarray(values, dtype=np.float32)
    except (TypeError, ValueError):
        logger.debug("Rejecting encoding with non-numeric values")
        return None
    if arr.ndim != 1 or arr.size == 0:
        logger.debug("Rejecting encoding that is not a flat non-empty vector")
        return None
    if not np.all(np.isfinite(arr)):
        logger.debug("Rejecting encoding with NaN or infinite values")
        return None
    return arr


def _regions_iou(region_a, region_b):
    """Return the Intersection over Union of two centered normalized regions.

    Both regions use the ``x`` / ``y`` center plus ``w`` / ``h`` size
    convention, with coordinates normalized to the image dimensions.

    Args:
        region_a (dict): Region with keys ``x``, ``y``, ``w``, ``h``.
        region_b (dict): Region with keys ``x``, ``y``, ``w``, ``h``.

    Returns:
        float: IoU in the [0, 1] range (``0.0`` when the regions do not
        overlap).
    """
    a_x1 = region_a["x"] - region_a["w"] / 2
    a_y1 = region_a["y"] - region_a["h"] / 2
    a_x2 = region_a["x"] + region_a["w"] / 2
    a_y2 = region_a["y"] + region_a["h"] / 2

    b_x1 = region_b["x"] - region_b["w"] / 2
    b_y1 = region_b["y"] - region_b["h"] / 2
    b_x2 = region_b["x"] + region_b["w"] / 2
    b_y2 = region_b["y"] + region_b["h"] / 2

    inter_width = max(0.0, min(a_x2, b_x2) - max(a_x1, b_x1))
    inter_height = max(0.0, min(a_y2, b_y2) - max(a_y1, b_y1))
    intersection = inter_width * inter_height
    area_a = max(0.0, a_x2 - a_x1) * max(0.0, a_y2 - a_y1)
    area_b = max(0.0, b_x2 - b_x1) * max(0.0, b_y2 - b_y1)
    union = area_a + area_b - intersection
    if union <= 0:
        return 0.0
    return intersection / union


# Lazy, process-wide import of the optional face_recognition dependency.
_face_recognition_module = None
_face_recognition_checked = False


def _load_face_recognition():
    """Import and cache the optional ``face_recognition`` module.

    The import is attempted only once per process; a missing dependency is
    not treated as an error.

    Returns:
        module or None: The ``face_recognition`` module, or ``None`` when it
        is not installed.
    """
    global _face_recognition_module, _face_recognition_checked
    if not _face_recognition_checked:
        try:
            import face_recognition
            _face_recognition_module = face_recognition
        except ImportError:
            logger.debug(
                "face_recognition is not installed; using the fallback descriptor")
            _face_recognition_module = None
        _face_recognition_checked = True
    return _face_recognition_module


def extract_face_encoding(image_path, face_region):
    """Extract a feature encoding vector for a face region in an image.

    Args:
        image_path (str): Path to the image file.
        face_region (dict): Normalized region with keys ``x``, ``y`` (center),
            ``w`` and ``h`` (width/height), all in the [0, 1] range.

    Returns:
        list[float] or None: The feature vector, or ``None`` when the region
        is invalid, the image cannot be read, or encoding fails.

    Notes:
        The image is intentionally not EXIF-rotated, matching how face
        regions are produced by the detection engines in
        :mod:`bagheeraview.core.imagecontroller` (which operate on the raw
        pixel data).  Applying an orientation flip here would misalign the
        normalized region with the stored coordinates.
    """
    if not image_path or not face_region or not isinstance(face_region, dict):
        return None

    try:
        x = float(face_region.get("x"))
        y = float(face_region.get("y"))
        w = float(face_region.get("w"))
        h = float(face_region.get("h"))
    except (TypeError, ValueError):
        logger.debug("Invalid face_region values in %s", face_region)
        return None

    if w <= 0 or h <= 0 or not all(
            math.isfinite(v) for v in (x, y, w, h)):
        logger.debug("Non-positive or non-finite face_region in %s", face_region)
        return None

    if not os.path.isfile(image_path):
        return None

    try:
        with Image.open(image_path) as img:
            img_w, img_h = img.size
            if img_w <= 0 or img_h <= 0:
                return None

            cx = x * img_w
            cy = y * img_h
            bw = w * img_w
            bh = h * img_h

            left = int(max(0, min(img_w - 1, cx - bw / 2)))
            top = int(max(0, min(img_h - 1, cy - bh / 2)))
            right = int(max(left + 1, min(img_w, cx + bw / 2)))
            bottom = int(max(top + 1, min(img_h, cy + bh / 2)))

            # Try face_recognition (dlib 128-D vectors) when available.
            if _load_face_recognition() is not None:
                try:
                    # Cropping to the region is equivalent to passing the full
                    # image with the same box: face_recognition only reads the
                    # box crop for landmark alignment, so encodings match.
                    crop = img.crop((left, top, right, bottom)).convert("RGB")
                    rgb_img = np.array(crop)
                    box = (0, right - left, bottom - top, 0)  # top,right,bottom,left
                    encodings = _face_recognition_module.face_encodings(
                        rgb_img, [box])
                    if encodings:
                        return encodings[0].tolist()
                except Exception as exc:
                    logger.debug("face_recognition encoding failed: %s", exc)

            # Fallback: mean-centred, unit-norm 32x32 grayscale descriptor.
            crop = img.crop((left, top, right, bottom))
            crop = crop.convert("L").resize(
                (FALLBACK_FEATURE_SIZE, FALLBACK_FEATURE_SIZE))
            arr = np.asarray(crop, dtype=np.float32).flatten()
            arr -= arr.mean()
            norm = float(np.linalg.norm(arr))
            if norm > 0:
                arr /= norm
            return arr.tolist()

    except (OSError, ValueError) as exc:
        logger.error("Error extracting face encoding for %s: %s", image_path, exc)
        return None


class PersonRecognitionDB:
    """Store face encodings and person tags in an LMDB database.

    The class provides nearest-neighbour matching between feature vectors and
    source-based deletion of records: a record is only deleted when it was
    created from the same face (same image path and overlapping region).
    Reads and writes are protected by an internal lock, so a single instance
    is safe to share across threads.

    Args:
        db_path (str or Path, optional): Directory holding the LMDB
            environment.  Defaults to :data:`PERSON_RECOGNITION_PATH`.
    """

    _instance = None

    def __init__(self, db_path=None):
        self.db_path = db_path or PERSON_RECOGNITION_PATH

        self._lmdb_env = None
        self._db = None
        self._lock = threading.RLock()
        # In-memory cache of decoded records, kept in sync with the database.
        self._records = {}
        # Nested maps: dimension -> {face_id: numpy.ndarray}.
        self._encodings = {}
        # Cached stacked matrices per dimension, aligned with ``_encodings``:
        # {dimension: (face_ids list, numpy.ndarray matrix)}.
        self._stacked_encodings = {}
        self._cache_loaded = False
        self.open_db()

    # ------------------------------------------------------------------
    # Singleton / lifecycle
    # ------------------------------------------------------------------

    @classmethod
    def get_instance(cls):
        """Return the process-wide singleton instance.

        The factory is thread-safe and lazily creates the instance on first
        use.

        Returns:
            PersonRecognitionDB: The shared instance.
        """
        if cls._instance is None:
            with _instance_lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def open_db(self):
        """Open (or re-open) the LMDB environment and named database.

        A call while the environment is already open is a no-op.
        """
        with self._lock:
            self._open_db_locked()

    def _open_db_locked(self):
        """Open LMDB; the caller must hold ``self._lock``."""
        if self._lmdb_env is not None and self._db is not None:
            return
        try:
            cache_dir = Path(self.db_path)
            cache_dir.mkdir(parents=True, exist_ok=True)

            env = lmdb.open(
                str(cache_dir),
                map_size=DEFAULT_MAP_SIZE,
                max_dbs=DEFAULT_MAX_DBS,
                readonly=False,
                create=True,
            )
            db = env.open_db(PERSON_RECOGNITION_DB_NAME, create=True)
            self._lmdb_env = env
            self._db = db
            logger.info("Person recognition LMDB opened at %s", self.db_path)
        except lmdb.Error as exc:
            logger.error("Failed to open Person Recognition DB: %s", exc)
            self._lmdb_env = None
            self._db = None

    def close(self):
        """Close the LMDB environment and release all cached state.

        After closing, the instance may be reopened transparently by any of
        the public methods, or a fresh singleton can be obtained from
        :meth:`get_instance`.
        """
        with self._lock:
            self._cache_loaded = False
            self._records.clear()
            self._encodings.clear()
            self._stacked_encodings.clear()
            env = self._lmdb_env
            self._lmdb_env = None
            self._db = None
            if env is not None:
                try:
                    env.close()
                    logger.info("Person recognition LMDB closed")
                except lmdb.Error as exc:
                    logger.error("Error closing Person Recognition DB: %s", exc)

    def __enter__(self):
        """Context-manager support: return ``self`` for use in ``with``."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context-manager support: close the database on block exit."""
        self.close()
        return False

    # ------------------------------------------------------------------
    # Internal cache management
    # ------------------------------------------------------------------
    def _ensure_cache_locked(self):
        """Load the in-memory cache once; caller must hold ``self._lock``."""
        if not self._cache_loaded:
            self._load_cache_locked()

    def _load_cache_locked(self):
        """Rebuild the in-memory cache from LMDB; caller holds ``self._lock``."""
        self._records.clear()
        self._encodings.clear()
        self._stacked_encodings.clear()
        self._cache_loaded = False
        if not self._lmdb_env or not self._db:
            self._open_db_locked()
        if not self._lmdb_env or not self._db:
            return

        with self._lmdb_env.begin(db=self._db, write=False) as txn:
            for key, value in txn.cursor():
                try:
                    record = json.loads(value.decode("utf-8"))
                    arr = _normalize_vector(record.get("encoding"))
                    if arr is None:
                        logger.warning("Skipping invalid face record %r", key)
                        continue
                    face_id = str(record.get("face_id") or key.decode(
                        "utf-8", "replace"))
                    record["face_id"] = face_id
                    self._records[face_id] = record
                    self._encodings.setdefault(arr.size, {})[face_id] = arr
                except (UnicodeDecodeError, json.JSONDecodeError):
                    logger.warning("Skipping corrupt face record %r", key)
        self._cache_loaded = True

    def _invalidate_stack_locked(self):
        """Drop every cached stacked matrix; caller must hold ``self._lock``."""
        self._stacked_encodings.clear()

    def _stacked_for_dim_locked(self, dim):
        """Return ``(face_ids, matrix)`` for ``dim``, building and caching it.

        The rows of ``matrix`` are aligned with ``face_ids``.  Returns
        ``([], None)`` when no encoding of that dimensionality is stored.

        Args:
            dim (int): Encoding dimensionality.

        Returns:
            tuple: ``(list[str], numpy.ndarray or None)``.
        """
        cached = self._stacked_encodings.get(dim)
        if cached is not None:
            return cached

        stored = self._encodings.get(dim)
        if not stored:
            return [], None

        face_ids = list(stored.keys())
        matrix = np.vstack([stored[fid] for fid in face_ids])
        self._stacked_encodings[dim] = (face_ids, matrix)
        return face_ids, matrix

    # ------------------------------------------------------------------
    # Public query API
    # ------------------------------------------------------------------

    def get_all_faces(self):
        """Return a list of all stored face record dictionaries.

        Returns:
            list[dict]: One dict per record, with keys ``face_id``, ``tag``,
            ``encoding`` and ``created_at``, plus ``source`` (optional) with
            the image path and normalized region the face was created from.
        """
        with self._lock:
            if not self._lmdb_env or not self._db:
                self._open_db_locked()
            self._ensure_cache_locked()
            return [dict(record) for record in self._records.values()]

    def find_matches(self, encoding, tolerance=0.6):
        """Return every stored record within ``tolerance`` of ``encoding``.

        Args:
            encoding (list[float] or numpy.ndarray): Query feature vector.
            tolerance (float): Maximum Euclidean distance.  The effective
                threshold is ``min(tolerance, default_for_dimension)`` so
                callers can tighten (e.g. ``0`` for exact matching) but never
                accidentally widen the per-dimension default.

        Returns:
            list[dict]: Matching records sorted by ascending distance, each
            augmented with a ``distance`` key.
        """
        arr = _normalize_vector(encoding)
        if arr is None:
            return []

        with self._lock:
            if not self._lmdb_env or not self._db:
                self._open_db_locked()
            self._ensure_cache_locked()

            face_ids, matrix = self._stacked_for_dim_locked(arr.size)
            if matrix is None:
                return []

            dists = np.linalg.norm(matrix - arr, axis=1)

            effective = min(tolerance, _default_tolerance(arr.size))
            matches = []
            for fid, dist in zip(face_ids, dists):
                if dist <= effective:
                    record = dict(self._records[fid])
                    record["distance"] = float(dist)
                    matches.append(record)
            matches.sort(key=lambda record: record["distance"])
            return matches

    def identify_person(self, target_encoding, tolerance=0.6):
        """Identify a person from a feature vector.

        Args:
            target_encoding (list[float] or numpy.ndarray): Vector to check.
            tolerance (float): Distance threshold (default ``0.6`` is tuned
                for 128-D ``face_recognition`` vectors).

        Returns:
            tuple: ``(matched_tag, face_id)`` for the nearest matching record,
            or ``(None, None)`` when no record is close enough.
        """
        matches = self.find_matches(target_encoding, tolerance)
        if not matches:
            return None, None
        best = matches[0]
        logger.info(
            "Person identified: %r (distance: %.4f)",
            best.get("tag"), best.get("distance", 0.0))
        return best.get("tag"), best.get("face_id")

    def count(self):
        """Return the number of stored face records.

        Returns:
            int: Record count.
        """
        with self._lock:
            if not self._lmdb_env or not self._db:
                self._open_db_locked()
            self._ensure_cache_locked()
            return len(self._records)

    def __len__(self):
        """Support ``len(instance)`` as an alias for :meth:`count`."""
        return self.count()

    # ------------------------------------------------------------------
    # Public write API
    # ------------------------------------------------------------------
    def add_face(self, face_id=None, encoding=None, tag=None, source=None):
        """Store a face identifier, encoding vector and person tag.

        A record is tied to the face instance it was created from: ``source``
        identifies the exact image path and region.  Before inserting, only
        records created from the same face (same path and overlapping region)
        are removed, regardless of their tag, so editing a face's name
        replaces that face's own record while never deleting the reference of
        a different person whose encoding happens to be similar.  The delete +
        insert runs in a single LMDB write transaction (atomic).

        Args:
            face_id (str, optional): Unique identifier for this face.  When
                ``None`` a new identifier is generated.
            encoding (list[float] or numpy.ndarray): Feature vector.
            tag (str): Person tag string.
            source (dict, optional): Origin of the face, with keys ``path``
                (image path) and ``x``, ``y``, ``w``, ``h`` (normalized
                region).  When ``None`` the record is stored without origin
                and is never auto-replaced by another ``add_face`` call.

        Returns:
            bool: ``True`` when the record was persisted, ``False`` otherwise.
        """
        arr = _normalize_vector(encoding)
        if not tag or arr is None:
            return False

        if not face_id:
            face_id = f"face_{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}"

        source = self._normalize_source(source)

        record = {
            "face_id": face_id,
            "tag": tag,
            "encoding": arr.tolist(),
            "created_at": time.time(),
        }
        if source is not None:
            record["source"] = source

        with self._lock:
            if not self._lmdb_env or not self._db:
                self._open_db_locked()
            if not self._lmdb_env or not self._db:
                return False
            self._ensure_cache_locked()

            deleted_ids = []
            try:
                with self._lmdb_env.begin(db=self._db, write=True) as txn:
                    for fid, rec in list(self._records.items()):
                        if fid == face_id:
                            continue
                        if source is not None and self._same_face_source(
                                rec.get("source"), source):
                            txn.delete(fid.encode("utf-8"))
                            deleted_ids.append(fid)
                    txn.put(
                        face_id.encode("utf-8"),
                        json.dumps(record).encode("utf-8"))
            except lmdb.Error as exc:
                logger.error("Error writing face record to DB: %s", exc)
                return False

            # Only touch the in-memory cache after a successful commit so it
            # can never diverge from LMDB (even if the transaction rolled
            # back), and keep it consistent when the same face_id is re-added
            # with a different encoding dimensionality.
            for fid in deleted_ids:
                self._records.pop(fid, None)
                for dim_map in self._encodings.values():
                    dim_map.pop(fid, None)
            for dim_map in self._encodings.values():
                dim_map.pop(face_id, None)
            self._records.pop(face_id, None)
            self._records[face_id] = record
            self._encodings.setdefault(arr.size, {})[face_id] = arr
            self._invalidate_stack_locked()
            logger.info("Stored person face record %s -> %r", face_id, tag)
            return True

    def _normalize_source(self, source):
        """Coerce a face origin dict into a validated JSON-serializable form.

        Args:
            source (dict or None): Face origin with ``path`` and normalized
                ``x``, ``y``, ``w``, ``h``.

        Returns:
            dict or None: The sanitized origin, or ``None`` when the input is
            missing or malformed.
        """
        if source is None:
            return None
        if not isinstance(source, dict):
            logger.debug("Ignoring non-dict face source %r", source)
            return None
        try:
            return {
                "path": str(source.get("path")),
                "x": float(source.get("x")),
                "y": float(source.get("y")),
                "w": float(source.get("w")),
                "h": float(source.get("h")),
            }
        except (TypeError, ValueError):
            logger.warning("Ignoring invalid face source %r", source)
            return None

    def _same_face_source(self, stored_source, source):
        """Return ``True`` when a stored record belongs to the same face.

        Two faces are the same when they were created from the same image path
        and their regions overlap with at least
        :data:`FACE_REGION_IOU_THRESHOLD`.

        Args:
            stored_source (dict or None): Origin stored on the record.
            source (dict): Sanitized origin to compare against.

        Returns:
            bool: ``True`` for the same face.
        """
        if not stored_source or not isinstance(stored_source, dict):
            return False
        if stored_source.get("path") != source.get("path"):
            return False
        return _regions_iou(stored_source, source) >= FACE_REGION_IOU_THRESHOLD

    def remove_face(self, face_id):
        """Delete a single stored record by its face identifier.

        Args:
            face_id (str): Identifier of the record to delete.

        Returns:
            bool: ``True`` when a record was deleted.
        """
        if not face_id:
            return False

        with self._lock:
            if not self._lmdb_env or not self._db:
                self._open_db_locked()
            if not self._lmdb_env or not self._db:
                return False
            self._ensure_cache_locked()

            try:
                with self._lmdb_env.begin(db=self._db, write=True) as txn:
                    deleted = txn.delete(face_id.encode("utf-8"))
                if deleted:
                    self._records.pop(face_id, None)
                    for dim_map in self._encodings.values():
                        dim_map.pop(face_id, None)
                    self._invalidate_stack_locked()
                    logger.info("Removed face record %s", face_id)
                return bool(deleted)
            except lmdb.Error as exc:
                logger.error("Error removing face record from DB: %s", exc)
                return False

    def remove_face_by_source(self, path, region):
        """Remove every stored record created from a specific face region.

        Only records whose origin matches ``path`` and overlaps ``region``
        (at least :data:`FACE_REGION_IOU_THRESHOLD`) are deleted.  Records of
        other people are left untouched even when their encoding is similar.

        Args:
            path (str): Image path the face was tagged on.
            region (dict): Normalized face region with keys ``x``, ``y``
                (center), ``w`` and ``h`` (width/height).

        Returns:
            int: Number of deleted records.
        """
        if not path or not isinstance(region, dict):
            return 0
        source = self._normalize_source({**region, "path": path})
        if source is None:
            return 0

        with self._lock:
            if not self._lmdb_env or not self._db:
                self._open_db_locked()
            if not self._lmdb_env or not self._db:
                return 0
            self._ensure_cache_locked()

            deleted_ids = []
            try:
                with self._lmdb_env.begin(db=self._db, write=True) as txn:
                    for fid, rec in list(self._records.items()):
                        if self._same_face_source(rec.get("source"), source):
                            txn.delete(fid.encode("utf-8"))
                            deleted_ids.append(fid)
            except lmdb.Error as exc:
                logger.error("Error removing face records by source: %s", exc)
                return 0

            for fid in deleted_ids:
                self._records.pop(fid, None)
                for dim_map in self._encodings.values():
                    dim_map.pop(fid, None)
            self._invalidate_stack_locked()
            if deleted_ids:
                logger.info("Removed %d person recognition record(s) from %s",
                            len(deleted_ids), path)
            return len(deleted_ids)
