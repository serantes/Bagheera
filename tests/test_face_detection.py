import os
from pathlib import Path
import subprocess
import sys
from types import ModuleType
import numpy as np
import pytest
from unittest.mock import MagicMock, patch
from PIL import Image

from bagheeraview.core import constants, imagecontroller, personrecognition
from bagheeraview.core.imagecontroller import (
    ImageController,
    _get_mediapipe,
    _load_mp_image
)


def test_startup_does_not_import_optional_recognition_or_similarity_libraries():
    source_dir = str(Path(__file__).resolve().parents[1] / "src")
    env = dict(os.environ, PYTHONPATH=source_dir, QT_QPA_PLATFORM="offscreen")
    result = subprocess.run(
        [sys.executable, "-c", """
import builtins
import importlib.machinery
import importlib.util

original_find_spec = importlib.util.find_spec
optional = {'mediapipe', 'face_recognition', 'face_recognition_models', 'faiss'}
def find_spec(name, *args, **kwargs):
    if name in optional:
        return importlib.machinery.ModuleSpec(name, None, is_package=True)
    return original_find_spec(name, *args, **kwargs)
importlib.util.find_spec = find_spec

original_import = builtins.__import__
attempts = []
def checked_import(name, *args, **kwargs):
    if name.split('.')[0] in optional:
        attempts.append(name)
        raise ImportError('optional dependency should be loaded on use')
    return original_import(name, *args, **kwargs)
builtins.__import__ = checked_import
import bagheeraview.core.app
assert not attempts, attempts
"""], env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr


def test_face_recognition_is_loaded_on_first_use(monkeypatch, tmp_path):
    module = MagicMock()
    module.face_encodings.return_value = [np.array([0.25, 0.5])]
    loader = MagicMock(return_value=module)
    monkeypatch.setattr(personrecognition, "HAVE_FACE_RECOGNITION", True)
    monkeypatch.setattr(personrecognition, "_face_recognition_checked", False)
    monkeypatch.setattr(personrecognition, "_face_recognition_module", None)
    monkeypatch.setattr(personrecognition, "_import_face_recognition", loader)
    path = tmp_path / "face.png"
    Image.new("RGB", (20, 20)).save(path)

    assert not loader.called
    for _ in range(2):
        assert personrecognition.extract_face_encoding(
            str(path), {"x": 0.5, "y": 0.5, "w": 0.5, "h": 0.5}) == [0.25, 0.5]
    loader.assert_called_once_with()
    assert module.face_encodings.call_count == 2


def test_unusable_face_recognition_logs_and_uses_fallback(monkeypatch, tmp_path, caplog):
    import builtins

    original_import = builtins.__import__

    def broken_import(name, *args, **kwargs):
        if name == "face_recognition":
            raise ImportError("broken face engine")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(constants.importlib.util, "find_spec", lambda name: object())
    monkeypatch.setattr(builtins, "__import__", broken_import)
    monkeypatch.setattr(personrecognition, "HAVE_FACE_RECOGNITION", True)
    monkeypatch.setattr(personrecognition, "_face_recognition_checked", False)
    monkeypatch.setattr(personrecognition, "_face_recognition_module", None)
    path = tmp_path / "face.png"
    Image.new("RGB", (20, 20)).save(path)

    result = personrecognition.extract_face_encoding(
        str(path), {"x": 0.5, "y": 0.5, "w": 0.5, "h": 0.5})

    assert len(result) == personrecognition.FALLBACK_FEATURE_SIZE ** 2
    assert "broken face engine" in caplog.text


def test_unusable_face_recognition_reports_error_to_detector(monkeypatch):
    monkeypatch.setattr(imagecontroller, "_face_recognition_module", None)
    monkeypatch.delitem(sys.modules, "face_recognition", raising=False)
    monkeypatch.setattr(imagecontroller, "_load_face_recognition", lambda: None)

    with pytest.raises(ImportError, match="unavailable or unusable"):
        imagecontroller._get_face_recognition()


def test_face_detector_uses_loader_even_when_module_is_being_imported(monkeypatch):
    partial_module = MagicMock()
    complete_module = MagicMock()
    loader = MagicMock(return_value=complete_module)
    monkeypatch.setitem(sys.modules, "face_recognition", partial_module)
    monkeypatch.setattr(imagecontroller, "_face_recognition_module", None)
    monkeypatch.setattr(imagecontroller, "_load_face_recognition", loader)

    assert imagecontroller._get_face_recognition() is complete_module
    loader.assert_called_once_with()


def test_mediapipe_failed_import_does_not_leave_partial_cache(monkeypatch):
    import builtins

    monkeypatch.setattr(imagecontroller, "_mediapipe_module", None)
    monkeypatch.setattr(imagecontroller, "_mp_python", None)
    monkeypatch.setattr(imagecontroller, "_mp_vision", None)
    monkeypatch.setitem(sys.modules, "mediapipe", MagicMock())
    monkeypatch.delitem(sys.modules, "mediapipe.tasks.python", raising=False)
    monkeypatch.delitem(sys.modules, "mediapipe.tasks.python.vision", raising=False)
    original_import = builtins.__import__

    def broken_import(name, *args, **kwargs):
        if name == "mediapipe.tasks":
            raise ImportError("broken tasks")
        return original_import(name, *args, **kwargs)

    with monkeypatch.context() as context:
        context.setattr(builtins, "__import__", broken_import)
        with pytest.raises(ImportError, match="broken tasks"):
            imagecontroller._get_mediapipe()
    assert imagecontroller._mediapipe_module is None

    tasks = ModuleType("mediapipe.tasks")
    python = ModuleType("mediapipe.tasks.python")
    vision = ModuleType("mediapipe.tasks.python.vision")
    tasks.python = python
    python.vision = vision
    monkeypatch.setitem(sys.modules, "mediapipe.tasks", tasks)
    monkeypatch.setitem(sys.modules, "mediapipe.tasks.python", python)
    monkeypatch.setitem(sys.modules, "mediapipe.tasks.python.vision", vision)
    _, loaded_python, loaded_vision = imagecontroller._get_mediapipe()
    assert loaded_python is python
    assert loaded_vision is vision


def test_get_mediapipe_caching():
    mock_mp = MagicMock()
    mock_python = MagicMock()
    mock_vision = MagicMock()
    mock_tasks = MagicMock()
    mock_tasks.python = mock_python
    mock_python.vision = mock_vision

    with patch.dict("sys.modules", {"mediapipe": mock_mp, "mediapipe.tasks": mock_tasks,
                                    "mediapipe.tasks.python": mock_python,
                                    "mediapipe.tasks.python.vision": mock_vision}):
        mp1, py1, vis1 = _get_mediapipe()
        mp2, py2, vis2 = _get_mediapipe()
        assert mp1 is mp2
        assert py1 is py2
        assert vis1 is vis2


def test_load_mp_image_pil_conversion(tmp_path):
    # Create a small dummy WebP image
    img_path = str(tmp_path / "test.webp")
    img = Image.new("RGB", (64, 64), color=(255, 0, 0))
    img.save(img_path, format="WEBP")

    mock_mp = MagicMock()
    mock_image_cls = MagicMock()
    mock_mp.Image = mock_image_cls

    with patch("bagheeraview.core.imagecontroller._get_mediapipe", return_value=(mock_mp, None, None)):
        _load_mp_image(img_path)
        assert mock_image_cls.called
        kwargs = mock_image_cls.call_args.kwargs
        assert "data" in kwargs
        assert isinstance(kwargs["data"], np.ndarray)
        assert kwargs["data"].shape == (64, 64, 3)


def test_detect_faces_mediapipe_webp(qapp, tmp_path):
    img_path = str(tmp_path / "test.webp")
    img = Image.new("RGB", (200, 200), color=(0, 255, 0))
    img.save(img_path, format="WEBP")

    controller = ImageController([], -1)
    try:
        mock_mp = MagicMock()
        mock_python = MagicMock()
        mock_vision = MagicMock()
        mock_detector = MagicMock()

        # Mock detector returning 1 detection
        mock_detection = MagicMock()
        mock_detection.bounding_box.origin_x = 10
        mock_detection.bounding_box.origin_y = 10
        mock_detection.bounding_box.width = 126
        mock_detection.bounding_box.height = 126

        mock_result = MagicMock()
        mock_result.detections = [mock_detection]
        mock_detector.detect.return_value = mock_result
        mock_vision.FaceDetector.create_from_options.return_value = mock_detector

        mock_mp_image = MagicMock()
        mock_mp_image.width = 200
        mock_mp_image.height = 200
        mock_mp.Image.return_value = mock_mp_image

        with patch("bagheeraview.core.imagecontroller._get_mediapipe", return_value=(mock_mp, mock_python, mock_vision)), \
             patch("os.path.exists", return_value=True), \
             patch("bagheeraview.core.imagecontroller._load_mp_image", return_value=mock_mp_image):

            faces = controller._detect_faces_mediapipe(img_path)
            assert len(faces) == 1
            assert faces[0]["type"] == "Face"
            assert faces[0]["w"] == 0.63
            assert faces[0]["h"] == 0.63
    finally:
        controller.cleanup()


def test_detect_faces_mediapipe_filters_tiny_regions(qapp, tmp_path):
    img_path = str(tmp_path / "test.webp")
    Image.new("RGB", (100, 100), color=(0, 255, 0)).save(img_path, format="WEBP")

    controller = ImageController([], -1)
    try:
        mock_mp = MagicMock()
        mock_python = MagicMock()
        mock_vision = MagicMock()
        mock_detector = MagicMock()
        small_detection = MagicMock()
        small_detection.bounding_box.origin_x = 10
        small_detection.bounding_box.origin_y = 10
        small_detection.bounding_box.width = 39
        small_detection.bounding_box.height = 39
        mock_result = MagicMock()
        mock_result.detections = [small_detection]
        mock_detector.detect.return_value = mock_result
        mock_vision.FaceDetector.create_from_options.return_value = mock_detector
        mock_mp_image = MagicMock()
        mock_mp_image.width = 100
        mock_mp_image.height = 100
        mock_mp.Image.return_value = mock_mp_image

        with patch("bagheeraview.core.imagecontroller._get_mediapipe",
                   return_value=(mock_mp, mock_python, mock_vision)), \
             patch("os.path.exists", return_value=True), \
             patch("bagheeraview.core.imagecontroller._load_mp_image",
                   return_value=mock_mp_image):
            assert controller._detect_faces_mediapipe(img_path) == []
            options = mock_vision.FaceDetectorOptions.call_args.kwargs
            assert options["min_detection_confidence"] == 0.7
    finally:
        controller.cleanup()


def test_minimum_region_size_applies_to_all_automatic_region_types(
        qapp):
    controller = ImageController([], -1)
    try:
        for region_type in ("Face", "Pet", "Body"):
            assert controller._create_region_from_pixels(
                10, 10, 79, 80, 200, 200, region_type) is None
            assert controller._create_region_from_pixels(
                10, 10, 80, 79, 200, 200, region_type) is None
            assert controller._create_region_from_pixels(
                10, 10, 80, 80, 200, 200, region_type) is not None
    finally:
        controller.cleanup()


def test_face_recognition_does_not_upsample_and_filters_tiny_regions(
        qapp, tmp_path):
    img_path = str(tmp_path / "test.jpg")
    Image.new("RGB", (100, 100), color=(0, 255, 0)).save(img_path)
    mock_face_recognition = MagicMock()
    mock_face_recognition.load_image_file.return_value = np.zeros((100, 100, 3))
    mock_face_recognition.face_locations.return_value = [(10, 49, 49, 10)]
    controller = ImageController([], -1)
    try:
        with patch("bagheeraview.core.imagecontroller._get_face_recognition",
                   return_value=mock_face_recognition):
            assert controller._detect_faces_face_recognition(img_path) == []
        mock_face_recognition.face_locations.assert_called_once_with(
            mock_face_recognition.load_image_file.return_value,
            number_of_times_to_upsample=0)
    finally:
        controller.cleanup()
