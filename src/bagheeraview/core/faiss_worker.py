"""
FAISS Similar Search Worker Module for Bagheera.

This module provides the FAISSSimilarSearchWorker, a QThread-based worker that
finds images visually similar to a target image. The worker maintains a
persistent SQLite cache of MediaPipe image embeddings, builds an in-memory
FAISS inner-product index (using an NVIDIA GPU when available) and emits the
matching results ordered by descending similarity.

Classes:
    FAISSSimilarSearchWorker: Background worker for the similar-image search.
"""
import os
import sqlite3
import urllib.request
import logging
import numpy as np
import faiss
import PIL.Image
from PySide6.QtCore import QThread, Signal
from .constants import APP_DATA_DIR, IMAGE_EXTENSIONS, DUPLICATE_AI_TOPK_DEFAULT

logger = logging.getLogger(__name__)

MODEL_URL = "https://storage.googleapis.com/mediapipe-models/image_embedder/" \
            "mobilenet_v3_small/float32/latest/mobilenet_v3_small.tflite"
MODEL_PATH = os.path.join(APP_DATA_DIR, "mobilenet_v3_small.tflite")
DB_PATH = os.path.join(APP_DATA_DIR, "faiss_embeddings.db")

# MediaPipe MobileNet V3 Small embedding dimension.
_EMBEDDING_DIM = 1024
# FAISS GPU k-selection limit for CUDA execution.
_GPU_MAX_K = 2048


def _download_model_if_needed(progress_callback=None):
    """
    Downloads the MediaPipe embedder model when it is not yet cached.

    Args:
        progress_callback (callable, optional): Called with
            ``(0, 0, "Downloading model...")`` while the model is fetched.
    """
    if not os.path.exists(MODEL_PATH):
        os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
        logger.info("Downloading MediaPipe model...")
        if progress_callback is not None:
            progress_callback(0, 0, "Downloading model...")
        urllib.request.urlretrieve(MODEL_URL, MODEL_PATH)
        logger.info("Model downloaded successfully.")


def _open_embeddings_db():
    """
    Opens (and creates if needed) the local embedding cache database.

    Returns:
        sqlite3.Connection: Connection to the embeddings cache with the
            schema already initialized.
    """
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


def _refresh_embeddings(conn, disk_images, progress_callback=None,
                        is_running_callback=None, existing_embeddings=None):
    """
    Updates the embedding cache with the current state of the disk images.

    Entries whose files no longer exist on disk are pruned and entries whose
    modification time changed are regenerated. When ``existing_embeddings``
    is provided, its contents are reused and the disk is only read for the
    paths not included in it; this avoids re-running the embedder when a
    warmed cache from a previous search is available.

    The MediaPipe embedder is created lazily and the whole generation can be
    aborted through ``is_running_callback``.

    Args:
        conn (sqlite3.Connection): Open connection to the embedding cache.
        disk_images (list): Absolute paths of the images expected in cache.
        progress_callback (callable, optional): Called as
            ``(processed, total, message)`` while images are processed.
        is_running_callback (callable, optional): Called with no arguments;
            when it returns False the generation aborts early.
        existing_embeddings (dict, optional): Mapping from path to a cached
            (mtime, embedding_bytes) tuple that is reused instead of reading
            the file again.

    Returns:
        None
    """
    cursor = conn.cursor()

    cursor.execute("SELECT path, mtime FROM embeddings")
    db_mapping = dict(cursor.fetchall())
    disk_images_set = set(disk_images)

    # Prune cache entries whose file no longer belongs to the search scope.
    # The caller passes the full set of paths it is interested in, so any DB
    # entry outside that set is stale for this operation.
    stale_paths = [path for path in db_mapping
                   if path not in disk_images_set]
    if stale_paths:
        cursor.executemany("DELETE FROM embeddings WHERE path = ?",
                           [(p,) for p in stale_paths])
        conn.commit()
        logger.info(f"Removed {len(stale_paths)} stale images from index.")

    # Identify images to add or update.
    images_to_process = []
    for path in disk_images:
        try:
            if existing_embeddings is not None \
                    and path in existing_embeddings:
                continue
            mtime = os.path.getmtime(path)
            if path not in db_mapping \
                    or abs(db_mapping[path] - mtime) > 0.001:
                images_to_process.append((path, mtime))
        except OSError:
            continue

    if not images_to_process:
        return

    _download_model_if_needed()

    # Dynamic imports of mediapipe to avoid overhead when not running.
    import mediapipe as mp
    from mediapipe.tasks import python
    from mediapipe.tasks.python import vision

    base_options = python.BaseOptions(model_asset_path=MODEL_PATH)
    options = vision.ImageEmbedderOptions(base_options=base_options,
                                          l2_normalize=True)

    total = len(images_to_process)
    processed = 0

    with vision.ImageEmbedder.create_from_options(options) as embedder:
        for path, mtime in images_to_process:
            if is_running_callback is not None \
                    and not is_running_callback():
                logger.info("Vector generation aborted by user.")
                break

            try:
                with PIL.Image.open(path) as pil_img:
                    rgb_img = pil_img.convert('RGB')
                    image_np = np.array(rgb_img)
                mp_image = mp.Image(image_format=mp.ImageFormat.SRGB,
                                    data=image_np)
                emb_res = embedder.embed(mp_image)
                if emb_res.embeddings:
                    emb_arr = np.array(emb_res.embeddings[0].embedding,
                                       dtype=np.float32)
                    emb_bytes = emb_arr.tobytes()
                    cursor.execute(
                        "INSERT OR REPLACE INTO embeddings "
                        "(path, mtime, embedding) VALUES (?, ?, ?)",
                        (path, mtime, emb_bytes)
                    )
            except Exception as e:
                logger.warning(f"Failed to embed image {path}: {e}")

            processed += 1
            if processed % 50 == 0:
                conn.commit()
            if progress_callback is not None:
                progress_callback(processed, total,
                                  f"Generating vectors... "
                                  f"{processed}/{total}")
    conn.commit()


