"""
Person Recognition and DB Persistence Module for Bagheera.

Manages face encodings / feature vectors and person tag associations
stored in an LMDB database table (PERSON_RECOGNITION_DB_NAME).
"""
import json
import logging
import os
import uuid
import time
from pathlib import Path
import numpy as np

import lmdb
from PIL import Image

from .constants import PERSON_RECOGNITION_PATH, PERSON_RECOGNITION_DB_NAME

logger = logging.getLogger(__name__)


def extract_face_encoding(image_path, face_region):
    """
    Extracts a feature encoding vector for a given face region in an image.

    Args:
        image_path (str): Path to image file.
        face_region (dict): Normalized region with 'x', 'y', 'w', 'h'.

    Returns:
        list[float] or None: Extract vector of floats, or None on error.
    """
    if not image_path or not os.path.exists(image_path) or not face_region:
        return None

    try:
        with Image.open(image_path) as img:
            img_w, img_h = img.size
            if img_w <= 0 or img_h <= 0:
                return None

            cx = face_region.get('x', 0.5) * img_w
            cy = face_region.get('y', 0.5) * img_h
            bw = face_region.get('w', 0.1) * img_w
            bh = face_region.get('h', 0.1) * img_h

            left = int(max(0, min(img_w - 1, cx - bw / 2)))
            top = int(max(0, min(img_h - 1, cy - bh / 2)))
            right = int(max(left + 1, min(img_w, cx + bw / 2)))
            bottom = int(max(top + 1, min(img_h, cy + bh / 2)))

            # Try face_recognition if available
            try:
                import face_recognition
                rgb_img = np.array(img.convert('RGB'))
                encodings = face_recognition.face_encodings(
                    rgb_img, [(top, right, bottom, left)])
                if encodings:
                    return encodings[0].tolist()
            except Exception as fe_err:
                logger.debug(f"face_recognition encoding fallback: {fe_err}")

            # Fallback feature vector: normalized 32x32 grayscale crop
            crop = img.crop((left, top, right, bottom)).convert('L').resize((32, 32))
            arr = np.array(crop, dtype=np.float32).flatten()
            norm = np.linalg.norm(arr)
            if norm > 0:
                arr /= norm
            return arr.tolist()

    except Exception as e:
        logger.error(f"Error extracting face encoding for {image_path}: {e}")
        return None


