"""
Main application module for the Bagheera Search GUI.
Provides the primary window and search logic integration.
"""
import calendar
import csv
import json
import os
from datetime import datetime

from PySide6.QtCore import (
    QDir, QLocale, QMimeDatabase, QProcess, QSize, QStringListModel,
    QThread, Qt, QUrl, Signal, Slot
)
from PySide6.QtGui import (
    QDesktopServices, QIcon, QImage, QKeySequence, QPixmap, QShortcut
)
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QComboBox, QCompleter, QFileDialog,
    QFileSystemModel, QFormLayout, QFrame, QGroupBox, QHBoxLayout,
    QHeaderView, QLabel, QMainWindow, QMenu, QMessageBox,
    QProgressBar, QPushButton, QSpinBox, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget, QCheckBox
)

try:
    from bagheerasearch.core.search_lib.search import BagheeraSearcher
    HAVE_SEARCH_LIB = True
except ImportError:
    HAVE_SEARCH_LIB = False

try:
    from bagheerasearch.tools.baloo_tools.baloo_tools import BalooTools
    HAVE_BALOO_TOOLS = True
except ImportError:
    HAVE_BALOO_TOOLS = False

PROG_ID = "bagheeragui"
CONFIG_FILE = f"{PROG_ID}rc"
CONFIG_LOCATION = os.environ.get('XDG_CONFIG_HOME') or os.path.expanduser('~/.config')
CONFIG_DIR = os.path.join(CONFIG_LOCATION, 'iserantes', PROG_ID)
CONFIG_PATH = os.path.join(CONFIG_DIR, CONFIG_FILE)


def load_app_config():
    """Loads the main application configuration from the JSON file."""
    if not os.path.exists(CONFIG_PATH):
        return {}
    try:
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def save_app_config(config):
    """Saves the main application configuration to the JSON file."""
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=4)
    except Exception as e:
        print(f"CRITICAL: Failed to save configuration to {CONFIG_PATH}: {e}")