def _embed_single_image(path):
    """
    Computes the MediaPipe embedding of a single image.

    Args:
        path (str): Absolute path of the image.

    Returns:
        numpy.ndarray | None: The embedding vector, or None when the model
            is unavailable or the image cannot be processed.
    """
    _download_model_if_needed()
    try:
        import mediapipe as mp
        from mediapipe.tasks import python
        from mediapipe.tasks.python import vision
        base_options = python.BaseOptions(model_asset_path=MODEL_PATH)
        options = vision.ImageEmbedderOptions(base_options=base_options,
                                              l2_normalize=True)
        with vision.ImageEmbedder.create_from_options(options) as embedder:
            with PIL.Image.open(path) as pil_img:
                rgb_img = pil_img.convert('RGB')
                image_np = np.array(rgb_img)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB,
                                data=image_np)
            emb_res = embedder.embed(mp_image)
            if emb_res.embeddings:
                return np.array(emb_res.embeddings[0].embedding,
                                dtype=np.float32)
    except Exception as e:
        logger.error(f"Failed to embed image {path}: {e}")
    return None


def _build_faiss_index(embeddings_np):
    """
    Builds a normalized inner-product index, using the NVIDIA GPU when
    available and falling back to the CPU otherwise.

    Args:
        embeddings_np (numpy.ndarray): Row-major matrix of embeddings; it is
            L2-normalized in place.

    Returns:
        faiss.IndexFlatIP: The ready-to-query index.
    """
    normalized = np.ascontiguousarray(embeddings_np, dtype=np.float32)
    faiss.normalize_L2(normalized)
    index_cpu = faiss.IndexFlatIP(_EMBEDDING_DIM)
    try:
        res = faiss.StandardGpuResources()
        index = faiss.index_cpu_to_gpu(res, 0, index_cpu)
        logger.info("FAISS is using the GPU (NVIDIA).")
    except Exception as gpu_err:
        logger.warning("Could not initialize FAISS on GPU, "
                       f"falling back to CPU. Error: {gpu_err}")
        index = index_cpu
    index.add(normalized)
    return index


