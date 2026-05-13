# Bagheera

Bagheera is a suite of tools designed to improve the KDE Baloo experience. Developed and planned tools are:

* **Search tool**
* **Image viewer**
* **Runner** (not available yet)

## Search Tool

**Bagheera Search Tool** is a high-performance CLI client and library designed to enhance the file search experience in the **KDE** ecosystem. It acts as an enhanced interface for the **Baloo** search engine, adding features like natural language date parsing, advanced exclusion filters, and direct metadata extraction.

### Features

*   **Natural Language Queries**: Search for modified files using intuitive expressions like *`MODIFIED TODAY`*, *`MODIFIED LAST 2 WEEKS`*, or *`MODIFIED 3 MONTHS AGO`*.
*   **Recursive Search**: Efficiently search directory structures and execute a second query in all files found.
*   **Advanced Filtering**: Use **`--exclude`** and **`--recursive-exclude`** with support for logical operators (*`AND`*, *`OR`*, *`NOT`*) and comparison operators (including *`!=`* and property-to-property comparisons like *`width > height`*).
*   **Metadata Integration**: Direct access to file *tags* and *metadata* via **Baloo's LMDB index**.
*   **CLI & Library**: Use it as a standalone command-line tool or integrate the *`BagheeraSearcher`* class into your own Python projects.

### Requirements

#### System Dependencies
Bagheera requires KDE Frameworks 6 (specifically Baloo and KFileMetaData) and Qt 6 development headers to compile the C++ wrapper.

*   KDE Frameworks 6 (Baloo, KFileMetaData, KCoreAddons)
*   Qt 6 Core
*   `pkg-config` and `g++` (for compilation)

#### Python Dependencies
*   `lmdb`
*   `pyparsing`

#### Prerequisites

Before installing, ensure your system has Python 3.13 and the following KF6 development libraries and tools:

#### Arch Linux

```bash
sudo pacman -S baloo6 kcoreaddons6 pkgconf gcc
```

#### Fedora

```bash
sudo dnf install kf6-baloo-devel kf6-kcoreaddons-devel pkgconf-pkg-config gcc
```

#### openSuSE

```bash
zypper install kf6-baloo-devel kf6-kcoreaddons-devel python313-pyside6 pkgconf gcc
```

#### Ubuntu / Debian (Testing/Unstable)

```bash
sudo apt install libkf6baloo-dev libkf6coreaddons-dev pkg-config gcc
```

### Installation
The installation process automatically compiles the required C++ wrapper (`libbaloo_wrapper.so`). Ensure you have the system dependencies installed before proceeding.

```bash
git clone https://github.net/serantes/Bagheera.git
sudo pip install "$PWD/Bagheera[faces,exiv]"
rm -rf Bagheera # Optional if you want to remove sources.
```

**Bagheera Search** will be available typing *"bagheerasearch"* in your console.

If you don't want to install **Bagheera** system wide use *Python venv* to install it:

```bash
cd "<install_dir>"
git clone https://github.net/serantes/Bagheera.git
cd "Bagheera"
python -m venv venv --system-site-packages
source venv/bin/activate
pip install "$PWD/Bagheera[faces,exiv]"
deactivate
rm -rf Bagheera # Optional if you want to remove sources.
```

**Bagheera Search** will be available typing "<install_dir>/Bagheera/venv/bin/bagheerasearch" in your console, but you can create an alias or a link in your path to call it.


#### Manual Compilation (Development)
If you need to compile the wrapper manually for development purposes:
```bash
g++ -shared -fPIC -std=c++17 -o libbaloo_wrapper.so src/bagheerasearch/tools/baloo_wrapper/baloo_wrapper.cpp $(pkg-config --cflags --libs KF6Baloo KF6FileMetaData Qt6Core) -I/usr/include/KF6 -I/usr/include/qt6
```

#### Running Tests

To run the unit tests, ensure you have all dependencies and `pytest` installed. It is recommended to install the package in editable mode so that dependencies are resolved automatically:

```bash
source venv/bin/activate
pip install -e .['tests'] pytest
python -m pytest
```

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

#### Recursive Search

Recursive search over folders including a second query for folder results.

```bash
# Fetch all directories in '~/Documents' where the folder name contains 'KDE' and fech all presentation files in that folders where the filename contains 'Baloo' or 'Bagheera'.
bagheerasearch --directory ~/Documents KDE --recursive "Baloo OR Bagheera" --type Presentation
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

#### Supported Types
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

---
*Bagheera uses Baloo documentation as a reference, but extends it with custom logic for a more robust CLI experience.*
