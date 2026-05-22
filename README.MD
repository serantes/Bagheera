# Bagheera

Bagheera is a suite of tools designed to improve the KDE Baloo experience. The developed and planned tools are:

- **Search tool**
- **Image viewer**
- **Runner** (not available yet)

## 🛠 Technical Stack

- **Language:** Python 3.13+
- **GUI Framework:** PySide6 (Qt for Python)
- **KDE Integration:** Baloo search and basic management
- **Metadata Handling:** Advanced image header manipulation to store faces, pets, bodies, objects, and landmarks, with support for file extended attributes
- **Duplicate Detection:** Using perceptual hashing (pHash).

## 📥 Installation (Development)

Ensure you have at least Python 3.13, the necessary PySide6, LMDB, and Exiv2 dependencies, and the KDE development headers for Baloo installed on your system. For the best integration, install at least PySide6 via your system package manager. For better results, install all required libraries from your Linux distribution's repositories if they are available.

```bash
# Clone the repository
git clone https://github.com/serantes/Bagheera.git
cd Bagheera

# Create a virtual environment using system packages
python -m venv venv --system-site-packages
source venv/bin/activate

# Install the package with all dependencies
pip install ".[all]"

# Run applications
python -m bagheerasearch
python -m bagheeraview

# Run tests
python -m pytest
```

## 📥 Installation (Production)

Ensure you have at least Python 3.13, the necessary PySide6, LMDB, and Exiv2 dependencies, and the KDE development headers for Baloo installed on your system.

### System-Wide Installation
```bash
# Create an installation directory
mkdir -p "$HOME/.local/share/bagheera"
cd "$HOME/.local/share/bagheera"

# Install system-wide
pip install "bagheera-suite[faces,exiv] @ git+https://github.com/serantes/Bagheera.git"

# Run the applications
bagheerasearch
bagheeraview
```

### User Installation
```bash
# Create an installation directory
mkdir -p "$HOME/.local/share/bagheera"
cd "$HOME/.local/share/bagheera"

# Create python venv
python -m venv venv --system-site-packages
source venv/bin/activate

# Install
pip install "bagheera-suite[faces,exiv] @ git+https://github.com/serantes/Bagheera.git"

# Deactivate venv
deactivate

# Run the applications using the absolute venv paths
"$HOME/.local/share/bagheera/venv/bin/bagheerasearch"
"$HOME/.local/share/bagheera/venv/bin/bagheeraview"
```

## 🤝 Contributing

We follow an **English-first policy** for the codebase and documentation.

1.  **Fork** the project.
2.  Create your **Feature Branch** (`git checkout -b feature/AmazingFeature`).
3.  **Commit** your changes (`git commit -m 'Add some AmazingFeature'`).
4.  **Push** to the branch (`git push origin feature/AmazingFeature`).
5.  Open a **Pull Request**.

## 📋 Requirements

### System Dependencies

Bagheera requires KDE Frameworks 6 (specifically Baloo and KFileMetaData) and Qt 6 development headers to compile the C++ wrapper.

- KDE Frameworks 6 (Baloo, KFileMetaData, KCoreAddons)
- Qt 6 Core
- `pkg-config` and `g++` (for compilation)

### Python Dependencies

- `PySide6`
- `lmdb`
- `pyparsing`
- `psutil`
- `watchdog`
- `imagehash`

### Optional Python Dependencies

- `exiv2`
- `face-recognition`
- `face-recognition-models`
- `mediapipe`

### Prerequisites

Before installing, ensure your system has Python 3.13 and the following KF6 development libraries and tools installed:

#### openSUSE
```bash
zypper install kf6-baloo-devel kf6-kcoreaddons-devel python313-pyside6 pkgconf gcc
```

### Manual Compilation (Development)

If you need to compile the Baloo wrapper manually due to compilation issues or for development purposes:
```bash
cd "src/bagheerasearch/tools/baloo_wrapper/"
mkdir -p build && cd build
cmake .. && make
```

### Running Tests

