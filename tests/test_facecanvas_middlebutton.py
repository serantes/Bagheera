import os
from unittest.mock import MagicMock, patch
from PySide6.QtCore import Qt, QPoint, QRect, QPointF
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication
from bagheeraview.core.imageviewer import FaceCanvas


def test_facecanvas_middle_button_region_selection(qapp):
    viewer = MagicMock()
    viewer.controller = MagicMock()
    viewer.controller.show_faces = True
    viewer.controller.faces = []
    viewer.crop_mode = False
    viewer.viewer = MagicMock()
    viewer.viewer._next_region_type = "Face"
    viewer.main_win = None

    canvas = FaceCanvas(viewer)
    canvas.resize(400, 400)

    pos_start = QPointF(10, 10)
    pos_end = QPointF(100, 100)

    # 1. Simulate mouse press with MiddleButton at (10, 10)
    press_event = QMouseEvent(
        QMouseEvent.Type.MouseButtonPress,
        pos_start,
        Qt.MouseButton.MiddleButton,
        Qt.MouseButton.MiddleButton,
        Qt.KeyboardModifier.NoModifier
    )
    canvas.mousePressEvent(press_event)

    assert canvas.drawing is True
    assert canvas.drawing_button == Qt.MouseButton.MiddleButton
    assert canvas.start_pos == QPoint(10, 10)

    # Simulate mouse move to (100, 100)
    move_event = QMouseEvent(
        QMouseEvent.Type.MouseMove,
        pos_end,
        Qt.MouseButton.NoButton,
        Qt.MouseButton.MiddleButton,
        Qt.KeyboardModifier.NoModifier
    )
    canvas.mouseMoveEvent(move_event)

    # Simulate mouse release with MiddleButton at (100, 100)
    release_event = QMouseEvent(
        QMouseEvent.Type.MouseButtonRelease,
        pos_end,
        Qt.MouseButton.MiddleButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier
    )

    mock_action = MagicMock()
    mock_menu = MagicMock()
    mock_menu.addAction.return_value = mock_action
    mock_menu.exec.return_value = mock_action

    with patch("bagheeraview.core.imageviewer.QMenu", return_value=mock_menu) as mock_qmenu_cls, \
         patch("bagheeraview.core.imageviewer.FaceNameDialog.get_name", return_value=("tag1", [], True)):

        canvas.mouseReleaseEvent(release_event)

        assert mock_qmenu_cls.called
        assert mock_menu.exec.called
        assert viewer.controller.add_face.called


def test_facecanvas_left_button_without_ctrl(qapp):
    viewer = MagicMock()
    viewer.controller = MagicMock()
    viewer.controller.show_faces = True
    viewer.controller.faces = []
    viewer.crop_mode = False
    viewer.viewer = MagicMock()
    viewer.viewer._next_region_type = "Face"
    viewer.main_win = None

    canvas = FaceCanvas(viewer)
    canvas.resize(400, 400)

    pos_start = QPointF(10, 10)
    pos_end = QPointF(100, 100)

    # Left button press
    press_event = QMouseEvent(
        QMouseEvent.Type.MouseButtonPress,
        pos_start,
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier
    )
    canvas.mousePressEvent(press_event)

    # Left button move
    move_event = QMouseEvent(
        QMouseEvent.Type.MouseMove,
        pos_end,
        Qt.MouseButton.NoButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier
    )
    canvas.mouseMoveEvent(move_event)

    # Left button release without Ctrl
    release_event = QMouseEvent(
        QMouseEvent.Type.MouseButtonRelease,
        pos_end,
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier
    )

    mock_menu = MagicMock()
    with patch("bagheeraview.core.imageviewer.QMenu", return_value=mock_menu) as mock_qmenu_cls, \
         patch("bagheeraview.core.imageviewer.FaceNameDialog.get_name", return_value=("tag1", [], True)):

        canvas.mouseReleaseEvent(release_event)

        assert not mock_qmenu_cls.called
        assert viewer.controller.add_face.called
