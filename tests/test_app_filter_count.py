from types import SimpleNamespace

from bagheeraview.core.app import MainWindow
from bagheeraview.core.constants import UITexts


def test_filter_counts_only_visible_and_total_images():
    filter_mode = SimpleNamespace(isChecked=lambda: True)
    window = SimpleNamespace(
        tags_list=SimpleNamespace(rowCount=lambda: 0),
        filter_mode_group=SimpleNamespace(buttons=lambda: [filter_mode]),
        is_cleaning=False,
        _suppress_updates=False,
        get_selected_paths=lambda: [],
        proxy_model=SimpleNamespace(
            include_tags=set(),
            exclude_tags=set(),
            name_filter="",
            excluded_extensions=set(),
            match_mode="AND",
            prepare_filter=lambda: None,
            invalidate=lambda: None,
            rowCount=lambda: 6,
        ),
        filter_name_input=SimpleNamespace(text=lambda: "sun"),
        _extension_checkboxes={},
        _visible_paths_cache=None,
        get_visible_image_paths=lambda: ["/photos/sun1.jpg", "/photos/sun2.jpg",
                                         "/photos/sun3.jpg"],
        get_all_image_paths=lambda: ["/photos/sun1.jpg", "/photos/sun2.jpg",
                                     "/photos/sun3.jpg", "/photos/other.jpg"],
        filter_stats_lbl=SimpleNamespace(setText=lambda text: setattr(
            window.filter_stats_lbl, "text", text)),
        filtered_count_lbl=SimpleNamespace(setText=lambda text: setattr(
            window.filtered_count_lbl, "text", text)),
        restore_selection=lambda paths: None,
        update_viewers_filter=lambda paths: setattr(
            window, "visible_paths_sent_to_viewers", paths),
    )

    MainWindow.apply_filters(window)

    assert window.filtered_count_lbl.text == UITexts.FILTERED_COUNT.format(3)
    assert window.filter_stats_lbl.text == UITexts.FILTER_STATS_HIDDEN.format(1, 3)
    assert window.visible_paths_sent_to_viewers == [
        "/photos/sun1.jpg",
        "/photos/sun2.jpg",
        "/photos/sun3.jpg",
    ]
