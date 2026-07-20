"""
Image Scanner Module for Bagheera Image Viewer.

This module handles asynchronous image discovery, thumbnail generation, and
persistent caching. It ensures the main application UI remains responsive by
offloading file I/O and image processing to background threads.

Key Features:
    - Asynchronous Scanning: Directory traversal and image loading in separate
    threads.
    - Two-Tier Caching:
        - In-Memory: LRU-based cache with safe concurrent access.
        - Disk: Persistent storage using LMDB (Lightning Memory-Mapped
          Database).
    - Incremental Loading: Batched image processing for memory efficiency.
    - Cache Maintenance: Automatic cleanup of invalid entries and size
      enforcement.
    - Improved Synchronization: Context managers, proper mutex handling, no
      deadlocks.
    - Better Path Handling: Uses pathlib for robust path operations.
    - Enhanced Error Handling: Detailed logging and recovery mechanisms.
"""
import os
import logging
import shlex
import shutil
import struct
import subprocess
import time
import argparse
import collections
from pathlib import Path
from contextlib import contextmanager
import lmdb
from PySide6.QtCore import (
    QObject, QThread, Signal, QMutex, QReadWriteLock, QSize, QSemaphore,
    QWaitCondition, QByteArray, QBuffer, QIODevice, Qt, QTimer, QRunnable,
    QThreadPool, QFile
)
from PySide6.QtGui import QImage, QImageReader, QImageIOHandler, QIcon
from PySide6.QtWidgets import QApplication

from .constants import (
    APP_CONFIG, CACHE_PATH, CACHE_MAX_SIZE, CACHE_MAX_RAM_BYTES,
    APP_DATA_DIR, MIN_FREE_RAM_PERCENT, DISK_CACHE_MAX_BYTES,
    HAVE_BAGHEERASEARCH_LIB, IMAGE_EXTENSIONS,
    SCANNER_SETTINGS_DEFAULTS, SEARCH_CMD, THUMBNAIL_SIZES,
    UITexts, METADATA_DB_NAME, DIRECTORY_DB_NAME
)

from .imageviewer import ImageViewer
from .metadatamanager import load_common_metadata

if HAVE_BAGHEERASEARCH_LIB:
    from bagheerasearch.core.search_lib.search import BagheeraSearcher

# Set up logging for better debugging
logger = logging.getLogger(__name__)

# Result structure for thumbnail retrieval to ensure API stability
ThumbnailResult = collections.namedtuple(
    'ThumbnailResult', ['image', 'mtime', 'tier'])
EMPTY_THUMBNAIL = ThumbnailResult(None, 0, 0)


class ThreadPoolManager:
    """Manages a global QThreadPool to dynamically adjust thread count."""
    def __init__(self):
        self.pool = QThreadPool()
        self.default_thread_count = APP_CONFIG.get(
            "generation_threads",
            SCANNER_SETTINGS_DEFAULTS.get("generation_threads", 4)
        )
        self.pool.setMaxThreadCount(self.default_thread_count)
        self.is_user_active = False
        logger.info(f"ThreadPoolManager initialized with "
                    f"{self.default_thread_count} threads.")

    def get_pool(self):
        """Returns the managed QThreadPool instance."""
        return self.pool

    def set_user_active(self, active):
        """
        Adjusts thread count based on user activity.

        Args:
            active (bool): True if the user is interacting with the UI.
        """
        if active == self.is_user_active:
            return
        self.is_user_active = active
        if active:
            # User is active, reduce threads to 1 to prioritize UI
            # responsiveness.
            self.pool.setMaxThreadCount(1)
            logger.debug("User is active, reducing thread pool to 1.")
        else:
            # User is idle, restore to default thread count.
            self.pool.setMaxThreadCount(self.default_thread_count)
            logger.debug(f"User is idle, restoring thread pool to "
                         f"{self.default_thread_count}.")

    def update_default_thread_count(self):
        """Updates the default thread count from application settings."""
        self.default_thread_count = APP_CONFIG.get(
            "generation_threads",
            SCANNER_SETTINGS_DEFAULTS.get("generation_threads", 4)
        )
        # Only apply if not in a user-active (low-thread) state.
        if not self.is_user_active:
            self.pool.setMaxThreadCount(self.default_thread_count)
        logger.info(f"Default thread count updated to "
                    f"{self.default_thread_count}.")


class ScannerWorker(QRunnable):
    """
    Worker to process a single image in a thread pool.
    Handles thumbnail retrieval/generation and metadata loading.
    """
    def __init__(self, cache, path, target_sizes=None, load_metadata=True, # Line 102
                 signal_emitter=None, semaphore=None, force_thumbnail_refresh=False):
        super().__init__()
        self.cache = cache
        self.path = path
        self.target_sizes = target_sizes
        self.load_metadata_flag = load_metadata
        self.emitter = signal_emitter
        self.semaphore = semaphore
        self.force_thumbnail_refresh = force_thumbnail_refresh
        self._is_cancelled = False
        # Result will be (path, thumb, mtime, tags, rating, inode, dev) or None
        self.result = None

    def shutdown(self):
        """Marks the worker as cancelled."""
        self._is_cancelled = True

    def run(self):
        from .constants import SCANNER_GENERATE_SIZES

        sizes_to_check = self.target_sizes if self.target_sizes is not None \
            else SCANNER_GENERATE_SIZES

        fd = None
        try:
            if self._is_cancelled:
                return

            # Optimize: Open file once to reuse FD for stat and xattrs
            fd = os.open(self.path, os.O_RDONLY)
            stat_res = os.fstat(fd)
            curr_mtime = stat_res.st_mtime
            curr_inode = stat_res.st_ino
            curr_dev = stat_res.st_dev

            tags, rating = [], 0

            # Attempt to get metadata from cache first to avoid xattr reads
            cached_tags, cached_rating, _ = self.cache.get_metadata(
                curr_dev, curr_inode, curr_mtime
            )
            metadata_cached = cached_tags is not None
            if metadata_cached:
                tags, rating = cached_tags, cached_rating

            smallest_thumb_for_signal = None
            min_size = min(sizes_to_check) if sizes_to_check else 0

            # Ensure required thumbnails exist
            for size in sizes_to_check:
                if self._is_cancelled:
                    return

                # Check if a valid thumbnail for this size exists
                res = self.cache.get_thumbnail(
                    self.path, size, curr_mtime=curr_mtime,
                    inode=curr_inode, device_id=curr_dev,
                    force_refresh=self.force_thumbnail_refresh)
                if not res.image or res.mtime != curr_mtime or res.tier != size:
                    # Use generation lock to prevent multiple threads generating
                    with self.cache.generation_lock(
                            self.path, size, curr_mtime,
                            curr_inode, curr_dev) as should_gen:
                        if self._is_cancelled:
                            return

                        if should_gen:
                            # I am the owner, I generate the thumbnail
                            new_thumb = generate_thumbnail(self.path, size, fd=fd)
                            if self._is_cancelled:
                                return
                            if new_thumb and not new_thumb.isNull():
                                self.cache.set_thumbnail(
                                    self.path, new_thumb, curr_mtime, size,
                                    inode=curr_inode, device_id=curr_dev, block=True)
                                if size == min_size:
                                    smallest_thumb_for_signal = new_thumb
                        else:
                            # Another thread generated it, re-fetch
                            if size == min_size:
                                re_res = self.cache.get_thumbnail(
                                    self.path, size, curr_mtime=curr_mtime,
                                    inode=curr_inode, device_id=curr_dev,
                                    async_load=False,
                                    force_refresh=self.force_thumbnail_refresh)
                                smallest_thumb_for_signal = re_res.image
                elif size == min_size:
                    # valid thumb exists, use it for signal
                    smallest_thumb_for_signal = res.image

            if not metadata_cached and self.load_metadata_flag:
                res_meta = load_common_metadata(fd)
                tags, rating = res_meta.tags, res_meta.rating
                # Update metadata cache for fast future rescans
                self.cache.set_metadata(curr_dev, curr_inode, curr_mtime,
                                        tags, rating, self.path)

            self.result = (self.path, smallest_thumb_for_signal,
                           curr_mtime, tags, rating, curr_inode, curr_dev)
        except (FileNotFoundError, PermissionError) as e:
            logger.debug(f"Skipping {self.path} due to access issue: {e}")
            self.result = None
        except Exception as e:
            logger.warning(f"Unexpected error processing image {self.path}: {e}")
            self.result = None
        finally:
            if fd is not None:
                try:
                    os.close(fd)
                except OSError:
                    pass
            if self.emitter:
                self.emitter.emit_progress()
            if self.semaphore:
                self.semaphore.release()


