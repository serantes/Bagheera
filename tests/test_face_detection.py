import os
import numpy as np
from unittest.mock import MagicMock, patch
from PIL import Image

from bagheeraview.core.imagecontroller import (
    ImageController,
    _get_face_recognition,
    _get_mediapipe,
    _load_mp_image
)


def test_get_mediapipe_caching():
    mock_mp = MagicMock()
    mock_python = MagicMock()
    mock_vision = MagicMock()

    with patch.dict("sys.modules", {"mediapipe": mock_mp, "mediapipe.tasks.python": mock_python, "mediapipe.tasks.python.vision": mock_vision}):
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
    img = Image.new("RGB", (100, 100), color=(0, 255, 0))
    img.save(img_path, format="WEBP")

    controller = ImageController([], -1)

    mock_mp = MagicMock()
    mock_python = MagicMock()
    mock_vision = MagicMock()
    mock_detector = MagicMock()

    # Mock detector returning 1 detection
    mock_detection = MagicMock()
    mock_detection.bounding_box.origin_x = 10
    mock_detection.bounding_box.origin_y = 10
    mock_detection.bounding_box.width = 40
    mock_detection.bounding_box.height = 40

    mock_result = MagicMock()
    mock_result.detections = [mock_detection]
    mock_detector.detect.return_value = mock_result
    mock_vision.FaceDetector.create_from_options.return_value = mock_detector

    mock_mp_image = MagicMock()
    mock_mp_image.width = 100
    mock_mp_image.height = 100
    mock_mp.Image.return_value = mock_mp_image

    with patch("bagheeraview.core.imagecontroller._get_mediapipe", return_value=(mock_mp, mock_python, mock_vision)), \
         patch("os.path.exists", return_value=True), \
         patch("bagheeraview.core.imagecontroller._load_mp_image", return_value=mock_mp_image):

        faces = controller._detect_faces_mediapipe(img_path)
        assert len(faces) == 1
        assert faces[0]["type"] == "Face"
        assert faces[0]["w"] == 0.4
        assert faces[0]["h"] == 0.4
