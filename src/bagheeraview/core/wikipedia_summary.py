#!/bin/env python
"""wikipedia_summary - small client for Wikipedia page summaries.

Uses only the Python standard library (no extra dependencies).

Library usage::

    from wikipedia_summary import get_summary, fetch_thumbnail, fetch_html, WikipediaNotFound, select_wikipedia_summary

    try:
        s = get_summary("Gato", lang=["es", "en"], fallback_search=True)
    except WikipediaNotFound:
        s = None
    else:
        print(s.title, "-", s.extract)
        html_content = fetch_html(s.url, s.lang)

    # Launch GUI selector
    # selected_md = select_wikipedia_summary("Python", languages="en,es,gl,ja,ko,zh")

Command line usage::

    python wikipedia_summary.py --gui
    python wikipedia_summary.py "Gato" --gui
    python wikipedia_summary.py "Gato" --markdown > gato.md
"""
from __future__ import annotations

import argparse
import base64
import json
import re
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from functools import lru_cache
from typing import Any, Iterable, List, Optional, Tuple

__all__ = [
    "WikipediaError",
    "WikipediaNotFound",
    "WikipediaNetworkError",
    "WikipediaSummary",
    "get_summary",
    "get_markdown",
    "search",
    "search_with_lang",
    "fetch_image",
    "fetch_thumbnail",
    "fetch_html",
    "set_user_agent",
    "clear_cache",
    "WikipediaSelectorDialog",
    "select_wikipedia_summary",
]

# --- Configuration ----------------------------------------------------------

USER_AGENT = "BagheeraView/1.0 (kde@aynoa.net)"
DEFAULT_LANG = "en"
TIMEOUT = 10.0                      # seconds
MAX_IMAGE_BYTES = 5 * 1024 * 1024   # refuse to download bigger images
MAX_HTML_BYTES = 10 * 1024 * 1024   # refuse to download huge HTML files

_LANG_RE = re.compile(r"^[a-z]{2,3}(-[a-z0-9]+)*$")


# --- Exceptions -------------------------------------------------------------

class WikipediaError(Exception):
    """Base class for all errors raised by this module."""


class WikipediaNotFound(WikipediaError):
    """The requested article does not exist."""


class WikipediaNetworkError(WikipediaError):
    """Network failure, timeout or unexpected HTTP status."""


# --- Markdown helpers -------------------------------------------------------

_MD_SPECIAL = re.compile(r"([\\`*_\[\]<>])")
_MD_BULLET = re.compile(r"^(\s*)([#+\-])(?=\s)", re.MULTILINE)
_MD_ORDERED = re.compile(r"^(\s*\d+)([.)])(?=\s)", re.MULTILINE)

# Labels used in the generated Markdown (fallback: English).
_MD_LABELS = {
    "en": {"location": "Location", "source": "Source"},
    "es": {"location": "Ubicación", "source": "Fuente"},
    "fr": {"location": "Emplacement", "source": "Source"},
    "de": {"location": "Standort", "source": "Quelle"},
    "pt": {"location": "Localização", "source": "Fonte"},
    "it": {"location": "Posizione", "source": "Fonte"},
    "gl": {"location": "Ubicación", "source": "Fonte"},
    "ja": {"location": "位置", "source": "出典"},
    "ko": {"location": "위치", "source": "출처"},
    "zh": {"location": "位置", "source": "来源"},
}

_CC_BY_SA_URL = "https://creativecommons.org/licenses/by-sa/4.0/"


def _escape_md(text: str) -> str:
    """Escape characters that Markdown would interpret as formatting."""
    text = _MD_SPECIAL.sub(r"\\\1", text)
    text = _MD_BULLET.sub(r"\1\\\2", text)
    return _MD_ORDERED.sub(r"\1\\\2", text)


def _md_url(url: str) -> str:
    """Make a URL safe inside a Markdown link or image."""
    return url.replace(" ", "%20").replace("(", "%28").replace(")", "%29")


# --- Data -------------------------------------------------------------------