def generate_thumbnail(path, size, fd=None):
    """Generates a QImage thumbnail for a given path and size."""
    try:
        qfile = None
        if fd is not None:
            try:
                # Ensure we are at the beginning of the file
                os.lseek(fd, 0, os.SEEK_SET)
                qfile = QFile()
                if qfile.open(fd, QIODevice.ReadOnly, QFile.DontCloseHandle):
                    reader = QImageReader(qfile)
                else:
                    qfile = None
                    reader = QImageReader(path)
            except OSError:
                reader = QImageReader(path)
        else:
            reader = QImageReader(path)

        # Optimization: Instruct the image decoder to scale while reading.
        # This drastically reduces memory usage and CPU time for large images
        # (e.g. JPEG).
        if reader.supportsOption(QImageIOHandler.ImageOption.ScaledSize):
            orig_size = reader.size()
            if orig_size.isValid() \
               and (orig_size.width() > size or orig_size.height() > size):
                target_size = QSize(orig_size)
                target_size.scale(size, size, Qt.KeepAspectRatio)
                reader.setScaledSize(target_size)

        reader.setAutoTransform(True)
        img = reader.read()

        logger.debug(f"QImageReader.read() result for {path}: {img.isNull()}")
        # Fallback: If optimization failed (and it wasn't just a missing file),
        # try standard read
        if img.isNull():
            error = reader.error()
            # Optimize: Don't retry for AppleDouble files (._*) if UnknownError
            if os.path.basename(path).startswith("._") and \
               error == QImageReader.ImageReaderError.UnknownError:
                return None

            if error != QImageReader.ImageReaderError.FileNotFoundError:
                reader = QImageReader(path)
                reader.setAutoTransform(True)
                logger.debug(f"Retrying QImageReader.read() for {path}")
                img = reader.read()

        if img.isNull():
            return None
        # Always scale to the target size. Qt.KeepAspectRatio will handle
        # both upscaling and downscaling correctly. SmoothTransformation gives
        # better quality for upscaling.
        return img.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    except Exception as e:
        logger.debug(f"Could not generate thumbnail for {path}: {e}")
        return None


class CacheWriter(QThread):
    """
    Dedicated background thread for writing thumbnails to LMDB asynchronously.
    Batches writes to improve disk throughput and avoid blocking the scanner.
    """
    def __init__(self, cache):
        super().__init__()
        self.cache = cache
        # Use deque for flexible buffer management and deduplication
        self._queue = collections.deque()
        self._mutex = QMutex()
        self._condition_new_data = QWaitCondition()
        self._condition_space_available = QWaitCondition()
        # Soft limit for blocking producers (background threads)
        self.setObjectName("CacheWriterThread")  # Add this line
        self._max_size = 50
        self._running = True

    def enqueue(self, item, block=False):
        """Queue an item for writing. Item: (device_id, inode_key, img, mtime, size,
        path)"""
        if not self._running:
            return

        self._mutex.lock()
        try:
            if block:
                # Backpressure for background threads (Scanner/Generator)
                while len(self._queue) >= self._max_size and self._running:
                    self._condition_space_available.wait(self._mutex)

                if not self._running:
                    return

            # Ensure we don't accept new items if stopping, especially when block=False
            if not self._running:
                return

            # --- Soft Cleaning: Deduplication ---
            # Remove redundant pending updates for the same image/size (e.g.
            # rapid rotations)
            if len(item) >= 5:
                new_dev, new_inode, _, _, new_size = item[:5]
                if self._queue:
                    # Rebuild deque excluding any item that matches the new one's key
                    self._queue = collections.deque(
                        q for q in self._queue
                        if not (len(q) >= 5 and
                                q[0] == new_dev and
                                q[1] == new_inode and
                                q[4] == new_size)
                    )

            # Always append the new item (it becomes the authoritative version)
            self._queue.append(item)
            self._condition_new_data.wakeOne()
        finally:
            self._mutex.unlock()

    def stop(self):
        self._mutex.lock()
        self._running = False
        # Do not clear the queue here; let the run loop drain it to prevent data loss.
        self._condition_new_data.wakeAll()
        logger.debug(f"{self.objectName()} stop requested, waking all.")
        self._condition_space_available.wakeAll()
        self._mutex.unlock()

    def run(self):
        self.setPriority(QThread.IdlePriority)
        while self._running or self._queue:
            self._mutex.lock()
            if not self._queue:
                if not self._running:
                    self._mutex.unlock()
                    break
                # Wait for new items
                self._condition_new_data.wait(self._mutex)

            # Auto-flush: if queue has data but not enough for a full batch,
            # wait up to 200ms for more data. If timeout, flush what we have.
            # Only wait if running (flush immediately on stop)
            if self._running and self._queue and len(self._queue) < 50:
                signaled = self._condition_new_data.wait(self._mutex, 200)
                if signaled and self._running and len(self._queue) < 50:
                    self._mutex.unlock()
                    continue

            if not self._queue:
                self._mutex.unlock()
                continue

            # Gather a batch of items
            # Adaptive batch size: if queue is backing up, increase transaction size
            # to improve throughput.
            # Respect max size even during shutdown to avoid OOM or huge transactions
            batch_limit = self._max_size

            batch = []
            while self._queue and len(batch) < batch_limit:
                batch.append(self._queue.popleft())

            # Notify producers that space might be available
            self._condition_space_available.wakeAll()
            self._mutex.unlock()

            if batch:
                try:
                    self.cache._batch_write_to_lmdb(batch)
                except Exception as e:
                    logger.error(f"CacheWriter batch write error: {e}")
        logger.debug(f"{self.objectName()} run method exiting.")


class CacheLoader(QThread):
    """
    Background thread to load and decode thumbnails from LMDB without blocking UI.
    Uses LIFO queue (deque) to prioritize most recently requested images.
    Implements a "drop-oldest" policy when full to ensure new requests (visible images)
    are prioritized over old pending ones (scrolled away).
    """
    def __init__(self, cache):
        super().__init__()
        self.cache = cache
        # Use deque for LIFO behavior with drop-oldest capability
        self._queue = collections.deque()
        self._max_size = 50
        self._mutex = QMutex()
        self._condition = QWaitCondition()
        self._running = True

    def enqueue(self, item):
        if not self._running:
            return False, None

        dropped_item = None
        self._mutex.lock()
        try:
            # If queue is full, drop the OLDEST item (left) to make room for NEWEST
            # (right).
            # This ensures that during fast scrolling, we process what is currently
            # on screen (just added) rather than what was on screen moments ago.
            while len(self._queue) >= self._max_size:
                # Drop oldest and return it so caller can cleanup state
                dropped = self._queue.popleft()
                dropped_item = (dropped[0], dropped[1])  # path, size

            self._queue.append(item)
            self._condition.wakeOne()
            return True, dropped_item
        finally:
            self._mutex.unlock()

    def promote(self, path, size):
        """Moves an item to the front of the line (end of deque) if exists."""
        if not self._running:
            return

        self._mutex.lock()
        try:
            # Find item by path and size
            for item in self._queue:
                if item[0] == path and item[1] == size:
                    # Move to right end (LIFO pop side - highest priority)
                    self._queue.remove(item)
                    self._queue.append(item)
                    break
        finally:
            self._mutex.unlock()

    def stop(self):
        self._running = False
        self._mutex.lock()
        self._condition.wakeAll()
        self._mutex.unlock()

    def run(self):
        self.setPriority(QThread.IdlePriority)
        while self._running:
            self._mutex.lock()
            if not self._queue:
                # Wait up to 100ms for new items
                self._condition.wait(self._mutex, 100)

            if not self._queue:
                self._mutex.unlock()
                continue

            # LIFO: Pop from right (newest)
            item = self._queue.pop()
            self._mutex.unlock()

            path, size, mtime, inode, dev = item

            # Call synchronous get_thumbnail to fetch and decode
            # This puts the result into the RAM cache
            res = self.cache.get_thumbnail(
                path, size, curr_mtime=mtime, inode=inode,
                device_id=dev, async_load=False
            )

            if res.image:
                self.cache.thumbnail_loaded.emit(path, size)

            self.cache._mark_load_complete(path, size)


class GenerationFuture:
    """Helper class to synchronize threads waiting for a thumbnail."""
    def __init__(self):
        self._mutex = QMutex()
        self._condition = QWaitCondition()
        self._finished = False

    def wait(self):
        self._mutex.lock()
        while not self._finished:
            self._condition.wait(self._mutex)
        self._mutex.unlock()

    def complete(self):
        self._mutex.lock()
        self._finished = True
        self._condition.wakeAll()
        self._mutex.unlock()


