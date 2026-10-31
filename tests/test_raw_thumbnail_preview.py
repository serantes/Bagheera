from types import SimpleNamespace

from PySide6.QtCore import QBuffer, QIODevice
from PySide6.QtGui import QImage

from bagheeraview.core import imagescanner


def _jpeg_bytes(width, height):
    image = QImage(width, height, QImage.Format_RGB32)
    image.fill(0xFF336699)
    buffer = QBuffer()
    buffer.open(QIODevice.WriteOnly)
    image.save(buffer, "JPEG")
    return bytes(buffer.data())


def test_raw_thumbnail_prefers_best_sized_embedded_jpeg(monkeypatch, tmp_path):
    small = SimpleNamespace(
        mimeType="image/jpeg", extension="jpg", width=320, height=160)
    large = SimpleNamespace(
        mimeType="image/jpeg", extension="jpg", width=1600, height=800)
    non_jpeg = SimpleNamespace(
        mimeType="image/tiff", extension="tif", width=2400, height=1800)
    selected = []
    preview_data = _jpeg_bytes(800, 400)

    class Preview:
        def data(self):
            return memoryview(preview_data)

    class PreviewManager:
        def __init__(self, _image):
            pass

        def getPreviewProperties(self):
            return small, large, non_jpeg

        def getPreviewImage(self, properties):
            selected.append(properties)
            return Preview()

    class Image:
        def readMetadata(self):
            pass

    fake_exiv2 = SimpleNamespace(
        ImageFactory=SimpleNamespace(open=lambda _path: Image()),
        PreviewManager=PreviewManager,
    )
    monkeypatch.setattr(imagescanner, "exiv2", fake_exiv2)
    raw_path = tmp_path / "image.NRW"
    raw_path.write_bytes(b"not decoded as a full RAW")

    thumbnail = imagescanner.generate_thumbnail(str(raw_path), 500)

    assert selected == [large]
    assert (thumbnail.width(), thumbnail.height()) == (500, 250)


def test_raw_without_embedded_preview_falls_back_to_image_reader(
        monkeypatch, tmp_path):
    class Image:
        def readMetadata(self):
            pass

    class PreviewManager:
        def __init__(self, _image):
            pass

        def getPreviewProperties(self):
            return ()

    monkeypatch.setattr(
        imagescanner, "exiv2",
        SimpleNamespace(
            ImageFactory=SimpleNamespace(open=lambda _path: Image()),
            PreviewManager=PreviewManager,
        ))
    jpeg_path = tmp_path / "image.nrw"
    jpeg_path.write_bytes(_jpeg_bytes(80, 40))

    thumbnail = imagescanner.generate_thumbnail(str(jpeg_path), 40)

    assert (thumbnail.width(), thumbnail.height()) == (40, 20)