To run the unit tests, ensure you have all dependencies and `pytest` installed. It is recommended to install the package in editable mode so that dependencies are resolved automatically:
```bash
source venv/bin/activate
pip install "bagheera-suite[test] @ git+https://github.com/serantes/Bagheera.git"
python -m pytest
```

## Search Tool

**Bagheera Search Tool** is a high-performance CLI client and library designed to enhance the file search experience in the **KDE** ecosystem. It acts as an enhanced interface for the **Baloo** search engine, adding features like natural language date parsing, advanced exclusion filters, and direct metadata extraction.

### 🚀 Key Features

- **Natural Language Queries**: Search for modified files using intuitive expressions like *`MODIFIED TODAY`*, *`MODIFIED LAST 2 WEEKS`*, or \*`MODIFIED 3 MONTHS AGO`\*.
- **Subquery Search**: Efficiently search directory structures and execute a second query on all files found.
- **Advanced Filtering**: Use **`--having`** and **`--subquery-having`** with the additional logical operator *`NOT`*, comparison operators like \*not equal\* *`!=`*, *does not contain* *`!:`*, *case-sensitive equal* *`==`*, and property-to-property comparisons like *`width > height`*.
- **Metadata Integration**: Direct access to file *tags* and *metadata* via **Baloo's LMDB index**.
- **CLI & Library**: Use it as a standalone command-line tool or integrate the *`BagheeraSearcher`* class into your own Python projects.

### Usage

#### Basic Search
```bash
# Fetch all files containing the terms 'Pink' and 'Floyd'.
bagheerasearch Pink Floyd
```

#### Natural Language Dates
```bash
# Fetch all files modified yesterday.
bagheerasearch MODIFIED YESTERDAY
```

#### Advanced Filtering

Exclude specific types or tags using complex logic:
```bash
# Fetch files containing 'report' while abandoning results where the file path includes 'pdf' or the file is marked with the 'Draft' tag.
bagheerasearch report --exclude "pdf OR tags:Draft"
```

#### Subquery Search

Execute a search over folders and include a second subquery for the results found inside those folders.
```bash
# Fetch all directories in '~/Documents' where the folder name contains 'KDE' and fetch all presentation files in those folders where the filename contains 'Baloo' or 'Bagheera'. Exclude files tagged as 'Obsolete' or 'Revised'.
bagheerasearch --directory '~/Documents' KDE --subquery 'Baloo OR Bagheera' --type Presentation --having 'NOT (tags=Obsolete OR tags=Revised)'
```

### Query Syntax

#### Comparison Operators

- `:` : Contains (text comparison)
- `=` : Equal
- `==` : Case-sensitive equal (available only in Bagheera 'having' expressions)
- `!=` : Not equal (available only in Bagheera 'having' expressions)
- `!:` : Does not contain (available only in Bagheera 'having' expressions)
- `>`, `>=`, `<`, `<=` : Numeric and date comparisons

#### Logical Operators

- `AND` : Available in Baloo queries and Bagheera 'having' expressions
- `OR` : Available in Baloo queries and Bagheera 'having' expressions
- `NOT` : Available in Bagheera 'having' expressions

#### Parentheses Operators

Parentheses are supported in both Baloo queries and Bagheera 'having' expressions.

#### Supported File Types

Use the `--type` flag or `type:` property:
`Archive`, `Audio`, `Document`, `Folder`, `Image`, `Presentation`, `Spreadsheet`, `Text`, `Video`.

#### Common Properties

These are some common properties available to use in queries (run `--help-query` for the full list):

- `filename`, `mimetype`, `modified`, `rating`, `tags`
- **Audio**: `Artist`, `Album`, `Duration`, `Genre`
- **Document**: `Author`, `PageCount`, `Title`
- **Media**: `Width`, `Height`, `ImageMake`, `PhotoFlash`

### BagheeraSearch Command Help