class ThumbnailCache(QObject):
    """
    Thread-safe in-memory thumbnail cache with LMDB disk persistence.

    Optimization: Uses (device, inode) as LMDB key instead of file paths.
    This gives:
    - Smaller keys (16 bytes vs variable path length)
    - Faster lookups and LMDB operations
    - Automatic handling of file moves/renames
    - Better cache efficiency
    """

    thumbnail_loaded = Signal(str, int)  # path, size

    def __init__(self):
        super().__init__()
        # In-memory cache: {path: {size: (QImage, mtime)}}
        self._thumbnail_cache = {}
        # Path -> (device, inode) mapping for fast lookup
        self._path_to_inode = {}
        self._loading_set = set()  # Track pending async loads (path, size)
        self._futures = {}  # Map (dev, inode, size) -> GenerationFuture
        self._futures_lock = QMutex()
        self._cache_lock = QReadWriteLock()
        self._db_lock = QMutex()  # Lock specifically for _db_handles access
        self._db_handles = {}  # Cache for LMDB database handles (dbi)
        self._cancel_loading = False
        self._metadata_db = None
        self._directory_db = None
        self._broken_cache = {}  # (dev, inode, size) -> (mtime, error_msg)
        self._cache_bytes_size = 0
        self._cache_writer = None
        self._cache_loader = None

        # Pre-generate broken images for standard tiers in the main thread
        self._broken_images = {}
        for size in THUMBNAIL_SIZES:
            icon = QIcon.fromTheme("image-missing",
                                   QIcon.fromTheme("broken-image",
                                                   QIcon.fromTheme("dialog-error")))
            self._broken_images[size] = icon.pixmap(size, size).toImage()

        self.lmdb_open()

    def lmdb_open(self):
        # Initialize LMDB environment
        cache_dir = Path(APP_DATA_DIR)
        cache_dir.mkdir(parents=True, exist_ok=True)

        try:
            # map_size: 1024MB max database size
            # max_dbs: 512 named databases (one per device + main DB)
            self._lmdb_env = lmdb.open(
                CACHE_PATH,
                map_size=DISK_CACHE_MAX_BYTES,
                max_dbs=512,
                readonly=False,
                create=True
            )
            logger.info(f"LMDB cache opened: {CACHE_PATH}")
            self._metadata_db = self._lmdb_env.open_db(METADATA_DB_NAME, create=True)
            self._directory_db = self._lmdb_env.open_db(DIRECTORY_DB_NAME, create=True)

            # Start the async writer thread
            self._cache_writer = CacheWriter(self)
            self._cache_writer.start()

            # Start the async loader thread
            self._cache_loader = CacheLoader(self)
            self._cache_loader.start()

        except Exception as e:
            logger.error(f"Failed to open LMDB cache: {e}")
            self._lmdb_env = None

    def lmdb_close(self):
        # Stop and wait for worker threads to ensure they are not accessing
        # the LMDB environment while it's being closed.
        if hasattr(self, '_cache_writer') and self._cache_writer:
            self._cache_writer.stop()
            while self._cache_writer.isRunning():
                if QApplication.instance():  # Check if QApplication is still valid
                    QApplication.processEvents()  # Keep UI responsive
                QThread.msleep(50)
            self._cache_writer = None

        if hasattr(self, '_cache_loader') and self._cache_loader:
            self._cache_loader.stop()
            while self._cache_loader.isRunning():
                if QApplication.instance():  # Check if QApplication is still valid
                    QApplication.processEvents()  # Keep UI responsive
                QThread.msleep(50)
            self._cache_loader = None
        self._loading_set.clear()
        self._futures.clear()

        self._metadata_db = None
        self._directory_db = None
        self._db_handles.clear()
        if hasattr(self, '_lmdb_env') and self._lmdb_env:
            self._lmdb_env.close()
            self._lmdb_env = None

    def __del__(self):
        self.lmdb_close()

    @staticmethod
    def _get_inode_key(path):
        """Get inode (8 bytes) for a file path."""
        try:
            stat_info = os.stat(path)
            # Pack inode as uint64 (8 bytes)
            return struct.pack('Q', stat_info.st_ino)
        except (OSError, AttributeError):
            return None

    @staticmethod
    def _get_device_id(path):
        """Get device ID for a file path."""
        try:
            stat_info = os.stat(path)
            return stat_info.st_dev
        except OSError:
            return 0

    def _get_device_db(self, device_id, size, write=False, txn=None):
        """Get or create a named database for the given device."""
        env = self._lmdb_env
        if not env:
            return None

        db_name = f"dev_{device_id}_{size}".encode('utf-8')

        # Protect access to _db_handles which is not thread-safe by default
        self._db_lock.lock()
        try:
            # Return cached handle if available
            if db_name in self._db_handles:
                return self._db_handles[db_name]

            # Not in cache, try to open/create
            db = env.open_db(db_name, create=write, integerkey=False, txn=txn)
            self._db_handles[db_name] = db
            return db

        except lmdb.NotFoundError:
            # Expected when reading from non-existent DB (cache miss)
            return None
        except Exception as e:
            logger.error(f"Error opening device DB for dev {device_id} "
                         f"size {size}: {e}")
            return None
        finally:
            self._db_lock.unlock()

    def get_metadata(self, dev_id, inode, mtime):
        """Retrieves cached metadata (tags, rating) using dev/inode."""
        if not self._lmdb_env or not self._metadata_db:
            return None, 0, None

        inode_key = struct.pack('Q', inode) if isinstance(inode, int) else inode
        lmdb_key = f"{dev_id}-{inode_key.hex()}".encode('utf-8')

        try:
            with self._lmdb_env.begin(db=self._metadata_db, write=False) as txn:
                val = txn.get(lmdb_key)
                if val and len(val) >= 13:
                    stored_mtime = struct.unpack('d', val[:8])[0]
                    if abs(stored_mtime - mtime) < 0.001: # Epsilon check
                        rating = int(val[8])
                        path_len = struct.unpack('I', val[9:13])[0]
                        path = val[13:13+path_len].decode('utf-8')
                        tags_str = val[13+path_len:].decode('utf-8')
                        tags = [t for t in tags_str.split('\0') if t]
                        return tags, rating, path
        except Exception:
            pass
        return None, 0, None

    def set_metadata(self, dev_id, inode, mtime, tags, rating, path):
        """Queues a metadata update for the cache."""
        if not self._cache_writer:
            return
        inode_key = struct.pack('Q', inode) if isinstance(inode, int) else inode
        # Use Marker -1 for metadata
        self._cache_writer.enqueue(
            (dev_id, inode_key, None, mtime, -1, None, (tags, rating, path)),
            block=False)

    def get_directory_cache(self, path):
        """Retrieves the cached file list for a directory."""
        if not self._lmdb_env or not self._directory_db:
            return 0, []
        try:
            with self._lmdb_env.begin(db=self._directory_db, write=False) as txn:
                val = txn.get(path.encode('utf-8'))
                if val and len(val) >= 8:
                    mtime = struct.unpack('d', val[:8])[0]
                    files = val[8:].decode('utf-8').split('\0')
                    return mtime, [f for f in files if f]
        except Exception:
            pass
        return 0, []

    def set_directory_cache(self, path, mtime, file_list):
        """Stores the file listing for a directory."""
        if not self._lmdb_env or not self._directory_db:
            return
        val = struct.pack('d', mtime) + '\0'.join(file_list).encode('utf-8')
        try:
            with self._lmdb_env.begin(db=self._directory_db, write=True) as txn:
                txn.put(path.encode('utf-8'), val)
        except Exception:
            pass

    def invalidate_directory_cache(self, path):
        """Removes the file list cache for a specific directory from disk."""
        if not self._lmdb_env or not self._directory_db:
            return
        try:
            with self._lmdb_env.begin(db=self._directory_db, write=True) as txn:
                txn.delete(path.encode('utf-8'))
        except lmdb.Error:
            pass

    @contextmanager
    def _write_lock(self):
        """Context manager for write-safe access to cache."""
        self._cache_lock.lockForWrite()
        try:
            yield
        finally:
            self._cache_lock.unlock()

    @contextmanager
    def _read_lock(self):
        """Context manager for read-safe access to cache."""
        self._cache_lock.lockForRead()
        try:
            yield
        finally:
            self._cache_lock.unlock()

    def _ensure_cache_limit(self):
        """Enforces cache size limit and reacts to system memory pressure.
        Must be called with a write lock held."""

        # 1. Enforce internal limits using tiered strategy
        while len(self._thumbnail_cache) > 0 and (
                len(self._thumbnail_cache) >= CACHE_MAX_SIZE or
                self._cache_bytes_size > CACHE_MAX_RAM_BYTES):
            self._evict_tiered()

        # Check system-wide memory pressure (Low RAM fallback)
        try:
            import psutil
            mem = psutil.virtual_memory()
            if (mem.available / mem.total) * 100 < MIN_FREE_RAM_PERCENT:
                logger.warning(f"Low system memory detected "
                               f"(< {MIN_FREE_RAM_PERCENT}%). "
                               f"Applying aggressive tiered pruning.")

                # Strategy: first clear ALL cached high-res tiers to free space quickly
                # while keeping the 128px grid thumbnails intact.
                for tier in [512, 256]:
                    self._prune_tier(tier)

                    # Re-check if pressure relieved
                    mem = psutil.virtual_memory()
                    if (mem.available / mem.total) * 100 >= MIN_FREE_RAM_PERCENT:
                        return

                # If still under pressure, remove oldest 10% of remaining entries
                items_to_prune = max(1, len(self._thumbnail_cache) // 10)
                for _ in range(items_to_prune):
                    if not self._thumbnail_cache:
                        break
                    self._evict_oldest_path_entirely()
        except (ImportError, Exception):
            pass

    def _evict_tiered(self):
        """
        Removes content from cache targeting larger tiers first from the oldest entries.
        Must be called with write lock held.
        """
        # We check the oldest 100 entries for large tiers to avoid O(N) scans
        # on every call while still being very effective for LRU behavior.
        check_limit = 100
        for tier in [512, 256]:
            count = 0
            for path, sizes in self._thumbnail_cache.items():
                if tier in sizes:
                    img, _ = sizes.pop(tier)
                    if img:
                        self._cache_bytes_size -= img.sizeInBytes()
                    return
                count += 1
                if count >= check_limit:
                    break

        self._evict_oldest_path_entirely()

    def _prune_tier(self, tier):
        """Removes all thumbnails of a specific tier from cache to free RAM quickly."""
        for path, sizes in self._thumbnail_cache.items():
            if tier in sizes:
                img, _ = sizes.pop(tier)
                if img:
                    self._cache_bytes_size -= img.sizeInBytes()

    def _evict_oldest_path_entirely(self):
        """Removes the oldest cache entry completely. Must be called with write lock."""
        oldest_path = next(iter(self._thumbnail_cache))
        cached_sizes = self._thumbnail_cache.pop(oldest_path)
        for img, _ in cached_sizes.values():
            if img:
                self._cache_bytes_size -= img.sizeInBytes()
        self._path_to_inode.pop(oldest_path, None)

    def clean_stale_metadata(self, stop_check=None):
        """
        Removes metadata entries from the database for files that no longer exist.
        """
        if not self._lmdb_env or not self._metadata_db:
            return 0

        removed_count = 0
        keys_to_delete = []

        with self._lmdb_env.begin(db=self._metadata_db, write=False) as txn:
            cursor = txn.cursor()
            for key, value in cursor:
                if stop_check and stop_check():
                    return removed_count
                if len(value) < 13:
                    keys_to_delete.append(key)
                    continue
                try:
                    # Value format: mtime(8) + rating(1) + path_len(4) + path + tags
                    path_len = struct.unpack('I', value[9:13])[0]
                    path = value[13:13+path_len].decode('utf-8')

                    if not os.path.exists(path):
                        keys_to_delete.append(key)
                except Exception:
                    keys_to_delete.append(key)  # Corrupted entry

        if keys_to_delete:
            with self._lmdb_env.begin(db=self._metadata_db, write=True) as txn:
                for key in keys_to_delete:
                    txn.delete(key)
                    removed_count += 1
            logger.info(f"Cleaned up {removed_count} stale metadata entries.")
        return removed_count

    def clean_stale_directories(self, stop_check=None):
        """
        Removes directory cache entries for directories that no longer exist.
        """
        if not self._lmdb_env or not self._directory_db:
            return 0

        removed_count = 0
        keys_to_delete = []

        with self._lmdb_env.begin(db=self._directory_db, write=False) as txn:
            cursor = txn.cursor()
            for key, value in cursor:
                if stop_check and stop_check():
                    return removed_count
                if len(value) < 8:
                    keys_to_delete.append(key)
                    continue
                path = key.decode('utf-8')
                if not os.path.isdir(path):
                    keys_to_delete.append(key)

        if keys_to_delete:
            with self._lmdb_env.begin(db=self._directory_db, write=True) as txn:
                for key in keys_to_delete:
                    txn.delete(key)
                    removed_count += 1
            logger.info(f"Cleaned up {removed_count} stale directory cache entries.")
        return removed_count

    def _get_tier_for_size(self, requested_size):
        """Determines the ideal thumbnail tier based on the requested size."""
        if requested_size <= 128:
            return 128
        if requested_size <= 256:
            return 256
        return 512

    def mark_broken(self, path, size, mtime, inode, dev_id, error_msg):
        """Marks a thumbnail load as failed with a message."""
        key = (dev_id, struct.pack('Q', inode) if inode is not None else None, size)
        with self._write_lock():
            self._broken_cache[key] = (mtime, error_msg)

    def get_broken_info(self, path, size, mtime, inode, dev_id):
        """Returns the error message if a thumbnail is known to have failed, else
        None."""
        key = (dev_id, struct.pack('Q', inode) if inode is not None else None, size)
        with self._read_lock():
            info = self._broken_cache.get(key)
            if info and info[0] == mtime:
                return info[1]
            return None

    def _resolve_file_identity(self, path, curr_mtime, inode, device_id):
        """Helper to resolve file mtime, device, and inode."""
        mtime = curr_mtime
        dev_id = device_id if device_id is not None else 0
        inode_key = struct.pack('Q', inode) if inode is not None else None

        if mtime is None or dev_id == 0 or not inode_key:
            try:
                stat_res = os.stat(path)
                mtime = stat_res.st_mtime
                dev_id = stat_res.st_dev
                inode_key = struct.pack('Q', stat_res.st_ino)
            except OSError:
                return None, 0, None

        return mtime, dev_id, inode_key

    def _queue_async_load(self, path, size, mtime, dev_id, inode_key):
        """Helper to queue async load."""
        with self._write_lock():
            if (path, size) in self._loading_set:
                # If already queued, promote to process sooner (LIFO)
                if self._cache_loader:
                    self._cache_loader.promote(path, size)
                return

            if not self._cache_loader:
                return

            inode_int = struct.unpack('Q', inode_key)[0] if inode_key else 0

            # Optimistically add to set
            self._loading_set.add((path, size))
            success, dropped = self._cache_loader.enqueue(
                (path, size, mtime, inode_int, dev_id))

            if dropped:
                self._loading_set.discard(dropped)
            elif not success:
                self._loading_set.discard((path, size))

    def _check_disk_cache(self, path, search_order, mtime, dev_id, inode_key):
        """Helper to check LMDB synchronously."""
        if not self._lmdb_env or not inode_key or dev_id == 0:
            return EMPTY_THUMBNAIL

        txn = None
        try:
            txn = self._lmdb_env.begin(write=False)
            for size in search_order:
                db = self._get_device_db(dev_id, size, write=False, txn=txn)
                if not db:
                    continue

                value_bytes = txn.get(inode_key, db=db)
                if value_bytes and len(value_bytes) > 8:
                    stored_mtime = struct.unpack('d', value_bytes[:8])[0]
                    if abs(stored_mtime - mtime) > 0.001: # Epsilon check
                        continue

                    payload = value_bytes[8:]
                    if len(payload) > 4 and payload.startswith(b'PTH\0'):
                        path_len = struct.unpack('I', payload[4:8])[0]
                        img_data = payload[8 + path_len:]
                    else:
                        img_data = payload

                    img = QImage()
                    if img.loadFromData(img_data, "PNG"):
                        with self._write_lock():
                            if path not in self._thumbnail_cache:
                                self._ensure_cache_limit()
                                self._thumbnail_cache[path] = {}
                            self._thumbnail_cache[path][size] = (img, mtime)
                            self._cache_bytes_size += img.sizeInBytes()
                            self._path_to_inode[path] = (dev_id, inode_key)
                        return ThumbnailResult(img, mtime, size)
        except Exception as e:
            logger.debug(f"Cache lookup error for {path}: {e}")
        finally:
            if txn:
                txn.abort()

        return EMPTY_THUMBNAIL

    def get_available_tier(self, path, requested_size, mtime):
        """Returns the best available tier in memory for the given path."""
        target_tier = self._get_tier_for_size(requested_size)
        with self._read_lock():
            cached_sizes = self._thumbnail_cache.get(path)
            if not cached_sizes:
                return 0
            if target_tier in cached_sizes:
                img, cached_mtime = cached_sizes[target_tier]
                if img and not img.isNull() and cached_mtime == mtime:
                    return target_tier
            for size in THUMBNAIL_SIZES:
                if size in cached_sizes:
                    img, cached_mtime = cached_sizes[size]
                    if img and not img.isNull() and cached_mtime == mtime:
                        return size
        return 0

    def get_thumbnail(self, path, requested_size, curr_mtime=None,
                      inode=None, device_id=None, async_load=False,
                      force_refresh=False):
        """
        Safely retrieve a thumbnail from cache, finding the best available size.
        Returns: ThumbnailResult object.
        """
        target_tier = self._get_tier_for_size(requested_size)
        search_order = [target_tier] + \
            sorted([s for s in THUMBNAIL_SIZES if s > target_tier]) + \
            sorted([s for s in THUMBNAIL_SIZES if s < target_tier], reverse=True)

        mtime, dev_id, inode_key = self._resolve_file_identity(
            path, curr_mtime, inode, device_id)

        if mtime is None:
            return EMPTY_THUMBNAIL

        # If force_refresh is True, invalidate existing cache entries for this path
        # and force regeneration.
        if force_refresh:
            logger.debug(f"Forcing refresh for {path}: invalidating cache entries.")
            with self._write_lock():
                if path in self._thumbnail_cache:
                    cached_sizes = self._thumbnail_cache.pop(path)
                    for img, _ in cached_sizes.values():
                        if img:
                            self._cache_bytes_size -= img.sizeInBytes()
                self._path_to_inode.pop(path, None) # Also remove from inode map
            self._delete_from_lmdb(path, device_id=dev_id, inode_key=inode_key)
            return EMPTY_THUMBNAIL # Signal that it's not in cache, forcing generation

        # Check if known to be broken
        broken_msg = self.get_broken_info(path, target_tier, mtime, inode, device_id)
        if broken_msg:
            return ThumbnailResult(
                self._broken_images.get(target_tier), mtime, target_tier)

        best_img, best_mtime, best_tier = None, 0, 0

        with self._read_lock():
            cached_sizes = self._thumbnail_cache.get(path)
            if cached_sizes:
                for size in search_order:
                    if size in cached_sizes:
                        img, cached_mtime = cached_sizes[size]
                        if img and not img.isNull() and abs(cached_mtime - mtime) < 0.001:
                            if size == target_tier:
                                return ThumbnailResult(img, mtime, size)
                            if not best_img:
                                best_img, best_mtime, best_tier = img, mtime, size

        if async_load:
            self._queue_async_load(path, target_tier, mtime, dev_id, inode_key)
            return ThumbnailResult(best_img, best_mtime, best_tier)

        res = self._check_disk_cache(path, [target_tier], mtime, dev_id, inode_key)
        if res.image:
            return res
        if best_img:
            return ThumbnailResult(best_img, best_mtime, best_tier)
        other_tiers = [s for s in search_order if s != target_tier]
        return self._check_disk_cache(path, other_tiers, mtime, dev_id, inode_key)

    def _mark_load_complete(self, path, size):
        """Remove item from pending loading set."""
        with self._write_lock():
            # Uncomment to trace individual completions:
            # logger.debug(f"Load complete: {path}")
            self._loading_set.discard((path, size))

    def set_thumbnail(self, path, img, mtime, size, inode=None, device_id=None,
                      block=False):
        """Safely store a thumbnail of a specific size in cache."""
        if not img or img.isNull() or size not in THUMBNAIL_SIZES:
            return False

        img_size = img.sizeInBytes()

        if inode is not None and device_id is not None:
            dev_id = device_id
            inode_key = struct.pack('Q', inode)
        else:
            dev_id = self._get_device_id(path)
            inode_key = self._get_inode_key(path)

        if not inode_key or dev_id == 0:
            return False

        with self._write_lock():
            if path not in self._thumbnail_cache:
                self._ensure_cache_limit()
                self._thumbnail_cache[path] = {}
            else:
                # Move to end to mark as recently used (LRU behavior)
                # We pop and re-insert the existing entry
                entry = self._thumbnail_cache.pop(path)
                self._thumbnail_cache[path] = entry

            # If replacing, subtract old size
            if size in self._thumbnail_cache.get(path, {}):
                old_img, _ = self._thumbnail_cache[path][size]
                if old_img:
                    self._cache_bytes_size -= old_img.sizeInBytes()

            self._thumbnail_cache[path][size] = (img, mtime)
            self._path_to_inode[path] = (dev_id, inode_key)
            self._cache_bytes_size += img_size

        # Enqueue asynchronous write to LMDB
        if self._cache_writer:
            self._cache_writer.enqueue(
                (dev_id, inode_key, img, mtime, size, path), block=block)
        self.thumbnail_loaded.emit(path, size)
        return True

    def invalidate_path(self, path):
        """Removes all cached data for a specific path from memory and disk."""
        inode_info = None
        with self._write_lock():
            if path in self._thumbnail_cache:
                cached_sizes = self._thumbnail_cache.pop(path)
                for img, _ in cached_sizes.values():
                    if img:
                        self._cache_bytes_size -= img.sizeInBytes()
            inode_info = self._path_to_inode.pop(path, None)

        device_id, inode_key = inode_info if inode_info else (None, None)
        self._delete_from_lmdb(path, device_id=device_id, inode_key=inode_key)

    def remove_if_missing(self, paths_to_check):
        """Remove cache entries for files that no longer exist on disk."""
        to_remove = []

        with self._read_lock():
            cached_paths = list(self._thumbnail_cache.keys())

        for path in cached_paths:
            if not os.path.exists(path):
                to_remove.append(path)

        if to_remove:
            entries_to_delete = []
            with self._write_lock():
                for path in to_remove:
                    if path in self._thumbnail_cache:
                        cached_sizes = self._thumbnail_cache.pop(path)
                        for img, _ in cached_sizes.values():
                            if img:
                                self._cache_bytes_size -= img.sizeInBytes()
                    inode_info = self._path_to_inode.pop(path, None)
                    entries_to_delete.append((path, inode_info))
            # Delete from LMDB outside the lock
            for path, inode_info in entries_to_delete:
                device_id, inode_key = inode_info if inode_info else (None, None)
                self._delete_from_lmdb(path, device_id=device_id, inode_key=inode_key)
            logger.info(f"Removed {len(to_remove)} missing entries from cache")

        return len(to_remove)

    def clean_orphans(self, stop_check=None):
        """
        Scans the LMDB database for entries where the original file no longer exists.
        This is a heavy operation and should be run in a background thread.
        """
        if not self._lmdb_env:
            return 0

        orphans_removed = 0

        # 1. Get all named databases (one per device/size)
        db_names = []
        try:
            with self._lmdb_env.begin(write=False) as txn:
                cursor = txn.cursor()
                for key, _ in cursor:
                    if key.startswith(b'dev_'):
                        db_names.append(key)
        except Exception as e:
            logger.error(f"Error listing DBs: {e}")
            return 0

        # 2. Iterate each DB and check paths
        for db_name in db_names:
            if stop_check and stop_check():
                return orphans_removed

            try:
                # Parse device ID from name "dev_{id}_{size}"
                parts = db_name.decode('utf-8').split('_')
                if len(parts) >= 3:
                    db_dev = int(parts[1])
                else:
                    db_dev = 0

                # Parse device ID from name "dev_{id}_{size}"
                # We open the DB to scan its keys
                with self._lmdb_env.begin(write=True) as txn:
                    db = self._lmdb_env.open_db(db_name, txn=txn, create=False)
                    cursor = txn.cursor(db=db)
                    for key, value in cursor:
                        if stop_check and stop_check():
                            return orphans_removed

                        if len(value) > 12 and value[8:12] == b'PTH\0':
                            path_len = struct.unpack('I', value[12:16])[0]
                            path_bytes = value[16:16+path_len]
                            path = path_bytes.decode('utf-8', errors='ignore')

                            should_delete = False
                            try:
                                st = os.stat(path)
                                key_inode = struct.unpack('Q', key)[0]
                                if st.st_dev != db_dev or st.st_ino != key_inode:
                                    should_delete = True
                            except OSError:
                                should_delete = True

                            if should_delete:
                                cursor.delete()
                                orphans_removed += 1
            except Exception as e:
                logger.error(f"Error cleaning DB {db_name}: {e}")

        return orphans_removed

    def clear_cache(self):
        """Clear both in-memory and LMDB cache."""
        with self._write_lock():
            self._thumbnail_cache.clear()
            self._path_to_inode.clear()
            self._cache_bytes_size = 0

        self.lmdb_close()
        try:
            if os.path.exists(CACHE_PATH):
                shutil.rmtree(CACHE_PATH)
            self.lmdb_open()
            logger.info("LMDB cache cleared by removing directory.")
        except Exception as e:
            logger.error(f"Error clearing LMDB by removing directory: {e}")

    def _batch_write_to_lmdb(self, batch):
        """Write a batch of thumbnails to LMDB in a single transaction."""
        env = self._lmdb_env
        if not env or not batch:
            return

        data_to_write = []
        meta_to_write = []
        dirs_to_write = []

        # 1. Prepare data (image encoding) outside the transaction lock
        # This is CPU intensive, better done without holding the DB lock if possible,
        # though LMDB write lock mostly blocks other writers.
        for item in batch:
            if len(item) >= 7 and item[4] == -1:  # Metadata Marker
                dev_id, inode_key, _, mtime, _, _, (tags, rating, path) = item
                lmdb_key = f"{dev_id}-{inode_key}".encode('utf-8')
                tags_str = "\0".join(tags)
                path_bytes = path.encode('utf-8')
                val = struct.pack('d', mtime) + bytes([int(rating)]) + \
                    struct.pack('I', len(path_bytes)) + path_bytes + tags_str.encode('utf-8')
                meta_to_write.append((lmdb_key, val))
                continue
            if len(item) >= 5 and item[4] == -2:  # Directory Marker
                _, path_key, _, mtime, _, _, file_list = item
                paths_str = "\0".join(file_list)
                val = struct.pack('d', mtime) + paths_str.encode('utf-8')
                dirs_to_write.append((path_key, val))
                continue

            # Small sleep to yield GIL/CPU to UI thread during heavy batch encoding
            QThread.msleep(1)

            if len(item) >= 6:
                device_id, inode_key, img, mtime, size, path = item[:6]
            else:
                device_id, inode_key, img, mtime, size = item[:5]
                path = None

            if not img or img.isNull():
                continue

            try:
                img_data = self._image_to_bytes(img)
                if not img_data:
                    continue

                # Pack mtime as a double (8 bytes) and prepend to image data
                mtime_bytes = struct.pack('d', mtime)

                # New format: mtime(8) + 'PTH\0'(4) + len(4) + path + img
                if path:
                    path_encoded = path.encode('utf-8')
                    header = mtime_bytes + b'PTH\0' + \
                        struct.pack('I', len(path_encoded)) + path_encoded
                    value_bytes = header + img_data
                else:
                    value_bytes = mtime_bytes + img_data

                data_to_write.append((device_id, size, inode_key, value_bytes))
            except Exception as e:
                logger.error(f"Error converting image for LMDB: {e}")

        if not data_to_write:
            return

        # 2. Commit to DB in one transaction
        try:
            with env.begin(write=True) as txn:
                # Write images
                for device_id, size, inode_key, value_bytes in data_to_write:
                    # Ensure DB exists (creates if needed) using the current transaction
                    db = self._get_device_db(device_id, size, write=True, txn=txn)
                    if db:
                        try:
                            txn.put(inode_key, value_bytes, db=db)
                        except lmdb.Error as e:
                            # Handle potential stale DB handles (EINVAL)
                            # This happens if a previous transaction created the handle
                            # but aborted.
                            if "Invalid argument" in str(e):
                                db_name = f"dev_{device_id}_{size}".encode('utf-8')
                                self._db_lock.lock()
                                if db_name in self._db_handles:
                                    del self._db_handles[db_name]
                                self._db_lock.unlock()
                                # Retry open and put with fresh handle
                                db = self._get_device_db(
                                    device_id, size, write=True, txn=txn)
                                if db:
                                    txn.put(inode_key, value_bytes, db=db)
                            else:
                                raise

                # Write metadata
                if meta_to_write:
                    meta_db = env.open_db(METADATA_DB_NAME, txn=txn, create=True)
                    for k, v in meta_to_write:
                        txn.put(k, v, db=meta_db)

                # Write directory listings
                if dirs_to_write:
                    dir_db = env.open_db(DIRECTORY_DB_NAME, txn=txn, create=True)
                    for k, v in dirs_to_write:
                        txn.put(k, v, db=dir_db)

        except Exception as e:
            logger.error(f"Error committing batch to LMDB: {e}")
            # If transaction failed, handles created within it are now invalid.
            # Clear cache to be safe.
            self._db_lock.lock()
            self._db_handles.clear()
            self._db_lock.unlock()

    def _delete_from_lmdb(self, path, device_id=None, inode_key=None):
        """Delete all thumbnail sizes for a path from LMDB."""
        env = self._lmdb_env
        if not env:
            return

        if device_id is None or inode_key is None:
            device_id = self._get_device_id(path)
            inode_key = self._get_inode_key(path)

        if not inode_key or device_id == 0:
            return

        for size in THUMBNAIL_SIZES:
            try:
                with env.begin(write=True) as txn:
                    # Get DB handle using the current transaction and don't force create
                    db = self._get_device_db(device_id, size, write=False, txn=txn)
                    if not db:
                        continue

                    try:
                        txn.delete(inode_key, db=db)
                    except lmdb.Error as e:
                        if "Invalid argument" in str(e):
                            # Handle potential stale DB handles (EINVAL)
                            db_name = f"dev_{device_id}_{size}".encode('utf-8')
                            self._db_lock.lock()
                            self._db_handles.pop(db_name, None)
                            self._db_lock.unlock()
                            # Retry with a fresh handle within the same transaction
                            db = self._get_device_db(
                                device_id, size, write=False, txn=txn)
                            if db:
                                txn.delete(inode_key, db=db)
                        elif "not found" in str(e).lower():
                            pass
                        else:
                            raise
            except lmdb.NotFoundError:
                pass
            except Exception as e:
                logger.error(f"Error deleting from LMDB for size {size}: {e}")

    @staticmethod
    def _image_to_bytes(img):
        """Convert QImage to PNG bytes."""
        buf = None
        try:
            ba = QByteArray()
            buf = QBuffer(ba)
            if not buf.open(QIODevice.WriteOnly):
                logger.error("Failed to open buffer for image conversion")
                return None

            if not img.save(buf, "PNG"):
                logger.warning(f"Failed to save QImage to buffer for {img.size()} (first attempt). Retrying with ARGB32.")
                # libpng errors (like "Incorrect data in iCCP") can cause save() topi
                # fail.
                # Converting to a standard format strips problematic metadata/profiles.
                ba.clear()
                buf.seek(0)
                if not img.convertToFormat(QImage.Format_ARGB32).save(buf, "PNG"):
                    logger.error(f"Failed to save QImage to buffer for {img.size()} (second attempt).")
                    logger.error("Failed to save image to buffer")
                    return None
            return ba.data()
        except Exception as e:
            logger.error(f"Error converting image to bytes: {e}")
            return None
        finally:
            if buf:
                buf.close()

    def get_cache_stats(self):
        """Get current cache statistics."""
        with self._read_lock():
            # Count all thumbnails, including different sizes of the same image.
            count = sum(len(sizes) for sizes in self._thumbnail_cache.values())
            size = self._cache_bytes_size
        return count, size

    def rename_entry(self, old_path, new_path):
        """Move a cache entry from one path to another."""
        # Get new identity to check for cross-filesystem moves
        try:
            stat_info = os.stat(new_path)
            new_dev = stat_info.st_dev
            new_inode_key = struct.pack('Q', stat_info.st_ino)
        except OSError:
            return False

        entries_to_rewrite = []
        old_inode_info = None

        with self._write_lock():
            if old_path not in self._thumbnail_cache:
                return False

            self._thumbnail_cache[new_path] = self._thumbnail_cache.pop(old_path)
            old_inode_info = self._path_to_inode.pop(old_path, None)

            if old_inode_info:
                self._path_to_inode[new_path] = (new_dev, new_inode_key)
                # Always prepare data to persist to update the embedded path in LMDB
                for size, (img, mtime) in self._thumbnail_cache[new_path].items():
                    entries_to_rewrite.append((size, img, mtime))

        # Perform LMDB operations outside the lock
        if not old_inode_info:
            return False

        old_dev, old_inode = old_inode_info

        # Only delete old key if physical identity changed (cross-filesystem moves)
        if old_inode_info != (new_dev, new_inode_key):
            self._delete_from_lmdb(old_path, device_id=old_dev, inode_key=old_inode)

        if self._cache_writer:
            for size, img, mtime in entries_to_rewrite:
                self._cache_writer.enqueue(
                    (new_dev, new_inode_key, img, mtime, size, new_path),
                    block=False)

            # Also update metadata cache path to prevent clean_stale_metadata from
            # deleting it. Reuse current tags and rating.
            if entries_to_rewrite:
                m_mtime = entries_to_rewrite[0][2]
                m_tags, m_rating, _ = self.get_metadata(old_dev, old_inode, m_mtime)
                if m_tags is not None:
                    self.set_metadata(new_dev, new_inode_key, m_mtime,
                                      m_tags, m_rating, new_path)

        return True

    @contextmanager
    def generation_lock(self, path, size, curr_mtime=None, inode=None,
                        device_id=None):
        """
        Context manager to coordinate thumbnail generation between threads.
        Prevents double work: if one thread is generating, others wait.

        Yields:
            bool: True if the caller should generate the thumbnail.
                  False if the caller waited and should check cache again.
        """
        # Resolve identity for locking key
        _, dev_id, inode_key = self._resolve_file_identity(
            path, curr_mtime, inode, device_id)

        if not inode_key or dev_id == 0:
            # Cannot lock reliably without stable ID, allow generation
            yield True
            return

        key = (dev_id, inode_key, size)
        future = None
        owner = False

        self._futures_lock.lock()
        if key in self._futures:
            future = self._futures[key]
        else:
            future = GenerationFuture()
            self._futures[key] = future
            owner = True
        self._futures_lock.unlock()

        if owner:
            try:
                yield True
            finally:
                future.complete()
                self._futures_lock.lock()
                if key in self._futures and self._futures[key] is future:
                    del self._futures[key]
                self._futures_lock.unlock()
        else:
            # Another thread is generating, wait for it
            future.wait()
            yield False


class CacheCleaner(QThread):
    """Background thread to remove cache entries for deleted files."""
    finished_clean = Signal(int)

    def __init__(self, cache):
        super().__init__()
        self.cache = cache
        self._is_running = True

    def stop(self):
        """Signals the thread to stop."""
        self._is_running = False
        self.wait()

    def run(self):
        self.setPriority(QThread.IdlePriority)
        if not self._is_running:
            return
        # Perform deep cleaning of LMDB
        removed_count = self.cache.remove_if_missing([])
        if self._is_running:
            removed_count += self.cache.clean_orphans(
                stop_check=lambda: not self._is_running)
        self.finished_clean.emit(removed_count)


class ThumbnailGenerator(QThread):
    """
    Background thread to generate thumbnails for a specific size for a list of
    already discovered files.
    """
    generation_complete = Signal()
    progress = Signal(int, int)  # processed, total

    class SignalEmitter(QObject):
        """Helper to emit signals from runnables to the main thread."""
        progress_tick = Signal()

        def emit_progress(self):
            self.progress_tick.emit()

    def __init__(self, cache, paths, size, thread_pool_manager):
        super().__init__()
        self.cache = cache
        self.paths = paths
        self.size = size
        self._abort = False
        self.thread_pool_manager = thread_pool_manager
        self._workers = []
        self._workers_mutex = QMutex()

    def stop(self):
        """Stops the worker thread gracefully."""
        self._abort = True
        self._workers_mutex.lock()
        for worker in self._workers:
            worker.shutdown()
        self._workers_mutex.unlock()
        self.wait()

    def run(self):
        """
        Main execution loop. Uses a thread pool to process paths in parallel.
        """
        pool = self.thread_pool_manager.get_pool()

        emitter = self.SignalEmitter()
        processed_count = 0
        total = len(self.paths)
        sem = QSemaphore(0)

        def on_tick():
            nonlocal processed_count
            processed_count += 1
            if processed_count % 5 == 0 or processed_count == total:
                # Signal remains int, format in receiver
                self.progress.emit(processed_count, total)

        # Use a direct connection or queued connection depending on context,
        # but since we are in QThread.run, we can connect local slot.
        # However, runnables run in pool threads. We need thread-safe update.
        # The signal/slot mechanism handles thread safety automatically.
        emitter.progress_tick.connect(on_tick, Qt.QueuedConnection)

        # Process in batches to avoid saturating the global thread pool queue.
        # This allows the application to respond to stop() signals almost
        # immediately.
        batch_size = max(4, pool.maxThreadCount() * 2)

        for i in range(0, len(self.paths), batch_size):
            if self._abort:
                break

            batch_slice = self.paths[i: i + batch_size]
            started_in_batch = 0

            for path in batch_slice:
                if self._abort:
                    break
                runnable = ScannerWorker(self.cache, path, target_sizes=[self.size],
                                         load_metadata=False, signal_emitter=emitter,
                                         semaphore=sem)
                runnable.setAutoDelete(False)

                self._workers_mutex.lock()
                self._workers.append(runnable)
                self._workers_mutex.unlock()

                pool.start(runnable)
                started_in_batch += 1

            if started_in_batch > 0:
                # Wait for the current batch to finish before queuing more
                sem.acquire(started_in_batch)
                self._workers_mutex.lock()
                self._workers.clear()
                self._workers_mutex.unlock()

        self._workers_mutex.lock()
        self._workers.clear()
        self._workers_mutex.unlock()

        if not self._abort:
            self.generation_complete.emit()


class ImageScanner(QThread):
    """
    Background thread for scanning directories and loading images.
    """
    # List of tuples (path, QImage_thumb, mtime, tags, rating)
    # Updated tuple: (path, QImage_thumb, mtime, tags, rating, inode, device_id)
    images_found = Signal(list)
    progress_msg = Signal(str)
    progress_percent = Signal(int)
    finished_scan = Signal(int)  # Total images found
    more_files_available = Signal(int, int)  # Last loaded index, remainder

    def __init__(self, cache, paths, is_file_list=False, viewers=None,
                 thread_pool_manager=None, target_sizes=None,
                 force_thumbnail_refresh=False,
                 scan_max_level=None):
        if not paths or not isinstance(paths, (list, tuple)):
            logger.warning("ImageScanner initialized with empty or invalid paths")
            paths = []
        super().__init__()
        self.cache = cache
        self.target_sizes = target_sizes
        self.all_files = []
        self.thread_pool_manager = thread_pool_manager
        self._viewers = viewers
        self._seen_files = set()
        self._is_file_list = is_file_list
        self._scan_max_level = scan_max_level
        if self._is_file_list:
            self.paths = []
            for p in paths:
                if os.path.isfile(p):
                    p_str = str(p)
                    if p_str not in self._seen_files:
                        self.all_files.append(p_str)
                        self._seen_files.add(p_str)
                    path = os.path.dirname(p)
                    if path not in self.paths:
                        self.paths.append(path)
                else:
                    self.paths.append(p)
        else:
            self.paths = paths
        self._is_running = True
        self._auto_load_enabled = False
        self.count = 0
        self.index = 0
        self._paused = False
        self.mutex = QMutex()
        self.condition = QWaitCondition()
        self.pending_tasks = []
        self._priority_queue = collections.deque()
        self._processed_paths = set()
        self.force_thumbnail_refresh = force_thumbnail_refresh
        self._current_workers = []
        self._current_workers_mutex = QMutex()

        # Initial load
        self.pending_tasks.append((0, APP_CONFIG.get(
            "scan_batch_size", SCANNER_SETTINGS_DEFAULTS["scan_batch_size"])))
        self._last_update_time = 0

        if self.thread_pool_manager:
            self.pool = self.thread_pool_manager.get_pool()
        else:
            self.pool = QThreadPool()
            max_threads = APP_CONFIG.get(
                "generation_threads",
                SCANNER_SETTINGS_DEFAULTS.get("generation_threads", 4))
            self.pool.setMaxThreadCount(max_threads)

        logger.info(f"ImageScanner initialized with {len(paths)} paths")

    def set_auto_load(self, enabled):
        """Enable or disable automatic loading of all subsequent images."""
        self._auto_load_enabled = enabled

    def set_paused(self, paused):
        """Pauses or resumes the scanning process."""
        self._paused = paused

    def prioritize(self, paths):
        """Adds paths to the priority queue for immediate processing."""
        self.mutex.lock()
        for p in paths:
            self._priority_queue.append(p)
        self.mutex.unlock()

    def run(self):
        # LowPriority ensures UI thread gets CPU time to process events (mouse, draw)
        self.setPriority(QThread.IdlePriority)
        self.progress_msg.emit(UITexts.SCANNING_DIRS)
        self.scan_files()

        while self._is_running:
            self.mutex.lock()
            while not self.pending_tasks and self._is_running:
                self.condition.wait(self.mutex)

            if not self._is_running:
                self.mutex.unlock()
                break

            i, to_load = self.pending_tasks.pop(0)
            self.mutex.unlock()

            self._process_images(i, to_load)

    def _update_viewers(self, force=False):
        if not self._viewers:
            return

        current_time = time.time()
        # Throttle updates to avoid saturating the event loop (max 5 times/sec)
        if not force and (current_time - self._last_update_time < 0.2):
            return
        self._last_update_time = current_time

        # Image viewers standalone unique sort, this must be improved.
        all_files_sorted_by_name_ascending = sorted(self.all_files)
        # Iterate over a copy to avoid runtime errors if list changes in main thread
        for w in list(self._viewers):
            try:
                if isinstance(w, ImageViewer):
                    QTimer.singleShot(
                        0, w, lambda viewer=w, files=all_files_sorted_by_name_ascending:
                        viewer.update_image_list(files))
            except (RuntimeError, Exception):
                # Handle cases where viewer might be closing/deleted (RuntimeError) or
                # other issues
                pass

    def scan_files(self):
        for path in self.paths:
            if not self._is_running:
                return
            try:
                if path.startswith("file://"):
                    path = path[7:]
                elif path.startswith("file:/"):
                    path = path[6:]

                # Check if path exists before resolving absolute path to avoid
                # creating fake paths for search queries.
                expanded_path = os.path.expanduser(path)
                if os.path.exists(expanded_path):
                    p = Path(os.path.abspath(expanded_path))
                    if p.is_file():
                        p_str = str(p)
                        if p_str not in self._seen_files:
                            self.all_files.append(p_str)
                            self._seen_files.add(p_str)
                    elif p.is_dir():
                        self._scan_directory(p, 0)
                        self._update_viewers()
                else:
                    self._search(path)
                    self._update_viewers()
                    # logger.warning(f"Path not found: {p}")
            except Exception as e:
                logger.error(f"Error scanning path {path}: {e}")

        # Ensure final update reaches viewers
        self._update_viewers(force=True)

    def _scan_directory(self, dir_path, current_depth):
        if self._scan_max_level is None:
            max_level = APP_CONFIG.get(
                "scan_max_level", SCANNER_SETTINGS_DEFAULTS["scan_max_level"])
        else:
            max_level = self._scan_max_level

        if not self._is_running or current_depth > max_level:
            return

        # Try to retrieve results from cache
        dir_stat = None
        try:
            dir_stat = os.stat(str(dir_path))
            cached_mtime, cached_files = self.cache.get_directory_cache(str(dir_path))
            # mtime > 0 means there is a cache entry (even if empty of images)
            if cached_mtime > 0 and abs(cached_mtime - dir_stat.st_mtime) < 0.001:
                for p in cached_files:
                    if p and p not in self._seen_files:
                        self.all_files.append(p)
                        self._seen_files.add(p)

                # IMPORTANT: Even if using cache for THIS folder's images,
                # subdirectories must be explored if max depth isn't reached.
                if current_depth < max_level:
                    try:
                        for item in dir_path.iterdir():
                            if not self._is_running:
                                return
                            if item.is_dir():
                                self._scan_directory(item, current_depth + 1)
                    except (PermissionError, OSError):
                        pass
                return
        except OSError:
            pass

        files_in_dir = []
        try:
            for item in dir_path.iterdir():
                if not self._is_running:
                    return
                if item.is_file() and item.suffix.lower() in IMAGE_EXTENSIONS:
                    p = os.path.abspath(str(item))
                    if p not in self._seen_files:
                        self.all_files.append(p)
                        self._seen_files.add(p)
                        files_in_dir.append(p)
                        self._update_viewers()
                elif item.is_dir():
                    self._scan_directory(item, current_depth + 1)

            # Cache findings for this directory
            if dir_stat:
                self.cache.set_directory_cache(
                    str(dir_path), dir_stat.st_mtime, sorted(files_in_dir))

        except (PermissionError, OSError):
            pass

    def _parse_query(self, query):
        parser = argparse.ArgumentParser(prog="bagheera-search",
                                         add_help=False)

        # Main arguments
        parser.add_argument("query", nargs="?", default="")
        parser.add_argument("-d", "--directory")
        parser.add_argument("-e", "--having", nargs="?", const="",
                            default=None)
        parser.add_argument("-l", "--limit", type=int)
        parser.add_argument("-o", "--offset", type=int)
        parser.add_argument("-r", "--subquery", nargs="?", const="",
                            default=None)
        parser.add_argument("-x", "--subquery-having", nargs="?", const="",
                            default=None)
        parser.add_argument("-s", "--sort")
        parser.add_argument("-t", "--type")

        # Date filters
        parser.add_argument("--day", type=int)
        parser.add_argument("--month", type=int)
        parser.add_argument("--year", type=int)

        try:
            args_list = shlex.split(str(query))
            args, unknown_args = parser.parse_known_args(args_list)

            if args.day is not None and args.month is None:
                raise ValueError("Missing --month (required when --day is used)")

            if args.month is not None and args.year is None:
                raise ValueError("Missing --year (required when --month is used)")

            query_parts = [args.query] if args.query else []
            if unknown_args:
                query_parts.extend(unknown_args)

            query_text = " ".join(query_parts)

            # Build options dictionary
            main_options = {}
            if args.subquery is not None:
                main_options["type"] = "folder"
            else:
                if args.limit is not None:
                    main_options["limit"] = args.limit
                if args.offset is not None:
                    main_options["offset"] = args.offset
                if args.type:
                    main_options["type"] = args.type

            if args.directory:
                main_options["directory"] = args.directory
            if args.year is not None:
                main_options["year"] = args.year
            if args.month is not None:
                main_options["month"] = args.month
            if args.day is not None:
                main_options["day"] = args.day
            if args.sort:
                main_options["sort"] = args.sort
            if args.having and args.having == '':
                args.subquery_having = None
            if args.subquery_having and args.subquery_having == '':
                args.subquery_having = None
            other_options = {
                "having": args.having,
                "id": False,
                "konsole": False,
                "limit": args.limit if args.limit and args.subquery is not None
                else 99999999999,
                "offset": args.offset if args.offset and args.subquery is not None
                else 0,
                "subquery": args.subquery,
                "subquery_indent": "",
                "subquery_having": args.subquery_having,
                "sort": args.sort,
                "type": args.type if args.subquery is not None else None,
                "verbose": False,
            }

            return query_text, main_options, other_options

        except ValueError as e:
            print(f"Arguments error: {e}")
            return None, []
        except Exception as e:
            print(f"Unexpected error parsing query: {e}")
            return None, []

    def _search(self, query):
        engine = APP_CONFIG.get("search_engine", "Bagheera")
        if HAVE_BAGHEERASEARCH_LIB and (engine == "Bagheera" or not SEARCH_CMD):
            query_text, main_options, other_options = self._parse_query(query)
            try:
                searcher = BagheeraSearcher()
                for item in searcher.search(query_text, main_options, other_options):
                    if not self._is_running:
                        break
                    p = item["path"].strip()
                    if p and os.path.exists(os.path.expanduser(p)):
                        if p not in self._seen_files:
                            self.all_files.append(p)
                            self._seen_files.add(p)
                            self._update_viewers()
            except Exception as e:
                print(f"Error during bagheerasearch library call: {e}")

        elif SEARCH_CMD:
            try:
                cmd = SEARCH_CMD + shlex.split(str(query))
                out = subprocess.check_output(cmd, text=True).splitlines()
                for p in out:
                    if not self._is_running:
                        break
                    p = p.strip()
                    if p.startswith("file://"):
                        p = p[7:]
                    if p and os.path.exists(os.path.expanduser(p)):
                        if p not in self._seen_files:
                            self.all_files.append(p)
                            self._seen_files.add(p)
                            self._update_viewers()
            except Exception as e:
                print(f"Error during {SEARCH_CMD} subprocess call: {e}")

    def load_images(self, i, to_load):
        if i < 0:
            i = 0
        if i >= len(self.all_files):
            return
        self.mutex.lock()
        self.pending_tasks.append((i, to_load))
        self.condition.wakeAll()
        self.mutex.unlock()

    def _process_images(self, i, to_load):

        if i >= len(self.all_files):
            self.finished_scan.emit(self.count)
            return

        if self.thread_pool_manager:
            max_threads = self.thread_pool_manager.default_thread_count
        else:
            max_threads = APP_CONFIG.get(
                "generation_threads",
                SCANNER_SETTINGS_DEFAULTS.get("generation_threads", 4))
            self.pool.setMaxThreadCount(max_threads)

        images_loaded = 0
        batch = []
        while i < len(self.all_files):

            if not self._is_running:
                return

            while self._paused and self._is_running:
                self.msleep(100)

            # Collect paths for this chunk to process in parallel
            chunk_size = max_threads * 2
            tasks = []  # List of (path, is_from_priority_queue)

            # 1. Drain priority queue up to chunk size
            self.mutex.lock()
            while len(tasks) < chunk_size and self._priority_queue:
                p = self._priority_queue.popleft()
                if p not in self._processed_paths and p in self._seen_files:
                    tasks.append((p, True))
            self.mutex.unlock()

            # 2. Fill remaining chunk space with sequential files
            temp_i = i
            while len(tasks) < chunk_size and temp_i < len(self.all_files):
                p = self.all_files[temp_i]
                # Skip if already processed (e.g. via priority earlier)
                if p not in self._processed_paths \
                   and Path(p).suffix.lower() in IMAGE_EXTENSIONS:
                    tasks.append((p, False))
                temp_i += 1

            if not tasks:
                # If no tasks found but still have files (e.g. all skipped extensions),
                # update index and continue loop
                i = temp_i
                continue

            # Submit tasks to thread pool
            sem = QSemaphore(0)
            runnables = []

            self._current_workers_mutex.lock()
            if not self._is_running:
                self._current_workers_mutex.unlock()
                return

            for f_path, _ in tasks:
                r = ScannerWorker(
                    self.cache, f_path, semaphore=sem, target_sizes=self.target_sizes,
                    force_thumbnail_refresh=self.force_thumbnail_refresh)
                r.setAutoDelete(False)
                runnables.append(r)
                self._current_workers.append(r)
                self.pool.start(r)
            self._current_workers_mutex.unlock()

            # Wait only for this chunk to finish using semaphore
            sem.acquire(len(runnables))

            self._current_workers_mutex.lock()
            self._current_workers.clear()
            self._current_workers_mutex.unlock()

            if not self._is_running:
                return

            # Process results
            for r in runnables:
                if r.result:
                    self._processed_paths.add(r.path)
                    batch.append(r.result)
                    self.count += 1
                    images_loaded += 1
                    # Emit progress every time an image is loaded
                    if len(self.all_files) > 0:
                        percent = int((self.count / len(self.all_files)) * 100)
                        self.progress_percent.emit(percent)

            # Clean up runnables
            runnables.clear()

            # Advance sequential index
            i = temp_i

            # Emit batch if size is enough (responsiveness optimization)
            if self.count <= 100:
                target_batch_size = 20
            else:
                target_batch_size = 200

            if len(batch) >= target_batch_size:
                self.images_found.emit(batch)
                batch = []
                self.msleep(10)  # Yield to UI

            # Check if loading limit reached
            if images_loaded >= to_load and to_load > 0:
                if batch:  # Emit remaining items
                    self.images_found.emit(batch)

                next_index = i
                total_files = len(self.all_files)
                self.index = next_index
                self.progress_msg.emit(UITexts.LOADED_PARTIAL.format(
                    self.count, total_files - next_index))

                if total_files > 0:
                    percent = int((self.count / total_files) * 100)
                    self.progress_percent.emit(percent)

                self.more_files_available.emit(next_index, total_files)
                # This loads all images continuously without pausing only if
                # explicitly requested
                if self._auto_load_enabled:
                    self.load_images(
                        next_index,
                        APP_CONFIG.get("scan_batch_size",
                                       SCANNER_SETTINGS_DEFAULTS[
                                           "scan_batch_size"]))
                return

            # Emit progress message less frequently, e.g., every 50 images or at batch
            # end
            if self.count % 50 == 0 or images_loaded >= to_load:
                self.progress_msg.emit(UITexts.LOADING_SCAN.format(
                    self.count, len(self.all_files)))

        self.index = len(self.all_files)
        if batch:
            self.images_found.emit(batch)
        self.progress_percent.emit(100)
        self.finished_scan.emit(self.count)

    def stop(self):
        logger.info("ImageScanner stop requested")
        self._is_running = False

        # Cancel currently running workers in the active batch
        self._current_workers_mutex.lock()
        for worker in self._current_workers:
            worker.shutdown()
        self._current_workers_mutex.unlock()

        # Wake up the condition variable
        self.mutex.lock()
        self.condition.wakeAll()
        self.mutex.unlock()
        self.wait()
