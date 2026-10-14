import math
import os
import tempfile

import numpy as np
import pytest
from PIL import Image, ImageDraw

from bagheeraview.core.constants import (
    SCANNER_SETTINGS_DEFAULTS, PERSON_RECOGNITION_DB_NAME
)
from bagheeraview.core.personrecognition import PersonRecognitionDB, extract_face_encoding


@pytest.fixture
def temp_db_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


def test_person_recognition_defaults():
    assert "person_recognition_enabled" in SCANNER_SETTINGS_DEFAULTS
    assert SCANNER_SETTINGS_DEFAULTS["person_recognition_enabled"] is False
    assert SCANNER_SETTINGS_DEFAULTS["unrecognized_person_tag"] == "Unrecognized"
    assert SCANNER_SETTINGS_DEFAULTS["unrecognized_person_action"] == "ask"
    assert PERSON_RECOGNITION_DB_NAME == b"person_recognition"


def test_person_recognition_db_persistence_and_matching(temp_db_dir):
    db = PersonRecognitionDB(db_path=temp_db_dir)

    # 128D encodings (like face_recognition)
    encoding1 = [0.1 * i for i in range(128)]
    # Slightly altered encoding for the same person
    encoding1_similar = [0.1 * i + 0.001 for i in range(128)]
    # Completely different encoding
    encoding2 = [0.5 * (i % 2) for i in range(128)]

    # Add multiple encodings mapping to the same person tag "Alice"
    res1 = db.add_face("id_alice_1", encoding1, "Alice")
    res2 = db.add_face("id_alice_2", encoding1_similar, "Alice")
    res3 = db.add_face("id_bob_1", encoding2, "Bob")

    assert res1 is True
    assert res2 is True
    assert res3 is True

    # Identify Alice with similar encoding
    matched_tag, matched_id = db.identify_person(encoding1_similar, tolerance=0.6)
    assert matched_tag == "Alice"

    # Identify Bob
    matched_tag_bob, _ = db.identify_person(encoding2, tolerance=0.6)
    assert matched_tag_bob == "Bob"

    # Unknown encoding should return None
    unknown_encoding = [10.0 for _ in range(128)]
    matched_unknown, _ = db.identify_person(unknown_encoding, tolerance=0.6)
    assert matched_unknown is None


