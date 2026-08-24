# Bagheera Search User Manual

## 1. Introduction

**Bagheera Search** is a high-performance search utility and library that enhances the standard **KDE Baloo** search experience. It allows users to locate files using a combination of file metadata, hierarchical tags, and advanced logical expressions.

## 2. Command Line Interface (CLI)

The primary way to interact with the search engine is via the `bagheerasearch` command.

### Basic Usage

```bash
bagheerasearch "your query terms" [options]
```

### Global Options

- `--help-query`: Shows detailed help regarding the supported query syntax.
- `--type [type]`: Filters results by file type (e.g., `image`, `video`, `audio`).
- `--having [query]`: Applies a filtering expression over the initial query results.
- `--subquery [query]`: Enables a secondary search over the folders returned by the main query.
- `--subquery-having [query]`: Applies a filtering expression over the subquery results.
- `--id`: Displays document IDs.
- `--konsole`: Displays files using the `file:/` protocol and quotes.
- `--year [YYYY]`: Filters results by a specific year.
- `--month [MM]`: Filters results by month (requires `--year`).
- `--day [DD]`: Filters results by day (requires `--year` and `--month`).
- `--version`: Displays the current version of the **Bagheera Search**.

For more options, please consult the CLI help (`--help`).

---

## 3. Query Syntax

**Bagheera** Search supports Baloo's rich query syntax for keyword matching. Additionally, the `having` options support an even more advanced syntax for fine-grained filtering.

### Logical Operators

Combine multiple criteria using uppercase logical operators:

- `AND`: Both conditions must be true.
- `OR`: At least one condition must be true.
- `NOT`: Inverts the following condition (only available within `having` options).
- `(...)`: Use parentheses to group expressions and define the order of evaluation.

**Example:** `bagheerasearch type=images AND modified>2025-01-01 --having "(vacaciones OR summer) AND NOT (work OR trabajo)"`

### Property Filters

Filter by specific file metadata using the `property <operator> value` syntax. When using having options, you can also use `property <operator> property` to compare two different metadata fields.

| Property   | Description                                                                       |
| ---------- | --------------------------------------------------------------------------------- |
| `tags`     | Keywords or labels assigned to the file.                                          |
| `rating`   | File rating (from 1 to 10).                                                       |
| `filename` | The name of the file.                                                             |
| `height`   | Image height in pixels.                                                           |
| `width`    | Image width in pixels.                                                            |
| `type`     | The file **Baloo** type (a full list of available types is provided in Chapter 6) |
| `mimetype` | The file mimetype (e.g., `jpeg`).                                                 |

A full list of available properties is provided in Chapter 7.

### Comparison Operators

**Bagheera** supports various ways to compare values:

- `=`: Equals.
- `==`: Strict equality (case-sensitive), available only with `having` options.
- `!=`: Not equal, available only with `having` options.
- `>` / `<`/ `>=`/ `<=`: Greater than, less than, greater than or equal to, less than or equal to (for numeric values and dates).
- `:`:  Contains or flexible match (case-insensitive).
- `!:`: Does not contain, available only with `having` options.

**Examples:**

- **Find large images**: `bagheerasearch width > 1920 AND height > 1080`
- **Find specific ratings**: `bagheerasearch rating = 5`
- **Property-to-Property comparison**: `bagheerasearch --having width > height` (finds landscape images).

---

## 4. Advanced Date Parsing

One of **Bagheera's** standout features is its **English Natural Language Date Parser**, which allows you to filter files by their modification date using human-readable strings.

### Supported Expressions

- `MODIFIED TODAY`: Files changed since midnight.
- `MODIFIED YESTERDAY`: Files changed during the previous day.
- `MODIFIED LAST [N] DAYS`: Files changed within the last N days (e.g., `MODIFIED LAST 7 DAYS`).
- `MODIFIED [N] YEAR AGO`: Files modified during that specific calendar year.
- **Number Conversion**: You can use words from ONE to TWENTY instead of digits (e.g., `MODIFIED LAST TWO DAYS`).

---

## 5. Tag Management

**Bagheera** handles tags with high precision, including the hierarchical tags often used in KDE/Dolphin.

### Hierarchical Tags

Tags are stored with a path-like structure (e.g., `Person/Julia`).

- **Searching**: Use `tags:Julia` to find anything tagged with "Julia" regardless of the parent category.
- **Explicit Matching**: Use `tags="Person/Julia"` for exact path matches.

### Known Behaviors & Tips

- **Space Handling**: To search for tags containing spaces (e.g., "María Callas"), you must search for the individual parts: `tags:Maria AND tags:Callas`. This is because the **Baloo engine** does not support quoted strings within the tag search.
- **Normalization**:  Both **Baloo** and **Bagheera** automatically handle accents and diacritics. Searching for `tags:vacacion` will match "Vacación".

---

## 6. Supportted types

The following types, to use in `--type` option or `type` property, are supported:

* Archive
* Folder
* Audio
* Video
* Image
* Document
  * Spreadsheet
  * Presentation
* Text

---

## 7. Supportted searchable properties

Properties are grouped by file type for easier reference..

### All Files
* filename
* mimetype (Note: You cannot search for full strings like `"text/plain"`. Search for individual words: `mimetype:text AND mimetype:plain`)
* modified (Formatted as yyyy-MM-dd)
* rating
* tags
* type
* userComment (Note: Search for individual words: `userComment:ready AND userComment:script` because **Baloo engine** does not support quoted strings within the `userComment` search)

