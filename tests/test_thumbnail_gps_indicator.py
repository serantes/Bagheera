import pytest

from bagheeraview.core import app as app_module


@pytest.mark.parametrize(
    ("coordinates", "expected"),
    [((40.0, -3.0), True), (None, False)],
)
def test_gps_lookup_worker_reports_geolocation(
        monkeypatch, coordinates, expected):
    monkeypatch.setattr(
        app_module.MetadataManager, "read_gps",
        lambda _path: coordinates)
    worker = app_module.GpsLookupWorker("/photos/image.jpg", 12.5, 0)
    results = []
    worker.signals.finished.connect(lambda *args: results.append(args))

    worker.run()

    assert results == [
        ("/photos/image.jpg", 12.5, 0, expected)]