# --- INTERNATIONALIZATION (i18n) ---
TRANSLATIONS: dict = {
    'en': {
        'HAVING_EXAMPLES': (
            "Syntax examples for 'Having':\n\n"
            "· width > height\n"
            "· tags=\"\" (no tags)\n"
            "· tags!=\"\" (with tags)\n"
            "· NOT (tags=gals)\n"
            "· created >= \"2024-01-01\"\n"
            "· userComment:vacations\n\n"
            "Operators: =, ==, !=, :, !:, >, >=, <, <="
        ),
        'QUERY_EXAMPLES': (
            "Search and natural language examples:\n\n"
            "· vacations beach (search for both words)\n"
            "· \"my document.pdf\" (exact search)\n"
            "· type:Audio (filter by type)\n"
            "· filename:report (filename)\n\n"
            "Natural language patterns (in CAPS):\n"
            "· MODIFIED TODAY / YESTERDAY\n"
            "· MODIFIED THIS WEEK / MONTH / YEAR\n"
            "· MODIFIED LAST 5 DAYS / 2 MONTHS\n"
            "· MODIFIED 10 DAYS AGO"
        ),
    },
    'es': {
        'Search': 'Buscar',
        'Search Placeholder': (
            "Escribe tu búsqueda aquí... (ej: 'vacaciones playa')"),
        'Basic Filters': 'Filtros Básicos',
        'Directory:': 'Directorio:',
        'Type:': 'Tipo:',
        'Order:': 'Orden:',
        'Any': 'Cualquiera',
        'Limits and Dates': 'Límites y Fechas',
        'Max Results:': 'Máx Resultados:',
        'Offset:': 'Desplazamiento:',
        'Year:': 'Año:',
        'Month:': 'Mes:',
        'Day:': 'Día:',
        'Advanced': 'Avanzado',
        'Having:': 'Manteniendo:',
        'Subquery:': 'Subconsulta:',
        'Subquery having:': 'Manteniendo subconsulta:',
        'Icon': 'Icono',
        'Syntax Help': 'Ayuda de sintaxis',
        'HAVING_EXAMPLES': (
            "Ejemplos de sintaxis para 'Having':\n\n"
            "· width > height\n"
            "· tags=\"\" (sin etiquetas)\n"
            "· tags!=\"\" (con etiquetas)\n"
            "· NOT (tags=gals)\n"
            "· created >= \"2024-01-01\"\n"
            "· userComment:vacaciones\n\n"
            "Operadores: =, ==, !=, :, !:, >, >=, <, <="
        ),
        'QUERY_EXAMPLES': (
            "Ejemplos de búsqueda y lenguaje natural:\n\n"
            "· vacaciones playa (busca ambas palabras)\n"
            "· \"mi documento.pdf\" (búsqueda exacta)\n"
            "· type:Audio (filtro por tipo)\n"
            "· filename:reporte (nombre de archivo)\n\n"
            "Patrones de lenguaje natural (en MAYÚSCULAS):\n"
            "· MODIFIED TODAY / YESTERDAY\n"
            "· MODIFIED THIS WEEK / MONTH / YEAR\n"
            "· MODIFIED LAST 5 DAYS / 2 MONTHS\n"
            "· MODIFIED 10 DAYS AGO"
        ),
        'Path': 'Ruta',
        'Ready': 'Listo',
        'Searching...': 'Buscando ...',
        'Found {0} results': 'Se encontraron {0} resultados',
        'Select Directory': 'Seleccionar Directorio',
        'Library Error': 'ERROR: No se encontró la librería bagheerasearch',
        'Clear': 'Limpiar',
        'Internal query for files in folders': (
            'Consulta interna para ficheros en carpetas'),
        'e.g.: width > height': 'p. ej.: width > height',
        'Clear History': 'Limpiar historial',
        'Are you sure you want to clear the history for this field?': (
            '¿Estás seguro de que deseas borrar el historial de este campo?'),
        'Export to CSV': 'Exportar a CSV',
        'Save CSV': 'Guardar CSV',
        'CSV Files (*.csv)': 'Archivos CSV (*.csv)',
        'Cancel': 'Cancelar',
        'Search Canceled': 'Búsqueda cancelada',
        'Image': 'Imagen',
        'Audio': 'Audio',
        'Video': 'Vídeo',
        'Document': 'Documento',
        'Folder': 'Carpeta',
        'Text': 'Texto',
        'Archive': 'Archivo',
        'Spreadsheet': 'Hoja de cálculo',
        'Presentation': 'Presentación',
        'Unknown': 'Desconocido',
        'Open': 'Abrir',
        'Open location': 'Abrir ubicación',
        'Clipboard': 'Portapapeles',
        'Copy File Path': 'Copiar ruta del archivo',
        'Copy Directory Path': 'Copiar ruta del directorio',
        'Copy File URL': 'Copiar URL del archivo',
        'Hide Icons': 'Ocultar iconos',
        'Activate Subquery': 'Activar Subconsulta',
        'Previous': 'Anterior',
        'Next': 'Siguiente',
        'Showing {0}-{1} results': 'Mostrando {0}-{1} resultados',
        'Default Application': 'Aplicación predeterminada',
        'Open with...': 'Abrir con...',
    },
    'gl': {
        'Search': 'Buscar',
        'Search Placeholder': (
            "Escribe a túa busca aquí... (ex: 'vacacións praia')"),
        'Basic Filters': 'Filtros Básicos',
        'Directory:': 'Directorio:',
        'Type:': 'Tipo:',
        'Order:': 'Orde:',
        'Any': 'Calquera',
        'Limits and Dates': 'Límites e Datas',
        'Max Results:': 'Máx. Resultados:',
        'Offset:': 'Desprazamento:',
        'Year:': 'Ano:',
        'Month:': 'Mes:',
        'Day:': 'Día:',
        'Advanced': 'Avanzado',
        'Having:': 'Mantendo:',
        'Subquery:': 'Subconsulta:',
        'Subquery having:': 'Mantendo subconsulta:',
        'Icon': 'Icona',
        'Syntax Help': 'Axuda de sintaxe',
        'HAVING_EXAMPLES': (
            "Exemplos de sintaxe para 'Having':\n\n"
            "· width > height\n"
            "· tags=\"\" (sen etiquetas)\n"
            "· tags!=\"\" (con etiquetas)\n"
            "· NOT (tags=gals)\n"
            "· created >= \"2024-01-01\"\n"
            "· userComment:vacacións\n\n"
            "Operadores: =, ==, !=, :, !:, >, >=, <, <="
        ),
        'QUERY_EXAMPLES': (
            "Exemplos de busca e linguaxe natural:\n\n"
            "· vacacións praia (busca ambas as palabras)\n"
            "· \"o meu documento.pdf\" (busca exacta)\n"
            "· type:Audio (filtro por tipo)\n"
            "· filename:reporte (nome de ficheiro)\n\n"
            "Patróns de linguaxe natural (en MAYÚSCULAS):\n"
            "· MODIFIED TODAY / YESTERDAY\n"
            "· MODIFIED THIS WEEK / MONTH / YEAR\n"
            "· MODIFIED LAST 5 DAYS / 2 MONTHS\n"
            "· MODIFIED 10 DAYS AGO"
        ),
        'Path': 'Ruta',
        'Ready': 'Listo',
        'Searching...': 'Buscando ...',
        'Found {0} results': 'Atopáronse {0} resultados',
        'Select Directory': 'Seleccionar Directorio',
        'Library Error': 'ERRO: Non se atopou a libraría bagheerasearch',
        'Clear': 'Limpar',
        'Internal query for files in folders': (
            'Consulta interna para ficheiros en carpetas'),
        'e.g.: width > height': 'p. ex.: width > height',
        'Clear History': 'Limpar historial',
        'Are you sure you want to clear the history for this field?': (
            '¿Estás seguro de que desexas borrar o historial deste campo?'),
        'Export to CSV': 'Exportar a CSV',
        'Save CSV': 'Gardar CSV',
        'CSV Files (*.csv)': 'Ficheiros CSV (*.csv)',
        'Cancel': 'Cancelar',
        'Search Canceled': 'Busca cancelada',
        'Image': 'Imaxe',
        'Audio': 'Audio',
        'Video': 'Vídeo',
        'Document': 'Documento',
        'Folder': 'Cartafol',
        'Text': 'Texto',
        'Archive': 'Arquivo',
        'Spreadsheet': 'Folla de cálculo',
        'Presentation': 'Presentación',
        'Unknown': 'Descoñecido',
        'Open': 'Abrir',
        'Open location': 'Abrir localización',
        'Clipboard': 'Portapapeis',
        'Copy File Path': 'Copiar ruta do ficheiro',
        'Copy Directory Path': 'Copiar ruta do directorio',
        'Copy File URL': 'Copiar URL do ficheiro',
        'Hide Icons': 'Ocultar iconas',
        'Activate Subquery': 'Activar Subconsulta',
        'Previous': 'Anterior',
        'Next': 'Seguinte',
        'Showing {0}-{1} results': 'Amosando {0}-{1} resultados',
        'Default Application': 'Aplicación predeterminada',
        'Open with...': 'Abrir con...',
    }
}


def _(text: str) -> str:
    """
    Translates the given text based on the system locale.

    Args:
        text: The source string in English.

    Returns:
        The translated string if available, otherwise the source text.
    """
    lang_code = QLocale.system().name()[:2]
    return TRANSLATIONS.get(lang_code, {}).get(text, text)


class SearchWorker(QThread):
    """
    Worker thread to handle the search process without blocking the GUI.
    """
    results_found = Signal(list)
    finished = Signal()

    def __init__(self, query, main_opts, other_opts, thumb_size, hide_icons):
        super().__init__()
        self.query = query
        self.main_opts = main_opts
        self.other_opts = other_opts
        self.thumb_size = thumb_size
        self.hide_icons = hide_icons

    def run(self):
        """
        Executes the search using the BagheeraSearcher library and
        emits the results.
        """
        if not HAVE_SEARCH_LIB:
            return
        try:
            searcher = BagheeraSearcher()
            results = list(
                searcher.search(self.query, self.main_opts, self.other_opts)
            )

            mime_db = QMimeDatabase()
            bt = BalooTools() if HAVE_BALOO_TOOLS else None

            for item in results:
                # 1. Enriquecemos los resultados con el tipo si falta
                if bt:
                    item_type = item.get("type")
                    if "id" in item and (not item_type or item_type == "Unknown"):
                        try:
                            doc_id = int(item["id"], 16)
                            info = bt.get_mime_type(doc_id)
                            item["type"] = info.get("type", "Unknown")
                        except (ValueError, TypeError):
                            pass

                # 2. Generación de miniatura en segundo plano (Background loading)
                if not self.hide_icons:
                    path = item.get("path")
                    if path and os.path.exists(path):
                        m_type = mime_db.mimeTypeForFile(path)
                        if m_type.name().startswith("image/"):
                            img = QImage(path)
                            if not img.isNull():
                                # Escalado pesado fuera del hilo principal
                                item["thumbnail"] = img.scaled(
                                    self.thumb_size,
                                    Qt.KeepAspectRatio,
                                    Qt.SmoothTransformation
                                )

            self.results_found.emit(results)
        except Exception as e:
            print(f"Search error: {e}")
        finally:
            self.finished.emit()