@dataclass(frozen=True)
class WikipediaSummary:
    """Summary of a Wikipedia article."""

    title: str
    extract: str                       # plain-text summary
    lang: str
    description: Optional[str] = None  # one-line description
    page_type: str = "standard"        # standard, disambiguation, no-extract...
    url: Optional[str] = None          # link to the article
    thumbnail_url: Optional[str] = None
    thumbnail_width: Optional[int] = None
    thumbnail_height: Optional[int] = None
    image_url: Optional[str] = None    # full-size image
    latitude: Optional[float] = None
    longitude: Optional[float] = None

    @property
    def is_disambiguation(self) -> bool:
        """True when the title matches several articles."""
        return self.page_type == "disambiguation"

    def attribution(self) -> str:
        """Attribution line required by the CC BY-SA 4.0 license."""
        link = self.url or f"https://{self.lang}.wikipedia.org/"
        return f"Source: Wikipedia ({link}), CC BY-SA 4.0"

    def to_markdown(self, *, heading_level: int = 1, include_image: bool = True,
                    image_src: Optional[str] = None,
                    include_coordinates: bool = True,
                    include_attribution: bool = True) -> str:
        """Return the summary as well-formatted Markdown."""
        lang_prefix = self.lang.split("-")[0].lower()
        labels = _MD_LABELS.get(lang_prefix, _MD_LABELS["en"])
        level = min(max(int(heading_level), 1), 6)
        blocks = [f"{'#' * level} {_escape_md(self.title)}"]

        if self.description:
            blocks.append(f"*{_escape_md(self.description)}*")

        src = image_src or self.thumbnail_url
        if include_image and src:
            blocks.append(f"![{_escape_md(self.title)}]({_md_url(src)})")

        paragraphs = [p.strip() for p in self.extract.splitlines() if p.strip()]
        blocks.extend(_escape_md(p) for p in paragraphs)

        if (include_coordinates and self.latitude is not None
                and self.longitude is not None):
            lat, lon = self.latitude, self.longitude
            osm = (f"https://www.openstreetmap.org/?mlat={lat:.5f}"
                   f"&mlon={lon:.5f}#map=12/{lat:.5f}/{lon:.5f}")
            blocks.append(
                f"**{labels['location']}:** [{lat:.5f}, {lon:.5f}]({osm})")

        if include_attribution:
            link = self.url or f"https://{self.lang}.wikipedia.org/"
            blocks.append("---")
            blocks.append(
                f"*{labels['source']}: [Wikipedia]({_md_url(link)}) · "
                f"[CC BY-SA 4.0]({_CC_BY_SA_URL})*")

        return "\n\n".join(blocks) + "\n"

    def to_dict(self) -> dict:
        """Return the summary as a plain dictionary."""
        return asdict(self)


# --- Internals --------------------------------------------------------------

def set_user_agent(user_agent: str) -> None:
    """Set the User-Agent sent with every request."""
    global USER_AGENT
    USER_AGENT = user_agent


def clear_cache() -> None:
    """Forget the summaries cached in memory."""
    _fetch_summary.cache_clear()


def _check_langs(lang: Optional[str | Iterable[str]]) -> List[str]:
    if lang is None:
        return [DEFAULT_LANG]
    if isinstance(lang, str):
        parts = [p.strip().lower() for p in re.split(r"[,;\s]+", lang) if p.strip()]
        if not parts:
            parts = [DEFAULT_LANG]
    elif isinstance(lang, (list, tuple, set)):
        flat = []
        for item in lang:
            if isinstance(item, str):
                parts = [p.strip().lower() for p in re.split(r"[,;\s]+", item) if p.strip()]
                flat.extend(parts)
            else:
                flat.append(str(item).strip().lower())
        parts = flat if flat else [DEFAULT_LANG]
    else:
        parts = [str(lang).strip().lower()]

    validated = []
    for code in parts:
        if not _LANG_RE.match(code):
            raise ValueError(f"Invalid language code: {code!r}")
        validated.append(code)

    seen = set()
    unique_langs = []
    for code in validated:
        if code not in seen:
            seen.add(code)
            unique_langs.append(code)

    return unique_langs or [DEFAULT_LANG]