class FaissPairSearcher:
    """
    Finds all visually similar image pairs in a set of paths.

    This class is not a QThread: it runs in the calling thread and is used
    by the duplicate detection pipeline to complement the perceptual hash
    search. It reuses the persistent MediaPipe embedding cache
    (``faiss_embeddings.db``) and reports pairs whose cosine similarity is at
    or above the configured threshold.

    The similarity percentage reported by this class (embedding cosine
    similarity) is NOT directly comparable to the perceptual hash percentage
    produced by the duplicate detector: the two values measure different
    visual properties on different scales.

    Attributes:
        paths (list): Absolute normalized paths of the images to compare.
        threshold (int): Minimum similarity percentage (0-100).
        top_k (int): Number of nearest neighbours considered per image;
            bounds the number of reported pairs.
    """

    def __init__(self, paths, threshold, top_k=DUPLICATE_AI_TOPK_DEFAULT,
                 progress_callback=None, is_running_callback=None):
        """
        Initializes the pair searcher.

        Args:
            paths (list): Absolute paths of the images to compare.
            threshold (int): Minimum similarity percentage (0-100).
            top_k (int, optional): Nearest neighbours considered per image.
            progress_callback (callable, optional): Called as
                ``(processed, total, message)`` while images are processed.
            is_running_callback (callable, optional): Polled to allow the
                caller to abort the search; must return True to keep going.
        """
        self.paths = [os.path.abspath(os.path.normpath(p)) for p in paths
                      if os.path.isfile(p)]
        self.threshold = threshold
        self.top_k = max(1, int(top_k))
        self._progress_callback = progress_callback
        self._is_running_callback = is_running_callback

    def _is_running(self):
        """Returns True when the caller did not request an abort."""
        if self._is_running_callback is None:
            return True
        try:
            return bool(self._is_running_callback())
        except Exception:
            return False

    def run(self):
        """
        Computes the missing embeddings and searches all image pairs.

        Returns:
            list: Tuples ``(path1, path2, similarity_pct)`` with
                ``path1 < path2`` and similarity at or above the threshold,
                ordered by descending similarity.
        """
        if not self.paths or not self._is_running():
            return []

        pairs = {}

        conn = _open_embeddings_db()
        try:
            # Reuse already-cached vectors when possible: _refresh_embeddings
            # only reads the disk for paths without a cache entry, avoiding a
            # second embedder run on a warmed cache.
            _refresh_embeddings(
                conn, self.paths,
                progress_callback=self._progress_callback,
                is_running_callback=self._is_running,
                existing_embeddings={path: None for path in self.paths})

            # Load exactly the embeddings of the requested paths. The query
            # is chunked to stay below SQLite's variable-number limit.
            cursor = conn.cursor()
            paths_list = []
            embeddings_list = []
            chunk_size = 400
            for start in range(0, len(self.paths), chunk_size):
                chunk = self.paths[start:start + chunk_size]
                placeholders = ",".join("?" * len(chunk))
                cursor.execute(
                    f"SELECT path, embedding FROM embeddings "
                    f"WHERE path IN ({placeholders})", chunk)
                for path, emb_bytes in cursor.fetchall():
                    if emb_bytes:
                        emb = np.frombuffer(emb_bytes, dtype=np.float32)
                        if emb.shape[0] == _EMBEDDING_DIM:
                            paths_list.append(path)
                            embeddings_list.append(emb)
        finally:
            conn.close()

        if len(paths_list) < 2 or not self._is_running():
            return []

        # Build the index and perform a batched all-pairs search.
        embeddings_np = np.vstack(embeddings_list).astype(np.float32)
        index = _build_faiss_index(embeddings_np)

        n = len(paths_list)
        k = min(self.top_k + 1, n)
        if isinstance(index, faiss.GpuIndex) and k > _GPU_MAX_K:
            logger.info(f"Requested k={k} exceeds GPU constraints; "
                        f"capping k at {_GPU_MAX_K} for CUDA execution.")
            k = _GPU_MAX_K

        batch_size = 512
        for start in range(0, n, batch_size):
            if not self._is_running():
                break
            batch = embeddings_np[start:start + batch_size]
            distances, indexes = index.search(batch, k)

            for row_idx, (dists, neigh) in enumerate(
                    zip(distances, indexes)):
                i = start + row_idx
                for dist, j in zip(dists, neigh):
                    if j < 0 or j == i:
                        continue
                    sim_pct = int(max(0.0, min(1.0, dist)) * 100)
                    if sim_pct < self.threshold:
                        continue
                    key = (min(i, j), max(i, j))
                    if key not in pairs or pairs[key][2] < sim_pct:
                        pairs[key] = (paths_list[key[0]], paths_list[key[1]],
                                      sim_pct)

        results = sorted(pairs.values(),
                         key=lambda item: item[2], reverse=True)
        return results


