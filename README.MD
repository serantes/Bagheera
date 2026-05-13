# Bagheera

Bagheera is a suite of tools designed to improve the KDE Baloo experience. Developed and planned tools are:

* **Search tool**
* **Image viewer**
* **Runner** (not available yet)



## 🛠 Technical Stack

- **Language:** Python 3
- **GUI Framework:** PySide6 (Qt for Python)
- **KDE Integration:** Baloo search and basic management
- **Metadata Handling:** Advanced image header manipulation to store faces, pets, body, objects and landmarks and support to file extended attributes
- **Duplicate Detection:** Two methods to detect duplicates, hashing and open vision



## 📥 Installation (Development)

Ensure you have at least Python 3.13, the necessary PySide6, LMDB and Exiv2 dependencies and KDE development headers for Baloo installed on your system. For best integration install at least PySide6 in your system, but for better results install all required libraries on your system if they are available in your Linux distribution.

Bash

```bash
# Clone the repository
git clone https://github.net/serantes/Bagheera.git
cd Bagheera
python -m venv venv python -m venv venv --system-site-packages
sudo pip install ".[all]"

# Run applications
source venv/bin/activate
python -m bagheerasearch
python -m bagheeraview
```



## 📥 Installation (Production)

Ensure you have at least Python 3.13, the necessary PySide6, LMDB and Exiv2 dependencies and KDE development headers for Baloo installed on your system. For best integration install at least PySide6 in your system, but for better results install all required libraries on your system if they are available in your Linux distribution.

System wide installation

Bash

```bash
# Clone the repository
cd /tmp
git clone https://github.net/serantes/Bagheera.git

cd Bagheera
pip install "$PWD/Bagheera[faces,exiv]"

# Run the applications
bagheerasearch
bagheeraview
```

User  installation

Bash

```bash
# Clone the repository
cd /tmp
git clone https://github.net/serantes/Bagheera.git

# Create an installation directory
mkdir "<an apps folder>/bagheera"
cd "<an apps folder>/bagheera"
python -m venv venv --system-site-packages
source venv/bin/activate

# Install dependencies
pip install "/tmp/Bagheera[faces,exiv]"

# Deactivate venv
deactivate

# Run the applications
"<an apps folder>/bagheera/venv/bin/bagheerasearch"
"<an apps folder>/bagheera/venv/bin/bagheerasearch"
```



## 🤝 Contributing

We follow an **English-first policy** for the codebase and documentation.

1.  **Fork** the project.

2.  Create your **Feature Branch** (`git checkout -b feature/AmazingFeature`).

3.  **Commit** your changes (`git commit -m 'Add some AmazingFeature'`).

4.  **Push** to the branch (`git push origin feature/AmazingFeature`).

5.  Open a **Pull Request**.****



## Requirements

### System Dependencies

Bagheera requires KDE Frameworks 6 (specifically Baloo and KFileMetaData) and Qt 6 development headers to compile the C++ wrapper.

*   KDE Frameworks 6 (Baloo, KFileMetaData, KCoreAddons)
*   Qt 6 Core
*   `pkg-config` and `g++` (for compilation)

### Python Dependencies

*   `PySide6`
*   `lmdb`
*   `pyparsing`
*   `psutil`
*   `watchdog`
*   `imagehash`

### Optional Python Dependencies

*   `exiv2`
*   `face-recognition`
*   `face-face_recognition_models`
*   `mediapipe`

### Prerequisites

Before installing, ensure your system has Python 3.13 and the following KF6 development libraries and tools:

### openSuSE

```bash
zypper install kf6-baloo-devel kf6-kcoreaddons-devel python313-pyside6 pkgconf gcc
```

### Manual Compilation (Development)

If you need to compile the Baloo wrapper manually for compilation problems or development purposes:
```bash
cd "src/bagheerasearch/tools/baloo_wrapper/"
mkdir -p build && cd build && cmake .. && make
```

### Running Tests

To run the unit tests, ensure you have all dependencies and `pytest` installed. It is recommended to install the package in editable mode so that dependencies are resolved automatically:

```bash
source venv/bin/activate
pip install -e .['test'] pytest
python -m pytest
```



## Search Tool

**Bagheera Search Tool** is a high-performance CLI client and library designed to enhance the file search experience in the **KDE** ecosystem. It acts as an enhanced interface for the **Baloo** search engine, adding features like natural language date parsing, advanced exclusion filters, and direct metadata extraction.

### 🚀 Key Features