def _http_get(url: str, accept: str = "application/json",
              max_bytes: Optional[int] = None) -> bytes:
    request = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Accept": accept})

    context = ssl.create_default_context()
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT, context=context) as response:
            data = response.read(max_bytes + 1) if max_bytes else response.read()
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError, ssl.SSLError):
        try:
            insecure_context = ssl._create_unverified_context()
            with urllib.request.urlopen(request, timeout=TIMEOUT, context=insecure_context) as response:
                data = response.read(max_bytes + 1) if max_bytes else response.read()
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                raise WikipediaNotFound(url) from exc
            raise WikipediaNetworkError(f"HTTP {exc.code} for {url}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise WikipediaNetworkError(f"{exc} ({url})") from exc

    if max_bytes and len(data) > max_bytes:
        raise WikipediaError(f"Response larger than {max_bytes} bytes: {url}")
    return data


def _get_json(url: str) -> Any:
    raw = _http_get(url)
    try:
        return json.loads(raw.decode("utf-8"))
    except ValueError as exc:
        raise WikipediaError(f"Invalid JSON received from {url}") from exc


def _parse_summary(data: dict, lang: str) -> WikipediaSummary:
    thumb = data.get("thumbnail") or {}
    original = data.get("originalimage") or {}
    coords = data.get("coordinates") or {}
    desktop = (data.get("content_urls") or {}).get("desktop") or {}
    return WikipediaSummary(
        title=data.get("title") or "",
        extract=data.get("extract") or "",
        lang=lang,
        description=data.get("description"),
        page_type=data.get("type") or "standard",
        url=desktop.get("page"),
        thumbnail_url=thumb.get("source"),
        thumbnail_width=thumb.get("width"),
        thumbnail_height=thumb.get("height"),
        image_url=original.get("source"),
        latitude=coords.get("lat"),
        longitude=coords.get("lon"),
    )


@lru_cache(maxsize=256)
def _fetch_summary(title: str, lang: str) -> WikipediaSummary:
    page = urllib.parse.quote(title.replace(" ", "_"), safe="")
    url = f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{page}"
    return _parse_summary(_get_json(url), lang)


# --- Public API -------------------------------------------------------------

def search(query: str, lang: Optional[str | Iterable[str]] = None, limit: int = 5) -> List[str]:
    """Return article titles matching ``query`` (best match first)."""
    results = search_with_lang(query, lang, limit)
    return [title for _, title in results]


def search_with_lang(query: str, lang: Optional[str | Iterable[str]] = None, limit: int = 5) -> List[Tuple[str, str]]:
    """Return list of tuples (lang, title) matching ``query`` across all specified languages."""
    query = (query or "").strip()
    if not query:
        return []
    langs = _check_langs(lang)
    all_results = []
    for lang in langs:
        url = (f"https://{lang}.wikipedia.org/w/api.php?action=opensearch"
               f"&format=json&namespace=0&redirects=resolve&limit={int(limit)}"
               f"&search={urllib.parse.quote(query)}")
        try:
            data = _get_json(url)
            if isinstance(data, list) and len(data) > 1 and isinstance(data[1], list) and data[1]:
                for title in data[1]:
                    all_results.append((lang, str(title)))
        except WikipediaError as exc:
            print(f"Search warning for lang {lang}: {exc}", file=sys.stderr)
            continue
    return all_results


def get_summary(title: str, lang: Optional[str | Iterable[str]] = None,
                fallback_search: bool = False) -> WikipediaSummary:
    """Return the summary of the article called ``title``."""
    title = (title or "").strip()
    if not title:
        raise ValueError("title is empty")
    langs = _check_langs(lang)
    last_exc = None
    for lang in langs:
        try:
            return _fetch_summary(title, lang)
        except WikipediaNotFound as exc:
            last_exc = exc
            if fallback_search:
                try:
                    candidates = search(title, lang, limit=1)
                    if candidates:
                        return _fetch_summary(candidates[0], lang)
                except Exception:
                    pass
        except (WikipediaError, ValueError) as exc:
            last_exc = exc
    if last_exc:
        raise last_exc
    raise WikipediaNotFound(title)


def get_markdown(title: str, lang: Optional[str | Iterable[str]] = None,
                 fallback_search: bool = False, **options: Any) -> str:
    """Shortcut: summary of ``title`` as Markdown."""
    return get_summary(title, lang, fallback_search).to_markdown(**options)


def fetch_image(url: str, max_bytes: int = MAX_IMAGE_BYTES) -> bytes:
    """Download an image (HTTPS only) and return its bytes."""
    if not url.startswith("https://"):
        raise ValueError("Only https:// URLs are allowed")
    return _http_get(url, accept="image/*", max_bytes=max_bytes)


def fetch_thumbnail(summary: WikipediaSummary) -> Optional[bytes]:
    """Download the summary's thumbnail, or return None if it has none."""
    if not summary.thumbnail_url:
        return None
    return fetch_image(summary.thumbnail_url)


def fetch_html(url: str, lang: str, max_bytes: int = MAX_HTML_BYTES) -> str:
    """Download the HTML content of the given Wikipedia article URL."""
    if not url.startswith("https://"):
        raise ValueError("Only https:// URLs are allowed")
    raw_data = _http_get(url, accept="text/html,application/xhtml+xml", max_bytes=max_bytes)
    html_content = raw_data.decode("utf-8", errors="replace")

    base_tag = f'<base href="https://{lang}.wikipedia.org/">'
    if "<head>" in html_content:
        html_content = html_content.replace("<head>", f"<head>\n    {base_tag}", 1)
    elif "<html>" in html_content:
        html_content = html_content.replace("<html>", f"<html>\n<head>\n    {base_tag}\n</head>", 1)

    return html_content


# --- GUI (PySide6) ----------------------------------------------------------

try:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import (
        QApplication,
        QDialog,
        QHBoxLayout,
        QHeaderView,
        QLineEdit,
        QPushButton,
        QSplitter,
        QTableWidget,
        QTableWidgetItem,
        QTextBrowser,
        QVBoxLayout,
    )
    from .constants import UITexts
    HAS_PYSIDE6 = True
except ImportError:
    HAS_PYSIDE6 = False


class SearchLineEdit(QLineEdit):
    """Custom QLineEdit to handle Enter key precisely without closing the dialog during search."""

    def __init__(self, parent=None, dialog=None):
        super().__init__(parent)
        self._dialog = dialog

    def keyPressEvent(self, event) -> None:
        """Intercept Enter/Return key to trigger search or accept based on results."""
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            if self._dialog:
                self._dialog._on_return_pressed()
                event.accept()
                return
        super().keyPressEvent(event)


class WikipediaSelectorDialog(QDialog):
    """Dialog with a PySide6 GUI to search, preview, and select a Wikipedia article."""

    def __init__(self, parent=None, initial_query: str = "", languages: str = "en,es,gl,ja,ko,zh"):
        super().__init__(parent)
        self.setWindowTitle(UITexts.WIKIPEDIA_TITLE)
        self.resize(950, 600)

        self._selected_markdown: Optional[str] = None
        self._search_results: List[Tuple[str, str]] = []  # List of (lang, title)
        self._last_searched_query: str = ""

        self._init_ui(initial_query, languages)

    def _init_ui(self, initial_query: str, languages: str) -> None:
        """Initialize the user interface layout and widgets."""
        main_layout = QVBoxLayout(self)

        # 1. Toolbar section
        toolbar_layout = QHBoxLayout()

        self.query_input = SearchLineEdit(parent=self, dialog=self)
        self.query_input.setText(initial_query)
        self.query_input.setPlaceholderText(
            UITexts.WIKIPEDIA_SEARCH_PLACEHOLDER
        )
        toolbar_layout.addWidget(self.query_input, stretch=2)

        # Languages text input (comma-separated, default: en,es,gl,ja,ko,zh)
        self.lang_input = QLineEdit(languages)
        self.lang_input.setPlaceholderText(
            UITexts.WIKIPEDIA_LANGUAGES_PLACEHOLDER
        )
        self.lang_input.setMaximumWidth(180)
        toolbar_layout.addWidget(self.lang_input)

        self.search_button = QPushButton(UITexts.WIKIPEDIA_SEARCH)
        self.search_button.clicked.connect(self._on_search)
        toolbar_layout.addWidget(self.search_button)

        main_layout.addLayout(toolbar_layout)

        # 2. Splitter section (Results grid left, Markdown viewer right)
        splitter = QSplitter(Qt.Horizontal)

        # Results table
        self.table = QTableWidget()
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels([
            UITexts.WIKIPEDIA_LANGUAGE_COLUMN,
            UITexts.WIKIPEDIA_ARTICLE_COLUMN,
        ])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        splitter.addWidget(self.table)

        # Read-only Markdown viewer
        self.viewer = QTextBrowser()
        self.viewer.setOpenExternalLinks(True)
        splitter.addWidget(self.viewer)

        splitter.setSizes([350, 600])
        main_layout.addWidget(splitter, stretch=1)

        # 3. Bottom buttons (Right-aligned: Accept first, then Cancel)
        bottom_layout = QHBoxLayout()
        bottom_layout.addStretch()

        self.accept_button = QPushButton(UITexts.WIKIPEDIA_ACCEPT)
        self.accept_button.clicked.connect(self._on_accept)
        self.accept_button.setDefault(False)
        bottom_layout.addWidget(self.accept_button)

        self.cancel_button = QPushButton(UITexts.CANCEL)
        self.cancel_button.clicked.connect(self.reject)
        bottom_layout.addWidget(self.cancel_button)

        main_layout.addLayout(bottom_layout)

        # Perform initial search ONLY if initial_query was explicitly provided
        if initial_query.strip():
            self._on_search()

    def _get_active_languages(self) -> List[str]:
        """Return a list of language codes parsed from the comma-separated input."""
        text = self.lang_input.text().strip()
        if not text:
            return ["en", "es", "gl", "ja", "ko", "zh"]
        return [lang.strip().lower() for lang in text.split(",") if lang.strip()]

    def _on_return_pressed(self) -> None:
        """Handle Enter key: if results exist and query hasn't changed, accept; otherwise search."""
        query = self.query_input.text().strip()
        if not query:
            return

        # If we have results and the query hasn't changed, Enter executes Accept
        if self.table.rowCount() > 0 and query == self._last_searched_query:
            self._on_accept()
        else:
            self._on_search()

    def _on_search(self) -> None:
        """Search query across active languages and populate the results grid."""
        query = self.query_input.text().strip()
        if not query:
            return

        self._last_searched_query = query
        langs = self._get_active_languages()
        try:
            self._search_results = search_with_lang(query, langs, limit=10)
        except Exception as exc:
            print(f"GUI Search error: {exc}", file=sys.stderr)
            self._search_results = []

        self.table.setRowCount(0)
        for row_idx, (lang, title) in enumerate(self._search_results):
            self.table.insertRow(row_idx)

            item_lang = QTableWidgetItem(lang)
            item_title = QTableWidgetItem(title)

            self.table.setItem(row_idx, 0, item_lang)
            self.table.setItem(row_idx, 1, item_title)

        if self._search_results:
            self.table.selectRow(0)
            self.table.setFocus()
        else:
            self.viewer.clear()

    def _on_selection_changed(self) -> None:
        """Fetch and render the Wikipedia summary for the currently selected table row."""
        selected_rows = self.table.selectionModel().selectedRows()
        if not selected_rows:
            return

        row = selected_rows[0].row()
        if row < 0 or row >= len(self._search_results):
            return

        lang, title = self._search_results[row]
        if not title.strip():
            return

        try:
            summary = get_summary(title, lang=lang)

            local_image_src = None
            if summary.thumbnail_url:
                try:
                    img_bytes = fetch_image(summary.thumbnail_url)
                    encoded = base64.b64encode(img_bytes).decode("utf-8")
                    mime = "image/png"
                    if summary.thumbnail_url.lower().endswith((".jpg", ".jpeg")):
                        mime = "image/jpeg"
                    elif summary.thumbnail_url.lower().endswith(".webp"):
                        mime = "image/webp"
                    local_image_src = f"data:{mime};base64,{encoded}"
                except Exception:
                    pass

            md_text = summary.to_markdown(image_src=local_image_src)
            self.viewer.setMarkdown(md_text)
        except Exception as exc:
            self.viewer.setPlainText(
                UITexts.WIKIPEDIA_ERROR_LOADING.format(exc)
            )

    def _on_accept(self) -> None:
        """Store the selected markdown text and accept the dialog."""
        selected_rows = self.table.selectionModel().selectedRows()
        if not selected_rows:
            if self.table.rowCount() > 0:
                self.table.selectRow(0)
                selected_rows = self.table.selectionModel().selectedRows()
            else:
                return

        row = selected_rows[0].row()
        if 0 <= row < len(self._search_results):
            lang, title = self._search_results[row]
            if not title.strip():
                return
            try:
                summary = get_summary(title, lang=lang)
                self._selected_markdown = summary.to_markdown()
                self.accept()
                return
            except Exception:
                pass
        self.reject()

    def get_selected_markdown(self) -> Optional[str]:
        """Return the markdown text of the accepted article."""
        return self._selected_markdown


def select_wikipedia_summary(initial_query: str = "", languages: str = "en,es,gl,ja,ko,zh", parent=None) -> Optional[str]:
    """Open the Wikipedia selector GUI dialog and return the selected article's Markdown."""
    if not HAS_PYSIDE6:
        raise ImportError("PySide6 is required to run the GUI. Install it via pip install PySide6.")

    app = QApplication.instance()
    created_app = False
    if app is None:
        app = QApplication(sys.argv)
        created_app = True

    dialog = WikipediaSelectorDialog(parent, initial_query=initial_query, languages=languages)
    result = dialog.exec()

    selected_text = dialog.get_selected_markdown() if result == QDialog.Accepted else None

    if created_app:
        app.quit()

    return selected_text


# --- Command line -----------------------------------------------------------

def _main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Show the Wikipedia summary or download HTML of an article.")
    parser.add_argument("title", nargs="?", default="", help="article title or search text")
    parser.add_argument("--lang", default="en,es,gl,ja,ko,zh",
                        help="comma-separated language code(s) (default: en,es,gl,ja,ko,zh)")
    parser.add_argument("--search", action="store_true",
                        help="list matching titles instead of a summary")
    parser.add_argument("--json", action="store_true",
                        help="print the summary as JSON")
    parser.add_argument("--markdown", action="store_true",
                        help="print the summary as Markdown")
    parser.add_argument("--html", action="store_true",
                        help="download and print the HTML page from the summary URL")
    parser.add_argument("--no-image", action="store_true",
                        help="omit the image in the Markdown output")
    parser.add_argument("--gui", action="store_true",
                        help="launch the PySide6 graphical user interface")
    args = parser.parse_args(argv)

    if args.gui or not args.title:
        if not HAS_PYSIDE6:
            print("Error: PySide6 is not installed. Cannot launch GUI.", file=sys.stderr)
            return 1
        result = select_wikipedia_summary(initial_query=args.title, languages=args.lang)
        if result:
            print(result, end="")
        return 0

    try:
        if args.search:
            results_with_lang = search_with_lang(args.title, args.lang, limit=10)
            if len(results_with_lang) == 1:
                lang_code, found_title = results_with_lang[0]
                summary = get_summary(found_title, lang=lang_code)
            elif len(results_with_lang) == 0:
                print(f"Not found: {args.title}", file=sys.stderr)
                return 1
            else:
                for lang_code, found_title in results_with_lang:
                    print(f"[{lang_code}] {found_title}")
                return 0
        else:
            summary = get_summary(args.title, args.lang, fallback_search=True)
    except WikipediaNotFound:
        print(f"Not found: {args.title}", file=sys.stderr)
        return 1
    except (WikipediaError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    if args.html:
        if not summary.url:
            print("Error: No URL available for this article.", file=sys.stderr)
            return 1
        try:
            html_content = fetch_html(summary.url, summary.lang)
            print(html_content, end="")
        except (WikipediaError, ValueError) as exc:
            print(f"Error downloading HTML: {exc}", file=sys.stderr)
            return 2
    elif args.markdown:
        print(summary.to_markdown(include_image=not args.no_image), end="")
    elif args.json:
        print(json.dumps(summary.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(summary.title)
        if summary.description:
            print(f"({summary.description})")
        print()
        print(summary.extract)
        print()
        print(summary.attribution())
    return 0


if __name__ == "__main__":
    sys.exit(_main())
