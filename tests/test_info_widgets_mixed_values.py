import pytest
from PySide6.QtWidgets import QApplication

from bagheeraview.core import widgets


@pytest.fixture
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def attributes(monkeypatch):
    values = {}

    def get_attribute(path, name, default=""):
        return values.get((path, name), default)

    def set_attribute(path, name, value):
        if value is None:
            values.pop((path, name), None)
        else:
            values[(path, name)] = value

    monkeypatch.setattr(widgets.XattrManager, "get_attribute", get_attribute)
    monkeypatch.setattr(widgets.XattrManager, "set_attribute", set_attribute)
    return values


def test_rating_widget_marks_mixed_values_and_applies_to_all(
        qapp, attributes):
    paths = ["first.jpg", "second.jpg"]
    attributes[(paths[0], widgets.RATING_XATTR_NAME)] = "2"
    attributes[(paths[1], widgets.RATING_XATTR_NAME)] = "4"
    widget = widgets.RatingWidget()

    widget.set_files(paths)

    assert widget._current_rating == 2
    assert widget.rating_label.styleSheet() == "color: #d32f2f;"
    assert not widget.btn_apply.isHidden()

    widget.save_rating()

    assert all(
        attributes[(path, widgets.RATING_XATTR_NAME)] == "2"
        for path in paths)
    assert not widget._mixed_rating
    assert widget.btn_apply.isHidden()


def test_comment_widget_marks_mixed_values_and_applies_to_all(
        qapp, attributes):
    paths = ["first.jpg", "second.jpg"]
    attributes[(paths[0], widgets.XATTR_COMMENT_NAME)] = "first comment"
    attributes[(paths[1], widgets.XATTR_COMMENT_NAME)] = "second comment"
    widget = widgets.CommentWidget()

    widget.set_files(paths)

    assert widget.comment_edit.toPlainText() == "first comment"
    assert "color: #d32f2f" in widget.comment_edit.styleSheet()
    assert not widget.btn_apply.isHidden()

    widget.save_comment()

    assert all(
        attributes[(path, widgets.XATTR_COMMENT_NAME)] == "first comment"
        for path in paths)
    assert not widget._mixed_comment
    assert widget.btn_apply.isHidden()