class BagheeraSearchWindow(QMainWindow):
    """
    Main window class for the Bagheera Search application.
    Manages widgets, layouts, and search orchestration.´
    """
    def __init__(self):
        super().__init__()
        self.worker = None
        self.config = load_app_config()
        self.setWindowTitle(_("Bagheera Search"))
        self.resize(1000, 700)
        self._setup_ui()
        self._setup_property_completers()
        self._restore_state()

    def _setup_ui(self):
        """Initializes and arranges the UI components."""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        help_icon = QIcon.fromTheme("help-about")

        # --- TOP SEARCH BAR ---
        search_bar_layout = QHBoxLayout()
        self.query_input = QComboBox()
        self.query_input.setEditable(True)
        self.query_input.setInsertPolicy(QComboBox.NoInsert)
        self.query_input.addItems(self.config.get("query_history", []))
        self.query_input.lineEdit().setPlaceholderText(_("Search Placeholder"))
        self.query_input.lineEdit().returnPressed.connect(
            self.perform_search
        )
        # self.query_input.lineEdit().textChanged.connect(
        #     self.perform_search
        # )

        self.btn_clear_query_history = QPushButton()
        self.btn_clear_query_history.setIcon(QIcon.fromTheme("edit-clear"))
        self.btn_clear_query_history.setToolTip(_("Clear History"))
        self.btn_clear_query_history.setFixedWidth(30)
        self.btn_clear_query_history.clicked.connect(
            lambda: self._clear_combo_history(
                self.query_input, "query_history")
        )

        self.btn_help_query = QPushButton()
        if help_icon.isNull():
            self.btn_help_query.setText("?")
        else:
            self.btn_help_query.setIcon(help_icon)
        self.btn_help_query.setFixedWidth(30)
        self.btn_help_query.setToolTip(_("Syntax Help"))
        self.btn_help_query.clicked.connect(self._show_query_help)

        self.btn_search = QPushButton(_("Search"))
        self.btn_search.setIcon(QIcon.fromTheme("system-search"))
        self.btn_search.clicked.connect(self.perform_search)

        self.btn_cancel = QPushButton(_("Cancel"))
        self.btn_cancel.setIcon(QIcon.fromTheme("process-stop"))
        self.btn_cancel.clicked.connect(self.cancel_search)
        self.btn_cancel.setVisible(False)

        self.btn_clear = QPushButton(_("Clear"))
        self.btn_clear.setIcon(QIcon.fromTheme("edit-clear"))
        self.btn_clear.clicked.connect(self._clear_filters)

        self.btn_export = QPushButton()
        self.btn_export.setIcon(QIcon.fromTheme("document-save-as"))
        self.btn_export.setToolTip(_("Export to CSV"))
        self.btn_export.clicked.connect(self._export_to_csv)
        self.btn_export.setEnabled(False)

        search_bar_layout.addWidget(self.query_input, 1)
        search_bar_layout.addWidget(self.btn_clear_query_history)
        search_bar_layout.addWidget(self.btn_help_query)
        search_bar_layout.addWidget(self.btn_search)
        search_bar_layout.addWidget(self.btn_cancel)
        search_bar_layout.addWidget(self.btn_clear)
        search_bar_layout.addWidget(self.btn_export)
        main_layout.addLayout(search_bar_layout)

        # --- FILTERS PANEL ---
        filters_container = QHBoxLayout()

        # Group 1: Location and Type
        basic_group = QGroupBox(_("Basic Filters"))
        basic_form = QFormLayout(basic_group)

        self.dir_input = QComboBox()
        self.dir_input.setEditable(True)
        self.dir_input.setInsertPolicy(QComboBox.NoInsert)
        self.dir_input.addItems(self.config.get("directory_history", []))

        # Local path autocompletion
        dir_completer = QCompleter(self)
        dir_fs_model = QFileSystemModel(dir_completer)
        dir_fs_model.setRootPath(QDir.rootPath())
        dir_fs_model.setFilter(QDir.Dirs | QDir.Drives | QDir.NoDotAndDotDot)
        dir_completer.setModel(dir_fs_model)
        self.dir_input.setCompleter(dir_completer)

        self.btn_clear_dir_history = QPushButton()
        self.btn_clear_dir_history.setIcon(QIcon.fromTheme("edit-clear"))
        self.btn_clear_dir_history.setToolTip(_("Clear History"))
        self.btn_clear_dir_history.setFixedWidth(30)
        self.btn_clear_dir_history.clicked.connect(
            lambda: self._clear_combo_history(self.dir_input, "directory_history")
        )

        self.btn_browse = QPushButton("...")
        self.btn_browse.setFixedWidth(30)
        self.btn_browse.clicked.connect(self._browse_directory)
        dir_layout = QHBoxLayout()
        dir_layout.addWidget(self.dir_input)
        dir_layout.addWidget(self.btn_clear_dir_history)
        dir_layout.addWidget(self.btn_browse)

        self.type_combo = QComboBox()
        types = [
            (_("Any"), "any"), (_("Image"), "image"), (_("Folder"), "folder"),
            (_("Audio"), "audio"), (_("Video"), "video"), (_("Document"), "document"), (_("Text"), "text")
        ]
        for text, data in types:
            self.type_combo.addItem(text, data)

        self.sort_combo = QComboBox()
        sort_options = [
            (_("Auto"), "auto"), (_("None"), "none"), (_("Modified"), "modified"),
            (_("Filename"), "filename"), (_("Size"), "size")
        ]
        for text, data in sort_options:
            self.sort_combo.addItem(text, data)

        basic_form.addRow(_("Directory:"), dir_layout)
        basic_form.addRow(_("Type:"), self.type_combo)
        basic_form.addRow(_("Order:"), self.sort_combo)
        filters_container.addWidget(basic_group)

        self.hide_icons_check = QCheckBox(_("Hide Icons"))
        self.hide_icons_check.setChecked(False)
        self.hide_icons_check.toggled.connect(self._toggle_icon_column_visibility)
        basic_form.addRow(self.hide_icons_check)

        # Group 2: Limits and Dates
        limit_group = QGroupBox(_("Limits and Dates"))
        limit_form = QFormLayout(limit_group)

        self.limit_spin = QSpinBox()
        self.limit_spin.setRange(0, 100000)
        self.limit_spin.setValue(100)
        self.limit_spin.valueChanged.connect(self._update_pagination_state)

        self.offset_spin = QSpinBox()
        self.offset_spin.setRange(0, 1000000)
        self.offset_spin.setValue(0)

        self.btn_prev_page = QPushButton(_("Previous"))
        self.btn_prev_page.setIcon(QIcon.fromTheme("go-previous"))
        self.btn_prev_page.clicked.connect(self._go_to_previous_page)
        self.btn_prev_page.setEnabled(False)

        self.btn_next_page = QPushButton(_("Next"))
        self.btn_next_page.setIcon(QIcon.fromTheme("go-next"))
        self.btn_next_page.clicked.connect(self._go_to_next_page)
        self.btn_next_page.setEnabled(False)

        offset_layout = QHBoxLayout()
        offset_layout.addWidget(self.offset_spin)
        offset_layout.addWidget(self.btn_prev_page)
        offset_layout.addWidget(self.btn_next_page)

        self.year_combo = QComboBox()
        self.year_combo.setEditable(True)
        current_year = datetime.now().year
        years = [_("Any")] + [str(y) for y in range(current_year, 1999, -1)]
        self.year_combo.addItems(years)
        self.year_combo.currentTextChanged.connect(self._update_date_visibility)
        # Habilitar autocompletado para el año
        self.year_combo.setCompleter(QCompleter(years, self.year_combo))

        self.month_combo = QComboBox()
        self.month_combo.addItems([_("Any")] + [str(i) for i in range(1, 13)])
        self.month_combo.setEnabled(False)
        self.month_combo.currentIndexChanged.connect(self._update_date_visibility)

        self.day_combo = QComboBox()
        self.day_combo.addItems([_("Any")] + [str(i) for i in range(1, 32)])
        self.day_combo.setEnabled(False)

        limit_form.addRow(_("Max Results:"), self.limit_spin)
        limit_form.addRow(_("Offset:"), offset_layout)
        limit_form.addRow(_("Year:"), self.year_combo)
        limit_form.addRow(_("Month:"), self.month_combo)
        limit_form.addRow(_("Day:"), self.day_combo)
        filters_container.addWidget(limit_group)

        # Group 3: Advanced (HAVING / SUBQUERY)
        adv_group = QGroupBox(_("Advanced"))
        adv_form = QFormLayout(adv_group)

        h_layout = QHBoxLayout()
        self.having_input = QComboBox()
        self.having_input.setEditable(True)
        self.having_input.setInsertPolicy(QComboBox.NoInsert)
        self.having_input.addItems(self.config.get("having_history", []))
        self.having_input.lineEdit().setPlaceholderText(_("e.g.: width > height"))
        btn_clear_h = QPushButton()
        btn_clear_h.setIcon(QIcon.fromTheme("edit-clear"))
        btn_clear_h.setFixedWidth(30)
        btn_clear_h.setToolTip(_("Clear History"))
        btn_clear_h.clicked.connect(
            lambda: self._clear_combo_history(
                self.having_input, "having_history")
        )

        btn_help_h = QPushButton()
        if help_icon.isNull():
            btn_help_h.setText("?")
        else:
            btn_help_h.setIcon(help_icon)
        btn_help_h.setFixedWidth(30)
        btn_help_h.setToolTip(_("Syntax Help"))
        btn_help_h.clicked.connect(self._show_syntax_help)

        h_layout.addWidget(self.having_input, 1)
        h_layout.addWidget(btn_help_h)
        h_layout.addWidget(btn_clear_h)

        # Subquery Input
        sq_layout = QHBoxLayout()
        self.subquery_input = QComboBox()
        self.subquery_input.setEditable(True)
        self.subquery_input.setInsertPolicy(QComboBox.NoInsert)
        self.subquery_input.addItems(self.config.get("subquery_history", []))
        self.subquery_input.lineEdit().setPlaceholderText(_("Internal query for files in folders"))
        btn_clear_sq = QPushButton()
        btn_clear_sq.setIcon(QIcon.fromTheme("edit-clear"))
        btn_clear_sq.setFixedWidth(30)
        btn_clear_sq.setToolTip(_("Clear History"))
        btn_clear_sq.clicked.connect(
            lambda: self._clear_combo_history(
                self.subquery_input, "subquery_history")
        )
        sq_layout.addWidget(self.subquery_input, 1)
        sq_layout.addWidget(btn_clear_sq)

        # Subquery Having Input
        sqh_layout = QHBoxLayout()
        self.subquery_having_input = QComboBox()
        self.subquery_having_input.setEditable(True)
        self.subquery_having_input.setInsertPolicy(QComboBox.NoInsert)
        self.subquery_having_input.addItems(self.config.get("subquery_having_history", []))
        self.subquery_having_input.lineEdit().setPlaceholderText(_("e.g.: width > height"))
        btn_clear_sqh = QPushButton()
        btn_clear_sqh.setIcon(QIcon.fromTheme("edit-clear"))
        btn_clear_sqh.setFixedWidth(30)
        btn_clear_sqh.setToolTip(_("Clear History"))
        btn_clear_sqh.clicked.connect(
            lambda: self._clear_combo_history(
                self.subquery_having_input, "subquery_having_history")
        )

        btn_help_sqh = QPushButton()
        if help_icon.isNull():
            btn_help_sqh.setText("?")
        else:
            btn_help_sqh.setIcon(help_icon)
        btn_help_sqh.setFixedWidth(30)
        btn_help_sqh.setToolTip(_("Syntax Help"))
        btn_help_sqh.clicked.connect(self._show_syntax_help)

        sqh_layout.addWidget(self.subquery_having_input, 1)
        sqh_layout.addWidget(btn_help_sqh)
        sqh_layout.addWidget(btn_clear_sqh)

        self.subquery_input.setEnabled(False)
        self.subquery_having_input.setEnabled(False)

        adv_form.addRow(_("Having:"), h_layout)

        self.subquery_active_check = QCheckBox(_("Activate Subquery"))

        # Visual Separator
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setFrameShadow(QFrame.Sunken)
        adv_form.addRow(separator)

        self.subquery_active_check.setChecked(False)
        self.subquery_active_check.toggled.connect(self._toggle_subquery_fields)
        adv_form.addRow(self.subquery_active_check)

        adv_form.addRow(_("Subquery:"), sq_layout)
        adv_form.addRow(_("Subquery having:"), sqh_layout)
        filters_container.addWidget(adv_group)

        main_layout.addLayout(filters_container)

        # --- RESULTS TABLE ---
        self.results_table = QTableWidget(0, 3)
        self.results_table.setHorizontalHeaderLabels(
            [_("Icon"), _("Path"), _("Type")]
        )
        self.results_table.setIconSize(QSize(24, 24))
        self.results_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeToContents
        )
        self.results_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.Stretch
        )
        self.results_table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeToContents
        )
        self.results_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.results_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.results_table.setSortingEnabled(True)
        self.results_table.setContextMenuPolicy(
            Qt.CustomContextMenu
        )
        self.results_table.customContextMenuRequested.connect(
            self._show_context_menu
        )
        self.results_table.doubleClicked.connect(self._open_result)
        main_layout.addWidget(self.results_table)

        # --- PROGRESS BAR ---
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setVisible(False)
        main_layout.addWidget(self.progress_bar)

        # --- STATUS ---
        self.status_label = QLabel(_("Ready"))
        self.status_label.setFrameStyle(QFrame.StyledPanel | QFrame.Sunken)
        main_layout.addWidget(self.status_label)

        if not HAVE_SEARCH_LIB:
            self.status_label.setText(_("Library Error"))
            self.btn_search.setEnabled(False)

        # --- SHORTCUTS ---
        self.search_shortcut = QShortcut(QKeySequence("Ctrl+F"), self)
        self.search_shortcut.activated.connect(self.query_input.setFocus)

        self.first_page_shortcut = QShortcut(QKeySequence("Ctrl+Home"), self)
        self.first_page_shortcut.activated.connect(self._go_to_first_page)
        self.query_input.lineEdit().textChanged.connect(self._reset_offset_on_query_change)

    def _setup_property_completers(self):
        """
        Configura el autocompletado avanzado para los campos de búsqueda.
        Permite completar propiedades individuales incluso en mitad de una frase.
        """
        properties = [
            "type:Audio", "type:Video", "type:Image", "type:Document",
            "type:Folder", "type:Archive", "type:Spreadsheet", "type:Presentation",
            "type:Text", "tags", "rating", "modified", "created", "filename",
            "mimetype", "userComment", "width", "height", "duration", "author",
            "title", "subject", "keywords", "pageCount", "album", "artist",
            "genre", "bitRate", "channels", "comment", "composer", "lyricist",
            "releaseYear", "sampleRate", "trackNumber", "copyright", "creationDate",
            "generator", "language", "lineCount", "publisher", "wordCount",
            "aspectRatio", "frameRate", "imageDateTime", "imageMake", "imageModel",
            "imageOrientation", "photoApertureValue", "photoDateTimeOriginal",
            "photoExposureBiasValue", "photoExposureTime", "photoFlash", "photoFNumber",
            "photoFocalLength", "photoISOSpeedRatings", "photoMeteringMode",
            "photoSaturation", "photoSharpness", "photoWhiteBalance"
        ]

        for combo in [
            self.query_input, self.having_input,
            self.subquery_input, self.subquery_having_input
        ]:
            history = [combo.itemText(i) for i in range(combo.count())]
            full_list = sorted(list(set(properties + history)))

            line_edit = combo.lineEdit()
            if not line_edit:
                continue

            # Reutilizar o crear completador asociado al line_edit
            completer = line_edit.property("custom_completer")
            if not completer:
                completer = QCompleter(full_list, self)
                completer.setCaseSensitivity(Qt.CaseInsensitive)
                completer.setFilterMode(Qt.MatchContains)
                completer.setWidget(line_edit)
                line_edit.setProperty("custom_completer", completer)

                # Handle manual logic for individual words
                line_edit.textChanged.connect(
                    lambda t, le=line_edit, c=completer:
                    self._update_completer_prefix(t, le, c)
                )
                completer.activated.connect(
                    lambda t, le=line_edit: self._insert_completion(t, le)
                )
            else:
                # If exists, update data model only
                completer.setModel(QStringListModel(full_list, completer))

    def _update_completer_prefix(self, text, line_edit, completer):
        """
        Actualiza el prefijo del completador para que coincida con la
        última palabra que se está escribiendo antes del cursor.
        """
        if not line_edit.hasFocus():
            return

        cursor_pos = line_edit.cursorPosition()
        before_cursor = text[:cursor_pos]

        # Extract last word delimited by spaces
        parts = before_cursor.split(" ")
        current_word = parts[-1] if parts else ""

        if len(current_word) >= 1:
            completer.setCompletionPrefix(current_word)
            if completer.completionCount() > 0:
                # Position popup at cursor location
                rect = line_edit.cursorRect()
                rect.setWidth(line_edit.width())
                completer.complete(rect)
            else:
                completer.popup().hide()
        else:
            completer.popup().hide()

    def _insert_completion(self, completion, line_edit):
        """
        Reemplaza únicamente la palabra actual con la sugerencia seleccionada
        manteniendo el resto del texto intacto.
        """
        full_text = line_edit.text()
        cursor_pos = line_edit.cursorPosition()
        before_cursor = full_text[:cursor_pos]
        after_cursor = full_text[cursor_pos:]

        # Find start of the word being completed
        last_space = before_cursor.rfind(" ")

        if last_space == -1:
            # First word in text
            new_text = completion + after_cursor
            new_cursor_pos = len(completion)
        else:
            # Previous text exists, maintain up to last space
            new_text = before_cursor[:last_space + 1] + completion + after_cursor
            new_cursor_pos = last_space + 1 + len(completion)

        line_edit.setText(new_text)
        line_edit.setCursorPosition(new_cursor_pos)

    def _update_combo_items(self, combo, key, placeholder=None):
        """Helper to populate comboboxes with history and set up basic props."""
        combo.setEditable(True)
        combo.setInsertPolicy(QComboBox.NoInsert)
        combo.addItems(self.config.get(key, []))
        if placeholder:
            combo.lineEdit().setPlaceholderText(placeholder)

    def closeEvent(self, event):
        """Save current field values to configuration before closing."""
        self._save_current_state()
        super().closeEvent(event)

    def _browse_directory(self):
        """Opens a file dialog to select the search directory."""
        path = QFileDialog.getExistingDirectory(self, _("Select Directory"))
        if path:
            self.dir_input.setEditText(path)

    def _open_result(self):
        """Opens the selected search result using the default system application."""
        row = self.results_table.currentRow()
        if row >= 0:
            path = self.results_table.item(row, 1).text()
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def _show_query_help(self):
        """Displays a message box with search query syntax examples."""
        QMessageBox.information(
            self, _("Syntax Help"), _("QUERY_EXAMPLES")
        )

    def _show_syntax_help(self):
        """Displays a message box with HAVING syntax examples."""
        QMessageBox.information(
            self,
            _("Syntax Help"),
            _("HAVING_EXAMPLES")
        )

    def _populate_open_menu(self, menu, path):
        """Populates the Open menu with associated applications."""
        # Acción por defecto
        file_url = QUrl.fromLocalFile(path)

        # Opción para abrir con la aplicación predeterminada del sistema
        default_app_action = menu.addAction(_("Default Application"))
        default_app_action.triggered.connect(lambda: QDesktopServices.openUrl(file_url))

        # Submenú para "Abrir con..."
        open_with_menu = menu.addMenu(_("Open with..."))
        mime_db = QMimeDatabase()
        mime_type = mime_db.mimeTypeForFile(path)

        # Manual application selection
        choose_app_action = open_with_menu.addAction(_("Open with..."))
        choose_app_action.triggered.connect(
            lambda: self._open_with_dialog(path, mime_type)
        )

    def _open_with_dialog(self, path, mime_type):
        """Opens a file dialog to let the user choose an application."""
        app_path, unused_filter = QFileDialog.getOpenFileName(
            self, _("Open with..."), "/usr/bin", "Applications (*)"
        )
        if app_path:
            QProcess.startDetached(app_path, [path])

    def _show_context_menu(self, pos):
        """Displays a context menu for the selected result."""
        item = self.results_table.itemAt(pos)
        if not item:
            return

        row = item.row()
        path = self.results_table.item(row, 1).text()
        if not os.path.exists(path):
            return

        menu = QMenu(self)

        # Open Submenu
        open_menu = menu.addMenu(_("Open"))
        self._populate_open_menu(open_menu, path)

        # 2. Open location
        open_loc_action = menu.addAction(_("Open location"))
        open_loc_action.triggered.connect(lambda: self._open_location(path))

        menu.addSeparator()

        # Clipboard Submenu
        clipboard_menu = menu.addMenu(_("Clipboard"))
        cb = QApplication.clipboard()

        copy_path_action = clipboard_menu.addAction(_("Copy File Path"))
        copy_path_action.triggered.connect(lambda: cb.setText(path))

        copy_dir_action = clipboard_menu.addAction(_("Copy Directory Path"))
        copy_dir_action.triggered.connect(
            lambda: cb.setText(os.path.dirname(path)))

        copy_url_action = clipboard_menu.addAction(_("Copy File URL"))
        copy_url_action.triggered.connect(
            lambda: cb.setText(QUrl.fromLocalFile(path).toString()))

        menu.exec(self.results_table.viewport().mapToGlobal(pos))

    def _open_location(self, path):
        """Opens the directory containing the file."""
        folder = os.path.dirname(path)
        if os.path.isdir(folder):
            QDesktopServices.openUrl(QUrl.fromLocalFile(folder))

    def perform_search(self):
        """
        Validates inputs, constructs search options, and starts the SearchWorker.
        """
        if self.worker and self.worker.isRunning():
            return

        query_text = self.query_input.currentText()

        # main_opts: only include present values
        main_opts = {}
        dir_text = self.dir_input.currentText()
        if dir_text:
            main_opts["directory"] = dir_text

        if self.type_combo.currentData() != "any":
            main_opts["type"] = self.type_combo.currentData()

        if self.limit_spin.value() > 0:
            main_opts["limit"] = self.limit_spin.value()
        else:
            main_opts["limit"] = 9999999

        if self.offset_spin.value() > 0:
            main_opts["offset"] = self.offset_spin.value()
        else:
            main_opts["offset"] = 0

        if self.sort_combo.currentData() != "auto":
            main_opts["sort"] = self.sort_combo.currentData()

        year_str = self.year_combo.currentText()
        if year_str != _("Any") and year_str.strip():
            month_txt = self.month_combo.currentText()
            day_txt = self.day_combo.currentText()
            try:
                main_opts["year"] = int(year_str)
                if self.month_combo.isEnabled() and month_txt != _("Any"):
                    main_opts["month"] = int(month_txt)
                    if self.day_combo.isEnabled() and day_txt != _("Any"):
                        main_opts["day"] = int(day_txt)
            except ValueError:
                pass

        # other_options: mandatory parameters (None if not provided)
        subquery_text = None
        subquery_having_text = None
        if self.subquery_active_check.isChecked():
            subquery_text = self.subquery_input.currentText()
            # If subquery is active but text is empty, send empty string
            if not subquery_text.strip():
                subquery_text = ""
            subquery_having_text = self.subquery_having_input.currentText()

        other_opts = {
            "having": self.having_input.currentText()
            if self.having_input.currentText() else None,
            "subquery": subquery_text,
            "subquery_having": subquery_having_text if subquery_having_text else None,
            "limit": main_opts.get("limit"),
            "offset": main_opts.get("offset", 0),
        }

        if other_opts.get("subquery") is not None:
            other_opts["type"] = main_opts.get("type")
            main_opts["type"] = None

        # Update history
        self._update_combo_history(self.query_input, "query_history", query_text)
        self._update_combo_history(self.dir_input, "directory_history", dir_text)
        self._update_combo_history(self.having_input, "having_history", other_opts.get("having"))
        self._update_combo_history(
            self.subquery_input, "subquery_history",
            other_opts.get("subquery"))
        self._update_combo_history(
            self.subquery_having_input, "subquery_having_history",
            other_opts.get("subquery_having"))
        self._save_current_state()

        self.status_label.setText(_("Searching..."))
        self.results_table.setRowCount(0)
        self.progress_bar.setRange(0, 0)  # Indeterminate mode
        self.progress_bar.setVisible(True)
        self.btn_export.setEnabled(False)
        self.btn_search.setVisible(False)
        self.btn_prev_page.setEnabled(False)
        self.btn_next_page.setEnabled(False)
        self.btn_cancel.setVisible(True)

        self.worker = SearchWorker(
            query_text, main_opts, other_opts, self.results_table.iconSize(),
            self.hide_icons_check.isChecked()
        )
        self.worker.results_found.connect(self._display_results)
        self.worker.finished.connect(self._on_search_finished)
        self.worker.start()

    def _update_date_visibility(self):
        """Updates the enabled state of month and day combos based on selection."""
        year_str = self.year_combo.currentText()
        has_year = year_str != _("Any") and year_str.strip() != ""
        self.month_combo.setEnabled(has_year)

        if not has_year:
            self.month_combo.setCurrentIndex(0)

        month_str = self.month_combo.currentText()
        has_month = self.month_combo.isEnabled() and month_str != _("Any")
        self.day_combo.setEnabled(has_month)

        if not has_month:
            self.day_combo.setCurrentIndex(0)

        # Calculate max days for month/year
        max_days = 31
        if has_year and has_month:
            try:
                # monthrange returns (weekday_start, days_in_month)
                max_days = calendar.monthrange(int(year_str), int(month_str))[1]
            except ValueError:
                pass

        # Update day combo items if limit changed
        if self.day_combo.count() - 1 != max_days:
            current_day_idx = self.day_combo.currentIndex()
            self.day_combo.blockSignals(True)
            self.day_combo.clear()
            self.day_combo.addItems(
                [_("Any")] + [str(i) for i in range(1, max_days + 1)]
            )
            self.day_combo.setCurrentIndex(min(current_day_idx, self.day_combo.count() - 1))
            self.day_combo.blockSignals(False)

    def _toggle_icon_column_visibility(self, checked):
        """Hides or shows the icon column in the results table."""
        self.results_table.setColumnHidden(0, checked)

    def _toggle_subquery_fields(self, checked):
        """Enables/disables subquery and subquery_having fields based on checkbox."""
        self.subquery_input.setEnabled(checked)
        self.subquery_having_input.setEnabled(checked)
        if not checked:
            self.subquery_input.setEditText("")
            self.subquery_having_input.setEditText("")

    def _reset_offset_on_query_change(self):
        """
        Resets the offset spinbox to 0 when the main query text changes.
        This prevents unexpected pagination when the search criteria changes.
        """
        if self.offset_spin.value() != 0:
            self.offset_spin.setValue(0)

    def _go_to_first_page(self):
        """Resets the offset to 0 and performs a new search."""
        if self.offset_spin.value() != 0:
            self.offset_spin.setValue(0)
            self.perform_search()

    def _update_pagination_state(self):
        """Updates the enabled state of pagination buttons based on current results and limit."""
        limit = self.limit_spin.value()
        # Requirements: Enable only when there is a limit value > 0
        has_limit = limit > 0
        current_offset = self.offset_spin.value()
        results_count = self.results_table.rowCount()
        self.btn_prev_page.setEnabled(has_limit and current_offset > 0)
        self.btn_next_page.setEnabled(has_limit and results_count > 0 and results_count == limit)

    def _go_to_previous_page(self):
        """Decrements the offset and performs a new search."""
        current_offset = self.offset_spin.value()
        limit = self.limit_spin.value()
        new_offset = max(0, current_offset - limit)
        if new_offset != current_offset:
            self.offset_spin.setValue(new_offset)
            self.perform_search()

    def _go_to_next_page(self):
        """Increments the offset and performs a new search."""
        current_offset = self.offset_spin.value()
        limit = self.limit_spin.value()
        # Only go to next page if the last search returned a full page of results
        # This is an heuristic as we don't have the total count from the worker
        if self.results_table.rowCount() == limit:
            new_offset = current_offset + limit
            self.offset_spin.setValue(new_offset)
            self.perform_search()

    def _save_current_state(self):
        """Collects the current values of all fields and saves them to the config file."""
        self.config["last_state"] = {
            "query": self.query_input.currentText(),
            "directory": self.dir_input.currentText(),
            "type": self.type_combo.currentData(),
            "sort": self.sort_combo.currentData(),
            "limit": self.limit_spin.value(),
            "offset": self.offset_spin.value(),
            "year": self.year_combo.currentText(),
            "month_index": self.month_combo.currentIndex(),
            "day_index": self.day_combo.currentIndex(),
            "having": self.having_input.currentText(),
            "subquery": self.subquery_input.currentText(),
            "subquery_having": self.subquery_having_input.currentText(),
            "subquery_active": self.subquery_active_check.isChecked(),
            "hide_icons": self.hide_icons_check.isChecked(),
        }
        save_app_config(self.config)

    def _restore_state(self):
        """Restores all field values from the saved configuration."""
        state = self.config.get("last_state", {})
        if not state:
            return

        self.query_input.setEditText(state.get("query", ""))
        self.dir_input.setEditText(state.get("directory", ""))
        self.having_input.setEditText(state.get("having", ""))
        self.subquery_input.setEditText(state.get("subquery", ""))
        self.subquery_having_input.setEditText(state.get("subquery_having", ""))
        self.subquery_active_check.setChecked(state.get("subquery_active", False))
        self.hide_icons_check.setChecked(state.get("hide_icons", False))
        self.limit_spin.setValue(state.get("limit", 100))
        # self.offset_spin.setValue(state.get("offset", 0))

        # Restoring dropdowns by data/index
        idx = self.type_combo.findData(state.get("type", "any"))
        if idx >= 0:
            self.type_combo.setCurrentIndex(idx)
        idx = self.sort_combo.findData(state.get("sort", "auto"))
        if idx >= 0:
            self.sort_combo.setCurrentIndex(idx)
        self._toggle_subquery_fields(self.subquery_active_check.isChecked())
        self._toggle_icon_column_visibility(self.hide_icons_check.isChecked())

        # Cascading date restore
        self.year_combo.setEditText(state.get("year", _("Any")))
        self._update_date_visibility()  # Enables month if year is valid
        self.month_combo.setCurrentIndex(state.get("month_index", 0))
        self._update_date_visibility()  # Enables day and sets range if month is valid
        self.day_combo.setCurrentIndex(state.get("day_index", 0))

    def _update_combo_history(self, combo, key, value):
        """Updates the history for a given combo and saves it to config."""
        if not value or not value.strip():
            return
        history = self.config.get(key, [])
        if value in history:
            history.remove(value)
        history.insert(0, value)
        history = history[:25]
        self.config[key] = history

        combo.blockSignals(True)
        if combo.lineEdit():
            combo.lineEdit().blockSignals(True)
        combo.clear()
        combo.addItems(history)
        combo.setEditText(value)
        if combo.lineEdit():
            combo.lineEdit().blockSignals(False)
        combo.blockSignals(False)

        # Refrescamos los completadores para incluir las nuevas entradas del historial
        self._setup_property_completers()

    def _clear_combo_history(self, combo, key):
        """Clears the history for a given combo and updates config."""
        confirm = QMessageBox.question(
            self,
            _("Clear History"),
            _("Are you sure you want to clear the history for this field?"),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if confirm != QMessageBox.Yes:
            return

        if key in self.config:
            self.config[key] = []
            save_app_config(self.config)

        combo.blockSignals(True)
        combo.clear()
        combo.setEditText("")
        combo.blockSignals(False)

    @Slot(list)
    def _display_results(self, results):
        """
        Populates the results table with the data returned by the worker.

        Args:
            results: A list of result dictionaries from the search engine.
        """
        self._toggle_icon_column_visibility(self.hide_icons_check.isChecked())
        self.results_table.setSortingEnabled(False)
        self.results_table.setRowCount(len(results))
        mime_db = QMimeDatabase()

        for i, item in enumerate(results):
            path = item.get("path", "")
            item_type = _(item.get("type", "Unknown"))
            thumbnail = item.get("thumbnail")

            if isinstance(thumbnail, QImage):
                # Fast QImage to QPixmap conversion in main thread
                icon = QIcon(QPixmap.fromImage(thumbnail))
            else:
                # Theme icon fallback
                mime_type = mime_db.mimeTypeForFile(path)
                icon = QIcon.fromTheme(
                    mime_type.iconName(), QIcon.fromTheme("text-x-generic")
                )

            icon_item = QTableWidgetItem()
            icon_item.setIcon(icon)

            self.results_table.setItem(i, 0, icon_item)
            self.results_table.setItem(i, 1, QTableWidgetItem(path))
            self.results_table.setItem(i, 2, QTableWidgetItem(item_type))
        self.results_table.setSortingEnabled(True)

        self._update_status_label(len(results))
        self.btn_export.setEnabled(len(results) > 0)
        self._update_pagination_state()

    def _update_status_label(self, count):
        """Updates the status label with current range info."""
        current_offset = self.offset_spin.value()
        if count > 0:
            start_range = current_offset + 1
            end_range = current_offset + count
            self.status_label.setText(
                _("Showing {0}-{1} results").format(start_range, end_range)
            )
        else:
            self.status_label.setText(_("No results found."))

    def cancel_search(self):
        """Stops the current search worker."""
        if self.worker and self.worker.isRunning():
            # Forcing termination as search library calls can be blocking
            self.worker.terminate()
            self.worker.wait()
            self.status_label.setText(_("Search Canceled"))
            self.btn_prev_page.setEnabled(False)
            self.btn_next_page.setEnabled(False)
            # UI reset is handled by the 'finished' signal already connected to _on_search_finished

    def _export_to_csv(self):
        """Exports the current table results to a CSV file."""
        if self.results_table.rowCount() == 0:
            return

        # Renamed '_' to 'unused_filter' to prevent shadowing the global translation function
        file_path, unused_filter = QFileDialog.getSaveFileName(
            self, _("Save CSV"), "", _("CSV Files (*.csv)")
        )
        if not file_path:
            return

        try:
            with open(file_path, mode='w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                # Header row
                headers = []
                # Omitir la columna 0 (Icono) en la exportación
                for col in range(1, self.results_table.columnCount()):
                    header_item = self.results_table.horizontalHeaderItem(col)
                    headers.append(header_item.text() if header_item else f"Column {col}")
                writer.writerow(headers)

                # Data rows
                for row in range(self.results_table.rowCount()):
                    row_data = [
                        self.results_table.item(row, col).text()
                        for col in range(1, self.results_table.columnCount())
                    ]
                    writer.writerow(row_data)
        except Exception as e:
            print(f"CRITICAL: Failed to export to {file_path}: {e}")

    def _on_search_finished(self):
        """Cleanup or notification logic after search completion."""
        self.progress_bar.setVisible(False)
        self.btn_cancel.setVisible(False)
        self.btn_search.setVisible(True)
        if HAVE_SEARCH_LIB:
            self.btn_search.setEnabled(True)

    def _clear_filters(self):
        """
        Resets all search input fields and filters to their default states.
        """
        self.query_input.setEditText("")
        self.dir_input.setEditText("")
        self.type_combo.setCurrentIndex(0)  # "Any"
        self.sort_combo.setCurrentIndex(0)  # "auto"
        self.limit_spin.setValue(100)
        self.offset_spin.setValue(0)
        self.year_combo.setCurrentIndex(0)
        self.month_combo.setCurrentIndex(0)  # "Any"
        self.day_combo.setCurrentIndex(0)  # "Any"
        self.having_input.setEditText("")
        self.subquery_input.setEditText("")
        self.subquery_having_input.setEditText("")
        self.subquery_active_check.setChecked(False)
        self.hide_icons_check.setChecked(False)

        self.results_table.setRowCount(0)
        self.progress_bar.setVisible(False)
        self.btn_cancel.setVisible(False)
        self.btn_prev_page.setEnabled(False)
        self.btn_next_page.setEnabled(False)
        self.btn_search.setVisible(True)
        self.btn_export.setEnabled(False)
        self.status_label.setText(_("Ready"))
