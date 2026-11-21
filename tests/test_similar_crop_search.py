import sqlite3
import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest
from PySide6.QtCore import QPoint, QRect
from PySide6.QtGui import QColor, QImage, QPixmap
from PySide6.QtWidgets import QApplication

from bagheeraview.core import app, faiss_worker, imageviewer, similardialog
from bagheeraview.core.constants import UITexts
from bagheeraview.core.imageviewer import FaceCanvas, ImageViewer


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def test_similar_dialog_is_imported_on_request(monkeypatch):
    module = ModuleType("bagheeraview.core.similardialog")
    dialog = Mock()
    module.SimilarImagesDialog = Mock(return_value=dialog)
    monkeypatch.setitem(sys.modules, module.__name__, module)
    monkeypatch.setattr(app, "HAVE_IMAGEHASH", True)
    window = object()
    query = object()

    app.MainWindow.find_similar_images(window, "/image.png", query_image=query)

    module.SimilarImagesDialog.assert_called_once_with(
        "/image.png", window, query_image=query)
    dialog.show.assert_called_once_with()


def test_similar_dialog_import_failure_is_reported(monkeypatch):
    module = ModuleType("bagheeraview.core.similardialog")
    monkeypatch.setitem(sys.modules, module.__name__, module)
    monkeypatch.setattr(app, "HAVE_IMAGEHASH", True)
    warning = Mock()
    monkeypatch.setattr(app.QMessageBox, "warning", warning)
    window = object()

    app.MainWindow.find_similar_images(window, "/image.png")

    warning.assert_called_once()
    assert warning.call_args.args[0] is window
    assert UITexts.SIMILAR_SEARCH_ERROR.split("{}")[0] in warning.call_args.args[2]


def test_crop_search_menu_uses_original_selected_pixels(qapp, monkeypatch):
    source = QImage(100, 80, QImage.Format_RGB32)
    source.fill(QColor("red"))
    for y in range(10, 30):
        for x in range(20, 50):
            source.setPixelColor(x, y, QColor("blue"))
    controller = SimpleNamespace(
        pixmap_original=QPixmap.fromImage(source),
        rotation=90, flip_h=False, flip_v=False,
        get_current_path=lambda: "/original.png")
    canvas = SimpleNamespace(
        crop_rect=QRect(50, 20, 20, 30),
        width=lambda: 80, height=lambda: 100,
        controller=controller)
    canvas.map_to_source = lambda rect: FaceCanvas.map_to_source(canvas, rect)
    viewer = SimpleNamespace(
        active_pane=SimpleNamespace(
            canvas=canvas, controller=controller, crop_mode=True),
        main_win=SimpleNamespace(find_similar_images=Mock()),
        save_cropped_image=Mock())
    viewer._cropped_image = lambda: ImageViewer._cropped_image(viewer)

    class Menu:
        def __init__(self, _parent):
            self.actions = []

        def addAction(self, *args):
            action = object()
            self.actions.append((args[-1], action))
            return action

        def exec(self, _pos):
            assert [text for text, _action in self.actions] == [
                UITexts.VIEWER_MENU_SAVE_CROP, UITexts.MENU_FIND_SIMILAR,
                UITexts.CLOSE]
            return self.actions[1][1]

    monkeypatch.setattr(imageviewer, "QMenu", Menu)
    monkeypatch.setattr(imageviewer, "HAVE_IMAGEHASH", True)

    ImageViewer.show_crop_menu(viewer, QPoint())

    args = viewer.main_win.find_similar_images.call_args
    assert args.args == ("/original.png",)
    selected = args.kwargs["query_image"]
    assert (selected.width(), selected.height()) == (30, 20)
    assert selected.pixelColor(0, 0) == QColor("blue")
    assert selected.pixelColor(29, 19) == QColor("blue")
    viewer.save_cropped_image.assert_not_called()


def test_crop_query_is_recomputed_without_changing_cached_embeddings(
        qapp, tmp_path, monkeypatch):
    source = str(tmp_path / "source.png")
    other = str(tmp_path / "other.png")
    for path in (source, other):
        with open(path, "wb") as file:
            file.write(b"placeholder")
    db_path = tmp_path / "embeddings.db"
    monkeypatch.setattr(faiss_worker, "DB_PATH", str(db_path))
    conn = faiss_worker._open_embeddings_db()
    full_vector = np.zeros(1024, dtype=np.float32)
    full_vector[0] = 1
    selection_vector = np.zeros(1024, dtype=np.float32)
    selection_vector[1] = 1
    conn.executemany(
        "INSERT INTO embeddings VALUES (?, ?, ?)",
        [(source, 1, full_vector.tobytes()),
         (other, 1, selection_vector.tobytes())])
    conn.commit()
    conn.close()
    refresh = Mock()
    embed = Mock(return_value=selection_vector)
    monkeypatch.setattr(faiss_worker, "_refresh_embeddings", refresh)
    monkeypatch.setattr(faiss_worker, "_embed_single_image", embed)
    query = QImage(3, 2, QImage.Format_RGB32)
    query.fill(QColor("blue"))

    for _ in range(2):
        worker = faiss_worker.FAISSSimilarSearchWorker(
            source, 80, "", "", visible_paths=[source, other],
            query_image=query)
        results = []
        errors = []
        worker.results_found.connect(results.append)
        worker.error.connect(errors.append)
        worker.run()
        assert errors == []
        assert results == [[(other, 100)]]

    assert embed.call_count == 2
    assert all(call.args == (source, query) for call in embed.call_args_list)
    assert refresh.call_count == 2
    embed.return_value = full_vector
    worker = faiss_worker.FAISSSimilarSearchWorker(
        source, 80, "", "", visible_paths=[source, other], query_image=query)
    source_results = []
    worker.results_found.connect(source_results.append)
    worker.run()
    assert source_results == [[(source, 100)]]
    conn = sqlite3.connect(db_path)
    rows = dict(conn.execute("SELECT path, embedding FROM embeddings"))
    conn.close()
    assert rows == {
        source: full_vector.tobytes(), other: selection_vector.tobytes()}


