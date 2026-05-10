# Bagheera

Bagheera is a suite of tools designed to improve the KDE Baloo experience. Developed and planned tools are:

* **Search tool**
* **Image viewer** (not available yet)
* **Runner** (not available yet)

## Search Tool

**Bagheera Search Tool** is a high-performance CLI client and library designed to enhance the file search experience in the **KDE** ecosystem. It acts as an enhanced interface for the **Baloo** search engine, adding features like natural language date parsing, advanced exclusion filters, and direct metadata extraction.

### Features

*   **Natural Language Queries**: Search for files using intuitive expressions like *`MODIFIED TODAY`*, *`MODIFIED LAST 2 WEEKS`*, or *`MODIFIED 3 MONTHS AGO`*.
*   **Recursive Search**: Efficiently navigate directory structures with recursive search capabilities.
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

Before installing, ensure your system has the following KF6 development libraries and tools:

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
zypper install baloo6-6 kcoreaddons6-dev pkgconf gcc
```

#### Ubuntu / Debian (Testing/Unstable)

```bash
sudo apt install libkf6baloo-dev libkf6coreaddons-dev pkg-config gcc
```

### Installation
The installation process automatically compiles the required C++ wrapper (`libbaloo_wrapper.so`). Ensure you have the system dependencies installed before proceeding.

```bash
git clone https://github.net/serantes/Bagheera.git
sudo pip install Bagheera
rm -rf Bagheera # Optional if you want to remove sources.
```

**Bagheera Search** will be available typing *"bagheerasearch"* in your console.

If you don't want to install **Bagheera** system wide use *Python venv* to install it:

```bash
cd "<install_dir>"
git clone https://github.net/serantes/Bagheera.git
cd "Bagheera"
python -m venv venv
source venv/bin/activate
pip install .
deactivate
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
pip install -e . pytest
pytest
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
bagheerasearch "MODIFIED YESTERDAY"
```

#### Advanced Filtering
Exclude specific types or tags using complex logic:
```bash
# Fech files containing 'report' while excluding results where the file path includes 'pdf' or the file is marked with the 'Draft' tag.
bagheerasearch "report" --exclude "pdf OR tags:Draft"
```

#### Recursive Search

Recursive search over folders including a second query for folder results.

```bash
# Fetch all presentations in '~/Documents' where the obtainefolder name contains 'KDE' and the filename contains 'Baloo'.
bagheerasearch --directory ~/Documents  "KDE" --recursive "Baloo" --type Presentation
```

### Query Syntax

#### Comparison Operators
*   `:` : Contains (text comparison)
*   `=` : Equal
*   `==` : Case-sensitive equal (not available with Baloo but can be used by Bagheera for exclusion filters)
*   `!=` : Not equal (not available with Baloo but can be used by Bagheera for exclusion filters)
*   `>`, `>=`, `<`, `<=` : Numeric and date comparisons

#### Supported Types
Use the `--type` flag or `type:` property:
`Archive`, `Folder`, `Audio`, `Video`, `Image`, `Document`, `Spreadsheet`, `Presentation`, `Text`.

#### Common Properties
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

### Query help (obtained from bagheerasearch --help-query)
```txt
Bagheera Search Tool uses the Baloo search engine, which is part of the KDE ecosystem, to perform file searches so next help is obtained from Baloo documentation on 2025-01-01, with some additional information, and it may not be up to date with the latest features or changes in Baloo. For the most current information, please refer to the official Baloo documentation or resources.

Baloo offers a rich syntax for searching through your files. Certain attributes of a file can be searched through.

For example 'type' can be used to filter for files based on their general type:

  type:Audio OR type:Document

The following comparison operators are supported, but note that 'not equal' (!=) operator is not available in Baloo search engine.
  · :   - contains (only for text comparison)
  · =   - equal
  · >   - greater than
  · >=  - greater than or equal to
  · <   - less than
  · <=  - less than or equal to

Currently the following types, to use in --type property, are supported:
  · Archive
  · Folder
  · Audio
  · Video
  · Image
  · Document
    · Spreadsheet
    · Presentation
  · Text

These expressions can be combined using logical operators 'AND' or 'OR' and additional parenthesis, but note that 'NOT' logical operator is not available.


The full list of properties which can be searched is listed below. They are grouped by file types.

All Files
  · filename
  · mimetype
  · modified (formated as yyyy-MM-dd[ hh[:mm[:ss]]])
  · rating
  · tags
  · userComment