class PersonRecognitionDB:
    """Manages LMDB storage and matching of face encodings with person tags."""

    _instance = None

    def __init__(self, db_path=None):
        self.db_path = db_path or PERSON_RECOGNITION_PATH

        self._lmdb_env = None
        self._db = None
        self.open_db()

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def open_db(self):
        try:
            cache_dir = Path(self.db_path)
            cache_dir.mkdir(parents=True, exist_ok=True)

            self._lmdb_env = lmdb.open(
                str(cache_dir),
                map_size=1024 * 1024 * 1024,  # 1GB max database size
                max_dbs=512,
                readonly=False,
                create=True
            )
            self._db = self._lmdb_env.open_db(PERSON_RECOGNITION_DB_NAME, create=True)
            logger.info(f"Person recognition LMDB opened at {self.db_path}")
        except Exception as e:
            logger.error(f"Failed to open Person Recognition DB: {e}")
            self._lmdb_env = None
            self._db = None

    def remove_face_by_encoding(self, target_encoding, tolerance=0.6):
        """
        Removes any stored face records that match target_encoding within tolerance.

        Args:
            target_encoding (list[float]): Vector to match and remove.
            tolerance (float): Distance threshold.

        Returns:
            int: Number of deleted records.
        """
        if not target_encoding or not self._lmdb_env or not self._db:
            return 0

        records = self.get_all_faces()
        if not records:
            return 0

        target_arr = np.array(target_encoding, dtype=np.float32)
        current_tolerance = tolerance if len(target_encoding) == 128 else 0.45
        to_delete = []

        for rec in records:
            stored_enc = rec.get("encoding")
            if not stored_enc or len(stored_enc) != len(target_encoding):
                continue
            stored_arr = np.array(stored_enc, dtype=np.float32)
            dist = float(np.linalg.norm(target_arr - stored_arr))
            if dist <= current_tolerance:
                face_id = rec.get("face_id")
                if face_id:
                    to_delete.append(face_id)

        if not to_delete:
            return 0

        deleted_count = 0
        try:
            with self._lmdb_env.begin(db=self._db, write=True) as txn:
                for fid in to_delete:
                    if txn.delete(fid.encode('utf-8')):
                        deleted_count += 1
            logger.info(f"Removed {deleted_count} person recognition record(s) matching encoding")
        except Exception as e:
            logger.error(f"Error removing face record from DB: {e}")

        return deleted_count

    def add_face(self, face_id, encoding, tag):
        """
        Stores a face identifier, face encoding vector, and person tag.
        Removes any prior matching record for the same encoding first.

        Args:
            face_id (str): Unique identifier for this face. If None, auto-generated.
            encoding (list[float]): Feature vector.
            tag (str): Person tag string.
        """
        if not tag or not encoding:
            return False

        # Remove existing records matching this encoding before writing new tag
        self.remove_face_by_encoding(encoding, tolerance=0)  # exact match

        if not face_id:
            face_id = f"face_{int(time.time()*1000)}_{uuid.uuid4().hex[:8]}"

        if not self._lmdb_env or not self._db:
            self.open_db()
            if not self._lmdb_env or not self._db:
                return False

        record = {
            "face_id": face_id,
            "tag": tag,
            "encoding": encoding,
            "created_at": time.time()
        }

        try:
            with self._lmdb_env.begin(db=self._db, write=True) as txn:
                txn.put(
                    face_id.encode('utf-8'),
                    json.dumps(record).encode('utf-8')
                )
            logger.info(f"Stored person face recognition record: {face_id} -> '{tag}'")
            return True
        except Exception as e:
            logger.error(f"Error writing face record to DB: {e}")
            return False

    def get_all_faces(self):
        """Returns list of stored face dict records."""
        if not self._lmdb_env or not self._db:
            return []

        records = []
        try:
            with self._lmdb_env.begin(db=self._db, write=False) as txn:
                cursor = txn.cursor()
                for k, v in cursor:
                    try:
                        rec = json.loads(v.decode('utf-8'))
                        records.append(rec)
                    except Exception:
                        pass
        except Exception as e:
            logger.error(f"Error reading face records from DB: {e}")
        return records

    def identify_person(self, target_encoding, tolerance=0.6):
        """
        Identifies a person by comparing target_encoding to stored encodings.

        Args:
            target_encoding (list[float]): Vector to check.
            tolerance (float): Distance threshold (default 0.6 for dlib 128D vectors).

        Returns:
            tuple: (matched_tag, face_id) if identified, or (None, None).
        """
        if not target_encoding:
            return None, None

        records = self.get_all_faces()
        if not records:
            return None, None

        target_arr = np.array(target_encoding, dtype=np.float32)
        best_tag = None
        best_face_id = None
        min_dist = float('inf')

        current_tolerance = tolerance if len(target_encoding) == 128 else 0.45

        for rec in records:
            stored_enc = rec.get("encoding")
            if not stored_enc or len(stored_enc) != len(target_encoding):
                continue

            stored_arr = np.array(stored_enc, dtype=np.float32)
            dist = float(np.linalg.norm(target_arr - stored_arr))

            if dist < min_dist and dist <= current_tolerance:
                min_dist = dist
                best_tag = rec.get("tag")
                best_face_id = rec.get("face_id")

        if best_tag:
            logger.info(f"Person identified: '{best_tag}' (distance: {min_dist:.4f})")
            return best_tag, best_face_id

        return None, None