def test_full_image_search_still_uses_cached_query_and_excludes_source(
        qapp, tmp_path, monkeypatch):
    source = str(tmp_path / "source.png")
    other = str(tmp_path / "other.png")
    for path in (source, other):
        with open(path, "wb") as file:
            file.write(b"placeholder")
    monkeypatch.setattr(faiss_worker, "DB_PATH", str(tmp_path / "embeddings.db"))
    vector = np.zeros(1024, dtype=np.float32)
    vector[0] = 1
    conn = faiss_worker._open_embeddings_db()
    conn.executemany(
        "INSERT INTO embeddings VALUES (?, ?, ?)",
        [(source, 1, vector.tobytes()), (other, 1, vector.tobytes())])
    conn.commit()
    conn.close()
    monkeypatch.setattr(faiss_worker, "_refresh_embeddings", Mock())
    embed = Mock()
    monkeypatch.setattr(faiss_worker, "_embed_single_image", embed)
    worker = faiss_worker.FAISSSimilarSearchWorker(
        source, 80, "", "", visible_paths=[source, other])
    results = []
    worker.results_found.connect(results.append)

    worker.run()

    assert results == [[(other, 100)]]
    embed.assert_not_called()


def test_in_memory_query_embedding_preserves_rgb_with_padded_rows(
        qapp, monkeypatch):
    captured = []
    vector = np.ones(1024, dtype=np.float32)

    class Embedder:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

        def embed(self, image):
            captured.append(image)
            return SimpleNamespace(
                embeddings=[SimpleNamespace(embedding=vector)])

    vision = SimpleNamespace(
        ImageEmbedderOptions=lambda **kwargs: kwargs,
        ImageEmbedder=SimpleNamespace(
            create_from_options=lambda _options: Embedder()))
    python = SimpleNamespace(
        BaseOptions=lambda **kwargs: kwargs, vision=vision)
    mp = SimpleNamespace(
        ImageFormat=SimpleNamespace(SRGB="srgb"),
        Image=lambda **kwargs: kwargs["data"], tasks=SimpleNamespace(python=python))
    monkeypatch.setitem(sys.modules, "mediapipe", mp)
    monkeypatch.setitem(sys.modules, "mediapipe.tasks", mp.tasks)
    monkeypatch.setitem(sys.modules, "mediapipe.tasks.python", python)
    monkeypatch.setattr(faiss_worker, "_download_model_if_needed", Mock())
    query = QImage(3, 2, QImage.Format_RGB32)
    query.fill(QColor(11, 22, 33))

    result = faiss_worker._embed_single_image("/unused.png", query)

    np.testing.assert_array_equal(result, vector)
    np.testing.assert_array_equal(captured[0], np.full(
        (2, 3, 3), [11, 22, 33], dtype=np.uint8))


def test_rescan_passes_same_selection_to_new_worker(qapp, monkeypatch):
    query = QImage(3, 2, QImage.Format_RGB32)
    worker = SimpleNamespace(
        progress_update=SimpleNamespace(connect=Mock()),
        results_found=SimpleNamespace(connect=Mock()),
        error=SimpleNamespace(connect=Mock()),
        finished=SimpleNamespace(connect=Mock()),
        start=Mock())
    create_worker = Mock(return_value=worker)
    monkeypatch.setattr(similardialog, "FAISSSimilarSearchWorker", create_worker)
    dialog = SimpleNamespace(
        worker=None, target_path="/source.png", query_image=query,
        table=SimpleNamespace(setRowCount=Mock()),
        btn_search=SimpleNamespace(setEnabled=Mock()),
        progress_bar=SimpleNamespace(show=Mock(), setRange=Mock()),
        visible_only_check=SimpleNamespace(isChecked=lambda: True),
        threshold_spin=SimpleNamespace(value=lambda: 65),
        main_win=SimpleNamespace(
            proxy_model=SimpleNamespace(
                get_visible_paths=lambda: ["/source.png", "/other.png"])),
        on_progress=Mock(), on_results_found=Mock(),
        on_search_error=Mock(), on_finished=Mock())

    similardialog.SimilarImagesDialog.start_search(dialog)

    assert create_worker.call_args.kwargs["query_image"] is query
    assert create_worker.call_args.kwargs["visible_paths"] == [
        "/source.png", "/other.png"]
    worker.start.assert_called_once_with()


def test_failed_selection_embedding_is_reported(qapp, tmp_path, monkeypatch):
    source = tmp_path / "source.png"
    source.write_bytes(b"placeholder")
    monkeypatch.setattr(faiss_worker, "DB_PATH", str(tmp_path / "embeddings.db"))
    monkeypatch.setattr(faiss_worker, "_refresh_embeddings", Mock())
    monkeypatch.setattr(faiss_worker, "_embed_single_image", Mock(return_value=None))
    worker = faiss_worker.FAISSSimilarSearchWorker(
        str(source), 80, "", "", visible_paths=[str(source)],
        query_image=QImage(2, 2, QImage.Format_RGB32))
    errors = []
    results = []
    worker.error.connect(errors.append)
    worker.results_found.connect(results.append)

    worker.run()

    assert errors == ["Could not calculate selection embedding"]
    assert results == []