Audio
  · Album
  · AlbumArtist
  · Artist
  · BitRate
  · Channels
  · Comment
  · Composer
  · Duration (this value must be in seconds, for example use 'duration > 300' to find files longer than 5 minutes)
  · Genre
  · Lyricist
  · ReleaseYear
  · SampleRate
  · TrackNumber

Documents
  · Author
  · Copyright
  · CreationDate (formated as yyyy-MM-dd[ hh[:mm[:ss]]])
  · Generator
  · Keywords
  · Language
  · LineCount
  · PageCount
  · Publisher
  · Subject
  · Title
  · WordCount

Media
  · AspectRatio
  · FrameRate
  · Height
  · Width

Images
  · ImageDateTime
  · ImageMake
  · ImageModel
  · ImageOrientation
  · PhotoApertureValue
  · PhotoDateTimeOriginal
  · PhotoExposureBiasValue
  · PhotoExposureTime
  · PhotoFlash
  · PhotoFNumber
  · PhotoFocalLength
  · PhotoFocalLengthIn35mmFilm
  · PhotoGpsAltitude
  · PhotoGpsLatitude
  · PhotoGpsLongitude
  · PhotoISOSpeedRatings
  · PhotoMeteringMode
  · PhotoPixelXDimension
  · PhotoPixelYDimension
  · PhotoSaturation
  · PhotoSharpness
  · PhotoWhiteBalance

Next properties are undocumented but available in source code, may work or not, but worth trying:
  · AssistiveAlternateDescription
  · Arranger
  · AudioCodec
  · ColorSpace
  · Compilation
  · Conductor
  · Description
  · DiscNumber
  · Ensemble
  · Label
  · License
  · Location
  · Lyrics
  · Manufacturer
  · Model
  · Opus
  · OriginUrl
  · OriginEmailSubject
  · OriginEmailSender
  · OriginEmailMessageId
  · Performer
  · PixelFormat
  · ReplayGainAlbumPeak
  · ReplayGainAlbumGain
  · ReplayGainTrackPeak
  · ReplayGainTrackGain
  · TranslationUnitsTotal
  · TranslationUnitsWithTranslation
  · TranslationUnitsWithDraftTranslation
  · TranslationLastAuthor
  · TranslationLastUpDate
  · TranslationTemplateDate
  · VideoCodec

Baloo documentation ends here, but Bagheera Search Tool adds some extra features on top of it.

Search engine recognizes some natural language sentences in English, as long as they are capitalized, and transforms them into queries that can be interpreted by the search engine.

Supported natural language sentences and patterns for queries are:
  · MODIFIED TODAY
  · MODIFIED YESTERDAY
  · MODIFIED THIS [ DAY | WEEK | MONTH | YEAR ]
  · MODIFIED LAST <NUMBER> [ DAYS | WEEKS | MONTHS | YEARS ]
  · MODIFIED <NUMBER> [ DAYS | WEEKS | MONTHS | YEARS ] AGO

<NUMBER> can be any number or a number text from ONE to TWENTY.


The --exclude and --recursive-exclude options allow you to filter files out of the results.
The syntax for both options supports parentheses and logical operators (AND, OR, and NOT) to combine multiple patterns.
In addition to standard query comparison operators, the not equal (!=) operator is available for comparing properties against specific values. Furthermore, you can compare two properties directly; for example, 'width > height' is a valid expression.

Remarks:
  · Text comparisons are case sensitive with '==' operator but case insensitive with '=' and ':' operator. For example, 'filename:report' would match 'report.docx', 'Report.docx', and 'REPORT.docx', while 'filename=report.docx' would only match 'report.docx'.
  · Tags comparisons are performed against both individual full tag string (using the '/' character as a level separator) and each individual level. All individual level values are normalized to lowercase and stripped of accents or diacritics. For example, a file tagged as 'Opera,Person/María Callas,Singer' would match any of the following elements: ['Opera', 'Person/María Callas', 'Singer', 'callas', 'maria', 'opera', 'person', 'singer']."
  · Only text and numeric data are supported, dates are not supported as of now.
  · Baloo limit of at least three characters for property values is not applied in --exclude and --recursive-exclude options, so you can use shorter values in those options.

For example, if you have a tag named 'Science' and another one 'Science Fiction' you can't obtain only results tagged with 'Science' becouse Baloo search engine will match both 'Science' and 'Science Fiction' tags when you use 'tags:Science' in your query. To exclude results tagged with 'Science Fiction' you can use the following query:
    bagheerasearch --exclude tags:Fiction tags:Science
```

---
*Bagheera uses Baloo documentation as a reference, but extends it with custom logic for a more robust CLI experience.*