def test_extract_face_encoding(temp_db_dir):
    # Create synthetic image file
    img_path = os.path.join(temp_db_dir, "test_face.png")
    img = Image.new("RGB", (100, 100), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.ellipse((20, 20, 80, 80), fill=(200, 100, 100))
    img.save(img_path)

    face_region = {"x": 0.5, "y": 0.5, "w": 0.6, "h": 0.6, "type": "Face"}
    encoding = extract_face_encoding(img_path, face_region)

    assert encoding is not None
    assert isinstance(encoding, list)
    assert len(encoding) > 0


def test_remove_face_by_source(temp_db_dir):
    db = PersonRecognitionDB(db_path=temp_db_dir)
    encoding = [0.2 * i for i in range(128)]
    img_path = os.path.join(temp_db_dir, "face_a.png")
    region = {"x": 0.5, "y": 0.5, "w": 0.4, "h": 0.4}

    db.add_face("id_1", encoding, "Carlos",
                source={"path": img_path, **region})
    tag, _ = db.identify_person(encoding)
    assert tag == "Carlos"

    # Remove the record created from this exact face region (e.g. when the
    # user marks the face as unrecognized).
    removed_count = db.remove_face_by_source(img_path, region)
    assert removed_count == 1
    assert db.count() == 0

    # Should no longer be identified
    tag_after, _ = db.identify_person(encoding)
    assert tag_after is None


def test_add_face_keeps_similar_distinct_person(temp_db_dir):
    """A similar (non-identical) encoding tagged with a different name must
    not delete the previously stored person."""
    db = PersonRecognitionDB(db_path=temp_db_dir)
    try:
        encoding1 = [0.1 * i for i in range(128)]
        encoding1_similar = [0.1 * i + 0.001 for i in range(128)]

        assert db.add_face("id_1", encoding1, "Alice") is True
        # Similar face, new tag: both records must survive.
        assert db.add_face("id_2", encoding1_similar, "Bob") is True

        assert db.count() == 2
        tag, face_id = db.identify_person(encoding1)
        assert tag == "Alice"
        assert face_id == "id_1"
        tag, face_id = db.identify_person(encoding1_similar)
        assert tag == "Bob"
        assert face_id == "id_2"
    finally:
        db.close()


def test_add_face_same_source_replaces(temp_db_dir):
    """Re-adding a face from the same photo + region replaces that face's own
    record instead of duplicating it."""
    db = PersonRecognitionDB(db_path=temp_db_dir)
    try:
        encoding = [0.2 * i for i in range(128)]
        img_path = os.path.join(temp_db_dir, "face_a.png")
        region = {"x": 0.5, "y": 0.5, "w": 0.4, "h": 0.4}
        source = {"path": img_path, **region}

        assert db.add_face("id_1", encoding, "Alice", source=source) is True
        # Same face re-tagged: the old record is replaced, not duplicated.
        assert db.add_face("id_2", encoding, "Alice", source=source) is True

        assert db.count() == 1
        assert db.get_all_faces()[0]["face_id"] == "id_2"
    finally:
        db.close()


def test_add_face_source_scoped_replacement(temp_db_dir):
    """Editing one face must never delete a different face's reference, even
    when their encodings are nearly identical (the case where recognition
    misidentified the person)."""
    db = PersonRecognitionDB(db_path=temp_db_dir)
    try:
        rng = np.random.RandomState(7)
        a = rng.rand(128).astype(np.float32)
        b = a + 0.02  # ~0.226 -> well inside the 0.6 tolerance
        assert float(np.linalg.norm(a - b)) < 0.6

        img_a = os.path.join(temp_db_dir, "alice.jpg")
        img_b = os.path.join(temp_db_dir, "bob.jpg")
        region_a = {"x": 0.5, "y": 0.5, "w": 0.4, "h": 0.4}
        region_b = {"x": 0.5, "y": 0.5, "w": 0.4, "h": 0.4}

        assert db.add_face("id_alice", a.tolist(), "Alice",
                           source={"path": img_a, **region_a}) is True
        # Bob's face is auto-identified as Alice (similar encoding) but comes
        # from a different photo: it must get its own record.
        assert db.add_face("id_bob", b.tolist(), "Bob",
                           source={"path": img_b, **region_b}) is True
        assert db.count() == 2

        # Rename Bob -> Robert: only Bob's record is replaced. Alice's
        # reference (the one the auto-identification matched) survives.
        assert db.add_face("id_robert", b.tolist(), "Robert",
                           source={"path": img_b, **region_b}) is True
        assert db.count() == 2
        tags = sorted({rec["tag"] for rec in db.get_all_faces()})
        assert tags == ["Alice", "Robert"]
        tag, _ = db.identify_person(a)
        assert tag == "Alice"
        tag, _ = db.identify_person(b)
        assert tag == "Robert"
    finally:
        db.close()


def test_remove_face_by_source_scoped(temp_db_dir):
    """remove_face_by_source only deletes the record created from the target
    face; similar records of other people are left untouched."""
    db = PersonRecognitionDB(db_path=temp_db_dir)
    try:
        rng = np.random.RandomState(11)
        a = rng.rand(128).astype(np.float32)
        b = a + 0.02  # ~0.226 -> well inside the 0.6 tolerance
        assert float(np.linalg.norm(a - b)) < 0.6

        img_a = os.path.join(temp_db_dir, "alice.jpg")
        img_b = os.path.join(temp_db_dir, "bob.jpg")
        region_a = {"x": 0.5, "y": 0.5, "w": 0.4, "h": 0.4}
        region_b = {"x": 0.5, "y": 0.5, "w": 0.4, "h": 0.4}

        assert db.add_face("id_a", a.tolist(), "Alice",
                           source={"path": img_a, **region_a}) is True
        assert db.add_face("id_b", b.tolist(), "Bob",
                           source={"path": img_b, **region_b}) is True

        removed = db.remove_face_by_source(img_b, region_b)
        assert removed == 1
        assert db.count() == 1
        tag, _ = db.identify_person(a)
        assert tag == "Alice"
    finally:
        db.close()


def test_identify_person_respects_caller_tolerance(temp_db_dir):
    """Callers can tighten the tolerance below the default threshold."""
    db = PersonRecognitionDB(db_path=temp_db_dir)
    try:
        encoding1 = [0.1 * i for i in range(128)]
        encoding1_similar = [0.1 * i + 0.001 for i in range(128)]
        db.add_face("id_alice", encoding1, "Alice")

        tag, _ = db.identify_person(encoding1_similar, tolerance=0.001)
        assert tag is None
        tag, _ = db.identify_person(encoding1_similar, tolerance=0.6)
        assert tag == "Alice"
    finally:
        db.close()


def test_add_face_rejects_invalid_input(temp_db_dir):
    """Invalid tags or encodings must be rejected without side effects."""
    db = PersonRecognitionDB(db_path=temp_db_dir)
    try:
        assert db.add_face("bad_1", [float("nan")] * 128, "Tag") is False
        assert db.add_face("bad_2", [0.1 * i for i in range(128)], "") is False
        assert db.add_face("bad_3", None, "Tag") is False
        assert db.add_face(None, None, None) is False
        assert db.count() == 0
    finally:
        db.close()


def test_close_and_reopen_same_path(temp_db_dir):
    """Closing an environment allows it to be reopened at the same path."""
    db = PersonRecognitionDB(db_path=temp_db_dir)
    encoding = [0.3 * i for i in range(128)]
    assert db.add_face("id_1", encoding, "Carlos") is True
    db.close()

    reopened = PersonRecognitionDB(db_path=temp_db_dir)
    try:
        assert reopened.count() == 1
        tag, _ = reopened.identify_person(encoding)
        assert tag == "Carlos"
    finally:
        reopened.close()


def test_find_matches_returns_ordered_results(temp_db_dir):
    """find_matches returns records sorted by ascending distance."""
    db = PersonRecognitionDB(db_path=temp_db_dir)
    try:
        encoding1 = [0.1 * i for i in range(128)]
        encoding1_similar = [0.1 * i + 0.001 for i in range(128)]
        encoding2 = [0.5 * (i % 2) for i in range(128)]
        db.add_face("id_1", encoding1, "Alice")
        db.add_face("id_2", encoding2, "Bob")

        matches = db.find_matches(encoding1_similar)
        assert [m["face_id"] for m in matches] == ["id_1"]
        assert "distance" in matches[0]
        assert math.isfinite(matches[0]["distance"])
    finally:
        db.close()


def test_find_matches_stays_correct_across_writes(temp_db_dir):
    """find_matches stays correct across cache-invalidating writes."""
    db = PersonRecognitionDB(db_path=temp_db_dir)
    try:
        encoding1 = [0.1 * i for i in range(128)]
        encoding1_similar = [0.1 * i + 0.001 for i in range(128)]
        encoding2 = [0.5 * (i % 2) for i in range(128)]

        db.add_face("id_1", encoding1, "Alice")
        db.add_face("id_2", encoding2, "Bob")

        # Build the stacked-matrix cache and exercise it.
        assert [m["face_id"] for m in db.find_matches(encoding1_similar)] == ["id_1"]
        assert [m["face_id"] for m in db.find_matches(encoding2)] == ["id_2"]

        # Adding a record must invalidate and rebuild the cache.
        encoding3 = [0.3 * i for i in range(128)]
        assert db.add_face("id_3", encoding3, "Carol") is True
        assert [m["face_id"] for m in db.find_matches(encoding1_similar)] == ["id_1"]
        assert [m["face_id"] for m in db.find_matches(encoding3)] == ["id_3"]

        # Removing a record must invalidate the cache again.
        assert db.remove_face("id_2") is True
        assert db.find_matches(encoding2) == []
        assert [m["face_id"] for m in db.find_matches(encoding1_similar)] == ["id_1"]
    finally:
        db.close()


def test_count_and_remove_face(temp_db_dir):
    """count / __len__ and remove_face operate on individual records."""
    db = PersonRecognitionDB(db_path=temp_db_dir)
    try:
        encoding1 = [0.1 * i for i in range(128)]
        encoding2 = [0.5 * (i % 2) for i in range(128)]
        assert db.add_face("id_1", encoding1, "Alice") is True
        assert db.add_face("id_2", encoding2, "Bob") is True
        assert db.count() == 2
        assert len(db) == 2

        assert db.remove_face("id_1") is True
        assert db.count() == 1
        assert db.remove_face("missing") is False
        assert db.count() == 1
    finally:
        db.close()


def test_extract_face_encoding_invalid_region(temp_db_dir):
    """extract_face_encoding returns None for invalid inputs."""
    img_path = os.path.join(temp_db_dir, "test_face.png")
    img = Image.new("RGB", (100, 100), color=(255, 255, 255))
    img.save(img_path)

    valid = {"x": 0.5, "y": 0.5, "w": 0.6, "h": 0.6}
    assert extract_face_encoding(None, valid) is None
    assert extract_face_encoding("", valid) is None
    assert extract_face_encoding(img_path, None) is None
    assert extract_face_encoding(img_path, [0.5, 0.5, 0.6, 0.6]) is None
    assert extract_face_encoding(img_path, {"x": 0.5, "y": 0.5, "w": 0, "h": 0.6}) is None
    assert extract_face_encoding(img_path, {"x": 0.5, "y": 0.5, "w": -1, "h": 0.6}) is None
    assert extract_face_encoding(img_path, {"x": "a", "y": 0.5, "w": 0.6, "h": 0.6}) is None
    assert extract_face_encoding(os.path.join(temp_db_dir, "missing.png"), valid) is None

    # A valid region still produces a feature vector.
    encoding = extract_face_encoding(img_path, valid)
    assert encoding is not None
    assert isinstance(encoding, list)
    assert len(encoding) > 0