*   **Natural Language Queries**: Search for modified files using intuitive expressions like *`MODIFIED TODAY`*, *`MODIFIED LAST 2 WEEKS`*, or *`MODIFIED 3 MONTHS AGO`*.
*   **Subquery Search**: Efficiently search directory structures and execute a second query in all files found.
*   **Advanced Filtering**: Use **`--having`** and **`--subquery-having`** with additional logical operator *`NOT`*, comparison operators *not equal* *`!=`*, *not contains* *`!:`* and *case-sensitive equal* *`==`*, and property-to-property comparisons like *`width > height`*.
*   **Metadata Integration**: Direct access to file *tags* and *metadata* via **Baloo's LMDB index**.
*   **CLI & Library**: Use it as a standalone command-line tool or integrate the *`BagheeraSearcher`* class into your own Python projects.

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
# Fech files containing 'report' while excluding results where the file path includes 'pdf' or the file is marked with the 'Draft' tag.
bagheerasearch report --exclude "pdf OR tags:Draft"
```

#### Subquery Search

Query search over folders including a second query for folder results.

```bash
# Fetch all directories in '~/Documents' where the folder name contains 'KDE' and fech all presentation files in that folders where the filename contains 'Baloo' or 'Bagheera'. Exclude from results files tagged as 'Obsolete' or 'Revised'.
bagheerasearch --directory '~/Documents' KDE --subquery 'Baloo OR Bagheera' --type Presentation --having 'NOT (tags=Obsolete OR tags=Revised)'
```

### Query Syntax

#### Comparison Operators
*   `:` : Contains (text comparison)
*   `=` : Equal
*   `==` : Case-sensitive equal (available only in Bagheera having expressions)
*   `!=` : Not equal (available only in Bagheera having expressions)
*   `!:` : Not contains (available only in Bagheera having expressions)
*   `>`, `>=`, `<`, `<=` : Numeric and date comparisons

#### Logical Operators
*   `AND` : Available on Baloo queries and Bagheera having expressions
*   `OR` : Available on Baloo queries and Bagheera having expressions
*   `NOT` : Available on Bagheera having expressions

#### Parenthesis Operators

Parenthesis are available in Baloo queries and Bagheera having expressions

#### Supported File Types
Use the `--type` flag or `type:` property:
`Archive`, `Audio`, `Document`, `Folder`, `Image`,`Presentation`,  `Spreadsheet`, `Text`, `Video`.

#### Common Properties
These are some common properties available to use in queries (full list in help).
*   `filename`, `mimetype`, `modified`, `rating`, `tags`
*   **Audio**: `Artist`, `Album`, `Duration`, `Genre`
*   **Document**: `Author`, `PageCount`, `Title`
*   **Media**: `Width`, `Height`, `ImageMake`, `PhotoFlash`

### BagheeraSearch command help
```txt
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
                        enable recurse with or without a query
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

Full query help are available typing:
```bash
 bagheerasearch --help-query
```

### 🌐 Internationalization (i18n)

BagheeraSearch currently is only available on  **English**.



## BagheeraView

**BagheeraView** is an image viewer specifically designed for the KDE ecosystem. Built with **Python** and **PySide6**, it leverages **Baloo** to deliver a powerful, agile, and fluid metadata-based image management experience without abandoning classic folder management.



### 🚀 Key Features

- **Enhanced Baloo Search:** Blazing fast image retrieval using the **KDE Baloo** indexing framework, featuring advanced capabilities not natively available in **Baloo**, such as **subquery search** and results **exclusion**, if **BagheeraSearch** library is available.

- **Versatile Thumbnail Grid:** A fluid and responsive browser for large collections, offering **Flat View**, several **Date View** modes, **Rating View** and **Folder View** modes.

- **Areas Management:** Integrated computer vision to detect *faces* and *pets* within your photos and assign tag names. *Body*, *object* and *landmark* areas are supported too but without computer vision detection.

- **Metadata:** A basic viewer and editor for **EXIF, IPTC, and XMP** data.

- **Tagging, Rating & Comments System:** Effortlessly manage tags, ratings and comments that integrate directly with your filesystem's extended attributes and used by **Baloo**.

- **Filter resuls:** Results can be filtered by tags or file name.

- **Duplicates Management:** A system to detect and manage duplicates using percentual hashing including a images comparison form and ignore list.

- **Smart State Persistence:** The application remembers your workflow. Your **last used search**, **last used sort order** and **view settings** are automatically saved and restored upon startup.

- **Favorites:** Favorite searchs can be saved and reused.

- **Cache:** Thumbnails cache and image hashes are cached on LMDB databases.

- **Window Manager Support:** **X11** and **Wayland** are supported, but in **Wayland** mode layouts are not available.



### 🌐 Internationalization (i18n)

BagheeraView is designed for a global audience with localized interface support. Initial supported languages include:

- **English** (Base development language)

- **Galician**

- **Spanish**

> **Note:** Following internal configuration standards, all source code labels and developer logs are maintained in English for technical consistency.



### ⚙️ Configuration & Persistence

BagheeraView is built for workflow continuity. The application stores the user's environment state in the local configuration:

- **Restore Last Layout:** Last layout and preferences are automatically saved and restored every  time you launch it.

- **Keyboard configuration:** All hotkeys can be parametriced by the user.

- **Interface Language:** The application automatically detects the system locale and applies the corresponding translation on startup or user can decide main language.

---
*Bagheera uses Baloo documentation as a reference, but extends it with custom logic for a more robust CLI experience.*

