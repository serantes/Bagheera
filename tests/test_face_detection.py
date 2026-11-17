import numpy as np
from unittest.mock import MagicMock, patch
from PIL import Image

from bagheeraview.core.imagecontroller import (
    ImageController,
    _get_mediapipe,
    _load_mp_image
)


def test_get_mediapipe_caching():
    mock_mp = MagicMock()
    mock_python = MagicMock()
    mock_vision = MagicMock()

    with patch.dict("sys.modules", {"mediapipe": mock_mp, "mediapipe.tasks.python": mock_python,
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
        mock_detector.detect.return_value.detections = [small_detection]
        mock_vision.FaceDetector.create_from_options.return_value = mock_detector
        mock_mp_image = MagicMock(width=100, height=100)
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
                10, 10, 125, 126, 200, 200, region_type) is None
            assert controller._create_region_from_pixels(
                10, 10, 126, 125, 200, 200, region_type) is None
            assert controller._create_region_from_pixels(
                10, 10, 126, 126, 200, 200, region_type) is not None
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
