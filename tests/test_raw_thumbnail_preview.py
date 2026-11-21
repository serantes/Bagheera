import os
from io import BytesIO
from types import SimpleNamespace

import pytest
from PIL import Image, ImageOps
from PySide6.QtCore import QBuffer, QIODevice
from PySide6.QtGui import QImage

from bagheeraview.core import imagescanner


def _jpeg_bytes(width, height, orientation=None):
    image = QImage(width, height, QImage.Format_RGB32)
    image.fill(0xFF336699)
    buffer = QBuffer()
    buffer.open(QIODevice.WriteOnly)
    image.save(buffer, "JPEG")
    data = bytes(buffer.data())
    if orientation is not None:
        with Image.open(BytesIO(data)) as jpeg:
            exif = jpeg.getexif()
            exif[274] = orientation
            output = BytesIO()
            jpeg.save(output, format="JPEG", exif=exif)
            data = output.getvalue()
    return data


def _exif_data(orientation):
    class Exif:
        def findKey(self, key):
            assert key == "Exif.Image.Orientation"
            return (SimpleNamespace(toString=lambda: str(orientation))
                    if orientation is not None else None)

        def end(self):
            return None

    return Exif()


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

        def exifData(self):
            return _exif_data(None)

    fake_exiv2 = SimpleNamespace(
        ImageFactory=SimpleNamespace(open=lambda _path: Image()),
        PreviewManager=PreviewManager,
        ExifKey=lambda key: key,
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


@pytest.mark.parametrize(
    ("extension", "orientation"),
    [(extension, orientation) for extension in ("png", "webp")
     for orientation in range(1, 9)] + [("jpg", 6), ("tiff", 8)])
@pytest.mark.parametrize("use_fd", [False, True])
def test_thumbnail_respects_exif_orientation(tmp_path, extension, orientation, use_fd):
    path = tmp_path / f"oriented.{extension}"
    original = Image.new("RGB", (64, 40))
    for y in range(40):
        for x in range(64):
            original.putpixel((x, y), (
                230 if x < 32 else 20,
                230 if y < 20 else 20,
                30 if x < 32 else 200))
    exif = original.getexif()
    exif[274] = orientation
    original.save(path, exif=exif)
    with Image.open(path) as stored:
        expected = ImageOps.exif_transpose(stored).convert("RGB")

    fd = os.open(path, os.O_RDONLY) if use_fd else None
    try:
        thumbnail = imagescanner.generate_thumbnail(str(path), 64, fd=fd)
    finally:
        if fd is not None:
            os.close(fd)

    assert (thumbnail.width(), thumbnail.height()) == expected.size
    for x, y in ((5, 5), (expected.width - 6, 5),
                 (5, expected.height - 6),
                 (expected.width - 6, expected.height - 6)):
        actual = thumbnail.pixelColor(x, y).getRgb()[:3]
        assert all(abs(a - b) <= 8 for a, b in zip(actual, expected.getpixel((x, y))))


@pytest.mark.parametrize(
    ("raw_orientation", "preview_orientation", "expected_size"),
    [(6, None, (20, 40)), (6, 6, (20, 40)),
     (6, 1, (40, 20)), (1, None, (40, 20)), (2, None, (40, 20))])
def test_raw_preview_uses_its_own_or_parent_orientation(
        monkeypatch, tmp_path, raw_orientation, preview_orientation, expected_size):
    original = Image.new("RGB", (80, 40), "red")
    original.paste("blue", (40, 0, 80, 40))
    exif = original.getexif()
    if preview_orientation is not None:
        exif[274] = preview_orientation
    buffer = BytesIO()
    original.save(buffer, format="JPEG", exif=exif)
    data = buffer.getvalue()
    with Image.open(BytesIO(data)) as stored:
        if preview_orientation is None:
            stored.getexif()[274] = raw_orientation
        expected = ImageOps.exif_transpose(stored).convert("RGB")
        expected = expected.resize(expected_size, Image.Resampling.LANCZOS)
    properties = SimpleNamespace(
        mimeType="image/jpeg", extension="jpg", width=80, height=40)

    class RawImage:
        def readMetadata(self):
            pass

        def exifData(self):
            return _exif_data(raw_orientation)

    class PreviewManager:
        def __init__(self, _image):
            pass

        def getPreviewProperties(self):
            return [properties]

        def getPreviewImage(self, _properties):
            return SimpleNamespace(data=lambda: memoryview(data))

    monkeypatch.setattr(imagescanner, "exiv2", SimpleNamespace(
        ImageFactory=SimpleNamespace(open=lambda _path: RawImage()),
        PreviewManager=PreviewManager, ExifKey=lambda key: key))
    path = tmp_path / "image.raw"
    path.touch()

    thumbnail = imagescanner.generate_thumbnail(str(path), 40)

    assert (thumbnail.width(), thumbnail.height()) == expected_size
    for x, y in ((4, 4), (expected.width - 5, expected.height - 5)):
        actual = thumbnail.pixelColor(x, y).getRgb()[:3]
        assert all(abs(a - b) <= 8 for a, b in zip(actual, expected.getpixel((x, y))))
