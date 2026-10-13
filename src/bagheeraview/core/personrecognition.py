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
    supports both exact and tolerance-based deletion of records.  Reads and
    writes are protected by an internal lock, so a single instance is safe to
    share across threads.

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

    # ------------------------------------------------------------------
    # Public query API
    # ------------------------------------------------------------------

    def get_all_faces(self):
        """Return a list of all stored face record dictionaries.

        Returns:
            list[dict]: One dict per record, with keys ``face_id``, ``tag``,
            ``encoding`` and ``created_at``.
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

            stored = self._encodings.get(arr.size)
            if not stored:
                return []

            face_ids = list(stored.keys())
            matrix = np.vstack([stored[fid] for fid in face_ids])
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
    def add_face(self, face_id=None, encoding=None, tag=None):
        """Store a face identifier, encoding vector and person tag.

        Any existing record whose encoding lies within the default tolerance
        of the new one is removed first, so re-tagging the same face replaces
        the previous association.  The delete + insert runs in a single LMDB
        write transaction (atomic).

        Args:
            face_id (str, optional): Unique identifier for this face.  When
                ``None`` a new identifier is generated.
            encoding (list[float] or numpy.ndarray): Feature vector.
            tag (str): Person tag string.

        Returns:
            bool: ``True`` when the record was persisted, ``False`` otherwise.
        """
        arr = _normalize_vector(encoding)
        if not tag or arr is None:
            return False

        if not face_id:
            face_id = f"face_{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}"

        record = {
            "face_id": face_id,
            "tag": tag,
            "encoding": arr.tolist(),
            "created_at": time.time(),
        }

        with self._lock:
            if not self._lmdb_env or not self._db:
                self._open_db_locked()
            if not self._lmdb_env or not self._db:
                return False
            self._ensure_cache_locked()

            # Keep the cache consistent if the same face_id is re-added with
            # a different encoding dimensionality (the write below overwrites).
            for dim_map in self._encodings.values():
                dim_map.pop(face_id, None)
            self._records.pop(face_id, None)

            try:
                with self._lmdb_env.begin(db=self._db, write=True) as txn:
                    for fid, stored in list(
                            self._encodings.get(arr.size, {}).items()):
                        if np.linalg.norm(
                                stored - arr) <= _default_tolerance(arr.size):
                            txn.delete(fid.encode("utf-8"))
                            self._records.pop(fid, None)
                            self._encodings[arr.size].pop(fid, None)
                    txn.put(
                        face_id.encode("utf-8"),
                        json.dumps(record).encode("utf-8"))
                self._records[face_id] = record
                self._encodings.setdefault(arr.size, {})[face_id] = arr
                logger.info("Stored person face record %s -> %r", face_id, tag)
                return True
            except lmdb.Error as exc:
                logger.error("Error writing face record to DB: %s", exc)
                return False

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
                    logger.info("Removed face record %s", face_id)
                return bool(deleted)
            except lmdb.Error as exc:
                logger.error("Error removing face record from DB: %s", exc)
                return False

    def remove_face_by_encoding(self, target_encoding, tolerance=0.6):
        """Remove every stored record matching ``target_encoding``.

        Args:
            target_encoding (list[float] or numpy.ndarray): Vector to match.
            tolerance (float): Maximum Euclidean distance.  Pass ``0`` to
                delete only exact duplicates.

        Returns:
            int: Number of deleted records.
        """
        matches = self.find_matches(target_encoding, tolerance)
        face_ids = [match["face_id"] for match in matches]
        deleted_count = 0
        for face_id in face_ids:
            if self.remove_face(face_id):
                deleted_count += 1
        if deleted_count:
            logger.info(
                "Removed %d person recognition record(s) matching encoding",
                deleted_count)
        return deleted_count