class FAISSSimilarSearchWorker(QThread):
    """
    Worker thread that finds images similar to a target image.

    The worker scans the whitelisted/blacklisted folders - or, when a set of
    ``visible_paths`` is provided, only those - updates the local embedding
    cache (``faiss_embeddings.db``) using the MediaPipe MobileNet V3 Small
    image embedder, and searches an in-memory FAISS index to rank images by
    cosine similarity against the target embedding.

    Signals:
        progress_update: Emitted with ``(current, total, message)`` progress.
        results_found: Emitted with the list of ``(path, similarity)`` results.
        finished: Emitted when the whole search has completed.
    """
    progress_update = Signal(int, int, str)
    results_found = Signal(list)  # List of (path, similarity)
    finished = Signal()

    def __init__(self, target_path, threshold, whitelist_str, blacklist_str,
                 visible_paths=None):
        """
        Initializes the FAISSSimilarSearchWorker.

        Args:
            target_path (str): Path of the image to find similar images for.
            threshold (int): Minimum similarity percentage (0-100) required
                for a result to be reported.
            whitelist_str (str): Comma separated list of allowed paths;
                defaults to the target's directory when empty.
            blacklist_str (str): Comma separated list of excluded paths.
            visible_paths (list, optional): When provided, only these paths are
                searched instead of walking the whitelist/blacklist folders.
                The original display order of the thumbnails is preserved.
        """
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

        # When the search scope is restricted to the displayed thumbnails,
        # keep the display order and drop duplicates while building a set for
        # fast containment checks during the search pipeline.
        self.visible_paths = []
        self.visible_paths_set = set()
        if visible_paths:
            seen = set()
            for path in visible_paths:
                abs_path = os.path.abspath(os.path.normpath(path))
                if abs_path not in seen:
                    seen.add(abs_path)
                    self.visible_paths.append(abs_path)
            self.visible_paths_set = seen

    def stop(self):
        """Requests the worker to abort and waits until it has finished."""
        self._is_running = False
        self.wait()

    def _is_allowed(self, path):
        """
        Checks whether a path passes the blacklist/whitelist rules.

        Blacklisted paths and their subtrees are always excluded; a path is
        allowed only if it equals or is contained in a whitelisted entry.

        Args:
            path (str): Path to check.

        Returns:
            bool: True if the path is allowed, False otherwise.
        """
        abs_p = os.path.abspath(os.path.normpath(path))
        for b in self.blacklist:
            if abs_p == b or abs_p.startswith(b + os.sep):
                return False
        for w in self.whitelist:
            if abs_p == w or abs_p.startswith(w + os.sep):
                return True
        return False

    def _get_all_images(self):
        """
        Collects all image files allowed under the whitelisted paths.

        When the search scope was restricted through ``visible_paths``, the
        folder walk is skipped and only those paths are collected (keeping
        the original display order); files that no longer exist on disk or do
        not have a supported image extension are skipped.

        Blacklisted subtrees are pruned in place during the directory walk;
        non-directory whitelist entries are included when they are images.

        Returns:
            list: Unique absolute paths of the allowed images.
        """
        if self.visible_paths:
            return [path for path in self.visible_paths
                    if os.path.isfile(path) and
                    os.path.splitext(path)[1].lower() in IMAGE_EXTENSIONS]

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
        """
        Opens (and creates if needed) the local embedding cache database.

        Returns:
            sqlite3.Connection: Connection to the embeddings cache.
        """
        return _open_embeddings_db()

    def _download_model_if_needed(self):
        """
        Downloads the MediaPipe embedder model when it is not yet cached.
        """
        _download_model_if_needed(self.progress_update.emit)

    def run(self):
        """
        Executes the similar-image search pipeline in the worker thread.

        The pipeline scans the filesystem for allowed images, evicts stale
        cache entries, embeds the new or modified images with the MediaPipe
        model, builds a FAISS inner-product index (GPU accelerated when an
        NVIDIA device is available) and emits the results whose similarity is
        above the configured threshold.
        """
        conn = None
        try:
            conn = _open_embeddings_db()
            cursor = conn.cursor()

            # 1. Scan filesystem for allowed images
            self.progress_update.emit(0, 0, "Scanning files...")
            disk_images = self._get_all_images()
            disk_images_set = set(disk_images)

            # Ensure target image is in the set to be indexed
            if os.path.exists(self.target_path) and self.target_path not in disk_images_set:
                disk_images.append(self.target_path)
                disk_images_set.add(self.target_path)

            # 2-5. Refresh the embedding cache (prunes stale entries and
            # generates vectors for new/modified images).
            _refresh_embeddings(
                conn, disk_images,
                progress_callback=lambda cur, total, msg:
                self.progress_update.emit(cur, total, msg),
                is_running_callback=lambda: self._is_running)

            # 6. Load the embeddings from DB to build FAISS index. When the
            # search is restricted to the displayed thumbnails, only the
            # entries belonging to that scope are taken into the index.
            cursor.execute("SELECT path, embedding FROM embeddings")
            all_db_records = cursor.fetchall()
            if self.visible_paths_set:
                all_db_records = [
                    record for record in all_db_records
                    if record[0] in self.visible_paths_set
                ]

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
                # Calculate query target embedding if not already cached.
                # The connection is not safe to share across threads, so the
                # helper reopens the cache on its own; the query vector is
                # still inserted by _refresh_embeddings above for new images.
                target_emb = _embed_single_image(self.target_path)

            results = []
            if target_emb is not None and embeddings_list:
                embeddings_np = np.vstack(embeddings_list).astype(np.float32)
                # Normalize just to be sure
                faiss.normalize_L2(embeddings_np)

                index = _build_faiss_index(embeddings_np)

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
