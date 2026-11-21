=========
Changelog
=========

Unreleased
==========

Version 1.2.0
=============

- Added search navigation with history and Baloo tag selection, and made
  direct paths start in flat grouping.
- Added batch face and pet detection, recursive region scanning and region
  data removal; improved duplicate detection with AI vector similarity.
- Added similar-image search, richer bookmark grouping and sorting, and
  thumbnail group-selection commands.
- Improved filmstrip thumbnail prioritization, EXIF orientation handling and
  cache invalidation; added warnings for unsupported image modifications.
- Improved image loading and resizing, and reduced startup cost by loading
  optional person-recognition dependencies lazily.

Version 1.1.0
=============

- BagheeraSearch: replaced the ``--having``, ``--subquery`` and
  ``--subquery-having`` options with ``HAVING`` and ``SUBQUERY`` clauses.
  Existing commands using the removed options must be updated.
- Added multiple subqueries combined with AND, OR, NOT and exclusive OR.
  An empty ``SUBQUERY`` searches the contents of the selected folders; an
  empty ``HAVING`` is ignored.
- Date and type options filter subquery results when subqueries are present;
  otherwise they apply to the main search. Fixed folders incorrectly returned
  as files when Baloo indexes their type incorrectly.
- BagheeraView: added support for the new syntax with the integrated
  BagheeraSearch engine.
- BagheeraGui: added editable subquery rows and HAVING controls, contextual
  help and clear buttons; improved the layout, pagination controls, path
  display and icon performance guidance.
- Updated search help and manuals, and added tests for the search syntax,
  combined results and graphical integrations.
- Improved desktop integration and packaging, and fixed GPU availability
  checks in the duplicate manager.
- Duplicate manager: new tabbed comparison interface (Side by Side / Overlay),
  a second tab bar inside Overlay with Toggle, Split, Difference and Opacity
  sub-modes, per-layer independent zoom and pan (Shift / Ctrl to target a
  single layer), fit/1:1 double click, Split and Opacity resets, overlay
  legend that follows the visible layer, and a new Overwrite action that
  renames the selected image over the other one (with confirmation).
- Duplicate list: the similarity percentage is now colored inside the %
  column instead of showing a separate label; the Link Panes button moved to
  the bottom action bar and is configurable (L); the overlay controls gained
  hotkey tooltips.

Version 1.0.0
=============

- Added bagheragui, Bagheera search tool gui
- Added bagherasearch, Bagheera search tool
- Added bagheraview, Bagheera image viewer
