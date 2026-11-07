from PySide6.QtWidgets import QApplication, QListView
from PySide6.QtGui import QStandardItemModel

from bagheeraview.core.section_scrubber import SectionScrubber, build_sections


def test_build_sections_keeps_discontiguous_keys_separate():
    sections = build_sections(
        ["2026-01", "2026-01", "2026-02", "2026-02", "2026-01"],
        label_fn=lambda key: key.replace("-", "/"),
    )

    assert sections == [
        ("2026/01", 0, 2),
        ("2026/02", 2, 2),
        ("2026/01", 4, 1),
    ]


def test_scrubber_jump_targets_section_header():
    app = QApplication.instance() or QApplication([])

    class TrackingListView(QListView):
        def scrollTo(self, index, hint=QListView.ScrollHint.EnsureVisible):
            self.scrolled_to = (index.row(), hint)

    view = TrackingListView()
    model = QStandardItemModel()
    model.setColumnCount(1)
    model.insertRows(0, 8)
    view.setModel(model)
    scrubber = SectionScrubber(view)
    scrubber.resize(64, 100)
    scrubber.set_sections([("A", 0, 4), ("B", 4, 4)])
    scrubber.show()
    app.processEvents()

    scrubber._jump(99)

    assert view.scrolled_to[0] == 4
    assert view.scrolled_to[1] == QListView.ScrollHint.PositionAtTop
    scrubber.close()
    view.close()
    app.processEvents()


def test_tooltip_resolves_full_section_label_for_timeline_position():
    app = QApplication.instance() or QApplication([])
    view = QListView()
    scrubber = SectionScrubber(view)
    scrubber.resize(64, 100)
    scrubber.set_sections([
        ("A very long section label that is truncated visually", 0, 4),
        ("Another long section label", 4, 4),
    ], [
        "Group A - 12 images",
        "Group B - 8 images",
    ])

    section_index = scrubber._section_index_at_y(99)

    assert scrubber._sections[section_index][0] == "Another long section label"
    assert scrubber._tooltips[section_index] == "Group B - 8 images"
    scrubber.close()
    view.close()
    app.processEvents()