### Audio
* Album
* AlbumArtist
* Artist
* BitRate
* Channels
* Comment
* Composer
* Duration (Value in seconds; e.g., `'duration > 300'` for files longer than 5 minutes)
* Genre
* Lyricist
* ReleaseYear
* SampleRate
* TrackNumber

### Documents
* Author
* Copyright
* CreationDate (Formatted as yyyy-MM-dd)
* Generator
* Keywords
* Language
* LineCount
* PageCount
* Publisher
* Subject
* Title
* WordCount

### Media
* AspectRatio
* FrameRate
* Height
* Width

### Images
* ImageDateTime (Formatted as yyyy-MM-dd. Note: Currently inconsistent in **Baloo**; use in `having` options for reliability).
* ImageMake
* ImageModel
* ImageOrientation
* PhotoApertureValue
* PhotoDateTimeOriginal
* PhotoExposureBiasValue
* PhotoExposureTime
* PhotoFlash
* PhotoFNumber
* PhotoFocalLength
* PhotoFocalLengthIn35mmFilm
* PhotoGpsAltitude
* PhotoGpsLatitude
* PhotoGpsLongitude
* PhotoISOSpeedRatings
* PhotoMeteringMode
* PhotoPixelXDimension
* PhotoPixelYDimension
* PhotoSaturation
* PhotoSharpness
* PhotoWhiteBalance

### Other available properties

The following properties are undocumented but available in the source code. They may or may not work, but are worth trying:

* AssistiveAlternateDescription
* Arranger
* AudioCodec
* ColorSpace
* Compilation
* Conductor
* Description
* DiscNumber
* Ensemble
* Label
* License
* Location
* Lyrics
* Manufacturer
* Model
* Opus
* OriginUrl
* OriginEmailSubject
* OriginEmailSender
* OriginEmailMessageId
* Performer
* PixelFormat
* ReplayGainAlbumPeak
* ReplayGainAlbumGain
* ReplayGainTrackPeak
* ReplayGainTrackGain
* TranslationUnitsTotal
* TranslationUnitsWithTranslation
* TranslationUnitsWithDraftTranslation
* TranslationLastAuthor
* TranslationLastUpDate
* TranslationTemplateDate
* VideoCodec

---

## 8. Having

The `--having` option allows you to filter the results returned by **Baloo**. It supports the standard **Baloo** syntax plus the `NOT` operator.

Additionally, you can use:

- `==` (case-sensitive equal)
- `!=` (not equal)
- `!:` (does not contains)
- Property-to-property comparison (e.g., `width > height`).
- `created`: A **Bagheera-specific** property for file creation dates (Formatted as `yyyy-MM-dd`).

### Important Remarks:

- **Case Sensitivity**: All text comparisons are case-insensitive unless `==` is used.
- **Empty Values**: You can check for the presence or absence of values using empty quotes. For example, `tags!=""` matches any file with at least one tag, while `tags=""` matches files with no tags.
- **Tag Levels**: Comparisons are performed against the full tag path and each individual level. A file tagged `Person/Maria Callas` matches `Maria`, `Callas`, `Person`, and the full string.
- **Character Limit**: Unlike **Baloo**, the 3-character minimum limit for string values is not enforced within `having` options.

---

## 9. Subqueries

**Bagheera** supports a secondary search within the folders returned by a main query. This is particularly useful for deep searches.

When using `--subquery`, the main query first identifies relevant folders; the subquery is then applied to the files contained within those folders. You can also use `--subquery-having` to filter these results further.

**Example:** Search for folders named "Project" and find documents within them modified in the last week.

```bash
bagheerasearch Project –subquery MODIFIED LAST WEEK
```

---

## 10. Examples

Here are some practical examples of how to use **Bagheera Search** effectively:

```bash
# JPEG images taken today.
bagheerasearch --type image MODIFIED TODAY

# Landscape photos not tagged as "Work".
bagheerasearch --type image --having "width > height AND NOT tags:Work"

# Find high-rated files from last year.
bagheerasearch "rating >= 9 AND MODIFIED 1 YEAR AGO"

# Complex multi-criteria search.
bagheerasearch "(tags:cosplay OR tags:portrait) AND width < 1000 AND rating > 0"

# Get files from folders named "KDE" in "~/Documents".
bagheerasearch --directory '~/Documents' KDE --subquery

# Get al presentations not tagged as "Obsolete" or "Revised" from folders named "KDE" in "~/Documents".
bagheerasearch --directory '~/Documents' KDE --subquery 'Baloo OR Bagheera' --type Presentation --having 'NOT (tags=Obsolete OR tags=Revised)'

# Get files tagget as "Science" ignoring "Science Fiction" tag.
bagheerasearch tags=Science --having "NOT tags=Fiction"
```

---

## 11. Troubleshooting

### Missing Metadata

Ensure **Baloo** is enabled and has finished indexing (`balooctl6 status`). Bagheera reads the index located at `~/.local/share/baloo/index`.

### Dependency Issues

Bagheera requires the compiled C++ wrapper `libbaloo_wrapper.so`. If the tool fails to start, ensure you have the `KF6Baloo` and `Qt6Core` development headers installed and reinstall the package to trigger the `setup.py` compilation.