```text
    usage: bagheerasearch [-h] [-d DIRECTORY] [-e EXCLUDE] [-i] [-k] [-l LIMIT] [-o OFFSET] [-r [RECURSIVE]]
                          [-n RECURSIVE_INDENT] [-x RECURSIVE_EXCLUDE] [-s SORT] [-t TYPE] [-v] [--day DAY] [--month MONTH]
                          [--year YEAR] [--help-query] [--version]
                          [query]

    An improved search tool for Baloo

    positional arguments:
      query                 list of words to query for

    options:
      -h, --help            show this help message and exit
      -d, --directory DIRECTORY
                            limit search to specified directory tree
      -e, --exclude EXCLUDE
                            Search exclude pattern
      -i, --id              show document IDs
      -k, --konsole         show files using file:/ and quotes
      -l, --limit LIMIT     the maximum number of results
      -o, --offset OFFSET   offset from which to start the search
      -r, --recursive [RECURSIVE]
                            enable recursion with or without a query
      -n, --recursive-indent RECURSIVE_INDENT
                            recursive indent character
      -x, --recursive-exclude RECURSIVE_EXCLUDE
                            recursion exclude query
      -s, --sort SORT       sorting criteria <auto|none>
      -t, --type TYPE       type of Baloo data to be searched
      -v, --verbose         Verbose mode
      --day DAY             day fixed filter, --month is required
      --month MONTH         month fixed filter, --year is required
      --year YEAR           year fixed filter
      --help-query          show query syntax help
      --version             show version information
```

The full query syntax help is available by running:

```bash
    bagheerasearch --help-query
```

### 🌐 Internationalization (i18n)

BagheeraSearch is currently available only in **English**.

## BagheeraView

**BagheeraView** is an image viewer specifically designed for the KDE ecosystem. Built with **Python** and **PySide6**, it leverages **Baloo** to deliver a powerful, agile, and fluid metadata-based image management experience without abandoning classic folder-based navigation.

### 🚀 Key Features

- **Enhanced Baloo Search:** Blazing fast image retrieval using the **KDE Baloo** indexing framework. It features advanced capabilities not natively available in **Baloo**—such as **subquery search** and **results exclusion**—provided that the **BagheeraSearch** library is available.
- **Versatile Thumbnail Grid:** A fluid and responsive browser for large collections, offering **Flat View**, multiple **Date View** modes, **Rating View**, and **Folder View** modes.
- **Region Management:** Integrated computer vision to detect *faces* and *pets* within your photos and assign tag names. *Body*, *object*, and *landmark* regions are supported as well, but without automated computer vision detection.
- **Metadata Viewer:** A basic viewer and editor for **EXIF, IPTC, and XMP** data.
- **Tagging, Rating & Comments System:** Effortlessly manage tags, ratings, and comments that integrate directly with your filesystem's extended attributes and are natively used by **Baloo**.
- **Result Filtering:** Results can be filtered instantly by tags or filename.
- **Duplicates Management:** A system to detect and manage duplicate images using perceptual hashing, including an image comparison form and an ignore list.
- **Smart State Persistence:** The application remembers your workflow. Your **last used search**, **last used sort order**, and **view settings** are automatically saved and restored upon startup.
- **Favorites:** Favorite searches can be saved and reused.
- **Caching:** The thumbnail cache and image hashes are stored in highly performant local LMDB databases.
- **Window Manager Support:** **X11** and **Wayland** are fully supported. Note: Window layouts are not available when running natively under **Wayland**.

### 🌐 Internationalization (i18n)

BagheeraView is designed for a global audience with localized interface support. Initial supported languages include:

- **English** (Base development language)
- **Galician**
- **Spanish**

> **Note:** Following development consistency standards, all source code labels and developer logs are maintained in English.

### ⚙️ Configuration & Persistence

BagheeraView is built for workflow continuity. The application stores the user's environment state in the local configuration files:

- **Restore Last Layout:** Your last active layout and preferences are automatically saved and restored every time you launch the app.
- **Keyboard Configuration:** All hotkeys can be fully customized and parameterized by the user.
- **Interface Language:** The application automatically detects the system locale and applies the corresponding translation on startup, or the user can manually force a preferred language.

------------------------------------------------------------------------

*Bagheera uses Baloo's documentation as a reference but extends it with custom logic for a more robust CLI and graphical experience.*
