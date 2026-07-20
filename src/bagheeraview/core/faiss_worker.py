import os
import sqlite3
import urllib.request
import logging
import numpy as np
import faiss
import PIL.Image
from PySide6.QtCore import QThread, Signal
from .constants import APP_DATA_DIR, IMAGE_EXTENSIONS

logger = logging.getLogger(__name__)

MODEL_URL = "https://storage.googleapis.com/mediapipe-models/image_embedder/" \
            "mobilenet_v3_small/float32/latest/mobilenet_v3_small.tflite"
MODEL_PATH = os.path.join(APP_DATA_DIR, "mobilenet_v3_small.tflite")
DB_PATH = os.path.join(APP_DATA_DIR, "faiss_embeddings.db")


class FAISSSimilarSearchWorker(QThread):
    """
    Worker thread to find similar images to a target path using FAISS and MediaPipe embeddings.
    """
    progress_update = Signal(int, int, str)
    results_found = Signal(list)  # List of (path, similarity)
    finished = Signal()

    def __init__(self, target_path, threshold, whitelist_str, blacklist_str):
        super().__init__()
        self.target_path = os.path.abspath(os.path.normpath(target_path))
        self.threshold = threshold
        self._is_running = True

        self.whitelist = [os.path.abspath(os.path.expanduser(p.strip()))
                          for p in whitelist_str.split(',') if p.strip()]
        self.blacklist = [os.path.abspath(os.path.expanduser(p.strip()))
                          for p in blacklist_str.split(',') if p.strip()]

        # Fallback if whitelist is empty
        if not self.whitelist:
            self.whitelist = [os.path.dirname(self.target_path)]

    def stop(self):
        self._is_running = False
        self.wait()

    def _is_allowed(self, path):
        abs_p = os.path.abspath(os.path.normpath(path))
        for b in self.blacklist:
            if abs_p == b or abs_p.startswith(b + os.sep):
                return False
        for w in self.whitelist:
            if abs_p == w or abs_p.startswith(w + os.sep):
                return True
        return False

    def _get_all_images(self):
        images = []
        for root_path in self.whitelist:
            if not os.path.isdir(root_path):
                if os.path.isfile(root_path) and os.path.splitext(root_path)[1].lower() in IMAGE_EXTENSIONS:
                    if not self._is_allowed(root_path):
                        continue
                    images.append(os.path.abspath(root_path))
                continue
            for root, dirs, files in os.walk(root_path):
                # Prune blacklisted subdirectories in-place
                dirs[:] = [d for d in dirs if self._is_allowed(os.path.join(root, d))]

                for f in files:
                    ext = os.path.splitext(f)[1].lower()
                    if ext in IMAGE_EXTENSIONS:
                        full_path = os.path.join(root, f)
                        if self._is_allowed(full_path):
                            images.append(os.path.abspath(full_path))
        return list(set(images))

    def _init_db(self):
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS embeddings (
                path TEXT PRIMARY KEY,
                mtime REAL,
                embedding BLOB
            )
        """)
        conn.commit()
        return conn

    def _download_model_if_needed(self):
        if not os.path.exists(MODEL_PATH):
            os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
            logger.info("Downloading MediaPipe model...")
            self.progress_update.emit(0, 0, "Downloading model...")
            urllib.request.urlretrieve(MODEL_URL, MODEL_PATH)
            logger.info("Model downloaded successfully.")

    def run(self):
        conn = None
        try:
            conn = self._init_db()
            cursor = conn.cursor()

            # 1. Scan filesystem for allowed images
            self.progress_update.emit(0, 0, "Scanning files...")
            disk_images = self._get_all_images()
            disk_images_set = set(disk_images)

            # Ensure target image is in the set to be indexed
            if os.path.exists(self.target_path) and self.target_path not in disk_images_set:
                disk_images.append(self.target_path)
                disk_images_set.add(self.target_path)

            # 2. Get cached entries from DB
            cursor.execute("SELECT path, mtime FROM embeddings")
            db_entries = cursor.fetchall()
            db_mapping = {path: mtime for path, mtime in db_entries}

            # 3. Transparently delete stale images from DB
            stale_paths = [path for path in db_mapping if path not in disk_images_set]
            if stale_paths:
                cursor.executemany("DELETE FROM embeddings WHERE path = ?", [(p,) for p in stale_paths])
                conn.commit()
                logger.info(f"Removed {len(stale_paths)} stale images from index.")

            # 4. Identify images to add or update
            images_to_process = []
            for path in disk_images:
                try:
                    mtime = os.path.getmtime(path)
                    if path not in db_mapping or abs(db_mapping[path] - mtime) > 0.001:
                        images_to_process.append((path, mtime))
                except OSError:
                    continue

            # 5. Process new/modified images
            if images_to_process:
                self._download_model_if_needed()

                # Dynamic imports of mediapipe to avoid overhead when not running
                import mediapipe as mp
                from mediapipe.tasks import python
                from mediapipe.tasks.python import vision

                base_options = python.BaseOptions(model_asset_path=MODEL_PATH)
                options = vision.ImageEmbedderOptions(base_options=base_options, l2_normalize=True)

                total = len(images_to_process)
                processed = 0

                with vision.ImageEmbedder.create_from_options(options) as embedder:
                    for path, mtime in images_to_process:
                        if not self._is_running:
                            logger.info("Vector generation aborted by user.")
                            break

                        try:
                            with PIL.Image.open(path) as pil_img:
                                rgb_img = pil_img.convert('RGB')
                                image_np = np.array(rgb_img)
                            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=image_np)
                            emb_res = embedder.embed(mp_image)
                            if emb_res.embeddings:
                                emb_arr = np.array(emb_res.embeddings[0].embedding, dtype=np.float32)
                                emb_bytes = emb_arr.tobytes()
                                cursor.execute(
                                    "INSERT OR REPLACE INTO embeddings (path, mtime, embedding) VALUES (?, ?, ?)",
                                    (path, mtime, emb_bytes)
                                )
                        except Exception as e:
                            logger.warning(f"Failed to embed image {path}: {e}")

                        processed += 1
                        if processed % 50 == 0:
                            conn.commit()
                        self.progress_update.emit(
                            processed, total,
                            f"Generating vectors... {processed}/{total}"
                        )
                conn.commit()

            # 6. Load all embeddings from DB to build FAISS index
            cursor.execute("SELECT path, embedding FROM embeddings")
            all_db_records = cursor.fetchall()

            paths_list = []
            embeddings_list = []
            target_emb = None

            for path, emb_bytes in all_db_records:
                if emb_bytes:
                    emb = np.frombuffer(emb_bytes, dtype=np.float32)
                    # Just double check dimensions
                    if emb.shape[0] == 1024:
                        paths_list.append(path)
                        embeddings_list.append(emb)
                        if path == self.target_path:
                            target_emb = emb

            if target_emb is None and os.path.exists(self.target_path):
                # Calculate query target embedding if not already cached
                self._download_model_if_needed()
                import mediapipe as mp
                from mediapipe.tasks import python
                from mediapipe.tasks.python import vision
                base_options = python.BaseOptions(model_asset_path=MODEL_PATH)
                options = vision.ImageEmbedderOptions(base_options=base_options, l2_normalize=True)
                with vision.ImageEmbedder.create_from_options(options) as embedder:
                    try:
                        with PIL.Image.open(self.target_path) as pil_img:
                            rgb_img = pil_img.convert('RGB')
                            image_np = np.array(rgb_img)
                        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=image_np)
                        emb_res = embedder.embed(mp_image)
                        if emb_res.embeddings:
                            target_emb = np.array(emb_res.embeddings[0].embedding, dtype=np.float32)
                    except Exception as e:
                        logger.error(f"Failed to embed target image: {e}")

            results = []
            if target_emb is not None and embeddings_list:
                embeddings_np = np.vstack(embeddings_list).astype(np.float32)
                # Normalize just to be sure
                faiss.normalize_L2(embeddings_np)

                index_cpu = faiss.IndexFlatIP(1024)

                try:
                    # 1. Initialize GPU resources
                    res = faiss.StandardGpuResources()
                    # 2. Migrate the flat index to the GPU (device 0 = first NVIDIA graphics card)
                    index = faiss.index_cpu_to_gpu(res, 0, index_cpu)
                    logger.info("FAISS is using the GPU (NVIDIA).")
                except Exception as gpu_err:
                    logger.warning(f"Could not initialize FAISS on GPU, falling back to CPU. Error: {gpu_err}")
                    index = index_cpu

                index.add(embeddings_np)

                query_emb = target_emb.reshape(1, 1024).astype(np.float32)
                faiss.normalize_L2(query_emb)

                # Search all of them
                k = len(paths_list)
                # If we successfully migrated to a GPU index, enforce the CUDA k-selection limit
                if isinstance(index, faiss.GpuIndex):
                    max_gpu_k = 2048
                    if k > max_gpu_k:
                        logger.info(f"Requested k={k} exceeds GPU constraints. Capping k at {max_gpu_k} for CUDA execution.")
                        k = max_gpu_k

                distances, indexes = index.search(query_emb, k)

                for dist, idx in zip(distances[0], indexes[0]):
                    if idx < 0 or idx >= len(paths_list):
                        continue
                    matched_path = paths_list[idx]
                    if matched_path == self.target_path:
                        continue

                    # Convert cosine similarity (-1 to 1) to percentage (0 to 100)
                    sim_pct = int(max(0.0, min(1.0, dist)) * 100)
                    if sim_pct >= self.threshold:
                        results.append((matched_path, sim_pct))

            results.sort(key=lambda x: x[1], reverse=True)
            self.results_found.emit(results)

        except Exception as e:
            logger.error(f"FAISSSimilarSearchWorker error: {e}", exc_info=True)
        finally:
            if conn:
                conn.close()
            self.finished.emit()
