import os
import tempfile
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


def test_remove_face_by_encoding(temp_db_dir):
    db = PersonRecognitionDB(db_path=temp_db_dir)
    encoding = [0.2 * i for i in range(128)]

    db.add_face("id_1", encoding, "Carlos")
    tag, _ = db.identify_person(encoding)
    assert tag == "Carlos"

    # Remove face encoding (e.g. when set to unrecognized)
    removed_count = db.remove_face_by_encoding(encoding)
    assert removed_count >= 1

    # Should no longer be identified
    tag_after, _ = db.identify_person(encoding)
    assert tag_after is None

