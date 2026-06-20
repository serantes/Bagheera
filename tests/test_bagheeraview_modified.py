import os
from unittest.mock import MagicMock, patch
from PySide6.QtCore import QPersistentModelIndex
from PySide6.QtGui import QStandardItem, QStandardItemModel
from bagheeraview.core.app import MainWindow
from bagheeraview.core.constants import (
    PATH_ROLE, MTIME_ROLE, TAGS_ROLE, RATING_ROLE
)


class DummyMainWindow(MainWindow):
    def __init__(self):
        # Skip MainWindow.__init__ to avoid UI initialization
        self._known_paths = set()
        self._paths_being_modified_by_app = set()
        self.cache = MagicMock()
        self.found_items_data = []
        self.proxy_model = MagicMock()
        self._path_to_model_index = {}
        self.thumbnail_model = QStandardItemModel()
        self.view_mode_combo = MagicMock()
        self.view_mode_combo.currentIndex.return_value = 0  # flat view
        self.thumbnail_view = MagicMock()
        self.status_lbl = MagicMock()
        self.viewers = []
        self.update_tag_edit_widget = MagicMock()
        self.update_info_widget = MagicMock()
        
        # Necessary attributes for ThumbnailGenerator logic
        self.current_thumb_size = 128
        self.thread_pool_manager = MagicMock()

    def _update_internal_data(self, path, qi=None, mtime=None, tags=None, rating=None,
                              inode=None, dev=None):
        # Simple mock update logic
        for i, item in enumerate(self.found_items_data):
            if item[0] == path:
                self.found_items_data[i] = (path, qi, mtime, tags, rating, inode, dev)
                break


def test_on_fs_file_modified(tmp_path):
    # Create a dummy image file
    img_file = tmp_path / "test_image.png"
    img_file.write_text("dummy content")
    path_str = os.path.abspath(str(img_file))

    # Instantiate the dummy main window
    win = DummyMainWindow()
    win._known_paths.add(path_str)

    # Setup standard item in model
    item = QStandardItem("test_image.png")
    item.setData(path_str, PATH_ROLE)
    item.setData(100.0, MTIME_ROLE)
    item.setData(["tag1"], TAGS_ROLE)
    item.setData(3, RATING_ROLE)
    win.thumbnail_model.appendRow(item)

    # Store persistent model index
    source_index = win.thumbnail_model.indexFromItem(item)
    win._path_to_model_index[path_str] = QPersistentModelIndex(source_index)

    # Add to found_items_data list
    win.found_items_data.append((path_str, None, 100.0, ["tag1"], 3, 1, 1))

    # Mock metadata returned from load_common_metadata
    mock_meta = MagicMock()
    mock_meta.tags = ["tag1", "tag2"]
    mock_meta.rating = 5

    with patch("bagheeraview.core.app.load_common_metadata", return_value=mock_meta), \
         patch("bagheeraview.core.app.ThumbnailGenerator") as mock_gen_class:
        
        mock_gen_instance = MagicMock()
        mock_gen_class.return_value = mock_gen_instance
        
        win.on_fs_file_modified(path_str)

        # Verify ThumbnailGenerator was created and started
        mock_gen_class.assert_called_once_with(
            win.cache, [path_str], win._get_tier_for_size(win.current_thumb_size), win.thread_pool_manager
        )
        mock_gen_instance.start.assert_called_once()

    # 1. Verify cache was invalidated
    win.cache.invalidate_path.assert_called_once_with(path_str)

    # 2. Verify proxy model cache updated
    win.proxy_model.add_to_cache.assert_called_once_with(path_str, ["tag1", "tag2"])

    # 3. Verify internal data updated
    assert win.found_items_data[0][2] > 100.0  # mtime updated
    assert win.found_items_data[0][3] == ["tag1", "tag2"]
    assert win.found_items_data[0][4] == 5

    # 4. Verify standard item roles updated
    updated_item = win.thumbnail_model.item(0)
    assert updated_item.data(TAGS_ROLE) == ["tag1", "tag2"]
    assert updated_item.data(RATING_ROLE) == 5
    assert updated_item.data(MTIME_ROLE) > 100.0

    # 5. Verify proxy_model.invalidate was called (flat view)
    win.proxy_model.invalidate.assert_called_once()
