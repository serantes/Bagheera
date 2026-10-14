from unittest.mock import MagicMock, patch
from PySide6.QtCore import QEvent, Qt, QPointF
from PySide6.QtGui import QMouseEvent, QPointingDevice
from bagheeraview.core.imageviewer import FaceCanvas
from bagheeraview.core.constants import APP_CONFIG


def test_facecanvas_left_click_with_shift_uses_last_name(qapp):
    APP_CONFIG["last_region_name"] = "StoredName"

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

    press_event = QMouseEvent(
        QEvent.Type.MouseButtonPress,
        pos_start,
        pos_start,
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.ShiftModifier,
        QPointingDevice.primaryPointingDevice()
    )
    canvas.mousePressEvent(press_event)

    move_event = QMouseEvent(
        QEvent.Type.MouseMove,
        pos_end,
        pos_end,
        Qt.MouseButton.NoButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.ShiftModifier,
        QPointingDevice.primaryPointingDevice()
    )
    canvas.mouseMoveEvent(move_event)

    release_event = QMouseEvent(
        QEvent.Type.MouseButtonRelease,
        pos_end,
        pos_end,
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.ShiftModifier,
        QPointingDevice.primaryPointingDevice()
    )

    with patch("bagheeraview.core.imageviewer.FaceNameDialog.get_name") as mock_dialog:
        canvas.mouseReleaseEvent(release_event)

        assert not mock_dialog.called
        viewer.controller.add_face.assert_called_once()
        args, kwargs = viewer.controller.add_face.call_args
        assert args[0] == "StoredName"


def test_facecanvas_left_click_with_shift_no_last_name_asks_dialog(qapp):
    APP_CONFIG["last_region_name"] = ""

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

    press_event = QMouseEvent(
        QEvent.Type.MouseButtonPress,
        pos_start,
        pos_start,
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.ShiftModifier,
        QPointingDevice.primaryPointingDevice()
    )
    canvas.mousePressEvent(press_event)

    move_event = QMouseEvent(
        QEvent.Type.MouseMove,
        pos_end,
        pos_end,
        Qt.MouseButton.NoButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.ShiftModifier,
        QPointingDevice.primaryPointingDevice()
    )
    canvas.mouseMoveEvent(move_event)

    release_event = QMouseEvent(
        QEvent.Type.MouseButtonRelease,
        pos_end,
        pos_end,
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.ShiftModifier,
        QPointingDevice.primaryPointingDevice()
    )

    with patch("bagheeraview.core.imageviewer.FaceNameDialog.get_name", return_value=("NewName", [], True)) as mock_dialog:
        canvas.mouseReleaseEvent(release_event)

        assert mock_dialog.called
        assert APP_CONFIG["last_region_name"] == "NewName"
        viewer.controller.add_face.assert_called_once()
        args, kwargs = viewer.controller.add_face.call_args
        assert args[0] == "NewName"


def test_facecanvas_middle_click_resets_last_name(qapp):
    APP_CONFIG["last_region_name"] = "OldName"

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

    press_event = QMouseEvent(
        QEvent.Type.MouseButtonPress,
        pos_start,
        pos_start,
        Qt.MouseButton.MiddleButton,
        Qt.MouseButton.MiddleButton,
        Qt.KeyboardModifier.NoModifier,
        QPointingDevice.primaryPointingDevice()
    )
    canvas.mousePressEvent(press_event)

    move_event = QMouseEvent(
        QEvent.Type.MouseMove,
        pos_end,
        pos_end,
        Qt.MouseButton.NoButton,
        Qt.MouseButton.MiddleButton,
        Qt.KeyboardModifier.NoModifier,
        QPointingDevice.primaryPointingDevice()
    )

    canvas.mouseMoveEvent(move_event)

    release_event = QMouseEvent(
        QEvent.Type.MouseButtonRelease,
        pos_end,
        pos_end,
        Qt.MouseButton.MiddleButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        QPointingDevice.primaryPointingDevice()
    )

    mock_action = MagicMock()
    mock_menu = MagicMock()
    mock_menu.addAction.return_value = mock_action
    mock_menu.exec.return_value = mock_action

    with patch("bagheeraview.core.imageviewer.QMenu", return_value=mock_menu), \
         patch("bagheeraview.core.imageviewer.FaceNameDialog.get_name",
               return_value=("DialogSelectedName", [], True)) as mock_dialog:

        canvas.mouseReleaseEvent(release_event)

        assert mock_dialog.called
        assert APP_CONFIG["last_region_name"] == "DialogSelectedName"
